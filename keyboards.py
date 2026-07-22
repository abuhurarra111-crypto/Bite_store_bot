# ============================================
# ⌨️ KEYBOARDS (with Button Size customization)
# ============================================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from button_system import decorate
from utils import get_product_delivery_mode, get_product_mode_tag, build_manual_order_whatsapp_url

# 🆕 v40: Per-button visual styler (size / align / padding)
try:
    from button_system import style_label as _bs_style_label
except Exception:
    def _bs_style_label(key, label):  # graceful fallback
        return label


def _apply_styler(key, label):
    """Wrapper — applies admin's per-button visual override (if any)."""
    try:
        return _bs_style_label(key, label) if label else label
    except Exception:
        return label

# 🆕 v37: i18n mapping for registry buttons
# btn_id → i18n translation key
_BTN_I18N_MAP = {
    "main_shop":         "menu_shop",
    "main_points":       "menu_buy_points",
    "main_account":      "menu_my_account",
    "main_orders":       "menu_my_orders",
    "main_transactions": "menu_transactions",
    "main_referral":     "menu_referral",
    "main_admin":        "menu_admin",
    # 🆕 v46: newly-registered main buttons
    "main_support":      "menu_support",
    "main_warranty":     "menu_warranty",
    "main_reviews":      "menu_reviews",
    "main_loyalty":      "menu_loyalty",
    "main_language":     "menu_language",
}

def _translate_btn_label(btn_id, default_label, user_id=None):
    """Translate a registry button label if (a) no admin override exists
       AND (b) we have an i18n key for it AND (c) user lang != English."""
    try:
        from i18n import t, get_user_lang
        from database import get_setting
        # If admin has set a custom label for this size, respect it
        size = _get_size()
        custom = get_setting(f"btn_label_{btn_id}_{size}", "")
        if custom:
            return default_label  # admin override wins
        key = _BTN_I18N_MAP.get(btn_id)
        if not key:
            return default_label
        lang = get_user_lang(user_id) if user_id else "en"
        if lang == "en":
            return default_label
        return t(key, lang=lang)
    except Exception:
        return default_label


# ════════════════════════════════════════════
# 🆕 BUTTON SIZE HELPER
# ════════════════════════════════════════════
# Sizes: 'small' (3-4/row, emoji only)
#        'medium' (2/row, emoji + short text) — DEFAULT
#        'large' (2/row, emoji + full text)
#        'xl' (1/row, full label + extras)

def _get_size():
    """Get current button size from DB. Default: medium"""
    try:
        from database import get_setting
        s = get_setting("button_size", "medium").lower().strip()
        return s if s in ("small", "medium", "large", "xl", "full") else "medium"
    except Exception:
        return "medium"


def _make_btn(label, *, callback_data=None, url=None, style=None):
    """🆕 v45: ALL inline buttons go through this helper so any label that
    contains a [[HTML]]<tg-emoji>...</tg-emoji> sentinel automatically
    gets `icon_custom_emoji_id` wired up on the resulting button.
    🎨 v46: optional `style` (primary/success/danger) = button background color.
    """
    style = (style or "").strip().lower() or None
    if style not in ("primary", "success", "danger"):
        style = None
    try:
        from button_system import make_premium_button
        if style or (isinstance(label, str) and ("[[HTML]]" in label or "<tg-emoji" in label.lower())):
            return make_premium_button(label, style=style, callback_data=callback_data, url=url)
    except Exception:
        pass
    if url:
        return InlineKeyboardButton(label, url=url)
    return InlineKeyboardButton(label, callback_data=callback_data)


def auto_product_style(product):
    """🎨 v46: Decide a product button's background color automatically.

    Returns 'danger' (red) / 'primary' (blue) / 'success' (green) / None.
    Controlled by the admin toggle `auto_product_colors` (Customization).

    Rules (admin requested):
      • Out of stock           → 🔴 danger (red)
      • Manual delivery        → 🔵 primary (blue)
      • Auto delivery + stock  → 🟢 success (green)

    Colors only render for bot owners with Telegram Premium (Bot API 9.4).
    """
    try:
        from database import get_toggle
        if get_toggle("auto_product_colors", "0") != "1":
            return None
    except Exception:
        return None
    try:
        p = product if isinstance(product, dict) else dict(product)
    except Exception:
        return None
    try:
        stock = int(p.get("stock", 0) or 0)
    except Exception:
        stock = 0
    dmode = (p.get("delivery_mode", "auto") or "auto").lower()
    if stock <= 0:
        return "danger"      # 🔴 out of stock
    if dmode == "manual":
        return "primary"     # 🔵 manual delivery
    return "success"         # 🟢 auto delivery, in stock


def _btn(short, medium, large, xl, callback_data=None, url=None):
    """Build a single button label based on size + apply menu style decoration.
    short = emoji or 1-char
    medium = emoji + short text
    large = emoji + full text
    xl = full label with extras
    """
    size = _get_size()
    label = {"small": short, "medium": medium, "large": large, "xl": xl, "full": xl}.get(size, medium)
    # 🎨 Apply current menu style decoration
    label = decorate(label)
    return _make_btn(label, callback_data=callback_data, url=url)


def _rb(btn_id, callback_data=None, url=None, user_id=None):
    """🆕 Registry button — uses admin override + hide checks.
    Returns None if button is hidden (caller filters None out).
    🆕 v37: user_id enables i18n translation when admin didn't override.
    🆕 v45: premium-emoji-aware — admin-saved [[HTML]] labels render as
            button icons via make_premium_button().
    """
    from button_system import BUTTONS, get_button_label, resolve_button_style
    size = _get_size()
    label = get_button_label(btn_id, size)
    if label is None:
        return None  # hidden
    # 🆕 v37: i18n
    label = _translate_btn_label(btn_id, label, user_id=user_id)
    label = decorate(label)
    # 🆕 v40: per-button visual styler override
    label = _apply_styler(f"reg_{btn_id}", label)
    # 🎨 v46: background color = per-button override OR group/location default
    try:
        style = resolve_button_style(btn_id)
    except Exception:
        style = ""
    # Use callback from registry if not overridden
    if callback_data is None and url is None:
        info = BUTTONS.get(btn_id, {})
        callback_data = info.get("callback")
    return _make_btn(label, callback_data=callback_data, url=url, style=style)


def _row(*btns):
    """Build a row, filtering out None (hidden) buttons.
    Returns None if entire row is empty."""
    row = [b for b in btns if b is not None]
    return row if row else None


def _per_row():
    """How many buttons fit in one row based on size"""
    return {"small": 3, "medium": 2, "large": 2, "xl": 1, "full": 1}.get(_get_size(), 2)


def _arrange(buttons):
    """Arrange list of buttons into rows based on current size"""
    n = _per_row()
    return [buttons[i:i + n] for i in range(0, len(buttons), n)]


def _apply_screen_pad_markup(markup, location):
    """📐 v46: widen EVERY button on a screen by the location's screen-padding.
    Rebuilds each InlineKeyboardButton preserving icon/style/callback/url etc.
    Skips the persistent 🔙 back/return rows so navigation stays compact? No —
    user wants the WHOLE screen padded, so we pad every button uniformly.
    """
    try:
        from button_system import get_screen_pad, apply_screen_pad
        if get_screen_pad(location) <= 0:
            return markup
    except Exception:
        return markup
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    new_rows = []
    for row in markup.inline_keyboard:
        new_row = []
        for b in row:
            try:
                new_text = apply_screen_pad(b.text or "", location)
                if new_text == (b.text or ""):
                    new_row.append(b); continue
                kw = {}
                for attr in ("callback_data", "url", "web_app", "login_url",
                             "switch_inline_query", "switch_inline_query_current_chat",
                             "copy_text", "pay", "callback_game",
                             "icon_custom_emoji_id", "style"):
                    v = getattr(b, attr, None)
                    if v is not None:
                        kw[attr] = v
                try:
                    new_row.append(InlineKeyboardButton(new_text, **kw))
                except TypeError:
                    # older PTB: push unknown fields through api_kwargs
                    ak = {}
                    for k in ("icon_custom_emoji_id", "style"):
                        if k in kw:
                            ak[k] = kw.pop(k)
                    new_row.append(InlineKeyboardButton(new_text, api_kwargs=ak, **kw))
            except Exception:
                new_row.append(b)
        new_rows.append(new_row)
    return InlineKeyboardMarkup(new_rows)


# ════════════════════════════════════════════
# 📋 PERSISTENT KEYBOARD
# ════════════════════════════════════════════
def persistent_menu():
    # 🆕 v78: 📚 How to Use button next to 🏠 Main Menu on the persistent
    # reply keyboard (always visible at the bottom of the chat).
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🏠 Main Menu"), KeyboardButton("📚 How to Use")]],
        resize_keyboard=True, is_persistent=True
    )


# ════════════════════════════════════════════
# 🏠 MAIN MENU
# ════════════════════════════════════════════
def main_menu_keyboard(is_admin=False, user_id=None):
    """🎨 v92: uses the layout engine (50 layouts).
    If the layout engine isn't available, falls back to the original
    registry-based render for safety."""
    # 🆕 v92: Try layout engine first
    try:
        from main_menu_layouts import render_layout
        return _apply_screen_pad_markup(
            render_layout(is_admin=is_admin, user_id=user_id), "main"
        )
    except Exception as _le:
        import logging
        logging.getLogger(__name__).warning(f"[v92] layout engine fail, using classic: {_le}")

    # ── Fallback: original v46 registry-based render ──
    # 🆕 Phase C: Use ordered ids (admin can reorder)
    from button_system import get_ordered_button_ids
    # 🆕 v37: i18n for new buttons
    try:
        from i18n import t, get_user_lang
        lang = get_user_lang(user_id) if user_id else "en"
    except Exception:
        lang = "en"
        def t(k, **kw): return k

    all_ordered = get_ordered_button_ids("main")
    # Exclude admin button (handled separately)
    # 🆕 v46: support/warranty/reviews/loyalty/language are now registry buttons
    # too, so they render via _rb() (rename / hide / color all work on them).
    ids = [bid for bid in all_ordered if bid != "main_admin"]
    buttons = [_rb(bid, user_id=user_id) for bid in ids]
    buttons = [b for b in buttons if b is not None]  # filter hidden
    kb = _arrange(buttons) if buttons else []
# 🆕 Phase B: append admin's custom buttons
    kb.extend(_custom_buttons_for("main"))
    if is_admin:
        admin_btn = _rb("main_admin", user_id=user_id)
        if admin_btn:
            kb.append([admin_btn])
    # 📐 v46: apply whole-screen padding (admin can widen the entire main menu)
    return _apply_screen_pad_markup(InlineKeyboardMarkup(kb), "main")


# ════════════════════════════════════════════
# 🛒 SHOP — PRODUCTS LIST
# ════════════════════════════════════════════
def all_products_keyboard(products, page=1, per_page=10, user=None, filter_mode="all"):
    """🆕 v59: Added `filter_mode` param — renders Filter buttons (All/Available/
    Unavailable) on bottom row so user can switch between in-stock and out-of-stock
    views. `filter_mode` is one of 'all'/'available'/'unavailable'.
    """
    total = len(products)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    page_prods = products[start:start + per_page]
    size = _get_size()
    # 🆕 v42: Admin toggle — show/hide the default 🛍️ emoji prefix on product names
    try:
        from database import get_toggle as _gt, get_setting as _gs
        show_emoji = _gt("show_product_emoji", "1") == "1"
        emoji_char = _gs("product_emoji", "🛍️") or "🛍️"
    except Exception:
        show_emoji = True
        emoji_char = "🛍️"
    prod_emoji = f"{emoji_char} " if show_emoji else ""
    # 🆕 v45: PREMIUM EMOJI in product name → render as button ICON
    #   - raw_name keeps the original [[HTML]]<tg-emoji>...</tg-emoji> form
    #   - make_premium_button() extracts the emoji_id and uses it as the
    #     button's icon_custom_emoji_id; the leftover text goes into label.
    try:
        from utils import name_for_button as _nfb
        from button_system import make_premium_button, extract_emoji_from_html
    except Exception:
        _nfb = lambda x: x
        make_premium_button = None
        extract_emoji_from_html = None
    kb = []
    for p in page_prods:
        s = p['stock']
        p = dict(p)
        raw_name = p.get('name', '') or ''
        # Detect premium emoji in name (if any) — store its id for the button
        if extract_emoji_from_html:
            name_emoji_id, plain_name = extract_emoji_from_html(raw_name)
        else:
            name_emoji_id, plain_name = "", _nfb(raw_name)
        # 🔧 BUGFIX (double emoji): if the name has a PREMIUM emoji it renders as
        # the button icon (and extract_emoji_from_html already removed its
        # fallback char from plain_name). Drop the default 🛍️ prefix too so the
        # leading slot belongs to the premium icon — otherwise two emojis show.
        this_prod_emoji = "" if name_emoji_id else prod_emoji
        # Use plain_name everywhere a text label is needed
        p['name'] = plain_name

        if size == "small":
            label = f"{this_prod_emoji}{p['name'][:18]}" if s > 0 else f"❌ {p['name'][:18]}"
        elif size == "medium":
            label = f"{this_prod_emoji}{p['name']} — ${p['price']:.2f}" if s > 0 else f"{this_prod_emoji}{p['name']} ❌"
        elif size == "large":
            label = f"{this_prod_emoji}{p['name']} [{s}] — ${p['price']:.2f}" if s > 0 else f"{this_prod_emoji}{p['name']} ❌ — ${p['price']:.2f}"
        else:
            label = f"{this_prod_emoji}{p['name']} [Stock: {s}] — ${p['price']:.2f}" if s > 0 else f"{this_prod_emoji}{p['name']} ❌ Out of Stock — ${p['price']:.2f}"
        from button_system import is_styled
        if is_styled(f"prod_{p['id']}"):
            label = _apply_styler(f"prod_{p['id']}", label)
        else:
            label = _apply_styler("shop_product", label)

        # 🎨 v46: auto background color (out=red / manual=blue / auto=green)
        _pstyle = auto_product_style(p)
        # 🆕 v45: If name has premium emoji, ALSO use icon_custom_emoji_id
        if (name_emoji_id or _pstyle) and make_premium_button:
            kb.append([make_premium_button(label, emoji_id=(name_emoji_id or None),
                                            style=_pstyle,
                                            callback_data=f"prod_{p['id']}")])
        else:
            kb.append([InlineKeyboardButton(label, callback_data=f"prod_{p['id']}")])

    # 🆕 v52: Pagination buttons now editable via Customization → 🎨 Buttons → Navigation
    nav = []
    if page > 1:
        _b = _rb("nav_shop_prev_page", callback_data=f"page_{page - 1}")
        if _b:
            nav.append(_b)
        else:
            plabel = "⬅️" if size == "small" else "⬅️ Previous"
            nav.append(InlineKeyboardButton(_apply_styler("shop_pagination", plabel),
                                             callback_data=f"page_{page - 1}"))
    if page < total_pages:
        _b = _rb("nav_shop_next_page", callback_data=f"page_{page + 1}")
        if _b:
            nav.append(_b)
        else:
            nlabel = "➡️" if size == "small" else "Next ➡️"
            nav.append(InlineKeyboardButton(_apply_styler("shop_pagination", nlabel),
                                             callback_data=f"page_{page + 1}"))
    if nav:
        kb.append(nav)

    # 🆕 v38: Inject custom buttons for shop screen
    try:
        kb.extend(_custom_buttons_for("shop"))
    except Exception:
        pass

    # 🆕 v59: Filter buttons row (All / Available / Out of Stock).
    # Active filter prefixed with • marker. Tapping switches view.
    fr = []
    def _f_label(mode, txt):
        return f"• {txt} •" if filter_mode == mode else txt
    fr.append(InlineKeyboardButton(_f_label("all", "📋 All"),
                                    callback_data="shopfilter_all"))
    fr.append(InlineKeyboardButton(_f_label("available", "✅ Available"),
                                    callback_data="shopfilter_available"))
    fr.append(InlineKeyboardButton(_f_label("unavailable", "❌ Out of Stock"),
                                    callback_data="shopfilter_unavailable"))
    kb.append(fr)

    # 🆕 v52: Home + Buy Points now editable via Navigation group too
    bottom_row = []
    _b = _rb("nav_shop_home", callback_data="main_menu")
    if _b:
        bottom_row.append(_b)
    else:
        home_lbl = _apply_styler("shop_home",
                      {"small": "🏠", "medium": "🏠 Home", "large": "🏠 Home",
                       "xl": "🏠 Back to Main Menu"}.get(size, "🏠 Home"))
        bottom_row.append(InlineKeyboardButton(home_lbl, callback_data="main_menu"))
    pts_lbl = _apply_styler("shop_buy_points",
                  {"small": "💎", "medium": "💎 Points", "large": "💎 Buy Points",
                   "xl": "💎 Buy Points"}.get(size, "💎 Buy Points"))
    bottom_row.append(InlineKeyboardButton(pts_lbl, callback_data="buy_points"))
    kb.append(bottom_row)
    return InlineKeyboardMarkup(kb), page, total_pages


def product_detail_keyboard(product, user=None):
    pid = product['id'] if isinstance(product, dict) or hasattr(product, '__getitem__') else product
    # 🔧 BUG FIX: `'stock' in product` on a sqlite3.Row checks VALUES not keys.
    # Use a key list that works for both dict and Row.
    _pkeys = product.keys() if hasattr(product, 'keys') else (product if isinstance(product, dict) else [])
    stock = product['stock'] if (hasattr(product, '__getitem__') and 'stock' in _pkeys) else 1000
    size = _get_size()
    rows = []
    if stock > 0:
        buy_lbl = _apply_styler("prod_buy", {"small": "🛒", "medium": "🛒 Buy",
                     "large": "🛒 Buy Now", "xl": "🛒 Buy Now — Order this item"}.get(size, "🛒 Buy"))
        buyx_lbl = _apply_styler("prod_buyx", {"small": "🛒×", "medium": "🛒× Buy Multiple",
                      "large": "🛒× Buy Multiple (Bulk)", "xl": "🛒× Buy Multiple — Bulk order"}.get(size, "🛒× Buy Multiple"))
        rows.append([InlineKeyboardButton(decorate(buy_lbl), callback_data=f"buy_{pid}")])
        rows.append([InlineKeyboardButton(decorate(buyx_lbl), callback_data=f"buyx_{pid}")])
    else:
        req_lbl = _apply_styler("prod_req", "🔔 Notify Me When Available")
        rows.append([InlineKeyboardButton(decorate(req_lbl), callback_data=f"req_restock_{pid}")])
        
    rev_lbl = _apply_styler("prod_review", "⭐ View Reviews")
    rows.append([InlineKeyboardButton(rev_lbl, callback_data=f"prodrev_{pid}")])

    # 🆕 v70: Share Product button — hidden if Free-via-Referrals is enabled
    try:
        from loyalty_extras import get_share_button
        _share_btn = get_share_button(pid)
        if _share_btn is not None:
            rows.append([_share_btn])
    except Exception:
        pass

    # 🆕 v47: Free-via-Referrals button (only when enabled for this product and
    # user has not claimed it yet). `user` may be a sqlite3.Row, int, or None.
    try:
        uid = None
        if user is not None:
            if isinstance(user, int):
                uid = user
            else:
                # Try (in order): user.id (Telegram User obj), user["id"] (dict),
                # user["user_id"] (sqlite Row), fall back to None.
                for accessor in (
                    lambda x: int(x.id),
                    lambda x: int(x["id"]),
                    lambda x: int(x["user_id"]),
                ):
                    try:
                        uid = accessor(user); break
                    except Exception:
                        continue
        if uid:
            from handlers_free_claim import get_free_claim_button
            fc_btn = get_free_claim_button(product, uid)
            if fc_btn is not None:
                rows.append([fc_btn])
    except Exception:
        pass

    # 🆕 v38: Inject custom buttons for product_detail screen (shown on every product)
    try:
        rows.extend(_custom_buttons_for("product_detail"))
    except Exception:
        pass
    # 🆕 v52: nav buttons now editable via Customization → 🎨 Buttons → 🔙 Navigation Buttons
    _nav_row = []
    _b = _rb("nav_prod_back_shop", callback_data="shop")
    if _b: _nav_row.append(_b)
    _b = _rb("nav_prod_home", callback_data="main_menu")
    if _b: _nav_row.append(_b)
    if _nav_row:
        rows.append(_nav_row)
    return InlineKeyboardMarkup(rows)


# ════════════════════════════════════════════
# 💳 PAYMENT METHODS
# ════════════════════════════════════════════
def payment_method_keyboard(pid, qty=1):
    kb = []
    # 🆕 v80: Check payment method enable/disable toggle. Disabled methods are
    # hidden from checkout entirely (customer only sees enabled ones).
    from database import is_payment_enabled
    # 🆕 v57: 'Pay with Points' is now a real registry button (pay_pts) so admin
    # can rename it / change color / add premium emoji from Customization →
    # 🎨 Buttons → 💳 Payment Methods.
    if is_payment_enabled("points"):
        b = _rb("pay_pts", callback_data=f"pay_pts_{pid}_{qty}")
        if b:
            kb.append([b])
        else:
            # Fallback (button hidden via admin) — keep original hardcoded version
            kb.append([InlineKeyboardButton("💎 Pay with Points (Wallet)",
                                            callback_data=f"pay_pts_{pid}_{qty}")])
    if is_payment_enabled("binance"):
        b = _rb("pay_binance", callback_data=f"pay_binance_{pid}_{qty}")
        if b: kb.append([b])
    if is_payment_enabled("easypaisa"):
        b = _rb("pay_easypaisa", callback_data=f"pay_easy_{pid}_{qty}")
        if b: kb.append([b])
    if is_payment_enabled("jazzcash"):
        b = _rb("pay_jazzcash", callback_data=f"pay_jazz_{pid}_{qty}")
        if b: kb.append([b])
    # 🆕 v38: Inject custom buttons for payment screen
    try:
        kb.extend(_custom_buttons_for("payment"))
    except Exception:
        pass
    # 🆕 v52: nav button editable via Customization → 🎨 Buttons → Navigation
    _b = _rb("nav_pay_cancel", callback_data="shop")
    if _b: kb.append([_b])
    return InlineKeyboardMarkup(kb)


# ════════════════════════════════════════════
# 🔙 COMMON BACK BUTTONS
# ════════════════════════════════════════════
def back_btn(back_to=None, location=None):
    """🆕 v38: Optional `location` parameter injects custom buttons for that screen
    above the back button. Used for adding custom buttons to my_account, shop, etc."""
    rows = []
    if location:
        try:
            rows.extend(_custom_buttons_for(location))
        except Exception:
            pass
    # 🆕 v52: editable nav button (admin overrides apply automatically)
    _cb = back_to or "go_back"
    _bid = "nav_back_main" if _cb == "main_menu" else "nav_back_generic"
    _b = _rb(_bid, callback_data=_cb)
    if _b:
        rows.append([_b])
    return InlineKeyboardMarkup(rows)


# 🆕 Inline cancel button for conversation prompts
def inline_cancel_btn():
    """Cancel button that ends ANY active conversation"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")]])


def cancel_back_btn():
    """🔧 BUG #2 FIX: Cancel now properly marks pending order as cancelled
    🆕 v52: both buttons now editable via Customization → 🎨 Buttons → Navigation."""
    row = []
    _b = _rb("nav_order_cancel", callback_data="cancel_order")
    if _b: row.append(_b)
    _b = _rb("nav_order_home", callback_data="main_menu")
    if _b: row.append(_b)
    return InlineKeyboardMarkup([row]) if row else InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_order"),
         InlineKeyboardButton("🏠 Home", callback_data="main_menu")]
    ])


# ════════════════════════════════════════════
# 💎 POINTS
# ════════════════════════════════════════════
def buy_points_keyboard():
    size = _get_size()
    # Points amount buttons
    if size == "small":
        per_row = 4
    elif size == "xl":
        per_row = 2
    elif size == "full":
        per_row = 1
    else:
        per_row = 3
    amounts = [("💎 $1", "pts_1"), ("💎 $5", "pts_5"), ("💎 $10", "pts_10"), ("💎 $25", "pts_25")]
    amt_btns = [InlineKeyboardButton(lbl, callback_data=cd) for lbl, cd in amounts]
    kb = [amt_btns[i:i + per_row] for i in range(0, len(amt_btns), per_row)]
    kb.append([_btn("💎", "💎 Custom", "💎 Custom Amount", "💎 Custom Amount — Type your own", callback_data="pts_custom")])
    # 🆕 v52: editable nav button
    _b = _rb("nav_points_back", callback_data="main_menu")
    if _b: kb.append([_b])
    return InlineKeyboardMarkup(kb)


def points_payment_keyboard(amt):
    """🆕 v102 FIX: only show payment methods admin has enabled.
    Bug: EasyPaisa/JazzCash still shown here even when admin turned them
    OFF from Payment Methods panel → users clicked → got 'unavailable'.
    """
    try:
        from database import is_payment_enabled as _ipe
    except Exception:
        _ipe = lambda m: True   # fail-open
    kb = []
    if _ipe("binance"):
        b = _rb("pay_binance", callback_data=f"ptspay_binance_{amt}")
        if b: kb.append([b])
    if _ipe("easypaisa"):
        b = _rb("pay_easypaisa", callback_data=f"ptspay_easy_{amt}")
        if b: kb.append([b])
    if _ipe("jazzcash"):
        b = _rb("pay_jazzcash", callback_data=f"ptspay_jazz_{amt}")
        if b: kb.append([b])
    # 🆕 v52: editable nav button
    _b = _rb("nav_points_cancel", callback_data="buy_points")
    if _b: kb.append([_b])
    return InlineKeyboardMarkup(kb)


# ════════════════════════════════════════════
# 📞 SUPPORT
# ════════════════════════════════════════════
def support_keyboard(wa, email):
    """🔧 BULLETPROOF: Always shows WhatsApp Support button
    Validates everything strictly to prevent Telegram API rejection."""
    kb = []

    # ── WhatsApp button ──
    try:
        wa_str = str(wa or "").strip()
        # Extract only digits (handles +92, spaces, dashes, etc.)
        clean_wa = ''.join(ch for ch in wa_str if ch.isdigit())
        # WhatsApp needs at least 7 digits to be valid
        if len(clean_wa) >= 7:
            wa_url = f"https://wa.me/{clean_wa}"
            kb.append([InlineKeyboardButton("💬 WhatsApp Support", url=wa_url)])
    except Exception:
        pass

    # ── Email button ──
    try:
        em_str = str(email or "").strip()
        # Basic email validation
        if "@" in em_str and "." in em_str.split("@")[-1] and " " not in em_str:
            kb.append([InlineKeyboardButton("📧 Email Support", url=f"mailto:{em_str}")])
    except Exception:
        pass

    # ── Fallback if no method set ──
    if not kb:
        kb.append([InlineKeyboardButton("⚠️ No support method set", callback_data="main_menu")])

    # 🆕 v52: editable nav button via Customization → 🎨 Buttons → Navigation
    _b = _rb("nav_back_main", callback_data="main_menu")
    if _b:
        kb.append([_b])
    else:
        kb.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")])

    return InlineKeyboardMarkup(kb)


# ════════════════════════════════════════════
# 👑 ADMIN MENUS
# ════════════════════════════════════════════
def admin_menu_keyboard():
    # 🆕 Phase C: Ordered ids
    # 🆕 v46: every admin button below is a registry button now → rename / hide /
    # background color all work, and "Bulk color" applies to the whole panel.
    from button_system import get_ordered_button_ids
    all_ordered = get_ordered_button_ids("admin")
    # These get their own full-width rows at the end — exclude from the top grid
    # 🆕 v73: "admin_orders" REMOVED (Pending Orders button deprecated).
    # Full-width bottom rows: AI Assistant, Reset, Backup.
    bottom = ["admin_ai", "admin_reset", "admin_backup"]
    # 🆕 v69: Hide buttons that ALSO appear inside Admin → Settings panel,
    # to avoid duplicate buttons in two places (user complaint).
    # These are still in the registry (so Customization sees them), but they
    # only render in their proper home: the Settings panel.
    settings_only = {
        # Inside ⚙️ Settings → 🪙 Binance Pay API panel
        "admin_binance_api",
        "admin_binance_api_test",
        "admin_binance_api_list",
        "admin_binance_proxies",
        "admin_proxy_ai_scout",
        # Inside 🏆 Loyalty → ⚙️ Configure Tiers panel
        "admin_tier_cfg",
    }
    grid_ids = [bid for bid in all_ordered if bid not in bottom and bid not in settings_only]

    def _row(bid):
        b = _rb(bid)
        return [b] if b is not None else None

    buttons = [_rb(bid) for bid in grid_ids]
    buttons = [b for b in buttons if b is not None]
    kb = _arrange(buttons) if buttons else []

    # Full-width rows (kept at the bottom for visibility)
    for bid in bottom:
        r = _row(bid)
        if r:
            kb.append(r)

    # 🆕 Phase B: admin's custom buttons in admin panel
    kb.extend(_custom_buttons_for("admin"))
    kb.append([_btn("🔙", "🔙 Return", "🔙 Return", "🔙 Back to Main Menu", callback_data="main_menu")])
    # 📐 v46: whole-screen padding for the admin panel
    return _apply_screen_pad_markup(InlineKeyboardMarkup(kb), "admin")


def admin_categories_keyboard(cats):
    """🆕 v40.1: Per-category styler applies here too (admin sees same custom labels)."""
    from button_system import is_styled
    kb = []
    for c in cats:
        lbl = f"🏷️ {c['emoji']} {c['name']}"
        if is_styled(f"cat_{c['id']}"):
            lbl = _apply_styler(f"cat_{c['id']}", lbl)
        else:
            lbl = _apply_styler("shop_category", lbl)
        kb.append([InlineKeyboardButton(lbl, callback_data=f"viewcat_{c['id']}")])
    kb.append([_btn("➕", "➕ Add", "➕ Add Category", "➕ Add New Category", callback_data="add_category")])
    kb.append([_btn("🔙", "🔙 Return", "🔙 Return", "🔙 Back to Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


def admin_products_keyboard(prods):
    """🆕 v40.1: Per-product styler applies here too.
    🆕 v45: premium-emoji-aware (icon from product name)."""
    from button_system import is_styled
    try:
        from button_system import make_premium_button, extract_emoji_from_html
    except Exception:
        make_premium_button = None
        extract_emoji_from_html = None
    kb = []
    for p in prods:
        raw = p.get('name', '') if hasattr(p, 'get') else p['name']
        raw = raw or ''
        if extract_emoji_from_html:
            ne_id, plain = extract_emoji_from_html(raw)
        else:
            ne_id, plain = "", raw
        lbl = f"📦 {plain} [Stock: {p['stock']}]"
        if is_styled(f"prod_{p['id']}"):
            lbl = _apply_styler(f"prod_{p['id']}", lbl)
        else:
            lbl = _apply_styler("shop_product", lbl)
        if ne_id and make_premium_button:
            kb.append([make_premium_button(lbl, emoji_id=ne_id,
                                            callback_data=f"viewprod_{p['id']}")])
        else:
            kb.append([InlineKeyboardButton(lbl, callback_data=f"viewprod_{p['id']}")])
    kb.append([_btn("➕", "➕ Add", "➕ Add Item", "➕ Add New Product", callback_data="add_product")])
    kb.append([_btn("🔙", "🔙 Return", "🔙 Return", "🔙 Back to Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


def admin_order_keyboard(oid):
    return InlineKeyboardMarkup([
        [
            _btn("✅", "✅ Approve", "✅ Approve", "✅ Approve & Deliver", callback_data=f"approve_{oid}"),
            _btn("❌", "❌ Reject", "❌ Reject", "❌ Reject Order", callback_data=f"reject_{oid}"),
        ],
        [_btn("🔙", "🔙 Back", "🔙 Back", "🔙 Back to Admin Panel", callback_data="admin_panel")],
    ])


def admin_pending_orders_keyboard(orders):
    kb = []
    for o in orders:
        e = "🔶" if o['payment_method'] == 'binance' else "📸" if o['status'] == 'screenshot_sent' else "🟡"
        # 🆕 v40.1: styler for order rows
        lbl = _apply_styler("admin_order_row", f"{e} #{o['id']} {o['product_name']}")
        kb.append([InlineKeyboardButton(lbl, callback_data=f"view_order_{o['id']}")])
    if not orders:
        kb.append([InlineKeyboardButton("📭 Empty", callback_data="admin_panel")])
    kb.append([_btn("🔙", "🔙", "🔙 Return", "🔙 Back to Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


def select_category_keyboard(cats):
    kb = [[InlineKeyboardButton(f"{c['emoji']} {c['name']}", callback_data=f"selcat_{c['id']}")] for c in cats]
    kb.append([_btn("❌", "❌ Cancel", "❌ Cancel", "❌ Cancel", callback_data="admin_products")])
    return InlineKeyboardMarkup(kb)


def admin_settings_keyboard():
    """🆕 v33: Cleaner — payment methods grouped under ONE button"""
    from button_system import get_ordered_button_ids
    all_ordered = get_ordered_button_ids("settings")
    # 🆕 v33: Hide individual payment buttons (replaced by "Payment Methods")
    hidden_pm = {"set_binance", "set_easypaisa", "set_jazzcash",
                 "set_binance_name", "set_easypaisa_name", "set_jazzcash_name",
                 "set_account_name"}
    bottom_ids = {"settings_responses", "settings_terms"}
    grid_ids = [bid for bid in all_ordered if bid not in bottom_ids and bid not in hidden_pm]
    buttons = [_rb(bid) for bid in grid_ids]
    buttons = [b for b in buttons if b is not None]
    kb = _arrange(buttons) if buttons else []
    # 🆕 v33: One "Payment Methods" button replaces all payment buttons
    kb.append([InlineKeyboardButton("💳 Payment Methods", callback_data="admin_payments")])
    # Responses + Terms at bottom
    for bid in all_ordered:
        if bid in bottom_ids:
            b = _rb(bid)
            if b: kb.append([b])
    # Custom buttons + API tests
    kb.extend(_custom_buttons_for("settings"))
    kb.append([
        InlineKeyboardButton("📧 Payment Email Settings", callback_data="admin_payment_emails"),
    ])
    # 🆕 v59: Default shop filter setting (what new users see by default)
    kb.append([
        InlineKeyboardButton("🛒 Default Shop Filter", callback_data="admin_shop_filter"),
    ])
    # 🆕 v61: Binance Pay API (REST + Pakistani proxy support)
    kb.append([
        InlineKeyboardButton("🪙 Binance Pay API", callback_data="admin_binance_api"),
    ])
    # 🆕 v70: Pinned Announcements
    kb.append([
        InlineKeyboardButton("📌 Pinned Announcements", callback_data="admin_pins"),
    ])
    # 🆕 v102: Referral Diagnostics — all attempts (accepted + blocked reasons)
    kb.append([
        InlineKeyboardButton("🔍 Referral Diagnostics", callback_data="admin_ref_diag"),
    ])
    # 🆕 v71: AI Auto-Reply for Support Tickets
    kb.append([
        InlineKeyboardButton("🤖 AI Support Auto-Reply", callback_data="admin_ai_support"),
    ])
    # 🆕 v72: Delivery integrity dashboard (SHA-256 byte-perfect monitor)
    kb.append([
        InlineKeyboardButton("🛡️ Delivery Integrity", callback_data="admin_integrity"),
    ])
    # 🆕 v80: Payment Methods Enable/Disable toggle
    kb.append([
        InlineKeyboardButton("💳 Payment Methods Toggle", callback_data="admin_pay_toggle"),
    ])
    # 🆕 v84: Maintenance Mode toggle + templates + custom message
    try:
        from maintenance_mode import is_maintenance_on
        _maint_label = ("🛠️ Maintenance Mode  🟢 ON"
                        if is_maintenance_on()
                        else "🛠️ Maintenance Mode  🔴 OFF")
    except Exception:
        _maint_label = "🛠️ Maintenance Mode"
    kb.append([
        InlineKeyboardButton(_maint_label, callback_data="maint_panel"),
    ])
    # 🆕 v87: Auto-Translator (source → target lang, full-bot scan + auto-sync)
    try:
        from auto_translator import is_translator_enabled, get_from_lang, get_to_lang, LANGUAGES
        if is_translator_enabled():
            _fl = LANGUAGES.get(get_from_lang(), "?").split(" ", 1)[0]
            _tl = LANGUAGES.get(get_to_lang(), "?").split(" ", 1)[0]
            _tr_label = f"🌐 Translator 🟢 {_fl}→{_tl}"
        else:
            _tr_label = "🌐 Auto-Translator  🔴 OFF"
    except Exception:
        _tr_label = "🌐 Auto-Translator"
    kb.append([
        InlineKeyboardButton(_tr_label, callback_data="admin_translator"),
    ])
    kb.append([_btn("🔙", "🔙 Return", "🔙 Return", "🔙 Back to Admin Panel", callback_data="admin_panel")])
    # 📐 v46: whole-screen padding for the settings menu
    return _apply_screen_pad_markup(InlineKeyboardMarkup(kb), "settings")


def admin_responses_keyboard(keys):
    kb = [[InlineKeyboardButton(f"✏️ {k.replace('_', ' ').title()}", callback_data=f"editresp_{k}")] for k in keys]
    kb.append([_btn("🔙", "🔙 Return", "🔙 Return", "🔙 Back to Settings", callback_data="admin_settings")])
    return InlineKeyboardMarkup(kb)


def admin_profit_keyboard(products):
    # 🆕 v45: premium-emoji-aware
    try:
        from button_system import make_premium_button, extract_emoji_from_html
    except Exception:
        make_premium_button = None
        extract_emoji_from_html = None
    kb = []
    for p in products:
        raw = p['name'] or ''
        if extract_emoji_from_html:
            ne_id, plain = extract_emoji_from_html(raw)
        else:
            ne_id, plain = "", raw
        if ne_id and make_premium_button:
            kb.append([make_premium_button(f"📦 {plain}", emoji_id=ne_id,
                                            callback_data=f"profit_{p['id']}")])
        else:
            kb.append([InlineKeyboardButton(f"📦 {plain or p['name']}", callback_data=f"profit_{p['id']}")])
    kb.append([_btn("📊", "📊 Summary", "📊 All Products", "📊 All Products Summary", callback_data="profit_all")])
    kb.append([_btn("🔙", "🔙 Return", "🔙 Return", "🔙 Back to Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


# ════════════════════════════════════════════
# 🎨 CUSTOMIZATION KEYBOARDS
# ════════════════════════════════════════════

def customization_menu_keyboard():
    """🎨 Main customization menu — registry + ordered"""
    from button_system import get_ordered_button_ids
    kb = []
    for bid in get_ordered_button_ids("customization"):
        b = _rb(bid)
        if b:
            kb.append([b])
    # 🆕 Phase B
    kb.extend(_custom_buttons_for("customization"))
    # 🛍️ Product Design moved here from Admin Panel
    kb.append([InlineKeyboardButton("🛍️ Product Design", callback_data="pd_panel")])
    # 🆕 v92: 🎨 Main Menu Layout Picker — 50 layouts, auto-adjusts to custom buttons
    try:
        from main_menu_layouts import get_active_layout_id, LAYOUTS
        _active = LAYOUTS.get(get_active_layout_id(), {})
        _mml_label = f"🎨 Main Menu Layout · {_active.get('name', '')[:20]}"
    except Exception:
        _mml_label = "🎨 Main Menu Layout (50 designs)"
    kb.append([InlineKeyboardButton(_mml_label, callback_data="admin_main_layout")])
    # 🆕 v94: Global broadcast button color
    try:
        from fake_engagement import _get_broadcast_global_color
        _bc = _get_broadcast_global_color() or ""
        _bc_lbl = {"": "⚪ Default", "primary": "🔵 Blue",
                   "success": "🟢 Green", "danger": "🔴 Red"}.get(_bc, "?")
        _bcol_label = f"🎨 Broadcast Buy Now Color · {_bc_lbl}"
    except Exception:
        _bcol_label = "🎨 Broadcast Buy Now Color"
    kb.append([InlineKeyboardButton(_bcol_label,
                                     callback_data="admin_broadcast_color")])
    # 🆕 v52: REMOVED duplicate "🎨 Inline Button Styler" entry.
    # All button editing (rename, color, size, align, pad, premium emoji, hide)
    # is now unified under 🎨 Buttons (admin_buttons) which appears above as a
    # customization-group registry button. Single source of truth.
    # NOTE (v43): The standalone "📝 Broadcast Button Texts" entry was
    # removed at admin's request. Button text editing now lives INSIDE
    # each template (see Fake Broadcast → Edit Templates → pick template
    # → Edit Button Text). Backend still exists for backward compatibility.
    kb.append([_btn("🔙", "🔙 Return", "🔙 Return", "🔙 Back to Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


def toggles_keyboard(t_w, t_q, t_s, t_p, t_sold="1", t_pemoji="1", emoji_char="🛍️"):
    """👁️ Toggle buttons keyboard"""
    def lbl(name, state):
        return f"{'🟢' if state == '1' else '🔴'} {name}: {'ON' if state == '1' else 'OFF'}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(lbl("🛡️ Warranty", t_w), callback_data="toggle_show_warranty")],
        [InlineKeyboardButton(lbl("📦 Quantity", t_q), callback_data="toggle_show_quantity")],
        [InlineKeyboardButton(lbl("📊 Stock", t_s), callback_data="toggle_show_stock")],
        [InlineKeyboardButton(lbl("🔥 Sold Count", t_sold), callback_data="toggle_show_sold")],
        [InlineKeyboardButton(lbl("📸 Photo", t_p), callback_data="toggle_show_photo")],
        # 🆕 v42: Toggle the default 🛍️ emoji that prefixes each product in the shop list
        [InlineKeyboardButton(lbl(f"{emoji_char} Product List Emoji", t_pemoji),
                              callback_data="toggle_show_product_emoji")],
        # 🆕 v42: Change WHICH emoji is used (default 🛍️)
        [InlineKeyboardButton(f"✏️ Change Product Emoji  ({emoji_char})",
                              callback_data="edit_product_emoji")],
        [_btn("🔙", "🔙 Return", "🔙 Return", "🔙 Back to Customization", callback_data="admin_customization")],
    ])


# 🆕 NEW: Button Size selection keyboard
def button_size_keyboard(current_size):
    """📏 Button size selection — shows current size with ✅"""
    def mk(label, val):
        mark = " ✅" if current_size == val else ""
        return InlineKeyboardButton(label + mark, callback_data=f"setsize_{val}")
    return InlineKeyboardMarkup([
        [mk("📱 Small (emoji only, 3/row)", "small")],
        [mk("💻 Medium (emoji + short text, 2/row)", "medium")],
        [mk("🖥️ Large (emoji + full text, 2/row)", "large")],
        [mk("📺 Extra Large (full label, 1/row)", "xl")],
        [mk("📺🖥️ Full Screen (widest, 1/row)", "full")],
        [_btn("🔙", "🔙 Return", "🔙 Return", "🔙 Back to Customization", callback_data="admin_customization")],
    ])


# 🆕 NEW: Menu Style selection keyboard
def menu_styles_keyboard(current_style_id):
    """🎨 Show 10 menu styles. Current one gets ✅"""
    from button_system import STYLES
    kb = []
    for sid, info in STYLES.items():
        mark = " ✅" if sid == current_style_id else ""
        # Build the label using the style itself for preview (so admin SEES the look)
        preview = info["preview"]
        kb.append([InlineKeyboardButton(f"{sid}. {info['name']} → {preview}{mark}",
                                         callback_data=f"setstyle_{sid}")])
    kb.append([InlineKeyboardButton("🔙 Return", callback_data="admin_customization")])
    return InlineKeyboardMarkup(kb)


# 🆕 NEW: Display Format selector (Raw / Carousel)
def display_format_keyboard(current_format):
    """🎠 Choose between Raw list or Carousel format"""
    def mk(label, val):
        mark = " ✅" if current_format == val else ""
        return InlineKeyboardButton(label + mark, callback_data=f"setformat_{val}")
    return InlineKeyboardMarkup([
        [mk("📋 Raw — Classic list view", "raw")],
        [mk("🎠 Carousel — Swipe-like cards", "carousel")],
        [_btn("🔙", "🔙 Return", "🔙 Return", "🔙 Back to Customization", callback_data="admin_customization")],
    ])


# ════════════════════════════════════════════
# 🎛️ MANAGE BUTTONS (Phase A)
# ════════════════════════════════════════════

def manage_buttons_groups_keyboard():
    """Show list of button groups (Main, Admin, Settings, etc.) + Add Custom shortcut
    🆕 v54: Reorganized for clarity.
    - 🌳 Screen Editor shown in its own clearly-labeled section
    - ➕ / 📋 Custom Buttons in their own section
    - System button groups in their own section
    - 🔙 Return goes back to Customization (the parent menu where this was opened from)
    """
    from button_system import GROUP_NAMES
    kb = []
    # ── Section 1: Screen-by-Screen drill-down editor ──
    kb.append([InlineKeyboardButton("🌳 Screen-by-Screen Editor (User Side)",
                                    callback_data="se_root")])
    # ── Section 2: Custom buttons (admin-created) ──
    kb.append([InlineKeyboardButton("➕ Add New Custom Button", callback_data="cbnew")])
    # 🆕 v54: send to admin_buttons-aware listing so Back returns here, not admin_cbtns
    kb.append([InlineKeyboardButton("📋 View My Custom Buttons", callback_data="mblist_all_custom")])
    # ── Section 3: System button groups ──
    kb.append([InlineKeyboardButton("━━━ ⚙️ System Button Groups ━━━",
                                    callback_data="noop")])
    for group_id, label in GROUP_NAMES.items():
        kb.append([InlineKeyboardButton(f"⚙️ {label}", callback_data=f"mbgrp_{group_id}")])
    # 🆕 v54: Return to Customization (the parent menu), not admin_panel
    kb.append([InlineKeyboardButton("🔙 Back to Customization",
                                    callback_data="admin_customization")])
    return InlineKeyboardMarkup(kb)


def manage_buttons_list_keyboard(group_id):
    """Show buttons inside a group (ordered) with hide/show state + ⬆⬇ reorder"""
    from button_system import BUTTONS, is_button_hidden, get_ordered_button_ids
    ordered_ids = get_ordered_button_ids(group_id)
    kb = []
    for btn_id in ordered_ids:
        info = BUTTONS.get(btn_id, {})
        hidden = is_button_hidden(btn_id)
        essential = info.get("essential")
        if essential:
            status = "🔒"
        elif hidden:
            status = "🔴"
        else:
            status = "🟢"
        preview = info.get("medium", btn_id)
        # Main button + reorder arrows in same row
        kb.append([
            InlineKeyboardButton(f"{status} {preview}", callback_data=f"mbedit_{btn_id}"),
            InlineKeyboardButton("⬆️", callback_data=f"mbup_{btn_id}"),
            InlineKeyboardButton("⬇️", callback_data=f"mbdn_{btn_id}"),
        ])
    # 🎨 v46: one-click bulk color for ALL buttons in this group
    from button_system import get_group_style
    _gs = get_group_style(group_id)
    _glbl = {"primary": "🔵 Blue", "success": "🟢 Green",
             "danger": "🔴 Red", "": "⬜ Default"}.get(_gs, "⬜ Default")
    kb.append([InlineKeyboardButton(f"🎨 Set Color for ALL ({_glbl})",
                                    callback_data=f"mbgcolor_{group_id}")])
    # 📐 v46: whole-screen padding for this menu (widen/narrow all buttons).
    # Only offered for groups whose full screen we render through the registry
    # (main / admin / settings) so the control always has a visible effect.
    if group_id in ("main", "admin", "settings"):
        from button_system import get_screen_pad
        _spad = get_screen_pad(group_id)
        kb.append([InlineKeyboardButton(f"📐 Screen Padding: {_spad}", callback_data="noop")])
        kb.append([
            InlineKeyboardButton("➖ 5", callback_data=f"mbscrpad_{group_id}_-5"),
            InlineKeyboardButton("🧹 0", callback_data=f"mbscrpad_{group_id}_0"),
            InlineKeyboardButton("➕ 5", callback_data=f"mbscrpad_{group_id}_5"),
            InlineKeyboardButton("➕ 10", callback_data=f"mbscrpad_{group_id}_10"),
        ])
        kb.append([InlineKeyboardButton("✏️ Custom Padding Number", callback_data=f"mbscrpadcustom_{group_id}")])
    # 🆕 v54: clearer back label — clarifies parent location
    kb.append([InlineKeyboardButton("🔙 Back to Button Groups", callback_data="admin_buttons")])
    return InlineKeyboardMarkup(kb)


def manage_one_button_keyboard(btn_id):
    """Actions for a single button: rename, hide, reset"""
    from button_system import BUTTONS, is_button_hidden
    btn = BUTTONS.get(btn_id, {})
    essential = btn.get("essential")
    hidden = is_button_hidden(btn_id)

    kb = [
        [InlineKeyboardButton("✏️ Rename (Medium)", callback_data=f"mbrenm_{btn_id}_medium")],
        [
            InlineKeyboardButton("📱 Edit Small", callback_data=f"mbrenm_{btn_id}_short"),
            InlineKeyboardButton("🖥️ Edit Large", callback_data=f"mbrenm_{btn_id}_large"),
        ],
        [InlineKeyboardButton("📺 Edit XL", callback_data=f"mbrenm_{btn_id}_xl")],
    ]

    # 🎨 v46: Button background color (Telegram Premium feature)
    try:
        from button_system import get_button_style
        _cur_style = get_button_style(btn_id)
    except Exception:
        _cur_style = ""
    _style_lbl = {"primary": "🔵 Blue", "success": "🟢 Green",
                  "danger": "🔴 Red", "": "⬜ Default"}.get(_cur_style, "⬜ Default")
    kb.append([InlineKeyboardButton(f"🎨 Background Color: {_style_lbl}",
                                    callback_data=f"mbcolor_{btn_id}")])

    # Hide/Show toggle (only for non-essential)
    if not essential:
        if hidden:
            kb.append([InlineKeyboardButton("🟢 Show this button", callback_data=f"mbtog_{btn_id}")])
        else:
            kb.append([InlineKeyboardButton("🔴 Hide this button", callback_data=f"mbtog_{btn_id}")])
    else:
        kb.append([InlineKeyboardButton("🔒 Essential (cannot hide)", callback_data="locked")])

    kb.append([InlineKeyboardButton("♻️ Reset to default", callback_data=f"mbrst_{btn_id}")])
    grp = btn.get("group", "main")
    # 🆕 v54: include group name in back label so admin knows exactly where they're going.
    # For navigation group (long name), use shorter friendly label.
    from button_system import GROUP_NAMES
    grp_name = GROUP_NAMES.get(grp, grp)
    # Strip emoji prefix for clean label
    parts = grp_name.split(" ", 1)
    grp_clean = parts[1] if len(parts) > 1 and len(parts[0]) <= 4 else grp_name
    # Truncate parenthetical descriptions for cleaner button labels
    if "(" in grp_clean:
        grp_clean = grp_clean.split("(", 1)[0].strip()
    kb.append([InlineKeyboardButton(f"🔙 Back to {grp_clean[:35]}", callback_data=f"mbgrp_{grp}")])
    return InlineKeyboardMarkup(kb)


def button_color_picker_keyboard(btn_id):
    """🎨 v46: pick a Telegram button background color for a registry button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔵 Blue (Primary)",  callback_data=f"mbsetcol_{btn_id}_primary")],
        [InlineKeyboardButton("🟢 Green (Success)", callback_data=f"mbsetcol_{btn_id}_success")],
        [InlineKeyboardButton("🔴 Red (Danger)",    callback_data=f"mbsetcol_{btn_id}_danger")],
        [InlineKeyboardButton("⬜ Default (no color)", callback_data=f"mbsetcol_{btn_id}_none")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"mbedit_{btn_id}")],
    ])


def group_color_picker_keyboard(group_id):
    """🎨 v46: pick ONE color to apply to ALL buttons in a group/location."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔵 Blue (Primary)",  callback_data=f"mbgsetcol_{group_id}_primary")],
        [InlineKeyboardButton("🟢 Green (Success)", callback_data=f"mbgsetcol_{group_id}_success")],
        [InlineKeyboardButton("🔴 Red (Danger)",    callback_data=f"mbgsetcol_{group_id}_danger")],
        [InlineKeyboardButton("⬜ Default (clear all)", callback_data=f"mbgsetcol_{group_id}_none")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"mbgrp_{group_id}")],
    ])


def custom_button_color_picker_keyboard(bid):
    """🎨 v46: pick a background color for a single custom button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔵 Blue (Primary)",  callback_data=f"cbsetcol_{bid}_primary")],
        [InlineKeyboardButton("🟢 Green (Success)", callback_data=f"cbsetcol_{bid}_success")],
        [InlineKeyboardButton("🔴 Red (Danger)",    callback_data=f"cbsetcol_{bid}_danger")],
        [InlineKeyboardButton("⬜ Default (no color)", callback_data=f"cbsetcol_{bid}_none")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"cbview_{bid}")],
    ])


# ════════════════════════════════════════════
# 🎨 CUSTOM BUTTONS RENDERER (Phase B)
# ════════════════════════════════════════════
def _custom_buttons_for(location):
    """Returns list of [button] rows for a given location.
    🆕 v38: Supports 17+ action types via unified cbact_ callback.
    🆕 v40.1: Per-custom-button styling (custom_<bid>) + fallback custom_default."""
    from button_system import is_styled
    try:
        from database import get_custom_buttons
        buttons = get_custom_buttons(location)
    except Exception:
        return []
    from button_system import get_button_style as _gbs, get_group_style as _ggs
    rows = []
    for b in buttons:
        if not b['is_active']:
            continue
        label = decorate(b['label'])
        # Apply per-button styler: individual override OR submenu default OR custom default
        style_key = f"custom_{b['id']}"
        if is_styled(style_key):
            label = _apply_styler(style_key, label)
        elif location.startswith("sub_"):
            label = _apply_styler("custom_submenu", label)
        else:
            label = _apply_styler("custom_default", label)
        # 🎨 v46: per-custom-button color OR the location's group color
        _cbstyle = _gbs(f"custom_{b['id']}") or _ggs(location)

        def mkbtn(lbl, **kw):
            kw.setdefault("style", _cbstyle)
            return _make_btn(lbl, **kw)

        btype = b['btype']
        # ── 🆕 v45: All custom-button constructions go through _make_btn()
        # which auto-detects premium-emoji HTML labels and renders icons.
        # ── Legacy types (kept for backward compatibility) ──
        if btype == 'url' and b['action']:
            rows.append([mkbtn(label, url=b['action'])])
        elif btype == 'text':
            rows.append([mkbtn(label, callback_data=f"cbtn_{b['id']}")])
        elif btype == 'submenu':
            rows.append([mkbtn(label, callback_data=f"cbsub_{b['id']}")])
        elif btype == 'page':
            rows.append([mkbtn(label, callback_data=f"cbpage_{b['id']}")])
        # ── 🆕 v38: WebApp gets native Telegram WebApp button ──
        elif btype == 'webapp' and b['action']:
            try:
                from telegram import WebAppInfo
                # web_app buttons don't pass through _make_btn (kwarg differs);
                # but admin can still include premium emoji — extract manually.
                try:
                    from button_system import make_premium_button
                    rows.append([make_premium_button(label, style=_cbstyle, web_app=WebAppInfo(url=b['action']))])
                except Exception:
                    rows.append([InlineKeyboardButton(label, web_app=WebAppInfo(url=b['action']))])
            except Exception:
                rows.append([mkbtn(label, url=b['action'])])
        # ── 🆕 v38: WhatsApp/Email/Telegram/Phone get native URL buttons ──
        elif btype == 'whatsapp' and b['action']:
            digits = "".join(c for c in b['action'] if c.isdigit())
            rows.append([mkbtn(label, url=f"https://wa.me/{digits}")])
        elif btype == 'email' and b['action']:
            rows.append([mkbtn(label, url=f"mailto:{b['action']}")])
        elif btype == 'telegram_chat' and b['action']:
            uname = b['action'].lstrip("@")
            rows.append([mkbtn(label, url=f"https://t.me/{uname}")])
        elif btype == 'phone_call' and b['action']:
            rows.append([mkbtn(label, url=f"tel:{b['action']}")])
        # ── 🆕 v38: ALL other action types → unified executor ──
        else:
            rows.append([mkbtn(label, callback_data=f"cbact_{b['id']}")])
    return rows


def custom_submenu_keyboard(parent_id):
    """Show buttons inside a submenu
    🔧 BUG #3 FIX: Back goes to wherever this submenu sits
    🔧 BUG #10 FIX: Empty submenu message is informational"""
    rows = _custom_buttons_for(f"sub_{parent_id}")
    if not rows:
        # Use a noop callback for the empty indicator
        rows = [[InlineKeyboardButton("📭 This submenu is empty — admin to add items", callback_data="noop")]]

    # Figure out parent's location to make Back go there
    back_target = "main_menu"
    try:
        from database import get_custom_button
        parent = get_custom_button(parent_id)
        if parent:
            loc = parent['location']
            # Top-level locations → back to their menu
            if loc == "admin":
                back_target = "admin_panel"
            elif loc == "settings":
                back_target = "admin_settings"
            elif loc == "customization":
                back_target = "admin_customization"
            elif loc.startswith("sub_"):
                # This is a 2nd-level submenu — back to parent submenu
                grandparent_id = loc.replace("sub_", "")
                back_target = f"cbsub_{grandparent_id}"
            # else: "main" → back_target stays "main_menu"
    except Exception:
        pass

    rows.append([_btn("🔙", "🔙 Back", "🔙 Back", "🔙 Back", callback_data=back_target)])
    return InlineKeyboardMarkup(rows)


# ════════════════════════════════════════════
# ➕ CUSTOM BUTTONS MANAGEMENT UI
# ════════════════════════════════════════════

# Location labels for nice display
CB_LOCATIONS = {
    "main": "🏠 Main Menu",
    "admin": "👑 Admin Panel",
    "settings": "⚙️ Settings",
    "customization": "🎨 Customization",
}


def cbtns_main_keyboard():
    """Main custom-buttons management screen — pick a location.
    🆕 v38: Shows all 13+ locations grouped."""
    from button_system import BUTTON_LOCATIONS
    kb = [
        [InlineKeyboardButton("➕ Add New Custom Button", callback_data="cbnew")],
        [InlineKeyboardButton("📋 View All Custom Buttons", callback_data="cblist_all")],
    ]
    # Group locations for clean display
    groups = [
        ("🏠 MAIN AREAS", ["main", "admin", "settings", "customization"]),
        ("👤 USER SCREENS", ["my_account", "shop", "my_orders", "support",
                              "warranty", "reviews", "loyalty",
                              "transactions", "referral", "buy_points"]),
        ("💼 OTHER", ["payment", "product_detail"]),
    ]
    for group_title, loc_ids in groups:
        kb.append([InlineKeyboardButton(group_title, callback_data="noop")])
        for lid in loc_ids:
            loc = next((l for l in BUTTON_LOCATIONS if l["id"] == lid), None)
            if loc:
                kb.append([InlineKeyboardButton(f"{loc['icon']} {loc['label']}",
                                                  callback_data=f"cblist_{lid}")])
    kb.append([InlineKeyboardButton("🔙 Return", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


def cbtns_list_keyboard(buttons, current_location_id=None, back_callback="admin_cbtns"):
    """Show list of custom buttons at a location + ⬆⬇ reorder.
    🆕 v38: Uses action_icon from button_actions for all 17+ types.
    🆕 nested-submenu UX: contextual Back can return to the parent submenu/button.
    """
    from button_system import action_icon
    kb = []
    for b in buttons:
        type_icon = action_icon(b['btype'])
        loc_label = CB_LOCATIONS.get(b['location'], b['location'])
        if current_location_id:
            label = f"{type_icon} {b['label']}"
            kb.append([
                InlineKeyboardButton(label, callback_data=f"cbview_{b['id']}"),
                InlineKeyboardButton("⬆️", callback_data=f"cbup_{b['id']}"),
                InlineKeyboardButton("⬇️", callback_data=f"cbdn_{b['id']}"),
            ])
        else:
            label = f"{type_icon} {b['label']}  ({loc_label})"
            kb.append([InlineKeyboardButton(label, callback_data=f"cbview_{b['id']}")])
    if not buttons:
        kb.append([InlineKeyboardButton("📭 No custom buttons here", callback_data=back_callback)])
    kb.append([InlineKeyboardButton("➕ Add New Custom Button", callback_data="cbnew")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data=back_callback)])
    return InlineKeyboardMarkup(kb)


def cbtns_view_keyboard(bid, btype, back_callback="admin_cbtns"):
    """🆕 v38: Single button actions — supports all 17+ action types."""
    from button_system import get_action
    action = get_action(btype)
    kb = [
        [InlineKeyboardButton("✏️ Rename (Label)", callback_data=f"cbedit_label_{bid}")],
    ]
    # Edit action value for types that have one
    if action and action.get("needs_value") and btype != "submenu":
        edit_label = {
            "url": "🔗 Change URL",
            "text": "📝 Change Text",
            "page": "📄 Change Page",
            "nav": "🧭 Change Target",
            "buy_product": "🛒 Change Product ID",
            "buy_points_amount": "💎 Change Amount",
            "whatsapp": "📱 Change Number",
            "email": "📧 Change Email",
            "telegram_chat": "💬 Change Username",
            "phone_call": "☎️ Change Number",
            "alert": "🔔 Change Message",
            "copy": "📋 Change Text",
            "send_photo": "📸 Change Photo",
            "send_video": "🎬 Change Video",
            "send_document": "📎 Change File",
            "send_audio": "🎵 Change Audio",
            "webapp": "🌐 Change URL",
            "command": "⚡ Change Command",
        }.get(btype, f"{action['icon']} Change Value")
        kb.append([InlineKeyboardButton(edit_label, callback_data=f"cbedit_action_{bid}")])
    if btype == "submenu":
        kb.append([InlineKeyboardButton("📂 Open Submenu (manage inside)", callback_data=f"cbsubmgmt_{bid}")])
    kb.append([InlineKeyboardButton("🎨 Style / Size / Padding", callback_data=f"cbstyle_{bid}")])
    kb.append([InlineKeyboardButton("📍 Change Location", callback_data=f"cbedit_location_{bid}")])
    # 🎨 v46: per-custom-button background color
    from button_system import get_button_style as _gbs
    _cs = _gbs(f"custom_{bid}")
    _cslbl = {"primary": "🔵 Blue", "success": "🟢 Green",
              "danger": "🔴 Red", "": "⬜ Default"}.get(_cs, "⬜ Default")
    kb.append([InlineKeyboardButton(f"🎨 Background Color: {_cslbl}", callback_data=f"cbcolor_{bid}")])
    kb.append([InlineKeyboardButton("🗑️ Delete", callback_data=f"cbdel_{bid}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data=back_callback)])
    return InlineKeyboardMarkup(kb)


def cb_back_only(parent="admin_cbtns"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=parent)]])


# ════════════════════════════════════════════
# 📄 CUSTOM PAGES MANAGEMENT UI (Phase D)
# ════════════════════════════════════════════

def cpages_main_keyboard(pages):
    """Main custom-pages management screen"""
    kb = [[InlineKeyboardButton("➕ Add New Page", callback_data="cpnew")]]
    for p in pages:
        photo_mark = " 📸" if p['photo_id'] else ""
        kb.append([InlineKeyboardButton(f"📄 {p['title']}{photo_mark}",
                                         callback_data=f"cpview_{p['id']}")])
    if not pages:
        kb.append([InlineKeyboardButton("📭 No pages yet", callback_data="admin_cpages")])
    kb.append([InlineKeyboardButton("🔙 Return", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


def cpages_view_keyboard(pid):
    """Actions for a single page"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Title", callback_data=f"cpedit_title_{pid}")],
        [InlineKeyboardButton("📝 Edit Content", callback_data=f"cpedit_content_{pid}")],
        [InlineKeyboardButton("📸 Change Photo", callback_data=f"cpedit_photo_{pid}")],
        [InlineKeyboardButton("🗑️ Remove Photo", callback_data=f"cprmphoto_{pid}")],
        [InlineKeyboardButton("👁️ Preview as User", callback_data=f"cppreview_{pid}")],
        [InlineKeyboardButton("🗑️ Delete Page", callback_data=f"cpdel_{pid}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_cpages")],
    ])


def cpages_picker_keyboard(pages, back_to="admin_cbtns"):
    """When creating a Page-type button, pick which page to link"""
    kb = []
    for p in pages:
        kb.append([InlineKeyboardButton(f"📄 {p['title']}",
                                         callback_data=f"cppick_{p['id']}")])
    if not pages:
        kb.append([InlineKeyboardButton("📭 Create a page first", callback_data="admin_cpages")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data=back_to)])
    return InlineKeyboardMarkup(kb)


def cpage_user_view_keyboard(pid, parent="main_menu"):
    """Bottom buttons when user views a page"""
    return InlineKeyboardMarkup([
        [_btn("🔙", "🔙 Back", "🔙 Back", "🔙 Back to Main Menu", callback_data=parent)],
    ])


# ════════════════════════════════════════════
# 🛒 CATEGORIZED SHOP (Phase D)
# ════════════════════════════════════════════

def shop_categories_keyboard(grouped):
    """Main shop view — list of categories (each with count).
    🆕 v40.1: Per-category styling (cat_<id>) + fallback to shop_category default."""
    from button_system import is_styled
    kb = []
    for cid, info in grouped.items():
        count = len(info['products'])
        in_stock = sum(1 for p in info['products'] if p['stock'] > 0)
        label = f"{info['emoji']} {info['name']} ({in_stock}/{count})"
        # Per-category override OR default category style
        if is_styled(f"cat_{cid}"):
            label = _apply_styler(f"cat_{cid}", label)
        else:
            label = _apply_styler("shop_category", label)
        kb.append([InlineKeyboardButton(label, callback_data=f"shopcat_{cid}")])
    if not grouped:
        kb.append([InlineKeyboardButton("📭 No products yet", callback_data="main_menu")])
    # View all products (flat list) as alternative
    view_all_lbl = _apply_styler("shop_view_all", "📋 View All Products")
    kb.append([InlineKeyboardButton(view_all_lbl, callback_data="shopall")])
    home_lbl = _apply_styler("shop_home", "🏠 Home")
    pts_lbl  = _apply_styler("shop_buy_points", "💎 Buy Points")
    kb.append([
        InlineKeyboardButton(home_lbl, callback_data="main_menu"),
        InlineKeyboardButton(pts_lbl, callback_data="buy_points"),
    ])
    return InlineKeyboardMarkup(kb)


def shop_category_products_keyboard(products, cat_id, page=1, per_page=10, user=None):
    """Products inside a specific category — paginated"""
    total = len(products)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    page_prods = products[start:start + per_page]
    from database import get_product_color
    size = _get_size()
    # 🆕 v42: Admin toggle — show/hide the default 🛍️ emoji prefix on product names
    try:
        from database import get_toggle as _gt, get_setting as _gs
        show_emoji = _gt("show_product_emoji", "1") == "1"
        emoji_char = _gs("product_emoji", "🛍️") or "🛍️"
    except Exception:
        show_emoji = True
        emoji_char = "🛍️"
    prod_emoji = f"{emoji_char} " if show_emoji else ""
    # 🆕 v45: PREMIUM EMOJI in product name → render as button ICON
    try:
        from utils import name_for_button as _nfb
        from button_system import make_premium_button, extract_emoji_from_html
    except Exception:
        _nfb = lambda x: x
        make_premium_button = None
        extract_emoji_from_html = None
    kb = []
    for p in page_prods:
        s = p['stock']
        p = dict(p)
        raw_name = p.get('name', '') or ''
        if extract_emoji_from_html:
            name_emoji_id, plain_name = extract_emoji_from_html(raw_name)
        else:
            name_emoji_id, plain_name = "", _nfb(raw_name)
        p['name'] = plain_name
        # 🎨 v46: auto background color (out=red/manual=blue/auto=green)
        _pstyle = auto_product_style(p)
        # premium emoji becomes the icon → drop default 🛍️ prefix to avoid 2 emojis
        this_prod_emoji = "" if name_emoji_id else prod_emoji
        color = get_product_color(s)
        prefix = f"{color} " if color else ""
        if size == "small":
            label = f"{prefix}{this_prod_emoji}{p['name'][:18]}" if s > 0 else f"{prefix}❌ {p['name'][:18]}"
        elif size == "medium":
            label = f"{prefix}{this_prod_emoji}{p['name']} — ${p['price']:.2f}" if s > 0 else f"{prefix}{this_prod_emoji}{p['name']} ❌"
        elif size == "large":
            label = f"{prefix}{this_prod_emoji}{p['name']} [{s}] — ${p['price']:.2f}" if s > 0 else f"{prefix}{this_prod_emoji}{p['name']} ❌ — ${p['price']:.2f}"
        else:
            label = f"{prefix}{this_prod_emoji}{p['name']} [Stock: {s}] — ${p['price']:.2f}" if s > 0 else f"{prefix}{this_prod_emoji}{p['name']} ❌ Out of Stock — ${p['price']:.2f}"
        from button_system import is_styled
        if is_styled(f"prod_{p['id']}"):
            label = _apply_styler(f"prod_{p['id']}", label)
        else:
            label = _apply_styler("shop_product", label)
        # 🆕 v45: Premium emoji from product name → button icon + 🎨 v46 color
        if (name_emoji_id or _pstyle) and make_premium_button:
            kb.append([make_premium_button(label, emoji_id=(name_emoji_id or None),
                                            style=_pstyle,
                                            callback_data=f"prod_{p['id']}")])
        else:
            kb.append([InlineKeyboardButton(label, callback_data=f"prod_{p['id']}")])
    # Pagination within category
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(_apply_styler("shop_pagination", "⬅️"),
                                         callback_data=f"shopcatpg_{cat_id}_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(_apply_styler("shop_pagination", "➡️"),
                                         callback_data=f"shopcatpg_{cat_id}_{page+1}"))
    if nav:
        kb.append(nav)
    back_lbl = _apply_styler("shop_back_cats", "🔙 Categories")
    home_lbl = _apply_styler("shop_home", "🏠 Home")
    kb.append([InlineKeyboardButton(back_lbl, callback_data="shop")])
    kb.append([InlineKeyboardButton(home_lbl, callback_data="main_menu")])
    return InlineKeyboardMarkup(kb), page, total_pages


# ════════════════════════════════════════════
# 🤖 AI ASSISTANT KEYBOARDS
# ════════════════════════════════════════════
def ai_chat_keyboard():
    """Persistent buttons during AI chat — exit + clear options"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Panel", callback_data="ai_exit")],
        [InlineKeyboardButton("🗑️ Clear Chat", callback_data="ai_clear")],
    ])


def ai_welcome_keyboard():
    """Initial AI welcome screen"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Panel", callback_data="ai_exit")],
    ])


# ════════════════════════════════════════════
# 🎨 PRODUCT COLOR INDICATORS UI (v23)
# ════════════════════════════════════════════

# 20+ color/shape options per category
COLOR_OPTIONS = {
    "in_stock": [
        # Green family (default)
        "🟢", "✅", "🟩", "💚", "🌿", "🍏", "🥬", "🌱",
        # Blue family
        "🔵", "🟦", "💙", "🌊",
        # Other positive
        "⭐", "✨", "💎", "🔆", "🌟", "👍", "🎯", "🆗",
    ],
    "low_stock": [
        # Yellow/Orange family (default)
        "🟡", "🟧", "⚠️", "🟨", "💛", "🍊", "🌅", "📙",
        # Other warning
        "⚡", "🔶", "🔔", "💫", "🟫", "🌟", "❗",
    ],
    "out_stock": [
        # Red family (default)
        "🔴", "❌", "🟥", "❤️", "🚫", "⛔", "🛑", "🍎",
        # Other negative
        "💔", "🔻", "⬛", "🔳", "⚫", "🟣", "🟪",
    ],
}


def color_settings_main_keyboard():
    """Main color settings screen"""
    from database import get_color_setting
    enabled = get_color_setting("color_enabled") == "1"
    enable_lbl = "🟢 Colors: ON" if enabled else "🔴 Colors: OFF"
    in_stk = get_color_setting("color_in_stock")
    low_stk = get_color_setting("color_low_stock")
    out_stk = get_color_setting("color_out_stock")
    threshold = get_color_setting("color_threshold")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(enable_lbl, callback_data="cl_toggle")],
        [InlineKeyboardButton(f"{in_stk}  In Stock indicator", callback_data="cl_pick_in_stock")],
        [InlineKeyboardButton(f"{low_stk}  Low Stock indicator", callback_data="cl_pick_low_stock")],
        [InlineKeyboardButton(f"{out_stk}  Out of Stock indicator", callback_data="cl_pick_out_stock")],
        [InlineKeyboardButton(f"📊 Low Stock Threshold: {threshold}", callback_data="cl_threshold")],
        [InlineKeyboardButton("👁️ Live Preview", callback_data="cl_preview")],
        [InlineKeyboardButton("♻️ Reset to Defaults", callback_data="cl_reset")],
        [InlineKeyboardButton("🔙 Back to Customization", callback_data="admin_customization")],
    ])


def color_picker_keyboard(state):
    """Show emoji picker for a specific state (in_stock/low_stock/out_stock)"""
    from database import get_color_setting
    options = COLOR_OPTIONS.get(state, [])
    current_key = f"color_{state}"
    current = get_color_setting(current_key)
    kb = []
    # Show 5 per row
    row = []
    for opt in options:
        mark = " ✅" if opt == current else ""
        row.append(InlineKeyboardButton(f"{opt}{mark}", callback_data=f"cl_set_{state}_{opt}"))
        if len(row) == 5:
            kb.append(row); row = []
    if row: kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_colors")])
    return InlineKeyboardMarkup(kb)


def color_threshold_keyboard():
    """Threshold picker (1-20)"""
    options = [1, 2, 3, 5, 7, 10, 15, 20]
    from database import get_color_setting
    current = int(get_color_setting("color_threshold") or "5")
    kb = []
    row = []
    for n in options:
        mark = " ✅" if n == current else ""
        row.append(InlineKeyboardButton(f"{n}{mark}", callback_data=f"cl_thr_{n}"))
        if len(row) == 4:
            kb.append(row); row = []
    if row: kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_colors")])
    return InlineKeyboardMarkup(kb)


# ════════════════════════════════════════════
# 💳 PAYMENT METHODS MANAGEMENT (v33)
# ════════════════════════════════════════════
def admin_payments_keyboard():
    """💳 Main Payment Methods screen — show all 3 methods.
    🧹 v39: Removed 6 dead variable fetches (settings were fetched but never used in returned keyboard)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔶 Binance Pay", callback_data="pm_binance")],
        [InlineKeyboardButton("📱 EasyPaisa", callback_data="pm_easypaisa")],
        [InlineKeyboardButton("📱 JazzCash", callback_data="pm_jazzcash")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")],
    ])


def admin_pm_binance_keyboard():
    """🔶 Binance Pay submenu — edit ID + Holder name"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Edit Binance Pay ID", callback_data="set_binance")],
        [InlineKeyboardButton("👤 Edit Binance Holder Name", callback_data="set_binance_name")],
        [InlineKeyboardButton("🔙 Back to Payment Methods", callback_data="admin_payments")],
    ])


def admin_pm_easypaisa_keyboard():
    """📱 EasyPaisa submenu — edit Number + Name"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Edit EasyPaisa Number", callback_data="set_easypaisa")],
        [InlineKeyboardButton("👤 Edit EasyPaisa Holder Name", callback_data="set_easypaisa_name")],
        [InlineKeyboardButton("🔙 Back to Payment Methods", callback_data="admin_payments")],
    ])


def admin_pm_jazzcash_keyboard():
    """📱 JazzCash submenu — edit Number + Name"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Edit JazzCash Number", callback_data="set_jazzcash")],
        [InlineKeyboardButton("👤 Edit JazzCash Holder Name", callback_data="set_jazzcash_name")],
        [InlineKeyboardButton("🔙 Back to Payment Methods", callback_data="admin_payments")],
    ])


# ════════════════════════════════════════════
# 📊 ADMIN DEPOSIT HISTORY (with screenshots)
# ════════════════════════════════════════════

def admin_deposit_history_keyboard(deposits, page=1, per_page=5):
    """📊 Paginated deposit history for admin — each deposit is clickable"""
    total = len(deposits)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    page_deps = deposits[start:start + per_page]
    
    kb = []
    for d in page_deps:
        status_map = {
            'pending': '🟡', 'screenshot_sent': '📸', 'binance_waiting': '⏳',
            'delivered': '✅', 'cancelled': '❌', 'rejected': '🚫'
        }
        emoji = status_map.get(d['status'], '❓')
        method = (d['payment_method'] or '').lower()
        if 'binance' in method: method_icon = "🔶"
        elif 'easy' in method: method_icon = "📱"
        elif 'jazz' in method: method_icon = "📱"
        else: method_icon = "💳"

        has_ss = "📸" if d['payment_screenshot'] else "—"
        try:
            order_type = d['order_type']
        except Exception:
            order_type = 'product'
        amt = f"${d['price']:.2f}" if order_type == 'product' else f"Rs.{d['binance_amount']:.0f}" if d['binance_amount'] else f"${d['price']:.2f}"

        # 🧹 v39: method_icon now shown in label
        label = f"{emoji} {method_icon} #{d['id']} {d['user_name'][:15]} | {amt} | {has_ss}"
        kb.append([InlineKeyboardButton(label, callback_data=f"depview_{d['id']}")])
    
    # Pagination
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"dephist_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"dephist_{page+1}"))
    if nav:
        kb.append(nav)
    
    kb.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


def admin_deposit_detail_keyboard(oid):
    """Detail view for a single deposit — approve/reject"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{oid}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{oid}"),
        ],
        [InlineKeyboardButton("🔙 Back to Deposits", callback_data="admin_deposits")],
    ])


# ════════════════════════════════════════════════════════════════
# 🎯 v38: ADVANCED ACTION SYSTEM — NEW KEYBOARDS
# ════════════════════════════════════════════════════════════════

def cbtns_action_picker_keyboard():
    """Step 1: Pick which type of ACTION the button performs.
    Organized in categorized rows for easy scanning."""
    from button_system import ACTION_TYPES
    kb = []
    # Group by category
    groups = [
        ("📋 BASIC", ["text", "url", "submenu", "page"]),
        ("🧭 NAVIGATION", ["nav"]),
        ("🛒 COMMERCE", ["buy_product", "buy_points_amount"]),
        ("📞 CONTACT", ["whatsapp", "email", "telegram_chat", "phone_call"]),
        ("🔔 INTERACTIVE", ["alert", "copy", "share_bot"]),
        ("📸 MEDIA", ["send_photo", "send_video", "send_document", "send_audio"]),
        ("⚡ ADVANCED", ["webapp", "command"]),
    ]
    for group_title, action_ids in groups:
        # Group header row (non-clickable)
        kb.append([InlineKeyboardButton(group_title, callback_data="noop")])
        # Action buttons (2 per row)
        row = []
        for aid in action_ids:
            act = next((a for a in ACTION_TYPES if a["id"] == aid), None)
            if act:
                row.append(InlineKeyboardButton(f"{act['icon']} {act['label']}",
                                                  callback_data=f"cbtype_{aid}"))
                if len(row) == 2:
                    kb.append(row); row = []
        if row:
            kb.append(row)
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_cbtns")])
    return InlineKeyboardMarkup(kb)


def cbtns_nav_target_keyboard():
    """Picker for navigation target when action type is 'nav'."""
    from button_system import NAVIGATION_TARGETS
    kb = []
    row = []
    for nav in NAVIGATION_TARGETS:
        row.append(InlineKeyboardButton(f"{nav['icon']} {nav['label']}",
                                          callback_data=f"cbnav_{nav['id']}"))
        if len(row) == 2:
            kb.append(row); row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_cbtns")])
    return InlineKeyboardMarkup(kb)


def cbtns_location_v2_keyboard(allow_submenus=True, exclude_sub_of=None, cancel_callback="admin_cbtns"):
    """Enhanced location picker — supports all new screens and nested submenus."""
    from button_system import BUTTON_LOCATIONS
    kb = []
    # Group locations
    groups = [
        ("🏠 MAIN AREAS", ["main", "admin", "settings", "customization"]),
        ("👤 USER SCREENS", ["my_account", "shop", "my_orders", "support",
                              "warranty", "reviews", "loyalty",
                              "transactions", "referral", "buy_points"]),
        ("💼 OTHER", ["payment", "product_detail"]),
    ]
    for group_title, loc_ids in groups:
        kb.append([InlineKeyboardButton(group_title, callback_data="noop")])
        row = []
        for lid in loc_ids:
            loc = next((l for l in BUTTON_LOCATIONS if l["id"] == lid), None)
            if loc:
                row.append(InlineKeyboardButton(f"{loc['icon']} {loc['label']}",
                                                  callback_data=f"cbloc_{lid}"))
                if len(row) == 2:
                    kb.append(row); row = []
        if row:
            kb.append(row)

    # 🆕 v95: append admin-created custom locations (from custom_locations.py)
    try:
        from custom_locations import get_custom_locations
        custom_locs = get_custom_locations()
        if custom_locs:
            kb.append([InlineKeyboardButton("🎨 CUSTOM LOCATIONS",
                                              callback_data="noop")])
            row = []
            for cl in custom_locs:
                lid = cl.get("id", "")
                name = cl.get("name", lid)
                if not lid: continue
                row.append(InlineKeyboardButton(name[:35],
                                                 callback_data=f"cbloc_{lid}"))
                if len(row) == 2:
                    kb.append(row); row = []
            if row:
                kb.append(row)
    except Exception:
        pass

    # Existing submenus as locations (including nested ones)
    if allow_submenus:
        try:
            from database import get_all_custom_buttons
            submenus = [b for b in get_all_custom_buttons() if b['btype'] == 'submenu']
            valid_subs = [sm for sm in submenus if not exclude_sub_of or sm['id'] != exclude_sub_of]
            if valid_subs:
                kb.append([InlineKeyboardButton("📂 INSIDE A SUBMENU", callback_data="noop")])
                for sm in valid_subs:
                    depth = 0
                    loc = str(sm['location'] or '')
                    while loc.startswith('sub_') and depth < 6:
                        depth += 1
                        try:
                            from database import get_custom_button
                            parent = get_custom_button(int(loc.replace('sub_', '', 1)))
                            loc = (dict(parent) if parent else {}).get('location', '') if parent else ''
                        except Exception:
                            break
                    prefix = "  " * depth + "↳ "
                    kb.append([InlineKeyboardButton(f"{prefix}{sm['label']}",
                                                      callback_data=f"cbloc_sub_{sm['id']}")])
        except Exception:
            pass
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data=cancel_callback)])
    return InlineKeyboardMarkup(kb)
