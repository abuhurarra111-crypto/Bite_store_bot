# ============================================================
# ⚡ v85: SUPPLIER AUTOMATION — 4 features in one module
# ============================================================
#   1. Auto-Sync every 30s (price+stock for synced_to_shop=1 products)
#      + every 5 min supplier balance refresh
#   2. Bulk Sync — 1 tap to sync all products of a supplier
#   3. Low Balance Alerts — DM admin when supplier balance < threshold
#      (per-supplier threshold, default $3.00)
#   4. Finance Dashboard — revenue / cost / profit for
#      today / yesterday / week / month, per-supplier breakdown
#
# NO schema changes. Uses:
#   - ext_suppliers.low_bal_threshold  (already exists)
#   - ext_suppliers.balance_usd        (already exists)
#   - ext_products.synced_to_shop      (v83, already exists)
#   - ext_products.shop_product_id     (v82, already exists)
#   - orders                           (existing)
#   - bot_settings.low_bal_alert_last_<sid>  (added on demand)
#   - bot_settings.autosync_enabled           (default "1")
# ============================================================

import asyncio
import logging
import time
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_ID
from database import get_connection, get_setting, set_setting
from utils import escape_md   # 🆕 v103: for finance dashboard error surface

logger = logging.getLogger(__name__)

# 🆕 v89: RE-ENTRANCY LOCKS — prevent overlapping JobQueue runs.
# If a run takes >30s (slow supplier API), the next tick would otherwise
# fire while the previous is still going → race conditions on the same
# product rows. These locks make the job idempotent per tick.
_AUTOSYNC_PS_RUNNING = False   # price+stock job lock
_AUTOSYNC_BAL_RUNNING = False  # balance job lock

# ------------------------------------------------------------
# Defaults
# ------------------------------------------------------------
DEFAULT_LOW_BAL_THRESHOLD = 3.00      # $3 default per new supplier
LOW_BAL_ALERT_COOLDOWN = 6 * 3600     # don't DM same alert more than every 6h
AUTOSYNC_PRICE_STOCK_INTERVAL = 30    # seconds — price+stock refresh
AUTOSYNC_BALANCE_INTERVAL = 300       # seconds — every 5 min balance too


# ============================================================
# 1. AUTO-SYNC JOBS
# ============================================================
def is_autosync_enabled() -> bool:
    return str(get_setting("autosync_enabled", "1")) == "1"

def set_autosync(on: bool):
    set_setting("autosync_enabled", "1" if on else "0")


async def autosync_price_stock_job(context):
    """
    Runs every 30 seconds.
    For every ext_product with synced_to_shop=1:
      - re-fetch its supplier's product list (once per supplier per tick)
      - update the matching ext_product row's cost_usd + stock
      - recompute sell_price via _compute_sell_price (SMART LOCK respected)
      - mirror the change to `products` table (price + stock only)

    Bulk-fetches once per supplier (not once per product) → API-friendly.

    🆕 v89: re-entrancy protected — if previous tick still running, skip.
    🆕 v89: adapter HTTP calls wrapped in asyncio.to_thread → non-blocking.
    """
    global _AUTOSYNC_PS_RUNNING
    if _AUTOSYNC_PS_RUNNING:
        logger.warning("[AutoSync] previous price+stock tick still running — skipping this tick")
        return
    if not is_autosync_enabled():
        return
    _AUTOSYNC_PS_RUNNING = True
    _tick_start = time.time()
    try:
        try:
            from ext_suppliers import (
                list_suppliers, get_adapter_for_supplier, get_ext_products,
                _compute_sell_price, update_ext_product, get_connection as _gc,
            )
            from async_adapter_helpers import async_fetch_products
        except Exception as e:
            logger.debug(f"[AutoSync] import fail: {e}")
            return

        # Find which suppliers actually have live-synced products.
        # 🆕 v89: also gate on supplier being enabled (skip disabled suppliers)
        conn = _gc(); c = conn.cursor()
        c.execute("""SELECT DISTINCT ep.supplier_id
                      FROM ext_products ep
                      JOIN ext_suppliers s ON s.id = ep.supplier_id
                      WHERE ep.synced_to_shop=1 AND ep.active=1
                        AND s.enabled=1""")
        live_sup_ids = [int(r["supplier_id"]) for r in c.fetchall()]
        conn.close()

        if not live_sup_ids:
            return  # nothing to sync

        total_updated = 0
        total_price_changes = 0
        total_stock_changes = 0

        for sid in live_sup_ids:
            try:
                sup = None
                for s in list_suppliers(include_disabled=False):
                    if s["id"] == sid:
                        sup = s; break
                if not sup:
                    continue

                ad = get_adapter_for_supplier(sup)
                if not ad:
                    continue

                # Bulk fetch supplier's live product list — ASYNC
                fresh = await async_fetch_products(ad)
                if not fresh:
                    logger.debug(f"[AutoSync] no products / fetch fail sup#{sid}")
                    continue

                fresh_by_remote = {}
                for p in fresh:
                    fresh_by_remote[str(p.get("remote_id"))] = p

                # For each live-synced ext_product of this supplier, apply updates
                our_prods = get_ext_products(supplier_id=sid, active_only=False)
                for ep in our_prods:
                    if not int(ep.get("synced_to_shop") or 0):
                        continue
                    remote_id = str(ep.get("remote_id"))
                    if remote_id not in fresh_by_remote:
                        continue
                    fresh_p = fresh_by_remote[remote_id]

                    new_cost = float(fresh_p.get("cost_usd") or 0)
                    new_stock = int(fresh_p.get("stock") or 0)
                    old_cost = float(ep.get("cost_usd") or 0)
                    old_stock = int(ep.get("stock") or 0)

                    # Recompute sell using SMART LOCK
                    new_sell = _compute_sell_price(
                        cost_usd=new_cost,
                        markup_pct=float(ep.get("markup_pct") or 0),
                        fixed_price=float(ep.get("fixed_price") or 0),
                        fixed_price_base=float(ep.get("fixed_price_base") or 0),
                    )

                    cost_changed = abs(new_cost - old_cost) > 0.001
                    stock_changed = new_stock != old_stock
                    stock_increased = new_stock > old_stock  # 🆕 v94 for restock alert

                    if not cost_changed and not stock_changed:
                        continue

                    # Update ext_product
                    update_ext_product(
                        int(ep["id"]),
                        cost_usd=new_cost,
                        stock=new_stock,
                        sell_price=new_sell,
                    )
                    if cost_changed: total_price_changes += 1
                    if stock_changed: total_stock_changes += 1

                    # Mirror to shop products table (in-place UPDATE)
                    shop_pid = int(ep.get("shop_product_id") or 0)
                    if shop_pid > 0:
                        try:
                            conn2 = _gc(); c2 = conn2.cursor()
                            c2.execute("""UPDATE products
                                           SET price=?, cost_price=?, stock=?
                                           WHERE id=?""",
                                        (new_sell, new_cost, new_stock, shop_pid))
                            conn2.commit(); conn2.close()
                            total_updated += 1

                            # 🆕 v94: fire restock broadcast if stock went UP
                            # on a synced-to-shop product. Uses fake activity
                            # destination + bc_stock template + Buy Now button.
                            if stock_increased:
                                try:
                                    from restock_alerts import fire_restock_alert
                                    added = new_stock - old_stock
                                    await fire_restock_alert(
                                        context.bot, shop_pid, added, new_stock
                                    )
                                except Exception as _rea:
                                    logger.debug(f"[AutoSync] restock alert fail pid={shop_pid}: {_rea}")
                        except Exception as e:
                            logger.debug(f"[AutoSync] mirror fail #{shop_pid}: {e}")
            except Exception as e:
                logger.warning(f"[AutoSync] supplier#{sid} error: {e}")

        if total_updated:
            elapsed = time.time() - _tick_start
            logger.info(
                f"[AutoSync 30s] {total_updated} products updated | "
                f"price changes: {total_price_changes} | "
                f"stock changes: {total_stock_changes} | "
                f"elapsed: {elapsed:.1f}s"
            )
    finally:
        _AUTOSYNC_PS_RUNNING = False


async def autosync_balance_job(context):
    """
    Runs every 5 minutes.
    Refreshes each supplier's balance_usd and triggers low-balance
    alerts if the balance dropped below its threshold.

    🆕 v89: re-entrancy protected + async adapter wraps.
    """
    global _AUTOSYNC_BAL_RUNNING
    if _AUTOSYNC_BAL_RUNNING:
        logger.warning("[AutoSync-Bal] previous balance tick still running — skipping")
        return
    if not is_autosync_enabled():
        return
    _AUTOSYNC_BAL_RUNNING = True
    try:
        try:
            from ext_suppliers import (
                list_suppliers, get_adapter_for_supplier, update_supplier,
            )
            from async_adapter_helpers import async_fetch_balance
        except Exception as e:
            logger.debug(f"[AutoSync-Bal] import fail: {e}")
            return

        for sup in list_suppliers(include_disabled=False):
            try:
                ad = get_adapter_for_supplier(sup)
                if not ad:
                    continue
                # ASYNC — event loop stays responsive
                bal = await async_fetch_balance(ad)
                if bal is None:
                    continue
                bal_f = float(bal)
                update_supplier(sup["id"],
                                 balance_usd=bal_f,
                                 balance_updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

                # Low balance check
                threshold = float(sup.get("low_bal_threshold") or DEFAULT_LOW_BAL_THRESHOLD)
                if threshold > 0 and bal_f < threshold:
                    await _maybe_send_low_balance_alert(context, sup, bal_f, threshold)
            except Exception as e:
                logger.warning(f"[AutoSync-Bal] sup#{sup['id']} error: {e}")
    finally:
        _AUTOSYNC_BAL_RUNNING = False


# ============================================================
# 2. LOW BALANCE ALERTS
# ============================================================
async def _maybe_send_low_balance_alert(context, sup, current_bal, threshold):
    """Send DM to admin, rate-limited per supplier (6h cooldown)."""
    sid = int(sup["id"])
    key = f"low_bal_alert_last_{sid}"
    try:
        last_str = get_setting(key, "0")
        last = float(last_str or 0)
    except Exception:
        last = 0.0
    now = time.time()
    if now - last < LOW_BAL_ALERT_COOLDOWN:
        return  # already alerted recently
    set_setting(key, str(int(now)))

    name = sup.get("name") or f"Supplier #{sid}"
    text = (
        "⚠️ *LOW BALANCE ALERT*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏪 Supplier: *{name}*\n"
        f"💰 Current balance: `${current_bal:.2f}`\n"
        f"🔻 Threshold: `${threshold:.2f}`\n\n"
        "_Please top up to avoid failed customer orders._"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔧 Open Supplier",
                               callback_data=f"ext_sup_view_{sid}")],
        [InlineKeyboardButton("📊 All Suppliers",
                               callback_data="admin_suppliers")],
    ])
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text,
                                        parse_mode="Markdown", reply_markup=kb)
        logger.info(f"[LowBal] Alert DM sent for supplier#{sid} bal=${current_bal:.2f}")
    except Exception as e:
        logger.warning(f"[LowBal] DM fail: {e}")


# ============================================================
# 3. BULK SYNC — sync ALL products of a supplier in 1 tap
# ============================================================
async def ext_sup_bulk_sync_callback(update, context):
    """
    Callback: ext_sup_bulk_sync_<sid>
    - Re-fetches products from supplier (updates cost/stock)
    - For every ext_product that has synced_to_shop=1, refreshes its
      matching shop row (price + stock + cost)
    - Reports counts
    """
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        sid = int(q.data.replace("ext_sup_bulk_sync_", "", 1))
    except Exception:
        await q.answer("❌ bad id"); return
    await q.answer("⏳ Bulk syncing…")

    try:
        from ext_suppliers import (
            get_ext_products,
            mirror_ext_to_products, get_supplier, _safe_edit, _set_q_data,
            ext_sup_view_callback,
        )
        # 🆕 v89: async wrapper (does the fetch on a thread, DB work stays inline)
        from async_adapter_helpers import async_sync_supplier_products
    except Exception as e:
        await q.answer(f"❌ import err: {e}"[:190], show_alert=True); return

    # 🆕 v94: snapshot old stock BEFORE sync so we can detect increases
    from database import get_connection as _gc
    stock_before = {}   # shop_product_id → old stock
    try:
        _conn = _gc(); _c = _conn.cursor()
        _c.execute("""SELECT ep.shop_product_id, p.stock
                       FROM ext_products ep JOIN products p ON p.id = ep.shop_product_id
                       WHERE ep.supplier_id=? AND ep.synced_to_shop=1
                         AND ep.shop_product_id > 0""", (sid,))
        for r in _c.fetchall():
            stock_before[int(r["shop_product_id"])] = int(r["stock"] or 0)
        _conn.close()
    except Exception as _e:
        logger.debug(f"[BulkSync] stock snapshot fail: {_e}")

    imported, err = await async_sync_supplier_products(sid)
    if err:
        await context.bot.send_message(chat_id=ADMIN_ID,
                                        text=f"❌ Bulk sync failed: {err}")
        return

    # Refresh shop rows for all synced_to_shop products
    prods = get_ext_products(supplier_id=sid)
    live_count = 0
    restock_alerts_fired = 0
    for ep in prods:
        if int(ep.get("synced_to_shop") or 0):
            try:
                mirror_ext_to_products(int(ep["id"]))
                live_count += 1
                # 🆕 v94: fire restock broadcast on stock increase
                shop_pid = int(ep.get("shop_product_id") or 0)
                if shop_pid > 0 and shop_pid in stock_before:
                    # Re-read stock AFTER mirror to get new value
                    try:
                        _c2 = _gc(); _cur = _c2.cursor()
                        _cur.execute("SELECT stock FROM products WHERE id=?", (shop_pid,))
                        _row = _cur.fetchone(); _c2.close()
                        new_stock = int(_row["stock"] or 0) if _row else 0
                        old_stock = stock_before[shop_pid]
                        if new_stock > old_stock:
                            try:
                                from restock_alerts import fire_restock_alert
                                await fire_restock_alert(
                                    context.bot, shop_pid,
                                    new_stock - old_stock, new_stock
                                )
                                restock_alerts_fired += 1
                            except Exception as _rea:
                                logger.debug(f"[BulkSync] restock alert fail: {_rea}")
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"[BulkSync] mirror fail #{ep['id']}: {e}")

    sup = get_supplier(sid)
    name = sup.get("name") if sup else f"#{sid}"
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"✅ *Bulk Sync Complete — {name}*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 Products fetched: *{imported}*\n"
            f"🔄 Live shop rows refreshed: *{live_count}*"
        ),
        parse_mode="Markdown",
    )
    # Refresh the supplier view screen
    try:
        _set_q_data(q, f"ext_sup_view_{sid}")
        await ext_sup_view_callback(update, context)
    except Exception:
        pass


# ============================================================
# 4. LOW-BAL THRESHOLD editor (per supplier)
# ============================================================
# Callback flow:
#   ext_sup_lowbal_<sid>           → prompt for new threshold
#   next text msg (conv state)     → save + confirm
# ============================================================
LOWBAL_EDIT_STATE = 9286

async def ext_sup_lowbal_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return -1
    await q.answer()
    try:
        sid = int(q.data.replace("ext_sup_lowbal_", "", 1))
    except Exception:
        return -1
    context.user_data["_lowbal_sid"] = sid
    from ext_suppliers import get_supplier
    sup = get_supplier(sid)
    if not sup:
        await q.message.reply_text("❌ Supplier not found."); return -1
    cur = float(sup.get("low_bal_threshold") or DEFAULT_LOW_BAL_THRESHOLD)
    await q.message.reply_text(
        f"⚠️ *Set Low-Balance Threshold*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏪 Supplier: *{sup.get('name', sid)}*\n"
        f"Current threshold: `${cur:.2f}`\n\n"
        f"Send a dollar amount (e.g. `2.5`, `10`).\n"
        f"Send `0` to *disable* alerts for this supplier.\n"
        f"/cancel to abort.",
        parse_mode="Markdown")
    return LOWBAL_EDIT_STATE


async def ext_sup_lowbal_received(update, context):
    if update.effective_user.id != ADMIN_ID:
        return -1
    txt = (update.message.text or "").strip().replace("$", "").replace(",", ".")
    try:
        val = float(txt)
        if val < 0:
            raise ValueError("negative")
    except Exception:
        await update.message.reply_text("❌ Invalid amount. Try again or /cancel.")
        return LOWBAL_EDIT_STATE
    sid = int(context.user_data.pop("_lowbal_sid", 0) or 0)
    if not sid:
        await update.message.reply_text("❌ Session lost. Try again."); return -1
    from ext_suppliers import update_supplier
    update_supplier(sid, low_bal_threshold=val)
    # Also reset the alert cooldown so a new alert can fire if still low
    set_setting(f"low_bal_alert_last_{sid}", "0")
    if val == 0:
        msg = f"✅ Low-balance alerts *disabled* for supplier #{sid}."
    else:
        msg = f"✅ Low-balance threshold set to `${val:.2f}` for supplier #{sid}."
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔧 Back to Supplier",
                              callback_data=f"ext_sup_view_{sid}")]])
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
    return -1


async def ext_sup_lowbal_cancel(update, context):
    try:
        await update.message.reply_text("❎ Cancelled.")
    except Exception:
        pass
    context.user_data.pop("_lowbal_sid", None)
    return -1


# ============================================================
# 🆕 v96: SUPPLIER RENAME (admin-only, admin-panel-only label)
# ============================================================
# Renames the ext_suppliers.name field — used purely in admin
# dashboard displays. Does NOT appear in any customer-facing
# broadcast or receipt (per user spec).
# ============================================================
SUP_RENAME_STATE = 9600   # 🐛 v96: was 9287 which collided with insta_api_flow.CONN_STRING_STATE. Now in fresh 9600-range.


async def ext_sup_rename_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return -1
    await q.answer()
    try:
        sid = int(q.data.replace("ext_sup_rename_", "", 1))
    except Exception:
        return -1
    context.user_data["_rename_sid"] = sid
    from ext_suppliers import get_supplier
    sup = get_supplier(sid)
    if not sup:
        await q.message.reply_text("❌ Supplier not found."); return -1
    cur = sup.get("name", "?")
    await q.message.reply_text(
        f"✏️ *Rename Supplier*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Current name: *{cur}*\n\n"
        f"Send the new display name (2–40 characters).\n"
        f"⚠️ Ye sirf admin dashboard mein dikhega — customers ko\n"
        f"    broadcasts ya receipts mein NAHI dikhta.\n\n"
        f"/cancel to abort.",
        parse_mode="Markdown"
    )
    return SUP_RENAME_STATE


async def ext_sup_rename_received(update, context):
    if update.effective_user.id != ADMIN_ID:
        return -1
    new_name = (update.message.text or "").strip()
    if not (2 <= len(new_name) <= 40):
        await update.message.reply_text(
            "❌ Name must be 2–40 characters. Try again or /cancel."
        )
        return SUP_RENAME_STATE
    sid = int(context.user_data.pop("_rename_sid", 0) or 0)
    if not sid:
        await update.message.reply_text("❌ Session lost. Try again."); return -1
    from ext_suppliers import update_supplier, get_supplier
    old = get_supplier(sid)
    old_name = old.get("name", "?") if old else "?"
    update_supplier(sid, name=new_name)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔧 Back to Supplier",
                             callback_data=f"ext_sup_view_{sid}")
    ]])
    await update.message.reply_text(
        f"✅ *Renamed!*\n\n"
        f"Old: {old_name}\n"
        f"New: *{new_name}*",
        parse_mode="Markdown", reply_markup=kb
    )
    return -1


async def ext_sup_rename_cancel(update, context):
    try:
        await update.message.reply_text("❎ Cancelled.")
    except Exception:
        pass
    context.user_data.pop("_rename_sid", None)
    return -1


# ============================================================
# 5. FINANCE DASHBOARD
# ============================================================
def _period_bounds(period: str):
    """Return (start_iso, end_iso, label). Uses SQLite text comparisons."""
    now = datetime.now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.strftime("%Y-%m-%d %H:%M:%S"), \
               now.strftime("%Y-%m-%d %H:%M:%S"), "Today"
    if period == "yesterday":
        y_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        y_start = y_end - timedelta(days=1)
        return y_start.strftime("%Y-%m-%d %H:%M:%S"), \
               y_end.strftime("%Y-%m-%d %H:%M:%S"), "Yesterday"
    if period == "week":
        start = now - timedelta(days=7)
        return start.strftime("%Y-%m-%d %H:%M:%S"), \
               now.strftime("%Y-%m-%d %H:%M:%S"), "Last 7 days"
    if period == "month":
        start = now - timedelta(days=30)
        return start.strftime("%Y-%m-%d %H:%M:%S"), \
               now.strftime("%Y-%m-%d %H:%M:%S"), "Last 30 days"
    if period == "all":
        return "1970-01-01 00:00:00", \
               now.strftime("%Y-%m-%d %H:%M:%S"), "All time"
    # default: today
    return _period_bounds("today")


def _finance_totals(start_iso: str, end_iso: str):
    """
    Returns:
      dict {
        orders_count, revenue, cost_estimate, profit_estimate,
        per_supplier: [{supplier_id, supplier_name, orders, revenue,
                        cost, profit}]
      }
    Only counts delivered orders in [start, end).
    Cost = ext_products.cost_usd × quantity (best available signal).
    Falls back to products.cost_price if the order isn't linked to an ext_product.
    """
    conn = get_connection(); c = conn.cursor()

    # Overall
    c.execute("""
        SELECT COUNT(*) AS n, COALESCE(SUM(price), 0) AS rev
        FROM orders
        WHERE status='delivered'
          AND created_at >= ? AND created_at < ?
    """, (start_iso, end_iso))
    r = c.fetchone()
    n = int(r["n"] or 0)
    rev = float(r["rev"] or 0)

    # Cost estimate via join to ext_products via products.ext_product_id
    # (This works because when we mirror ext_products → products, we set
    #  products.ext_product_id + products.cost_price. Orders link to products
    #  via orders.product_id.)
    c.execute("""
        SELECT COALESCE(SUM(
            CASE WHEN p.cost_price IS NOT NULL AND p.cost_price > 0
                 THEN p.cost_price
                 WHEN ep.cost_usd IS NOT NULL AND ep.cost_usd > 0
                 THEN ep.cost_usd
                 ELSE 0
            END
        ), 0) AS cost_est
        FROM orders o
        LEFT JOIN products p     ON p.id = o.product_id
        LEFT JOIN ext_products ep ON ep.id = p.ext_product_id
        WHERE o.status='delivered'
          AND o.created_at >= ? AND o.created_at < ?
    """, (start_iso, end_iso))
    cost = float((c.fetchone() or {"cost_est": 0})["cost_est"] or 0)
    profit = rev - cost

    # Per-supplier breakdown
    per_sup = []
    try:
        c.execute("""
            SELECT s.id AS sid, s.name AS sname,
                   COUNT(o.id) AS n,
                   COALESCE(SUM(o.price), 0) AS rev,
                   COALESCE(SUM(
                       CASE WHEN p.cost_price IS NOT NULL AND p.cost_price > 0
                            THEN p.cost_price
                            WHEN ep.cost_usd IS NOT NULL AND ep.cost_usd > 0
                            THEN ep.cost_usd
                            ELSE 0
                       END
                   ), 0) AS cost
            FROM orders o
            JOIN products p          ON p.id = o.product_id
            JOIN ext_products ep      ON ep.id = p.ext_product_id
            JOIN ext_suppliers s      ON s.id = ep.supplier_id
            WHERE o.status='delivered'
              AND o.created_at >= ? AND o.created_at < ?
            GROUP BY s.id, s.name
            ORDER BY rev DESC
        """, (start_iso, end_iso))
        for r in c.fetchall():
            rrev = float(r["rev"] or 0); rcost = float(r["cost"] or 0)
            per_sup.append({
                "supplier_id": int(r["sid"]),
                "supplier_name": r["sname"] or "?",
                "orders": int(r["n"] or 0),
                "revenue": rrev,
                "cost": rcost,
                "profit": rrev - rcost,
            })
    except Exception as e:
        logger.debug(f"[Finance] per-sup query failed: {e}")

    # Manual (non-supplier) orders — bucket separately if any
    try:
        c.execute("""
            SELECT COUNT(o.id) AS n,
                   COALESCE(SUM(o.price), 0) AS rev,
                   COALESCE(SUM(COALESCE(p.cost_price, 0)), 0) AS cost
            FROM orders o
            LEFT JOIN products p ON p.id = o.product_id
            WHERE o.status='delivered'
              AND o.created_at >= ? AND o.created_at < ?
              AND (p.ext_product_id IS NULL OR p.ext_product_id = 0)
        """, (start_iso, end_iso))
        mr = c.fetchone()
        mrev = float((mr or {}).get("rev", 0) or 0)
        mcost = float((mr or {}).get("cost", 0) or 0)
        mn = int((mr or {}).get("n", 0) or 0)
        if mn > 0:
            per_sup.append({
                "supplier_id": 0,
                "supplier_name": "🧑 Manual / Non-supplier",
                "orders": mn, "revenue": mrev, "cost": mcost,
                "profit": mrev - mcost,
            })
    except Exception as e:
        logger.debug(f"[Finance] manual bucket fail: {e}")

    conn.close()
    return {
        "orders_count": n,
        "revenue": rev,
        "cost_estimate": cost,
        "profit_estimate": profit,
        "per_supplier": per_sup,
    }


def _build_finance_text(period: str) -> str:
    start_iso, end_iso, label = _period_bounds(period)
    tot = _finance_totals(start_iso, end_iso)

    def _line(sup):
        margin = (sup["profit"] / sup["revenue"] * 100) if sup["revenue"] > 0 else 0
        return (
            f"  • *{sup['supplier_name']}* — "
            f"{sup['orders']} order(s)\n"
            f"     💵 Rev `${sup['revenue']:.2f}`  💸 Cost `${sup['cost']:.2f}`  "
            f"📈 Profit `${sup['profit']:.2f}` ({margin:.0f}%)"
        )

    header = (
        f"💰 *Finance Dashboard*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Period: *{label}*\n\n"
        f"📦 Delivered orders: *{tot['orders_count']}*\n"
        f"💵 Revenue: `${tot['revenue']:.2f}`\n"
        f"💸 Est. cost: `${tot['cost_estimate']:.2f}`\n"
        f"📈 *Est. profit: `${tot['profit_estimate']:.2f}`*"
    )
    if tot["revenue"] > 0:
        margin = tot["profit_estimate"] / tot["revenue"] * 100
        header += f"   ({margin:.0f}% margin)"

    if tot["per_supplier"]:
        header += "\n\n🏪 *Per-Supplier Breakdown*"
        for sup in tot["per_supplier"]:
            header += "\n" + _line(sup)
    else:
        header += "\n\n_No supplier-linked delivered orders in this period._"

    header += ("\n\n_Cost estimate uses `products.cost_price` (mirrored "
               "from `ext_products.cost_usd` at delivery time)._")
    return header


def _build_finance_kb(period: str) -> InlineKeyboardMarkup:
    def _btn(label, key):
        mark = "⦿ " if key == period else ""
        return InlineKeyboardButton(f"{mark}{label}", callback_data=f"fin_p_{key}")
    return InlineKeyboardMarkup([
        [_btn("📆 Today", "today"), _btn("📅 Yesterday", "yesterday")],
        [_btn("🗓️ 7d", "week"), _btn("📊 30d", "month"),
         _btn("🌐 All", "all")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"fin_p_{period}")],
        [InlineKeyboardButton("🔙 Back to Admin Panel",
                               callback_data="admin_panel")],
    ])


async def admin_finance_callback(update, context):
    """🐛 v103 FIX: was crashing with 'Temporary error' when Markdown parsing
    failed or the underlying message was a caption. Now:
      • wraps every step in try/except so admin sees a useful error, not a
        generic 'Temporary error'
      • falls back through Markdown → plain text → send-new-message
      • includes DB error surface so admin knows WHAT is broken
    """
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    try:
        text = _build_finance_text("today")
        kb = _build_finance_kb("today")
    except Exception as e:
        logger.exception("[Finance] _build failed")
        text = (f"💰 *Finance Dashboard*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"⚠️ *Data assembly failed*\n\n"
                f"`{escape_md(str(e)[:200])}`\n\n"
                f"_Tap Refresh or contact developer._")
        kb = _build_finance_kb("today")

    async def _try(mode):
        return await q.edit_message_text(text, parse_mode=mode, reply_markup=kb)

    for mode in ("Markdown", None):
        try:
            await _try(mode)
            return
        except Exception as e:
            emsg = str(e).lower()
            if "not modified" in emsg:
                return  # nothing to update
            logger.debug(f"[Finance] edit_message_text mode={mode} failed: {e}")

    # Caption message — try edit_message_caption
    for mode in ("Markdown", None):
        try:
            await q.edit_message_caption(caption=text, parse_mode=mode, reply_markup=kb)
            return
        except Exception as e:
            logger.debug(f"[Finance] edit_message_caption mode={mode} failed: {e}")

    # Last resort — send NEW message so admin always sees the dashboard
    try:
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        try:
            await q.message.reply_text(text, reply_markup=kb)
        except Exception as e:
            logger.warning(f"[Finance] final reply_text failed: {e}")


async def fin_p_callback(update, context):
    """🐛 v103: hardened same as admin_finance_callback — no more silent
    'Temporary error' on period switches."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("⏳")
    key = (q.data or "").replace("fin_p_", "").strip() or "today"

    try:
        text = _build_finance_text(key)
        kb = _build_finance_kb(key)
    except Exception as e:
        logger.exception("[Finance] period switch _build failed")
        text = (f"💰 *Finance Dashboard*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"⚠️ *Data assembly failed for '{escape_md(key)}'*\n\n"
                f"`{escape_md(str(e)[:200])}`")
        kb = _build_finance_kb(key)

    for mode in ("Markdown", None):
        try:
            await q.edit_message_text(text, parse_mode=mode, reply_markup=kb)
            return
        except Exception as e:
            emsg = str(e).lower()
            if "not modified" in emsg:
                return
            logger.debug(f"[Finance] period {key} edit failed mode={mode}: {e}")

    for mode in ("Markdown", None):
        try:
            await q.edit_message_caption(caption=text, parse_mode=mode, reply_markup=kb)
            return
        except Exception:
            pass

    try:
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        try:
            await q.message.reply_text(text, reply_markup=kb)
        except Exception as e:
            logger.warning(f"[Finance] period {key} final reply failed: {e}")


# ============================================================
# 6. AUTO-SYNC TOGGLE PANEL (small admin control)
# ============================================================
async def admin_autosync_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    on = is_autosync_enabled()
    # count live products
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("""SELECT COUNT(*) AS n FROM ext_products
                      WHERE synced_to_shop=1 AND active=1""")
        live = int((c.fetchone() or {"n": 0})["n"] or 0)
    except Exception:
        live = 0
    conn.close()
    text = (
        "⏰ *Auto-Sync Settings*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Status: {'🟢 ON' if on else '🔴 OFF'}\n"
        f"Live products being synced: *{live}*\n\n"
        f"🔄 Price + Stock refresh: every *{AUTOSYNC_PRICE_STOCK_INTERVAL}s*\n"
        f"💰 Balance + Low-bal alerts: every *{AUTOSYNC_BALANCE_INTERVAL // 60} min*\n\n"
        "_Only products you've explicitly tapped 🔄 Sync-to-Shop are auto-synced. "
        "The rest stay dormant so API calls stay lean._"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            ("🔴 Turn OFF" if on else "🟢 Turn ON"),
            callback_data="autosync_toggle")],
        [InlineKeyboardButton("🔙 Back to Suppliers",
                               callback_data="admin_suppliers")],
    ])
    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def autosync_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    set_autosync(not is_autosync_enabled())
    await q.answer("Toggled ✅")
    await admin_autosync_callback(update, context)
