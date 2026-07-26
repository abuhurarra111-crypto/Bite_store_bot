def _get_eff_price(p):
    d = dict(p)
    return float(d.get('flash_price', 0)) if d.get('is_flash_sale') else float(d.get('price', 0))

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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import *
from database import *
from keyboards import *
from utils import escape_md, format_pkr, nav_push, build_manual_order_whatsapp_url, get_product_mode_tag, smart_text_and_mode, contains_premium_markup, fmt_price
import re
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


def _amounts_match(actual, expected, tolerance=0.05):
    """Return True only when a paid/entered USD amount matches expected price."""
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
    """Send text with automatic Markdown→HTML conversion for premium emojis."""
    preferred = kwargs.pop("parse_mode", "Markdown")
    send_text, send_mode = smart_text_and_mode(text, preferred)
    try:
        return await bot.send_message(chat_id, send_text, parse_mode=send_mode, **kwargs)
    except Exception as e:
        if "parse" in str(e).lower():
            return await bot.send_message(chat_id, send_text, **kwargs)
        raise


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
        await context.bot.send_message(chat_id=q.message.chat_id, text=send_text, **send_kwargs)
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
        await _safe_send(q, context, _r("out_of_stock"), reply_markup=back_btn()); return

    # 🆕 Minimum order quantity: if admin set a minimum > 1, the customer must
    # order at least that many → send them into the quantity flow instead of
    # buying just 1.
    min_qty = _get_min_qty(p)
    if min_qty > 1:
        context.user_data['bulk_product_id'] = p['id']
        context.user_data['bulk_step'] = 'waiting_qty'
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")]])
        if is_manual:
            stock_text = "🟢 On-Demand"; max_qty = 100
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
    
    total_price = _get_eff_price(p) * qty
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
        await _safe_send(q, context, _r("out_of_stock"), reply_markup=back_btn()); return
        
    context.user_data['bulk_product_id'] = p['id']
    context.user_data['bulk_step'] = 'waiting_qty'
    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
    ])
    pkr = format_pkr(_get_eff_price(p), _pkr_rate())
    
    if is_manual:
        stock_text = "🟢 On-Demand (Unlimited)"
        max_qty = 100
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

    total = _get_eff_price(p) * qty
    pkr = format_pkr(total, _pkr_rate())
    msg = (
        f"🛒× *Confirm Bulk Purchase*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *{_fmt_msg_name(p['name'])}*\n"
        f"💰 Unit Price: ${_get_eff_price(p):.2f}\n"
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
        f"💵 Amount: *${float(amount):.2f}*\n\n"
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
    amount = round(float(amount), 2)
    if amount <= 0:
        await _safe_send(q, context, "❌ Invalid amount.", reply_markup=back_btn())
        return

    # Clear old payment state
    for k in ['ep_step','ep_amount','ep_tid','binance_step','binance_amount','binance_txid',
              'binance_product_id','binance_qty','binance_name','jc_step','jc_amount','jc_tid',
              'pending_order_id']:
        context.user_data.pop(k, None)

    if is_points:
        pts = int(amount * POINTS_PER_DOLLAR)
        oid = create_order(u.id, un, 0, f"💎 {pts} Points", amount, 'binance', note_id, amount, 'USDT', 'points')
        title = f"💎 Deposit for *{pts} Points*"
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
        oid = create_order(u.id, un, p['id'], pname, amount, 'binance', note_id, amount, 'USDT', 'product', creds)
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
    """Build user-facing Binance instructions. NO mention of 'API' or 'Gmail'."""
    bid = get_setting("binance_id", BINANCE_PAY_ID)
    holder = get_setting("binance_name", get_setting("account_name", ACCOUNT_NAME))
    parts = [
        "🟡 *Binance Pay Checkout*",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        title,
        f"💵 Amount: *${float(amount):.2f}*",
        "",
        "📋 *Step 1 — Send the payment*",
        f"  • Pay ID:  `{bid}`",
        f"  • Name:    *{escape_md(holder)}*",
        f"  • Amount:  *${float(amount):.2f}*",
        "",
        "📨 *Step 2 — Send your Order ID*",
        "After completing the payment, open the transaction "
        "in your Binance app, copy the *Order ID*, and "
        "paste it below.",
        "",
        "_Your order will be confirmed automatically within a few seconds._",
    ]
    if order_id_for_display:
        parts += ["", f"_Your last submitted Order ID:_ `{order_id_for_display}`"]
    return "\n".join(parts)


async def _start_binance_order_id_flow(update, context, *, is_points, product, qty, amount, points_amount=None):
    """Create a pending Binance order, ask the user to paste their Order ID."""
    q = update.callback_query
    u = q.from_user
    un = u.first_name or str(u.id)
    save_user(u.id, u.username or "", u.first_name or "")

    amount = round(float(amount), 2)
    if amount <= 0:
        await _safe_send(q, context, "❌ Invalid amount.", reply_markup=back_btn())
        return

    if is_points:
        pts = int(amount * POINTS_PER_DOLLAR)
        oid = create_order(
            u.id, un, 0, f"💎 {pts} Points",
            amount, "binance", "", amount, "USDT", "points",
        )
        title = f"💎 You will receive *{pts} Points*"
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
        )
        title = f"📦 *{_fmt_msg_name(pname)}*"

    update_order_status(oid, "binance_waiting")
    context.user_data["pending_order_id"] = oid
    context.user_data["binance_step"]     = "waiting_order_id"
    context.user_data["binance_amount"]   = amount

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_order")],
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
    if o["status"] in ("paid_pending_delivery", "completed"):
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
    if fresh and fresh["status"] in ("delivered", "paid_pending_delivery", "completed"):
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

    # Notify admin
    try:
        u2 = update.effective_user
        await context.bot.send_message(
            ADMIN_ID,
            f"🟡 *Binance Order Pending #{oid}*\n"
            f"User: {escape_md(u2.first_name or '?')} (`{u2.id}`)\n"
            f"Amount: ${expected_amount:.2f}\n"
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
    if fresh2 and fresh2["status"] in ("delivered", "paid_pending_delivery", "completed"):
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
    pts = int(float(paid_amount or order['price'] or 0) * POINTS_PER_DOLLAR)
    if pts <= 0:
        pts = int(float(order['price'] or 0) * POINTS_PER_DOLLAR)
    save_user(order['user_id'], '', order['user_name'] or '')
    add_points(order['user_id'], pts)
    update_order_status(order['id'], 'delivered')
    total_pts = get_user_points(order['user_id'])
    text = (
        f"🎉 *Deposit Successful!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ Your payment has been confirmed.\n"
        f"💎 Points Added: *{pts}*\n"
        f"💰 Amount: *{fmt_price(float(paid_amount or order['price'] or 0))}*\n"
        f"🧾 Order ID: `#{order['id']}`\n\n"
        f"📊 New Points Balance: *{total_pts}*\n\n"
        f"Thank you for your deposit!"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy More", callback_data="shop")],
        [InlineKeyboardButton("📊 My Account", callback_data="my_account")],
    ])
    await _bot_send_smart(bot, order['user_id'], text, parse_mode="Markdown", reply_markup=kb)


async def _send_static_media_delivery(bot, order, product, method, amount, pts_bonus=0):
    """Send static media/file delivery to customer instantly.
       🆕 v66: 10pts bonus REMOVED. Tier progress hint appended instead."""
    pd = dict(product) if product else {}
    file_id = pd.get('delivery_file_id', '') or ''
    file_type = pd.get('delivery_file_type', '') or 'document'
    file_name = pd.get('delivery_file_name', '') or file_type
    caption_text = (pd.get('delivery_caption', '') or pd.get('delivery_text', '') or '').strip()

    from database import save_order_delivery_content
    history_note = f"[Static {file_type}: {file_name}]"
    if caption_text:
        history_note += f"\n{caption_text}"
    save_order_delivery_content(order['id'], history_note)
    update_order_status(order['id'], 'delivered')
    # 🆕 v66: bonus 10pts removed — no add_points call here.

    header = (
        f"🎉 *Thanks for purchasing!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ Payment confirmed and your product is delivered below.\n"
        f"🧾 Order ID: `#{order['id']}`\n"
        f"📦 Product: *{_fmt_msg_name(order['product_name'])}*\n"
        f"💳 Payment: *{escape_md(method)}*\n"
    )
    # 🆕 v66: Tier progress hint (notify_tier_upgrade still fires separately if upgraded)
    # 🆕 v68: Per-order tier bonus (admin-configured points credit)
    try:
        from loyalty_extras import build_tier_progress_line, credit_tier_bonus
        _bonus_pts = credit_tier_bonus(order['user_id'])
        if _bonus_pts > 0:
            header += f"💎 *Tier bonus: +{_bonus_pts} points*\n"
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

    # Auto/static text delivery: static text handled inside build_delivery_from_accounts();
    # account-pool delivery is also handled there.
    from database import build_delivery_from_accounts, save_order_delivery_content
    delivery = build_delivery_from_accounts(order['product_id'], order['id'], qty, order['user_id'])
    save_order_delivery_content(order['id'], delivery)
    update_order_status(order['id'], 'delivered')

    # 🆕 v66: bonus 10pts removed entirely — no add_points here.

    # 🆕 v72 BUG FIX: Send delivery content as a SEPARATE message in its native
    # format (HTML for templated, plain for static text). Previously this code
    # escape_md()'d the entire pre-rendered delivery which MANGLED special
    # chars in user content (URLs, passwords, codes etc.).
    delivery_label = "Your Product Details" if not has_static_text else "Your Delivery"
    text = (
        f"🎉 *Thanks for purchasing!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ Payment confirmed and your product is delivered below.\n"
        f"🧾 Order ID: `#{order['id']}`\n"
        f"📦 Product: *{_fmt_msg_name(order['product_name'])}*\n"
        f"💳 Payment: *{escape_md(method)}*\n\n"
        f"📨 *{delivery_label}* — see the next message."
    )
    # 🆕 v66: Tier progress hint  +  🆕 v68: Tier bonus credit
    try:
        from loyalty_extras import build_tier_progress_line, credit_tier_bonus
        _bonus_pts = credit_tier_bonus(order['user_id'])
        if _bonus_pts > 0:
            text += f"\n\n💎 *Tier bonus: +{_bonus_pts} points*"
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
    total = round(_get_eff_price(p) * qty, 2)
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
        f"💰 *Total: ${total:.2f}*\n\n"
        f"📋 *Send ${total:.2f} to:*\n"
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
        total = (_get_eff_price(p) * qty) if p else 0
    
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
        pts = int(expected_amount * POINTS_PER_DOLLAR)
        oid = create_order(u.id, un, 0, f"💎 {pts} Points", expected_amount, 'binance', sender_name, expected_amount, 'USDT', 'points')
        pname = f"💎 {pts} Points"
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
        order_total = round(_get_eff_price(p) * qty, 2)
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
        oid = create_order(u.id, un, p['id'], pname, order_total, 'binance', sender_name, expected_amount, 'USDT', 'product', creds)
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
    
    # Notify admin
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"🔶 *Binance Order Pending #{oid}*\n"
            f"User: {escape_md(un)} (`{u.id}`)\n"
            f"Product: {_fmt_msg_name(pname)}\n"
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
    total_usd = _get_eff_price(p) * qty
    total_rs = total_usd * _pkr_rate()

    creds = context.user_data.pop('order_creds', '')
    oid = create_order(u.id, un, p['id'], pname, total_usd, 'easypaisa', '', total_rs, 'PKR', 'product', creds)
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
    total_usd = _get_eff_price(p) * qty
    total_rs = total_usd * _pkr_rate()

    # Create pending order RIGHT NOW
    creds = context.user_data.pop('order_creds', '')
    oid = create_order(u.id, un, p['id'], pname, total_usd, 'jazzcash', '', total_rs, 'PKR', 'product', creds)
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
        await _bot_send_smart(context.bot, ADMIN_ID,
            f"📱 *JazzCash Order Pending #{oid}*\n"
            f"User: {escape_md(un)} (`{u.id}`)\n"
            f"Product: {_fmt_msg_name(pname)}\n"
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
        m = re.search(r'(\d+)', order['product_name'] or '')
        return int(m.group(1)) if m else int(float(order['price'] or 0) * POINTS_PER_DOLLAR)
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
        from payments import verify_by_tid_only
    else:
        from payments import verify_by_tid_only

    api_result = await asyncio.to_thread(verify_by_tid_only, tid)
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
            add_points(o['user_id'], pts)
        update_order_status(oid, 'delivered')
        total_pts = get_user_points(o['user_id'])
        text = (
            f"🎉 *Deposit Successful!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Your payment has been confirmed.\n"
            f"💎 Points Added: *{pts}*\n"
            f"💰 Amount: *Rs.{actual_rs:.0f}*\n"
            f"🧾 Order ID: `#{oid}`\n"
            f"🔢 Transaction ID: `{tid}`\n\n"
            f"📊 New Points Balance: *{total_pts}*\n\n"
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

    # 🔧 v33 FIX: Call the API to get the result (was missing!)
    from payments import verify_by_tid_only
    api_result = verify_by_tid_only(tid)
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
            m = re.search(r'(\d+)', o['product_name'] or '')
            pts = int(m.group(1)) if m else 0
            if pts > 0: add_points(o['user_id'], pts)
            msg = (f"🎉 *Payment Verified!* ✅\n━━━━━━━━━━━━━━━━━━━━\n\n"
                   f"💎 *{pts} Points* added to your account!\n\n"
                   f"💰 Amount: Rs.{actual_rs:.0f}\n👤 From: {sender_name}\n🔢 TID: `{tid}`\n\nThank you! 🙏")
        else:
            order_qty = 1
            qm = re.search(r'×\s*(\d+)$', o['product_name'] or '')
            if qm: order_qty = int(qm.group(1))
            
            p = get_product(o['product_id'])
            is_manual = (dict(p) if p else {}).get('delivery_mode') == 'manual'
            pts_bonus = int(o['price'] * POINTS_PER_DOLLAR)
            
            if is_manual:
                req_type = (dict(p) if p else {}).get('req_account_type', 'none')
                if req_type == 'none':
                    update_order_status(oid, 'paid_pending_delivery')
                    msg = f"✅ Payment verified!\n\nYour order request has been sent to the store owner. In 1 to 3 hours, as soon as the owner is online, your order will be completed."
                    if (dict(p) if p else {}).get('delivery_text'):
                        msg += f"\n\n📝 *Instructions:*\n{p['delivery_text']}"
                    admin_msg = f"🔔 *New Order! (Readymade)*\nOrder #{oid}\nProduct: {p['name']}\n\nPlease deliver the account."
                    from config import ADMIN_ID
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
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
                update_order_status(oid, 'delivered')
                from database import build_delivery_from_accounts
                delivery = build_delivery_from_accounts(o['product_id'], o['id'], order_qty, o['user_id'])
                # 🆕 v66: bonus 10pts removed
                # 🆕 v72: byte-perfect — receipt header (Markdown) + delivery
                # content (HTML, native format) sent as 2 separate messages so
                # neither parse mode mangles the other.
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
                # 🆕 v66: tier progress hint  +  🆕 v68: tier bonus credit
                try:
                    from loyalty_extras import build_tier_progress_line, credit_tier_bonus
                    _bonus_pts = credit_tier_bonus(o['user_id'])
                    if _bonus_pts > 0:
                        msg += f"\n\n💎 *Tier bonus: +{_bonus_pts} points*"
                    tline = build_tier_progress_line(o['user_id'])
                    if tline:
                        msg += f"\n\n{tline}"
                except Exception: pass

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
# 💎 BUY POINTS HANDLERS
# ════════════════════════════════════════════
async def points_amount_callback(update, context):
    q = update.callback_query; await q.answer()
    amt = int(q.data.split("_")[1]); pts = amt * POINTS_PER_DOLLAR
    context.user_data['points_amount'] = amt
    await q.edit_message_text(
        f"💎 *Buy {pts} Points*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 ${amt} = {pts} Points\n\nSelect payment method:",
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
    pts = int(amt * POINTS_PER_DOLLAR)
    await update.message.reply_text(
        f"💎 *{pts} Points* — ${amt}\n\nSelect payment method:",
        parse_mode="Markdown", reply_markup=points_payment_keyboard(amt))
    return True


async def points_binance_callback(update, context):
    """🔶 Binance Buy Points → Order-ID flow (when API toggle ON) or legacy sender-name flow."""
    q = update.callback_query; await q.answer()
    amt = float(q.data.split("_")[2])
    pts = int(amt * POINTS_PER_DOLLAR)

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
        f"💎 You will receive: *{pts} Points*\n"
        f"💰 Amount: *${amt:.2f}*\n\n"
        f"📋 *Send ${amt:.2f} to:*\n"
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
    pts = int(amt * POINTS_PER_DOLLAR)
    rs_amount = amt * _pkr_rate()
    u = q.from_user
    un = u.first_name or str(u.id)
    save_user(u.id, u.username or '', u.first_name or '')

    # Clear old state
    for k in ['ep_step','ep_amount','ep_tid','binance_step','binance_amount']:
        context.user_data.pop(k, None)

    # Create pending order NOW
    oid = create_order(u.id, un, 0, f"💎 {pts} Points", amt, 'easypaisa', '', rs_amount, 'PKR', 'points')
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
        f"📱 *Order #{oid} — EasyPaisa Buy {pts} Points*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 You will receive: *{pts} Points*\n"
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
    pts = int(amt * POINTS_PER_DOLLAR)
    rs_amount = amt * _pkr_rate()
    u = q.from_user
    un = u.first_name or str(u.id)
    save_user(u.id, u.username or '', u.first_name or '')

    # Clear old state
    for k in ['ep_step','ep_amount','ep_tid','binance_step','binance_amount','jc_step','jc_amount','jc_tid']:
        context.user_data.pop(k, None)

    # Create pending order
    oid = create_order(u.id, un, 0, f"💎 {pts} Points", amt, 'jazzcash', '', rs_amount, 'PKR', 'points')
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
        f"📱 *Order #{oid} — JazzCash Buy {pts} Points*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 You will receive: *{pts} Points*\n"
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
    q = update.callback_query; await q.answer()
    nav_push(context, 'my_orders')
    orders = get_user_product_orders(q.from_user.id)
    if not orders:
        await q.edit_message_text("📜 *No orders yet!*", parse_mode="Markdown",
                                    reply_markup=back_btn(location="my_orders"))
        return
    text = "📜 *Order History:*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    rows = []
    for o in orders[:12]:
        s_icon = {'pending':'🟡','screenshot_sent':'📸','binance_waiting':'🔶',
                  'paid_pending_delivery':'🕒','waiting_for_details':'📨',
                  'delivered':'✅','cancelled':'❌','rejected':'❌'}.get(o['status'],'❓')
        text += f"• #{o['id']} {escape_md(o['product_name'])} — {fmt_price(o['price'])} {s_icon}\n"
        if o['status'] == 'delivered':
            text += "   ↳ Tap View to see/resend delivery details.\n"
        elif o['status'] in ('paid_pending_delivery','waiting_for_details'):
            text += "   ↳ Your order is in progress.\n"
        text += "\n"
        rows.append([InlineKeyboardButton(f"🔎 View #{o['id']}", callback_data=f"myord_{o['id']}")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    send_text, send_mode = smart_text_and_mode(text[:3900], "Markdown")
    await q.edit_message_text(send_text, parse_mode=send_mode, reply_markup=InlineKeyboardMarkup(rows))


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
    rows = []
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
    from payments import verify_by_tid_only
    api_result = verify_by_tid_only(tid)

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
            m = re.search(r'(\d+)', o['product_name'] or '')
            pts = int(m.group(1)) if m else 0
            if pts > 0: add_points(o['user_id'], pts)
            msg = (f"🎉 *Payment Verified!* ✅\n━━━━━━━━━━━━━━━━━━━━\n\n"
                   f"💎 *{pts} Points* added to your account!\n\n"
                   f"💰 Amount: Rs.{actual_rs:.0f}\n"
                   + (f"👤 From: {sender_name}\n" if sender_name else "")
                   + f"🔢 TID: `{tid}`\n\nThank you! 🙏")
        else:
            order_qty = 1
            qm = re.search(r'×\s*(\d+)$', o['product_name'] or '')
            if qm: order_qty = int(qm.group(1))
            
            p = get_product(o['product_id'])
            is_manual = (dict(p) if p else {}).get('delivery_mode') == 'manual'
            pts_bonus = int(o['price'] * POINTS_PER_DOLLAR)
            
            if is_manual:
                req_type = (dict(p) if p else {}).get('req_account_type', 'none')
                if req_type == 'none':
                    update_order_status(oid, 'paid_pending_delivery')
                    msg = f"✅ Payment verified!\n\nYour order request has been sent to the store owner. In 1 to 3 hours, as soon as the owner is online, your order will be completed."
                    if (dict(p) if p else {}).get('delivery_text'):
                        msg += f"\n\n📝 *Instructions:*\n{p['delivery_text']}"
                    admin_msg = f"🔔 *New Order! (Readymade)*\nOrder #{oid}\nProduct: {p['name']}\n\nPlease deliver the account."
                    from config import ADMIN_ID
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
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
                update_order_status(oid, 'delivered')
                from database import build_delivery_from_accounts
                delivery = build_delivery_from_accounts(o['product_id'], o['id'], order_qty, o['user_id'])
                # 🆕 v66: bonus 10pts removed
                # 🆕 v72: byte-perfect — receipt header (Markdown) + delivery
                # content (HTML, native format) sent as 2 separate messages so
                # neither parse mode mangles the other.
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
                # 🆕 v66: tier progress hint  +  🆕 v68: tier bonus credit
                try:
                    from loyalty_extras import build_tier_progress_line, credit_tier_bonus
                    _bonus_pts = credit_tier_bonus(o['user_id'])
                    if _bonus_pts > 0:
                        msg += f"\n\n💎 *Tier bonus: +{_bonus_pts} points*"
                    tline = build_tier_progress_line(o['user_id'])
                    if tline:
                        msg += f"\n\n{tline}"
                except Exception: pass

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

async def _show_payment_screen(q, context, p, qty, update=None):
    total_price = _get_eff_price(p) * qty
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
        
    from database import get_user, deduct_points, create_order, get_order
    from config import POINTS_PER_DOLLAR, ADMIN_ID
    
    user = get_user(q.from_user.id)
    # 🔧 CRITICAL BUG FIX: `'points' in user` on a sqlite3.Row checks VALUES,
    # not keys → it was always False → balance read as 0 → NOBODY could buy with
    # wallet/points (always "Insufficient balance"). Use .keys() instead.
    balance = user['points'] if (user is not None and 'points' in user.keys()) else 0
    
    cost_usd = _get_eff_price(p) * qty
    cost_pts = int(cost_usd * POINTS_PER_DOLLAR)
    
    if balance < cost_pts:
        missing = cost_pts - balance
        txt = (f"❌ *Insufficient Wallet Balance*\n"
               f"━━━━━━━━━━━━━━━━━━━━\n\n"
               f"📦 Product: *{_fmt_msg_name(p['name'])}* (x{qty})\n"
               f"💰 Required: *{cost_pts} 💎*\n"
               f"💳 Your Balance: *{balance} 💎*\n"
               f"📉 Short by: *{missing} 💎*\n\n"
               f"_Top up your points balance to complete this purchase._")
        
        kb = [
            [InlineKeyboardButton("💎 Buy More Points", callback_data="buy_points")],
            [InlineKeyboardButton("🔙 Back to Payment Methods", callback_data=f"buy_{pid}" if qty == 1 else f"buyx_{pid}")]
        ]
        await _safe_send(q, context, txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    # --- 🟢 SUFFICIENT POINTS: Process Instant Checkout ---
    deduct_points(q.from_user.id, cost_pts)
    new_balance = balance - cost_pts
    
    un = q.from_user.username or q.from_user.first_name
    creds = context.user_data.pop('order_creds', '')
    pname = p['name'] if qty == 1 else f"{p['name']} × {qty}"
    oid = create_order(q.from_user.id, un, pid, pname, cost_usd, 'wallet', '', cost_pts, 'PTS', 'product', creds)
    
    await _safe_send(q, context,
        f"✅ *Wallet Payment Successful!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Old Balance: `{balance}` 💎\n"
        f"➖ Deducted: `-{cost_pts}` 💎\n"
        f"💳 New Balance: *{new_balance}* 💎\n\n"
        f"⏳ Processing your order...",
        parse_mode="Markdown")

    order = get_order(oid)
    await fulfill_paid_product_order(context.bot, order, cost_pts,
                                     payment_method_label=f"Wallet / Points (-{cost_pts} 💎)",
                                     award_bonus=False)



