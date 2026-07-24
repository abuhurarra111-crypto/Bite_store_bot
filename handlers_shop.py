# ============================================
# 🛍️ SHOP — Raw OR Carousel format
# ============================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
from database import (get_all_active_products, get_product,
                      get_setting, get_toggle, get_products_grouped_by_category)
from keyboards import (all_products_keyboard, product_detail_keyboard, back_btn,
                       shop_categories_keyboard,
                       shop_category_products_keyboard)
from config import DEFAULT_RESPONSES, USD_TO_PKR_RATE, ADMIN_ID
from utils import (fmt_price,
    escape_md, format_pkr, nav_push,
    get_product_delivery_mode, get_product_mode_tag,
    build_manual_order_whatsapp_url,
    is_html_value, strip_html_prefix, name_for_message_html,
    contains_premium_markup, html_strip_tags, smart_text_and_mode,
)


# 🔧 BUG FIX: shop_flash_callback() called _safe_edit() but it was never
# defined or imported in this module (NameError → "Active Flash Sales" screen
# crashed). Define it locally, matching the helper used in other handlers.
async def _safe_edit(q, text, **kwargs):
    send_text, send_mode = smart_text_and_mode(text, kwargs.get("parse_mode", "Markdown"))
    k0 = dict(kwargs); k0["parse_mode"] = send_mode
    try:
        await q.edit_message_text(send_text, **k0); return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in k0:
            k = dict(k0); k.pop("parse_mode")
            try:
                await q.edit_message_text(send_text, **k); return
            except Exception: pass
    try:
        await q.edit_message_caption(caption=send_text, **k0); return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in k0:
            k = dict(k0); k.pop("parse_mode")
            try:
                await q.edit_message_caption(caption=send_text, **k); return
            except Exception: pass
    try:
        await q.message.reply_text(send_text, **k0)
    except Exception:
        k = dict(k0); k.pop("parse_mode", None)
        try: await q.message.reply_text(send_text, **k)
        except Exception: pass


def _get_resp(key, user_id=None):
    """🆕 v79: Optional user_id triggers per-language lookup first."""
    if user_id is not None:
        try:
            from i18n_responses import get_translated_response
            tr = get_translated_response(key, user_id=user_id)
            if tr is not None:
                return tr
        except Exception:
            pass
    from database import get_response_with_auto_register
    return get_response_with_auto_register(key, DEFAULT_RESPONSES.get(key, ""))


def _sold_line(p):
    """🆕 '🔥 Sold: N' line shown to customers (fake base + real sales).
    Controlled by the 'show_sold' toggle (ON by default). Returns '' if hidden."""
    try:
        if get_toggle("show_sold") == "0":
            return ""
        from database import get_sold_display
        n = get_sold_display(p)
        if n <= 0:
            return ""
        return f"🔥 Sold: *{n}*\n"
    except Exception:
        return ""


def _get_display_format():
    """Returns 'raw' or 'carousel'. Default: raw"""
    fmt = get_setting("display_format", "raw").lower().strip()
    return fmt if fmt in ("raw", "carousel") else "raw"


# 🆕 v42: Build the product detail text in either Markdown OR HTML mode,
# depending on whether the product name was saved with a premium-emoji
# HTML representation. Returns (text, parse_mode).
def _build_detail_text(p):
    import html as _html
    name_html_aware = is_html_value(p['name'])
    rate = float(get_setting("usd_pkr_rate", USD_TO_PKR_RATE))
    pkr = format_pkr(p['price'], rate)
    is_flash = dict(p).get('is_flash_sale', 0)
    f_price = dict(p).get('flash_price', 0) if is_flash else 0
    pkr_f = format_pkr(f_price, rate) if is_flash else ""

    show_warranty = get_toggle("show_warranty") == "1"
    show_quantity = get_toggle("show_quantity") == "1"
    show_stock = get_toggle("show_stock") == "1"

    try: warranty = p['warranty']
    except (IndexError, KeyError): warranty = ""
    try: quantity = p['quantity']
    except (IndexError, KeyError): quantity = ""

    html_needed = name_html_aware or contains_premium_markup(p.get('description', '')) or contains_premium_markup(warranty) or contains_premium_markup(quantity)
    if html_needed:
        # HTML mode — premium emojis render anywhere in product content
        title = name_for_message_html(p['name'])
        text = f"📦 <b>{title}</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        if p['description']:
            desc_html = name_for_message_html(p['description']) if contains_premium_markup(p['description']) else _html.escape(html_strip_tags(str(p['description'])))
            text += f"📝 {desc_html}\n\n"
        if is_flash:
            text += (f"💰 Price: <s>{fmt_price(p['price'])}</s> ⚡ "
                     f"<b>${f_price:.2f}</b> ≈ <b>{_html.escape(pkr_f)}</b>\n")
        else:
            text += f"💰 Price: <b>{fmt_price(p['price'])}</b> ≈ <b>{_html.escape(pkr)}</b>\n"
        if show_warranty and warranty:
            warranty_html = name_for_message_html(warranty) if contains_premium_markup(warranty) else _html.escape(html_strip_tags(str(warranty)))
            text += f"🛡️ Warranty: <b>{warranty_html}</b>\n"
        if show_quantity and quantity:
            qty_html = name_for_message_html(quantity) if contains_premium_markup(quantity) else _html.escape(html_strip_tags(str(quantity)))
            text += f"📦 Quantity: <b>{qty_html}</b>\n"
        if show_stock:
            text += f"📊 In Stock: <b>{p['stock']}</b>\n"
        text += _sold_line_html(p)
        return text, "HTML"

    # Default Markdown path (unchanged behaviour)
    text = f"📦 *{escape_md(p['name'])}*\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    if p['description']:
        text += f"📝 {escape_md(p['description'])}\n\n"
    if is_flash:
        text += f"💰 Price: ~{fmt_price(p['price'])}~ ⚡ *${f_price:.2f}* ≈ *{pkr_f}*\n"
    else:
        text += f"💰 Price: *{fmt_price(p['price'])}* ≈ *{pkr}*\n"
    if show_warranty and warranty:
        text += f"🛡️ Warranty: *{escape_md(warranty)}*\n"
    if show_quantity and quantity:
        text += f"📦 Quantity: *{escape_md(quantity)}*\n"
    if show_stock:
        text += f"📊 In Stock: *{p['stock']}*\n"
    text += _sold_line(p)
    return text, "Markdown"


def _sold_line_html(p):
    """HTML variant of _sold_line() (no markdown asterisks)."""
    try:
        if get_toggle("show_sold") == "0":
            return ""
        from database import get_sold_display
        n = get_sold_display(p)
        if n <= 0:
            return ""
        return f"🔥 Sold: <b>{n}</b>\n"
    except Exception:
        return ""


# ════════════════════════════════════════════
# 🛒 SHOP ENTRY
# ════════════════════════════════════════════
def _use_categorized_shop():
    """Check toggle: shop should show categories first?"""
    return get_setting("shop_categorized", "0") == "1"


# 🆕 v59: Shop stock-based filter (all / available / unavailable)
DEFAULT_SHOP_FILTER_VALID = ("all", "available", "unavailable")


def _get_default_shop_filter():
    """Admin-configurable default filter for new users entering shop.
    Stored in bot_settings as `shop_default_filter`. Valid: all/available/unavailable.
    """
    val = (get_setting("shop_default_filter", "all") or "all").strip().lower()
    return val if val in DEFAULT_SHOP_FILTER_VALID else "all"


def _get_user_shop_filter(context):
    """Per-user (session-level) override of the shop filter. Falls back to admin's
    default if the user hasn't picked one yet."""
    f = context.user_data.get("shop_filter")
    if f in DEFAULT_SHOP_FILTER_VALID:
        return f
    return _get_default_shop_filter()


def _set_user_shop_filter(context, mode):
    """Persist user's filter choice for this chat session."""
    if mode in DEFAULT_SHOP_FILTER_VALID:
        context.user_data["shop_filter"] = mode
        # Also reset to page 1 when filter changes (else page count can overflow)
        context.user_data["shop_page"] = 1


async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    nav_push(context, 'shop')  # 🔙 Track navigation
    # 🆕 v59: Apply stock-based filter (all/available/unavailable)
    from database import get_products_filtered
    filter_mode = _get_user_shop_filter(context)
    products = get_products_filtered(filter_mode)
    # 🆕 v98: auto-group by first word (default ON, admin toggle in Customization)
    try:
        from utils import sort_products_by_first_word
        products = sort_products_by_first_word(products)
    except Exception:
        pass
    if not products:
        # 🆕 v59: friendly mode-aware message + button to switch filter back to All
        empty_text = _get_resp("no_products", user_id=q.from_user.id)
        if filter_mode == "unavailable":
            empty_text = _get_resp("shop_no_unavailable").format(empty=empty_text)
        elif filter_mode == "available":
            empty_text = _get_resp("shop_no_available").format(empty=empty_text)
        kb_back = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Show All Products", callback_data="shopfilter_all")],
            [InlineKeyboardButton("🏠 Home", callback_data="main_menu")],
        ])
        try:
            await q.edit_message_text(empty_text, parse_mode="Markdown", reply_markup=kb_back)
        except Exception:
            await context.bot.send_message(q.from_user.id, empty_text,
                                           parse_mode="Markdown", reply_markup=kb_back)
        return

    # 🆕 Phase D: If categorized mode is ON, show categories first
    if _use_categorized_shop():
        grouped = get_products_grouped_by_category()
        if len(grouped) > 1 or (len(grouped) == 1 and 0 in grouped):
            # More than one category OR uncategorized only — show the picker
            title = "🛒 *Shop — Categories*\n━━━━━━━━━━━━━━━━━━━━\n\nSelect a category to browse:"
            try:
                await q.edit_message_text(title, parse_mode="Markdown",
                                          reply_markup=shop_categories_keyboard(grouped))
            except Exception:
                try: await q.message.delete()
                except: pass
                await context.bot.send_message(q.from_user.id, title, parse_mode="Markdown",
                                              reply_markup=shop_categories_keyboard(grouped))
            return
        # If only one category exists and it has products → fall through to flat list

    fmt = _get_display_format()
    if fmt == "carousel":
        context.user_data['carousel_idx'] = 0
        await _show_carousel(update, context, products, 0, is_initial=True, user=q.from_user)
        return

    # ── Raw mode (flat list) ──
    page = context.user_data.get('shop_page', 1)
    # 🆕 v59: Pass filter_mode so keyboard can render filter toggle buttons
    kb, pg, tp = all_products_keyboard(products, page, user=q.from_user,
                                       filter_mode=filter_mode)
    title = _get_resp("shop_title", user_id=q.from_user.id).format(page=pg, total_pages=tp)
    # 🆕 v59: Append filter mode indicator
    title += f"\n_Filter: {_filter_label(filter_mode)}_"
    try:
        await q.edit_message_text(title, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        try: await q.message.delete()
        except: pass
        await context.bot.send_message(q.from_user.id, title, parse_mode="Markdown", reply_markup=kb)


def _filter_label(mode):
    """Human-readable label for a filter mode."""
    return {
        "all":         "📋 All Products",
        "available":   "✅ Available Only",
        "unavailable": "❌ Out of Stock Only",
    }.get(mode, "📋 All Products")


# 🆕 v59: Handle filter switch callbacks (shopfilter_all / shopfilter_available / shopfilter_unavailable)
async def shop_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch the shop filter (all/available/unavailable) and re-render shop."""
    q = update.callback_query
    await q.answer()
    mode = q.data.replace("shopfilter_", "")
    if mode not in DEFAULT_SHOP_FILTER_VALID:
        mode = "all"
    _set_user_shop_filter(context, mode)
    # Re-render shop with new filter
    await shop_callback(update, context)


# 🆕 NEW: View all products (bypass categories — flat list)
async def shop_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Flat product list (called when 'View All Products' tapped)"""
    q = update.callback_query
    await q.answer()
    nav_push(context, 'shop')  # 🔙 Back goes to shop
    products = get_all_active_products()
    if not products:
        await q.edit_message_text(_get_resp("no_products", user_id=q.from_user.id), parse_mode="Markdown", reply_markup=back_btn())
        return
    # 🆕 v98: auto-group by first word (default ON, admin toggle in Customization)
    try:
        from utils import sort_products_by_first_word
        products = sort_products_by_first_word(products)
    except Exception:
        pass
    page = 1
    context.user_data['shop_page'] = page
    kb, pg, tp = all_products_keyboard(products, page, user=q.from_user)
    title = _get_resp("shop_title", user_id=q.from_user.id).format(page=pg, total_pages=tp)
    try:
        await q.edit_message_text(title, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        try: await q.message.delete()
        except: pass
        await context.bot.send_message(q.from_user.id, title, parse_mode="Markdown", reply_markup=kb)


# 🆕 NEW: Show products of a specific category
async def shop_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User tapped a category in categorized shop"""
    q = update.callback_query
    await q.answer()
    nav_push(context, 'shop')  # 🔙 Back goes to shop categories
    cat_id = int(q.data.replace("shopcat_", ""))
    grouped = get_products_grouped_by_category()
    if cat_id not in grouped:
        await q.edit_message_text("❌ Category not found.", reply_markup=back_btn())
        return
    info = grouped[cat_id]
    products = info['products']
    # 🆕 v98: auto-group by first word within this category
    try:
        from utils import sort_products_by_first_word
        products = sort_products_by_first_word(products)
    except Exception:
        pass
    page = 1
    context.user_data['shop_cat_page'] = page
    kb, pg, tp = shop_category_products_keyboard(products, cat_id, page, user=q.from_user)
    title = f"📂 *{info['emoji']} {info['name']}*\n━━━━━━━━━━━━━━━━━━━━\n(Page {pg}/{tp})"
    try:
        await q.edit_message_text(title, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        try: await q.message.delete()
        except: pass
        await context.bot.send_message(q.from_user.id, title, parse_mode="Markdown", reply_markup=kb)


async def shop_category_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pagination inside a category"""
    q = update.callback_query
    await q.answer()
    # data format: shopcatpg_<cat>_<page>
    parts = q.data.replace("shopcatpg_", "").split("_")
    cat_id = int(parts[0]); page = int(parts[1])
    grouped = get_products_grouped_by_category()
    if cat_id not in grouped:
        await q.edit_message_text("❌", reply_markup=back_btn()); return
    info = grouped[cat_id]
    prods_sorted = info['products']
    # 🆕 v98: match grouping applied on page 1 so pagination stays consistent
    try:
        from utils import sort_products_by_first_word
        prods_sorted = sort_products_by_first_word(prods_sorted)
    except Exception:
        pass
    kb, pg, tp = shop_category_products_keyboard(prods_sorted, cat_id, page, user=q.from_user)
    title = f"📂 *{info['emoji']} {info['name']}*\n━━━━━━━━━━━━━━━━━━━━\n(Page {pg}/{tp})"
    await q.edit_message_text(title, parse_mode="Markdown", reply_markup=kb)


async def page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Raw mode pagination — 🆕 v59: respects current filter mode."""
    q = update.callback_query; await q.answer()
    nav_push(context, 'shop')  # 🔙 Back goes to shop
    page = int(q.data.split("_")[1])
    context.user_data['shop_page'] = page
    from database import get_products_filtered
    filter_mode = _get_user_shop_filter(context)
    products = get_products_filtered(filter_mode)
    # 🆕 v98: auto-group by first word — MUST match ordering used on page 1
    # otherwise page-2's items would be from ungrouped list
    try:
        from utils import sort_products_by_first_word
        products = sort_products_by_first_word(products)
    except Exception:
        pass
    if not products:
        # Filter became empty after stock change — re-route to shop_callback for proper empty UI
        await shop_callback(update, context)
        return
    kb, pg, tp = all_products_keyboard(products, page, user=q.from_user,
                                       filter_mode=filter_mode)
    title = _get_resp("shop_title", user_id=q.from_user.id).format(page=pg, total_pages=tp)
    title += f"\n_Filter: {_filter_label(filter_mode)}_"
    await q.edit_message_text(title, parse_mode="Markdown", reply_markup=kb)


# ════════════════════════════════════════════
# 🎠 CAROUSEL LOGIC
# ════════════════════════════════════════════

def _carousel_keyboard(idx, total, product, user=None):
    """Build navigation keyboard for carousel.
    🆕 v52: Prev/Next/Home buttons are now full registry buttons
    (editable via Customization → 🎨 Buttons → Navigation)."""
    from button_system import style_label as _sl
    from keyboards import _rb
    pid = product['id']
    nav = []
    if idx > 0:
        _b = _rb("nav_carousel_prev", callback_data="cnav_prev")
        if _b: nav.append(_b)
        else:
            nav.append(InlineKeyboardButton(_sl("cnav_prev", "⬅️ Prev"),
                                             callback_data="cnav_prev"))
    if product['stock'] > 0:
        nav.append(InlineKeyboardButton(_sl("cnav_buy", "🛒 Buy Now"),
                                         callback_data=f"buy_{pid}"))
    else:
        nav.append(InlineKeyboardButton(_sl("cnav_buy", "🔔 Notify Me"),
                                         callback_data=f"req_restock_{pid}"))
    if idx < total - 1:
        _b = _rb("nav_carousel_next", callback_data="cnav_next")
        if _b: nav.append(_b)
        else:
            nav.append(InlineKeyboardButton(_sl("cnav_next", "Next ➡️"),
                                             callback_data="cnav_next"))
    home_b = _rb("nav_shop_home", callback_data="main_menu")
    home_btn = home_b or InlineKeyboardButton(_sl("shop_home", "🏠 Home"), callback_data="main_menu")
    return InlineKeyboardMarkup([
        nav,
        [home_btn,
         InlineKeyboardButton(_sl("cnav_list", "📋 List View"), callback_data="cnav_listview")],
    ])


def _build_carousel_caption(p, idx, total):
    """Build product caption text for carousel.
    Returns plain text (Markdown). Premium-emoji aware variant returns HTML."""
    text, mode = _build_detail_text(p)
    # Append carousel footer in matching syntax
    if mode == "HTML":
        text += "\n━━━━━━━━━━━━━━━━━━━━\n"
        text += f"🎠 <b>Product {idx + 1} of {total}</b>"
    else:
        text += "\n━━━━━━━━━━━━━━━━━━━━\n"
        text += f"🎠 *Product {idx + 1} of {total}*"
    return text, mode


async def _show_carousel(update, context, products, idx, is_initial=False, user=None):
    """Display a product card in carousel mode at given index"""
    q = update.callback_query
    if idx < 0: idx = 0
    if idx >= len(products): idx = len(products) - 1
    context.user_data['carousel_idx'] = idx

    p = products[idx]
    caption, parse_mode = _build_carousel_caption(p, idx, len(products))
    kb = _carousel_keyboard(idx, len(products), p, user=user)

    show_photo = get_toggle("show_photo") == "1"
    try: photo_id = p['photo_id']
    except (IndexError, KeyError): photo_id = ""

    use_photo = show_photo and photo_id

    if is_initial:
        # Delete the original "Shop list" message and send fresh
        try: await q.message.delete()
        except: pass
        if use_photo:
            try:
                await context.bot.send_photo(q.from_user.id, photo=photo_id,
                                             caption=caption, parse_mode=parse_mode,
                                             reply_markup=kb)
                return
            except Exception:
                pass
        # Fallback: text only
        await context.bot.send_message(q.from_user.id, caption,
                                       parse_mode=parse_mode, reply_markup=kb)
        return

    # Navigation: try to edit existing message
    msg = q.message
    msg_has_photo = bool(msg and msg.photo)

    if use_photo:
        # Try to edit media (works whether previous was photo or text)
        try:
            await q.edit_message_media(
                media=InputMediaPhoto(media=photo_id, caption=caption, parse_mode=parse_mode),
                reply_markup=kb,
            )
            return
        except Exception:
            pass
        # Fallback: delete and resend
        try: await msg.delete()
        except: pass
        try:
            await context.bot.send_photo(q.from_user.id, photo=photo_id,
                                         caption=caption, parse_mode=parse_mode,
                                         reply_markup=kb)
            return
        except Exception:
            pass
        # Final fallback: send text
        await context.bot.send_message(q.from_user.id, caption,
                                       parse_mode=parse_mode, reply_markup=kb)
        return

    # No photo — text mode
    if msg_has_photo:
        # Previous was photo, need to delete and resend as text
        try: await msg.delete()
        except: pass
        await context.bot.send_message(q.from_user.id, caption,
                                       parse_mode=parse_mode, reply_markup=kb)
        return

    # Both old and new are text — simple edit
    try:
        await q.edit_message_text(caption, parse_mode=parse_mode, reply_markup=kb)
    except Exception:
        await context.bot.send_message(q.from_user.id, caption,
                                       parse_mode=parse_mode, reply_markup=kb)


async def carousel_nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Prev/Next/ListView buttons in carousel"""
    q = update.callback_query
    await q.answer()
    action = q.data.replace("cnav_", "")

    products = get_all_active_products()
    # 🆕 v98: apply auto-grouping to carousel too, for consistent order
    try:
        from utils import sort_products_by_first_word
        products = sort_products_by_first_word(products)
    except Exception:
        pass
    if not products:
        await context.bot.send_message(q.from_user.id, _get_resp("no_products", user_id=q.from_user.id),
                                       parse_mode="Markdown", reply_markup=back_btn())
        return

    if action == "listview":
        # Switch this user temporarily to raw view (one-time, doesn't change setting)
        try: await q.message.delete()
        except: pass
        context.user_data['shop_page'] = 1
        page = 1
        kb, pg, tp = all_products_keyboard(products, page, user=q.from_user)
        title = _get_resp("shop_title", user_id=q.from_user.id).format(page=pg, total_pages=tp)
        await context.bot.send_message(q.from_user.id, title,
                                       parse_mode="Markdown", reply_markup=kb)
        return

    idx = context.user_data.get('carousel_idx', 0)
    if action == "prev":
        idx -= 1
    elif action == "next":
        idx += 1
    await _show_carousel(update, context, products, idx, is_initial=False, user=q.from_user)


# ════════════════════════════════════════════
# 📦 PRODUCT DETAIL (Raw mode — when user taps a list item)
# ════════════════════════════════════════════
async def product_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    nav_push(context, 'shop')  # 🔙 Back goes to shop
    p = get_product(int(q.data.split("_")[1]))
    if not p:
        await q.edit_message_text("❌ Not found!", reply_markup=back_btn()); return

    show_photo = get_toggle("show_photo") == "1"
    try: photo_id = p['photo_id']
    except (IndexError, KeyError): photo_id = ""

    # 🆕 v42: HTML or Markdown rendering based on premium-emoji presence in name
    text, parse_mode = _build_detail_text(p)
    kb = product_detail_keyboard(p, user=q.from_user)

    if show_photo and photo_id:
        try:
            await q.message.delete()
            await context.bot.send_photo(
                chat_id=q.from_user.id, photo=photo_id, caption=text,
                parse_mode=parse_mode, reply_markup=kb
            )
            return
        except Exception:
            pass

    try:
        await q.edit_message_text(text, parse_mode=parse_mode, reply_markup=kb)
    except Exception:
        try: await q.message.delete()
        except: pass
        await context.bot.send_message(q.from_user.id, text, parse_mode=parse_mode, reply_markup=kb)


async def show_product_detail_direct(bot, user_id, product_id):
    """Directly send product details & purchase buttons to a user (used by deep linking)."""
    p = get_product(product_id)
    if not p:
        await bot.send_message(chat_id=user_id, text="❌ Product not found!")
        return
    if p['stock'] <= 0:
        await bot.send_message(chat_id=user_id, text=_get_resp("out_of_stock", user_id=user_id if user_id else 0))
        return

    show_photo = get_toggle("show_photo") == "1"
    try: photo_id = p['photo_id']
    except (IndexError, KeyError): photo_id = ""

    # 🆕 v42: HTML/Markdown switch for premium-emoji product names
    text, parse_mode = _build_detail_text(p)
    kb = product_detail_keyboard(p, user={'id': user_id})

    if show_photo and photo_id:
        try:
            await bot.send_photo(
                chat_id=user_id, photo=photo_id, caption=text,
                parse_mode=parse_mode, reply_markup=kb
            )
            return
        except Exception:
            pass

    await bot.send_message(chat_id=user_id, text=text, parse_mode=parse_mode, reply_markup=kb)


async def req_restock_callback(update, context):
    q = update.callback_query
    await q.answer("🔔 Alert Set! You will be notified automatically when stock is added.", show_alert=True)
    pid = int(q.data.replace("req_restock_", ""))
    from database import add_restock_request, add_stock_alert
    add_restock_request(pid, q.from_user.id)
    add_stock_alert(pid, q.from_user.id)

async def shop_flash_callback(update, context):
    q = update.callback_query
    await q.answer()
    nav_push(context, 'shop_flash')
    from database import get_flash_sale_products
    products = get_flash_sale_products()
    if not products:
        await q.edit_message_text("No active flash sales right now.", reply_markup=back_btn('shop'))
        return
        
    # 🆕 v45: premium-emoji-aware buttons for flash sale list
    try:
        from button_system import make_premium_button, extract_emoji_from_html
    except Exception:
        make_premium_button = None
        extract_emoji_from_html = None
    kb = []
    for p in products:
        s = p['stock']
        raw = p.get('name', '') or ''
        if extract_emoji_from_html:
            ne_id, plain = extract_emoji_from_html(raw)
        else:
            ne_id, plain = "", raw
        lbl = f"⚡ {plain} [Stock: {s}] — {fmt_price(p['flash_price'])}" if s > 0 else f"⚡ {plain} ❌ Out of Stock"
        cb_data = f"viewprod_{p['id']}" if q.from_user.id == ADMIN_ID else f"prod_{p['id']}"
        if ne_id and make_premium_button:
            kb.append([make_premium_button(lbl, emoji_id=ne_id, callback_data=cb_data)])
        else:
            kb.append([InlineKeyboardButton(lbl, callback_data=cb_data)])
        
    kb.append([InlineKeyboardButton("🔙 Back to Shop", callback_data="shop")])
    await _safe_edit(q, "⚡ *Active Flash Sales*\n━━━━━━━━━━━━━━━━━━━━\nGrab these limited-time deals:\n", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
