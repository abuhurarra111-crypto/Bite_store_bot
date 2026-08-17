def _get_eff_price(p):
    """🐛 v157 (Bulk Discount): returns the EFFECTIVE price — flash price if
    flash-sale is on, else the discounted price when discount_pct is active."""
    try:
        from database import get_discounted_price
        price, _orig, pct = get_discounted_price(p)
        return float(price)
    except Exception:
        d = dict(p)
        return float(d.get('flash_price', 0)) if d.get('is_flash_sale') else float(d.get('price', 0))

def _get_price_for_qty(p, qty=1):
    """🐛 v158 (Tiered Discount): unit price for a given quantity — picks the
    largest tier whose min_qty <= qty (Gemini: 1→$1, 10→$0.89, 30→$0.52…)."""
    try:
        base = _get_eff_price(p)
        from database import tier_price_for_qty
        unit, _min = tier_price_for_qty(int(p['id']), int(qty or 1), base)
        return float(unit)
    except Exception:
        return _get_eff_price(p)


def _get_min_qty(p):
    """🆕 Minimum order quantity (stored in the `quantity` column as a number).
    Returns 1 if not set / not numeric."""
    try:
        d = dict(p)
        raw = str(d.get('quantity', '') or '').strip()
        import re as _re
        m = _re.search(r'\d+', raw)
        n = int(m.group(0)) if m else 1
        return n if n >= 1 else 1
    except Exception:
        return 1
# ============================================
# 🛒 ORDERS (v25 — Auto-Verify for Binance + EasyPaisa)
# ============================================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton
from config import *
from database import *
from keyboards import *
from utils import escape_md, format_pkr, nav_push, build_manual_order_whatsapp_url, get_product_mode_tag, smart_text_and_mode, contains_premium_markup, fmt_price, points_from_usd, fmt_points, order_payment_context, payment_method_label
import re
import os
import logging
import secrets
import asyncio
import json




def _should_auto_deliver(product_id):
    """Check if product has auto delivery mode.
    Returns True if auto (default), False if manual."""
    if not product_id:
        return True  # Points orders always auto
    p = get_product(product_id)
    if not p:
        return True
    try:
        mode = p['delivery_mode'] or 'auto'
    except Exception:
        mode = 'auto'
    return mode == 'auto'


def _r(key, user_id=None):
    """🔧 BUG FIX #9: Use auto-register to stay consistent with other handlers.
    🆕 v79: Optional user_id triggers per-language lookup first.
    """
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


def _pkr_rate():
    """Get current USD→PKR rate from settings"""
    try: return float(get_setting("usd_pkr_rate", USD_TO_PKR_RATE))
    except: return float(USD_TO_PKR_RATE)


def _amounts_match(actual, expected, tolerance=0.005):
    """Return True only when a paid/entered USD amount matches expected price.

    🔧 v111: Old tolerance was $0.05, which is too loose for micro-priced
    products like Outlook Mail ($0.038). Use half-cent tolerance so a 1-account
    payment can never validate a higher-quantity order.
    """
    try:
        return abs(float(actual) - float(expected)) <= float(tolerance)
    except Exception:
        return False


def _expected_binance_order_amount(order):
    """Use immutable order price as Binance expected amount, not user-entered text."""
    try:
        return float(order['price'] or 0)
    except Exception:
        try:
            return float(order['binance_amount'] or 0)
        except Exception:
            return 0.0


# ════════════════════════════════════════════
# ⏱️ VERIFY COOLDOWN TRACKER (v28 — anti-spam)
# ════════════════════════════════════════════
# Tracks last verify timestamp per (user_id, order_id) pair.
# Prevents users from spamming the verify button.
import time as _time
import datetime as _dt
_verify_cooldowns = {}   # {(user_id, order_id): last_verify_timestamp}
VERIFY_COOLDOWN_SEC = 20


def _get_remaining_cooldown(user_id, order_id):
    """Returns seconds left in cooldown (0 if no cooldown)"""
    key = (user_id, order_id)
    last = _verify_cooldowns.get(key, 0)
    elapsed = _time.time() - last
    if elapsed >= VERIFY_COOLDOWN_SEC:
        return 0
    return int(VERIFY_COOLDOWN_SEC - elapsed)


def _set_cooldown(user_id, order_id):
    """Mark verify time for cooldown tracking"""
    _verify_cooldowns[(user_id, order_id)] = _time.time()
    # Cleanup old entries (older than 5 min) to prevent memory leak
    cutoff = _time.time() - 300
    for k in list(_verify_cooldowns.keys()):
        if _verify_cooldowns[k] < cutoff:
            del _verify_cooldowns[k]


def _verify_button_label(remaining_sec):
    """Returns the button label based on cooldown state"""
    if remaining_sec > 0:
        return f"⏱️ Check Again ({remaining_sec}s)"
    return "🔄 Check Again"


def _fmt_msg_name(value):
    """Premium-emoji aware product name for message templates."""
    return str(value or "") if contains_premium_markup(value) else escape_md(value)


async def _bot_send_smart(bot, chat_id, text, **kwargs):
    """Send text with automatic Markdown→HTML conversion for premium emojis.
    🔧 v133: accepts optional react_key to react to the sent message."""
    preferred = kwargs.pop("parse_mode", "Markdown")
    react_key = kwargs.pop("react_key", "")
    send_text, send_mode = smart_text_and_mode(text, preferred)
    try:
        sent = await bot.send_message(chat_id, send_text, parse_mode=send_mode, **kwargs)
    except Exception as e:
        if "parse" in str(e).lower():
            sent = await bot.send_message(chat_id, send_text, **kwargs)
        else:
            raise
    if react_key and getattr(sent, "message_id", None):
        try:
            from customization import react_to_message
            await react_to_message(bot, chat_id, sent.message_id, react_key)
        except Exception:
            pass
    return sent


def _pay_resp(key):
    try:
        return get_response_with_auto_register(key, DEFAULT_RESPONSES.get(key, ""))
    except Exception:
        return DEFAULT_RESPONSES.get(key, "")


def _fmt_usdt_amount(value):
    """Display USDT amount like product price (no unnecessary trailing zeros)."""
    try:
        return fmt_price(float(value)).lstrip('$')
    except Exception:
        return str(value)


async def _safe_send(q, context, text, **kwargs):
    send_text, send_mode = smart_text_and_mode(text, kwargs.get("parse_mode", "Markdown"))
    send_kwargs = dict(kwargs)
    send_kwargs["parse_mode"] = send_mode
    try:
        await q.edit_message_text(send_text, **send_kwargs)
        return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in send_kwargs:
            kwargs_no_md = dict(send_kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.edit_message_text(send_text, **kwargs_no_md)
                return
            except Exception: pass

    try:
        await q.edit_message_caption(caption=send_text, **send_kwargs)
        return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in send_kwargs:
            kwargs_no_md = dict(send_kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.edit_message_caption(caption=send_text, **kwargs_no_md)
                return
            except Exception: pass

    try:
        if q.message.photo or q.message.video or q.message.document:
            await q.message.reply_text(send_text, **send_kwargs)
            return
        # 🔧 v133: optional reaction on the fresh message
        _rk = kwargs.get("react_key") or ""
        sent = await context.bot.send_message(chat_id=q.message.chat_id, text=send_text, **send_kwargs)
        if _rk and getattr(sent, "message_id", None):
            try:
                from customization import react_to_message
                await react_to_message(context.bot, q.message.chat_id, sent.message_id, _rk)
            except Exception:
                pass
        return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in send_kwargs:
            kwargs_no_md = dict(send_kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await context.bot.send_message(chat_id=q.message.chat_id, text=send_text, **kwargs_no_md)
            except Exception: pass

def _clean_error_text(text):
    """Remove characters that break Telegram Markdown parsing"""
    if not text: return ""
    # Escape problematic markdown chars in error messages
    text = str(text)
    for ch in ['`', '*', '_', '[', ']']:
        text = text.replace(ch, '\\' + ch)
    return text


# ════════════════════════════════════════════
# 🛒 BUY BUTTON (single + multiple)
# ════════════════════════════════════════════
async def buy_callback(update, context):
    q = update.callback_query; await q.answer()
    nav_push(context, 'shop')
    p = get_product(int(q.data.split("_")[1]))
    if not p:
        await _safe_send(q, context, "❌ Product not found!", reply_markup=back_btn()); return
        
    is_manual = (dict(p) if p else {}).get('delivery_mode') == 'manual'
    if not is_manual and p['stock'] <= 0:
        await _safe_send(q, context, _r("out_of_stock", user_id=q.from_user.id), reply_markup=back_btn()); return

    # 🆕 Minimum order quantity: if admin set a minimum > 1, the customer must
    # order at least that many → send them into the quantity flow instead of
    # buying just 1.
    min_qty = _get_min_qty(p)
    if min_qty > 1:
        context.user_data['bulk_product_id'] = p['id']
        context.user_data['bulk_step'] = 'waiting_qty'
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]])
        if is_manual:
            stock_text = "🟢 On-Demand"; max_qty = 9999
        else:
            stock_text = f"{p['stock']}"; max_qty = p['stock']
        pkr = format_pkr(_get_eff_price(p), _pkr_rate())
        await _safe_send(q, context,
            f"🛒× *Buy {_fmt_msg_name(p['name'])}*\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Unit Price: *${_get_eff_price(p):.2f}* ≈ *{pkr}*\n"
            f"📊 Stock Available: *{stock_text}*\n\n"
            f"⚠️ *Minimum order: {min_qty}*\n"
            f"📝 Type quantity (number):\n\n"
            f"*(Min: {min_qty}, Max: {max_qty})*",
            parse_mode="Markdown", reply_markup=cancel_kb)
        return

    if not await _process_checkout_checks(q, update, context, p, 1):
        return

    await _show_payment_screen(q, context, p, 1)



async def order_creds_received(update, context):
    txt = update.message.text.strip()
    pid = context.user_data.get('order_req_pid')
    qty = context.user_data.get('order_req_qty', 1)
    p = get_product(pid)
    if not p: return True
    
    req_type = (dict(p) if p else {}).get('req_account_type', 'none')
    req_pwd = (dict(p) if p else {}).get('req_password', 0)
    
    lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
    if len(lines) < qty:
        await update.message.reply_text(f"❌ You ordered {qty} but provided {len(lines)} lines! Please provide {qty} lines.")
        return True
        
    # Validate each line
    for i, ln in enumerate(lines[:qty]):
        if req_pwd and ('|' not in ln and ':' not in ln):
            await update.message.reply_text(f"❌ Line {i+1} is missing a password separator (e.g. `|` or `:`). Please format as `email | password`")
            return True
            
        if req_type == 'gmail' and '@gmail.com' not in ln.lower():
            await update.message.reply_text(f"❌ Line {i+1} must be a Gmail account! Please send a valid Gmail.")
            return True
            
    # Success
    context.user_data['order_creds'] = "\n".join(lines[:qty])
    context.user_data.pop('order_req_step', None)
    
    # 🐛 v158: tiered quantity discount
    _unit = _get_price_for_qty(p, qty)
    total_price = _unit * qty
    pkr = format_pkr(total_price, _pkr_rate())
    
    from handlers_order import payment_method_keyboard
    msg = (
        f"✅ Account details saved.\n\n"
        f"🛒 *Confirm Purchase*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *{_fmt_msg_name(p['name'])}*\n"
        f"🔢 Quantity: *{qty}*\n"
        f"💰 Total: *${total_price:.2f}* ≈ *{pkr}*\n\n"
        f"Select payment method:"
    )
    send_text, send_mode = smart_text_and_mode(msg, "Markdown")
    await update.message.reply_text(send_text, parse_mode=send_mode, reply_markup=payment_method_keyboard(p['id'], qty))
    return True
async def buy_multiple_callback(update, context):
    """🛒× Buy Multiple"""
    q = update.callback_query; await q.answer()
    nav_push(context, 'shop')
    p = get_product(int(q.data.split("_")[1]))
    if not p:
        await _safe_send(q, context, "❌ Product not found!", reply_markup=back_btn()); return
        
    is_manual = (dict(p) if p else {}).get('delivery_mode') == 'manual'
    if not is_manual and p['stock'] <= 0:
        await _safe_send(q, context, _r("out_of_stock", user_id=q.from_user.id), reply_markup=back_btn()); return
        
    context.user_data['bulk_product_id'] = p['id']
    context.user_data['bulk_step'] = 'waiting_qty'
    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
    ])
    pkr = format_pkr(_get_eff_price(p), _pkr_rate())
    
    if is_manual:
        stock_text = "🟢 On-Demand (Unlimited)"
        max_qty = 9999
    else:
        stock_text = f"{p['stock']}"
        max_qty = p['stock']
        
    await _safe_send(q, context,
        f"🛒× *Buy Multiple*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *{_fmt_msg_name(p['name'])}*\n"
        f"💰 Unit Price: *${_get_eff_price(p):.2f}* ≈ *{pkr}*\n"
        f"📊 Stock Available: *{stock_text}*\n\n"
        f"📝 Type quantity (number):\n_Example: 5_\n\n"
        f"*(Min: 1, Max: {max_qty})*",
        parse_mode="Markdown", reply_markup=cancel_kb)

async def bulk_qty_received(update, context):
    """Handle quantity input for bulk order"""
    if context.user_data.get('bulk_step') != 'waiting_qty':
        return False
    pid = context.user_data.get('bulk_product_id')
    if not pid:
        context.user_data.pop('bulk_step', None)
        return False
    txt = update.message.text.strip()
    m = re.search(r'(\d+)', txt)
    if not m:
        await update.message.reply_text("❌ Type a number please. e.g. `5`", parse_mode="Markdown")
        return True
    qty = int(m.group(1))
    p = get_product(pid)
    if not p:
        await update.message.reply_text("❌ Product not found.", reply_markup=back_btn())
        context.user_data.pop('bulk_step', None)
        context.user_data.pop('bulk_product_id', None)
        return True
    is_manual = (dict(p) if p else {}).get('delivery_mode') == 'manual'
    # 🆕 Enforce MINIMUM order quantity set by admin.
    min_qty = _get_min_qty(p)
    if qty < min_qty:
        await update.message.reply_text(
            f"❌ Minimum order for this product is *{min_qty}*. Please type *{min_qty}* or more.",
            parse_mode="Markdown")
        return True
    if qty < 1:
        await update.message.reply_text("❌ Quantity must be at least 1.")
        return True
    if not is_manual and qty > p['stock']:
        await update.message.reply_text(
            f"❌ Only *{p['stock']}* in stock. Type a smaller number.",
            parse_mode="Markdown")
        return True
    context.user_data.pop('bulk_step', None)
    context.user_data.pop('bulk_product_id', None)

    # 🆕 Manual products: collect required email/password BEFORE payment
    # (same as single buy) so requirements are honoured for bulk orders too.
    if not await _process_checkout_checks(None, update, context, p, qty):
        return True

    # 🐛 v158: tiered quantity discount — unit price depends on qty
    _unit = _get_price_for_qty(p, qty)
    total = _unit * qty
    pkr = format_pkr(total, _pkr_rate())
    msg = (
        f"🛒× *Confirm Bulk Purchase*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *{_fmt_msg_name(p['name'])}*\n"
        f"💰 Unit Price: ${_unit:.2f}\n"
        f"📦 Quantity: *{qty}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 *Total: ${total:.2f}* ≈ *{pkr}*\n\n"
        f"Select payment method:"
    )
    send_text, send_mode = smart_text_and_mode(msg, "Markdown")
    await update.message.reply_text(send_text, parse_mode=send_mode, reply_markup=payment_method_keyboard(pid, qty=qty))
    return True


# ════════════════════════════════════════════
# 🔶 BINANCE PAYMENT (Gmail Auto-Verify)
# ════════════════════════════════════════════
# NEW FLOW: Screenshot removed!
# Step 1: User sends payment to Binance Pay ID
# Step 2: User enters their Binance sender name
# Step 3: User enters amount they sent
# Step 4: Bot checks Gmail for matching email
# Step 5: If match found → auto-deliver/points


# ════════════════════════════════════════════
# 🔶 BINANCE TRANSFER NOTE AUTO-CHECK FLOW
# ════════════════════════════════════════════
def _generate_transfer_note_id():
    """Unique numeric transfer note for Binance Pay remarks/notes."""
    # 10 digits, easy for customer to copy, unique enough with DB order id context.
    return f"{int(_time.time()) % 1000000:06d}{secrets.randbelow(10000):04d}"


def _order_qty_from_name(product_name):
    try:
        m = re.search(r'[×x]\s*(\d+)\s*$', product_name or '')
        return int(m.group(1)) if m else 1
    except Exception:
        return 1


def _binance_instruction_text(order_id, title, amount, note_id):
    bid = get_setting("binance_id", BINANCE_PAY_ID)
    holder = get_setting("binance_name", get_setting("account_name", ACCOUNT_NAME))
    return (
        f"🔶 *Binance Payment*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{title}\n"
        f"💵 Amount: *{fmt_price(amount)}*\n\n"
        f"📋 *Send payment to:*\n"
        f"• Binance Pay ID: `{bid}`\n"
        f"• Account Name: *{escape_md(holder)}*\n\n"
        f"📝 *Transfer Note / Remarks:*\n"
        f"`{note_id}`\n\n"
        f"⚠️ *Important:* Enter the Transfer Note exactly as shown above.\n"
        f"After payment, keep this chat open. You will receive confirmation here.\n\n"
        f"Order ID: `#{order_id}`"
    )


def _cancel_payment_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]])


async def _start_binance_note_order(update, context, *, is_points=False, product=None, qty=1, amount=0.0, points_amount=None):
    """Create a Binance pending order, assign transfer note id, send instructions."""
    q = update.callback_query
    u = q.from_user
    un = u.first_name or str(u.id)
    save_user(u.id, u.username or '', u.first_name or '')

    note_id = _generate_transfer_note_id()
    amount = float(amount)
    if amount <= 0:
        await _safe_send(q, context, "❌ Invalid amount.", reply_markup=back_btn())
        return

    # Clear old payment state
    for k in ['ep_step','ep_amount','ep_tid','binance_step','binance_amount','binance_txid',
              'binance_product_id','binance_qty','binance_name','jc_step','jc_amount','jc_tid',
              'pending_order_id']:
        context.user_data.pop(k, None)

    if is_points:
        pts = points_from_usd(amount)
        pts_txt = fmt_points(pts)
        oid = create_order(u.id, un, 0, f"💎 {pts_txt} Points", amount, 'binance', note_id, amount, 'USDT', 'points')
        title = f"💎 Deposit for *{pts_txt} Points*"
    else:
        p = product
        if not p:
            await _safe_send(q, context, "❌ Product not found.", reply_markup=back_btn())
            return
        if int(p['stock'] or 0) < int(qty):
            await _safe_send(q, context, f"❌ Only {p['stock']} in stock!", reply_markup=back_btn())
            return
        pname = p['name'] if int(qty) == 1 else f"{p['name']} × {int(qty)}"
        creds = context.user_data.pop('order_creds', '')
        oid = create_order(u.id, un, p['id'], pname, amount, 'binance', note_id, amount, 'USDT', 'product', creds, qty=int(qty))
        title = f"📦 Product: *{_fmt_msg_name(pname)}*"

    set_order_payment_note(oid, note_id)
    update_order_status(oid, 'binance_waiting')
    context.user_data['pending_order_id'] = oid
    context.user_data['binance_step'] = 'auto_note_waiting'

    await _safe_send(q, context, _binance_instruction_text(oid, title, amount, note_id),
                     parse_mode="Markdown", reply_markup=_cancel_payment_keyboard())


# ════════════════════════════════════════════════════════════════
# 🆕 v62 — BINANCE ORDER-ID FLOW (clean professional, no API mention)
# ════════════════════════════════════════════════════════════════
def _binance_orderid_instructions(*, title, amount, order_id_for_display=None):
    bid = get_setting("binance_id", BINANCE_PAY_ID)
    holder = get_setting("binance_name", get_setting("account_name", ACCOUNT_NAME))
    tpl = _pay_resp("payment_binance_pay_orderid")
    txt = tpl.format(
        title=title, amount=_fmt_usdt_amount(amount),
        pay_id=escape_md(bid), holder=escape_md(holder)
    )
    if order_id_for_display:
        txt += f"\n\n_Your last submitted Order ID:_ `{escape_md(order_id_for_display)}`"
    return txt


async def _start_binance_order_id_flow(update, context, *, is_points, product, qty, amount, points_amount=None):
    """Create a pending Binance order, ask the user to paste their Order ID."""
    q = update.callback_query
    u = q.from_user
    un = u.first_name or str(u.id)
    save_user(u.id, u.username or "", u.first_name or "")

    amount = float(amount)
    if amount <= 0:
        await _safe_send(q, context, "❌ Invalid amount.", reply_markup=back_btn())
        return

    if is_points:
        pts = points_from_usd(amount)
        pts_txt = fmt_points(pts)
        oid = create_order(
            u.id, un, 0, f"💎 {pts_txt} Points",
            amount, "binance", "", amount, "USDT", "points",
        )
        title = f"💎 You will receive *{pts_txt} Points*"
    else:
        p = product
        if not p:
            await _safe_send(q, context, "❌ Product not found.", reply_markup=back_btn())
            return
        if int(p["stock"] or 0) < int(qty):
            await _safe_send(q, context, f"❌ Only {p['stock']} in stock!", reply_markup=back_btn())
            return
        pname = p["name"] if int(qty) == 1 else f"{p['name']} × {int(qty)}"
        creds = context.user_data.pop("order_creds", "")
        oid = create_order(
            u.id, un, p["id"], pname,
            amount, "binance", "", amount, "USDT", "product", creds,
            qty=int(qty),
        )
        title = f"📦 *{_fmt_msg_name(pname)}*"

    update_order_status(oid, "binance_waiting")
    context.user_data["pending_order_id"] = oid
    context.user_data["binance_step"]     = "waiting_order_id"
    context.user_data["binance_amount"]   = amount

    bid_for_copy = get_setting("binance_id", BINANCE_PAY_ID)
    # 🆕 v144.1: Binance Pay ID copy + cancel are now EDITABLE registry buttons
    # (rename / premium emoji / color) — mirror of the Bybit flow.
    kb = InlineKeyboardMarkup([
        [_make_flow_btn("pay_copy_binance_payid", copy_text=CopyTextButton(bid_for_copy))],
        [_make_flow_btn("pay_cancel_payment", callback_data="cancel_order")],
    ])
    await _safe_send(
        q, context,
        _binance_orderid_instructions(title=title, amount=amount),
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def binance_order_id_received(update, context):
    """User pasted their Binance Order ID — verify the payment now."""
    if context.user_data.get("binance_step") != "waiting_order_id":
        return False

    raw = (update.message.text or "").strip()
    # Clean up — Binance Order IDs are alphanumeric, possibly with underscores
    order_id = re.sub(r"[^A-Za-z0-9_\-]", "", raw)
    if len(order_id) < 6 or len(order_id) > 64:
        await update.message.reply_text(
            "❌ That doesn't look like a valid Order ID.\n\n"
            "Please copy the *Order ID* from your Binance app transaction "
            "screen and paste it here (it's usually a long string of "
            "letters and numbers).",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
            ]),
        )
        return True

    oid = context.user_data.get("pending_order_id")
    o = get_order(oid) if oid else None
    if not o:
        await update.message.reply_text("❌ Order not found. Please start again.", reply_markup=back_btn())
        for k in ["binance_step", "binance_order_id", "pending_order_id"]:
            context.user_data.pop(k, None)
        return True

    # 🆕 v64 BUG FIX: if order is already delivered (e.g. background job picked it up
    # while user was typing), just acknowledge silently — never show "not confirmed".
    if o["status"] == "delivered":
        for k in ["binance_step", "binance_order_id", "binance_amount",
                  "binance_product_id", "binance_qty", "points_mode",
                  "pending_order_id", "points_amount", "order_qty"]:
            context.user_data.pop(k, None)
        await update.message.reply_text(
            "✅ *Your payment is already confirmed!*\n\n"
            "Check your account / order history.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
                [InlineKeyboardButton("🏠 Main Menu",     callback_data="main_menu")],
            ]),
        )
        return True

    # 🆕 v64: also short-circuit if status indicates payment already accepted
    if o["status"] in ("paid_pending_delivery", "completed", "supplier_processing"):
        for k in ["binance_step", "binance_order_id", "binance_amount",
                  "binance_product_id", "binance_qty", "points_mode",
                  "pending_order_id", "points_amount", "order_qty"]:
            context.user_data.pop(k, None)
        await update.message.reply_text(
            "✅ *Your payment is already confirmed!*\n\n"
            "Your order is being processed and will be delivered shortly.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
                [InlineKeyboardButton("🏠 Main Menu",     callback_data="main_menu")],
            ]),
        )
        return True

    expected_amount = float(o["price"] or context.user_data.get("binance_amount") or 0)
    context.user_data["binance_order_id"] = order_id

    # Save the order id on the order row (reuse payment_note_id slot for now)
    try:
        set_order_payment_note(oid, order_id)
    except Exception:
        pass

    processing_msg = await update.message.reply_text(
        f"⏳ *Processing your payment…*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Order #{oid}  •  ${expected_amount:.2f}\n"
        f"Order ID: `{order_id}`\n\n"
        f"_Please wait a few seconds._",
        parse_mode="Markdown",
    )

    # Verify — API-first when toggle ON (with email fallback). User has no idea.
    from payments import verify_payment_unified
    result = await asyncio.to_thread(
        verify_payment_unified,
        expected_amount=expected_amount,
        order_id=order_id,
        use_email_fallback=True,
    )

    # 🆕 v64: Re-check order status AFTER verify call too — background job could
    # have delivered it during this verify call's seconds-long window.
    fresh = get_order(oid)
    if fresh and fresh["status"] in ("delivered", "paid_pending_delivery", "completed", "supplier_processing"):
        try: await processing_msg.delete()
        except Exception: pass
        for k in ["binance_step", "binance_order_id", "binance_amount",
                  "binance_product_id", "binance_qty", "points_mode",
                  "pending_order_id", "points_amount", "order_qty"]:
            context.user_data.pop(k, None)
        # Don't double-send success message — the background job's success message
        # already went out. Just silently consume the user's Order-ID submission.
        return True

    if result.get("success"):
        try: await processing_msg.delete()
        except Exception: pass
        sender_name = result.get("sender_name") or ""
        await _complete_binance_name_amount_order(context, get_order(oid), result, sender_name, expected_amount)
        for k in ["binance_step", "binance_order_id", "binance_amount",
                  "binance_product_id", "binance_qty", "points_mode",
                  "pending_order_id", "points_amount", "order_qty"]:
            context.user_data.pop(k, None)
        return True

    # Not matched — show retry / ticket buttons (no API/Gmail language)
    try: await processing_msg.delete()
    except Exception: pass

    status = result.get("status", "not_found")
    if status == "already_used":
        update_order_status(oid, "rejected")
        await update.message.reply_text(
            f"❌ *This payment has already been used.*\n\n"
            f"Order #{oid} has been rejected. If you think this is a mistake, "
            f"please open a support ticket.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="st_new")],
                [InlineKeyboardButton("🔙 Main Menu",            callback_data="main_menu")],
            ]),
        )
        for k in ["binance_step", "binance_order_id", "pending_order_id"]:
            context.user_data.pop(k, None)
        return True

    # Still waiting — keep order pending, give retry/ticket options
    context.user_data["binance_step"] = "awaiting_oid_verify"

    bid = get_setting("binance_id", BINANCE_PAY_ID)
    holder = get_setting("binance_name", get_setting("account_name", ACCOUNT_NAME))

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Check Again",            callback_data=f"vpoid_{oid}")],
        [InlineKeyboardButton("🎫 Create Support Ticket",  callback_data="st_new")],
        [InlineKeyboardButton("❌ Cancel Payment",         callback_data="cancel_order")],
    ])
    text = (
        f"⏳ *Payment not confirmed yet*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Order #{oid}  •  ${expected_amount:.2f}\n"
        f"Order ID: `{order_id}`\n\n"
        f"📌 Please make sure:\n"
        f"  • You sent *exactly ${expected_amount:.2f}* to Pay ID `{bid}`\n"
        f"  • The Order ID above matches the one in your Binance app\n\n"
        f"Payments can take up to 2 minutes to confirm. Tap *Check Again* "
        f"to retry, or open a *Support Ticket* if you need help."
    )
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    await update.message.reply_text(send_text, parse_mode=send_mode, reply_markup=kb)

    # Notify admin (🐛 v145: enriched with product + supplier cost + selling)
    try:
        u2 = update.effective_user
        ctx_lines = order_payment_context(oid)
        ctx_txt = "\n".join(ctx_lines) + ("\n" if ctx_lines else "")
        await context.bot.send_message(
            ADMIN_ID,
            f"🟡 *Binance Pay Pending #{oid}*\n"
            f"User: {escape_md(u2.first_name or '?')} (`{u2.id}`)\n"
            f"Method: 🪙 Binance Pay\n"
            f"Amount: ${expected_amount:.2f}\n"
            f"{ctx_txt}"
            f"Order ID submitted: `{order_id}`\n"
            f"_Waiting for confirmation…_",
            parse_mode="Markdown",
        )
    except Exception:
        pass
    return True


async def verify_order_id_callback(update, context):
    """🔄 Check Again button for Order-ID flow."""
    q = update.callback_query
    user_id = q.from_user.id
    try:
        oid = int(q.data.replace("vpoid_", ""))
    except ValueError:
        await q.answer("Invalid order", show_alert=True)
        return

    # Cooldown
    remaining = _get_remaining_cooldown(user_id, oid)
    if remaining > 0:
        await q.answer(f"⏱️ Please wait {remaining}s before checking again.", show_alert=True)
        return

    await q.answer("⏳ Checking…", show_alert=False)
    o = get_order(oid)
    if not o:
        await q.edit_message_text("❌ Order not found.", reply_markup=back_btn()); return
    if o["status"] == "delivered":
        await q.edit_message_text(
            "✅ *Payment already confirmed!*\n\nYour order has been delivered. "
            "Check your account!",
            parse_mode="Markdown", reply_markup=back_btn())
        return

    _set_cooldown(user_id, oid)

    order_id = o.get("payment_note_id") or context.user_data.get("binance_order_id") or ""
    expected_amount = float(o["price"] or 0)

    if not order_id:
        await q.edit_message_text(
            "❌ No Order ID on file for this order. Please start a new order.",
            reply_markup=back_btn())
        return

    try:
        await q.edit_message_text(
            f"⏳ *Processing your payment…*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Order #{oid}  •  ${expected_amount:.2f}\n"
            f"Order ID: `{order_id}`\n\n"
            f"_Please wait a few seconds._",
            parse_mode="Markdown")
    except Exception:
        pass

    from payments import verify_payment_unified
    result = await asyncio.to_thread(
        verify_payment_unified,
        expected_amount=expected_amount,
        order_id=order_id,
        use_email_fallback=True,
    )

    # 🆕 v64: After the verify call, re-check status — background job may have
    # already delivered this order during our verify window.
    fresh2 = get_order(oid)
    if fresh2 and fresh2["status"] in ("delivered", "paid_pending_delivery", "completed", "supplier_processing"):
        for k in ["binance_step", "binance_order_id", "pending_order_id"]:
            context.user_data.pop(k, None)
        try:
            await q.edit_message_text(
                "✅ *Your payment is already confirmed!*\n\n"
                "Check your account / order history.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
                    [InlineKeyboardButton("🏠 Main Menu",     callback_data="main_menu")],
                ]),
            )
        except Exception: pass
        return

    if result.get("success"):
        sender_name = result.get("sender_name") or ""
        await _complete_binance_name_amount_order(context, o, result, sender_name, expected_amount)
        for k in ["binance_step", "binance_order_id", "pending_order_id"]:
            context.user_data.pop(k, None)
        return

    status = result.get("status", "not_found")
    if status == "already_used":
        update_order_status(oid, "rejected")
        await q.edit_message_text(
            "❌ *This payment has already been used.*\n\nOrder rejected.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="st_new")],
                [InlineKeyboardButton("🔙 Main Menu",            callback_data="main_menu")],
            ]),
        )
        return

    # Still not found
    cooldown = _get_remaining_cooldown(user_id, oid)
    btn_label = _verify_button_label(cooldown)
    bid = get_setting("binance_id", BINANCE_PAY_ID)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(btn_label,                  callback_data=f"vpoid_{oid}")],
        [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="st_new")],
        [InlineKeyboardButton("❌ Cancel Payment",        callback_data="cancel_order")],
    ])
    await q.edit_message_text(
        f"⏳ *Still waiting for payment confirmation*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Order #{oid}  •  ${expected_amount:.2f}\n"
        f"Order ID: `{order_id}`\n\n"
        f"📌 Please verify:\n"
        f"  • Amount sent is exactly *${expected_amount:.2f}*\n"
        f"  • Receiving Pay ID is `{bid}`\n"
        f"  • Order ID matches your Binance receipt\n\n"
        f"Tap *Check Again* in a few seconds, or open a *Support Ticket*.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def _send_deposit_success(bot, order, paid_amount):
    # v120 safety: never credit the same points deposit twice if a retry/race
    # calls this helper after the order is already delivered.
    try:
        fresh = get_order(order['id']) or order
        if fresh and str(fresh.get('status') or '') == 'delivered':
            return True
        order = fresh or order
    except Exception:
        pass
    pts = points_from_usd(float(paid_amount or order['price'] or 0))
    if pts <= 0:
        pts = points_from_usd(float(order['price'] or 0))
    save_user(order['user_id'], '', order['user_name'] or '')
    add_points(order['user_id'], pts, tx_type='deposit', description='Points deposit', event_id=f"deposit_order_{order['id']}", order_id=order['id'])
    update_order_status(order['id'], 'delivered')
    total_pts = get_user_points(order['user_id'])
    text = (
        f"🎉 *Deposit Successful!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ Your payment has been confirmed.\n"
        f"💎 Points Added: *{fmt_points(pts)}*\n"
        f"💰 Amount: *{fmt_price(float(paid_amount or order['price'] or 0))}*\n"
        f"🧾 Order ID: `#{order['id']}`\n\n"
        f"📊 New Points Balance: *{fmt_points(total_pts)}*\n\n"
        f"Thank you for your deposit!"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy More", callback_data="shop")],
        [InlineKeyboardButton("📊 My Account", callback_data="my_account")],
    ])
    await _bot_send_smart(bot, order['user_id'], text, parse_mode="Markdown", reply_markup=kb)


async def _notify_admin_order_delivered(bot, order, qty=1, supplier_name="",
                                        cost_usd=None, stock_before=None, stock_after=None,
                                        payment_method="", user_wallet_before=None,
                                        user_wallet_after=None, api_balance_before=None,
                                        api_balance_after=None, extra_note=""):
    """🆕 v170.23: SINGLE unified admin notification for EVERY product delivery
    (supplier + own/manual). Full detail: buyer name + @username + ID, premium-
    emoji product name, qty, payment, user wallet before/after, supplier + API
    balance (supplier products), stock before/after (own products), cost/sold/
    profit, PKT time.

    🐛 v170.23 FIX: pehle supplier products par 2 notifications aati thin
    ("Order Delivered!" + "Supplier order delivered!"). Ab sirf EK aati hai.
    🐛 v170.23 FIX: buyer username + product premium emoji ab har notification
    me hain (user demand — pehle bottom wale me dono missing the).
    🛡️ v170.23: customer ko kabhi supplier ka naam nahi jaata — ye sirf ADMIN
    notification hai (notify_admin → ADMIN_ID).

    🆕 v170.28: FREEBIE orders (payment_method='freebie') yahan SKIP hote hain —
    unka apna DETAILED "🎁 FREEBIE CLAIMED!" notification handlers_freebies.py
    bhejta hai (duplicate "Order Delivered" nahi aata)."""
    try:
        if str((order.get('payment_method') if isinstance(order, dict) else '') or '').strip().lower() == 'freebie':
            return
        from utils import notify_admin
        from datetime import datetime, timezone, timedelta
        oid = int(order.get('id') or 0)
        uid = int(order.get('user_id') or 0)
        sold = float(order.get('price') or 0)
        qty = max(1, int(qty or 1))
        # ── customer name + @username ──
        fname = str(order.get('user_name') or '').strip()
        uname = ""
        try:
            from database import get_user
            u = get_user(uid)
            if u:
                uname = str(u.get('username') or '').strip()
                if not fname:
                    fname = str(u.get('first_name') or '').strip()
        except Exception:
            pass
        # ── profit ──
        try:
            if cost_usd is None:
                from database import get_product
                _p = get_product(order.get('product_id') or 0)
                cost = float((dict(_p) if _p else {}).get('cost_price') or 0)
            else:
                cost = float(cost_usd)
        except Exception:
            cost = 0.0
        profit = round((sold - cost) * qty, 6)
        # ── user wallet before/after (auto-compute when not provided) ──
        if user_wallet_before is None or user_wallet_after is None:
            try:
                from database import get_user
                _uw = get_user(uid)
                _w_after = float((_uw.get('points') or 0) if _uw else 0)
                _w_before = _w_after
                if str(order.get('payment_method') or '').lower() == 'wallet':
                    _w_before = _w_after + float(order.get('binance_amount') or 0)
                user_wallet_before, user_wallet_after = _w_before, _w_after
            except Exception:
                pass
        # 🐛 v170.10: ye message HTML mode me render hota hai (premium emoji).
        # markdownish_to_html `_`/`*` ko italic/bold bana deta hai (escape respect
        # nahi karta) → isliye unhe HTML entities mein convert karo (&#95; etc.)
        # taake literal dikhe. Backtick bhi clean karo.
        def _safe_plain(s):
            try:
                import html as _html
                from utils import html_strip_tags as _hst
                s = _html.escape(_hst(s or "") or "")
            except Exception:
                pass
            return (s.replace("`", "'")
                     .replace("_", "&#95;")
                     .replace("*", "&#42;")
                     .replace("[", "&#91;").replace("]", "&#93;"))
        fname = _safe_plain(fname)
        uname = _safe_plain(uname)
        name_line = f"{fname} (@{uname})" if (fname and uname) else (fname or uname or "—")
        # ── PKT time (user's timezone) ──
        pk_time = datetime.now(timezone(timedelta(hours=5))).strftime("%Y-%m-%d %I:%M:%S %p PKT")
        title = "✅ *Supplier order delivered!*" if supplier_name else "🎉 *Order Delivered!* ✅"
        lines = [
            title,
            "━━━━━━━━━━━━━━━━━━━━",
            f"🛒 Order: `#{oid}`",
            f"🕒 Time: `{pk_time}`",
            f"👤 Customer: `{name_line}` (`{uid}`)",
            f"📦 Product: {_fmt_msg_name(order.get('product_name'))}",
            f"🔢 Qty: *{qty}*",
        ]
        pm = str(payment_method or order.get('payment_method') or '').strip()
        if pm:
            lines.append(f"💳 Payment: `{_safe_plain(pm)}`")
        if user_wallet_before is not None and user_wallet_after is not None:
            lines.append(f"💎 User Wallet: `{fmt_points(user_wallet_before)}` → `{fmt_points(user_wallet_after)}`")
        if supplier_name:
            try:
                import html as _html2
                from utils import html_strip_tags as _hst2
                supplier_name = _html2.escape(_hst2(str(supplier_name)))
            except Exception:
                pass
            lines.append(f"🏬 Supplier: *{supplier_name}*")
            if api_balance_before is not None and api_balance_after is not None:
                lines.append(f"🔌 API Balance: `{fmt_price(api_balance_before)}` → `{fmt_price(api_balance_after)}`")
        if stock_before is not None and stock_after is not None:
            lines.append(f"📊 Stock: *{stock_before}* → *{stock_after}*")
        lines.append(f"💰 Cost: `{fmt_price(cost)}` · Sold: `{fmt_price(sold)}`")
        lines.append(f"📈 Profit: `{fmt_price(profit)}`")
        if extra_note:
            lines.append("")
            lines.append(f"⚠️ {extra_note}")
        await notify_admin(bot, "\n".join(lines))
    except Exception as e:
        import logging as _l
        _l.getLogger(__name__).debug(f"[admin-delivered-notify] {e}")


async def _send_static_media_delivery(bot, order, product, method, amount, pts_bonus=0):
    """Send static media/file delivery to customer instantly.
       🆕 v66: 10pts bonus REMOVED. Tier progress hint appended instead."""
    pd = dict(product) if product else {}
    file_id = pd.get('delivery_file_id', '') or ''
    file_type = pd.get('delivery_file_type', '') or 'document'
    file_name = pd.get('delivery_file_name', '') or file_type
    caption_text = (pd.get('delivery_caption', '') or pd.get('delivery_text', '') or '').strip()

    from database import save_order_delivery_content, add_order_delivery, set_order_delivery_file
    history_note = f"[Static {file_type}: {file_name}]"
    if caption_text:
        history_note += f"\n{caption_text}"
    save_order_delivery_content(order['id'], history_note)
    # 🆕 v161.20: log the ACTUAL delivered media file so the admin can re-open
    # the exact file (photo/video/document) from Completed Orders.
    add_order_delivery(order['id'], kind=file_type or 'document',
                       content=caption_text,
                       file_id=file_id,
                       file_name=file_name)
    if file_id:
        set_order_delivery_file(order['id'], file_id)
    update_order_status(order['id'], 'delivered')
    # 🆕 v170.23: ADMIN notification — static media delivered (full detail:
    # username + premium emoji + payment + wallet + profit).
    try:
        await _notify_admin_order_delivered(
            bot, order, qty=1,
            payment_method=str(order.get('payment_method') or ''))
    except Exception:
        pass
    # 🆕 v66: bonus 10pts removed — no add_points call here.

    header = (
        f"🎉 *Thanks for purchasing!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ Payment confirmed and your product is delivered below.\n"
        f"🧾 Order ID: `#{order['id']}`\n"
        f"📦 Product: *{_fmt_msg_name(order['product_name'])}*\n"
        f"💳 Payment: *{escape_md(method)}*\n"
    )
    # v121: Tier progress hint only. Per-order bonus points are disabled so
    # payment success/product delivery never grants extra points.
    try:
        from loyalty_extras import build_tier_progress_line
        tier_line = build_tier_progress_line(order['user_id'])
        if tier_line:
            header += f"{tier_line}\n"
    except Exception: pass
    header += "\nPlease keep your delivery file/details safe."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy More", callback_data="shop")],
        [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
    ])
    send_text, send_mode = smart_text_and_mode(header, "Markdown")
    try:
        if file_type == 'photo':
            await bot.send_photo(order['user_id'], file_id, caption=send_text[:1024], parse_mode=send_mode, reply_markup=kb)
        elif file_type == 'video':
            await bot.send_video(order['user_id'], file_id, caption=send_text[:1024], parse_mode=send_mode, reply_markup=kb)
        else:
            await bot.send_document(order['user_id'], file_id, caption=send_text[:1024], parse_mode=send_mode, reply_markup=kb)
    except Exception:
        # Fallback: send text first, then raw document if Telegram rejects caption/parse mode.
        await bot.send_message(order['user_id'], send_text, parse_mode=send_mode, reply_markup=kb)
        try:
            if file_type == 'photo':
                await bot.send_photo(order['user_id'], file_id)
            elif file_type == 'video':
                await bot.send_video(order['user_id'], file_id)
            else:
                await bot.send_document(order['user_id'], file_id)
        except Exception:
            await bot.send_message(order['user_id'], "⚠️ Delivery file could not be sent. Please contact support.")
    return True


async def fulfill_paid_product_order(bot, order, paid_amount=None, *, payment_method_label=None, award_bonus=True):
    """Central fulfillment router for any paid PRODUCT order.

    Routes after payment success:
    - manual product  -> paid_pending_delivery + customer/admin notifications
    - auto/static     -> instant delivery via build_delivery_from_accounts()

    This keeps product orders out of deposit history and prevents the old mixed
    payment/order workflow from sending every product to manual deposit screens.
    """
    # Refresh row so status/product data is current
    try:
        order = get_order(order['id']) or order
    except Exception:
        pass

    if not order or not order['product_id']:
        return False

    # 🔧 v111 idempotency guard: if a payment checker/user retry calls the
    # fulfillment function again after delivery/cancel/refund, never deliver or
    # buy supplier stock a second time.
    try:
        _st = str(order.get('status') or '')
        if _st in ('delivered', 'supplier_processing', 'supplier_retry_pending', 'refunded', 'cancelled', 'rejected'):
            return True
    except Exception:
        pass

    # 🆕 v82: External Supplier ROUTER — if the product is linked to a REST-API
    # supplier, delegate delivery to the router. Router handles: adapter call,
    # v72 byte-perfect delivery, bulk .txt file, auto-refund on failure.
    try:
        p_check = get_product(order['product_id'])
        if p_check and (dict(p_check).get('ext_product_id') or 0) > 0:
            from ext_suppliers import route_order_to_supplier
            handled = await route_order_to_supplier(bot, order)
            if handled:
                return True
    except Exception as _rt_err:
        import logging as _l
        _l.getLogger(__name__).error(f"[fulfill] supplier router failed: {_rt_err}")
        # Fall through to normal flow (safer than crashing)

    p = get_product(order['product_id'])
    amount = float(paid_amount if paid_amount is not None else (order['price'] or 0))
    method = payment_method_label or str(order['payment_method'] or '').title()
    qty = _order_qty_from_name(order['product_name'])

    if not p:
        update_order_status(order['id'], 'paid_pending_delivery')
        await _bot_send_smart(
            bot,
            order['user_id'],
            f"✅ *Payment Confirmed!*\n\nYour order `#{order['id']}` has been received. The store owner will complete it soon.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📜 Order History", callback_data="my_orders")]])
        )
        return True

    pd = dict(p)
    is_manual = (pd.get('delivery_mode') == 'manual')
    has_static_text = bool((pd.get('delivery_text') or '').strip())

    # Manual products must never auto-deliver, even if they have instructions text.
    if is_manual:
        req_type = pd.get('req_account_type', 'none') or 'none'
        if req_type != 'none':
            await _begin_manual_details_after_payment(bot, order, p, method)
            return True

        update_order_status(order['id'], 'paid_pending_delivery')
        customer_text = (
            f"✅ *Payment Confirmed!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 Product: *{_fmt_msg_name(order['product_name'])}*\n"
            f"🧾 Order ID: `#{order['id']}`\n"
            f"💳 Payment: *{escape_md(method)}*\n\n"
            f"Your order details have been sent to the Bite Store owner.\n"
            f"Your product will be completed and delivered within *1–6 hours*.\n\n"
            f"If your order is not completed in time, please create a support ticket for fast assistance."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎫 Support", callback_data="support_menu")],
            [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
            [InlineKeyboardButton("🛒 Buy More", callback_data="shop")],
        ])
        await _bot_send_smart(bot, order['user_id'], customer_text, parse_mode="Markdown", reply_markup=kb)
        try:
            chat_url = None
            # Username is not stored reliably in orders; admin panel/chat system is handled in Step 3.
            admin_text = (
                f"🔔 *Paid Manual Order*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Order: `#{order['id']}`\n"
                f"Customer: {escape_md(order['user_name'])} (`{order['user_id']}`)\n"
                f"Product: *{_fmt_msg_name(order['product_name'])}*\n"
                f"Payment: *{escape_md(method)}* | Amount: `{amount:.2f}`\n\n"
                f"Open *Pending Manual Delivery* to complete this order."
            )
            kb_admin = InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Pending Manual Delivery", callback_data="adm_pending_delivery")],
                [InlineKeyboardButton("💬 Internal Chat", callback_data=f"adm_chat_{order['user_id']}")],
                # 🆕 v65: Refund + Cancel buttons
                [InlineKeyboardButton("🔄 Refund (Add Points)", callback_data=f"adm_refund_{order['id']}"),
                 InlineKeyboardButton("❌ Cancel Order",         callback_data=f"adm_cancel_{order['id']}")],
            ])
            await _bot_send_smart(bot, ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=kb_admin)
        except Exception:
            pass
        return True

    # Auto/static media delivery: photo/video/PDF/document delivered instantly.
    # 🆕 v66: pts_bonus REMOVED — always 0 (kept var for back-compat of helper sig)
    pts_bonus = 0
    if pd.get('delivery_file_id'):
        return await _send_static_media_delivery(bot, order, p, method, amount, pts_bonus=pts_bonus)

    # Auto/static text delivery: static text handled inside build_delivery_detailed();
    # account-pool delivery is also handled there.
    # 🔧 AUDIT-FIX C1/C2 (2026-07-31): use the structured result so an order is
    # NEVER marked 'delivered' when the stock pool couldn't cover the full qty.
    from database import build_delivery_detailed, save_order_delivery_content, add_order_delivery
    # 🆕 v170.10: stock BEFORE capture (admin delivered-notification ke liye)
    try:
        _stock_before = int(dict(get_product(order['product_id'])).get('stock') or 0)
    except Exception:
        _stock_before = None
    dres = build_delivery_detailed(order['product_id'], order['id'], qty, order['user_id'])
    delivery = dres['text']
    save_order_delivery_content(order['id'], delivery)
    # 🆕 v161.20: audit log — the exact delivery text is stored so Completed
    # Orders can show/re-open it later.
    add_order_delivery(order['id'], kind='text', content=delivery)

    if not dres['ok']:
        # ⛔ Not fully fulfilled — park the order for the admin instead of
        # silently "delivering" an out-of-stock notice.
        got, want = dres.get('delivered', 0), dres.get('requested', qty)
        update_order_status(order['id'], 'paid_pending_delivery')
        note = (
            f"⚠️ *Order #{order['id']} — not fully delivered*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 Product: *{_fmt_msg_name(order['product_name'])}*\n"
            f"🔢 Requested: *{want}* · Delivered: *{got}*\n\n"
        )
        if got:
            note += "✅ What was available has been sent in the next message.\n"
        note += (
            f"The product ran out of stock while your order was processing.\n"
            f"Your order is now in *Pending Delivery* — the store will complete "
            f"the remaining *{max(0, want - got)}* or refund your wallet.\n\n"
            f"🎫 You can also open a Support Ticket anytime."
        )
        kb_pending = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎫 Support", callback_data="support_menu")],
            [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
            [InlineKeyboardButton("🛒 Buy More", callback_data="shop")],
        ])
        await _bot_send_smart(bot, order['user_id'], note, parse_mode="Markdown")
        if delivery and got:
            await _bot_send_smart(bot, order['user_id'], delivery, parse_mode=None,
                                  reply_markup=kb_pending)
        try:
            from utils import notify_admin as _na
            await _na(bot,
                f"🚨 *Order #{order['id']} — partially delivered (OOS)*\n"
                f"🔢 Requested: `{want}` · Delivered: `{got}`\n"
                f"📦 Product: {escape_md(str(order.get('product_name') or '?')[:70])}\n"
                f"👤 Customer: `{order['user_id']}`\n\n"
                f"Complete the shortfall via *Pending Manual Delivery* or refund.")
        except Exception as _na_err:
            import logging as _l
            _l.getLogger(__name__).warning(f"[fulfill] admin OOS alert failed: {_na_err}")
        return True

    update_order_status(order['id'], 'delivered')

    # 🆕 v170.10: ADMIN notification — own product delivered (username + qty +
    # stock before/after + sold/profit).
    try:
        _stock_after = int(dict(get_product(order['product_id']) or {}).get('stock') or 0)
    except Exception:
        _stock_after = None
    try:
        await _notify_admin_order_delivered(
            bot, order, qty=qty, stock_before=_stock_before, stock_after=_stock_after,
            payment_method=str(order.get('payment_method') or ''))
    except Exception:
        pass

    # 🆕 v66: bonus 10pts removed entirely — no add_points here.

    # 🆕 v72 BUG FIX: Send delivery content as a SEPARATE message in its native
    # format (HTML for templated, plain for static text). Previously this code
    # escape_md()'d the entire pre-rendered delivery which MANGLED special
    # chars in user content (URLs, passwords, codes etc.).
    delivery_label = "Your Product Details" if not has_static_text else "Your Delivery"
    # 🆕 v170.29: FREEBIE orders → "Thanks for purchasing" NAHI; freebie wala
    # header (user ko pata chale ke FREE claim kiya).
    is_freebie = str(order.get('payment_method') or '').strip().lower() == 'freebie' \
                 or str(payment_method_label or '').startswith('🎁 FREEBIE')
    if is_freebie:
        text = (
            f"🎁 *Freebie Claimed — FREE!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Your FREE product is delivered below — no payment needed!\n"
            f"🧾 Order ID: `#{order['id']}`\n"
            f"📦 Product: *{_fmt_msg_name(order['product_name'])}*\n\n"
            f"📨 *{delivery_label}* — see the next message."
        )
    else:
        text = (
            f"🎉 *Thanks for purchasing!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Payment confirmed and your product is delivered below.\n"
            f"🧾 Order ID: `#{order['id']}`\n"
            f"📦 Product: *{_fmt_msg_name(order['product_name'])}*\n"
            f"💳 Payment: *{escape_md(method)}*\n\n"
            f"📨 *{delivery_label}* — see the next message."
        )
    # v121: Tier progress hint only. No extra points on payment success.
    # 🆕 v170.29: freebie par tier hint skip (koi spend nahi).
    if not is_freebie:
        try:
            from loyalty_extras import build_tier_progress_line
            tier_line = build_tier_progress_line(order['user_id'])
            if tier_line:
                text += f"\n\n{tier_line}"
        except Exception: pass
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy More", callback_data="shop")],
        [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
    ])
    # First: send the receipt header (Markdown)
    await _bot_send_smart(bot, order['user_id'], text, parse_mode="Markdown")
    # 🆕 v72 BUG FIX: Then send the delivery content in its NATIVE format
    # (HTML if our template rendered it with [[HTML]] sentinel, plain text
    # if it's admin's static delivery_text). The premium_emoji_guard auto-
    # picks the right parse_mode based on [[HTML]] prefix. Content is
    # byte-perfect preserved (inside <code> blocks for HTML mode).
    await _bot_send_smart(bot, order['user_id'], delivery, parse_mode=None,
                          reply_markup=kb)
    return True


async def _send_product_success_or_queue(bot, order, paid_amount):
    """Backward-compatible wrapper for the central product fulfillment router."""
    return await fulfill_paid_product_order(bot, order, paid_amount, payment_method_label=(order.get('payment_method') or 'Payment'))


async def _complete_binance_note_order(context, order, result):
    """Mark a Binance note order paid and deliver points/product exactly once."""
    oid = order['id']
    fresh = get_order(oid)
    if not fresh or fresh['status'] != 'binance_waiting':
        return
    from database import mark_binance_email_used, update_order_txid
    paid_amount = float(result.get('amount') or fresh['price'] or 0)
    email_hash = result.get('email_hash', '')
    txid = result.get('txid', '')
    if not email_hash:
        email_hash = f"binance-note:{fresh.get('payment_note_id') or oid}:{txid or oid}"
    mark_binance_email_used(email_hash, oid, fresh.get('payment_note_id') or '', paid_amount, txid, fresh['user_id'])
    if txid:
        update_order_txid(oid, txid)
    if (fresh['order_type'] == 'points') or (not fresh['product_id'] and 'Points' in (fresh['product_name'] or '')):
        await _send_deposit_success(context.bot, fresh, paid_amount)
    else:
        await _send_product_success_or_queue(context.bot, fresh, paid_amount)


async def _complete_binance_name_amount_order(context, order, result, sender_name, expected_amount):
    """Complete Binance name+amount verified order via central routers."""
    if not order:
        return
    oid = order['id']
    fresh = get_order(oid)
    if not fresh or fresh['status'] == 'delivered':
        return
    from database import mark_binance_email_used, update_order_txid
    paid_amount = float(result.get('amount') or expected_amount or fresh['price'] or 0)
    email_hash = result.get('email_hash', '') or ''
    txid = result.get('txid', '') or ''
    if not email_hash:
        email_hash = f"binance-name-amount:{oid}:{txid or sender_name}:{paid_amount}"
    mark_binance_email_used(email_hash, oid, sender_name, paid_amount, txid, fresh['user_id'])
    if txid:
        update_order_txid(oid, txid)

    is_points = ((fresh['order_type'] if 'order_type' in fresh.keys() and fresh['order_type'] else 'product') == 'points' or
                 (not fresh['product_id'] and 'Points' in (fresh['product_name'] or '')))
    if is_points:
        await _send_deposit_success(context.bot, fresh, paid_amount)
    else:
        await fulfill_paid_product_order(context.bot, fresh, paid_amount, payment_method_label='Binance')


async def binance_note_background_job(context):
    """Background auto-check for Binance orders with Transfer Note IDs.
    🆕 v64: Only process orders older than 30 seconds, to give the foreground
    verify call a head start and avoid race-condition duplicate messages.
    """
    try:
        orders = get_pending_binance_note_orders(limit=25)
    except Exception as e:
        logging.getLogger(__name__).error(f"[BinanceNote] DB pending fetch failed: {e}")
        return
    if not orders:
        return
    # 🆕 v64: skip very-recent orders (foreground is still processing them)
    import datetime as _dt
    now = _dt.datetime.utcnow()
    filtered = []
    for o in orders:
        try:
            created = o.get('created_at') or ''
            if not created:
                filtered.append(o); continue
            # created_at is "YYYY-MM-DD HH:MM:SS" — try ISO parse
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
                try:
                    ts = _dt.datetime.strptime(created, fmt)
                    age = (now - ts).total_seconds()
                    if age >= 30:
                        filtered.append(o)
                    break
                except Exception:
                    continue
            else:
                filtered.append(o)
        except Exception:
            filtered.append(o)
    orders = filtered
    if not orders:
        return
    # v61/v62: try Binance Pay API first (with proxy), then fall back to Gmail IMAP.
    # payment_note_id may hold either a generated transfer-note (legacy) or the
    # user-supplied Binance Order ID (v62 Order-ID flow). We try BOTH match modes.
    from database import get_setting
    use_api = (get_setting("binance_api_enabled", "0") == "1")
    if use_api:
        from payments import verify_payment_unified
    else:
        from payments import (
            verify_binance_payment_by_note,
            verify_binance_payment_by_order_id,
        )
    for order in orders:
        try:
            note_id = (order.get('payment_note_id') or '').strip()
            if not note_id:
                continue
            expected = float(order['price'] or order.get('binance_amount') or 0)
            if use_api:
                # API path — try as order_id first (more common in v62 flow), then as note
                result = await asyncio.to_thread(
                    verify_payment_unified,
                    expected_amount=expected, order_id=note_id, use_email_fallback=True,
                )
                if not result.get('success'):
                    result = await asyncio.to_thread(
                        verify_payment_unified,
                        expected_amount=expected, note_id=note_id, use_email_fallback=True,
                    )
                # 🐛 v147: customer typed a wrong Order ID → rescue by
                # amount + fuzzy customer-name (real payment observed live).
                if not result.get('success'):
                    _uname = str(order.get('user_name') or '').strip()
                    if _uname:
                        result = await asyncio.to_thread(
                            verify_payment_unified,
                            expected_amount=expected, sender_name=_uname,
                            use_email_fallback=True,
                        )
            else:
                # Email path — try note-id match, fall back to order-id body match
                result = await asyncio.to_thread(verify_binance_payment_by_note, note_id, expected)
                if not result.get('success'):
                    result = await asyncio.to_thread(
                        verify_binance_payment_by_order_id, note_id, expected,
                    )
            if result.get('success'):
                await _complete_binance_note_order(context, order, result)
        except Exception as e:
            logging.getLogger(__name__).error(f"[BinanceNote] order {order.get('id') if order else '?'} failed: {e}")


async def payment_binance_callback(update, context):
    """🔶 Product Binance Pay → Order-ID flow (when API toggle ON) or legacy sender-name flow."""
    q = update.callback_query; await q.answer()
    # 🆕 v80: guard against disabled payment method
    from database import is_payment_enabled, get_payment_disable_msg
    if not is_payment_enabled("binance"):
        await _safe_send(q, context, get_payment_disable_msg("binance"),
                          reply_markup=back_btn()); return
    parts = q.data.split("_")
    pid = int(parts[2])
    qty = int(parts[3]) if len(parts) > 3 else 1
    p = get_product(pid)
    if not p:
        await _safe_send(q, context, "❌ Product not found!", reply_markup=back_btn()); return
    if p['stock'] < qty:
        await _safe_send(q, context, f"❌ Only {p['stock']} in stock!", reply_markup=back_btn()); return

    # Clear old state
    for k in ['binance_step','binance_amount','binance_txid','binance_name','binance_order_id',
              'ep_step','ep_amount','ep_tid','jc_step','jc_amount','jc_tid',
              'pending_order_id']:
        context.user_data.pop(k, None)

    context.user_data['binance_product_id'] = pid
    context.user_data['binance_qty'] = qty
    context.user_data['points_mode'] = False
    total = round(_get_price_for_qty(p, qty) * qty, 2)
    context.user_data['binance_amount'] = total

    # 🆕 v62: Route to Order-ID flow when admin has enabled API mode
    if get_setting("binance_api_enabled", "0") == "1":
        await _start_binance_order_id_flow(
            update, context,
            is_points=False, product=p, qty=qty, amount=total,
        )
        return

    # ── Legacy sender-name flow (API mode OFF) ──
    context.user_data['binance_step'] = 'waiting_name'
    qty_text = f" × {qty}" if qty > 1 else ""
    bid = get_setting("binance_id", BINANCE_PAY_ID)
    bn_holder = get_setting("binance_name", get_setting("account_name", ACCOUNT_NAME))

    await _safe_send(q, context,
        f"🔶 *Binance Payment*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *{_fmt_msg_name(p['name'])}*{qty_text}\n"
        f"💰 *Total: {fmt_price(total)}*\n\n"
        f"📋 *Send {fmt_price(total)} to:*\n"
        f"• Binance Pay ID: `{bid}`\n"
        f"• Account Name: *{escape_md(bn_holder)}*\n\n"
        f"✅ *Step 1/2:* Enter your *Binance sender name* below.\n"
        f"Example: `John Doe`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))


async def binance_name_received(update, context):
    """🔶 Step 1: User enters their Binance sender name → now ask for amount"""
    if context.user_data.get('binance_step') != 'waiting_name':
        return False
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text(
            "❌ Name too short! Enter your Binance sender name.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
        return True
    if len(name) > 60:
        await update.message.reply_text(
            "❌ Name too long! Max 60 characters.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
        return True
    
    context.user_data['binance_name'] = name
    context.user_data['binance_step'] = 'waiting_amount'
    
    pid = context.user_data.get('binance_product_id')
    is_points = context.user_data.get('points_mode', False)
    
    if is_points:
        total = context.user_data.get('points_amount', 0)
    else:
        p = get_product(pid) if pid else None
        qty = context.user_data.get('binance_qty', 1)
        total = (_get_price_for_qty(p, qty) * qty) if p else 0
    
    await update.message.reply_text(
        f"✅ Name: *{escape_md(name)}*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 *Step 2/2:* Enter the *exact USD amount* you sent:\n"
        f"_(e.g. `{total}` or `${total}`)_\n\n"
        f"Your payment will be processed after submission.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
    return True


async def binance_amount_received(update, context):
    """🔶 Step 2: User enters amount → Create order → Check Gmail → Auto-verify"""
    if context.user_data.get('binance_step') != 'waiting_amount':
        return False
    txt = update.message.text.strip().replace('$','').replace(',','').strip()
    m = re.search(r'(\d+\.?\d*)', txt)
    if not m:
        await update.message.reply_text(
            "❌ Enter a number! e.g. `5` or `$5`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
        return True
    amt = float(m.group(1))
    if amt <= 0:
        await update.message.reply_text("❌ Amount must be > 0!")
        return True

    sender_name = context.user_data.get('binance_name', '')
    
    # Create the pending order RIGHT NOW — but ONLY after validating the
    # amount against the real product/points price. Never trust user-entered
    # amount text for product delivery.
    u = update.effective_user
    un = u.first_name or str(u.id)
    is_points = context.user_data.get('points_mode', False)
    pid = context.user_data.get('binance_product_id')
    expected_amount = 0.0

    if is_points:
        expected_amount = float(context.user_data.get('points_amount') or context.user_data.get('binance_amount') or 0)
        if expected_amount <= 0 or not _amounts_match(amt, expected_amount):
            await update.message.reply_text(
                f"❌ *Wrong amount!*\n\n"
                f"Expected: `${expected_amount:.2f}`\n"
                f"You entered: `${amt:.2f}`\n\n"
                f"Please enter the exact amount you selected.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
            return True
        amt = expected_amount
        pts = points_from_usd(expected_amount)
        pts_txt = fmt_points(pts)
        oid = create_order(u.id, un, 0, f"💎 {pts_txt} Points", expected_amount, 'binance', sender_name, expected_amount, 'USDT', 'points')
        pname = f"💎 {pts_txt} Points"
    else:
        p = get_product(pid)
        if not p:
            await update.message.reply_text("❌ Product not found.", reply_markup=back_btn())
            for k in ['binance_step','binance_amount','binance_product_id','binance_qty','points_mode','binance_name']:
                context.user_data.pop(k, None)
            return True
        qty = int(context.user_data.get('binance_qty', 1) or 1)
        if p['stock'] < qty:
            await update.message.reply_text(f"❌ Only {p['stock']} in stock!", reply_markup=back_btn())
            for k in ['binance_step','binance_amount','binance_product_id','binance_qty','points_mode','binance_name']:
                context.user_data.pop(k, None)
            return True
        pname = p['name'] if qty == 1 else f"{p['name']} × {qty}"
        order_total = round(_get_price_for_qty(p, qty) * qty, 2)
        expected_amount = order_total
        if not _amounts_match(amt, expected_amount):
            await update.message.reply_text(
                f"❌ *Wrong amount!*\n\n"
                f"Product total: `${expected_amount:.2f}`\n"
                f"You entered: `${amt:.2f}`\n\n"
                f"Please send and enter the exact product total shown above.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
            return True
        amt = expected_amount
        creds = context.user_data.pop('order_creds', '')
        oid = create_order(u.id, un, p['id'], pname, order_total, 'binance', sender_name, expected_amount, 'USDT', 'product', creds, qty=qty)
        context.user_data['order_qty'] = qty

    update_order_status(oid, 'binance_waiting')
    context.user_data['binance_amount'] = expected_amount
    context.user_data['pending_order_id'] = oid
    
    # Show "checking..." message
    checking_msg = await update.message.reply_text(
        f"⏳ *Processing payment...*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Sender: *{escape_md(sender_name)}*\n"
        f"💵 Amount: *${amt}*\n\n"
        f"_Please wait a few seconds._",
        parse_mode="Markdown")

    # 🤖 v61: AUTO-VERIFY — API first (if enabled), else Gmail
    from database import get_setting as _gs61
    if _gs61("binance_api_enabled", "0") == "1":
        from payments import verify_payment_unified
        result = verify_payment_unified(
            expected_amount=amt, sender_name=sender_name,
            use_email_fallback=True,
        )
    else:
        from payments import verify_binance_payment
        result = verify_binance_payment(sender_name, amt)
    
    if result['success']:
        try:
            await checking_msg.delete()
        except Exception:
            pass
        await _complete_binance_name_amount_order(context, get_order(oid), result, sender_name, expected_amount)
        for k in ['binance_step','binance_amount','binance_product_id','binance_qty',
                  'points_mode','pending_order_id','binance_name','points_amount','order_qty']:
            context.user_data.pop(k, None)
        return True

    # ── NOT FOUND YAY ──
    # Delete checking message, show "waiting" status
    try: await checking_msg.delete()
    except: pass
    
    status = result.get('status', 'not_found')
    reason = result.get('reason', '')
    
    if status == 'already_used':
        # This exact payment was already verified before
        update_order_status(oid, 'rejected')
        await update.message.reply_text(
            f"❌ *Payment Already Used!*\n━━━━━━━━━━━━━━━━━━━━\n\n{reason}\n\n"
            f"Order #{oid} rejected.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]))
        for k in ['binance_step','binance_amount','binance_product_id','binance_qty',
                  'points_mode','pending_order_id','binance_name','points_amount']:
            context.user_data.pop(k, None)
        return True
    
    # Payment not found yet — keep order pending, show retry button
    context.user_data['binance_step'] = 'awaiting_verify'
    
    bid = get_setting("binance_id", BINANCE_PAY_ID)
    bn_holder = get_setting("binance_name", get_setting("account_name", ACCOUNT_NAME))
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Check Again", callback_data=f"vpay_{oid}")],
        [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="st_new")],
        [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
    ])
    msg = (
        f"⏳ *Order #{oid} — Waiting for Payment*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 *{_fmt_msg_name(pname)}*\n"
        f"💰 Amount: *${amt}*\n"
        f"👤 Sender: *{escape_md(sender_name)}*\n\n"
        f"📋 *Make sure you sent ${amt} to:*\n"
        f"  Binance Pay ID: `{bid}`\n"
        f"  Holder: {escape_md(bn_holder)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Payment is not confirmed yet. It may take a few minutes.\n\n"
        f"*Tap 'Check Again' after sending payment.*"
    )
    send_text, send_mode = smart_text_and_mode(msg, "Markdown")
    await update.message.reply_text(send_text, parse_mode=send_mode, reply_markup=kb)
    
    # Notify admin (🐛 v145: enriched)
    try:
        ctx_lines = order_payment_context(oid)
        ctx_txt = "\n".join(ctx_lines) + ("\n" if ctx_lines else "")
        await context.bot.send_message(
            ADMIN_ID,
            f"🔶 *Binance (Gmail) Pending #{oid}*\n"
            f"User: {escape_md(un)} (`{u.id}`)\n"
            f"Method: 🪙 Binance Pay (Gmail auto-verify)\n"
            f"{ctx_txt}"
            f"Amount: ${amt} | Sender: {escape_md(sender_name)}\n"
            f"_Waiting for payment confirmation..._",
            parse_mode="Markdown")
    except: pass

    return True



# ════════════════════════════════════════════
# ✅ VERIFY BINANCE PAYMENT (Binance API)
# ════════════════════════════════════════════
async def handle_binance_screenshot(update, context):
    """📸 Legacy: User uploaded screenshot → redirect to Gmail verify flow.
    Screenshot-based verification is no longer used for Binance."""
    if context.user_data.get('binance_step') != 'waiting_screenshot':
        return False
    
    # Redirect user to enter name instead
    context.user_data['binance_step'] = 'waiting_name'
    await update.message.reply_text(
        "📸 *Screenshot upload is no longer needed!*\n\n"
        "Please follow the Binance payment instructions.\n\n"
        "✅ *Step 1/2:* Apna *Binance sender name* likhein:\n"
        "_(The name used for the payment)_\n\n"
        "💡 _Example: `John Doe` ya `Ali Khan`_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
    return True


async def reupload_screenshot_callback(update, context):
    """📸 Legacy callback — redirect to Gmail verify (check again)"""
    q = update.callback_query
    await q.answer()
    # Try to get the order ID from context
    oid = context.user_data.get('pending_order_id')
    if oid:
        # Redirect to check again
        q.data = f"vpay_{oid}"
        await verify_screenshot_callback(update, context)
    else:
        await q.edit_message_text(
            "❌ No pending order found. Please start a new order.",
            reply_markup=back_btn())


async def verify_screenshot_callback(update, context):
    """🔶 User tapped 'Check Again' button → re-check Gmail for matching Binance email"""
    q = update.callback_query
    user_id = q.from_user.id

    try:
        oid = int(q.data.replace("vpay_", ""))
    except ValueError:
        await q.answer("Invalid order", show_alert=True)
        return

    # ⏱️ Cooldown check
    remaining = _get_remaining_cooldown(user_id, oid)
    if remaining > 0:
        await q.answer(
            f"⏱️ Wait {remaining} seconds before checking again.",
            show_alert=True
        )
        return

    await q.answer("⏳ Processing payment...", show_alert=False)

    o = get_order(oid)
    if not o:
        await q.edit_message_text("❌ Order not found.", reply_markup=back_btn())
        return
    if o['status'] == 'delivered':
        await q.edit_message_text(
            "✅ *Already Verified!*\n\nOrder already delivered. Check your account!",
            parse_mode="Markdown", reply_markup=back_btn())
        return

    # Set cooldown
    _set_cooldown(user_id, oid)

    # Get saved sender name + amount from order
    sender_name = o['binance_sender_name'] or context.user_data.get('binance_name', '')
    expected_amount = _expected_binance_order_amount(o)
    
    if not sender_name:
        await q.edit_message_text(
            "❌ No sender name found for this order.\nPlease start a new order.",
            reply_markup=back_btn())
        return

    # Show verifying message
    try:
        await q.edit_message_text(
            f"⏳ *Processing payment...*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Order #{oid} | Amount: ${expected_amount}\n"
            f"Sender: {escape_md(sender_name)}\n\n"
            f"_Please wait a few seconds._",
            parse_mode="Markdown")
    except: pass

    # 🤖 v61: API first (if enabled), then Gmail fallback
    from database import get_setting as _gs61
    if _gs61("binance_api_enabled", "0") == "1":
        from payments import verify_payment_unified
        result = verify_payment_unified(
            expected_amount=expected_amount, sender_name=sender_name,
            use_email_fallback=True,
        )
    else:
        from payments import verify_binance_payment
        result = verify_binance_payment(sender_name, expected_amount)

    if result['success']:
        await _complete_binance_name_amount_order(context, o, result, sender_name, expected_amount)
        for k in ['binance_step','binance_amount','binance_product_id','binance_qty',
                  'points_mode','pending_order_id','screenshot_file_id','binance_name','points_amount','order_qty']:
            context.user_data.pop(k, None)
        return

    # ── FAILED — show error with retry ──
    status = result.get('status', 'not_found')
    reason = result.get('reason', 'Payment not found yet.')
    
    cooldown = _get_remaining_cooldown(user_id, oid)
    btn_label = _verify_button_label(cooldown)
    
    if status == 'already_used':
        update_order_status(oid, 'rejected')
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
        await q.edit_message_text(
            f"❌ *Payment Already Used!*\n━━━━━━━━━━━━━━━━━━━━\n\n{reason}\n\nOrder rejected.",
            parse_mode="Markdown", reply_markup=kb)
        for k in ['binance_step','binance_amount','binance_product_id','binance_qty',
                  'points_mode','pending_order_id','screenshot_file_id','binance_name']:
            context.user_data.pop(k, None)
        return

    # Not found yet — show retry
    bid = get_setting("binance_id", BINANCE_PAY_ID)
    bn_holder = get_setting("binance_name", get_setting("account_name", ACCOUNT_NAME))
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(btn_label, callback_data=f"vpay_{oid}")],
        [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="st_new")],
        [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
    ])
    await q.edit_message_text(
        f"⏳ *Payment Not Found Yet*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Order #{oid} | Amount: ${expected_amount}\n"
        f"Sender: {escape_md(sender_name)}\n\n"
        f"📋 Make sure you sent to:\n"
        f"  Binance Pay ID: `{bid}`\n"
        f"  Holder: {escape_md(bn_holder)}\n\n"
        f"Payment is not confirmed yet. Please wait 2 minutes and tap *Check Again*.\n"
        f"If it is not confirmed within 15 minutes, create a support ticket.",
        parse_mode="Markdown", reply_markup=kb)



async def payment_jazzcash_callback(update, context):
    """📱 JazzCash → manual screenshot flow"""
    # 🆕 v80: guard against disabled payment method
    from database import is_payment_enabled, get_payment_disable_msg
    if not is_payment_enabled("jazzcash"):
        q = update.callback_query
        await q.answer()
        await _safe_send(q, context, get_payment_disable_msg("jazzcash"),
                          reply_markup=back_btn()); return
    await _start_jc_manual(update, context)


async def payment_easypaisa_callback(update, context):
    """📱 EasyPaisa product purchase → start EP flow"""
    # 🆕 v80: guard against disabled payment method
    from database import is_payment_enabled, get_payment_disable_msg
    if not is_payment_enabled("easypaisa"):
        q = update.callback_query
        await q.answer()
        await _safe_send(q, context, get_payment_disable_msg("easypaisa"),
                          reply_markup=back_btn()); return
    await _start_ep_flow(update, context, is_points=False)


async def _start_ep_flow(update, context, is_points=False):
    """🆕 v31: Start EasyPaisa flow → asks ONLY for TID (bot reads amount+name from email)"""
    q = update.callback_query; await q.answer()
    parts = q.data.split("_")
    pid = int(parts[2])
    qty = int(parts[3]) if len(parts) > 3 else 1
    p = get_product(pid)
    if not p: await q.edit_message_text("❌!"); return
    if p['stock'] < qty:
        await q.edit_message_text(f"❌ Only {p['stock']} in stock!", reply_markup=back_btn()); return

    # Clear old state
    for k in ['ep_step','ep_amount','ep_tid','binance_step','binance_amount']:
        context.user_data.pop(k, None)

    # Create pending order RIGHT NOW
    u = q.from_user
    un = u.first_name or str(u.id)
    pname = p['name'] if qty == 1 else f"{p['name']} × {qty}"
    total_usd = _get_price_for_qty(p, qty) * qty
    total_rs = total_usd * _pkr_rate()

    creds = context.user_data.pop('order_creds', '')
    oid = create_order(u.id, un, p['id'], pname, total_usd, 'easypaisa', '', total_rs, 'PKR', 'product', creds, qty=qty)
    update_order_status(oid, 'screenshot_sent')

    context.user_data['ep_product_id'] = pid
    context.user_data['ep_qty'] = qty
    context.user_data['ep_step'] = 'waiting_tid'
    context.user_data['ep_points_mode'] = False
    context.user_data['ep_expected_rs'] = total_rs
    context.user_data['pending_order_id'] = oid
    context.user_data['order_qty'] = qty

    legacy_name = get_setting("account_name", ACCOUNT_NAME)
    num = get_setting("easypaisa", EASYPAISA_NUMBER)
    an = get_setting("easypaisa_name", legacy_name)
    pkr = format_pkr(total_usd, _pkr_rate())
    qty_text = f" × {qty}" if qty > 1 else ""

    await _safe_send(q, context,
        f"📱 *Order #{oid} — EasyPaisa Payment*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *{_fmt_msg_name(p['name'])}*{qty_text}\n"
        f"💰 Amount: *${total_usd:.2f}* ≈ *{pkr}*\n\n"
        f"📲 *Send Rs.{total_rs:.0f} to:*\n"
        f"  Number: `{num}`\n"
        f"  Name: {escape_md(an)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 *Instructions:*\n"
        f"1. Send the exact amount to Easypaisa account above 💳\n"
        f"2. EasyPaisa will send you SMS with Trx ID\n"
        f"3. Enter only the *Transaction ID* below.\n\n"
        f"🔢 *Enter your Transaction ID (10-13 digits):*\n"
        f"_(Find it in the EasyPaisa SMS)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))


async def _start_jc_manual(update, context):
    """🆕 v40.2: JazzCash → Auto-verify via TID (same as EasyPaisa).
    User just enters TID, bot verifies in the background — no screenshot."""
    q = update.callback_query; await q.answer()
    parts = q.data.split("_")
    pid = int(parts[2])
    qty = int(parts[3]) if len(parts) > 3 else 1
    p = get_product(pid)
    if not p: await q.edit_message_text("❌!"); return
    if p['stock'] < qty:
        await q.edit_message_text(f"❌ Only {p['stock']} in stock!", reply_markup=back_btn()); return

    # Clear old state
    for k in ['ep_step','ep_amount','ep_tid','binance_step','binance_amount','jc_step','jc_amount','jc_tid']:
        context.user_data.pop(k, None)

    u = q.from_user
    un = u.first_name or str(u.id)
    pname = p['name'] if qty == 1 else f"{p['name']} × {qty}"
    total_usd = _get_price_for_qty(p, qty) * qty
    total_rs = total_usd * _pkr_rate()

    # Create pending order RIGHT NOW
    creds = context.user_data.pop('order_creds', '')
    oid = create_order(u.id, un, p['id'], pname, total_usd, 'jazzcash', '', total_rs, 'PKR', 'product', creds, qty=qty)
    update_order_status(oid, 'screenshot_sent')

    context.user_data['jc_product_id'] = pid
    context.user_data['jc_qty'] = qty
    context.user_data['jc_step'] = 'waiting_tid'
    context.user_data['jc_points_mode'] = False
    context.user_data['jc_expected_rs'] = total_rs
    context.user_data['pending_order_id'] = oid
    context.user_data['order_qty'] = qty

    legacy_name = get_setting("account_name", ACCOUNT_NAME)
    num = get_setting("jazzcash", JAZZCASH_NUMBER)
    an = get_setting("jazzcash_name", legacy_name)
    pkr = format_pkr(total_usd, _pkr_rate())
    qty_text = f" × {qty}" if qty > 1 else ""

    await _safe_send(q, context,
        f"📱 *Order #{oid} — JazzCash Payment*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *{_fmt_msg_name(p['name'])}*{qty_text}\n"
        f"💰 Amount: *${total_usd:.2f}* ≈ *{pkr}*\n\n"
        f"📲 *Send Rs.{total_rs:.0f} to:*\n"
        f"  Number: `{num}`\n"
        f"  Name: {escape_md(an)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 *Instructions:*\n"
        f"1. Send the exact amount via JazzCash to the number above\n"
        f"2. JazzCash will send you an SMS with the Transaction ID\n"
        f"3. Enter only the *Transaction ID* below.\n\n"
        f"🔢 *Enter your Transaction ID (10-15 digits):*\n"
        f"_(Find it in the JazzCash SMS)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
    try:
        ctx_lines = order_payment_context(oid)
        ctx_txt = "\n".join(ctx_lines) + ("\n" if ctx_lines else "")
        await _bot_send_smart(context.bot, ADMIN_ID,
            f"📞 *JazzCash Pending #{oid}*\n"
            f"User: {escape_md(un)} (`{u.id}`)\n"
            f"Method: 📞 JazzCash\n"
            f"{ctx_txt}"
            f"Amount: Rs.{total_rs:.0f}\n"
            f"_Waiting for TID..._",
            parse_mode="Markdown")
    except: pass


# ── EP flow steps ──
async def ep_amount_received(update, context):
    """🆕 v31: No longer used — kept for backward compat. Just no-op."""
    return False


# ════════════════════════════════════════════
# 💎 EP/JC BUY POINTS — INSTANT TXID PROCESSING
# ════════════════════════════════════════════
def _points_from_order_name(order):
    try:
        m = re.search(r'(\d+(?:\.\d+)?)', order['product_name'] or '')
        return float(m.group(1)) if m else points_from_usd(float(order['price'] or 0))
    except Exception:
        return 0


def _is_points_order(order):
    try:
        return ((order['order_type'] if 'order_type' in order.keys() and order['order_type'] else 'product') == 'points'
                or (not order['product_id'] and 'Points' in (order['product_name'] or '')))
    except Exception:
        return False


async def _send_or_edit(target, text, **kwargs):
    """Send for Message update, edit for CallbackQuery."""
    try:
        if hasattr(target, 'edit_message_text'):
            await target.edit_message_text(text, **kwargs)
        elif hasattr(target, 'message') and target.message:
            await target.message.reply_text(text, **kwargs)
    except Exception as e:
        if "parse" in str(e).lower() and 'parse_mode' in kwargs:
            kwargs.pop('parse_mode', None)
            if hasattr(target, 'edit_message_text'):
                await target.edit_message_text(text, **kwargs)
            elif hasattr(target, 'message') and target.message:
                await target.message.reply_text(text, **kwargs)


def _check_again_kb(prefix, oid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Check Again", callback_data=f"{prefix}_{oid}")],
        [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="st_new")],
        [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
    ])


def _deposit_success_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 My Account", callback_data="my_account")],
        [InlineKeyboardButton("💎 Buy More Points", callback_data="buy_points")],
    ])


async def _process_points_tid_payment(target, context, oid, *, platform, callback_prefix):
    """Process Buy Points TID immediately; show success or Check Again."""
    o = get_order(oid)
    if not o:
        await _send_or_edit(target, "❌ Order not found.", reply_markup=back_btn())
        return
    if o['status'] == 'delivered':
        await _send_or_edit(target, "✅ *Already Confirmed!*\n\nYour points have already been added.", parse_mode="Markdown", reply_markup=_deposit_success_kb())
        return
    if not _is_points_order(o):
        # Product order flow will be handled in Step 2; keep old manual button behavior for now.
        return None

    tid = o['binance_txid'] if 'binance_txid' in o.keys() else ''
    expected_rs = float(o['binance_amount'] or 0)
    if not tid:
        await _send_or_edit(target, "❌ Transaction ID not found. Please send it again.", reply_markup=back_btn())
        return

    await _send_or_edit(target,
        f"⏳ *Processing Payment...*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Order ID: `#{oid}`\n"
        f"Transaction ID: `{tid}`\n\n"
        f"Please wait a few seconds.",
        parse_mode="Markdown")

    if platform == 'easypaisa':
        from payments import easypaisa_verify_by_tid_only as _verify_tid
    else:
        from payments import jazzcash_verify_by_tid_only as _verify_tid

    api_result = await asyncio.to_thread(_verify_tid, tid)
    result = {'success': False, 'status': api_result.get('status', 'error'),
              'reason': api_result.get('reason', ''), 'amount': api_result.get('amount', 0),
              'name': api_result.get('name', '')}

    if api_result.get('success'):
        actual_rs = float(api_result.get('amount', 0) or 0)
        if abs(actual_rs - expected_rs) > 5:
            result['status'] = 'amount_mismatch'
            result['reason'] = f"Expected Rs.{expected_rs:.0f}, received Rs.{actual_rs:.0f}."
        elif api_result.get('type', '') == 'sent':
            result['status'] = 'wrong_direction'
            result['reason'] = "Invalid transaction direction."
        else:
            result['success'] = True
            result['status'] = 'matched'

    if result.get('success'):
        from database import mark_txid_used
        actual_rs = float(result.get('amount', expected_rs) or expected_rs)
        pts = _points_from_order_name(o)
        mark_txid_used(tid, o['user_id'], oid, actual_rs, 'PKR')
        if pts > 0:
            add_points(o['user_id'], pts, tx_type='deposit', description='Points deposit', event_id=f"points_order_{oid}", order_id=oid)
        update_order_status(oid, 'delivered')
        total_pts = get_user_points(o['user_id'])
        text = (
            f"🎉 *Deposit Successful!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Your payment has been confirmed.\n"
            f"💎 Points Added: *{fmt_points(pts)}*\n"
            f"💰 Amount: *Rs.{actual_rs:.0f}*\n"
            f"🧾 Order ID: `#{oid}`\n"
            f"🔢 Transaction ID: `{tid}`\n\n"
            f"📊 New Points Balance: *{fmt_points(total_pts)}*\n\n"
            f"Thank you for your deposit!"
        )
        # clear state
        for k in ['ep_step','ep_amount','ep_tid','ep_product_id','ep_qty','ep_points_mode','ep_points_usd','ep_expected_rs',
                  'jc_step','jc_amount','jc_tid','jc_product_id','jc_qty','jc_points_mode','jc_expected_rs','pending_order_id']:
            context.user_data.pop(k, None)
        await _send_or_edit(target, text, parse_mode="Markdown", reply_markup=_deposit_success_kb())
        return

    # Not confirmed yet / mismatch / pending
    if result.get('status') == 'amount_mismatch':
        main_line = "The received amount does not match this order."
        detail = f"Expected: *Rs.{expected_rs:.0f}*"
    elif result.get('status') == 'wrong_direction':
        main_line = "This Transaction ID is not valid for this deposit."
        detail = "Please send the Transaction ID from your payment message."
    else:
        main_line = "Payment is not confirmed yet."
        detail = "Please wait 2 minutes and tap *Check Again*. If it is not confirmed within 15 minutes, create a support ticket."

    text = (
        f"⏳ *Payment Pending*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{main_line}\n\n"
        f"Order ID: `#{oid}`\n"
        f"Transaction ID: `{tid}`\n"
        f"{detail}"
    )
    await _send_or_edit(target, text, parse_mode="Markdown", reply_markup=_check_again_kb(callback_prefix, oid))
    return


async def ep_tid_received(update, context):
    """🆕 v31: User enters TID → save + show Verify Payment button.
    Submit the Transaction ID from your payment message."""
    if context.user_data.get('ep_step') != 'waiting_tid':
        return False
    tid = update.message.text.strip()
    digits_only = re.sub(r'\D', '', tid)
    # Accept 10-13 digit TIDs (some EasyPaisa formats vary)
    if not (10 <= len(digits_only) <= 13):
        await update.message.reply_text(
            f"❌ Trx ID must be *10-13 digits*!\nYou entered: {len(digits_only)} digits\n_Check EasyPaisa SMS._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
        return True

    # Anti-fraud check
    from database import is_txid_used, get_txid_record, update_order_txid
    if is_txid_used(digits_only):
        rec = get_txid_record(digits_only)
        await update.message.reply_text(
            f"❌ *This Trx ID is already used!*\n\nEach transaction can be used ONCE.\n\n"
            f"_Already used at: {rec['verified_at'][:16] if rec else 'unknown'}_",
            parse_mode="Markdown", reply_markup=back_btn())
        for k in ['ep_step','ep_amount','ep_tid','ep_product_id','ep_qty','ep_points_mode','ep_points_usd','pending_order_id']:
            context.user_data.pop(k, None)
        return True

    # Save TID to order
    oid = context.user_data.get('pending_order_id')
    if oid:
        update_order_txid(oid, digits_only)

    context.user_data['ep_tid'] = digits_only
    context.user_data['ep_step'] = 'awaiting_verify'

    expected_rs = context.user_data.get('ep_expected_rs', 0)

    # Buy Points: process immediately after TXID. Product order flow remains for Step 2.
    if context.user_data.get('ep_points_mode'):
        await _process_points_tid_payment(update, context, oid, platform='easypaisa', callback_prefix='epv')
        return True

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Check Again", callback_data=f"epv_{oid}")],
        [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
    ])
    await update.message.reply_text(
        f"🔢 *Transaction ID Received:* `{digits_only}` ✅\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 Order #{oid}\n"
        f"💰 Expected: *Rs.{expected_rs:.0f}*\n\n"
        f"⏳ Your payment is being processed. Tap *Check Again* after 2 minutes.",
        parse_mode="Markdown", reply_markup=kb)

    # Notify admin
    try:
        u = update.effective_user
        await context.bot.send_message(
            ADMIN_ID,
            f"📱 *New EP Order #{oid}*\n"
            f"User: {escape_md(u.first_name or 'N/A')} (`{u.id}`)\n"
            f"TID: `{digits_only}`\n"
            f"Expected: Rs.{expected_rs:.0f}",
            parse_mode="Markdown")
    except: pass
    return True


async def ep_name_received(update, context):
    """🆕 v31: No longer needed — kept for backward compat."""
    return False



async def ep_verify_callback(update, context):
    """User taps Verify for EasyPaisa order — calls Gmail IMAP (with 20s cooldown)"""
    q = update.callback_query
    user_id = q.from_user.id
    try:
        oid = int(q.data.replace("epv_", ""))
    except ValueError:
        await q.answer("Invalid order", show_alert=True)
        return

    # ⏱️ COOLDOWN CHECK
    remaining = _get_remaining_cooldown(user_id, oid)
    if remaining > 0:
        await q.answer(
            f"⏱️ Please wait {remaining} seconds before checking again.",
            show_alert=True
        )
        return

    await q.answer("⏳ Processing payment...", show_alert=False)
    o = get_order(oid)
    if not o:
        await q.edit_message_text("❌ Order not found.", reply_markup=back_btn())
        return
    if o['status'] == 'delivered':
        await q.edit_message_text(
            "✅ *Already Confirmed!*\n\nYour points/order has already been processed.",
            parse_mode="Markdown", reply_markup=back_btn())
        return

    if _is_points_order(o):
        _set_cooldown(user_id, oid)
        await _process_points_tid_payment(q, context, oid, platform='easypaisa', callback_prefix='epv')
        return

    # ⏱️ Set cooldown
    _set_cooldown(user_id, oid)

    tid = o['binance_txid'] if 'binance_txid' in o.keys() else ''
    amount_rs = o['binance_amount']
    # name = o['binance_sender_name'] if 'binance_sender_name' in o.keys() else ''  # 🧹 v39: unused

    if not tid:
        await q.edit_message_text("❌ No TID on order.", reply_markup=back_btn())
        return

    try:
        await _safe_send(q, context,
            f"⏳ *Processing payment...*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Order #{oid} | TID: `{tid}`\n\n_Please wait a few seconds..._",
            parse_mode="Markdown")
    except: pass

    # 🔧 v33 FIX: Call the EasyPaisa parser to get the result.
    from payments import easypaisa_verify_by_tid_only
    api_result = easypaisa_verify_by_tid_only(tid)
    expected_rs = amount_rs

    # Build unified result for handler below
    result = {'success': False, 'status': api_result.get('status', 'error'),
              'reason': api_result.get('reason', ''),
              'amount': api_result.get('amount', 0),
              'name': api_result.get('name', '')}

    # Amount validation if API found the email
    if api_result.get('success'):
        actual_rs = api_result.get('amount', 0)
        # Allow Rs.5 tolerance for amount match
        if abs(actual_rs - expected_rs) > 5:
            result['status'] = 'amount_mismatch'
            result['reason'] = (
                f"Amount mismatch!\n"
                f"Expected: Rs.{expected_rs:.0f}\n"
                f"Your payment: Rs.{actual_rs:.0f}\n\n"
                f"Please send the EXACT amount."
            )
        else:
            ptype = api_result.get('type', '')
            if ptype == 'sent':
                result['status'] = 'wrong_direction'
                result['reason'] = (
                    "This TID is for a payment YOU sent FROM bot's account.\n"
                    "We need a TID where YOU SENT TO our account.\n"
                    "Wrong TID?"
                )
            else:
                # SUCCESS!
                result['success'] = True
                result['status'] = 'matched'

    if result['success']:
        from database import mark_txid_used, decrease_stock, add_points
        actual_rs = result.get('amount', expected_rs)
        sender_name = result.get('name', '')
        mark_txid_used(tid, o['user_id'], oid, actual_rs, 'PKR')
        if not _is_points_order(o):
            await fulfill_paid_product_order(context.bot, o, actual_rs, payment_method_label='EasyPaisa')
            for k in ['ep_step','ep_amount','ep_tid','ep_product_id','ep_qty','ep_points_mode','ep_points_usd','ep_expected_rs','pending_order_id']:
                context.user_data.pop(k, None)
            return
        update_order_status(oid, 'delivered')

        is_points = ((o['order_type'] if 'order_type' in o.keys() and o['order_type'] else 'product') == 'points' or
                     (not o['product_id'] and 'Points' in (o['product_name'] or '')))
        if is_points:
            pts = _points_from_order_name(o)
            if pts > 0: add_points(o['user_id'], pts, tx_type='deposit', description='Points deposit', event_id=f"points_order_{oid}", order_id=oid)
            msg = (f"🎉 *Payment Verified!* ✅\n━━━━━━━━━━━━━━━━━━━━\n\n"
                   f"💎 *{fmt_points(pts)} Points* added to your account!\n\n"
                   f"💰 Amount: Rs.{actual_rs:.0f}\n👤 From: {sender_name}\n🔢 TID: `{tid}`\n\nThank you! 🙏")
        else:
            order_qty = 1
            qm = re.search(r'×\s*(\d+)$', o['product_name'] or '')
            if qm: order_qty = int(qm.group(1))
            
            p = get_product(o['product_id'])
            is_manual = (dict(p) if p else {}).get('delivery_mode') == 'manual'
            pts_bonus = points_from_usd(o['price'])
            
            if is_manual:
                req_type = (dict(p) if p else {}).get('req_account_type', 'none')
                if req_type == 'none':
                    update_order_status(oid, 'paid_pending_delivery')
                    msg = f"✅ Payment verified!\n\nYour order request has been sent to the store owner. In 1 to 3 hours, as soon as the owner is online, your order will be completed."
                    if (dict(p) if p else {}).get('delivery_text'):
                        msg += f"\n\n📝 *Instructions:*\n{p['delivery_text']}"
                    admin_msg = f"🔔 *New Order! (Readymade)*\nOrder #{oid}\nProduct: {p['name']}\n\nPlease deliver the account."
                    from config import ADMIN_ID
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton
                    try: await context.bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Upload Account", callback_data=f"adm_upacct_{oid}")]]))
                    except: pass
                else:
                    update_order_status(oid, 'waiting_for_details')
                    msg = f"✅ Payment verified!\n\nPlease provide the required details to process your order."
                    context.user_data['ownmail_oid'] = oid
                    context.user_data['ownmail_qty'] = order_qty
                    context.user_data['ownmail_step'] = 'email'
                    pt1 = 'Fresh Gmail' if req_type=='fresh_gmail' else ('Gmail' if req_type=='any_gmail' else 'Email Address')
                    prompt = f"📝 *Please enter your {pt1}*\n"
                    if order_qty > 1: prompt += "_(Send one per line)_"
                    try: await context.bot.send_message(o['user_id'] if (o is not None and 'user_id' in o.keys()) else u.id, prompt, parse_mode="Markdown")
                    except: pass
            else:
                # 🔧 AUDIT-FIX C1/C2 (2026-07-31): structured result — never mark
                # 'delivered' when the stock pool couldn't cover the full qty.
                from database import build_delivery_detailed
                _dres = build_delivery_detailed(o['product_id'], o['id'], order_qty, o['user_id'])
                delivery = _dres['text']
                # 🆕 v66: bonus 10pts removed
                # 🆕 v72: byte-perfect — receipt header (Markdown) + delivery
                # content (HTML, native format) sent as 2 separate messages so
                # neither parse mode mangles the other.
                if _dres['ok']:
                    update_order_status(oid, 'delivered')
                    msg = (f"🎉 *Order Delivered!* ✅\n━━━━━━━━━━━━━━━━━━━━\n\n"
                           f"📦 {escape_md(o['product_name'])}\n\n"
                           f"📨 *Your Product* — see the next message.\n\n"
                           f"Thank you! 🙏")
                    # Send the delivery content separately, with no parse_mode
                    # override so smart_text_and_mode picks HTML for [[HTML]] sentinel
                    try:
                        await context.bot.send_message(o['user_id'], delivery)
                    except Exception:
                        pass
                    # v121: Tier progress hint only. No extra points on payment success.
                    try:
                        from loyalty_extras import build_tier_progress_line
                        tline = build_tier_progress_line(o['user_id'])
                        if tline:
                            msg += f"\n\n{tline}"
                    except Exception: pass
                else:
                    _got, _want = _dres.get('delivered', 0), _dres.get('requested', order_qty)
                    update_order_status(oid, 'paid_pending_delivery')
                    msg = (f"⚠️ *Order #{oid} — not fully delivered*\n"
                           f"━━━━━━━━━━━━━━━━━━━━\n\n"
                           f"📦 {escape_md(o['product_name'])}\n"
                           f"🔢 Requested: *{_want}* · Delivered: *{_got}*\n\n"
                           f"The product ran out of stock while your order was "
                           f"processing. Your order is in *Pending Delivery* — "
                           f"the remaining items will be completed or refunded.")
                    if delivery and _got:
                        try:
                            await context.bot.send_message(o['user_id'], delivery)
                        except Exception:
                            pass
                    try:
                        from utils import notify_admin as _na
                        await _na(context.bot,
                            f"🚨 *Order #{oid} — partially delivered (OOS)*\n"
                            f"🔢 Requested: `{_want}` · Delivered: `{_got}`\n"
                            f"📦 Product: {escape_md(str(o.get('product_name') or '?')[:70])}\n"
                            f"👤 Customer: `{o['user_id']}`\n\n"
                            f"Complete the shortfall via *Pending Manual Delivery* or refund.")
                    except Exception:
                        pass

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 My Account", callback_data="my_account")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ])
        await q.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)
        try:
            await context.bot.send_message(ADMIN_ID,
                f"✅ EasyPaisa Auto-Verified!\n#{oid} | User: `{o['user_id']}`\n"
                f"Rs.{actual_rs:.0f} from {sender_name}\nTID: `{tid}`",
                parse_mode="Markdown")
        except: pass
        return

    status = result.get('status', 'error')
    reason = result.get('reason', 'Unknown error')

    # 🔧 Use _safe_send + plain text for error messages
    # ⏱️ Cooldown-aware button label
    cooldown = _get_remaining_cooldown(user_id, oid)
    btn_label = _verify_button_label(cooldown)

    if status == 'duplicate':
        update_order_status(oid, 'rejected')
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
        text = f"❌ Duplicate TID!\n━━━━━━━━━━━━━━━━━━━━\n\n{reason}\n\nOrder rejected."
        await _safe_send(q, context, text, reply_markup=kb)
    elif status == 'wrong_direction':
        update_order_status(oid, 'rejected')
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
        text = f"❌ Wrong Payment Direction\n━━━━━━━━━━━━━━━━━━━━\n\n{reason}"
        await _safe_send(q, context, text, reply_markup=kb)
    elif status == 'amount_mismatch':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_label, callback_data=f"epv_{oid}")],
            [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
        ])
        text = f"❌ Amount Mismatch\n━━━━━━━━━━━━━━━━━━━━\n\n{reason}"
        await _safe_send(q, context, text, reply_markup=kb)
    elif status in ('tid_not_found', 'no_emails'):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_label, callback_data=f"epv_{oid}")],
            [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ])
        text = (f"⏳ *Payment Not Found Yet*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Sometimes it takes a few minutes to process.\n\n"
                f"*Please try again in 2 minutes.*\n\n"
                f"If it still doesn't work:\n"
                f"• Double-check the Transaction ID is correct\n"
                f"• Make sure the payment was sent to our account\n"
                f"• Make sure you sent the exact amount")
        await _safe_send(q, context, text, parse_mode="Markdown", reply_markup=kb)
    elif status == 'name_mismatch':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_label, callback_data=f"epv_{oid}")],
            [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
        ])
        text = f"❌ *Name Mismatch*\n━━━━━━━━━━━━━━━━━━━━\n\n{reason}"
        await _safe_send(q, context, text, parse_mode="Markdown", reply_markup=kb)
    elif status == 'imap_error':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_label, callback_data=f"epv_{oid}")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ])
        text = (f"⚠️ *Service Temporarily Unavailable*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Payment verification is taking longer than usual.\n\n"
                f"*Please try again in 2 minutes.*")
        await _safe_send(q, context, text, parse_mode="Markdown", reply_markup=kb)
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_label, callback_data=f"epv_{oid}")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ])
        text = (f"⚠️ *Verification Failed*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Please try again in 2 minutes.\n\n"
                f"If the issue persists, contact support.")
        await _safe_send(q, context, text, parse_mode="Markdown", reply_markup=kb)

# ════════════════════════════════════════════
# 🪙 USDT TRC20 / BEP20 ON-CHAIN AUTO VERIFY
# ════════════════════════════════════════════
USDT_PAYMENT_METHODS = {
    'usdt_trc20': {
        'label': 'USDT TRC20',
        'network_label': 'TRC20 (Tron)',
        'accepted_networks': {'TRX', 'TRC20', 'TRON'},
        'address': 'TAYv4LPE92rixGsr2sKe3Pz8mGfFU5cDW7',
    },
    'usdt_bep20': {
        'label': 'USDT BEP20',
        'network_label': 'BEP20 (BNB Smart Chain)',
        'accepted_networks': {'BSC', 'BEP20', 'BNB', 'BNB Smart Chain'.upper()},
        'address': '0xe171a20f64b002b839344f67b04620c8a90d1f78',
    },
    'bybit_usdt_trc20': {
        'label': 'Bybit USDT TRC20',
        'network_label': 'TRC20 (Tron)',
        'accepted_networks': {'TRX', 'TRC20', 'TRON'},
        'address': os.getenv('BYBIT_USDT_TRC20_ADDRESS', 'TF4dCTJw42VT99NfUg95YNi5yF6uK7P2FG'),
    },
    'bybit_usdt_bep20': {
        'label': 'Bybit USDT BEP20',
        'network_label': 'BEP20 (BSC)',
        'accepted_networks': {'BSC', 'BEP20', 'BNB'},
        'address': os.getenv('BYBIT_USDT_BEP20_ADDRESS', '0xfb57f22306f460221c01ad28378fd2ce07a57bd6'),
    },
}


def _usdt_cfg(method):
    method = str(method or '').lower()
    cfg = dict(USDT_PAYMENT_METHODS.get(method) or {})
    try:
        if method == 'usdt_trc20':
            cfg['address'] = get_setting('binance_usdt_trc20_address', cfg.get('address',''))
        elif method == 'usdt_bep20':
            cfg['address'] = get_setting('binance_usdt_bep20_address', cfg.get('address',''))
        elif method == 'bybit_usdt_trc20':
            cfg['address'] = get_setting('bybit_usdt_trc20_address', cfg.get('address',''))
        elif method == 'bybit_usdt_bep20':
            cfg['address'] = get_setting('bybit_usdt_bep20_address', cfg.get('address',''))
    except Exception:
        pass
    return cfg


def _usdt_amount_match(actual, expected, tolerance=None, anchored=False):
    """v146: on-chain USDT deposits routinely arrive slightly ABOVE the order
    amount (users add a small fee buffer / round up). The old hard 0.0001
    tolerance rejected REAL payments — e.g. order for 1.0 USDT received
    1.0008888 (verified live against Binance deposit history, 2026-08-06).

    New policy:
      - `anchored=True`  (customer pasted the TXID / Bybit sender UID known):
        generous tolerance = 5 US-cents or 1% of expected (whichever is bigger).
        The txid/UID is the primary anchor; the amount is only confirmatory.
      - `anchored=False` (amount-only auto-match, no txid): tighter =
        2 US-cents or 0.5% of expected — still covers fee buffers but avoids
        cross-crediting a materially different deposit to the shared address.
    """
    try:
        actual = float(actual)
        expected = float(expected)
    except Exception:
        return False
    if tolerance is None:
        tolerance = (max(0.05, 0.01 * abs(expected)) if anchored
                     else max(0.02, 0.005 * abs(expected)))
    return abs(actual - expected) <= float(tolerance)


def _usdt_network_ok(network, cfg):
    n = str(network or '').strip().upper()
    return n in {str(x).upper() for x in (cfg.get('accepted_networks') or set())}


def _usdt_address_ok(address, cfg):
    return str(address or '').strip().lower() == str(cfg.get('address') or '').strip().lower()


def _find_matching_usdt_deposit(order, lookback_hours=96):
    """Find a successful Binance deposit matching method/network/address/amount."""
    method = str(order.get('payment_method') or '').lower()
    cfg = _usdt_cfg(method)
    if not cfg:
        return None, 'unknown_method'
    expected = float(order.get('binance_amount') or order.get('price') or 0)
    note = str(order.get('payment_note_id') or '').strip()
    if expected <= 0:
        return None, 'bad_amount'
    try:
        from payments import get_recent_deposits, binance_api_is_configured
        if not binance_api_is_configured():
            return None, 'binance_api_not_configured'
        deps = get_recent_deposits('USDT', lookback_hours=lookback_hours, limit=100)
    except Exception as e:
        return None, f'api_error:{e}'
    try:
        from database import is_txid_used
    except Exception:
        is_txid_used = lambda tx: False
    order_ts = _parse_order_created_epoch(order) if order else 0
    for d in deps:
        txid = d.get('txid') or ''
        if not txid or is_txid_used(txid):
            continue
        if note and note.lower() not in txid.lower():
            continue
        if not _usdt_network_ok(d.get('network'), cfg):
            continue
        if not _usdt_address_ok(d.get('address'), cfg):
            continue
        if not _usdt_amount_match(d.get('amount'), expected, anchored=bool(note)):
            continue
        # 🔧 v118: on-chain deposits have no note — anchor on time. A deposit that
        # landed BEFORE the order was created can't be this payment.
        t = int(d.get('time_ms') or 0)
        if t and order_ts and t < order_ts:
            continue
        return d, 'matched'
    return None, 'not_found'


async def _complete_usdt_order(bot, order, deposit):
    from database import mark_txid_used, update_order_txid, update_order_status
    txid = deposit.get('txid') or ''
    amount = float(deposit.get('amount') or order.get('binance_amount') or order.get('price') or 0)
    if txid:
        ok = mark_txid_used(txid, order['user_id'], order['id'], amount, 'USDT')
        if not ok:
            return False, 'duplicate_txid'
        update_order_txid(order['id'], txid)
    if _is_points_order(order):
        await _send_deposit_success(bot, order, amount)
    else:
        await fulfill_paid_product_order(bot, order, amount, payment_method_label=str(order.get('payment_method') or 'USDT').upper())
    return True, 'delivered'


async def _verify_usdt_order_and_respond(target, context, oid):
    o = get_order(int(oid))
    if not o:
        await _send_or_edit(target, '❌ Order not found.', reply_markup=back_btn()); return
    if o['status'] == 'delivered':
        await _send_or_edit(target, '✅ Already verified and delivered.', reply_markup=back_btn()); return
    dep, reason = _find_matching_usdt_deposit(o)
    if dep:
        ok, msg = await _complete_usdt_order(context.bot, o, dep)
        if ok:
            await _send_or_edit(target,
                f"✅ *USDT Payment Verified!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Order: `#{oid}`\n"
                f"Network: `{escape_md(dep.get('network',''))}`\n"
                f"Amount: *{float(dep.get('amount') or 0):.4f} USDT*\n"
                f"TXID: `{escape_md((dep.get('txid') or '')[:80])}`",
                parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📜 Order History', callback_data='my_orders')]]))
            return
        reason = msg
    await _send_or_edit(target,
        _pay_resp('payment_not_found_txid').format(reason=escape_md(str(reason)[:80])),
        parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('🔄 Verify Again', callback_data=f'usdtv_{oid}')],
            [InlineKeyboardButton('🎫 Support', callback_data='support_menu')],
            [InlineKeyboardButton('❌ Cancel Payment', callback_data='cancel_order')],
        ]))


def _looks_like_deposit_address(text, cfg=None):
    """v146: heuristics to catch users pasting the DEPOSIT ADDRESS where the
    bot expects a TXID (observed in the wild: '0xe171a20f...\n\nSend amount
    this adrress usdt bep20 ok'). Returns True for a plain wallet address."""
    t = str(text or '').strip()
    if not t:
        return False
    if cfg:
        addr = str(cfg.get('address') or '').strip().lower()
        if addr and addr in t.lower():
            return True
    import re as _re
    # BSC/ETH-style address: 0x + 40 hex
    if _re.fullmatch(r'0x[0-9a-fA-F]{40}', t):
        return True
    # Tron-style address: T + 33 base58 chars
    if t.startswith('T') and len(t) == 34 and _re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{34}', t):
        return True
    return False


async def usdt_txid_received(update, context):
    if context.user_data.get('usdt_step') != 'waiting_txid':
        return False
    oid = context.user_data.get('pending_order_id')
    note = (update.message.text or '').strip()
    if not oid:
        await update.message.reply_text('❌ No pending order.')
        return True
    # 🔧 v146: catch address-vs-TXID confusion BEFORE creating a dead order.
    try:
        from database import get_order
        _o = get_order(int(oid))
        cfg = _usdt_cfg(str((_o or {}).get('payment_method') or '')) if _o else None
        if _looks_like_deposit_address(note, cfg):
            await update.message.reply_text(
                "⚠️ *Ye deposit ADDRESS hai, TXID nahi!*\n\n"
                "Aap ne bot ka wallet address paste kar diya hai. Bot ko *transaction "
                "ID (TXID)* chahiye — wo transaction ka 64-characters ka proof hota hai.\n\n"
                "🪙 *TXID kaise copy karein:*\n"
                "Trust Wallet → Transaction History → us payment pe tap karein → "
                "copy karein (0x se start hone wala long hash).\n\n"
                "Ab TXID paste karein:", parse_mode='Markdown')
            return True
    except Exception:
        pass
    from database import set_order_payment_note
    set_order_payment_note(int(oid), note)
    context.user_data.pop('usdt_step', None)
    await _verify_usdt_order_and_respond(update, context, int(oid))
    return True


async def usdt_verify_callback(update, context):
    q = update.callback_query; await q.answer('Checking USDT deposit...')
    try:
        oid = int(q.data.replace('usdtv_', ''))
    except Exception:
        await q.answer('Bad order', show_alert=True); return
    await _verify_usdt_order_and_respond(q, context, oid)


async def usdt_deposit_background_job(context):
    try:
        from database import get_pending_usdt_orders
        orders = get_pending_usdt_orders(limit=25)
    except Exception:
        return
    for o in orders:
        try:
            dep, reason = _find_matching_usdt_deposit(o, lookback_hours=96)
            if dep:
                await _complete_usdt_order(context.bot, o, dep)
        except Exception:
            pass


async def _start_usdt_payment(update, context, method, *, is_points=False, amount=None, product=None, qty=1):
    from database import is_payment_enabled, get_payment_disable_msg
    cfg = _usdt_cfg(method)
    if not cfg:
        return
    q = update.callback_query; await q.answer()
    if not is_payment_enabled(method):
        await _safe_send(q, context, get_payment_disable_msg(method), reply_markup=back_btn()); return
    u = q.from_user
    save_user(u.id, u.username or '', u.first_name or '')
    if is_points:
        total_usd = float(amount or 0)
        pts = points_from_usd(total_usd)
        title_line = f"💎 You will receive *{fmt_points(pts)} Points*"
        oid = create_order(u.id, u.first_name or str(u.id), 0, f"💎 {fmt_points(pts)} Points", total_usd, method, '', total_usd, 'USDT', 'points')
    else:
        p = product
        if not p:
            await _safe_send(q, context, '❌ Product not found.', reply_markup=back_btn()); return
        total_usd = _get_price_for_qty(p, int(qty or 1)) * int(qty or 1)
        pname = p['name'] if int(qty or 1) == 1 else f"{p['name']} × {int(qty or 1)}"
        title_line = f"📦 Product: *{_fmt_msg_name(pname)}*"
        creds = context.user_data.pop('order_creds', '')
        oid = create_order(u.id, u.first_name or str(u.id), p['id'], pname, total_usd, method, '', total_usd, 'USDT', 'product', creds, qty=qty)
    update_order_status(oid, 'usdt_waiting')
    context.user_data['pending_order_id'] = oid
    context.user_data['usdt_step'] = 'waiting_txid'
    address = cfg['address']
    instr = title_line + "\n" + _pay_resp('payment_binance_usdt').format(
        method_label=cfg['label'], order_id=oid, amount=_fmt_usdt_amount(total_usd),
        network_label=cfg['network_label'], address=address
    )
    # 🔧 v129: Binance USDT is TXID-only — the customer pastes the TXID and the
    # bot auto-verifies via API. No Check button (that's Bybit USDT only).
    # 🆕 v144.1: Copy Address + Cancel are now EDITABLE registry buttons.
    await _safe_send(q, context, instr,
        parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([
            [_make_flow_btn('pay_copy_usdt_address', copy_text=CopyTextButton(address))],
            [_make_flow_btn('pay_cancel_payment', callback_data='cancel_order')],
        ]))



async def points_usdt_callback(update, context):
    q = update.callback_query
    # ptspay_usdt_trc20_5 OR ptspay_usdt_bep20_5
    raw = q.data.replace('ptspay_', '')
    method, amt_s = raw.rsplit('_', 1)
    await _start_usdt_payment(update, context, method, is_points=True, amount=float(amt_s))


async def payment_usdt_callback(update, context):
    q = update.callback_query
    # pay_usdt_trc20_<pid>_<qty>
    parts = q.data.split('_')
    method = '_'.join(parts[1:3])
    pid = int(parts[3]); qty = int(parts[4]) if len(parts) > 4 else 1
    p = get_product(pid)
    if not p:
        await _safe_send(q, context, '❌ Product not found.', reply_markup=back_btn()); return
    if p['stock'] < qty:
        await _safe_send(q, context, f"❌ Only {p['stock']} in stock!", reply_markup=back_btn()); return
    await _start_usdt_payment(update, context, method, is_points=False, product=p, qty=qty)


# ── Grouped payment menus ──
async def payment_binance_menu_callback(update, context):
    q=update.callback_query; await q.answer()
    parts=q.data.split('_'); pid=int(parts[3]); qty=int(parts[4]) if len(parts)>4 else 1
    from database import is_payment_enabled
    kb=[]
    from keyboards import _rb
    if is_payment_enabled('binance'):
        b=_rb('pay_binance', callback_data=f'pay_binance_{pid}_{qty}'); kb.append([b] if b else [InlineKeyboardButton('Binance Pay', callback_data=f'pay_binance_{pid}_{qty}')])
    if is_payment_enabled('usdt_bep20'):
        b=_rb('pay_usdt_bep20', callback_data=f'pay_usdt_bep20_{pid}_{qty}'); kb.append([b] if b else [InlineKeyboardButton('USDT BEP20', callback_data=f'pay_usdt_bep20_{pid}_{qty}')])
    if is_payment_enabled('usdt_trc20'):
        b=_rb('pay_usdt_trc20', callback_data=f'pay_usdt_trc20_{pid}_{qty}'); kb.append([b] if b else [InlineKeyboardButton('USDT TRC20', callback_data=f'pay_usdt_trc20_{pid}_{qty}')])
    kb.append([InlineKeyboardButton('🔙 Back', callback_data=f'buy_{pid}' if qty==1 else f'buyx_{pid}')])
    await _safe_send(q, context, _pay_resp('payment_binance_menu_text'), parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

async def points_binance_menu_callback(update, context):
    q=update.callback_query; await q.answer()
    amt=q.data.replace('ptspay_binance_menu_','')
    from database import is_payment_enabled
    kb=[]
    from keyboards import _rb
    if is_payment_enabled('binance'):
        b=_rb('pay_binance', callback_data=f'ptspay_binance_{amt}'); kb.append([b] if b else [InlineKeyboardButton('Binance Pay', callback_data=f'ptspay_binance_{amt}')])
    if is_payment_enabled('usdt_bep20'):
        b=_rb('pay_usdt_bep20', callback_data=f'ptspay_usdt_bep20_{amt}'); kb.append([b] if b else [InlineKeyboardButton('USDT BEP20', callback_data=f'ptspay_usdt_bep20_{amt}')])
    if is_payment_enabled('usdt_trc20'):
        b=_rb('pay_usdt_trc20', callback_data=f'ptspay_usdt_trc20_{amt}'); kb.append([b] if b else [InlineKeyboardButton('USDT TRC20', callback_data=f'ptspay_usdt_trc20_{amt}')])
    kb.append([InlineKeyboardButton('🔙 Back', callback_data='buy_points')])
    await _safe_send(q, context, _pay_resp('payment_binance_menu_text'), parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

async def payment_bybit_menu_callback(update, context):
    q=update.callback_query; await q.answer()
    parts=q.data.split('_'); pid=int(parts[3]); qty=int(parts[4]) if len(parts)>4 else 1
    from database import is_payment_enabled
    kb=[]
    from keyboards import _rb
    if is_payment_enabled('bybit_pay'):
        b=_rb('pay_bybit_pay', callback_data=f'pay_bybit_pay_{pid}_{qty}'); kb.append([b] if b else [InlineKeyboardButton('Bybit Pay', callback_data=f'pay_bybit_pay_{pid}_{qty}')])
    if is_payment_enabled('bybit_usdt_bep20'):
        b=_rb('pay_bybit_usdt_bep20', callback_data=f'pay_bybit_usdt_bep20_{pid}_{qty}'); kb.append([b] if b else [InlineKeyboardButton('USDT BEP20', callback_data=f'pay_bybit_usdt_bep20_{pid}_{qty}')])
    if is_payment_enabled('bybit_usdt_trc20'):
        b=_rb('pay_bybit_usdt_trc20', callback_data=f'pay_bybit_usdt_trc20_{pid}_{qty}'); kb.append([b] if b else [InlineKeyboardButton('USDT TRC20', callback_data=f'pay_bybit_usdt_trc20_{pid}_{qty}')])
    kb.append([InlineKeyboardButton('🔙 Back', callback_data=f'buy_{pid}' if qty==1 else f'buyx_{pid}')])
    await _safe_send(q, context, _pay_resp('payment_bybit_menu_text'), parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

async def points_bybit_menu_callback(update, context):
    q=update.callback_query; await q.answer()
    amt=q.data.replace('ptspay_bybit_menu_','')
    from database import is_payment_enabled
    kb=[]
    from keyboards import _rb
    if is_payment_enabled('bybit_pay'):
        b=_rb('pay_bybit_pay', callback_data=f'ptspay_bybit_pay_{amt}'); kb.append([b] if b else [InlineKeyboardButton('Bybit Pay', callback_data=f'ptspay_bybit_pay_{amt}')])
    if is_payment_enabled('bybit_usdt_bep20'):
        b=_rb('pay_bybit_usdt_bep20', callback_data=f'ptspay_bybit_usdt_bep20_{amt}'); kb.append([b] if b else [InlineKeyboardButton('USDT BEP20', callback_data=f'ptspay_bybit_usdt_bep20_{amt}')])
    if is_payment_enabled('bybit_usdt_trc20'):
        b=_rb('pay_bybit_usdt_trc20', callback_data=f'ptspay_bybit_usdt_trc20_{amt}'); kb.append([b] if b else [InlineKeyboardButton('USDT TRC20', callback_data=f'ptspay_bybit_usdt_trc20_{amt}')])
    kb.append([InlineKeyboardButton('🔙 Back', callback_data='buy_points')])
    await _safe_send(q, context, _pay_resp('payment_bybit_menu_text'), parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))


def _norm_hash(value):
    return re.sub(r"[^a-zA-Z0-9]", "", str(value or "")).lower()


def _bybit_hash_matches(record, note):
    if not note:
        return True
    key = _norm_hash(note)
    if not key:
        return False
    candidates = []
    for k in ("txid", "id", "transactionHash", "hash", "txHash", "transactionId"):
        v = record.get(k) if isinstance(record, dict) else None
        if v: candidates.append(v)
    try:
        candidates.extend(record.get("identifiers") or [])
    except Exception:
        pass
    try:
        raw = record.get("raw") or {}
        if isinstance(raw, dict):
            for k in ("txID", "id", "transactionHash", "hash", "txHash", "transactionId"):
                if raw.get(k): candidates.append(raw.get(k))
    except Exception:
        pass
    for cand in candidates:
        c = _norm_hash(cand)
        if c and (key == c or key in c or c in key):
            return True
    return False


def _parse_order_created_epoch(order) -> int:
    """Parse orders.created_at ("YYYY-MM-DD HH:MM:SS") to epoch ms. 0 on fail."""
    try:
        raw = str((order or {}).get('created_at') or '')
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return int(_dt.datetime.strptime(raw, fmt).replace(tzinfo=_dt.timezone.utc).timestamp() * 1000)
            except Exception:
                continue
    except Exception:
        pass
    return 0


def _bybit_recent_amount_fallback(rows, expected, order=None, window_min=0):
    """🔧 v113/v117: Safe fallback when the customer's pasted Bybit Pay Order ID
    does not exactly equal the API's internal-deposit txID (Bybit Pay may show
    a different order number than the internal transfer ID — the Order ID is
    NOT stored in the API record at all, only a UUID txID).

    Matching rules (all must hold, fraud-safe):
      - deposit is an internal transfer (BYBIT_INTERNAL = Bybit Pay/UID transfer),
      - amount matches within tolerance,
      - NOT already marked used,
      - it arrived AFTER the order was created (when `order` is given) — this
        replaces the old 30-min window so older-but-valid payments still match,
      - and it is the ONLY such deposit (unambiguous).
    v117: the recency window is replaced by "created after the order", which
    fixes the real case where a Bybit Pay transfer arrives and the customer
    pastes the app Order ID hours later — the old 30-min window had expired.
    """
    try:
        from database import is_txid_used
    except Exception:
        is_txid_used = lambda tx: False
    order_ts = _parse_order_created_epoch(order) if order else 0
    hits = []
    seen = set()
    for d in rows:
        try:
            txid = d.get('txid') or ''
            sig = (txid, d.get('amount'), d.get('network'))
            if sig in seen:
                continue
            seen.add(sig)
            if not txid or is_txid_used(txid):
                continue
            if str(d.get('network') or '').upper() != 'BYBIT_INTERNAL':
                continue
            if not _usdt_amount_match(d.get('amount'), expected, anchored=True):
                continue
            # 🆕 v161.18: TIME SYSTEM REMOVED (user demand). Payment matches on
            # unique amount + txid dedup alone — the deposit can arrive at any
            # time (before or after order creation) and still credit, because
            # the bot's unique random amount + is_txid_used guard make
            # double-credit impossible. No order_ts comparison anymore.
            hits.append(d)
        except Exception:
            continue
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        # 🆕 v161.12: multiple same-amount internal deposits after the order
        # (e.g. an abandoned attempt + the real one) — prefer the NEWEST one,
        # which is overwhelmingly the current payment. All hits already passed
        # amount + internal + after-order + not-used filters (fraud-safe).
        try:
            return max(hits, key=lambda d: int(d.get('time_ms') or 0))
        except Exception:
            return None
    return None


def _norm_digits(value):
    """Keep only digits — Bybit Pay Order IDs are long digit strings that may
    be copied with spaces/dashes or split across receipt lines."""
    return re.sub(r"\D", "", str(value or ""))


def _deep_find_id(record, key_norm):
    """Recursively search every string value inside the deposit record (incl.
    raw nested dicts/lists) for the normalized pasted Order ID.

    🔧 v116 (2026-08-01): Bybit Pay shows a 25-32 digit *Order ID* on the
    receipt, while the internal-deposit API returns a *txID* (often a UUID) in
    `txID`. The Order ID may live in another field of the raw record that the
    docs don't advertise (e.g. id/reference/orderId/transferId). A pasted ID is
    long and specific, so finding it anywhere in the record is a safe match.
    """
    if not key_norm:
        return False
    stack = [record]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple, set)):
            stack.extend(item)
        elif isinstance(item, str):
            if key_norm in _norm_digits(item):
                return True
    return False


def _find_matching_bybit_payment(order, lookback_hours=720):  # 🆕 v161.18: 30 days — no time rejection
    """Find a Bybit deposit matching the order.

    🔧 AUDIT-FIX v112 (2026-07-31): returns a *diagnostic* reason string instead
    of the old generic "transaction_hash_not_found", so a failed verification
    tells the admin exactly what happened:
      - bybit_api_not_configured      → BYBIT_API_KEY/SECRET missing on server
      - api_error:<retMsg>            → the Bybit API itself returned an error
                                        (e.g. permission denied, IP blocked)
      - no_records:<details>          → API OK but 0 deposits in the window
      - hash_not_found:<N>            → N records scanned, hash matched none
      - amount_mismatch               → hash matched but the sent amount differs
      - matched                       → verified
    """
    method=str(order.get('payment_method') or '').lower()
    expected=float(order.get('binance_amount') or order.get('price') or 0)
    note=str(order.get('payment_note_id') or '').strip()
    try:
        from payments import (bybit_api_is_configured, get_bybit_deposit_records,
                              get_bybit_internal_deposits, bybit_api_last_meta)
        if not bybit_api_is_configured(): return None, 'bybit_api_not_configured'
    except Exception as e:
        return None, f'import_error:{e}'
    try:
        from database import is_txid_used
    except Exception:
        is_txid_used=lambda tx: False
    cfg=_usdt_cfg(method)
    if method == 'bybit_pay':
        rows = []
        diag = {"internal_ok": None, "internal_count": 0,
                "onchain_ok": None, "onchain_count": 0}
        # 🔧 v122: UID+unique-amount match (new flow). When the order carries the
        # customer's Bybit UID and a unique 4-decimal amount, match an internal
        # deposit from that exact sender UID with the exact amount. This is the
        # primary detection for the new flow — no pasted ID needed.
        try:
            cust_uid = str((order or {}).get('customer_bybit_uid') or '').strip()
        except Exception:
            cust_uid = ''
        uid_mode = False  # 🆕 v161.12
        if cust_uid:
            uid_mode = True  # 🆕 v161.12: remember we had a UID to report better
            try:
                uid_rows = get_bybit_internal_deposits('USDT', lookback_hours=lookback_hours)
            except Exception:
                uid_rows = []
            for d in uid_rows:
                try:
                    txid = d.get('txid') or ''
                    if not txid or is_txid_used(txid):
                        continue
                    if str(d.get('from_member_id') or '').strip() != cust_uid:
                        continue
                    if not _usdt_amount_match(d.get('amount'), expected, anchored=True):
                        continue
                    return d, 'matched'
                except Exception:
                    continue
            # 🆕 v161.12 BUGFIX: NO early return here! Bybit's deposit API can
            # lag or omit from_member_id on fresh internal transfers — falling
            # straight back to the generic scan + amount fallback lets the SAME
            # deposit still be matched by amount/internal/recency, instead of
            # failing with a bare 'no_records' that blocks auto-credit.
        # First try exact ID query, then always scan recent list. Bybit UI may
        # show an ID that does not return with the exact txID filter, while the
        # same ID exists in the recent payload — the full scan covers that.
        try:
            if note:
                rows.extend(get_bybit_internal_deposits('USDT', lookback_hours=lookback_hours, txid=note))
        except Exception:
            pass
        try:
            rows.extend(get_bybit_internal_deposits('USDT', lookback_hours=lookback_hours))
        except Exception:
            pass
        m = bybit_api_last_meta()
        diag["internal_ok"] = bool(m.get("ok"))
        diag["internal_count"] = int(m.get("count") or 0)
        # Some Bybit-to-Bybit receipts appear in normal deposit records
        # depending on account/site, so scan both exact and full on-chain too.
        try:
            if note:
                rows.extend(get_bybit_deposit_records('USDT', lookback_hours=lookback_hours, txid=note))
        except Exception:
            pass
        try:
            rows.extend(get_bybit_deposit_records('USDT', lookback_hours=lookback_hours))
        except Exception:
            pass
        m2 = bybit_api_last_meta()
        diag["onchain_ok"] = bool(m2.get("ok"))
        diag["onchain_count"] = int(m2.get("count") or 0)

        if diag["internal_ok"] is False or diag["onchain_ok"] is False:
            err = (m or m2 or {}).get("retMsg") or (m or m2 or {}).get("error") or "unknown"
            return None, f"api_error:{str(err)[:140]}"

        seen = set()
        note_norm = _norm_digits(note)
        # 🔧 v118: the per-order Reference ID (if any) is another match candidate —
        # best-effort, in case Bybit surfaces it in the record (it is not in the
        # internal-deposit response today, but deep-match is harmless).
        try:
            ref = str(order.get('pay_reference') or '') if order else ''
        except Exception:
            ref = ''
        ref_norm = _norm_digits(ref)
        for d in rows:
            txid=d.get('txid') or ''
            sig = (txid, d.get('amount'), d.get('network'))
            if sig in seen: continue
            seen.add(sig)
            if not txid or is_txid_used(txid): continue
            # 🔧 v116/v118: match by hash, pasted Order ID, or stored Reference ID
            # found anywhere in the record (digits-normalized).
            # 🆕 v161.15 FIX: with NO pasted ID, _bybit_hash_matches(d,"") returns
            # True for EVERY record → the first old deposit triggered a bogus
            # 'amount_mismatch' and blocked the amount-fallback. Only do hash
            # matching when the customer actually pasted something.
            hash_ok = False
            if note or ref:
                hash_ok = (_bybit_hash_matches(d, note)
                           or (note_norm and _deep_find_id(d, note_norm))
                           or (ref_norm and _deep_find_id(d, ref_norm)))
            if hash_ok and not _usdt_amount_match(d.get('amount'), expected, anchored=True):
                return None, 'amount_mismatch'
            if hash_ok and _usdt_amount_match(d.get('amount'), expected, anchored=True):
                return d, 'matched'
        # 🔧 v113/v117: Bybit Pay Order ID vs internal txID fallback (see helper).
        fb = _bybit_recent_amount_fallback(rows, expected, order=order)
        if fb:
            return fb, 'matched'
        if not rows:
            if uid_mode:
                # 🆕 v161.12: deposit not yet visible to the API (Bybit lag) or
                # from_member_id absent — tell admin clearly, keep order pending.
                return None, 'uid_amount_not_found'
            return None, f"no_records:internal={diag['internal_count']},onchain={diag['onchain_count']}"
        return None, f"hash_not_found:{len(rows)}"
    if method in ('bybit_usdt_trc20','bybit_usdt_bep20'):
        rows=get_bybit_deposit_records('USDT', lookback_hours=lookback_hours, txid=note) if note else get_bybit_deposit_records('USDT', lookback_hours=lookback_hours)
        # 🔧 v161.12: also scan the full recent list when a txid filter came back
        # empty (Bybit indexing lag) — never trust a single filtered query.
        if note:
            try:
                rows.extend(get_bybit_deposit_records('USDT', lookback_hours=lookback_hours))
            except Exception:
                pass
        for d in rows:
            txid=d.get('txid') or ''
            if not txid or is_txid_used(txid): continue
            # 🆕 v161.12: TXID optional — if the customer didn't paste one (or
            # Bybit lags), match by network + address + amount + after-order,
            # exactly like the internal fallback. Amount is the primary anchor.
            if note:
                if not _bybit_hash_matches(d, note): continue
            if not _usdt_network_ok(d.get('network'), cfg): continue
            if not _usdt_address_ok(d.get('address'), cfg): continue
            if not _usdt_amount_match(d.get('amount'), expected, anchored=bool(note)):
                continue
            # 🆕 v161.18: TIME SYSTEM REMOVED (user demand) — network + address +
            # amount + txid-dedup is enough. Deposit arriving any time still
            # credits; is_txid_used prevents double-credit.
            return d, 'matched'
        if not rows:
            return None, 'no_records'
        return None, 'not_found'
    return None, 'unknown_method'

async def _complete_bybit_order(bot, order, dep):
    from database import mark_txid_used, update_order_txid
    txid=dep.get('txid') or ''
    amount=float(dep.get('amount') or order.get('binance_amount') or order.get('price') or 0)
    if txid:
        ok=mark_txid_used(txid, order['user_id'], order['id'], amount, 'USDT')
        if not ok: return False, 'duplicate_txid'
        update_order_txid(order['id'], txid)
    if _is_points_order(order): await _send_deposit_success(bot, order, amount)
    else: await fulfill_paid_product_order(bot, order, amount, payment_method_label=str(order.get('payment_method') or 'BYBIT').upper())
    return True, 'delivered'

def _bybit_failure_hint(reason):
    """Human explanation of a Bybit verification failure reason (v112)."""
    r = str(reason or '')
    if r == 'bybit_api_not_configured':
        return "BYBIT_API_KEY / BYBIT_API_SECRET are missing on the server — set them in Render env."
    if r == 'amount_mismatch':
        return "The transfer ID was FOUND but the received amount differs from the order amount."
    if r.startswith('api_error:'):
        return (f"The Bybit API itself returned an error:\n`{r[len('api_error:'):]}`\n"
                f"Fix: 1) In Bybit → API Management, under *Wallet* enable **Asset Information** "
                f"(资产信息) — this is the permission that gates deposit records. "
                f"2) Set the key to *No IP restriction* (or add Render's IPs). "
                f"3) Make sure the key belongs to the *same Bybit UID* as the Pay ID "
                f"customers pay to. All three are read-only and safe.")
    if r.startswith('no_records:'):
        return "Bybit API works, but no deposits were found in the last 96h for this API key's account. Check that the Bybit Pay ID / UID in the bot matches THIS API key's account."
    if r.startswith('hash_not_found:'):
        return (f"The bot scanned {r.split(':',1)[1]} record(s) but none matched the pasted ID, "
                f"and no fresh same-amount Bybit Pay transfer was found either. Ask the customer "
                f"to re-copy the exact *Transfer ID* from Bybit Pay → Transaction History, or "
                f"confirm the deposit in the Bybit app and tap 'Mark Received & Credit'.")
    return "Payment could not be auto-verified. Confirm the deposit in your Bybit app before crediting."


def _bybit_deposit_dump(rows, limit=6, pasted_id="") -> str:
    """Short human-readable dump of what the Bybit API actually returned, so
    the admin can see whether the customer's deposit is visible to the API key
    and why it didn't match. 🔧 v115. v116 adds `id` + whether the pasted Order
    ID was found anywhere inside the record (deep search)."""
    if not rows:
        return "API returned 0 deposit records."
    lines = []
    now_ms = int(_time.time() * 1000)
    note_norm = _norm_digits(pasted_id)
    for i, d in enumerate(rows[:limit], 1):
        txid = str(d.get('txid') or '')[:26] or '?'
        rid = str(d.get('id') or '')[:20] or '?'
        amt = d.get('amount')
        net = d.get('network') or '?'
        try:
            t = int(d.get('time_ms') or 0)
            age_min = round((now_ms - t) / 60000, 1) if t else None
            age = f"{age_min}min old" if age_min is not None else "time?"
        except Exception:
            age = "time?"
        found = ""
        if note_norm:
            try:
                found = "  🎯 PASTED-ID FOUND IN RECORD" if _deep_find_id(d, note_norm) else ""
            except Exception:
                found = ""
        lines.append(f"  {i}. id={rid}  txid={txid}…  {amt} USDT  net={net}  {age}{found}")
    if len(rows) > limit:
        lines.append(f"  …and {len(rows) - limit} more")
    return "\n".join(lines)


async def _notify_admin_bybit_failure(bot, order, reason):
    """Send the admin an ACTIONABLE alert when Bybit auto-verification fails.

    🔧 AUDIT-FIX v112: the old code either sent a passive debug message or
    (in the background job) NOTHING at all — stuck bybit_waiting orders were
    invisible until a customer complained. Now the admin gets a one-tap
    "Mark Received & Credit" button to resolve it instantly.
    """
    try:
        from config import ADMIN_ID as _AID
        oid = int(order.get('id') or 0)
        note_dbg = str(order.get('payment_note_id') or '').strip()
        exp = float(order.get('binance_amount') or order.get('price') or 0)
        # 🔧 v115 diagnostics: API key UID vs Pay ID + what deposits the API saw
        diag_lines = []
        try:
            from payments import get_bybit_api_key_info
            kinfo = await asyncio.to_thread(get_bybit_api_key_info)
            try:
                from database import get_setting as _gs
                pay_uid = str(_gs('bybit_pay_id', os.getenv('BYBIT_PAY_ID', '')) or '')
            except Exception:
                pay_uid = str(os.getenv('BYBIT_PAY_ID', '') or '')
            if kinfo.get('ok'):
                key_uid = str(kinfo.get('uid') or '')
                diag_lines.append(f"🔑 *API key UID:* `{key_uid or '?'}`")
                if pay_uid and key_uid and pay_uid.strip() != key_uid.strip():
                    diag_lines.append("🚨 *UID MISMATCH!* API key UID ≠ Pay ID customers pay to. The bot can NEVER see these deposits. Use a key from the SAME account as the Pay ID.")
            else:
                diag_lines.append(f"🔑 API key UID: unreadable ({escape_md(str(kinfo.get('error'))[:80])})")
            diag_lines.append(f"🎯 *Customers pay to:* `{escape_md(pay_uid or 'not set')}`")
        except Exception as _du:
            diag_lines.append(f"(uid diag failed: {_du})")
        try:
            dep_rows = []
            try:
                from payments import get_bybit_internal_deposits, get_bybit_deposit_records
                dep_rows.extend(await asyncio.to_thread(get_bybit_internal_deposits, 'USDT', 96))
                dep_rows.extend(await asyncio.to_thread(get_bybit_deposit_records, 'USDT', 96))
            except Exception:
                pass
            seen = set()
            uniq = []
            for d in dep_rows:
                sig = (d.get('txid'), d.get('amount'), d.get('network'))
                if sig in seen:
                    continue
                seen.add(sig)
                uniq.append(d)
            diag_lines.append("📡 *API deposits found:*")
            diag_lines.append(_bybit_deposit_dump(uniq, pasted_id=note_dbg))
        except Exception as _dd:
            diag_lines.append(f"(deposit dump failed: {_dd})")
        diag_text = "\n".join(diag_lines)
        txt = (
            "⚠️ *Bybit Payment — needs your check*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🧾 Order: `#{oid}` (created {escape_md(str(order.get('created_at') or '?'))})\n"
            f"👤 Customer: `{order.get('user_id') or '?'}`\n"
            f"💵 Amount: *{fmt_price(exp)} USDT*\n"
            + "\n".join(order_payment_context(oid)) + ("\n" if order_payment_context(oid) else "") +
            f"🔗 ID pasted: `{escape_md(note_dbg[:60]) or '—'}`\n"
            f"📋 Reason: `{escape_md(str(reason)[:120])}`\n"
            f"💡 {_bybit_failure_hint(reason)}\n\n"
            f"{diag_text}\n\n"
            f"_Check your Bybit app (Funding → History → Bybit Pay / Deposit). "
            f"If the payment is there, tap below — points/order will be credited "
            f"and this hash marked used so it can't be reused._"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Mark Received & Credit", callback_data=f"bybit_manual_confirm_{oid}")],
            [InlineKeyboardButton("👤 Customer Chat", callback_data=f"adm_chat_{order.get('user_id') or 0}")],
        ])
        await bot.send_message(_AID, txt, parse_mode='Markdown', reply_markup=kb)
    except Exception as e:
        import logging as _l
        _l.getLogger(__name__).warning(f"[BybitAlert] admin notify failed: {e}")


def _bybit_failure_alerted_recently(order_id, cooldown_min=30):
    """Throttle: don't spam the admin every 45s for the same stuck order."""
    try:
        from database import get_setting, set_setting
        key = f"bybit_alerted_{int(order_id)}"
        last = 0
        try:
            last = float(get_setting(key, '0') or 0)
        except Exception:
            last = 0
        now = _time.time()
        if now - last < cooldown_min * 60:
            return True
        set_setting(key, f"{now}")
        return False
    except Exception:
        return False


async def bybit_manual_confirm_callback(update, context):
    """✅ Admin one-tap manual confirm for a stuck Bybit payment (v112)."""
    q = update.callback_query
    try:
        if q.from_user.id != ADMIN_ID:
            await q.answer("❌", show_alert=True)
            return
        await q.answer("Crediting…")
        oid = int(q.data.replace('bybit_manual_confirm_', ''))
    except Exception:
        return
    try:
        o = get_order(oid)
        if not o:
            await q.edit_message_text("❌ Order not found.")
            return
        if str(o.get('status') or '') == 'delivered':
            await q.edit_message_text("✅ Order already delivered.")
            return
        if str(o.get('status') or '') not in ('bybit_waiting', 'usdt_waiting', 'paid_pending_delivery', 'pending'):
            await q.edit_message_text(f"⚠️ Order status is `{o.get('status')}` — no credit applied.", parse_mode='Markdown')
            return
        # Reuse the same completion logic as auto-verify (idempotent: marks
        # the pasted ID used so the same transfer can't be re-credited).
        amount = float(o.get('binance_amount') or o.get('price') or 0)
        note = str(o.get('payment_note_id') or '').strip()
        dep = {"txid": note or "", "amount": amount}
        ok, msg = await _complete_bybit_order(context.bot, o, dep)
        if ok:
            await q.edit_message_text(
                f"✅ *Order #{oid} credited manually.*\n"
                f"💵 Amount: `{fmt_price(amount)} USDT`\n"
                f"🔗 ID: `{escape_md((note or '—')[:60])}`\n\n"
                f"Customer has been notified.",
                parse_mode='Markdown')
        else:
            await q.edit_message_text(f"⚠️ Could not credit: {escape_md(str(msg))}", parse_mode='Markdown')
    except Exception as e:
        import logging as _l
        _l.getLogger(__name__).exception(f"[BybitManual] confirm failed for {oid}")
        try:
            await q.edit_message_text("❌ Failed to credit. Check logs.")
        except Exception:
            pass


async def _verify_bybit_order_and_respond(target, context, oid):
    o=get_order(int(oid))
    if not o: await _send_or_edit(target, '❌ Order not found.', reply_markup=back_btn()); return
    if o['status']=='delivered': await _send_or_edit(target, '✅ Already verified.', reply_markup=back_btn()); return
    # 🆕 v161.22 FIX (bot SLOW + not-detected): the Bybit scan is a sync
    # proxy-rotating API call — run it in a worker thread so the Check button
    # responds instantly and the event loop never freezes.
    dep,reason=await asyncio.to_thread(_find_matching_bybit_payment, o)
    if dep:
        ok,msg=await _complete_bybit_order(context.bot,o,dep)
        if ok:
            # 🆕 v161.24 (user demand): extra "Bybit Payment Verified!" message
            # REMOVED — the beautiful "Deposit Successful!" message (points) or
            # the product-delivery message is ALREADY sent by _complete_bybit_order.
            # The Check Payment screen just shows a small confirmation toast.
            try:
                await target.answer("✅ Verified! Check your deposit message above.")
            except Exception:
                pass
            return
        reason=msg
    # 🔧 AUDIT-FIX v112: actionable admin alert (throttled to avoid spam when
    # the customer taps "Check Again" repeatedly). Customer still sees the
    # friendly "not found yet" screen with retry/support options.
    try:
        if not _bybit_failure_alerted_recently(oid, cooldown_min=15):
            await _notify_admin_bybit_failure(context.bot, o, reason)
    except Exception:
        pass
    await _send_or_edit(target, _pay_resp('payment_not_found_txid').format(reason="not found yet"), parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔄 Check Again', callback_data=f'bybitv_{oid}')],[InlineKeyboardButton('🎫 Support', callback_data='support_menu')],[InlineKeyboardButton('❌ Cancel Payment', callback_data='cancel_order')]]))

async def bybit_verify_callback(update, context):
    q=update.callback_query; await q.answer('Checking Bybit payment...')
    oid=int(q.data.replace('bybitv_',''))
    await _verify_bybit_order_and_respond(q, context, oid)

async def bybit_txid_received(update, context):
    if context.user_data.get('bybit_step')!='waiting_txid': return False
    oid=context.user_data.get('pending_order_id')
    note=(update.message.text or '').strip()
    if not oid: await update.message.reply_text('❌ No pending order.'); return True
    from database import set_order_payment_note
    set_order_payment_note(int(oid), note)
    context.user_data.pop('bybit_step',None)
    await _verify_bybit_order_and_respond(update, context, int(oid))
    return True

async def bybit_deposit_background_job(context):
    """🆕 v161.24 (user demand): Bybit auto-detect job REMOVED.
    Verification now ONLY happens when the customer taps 🔍 Check Payment
    (see _verify_bybit_order_and_respond). This stub stays so old imports
    never break — it does nothing.
    """


async def _start_bybit_payment(update, context, method, *, is_points=False, amount=None, product=None, qty=1):
    from database import is_payment_enabled, get_payment_disable_msg
    q=update.callback_query; await q.answer()
    if not is_payment_enabled(method): await _safe_send(q, context, get_payment_disable_msg(method), reply_markup=back_btn()); return
    u=q.from_user; save_user(u.id,u.username or '',u.first_name or '')
    if is_points:
        total_usd=float(amount or 0); pts=points_from_usd(total_usd)
        title_line = f"💎 You will receive *{fmt_points(pts)} Points*"
        oid=create_order(u.id,u.first_name or str(u.id),0,f"💎 {fmt_points(pts)} Points",total_usd,method,'',total_usd,'USDT','points')
    else:
        p=product
        total_usd=_get_eff_price(p)*int(qty or 1); pname=p['name'] if int(qty or 1)==1 else f"{p['name']} × {int(qty or 1)}"
        title_line = f"📦 Product: *{_fmt_msg_name(pname)}*"
        creds=context.user_data.pop('order_creds','')
        oid=create_order(u.id,u.first_name or str(u.id),p['id'],pname,total_usd,method,'',total_usd,'USDT','product',creds,qty=qty)
    update_order_status(oid,'bybit_waiting'); context.user_data['pending_order_id']=oid; context.user_data['bybit_step']='waiting_txid'
    if method=='bybit_pay':
        pay_id=get_setting('bybit_pay_id', os.getenv('BYBIT_PAY_ID','')).strip()
        if not pay_id:
            await _safe_send(q, context, '❌ Bybit Pay ID is not configured. Admin must set BYBIT_PAY_ID in Render env or Payment Settings.', reply_markup=back_btn()); return
        # 🔧 v118: per-order Reference ID — customer pastes it into the Bybit Pay
        # "Reference" field when sending, so the bot can identify the payment.
        # 🔧 v119: reference line + copy buttons are now EDITABLE (screen editor):
        #   - the reference text uses the editable response payment_bybit_pay_reference
        #   - the Copy buttons read btn_label_pay_copy_* / btn_style_pay_copy_*
        #     (rename with premium emoji + pick blue/green/red), see make_copy_text_button
        from database import gen_unique_pay_reference, set_order_pay_reference
        from button_system import make_copy_text_button
        ref = gen_unique_pay_reference()
        set_order_pay_reference(oid, ref)
        instr = title_line + "\n" + _pay_resp('payment_bybit_pay').format(order_id=oid, amount=_fmt_usdt_amount(total_usd), pay_id=escape_md(pay_id))
        instr += "\n\n" + _pay_resp('payment_bybit_pay_reference').format(reference_id=ref)
        kb = InlineKeyboardMarkup([
            [make_copy_text_button('pay_copy_reference', ref)],
            [make_copy_text_button('pay_copy_bybitpay', pay_id)],
            [InlineKeyboardButton('❌ Cancel Payment', callback_data='cancel_order')],
        ])
    else:
        cfg=_usdt_cfg(method)
        instr = title_line + "\n" + _pay_resp('payment_bybit_usdt').format(
            method_label=cfg['label'], order_id=oid, amount=_fmt_usdt_amount(total_usd),
            network_label=cfg['network_label'], address=cfg['address']
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton('📋 Copy Address', copy_text=CopyTextButton(cfg['address']))],[InlineKeyboardButton('❌ Cancel Payment', callback_data='cancel_order')]])
    await _safe_send(q, context, instr, parse_mode='Markdown', reply_markup=kb)


async def points_bybit_callback(update, context):
    q=update.callback_query; raw=q.data.replace('ptspay_',''); method,amt_s=raw.rsplit('_',1)
    try:
        await q.answer()
    except Exception:
        pass
    # 🔧 v125: all Bybit methods use the unified flow.
    if method in ('bybit_pay', 'bybit_usdt_trc20', 'bybit_usdt_bep20'):
        await bybit_start_flow(q, context, method, mode='points', base_amount=float(amt_s))
        return
    await _start_bybit_payment(update, context, method, is_points=True, amount=float(amt_s))

async def payment_bybit_callback(update, context):
    q=update.callback_query; parts=q.data.split('_')
    # pay_bybit_usdt_trc20_pid_qty OR pay_bybit_pay_pid_qty
    if parts[2]=='pay': method='bybit_pay'; pid=int(parts[3]); qty=int(parts[4]) if len(parts)>4 else 1
    else: method='_'.join(parts[1:4]); pid=int(parts[4]); qty=int(parts[5]) if len(parts)>5 else 1
    try:
        await q.answer()
    except Exception:
        pass
    p=get_product(pid)
    if not p: await _safe_send(q, context, '❌ Product not found.', reply_markup=back_btn()); return
    if p['stock'] < qty: await _safe_send(q, context, f"❌ Only {p['stock']} in stock!", reply_markup=back_btn()); return
    # 🔧 v125: all Bybit methods use the unified flow.
    if method in ('bybit_pay', 'bybit_usdt_trc20', 'bybit_usdt_bep20'):
        await bybit_start_flow(q, context, method, mode='product', product=p, qty=qty)
        return
    await _start_bybit_payment(update, context, method, is_points=False, product=p, qty=qty)


# ════════════════════════════════════════════
# 💎 BUY POINTS HANDLERS
# ════════════════════════════════════════════
async def points_amount_callback(update, context):
    q = update.callback_query; await q.answer()
    amt = int(q.data.split("_")[1]); pts = points_from_usd(amt)
    context.user_data['points_amount'] = amt
    await q.edit_message_text(
        f"💎 *Buy {fmt_points(pts)} Points*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 ${amt} = {fmt_points(pts)} Points\n\nSelect payment method:",
        parse_mode="Markdown", reply_markup=points_payment_keyboard(amt))


async def points_custom_callback(update, context):
    q = update.callback_query; await q.answer()
    context.user_data['points_step'] = 'waiting_custom_amount'
    await q.edit_message_text("💎 Enter amount ($):", reply_markup=cancel_back_btn())


async def points_custom_amount_received(update, context):
    if context.user_data.get('points_step') != 'waiting_custom_amount':
        return False
    txt = update.message.text.strip().replace('$','').strip()
    m = re.search(r'(\d+\.?\d*)', txt)
    if not m: await update.message.reply_text("❌ Numbers only!"); return True
    amt = float(m.group(1))
    if amt <= 0: await update.message.reply_text("❌ > 0!"); return True
    context.user_data['points_amount'] = amt
    context.user_data.pop('points_step', None)
    pts = points_from_usd(amt)
    await update.message.reply_text(
        f"💎 *{fmt_points(pts)} Points* — ${amt}\n\nSelect payment method:",
        parse_mode="Markdown", reply_markup=points_payment_keyboard(amt))
    return True


async def points_binance_callback(update, context):
    """🔶 Binance Buy Points → Order-ID flow (when API toggle ON) or legacy sender-name flow."""
    q = update.callback_query; await q.answer()
    amt = float(q.data.split("_")[2])
    pts = points_from_usd(amt)

    for k in ['ep_step','ep_amount','ep_tid','binance_step','binance_amount',
              'binance_txid','binance_product_id','binance_qty','binance_name','binance_order_id',
              'jc_step','jc_amount','jc_tid','pending_order_id']:
        context.user_data.pop(k, None)

    context.user_data['binance_amount'] = amt
    context.user_data['binance_product_id'] = None
    context.user_data['points_mode'] = True
    context.user_data['points_amount'] = amt

    # 🆕 v62: Order-ID flow when admin enabled API mode
    if get_setting("binance_api_enabled", "0") == "1":
        await _start_binance_order_id_flow(
            update, context,
            is_points=True, product=None, qty=1, amount=amt, points_amount=amt,
        )
        return

    # ── Legacy sender-name flow ──
    context.user_data['binance_step'] = 'waiting_name'
    bid = get_setting("binance_id", BINANCE_PAY_ID)
    bn_holder = get_setting("binance_name", get_setting("account_name", ACCOUNT_NAME))
    await _safe_send(q, context,
        f"🔶 *Binance Deposit*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💎 You will receive: *{fmt_points(pts)} Points*\n"
        f"💰 Amount: *{fmt_price(amt)}*\n\n"
        f"📋 *Send {fmt_price(amt)} to:*\n"
        f"• Binance Pay ID: `{bid}`\n"
        f"• Account Name: *{escape_md(bn_holder)}*\n\n"
        f"✅ *Step 1/2:* Enter your *Binance sender name* below.\n"
        f"Example: `John Doe`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))


async def points_easypaisa_callback(update, context):
    """🆕 v31: EasyPaisa Points — TID only flow"""
    q = update.callback_query; await q.answer()
    amt = float(q.data.split("_")[2])
    pts = points_from_usd(amt)
    rs_amount = amt * _pkr_rate()
    u = q.from_user
    un = u.first_name or str(u.id)
    save_user(u.id, u.username or '', u.first_name or '')

    # Clear old state
    for k in ['ep_step','ep_amount','ep_tid','binance_step','binance_amount']:
        context.user_data.pop(k, None)

    # Create pending order NOW
    oid = create_order(u.id, un, 0, f"💎 {fmt_points(pts)} Points", amt, 'easypaisa', '', rs_amount, 'PKR', 'points')
    update_order_status(oid, 'screenshot_sent')

    context.user_data['ep_product_id'] = None
    context.user_data['ep_qty'] = 1
    context.user_data['ep_step'] = 'waiting_tid'
    context.user_data['ep_points_mode'] = True
    context.user_data['ep_points_usd'] = amt
    context.user_data['ep_expected_rs'] = rs_amount
    context.user_data['pending_order_id'] = oid

    legacy_name = get_setting("account_name", ACCOUNT_NAME)
    num = get_setting("easypaisa", EASYPAISA_NUMBER)
    an = get_setting("easypaisa_name", legacy_name)

    await _safe_send(q, context,
        f"📱 *Order #{oid} — EasyPaisa Buy {fmt_points(pts)} Points*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 You will receive: *{fmt_points(pts)} Points*\n"
        f"💰 Pay: *Rs.{rs_amount:.0f}* (= ${amt})\n\n"
        f"📲 *Send Rs.{rs_amount:.0f} to:*\n"
        f"  Number: `{num}`\n"
        f"  Name: {escape_md(an)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 *Instructions:*\n"
        f"1. Send the exact amount via EasyPaisa to the number above\n"
        f"2. EasyPaisa will send you an SMS with the Transaction ID\n"
        f"3. Enter only the *Transaction ID* below.\n\n"
        f"🔢 *Enter your Transaction ID (10-13 digits):*\n"
        f"_(Find it in the EasyPaisa SMS)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))


async def points_jazzcash_callback(update, context):
    """🆕 v40.2: JazzCash Points — Auto-verify via TID."""
    q = update.callback_query; await q.answer()
    amt = float(q.data.split("_")[2])
    pts = points_from_usd(amt)
    rs_amount = amt * _pkr_rate()
    u = q.from_user
    un = u.first_name or str(u.id)
    save_user(u.id, u.username or '', u.first_name or '')

    # Clear old state
    for k in ['ep_step','ep_amount','ep_tid','binance_step','binance_amount','jc_step','jc_amount','jc_tid']:
        context.user_data.pop(k, None)

    # Create pending order
    oid = create_order(u.id, un, 0, f"💎 {fmt_points(pts)} Points", amt, 'jazzcash', '', rs_amount, 'PKR', 'points')
    update_order_status(oid, 'screenshot_sent')

    context.user_data['jc_product_id'] = None
    context.user_data['jc_qty'] = 1
    context.user_data['jc_step'] = 'waiting_tid'
    context.user_data['jc_points_mode'] = True
    context.user_data['jc_expected_rs'] = rs_amount
    context.user_data['pending_order_id'] = oid

    legacy_name = get_setting("account_name", ACCOUNT_NAME)
    num = get_setting("jazzcash", JAZZCASH_NUMBER)
    an = get_setting("jazzcash_name", legacy_name)

    await _safe_send(q, context,
        f"📱 *Order #{oid} — JazzCash Buy {fmt_points(pts)} Points*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 You will receive: *{fmt_points(pts)} Points*\n"
        f"💰 Pay: *Rs.{rs_amount:.0f}* (= ${amt})\n\n"
        f"📲 *Send Rs.{rs_amount:.0f} to:*\n"
        f"  Number: `{num}`\n"
        f"  Name: {escape_md(an)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 *Instructions:*\n"
        f"1. Send the exact amount via JazzCash to the number above\n"
        f"2. JazzCash will send you an SMS with the Transaction ID\n"
        f"3. Enter only the *Transaction ID* below.\n\n"
        f"🔢 *Enter your Transaction ID (10-15 digits):*\n"
        f"_(Find it in the JazzCash SMS)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))


# ════════════════════════════════════════════
# 📸 SCREENSHOT HANDLER (JazzCash only)
# ════════════════════════════════════════════
async def handle_screenshot(update, context):
    # 🆕 First check: DB restore upload (admin only)
    if context.user_data.get('awaiting_restore'):
        from handlers_admin import handle_db_upload
        if await handle_db_upload(update, context):
            return

    # 🆕 v30: Binance screenshot upload (auto-verify)
    if context.user_data.get('binance_step') == 'waiting_screenshot':
        if await handle_binance_screenshot(update, context):
            return

    # 🆕 v32: JazzCash screenshot upload (auto-verify)
    if context.user_data.get('jc_step') == 'waiting_screenshot':
        if await handle_jazzcash_screenshot(update, context):
            return

    # Other legacy/manual screenshot flows — but NEVER forward screenshots for
    # auto-payment orders (Binance/EasyPaisa/JazzCash/Buy Points). Those are
    # verified by Transfer Note / TXID flows and must not go to admin approval.
    pending = context.user_data.get('pending_order_id')
    if not pending:
        await update.message.reply_text("❓ No pending order. /start"); return

    o = get_order(pending)
    if o:
        pm = (o['payment_method'] or '').lower()
        otype = (o['order_type'] or '').lower() if 'order_type' in o.keys() else ''
        if pm in ('binance', 'easypaisa', 'jazzcash') or otype == 'points':
            if pm == 'binance':
                msg = (
                    f"ℹ️ *Screenshot is not required.*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Order ID: `#{pending}`\n\n"
                    f"Please follow the Binance payment instructions and enter sender name/exact amount when asked.\n"
                    f"Your payment will be confirmed here once received."
                )
            else:
                msg = (
                    f"ℹ️ *Screenshot is not required.*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Order ID: `#{pending}`\n\n"
                    f"Please send the Transaction ID as text from your payment message."
                )
            await update.message.reply_text(msg, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
            return
    fid = None
    if update.message.photo:
        fid = update.message.photo[-1].file_id
    elif update.message.document:
        doc = update.message.document
        mime = (doc.mime_type or "").lower()
        fname = (doc.file_name or "").lower()
        allowed_ext = ('.jpg', '.jpeg', '.png', '.webp')
        if not (mime.startswith('image/') or fname.endswith(allowed_ext)):
            await update.message.reply_text(
                "❌ Please send a payment screenshot as an image (JPG/PNG/WebP). "
                "Other documents are not accepted for payment verification.")
            return
        if doc.file_size and doc.file_size > 10 * 1024 * 1024:
            await update.message.reply_text("❌ Screenshot file too large (max 10 MB).")
            return
        fid = doc.file_id
    if not fid: await update.message.reply_text("📸 Send photo!"); return
    save_payment_screenshot(pending, fid)
    await update.message.reply_text(
        f"✅ Screenshot received! Order #{pending} — verifying ⏳",
        reply_markup=back_btn())
    o = get_order(pending)
    try:
        await context.bot.send_photo(
            ADMIN_ID, fid,
            caption=f"📸 #{pending} | {escape_md(o['product_name'])} | {fmt_price(o['price'])}" if o else f"#{pending}",
            parse_mode="Markdown",
            reply_markup=admin_order_keyboard(pending))
    except: pass
    context.user_data.pop('pending_order_id', None)


# ════════════════════════════════════════════
# 📜 MY ORDERS (Product History)
# ════════════════════════════════════════════
async def my_orders_callback(update, context):
    """🆕 v170: Orders screen with premium layouts - shop-like display.
    🆕 v170.5: receipt pagination support (myordspg_N)."""
    q = update.callback_query; await q.answer()
    nav_push(context, 'my_orders')
    # 🆕 v170.6: "myords_<filter>_<page>" (filter + pagination) | "myordspg_N" (old)
    page = 0
    status_filter = "all"
    try:
        _d = str(q.data or "")
        if _d.startswith("myords_"):
            parts = _d.split("_")
            status_filter = parts[1] if len(parts) > 1 else "all"
            page = max(0, int(parts[2] or 0)) if len(parts) > 2 else 0
        elif _d.startswith("myordspg_"):
            page = max(0, int(_d.replace("myordspg_", "")))
    except Exception:
        page = 0
    orders = get_user_product_orders(q.from_user.id)
    if not orders:
        await q.edit_message_text("📜 *No orders yet!*\n\nStart shopping to see your orders here.", 
                                  parse_mode="Markdown",
                                  reply_markup=back_btn(location="my_orders"))
        return
    
    # 🆕 v170: Use orders layout system with premium emojis + colored backgrounds
    try:
        from orders_layouts import render_orders
        text, buttons = render_orders(orders, q.from_user.id, page=page, page_size=8,
                                      status_filter=status_filter)
        
        # 🆕 v170.7: "Change Layout" button REMOVED (user demand) — sirf receipt layout
        # Add back button
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
        
        keyboard = InlineKeyboardMarkup(buttons)
        send_text, send_mode = smart_text_and_mode(text[:3900], "Markdown")
        await q.edit_message_text(send_text, parse_mode=send_mode, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Orders layout error: {e}")
        # Fallback to old system
        products_seen = {}
        for o in orders:
            pid = o.get('product_id') or o.get('id')
            if pid not in products_seen:
                products_seen[pid] = o
        
        text = "📦 *My Orders*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        text += f"🛍️ You have ordered *{len(products_seen)}* product(s)\n\n"
        
        rows = []
        for pid, o in list(products_seen.items())[:15]:
            pname = o.get('product_name', 'Product')
            import re as _re
            clean_name = _re.sub(r'<[^>]+>', '', pname).replace('[[HTML]]', '')
            if len(clean_name) > 40:
                clean_name = clean_name[:37] + "..."
            
            status = o.get('status', 'pending')
            s_icon = {
                'pending': '🟡', 'screenshot_sent': '📸', 'binance_waiting': '🔶',
                'usdt_waiting': '🪙', 'bybit_waiting': '🟡',
                'paid_pending_delivery': '🕒', 'waiting_for_details': '📨',
                'supplier_processing': '🔄', 'supplier_retry_pending': '🔁',
                'delivered': '✅', 'cancelled': '❌', 'rejected': '❌', 'refunded': '💎'
            }.get(status, '❓')
            
            text += f"{s_icon} *{escape_md(clean_name)}*\n"
            text += f"   Status: #{o['id']} • 💰 {fmt_price(o.get('price', 0))}\n\n"
            
            btn_text = f"📦 View Delivery #{o['id']}" if status == 'delivered' else f"🔎 View #{o['id']}"
            rows.append([InlineKeyboardButton(btn_text, callback_data=f"myord_{o['id']}")])
        
        rows.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
        
        send_text, send_mode = smart_text_and_mode(text[:3900], "Markdown")
        await q.edit_message_text(send_text, parse_mode=send_mode, reply_markup=InlineKeyboardMarkup(rows))


async def orders_layout_picker_callback(update, context):
    """🆕 v170: Show all 10 order layouts for admin to choose"""
    q = update.callback_query; await q.answer()
    
    from orders_layouts import get_all_layouts, get_orders_layout
    layouts = get_all_layouts()
    current = get_orders_layout()
    
    text = "🎨 *Orders Layout Picker*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"Current: *{layouts[current]['name']}*\n\n"
    text += "_Choose a layout to change how orders display:_\n\n"
    
    rows = []
    for layout_id, layout in layouts.items():
        marker = "✅" if layout_id == current else "  "
        rows.append([InlineKeyboardButton(
            f"{marker} {layout['name']}",
            callback_data=f"set_orders_layout_{layout_id}"
        )])
    
    rows.append([InlineKeyboardButton("🔙 Back to Orders", callback_data="my_orders")])
    
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))


async def set_orders_layout_callback(update, context):
    """🆕 v170: Set the selected orders layout"""
    q = update.callback_query; await q.answer()
    
    layout_id = q.data.replace("set_orders_layout_", "")
    
    from orders_layouts import set_orders_layout, get_all_layouts
    layouts = get_all_layouts()
    
    if layout_id in layouts:
        set_orders_layout(layout_id)
        await q.answer(f"✅ Layout changed to {layouts[layout_id]['name']}", show_alert=True)
        
        # Go back to orders screen
        from handlers_order import my_orders_callback
        await my_orders_callback(update, context)
    else:
        await q.answer("❌ Invalid layout", show_alert=True)



async def my_order_detail_callback(update, context):
    q = update.callback_query
    await q.answer()
    try:
        oid = int(q.data.replace('myord_', ''))
    except Exception:
        await q.answer("Invalid order", show_alert=True); return
    o = get_order(oid)
    if not o or o['user_id'] != q.from_user.id:
        await q.answer("Order not found", show_alert=True); return
    p = get_product(o['product_id']) if o['product_id'] else None
    pd = dict(p) if p else {}
    status = o['status']
    content = (dict(o).get('delivery_content') if o else '') or ''
    # 🐛 v104: heal legacy escaped <tg-emoji> markup so purani orders
    # bhi clean render hon (see utils.heal_escaped_delivery_content)
    try:
        from utils import heal_escaped_delivery_content
        content = heal_escaped_delivery_content(content)
    except Exception:
        pass
    has_file = bool(pd.get('delivery_file_id'))
    text = (
        f"📦 *Order #{oid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 Product: *{_fmt_msg_name(o['product_name'])}*\n"
        f"💰 Price: *{fmt_price(float(o['price'] or 0))}*\n"
        f"💳 Payment: *{escape_md(o['payment_method'] or 'N/A')}*\n"
        f"📊 Status: *{escape_md(status)}*\n\n"
    )
    # 🆕 v142: Better order tracking timeline
    tracking_map = {
        'pending': [('Order created','✅'), ('Payment','⏳'), ('Delivery','▫️')],
        'binance_waiting': [('Order created','✅'), ('Payment verification','⏳'), ('Delivery','▫️')],
        'usdt_waiting': [('Order created','✅'), ('USDT blockchain confirmation','⏳'), ('Delivery','▫️')],
        'bybit_waiting': [('Order created','✅'), ('Bybit payment verification','⏳'), ('Delivery','▫️')],
        'screenshot_sent': [('Order created','✅'), ('Screenshot received','📸'), ('Delivery','▫️')],
        'supplier_processing': [('Payment verified','✅'), ('Supplier processing','🔄'), ('Delivery','⏳')],
        'supplier_retry_pending': [('Payment verified','✅'), ('Retrying delivery','🔁'), ('Auto-refund safety','⏳')],
        'paid_pending_delivery': [('Payment verified','✅'), ('Manual delivery','⏳'), ('Completed','▫️')],
        'delivered': [('Payment verified','✅'), ('Delivery','✅'), ('Completed','✅')],
        'refunded': [('Payment verified','✅'), ('Delivery unavailable','⚠️'), ('Refunded','💎')],
        'cancelled': [('Order','❌'), ('Payment','▫️'), ('Delivery','▫️')],
        'rejected': [('Order','❌'), ('Payment','▫️'), ('Delivery','▫️')],
    }
    steps = tracking_map.get(status, [('Order status', 'ℹ️')])
    text += "🧭 *Tracking:*\n" + "\n".join(f"{icon} {escape_md(label)}" for label, icon in steps) + "\n\n"
    rows = []
    if status == 'supplier_retry_pending':
        text += (
            "🔁 Supplier retry window is active. If delivery is not completed soon, "
            "your wallet will be automatically refunded.\n\n"
        )
    if status == 'delivered':
        if has_file:
            text += "📎 Your delivery contains a file/media item. Tap the button below to resend it.\n"
            rows.append([InlineKeyboardButton("📎 Resend Delivery File", callback_data=f"myord_resend_{oid}")])
        elif content:
            # 🐛 v100 FIX: delivery_content may already be v83-rendered HTML
            # (starts with [[HTML]] or contains <b>/<code>/<tg-emoji> tags).
            # Escaping with escape_md() showed raw HTML tags to customers.
            # Detect + branch: HTML → embed raw (smart_text_and_mode auto-flips
            # parse_mode to HTML). Plain text → escape for Markdown.
            import re as _re
            _content_trimmed = content[:2500]
            _is_html_content = (_content_trimmed.startswith("[[HTML]]") or
                                 _re.search(r"<(?:b|i|u|s|code|pre|tg-emoji|a)\b",
                                            _content_trimmed, flags=_re.I))
            if _is_html_content:
                # Strip sentinel and embed as raw HTML (existing markup wins)
                _clean = _content_trimmed[len("[[HTML]]"):] if _content_trimmed.startswith("[[HTML]]") else _content_trimmed
                text += "📨 *Delivery Details:*\n━━━━━━━━━━━━━━━━━━━━\n" + _clean + "\n"
            else:
                text += f"📨 *Delivery Details:*\n━━━━━━━━━━━━━━━━━━━━\n{escape_md(_content_trimmed)}\n"
        else:
            text += "✅ This order is delivered. Delivery details are not stored as text.\n"
    elif status == 'waiting_for_details':
        text += "📨 We are waiting for the required account details from you. Please send them in this chat.\n"
    elif status == 'paid_pending_delivery':
        text += "🕒 Payment confirmed. The store owner will complete your order soon.\n"
    else:
        text += "⏳ This order is not delivered yet.\n"
    # 🆕 v71: Replacement button if eligible
    try:
        from support_replacement import get_replacement_button
        _rep_btn = get_replacement_button(dict(o) if o else None)
        if _rep_btn is not None:
            rows.append([_rep_btn])
    except Exception: pass
    rows.append([InlineKeyboardButton("📜 Back to Order History", callback_data="my_orders")])
    rows.append([InlineKeyboardButton("🛒 Buy More", callback_data="shop")])
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    await q.edit_message_text(send_text, parse_mode=send_mode, reply_markup=InlineKeyboardMarkup(rows))


async def my_order_resend_callback(update, context):
    q = update.callback_query
    await q.answer("Sending delivery file...", show_alert=False)
    try:
        oid = int(q.data.replace('myord_resend_', ''))
    except Exception:
        await q.answer("Invalid order", show_alert=True); return
    o = get_order(oid)
    if not o or o['user_id'] != q.from_user.id:
        await q.answer("Order not found", show_alert=True); return
    if o['status'] != 'delivered':
        await q.answer("Order is not delivered yet", show_alert=True); return
    p = get_product(o['product_id']) if o['product_id'] else None
    pd = dict(p) if p else {}
    file_id = pd.get('delivery_file_id', '') or ''
    if not file_id:
        await q.answer("No delivery file saved for this order", show_alert=True); return
    file_type = pd.get('delivery_file_type', '') or 'document'
    caption = (
        f"📎 *Delivery File Resent*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Order ID: `#{oid}`\n"
        f"Product: *{_fmt_msg_name(o['product_name'])}*"
    )
    send_text, send_mode = smart_text_and_mode(caption, "Markdown")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📜 Order History", callback_data="my_orders")]])
    try:
        if file_type == 'photo':
            await context.bot.send_photo(q.from_user.id, file_id, caption=send_text[:1024], parse_mode=send_mode, reply_markup=kb)
        elif file_type == 'video':
            await context.bot.send_video(q.from_user.id, file_id, caption=send_text[:1024], parse_mode=send_mode, reply_markup=kb)
        else:
            await context.bot.send_document(q.from_user.id, file_id, caption=send_text[:1024], parse_mode=send_mode, reply_markup=kb)
    except Exception as e:
        await q.answer("Could not resend file. Contact support.", show_alert=True)


# ════════════════════════════════════════════
# ❌ CANCEL ORDER
# ════════════════════════════════════════════
async def cancel_pending_order_callback(update, context):
    """❌ User taps Cancel Payment — marks order cancelled + cleans state"""
    q = update.callback_query
    await q.answer("Cancelled ❌", show_alert=False)
    pending_oid = context.user_data.get('pending_order_id')
    cancelled_msg = "❌ *Cancelled.*\n\nReturned to main menu."
    if pending_oid:
        try:
            update_order_status(pending_oid, 'cancelled')
            o = get_order(pending_oid)
            if o:
                cancelled_msg = f"❌ *Order #{pending_oid} Cancelled.*\n\nMarked as canceled in your transaction history."
                if q.from_user.id != ADMIN_ID:
                    try:
                        await context.bot.send_message(
                            ADMIN_ID,
                            f"❌ *Order Cancelled by User*\n"
                            f"#{pending_oid} | {escape_md(o['user_name'])} | "
                            f"{escape_md(o['product_name'])} | {fmt_price(o['price'])}",
                            parse_mode="Markdown")
                    except: pass
        except: pass
    # Clean ALL state
    for k in ['pending_order_id',
              'binance_step','binance_product_id','binance_name','binance_amount','binance_qty','binance_txid',
              'points_mode','points_step','points_amount',
              'ep_step','ep_amount','ep_tid','ep_product_id','ep_qty','ep_points_mode','ep_points_usd','ep_expected_rs',
              'jc_step','jc_amount','jc_product_id','jc_qty','jc_points_mode','jc_expected_rs',
              'screenshot_file_id','shop_page','carousel_idx','bulk_step','bulk_product_id']:
        context.user_data.pop(k, None)
    from keyboards import main_menu_keyboard
    try:
        await q.edit_message_text(
            cancelled_msg, parse_mode="Markdown",
            reply_markup=main_menu_keyboard(q.from_user.id == ADMIN_ID, user_id=q.from_user.id))
    except Exception:
        try: await q.message.delete()
        except: pass
        await context.bot.send_message(
            q.from_user.id, cancelled_msg, parse_mode="Markdown",
            reply_markup=main_menu_keyboard(q.from_user.id == ADMIN_ID, user_id=q.from_user.id))


# ════════════════════════════════════════════
# 📱 JAZZCASH AUTO-VERIFY via TID (v40.2)
# ════════════════════════════════════════════
# Screenshot flow removed — JazzCash now uses TID-only flow (same UX as EasyPaisa).

async def handle_jazzcash_screenshot(update, context):
    """🆕 v40.2: Screenshot flow disabled. Tell user to enter TID instead."""
    if context.user_data.get('jc_step') not in ('waiting_screenshot', 'screenshot_uploaded'):
        return False
    # Migrate to TID flow
    context.user_data['jc_step'] = 'waiting_tid'
    oid = context.user_data.get('pending_order_id')
    expected_rs = context.user_data.get('jc_expected_rs', 0)
    await update.message.reply_text(
        f"📝 *Please enter your Transaction ID instead.*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Order #{oid} | Expected: Rs.{expected_rs:.0f}\n\n"
        f"🔢 Type the *Transaction ID* (10-15 digits) from your JazzCash SMS.\n\n"
        f"Your payment is being processed.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
    return True


async def jc_reupload_callback(update, context):
    """🆕 v40.2: Legacy callback — redirect to TID entry."""
    q = update.callback_query
    await q.answer()
    context.user_data['jc_step'] = 'waiting_tid'
    context.user_data.pop('screenshot_file_id', None)
    oid = context.user_data.get('pending_order_id', '?')
    await q.edit_message_text(
        f"📝 *Enter your Transaction ID*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Order #{oid}\n\n"
        f"🔢 Type the *Transaction ID* (10-15 digits) from your JazzCash SMS.\n\n"
        f"Your payment is being processed.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))


async def jc_tid_received(update, context):
    """🆕 v40.2: User entered JazzCash TID → save + show Verify button.
    Same UX as EasyPaisa — backend verification is hidden from user."""
    if context.user_data.get('jc_step') != 'waiting_tid':
        return False
    tid = update.message.text.strip()
    digits_only = re.sub(r'\D', '', tid)
    # Accept 10-15 digit TIDs (JazzCash formats vary)
    if not (10 <= len(digits_only) <= 15):
        await update.message.reply_text(
            f"❌ Transaction ID must be *10-15 digits*.\nYou entered: {len(digits_only)} digits.\n_Check your JazzCash SMS and try again._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]]))
        return True

    # Anti-fraud check
    from database import is_txid_used, get_txid_record, update_order_txid
    if is_txid_used(digits_only):
        rec = get_txid_record(digits_only)
        await update.message.reply_text(
            f"❌ *This Transaction ID has already been used.*\n\nEach payment can only be used once.\n\n"
            f"_Used at: {rec['verified_at'][:16] if rec else 'unknown'}_",
            parse_mode="Markdown", reply_markup=back_btn())
        for k in ['jc_step','jc_amount','jc_tid','jc_product_id','jc_qty','jc_points_mode','jc_expected_rs','pending_order_id']:
            context.user_data.pop(k, None)
        return True

    # Save TID on order
    oid = context.user_data.get('pending_order_id')
    if oid:
        update_order_txid(oid, digits_only)

    context.user_data['jc_tid'] = digits_only
    context.user_data['jc_step'] = 'awaiting_verify'

    expected_rs = context.user_data.get('jc_expected_rs', 0)

    # Buy Points: process immediately after TXID. Product order flow remains for Step 2.
    if context.user_data.get('jc_points_mode'):
        await _process_points_tid_payment(update, context, oid, platform='jazzcash', callback_prefix='jcv')
        return True

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Check Again", callback_data=f"jcv_{oid}")],
        [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
    ])
    await update.message.reply_text(
        f"🔢 *Transaction ID Received:* `{digits_only}` ✅\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 Order #{oid}\n"
        f"💰 Expected: *Rs.{expected_rs:.0f}*\n\n"
        f"⏳ Your payment is being processed. Tap *Check Again* after 2 minutes.",
        parse_mode="Markdown", reply_markup=kb)

    # Notify admin (internal — backend tech kept hidden from user)
    try:
        u = update.effective_user
        await context.bot.send_message(
            ADMIN_ID,
            f"📱 *New JazzCash Order #{oid}*\n"
            f"User: {escape_md(u.first_name or 'N/A')} (`{u.id}`)\n"
            f"TID: `{digits_only}`\n"
            f"Expected: Rs.{expected_rs:.0f}",
            parse_mode="Markdown")
    except: pass
    return True


async def jc_verify_callback(update, context):
    """🆕 v40.2: User tapped 'Verify Payment' for JazzCash → TID-based auto-verify.
    Same UX pattern as EasyPaisa. All backend tech (email lookup, etc.)
    is hidden from the user — only professional, friendly messages."""
    q = update.callback_query
    user_id = q.from_user.id
    try:
        oid = int(q.data.replace("jcv_", ""))
    except ValueError:
        await q.answer("Invalid order", show_alert=True)
        return

    # ⏱️ Cooldown
    remaining = _get_remaining_cooldown(user_id, oid)
    if remaining > 0:
        await q.answer(
            f"⏱️ Please wait {remaining} seconds before checking again.",
            show_alert=True)
        return

    await q.answer("⏳ Processing payment...", show_alert=False)
    o = get_order(oid)
    if not o:
        await q.edit_message_text("❌ Order not found.", reply_markup=back_btn())
        return
    if o['status'] == 'delivered':
        await q.edit_message_text(
            "✅ *Already Confirmed!*\n\nYour points/order has already been processed.",
            parse_mode="Markdown", reply_markup=back_btn())
        return

    if _is_points_order(o):
        _set_cooldown(user_id, oid)
        await _process_points_tid_payment(q, context, oid, platform='jazzcash', callback_prefix='jcv')
        return

    # ⏱️ Set cooldown
    _set_cooldown(user_id, oid)

    tid = o['binance_txid'] if 'binance_txid' in o.keys() else ''
    expected_rs = o['binance_amount']

    if not tid:
        await q.edit_message_text(
            "❌ No Transaction ID found for this order.",
            reply_markup=back_btn())
        return

    try:
        await _safe_send(q, context,
            f"⏳ *Processing payment...*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Order #{oid} | TID: `{tid}`\n\n"
            f"_Please wait a few seconds._",
            parse_mode="Markdown")
    except: pass

    # 🆕 v40.2: Use JazzCash API (Gmail-based, but user never sees that)
    from payments import jazzcash_verify_by_tid_only
    api_result = jazzcash_verify_by_tid_only(tid)

    # Build unified result
    result = {'success': False,
              'status': api_result.get('status', 'error'),
              'reason': api_result.get('reason', ''),
              'amount': api_result.get('amount', 0),
              'name': api_result.get('name', '')}

    # Amount validation if found
    if api_result.get('success'):
        actual_rs = api_result.get('amount', 0)
        if abs(actual_rs - expected_rs) > 5:
            result['status'] = 'amount_mismatch'
            result['reason'] = (
                f"Amount does not match.\n"
                f"Expected: Rs.{expected_rs:.0f}\n"
                f"Received: Rs.{actual_rs:.0f}\n\n"
                f"Please send the exact amount."
            )
        else:
            ptype = api_result.get('type', '')
            if ptype == 'sent':
                result['status'] = 'wrong_direction'
                result['reason'] = (
                    "This Transaction ID is for a payment sent FROM our account.\n"
                    "Please use the Transaction ID from your own payment SMS."
                )
            else:
                result['success'] = True
                result['status'] = 'matched'

    if result['success']:
        from database import mark_txid_used, decrease_stock, add_points
        actual_rs = result.get('amount', expected_rs)
        sender_name = result.get('name', '')
        mark_txid_used(tid, o['user_id'], oid, actual_rs, 'PKR')
        if not _is_points_order(o):
            await fulfill_paid_product_order(context.bot, o, actual_rs, payment_method_label='JazzCash')
            for k in ['jc_step','jc_amount','jc_tid','jc_product_id','jc_qty','jc_points_mode','jc_expected_rs','pending_order_id','screenshot_file_id']:
                context.user_data.pop(k, None)
            return
        update_order_status(oid, 'delivered')

        is_points = ((o['order_type'] if 'order_type' in o.keys() and o['order_type'] else 'product') == 'points' or
                     (not o['product_id'] and 'Points' in (o['product_name'] or '')))
        if is_points:
            pts = _points_from_order_name(o)
            if pts > 0: add_points(o['user_id'], pts, tx_type='deposit', description='Points deposit', event_id=f"points_order_{oid}", order_id=oid)
            msg = (f"🎉 *Payment Verified!* ✅\n━━━━━━━━━━━━━━━━━━━━\n\n"
                   f"💎 *{fmt_points(pts)} Points* added to your account!\n\n"
                   f"💰 Amount: Rs.{actual_rs:.0f}\n"
                   + (f"👤 From: {sender_name}\n" if sender_name else "")
                   + f"🔢 TID: `{tid}`\n\nThank you! 🙏")
        else:
            order_qty = 1
            qm = re.search(r'×\s*(\d+)$', o['product_name'] or '')
            if qm: order_qty = int(qm.group(1))
            
            p = get_product(o['product_id'])
            is_manual = (dict(p) if p else {}).get('delivery_mode') == 'manual'
            pts_bonus = points_from_usd(o['price'])
            
            if is_manual:
                req_type = (dict(p) if p else {}).get('req_account_type', 'none')
                if req_type == 'none':
                    update_order_status(oid, 'paid_pending_delivery')
                    msg = f"✅ Payment verified!\n\nYour order request has been sent to the store owner. In 1 to 3 hours, as soon as the owner is online, your order will be completed."
                    if (dict(p) if p else {}).get('delivery_text'):
                        msg += f"\n\n📝 *Instructions:*\n{p['delivery_text']}"
                    admin_msg = f"🔔 *New Order! (Readymade)*\nOrder #{oid}\nProduct: {p['name']}\n\nPlease deliver the account."
                    from config import ADMIN_ID
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton
                    try: await context.bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Upload Account", callback_data=f"adm_upacct_{oid}")]]))
                    except: pass
                else:
                    update_order_status(oid, 'waiting_for_details')
                    msg = f"✅ Payment verified!\n\nPlease provide the required details to process your order."
                    context.user_data['ownmail_oid'] = oid
                    context.user_data['ownmail_qty'] = order_qty
                    context.user_data['ownmail_step'] = 'email'
                    pt1 = 'Fresh Gmail' if req_type=='fresh_gmail' else ('Gmail' if req_type=='any_gmail' else 'Email Address')
                    prompt = f"📝 *Please enter your {pt1}*\n"
                    if order_qty > 1: prompt += "_(Send one per line)_"
                    try: await context.bot.send_message(o['user_id'] if (o is not None and 'user_id' in o.keys()) else u.id, prompt, parse_mode="Markdown")
                    except: pass
            else:
                # 🔧 AUDIT-FIX C1/C2 (2026-07-31): structured result — never mark
                # 'delivered' when the stock pool couldn't cover the full qty.
                from database import build_delivery_detailed
                _dres = build_delivery_detailed(o['product_id'], o['id'], order_qty, o['user_id'])
                delivery = _dres['text']
                # 🆕 v66: bonus 10pts removed
                # 🆕 v72: byte-perfect — receipt header (Markdown) + delivery
                # content (HTML, native format) sent as 2 separate messages so
                # neither parse mode mangles the other.
                if _dres['ok']:
                    update_order_status(oid, 'delivered')
                    msg = (f"🎉 *Order Delivered!* ✅\n━━━━━━━━━━━━━━━━━━━━\n\n"
                           f"📦 {escape_md(o['product_name'])}\n\n"
                           f"📨 *Your Product* — see the next message.\n\n"
                           f"Thank you! 🙏")
                    # Send the delivery content separately, with no parse_mode
                    # override so smart_text_and_mode picks HTML for [[HTML]] sentinel
                    try:
                        await context.bot.send_message(o['user_id'], delivery)
                    except Exception:
                        pass
                    # v121: Tier progress hint only. No extra points on payment success.
                    try:
                        from loyalty_extras import build_tier_progress_line
                        tline = build_tier_progress_line(o['user_id'])
                        if tline:
                            msg += f"\n\n{tline}"
                    except Exception: pass
                else:
                    _got, _want = _dres.get('delivered', 0), _dres.get('requested', order_qty)
                    update_order_status(oid, 'paid_pending_delivery')
                    msg = (f"⚠️ *Order #{oid} — not fully delivered*\n"
                           f"━━━━━━━━━━━━━━━━━━━━\n\n"
                           f"📦 {escape_md(o['product_name'])}\n"
                           f"🔢 Requested: *{_want}* · Delivered: *{_got}*\n\n"
                           f"The product ran out of stock while your order was "
                           f"processing. Your order is in *Pending Delivery* — "
                           f"the remaining items will be completed or refunded.")
                    if delivery and _got:
                        try:
                            await context.bot.send_message(o['user_id'], delivery)
                        except Exception:
                            pass
                    try:
                        from utils import notify_admin as _na
                        await _na(context.bot,
                            f"🚨 *Order #{oid} — partially delivered (OOS)*\n"
                            f"🔢 Requested: `{_want}` · Delivered: `{_got}`\n"
                            f"📦 Product: {escape_md(str(o.get('product_name') or '?')[:70])}\n"
                            f"👤 Customer: `{o['user_id']}`\n\n"
                            f"Complete the shortfall via *Pending Manual Delivery* or refund.")
                    except Exception:
                        pass

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 My Account", callback_data="my_account")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ])
        await q.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)
        try:
            await context.bot.send_message(ADMIN_ID,
                f"✅ JazzCash Auto-Verified!\n#{oid} | User: `{o['user_id']}`\n"
                f"Rs.{actual_rs:.0f} from {sender_name or 'unknown'}\nTID: `{tid}`",
                parse_mode="Markdown")
        except: pass
        for k in ['jc_step','jc_amount','jc_tid','jc_product_id','jc_qty','jc_points_mode','jc_expected_rs','pending_order_id','screenshot_file_id']:
            context.user_data.pop(k, None)
        return

    # ── FAILED ──
    status = result.get('status', 'error')
    reason = result.get('reason', 'Verification failed. Please try again in 2 minutes.')

    cooldown = _get_remaining_cooldown(user_id, oid)
    btn_label = _verify_button_label(cooldown)

    if status == 'duplicate':
        update_order_status(oid, 'rejected')
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
        text = (f"❌ *Duplicate Transaction ID*\n━━━━━━━━━━━━━━━━━━━━\n\n{reason}\n\n"
                f"Order rejected.")
        await _safe_send(q, context, text, parse_mode="Markdown", reply_markup=kb)

    elif status == 'wrong_direction':
        update_order_status(oid, 'rejected')
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
        text = f"❌ *Wrong Payment Direction*\n━━━━━━━━━━━━━━━━━━━━\n\n{reason}"
        await _safe_send(q, context, text, parse_mode="Markdown", reply_markup=kb)

    elif status == 'amount_mismatch':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_label, callback_data=f"jcv_{oid}")],
            [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
        ])
        text = f"❌ *Amount Mismatch*\n━━━━━━━━━━━━━━━━━━━━\n\n{reason}"
        await _safe_send(q, context, text, parse_mode="Markdown", reply_markup=kb)

    elif status in ('tid_not_found', 'no_emails'):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_label, callback_data=f"jcv_{oid}")],
            [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ])
        text = (f"⏳ *Payment Not Found Yet*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Sometimes it takes a few minutes to process.\n\n"
                f"*Please try again in 2 minutes.*\n\n"
                f"If it still doesn't work:\n"
                f"• Double-check the Transaction ID is correct\n"
                f"• Make sure the payment was sent to our account\n"
                f"• Make sure you sent the exact amount")
        await _safe_send(q, context, text, parse_mode="Markdown", reply_markup=kb)

    elif status == 'invalid_tid':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
        ])
        text = f"❌ *Invalid Transaction ID*\n━━━━━━━━━━━━━━━━━━━━\n\n{reason}"
        await _safe_send(q, context, text, parse_mode="Markdown", reply_markup=kb)

    elif status == 'imap_error':
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_label, callback_data=f"jcv_{oid}")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ])
        text = (f"⚠️ *Service Temporarily Unavailable*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Payment verification is taking longer than usual.\n\n"
                f"*Please try again in 2 minutes.*")
        await _safe_send(q, context, text, parse_mode="Markdown", reply_markup=kb)

    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_label, callback_data=f"jcv_{oid}")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ])
        text = (f"⚠️ *Verification Failed*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Please try again in 2 minutes.\n\n"
                f"If the issue persists, contact support.")
        await _safe_send(q, context, text, parse_mode="Markdown", reply_markup=kb)


async def _co_send(q, update, context, text, **kwargs):
    """Send a checkout message whether we came from a callback (q) or a
    plain text message (q is None, e.g. the bulk-quantity flow)."""
    if q is not None:
        await _safe_send(q, context, text, **kwargs)
    else:
        send_text, send_mode = smart_text_and_mode(text, kwargs.get("parse_mode", "Markdown"))
        send_kwargs = dict(kwargs)
        send_kwargs["parse_mode"] = send_mode
        await update.message.reply_text(send_text, **send_kwargs)

async def _process_checkout_checks(q, update, context, p, qty):
    # Manual account/customer details are collected AFTER payment confirmation.
    # This keeps checkout simple and avoids asking for emails/passwords before payment.
    return True


async def ord_fresh_yes_callback(update, context):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")
    pid = int(parts[3])
    qty = int(parts[4])
    p = get_product(pid)
    
    req_type = (dict(p) if p else {}).get('req_account_type', 'none')
    if req_type != 'none':
        await _prompt_for_email(q, update, context, p, qty)
    else:
        await _show_payment_screen(q, context, p, qty)

async def _prompt_for_email(q, update, context, p, qty):
    req_type = (dict(p) if p else {}).get('req_account_type', 'none')
    context.user_data['order_req_step'] = 'waiting_email'
    context.user_data['order_req_pid'] = p['id']
    context.user_data['order_req_qty'] = qty
    
    msg = f"🛒 *{_fmt_msg_name(p['name'])}*\n\n"
    if qty > 1:
        msg += f"📝 *Please reply with {qty} Emails (one per line)*\n"
    else:
        msg += f"📝 *Please reply with your Email Address*\n"
        
    if 'gmail' in req_type:
        msg += f"_Must be @gmail.com_\n"
        
    await _co_send(q, update, context, msg, parse_mode="Markdown", reply_markup=cancel_back_btn())




async def order_email_received(update, context):
    txt = update.message.text.strip()
    pid = context.user_data.get('order_req_pid')
    qty = context.user_data.get('order_req_qty', 1)
    p = get_product(pid)
    if not p: return True
    
    req_type = (dict(p) if p else {}).get('req_account_type', 'none')
    
    lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
    if len(lines) < qty:
        await update.message.reply_text(f"❌ You ordered {qty} but provided {len(lines)} lines! Please provide {qty} lines.")
        return True
        
    for i, ln in enumerate(lines[:qty]):
        if 'gmail' in req_type and '@gmail.com' not in ln.lower():
            await update.message.reply_text(f"❌ Line {i+1} must be a Gmail account! Please send a valid Gmail.")
            return True
            
    context.user_data['order_emails'] = lines[:qty]
    
    if req_type == 'gmail_and_pass':
        context.user_data['order_req_step'] = 'waiting_pass'
        msg = f"🔑 *Now please reply with the Password(s) for the email(s) provided.*\n"
        if qty > 1:
            msg += "_(One password per line, in the same order)_\n"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=cancel_back_btn())
    else:
        context.user_data['order_creds'] = "\n".join(lines[:qty])
        context.user_data.pop('order_req_step', None)
        await _show_payment_screen(None, context, p, qty, update=update)
        
    return True

async def order_pass_received(update, context):
    txt = update.message.text.strip()
    pid = context.user_data.get('order_req_pid')
    qty = context.user_data.get('order_req_qty', 1)
    p = get_product(pid)
    
    lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
    if len(lines) < qty:
        await update.message.reply_text(f"❌ You provided {len(lines)} lines of passwords, but need {qty}.")
        return True
        
    emails = context.user_data.get('order_emails', [])
    creds = []
    for i in range(qty):
        creds.append(f"{emails[i]} | {lines[i]}")
        
    context.user_data['order_creds'] = "\n".join(creds)
    context.user_data.pop('order_req_step', None)
    context.user_data.pop('order_emails', None)
    
    await _show_payment_screen(None, context, p, qty, update=update)
    return True

async def open_checkout_direct(bot, user_id, product_id):
    """🐛 v147 FIX (Bug7): open a product's CHECKOUT (payment-method screen)
    directly in a user's private chat — used by broadcast buttons with the
    `https://t.me/<bot>?start=chk_<pid>` deep link."""
    try:
        from database import get_product
        from utils import smart_text_and_mode, format_pkr, contains_premium_markup
        p = get_product(int(product_id))
        if not p:
            return False
        d = dict(p)
        if int(d.get('is_active', 1) or 1) != 1:
            return False
        try:
            from database import is_product_hidden
            if is_product_hidden(int(product_id)):
                return False
        except Exception:
            pass
        stock = int(d.get('stock') or 0)
        manual = d.get('delivery_mode') == 'manual'
        if not manual and stock <= 0:
            return False
        qty = 1
        total = _get_price_for_qty(p, qty) * qty
        pkr = format_pkr(total, _pkr_rate())
        msg = (
            f"🛒 *Confirm Purchase*\n━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 *{_fmt_msg_name(d.get('name',''))}*\n"
            f"🔢 Quantity: *{qty}*\n"
            f"💰 Total: *${total:.2f}* ≈ *{pkr}*\n\n"
            f"Select payment method:"
        )
        send_text, send_mode = smart_text_and_mode(msg, "Markdown")
        kb = payment_method_keyboard(int(product_id), qty)
        await bot.send_message(chat_id=user_id, text=send_text,
                               parse_mode=send_mode, reply_markup=kb)
        return True
    except Exception:
        return False


async def _show_payment_screen(q, context, p, qty, update=None):
    total_price = _get_price_for_qty(p, qty) * qty
    pkr = format_pkr(total_price, _pkr_rate())
    
    is_manual = (dict(p) if p else {}).get('delivery_mode') == 'manual'
    req_type = (dict(p) if p else {}).get('req_account_type', 'none')
    req_pass = (dict(p) if p else {}).get('req_password', 0)
    
    msg = f"🛒 *Confirm Purchase*\n━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📦 *{_fmt_msg_name(p['name'])}*\n"
    msg += f"🔢 Quantity: *{qty}*\n"
    msg += f"💰 Total: *${total_price:.2f}* ≈ *{pkr}*\n\n"
    
    if is_manual and req_type != 'none':
        msg += f"⚠️ *Requirements for this order:*\n"
        msg += f"• You will need to provide: *{'Fresh Gmail' if req_type=='fresh_gmail' else ('Gmail' if req_type=='any_gmail' else 'Any Email')}*\n"
        if req_pass:
            msg += f"• You will need to provide: *Password*\n"
        msg += f"_(You will be asked to enter these details AFTER payment)_\n\n"
        
    msg += f"Select payment method:" 
    
    if update:
        send_text, send_mode = smart_text_and_mode(msg, "Markdown")
        await update.message.reply_text(send_text, parse_mode=send_mode, reply_markup=payment_method_keyboard(p['id'], qty))
    else:
        await _safe_send(q, context, msg, parse_mode="Markdown", reply_markup=payment_method_keyboard(p['id'], qty))


# ════════════════════════════════════════════
# 📧 POST-PAYMENT OWN MAIL / FRESH GMAIL DETAILS
# ════════════════════════════════════════════
_DETAILS_PREFIX = "DETAILS_JSON:"


def _load_detail_state(raw):
    raw = str(raw or '')
    if raw.startswith(_DETAILS_PREFIX):
        try:
            return json.loads(raw[len(_DETAILS_PREFIX):])
        except Exception:
            return {}
    return {}


def _save_detail_state(oid, data):
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE orders SET customer_credentials=? WHERE id=?", (_DETAILS_PREFIX + json.dumps(data), oid))
    conn.commit(); conn.close()


def _clear_detail_state(oid):
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE orders SET customer_credentials='' WHERE id=?", (oid,))
    conn.commit(); conn.close()


def _format_customer_credentials(emails, passwords=None):
    passwords = passwords or []
    out = []
    for i, email in enumerate(emails):
        if i < len(passwords) and passwords[i]:
            out.append(f"Email: {email}\nPassword: {passwords[i]}")
        else:
            out.append(f"Email: {email}")
    return "\n\n".join(out)


def _manual_detail_label(req_type):
    if req_type == 'fresh_gmail':
        return 'fresh Gmail address'
    if req_type == 'any_gmail':
        return 'Gmail address'
    return 'email address'


def _find_waiting_manual_details_order(uid):
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT * FROM orders
        WHERE user_id=? AND status='waiting_for_details' AND order_type='product'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    """, (uid,))
    row = c.fetchone(); conn.close(); return row


async def _send_manual_email_prompt(bot, user_id, order, product, qty=None, retry=False):
    pd = dict(product) if product else {}
    req_type = pd.get('req_account_type', 'none') or 'none'
    req_pass = bool(pd.get('req_password', 0))
    qty = qty or _order_qty_from_name(order['product_name'])
    label = _manual_detail_label(req_type)
    text = (
        f"✅ *Payment Confirmed!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Product: *{_fmt_msg_name(order['product_name'])}*\n"
        f"🧾 Order ID: `#{order['id']}`\n\n"
    )
    if retry:
        text += "❌ The previous email was not confirmed as fresh.\nPlease send a fresh Gmail address this time.\n\n"
    text += f"This product requires your own {label} for activation.\n"
    if qty > 1:
        text += f"Please send *{qty} {label}s*, one per line.\n"
    else:
        text += f"Please send your *{label}*.\n"
    if 'gmail' in req_type:
        text += "\nThe address must end with `@gmail.com`."
    if req_pass:
        text += "\nAfter that, I will ask for the password."
    await _bot_send_smart(bot, user_id, text, parse_mode="Markdown",
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎫 Support", callback_data="support_menu")], [InlineKeyboardButton("📜 Order History", callback_data="my_orders")]]))


async def _begin_manual_details_after_payment(bot, order, product, method_label='Payment'):
    """Start post-payment email/password collection for manual own-mail products."""
    update_order_status(order['id'], 'waiting_for_details')
    _clear_detail_state(order['id'])
    qty = _order_qty_from_name(order['product_name'])
    await _send_manual_email_prompt(bot, order['user_id'], order, product, qty=qty)
    try:
        await _bot_send_smart(
            bot,
            ADMIN_ID,
            f"📨 *Waiting for Customer Details*\n━━━━━━━━━━━━━━━━━━━━\n"
            f"Order: `#{order['id']}`\n"
            f"Customer: {escape_md(order['user_name'])} (`{order['user_id']}`)\n"
            f"Product: *{_fmt_msg_name(order['product_name'])}*\n"
            f"Payment: *{escape_md(method_label)}*\n\n"
            f"The customer has been asked to send required account details.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Chat Customer", callback_data=f"adm_chat_{order['user_id']}")]])
        )
    except Exception:
        pass


async def _ask_fresh_confirmation(update, oid):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, it is fresh", callback_data=f"ownmail_fresh_yes_{oid}")],
        [InlineKeyboardButton("❌ No, I will send another", callback_data=f"ownmail_fresh_no_{oid}")],
    ])
    await update.message.reply_text(
        "🌱 *Fresh Gmail Confirmation*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Is the Gmail address you provided completely fresh and unused for this activation?",
        parse_mode="Markdown", reply_markup=kb)


async def _finalize_ownmail_details(update, context, order, product, emails, passwords=None):
    oid = order['id']
    creds_text = _format_customer_credentials(emails, passwords)
    update_order_status(oid, 'paid_pending_delivery')
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE orders SET customer_credentials=? WHERE id=?", (creds_text, oid))
    conn.commit(); conn.close()

    # Clear state
    for k in ['ownmail_step','ownmail_oid','ownmail_qty','ownmail_emails','ownmail_passwords']:
        context.user_data.pop(k, None)

    customer_msg = (
        f"✅ *Order Confirmed!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Product: *{_fmt_msg_name(order['product_name'])}*\n"
        f"🧾 Order ID: `#{oid}`\n\n"
        f"Your order details have been sent to the Bite Store owner.\n"
        f"Your product will be completed within *1–5 hours*.\n\n"
        f"If no one contacts you within 5 hours, please create a support ticket for fast order completion."
    )
    send_text, send_mode = smart_text_and_mode(customer_msg, "Markdown")
    await update.message.reply_text(send_text, parse_mode=send_mode,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎫 Support", callback_data="support_menu")],
            [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
        ]))

    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 *Manual Order Ready for Delivery*\n━━━━━━━━━━━━━━━━━━━━\n"
            f"Order: `#{oid}`\n"
            f"Customer: {escape_md(order['user_name'])} (`{order['user_id']}`)\n"
            f"Product: *{_fmt_msg_name(order['product_name'])}*\n\n"
            f"*Customer Details:*\n`{escape_md(creds_text)}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Chat", callback_data=f"adm_chat_{order['user_id']}")],
                [InlineKeyboardButton("📦 Deliver Order", callback_data=f"adm_deliver_{oid}")],
                # 🆕 v65: Refund + Cancel buttons
                [InlineKeyboardButton("🔄 Refund (Add Points)", callback_data=f"adm_refund_{oid}"),
                 InlineKeyboardButton("❌ Cancel Order",         callback_data=f"adm_cancel_{oid}")],
                [InlineKeyboardButton("📦 Pending Manual Delivery", callback_data="adm_pending_delivery")],
            ])
        )
    except Exception:
        pass


async def _handle_manual_email_text(update, context, order, product):
    qty = _order_qty_from_name(order['product_name'])
    pd = dict(product) if product else {}
    req_type = pd.get('req_account_type', 'none') or 'none'
    req_pass = bool(pd.get('req_password', 0))
    txt = update.message.text.strip()
    lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
    if len(lines) < qty:
        await update.message.reply_text(f"❌ You ordered {qty} item(s). Please provide {qty} line(s).")
        return True
    for i, ln in enumerate(lines[:qty]):
        if 'gmail' in req_type and not ln.lower().endswith('@gmail.com'):
            await update.message.reply_text(f"❌ Line {i+1} must be a valid Gmail address ending with @gmail.com.")
            return True
    emails = lines[:qty]
    _save_detail_state(order['id'], {'emails': emails})
    context.user_data['ownmail_oid'] = order['id']
    context.user_data['ownmail_qty'] = qty
    context.user_data['ownmail_emails'] = emails
    if req_pass:
        context.user_data['ownmail_step'] = 'pass'
        msg = "🔑 *Now please send the password(s).*"
        if qty > 1:
            msg += "\nSend one password per line, in the same order as the emails."
        await update.message.reply_text(msg, parse_mode="Markdown")
        return True
    if req_type == 'fresh_gmail':
        await _ask_fresh_confirmation(update, order['id'])
        return True
    await _finalize_ownmail_details(update, context, order, product, emails, [])
    return True


async def _handle_manual_password_text(update, context, order, product):
    qty = _order_qty_from_name(order['product_name'])
    state = _load_detail_state(order['customer_credentials'] if 'customer_credentials' in order.keys() else '')
    emails = context.user_data.get('ownmail_emails') or state.get('emails') or []
    if len(emails) < qty:
        # State missing; ask email again.
        _clear_detail_state(order['id'])
        await _send_manual_email_prompt(context.bot, order['user_id'], order, product, qty=qty, retry=False)
        return True
    lines = [ln.strip() for ln in update.message.text.strip().split("\n") if ln.strip()]
    if len(lines) < qty:
        await update.message.reply_text(f"❌ You provided {len(lines)} password(s), but {qty} required.")
        return True
    passwords = lines[:qty]
    _save_detail_state(order['id'], {'emails': emails, 'passwords': passwords})
    context.user_data['ownmail_passwords'] = passwords
    req_type = (dict(product) if product else {}).get('req_account_type', 'none') or 'none'
    if req_type == 'fresh_gmail':
        await _ask_fresh_confirmation(update, order['id'])
        return True
    await _finalize_ownmail_details(update, context, order, product, emails, passwords)
    return True


async def handle_waiting_manual_details(update, context):
    """DB-backed handler for users whose paid manual order is waiting for email/password."""
    order = _find_waiting_manual_details_order(update.effective_user.id)
    if not order:
        return False
    product = get_product(order['product_id']) if order['product_id'] else None
    state = _load_detail_state(order['customer_credentials'] if 'customer_credentials' in order.keys() else '')
    pd = dict(product) if product else {}
    req_pass = bool(pd.get('req_password', 0))
    if state.get('emails') and req_pass and not state.get('passwords'):
        return await _handle_manual_password_text(update, context, order, product)
    return await _handle_manual_email_text(update, context, order, product)


async def ownmail_email_received(update, context):
    oid = context.user_data.get('ownmail_oid')
    if not oid:
        return await handle_waiting_manual_details(update, context)
    o = get_order(oid)
    if not o:
        return True
    p = get_product(o['product_id']) if o['product_id'] else None
    return await _handle_manual_email_text(update, context, o, p)


async def ownmail_pass_received(update, context):
    oid = context.user_data.get('ownmail_oid')
    if not oid:
        return await handle_waiting_manual_details(update, context)
    o = get_order(oid)
    if not o:
        return True
    p = get_product(o['product_id']) if o['product_id'] else None
    return await _handle_manual_password_text(update, context, o, p)


async def ownmail_fresh_yes_callback(update, context):
    q = update.callback_query
    await q.answer()
    oid = int(q.data.replace('ownmail_fresh_yes_', ''))
    o = get_order(oid)
    if not o or o['user_id'] != q.from_user.id:
        await q.answer("Invalid order", show_alert=True); return
    p = get_product(o['product_id']) if o['product_id'] else None
    state = _load_detail_state(o['customer_credentials'] if 'customer_credentials' in o.keys() else '')
    emails = state.get('emails') or context.user_data.get('ownmail_emails') or []
    passwords = state.get('passwords') or context.user_data.get('ownmail_passwords') or []
    if not emails:
        await q.edit_message_text("❌ Email details missing. Please send your email again.")
        _clear_detail_state(oid)
        return
    # Fake a message-like reply target by using q.message for final notification? Simpler send separate messages.
    class _U:
        effective_user = q.from_user
        message = q.message
    await q.edit_message_text("✅ Fresh Gmail confirmed. Finalizing your order...")
    await _finalize_ownmail_details(_U, context, o, p, emails, passwords)


async def ownmail_fresh_no_callback(update, context):
    q = update.callback_query
    await q.answer()
    oid = int(q.data.replace('ownmail_fresh_no_', ''))
    o = get_order(oid)
    if not o or o['user_id'] != q.from_user.id:
        await q.answer("Invalid order", show_alert=True); return
    p = get_product(o['product_id']) if o['product_id'] else None
    _clear_detail_state(oid)
    for k in ['ownmail_step','ownmail_emails','ownmail_passwords']:
        context.user_data.pop(k, None)
    context.user_data['ownmail_oid'] = oid
    context.user_data['ownmail_qty'] = _order_qty_from_name(o['product_name'])
    context.user_data['ownmail_step'] = 'email'
    await q.edit_message_text("❌ No problem. Please send a fresh Gmail address this time.")
    await _send_manual_email_prompt(context.bot, o['user_id'], o, p, retry=True)


# ════════════════════════════════════════════
# 💎 PAY WITH POINTS (WALLET SYSTEM)
# ════════════════════════════════════════════
async def pay_pts_callback(update, context):
    q = update.callback_query
    await q.answer()
    # 🆕 v80: guard against disabled payment method
    from database import is_payment_enabled, get_payment_disable_msg
    if not is_payment_enabled("points"):
        await _safe_send(q, context, get_payment_disable_msg("points"),
                          reply_markup=back_btn()); return

    parts = q.data.split("_")
    pid = int(parts[2])
    qty = int(parts[3]) if len(parts) > 3 else 1
    
    p = get_product(pid)
    if not p:
        await _safe_send(q, context, "❌ Product not found!", reply_markup=back_btn())
        return
        
    # 🔧 AUDIT-FIX C3 (2026-07-31): the debit and the balance check must be a
    # single atomic operation. Reading the balance first, then deducting in a
    # second transaction, allows a race to create two orders for one payment.
    # deduct_points_if_enough() does check+debit inside BEGIN IMMEDIATE and
    # returns False when the balance is insufficient OR the debit failed — only
    # on True do we create the order and fulfill it.
    from database import get_user, deduct_points_if_enough, create_order, get_order, get_combined_points
    from config import POINTS_PER_DOLLAR, ADMIN_ID
    
    user = get_user(q.from_user.id)
    balance = get_combined_points(q.from_user.id)  # 🆕 v161.12: wallet + referral points
    
    cost_usd = _get_eff_price(p) * qty
    cost_pts = points_from_usd(cost_usd)

    # 🆕 v161.12: referral points (ref_points) are NOW spendable in the normal
    # "Pay with Points" checkout too — combined wallet checkout.
    from database import deduct_combined_points
    if not deduct_combined_points(q.from_user.id, cost_pts, tx_type='purchase',
                                   description=f"Product #{pid}"):
        # Refresh balance for accurate messaging (it may have changed under us).
        try:
            balance = get_combined_points(q.from_user.id)
        except Exception:
            pass
        missing = max(0.0, cost_pts - balance)
        txt = (f"❌ *Insufficient Wallet Balance*\n"
               f"━━━━━━━━━━━━━━━━━━━━\n\n"
               f"📦 Product: *{_fmt_msg_name(p['name'])}* (x{qty})\n"
               f"💰 Required: *{fmt_points(cost_pts)} 💎*\n"
               f"💳 Your Balance: *{fmt_points(balance)} 💎*\n"
               f"📉 Short by: *{fmt_points(missing)} 💎*\n\n"
               f"_Wallet + referral points count together._\n"
               f"Top up your points balance to complete this purchase.")
        
        kb = [
            [InlineKeyboardButton("💎 Buy More Points", callback_data="buy_points")],
            [InlineKeyboardButton("🔙 Back to Payment Methods", callback_data=f"buy_{pid}" if qty == 1 else f"buyx_{pid}")]
        ]
        await _safe_send(q, context, txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    # --- 🟢 SUFFICIENT POINTS: Process Instant Checkout ---
    new_balance = balance - cost_pts
    
    un = q.from_user.username or q.from_user.first_name
    creds = context.user_data.pop('order_creds', '')
    pname = p['name'] if qty == 1 else f"{p['name']} × {qty}"
    oid = create_order(q.from_user.id, un, pid, pname, cost_usd, 'wallet', '', cost_pts, 'PTS', 'product', creds, qty=qty)
    
    await _safe_send(q, context,
        f"✅ *Wallet Payment Successful!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Old Balance: `{fmt_points(balance)}` 💎\n"
        f"➖ Deducted: `-{fmt_points(cost_pts)}` 💎\n"
        f"💳 New Balance: *{fmt_points(new_balance)}* 💎\n\n"
        f"⏳ Processing your order...",
        parse_mode="Markdown")

    order = get_order(oid)
    await fulfill_paid_product_order(context.bot, order, cost_pts,
                                     payment_method_label=f"Wallet / Points (-{fmt_points(cost_pts)} 💎)",
                                     award_bonus=False)





# ════════════════════════════════════════════════════════════
# 🔧 v122 — BYBIT PAY UID FLOW (warning → UID → amount → unique deposit)
# Auto-match: sender Bybit UID + unique 4-decimal amount (+ reference)
# ════════════════════════════════════════════════════════════

def _gen_unique_bybit_amount(base_amount: float) -> float:
    """Base amount + random 4-decimal fraction → each order's amount is unique
    (e.g. 1 → 1.9076, 5 → 5.0087). This lets the bot match by UID + exact amount
    even when many customers deposit the same nominal value at the same time."""
    import random as _r
    try:
        base = float(base_amount or 0)
    except Exception:
        base = 0.0
    base = max(1.0, base)
    frac = round(_r.uniform(0.0001, 0.9999), 4)
    return round(base + frac, 4)


def _make_flow_btn(btn_id, callback_data=None, copy_text=None):
    """Editable flow button (label + premium emoji + color) for the Bybit flow."""
    try:
        from button_system import get_button_label, resolve_button_style, make_premium_button
        from database import get_setting as _gs
        size = _gs("button_size", "large")
        _alias = {"small": "short", "full": "xl"}
        size = _alias.get(size, size)
        label = get_button_label(btn_id, size) or "…"
        style = resolve_button_style(btn_id)
        return make_premium_button(label, callback_data=callback_data,
                                   copy_text=copy_text, style=style)
    except Exception:
        return InlineKeyboardButton("…", callback_data=callback_data or "se_noop",
                                    copy_text=copy_text)



# ════════════════════════════════════════════════════════════
# 🟡 v125 — BYBIT FLOW (clean rebuild, unified, bug-free)
#   bybit_pay:   warning → UID → (amount if points) → deposit → check
#   bybit_usdt*: warning → (amount if points) → deposit → check
#   Check payment (bybitv_<oid>) → API auto-match → credit/deliver
# ════════════════════════════════════════════════════════════

async def _bf_send_retry(reply_fn, text, **kw):
    """Send with graceful fallback — NEVER silently swallow.

    🔧 v127 FIX: the old closure did `except Exception: return None` which made
    any failure (Markdown parse error, 429 FloodWait, BadRequest) invisible —
    the customer saw NO response after typing the amount. Now:
      1. try as requested (parse_mode=Markdown)
      2. on parse error → retry WITHOUT parse_mode
      3. on FloodWait/RetryAfter → wait and retry once
      4. on other errors → log + retry as plain text
      5. if everything fails → raise so callers can show a visible fallback
    """
    import logging as _l
    try:
        return await reply_fn(text, **kw)
    except Exception as _e1:
        _l.getLogger(__name__).warning(f"[BybitFlow] send failed (1st): {type(_e1).__name__}: {str(_e1)[:120]}")
        # Markdown parse error → retry without parse_mode
        if kw.get("parse_mode") and "parse" in str(_e1).lower():
            kw2 = dict(kw); kw2.pop("parse_mode", None)
            try:
                return await reply_fn(text, **kw2)
            except Exception as _e2:
                _l.getLogger(__name__).warning(f"[BybitFlow] send failed (no-md): {type(_e2).__name__}")
                return None
        # FloodWait / RetryAfter → wait and retry
        try:
            from telegram.error import RetryAfter, FloodWait
            if isinstance(_e1, (RetryAfter, FloodWait)):
                wait = getattr(_e1, "retry_after", None) or 5
                await asyncio.sleep(min(int(wait) + 1, 20))
                kw2 = dict(kw); kw2.pop("parse_mode", None)
                try:
                    return await reply_fn(text, **kw2)
                except Exception as _e3:
                    _l.getLogger(__name__).warning(f"[BybitFlow] send failed (flood-retry): {type(_e3).__name__}")
                    return None
        except Exception:
            pass
        # Last resort: plain text without any kwargs that may fail
        try:
            return await reply_fn(text)
        except Exception as _e4:
            _l.getLogger(__name__).error(f"[BybitFlow] send failed (plain): {type(_e4).__name__}: {str(_e4)[:120]}")
            raise


def _bybit_flow_target(target):
    """Normalize a send target (CallbackQuery or Message) → (user, send_fn).

    🔧 v127: send is robust (never silent) — see _bf_send_retry.
    🔧 v129: duck-type instead of isinstance(CallbackQuery) — works with real
    PTB objects AND any test double that has .message / .from_user.
    """
    if getattr(target, "message", None) is not None:
        # CallbackQuery-like: replies go through target.message
        user = getattr(target, "from_user", None)
        async def send(text, **kw):
            return await _bf_send_retry(target.message.reply_text, text, **kw)
        return user, send
    # Message-like
    user = getattr(target, "from_user", None)
    async def send(text, **kw):
        return await _bf_send_retry(target.reply_text, text, **kw)
    return user, send


async def bybit_start_flow(q, context, method, *, mode, base_amount=None, product=None, qty=1):
    """Entry: user tapped a Bybit method → decimals/fee warning screen."""
    from database import is_payment_enabled, get_payment_disable_msg
    if not is_payment_enabled(method):
        await _safe_send(q, context, get_payment_disable_msg(method), reply_markup=back_btn())
        return
    context.user_data['bybit_flow'] = {
        'step': 'warned',
        'mode': mode,                      # 'points' | 'product'
        'method': method,                  # bybit_pay | bybit_usdt_trc20 | bybit_usdt_bep20
        'base_amount': float(base_amount) if base_amount is not None else None,
        'product_id': int(product['id']) if product else 0,
        'qty': int(qty or 1),
    }
    text = _pay_resp('bybit_warning_text') if method == 'bybit_pay' else _pay_resp('bybit_usdt_warning_text')
    kb = InlineKeyboardMarkup([
        [_make_flow_btn('bybit_continue', callback_data='bybit_flow_continue')],
        [_make_flow_btn('bybit_cancel_flow', callback_data='bybit_flow_cancel')],
    ])
    await _safe_send(q, context, text, parse_mode='Markdown', reply_markup=kb)


async def bybit_flow_continue_callback(update, context):
    """Warning → Continue. bybit_pay asks UID; usdt asks amount (points) or goes
    straight to deposit (product)."""
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    fl = context.user_data.get('bybit_flow') or {}
    method = fl.get('method', 'bybit_pay')
    mode = fl.get('mode', 'points')
    if method == 'bybit_pay':
        fl['step'] = 'waiting_uid'
        context.user_data['bybit_flow'] = fl
        text = _pay_resp('bybit_uid_prompt')
        kb = InlineKeyboardMarkup([[_make_flow_btn('bybit_cancel_flow', callback_data='bybit_flow_cancel')]])
        await _safe_send(q, context, text, parse_mode='Markdown', reply_markup=kb)
        return
    # USDT (TRC-20 / BEP-20)
    if mode == 'product':
        await _bybit_create_and_show(q, context)
        return
    # 🔧 v129: amount already selected on the Buy Points screen → skip the
    # amount prompt entirely and go straight to the deposit screen (unique
    # amount generated from the chosen base). No double-asking.
    if fl.get('base_amount') is not None:
        fl['step'] = 'ready_create'
        context.user_data['bybit_flow'] = fl
        await _bybit_create_and_show(q, context)
        return
    fl['step'] = 'waiting_amount'
    context.user_data['bybit_flow'] = fl
    cfg = _usdt_cfg(method)
    net = str(cfg.get('network_label') or 'TRC-20')
    text = _pay_resp('bybit_usdt_amount_prompt').format(network_label=escape_md(net))
    kb = InlineKeyboardMarkup([[_make_flow_btn('bybit_cancel_flow', callback_data='bybit_flow_cancel')]])
    await _safe_send(q, context, text, parse_mode='Markdown', reply_markup=kb)


async def bybit_flow_cancel_callback(update, context):
    """Cancel the Bybit flow → back to Buy Points."""
    q = update.callback_query
    try:
        await q.answer("Cancelled", show_alert=False)
    except Exception:
        pass
    context.user_data.pop('bybit_flow', None)
    context.user_data.pop('pending_order_id', None)
    try:
        from handlers_start import buy_points_callback
        q.data = "buy_points"
        await buy_points_callback(update, context)
    except Exception:
        await _safe_send(q, context, _pay_resp('bybit_cancelled'),
                          parse_mode='Markdown', reply_markup=back_btn())


async def bybit_flow_uid_received(update, context):
    """User types their Bybit UID (bybit_pay only). Returns True when consumed."""
    fl = context.user_data.get('bybit_flow') or {}
    if fl.get('step') != 'waiting_uid':
        return False
    txt = (update.message.text or '').strip()
    if not txt.isdigit() or not (6 <= len(txt) <= 12):
        await update.message.reply_text(_pay_resp('bybit_uid_invalid'), parse_mode='Markdown')
        return True
    fl['uid'] = txt
    # 🔧 v129: product → straight to deposit; points with pre-selected amount →
    # skip the amount prompt (no double-asking); points without amount → ask.
    if fl.get('mode') == 'product' or fl.get('base_amount') is not None:
        fl['step'] = 'ready_create'
        context.user_data['bybit_flow'] = fl
        await _bybit_create_and_show(update.message, context)
        return True
    fl['step'] = 'waiting_amount'
    context.user_data['bybit_flow'] = fl
    text = _pay_resp('bybit_amount_prompt')
    kb = InlineKeyboardMarkup([[_make_flow_btn('bybit_cancel_flow', callback_data='bybit_flow_cancel')]])
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=kb)
    return True


async def bybit_flow_amount_received(update, context):
    """User types the deposit amount (bybit_pay points OR usdt points)."""
    fl = context.user_data.get('bybit_flow') or {}
    if fl.get('step') != 'waiting_amount':
        return False
    method = fl.get('method', 'bybit_pay')
    invalid_key = 'bybit_usdt_amount_invalid' if method != 'bybit_pay' else 'bybit_amount_invalid'
    txt = (update.message.text or '').strip().replace('$', '').replace(',', '')
    m = re.search(r'(\d+(?:\.\d+)?)', txt)
    if not m:
        await update.message.reply_text(_pay_resp(invalid_key), parse_mode='Markdown')
        return True
    base = float(m.group(1))
    if base < 1 or base > 5000:
        await update.message.reply_text(_pay_resp(invalid_key), parse_mode='Markdown')
        return True
    fl['base_amount'] = base
    fl['step'] = 'ready_create'
    context.user_data['bybit_flow'] = fl
    try:
        await _bybit_create_and_show(update.message, context)
    except Exception as e:
        import logging as _l
        _l.getLogger(__name__).exception("[BybitFlow] amount → create_and_show failed")
        # NEVER leave the customer with silence
        try:
            await update.message.reply_text(
                "⚠️ *Oops — could not process your amount.*\n"
                "Please tap *🔍 Check payment* or try again. If it keeps failing, contact support.",
                parse_mode="Markdown")
        except Exception:
            try:
                await update.message.reply_text("⚠️ Could not process your amount. Please try again.")
            except Exception:
                pass
    return True


async def _bybit_create_and_show(target, context):
    """Create the order (unique amount for points / exact price for products) and
    show the deposit screen with copy / check / cancel buttons."""
    fl = context.user_data.get('bybit_flow') or {}
    method = fl.get('method', 'bybit_pay')
    mode = fl.get('mode', 'points')
    pid = int(fl.get('product_id') or 0)
    qty = int(fl.get('qty') or 1)
    base = fl.get('base_amount')

    from database import gen_unique_pay_reference, set_order_pay_reference, set_order_customer_bybit_uid

    user, send = _bybit_flow_target(target)
    if user is None or not getattr(user, 'id', None):
        return

    if mode == 'points':
        base = float(base if base is not None else 1)
        amount = _gen_unique_bybit_amount(base)
        pts = points_from_usd(amount)
        pname = f"💎 {fmt_points(pts)} Points"
        otype = 'points'
    else:
        p = get_product(pid) if pid else None
        if not p:
            await send("❌ Product not found.")
            return
        amount = float(_get_eff_price(p)) * qty
        pname = p['name'] if qty == 1 else f"{p['name']} × {qty}"
        otype = 'product'

    save_user(user.id, user.username or '', user.first_name or '')
    ref = gen_unique_pay_reference()
    oid = create_order(user.id, user.first_name or str(user.id), pid if pid else 0,
                       pname, amount, method, '', amount, 'USDT', otype, '',
                       qty=qty if mode == 'product' else 1)
    update_order_status(oid, 'bybit_waiting' if method == 'bybit_pay' else 'usdt_waiting')
    set_order_pay_reference(oid, ref)
    if method == 'bybit_pay' and fl.get('uid'):
        set_order_customer_bybit_uid(oid, fl['uid'])
    context.user_data['pending_order_id'] = oid
    context.user_data.pop('bybit_flow', None)

    if method == 'bybit_pay':
        store_uid = get_setting('bybit_pay_id', os.getenv('BYBIT_PAY_ID', '')).strip()
        if not store_uid:
            await send("❌ Bybit Pay ID is not configured. Please contact support.")
            return
        amount_str = f"{amount:.4f}"
        text = _pay_resp('bybit_deposit_instructions').format(
            store_uid=escape_md(store_uid), amount=amount_str, reference_id=ref)
        kb = InlineKeyboardMarkup([
            [_make_flow_btn('bybit_copy_amount', copy_text=amount_str),
             _make_flow_btn('bybit_copy_uid', copy_text=store_uid)],
            [_make_flow_btn('bybit_check_payment', callback_data=f"bybitv_{oid}")],
            [_make_flow_btn('bybit_cancel_payment', callback_data='cancel_order')],
        ])
    else:
        cfg = _usdt_cfg(method)
        address = str(cfg.get('address') or '')
        net = str(cfg.get('network_label') or 'TRC-20')
        amount_str = f"{amount:.6f}".rstrip('0').rstrip('.') if amount == int(amount) else f"{amount:.4f}"
        text = _pay_resp('bybit_usdt_deposit_instructions').format(
            network_label=escape_md(net), address=escape_md(address), amount=amount_str)
        kb = InlineKeyboardMarkup([
            [_make_flow_btn('bybit_copy_address', copy_text=address),
             _make_flow_btn('bybit_copy_amount', copy_text=amount_str)],
            [_make_flow_btn('bybit_check_payment', callback_data=f"bybitv_{oid}")],
            [_make_flow_btn('bybit_cancel_payment', callback_data='cancel_order')],
        ])

    await send(text, parse_mode='Markdown', reply_markup=kb)
