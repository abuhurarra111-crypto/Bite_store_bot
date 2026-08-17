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

    if not freebies:
        txt = _r("freebies_empty",
                 "🎁 *Freebies*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                 "_Abhi koi free product available nahi. Wapis aana!_")
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🛍️ Shop", callback_data="shop"),
            InlineKeyboardButton("🏠 Home", callback_data="main_menu"),
        ]])
    else:
        lines = ["🎁 *Freebies*", "━━━━━━━━━━━━━━━━━━━━",
                 "_Ye products bilkul FREE hain — claim karo!_", ""]
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
        kb_rows.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
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

    name = _clean_name(prod.get("name") or "", 40)
    lines = [
        f"🎁 *{escape_md(name)}*",
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
            InlineKeyboardButton("🎁 Freebies", callback_data="freebies_menu"),
            InlineKeyboardButton("🔙 Home", callback_data="main_menu"),
        ]])
    elif required_refs > 0 and refs_have < required_refs:
        lines.append(f"🔁 Dobara claim ke liye *{required_refs} referrals* chahiye.")
        lines.append(f"👥 Aapke referrals: *{refs_have}*")
        lines.append(f"⭐ Aur *{required_refs - refs_have}* chahiye.")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Refer & Earn", callback_data="referral")],
            [InlineKeyboardButton("🎁 Freebies", callback_data="freebies_menu"),
             InlineKeyboardButton("🔙 Home", callback_data="main_menu")],
        ])
    else:
        lines.append("✅ Ready to claim — FREE!")
        if required_refs > 0:
            lines.append(f"🔁 ({required_refs} referrals requirement met)")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎉 Claim FREE Now", callback_data=f"freebie_do_{pid}")],
            [InlineKeyboardButton("🎁 Freebies", callback_data="freebies_menu"),
             InlineKeyboardButton("🔙 Home", callback_data="main_menu")],
        ])

    txt = "\n".join(lines)
    await _safe_edit(q, txt, parse_mode="Markdown", reply_markup=kb)


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
        await _safe_edit(q, "ℹ️ Freebie ab available nahi.")
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

    # notify admin
    try:
        from utils import notify_admin
        await notify_admin(context.bot,
            f"🎁 *FREEBIE CLAIMED!*\n"
            f"👤 {escape_md(user_obj.first_name or '')} (`{uid}`)\n"
            f"📦 {escape_md(_clean_name(prod.get('name') or '', 60))}\n"
            f"🔁 Claim #{claims + 1}\n"
            f"🧾 Order: `#{oid}`")
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
                     "🔁 Dobara claim ke liye: {reclaim} referrals.")
        confirm = confirm.replace("{product}", escape_md(_clean_name(prod.get('name') or '', 60)))
        confirm = confirm.replace("{reclaim}", str(reclaim))
        _st, _sm = smart_text_and_mode(confirm, "Markdown")
        await context.bot.send_message(uid, _st, parse_mode=_sm,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎁 Freebies", callback_data="freebies_menu"),
                 InlineKeyboardButton("🛍️ Shop", callback_data="shop")]]))
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# 🛠️ ADMIN PANEL
# ════════════════════════════════════════════════════════════════

async def freebies_admin_panel_callback(update, context):
    """🎁 Admin freebies panel — list products, toggle freebie, set rules."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    from database import get_all_products, get_freebie_config
    prods = get_all_products()
    lines = ["🎁 *Freebies Admin*",
             "━━━━━━━━━━━━━━━━━━━━",
             "_(Tap a product → freebie ON/OFF + rules)_", ""]
    kb = []
    for p in prods[:12]:
        pid = int(p["id"])
        cfg = get_freebie_config(pid)
        on = "✅" if cfg.get("enabled") else "⬜"
        name = _clean_name(p.get("name") or "", 26)
        lines.append(f"{on} #{pid} · {name}")
        kb.append([InlineKeyboardButton(
            f"{on} #{pid} {name[:20]}",
            callback_data=f"freebie_cfg_{pid}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


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


async def freebie_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_toggle_", ""))
    except Exception:
        return
    from database import get_freebie_config, set_freebie_config
    cfg = get_freebie_config(pid)
    set_freebie_config(pid, enabled=not cfg.get("enabled"))
    await freebie_config_callback(update, context)


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
