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
)

logger = logging.getLogger(__name__)


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
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")],
    ])


async def refadm_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the Referral Abuse panel.
    🆕 v55: cancels any pending refadm_step text-input flow."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    # 🆕 v55: cancel any pending text-input flow
    context.user_data.pop("refadm_step", None)
    # Stats
    counted = get_referral_log(limit=10000, status="counted")
    blocked = get_referral_log(limit=10000, status="blocked")
    bans = get_referral_bans(limit=10000)
    text = (
        "🛡️ *Referral Abuse Control*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ Counted Referrals: *{len(counted)}*\n"
        f"🚫 Blocked Attempts: *{len(blocked)}*\n"
        f"🔨 Currently Banned: *{len(bans)}*\n\n"
        "_Manage referral system integrity below:_"
    )
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=_panel_kb())


async def refadm_log_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent referral log entries (counted / blocked / all)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    data = q.data.replace("refadm_log_", "")
    status_filter = None
    title = "📜 *All Referral Attempts*"
    if data == "counted":
        status_filter = "counted"; title = "✅ *Counted Referrals*"
    elif data == "blocked":
        status_filter = "blocked"; title = "🚫 *Blocked Referrals*"
    rows = get_referral_log(limit=30, status=status_filter)
    if not rows:
        body = "_No entries yet._"
    else:
        lines = []
        for r in rows:
            icon = "✅" if r["status"] == "counted" else "🚫"
            at = (r.get("created_at") or "")[:16].replace("T", " ")
            reason = escape_md(r.get("reason") or "")
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
