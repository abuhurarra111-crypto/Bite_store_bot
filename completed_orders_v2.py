# ============================================================
# ✅ v84: COMPLETED ORDERS — GROUPED BY USER (v2)
# ============================================================
# Overhauls the "Completed Orders" admin screen.
#
# The old (v73) panel listed every order individually. Now:
#   1. TOP screen  → user list, sorted by most-recent order,
#      searchable, with count + total spend + last-order date.
#   2. USER screen → all completed orders by that user, newest
#      first, with product name, price, date/time, order id,
#      status, AND the full delivered account details.
#
# Preserves the old panel entry (admin_completed) — this new
# panel is added as admin_completed_v2 and wired to the same
# button. The old callbacks stay registered as a safety-net
# fallback; nothing existing breaks.
#
# Callbacks:
#   admin_completed_v2                      → top user list
#   ac2_search                              → prompt admin for search text
#   ac2_page_<n>                            → paginate user list
#   ac2_user_<uid>_<page>                   → open a specific user's orders
#   ac2_order_<oid>                         → show full details of one order
# ============================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import ADMIN_ID
from database import get_connection

logger = logging.getLogger(__name__)

USERS_PER_PAGE = 15
ORDERS_PER_PAGE = 20

_COMPLETED_STATUSES = ("delivered", "refunded", "cancelled", "rejected")

# In-memory search text keyed by admin id (transient, resets on restart —
# fine because admin usually searches once per session).
_SEARCH_CACHE = {}   # admin_id → search string (lowercased)

# Conversation state for search input
AC2_SEARCH_TEXT = 9285


async def _safe_edit(q, text, **kw):
    try:
        await q.edit_message_text(text, **kw)
    except Exception:
        try:
            kw.pop("parse_mode", None)
            await q.edit_message_text(text, **kw)
        except Exception:
            try:
                await q.message.reply_text(text)
            except Exception:
                pass


# ------------------------------------------------------------
# Data helpers
# ------------------------------------------------------------
def _fetch_users_with_completed_orders(search: str = ""):
    """
    Returns list of dicts sorted by most-recent order desc:
      { user_id, name, orders_count, total_spend, last_order_at }

    `search` (optional) matches against user_id, username, first_name
    (case-insensitive substring).
    """
    conn = get_connection()
    c = conn.cursor()
    # Aggregate per user_id from orders. Join to users table for name.
    sql = f"""
        SELECT o.user_id,
               COALESCE(NULLIF(u.first_name, ''),
                        NULLIF(u.username, ''),
                        NULLIF(o.user_name, ''),
                        CAST(o.user_id AS TEXT)) AS display_name,
               COALESCE(u.username, '') AS username,
               COUNT(*)                                        AS orders_count,
               COALESCE(SUM(CASE WHEN o.status='delivered'
                                 THEN o.price ELSE 0 END), 0)  AS total_spend,
               MAX(COALESCE(o.created_at, ''))                 AS last_order_at
        FROM orders o
        LEFT JOIN users u ON u.user_id = o.user_id
        WHERE o.status IN ({",".join("?" * len(_COMPLETED_STATUSES))})
        GROUP BY o.user_id
        ORDER BY last_order_at DESC, orders_count DESC
    """
    c.execute(sql, _COMPLETED_STATUSES)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    if search:
        s = search.lower().strip()
        def _match(r):
            hay = (
                str(r.get("user_id") or "") + " " +
                str(r.get("display_name") or "").lower() + " " +
                str(r.get("username") or "").lower()
            )
            return s in hay
        rows = [r for r in rows if _match(r)]
    return rows


def _fetch_orders_of_user(uid: int):
    """Return every completed order of a user, newest first."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(f"""
        SELECT id, user_id, product_id, product_name, price, status,
               COALESCE(created_at, '') AS created_at,
               COALESCE(payment_method, '') AS payment_method,
               COALESCE(delivery_content, '') AS delivery_content
        FROM orders
        WHERE user_id=? AND status IN ({",".join("?" * len(_COMPLETED_STATUSES))})
        ORDER BY id DESC
    """, (uid, *_COMPLETED_STATUSES))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def _fetch_single_order(oid: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, user_name, product_id, product_name, price, status,
               COALESCE(created_at, '') AS created_at,
               COALESCE(payment_method, '') AS payment_method,
               COALESCE(delivery_content, '') AS delivery_content
        FROM orders WHERE id=?
    """, (oid,))
    r = c.fetchone()
    conn.close()
    return dict(r) if r else None


def _status_emoji(s: str) -> str:
    return {
        "delivered": "✅",
        "refunded":  "💸",
        "cancelled": "❌",
        "rejected":  "🚫",
    }.get(s, "•")


def _fmt_date(dt: str) -> str:
    """Return a short date+time from ISO / SQL timestamp."""
    if not dt:
        return "—"
    # Try to keep it short: 'YYYY-MM-DD HH:MM'
    try:
        # Common SQLite: 'YYYY-MM-DD HH:MM:SS'
        return dt[:16]
    except Exception:
        return dt


# ------------------------------------------------------------
# TOP SCREEN — user list
# ------------------------------------------------------------
def _build_user_list_kb(rows, page: int, search: str) -> InlineKeyboardMarkup:
    from utils import name_for_button
    kb = []
    kb.append([InlineKeyboardButton(
        "🔎 Search Users…" if not search else f"🔎 Search: {search[:20]}",
        callback_data="ac2_search")])
    if search:
        kb.append([InlineKeyboardButton("🧹 Clear Search",
                                         callback_data="ac2_clear_search")])

    total = len(rows)
    total_pages = max(1, (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * USERS_PER_PAGE
    end = start + USERS_PER_PAGE
    page_rows = rows[start:end]

    if not page_rows:
        kb.append([InlineKeyboardButton("📭 No users found",
                                         callback_data="admin_completed_v2")])
    for r in page_rows:
        name = name_for_button(r.get("display_name") or "User") or "User"
        name = name[:22]
        spent = float(r.get("total_spend") or 0)
        cnt = int(r.get("orders_count") or 0)
        label = f"👤 {name} • {cnt} orders • ${spent:.2f}"
        kb.append([InlineKeyboardButton(
            label, callback_data=f"ac2_user_{r['user_id']}_0")])

    # Pagination
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Prev",
                                             callback_data=f"ac2_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}",
                                         callback_data="ac2_noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️ Next",
                                             callback_data=f"ac2_page_{page+1}"))
        kb.append(nav)

    kb.append([InlineKeyboardButton("📋 Old Flat View",
                                     callback_data="admin_completed")])
    kb.append([InlineKeyboardButton("🔙 Back to Admin Panel",
                                     callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


def _build_user_list_text(rows, search: str) -> str:
    total = len(rows)
    tail = f"\n🔎 Filter: `{search}`" if search else ""
    return (
        "✅ *Completed Orders — Users*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total customers with completed orders: *{total}*\n"
        "📅 Sorted by most-recent order\n"
        f"{tail}\n\n"
        "_Tap any user to see all their purchases with delivered account details._"
    )


# ------------------------------------------------------------
# USER SCREEN — orders of that user
# ------------------------------------------------------------
def _build_user_orders_kb(uid: int, orders, page: int) -> InlineKeyboardMarkup:
    from utils import name_for_button
    kb = []
    total = len(orders)
    total_pages = max(1, (total + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * ORDERS_PER_PAGE
    end = start + ORDERS_PER_PAGE
    page_rows = orders[start:end]

    for o in page_rows:
        em = _status_emoji(o.get("status", ""))
        pname = name_for_button(o.get("product_name") or "Product") or "Product"
        pname = pname[:24]
        price = float(o.get("price") or 0)
        dt = _fmt_date(o.get("created_at") or "")
        label = f"{em} #{o['id']} • {pname} • ${price:.2f} • {dt}"
        kb.append([InlineKeyboardButton(label,
                                         callback_data=f"ac2_order_{o['id']}")])

    if not page_rows:
        kb.append([InlineKeyboardButton("📭 No completed orders",
                                         callback_data="admin_completed_v2")])

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Prev",
                                             callback_data=f"ac2_user_{uid}_{page-1}"))
        nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}",
                                         callback_data="ac2_noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️ Next",
                                             callback_data=f"ac2_user_{uid}_{page+1}"))
        kb.append(nav)

    kb.append([InlineKeyboardButton("🔙 Back to Users",
                                     callback_data="admin_completed_v2")])
    return InlineKeyboardMarkup(kb)


def _build_user_orders_text(uid: int, orders) -> str:
    total = len(orders)
    delivered = sum(1 for o in orders if o.get("status") == "delivered")
    refunded = sum(1 for o in orders if o.get("status") == "refunded")
    cancelled = sum(1 for o in orders
                    if o.get("status") in ("cancelled", "rejected"))
    spent = sum(float(o.get("price") or 0) for o in orders
                if o.get("status") == "delivered")
    # Try to pull a display name
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT COALESCE(NULLIF(first_name,''), NULLIF(username,''), '')
                  AS n, COALESCE(username,'') AS un
                  FROM users WHERE user_id=?""", (uid,))
    r = c.fetchone(); conn.close()
    dname = (r["n"] if r else "") or str(uid)
    un = (f" (@{r['un']})" if (r and r["un"]) else "")
    return (
        f"👤 *{dname}*{un}\n"
        f"🆔 User ID: `{uid}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Total orders: *{total}*   💵 Spent: *${spent:.2f}*\n"
        f"✅ Delivered: {delivered}  💸 Refunded: {refunded}  ❌ Cancelled: {cancelled}\n\n"
        "_Tap any order to see full details + delivered account._"
    )


# ------------------------------------------------------------
# ORDER SCREEN — full details
# ------------------------------------------------------------
def _build_order_detail_kb(order: dict) -> InlineKeyboardMarkup:
    kb = []
    uid = order.get("user_id")
    # 🆕 v101: "User-Side Delivery Content" button — shows EXACTLY what the
    # customer saw when their order was delivered (byte-perfect, same HTML,
    # same premium emojis, same buttons). Admin can then decide if the
    # format needs adjustment.
    oid = order.get("id")
    if order.get("status") == "delivered" and order.get("delivery_content"):
        kb.append([InlineKeyboardButton("👀 User-Side Delivery View",
                                         callback_data=f"ac2_userview_{oid}")])
    kb.append([InlineKeyboardButton("🔙 Back to User's Orders",
                                     callback_data=f"ac2_user_{uid}_0")])
    kb.append([InlineKeyboardButton("👥 All Users",
                                     callback_data="admin_completed_v2")])
    return InlineKeyboardMarkup(kb)


def _build_order_detail_text(order: dict) -> str:
    from utils import html_code_block
    def escape_html(s: str) -> str:
        s = str(s or "")
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 🐛 v100 FIX: Product name may contain [[HTML]]<tg-emoji ...> premium
    # markup. Escaping it with escape_html() shows raw <tg-emoji ...> tags
    # to admin (see screenshot). Detect & embed HTML markup properly.
    def _render_product_name(raw):
        s = str(raw or "Product").strip()
        # Strip [[HTML]] sentinel and let the <tg-emoji>/HTML pass through
        if s.startswith("[[HTML]]"):
            return s[len("[[HTML]]"):]
        # Legacy: contains raw HTML tags (b/i/tg-emoji/etc.) — embed as-is
        import re as _re
        if _re.search(r"<(?:b|i|u|s|code|tg-emoji|a)\b", s, flags=_re.I):
            return s
        # Plain text — safe to escape
        return escape_html(s)

    em = _status_emoji(order.get("status", ""))
    pname = _render_product_name(order.get("product_name"))
    dt = _fmt_date(order.get("created_at") or "")
    price = float(order.get("price") or 0)
    pay = escape_html(order.get("payment_method") or "—")
    uname = escape_html(order.get("user_name") or "")
    dc = (order.get("delivery_content") or "").strip()

    body = (
        f"{em} <b>Order #{order['id']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Product:</b> {pname}\n"
        f"💵 <b>Price:</b> ${price:.2f}\n"
        f"💳 <b>Payment:</b> {pay}\n"
        f"📅 <b>When:</b> {dt}\n"
        f"🆔 <b>Order ID:</b> <code>#{order['id']}</code>\n"
        f"🧑 <b>Customer:</b> {uname or ('user ' + str(order.get('user_id')))}\n"
        f"🔖 <b>Status:</b> {order.get('status','?')}\n"
    )

    if dc:
        body += "\n📤 <b>Delivered Content:</b>\n"
        # 🐛 v100 FIX: delivery_content may already be rendered HTML (from
        # v83 renderer render_v83_delivery — starts with "[[HTML]]" or
        # contains <b>/<code>/<tg-emoji> markup). If so, embed as-is instead
        # of wrapping in html_code_block() which escapes all < > → shows
        # raw "<b>...</b>" text to admin (see user screenshot Order #6).
        import re as _re
        if dc.startswith("[[HTML]]"):
            body += dc[len("[[HTML]]"):]
        elif _re.search(r"<(?:b|i|u|s|code|pre|tg-emoji|a)\b", dc, flags=_re.I):
            # Already-rendered HTML delivery block — embed directly
            body += dc
        else:
            # Plain text (admin's manual delivery) — byte-perfect wrap
            body += html_code_block(dc)
    else:
        body += "\n📤 <b>Delivered Content:</b> <i>(nothing stored)</i>\n"
    return "[[HTML]]" + body


# ------------------------------------------------------------
# CALLBACK HANDLERS
# ------------------------------------------------------------
async def admin_completed_v2_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    search = _SEARCH_CACHE.get(q.from_user.id, "")
    rows = _fetch_users_with_completed_orders(search=search)
    kb = _build_user_list_kb(rows, page=0, search=search)
    await _safe_edit(q, _build_user_list_text(rows, search),
                     parse_mode="Markdown", reply_markup=kb)


async def ac2_page_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        page = int((q.data or "").replace("ac2_page_", ""))
    except Exception:
        page = 0
    search = _SEARCH_CACHE.get(q.from_user.id, "")
    rows = _fetch_users_with_completed_orders(search=search)
    kb = _build_user_list_kb(rows, page=page, search=search)
    await _safe_edit(q, _build_user_list_text(rows, search),
                     parse_mode="Markdown", reply_markup=kb)


async def ac2_user_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    data = (q.data or "").replace("ac2_user_", "", 1)
    try:
        uid_s, page_s = data.rsplit("_", 1)
        uid = int(uid_s); page = int(page_s)
    except Exception:
        return
    orders = _fetch_orders_of_user(uid)
    kb = _build_user_orders_kb(uid, orders, page)
    await _safe_edit(q, _build_user_orders_text(uid, orders),
                     parse_mode="Markdown", reply_markup=kb)


async def ac2_order_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        oid = int((q.data or "").replace("ac2_order_", ""))
    except Exception:
        return
    o = _fetch_single_order(oid)
    if not o:
        await _safe_edit(q, "❌ Order not found.")
        return
    text = _build_order_detail_text(o)
    kb = _build_order_detail_kb(o)
    # HTML because we use [[HTML]] prefix and <code>
    await _safe_edit(q, text, parse_mode="HTML",
                     reply_markup=kb, disable_web_page_preview=True)


async def ac2_userview_callback(update, context):
    """🆕 v101: Show the EXACT delivery message the customer received —
    byte-perfect, same HTML mode, same premium emojis. Admin uses this to
    verify the format that customers see and decide if it needs changing.

    Content flow:
      1. Load order.delivery_content from DB (this IS the exact bytes sent
         to the customer's private chat when their order was delivered)
      2. Send as a fresh message with proper parse_mode auto-detected
         (v83 rendered content starts with [[HTML]] → HTML mode; plain
         text → Markdown mode via smart_text_and_mode)
      3. Include a header banner so admin knows this is the customer's view
      4. Attach a "🔙 Back to Order" button so admin can return
    """
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        oid = int((q.data or "").replace("ac2_userview_", ""))
    except Exception:
        return
    o = _fetch_single_order(oid)
    if not o:
        await _safe_edit(q, "❌ Order not found.")
        return
    dc = (o.get("delivery_content") or "").strip()
    if not dc:
        await _safe_edit(
            q,
            "ℹ️ <i>No delivery content stored for this order.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Order",
                                     callback_data=f"ac2_order_{oid}")
            ]])
        )
        return

    # Banner explaining what admin is looking at
    banner = (
        f"👀 <b>User-Side Delivery Preview — Order #{oid}</b>\n"
        f"<i>This is exactly what the customer received in their chat.</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    # Assemble message: banner + real delivery content, choose parse_mode smartly
    from utils import smart_text_and_mode
    combined = banner + (dc[len("[[HTML]]"):] if dc.startswith("[[HTML]]") else dc)
    # Force HTML mode when content has [[HTML]] prefix OR HTML tags
    import re as _re
    is_html = (dc.startswith("[[HTML]]") or
               _re.search(r"<(?:b|i|u|s|code|pre|tg-emoji|a)\b", dc, flags=_re.I))
    if is_html:
        send_text, send_mode = combined, "HTML"
    else:
        # Convert banner to Markdown too
        md_banner = (
            f"👀 *User-Side Delivery Preview — Order #{oid}*\n"
            f"_This is exactly what the customer received in their chat._\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        send_text, send_mode = smart_text_and_mode(md_banner + dc, "Markdown")

    back_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back to Order",
                             callback_data=f"ac2_order_{oid}")
    ]])
    # Send as a fresh message (not edit) so admin sees the delivery like a
    # real customer would — separate visual block, own copyable code fields.
    try:
        await q.message.reply_text(send_text, parse_mode=send_mode,
                                   reply_markup=back_kb,
                                   disable_web_page_preview=True)
    except Exception as e:
        # HTML parse errors on legacy content → retry as plain text
        try:
            await q.message.reply_text(
                send_text, reply_markup=back_kb,
                disable_web_page_preview=True
            )
        except Exception as e2:
            await q.answer(f"⚠️ Preview failed: {e2}", show_alert=True)


async def ac2_noop_callback(update, context):
    await update.callback_query.answer()


async def ac2_clear_search_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    _SEARCH_CACHE.pop(q.from_user.id, None)
    await q.answer("Cleared ✅")
    rows = _fetch_users_with_completed_orders(search="")
    kb = _build_user_list_kb(rows, page=0, search="")
    await _safe_edit(q, _build_user_list_text(rows, ""),
                     parse_mode="Markdown", reply_markup=kb)


# ---- Search conversation --------------------------------------------
async def ac2_search_entry(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return -1
    await q.answer()
    await q.message.reply_text(
        "🔎 *Search Users*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Type a user id, username, or first-name substring.\n"
        "Reply with `-` to clear, /cancel to abort.",
        parse_mode="Markdown")
    return AC2_SEARCH_TEXT


async def ac2_search_received(update, context):
    if update.effective_user.id != ADMIN_ID:
        return -1
    msg = update.message
    txt = (msg.text or "").strip()
    if txt == "-":
        _SEARCH_CACHE.pop(msg.from_user.id, None)
        await msg.reply_text("🧹 Cleared search.",
                              reply_markup=InlineKeyboardMarkup([[
                                  InlineKeyboardButton("✅ Open Users",
                                                        callback_data="admin_completed_v2")]]))
        return -1
    _SEARCH_CACHE[msg.from_user.id] = txt
    rows = _fetch_users_with_completed_orders(search=txt)
    await msg.reply_text(f"🔎 Filter set → `{txt}` — {len(rows)} user(s) matched.",
                          parse_mode="Markdown",
                          reply_markup=InlineKeyboardMarkup([[
                              InlineKeyboardButton("✅ Open Results",
                                                    callback_data="admin_completed_v2")]]))
    return -1


async def ac2_search_cancel(update, context):
    try:
        await update.message.reply_text("❎ Cancelled.")
    except Exception:
        pass
    return -1
