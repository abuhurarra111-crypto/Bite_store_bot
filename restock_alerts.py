# ============================================================
# 🔔 v94: AUTO RESTOCK ALERTS
# ============================================================
# When a supplier product's stock INCREASES and the product is
# synced-to-shop (ext_products.synced_to_shop=1), automatically
# fires a `bc_stock` broadcast to the configured fake activity
# destination (bot / group / both).
#
# Respects existing infrastructure:
#   - Uses `broadcast_store_message()` from fake_engagement.py
#   - Uses `bc_stock` template variants from customization.py
#   - Respects `fbc_type_stock` toggle from fake broadcast panel
#     (if admin turned OFF stock alerts, nothing fires)
#   - Uses per-template button ("bc_stock" template) so the button
#     color + premium emoji admin set for stock template renders
#
# Trigger points (called by v94 patches):
#   1. supplier_automation.autosync_price_stock_job — auto-sync every 30s
#   2. supplier_automation.ext_sup_bulk_sync_callback — manual bulk sync
#   3. ext_suppliers.sync_supplier_products — on-demand import
# ============================================================

import asyncio
import logging

logger = logging.getLogger(__name__)


def _is_stock_broadcast_enabled() -> bool:
    """Check if admin has fake broadcasts ON + stock type ON.

    🐛 v96 FIX: was checking the OLD fake_engagement panel settings
    (fbc_enabled / fbc_type_stock) but admin actually uses the current
    Per-User Fake Activity panel (pua_global_enabled / pua_type_stock).
    Result: restock alerts NEVER fired because fbc_enabled defaulted to '0'.
    Now checks BOTH panels (either being ON is enough) — backward compatible.
    """
    try:
        # 🆕 v96 primary: Per-User Fake Activity (current panel)
        from per_user_activity import is_globally_enabled, is_type_on
        if is_globally_enabled() and is_type_on("stock"):
            return True
    except Exception:
        pass
    try:
        # Legacy: old FBC panel
        from fake_engagement import is_enabled, is_type_enabled
        if is_enabled() and is_type_enabled("stock"):
            return True
    except Exception:
        pass
    return False


def _get_shop_product_price(shop_pid: int) -> float:
    """Fetch current shop-price of a mirrored product for display."""
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT price FROM products WHERE id=?", (int(shop_pid),))
        row = c.fetchone(); conn.close()
        return float(row["price"] or 0) if row else 0.0
    except Exception:
        return 0.0


def _get_shop_product_name(shop_pid: int) -> str:
    """Fetch shop-display name (with premium emoji HTML preserved)."""
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT name FROM products WHERE id=?", (int(shop_pid),))
        row = c.fetchone(); conn.close()
        return (row["name"] or "").strip() if row else ""
    except Exception:
        return ""


async def fire_restock_alert(bot, shop_pid: int, added: int, new_stock: int):
    """
    Send an auto-restock broadcast for shop product `shop_pid`.

    Args:
        bot: PTB Bot instance
        shop_pid: products.id (the shop-mirror row)
        added: how many units were added (new_stock - old_stock)
        new_stock: total stock now

    Returns:
        int: number of destinations broadcast to (0 if skipped/disabled)
    """
    if shop_pid <= 0 or added <= 0:
        return 0

    # 🆕 v96: maintenance mode gate
    try:
        from maintenance_mode import is_maintenance_on
        if is_maintenance_on():
            logger.info(f"[restock_alert] SKIP pid={shop_pid} — maintenance ON")
            return 0
    except Exception:
        pass

    if not _is_stock_broadcast_enabled():
        logger.debug(f"[restock_alert] SKIP pid={shop_pid} — stock broadcasts disabled")
        return 0

    name = _get_shop_product_name(shop_pid)
    if not name:
        return 0

    price = _get_shop_product_price(shop_pid)

    # Render the template — supports admin's chosen variant (bc_stock 1..10)
    try:
        from customization import render_template
        msg = render_template("bc_stock", {
            "product": name,
            "added": str(added),
            "stock": str(new_stock),
            "price": f"{price:.2f}",
        })
    except Exception:
        msg = None

    # Safe fallback if template render fails
    if not msg:
        msg = (
            f"🔔 New stock available!\n\n"
            f"🏪 Product: {name}\n"
            f"➕ Added: {added}\n"
            f"📦 Current stock: {new_stock}\n"
            f"💰 Price: ${price:.2f}\n\n"
            f"🛒 Buy now before it sells out!"
        )

    # Delegate to the well-tested broadcast engine (handles per-template
    # button, color, premium emoji, dest routing, and the v94 "product-name
    # prefix" on the Buy Now button — see fake_engagement patch)
    try:
        from fake_engagement import broadcast_store_message
        sent = await broadcast_store_message(
            bot, msg, pid=shop_pid, tpl_id="bc_stock"
        )
        logger.info(f"[restock_alert] fired for pid={shop_pid} "
                    f"added={added} stock={new_stock} → {sent} destinations")
        return sent
    except Exception as e:
        logger.warning(f"[restock_alert] broadcast failed for pid={shop_pid}: {e}")
        return 0


def fire_restock_alert_sync(shop_pid: int, added: int, new_stock: int):
    """
    Sync wrapper — schedules the async broadcast on the running event loop.
    Used from `sync_supplier_products` which is called from sync contexts.
    Safe no-op if no event loop is running.
    """
    if shop_pid <= 0 or added <= 0:
        return
    try:
        # Get the running loop; if none, we're in a test/CLI context and skip.
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if not loop.is_running():
            # Not inside async — call from a fresh loop
            # (rare — most callers ARE inside PTB's loop)
            return
        # Need the bot instance — grab from PTB Application singleton if available
        from telegram.ext import Application
        try:
            # PTB stores the current app in a WeakSet — best-effort access
            import telegram.ext._application as _app_module
            for app in getattr(_app_module, "_APPLICATIONS", []):
                if app.bot:
                    asyncio.ensure_future(
                        fire_restock_alert(app.bot, shop_pid, added, new_stock),
                        loop=loop
                    )
                    return
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"[restock_alert_sync] skipped: {e}")


# ============================================================
# HELPER: called from patched code to detect stock changes
# ============================================================
def get_shop_pid_for_ext(ext_product_id: int) -> int:
    """Given an ext_products.id, return its linked shop products.id
    if the row has synced_to_shop=1. Returns 0 if not synced."""
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("""SELECT shop_product_id FROM ext_products
                     WHERE id=? AND synced_to_shop=1""", (int(ext_product_id),))
        row = c.fetchone(); conn.close()
        return int(row["shop_product_id"]) if row and row["shop_product_id"] else 0
    except Exception:
        return 0
