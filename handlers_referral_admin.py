# ════════════════════════════════════════════════════════════════
# 🛡️ REFERRAL ABUSE ADMIN PANEL (v48)
# ════════════════════════════════════════════════════════════════
# Admin can:
#   - View recent referral attempts (counted + blocked)
#   - Ban / unban a user from giving or receiving referral credit
#   - Manually adjust someone's ref_points balance
# ════════════════════════════════════════════════════════════════
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID
from utils import escape_md, smart_text_and_mode, capture_user_text, safe_display
from database import (
    get_referral_log, get_referral_bans,
    ban_referrer, unban_referrer, is_referrer_banned,
    add_ref_points, get_ref_points, get_user,
    get_setting, set_setting,
)

logger = logging.getLogger(__name__)

REF_TPL_DEFAULTS = {
    "referrer": """🎉 *New Referral Joined!*\n━━━━━━━━━━━━━━━━━━━━\n\n👤 Referred user: *{referred_name}*\n🆔 Referred ID: `{referred_id}`\n\n✅ Reward: *+{reward_points} referral point*\n📊 Your direct referrals: *{total_referrals}*\n🎯 Next bonus: *{remaining_to_bonus}* more referrals → *+{milestone_bonus} wallet points* ($1)\n\nKeep sharing your link and earning rewards! 🚀""",
    "admin": """🎁 *New Direct Referral*\n━━━━━━━━━━━━━━━━━━━━\n\n👑 Referrer:\n• Name: *{referrer_name}*\n• Username: @{referrer_username}\n• ID: `{referrer_id}`\n\n🆕 Referred User:\n• Name: *{referred_name}*\n• Username: @{referred_username}\n• ID: `{referred_id}`\n\n🎯 Reward: +{reward_points} referral point\n📊 Referrer's direct referrals: {total_referrals}""",
    "milestone": """🏆 *Referral Milestone Unlocked!*\n━━━━━━━━━━━━━━━━━━━━\n\n🔥 You reached *{milestone_number} direct referrals*!\n🎁 Bonus reward: *+{milestone_bonus} wallet points* ($1)\n💎 Wallet bonus has been added to your balance.\n\nNext milestone: *{next_milestone} referrals* 🚀""",
    "product_referrer": """🎁 *Product Referral Counted!*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Product: *{product_name}*\n👤 New user: *{referred_name}*\n🆔 User ID: `{referred_id}`\n\n📊 Your progress: *{product_referrals}/{product_required}*\n🎯 Need *{product_remaining}* more referral(s) to claim this product free.\n\nKeep sharing this product link! 🚀""",
    "product_admin": """🎁 *Product Referral Counted*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Product: *{product_name}* (`#{product_id}`)\n📊 Progress: *{product_referrals}/{product_required}*\n🎯 Remaining: *{product_remaining}*\n\n👑 Referrer:\n• Name: *{referrer_name}*\n• Username: @{referrer_username}\n• ID: `{referrer_id}`\n\n🆕 Referred User:\n• Name: *{referred_name}*\n• Username: @{referred_username}\n• ID: `{referred_id}`""",
    "product_unlock": """🎉 *Free Product Unlocked!*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Product: *{product_name}*\n✅ Progress complete: *{product_referrals}/{product_required}*\n\nYou can now claim this product for FREE. Tap the button below.""",
}

REF_TPL_READYMADE = {
    "referrer": [
        REF_TPL_DEFAULTS["referrer"],
        """✅ *Referral Reward Added!*\n\nYour friend `{referred_id}` started the bot from your link.\n\n🎁 You earned *+{reward_points} referral point*.\n📊 Total direct referrals: *{total_referrals}*\n🏆 Bonus progress: *{remaining_to_bonus}* more for +{milestone_bonus} wallet points.""",
        """🚀 *Nice! New Referral*\n\n👤 {referred_name} (`{referred_id}`) joined via your link.\n💎 Reward: +{reward_points} referral point\n📈 Your total: {total_referrals}\n🎯 Every 20 referrals = +{milestone_bonus} wallet points.""",
    ],
    "admin": [
        REF_TPL_DEFAULTS["admin"],
        """🛡️ *Referral Counted*\n\nReferrer: {referrer_name} (`{referrer_id}`) @{referrer_username}\nNew User: {referred_name} (`{referred_id}`) @{referred_username}\nReward: +{reward_points} ref point\nTotal: {total_referrals}""",
        """🎁 *Referral Activity*\n━━━━━━━━━━━━━━━━━━━━\n`{referrer_id}` brought `{referred_id}`\nReferrer: {referrer_name}\nJoined user: {referred_name}\nTotal referrals: {total_referrals}""",
    ],
    "milestone": [
        REF_TPL_DEFAULTS["milestone"],
        """🎉 *20 Referral Bonus!*\n\nYou hit *{milestone_number}* referrals.\n+{milestone_bonus} wallet points have been added.\nNext target: {next_milestone}.""",
        """🏆 *Milestone Reward Paid*\n\nDirect referrals: {milestone_number}\nBonus: +{milestone_bonus} wallet points ($1)\nKeep going — next bonus at {next_milestone}!""",
    ],
    "product_referrer": [
        REF_TPL_DEFAULTS["product_referrer"],
        """📦 *Product Referral Progress*\n\n{referred_name} (`{referred_id}`) joined for *{product_name}*.\nProgress: {product_referrals}/{product_required}\nNeed {product_remaining} more to claim free.""",
        """🎁 *One Step Closer!*\n\nProduct: {product_name}\nNew referral ID: `{referred_id}`\nYour count: {product_referrals}/{product_required}\nRemaining: {product_remaining}""",
    ],
    "product_admin": [
        REF_TPL_DEFAULTS["product_admin"],
        """🛡️ *Product Referral*\nProduct: {product_name} (`#{product_id}`)\nReferrer: {referrer_name} `{referrer_id}`\nNew user: {referred_name} `{referred_id}`\nProgress: {product_referrals}/{product_required}""",
        """🎁 *Free-Claim Referral Counted*\n`{referrer_id}` brought `{referred_id}` for product `#{product_id}`.\nProduct: {product_name}\nRemaining: {product_remaining}""",
    ],
    "product_unlock": [
        REF_TPL_DEFAULTS["product_unlock"],
        """🎉 *Claim Ready!*\n\nYou completed {product_referrals}/{product_required} referrals for *{product_name}*.\nTap below to claim it free.""",
        """🏆 *Free Product Unlocked*\nProduct: {product_name}\nProgress: {product_referrals}/{product_required}\nClaim button is below.""",
    ],
}

REF_PLACEHOLDERS = """Placeholders:\n`{referrer_id}` `{referrer_name}` `{referrer_username}`\n`{referred_id}` `{referred_name}` `{referred_username}`\n`{reward_points}` `{total_referrals}` `{remaining_to_bonus}`\n`{milestone_bonus}` `{milestone_number}` `{next_milestone}`\nProduct-only: `{product_id}` `{product_name}` `{product_referrals}` `{product_required}` `{product_remaining}`"""


def _tpl_key(kind):
    return f"ref_tpl_{kind}"


async def _safe_edit(q, text, **kwargs):
    send_text, send_mode = smart_text_and_mode(text, kwargs.get("parse_mode", "Markdown"))
    send_kwargs = dict(kwargs); send_kwargs["parse_mode"] = send_mode
    try:
        await q.edit_message_text(send_text, **send_kwargs); return
    except Exception:
        pass
    try:
        await q.edit_message_caption(caption=send_text, **send_kwargs); return
    except Exception:
        pass
    try:
        await q.message.reply_text(send_text, **send_kwargs)
    except Exception:
        pass


def _panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Recent Referral Log", callback_data="refadm_log_all")],
        [InlineKeyboardButton("✅ Counted Only", callback_data="refadm_log_counted"),
         InlineKeyboardButton("🚫 Blocked Only", callback_data="refadm_log_blocked")],
        [InlineKeyboardButton("🔨 Ban a User",   callback_data="refadm_ban_start")],
        [InlineKeyboardButton("🔓 Unban a User", callback_data="refadm_unban_start")],
        [InlineKeyboardButton("📋 Banned List",  callback_data="refadm_banlist")],
        [InlineKeyboardButton("💎 Adjust Ref Points", callback_data="refadm_adjust_start")],
        [InlineKeyboardButton("✉️ Notification Templates", callback_data="refadm_tpl_panel")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")],
    ])


def _is_direct_referral(row):
    """🆕 v110: True if row is a DIRECT (general) referral, not a product-mode one.
    Product-mode entries store reason like 'product_ref_pid_5' or
    'dup_product_ref_pid_5'. Direct ones use 'ok' (or empty).
    """
    reason = (row.get("reason") or "").lower() if hasattr(row, "get") else \
             (row["reason"] or "").lower()
    return not reason.startswith("product_ref_pid_") and \
           not reason.startswith("dup_product_ref_pid_")


async def refadm_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the Referral Abuse panel.
    🆕 v55: cancels any pending refadm_step text-input flow.
    🆕 v110: Counts show only DIRECT (general) referrals. Product-mode
    referrals now have their own dedicated per-product tracker inside
    the Free-via-Referrals settings panel (👥 Referrals for This Product).
    """
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    # 🆕 v55: cancel any pending text-input flow
    context.user_data.pop("refadm_step", None)
    # Stats — filter out product-mode
    counted_all = get_referral_log(limit=10000, status="counted")
    blocked_all = get_referral_log(limit=10000, status="blocked")
    counted = [r for r in counted_all if _is_direct_referral(r)]
    blocked = [r for r in blocked_all if _is_direct_referral(r)]
    bans = get_referral_bans(limit=10000)
    text = (
        "🛡️ *Referral Abuse Control*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ Direct Counted Referrals: *{len(counted)}*\n"
        f"🚫 Blocked Attempts: *{len(blocked)}*\n"
        f"🔨 Currently Banned: *{len(bans)}*\n\n"
        "_Only DIRECT referrals (via general Refer & Earn link) shown here.\n"
        "For product-specific referrals see: Product → 🎁 Free via Referrals → 👥 Referrals for This Product._"
    )
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=_panel_kb())


async def refadm_log_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent referral log entries (counted / blocked / all).

    🆕 v110: Filters out product-mode referrals (they have their own
    per-product view). This panel is now DIRECT-ONLY.
    """
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    data = q.data.replace("refadm_log_", "")
    status_filter = None
    title = "📜 *All Direct Referral Attempts*"
    if data == "counted":
        status_filter = "counted"; title = "✅ *Direct Counted Referrals*"
    elif data == "blocked":
        status_filter = "blocked"; title = "🚫 *Blocked Referrals*"
    rows = get_referral_log(limit=200, status=status_filter)  # fetch more, filter after
    rows = [r for r in rows if _is_direct_referral(r)][:30]
    if not rows:
        body = "_No direct-referral entries yet._"
    else:
        lines = []
        for r in rows:
            icon = "✅" if r["status"] == "counted" else "🚫"
            at = (r["created_at"] or "")[:16].replace("T", " ") if r["created_at"] else ""
            reason = escape_md(r["reason"] or "")
            lines.append(
                f"{icon} `{r['referrer_id']}` → `{r['referred_id']}` "
                f"| _{at}_"
                + (f"\n    _{reason}_" if r["status"] == "blocked" and reason else "")
            )
        body = "\n".join(lines)
    text = f"{title}\n━━━━━━━━━━━━━━━━━━━━\n\n{body}"
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup([
                         [InlineKeyboardButton("🔙 Back", callback_data="refadm_panel")]
                     ]))


async def refadm_banlist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    bans = get_referral_bans(limit=50)
    if not bans:
        body = "_No banned users._"
    else:
        lines = []
        for b in bans:
            uid = b["user_id"]
            reason = escape_md(b.get("reason") or "")
            at = (b.get("banned_at") or "")[:16].replace("T", " ")
            lines.append(f"🔨 `{uid}` — _{at}_" + (f"\n    _{reason}_" if reason else ""))
        body = "\n".join(lines)
    await _safe_edit(q,
        f"📋 *Banned from Referral System*\n━━━━━━━━━━━━━━━━━━━━\n\n{body}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="refadm_panel")]]))


async def refadm_ban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data["refadm_step"] = "ban"
    await _safe_edit(q,
        "🔨 *Ban a User from Referral System*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📥 Send the user ID followed by an optional reason:\n"
        "_Format:_ `<user_id> [reason]`\n\n"
        "_Examples:_\n"
        "  `7105782769`\n"
        "  `7105782769 spammer using bots`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="refadm_panel")]]))


async def refadm_unban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data["refadm_step"] = "unban"
    await _safe_edit(q,
        "🔓 *Unban a User*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📥 Send the user ID to unban:\n"
        "_e.g._ `7105782769`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="refadm_panel")]]))


async def refadm_adjust_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data["refadm_step"] = "adjust"
    await _safe_edit(q,
        "💎 *Adjust a User's Ref Points*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📥 Send: `<user_id> <±amount>`\n\n"
        "_Examples:_\n"
        "  `7105782769 5`     (add 5 ref points)\n"
        "  `7105782769 -3`    (deduct 3 ref points)\n"
        "  `7105782769 =10`   (set balance to exactly 10)",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="refadm_panel")]]))


def _ref_tpl_panel_text_kb():
    text = (
        "✉️ *Referral Notification Templates*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Edit messages sent when a direct referral is counted.\n\n"
        "• 👤 Referrer message — sent to the user who invited someone\n"
        "• 🛡️ Admin message — sent to admin with both user details\n"
        "• 🏆 Milestone message — sent every 20 direct referrals when +10 wallet points are awarded\n\n"
        f"{REF_PLACEHOLDERS}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Direct Referrer Msg", callback_data="refadm_tpl_edit_referrer")],
        [InlineKeyboardButton("🛡️ Direct Admin Msg", callback_data="refadm_tpl_edit_admin")],
        [InlineKeyboardButton("🏆 Direct Milestone Msg", callback_data="refadm_tpl_edit_milestone")],
        [InlineKeyboardButton("📦 Product Referrer Msg", callback_data="refadm_tpl_edit_product_referrer")],
        [InlineKeyboardButton("🛡️ Product Admin Msg", callback_data="refadm_tpl_edit_product_admin")],
        [InlineKeyboardButton("🎉 Product Unlock Msg", callback_data="refadm_tpl_edit_product_unlock")],
        [InlineKeyboardButton("🎨 Readymade Templates", callback_data="refadm_tpl_ready_referrer")],
        [InlineKeyboardButton("♻️ Reset All Defaults", callback_data="refadm_tpl_reset_all")],
        [InlineKeyboardButton("🔙 Back", callback_data="refadm_panel")],
    ])
    return text, kb


async def refadm_tpl_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    text, kb = _ref_tpl_panel_text_kb()
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def refadm_tpl_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    kind = q.data.replace("refadm_tpl_edit_", "", 1)
    if kind not in REF_TPL_DEFAULTS:
        await q.answer("Invalid template", show_alert=True); return
    current = get_setting(_tpl_key(kind), REF_TPL_DEFAULTS[kind]) or REF_TPL_DEFAULTS[kind]
    context.user_data["refadm_step"] = f"tpl_{kind}"
    await _safe_edit(q,
        f"✏️ *Edit {kind.title()} Referral Template*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current template:\n`{escape_md(current[:900])}`\n\n"
        f"{REF_PLACEHOLDERS}\n\n"
        f"Send the new template as your next message.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="refadm_tpl_panel")]]))


async def refadm_tpl_ready_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    kind = q.data.replace("refadm_tpl_ready_", "", 1)
    if kind not in REF_TPL_READYMADE:
        kind = "referrer"
    rows = []
    for i, tpl in enumerate(REF_TPL_READYMADE[kind]):
        rows.append([InlineKeyboardButton(f"Template {i+1}: {tpl.splitlines()[0][:30]}", callback_data=f"refadm_tpl_apply_{kind}_{i}")])
    rows.append([InlineKeyboardButton("👤 Direct Referrer", callback_data="refadm_tpl_ready_referrer"),
                 InlineKeyboardButton("🛡️ Direct Admin", callback_data="refadm_tpl_ready_admin")])
    rows.append([InlineKeyboardButton("🏆 Direct Milestone", callback_data="refadm_tpl_ready_milestone")])
    rows.append([InlineKeyboardButton("📦 Product Referrer", callback_data="refadm_tpl_ready_product_referrer")])
    rows.append([InlineKeyboardButton("🛡️ Product Admin", callback_data="refadm_tpl_ready_product_admin"),
                 InlineKeyboardButton("🎉 Product Unlock", callback_data="refadm_tpl_ready_product_unlock")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="refadm_tpl_panel")])
    await _safe_edit(q,
        f"🎨 *Readymade Templates — {kind.title()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        "Pick one to apply instantly, or go back and edit custom.",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))


async def refadm_tpl_apply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        rest = q.data.replace("refadm_tpl_apply_", "", 1)
        kind, idx_s = rest.rsplit("_", 1)
        idx = int(idx_s)
        tpl = REF_TPL_READYMADE[kind][idx]
    except Exception:
        await q.answer("Invalid template", show_alert=True); return
    set_setting(_tpl_key(kind), tpl)
    await q.answer("✅ Template applied", show_alert=True)
    text, kb = _ref_tpl_panel_text_kb()
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def refadm_tpl_reset_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("✅ Reset", show_alert=True)
    for kind, tpl in REF_TPL_DEFAULTS.items():
        set_setting(_tpl_key(kind), tpl)
    text, kb = _ref_tpl_panel_text_kb()
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def refadm_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Router for refadm text input. Called from bot.py::handle_text."""
    if update.effective_user.id != ADMIN_ID:
        return False
    step = context.user_data.get("refadm_step")
    if not step:
        return False
    raw = (update.message.text or "").strip()
    context.user_data.pop("refadm_step", None)

    kb_back = InlineKeyboardMarkup([[InlineKeyboardButton(
        "🔙 Referral Panel", callback_data="refadm_panel")]])

    if step.startswith("tpl_"):
        kind = step.replace("tpl_", "", 1)
        if kind not in REF_TPL_DEFAULTS:
            await update.message.reply_text("❌ Invalid template type.", reply_markup=kb_back)
            return True
        if not raw:
            await update.message.reply_text("❌ Template cannot be empty.", reply_markup=kb_back)
            return True
        set_setting(_tpl_key(kind), raw)
        await update.message.reply_text(
            f"✅ *{kind.title()} referral template saved!*\n\n"
            f"Use the panel to test by bringing a referral.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✉️ Templates", callback_data="refadm_tpl_panel")]]))
        return True

    try:
        parts = raw.split(None, 1)
        uid = int(parts[0])
        rest = parts[1].strip() if len(parts) > 1 else ""
    except Exception:
        await update.message.reply_text("❌ Invalid format. Try again.",
                                        reply_markup=kb_back)
        return True

    if step == "ban":
        ban_referrer(uid, rest or "manual_admin_ban")
        await update.message.reply_text(
            f"🔨 *Banned* `{uid}` from referral system.\n_Reason: {escape_md(rest) or 'manual_admin_ban'}_",
            parse_mode="Markdown", reply_markup=kb_back)
        return True

    if step == "unban":
        unban_referrer(uid)
        await update.message.reply_text(
            f"🔓 *Unbanned* `{uid}`. They can now give/receive referrals again.",
            parse_mode="Markdown", reply_markup=kb_back)
        return True

    if step == "adjust":
        amt_str = (rest or "0").strip()
        try:
            if amt_str.startswith("="):
                target = int(amt_str[1:])
                cur = get_ref_points(uid)
                delta = target - cur
                add_ref_points(uid, delta)
                new_bal = get_ref_points(uid)
                await update.message.reply_text(
                    f"💎 Set `{uid}` ref_points = *{new_bal}* (was {cur}).",
                    parse_mode="Markdown", reply_markup=kb_back)
            else:
                delta = int(amt_str)
                add_ref_points(uid, delta)
                new_bal = get_ref_points(uid)
                sign = "+" if delta >= 0 else ""
                await update.message.reply_text(
                    f"💎 Adjusted `{uid}` by *{sign}{delta}*. New balance: *{new_bal}*.",
                    parse_mode="Markdown", reply_markup=kb_back)
            # Notify the user
            try:
                if delta != 0:
                    await context.bot.send_message(uid,
                        f"📢 *Admin updated your Referral Points*\n"
                        f"➡️ Change: *{('+' if delta>=0 else '')}{delta}*\n"
                        f"💎 New Balance: *{get_ref_points(uid)}*",
                        parse_mode="Markdown")
            except Exception:
                pass
        except Exception as e:
            await update.message.reply_text(f"❌ Invalid amount: {e}", reply_markup=kb_back)
        return True

    return False
