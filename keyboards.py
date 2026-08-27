# ============================================
# ⌨️ KEYBOARDS (with Button Size customization)
# ============================================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from button_system import decorate
# 🆕 v170.11 FIX: pehle inline `if 'resolve_button_style' in dir()` checks module
# level pe False hote the (import lazy tha) → product-detail buttons ka color
# (prod_buy/prod_favorite...) kabhi apply nahi hota tha. Ab top-level import.
try:
    from button_system import resolve_button_style, get_button_style, set_button_style
except Exception:
    def resolve_button_style(btn_id, group=None): return ""
    def get_button_style(btn_id): return ""
    def set_button_style(btn_id, style): pass
from utils import get_product_delivery_mode, get_product_mode_tag, build_manual_order_whatsapp_url, fmt_price

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
        # 🐛 v170.11 FIX: pehle `return default_label` hota tha (custom ignore
        # ho jata tha) → dynamic keys (prod_buy/prod_favorite...) rename hota
        # hi nahi tha. Ab custom return hota hai (premium emoji ke saath).
        size = _get_size()
        custom = get_setting(f"btn_label_{btn_id}_{size}", "")
        if custom:
            return custom  # admin override wins (premium emoji included)
        key = _BTN_I18N_MAP.get(btn_id)
        if not key:
            return default_label
        lang = get_user_lang(user_id) if user_id else "en"
        if lang == "en":
            return default_label
        if key:
            static = t(key, lang=lang)
            if static != key:
                return static
        # Dynamic display-time fallback for admin/custom/hardcoded labels.
        try:
            from i18n import tr_user
            return tr_user(default_label, user_id=user_id, lang=lang)
        except Exception:
            return default_label
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
# ════════════════════════════════════════════════════════════
# ⌨️ PERSISTENT REPLY KEYBOARD (bottom bar — always visible)
# ════════════════════════════════════════════════════════════
# 🆕 v170.12: ab ADMIN configurable (rename + reorder). Buttons:
#   home / howto / reseller  (freebies Batch 6 me add hoga)
_PERSIST_DEFAULTS = {
    "home":     "🏠 Menu",
    "howto":    "📚 How to Use",
    "reseller": "🔗 Reseller API",
    "freebies": "🎁 Freebies",
}

_PERSIST_IDS = ("home", "howto", "reseller", "freebies")


def persist_button_from_text(text, user_id=None):
    """🆕 v170.19: reply-keyboard text → pid matching. Admin ka CUSTOM label,
    translated default ya plain default — jo bhi button label abhi hai, usse
    match karo (🐛 FIX: pehle hardcoded emoji label se match hota tha → admin
    ne emoji hata kar label rename kiya to buttons kaam karna band ho gaye)."""
    t = (text or "").strip()
    if not t:
        return None
    for pid in _PERSIST_IDS:
        try:
            lbl = get_persist_label(pid, user_id=user_id)
            if lbl and t == str(lbl).strip():
                return pid
        except Exception:
            pass
    # safety fallback: default labels (emoji wale bhi)
    for pid, d in _PERSIST_DEFAULTS.items():
        if t == d:
            return pid
    # legacy aliases (purane labels jo kisi client me cache ho sakte hain)
    _legacy = {
        "🏠 Main Menu": "home",
        "📚 How to Use": "howto",
        "🔗 Reseller API": "reseller",
        "🎁 Freebies": "freebies",
    }
    if t in _legacy:
        return _legacy[t]
    return None


def get_persist_label(pid, user_id=None):
    """Persistent button ka label: admin override → default → (translate nahi
    hota kyunki admin ka custom text user-language independent hota hai)."""
    try:
        from database import get_setting
        custom = (get_setting(f"persist_label_{pid}", "") or "").strip()
        if custom:
            return custom
    except Exception:
        pass
    label = _PERSIST_DEFAULTS.get(pid, pid)
    # v137: default labels user language me translate hote hain
    try:
        from i18n import tr_user
        _t = tr_user(label, user_id=user_id)
        if _t:
            label = _t
    except Exception:
        pass
    return label


def get_persist_style(pid):
    """🆕 v170.15: REAL background color for a persistent reply-keyboard button.
    Bot API 9.4 ne KeyboardButton par bhi `style` add kiya hai:
      success (green) / primary (blue) / danger (red).
    Setting: persist_color_<pid> = green|blue|red (khali = default white)."""
    try:
        from database import get_setting
        c = (get_setting(f"persist_color_{pid}", "") or "").strip()
        return {"green": "success", "blue": "primary", "red": "danger"}.get(c, "")
    except Exception:
        return ""


def get_persist_emoji(pid):
    """🆕 v170.15: optional premium emoji ICON for a persistent button
    (KeyboardButton.icon_custom_emoji_id). Setting: persist_emoji_<pid>."""
    try:
        from database import get_setting
        return (get_setting(f"persist_emoji_{pid}", "") or "").strip()
    except Exception:
        return ""


def get_persist_order():
    """Persistent buttons ka order (admin-configurable, comma list)."""
    try:
        from database import get_setting
        raw = (get_setting("persist_order", "") or "").strip()
        if raw:
            ids = [x.strip() for x in raw.split(",") if x.strip() in _PERSIST_IDS]
            # baqi (naye) ids jo list me nahi, unhe end par add karo
            for pid in _PERSIST_IDS:
                if pid not in ids:
                    ids.append(pid)
            return ids
    except Exception:
        pass
    return list(_PERSIST_IDS)


def persistent_menu(user_id=None):
    """🆕 v170.15: configurable persistent reply keyboard — REAL background
    colors (green/blue/red) + premium emoji icons (Bot API 9.4 KeyboardButton
    style + icon_custom_emoji_id). Buttons: home/howto/reseller/freebies."""
    order = get_persist_order()
    buttons = []
    for pid in order:
        lbl = get_persist_label(pid, user_id=user_id)
        if not lbl:
            continue
        style = get_persist_style(pid) or None
        emoji_id = get_persist_emoji(pid) or None
        kw = {}
        if style:
            kw["style"] = style
        if emoji_id:
            kw["icon_custom_emoji_id"] = emoji_id
        buttons.append(KeyboardButton(lbl, **kw))
    # buttons ko rows me baanto (2 per row)
    rows = []
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i:i + 2])
    return ReplyKeyboardMarkup(
        rows, resize_keyboard=True, is_persistent=True
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
def all_products_keyboard(products, page=1, per_page=10, user=None, filter_mode="all", shop_mode=None):
    """🆕 v59: Added `filter_mode` param — renders Filter buttons (All/Available/
    Unavailable) on bottom row so user can switch between in-stock and out-of-stock
    views. `filter_mode` is one of 'all'/'available'/'unavailable'.
    """
    total = len(products)
    total_pages = max(1, (total + per_page - 1) // per_page)
    # Product/category changes can shrink a live catalog while a user is on a
    # later page. Clamp stale callback pages instead of rendering an empty row.
    try:
        page = max(1, min(int(page), total_pages))
    except (TypeError, ValueError):
        page = 1
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
    user_id = getattr(user, 'id', None) if user is not None else None
    # 🆕 v144: display format (grid = 2/row compact, list = 1/row full)
    try:
        from database import get_setting as _gs2
        _fmt = (_gs2("display_format", "raw") or "raw").strip().lower()
        if _fmt not in ("raw", "grid", "list"):
            _fmt = "raw"
    except Exception:
        _fmt = "raw"
    # 🆕 v144: per-category color map (catcolor_<cid>)
    _catcolors = {}
    try:
        from database import get_connection as _gc3
        _cn = _gc3(); _cur = _cn.cursor()
        for (k, v) in _cur.execute("SELECT key, value FROM bot_settings WHERE key LIKE 'catcolor_%'").fetchall():
            _catcolors[str(k).replace("catcolor_", "")] = (v or "").strip()
        _cn.close()
    except Exception:
        pass
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

        if _fmt == "grid":
            # compact 2-column labels (name + price, short)
            label = f"{this_prod_emoji}{p['name'][:16]} {fmt_price(p['price'])}" if s > 0 else f"{this_prod_emoji}{p['name'][:14]} ❌"
        elif _fmt == "list":
            label = f"{this_prod_emoji}{p['name']}  —  {fmt_price(p['price'])}" if s > 0 else f"{this_prod_emoji}{p['name']}  ❌"
        elif size == "small":
            label = f"{this_prod_emoji}{p['name'][:18]}" if s > 0 else f"❌ {p['name'][:18]}"
        elif size == "medium":
            label = f"{this_prod_emoji}{p['name']} — {fmt_price(p['price'])}" if s > 0 else f"{this_prod_emoji}{p['name']} ❌"
        elif size == "large":
            label = f"{this_prod_emoji}{p['name']} [{s}] — {fmt_price(p['price'])}" if s > 0 else f"{this_prod_emoji}{p['name']} ❌ — {fmt_price(p['price'])}"
        else:
            label = f"{this_prod_emoji}{p['name']} [Stock: {s}] — {fmt_price(p['price'])}" if s > 0 else f"{this_prod_emoji}{p['name']} ❌ Out of Stock — {fmt_price(p['price'])}"
        try:
            from i18n import tr_user
            label = tr_user(label, user_id=user_id)
        except Exception:
            pass
        from button_system import is_styled
        if is_styled(f"prod_{p['id']}"):
            label = _apply_styler(f"prod_{p['id']}", label)
        else:
            label = _apply_styler("shop_product", label)

        # 🎨 v46: auto background color (out=red / manual=blue / auto=green)
        _pstyle = auto_product_style(p)
        # 🆕 v144: per-category color override (only when in stock)
        try:
            _cid = str(p.get("category_id") or 0)
            if s > 0 and _cid in _catcolors and _catcolors[_cid]:
                _pstyle = _catcolors[_cid]
        except Exception:
            pass
        # 🆕 v45: If name has premium emoji, ALSO use icon_custom_emoji_id
        if make_premium_button:
            _btn = make_premium_button(label, emoji_id=(name_emoji_id or None),
                                       style=_pstyle or None,
                                       callback_data=f"prod_{p['id']}")
        else:
            _btn = InlineKeyboardButton(label, callback_data=f"prod_{p['id']}")
        if _fmt == "grid" and kb and len(kb[-1]) < 2:
            kb[-1].append(_btn)
        else:
            kb.append([_btn])

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

    # v170.63: Classic Shop keeps its existing product/filter rows and adds a
    # visible route back to the persisted Categorized picker.  Other screens
    # that reuse this keyboard leave ``shop_mode`` unset and remain unchanged.
    if shop_mode in ("categorized", "classic"):
        cat_label = "🗂️ Categorized ✓" if shop_mode == "categorized" else "🗂️ Categorized"
        classic_label = "📋 Classic ✓" if shop_mode == "classic" else "📋 Classic"
        kb.append([
            InlineKeyboardButton(cat_label, callback_data="shopmode_categorized"),
            InlineKeyboardButton(classic_label, callback_data="shopmode_classic"),
        ])

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
    user_id = getattr(user, 'id', None) if user is not None and not isinstance(user, dict) else (user.get('id') if isinstance(user, dict) else (user if isinstance(user, int) else None))
    # 🔧 BUG FIX: `'stock' in product` on a sqlite3.Row checks VALUES not keys.
    # Use a key list that works for both dict and Row.
    _pkeys = product.keys() if hasattr(product, 'keys') else (product if isinstance(product, dict) else [])
    stock = product['stock'] if (hasattr(product, '__getitem__') and 'stock' in _pkeys) else 1000
    size = _get_size()
    rows = []
    try:
        if user_id:
            from database import is_favorite
            fav = is_favorite(user_id, pid)
            fav_lbl = _translate_btn_label("prod_favorite", "💔 Remove Favorite" if fav else "⭐ Add to Favorites", user_id=user_id)
            fav_lbl = _apply_styler("prod_favorite", fav_lbl)
            fav_style = resolve_button_style("prod_favorite")
            rows.append([_make_btn(fav_lbl, callback_data=f"fav_toggle_{pid}", style=fav_style)])
    except Exception:
        pass
    # Reusable static text/file delivery is unlimited even on old rows with
    # stock=0, matching database.build_delivery_detailed().
    _reusable_delivery = bool(str((product['delivery_text'] if 'delivery_text' in _pkeys else '') or '').strip()
                              or str((product['delivery_file_id'] if 'delivery_file_id' in _pkeys else '') or '').strip())
    if stock > 0 or _reusable_delivery:
        buy_lbl = _apply_styler("prod_buy", _translate_btn_label("prod_buy", {"small": "🛒", "medium": "🛒 Buy",
                     "large": "🛒 Buy Now", "xl": "🛒 Buy Now — Order this item"}.get(size, "🛒 Buy"), user_id=user_id))
        buyx_lbl = _apply_styler("prod_buyx", _translate_btn_label("prod_buyx", {"small": "🛒×", "medium": "🛒× Buy Multiple",
                      "large": "🛒× Buy Multiple (Bulk)", "xl": "🛒× Buy Multiple — Bulk order"}.get(size, "🛒× Buy Multiple"), user_id=user_id))
        # 🎨 v169: Apply background color and premium emoji support
        buy_style = resolve_button_style("prod_buy")
        buyx_style = resolve_button_style("prod_buyx")
        rows.append([_make_btn(buy_lbl, callback_data=f"buy_{pid}", style=buy_style)])
        rows.append([_make_btn(buyx_lbl, callback_data=f"buyx_{pid}", style=buyx_style)])
    else:
        req_lbl = _apply_styler("prod_req", _translate_btn_label("prod_req", "🔔 Notify Me When Available", user_id=user_id))
        req_style = resolve_button_style("prod_req")
        rows.append([_make_btn(req_lbl, callback_data=f"req_restock_{pid}", style=req_style)])
        
    rev_lbl = _apply_styler("prod_review", _translate_btn_label("prod_review", "⭐ View Reviews", user_id=user_id))
    rev_style = resolve_button_style("prod_review")
    rows.append([_make_btn(rev_lbl, callback_data=f"prodrev_{pid}", style=rev_style)])

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
    from database import is_payment_enabled
    if is_payment_enabled("points"):
        b = _rb("pay_pts", callback_data=f"pay_pts_{pid}_{qty}")
        if b:
            kb.append([b])
        else:
            kb.append([InlineKeyboardButton("💎 Pay with Points (Wallet)", callback_data=f"pay_pts_{pid}_{qty}")])
    # Grouped external methods
    if any(is_payment_enabled(m) for m in ("binance", "usdt_trc20", "usdt_bep20")):
        b = _rb("pay_group_binance", callback_data=f"pay_binance_menu_{pid}_{qty}")
        kb.append([b] if b else [InlineKeyboardButton("Binance", callback_data=f"pay_binance_menu_{pid}_{qty}")])
    if any(is_payment_enabled(m) for m in ("bybit", "bybit_pay", "bybit_usdt_trc20", "bybit_usdt_bep20")):
        b = _rb("pay_group_bybit", callback_data=f"pay_bybit_menu_{pid}_{qty}")
        kb.append([b] if b else [InlineKeyboardButton("Bybit", callback_data=f"pay_bybit_menu_{pid}_{qty}")])
    if is_payment_enabled("easypaisa"):
        b = _rb("pay_easypaisa", callback_data=f"pay_easy_{pid}_{qty}")
        kb.append([b] if b else [InlineKeyboardButton("EasyPaisa", callback_data=f"pay_easy_{pid}_{qty}")])
    if is_payment_enabled("jazzcash"):
        b = _rb("pay_jazzcash", callback_data=f"pay_jazz_{pid}_{qty}")
        kb.append([b] if b else [InlineKeyboardButton("JazzCash", callback_data=f"pay_jazz_{pid}_{qty}")])
    # ⭐ v161.25: Telegram Stars (product checkout)
    if is_payment_enabled("telegram_stars"):
        b = _rb("pay_stars", callback_data=f"pay_stars_{pid}_{qty}")
        kb.append([b] if b else [InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"pay_stars_{pid}_{qty}")])
    try:
        kb.extend(_custom_buttons_for("payment"))
    except Exception:
        pass
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
    try:
        from database import is_payment_enabled as _ipe
    except Exception:
        _ipe = lambda m: True
    kb = []
    if any(_ipe(m) for m in ("binance", "usdt_trc20", "usdt_bep20")):
        b = _rb("pay_group_binance", callback_data=f"ptspay_binance_menu_{amt}")
        kb.append([b] if b else [InlineKeyboardButton("Binance", callback_data=f"ptspay_binance_menu_{amt}")])
    if any(_ipe(m) for m in ("bybit", "bybit_pay", "bybit_usdt_trc20", "bybit_usdt_bep20")):
        b = _rb("pay_group_bybit", callback_data=f"ptspay_bybit_menu_{amt}")
        kb.append([b] if b else [InlineKeyboardButton("Bybit", callback_data=f"ptspay_bybit_menu_{amt}")])
    if _ipe("easypaisa"):
        b = _rb("pay_easypaisa", callback_data=f"ptspay_easy_{amt}")
        kb.append([b] if b else [InlineKeyboardButton("EasyPaisa", callback_data=f"ptspay_easy_{amt}")])
    if _ipe("jazzcash"):
        b = _rb("pay_jazzcash", callback_data=f"ptspay_jazz_{amt}")
        kb.append([b] if b else [InlineKeyboardButton("JazzCash", callback_data=f"ptspay_jazz_{amt}")])
    # ⭐ v161.25: Telegram Stars deposit
    if _ipe("telegram_stars"):
        b = _rb("pay_stars", callback_data=f"ptspay_stars_{amt}")
        kb.append([b] if b else [InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"ptspay_stars_{amt}")])
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
    """Editable category manager with visibility/order presentation controls."""
    try:
        from button_system import make_premium_button, extract_emoji_from_html, is_styled
        from utils import html_strip_tags
    except Exception:
        make_premium_button = None
        extract_emoji_from_html = None
        is_styled = lambda _key: False
        html_strip_tags = lambda x: str(x or "")
    kb = []
    for cat in cats:
        c = dict(cat)
        cid = int(c.get("id") or 0)
        raw_name = str(c.get("name") or "Category")
        raw_emoji = str(c.get("emoji") or "🏷️")
        if extract_emoji_from_html:
            name_id, name = extract_emoji_from_html(raw_name)
            icon_id, icon = extract_emoji_from_html(raw_emoji)
        else:
            name_id = icon_id = ""
            name, icon = html_strip_tags(raw_name), html_strip_tags(raw_emoji)
        custom_id = name_id or icon_id
        label = (name or "Category") if custom_id else f"🏷️ {icon} {name or 'Category'}"
        if not int(c.get("is_active", 1) or 0):
            label += "  ·  🚫 Disabled"
        elif int(c.get("is_hidden", 0) or 0):
            label += "  ·  🙈 Hidden"
        if is_styled(f"cat_{cid}"):
            label = _apply_styler(f"cat_{cid}", label)
        else:
            label = _apply_styler("shop_category", label)
        style = str(c.get("button_style") or "primary").strip().lower()
        if style not in ("primary", "success", "danger"):
            style = "primary"
        if custom_id and make_premium_button:
            label = (f'[[HTML]]<tg-emoji emoji-id="{custom_id}">◼️</tg-emoji> '
                     f"{label}")
            kb.append([make_premium_button(label, style=style,
                                           callback_data=f"viewcat_{cid}")])
        else:
            kb.append([_make_btn(label, style=style, callback_data=f"viewcat_{cid}")])
    kb.append([InlineKeyboardButton("⚙️ Category Picker Settings", callback_data="catpresent")])
    kb.append([_btn("➕", "➕ Add", "➕ Add Category", "➕ Add New Category", callback_data="add_category")])
    kb.append([_btn("🔙", "🔙 Return", "🔙 Return", "🔙 Back to Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)

ADMIN_PRODUCTS_PAGE_SIZE = 20


def admin_products_page_meta(prods, page=0, per_page=ADMIN_PRODUCTS_PAGE_SIZE):
    """Return a Telegram-safe page of the owner Edit Items catalog.

    Telegram accepts at most 100 inline buttons in one keyboard.  Restored
    stores commonly have more products than that, so never render the whole
    admin catalog in a single reply markup.
    """
    items = list(prods or [])
    try:
        per_page = int(per_page)
    except (TypeError, ValueError):
        per_page = ADMIN_PRODUCTS_PAGE_SIZE
    # Five permanent action rows plus two navigation buttons must remain
    # comfortably below Telegram's 100-button ceiling even for direct callers.
    per_page = max(1, min(per_page, 80))
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 0
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    return items[start:start + per_page], page, total_pages, len(items)


def admin_products_keyboard(prods, page=0, per_page=ADMIN_PRODUCTS_PAGE_SIZE):
    """Paginated owner Edit Items keyboard with premium-emoji-safe labels.

    Keeping this list paginated avoids Telegram rejecting a restored catalog
    with more than 100 buttons, which otherwise looks like a non-responsive
    Edit Items button to the owner.
    """
    from button_system import is_styled
    try:
        from button_system import make_premium_button, extract_emoji_from_html
    except Exception:
        make_premium_button = None
        extract_emoji_from_html = None
    page_prods, page, total_pages, _total = admin_products_page_meta(
        prods, page=page, per_page=per_page)
    kb = []
    for p in page_prods:
        raw = p.get('name', '') if hasattr(p, 'get') else p['name']
        raw = raw or ''
        if extract_emoji_from_html:
            ne_id, plain = extract_emoji_from_html(raw)
        else:
            ne_id, plain = "", raw
        # Admin "Edit Items" list should show clean product names only.
        # Status/format/stock are visible after tapping product details; keeping
        # them here made rows unreadable (ACTIVE | FORMAT | EMAIL PASS...).
        lbl = plain or raw
        try:
            # If this is a supplier product with a manually fixed plain emoji
            # (no premium custom_emoji_id), prepend it to the clean name.
            ext_id = int((p.get('ext_product_id', 0) if hasattr(p, 'get') else p['ext_product_id']) or 0)
            if ext_id and not ne_id:
                from ext_suppliers import get_ext_product as _get_ext_product
                ep = _get_ext_product(ext_id) or {}
                echar = str(ep.get('emoji_char') or '').strip()
                if echar and not str(lbl).lstrip().startswith(echar):
                    lbl = f"{echar} {lbl}"
        except Exception:
            pass
        if len(lbl) > 96:
            lbl = lbl[:93] + '...'
        if is_styled(f"prod_{p['id']}"):
            lbl = _apply_styler(f"prod_{p['id']}", lbl)
        else:
            lbl = _apply_styler("shop_product", lbl)
        if ne_id and make_premium_button:
            kb.append([make_premium_button(lbl, emoji_id=ne_id,
                                            callback_data=f"viewprod_{p['id']}")])
        else:
            kb.append([InlineKeyboardButton(lbl, callback_data=f"viewprod_{p['id']}")])

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Previous",
                                             callback_data=f"adminprodpg_{page - 1}"))
        # The page indicator lives in the screen heading. Do not make it a
        # clickable no-op button: Telegram rejects an identical edit as
        # "message is not modified", which could otherwise create a duplicate
        # fallback message if the owner taps the current page label.
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Next ➡️",
                                             callback_data=f"adminprodpg_{page + 1}"))
        kb.append(nav)

    kb.append([_btn("➕", "➕ Add", "➕ Add Item", "➕ Add New Product", callback_data="add_product")])
    kb.append([InlineKeyboardButton("💰 Bulk Price Editor", callback_data="bulkprice_start")])
    # 🆕 v157: Bulk Discount (users see discount + destination alert)
    kb.append([InlineKeyboardButton("🎉 Bulk Discount", callback_data="bdisc_start")])
    kb.append([InlineKeyboardButton("🗑️ Bulk Delete Items", callback_data="bulkprod_start")])
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
    """Owner product-category picker, including safe premium category icons."""
    try:
        from button_system import make_premium_button, extract_emoji_from_html
        from utils import html_strip_tags
    except Exception:
        make_premium_button = None
        extract_emoji_from_html = None
        html_strip_tags = lambda value: str(value or "")
    kb = []
    for category in cats:
        cat = dict(category)
        cid = int(cat.get("id") or 0)
        raw_name = str(cat.get("name") or "Category")
        raw_icon = str(cat.get("emoji") or "📦")
        if extract_emoji_from_html:
            name_id, name = extract_emoji_from_html(raw_name)
            icon_id, icon = extract_emoji_from_html(raw_icon)
        else:
            name_id = icon_id = ""
            name, icon = html_strip_tags(raw_name), html_strip_tags(raw_icon)
        premium_id = name_id or icon_id
        label = (name or "Category") if premium_id else f"{icon} {name or 'Category'}"
        label = label[:60].rstrip() or "Category"
        if premium_id and make_premium_button:
            kb.append([make_premium_button(label, emoji_id=premium_id,
                                           callback_data=f"selcat_{cid}")])
        else:
            kb.append([InlineKeyboardButton(label, callback_data=f"selcat_{cid}")])
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
    # 🆕 v170.46: Message Effects (global + per-command)
    kb.append([
        InlineKeyboardButton("✨ Message Effects", callback_data="fxpanel"),
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
        # 🆕 v141: Premium emoji — same rename flow (premium capture supported),
        # but with a dedicated button so admins know they can add animated emojis.
        [InlineKeyboardButton("✨ Premium Emoji", callback_data=f"mbrenm_{btn_id}_medium")],
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

    # 🆕 v141: Shape / Display-Format / Padding — opens the Inline Button
    # Styler for this registry button (size / align / pad / shape). The styler
    # already supports reg_<bid> keys via _apply_styler("reg_<bid>", ...).
    kb.append([InlineKeyboardButton("📐 Shape / Size / Padding", callback_data=f"bs_edit_reg_{btn_id}")])
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

def _category_picker_columns():
    """Configured picker width; default remains the screenshot-style 2 columns."""
    try:
        from database import get_setting
        value = int(get_setting("shop_category_columns", "2") or 2)
        return value if value in (1, 2) else 2
    except Exception:
        return 2


# v170.66: Telegram sizes inline buttons from their label text.  Category names
# such as "AI" therefore used to look like tiny chips beside longer names even
# though both buttons occupied one Python keyboard row.  The reference layout
# is a true visual two-column grid, so unstylized category labels are clipped
# and padded to one consistent, mobile-safe visual width.  A real owner style
# override still wins through the existing Button Styler.
_CATEGORY_PICKER_TWO_COLUMN_WIDTH = 24
_CATEGORY_PICKER_PAD_CHAR = "\u3164"  # Hangul Filler: visibly blank, not trimmed by Telegram.


def _category_picker_visual_width(text):
    """Approximate Telegram label width using the Button Styler's emoji rule."""
    width = 0
    for char in str(text or ""):
        codepoint = ord(char)
        width += 2 if codepoint >= 0x1F000 or 0x2600 <= codepoint <= 0x27BF else 1
    return width


def _category_picker_clip_label(label, max_width):
    """Keep a two-column category label within its fixed visual slot."""
    label = str(label or "").strip()
    if _category_picker_visual_width(label) <= max_width:
        return label
    # Reserve one visual unit for a clear truncation marker.  This prevents an
    # unusually long category name from making just one button wider than its
    # paired category and breaking the screenshot-style grid.
    budget = max(1, int(max_width) - 1)
    kept, used = [], 0
    for char in label:
        char_width = _category_picker_visual_width(char)
        if used + char_width > budget:
            break
        kept.append(char)
        used += char_width
    return ("".join(kept).rstrip() or "Category") + "…"


def _category_picker_icon_snug_fill(label):
    """v170.77: AUTO right-fill so icon-tile text always reaches the icon.

    Telegram clients pin an API icon at the LEFT edge of the button while the
    text is centered independently in the full tile width.  A fixed filler
    count therefore worked only for long names — short names ("Rename") were
    still centered with a gap.  The fill is now computed from the label's own
    visual width against a target that exceeds the tile width on large
    phones, guaranteeing overflow: overflowing centered text renders from its
    START (left-anchored), so the name lands right beside the icon and only
    invisible fillers are clipped off-screen.
    """
    width = _category_picker_visual_width(label)
    target = 34 if _category_picker_columns() == 2 else 68
    # Hangul filler is visually ≈ 2 latin units wide.
    return min(40, max(0, -(-(target - width) // 2)))


def _category_picker_default_grid_label(label, has_custom_icon=False, snug=True):
    """Return the category label for the default grid, honoring owner styling.

    v170.72: no forced filler padding — Telegram centers plain labels itself.
    v170.73: owner-editable padding + text alignment via the Category Picker
    Settings panel (Admin → Categories → Picker Settings):
      * ``shop_category_pad``   (0-12): invisible filler units that make the
        label look wider/fuller ("bigger" tiles). 0 = compact native look.
      * ``shop_category_align`` (left/center/right): where the text sits.
        Left/right need fillers on the opposite side to visibly shift text,
        so a minimum effective padding is used for those modes even at 0.
    """
    max_width = _CATEGORY_PICKER_TWO_COLUMN_WIDTH - (2 if has_custom_icon else 0)
    label = _category_picker_clip_label(label, max_width)
    try:
        from database import get_setting
        pad = int(get_setting("shop_category_pad", "0") or 0)
        align = str(get_setting("shop_category_align", "center") or "center").strip().lower()
        icon_fill = int(get_setting("shop_category_icon_fill", "8") or 8)
    except Exception:
        pad, align, icon_fill = 0, "center", 8
    pad = max(0, min(pad, 12))
    icon_fill = max(0, min(icon_fill, 14))
    if align not in ("left", "center", "right"):
        align = "center"
    if align == "center":
        left = right = pad
        # v170.83: Telegram splits a row's width by each button's label
        # length, so clean short names ("VPNS") rendered as tiny chips next
        # to long ones — the owner wants every tile as big and equal as the
        # v170.79 screenshot.  Labels are therefore padded SYMMETRICALLY to
        # one uniform visual width: equal fillers on BOTH sides keep the
        # text (and an in-text emoji) perfectly centered while every tile
        # claims the same footprint.  The target stays safely below the
        # tile's visible capacity so the string never overflows (overflow
        # would left-anchor the text and break centering).
        target = 16 if has_custom_icon else 18
        width = _category_picker_visual_width(label)
        if width < target:
            # Hangul filler renders ≈ 2 latin units wide; floor keeps the
            # final width safely UNDER the target so no device overflows.
            each = max(0, (target - width) // 4)
            left += each
            right += each
    else:
        # One-sided fillers push the text to the other edge.  Even at pad 0 a
        # small effective padding is required for the shift to be visible.
        total = max(pad, 3) * 2
        left, right = (0, total) if align == "left" else (total, 0)
    # v170.77: an API-attached premium icon is pinned by Telegram at the LEFT
    # edge of the tile while the text is centered separately.  The right-side
    # fill is now AUTO-SIZED per label so even short names overflow and pin
    # hard-left beside the icon.  The owner setting fine-tunes it:
    #   0 = off (old centered look) · 8 = neutral auto · below/above 8 nudges
    #   the auto amount smaller/larger.
    if snug and has_custom_icon and align != "right" and icon_fill > 0:
        snug = _category_picker_icon_snug_fill(label) + (icon_fill - 8)
        right = max(right, max(0, snug))
    if left <= 0 and right <= 0:
        return label
    return (_CATEGORY_PICKER_PAD_CHAR * left) + label + (_CATEGORY_PICKER_PAD_CHAR * right)


def _category_picker_spacer():
    """Safe blank second cell so an odd final category remains half-width.

    Telegram has no non-button grid spacer.  A single Hangul-filler no-op has
    a stable half-row footprint (Telegram equalizes widths within the row),
    exposes no product/category action, and is handled by the app's existing
    generic ``noop`` callback.
    """
    return InlineKeyboardButton(_CATEGORY_PICKER_PAD_CHAR,
                                callback_data="noop")


def _category_picker_button(info, columns=2):
    """Build one category button with a real Telegram custom-emoji icon.

    Category names and icons are stored in the same ``[[HTML]]<tg-emoji>``
    form as existing product labels.  Inline buttons do not parse HTML, so the
    custom emoji must become ``icon_custom_emoji_id`` through ``_make_btn``.
    Telegram allows one custom icon per button; a premium emoji in the name is
    deliberately preferred over the optional icon field because it is what the
    owner sees and edits as the category display name.
    """
    try:
        from button_system import extract_emoji_from_html, is_styled
        from utils import html_strip_tags
    except Exception:
        extract_emoji_from_html = None
        is_styled = lambda _key: False
        html_strip_tags = lambda x: str(x or "")

    cid = int(info.get("id") or 0)
    raw_name = str(info.get("name") or "Category")
    raw_emoji = str(info.get("emoji") or "")
    if extract_emoji_from_html:
        name_emoji_id, name_text = extract_emoji_from_html(raw_name)
        icon_emoji_id, icon_text = extract_emoji_from_html(raw_emoji)
    else:
        name_emoji_id = icon_emoji_id = ""
        name_text, icon_text = html_strip_tags(raw_name), html_strip_tags(raw_emoji)
    name_text = (name_text or html_strip_tags(raw_name) or "Category").strip()
    icon_text = (icon_text or html_strip_tags(raw_emoji) or "").strip()

    # v170.76: the separate icon system is removed — the button icon comes
    # ONLY from a Premium custom emoji inside the category NAME.  A legacy
    # emoji field still shows inline as plain text (e.g. "🤖 Ai Tools") so
    # old categories keep their look, but it never becomes an API icon.
    # v170.81: owner-selectable icon style.
    #   "premium" → real premium image icon, Telegram pins it at the LEFT
    #               edge (client limitation — cannot be centered); text is
    #               pulled snugly beside it.
    #   "emoji"   → the premium emoji's plain fallback stays INSIDE the text,
    #               so emoji + name render perfectly CENTERED together.
    #   "both"    → hybrid trick: the premium image icon stays at the left
    #               AND the themed fallback emoji rides inside the centered
    #               text ("🤖 Chatgpt" centered + premium icon left).
    icon_mode = "premium"
    try:
        from database import get_setting
        icon_mode = str(get_setting("shop_category_icon_mode", "premium")
                        or "premium").strip().lower()
    except Exception:
        pass
    custom_emoji_id = name_emoji_id
    if icon_mode in ("emoji", "both"):
        fallback = ""
        if name_emoji_id:
            import re as _re
            m = _re.search(r"<tg-emoji[^>]*>(.*?)</tg-emoji>", raw_name)
            fallback = (m.group(1) or "").strip() if m else ""
        if icon_mode == "emoji":
            custom_emoji_id = ""
        label = f"{fallback or icon_text} {name_text}".strip()
    else:
        label = name_text if custom_emoji_id else f"{icon_text} {name_text}".strip()
    label = label[:48].rstrip() or "Category"
    # A deliberate per-category or global Button Styler choice remains fully
    # editable.  Otherwise the default two-column picker uses equal-width,
    # centered tiles exactly like the owner-provided reference layout.
    if is_styled(f"cat_{cid}"):
        label = _apply_styler(f"cat_{cid}", label)
    elif is_styled("shop_category"):
        label = _apply_styler("shop_category", label)
    else:
        # v170.73: the owner's picker padding + alignment settings apply to
        # every unstylized category tile in both one- and two-column grids.
        # v170.81 DISCOVERY: the main menu's Shop Now button proves that a
        # premium icon renders ADJACENT to the button text and centers WITH
        # it whenever the text is clean — the old left-pinned look was our
        # own snug-fill fillers pushing the text full-width.  So the exact
        # Shop Now formula (clean label + icon, ZERO fillers) is now used:
        # premium icon + name render centered together.  No snug fill in any
        # icon mode.
        label = _category_picker_default_grid_label(
            label, has_custom_icon=bool(custom_emoji_id), snug=False)

    # ``_make_btn`` delegates to make_premium_button and therefore maps this
    # sentinel to icon_custom_emoji_id rather than leaking markup to users.
    if custom_emoji_id:
        label = (f'[[HTML]]<tg-emoji emoji-id="{custom_emoji_id}">◼️</tg-emoji> '
                 f"{label}")
    style = str(info.get("button_style") or "primary").strip().lower()
    if style not in ("primary", "success", "danger"):
        style = "primary"
    return _make_btn(label, callback_data=f"shopcat_{cid}", style=style)


def shop_categories_keyboard(grouped, user_mode="categorized"):
    """Compact user-facing category picker.

    Categories are provided by the database in persisted display order.  The
    editable default is two per row; unstylized buttons receive equal visual
    width so each pair fills one row like the owner-provided reference.  Each
    category defaults to Telegram's blue ``primary`` style.  Unlike the old
    picker, counts are intentionally omitted for the clean screenshot-style
    visual; empty categories are decided by the database presentation controls
    before they reach this function.
    """
    kb = []
    buttons = []
    columns = _category_picker_columns()
    for _cid, info in (grouped or {}).items():
        try:
            buttons.append(_category_picker_button(dict(info), columns=columns))
        except Exception:
            # A malformed legacy label must not prevent every other category
            # from appearing.  The safe plain fallback remains blue and uses
            # the same default two-column width treatment.
            try:
                name = str(info.get("name") or "Category")[:48]
                name = _category_picker_default_grid_label(name)
                buttons.append(_make_btn(name, callback_data=f"shopcat_{int(_cid)}",
                                         style="primary"))
            except Exception:
                pass
    for pos in range(0, len(buttons), columns):
        row = buttons[pos:pos + columns]
        # Owner-selected behavior for an odd count: keep the real category in
        # the left half of the fixed two-column grid instead of stretching it
        # across a full row.
        if columns == 2 and len(row) == 1:
            row.append(_category_picker_spacer())
        kb.append(row)
    if not buttons:
        kb.append([InlineKeyboardButton("📭 No visible categories yet", callback_data="shop")])

    # A visible, one-tap and persisted mode selector.  The selected option is
    # still clickable (a harmless refresh) so Telegram has no disabled-button
    # ambiguity and users can always see both supported modes.
    categorized_label = "🗂️ Categorized ✓" if user_mode == "categorized" else "🗂️ Categorized"
    classic_label = "📋 Classic ✓" if user_mode == "classic" else "📋 Classic"
    kb.append([
        InlineKeyboardButton(categorized_label, callback_data="shopmode_categorized"),
        InlineKeyboardButton(classic_label, callback_data="shopmode_classic"),
    ])
    # v170.65: the picker and every category page share the same Home registry
    # control, so one Screen-by-Screen Editor change reaches both routes.
    home_b = _rb("nav_shop_home", callback_data="main_menu")
    if home_b is None:
        home_b = InlineKeyboardButton(_apply_styler("shop_home", "🏠 Home"),
                                      callback_data="main_menu")
    pts_lbl = _apply_styler("shop_buy_points", "💎 Buy Points")
    kb.append([
        home_b,
        InlineKeyboardButton(pts_lbl, callback_data="buy_points"),
    ])
    return InlineKeyboardMarkup(kb)


def shop_category_footer_keyboard(user=None):
    """The exact shared Back + Home footer for every category product page.

    Both are essential registry buttons.  Their label, premium icon, padding
    and color are changed once in Screen-by-Screen Editor → Shop / Product List
    and are then rendered identically for every category.
    """
    user_id = (getattr(user, "id", None) if user is not None and not isinstance(user, dict)
               else (user.get("id") if isinstance(user, dict) else (user if isinstance(user, int) else None)))
    back_b = _rb("nav_categories_back", callback_data="shop", user_id=user_id)
    home_b = _rb("nav_shop_home", callback_data="main_menu", user_id=user_id)
    # Essential registry entries normally cannot be hidden.  Keep a safe,
    # navigable fallback if an older/custom registry ever fails to load.
    if back_b is None:
        back_b = InlineKeyboardButton(_apply_styler("shop_back_cats", "🔙 Categories"),
                                      callback_data="shop")
    if home_b is None:
        home_b = InlineKeyboardButton(_apply_styler("shop_home", "🏠 Home"),
                                      callback_data="main_menu")
    return InlineKeyboardMarkup([[back_b, home_b]])


def shop_category_products_keyboard(products, cat_id, page=1, per_page=10, user=None):
    """Products inside a specific category — paginated"""
    total = len(products)
    total_pages = max(1, (total + per_page - 1) // per_page)
    # Clamp an old category-page callback after products were hidden/deleted.
    try:
        page = max(1, min(int(page), total_pages))
    except (TypeError, ValueError):
        page = 1
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
    user_id = getattr(user, 'id', None) if user is not None else None
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
            label = f"{prefix}{this_prod_emoji}{p['name']} — {fmt_price(p['price'])}" if s > 0 else f"{prefix}{this_prod_emoji}{p['name']} ❌"
        elif size == "large":
            label = f"{prefix}{this_prod_emoji}{p['name']} [{s}] — {fmt_price(p['price'])}" if s > 0 else f"{prefix}{this_prod_emoji}{p['name']} ❌ — {fmt_price(p['price'])}"
        else:
            label = f"{prefix}{this_prod_emoji}{p['name']} [Stock: {s}] — {fmt_price(p['price'])}" if s > 0 else f"{prefix}{this_prod_emoji}{p['name']} ❌ Out of Stock — {fmt_price(p['price'])}"
        try:
            from i18n import tr_user
            label = tr_user(label, user_id=user_id)
        except Exception:
            pass
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
    # v170.65: category pagination uses the same global prev/next registry
    # entries shown in the Shop Screen Editor.  Only callback data changes.
    nav = []
    if page > 1:
        prev_b = _rb("nav_shop_prev_page", callback_data=f"shopcatpg_{cat_id}_{page-1}",
                     user_id=user_id)
        nav.append(prev_b or InlineKeyboardButton(
            _apply_styler("shop_pagination", "⬅️"),
            callback_data=f"shopcatpg_{cat_id}_{page-1}"))
    if page < total_pages:
        next_b = _rb("nav_shop_next_page", callback_data=f"shopcatpg_{cat_id}_{page+1}",
                     user_id=user_id)
        nav.append(next_b or InlineKeyboardButton(
            _apply_styler("shop_pagination", "➡️"),
            callback_data=f"shopcatpg_{cat_id}_{page+1}"))
    if nav:
        kb.append(nav)
    # The category page intentionally has exactly these two shared navigation
    # controls — no Classic-mode switch here.  Classic remains safely available
    # from the category picker, while Back always returns to that picker.
    kb.extend(shop_category_footer_keyboard(user=user).inline_keyboard)
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
        [InlineKeyboardButton("🪙 Crypto / Bybit Settings", callback_data="pm_crypto")],
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
        amt = f"{fmt_price(d['price'])}" if order_type == 'product' else f"Rs.{d['binance_amount']:.0f}" if d['binance_amount'] else f"{fmt_price(d['price'])}"

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
