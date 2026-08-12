# ============================================================
# ⭐ v161.25 — TELEGRAM STARS PAYMENT (Buy Points + Products)
# ============================================================
# How it works:
#   1. User picks ⭐ Telegram Stars as payment method (Buy Points or product)
#   2. Bot converts USD → Stars (rate: stars_per_dollar, default 120)
#   3. Bot sends a Telegram native invoice (currency XTR, provider_token "")
#   4. User pays with Stars in Telegram's payment window
#   5. Telegram sends pre_checkout_query → bot answers OK
#   6. Telegram sends successful_payment message → bot credits points /
#      delivers product + sends the nice "Deposit Successful!" message
#
# No BotFather setup needed — Stars is available to ALL bots automatically.
# ============================================================
import json
import logging
import os
import time

from telegram import LabeledPrice, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

STARS_METHOD = "telegram_stars"

# Amount rounding guard: Telegram Stars amounts must be positive whole integers
# and the invoice total (sum of prices) must fit a signed 32-bit int.


def _stars_per_dollar():
    """Admin-editable rate: how many Stars = $1. Default 120 (like Stock Lara)."""
    try:
        from database import get_setting
        val = float(get_setting("stars_per_dollar", "120") or 120)
        return max(1.0, val)
    except Exception:
        return 120.0


def usd_to_stars(usd: float) -> int:
    """Convert USD → whole Stars (min 1)."""
    try:
        stars = int(round(float(usd or 0) * _stars_per_dollar()))
        return max(1, stars)
    except Exception:
        return 120


def _make_payload(order_id, user_id, mode, product_id=0, qty=1):
    """Invoice payload — returned verbatim in successful_payment."""
    return json.dumps({
        "oid": int(order_id or 0),
        "uid": int(user_id or 0),
        "mode": mode,          # 'points' | 'product'
        "pid": int(product_id or 0),
        "qty": int(qty or 1),
        "t": int(time.time()),
    }, separators=(",", ":"))


def _parse_payload(raw):
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}


def _stars_instructions_text(order_id, amount_usd, stars, product_name=""):
    """Instructions shown before the invoice (editable response)."""
    try:
        from database import get_response_with_auto_register
        from config import DEFAULT_RESPONSES
        key = "payment_stars_checkout" if product_name else "payment_stars_deposit"
        fallback_key = "stars_pay_instructions"
        tpl = get_response_with_auto_register(
            key, DEFAULT_RESPONSES.get(key, DEFAULT_RESPONSES.get(fallback_key, "")))
    except Exception:
        tpl = ""
    if tpl:
        try:
            return tpl.format(
                order_id=order_id, amount=f"{float(amount_usd):.2f}",
                stars=stars, rate=f"{_stars_per_dollar():g}",
                product=product_name or "Points Deposit")
        except Exception:
            pass
    return (
        "⭐ *Pay with Telegram Stars*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🧾 Order: `#{order_id}`\n"
        f"📦 Product: *{product_name or 'Points Deposit'}*\n"
        f"💰 Amount: *${float(amount_usd):.2f}*\n"
        f"⭐ Stars needed: *{stars} Stars*\n"
        f"📊 Rate: 1$ = {_stars_per_dollar():g} Stars\n\n"
        "👇 Tap the button below — Telegram will open its secure payment window.\n"
        "_No ID or screenshot needed — Stars credit instantly._"
    )


# ────────────────────────────────────────────────────────────
# 🛒 ENTRY — from Buy Points amount screen (ptspay_stars_{amt})
# ────────────────────────────────────────────────────────────
async def points_stars_callback(update, context):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    uid = q.from_user.id
    try:
        amt = float(q.data.replace("ptspay_stars_", ""))
    except Exception:
        amt = 0.0
    if amt < 1:
        await q.edit_message_text("❌ Minimum deposit is $1.")
        return

    stars = usd_to_stars(amt)
    try:
        from database import create_order, update_order_status
        from utils import points_from_usd, fmt_points
        pts = points_from_usd(amt)
        pname = f"💎 {fmt_points(pts)} Points"
        oid = create_order(uid, q.from_user.first_name or str(uid), 0,
                           pname, amt, STARS_METHOD, '', amt, 'XTR', 'points')
        update_order_status(oid, 'stars_waiting')
    except Exception as e:
        logger.exception(f"[Stars] create points order failed: {e}")
        await q.edit_message_text("❌ Could not start Stars payment. Please try again.")
        return

    payload = _make_payload(oid, uid, "points")
    text = _stars_instructions_text(oid, amt, stars)
    await _send_stars_invoice(context, q, oid, uid, "⭐ Deposit Points",
                              text, payload, stars)


# ────────────────────────────────────────────────────────────
# 🛒 ENTRY — product order (pay_stars_{pid}_{qty})
# ────────────────────────────────────────────────────────────
async def product_stars_callback(update, context):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    uid = q.from_user.id
    parts = (q.data or "").split("_")
    try:
        pid = int(parts[2])
        qty = int(parts[3]) if len(parts) > 3 else 1
    except Exception:
        await q.edit_message_text("❌ Invalid product.")
        return
    try:
        from database import get_product
        p = get_product(pid)
        if not p:
            await q.edit_message_text("❌ Product not found.")
            return
        from handlers_order import _get_eff_price
        total = float(_get_eff_price(p)) * qty
        pname = p["name"] if qty == 1 else f"{p['name']} × {qty}"
    except Exception as e:
        logger.exception(f"[Stars] product lookup failed: {e}")
        await q.edit_message_text("❌ Could not load product.")
        return

    stars = usd_to_stars(total)
    try:
        from database import create_order, update_order_status
        creds = (context.user_data or {}).pop('order_creds', '')
        oid = create_order(uid, q.from_user.first_name or str(uid), pid,
                           pname, total, STARS_METHOD, '', total, 'XTR', 'product', creds, qty=qty)
        update_order_status(oid, 'stars_waiting')
    except Exception as e:
        logger.exception(f"[Stars] create product order failed: {e}")
        await q.edit_message_text("❌ Could not start Stars payment.")
        return

    payload = _make_payload(oid, uid, "product", product_id=pid, qty=qty)
    text = _stars_instructions_text(oid, total, stars, product_name=pname)
    await _send_stars_invoice(context, q, oid, uid, "⭐ Buy Product",
                              text, payload, stars)


# ────────────────────────────────────────────────────────────
# 📨 SEND INVOICE
# ────────────────────────────────────────────────────────────
async def _send_stars_invoice(context, q, oid, uid, title, text, payload, stars):
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from button_system import build_button as _bb

        stars = max(1, int(stars))
        # Telegram requires: positive amounts, total fits int32, label sane.
        prices = [LabeledPrice("Deposit", stars)]
        try:
            btn = _bb("pay_stars_pay", f"⭐ Pay {stars} Stars",
                      callback_data=f"stars_pay_{oid}", force_default=True)
        except Exception:
            btn = InlineKeyboardButton(f"⭐ Pay {stars} Stars",
                                       callback_data=f"stars_pay_{oid}")
        try:
            cancel_btn = _bb("nav_pay_cancel", "❌ Cancel",
                             callback_data="cancel_order", force_default=True)
        except Exception:
            cancel_btn = InlineKeyboardButton("❌ Cancel", callback_data="cancel_order")
        kb = InlineKeyboardMarkup([[btn], [cancel_btn]])
        # Show instructions first, then invoice button via edit
        from handlers_order import _safe_send
        await _safe_send(q, context, text, reply_markup=kb)
        # Keep the real invoice for when user taps the pay button — we store it
        # in user_data and send on tap (avoids double-invoice confusion).
        context.user_data['stars_invoice'] = {
            "oid": int(oid), "title": title, "payload": payload,
            "stars": stars, "desc": text,
        }
    except Exception as e:
        logger.exception(f"[Stars] send invoice setup failed: {e}")
        try:
            await q.edit_message_text("❌ Stars invoice could not be created. Please try again.")
        except Exception:
            pass


# ────────────────────────────────────────────────────────────
# ⭐ TAP "Pay X Stars" → actually send the native invoice
# ────────────────────────────────────────────────────────────
async def stars_pay_callback(update, context):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    oid = 0
    try:
        oid = int((q.data or "").replace("stars_pay_", ""))
    except Exception:
        oid = 0
    inv = (context.user_data or {}).get("stars_invoice") or {}
    if not inv or int(inv.get("oid") or 0) != oid:
        await q.answer("⚠️ Invoice expired — please start again.", show_alert=True)
        return
    uid = q.from_user.id
    stars = int(inv.get("stars") or 120)
    title = str(inv.get("title") or "Bite Store Deposit")
    payload = str(inv.get("payload") or "")
    desc = str(inv.get("desc") or "")
    try:
        await context.bot.send_invoice(
            chat_id=uid,
            title=title,
            description=desc[:255],
            payload=payload,
            provider_token="",          # EMPTY = Telegram Stars
            currency="XTR",             # Stars currency code
            prices=[LabeledPrice("Deposit", stars)],
        )
        try:
            await q.delete_message()
        except Exception:
            pass
    except Exception as e:
        logger.exception(f"[Stars] send_invoice failed: {e}")
        try:
            await q.answer("❌ Could not open payment. Try again.", show_alert=True)
        except Exception:
            pass


# ────────────────────────────────────────────────────────────
# ✅ PRE-CHECKOUT — Telegram asks "can this payment go through?"
# ────────────────────────────────────────────────────────────
async def stars_precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.pre_checkout_query
    payload = _parse_payload(getattr(q, "invoice_payload", ""))
    oid = int(payload.get("oid") or 0)
    if not oid:
        try:
            await q.answer(ok=False, error_message="Invalid payment — please start again.")
        except Exception:
            pass
        return
    # Always OK — Stars payment is instant and safe.
    try:
        await q.answer(ok=True)
    except Exception as e:
        logger.warning(f"[Stars] pre-checkout answer failed: {e}")


# ────────────────────────────────────────────────────────────
# 🎉 SUCCESSFUL PAYMENT — Telegram confirms Stars paid
# ────────────────────────────────────────────────────────────
async def stars_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = msg.from_user.id
    pay = getattr(msg, "successful_payment", None)
    if pay is None:
        return
    payload = _parse_payload(getattr(pay, "invoice_payload", ""))
    oid = int(payload.get("oid") or 0)
    mode = payload.get("mode") or "points"
    stars = int(getattr(pay, "total_amount", 0) or 0)
    charge_id = str(getattr(pay, "telegram_payment_charge_id", "") or "")
    currency = str(getattr(pay, "currency", "") or "")

    logger.info(f"[Stars] payment OK uid={uid} oid={oid} stars={stars} charge={charge_id}")

    try:
        from database import (get_order, update_order_status, add_points,
                              mark_txid_used, update_order_txid,
                              save_order_delivery_content, add_order_delivery,
                              get_connection)
        o = get_order(oid) if oid else None
        if not o:
            await msg.reply_text("✅ Payment received! Order not found — contact support.")
            return
        if o["status"] == "delivered":
            await msg.reply_text("✅ Payment already processed.")
            return

        # Dedup: Stars charge id as txid
        if charge_id:
            try:
                used = mark_txid_used(charge_id, uid, oid, float(o.get("price") or 0), "XTR")
                if not used:
                    await msg.reply_text("⚠️ This payment was already used.")
                    return
                update_order_txid(oid, charge_id)
            except Exception:
                pass

        if mode == "product" or (o.get("order_type") or "") == "product":
            # Deliver product exactly like other payments
            from handlers_order import fulfill_paid_product_order
            ok, msg2 = await fulfill_paid_product_order(
                context.bot, o, float(o.get("price") or 0),
                payment_method_label="TELEGRAM STARS")
            try:
                if not ok:
                    await msg.reply_text(f"⚠️ Payment received. Order processing: {msg2}")
            except Exception:
                pass
            return

        # Points deposit
        amount = float(o.get("price") or o.get("binance_amount") or 0)
        try:
            from utils import points_from_usd
            pts = points_from_usd(amount)
        except Exception:
            pts = int(round(amount * 100))
        add_points(uid, pts, tx_type="telegram_stars",
                   description="Telegram Stars deposit",
                   event_id=f"stars_{charge_id or oid}")
        update_order_status(oid, "delivered")
        # Deposit success message (editable response stars_payment_success)
        try:
            from database import get_response_with_auto_register
            from config import DEFAULT_RESPONSES
            from utils import fmt_points
            tpl = get_response_with_auto_register(
                "stars_payment_success",
                DEFAULT_RESPONSES.get("stars_payment_success", ""))
            if tpl:
                msg_text = tpl.format(points=fmt_points(pts), amount=f"{amount:.2f}",
                                      order_id=oid)
                from utils import smart_text_and_mode
                s_txt, s_mode = smart_text_and_mode(msg_text, "Markdown")
                await msg.reply_text(s_txt, parse_mode=s_mode)
            else:
                from handlers_order import _send_deposit_success
                await _send_deposit_success(context.bot, o, amount)
        except Exception:
            try:
                from utils import fmt_points, smart_text_and_mode
                fb_text = (
                    f"🎉 *Deposit Successful!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"✅ Your payment has been confirmed.\n"
                    f"💎 Points Added: *{fmt_points(pts)}*\n"
                    f"💰 Amount: *${amount:.2f}*\n"
                    f"🧾 Order ID: *#{oid}*\n\n"
                    f"_Thank you for your deposit!_"
                )
                s_txt, s_mode = smart_text_and_mode(fb_text, "Markdown")
                await msg.reply_text(s_txt, parse_mode=s_mode)
            except Exception:
                pass
    except Exception as e:
        logger.exception(f"[Stars] successful_payment processing failed: {e}")
        try:
            await msg.reply_text("⚠️ Payment received but processing hit an error — contact support.")
        except Exception:
            pass
