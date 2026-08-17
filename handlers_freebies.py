# ============================================================
# 🎁 v170.13 — FREEBIES (free products for every user)
# ============================================================
# User demand:
#   - Persistent reply-keyboard button "🎁 Freebies"
#   - Free products har user free claim kar sake (pehli baar 0 referrals)
#   - Admin settings: kaunsa product freebie hai, claim limit (kitni baar),
#     reclaim_refs (dobara claim ke liye referrals chahiye)
# Freebies = free-via-referrals (product_free_claim) se ALAG system hai.
# ============================================================

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID, SHOP_NAME
from utils import escape_md, smart_text_and_mode, html_strip_tags

logger = logging.getLogger(__name__)


def _r(key, default="", user_id=None):
    """Editable response with fallback."""
    try:
        from database import get_response_with_auto_register
        from config import DEFAULT_RESPONSES
        return get_response_with_auto_register(key, DEFAULT_RESPONSES.get(key, default))
    except Exception:
        return default


async def _safe_edit(q, text, **kwargs):
    try:
        await q.edit_message_text(text, **kwargs)
        return
    except Exception:
        if "parse" in str(kwargs).lower() and "parse_mode" in kwargs:
            k = dict(kwargs); k.pop("parse_mode", None)
            try:
                await q.edit_message_text(text, **k); return
            except Exception:
                pass
    try:
        await q.message.reply_text(text, **kwargs)
    except Exception:
        pass


def _clean_name(raw, limit=28):
    from utils import html_strip_tags
    s = html_strip_tags(str(raw or "")) or "Product"
    return s[:limit]


# ════════════════════════════════════════════════════════════════
# 👤 USER FLOW
# ════════════════════════════════════════════════════════════════

async def freebies_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎁 Freebies list (inline callback se) — enabled freebie products."""
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    uid = q.from_user.id
    await _show_freebies_menu(q, uid, from_text=False)


async def freebies_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎁 Freebies list (persistent reply-keyboard button se — text trigger)."""
    msg = update.message
    uid = update.effective_user.id
    await _show_freebies_menu(msg, uid, from_text=True)


async def _show_freebies_menu(target, uid, from_text=False):
    from database import get_all_freebie_products
    freebies = get_all_freebie_products()
    try:
        from button_system import make_premium_button, extract_emoji_from_html
        _have = True
    except Exception:
        _have = False

    try:
        from keyboards import _rb
    except Exception:
        _rb = None

    def _back_btn():
        if _rb:
            b = _rb("freebie_back", callback_data="main_menu")
            return b if b else InlineKeyboardButton("🔙 Back", callback_data="main_menu")
        return InlineKeyboardButton("🔙 Back", callback_data="main_menu")

    if not freebies:
        txt = _r("freebies_empty",
                 "🎁 *Freebies*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                 "_No free products available right now. Check back soon!_")
        kb = InlineKeyboardMarkup([[_back_btn()]])
    else:
        header = _r("freebies_menu_header",
                    "🎁 *Freebies*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    "_These products are 100% FREE — claim yours now!_")
        lines = header.split("\n") + [""]
        kb_rows = []
        for f in freebies:
            pid = int(f.get("product_id") or 0)
            raw = str(f.get("name") or f"#{pid}")
            plain, eid = raw, ""
            if _have:
                try:
                    _eid, _plain = extract_emoji_from_html(raw)
                    if _plain:
                        plain = _plain
                    eid = _eid or ""
                except Exception:
                    pass
            lines.append(f"🎁 {plain[:30]}")
            if _have:
                kb_rows.append([make_premium_button(
                    f"🎁 Claim — {plain[:22]}", emoji_id=eid or None,
                    style="success", callback_data=f"freebie_open_{pid}")])
            else:
                kb_rows.append([InlineKeyboardButton(
                    f"🎁 Claim — {plain[:22]}", callback_data=f"freebie_open_{pid}")])
        kb_rows.append([_back_btn()])
        txt = "\n".join(lines)
        kb = InlineKeyboardMarkup(kb_rows)

    _st, _sm = smart_text_and_mode(txt, "Markdown")
    try:
        if from_text:
            await target.reply_text(_st, parse_mode=_sm, reply_markup=kb)
        else:
            await target.edit_message_text(_st, parse_mode=_sm, reply_markup=kb)
    except Exception:
        try:
            if from_text:
                await target.reply_text(txt, reply_markup=kb)
            else:
                await target.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass


async def freebie_open_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User taps a freebie product → claim screen (status + rules)."""
    q = update.callback_query
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_open_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id")
        return
    uid = q.from_user.id
    await _show_freebie_product(q, uid, pid)


async def _show_freebie_product(q, uid, pid):
    from database import (get_product, get_freebie_config, freebie_claims_count,
                          get_referral_count)
    prod = get_product(pid)
    cfg = get_freebie_config(pid)
    if not prod or not cfg.get("enabled"):
        await _safe_edit(q, "ℹ️ This product is not available for free claim right now.")
        return

    claims = freebie_claims_count(uid, pid)
    limit = int(cfg.get("claim_limit") or 1)
    reclaim = int(cfg.get("reclaim_refs") or 0)
    refs_have = int(get_referral_count(uid) or 0)

    # Required refs for THIS claim: pehli claim 0, har agli claim reclaim × claims
    required_refs = 0 if claims == 0 else reclaim * claims

    try:
        from keyboards import _rb
    except Exception:
        _rb = None
    def _btn(reg_id, fallback_label, cb):
        if _rb:
            b = _rb(reg_id, callback_data=cb)
            return b if b else InlineKeyboardButton(fallback_label, callback_data=cb)
        return InlineKeyboardButton(fallback_label, callback_data=cb)
    def _back_btn():
        return _btn("freebie_back", "🔙 Back", "main_menu")
    def _menu_btn():
        return _btn("freebie_menu_back", "🎁 Freebies", "freebies_menu")

    # 🆕 v170.29: product name PREMIUM emoji ke saath render (pehle simple emoji)
    try:
        from handlers_order import _fmt_msg_name
        name_line = _fmt_msg_name(prod.get("name") or "")
    except Exception:
        name_line = escape_md(_clean_name(prod.get("name") or "", 40))

    lines = [
        f"🎁 {name_line}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👥 Your claims: *{claims}*"
    ]
    if limit > 0:
        lines.append(f"🔢 Claim limit: *{limit}* (total)")
    else:
        lines.append("🔢 Claim limit: *Unlimited*")
    if reclaim > 0:
        lines.append(f"🔁 Re-claim rule: *{reclaim} referrals* per extra claim")
    lines.append("")

    # limit check
    if limit > 0 and claims >= limit and reclaim == 0:
        lines.append("❌ You reached the claim limit for this product.")
        kb = InlineKeyboardMarkup([[
            _menu_btn(),
            _back_btn(),
        ]])
    elif required_refs > 0 and refs_have < required_refs:
        lines.append(f"🔁 To claim again you need *{required_refs} referrals*.")
        lines.append(f"👥 Your referrals: *{refs_have}*")
        lines.append(f"⭐ You need *{required_refs - refs_have}* more.")
        kb = InlineKeyboardMarkup([
            [_btn("freebie_refer_earn", "🔗 Refer & Earn", "referral")],
            [_menu_btn(), _back_btn()],
        ])
    else:
        lines.append("✅ Ready to claim — FREE!")
        if required_refs > 0:
            lines.append(f"🔁 ({required_refs} referrals requirement met)")
        kb = InlineKeyboardMarkup([
            [_btn("freebie_claim_now", "🎉 Claim FREE Now", f"freebie_do_{pid}")],
            [_menu_btn(), _back_btn()],
        ])

    txt = "\n".join(lines)
    _st, _sm = smart_text_and_mode(txt, "Markdown")
    await _safe_edit(q, _st, parse_mode=_sm, reply_markup=kb)


async def freebie_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎉 User confirms freebie claim → deliver product."""
    q = update.callback_query
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_do_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id")
        return
    uid = q.from_user.id
    user_obj = q.from_user

    from database import (get_product, get_freebie_config, freebie_claims_count,
                          get_referral_count, create_order, update_order_status,
                          get_order)
    prod = get_product(pid)
    cfg = get_freebie_config(pid)
    if not prod or not cfg.get("enabled"):
        await _safe_edit(q, "ℹ️ This freebie is not available right now.")
        return

    claims = freebie_claims_count(uid, pid)
    limit = int(cfg.get("claim_limit") or 1)
    reclaim = int(cfg.get("reclaim_refs") or 0)
    refs_have = int(get_referral_count(uid) or 0)
    required_refs = 0 if claims == 0 else reclaim * claims

    # limit + refs gates (race-safe re-check)
    if limit > 0 and claims >= limit and reclaim == 0:
        await _safe_edit(q, "❌ Claim limit reached.")
        return
    if required_refs > 0 and refs_have < required_refs:
        await _show_freebie_product(q, uid, pid)
        return

    # stock check
    try:
        stock_val = int(prod.get("stock") or 0)
    except Exception:
        stock_val = 0
    if stock_val <= 0:
        await _safe_edit(q, "😔 Out of stock right now. Please try later.",
                         reply_markup=InlineKeyboardMarkup([[
                             InlineKeyboardButton("🎁 Freebies", callback_data="freebies_menu")]]))
        return

    # create FREE order
    uname = user_obj.username or user_obj.first_name or ""
    try:
        oid = create_order(uid, uname, pid, prod.get("name") or "", 0.0,
                           method="freebie", bname="", bamt=0, bcur="",
                           otype="product", creds="")
        update_order_status(oid, "paid")
    except Exception as e:
        logger.exception("[freebie] create_order failed")
        await _safe_edit(q, f"⚠️ Could not create order: `{e}`", parse_mode="Markdown")
        return

    # record claim
    try:
        from database import record_freebie_claim
        record_freebie_claim(uid, pid, oid, required_refs)
    except Exception as e:
        logger.exception("[freebie] record failed")

    # 🆕 v170.28: DETAILED admin notification — supplier orders-delivered wali
    # tarah (username + premium emoji + claim # + PKT time + cost).
    try:
        from utils import notify_admin, fmt_price
        from datetime import datetime, timezone, timedelta
        from handlers_order import _fmt_msg_name
        # buyer name + @username
        fname = user_obj.first_name or ''
        uname = user_obj.username or ''
        try:
            from database import get_user as _gu
            _urow = _gu(uid)
            if _urow:
                if not fname:
                    fname = str(_urow.get('first_name') or '')
                if not uname:
                    uname = str(_urow.get('username') or '')
        except Exception:
            pass
        def _sp(s):
            try:
                import html as _h
                from utils import html_strip_tags as _hst
                s = _h.escape(_hst(s or '') or '')
            except Exception:
                pass
            return (str(s).replace('`', "'").replace('_', '&#95;')
                     .replace('*', '&#42;').replace('[', '&#91;').replace(']', '&#93;'))
        name_line = f"{_sp(fname)} (@{_sp(uname)})" if (fname and uname) else (_sp(fname) or _sp(uname) or '—')
        pk_time = datetime.now(timezone(timedelta(hours=5))).strftime('%Y-%m-%d %I:%M:%S %p PKT')
        try:
            cost = float((dict(prod) or {}).get('cost_price') or 0)
        except Exception:
            cost = 0.0
        await notify_admin(context.bot,
            f"🎁 *FREEBIE CLAIMED!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛒 Order: `#{oid}`\n"
            f"🕒 Time: `{pk_time}`\n"
            f"👤 Customer: `{name_line}` (`{uid}`)\n"
            f"📦 Product: {_fmt_msg_name(prod.get('name'))}\n"
            f"🔁 Claim: #{claims + 1}\n"
            f"💳 Payment: `freebie`\n"
            f"💰 Cost: `{fmt_price(cost)}` · Sold: `$0`\n"
            f"📉 Loss: `{fmt_price(-cost)}`")
    except Exception:
        pass

    # deliver via central router
    try:
        from handlers_order import fulfill_paid_product_order
        order = get_order(oid)
        await fulfill_paid_product_order(
            context.bot, order, paid_amount=0.0,
            payment_method_label="🎁 FREEBIE", award_bonus=False)
    except Exception as e:
        logger.exception("[freebie] fulfill failed")
        try:
            await context.bot.send_message(uid, "⚠️ Delivery hiccup — admin will deliver manually.")
        except Exception:
            pass

    # confirmation
    try:
        confirm = _r("freebie_success",
                     "🎉 *Freebie Claimed!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                     "📦 {product}\n✅ Delivered FREE above.\n\n"
                     "🔁 To claim again: {reclaim} referrals.")
        confirm = confirm.replace("{product}", escape_md(_clean_name(prod.get('name') or '', 60)))
        confirm = confirm.replace("{reclaim}", str(reclaim))
        _st, _sm = smart_text_and_mode(confirm, "Markdown")
        await context.bot.send_message(uid, _st, parse_mode=_sm,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎁 Freebies", callback_data="freebies_menu")]]))
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# 🛠️ ADMIN PANEL
# ════════════════════════════════════════════════════════════════

async def freebies_admin_panel_callback(update, context):
    """🎁 Admin freebies panel — warranty/refund style product list
    (premium emoji + green/red toggle) + tap → rules."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    from database import get_all_products, get_freebie_config
    prods = get_all_products()
    try:
        from button_system import make_premium_button, extract_emoji_from_html
        _have = True
    except Exception:
        _have = False
    lines = ["🎁 *Freebies Admin*",
             "━━━━━━━━━━━━━━━━━━━━",
             "_(🟢 = freebie ON · 🔴 = OFF — tap kar ke rules set karo)_", ""]
    kb = []
    for p in prods[:14]:
        pid = int(p["id"])
        cfg = get_freebie_config(pid)
        on = bool(cfg.get("enabled"))
        raw = str(p.get("name") or f"#{pid}")
        plain, eid = raw, ""
        if _have:
            try:
                _eid, _plain = extract_emoji_from_html(raw)
                if _plain:
                    plain = _plain
                eid = _eid or ""
            except Exception:
                pass
        lines.append(f"{'✅' if on else '⛔'} #{pid} · {plain[:28]}")
        if _have:
            kb.append([make_premium_button(
                f"{'🟢 ON' if on else '🔴 OFF'} — {plain[:20]}",
                emoji_id=eid or None,
                style="success" if on else "danger",
                callback_data=f"freebie_cfg_{pid}")])
        else:
            kb.append([InlineKeyboardButton(
                f"{'🟢 ON' if on else '🔴 OFF'} — {plain[:20]}",
                callback_data=f"freebie_cfg_{pid}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def _render_freebie_config(q, pid):
    """Shared render — freebie config screen (toggle + rules)."""
    from database import get_product, get_freebie_config
    prod = get_product(pid)
    cfg = get_freebie_config(pid)
    name = _clean_name(prod.get("name") or "", 40) if prod else f"#{pid}"
    on = "🟢 ON" if cfg.get("enabled") else "🔴 OFF"
    text = (
        f"🎁 *Freebie — #{pid}*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 {escape_md(name)}\n"
        f"Status: *{on}*\n"
        f"🔢 Claim limit: *{cfg.get('claim_limit')}* (0=unlimited)\n"
        f"🔁 Re-claim refs: *{cfg.get('reclaim_refs')}* (0=free forever)\n\n"
        f"_Claim rule: pehli claim FREE; har agli claim ke liye "
        f"reclaim_refs × claims referrals chahiye._"
    )
    kb = [
        [InlineKeyboardButton("🔄 Toggle ON/OFF", callback_data=f"freebie_toggle_{pid}")],
        [InlineKeyboardButton("🔢 Set Claim Limit", callback_data=f"freebie_limit_{pid}"),
         InlineKeyboardButton("🔁 Set Re-claim Refs", callback_data=f"freebie_refs_{pid}")],
        [InlineKeyboardButton("🔙 Freebies", callback_data="freebies_admin_panel")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def freebie_config_callback(update, context):
    """Per-product freebie config: toggle + claim limit + reclaim refs."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_cfg_", ""))
    except Exception:
        return
    await _render_freebie_config(q, pid)


async def freebie_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        pid = int(q.data.replace("freebie_toggle_", ""))
    except Exception:
        return
    from database import get_freebie_config, set_freebie_config
    cfg = get_freebie_config(pid)
    new_on = not bool(cfg.get("enabled"))
    set_freebie_config(pid, enabled=new_on)
    # 🐛 v170.16 FIX: pehle koi response nahi aata tha (screen refresh kafi
    # nahi tha admin ko pata nahi chalta on hua ya off). Ab clear TOAST/ALERT:
    try:
        await q.answer(
            f"{'🟢 Freebie ON ✅' if new_on else '🔴 Freebie OFF ❌'}",
            show_alert=True)
    except Exception:
        pass
    # 🐛 v170.14 FIX: pehle freebie_config_callback ko call karta tha jo q.data
    # se "freebie_cfg_" parse karti thi → "freebie_toggle_101" par int() fail →
    # silent return → screen kabhi refresh nahi hoti. Ab shared render directly.
    await _render_freebie_config(q, pid)


async def freebie_limit_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_limit_", ""))
    except Exception:
        return
    context.user_data["freebie_step"] = {"action": "limit", "pid": pid}
    await _safe_edit(q,
        f"🔢 *Claim limit for #{pid}*\n\n"
        f"Send number (kitni baar claim kar sake; `0` = unlimited):\n"
        f"_(/cancel to cancel)_", parse_mode="Markdown")


async def freebie_refs_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_refs_", ""))
    except Exception:
        return
    context.user_data["freebie_step"] = {"action": "refs", "pid": pid}
    await _safe_edit(q,
        f"🔁 *Re-claim referrals for #{pid}*\n\n"
        f"Send number (dobara claim ke liye kitne referrals; `0` = free forever):\n"
        f"_(/cancel to cancel)_", parse_mode="Markdown")


async def freebie_step_received(update, context):
    """Admin text input: claim limit ya reclaim refs."""
    step = context.user_data.get("freebie_step")
    if not step:
        return False
    txt = (update.message.text or "").strip()
    if txt == "/cancel":
        context.user_data.pop("freebie_step", None)
        await update.message.reply_text("❌ Cancelled.")
        return True
    try:
        val = int(txt)
        if val < 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("❌ Enter a whole number ≥ 0.")
        return True
    from database import set_freebie_config
    pid = int(step.get("pid") or 0)
    if step.get("action") == "limit":
        set_freebie_config(pid, claim_limit=val)
        await update.message.reply_text(
            f"✅ Claim limit for #{pid} → *{val}*" + (" (unlimited)" if val == 0 else ""),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data=f"freebie_cfg_{pid}")]]))
    else:
        set_freebie_config(pid, reclaim_refs=val)
        await update.message.reply_text(
            f"✅ Re-claim referrals for #{pid} → *{val}*" + (" (free forever)" if val == 0 else ""),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data=f"freebie_cfg_{pid}")]]))
    context.user_data.pop("freebie_step", None)
    return True
