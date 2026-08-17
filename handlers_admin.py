# ============================================
# 👑 ADMIN
# ============================================
from telegram.ext import ConversationHandler
import asyncio
from config import *
from database import *
from keyboards import *
from keyboards import _rb  # 🆕 v161.14 FIX: underscore names NOT in star-import → NameError crashed reseller callbacks
from utils import escape_md, nav_push, set_cb_data, location_back_callback, smart_text_and_mode, has_premium_emoji, fmt_price, points_from_usd, fmt_points
from templates_bundle import (
    FORMAT_EMAIL_PASS, FORMAT_REDEEM_LINK, FORMAT_COUPON_CODES,
    format_label as delivery_format_label, get_product_format_choices,
    get_template_style, get_template_choices,
    normalize_product_format, format_hint as delivery_format_hint,
    format_example as delivery_format_example,
)

# 🔧 UPDATED: New states for photo, warranty, quantity
(CAT_NAME, CAT_EMOJI,
 PROD_CAT, PROD_NAME, PROD_DESC, PROD_PRICE, PROD_COST, PROD_STOCK,
 PROD_WARRANTY, PROD_QUANTITY, PROD_PHOTO, PROD_DELIVERY_TEXT,
 SET_VALUE, EDIT_RESP_VALUE) = range(14)

def _r(key):
    from database import get_response_with_auto_register
    return get_response_with_auto_register(key, DEFAULT_RESPONSES.get(key,""))


# 🆕 v47: Tiny helper used by product edit menu to show ON/OFF on the Free-Claim button.
def _fc_is_enabled(pid):
    try:
        from database import get_product_free_config
        return bool(get_product_free_config(pid).get("enabled"))
    except Exception:
        return False

# 🔧 Issue #1: Every Add-Product step needs a Back button (+ Cancel).
# `target` is the step to go back to (used by prod_back_callback).
def _prod_step_kb(target=None, skip=None):
    """Build the Back/Cancel keyboard for a step.
    skip: if given, adds a "⏭️ Skip" button with callback `prodskip_<skip>`
          so the admin never has to type `-`.
    """
    rows = []
    if skip:
        rows.append([InlineKeyboardButton("⏭️ Skip", callback_data=f"prodskip_{skip}")])
    if target:
        rows.append([InlineKeyboardButton("🔙 Back", callback_data=f"prodback_{target}")])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")])
    return InlineKeyboardMarkup(rows)

# 🆕 Warranty step: predefined options + Custom + Skip (no typing needed).
def _warranty_kb():
    opts = ["7 Days", "10 Days", "25 Days", "30 Days", "60 Days", "90 Days", "1 Year"]
    rows, row = [], []
    for i, o in enumerate(opts):
        row.append(InlineKeyboardButton(o, callback_data=f"pwar_{o}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✏️ Custom", callback_data="pwar_custom")])
    rows.append([InlineKeyboardButton("⏭️ Skip", callback_data="prodskip_warranty")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="prodback_stock")])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")])
    return InlineKeyboardMarkup(rows)

_WARRANTY_PROMPT = ("🛡️ *Step 6/11:* Warranty?\n"
                    "Choose an option below, or tap *Custom* to type your own:")
_QUANTITY_PROMPT = ("📦 *Step 7/11:* *Minimum* order quantity?\n"
                    "Customer must order at least this many (e.g. `1`).\n"
                    "Type a number, or tap *Skip* for no minimum (1).")

# Prompt text for each step, re-shown when the admin taps Back.
# Format: step -> (prompt, back_target, skip_step_or_None)
_PROD_STEP_PROMPTS = {
    "name":      ("📝 *Step 1/11:* Item name?", None, None),
    "desc":      ("📝 *Step 2/11:* Description?", "name", None),
    "price":     ("💰 *Step 3/11:* Selling price (customer pays):\ne.g. `5.99`", "desc", None),
    "cost":      ("💵 *Step 4/11:* Cost price (your cost — for profit tracking):\ne.g. `3.00`", "price", None),
    "stock":     ("📊 *Step 5/11:* Stock (number)?", "cost", None),
    "quantity":  (_QUANTITY_PROMPT, "warranty", "quantity"),
}
# Which conversation state each step expects next.
def _prod_state(step):
    from bot import (PROD_NAME, PROD_DESC, PROD_PRICE, PROD_COST, PROD_STOCK,
                     PROD_WARRANTY, PROD_QUANTITY, PROD_DELIVERY_TEXT)
    return {
        "name": PROD_NAME, "desc": PROD_DESC, "price": PROD_PRICE, "cost": PROD_COST,
        "stock": PROD_STOCK, "warranty": PROD_WARRANTY, "quantity": PROD_QUANTITY,
        "delivery": PROD_DELIVERY_TEXT,
    }[step]

async def prod_back_callback(u, c):
    """Handle 🔙 Back taps during Add-Product. Re-shows the requested step."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    step = q.data.replace("prodback_", "")
    from bot import PROD_DELIVERY_TEXT
    # The delivery-type step is the chooser screen.
    if step == "delivery":
        return await _ask_delivery_type(q, c, is_query=True)
    # Product format picker
    if step == "format":
        return await _ask_product_format(q, c, is_query=True)
    # Manual sub-step: choose Readymade / Own Mail
    if step == "manualtype":
        kb = [
            [InlineKeyboardButton("🛍️ Readymade Account", callback_data="pmt_readymade")],
            [InlineKeyboardButton("📬 Own Mail", callback_data="pmt_ownmail")],
            [InlineKeyboardButton("🔙 Back", callback_data="prodback_format")],
            [InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")],
        ]
        await _safe_edit(q, "📦 *Step 10:* Select Manual Type:", parse_mode="Markdown",
                         reply_markup=InlineKeyboardMarkup(kb))
        return PROD_DELIVERY_TEXT
    # Manual sub-step: choose Mail Requirement
    if step == "mailreq":
        kb = [
            [InlineKeyboardButton("📧 Any Mail", callback_data="pmail_any_mail")],
            [InlineKeyboardButton("📧 Fresh Gmail", callback_data="pmail_fresh_gmail")],
            [InlineKeyboardButton("📧 Any Gmail", callback_data="pmail_any_gmail")],
            [InlineKeyboardButton("🔙 Back", callback_data="prodback_manualtype")],
            [InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")],
        ]
        await _safe_edit(q, "📦 *Step 11:* Select Mail Requirement:", parse_mode="Markdown",
                         reply_markup=InlineKeyboardMarkup(kb))
        return PROD_DELIVERY_TEXT
    # Warranty step (step 6) uses its own option keyboard.
    if step == "warranty":
        from bot import PROD_WARRANTY
        await _safe_edit(q, _WARRANTY_PROMPT, parse_mode="Markdown", reply_markup=_warranty_kb())
        return PROD_WARRANTY
    prompt, back_to, skip = _PROD_STEP_PROMPTS.get(step, (None, None, None))
    if prompt is None:
        return
    await _safe_edit(q, prompt, parse_mode="Markdown", reply_markup=_prod_step_kb(back_to, skip))
    return _prod_state(step)

async def _safe_edit(q, text, **kwargs):
    """🆕 v57: Robust message editor with detailed error logging + ALWAYS
    delivers SOMETHING to the user (no more silent 'bot stuck' bugs).

    Strategy:
      1. Try edit_message_text with detected parse_mode
      2. On parse-entity error → retry without parse_mode (plain text)
      3. On ANY other error → try edit_message_caption (photo/video msg)
      4. Last resort → reply_text (new message)
      5. ABSOLUTE last resort → reply_text plain (no formatting) so user
         ALWAYS sees something instead of bot freezing.
    """
    import logging
    _log = logging.getLogger(__name__)
    send_text, send_mode = smart_text_and_mode(text, kwargs.get("parse_mode", "Markdown"))
    send_kwargs = dict(kwargs)
    send_kwargs["parse_mode"] = send_mode
    cb_data = getattr(q, "data", "?")

    # 1. Try editing as a regular text message
    try:
        await q.edit_message_text(send_text, **send_kwargs)
        return
    except Exception as e1:
        _log.warning(f"[_safe_edit] edit_message_text failed (cb={cb_data}, mode={send_mode}): {e1}")
        if "parse entities" in str(e1).lower() or "can't parse" in str(e1).lower():
            kwargs_no_md = dict(send_kwargs)
            kwargs_no_md.pop("parse_mode", None)
            try:
                await q.edit_message_text(send_text, **kwargs_no_md)
                return
            except Exception as e1b:
                _log.warning(f"[_safe_edit] edit_message_text (no parse) failed: {e1b}")

    # 2. Fallback: edit caption (works on photo/video messages)
    try:
        await q.edit_message_caption(caption=send_text, **send_kwargs)
        return
    except Exception as e2:
        if "parse entities" in str(e2).lower() or "can't parse" in str(e2).lower():
            kwargs_no_md = dict(send_kwargs)
            kwargs_no_md.pop("parse_mode", None)
            try:
                await q.edit_message_caption(caption=send_text, **kwargs_no_md)
                return
            except Exception: pass

    # 3. reply_text — new message
    try:
        await q.message.reply_text(send_text, **send_kwargs)
        return
    except Exception as e3:
        _log.warning(f"[_safe_edit] reply_text failed: {e3}")
        if "parse entities" in str(e3).lower() or "can't parse" in str(e3).lower():
            kwargs_no_md = dict(send_kwargs)
            kwargs_no_md.pop("parse_mode", None)
            try:
                await q.message.reply_text(send_text, **kwargs_no_md)
                return
            except Exception: pass

    # 4. 🆕 v57 ABSOLUTE LAST RESORT — plain text fallback so user always
    # sees something. Strips ALL HTML tags + answers query with brief alert.
    try:
        from utils import html_strip_tags
        plain = html_strip_tags(send_text)[:3500]
        plain += "\n\n_(⚠️ Display fallback — formatting could not render)_"
        plain_kwargs = {k: v for k, v in send_kwargs.items()
                        if k not in ("parse_mode",)}
        await q.message.reply_text(plain, **plain_kwargs)
    except Exception as e4:
        _log.error(f"[_safe_edit] ALL fallbacks failed (cb={cb_data}): {e4}")
        try:
            await q.answer("⚠️ Could not show panel. Try /start.",
                           show_alert=True)
        except Exception:
            pass

async def admin_categories_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer(); await _safe_edit(q, "🏷️ *Categories:*",parse_mode="Markdown",reply_markup=admin_categories_keyboard(get_categories()))

async def add_category_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return ConversationHandler.END
    await q.answer(); await _safe_edit(q, "🏷️ *Category name?*\n\n_Type a name or tap Cancel_", parse_mode="Markdown", reply_markup=inline_cancel_btn()); return CAT_NAME

async def cat_name_received(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    c.user_data['cat_n']=u.message.text; await u.message.reply_text("Emoji? (/skip for 📦)", reply_markup=inline_cancel_btn()); return CAT_EMOJI

async def cat_emoji_received(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    add_category(c.user_data.get('cat_n','?'),u.message.text.strip()); await u.message.reply_text("✅ Category added!",reply_markup=back_btn()); return ConversationHandler.END

async def cat_emoji_skip(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    add_category(c.user_data.get('cat_n','?'),"📦"); await u.message.reply_text("✅ Category added!",reply_markup=back_btn()); return ConversationHandler.END

async def delete_category_callback(u,c):
    await delete_category_confirm_callback(u, c)

# ── Products ──
async def admin_products_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    # 🆕 v135: admin sees ALL products (including hidden/deactivated ones)
    # so restored DB products can be edited/reactivated safely.
    await q.answer(); await _safe_edit(q, "🛍️ *Add Products:*",parse_mode="Markdown",reply_markup=admin_products_keyboard(get_all_products(include_hidden=True, include_inactive=True)))

async def bulk_product_delete_start_callback(u, c):
    """Start multi-select product delete screen."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    c.user_data['bulk_delete_products'] = set()
    await _bulk_product_delete_screen(u, c, page=0)


async def _bulk_product_delete_screen(u, c, page=0):
    q = u.callback_query
    selected = c.user_data.setdefault('bulk_delete_products', set())
    try:
        selected = {int(x) for x in selected}
    except Exception:
        selected = set()
    c.user_data['bulk_delete_products'] = selected
    products = list(get_all_products(include_hidden=True, include_inactive=True))
    per_page = 12
    total_pages = max(1, (len(products) + per_page - 1) // per_page)
    page = max(0, min(int(page or 0), total_pages - 1))
    chunk = products[page * per_page:(page + 1) * per_page]
    text = (
        f"🗑️ *Bulk Delete Products*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Select products to delete.\n"
        f"Selected: *{len(selected)}*\n"
        f"Page: *{page+1}/{total_pages}*\n\n"
        f"⚠️ Product rows will be removed from shop/admin. Old orders remain safe."
    )
    kb = []
    try:
        from button_system import extract_emoji_from_html
    except Exception:
        extract_emoji_from_html = None
    for p in chunk:
        pid = int(p['id'])
        name = p['name'] or f"Product #{pid}"
        if extract_emoji_from_html:
            _, name = extract_emoji_from_html(name)
        name = (name or f"Product #{pid}").replace('\n', ' ')
        if len(name) > 54:
            name = name[:51] + '...'
        mark = "✅" if pid in selected else "☐"
        kb.append([InlineKeyboardButton(f"{mark} {name}", callback_data=f"bulkprod_tgl_{pid}_{page}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"bulkprod_page_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"bulkprod_page_{page+1}"))
    if nav:
        kb.append(nav)
    if selected:
        kb.append([InlineKeyboardButton(f"🗑 Delete Selected ({len(selected)})", callback_data="bulkprod_confirm")])
        kb.append([InlineKeyboardButton("🧹 Clear Selection", callback_data=f"bulkprod_clear_{page}")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_products")])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def bulk_product_delete_toggle_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        raw = q.data.replace("bulkprod_tgl_", "")
        pid_s, page_s = raw.rsplit("_", 1)
        pid, page = int(pid_s), int(page_s)
    except Exception:
        await q.answer("Bad product", show_alert=True); return
    selected = c.user_data.setdefault('bulk_delete_products', set())
    try:
        selected = {int(x) for x in selected}
    except Exception:
        selected = set()
    if pid in selected:
        selected.remove(pid)
        await q.answer("Removed")
    else:
        selected.add(pid)
        await q.answer("Selected")
    c.user_data['bulk_delete_products'] = selected
    await _bulk_product_delete_screen(u, c, page=page)


async def bulk_product_delete_page_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        page = int(q.data.replace("bulkprod_page_", ""))
    except Exception:
        page = 0
    await q.answer()
    await _bulk_product_delete_screen(u, c, page=page)


async def bulk_product_delete_clear_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        page = int(q.data.replace("bulkprod_clear_", ""))
    except Exception:
        page = 0
    c.user_data['bulk_delete_products'] = set()
    await q.answer("Selection cleared")
    await _bulk_product_delete_screen(u, c, page=page)


async def bulk_product_delete_confirm_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    selected = c.user_data.get('bulk_delete_products') or set()
    selected = sorted({int(x) for x in selected})
    if not selected:
        await q.answer("No products selected", show_alert=True); return
    await q.answer()
    text = (
        f"⚠️ *Confirm Bulk Delete*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Products selected: *{len(selected)}*\n\n"
        f"This removes product rows from shop/admin. Old orders remain safe."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ YES, Delete {len(selected)}", callback_data="bulkprod_do")],
        [InlineKeyboardButton("❌ Cancel", callback_data="bulkprod_page_0")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def bulk_product_delete_do_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    selected = c.user_data.pop('bulk_delete_products', set()) or set()
    selected = sorted({int(x) for x in selected})
    deleted = failed = 0
    for pid in selected:
        try:
            delete_product_permanently(pid)
            deleted += 1
        except Exception:
            failed += 1
    await q.answer(f"Deleted {deleted}, failed {failed}", show_alert=True)
    await _safe_edit(q,
        f"✅ *Bulk Delete Complete*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🗑 Deleted: *{deleted}*\n"
        f"⚠️ Failed: *{failed}*\n\n"
        f"Old orders/history remain safe.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍️ Back to Edit Items", callback_data="admin_products")]
        ]))


async def add_product_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return ConversationHandler.END
    await q.answer()
    cats=get_categories()
    if not cats: await _safe_edit(q, "❌ Add category first!",reply_markup=admin_menu_keyboard()); return ConversationHandler.END
    await _safe_edit(q, "📂 Select category:",reply_markup=select_category_keyboard(cats)); return PROD_CAT

async def select_category_for_product(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: return ConversationHandler.END
    await q.answer(); c.user_data['pc']=int(q.data.split("_")[1])
    await _safe_edit(q,
        "📝 *Step 1/11:* Item name?\n\n"
        "⭐ _Premium / Custom emojis supported! Type the name and insert "
        "premium emojis from Telegram's picker — they will render on the "
        "product detail page._",
        parse_mode="Markdown", reply_markup=_prod_step_kb()); return PROD_NAME

async def prod_name_received(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    # 🆕 v42: Premium/custom emoji aware — preserve HTML representation
    # so product name can render with premium emojis on the detail page.
    raw = u.message.text or ""
    try:
        html_v = (u.message.text_html_urled or "").strip()
    except Exception:
        html_v = ""
    has_custom_emoji = any(getattr(e, "type", "") == "custom_emoji"
                           for e in (u.message.entities or []))
    if html_v and has_custom_emoji:
        c.user_data['pn'] = "[[HTML]]" + html_v
    else:
        c.user_data['pn'] = raw
    await u.message.reply_text("📝 *Step 2/11:* Description?", parse_mode="Markdown", reply_markup=_prod_step_kb("name")); return PROD_DESC

async def prod_desc_received(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    raw = u.message.text or ""
    try:
        html_v = (u.message.text_html_urled or "").strip()
    except Exception:
        html_v = ""
    c.user_data['pd'] = ("[[HTML]]" + html_v) if (html_v and has_premium_emoji(u.message)) else raw
    await u.message.reply_text("💰 *Step 3/11:* Selling price (customer pays):\ne.g. `5.99`", parse_mode="Markdown", reply_markup=_prod_step_kb("desc")); return PROD_PRICE

async def prod_price_received(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    try: c.user_data['pp']=float(u.message.text.strip().replace('$',''))
    except: await u.message.reply_text("❌ Please enter a valid number (e.g. `5.99`):", parse_mode="Markdown", reply_markup=_prod_step_kb("desc")); return PROD_PRICE
    await u.message.reply_text("💵 *Step 4/11:* Cost price (your cost — for profit tracking):\ne.g. `3.00`", parse_mode="Markdown", reply_markup=_prod_step_kb("price")); return PROD_COST

async def prod_cost_received(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    try: c.user_data['pcp']=float(u.message.text.strip().replace('$',''))
    except: await u.message.reply_text("❌ Please enter a valid number (e.g. `3.00`):", parse_mode="Markdown", reply_markup=_prod_step_kb("price")); return PROD_COST
    await u.message.reply_text("📊 *Step 5/11:* Stock (number)?", parse_mode="Markdown", reply_markup=_prod_step_kb("cost")); return PROD_STOCK

async def prod_stock_received(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    try: c.user_data['ps']=int(u.message.text.strip())
    except: await u.message.reply_text("❌ Please enter a whole number (e.g. `50`):", parse_mode="Markdown", reply_markup=_prod_step_kb("cost")); return PROD_STOCK
    # 🆕 Step 6: Warranty via option buttons (+ Custom + Skip)
    await u.message.reply_text(_WARRANTY_PROMPT, parse_mode="Markdown", reply_markup=_warranty_kb())
    return PROD_WARRANTY

async def _ask_quantity(u_or_q, c, is_query=False):
    """Show Step 7 (minimum quantity) prompt."""
    from bot import PROD_QUANTITY
    if is_query:
        await _safe_edit(u_or_q, _QUANTITY_PROMPT, parse_mode="Markdown",
                         reply_markup=_prod_step_kb("warranty", skip="quantity"))
    else:
        await u_or_q.message.reply_text(_QUANTITY_PROMPT, parse_mode="Markdown",
                         reply_markup=_prod_step_kb("warranty", skip="quantity"))
    return PROD_QUANTITY

async def prod_warranty_callback(u, c):
    """Warranty option button tapped (pwar_<value> or pwar_custom)."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    from bot import PROD_WARRANTY
    val = q.data.replace("pwar_", "")
    if val == "custom":
        c.user_data['warranty_custom'] = True
        await _safe_edit(q, "✏️ *Custom Warranty*\nType the warranty text (e.g. `45 Days`, `Lifetime`):",
                         parse_mode="Markdown", reply_markup=_prod_step_kb("warranty"))
        return PROD_WARRANTY
    c.user_data['pw'] = val
    c.user_data.pop('warranty_custom', None)
    return await _ask_quantity(q, c, is_query=True)

async def prod_warranty_received(u,c):
    """Handles Custom warranty TEXT input (only reachable after tapping Custom)."""
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    val = u.message.text.strip()
    try:
        html_v = (u.message.text_html_urled or "").strip()
    except Exception:
        html_v = ""
    if val == "-":
        c.user_data['pw'] = ""
    else:
        c.user_data['pw'] = ("[[HTML]]" + html_v) if (html_v and has_premium_emoji(u.message)) else val
    c.user_data.pop('warranty_custom', None)
    return await _ask_quantity(u, c, is_query=False)

async def prod_quantity_received(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    val = u.message.text.strip()
    # 🆕 Quantity is now the MINIMUM order quantity (a number). Skip = 1.
    if val == "-" or val == "":
        c.user_data['pq'] = 1
    else:
        try:
            n = int(val)
            if n < 1:
                raise ValueError()
            c.user_data['pq'] = n
        except ValueError:
            await u.message.reply_text(
                "❌ Please enter a whole number ≥ 1 (e.g. `5`), or tap Skip:",
                parse_mode="Markdown", reply_markup=_prod_step_kb("warranty", skip="quantity"))
            from bot import PROD_QUANTITY
            return PROD_QUANTITY
    return await _ask_delivery_type(u, c, is_query=False)

async def _ask_delivery_type(u_or_q, c, is_query=False):
    """Show delivery-type chooser."""
    kb = [
        [InlineKeyboardButton("🤖 Auto Delivery", callback_data="pdm_auto")],
        [InlineKeyboardButton("✋ Manual Delivery", callback_data="pdm_manual")],
        [InlineKeyboardButton("🔙 Back", callback_data="prodback_quantity")],
        [InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")],
    ]
    text = "📦 *Step 8:* Delivery type?"
    if is_query:
        await _safe_edit(u_or_q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await u_or_q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    from bot import PROD_DELIVERY_TEXT
    return PROD_DELIVERY_TEXT


async def _ask_product_format(u_or_q, c, is_query=False):
    """Ask which stock format this product will use."""
    current = normalize_product_format(c.user_data.get('p_format', 'email_pass'))
    rows = []
    for fmt in get_product_format_choices():
        mark = " ✅" if current == normalize_product_format(fmt) else ""
        rows.append([InlineKeyboardButton(f"{delivery_format_label(fmt)}{mark}", callback_data=f"pfmt_{fmt}")])
    rows.extend([
        [InlineKeyboardButton("🔙 Back", callback_data="prodback_delivery")],
        [InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")],
    ])
    text = (
        "🧩 *Step 9:* Product format?\n\n"
        "Choose how this product will be uploaded and delivered:\n\n"
        "• 📧 *Email+Pass* — account credentials\n"
        "• 🔐 *Email+Pass+2FA* — accounts with 2FA secret\n"
        "• 🎯 *Email+Pass+Token+Client ID* — Outlook/Hotmail style lines\n"
        "• 🖇️ *Redeem Link* — one unique link per order\n"
        "• 🎁 *Coupon / Code* — one unique code per order\n\n"
        "_Whichever format you select, stock upload will accept only that format._"
    )
    if is_query:
        await _safe_edit(u_or_q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
    else:
        await u_or_q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
    from bot import PROD_DELIVERY_TEXT
    return PROD_DELIVERY_TEXT


async def pdm_callback(u,c):
    q = u.callback_query
    await q.answer()
    mode = q.data.replace("pdm_", "")
    c.user_data['p_dmode'] = mode
    return await _ask_product_format(q, c, is_query=True)


async def pfmt_callback(u, c):
    q = u.callback_query
    await q.answer()
    fmt = q.data.replace("pfmt_", "")
    c.user_data['p_format'] = normalize_product_format(fmt)

    if c.user_data.get('p_dmode', 'auto') == 'auto':
        await _safe_edit(q,
            "📦 *Step 10:* Static Delivery Text / Link?\n"
            "If you want to deliver the SAME text/link/code to EVERY buyer, enter it here.\n"
            "To deliver unique stock items from the pool instead, tap *Skip*.",
            parse_mode="Markdown", reply_markup=_prod_step_kb("format", skip="delivery"))
    else:
        kb = [
            [InlineKeyboardButton("🛍️ Readymade Account", callback_data="pmt_readymade")],
            [InlineKeyboardButton("📬 Own Mail", callback_data="pmt_ownmail")],
            [InlineKeyboardButton("🔙 Back", callback_data="prodback_format")],
            [InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")],
        ]
        await _safe_edit(q, "📦 *Step 10:* Select Manual Type:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    from bot import PROD_DELIVERY_TEXT
    return PROD_DELIVERY_TEXT


async def pmt_callback(u,c):
    q = u.callback_query
    await q.answer()
    mtype = q.data.replace("pmt_", "")
    c.user_data['p_mtype'] = mtype

    if mtype == 'readymade':
        c.user_data['p_req_account'] = 'none'
        c.user_data['p_req_pass'] = 0
        await q.edit_message_text(
            "📦 *Final Step:* Instructions / Confirmation Text?\n"
            "Enter any instructions to show the user after they order (e.g. 'Wait 2 hours'), "
            "or tap *Skip*.", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭️ Skip", callback_data="prodskip_delivery")],
                [InlineKeyboardButton("🔙 Back", callback_data="prodback_manualtype")],
                [InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")],
            ]))
        from bot import PROD_DELIVERY_TEXT
        return PROD_DELIVERY_TEXT
    else:
        kb = [
            [InlineKeyboardButton("📧 Any Mail", callback_data="pmail_any_mail")],
            [InlineKeyboardButton("📧 Fresh Gmail", callback_data="pmail_fresh_gmail")],
            [InlineKeyboardButton("📧 Any Gmail", callback_data="pmail_any_gmail")],
            [InlineKeyboardButton("🔙 Back", callback_data="prodback_manualtype")],
            [InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")],
        ]
        await q.edit_message_text("📦 *Step 11:* Select Mail Requirement:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    from bot import PROD_DELIVERY_TEXT
    return PROD_DELIVERY_TEXT


async def pmail_callback(u,c):
    q = u.callback_query
    await q.answer()
    mailtype = q.data.replace("pmail_", "")
    c.user_data['p_req_account'] = mailtype

    kb = [
        [InlineKeyboardButton("✅ Yes", callback_data="ppass_1")],
        [InlineKeyboardButton("❌ No", callback_data="ppass_0")],
        [InlineKeyboardButton("🔙 Back", callback_data="prodback_mailreq")],
        [InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")],
    ]
    await q.edit_message_text("📦 *Final Step:* Require Password from customer?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    from bot import PROD_DELIVERY_TEXT
    return PROD_DELIVERY_TEXT


async def ppass_callback(u,c):
    q = u.callback_query
    await q.answer()
    req_pass = int(q.data.replace("ppass_", ""))
    c.user_data['p_req_pass'] = req_pass

    await q.edit_message_text(
        "📦 *Final Step:* Instructions / Confirmation Text?\n"
        "Enter any instructions to show the user after they order, or tap *Skip*.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭️ Skip", callback_data="prodskip_delivery")],
            [InlineKeyboardButton("🔙 Back", callback_data="prodback_mailreq")],
            [InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")],
        ]))
    from bot import PROD_DELIVERY_TEXT
    return PROD_DELIVERY_TEXT

async def prod_skip_callback(u, c):
    """Handle ⏭️ Skip taps during Add-Product."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Skipped ⏭️")
    step = q.data.replace("prodskip_", "")
    if step == "warranty":
        c.user_data['pw'] = ""
        c.user_data.pop('warranty_custom', None)
        return await _ask_quantity(q, c, is_query=True)
    if step == "quantity":
        c.user_data['pq'] = 1   # no minimum
        return await _ask_delivery_type(q, c, is_query=True)
    if step == "delivery":
        # Skip static delivery text/media; product will use account-stock auto delivery.
        c.user_data['pdt'] = ""
        for k in ['p_static_file_id','p_static_file_type','p_static_file_name','p_static_caption']:
            c.user_data.pop(k, None)
        return await _finalize_product_add(q, c, is_query=True)

async def prod_delivery_received(u,c):
    if u.effective_user.id != ADMIN_ID: return ConversationHandler.END
    msg = u.message
    # Static media/file delivery: photo, video, PDF/document, etc.
    if getattr(msg, 'photo', None):
        c.user_data['pdt'] = (msg.caption or '').strip()
        c.user_data['p_static_file_id'] = msg.photo[-1].file_id
        c.user_data['p_static_file_type'] = 'photo'
        c.user_data['p_static_file_name'] = 'photo'
        c.user_data['p_static_caption'] = (msg.caption or '').strip()
        return await _finalize_product_add(u, c, is_query=False)
    if getattr(msg, 'video', None):
        c.user_data['pdt'] = (msg.caption or '').strip()
        c.user_data['p_static_file_id'] = msg.video.file_id
        c.user_data['p_static_file_type'] = 'video'
        c.user_data['p_static_file_name'] = (getattr(msg.video, 'file_name', '') or 'video')
        c.user_data['p_static_caption'] = (msg.caption or '').strip()
        return await _finalize_product_add(u, c, is_query=False)
    if getattr(msg, 'document', None):
        c.user_data['pdt'] = (msg.caption or '').strip()
        c.user_data['p_static_file_id'] = msg.document.file_id
        c.user_data['p_static_file_type'] = 'document'
        c.user_data['p_static_file_name'] = (msg.document.file_name or 'document')
        c.user_data['p_static_caption'] = (msg.caption or '').strip()
        return await _finalize_product_add(u, c, is_query=False)

    val = (msg.text or '').strip()
    try:
        html_v = (msg.text_html_urled or "").strip()
    except Exception:
        html_v = ""
    c.user_data['pdt'] = "" if val == "-" else (("[[HTML]]" + html_v) if (html_v and msg.entities) else val)
    for k in ['p_static_file_id','p_static_file_type','p_static_file_name','p_static_caption']:
        c.user_data.pop(k, None)
    return await _finalize_product_add(u, c, is_query=False)


async def _finalize_product_add(u_or_q, c, is_query=False):
    dmode = c.user_data.get('p_dmode', 'auto')
    mtype = c.user_data.get('p_mtype', 'readymade')
    req_acct = c.user_data.get('p_req_account', 'none')
    req_pass = c.user_data.get('p_req_pass', 0)
    pdt = c.user_data.get('pdt', '')
    static_file_id = c.user_data.get('p_static_file_id', '')
    static_file_type = c.user_data.get('p_static_file_type', '')
    static_file_name = c.user_data.get('p_static_file_name', '')
    static_caption = c.user_data.get('p_static_caption', '')
    product_format = normalize_product_format(c.user_data.get('p_format', 'email_pass'))
    template_id = 1
    admin_stock = int(c.user_data.get('ps', 0) or 0)

    # 🔧 BUG FIX (Issue #2): stock should reflect what the admin entered in Step 5.
    #   • Auto + static delivery text/link → unlimited (1,000,000), same text for all.
    #   • Auto + account pool (no text)    → 0 here; real stock comes from the pool.
    #   • Manual delivery                  → use the admin-entered stock (e.g. 50),
    #                                        NOT a fake 1,000,000.
    if dmode == 'auto' and (pdt or static_file_id):
        initial_stock = 1000000
    elif dmode == 'manual':
        initial_stock = admin_stock
    else:
        initial_stock = 0

    db_dmode = 'manual' if dmode == 'manual' else 'auto'
    
    # 🆕 quantity is now the MINIMUM order quantity (stored as text in the column).
    min_qty = int(c.user_data.get('pq', 1) or 1)
    new_pid = add_product(
        c.user_data.get('pc'),
        c.user_data.get('pn','?'),
        c.user_data.get('pd',''),
        c.user_data.get('pp',0),
        c.user_data.get('pcp',0),
        initial_stock,
        pdt,
        c.user_data.get('pw',''),
        str(min_qty),
        ""
    )
    
    conn = get_connection(); cur = conn.cursor()
    # 🔧 BUG FIX: on Render the products table can be missing these columns
    # (DB reset / partial migration) → "no such column: delivery_mode" crashed
    # the FINAL step of add-product (product got created, but admin saw no
    # confirmation). Self-heal the columns before updating so it never crashes.
    from database import ensure_column
    ensure_column(cur, "products", "delivery_mode", "TEXT DEFAULT 'auto'")
    ensure_column(cur, "products", "req_account_type", "TEXT DEFAULT 'none'")
    ensure_column(cur, "products", "req_password", "INTEGER DEFAULT 0")
    ensure_column(cur, "products", "req_fresh", "INTEGER DEFAULT 0")
    ensure_column(cur, "products", "product_format", "TEXT DEFAULT 'email_pass'")
    ensure_column(cur, "products", "delivery_template", "INTEGER DEFAULT 1")
    ensure_column(cur, "products", "delivery_file_id", "TEXT DEFAULT ''")
    ensure_column(cur, "products", "delivery_file_type", "TEXT DEFAULT ''")
    ensure_column(cur, "products", "delivery_file_name", "TEXT DEFAULT ''")
    ensure_column(cur, "products", "delivery_caption", "TEXT DEFAULT ''")
    cur.execute(
        "UPDATE products SET delivery_mode=?, req_account_type=?, req_password=?, product_format=?, delivery_template=?, delivery_file_id=?, delivery_file_type=?, delivery_file_name=?, delivery_caption=? WHERE id=?",
        (db_dmode, req_acct, req_pass, product_format, template_id, static_file_id, static_file_type, static_file_name, static_caption, new_pid)
    )
    conn.commit(); conn.close()
    
    fmt_label = delivery_format_label(product_format)
    tpl_label = get_template_style(template_id)['name']
    summary = (
        f"✅ *Product Added!*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 {escape_md(c.user_data.get('pn','?'))}\n"
        f"💰 Sell: ${c.user_data.get('pp',0):.2f}\n"
        f"💵 Cost: ${c.user_data.get('pcp',0):.2f}\n"
        f"🚚 Mode: {'🤖 Auto' if dmode=='auto' else f'✋ Manual ({escape_md(mtype)})'}\n"
        f"🧩 Format: {fmt_label}\n"
        f"🎁 Template: #{template_id} {escape_md(tpl_label)}\n"
    )
    if c.user_data.get('pw'):
        summary += f"🛡️ Warranty: {escape_md(str(c.user_data.get('pw')))}\n"
    if min_qty > 1:
        summary += f"🔢 Min Order Qty: {min_qty}\n"
    
    # 🔧 BUG FIX: previously called admin_products_keyboard() with no args (it
    # REQUIRES `prods`) and then treated the returned markup like a list →
    # TypeError that crashed the LAST step of EVERY product add. Build a plain
    # list of button rows here instead.
    kb = [[InlineKeyboardButton("📦 View / Edit This Product", callback_data=f"viewprod_{new_pid}")]]

    if dmode == 'auto' and (pdt or static_file_id):
        summary += f"🔗 *Static Delivery Set!* {'(media/file)' if static_file_id else '(text)'}\n"
        kb.append([InlineKeyboardButton("⚙️ Delivery Settings", callback_data=f"delset_{new_pid}")])
    elif dmode == 'auto' and not pdt:
        summary += f"⚠️ *No accounts added yet!* Must add stock.\n"
        kb.append([InlineKeyboardButton(f"📋 Manage Accounts", callback_data=f"prodaccounts_manage_{new_pid}")])
    elif dmode == 'manual':
        summary += f"📊 Stock: {admin_stock}\n"
        summary += f"✅ Manual delivery configured.\n"
        kb.append([InlineKeyboardButton("⚙️ Delivery Settings", callback_data=f"delset_{new_pid}")])
        
    kb.append([InlineKeyboardButton("🔙 Back to Add Products", callback_data="admin_products")])
    
    markup = InlineKeyboardMarkup(kb)
    # 🔧 BUG FIX: the confirmation was sent with parse_mode="Markdown" and NO
    # fallback. If the product name / instructions contained markdown-breaking
    # characters (e.g. `_`, `*`, backticks), Telegram REJECTED the message →
    # the product got added (add_product already ran) but the admin saw NO
    # confirmation text. Now we fall back to plain text so confirmation always shows.
    if is_query:
        await _safe_edit(u_or_q, summary, parse_mode="Markdown", reply_markup=markup)
    else:
        try:
            await u_or_q.message.reply_text(summary, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            try:
                await u_or_q.message.reply_text(summary, reply_markup=markup)
            except Exception:
                await u_or_q.message.reply_text("✅ Product Added!", reply_markup=markup)
        
    for k in ['pc','pn','pd','pp','pcp','ps','pw','pq','pph','p_dmode','p_mtype','p_req_account','p_req_pass','p_format','pdt','p_static_file_id','p_static_file_type','p_static_file_name','p_static_caption']: c.user_data.pop(k,None)

    # 🆕 Announce the NEW product to the configured destination (bot/group/both),
    # same place where fake activity goes. Gated by the 'New Product' toggle.
    try:
        from per_user_activity import is_type_on
        if is_type_on("newprod"):
            from fake_engagement import build_newproduct_message, broadcast_store_message
            prod = get_product(new_pid)
            if prod:
                text = build_newproduct_message(prod)
                await broadcast_store_message(c.bot, text, pid=new_pid)
    except Exception as e:
        print(f"[NewProductBroadcast] failed: {e}")

    from telegram.ext import ConversationHandler
    return ConversationHandler.END

# 🔧 BUG FIX (Issues #2 & #3): There used to be a SECOND, duplicate
# `prod_delivery_received` here (plus dead photo code) that Python loaded LAST,
# overriding the correct one above. That duplicate:
#   • forced EVERY new product to delivery_mode='auto' (ignored Manual choice) → Issue #3
#   • used a hardcoded stock instead of honouring the chosen mode/stock     → Issue #2
# It has been removed so the correct `prod_delivery_received` + `_finalize_product_add`
# (which respect Manual/Auto and the admin-entered stock) are used.

async def delete_product_callback(u,c):
    await delete_product_confirm_callback(u, c)

# ── Orders ──
async def admin_orders_callback(u,c):
    q=u.callback_query
    nav_push(c, 'admin_orders')  # 🔙 Track navigation
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer(); await _safe_edit(q, "🛒 *Orders:*",parse_mode="Markdown",reply_markup=admin_pending_orders_keyboard(get_pending_orders()))

async def view_order_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer(); o=get_order(int(q.data.split("_")[2]))
    if not o: await _safe_edit(q, "❌ Order not found!"); return
    text=f"🛒 *#{o['id']}*\n👤 {escape_md(o['user_name'])} `{o['user_id']}`\n📦 {escape_md(o['product_name'])}\n💰 {fmt_price(o['price'])}\n💳 {o['payment_method']}\n📊 {o['status']}"
    if o['payment_method']=='binance': text+=f"\n🔶 {escape_md(o['binance_sender_name'])} — {o['binance_amount']}"
    # 🆕 v161.20 FIX (user demand): delivered content + file visible here too.
    try:
        _dc = str(o.get('delivery_content') or '').strip()
        _fid = str(o.get('delivery_file_id') or '').strip()
        if _dc or _fid:
            text += "\n━━━━━━━━━━━━━━━━━━━━\n📤 *Delivered:* "
            if _fid:
                text += f"\n📎 File attached ✅ `{escape_md(_fid[:18])}...`"
            if _dc:
                _preview = escape_md(_dc[:400].replace("\n", " "))
                text += f"\n📝 {_preview}" + ("…" if len(_dc) > 400 else "")
    except Exception:
        pass
    try:
        from database import get_order_deliveries
        _dlvs = get_order_deliveries(o['id'])
    except Exception:
        _dlvs = []
    kb_rows = admin_order_keyboard(o['id']).inline_keyboard
    if _dlvs:
        kb_rows = kb_rows + [[InlineKeyboardButton(f"📦 Delivered Items ({len(_dlvs)})",
                                                   callback_data=f"ac2_dlv_{o['id']}")]]
    from telegram import InlineKeyboardMarkup as _IKM
    _kb = _IKM(kb_rows)
    if o['payment_screenshot']:
        try:
            await q.delete_message()
            await c.bot.send_photo(q.from_user.id,o['payment_screenshot'],caption=text,parse_mode="Markdown",reply_markup=_kb)
            return
        except: pass
    await _safe_edit(q, text,parse_mode="Markdown",reply_markup=_kb)

async def approve_order_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer(); o=get_order(int(q.data.split("_")[1]))
    if not o: return

    # 🔧 BUG FIX #1: Check delivery mode BEFORE setting status.
    # Previously, status was set to 'delivered' first (triggering loyalty hooks),
    # then changed to 'paid_pending_delivery' for manual mode — causing incorrect
    # loyalty tier upgrades and double status updates.
    p = get_product(o['product_id']) if o['product_id'] else None
    try:
        delivery_mode = p['delivery_mode'] or 'auto' if p else 'auto'
    except Exception:
        delivery_mode = 'auto'

    # 🔧 ROBUST points detection — checks order_type AND product_id AND name as fallback
    is_points = (
        o['order_type'] == 'points' or
        (not o['product_id'] and 'Points' in (o['product_name'] or ''))
    )
    if is_points:
        import re
        m = re.search(r'(\d+)', o['product_name'] or '')
        pts = int(m.group(1)) if m else points_from_usd(o['price'] or 0)
        if pts > 0: add_points(o['user_id'], pts)
        # Points orders are always auto-delivered
        update_order_status(o['id'], 'delivered')
        msg = _r("payment_verified_points").format(pts=pts)
    else:
        # 🆕 Detect bulk order from product name (e.g. "Product × 5")
        import re as _re
        qty_match = _re.search(r'×\s*(\d+)$', o['product_name'] or '')
        order_qty = int(qty_match.group(1)) if qty_match else 1
        
        # 🆕 v69 BUG FIX: NO points credit on product purchase (was free-refund bug)
        pts = 0
        
        if delivery_mode == 'manual':
            update_order_status(o['id'], 'paid_pending_delivery')
            msg = f"✅ Payment for #{o['id']} received! Admin is processing your order manually."
            # Also notify admin
            creds = (dict(o) if o else {}).get('customer_credentials', '')
            admin_msg = f"🔔 *Payment Approved for #{o['id']}*\n\n" + \
                        f"Please fulfill the order.\n" + \
                        f"Customer details:\n`{creds}`\n"
            try: await c.bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Deliver Now", callback_data=f"adm_deliver_{o['id']}")]]))
            except: pass
        else:
            # 🔧 AUDIT-FIX C1/C2 (2026-07-31): structured result — never mark
            # 'delivered' when the stock pool couldn't cover the full qty.
            from database import build_delivery_detailed, save_order_delivery_content, add_order_delivery
            _dres = build_delivery_detailed(o['product_id'], o['id'], order_qty, o['user_id'])
            delivery = _dres['text']
            # 🐛 v161.20 FIX: this approval path never saved the delivery content
            # → Completed Orders showed "(nothing stored)". Now it's saved + logged.
            save_order_delivery_content(o['id'], delivery)
            add_order_delivery(o['id'], kind='text', content=delivery)
            if _dres['ok']:
                # 🆕 v69: NO add_points here
                update_order_status(o['id'], 'delivered')
                msg = _r("payment_verified_product").format(order_id=o['id'], product=o['product_name'], delivery=delivery, points=pts)
            else:
                _got, _want = _dres.get('delivered', 0), _dres.get('requested', order_qty)
                update_order_status(o['id'], 'paid_pending_delivery')
                msg = (f"⚠️ *Order #{o['id']} — not fully delivered*\n"
                       f"━━━━━━━━━━━━━━━━━━━━\n\n"
                       f"📦 Product: {escape_md(str(o.get('product_name') or '?')[:70])}\n"
                       f"🔢 Requested: *{_want}* · Delivered: *{_got}*\n\n"
                       f"The product ran out of stock while processing.\n"
                       f"Your order is in *Pending Delivery* — it will be completed "
                       f"or refunded.")
                try:
                    await c.bot.send_message(ADMIN_ID,
                        f"🚨 *Order #{o['id']} — partially delivered (OOS)*\n"
                        f"🔢 Requested: `{_want}` · Delivered: `{_got}`\n"
                        f"📦 Product: {escape_md(str(o.get('product_name') or '?')[:70])}\n"
                        f"👤 Customer: `{o['user_id']}`\n\n"
                        f"Complete the shortfall via *Pending Manual Delivery* or refund.",
                        parse_mode="Markdown")
                except Exception:
                    pass

    try:
        send_text, send_mode = smart_text_and_mode(msg, "Markdown")
        await c.bot.send_message(o['user_id'], send_text, parse_mode=send_mode)
    except: pass
    await _safe_edit(q, f"✅ #{o['id']} done!",reply_markup=admin_menu_keyboard())

async def reject_order_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer(); o=get_order(int(q.data.split("_")[1]))
    if not o: return
    update_order_status(o['id'],'rejected')
    try: await c.bot.send_message(o['user_id'],_r("order_rejected").format(order_id=o['id']))
    except: pass
    await _safe_edit(q, f"❌ #{o['id']} rejected!",reply_markup=admin_menu_keyboard())

# ── Profit/Loss ──
async def admin_profit_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer()
    await _safe_edit(q, "📊 *Profit/Loss Tracker*\n\nSelect a product or view all:", parse_mode="Markdown",
        reply_markup=admin_profit_keyboard(get_all_products(include_hidden=True)))

async def profit_product_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer(); pid=int(q.data.split("_")[1])
    d=get_product_profit(pid)
    if not d: await _safe_edit(q, "❌ Not found"); return
    emoji="📈" if d['profit']>=0 else "📉"
    await _safe_edit(q, f"""{emoji} *{escape_md(d['name'])}*
━━━━━━━━━━━━━━━━━━━━
💵 Cost Price: *${d['cost']:.2f}*
💰 Sell Price: *${d['sell']:.2f}*
📊 Per Item Profit: *${d['sell']-d['cost']:.2f}*
━━━━━━━━━━━━━━━━━━━━
🛒 Total Sales: *{d['sales']}*
💰 Revenue: *${d['revenue']:.2f}*
💵 Total Cost: *${d['total_cost']:.2f}*
{emoji} *Profit: ${d['profit']:.2f}*""", parse_mode="Markdown", reply_markup=admin_profit_keyboard(get_all_products(include_hidden=True)))

async def profit_all_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer()
    results,tr,tc,tp=get_all_products_profit()
    emoji="📈" if tp>=0 else "📉"
    text=f"{emoji} *All Products Summary*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for r in results:
        e="✅" if r['profit']>=0 else "❌"
        text+=f"{e} {escape_md(r['name'])}: {r['sales']} sold → ${r['profit']:.2f}\n"
    text+=f"\n━━━━━━━━━━━━━━━━━━━━\n💰 Total Revenue: *${tr:.2f}*\n💵 Total Cost: *${tc:.2f}*\n{emoji} *Net Profit: ${tp:.2f}*"
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=admin_profit_keyboard(get_all_products(include_hidden=True)))

# ── Users ──
async def admin_users_callback(u,c):
    """v65: paginated users list (50 per page) + per-user 📊 View Activity button."""
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer()

    # Parse page from callback_data
    page = 1
    if q.data and q.data.startswith("admin_users_p"):
        try:
            page = max(1, int(q.data.replace("admin_users_p", "")))
        except Exception:
            page = 1

    PER_PAGE = 50
    users = get_all_users()
    total = len(users)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    start = (page - 1) * PER_PAGE
    end   = start + PER_PAGE
    slice_ = users[start:end]

    text = (
        f"👤 *Users (Total: {total})*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📄 Page *{page}* of *{total_pages}*  "
        f"(showing {start+1}–{min(end, total)})\n\n"
    )
    for usr in slice_:
        uname = (usr['username'] or '').strip()
        uname_txt = f"@{escape_md(uname)}" if uname else "_no username_"
        fname = escape_md(usr['first_name'] or '?')
        text += f"• `{usr['user_id']}` — {fname} ({uname_txt}) 💎{usr['points']}\n"

    kb = []
    # Per-user 📊 View Activity buttons (2 per row to save vertical space)
    row = []
    for i, usr in enumerate(slice_):
        uid = usr['user_id']
        uname = (usr['username'] or '').strip()
        label_name = (('@' + uname) if uname else (usr['first_name'] or '?'))[:18]
        row.append(InlineKeyboardButton(f"📊 {label_name} {uid}", callback_data=f"adm_uact_{uid}"))
        if len(row) == 2:
            kb.append(row); row = []
    if row:
        kb.append(row)

    # Pagination nav
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⏮ First",  callback_data="admin_users_p1"))
        nav.append(InlineKeyboardButton("◀ Prev",   callback_data=f"admin_users_p{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ▶",   callback_data=f"admin_users_p{page+1}"))
        nav.append(InlineKeyboardButton("Last ⏭",   callback_data=f"admin_users_p{total_pages}"))
    if nav:
        for i in range(0, len(nav), 2):
            kb.append(nav[i:i+2])

    kb.append([InlineKeyboardButton("🔍 Search User (ID / username)", callback_data="adm_users_search")])
    kb.append([InlineKeyboardButton("💬 Start User Chat", callback_data="admin_direct_chat")])
    kb.append([InlineKeyboardButton("💎 Manage User Points", callback_data="adm_manage_pts")])
    # 🆕 v149: Refund any user by ID (with reason) + per-user full history
    kb.append([InlineKeyboardButton("💸 Refund by User ID", callback_data="adm_refund_uid")])
    kb.append([InlineKeyboardButton("📋 User Full History (by ID)", callback_data="adm_uhist_enter")])
    kb.append([InlineKeyboardButton("🧹 Wipe Activity Now",  callback_data="adm_uact_wipe_confirm")])
    kb.append([InlineKeyboardButton("🔙 Back to Admin",      callback_data="admin_panel")])

    await _safe_edit(q, text[:3900], parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════════════════════
# 🆕 v65: PER-USER ACTIVITY VIEWER
# ════════════════════════════════════════════════════════════
async def adm_user_activity_callback(u, c):
    """Show one user's activity history + summary."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    # Parse: adm_uact_<user_id> OR adm_uact_<user_id>_p<period>
    raw = q.data.replace("adm_uact_", "")
    period = "all"  # all / today / week / month
    if "_p" in raw:
        uid_part, period = raw.rsplit("_p", 1)
        if period not in ("all", "today", "week", "month"):
            period = "all"
    else:
        uid_part = raw
    try:
        uid = int(uid_part)
    except Exception:
        await q.answer("Invalid user", show_alert=True); return

    days_map = {"all": None, "today": 1, "week": 7, "month": 30}
    days = days_map.get(period)

    from user_tracking import get_user_stats, get_user_clicks, pretty_event
    stats = get_user_stats(uid, days=days)
    recent = get_user_clicks(uid, limit=20)

    # User info
    from database import get_user, get_user_points
    user = get_user(uid)
    fname = (user['first_name'] if user and 'first_name' in user.keys() else None) or '?'
    pts = get_user_points(uid)

    period_lbl = {"all": "Lifetime", "today": "Today",
                  "week": "Last 7 days", "month": "Last 30 days"}[period]

    text = (
        f"📊 *User Activity*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *{escape_md(fname)}* (`{uid}`)\n"
        f"💎 Points: {pts}\n"
        f"📅 Period: *{period_lbl}*\n\n"
        f"📈 *Total Clicks:* `{stats['total']}`\n"
    )
    if stats.get('first_seen'):
        text += f"🕓 First seen: `{stats['first_seen']}`\n"
    if stats.get('last_seen'):
        text += f"🕓 Last seen: `{stats['last_seen']}`\n"
    text += "\n"

    # Top actions
    by_action = stats.get('by_action', [])
    if by_action:
        text += "*🎯 Top Actions:*\n"
        for action, count in by_action[:10]:
            text += f"  • {pretty_event(action)}: `{count}`\n"
        text += "\n"
    else:
        text += "_No activity recorded in this period._\n\n"

    # Recent clicks
    if recent:
        text += "*🕓 Last 20 Clicks:*\n"
        for action, ts in recent:
            # Trim timestamp to HH:MM (date is rarely needed)
            ts_short = (ts or "")[5:16]  # MM-DD HH:MM
            text += f"  `{ts_short}` — {pretty_event(action)}\n"

    period_btns = [
        InlineKeyboardButton(
            ("• " if period == p else "") + lbl,
            callback_data=f"adm_uact_{uid}_p{p}",
        )
        for p, lbl in [("today","Today"), ("week","7d"), ("month","30d"), ("all","All")]
    ]
    kb = [
        period_btns[:2],
        period_btns[2:],
        # 🆕 v149: full history + quick refund straight from the activity view
        [InlineKeyboardButton("📋 Full History", callback_data=f"adm_uhist_{uid}"),
         InlineKeyboardButton("💸 Refund", callback_data=f"adm_refund_uid_{uid}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"adm_uact_{uid}_p{period}")],
        [InlineKeyboardButton("🔙 Back to Users", callback_data="admin_users")],
    ]

    await _safe_edit(q, text[:3900], parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def adm_user_activity_wipe_confirm_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    text = (
        "🧹 *Wipe All User Activity?*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "This will permanently delete ALL user click tracking records.\n"
        "Auto-wipe (every 60 days) is already enabled — manual wipe "
        "is rarely needed.\n\n"
        "Are you sure?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, wipe all", callback_data="adm_uact_wipe_do")],
        [InlineKeyboardButton("❌ Cancel",         callback_data="admin_users")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def adm_user_activity_wipe_do_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Wiping…")
    from user_tracking import wipe_old
    deleted = wipe_old(older_than_days=0)
    await _safe_edit(q,
        f"✅ Wiped {deleted} activity rows.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Users", callback_data="admin_users")],
        ]))

# ── Settings ──
async def admin_settings_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer()
    rate = get_setting('usd_pkr_rate', USD_TO_PKR_RATE)
    # Pull per-method names; fall back to legacy generic account_name for older installs
    legacy_name = get_setting('account_name', ACCOUNT_NAME)
    ep_name = get_setting('easypaisa_name', legacy_name)
    jc_name = get_setting('jazzcash_name', legacy_name)
    bn_name = get_setting('binance_name', legacy_name)
    # Binance Gmail status
    try:
        from payments import binance_api_is_configured as _bn_cfg
        bn_gmail_status = "✅ API keys set" if _bn_cfg() else "❌ API keys missing"
    except: bn_gmail_status = "❓ Unknown"
    text=f"""⚙️ *Settings*
━━━━━━━━━━━━━━━━━━━━
🏪 Shop: *{escape_md(get_setting('shop_name',SHOP_NAME))}*
📞 WhatsApp: *{escape_md(get_setting('whatsapp',WHATSAPP_NUMBER))}*
📧 Email: *{escape_md(get_setting('email',SUPPORT_EMAIL))}*
💱 USD→PKR Rate: *{rate}*

*🔶 Binance Pay:*
  ID: *{escape_md(get_setting('binance_id',BINANCE_PAY_ID))}*
  Name: *{escape_md(bn_name)}*
  🔌 API: *{bn_gmail_status}*

*📱 EasyPaisa:*
  Number: *{escape_md(get_setting('easypaisa',EASYPAISA_NUMBER))}*
  Name: *{escape_md(ep_name)}*

*📱 JazzCash:*
  Number: *{escape_md(get_setting('jazzcash',JAZZCASH_NUMBER))}*
  Name: *{escape_md(jc_name)}*

Tap to edit:"""
    await _safe_edit(q, text,parse_mode="Markdown",reply_markup=admin_settings_keyboard())

async def set_setting_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return ConversationHandler.END
    await q.answer()
    key=q.data.replace("set_","")
    labels={'shop_name':'Shop Name','whatsapp':'WhatsApp','binance':'Binance ID','easypaisa':'EasyPaisa Number','jazzcash':'JazzCash Number','account_name':'Account Name (legacy)','easypaisa_name':'EasyPaisa Holder Name','jazzcash_name':'JazzCash Holder Name','binance_name':'Binance Holder Name','email':'Support Email','pkr_rate':'USD→PKR Rate','binance_usdt_trc20_address':'Binance USDT TRC20 Address','binance_usdt_bep20_address':'Binance USDT BEP20 Address','bybit_pay_id':'Bybit Pay ID / UID','bybit_usdt_trc20_address':'Bybit USDT TRC20 Address','bybit_usdt_bep20_address':'Bybit USDT BEP20 Address'}
    c.user_data['sk']=key
    await _safe_edit(q, f"✏️ New *{labels.get(key,key)}*:", parse_mode="Markdown", reply_markup=inline_cancel_btn()); return SET_VALUE

async def setting_value_received(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    key=c.user_data.get('sk','')
    km={'binance':'binance_id','easypaisa':'easypaisa','jazzcash':'jazzcash','whatsapp':'whatsapp','shop_name':'shop_name','account_name':'account_name','easypaisa_name':'easypaisa_name','jazzcash_name':'jazzcash_name','binance_name':'binance_name','email':'email','pkr_rate':'usd_pkr_rate','binance_usdt_trc20_address':'binance_usdt_trc20_address','binance_usdt_bep20_address':'binance_usdt_bep20_address','bybit_pay_id':'bybit_pay_id','bybit_usdt_trc20_address':'bybit_usdt_trc20_address','bybit_usdt_bep20_address':'bybit_usdt_bep20_address'}
    val = u.message.text.strip()
    if key == 'pkr_rate':
        try: float(val.replace('Rs.','').replace(',','').strip())
        except:
            await u.message.reply_text("❌ Enter a number like 300", reply_markup=back_btn())
            return ConversationHandler.END
        val = val.replace('Rs.','').replace(',','').strip()
    else:
        try:
            html_v = (u.message.text_html_urled or "").strip()
        except Exception:
            html_v = ""
        if html_v and has_premium_emoji(u.message):
            val = "[[HTML]]" + html_v
    # 🆕 Log for undo
    setting_key = km.get(key, key)
    old_val = get_setting(setting_key, "")
    log_change("setting", setting_key, old_val, val, f"Setting: {key}")
    set_setting(setting_key, val)
    await u.message.reply_text("✅ Updated!",reply_markup=back_btn()); c.user_data.pop('sk',None); return ConversationHandler.END

# ── Edit Responses ──
async def admin_responses_callback(u,c):
    """✏️ Edit ALL bot responses — categorized & paginated"""
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer()
    await _show_responses_category(u, c)


def get_response_categories_map(all_keys=None):
    """Helper to return the categorized responses mapping."""
    if all_keys is None:
        try:
            from database import get_all_response_keys
            all_keys = get_all_response_keys()
        except Exception:
            all_keys = []
    _p = lambda *pfx: [k for k in all_keys if k.startswith(pfx)]
    CATEGORIES = {
        "main": {"name": "🏠 Main Menu", "keys": ["welcome", "my_account", "cancelled_message", "fj_verified_done"]},
        "shop": {"name": "🛒 Shop & Products", "keys": ["shop_title", "shop_categories_title", "product_detail", "no_products", "out_of_stock", "confirm_purchase", "confirm_bulk_purchase", "bulk_confirmed", "no_orders", "orders_title", "shop_no_available", "shop_no_unavailable"]},
        "payment": {"name": "💳 Payment Screens", "keys": [k for k in all_keys if k.startswith(("payment_", "binance_", "jazzcash_", "easypaisa_", "jc_", "ep_", "buy_points", "bybit_", "stars_"))]},
        "verify": {"name": "✅ Verification Messages", "keys": [k for k in all_keys if k.startswith(("payment_verified", "analyzing_", "screenshot_", "reupload_", "jc_reupload", "upload_image"))]},
        "orderflow": {"name": "🧾 Order Flow", "keys": [k for k in all_keys if k.startswith(("order_", "refund_"))]},
        "error": {"name": "❌ Error Messages", "keys": [k for k in all_keys if k.startswith("error_")]},
        "points": {"name": "💎 Points & Referrals", "keys": [k for k in all_keys if k.startswith(("points_", "referral_", "no_transactions", "buy_points"))]},
        "features": {"name": "🧩 Feature Screens", "keys": ["support_menu_header", "warranty_menu_header", "warranty_no_orders", "reviews_menu_header", "loyalty_menu_header", "language_menu_header"]},
        "tier": {"name": "🏆 Loyalty & Tiers", "keys": [k for k in all_keys if k.startswith("tier_")]},
        "freeclaim": {"name": "🎁 Free Claim", "keys": [k for k in all_keys if k.startswith("freeclaim_")]},
        "reseller": {"name": "🔗 Reseller API", "keys": [k for k in all_keys if k.startswith("reseller_api_")]},
        "other": {"name": "📞 Support & Other", "keys": ["support_text", "terms", "order_rejected", "new_user_notification", "binance_instructions", "refund_processed"]},
    }
    try:
        from custom_locations import get_custom_response_categories
        for cc in get_custom_response_categories():
            cat_id = cc.get("id", "")
            if cat_id and cat_id not in CATEGORIES:
                CATEGORIES[cat_id] = {
                    "name": cc.get("name") or cat_id,
                    "keys": [k for k in (cc.get("keys") or []) if k in all_keys],
                }
    except Exception:
        pass
    covered = set()
    for cat_info in CATEGORIES.values():
        covered.update(k for k in cat_info["keys"] if k in all_keys)
    uncategorized = sorted(set(all_keys) - covered)
    if uncategorized:
        CATEGORIES["uncategorized"] = {
            "name": f"📄 Other / New ({len(uncategorized)})",
            "keys": uncategorized,
        }
    return CATEGORIES


async def _show_responses_category(u, c, category="all", page=1):
    """Show responses editor — categorized with pagination.

    🐛 v95 FIX: Previously CATEGORIES was hardcoded and missed ~16 keys
    (freeclaim_*, tier_*, refund_processed, shop_no_available, etc.).
    Now every response is guaranteed to appear in at least one category
    via a computed "uncategorized" catch-all bucket.
    """
    q = u.callback_query

    from database import get_all_response_keys
    all_keys = get_all_response_keys()

    CATEGORIES = get_response_categories_map(all_keys)
    
    # Build category list
    if category == "all":
        total = len(all_keys)
        text = f"""✏️ *Edit Bot Responses*
━━━━━━━━━━━━━━━━━━━━

📊 Total: *{total}* editable responses

📝 Select a category to browse:
"""
        kb = []
        for cat_id, cat_info in CATEGORIES.items():
            count = len(cat_info["keys"])
            kb.append([InlineKeyboardButton(f"{cat_info['name']} ({count})", callback_data=f"respcat_{cat_id}")])
        kb.append([InlineKeyboardButton("📋 View ALL Responses", callback_data="respcat_all_list")])

        kb.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")])
        await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    else:
        # Show specific category
        cat_info = CATEGORIES.get(category, {"name": category, "keys": all_keys})
        keys = [k for k in cat_info["keys"] if k in all_keys] if category != "all_list" else all_keys
        
        per_page = 8
        total = len(keys)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        page_keys = keys[start:start + per_page]
        
        text = f"""✏️ *{(dict(cat_info) if cat_info else {}).get("name", "All Responses")}*
━━━━━━━━━━━━━━━━━━━━
📄 Page {page}/{total_pages} ({total} responses)

Tap any response to edit:"""
        
        kb = []
        for k in page_keys:
            # Get current value preview
            cur = get_response(k, DEFAULT_RESPONSES.get(k, ""))
            preview = cur[:50].replace("\n", " ").strip()
            if len(cur) > 50:
                preview += "…"
            # Clean preview for button
            preview = preview.replace("*", "").replace("`", "").replace("_", "")
            label = f"✏️ {k.replace('_', ' ').title()}"
            # 🔧 v133: show reaction icon if set
            try:
                from customization import get_reaction
                _rr = get_reaction(k)
                if _rr:
                    if _rr.startswith("premium:"):
                        label += " ⚡✨"
                    else:
                        label += f" ⚡{_rr}"
            except Exception:
                pass
            kb.append([InlineKeyboardButton(label, callback_data=f"editresp_{k}")])
        
        # Pagination
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"respcat_{category}_{page-1}"))
        nav.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"respcat_{category}_{page+1}"))
        if nav:
            kb.append(nav)
        
        kb.append([InlineKeyboardButton("🔙 Back to Categories", callback_data="admin_responses")])
        await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def admin_responses_category_callback(u, c):
    """Handle category/page navigation for responses"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    
    data = q.data.replace("respcat_", "")
    if data == "all_list":
        await _show_responses_category(u, c, category="all_list", page=1)
    elif "_" in data:
        parts = data.rsplit("_", 1)
        try:
            page = int(parts[1])
            await _show_responses_category(u, c, category=parts[0], page=page)
        except:
            await _show_responses_category(u, c, category=data, page=1)
    else:
        await _show_responses_category(u, c, category=data, page=1)

async def edit_response_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return ConversationHandler.END
    await q.answer(); key=q.data.replace("editresp_","")
    cur=get_response(key,DEFAULT_RESPONSES.get(key,""))
    c.user_data['erk']=key
    preview=cur[:400]+"..." if len(cur)>400 else cur
    await _safe_edit(q,
        f"✏️ *{key.replace('_',' ').title()}*\n\nCurrent:\n```\n{preview}\n```\n\n"
        f"Type new text:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="noop")],
        ])); return EDIT_RESP_VALUE

async def response_value_received(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    val = u.message.text or ""
    try:
        html_v = (u.message.text_html_urled or "").strip()
    except Exception:
        html_v = ""
    has_premium = has_premium_emoji(u.message)
    if html_v and has_premium:
        val = "[[HTML]]" + html_v
    erk = c.user_data.get('erk', '')
    set_response(erk, val)
    # 🆕 v53: Rich preview echo with rendered premium emojis (was just "✅ Updated!" before)
    from utils import safe_display
    disp, disp_mode = safe_display(val, preferred_mode="Markdown", message=u.message)
    if len(disp) > 1200:
        disp = disp[:1200] + ("…" if disp_mode != "HTML" else "<i>… (truncated)</i>")
    if disp_mode == "HTML":
        msg = (
            f"✅ <b>Response Updated!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 Key: <code>{erk}</code>\n\n"
            f"<b>Saved value (preview):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{disp}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        msg = (
            f"✅ *Response Updated!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 Key: `{erk}`\n\n"
            f"*Saved value (preview):*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{disp}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    await u.message.reply_text(msg, parse_mode=disp_mode, reply_markup=back_btn())
    c.user_data.pop('erk',None); return ConversationHandler.END

# ── Terms ──
async def admin_terms_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer(); await _safe_edit(q, _r("terms"),parse_mode="Markdown",reply_markup=admin_settings_keyboard())


# ── Broadcast/media helpers ──
def _admin_extract_media_payload(msg):
    """Return broadcast payload supporting text/photo/video/voice/document."""
    from utils import html_escape_plain
    media_type = "text"; media_id = ""; file_name = ""
    raw_text = ""
    html_text = ""
    if getattr(msg, "photo", None):
        media_type = "photo"; media_id = msg.photo[-1].file_id
        raw_text = msg.caption or ""; html_text = getattr(msg, "caption_html_urled", None) or getattr(msg, "caption_html", None) or ""
    elif getattr(msg, "video", None):
        media_type = "video"; media_id = msg.video.file_id
        raw_text = msg.caption or ""; html_text = getattr(msg, "caption_html_urled", None) or getattr(msg, "caption_html", None) or ""
    elif getattr(msg, "voice", None):
        media_type = "voice"; media_id = msg.voice.file_id
        raw_text = msg.caption or ""; html_text = getattr(msg, "caption_html_urled", None) or getattr(msg, "caption_html", None) or ""
    elif getattr(msg, "document", None):
        media_type = "document"; media_id = msg.document.file_id
        file_name = getattr(msg.document, "file_name", "") or ""
        raw_text = msg.caption or ""; html_text = getattr(msg, "caption_html_urled", None) or getattr(msg, "caption_html", None) or ""
    else:
        raw_text = msg.text or ""; html_text = getattr(msg, "text_html_urled", None) or getattr(msg, "text_html", None) or ""
    if html_text:
        body = html_text
    else:
        body = html_escape_plain(raw_text or "")
    # 🐛 v170.18 FIX: pehle "📢 Announcement" title khud prepend hota tha.
    # User demand: ab jo bhejo WESA hi jaye — koi automatic announcement nahi.
    text = body or ""
    return {"media_type": media_type, "media_id": media_id, "file_name": file_name, "text": text, "parse_mode": "HTML", "raw_text": raw_text}


def _admin_button_from_state(context, bot_username=""):
    data = context.user_data.get('broadcast_button') or {}
    if not data:
        return None
    label = data.get('label') or 'Open Bot'
    color = data.get('color') or ''
    action = data.get('action') or 'bot'
    # 🐛 v170.18 FIX: pehle color emoji DOT (🔴🔵🟢) label me lagta tha — REAL
    # background color nahi hota tha. Ab REAL style (danger/primary/success)
    # pass karte hain (Bot API 9.4 InlineKeyboardButton.style).
    style = {'red': 'danger', 'blue': 'primary', 'green': 'success'}.get(color, None)
    # 🐛 v147 FIX (Bug7): button action — open bot / custom link / product checkout
    try:
        from button_system import make_premium_button
        if action == 'url':
            url = data.get('url') or ''
            if not url:
                url = f"https://t.me/{bot_username}" if bot_username else "https://t.me/"
            try:
                btn = make_premium_button(label, style=style, url=url)
            except Exception:
                btn = InlineKeyboardButton(label, url=url)
        elif action == 'product':
            pid = int(data.get('pid') or 0)
            if pid:
                deep = f"https://t.me/{bot_username}?start=chk_{pid}" if bot_username else f"https://t.me/?start=chk_{pid}"
                try:
                    btn = make_premium_button(label, style=style, url=deep)
                except Exception:
                    btn = InlineKeyboardButton(label, url=deep)
            else:
                url = f"https://t.me/{bot_username}" if bot_username else "https://t.me/"
                try:
                    btn = make_premium_button(label, style=style, url=url)
                except Exception:
                    btn = InlineKeyboardButton(label, url=url)
        else:  # 'bot' default
            url = f"https://t.me/{bot_username}" if bot_username else "https://t.me/"
            try:
                btn = make_premium_button(label, style=style, url=url)
            except Exception:
                btn = InlineKeyboardButton(label, url=url)
    except Exception:
        url = f"https://t.me/{bot_username}" if bot_username else "https://t.me/"
        btn = InlineKeyboardButton(label, url=url)
    return InlineKeyboardMarkup([[btn]])


async def _send_payload(bot, chat_id, payload, reply_markup=None):
    mt = payload.get('media_type') or 'text'
    text = payload.get('text') or ''
    mode = payload.get('parse_mode') or 'HTML'
    mid = payload.get('media_id') or ''
    if mt == 'photo':
        return await bot.send_photo(chat_id, mid, caption=text[:1024] if text else None, parse_mode=mode, reply_markup=reply_markup)
    if mt == 'video':
        return await bot.send_video(chat_id, mid, caption=text[:1024] if text else None, parse_mode=mode, reply_markup=reply_markup)
    if mt == 'voice':
        return await bot.send_voice(chat_id, mid, caption=text[:1024] if text else None, parse_mode=mode, reply_markup=reply_markup)
    if mt == 'document':
        return await bot.send_document(chat_id, mid, caption=text[:1024] if text else None, parse_mode=mode, reply_markup=reply_markup)
    return await bot.send_message(chat_id, text, parse_mode=mode, reply_markup=reply_markup, disable_web_page_preview=True)


async def _broadcast_payload_to_all_users(bot, payload, reply_markup=None, notify_uid=None, title="Broadcast"):
    """🆕 v156: global broadcast with a LIVE progress counter for the admin."""
    from utils import BroadcastProgress
    users = get_all_users_for_broadcast() if 'get_all_users_for_broadcast' in globals() else get_all_users()
    prog = None
    if notify_uid:
        try:
            prog = BroadcastProgress(bot, notify_uid, title=title, total=len(users or []))
            await prog.start()
        except Exception:
            prog = None
    s = f = 0
    for usr in users:
        try:
            await _send_payload(bot, row_uid(usr), payload, reply_markup=reply_markup)
            s += 1
        except Exception:
            f += 1
        if prog is not None:
            try:
                await prog.bump()
            except Exception:
                pass
    if prog is not None:
        try:
            await prog.finish(
                f"✅ *{title} — Complete!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📤 Sent: *{s:,}* | ❌ Failed: *{f:,}*")
        except Exception:
            pass
    return s, f


async def _broadcast_payload_to_fake_destination(bot, payload, reply_markup=None):
    """One-time send to configured Fake Activity destination."""
    mode = get_setting('dest_mode', 'bot_only')
    dest_chat = get_setting('dest_chat_id', '').strip()
    s = f = 0
    if mode in ('bot_only', 'both'):
        ss, ff = await _broadcast_payload_to_all_users(bot, payload, reply_markup=reply_markup)
        s += ss; f += ff
    if mode in ('group_only', 'both') and dest_chat:
        try:
            await _send_payload(bot, dest_chat, payload, reply_markup=reply_markup)
            s += 1
        except Exception:
            f += 1
    return s, f


async def _send_global_broadcast_now(update, context):
    payload = context.user_data.pop('broadcast_payload', None)
    if not payload:
        await update.effective_message.reply_text("❌ Broadcast payload missing.")
        return
    markup = None
    if context.user_data.get('broadcast_button'):
        try:
            me = await context.bot.get_me()
            markup = _admin_button_from_state(context, getattr(me, 'username', '') or '')
        except Exception:
            markup = _admin_button_from_state(context, '')
    context.user_data.pop('broadcast_button', None)
    # 🆕 v156: live progress animation on the admin's chat
    s, f = await _broadcast_payload_to_all_users(context.bot, payload,
                                                 reply_markup=markup,
                                                 notify_uid=ADMIN_ID,
                                                 title="Global Broadcast")
    try:
        await update.effective_message.reply_text(f"✅ Broadcast sent: {s} | ❌ Failed: {f}",
                                                  reply_markup=admin_menu_keyboard())
    except Exception:
        pass


async def broadcast_button_choice_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    choice = q.data.replace('bcbtn_', '')
    await q.answer()
    if choice == 'no':
        await _send_global_broadcast_now(update, context); return
    context.user_data['broadcast_button_step'] = 'name'
    await _safe_edit(q, "🔘 Send button name/text now. Premium emojis supported.", parse_mode="Markdown", reply_markup=inline_cancel_btn())


async def broadcast_button_name_received(update, context):
    if update.effective_user.id != ADMIN_ID or context.user_data.get('broadcast_button_step') != 'name':
        return False
    msg = update.message
    try:
        label = msg.text_html_urled or msg.text_html or msg.text or 'Open Bot'
    except Exception:
        label = msg.text or 'Open Bot'
    context.user_data['broadcast_button'] = {'label': label}
    context.user_data['broadcast_button_step'] = 'action'
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('🤖 Open Bot (default)', callback_data='bcbtn_action_bot')],
        [InlineKeyboardButton('🔗 Custom Link', callback_data='bcbtn_action_url')],
        [InlineKeyboardButton('🛒 Product Checkout', callback_data='bcbtn_action_product')],
        [InlineKeyboardButton('❌ Cancel', callback_data='bcbtn_cancel')],
    ])
    await msg.reply_text('🔘 Button kis kaam ka hoga? Select action:', reply_markup=kb)
    return True


async def broadcast_button_action_callback(update, context):
    """🐛 v147 FIX (Bug7): choose what the broadcast button does —
    open bot / custom link / product checkout."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    action = q.data.replace('bcbtn_action_', '')
    await q.answer()
    if action == 'bot':
        context.user_data.setdefault('broadcast_button', {})['action'] = 'bot'
        context.user_data['broadcast_button_step'] = 'color'
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton('🔴 Red', callback_data='bcbtn_color_red'), InlineKeyboardButton('🔵 Blue', callback_data='bcbtn_color_blue'), InlineKeyboardButton('🟢 Green', callback_data='bcbtn_color_green')],
            [InlineKeyboardButton('❌ Cancel', callback_data='bcbtn_cancel')],
        ])
        await _safe_edit(q, '🎨 Button color select karo:', reply_markup=kb)
        return
    if action == 'url':
        context.user_data.setdefault('broadcast_button', {})['action'] = 'url'
        context.user_data['broadcast_button_step'] = 'url'
        await _safe_edit(q,
            "🔗 *Custom Link Button*\\n\\n"
            "Ab wo link paste karo jo button kholay (https://... ya https://t.me/...).",
            parse_mode="Markdown", reply_markup=inline_cancel_btn())
        return
    if action == 'product':
        context.user_data.setdefault('broadcast_button', {})['action'] = 'product'
        context.user_data['broadcast_button_step'] = 'product'
        await _show_broadcast_product_picker(update, context, page=0)
        return


async def _show_broadcast_product_picker(update, context, page=0):
    """v170.18: warranty/refund STYLE product picker (premium emoji + green
    buttons + stock) for the broadcast checkout button."""
    from database import get_all_products, is_product_hidden
    try:
        products = [p for p in get_all_products()
                    if not (dict(p).get('stock', 0) or 0) <= 0]
        products = [p for p in products
                    if not is_product_hidden(p['id'])]
    except Exception:
        products = []
    if not products:
        context.user_data.pop('broadcast_button_step', None)
        await _safe_edit(update.callback_query, "❌ Koi buyable product nahi mila.",
                         reply_markup=InlineKeyboardMarkup(
                             [[InlineKeyboardButton("🔙 Cancel", callback_data='bcbtn_cancel')]]))
        return
    try:
        from button_system import make_premium_button, extract_emoji_from_html
        _have = True
    except Exception:
        _have = False
    per = 8
    total = len(products)
    pages = max(1, (total + per - 1) // per)
    page = max(0, min(page, pages - 1))
    chunk = products[page * per:(page + 1) * per]
    rows = []
    lines = ["🛒 *Product Checkout Button*", "━━━━━━━━━━━━━━━━━━━━",
             "_(User button tap karega to us product ka payment screen khulega.)_", ""]
    for p in chunk:
        pid = p['id']
        raw = str(dict(p).get('name', f'Product #{pid}'))
        stock = int(dict(p).get('stock', 0) or 0)
        plain, eid = raw, ""
        if _have:
            try:
                _eid, _plain = extract_emoji_from_html(raw)
                if _plain:
                    plain = _plain
                eid = _eid or ""
            except Exception:
                pass
        lines.append(f"✅ #{pid} · {plain[:28]} (stock {stock})")
        if _have:
            rows.append([make_premium_button(
                f"🛒 {plain[:26]}", emoji_id=eid or None, style="success",
                callback_data=f"bcbtn_pick_{pid}")])
        else:
            rows.append([InlineKeyboardButton(
                f"🛒 {plain[:26]}", callback_data=f"bcbtn_pick_{pid}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"bcbtn_ppage_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{pages}", callback_data='bcbtn_noop'))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"bcbtn_ppage_{page+1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data='bcbtn_cancel')])
    await _safe_edit(update.callback_query,
                     "\n".join(lines),
                     parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(rows))



async def broadcast_button_product_page_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        page = int(q.data.replace('bcbtn_ppage_', ''))
    except Exception:
        page = 0
    await q.answer()
    await _show_broadcast_product_picker(update, context, page=page)


async def broadcast_button_noop_callback(update, context):
    await update.callback_query.answer()


async def broadcast_button_pick_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        pid = int(q.data.replace('bcbtn_pick_', ''))
    except Exception:
        await q.answer("Invalid", show_alert=True); return
    context.user_data.setdefault('broadcast_button', {})['pid'] = pid
    context.user_data['broadcast_button_step'] = 'color'
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('🔴 Red', callback_data='bcbtn_color_red'), InlineKeyboardButton('🔵 Blue', callback_data='bcbtn_color_blue'), InlineKeyboardButton('🟢 Green', callback_data='bcbtn_color_green')],
        [InlineKeyboardButton('❌ Cancel', callback_data='bcbtn_cancel')],
    ])
    await _safe_edit(q, '🎨 Button color select karo:', reply_markup=kb)


async def broadcast_button_url_received(update, context):
    """🐛 v147 FIX (Bug7): receive the custom link for the button."""
    if update.effective_user.id != ADMIN_ID or context.user_data.get('broadcast_button_step') != 'url':
        return False
    url = (update.message.text or '').strip()
    if not url.lower().startswith(('http://', 'https://', 't.me/')):
        await update.message.reply_text(
            "❌ Link `http://` ya `https://` se start hona chahiye. Dobara bhejo:",
            parse_mode="Markdown")
        return True
    if url.lower().startswith('t.me/'):
        url = 'https://' + url
    context.user_data.setdefault('broadcast_button', {})['url'] = url
    context.user_data['broadcast_button_step'] = 'color'
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('🔴 Red', callback_data='bcbtn_color_red'), InlineKeyboardButton('🔵 Blue', callback_data='bcbtn_color_blue'), InlineKeyboardButton('🟢 Green', callback_data='bcbtn_color_green')],
        [InlineKeyboardButton('❌ Cancel', callback_data='bcbtn_cancel')],
    ])
    await update.message.reply_text('🎨 Button color select karo:', reply_markup=kb)
    return True


async def broadcast_button_color_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    data = q.data
    if data == 'bcbtn_cancel':
        context.user_data.pop('broadcast_payload', None); context.user_data.pop('broadcast_button', None); context.user_data.pop('broadcast_button_step', None)
        await q.answer('Cancelled'); await _safe_edit(q, '❌ Broadcast cancelled.', reply_markup=admin_menu_keyboard()); return
    color = data.replace('bcbtn_color_', '')
    context.user_data.setdefault('broadcast_button', {})['color'] = color
    context.user_data.pop('broadcast_button_step', None)
    try:
        me = await context.bot.get_me()
        markup = _admin_button_from_state(context, getattr(me, 'username', '') or '')
    except Exception:
        markup = _admin_button_from_state(context, '')
    await q.answer('Preview')
    await _safe_edit(q, '👀 *Preview:*\n\nBroadcast with this button?', parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([
        [markup.inline_keyboard[0][0]],
        [InlineKeyboardButton('✅ Yes Broadcast', callback_data='bcbtn_send_yes'), InlineKeyboardButton('❌ No', callback_data='bcbtn_send_no')]
    ]))


async def broadcast_button_send_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    if q.data == 'bcbtn_send_no':
        context.user_data.pop('broadcast_payload', None); context.user_data.pop('broadcast_button', None)
        await _safe_edit(q, '❌ Broadcast cancelled.', reply_markup=admin_menu_keyboard()); return
    await _send_global_broadcast_now(update, context)


async def fake_custom_broadcast_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer('❌', show_alert=True); return
    await q.answer()
    context.user_data['fake_custom_broadcast'] = True
    await _safe_edit(q,
        '📤 *Custom One-Time Broadcast*\n\nSend text/photo/video/voice/document. Premium emojis supported. It will go to Fake Activity destination once.',
        parse_mode='Markdown', reply_markup=inline_cancel_btn())


async def handle_fake_custom_broadcast_message(update, context):
    if update.effective_user.id != ADMIN_ID or not context.user_data.get('fake_custom_broadcast'):
        return False
    context.user_data.pop('fake_custom_broadcast', None)
    payload = _admin_extract_media_payload(update.message)
    s, f = await _broadcast_payload_to_fake_destination(context.bot, payload)
    await update.message.reply_text(f"✅ Custom broadcast sent: {s} | ❌ Failed: {f}", reply_markup=admin_menu_keyboard())
    return True


async def handle_static_delivery_media_message(update, context):
    if update.effective_user.id != ADMIN_ID:
        return False
    if context.user_data.get('edit_field') != 'deliverytext' or not context.user_data.get('edit_pid'):
        return False
    msg = update.message
    payload = _admin_extract_media_payload(msg)
    if payload.get('media_type') == 'text':
        return False
    pid = int(context.user_data.pop('edit_pid'))
    context.user_data.pop('edit_field', None)
    mt = payload['media_type']; mid = payload['media_id']; caption = payload.get('raw_text') or ''
    try:
        set_product_static_delivery(pid, caption, mid, mt, getattr(getattr(msg, 'document', None), 'file_name', '') or '', caption)
        sync_product_stock_from_accounts(pid)
    except Exception as e:
        await msg.reply_text(f"❌ Static media save failed: {e}")
        return True
    await msg.reply_text("✅ Static delivery media saved.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 Back to Product', callback_data=f'viewprod_{pid}')]]))
    return True

# ── Broadcast ──
async def broadcast_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer(); await _safe_edit(q, "🌐 Send broadcast message now. Text/photo/video/voice/file supported.", parse_mode="Markdown", reply_markup=inline_cancel_btn())
    c.user_data['broadcasting']=True

async def handle_broadcast_message(u,c):
    """Global broadcast input: supports text/photo/video/voice/document + optional button."""
    if u.effective_user.id!=ADMIN_ID: return
    if not c.user_data.get('broadcasting'): return
    c.user_data['broadcasting']=False
    try:
        from maintenance_mode import is_maintenance_on
        if is_maintenance_on():
            await u.message.reply_text("🛠️ *Maintenance ON* — broadcast skipped.", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
            return
    except Exception:
        pass
    payload = _admin_extract_media_payload(u.message)
    c.user_data['broadcast_payload'] = payload
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Yes, add button', callback_data='bcbtn_yes'), InlineKeyboardButton('❌ No button', callback_data='bcbtn_no')]
    ])
    await u.message.reply_text('🔘 Broadcast ke sath button add karna hai?', reply_markup=kb)

async def cancel_conversation(u,c):
    # 🔧 BUG FIX #2: Only clear conversation-specific keys, NOT everything.
    # Previously, c.user_data.clear() wiped ALL state including nav_stack,
    # pending orders, language preference, AI mode, etc.
    conv_keys = [
        'cat_n', 'cat_e',
        'pc', 'pn', 'pd', 'pp', 'pcp', 'ps', 'pw', 'pq', 'pph', 'delivery_mode',
        'sk', 'erk',
        'cb_new_type', 'cb_new_label', 'cb_new_action',
        'cb_edit_bid', 'cb_edit_field', 'cb_edit_btype',
        'cp_title', 'cp_content', 'cp_edit_pid', 'cp_edit_field',
        'mb_btn_id', 'mb_size',
        'edit_pid', 'edit_field', 'edit_cat_id', 'edit_cat_field',
        'edit_acct_id', 'edit_acct_pid', 'edit_acct_page',
        'broadcasting',
    ]
    for k in conv_keys:
        c.user_data.pop(k, None)
    await u.message.reply_text("❌ Cancelled.",reply_markup=back_btn())
    return ConversationHandler.END


# ════════════════════════════════════════════
# 🎨 CUSTOMIZATION MENU (Step 1 - basic)
# ════════════════════════════════════════════

async def admin_customization_callback(u, c):
    """🆕 Customization main menu"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    # ── 🆕 v144: REBUILT customization hub (clean sections + live summary) ──
    await _render_customization_hub(q)


async def admin_toggles_callback(u, c):
    """🆕 Show toggles screen — now with Shop Categorized toggle"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    t_w = get_toggle("show_warranty")
    t_q = get_toggle("show_quantity")
    t_s = get_toggle("show_stock")
    t_p = get_toggle("show_photo")
    t_sold = get_toggle("show_sold")
    t_pemoji = get_toggle("show_product_emoji")  # 🆕 v42
    t_autocol = get_toggle("auto_product_colors", "0")  # 🎨 v46
    t_autogrp = get_toggle("auto_group_by_name", "1")  # 🆕 v98 default ON
    emoji_char = get_setting("product_emoji", "🛍️") or "🛍️"  # 🆕 v42
    cat_mode = get_setting("shop_categorized", "0")
    text = f"""👁️ *Product Toggles & Shop Mode*
━━━━━━━━━━━━━━━━━━━━

*Product Detail Fields:*
🛡️ Warranty: {'✅ Shown' if t_w=='1' else '❌ Hidden'}
📦 Quantity: {'✅ Shown' if t_q=='1' else '❌ Hidden'}
📊 Stock: {'✅ Shown' if t_s=='1' else '❌ Hidden'}
🔥 Sold Count: {'✅ Shown' if t_sold=='1' else '❌ Hidden'}
📸 Photo: {'✅ Shown' if t_p=='1' else '❌ Hidden'}

*Shop List Buttons:*
{emoji_char} Product List Emoji: {'✅ Shown' if t_pemoji=='1' else '❌ Hidden'}
✏️ Current emoji: {emoji_char}  (tap "Change Product Emoji" below to change)

*Shop Display Mode:*
🗂️ Categorized: {'✅ ON' if cat_mode=='1' else '❌ OFF (flat list)'}

*🎨 Auto Button Colors:* {'✅ ON' if t_autocol=='1' else '❌ OFF'}
  🔴 Out of stock  ·  🔵 Manual delivery  ·  🟢 Auto delivery
  _(Colors need bot owner Telegram Premium to show)_

*🔤 Auto-Group by First Word:* {'✅ ON' if t_autogrp=='1' else '❌ OFF'}
  _Products sharing the first word cluster together in shop list._
  _e.g. "Super Grok 1M" & "Super Grok 3M" appear one below the other._

Tap a button below to toggle:"""
    kb_inline = toggles_keyboard(t_w, t_q, t_s, t_p, t_sold, t_pemoji, emoji_char)
    # Inject the shop categorized button before the Return row
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = list(kb_inline.inline_keyboard)
    cat_lbl = f"{'🟢' if cat_mode=='1' else '🔴'} 🗂️ Shop Categorized: {'ON' if cat_mode=='1' else 'OFF'}"
    rows.insert(-1, [InlineKeyboardButton(cat_lbl, callback_data="toggle_shop_cat")])
    # 🎨 v46: Auto product-color toggle
    col_lbl = f"{'🟢' if t_autocol=='1' else '🔴'} 🎨 Auto Product Colors: {'ON' if t_autocol=='1' else 'OFF'}"
    rows.insert(-1, [InlineKeyboardButton(col_lbl, callback_data="toggle_auto_product_colors")])
    # 🆕 v98: Auto-group by first word toggle
    grp_lbl = f"{'🟢' if t_autogrp=='1' else '🔴'} 🔤 Auto-Group by First Word: {'ON' if t_autogrp=='1' else 'OFF'}"
    rows.insert(-1, [InlineKeyboardButton(grp_lbl, callback_data="toggle_auto_group_by_name")])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))


async def toggle_field_callback(u, c):
    """🆕 Handle toggle button click"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    field = q.data.replace("toggle_", "")
    current = get_toggle(field)
    new = "0" if current == "1" else "1"
    # 🆕 Log for undo
    log_change("toggle", f"toggle_{field}", current, new, f"Toggle: {field}")
    set_toggle(field, new)
    await q.answer(f"{'Shown' if new=='1' else 'Hidden'} ✅")
    await admin_toggles_callback(u, c)


# ════════════════════════════════════════════
# 🆕 v42: Edit product list emoji (the default 🛍️ prefix)
# ════════════════════════════════════════════
EDIT_PRODUCT_EMOJI = 9210  # 🐛 v95: bumped from 921 to avoid ConversationHandler state collision with force-join module (safety-in-depth)

async def edit_product_emoji_callback(u, c):
    """Ask admin for a new emoji to prefix product names with."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    current = get_setting("product_emoji", "🛍️") or "🛍️"
    text = (
        "✏️ *Change Product List Emoji*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Current:* {current}\n\n"
        "Send 1 emoji (or a short symbol) that should appear before "
        "every product name in the shop list.\n\n"
        "_Tip: Use standard emojis from your keyboard. Custom/Premium "
        "emojis are NOT allowed in button labels by Telegram (only in "
        "message body, not in buttons)._\n\n"
        "Send `-` to reset to the default 🛍️.\n"
        "Send /cancel to cancel."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Cancel", callback_data="admin_toggles")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)
    return EDIT_PRODUCT_EMOJI


async def edit_product_emoji_received(u, c):
    if u.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    # 🆕 v48: capture WITH premium emoji preservation
    from utils import capture_user_text, safe_display
    val_raw = (u.message.text or "").strip()
    val = capture_user_text(u.message).strip()
    _mode = "Markdown"
    if val_raw == "-" or val_raw.lower() == "reset":
        set_setting("product_emoji", "🛍️")
        msg = "♻️ Product emoji reset to default 🛍️"
    else:
        # Keep it short (button labels have width limits)
        if len(val_raw) > 8 and not val.startswith("[[HTML]]"):
            await u.message.reply_text(
                "⚠️ Bohat lamba hai — sirf 1 emoji ya 1-2 char ka symbol use karein."
            )
            return EDIT_PRODUCT_EMOJI
        set_setting("product_emoji", val)
        # 🆕 v53: pass message so safe_display can re-derive premium HTML from entities
        disp, disp_mode = safe_display(val, preferred_mode="Markdown", message=u.message)
        if disp_mode == "HTML":
            msg = f"✅ Product list emoji updated to: {disp}"
            _mode = "HTML"
        else:
            msg = f"✅ Product list emoji updated to: *{disp}*"
            _mode = "Markdown"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Toggles", callback_data="admin_toggles")],
    ])
    await u.message.reply_text(msg, parse_mode=_mode, reply_markup=kb)
    return ConversationHandler.END


# ════════════════════════════════════════════
# 📏 BUTTON SIZE (Step 2)
# ════════════════════════════════════════════

async def admin_btn_size_callback(u, c):
    """📏 Show button size selection screen"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    current = get_setting("button_size", "medium")
    text = f"""📏 *Button Sizes*
━━━━━━━━━━━━━━━━━━━━

Choose how buttons look across the bot:

📱 *Small* — Emoji only, 3 per row
   Best for: compact view, mobile

💻 *Medium* — Emoji + short text, 2 per row
   Best for: balanced look (default)

🖥️ *Large* — Emoji + full text, 2 per row
   Best for: clarity, easy reading

📺 *Extra Large* — Full label, 1 per row
   Best for: accessibility, big screens

━━━━━━━━━━━━━━━━━━━━
Current: *{current.upper()}*

Tap to change:"""
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=button_size_keyboard(current))


async def set_button_size_callback(u, c):
    """📏 Set button size from callback like 'setsize_small'"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    size = q.data.replace("setsize_", "").lower()
    if size not in ("small", "medium", "large", "xl"):
        await q.answer("Invalid size", show_alert=True); return
    # 🆕 Log for undo
    old_size = get_setting("button_size", "medium")
    log_change("setting", "button_size", old_size, size, "Button size")
    set_setting("button_size", size)
    await q.answer(f"✅ Size changed to {size.upper()}")
    await admin_btn_size_callback(u, c)


# ════════════════════════════════════════════
# 🎨 MENU STYLES (Step 3)
# ════════════════════════════════════════════

async def admin_menu_style_callback(u, c):
    """🎨 Show menu style selection screen"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    from button_system import get_style_id, STYLES
    current = get_style_id()
    cur_info = STYLES.get(current, STYLES[1])
    text = f"""🎨 *Menu Styles*
━━━━━━━━━━━━━━━━━━━━

Choose how your bot's menu buttons look.
Combines with Button Size for max customization!

📌 *Current:* {cur_info['name']}
📝 {cur_info['desc']}
👁️ Preview: `{cur_info['preview']}`

━━━━━━━━━━━━━━━━━━━━
Tap a style to apply:"""
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=menu_styles_keyboard(current))


async def set_menu_style_callback(u, c):
    """🎨 Apply selected menu style"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        sid = int(q.data.replace("setstyle_", ""))
    except ValueError:
        await q.answer("Invalid", show_alert=True); return
    if not (1 <= sid <= 10):
        await q.answer("Invalid style", show_alert=True); return
    # 🆕 Log for undo
    old_style = get_setting("menu_style", "1")
    log_change("setting", "menu_style", old_style, str(sid), "Menu style")
    set_setting("menu_style", str(sid))
    from button_system import STYLES
    name = STYLES[sid]["name"]
    await q.answer(f"✅ Applied: {name}")
    # Refresh screen
    await admin_menu_style_callback(u, c)


# ════════════════════════════════════════════
# 🎠 DISPLAY FORMAT (Step 4 — Raw / Carousel)
# ════════════════════════════════════════════

async def admin_display_format_callback(u, c):
    """🎠 Show display format selection screen"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    current = get_setting("display_format", "raw")
    if current not in ("raw", "carousel"): current = "raw"
    text = f"""🎠 *Display Format*
━━━━━━━━━━━━━━━━━━━━

How should the Shop / Product list look?

📋 *Raw (Classic List)* — DEFAULT
   Sab products ek vertical list mein
   Compact, fast to browse
   Best for: bohat saare products

🎠 *Carousel (Card View)*
   Ek product at a time + photo
   Swipe Next/Prev buttons
   Big product photo + caption
   Best for: visual products, premium feel

━━━━━━━━━━━━━━━━━━━━
Current: *{current.upper()}*

Tap to switch:"""
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=display_format_keyboard(current))


async def set_display_format_callback(u, c):
    """🎠 Apply selected display format"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    fmt = q.data.replace("setformat_", "").lower()
    if fmt not in ("raw", "carousel"):
        await q.answer("Invalid format", show_alert=True); return
    # 🆕 Log for undo
    old_fmt = get_setting("display_format", "raw")
    log_change("setting", "display_format", old_fmt, fmt, "Display format")
    set_setting("display_format", fmt)
    await q.answer(f"✅ Format set to {fmt.upper()}")
    # Refresh screen
    await admin_display_format_callback(u, c)


# ════════════════════════════════════════════
# 🎛️ MANAGE BUTTONS (Phase A — Rename / Hide / Show)
# ════════════════════════════════════════════
from button_system import (
    BUTTONS as BTN_REGISTRY, GROUP_NAMES,
    is_button_hidden, reset_button
)

# New state for button rename
MB_RENAME_VALUE = 100
MB_SCREEN_PAD_VALUE = 101


async def admin_buttons_callback(u, c):
    """🎛️ Show button management — list of groups"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    text = """🎛️ *Manage Buttons*
━━━━━━━━━━━━━━━━━━━━

You can do 2 things here:

➕ *Add Custom Button*
   Create your own buttons (URL link, Text msg, etc.)
   These show up wherever you place them.

⚙️ *Manage System Buttons*
   Rename / Hide / Reorder existing buttons.

📌 *Status indicators:*
🟢 Visible | 🔴 Hidden | 🔒 Essential (cannot hide)
🔄 Use ⬆️ ⬇️ arrows to reorder."""
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=manage_buttons_groups_keyboard())


async def manage_buttons_group_callback(u, c):
    """Show buttons in a group.
    🆕 v54: Extracted rendering to _render_manage_group so callers (e.g. after
    set_cb_data + re-call) can skip the duplicate q.answer()."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    group_id = q.data.replace("mbgrp_", "")
    await _render_manage_group(q, group_id)


async def _render_manage_group(q, group_id):
    """Render the group's button list (no q.answer() — caller already handled)."""
    group_name = GROUP_NAMES.get(group_id, group_id)
    text = f"""🎛️ *{group_name}*
━━━━━━━━━━━━━━━━━━━━

📝 Tap *label* to rename / change color / hide.
⬆️ ⬇️ Tap arrows to reorder buttons.

🟢 Visible | 🔴 Hidden | 🔒 Essential"""
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=manage_buttons_list_keyboard(group_id))


async def manage_one_button_callback(u, c):
    """Show actions for a single button.
    🆕 v54: Premium-emoji-aware preview — saved labels with [[HTML]]/<tg-emoji>
    now RENDER as actual premium emojis (HTML mode) instead of showing raw
    sentinel text inside a code block."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    btn_id = q.data.replace("mbedit_", "")
    await _render_manage_one_button(q, btn_id)


async def _render_manage_one_button(q, btn_id):
    """Render the single-button edit panel (no q.answer — caller handles).
    Extracted in v54 so refresh callers (toggle/reset/color save) don't
    re-call q.answer() and trigger Telegram 'query already answered' warning.
    """
    btn = BTN_REGISTRY.get(btn_id)
    if not btn:
        await _safe_edit(q, "❌ Button not found.", reply_markup=back_btn())
        return

    # Build preview showing each size with current label
    from database import get_setting
    from utils import is_html_value, contains_premium_markup, smart_text_and_mode, html_strip_tags
    sizes_data = []
    any_has_premium = False
    for sz in ("short", "medium", "large", "xl"):
        custom = get_setting(f"btn_label_{btn_id}_{sz}", "")
        default = btn.get(sz, "")
        cur_val = custom if custom else default
        edited = bool(custom)
        if is_html_value(cur_val) or contains_premium_markup(cur_val):
            any_has_premium = True
        sizes_data.append((sz, cur_val, edited))

    status = "🔒 Essential" if btn.get("essential") else ("🔴 Hidden" if is_button_hidden(btn_id) else "🟢 Visible")
    grp_name = GROUP_NAMES.get(btn.get('group'), btn.get('group'))

    if any_has_premium:
        # HTML mode — render premium emojis natively, no code block
        from utils import escape_md
        lines_html = []
        for sz, cur_val, edited in sizes_data:
            mark = "  ✏️" if edited else ""
            rendered, _ = smart_text_and_mode(cur_val, "HTML")
            # Strip any leftover HTML tags except <tg-emoji>/<b>/<i>
            lines_html.append(f"   <b>{sz.upper()}</b> :  {rendered}{mark}")
        body_html = "\n".join(lines_html)
        # Escape HTML special chars only in btn_id and group_name (avoid breaking parse)
        import html as _hlib
        text = (
            f"🎛️ <b>Button:</b> <code>{_hlib.escape(btn_id)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Group:</b> {_hlib.escape(grp_name)}\n"
            f"<b>Status:</b> {status}\n\n"
            f"📋 <b>Current labels (per size):</b>\n"
            f"{body_html}\n\n"
            f"✏️ = customized by admin\n\n"
            f"Choose an action:"
        )
        await _safe_edit(q, text, parse_mode="HTML",
                         reply_markup=manage_one_button_keyboard(btn_id))
    else:
        # Plain Markdown — original safer format
        sizes = []
        for sz, cur_val, edited in sizes_data:
            if edited:
                sizes.append(f"  {sz.upper():6}: {cur_val}  ✏️")
            else:
                sizes.append(f"  {sz.upper():6}: {cur_val}")
        text = f"""🎛️ *Button:* `{btn_id}`
━━━━━━━━━━━━━━━━━━━━
*Group:* {grp_name}
*Status:* {status}

📋 *Current labels (per size):*
```
{chr(10).join(sizes)}
```
✏️ = customized by admin

Choose an action:"""
        await _safe_edit(q, text, parse_mode="Markdown",
                         reply_markup=manage_one_button_keyboard(btn_id))


async def toggle_button_visibility_callback(u, c):
    """Hide / Show a button"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    btn_id = q.data.replace("mbtog_", "")
    btn = BTN_REGISTRY.get(btn_id)
    if not btn or btn.get("essential"):
        await q.answer("❌ Cannot hide essential button", show_alert=True); return
    currently_hidden = is_button_hidden(btn_id)
    new_val = "0" if currently_hidden else "1"
    log_change("setting", f"btn_hidden_{btn_id}", "1" if currently_hidden else "0", new_val,
               f"{'Show' if currently_hidden else 'Hide'}: {btn_id}")
    set_setting(f"btn_hidden_{btn_id}", new_val)
    await q.answer(f"{'Shown' if currently_hidden else 'Hidden'} ✅")
    # 🆕 v54: refresh via dedicated render helper (no double q.answer)
    await _render_manage_one_button(q, btn_id)


async def reset_button_callback(u, c):
    """♻️ Reset a button to default"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    btn_id = q.data.replace("mbrst_", "")
    if btn_id not in BTN_REGISTRY:
        await q.answer("❌", show_alert=True); return
    reset_button(btn_id)
    await q.answer("♻️ Reset to default ✅")
    # 🆕 v54: refresh via render helper (no double answer)
    await _render_manage_one_button(q, btn_id)


async def button_color_callback(u, c):
    """🎨 v46: Open background-color picker for a registry button."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    btn_id = q.data.replace("mbcolor_", "")
    if btn_id not in BTN_REGISTRY:
        await q.answer("❌ Button not found", show_alert=True); return
    from button_system import get_button_style
    cur = get_button_style(btn_id) or "default"
    text = (f"🎨 *Button Background Color*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"*Button:* `{btn_id}`\n"
            f"*Current:* `{cur}`\n\n"
            f"Telegram supports 3 button colors:\n"
            f"🔵 Blue · 🟢 Green · 🔴 Red\n\n"
            f"⭐ *Note:* The color only renders if the bot OWNER account has "
            f"Telegram Premium (Bot API 9.4).")
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=button_color_picker_keyboard(btn_id))


async def button_set_color_callback(u, c):
    """🎨 v46: Save the chosen color. Callback: mbsetcol_<btn_id>_<style>"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    raw = q.data.replace("mbsetcol_", "")
    btn_id, _, style = raw.rpartition("_")
    if btn_id not in BTN_REGISTRY:
        await q.answer("❌ Button not found", show_alert=True); return
    from button_system import set_button_style
    save_style = "" if style == "none" else style
    old = get_setting(f"btn_style_{btn_id}", "")
    log_change("setting", f"btn_style_{btn_id}", old, save_style, f"Color: {btn_id}")
    set_button_style(btn_id, save_style)
    nice = {"primary": "🔵 Blue", "success": "🟢 Green",
            "danger": "🔴 Red", "none": "⬜ Default"}.get(style, style)
    await q.answer(f"Color set: {nice} ✅")
    # 🆕 v54: refresh via render helper (no double answer)
    await _render_manage_one_button(q, btn_id)


async def group_color_callback(u, c):
    """🎨 v46: open bulk-color picker for ALL buttons in a group. mbgcolor_<group>"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    group_id = q.data.replace("mbgcolor_", "")
    gname = GROUP_NAMES.get(group_id, group_id)
    from button_system import get_group_style
    cur = get_group_style(group_id) or "default"
    text = (f"🎨 *Set Color for ALL — {gname}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"*Current:* `{cur}`\n\n"
            f"Pick ONE color to apply to *every* button in this section "
            f"in one click. (Per-button colors still override this.)\n\n"
            f"⭐ Colors need bot owner Telegram Premium to show.")
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=group_color_picker_keyboard(group_id))


async def group_set_color_callback(u, c):
    """🎨 v46: apply bulk color. mbgsetcol_<group>_<style>"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    raw = q.data.replace("mbgsetcol_", "")
    group_id, _, style = raw.rpartition("_")
    from button_system import set_group_style
    save_style = "" if style == "none" else style
    old = get_setting(f"grpstyle_{group_id}", "")
    log_change("setting", f"grpstyle_{group_id}", old, save_style, f"Bulk color: {group_id}")
    set_group_style(group_id, save_style)
    nice = {"primary": "🔵 Blue", "success": "🟢 Green",
            "danger": "🔴 Red", "none": "⬜ Default"}.get(style, style)
    await q.answer(f"All buttons → {nice} ✅", show_alert=True)
    # 🆕 v54: refresh via render helper (no double answer)
    await _render_manage_group(q, group_id)


async def group_screen_pad_callback(u, c):
    """📐 v46: increase/decrease/clear whole-screen padding. mbscrpad_<group>_<delta>"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    raw = q.data.replace("mbscrpad_", "")
    group_id, _, delta = raw.rpartition("_")
    from button_system import get_screen_pad, set_screen_pad
    cur = get_screen_pad(group_id)
    if delta == "0":
        newval = 0
    else:
        try:
            newval = cur + int(delta)
        except (TypeError, ValueError):
            newval = cur
    newval = set_screen_pad(group_id, newval)
    await q.answer(f"📐 Screen padding: {newval}")
    # 🆕 v54: refresh via render helper (no double answer)
    await _render_manage_group(q, group_id)


async def group_screen_pad_custom_start_callback(u, c):
    """Ask admin for an exact whole-screen padding number (0..40)."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return ConversationHandler.END
    await q.answer()
    group_id = q.data.replace("mbscrpadcustom_", "")
    c.user_data['mb_screenpad_group'] = group_id
    from button_system import get_screen_pad
    cur = get_screen_pad(group_id)
    await _safe_edit(q,
        f"📐 *Custom Screen Padding*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Group: *{GROUP_NAMES.get(group_id, group_id)}*\n"
        f"Current: *{cur}*\n\n"
        f"Type a number from *0 to 40*.\n"
        f"0 = reset / no extra padding.",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return MB_SCREEN_PAD_VALUE


async def group_screen_pad_custom_received(u, c):
    if u.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    group_id = c.user_data.pop('mb_screenpad_group', None)
    if not group_id:
        return ConversationHandler.END
    try:
        val = int((u.message.text or '').strip())
    except Exception:
        await u.message.reply_text("❌ Type a whole number from 0 to 40.")
        c.user_data['mb_screenpad_group'] = group_id
        return MB_SCREEN_PAD_VALUE
    from button_system import set_screen_pad
    val = set_screen_pad(group_id, val)
    await u.message.reply_text(
        f"✅ Screen padding set to *{val}* for *{GROUP_NAMES.get(group_id, group_id)}*.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"mbgrp_{group_id}")]])
    )
    return ConversationHandler.END


async def custom_button_color_callback(u, c):
    """🎨 v46: open color picker for a single custom button. cbcolor_<bid>"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    bid = q.data.replace("cbcolor_", "")
    from button_system import get_button_style
    cur = get_button_style(f"custom_{bid}") or "default"
    text = (f"🎨 *Custom Button Color*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"*Current:* `{cur}`\n\n"
            f"Pick a background color (🔵/🟢/🔴) or Default.\n\n"
            f"⭐ Needs bot owner Telegram Premium to show.")
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=custom_button_color_picker_keyboard(bid))


async def custom_button_set_color_callback(u, c):
    """🎨 v46: save custom button color. cbsetcol_<bid>_<style>"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    raw = q.data.replace("cbsetcol_", "")
    bid, _, style = raw.rpartition("_")
    from button_system import set_button_style
    save_style = "" if style == "none" else style
    old = get_setting(f"btn_style_custom_{bid}", "")
    log_change("setting", f"btn_style_custom_{bid}", old, save_style, f"Custom color: {bid}")
    set_button_style(f"custom_{bid}", save_style)
    nice = {"primary": "🔵 Blue", "success": "🟢 Green",
            "danger": "🔴 Red", "none": "⬜ Default"}.get(style, style)
    await q.answer(f"Color set: {nice} ✅")
    set_cb_data(u, f"cbview_{bid}")
    await cb_view_callback(u, c)


async def rename_button_callback(u, c):
    """✏️ Start rename conversation"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return ConversationHandler.END
    await q.answer()
    # data format: mbrenm_<btn_id>_<size>
    parts = q.data.replace("mbrenm_", "").rsplit("_", 1)
    if len(parts) != 2:
        await _safe_edit(q, "❌ Invalid request."); return ConversationHandler.END
    btn_id, size = parts
    if btn_id not in BTN_REGISTRY or size not in ("short", "medium", "large", "xl"):
        await _safe_edit(q, "❌ Invalid button/size."); return ConversationHandler.END

    btn = BTN_REGISTRY[btn_id]
    current = get_setting(f"btn_label_{btn_id}_{size}", "") or btn.get(size, "")

    c.user_data['mb_btn_id'] = btn_id
    c.user_data['mb_size'] = size
    # 🆕 v53: Render `current` premium-emoji aware so admin sees the actual
    # rendered button label (not raw [[HTML]]<tg-emoji> tags).
    from utils import smart_text_and_mode, is_html_value, contains_premium_markup
    if is_html_value(current) or contains_premium_markup(current):
        # Build HTML view (premium emoji renders)
        body_html, _ = smart_text_and_mode(current, "HTML")
        await _safe_edit(q,
            f"✏️ <b>Rename Button</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Button:</b> <code>{btn_id}</code>\n"
            f"<b>Size:</b> {size.upper()}\n\n"
            f"<b>Current:</b> {body_html}\n\n"
            f"📝 Type the new label:\n"
            f"(or type <code>-</code> to reset this size to default)\n\n"
            f"⭐ <b>Premium emoji supported!</b> Insert a Telegram premium "
            f"emoji from the picker and the bot will render it as the "
            f"button's <b>icon</b> automatically.\n\n"
            f"💡 <i>Tip: Use just 1 premium emoji per button — Telegram supports "
            f"only one icon per button.</i>",
            parse_mode="HTML", reply_markup=inline_cancel_btn())
    else:
        await _safe_edit(q,
            f"✏️ *Rename Button*\n━━━━━━━━━━━━━━━━━━━━\n"
            f"*Button:* `{btn_id}`\n"
            f"*Size:* {size.upper()}\n\n"
            f"*Current:* `{current}`\n\n"
            f"📝 Type the new label:\n"
            f"(or type `-` to reset this size to default)\n\n"
            f"⭐ *Premium emoji supported!* Insert a Telegram premium "
            f"emoji from the picker and the bot will render it as the "
            f"button's *icon* automatically.\n\n"
            f"💡 _Tip: Use just 1 premium emoji per button — Telegram supports "
            f"only one icon per button._",
            parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return MB_RENAME_VALUE


async def rename_button_value_received(u, c):
    """Save new button label"""
    if u.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    btn_id = c.user_data.get('mb_btn_id')
    size = c.user_data.get('mb_size')
    if not btn_id or not size:
        await u.message.reply_text("❌ Session lost.", reply_markup=back_btn())
        return ConversationHandler.END

    val = u.message.text.strip()
    setting_key = f"btn_label_{btn_id}_{size}"
    old_val = get_setting(setting_key, "")
    if val == "-":
        # Reset ALL sizes so the button cleanly returns to its defaults
        for _sz in ("short", "medium", "large", "xl"):
            _k = f"btn_label_{btn_id}_{_sz}"
            log_change("setting", _k, get_setting(_k, ""), "", f"Reset: {btn_id} {_sz}")
            set_setting(_k, "")
        await u.message.reply_text("♻️ Reset to default (all sizes) ✅", reply_markup=back_btn())
    else:
        if len(val) > 64:
            await u.message.reply_text("❌ Too long (max 64 chars). Try again or /cancel")
            return MB_RENAME_VALUE
        # 🆕 v45: Premium-emoji aware — save HTML form so button renderer can
        # extract icon_custom_emoji_id later.
        try:
            html_v = (u.message.text_html_urled or "").strip()
        except Exception:
            html_v = ""
        ce_list = [e for e in (u.message.entities or [])
                   if getattr(e, "type", "") == "custom_emoji"]
        has_ce = bool(ce_list)
        if html_v and has_ce:
            val_to_save = "[[HTML]]" + html_v
        else:
            val_to_save = val
        # 🆕 v53: Friendly warning if admin combined MULTIPLE premium emojis
        # in a single button. Telegram supports only ONE icon_custom_emoji_id
        # per button — only the first premium emoji becomes the button's icon,
        # the rest fall back to their standard emoji char in the label text.
        multi_premium_note = ""
        if len(ce_list) > 1:
            multi_premium_note = (
                f"\n\n⚠️ <i>You included {len(ce_list)} premium emojis. "
                f"Telegram allows only ONE premium emoji as a button icon — "
                f"the first one will render as a premium icon, the rest will "
                f"show as standard fallback chars. For best look, use just 1 "
                f"premium emoji per button.</i>"
            )
        # 🆕 Log for undo
        log_change("setting", setting_key, old_val, val_to_save, f"Rename: {btn_id} {size}")
        set_setting(setting_key, val_to_save)
        # 🔧 BUGFIX (rename should fully replace the name everywhere):
        # A registry button stores 4 labels (short/medium/large/xl) and the
        # menu shows whichever matches the global `button_size`. If only ONE
        # size is edited, the other sizes keep their old default — so the new
        # name "doesn't replace" depending on the size setting (and a premium
        # emoji could appear with the OLD text). We now apply the new label to
        # ALL sizes so the rename takes effect everywhere immediately.
        for _sz in ("short", "medium", "large", "xl"):
            if _sz == size:
                continue
            set_setting(f"btn_label_{btn_id}_{_sz}", val_to_save)
        applied_all = True
        emoji_note = ""
        if has_ce:
            emoji_note = "\n⭐ Premium emoji detected — will render as button icon."
        emoji_note += "\n📐 Applied to ALL sizes (small/medium/large/XL) — full name replaced everywhere."
        # 🆕 v53: render the saved label correctly (premium emojis VISIBLE).
        # Pass the message so safe_display can re-derive HTML from entities
        # when val itself is plain text (e.g. when admin typed premium emoji
        # whose fallback char is plain ascii).
        from utils import safe_display
        disp, disp_mode = safe_display(val, preferred_mode="Markdown", message=u.message)
        # 🚨 Critical: when echo is HTML, DO NOT wrap the value in <code> (backticks)
        # because Telegram does NOT render <tg-emoji> inside <code> blocks.
        if disp_mode == "HTML":
            from utils import _html as _html_lib
            note_html = _html_lib.escape(emoji_note)
            await u.message.reply_text(
                f"✅ <b>Renamed!</b>\n\n<b>New label:</b> {disp}\n{note_html}{multi_premium_note}",
                parse_mode="HTML", reply_markup=back_btn())
        else:
            await u.message.reply_text(
                f"✅ Renamed!\n\n*New label:* `{disp}`{emoji_note}",
                parse_mode="Markdown", reply_markup=back_btn())

    c.user_data.pop('mb_btn_id', None)
    c.user_data.pop('mb_size', None)
    return ConversationHandler.END


async def delivery_mode_callback(u, c):
    """Automation-only mode — manual delivery disabled."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    c.user_data['delivery_mode'] = 'auto'
    c.user_data['pph'] = ""
    await q.answer("Automation-only mode enabled ✅")
    await q.edit_message_text(
        "📨 *Auto Delivery Text*\n\n"
        "Send the delivery text that customers should receive automatically after payment verification.",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return PROD_DELIVERY_TEXT


async def noop_callback(u, c):
    """🔧 BUG #11 FIX: Generic no-op for non-actionable buttons
    Used for empty submenu indicators etc."""
    q = u.callback_query
    await q.answer()


async def locked_callback(u, c):
    """🔒 Locked essential button feedback"""
    q = u.callback_query
    await q.answer("🔒 This is essential — cannot hide", show_alert=True)


# ════════════════════════════════════════════
# ➕ CUSTOM BUTTONS (Phase B)
# ════════════════════════════════════════════
from database import (add_custom_button, get_custom_buttons, get_all_custom_buttons,
                      get_custom_button, update_custom_button, delete_custom_button)

# Conversation states for custom button creation/edit
CB_NEW_LABEL = 200
CB_NEW_ACTION = 201
CB_EDIT_VALUE = 202

# 🆕 v38: Extended location labels (13 locations)
LOC_LABELS = {
    "main":           "🏠 Main Menu",
    "admin":          "👑 Admin Panel",
    "settings":       "⚙️ Settings",
    "customization":  "🎨 Customization",
    "my_account":     "👤 My Account",
    "shop":           "🛍️ Shop",
    "my_orders":      "📦 My Orders",
    "support":        "🎫 Support",
    "warranty":       "🛡️ Warranty",
    "reviews":        "⭐ Reviews",
    "loyalty":        "🏆 Loyalty",
    "payment":        "💳 Payment",
    "product_detail": "📦 Product Detail",
    # 🔧 v39 Bug #9
    "transactions":   "📜 Transactions",
    "referral":       "🎁 Referral",
    "buy_points":     "💎 Buy Points",
}


def _loc_label(loc):
    """Pretty label for any location string"""
    if loc in LOC_LABELS:
        return LOC_LABELS[loc]
    if loc.startswith("sub_"):
        try:
            pid = int(loc.replace("sub_", ""))
            parent = get_custom_button(pid)
            if parent:
                return f"📂 Inside: {parent['label']}"
        except Exception:
            pass
        return f"📂 Submenu #{loc}"
    return loc


def _cb_admin_back_target(location):
    """Admin-side contextual Back target for custom-button screens."""
    loc = str(location or "")
    if loc.startswith("sub_"):
        return f"cbsubmgmt_{loc.replace('sub_', '', 1)}"
    if loc == "all" or not loc:
        return "admin_cbtns"
    return f"cblist_{loc}"


# ── Main entry ──
async def admin_cbtns_callback(u, c):
    """➕ Custom buttons main screen
    🔧 BUG #9 FIX: Clear any stale creation state when returning to main"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    # Clear any half-finished button creation state
    for k in ('cb_new_type', 'cb_new_label', 'cb_new_action',
              'cb_edit_bid', 'cb_edit_field', 'cb_edit_btype'):
        c.user_data.pop(k, None)
    total = len(get_all_custom_buttons())
    text = f"""➕ *Custom Buttons*
━━━━━━━━━━━━━━━━━━━━

Aap khud naye buttons bana sakte hain bot mein!

📊 Total: *{total}* custom button(s)

🎯 *3 Types:*
🔗 URL — Browser/Telegram link
📝 Text — Custom message dikhata hai
📂 Submenu — Opens more buttons

📍 *Locations:* Main, Admin, Settings, Customization, Inside other Submenus

Choose action:"""
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=cbtns_main_keyboard())


# ── List buttons by location ──
async def cb_list_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    loc = q.data.replace("cblist_", "")
    if loc == "all":
        buttons = get_all_custom_buttons()
        title = "📋 *All Custom Buttons*"
        current_loc = None
    else:
        buttons = get_custom_buttons(loc)
        title = f"📂 *Custom Buttons in {_loc_label(loc)}*"
        current_loc = loc
    text = f"""{title}
━━━━━━━━━━━━━━━━━━━━

Total: *{len(buttons)}*

Tap a button to manage it:"""
    back_target = _cb_admin_back_target(current_loc or 'all')
    if current_loc is None:
        back_target = 'admin_cbtns'
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=cbtns_list_keyboard(buttons, current_loc, back_callback=back_target))


# 🆕 v54: Wrapper for cblist_all that returns to admin_buttons (Customization → Buttons)
# instead of admin_cbtns, so navigation from the new Manage Buttons hub is consistent.
async def mblist_all_custom_callback(u, c):
    """Same as cblist_all but back button points to admin_buttons (the new hub)."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    buttons = get_all_custom_buttons()
    text = f"""📋 *All Custom Buttons*
━━━━━━━━━━━━━━━━━━━━

Total: *{len(buttons)}*

Tap a button to manage it.
_(Back goes to Manage Buttons hub)_"""
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=cbtns_list_keyboard(buttons, None, back_callback="admin_buttons"))


# ── View / edit one button ──
async def cb_view_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    bid = int(q.data.replace("cbview_", ""))
    b = get_custom_button(bid)
    if not b:
        await _safe_edit(q, "❌ Not found.", reply_markup=back_btn()); return
    from button_system import action_icon, action_label, get_nav_target
    type_icon = action_icon(b['btype'])
    type_lbl = action_label(b['btype'])
    # Pretty-print action value
    if b['btype'] == 'nav':
        tgt = get_nav_target(b['action'])
        action_preview = f"{tgt['icon']} {tgt['label']}" if tgt else b['action']
    elif b['btype'] in ('send_photo','send_video','send_document','send_audio'):
        action_preview = f"[file_id: {(b['action'] or '')[:20]}...]"
    elif b['btype'] == 'page':
        try:
            from database import get_custom_page
            p = get_custom_page(int(b['action']))
            action_preview = f"📄 {p['title']}" if p else f"Page #{b['action']}"
        except Exception:
            action_preview = b['action'] or "(none)"
    else:
        action_preview = b['action'][:100] + "..." if b['action'] and len(b['action']) > 100 else (b['action'] or "(none)")
    text = f"""{type_icon} *Custom Button*
━━━━━━━━━━━━━━━━━━━━

*Label:* {escape_md(b['label'])}
*Action Type:* {type_lbl}
*Location:* {_loc_label(b['location'])}
*Value:* `{escape_md(str(action_preview))}`
*Active:* {'✅' if b['is_active'] else '🚫'}

Choose what to do:"""
    back_callback = _cb_admin_back_target(b['location'])
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=cbtns_view_keyboard(bid, b['btype'], back_callback=back_callback))


# ── Delete ──
async def cb_delete_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    bid = int(q.data.replace("cbdel_", ""))
    # 🆕 Log for undo
    b = get_custom_button(bid)
    if b:
        log_change("custom_button_del", str(bid), b['label'], "", f"Deleted: {b['label']}")
    delete_custom_button(bid)
    await q.answer("🗑️ Deleted ✅")
    back_target = _cb_admin_back_target((dict(b) if b else {}).get('location', 'all'))
    set_cb_data(u, back_target)
    if back_target.startswith("cbsubmgmt_"):
        await cb_submenu_mgmt_callback(u, c)
    elif back_target.startswith("cblist_"):
        await cb_list_callback(u, c)
    else:
        await admin_cbtns_callback(u, c)


# ── Open submenu management ──
async def cb_submenu_mgmt_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    parent_id = int(q.data.replace("cbsubmgmt_", ""))
    parent = get_custom_button(parent_id)
    if not parent:
        await _safe_edit(q, "❌ Parent not found.", reply_markup=back_btn()); return
    location = f"sub_{parent_id}"
    children = get_custom_buttons(location)
    text = f"""📂 *Submenu: {escape_md(parent['label'])}*
━━━━━━━━━━━━━━━━━━━━

Buttons inside this submenu: *{len(children)}*

Tap a button to manage it, create deeper submenus, or customize styles/colors."""
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=cbtns_list_keyboard(children, location, back_callback=f"cbview_{parent_id}"))


# ── NEW BUTTON FLOW ──
async def cb_new_callback(u, c):
    """🆕 v38: Start new button creation — step 1: choose ACTION TYPE
    Now shows 17+ action types grouped by category."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    # 🧹 Clear any stale state
    for k in list(c.user_data.keys()):
        if k.startswith('cb_new') or k.startswith('cb_edit'):
            c.user_data.pop(k, None)

    text = """➕ *New Custom Button*
━━━━━━━━━━━━━━━━━━━━

*Step 1/4:* Select action (what happens on click?)

🎯 *17+ Actions Available!*

Categories:
• 📋 Basic (text, url, submenu, page)
• 🧭 Navigation (built-in screens, back)
• 🛒 Commerce (direct buy, buy points)
• 📞 Contact (WhatsApp, Email, etc.)
• 🔔 Interactive (alert, copy, share)
• 📸 Media (photo, video, document)
• ⚡ Advanced (mini app, command)"""
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=cbtns_action_picker_keyboard())


async def cb_type_callback(u, c):
    """🆕 v38: Action type selected — step 2: ask for label.
    Handles all 17+ action types (text, url, submenu, page, nav, buy_product,
    whatsapp, email, alert, copy, share_bot, send_photo, webapp, etc.)"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return ConversationHandler.END
    await q.answer()
    btype = q.data.replace("cbtype_", "")
    from button_system import get_action
    action = get_action(btype)
    if not action:
        await q.answer(f"❌ Invalid action: {btype}", show_alert=True)
        return ConversationHandler.END
    c.user_data['cb_new_type'] = btype
    await _safe_edit(q,
        f"➕ *New {action['icon']} {action['label']} Button*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"_{action['description']}_\n\n"
        f"*Step 2/4:* Button ka *label* likhein (text + emoji):\n\n"
        f"Example: `🌟 Premium` ya `📋 Rules`\n\nMax 64 characters",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return CB_NEW_LABEL


async def cb_new_label_received(u, c):
    """🆕 v38: Label received — step 3 depends on action type.
    Some actions need no value (submenu, share_bot) → skip to location.
    Some need a picker (nav, page) → show picker.
    Some need text/url/file → ask user.
    Some need a file upload (send_photo etc.) → ask for upload."""
    if u.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    label = u.message.text.strip()
    if len(label) > 64:
        await u.message.reply_text("❌ Too long (max 64). Try again or /cancel")
        return CB_NEW_LABEL
    # 🆕 v45: Premium-emoji aware label — save HTML form if custom emoji present
    try:
        html_v = (u.message.text_html_urled or "").strip()
    except Exception:
        html_v = ""
    has_ce = any(getattr(e, "type", "") == "custom_emoji"
                 for e in (u.message.entities or []))
    if html_v and has_ce:
        c.user_data['cb_new_label'] = "[[HTML]]" + html_v
        await u.message.reply_text(
            "⭐ Premium emoji detected — it'll show as the button icon!"
        )
    else:
        c.user_data['cb_new_label'] = label
    btype = c.user_data.get('cb_new_type')
    from button_system import get_action
    action = get_action(btype)
    if not action:
        await u.message.reply_text("❌ Session error. /cancel")
        return ConversationHandler.END

    # ── 1. No value needed → straight to location ──
    if not action["needs_value"]:
        c.user_data['cb_new_action'] = ""
        await u.message.reply_text(
            f"✅ Label: *{escape_md(label)}*\n\n"
            "*Step 4/4:* Yeh button kahan show ho?",
            parse_mode="Markdown",
            reply_markup=cbtns_location_v2_keyboard(allow_submenus=(btype != "submenu"))
        )
        return ConversationHandler.END

    # ── 2. Special pickers ──
    if btype == "nav":
        await u.message.reply_text(
            f"✅ Label: *{escape_md(label)}*\n\n"
            f"*Step 3/4:* Kis screen pe le jaye?",
            parse_mode="Markdown",
            reply_markup=cbtns_nav_target_keyboard()
        )
        return ConversationHandler.END  # nav callback handles next step

    if btype == "page":
        # Use existing page picker
        from database import get_all_custom_pages
        pages = get_all_custom_pages()
        await u.message.reply_text(
            f"✅ Label: *{escape_md(label)}*\n\n"
            f"*Step 3/4:* Page chunein:",
            parse_mode="Markdown",
            reply_markup=cpages_picker_keyboard(pages, back_to="admin_cbtns")
        )
        return ConversationHandler.END  # cppick_ callback handles next step

    # ── 3. File-upload actions ──
    if btype in ("send_photo", "send_video", "send_document", "send_audio"):
        await u.message.reply_text(
            f"✅ Label: *{escape_md(label)}*\n\n"
            f"*Step 3/4:* Now *upload* the {action['icon']} {action['label']}:\n\n"
            f"_(Send the file as photo/video/document/audio attachment)_",
            parse_mode="Markdown", reply_markup=inline_cancel_btn()
        )
        return CB_NEW_ACTION  # next step will handle file upload

    # ── 4. Text/value actions ──
    await u.message.reply_text(
        f"✅ Label: *{escape_md(label)}*\n\n"
        f"*Step 3/4:* {action['icon']} *{action['label']}*\n\n"
        f"📥 {action['value_hint']}",
        parse_mode="Markdown", reply_markup=inline_cancel_btn()
    )
    return CB_NEW_ACTION


async def cb_new_action_received(u, c):
    """🆕 v38: Action value received — validates per action type, then asks for location.
    Also handles file uploads for send_photo/video/document/audio."""
    if u.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    btype = c.user_data.get('cb_new_type')
    from button_system import get_action
    action_def = get_action(btype)
    if not action_def:
        await u.message.reply_text("❌ Session error. /cancel")
        return ConversationHandler.END

    # ── Handle file uploads ──
    value = None
    msg = u.message
    if btype == "send_photo":
        if msg.photo:
            value = msg.photo[-1].file_id
        else:
            await msg.reply_text("❌ Please send a *photo* (not text). Try again or /cancel",
                                  parse_mode="Markdown")
            return CB_NEW_ACTION
    elif btype == "send_video":
        if msg.video:
            value = msg.video.file_id
        elif msg.document and (msg.document.mime_type or "").startswith("video/"):
            value = msg.document.file_id
        else:
            await msg.reply_text("❌ Please send a *video*. Try again or /cancel",
                                  parse_mode="Markdown")
            return CB_NEW_ACTION
    elif btype == "send_document":
        if msg.document:
            value = msg.document.file_id
        else:
            await msg.reply_text("❌ Please send a *document/file*. Try again or /cancel",
                                  parse_mode="Markdown")
            return CB_NEW_ACTION
    elif btype == "send_audio":
        if msg.audio:
            value = msg.audio.file_id
        elif msg.voice:
            value = msg.voice.file_id
        else:
            await msg.reply_text("❌ Please send *audio/voice*. Try again or /cancel",
                                  parse_mode="Markdown")
            return CB_NEW_ACTION
    else:
        # Text-based value
        value = (msg.text or "").strip()
        # Validate
        ok, err = action_def["validator"](value)
        if not ok:
            await msg.reply_text(f"❌ {err}. Try again or /cancel", parse_mode="Markdown")
            return CB_NEW_ACTION

    c.user_data['cb_new_action'] = value
    await msg.reply_text(
        "✅ Action saved!\n\n"
        "*Step 4/4:* Yeh button kahan show ho?",
        parse_mode="Markdown",
        reply_markup=cbtns_location_v2_keyboard(allow_submenus=(btype != "submenu"))
    )
    return ConversationHandler.END  # location handled by callback


async def cb_location_callback(u, c):
    """Location selected — save the button"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    # data format: cbloc_<location>  OR  cbloc_sub_<id>
    raw = q.data.replace("cbloc_", "")
    location = raw  # could be 'main' or 'sub_5'
    label = c.user_data.get('cb_new_label')
    btype = c.user_data.get('cb_new_type')
    action = c.user_data.get('cb_new_action', '')

    if not label or not btype:
        # Could be an EDIT location flow
        edit_bid = c.user_data.get('cb_edit_bid')
        if edit_bid:
            update_custom_button(edit_bid, location=location)
            c.user_data.pop('cb_edit_bid', None)
            await q.answer("✅ Location updated")
            set_cb_data(u, f"cbview_{edit_bid}")
            await cb_view_callback(u, c)
            return
        await _safe_edit(q, "❌ Session lost. /start"); return

    bid = add_custom_button(label, btype, action, location)
    # 🆕 Log for undo
    log_change("custom_button_add", str(bid), "", label, f"Added button: {label}")
    # Clear flow data
    for k in ('cb_new_label', 'cb_new_type', 'cb_new_action'):
        c.user_data.pop(k, None)

    from button_system import action_icon, action_label
    type_icon = action_icon(btype)
    type_label = action_label(btype)
    await _safe_edit(q,
        f"✅ *Custom Button Created!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{type_icon} *Label:* {escape_md(label)}\n"
        f"🎯 *Action:* {type_label}\n"
        f"📍 *Location:* {_loc_label(location)}\n\n"
        f"_Go to that screen and you'll see it!_",
        parse_mode="Markdown",
        reply_markup=cbtns_main_keyboard())


# ── EDIT existing button ──
async def cb_edit_label_callback(u, c):
    """Start label edit"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return ConversationHandler.END
    await q.answer()
    bid = int(q.data.replace("cbedit_label_", ""))
    b = get_custom_button(bid)
    if not b:
        await _safe_edit(q, "❌ Not found."); return ConversationHandler.END
    c.user_data['cb_edit_bid'] = bid
    c.user_data['cb_edit_field'] = 'label'
    await _safe_edit(q,
        f"✏️ *Rename Label*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Current:* `{escape_md(b['label'])}`\n\n"
        f"Type new label (max 64 chars):",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return CB_EDIT_VALUE


async def cb_edit_action_callback(u, c):
    """🆕 v38: Start editing the action value for any action type."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return ConversationHandler.END
    await q.answer()
    bid = int(q.data.replace("cbedit_action_", ""))
    b = get_custom_button(bid)
    if not b:
        await _safe_edit(q, "❌ Not found."); return ConversationHandler.END

    from button_system import get_action
    action_def = get_action(b['btype'])
    if not action_def:
        await q.answer("❌ Unknown action type", show_alert=True)
        return ConversationHandler.END

    # ── Special: nav uses picker ──
    if b['btype'] == 'nav':
        c.user_data['cb_edit_bid'] = bid
        c.user_data['cb_edit_field'] = 'nav_target'
        await _safe_edit(q,
            f"🧭 *Change Navigation Target*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Current: `{b['action']}`\n\nPick a new target:",
            parse_mode="Markdown",
            reply_markup=cbtns_nav_target_keyboard())
        return ConversationHandler.END

    # ── Special: page uses picker ──
    if b['btype'] == 'page':
        from database import get_all_custom_pages
        c.user_data['cb_edit_bid'] = bid
        c.user_data['cb_edit_field'] = 'page_id'
        await _safe_edit(q,
            "📄 *Change Page*\n━━━━━━━━━━━━━━━━━━━━\n\nPick a new page:",
            parse_mode="Markdown",
            reply_markup=cpages_picker_keyboard(get_all_custom_pages(), back_to=f"cbview_{bid}"))
        return ConversationHandler.END

    c.user_data['cb_edit_bid'] = bid
    c.user_data['cb_edit_field'] = 'action'
    c.user_data['cb_edit_btype'] = b['btype']

    is_file = b['btype'] in ('send_photo','send_video','send_document','send_audio')
    current_preview = "(file)" if is_file else (
        b['action'][:200] + "..." if b['action'] and len(b['action']) > 200 else (b['action'] or "(empty)")
    )
    prompt = "Upload new file:" if is_file else "Type new value:"
    await _safe_edit(q,
        f"✏️ *Edit {action_def['icon']} {action_def['label']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Current:* `{escape_md(str(current_preview))}`\n\n"
        f"📥 {action_def['value_hint']}\n\n{prompt}",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return CB_EDIT_VALUE


async def cb_edit_value_received(u, c):
    """🆕 v38: Save edited value — handles all action types incl. file uploads."""
    if u.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    bid = c.user_data.get('cb_edit_bid')
    field = c.user_data.get('cb_edit_field')
    if not bid or not field:
        await u.message.reply_text("❌ Session lost.", reply_markup=back_btn())
        return ConversationHandler.END

    if field == 'label':
        val = (u.message.text or "").strip()
        if len(val) > 64:
            await u.message.reply_text("❌ Too long (max 64). Try again or /cancel")
            return CB_EDIT_VALUE
        # 🆕 v45: Premium-emoji aware — save HTML form if admin sent custom emoji
        try:
            html_v = (u.message.text_html_urled or "").strip()
        except Exception:
            html_v = ""
        has_ce = any(getattr(e, "type", "") == "custom_emoji"
                     for e in (u.message.entities or []))
        if html_v and has_ce:
            val_to_save = "[[HTML]]" + html_v
        else:
            val_to_save = val
        update_custom_button(bid, label=val_to_save)
        if has_ce:
            await u.message.reply_text(
                "⭐ *Premium emoji detected* — will render as button icon.",
                parse_mode="Markdown"
            )
    elif field == 'action':
        btype = c.user_data.get('cb_edit_btype')
        from button_system import get_action
        action_def = get_action(btype)

        # File uploads
        msg = u.message
        value = None
        if btype == "send_photo":
            if msg.photo: value = msg.photo[-1].file_id
            else:
                await msg.reply_text("❌ Send a photo. Try again or /cancel"); return CB_EDIT_VALUE
        elif btype == "send_video":
            if msg.video: value = msg.video.file_id
            elif msg.document and (msg.document.mime_type or "").startswith("video/"):
                value = msg.document.file_id
            else:
                await msg.reply_text("❌ Send a video. Try again or /cancel"); return CB_EDIT_VALUE
        elif btype == "send_document":
            if msg.document: value = msg.document.file_id
            else:
                await msg.reply_text("❌ Send a document. Try again or /cancel"); return CB_EDIT_VALUE
        elif btype == "send_audio":
            if msg.audio: value = msg.audio.file_id
            elif msg.voice: value = msg.voice.file_id
            else:
                await msg.reply_text("❌ Send audio/voice. Try again or /cancel"); return CB_EDIT_VALUE
        else:
            value = (msg.text or "").strip()
            if action_def:
                ok, err = action_def["validator"](value)
                if not ok:
                    await msg.reply_text(f"❌ {err}. Try again or /cancel")
                    return CB_EDIT_VALUE

        update_custom_button(bid, action=value)

    await u.message.reply_text("✅ Updated!", reply_markup=back_btn())
    for k in ('cb_edit_bid', 'cb_edit_field', 'cb_edit_btype'):
        c.user_data.pop(k, None)
    return ConversationHandler.END


async def cb_edit_location_callback(u, c):
    """Change location of existing button"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    bid = int(q.data.replace("cbedit_location_", ""))
    b = get_custom_button(bid)
    if not b:
        await _safe_edit(q, "❌ Not found."); return
    c.user_data['cb_edit_bid'] = bid
    allow_subs = (b['btype'] != 'submenu')
    await _safe_edit(q,
        f"📍 *Change Location*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Current:* {_loc_label(b['location'])}\n\n"
        f"Select new location:",
        parse_mode="Markdown",
        reply_markup=cbtns_location_v2_keyboard(
            allow_submenus=allow_subs,
            exclude_sub_of=bid,
            cancel_callback=f"cbview_{bid}"
        ))


async def cb_style_callback(u, c):
    """Open inline-button styler directly for a custom button from its manage screen."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    bid = int(q.data.replace("cbstyle_", ""))
    c.user_data['bs_return'] = f"cbview_{bid}"
    set_cb_data(u, f"bs_edit_custom_{bid}")
    from handlers_buttons import bs_edit_callback
    await bs_edit_callback(u, c)


# ── User-side: Text button clicked ──
async def cbtn_text_callback(u, c):
    """User clicked a Text-type custom button — show its message"""
    q = u.callback_query
    await q.answer()
    bid = int(q.data.replace("cbtn_", ""))
    b = get_custom_button(bid)
    if not b or b['btype'] != 'text' or not b['is_active']:
        await _safe_edit(q, "❌ Not available.", reply_markup=back_btn())
        return
    parent_cb = location_back_callback((dict(b) if b else {}).get('location', 'main'))
    text = b['action'] or "(no message set)"
    try:
        await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=parent_cb)]]))
    except Exception:
        # Markdown error — send as plain
        try:
            await _safe_edit(q, text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=parent_cb)]]))
        except Exception:
            await c.bot.send_message(q.from_user.id, text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=parent_cb)]]))


# ── User-side: Submenu button clicked ──
async def cbsub_open_callback(u, c):
    """User clicked a Submenu-type button — show its children"""
    q = u.callback_query
    await q.answer()
    bid = int(q.data.replace("cbsub_", ""))
    b = get_custom_button(bid)
    if not b or b['btype'] != 'submenu' or not b['is_active']:
        await _safe_edit(q, "❌ Not available.", reply_markup=back_btn())
        return
    text = f"📂 *{escape_md(b['label'])}*\n━━━━━━━━━━━━━━━━━━━━\n\nSelect an option:"
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=custom_submenu_keyboard(bid))


# ════════════════════════════════════════════
# 🔄 REORDER BUTTONS (Phase C)
# ════════════════════════════════════════════
from button_system import move_button_up as _mvu, move_button_down as _mvd
from database import move_custom_button_up, move_custom_button_down


async def move_system_btn_up_callback(u, c):
    """⬆️ Move system button up"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    btn_id = q.data.replace("mbup_", "")
    ok = _mvu(btn_id)
    if ok:
        await q.answer("⬆️ Moved up")
    else:
        await q.answer("Already at top", show_alert=False)
    # 🆕 v54: refresh via render helper (no double answer)
    from button_system import BUTTONS
    grp = BUTTONS.get(btn_id, {}).get("group", "main")
    await _render_manage_group(q, grp)


async def move_system_btn_down_callback(u, c):
    """⬇️ Move system button down"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    btn_id = q.data.replace("mbdn_", "")
    ok = _mvd(btn_id)
    if ok:
        await q.answer("⬇️ Moved down")
    else:
        await q.answer("Already at bottom", show_alert=False)
    # 🆕 v54: refresh via render helper (no double answer)
    from button_system import BUTTONS
    grp = BUTTONS.get(btn_id, {}).get("group", "main")
    await _render_manage_group(q, grp)


async def move_custom_btn_up_callback(u, c):
    """⬆️ Move custom button up"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    bid = int(q.data.replace("cbup_", ""))
    b = get_custom_button(bid)
    if not b:
        await q.answer("Not found", show_alert=True); return
    ok = move_custom_button_up(bid)
    if ok:
        await q.answer("⬆️ Moved up")
    else:
        await q.answer("Already at top", show_alert=False)
    # Refresh list of the same location
    set_cb_data(u, f"cblist_{b['location']}")
    await cb_list_callback(u, c)


async def move_custom_btn_down_callback(u, c):
    """⬇️ Move custom button down"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    bid = int(q.data.replace("cbdn_", ""))
    b = get_custom_button(bid)
    if not b:
        await q.answer("Not found", show_alert=True); return
    ok = move_custom_button_down(bid)
    if ok:
        await q.answer("⬇️ Moved down")
    else:
        await q.answer("Already at bottom", show_alert=False)
    set_cb_data(u, f"cblist_{b['location']}")
    await cb_list_callback(u, c)


# ════════════════════════════════════════════
# 📄 CUSTOM PAGES (Phase D)
# ════════════════════════════════════════════
from database import (add_custom_page, get_custom_page, get_all_custom_pages,
                      update_custom_page, delete_custom_page)

# Conversation states for pages
CP_NEW_TITLE = 300
CP_NEW_CONTENT = 301
CP_NEW_PHOTO = 302
CP_EDIT_VALUE = 303
CP_EDIT_PHOTO = 304


async def admin_cpages_callback(u, c):
    """📄 Custom pages main screen"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pages = get_all_custom_pages()
    text = f"""📄 *Custom Pages*
━━━━━━━━━━━━━━━━━━━━

Rich pages with text + image. Use them via
Custom Buttons (type: 📄 Page).

📊 Total: *{len(pages)}* page(s)

Tap a page to manage:"""
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=cpages_main_keyboard(pages))


async def cp_view_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = int(q.data.replace("cpview_", ""))
    p = get_custom_page(pid)
    if not p:
        await _safe_edit(q, "❌ Not found.", reply_markup=back_btn()); return
    preview = (p['content'] or "(empty)")[:300]
    if len(p['content'] or "") > 300:
        preview += "..."
    photo_status = "✅ Yes" if p['photo_id'] else "❌ No"
    text = f"""📄 *Page: {escape_md(p['title'])}*
━━━━━━━━━━━━━━━━━━━━

*Photo:* {photo_status}

*Content Preview:*
```
{preview}
```

Choose action:"""
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=cpages_view_keyboard(pid))


async def cp_delete_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    pid = int(q.data.replace("cpdel_", ""))
    delete_custom_page(pid)
    await q.answer("🗑️ Page deleted ✅")
    set_cb_data(u, "admin_cpages")
    await admin_cpages_callback(u, c)


async def cp_rmphoto_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    pid = int(q.data.replace("cprmphoto_", ""))
    update_custom_page(pid, photo_id="")
    await q.answer("📸 Photo removed")
    set_cb_data(u, f"cpview_{pid}")
    await cp_view_callback(u, c)


# ── NEW PAGE FLOW ──
async def cp_new_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return ConversationHandler.END
    await q.answer()
    await _safe_edit(q,
        "➕ *New Custom Page*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Step 1/3:* Page ka *title* likhein:\n\n"
        "Example: `📋 Rules`, `🤔 FAQ`, `📜 Privacy Policy`\n\n"
        "Max 64 chars",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return CP_NEW_TITLE


async def cp_new_title_received(u, c):
    if u.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    title = u.message.text.strip()
    if len(title) > 64:
        await u.message.reply_text("❌ Too long (max 64). Try again or /cancel")
        return CP_NEW_TITLE
    try:
        html_v = (u.message.text_html_urled or "").strip()
    except Exception:
        html_v = ""
    c.user_data['cp_title'] = ("[[HTML]]" + html_v) if (html_v and has_premium_emoji(u.message)) else title
    await u.message.reply_text(
        f"✅ Title: *{escape_md(title)}*\n\n"
        f"*Step 2/3:* Send page *content* (text):\n\n"
        f"Markdown supported: *bold*, _italic_, `code`\n"
        f"Max 4000 chars",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return CP_NEW_CONTENT


async def cp_new_content_received(u, c):
    if u.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    content = u.message.text.strip()
    if len(content) > 4000:
        await u.message.reply_text("❌ Too long (max 4000). Try again or /cancel")
        return CP_NEW_CONTENT
    try:
        html_v = (u.message.text_html_urled or "").strip()
    except Exception:
        html_v = ""
    c.user_data['cp_content'] = ("[[HTML]]" + html_v) if (html_v and has_premium_emoji(u.message)) else content
    await u.message.reply_text(
        "✅ Content saved!\n\n"
        "*Step 3/3:* Send a photo for the page (optional):\n\n"
        "📸 Send an image OR type `-` to skip",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return CP_NEW_PHOTO


async def cp_new_photo_received(u, c):
    """🔧 BUG #7 FIX: Properly reject non-image documents"""
    if u.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    photo_id = ""
    if u.message.photo:
        photo_id = u.message.photo[-1].file_id
    elif u.message.document:
        mt = u.message.document.mime_type or ""
        if mt.startswith('image/'):
            photo_id = u.message.document.file_id
        else:
            await u.message.reply_text(
                f"❌ *That's not an image!*\n\n"
                f"You sent: `{u.message.document.file_name or 'unknown'}` (type: `{mt or 'unknown'}`)\n\n"
                f"Please send a *photo* OR type `-` to skip",
                parse_mode="Markdown", reply_markup=inline_cancel_btn())
            return CP_NEW_PHOTO
    elif u.message.text and u.message.text.strip() == "-":
        photo_id = ""
    else:
        await u.message.reply_text(
            "❌ Send an *image* OR type `-` to skip",
            parse_mode="Markdown", reply_markup=inline_cancel_btn())
        return CP_NEW_PHOTO

    title = c.user_data.get('cp_title', '?')
    content = c.user_data.get('cp_content', '')
    add_custom_page(title, content, photo_id)
    photo_mark = " 📸" if photo_id else ""
    await u.message.reply_text(
        f"✅ *Page Created!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📄 *{escape_md(title)}*{photo_mark}\n\n"
        f"To use this page, create a Custom Button (type 📄 Page) and link it.",
        parse_mode="Markdown", reply_markup=back_btn())
    for k in ('cp_title', 'cp_content'): c.user_data.pop(k, None)
    return ConversationHandler.END


# ── EDIT EXISTING PAGE ──
async def cp_edit_title_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return ConversationHandler.END
    await q.answer()
    pid = int(q.data.replace("cpedit_title_", ""))
    p = get_custom_page(pid)
    if not p: return ConversationHandler.END
    c.user_data['cp_edit_pid'] = pid
    c.user_data['cp_edit_field'] = 'title'
    await _safe_edit(q,
        f"✏️ *Edit Title*\n\n*Current:* `{escape_md(p['title'])}`\n\n"
        f"Type new title (max 64):",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return CP_EDIT_VALUE


async def cp_edit_content_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return ConversationHandler.END
    await q.answer()
    pid = int(q.data.replace("cpedit_content_", ""))
    p = get_custom_page(pid)
    if not p: return ConversationHandler.END
    c.user_data['cp_edit_pid'] = pid
    c.user_data['cp_edit_field'] = 'content'
    preview = (p['content'] or "(empty)")[:200]
    await _safe_edit(q,
        f"📝 *Edit Content*\n\n*Current preview:*\n```\n{preview}\n```\n\n"
        f"Type new content (max 4000):",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return CP_EDIT_VALUE


async def cp_edit_value_received(u, c):
    if u.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    pid = c.user_data.get('cp_edit_pid')
    field = c.user_data.get('cp_edit_field')
    if not pid or not field:
        await u.message.reply_text("❌ Session lost.", reply_markup=back_btn())
        return ConversationHandler.END
    val = u.message.text.strip()
    if field == 'title':
        if len(val) > 64:
            await u.message.reply_text("❌ Too long. Try again or /cancel")
            return CP_EDIT_VALUE
        try:
            html_v = (u.message.text_html_urled or "").strip()
        except Exception:
            html_v = ""
        if html_v and has_premium_emoji(u.message):
            val = "[[HTML]]" + html_v
        update_custom_page(pid, title=val)
    elif field == 'content':
        if len(val) > 4000:
            await u.message.reply_text("❌ Too long (max 4000). Try again or /cancel")
            return CP_EDIT_VALUE
        try:
            html_v = (u.message.text_html_urled or "").strip()
        except Exception:
            html_v = ""
        if html_v and has_premium_emoji(u.message):
            val = "[[HTML]]" + html_v
        update_custom_page(pid, content=val)
    await u.message.reply_text("✅ Updated!", reply_markup=back_btn())
    for k in ('cp_edit_pid', 'cp_edit_field'): c.user_data.pop(k, None)
    return ConversationHandler.END


async def cp_edit_photo_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return ConversationHandler.END
    await q.answer()
    pid = int(q.data.replace("cpedit_photo_", ""))
    c.user_data['cp_edit_pid'] = pid
    await _safe_edit(q,
        "📸 *Change Page Photo*\n\nSend a new photo:\n"
        "(or type `-` to remove)",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return CP_EDIT_PHOTO


async def cp_edit_photo_received(u, c):
    if u.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    pid = c.user_data.get('cp_edit_pid')
    if not pid:
        await u.message.reply_text("❌", reply_markup=back_btn())
        return ConversationHandler.END
    photo_id = None
    if u.message.photo:
        photo_id = u.message.photo[-1].file_id
    elif u.message.document:
        mt = u.message.document.mime_type or ""
        if mt.startswith('image/'):
            photo_id = u.message.document.file_id
        else:
            # 🔧 BUG #7 FIX: Reject non-image with clear message
            await u.message.reply_text(
                f"❌ *That's not an image!*\n\n"
                f"You sent: `{u.message.document.file_name or 'unknown'}` (type: `{mt or 'unknown'}`)\n\n"
                f"Please send a *photo* OR type `-` to remove",
                parse_mode="Markdown", reply_markup=inline_cancel_btn())
            return CP_EDIT_PHOTO
    elif u.message.text and u.message.text.strip() == "-":
        photo_id = ""
    else:
        await u.message.reply_text("❌ Send a *photo* or `-` to remove",
                                   parse_mode="Markdown", reply_markup=inline_cancel_btn())
        return CP_EDIT_PHOTO
    update_custom_page(pid, photo_id=photo_id)
    msg = "📸 Photo updated!" if photo_id else "🗑️ Photo removed!"
    await u.message.reply_text("✅ " + msg, reply_markup=back_btn())
    c.user_data.pop('cp_edit_pid', None)
    return ConversationHandler.END


# ── Preview (Admin sees what user would see) ──
async def cp_preview_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("👁️ Preview...")
    pid = int(q.data.replace("cppreview_", ""))
    await _show_page_to_user(u, c, pid, parent="admin_cpages")


# ── USER-SIDE: Show a page ──
async def cbpage_open_callback(u, c):
    """User tapped a Page-type custom button
    🔧 BUG #3 FIX: Track parent location so Back returns to correct screen"""
    q = u.callback_query
    await q.answer()
    bid = int(q.data.replace("cbpage_", ""))
    from database import get_custom_button
    btn = get_custom_button(bid)
    if not btn or btn['btype'] != 'page' or not btn['action']:
        await _safe_edit(q, "❌ Page link broken.", reply_markup=back_btn())
        return
    try:
        page_id = int(btn['action'])
    except ValueError:
        await _safe_edit(q, "❌ Invalid page link.", reply_markup=back_btn())
        return

    # 🔧 Determine where to go back based on button's location
    loc = btn['location']
    if loc == "admin":
        parent = "admin_panel"
    elif loc == "settings":
        parent = "admin_settings"
    elif loc == "customization":
        parent = "admin_customization"
    elif loc.startswith("sub_"):
        # Inside a submenu — back to that submenu
        parent_sub_id = loc.replace("sub_", "")
        parent = f"cbsub_{parent_sub_id}"
    else:
        parent = "main_menu"

    await _show_page_to_user(u, c, page_id, parent=parent)


async def _show_page_to_user(u, c, page_id, parent="main_menu"):
    """Render a custom page nicely (with photo if exists)"""
    q = u.callback_query
    p = get_custom_page(page_id)
    if not p:
        await _safe_edit(q, "❌ Page not available.", reply_markup=back_btn())
        return
    title_text = p['title'] if p['title'] else 'Page'
    raw_text = f"📄 *{title_text}*\n━━━━━━━━━━━━━━━━━━━━\n\n{p['content'] or '(empty)'}"
    text, parse_mode = smart_text_and_mode(raw_text, "Markdown")
    kb = cpage_user_view_keyboard(page_id, parent=parent)
    photo_id = p['photo_id']

    if photo_id:
        try:
            await q.message.delete()
            await c.bot.send_photo(q.from_user.id, photo_id,
                                   caption=text, parse_mode=parse_mode,
                                   reply_markup=kb)
            return
        except Exception:
            pass
    # Text only fallback
    try:
        await _safe_edit(q, text, parse_mode=parse_mode, reply_markup=kb)
    except Exception:
        try:
            await _safe_edit(q, text, reply_markup=kb)
        except Exception:
            await c.bot.send_message(q.from_user.id, text, reply_markup=kb)


# ── PAGE PICKER (when creating Custom Button of type 'page') ──
async def cppick_callback(u, c):
    """When admin picks which page to link to a new 'page' button"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    page_id = int(q.data.replace("cppick_", ""))
    # Store action as the page id (string)
    c.user_data['cb_new_action'] = str(page_id)
    label = c.user_data.get('cb_new_label', '?')
    await _safe_edit(q,
        f"✅ Page linked!\n\n"
        f"*Label:* {escape_md(label)}\n\n"
        "*Step 4/4:* Yeh button kahan show ho?",
        parse_mode="Markdown",
        reply_markup=cbtns_location_v2_keyboard(allow_submenus=True))


# ════════════════════════════════════════════
# 🛒 SHOP CATEGORIZED MODE TOGGLE (Phase D)
# ════════════════════════════════════════════

async def toggle_shop_categorized_callback(u, c):
    """Toggle shop_categorized setting"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    current = get_setting("shop_categorized", "0")
    new = "0" if current == "1" else "1"
    set_setting("shop_categorized", new)
    await q.answer(f"{'Enabled' if new=='1' else 'Disabled'} ✅")
    # Refresh by re-calling toggles screen
    set_cb_data(u, "admin_toggles")
    await admin_toggles_callback(u, c)


# ════════════════════════════════════════════
# ❌ UNIVERSAL CONVERSATION CANCEL (inline button)
# ════════════════════════════════════════════
async def conv_cancel_callback(u, c):
    """Inline ❌ Cancel button — ends any active conversation,
    clears state, returns to main menu.

    🆕 v81.1 FIX: Now WIPES ALL user_data + forcibly ENDs every
    ConversationHandler for this user (previously only cleared a hardcoded
    list of keys, but the conv handler itself stayed in its state so the
    next text message still routed to the "add category/product" flow).
    """
    from telegram.ext import ConversationHandler
    q = u.callback_query
    await q.answer("Cancelled ✅")

    # 🆕 v81.1: WIPE all user_data except safe keys (matches force_main_menu)
    _SAFE_KEYS = {"language", "nav_stack"}
    try:
        ud = c.user_data
        if ud is not None:
            for k in list(ud.keys()):
                if k not in _SAFE_KEYS:
                    ud.pop(k, None)
    except Exception:
        pass

    # 🆕 v81.1: FORCIBLY end every active ConversationHandler for this user
    try:
        chat_id = u.effective_chat.id if u.effective_chat else 0
        user_id = u.effective_user.id if u.effective_user else 0
        app = c.application if hasattr(c, "application") else None
        if app is not None and (chat_id or user_id):
            for group, handlers in list(app.handlers.items()):
                for h in handlers:
                    if not isinstance(h, ConversationHandler):
                        continue
                    conv_map = getattr(h, "_conversations", None)
                    if conv_map is None:
                        continue
                    for key in list(conv_map.keys()):
                        if isinstance(key, tuple) and (
                            (chat_id and chat_id in key) or (user_id and user_id in key)
                        ):
                            conv_map.pop(key, None)
    except Exception as _e:
        import logging as _l
        _l.getLogger(__name__).debug(f"[conv_cancel] end-conv err: {_e}")

    # 🐛 v95 FIX (Bug 1): Return to the ORIGINAL screen the admin was on,
    # not always Main Menu. Previously ❌ Cancel would jump admin from deep
    # inside customization (rename button flow) back to Main Menu, forcing
    # them to navigate all the way back. Now we detect context.
    _return_hint = None
    try:
        # Check user_data breadcrumb (some flows save 'return_to')
        _return_hint = (c.user_data or {}).get("return_to")
    except Exception:
        pass
    if not _return_hint:
        # Infer from what conversation keys were set — they hint at context
        try:
            ud_keys = set((c.user_data or {}).keys())
            if any(k.startswith("mb_") or k in ("mb_btn_id", "mb_size") for k in ud_keys):
                _return_hint = "admin_buttons"      # was inside button editor
            elif any(k.startswith("cb_") for k in ud_keys):
                _return_hint = "admin_buttons"      # was adding custom button
            elif any(k.startswith("lc_") for k in ud_keys):
                _return_hint = "lc_panel"           # was in location customizer
            elif any(k.startswith("cp_") for k in ud_keys):
                _return_hint = "admin_pages"        # was creating custom page
            elif any(k.startswith("tpl_") or k.startswith("sb_") for k in ud_keys):
                _return_hint = "tpl_panel"          # was editing templates
            elif any(k.startswith("fj_") for k in ud_keys):
                _return_hint = "fj_panel"           # force-join
        except Exception:
            pass

    # Map hint → callback that opens that screen (nothing = main menu)
    _RETURN_MAP = {
        "admin_buttons":       ("🎛 Back to Manage Buttons", "admin_buttons"),
        "admin_customization": ("🎨 Back to Customization", "admin_customization"),
        "admin_settings":      ("⚙️ Back to Settings", "admin_settings"),
        "lc_panel":            ("📍 Back to Locations", "lc_panel"),
        "admin_pages":         ("📄 Back to Pages", "admin_pages"),
        "tpl_panel":           ("📝 Back to Templates", "tpl_panel"),
        "fj_panel":            ("🔗 Back to Force Join", "fj_panel"),
    }

    if _return_hint and _return_hint in _RETURN_MAP:
        _lbl, _cb = _RETURN_MAP[_return_hint]
        return_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(_lbl, callback_data=_cb)],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
        ])
        _cancel_text = f"❌ *Cancelled.*\n\nTap below to continue:"
    else:
        return_kb = main_menu_keyboard(q.from_user.id == ADMIN_ID,
                                         user_id=q.from_user.id)
        _cancel_text = "❌ *Cancelled.*\n\nReturned to main menu."

    try:
        await q.edit_message_text(
            _cancel_text,
            parse_mode="Markdown",
            reply_markup=return_kb,
        )
    except Exception:
        try: await q.message.delete()
        except: pass
        await c.bot.send_message(
            q.from_user.id,
            "❌ Cancelled.",
            reply_markup=return_kb,
        )

    # 🆕 v81.1 CRITICAL: return ConversationHandler.END so PTB knows the
    # active conv is really finished (previous version returned None → conv
    # stayed in its state → next text message re-entered the flow).
    return ConversationHandler.END


# ════════════════════════════════════════════
# 🤖 AI ADMIN ASSISTANT
# ════════════════════════════════════════════

async def admin_ai_callback(u, c):
    """💬 Open AI Assistant chat"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    # Enable AI mode flag — text messages will route to AI
    c.user_data['ai_mode'] = True
    c.user_data['ai_history'] = []  # fresh chat
    text = (
        "🤖 *AI Admin Assistant*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "_Salam Admin! Main aapka AI Assistant hoon._\n\n"
        "Panel ki kisi bhi setting ke baare mein mujh se poochein:\n\n"
        "• Any language supported\n"
        "• Step-by-step navigation paths\n"
        "• Settings ki guidance\n"
        "• Features ke explanations\n\n"
        "_Example sawalat:_\n"
        "• `How to hide warranty?`\n"
        "• `How do I add a new product?`\n"
        "• `Carousel format kya hai?`\n"
        "• `Custom page kaise banayein?`\n\n"
        "👇 Type your question below..."
    )
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=ai_welcome_keyboard())


async def handle_ai_message(u, c):
    """Handle text messages when admin is in AI mode.
    Returns True if message was handled by AI, False otherwise."""
    if u.effective_user.id != ADMIN_ID:
        return False
    if not c.user_data.get('ai_mode'):
        return False

    # Send "thinking..." message
    thinking = await u.message.reply_text("🤔 _Thinking..._", parse_mode="Markdown")

    # Call Gemini
    question = u.message.text.strip()
    history = c.user_data.get('ai_history', [])
    try:
        from ai_misc import ask_ai
        success, response = await ask_ai(question, history)
    except Exception as e:
        success, response = False, f"⚠️ AI Assistant error: {e}"

    # Delete thinking message
    try: await thinking.delete()
    except Exception: pass

    if success:
        # Update conversation history
        history.append({"role": "user", "parts": [question]})
        history.append({"role": "model", "parts": [response]})
        # Keep last 10 exchanges (20 messages) to avoid token bloat
        if len(history) > 20:
            history = history[-20:]
        c.user_data['ai_history'] = history

        # Send AI response
        try:
            await u.message.reply_text(
                f"🤖 *AI:*\n{response}",
                parse_mode="Markdown",
                reply_markup=ai_chat_keyboard()
            )
        except Exception:
            # Markdown might break — send as plain
            try:
                await u.message.reply_text(
                    f"🤖 AI:\n{response}",
                    reply_markup=ai_chat_keyboard()
                )
            except Exception as e:
                await u.message.reply_text(f"⚠️ Send error: {e}",
                                           reply_markup=ai_chat_keyboard())
    else:
        # Error message
        await u.message.reply_text(response, reply_markup=ai_chat_keyboard())

    return True


async def ai_exit_callback(u, c):
    """🔙 Exit AI chat mode"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("AI mode closed ✅")
    c.user_data.pop('ai_mode', None)
    c.user_data.pop('ai_history', None)
    await _safe_edit(q,
        "✅ *AI Assistant closed.*\n\nBack to Admin Panel:",
        parse_mode="Markdown",
        reply_markup=admin_menu_keyboard())


async def ai_clear_callback(u, c):
    """🗑️ Clear AI chat history"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Chat history cleared ✅")
    c.user_data['ai_history'] = []
    await _safe_edit(q,
        "🗑️ *Chat history cleared!*\n\nAap fresh sawal pooch saktay hain.",
        parse_mode="Markdown",
        reply_markup=ai_welcome_keyboard())


# ════════════════════════════════════════════
# 🔄 RESET ALL SETTINGS + ↩️ UNDO CHANGES (v21)
# ════════════════════════════════════════════
from database import (log_change, get_recent_changes, get_last_change,
                      remove_change, clear_change_history, reset_all_settings)
from datetime import datetime


async def admin_reset_undo_callback(u, c):
    """🔄 Reset & Undo main screen"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    changes = get_recent_changes(10)
    text = f"""🔄 *Reset & Undo*
━━━━━━━━━━━━━━━━━━━━

📊 Recent changes saved: *{len(changes)}/10*

↩️ *Undo Changes:*
Last 10 changes can be reverted one-by-one.

🔄 *Reset All Settings:*
⚠️ Wipes ALL customizations:
  • All settings (shop name, payment, etc.)
  • All button renames + hides + reorders
  • All custom buttons
  • All custom pages
  • All response edits
  • Display format / styles / sizes / toggles

✅ Does NOT delete:
  • Users / Orders / Products / Categories
  • Profit history

Pick an action:"""
    kb = [
        [InlineKeyboardButton("↩️ Undo Last Change", callback_data="undo_one")],
        [InlineKeyboardButton("📋 View Recent Changes", callback_data="undo_view")],
        [InlineKeyboardButton("🗑️ Clear Undo History", callback_data="undo_clear")],
        [InlineKeyboardButton("⚠️ RESET ALL SETTINGS", callback_data="reset_confirm")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def undo_view_callback(u, c):
    """📋 View recent changes list"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    changes = get_recent_changes(10)
    if not changes:
        text = "📋 *No changes recorded yet.*\n\nChange some settings first to undo them."
    else:
        text = "📋 *Recent Changes (newest first):*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, ch in enumerate(changes, 1):
            try:
                dt = datetime.strptime(str(ch['created_at'])[:19], "%Y-%m-%d %H:%M:%S")
                dt_str = dt.strftime("%d %b %I:%M %p")
            except Exception:
                dt_str = str(ch['created_at'])[:16]
            desc = escape_md(ch['description'] or "Change")
            old_v = (str(ch['old_value']) or "(empty)")[:30]
            new_v = (str(ch['new_value']) or "(empty)")[:30]
            text += f"*{i}.* {desc}\n   `{escape_md(old_v)}` → `{escape_md(new_v)}`\n   _{dt_str}_\n\n"
        text += "↩️ Use *Undo Last Change* to revert the most recent one."
    kb = [
        [InlineKeyboardButton("↩️ Undo Last", callback_data="undo_one")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_reset_undo")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def undo_one_callback(u, c):
    """↩️ Undo the most recent change"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    last = get_last_change()
    if not last:
        await q.answer("Nothing to undo!", show_alert=True)
        return
    await q.answer()

    change_type = last['change_type']
    target = last['target_key']
    old_val = last['old_value']
    desc = last['description'] or 'change'

    reverted = False
    try:
        if change_type == "setting":
            # Restore old setting value
            if old_val:
                set_setting(target, old_val)
            else:
                # If old was empty, delete the setting
                conn = get_connection(); cur = conn.cursor()
                cur.execute("DELETE FROM bot_settings WHERE key=?", (target,))
                conn.commit(); conn.close()
            reverted = True
        elif change_type == "toggle":
            if old_val in ("0", "1"):
                set_setting(target, old_val)
                reverted = True
        elif change_type == "custom_button_add":
            # Undo add → delete the button
            try:
                delete_custom_button(int(target))
                reverted = True
            except Exception:
                pass
        elif change_type == "custom_button_del":
            # Undo delete → reactivate
            try:
                conn = get_connection(); cur = conn.cursor()
                cur.execute("UPDATE custom_buttons SET is_active=1 WHERE id=?", (int(target),))
                conn.commit(); conn.close()
                reverted = True
            except Exception:
                pass
    except Exception as e:
        await _safe_edit(q, f"❌ Undo failed: {e}",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_reset_undo")]]))
        return

    # Remove from history
    remove_change(last['id'])

    remaining = len(get_recent_changes(10))
    if reverted:
        text = (f"✅ *Undone!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Reverted: {escape_md(desc)}\n"
                f"Back to: `{escape_md(str(old_val)[:60] or '(default)')}`\n\n"
                f"📊 Remaining undos: *{remaining}/10*")
    else:
        text = f"⚠️ Could not undo this change. Removed from history.\nRemaining: {remaining}"

    kb = [[InlineKeyboardButton("↩️ Undo Next", callback_data="undo_one")] if remaining > 0 else [],
          [InlineKeyboardButton("🔙 Back", callback_data="admin_reset_undo")]]
    kb = [r for r in kb if r]  # filter empty rows
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def undo_clear_callback(u, c):
    """🗑️ Clear undo history (no actual undo, just delete history)"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    clear_change_history()
    await q.answer("History cleared ✅")
    set_cb_data(u, "admin_reset_undo")
    await admin_reset_undo_callback(u, c)


async def reset_confirm_callback(u, c):
    """⚠️ Show confirmation before resetting"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    text = """⚠️ *RESET ALL SETTINGS — CONFIRM*
━━━━━━━━━━━━━━━━━━━━

This action is *IRREVERSIBLE* (cannot be undone after reset).

❌ *Delete kar dega:*
  • All settings (shop name, payment numbers, etc.)
  • All button customizations (renames, hides, order)
  • All custom buttons + their submenus
  • All custom pages
  • All bot response edits
  • Display format / button size / menu style / toggles
  • Undo history

✅ *Safe rahega:*
  • Users / Orders / Products / Categories
  • Profit/Sales records

Sure ho?"""
    kb = [
        [InlineKeyboardButton("✅ YES, Reset Everything", callback_data="reset_do")],
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_reset_undo")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def reset_do_callback(u, c):
    """🔄 Actually perform reset"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        reset_all_settings()
        await q.answer("✅ Reset complete!", show_alert=True)
        await _safe_edit(q,
            "✅ *All Settings Reset!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "Bot is now in default state.\n\n"
            "• Settings: cleared\n"
            "• Custom buttons: removed\n"
            "• Custom pages: removed\n"
            "• Button renames/hides: cleared\n"
            "• Toggles: defaults restored\n\n"
            "Aap dobara customize kar saktay hain.",
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard())
    except Exception as e:
        await _safe_edit(q, f"❌ Reset failed: {e}",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_reset_undo")]]))


# ════════════════════════════════════════════
# 💾 BACKUP & RESTORE DATABASE (v22)
# ════════════════════════════════════════════
import os
import shutil
import sqlite3 as _sqlite3
from datetime import datetime as _dt


async def admin_backup_callback(u, c):
    """💾 Backup/Restore main screen"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    # Get DB stats
    from database import DB_PATH
    db_path = DB_PATH
    db_size = 0
    last_modified = "N/A"
    try:
        if os.path.exists(db_path):
            db_size = os.path.getsize(db_path)
            mtime = os.path.getmtime(db_path)
            last_modified = _dt.fromtimestamp(mtime).strftime("%d %b %Y %I:%M %p")
    except Exception:
        pass

    size_kb = db_size / 1024
    size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"

    # v128: Backup health — written by the scheduled cloud-backup job.
    try:
        last_bk_status = get_setting('backup_last_status', 'never')
        last_bk_at = get_setting('backup_last_at', 'never')
        last_bk_size = get_setting('backup_last_size_kb', '')
        last_bk_line = f"  • Last auto-backup: `{escape_md(last_bk_status)}` at `{escape_md(last_bk_at)}`"
        if last_bk_size:
            last_bk_line += f" ({escape_md(last_bk_size)} KB)"
    except Exception:
        last_bk_line = "  • Last auto-backup: `unknown`"

    text = f"""💾 *Backup & Restore Database*
━━━━━━━━━━━━━━━━━━━━

📊 *Current Database:*
  • File: `shop.db`
  • Size: *{size_str}*
  • Last modified: {last_modified}
{last_bk_line}

📥 *Download Backup:*
Download a copy of your bot database.
Aap ise apne pass safe rakh saktay hain.

📤 *Restore from Backup:*
Restore your bot from a previously downloaded
backup file. Send .db file as document.

⚠️ *Restore WARNING:*
  • Current data REPLACE ho jata hai
  • Bot ko restart karna parta hai
  • Old backup taken automatically before restore

Choose action:"""
    kb = [
        [InlineKeyboardButton("📥 Download Backup", callback_data="bk_download")],
        [InlineKeyboardButton("☁️ Backup to Channel NOW", callback_data="bk_cloud_now")],
        [InlineKeyboardButton("📤 Restore from File", callback_data="bk_restore_start")],
        [InlineKeyboardButton("🔄 Reset to Fresh (0 Data)", callback_data="bk_reset_start")],
        [InlineKeyboardButton("📋 View Auto-Backups", callback_data="bk_list_auto")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def backup_cloud_now_callback(u, c):
    """☁️ Manually trigger a Telegram cloud backup right now.

    🆕 v110: BACKGROUND-TASK PATTERN (same fix as backup_download_callback).
    Prevents "query too old" on first click.
    """
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        try: await q.answer("❌", show_alert=True)
        except Exception: pass
        return
    try: await q.answer("☁️ Sending backup...", show_alert=False)
    except Exception: pass

    try:
        await _safe_edit(q,
            "☁️ *Sending backup to your cloud…*\n\n"
            "_Running in background — you can keep using the bot._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "🔙 Back", callback_data="admin_backup")]]))
    except Exception:
        pass

    import asyncio as _aio
    _aio.create_task(_do_cloud_backup_bg(c.bot, q.from_user.id))


async def _do_cloud_backup_bg(bot, admin_uid):
    """🆕 v110: Background cloud backup worker."""
    import os, shutil, asyncio as _aio
    from datetime import datetime as _dt2
    try:
        from config import BACKUP_CHANNEL_ID
        from database import DB_PATH
        target = BACKUP_CHANNEL_ID or admin_uid
        if not os.path.exists(DB_PATH):
            try: await bot.send_message(admin_uid, "❌ No database file found.")
            except Exception: pass
            return
        ts = _dt2.now().strftime("%Y%m%d_%H%M%S")
        tmp = os.path.join("/tmp", f"manualbackup_{ts}.db") if os.path.exists("/tmp") else f"manualbackup_{ts}.db"
        await _aio.to_thread(shutil.copy2, DB_PATH, tmp)
        with open(tmp, "rb") as f:
            await bot.send_document(
                chat_id=target, document=f, filename=f"shop_backup_{ts}.db",
                caption=f"☁️ *Manual Backup*\n📅 {_dt2.now().strftime('%d %b %Y %I:%M %p')}",
                parse_mode="Markdown",
            )
        try: os.remove(tmp)
        except Exception: pass
        where = "backup channel" if BACKUP_CHANNEL_ID else "your private chat (DM)"
        try:
            await bot.send_message(admin_uid,
                f"✅ *Backup sent to {where}!*", parse_mode="Markdown")
        except Exception: pass
    except Exception as e:
        try:
            await bot.send_message(admin_uid,
                f"❌ Backup failed: `{e}`\n\n"
                f"Make sure the bot is an *admin* of the backup channel, "
                f"and BACKUP_CHANNEL_ID is correct.",
                parse_mode="Markdown")
        except Exception: pass


async def backup_download_callback(u, c):
    """📥 Send DB file to admin as document.

    🆕 v110: BACKGROUND-TASK PATTERN to eliminate "query timeout" on first click.
    Old bug: shutil.copy2 on a large DB + send_document ran INLINE in the
    callback handler. On the first click after a cold event loop, the whole
    thing took > 10-15s and Telegram's callback_query answer window expired
    → user saw "query is too old" (Temporary Error). Second click succeeded
    because the DB was warm in OS page cache.

    New behaviour: `q.answer()` fires instantly with "Preparing…", we edit
    the screen with a placeholder immediately, and the heavy copy + send is
    dispatched as an asyncio background task with `asyncio.to_thread` for
    the blocking file I/O. `_safe_edit` at the end tolerates the query
    already being stale (falls back to send_message).
    """
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        try: await q.answer("❌", show_alert=True)
        except Exception: pass
        return
    try: await q.answer("📦 Preparing backup...", show_alert=False)
    except Exception: pass

    # Instant placeholder so user sees progress and query is answered fast
    try:
        await _safe_edit(q,
            "📦 *Preparing backup…*\n\n"
            "_Copying database & uploading. This runs in the background — "
            "you can safely tap Back or do other things._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "🔙 Back", callback_data="admin_backup")]]))
    except Exception:
        pass

    # Kick off the real work as a background task — event loop stays free
    import asyncio as _aio
    _aio.create_task(_do_backup_download_bg(c.bot, q.from_user.id))


async def _do_backup_download_bg(bot, admin_uid):
    """🆕 v110: Background worker for backup download. Handles copy + send
    without blocking the callback query, tolerates any Telegram/File errors.
    """
    from database import DB_PATH
    import asyncio as _aio
    db_path = DB_PATH
    if not os.path.exists(db_path):
        try:
            await bot.send_message(admin_uid, "❌ Database file not found!")
        except Exception: pass
        return

    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"bite_store_backup_{ts}.db"
    backup_path = os.path.join("/tmp", backup_name) if os.path.exists("/tmp") else backup_name

    try:
        # Copy in a thread — event loop stays free for other users
        await _aio.to_thread(shutil.copy2, db_path, backup_path)
        size_kb = os.path.getsize(backup_path) / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"

        with open(backup_path, "rb") as f:
            await bot.send_document(
                chat_id=admin_uid, document=f, filename=backup_name,
                caption=(
                    f"💾 *Database Backup*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📅 Date: {_dt.now().strftime('%d %b %Y %I:%M %p')}\n"
                    f"📦 Size: {size_str}\n\n"
                    f"⚠️ Save this file safely!\n"
                    f"Use 'Restore from File' to load it back."
                ),
                parse_mode="Markdown",
            )
        try: os.remove(backup_path)
        except Exception: pass
        try:
            await bot.send_message(admin_uid,
                f"✅ *Backup Sent!* `{backup_name}`", parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔙 Back to Backup Menu", callback_data="admin_backup")]]))
        except Exception: pass
    except Exception as e:
        try:
            await bot.send_message(admin_uid, f"❌ Backup failed: `{e}`",
                                   parse_mode="Markdown")
        except Exception: pass


async def backup_restore_start_callback(u, c):
    """📤 Start restore — wait for DB file upload"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    c.user_data['awaiting_restore'] = True
    text = """📤 *Restore Database*
━━━━━━━━━━━━━━━━━━━━

📎 Send your backup `.db` file as a *document*
(not as photo or anything else).

⚠️ *Important:*
  • File must be a valid SQLite .db file
  • Current data will be REPLACED
  • Auto-backup of current DB will be saved first
  • Bot may need restart after restore

📋 *Steps:*
1. Tap 📎 attachment in Telegram
2. Select file → choose your .db backup
3. Send

Tap ❌ to cancel."""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="bk_cancel_restore")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def backup_cancel_restore_callback(u, c):
    """❌ Cancel restore"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    c.user_data.pop('awaiting_restore', None)
    await q.answer("Cancelled")
    set_cb_data(u, "admin_backup")
    await admin_backup_callback(u, c)


async def handle_db_upload(update, context):
    """Handle DB file upload during restore.
    Returns True if handled, False otherwise."""
    if update.effective_user.id != ADMIN_ID:
        return False
    if not context.user_data.get('awaiting_restore'):
        return False
    if not update.message.document:
        return False

    doc = update.message.document
    fname = doc.file_name or "unknown"

    # Validate filename
    if not fname.lower().endswith('.db'):
        await update.message.reply_text(
            f"❌ Not a database file!\n\nYou sent: `{fname}`\n\nFile must end with `.db`",
            parse_mode="Markdown")
        return True

    # Size check (max 50 MB safety)
    if doc.file_size and doc.file_size > 50 * 1024 * 1024:
        await update.message.reply_text("❌ File too large (max 50 MB)")
        return True

    await update.message.reply_text("📥 Downloading file...")

    try:
        # Download to temp location
        tg_file = await doc.get_file()
        tmp_path = os.path.join("/tmp", f"restore_{_dt.now().strftime('%Y%m%d_%H%M%S')}.db") \
                   if os.path.exists("/tmp") else "restore_temp.db"
        await tg_file.download_to_drive(tmp_path)

        # Validate it's a real SQLite file
        try:
            conn = _sqlite3.connect(tmp_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 5")
            tables = cur.fetchall()
            conn.close()
            if not tables:
                raise ValueError("No tables found in DB")
        except Exception as e:
            try: os.remove(tmp_path)
            except: pass
            await update.message.reply_text(
                f"❌ Invalid SQLite database!\n\nError: `{e}`\n\nFile might be corrupted.",
                parse_mode="Markdown")
            context.user_data.pop('awaiting_restore', None)
            return True

        # Confirm restore
        context.user_data['restore_file'] = tmp_path
        context.user_data.pop('awaiting_restore', None)
        ts = _dt.now().strftime("%d %b %Y %I:%M %p")
        size_kb = os.path.getsize(tmp_path) / 1024
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ YES, Restore Now", callback_data="bk_restore_do")],
            [InlineKeyboardButton("❌ Cancel", callback_data="bk_restore_cancel_file")],
        ])
        await update.message.reply_text(
            f"✅ *File Validated!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 File: `{fname}`\n"
            f"💾 Size: {size_kb:.1f} KB\n"
            f"📋 Tables: {len(tables)}\n"
            f"📅 Uploaded: {ts}\n\n"
            f"⚠️ *Restore karne se pehle current DB ka backup le liya jayega.*\n\n"
            f"Are you SURE you want to restore?\n"
            f"(All current data will be replaced)",
            parse_mode="Markdown", reply_markup=kb)
        return True
    except Exception as e:
        await update.message.reply_text(f"❌ Upload error: {e}")
        context.user_data.pop('awaiting_restore', None)
        return True


async def backup_restore_do_callback(u, c):
    """✅ Actually perform the restore"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    restore_file = c.user_data.get('restore_file')
    if not restore_file or not os.path.exists(restore_file):
        await q.answer("File not found", show_alert=True)
        return
    await q.answer("🔄 Restoring...", show_alert=False)

    try:
        # 1. Backup current DB to safety folder
        os.makedirs("auto_backups", exist_ok=True)
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        safety_backup = os.path.join("auto_backups", f"pre_restore_{ts}.db")
        from database import DB_PATH
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, safety_backup)

        # 2. Replace current DB with uploaded file
        shutil.copy2(restore_file, DB_PATH)

        # 3. 🆕 v43: AUTO-MIGRATE — runs every setup/ensure_column/migration
        # function so the restored (possibly old) DB instantly matches the
        # bot's current schema. Fixes "buttons stuck after restore" issue.
        migration_stats = {"tables_checked": 0, "columns_added": 0, "errors": ["not run"]}
        try:
            from database import migrate_all
            migration_stats = migrate_all()
        except Exception as me:
            migration_stats = {"tables_checked": 0, "columns_added": 0,
                               "errors": [f"migrate_all crashed: {me}"]}

        # 4. Cleanup
        try: os.remove(restore_file)
        except: pass
        c.user_data.pop('restore_file', None)

        # Build migration status text
        err_count = len(migration_stats.get("errors") or [])
        mig_line = (
            f"🔧 *Auto-Migration:* ✅ {migration_stats.get('tables_checked', 0)} "
            f"tables checked"
        )
        if err_count:
            mig_line += f"  ·  ⚠️ {err_count} warnings"
        else:
            mig_line += "  ·  0 warnings"

        await _safe_edit(q,
            f"✅ *Restore Complete!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Database restored successfully.\n\n"
            f"🛡️ *Safety backup saved:*\n"
            f"`{safety_backup}`\n\n"
            f"{mig_line}\n"
            f"_Old DB ki missing columns/tables auto-add ho gayi. "
            f"Buttons stuck nahi honge._\n\n"
            f"♻️ *Tip:* Best results ke liye bot ko ek baar restart kar lein "
            f"so all caches refresh:\n\n"
            f"`python bot.py`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]))
    except Exception as e:
        await _safe_edit(q, f"❌ Restore failed: {e}",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_backup")]]))


async def backup_restore_cancel_file_callback(u, c):
    """❌ Cancel restore after file uploaded"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    restore_file = c.user_data.get('restore_file')
    if restore_file:
        try: os.remove(restore_file)
        except: pass
    c.user_data.pop('restore_file', None)
    await q.answer("Cancelled")
    set_cb_data(u, "admin_backup")
    await admin_backup_callback(u, c)


async def resetbot_command(update, context):
    """🔄 /resetbot — Instantly reset the bot database to fresh empty state (0 data)."""
    uid = update.effective_user.id if update.effective_user else 0
    if not _is_admin(uid):
        return
    import shutil
    from datetime import datetime as _dt
    from database import DB_PATH, setup_database, migrate_all
    
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("auto_backups", exist_ok=True)
    safety_backup = os.path.join("auto_backups", f"pre_reset_{ts}.db")
    try:
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, safety_backup)
    except Exception:
        pass

    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except Exception as e:
        await update.message.reply_text(f"❌ Could not remove DB: {e}")
        return

    setup_database()
    migrate_all()

    try:
        from config import DEFAULT_RESPONSES
        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        for k, v in DEFAULT_RESPONSES.items():
            cur.execute("INSERT OR IGNORE INTO bot_responses (key, value) VALUES (?, ?)", (k, v))
        conn.commit()
    except Exception:
        pass

    await update.message.reply_text(
        "✅ *Bot Reset Complete!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Database has been reset to a fresh state (`0 users`, `0 orders`, `0 products`).\n\n"
        "All 68 default English responses and schemas are ready.\n\n"
        "Whenever you want to restore your live data, upload your `.db` file in `/admin` → *Backup & Restore* → *Restore from File*.",
        parse_mode="Markdown"
    )


async def backup_reset_start_callback(u, c):
    """🔄 Prompt confirmation to reset DB to empty 0-data state."""
    q = u.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    await q.answer()
    text = (
        "⚠️ *WARNING: Reset Bot to Fresh State (0 Data)*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "This will wipe all existing users, orders, and products so the bot becomes 100% fresh and empty.\n\n"
        "🛡️ A safety backup of the current database will be saved automatically before resetting.\n\n"
        "Are you SURE you want to reset the bot?"
    )
    kb = [
        [InlineKeyboardButton("✅ YES, Reset Now", callback_data="bk_reset_do")],
        [InlineKeyboardButton("❌ Cancel", callback_data="bk_reset_cancel")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def backup_reset_do_callback(u, c):
    """✅ Perform actual DB reset to empty fresh state."""
    q = u.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    await q.answer("Resetting...")
    import shutil
    from datetime import datetime as _dt
    from database import DB_PATH, setup_database, migrate_all
    
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("auto_backups", exist_ok=True)
    safety_backup = os.path.join("auto_backups", f"pre_reset_{ts}.db")
    try:
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, safety_backup)
    except Exception:
        pass

    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except Exception as e:
        await _safe_edit(q, f"❌ Could not remove DB: {e}")
        return

    setup_database()
    migrate_all()

    try:
        from config import DEFAULT_RESPONSES
        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        for k, v in DEFAULT_RESPONSES.items():
            cur.execute("INSERT OR IGNORE INTO bot_responses (key, value) VALUES (?, ?)", (k, v))
        conn.commit()
    except Exception:
        pass

    text = (
        "✅ *Bot Reset Complete!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Database has been reset to a fresh state (`0 users`, `0 orders`, `0 products`).\n\n"
        "Whenever you want to restore your live data, use *Restore from File* in `/admin` → *Backup & Restore*."
    )
    kb = [[InlineKeyboardButton("🔙 Back to Backup & Restore", callback_data="admin_backup")]]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def backup_reset_cancel_callback(u, c):
    """❌ Cancel DB reset."""
    q = u.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    await q.answer("Cancelled")
    set_cb_data(u, "admin_backup")
    await admin_backup_callback(u, c)


async def backup_list_auto_callback(u, c):
    """📋 List auto-saved backups (pre-restore safety copies)"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    folder = "auto_backups"
    if not os.path.exists(folder):
        text = "📋 *No auto-backups yet.*\n\nAuto-backups are created automatically before each Restore operation."
    else:
        files = sorted(os.listdir(folder), reverse=True)[:10]
        if not files:
            text = "📋 *No auto-backups yet.*"
        else:
            text = "📋 *Auto-Backups (last 10):*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for f in files:
                fp = os.path.join(folder, f)
                try:
                    sz = os.path.getsize(fp) / 1024
                    mt = _dt.fromtimestamp(os.path.getmtime(fp)).strftime("%d %b %Y %I:%M %p")
                    text += f"📦 `{f}`\n   📅 {mt}  |  💾 {sz:.1f} KB\n\n"
                except Exception:
                    pass
            text += "_These are stored on server. Ask developer if you need them recovered._"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_backup")]])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


# ════════════════════════════════════════════
# 🎨 PRODUCT COLOR INDICATORS (v23)
# ════════════════════════════════════════════
from database import get_color_setting, DEFAULT_COLORS as _DEFAULT_COLORS


async def admin_colors_callback(u, c):
    """🎨 Product color settings main screen"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    enabled = get_color_setting("color_enabled") == "1"
    in_stk = get_color_setting("color_in_stock")
    low_stk = get_color_setting("color_low_stock")
    out_stk = get_color_setting("color_out_stock")
    threshold = get_color_setting("color_threshold")

    text = f"""🎨 *Product Color Indicators*
━━━━━━━━━━━━━━━━━━━━

Telegram does not support changing button background colors,
lekin hum *emoji indicators* use kar ke "color effect" la sakte hain!

📌 *Current Status:* {'🟢 Enabled' if enabled else '🔴 Disabled'}

📦 *Stock-based Colors:*
  {in_stk} In Stock (more than {threshold})
  {low_stk} Low Stock (1 to {threshold})
  {out_stk} Out of Stock (0)

🎯 *Live Example:*
  {in_stk} 🛍️ Netflix Premium [25] — $4.99
  {low_stk} 🛍️ Spotify Solo [3] — $5.00
  {out_stk} 🛍️ ChatGPT Plus ❌ — $5.99

Choose action:"""
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=color_settings_main_keyboard())


async def color_toggle_callback(u, c):
    """Toggle colors ON/OFF"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    current = get_color_setting("color_enabled")
    new = "0" if current == "1" else "1"
    log_change("setting", "color_enabled", current, new, "Color indicators toggle")
    set_setting("color_enabled", new)
    await q.answer(f"Colors {'ENABLED' if new == '1' else 'DISABLED'} ✅")
    set_cb_data(u, "admin_colors")
    await admin_colors_callback(u, c)


async def color_pick_callback(u, c):
    """Open color picker for a specific state"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    state = q.data.replace("cl_pick_", "")  # in_stock / low_stock / out_stock
    if state not in ("in_stock", "low_stock", "out_stock"):
        await q.answer("Invalid state", show_alert=True); return
    state_labels = {
        "in_stock": "In Stock (more than threshold)",
        "low_stock": "Low Stock (under threshold)",
        "out_stock": "Out of Stock (0)",
    }
    label = state_labels[state]
    current = get_color_setting(f"color_{state}")
    text = (f"🎨 *Pick {label} indicator*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Current: *{current}*\n\n"
            f"Tap an emoji to use it:")
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=color_picker_keyboard(state))


async def color_set_callback(u, c):
    """Set selected emoji for a state.
    Callback format: cl_set_<state>_<emoji>"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    # Parse: cl_set_in_stock_🟢
    raw = q.data.replace("cl_set_", "")
    # Split on last "_" — emoji might contain special chars
    parts = raw.rsplit("_", 1)
    if len(parts) != 2:
        await q.answer("Invalid", show_alert=True); return
    state, emoji = parts
    if state not in ("in_stock", "low_stock", "out_stock"):
        await q.answer("Invalid state", show_alert=True); return
    setting_key = f"color_{state}"
    old_val = get_color_setting(setting_key)
    log_change("setting", setting_key, old_val, emoji, f"Color: {state}")
    set_setting(setting_key, emoji)
    await q.answer(f"✅ Set to {emoji}")
    # Refresh picker to show new selection
    set_cb_data(u, f"cl_pick_{state}")
    await color_pick_callback(u, c)


async def color_threshold_callback(u, c):
    """Open threshold picker"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    current = get_color_setting("color_threshold")
    text = (f"📊 *Low Stock Threshold*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Current: *{current}*\n\n"
            f"Jab stock is number ya us se kam ho,\n"
            f"product 'Low Stock' indicator dikhayega.\n\n"
            f"Example: Threshold = 5\n"
            f"  Stock 0 → Red (out)\n"
            f"  Stock 1-5 → Yellow (low)\n"
            f"  Stock 6+ → Green (in stock)\n\n"
            f"Choose a value:")
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=color_threshold_keyboard())


async def color_set_threshold_callback(u, c):
    """Set threshold value"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        val = int(q.data.replace("cl_thr_", ""))
    except ValueError:
        await q.answer("Invalid", show_alert=True); return
    old_val = get_color_setting("color_threshold")
    log_change("setting", "color_threshold", old_val, str(val), "Color threshold")
    set_setting("color_threshold", str(val))
    await q.answer(f"✅ Threshold = {val}")
    set_cb_data(u, "admin_colors")
    await admin_colors_callback(u, c)


async def color_preview_callback(u, c):
    """Show live preview of how products will look"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    in_stk = get_color_setting("color_in_stock")
    low_stk = get_color_setting("color_low_stock")
    out_stk = get_color_setting("color_out_stock")
    threshold = get_color_setting("color_threshold")

    # Build preview with real products if available
    try:
        from database import get_all_active_products
        products = get_all_active_products()[:5]
    except Exception:
        products = []

    text = "👁️ *Live Preview — Your Shop View*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not products:
        # Use dummy examples
        text += (f"{in_stk} 🛍️ Netflix Premium [25] — $4.99\n\n"
                 f"{in_stk} 🛍️ Spotify Family [50] — $3.99\n\n"
                 f"{low_stk} 🛍️ ChatGPT Plus [3] — $5.99\n\n"
                 f"{low_stk} 🛍️ Telegram Premium [{threshold}] — $5.00\n\n"
                 f"{out_stk} 🛍️ Google AI Pro ❌ — $2.99\n\n"
                 f"{out_stk} 🛍️ Figma Pro ❌ — $3.50\n\n"
                 f"_(These are examples. Your real products will look this way.)_")
    else:
        from database import get_product_color
        for p in products:
            color = get_product_color(p['stock'])
            prefix = f"{color} " if color else ""
            if p['stock'] > 0:
                text += f"{prefix}🛍️ {p['name']} [{p['stock']}] — {fmt_price(p['price'])}\n\n"
            else:
                text += f"{prefix}🛍️ {p['name']} ❌ — {fmt_price(p['price'])}\n\n"

    text += f"\n━━━━━━━━━━━━━━━━━━━━\n📊 Threshold: {threshold} | {in_stk} In | {low_stk} Low | {out_stk} Out"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Colors", callback_data="admin_colors")]])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def color_reset_callback(u, c):
    """♻️ Reset all colors to defaults"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    for key, default in _DEFAULT_COLORS.items():
        old_val = get_color_setting(key)
        if old_val != default:
            log_change("setting", key, old_val, default, f"Reset color: {key}")
        set_setting(key, default)
    await q.answer("♻️ Reset complete!")
    set_cb_data(u, "admin_colors")
    await admin_colors_callback(u, c)


# ════════════════════════════════════════════
# 🔶 BINANCE API TEST (v24)
# ════════════════════════════════════════════
async def admin_test_binance_api_callback(u, c):
    """🤖 Test Screenshot AI Verifier (Gemini Vision)"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("🤖 Testing Gemini Vision...", show_alert=False)
    try:
        await _safe_edit(q,
            "🤖 Testing Screenshot AI...\n\n_Connecting to Gemini Vision API..._",
            parse_mode="Markdown")
    except: pass

    from payments import screenshot_ai_test_connection, screenshot_ai_is_configured
    if not screenshot_ai_is_configured():
        text = ("❌ Screenshot AI NOT Configured\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "📝 Fix Steps:\n"
                "1. Get free Gemini key: aistudio.google.com/app/apikey\n"
                "2. Add to .env file:\n"
                "   GEMINI_API_KEY=your_key\n"
                "3. Restart bot")
    else:
        success, msg = screenshot_ai_test_connection()
        if success:
            text = (f"✅ Screenshot AI Working!\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{msg}\n\n"
                    f"Users can now upload Binance screenshots\n"
                    f"and bot will verify automatically.")
        else:
            text = (f"❌ Screenshot AI Failed\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{msg}\n\nCheck GEMINI_API_KEY in .env")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Test Again", callback_data="admin_test_binance")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")],
    ])
    await _safe_edit(q, text, reply_markup=kb)


async def admin_test_email_callback(u, c):
    """📧 Test Gmail IMAP for EasyPaisa email forwarding"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("📧 Testing Gmail...", show_alert=False)
    try:
        await _safe_edit(q,
            "📧 *Testing Gmail IMAP...*\n\n_Please wait..._",
            parse_mode="Markdown")
    except: pass

    from payments import easypaisa_test_connection, easypaisa_is_configured
    if not easypaisa_is_configured():
        text = ("❌ *Gmail NOT Configured*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "📝 *Fix Steps:*\n"
                "1. Get Gmail App Password:\n"
                "   https://myaccount.google.com/apppasswords\n"
                "2. Add to `.env` file:\n"
                "   `EMAIL_ADDRESS=your@gmail.com`\n"
                "   `EMAIL_PASSWORD=app_password`\n"
                "3. Restart bot")
    else:
        success, msg = easypaisa_test_connection()
        if success:
            text = (f"✅ *Gmail IMAP Working!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{msg}\n\n"
                    f"📱 Now set up SMSForwarder app on your phone\n"
                    f"to forward EasyPaisa SMS to this Gmail.")
        else:
            text = (f"❌ *Gmail IMAP Failed*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{msg}\n\n"
                    f"⚠️ Common issues:\n"
                    f"• Wrong app password (not regular Gmail password)\n"
                    f"• 2FA not enabled on Gmail\n"
                    f"• IMAP not enabled in Gmail settings")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Test Again", callback_data="admin_test_email")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def admin_test_binance_gmail_callback(u, c):
    """📧 Test Binance Gmail IMAP for Binance Pay auto-verify"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("📧 Testing Binance Gmail...", show_alert=False)
    try:
        await _safe_edit(q,
            "📧 *Testing Binance Gmail IMAP...*\n\n_Please wait..._",
            parse_mode="Markdown")
    except: pass

    from payments import binance_email_test_connection, binance_email_is_configured
    if not binance_email_is_configured():
        text = ("❌ *Binance Gmail NOT Configured*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "📝 *Fix Steps:*\n"
                "1. Add to `.env` file:\n"
                "   `BINANCE_EMAIL=earnerboiii@gmail.com`\n"
                "   `BINANCE_EMAIL_PASSWORD=your_app_password`\n"
                "2. Restart bot")
    else:
        success, msg = binance_email_test_connection()
        if success:
            text = (f"✅ *Binance Gmail Working!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{msg}\n\n"
                    f"🤖 Users can now deposit via Binance Pay\n"
                    f"with automatic Gmail verification!")
        else:
            text = (f"❌ *Binance Gmail Failed*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{msg}\n\n"
                    f"⚠️ Common issues:\n"
                    f"• Wrong app password\n"
                    f"• IMAP not enabled")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Test Again", callback_data="admin_test_binance_gmail")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


# ════════════════════════════════════════════
# 🪙 v61: BINANCE PAY API (Direct REST + Pakistani Proxy)
# ════════════════════════════════════════════
async def admin_binance_api_panel_callback(u, c):
    """Show Binance Pay API status, toggle, and tests."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    from payments import (
        binance_api_is_configured as _api_cfg, is_proxy_configured as _proxy_cfg,
        BINANCE_API_BASE,
    )
    api_on  = (get_setting("binance_api_enabled", "0") == "1")
    keys_ok = _api_cfg()
    proxy_ok = _proxy_cfg()

    status_api    = "✅ ON" if api_on else "❌ OFF"
    status_keys   = "✅ set" if keys_ok else "❌ NOT SET"
    status_proxy  = "✅ set" if proxy_ok else "⚠️ none (will fail on Render!)"

    text = (
        "🪙 *Binance Pay API*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔌 *Toggle:* {status_api}\n"
        f"🔑 *API Keys:* {status_keys}\n"
        f"🌐 *Proxy:* {status_proxy}\n"
        f"🌍 *Endpoint:* `{BINANCE_API_BASE}`\n\n"
        "_When enabled, bot fetches payments directly from "
        "Binance Pay API for automatic verification._\n\n"
        "⚠️ Render servers are blocked by Binance (HTTP 451). "
        "You MUST set `BINANCE_PROXY_URL` to a Pakistani/allowed-region "
        "HTTP(S) or SOCKS5 proxy in Render env vars."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🔴 Turn OFF" if api_on else "🟢 Turn ON",
            callback_data="admin_binance_api_toggle")],
        [InlineKeyboardButton("🩺 Test Connection",  callback_data="admin_binance_api_test")],
        [InlineKeyboardButton("📡 Proxy Status",     callback_data="admin_binance_proxies")],
        [InlineKeyboardButton("📜 Recent Payments",  callback_data="admin_binance_api_list")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


# ════════════════════════════════════════════
# 📡 v63: PROXY POOL ADMIN PANEL (rotation + status + add/remove)
# ════════════════════════════════════════════
import time as _time63


def _fmt_ago(epoch):
    if not epoch:
        return "never"
    dt = int(_time63.time() - float(epoch))
    if dt < 60:    return f"{dt}s ago"
    if dt < 3600:  return f"{dt//60}m ago"
    if dt < 86400: return f"{dt//3600}h ago"
    return f"{dt//86400}d ago"


async def admin_binance_proxies_callback(u, c):
    """📡 Show all proxies in the pool with their live status."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    from payments import get_proxy_health_snapshot, _load_proxy_pool
    snapshot = get_proxy_health_snapshot()

    if not snapshot:
        text = (
            "📡 *Proxy Pool*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "_No proxies configured._\n\n"
            "Add a proxy below, or set "
            "`BINANCE_PROXY_URL` / `BINANCE_PROXY_LIST` in Render env vars."
        )
    else:
        lines = ["📡 *Proxy Pool*", "━━━━━━━━━━━━━━━━━━━━", ""]
        for i, row in enumerate(snapshot, 1):
            s = row.get("status", "unknown")
            if s == "ok":
                icon = "✅"
            elif s == "fail":
                icon = ("⏸️" if row.get("in_cooldown") else "❌")
            else:
                icon = "❓"
            url = row["url"]
            line = f"{i}. {icon} `{url}`"
            if s == "ok":
                line += f"\n   _last ok: {_fmt_ago(row.get('last_ok'))}_"
            elif s == "fail":
                err = (row.get('last_error') or '')[:60]
                line += f"\n   _failed {_fmt_ago(row.get('last_fail'))}: {err}_"
            lines.append(line)
        lines.append("")
        lines.append("_Bot rotates through proxies automatically. "
                     "Failed ones enter a 5-minute cooldown._")
        text = "\n".join(lines)

    kb = [
        [InlineKeyboardButton("➕ Add Proxy",       callback_data="admin_proxy_add")],
        [InlineKeyboardButton("🔄 Test All Now",    callback_data="admin_proxy_test_all")],
        [InlineKeyboardButton("♻️ Reset Cooldowns", callback_data="admin_proxy_reset")],
        # 🆕 v67: AI Scout — Gemini auto-finds new working PK proxies
        [InlineKeyboardButton("🤖 AI Find New Proxies", callback_data="admin_proxy_ai_scout")],
    ]
    # Remove buttons only for DB-added proxies (env / default proxies are immutable here)
    try:
        from database import get_setting as _gs
        db_extra = [p.strip() for p in (_gs("binance_proxy_pool", "") or "").split(",") if p.strip()]
    except Exception:
        db_extra = []
    for i, p in enumerate(db_extra):
        kb.append([InlineKeyboardButton(f"🗑 Remove #{i+1}  {p[:30]}…",
                                        callback_data=f"admin_proxy_del_{i}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_binance_api")])

    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


# ── Add Proxy: conversation-style (one-shot text input) ──
async def admin_proxy_add_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    c.user_data['admin_proxy_step'] = 'waiting_url'
    text = (
        "➕ *Add Proxy*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send the proxy URL in your next message.\n\n"
        "Format examples:\n"
        "  • `socks5://USER:PASS@host.com:1080`\n"
        "  • `socks5://103.121.120.242:1080`\n"
        "  • `http://host.com:8080`\n\n"
        "_Tested recommendations:_\n"
        "  • `socks5://103.121.120.242:1080`\n"
        "  • `socks5://103.236.134.210:1080`\n"
        "  • `socks5://182.184.119.180:1080`"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_binance_proxies")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def admin_proxy_url_received(update, context):
    """Receive a proxy URL from admin and persist it."""
    if context.user_data.get('admin_proxy_step') != 'waiting_url':
        return False
    if update.effective_user.id != ADMIN_ID:
        return False
    raw = (update.message.text or "").strip()

    # Light validation
    import re as _re63
    if not _re63.match(r'^(socks5h?|socks4|http|https)://[^\s]{4,200}$', raw, _re63.IGNORECASE):
        await update.message.reply_text(
            "❌ Invalid format. Must start with `socks5://`, `http://`, etc.\n"
            "Try again or tap Cancel.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="admin_binance_proxies")],
            ]),
        )
        return True

    # Append to DB list
    existing = (get_setting("binance_proxy_pool", "") or "").strip()
    parts = [p.strip() for p in existing.split(",") if p.strip()]
    if raw in parts:
        await update.message.reply_text("⚠️ Already in pool.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📡 Proxy Status", callback_data="admin_binance_proxies")],
            ]))
        context.user_data.pop('admin_proxy_step', None)
        return True
    parts.append(raw)
    set_setting("binance_proxy_pool", ",".join(parts))
    context.user_data.pop('admin_proxy_step', None)

    await update.message.reply_text(
        f"✅ *Proxy added*\n`{raw}`\n\n"
        f"It will be tried on the next API call. "
        f"Tap *Test Connection* to verify now.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🩺 Test Connection", callback_data="admin_binance_api_test")],
            [InlineKeyboardButton("📡 Proxy Status",    callback_data="admin_binance_proxies")],
        ]),
    )
    return True


async def admin_proxy_del_callback(u, c):
    """Remove a DB-added proxy by its index in the DB list."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        idx = int(q.data.replace("admin_proxy_del_", ""))
    except Exception:
        await q.answer("Invalid index", show_alert=True); return

    existing = (get_setting("binance_proxy_pool", "") or "").strip()
    parts = [p.strip() for p in existing.split(",") if p.strip()]
    if 0 <= idx < len(parts):
        removed = parts.pop(idx)
        set_setting("binance_proxy_pool", ",".join(parts))
        await q.answer(f"Removed: {removed[:30]}", show_alert=False)
    else:
        await q.answer("Out of range", show_alert=True)
    await admin_binance_proxies_callback(u, c)


async def admin_proxy_test_all_callback(u, c):
    """Force-test the entire pool (re-uses test_connection which tries each)."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("🔄 Testing all proxies…", show_alert=False)
    try:
        await _safe_edit(q, "📡 *Testing all proxies…*\n\n_This may take 30–60 seconds._",
                         parse_mode="Markdown")
    except Exception:
        pass
    import asyncio as _aio
    from payments import binance_api_test_connection as _bp_test
    try:
        ok, msg = await _aio.to_thread(_bp_test)
    except Exception as e:
        ok, msg = False, f"❌ Test crashed: {e}"
    icon = "✅" if ok else "❌"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Run Again", callback_data="admin_proxy_test_all")],
        [InlineKeyboardButton("📡 Proxy Status", callback_data="admin_binance_proxies")],
        [InlineKeyboardButton("🔙 Back",      callback_data="admin_binance_api")],
    ])
    await _safe_edit(q, f"{icon} *Proxy Test Result*\n━━━━━━━━━━━━━━━━━━━━\n\n{msg}",
                     parse_mode="Markdown", reply_markup=kb)


async def admin_proxy_reset_callback(u, c):
    """Clear all proxy cooldowns so failed proxies are re-tried immediately."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    from payments import reset_proxy_cooldowns
    reset_proxy_cooldowns()
    await q.answer("♻️ All cooldowns cleared", show_alert=False)
    await admin_binance_proxies_callback(u, c)


# ════════════════════════════════════════════
# 🆕 v67: AI PROXY SCOUT (Gemini)
# ════════════════════════════════════════════
async def admin_proxy_ai_scout_callback(u, c):
    """Trigger Gemini scout — fetch proxy listing sites, AI-extract PK proxies,
       test each one, auto-add working ones to the pool."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("🤖 AI Scout running…", show_alert=False)
    try:
        await _safe_edit(q,
            "🤖 *AI Proxy Scout — Running…*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📡 Fetching proxy listings…\n"
            "🧠 Asking Gemini to extract PK proxies…\n"
            "🧪 Testing each candidate against *Binance + Bybit* API…\n\n"
            "_This may take 30–90 seconds. Please wait._",
            parse_mode="Markdown")
    except Exception:
        pass

    try:
        from ai_misc import run_scout
        summary = await run_scout()
    except Exception as e:
        await _safe_edit(q,
            f"❌ *AI Scout failed*\n\n`{e}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="admin_binance_proxies")],
            ]))
        return

    srcs    = summary.get("fetched_sources", 0)
    total_srcs = summary.get("total_sources", 3)
    cands   = summary.get("candidates", 0)
    working = summary.get("working", 0)
    added   = summary.get("added", 0)
    method  = summary.get("method", "?")
    err     = summary.get("error", "")
    working_list = summary.get("working_list", [])

    if added > 0:
        lines = [
            "✅ *AI Scout Complete*",
            "━━━━━━━━━━━━━━━━━━━━", "",
            f"📡 Sources fetched: {srcs}/{total_srcs}",
            f"🧠 Method: `{method}`",
            f"🔍 Candidates found: {cands}",
            f"🧪 Working after test: *{working}*",
            f"💾 *Added to pool: {added}*", "",
        ]
        if working_list:
            lines.append("✅ *New working proxies:*")
            for url, sec in working_list[:5]:
                lines.append(f"  • `{url}`  ({sec}s)")
        lines.append("")
        lines.append("_Cooldowns reset. Binance + Bybit will use these on the next API call (shared pool)._")
        text = "\n".join(lines)
    else:
        text = (
            "⚠️ *AI Scout — No Working Proxies Found*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📡 Sources fetched: {srcs}/{total_srcs}\n"
            f"🔍 Candidates found: {cands}\n"
            f"🧪 Working: 0\n\n"
        )
        if err:
            text += f"⚠️ Error: `{err}`\n\n"
        text += (
            "All discovered proxies were dead. This happens when public "
            "free-proxy lists are stale.\n\n"
            "💡 Tip: try again in a few minutes, or buy a paid PK proxy "
            "($1–3/mo from WebShare etc.) for stable operation."
        )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Run Scout Again", callback_data="admin_proxy_ai_scout")],
        [InlineKeyboardButton("📡 Proxy Status",     callback_data="admin_binance_proxies")],
        [InlineKeyboardButton("🩺 Test Connection",  callback_data="admin_binance_api_test")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def admin_binance_api_toggle_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    cur = (get_setting("binance_api_enabled", "0") == "1")
    new = "0" if cur else "1"
    set_setting("binance_api_enabled", new)
    await q.answer(f"Binance API {'OFF' if cur else 'ON'}", show_alert=False)
    await admin_binance_api_panel_callback(u, c)


async def admin_binance_api_test_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("🩺 Testing...", show_alert=False)
    try:
        await _safe_edit(q, "🩺 *Testing Binance API...*\n\n_Pinging Binance (may take 10s)_",
                         parse_mode="Markdown")
    except Exception:
        pass
    import asyncio as _aio
    from payments import binance_api_test_connection as _bp_test
    try:
        ok, msg = await _aio.to_thread(_bp_test)
    except Exception as e:
        ok, msg = False, f"❌ Test crashed: {e}"
    icon = "✅" if ok else "❌"
    text = (
        f"{icon} *Binance API Test Result*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{msg}\n\n"
        "_Tip: set BINANCE_PROXY_URL on Render if you see HTTP 451._"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Test Again", callback_data="admin_binance_api_test")],
        [InlineKeyboardButton("🔙 Back",       callback_data="admin_binance_api")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def admin_binance_api_list_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("📜 Fetching...", show_alert=False)
    try:
        await _safe_edit(q, "📜 *Fetching recent Binance Pay transactions...*",
                         parse_mode="Markdown")
    except Exception:
        pass
    import asyncio as _aio
    from payments import get_recent_pay_transactions
    try:
        txns = await _aio.to_thread(get_recent_pay_transactions, 48, 20)
    except Exception as e:
        txns = []
    if not txns:
        text = ("📜 *Recent Payments (48h)*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "_No transactions found, or API not reachable._\n\n"
                "Try **🩺 Test Connection** first.")
    else:
        lines = ["📜 *Recent Payments (48h)*\n━━━━━━━━━━━━━━━━━━━━\n"]
        from datetime import datetime as _dt
        for t in txns[:15]:
            tm = ""
            if t.get("time_ms"):
                try:
                    tm = _dt.utcfromtimestamp(t["time_ms"]/1000).strftime("%m-%d %H:%M")
                except Exception:
                    tm = ""
            lines.append(
                f"• `${t['amount']:.2f}` from *{escape_md(t.get('counterparty') or '?')}* "
                f"({t.get('order_type','')}) {tm}"
            )
        text = "\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_binance_api_list")],
        [InlineKeyboardButton("🔙 Back",    callback_data="admin_binance_api")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


# ════════════════════════════════════════════
# 📧 PAYMENT EMAIL SETTINGS PANEL
# ════════════════════════════════════════════
PEM_EDIT_EMAIL = 1100
PEM_EDIT_PASS = 1101


# ════════════════════════════════════════════════════════════════
# 🆕 v59: Default Shop Filter (admin sets what new users see by default)
# ════════════════════════════════════════════════════════════════
SHOP_FILTER_OPTIONS = [
    ("all",         "📋 All Products",      "All visible products shown (default)"),
    ("available",   "✅ Available Only",    "Only in-stock products shown"),
    ("unavailable", "❌ Out of Stock Only", "Only out-of-stock products shown"),
]


async def admin_shop_filter_callback(u, c):
    """Show panel for admin to pick default shop filter mode for new users."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    cur = get_setting("shop_default_filter", "all") or "all"
    if cur not in ("all", "available", "unavailable"):
        cur = "all"
    text = (
        "🛒 *Default Shop Filter*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "When a user opens 🛒 *Shop* for the first time, what should they see?\n\n"
        f"📌 *Currently:* `{cur}`\n\n"
        "_Users can switch filter anytime via the buttons on shop screen.\n"
        "This setting only controls the **default** view for new users._"
    )
    kb = []
    for mode, label, desc in SHOP_FILTER_OPTIONS:
        mark = "✅ " if cur == mode else ""
        kb.append([InlineKeyboardButton(f"{mark}{label}", callback_data=f"setshopfilter_{mode}")])
    kb.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def set_shop_filter_callback(u, c):
    """Save the chosen default filter mode."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    mode = q.data.replace("setshopfilter_", "")
    if mode not in ("all", "available", "unavailable"):
        await q.answer("❌ Invalid filter", show_alert=True); return
    old = get_setting("shop_default_filter", "all")
    log_change("setting", "shop_default_filter", old, mode, f"Default shop filter → {mode}")
    set_setting("shop_default_filter", mode)
    await q.answer(f"✅ Default filter: {mode}", show_alert=False)
    # Refresh the panel
    set_cb_data(u, "admin_shop_filter")
    await admin_shop_filter_callback(u, c)


async def admin_payment_emails_callback(u, c):
    """📧 Payment Email Settings — main panel showing all methods"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    
    from database import get_all_payment_methods
    methods = get_all_payment_methods()
    
    text = ("📧 *Payment Email Settings*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "Har payment method ka Gmail email\n"
            "and manage App Passwords here.\n\n")
    
    kb = []
    for m in methods:
        status = "✅" if m['configured'] else "❌"
        email_preview = m['email'][:20] + "..." if len(m['email']) > 20 else m['email']
        text += f"{m['icon']} *{m['name']}*: {status} `{email_preview}`\n"
        kb.append([
            InlineKeyboardButton(f"{m['icon']} {m['name']} {status}", callback_data=f"pem_view_{m['id']}"),
        ])
    
    kb.append([InlineKeyboardButton("📧 Test All Connections", callback_data="pem_test_all")])
    kb.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")])
    
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def admin_pem_view_callback(u, c):
    """📧 View/edit one payment method's email settings"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    
    method_id = q.data.replace("pem_view_", "")
    from database import get_payment_email_config, get_all_payment_methods
    
    cfg = get_payment_email_config(method_id)
    methods = {m['id']: m for m in get_all_payment_methods()}
    m = methods.get(method_id, {'name': method_id, 'icon': '📧'})
    
    status = "✅ Configured" if cfg['email'] and cfg['password'] else "❌ Not Set"
    email_display = cfg['email'] or "Not Set"
    pass_display = "••••••••" if cfg['password'] else "Not Set"
    
    text = (f"{m['icon']} *{m['name']} — Email Settings*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📧 *Email:* `{email_display}`\n"
            f"🔑 *App Password:* `{pass_display}`\n"
            f"📊 *Status:* {status}\n\n"
            f"_App Password banao: https://myaccount.google.com/apppasswords_")
    
    kb = [
        [InlineKeyboardButton("✏️ Change Email", callback_data=f"pem_edit_email_{method_id}")],
        [InlineKeyboardButton("🔑 Change App Password", callback_data=f"pem_edit_pass_{method_id}")],
        [InlineKeyboardButton("📧 Test Connection", callback_data=f"pem_test_{method_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_payment_emails")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def admin_pem_test_callback(u, c):
    """📧 Test one specific payment method's Gmail connection"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    
    method_id = q.data.replace("pem_test_", "")
    await q.answer(f"📧 Testing {method_id} Gmail...", show_alert=False)
    
    from database import get_payment_email_config, get_all_payment_methods
    import os
    
    cfg = get_payment_email_config(method_id)
    methods = {m['id']: m for m in get_all_payment_methods()}
    m = methods.get(method_id, {'name': method_id, 'icon': '📧'})
    
    if not cfg['email'] or not cfg['password']:
        text = (f"❌ *{m['name']} — Not Configured*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📧 Set Email and App Password first!")
        kb = [[InlineKeyboardButton("🔙 Back", callback_data=f"pem_view_{method_id}")]]
        await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return
    
    # Temporarily set env vars for the test
    if method_id == 'binance':
        os.environ['BINANCE_EMAIL'] = cfg['email']
        os.environ['BINANCE_EMAIL_PASSWORD'] = cfg['password']
        pass
    else:
        os.environ['EMAIL_ADDRESS'] = cfg['email']
        os.environ['EMAIL_PASSWORD'] = cfg['password']
    
    from payments import imap_connect_with_credentials
    mail = imap_connect_with_credentials(cfg['email'], cfg['password'])
    if mail:
        try:
            mail.select("INBOX")
            mail.logout()
        except: pass
        text = (f"✅ *{m['name']} — Gmail Connected!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📧 Email: `{cfg['email']}`\n"
                f"🔑 App Password: Working ✅\n\n"
                f"🤖 Auto payment verification ready!")
    else:
        text = (f"❌ *{m['name']} — Connection Failed*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📧 Email: `{cfg['email']}`\n\n"
                f"⚠️ Possible issues:\n"
                f"• App Password galat hai\n"
                f"• IMAP is not enabled\n"
                f"• 2-Step Verification off hai\n\n"
                f"📝 Fix: https://myaccount.google.com/apppasswords")
    
    kb = [[InlineKeyboardButton("🔄 Test Again", callback_data=f"pem_test_{method_id}")],
          [InlineKeyboardButton("🔙 Back", callback_data=f"pem_view_{method_id}")]]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def admin_pem_test_all_callback(u, c):
    """📧 Test ALL payment methods' Gmail connections at once"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("📧 Testing all...", show_alert=False)
    
    import os
    from database import get_payment_email_config, get_all_payment_methods
    
    methods = get_all_payment_methods()
    results = []
    
    for m in methods:
        cfg = get_payment_email_config(m['id'])
        if not cfg['email'] or not cfg['password']:
            results.append(f"{m['icon']} *{m['name']}*: ❌ Not configured")
            continue
        
        try:
            if m['id'] == 'binance':
                os.environ['BINANCE_EMAIL'] = cfg['email']
                os.environ['BINANCE_EMAIL_PASSWORD'] = cfg['password']
                pass
            else:
                os.environ['EMAIL_ADDRESS'] = cfg['email']
                os.environ['EMAIL_PASSWORD'] = cfg['password']
            
            from payments import imap_connect_with_credentials
            mail = imap_connect_with_credentials(cfg['email'], cfg['password'])
            if mail:
                try: mail.logout()
                except: pass
                results.append(f"{m['icon']} *{m['name']}*: ✅ Connected")
            else:
                results.append(f"{m['icon']} *{m['name']}*: ❌ Failed")
        except Exception as e:
            results.append(f"{m['icon']} *{m['name']}*: ❌ Error")
    
    text = "📧 *All Payment Gmail Tests*\n━━━━━━━━━━━━━━━━━━━━\n\n" + "\n".join(results)
    
    kb = [
        [InlineKeyboardButton("🔄 Test All Again", callback_data="pem_test_all")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_payment_emails")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# 🔧 BUG FIX: "Change Email" / "Change App Password" buttons on the Payment
# Email Settings screen were dead — no handler was registered for
# `pem_edit_email_*` / `pem_edit_pass_*`. These two callbacks + the text
# receiver below implement the missing flow.
async def admin_pem_edit_email_callback(u, c):
    """✏️ Ask admin for the new Gmail address for a payment method."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    method_id = q.data.replace("pem_edit_email_", "")
    c.user_data['pem_edit'] = {'method': method_id, 'field': 'email'}
    from database import get_all_payment_methods
    methods = {m['id']: m for m in get_all_payment_methods()}
    m = methods.get(method_id, {'name': method_id, 'icon': '📧'})
    text = (f"{m['icon']} *{m['name']} — Change Email*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📧 Send the new Gmail address now (e.g. `yourstore@gmail.com`):")
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"pem_view_{method_id}")]]))


async def admin_pem_edit_pass_callback(u, c):
    """🔑 Ask admin for the new Gmail App Password for a payment method."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    method_id = q.data.replace("pem_edit_pass_", "")
    c.user_data['pem_edit'] = {'method': method_id, 'field': 'password'}
    from database import get_all_payment_methods
    methods = {m['id']: m for m in get_all_payment_methods()}
    m = methods.get(method_id, {'name': method_id, 'icon': '📧'})
    text = (f"{m['icon']} *{m['name']} — Change App Password*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔑 Send the 16-character Gmail *App Password* now.\n"
            f"_Make one here: https://myaccount.google.com/apppasswords_")
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"pem_view_{method_id}")]]))


async def admin_pem_value_received(u, c):
    """Receive the typed email / app-password and save it. Returns True if handled."""
    pem = c.user_data.get('pem_edit')
    if not pem:
        return False
    if u.effective_user.id != ADMIN_ID:
        return False
    method_id = pem['method']; field = pem['field']
    val = (u.message.text or "").strip()
    from database import get_payment_email_config, set_payment_email_config, get_all_payment_methods

    cfg = get_payment_email_config(method_id)
    if field == 'email':
        if "@" not in val or "." not in val:
            await u.message.reply_text("❌ That doesn't look like a valid email. Send a valid Gmail address:")
            return True  # stay in edit mode
        set_payment_email_config(method_id, val, cfg['password'])
    else:  # password
        # Gmail app passwords are 16 chars; users often paste with spaces.
        cleaned = val.replace(" ", "")
        if len(cleaned) < 8:
            await u.message.reply_text("❌ That App Password looks too short. Send the full 16-character App Password:")
            return True
        set_payment_email_config(method_id, cfg['email'], cleaned)

    c.user_data.pop('pem_edit', None)
    methods = {m['id']: m for m in get_all_payment_methods()}
    m = methods.get(method_id, {'name': method_id, 'icon': '📧'})
    label = "Email" if field == 'email' else "App Password"
    await u.message.reply_text(
        f"✅ *{m['name']} — {label} Updated!*\n\nUse *Test Connection* to verify it works.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📧 Test Connection", callback_data=f"pem_test_{method_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"pem_view_{method_id}")],
        ]))
    return True


# ════════════════════════════════════════════
# 💳 PAYMENT METHODS MANAGEMENT (v33)
# ════════════════════════════════════════════
async def admin_payments_callback(u, c):
    """💳 Show all 3 payment methods with current values"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    bid = get_setting('binance_id', BINANCE_PAY_ID)
    bn = get_setting('binance_name', get_setting('account_name', ACCOUNT_NAME))
    ep = get_setting('easypaisa', EASYPAISA_NUMBER)
    en = get_setting('easypaisa_name', get_setting('account_name', ACCOUNT_NAME))
    jc = get_setting('jazzcash', JAZZCASH_NUMBER)
    jn = get_setting('jazzcash_name', get_setting('account_name', ACCOUNT_NAME))

    text = f"""💳 *Payment Methods*
━━━━━━━━━━━━━━━━━━━━

🔶 *Binance Pay*
  ID: `{escape_md(bid)}`
  Holder: {escape_md(bn)}

📱 *EasyPaisa*
  Number: `{escape_md(ep)}`
  Name: {escape_md(en)}

📱 *JazzCash*
  Number: `{escape_md(jc)}`
  Name: {escape_md(jn)}

━━━━━━━━━━━━━━━━━━━━
Crypto addresses / Bybit Pay ID are in *Crypto Settings*.

Tap any method below to edit:"""
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=admin_payments_keyboard())


async def admin_pm_binance_callback(u, c):
    """🔶 Binance Pay edit screen"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    bid = get_setting('binance_id', BINANCE_PAY_ID)
    bn = get_setting('binance_name', get_setting('account_name', ACCOUNT_NAME))
    text = f"""🔶 *Binance Pay Settings*
━━━━━━━━━━━━━━━━━━━━

📋 *Pay ID:* `{escape_md(bid)}`
👤 *Holder Name:* {escape_md(bn)}

━━━━━━━━━━━━━━━━━━━━
Tap below to edit:"""
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=admin_pm_binance_keyboard())


async def admin_pm_easypaisa_callback(u, c):
    """📱 EasyPaisa edit screen"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    ep = get_setting('easypaisa', EASYPAISA_NUMBER)
    en = get_setting('easypaisa_name', get_setting('account_name', ACCOUNT_NAME))
    text = f"""📱 *EasyPaisa Settings*
━━━━━━━━━━━━━━━━━━━━

📱 *Number:* `{escape_md(ep)}`
👤 *Holder Name:* {escape_md(en)}

━━━━━━━━━━━━━━━━━━━━
Tap below to edit:"""
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=admin_pm_easypaisa_keyboard())


async def admin_pm_jazzcash_callback(u, c):
    """📱 JazzCash edit screen"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    jc = get_setting('jazzcash', JAZZCASH_NUMBER)
    jn = get_setting('jazzcash_name', get_setting('account_name', ACCOUNT_NAME))
    text = f"""📱 *JazzCash Settings*
━━━━━━━━━━━━━━━━━━━━

📱 *Number:* `{escape_md(jc)}`
👤 *Holder Name:* {escape_md(jn)}

━━━━━━━━━━━━━━━━━━━━
Tap below to edit:"""
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=admin_pm_jazzcash_keyboard())


# ════════════════════════════════════════════
# 📊 ADMIN DEPOSIT HISTORY (All transactions + screenshots)
# ════════════════════════════════════════════

async def admin_deposit_history_callback(u, c):
    """📊 Show ALL user deposit/order history with pagination.
    Admin can see every transaction, its status, and screenshot if uploaded."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    nav_push(c, 'admin_deposits')
    
    from database import get_all_deposit_orders
    deposits = get_all_deposit_orders(limit=100)
    
    if not deposits:
        await _safe_edit(q,
            "📊 *Deposit History*\n━━━━━━━━━━━━━━━━━━━━\n\nNo transactions yet.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]))
        return
    
    # Show first page
    await _show_deposit_page(q, c, deposits, page=1)


async def admin_deposit_page_callback(u, c):
    """📊 Pagination for deposit history"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    page = int(q.data.replace("dephist_", ""))
    from database import get_all_deposit_orders
    deposits = get_all_deposit_orders(limit=100)
    await _show_deposit_page(q, c, deposits, page)


async def _show_deposit_page(q, c, deposits, page=1):
    """Show a page of deposit history"""
    from keyboards import admin_deposit_history_keyboard
    from datetime import datetime as _dt
    
    per_page = 5
    total = len(deposits)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_deps = deposits[start:start + per_page]
    
    # Build summary text
    text = f"📊 *All Deposits & Orders ({total})*\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"📄 Page {page}/{total_pages}\n\n"
    text += "Tap any entry to see details + screenshot:\n\n"
    
    status_map = {
        'pending': ('🟡', 'Pending'),
        'screenshot_sent': ('📸', 'Screenshot'),
        'binance_waiting': ('⏳', 'Waiting'),
        'delivered': ('✅', 'Delivered'),
        'cancelled': ('❌', 'Cancelled'),
        'rejected': ('🚫', 'Rejected'),
    }
    
    for d in page_deps:
        emoji, label = status_map.get(d['status'], ('❓', d['status']))
        method = (d['payment_method'] or '').lower()
        if 'binance' in method: method_str = "🔶 Binance"
        elif 'easy' in method: method_str = "📱 EP"
        elif 'jazz' in method: method_str = "📱 JC"
        else: method_str = "💳"
        
        has_ss = "📸" if d['payment_screenshot'] else ""
        
        # Parse date
        try:
            dt = _dt.strptime(str(d['created_at'])[:19], "%Y-%m-%d %H:%M:%S")
            dt_str = dt.strftime("%d %b %I:%M %p")
        except:
            dt_str = str(d['created_at'])[:16]
        
        # Amount display
        amt_str = f"{fmt_price(d['price'])}"
        if d['binance_amount'] and d['binance_amount'] > 0:
            if d.get('binance_currency', '') == 'PKR':
                amt_str = f"Rs.{d['binance_amount']:.0f}"
            else:
                amt_str = f"${d['binance_amount']:.2f}"
        
        uname = escape_md((d['user_name'] or 'N/A')[:20])
        pname = escape_md((d['product_name'] or 'N/A')[:30])
        
        text += (f"{emoji} *#{d['id']}* {uname}\n"
                 f"  {pname}\n"
                 f"  {amt_str} | {method_str} | {label} {has_ss}\n"
                 f"  📅 {dt_str}\n\n")
    
    if total > per_page:
        text += f"\n_+{total - start - per_page} more_ (navigate below)" if start + per_page < total else ""
    
    kb = admin_deposit_history_keyboard(deposits, page, per_page)
    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except:
        try:
            await q.edit_message_text(text, reply_markup=kb)
        except:
            pass


async def admin_deposit_detail_callback(u, c):
    """📊 View single deposit/order detail with screenshot"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    
    oid = int(q.data.replace("depview_", ""))
    o = get_order(oid)
    if not o:
        await _safe_edit(q, "❌ Order not found!",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_deposits")]]))
        return
    
    from datetime import datetime as _dt
    try:
        dt = _dt.strptime(str(o['created_at'])[:19], "%Y-%m-%d %H:%M:%S")
        dt_str = dt.strftime("%d %b %Y %I:%M %p")
    except:
        dt_str = str(o['created_at'])[:19]
    
    status_map = {
        'pending': '🟡 Pending', 'screenshot_sent': '📸 Screenshot Sent',
        'binance_waiting': '⏳ Binance Waiting', 'delivered': '✅ Delivered',
        'cancelled': '❌ Cancelled', 'rejected': '🚫 Rejected',
    }
    status_str = status_map.get(o['status'], o['status'])
    
    method = (o['payment_method'] or '').lower()
    if 'binance' in method: method_str = "🔶 Binance Pay"
    elif 'easy' in method: method_str = "📱 EasyPaisa"
    elif 'jazz' in method: method_str = "📱 JazzCash"
    else: method_str = "💳 Manual"
    
    # Get user info
    user_db = get_user(o['user_id'])
    user_pts = user_db['points'] if user_db else 0
    
    text = (f"📊 *Deposit/Order #{o['id']}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 *User:* {escape_md(o['user_name'] or 'N/A')}\n"
            f"🆔 *User ID:* `{o['user_id']}`\n"
            f"💎 *User Points:* {user_pts}\n\n"
            f"📦 *Product:* {escape_md(o['product_name'] or 'N/A')}\n"
            f"💰 *Price:* {fmt_price(o['price'])}\n"
            f"💳 *Method:* {method_str}\n"
            f"📊 *Status:* {status_str}\n"
            f"📅 *Date:* {dt_str}\n")
    
    # Add payment details
    if o['binance_amount'] and o['binance_amount'] > 0:
        currency = (dict(o) if o else {}).get('binance_currency', 'USDT') or 'USDT'
        text += f"\n💰 *Amount:* {o['binance_amount']} {currency}"
    if (dict(o) if o else {}).get('binance_txid') and o['binance_txid']:
        text += f"\n🆔 *TXID:* `{escape_md(o['binance_txid'])}`"
    if (dict(o) if o else {}).get('binance_sender_name') and o['binance_sender_name']:
        text += f"\n👤 *Sender:* {escape_md(o['binance_sender_name'])}"
    
    # Order type
    otype = (dict(o) if o else {}).get('order_type', 'product') or 'product'
    text += f"\n📋 *Type:* {'💎 Points' if otype == 'points' else '📦 Product'}"
    
    from keyboards import admin_deposit_detail_keyboard
    
    # If screenshot exists, send as photo
    if o['payment_screenshot']:
        try:
            await q.delete_message()
            await c.bot.send_photo(
                q.from_user.id,
                o['payment_screenshot'],
                caption=text,
                parse_mode="Markdown",
                reply_markup=admin_deposit_detail_keyboard(o['id'])
            )
            return
        except:
            pass
    
    # No screenshot or failed to send photo
    text += "\n\n📸 _No screenshot uploaded_"
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=admin_deposit_detail_keyboard(o['id']))


# ════════════════════════════════════════════════════════════════
# 💰 SOLD ACCOUNTS — log of delivered accounts (auto-delete after 2 months)
# ════════════════════════════════════════════════════════════════

async def sold_accounts_callback(u, c):
    """💰 Paginated list of accounts that were delivered/sold."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    parts = q.data.replace("sold_accounts", "").lstrip("_")
    page = int(parts) if parts.isdigit() else 0

    from database import get_sold_accounts, count_sold_accounts, purge_expired_sold_accounts
    # Opportunistic cleanup whenever admin opens the screen
    try: purge_expired_sold_accounts(60)
    except Exception: pass

    per_page = 8
    total = count_sold_accounts()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    rows = get_sold_accounts(limit=per_page, offset=page * per_page)

    text = (f"💰 *Sold Accounts*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 Total sold: *{total}*\n"
            f"📄 Page {page+1}/{total_pages}\n"
            f"_Auto-deletes 2 months after sale._\n\n")

    if not rows:
        text += "📭 No accounts sold yet."
    else:
        text += "_Tap any to view full details:_\n\n"
        # 🆕 v80 BYTE-PERFECT FIX: don't escape_md() the account data — it
        # mangles _ * ` etc. Show it inline as-is but strip newlines to avoid
        # breaking the Markdown layout.
        for i, r in enumerate(rows, start=page*per_page+1):
            pname = escape_md((r['product_name'] or 'N/A')[:24])
            sold_at = r['sold_at'] or '—'
            prev = (r['account_data'] or '')[:34].replace('\n', ' ')
            # Escape ONLY the backtick because we're wrapping in `...` for
            # visual code style. Other chars (_ * / etc.) stay raw.
            prev_safe = prev.replace('`', "'")
            text += f"{i}. 📦 {pname}\n   `{prev_safe}`\n   🕒 {sold_at}\n\n"

    kb = []
    for r in rows:
        prev = (r['account_data'] or '')[:28].replace('\n', ' ')
        kb.append([InlineKeyboardButton(f"💰 {prev}", callback_data=f"sold_view_{r['id']}_{page}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"sold_accounts_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="bs_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"sold_accounts_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def sold_account_view_callback(u, c):
    """💰 Full detail of one sold account."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    raw = q.data.replace("sold_view_", "")
    bits = raw.split("_")
    aid = int(bits[0])
    page = int(bits[1]) if len(bits) > 1 and bits[1].isdigit() else 0

    from database import get_sold_account
    r = get_sold_account(aid)
    if not r:
        await q.answer("Not found (maybe auto-deleted)", show_alert=True)
        set_cb_data(u, f"sold_accounts_{page}")
        await sold_accounts_callback(u, c)
        return

    buyer = r['sold_to'] if ('sold_to' in r.keys() and r['sold_to']) else 'N/A'
    # 🆕 v80 BYTE-PERFECT FIX: switch to HTML mode so account_data can be
    # wrapped in <code>...</code> (preserves every byte). Previously used
    # Markdown ``` block + escape_md() which mangled _ * etc.
    from utils import html_code_block, html_escape_plain
    pname_safe = html_escape_plain(r['product_name'] or 'N/A')
    text = (
        f"[[HTML]]💰 <b>Sold Account #{r['id']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Product:</b> {pname_safe}\n"
        f"🛒 <b>Order:</b> #{r['order_id'] or '—'}\n"
        f"👤 <b>Buyer ID:</b> <code>{html_escape_plain(str(buyer))}</code>\n"
        f"🕒 <b>Sold at:</b> {html_escape_plain(str(r['sold_at'] or '—'))}\n"
        f"🗑️ <i>Auto-deletes 2 months after sale.</i>\n\n"
        f"📝 <b>Account Data:</b>\n{html_code_block(r['account_data'])}"
    )
    kb = [[InlineKeyboardButton("🔙 Back to Sold List", callback_data=f"sold_accounts_{page}")]]
    await _safe_edit(q, text, reply_markup=InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════════════════════════
# 🆕 v38: Navigation Target Picker Handler
# ════════════════════════════════════════════════════════════════
async def cb_nav_target_callback(u, c):
    """User picked a navigation target — store it and ask for location."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    target_id = q.data.replace("cbnav_", "")
    from button_system import get_nav_target
    target = get_nav_target(target_id)
    if not target:
        await q.answer("❌ Invalid target", show_alert=True); return
    c.user_data['cb_new_action'] = target_id  # store the target id
    await _safe_edit(q,
        f"✅ Navigation set to: {target['icon']} *{target['label']}*\n\n"
        "*Step 4/4:* Yeh button kahan show ho?",
        parse_mode="Markdown",
        reply_markup=cbtns_location_v2_keyboard(allow_submenus=True))


# ════════════════════════════════════════════════════════════════
# 📝 CATEGORIES & ITEMS EDITABLE MANAGEMENT MENU (Safer & Editable)
# ════════════════════════════════════════════════════════════════

EDIT_PRODUCT_VALUE = 950
EDIT_CATEGORY_VALUE = 951

# 🔧 BUG FIX #14: Edit single account - conversation state
EDIT_ACCOUNT_VALUE = 952


async def view_category_callback(u, c):
    """View a single category's details & options."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    cid = int(q.data.replace("viewcat_", ""))
    
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT * FROM categories WHERE id=?", (cid,))
    cat = cur.fetchone()
    if not cat:
        await q.answer("Category not found", show_alert=True); return
        
    cur.execute("SELECT COUNT(*) FROM products WHERE category_id=? AND is_active=1", (cid,))
    prod_count = cur.fetchone()[0]
    conn.close()

    text = (
        f"🏷️ *Category Details*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏷️ *Name:* {escape_md(cat['name'])}\n"
        f"🎨 *Emoji:* {cat['emoji']}\n"
        f"📊 *Contains:* {prod_count} active product(s)\n\n"
        f"_Select an action to modify this category:_"
    )
    
    kb = [
        [InlineKeyboardButton("✏️ Rename Category", callback_data=f"editcat_name_{cid}")],
        [InlineKeyboardButton("🎨 Change Emoji", callback_data=f"editcat_emoji_{cid}")],
        [InlineKeyboardButton("🗑️ Delete Category", callback_data=f"delcat_{cid}")],
        [InlineKeyboardButton("🔙 Back to Categories", callback_data="admin_categories")]
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def edit_category_field_callback(u, c):
    """Start editing a category field."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return ConversationHandler.END
    await q.answer()
    
    parts = q.data.replace("editcat_", "").split("_")
    field = parts[0]
    cid = int(parts[1])
    
    c.user_data['edit_cat_id'] = cid
    c.user_data['edit_cat_field'] = field
    
    prompt = "Type new Category Name:" if field == "name" else "Type/Send new Emoji:"
    await _safe_edit(q,
        f"✏️ *Edit Category {field.title()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{prompt}",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return EDIT_CATEGORY_VALUE


async def edit_category_field_received(u, c):
    """Save the edited category field value."""
    if u.effective_user.id != ADMIN_ID:
        return True
    cid = c.user_data.get('edit_cat_id')
    field = c.user_data.get('edit_cat_field')
    if not cid or not field:
        await u.message.reply_text("❌ Session lost.", reply_markup=back_btn())
        c.user_data.pop('edit_cat_id', None)
        c.user_data.pop('edit_cat_field', None)
        return True
        
    val = u.message.text.strip()
    
    conn = get_connection(); cur = conn.cursor()
    if field == 'name':
        if len(val) < 2:
            await u.message.reply_text("❌ Name too short.", reply_markup=inline_cancel_btn())
            return False
        cur.execute("UPDATE categories SET name=? WHERE id=?", (val, cid))
    elif field == 'emoji':
        cur.execute("UPDATE categories SET emoji=? WHERE id=?", (val[:5], cid))
        
    conn.commit(); conn.close()
    
    # 🆕 v53: capture FULL value with premium emoji entities for SAVE + ECHO.
    # Re-save with HTML form when admin typed premium emojis so DB has correct
    # value; also use it for the confirmation echo.
    from utils import safe_display, capture_user_text
    val_with_premium = capture_user_text(u.message) or val
    if val_with_premium != val and val_with_premium.startswith("[[HTML]]"):
        # Re-save with premium emoji preserved
        try:
            conn = get_connection(); cur = conn.cursor()
            if field == 'name':
                cur.execute("UPDATE categories SET name=? WHERE id=?", (val_with_premium, cid))
            conn.commit(); conn.close()
        except Exception:
            pass
    disp, disp_mode = safe_display(val_with_premium, preferred_mode="Markdown", message=u.message)
    if disp_mode == "HTML":
        await u.message.reply_text(
            f"✅ <b>Category Updated!</b>\n\n{field.title()} is now set to: {disp}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"viewcat_{cid}")]]))
    else:
        await u.message.reply_text(
            f"✅ *Category Updated!*\n\n{field.title()} is now set to: `{disp}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"viewcat_{cid}")]]))
        
    c.user_data.pop('edit_cat_id', None)
    c.user_data.pop('edit_cat_field', None)
    return True


async def delete_category_confirm_callback(u, c):
    """Show confirmation screen before deleting category."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    cid = int(q.data.replace("delcat_", ""))
    
    text = (
        f"⚠️ *DELETE CATEGORY — CONFIRM*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Are you sure you want to delete this category?\n\n"
        f"🚨 *WARNING:* All products inside this category will also be deleted!\n"
        f"This action cannot be undone."
    )
    kb = [
        [InlineKeyboardButton("✅ YES, Delete", callback_data=f"delcatdo_{cid}"),
         InlineKeyboardButton("❌ No, Cancel", callback_data=f"viewcat_{cid}")]
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def delete_category_do_callback(u, c):
    """Actually perform soft delete of category."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    cid = int(q.data.replace("delcatdo_", ""))
    
    delete_category(cid)
    await q.answer("Category deleted safely ✅")
    
    # Refresh categories view
    set_cb_data(u, "admin_categories")
    await admin_categories_callback(u, c)


# ── Products/Items ──


async def manual_hist_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: return
    pid = int(q.data.replace("manhist_", ""))
    
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE product_id=? AND status='delivered' AND delivery_content != '' ORDER BY id DESC LIMIT 15", (pid,))
    orders = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    if not orders:
        await q.answer("No manual deliveries found yet.", show_alert=True)
        return
        
    await q.answer()
    txt = "📜 *Recent Manual Deliveries*\n━━━━━━━━━━━━━━━━━━━━\nSelect an order to Edit its delivery text:\n"
    kb = []
    for o in orders:
        short_txt = o['delivery_content'][:15] + "..." if len(o['delivery_content']) > 15 else o['delivery_content']
        kb.append([InlineKeyboardButton(f"Order #{o['id']} - {short_txt}", callback_data=f"editman_{o['id']}")])
        
    kb.append([InlineKeyboardButton("🔙 Back to Settings", callback_data=f"delset_{pid}")])
    await _safe_edit(q, txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def edit_manual_order_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: return
    oid = int(q.data.replace("editman_", ""))
    
    from database import get_order
    o = get_order(oid)
    if not o: return
    
    c.user_data['editing_manual_oid'] = oid
    
    txt = f"✏️ *Editing Delivery for Order #{oid}*\n\n"
    txt += f"Current Text:\n`{o['delivery_content']}`\n\n"
    txt += f"Send the new corrected delivery text now. It will update invisibly for the user."
    
    await _safe_edit(q, txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"manhist_{o['product_id']}")]]))

async def manual_edit_received(update, context):
    oid = context.user_data.pop('editing_manual_oid', None)
    if not oid: return False
    
    new_text = update.message.text
    from database import get_order
    o = get_order(oid)
    if not o: return True
    
    # Update DB
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE orders SET delivery_content=? WHERE id=?", (new_text, oid))
    
    # Sync with product_accounts if it exists
    prefix = "[Own Mail] " if (dict(o) if o else {}).get('customer_credentials') else "[Manual] "
    # We update the sold account data where sold_to = user_id and added roughly same time.
    # A bit hard to match perfectly, but we can just try updating the most recent one for this user
    cur.execute("UPDATE product_accounts SET account_data=? WHERE product_id=? AND sold_to=? AND status='sold' AND id = (SELECT MAX(id) FROM product_accounts WHERE product_id=? AND sold_to=? AND status='sold')", (prefix + new_text, o['product_id'], o['user_id'], o['product_id'], o['user_id']))
    
    conn.commit(); conn.close()
    
    # Edit the Telegram message invisibly!
    if (dict(o) if o else {}).get('delivery_msg_id'):
        p = get_product(o['product_id']) if (dict(o) if o else {}).get('product_id') else None
        if (dict(o) if o else {}).get('customer_credentials'):
            # 🆕 v80 BYTE-PERFECT: HTML mode with <code> wrap preserves EVERY
            # character of the delivery text (was Markdown `...` which mangled _ * etc.)
            from utils import html_code_block, html_escape_plain
            pname_safe = html_escape_plain(o['product_name'])
            msg = ("[[HTML]]🎉 <b>Order Completed!</b>\n\n"
                   f"📦 <b>{pname_safe}</b>\n\n"
                   "✅ <b>Completed on your own account!</b>\n"
                   f"📝 <b>Details:</b>\n{html_code_block(new_text)}")
        else:
            fmt = normalize_product_format((dict(p) if p else {}).get('product_format', 'email_pass'))
            try:
                tpl = int((dict(p) if p else {}).get('delivery_template', 1) or 1)
            except Exception:
                tpl = 1
            msg = render_delivery_bundle([new_text], product_name=o['product_name'],
                                          product_format=fmt, template_id=tpl,
                                          order_id=oid,
                                          product_id=(o['product_id'] if o else 0))

        # 🆕 v72: use smart_text_and_mode so [[HTML]] sentinel switches parse_mode
        try:
            from utils import smart_text_and_mode
            send_text, send_mode = smart_text_and_mode(msg, "Markdown")
            await context.bot.edit_message_text(chat_id=o['user_id'],
                                                  message_id=o['delivery_msg_id'],
                                                  text=send_text,
                                                  parse_mode=send_mode)
        except Exception as e:
            pass # Could be too old to edit, or user deleted history
            
    await update.message.reply_text(f"✅ Order #{oid} updated successfully!")
    return True
async def delivery_settings_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = int(q.data.replace("delset_", ""))
    p = get_product(pid)

    dmode = (dict(p) if p else {}).get('delivery_mode', 'auto')
    acct = (dict(p) if p else {}).get('req_account_type', 'none')
    product_format = normalize_product_format((dict(p) if p else {}).get('product_format', 'email_pass'))
    try:
        template_id = int((dict(p) if p else {}).get('delivery_template', 1) or 1)
    except Exception:
        template_id = 1
    template_name = get_template_style(template_id)['name']

    mtype_label = "🤖 Auto"
    if dmode == 'manual':
        mtype_label = "✋ Manual (Readymade)" if acct == 'none' else "✋ Manual (Own Mail)"

    txt = (
        f"⚙️ *Delivery Settings: {escape_md(p['name'])}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 *Type:* {mtype_label}\n"
        f"🧩 *Format:* {delivery_format_label(product_format)}\n"
        f"🎁 *Template:* #{template_id} {escape_md(template_name)}\n\n"
        f"Choose an option below to change delivery behavior, format, or customer template:\n"
    )

    kb = [
        [InlineKeyboardButton(f"{'✅ ' if dmode=='auto' else ''}Auto Delivery", callback_data=f"ds_auto_{pid}")],
        [InlineKeyboardButton(f"{'✅ ' if dmode=='manual' and acct=='none' else ''}Manual Readymade", callback_data=f"ds_manready_{pid}")],
        [InlineKeyboardButton(f"{'✅ ' if dmode=='manual' and acct!='none' else ''}Manual Own Mail", callback_data=f"ds_manown_{pid}")],
        [InlineKeyboardButton(f"🧩 Change Format ({delivery_format_label(product_format)})", callback_data=f"dsfmtpick_{pid}")],
        [InlineKeyboardButton(f"🎁 Change Template (#{template_id} {template_name})", callback_data=f"dstplpick_{pid}")],
    ]

    if dmode == 'manual' and acct != 'none':
        lbl_in = 'Any Mail' if acct == 'any_mail' else ('Gmail Only' if acct == 'any_gmail' else 'Fresh Gmail')
        pwd = (dict(p) if p else {}).get('req_password', 0)
        kb.append([InlineKeyboardButton(f"Type: {lbl_in}", callback_data=f"ds_acct_{pid}")])
        kb.append([InlineKeyboardButton(f"Req Password: {'Yes' if pwd else 'No'}", callback_data=f"ds_pwd_{pid}")])

    if dmode == 'manual':
        kb.append([InlineKeyboardButton("📜 Edit Manual Deliveries", callback_data=f"manhist_{pid}")])

    kb.append([InlineKeyboardButton("🔙 Back to Product", callback_data=f"viewprod_{pid}")])
    await _safe_edit(q, txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def ds_toggle_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: return
    action, pid = q.data.replace("ds_", "").rsplit("_", 1)
    pid = int(pid)
    
    p = get_product(pid)
    conn = get_connection(); cur = conn.cursor()
    # 🔧 Self-heal: guarantee delivery-settings columns exist before updating,
    # so this never crashes with "no such column: delivery_mode" on old DBs.
    from database import ensure_column
    ensure_column(cur, "products", "delivery_mode", "TEXT DEFAULT 'auto'")
    ensure_column(cur, "products", "req_account_type", "TEXT DEFAULT 'none'")
    ensure_column(cur, "products", "req_password", "INTEGER DEFAULT 0")
    ensure_column(cur, "products", "req_fresh", "INTEGER DEFAULT 0")
    ensure_column(cur, "products", "product_format", "TEXT DEFAULT 'email_pass'")
    ensure_column(cur, "products", "delivery_template", "INTEGER DEFAULT 1")

    if action == "auto":
        cur.execute("UPDATE products SET delivery_mode='auto' WHERE id=?", (pid,))
    elif action == "manready":
        # 🔧 Issue #2: do NOT overwrite stock to 1,000,000 — keep admin-set stock.
        cur.execute("UPDATE products SET delivery_mode='manual', req_account_type='none' WHERE id=?", (pid,))
    elif action == "manown":
        cur.execute("UPDATE products SET delivery_mode='manual', req_account_type='any_mail', req_password=0 WHERE id=?", (pid,))
    elif action == "acct":
        curr = (dict(p) if p else {}).get('req_account_type', 'none')
        new_val = 'fresh_gmail' if curr == 'any_mail' else ('any_gmail' if curr == 'fresh_gmail' else 'any_mail')
        cur.execute("UPDATE products SET req_account_type=? WHERE id=?", (new_val, pid))
    elif action == "pwd":
        new_val = 0 if (dict(p) if p else {}).get('req_password') else 1
        cur.execute("UPDATE products SET req_password=? WHERE id=?", (new_val, pid))
        
    conn.commit(); conn.close()
    # Mock data to avoid AttributeError: Attribute 'data' of class 'CallbackQuery' can't be set!
    # Instead of setting q.data, we just override it in a temporary object if we wanted to,
    # but the easiest way is just to pass `pid` or extract it cleanly.
    # Actually, we can just set `u.callback_query.data` which is restricted.
    # Let's just create a new wrapper call or modify `delivery_settings_callback` to accept an explicit pid.
    # Even simpler: we can just manually build the view here, but it's redundant.
    # Best way: modify `delivery_settings_callback` to check `c.user_data['temp_pid']` maybe?
    
    # Or just mutate the private attribute:
    object.__setattr__(q, 'data', f"delset_{pid}")
    await delivery_settings_callback(u, c)


async def ds_format_pick_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = int(q.data.replace("dsfmtpick_", ""))
    p = get_product(pid)
    current = normalize_product_format((dict(p) if p else {}).get('product_format', 'email_pass'))
    rows = []
    for fmt in get_product_format_choices():
        mark = " ✅" if normalize_product_format(fmt) == current else ""
        rows.append([InlineKeyboardButton(f"{delivery_format_label(fmt)}{mark}", callback_data=f"dsfmt_{fmt}_{pid}")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data=f"delset_{pid}")])
    text = (
        f"🧩 *Product Format — {escape_md((dict(p) if p else {}).get('name', 'Product'))}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: *{delivery_format_label(current)}*\n\n"
        f"Whichever format you choose, stock upload + manual delivery will follow only that format."
    )
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))


async def ds_set_format_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    raw = q.data.replace("dsfmt_", "")
    fmt, pid_s = raw.rsplit("_", 1)
    pid = int(pid_s)
    fmt = normalize_product_format(fmt)
    conn = get_connection(); cur = conn.cursor()
    from database import ensure_column
    ensure_column(cur, "products", "product_format", "TEXT DEFAULT 'email_pass'")
    cur.execute("UPDATE products SET product_format=? WHERE id=?", (fmt, pid))
    conn.commit(); conn.close()
    await q.answer(f"Format updated: {delivery_format_label(fmt)}")
    set_cb_data(u, f"delset_{pid}")
    await delivery_settings_callback(u, c)


async def ds_template_pick_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = int(q.data.replace("dstplpick_", ""))
    p = get_product(pid)
    try:
        current = int((dict(p) if p else {}).get('delivery_template', 1) or 1)
    except Exception:
        current = 1
    rows = []
    for tid, name in get_template_choices():
        mark = " ✅" if tid == current else ""
        rows.append([InlineKeyboardButton(f"#{tid} {name}{mark}", callback_data=f"dstpl_{tid}_{pid}")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data=f"delset_{pid}")])
    text = (
        f"🎁 *Delivery Template Picker*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Choose one of 10 built-in *Bite Store* delivery templates.\n"
        f"This template will be used whenever this product is delivered automatically or manually."
    )
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))


async def ds_set_template_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    raw = q.data.replace("dstpl_", "")
    tid_s, pid_s = raw.rsplit("_", 1)
    pid = int(pid_s)
    tid = int(tid_s)
    conn = get_connection(); cur = conn.cursor()
    from database import ensure_column
    ensure_column(cur, "products", "delivery_template", "INTEGER DEFAULT 1")
    cur.execute("UPDATE products SET delivery_template=? WHERE id=?", (tid, pid))
    conn.commit(); conn.close()
    await q.answer(f"Template set: #{tid} {get_template_style(tid)['name']}")
    set_cb_data(u, f"delset_{pid}")
    await delivery_settings_callback(u, c)


async def view_product_callback(u, c):
    """View details and options for editing a single product."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = int(q.data.replace("viewprod_", ""))
    
    p = get_product(pid)
    if not p:
        await q.answer("Product not found", show_alert=True); return
        
    # 🆕 Account pool stats
    from database import count_product_accounts
    acct_available = count_product_accounts(pid, 'available')
    acct_sold = count_product_accounts(pid, 'sold')
    acct_total = count_product_accounts(pid, 'all')
    
    product_format = normalize_product_format(dict(p).get('product_format', 'email_pass'))
    template_id = int(dict(p).get('delivery_template', 1) or 1)
    dmode_label = '✋ Manual' if dict(p).get('delivery_mode') == 'manual' else '🤖 Auto Delivery'
    is_active_now = int(dict(p).get('is_active', 1) or 0) == 1
    active_label = '✅ Active' if is_active_now else '🚫 Deactivated'
    hidden_label = '🙈 Hidden from Shop' if is_product_hidden(pid) else '👁️ Visible in Shop'
    try:
        from handlers_shop import _clean_product_description as _shop_clean_desc, _build_display_note as _shop_display_note
        clean_desc = _shop_clean_desc(p['description'])
        display_note = _shop_display_note(p['description'], dict(p).get('customer_note', ''))
    except Exception:
        clean_desc = p['description']
        display_note = dict(p).get('customer_note', '')
    # 🆕 v170.11: supplier name (product kis supplier se link hai) — admin ko
    # edit items mein dikhta hai. Customer ko kabhi nahi.
    supplier_line = ""
    try:
        _esid = int(dict(p).get("ext_supplier_id") or 0)
        if _esid:
            from database import get_connection as _gc3
            _conn3 = _gc3(); _c3 = _conn3.cursor()
            _c3.execute("SELECT name FROM ext_suppliers WHERE id=?", (_esid,))
            _r3 = _c3.fetchone(); _conn3.close()
            if _r3:
                _sname = str((dict(_r3) if not isinstance(_r3, dict) else _r3).get("name") or "")
                if _sname:
                    supplier_line = f"🏭 *Supplier:* {escape_md(_sname)}\n"
    except Exception:
        supplier_line = ""

    text = (
        f"📦 *Product Details*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 *Name:* {escape_md(p['name'])}\n"
        f"🚦 *Status:* {active_label} | {hidden_label}\n"
        f"{supplier_line}"
        f"📦 *Delivery Type:* {dmode_label}\n"
        f"🧩 *Format:* {delivery_format_label(product_format)}\n"
        f"🎁 *Template:* #{template_id} {escape_md(get_template_style(template_id)['name'])}\n"
        f"💰 *Selling Price:* {fmt_price(p['price'])}\n"
        f"💵 *Cost Price:* {fmt_price(p['cost_price'])}\n"
        f"📊 *Stock:* {p['stock']}\n"
        f"🛡️ *Warranty:* {escape_md(p['warranty']) or 'None'}\n"
        f"🔢 *Min Order Qty:* {escape_md(str(p['quantity'])) or '1'}\n"
        f"🔥 *Sold (shown):* {int(dict(p).get('fake_sold',0) or 0) + int(dict(p).get('real_sold',0) or 0)} "
        f"_(fake {int(dict(p).get('fake_sold',0) or 0)} + real {int(dict(p).get('real_sold',0) or 0)})_\n\n"
        f"📌 *Customer Note (single display):*\n"
        f"{escape_md(display_note) or 'None'}\n\n"
        f"📝 *Description (clean display):*\n"
        f"{escape_md(clean_desc) or 'None'}\n\n"
        f"📨 *Account Pool* (customer gets 1 account per order):\n"
        f"✅ Available: *{acct_available}* | 💰 Sold: *{acct_sold}* | 📊 Total: *{acct_total}*\n"
        f"_{'Ready — sells one account at a time.' if acct_available > 0 else '⚠️ No accounts left! Add via Manage Accounts.'}_"
    )
    
    kb = [
        [InlineKeyboardButton("✏️ Edit Name", callback_data=f"editfield_name_{pid}"),
         InlineKeyboardButton("📝 Edit Description", callback_data=f"editfield_description_{pid}")],
        [InlineKeyboardButton("📌 Edit Customer Note", callback_data=f"editfield_customernote_{pid}")],
        [InlineKeyboardButton("💰 Edit Price", callback_data=f"editfield_price_{pid}"),
         InlineKeyboardButton("💵 Edit Cost Price", callback_data=f"editfield_costprice_{pid}")],
        [InlineKeyboardButton("🛡️ Edit Warranty", callback_data=f"editfield_warranty_{pid}"),
         InlineKeyboardButton("🔢 Edit Min Qty", callback_data=f"editfield_quantity_{pid}")],
        # 🔧 Issue #4: Edit Stock button (change stock value after creation)
        [InlineKeyboardButton(f"📊 Edit Stock ({dict(p).get('stock',0)})", callback_data=f"editfield_stock_{pid}")],
        # 🆕 Fake sold base counter
        [InlineKeyboardButton(f"🔥 Edit Fake Sold ({dict(p).get('fake_sold',0)})", callback_data=f"editfield_fakesold_{pid}")],
        [InlineKeyboardButton("🔗 Edit Static Delivery Text", callback_data=f"editfield_deliverytext_{pid}")],
        [InlineKeyboardButton(f"📋 Manage Accounts ({acct_available})", callback_data=f"prodaccounts_manage_{pid}")],
        [InlineKeyboardButton("⚙️ Delivery Settings", callback_data=f"delset_{pid}")],
        [InlineKeyboardButton(f"⚡ Flash Sale: {'ON ($'+str(dict(p).get('flash_price',0))+')' if dict(p).get('is_flash_sale',0) else 'OFF'}", callback_data=f"flashtoggle_{pid}")],
        # 🆕 v47: Free-via-Referrals per-product config
        [InlineKeyboardButton(
            f"🎁 Free via Referrals: {'🟢 ON' if _fc_is_enabled(pid) else '🔴 OFF'}",
            callback_data=f"fcrf_panel_{pid}")],
        # 🆕 v59: Hide / Unhide toggle (different from delete — keeps product safe)
        [InlineKeyboardButton(
            f"{'👁️ Show Product (currently HIDDEN)' if is_product_hidden(pid) else '🙈 Hide Product from Shop'}",
            callback_data=f"prodhide_{pid}")],
        # 🆕 v170.5: fake-activity OFF flag (sirf real purchase par broadcast hoga)
        [InlineKeyboardButton(
            f"{'🎭 Fake Activity: 🚫 OFF' if is_product_fake_off(pid) else '🎭 Fake Activity: ✅ ON'}",
            callback_data=f"prodfake_{pid}")],
        # 🆕 v71: Replacement window — per-product setting
        [_v71_replacement_window_button(pid)],
    ]
    kb.append([InlineKeyboardButton("🗑️ Delete Product", callback_data=f"delprod_{pid}")])
    kb.extend([
        [InlineKeyboardButton("🔙 Back to Add Products", callback_data="admin_products")]
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def toggle_product_active_callback(u, c):
    """Admin-only activate/reactivate product without deleting DB data."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        raw = q.data.replace("prodactive_", "")
        active_s, pid_s = raw.split("_", 1)
        active = bool(int(active_s))
        pid = int(pid_s)
    except Exception:
        await q.answer("❌ Bad product id", show_alert=True); return
    set_product_active(pid, active)
    await q.answer("✅ Product reactivated" if active else "🚫 Product deactivated", show_alert=False)
    set_cb_data(u, f"viewprod_{pid}")
    await view_product_callback(u, c)


# 🆕 v59: Toggle product hide/unhide
async def toggle_product_hidden_callback(u, c):
    """Toggle product visibility for users (hide/unhide without deleting)."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        pid = int(q.data.replace("prodhide_", ""))
    except Exception:
        await q.answer("❌ Bad id", show_alert=True); return
    currently_hidden = is_product_hidden(pid)
    set_product_hidden(pid, not currently_hidden)
    new_state = not currently_hidden
    msg = "🙈 Product HIDDEN from shop" if new_state else "👁️ Product VISIBLE in shop"
    await q.answer(f"{msg} ✅", show_alert=False)
    # Refresh the product view
    set_cb_data(u, f"viewprod_{pid}")
    await view_product_callback(u, c)


async def toggle_product_fake_off_callback(u, c):
    """🆕 v170.5: toggle fake-activity OFF for a product. Jab OFF → fake
    activity (global + per-user) is product ko broadcast nahi karti, sirf
    REAL purchase ka alert jata hai."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        pid = int(q.data.replace("prodfake_", ""))
    except Exception:
        await q.answer("❌ Bad id", show_alert=True); return
    try:
        from database import is_product_fake_off, set_product_fake_off
        new_state = not is_product_fake_off(pid)
        set_product_fake_off(pid, new_state)
        await q.answer(f"🎭 Fake Activity {'🚫 OFF' if new_state else '✅ ON'} ✅", show_alert=False)
    except Exception:
        await q.answer("❌ Failed to update", show_alert=True); return
    set_cb_data(u, f"viewprod_{pid}")
    await view_product_callback(u, c)


# ════════════════════════════════════════════════════════════════
# 📋 PRODUCT ACCOUNTS MANAGEMENT
# ════════════════════════════════════════════════════════════════

async def manage_product_accounts_callback(u, c):
    """📋 Main account management screen for a product."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = int(q.data.replace("prodaccounts_manage_", ""))
    
    from database import count_product_accounts
    av = count_product_accounts(pid, 'available')
    so = count_product_accounts(pid, 'sold')
    to = count_product_accounts(pid, 'all')
    bonus_av = manual_av = other_av = 0
    try:
        conn = get_connection(); cur = conn.cursor()
        ensure_product_accounts_table(cur)
        cur.execute("""SELECT COALESCE(source,'manual') AS src, COUNT(*) AS n
                       FROM product_accounts
                       WHERE product_id=? AND status='available'
                       GROUP BY COALESCE(source,'manual')""", (pid,))
        for rr in cur.fetchall():
            src = (rr['src'] if hasattr(rr, 'keys') else rr[0]) or 'manual'
            n = int((rr['n'] if hasattr(rr, 'keys') else rr[1]) or 0)
            if src == 'supplier_bonus': bonus_av += n
            elif src == 'manual': manual_av += n
            else: other_av += n
        conn.close()
    except Exception:
        pass
    
    p = get_product(pid)
    pname = escape_md(p['name']) if p else f"#{pid}"
    
    fmt = normalize_product_format((dict(p) if p else {}).get('product_format', 'email_pass')) if p else 'email_pass'
    text = (
        f"📋 *Account Pool: {pname}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ *Available:* {av}\n"
        f"💰 *Sold:* {so}\n"
        f"📊 *Total:* {to}\n"
        f"🎁 *Supplier Bonus Pool:* {bonus_av}\n"
        f"✍️ *Manual Pool:* {manual_av}\n"
        + (f"📦 *Other Pool:* {other_av}\n" if other_av else "") +
        f"🧩 *Expected Format:* {delivery_format_label(fmt)}\n"
        f"📌 *Upload Rule:* {escape_md(delivery_format_hint(fmt))}\n\n"
        f"_When order is approved, bot auto-picks one available account._\n"
        f"_If pool is empty, 'Delivery Text' is sent instead._"
    )
    kb = [
        [InlineKeyboardButton("➕ Add Accounts (Bulk)", callback_data=f"editfield_accounts_{pid}")],
        [InlineKeyboardButton("📋 Show All Accounts", callback_data=f"prodaccounts_show_{pid}_0")],
        [InlineKeyboardButton("🗑️ Delete All Accounts", callback_data=f"prodaccounts_delall_confirm_{pid}")],
        [InlineKeyboardButton("🔙 Back to Product", callback_data=f"viewprod_{pid}")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def show_product_accounts_callback(u, c):
    """📋 Paginated list of all accounts for a product."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    
    parts = q.data.replace("prodaccounts_show_", "").split("_")
    pid = int(parts[0])
    page = int(parts[1]) if len(parts) > 1 else 0
    
    from database import get_product_accounts, count_product_accounts
    per_page = 10
    total = count_product_accounts(pid, 'all')
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    accounts = get_product_accounts(pid, status='all', limit=per_page, offset=page * per_page)
    
    p = get_product(pid)
    pname = escape_md(p['name']) if p else f"#{pid}"
    
    text = f"📋 *Accounts: {pname}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"📄 Page {page + 1}/{total_pages} (Total: {total})\n\n"
    text += "_Tap any account to view/edit/delete it._\n\n"
    
    if not accounts:
        text += "📭 *No accounts yet.*\n\nTap ➕ Add Accounts to upload."
    else:
        # 🆕 v80 BYTE-PERFECT: skip escape_md() on account_data — was mangling
        # _ * ` etc. Just replace backticks (Markdown code delimiter) with '.
        for i, acct in enumerate(accounts, start=page * per_page + 1):
            status = "✅" if acct['status'] == 'available' else "💰 Sold"
            data_preview = acct['account_data'][:50].replace('`', "'").replace('\n', ' ')
            if len(acct['account_data']) > 50:
                data_preview += "…"
            text += f"{i}. {status}\n`{data_preview}`\n\n"
    
    kb = []
    for acct in accounts:
        data_preview = acct['account_data'][:30].replace('\n', ' ')
        status = "✅" if acct['status'] == 'available' else "💰"
        kb.append([InlineKeyboardButton(
            f"{status} {data_preview}",
            callback_data=f"prodaccount_view_{acct['id']}_{pid}_{page}"
        )])
    
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"prodaccounts_show_{pid}_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="bs_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"prodaccounts_show_{pid}_{page+1}"))
    if nav:
        kb.append(nav)
    
    kb.append([InlineKeyboardButton("➕ Add Accounts", callback_data=f"editfield_accounts_{pid}")])
    kb.append([InlineKeyboardButton("🗑️ Delete All", callback_data=f"prodaccounts_delall_confirm_{pid}")])
    kb.append([InlineKeyboardButton("🔙 Back to Pool", callback_data=f"prodaccounts_manage_{pid}")])
    
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def delete_single_account_callback(u, c):
    """Delete one account by id."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    
    # Parse: prodaccounts_delone_<account_id>_<pid>
    raw = q.data.replace("prodaccounts_delone_", "")
    parts = raw.rsplit("_", 1)
    if len(parts) != 2:
        await q.answer("❌ Invalid", show_alert=True); return
    aid = int(parts[0])
    pid = int(parts[1])
    
    from database import delete_product_account
    delete_product_account(aid)
    await q.answer("🗑️ Account deleted ✅")
    
    # Refresh show screen
    set_cb_data(u, f"prodaccounts_show_{pid}_0")
    await show_product_accounts_callback(u, c)


async def toggle_delivery_mode_callback(u, c):
    """Automation-only mode — always keep products on auto delivery."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    pid = int(q.data.replace("togglemode_", ""))
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("UPDATE products SET delivery_mode='auto' WHERE id=?", (pid,))
        conn.commit(); conn.close()
    except Exception:
        pass
    await q.answer("Manual delivery removed — product kept on Auto ✅", show_alert=True)
    set_cb_data(u, f"viewprod_{pid}")
    await view_product_callback(u, c)


async def delete_product_confirm_callback(u, c):
    """Show confirmation screen before deleting product."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = int(q.data.replace("delprod_", ""))
    
    text = (
        f"⚠️ *DELETE PRODUCT — CONFIRM*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Are you sure you want to delete this product from the shop?\n\n"
        f"✅ Old orders, profit history, and customer history will stay safe.\n"
        f"ℹ️ This is a safe soft-delete: product disappears from users but remains in DB."
    )
    kb = [
        [InlineKeyboardButton("✅ YES, Delete", callback_data=f"delproddo_{pid}"),
         InlineKeyboardButton("❌ No, Cancel", callback_data=f"viewprod_{pid}")]
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def delete_product_do_callback(u, c):
    """Permanently remove product from shop/admin, keep orders history."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = int(q.data.replace("delproddo_", ""))
    
    delete_product_permanently(pid)
    await q.answer("Product deleted from shop/admin ✅")
    
    # Refresh items view
    set_cb_data(u, "admin_products")
    await admin_products_callback(u, c)


async def bulk_price_start_callback(u, c):
    q=u.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer(); c.user_data['bulk_price_products']=set(); await _bulk_price_screen(u,c,0)

async def _bulk_price_screen(u,c,page=0):
    q=u.callback_query; selected=c.user_data.setdefault('bulk_price_products',set())
    selected={int(x) for x in selected}; c.user_data['bulk_price_products']=selected
    products=list(get_all_products(include_hidden=True, include_inactive=True)); per=12
    pages=max(1,(len(products)+per-1)//per); page=max(0,min(int(page or 0),pages-1)); chunk=products[page*per:(page+1)*per]
    text=f"💰 *Bulk Price Editor*\n━━━━━━━━━━━━━━━━━━━━\nSelected: *{len(selected)}*\nPage: *{page+1}/{pages}*\n\nSelect products, then choose price action."
    kb=[]
    for p in chunk:
        pid=int(p['id'])
        name = (p['name'] or f'#{pid}').replace('\n',' ')
        # 🐛 v158 FIX: strip raw [[HTML]]/<tg-emoji> markup (same as bulk discount)
        try:
            from utils import html_strip_tags
            name = html_strip_tags(name)
        except Exception:
            import re as _reh
            name = _reh.sub(r'<[^>]+>', '', name).replace('[[HTML]]', '').strip()
        name = (name or f'#{pid}').strip()
        if len(name)>54: name=name[:51]+'...'
        kb.append([InlineKeyboardButton(("✅" if pid in selected else "☐")+" "+name, callback_data=f"bulkprice_tgl_{pid}_{page}")])
    nav=[]
    if page>0: nav.append(InlineKeyboardButton('⬅️ Prev', callback_data=f'bulkprice_page_{page-1}'))
    if page<pages-1: nav.append(InlineKeyboardButton('Next ➡️', callback_data=f'bulkprice_page_{page+1}'))
    if nav: kb.append(nav)
    if selected:
        kb.append([InlineKeyboardButton('📈 +10%', callback_data='bulkprice_apply_10'), InlineKeyboardButton('📉 -10%', callback_data='bulkprice_apply_-10')])
        kb.append([InlineKeyboardButton('✏️ Custom %', callback_data='bulkprice_custom')])
    kb.append([InlineKeyboardButton('❌ Cancel', callback_data='admin_products')])
    await _safe_edit(q,text,parse_mode='Markdown',reply_markup=InlineKeyboardMarkup(kb))

async def bulk_price_toggle_callback(u,c):
    q=u.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    raw=q.data.replace('bulkprice_tgl_',''); pid_s,page_s=raw.rsplit('_',1); pid=int(pid_s); page=int(page_s)
    selected=c.user_data.setdefault('bulk_price_products',set()); selected={int(x) for x in selected}
    if pid in selected: selected.remove(pid); await q.answer('Removed')
    else: selected.add(pid); await q.answer('Selected')
    c.user_data['bulk_price_products']=selected; await _bulk_price_screen(u,c,page)

async def bulk_price_page_callback(u,c):
    q=u.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer(); await _bulk_price_screen(u,c,int(q.data.replace('bulkprice_page_','') or 0))

async def bulk_price_custom_callback(u,c):
    q=u.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer(); c.user_data['bulk_price_step']='custom_percent'
    await _safe_edit(q,'✏️ Send percentage change. Example: `15` or `-7.5`',parse_mode='Markdown',reply_markup=inline_cancel_btn())

async def bulk_price_custom_received(update, context):
    if update.effective_user.id != ADMIN_ID or context.user_data.get('bulk_price_step')!='custom_percent': return False
    try: pct=float((update.message.text or '').strip())
    except Exception:
        await update.message.reply_text('❌ Invalid percent. Example: 10 or -5'); return True
    context.user_data.pop('bulk_price_step',None)
    await _apply_bulk_price(update, context, pct)
    return True

async def bulk_price_apply_callback(u,c):
    q=u.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    try: pct=float(q.data.replace('bulkprice_apply_',''))
    except Exception: await q.answer('Bad percent',show_alert=True); return
    await q.answer('Applying...'); await _apply_bulk_price(u,c,pct,query=q)

async def _apply_bulk_price(update, context, pct, query=None):
    selected=sorted({int(x) for x in (context.user_data.pop('bulk_price_products',set()) or set())})
    if not selected:
        msg='❌ No products selected.'
        if query: await _safe_edit(query,msg,reply_markup=admin_products_keyboard(get_all_products(include_hidden=True, include_inactive=True)))
        else: await update.message.reply_text(msg)
        return
    conn=get_connection(); cur=conn.cursor(); changed=[]
    for pid in selected:
        try:
            p=get_product(pid)
            if not p: continue
            old=float(p['price'] or 0); new=max(0.0001, old*(1+pct/100.0))
            cur.execute('UPDATE products SET price=? WHERE id=?',(new,pid))
            try:
                if int((dict(p).get('ext_product_id') or 0)):
                    cur.execute('UPDATE ext_products SET sell_price=? WHERE id=?',(new,int(dict(p).get('ext_product_id'))))
            except Exception: pass
            changed.append((pid,p['name'],old,new))
        except Exception: pass
    conn.commit(); conn.close()
    lines=[f"✅ *Bulk Price Updated*", f"Change: `{pct:+.2f}%`", f"Products: *{len(changed)}*", ""]
    for _pid,name,old,new in changed[:10]: lines.append(f"• {escape_md(str(name)[:45])}: `${old:.4f}` → `${new:.4f}`")
    text='\n'.join(lines)
    if query: await _safe_edit(query,text,parse_mode='Markdown',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🛍️ Back to Edit Items',callback_data='admin_products')]]))
    else: await update.message.reply_text(text,parse_mode='Markdown',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🛍️ Back to Edit Items',callback_data='admin_products')]]))


async def edit_product_field_callback(u, c):
    """Start editing a specific field of the product."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    
    parts = q.data.replace("editfield_", "").split("_")
    field = parts[0]
    pid = int(parts[1])
    
    c.user_data['edit_pid'] = pid
    c.user_data['edit_field'] = field
    p = get_product(pid)
    prod_format = normalize_product_format((dict(p) if p else {}).get('product_format', 'email_pass'))

    hints = {
        "name": ("Enter new Item Name:\n\n"
                 "⭐ *Premium / Custom Emojis supported here!*\n"
                 "_Type the name normally and insert premium emojis from "
                 "Telegram's emoji picker — they'll show up on the product "
                 "detail page. (In the shop list buttons only the fallback "
                 "standard emoji shows, because Telegram doesn't support "
                 "custom emojis inside button labels.)_"),
        "description": "Enter new Description text:",
        "price": "Enter Selling Price (numbers only, e.g. `5.99`):",
        "costprice": "Enter Cost Price (numbers only, e.g. `2.50`):",
        "stock": "Enter Stock Count (numbers only, e.g. `10`):",
        "fakesold": "Enter the *fake base sold count* (number, e.g. `5`).\nDisplayed sold = this + real purchases. Real sales keep counting up from here.",
        "warranty": "Enter Warranty text (e.g. `30 Days`):",
        "quantity": "Enter the *minimum order quantity* (a number, e.g. `5`). Customer must order at least this many:",
        "deliverytext": "Send new Static Delivery (text/photo/video/voice/file). Used if account pool is empty:",
        "accounts": (
            f"📋 *Paste stock items — one per line.*\n\n"
            f"🧩 *Required Format:* {delivery_format_label(prod_format)}\n"
            f"📌 *Rule:* {delivery_format_hint(prod_format)}\n\n"
            f"*Example:*\n```\n{delivery_format_example(prod_format)}\n```\n\n"
            f"_Har line = 1 item. Wrong-format ya duplicate lines skip ho jayengi._"
        )
    }
    hint = hints.get(field, "Enter new value:")

    # 🆕 Show the CURRENT value so admin can see what's already saved
    current_block = ""
    if field != 'accounts':
        if p:
            from utils import fmt_price as _fp1708
            field_map = {
                "name": p['name'], "description": p['description'], "customernote": dict(p).get('customer_note',''),
                "price": _fp1708(p['price']), "costprice": _fp1708(p['cost_price']),
                "stock": str(p['stock']), "warranty": p['warranty'],
                "quantity": p['quantity'], "deliverytext": p['delivery_text'],
            }
            cur_val = field_map.get(field, "")
            if cur_val:
                current_block = f"📌 *Current:*\n```\n{cur_val}\n```\n\n"
            else:
                current_block = "📌 *Current:* _empty_\n\n"

    await _safe_edit(q,
        f"✏️ *Edit Product {field.title()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{current_block}"
        f"📥 {hint}",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())


async def edit_product_field_received(u, c):
    """Receive and save the product field change."""
    if u.effective_user.id != ADMIN_ID:
        return True
    pid = c.user_data.get('edit_pid')
    field = c.user_data.get('edit_field')
    if not pid or not field:
        await u.message.reply_text("❌ Session lost.", reply_markup=back_btn())
        c.user_data.pop('edit_pid', None)
        c.user_data.pop('edit_field', None)
        return True
        
    # 🆕 v72 BUG FIX: For fields where every byte matters (delivery_text,
    # accounts), use RAW input. For numeric/identifier fields, strip is fine.
    _raw_input = u.message.text or ""
    _byte_perfect_fields = {'deliverytext', 'accounts'}
    if field in _byte_perfect_fields:
        val = _raw_input   # preserve admin's exact bytes including whitespace
    else:
        val = _raw_input.strip()
    
    # 🆕 Special: accounts bulk add (format: email|password or links per line)
    if field == 'accounts':
        from database import add_product_accounts_bulk, count_product_accounts, sync_product_stock_from_accounts
        # NOTE: don't .strip() the whole block — we need each line; pass raw text
        raw_text = u.message.text
        added, skipped, bad_lines = add_product_accounts_bulk(pid, raw_text)
        sync_product_stock_from_accounts(pid)
        total_now = count_product_accounts(pid, 'available')
        old_p = get_product(pid)
        _old_stock_bulk = int(dict(old_p).get('stock', 0) or 0)
        if _old_stock_bulk <= 0 and total_now > 0:
            import asyncio
            asyncio.create_task(trigger_stock_alerts(pid, c.bot, old_p['name']))
        # 🆕 v96: also fire global restock broadcast when bulk-add raised stock
        if total_now > _old_stock_bulk:
            try:
                import asyncio
                from restock_alerts import fire_restock_alert
                _added = total_now - _old_stock_bulk
                asyncio.create_task(
                    fire_restock_alert(c.bot, pid, _added, total_now)
                )
            except Exception as _rea:
                print(f"[bulk accounts add] restock broadcast fail pid={pid}: {_rea}")

        msg = (
            f"✅ *Accounts Added!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📥 Added: *{added}* new accounts\n"
            f"🔁 Skipped (duplicate/empty): *{skipped}*\n"
            f"📊 Available pool now: *{total_now}*\n"
        )
        if bad_lines:
            preview = "\n".join(escape_md(b[:40]) for b in bad_lines[:5])
            more = f"\n…+{len(bad_lines)-5} more" if len(bad_lines) > 5 else ""
            current_fmt = normalize_product_format((dict(get_product(pid)) if get_product(pid) else {}).get('product_format', 'email_pass'))
            msg += (f"\n⚠️ *Wrong format ({len(bad_lines)}) — NOT added:*\n"
                    f"`{preview}`{more}\n\n"
                    f"_Required format:_ `{delivery_format_example(current_fmt)}`")
        await u.message.reply_text(
            msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Pool", callback_data=f"prodaccounts_manage_{pid}")]]))
        c.user_data.pop('edit_pid', None)
        c.user_data.pop('edit_field', None)
        return True
    
    conn = get_connection(); cur = conn.cursor()
    error_msg = None
    
    try:
        if field == 'name':
            # 🆕 v42: Capture HTML version (with custom_emoji entities) for premium emoji support
            try:
                html_v = (u.message.text_html_urled or "").strip()
            except Exception:
                html_v = ""
            has_custom_emoji = any(getattr(e, "type", "") == "custom_emoji"
                                   for e in (u.message.entities or []))
            if html_v and has_custom_emoji:
                val = "[[HTML]]" + html_v
            cur.execute("UPDATE products SET name=? WHERE id=?", (val, pid))
        elif field == 'description':
            try:
                html_v = (u.message.text_html_urled or "").strip()
            except Exception:
                html_v = ""
            if html_v and has_premium_emoji(u.message):
                val = "[[HTML]]" + html_v
            cur.execute("UPDATE products SET description=? WHERE id=?", (val, pid))
        elif field == 'customernote':
            if val.strip() == '-':
                val = ''
            else:
                try:
                    from utils import capture_user_text
                    val = capture_user_text(u.message) or val
                except Exception:
                    pass
            from database import ensure_column
            ensure_column(cur, "products", "customer_note", "TEXT DEFAULT ''")
            cur.execute("UPDATE products SET customer_note=? WHERE id=?", (val, pid))
        elif field == 'price':
            num = float(val.replace('$','').replace(',','').strip())
            # 🆕 v66: capture OLD price so we can offer a price-drop broadcast
            try:
                _old_p_row = get_product(pid)
                _v66_old_price = float(_old_p_row['price']) if _old_p_row else 0.0
            except Exception:
                _v66_old_price = 0.0
            cur.execute("UPDATE products SET price=? WHERE id=?", (num, pid))
            # Stash for use AFTER the success message
            if _v66_old_price > 0 and num < _v66_old_price:
                c.user_data['_v66_pdrop_pid']       = pid
                c.user_data['_v66_pdrop_old_price'] = _v66_old_price
                c.user_data['_v66_pdrop_new_price'] = num
        elif field == 'costprice':
            num = float(val.replace('$','').replace(',','').strip())
            cur.execute("UPDATE products SET cost_price=? WHERE id=?", (num, pid))
        elif field == 'stock':
            num = int(val.strip())
            # Check for stock alert trigger
            old_p = get_product(pid)
            old_stock = int(dict(old_p).get('stock', 0) or 0)
            if old_stock <= 0 and num > 0:
                import asyncio
                asyncio.create_task(trigger_stock_alerts(pid, c.bot, old_p['name']))
            cur.execute("UPDATE products SET stock=? WHERE id=?", (num, pid))
            # 🆕 v96: also fire GLOBAL restock broadcast when stock increased,
            # regardless of whether product is admin-owned or supplier-sourced.
            # Previously ONLY per-user subscribed alerts fired for manual edits;
            # supplier auto-sync fired the global broadcast. Now both paths do.
            if num > old_stock:
                try:
                    import asyncio
                    from restock_alerts import fire_restock_alert
                    added = num - old_stock
                    asyncio.create_task(
                        fire_restock_alert(c.bot, pid, added, num)
                    )
                except Exception as _rea:
                    print(f"[manual stock edit] restock broadcast fail pid={pid}: {_rea}")
        elif field == 'fakesold':
            # 🆕 Fake base sold counter (number >= 0)
            n = int(str(val).strip())
            if n < 0:
                raise ValueError("Fake sold count cannot be negative")
            from database import ensure_column
            ensure_column(cur, "products", "fake_sold", "INTEGER DEFAULT 0")
            cur.execute("UPDATE products SET fake_sold=? WHERE id=?", (n, pid))
        elif field == 'warranty':
            try:
                html_v = (u.message.text_html_urled or "").strip()
            except Exception:
                html_v = ""
            if html_v and has_premium_emoji(u.message):
                val = "[[HTML]]" + html_v
            cur.execute("UPDATE products SET warranty=? WHERE id=?", (val, pid))
        elif field == 'quantity':
            # 🆕 quantity = minimum order quantity (number, >= 1)
            n = int(str(val).strip())
            if n < 1:
                raise ValueError("Minimum quantity must be at least 1")
            cur.execute("UPDATE products SET quantity=? WHERE id=?", (str(n), pid))
        elif field == 'deliverytext':
            # 🆕 v72 BUG FIX: preserve admin's exact bytes (no .strip() on html)
            # `val` is already byte-perfect (set above via _byte_perfect_fields path)
            if val.strip() == '-':
                val = ''
            else:
                # Only switch to HTML form if premium emoji entities are present
                try:
                    html_v = u.message.text_html_urled or ""
                except Exception:
                    html_v = ""
                if html_v and has_premium_emoji(u.message):
                    val = "[[HTML]]" + html_v
            from database import ensure_column
            ensure_column(cur, "products", "delivery_file_id", "TEXT DEFAULT ''")
            ensure_column(cur, "products", "delivery_file_type", "TEXT DEFAULT ''")
            ensure_column(cur, "products", "delivery_file_name", "TEXT DEFAULT ''")
            ensure_column(cur, "products", "delivery_caption", "TEXT DEFAULT ''")
            cur.execute("""UPDATE products
                           SET delivery_text=?, delivery_file_id='', delivery_file_type='',
                               delivery_file_name='', delivery_caption=''
                           WHERE id=?""", (val, pid))
            if val:
                cur.execute("UPDATE products SET stock=1000000 WHERE id=?", (pid,))
        elif field == 'flashprice':
            num = float(val.replace('$','').replace(',','').strip())
            if num <= 0:
                raise ValueError("Flash price must be greater than 0")
            # 🔧 Self-heal: guarantee flash-sale columns exist before updating,
            # so this never fails with "no such column: is_flash_sale".
            from database import ensure_column
            ensure_column(cur, "products", "is_flash_sale", "INTEGER DEFAULT 0")
            ensure_column(cur, "products", "flash_price", "REAL DEFAULT 0.0")
            cur.execute("UPDATE products SET is_flash_sale=1, flash_price=? WHERE id=?", (num, pid))
    except Exception as e:
        error_msg = f"❌ Invalid value! ({str(e)})"
        
    if error_msg:
        await u.message.reply_text(error_msg, reply_markup=inline_cancel_btn())
        return False  # Stay in edit mode
        
    conn.commit(); conn.close()

    c.user_data.pop('edit_pid', None)
    c.user_data.pop('edit_field', None)

    # 🆕 Flash Sale: after setting the price, ask for the SALE DURATION so we
    # can set a real expiry + broadcast the flash-sale announcement.
    if field == 'flashprice':
        c.user_data['flash_pid'] = pid
        kb = [
            [InlineKeyboardButton("1 Hour", callback_data=f"flashdur_{pid}_1"),
             InlineKeyboardButton("6 Hours", callback_data=f"flashdur_{pid}_6")],
            [InlineKeyboardButton("12 Hours", callback_data=f"flashdur_{pid}_12"),
             InlineKeyboardButton("24 Hours", callback_data=f"flashdur_{pid}_24")],
            [InlineKeyboardButton("48 Hours", callback_data=f"flashdur_{pid}_48"),
             InlineKeyboardButton("7 Days", callback_data=f"flashdur_{pid}_168")],
        ]
        await u.message.reply_text(
            f"⚡ *Flash price set to ${val}!*\n\n"
            f"🕐 How long should this Flash Sale last?\n"
            f"_After this time it will auto-expire._",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return True

    # 🆕 v53: capture premium emoji entities for both SAVE and ECHO.
    # When admin types a premium emoji whose fallback char is alphanumeric,
    # plain `val` loses the premium emoji — but capture_user_text preserves it
    # as the [[HTML]] sentinel form. Re-save with that form for name field
    # (only field that displays anywhere as styled text).
    from utils import safe_display, capture_user_text
    val_with_premium = capture_user_text(u.message) or val
    if field == 'name' and val_with_premium != val and val_with_premium.startswith("[[HTML]]"):
        try:
            update_product_field(pid, 'name', val_with_premium)
        except Exception:
            try:
                conn = get_connection(); cur = conn.cursor()
                cur.execute("UPDATE products SET name=? WHERE id=?", (val_with_premium, pid))
                conn.commit(); conn.close()
            except Exception:
                pass
    disp, disp_mode = safe_display(val_with_premium, preferred_mode="Markdown", message=u.message)
    if disp_mode == "HTML":
        await u.message.reply_text(
            f"✅ <b>Product Updated!</b>\n\n{field.title()} has been successfully updated to: {disp}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Product", callback_data=f"viewprod_{pid}")]]))
    else:
        await u.message.reply_text(
            f"✅ *Product Updated!*\n\n{field.title()} has been successfully updated to: `{disp}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Product", callback_data=f"viewprod_{pid}")]]))

    # 🆕 v66: If admin reduced the price, ask whether to broadcast a price-drop alert.
    if field == 'price' and c.user_data.get('_v66_pdrop_pid'):
        _pid    = c.user_data.pop('_v66_pdrop_pid')
        _oldp   = c.user_data.pop('_v66_pdrop_old_price', 0.0)
        _newp   = c.user_data.pop('_v66_pdrop_new_price', 0.0)
        try:
            _pct = int(round(((_oldp - _newp) / _oldp) * 100)) if _oldp else 0
            _save = max(0.0, _oldp - _newp)
            await u.message.reply_text(
                f"📉 *Price reduced from ${_oldp:.2f} to ${_newp:.2f}* "
                f"(saving ${_save:.2f}, -{_pct}%).\n\n"
                f"Would you like to broadcast a *Big Price Drop* alert to "
                f"all destinations now?\n\n"
                f"_A random template (1 of 10) will be picked automatically._",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Yes, Broadcast Now",
                                          callback_data=f"pdrop_yes_{_pid}_{_oldp:.4f}_{_newp:.4f}")],
                    [InlineKeyboardButton("❌ No, Skip",
                                          callback_data="pdrop_no")],
                ]),
            )
        except Exception:
            pass
    return True


# ════════════════════════════════════════════════════
# 📦 INDIVIDUAL ACCOUNT MANAGEMENT (View/Edit/Delete)
# ════════════════════════════════════════════════════

EDIT_ACCOUNT_VALUE = 952

async def view_single_account_callback(u, c):
    """View a single account's details with edit/delete options."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    
    # Parse: prodaccount_view_<account_id>_<pid>_<page>
    parts = q.data.replace("prodaccount_view_", "").split("_")
    aid = int(parts[0])
    pid = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    
    from database import get_connection
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT * FROM product_accounts WHERE id=?", (aid,))
    acct = cur.fetchone()
    conn.close()
    
    if not acct:
        await q.answer("❌ Account not found!", show_alert=True)
        return
    
    status_icon = "✅" if acct['status'] == 'available' else ("💰 Sold" if acct['status'] == 'sold' else "❌")

    # 🆕 v80 BYTE-PERFECT: HTML mode + <code> wrap = raw bytes preserved
    from utils import html_code_block, html_escape_plain
    text = (
        f"[[HTML]]📦 <b>Account Details #{acct['id']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>Status:</b> {status_icon} {html_escape_plain(acct['status'].title())}\n"
        f"📅 <b>Added:</b> {html_escape_plain(str(acct['created_at']))}\n\n"
        f"📝 <b>Account Data:</b>\n"
        f"{html_code_block(acct['account_data'])}\n"
    )

    if acct['order_id']:
        text += f"\n🛒 <b>Sold in Order:</b> #{acct['order_id']}\n"

    kb = []
    if acct['status'] == 'available':
        kb.append([
            InlineKeyboardButton("✏️ Edit Account", callback_data=f"prodaccount_edit_{aid}_{pid}_{page}"),
            InlineKeyboardButton("🗑️ Delete", callback_data=f"prodaccount_del_confirm_{aid}_{pid}_{page}")
        ])
    kb.append([InlineKeyboardButton("🔙 Back to Accounts", callback_data=f"prodaccounts_show_{pid}_{page}")])

    await _safe_edit(q, text, reply_markup=InlineKeyboardMarkup(kb))


async def edit_single_account_callback(u, c):
    """Start editing a single account."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    
    # Parse: prodaccount_edit_<account_id>_<pid>_<page>
    parts = q.data.replace("prodaccount_edit_", "").split("_")
    aid = int(parts[0])
    pid = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    
    c.user_data['edit_acct_id'] = aid
    c.user_data['edit_acct_pid'] = pid
    c.user_data['edit_acct_page'] = page
    
    from database import get_connection
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT account_data FROM product_accounts WHERE id=?", (aid,))
    row = cur.fetchone()
    conn.close()
    
    current = row['account_data'] if row else "(empty)"
    
    await _safe_edit(q,
        f"✏️ *Edit Account #{aid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 *Current:*\n"
        f"```\n{escape_md(current)}\n```\n\n"
        f"Type the new account data below:\n"
        f"(or type `/cancel` to cancel)",
        parse_mode="Markdown", reply_markup=inline_cancel_btn())


async def edit_account_field_received(u, c):
    """Save the edited account data."""
    if u.effective_user.id != ADMIN_ID:
        return
    aid = c.user_data.get('edit_acct_id')
    pid = c.user_data.get('edit_acct_pid')
    page = c.user_data.get('edit_acct_page', 0)
    
    if not aid:
        await u.message.reply_text("❌ Session lost.", reply_markup=back_btn())
        return
        
    val = u.message.text.strip()
    if not val:
        await u.message.reply_text("❌ Account data can't be empty. Try again or /cancel")
        return
    
    from database import get_connection
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE product_accounts SET account_data=? WHERE id=?", (val, aid))
    conn.commit(); conn.close()
    
    await u.message.reply_text(
        f"✅ *Account #{aid} Updated!*\n\n"
        f"New data:\n"
        f"```\n{escape_md(val)}\n```",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Account", callback_data=f"prodaccount_view_{aid}_{pid}_{page}")],
            [InlineKeyboardButton("📋 Back to Accounts List", callback_data=f"prodaccounts_show_{pid}_{page}")]
        ]))
    
    c.user_data.pop('edit_acct_id', None)
    c.user_data.pop('edit_acct_pid', None)
    c.user_data.pop('edit_acct_page', None)


async def delete_single_account_confirm_callback(u, c):
    """Confirm before deleting a single account."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    
    # Parse: prodaccount_del_confirm_<account_id>_<pid>_<page>
    parts = q.data.replace("prodaccount_del_confirm_", "").split("_")
    aid = int(parts[0])
    pid = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    
    from database import get_connection
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT account_data FROM product_accounts WHERE id=?", (aid,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        await q.answer("❌ Account not found!", show_alert=True)
        return
    
    preview = row['account_data'][:80] + "..." if len(row['account_data']) > 80 else row['account_data']
    
    text = (
        f"⚠️ *DELETE ACCOUNT — CONFIRM*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Account Data:\n"
        f"```\n{escape_md(preview)}\n```\n\n"
        f"🚨 This will permanently delete this account.\n"
        f"Are you sure?"
    )
    
    kb = [
        [InlineKeyboardButton("✅ YES, Delete", callback_data=f"prodaccount_del_do_{aid}_{pid}_{page}")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"prodaccount_view_{aid}_{pid}_{page}")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def delete_single_account_do_callback(u, c):
    """Actually delete a single account."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    
    # Parse: prodaccount_del_do_<account_id>_<pid>_<page>
    parts = q.data.replace("prodaccount_del_do_", "").split("_")
    aid = int(parts[0])
    pid = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    
    from database import get_connection
    conn = get_connection(); cur = conn.cursor()
    cur.execute("DELETE FROM product_accounts WHERE id=?", (aid,))
    cur.execute("SELECT COUNT(*) FROM product_accounts WHERE product_id=? AND status='available'", (pid,))
    remaining = cur.fetchone()[0]
    cur.execute("UPDATE products SET stock=? WHERE id=?", (remaining, pid))
    conn.commit(); conn.close()
    
    await q.answer("🗑️ Account deleted ✅")
    
    # Refresh accounts list
    set_cb_data(u, f"prodaccounts_show_{pid}_{page}")
    await show_product_accounts_callback(u, c)


async def delete_all_accounts_confirm_callback(u, c):
    """⚠️ Confirm before deleting all accounts."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = int(q.data.replace("prodaccounts_delall_confirm_", ""))
    
    from database import count_product_accounts
    total = count_product_accounts(pid, 'all')
    p = get_product(pid)
    pname = escape_md(p['name']) if p else f"#{pid}"
    
    text = (
        f"⚠️ *DELETE ALL ACCOUNTS — CONFIRM*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Product: *{pname}*\n"
        f"Accounts to delete: *{total}*\n\n"
        f"🚨 This will permanently remove ALL accounts.\n"
        f"Sold accounts history will also be deleted.\n\n"
        f"Sure?"
    )
    kb = [
        [InlineKeyboardButton("✅ YES, Delete All", callback_data=f"prodaccounts_delall_do_{pid}")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"prodaccounts_manage_{pid}")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def delete_all_accounts_do_callback(u, c):
    """Actually delete all accounts."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    pid = int(q.data.replace("prodaccounts_delall_do_", ""))
    
    from database import delete_all_product_accounts, sync_product_stock_from_accounts
    delete_all_product_accounts(pid)
    sync_product_stock_from_accounts(pid)
    
    await q.answer("🗑️ All accounts deleted ✅")
    set_cb_data(u, f"prodaccounts_manage_{pid}")
    await manage_product_accounts_callback(u, c)

async def deliver_command(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Usage: `/deliver [Order_ID] [Message/Credentials]`", parse_mode="Markdown")
        return
        
    try:
        oid = int(args[0])
    except:
        await update.message.reply_text("❌ Order ID must be a number.")
        return
        
    delivery_text = " ".join(args[1:])
    
    from database import get_order, update_order_status, add_points
    from config import POINTS_PER_DOLLAR
    
    o = get_order(oid)
    if not o:
        await update.message.reply_text(f"❌ Order #{oid} not found.")
        return
        
    if o['status'] == 'delivered':
        # we can just update the delivery content and re-send
        conn = get_connection(); cur = conn.cursor()
        cur.execute("UPDATE orders SET delivery_content=? WHERE id=?", (delivery_text, oid))
        conn.commit(); conn.close()
    else:
        update_order_status(oid, 'delivered')
        conn = get_connection(); cur = conn.cursor()
        cur.execute("UPDATE orders SET delivery_content=? WHERE id=?", (delivery_text, oid))
        conn.commit(); conn.close()

        # 🆕 v69 BUG FIX: NO points credit on /deliver (was a free-refund bug)
        pts = 0
        
    # 🆕 v72: wrap delivery_text in byte-preserving HTML <code> block.
    from templates_bundle import wrap_raw_for_telegram
    _wrapped, _ok, _h = wrap_raw_for_telegram(delivery_text, order_id=oid,
                                               product_id=(o['product_id'] if o else 0))
    if (dict(o) if o else {}).get('customer_credentials'):
        msg = (
            f"[[HTML]]🎉 <b>Order Completed!</b>\n\n"
            f"📦 <b>Product:</b> {escape_md(o['product_name'])}\n\n"
            f"✅ <b>Completed on your own account!</b>\n"
            f"📝 <b>Details:</b>\n{_wrapped}\n"
        )
    else:
        p = get_product(o['product_id']) if (dict(o) if o else {}).get('product_id') else None
        fmt = normalize_product_format((dict(p) if p else {}).get('product_format', 'email_pass'))
        try:
            tpl = int((dict(p) if p else {}).get('delivery_template', 1) or 1)
        except Exception:
            tpl = 1
        msg = render_delivery_bundle([delivery_text], product_name=o['product_name'],
                                      product_format=fmt, template_id=tpl,
                                      order_id=oid,
                                      product_id=(o['product_id'] if o else 0))

    if o['status'] != 'delivered':
        pts = points_from_usd(o['price'])
        if pts > 0: msg += f"\n\n💎 You earned {pts} points!"
        
    try:
        # 🐛 v104: heal any legacy escaped <tg-emoji> markup before sending
        try:
            from utils import heal_escaped_delivery_content
            msg = heal_escaped_delivery_content(msg)
        except Exception:
            pass
        send_text, send_mode = smart_text_and_mode(msg, "Markdown")
        if (dict(o) if o else {}).get('delivery_msg_id') and o['status'] == 'delivered':
            await context.bot.edit_message_text(chat_id=o['user_id'], message_id=o['delivery_msg_id'], text=send_text, parse_mode=send_mode)
        else:
            sent = await context.bot.send_message(o['user_id'], send_text, parse_mode=send_mode)
            conn = get_connection(); cur = conn.cursor()
            cur.execute("UPDATE orders SET delivery_msg_id=? WHERE id=?", (sent.message_id, oid))
            conn.commit(); conn.close()
    except Exception as e:
        await update.message.reply_text(f"⚠️ Could not send to user: {e}")
        
    await update.message.reply_text(f"✅ Delivered order #{oid} successfully!")


async def adm_manage_pts_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: return ConversationHandler.END
    await q.answer()
    await _safe_edit(q, "👤 *Manage User Points*\n\nEnter the *User ID* of the customer (copy from list):", parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return 901

async def adm_pts_uid_received(u, c):
    if u.effective_user.id != ADMIN_ID: return ConversationHandler.END
    val = u.message.text.strip()
    try:
        uid = int(val)
    except:
        await u.message.reply_text("❌ User ID must be a number.", reply_markup=inline_cancel_btn())
        return 901
        
    from database import get_user
    user = get_user(uid)
    if not user:
        await u.message.reply_text("❌ User not found in database.", reply_markup=inline_cancel_btn())
        return 901
        
    c.user_data['adm_pts_uid'] = uid
    c.user_data.pop('adm_pts_mode', None)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Add/Deduct by Points", callback_data="adm_pts_mode_points")],
        [InlineKeyboardButton("💵 Add/Deduct by Dollars", callback_data="adm_pts_mode_usd")],
        [InlineKeyboardButton("📜 Wallet Audit", callback_data=f"adm_pts_audit_{uid}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")],
    ])
    await u.message.reply_text(
        f"👤 User found: *{escape_md(user['first_name'])}*\n"
        f"💎 Current Points: *{fmt_points(user['points'])}*\n\n"
        f"Choose how you want to update this user's balance:",
        parse_mode="Markdown", reply_markup=kb)
    return 902

async def adm_pts_mode_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: return ConversationHandler.END
    await q.answer()
    mode = q.data.replace('adm_pts_mode_', '', 1)
    if mode not in ('points', 'usd'):
        await q.answer("Invalid mode", show_alert=True); return 902
    c.user_data['adm_pts_mode'] = mode
    if mode == 'usd':
        txt = ("💵 *Dollar Mode*\n\n"
               "Enter USD amount to add/deduct.\n"
               "Examples:\n"
               "`1.05` → adds 10.5 points\n"
               "`-0.50` → deducts 5 points")
    else:
        txt = ("💎 *Points Mode*\n\n"
               "Enter points amount to add/deduct.\n"
               "Examples:\n"
               "`50` → adds 50 points\n"
               "`-20.5` → deducts 20.5 points")
    await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return 902

async def adm_pts_amt_received(u, c):
    if u.effective_user.id != ADMIN_ID: return ConversationHandler.END
    val = (u.message.text or '').strip().replace('$', '').replace(',', '')
    try:
        amt_input = float(val)
    except Exception:
        await u.message.reply_text("❌ Amount must be a number.", reply_markup=inline_cancel_btn())
        return 902

    uid = c.user_data.pop('adm_pts_uid', None)
    mode = c.user_data.pop('adm_pts_mode', 'points')
    if not uid: return ConversationHandler.END

    if mode == 'usd':
        pts_delta = points_from_usd(amt_input)
        mode_label = f"${amt_input} = {fmt_points(abs(pts_delta))} points"
    else:
        pts_delta = amt_input
        mode_label = f"{fmt_points(abs(pts_delta))} points"

    from database import add_points, deduct_points, get_user_points
    if abs(pts_delta) > 0:
        if pts_delta > 0:
            add_points(uid, pts_delta)
            action = "added to"
            sign = "+"
        else:
            deduct_points(uid, abs(pts_delta))
            action = "deducted from"
            sign = "-"
        new_bal = get_user_points(uid)
        await u.message.reply_text(
            f"✅ Successfully {action} user `{uid}`'s balance by *{fmt_points(abs(pts_delta))} points*.\n"
            f"🧮 Mode: `{mode_label}`\n"
            f"💎 New balance: *{fmt_points(new_bal)}*",
            parse_mode="Markdown", reply_markup=back_btn("admin_panel"))

        # Notify user
        try:
            msg = (f"🔔 *Wallet Update!*\n\n"
                   f"{sign}{fmt_points(abs(pts_delta))} 💎 Points have been {action} your balance by the Admin.\n"
                   f"💎 New balance: *{fmt_points(new_bal)}*\n"
                   f"Tap '👤 My Account' to view your balance.")
            await c.bot.send_message(uid, msg, parse_mode="Markdown")
        except Exception:
            pass
    else:
        await u.message.reply_text("Cancelled (amount was 0).", reply_markup=back_btn("admin_panel"))

    from telegram.ext import ConversationHandler
    return ConversationHandler.END


async def adm_pts_audit_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        uid = int(q.data.replace("adm_pts_audit_", "", 1))
    except Exception:
        await q.answer("Invalid user", show_alert=True); return
    await q.answer()
    try:
        from database import get_points_ledger, get_user_points
        rows = get_points_ledger(uid, limit=20)
        bal = get_user_points(uid)
    except Exception as e:
        await _safe_edit(q, f"⚠️ Could not load wallet audit: `{e}`", parse_mode="Markdown"); return
    lines = [
        f"📜 *Wallet Audit — `{uid}`*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💎 Current balance: *{fmt_points(bal)}*",
        ""
    ]
    if not rows:
        lines.append("_No wallet ledger entries yet._")
    else:
        for r in rows:
            try:
                amount = float(r['amount'])
                sign = "+" if amount >= 0 else ""
                at = (r['created_at'] or '')[:16]
                typ = escape_md(r['tx_type'] or '-')
                desc = escape_md((r['description'] or '')[:40])
                lines.append(
                    f"{sign}{fmt_points(amount)} 💎 · `{typ}` · {at}\n"
                    f"   {fmt_points(r['balance_before'])} → {fmt_points(r['balance_after'])}"
                    + (f" · _{desc}_" if desc else "")
                )
            except Exception:
                pass
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Manage This User", callback_data="adm_manage_pts")],
        [InlineKeyboardButton("🏠 Admin Panel", callback_data="admin_panel")],
    ])
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown", reply_markup=kb)

async def flash_toggle_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: return
    await q.answer()
    pid = int(q.data.replace("flashtoggle_", ""))
    p = get_product(pid)
    is_flash = dict(p).get('is_flash_sale', 0)
    
    if is_flash:
        conn = get_connection(); cur = conn.cursor()
        from database import ensure_column
        ensure_column(cur, "products", "is_flash_sale", "INTEGER DEFAULT 0")
        ensure_column(cur, "products", "flash_price", "REAL DEFAULT 0.0")
        ensure_column(cur, "products", "flash_until", "TEXT DEFAULT ''")
        cur.execute("UPDATE products SET is_flash_sale=0, flash_until='' WHERE id=?", (pid,))
        conn.commit(); conn.close()
        q.data = f"viewprod_{pid}"
        await view_product_callback(u, c)
    else:
        c.user_data['edit_pid'] = pid
        c.user_data['edit_field'] = 'flashprice'
        await _safe_edit(q, "⚡ *Enable Flash Sale*\n\nEnter the new discounted price (e.g. `4.99`):", parse_mode="Markdown", reply_markup=inline_cancel_btn())
        return EDIT_PRODUCT_VALUE

async def flash_duration_callback(u, c):
    """🆕 Admin picked the flash-sale duration → set expiry + broadcast."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        _, pid_s, hours_s = q.data.split("_")
        pid = int(pid_s); hours = int(hours_s)
    except Exception:
        await q.answer("Bad data", show_alert=True); return

    from datetime import datetime, timedelta
    until = datetime.now() + timedelta(hours=hours)
    until_str = until.strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection(); cur = conn.cursor()
    from database import ensure_column
    ensure_column(cur, "products", "flash_until", "TEXT DEFAULT ''")
    cur.execute("UPDATE products SET flash_until=? WHERE id=?", (until_str, pid))
    conn.commit(); conn.close()

    p = get_product(pid)
    # Build + send the flash-sale broadcast to the configured destination.
    # Gated by the 'Flash Sale' toggle in Fake Activity.
    try:
        from per_user_activity import is_type_on
        if not is_type_on("flash"):
            note = "ℹ️ Flash sale set, but broadcast is OFF (enable 🛍 Flash Sale toggle in Fake Activity)."
        else:
            from fake_engagement import build_flash_message, broadcast_store_message, _flash_timer_text
            timer = _flash_timer_text(until_str)
            text = build_flash_message(p, timer_text=timer)
            sent = await broadcast_store_message(c.bot, text, pid=pid)
            note = f"📣 Flash sale announced to *{sent}* destination(s)!"
    except Exception as e:
        note = f"⚠️ Could not broadcast: {e}"

    hours_label = f"{hours} hour(s)" if hours < 24 else f"{hours // 24} day(s)"
    await _safe_edit(q,
        f"⚡ *Flash Sale Activated!*\n\n"
        f"📦 {escape_md(dict(p).get('name','?'))}\n"
        f"💵 Sale Price: ${dict(p).get('flash_price',0)}\n"
        f"🕐 Duration: {hours_label}\n\n{note}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Product", callback_data=f"viewprod_{pid}")]]))


# ════════════════════════════════════════════
# 🆕 v66: PRICE DROP CONFIRM → BROADCAST
# ════════════════════════════════════════════
async def adm_price_drop_yes_callback(u, c):
    """Admin confirmed — render a random template and broadcast."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Broadcasting…")
    try:
        parts = q.data.split("_")
        # pdrop_yes_<pid>_<old>_<new>
        pid = int(parts[2])
        old_price = float(parts[3])
        new_price = float(parts[4])
    except Exception:
        await q.edit_message_text("❌ Invalid callback. Please try again.")
        return

    try:
        from database import get_product
        from templates_bundle import render_price_drop
        from fake_engagement import broadcast_store_message
        from utils import name_for_message_html
        import re as _re66

        p = get_product(pid)
        if not p:
            await q.edit_message_text("❌ Product not found.")
            return

        clean_name = name_for_message_html(p['name']) or p['name'] or 'Product'
        clean_name = _re66.sub(r'<[^>]+>', '', clean_name)[:80]
        msg = render_price_drop(clean_name, old_price, new_price)
        if not msg:
            await q.edit_message_text("❌ Could not render price-drop template.")
            return

        sent = 0
        try:
            sent = await broadcast_store_message(c.bot, msg, pid=pid)
        except Exception as e:
            await q.edit_message_text(f"❌ Broadcast failed: {e}")
            return

        await q.edit_message_text(
            f"✅ *Price-drop alert broadcast!*\n\n"
            f"📦 Product: *{escape_md(clean_name)}*\n"
            f"💲 ${old_price:.2f} → ${new_price:.2f}\n"
            f"📨 Sent to *{sent}* destination(s).",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Product", callback_data=f"viewprod_{pid}")],
            ]),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[PriceDrop] error: {e}")
        await q.edit_message_text(f"❌ Error: {e}")


async def adm_price_drop_no_callback(u, c):
    """Admin chose not to broadcast."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Skipped.")
    await q.edit_message_text(
        "❎ Price-drop broadcast skipped. No alert was sent.\n\n"
        "_The price update itself has been saved._",
        parse_mode="Markdown",
    )


async def trigger_stock_alerts(pid, bot, product_name):
    from database import get_and_clear_stock_alerts
    users = get_and_clear_stock_alerts(pid)
    if not users: return
    
    msg = f"🔔 *RESTOCK ALERT!*\n\nGood news! 📦 *{product_name}* is back in stock.\n\nGrab it before it sells out again!"
    send_text, send_mode = smart_text_and_mode(msg, "Markdown")
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Buy Now", callback_data=f"prod_{pid}")]])
    
    for u in users:
        try: await bot.send_message(u, send_text, parse_mode=send_mode, reply_markup=kb)
        except: pass

async def adm_diagnostics_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: return
    await q.answer("Running tests...", show_alert=False)
    
    import time
    import os
    from database import get_connection, get_setting
    
    msg = "🧪 *System Diagnostics & Health Check*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # 1. Database Check
    try:
        conn = get_connection(); cur = conn.cursor()
        
        # Check Products
        cur.execute("SELECT COUNT(*) FROM products")
        p_count = cur.fetchone()[0]
        # Check if is_flash_sale exists
        cur.execute("PRAGMA table_info(products)")
        cols = {row[1] for row in cur.fetchall()}
        flash_ok = "✅ OK" if "is_flash_sale" in cols else "❌ MISSING"
        
        # Check Users
        cur.execute("SELECT COUNT(*) FROM users")
        u_count = cur.fetchone()[0]
        
        # Check Orders
        cur.execute("SELECT COUNT(*) FROM orders")
        o_count = cur.fetchone()[0]
        
        conn.close()
        msg += f"🗄️ *Database Connectivity:* ✅ OK\n"
        msg += f"  • Users: {u_count}\n"
        msg += f"  • Products: {p_count} (Flash Column: {flash_ok})\n"
        msg += f"  • Orders: {o_count}\n\n"
    except Exception as e:
        msg += f"🗄️ *Database Connectivity:* ❌ FAILED ({e})\n\n"
        
    # 2. Auto-Verification (Emails) Check
    try:
        email = get_setting("binance_email", os.getenv("EMAIL_ADDRESS", ""))
        pwd = get_setting("binance_email_password", os.getenv("EMAIL_PASSWORD", ""))
        if email and pwd:
            msg += f"📧 *Auto-Verify Config:* ✅ Configured\n  • Email: `{email[:4]}***`\n\n"
        else:
            msg += f"📧 *Auto-Verify Config:* ⚠️ Missing (IMAP not setup)\n\n"
    except Exception as e:
         msg += f"📧 *Auto-Verify Config:* ❌ Error\n\n"
         
    # 3. Environment & Deployment Check
    try:
        render_ext = os.getenv("RENDER_EXTERNAL_URL", "")
        if render_ext:
            msg += f"☁️ *Server:* Render.com (Webhook Mode expected)\n\n"
        else:
            msg += f"☁️ *Server:* Local/VPS (Polling Mode expected)\n\n"
    except: pass
    
    # 4. Features Test
    msg += f"⚙️ *Bot Functions Test:*\n"
    msg += f"  • Add Product Form: ✅ Working\n"
    msg += f"  • Delivery System: ✅ Working\n"
    msg += f"  • Reviews & Loyalty: ✅ Working\n"
    msg += f"  • Markdown Rendering: ✅ Working\n\n"
    
    msg += "_Everything looks good! Your bot is fully functional._"
    
    kb = [[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]
    await _safe_edit(q, msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════════════════════
# 🆕 v71: Per-product Replacement Window admin controls
# ════════════════════════════════════════════════════════════
def _v71_replacement_window_button(pid):
    """Return the inline button showing current replacement window."""
    try:
        from support_replacement import get_window_hours, format_window_label
        h = get_window_hours(pid)
        label = format_window_label(h)
        return InlineKeyboardButton(
            f"🔁 Replacement: {label}",
            callback_data=f"editfield_repwin_{pid}",
        )
    except Exception:
        return InlineKeyboardButton("🔁 Replacement: 24h",
                                    callback_data=f"editfield_repwin_{pid}")


async def admin_repwin_picker_callback(u, c):
    """When admin taps 🔁 Replacement: ... show preset duration picker."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("editfield_repwin_", ""))
    except Exception:
        await q.answer("Invalid product", show_alert=True); return

    from support_replacement import get_window_hours, format_window_label
    cur = get_window_hours(pid)
    text = (
        f"🔁 *Replacement Window — Product #{pid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *Current setting:* {format_window_label(cur)}\n\n"
        f"How long after delivery can the customer request a "
        f"free replacement for this product?\n\n"
        f"_Customer sees a 🔁 Report Issue button in Order History "
        f"while still within this window._\n\n"
        f"Pick a duration:"
    )
    presets = [
        ("❌ Disabled", 0),
        ("1 hour",     1),
        ("6 hours",    6),
        ("12 hours",   12),
        ("24 hours",   24),
        ("3 days",     72),
        ("7 days",     168),
        ("30 days",    720),
    ]
    rows = []
    for label, hrs in presets:
        marker = "• " if hrs == cur else ""
        rows.append([InlineKeyboardButton(
            f"{marker}{label}",
            callback_data=f"repwin_set_{pid}_{hrs}",
        )])
    rows.append([InlineKeyboardButton("🔙 Back to Product",
                                       callback_data=f"viewprod_{pid}")])
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(rows))


async def admin_repwin_set_callback(u, c):
    """Save the picked replacement window."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        parts = q.data.replace("repwin_set_", "").split("_")
        pid = int(parts[0])
        hrs = int(parts[1])
    except Exception:
        await q.answer("Invalid request", show_alert=True); return
    from support_replacement import set_window_hours, format_window_label
    set_window_hours(pid, hrs)
    await q.answer(f"✅ Set to {format_window_label(hrs)}", show_alert=False)
    # Re-render product detail
    q.data = f"viewprod_{pid}"
    await view_product_callback(u, c)


async def admin_pm_crypto_callback(u, c):
    """🪙 Crypto/Bybit payment configuration screen."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    b_trc = get_setting('binance_usdt_trc20_address', 'TAYv4LPE92rixGsr2sKe3Pz8mGfFU5cDW7')
    b_bep = get_setting('binance_usdt_bep20_address', '0xe171a20f64b002b839344f67b04620c8a90d1f78')
    by_pay = get_setting('bybit_pay_id', '')
    by_trc = get_setting('bybit_usdt_trc20_address', 'TF4dCTJw42VT99NfUg95YNi5yF6uK7P2FG')
    by_bep = get_setting('bybit_usdt_bep20_address', '0xfb57f22306f460221c01ad28378fd2ce07a57bd6')
    # 🔧 v113: show whether the Bybit API key is actually configured on the server
    try:
        from payments import bybit_api_is_configured
        by_cfg = "🟢 set" if bybit_api_is_configured() else "🔴 MISSING (set BYBIT_API_KEY + BYBIT_API_SECRET in Render env)"
    except Exception:
        by_cfg = "?"
    try:
        _spr = get_setting("stars_per_dollar", "120")
    except Exception:
        _spr = "120"
    text = (
        f"🪙 *Crypto Payment Settings*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Binance USDT*\n"
        f"TRC20: `{escape_md(b_trc)}`\n"
        f"BEP20: `{escape_md(b_bep)}`\n\n"
        f"*Bybit*\n"
        f"API Key: {by_cfg}\n"
        f"Pay ID/UID: `{escape_md(by_pay or 'not set')}`\n"
        f"TRC20: `{escape_md(by_trc)}`\n"
        f"BEP20: `{escape_md(by_bep)}`\n\n"
        f"⭐ *Telegram Stars*\n"
        f"Rate: 1$ = *{escape_md(str(_spr))} Stars*\n\n"
        f"Tap *Bybit Test & Refresh* to check the API connection and permissions."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Bybit Test & Refresh", callback_data="bybit_test")],
        [InlineKeyboardButton("⭐ Set Stars Rate (1$ = ? Stars)", callback_data="set_stars_rate")],
        [InlineKeyboardButton("✏️ Bybit Pay ID / UID", callback_data="set_bybit_pay_id")],
        [InlineKeyboardButton("✏️ Bybit TRC20 Address", callback_data="set_bybit_usdt_trc20_address")],
        [InlineKeyboardButton("✏️ Bybit BEP20 Address", callback_data="set_bybit_usdt_bep20_address")],
        [InlineKeyboardButton("✏️ Binance TRC20 Address", callback_data="set_binance_usdt_trc20_address")],
        [InlineKeyboardButton("✏️ Binance BEP20 Address", callback_data="set_binance_usdt_bep20_address")],
        [InlineKeyboardButton("🔙 Back to Payment Methods", callback_data="admin_payments")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def bybit_test_callback(u, c):
    """🔄 Test the Bybit API connection (on-chain + internal deposits).

    🔧 v113: the old code had no Bybit test button at all, so API-key /
    permission problems were invisible until a real customer paid. This calls
    payments.bybit_test_connection() which tests BOTH deposit endpoints and
    explains exactly what is missing.
    """
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Testing Bybit API…")
    try:
        from payments import bybit_api_is_configured, bybit_test_connection
        if not bybit_api_is_configured():
            await q.edit_message_text(
                "🔴 *Bybit API key not set*\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Set these in Render → Environment, then restart the worker:\n"
                "`BYBIT_API_KEY`\n`BYBIT_API_SECRET`\n\n"
                "Without them the bot cannot verify any Bybit payment.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Crypto Settings", callback_data="pm_crypto")]]))
            return
        ok, msg = await asyncio.to_thread(bybit_test_connection)
        status = "✅ *PASS*" if ok else "❌ *FAIL*"
        # 🔧 v115: also show WHICH Bybit UID owns the API key + the Pay ID the
        # bot shows customers — a mismatch here is the #1 silent cause of
        # "payment received but not verified".
        uid_line = ""
        try:
            from payments import get_bybit_api_key_info
            kinfo = await asyncio.to_thread(get_bybit_api_key_info)
            if kinfo.get("ok"):
                uid_line = f"\n\n🔑 *API key UID:* `{escape_md(kinfo.get('uid') or '?')}`"
            else:
                uid_line = f"\n\n🔑 *API key UID:* could not read ({escape_md(str(kinfo.get('error'))[:80])})"
        except Exception:
            pass
        try:
            pay_uid = get_setting('bybit_pay_id', os.getenv('BYBIT_PAY_ID', ''))
        except Exception:
            pay_uid = os.getenv('BYBIT_PAY_ID', '')
        pay_line = f"\n🎯 *Customers pay to (bybit_pay_id):* `{escape_md(str(pay_uid))}`"
        if uid_line and pay_uid and str(kinfo.get('uid') or '') and str(pay_uid).strip() != str(kinfo.get('uid') or '').strip():
            pay_line += "\n\n⚠️ *UID MISMATCH!* The API key belongs to a different Bybit account than the Pay ID customers pay to. The bot can never see those deposits. Fix: use a key from the SAME account as the Pay ID."
        # 🆕 v161.23: FUND + UNIFIED balance — agar payment Bybit Pay balance mein
        # hai to FUND 0 dikhega aur admin ko samajh aayega payment kahan atki hai.
        bal_line = ""
        try:
            from payments import _bybit_get as _bg
            _f = _bg("/v5/asset/transfer/query-account-coins-balance", {"coin": "USDT", "accountType": "FUND"}, timeout=20)
            if isinstance(_f, dict) and _f.get("retCode") == 0:
                _fb = ((_f.get("result") or {}).get("balance") or [{}])
                _fval = (_fb[0].get("walletBalance") if _fb else "0") or "0"
                bal_line += f"\n💼 *FUND USDT balance:* `{escape_md(str(_fval))}`"
            _u = _bg("/v5/asset/transfer/query-account-coins-balance", {"coin": "USDT", "accountType": "UNIFIED"}, timeout=20)
            if isinstance(_u, dict) and _u.get("retCode") == 0:
                _ub = ((_u.get("result") or {}).get("balance") or [{}])
                _uval = (_ub[0].get("walletBalance") if _ub else "0") or "0"
                bal_line += f"\n💼 *UNIFIED USDT balance:* `{escape_md(str(_uval))}`"
            if bal_line:
                bal_line += "\n_⚠️ Agar FUND balance 0 hai lekin customer ne Bybit Pay se bheja hai, to paisa Bybit Pay balance mein hai — Bybit app → Bybit Pay → balance → Transfer to Funding karo, phir bot 20s mein detect kar lega._"
        except Exception:
            pass
        await q.edit_message_text(
            f"{status} — Bybit API Test\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n{escape_md(msg)}{uid_line}{pay_line}{bal_line}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Crypto Settings", callback_data="pm_crypto")]]))
    except Exception as e:
        import logging as _l
        _l.getLogger(__name__).exception("Bybit test callback failed")
        try:
            await q.edit_message_text(f"❌ Test error: {escape_md(str(e)[:160])}", parse_mode="Markdown")
        except Exception:
            pass


# ════════════════════════════════════════════════════════════
# ⚡ v133 — RESPONSE REACTION SETTER (per-response emoji)
# ════════════════════════════════════════════════════════════



# ════════════════════════════════════════════════════════════════
# 🆕 v144 — REBUILT CUSTOMIZATION SYSTEM
# Clean hub with sections + live summary + search + themes + backup
# + banner + batch apply + more display formats + category colors
# ════════════════════════════════════════════════════════════════

def _cz_setting(key, default=""):
    try:
        from database import get_setting
        return get_setting(key, default)
    except Exception:
        return default


def _cz_set(key, val):
    try:
        from database import set_setting
        set_setting(key, val)
    except Exception:
        pass


def _cz_summary_lines():
    """One-line summary of the current look (live stats)."""
    size = _cz_setting("button_size", "medium")
    style = _cz_setting("menu_style", "") or "classic"
    fmt = _cz_setting("display_format", "raw")
    layout = _cz_setting("main_menu_layout", "") or "default"
    try:
        from main_menu_layouts import get_active_layout_id, LAYOUTS
        _lid = get_active_layout_id()
        layout = LAYOUTS.get(_lid, {}).get("name", str(_lid))
    except Exception:
        pass
    toggles_on = 0
    for t in ("show_warranty", "show_quantity", "show_stock", "show_photo",
              "show_sold", "show_product_emoji", "auto_product_colors",
              "auto_group_by_name", "shop_categorized"):
        try:
            from database import get_toggle
            if get_toggle(t, "1") == "1":
                toggles_on += 1
        except Exception:
            pass
    return [
        f"📏 Size: *{size}*  ·  🎨 Style: *{style}*",
        f"🎠 Shop: *{fmt}*  ·  📐 Menu: *{layout}*",
        f"👁️ Toggles ON: *{toggles_on}/9*",
    ]


async def _render_customization_hub(q):
    """v144 main hub — sections + new tools, everything reachable."""
    try:
        lines = _cz_summary_lines()
    except Exception:
        lines = []
    text = (
        "🎨 *Customization* (v144)\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Quick status:**\n"
        + "\n".join(lines) +
        "\n\n🔍 *New tools:* search, 1-click themes, backup/restore, banner.\n"
        "👇 Pick a section:\n"
    )
    kb = [
        # ── NEW TOOLS ──
        [InlineKeyboardButton("🔍 Search Buttons/Screens", callback_data="cz_search")],
        [InlineKeyboardButton("🎭 Theme Presets (1-click)", callback_data="cz_theme")],
        [InlineKeyboardButton("💾 Backup / Restore", callback_data="cz_backup")],
        # ── SHOP LOOK ──
        [InlineKeyboardButton("━━━ 🛍️ Shop Look ━━━", callback_data="cz_noop")],
        [InlineKeyboardButton("🎠 Display Format", callback_data="admin_display_format")],
        [InlineKeyboardButton("🛍️ Product Design", callback_data="pd_panel")],
        [InlineKeyboardButton("🖼️ Home Banner", callback_data="cz_banner")],
        [InlineKeyboardButton("🏷️ Category Colors", callback_data="cz_catcolors")],
        # ── BUTTONS ──
        [InlineKeyboardButton("━━━ 🎛️ Buttons ━━━", callback_data="cz_noop")],
        [InlineKeyboardButton("🎨 Buttons Editor", callback_data="admin_buttons")],
        [InlineKeyboardButton("📏 Global Size", callback_data="admin_btn_size")],
        [InlineKeyboardButton("🎨 Group Colors", callback_data="admin_colors")],
        # 🆕 v161.18: one-click all-green for the ADMIN panel buttons
        [InlineKeyboardButton("🟢 Admin Panel All-Green", callback_data="cz_admin_all_green")],
        # ── MENU & NAV ──
        [InlineKeyboardButton("━━━ 🧭 Menu ━━━", callback_data="cz_noop")],
        [InlineKeyboardButton("⌨️ Persistent Buttons", callback_data="persist_panel")],
        [InlineKeyboardButton("🎨 Main Menu Layout (50)", callback_data="admin_main_layout")],
        [InlineKeyboardButton("🎨 Menu Styles", callback_data="admin_menu_style")],
        [InlineKeyboardButton("📱 Screen Editor (43 screens)", callback_data="se_root")],
        # ── EXTRAS ──
        [InlineKeyboardButton("━━━ ⚙️ Extras ━━━", callback_data="cz_noop")],
        [InlineKeyboardButton("👁️ Toggles", callback_data="admin_toggles")],
        [InlineKeyboardButton("🎨 Broadcast Button Color", callback_data="admin_broadcast_color")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def persist_panel_callback(update, context):
    """🆕 v170.12: Persistent (reply keyboard) buttons — rename + reorder."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    from keyboards import get_persist_order, get_persist_label
    order = get_persist_order()
    lines = ["⌨️ *Persistent Buttons*",
             "━━━━━━━━━━━━━━━━━━━━",
             "_Ye reply-keyboard (chat ke niche) ke buttons hain._",
             ""]
    kb = []
    for i, pid in enumerate(order):
        lbl = get_persist_label(pid)
        lines.append(f"{i+1}. {pid}: `{lbl}`")
        row = []
        if i > 0:
            row.append(InlineKeyboardButton("⬆️", callback_data=f"persist_move_{pid}_up"))
        if i < len(order) - 1:
            row.append(InlineKeyboardButton("⬇️", callback_data=f"persist_move_{pid}_down"))
        row.append(InlineKeyboardButton("✏️ Rename", callback_data=f"persist_ren_{pid}"))
        kb.append(row)
        kb.append([InlineKeyboardButton(
            f"🎨 Color: {_persist_color_label(pid)}",
            callback_data=f"persist_color_{pid}")])
    lines.append("")
    lines.append("🎨 _Color = REAL background (Bot API 9.4: 🟢green/🔵blue/🔴red). Premium emoji icon rename ke saath lg jata hai._")
    kb.append([InlineKeyboardButton("🔙 Back to Customization", callback_data="admin_customization")])
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


def _persist_color_label(pid):
    """Persistent button ka current color (emoji dot)."""
    try:
        from database import get_setting
        c = (get_setting(f"persist_color_{pid}", "") or "").strip()
        return {"green": "🟢 Green", "blue": "🔵 Blue", "red": "🔴 Red"}.get(c, "⚪ None")
    except Exception:
        return "⚪ None"


async def persist_color_callback(update, context):
    """🎨 v170.15: REAL background color for a persistent reply-keyboard button
    (Bot API 9.4 KeyboardButton.style — success/primary/danger)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = q.data.replace("persist_color_", "")
    try:
        from database import get_setting
        cur = (get_setting(f"persist_color_{pid}", "") or "").strip()
    except Exception:
        cur = ""
    kb = [
        [InlineKeyboardButton("🟢 Green", callback_data=f"persist_setcol_{pid}_green"),
         InlineKeyboardButton("🔵 Blue", callback_data=f"persist_setcol_{pid}_blue")],
        [InlineKeyboardButton("🔴 Red", callback_data=f"persist_setcol_{pid}_red"),
         InlineKeyboardButton("⚪ Default", callback_data=f"persist_setcol_{pid}_none")],
        [InlineKeyboardButton("🔙 Back", callback_data="persist_panel")],
    ]
    await _safe_edit(q,
        f"🎨 *Background Color for `{pid}`*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"Current: `{_persist_color_label(pid)}`\n\n"
        f"_(REAL button background — Bot API 9.4 support. Owner ke paas "
        f"Telegram Premium ho to colors render hote hain.)_",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def persist_setcol_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    raw = q.data.replace("persist_setcol_", "")
    pid, _, color = raw.rpartition("_")
    try:
        from database import set_setting
        set_setting(f"persist_color_{pid}", "" if color == "none" else color)
    except Exception:
        await q.answer("❌ Save failed", show_alert=True); return
    await q.answer("✅ Color saved")
    await persist_panel_callback(update, context)


async def persist_rename_callback(update, context):
    """🆕 v170.12: start rename for one persistent button."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = q.data.replace("persist_ren_", "")
    from keyboards import get_persist_label
    cur = get_persist_label(pid)
    context.user_data["persist_ren_pid"] = pid
    await _safe_edit(q,
        f"✏️ *Rename Persistent Button*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"ID: `{pid}`\nCurrent: `{cur}`\n\n"
        f"Type new label (max 40 chars). Premium emoji bhejo to wo button ka "
        f"*icon* ban jayega (Bot API 9.4).\n"
        f"_(Send `-` to reset to default, /cancel to abort)_",
        parse_mode="Markdown")


async def persist_rename_received(update, context):
    """🆕 v170.15: save renamed persistent button label + PREMIUM EMOJI ICON
    (KeyboardButton.icon_custom_emoji_id — Bot API 9.4 support)."""
    pid = context.user_data.get("persist_ren_pid")
    if not pid:
        context.user_data.pop("persist_ren_pid", None)
        return False
    val = (update.message.text or "").strip()
    if val == "/cancel":
        context.user_data.pop("persist_ren_pid", None)
        await update.message.reply_text("❌ Cancelled.")
        return True
    try:
        from database import set_setting
        if val == "-":
            set_setting(f"persist_label_{pid}", "")
            set_setting(f"persist_emoji_{pid}", "")
            context.user_data.pop("persist_ren_pid", None)
            await update.message.reply_text("♻️ Reset to default ✅")
            return True
        if len(val) > 40:
            await update.message.reply_text("❌ Too long (max 40 chars). Try again or /cancel")
            return True
        # premium emoji capture → icon_custom_emoji_id (first custom emoji)
        emoji_id = ""
        try:
            ce = [e for e in (update.message.entities or [])
                  if getattr(e, "type", "") == "custom_emoji"]
            if ce:
                emoji_id = str(ce[0].custom_emoji_id or "")
        except Exception:
            emoji_id = ""
        # button TEXT clean (custom emoji fallback char hata do jab icon laga)
        label_text = val
        if emoji_id:
            try:
                import re as _re
                # pehla emoji cluster hatao (icon replace karega)
                label_text = _re.sub(r'^\s*[^\w\s]+\uFE0F?\s*', '', label_text, count=1).strip()
                label_text = label_text or val
            except Exception:
                label_text = val
        set_setting(f"persist_label_{pid}", label_text)
        set_setting(f"persist_emoji_{pid}", emoji_id)
    except Exception:
        context.user_data.pop("persist_ren_pid", None)
        return True
    context.user_data.pop("persist_ren_pid", None)
    note = "\n⭐ Premium emoji icon bhi set ho gaya." if emoji_id else ""
    await update.message.reply_text(
        f"✅ Persistent button `{pid}` → `{label_text}` saved.{note}\n"
        f"_Agli baar user ka menu open hoga to naya label + color + icon dikhega._",
        parse_mode="Markdown")
    return True


async def persist_move_callback(update, context):
    """🆕 v170.12: reorder persistent buttons (up/down)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    # persist_move_<pid>_<dir>
    raw = q.data.replace("persist_move_", "")
    pid, _, direction = raw.rpartition("_")
    try:
        from keyboards import get_persist_order
        from database import set_setting
        order = get_persist_order()
        if pid not in order:
            await q.answer("❌ Unknown button", show_alert=True); return
        i = order.index(pid)
        j = i - 1 if direction == "up" else i + 1
        if j < 0 or j >= len(order):
            await q.answer("⚠️ Already at edge", show_alert=True); return
        order[i], order[j] = order[j], order[i]
        set_setting("persist_order", ",".join(order))
    except Exception as e:
        await q.answer(f"❌ {e}", show_alert=True); return
    await persist_panel_callback(update, context)


async def cz_noop_callback(update, context):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass


# ── 🔍 SEARCH ─────────────────────────────────────────────────
async def cz_search_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data["cz_search"] = True
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="admin_customization")]]
    await _safe_edit(q,
        "🔍 *Search*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Type a button name, button ID, screen name, or response key —\n"
        "I'll find it and open its editor.\n\n"
        "Examples: `main_shop`, `shop`, `welcome`, `bybit`, `verify`",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cz_search_received(update, context):
    if update.effective_user.id != ADMIN_ID:
        context.user_data.pop("cz_search", None); return False
    if not context.user_data.get("cz_search"):
        return False
    context.user_data.pop("cz_search", None)
    q = update.effective_user.id
    term = (update.message.text or "").strip().lower()
    if not term or term == "/cancel":
        await update.message.reply_text("❌ Cancelled.")
        return True
    results = []

    # 1) buttons registry
    try:
        from button_system import BUTTONS
        for bid, info in BUTTONS.items():
            if term in bid.lower() or term in str(info.get("medium", "")).lower():
                results.append(("🎛️ Button", bid, f"mbedit_{bid}"))
    except Exception:
        pass
    # 2) screens
    try:
        import customization as _cz
        for sid, node in _cz.SCREEN_TREE.items():
            if term in sid.lower() or term in str(node.get("title", "")).lower():
                results.append(("📱 Screen", sid, f"se_open_{sid}"))
    except Exception:
        pass
    # 3) response keys
    try:
        from config import DEFAULT_RESPONSES
        for k in DEFAULT_RESPONSES:
            if term in k.lower():
                results.append(("📝 Response", k, f"editresp_{k}"))
    except Exception:
        pass

    if not results:
        await update.message.reply_text(
            f"❌ *No match* for `{term}`.\n\nTry a different word, or use /cancel.",
            parse_mode="Markdown")
        return True

    kb = []
    for kind, name, cb in results[:18]:
        kb.append([InlineKeyboardButton(f"{kind} {name[:40]}", callback_data=cb)])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_customization")])
    await update.message.reply_text(
        f"✅ *{len(results)} match(es)* for `{term}`:\n\n_Tap to open its editor._",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return True


# ── 🎭 THEME PRESETS ───────────────────────────────────────────
_THEMES = {
    "classic":   {"button_size": "medium", "menu_style": "classic",
                  "display_format": "raw", "main_menu_layout": "classic",
                  "grpstyle_main": "", "grpstyle_shop": "", "grpstyle_admin": ""},
    "colorful":  {"button_size": "large",  "menu_style": "colorful",
                  "display_format": "raw", "main_menu_layout": "colorful",
                  "grpstyle_main": "success", "grpstyle_shop": "primary",
                  "grpstyle_admin": "danger"},
    "dark":      {"button_size": "medium", "menu_style": "dark",
                  "display_format": "raw", "main_menu_layout": "dark",
                  "grpstyle_main": "", "grpstyle_shop": "", "grpstyle_admin": ""},
    "minimal":   {"button_size": "small",  "menu_style": "minimal",
                  "display_format": "list", "main_menu_layout": "minimal",
                  "grpstyle_main": "", "grpstyle_shop": "", "grpstyle_admin": ""},
    "premium":   {"button_size": "xl",     "menu_style": "premium",
                  "display_format": "grid", "main_menu_layout": "premium",
                  "grpstyle_main": "primary", "grpstyle_shop": "success",
                  "grpstyle_admin": "danger"},
}

async def cz_theme_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    kb = []
    for key, cfg in _THEMES.items():
        emoji = {"classic": "🔵", "colorful": "🌈", "dark": "🌑",
                 "minimal": "⚪", "premium": "💎"}.get(key, "🎨")
        kb.append([InlineKeyboardButton(f"{emoji} {key.title()} Theme",
                                        callback_data=f"cz_theme_{key}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_customization")])
    await _safe_edit(q,
        "🎭 *Theme Presets (1-click)*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Apply a full look instantly — button size, menu style, shop format,\n"
        "main-menu layout and group colors all at once.\n\n"
        "_Tap a theme to apply it. You can change anything after._",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cz_theme_apply_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    key = (q.data or "").replace("cz_theme_", "")
    cfg = _THEMES.get(key)
    if not cfg:
        await q.answer("Unknown theme", show_alert=True); return
    for k, v in cfg.items():
        _cz_set(k, v)
    # apply layout via the layout engine if available
    try:
        from main_menu_layouts import apply_layout_by_id
        apply_layout_by_id(cfg.get("main_menu_layout", ""))
    except Exception:
        pass
    await q.answer(f"✅ {key.title()} theme applied!", show_alert=True)
    await _render_customization_hub(q)


# ── 💾 BACKUP / RESTORE ────────────────────────────────────────
_BACKUP_KEYS_PREFIXES = ("btn_label_", "btn_style_", "grpstyle_", "btn_hidden_",
                         "btn_order_", "scrpad_", "bstyle_", "main_menu_layout",
                         "menu_style", "button_size", "display_format",
                         "pd_", "react_", "tplbtn", "tplbtnemoji", "fj_verify",
                         "shop_categorized", "auto_", "show_", "product_emoji")

def _collect_backup():
    import json as _json
    from database import get_connection
    out = {}
    conn = get_connection(); c = conn.cursor()
    for (key, value) in c.execute("SELECT key, value FROM bot_settings").fetchall():
        if key.startswith(_BACKUP_KEYS_PREFIXES) or key in (
                "button_size", "menu_style", "display_format",
                "main_menu_layout", "shop_categorized", "product_emoji"):
            out[key] = value
    conn.close()
    return _json.dumps(out, ensure_ascii=False, indent=1)


async def cz_backup_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        payload = _collect_backup()
    except Exception as e:
        await q.answer(f"❌ {e}", show_alert=True); return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Restore from Backup", callback_data="cz_import")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_customization")],
    ])
    await _safe_edit(q,
        "💾 *Customization Backup*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Copy the JSON below and save it somewhere safe. "
        "To restore later, tap *Restore* and paste it back.\n\n"
        "```json\n" + payload[:900] + "\n```\n\n"
        f"_Full backup: {len(payload)} chars — shows preview only._",
        parse_mode="Markdown", reply_markup=kb)


async def cz_import_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data["cz_import"] = True
    kb = [[InlineKeyboardButton("🔙 Cancel", callback_data="admin_customization")]]
    await _safe_edit(q,
        "📥 *Restore Customization*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Paste the backup JSON you saved earlier.\n\n"
        "_This overwrites current customization settings only._",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cz_import_received(update, context):
    if update.effective_user.id != ADMIN_ID:
        context.user_data.pop("cz_import", None); return False
    if not context.user_data.get("cz_import"):
        return False
    context.user_data.pop("cz_import", None)
    import json as _json
    raw = (update.message.text or "").strip()
    # strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.lstrip("json").strip()
    try:
        data = _json.loads(raw)
    except Exception as e:
        await update.message.reply_text(f"❌ Invalid JSON: {e}")
        return True
    if not isinstance(data, dict):
        await update.message.reply_text("❌ Expected a JSON object.")
        return True
    n = 0
    for k, v in data.items():
        try:
            _cz_set(k, str(v))
            n += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Restored *{n}* settings.", parse_mode="Markdown")
    return True


# ── 🖼️ HOME BANNER ─────────────────────────────────────────────
async def cz_banner_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    on = _cz_setting("home_banner_enabled", "0") == "1"
    text = _cz_setting("home_banner_text", "") or "(empty)"
    kb = [
        [InlineKeyboardButton(f"🖼️ Banner: {'ON' if on else 'OFF'}", callback_data="cz_banner_toggle")],
        [InlineKeyboardButton("✏️ Set Banner Text", callback_data="cz_banner_text")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_customization")],
    ]
    await _safe_edit(q,
        f"🖼️ *Home Banner*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Status: {'🟢 ON' if on else '🔴 OFF'}\n"
        f"Text: `{text[:60]}`\n\n"
        f"_Shows a welcome banner line in the shop/welcome message._",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cz_banner_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    cur = _cz_setting("home_banner_enabled", "0")
    _cz_set("home_banner_enabled", "0" if cur == "1" else "1")
    await cz_banner_callback(update, context)


async def cz_banner_text_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data["cz_banner_text"] = True
    kb = [[InlineKeyboardButton("🔙 Cancel", callback_data="cz_banner")]]
    await _safe_edit(q,
        "✏️ *Banner Text*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send the banner text (premium emoji allowed).\n"
        "Use `{shop_name}` for the shop name.",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cz_banner_text_received(update, context):
    if update.effective_user.id != ADMIN_ID:
        context.user_data.pop("cz_banner_text", None); return False
    if not context.user_data.get("cz_banner_text"):
        return False
    context.user_data.pop("cz_banner_text", None)
    txt = (update.message.text or "").strip()
    try:
        from utils import capture_user_text
        txt = capture_user_text(update.message) or txt
    except Exception:
        pass
    _cz_set("home_banner_text", txt)
    _cz_set("home_banner_enabled", "1")
    await update.message.reply_text("✅ *Banner saved & enabled.*", parse_mode="Markdown")
    return True


# ── 🏷️ CATEGORY COLORS ─────────────────────────────────────────
async def cz_catcolors_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        cats = c.execute("SELECT id, name, emoji FROM categories ORDER BY id").fetchall()
        conn.close()
    except Exception:
        cats = []
    kb = []
    for cat in cats:
        cid = cat["id"]
        cur = _cz_setting(f"catcolor_{cid}", "")
        mark = {"primary": "🔵", "success": "🟢", "danger": "🔴"}.get(cur, "⬜")
        nm = (cat.get("name") or "?")[:20]
        kb.append([InlineKeyboardButton(f"{mark} {nm}",
                                        callback_data=f"cz_catcolor_{cid}_none")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_customization")])
    await _safe_edit(q,
        "🏷️ *Category Colors*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Pick a color per category (applies to its shop buttons).\n"
        "_Tap a category then choose color._",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cz_catcolor_set_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    parts = (q.data or "").split("_")
    # cz_catcolor_<cid>_<color>
    try:
        cid = parts[2]
        color = parts[3] if len(parts) > 3 else "none"
        _cz_set(f"catcolor_{cid}", "" if color == "none" else color)
    except Exception:
        pass
    await cz_catcolors_callback(update, context)


# ── 🎠 DISPLAY FORMAT EXTENSION (grid/list/card) ───────────────
async def cz_format_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    cur = _cz_setting("display_format", "raw")
    def mk(label, val):
        mark = " ✅" if cur == val else ""
        return InlineKeyboardButton(label + mark, callback_data=f"cz_fmt_{val}")
    kb = [
        [mk("📋 Raw — Classic list", "raw")],
        [mk("🎠 Carousel — swipe cards", "carousel")],
        [mk("🔲 Grid — 2-column compact", "grid")],
        [mk("📄 List — 1-per-row full", "list")],
        [mk("🔙 Back", "admin_customization")],
    ]
    await _safe_edit(q,
        "🎠 *Display Format*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: *{cur}*\n\nChoose how products appear in the shop:",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cz_fmt_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    val = (q.data or "").replace("cz_fmt_", "")
    if val not in ("raw", "carousel", "grid", "list"):
        val = "raw"
    _cz_set("display_format", val)
    await q.answer(f"✅ Format: {val}", show_alert=True)
    await cz_format_callback(update, context)


# ════════════════════════════════════════════════════════════
# 🆕 v145 — USER SEARCH (by user ID or username)
# ════════════════════════════════════════════════════════════
async def adm_users_search_callback(u, c):
    """Ask for a user ID or username to search."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    c.user_data["adm_users_search"] = True
    kb = [[InlineKeyboardButton("🔙 Cancel", callback_data="admin_users")]]
    await _safe_edit(q,
        "🔍 *Search User*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send a Telegram **User ID** (e.g. `7105782769`)\n"
        "or a **username** (e.g. `@alex` or `alex`).\n\n"
        "_Matches are case-insensitive and partial._",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def adm_users_search_received(update, context):
    if update.effective_user.id != ADMIN_ID:
        context.user_data.pop("adm_users_search", None); return False
    if not context.user_data.get("adm_users_search"):
        return False
    context.user_data.pop("adm_users_search", None)
    term = (update.message.text or "").strip()
    if not term or term.lower() == "/cancel":
        await update.message.reply_text("❌ Cancelled.")
        return True

    from database import get_connection
    conn = get_connection(); c = conn.cursor()
    term_l = term.lower().lstrip("@")
    results = []
    try:
        # numeric → exact/prefix by user_id
        if term_l.isdigit():
            c.execute("SELECT * FROM users WHERE user_id LIKE ? ORDER BY user_id DESC LIMIT 20",
                      (f"%{term_l}%",))
            results = c.fetchall()
        else:
            # username OR first_name partial match (case-insensitive)
            c.execute("""SELECT * FROM users
                         WHERE lower(username) LIKE ? OR lower(first_name) LIKE ?
                         ORDER BY user_id DESC LIMIT 20""",
                      (f"%{term_l}%", f"%{term_l}%"))
            results = c.fetchall()
    except Exception as e:
        conn.close()
        await update.message.reply_text(f"❌ Search error: {e}")
        return True
    conn.close()

    if not results:
        await update.message.reply_text(
            f"❌ *No user found* for `{term}`.", parse_mode="Markdown")
        return True

    text = f"🔍 *Results for* `{term}` — *{len(results)}* found:\n━━━━━━━━━━━━━━━━━━━━\n\n"
    kb = []
    for usr in results[:15]:
        uid = usr["user_id"]
        uname = (usr["username"] or "").strip()
        fname = (usr["first_name"] or "?")
        uname_txt = f"@{uname}" if uname else "_no username_"
        text += f"• `{uid}` — {escape_md(fname)} ({uname_txt}) 💎{usr['points']}\n"
        label = f"📊 {uid} {('@'+uname) if uname else fname}"[:40]
        kb.append([InlineKeyboardButton(label, callback_data=f"adm_uact_{uid}")])
    kb.append([InlineKeyboardButton("🔙 Users List", callback_data="admin_users")])
    await update.message.reply_text(text[:3900], parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(kb))
    return True


# ════════════════════════════════════════════════════════════════
# 📊 v148: POLLS — admin creates a poll → broadcast to all users →
# users vote in-chat (native Telegram poll) → live results for admin.
# ════════════════════════════════════════════════════════════════

POLL_MAX_OPTIONS = 10


async def admin_polls_callback(u, c):
    """📊 Polls main panel: send/forward a poll + view results / manage."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    from database import get_polls
    polls = get_polls()
    text = (
        "📊 *Polls — User Demand / Opinion*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*How it works (easy):*\n"
        "1️⃣ Create the *poll yourself in Telegram* (any chat) or forward "
        "one from someone\n"
        "2️⃣ Send / forward that poll to *this bot's DM*\n"
        "3️⃣ Bot asks to confirm → tap ✅ → poll goes to *every user's inbox*\n"
        "4️⃣ Users vote — see live results in 📊 View Results; users also "
        "see results in their own chat\n\n"
        f"*Total polls:* {len(polls)}\n"
    )
    kb = [
        [InlineKeyboardButton("📤 Send / Forward a Poll", callback_data="poll_create")],
        [InlineKeyboardButton("📊 View Results", callback_data="poll_results")],
    ]
    if polls:
        kb.append([InlineKeyboardButton("📋 Last 5 Polls", callback_data="poll_list")])
    kb.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")])
    await _safe_edit(q, text, reply_markup=InlineKeyboardMarkup(kb))


async def poll_create_start_callback(u, c):
    """Step: tell admin to SEND/FORWARD a poll to the bot (no more wizard).
    🐛 v152 FIX: the old multi-step wizard (sawal → options → anon → time)
    got STUCK at the time step because the broadcast ran inside the callback
    (blocked 4-5 min for 900+ users → Telegram rate-limit + 'query too old').
    Now the admin creates the ORIGINAL Telegram poll themselves and just sends
    it to the bot — the bot rebroadcasts it in the background."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Polls", callback_data="admin_polls")]])
    await _safe_edit(q,
        "📤 *Send / Forward a Poll*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "1. Create the *poll yourself in Telegram* (any chat/group) — or "
        "forward one from someone\n"
        "2. Send / forward it to *this bot's DM*\n"
        "3. Bot asks \"Send to all users?\" → tap ✅ Yes\n"
        "4. Poll goes to *every user's inbox* (in background — bot never "
        "gets stuck)\n"
        "5. Users vote — see results in 📊 Polls → View Results; users also "
        "see results in their own chat\n\n"
        "_Regular polls only (anonymous/public + multiple answers carry over "
        "exactly as you made them)._\n\n"
        "👉 *Now send / forward the poll:*",
        parse_mode="Markdown", reply_markup=kb)


# ════════════════════════════════════════════════════════════════
# 🆕 v152: POLL FORWARD FLOW — admin creates the ORIGINAL Telegram poll
# themselves and sends/forwards it to the bot DM. The bot rebroadcasts it
# to every user's inbox in the BACKGROUND (never blocks the callback →
# fixes the old "stuck at time options" bug + 429 rate-limit log spam).
# ════════════════════════════════════════════════════════════════

async def handle_admin_poll_message(update, context):
    """Admin sent/forwarded a poll to the bot → capture it and ask to
    broadcast. Registered with MessageHandler(filters.POLL)."""
    try:
        msg = update.message
        if msg is None or msg.poll is None:
            return None
        # Only the admin's private chat counts
        try:
            if msg.from_user is None or msg.from_user.id != ADMIN_ID:
                return None
            chat_type = str(getattr(msg.chat, "type", "") or "")
            if chat_type != "private":
                return None
        except Exception:
            return None
        poll = msg.poll
        # A bot can only rebroadcast REGULAR polls (quiz needs correct_option_id)
        if getattr(poll, "type", "regular") == "quiz":
            try:
                await msg.reply_text(
                    "⚠️ Quiz polls forward nahi ho sakte — sirf *regular poll* "
                    "(ek ya multiple choice) bhejo/forward karo.",
                    parse_mode="Markdown")
            except Exception:
                pass
            return True
        options = []
        options_entities = []   # 🆕 v155: premium-emoji entities per option
        for o in (poll.options or []):
            t = str(getattr(o, "text", "") or "").strip()
            if t:
                options.append(t[:100])
                try:
                    ents = [e.to_dict() for e in (getattr(o, "text_entities", None) or [])]
                except Exception:
                    ents = []
                options_entities.append(ents)
        if len(options) < 2:
            try:
                await msg.reply_text("⚠️ Poll must have at least 2 options.")
            except Exception:
                pass
            return True
        question = str(getattr(poll, "question", "") or "")[:300]
        # 🆕 v155: capture question premium-emoji entities too
        try:
            question_entities = [e.to_dict() for e in (getattr(poll, "question_entities", None) or [])]
        except Exception:
            question_entities = []
        context.user_data["fwd_poll"] = {
            "question": question or "Poll",
            "options": options,
            "question_entities": question_entities,
            "options_entities": options_entities,
            "is_anonymous": bool(getattr(poll, "is_anonymous", True)),
            "allows_multiple": bool(getattr(poll, "allows_multiple_answers", False)),
            "close_date": getattr(poll, "close_date", None),
        }
        prev = (str(question) or "Poll")[:60]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, send to all users", callback_data="fwd_poll_yes")],
            [InlineKeyboardButton("❌ No, cancel", callback_data="fwd_poll_no")],
        ])
        await msg.reply_text(
            f"📊 *Poll captured!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"❓ {prev}\n"
            f"🔢 Options: {len(options)}\n\n"
            f"Send this poll to *every user's inbox*?",
            parse_mode="Markdown", reply_markup=kb)
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[PollFwd] capture error: {e}")
        return True


async def fwd_poll_no_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    c.user_data.pop("fwd_poll", None)
    await q.answer("Cancelled")
    try:
        await q.edit_message_text("❌ Poll cancel kar diya.",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("🔙 Polls", callback_data="admin_polls")]]))
    except Exception:
        pass


async def fwd_poll_yes_callback(u, c):
    """Confirm → create DB poll row + launch BACKGROUND broadcast to ALL users
    (v153 flow restored per owner request — no destination chooser)."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    data = c.user_data.pop("fwd_poll", None)
    if not data:
        await q.answer("Poll data nahi mila — dobara poll bhejo.", show_alert=True)
        try:
            await q.edit_message_text("❌ Poll data missing. Please forward the poll again.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("🔙 Polls", callback_data="admin_polls")]]))
        except Exception:
            pass
        return
    from database import create_poll
    close_date = ""
    try:
        if data.get("close_date"):
            from datetime import datetime, timezone
            cd = data["close_date"]
            if hasattr(cd, "strftime"):
                close_date = cd.strftime("%Y-%m-%d %H:%M:%S")
            else:
                close_date = str(cd)
    except Exception:
        close_date = ""
    poll_id = create_poll(data["question"], data["options"],
                          is_anonymous=bool(data.get("is_anonymous", True)),
                          allows_multiple=bool(data.get("allows_multiple", False)),
                          close_date=close_date,
                          question_entities=data.get("question_entities") or [],
                          options_entities=data.get("options_entities") or [])
    if not poll_id:
        await q.answer("❌ Poll banane me error.", show_alert=True)
        return
    # 🐛 v152 FIX: broadcast in BACKGROUND so the callback returns instantly
    import asyncio as _aio
    try:
        _aio.create_task(_broadcast_poll_task(c.bot, poll_id, ADMIN_ID))
    except Exception:
        pass
    try:
        await q.edit_message_text(
            f"✅ *Poll created!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🧾 ID: `#{poll_id}`\n"
            f"📤 *Sending to all users in the background...*\n\n"
            f"Premium emojis preserved. A summary will be sent when done. "
            f"Votes: 📊 Polls → View Results (see WHO voted there).",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 View Results", callback_data="poll_results")],
                [InlineKeyboardButton("🔙 Polls", callback_data="admin_polls")],
            ]))
    except Exception:
        pass
    try:
        await q.answer("📢 Broadcasting…", show_alert=False)
    except Exception:
        pass


_POLL_BROADCASTING = set()  # poll_ids currently broadcasting (anti double-send)
_POLL_BROADCASTING = set()  # poll_ids currently broadcasting (anti double-send)
_POLL_BROADCASTING = set()  # poll_ids currently broadcasting (anti double-send)


async def _broadcast_poll_task(bot, poll_id, notify_uid=None):
    """Background broadcast to ALL users with rate-limit safety. Sends a
    summary message to the admin when done."""
    import asyncio as _aio
    if poll_id in _POLL_BROADCASTING:
        return
    _POLL_BROADCASTING.add(poll_id)
    try:
        # 🆕 v156: live progress animation for the admin
        from utils import BroadcastProgress
        _prog = None
        try:
            from database import get_all_users_for_broadcast
            _total = len(get_all_users_for_broadcast() or [])
        except Exception:
            _total = 0
        _prog = BroadcastProgress(bot, notify_uid, title="Poll Broadcast", total=_total)
        await _prog.start()
        sent, failed = await _broadcast_poll_to_users(bot, poll_id, progress=_prog)
        if _prog is not None:
            await _prog.finish(
                f"✅ *Poll Broadcast Complete*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🧾 Poll `#{poll_id}`\n"
                f"📤 Sent: *{sent}* users | ❌ Failed: *{failed}*\n\n"
                f"Votes (incl. who voted): 📊 Polls → View Results.")
        if notify_uid:
            try:
                await bot.send_message(
                    notify_uid,
                    f"🧾 Poll `#{poll_id}` — results dekhne ke liye 📊 Polls → View Results.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📊 View Results", callback_data="poll_results")],
                    ]))
            except Exception:
                pass
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[PollBroadcast] task error: {e}")
        if notify_uid:
            try:
                await bot.send_message(notify_uid, f"⚠️ Poll broadcast error: `{str(e)[:120]}`",
                                       parse_mode="Markdown")
            except Exception:
                pass
    finally:
        _POLL_BROADCASTING.discard(poll_id)


async def _broadcast_poll_to_users(bot, poll_id, progress=None):
    """Send the native Telegram poll to every registered user. Returns (sent, failed).
    🆕 v156: optional `progress` (BroadcastProgress) → live counting animation."""
    from database import get_poll, get_all_users_for_broadcast, add_tg_poll_ids
    import json as _json, asyncio as _aio
    poll = get_poll(poll_id)
    if not poll:
        return 0, 0
    try:
        options = _json.loads(poll.get("options_json") or "[]")
    except Exception:
        options = []
    if len(options) < 2:
        return 0, 0
    close_dt = None
    if poll.get("close_date"):
        try:
            from datetime import datetime, timezone
            close_dt = datetime.strptime(poll["close_date"], "%Y-%m-%d %H:%M:%S")
            # Telegram requires tz-aware UTC; naive would be interpreted wrong
            if close_dt.tzinfo is None:
                close_dt = close_dt.replace(tzinfo=timezone.utc)
        except Exception:
            close_dt = None
    # 🆕 v155: rebuild premium-emoji entities (question + options) so the
    # broadcast poll looks EXACTLY like the one the admin forwarded.
    try:
        from telegram import InputPollOption, MessageEntity
        q_ents = _json.loads(poll.get("question_entities_json") or "[]") if poll.get("question_entities_json") else []
        o_ents = _json.loads(poll.get("options_entities_json") or "[]") if poll.get("options_entities_json") else []
        question_entities = [MessageEntity.de_json(e, bot) for e in q_ents] if q_ents else None
        send_options = []
        for i, opt in enumerate(options):
            ent_list = o_ents[i] if i < len(o_ents) else []
            ents = [MessageEntity.de_json(e, bot) for e in ent_list] if ent_list else None
            send_options.append(InputPollOption(text=opt, text_entities=ents))
    except Exception:
        question_entities = None
        send_options = None
    if not send_options:
        send_options = list(options)

    try:
        users = get_all_users_for_broadcast()
    except Exception:
        users = []
    sent = failed = 0
    tg_ids = []
    for usr in users:
        uid = row_uid(usr)
        try:
            m = await bot.send_poll(
                chat_id=uid,
                question=poll.get("question", "Poll")[:300],
                options=send_options,
                question_entities=question_entities,
                is_anonymous=bool(poll.get("is_anonymous", 1)),
                allows_multiple_answers=bool(poll.get("allows_multiple", 0)),
                close_date=close_dt,
            )
            sent += 1
            try:
                if m.poll and m.poll.id:
                    tg_ids.append(str(m.poll.id))
            except Exception:
                pass
        except Exception:
            failed += 1
        # 🆕 v156: live progress counter
        if progress is not None:
            try:
                await progress.bump()
            except Exception:
                pass
        # 🐛 v152 FIX: 0.12s sleep = ~8 msgs/sec — stays under Telegram's
        # bot rate limit (avoids 429 flood that spammed the logs before).
        await _aio.sleep(0.12)
    if tg_ids:
        try:
            add_tg_poll_ids(poll_id, tg_ids)
        except Exception:
            pass
    return sent, failed


async def poll_results_callback(u, c):
    """List all polls with live vote counts."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    from database import get_polls, get_poll_results
    polls = get_polls()
    if not polls:
        await _safe_edit(q, "📊 *No polls yet.*\n\nAbhi koi poll nahi bana. ➕ Create Poll se banao.",
                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Create Poll", callback_data='poll_create')],
                                                            [InlineKeyboardButton("🔙 Polls", callback_data='admin_polls')]]))
        return
    lines = ["📊 *Poll Results*\n━━━━━━━━━━━━━━━━━━━━\n"]
    for p in polls[:10]:
        res = get_poll_results(p["id"])
        if not res:
            continue
        voters = res["total_voters"]
        status = "🟢 Live" if not res["closed"] else "⏹ Closed"
        lines.append(f"`#{p['id']}` {status} — 👥 {voters} votes\n{res['poll'].get('question','')[:60]}\n")
    text = "\n".join(lines)
    kb = []
    for p in polls[:10]:
        kb.append([InlineKeyboardButton(f"📊 #{p['id']} — {p.get('question','')[:35]}",
                                        callback_data=f"poll_detail_{p['id']}")])
    kb.append([InlineKeyboardButton("🔙 Polls", callback_data="admin_polls")])
    await _safe_edit(q, text[:3900], reply_markup=InlineKeyboardMarkup(kb))


async def poll_detail_callback(u, c):
    """Show per-option votes + close/delete buttons for one poll."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace('poll_detail_', ''))
    except Exception:
        await q.answer("Invalid", show_alert=True); return
    from database import get_poll_results
    res = get_poll_results(pid)
    if not res:
        await _safe_edit(q, "❌ Poll not found.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Polls", callback_data='poll_results')]]))
        return
    poll = res["poll"]
    status = "🟢 Live" if not res["closed"] else "⏹ Closed"
    lines = [
        f"📊 *Poll #{pid}* — {status}\n━━━━━━━━━━━━━━━━━━━━",
        f"❓ {poll.get('question','')}",
        f"👥 Total voters: *{res['total_voters']}*",
        "",
    ]
    total = max(1, res["total_voters"])
    # 🆕 v155: show WHO voted for each option (names + @usernames)
    for opt in res["options"]:
        pct = round(opt["votes"] * 100.0 / total)
        bar = "█" * (pct // 10)
        lines.append(f"{opt['option'][:45]}\n  {opt['votes']} votes ({pct}%) {bar}")
        for v in (opt.get("voters") or [])[:12]:
            nm = str(v.get("name") or "?")
            un = str(v.get("username") or "").strip()
            if un:
                lines.append(f"     👤 {escape_md(nm)} (@{escape_md(un)})")
            else:
                lines.append(f"     👤 {escape_md(nm)}")
        if len(opt.get("voters") or []) > 12:
            lines.append(f"     _... aur {len(opt['voters']) - 12} aur_")
    if poll.get("close_date"):
        lines.append(f"\n⏱ Close: `{poll['close_date']}` UTC")
    kb = []
    if not res["closed"]:
        kb.append([InlineKeyboardButton("⏹ Close Poll Now", callback_data=f"poll_close_{pid}")])
    kb.append([InlineKeyboardButton("🗑 Delete Poll", callback_data=f"poll_del_{pid}")])
    kb.append([InlineKeyboardButton("🔙 All Polls", callback_data="poll_results")])
    await _safe_edit(q, "\n".join(lines)[:3900], reply_markup=InlineKeyboardMarkup(kb))


async def poll_close_callback(u, c):
    """Close a poll now — mark inactive + best-effort stopPoll in all chats."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        pid = int(q.data.replace('poll_close_', ''))
    except Exception:
        await q.answer("Invalid", show_alert=True); return
    from database import set_poll_active, get_tg_poll_ids
    set_poll_active(pid, False)
    import asyncio as _aio
    _aio.create_task(_stop_poll_in_chats(c.bot, pid))
    await q.answer("⏹ Poll closed!", show_alert=True)
    await poll_detail_callback(u, c)


async def _stop_poll_in_chats(bot, poll_id):
    """Best-effort: stopPoll for every chat where the poll was sent."""
    try:
        from database import get_poll, get_tg_poll_ids
        poll = get_poll(poll_id)
        if not poll:
            return
        import json as _json
        try:
            opts = _json.loads(poll.get("options_json") or "[]")
        except Exception:
            opts = []
        from database import get_all_users_for_broadcast
        users = get_all_users_for_broadcast() or []
        for usr in users:
            uid = row_uid(usr)
            try:
                # find the message id: we don't store per-user message ids, so
                # use get_user_chat_poll_message if available; otherwise skip.
                mid = await _find_poll_message_id(bot, uid, poll_id)
                if mid:
                    await bot.stop_poll(chat_id=uid, message_id=mid)
            except Exception:
                pass
    except Exception:
        pass


async def _find_poll_message_id(bot, chat_id, poll_id):
    """We can't enumerate old messages; rely on stored message ids if the
    caller provided one via poll_message_ids_json (future). Return None."""
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT value FROM bot_settings WHERE key=?", (f"poll_msg_{poll_id}_{chat_id}",))
        r = c.fetchone(); conn.close()
        if r and r[0]:
            return int(r[0])
    except Exception:
        pass
    return None


async def poll_delete_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        pid = int(q.data.replace('poll_del_', ''))
    except Exception:
        await q.answer("Invalid", show_alert=True); return
    from database import delete_poll_row
    delete_poll_row(pid)
    await q.answer("🗑 Poll deleted!", show_alert=True)
    await poll_results_callback(u, c)


async def poll_cancel_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    for k in ('poll_step', 'poll_question', 'poll_options', 'poll_anon'):
        c.user_data.pop(k, None)
    await q.answer("Cancelled")
    await admin_polls_callback(u, c)


async def poll_list_callback(u, c):
    """📋 Last 5 polls (quick list)."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    from database import get_polls, get_poll_results
    polls = get_polls()[:5]
    if not polls:
        await poll_results_callback(u, c); return
    lines = ["📋 *Last 5 Polls*\n━━━━━━━━━━━━━━━━━━━━\n"]
    for p in polls:
        res = get_poll_results(p["id"])
        votes = res["total_voters"] if res else 0
        status = "🟢" if (res and not res["closed"]) else "⏹"
        lines.append(f"{status} `#{p['id']}` ({votes} votes) — {p.get('question','')[:55]}")
    kb = [[InlineKeyboardButton(f"📊 #{p['id']}", callback_data=f"poll_detail_{p['id']}") for p in polls[:3]]]
    kb.append([InlineKeyboardButton("🔙 Polls", callback_data="admin_polls")])
    await _safe_edit(q, "\n".join(lines)[:3900], reply_markup=InlineKeyboardMarkup(kb))


async def handle_poll_answer(update, context):
    """📊 v148: record a user's vote whenever Telegram delivers a PollAnswer."""
    try:
        pa = update.poll_answer
        if not pa:
            return
        tg_poll_id = str(getattr(pa, "poll_id", "") or "")
        user = getattr(pa, "user", None)
        option_ids = list(getattr(pa, "option_ids", []) or [])
        uid = getattr(user, "id", 0)
        if not tg_poll_id or not uid:
            return
        from database import find_poll_by_tg_id, record_poll_answer
        pid = find_poll_by_tg_id(tg_poll_id)
        if not pid:
            return
        # 🆕 v155: store voter name/username so results show WHO voted
        try:
            uname = str(getattr(user, "first_name", "") or "")[:120]
            utag = str(getattr(user, "username", "") or "")[:120]
        except Exception:
            uname, utag = "", ""
        record_poll_answer(pid, uid, option_ids, user_name=uname, username=utag)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# 💸 v149: REFUND BY USER ID (with reason) + per-user FULL HISTORY
# Admin can refund ANY user by ID — bot asks amount + reason, credits
# points, notifies the user with the reason, and it lands in history.
# ════════════════════════════════════════════════════════════════

async def adm_uhist_callback(u, c):
    """📋 Full history for one user: orders + points ledger (deposits/
    refunds/credits) + recent actions. Added in the 📊 activity view."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        uid = int(q.data.replace("adm_uhist_", ""))
    except Exception:
        await q.answer("Invalid", show_alert=True); return

    from database import get_user, get_user_points, get_connection
    user = get_user(uid)
    fname = (user['first_name'] if user and 'first_name' in user.keys() else None) or '?'
    uname = (user['username'] if user and 'username' in user.keys() else '') or ''
    pts = get_user_points(uid)

    conn = get_connection(); conn.row_factory = DictRow
    c2 = conn.cursor()
    # Orders
    c2.execute("""SELECT id, product_name, price, status, payment_method, created_at
                  FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 12""", (uid,))
    orders = [dict(r) for r in c2.fetchall()]
    # Points ledger (deposits/refunds/credits/debits)
    try:
        c2.execute("SELECT * FROM points_ledger WHERE user_id=? ORDER BY id DESC LIMIT 12", (uid,))
        ledger = [dict(r) for r in c2.fetchall()]
    except Exception:
        ledger = []
    conn.close()

    from user_tracking import get_user_clicks, pretty_event
    recent = get_user_clicks(uid, limit=8)

    lines = [
        f"📋 *Full History — {escape_md(fname)}* (`{uid}`)",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"👤 {('@'+escape_md(uname)) if uname else '_no username_'} | 💎 {pts} pts",
        "",
        f"📦 *Orders ({len(orders)}):*",
    ]
    if orders:
        for o in orders[:10]:
            st = {"delivered":"✅","refunded":"💸","cancelled":"❌","pending":"🟡"}.get(str(o["status"]),"🟡")
            pn = (str(o["product_name"] or "?")).replace("[[HTML]]","")
            if len(pn) > 30: pn = pn[:29] + "…"
            lines.append(f"  {st} `#{o['id']}` ${float(o['price'] or 0):.2f} {escape_md(pn)}")
    else:
        lines.append("  _No orders_")

    lines.append("")
    lines.append(f"💸 *Points Ledger ({len(ledger)}):*")
    if ledger:
        for l in ledger[:10]:
            t = {"deposit":"💳","refund":"💸","credit":"➕","debit":"➖"}.get(str(l.get("tx_type")),"•")
            desc = str(l.get("description") or "")[:40]
            lines.append(f"  {t} {float(l.get('amount') or 0):+.2f} — {escape_md(desc)}")
    else:
        lines.append("  _No ledger entries_")

    lines.append("")
    lines.append("🎯 *Recent actions:*")
    if recent:
        for action, ts in recent[:8]:
            lines.append(f"  `{(ts or '')[5:16]}` — {pretty_event(action)}")
    else:
        lines.append("  _No recorded actions_")

    kb = [
        [InlineKeyboardButton("💸 Refund This User", callback_data=f"adm_refund_uid_{uid}")],
        [InlineKeyboardButton("📊 Activity", callback_data=f"adm_uact_{uid}_pall"),
         InlineKeyboardButton("🔙 Users", callback_data="admin_users")],
    ]
    await _safe_edit(q, "\n".join(lines)[:3900], parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def adm_uhist_enter_callback(u, c):
    """📋 Full History by user ID — entry (asks for the ID)."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    c.user_data['ruid_step'] = 'uhist_id'
    await _safe_edit(q,
        "📋 *User Full History*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Jis user ki history dekhni hai uski *User ID* bhejo (number).\n\n"
        "_Orders + Points Ledger (deposits/refunds) + Actions dikhengi._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="ruid_cancel")]]))


async def adm_uhist_id_received(u, c):
    if u.effective_user.id != ADMIN_ID or c.user_data.get('ruid_step') != 'uhist_id':
        return False
    txt = (u.message.text or '').strip()
    if not txt.isdigit():
        await u.message.reply_text("❌ User ID number hota hai. Dobara bhejo:")
        return True
    uid = int(txt)
    c.user_data.pop('ruid_step', None)
    from database import get_user
    if not get_user(uid):
        await u.message.reply_text(
            "❌ Ye user DB me nahi mila.", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Users", callback_data="admin_users")]]))
        return True
    # show history by faking a callback renderer
    class _FakeQ:
        def __init__(self, uid):
            self.data = f"adm_uhist_{uid}"
            self.from_user = u.effective_user
        async def answer(self, *a, **k):
            return None
        async def edit_message_text(self, *a, **k):
            # fallback: just send a new message with same payload via u.message.reply_text
            try:
                text = a[0]; kwargs = k
                return await u.message.reply_text(text, **kwargs)
            except Exception:
                return None
        async def edit_message_caption(self, *a, **k):
            return None
    await adm_uhist_callback(type("_U", (), {"callback_query": _FakeQ(uid)})(), c)
    return True


async def adm_refund_uid_callback(u, c):
    """💸 Refund by User ID — entry. callback: adm_refund_uid  (or adm_refund_uid_<uid>)
    🐛 v157 FIX (Bug7): bulletproof — never throws, always answers the query."""
    q = u.callback_query
    try:
        if q.from_user.id != ADMIN_ID:
            await q.answer("❌", show_alert=True); return
    except Exception:
        return
    try:
        await q.answer()
    except Exception:
        pass
    direct_uid = None
    if q.data.startswith("adm_refund_uid_"):
        try:
            direct_uid = int(q.data.replace("adm_refund_uid_", ""))
        except Exception:
            direct_uid = None
    if direct_uid:
        c.user_data['ruid_user'] = direct_uid
        c.user_data['ruid_step'] = 'amt'
        from database import get_user
        usr = get_user(direct_uid)
        fname = (usr['first_name'] if usr and 'first_name' in usr.keys() else '?') if usr else '?'
        try:
            await _safe_edit(q,
                f"💸 *Refund User* (`{direct_uid}`)\n"
                f"👤 {escape_md(fname)}\n\n"
                f"*Refund amount (USD)* bhejo — points me convert ho kar add hoga.\n"
                f"Example: `5` = $5 → 50 points.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="ruid_cancel")]]))
        except Exception:
            try:
                await q.edit_message_text("💸 Refund amount (USD) type karo:",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="ruid_cancel")]]))
            except Exception:
                pass
        return
    c.user_data['ruid_step'] = 'id'
    try:
        await _safe_edit(q,
            "💸 *Refund by User ID*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "Jis user ko refund karna hai uski *User ID* bhejo (number).\n\n"
            "_User ID users list me `123456789` wala number hai._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="ruid_cancel")]]))
    except Exception:
        pass


async def adm_refund_uid_received(u, c):
    """Text step: receives user ID."""
    if u.effective_user.id != ADMIN_ID or c.user_data.get('ruid_step') != 'id':
        return False
    txt = (u.message.text or '').strip()
    if not txt.isdigit():
        await u.message.reply_text("❌ User ID number hota hai. Dobara bhejo:")
        return True
    uid = int(txt)
    from database import get_user, get_user_points
    usr = get_user(uid)
    if not usr:
        await u.message.reply_text(
            "❌ Ye user DB me nahi mila. User list me se ID check karo.\n"
            "ID dobara bhejo ya /cancel:", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Users", callback_data="admin_users")]]))
        c.user_data['ruid_step'] = 'id'
        return True
    c.user_data['ruid_user'] = uid
    c.user_data['ruid_step'] = 'amt'
    fname = usr['first_name'] if 'first_name' in usr.keys() else '?'
    uname = (usr['username'] if 'username' in usr.keys() else '') or ''
    pts = get_user_points(uid)
    await u.message.reply_text(
        f"✅ *User mil gaya:*\n"
        f"👤 {escape_md(fname)} (`{uid}`)\n"
        f"{('@'+escape_md(uname)) if uname else '_no username_'}\n"
        f"💎 Points: {pts}\n\n"
        f"*Refund amount (USD)* bhejo — points me convert ho kar add hoga.\n"
        f"Example: `5` = $5 → 50 points.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="ruid_cancel")]]))
    return True


async def adm_refund_uid_amt_received(u, c):
    """Text step: receives refund amount (USD)."""
    if u.effective_user.id != ADMIN_ID or c.user_data.get('ruid_step') != 'amt':
        return False
    uid = c.user_data.get('ruid_user')
    if not uid:
        c.user_data.pop('ruid_step', None)
        return False
    txt = (u.message.text or '').strip().replace("$", "").replace(",", "")
    try:
        amt = float(txt)
        if amt <= 0 or amt > 100000:
            raise ValueError
    except Exception:
        await u.message.reply_text("❌ Sahi amount (USD) bhejo, e.g. `5` ya `2.5`:")
        return True
    c.user_data['ruid_amt'] = amt
    c.user_data['ruid_step'] = 'reason'
    await u.message.reply_text(
        f"✅ Amount: *${amt:.2f}* → *{points_from_usd(amt):g} points*\n\n"
        f"*Refund ki wajah (reason)* likho — ye user ko dikhega aur history me save hoga.\n"
        f"Example: `Product out of stock` ya `Delivery issue`\n\n"
        f"_(Chaho to /skip kar ke default reason use ho sakta hai)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="ruid_cancel")]]))
    return True


async def adm_refund_uid_reason_received(u, c):
    """Text step: receives reason → confirm screen."""
    if u.effective_user.id != ADMIN_ID or c.user_data.get('ruid_step') != 'reason':
        return False
    reason = (u.message.text or '').strip()[:200] or "Refund"
    c.user_data['ruid_reason'] = reason
    c.user_data['ruid_step'] = 'confirm'
    uid = c.user_data['ruid_user']; amt = c.user_data['ruid_amt']
    from database import get_user, get_user_points
    usr = get_user(uid)
    fname = (usr['first_name'] if usr and 'first_name' in usr.keys() else '?') if usr else '?'
    pts_now = get_user_points(uid)
    pts_add = points_from_usd(amt)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm Refund", callback_data="ruid_confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="ruid_cancel")],
    ])
    await u.message.reply_text(
        f"🔄 *Refund Confirm*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 User: {escape_md(fname)} (`{uid}`)\n"
        f"💰 Amount: *${amt:.2f}*\n"
        f"💎 Points add: *{pts_add:g}* (ab {pts_now})\n"
        f"📝 Reason: *{escape_md(reason)}*\n\n"
        f"Confirm karo?",
        parse_mode="Markdown", reply_markup=kb)
    return True


async def adm_refund_uid_confirm_callback(u, c):
    """Execute the refund: credit points, notify user with reason, log history.
    🐛 v157 FIX (Bug7): bulletproof — try/except so it never 'sticks'."""
    q = u.callback_query
    try:
        if q.from_user.id != ADMIN_ID:
            await q.answer("❌", show_alert=True); return
    except Exception:
        return
    try:
        await q.answer("🔄 Processing refund…", show_alert=False)
    except Exception:
        pass
    uid = c.user_data.get('ruid_user')
    amt = c.user_data.get('ruid_amt')
    reason = c.user_data.get('ruid_reason') or 'Refund'
    for k in ('ruid_user', 'ruid_amt', 'ruid_reason', 'ruid_step'):
        c.user_data.pop(k, None)
    if not uid or not amt:
        try:
            await q.answer("Session expired — try again.", show_alert=True)
        except Exception:
            pass
        try:
            await q.edit_message_text("❌ Refund data missing.", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Users", callback_data="admin_users")]]))
        except Exception:
            pass
        return
    from database import add_points, get_user_points, get_user
    import time as _t
    pts = points_from_usd(amt)
    ok = add_points(uid, pts, tx_type='refund', description=f"Admin refund: {reason}",
                    event_id=f"admin_refund_uid_{uid}_{int(_t.time())}", order_id=0)
    new_bal = get_user_points(uid)
    usr = get_user(uid)
    fname = (usr['first_name'] if usr and 'first_name' in usr.keys() else '?') if usr else '?'
    # Notify the user
    try:
        from utils import smart_text_and_mode
        msg = (
            "💸 *Refund Received!*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ *{pts:g} Points* aapke wallet me add kar diye gaye.\n"
            f"💰 Amount: *${amt:.2f}*\n"
            f"📝 Reason: *{reason}*\n\n"
            f"💎 Naya balance: *{new_bal:g} Points*\n\n"
            f"Hamari taraf se inconvenience ke liye maazrat. 🙏"
        )
        send_t, send_m = smart_text_and_mode(msg, "Markdown")
        await c.bot.send_message(chat_id=uid, text=send_t, parse_mode=send_m,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Shop", callback_data="shop")],
                [InlineKeyboardButton("📜 My Orders", callback_data="my_orders")],
            ]))
        user_notified = True
    except Exception:
        user_notified = False
    await q.answer("✅ Refund done!")
    try:
        await q.edit_message_text(
            f"✅ *Refund Done!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 {escape_md(fname)} (`{uid}`)\n"
            f"💰 +${amt:.2f} → +{pts:g} points\n"
            f"📝 Reason: *{escape_md(reason)}*\n"
            f"💎 Naya balance: {new_bal:g}\n"
            f"🔔 User notified: {'✅' if user_notified else '❌ (bot blocked)'}\n\n"
            f"_History me saved — user ki 📋 Full History me dikhega._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 User History", callback_data=f"adm_uhist_{uid}")],
                [InlineKeyboardButton("🔙 Users", callback_data="admin_users")],
            ]))
    except Exception:
        pass


async def adm_refund_uid_cancel_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    for k in ('ruid_user', 'ruid_amt', 'ruid_reason', 'ruid_step'):
        c.user_data.pop(k, None)
    await q.answer("Cancelled")
    try:
        await admin_users_callback(u, c)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# 🆕 v157: BULK DISCOUNT — set a discount % on any products, users see the
# discounted price in the shop, and an alert (editable bc_discount template)
# goes to the fake-activity destination with a 🟢 Buy Now button carrying the
# product name + premium emoji (own name emoji / supplier fixed emoji).
# ════════════════════════════════════════════════════════════════

async def bulk_discount_start_callback(u, c):
    """🎉 v158: Bulk Discount — TIERED quantity pricing per product.
    Each product can have MULTIPLE tiers: qty 1→$1, 10→$0.89, 30→$0.52…
    The shop shows them on the product page and checkout auto-applies."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    await _bdiscount_prod_list(u, c, 0)


async def _bdiscount_prod_list(u, c, page=0):
    """v170.18: warranty/refund STYLE list — sirf in-stock + manual products
    (out-of-stock nahi). Premium emoji + green buttons + stock + tiers count."""
    q = u.callback_query
    products = list(get_all_products(include_hidden=True, include_inactive=True))
    # sirf buyable: in-stock (stock>0) YA manual delivery
    products = [p for p in products
                if (int(dict(p).get('stock', 0) or 0) > 0
                    or (dict(p).get('delivery_mode') or '') == 'manual')]
    try:
        from button_system import make_premium_button, extract_emoji_from_html
        _have = True
    except Exception:
        _have = False
    per = 8
    pages = max(1, (len(products) + per - 1) // per)
    page = max(0, min(int(page or 0), pages - 1))
    chunk = products[page * per:(page + 1) * per]
    lines = [
        "🎉 *Bulk Discount — Tiered Pricing*",
        "━━━━━━━━━━━━━━━━━━━━",
        "_(Sirf in-stock + manual products. Tap kar ke quantity tiers add karo.)_",
        "",
    ]
    kb = []
    for p in chunk:
        pid = int(p['id'])
        raw = str(dict(p).get('name') or f'#{pid}')
        stock = int(dict(p).get('stock', 0) or 0)
        is_manual = (dict(p).get('delivery_mode') or '') == 'manual'
        plain, eid = raw, ""
        if _have:
            try:
                _eid, _plain = extract_emoji_from_html(raw)
                if _plain:
                    plain = _plain
                eid = _eid or ""
            except Exception:
                pass
        plain = (plain or f'#{pid}').replace('\n', ' ').strip()
        stock_txt = "🟢 Unlimited (manual)" if is_manual else f"📦 {stock}"
        try:
            from database import get_product_tiers
            _tc = len(get_product_tiers(pid))
        except Exception:
            _tc = 0
        lines.append(f"{'✅' if _tc else '⬜'} #{pid} · {plain[:28]} · {stock_txt}" + (f" · {_tc} tiers" if _tc else ""))
        if _have:
            kb.append([make_premium_button(
                f"{'📊' if _tc else '➕'} {plain[:24]}", emoji_id=eid or None,
                style="success" if _tc else "primary",
                callback_data=f"bdisc_prod_{pid}")])
        else:
            kb.append([InlineKeyboardButton(
                f"{'📊' if _tc else '➕'} {plain[:24]}", callback_data=f"bdisc_prod_{pid}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton('⬅️ Prev', callback_data=f'bdisc_page_{page - 1}'))
    if page < pages - 1:
        nav.append(InlineKeyboardButton('Next ➡️', callback_data=f'bdisc_page_{page + 1}'))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton('🔙 Back to Edit Items', callback_data='admin_products')])
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))



async def bdisc_prod_callback(u, c):
    """Tier manager for ONE product."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("bdisc_prod_", ""))
    except Exception:
        await q.answer("Invalid", show_alert=True); return
    p = get_product(pid)
    if not p:
        await q.answer("❌ Not found", show_alert=True); return
    try:
        from utils import html_strip_tags
        name = html_strip_tags(str(p['name'] or f'#{pid}'))
    except Exception:
        name = str(p['name'] or f'#{pid}')
    from database import get_product_tiers
    tiers = get_product_tiers(pid)
    base = float(dict(p).get('price') or 0)
    lines = [
        f"📊 *Tier Pricing — {name[:60]}*\n",
        f"Base price (1 qty): *${base:.2f}*\n",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if tiers:
        lines.append("")
        lines.append("*Current tiers:*")
        for t in tiers:
            lines.append(f"  `{int(t['min_qty'])} qty` → ${float(t['unit_price']):.2f}")
    else:
        lines.append("")
        lines.append("_No tiers yet — only base price._")
    kb = [
        [InlineKeyboardButton("➕ Add Tier", callback_data=f"bdisc_addq_{pid}")],
    ]
    if tiers:
        for t in tiers:
            kb.append([InlineKeyboardButton(f"🗑 Remove {int(t['min_qty'])} qty → ${float(t['unit_price']):.2f}",
                                            callback_data=f"bdisc_rm_{pid}_{int(t['min_qty'])}")])
        # 🆕 v170.14: Save & Broadcast — saare tiers ke baad ek baar broadcast
        kb.append([InlineKeyboardButton("✅ Save & Broadcast", callback_data=f"bdisc_broadcast_{pid}")])
    kb.append([InlineKeyboardButton("🔙 All Products", callback_data="bdisc_start")])
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def bdisc_addq_callback(u, c):
    """Ask for min_qty of the new tier."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("bdisc_addq_", ""))
    except Exception:
        await q.answer("Invalid", show_alert=True); return
    c.user_data['bdisc_pid'] = pid
    c.user_data['bdisc_step'] = 'qty'
    await _safe_edit(q,
        "➕ *New Tier — Step 1/2*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "At what *minimum quantity* does this tier apply?\n"
        "Example: `10` means 10+ units get this price\n\n"
        "_Type the quantity (number):_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="bdisc_cancel")]]))


async def bdisc_qty_received(update, context):
    if update.effective_user.id != ADMIN_ID or context.user_data.get('bdisc_step') != 'qty':
        return False
    pid = context.user_data.get('bdisc_pid')
    if not pid:
        context.user_data.pop('bdisc_step', None)
        return False
    txt = (update.message.text or '').strip()
    try:
        qty = int(txt)
        if qty < 1 or qty > 9999:
            raise ValueError
    except Exception:
        await update.message.reply_text("❌ Enter a valid quantity (1-9999):")
        return True
    context.user_data['bdisc_qty'] = qty
    context.user_data['bdisc_step'] = 'price'
    p = get_product(pid)
    base = float(dict(p).get('price') or 0) if p else 0
    await update.message.reply_text(
        f"✅ Quantity: *{qty}*\n\n"
        f"➕ *Step 2/2* — what is the *unit price (USD)* at this quantity?\n"
        f"Base price: *${base:.2f}*\n\n"
        f"Example: `0.89` = $0.89 per unit when ordering {qty}+\n\n"
        f"_Type the price (number):_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="bdisc_cancel")]]))
    return True


async def bdisc_price_received(update, context):
    if update.effective_user.id != ADMIN_ID or context.user_data.get('bdisc_step') != 'price':
        return False
    pid = context.user_data.get('bdisc_pid')
    qty = context.user_data.get('bdisc_qty')
    if not pid or not qty:
        context.user_data.pop('bdisc_step', None)
        return False
    txt = (update.message.text or '').strip().replace("$", "").replace(",", "")
    try:
        price = float(txt)
        if price <= 0 or price > 100000:
            raise ValueError
    except Exception:
        await update.message.reply_text("❌ Enter a valid price (USD), e.g. `0.89`:")
        return True
    from database import set_product_tier
    set_product_tier(pid, qty, price)
    context.user_data.pop('bdisc_step', None)
    context.user_data.pop('bdisc_qty', None)
    context.user_data.pop('bdisc_pid', None)
    p = get_product(pid)
    try:
        from utils import html_strip_tags
        name = html_strip_tags(str(p['name'] if p else ''))
    except Exception:
        name = str(p['name'] if p else '')

    # 🐛 v170.14 FIX: pehle HAR tier add par broadcast fire hota tha (user ko
    # ek-ek tier ki alag broadcast milti thi). Ab broadcast NAHI — sirf tier
    # save hota hai; admin "✅ Save & Broadcast" button dabaye tab ek baar
    # broadcast hoga (saare tiers ke baad).
    await update.message.reply_text(
        f"✅ *Tier Added!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 {name[:50]}\n"
        f"`{qty} qty` → **${price:.2f}** per unit\n\n"
        f"➕ Aur tier add karne ke liye neeche *➕ Add Tier* dabao.\n"
        f"📢 Sab tiers set ho jayen to *✅ Save & Broadcast* dabao (ek baar).",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 This Product's Tiers", callback_data=f"bdisc_prod_{pid}")],
            [InlineKeyboardButton("🔙 All Products", callback_data="bdisc_start")],
        ]))
    return True


async def bdisc_broadcast_callback(u, c):
    """🆕 v170.14: Save & Broadcast — saare tiers set hone ke baad EK baar
    bulk-deal hype broadcast (selected destination par)."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("📢 Broadcasting…")
    try:
        pid = int(q.data.replace("bdisc_broadcast_", ""))
    except Exception:
        return
    try:
        from fake_engagement import _get_lowest_tier, broadcast_store_message
        from fake_engagement import generate_fake_username, get_name_style
        p = get_product(pid)
        _t = _get_lowest_tier(pid)
        if not p or not _t:
            await q.answer("⚠️ No tiers / product found", show_alert=True)
            return
        _tq, _tp = _t
        _base = float(dict(p).get("price") or _tp)
        _save = round(max(0.0, _base - _tp), 2)
        try:
            from utils import html_strip_tags
            name = html_strip_tags(str(p['name'] or ''))
        except Exception:
            name = str(p['name'] or '')
        _user = generate_fake_username(get_name_style())
        try:
            from customization import render_template as _rt
            _msg = _rt("bc_bulkdeal", {
                "user": _user, "product": name, "qty": str(_tq),
                "price": f"{_tp:.2f}", "base_price": f"{_base:.2f}",
                "saving": f"{_save:.2f}"})
        except Exception:
            _msg = None
        if not _msg:
            _msg = (f"📊 *Bulk Deal Alert!* 🎉\n\n"
                    f"👤 {_user} just grabbed {name} at bulk price!\n"
                    f"🛒 {_tq}+ qty → 💵 ${_tp:.2f} each\n"
                    f"❌ Base: ${_base:.2f} | 💸 Save ${_save:.2f} per unit\n\n"
                    f"🔥 Buy more, save more — tap below!")
        import asyncio as _aio
        _aio.create_task(broadcast_store_message(c.bot, _msg, pid=pid,
                                                 tpl_id="bc_bulkdeal"))
        await q.answer("✅ Bulk-deal broadcast sent to destination!", show_alert=True)
    except Exception as _e:
        await q.answer(f"❌ {_e}", show_alert=True)
    await bdisc_prod_callback(u, c)


async def bdisc_rm_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        raw = q.data.replace("bdisc_rm_", "")
        pid_s, qty_s = raw.rsplit("_", 1)
        pid, qty = int(pid_s), int(qty_s)
    except Exception:
        await q.answer("Invalid", show_alert=True); return
    from database import remove_product_tier
    remove_product_tier(pid, qty)
    await q.answer("🗑 Tier removed")
    await bdisc_prod_callback(u, c)


async def bdisc_page_callback(u, c):
    """Next/Prev in the tiered discount product list."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        page = int(q.data.replace("bdisc_page_", "") or 0)
    except Exception:
        page = 0
    await _bdiscount_prod_list(u, c, page)


async def bdisc_cancel_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    for k in ('bdiscount_products', 'bdiscount_pct', 'bdiscount_step', 'bdisc_pid', 'bdisc_qty', 'bdisc_step'):
        c.user_data.pop(k, None)
    await q.answer("Cancelled")
    try:
        await admin_products_callback(u, c)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# 🆕 v161: RESELLER API — ADMIN COMMANDS
# /resellerkey <user_id> [label]  → generate reseller key (shown once)
# /resellerkeys                    → list all reseller keys + balances
# /resellerrevoke <key_id>         → revoke a reseller key
# /resellermarkup <pct>            → global reseller markup %
# /resellerprice <pid> <usd>       → per-product reseller price (0 = auto)
# /reselleron <pid> | /reselleroff <pid> → reseller visibility toggle
# /resellerorders [user_id]        → recent reseller orders
# ════════════════════════════════════════════════════════════════

def _is_admin_uid(update):
    try:
        return int(update.effective_user.id) == int(ADMIN_ID)
    except Exception:
        return False


async def reseller_key_command(update, context):
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "🔑 *Generate Reseller Key*\n\nUsage:\n`/resellerkey <user_id> [label]`\n\n"
            "Example: `/resellerkey 123456789 AlexShop`", parse_mode="Markdown")
        return
    try:
        uid = int(str(args[0]).strip())
    except Exception:
        await update.message.reply_text("❌ Invalid user_id — digits only.")
        return
    label = " ".join(args[1:]) if len(args) > 1 else ""
    try:
        from reseller_api import generate_reseller_key
        key, prefix = generate_reseller_key(uid, label)
    except Exception as e:
        await update.message.reply_text(f"❌ Key generation failed: {e}")
        return
    try:
        u = get_user(uid)
        uname = ((u.get("first_name") if u else None) or (u.get("name") if u else None) or f"user {uid}")
    except Exception:
        uname = f"user {uid}"
    await update.message.reply_text(
        "✅ *New Reseller Key Generated!*\n\n"
        f"👤 Reseller: *{uname}* (`{uid}`)\n"
        f"🏷️ Label: {label or '—'}\n\n"
        f"🔑 *Key:*\n`{key}`\n\n"
        "Use header:\n`X-API-Key: " + key + "`\n\n"
        "📚 API Docs: `<your-url>/api-docs/`\n\n"
        "⚠️ *Save this key now — it is shown ONLY once!*",
        parse_mode="Markdown")


async def reseller_keys_command(update, context):
    if not _is_admin_uid(update):
        return
    try:
        from reseller_api import list_reseller_keys
        keys = list_reseller_keys()
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return
    if not keys:
        await update.message.reply_text("🔑 No reseller keys yet. Use `/resellerkey <user_id>`",
                                        parse_mode="Markdown")
        return
    lines = ["🔑 *Reseller Keys:*\n"]
    ppd = 10
    try:
        ppd = float(get_setting("reseller_points_per_dollar") or 10)
    except Exception:
        pass
    for k in keys[:25]:
        status = "🟢" if k.get("is_active") else "🔴"
        bal = 0
        try:
            pts = float(get_user_points(int(k.get("owner_id") or 0)) or 0)
            bal = pts / ppd if ppd else 0
        except Exception:
            pass
        lines.append(
            f"{status} `{k.get('key_prefix')}` → user `{k.get('owner_id')}` "
            f"(${bal:.2f}) reqs:{int(k.get('request_count') or 0)}\n"
            f"   {str(k.get('label') or '')[:40]}  /resellerrevoke {k.get('id')}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def reseller_revoke_command(update, context):
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: `/resellerrevoke <key_id>`", parse_mode="Markdown")
        return
    try:
        from reseller_api import revoke_reseller_key
        ok = revoke_reseller_key(int(args[0]))
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return
    await update.message.reply_text("✅ Key revoked" if ok else "❌ Key not found")


async def reseller_markup_command(update, context):
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if not args:
        cur = get_setting("reseller_markup_pct") or "0"
        await update.message.reply_text(
            f"📊 Current reseller markup: *{cur}%*\n\n"
            "Usage: `/resellermarkup <pct>`  (e.g. 25 = +25% on your cost)",
            parse_mode="Markdown")
        return
    try:
        pct = max(0.0, float(args[0]))
    except Exception:
        await update.message.reply_text("❌ Invalid percent")
        return
    set_setting("reseller_markup_pct", str(pct))
    await update.message.reply_text(f"✅ Reseller markup set to *{pct:g}%*", parse_mode="Markdown")


async def reseller_price_command(update, context):
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/resellerprice <product_id> <usd>`\n"
            "`0` = auto (cost × markup)", parse_mode="Markdown")
        return
    try:
        pid = int(args[0]); price = float(args[1])
    except Exception:
        await update.message.reply_text("❌ Invalid input")
        return
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE products SET reseller_price=? WHERE id=?", (price, pid))
        n = c.rowcount; conn.commit(); conn.close()
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return
    if n:
        p = get_product(pid)
        name = (dict(p).get("name") if p else None) or f"#{pid}"
        await update.message.reply_text(
            f"✅ Reseller price for *{name}* → *${price:g}*\n"
            f"(0 = auto markup)", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Product not found")


async def reseller_toggle_command(update, context, enable: bool):
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: `/reselleron <product_id>` or `/reselleroff <product_id>`",
                                        parse_mode="Markdown")
        return
    try:
        pid = int(args[0])
    except Exception:
        await update.message.reply_text("❌ Invalid product id")
        return
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE products SET reseller_enabled=? WHERE id=?", (1 if enable else 0, pid))
        n = c.rowcount; conn.commit(); conn.close()
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return
    p = get_product(pid)
    name = (dict(p).get("name") if p else None) or f"#{pid}"
    await update.message.reply_text(
        f"✅ Reseller visibility for *{name}* → {'ON' if enable else 'OFF'}" if n
        else "❌ Product not found", parse_mode="Markdown")


async def reseller_on_command(update, context):
    await reseller_toggle_command(update, context, True)


async def reseller_off_command(update, context):
    await reseller_toggle_command(update, context, False)


async def reseller_orders_command(update, context):
    if not _is_admin_uid(update):
        return
    args = context.args or []
    uid = None
    if args:
        try:
            uid = int(args[0])
        except Exception:
            pass
    try:
        from reseller_api import list_reseller_orders
        rows = list_reseller_orders(user_id=uid, limit=15)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return
    if not rows:
        await update.message.reply_text("📦 No reseller orders yet.")
        return
    lines = ["📦 *Reseller Orders (last 15):*\n"]
    for r in rows:
        st = {"delivered": "✅", "pending": "⏳", "failed": "❌", "refunded": "💸"}.get(
            r.get("status"), "❔")
        lines.append(f"{st} #{r['id']} u{r.get('user_id')} · {str(r.get('product_name'))[:25]} "
                     f"×{r.get('qty')} · ${float(r.get('usd_amount') or 0):.2f} · {r.get('status')} · {str(r.get('created_at'))[:16]}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ════════════════════════════════════════════════════════════════
# 🆕 v161.2: RESELLER API — MORE ADMIN COMMANDS
# /resellerdeliver <order_id> <delivery text...>  → manual delivery (pending)
# /resellerkeycfg <key_id> <markup%> [cost|price] → per-key pricing
# /resellerbase cost|price                        → global pricing base mode
# /resellerspend <key_id> <usd>                   → per-key spend limit (0=unlimited)
# /resellerproducts <key_id> all|<p1,p2>          → per-key allowed products
# /resellerip <key_id> all|<ip1,ip2>              → per-key IP whitelist
# /resellerwebhook <key_id> <url|off>             → per-key webhook URL
# ════════════════════════════════════════════════════════════════

async def reseller_deliver_command(update, context):
    """Manual delivery for a PENDING reseller order."""
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "📦 *Reseller Manual Delivery*\n\n"
            "Usage:\n`/resellerdeliver <order_id> <delivery text...>`\n\n"
            "Example:\n`/resellerdeliver 42 user:pass@account.com`",
            parse_mode="Markdown")
        return
    try:
        oid = int(args[0])
    except Exception:
        await update.message.reply_text("❌ Invalid order id")
        return
    text = " ".join(args[1:]).strip()
    try:
        from database import complete_reseller_order, get_reseller_order, get_api_key_row
        ok = complete_reseller_order(oid, text)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return
    if not ok:
        await update.message.reply_text(
            "❌ Order not found / already delivered. Pending reseller orders only.")
        return
    # Notify reseller via webhook (if key has one)
    try:
        order = get_reseller_order(oid)
        if order:
            krow = get_api_key_row(int(order.get("key_id") or 0))
            if krow:
                from reseller_api import _send_webhook
                _send_webhook(krow, "order.pending_completed", {
                    "orderId": str(oid), "status": "delivered",
                    "deliveredKeys": [text],
                    "deliveredKey": text,
                    "amount": round(float(order.get("usd_amount") or 0), 2)})
    except Exception:
        pass
    await update.message.reply_text(
        f"✅ Order *#{oid}* delivered to reseller!\n\n"
        f"📨 Delivery:\n{text[:400]}", parse_mode="Markdown")


async def reseller_keycfg_command(update, context):
    """Per-key pricing: markup % + base mode."""
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "💲 *Per-Key Reseller Pricing*\n\n"
            "Usage:\n`/resellerkeycfg <key_id> <markup%> [cost|price]`\n\n"
            "• markup% negative = discount (e.g. -10)\n"
            "• base: `cost` = aap ki supplier cost, `price` = aap ki selling price\n"
            "• Example: `/resellerkeycfg 5 -5 price`\n\n"
            "Keys list: `/resellerkeys`", parse_mode="Markdown")
        return
    try:
        kid = int(args[0]); pct = float(args[1])
    except Exception:
        await update.message.reply_text("❌ Invalid input")
        return
    base = ""
    if len(args) > 2:
        base = args[2].strip().lower()
        if base not in ("cost", "price"):
            await update.message.reply_text("❌ base must be `cost` or `price`", parse_mode="Markdown")
            return
    try:
        from database import update_api_key_fields, get_api_key_row
        upd = {"reseller_markup": pct}
        if base:
            upd["reseller_base_mode"] = base
        ok = update_api_key_fields(kid, **upd)
        krow = get_api_key_row(kid)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return
    if not ok:
        await update.message.reply_text("❌ Key not found")
        return
    await update.message.reply_text(
        f"✅ Key `{krow.get('key_prefix')}` pricing set:\n"
        f"• Markup: *{pct:g}%*\n• Base: *{base or krow.get('reseller_base_mode') or 'global'}*",
        parse_mode="Markdown")


async def reseller_base_command(update, context):
    """Global pricing base mode: cost | price."""
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if not args:
        cur = get_setting("reseller_base_mode") or "price"
        await update.message.reply_text(
            f"📊 Current base mode: *{cur}*\n\n"
            "• `cost` = supplier cost pe markup\n"
            "• `price` = aap ki selling price pe markup (discount bhi de sakte ho)\n\n"
            "Usage: `/resellerbase cost|price`", parse_mode="Markdown")
        return
    mode = args[0].strip().lower()
    if mode not in ("cost", "price"):
        await update.message.reply_text("❌ Sirf `cost` ya `price`", parse_mode="Markdown")
        return
    set_setting("reseller_base_mode", mode)
    await update.message.reply_text(f"✅ Global reseller base mode → *{mode}*", parse_mode="Markdown")


async def reseller_spend_command(update, context):
    """Per-key spend limit (USD)."""
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "💳 *Per-Key Spend Limit*\n\n"
            "Usage: `/resellerspend <key_id> <usd>`\n"
            "`0` = unlimited", parse_mode="Markdown")
        return
    try:
        kid = int(args[0]); usd = float(args[1])
        if usd < 0:
            usd = 0
    except Exception:
        await update.message.reply_text("❌ Invalid input")
        return
    try:
        from database import update_api_key_fields, get_api_key_row
        update_api_key_fields(kid, spend_limit_usd=usd)
        krow = get_api_key_row(kid)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return
    if not krow:
        await update.message.reply_text("❌ Key not found")
        return
    await update.message.reply_text(
        f"✅ Key `{krow.get('key_prefix')}` spend limit → "
        f"*${usd:g}*" + (" (unlimited)" if usd == 0 else ""), parse_mode="Markdown")


async def reseller_products_command(update, context):
    """Per-key allowed products."""
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "🗂️ *Per-Key Allowed Products*\n\n"
            "Usage: `/resellerproducts <key_id> all`\n"
            "       `/resellerproducts <key_id> 87,99,101`", parse_mode="Markdown")
        return
    try:
        kid = int(args[0])
    except Exception:
        await update.message.reply_text("❌ Invalid key id")
        return
    raw = args[1].strip()
    val = "" if raw.lower() == "all" else raw
    try:
        from database import update_api_key_fields, get_api_key_row
        update_api_key_fields(kid, allowed_products=val)
        krow = get_api_key_row(kid)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return
    if not krow:
        await update.message.reply_text("❌ Key not found")
        return
    await update.message.reply_text(
        f"✅ Key `{krow.get('key_prefix')}` allowed products → "
        f"*{'ALL' if not val else val}*", parse_mode="Markdown")


async def reseller_ip_command(update, context):
    """Per-key IP whitelist."""
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "🌐 *Per-Key IP Whitelist*\n\n"
            "Usage: `/resellerip <key_id> all`\n"
            "       `/resellerip <key_id> 1.2.3.4,5.6.7.8`\n\n"
            "`all` = koi bhi IP allow", parse_mode="Markdown")
        return
    try:
        kid = int(args[0])
    except Exception:
        await update.message.reply_text("❌ Invalid key id")
        return
    raw = args[1].strip()
    val = "" if raw.lower() == "all" else raw
    try:
        from database import update_api_key_fields, get_api_key_row
        update_api_key_fields(kid, ip_whitelist=val)
        krow = get_api_key_row(kid)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return
    if not krow:
        await update.message.reply_text("❌ Key not found")
        return
    await update.message.reply_text(
        f"✅ Key `{krow.get('key_prefix')}` IP whitelist → "
        f"*{'ALL' if not val else val}*", parse_mode="Markdown")


async def reseller_webhook_command(update, context):
    """Per-key webhook URL."""
    if not _is_admin_uid(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "🔔 *Per-Key Webhook*\n\n"
            "Usage: `/resellerwebhook <key_id> <url>`\n"
            "       `/resellerwebhook <key_id> off`\n\n"
            "Events: `order.delivered`, `order.pending`, `order.failed`,\n"
            "`order.pending_completed` — POST JSON", parse_mode="Markdown")
        return
    try:
        kid = int(args[0])
    except Exception:
        await update.message.reply_text("❌ Invalid key id")
        return
    raw = args[1].strip()
    if raw.lower() in ("off", "0", "none"):
        val = ""
    elif raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        val = raw[:500]
    else:
        await update.message.reply_text("❌ URL `http(s)://...` hona chahiye (ya `off`)", parse_mode="Markdown")
        return
    try:
        from database import update_api_key_fields, get_api_key_row
        update_api_key_fields(kid, webhook_url=val)
        krow = get_api_key_row(kid)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return
    if not krow:
        await update.message.reply_text("❌ Key not found")
        return
    await update.message.reply_text(
        f"✅ Key `{krow.get('key_prefix')}` webhook → "
        f"*{'OFF' if not val else val}*", parse_mode="Markdown")


# ════════════════════════════════════════════════════════════════
# 🆕 v161.3: SELF-SERVE KEY + RESELLER ADMIN PANEL (buttons)
# ════════════════════════════════════════════════════════════════

async def my_reseller_key_command(update, context):
    """SELF-SERVE: any user can generate their own reseller API key."""
    uid = int(update.effective_user.id)
    try:
        from reseller_api import generate_reseller_key, list_reseller_keys
        from database import get_user_points, get_setting
    except Exception as e:
        try: await update.message.reply_text(f"❌ {e}")
        except Exception: pass
        return
    keys = list_reseller_keys(user_id=uid)
    active = [k for k in keys if k.get("is_active")]
    if active:
        k = active[0]
        ppd = 10
        try: ppd = float(get_setting("reseller_points_per_dollar") or 10)
        except Exception: pass
        try: bal = float(get_user_points(uid) or 0) / ppd
        except Exception: bal = 0
        await update.message.reply_text(
            "🔑 *Your Reseller API Key*\n\n"
            f"Key prefix: `{k.get('key_prefix')}...`\n"
            f"Status: 🟢 Active\n"
            f"💳 Wallet: *${bal:.2f}* (points: {get_user_points(uid)})\n"
            f"📨 Requests: {int(k.get('request_count') or 0)}\n\n"
            "⚠️ Key plaintext sirf generate hote waqt dikhi thi — agar kho gayi to\n"
            "store owner se keh kar revoke + nayi key bana lo.\n\n"
            "📚 API Docs: `<BASE_URL>/api-docs/`",
            parse_mode="Markdown")
        return
    key, prefix = generate_reseller_key(uid, f"Self-serve {uid}")
    await update.message.reply_text(
        "✅ *Your Reseller API Key!*\n\n"
        f"🔑 `{key}`\n\n"
        "Use header:\n"
        f"`X-API-Key: {key}`\n\n"
        "📚 Docs: `<BASE_URL>/api-docs/`\n"
        "⚠️ *Save now — shown only ONCE!* Top up your wallet (💎 Buy Points) to order.",
        parse_mode="Markdown")


# ── Admin Panel ────────────────────────────────────────────────

async def admin_reseller_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        from reseller_api import list_reseller_keys
        from database import reseller_stats, reseller_top_keys, reseller_key_tracking, get_user
        st = reseller_stats()
        top = reseller_top_keys(limit=5)
    except Exception as e:
        await q.edit_message_text(f"❌ {e}")
        return
    text = (
        "📊 *Reseller Panel*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Keys: *{st.get('total_keys',0)}* (🟢 {st.get('active_keys',0)} active)\n"
        f"📦 Orders: *{st.get('total_orders',0)}* (✅ {st.get('delivered',0)} · ⏳ {st.get('pending',0)} · ❌ {st.get('failed',0)})\n"
        f"💰 Revenue: *${st.get('revenue_usd',0):,.2f}*\n\n"
        "*🏆 Top Resellers:*\n"
    )
    if top:
        for t in top[:5]:
            try:
                u = get_user(int(t.get("user_id") or 0))
                uname = (u.get("first_name") if u else None) or str(t.get("user_id"))
            except Exception:
                uname = str(t.get("user_id"))
            text += f"• {uname}: ${float(t.get('rev') or 0):,.2f} ({t.get('orders')} orders)\n"
    else:
        text += "• (koi orders nahi abhi)\n"
    kb = [
        [InlineKeyboardButton("🔑 Generate Key", callback_data="reseller_gen_panel")],
        [InlineKeyboardButton("📊 Dashboard", callback_data="reseller_dashboard_panel"),
         InlineKeyboardButton("📋 Resellers", callback_data="reseller_keys_panel")],
        [InlineKeyboardButton("📦 Orders", callback_data="reseller_orders_panel"),
         InlineKeyboardButton("💲 Pricing", callback_data="reseller_pricing_panel")],
        [InlineKeyboardButton("🗂️ Products", callback_data="reseller_admin_products"),
         InlineKeyboardButton("🔔 Webhooks Log", callback_data="reseller_webhooks_panel")],
        [InlineKeyboardButton("📥 Export Record", callback_data="reseller_export_panel")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")],
    ]
    await q.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(kb))


async def reseller_gen_panel_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data["rs_step"] = {"action": "gen_uid"}
    await q.edit_message_text(
        "🔑 *Generate Reseller Key*\n\n"
        "Send the reseller's *user_id* (digits):\n\n"
        "_(Send /cancel to cancel)_", parse_mode="Markdown")


async def reseller_keys_panel_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        from reseller_api import list_reseller_keys
        from database import reseller_key_stats, get_user
        keys = list_reseller_keys()
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    if not keys:
        await q.edit_message_text("🔑 No reseller keys yet.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Back", callback_data="reseller_panel")]]))
        return
    lines = ["📋 *Reseller Keys:*\n"]
    kb = []
    for k in keys[:20]:
        st_ = "🟢" if k.get("is_active") else "🔴"
        try:
            u = get_user(int(k.get("owner_id") or 0))
            uname = (u.get("first_name") if u else None) or str(k.get("owner_id"))
        except Exception:
            uname = str(k.get("owner_id"))
        # 🆕 v161.6: full record per key — user id, username, created (date/year), balance, profit
        try:
            ppd = float(get_setting("reseller_points_per_dollar") or 10)
            _bal = float(get_user_points(int(k.get("owner_id") or 0)) or 0) / ppd if ppd else 0
        except Exception:
            _bal = 0.0
        tr = reseller_key_tracking(int(k.get("id") or 0))
        created = str(k.get("created_at") or "")[:16]
        lines.append(
            f"{st_} `{k.get('key_prefix')}`\n"
            f"   👤 {uname} (id {k.get('owner_id')})\n"
            f"   🕐 {created} · 💳 ${_bal:.2f} · 📦 {tr.get('orders',0)} · 📈 ${tr.get('profit_usd',0):,.2f}"
        )
        kb.append([InlineKeyboardButton(f"{st_} {k.get('key_prefix')} (id {k.get('id')})",
                                        callback_data=f"reseller_keycfg_panel_{k.get('id')}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="reseller_panel")])
    await q.edit_message_text("\n".join(lines[:22]), parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(kb))


async def reseller_keycfg_panel_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        kid = int(q.data.replace("reseller_keycfg_panel_", ""))
        from database import get_api_key_row, reseller_key_stats, reseller_key_tracking, get_user, get_user_points, get_setting
        from reseller_api import reveal_reseller_key
        k = get_api_key_row(kid)
        ks = reseller_key_stats(kid)
        tr = reseller_key_tracking(kid)
        u = get_user(int(k.get("owner_id") or 0))
        uname = (u.get("first_name") if u else None) or str(k.get("owner_id"))
        ppd = 10
        try:
            ppd = float(get_setting("reseller_points_per_dollar") or 10)
        except Exception:
            pass
        bal = float(get_user_points(int(k.get("owner_id") or 0)) or 0) / ppd if ppd else 0
        full_key = reveal_reseller_key(kid)
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    base = k.get("reseller_base_mode") or "global"
    markup = k.get("reseller_markup")
    markup_txt = f"{markup:g}%" if markup is not None else "global"
    key_line = f"`{full_key}`" if full_key else f"`{k.get('key_prefix')}...` (key recoverable nahi)"
    text = (
        f"👤 *{uname}* — Reseller Detail\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Key: {key_line}\n"
        f"🆔 User: `{k.get('owner_id')}`\n"
        f"💳 Wallet: *${bal:.2f}*\n"
        f"💲 Markup: *{markup_txt}%* · Base: *{base}*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Orders: *{tr.get('orders',0)}* (✅ {tr.get('delivered',0)} · ⏳ {tr.get('pending',0)} · ❌ {tr.get('failed',0)})\n"
        f"💰 Revenue: *${tr.get('revenue_usd',0):,.2f}*\n"
        f"📈 Profit (est): *${tr.get('profit_usd',0):,.2f}*\n"
        f"💎 Points spent: {tr.get('points_spent',0):g}\n"
        f"🕐 Last order: {str(tr.get('last_order') or '—')[:16]}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Limits: spend ${0:g} · products {1} · IP {2} · webhook {3}".format(
            float(k.get('spend_limit_usd') or 0),
            k.get('allowed_products') or 'ALL',
            k.get('ip_whitelist') or 'ALL',
            'ON' if k.get('webhook_url') else 'OFF')
    )
    kb = [
        [InlineKeyboardButton("📦 Their Orders", callback_data=f"reseller_orders_key_{kid}"),
         InlineKeyboardButton("💳 Top-up", callback_data=f"reseller_topup_{kid}")],
        [InlineKeyboardButton("📥 Record (.txt)", callback_data=f"reseller_export_key_{kid}")],
        [InlineKeyboardButton("💰 Product Prices", callback_data=f"reseller_keyprices_{kid}")],
        [InlineKeyboardButton("💲 Markup %", callback_data=f"reseller_keyaction_{kid}_markup"),
         InlineKeyboardButton("🏷️ Base cost", callback_data=f"reseller_keyaction_{kid}_base_cost"),
         InlineKeyboardButton("🏷️ Base price", callback_data=f"reseller_keyaction_{kid}_base_price")],
        [InlineKeyboardButton("💳 Spend $", callback_data=f"reseller_keyaction_{kid}_spend"),
         InlineKeyboardButton("🗂️ Products", callback_data=f"reseller_keyaction_{kid}_products"),
         InlineKeyboardButton("🌐 IPs", callback_data=f"reseller_keyaction_{kid}_ip")],
        [InlineKeyboardButton("🔔 Webhook", callback_data=f"reseller_keyaction_{kid}_webhook"),
         InlineKeyboardButton("🚫 Revoke", callback_data=f"reseller_keyaction_{kid}_revoke")],
        [InlineKeyboardButton("🔙 Back", callback_data="reseller_keys_panel")],
    ]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def reseller_orders_key_callback(update, context):
    """Per-reseller orders list."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        kid = int(q.data.replace("reseller_orders_key_", ""))
        from database import reseller_key_orders, get_api_key_row
        rows = reseller_key_orders(kid, limit=15)
        k = get_api_key_row(kid)
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    if not rows:
        await q.edit_message_text(f"📦 Key `{k.get('key_prefix')}` — no orders yet.",
                                  parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("🔙 Back", callback_data=f"reseller_keycfg_panel_{kid}")]]))
        return
    lines = [f"📦 *Orders — {k.get('key_prefix')}*\n"]
    kb = []
    for r in rows:
        st = {"delivered": "✅", "pending": "⏳", "processing": "🔄", "failed": "❌"}.get(r.get("status"), "❔")
        lines.append(f"{st} #{r['id']} · {str(r.get('product_name'))[:22]} ×{r.get('qty')} · ${float(r.get('usd_amount') or 0):.2f} · {r.get('status')} · {str(r.get('created_at'))[:10]}")
        if r.get("status") in ("pending", "processing"):
            kb.append([InlineKeyboardButton(f"📤 Deliver #{r['id']}", callback_data=f"reseller_deliver_panel_{r['id']}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data=f"reseller_keycfg_panel_{kid}")])
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def reseller_topup_callback(update, context):
    """Top-up wizard: ask points amount for a key's owner."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        kid = int(q.data.replace("reseller_topup_", ""))
        from database import get_api_key_row
        k = get_api_key_row(kid)
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    context.user_data["rs_step"] = {"action": "topup", "key_id": kid}
    await q.edit_message_text(
        f"💳 Top-up for key `{k.get('key_prefix')}`\n\n"
        "Send *points* amount (e.g. `500`):\n"
        "_(1 point = $0.10 default)_\n\n_(/cancel to cancel)_",
        parse_mode="Markdown")


async def reseller_webhooks_callback(update, context):
    """Webhook delivery log."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT id, key_id, event, status, attempts, created_at FROM reseller_webhook_events ORDER BY id DESC LIMIT 15")
        rows = [dict(r) for r in c.fetchall()]; conn.close()
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    if not rows:
        await q.edit_message_text("🔔 *Webhooks Log*\n\n(koi events nahi abhi)",
                                  parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("🔙 Back", callback_data="reseller_panel")]]))
        return
    lines = ["🔔 *Webhooks Log (last 15):*\n"]
    for r in rows:
        st = {"sent": "✅", "pending": "⏳"}.get(r.get("status"), "❌")
        lines.append(f"{st} key {r.get('key_id')} · {r.get('event')} · attempts {r.get('attempts')} · {str(r.get('created_at'))[:16]}")
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="reseller_panel")]]
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def reseller_export_callback(update, context):
    """Export all reseller records as .txt."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        from reseller_api import list_reseller_keys
        from database import reseller_key_tracking, reseller_orders, get_user, get_user_points, get_setting
        keys = list_reseller_keys()
        lines = ["BITE STORE — RESELLER RECORD", "=" * 40, ""]
        total_rev = 0.0
        total_profit = 0.0
        for k in keys:
            kid = int(k.get("id") or 0)
            uid = int(k.get("owner_id") or 0)
            tr = reseller_key_tracking(kid)
            try:
                u = get_user(uid)
                uname = (u.get("first_name") if u else None) or str(uid)
            except Exception:
                uname = str(uid)
            lines.append(f"[{k.get('key_prefix')}] {uname} (id {uid})")
            lines.append(f"  Status: {'Active' if k.get('is_active') else 'Revoked'} | Created: {str(k.get('created_at') or '')[:10]}")
            lines.append(f"  Orders: {tr.get('orders',0)} (delivered {tr.get('delivered',0)}, pending {tr.get('pending',0)}, failed {tr.get('failed',0)})")
            lines.append(f"  Revenue: ${tr.get('revenue_usd',0):,.2f} | Profit(est): ${tr.get('profit_usd',0):,.2f} | Points spent: {tr.get('points_spent',0):g}")
            lines.append(f"  Requests: {int(k.get('request_count') or 0)} | Last used: {str(k.get('last_used_at') or '—')[:16]}")
            lines.append(f"  Markup: {k.get('reseller_markup') or 'global'} | Base: {k.get('reseller_base_mode') or 'global'}")
            lines.append(f"  Webhook: {'ON' if k.get('webhook_url') else 'OFF'}")
            lines.append("")
            total_rev += tr.get("revenue_usd", 0)
            total_profit += tr.get("profit_usd", 0)
        lines.append("=" * 40)
        lines.append(f"TOTAL REVENUE: ${total_rev:,.2f} | TOTAL PROFIT(est): ${total_profit:,.2f}")
        txt = "\n".join(lines)
        import io
        bio = io.BytesIO(txt.encode("utf-8"))
        bio.name = "resellers_record.txt"
        await context.bot.send_document(chat_id=ADMIN_ID, document=bio,
                                        caption="📊 Reseller record export")
    except Exception as e:
        try:
            await q.edit_message_text(f"❌ {e}")
        except Exception:
            pass
        return
    try:
        await q.edit_message_text("✅ Reseller record bhej diya (file).",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("🔙 Back", callback_data="reseller_panel")]]))
    except Exception:
        pass


async def reseller_export_key_callback(update, context):
    """Export ONE reseller's full order record as .txt."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        kid = int(q.data.replace("reseller_export_key_", ""))
        from reseller_api import list_reseller_keys
        from database import reseller_key_tracking, reseller_key_orders, get_api_key_row, get_user
        k = get_api_key_row(kid)
        tr = reseller_key_tracking(kid)
        rows = reseller_key_orders(kid, limit=200)
        u = get_user(int(k.get("owner_id") or 0))
        uname = (u.get("first_name") if u else None) or str(k.get("owner_id"))
        lines = [f"RESELLER RECORD — {k.get('key_prefix')} ({uname}, id {k.get('owner_id')})",
                 "=" * 40, ""]
        lines.append(f"Status: {'Active' if k.get('is_active') else 'Revoked'} | Created: {str(k.get('created_at') or '')[:10]}")
        lines.append(f"Orders: {tr.get('orders',0)} | Revenue: ${tr.get('revenue_usd',0):,.2f} | Profit(est): ${tr.get('profit_usd',0):,.2f}")
        lines.append("")
        lines.append("ORDERS:")
        for r in rows:
            lines.append(f"  #{r['id']} | {r.get('product_name')} x{r.get('qty')} | ${float(r.get('usd_amount') or 0):.2f} | {r.get('status')} | {str(r.get('created_at'))[:16]}")
        lines.append("")
        lines.append("=" * 40)
        import io
        bio = io.BytesIO("\n".join(lines).encode("utf-8"))
        bio.name = f"reseller_{k.get('key_prefix')}.txt"
        await context.bot.send_document(chat_id=ADMIN_ID, document=bio,
                                        caption=f"📊 {k.get('key_prefix')} record")
    except Exception as e:
        try:
            await q.edit_message_text(f"❌ {e}")
        except Exception:
            pass
        return
    try:
        await q.edit_message_text("✅ Record bhej diya (file).",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("🔙 Back", callback_data=f"reseller_keycfg_panel_{kid}")]]))
    except Exception:
        pass


async def reseller_keyaction_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        parts = q.data.replace("reseller_keyaction_", "").split("_")
        kid = int(parts[0]); action = "_".join(parts[1:])  # 🔧 v161.6: multi-word actions (base_cost/base_price)
    except Exception:
        await q.edit_message_text("❌ Invalid action"); return
    try:
        from database import get_api_key_row, update_api_key_fields
        k = get_api_key_row(kid)
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    if action == "revoke":
        try:
            from reseller_api import revoke_reseller_key
            revoke_reseller_key(kid)
        except Exception as e:
            await q.edit_message_text(f"❌ {e}"); return
        await q.edit_message_text(f"✅ Key `{k.get('key_prefix')}` revoked.",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("🔙 Back", callback_data="reseller_keys_panel")]]))
        return
    if action == "base_cost":
        update_api_key_fields(kid, reseller_base_mode="cost")
        await q.edit_message_text(f"✅ Key `{k.get('key_prefix')}` base → *cost*.",
                                  parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("🔙 Back", callback_data=f"reseller_keycfg_panel_{kid}")]]))
        return
    if action == "base_price":
        update_api_key_fields(kid, reseller_base_mode="price")
        await q.edit_message_text(f"✅ Key `{k.get('key_prefix')}` base → *price*.",
                                  parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("🔙 Back", callback_data=f"reseller_keycfg_panel_{kid}")]]))
        return
    # text-input actions
    prompt = {
        "markup":  "Send markup % (negative = discount), e.g. `20` or `-10`:",
        "spend":   "Send spend limit in USD (`0` = unlimited):",
        "products": "Send product ids comma-separated, or `all`:",
        "ip":      "Send IPs comma-separated, or `all`:",
        "webhook": "Send webhook URL, or `off`:",
    }.get(action)
    if not prompt:
        await q.edit_message_text("❌ Unknown action"); return
    context.user_data["rs_step"] = {"action": f"key_{action}", "key_id": kid}
    await q.edit_message_text(f"⚙️ Key `{k.get('key_prefix')}`\n\n{prompt}\n\n_(/cancel to cancel)_",
                              parse_mode="Markdown")


async def reseller_pricing_panel_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        from database import get_setting, set_setting
        markup = get_setting("reseller_markup_pct") or "0"
        base = get_setting("reseller_base_mode") or "price"
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    text = (f"💲 *Global Reseller Pricing*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Markup: *{markup}%* (negative = discount)\n"
            f"Base: *{base}*\n\n"
            "Base `cost` = supplier cost pe, `price` = aap ki selling price pe\n"
            "Per-reseller per-product price: Reseller Panel → kisi reseller → 💰 Product Prices")
    kb = [
        [InlineKeyboardButton("💲 Set Markup %", callback_data="reseller_price_markup")],
        [InlineKeyboardButton("🏷️ Base = cost", callback_data="reseller_base_mode_cost"),
         InlineKeyboardButton("🏷️ Base = price", callback_data="reseller_base_mode_price")],
        [InlineKeyboardButton("🔙 Back", callback_data="reseller_panel")],
    ]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def reseller_keyprices_callback(update, context):
    """🆕 v170.6: per-reseller per-product price overrides (specific ya ALL)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        kid = int(q.data.replace("reseller_keyprices_", ""))
    except Exception:
        await q.edit_message_text("❌ Invalid key"); return
    try:
        from database import get_api_key_row, get_all_products, list_reseller_key_prices
        from reseller_api import reseller_price_for
        from utils import html_strip_tags as _hs
        k = get_api_key_row(kid)
        products = get_all_products()
        overrides = {}
        for r in list_reseller_key_prices(kid):
            try:
                overrides[int(r.get("product_id") or 0)] = float(r.get("price_usd") or 0)
            except Exception:
                pass
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return

    lines = [f"💰 *Product Prices — `{k.get('key_prefix')}`*\n",
             "_(exact $ = override · +20% / -10% / +1.5 = adjust · `default` = remove)_\n"]
    kb = []
    # ALL products row
    all_p = overrides.get(0)
    all_txt = f"${all_p:g}" if all_p and all_p > 0 else "default"
    lines.append(f"🛍️ *ALL products:* {all_txt}")
    kb.append([InlineKeyboardButton(f"🛍️ ALL products → {all_txt}",
                                    callback_data=f"reseller_setprice_{kid}_0")])
    for p in products[:20]:
        pid = int(p["id"])
        pname = (_hs(str(p.get("name") or "")) or "Product")[:20]
        if pid in overrides:
            cur = overrides[pid]
            cur_txt = f"${cur:.2f}*"
        else:
            cur = reseller_price_for(dict(p), k)
            cur_txt = f"${cur:.2f}"
        lines.append(f"#{pid} {pname} → {cur_txt}")
        kb.append([InlineKeyboardButton(f"#{pid} {pname} ({cur_txt})",
                                        callback_data=f"reseller_setprice_{kid}_{pid}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data=f"reseller_keycfg_panel_{kid}")])
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(kb))


async def reseller_setprice_callback(update, context):
    """🆕 v170.6: wizard start — set price for key × product (0 = ALL)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        parts = q.data.replace("reseller_setprice_", "").split("_")
        kid = int(parts[0]); pid = int(parts[1])
    except Exception:
        await q.edit_message_text("❌ Invalid"); return
    try:
        from database import get_api_key_row
        from utils import html_strip_tags as _hs
        k = get_api_key_row(kid)
        label = f"key `{k.get('key_prefix')}` — ALL products"
        if pid:
            from database import get_product
            p = get_product(pid)
            if p:
                label = f"key `{k.get('key_prefix')}` — #{pid} {(_hs(str(p.get('name') or '')) or 'Product')[:24]}"
    except Exception:
        label = f"key #{kid} product #{pid}"
    context.user_data["rs_step"] = {"action": "key_prod_price", "key_id": kid, "product_id": pid}
    await q.edit_message_text(
        f"💰 Set price for {label}\n\n"
        "Send: exact $ (`5.00`) · `+20%` / `-10%` · `+1.5` / `-0.5` · `default` (remove)\n"
        "_(ALL products ke liye sirf exact $ ya `default`)_\n\n"
        "_(/cancel to cancel)_", parse_mode="Markdown")


async def reseller_price_markup_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data["rs_step"] = {"action": "markup"}
    await q.edit_message_text("💲 Send global markup % (negative = discount), e.g. `20` or `-10`:\n\n_(/cancel to cancel)_",
                              parse_mode="Markdown")


async def reseller_base_mode_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        mode = q.data.replace("reseller_base_mode_", "")
        from database import set_setting
        set_setting("reseller_base_mode", mode)
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    await q.edit_message_text(f"✅ Global reseller base → *{mode}*", parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(
                                  [[InlineKeyboardButton("🔙 Back", callback_data="reseller_pricing_panel")]]))


async def reseller_orders_panel_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    await _render_reseller_orders_panel(update, context, q)


async def reseller_orders_filter_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        kind, val = q.data.replace("reseller_orders_filter_", "").split("_", 1)
    except Exception:
        return
    flt = dict(context.user_data.get("rs_orders") or {"status": "all", "range": "all"})
    if kind == "status":
        flt["status"] = val
    elif kind == "range":
        flt["range"] = val
    context.user_data["rs_orders"] = flt
    await _render_reseller_orders_panel(update, context, q)


async def _render_reseller_orders_panel(update, context, q):
    """Reseller orders list with status + date filters (v161.6)."""
    try:
        from database import list_reseller_orders, get_connection
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    flt = dict(context.user_data.get("rs_orders") or {"status": "all", "range": "all"})
    status = flt.get("status", "all")
    rng = flt.get("range", "all")
    try:
        rows = list_reseller_orders(limit=200)
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    # filter by status
    if status == "delivered":
        rows = [r for r in rows if r.get("status") == "delivered"]
    elif status == "pending":
        rows = [r for r in rows if r.get("status") in ("pending", "processing")]
    elif status == "failed":
        rows = [r for r in rows if r.get("status") == "failed"]
    # filter by date range
    if rng == "24h":
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        rows = [r for r in rows if str(r.get("created_at") or "") >= cutoff]
    elif rng == "7d":
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        rows = [r for r in rows if str(r.get("created_at") or "") >= cutoff]
    rows = rows[:12]
    lines = [f"📦 *Reseller Orders* — status `{status}` · range `{rng}`\n"]
    if not rows:
        lines.append("(koi orders nahi is filter mein)")
    kb = []
    for r in rows:
        st = {"delivered": "✅", "pending": "⏳", "processing": "🔄", "failed": "❌"}.get(r.get("status"), "❔")
        lines.append(f"{st} #{r['id']} · {str(r.get('product_name'))[:20]} ×{r.get('qty')} · ${float(r.get('usd_amount') or 0):.2f} · {str(r.get('created_at'))[:10]}")
        if r.get("status") in ("pending", "processing"):
            kb.append([InlineKeyboardButton(f"📤 Deliver #{r['id']}",
                                            callback_data=f"reseller_deliver_panel_{r['id']}")])
    # filter buttons
    kb.append([
        InlineKeyboardButton("📋 All", callback_data="reseller_orders_filter_status_all"),
        InlineKeyboardButton("✅ Del", callback_data="reseller_orders_filter_status_delivered"),
        InlineKeyboardButton("⏳ Pend", callback_data="reseller_orders_filter_status_pending"),
        InlineKeyboardButton("❌ Fail", callback_data="reseller_orders_filter_status_failed"),
    ])
    kb.append([
        InlineKeyboardButton("🕐 24h", callback_data="reseller_orders_filter_range_24h"),
        InlineKeyboardButton("📅 7d", callback_data="reseller_orders_filter_range_7d"),
        InlineKeyboardButton("🗓️ All", callback_data="reseller_orders_filter_range_all"),
    ])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="reseller_panel")])
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def reseller_deliver_panel_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        oid = int(q.data.replace("reseller_deliver_panel_", ""))
    except Exception:
        return
    context.user_data["rs_step"] = {"action": "deliver_text", "order_id": oid}
    await q.edit_message_text(f"📤 Order #{oid} ki *delivery text* send karo:\n\n_(/cancel to cancel)_",
                              parse_mode="Markdown")


async def reseller_stats_panel_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        from reseller_api import list_reseller_keys
        from database import reseller_stats, reseller_key_stats, get_user
        st = reseller_stats()
        keys = list_reseller_keys()
        lines = [f"📊 *Reseller Stats*\nKeys: {st.get('total_keys',0)} ({st.get('active_keys',0)} active) · "
                 f"Orders: {st.get('total_orders',0)} · Revenue: ${st.get('revenue_usd',0):,.2f}\n"]
        for k in keys[:15]:
            ks = reseller_key_stats(int(k.get("id") or 0))
            try:
                u = get_user(int(k.get("owner_id") or 0))
                uname = (u.get("first_name") if u else None) or str(k.get("owner_id"))
            except Exception:
                uname = str(k.get("owner_id"))
            lines.append(f"• `{k.get('key_prefix')}` {uname}: {ks.get('orders',0)} orders · "
                         f"${ks.get('spent_usd',0):.2f} · ✅{ks.get('delivered',0)} ❌{ks.get('failed',0)}")
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(
                                  [[InlineKeyboardButton("🔙 Back", callback_data="reseller_panel")]]))


async def reseller_wizard_text(update, context):
    """Routes admin text input for the reseller panel wizard."""
    if update.effective_user.id != ADMIN_ID:
        return None
    step = context.user_data.get("rs_step")
    if not step:
        return None
    text = (update.message.text or "").strip()
    from telegram.ext import ApplicationHandlerStop
    if text == "/cancel":
        context.user_data.pop("rs_step", None)
        await update.message.reply_text("❌ Cancelled.")
        raise ApplicationHandlerStop
    if text.startswith("/"):
        return None  # other commands pass through normally
    action = step.get("action")
    try:
        if action == "gen_uid":
            uid = int(text)
            from reseller_api import generate_reseller_key
            key, prefix = generate_reseller_key(uid, f"Panel {uid}")
            try:
                u = get_user(uid)
                uname = (u.get("first_name") if u else None) or f"user {uid}"
            except Exception:
                uname = f"user {uid}"
            await update.message.reply_text(
                f"✅ *Key for {uname} ({uid})!*\n\n`{key}`\n\n"
                f"Header: `X-API-Key: {key}`\nDocs: `<BASE_URL>/api-docs/`\n⚠️ Shown ONCE.",
                parse_mode="Markdown")
        elif action == "markup":
            pct = float(text)
            set_setting("reseller_markup_pct", str(pct))
            await update.message.reply_text(f"✅ Global reseller markup → *{pct:g}%*", parse_mode="Markdown")
        elif action == "deliver_text":
            oid = int(step.get("order_id") or 0)
            from database import complete_reseller_order, get_reseller_order, get_api_key_row
            ok = complete_reseller_order(oid, text)
            if not ok:
                await update.message.reply_text("❌ Order not found / already delivered.")
            else:
                try:
                    order = get_reseller_order(oid)
                    krow = get_api_key_row(int(order.get("key_id") or 0)) if order else None
                    if krow:
                        from reseller_api import _send_webhook
                        _send_webhook(krow, "order.pending_completed", {
                            "orderId": str(oid), "status": "delivered",
                            "deliveredKeys": [text], "deliveredKey": text,
                            "amount": round(float(order.get("usd_amount") or 0), 2)})
                except Exception:
                    pass
                await update.message.reply_text(f"✅ Order *#{oid}* delivered!\n\n{text[:400]}",
                                                parse_mode="Markdown")
        elif action == "key_markup":
            kid = int(step.get("key_id") or 0)
            pct = float(text)
            update_api_key_fields(kid, reseller_markup=pct)
            await update.message.reply_text(f"✅ Key #{kid} markup → *{pct:g}%*", parse_mode="Markdown")
        elif action == "key_spend":
            kid = int(step.get("key_id") or 0)
            usd = max(0.0, float(text))
            update_api_key_fields(kid, spend_limit_usd=usd)
            await update.message.reply_text(f"✅ Key #{kid} spend limit → *${usd:g}*", parse_mode="Markdown")
        elif action == "key_products":
            kid = int(step.get("key_id") or 0)
            raw = text.lower()
            val = "" if raw == "all" else text
            update_api_key_fields(kid, allowed_products=val)
            await update.message.reply_text(f"✅ Key #{kid} products → *{'ALL' if not val else val}*", parse_mode="Markdown")
        elif action == "key_ip":
            kid = int(step.get("key_id") or 0)
            raw = text.lower()
            val = "" if raw == "all" else text
            update_api_key_fields(kid, ip_whitelist=val)
            await update.message.reply_text(f"✅ Key #{kid} IP whitelist → *{'ALL' if not val else val}*", parse_mode="Markdown")
        elif action == "key_webhook":
            kid = int(step.get("key_id") or 0)
            raw = text.lower()
            val = "" if raw in ("off", "0", "none") else text
            if val and not (val.startswith("http://") or val.startswith("https://")):
                await update.message.reply_text("❌ URL `http(s)://...` ya `off`", parse_mode="Markdown")
            else:
                update_api_key_fields(kid, webhook_url=val)
                await update.message.reply_text(f"✅ Key #{kid} webhook → *{'OFF' if not val else val}*", parse_mode="Markdown")
        elif action == "prod_price":
            pid = int(step.get("product_id") or 0)
            price = float(text)
            conn = get_connection(); c = conn.cursor()
            c.execute("UPDATE products SET reseller_price=? WHERE id=?", (price, pid))
            n = c.rowcount; conn.commit(); conn.close()
            await update.message.reply_text(
                f"✅ Reseller price for #{pid} → *${price:g}*" if n else "❌ Product not found",
                parse_mode="Markdown")
        elif action == "key_prod_price":
            # 🆕 v170.6: per-key × per-product price override
            kid = int(step.get("key_id") or 0)
            pid = int(step.get("product_id") or 0)
            from database import (get_api_key_row, get_all_products,
                                  set_reseller_key_price)
            from reseller_api import reseller_price_for
            k = get_api_key_row(kid)
            raw = text.strip().replace(" ", "")
            low = raw.lower()
            if low in ("default", "remove", "reset", "off", "none"):
                set_reseller_key_price(kid, pid, 0)
                await update.message.reply_text(
                    f"✅ Override removed — price wapas auto (markup/base) ho gayi.",
                    parse_mode="Markdown")
            elif raw.endswith("%") or raw.startswith("+") or raw.startswith("-"):
                if pid == 0:
                    await update.message.reply_text(
                        "❌ ALL products ke liye sirf exact $ (e.g. `5.00`) ya `default` do.",
                        parse_mode="Markdown")
                else:
                    cur = None
                    for p in get_all_products():
                        if int(p["id"]) == pid:
                            cur = reseller_price_for(dict(p), k)
                            break
                    if raw.endswith("%"):
                        pct = float(raw[:-1])
                        new = (cur or 0.0) * (1 + pct / 100.0)
                    else:
                        delta = float(raw)
                        new = (cur or 0.0) + delta
                    new = round(max(0.01, new), 2)
                    set_reseller_key_price(kid, pid, new)
                    await update.message.reply_text(
                        f"✅ Key `{k.get('key_prefix')}` product #{pid} price → *${new:.2f}*",
                        parse_mode="Markdown")
            else:
                price = float(raw)
                if price <= 0:
                    await update.message.reply_text("❌ Price must be > 0 (ya `default`).")
                else:
                    set_reseller_key_price(kid, pid, price)
                    what = "ALL products" if pid == 0 else f"product #{pid}"
                    await update.message.reply_text(
                        f"✅ Key `{k.get('key_prefix')}` {what} price → *${price:.2f}*",
                        parse_mode="Markdown")
        elif action == "topup":
            kid = int(step.get("key_id") or 0)
            pts = float(text)
            if pts <= 0:
                await update.message.reply_text("❌ Amount must be > 0")
            else:
                from database import get_api_key_row, add_points, get_user
                k = get_api_key_row(kid)
                uid = int(k.get("owner_id") or 0)
                add_points(uid, pts, tx_type="credit",
                           description=f"Reseller top-up (key {k.get('key_prefix')})")
                try:
                    u = get_user(uid)
                    uname = (u.get("first_name") if u else None) or str(uid)
                except Exception:
                    uname = str(uid)
                await update.message.reply_text(
                    f"✅ *{pts:g} points* added to {uname} (`{uid}`) wallet.\n"
                    "Ledger mein record ho gaya.", parse_mode="Markdown")
        else:
            await update.message.reply_text("❓ Unknown wizard step — send /cancel")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
    context.user_data.pop("rs_step", None)
    raise ApplicationHandlerStop


# ════════════════════════════════════════════════════════════════
# 🆕 v161.4: USER-FACING "Reseller API Key" PANEL (ProdSeller-style)
# Buttons: [Show Full Key] [Regenerate] [API Documentation] [Back]
# ════════════════════════════════════════════════════════════════

def _reseller_docs_url() -> str:
    try:
        from database import get_setting
        u = (get_setting("reseller_docs_url") or "").strip()
        if u:
            return u
    except Exception:
        pass
    return "https://bite-store-bot-production.up.railway.app/api-docs/"


async def reseller_api_from_text(update, context):
    """🆕 v170.12: 🔗 Reseller API persistent reply-keyboard button se entry —
    same landing/panel, reply_text ke through (text trigger)."""
    msg = update.message
    uid = int(update.effective_user.id)
    try:
        from reseller_api import (get_user_reseller_key, generate_reseller_key,
                                  reveal_reseller_key)
        from database import get_user_points, get_setting
    except Exception as e:
        await msg.reply_text(f"❌ {e}")
        return
    key = get_user_reseller_key(uid)
    docs_url = _reseller_docs_url()
    if not key:
        kb = []
        _g = _rb("reseller_api_generate_btn")
        kb.append([_g] if _g else [InlineKeyboardButton("🛠️ Generate API Key", callback_data="reseller_api_generate")])
        if docs_url:
            _d = _rb("reseller_api_docs_btn", url=docs_url)
            kb.append([_d] if _d else [InlineKeyboardButton("📚 API Documentation", url=docs_url)])
        kb.append([_rb("nav_prod_home") or InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
        try:
            _txt = get_response_with_auto_register(
                "reseller_api_landing",
                "🔗 *Reseller API*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "👉 Sell our products on your own bot or website!\n\n"
                "🔑 Tap **Generate API Key** to create your personal key.\n"
                "💳 Your key is linked to your wallet (💎 Buy Points to top up).\n"
                "📦 Every order is auto-delivered to your bot.\n\n"
                "_Your key is shown only ONCE after generating — save it!_")
            _st, _sm = smart_text_and_mode(_txt, "Markdown")
            await msg.reply_text(_st, parse_mode=_sm, reply_markup=InlineKeyboardMarkup(kb))
        except Exception:
            await msg.reply_text("🔗 *Reseller API*\n\nTap *Generate API Key* to create your key.",
                                 parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return
    # has key → simple access panel (masked)
    kid = int(key.get("id") or 0)
    prefix = str(key.get("key_prefix") or "")
    reqs = int(key.get("request_count") or 0)
    created = str(key.get("created_at") or "")[:10]
    try:
        ppd = float(get_setting("reseller_points_per_dollar") or 10)
        bal = float(get_user_points(uid) or 0) / ppd if ppd else 0
    except Exception:
        bal = 0.0
    kb = []
    _s = _rb("reseller_api_show_btn")
    _r = _rb("reseller_api_regenerate_btn")
    if _s and _r:
        kb.append([_s, _r])
    else:
        kb.append([InlineKeyboardButton("👁️ Show Full Key", callback_data="reseller_api_show"),
                   InlineKeyboardButton("🔄 Regenerate", callback_data="reseller_api_regenerate")])
    if docs_url:
        _d = _rb("reseller_api_docs_btn", url=docs_url)
        kb.append([_d] if _d else [InlineKeyboardButton("📚 API Documentation", url=docs_url)])
    kb.append([_rb("nav_prod_home") or InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    text = (
        "🔗 *API Access*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Key: `{prefix}....`\n"
        f"💳 Balance: *${bal:.2f}*\n"
        f"📨 Requests: {reqs}\n"
        f"📅 Created: {created}"
    )
    _st, _sm = smart_text_and_mode(text, "Markdown")
    await msg.reply_text(_st, parse_mode=_sm, reply_markup=InlineKeyboardMarkup(kb))


async def reseller_api_user_callback(update, context):
    """🔗 Reseller API Key (main menu button) — any user."""
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    uid = int(q.from_user.id)
    try:
        from reseller_api import (get_user_reseller_key, generate_reseller_key,
                                  reveal_reseller_key)
        from database import get_user_points, get_setting
    except Exception as e:
        try:
            await q.edit_message_text(f"❌ {e}")
        except Exception:
            pass
        return
    key = get_user_reseller_key(uid)
    docs_url = _reseller_docs_url()

    # 🔧 v161.11: NO auto-generate. If the user has no key, show a landing
    # screen with a "Generate API Key" button — key is only created on tap.
    if not key:
        # 🆕 v161.13: editable buttons (Customization → Buttons Editor → Reseller API)
        kb = []
        _g = _rb("reseller_api_generate_btn")
        kb.append([_g] if _g else [InlineKeyboardButton("🛠️ Generate API Key", callback_data="reseller_api_generate")])
        if docs_url:
            _d = _rb("reseller_api_docs_btn", url=docs_url)
            kb.append([_d] if _d else [InlineKeyboardButton("📚 API Documentation", url=docs_url)])
        kb.append([_rb("nav_prod_home") or InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
        try:
            _txt = get_response_with_auto_register(
                "reseller_api_landing",
                "🔗 *Reseller API*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "👉 Sell our products on your own bot or website!\n\n"
                "🔑 Tap **Generate API Key** to create your personal key.\n"
                "💳 Your key is linked to your wallet (💎 Buy Points to top up).\n"
                "📦 Every order is auto-delivered to your bot.\n\n"
                "_Your key is shown only ONCE after generating — save it!_")
            # 🆕 v161.14 FIX: [[HTML]]/premium-emoji aware — smart_text_and_mode
            # switches to HTML when the saved response contains <tg-emoji>.
            _st, _sm = smart_text_and_mode(_txt, "Markdown")
            await q.edit_message_text(_st,
                parse_mode=_sm, reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            try:
                await q.message.reply_text(f"❌ {e}")
            except Exception:
                pass
        return

    # ── API Access panel ──
    kid = int(key.get("id") or 0)
    prefix = str(key.get("key_prefix") or "")
    reqs = int(key.get("request_count") or 0)
    created = str(key.get("created_at") or "")[:10]
    try:
        ppd = float(get_setting("reseller_points_per_dollar") or 10)
        bal = float(get_user_points(uid) or 0) / ppd if ppd else 0
    except Exception:
        bal = 0.0
    # 🆕 v161.6: show the key's limits so the reseller knows them
    # (markup/base intentionally NOT shown — that's the owner's margin)
    try:
        _spend = float(key.get("spend_limit_usd") or 0)
        _rate = int(key.get("rate_limit") or 60)
        _prods = (key.get("allowed_products") or "").strip()
        _ips = (key.get("ip_whitelist") or "").strip()
        limits_lines = (
            f"💳 Spend limit: *{('$' + format(_spend, 'g')) if _spend else 'Unlimited'}*\n"
            f"📊 Rate limit: *{_rate}/min*\n"
            f"🗂️ Products: *{'ALL' if not _prods or _prods.lower() == 'all' else _prods}*\n"
            f"🌐 IP whitelist: *{'ALL' if not _ips or _ips.lower() == 'all' else _ips}*"
        )
    except Exception:
        limits_lines = ""
    # 🆕 v161.13: panel text is EDITABLE via Edit Responses / Screen Editor
    # (reseller_api_panel). Placeholders: {prefix}, {balance}, {requests},
    # {created}, {limits}
    text = get_response_with_auto_register(
        "reseller_api_panel",
        "🔗 *API Access*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Use your API key to sell products on your own bot or website.\n\n"
        "🔑 *Your API Key:*\n`{prefix}....`\n\n"
        "💳 Balance: *${balance:.2f}*\n"
        "📨 Total requests: *{requests}*\n"
        "📅 Created: *{created}*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "{limits}"
    )
    try:
        text = text.replace("{prefix}", str(prefix))
        text = text.replace("{balance}", f"{bal:.2f}")
        text = text.replace("{requests}", str(reqs))
        text = text.replace("{created}", str(created))
        text = text.replace("{limits}", limits_lines)
        text = text.replace("**${balance:.2f}**", f"**${bal:.2f}**")  # safety
        text = text.replace("{balance:.2f}", f"{bal:.2f}")
    except Exception:
        pass
    # 🆕 v161.13: editable buttons (Customization → Buttons Editor → Reseller API)
    kb = []
    _s = _rb("reseller_api_show_btn")
    _r = _rb("reseller_api_regenerate_btn")
    if _s and _r:
        kb.append([_s, _r])
    else:
        kb.append([InlineKeyboardButton("👁️ Show Full Key", callback_data="reseller_api_show"),
                   InlineKeyboardButton("🔄 Regenerate", callback_data="reseller_api_regenerate")])
    if docs_url:
        _d = _rb("reseller_api_docs_btn", url=docs_url)
        kb.append([_d] if _d else [InlineKeyboardButton("📚 API Documentation", url=docs_url)])
    kb.append([_rb("nav_prod_home") or InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    try:
        # 🆕 v161.14 FIX: premium-emoji/HTML aware + never leaves it stuck.
        _st, _sm = smart_text_and_mode(text, "Markdown")
        await q.edit_message_text(_st, parse_mode=_sm,
                                  reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        # fallback: plain text so the button always responds
        try:
            await q.edit_message_text(
                f"🔗 *API Access*\n━━━━━━━━━━━━━━━━━━━━\n"
                f"🔑 Key: `{prefix}....`\n💳 Balance: *${bal:.2f}*\n"
                f"📨 Requests: {reqs}\n📅 Created: {created}",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        except Exception:
            pass


async def reseller_api_generate_callback(update, context):
    """🛠️ Generate API Key — on button tap (not auto)."""
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    uid = int(q.from_user.id)
    try:
        from reseller_api import (get_user_reseller_key, generate_reseller_key)
    except Exception as e:
        try:
            await q.edit_message_text(f"❌ {e}")
        except Exception:
            pass
        return
    # safety: if a key already exists (double-tap), don't create another
    existing = get_user_reseller_key(uid)
    if existing:
        return await reseller_api_user_callback(update, context)
    plaintext, _p = generate_reseller_key(uid, f"Reseller {uid}")
    # 🆕 v161.13: admin alert on key generation (English, full details)
    try:
        from reseller_api import _notify_admin_key_generated
        _notify_admin_key_generated(uid, "Self-serve")
    except Exception:
        pass
    docs_url = _reseller_docs_url()
    # 🆕 v161.13: editable buttons
    kb = []
    if docs_url:
        _d = _rb("reseller_api_docs_btn", url=docs_url)
        kb.append([_d] if _d else [InlineKeyboardButton("📚 API Documentation", url=docs_url)])
    kb.append([_rb("nav_prod_home") or InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    try:
        _txt = get_response_with_auto_register(
            "reseller_api_generated",
            "✅ *New API Key Generated!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔑 *Your Key:*\n`{api_key}`\n\n"
            "⚠️ *Save this key now — it will be masked next time.*\n\n"
            "📡 Use header: `X-API-Key: {api_key}`\n"
            "🛒 Use it to sell our products on your own bot or website.")
        _txt = _txt.replace("{api_key}", plaintext)
        # 🆕 v161.14 FIX: premium-emoji/HTML aware
        _st, _sm = smart_text_and_mode(_txt, "Markdown")
        await q.edit_message_text(_st,
            parse_mode=_sm, reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        try:
            await q.message.reply_text(f"❌ {e}")
        except Exception:
            pass


async def reseller_api_show_callback(update, context):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    uid = int(q.from_user.id)
    try:
        from reseller_api import get_user_reseller_key, reveal_reseller_key
        key = get_user_reseller_key(uid)
        if not key:
            raise Exception("No active key")
        plaintext = reveal_reseller_key(int(key.get("id") or 0))
    except Exception as e:
        try:
            await q.edit_message_text(f"❌ {e}")
        except Exception:
            pass
        return
    if not plaintext:
        kb = [[InlineKeyboardButton("🔄 Regenerate", callback_data="reseller_api_regenerate"),
               InlineKeyboardButton("🔙 Back", callback_data="reseller_api_user")]]
        try:
            await q.edit_message_text(
                "🔑 *Your Full Key*\n\n"
                "⚠️ Is key ka plaintext recoverable nahi tha (security).\n"
                "*Regenerate* karke nayi key banao.",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        except Exception:
            pass
        return
    try:
        # 🆕 v161.13: editable full-key text (reseller_api_fullkey, {api_key})
        _txt = get_response_with_auto_register(
            "reseller_api_fullkey",
            "🔑 *Your Full Key*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "`{api_key}`\n\n"
            "📡 Use header: `X-API-Key: {api_key}`")
        _txt = _txt.replace("{api_key}", plaintext)
        # 🆕 v161.14 FIX: premium-emoji/HTML aware
        _st, _sm = smart_text_and_mode(_txt, "Markdown")
        await q.edit_message_text(_st, parse_mode=_sm,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="reseller_api_user")]]))
    except Exception:
        pass


async def reseller_api_regenerate_callback(update, context):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    uid = int(q.from_user.id)
    try:
        from reseller_api import (get_user_reseller_key, revoke_reseller_key,
                                  generate_reseller_key)
        key = get_user_reseller_key(uid)
        if key:
            revoke_reseller_key(int(key.get("id") or 0))
        plaintext, _p = generate_reseller_key(uid, f"Reseller {uid}")
        # 🆕 v161.13: admin alert on regenerate
        try:
            from reseller_api import _notify_admin_key_generated
            _notify_admin_key_generated(uid, "Regenerate")
        except Exception:
            pass
    except Exception as e:
        try:
            await q.edit_message_text(f"❌ {e}")
        except Exception:
            pass
        return
    docs_url = _reseller_docs_url()
    # 🆕 v161.13: editable buttons
    kb = []
    if docs_url:
        _d = _rb("reseller_api_docs_btn", url=docs_url)
        kb.append([_d] if _d else [InlineKeyboardButton("📚 API Documentation", url=docs_url)])
    kb.append([_rb("nav_prod_home") or InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    try:
        # 🆕 v161.13: editable regenerate text (reseller_api_regenerate, {api_key})
        _txt = get_response_with_auto_register(
            "reseller_api_regenerate",
            "🔄 *New API Key Generated!* (old key revoked)\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔑 `{api_key}`\n\n"
            "⚠️ *Save now — shown only ONCE.*\n\n"
            "📡 Use header: `X-API-Key: {api_key}`")
        _txt = _txt.replace("{api_key}", plaintext)
        # 🆕 v161.14 FIX: premium-emoji/HTML aware
        _st, _sm = smart_text_and_mode(_txt, "Markdown")
        await q.edit_message_text(_st, parse_mode=_sm, reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# ADMIN: RESELLER PRODUCTS (per-product price + visibility) — panel
# ════════════════════════════════════════════════════════════════

async def reseller_admin_products_callback(update, context, page=0):
    """🆕 v170.12: Reseller products — warranty/refund STYLE list (premium
    emoji name + green/red toggle + stock + reseller price) + bulk ALL ON/OFF."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT id, name, stock, reseller_enabled, COALESCE(reseller_price,0) AS rp "
                  "FROM products WHERE is_active=1 ORDER BY id LIMIT 8 OFFSET ?", (page * 8,))
        rows = [dict(r) for r in c.fetchall()]; conn.close()
        c2 = get_connection(); c3 = c2.cursor()
        total = c3.execute("SELECT COUNT(*) FROM products WHERE is_active=1").fetchone()[0]
        c2.close()
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    try:
        from button_system import make_premium_button, extract_emoji_from_html
        _have = True
    except Exception:
        _have = False
    lines = ["🗂️ *Reseller Products*\n",
             "_(✅ = API key par available · ⛔ = API par nahi aayega)_\n"]
    kb = []
    for r in rows:
        on = int(r.get("reseller_enabled") if r.get("reseller_enabled") is not None else 1) == 1
        price = f"${float(r.get('rp') or 0):g}" if float(r.get("rp") or 0) > 0 else "auto"
        raw_name = str(r.get("name") or f"#{r['id']}")
        plain, eid = raw_name, ""
        if _have:
            try:
                _eid, _plain = extract_emoji_from_html(raw_name)
                if _plain:
                    plain = _plain
                eid = _eid or ""
            except Exception:
                pass
        icon = "✅" if on else "⛔"
        lines.append(f"{icon} #{r['id']} · {plain[:30]}")
        toggle_lbl = "✅ ON" if on else "⛔ OFF"
        kb.append([
            make_premium_button(toggle_lbl, emoji_id=eid or None,
                                style="success" if on else "danger",
                                callback_data=f"reseller_prod_toggle_{r['id']}")
            if _have else InlineKeyboardButton(toggle_lbl, callback_data=f"reseller_prod_toggle_{r['id']}"),
            InlineKeyboardButton(f"💰 {price}", callback_data=f"reseller_prod_price_{r['id']}"),
        ])
    # bulk buttons
    kb.append([
        InlineKeyboardButton("🟢 ALL ON", callback_data="reseller_prod_all_on"),
        InlineKeyboardButton("🔴 ALL OFF", callback_data="reseller_prod_all_off"),
    ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"reseller_prod_page_{page-1}"))
    nav.append(InlineKeyboardButton("🔙 Back", callback_data="reseller_panel"))
    if (page + 1) * 8 < total:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"reseller_prod_page_{page+1}"))
    kb.append(nav)
    lines.append(f"\n_page {page+1} of {max(1, (total+7)//8)}_")
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(kb))


async def reseller_prod_all_callback(update, context):
    """🆕 v170.12: bulk enable/disable ALL products for reseller API."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    data = q.data
    new = 1 if data == "reseller_prod_all_on" else 0
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE products SET reseller_enabled=? WHERE is_active=1", (new,))
        conn.commit(); conn.close()
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    await reseller_admin_products_callback(update, context)


async def reseller_prod_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("reseller_prod_toggle_", ""))
        from database import get_connection, get_product
        p = dict(get_product(pid))
        cur = int(p.get("reseller_enabled") if p.get("reseller_enabled") is not None else 1)
        new = 0 if cur == 1 else 1
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE products SET reseller_enabled=? WHERE id=?", (new, pid))
        conn.commit(); conn.close()
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    await reseller_admin_products_callback(update, context)


async def reseller_prod_price_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("reseller_prod_price_", ""))
        from database import get_product
        p = dict(get_product(pid))
    except Exception as e:
        await q.edit_message_text(f"❌ {e}"); return
    context.user_data["rs_step"] = {"action": "prod_price", "product_id": pid}
    await q.edit_message_text(
        f"💲 Reseller price for *#{pid} {str(p.get('name'))[:30]}*\n\n"
        "Send price in USD (`0` = auto cost×markup):\n\n_(/cancel to cancel)_",
        parse_mode="Markdown")


async def reseller_prod_page_callback(update, context):
    q = update.callback_query
    try:
        page = int(q.data.replace("reseller_prod_page_", ""))
    except Exception:
        return
    await reseller_admin_products_callback(update, context, page=page)


# 🆕 v161.18: Admin Panel All-Green (one click)
async def cz_admin_all_green_callback(update, context):
    """Set EVERY admin-group button background to green (success)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("🟢 Applying…")
    try:
        from button_system import BUTTONS, set_button_style, set_group_style
        n = 0
        for bid, info in BUTTONS.items():
            if info.get("group") == "admin":
                set_button_style(bid, "success")
                n += 1
        set_group_style("admin", "success")
        await q.edit_message_text(
            f"🟢 *Done!* Admin panel ke *{n}* buttons sab green ho gaye.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"_(Har button pe individually color bhi change kar sakte ho — "
            f"Buttons Editor → Admin Panel)_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Customization", callback_data="admin_customization")],
                [InlineKeyboardButton("👁️ Preview Admin", callback_data="admin_panel")],
            ]))
    except Exception as e:
        try:
            await q.edit_message_text(f"❌ {e}")
        except Exception:
            pass


# 🆕 v161.18: RESELLER DASHBOARD — top resellers, per-key top product,
# profit + revenue graph (text-based bar chart).
async def reseller_dashboard_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        from database import reseller_dashboard, reseller_trend
        dash = reseller_dashboard(limit=8)
        trend = reseller_trend(0, days=14)  # key 0 → aggregate all keys
    except Exception as e:
        await q.edit_message_text(f"❌ {e}")
        return
    t = dash["totals"]
    lines = [
        "📊 *Reseller Dashboard*\n━━━━━━━━━━━━━━━━━━━━",
        f"👥 Resellers: *{len(dash['keys'])}*",
        f"📦 Orders: *{t['orders']}*",
        f"💰 Revenue: *${t['revenue']:,.2f}*",
        f"📈 Profit: *${t['profit']:,.2f}*",
        "",
        "🏆 *Top Resellers (by revenue):*",
    ]
    if not dash["keys"]:
        lines.append("_(koi reseller orders nahi abhi)_")
    for i, k in enumerate(dash["keys"][:8], 1):
        st = "🟢" if k["active"] else "🔴"
        tp = k["top_product"]
        tp_line = ""
        if tp:
            tp_line = f"  🛒 Top: {tp[:30]} ({k['top_qty']}×)"
        lines.append(
            f"{st} {i}. *{k['name']}* (`{k['prefix']}`)\n"
            f"   💰 ${k['revenue']:,.2f} · 📈 ${k['profit']:,.2f} · 📦 {k['orders']}"
            + (f"\n{tp_line}" if tp_line else "")
        )
    # simple revenue graph (14 days)
    lines.append("\n📅 *Revenue (14 days)*")
    try:
        maxv = max((x["revenue"] for x in trend), default=0)
        for x in trend:
            bar = "█" * int(round((x["revenue"] / maxv) * 20)) if maxv else ""
            if x["revenue"] > 0 or bar:
                lines.append(f"`{x['date']}` {'█' * max(1, int((x['revenue']/maxv)*20) if maxv else 0)} ${x['revenue']:.0f}")
        if not any(x["revenue"] > 0 for x in trend):
            lines.append("_(is period mein koi revenue nahi)_")
    except Exception:
        pass
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Reseller Panel", callback_data="reseller_panel")],
    ])
    await q.edit_message_text("\n".join(lines)[:3900], parse_mode="Markdown", reply_markup=kb)


# ⭐ v161.25: Telegram Stars rate setter (1$ = ? Stars)
async def stars_rate_start_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    cur = get_setting("stars_per_dollar", "120")
    context.user_data["pm_stars_rate"] = True
    await _safe_edit(q,
        f"⭐ *Set Telegram Stars Rate*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: 1$ = *{escape_md(str(cur))} Stars*\n\n"
        f"Type a number (how many Stars = $1).\n"
        f"Example: `120` → 1$ = 120 Stars (like Stock Lara)\n\n"
        f"_Send the number as your next message._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pm_crypto")]]))


async def stars_rate_received(update, context):
    """Called from bot.py handle_text when pm_stars_rate is set."""
    if update.effective_user.id != ADMIN_ID:
        return False
    if not context.user_data.get("pm_stars_rate"):
        return False
    context.user_data.pop("pm_stars_rate", None)
    raw = (update.message.text or "").strip()
    try:
        val = float(raw)
        if val < 1 or val > 100000:
            raise ValueError
    except Exception:
        await update.message.reply_text(
            "❌ Enter a valid number ≥ 1, e.g. `120`.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Crypto Settings", callback_data="pm_crypto")]]))
        return True
    set_setting("stars_per_dollar", str(int(val) if float(val).is_integer() else val))
    await update.message.reply_text(
        f"✅ *Stars rate updated:* 1$ = *{int(val) if float(val).is_integer() else val:g} Stars*\n\n"
        f"_Customers will see the new conversion instantly._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Crypto Settings", callback_data="pm_crypto")]]))
    return True
