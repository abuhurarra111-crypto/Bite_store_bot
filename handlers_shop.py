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


def _display_text_normalize_newlines(value):
    """Normalize supplier text for display only (DB stays unchanged)."""
    if value is None:
        return ""
    text = str(value)
    prefix = "[[HTML]]" if text.startswith("[[HTML]]") else ""
    body = text[len(prefix):] if prefix else text
    # Actual CR/LF first, then literal "\\n" sequences from JSON/supplier dumps.
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = (body.replace("\\r\\n", "\n")
                .replace("\\n", "\n")
                .replace("\\t", "\t"))
    return prefix + body if prefix else body

def _split_display_prefix(value):
    text = _display_text_normalize_newlines(value)
    prefix = "[[HTML]]" if text.startswith("[[HTML]]") else ""
    return prefix, text[len(prefix):] if prefix else text


def _strip_bullet_prefix(line):
    import re
    s = str(line or "").strip()
    # Remove common supplier bullets: +)  -  •  1) etc.
    s = re.sub(r"^\s*(?:[+\-*•●▪◦]+\s*\)?\s*|\d+[.)]\s*)+", "", s).strip()
    return s


def _is_separator_line(line):
    import re
    return bool(re.match(r"^\s*[=━─\-_*]{5,}\s*$", str(line or "")))


def _line_key(line):
    import re
    s = _strip_bullet_prefix(html_strip_tags(str(line or "")))
    s = re.sub(r"(?i)^usage\s*:\s*", "", s).strip()
    s = re.sub(r"(?i)^notes?\s*[⚠️❗!\s]*[:：\-–—]*\s*", "", s).strip()
    s = re.sub(r"(?i)^important(?:\s+note)?\s*[:：\-–—]*\s*", "", s).strip()
    s = re.sub(r"(?i)^format\s*[:：\-–—]*\s*", "", s).strip()
    s = re.sub(r"\s+", " ", s).strip().lower()
    s = s.replace("refresh tokens", "refresh token")
    s = s.strip(" .,:;|-_=*()[]{}'\"")
    return s


def _is_format_line(line):
    import re
    s = _strip_bullet_prefix(line)
    low = html_strip_tags(s).strip().lower()
    if not low:
        return False
    if re.match(r"^(format|delivery\s*format|account\s*format|định\s*dạng)\s*[:：\-–—]", low):
        return True
    if low.startswith("usage:"):
        rest = low.split(":", 1)[1].strip()
        if rest.startswith(("format:", "format ")):
            return True
        if "|" in rest and any(w in rest for w in ("email", "mail", "pass", "password", "token", "client", "2fa", "link", "code")):
            return True
    return False


def _note_payload(line):
    import re
    s = _strip_bullet_prefix(line)
    plain = html_strip_tags(s).strip()
    m = re.match(r"(?is)^(?:important\s+note|notes?|note)\s*[⚠️❗!\s]*[:：\-–—]*\s*(.+)$", plain)
    if not m:
        return None
    payload = m.group(1).strip()
    return payload or None


def _drop_duplicate_supplier_blocks(body):
    """Skip repeated supplier blocks after ===== separators when they repeat keys."""
    import re
    text = str(body or "")
    blocks = [b.strip() for b in re.split(r"(?m)^\s*[=━─\-_*]{5,}\s*$", text) if b.strip()]
    if len(blocks) <= 1:
        return text
    kept = []
    seen = set()
    for block in blocks:
        keys = set()
        for ln in block.splitlines():
            if not ln.strip() or _is_separator_line(ln):
                continue
            k = _line_key(ln)
            if k:
                keys.add(k)
        # Supplier often repeats the same product in another language after =====.
        # If the block shares useful keys (format/url/note lines), keep only first.
        if kept and (len(keys & seen) >= 2 or any(_is_format_line(x) and _line_key(x) in seen for x in block.splitlines())):
            continue
        kept.append(block)
        seen |= keys
    return "\n\n".join(kept).strip()


def _clean_product_description(desc):
    """Clean duplicate supplier description blocks at display time only.

    - DB original text is never changed (supplier mapping/order safety).
    - Repeated Format/Note lines are removed from the description because the
      product detail screen shows Format and Note as their own single sections.
    - Exact/near duplicate Usage/URL lines are collapsed.
    """
    if not desc:
        return ""
    prefix, body = _split_display_prefix(desc)
    body = _drop_duplicate_supplier_blocks(body)
    lines = body.splitlines()
    out = []
    seen = set()
    prev_blank = False
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            if not prev_blank and out:
                out.append("")
            prev_blank = True
            continue
        if _is_separator_line(stripped):
            continue
        if _is_format_line(stripped):
            continue
        if _note_payload(stripped) is not None:
            continue
        prev_blank = False
        key = _line_key(stripped)
        if not key:
            continue
        usage_rest_key = ""
        if _strip_bullet_prefix(stripped).lower().startswith("usage:"):
            usage_rest_key = _line_key(_strip_bullet_prefix(stripped).split(":", 1)[1])
            if usage_rest_key and usage_rest_key in seen:
                continue
        if key in seen:
            continue
        seen.add(key)
        if usage_rest_key:
            seen.add(usage_rest_key)
        out.append(stripped)
    cleaned = "\n".join(out).strip()
    return prefix + cleaned if (prefix and cleaned) else cleaned


def _extract_notes_from_description(desc):
    if not desc:
        return ""
    _prefix, body = _split_display_prefix(desc)
    body = _drop_duplicate_supplier_blocks(body)
    notes = []
    seen = set()
    for ln in body.splitlines():
        payload = _note_payload(ln)
        if not payload:
            continue
        key = _line_key(payload)
        if key and key not in seen:
            seen.add(key)
            notes.append(payload)
    return "\n".join(notes).strip()


def _dedupe_multiline_display_text(text):
    if not text:
        return ""
    prefix, body = _split_display_prefix(text)
    out = []
    seen = set()
    for ln in body.splitlines():
        stripped = ln.strip()
        if not stripped:
            continue
        key = _line_key(stripped)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(stripped)
    joined = "\n".join(out).strip()
    return prefix + joined if (prefix and joined) else joined


def _build_display_note(desc, customer_note=""):
    """Return one customer note block from DB note + supplier Note lines."""
    parts = []
    if customer_note:
        parts.append(_dedupe_multiline_display_text(customer_note))
    auto_note = _extract_notes_from_description(desc)
    if auto_note:
        parts.append(auto_note)
    out = []
    seen = set()
    for part in parts:
        for ln in str(part or "").splitlines():
            stripped = ln.strip()
            if not stripped:
                continue
            key = _line_key(stripped)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            out.append(stripped)
    return "\n".join(out).strip()


def _product_format_label(p):
    try:
        from templates_bundle import format_label as _fmt_label, normalize_product_format
        return _fmt_label(normalize_product_format((dict(p) if p else {}).get('product_format', 'email_pass')))
    except Exception:
        return "📧 Email+Pass"


def _product_status_label(p):
    try:
        active = int((dict(p) if p else {}).get('is_active', 1) or 0) == 1
    except Exception:
        active = True
    return "✅ Active" if active else "🚫 Deactivated"

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
    """Returns raw/carousel/grid/list. Default: raw. 🆕 v144 grid+list."""
    fmt = get_setting("display_format", "raw").lower().strip()
    return fmt if fmt in ("raw", "carousel", "grid", "list") else "raw"


# 🆕 v42: Build the product detail text in either Markdown OR HTML mode,
# depending on whether the product name was saved with a premium-emoji
# HTML representation. Returns (text, parse_mode).
def _build_detail_text(p, user_id=None):
    import html as _html
    try:
        from i18n import tr_user as _tr_user
    except Exception:
        _tr_user = lambda x, user_id=None: x
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
    try: customer_note = p['customer_note']
    except (IndexError, KeyError): customer_note = ""

    raw_description = p.get('description', '') if hasattr(p, 'get') else p['description']
    desc_clean = _clean_product_description(raw_description)
    display_note = _build_display_note(raw_description, customer_note)
    delivery_label = get_product_mode_tag(p)
    status_label = _product_status_label(p)
    fmt_label = _product_format_label(p)

    # 🐛 v106 FIX: also switch to HTML mode when description contains
    # regular HTML tags (<b>, <blockquote>, <i>, etc.) — many suppliers
    # send richly-formatted HTML descriptions. Previously such tags were
    # either stripped (HTML branch) or shown as literal `<b>Note:</b>` text
    # (Markdown branch). Now we detect and preserve them properly.
    import re as _re_desc_ck
    def _has_html_tags(_v):
        if not _v: return False
        s = str(_v)
        if s.startswith("[[HTML]]"):
            return True
        return bool(_re_desc_ck.search(
            r"<(?:b|i|u|s|code|pre|blockquote|tg-emoji|a|em|strong|br)\b",
            s, flags=_re_desc_ck.I))

    html_needed = (name_html_aware
                   or contains_premium_markup(desc_clean)
                   or contains_premium_markup(warranty)
                   or contains_premium_markup(quantity)
                   or contains_premium_markup(display_note)
                   or _has_html_tags(desc_clean)
                   or _has_html_tags(warranty)
                   or _has_html_tags(quantity)
                   or _has_html_tags(display_note))
    if html_needed:
        # HTML mode — premium emojis render anywhere in product content
        title = name_for_message_html(_tr_user(html_strip_tags(p['name']), user_id=user_id))
        text = f"📦 <b>{title}</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        if desc_clean:
            # 🐛 v106: preserve HTML formatting — supplier <b>/<blockquote>/etc.
            # renders properly for customer instead of showing as literal text.
            _d = str(_tr_user(desc_clean, user_id=user_id))
            if contains_premium_markup(_d):
                desc_html = name_for_message_html(_d)
            elif _has_html_tags(_d):
                # Strip [[HTML]] sentinel + embed raw HTML tags as-is
                desc_html = _d[len("[[HTML]]"):] if _d.startswith("[[HTML]]") else _d
            else:
                desc_html = _html.escape(html_strip_tags(_d))
            text += f"📝 {desc_html}\n\n"
        if display_note:
            _cn = str(_tr_user(display_note, user_id=user_id))
            if contains_premium_markup(_cn):
                cn_html = name_for_message_html(_cn)
            elif _has_html_tags(_cn):
                cn_html = _cn[len("[[HTML]]"):] if _cn.startswith("[[HTML]]") else _cn
            else:
                cn_html = _html.escape(html_strip_tags(_cn))
            text += f"📌 <b>Important Note:</b> {cn_html}\n\n"
        if is_flash:
            text += (f"💰 Price: <s>{fmt_price(p['price'])}</s> ⚡ "
                     f"<b>${f_price:.2f}</b> ≈ <b>{_html.escape(pkr_f)}</b>\n")
        else:
            text += f"💰 Price: <b>{fmt_price(p['price'])}</b> ≈ <b>{_html.escape(pkr)}</b>\n"
        _status = _html.escape(html_strip_tags(str(_tr_user(status_label, user_id=user_id))))
        _delivery = _html.escape(html_strip_tags(str(_tr_user(delivery_label, user_id=user_id))))
        _format = _html.escape(html_strip_tags(str(_tr_user(fmt_label, user_id=user_id))))
        text += f"🚦 <b>Status:</b> {_status}\n"
        text += f"📦 <b>Delivery Type:</b> {_delivery}\n"
        text += f"🧩 <b>Format:</b> {_format}\n"
        if show_warranty and warranty:
            # 🐛 v106: preserve HTML tags in warranty text (supplier formatting)
            _w = str(_tr_user(warranty, user_id=user_id))
            if contains_premium_markup(_w):
                warranty_html = name_for_message_html(_w)
            elif _has_html_tags(_w):
                warranty_html = _w[len("[[HTML]]"):] if _w.startswith("[[HTML]]") else _w
            else:
                warranty_html = _html.escape(html_strip_tags(_w))
            text += f"🛡️ Warranty: <b>{warranty_html}</b>\n"
        if show_quantity and quantity:
            _q = str(_tr_user(quantity, user_id=user_id))
            if contains_premium_markup(_q):
                qty_html = name_for_message_html(_q)
            elif _has_html_tags(_q):
                qty_html = _q[len("[[HTML]]"):] if _q.startswith("[[HTML]]") else _q
            else:
                qty_html = _html.escape(html_strip_tags(_q))
            text += f"📦 Quantity: <b>{qty_html}</b>\n"
        if show_stock:
            text += f"📊 In Stock: <b>{p['stock']}</b>\n"
        text += _sold_line_html(p)
        return text, "HTML"

    # Default Markdown path (unchanged behaviour)
    text = f"📦 *{escape_md(_tr_user(p['name'], user_id=user_id))}*\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    if desc_clean:
        text += f"📝 {escape_md(_tr_user(desc_clean, user_id=user_id))}\n\n"
    if display_note:
        text += f"📌 *Important Note:* {escape_md(_tr_user(display_note, user_id=user_id))}\n\n"
    if is_flash:
        text += f"💰 Price: ~{fmt_price(p['price'])}~ ⚡ *${f_price:.2f}* ≈ *{pkr_f}*\n"
    else:
        text += f"💰 Price: *{fmt_price(p['price'])}* ≈ *{pkr}*\n"
    text += f"🚦 *Status:* {escape_md(_tr_user(status_label, user_id=user_id))}\n"
    text += f"📦 *Delivery Type:* {escape_md(_tr_user(delivery_label, user_id=user_id))}\n"
    text += f"🧩 *Format:* {escape_md(_tr_user(fmt_label, user_id=user_id))}\n"
    if show_warranty and warranty:
        text += f"🛡️ Warranty: *{escape_md(_tr_user(warranty, user_id=user_id))}*\n"
    if show_quantity and quantity:
        text += f"📦 Quantity: *{escape_md(_tr_user(quantity, user_id=user_id))}*\n"
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
    # v128: opening Shop verifies pending referrals immediately.
    try:
        from handlers_start import approve_pending_referral_for_user
        await approve_pending_referral_for_user(context, q.from_user.id, reason='shop_open')
    except Exception:
        pass
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
    _flt = _filter_label(filter_mode)
    try:
        from i18n import tr_user
        _flt = tr_user(_flt, user_id=q.from_user.id) or _flt
    except Exception:
        pass
    title += f"\n_Filter: {_flt}_"
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


def _build_carousel_caption(p, idx, total, user_id=None):
    """Build product caption text for carousel.
    Returns plain text (Markdown). Premium-emoji aware variant returns HTML."""
    text, mode = _build_detail_text(p, user_id=user_id)
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
    caption, parse_mode = _build_carousel_caption(p, idx, len(products), user_id=q.from_user.id)
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
    text, parse_mode = _build_detail_text(p, user_id=q.from_user.id)
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
    text, parse_mode = _build_detail_text(p, user_id=user_id)
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


async def favorite_toggle_callback(update, context):
    q = update.callback_query
    await q.answer()
    try:
        pid = int(q.data.replace('fav_toggle_', ''))
    except Exception:
        await q.answer('Bad product', show_alert=True); return
    from database import add_favorite, remove_favorite, is_favorite
    if is_favorite(q.from_user.id, pid):
        remove_favorite(q.from_user.id, pid)
        await q.answer('Removed from favorites 💔', show_alert=False)
    else:
        add_favorite(q.from_user.id, pid)
        await q.answer('Added to favorites ⭐', show_alert=False)
    q.data = f'prod_{pid}'
    await product_detail_callback(update, context)


async def favorites_callback(update, context):
    q = update.callback_query
    await q.answer()
    from database import get_user_favorites
    favs = get_user_favorites(q.from_user.id)
    if not favs:
        await q.edit_message_text('⭐ *My Favorites*\n\nNo favorite products yet.', parse_mode='Markdown', reply_markup=back_btn())
        return
    text = '⭐ *My Favorites*\n━━━━━━━━━━━━━━━━━━━━\n\nTap a product to open:'
    rows=[]
    for p in favs[:20]:
        name=(p['name'] or '')[:55]
        rows.append([InlineKeyboardButton(name, callback_data=f"prod_{p['id']}")])
    rows.append([InlineKeyboardButton('🔙 Back', callback_data='main_menu')])
    await q.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(rows))
