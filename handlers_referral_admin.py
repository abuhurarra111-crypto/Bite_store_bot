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


REF_TPL_PLACEHOLDERS = {
    "referrer": "Placeholders:\n`{referred_id}` `{referred_name}` `{referred_username}`\n`{reward_points}` `{total_referrals}` `{remaining_to_bonus}` `{milestone_bonus}`",
    "admin": "Placeholders:\n`{referrer_id}` `{referrer_name}` `{referrer_username}`\n`{referred_id}` `{referred_name}` `{referred_username}`\n`{reward_points}` `{total_referrals}`",
    "milestone": "Placeholders:\n`{milestone_number}` `{milestone_bonus}` `{next_milestone}`\n`{referrer_id}` `{referrer_name}`",
    "product_referrer": "Placeholders:\n`{product_id}` `{product_name}` `{product_referrals}` `{product_required}` `{product_remaining}`\n`{referred_id}` `{referred_name}` `{referred_username}`",
    "product_admin": "Placeholders:\n`{product_id}` `{product_name}` `{product_referrals}` `{product_required}` `{product_remaining}`\n`{referrer_id}` `{referrer_name}` `{referrer_username}`\n`{referred_id}` `{referred_name}` `{referred_username}`",
    "product_unlock": "Placeholders:\n`{product_id}` `{product_name}` `{product_referrals}` `{product_required}`\n`{referrer_id}` `{referrer_name}`",
}

def _pad_ref_templates():
    for kind in list(REF_TPL_DEFAULTS.keys()):
        base = REF_TPL_DEFAULTS[kind]
        if kind.startswith('product_'):
            variants = [base,
                "📦 *Product Referral*\n\nProduct: {product_name}\nNew user: `{referred_id}`\nProgress: {product_referrals}/{product_required}",
                "🎁 *Free Claim Progress*\n\n{referred_name} joined for {product_name}. Need {product_remaining} more.",
                "✅ *Product Referral Counted*\n\n{product_name}: {product_referrals}/{product_required}\nUser ID: `{referred_id}`",
                "🚀 *Closer to Free!*\n\nProduct: {product_name}\nRemaining: {product_remaining}",
                "📈 *Progress Update*\n\n{product_referrals}/{product_required} for {product_name}.",
                "🎯 *Target Update*\n\nBring {product_remaining} more for free {product_name}.",
                "🧾 *Product Referral Receipt*\n\nProduct #{product_id}\nReferrer `{referrer_id}`\nReferred `{referred_id}`",
                "🌟 *Referral Added*\n\n{referred_name} counted toward {product_name}.",
                "🏆 *Free Reward Path*\n\nProgress: {product_referrals}/{product_required}\nProduct: {product_name}"]
        else:
            variants = [base,
                "✅ *Referral Update*\n\nUser `{referred_id}` joined. Reward: +{reward_points}. Total: {total_referrals}.",
                "🚀 *New Referral!*\n\n{referred_name} (`{referred_id}`) joined via your link. Progress: {total_referrals}.",
                "🎁 *Reward Added*\n\n+{reward_points} referral point for `{referred_id}`. Next bonus in {remaining_to_bonus}.",
                "🌟 *Great work!*\n\nReferral ID `{referred_id}` counted. You now have {total_referrals} direct referrals.",
                "📈 *Referral Progress*\n\nNew user: {referred_name}\nID: `{referred_id}`\nTotal: {total_referrals}",
                "💎 *Earning Update*\n\n+{reward_points} point earned. Referred: `{referred_id}`.",
                "🔥 *Another referral!*\n\n{referred_name} started the bot. Keep going for milestone rewards.",
                "🧾 *Referral Receipt*\n\nReferrer `{referrer_id}` → Referred `{referred_id}`\nTotal: {total_referrals}",
                "🏆 *Milestone Progress*\n\nCurrent: {total_referrals}\nNext bonus: {remaining_to_bonus} more → +{milestone_bonus} points."]
        REF_TPL_READYMADE[kind] = variants[:10]
_pad_ref_templates()

REF_UNLOCK_BTN_KEY = "ref_unlock_claim_btn"


def _tpl_key(kind):
    return f"ref_tpl_{kind}"


async def _safe_edit(q, text, **kwargs):
    send_text, send_mode = smart_text_and_mode(text, kwargs.get("parse_mode", "Markdown"))
    send_kwargs = dict(kwargs); send_kwargs["parse_mode"] = send_mode
    try:
        await q.edit_message_text(send_text, **send_kwargs); return
    except Exception:
        pass
    # v130: hard fallback without parse_mode — prevents template editor screens
    # from silently failing when custom placeholders/underscores break Markdown.
    plain_kwargs = dict(send_kwargs)
    plain_kwargs.pop("parse_mode", None)
    try:
        await q.edit_message_text(send_text, **plain_kwargs); return
    except Exception:
        pass
    try:
        await q.edit_message_caption(caption=send_text, **send_kwargs); return
    except Exception:
        pass
    try:
        await q.edit_message_caption(caption=send_text, **plain_kwargs); return
    except Exception:
        pass
    try:
        await q.message.reply_text(send_text, **send_kwargs)
    except Exception:
        try:
            await q.message.reply_text(send_text, **plain_kwargs)
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
        [InlineKeyboardButton("👁 Preview Referrer", callback_data="refadm_tpl_preview_referrer"),
         InlineKeyboardButton("👁 Preview Product", callback_data="refadm_tpl_preview_product_referrer")],
        [InlineKeyboardButton("🎛️ Unlock Button Editor", callback_data="refadm_btn_panel")],
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
        f"{REF_TPL_PLACEHOLDERS.get(kind, REF_PLACEHOLDERS)}\n\n"
        f"Send the new template as your next message. Premium emojis are supported.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👁 Live Preview", callback_data=f"refadm_tpl_preview_{kind}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="refadm_tpl_panel")],
        ]))


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


def _ref_sample_values(kind):
    vals = {
        'referrer_id': 111111111,
        'referrer_name': 'Alex Referrer',
        'referrer_username': 'alex_ref',
        'referred_id': 222222222,
        'referred_name': 'New Friend',
        'referred_username': 'new_friend',
        'reward_points': '1',
        'total_referrals': 7,
        'remaining_to_bonus': 13,
        'milestone_bonus': '10',
        'milestone_number': 20,
        'next_milestone': 40,
        'product_id': 99,
        'product_name': 'Sample Product',
        'product_referrals': 3,
        'product_required': 5,
        'product_remaining': 2,
    }
    return vals


def _render_preview(kind):
    tpl = get_setting(_tpl_key(kind), REF_TPL_DEFAULTS.get(kind, '')) or REF_TPL_DEFAULTS.get(kind, '')
    vals = _ref_sample_values(kind)
    try:
        return tpl.format(**vals)
    except Exception as e:
        return f"⚠️ Template format error: {e}\n\n{tpl}"


async def refadm_tpl_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("👁 Preview")
    kind = q.data.replace("refadm_tpl_preview_", "", 1)
    if kind not in REF_TPL_DEFAULTS:
        await q.answer("Invalid template", show_alert=True); return
    preview = _render_preview(kind)
    send_text, send_mode = smart_text_and_mode(preview, "Markdown")
    rows = []
    if kind == 'product_unlock':
        try:
            from button_system import build_button, wrap_button
            btn = build_button(REF_UNLOCK_BTN_KEY, '🎁 Claim FREE Now', callback_data='preview_claim')
            btn = wrap_button(REF_UNLOCK_BTN_KEY, btn)
            rows.append([btn])
        except Exception:
            pass
    rows.append([InlineKeyboardButton("✏️ Edit This Template", callback_data=f"refadm_tpl_edit_{kind}")])
    rows.append([InlineKeyboardButton("🔙 Templates", callback_data="refadm_tpl_panel")])
    await _safe_edit(q,
        f"👁 *Live Preview — {kind.title()}*\n━━━━━━━━━━━━━━━━━━━━\n\n{send_text}",
        parse_mode=send_mode,
        reply_markup=InlineKeyboardMarkup(rows))


async def refadm_tpl_reset_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("✅ Reset", show_alert=True)
    for kind, tpl in REF_TPL_DEFAULTS.items():
        set_setting(_tpl_key(kind), tpl)
    text, kb = _ref_tpl_panel_text_kb()
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


def _unlock_btn_panel_text_kb():
    try:
        from button_system import get_button_text, get_button_emoji_id, get_button_style
        txt = get_button_text(REF_UNLOCK_BTN_KEY, "🎁 Claim FREE Now")
        emoji = get_button_emoji_id(REF_UNLOCK_BTN_KEY) or "none"
        color = get_button_style(REF_UNLOCK_BTN_KEY) or "default"
    except Exception:
        txt, emoji, color = "🎁 Claim FREE Now", "none", "default"
    body = (
        "🎛️ *Product Unlock Button Editor*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Text: `{escape_md(txt)}`\n"
        f"Premium icon: `{escape_md(emoji)}`\n"
        f"Background: `{escape_md(color)}`\n\n"
        "This button is sent with the Product Unlock notification."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Text/Icon", callback_data="refadm_btn_edit")],
        [InlineKeyboardButton("🔵 Blue", callback_data="refadm_btn_color_primary"),
         InlineKeyboardButton("🟢 Green", callback_data="refadm_btn_color_success"),
         InlineKeyboardButton("🔴 Red", callback_data="refadm_btn_color_danger")],
        [InlineKeyboardButton("⬜ Default Color", callback_data="refadm_btn_color_none")],
        [InlineKeyboardButton("♻️ Reset Button", callback_data="refadm_btn_reset")],
        [InlineKeyboardButton("🔙 Templates", callback_data="refadm_tpl_panel")],
    ])
    return body, kb


async def refadm_btn_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    text, kb = _unlock_btn_panel_text_kb()
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def refadm_btn_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data['refadm_step'] = 'unlock_btn_text'
    await _safe_edit(q,
        "✏️ *Edit Product Unlock Button*\n\n"
        "Send new button text. If you start the message with a premium emoji, "
        "it will be saved as the button icon.\n\n"
        "Example: `[premium emoji] Claim FREE Now`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="refadm_btn_panel")]]))


async def refadm_btn_color_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    color = q.data.replace('refadm_btn_color_', '', 1)
    if color == 'none': color = ''
    if color not in ('', 'primary', 'success', 'danger'):
        await q.answer('Invalid color', show_alert=True); return
    try:
        from button_system import set_button_style
        set_button_style(REF_UNLOCK_BTN_KEY, color)
        await q.answer('✅ Color saved', show_alert=False)
    except Exception as e:
        await q.answer(f'⚠️ {e}', show_alert=True); return
    text, kb = _unlock_btn_panel_text_kb()
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def refadm_btn_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        from button_system import reset_button, set_button_style
        reset_button(REF_UNLOCK_BTN_KEY)
        set_button_style(REF_UNLOCK_BTN_KEY, '')
        await q.answer('✅ Button reset', show_alert=False)
    except Exception as e:
        await q.answer(f'⚠️ {e}', show_alert=True); return
    text, kb = _unlock_btn_panel_text_kb()
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

    if step == 'unlock_btn_text':
        try:
            from button_system import extract_custom_emoji, set_button, get_button_emoji_id
            emoji_id, stripped = extract_custom_emoji(update.message)
            text_value = (stripped or raw).strip()
            set_button(REF_UNLOCK_BTN_KEY, text_value, emoji_id or get_button_emoji_id(REF_UNLOCK_BTN_KEY))
            await update.message.reply_text("✅ Unlock button saved.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎛️ Button Panel", callback_data="refadm_btn_panel")]]))
        except Exception as e:
            await update.message.reply_text(f"❌ Could not save button: {e}", reply_markup=kb_back)
        return True

    if step.startswith("tpl_"):
        kind = step.replace("tpl_", "", 1)
        if kind not in REF_TPL_DEFAULTS:
            await update.message.reply_text("❌ Invalid template type.", reply_markup=kb_back)
            return True
        captured = capture_user_text(update.message) or raw
        if not captured.strip():
            await update.message.reply_text("❌ Template cannot be empty.", reply_markup=kb_back)
            return True
        set_setting(_tpl_key(kind), captured)
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
