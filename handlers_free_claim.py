# ════════════════════════════════════════════════════════════════
# 🎁 FREE CLAIM (via Referrals) — Handlers (v47)
# ════════════════════════════════════════════════════════════════
# Two halves in this file:
#   1. ADMIN side — per-product configuration panel
#         opened from product edit screen (button "🎁 Free via Referrals")
#         callbacks:  fcrf_*
#         text input: context.user_data['fcrf_step']
#   2. USER side — claim flow
#         shown on product detail page when enabled & user hasn't claimed
#         callbacks:  freeclaim_*
# ════════════════════════════════════════════════════════════════
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID, SHOP_NAME, DEFAULT_RESPONSES
from utils import (
    escape_md, smart_text_and_mode, notify_admin,
    capture_user_text, safe_display,  # 🆕 v48
)
from database import (
    get_product,
    get_product_free_config, set_product_free_config,
    get_user, count_eligible_unused_refs,
    has_user_claimed_free, record_free_claim,
    create_order, get_order, update_order_status,
    get_all_free_claims,
    deduct_ref_points, get_ref_points,  # 🆕 v48
)
from templates_bundle import (
    FREE_CLAIM_TEMPLATES, build_free_claim_message,
    get_global_template_index, set_global_template_index,
    get_global_custom_text, set_global_custom_text,
)

logger = logging.getLogger(__name__)


def _r(key, default=""):
    """Editable response wrapper — admin can change these from Responses panel."""
    try:
        from database import get_response_with_auto_register
        return get_response_with_auto_register(key, DEFAULT_RESPONSES.get(key, default))
    except Exception:
        return DEFAULT_RESPONSES.get(key, default)


async def _safe_edit(q, text, **kwargs):
    """Edit a message safely (text or caption)."""
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


# ════════════════════════════════════════════════════════════════
# 🔐 ADMIN: Per-product Free Claim panel
# ════════════════════════════════════════════════════════════════

def _admin_panel_text(pid, cfg, prod):
    pname = escape_md(prod["name"]) if prod else f"#{pid}"
    enabled = bool(cfg.get("enabled"))
    refs = int(cfg.get("required_refs") or 5)
    tpl_idx = int(cfg.get("tpl_index") if cfg.get("tpl_index") is not None else -1)
    custom = cfg.get("custom_text") or ""
    if custom.strip():
        tpl_label = "✏️ Custom Text"
    elif tpl_idx >= 0:
        tpl_label = f"🎨 Template #{tpl_idx + 1}"
    else:
        tpl_label = f"🌐 Global Default (#{get_global_template_index() + 1})"

    status = "🟢 *ON*" if enabled else "🔴 *OFF*"
    return (
        f"🎁 *Free via Referrals*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Product: *{pname}*\n"
        f"📊 Status: {status}\n"
        f"👥 Required Referrals: *{refs}*\n"
        f"🎨 Broadcast: {tpl_label}\n\n"
        f"_When ON, users with at least *{refs}* referrals can claim this product for FREE.\n"
        f"Each user can claim this product only ONCE.\n"
        f"A broadcast announcement is sent to your configured destination (see → 🎭 Activity → Destination)._"
    )


def _admin_panel_kb(pid, cfg):
    enabled = bool(cfg.get("enabled"))
    refs = int(cfg.get("required_refs") or 5)
    kb = [
        [InlineKeyboardButton(
            f"{'🟢 Enabled — Tap to Disable' if enabled else '🔴 Disabled — Tap to Enable'}",
            callback_data=f"fcrf_toggle_{pid}"
        )],
        [InlineKeyboardButton(f"👥 Required Refs: {refs}",
                              callback_data=f"fcrf_setrefs_{pid}")],
        [InlineKeyboardButton("🎨 Pick Broadcast Template",
                              callback_data=f"fcrf_tpllist_{pid}_0")],
        [InlineKeyboardButton("✏️ Set Custom Broadcast Text",
                              callback_data=f"fcrf_custom_{pid}")],
        [InlineKeyboardButton("👁️ Preview Broadcast",
                              callback_data=f"fcrf_preview_{pid}"),
         InlineKeyboardButton("📤 Send Test",
                              callback_data=f"fcrf_test_{pid}")],
        [InlineKeyboardButton("📜 Recent Claims (all products)",
                              callback_data="fcrf_history")],
        [InlineKeyboardButton("🔙 Back to Product", callback_data=f"viewprod_{pid}")],
    ]
    return InlineKeyboardMarkup(kb)


async def fcrf_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the per-product Free-Claim admin panel.
    🆕 v55: cancels any in-progress fcrf_* text-input flow."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    # 🆕 v55: cancel any pending text-input flow
    context.user_data.pop("fcrf_step", None)
    context.user_data.pop("fcrf_pid", None)
    try:
        pid = int(q.data.replace("fcrf_panel_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad product id."); return
    prod = get_product(pid)
    if not prod:
        await _safe_edit(q, "❌ Product not found."); return
    cfg = get_product_free_config(pid)
    await _safe_edit(q, _admin_panel_text(pid, cfg, prod),
                     parse_mode="Markdown",
                     reply_markup=_admin_panel_kb(pid, cfg))


async def fcrf_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        pid = int(q.data.replace("fcrf_toggle_", ""))
    except Exception:
        await q.answer("❌ Bad id", show_alert=True); return
    cfg = get_product_free_config(pid)
    new_state = 0 if cfg.get("enabled") else 1
    set_product_free_config(pid, enabled=bool(new_state))
    await q.answer("✅ Toggled", show_alert=False)
    # Refresh panel
    cfg = get_product_free_config(pid); prod = get_product(pid)
    await _safe_edit(q, _admin_panel_text(pid, cfg, prod),
                     parse_mode="Markdown",
                     reply_markup=_admin_panel_kb(pid, cfg))


async def fcrf_setrefs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin for number of required refs."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("fcrf_setrefs_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return
    context.user_data["fcrf_step"] = "refs"
    context.user_data["fcrf_pid"] = pid
    cfg = get_product_free_config(pid)
    await _safe_edit(q,
        f"👥 *Required Referrals*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 Current: *{cfg.get('required_refs', 5)}*\n\n"
        f"📥 Send the new number (1-100):\n"
        f"_e.g._ `5`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "❌ Cancel", callback_data=f"fcrf_panel_{pid}")]]))


async def fcrf_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Router for text input — called from bot.py::handle_text()."""
    if update.effective_user.id != ADMIN_ID:
        return False
    step = context.user_data.get("fcrf_step")
    pid = context.user_data.get("fcrf_pid")
    if not step or not pid:
        return False
    text = (update.message.text or "").strip()

    if step == "refs":
        try:
            n = int(text)
            if n < 1 or n > 100:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Enter a number between 1 and 100.")
            return True
        set_product_free_config(pid, required_refs=n)
        context.user_data.pop("fcrf_step", None)
        context.user_data.pop("fcrf_pid", None)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            "🎁 Back to Free Claim Panel", callback_data=f"fcrf_panel_{pid}")]])
        await update.message.reply_text(
            f"✅ *Required Referrals saved:* `{n}`",
            parse_mode="Markdown", reply_markup=kb)
        return True

    if step == "custom":
        # 🆕 v48: capture text WITH premium emojis preserved
        captured = capture_user_text(update.message)
        # "/clear" wipes custom text → fallback to template
        if (text or "").lower() in ("/clear", "clear", "reset", "/reset"):
            set_product_free_config(pid, custom_text="")
            msg = "✅ Custom text cleared. Will use selected template."
            send_mode = "Markdown"
        else:
            set_product_free_config(pid, custom_text=captured)
            # 🆕 v48: echo with proper rendering (premium emojis visible, no [[HTML]] garbage)
            display, send_mode = safe_display(captured, preferred_mode="Markdown")
            if send_mode == "HTML":
                msg = (
                    "✅ <b>Custom broadcast text saved.</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{display}"
                )
            else:
                msg = (
                    "✅ *Custom broadcast text saved.*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"`{escape_md(captured)}`"
                )
        context.user_data.pop("fcrf_step", None)
        context.user_data.pop("fcrf_pid", None)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            "👁️ Preview", callback_data=f"fcrf_preview_{pid}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"fcrf_panel_{pid}")]])
        await update.message.reply_text(msg, parse_mode=send_mode, reply_markup=kb)
        return True

    return False


async def fcrf_tpllist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of 10 templates for selection. Paginated 5 per page."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        rest = q.data.replace("fcrf_tpllist_", "")
        pid_s, page_s = rest.rsplit("_", 1)
        pid = int(pid_s); page = int(page_s)
    except Exception:
        await _safe_edit(q, "❌ Bad data"); return

    per_page = 5
    total = len(FREE_CLAIM_TEMPLATES)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    end = min(start + per_page, total)

    cfg = get_product_free_config(pid)
    current_idx = int(cfg.get("tpl_index") if cfg.get("tpl_index") is not None else -1)

    kb = []
    # "Use Global Default" option at top of first page
    if page == 0:
        marker = "✅ " if current_idx < 0 else ""
        kb.append([InlineKeyboardButton(
            f"{marker}🌐 Use Global Default", callback_data=f"fcrf_pick_{pid}_-1")])

    for i in range(start, end):
        # Show 1st line of template as label
        first_line = FREE_CLAIM_TEMPLATES[i].split("\n", 1)[0][:40]
        marker = "✅ " if i == current_idx else ""
        kb.append([InlineKeyboardButton(
            f"{marker}#{i+1} {first_line}",
            callback_data=f"fcrf_pick_{pid}_{i}")])

    # Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"fcrf_tpllist_{pid}_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"fcrf_tpllist_{pid}_{page+1}"))
    if nav: kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 Back", callback_data=f"fcrf_panel_{pid}")])

    await _safe_edit(q,
        f"🎨 *Pick Broadcast Template*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Showing {start+1}-{end} of {total}.\n"
        f"_Tap any to set as broadcast template for this product._\n"
        f"_Currently:_ {'✏️ Custom' if (cfg.get('custom_text') or '').strip() else ('🌐 Global' if current_idx < 0 else f'#{current_idx+1}')}",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def fcrf_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save picked template index (-1 = use global)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        rest = q.data.replace("fcrf_pick_", "")
        pid_s, idx_s = rest.rsplit("_", 1)
        pid = int(pid_s); idx = int(idx_s)
    except Exception:
        await q.answer("❌ Bad data", show_alert=True); return

    # Setting a template clears any custom override so admin's pick wins
    set_product_free_config(pid, tpl_index=idx, custom_text="")
    await q.answer(f"✅ Template set: {'Global' if idx < 0 else f'#{idx+1}'}", show_alert=False)
    # Refresh panel
    cfg = get_product_free_config(pid); prod = get_product(pid)
    await _safe_edit(q, _admin_panel_text(pid, cfg, prod),
                     parse_mode="Markdown",
                     reply_markup=_admin_panel_kb(pid, cfg))


async def fcrf_custom_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin to type custom broadcast text."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("fcrf_custom_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return

    context.user_data["fcrf_step"] = "custom"
    context.user_data["fcrf_pid"] = pid

    cfg = get_product_free_config(pid)
    current = cfg.get("custom_text") or ""
    current_block = f"📌 *Current:*\n```\n{current}\n```\n\n" if current else ""

    await _safe_edit(q,
        f"✏️ *Set Custom Broadcast Text*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{current_block}"
        f"📥 Type your custom message.\n"
        f"_Use placeholders:_\n"
        f"  `{{user}}` — masked username\n"
        f"  `{{product}}` — product name\n"
        f"  `{{refs}}` — referrals used\n"
        f"  `{{shop}}` — shop name\n\n"
        f"_Send_ `/clear` _to remove custom text and use selected template instead._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "❌ Cancel", callback_data=f"fcrf_panel_{pid}")]]))


async def fcrf_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show what the broadcast will look like (without sending)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("fcrf_preview_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return
    prod = get_product(pid)
    if not prod:
        await _safe_edit(q, "❌ Product not found"); return
    cfg = get_product_free_config(pid)

    msg = build_free_claim_message(
        user_name=q.from_user.first_name or "You",
        product_name=prod["name"],
        refs_used=int(cfg.get("required_refs") or 5),
        tpl_index=int(cfg.get("tpl_index") if cfg.get("tpl_index") is not None else -1),
        custom_text=cfg.get("custom_text") or "",
        shop_name=SHOP_NAME,
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send Test to Destination", callback_data=f"fcrf_test_{pid}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"fcrf_panel_{pid}")],
    ])
    await _safe_edit(q,
        f"👁️ *Broadcast Preview*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{msg}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"_This is exactly what users will see (with a 🎁 Get Yours button)._",
        parse_mode="Markdown", reply_markup=kb)


async def fcrf_test_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Actually send the broadcast to the destination (as a test, no claim recorded)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("📤 Sending test...", show_alert=False)
    try:
        pid = int(q.data.replace("fcrf_test_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return
    prod = get_product(pid)
    if not prod:
        await _safe_edit(q, "❌ Product not found"); return
    cfg = get_product_free_config(pid)

    msg = build_free_claim_message(
        user_name=(q.from_user.first_name or "Tester") + " (TEST)",
        product_name=prod["name"],
        refs_used=int(cfg.get("required_refs") or 5),
        tpl_index=int(cfg.get("tpl_index") if cfg.get("tpl_index") is not None else -1),
        custom_text=cfg.get("custom_text") or "",
        shop_name=SHOP_NAME,
    )
    try:
        from fake_engagement import broadcast_store_message
        # 🆕 v49: prefer per-product button (fc_btn_<pid>) when admin has customized it
        custom_tpl = f"fc_btn_{pid}" if fc_btn_has_custom(pid) else None
        sent = await broadcast_store_message(
            context.bot, msg, pid=pid,
            tpl_id=custom_tpl,
            btn_key=(None if custom_tpl else "sb_buy_generic"))
        await context.bot.send_message(
            ADMIN_ID,
            f"✅ Test broadcast sent.\nDelivered to *{sent}* destination(s).",
            parse_mode="Markdown")
    except Exception as e:
        logger.exception("[fcrf_test] failed")
        await context.bot.send_message(ADMIN_ID, f"⚠️ Test failed: `{e}`", parse_mode="Markdown")


async def fcrf_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent free claims (admin only)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    rows = get_all_free_claims(limit=30)
    if not rows:
        text = "📜 *Recent Free Claims*\n━━━━━━━━━━━━━━━━━━━━\n\n_No free claims yet._"
    else:
        lines = ["📜 *Recent Free Claims*", "━━━━━━━━━━━━━━━━━━━━", ""]
        for r in rows:
            uname = escape_md(r.get("user_name") or "Unknown")
            pname = escape_md(r.get("product_name") or f"#{r['product_id']}")
            uid = r.get("user_id")
            refs = r.get("refs_used")
            at = (r.get("claimed_at") or "")[:16].replace("T", " ")
            lines.append(f"• *{pname}* — by {uname} (`{uid}`) | {refs} refs | _{at}_")
        text = "\n".join(lines)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


# ════════════════════════════════════════════════════════════════
# 👤 USER: Claim flow
# ════════════════════════════════════════════════════════════════

def _user_screen_text(user, prod, cfg, available_refs):
    pname = escape_md(prod["name"])
    required = int(cfg.get("required_refs") or 5)
    can_claim = available_refs >= required

    if has_user_claimed_free(user.id, prod["id"]):
        body = _r("freeclaim_already_claimed",
                  "✅ *You already claimed this product for free.*\n\n"
                  "Each user can claim a free product only once.")
        return f"🎁 *Free Claim — {pname}*\n━━━━━━━━━━━━━━━━━━━━\n\n{body}"

    if can_claim:
        msg = _r("freeclaim_user_screen",
                 "🎁 *Get this product FREE!*\n\n"
                 "📦 *{product}*\n"
                 "👥 Required Referrals: *{required}*\n"
                 "✅ Your Available Referrals: *{available}*\n\n"
                 "🎉 *You're eligible!* Tap *Claim Now* to receive your product instantly.")
    else:
        msg = _r("freeclaim_not_enough",
                 "🎁 *Get this product FREE!*\n\n"
                 "📦 *{product}*\n"
                 "👥 Required Referrals: *{required}*\n"
                 "📊 Your Available Referrals: *{available}*\n"
                 "📉 Need *{missing}* more referrals.\n\n"
                 "🔗 Share your referral link with friends — when they /start the bot, "
                 "your referral count goes up!")
    try:
        msg = msg.format(
            product=pname,
            required=required,
            available=available_refs,
            missing=max(0, required - available_refs),
        )
    except Exception:
        pass
    return msg


def _user_screen_kb(uid, prod, cfg, available_refs, bot_username):
    pid = prod["id"]
    required = int(cfg.get("required_refs") or 5)
    already = has_user_claimed_free(uid, pid)
    can_claim = (not already) and (available_refs >= required)

    kb = []
    if already:
        kb.append([InlineKeyboardButton("🛒 Buy Normally", callback_data=f"buy_{pid}")])
    elif can_claim:
        kb.append([InlineKeyboardButton(f"🎁 Claim NOW (uses {required} refs)",
                                        callback_data=f"freeclaim_do_{pid}")])
        # 🆕 v48: Always show smart share — invite friends to earn even more
        kb.append([InlineKeyboardButton("🔗 Share this Product Link",
                                        callback_data=f"freeclaim_share_{pid}")])
    else:
        # 🆕 v48: Smart share — product-specific deep link
        kb.append([InlineKeyboardButton("🔗 Share My Link & Earn Refs",
                                        callback_data=f"freeclaim_share_{pid}")])
        kb.append([InlineKeyboardButton("📊 My Referral Page", callback_data="referral")])
    kb.append([InlineKeyboardButton("🔙 Back to Product", callback_data=f"prod_{pid}")])
    return InlineKeyboardMarkup(kb)


async def freeclaim_open_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User taps '🎁 Get FREE' on product detail."""
    q = update.callback_query
    await q.answer()
    try:
        pid = int(q.data.replace("freeclaim_open_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return
    prod = get_product(pid)
    if not prod:
        await _safe_edit(q, "❌ Product not found."); return
    cfg = get_product_free_config(pid)
    if not cfg.get("enabled"):
        await _safe_edit(q, "ℹ️ This product is not available for free claim right now."); return

    uid = q.from_user.id
    # 🆕 v102: pick the higher of general points OR product-specific pool
    from database import count_product_refs
    available_points = count_eligible_unused_refs(uid)
    available_pool = count_product_refs(uid, pid)
    available = max(available_points, available_pool)
    user = q.from_user
    try:
        me = await context.bot.get_me()
        bot_username = me.username
    except Exception:
        bot_username = None

    await _safe_edit(q,
        _user_screen_text(user, prod, cfg, available),
        parse_mode="Markdown",
        reply_markup=_user_screen_kb(uid, prod, cfg, available, bot_username))


async def freeclaim_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User confirms claim → create order, deliver product, broadcast."""
    q = update.callback_query
    await q.answer()
    try:
        pid = int(q.data.replace("freeclaim_do_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return

    uid = q.from_user.id
    user_obj = q.from_user

    prod = get_product(pid)
    if not prod:
        await _safe_edit(q, "❌ Product not found."); return

    cfg = get_product_free_config(pid)
    if not cfg.get("enabled"):
        await _safe_edit(q, "ℹ️ Free claim is no longer enabled for this product.")
        return

    # Re-verify (defend against double-tap / stale UI)
    if has_user_claimed_free(uid, pid):
        await _safe_edit(q,
            "✅ You already claimed this product for free. Each user can claim only once.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "🔙 Back to Product", callback_data=f"prod_{pid}")]]))
        return

    required = int(cfg.get("required_refs") or 5)
    # 🆕 v102: dual-source eligibility — either general ref_points OR
    # per-product pool (whichever meets requirement). This preserves BOTH
    # behaviors: users can spend hoarded ref_points OR use product-specific
    # referrals they earned via ?start=ref_<uid>_<pid> share link.
    from database import count_product_refs
    available_points = count_eligible_unused_refs(uid)
    available_pool = count_product_refs(uid, pid)
    available = max(available_points, available_pool)
    # 🆕 v102: prefer draining the per-product pool first (doesn't cost points)
    _use_pool = available_pool >= required
    if available < required:
        await _safe_edit(q,
            f"❌ Not enough referrals.\n\n"
            f"Required: *{required}*\nYou have: *{available}*\n"
            f"(General points: {available_points} · Product-specific: {available_pool})\n"
            f"Need *{required - available}* more.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "🔗 Get Referral Link", callback_data="referral")],
                [InlineKeyboardButton("🔗 Get Product Share Link",
                                      callback_data=f"freeclaim_share_{pid}")],
                [InlineKeyboardButton("🔙 Back", callback_data=f"freeclaim_open_{pid}")]]))
        return

    # Stock check
    try:
        stock_val = int(prod["stock"] or 0)
    except Exception:
        stock_val = 0
    if stock_val <= 0:
        await _safe_edit(q,
            "😔 This product is out of stock right now. Please try later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "🔙 Back", callback_data=f"prod_{pid}")]]))
        return

    # ── Create FREE order ──
    uname = user_obj.username or user_obj.first_name or ""
    try:
        oid = create_order(
            uid, uname, pid, prod["name"], 0.0,
            method="free_referral", bname="", bamt=0, bcur="REF",
            otype="product", creds="",
        )
    except Exception as e:
        logger.exception("[freeclaim] create_order failed")
        await _safe_edit(q, f"⚠️ Could not create order: `{e}`",
                         parse_mode="Markdown")
        return

    # Mark as paid for fulfillment router
    try:
        update_order_status(oid, "paid")
    except Exception:
        pass

    # 🆕 v102: two paths — pool-first (free from product share link) OR points
    if _use_pool:
        from database import clear_product_refs
        clear_product_refs(uid, pid)   # zero out the product-specific counter
        deducted = True
    else:
        # 🆕 v48: DEDUCT ref_points (this is the actual currency)
        deducted = deduct_ref_points(uid, required)
    if not deducted:
        # Shouldn't happen (we checked above) but defend
        await _safe_edit(q, "⚠️ Balance changed — please try again.")
        return

    # Record claim (BEFORE fulfillment to prevent re-claim race conditions)
    try:
        record_free_claim(uid, pid, oid, required)
    except Exception as e:
        logger.exception("[freeclaim] record_free_claim failed")

    # Notify admin
    try:
        await notify_admin(context.bot,
            f"🎁 *FREE CLAIM!*\n"
            f"👤 {escape_md(user_obj.first_name or '')} (`{uid}`)\n"
            f"📦 *{escape_md(prod['name'])}*\n"
            f"👥 Refs used: *{required}*\n"
            f"🧾 Order: `#{oid}`")
    except Exception:
        pass

    # ── Deliver via central fulfillment router ──
    try:
        from handlers_order import fulfill_paid_product_order
        order = get_order(oid)
        await fulfill_paid_product_order(
            context.bot, order, paid_amount=0.0,
            payment_method_label="🎁 FREE (Referrals)",
            award_bonus=False,
        )
    except Exception as e:
        logger.exception("[freeclaim] fulfill failed")
        await context.bot.send_message(uid,
            "⚠️ Delivery hiccup — admin will deliver manually.")
        try:
            await notify_admin(context.bot,
                f"⚠️ Free claim delivery failed for order `#{oid}`: `{e}`")
        except Exception:
            pass

    # ── Broadcast to destination ──
    try:
        msg = build_free_claim_message(
            user_name=user_obj.first_name or user_obj.username or "Someone",
            product_name=prod["name"],
            refs_used=required,
            tpl_index=int(cfg.get("tpl_index") if cfg.get("tpl_index") is not None else -1),
            custom_text=cfg.get("custom_text") or "",
            shop_name=SHOP_NAME,
        )
        from fake_engagement import broadcast_store_message
        # 🆕 v49: prefer per-product button when admin has customized it
        custom_tpl = f"fc_btn_{pid}" if fc_btn_has_custom(pid) else None
        await broadcast_store_message(
            context.bot, msg, pid=pid,
            tpl_id=custom_tpl,
            btn_key=(None if custom_tpl else "sb_buy_generic"))
    except Exception:
        logger.exception("[freeclaim] broadcast failed")

    # ── Confirmation in current chat ──
    confirm = _r("freeclaim_success",
                 "🎉 *Claim Successful!*\n\n"
                 "📦 *{product}*\n"
                 "👥 Referrals spent: *{refs}*\n\n"
                 "✅ Your product has been delivered above.\n"
                 "💡 Keep referring to claim more free products!")
    try:
        confirm = confirm.format(product=escape_md(prod["name"]), refs=required)
    except Exception:
        pass
    try:
        await context.bot.send_message(uid, confirm, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛍️ Shop More", callback_data="shop")],
                [InlineKeyboardButton("🔗 My Referral Page", callback_data="referral")],
            ]))
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# Helper used by keyboards.py — "🎁 Get FREE (X refs)" button on product detail
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
# 🆕 v48: Smart Product-Specific Share Link Screen
# ════════════════════════════════════════════════════════════════

from urllib.parse import quote_plus


async def freeclaim_share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User taps '🔗 Share this product link' inside Free Claim screen.

    Generates a product-specific deep link: t.me/<bot>?start=ref_<uid>_<pid>
    Shows pre-filled share message + share buttons (WA, FB, TG, X).
    """
    q = update.callback_query
    await q.answer()
    try:
        pid = int(q.data.replace("freeclaim_share_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return
    prod = get_product(pid)
    if not prod:
        await _safe_edit(q, "❌ Product not found."); return

    uid = q.from_user.id
    try:
        me = await context.bot.get_me()
        bot_username = me.username
    except Exception:
        bot_username = "your_bot"
    link = f"https://t.me/{bot_username}?start=ref_{uid}_{pid}"

    # Pre-filled share message (editable from Edit Responses)
    pname_display = prod["name"]
    # Strip [[HTML]] for cleaner share text — premium emojis won't render outside Telegram anyway
    try:
        from utils import html_strip_tags, is_html_value
        pname_clean = html_strip_tags(pname_display) if is_html_value(pname_display) else pname_display
    except Exception:
        pname_clean = pname_display

    share_tpl = _r("freeclaim_share_message",
        "🎁 I'm getting {product} for FREE on {shop}!\n\n"
        "Want one too? Super easy:\n"
        "1️⃣ Click my link\n"
        "2️⃣ Open the bot in Telegram\n"
        "3️⃣ Tap Start — and you're in!\n\n"
        "👇 My link:\n{link}")
    try:
        share_text = share_tpl.format(product=pname_clean, shop=SHOP_NAME, link=link)
    except Exception:
        share_text = share_tpl + f"\n{link}"

    # URL-encoded versions for share buttons
    enc_full = quote_plus(share_text)
    enc_link = quote_plus(link)
    enc_text_only = quote_plus(share_text.replace(link, "").strip())

    kb = InlineKeyboardMarkup([
        # Row 1: Telegram + WhatsApp
        [InlineKeyboardButton("📤 Share on Telegram",
                              url=f"https://t.me/share/url?url={enc_link}&text={enc_text_only}"),
         InlineKeyboardButton("💬 WhatsApp",
                              url=f"https://wa.me/?text={enc_full}")],
        # Row 2: Facebook + Twitter/X
        [InlineKeyboardButton("📘 Facebook",
                              url=f"https://www.facebook.com/sharer/sharer.php?u={enc_link}"),
         InlineKeyboardButton("🐦 Twitter / X",
                              url=f"https://twitter.com/intent/tweet?text={enc_text_only}&url={enc_link}")],
        # Row 3: Copy via clipboard helper (Telegram doesn't have native copy btn, so we show the link big)
        [InlineKeyboardButton("🔙 Back to Free Claim", callback_data=f"freeclaim_open_{pid}")],
    ])

    # Build screen text — show link in code block so user can long-press → copy
    screen_tpl = _r("freeclaim_share_screen",
        "🔗 *Your Share Link for this Product*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📦 *{product}*\n"
        "🎁 Need: *{required}* referrals\n"
        "📊 You have: *{available}*\n\n"
        "🔗 *Tap below to copy your unique link:*\n"
        "`{link}`\n\n"
        "📲 *Use the buttons below to share on any platform.*\n"
        "_When someone clicks your link and signs up, you instantly get *1 referral point*!_\n\n"
        "📝 *Preview of share message:*\n"
        "```\n{preview}\n```")
    cfg = get_product_free_config(pid)
    required = int(cfg.get("required_refs") or 5)
    available = count_eligible_unused_refs(uid)
    try:
        screen_text = screen_tpl.format(
            product=escape_md(pname_clean),
            required=required, available=available,
            link=link,
            preview=share_text[:300]
        )
    except Exception:
        screen_text = (
            f"🔗 *Your Share Link*\n\n"
            f"`{link}`\n\n"
            f"Tap a button below to share."
        )
    await _safe_edit(q, screen_text, parse_mode="Markdown", reply_markup=kb)


# Helper used by keyboards.py — "🎁 Get FREE (X refs)" button on product detail
# ════════════════════════════════════════════════════════════════

def get_free_claim_button(product, user_id):
    """If this product has free claim enabled and the user hasn't claimed,
    return an InlineKeyboardButton; else None.

    Used by keyboards.product_detail_keyboard() to inject the button.
    """
    try:
        pid = product["id"]
    except Exception:
        return None
    try:
        cfg = get_product_free_config(pid)
    except Exception:
        return None
    if not cfg.get("enabled"):
        return None
    if has_user_claimed_free(user_id, pid):
        return None
    required = int(cfg.get("required_refs") or 5)
    available = count_eligible_unused_refs(user_id)
    if available >= required:
        label = f"🎁 Claim FREE ({required} refs ✅)"
    else:
        label = f"🎁 Get FREE — need {required - available} more refs"
    return InlineKeyboardButton(label, callback_data=f"freeclaim_open_{pid}")


# ════════════════════════════════════════════════════════════════
# 🎨 v49: PER-PRODUCT BROADCAST BUTTON EDITOR
# ════════════════════════════════════════════════════════════════
# Lets admin customize the "🛒 Buy Now" button that goes with the free-claim
# broadcast announcement, for EACH product separately.
#
# Reuses existing infrastructure (zero reinvention):
#   - template_buttons.{get_button_text, get_button_emoji_id, set_button,
#                       reset_button, extract_custom_emoji, build_button}
#       for text + premium-emoji-icon
#   - button_styler.{get_style, set_style, reset_style, style_label}
#       for size / alignment / padding
#   - button_registry.{get_button_style, set_button_style}
#       for Telegram Premium background color
#
# Per-product key naming convention:
#   "fc_btn_<pid>"   e.g. fc_btn_5
#
# When this key has saved text/icon, store_broadcast._buy_now_keyboard()
# automatically prefers it over the default sb_generic.
# ════════════════════════════════════════════════════════════════

VALID_COLORS = ("", "primary", "success", "danger")


def _fcb_key(pid):
    """Return the persistent key used by template_buttons / button_styler /
    button_registry for this product's broadcast button."""
    return f"fc_btn_{int(pid)}"


def fc_btn_has_custom(pid):
    """True if admin has saved ANY customization for this product's button."""
    try:
        from button_system import get_button_text, get_button_emoji_id
        from button_system import is_styled
        from button_system import get_button_style
        k = _fcb_key(pid)
        if get_button_text(k, "") or get_button_emoji_id(k):
            return True
        if is_styled(k):
            return True
        if get_button_style(k):
            return True
        return False
    except Exception:
        return False


def _fcb_panel_text(pid, prod):
    """Build the editor panel text + current settings summary."""
    from button_system import get_button_text, get_button_emoji_id
    from button_system import get_style
    from button_system import get_button_style

    k = _fcb_key(pid)
    text   = get_button_text(k, "") or "🛒 Buy Now"
    emoji  = get_button_emoji_id(k) or ""
    style  = get_style(k)
    color  = get_button_style(k) or "none"

    pname  = escape_md(prod["name"]) if prod else f"#{pid}"

    emoji_disp = f"`{emoji}`" if emoji else "_none_"
    color_label = {
        "": "⬜ Default",
        "primary": "🔵 Primary (blue)",
        "success": "🟢 Success (green)",
        "danger":  "🔴 Danger (red)",
    }.get(color if color != "none" else "", "⬜ Default")

    return (
        f"🎨 *Broadcast Button Editor*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Product: *{pname}*\n\n"
        f"🔤 *Text:* `{text}`\n"
        f"⭐ *Premium Emoji Icon:* {emoji_disp}\n"
        f"📏 *Size:* `{style['size']}`\n"
        f"↔️ *Alignment:* `{style['align']}`\n"
        f"📐 *Padding:* `{style['pad']}`\n"
        f"🎨 *Background:* {color_label}\n\n"
        f"_This button appears below the broadcast announcement when\n"
        f"someone claims this product for free. Tap any option to edit._"
    )


def _fcb_panel_kb(pid):
    """Build the editor panel keyboard."""
    k = _fcb_key(pid)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Text",        callback_data=f"fcb_settext_{pid}"),
         InlineKeyboardButton("⭐ Set Premium Icon", callback_data=f"fcb_setemoji_{pid}")],
        [InlineKeyboardButton("📏 Size / Alignment / Padding",
                              callback_data=f"fcb_styler_{pid}")],
        [InlineKeyboardButton("🎨 Background Color", callback_data=f"fcb_color_{pid}")],
        [InlineKeyboardButton("👁️ Preview",        callback_data=f"fcb_preview_{pid}"),
         InlineKeyboardButton("📤 Send Test",      callback_data=f"fcrf_test_{pid}")],
        [InlineKeyboardButton("♻️ Reset to Default", callback_data=f"fcb_reset_{pid}")],
        [InlineKeyboardButton("🔙 Back to Free Claim", callback_data=f"fcrf_panel_{pid}")],
    ])


async def fcb_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the broadcast-button editor for a specific product.
    🆕 v55: Also acts as a cancel target — cleans up fcb_step/fcb_pid so a
    pending text-input flow doesn't capture admin's next unrelated message."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    # 🆕 v55: cancel any in-progress text-input flow
    context.user_data.pop("fcb_step", None)
    context.user_data.pop("fcb_pid", None)
    try:
        pid = int(q.data.replace("fcb_panel_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return
    prod = get_product(pid)
    if not prod:
        await _safe_edit(q, "❌ Product not found"); return
    await _safe_edit(q, _fcb_panel_text(pid, prod),
                     parse_mode="Markdown",
                     reply_markup=_fcb_panel_kb(pid))


async def fcb_settext_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin for new button text."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("fcb_settext_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return
    context.user_data["fcb_step"] = "text"
    context.user_data["fcb_pid"] = pid
    from button_system import get_button_text
    k = _fcb_key(pid)
    current = get_button_text(k, "") or "🛒 Buy Now"
    await _safe_edit(q,
        f"✏️ *Edit Button Text*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *Current:* `{current}`\n\n"
        f"📥 Type the new button text:\n"
        f"_e.g._ `🎁 Get Yours Now`\n\n"
        f"💡 *Tip:* You can include standard emojis (🎁 🛒 ⚡ etc.)\n"
        f"_Premium emojis go in the separate ⭐ Premium Icon option._\n\n"
        f"_Send_ `/clear` _to reset to default ('🛒 Buy Now')._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "❌ Cancel", callback_data=f"fcb_panel_{pid}")]]))


async def fcb_setemoji_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin to send a message starting with a premium emoji."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("fcb_setemoji_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return
    context.user_data["fcb_step"] = "emoji"
    context.user_data["fcb_pid"] = pid
    from button_system import get_button_emoji_id
    k = _fcb_key(pid)
    current = get_button_emoji_id(k) or ""
    cur_disp = f"`{current}`" if current else "_none set_"
    await _safe_edit(q,
        f"⭐ *Set Premium Emoji Icon*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *Current ID:* {cur_disp}\n\n"
        f"📥 *Send a message starting with the premium emoji you want.*\n\n"
        f"💡 *How:*\n"
        f"1. Open Telegram's emoji picker (😀 button)\n"
        f"2. Switch to your *Premium Emoji* pack (star icon at top)\n"
        f"3. Tap any premium emoji\n"
        f"4. Send the message (any text after the emoji is ignored)\n\n"
        f"_Bot will detect the `custom_emoji_id` and use it as the button icon._\n\n"
        f"_Send_ `/clear` _to remove the premium icon._\n"
        f"_(Requires your bot owner to have Telegram Premium.)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "❌ Cancel", callback_data=f"fcb_panel_{pid}")]]))


async def fcb_styler_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the existing button_styler editor for the fc_btn_<pid> key."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("fcb_styler_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return
    k = _fcb_key(pid)
    # Hand off to the existing styler — it knows how to render size/align/pad
    try:
        from handlers_buttons import _show_editor
        # Remember where to return after styler "Back" is tapped
        context.user_data["bs_return_cb"] = f"fcb_panel_{pid}"
        await _show_editor(q, k, context)
    except Exception as e:
        logger.exception("[fcb] styler open failed")
        await _safe_edit(q, f"⚠️ Could not open styler: `{e}`",
                         parse_mode="Markdown")


async def fcb_color_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show a color picker for the button background."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("fcb_color_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return
    k = _fcb_key(pid)
    from button_system import get_button_style
    cur = get_button_style(k) or ""

    def _opt(label, val):
        marker = "✅ " if cur == val else ""
        return InlineKeyboardButton(f"{marker}{label}", callback_data=f"fcb_pickcolor_{pid}_{val or 'none'}")

    kb = InlineKeyboardMarkup([
        [_opt("⬜ Default", ""),
         _opt("🔵 Primary",  "primary")],
        [_opt("🟢 Success",  "success"),
         _opt("🔴 Danger",   "danger")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"fcb_panel_{pid}")],
    ])
    await _safe_edit(q,
        "🎨 *Background Color*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Pick a Telegram Premium button background:\n\n"
        "  • *Default* — normal button look (works for everyone)\n"
        "  • *Primary*  🔵 — blue tint (Premium clients)\n"
        "  • *Success*  🟢 — green tint (Premium clients)\n"
        "  • *Danger*   🔴 — red tint (Premium clients)\n\n"
        "_Non-Premium clients see the default look — no breakage._",
        parse_mode="Markdown", reply_markup=kb)


async def fcb_pickcolor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the selected color."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        rest = q.data.replace("fcb_pickcolor_", "")
        pid_s, color = rest.rsplit("_", 1)
        pid = int(pid_s)
    except Exception:
        await q.answer("❌ Bad data", show_alert=True); return
    if color == "none":
        color = ""
    if color not in VALID_COLORS:
        await q.answer("❌ Unknown color", show_alert=True); return
    k = _fcb_key(pid)
    try:
        from button_system import set_button_style
        set_button_style(k, color)
    except Exception as e:
        await q.answer(f"⚠️ {e}", show_alert=True); return
    await q.answer(f"✅ Color set: {color or 'default'}", show_alert=False)
    # Refresh panel
    prod = get_product(pid)
    await _safe_edit(q, _fcb_panel_text(pid, prod),
                     parse_mode="Markdown",
                     reply_markup=_fcb_panel_kb(pid))


async def fcb_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Render the actual button + a sample broadcast message for preview."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("📤 Building preview...", show_alert=False)
    try:
        pid = int(q.data.replace("fcb_preview_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id"); return
    prod = get_product(pid)
    if not prod:
        await _safe_edit(q, "❌ Product not found"); return

    # Build the actual button using same path as production broadcast
    try:
        from button_system import build_button as _bb
        from button_system import wrap_button as _wrap
        k = _fcb_key(pid)
        btn = _bb(k, "🛒 Buy Now", callback_data=f"buy_{pid}")
        # Apply per-key size/align/pad styler
        btn = _wrap(k, btn)
    except Exception as e:
        await _safe_edit(q, f"⚠️ Preview failed: `{e}`", parse_mode="Markdown"); return

    # Build sample message similar to a real claim
    cfg = get_product_free_config(pid)
    sample = build_free_claim_message(
        user_name="Preview",
        product_name=prod["name"],
        refs_used=int(cfg.get("required_refs") or 5),
        tpl_index=int(cfg.get("tpl_index") if cfg.get("tpl_index") is not None else -1),
        custom_text=cfg.get("custom_text") or "",
        shop_name=SHOP_NAME,
    )

    sent_text, sent_mode = smart_text_and_mode(sample, "Markdown")
    kb = InlineKeyboardMarkup([
        [btn],
        [InlineKeyboardButton("🔙 Back to Button Editor", callback_data=f"fcb_panel_{pid}")],
    ])
    # Send as NEW message so admin sees the live button (edit_message_text can't
    # always show the styler effects when message has reply_markup updates)
    try:
        await context.bot.send_message(ADMIN_ID,
            f"👁️ *Live Preview:*\n━━━━━━━━━━━━━━━━━━━━\n\n{sent_text}",
            parse_mode=sent_mode, reply_markup=kb)
    except Exception as e:
        await _safe_edit(q, f"⚠️ Could not send preview: `{e}`", parse_mode="Markdown")


async def fcb_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset ALL customizations for this product's button."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        pid = int(q.data.replace("fcb_reset_", ""))
    except Exception:
        await q.answer("❌ Bad id", show_alert=True); return
    k = _fcb_key(pid)
    try:
        from button_system import reset_button as _reset_tb
        from button_system import reset_style as _reset_bs
        from button_system import set_button_style as _reset_bg
        _reset_tb(k)      # text + emoji
        _reset_bs(k)      # size/align/pad
        _reset_bg(k, "")  # color
    except Exception as e:
        await q.answer(f"⚠️ {e}", show_alert=True); return
    await q.answer("♻️ Reset complete", show_alert=False)
    prod = get_product(pid)
    await _safe_edit(q, _fcb_panel_text(pid, prod),
                     parse_mode="Markdown",
                     reply_markup=_fcb_panel_kb(pid))


async def fcb_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Router for text/emoji input. Called from bot.py::handle_text."""
    if update.effective_user.id != ADMIN_ID:
        return False
    step = context.user_data.get("fcb_step")
    pid = context.user_data.get("fcb_pid")
    if not step or not pid:
        return False

    raw = (update.message.text or "").strip()
    k = _fcb_key(pid)

    kb_back = InlineKeyboardMarkup([[InlineKeyboardButton(
        "🔙 Button Editor", callback_data=f"fcb_panel_{pid}")]])

    # ── Text edit ──
    if step == "text":
        from button_system import (
            set_button as _set_btn, get_button_emoji_id as _get_em
        )
        if raw.lower() in ("/clear", "clear", "reset", "/reset"):
            # Preserve existing emoji if any — only clear text
            _set_btn(k, "", _get_em(k))
            msg = "✅ Button text cleared. Will use default '🛒 Buy Now'."
        else:
            # Preserve existing emoji
            _set_btn(k, raw, _get_em(k))
            msg = f"✅ *Button text saved:* `{escape_md(raw)}`"
        context.user_data.pop("fcb_step", None)
        context.user_data.pop("fcb_pid", None)
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb_back)
        return True

    # ── Premium emoji icon edit ──
    if step == "emoji":
        from button_system import (
            extract_custom_emoji as _xc,
            set_button as _set_btn, get_button_text as _get_text,
        )
        if raw.lower() in ("/clear", "clear", "reset", "/reset"):
            _set_btn(k, _get_text(k, ""), "")
            msg = "✅ Premium emoji icon cleared."
            context.user_data.pop("fcb_step", None)
            context.user_data.pop("fcb_pid", None)
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb_back)
            return True

        emoji_id, _stripped = _xc(update.message)
        if not emoji_id:
            await update.message.reply_text(
                "⚠️ *No premium emoji detected.*\n\n"
                "Tap your phone's emoji picker → open your *Premium emoji pack* "
                "→ tap a premium emoji → send the message.\n\n"
                "Try again, or send /clear to cancel.",
                parse_mode="Markdown")
            # keep step active for retry
            return True
        # Preserve existing text
        _set_btn(k, _get_text(k, ""), emoji_id)
        context.user_data.pop("fcb_step", None)
        context.user_data.pop("fcb_pid", None)
        await update.message.reply_text(
            f"✅ *Premium emoji saved!*\n\n"
            f"🆔 ID: `{emoji_id}`\n\n"
            f"Tap *👁️ Preview* to see how the button looks.",
            parse_mode="Markdown", reply_markup=kb_back)
        return True

    return False


# ════════════════════════════════════════════════════════════════
# Hook to expose the new "🎨 Edit Broadcast Button" option in the existing
# Free Claim admin panel. We don't want to touch _admin_panel_kb every time
# we add a feature — instead we patch it once here.
# ════════════════════════════════════════════════════════════════
_orig_admin_panel_kb = _admin_panel_kb  # snapshot the v47 keyboard builder


def _admin_panel_kb(pid, cfg):  # noqa: F811 — intentional override
    """Wrapped version of v47's _admin_panel_kb that adds the v49 button-editor row."""
    base = _orig_admin_panel_kb(pid, cfg)
    rows = list(base.inline_keyboard)
    # Find the "Recent Claims" row to insert above it (keeps Back as last)
    new_row = [InlineKeyboardButton("🎨 Edit Broadcast Button",
                                    callback_data=f"fcb_panel_{pid}")]
    insert_at = None
    for i, row in enumerate(rows):
        for b in row:
            if (getattr(b, "callback_data", "") or "").startswith("fcrf_history"):
                insert_at = i; break
        if insert_at is not None:
            break
    if insert_at is None:
        # Fallback: insert just before the last (Back) row
        insert_at = max(0, len(rows) - 1)
    rows.insert(insert_at, new_row)
    return InlineKeyboardMarkup(rows)

