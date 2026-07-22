# ============================================================
# 🧩 v77 BUNDLE: support_replacement.py
# ============================================================
# This file is the merged result of 5 originally separate modules:
#   • ticket_chat.py
#   • replacement_system.py
#   • handlers_replacement.py
#   • handlers_replacement_history.py
#   • review_reminder.py
#
# 🛡️ ALL CODE IS PRESERVED VERBATIM. Each original file's contents appears
# below in its own section. Imports and behavior are byte-identical to the
# pre-merge codebase — only file count is reduced.
# ============================================================


# ============================================================
# 📄 ORIGINAL FILE: ticket_chat.py
# ============================================================

# ============================================
# 🎫 TICKET CHAT (two-way media)  (v73)
# ============================================
# Persists every message exchanged between user and admin on a support ticket
# along with optional media (photo / video / document).
#
# Both sides can send photos + videos (with caption) which are auto-forwarded
# to the other party AND stored in `ticket_messages` for later replay.
# ============================================

import logging
from datetime import datetime
from database import get_connection, ensure_column

logger = logging.getLogger(__name__)


def ensure_ticket_messages_table():
    """Create the ticket_messages table if it doesn't exist (additive only)."""
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS ticket_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id   INTEGER NOT NULL,
            sender      TEXT    NOT NULL,        -- 'user' | 'admin'
            sender_id   INTEGER NOT NULL,
            text        TEXT    DEFAULT '',
            media_type  TEXT    DEFAULT '',      -- 'photo' | 'video' | 'document' | ''
            media_id    TEXT    DEFAULT '',      -- Telegram file_id
            created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
        )""")
        # Helpful index for per-ticket history queries
        c.execute("CREATE INDEX IF NOT EXISTS idx_ticket_msgs_tid "
                  "ON ticket_messages(ticket_id)")
        conn.commit(); conn.close()
    except Exception as e:
        logger.warning(f"[TicketChat] ensure table failed: {e}")


def add_ticket_message(ticket_id: int, sender: str, sender_id: int,
                       text: str = "", media_type: str = "",
                       media_id: str = ""):
    """Save one chat message. `sender` must be 'user' or 'admin'."""
    ensure_ticket_messages_table()
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("""INSERT INTO ticket_messages
                     (ticket_id, sender, sender_id, text, media_type, media_id, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (int(ticket_id), str(sender)[:10], int(sender_id),
                   str(text or "")[:4000], str(media_type or "")[:20],
                   str(media_id or "")[:200],
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit(); conn.close()
        return True
    except Exception as e:
        logger.warning(f"[TicketChat] add msg failed: {e}")
        return False


def get_ticket_messages(ticket_id: int, limit: int = 100):
    """Return chronological list of messages for a ticket."""
    ensure_ticket_messages_table()
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("""SELECT * FROM ticket_messages
                     WHERE ticket_id=? ORDER BY id ASC LIMIT ?""",
                  (int(ticket_id), int(limit)))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.warning(f"[TicketChat] get msgs failed: {e}")
        return []


def get_ticket_message_count(ticket_id: int) -> int:
    ensure_ticket_messages_table()
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM ticket_messages WHERE ticket_id=?",
                  (int(ticket_id),))
        n = int(c.fetchone()[0] or 0)
        conn.close()
        return n
    except Exception:
        return 0


def extract_media(message):
    """Inspect a Telegram Message object → (media_type, file_id, caption_text).

    Returns ('', '', '') if no supported media is attached.
    Supported: photo, video, document.
    """
    if not message:
        return ("", "", "")
    caption = (message.caption or "").strip() if hasattr(message, "caption") else ""
    # Photos: take the largest size
    if getattr(message, "photo", None):
        try:
            largest = message.photo[-1]
            return ("photo", largest.file_id, caption)
        except Exception:
            pass
    if getattr(message, "video", None):
        try:
            return ("video", message.video.file_id, caption)
        except Exception:
            pass
    if getattr(message, "document", None):
        try:
            return ("document", message.document.file_id, caption)
        except Exception:
            pass
    return ("", "", "")


async def relay_media_to(bot, chat_id: int, media_type: str,
                          media_id: str, caption: str = ""):
    """Forward stored media (by file_id) to another chat. Returns sent Message or None."""
    try:
        if media_type == "photo":
            return await bot.send_photo(chat_id, photo=media_id, caption=caption or None)
        if media_type == "video":
            return await bot.send_video(chat_id, video=media_id, caption=caption or None)
        if media_type == "document":
            return await bot.send_document(chat_id, document=media_id, caption=caption or None)
    except Exception as e:
        logger.warning(f"[TicketChat] relay_media failed: {e}")
    return None


# ============================================================
# 📄 ORIGINAL FILE: replacement_system.py
# ============================================================

# ============================================================
# 🔁 PRODUCT REPLACEMENT SYSTEM (v71)
# ============================================================
# Per-product setting: how many hours after delivery the customer can
# request a free replacement (e.g. login failed, account banned).
#
# Flow:
#   1. User opens Order History → order detail
#   2. If within window AND not yet replaced → "🔁 Report Issue" button
#   3. User picks reason → admin DM with [✅ Approve] [❌ Reject]
#   4. Approve → bot dispenses new account from product_accounts pool
#   5. Reject → admin can optionally type reason → user gets msg
# ============================================================

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_HOURS = 24


def _ensure_columns():
    """Add replacement_window_hours to products, replacement_requested + replacement_count to orders."""
    try:
        from database import get_connection, ensure_column
        conn = get_connection(); c = conn.cursor()
        # Products: per-product window
        ensure_column(c, "products", "replacement_window_hours",
                      f"INTEGER DEFAULT {DEFAULT_WINDOW_HOURS}")
        # Orders: track if replacement was requested + how many times
        ensure_column(c, "orders", "replacement_count", "INTEGER DEFAULT 0")
        ensure_column(c, "orders", "replacement_status", "TEXT DEFAULT ''")
        ensure_column(c, "orders", "replacement_requested_at", "TEXT DEFAULT ''")
        ensure_column(c, "orders", "replacement_reason", "TEXT DEFAULT ''")
        conn.commit(); conn.close()
    except Exception as e:
        logger.debug(f"[Replacement] ensure_columns failed: {e}")


def get_window_hours(product_id) -> int:
    """Return replacement window in hours for a product (defaults to 24)."""
    _ensure_columns()
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT COALESCE(replacement_window_hours, ?) FROM products WHERE id=?",
                  (DEFAULT_WINDOW_HOURS, int(product_id)))
        r = c.fetchone()
        conn.close()
        return int(r[0]) if r else DEFAULT_WINDOW_HOURS
    except Exception:
        return DEFAULT_WINDOW_HOURS


def set_window_hours(product_id, hours: int) -> bool:
    """Admin sets the per-product replacement window."""
    _ensure_columns()
    try:
        from database import get_connection
        hours = max(0, int(hours))   # 0 = disabled
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE products SET replacement_window_hours=? WHERE id=?",
                  (hours, int(product_id)))
        conn.commit(); conn.close()
        return True
    except Exception as e:
        logger.warning(f"[Replacement] set_window_hours failed: {e}")
        return False


def is_eligible_for_replacement(order) -> tuple:
    """Check if an order can request replacement.
    Returns (eligible: bool, reason: str).
    """
    _ensure_columns()
    try:
        if not order:
            return False, "Order not found"
        # Must be delivered
        if order.get('status') != 'delivered':
            return False, "Order not yet delivered"
        # Must have a product
        if not order.get('product_id'):
            return False, "Not applicable (deposit/points order)"
        # Check if already requested or replaced
        status = (order.get('replacement_status') or '').lower()
        if status in ('pending', 'approved', 'rejected'):
            return False, f"Already requested ({status})"
        count = int(order.get('replacement_count') or 0)
        if count >= 1:
            return False, "Replacement already used"
        # Check window
        hours = get_window_hours(order.get('product_id'))
        if hours <= 0:
            return False, "Replacement not enabled for this product"
        # Parse delivery time
        created_at = order.get('created_at')
        if not created_at:
            return False, "Order date unavailable"
        try:
            order_dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return False, "Invalid date format"
        deadline = order_dt + timedelta(hours=hours)
        if datetime.utcnow() > deadline:
            elapsed = (datetime.utcnow() - order_dt).total_seconds() / 3600
            return False, f"Window expired ({hours}h limit, {int(elapsed)}h elapsed)"
        return True, "Eligible"
    except Exception as e:
        logger.warning(f"[Replacement] eligibility check failed: {e}")
        return False, str(e)


def mark_replacement_requested(order_id, reason: str):
    """Mark order as having a pending replacement request."""
    _ensure_columns()
    try:
        from database import get_connection
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection(); c = conn.cursor()
        c.execute("""
            UPDATE orders
            SET replacement_status='pending',
                replacement_requested_at=?,
                replacement_reason=?
            WHERE id=?
        """, (now, str(reason)[:200], int(order_id)))
        conn.commit(); conn.close()
        return True
    except Exception as e:
        logger.warning(f"[Replacement] mark_requested failed: {e}")
        return False


def mark_replacement_approved(order_id):
    """Mark replacement as approved + increment count."""
    _ensure_columns()
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("""
            UPDATE orders
            SET replacement_status='approved',
                replacement_count = COALESCE(replacement_count, 0) + 1
            WHERE id=?
        """, (int(order_id),))
        conn.commit(); conn.close()
        return True
    except Exception as e:
        logger.warning(f"[Replacement] mark_approved failed: {e}")
        return False


def mark_replacement_rejected(order_id):
    """Mark replacement as rejected (won't count toward count)."""
    _ensure_columns()
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE orders SET replacement_status='rejected' WHERE id=?",
                  (int(order_id),))
        conn.commit(); conn.close()
        return True
    except Exception as e:
        logger.warning(f"[Replacement] mark_rejected failed: {e}")
        return False


def format_window_label(hours: int) -> str:
    """Pretty-format hours like '24 hours' or '3 days'."""
    h = int(hours or 0)
    if h <= 0:
        return "❌ Disabled"
    if h < 24:
        return f"{h} hour{'s' if h != 1 else ''}"
    days = h // 24
    if h % 24 == 0:
        return f"{days} day{'s' if days != 1 else ''}"
    return f"{h} hours ({days}d {h%24}h)"


REASON_OPTIONS = [
    ("login_fail",  "🔒 Login Failed",        "The account credentials don't work"),
    ("banned",      "🚫 Account Banned",      "Account got banned/suspended quickly"),
    ("wrong",       "❓ Wrong Product",        "I received a different product"),
    ("expired",     "⏰ Subscription Expired", "Account expired before promised time"),
    ("other",       "📝 Other Issue",          "Custom reason (will need admin review)"),
]


# ============================================================
# 📄 ORIGINAL FILE: handlers_replacement.py
# ============================================================

# ============================================================
# 🔁 PRODUCT REPLACEMENT — user + admin handlers (v71)
# ============================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID
from database import (
    get_order, get_product, save_order_delivery_content,
    update_order_status, build_delivery_from_accounts,
)
from utils import escape_md, smart_text_and_mode
# [v77-merge] from replacement_system import (
# [v77-merge] is_eligible_for_replacement, mark_replacement_requested,
# [v77-merge] mark_replacement_approved, mark_replacement_rejected,
# [v77-merge] get_window_hours, format_window_label, REASON_OPTIONS,
# [v77-merge] )
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# 🔁 USER — Step 1: Tap "Report Issue" on order detail
# ════════════════════════════════════════════════════════════
def get_replacement_button(order):
    """Returns the inline button if eligible, else None.
    Called from my_order_detail_callback to inject into keyboard."""
    eligible, reason = is_eligible_for_replacement(order)
    if not eligible:
        return None
    return InlineKeyboardButton(
        "🔁 Report Issue (Free Replacement)",
        callback_data=f"reprep_{order['id']}",
    )


async def user_replace_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User tapped '🔁 Report Issue'. Show reason picker."""
    q = update.callback_query
    await q.answer()
    try:
        oid = int(q.data.replace("reprep_", ""))
    except Exception:
        await q.answer("Invalid order", show_alert=True); return

    o = get_order(oid)
    if not o or o['user_id'] != q.from_user.id:
        await q.answer("Order not found", show_alert=True); return

    eligible, reason_msg = is_eligible_for_replacement(o)
    if not eligible:
        await q.answer(f"❌ {reason_msg}", show_alert=True)
        return

    hours = get_window_hours(o.get('product_id'))
    text = (
        f"🔁 *Report Issue — Order #{oid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Product: *{escape_md(o.get('product_name','') or '?')}*\n"
        f"⏰ Replacement window: *{format_window_label(hours)}*\n\n"
        f"Why do you need a replacement?\n\n"
        f"_Admin will review your request and respond shortly._"
    )
    kb_rows = []
    for code, label, _desc in REASON_OPTIONS:
        kb_rows.append([InlineKeyboardButton(label, callback_data=f"reprsn_{oid}_{code}")])
    kb_rows.append([InlineKeyboardButton("❌ Cancel", callback_data=f"myord_{oid}")])
    await q.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(kb_rows))


async def user_replace_reason_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User picked a reason. Mark order + DM admin for approval."""
    q = update.callback_query
    await q.answer()
    try:
        parts = q.data.replace("reprsn_", "").split("_", 1)
        oid = int(parts[0])
        reason_code = parts[1] if len(parts) > 1 else "other"
    except Exception:
        await q.answer("Invalid request", show_alert=True); return

    o = get_order(oid)
    if not o or o['user_id'] != q.from_user.id:
        await q.answer("Order not found", show_alert=True); return

    # Re-check eligibility (in case of race)
    eligible, reason_msg = is_eligible_for_replacement(o)
    if not eligible:
        await q.answer(f"❌ {reason_msg}", show_alert=True)
        return

    # Find the human-friendly reason label
    reason_label = "Other"
    for code, label, _desc in REASON_OPTIONS:
        if code == reason_code:
            reason_label = label
            break

    # Mark as pending
    mark_replacement_requested(oid, reason_label)

    # User confirmation
    await q.edit_message_text(
        f"✅ *Replacement Request Submitted*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🧾 Order #{oid}\n"
        f"📝 Reason: *{escape_md(reason_label)}*\n"
        f"📊 Status: 🟡 Pending admin review\n\n"
        f"You'll be notified as soon as admin approves or rejects.\n"
        f"_Most requests are reviewed within a few hours._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
            [InlineKeyboardButton("🏠 Main Menu",     callback_data="main_menu")],
        ]))

    # Notify admin
    try:
        user_name = q.from_user.first_name or str(q.from_user.id)
        admin_text = (
            f"🔁 *Replacement Request — Order #{oid}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Customer: {escape_md(user_name)} (`{q.from_user.id}`)\n"
            f"📦 Product: *{escape_md(o.get('product_name','') or '?')}*\n"
            f"💰 Original price: *${float(o.get('price') or 0):.2f}*\n"
            f"📝 Reason: *{escape_md(reason_label)}*\n\n"
            f"Tap *Approve* to dispense a new account automatically, or *Reject*."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve & Replace", callback_data=f"adm_repap_{oid}"),
             InlineKeyboardButton("❌ Reject",             callback_data=f"adm_reprj_{oid}")],
        ])
        await context.bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown",
                                        reply_markup=kb)
    except Exception as e:
        logger.warning(f"[Replacement] admin notify failed: {e}")


# ════════════════════════════════════════════════════════════
# 🛡 ADMIN — Approve / Reject
# ════════════════════════════════════════════════════════════
async def admin_replace_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approved — dispense new account."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Processing replacement…")
    try:
        oid = int(q.data.replace("adm_repap_", ""))
    except Exception:
        await q.answer("Invalid order", show_alert=True); return

    o = get_order(oid)
    if not o:
        await q.edit_message_text("❌ Order not found."); return

    # Try to dispense a new account
    p = get_product(o.get('product_id')) if o.get('product_id') else None
    if not p:
        await q.edit_message_text("❌ Product not found in DB."); return

    qty = 1
    import re as _re
    qm = _re.search(r'×\s*(\d+)$', o.get('product_name','') or '')
    if qm:
        qty = int(qm.group(1))

    try:
        new_delivery = build_delivery_from_accounts(
            o['product_id'], o['id'], qty, o['user_id'],
        )
    except Exception as e:
        await q.edit_message_text(
            f"❌ *Auto-dispense failed*\n\n`{e}`\n\n"
            f"Probably no stock left. Please add stock or deliver manually.",
            parse_mode="Markdown")
        return

    if not new_delivery or "no stock" in str(new_delivery).lower():
        await q.edit_message_text(
            "⚠️ *No stock available*\n\n"
            "Please add more stock to this product and try again,\n"
            "or use 📦 Pending Manual Delivery to deliver manually.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Pending Delivery", callback_data="adm_pending_delivery")],
            ]))
        return

    # Save replacement delivery + mark order
    try:
        save_order_delivery_content(oid, f"[🔁 REPLACEMENT]\n{new_delivery}")
    except Exception:
        pass
    mark_replacement_approved(oid)

    # Notify customer
    user_id = o['user_id']
    pname = o.get('product_name','') or 'your product'
    customer_msg = (
        # 🆕 v80 BYTE-PERFECT: switch to HTML mode for the delivery portion.
        # <code>...</code> preserves _ * / \\ etc. exactly as admin entered them.
        f"[[HTML]]✅ <b>Replacement Approved!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🧾 Order #{oid}\n"
        f"📦 Product: <b>{__import__('utils').html_escape_plain(pname)}</b>\n\n"
        f"📨 <b>New Delivery:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{__import__('utils').html_code_block(new_delivery[:1500])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Sorry for the inconvenience. Thank you for your patience! 🙏"
    )
    send_text, send_mode = smart_text_and_mode(customer_msg, "Markdown")
    try:
        await context.bot.send_message(user_id, send_text, parse_mode=send_mode,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
                [InlineKeyboardButton("🛒 Shop More",     callback_data="shop")],
            ]))
    except Exception as e:
        logger.warning(f"[Replacement] customer notify failed: {e}")

    # Admin confirmation
    await q.edit_message_text(
        f"✅ *Replacement Sent*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Order #{oid} — new account dispensed from stock.\n"
        f"Customer `{user_id}` has been notified.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Pending Delivery", callback_data="adm_pending_delivery")],
            [InlineKeyboardButton("🔙 Admin Panel",      callback_data="admin_panel")],
        ]))


async def admin_replace_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin rejected — notify customer."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Rejecting…")
    try:
        oid = int(q.data.replace("adm_reprj_", ""))
    except Exception:
        await q.answer("Invalid order", show_alert=True); return

    o = get_order(oid)
    if not o:
        await q.edit_message_text("❌ Order not found."); return

    mark_replacement_rejected(oid)

    user_id = o['user_id']
    pname = o.get('product_name','') or 'your product'
    customer_msg = (
        f"❌ *Replacement Request — Not Approved*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🧾 Order #{oid}\n"
        f"📦 Product: *{escape_md(pname)}*\n\n"
        f"After review, we are unable to approve a free replacement for this order.\n\n"
        f"If you believe this is a mistake, please open a new support ticket "
        f"with more details — our team will assist."
    )
    send_text, send_mode = smart_text_and_mode(customer_msg, "Markdown")
    try:
        await context.bot.send_message(user_id, send_text, parse_mode=send_mode,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="st_new")],
                [InlineKeyboardButton("🏠 Main Menu",             callback_data="main_menu")],
            ]))
    except Exception as e:
        logger.warning(f"[Replacement] customer notify failed: {e}")

    await q.edit_message_text(
        f"❌ *Replacement Rejected*\n\n"
        f"Order #{oid} — customer notified.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Pending Delivery", callback_data="adm_pending_delivery")],
            [InlineKeyboardButton("🔙 Admin Panel",      callback_data="admin_panel")],
        ]))


# ============================================================
# 📄 ORIGINAL FILE: handlers_replacement_history.py
# ============================================================

# ============================================
# 🔁 REPLACEMENT HISTORY & MANAGEMENT  (v73)
# ============================================
# Admin panel to browse + manage every replacement request ever made.
#
# Tabs:  All / Pending / Approved / Rejected
# Per-replacement view: user, product, order id, reason, requested date,
#   current status + Approve / Reject / Note buttons.
#
# Backed by the same `orders` table columns added in v71 by replacement_system:
#   replacement_status   ('' | 'pending' | 'approved' | 'rejected')
#   replacement_reason   (text)
#   replacement_requested_at (ISO timestamp)
#   replacement_count    (int)
# ============================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_ID
from database import get_connection
# [v77-merge] from replacement_system import (
# [v77-merge] _ensure_columns, mark_replacement_approved, mark_replacement_rejected,
# [v77-merge] )
logger = logging.getLogger(__name__)

PAGE_SIZE = 20

# Filter key → label + SQL WHERE clause
_FILTERS = {
    "all": {
        "label": "📋 All",
        "where": "replacement_status IN ('pending','approved','rejected')",
    },
    "pending": {
        "label": "⏳ Pending",
        "where": "replacement_status = 'pending'",
    },
    "approved": {
        "label": "✅ Approved",
        "where": "replacement_status = 'approved'",
    },
    "rejected": {
        "label": "❌ Rejected",
        "where": "replacement_status = 'rejected'",
    },
}

_STATUS_EMOJI = {
    "pending":  "⏳",
    "approved": "✅",
    "rejected": "❌",
    "":         "•",
}


async def _safe_edit(q, text, **kwargs):
    try:
        await q.edit_message_text(text, **kwargs)
    except Exception:
        try:
            kwargs.pop("parse_mode", None)
            await q.edit_message_text(text, **kwargs)
        except Exception:
            try:
                await q.message.reply_text(text)
            except Exception:
                pass


def _fetch_replacements(filter_key: str, page: int = 0):
    _ensure_columns()
    f = _FILTERS.get(filter_key) or _FILTERS["all"]
    where = f["where"]
    offset = max(0, int(page)) * PAGE_SIZE
    conn = get_connection()
    c = conn.cursor()
    c.execute(f"SELECT COUNT(*) FROM orders WHERE {where}")
    total = int(c.fetchone()[0] or 0)
    c.execute(f"""
        SELECT id, user_id, product_name, price, status,
               COALESCE(replacement_status, '') as rep_status,
               COALESCE(replacement_reason, '') as rep_reason,
               COALESCE(replacement_requested_at, '') as rep_at,
               COALESCE(replacement_count, 0) as rep_count
        FROM orders
        WHERE {where}
        ORDER BY datetime(COALESCE(replacement_requested_at, created_at)) DESC,
                 id DESC
        LIMIT ? OFFSET ?
    """, (PAGE_SIZE, offset))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows, total


def _build_text(filter_key: str, total: int) -> str:
    meta = _FILTERS.get(filter_key) or _FILTERS["all"]
    return (
        f"🔁 *Replacement History*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 Filter: {meta['label']}\n"
        f"🔢 Total: *{total}* request(s)\n\n"
        f"_Tap any row to view full details + manage._"
    )


def _build_keyboard(rows, filter_key: str, page: int, total: int):
    kb = []
    # Filter tabs (2 per row)
    tabs = []
    for key in ("all", "pending", "approved", "rejected"):
        meta = _FILTERS[key]
        prefix = "⦿ " if key == filter_key else ""
        tabs.append(InlineKeyboardButton(
            f"{prefix}{meta['label']}",
            callback_data=f"admin_replacements_filter_{key}_0",
        ))
    kb.append(tabs[:2])
    kb.append(tabs[2:])

    # 🔧 v78 FIX: clean product names for professional display (strip HTML/emoji markup)
    from utils import name_for_button
    for o in rows:
        e = _STATUS_EMOJI.get(o.get("rep_status") or "", "•")
        raw_name = o.get("product_name") or "Product"
        clean_name = name_for_button(raw_name) or "Product"
        pname = clean_name[:24]
        label = f"{e} #{o['id']} • {pname} • U{o['user_id']}"
        kb.append([InlineKeyboardButton(label,
                    callback_data=f"admin_replacement_view_{o['id']}")])

    if not rows:
        kb.append([InlineKeyboardButton("📭 No replacements in this category",
                                         callback_data="admin_replacements")])

    # Pagination
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Prev",
                callback_data=f"admin_replacements_filter_{filter_key}_{page-1}"))
        nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}",
            callback_data="admin_replacements"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️ Next",
                callback_data=f"admin_replacements_filter_{filter_key}_{page+1}"))
        kb.append(nav)

    kb.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


# ───────────────────────────────────────────
# Callbacks
# ───────────────────────────────────────────

async def admin_replacement_history_callback(update, context):
    """Open Replacement History — defaults to 'all' filter, page 0."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    rows, total = _fetch_replacements("all", 0)
    await _safe_edit(q, _build_text("all", total),
                     parse_mode="Markdown",
                     reply_markup=_build_keyboard(rows, "all", 0, total))


async def admin_replacement_filter_callback(update, context):
    """Filter / paginate.  Callback: admin_replacements_filter_<key>_<page>"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    data = (q.data or "").replace("admin_replacements_filter_", "", 1)
    try:
        key, page_str = data.rsplit("_", 1)
        page = int(page_str)
    except Exception:
        key, page = "all", 0
    if key not in _FILTERS:
        key = "all"
    rows, total = _fetch_replacements(key, page)
    await _safe_edit(q, _build_text(key, total),
                     parse_mode="Markdown",
                     reply_markup=_build_keyboard(rows, key, page, total))


async def admin_replacement_view_callback(update, context):
    """View one replacement's full detail. Callback: admin_replacement_view_<oid>"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        oid = int((q.data or "").replace("admin_replacement_view_", "", 1))
    except Exception:
        oid = 0
    _ensure_columns()
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT id, user_id, product_id, product_name, price, status,
               COALESCE(created_at, '') as created_at,
               COALESCE(replacement_status, '') as rep_status,
               COALESCE(replacement_reason, '') as rep_reason,
               COALESCE(replacement_requested_at, '') as rep_at,
               COALESCE(replacement_count, 0) as rep_count
        FROM orders WHERE id=?
    """, (oid,))
    r = c.fetchone()
    conn.close()
    if not r:
        await _safe_edit(q, "❌ Order not found.",
                         reply_markup=InlineKeyboardMarkup([[
                             InlineKeyboardButton("🔙 Back", callback_data="admin_replacements")
                         ]]))
        return
    o = dict(r)
    rs = (o.get("rep_status") or "").lower()
    e = _STATUS_EMOJI.get(rs, "•")
    pname = o.get("product_name") or "Product"
    reason = o.get("rep_reason") or "_(no reason given)_"
    rep_at = o.get("rep_at") or "_unknown_"
    order_status = (o.get("status") or "").lower() or "_unknown_"
    text = (
        f"🔁 *Replacement Request #{o['id']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Product: *{pname}*\n"
        f"💵 Price: `${float(o.get('price') or 0):.2f}`\n"
        f"👤 User: `{o['user_id']}`\n"
        f"📅 Order placed: {o.get('created_at') or '_unknown_'}\n"
        f"📅 Replacement requested: {rep_at}\n"
        f"🔢 Replacement count: *{o.get('rep_count') or 0}*\n"
        f"📊 Order status: `{order_status}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 *Reason given:*\n{reason}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 Current replacement status: {e} *{rs.upper() or 'NONE'}*"
    )

    kb = []
    if rs == "pending":
        kb.append([
            InlineKeyboardButton("✅ Approve",
                callback_data=f"admin_replacement_act_approve_{oid}"),
            InlineKeyboardButton("❌ Reject",
                callback_data=f"admin_replacement_act_reject_{oid}"),
        ])
    elif rs == "approved":
        kb.append([
            InlineKeyboardButton("↩️ Mark as Rejected",
                callback_data=f"admin_replacement_act_reject_{oid}"),
        ])
    elif rs == "rejected":
        kb.append([
            InlineKeyboardButton("↩️ Mark as Approved",
                callback_data=f"admin_replacement_act_approve_{oid}"),
        ])
    # View original order detail (re-uses existing view_order_<id> handler)
    kb.append([InlineKeyboardButton("📦 View Original Order",
                                     callback_data=f"view_order_{oid}")])
    kb.append([InlineKeyboardButton("🔙 Back to History",
                                     callback_data="admin_replacements")])

    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def admin_replacement_action_callback(update, context):
    """Approve / reject a replacement.
    Callback: admin_replacement_act_<approve|reject>_<oid>
    """
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    data = (q.data or "").replace("admin_replacement_act_", "", 1)
    try:
        action, oid_str = data.split("_", 1)
        oid = int(oid_str)
    except Exception:
        await q.answer("⚠️ Bad payload", show_alert=True); return

    ok = False
    if action == "approve":
        ok = mark_replacement_approved(oid)
        await q.answer("✅ Approved" if ok else "❌ Failed", show_alert=True)
    elif action == "reject":
        ok = mark_replacement_rejected(oid)
        await q.answer("❌ Rejected" if ok else "❌ Failed", show_alert=True)
    else:
        await q.answer("⚠️ Unknown action", show_alert=True)
        return

    # Notify user
    if ok:
        try:
            conn = get_connection(); c = conn.cursor()
            c.execute("SELECT user_id, product_name FROM orders WHERE id=?", (oid,))
            r = c.fetchone(); conn.close()
            if r:
                pname = r["product_name"] or "Product"
                if action == "approve":
                    msg = (f"✅ *Replacement Approved*\n\n"
                           f"📦 Product: *{pname}*\n"
                           f"🆔 Order #{oid}\n\n"
                           f"Admin has approved your replacement request. "
                           f"You will receive your replacement shortly.")
                else:
                    msg = (f"❌ *Replacement Rejected*\n\n"
                           f"📦 Product: *{pname}*\n"
                           f"🆔 Order #{oid}\n\n"
                           f"Admin has reviewed and rejected your replacement request. "
                           f"Please contact support for any questions.")
                try:
                    await context.bot.send_message(r["user_id"], msg, parse_mode="Markdown")
                except Exception as e:
                    logger.debug(f"[ReplacementHistory] notify user failed: {e}")
        except Exception as e:
            logger.debug(f"[ReplacementHistory] notify lookup failed: {e}")

    # Refresh the detail view
    from telegram.ext import ContextTypes  # noqa
    # Re-trigger view callback by mutating q.data
    try:
        q.data = f"admin_replacement_view_{oid}"
    except Exception:
        pass
    await admin_replacement_view_callback(update, context)


# ============================================================
# 📄 ORIGINAL FILE: review_reminder.py
# ============================================================

# ============================================================
# 📝 REVIEW REMINDER (v69)
# ============================================================
# 24 hours after an order is delivered, automatically send the
# customer a friendly English message asking for feedback/review.
#
# Idempotent — never sends twice for the same order.
# Uses a `review_reminder_sent` column on orders table to track.
# ============================================================

import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

REMINDER_HOURS = 24   # delay after delivery before asking
LOOK_BACK_HOURS = 72  # don't send for orders older than 72h (avoid spam on bot restart)


def _ensure_column():
    """Add the review_reminder_sent column if it doesn't exist."""
    try:
        from database import get_connection, ensure_column
        conn = get_connection(); c = conn.cursor()
        ensure_column(c, "orders", "review_reminder_sent", "INTEGER DEFAULT 0")
        conn.commit(); conn.close()
    except Exception as e:
        logger.debug(f"[ReviewReminder] ensure_column failed: {e}")


def _pick_eligible_orders():
    """Return a list of orders that need a review reminder NOW.
       Criteria:
       - status = 'delivered'
       - product_id IS NOT NULL (only real products, not points deposits)
       - delivered between LOOK_BACK_HOURS ago and REMINDER_HOURS ago
       - review_reminder_sent = 0
    """
    _ensure_column()
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        now = datetime.utcnow()
        # Window: must be > 24h old but < 72h old
        upper = (now - timedelta(hours=REMINDER_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
        lower = (now - timedelta(hours=LOOK_BACK_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            SELECT id, user_id, product_id, product_name, created_at
            FROM orders
            WHERE status = 'delivered'
              AND product_id IS NOT NULL
              AND COALESCE(review_reminder_sent, 0) = 0
              AND created_at <= ?
              AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT 20
        """, (upper, lower))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"[ReviewReminder] eligible query failed: {e}")
        return []


def _mark_sent(order_id):
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE orders SET review_reminder_sent = 1 WHERE id = ?", (int(order_id),))
        conn.commit(); conn.close()
    except Exception as e:
        logger.debug(f"[ReviewReminder] mark_sent failed: {e}")


def _build_message(order, product_name):
    """Build the English review request message."""
    return (
        f"⭐ *How was your experience?*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Hi! You purchased *{product_name}* from us "
        f"about 24 hours ago.\n\n"
        f"Your feedback genuinely helps other customers decide. "
        f"Would you take a moment to share a short review?\n\n"
        f"It only takes 30 seconds and helps the whole community! 🙏"
    )


async def review_reminder_job(context):
    """Background job — runs hourly. Sends reminders for eligible orders."""
    try:
        orders = _pick_eligible_orders()
        if not orders:
            return
        sent_count = 0
        for o in orders:
            try:
                oid    = int(o['id'])
                uid    = int(o['user_id'])
                pname  = str(o.get('product_name') or 'your order')[:80]
                pid    = o.get('product_id')

                # Build message + keyboard
                msg = _build_message(o, pname)
                kb_rows = []
                if pid:
                    kb_rows.append([
                        InlineKeyboardButton("⭐ Write a Review",
                                             callback_data=f"rate_{pid}")
                    ])
                kb_rows.append([
                    InlineKeyboardButton("⭐ My Reviews",  callback_data="reviews_menu"),
                ])
                kb_rows.append([
                    InlineKeyboardButton("🛒 Buy More",   callback_data="shop"),
                    InlineKeyboardButton("🏠 Main Menu",  callback_data="main_menu"),
                ])
                kb = InlineKeyboardMarkup(kb_rows)

                try:
                    await context.bot.send_message(
                        uid, msg, parse_mode="Markdown", reply_markup=kb,
                    )
                    _mark_sent(oid)
                    sent_count += 1
                    logger.info(f"[ReviewReminder] sent for order #{oid} → uid={uid}")
                except Exception as e:
                    # User may have blocked the bot — mark as sent so we don't retry
                    msg_low = str(e).lower()
                    if "forbidden" in msg_low or "chat not found" in msg_low or "blocked" in msg_low:
                        _mark_sent(oid)
                        logger.debug(f"[ReviewReminder] user blocked or chat gone for oid={oid}: {e}")
                    else:
                        logger.warning(f"[ReviewReminder] send failed for oid={oid}: {e}")
            except Exception as e:
                logger.warning(f"[ReviewReminder] order processing failed: {e}")
                continue
        if sent_count > 0:
            logger.info(f"[ReviewReminder] ✅ sent {sent_count} reminders this cycle")
    except Exception as e:
        logger.error(f"[ReviewReminder] job error: {e}")

