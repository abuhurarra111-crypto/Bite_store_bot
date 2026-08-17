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
_STATUS_CACHE = {}  # admin_id → status filter (all/delivered/refunded/cancelled)

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
def _fetch_users_with_completed_orders(search: str = "", status_filter: str = "all"):
    """
    Returns list of dicts sorted by most-recent order desc:
      { user_id, name, orders_count, total_spend, last_order_at }

    `search` (optional) matches against user_id, username, first_name
    (case-insensitive substring).
    """
    conn = get_connection()
    c = conn.cursor()
    statuses = _COMPLETED_STATUSES
    if status_filter in ("delivered", "refunded", "cancelled"):
        statuses = {
            "delivered": ("delivered",),
            "refunded": ("refunded",),
            "cancelled": ("cancelled", "rejected"),
        }[status_filter]
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
        WHERE o.status IN ({",".join("?" * len(statuses))})
        GROUP BY o.user_id
        ORDER BY last_order_at DESC, orders_count DESC
    """
    c.execute(sql, statuses)
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


def _completed_summary():
    """v170.17: top summary - total orders, delivered spend, profit, refunds."""
    conn = get_connection(); c = conn.cursor()
    c.execute(f"""SELECT COUNT(*),
                         COALESCE(SUM(CASE WHEN status='delivered' THEN price ELSE 0 END),0),
                         COALESCE(SUM(CASE WHEN status='refunded' THEN price ELSE 0 END),0)
                  FROM orders WHERE status IN ({" ,".join("?"*len(_COMPLETED_STATUSES))})""",
              _COMPLETED_STATUSES)
    total, spend, refunds = c.fetchone()
    conn.close()
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT COALESCE(SUM(o.price - COALESCE(p.cost_price,0) * COALESCE(o.order_qty,1)),0)
                 FROM orders o LEFT JOIN products p ON p.id = o.product_id
                 WHERE o.status='delivered'""")
    profit = c.fetchone()[0] or 0
    conn.close()
    return {
        "total": int(total or 0),
        "spend": float(spend or 0),
        "profit": float(profit or 0),
        "refunds": float(refunds or 0),
    }


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


# ════════════════════════════════════════════════════════════════
# 🆕 v170.17: PAYMENT BADGE (real premium emoji jo admin ne Buy Points
# wale payment buttons par set kiya hai) + PROFIT helper
# ════════════════════════════════════════════════════════════════

# orders.payment_method → payment registry button id (jiska premium emoji
# admin ne set kiya hai btn_label_pay_<id>_<size> mein)
_PAY_BTN_MAP = {
    "binance":           "pay_binance",
    "easypaisa":         "pay_easypaisa",
    "jazzcash":          "pay_jazzcash",
    "usdt_trc20":        "pay_usdt_trc20",
    "usdt_bep20":        "pay_usdt_bep20",
    "bybit_pay":         "pay_bybit_pay",
    "bybit":             "pay_group_bybit",
    "bybit_usdt_trc20":  "pay_bybit_usdt_trc20",
    "bybit_usdt_bep20":  "pay_bybit_usdt_bep20",
    "points":            "pay_pts",
    "wallet":            "pay_pts",
    "telegram_stars":    "pay_stars",
    "free_referral":     None,
    "freebie":           None,
}


def _pay_badge_html(method):
    """🆕 v170.17: payment method ka PREMIUM EMOJI badge (HTML). Admin ne jo
    premium emoji Buy Points ke payment button par set kiya hai wahi use hota
    hai; koi custom nahi to registry default label. Returns HTML string."""
    method = (method or "").strip().lower()
    btn_id = _PAY_BTN_MAP.get(method)
    label = ""
    emoji_id = ""
    if method == "free_referral":
        return "🎁 Free (Referrals)"
    if method == "freebie":
        return "🎁 Freebie"
    if btn_id:
        try:
            from database import get_setting
            # custom premium-emoji label (sab sizes mein ek hi hota hai)
            for size in ("medium", "large", "short", "xl"):
                raw = (get_setting(f"btn_label_{btn_id}_{size}", "") or "").strip()
                if raw and ("<tg-emoji" in raw or raw.startswith("[[HTML]]")):
                    import re as _re
                    m = _re.search(
                        r'<tg-emoji\s+emoji-id=["\'](\d+)["\']\s*>([^<]*)</tg-emoji>',
                        raw, flags=_re.I)
                    if m:
                        emoji_id = m.group(1)
                        fallback = m.group(2)
                        rest = _re.sub(r"<[^>]+>", "", raw.replace("[[HTML]]", ""))
                        rest = _re.sub(r"^\s*[^\w\s]+\uFE0F?\s*", "", rest).strip()
                        label = rest or label
                        if label and fallback:
                            return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji> {label}'
                        if fallback:
                            return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
        except Exception:
            pass
    # fallback: PAYMENT_METHODS label
    try:
        from database import PAYMENT_METHODS
        label = PAYMENT_METHODS.get(method, {}).get("label", "")
        if label:
            return label
    except Exception:
        pass
    return (method or "—").title()


def _order_profit(o) -> float:
    """🆕 v170.17: profit = sold price − product cost (orders table me cost nahi,
    products table se). Returns float."""
    try:
        sold = float(o.get("price") or 0)
        pid = int(o.get("product_id") or 0)
        cost = 0.0
        if pid:
            from database import get_product
            p = get_product(pid)
            if p:
                cost = float((dict(p) if p else {}).get("cost_price") or 0)
        # qty (bulk orders)
        qty = 1
        try:
            qty = int(o.get("order_qty") or 1)
        except Exception:
            qty = 1
        return round((sold - cost) * qty, 4)
    except Exception:
        return 0.0


# ------------------------------------------------------------
# TOP SCREEN — user list
# ------------------------------------------------------------
def _build_user_list_kb(rows, page: int, search: str) -> InlineKeyboardMarkup:
    from utils import name_for_button
    kb = []
    kb.append([InlineKeyboardButton(
        "🔎 Search (user ya order #ID)…" if not search else f"🔎 Search: {search[:20]}",
        callback_data="ac2_search")])
    if search:
        kb.append([InlineKeyboardButton("🧹 Clear Search",
                                         callback_data="ac2_clear_search")])
    # v170.17: status tabs
    kb.append([
        InlineKeyboardButton("📋 All", callback_data="ac2_sf_all"),
        InlineKeyboardButton("✅ Delivered", callback_data="ac2_sf_delivered"),
        InlineKeyboardButton("💸 Refunded", callback_data="ac2_sf_refunded"),
        InlineKeyboardButton("❌ Cancelled", callback_data="ac2_sf_cancelled"),
    ])

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


def _build_user_list_text(rows, search: str, status_filter: str = "all") -> str:
    total = len(rows)
    tail = f"\n🔎 Filter: `{search}`" if search else ""
    try:
        _sm = _completed_summary()
        summary = (
            f"📦 Orders: *{_sm['total']}*  💵 Spend: *${_sm['spend']:.2f}*\n"
            f"📈 Profit: *${_sm['profit']:.2f}*  💸 Refunds: *${_sm['refunds']:.2f}*\n\n"
        )
    except Exception:
        summary = ""
    _sf_lbl = {"all": "All", "delivered": "✅ Delivered", "refunded": "💸 Refunded",
               "cancelled": "❌ Cancelled"}.get(status_filter, "All")
    return (
        "✅ *Completed Orders*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{summary}"
        f"📂 View: *{_sf_lbl}*\n"
        f"👥 Customers: *{total}*\n"
        "📅 Sorted by most-recent order\n"
        f"{tail}\n\n"
        "_Tap any user to see all their purchases + delivered details._"
    )


# ------------------------------------------------------------
# USER SCREEN — orders of that user
# ------------------------------------------------------------
def _build_user_orders_kb(uid: int, orders, page: int) -> InlineKeyboardMarkup:
    """🆕 v170.24: user's orders ab WARRANTY-style render hote hain — GREEN
    (success) premium-emoji buttons + clean product name + price, waisa hi
    jaise 🛡️ Warranty & Refund screen me (user demand). Status ke hisaab se
    color: delivered=green, refunded=blue, cancelled/rejected=red."""
    kb = []
    total = len(orders)
    total_pages = max(1, (total + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * ORDERS_PER_PAGE
    end = start + ORDERS_PER_PAGE
    page_rows = orders[start:end]

    try:
        from button_system import extract_emoji_from_html
        _have_helpers = True
    except Exception:
        _have_helpers = False
    from utils import fmt_price as _fmt_price

    for o in page_rows:
        oid = o['id']
        status = str(o.get('status') or '')
        em = _status_emoji(status)
        raw_name = str(o.get('product_name') or 'Product')
        plain = raw_name
        eid = ""
        if _have_helpers:
            try:
                _eid, _plain = extract_emoji_from_html(raw_name)
                if _plain:
                    plain = _plain
                eid = _eid or ""
            except Exception:
                pass
        plain = (plain or 'Product').strip()[:26]
        price = _fmt_price(o.get('price'))
        label = f"#{oid} {plain} — {price}  {em}"
        style = {
            'delivered': 'success',
            'refunded': 'primary',
            'cancelled': 'danger',
            'rejected': 'danger',
        }.get(status, 'primary')
        # 🆕 v170.24: button MANUALLY build (make_premium_button ka leading
        # emoji-strip `#`/emoji kha jata tha) — taake label + status emoji +
        # premium icon + color sab consistent rahe.
        try:
            if eid:
                kb.append([InlineKeyboardButton(label, icon_custom_emoji_id=eid,
                                                style=style,
                                                callback_data=f"ac2_order_{oid}")])
            else:
                kb.append([InlineKeyboardButton(label, style=style,
                                                callback_data=f"ac2_order_{oid}")])
            continue
        except TypeError:
            pass
        try:
            ak = {"style": style}
            if eid:
                ak["icon_custom_emoji_id"] = eid
            kb.append([InlineKeyboardButton(label, api_kwargs=ak,
                                            callback_data=f"ac2_order_{oid}")])
            continue
        except Exception:
            pass
        kb.append([InlineKeyboardButton(label, callback_data=f"ac2_order_{oid}")])

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
    # 🆕 v170.5: one-tap — sab delivered files (voice/video/pic/doc/.txt) bhejo
    if order.get("status") == "delivered":
        kb.append([InlineKeyboardButton("📥 Get Delivered File(s)",
                                         callback_data=f"ac2_allfiles_{oid}")])
        # v170.17: one-click resend delivered content to CUSTOMER (agar usne
        # delete kar diya ho ya dobara chahiye)
        kb.append([InlineKeyboardButton("📤 Resend to Customer",
                                         callback_data=f"ac2_resend_{oid}")])
    # 🐛 v145: bulk .txt delivery file — re-open / download from Completed Orders
    if order.get("delivery_file_id"):
        kb.append([InlineKeyboardButton("📎 Download Delivery File (.txt)",
                                         callback_data=f"ac2_dlfile_{oid}")])
    # 🆕 v161.20: delivered-items audit — voice/video/pic/file/text ALL listed
    try:
        from database import get_order_deliveries
        _dlvs = get_order_deliveries(oid)
        if _dlvs:
            kb.append([InlineKeyboardButton(f"📦 Delivered Items ({len(_dlvs)})",
                                             callback_data=f"ac2_dlv_{oid}")])
    except Exception:
        pass
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
    # v170.17: payment badge = admin ka set kiya hua PREMIUM EMOJI (Buy Points
    # payment buttons wala). HTML-safe (tg-emoji), escape nahi karte.
    pay = _pay_badge_html(order.get("payment_method"))
    uname = escape_html(order.get("user_name") or "")
    profit = _order_profit(order)
    # 🆕 v170.5: supplier name (ADMIN-ONLY — customer kabhi nahi dekhta). Product
    # ka ext_supplier_id → ext_suppliers.name. Sirf completed_orders (admin view)
    # mein dikhta hai; user-side delivery untouched → no supplier leak.
    supplier_name = ""
    try:
        from database import get_product, get_connection as _gc2
        _p = get_product(order.get("product_id") or 0)
        _esid = int((dict(_p) if _p else {}).get("ext_supplier_id") or 0)
        if _esid:
            _conn2 = _gc2(); _c2 = _conn2.cursor()
            _c2.execute("SELECT name FROM ext_suppliers WHERE id=?", (_esid,))
            _r2 = _c2.fetchone(); _conn2.close()
            if _r2:
                supplier_name = str((dict(_r2) if not isinstance(_r2, dict) else _r2).get("name") or "")
    except Exception:
        supplier_name = ""
    dc = (order.get("delivery_content") or "").strip()
    # 🐛 v104: heal legacy escaped <tg-emoji> markup that v83 renderer
    # accidentally wrote before v104 (see utils.heal_escaped_delivery_content)
    try:
        from utils import heal_escaped_delivery_content
        dc = heal_escaped_delivery_content(dc)
    except Exception:
        pass

    body = (
        f"{em} <b>Order #{order['id']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Product:</b> {pname}\n"
        f"💵 <b>Price:</b> ${price:.2f}\n"
        f"💳 <b>Payment:</b> {pay}\n"
        f"📈 <b>Profit:</b> ${profit:.4g}\n"
        f"📅 <b>When:</b> {dt}\n"
        f"🆔 <b>Order ID:</b> <code>#{order['id']}</code>\n"
        f"🧑 <b>Customer:</b> {uname or ('user ' + str(order.get('user_id')))}\n"
        f"🔖 <b>Status:</b> {order.get('status','?')}\n"
    )
    # v170.17: refund/cancel reason (agar saved ho)
    _ref_reason = (order.get("supplier_failure_reason") or "").strip() or \
                  (order.get("replacement_reason") or "").strip()
    if _ref_reason:
        body += f"⚠️ <b>Reason:</b> {escape_html(_ref_reason[:120])}\n"
    # 🆕 v170.5: supplier name (admin-only)
    if supplier_name:
        body += f"🏭 <b>Supplier:</b> {escape_html(supplier_name)}\n"

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
    sf = _STATUS_CACHE.get(q.from_user.id, "all")
    rows = _fetch_users_with_completed_orders(search=search, status_filter=sf)
    kb = _build_user_list_kb(rows, page=0, search=search)
    await _safe_edit(q, _build_user_list_text(rows, search, sf),
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
    sf = _STATUS_CACHE.get(q.from_user.id, "all")
    rows = _fetch_users_with_completed_orders(search=search, status_filter=sf)
    kb = _build_user_list_kb(rows, page=page, search=search)
    await _safe_edit(q, _build_user_list_text(rows, search, sf),
                     parse_mode="Markdown", reply_markup=kb)


async def ac2_sf_callback(update, context):
    """v170.17: status filter tabs (all/delivered/refunded/cancelled)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        sf = (q.data or "").replace("ac2_sf_", "")
    except Exception:
        sf = "all"
    if sf not in ("all", "delivered", "refunded", "cancelled"):
        sf = "all"
    _STATUS_CACHE[q.from_user.id] = sf
    search = _SEARCH_CACHE.get(q.from_user.id, "")
    rows = _fetch_users_with_completed_orders(search=search, status_filter=sf)
    kb = _build_user_list_kb(rows, page=0, search=search)
    await _safe_edit(q, _build_user_list_text(rows, search, sf),
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


async def ac2_resend_callback(update, context):
    """v170.17: resend delivered content (file/text) to the CUSTOMER."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("📤 Resending…")
    try:
        oid = int((q.data or "").replace("ac2_resend_", ""))
    except Exception:
        return
    o = _fetch_single_order(oid)
    if not o or o.get("status") != "delivered":
        await q.answer("⚠️ Not a delivered order", show_alert=True)
        return
    try:
        uid = int(o.get("user_id") or 0)
        dc = (o.get("delivery_content") or "").strip()
        # file delivery (delivery_file_id)
        from database import get_order, get_order_deliveries
        full = get_order(oid)
        sent_any = False
        if full and full.get("delivery_file_id"):
            try:
                await context.bot.send_document(
                    uid, document=str(full["delivery_file_id"]),
                    caption=f"📦 <i>Your delivery — Order #{oid}</i>",
                    parse_mode="HTML")
                sent_any = True
            except Exception:
                pass
        if dc:
            try:
                from utils import smart_text_and_mode
                _txt, _mode = smart_text_and_mode(dc, "HTML")
                await context.bot.send_message(uid, _txt, parse_mode=_mode)
                sent_any = True
            except Exception:
                pass
        if not sent_any:
            await q.answer("⚠️ No stored delivery to resend", show_alert=True)
            return
        await q.answer("✅ Resent to customer", show_alert=True)
    except Exception as e:
        await q.answer(f"❌ {e}", show_alert=True)


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
    # 🐛 v104: heal any legacy escaped <tg-emoji> markup pre-display
    try:
        from utils import heal_escaped_delivery_content
        dc = heal_escaped_delivery_content(dc)
    except Exception:
        pass
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
    # v170.17: agar admin ne ORDER ID (#123) di to direct us order par jao
    _digits = txt.lstrip("#").strip()
    if _digits.isdigit():
        _o = _fetch_single_order(int(_digits))
        if _o:
            await msg.reply_text(
                _build_order_detail_text(_o), parse_mode="HTML",
                reply_markup=_build_order_detail_kb(_o),
                disable_web_page_preview=True)
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


async def ac2_allfiles_callback(update, context):
    """🆕 v170.5: one tap — send EVERY file that was delivered to the customer
    (bulk .txt delivery_file_id + sab order_deliveries items jo file_id rakhte
    hain — photo/video/voice/audio/document)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        oid = int(q.data.replace("ac2_allfiles_", ""))
    except Exception:
        return
    from database import get_order, get_order_deliveries
    o = get_order(oid)
    if not o:
        await q.answer("Order not found", show_alert=True); return
    sent = 0
    caption = f"📥 <i>Delivered file(s) — Order #{oid}</i>"
    # 1) bulk .txt file (orders.delivery_file_id) — sirf real file id bhejo
    _dfid = (o.get("delivery_file_id") or "").strip()
    if _dfid and len(_dfid) > 6:
        try:
            await context.bot.send_document(q.from_user.id,
                                            document=str(_dfid),
                                            caption=caption, parse_mode="HTML")
            sent += 1
        except Exception as e:
            logging.getLogger(__name__).warning(f"[ac2_allfiles] txt send fail: {e}")
    # 2) individual delivered items with file_id
    for d in get_order_deliveries(oid):
        kind = d.get("kind") or ""
        fid = d.get("file_id") or ""
        if not fid:
            continue
        try:
            if kind == "photo":
                await context.bot.send_photo(q.from_user.id, photo=fid, caption=caption, parse_mode="HTML")
            elif kind == "video":
                await context.bot.send_video(q.from_user.id, video=fid, caption=caption, parse_mode="HTML")
            elif kind == "voice":
                await context.bot.send_voice(q.from_user.id, voice=fid)
            elif kind == "audio":
                await context.bot.send_audio(q.from_user.id, audio=fid, caption=caption, parse_mode="HTML")
            else:
                await context.bot.send_document(q.from_user.id, document=fid, caption=caption, parse_mode="HTML")
            sent += 1
        except Exception as e:
            logging.getLogger(__name__).warning(f"[ac2_allfiles] item send fail: {e}")
    # 🐛 v170.8 FIX: jab koi FILE nahi (text-only delivery) to customer ka
    # DELIVERED CONTENT text bhejo — pehle kuch bhi nahi aata tha (sent=0).
    if sent == 0:
        dc = (o.get("delivery_content") or "").strip()
        if dc:
            try:
                from utils import smart_text_and_mode
                _txt, _mode = smart_text_and_mode(dc, "HTML")
                await context.bot.send_message(
                    q.from_user.id, _txt, parse_mode=_mode,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to Order",
                                             callback_data=f"ac2_order_{oid}")]]))
                sent += 1
            except Exception as e:
                logging.getLogger(__name__).warning(f"[ac2_allfiles] text send fail: {e}")
    if sent == 0:
        await q.answer("No delivered files stored for this order", show_alert=True)


async def ac2_dlfile_callback(update, context):
    """🐛 v145: admin downloads the bulk .txt delivery file from Completed Orders."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        oid = int(q.data.replace("ac2_dlfile_", ""))
        from database import get_order
        o = get_order(oid)
        if not o or not o.get("delivery_file_id"):
            await q.answer("No file for this order", show_alert=True); return
        await context.bot.send_document(
            q.from_user.id,
            document=str(o["delivery_file_id"]),
            caption=f"📎 *Delivery file — Order #{oid}*",
            parse_mode="Markdown")
    except Exception as e:
        await q.answer(f"❌ {str(e)[:60]}", show_alert=True)


# ─────────────────────────────────────────────────────────────
# 🆕 v161.20 — DELIVERED ITEMS AUDIT VIEW
# Shows EVERYTHING that was delivered for an order (text / document /
# photo / video / voice / audio) — whatever the customer got, the admin
# sees it here and can re-open any media file.
# ─────────────────────────────────────────────────────────────
_KIND_ICON = {
    "text": "📝", "document": "📄", "photo": "🖼️", "video": "🎬",
    "voice": "🎤", "audio": "🎵", "sticker": "🩹",
}


def _esc_html(s: str) -> str:
    s = str(s or "")
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


async def ac2_dlv_callback(update, context):
    """List all delivered items for an order."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        oid = int(q.data.replace("ac2_dlv_", ""))
    except Exception:
        return
    from database import get_order_deliveries, get_order
    o = get_order(oid)
    if not o:
        await _safe_edit(q, "❌ Order not found.")
        return
    dlvs = get_order_deliveries(oid)
    if not dlvs:
        await _safe_edit(q, "ℹ️ <i>No delivered items logged for this order.</i>",
                         parse_mode="HTML",
                         reply_markup=InlineKeyboardMarkup([[
                             InlineKeyboardButton("🔙 Back to Order",
                                                  callback_data=f"ac2_order_{oid}")]]))
        return
    lines = [
        f"📦 <b>Delivered Items — Order #{oid}</b>",
        f"<i>Everything sent to the customer:</i>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    kb = []
    for d in dlvs:
        kind = d.get("kind") or "text"
        icon = _KIND_ICON.get(kind, "📦")
        fname = (d.get("file_name") or "")[:24]
        if d.get("file_id"):
            label = f"{icon} {kind.title()} · {fname or 'file'}"
            kb.append([InlineKeyboardButton(f"📂 Open: {label}",
                                            callback_data=f"ac2_dlvopen_{d['id']}")])
        else:
            preview = (d.get("content") or "").strip().replace("\n", " ")[:60]
            label = f"{icon} {kind.title()}: {preview or '(empty)'}"
        lines.append(f"{icon} <b>{kind.title()}</b>"
                     + (f" · {_esc_html(fname)}" if fname else "")
                     + f" · <code>#{d.get('seq')}</code>")
        if not d.get("file_id"):
            content = (d.get("content") or "").strip()
            if content:
                lines.append(f"    ↳ <i>{_esc_html(content[:120])}</i>"
                             + ("…" if len(content) > 120 else ""))
            else:
                lines.append("    ↳ <i>(no text)</i>")
    kb.append([InlineKeyboardButton("🔙 Back to Order",
                                    callback_data=f"ac2_order_{oid}")])
    await _safe_edit(q, "\n".join(lines), parse_mode="HTML",
                     reply_markup=InlineKeyboardMarkup(kb))


async def ac2_dlvopen_callback(update, context):
    """Re-open / re-download one specific delivered media item."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        did = int(q.data.replace("ac2_dlvopen_", ""))
    except Exception:
        return
    from database import get_connection
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM order_deliveries WHERE id=?", (did,))
    d = c.fetchone(); conn.close()
    if not d:
        await q.answer("Item not found", show_alert=True); return
    d = dict(d)
    oid = d.get("order_id")
    kind = d.get("kind") or "document"
    fid = d.get("file_id") or ""
    content = (d.get("content") or "").strip()
    caption = f"📦 <i>Delivered item #{d.get('seq')} — Order #{oid}</i>"
    if content:
        caption += f"\n<i>{content[:200]}</i>"
    back_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Delivered Items",
                             callback_data=f"ac2_dlv_{oid}"),
        InlineKeyboardButton("🔙 Order", callback_data=f"ac2_order_{oid}"),
    ]])
    if not fid:
        # text-only item → just re-send the content
        await _safe_edit(q, f"<b>📝 Delivered text — Order #{oid}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{content or '(empty)'}",
                         parse_mode="HTML", reply_markup=back_kb)
        return
    try:
        if kind == "photo":
            await context.bot.send_photo(q.from_user.id, photo=fid, caption=caption,
                                         parse_mode="HTML", reply_markup=back_kb)
        elif kind == "video":
            await context.bot.send_video(q.from_user.id, video=fid, caption=caption,
                                         parse_mode="HTML", reply_markup=back_kb)
        elif kind == "voice":
            await context.bot.send_voice(q.from_user.id, voice=fid, caption=caption,
                                         parse_mode="HTML", reply_markup=back_kb)
        elif kind == "audio":
            await context.bot.send_audio(q.from_user.id, audio=fid, caption=caption,
                                         parse_mode="HTML", reply_markup=back_kb)
        else:
            await context.bot.send_document(q.from_user.id, document=fid, caption=caption,
                                            parse_mode="HTML", reply_markup=back_kb)
    except Exception as e:
        await q.answer(f"❌ Could not re-open: {str(e)[:70]}", show_alert=True)
