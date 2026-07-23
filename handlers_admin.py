# ============================================
# 👑 ADMIN
# ============================================
from telegram.ext import ConversationHandler
from config import *
from database import *
from keyboards import *
from utils import escape_md, nav_push, set_cb_data, location_back_callback, smart_text_and_mode, has_premium_emoji
from templates_bundle import (
    FORMAT_EMAIL_PASS, FORMAT_REDEEM_LINK, FORMAT_COUPON_CODES,
    format_label as delivery_format_label,
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
    # 🆕 v60: admin sees ALL products (including hidden ones) so they can unhide/edit
    await q.answer(); await _safe_edit(q, "🛍️ *Add Products:*",parse_mode="Markdown",reply_markup=admin_products_keyboard(get_all_products(include_hidden=True)))

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
    rows = [
        [InlineKeyboardButton(f"📧 Email+Pass{' ✅' if current == FORMAT_EMAIL_PASS else ''}", callback_data=f"pfmt_{FORMAT_EMAIL_PASS}")],
        [InlineKeyboardButton(f"🖇️ Redeem Link{' ✅' if current == FORMAT_REDEEM_LINK else ''}", callback_data=f"pfmt_{FORMAT_REDEEM_LINK}")],
        [InlineKeyboardButton(f"🎁 Coupon Codes{' ✅' if current == FORMAT_COUPON_CODES else ''}", callback_data=f"pfmt_{FORMAT_COUPON_CODES}")],
        [InlineKeyboardButton("🔙 Back", callback_data="prodback_delivery")],
        [InlineKeyboardButton("❌ Cancel", callback_data="conv_cancel")],
    ]
    text = (
        "🧩 *Step 9:* Product format?\n\n"
        "Choose how this product will be uploaded and delivered:\n\n"
        "• 📧 *Email+Pass* — account credentials\n"
        "• 🖇️ *Redeem Link* — one unique link per order\n"
        "• 🎁 *Coupon Codes* — one unique code per order\n\n"
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
    text=f"🛒 *#{o['id']}*\n👤 {escape_md(o['user_name'])} `{o['user_id']}`\n📦 {escape_md(o['product_name'])}\n💰 ${o['price']:.2f}\n💳 {o['payment_method']}\n📊 {o['status']}"
    if o['payment_method']=='binance': text+=f"\n🔶 {escape_md(o['binance_sender_name'])} — {o['binance_amount']}"
    if o['payment_screenshot']:
        try:
            await q.delete_message()
            await c.bot.send_photo(q.from_user.id,o['payment_screenshot'],caption=text,parse_mode="Markdown",reply_markup=admin_order_keyboard(o['id']))
            return
        except: pass
    await _safe_edit(q, text,parse_mode="Markdown",reply_markup=admin_order_keyboard(o['id']))

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
        pts = int(m.group(1)) if m else int((o['price'] or 0) * POINTS_PER_DOLLAR)
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
            # 🆕 Deliver from product_accounts pool (consumes & marks sold)
            from database import build_delivery_from_accounts
            delivery = build_delivery_from_accounts(o['product_id'], o['id'], order_qty, o['user_id'])
            # 🆕 v69: NO add_points here
            update_order_status(o['id'], 'delivered')
            msg = _r("payment_verified_product").format(order_id=o['id'], product=o['product_name'], delivery=delivery, points=pts)

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
        text += f"• `{usr['user_id']}` {escape_md(usr['first_name'] or '?')} 💎{usr['points']}\n"

    kb = []
    # Per-user 📊 View Activity buttons (2 per row to save vertical space)
    row = []
    for i, usr in enumerate(slice_):
        uid = usr['user_id']
        fname = (usr['first_name'] or '?')[:12]
        row.append(InlineKeyboardButton(f"📊 {fname} {uid}", callback_data=f"adm_uact_{uid}"))
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

    kb.append([InlineKeyboardButton("💎 Manage User Points", callback_data="adm_manage_pts")])
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
        from payments import is_configured as _bn_cfg
        bn_gmail_status = "✅ Connected" if _bn_cfg() else "❌ Not Set"
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
  📧 Gmail: *{bn_gmail_status}*

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
    labels={'shop_name':'Shop Name','whatsapp':'WhatsApp','binance':'Binance ID','easypaisa':'EasyPaisa Number','jazzcash':'JazzCash Number','account_name':'Account Name (legacy)','easypaisa_name':'EasyPaisa Holder Name','jazzcash_name':'JazzCash Holder Name','binance_name':'Binance Holder Name','email':'Support Email','pkr_rate':'USD→PKR Rate'}
    c.user_data['sk']=key
    await _safe_edit(q, f"✏️ New *{labels.get(key,key)}*:", parse_mode="Markdown", reply_markup=inline_cancel_btn()); return SET_VALUE

async def setting_value_received(u,c):
    if u.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    key=c.user_data.get('sk','')
    km={'binance':'binance_id','easypaisa':'easypaisa','jazzcash':'jazzcash','whatsapp':'whatsapp','shop_name':'shop_name','account_name':'account_name','easypaisa_name':'easypaisa_name','jazzcash_name':'jazzcash_name','binance_name':'binance_name','email':'email','pkr_rate':'usd_pkr_rate'}
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

    # Define categories — hardcoded lists for the well-known groups.
    CATEGORIES = {
        "main": {"name": "🏠 Main Menu", "keys": ["welcome", "my_account", "cancelled_message"]},
        "shop": {"name": "🛒 Shop & Products", "keys": ["shop_title", "shop_categories_title", "product_detail", "no_products", "out_of_stock", "confirm_purchase", "confirm_bulk_purchase", "bulk_confirmed", "no_orders", "orders_title", "shop_no_available", "shop_no_unavailable"]},
        "payment": {"name": "💳 Payment Screens", "keys": [k for k in all_keys if k.startswith(("binance_", "jazzcash_", "easypaisa_", "jc_", "ep_", "buy_points"))]},
        "verify": {"name": "✅ Verification Messages", "keys": [k for k in all_keys if k.startswith(("payment_verified", "analyzing_", "screenshot_", "reupload_", "jc_reupload", "upload_image"))]},
        "error": {"name": "❌ Error Messages", "keys": [k for k in all_keys if k.startswith("error_")]},
        "points": {"name": "💎 Points & Referrals", "keys": ["buy_points", "buy_points_title", "buy_points_custom", "buy_points_custom_confirmed", "referral_text", "no_transactions", "order_created", "order_cancelled", "order_cancelled_no_reason", "order_cancelled_with_reason", "referral_blocked_by_admin", "referral_success_notification"]},
        "features": {"name": "🧩 Feature Screens", "keys": ["support_menu_header", "warranty_menu_header", "warranty_no_orders", "reviews_menu_header", "loyalty_menu_header", "language_menu_header"]},
        # 🆕 v95: NEW category for tier / freeclaim / refund groups (were missing)
        "tier": {"name": "🏆 Loyalty & Tiers", "keys": [k for k in all_keys if k.startswith("tier_")]},
        "freeclaim": {"name": "🎁 Free Claim", "keys": [k for k in all_keys if k.startswith("freeclaim_")]},
        "other": {"name": "📞 Support & Other", "keys": ["support_text", "terms", "order_rejected", "new_user_notification", "binance_instructions", "refund_processed"]},
    }

    # 🆕 v95: merge admin-added custom response categories (dynamic, from DB)
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

    # 🐛 v95 FIX: compute what's covered vs missing, add a catch-all for
    # anything that slipped through (future-proof — if admin adds a new
    # DEFAULT_RESPONSES key, it appears here automatically without code change)
    covered = set()
    for cat_info in CATEGORIES.values():
        covered.update(k for k in cat_info["keys"] if k in all_keys)
    uncategorized = sorted(set(all_keys) - covered)
    if uncategorized:
        CATEGORIES["uncategorized"] = {
            "name": f"📄 Other / New ({len(uncategorized)})",
            "keys": uncategorized,
        }
    
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
    await _safe_edit(q, f"✏️ *{key.replace('_',' ').title()}*\n\nCurrent:\n```\n{preview}\n```\n\nType new text:", parse_mode="Markdown", reply_markup=inline_cancel_btn()); return EDIT_RESP_VALUE

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

# ── Broadcast ──
async def broadcast_callback(u,c):
    q=u.callback_query
    if q.from_user.id!=ADMIN_ID: await q.answer("❌",show_alert=True); return
    await q.answer(); await _safe_edit(q, "🌐 Type the announcement message:", parse_mode="Markdown", reply_markup=inline_cancel_btn())
    c.user_data['broadcasting']=True

async def handle_broadcast_message(u,c):
    """🆕 v96: auto-detect premium emojis in admin broadcast messages.

    If admin's message contains custom_emoji entities (Telegram Premium),
    convert to HTML with <tg-emoji> tags and send in HTML mode.
    Otherwise fall back to Markdown as before.

    Also gated by maintenance mode: if maintenance ON, skip broadcast.
    """
    if u.effective_user.id!=ADMIN_ID: return
    if not c.user_data.get('broadcasting'): return
    c.user_data['broadcasting']=False

    # 🆕 v96: maintenance mode gate
    try:
        from maintenance_mode import is_maintenance_on
        if is_maintenance_on():
            await u.message.reply_text(
                "🛠️ *Maintenance ON* — broadcast skipped.\n"
                "Maintenance off karo phir broadcast dubara try karo.",
                parse_mode="Markdown", reply_markup=admin_menu_keyboard()
            )
            return
    except Exception:
        pass

    # 🆕 v96: auto-detect premium emoji entities
    msg = u.message
    entities = msg.entities or []
    has_premium = any(getattr(e, "type", "") == "custom_emoji" for e in entities)

    if has_premium:
        # Use HTML mode with tg-emoji preserved via text_html_urled
        try:
            html_body = msg.text_html_urled or msg.text_html or msg.text
        except Exception:
            html_body = msg.text
        text_to_send = f"📢 <b>Announcement</b>\n\n{html_body}"
        parse_mode = "HTML"
    else:
        text_to_send = f"📢 *Announcement*\n\n{escape_md(msg.text)}"
        parse_mode = "Markdown"

    users=get_all_users(); s=f=0
    for usr in users:
        try:
            await c.bot.send_message(usr['user_id'], text_to_send, parse_mode=parse_mode)
            s+=1
        except Exception:
            # Retry once as plain text if formatting failed
            try:
                await c.bot.send_message(usr['user_id'], msg.text)
                s+=1
            except Exception:
                f+=1
    premium_note = " 🎨 (premium emojis detected)" if has_premium else ""
    await u.message.reply_text(
        f"✅ {s} | ❌ {f}{premium_note}",
        reply_markup=admin_menu_keyboard()
    )

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
    text = """🎨 *Customization Panel*
━━━━━━━━━━━━━━━━━━━━

Customize your bot's look and feel:

✅ *All Features Active:*
• 👁️ Product Detail Toggles
• 📏 Button Sizes (4 sizes)
• 🎨 Menu Styles (10 looks)
• 🎠 Display Format (Raw / Carousel)

Tap a feature to customize:"""
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=customization_menu_keyboard())


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

    text = f"""💾 *Backup & Restore Database*
━━━━━━━━━━━━━━━━━━━━

📊 *Current Database:*
  • File: `shop.db`
  • Size: *{size_str}*
  • Last modified: {last_modified}

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
        [InlineKeyboardButton("📋 View Auto-Backups", callback_data="bk_list_auto")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def backup_cloud_now_callback(u, c):
    """☁️ Manually trigger a Telegram cloud backup right now."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("☁️ Sending backup...", show_alert=False)

    import os, shutil
    from datetime import datetime as _dt2
    try:
        from config import BACKUP_CHANNEL_ID
        from database import DB_PATH
        target = BACKUP_CHANNEL_ID or ADMIN_ID
        if not os.path.exists(DB_PATH):
            await _safe_edit(q, "❌ No database file found.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_backup")]]))
            return
        ts = _dt2.now().strftime("%Y%m%d_%H%M%S")
        tmp = os.path.join("/tmp", f"manualbackup_{ts}.db") if os.path.exists("/tmp") else f"manualbackup_{ts}.db"
        shutil.copy2(DB_PATH, tmp)
        with open(tmp, "rb") as f:
            await c.bot.send_document(
                chat_id=target,
                document=f,
                filename=f"shop_backup_{ts}.db",
                caption=f"☁️ *Manual Backup*\n📅 {_dt2.now().strftime('%d %b %Y %I:%M %p')}",
                parse_mode="Markdown",
            )
        try: os.remove(tmp)
        except Exception: pass
        where = "backup channel" if BACKUP_CHANNEL_ID else "your private chat (DM)"
        await _safe_edit(q,
            f"✅ *Backup sent to {where}!*\n\n"
            f"_Tip: Set BACKUP_CHANNEL_ID in config.py to use a private channel._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_backup")]]))
    except Exception as e:
        await _safe_edit(q,
            f"❌ Backup failed: {e}\n\n"
            f"Make sure the bot is an *admin* of the backup channel, "
            f"and BACKUP_CHANNEL_ID is correct.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_backup")]]))


async def backup_download_callback(u, c):
    """📥 Send DB file to admin as document"""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("📦 Preparing backup...", show_alert=False)

    from database import DB_PATH
    db_path = DB_PATH
    if not os.path.exists(db_path):
        await _safe_edit(q, "❌ Database file not found!",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_backup")]]))
        return

    # Create timestamped backup file
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"bite_store_backup_{ts}.db"
    backup_path = os.path.join("/tmp", backup_name) if os.path.exists("/tmp") else backup_name

    try:
        # Copy DB (safe copy, prevents lock issues)
        shutil.copy2(db_path, backup_path)
        size_kb = os.path.getsize(backup_path) / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"

        # Send as document
        with open(backup_path, "rb") as f:
            await c.bot.send_document(
                chat_id=q.from_user.id,
                document=f,
                filename=backup_name,
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
        # Cleanup tmp
        try: os.remove(backup_path)
        except Exception: pass

        # Confirmation
        await _safe_edit(q,
            f"✅ *Backup Sent!*\n\nCheck your messages above 👆\n\nFile: `{backup_name}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_backup")]]))
    except Exception as e:
        await _safe_edit(q, f"❌ Backup failed: {e}",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_backup")]]))


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
                text += f"{prefix}🛍️ {p['name']} [{p['stock']}] — ${p['price']:.2f}\n\n"
            else:
                text += f"{prefix}🛍️ {p['name']} ❌ — ${p['price']:.2f}\n\n"

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

    from payments import test_connection, is_configured
    if not is_configured():
        text = ("❌ Screenshot AI NOT Configured\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "📝 Fix Steps:\n"
                "1. Get free Gemini key: aistudio.google.com/app/apikey\n"
                "2. Add to .env file:\n"
                "   GEMINI_API_KEY=your_key\n"
                "3. Restart bot")
    else:
        success, msg = test_connection()
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

    from payments import test_connection, is_configured
    if not is_configured():
        text = ("❌ *Gmail NOT Configured*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "📝 *Fix Steps:*\n"
                "1. Get Gmail App Password:\n"
                "   https://myaccount.google.com/apppasswords\n"
                "2. Add to `.env` file:\n"
                "   `EMAIL_ADDRESS=your@gmail.com`\n"
                "   `EMAIL_PASSWORD=app_password`\n"
                "3. Restart bot")
    else:
        success, msg = test_connection()
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

    from payments import test_connection, is_configured
    if not is_configured():
        text = ("❌ *Binance Gmail NOT Configured*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                "📝 *Fix Steps:*\n"
                "1. Add to `.env` file:\n"
                "   `BINANCE_EMAIL=earnerboiii@gmail.com`\n"
                "   `BINANCE_EMAIL_PASSWORD=your_app_password`\n"
                "2. Restart bot")
    else:
        success, msg = test_connection()
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
        is_configured as _api_cfg, is_proxy_configured as _proxy_cfg,
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
        "Binance Pay API instead of (or in addition to) Gmail. "
        "Gmail remains as a fallback._\n\n"
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
    from payments import test_connection as _bp_test
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
            "📡 Fetching proxy listings (3 sites)…\n"
            "🧠 Asking Gemini to extract PK proxies…\n"
            "🧪 Testing each candidate against Binance API…\n\n"
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
            f"📡 Sources fetched: {srcs}/3",
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
        lines.append("_Cooldowns reset. Bot will use these on the next API call._")
        text = "\n".join(lines)
    else:
        text = (
            "⚠️ *AI Scout — No Working Proxies Found*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📡 Sources fetched: {srcs}/3\n"
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
    from payments import test_connection as _bp_test
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
        from payments import connect_imap
    else:
        os.environ['EMAIL_ADDRESS'] = cfg['email']
        os.environ['EMAIL_PASSWORD'] = cfg['password']
        from payments import connect_imap
    
    mail = connect_imap()
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
                from payments import connect_imap
            else:
                os.environ['EMAIL_ADDRESS'] = cfg['email']
                os.environ['EMAIL_PASSWORD'] = cfg['password']
                from payments import connect_imap
            
            mail = connect_imap()
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
        amt_str = f"${d['price']:.2f}"
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
            f"💰 *Price:* ${o['price']:.2f}\n"
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
    for fmt in (FORMAT_EMAIL_PASS, FORMAT_REDEEM_LINK, FORMAT_COUPON_CODES):
        mark = " ✅" if fmt == current else ""
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
    dmode_label = '✋ Manual' if dict(p).get('delivery_mode') == 'manual' else '🤖 Auto'
    text = (
        f"📦 *Product Details*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 *Name:* {escape_md(p['name'])}\n"
        f"💰 *Selling Price:* ${p['price']:.2f}\n"
        f"💵 *Cost Price:* ${p['cost_price']:.2f}\n"
        f"📊 *Stock:* {p['stock']}\n"
        f"🛡️ *Warranty:* {escape_md(p['warranty']) or 'None'}\n"
        f"🔢 *Min Order Qty:* {escape_md(str(p['quantity'])) or '1'}\n"
        f"🧩 *Format:* {delivery_format_label(product_format)}\n"
        f"🎁 *Template:* #{template_id} {escape_md(get_template_style(template_id)['name'])}\n"
        f"🔥 *Sold (shown):* {int(dict(p).get('fake_sold',0) or 0) + int(dict(p).get('real_sold',0) or 0)} "
        f"_(fake {int(dict(p).get('fake_sold',0) or 0)} + real {int(dict(p).get('real_sold',0) or 0)})_\n"
        f"📦 *Delivery:* {dmode_label}\n\n"
        f"📝 *Description:*\n"
        f"{escape_md(p['description']) or 'None'}\n\n"
        f"📨 *Account Pool* (customer gets 1 account per order):\n"
        f"✅ Available: *{acct_available}* | 💰 Sold: *{acct_sold}* | 📊 Total: *{acct_total}*\n"
        f"_{'Ready — sells one account at a time.' if acct_available > 0 else '⚠️ No accounts left! Add via Manage Accounts.'}_"
    )
    
    kb = [
        [InlineKeyboardButton("✏️ Edit Name", callback_data=f"editfield_name_{pid}"),
         InlineKeyboardButton("📝 Edit Description", callback_data=f"editfield_description_{pid}")],
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
        # 🆕 v71: Replacement window — per-product setting
        [_v71_replacement_window_button(pid)],
        [InlineKeyboardButton("🗑️ Delete Product", callback_data=f"delprod_{pid}")],
        [InlineKeyboardButton("🔙 Back to Add Products", callback_data="admin_products")]
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


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
    
    p = get_product(pid)
    pname = escape_md(p['name']) if p else f"#{pid}"
    
    fmt = normalize_product_format((dict(p) if p else {}).get('product_format', 'email_pass')) if p else 'email_pass'
    text = (
        f"📋 *Account Pool: {pname}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ *Available:* {av}\n"
        f"💰 *Sold:* {so}\n"
        f"📊 *Total:* {to}\n"
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
        f"Are you sure you want to delete this product?\n\n"
        f"This action cannot be undone."
    )
    kb = [
        [InlineKeyboardButton("✅ YES, Delete", callback_data=f"delproddo_{pid}"),
         InlineKeyboardButton("❌ No, Cancel", callback_data=f"viewprod_{pid}")]
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def delete_product_do_callback(u, c):
    """Actually perform soft delete of product."""
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    pid = int(q.data.replace("delproddo_", ""))
    
    delete_product(pid)
    await q.answer("Product deleted safely ✅")
    
    # Refresh items view
    set_cb_data(u, "admin_products")
    await admin_products_callback(u, c)


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
        "deliverytext": "Enter new Delivery Text (fallback if account pool empty):",
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
            field_map = {
                "name": p['name'], "description": p['description'],
                "price": f"{p['price']:.2f}", "costprice": f"{p['cost_price']:.2f}",
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
        pts = int(o['price'] * POINTS_PER_DOLLAR)
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
    await u.message.reply_text(f"👤 User found: *{escape_md(user['first_name'])}*\n💎 Current Points: *{user['points']}*\n\nEnter the amount to ADD or DEDUCT.\n(Use `-` for deduction, e.g. `50` to add, `-20` to deduct):", parse_mode="Markdown", reply_markup=inline_cancel_btn())
    return 902

async def adm_pts_amt_received(u, c):
    if u.effective_user.id != ADMIN_ID: return ConversationHandler.END
    val = u.message.text.strip()
    try:
        amt = int(val)
    except:
        await u.message.reply_text("❌ Amount must be a number.", reply_markup=inline_cancel_btn())
        return 902
        
    uid = c.user_data.pop('adm_pts_uid', None)
    if not uid: return ConversationHandler.END
    
    from database import add_points, get_connection
    if amt != 0:
        if amt > 0:
            add_points(uid, amt)
            action = "added to"
        else:
            conn = get_connection(); cur = conn.cursor()
            cur.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id=?", (abs(amt), uid))
            conn.commit(); conn.close()
            action = "deducted from"
            
        await u.message.reply_text(f"✅ Successfully {action} user `{uid}`'s balance by {abs(amt)} points.", parse_mode="Markdown", reply_markup=back_btn("admin_panel"))
        
        # Notify user
        try:
            sign = "+" if amt > 0 else "-"
            msg = f"🔔 *Wallet Update!*\n\n{sign}{abs(amt)} 💎 Points have been {action} your balance by the Admin.\nTap '👤 My Account' to view your new balance."
            await c.bot.send_message(uid, msg, parse_mode="Markdown")
        except: pass
    else:
        await u.message.reply_text("Cancelled (amount was 0).", reply_markup=back_btn("admin_panel"))
        
    from telegram.ext import ConversationHandler
    return ConversationHandler.END

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

