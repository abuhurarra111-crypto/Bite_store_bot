# ============================================================
# 🧩 v77 BUNDLE: admin_panels.py
# ============================================================
# This file is the merged result of 6 originally separate modules:
#   • handlers_completed_orders.py
#   • handlers_refund_cancel.py
#   • handlers_integrity.py
#   • handlers_admin_api.py
#   • handlers_price_list.py
#   • handlers_analytics.py
#
# 🛡️ ALL CODE IS PRESERVED VERBATIM. Each original file's contents appears
# below in its own section. Imports and behavior are byte-identical to the
# pre-merge codebase — only file count is reduced.
# ============================================================


# ============================================================
# 📄 ORIGINAL FILE: handlers_completed_orders.py
# ============================================================

# ============================================
# ✅ COMPLETED ORDERS PANEL  (v73)
# ============================================
# Admin can browse all finished orders with status filter tabs:
#   • Delivered   (status = 'delivered')
#   • Refunded    (status = 'refunded')
#   • Cancelled   (status = 'cancelled' or 'rejected')
#
# Lists newest first, 25 per page, with user / product / price / date.
# Tap any order row → opens the existing single-order detail (view_order_<id>)
# so admin can re-view delivery content, refund, etc. without duplicating UI.
#
# Replaces the old 🛒 Pending Orders button (removed per user request in v73).
# ============================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_ID
from database import get_connection

logger = logging.getLogger(__name__)

PAGE_SIZE = 25

# Status filter → human label + SQL where clause
_FILTERS = {
    "delivered": {
        "label": "✅ Delivered",
        "where": "status = 'delivered'",
    },
    "refunded": {
        "label": "💸 Refunded",
        "where": "status = 'refunded'",
    },
    "cancelled": {
        "label": "❌ Cancelled",
        "where": "status IN ('cancelled', 'rejected')",
    },
    "all": {
        "label": "📋 All Finished",
        "where": "status IN ('delivered','refunded','cancelled','rejected')",
    },
}


async def _safe_edit(q, text, **kwargs):
    """Edit message, falling back to plain text on Markdown parse error."""
    try:
        await q.edit_message_text(text, **kwargs)
    except Exception as e:
        try:
            # Strip parse_mode and retry
            kwargs.pop("parse_mode", None)
            await q.edit_message_text(text, **kwargs)
        except Exception as e2:
            logger.debug(f"[CompletedOrders] _safe_edit fallback failed: {e2}")
            try:
                await q.message.reply_text(text)
            except Exception:
                pass


def _fetch_orders(filter_key: str, page: int = 0):
    """Pull a page of orders matching the filter. Returns (rows, total_count)."""
    f = _FILTERS.get(filter_key) or _FILTERS["delivered"]
    where = f["where"]
    offset = max(0, int(page)) * PAGE_SIZE
    conn = get_connection()
    c = conn.cursor()
    # Total count
    c.execute(f"SELECT COUNT(*) FROM orders WHERE {where}")
    total = int(c.fetchone()[0] or 0)
    # Page rows
    c.execute(f"""
        SELECT id, user_id, product_name, price, status,
               COALESCE(created_at, '') as created_at,
               COALESCE(payment_method, '') as payment_method
        FROM orders
        WHERE {where}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (PAGE_SIZE, offset))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows, total


def _emoji_for(status: str) -> str:
    return {
        "delivered": "✅",
        "refunded":  "💸",
        "cancelled": "❌",
        "rejected":  "🚫",
    }.get(status, "•")


def _build_keyboard(rows, filter_key: str, page: int, total: int):
    kb = []
    # ── Filter tabs row (current one marked with ⦿) ──
    tabs = []
    for key in ("delivered", "refunded", "cancelled", "all"):
        meta = _FILTERS[key]
        prefix = "⦿ " if key == filter_key else ""
        tabs.append(InlineKeyboardButton(
            f"{prefix}{meta['label']}",
            callback_data=f"admin_completed_filter_{key}_0"
        ))
    # 2 tabs per row for readability
    kb.append(tabs[:2])
    kb.append(tabs[2:])

    # ── Order rows ──
    # 🔧 v78 FIX: strip [[HTML]] sentinel + <tg-emoji> tags from product names
    # so button labels look professional (not raw markup).
    from utils import name_for_button
    for o in rows:
        e = _emoji_for(o["status"])
        raw_name = o.get("product_name") or "Product"
        clean_name = name_for_button(raw_name) or "Product"
        # Trim product name so the row label fits Telegram's button limits
        pname = clean_name[:28]
        price = float(o.get("price") or 0)
        label = f"{e} #{o['id']} • ${price:.2f} • {pname}"
        kb.append([InlineKeyboardButton(label, callback_data=f"view_order_{o['id']}")])

    if not rows:
        kb.append([InlineKeyboardButton("📭 No orders in this category", callback_data="admin_completed")])

    # ── Pagination ──
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Prev",
                callback_data=f"admin_completed_filter_{filter_key}_{page-1}"))
        nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}",
            callback_data="admin_completed"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️ Next",
                callback_data=f"admin_completed_filter_{filter_key}_{page+1}"))
        kb.append(nav)

    kb.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


def _build_text(filter_key: str, total: int) -> str:
    meta = _FILTERS.get(filter_key) or _FILTERS["delivered"]
    return (
        f"✅ *Completed Orders*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 Filter: {meta['label']}\n"
        f"🔢 Total: *{total}* order(s)\n\n"
        f"_Tap any order row to view full details._"
    )


# ───────────────────────────────────────────
# Callbacks
# ───────────────────────────────────────────

async def admin_completed_orders_callback(update, context):
    """Open Completed Orders panel — defaults to 'delivered' filter, page 0."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    rows, total = _fetch_orders("delivered", 0)
    await _safe_edit(q, _build_text("delivered", total),
                     parse_mode="Markdown",
                     reply_markup=_build_keyboard(rows, "delivered", 0, total))


async def admin_completed_filter_callback(update, context):
    """Switch filter / page. Callback format: admin_completed_filter_<key>_<page>"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    data = (q.data or "").replace("admin_completed_filter_", "", 1)
    # data like "delivered_0" / "refunded_2"
    try:
        key, page_str = data.rsplit("_", 1)
        page = int(page_str)
    except Exception:
        key, page = "delivered", 0
    if key not in _FILTERS:
        key = "delivered"
    rows, total = _fetch_orders(key, page)
    await _safe_edit(q, _build_text(key, total),
                     parse_mode="Markdown",
                     reply_markup=_build_keyboard(rows, key, page, total))


# ============================================================
# 📄 ORIGINAL FILE: handlers_refund_cancel.py
# ============================================================

# ============================================================
# 🔄 REFUND + ❌ CANCEL handlers (v65)
# ============================================================
# Admin can refund a paid manual order (credits equivalent points to user)
# or cancel a paid order (optional reason → user sees the reason).
# ============================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID, POINTS_PER_DOLLAR
from database import (
    get_order, update_order_status, add_points, get_user_points,
)
from utils import escape_md, smart_text_and_mode

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# 🔄 REFUND  (admin → confirms → user gets points + message)
# ════════════════════════════════════════════════════════════
async def adm_refund_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        oid = int(q.data.replace("adm_refund_", ""))
    except Exception:
        await q.answer("Invalid order", show_alert=True); return

    o = get_order(oid)
    if not o:
        await q.edit_message_text("❌ Order not found.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]))
        return

    if o["status"] in ("refunded", "cancelled", "rejected"):
        await q.answer(f"Order already {o['status']}.", show_alert=True)
        return

    price = float(o["price"] or 0)
    pts = int(price * POINTS_PER_DOLLAR)
    text = (
        f"🔄 *Refund Order #{oid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Customer: `{o['user_id']}`\n"
        f"📦 Product: *{escape_md(o.get('product_name','') or '?')}*\n"
        f"💰 Amount paid: *${price:.2f}*\n\n"
        f"⚠️ Refund action:\n"
        f"  • Order status → `refunded`\n"
        f"  • Customer will be credited *{pts} Points* "
        f"(equivalent of ${price:.2f})\n"
        f"  • Customer notified via bot\n\n"
        f"Confirm?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm Refund", callback_data=f"adm_refund_confirm_{oid}")],
        [InlineKeyboardButton("❌ Cancel",          callback_data=f"adm_refund_abort_{oid}")],
    ])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def adm_refund_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Processing refund…")
    try:
        oid = int(q.data.replace("adm_refund_confirm_", ""))
    except Exception:
        await q.answer("Invalid order", show_alert=True); return

    o = get_order(oid)
    if not o:
        await q.edit_message_text("❌ Order not found."); return
    if o["status"] in ("refunded", "cancelled", "rejected"):
        await q.answer(f"Already {o['status']}", show_alert=True); return

    price = float(o["price"] or 0)
    pts = int(price * POINTS_PER_DOLLAR)
    user_id = o["user_id"]
    pname = o.get("product_name", "") or "your order"

    update_order_status(oid, "refunded")
    if pts > 0:
        try:
            add_points(user_id, pts)
        except Exception as e:
            logger.warning(f"[Refund] add_points failed for uid={user_id}: {e}")

    new_balance = get_user_points(user_id)

    customer_msg = (
        f"💸 *Refund Processed*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"This product is currently unavailable, "
        f"so your payment is being refunded.\n\n"
        f"📦 Order: `#{oid}`\n"
        f"📌 Product: *{escape_md(pname)}*\n"
        f"💰 Amount: *${price:.2f}*\n\n"
        f"✅ *{pts} Points have been credited* to your wallet "
        f"as an instant refund.\n"
        f"💎 New balance: *{new_balance} Points*\n\n"
        f"You can use these Points to buy other products in the store. "
        f"We apologise for the inconvenience."
    )
    kb_user = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Browse Other Products", callback_data="shop")],
        [InlineKeyboardButton("📜 Order History",         callback_data="my_orders")],
        [InlineKeyboardButton("🏠 Main Menu",             callback_data="main_menu")],
    ])
    send_text, send_mode = smart_text_and_mode(customer_msg, "Markdown")
    try:
        await context.bot.send_message(user_id, send_text,
            parse_mode=send_mode, reply_markup=kb_user)
    except Exception as e:
        logger.warning(f"[Refund] failed to message user {user_id}: {e}")

    admin_msg = (
        f"✅ *Refund Completed*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Order #{oid} refunded.\n"
        f"Customer `{user_id}` credited with *{pts} Points*.\n"
        f"New balance: {new_balance} Points."
    )
    await q.edit_message_text(admin_msg, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Pending Manual Delivery",
                                  callback_data="adm_pending_delivery")],
            [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
        ]))


async def adm_refund_abort_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Refund cancelled.")
    try:
        oid = int(q.data.replace("adm_refund_abort_", ""))
    except Exception:
        oid = 0
    await q.edit_message_text(
        f"❎ Refund cancelled for order #{oid}.\n\nNo changes made.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Pending Manual Delivery",
                                  callback_data="adm_pending_delivery")],
            [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
        ]))


# ════════════════════════════════════════════════════════════
# ❌ CANCEL  (admin → reason / skip → user gets cancellation msg)
# ════════════════════════════════════════════════════════════
async def adm_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        oid = int(q.data.replace("adm_cancel_", ""))
    except Exception:
        await q.answer("Invalid order", show_alert=True); return

    o = get_order(oid)
    if not o:
        await q.edit_message_text("❌ Order not found."); return
    if o["status"] in ("refunded", "cancelled", "rejected"):
        await q.answer(f"Already {o['status']}.", show_alert=True); return

    context.user_data["adm_cancel_oid"] = oid
    context.user_data["adm_cancel_step"] = "waiting_reason"

    text = (
        f"❌ *Cancel Order #{oid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Customer: `{o['user_id']}`\n"
        f"📦 Product: *{escape_md(o.get('product_name','') or '?')}*\n"
        f"💰 Amount: `${float(o.get('price') or 0):.2f}`\n\n"
        f"✍️ Please type a *cancellation reason* in your next message.\n"
        f"_(The customer will see this reason.)_\n\n"
        f"Or tap *Skip* below to cancel without giving a reason."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ Skip (No Reason)", callback_data=f"adm_cancel_skip_{oid}")],
        [InlineKeyboardButton("❎ Abort",            callback_data=f"adm_cancel_abort_{oid}")],
    ])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def adm_cancel_skip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        oid = int(q.data.replace("adm_cancel_skip_", ""))
    except Exception:
        await q.answer("Invalid order", show_alert=True); return
    context.user_data.pop("adm_cancel_oid",  None)
    context.user_data.pop("adm_cancel_step", None)
    await _do_cancel_order(context, q, oid, reason="")


async def adm_cancel_abort_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Cancellation aborted.")
    context.user_data.pop("adm_cancel_oid",  None)
    context.user_data.pop("adm_cancel_step", None)
    try:
        oid = int(q.data.replace("adm_cancel_abort_", ""))
    except Exception:
        oid = 0
    await q.edit_message_text(
        f"❎ Cancellation aborted for order #{oid}.\n\nNo changes made.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Pending Manual Delivery",
                                  callback_data="adm_pending_delivery")],
            [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
        ]))


async def adm_cancel_reason_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive the admin's cancellation reason text."""
    if context.user_data.get("adm_cancel_step") != "waiting_reason":
        return False
    if update.effective_user.id != ADMIN_ID:
        return False

    oid = context.user_data.pop("adm_cancel_oid",  None)
    context.user_data.pop("adm_cancel_step", None)
    reason = (update.message.text or "").strip()[:500]

    if not oid:
        await update.message.reply_text("❌ Order context lost. Please start again.")
        return True

    class _MsgFake:
        async def edit_message_text(self, *a, **kw):
            await update.message.reply_text(*a, **kw)
    await _do_cancel_order(context, _MsgFake(), oid, reason=reason)
    return True


async def _do_cancel_order(context, q_or_msg, oid, reason=""):
    o = get_order(oid)
    if not o:
        try: await q_or_msg.edit_message_text("❌ Order not found.")
        except Exception: pass
        return
    if o["status"] in ("refunded", "cancelled", "rejected"):
        try: await q_or_msg.edit_message_text(f"Order already {o['status']}.")
        except Exception: pass
        return

    user_id = o["user_id"]
    pname = o.get("product_name", "") or "your order"
    price = float(o.get("price") or 0)

    update_order_status(oid, "cancelled")

    if reason:
        customer_msg = (
            f"❌ *Order Cancelled*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 Order: `#{oid}`\n"
            f"📌 Product: *{escape_md(pname)}*\n"
            f"💰 Amount: `${price:.2f}`\n\n"
            f"📋 *Reason from the store:*\n"
            f"_{escape_md(reason)}_\n\n"
            f"If you have already paid, please contact support to "
            f"arrange a refund."
        )
    else:
        customer_msg = (
            f"❌ *Order Cancelled*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 Order: `#{oid}`\n"
            f"📌 Product: *{escape_md(pname)}*\n"
            f"💰 Amount: `${price:.2f}`\n\n"
            f"Your order has been cancelled. "
            f"If you have already paid, please contact support to "
            f"arrange a refund."
        )
    kb_user = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="st_new")],
        [InlineKeyboardButton("🛒 Browse Other Products", callback_data="shop")],
        [InlineKeyboardButton("🏠 Main Menu",             callback_data="main_menu")],
    ])
    send_text, send_mode = smart_text_and_mode(customer_msg, "Markdown")
    try:
        await context.bot.send_message(user_id, send_text,
            parse_mode=send_mode, reply_markup=kb_user)
    except Exception as e:
        logger.warning(f"[Cancel] failed to message user {user_id}: {e}")

    admin_summary = (
        f"✅ *Order Cancelled*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Order #{oid} cancelled.\n"
        f"Customer `{user_id}` notified."
    )
    if reason:
        admin_summary += f"\n\n📋 Reason given:\n_{escape_md(reason)}_"
    else:
        admin_summary += "\n\n_(No reason was given.)_"
    try:
        await q_or_msg.edit_message_text(admin_summary, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Pending Manual Delivery",
                                      callback_data="adm_pending_delivery")],
                [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
            ]))
    except Exception:
        pass


# ============================================================
# 📄 ORIGINAL FILE: handlers_integrity.py
# ============================================================

# ============================================================
# 🛡️ DELIVERY INTEGRITY — admin panel (v72)
# ============================================================
# Admin can view all SHA-256 integrity check events: confirmations
# that stored content == delivered content, and any mismatches.
# ============================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID
from utils import escape_md
from templates_bundle import (
    get_recent_integrity_issues, get_mismatch_count,
    ensure_integrity_table,
)

logger = logging.getLogger(__name__)


async def admin_integrity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show integrity dashboard: counts + recent events."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    ensure_integrity_table()

    mismatches = get_mismatch_count()
    rows = get_recent_integrity_issues(limit=15)
    total = len(rows)
    ok_count = sum(1 for r in rows if r.get('status') == 'ok')

    lines = [
        "🛡️ <b>Delivery Integrity Monitor</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📊 <b>Status:</b>",
        f"  • Total mismatches lifetime: <code>{mismatches}</code>",
        f"  • Recent events shown: <code>{total}</code>",
        f"  • Recent OK / problem ratio: <code>{ok_count}/{total - ok_count}</code>",
        "",
        "<i>Every delivery is verified with a SHA-256 hash check.</i>",
        "<i>Stored bytes must equal delivered bytes (round-trip safe).</i>",
        "",
    ]

    if mismatches > 0:
        lines.append("⚠️ <b>Warning:</b> Mismatches detected. Tap below to view details.")
        lines.append("")

    if rows:
        lines.append("<b>🕓 Last 15 Events:</b>")
        for r in rows[:15]:
            status = r.get('status') or '?'
            stage = r.get('stage') or '?'
            oid = r.get('order_id') or 0
            pid = r.get('product_id') or 0
            slen = r.get('stored_len') or 0
            clen = r.get('computed_len') or 0
            ts = (r.get('created_at') or '')[5:16]

            if status == 'ok':
                icon = "✅"
            elif status == 'mismatch':
                icon = "⚠️"
            elif status == 'blocked':
                icon = "🛑"
            else:
                icon = "❓"
            extra = ""
            if status != 'ok':
                extra = f" <code>{slen}→{clen}b</code>"
            lines.append(
                f"  {icon} <code>{ts}</code> "
                f"<code>{stage}</code> "
                f"#order:{oid} #pid:{pid}{extra}"
            )
    else:
        lines.append("_No events recorded yet — system is healthy._")

    text = "\n".join(lines)[:3900]

    kb = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_integrity")],
        [InlineKeyboardButton("📜 View Mismatches Only", callback_data="admin_integrity_bad")],
        [InlineKeyboardButton("🔙 Back to Settings",     callback_data="admin_settings")],
    ]
    try:
        await q.edit_message_text(text, parse_mode="HTML",
                                   reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        await q.edit_message_text(text[:3900], reply_markup=InlineKeyboardMarkup(kb))


async def admin_integrity_bad_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show only mismatch/blocked events."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    ensure_integrity_table()

    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("""
            SELECT order_id, product_id, stage, status,
                   stored_len, computed_len, detail, created_at
            FROM delivery_integrity_log
            WHERE status IN ('mismatch', 'blocked')
            ORDER BY id DESC LIMIT 30
        """)
        rows = c.fetchall()
        conn.close()
    except Exception:
        rows = []

    if not rows:
        text = (
            "🛡️ <b>Integrity — Mismatches</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎉 <b>Zero mismatches.</b> Every delivery has passed integrity check.\n\n"
            "<i>The byte-perfect storage system is working as designed.</i>"
        )
    else:
        lines = [
            "🛡️ <b>Integrity Mismatches — Recent 30</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for r in rows[:30]:
            d = dict(r)
            icon = "🛑" if d['status'] == 'blocked' else "⚠️"
            lines.append(
                f"{icon} #order:{d['order_id']} pid:{d['product_id']} "
                f"<code>{d['stage']}</code>"
            )
            lines.append(
                f"   <code>{d['created_at']}</code> "
                f"len <code>{d['stored_len']}→{d['computed_len']}</code>"
            )
            if d.get('detail'):
                lines.append(f"   <i>{escape_md(str(d['detail'])[:80])}</i>")
            lines.append("")
        text = "\n".join(lines)[:3900]

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh",            callback_data="admin_integrity_bad")],
        [InlineKeyboardButton("🔙 Back to Dashboard",  callback_data="admin_integrity")],
    ])
    try:
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await q.edit_message_text(text[:3900], reply_markup=kb)


# ============================================================
# 📄 ORIGINAL FILE: handlers_admin_api.py
# ============================================================

"""
🆕 v46: API Management UI in Admin Panel
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import secrets
from database import (
    add_api_key, list_api_keys, revoke_api_key,
    add_external_api, list_external_apis, get_external_api
)
from keyboards import _btn
from config import ADMIN_ID


# --- Local API key helpers (kept here so the bot does NOT require fastapi/uvicorn,
#     which are only needed by the optional standalone API server in api.py) ---
def create_new_api_key(bot_name: str, owner_id: int):
    # Cryptographically secure token; not predictable from time/admin id.
    key = secrets.token_urlsafe(32)
    add_api_key(key, bot_name, owner_id)
    return key


def get_my_api_keys(owner_id: int):
    return list_api_keys(owner_id)

async def api_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Generate New API Key", callback_data="api_gen_key")],
        [InlineKeyboardButton("📋 My API Keys", callback_data="api_list_keys")],
        [InlineKeyboardButton("➕ Add External API (Sell Other Bots)", callback_data="api_add_external")],
        [InlineKeyboardButton("📡 View External APIs", callback_data="api_list_external")],
        [_btn("🔙", "🔙 Back", "🔙 Back", "🔙 Back to Admin", callback_data="admin_panel")]
    ])
    await q.edit_message_text("🔗 *API Management Panel*\n\nManage affiliate API keys and external bot integrations.",
                              parse_mode="Markdown", reply_markup=kb)


async def api_generate_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return

    # Generate key
    key = create_new_api_key("MyAffiliateBot", q.from_user.id)

    text = f"✅ **New API Key Generated!**\n\n`{key}`\n\nShare this key with trusted affiliate bots.\n\n⚠️ Keep it secret!"
    await q.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup([[_btn("🔙", "🔙 Back", "🔙 Back", "🔙 Back", callback_data="api_panel")]]))


async def api_list_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return

    keys = get_my_api_keys(q.from_user.id)
    if not keys:
        text = "No API keys yet."
    else:
        text = "🔑 **Your API Keys:**\n\n"
        for k in keys:
            status = "🟢 Active" if k['is_active'] else "🔴 Revoked"
            text += f"• `{k['api_key'][:12]}...` — {k['bot_name']} ({status})\n"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Revoke Last Key", callback_data="api_revoke_last")],
        [_btn("🔙", "🔙 Back", "🔙 Back", "🔙 Back", callback_data="api_panel")]
    ])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def api_revoke_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return

    keys = get_my_api_keys(q.from_user.id)
    active = [k for k in keys if k['is_active']]
    if active:
        revoke_api_key(active[-1]['id'])
        await q.answer("✅ Last active key revoked", show_alert=True)
    else:
        await q.answer("No active keys to revoke", show_alert=True)
    # Refresh the list
    await api_list_keys(update, context)


async def api_add_external(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return

    context.user_data['api_adding_external'] = True
    await q.edit_message_text("Send in this format:\n\n`BotName|API_KEY|https://example.com|10`\n\n(Commission % optional, default 10)",
                              parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup([[_btn("❌", "Cancel", "❌ Cancel", "❌ Cancel", callback_data="api_panel")]]))


# This handler will be connected in bot.py for text messages when in adding mode
async def api_save_external(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('api_adding_external'):
        return False

    text = update.message.text.strip()
    try:
        parts = text.split('|')
        name = parts[0].strip()
        key = parts[1].strip()
        url = parts[2].strip()
        comm = float(parts[3]) if len(parts) > 3 else 10.0

        add_external_api(name, key, url, comm)
        await update.message.reply_text("✅ External API added successfully!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

    context.user_data['api_adding_external'] = False
    return True


async def api_list_external(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return

    apis = list_external_apis()
    if not apis:
        text = "No external APIs configured."
    else:
        text = "📡 **External APIs (You sell their products):**\n\n"
        for a in apis:
            text += f"• {a['name']} — {a['base_url']} (Comm: {a['commission_percent']}%)\n"

    await q.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup([[_btn("🔙", "🔙 Back", "🔙 Back", "🔙 Back", callback_data="api_panel")]]))


# ============================================================
# 📄 ORIGINAL FILE: handlers_price_list.py
# ============================================================

# ============================================================
# 📊 PRICE LIST screen (v69)
# ============================================================
# Plain list of all products with prices + sort by All/Available/OOS.
# Reachable from Main Menu (or wherever admin places the button).
# ============================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import get_products_filtered, get_setting
from utils import escape_md, smart_text_and_mode, name_for_message_html
from config import USD_TO_PKR_RATE

logger = logging.getLogger(__name__)


def _pkr_rate():
    try:
        return float(get_setting("usd_pkr_rate", USD_TO_PKR_RATE) or USD_TO_PKR_RATE)
    except Exception:
        return float(USD_TO_PKR_RATE)


async def price_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show 📊 Price List screen with sort buttons."""
    q = update.callback_query
    await q.answer()

    # Parse filter mode from callback (price_list OR price_list_<mode>)
    mode = "all"
    if q.data and q.data.startswith("price_list_"):
        candidate = q.data.replace("price_list_", "")
        if candidate in ("all", "available", "unavailable"):
            mode = candidate

    try:
        products = get_products_filtered(mode)
    except Exception as e:
        logger.warning(f"[PriceList] fetch failed: {e}")
        products = []

    mode_label = {
        "all":         "📋 All Products",
        "available":   "✅ Available Only",
        "unavailable": "❌ Out of Stock",
    }[mode]

    lines = [
        "📊 *Price List*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"*Showing:* {mode_label}  ({len(products)})",
        "",
    ]

    if not products:
        if mode == "available":
            lines.append("😔 No products currently available. Check back soon!")
        elif mode == "unavailable":
            lines.append("✅ Everything is in stock — no out-of-stock items!")
        else:
            lines.append("📭 No products in the store yet.")
    else:
        rate = _pkr_rate()
        for i, p in enumerate(products, 1):
            try:
                raw_name = p['name'] or 'Product'
                # Strip [[HTML]] sentinel and tags for plain text display
                clean = name_for_message_html(raw_name) or raw_name
                import re as _re
                clean = _re.sub(r'<[^>]+>', '', clean)
                # Limit name length for clean display
                clean = clean[:50]

                price = float(p['price'] or 0)
                stock = int(p['stock'] or 0)
                stock_icon = "✅" if stock > 0 else "❌"
                pkr = price * rate

                lines.append(
                    f"`{i:>2}.` {stock_icon} *{escape_md(clean)}*"
                )
                lines.append(
                    f"      💰 *${price:.2f}*  ≈  Rs. *{pkr:,.0f}*  "
                    f"📦 Stock: *{stock}*"
                )
            except Exception:
                continue

        lines.append("")
        lines.append("_Tap a sort button below to filter, or 🛒 *Shop* to buy._")

    # Build keyboard — sort buttons + bottom nav
    def _btn(label, callback, active=False):
        prefix = "• " if active else ""
        return InlineKeyboardButton(prefix + label, callback_data=callback)

    kb = [
        [
            _btn("📋 All",          "price_list_all",          active=(mode == "all")),
            _btn("✅ Available",    "price_list_available",    active=(mode == "available")),
            _btn("❌ Out of Stock", "price_list_unavailable",  active=(mode == "unavailable")),
        ],
        [
            InlineKeyboardButton("🛒 Open Shop", callback_data="shop"),
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu"),
        ],
    ]

    text = "\n".join(lines)[:3900]
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    try:
        await q.edit_message_text(send_text, parse_mode=send_mode,
                                  reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        # Fallback for parse errors — plain text
        try:
            await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        except Exception:
            pass


# ============================================================
# 📄 ORIGINAL FILE: handlers_analytics.py
# ============================================================

# ============================================
# 📊 ANALYTICS DASHBOARD HANDLERS
# ============================================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_ID, USD_TO_PKR_RATE
from database import (
    analytics_summary, analytics_top_products, analytics_top_customers,
    analytics_payment_breakdown, analytics_daily_revenue, get_setting,
    get_user_count
)
from utils import escape_md, format_pkr


PERIODS = [
    ("today",  1,    "📅 Today"),
    ("week",   7,    "📆 Last 7 Days"),
    ("month",  30,   "🗓️ Last 30 Days"),
    ("all",    None, "♾️ All Time"),
]


async def _safe_edit(q, text, **kwargs):
    # 1. Try editing as a regular text message
    try:
        await q.edit_message_text(text, **kwargs)
        return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in kwargs:
            kwargs_no_md = dict(kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.edit_message_text(text, **kwargs_no_md)
                return
            except Exception: pass

    # 2. Fallback: edit caption (works on photo/video messages)
    try:
        await q.edit_message_caption(caption=text, **kwargs)
        return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in kwargs:
            kwargs_no_md = dict(kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.edit_message_caption(caption=text, **kwargs_no_md)
                return
            except Exception: pass

    # 3. Last resort: reply_text
    try:
        await q.message.reply_text(text, **kwargs)
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in kwargs:
            kwargs_no_md = dict(kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.message.reply_text(text, **kwargs_no_md)
            except Exception: pass

def _period_keyboard(active="week"):
    rows = []
    row = []
    for key, days, label in PERIODS:
        marker = "✅ " if key == active else ""
        row.append(InlineKeyboardButton(f"{marker}{label}", callback_data=f"an_p_{key}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton("🏆 Top Products", callback_data=f"an_top_prod_{active}"),
        InlineKeyboardButton("👑 Top Customers", callback_data=f"an_top_cust_{active}"),
    ])
    rows.append([
        InlineKeyboardButton("💳 Payment Methods", callback_data=f"an_pay_{active}"),
        InlineKeyboardButton("📈 Daily Chart", callback_data=f"an_chart_{active}"),
    ])
    rows.append([InlineKeyboardButton("🔙 Return", callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)


def _format_summary(stats, period_label, rate):
    rev_usd = stats['revenue']
    rev_pkr = format_pkr(rev_usd, rate)
    lines = [
        "📊 *Analytics Dashboard*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"_Period: {period_label}_",
        "",
        f"💰 *Revenue:* ${rev_usd:.2f}  _({rev_pkr})_",
        f"✅ *Delivered Orders:* {stats['delivered']}",
        f"📦 *Total Orders:* {stats['total_orders']}",
        f"⏳ *Pending:* {stats['pending']}",
        f"👥 *New Users:* {stats['new_users']}",
        f"💵 *Avg Order Value:* ${stats['avg_order']:.2f}",
        f"📈 *Conversion Rate:* {stats['conversion']:.1f}%",
    ]
    return "\n".join(lines)


# ════════════════════════════════════════════
# MAIN HANDLER
# ════════════════════════════════════════════

async def analytics_callback(update, context):
    """Main analytics view — default to 7 days."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    period = "week"; days = 7; label = "📆 Last 7 Days"
    rate = float(get_setting("usd_to_pkr", USD_TO_PKR_RATE) or USD_TO_PKR_RATE)

    stats = analytics_summary(days=days)
    text = _format_summary(stats, label, rate)
    text += f"\n\n👥 *Total Users in System:* {get_user_count()}"

    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=_period_keyboard(active=period))


async def analytics_period_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    # Format: an_p_<key>
    period = q.data.split("_")[-1]
    match = next((p for p in PERIODS if p[0] == period), PERIODS[1])
    _, days, label = match
    rate = float(get_setting("usd_to_pkr", USD_TO_PKR_RATE) or USD_TO_PKR_RATE)

    stats = analytics_summary(days=days)
    text = _format_summary(stats, label, rate)
    text += f"\n\n👥 *Total Users in System:* {get_user_count()}"

    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=_period_keyboard(active=period))


async def analytics_top_products_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    period = q.data.split("_")[-1]
    match = next((p for p in PERIODS if p[0] == period), PERIODS[1])
    _, days, label = match

    top = analytics_top_products(days=days, limit=10)
    lines = [f"🏆 *Top Products* — {label}", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not top:
        lines.append("📭 No delivered orders yet")
    else:
        medals = ["🥇", "🥈", "🥉"] + ["▫️"] * 20
        for i, row in enumerate(top):
            name = escape_md((row['product_name'] or '?')[:30])
            lines.append(f"{medals[i]} *{name}* — {row['cnt']} sold (${row['rev']:.2f})")

    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=_period_keyboard(active=period))


async def analytics_top_customers_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    period = q.data.split("_")[-1]
    match = next((p for p in PERIODS if p[0] == period), PERIODS[1])
    _, days, label = match

    top = analytics_top_customers(days=days, limit=10)
    lines = [f"👑 *Top Customers* — {label}", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not top:
        lines.append("📭 No customers yet")
    else:
        medals = ["🥇", "🥈", "🥉"] + ["▫️"] * 20
        for i, row in enumerate(top):
            name = escape_md((row['first_name'] or 'N/A')[:20])
            lines.append(f"{medals[i]} *{name}* (`{row['user_id']}`)\n"
                         f"     {row['cnt']} orders • *${row['spent']:.2f}*")

    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=_period_keyboard(active=period))


async def analytics_payment_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    period = q.data.split("_")[-1]
    match = next((p for p in PERIODS if p[0] == period), PERIODS[1])
    _, days, label = match

    breakdown = analytics_payment_breakdown(days=days)
    lines = [f"💳 *Payment Methods* — {label}", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not breakdown:
        lines.append("📭 No payments yet")
    else:
        total_rev = sum(r['rev'] for r in breakdown) or 1
        icons = {"binance": "🔶", "easypaisa": "📱", "jazzcash": "📞", "points": "💎", "manual": "✋"}
        for row in breakdown:
            pm = row['payment_method'] or 'manual'
            icon = icons.get(pm.lower(), "💳")
            pct = (row['rev'] / total_rev * 100) if total_rev else 0
            bar = "▰" * int(pct / 10) + "▱" * (10 - int(pct / 10))
            lines.append(f"{icon} *{pm.title()}* — {row['cnt']} orders (${row['rev']:.2f})\n"
                         f"   {bar} {pct:.0f}%")

    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=_period_keyboard(active=period))


async def analytics_chart_callback(update, context):
    """ASCII bar chart of daily revenue."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    period = q.data.split("_")[-1]
    match = next((p for p in PERIODS if p[0] == period), PERIODS[1])
    _, days, label = match

    chart_days = days if days and days <= 30 else 7
    data = analytics_daily_revenue(days=chart_days)

    lines = [f"📈 *Daily Revenue Chart* — Last {chart_days} days", "━━━━━━━━━━━━━━━━━━━━", "```"]
    if not data:
        lines.append("No data yet")
    else:
        max_rev = max((d[1] for d in data), default=1) or 1
        for d, rev, cnt in data:
            bar_len = int((rev / max_rev) * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(f"{d[5:]} │{bar}│ ${rev:>6.2f} ({cnt})")
    lines.append("```")

    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=_period_keyboard(active=period))



# ────────────────────────────────────────────────────────────
# 🆕 v80: PAYMENT METHODS ENABLE/DISABLE ADMIN PANEL
# ────────────────────────────────────────────────────────────
import logging as _pay_log
_pay_logger = _pay_log.getLogger(__name__)


async def admin_payment_toggle_callback(update, context):
    """💳 Payment Methods Toggle — enable/disable each method + edit unavailable msg."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    from database import get_all_payment_states
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    states = get_all_payment_states()
    lines = [
        "💳 *Payment Methods — Enable / Disable*",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "Tap 🟢/🔴 to toggle. Disabled methods are HIDDEN from customer's",
        "checkout screen. Tap ✏️ to edit the 'unavailable' message.",
        "",
    ]
    kb = []
    for st in states:
        icon = "🟢" if st["enabled"] else "🔴"
        status_text = "ENABLED" if st["enabled"] else "DISABLED"
        lines.append(f"{icon} *{st['label']}* — {status_text}")
        kb.append([
            InlineKeyboardButton(f"{icon} {st['label']}",
                                 callback_data=f"admin_pay_toggle_{st['method']}"),
            InlineKeyboardButton("✏️ Message",
                                 callback_data=f"admin_pay_msg_{st['method']}"),
        ])
    kb.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")])
    text = "\n".join(lines)
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def admin_payment_toggle_action_callback(update, context):
    """Toggle a payment method on/off."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    method = (q.data or "").replace("admin_pay_toggle_", "", 1)
    from database import is_payment_enabled, set_payment_enabled, PAYMENT_METHODS
    if method not in PAYMENT_METHODS:
        await q.answer("⚠️ Unknown method", show_alert=True); return
    now_enabled = is_payment_enabled(method)
    new_state = not now_enabled
    set_payment_enabled(method, new_state)
    icon = "🟢 ENABLED" if new_state else "🔴 DISABLED"
    await q.answer(f"{PAYMENT_METHODS[method]['label']} → {icon}", show_alert=True)
    # Refresh panel
    await admin_payment_toggle_callback(update, context)


async def admin_payment_msg_start_callback(update, context):
    """Admin taps ✏️ Message — asks for new unavailable message text."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    method = (q.data or "").replace("admin_pay_msg_", "", 1)
    from database import PAYMENT_METHODS, get_payment_disable_msg
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    if method not in PAYMENT_METHODS:
        return
    current = get_payment_disable_msg(method)
    context.user_data["admin_pay_msg_editing"] = method
    text = (
        f"✏️ *Edit Unavailable Message*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Method: *{PAYMENT_METHODS[method]['label']}*\n\n"
        f"*Current message:*\n"
        f"{current}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Send the *new message text* in your next reply.\n"
        f"Max 2000 characters. Send /cancel to abort."
    )
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup([[
                         InlineKeyboardButton("❌ Cancel", callback_data="admin_pay_toggle")
                     ]]))


async def admin_payment_msg_received(update, context):
    """Save admin's new unavailable message. Called from bot.py handle_text."""
    method = context.user_data.get("admin_pay_msg_editing")
    if not method:
        return False
    if update.effective_user.id != ADMIN_ID:
        return False
    new_msg = (update.message.text or "").strip()
    if len(new_msg) < 5:
        await update.message.reply_text("⚠️ Message too short (min 5 chars). Try again.")
        return True
    from database import set_payment_disable_msg, PAYMENT_METHODS
    set_payment_disable_msg(method, new_msg)
    context.user_data.pop("admin_pay_msg_editing", None)
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    await update.message.reply_text(
        f"✅ *Message saved for {PAYMENT_METHODS[method]['label']}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Payment Toggle", callback_data="admin_pay_toggle")
        ]]))
    return True
