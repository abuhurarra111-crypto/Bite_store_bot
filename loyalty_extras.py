# ============================================================
# 🧩 v77 BUNDLE: loyalty_extras.py
# ============================================================
# This file is the merged result of 5 originally separate modules:
#   • handlers_loyalty.py
#   • handlers_share_product.py
#   • handlers_pinned.py
#   • pinned_announcements.py
#   • tier_config.py
#
# 🛡️ ALL CODE IS PRESERVED VERBATIM. Each original file's contents appears
# below in its own section. Imports and behavior are byte-identical to the
# pre-merge codebase — only file count is reduced.
# ============================================================


# ============================================================
# 📄 ORIGINAL FILE: handlers_loyalty.py
# ============================================================

# ============================================
# 🏆 LOYALTY TIERS HANDLERS
# ============================================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_ID
from database import (
    get_user_tier_data, get_top_customers_by_tier, TIER_CONFIG
)
from i18n import t, get_user_lang
from utils import escape_md, nav_push


async def _safe_edit(q, text, **kwargs):
    # 1. Try editing as a regular text message
    try:
        await q.edit_message_text(text, **kwargs)
        return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in kwargs:
            kwargs_no_md = dict(kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.edit_message_text(text, **kwargs_no_md)
                return
            except Exception: pass

    # 2. Fallback: edit caption (works on photo/video messages)
    try:
        await q.edit_message_caption(caption=text, **kwargs)
        return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in kwargs:
            kwargs_no_md = dict(kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.edit_message_caption(caption=text, **kwargs_no_md)
                return
            except Exception: pass

    # 3. Last resort: reply_text
    try:
        await q.message.reply_text(text, **kwargs)
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in kwargs:
            kwargs_no_md = dict(kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.message.reply_text(text, **kwargs_no_md)
            except Exception: pass

def _progress_bar(pct, width=10):
    filled = int(width * pct / 100)
    return "▰" * filled + "▱" * (width - filled)


# ════════════════════════════════════════════
# USER-SIDE
# ════════════════════════════════════════════

async def loyalty_callback(update, context):
    """Show user's tier card with progress and benefits."""
    q = update.callback_query
    await q.answer()
    nav_push(context, 'loyalty_menu')  # 🔧 v39 Bug #5
    uid = q.from_user.id
    lang = get_user_lang(uid)

    data = get_user_tier_data(uid)
    if not data:
        await _safe_edit(q, t("error", lang=lang),
                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                             t("btn_back", lang=lang), callback_data="main_menu")]]))
        return

    # 🆕 v46: editable header line (admin can change via Edit Responses)
    try:
        from database import get_response_with_auto_register
        from config import DEFAULT_RESPONSES
        _hdr = get_response_with_auto_register(
            "loyalty_menu_header", DEFAULT_RESPONSES.get("loyalty_menu_header", ""))
        _hdr = (_hdr or "🏆 Loyalty Status\n━━━━━━━━━━━━━━━━━━━━").replace("*", "")
    except Exception:
        _hdr = "🏆 Loyalty Status\n━━━━━━━━━━━━━━━━━━━━"
    lines = [
        *(_hdr.split("\n")),
        "",
        f"{t('tier_your', lang=lang)} {data['tier_name']}",
        f"{t('tier_total_spent', lang=lang)} ${data['total_spent']:.2f}",
        f"{t('tier_total_orders', lang=lang)} {data['total_orders']}",
        "",
    ]

    # Benefits
    bonus = data['bonus_pct']
    lines.append(f"{t('tier_benefits', lang=lang)}")
    if bonus > 0:
        lines.append(f"  💎 +{bonus}% bonus points on every purchase")
        lines.append("  ⚡ Priority support")
        if bonus >= 10:
            lines.append("  🎁 Exclusive deals & early access")
        if bonus >= 15:
            lines.append("  🚀 Free upgrades on select products")
        if bonus >= 20:
            lines.append("  👑 VIP-only products + personal manager")
    else:
        lines.append("  Make your first purchase to unlock benefits!")
    lines.append("")

    # Progress
    if data['next_tier']:
        bar = _progress_bar(data['progress_pct'])
        lines.append(f"{t('tier_progress', lang=lang)}")
        lines.append(f"{bar} {data['progress_pct']:.0f}%")
        lines.append(f"{data['progress_label']}")
    else:
        lines.append(t("tier_max", lang=lang))

    # Build tier ladder
    lines.append("")
    lines.append("📊 All Tiers:")
    for tier in TIER_CONFIG:
        marker = " ← you" if tier['key'] == data['tier_key'] else ""
        lines.append(f"  {tier['name']} — ${tier['min_spent']}+ or {tier['min_orders']}+ orders ({tier['bonus_pct']}%){marker}")

    kb = []
    # 🆕 v38: Inject custom buttons for loyalty screen
    try:
        from keyboards import _custom_buttons_for
        kb.extend(_custom_buttons_for("loyalty"))
    except Exception:
        pass
    kb.append([InlineKeyboardButton(t("btn_back", lang=lang), callback_data="main_menu")])
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════
# ADMIN-SIDE: Tier Leaderboard
# ════════════════════════════════════════════

async def admin_loyalty_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    lines = ["🏆 *Loyalty Leaderboard*", "━━━━━━━━━━━━━━━━━━━━", ""]
    top = get_top_customers_by_tier(limit=15)

    if not top:
        lines.append("📭 No customers yet")
    else:
        # 🔧 v39 Bug #7 + #12: Show tier distribution + rename loop var (was shadowing i18n `t`)
        # Get ALL users tier counts (not just top 15)
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT tier, COUNT(*) FROM users WHERE tier IS NOT NULL GROUP BY tier")
        tier_counts = {row[0]: row[1] for row in c.fetchall()}
        conn.close()

        # Display distribution
        lines.append("*📊 Tier Distribution:*")
        for tier in TIER_CONFIG:
            cnt = tier_counts.get(tier['key'], 0)
            bar = "▰" * min(cnt, 10) + "▱" * max(0, 10 - cnt)
            lines.append(f"  {tier['name']}: {bar} *{cnt}*")
        lines.append("")

        lines.append("*🏆 Top Customers by Spend:*\n")
        medals = ["🥇", "🥈", "🥉"] + ["▫️"] * 20
        for i, u in enumerate(top):
            tier_info = next((tier for tier in TIER_CONFIG if tier['key'] == (u['tier'] or 'bronze')), TIER_CONFIG[0])
            name = escape_md((u['first_name'] or 'N/A')[:18])
            lines.append(f"{medals[i]} *{name}* — ${u['total_spent']:.2f} • "
                         f"{u['total_orders']} orders {tier_info['name']}")

    kb = [
        # 🆕 v68: Configure Tiers panel
        [InlineKeyboardButton("⚙️ Configure Tiers", callback_data="admin_tier_cfg")],
        [InlineKeyboardButton("🔙 Return", callback_data="admin_panel")],
    ]
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════════════════════
# 🆕 v68: TIER CUSTOMIZATION ADMIN PANEL
# ════════════════════════════════════════════════════════════
async def admin_tier_cfg_callback(update, context):
    """Main tier configuration panel — list all 5 tiers with current settings."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    # [v77-merge] from tier_config import (

    # [v77-merge] get_tier_config, is_tier_bonus_enabled, is_tier_msg_enabled,

    # [v77-merge] )
    tiers = get_tier_config()
    bonus_on = is_tier_bonus_enabled()
    msg_on   = is_tier_msg_enabled()

    lines = [
        "⚙️ *Tier Configuration*",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "🔧 *System Toggles:*",
        f"  • Per-Order Tier Bonus: {'🟢 ON' if bonus_on else '🔴 OFF'}",
        f"  • Custom Upgrade Messages: {'🟢 ON' if msg_on else '🔴 OFF'}",
        "",
        "📋 *Current Tiers:*",
    ]
    # Static tier emoji names for display
    names = {
        "bronze": "🥉 Bronze", "silver": "🥈 Silver", "gold": "🥇 Gold",
        "platinum": "💎 Platinum", "diamond": "💠 Diamond",
    }
    for t in tiers:
        nm = names.get(t['key'], t['key'])
        spent = float(t.get('min_spent', 0))
        bonus = int(t.get('bonus_pts', 0))
        msg_preview = (t.get('upgrade_msg', '') or '').replace('\n', ' ')[:50]
        lines.append("")
        lines.append(f"*{nm}*")
        if t['key'] == 'bronze':
            lines.append(f"  • Spending required: `$0` (entry tier)")
        else:
            lines.append(f"  • Spending required: `${spent:.0f}`")
        lines.append(f"  • Bonus per order: `{bonus} pts`")
        lines.append(f"  • Message: _{escape_md(msg_preview)}…_")

    lines.append("")
    lines.append("_Tap any tier below to edit its settings._")

    kb = [
        [InlineKeyboardButton(
            ("🔴 Turn OFF" if bonus_on else "🟢 Turn ON") + " Tier Bonus",
            callback_data="admin_tier_toggle_bonus"),
         InlineKeyboardButton(
            ("🔴 OFF" if msg_on else "🟢 ON") + " Custom Msgs",
            callback_data="admin_tier_toggle_msg")],
    ]
    # Per-tier edit buttons (2 per row)
    row = []
    for t in tiers:
        nm = names.get(t['key'], t['key'])
        row.append(InlineKeyboardButton(f"✏️ {nm}", callback_data=f"admin_tier_edit_{t['key']}"))
        if len(row) == 2:
            kb.append(row); row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton("♻️ Reset All to Defaults", callback_data="admin_tier_reset_confirm")])
    kb.append([InlineKeyboardButton("🔙 Back to Loyalty", callback_data="admin_loyalty")])

    await _safe_edit(q, "\n".join(lines)[:3900], parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def admin_tier_toggle_bonus_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    # [v77-merge] self-bundle import removed: from tier_config import is_tier_bonus_enabled, set_tier_bonus_enabled
    cur = is_tier_bonus_enabled()
    set_tier_bonus_enabled(not cur)
    await q.answer(f"Tier bonus {'OFF' if cur else 'ON'}", show_alert=False)
    await admin_tier_cfg_callback(update, context)


async def admin_tier_toggle_msg_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    # [v77-merge] self-bundle import removed: from tier_config import is_tier_msg_enabled, set_tier_msg_enabled
    cur = is_tier_msg_enabled()
    set_tier_msg_enabled(not cur)
    await q.answer(f"Custom messages {'OFF' if cur else 'ON'}", show_alert=False)
    await admin_tier_cfg_callback(update, context)


async def admin_tier_edit_callback(update, context):
    """Show edit panel for a single tier."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    tier_key = q.data.replace("admin_tier_edit_", "")
    # [v77-merge] self-bundle import removed: from tier_config import get_tier_config
    tiers = get_tier_config()
    tier = next((t for t in tiers if t['key'] == tier_key), None)
    if not tier:
        await q.edit_message_text("❌ Tier not found.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="admin_tier_cfg")]]))
        return

    names = {"bronze": "🥉 Bronze", "silver": "🥈 Silver", "gold": "🥇 Gold",
             "platinum": "💎 Platinum", "diamond": "💠 Diamond"}
    nm = names.get(tier_key, tier_key)
    spent = float(tier.get('min_spent', 0))
    bonus = int(tier.get('bonus_pts', 0))
    msg = tier.get('upgrade_msg', '') or ''

    text = (
        f"✏️ *Edit Tier — {nm}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 *Current Settings:*\n"
        f"  • Spending threshold: `${spent:.0f}`\n"
        f"  • Per-order bonus: `{bonus} points`\n\n"
        f"💬 *Upgrade message:*\n"
        f"_{escape_md(msg[:400])}_\n\n"
        f"Tap a field below to edit it."
    )
    kb = []
    if tier_key != 'bronze':
        kb.append([InlineKeyboardButton(
            f"💵 Edit Threshold (${spent:.0f})",
            callback_data=f"admin_tier_field_{tier_key}_spent")])
    kb.append([InlineKeyboardButton(
        f"💎 Edit Bonus ({bonus} pts)",
        callback_data=f"admin_tier_field_{tier_key}_bonus")])
    kb.append([InlineKeyboardButton(
        "💬 Edit Upgrade Message",
        callback_data=f"admin_tier_field_{tier_key}_msg")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_tier_cfg")])
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def admin_tier_field_callback(update, context):
    """Prompt admin for the new value for a specific tier field."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    # callback: admin_tier_field_<key>_<field>
    parts = q.data.replace("admin_tier_field_", "").rsplit("_", 1)
    if len(parts) != 2:
        await q.edit_message_text("❌ Invalid request."); return
    tier_key, field = parts[0], parts[1]
    if field not in ("spent", "bonus", "msg"):
        await q.edit_message_text("❌ Unknown field."); return

    context.user_data["admin_tier_edit_key"]   = tier_key
    context.user_data["admin_tier_edit_field"] = field
    context.user_data["admin_tier_edit_step"]  = "waiting_value"

    prompts = {
        "spent": (
            f"💵 *Edit Spending Threshold — {tier_key}*\n\n"
            f"Type the new threshold in USD.\n"
            f"Example: `100` (means $100 spent to unlock)\n\n"
            f"Bronze should always be `0`."
        ),
        "bonus": (
            f"💎 *Edit Bonus Points — {tier_key}*\n\n"
            f"Type the per-order bonus points (whole number).\n"
            f"Example: `5` (user gets +5 points on every order)\n\n"
            f"Type `0` to disable bonus for this tier."
        ),
        "msg": (
            f"💬 *Edit Upgrade Message — {tier_key}*\n\n"
            f"Type the message users will see when they reach this tier.\n"
            f"Plain English recommended. Max 1000 chars.\n\n"
            f"Example: _Congratulations! You unlocked Gold tier and "
            f"now earn 3 bonus points per order!_"
        ),
    }
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"admin_tier_edit_{tier_key}")],
    ])
    await _safe_edit(q, prompts[field], parse_mode="Markdown", reply_markup=kb)


async def admin_tier_value_received(update, context):
    """Receive the new value the admin typed."""
    if context.user_data.get("admin_tier_edit_step") != "waiting_value":
        return False
    if update.effective_user.id != ADMIN_ID:
        return False
    tier_key = context.user_data.pop("admin_tier_edit_key", None)
    field    = context.user_data.pop("admin_tier_edit_field", None)
    context.user_data.pop("admin_tier_edit_step", None)

    if not tier_key or not field:
        await update.message.reply_text("❌ Edit context lost. Try again.")
        return True

    raw = (update.message.text or "").strip()

    # [v77-merge] self-bundle import removed: from tier_config import set_tier_field
    try:
        if field == "spent":
            v = float(raw.replace("$", "").replace(",", "").strip())
            if v < 0: raise ValueError("Threshold must be ≥ 0")
            set_tier_field(tier_key, "min_spent", v)
            confirm = f"✅ Threshold for *{tier_key}* set to *${v:.0f}*"
        elif field == "bonus":
            v = int(raw.replace(",", "").strip())
            if v < 0 or v > 10000: raise ValueError("Bonus must be 0–10000")
            set_tier_field(tier_key, "bonus_pts", v)
            confirm = f"✅ Bonus for *{tier_key}* set to *{v} points/order*"
        elif field == "msg":
            if len(raw) < 5:
                raise ValueError("Message too short (min 5 chars)")
            set_tier_field(tier_key, "upgrade_msg", raw[:1000])
            confirm = f"✅ Upgrade message for *{tier_key}* updated"
        else:
            confirm = "❌ Unknown field"
    except Exception as e:
        await update.message.reply_text(
            f"❌ Invalid value: {e}\n\nTry again or tap Cancel from previous screen.",
            parse_mode="Markdown")
        return True

    await update.message.reply_text(
        confirm, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Edit More", callback_data=f"admin_tier_edit_{tier_key}")],
            [InlineKeyboardButton("⚙️ All Tiers", callback_data="admin_tier_cfg")],
        ]))
    return True


async def admin_tier_reset_confirm_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    text = (
        "♻️ *Reset all tiers to factory defaults?*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "This will erase all your custom thresholds, bonuses, and upgrade messages.\n\n"
        "Defaults will be:\n"
        "  • 🥉 Bronze — $0\n"
        "  • 🥈 Silver — $100\n"
        "  • 🥇 Gold — $500 (3 pts/order)\n"
        "  • 💎 Platinum — $1000 (5 pts/order)\n"
        "  • 💠 Diamond — $2500 (10 pts/order)\n\n"
        "Are you sure?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, reset", callback_data="admin_tier_reset_do")],
        [InlineKeyboardButton("❌ Cancel",      callback_data="admin_tier_cfg")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def admin_tier_reset_do_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    # [v77-merge] self-bundle import removed: from tier_config import reset_to_defaults
    reset_to_defaults()
    await q.answer("✅ Reset to defaults.", show_alert=False)
    await admin_tier_cfg_callback(update, context)


# ════════════════════════════════════════════
# HOOK: Call this when an order is delivered
# ════════════════════════════════════════════

async def broadcast_real_tier_upgrade(bot, user_id, new_tier_key):
    """Broadcast a real user's tier upgrade in the same style as fake ones!"""
    try:
        from database import get_user_tier_data, get_setting, get_connection
        from per_user_activity import _mask_name
        from ui_extras import send_activity_message
        from datetime import datetime
        import logging
        
        # 1. Get user tier data
        data = get_user_tier_data(user_id)
        if not data:
            return
            
        # 2. Get user name
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT first_name FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        
        first_name = row[0] if row and row[0] else "User"
        masked = _mask_name(first_name)
        
        # 3. Get PKR rate
        pkr_rate = float(get_setting("usd_to_pkr_rate", "280"))
        
        # 4. Determine prev and new tier names and benefits
        from database import TIER_CONFIG
        new_idx = next((i for i, t in enumerate(TIER_CONFIG) if t["key"] == new_tier_key), 1)
        prev_tier = TIER_CONFIG[new_idx - 1]["name"] if new_idx > 0 else "None"
        new_tier = TIER_CONFIG[new_idx]["name"]
        benefit = f"{TIER_CONFIG[new_idx]['bonus_pct']}% Permanent Discount" if TIER_CONFIG[new_idx]['bonus_pct'] > 0 else "None"
        
        spent_usd = data["total_spent"]
        spent_pkr = f"Rs {int(spent_usd * pkr_rate):,}"
        spent_str = f"${spent_usd:.2f} (~{spent_pkr})"
        
        date_str = datetime.now().strftime("%d %b %Y")
        
        # 5. Build message
        msg = (
            f"***💎 Loyalty Tier Update! 🏆***\n"
            f"***━━━━━━━━━━━━━━━━━━━━━***\n"
            f"***👤 User: {masked}***\n"
            f"***🎖️ Previous Tier: {prev_tier}***\n"
            f"***🚀 New Tier: {new_tier}***\n"
            f"***🛍️ Total Spent: {spent_str}***\n"
            f"***🎁 Tier Benefit: {benefit}***\n"
            f"***📅 Upgraded On: {date_str}***\n\n"
            f"***⚡ Status: Tier Upgraded Automatically 🟢***"
        )
        
        # 6. Broadcast using our centralized send_activity_message function
        await send_activity_message(bot, user_id, msg)
        logging.getLogger(__name__).info(f"[Loyalty] Broadcasted real tier upgrade of {user_id} ({masked}) to destinations.")
    except Exception as e:
        logging.getLogger(__name__).error(f"[Loyalty] Error broadcasting real tier upgrade: {e}")


# ════════════════════════════════════════════
# 🆕 v66: Tier progress hint (1-line, appended to delivery messages)
# ════════════════════════════════════════════
def build_tier_progress_line(user_id):
    """Return a 1-line tier-progress hint string. Empty on any error.

    Examples:
      "🏆 Tier: 🥉 Bronze — 3 more orders for 🥈 Silver"
      "🏆 Tier: 🥇 Gold — $200 more for 💎 Platinum"
      "🏆 Tier: 💠 Diamond (Max tier reached!)"
    """
    try:
        data = get_user_tier_data(user_id)
        if not data:
            return ""
        cur_name = data.get('tier_name') or ''
        nxt = data.get('next_tier')
        if not nxt:
            return f"🏆 Tier: {cur_name} (Max tier reached!)"
        more_orders = max(0, int(nxt.get('min_orders', 0)) - int(data.get('total_orders', 0)))
        more_spent  = max(0.0, float(nxt.get('min_spent', 0)) - float(data.get('total_spent', 0)))
        # Prefer whichever is reachable faster
        if more_orders > 0 and more_spent > 0:
            if more_orders <= 3:
                hint = f"{more_orders} more orders"
            else:
                hint = f"${more_spent:.0f} more"
        elif more_orders > 0:
            hint = f"{more_orders} more orders"
        elif more_spent > 0:
            hint = f"${more_spent:.0f} more"
        else:
            return f"🏆 Tier: {cur_name}"
        return f"🏆 Tier: {cur_name} — *{hint}* for {nxt.get('name','next tier')}"
    except Exception:
        return ""


# ════════════════════════════════════════════
# 🆕 v68: Per-order tier bonus crediting
# ════════════════════════════════════════════
def credit_tier_bonus(user_id):
    """🆕 v69: DEFAULT OFF. Only credits if admin explicitly turns ON via
       Loyalty → Configure Tiers panel. (User reported $150 loss because
       v68 tier bonus + delivery bonus stacked into a free-refund bug.)
    """
    try:
        # [v77-merge] self-bundle import removed: from tier_config import is_tier_bonus_enabled, get_bonus_for_tier
        # In v69 we changed the default from "1" to "0" so existing
        # deployments don't credit any tier bonus until admin opts in.
        from database import get_setting
        # Hard check — must be explicitly enabled (not just default)
        if get_setting("tier_bonus_enabled", "0") != "1":
            return 0
        from database import get_user_tier_data, add_points
        data = get_user_tier_data(user_id)
        if not data:
            return 0
        tier_key = data.get("tier_key") or "bronze"
        pts = int(get_bonus_for_tier(tier_key))
        if pts > 0:
            try:
                add_points(user_id, pts)
            except Exception:
                return 0
            return pts
        return 0
    except Exception:
        return 0


async def notify_tier_upgrade(bot, user_id, new_tier_key):
    """🆕 v68: Send tier upgrade congrats using admin's custom message
       (from tier_config.py) when enabled. Falls back to i18n default."""
    try:
        from database import get_tier_info as _live_tier_info
        tier_info = _live_tier_info(new_tier_key)
        if not tier_info:
            return

        # 🆕 v68: prefer admin's custom message
        custom_msg = ""
        try:
            # [v77-merge] from tier_config import (
            # [v77-merge] is_tier_msg_enabled, get_upgrade_message_for_tier,
            # [v77-merge] get_bonus_for_tier,
            # [v77-merge] )
            if is_tier_msg_enabled():
                custom_msg = (get_upgrade_message_for_tier(new_tier_key) or "").strip()
            bonus_pts = get_bonus_for_tier(new_tier_key)
        except Exception:
            bonus_pts = 0

        if custom_msg:
            body = (
                f"🎉 *Congratulations!*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"You've reached *{tier_info['name']}* tier!\n\n"
                f"{custom_msg}"
            )
            if bonus_pts > 0:
                body += f"\n\n🎁 *New benefit:* +{bonus_pts} bonus points per order"
            await bot.send_message(user_id, body, parse_mode="Markdown")
        else:
            # Legacy fallback
            lang = get_user_lang(user_id)
            msg = t("tier_upgraded", lang=lang, tier=tier_info['name'])
            extra = ""
            if bonus_pts > 0:
                extra = f"\n\n🎁 New benefit: +{bonus_pts} bonus points per order!"
            await bot.send_message(user_id, msg + extra, parse_mode="Markdown")

        # Broadcast real upgrade to active destinations (group / bot)
        await broadcast_real_tier_upgrade(bot, user_id, new_tier_key)
    except Exception:
        pass


# ============================================================
# 📄 ORIGINAL FILE: handlers_share_product.py
# ============================================================

# ============================================================
# 🔗 SHARE PRODUCT LINK (v70)
# ============================================================
# Each product (in shop) gets a "🔗 Share" button.
# Tap → bot offers: (a) Copy link with pre-filled teaser, (b) QR code image.
# Both use the existing Telegram deep-link `t.me/<botname>?start=buy_<pid>`.
#
# Skip rule: if the product has Free-via-Referrals enabled (admin set), the
# share button is HIDDEN. User must use Refer button (already shown on product).
# This is to avoid people sharing direct buy links when admin wants viral
# referral-based growth.
# ============================================================

import io
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import get_product, get_product_free_config
from utils import escape_md, name_for_message_html

logger = logging.getLogger(__name__)


def is_share_allowed(product_id: int) -> bool:
    """Returns False if product has Free-via-Referrals enabled — then we hide share button."""
    try:
        cfg = get_product_free_config(int(product_id))
        return int(cfg.get("enabled", 0)) == 0
    except Exception:
        return True


def get_share_button(product_id: int) -> InlineKeyboardButton | None:
    """Return the inline button to add to product_detail keyboard.
       Returns None if Free-via-Referrals is enabled (caller skips)."""
    if not is_share_allowed(int(product_id)):
        return None
    return InlineKeyboardButton("🔗 Share", callback_data=f"sharep_{int(product_id)}")


def _clean_product_name(raw_name: str) -> str:
    """Strip [[HTML]] sentinel + tags for plain-text use in deep-link teasers."""
    if not raw_name:
        return "Product"
    try:
        s = name_for_message_html(raw_name) or raw_name
        import re as _re
        s = _re.sub(r'<[^>]+>', '', s)
        return s.strip()[:60] or "Product"
    except Exception:
        return str(raw_name)[:60]


async def share_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User tapped 🔗 Share on a product. Show 2 options: Copy Link + Get QR."""
    q = update.callback_query
    await q.answer()
    try:
        pid = int(q.data.replace("sharep_", ""))
    except Exception:
        await q.answer("Invalid product", show_alert=True); return

    p = get_product(pid)
    if not p:
        await q.answer("Product not found", show_alert=True); return

    # Re-check (in case admin toggled referral flag between rendering and tap)
    if not is_share_allowed(pid):
        await q.answer("Share not available for this product.", show_alert=True)
        return

    # Build deep link
    try:
        me = await context.bot.get_me()
        bot_username = me.username
    except Exception:
        bot_username = "your_bot"

    name = _clean_product_name(p['name'])
    try:
        price = float(p['price'] or 0)
    except Exception:
        price = 0.0
    deeplink = f"https://t.me/{bot_username}?start=buy_{pid}"

    # Pre-filled teaser text (the message user will copy + paste anywhere)
    teaser = (
        f"🔥 *{name}* — only *${price:.2f}*!\n\n"
        f"Buy now from @{bot_username}:\n"
        f"{deeplink}"
    )

    text = (
        f"🔗 *Share This Product*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 *{escape_md(name)}*\n"
        f"💰 *${price:.2f}*\n\n"
        f"*Direct link:*\n"
        f"`{deeplink}`\n\n"
        f"*Ready-to-share message:*\n"
        f"```\n{teaser}\n```\n\n"
        f"_Tap the message above to copy it, then paste anywhere "
        f"(WhatsApp, Telegram, Facebook, etc.)._\n\n"
        f"For a QR code (great for printing or posters), tap below."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Get QR Code",      callback_data=f"shareqr_{pid}")],
        [InlineKeyboardButton("🔙 Back to Product",  callback_data=f"prod_{pid}")],
    ])
    try:
        # If we're viewing a photo-message, edit caption; else edit text.
        if q.message and q.message.photo:
            await q.edit_message_caption(caption=text, parse_mode="Markdown", reply_markup=kb)
        else:
            await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        # Fallback: send a new message
        try:
            await context.bot.send_message(q.from_user.id, text,
                                            parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass


async def share_qr_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate + send a QR code PNG for the product's deep link."""
    q = update.callback_query
    await q.answer("Generating QR…", show_alert=False)
    try:
        pid = int(q.data.replace("shareqr_", ""))
    except Exception:
        await q.answer("Invalid product", show_alert=True); return

    p = get_product(pid)
    if not p:
        await q.answer("Product not found", show_alert=True); return

    try:
        me = await context.bot.get_me()
        bot_username = me.username
    except Exception:
        bot_username = "your_bot"

    name = _clean_product_name(p['name'])
    deeplink = f"https://t.me/{bot_username}?start=buy_{pid}"

    # Generate QR via the `qrcode` library (requires Pillow)
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(deeplink)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        buf.name = f"qr_product_{pid}.png"
    except ImportError:
        await q.answer("QR library not installed — please reinstall.", show_alert=True)
        return
    except Exception as e:
        logger.warning(f"[ShareQR] generate failed: {e}")
        await q.answer("Failed to generate QR.", show_alert=True)
        return

    caption = (
        f"📱 *QR Code — {escape_md(name)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 *${float(p['price'] or 0):.2f}*\n\n"
        f"Anyone who scans this code goes directly to the product on your bot.\n\n"
        f"_Save the image and share it on Instagram, status, posters, etc._"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Product", callback_data=f"prod_{pid}")],
    ])
    try:
        await context.bot.send_photo(
            chat_id=q.from_user.id, photo=buf,
            caption=caption, parse_mode="Markdown", reply_markup=kb,
        )
        # Also delete the previous share-options message for cleanliness
        try:
            await q.message.delete()
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"[ShareQR] send failed: {e}")
        await q.answer("Send failed — please try again.", show_alert=True)


# ============================================================
# 📄 ORIGINAL FILE: handlers_pinned.py
# ============================================================

# ============================================================
# 📌 PINNED ANNOUNCEMENTS — admin handlers (v70)
# ============================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID
from utils import escape_md, smart_text_and_mode
# [v77-merge] from pinned_announcements import (
# [v77-merge] add_pin, get_all_pins, delete_pin, toggle_pin, ensure_table,
# [v77-merge] )
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════
# 📌 MAIN PANEL — list all pins
# ════════════════════════════════════════════
async def admin_pins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all pinned announcements (active + expired)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    ensure_table()
    pins = get_all_pins()

    lines = [
        "📌 *Pinned Announcements*",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not pins:
        lines.append("_No pinned announcements yet._")
        lines.append("")
        lines.append("Tap *➕ Add New Pin* below to create one.")
        lines.append("")
        lines.append("Pinned messages appear at the top of every user's *Main Menu*.")
    else:
        from datetime import datetime
        now = datetime.utcnow()
        for p in pins[:10]:
            pid = p['id']
            text = (p['text'] or '')[:80].replace('\n', ' ')
            active = int(p.get('active', 1))
            expires_at = p.get('expires_at') or ''
            status_icon = "🟢" if active else "⏸️"
            expiry_label = ""
            if expires_at:
                try:
                    exp_dt = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
                    if exp_dt < now:
                        status_icon = "⌛"
                        expiry_label = " (expired)"
                    else:
                        delta = exp_dt - now
                        hours = int(delta.total_seconds() / 3600)
                        if hours < 24:
                            expiry_label = f" (expires in {hours}h)"
                        else:
                            days = hours // 24
                            expiry_label = f" (expires in {days}d)"
                except Exception:
                    pass
            else:
                expiry_label = " (no expiry)"
            lines.append(f"{status_icon} *#{pid}* — {escape_md(text)}{expiry_label}")

    # 🆕 v101: real-pin-mode status line at the top so admin knows which mode is active
    _real_mode = is_real_pin_mode()
    _rm_label = "🟢 ON" if _real_mode else "🔴 OFF"
    lines.insert(2, f"📢 *Real Pin Mode:* {_rm_label}")
    lines.insert(3, "_When ON: new pins are broadcast + pinned in each user's DM._")
    lines.insert(4, "_When OFF: pins appear inside the welcome message (legacy)._")
    lines.insert(5, "")

    kb = [
        [InlineKeyboardButton("➕ Add New Pin",        callback_data="admin_pins_add")],
        [InlineKeyboardButton("📋 Quick Templates",   callback_data="admin_pins_templates")],
        # 🆕 v101: Real Pin Mode toggle
        [InlineKeyboardButton(
            f"📢 Real Pin Mode: {'🟢 ON' if _real_mode else '🔴 OFF'}",
            callback_data="admin_pin_realmode_toggle")],
    ]
    # Per-pin manage rows — 🆕 v101: also add "📢 Broadcast+Pin Now" per pin
    for p in pins[:10]:
        pid = p['id']
        kb.append([
            InlineKeyboardButton(f"⏸️/▶️ #{pid}", callback_data=f"admin_pin_toggle_{pid}"),
            InlineKeyboardButton(f"📢 Push #{pid}", callback_data=f"admin_pin_push_{pid}"),
            InlineKeyboardButton(f"🗑 #{pid}",    callback_data=f"admin_pin_del_{pid}"),
        ])
    kb.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")])

    send_text, send_mode = smart_text_and_mode("\n".join(lines)[:3900], "Markdown")
    try:
        await q.edit_message_text(send_text, parse_mode=send_mode, reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        await q.edit_message_text("\n".join(lines)[:3900], reply_markup=InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════
# ➕ ADD NEW PIN — step 1: ask for text
# ════════════════════════════════════════════
async def admin_pins_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data["admin_pin_step"] = "waiting_text"

    text = (
        "➕ *Add New Pinned Announcement*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Type the announcement text in your *next message*.\n\n"
        "It will appear at the top of every user's *Main Menu*.\n\n"
        "Examples:\n"
        "  • `🎉 Eid sale 50% off — ends Friday!`\n"
        "  • `⚠️ Server maintenance 12 AM-2 AM tonight`\n"
        "  • `🆕 New product alert: Gemini Pro added`\n\n"
        "_Max 1500 characters. Markdown supported._"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_pins")],
    ])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def admin_pin_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive pin text from admin → ask for expiry duration.

    🆕 v101: auto-detect Telegram Premium emoji in admin's message. If any
    custom_emoji entity is present, capture HTML version (preserves
    <tg-emoji emoji-id="...">📱</tg-emoji> markup) and set parse_mode='HTML'
    so the pin renders premium emojis correctly for every user.
    """
    if context.user_data.get("admin_pin_step") != "waiting_text":
        return False
    if update.effective_user.id != ADMIN_ID:
        return False

    msg = update.message
    # 🆕 v101: premium emoji auto-detection
    entities = msg.entities or []
    has_premium = any(getattr(e, "type", "") == "custom_emoji" for e in entities)
    if has_premium:
        try:
            pin_text = (msg.text_html_urled or msg.text_html or msg.text or "").strip()
        except Exception:
            pin_text = (msg.text or "").strip()
        pin_parse_mode = "HTML"
    else:
        pin_text = (msg.text or "").strip()
        pin_parse_mode = "Markdown"

    if len(pin_text) < 3:
        await update.message.reply_text(
            "❌ Text too short (min 3 characters). Try again or tap Cancel from previous screen.")
        return True
    if len(pin_text) > 1500:
        await update.message.reply_text(
            "❌ Text too long (max 1500 characters). Please shorten it.")
        return True

    # Stash and ask for expiry (also stash parse_mode)
    context.user_data["admin_pin_pending_text"] = pin_text
    context.user_data["admin_pin_pending_parse_mode"] = pin_parse_mode
    context.user_data["admin_pin_step"] = "waiting_expiry"

    preview = pin_text[:200] + ("…" if len(pin_text) > 200 else "")
    text = (
        f"✏️ *Pin Preview:*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{escape_md(preview)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ *Pick expiry duration:*"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 hour",    callback_data="admin_pin_exp_1"),
            InlineKeyboardButton("6 hours",   callback_data="admin_pin_exp_6"),
        ],
        [
            InlineKeyboardButton("24 hours",  callback_data="admin_pin_exp_24"),
            InlineKeyboardButton("3 days",    callback_data="admin_pin_exp_72"),
        ],
        [
            InlineKeyboardButton("7 days",    callback_data="admin_pin_exp_168"),
            InlineKeyboardButton("Never",     callback_data="admin_pin_exp_0"),
        ],
        [InlineKeyboardButton("❌ Cancel",    callback_data="admin_pin_cancel_add")],
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return True


async def admin_pin_expiry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin picked an expiry → finalize pin."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    try:
        hours = int(q.data.replace("admin_pin_exp_", ""))
    except Exception:
        hours = 0

    text = context.user_data.pop("admin_pin_pending_text", "")
    parse_mode = context.user_data.pop("admin_pin_pending_parse_mode", "Markdown")
    context.user_data.pop("admin_pin_step", None)

    if not text:
        await q.edit_message_text(
            "❌ Pin text lost. Please start again.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📌 Back to Pins", callback_data="admin_pins")]]))
        return

    new_id = add_pin(text, expires_hours=hours, parse_mode=parse_mode)
    expiry_label = "never" if hours == 0 else (f"in {hours} hours" if hours < 24 else f"in {hours//24} days")

    # 🆕 v101: if Real Pin Mode is ON, broadcast + pin to every user's DM
    real_mode = is_real_pin_mode()
    broadcast_note = ""
    if real_mode and new_id:
        try:
            sent, pinned, failed = await broadcast_and_pin(context.bot, new_id)
            broadcast_note = (
                f"\n\n📢 *Real Pin Mode ACTIVE:*\n"
                f"  • Delivered: *{sent}* users\n"
                f"  • Pinned in DM: *{pinned}* users\n"
                f"  • Failed: *{failed}*\n"
                f"_Auto-unpin will fire on expiry._"
            )
        except Exception as e:
            broadcast_note = f"\n\n⚠️ Real Pin broadcast partially failed: {e}"

    location_note = ("pinned directly in every user's chat"
                     if real_mode else
                     "appear at the top of every user's Main Menu")
    premium_note = " 🎨 _(premium emojis detected)_" if parse_mode == "HTML" else ""
    confirm = (
        f"✅ *Pin #{new_id} added!*{premium_note}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Will be {location_note}, "
        f"expires *{expiry_label}*.{broadcast_note}"
    )
    await q.edit_message_text(confirm, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Another", callback_data="admin_pins_add")],
            [InlineKeyboardButton("📌 All Pins",    callback_data="admin_pins")],
        ]))


async def admin_pin_cancel_add_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Cancelled.")
    context.user_data.pop("admin_pin_step", None)
    context.user_data.pop("admin_pin_pending_text", None)
    context.user_data.pop("admin_pin_pending_parse_mode", None)
    await admin_pins_callback(update, context)


# ════════════════════════════════════════════════════════════════
# 🆕 v101: REAL-PIN-MODE TOGGLE + MANUAL PUSH
# ════════════════════════════════════════════════════════════════
async def admin_pin_realmode_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    cur = is_real_pin_mode()
    set_real_pin_mode(not cur)
    await q.answer(f"Real Pin Mode: {'ON ✅' if not cur else 'OFF ❌'}",
                   show_alert=False)
    await admin_pins_callback(update, context)


async def admin_pin_push_callback(update, context):
    """Manually broadcast + pin an existing pin to all users' DMs.
    Useful when Real Pin Mode was OFF at add-time but admin wants to push now.
    """
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("📢 Broadcasting…")
    try:
        pid = int(q.data.replace("admin_pin_push_", ""))
    except Exception:
        return
    try:
        sent, pinned, failed = await broadcast_and_pin(context.bot, pid)
        await q.answer(f"✅ Sent {sent} · Pinned {pinned} · Failed {failed}",
                       show_alert=True)
    except Exception as e:
        await q.answer(f"❌ {e}", show_alert=True)
    await admin_pins_callback(update, context)


# ════════════════════════════════════════════
# 🆕 v79: READYMADE PIN TEMPLATES
# ════════════════════════════════════════════
# Common situations the shop owner faces — 1-click pin add with sensible default
# expiry. Tap a template → pin appears at top of every user's main menu instantly.

PIN_TEMPLATES = [
    # (situation_label, pin_text, default_expiry_hours)
    ("🟢 Bot is LIVE",
     "🟢 *Bot is LIVE and ready!*\n"
     "All systems running smoothly. Orders are being processed instantly. ⚡",
     0),
    ("🟡 Working / Busy",
     "🟡 *We're actively working on orders right now*\n"
     "Replies may be a bit slower. Thank you for your patience! 🙏",
     6),
    ("🔧 Maintenance Mode",
     "🔧 *Scheduled Maintenance*\n"
     "The bot is undergoing maintenance. New orders may take longer to process. "
     "We'll be back to normal speed shortly. Thanks for understanding! 🛠",
     2),
    ("⛔ Bot Closed Temporarily",
     "⛔ *Bot is temporarily closed for new orders*\n"
     "We're upgrading systems. Please check back in a few hours. "
     "Existing orders will still be delivered. 🙏",
     12),
    ("🆕 New Product Added",
     "🆕 *New Product Alert!*\n"
     "Check out our latest addition in the 🛒 Shop. Limited stock available! 🔥",
     48),
    ("🎉 Sale ON",
     "🎉 *MEGA SALE IS LIVE!*\n"
     "Massive discounts on selected products. Open the 🛒 Shop and grab yours before stock runs out! ⚡",
     24),
    ("🔥 Flash Sale",
     "🔥 *Flash Sale — Limited Time!*\n"
     "Special prices for the next few hours only. Don't miss it! ⏳",
     3),
    ("📦 Restock Update",
     "📦 *Restock Update*\n"
     "Out-of-stock products have been refilled. Check the 🛒 Shop now! ✅",
     24),
    ("⚠️ Payment Delay",
     "⚠️ *Payment Verification Delay*\n"
     "We're experiencing a slight delay in payment verifications. "
     "Your order is safe — it'll be delivered as soon as verification completes. 🙏",
     6),
    ("🎁 Special Offer",
     "🎁 *Special Offer for Our Customers!*\n"
     "Limited-time bonus on selected products. Tap 🛒 Shop to see what's new! ✨",
     48),
    ("🌙 Night Mode",
     "🌙 *Late-night service — auto delivery active*\n"
     "All orders being processed automatically. Admin will personally check in the morning if there's any issue. 💤",
     8),
    ("💬 Support Update",
     "💬 *Support Tickets — Quick Reply Mode*\n"
     "Admin is actively answering tickets right now. Open 🎫 Support if you need help!",
     4),
    ("🎊 Holiday Greeting",
     "🎊 *Happy Holidays from BITE STORE!*\n"
     "Wishing you a great day. Special deals are live — check the 🛒 Shop! 💝",
     24),
    ("📢 Announcement",
     "📢 *Important Announcement*\n"
     "Please read the latest update from our team. More details inside the bot. 📌",
     12),
]


async def admin_pins_templates_callback(update, context):
    """Show readymade pin templates — 1-click add."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    text = (
        "📋 *Quick Pin Templates*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Tap any template below to instantly pin it. Default expiry applies "
        "(you can delete or toggle anytime from 📌 Pinned Announcements panel).\n\n"
        "_All templates use Markdown formatting and ready-made wording for common situations._"
    )
    kb = []
    for i, (label, _txt, _exp) in enumerate(PIN_TEMPLATES):
        kb.append([InlineKeyboardButton(label, callback_data=f"admin_pin_tpl_{i}")])
    kb.append([InlineKeyboardButton("🔙 Back to Pinned Announcements",
                                     callback_data="admin_pins")])
    await q.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(kb))


async def admin_pin_use_template_callback(update, context):
    """1-click use a template — adds it as a pin immediately."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        idx = int(q.data.replace("admin_pin_tpl_", ""))
        if idx < 0 or idx >= len(PIN_TEMPLATES):
            raise ValueError
    except Exception:
        await q.answer("⚠️ Bad template", show_alert=True); return
    label, pin_text, exp_hours = PIN_TEMPLATES[idx]
    new_id = add_pin(pin_text, expires_hours=exp_hours)
    exp_label = "never" if exp_hours == 0 else (
        f"in {exp_hours} hours" if exp_hours < 24 else f"in {exp_hours//24} days"
    )
    await q.answer(f"✅ Pin #{new_id} added!", show_alert=True)
    confirm = (
        f"✅ *{label} pin added!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Pin #{new_id}:*\n{pin_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Expires *{exp_label}*\n"
        f"📍 Shows on every user's Main Menu now"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 More Templates",   callback_data="admin_pins_templates")],
        [InlineKeyboardButton("📌 Back to Pins",      callback_data="admin_pins")],
    ])
    await q.edit_message_text(confirm, parse_mode="Markdown", reply_markup=kb)


# ════════════════════════════════════════════
# 🗑 DELETE / ⏸ TOGGLE
# ════════════════════════════════════════════
async def admin_pin_del_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        pin_id = int(q.data.replace("admin_pin_del_", ""))
    except Exception:
        await q.answer("Invalid ID", show_alert=True); return
    # 🆕 v101: unpin from every user's chat FIRST if this pin was broadcast
    try:
        await unpin_and_deactivate(context.bot, pin_id)
    except Exception:
        pass
    ok = delete_pin(pin_id)
    await q.answer("🗑 Deleted (and unpinned)" if ok else "❌ Failed", show_alert=False)
    await admin_pins_callback(update, context)


async def admin_pin_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        pin_id = int(q.data.replace("admin_pin_toggle_", ""))
    except Exception:
        await q.answer("Invalid ID", show_alert=True); return
    ok = toggle_pin(pin_id)
    await q.answer("Toggled" if ok else "❌ Failed", show_alert=False)
    await admin_pins_callback(update, context)


# ============================================================
# 📄 ORIGINAL FILE: pinned_announcements.py
# ============================================================

# ============================================================
# 📌 PINNED ANNOUNCEMENTS (v70)
# ============================================================
# Admin can pin 1-N important messages that appear at the top of every
# user's Main Menu screen. Each pin has an optional expiry date.
#
# Use cases:
#   • "🎉 Eid sale 50% off — ends Friday!"
#   • "⚠️ Server maintenance 12 AM-2 AM tonight"
#   • "🆕 New product alert: Gemini Pro added"
#
# Storage: own SQLite table (additive, no migrations to existing tables).
# ============================================================

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def ensure_table():
    """Create pinned_announcements table if not exists.

    🆕 v101 additive columns (safe migration via ensure_column):
      • parse_mode              — 'HTML' / 'Markdown' (preserves premium emoji)
      • pinned_message_ids_json — {user_id: message_id, ...} — tracks the
                                   pinned message per user so watchdog can unpin
      • is_broadcasted          — 1 if this pin has already been sent to users
    """
    try:
        from database import get_connection, ensure_column
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS pinned_announcements (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                text       TEXT NOT NULL,
                expires_at TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active     INTEGER DEFAULT 1
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pins_active ON pinned_announcements(active)")
        # 🆕 v101 additive
        ensure_column(c, "pinned_announcements", "parse_mode", "TEXT DEFAULT 'Markdown'")
        ensure_column(c, "pinned_announcements", "pinned_message_ids_json", "TEXT DEFAULT '{}'")
        ensure_column(c, "pinned_announcements", "is_broadcasted", "INTEGER DEFAULT 0")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"[Pins] ensure_table failed: {e}")


def add_pin(text: str, expires_hours: int = 0, parse_mode: str = "Markdown") -> int:
    """Add a new pinned announcement. Returns the new pin's ID.
       expires_hours=0 means never expires.

       🆕 v101: parse_mode param — 'HTML' preserves <tg-emoji> premium markup
       and <b>/<i>/<code> tags. Defaults to 'Markdown' for legacy compat.
    """
    if not text or not text.strip():
        return 0
    try:
        ensure_table()
        from database import get_connection
        expires_at = ""
        if expires_hours and int(expires_hours) > 0:
            expires_at = (datetime.utcnow() + timedelta(hours=int(expires_hours))).strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        c = conn.cursor()
        pm = parse_mode if parse_mode in ("HTML", "Markdown") else "Markdown"
        c.execute(
            "INSERT INTO pinned_announcements (text, expires_at, active, parse_mode) VALUES (?, ?, 1, ?)",
            (str(text)[:1500], expires_at, pm),
        )
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        return int(new_id or 0)
    except Exception as e:
        logger.warning(f"[Pins] add_pin failed: {e}")
        return 0


# ════════════════════════════════════════════════════════════════
# 🆕 v101: REAL PIN BROADCAST — send + pin to each user's DM
# ════════════════════════════════════════════════════════════════
# Two operating modes:
#   MODE A (legacy — default OFF): pins prepend to welcome text
#   MODE B (new — Real Pin Mode ON): announcement sent as a normal message
#     then Telegram-pinned in each user's private chat. Auto-unpins on expiry.
#
# Toggle key: bot_settings['pin_real_mode'] = '1' | '0'  (default '0')
# ════════════════════════════════════════════════════════════════

def is_real_pin_mode() -> bool:
    """Admin toggle: is Real Pin Broadcast Mode ON?"""
    try:
        from database import get_setting
        return str(get_setting("pin_real_mode", "0")) == "1"
    except Exception:
        return False


def set_real_pin_mode(on: bool):
    try:
        from database import set_setting
        set_setting("pin_real_mode", "1" if on else "0")
    except Exception:
        pass


async def broadcast_and_pin(bot, pin_id: int) -> tuple:
    """Send the pin's text to every registered user's DM and pin it there.

    Uses the pin's stored parse_mode so premium <tg-emoji> markup renders.
    Records the per-user message_id in pinned_message_ids_json so the
    watchdog can unpin on expiry / manual removal.

    Returns (sent_count, pinned_count, failed_count)
    """
    from database import get_connection, get_all_users
    import json as _json
    ensure_table()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT id, text, parse_mode, pinned_message_ids_json FROM pinned_announcements WHERE id=?",
              (int(pin_id),))
    row = c.fetchone()
    conn.close()
    if not row:
        return 0, 0, 0
    text = row["text"]
    parse_mode = row["parse_mode"] or "Markdown"

    # Auto-detect HTML if content has premium/tag markup
    try:
        from utils import smart_text_and_mode
        send_text, send_mode = smart_text_and_mode(text, parse_mode)
    except Exception:
        send_text, send_mode = text, parse_mode

    msg_map = {}
    try:
        msg_map = _json.loads(row["pinned_message_ids_json"] or "{}")
    except Exception:
        msg_map = {}

    users = get_all_users() or []
    sent = pinned = failed = 0
    for u in users:
        uid = u["user_id"] if hasattr(u, "__getitem__") else u.get("user_id")
        if not uid:
            continue
        try:
            m = await bot.send_message(chat_id=uid, text=send_text,
                                       parse_mode=send_mode,
                                       disable_web_page_preview=True)
            sent += 1
            # Try to pin — safe in private chats (no admin needed)
            try:
                await bot.pin_chat_message(chat_id=uid,
                                           message_id=m.message_id,
                                           disable_notification=False)
                pinned += 1
                msg_map[str(uid)] = m.message_id
            except Exception as _pe:
                logger.debug(f"[pin_broadcast] pin failed uid={uid}: {_pe}")
        except Exception as _e:
            failed += 1
            logger.debug(f"[pin_broadcast] send failed uid={uid}: {_e}")

    # Persist the map + mark as broadcasted
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE pinned_announcements SET pinned_message_ids_json=?, is_broadcasted=1 WHERE id=?",
                  (_json.dumps(msg_map), int(pin_id)))
        conn.commit(); conn.close()
    except Exception as e:
        logger.warning(f"[pin_broadcast] persist msg_map failed: {e}")

    return sent, pinned, failed


async def unpin_and_deactivate(bot, pin_id: int) -> tuple:
    """Unpin the message from every user chat where it was pinned + mark
    the pin inactive. Called by watchdog on expiry, or manually by admin.

    Returns (unpinned_count, failed_count)
    """
    from database import get_connection
    import json as _json
    ensure_table()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT pinned_message_ids_json FROM pinned_announcements WHERE id=?",
              (int(pin_id),))
    row = c.fetchone()
    conn.close()
    if not row:
        return 0, 0

    try:
        msg_map = _json.loads(row["pinned_message_ids_json"] or "{}")
    except Exception:
        msg_map = {}

    unpinned = failed = 0
    for uid_str, mid in msg_map.items():
        try:
            await bot.unpin_chat_message(chat_id=int(uid_str), message_id=int(mid))
            unpinned += 1
        except Exception as _e:
            failed += 1
            logger.debug(f"[pin_broadcast] unpin uid={uid_str}: {_e}")

    # Mark inactive
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE pinned_announcements SET active=0 WHERE id=?", (int(pin_id),))
        conn.commit(); conn.close()
    except Exception:
        pass

    return unpinned, failed


async def pin_expiry_watchdog_job(context):
    """Background job — every 5 minutes, unpin expired announcements.
    Registered in bot.py setup_jobs().
    """
    from database import get_connection
    ensure_table()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("""
            SELECT id FROM pinned_announcements
            WHERE active = 1
              AND expires_at != ''
              AND expires_at <= ?
        """, (now,))
        expired_ids = [r["id"] for r in c.fetchall()]
        conn.close()
    except Exception as e:
        logger.debug(f"[pin_watchdog] scan failed: {e}")
        return

    if not expired_ids:
        return

    for pid in expired_ids:
        try:
            u, f = await unpin_and_deactivate(context.bot, pid)
            logger.info(f"[pin_watchdog] pin #{pid} expired — unpinned {u} chats ({f} failed)")
        except Exception as e:
            logger.warning(f"[pin_watchdog] pin #{pid} unpin loop failed: {e}")


def get_active_pins() -> list:
    """Return all currently-active, non-expired pins (newest first)."""
    try:
        ensure_table()
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        # active=1 AND (no expiry OR not yet expired)
        c.execute("""
            SELECT id, text, expires_at, created_at
            FROM pinned_announcements
            WHERE active = 1
              AND (expires_at = '' OR expires_at > ?)
            ORDER BY id DESC
        """, (now,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"[Pins] get_active_pins failed: {e}")
        return []


def get_all_pins(include_expired: bool = True) -> list:
    """Admin view — all pins ever (including expired/inactive)."""
    try:
        ensure_table()
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT id, text, expires_at, created_at, active
            FROM pinned_announcements
            ORDER BY id DESC
            LIMIT 50
        """)
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"[Pins] get_all_pins failed: {e}")
        return []


def delete_pin(pin_id: int) -> bool:
    try:
        ensure_table()
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM pinned_announcements WHERE id=?", (int(pin_id),))
        ok = c.rowcount > 0
        conn.commit()
        conn.close()
        return ok
    except Exception as e:
        logger.warning(f"[Pins] delete_pin failed: {e}")
        return False


def toggle_pin(pin_id: int) -> bool:
    """Toggle active flag (0 ↔ 1)."""
    try:
        ensure_table()
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT active FROM pinned_announcements WHERE id=?", (int(pin_id),))
        row = c.fetchone()
        if not row:
            conn.close(); return False
        new_val = 0 if int(row['active']) == 1 else 1
        c.execute("UPDATE pinned_announcements SET active=? WHERE id=?", (new_val, int(pin_id)))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.warning(f"[Pins] toggle_pin failed: {e}")
        return False


def format_pins_for_menu() -> str:
    """Return formatted string to prepend to user's main menu message.
       Empty string if no active pins.

       🆕 v101: when Real Pin Mode is ON, returns "" so pins DON'T show
       inside the welcome message — they exist only as real Telegram
       pinned messages in each user's chat (pro-user pattern). Toggle at
       admin → 📌 Pinned Announcements → 📢 Real Pin Mode.
    """
    if is_real_pin_mode():
        return ""
    pins = get_active_pins()
    if not pins:
        return ""
    parts = ["📌 *Pinned Announcements*", "━━━━━━━━━━━━━━━━━━━━"]
    for p in pins:
        parts.append("")
        parts.append(str(p['text']))
    parts.append("━━━━━━━━━━━━━━━━━━━━")
    parts.append("")
    return "\n".join(parts)


# ============================================================
# 📄 ORIGINAL FILE: tier_config.py
# ============================================================

# ============================================================
# 🏆 CUSTOMIZABLE TIER CONFIG (v68)
# ============================================================
# Loyalty tiers — admin can edit thresholds, per-order bonus points,
# and custom upgrade messages from the admin panel.
#
# Backed by `bot_settings` table (JSON in `tier_config_json` key).
# Falls back to hardcoded defaults if no admin override exists.
# ============================================================

import json
import logging

logger = logging.getLogger(__name__)

# Default tier config — used when admin hasn't customised yet
DEFAULTS = [
    {
        "key": "bronze",
        "name": "🥉 Bronze",
        "min_spent": 0,
        "bonus_pts": 0,
        "upgrade_msg": (
            "Welcome to the Bite Store loyalty program! 🥉\n\n"
            "Start shopping to unlock higher tiers with bonus rewards."
        ),
    },
    {
        "key": "silver",
        "name": "🥈 Silver",
        "min_spent": 100,
        "bonus_pts": 0,
        "upgrade_msg": (
            "Congratulations! You've reached Silver tier 🥈\n\n"
            "Keep shopping to unlock more rewards!"
        ),
    },
    {
        "key": "gold",
        "name": "🥇 Gold",
        "min_spent": 500,
        "bonus_pts": 3,
        "upgrade_msg": (
            "Amazing! You're now a Gold member 🥇\n\n"
            "From now on you earn 3 bonus points on every order!"
        ),
    },
    {
        "key": "platinum",
        "name": "💎 Platinum",
        "min_spent": 1000,
        "bonus_pts": 5,
        "upgrade_msg": (
            "Outstanding! Welcome to Platinum tier 💎\n\n"
            "You now earn 5 bonus points on every order. "
            "Thank you for your loyalty!"
        ),
    },
    {
        "key": "diamond",
        "name": "💠 Diamond",
        "min_spent": 2500,
        "bonus_pts": 10,
        "upgrade_msg": (
            "Legendary! You're now a Diamond VIP 💠\n\n"
            "10 bonus points on every order — our highest tier. "
            "You're an absolute legend!"
        ),
    },
]


def _load_tier_settings():
    """Read tier config from DB. Returns list of dicts (5 tiers)."""
    try:
        from database import get_setting
        raw = get_setting("tier_config_json", "")
        if not raw:
            return [dict(t) for t in DEFAULTS]
        data = json.loads(raw)
        # Validate: must be a list of 5 dicts with required keys
        if not isinstance(data, list) or len(data) != 5:
            return [dict(t) for t in DEFAULTS]
        out = []
        for i, item in enumerate(data):
            d = dict(DEFAULTS[i])  # start with defaults
            if isinstance(item, dict):
                d.update({k: item[k] for k in ("min_spent", "bonus_pts", "upgrade_msg")
                          if k in item})
            out.append(d)
        return out
    except Exception as e:
        logger.warning(f"[Tier] load failed: {e}")
        return [dict(t) for t in DEFAULTS]


def _save_tier_settings(tiers):
    """Persist tier config to DB."""
    try:
        from database import set_setting
        # Only save the editable fields, name/key are fixed
        slim = [
            {
                "key": t["key"],
                "min_spent": float(t.get("min_spent", 0)),
                "bonus_pts": int(t.get("bonus_pts", 0)),
                "upgrade_msg": str(t.get("upgrade_msg", ""))[:1000],
            }
            for t in tiers
        ]
        set_setting("tier_config_json", json.dumps(slim, ensure_ascii=False))
        return True
    except Exception as e:
        logger.warning(f"[Tier] save failed: {e}")
        return False


def get_tier_config():
    """Public — get the live tier config (admin-customised or defaults)."""
    return _load_tier_settings()


def set_tier_field(tier_key, field, value):
    """Update a single field of a single tier and persist."""
    tiers = _load_tier_settings()
    for t in tiers:
        if t["key"] == tier_key:
            if field == "min_spent":
                t["min_spent"] = float(value)
            elif field == "bonus_pts":
                t["bonus_pts"] = int(value)
            elif field == "upgrade_msg":
                t["upgrade_msg"] = str(value)[:1000]
            break
    return _save_tier_settings(tiers)


def reset_to_defaults():
    """Restore all tiers to factory defaults."""
    try:
        from database import set_setting
        set_setting("tier_config_json", "")
        return True
    except Exception:
        return False


# ── Toggles ──
def is_tier_bonus_enabled():
    """🆕 v69: Master switch — DEFAULT OFF after the v68 free-refund bug.
       Admin must explicitly opt in via Loyalty → Configure Tiers panel."""
    try:
        from database import get_setting
        return get_setting("tier_bonus_enabled", "0") == "1"
    except Exception:
        return False


def set_tier_bonus_enabled(on: bool):
    from database import set_setting
    set_setting("tier_bonus_enabled", "1" if on else "0")


def is_tier_msg_enabled():
    """Master switch: should tier-upgrade messages use admin's custom text?"""
    try:
        from database import get_setting
        return get_setting("tier_msg_enabled", "1") == "1"
    except Exception:
        return True


def set_tier_msg_enabled(on: bool):
    from database import set_setting
    set_setting("tier_msg_enabled", "1" if on else "0")


# ── Compatibility helpers (match old TIER_CONFIG API) ──
def calculate_tier(total_spent, total_orders=0):
    """Returns tier key based on total_spent crossing threshold.
       (orders metric removed in v68 — admin controls only by $ spent)"""
    tiers = _load_tier_settings()
    best = tiers[0]["key"]
    for tier in tiers:
        if float(total_spent or 0) >= float(tier["min_spent"]):
            best = tier["key"]
    return best


def get_tier_info(tier_key):
    """Return the full tier dict for a key."""
    tiers = _load_tier_settings()
    for t in tiers:
        if t["key"] == tier_key:
            return t
    return tiers[0]


def get_next_tier(current_key):
    """Return next-tier dict, or None if at max."""
    tiers = _load_tier_settings()
    keys = [t["key"] for t in tiers]
    try:
        idx = keys.index(current_key)
        if idx + 1 < len(tiers):
            return tiers[idx + 1]
    except ValueError:
        pass
    return None


def get_bonus_for_tier(tier_key):
    """Return per-order bonus points for a tier (respects master toggle)."""
    if not is_tier_bonus_enabled():
        return 0
    info = get_tier_info(tier_key)
    return int(info.get("bonus_pts", 0))


def get_upgrade_message_for_tier(tier_key):
    """Return admin's custom upgrade message for a tier."""
    info = get_tier_info(tier_key)
    return info.get("upgrade_msg", "")

