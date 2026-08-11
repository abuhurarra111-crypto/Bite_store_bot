# ============================================================
# 🧩 v77 BUNDLE: customization.py
# ============================================================
# This file is the merged result of 3 originally separate modules:
#   • handlers_customizer.py
#   • handlers_screen_editor.py
#   • screen_tree.py
#
# 🛡️ ALL CODE IS PRESERVED VERBATIM. Each original file's contents appears
# below in its own section. Imports and behavior are byte-identical to the
# pre-merge codebase — only file count is reduced.
# ============================================================


# ============================================================
# 📄 ORIGINAL FILE: handlers_customizer.py
# ============================================================

# ================================================================
# 🎨 FULL CUSTOMIZER — handlers_customizer.py
# ================================================================
#
# TWO SYSTEMS IN ONE FILE:
#
# 1. 📍 LOCATION CUSTOMIZER
#    Admin Panel → 🎨 Customization → 📍 Location Styles
#    Customize how EVERY screen/location looks:
#      - Main Menu, Shop, Account, Orders, Support, Payment, etc.
#      - Change header text, emoji, separator style
#      - Toggle which info fields show
#      - Change button arrangement (1-col / 2-col / 3-col)
#      - Live preview on screen
#
# 2. 📝 TEMPLATE EDITOR
#    Admin Panel → 📢 Fake Broadcast → 📝 Edit Templates
#    Admin Panel → ⭐ Fake Reviews   → 📝 Edit Templates
#    Change the exact text format of every fake message type:
#      - Purchase, Deposit, Referral, Tier, Discount, Stock Alert
#      - Urdu review template
#      - English review template
#    Available variables shown for each template.
#    Live preview with sample data.
#    Reset individual templates to default.
#
# ================================================================
# HOW TO REGISTER IN bot.py (add these):
# ================================================================
#
#   from handlers_customizer import (
#       location_customizer_panel_callback,
#       lc_pick_location_callback,
#       lc_set_header_callback,
#       lc_header_received,
#       lc_set_cols_callback,
#       lc_reset_callback,
#       template_editor_panel_callback,
#       tpl_pick_callback,
#       tpl_edit_callback,
#       tpl_text_received,
#       tpl_reset_callback,
#       tpl_preview_callback,
#       LC_HEADER, TPL_TEXT,
#   )
#
#   # ConversationHandlers:
#   app.add_handler(ConversationHandler(
#       entry_points=[CallbackQueryHandler(lc_set_header_callback, pattern="^lc_header_")],
#       states={LC_HEADER: [MessageHandler(filters.TEXT & ~filters.COMMAND, lc_header_received)]},
#       fallbacks=[CommandHandler("cancel", cancel_conversation)],
#   ))
#   app.add_handler(ConversationHandler(
#       entry_points=[CallbackQueryHandler(tpl_edit_callback, pattern="^tpl_edit_")],
#       states={TPL_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tpl_text_received)]},
#       fallbacks=[CommandHandler("cancel", cancel_conversation)],
#   ))
#
#   # Callback handlers:
#   app.add_handler(CallbackQueryHandler(location_customizer_panel_callback, pattern="^lc_panel$"))
#   app.add_handler(CallbackQueryHandler(lc_pick_location_callback,          pattern="^lc_loc_"))
#   app.add_handler(CallbackQueryHandler(lc_set_cols_callback,               pattern="^lc_cols_"))
#   app.add_handler(CallbackQueryHandler(lc_reset_callback,                  pattern="^lc_reset_"))
#   app.add_handler(CallbackQueryHandler(template_editor_panel_callback,     pattern="^tpl_panel$"))
#   app.add_handler(CallbackQueryHandler(tpl_pick_callback,                  pattern="^tpl_pick_"))
#   app.add_handler(CallbackQueryHandler(tpl_reset_callback,                 pattern="^tpl_reset_"))
#   app.add_handler(CallbackQueryHandler(tpl_preview_callback,               pattern="^tpl_preview_"))
#
# ADD BUTTONS:
#   In keyboards.py → admin_menu_keyboard():
#     kb.append([InlineKeyboardButton("📍 Location Styles", callback_data="lc_panel")])
#     kb.append([InlineKeyboardButton("📝 Message Templates", callback_data="tpl_panel")])
#
# ================================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
from utils import smart_text_and_mode

logger = logging.getLogger(__name__)

LC_HEADER = 801   # ConversationHandler state for header input
TPL_TEXT  = 802   # ConversationHandler state for template text input
SB_CUSTOM_TEXT = 803  # state for Flash/New-Product custom template input


# ════════════════════════════════════════════════════════════════
# 🔧 HELPERS
# ════════════════════════════════════════════════════════════════

def _is_admin(uid):
    from config import ADMIN_ID
    return uid == ADMIN_ID

def _g(key, default=""):
    try:
        from database import get_setting
        return get_setting(key, default)
    except Exception:
        return default

def _s(key, val):
    try:
        from database import set_setting
        set_setting(key, str(val))
    except Exception:
        pass

async def _edit(q, text, keyboard):
    rm = InlineKeyboardMarkup(keyboard)
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    try:
        await q.edit_message_text(send_text, parse_mode=send_mode, reply_markup=rm)
        return
    except Exception:
        pass
    # 🔧 BUG FIX: Markdown/HTML could fail, so fall back cleanly.
    try:
        await q.edit_message_caption(caption=send_text, parse_mode=send_mode, reply_markup=rm)
        return
    except Exception:
        pass
    try:
        await q.edit_message_text(send_text, reply_markup=rm)  # plain text
        return
    except Exception:
        pass
    try:
        await q.edit_message_caption(caption=send_text, reply_markup=rm)  # plain caption
        return
    except Exception:
        pass
    try:
        await q.message.reply_text(send_text, reply_markup=rm)  # last resort: new message
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
#  PART 1 — 📍 LOCATION CUSTOMIZER
# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════

# All locations that can be customized
LOCATIONS = [
    {"id": "main",       "name": "🏠 Main Menu",         "default_header": "🏠 *Main Menu*\n━━━━━━━━━━━━━━━━"},
    {"id": "shop",       "name": "🛍️ Shop",               "default_header": "🛍️ *Shop — Products*\n━━━━━━━━━━━━━━━━"},
    {"id": "account",    "name": "👤 My Account",         "default_header": "👤 *My Account*\n━━━━━━━━━━━━━━━━"},
    {"id": "orders",     "name": "📦 My Orders",          "default_header": "📦 *My Orders*\n━━━━━━━━━━━━━━━━"},
    {"id": "points",     "name": "💎 Buy Points",         "default_header": "💎 *Buy Points*\n━━━━━━━━━━━━━━━━"},
    {"id": "support",    "name": "🎫 Support",            "default_header": "🎫 *Support*\n━━━━━━━━━━━━━━━━"},
    {"id": "payment",    "name": "💳 Payment Screen",     "default_header": "💳 *Payment*\n━━━━━━━━━━━━━━━━"},
    {"id": "referral",   "name": "🎁 Referral",           "default_header": "🎁 *Referral Program*\n━━━━━━━━━━━━━━━━"},
    {"id": "loyalty",    "name": "🏆 Loyalty",            "default_header": "🏆 *Loyalty Program*\n━━━━━━━━━━━━━━━━"},
    {"id": "reviews",    "name": "⭐ Reviews",             "default_header": "⭐ *Reviews & Ratings*\n━━━━━━━━━━━━━━━━"},
    {"id": "warranty",   "name": "🛡️ Warranty",           "default_header": "🛡️ *Warranty / Refund*\n━━━━━━━━━━━━━━━━"},
    {"id": "language",   "name": "🌐 Language",           "default_header": "🌐 *Language Settings*\n━━━━━━━━━━━━━━━━"},
    {"id": "transactions","name": "📜 Transactions",      "default_header": "📜 *Transactions*\n━━━━━━━━━━━━━━━━"},
]

# Separator styles
SEPARATORS = {
    "line":    "━━━━━━━━━━━━━━━━",
    "dots":    "• • • • • • • •",
    "stars":   "✦ ✦ ✦ ✦ ✦ ✦ ✦",
    "dashes":  "────────────────",
    "arrows":  "› › › › › › › ›",
    "none":    "",
}


def _lc_key(loc_id, field):
    return f"lc_{loc_id}_{field}"

def get_location_header(loc_id):
    """Get the current custom header for a location, or return default."""
    default = next((l["default_header"] for l in LOCATIONS if l["id"] == loc_id), "")
    return _g(_lc_key(loc_id, "header"), default)

def get_location_cols(loc_id):
    """Get the button column count for a location. Default: 2."""
    try:
        return int(_g(_lc_key(loc_id, "cols"), "2"))
    except Exception:
        return 2

def get_location_sep(loc_id):
    """Get separator style for a location. Default: line."""
    return _g(_lc_key(loc_id, "sep"), "line")


# ── Main Panel ──

async def location_customizer_panel_callback(update, context):
    """
    Location Customizer — shows list of all customizable locations.
    Access: Admin Panel → 📍 Location Styles
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    text = (
        "📍 *Location Style Customizer*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Pick any screen to customize:\n"
        "• Header text & emoji\n"
        "• Separator line style\n"
        "• Button columns (1 / 2 / 3)\n\n"
        "_Changes apply immediately with live preview_"
    )

    keyboard = []
    row = []
    # 🐛 v95 FIX: use get_all_locations() so admin-added custom locations
    # (via ➕ Add Custom Location button below) appear here automatically.
    try:
        from custom_locations import get_all_locations
        _locs = get_all_locations()
    except Exception:
        _locs = LOCATIONS
    for i, loc in enumerate(_locs):
        row.append(InlineKeyboardButton(loc["name"], callback_data=f"lc_loc_{loc['id']}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # 🆕 v95: admin can add fresh custom locations that appear everywhere
    keyboard.append([InlineKeyboardButton("➕ Add Custom Location",
                                            callback_data="lc_add_custom")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")])
    await _edit(q, text, keyboard)


# ── Location Detail Panel ──

async def lc_pick_location_callback(update, context):
    """
    Show customization options for a specific location.
    Callback: lc_loc_{location_id}
    Includes live preview.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    loc_id = q.data.replace("lc_loc_", "")
    loc = next((l for l in LOCATIONS if l["id"] == loc_id), None)
    if not loc:
        await q.answer("❌ Unknown location", show_alert=True)
        return

    context.user_data["lc_current"] = loc_id
    await _show_location_panel(q, loc_id, loc)


async def _show_location_panel(q, loc_id, loc):
    """Build and display the location customization panel with live preview."""
    header  = get_location_header(loc_id)
    sep_key = get_location_sep(loc_id)
    cols    = get_location_cols(loc_id)
    sep_str = SEPARATORS.get(sep_key, "━━━━━━━━━━━━━━━━")

    # Live preview
    preview_lines = [header]
    if sep_str:
        preview_lines.append(sep_str)
    preview_lines.append("_[buttons appear here]_")
    preview = "\n".join(preview_lines)

    text = (
        f"📍 *{loc['name']} — Customization*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Current Settings:*\n"
        f"  🔤 Header: set\n"
        f"  ─ Separator: `{sep_key}`\n"
        f"  📐 Columns: `{cols}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👁️ *LIVE PREVIEW:*\n\n"
        f"{preview}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = [
        [InlineKeyboardButton("✏️ Edit Header Text", callback_data=f"lc_header_{loc_id}")],
        [InlineKeyboardButton("━━━ Separator Style ━━━", callback_data="lc_noop")],
        [
            InlineKeyboardButton(f"{'✅' if sep_key=='line'   else '▫️'} ━━━ Line",   callback_data=f"lc_sep_{loc_id}_line"),
            InlineKeyboardButton(f"{'✅' if sep_key=='dots'   else '▫️'} • • • Dots",  callback_data=f"lc_sep_{loc_id}_dots"),
        ],
        [
            InlineKeyboardButton(f"{'✅' if sep_key=='stars'  else '▫️'} ✦ Stars",    callback_data=f"lc_sep_{loc_id}_stars"),
            InlineKeyboardButton(f"{'✅' if sep_key=='dashes' else '▫️'} ─── Dashes", callback_data=f"lc_sep_{loc_id}_dashes"),
        ],
        [
            InlineKeyboardButton(f"{'✅' if sep_key=='arrows' else '▫️'} › Arrows",   callback_data=f"lc_sep_{loc_id}_arrows"),
            InlineKeyboardButton(f"{'✅' if sep_key=='none'   else '▫️'} None",        callback_data=f"lc_sep_{loc_id}_none"),
        ],
        [InlineKeyboardButton("━━━ Button Columns ━━━", callback_data="lc_noop")],
        [
            InlineKeyboardButton(f"{'✅' if cols==1 else '▫️'} 1 Column",  callback_data=f"lc_cols_{loc_id}_1"),
            InlineKeyboardButton(f"{'✅' if cols==2 else '▫️'} 2 Columns", callback_data=f"lc_cols_{loc_id}_2"),
            InlineKeyboardButton(f"{'✅' if cols==3 else '▫️'} 3 Columns", callback_data=f"lc_cols_{loc_id}_3"),
        ],
        [
            InlineKeyboardButton("🔄 Reset This Location", callback_data=f"lc_reset_{loc_id}"),
            InlineKeyboardButton("🔙 Back",                callback_data="lc_panel"),
        ],
    ]
    await _edit(q, text, keyboard)


# ── Header Edit ──

async def lc_set_header_callback(update, context):
    """Ask admin to type a new header for the location."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()

    loc_id = q.data.replace("lc_header_", "")
    context.user_data["lc_edit_loc"] = loc_id
    current = get_location_header(loc_id)

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=f"lc_loc_{loc_id}")]]
    text = (
        f"✏️ *Edit Header — {loc_id.title()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Current header:*\n{current}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Type the new header text.\n\n"
        f"*Tips:*\n"
        f"• Use *bold* with `*text*`\n"
        f"• Use _italic_ with `_text_`\n"
        f"• Add emojis freely 🎯\n"
        f"• Use `\\n` for new line or just press Enter\n\n"
        f"*Examples:*\n"
        f"`🛍️ *Welcome to BITE STORE!*`\n"
        f"`🏠 *Main Menu*\n━━━━━━━━━━━━━━━━`"
    )
    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        pass
    return LC_HEADER


async def lc_header_received(update, context):
    """Save the new header text."""
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    loc_id = context.user_data.get("lc_edit_loc")
    if not loc_id:
        return ConversationHandler.END

    new_header = update.message.text.strip()
    try:
        html_v = (update.message.text_html_urled or "").strip()
    except Exception:
        html_v = ""
    # 🆕 v55: Use has_premium_emoji (not raw entities) so bold/italic/link
    # entities don't trigger [[HTML]] save → avoids &amp;amp; double-escape bug.
    from utils import has_premium_emoji
    if html_v and has_premium_emoji(update.message):
        new_header = "[[HTML]]" + html_v
    _s(_lc_key(loc_id, "header"), new_header)

    keyboard = [[InlineKeyboardButton("🔙 Back to Location Settings",
                                      callback_data=f"lc_loc_{loc_id}")]]
    await update.message.reply_text(
        f"✅ *Header Updated!*\n\n{new_header}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


# ── Separator ──

async def lc_set_sep_callback(update, context):
    """
    Set separator style for a location.
    Callback: lc_sep_{loc_id}_{style}
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    parts = q.data.split("_")
    # lc_sep_{loc_id}_{style} — loc_id might have underscore
    # Format: lc_sep_main_line → parts = ['lc','sep','main','line']
    style  = parts[-1]
    loc_id = "_".join(parts[2:-1])
    loc = next((l for l in LOCATIONS if l["id"] == loc_id), None)
    if not loc:
        await q.answer("❌ Unknown location")
        return
    _s(_lc_key(loc_id, "sep"), style)
    await q.answer(f"✅ Separator: {style}")
    await _show_location_panel(q, loc_id, loc)


# ── Columns ──

async def lc_set_cols_callback(update, context):
    """
    Set button column count for a location.
    Callback: lc_cols_{loc_id}_{n}
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    parts = q.data.split("_")
    cols   = parts[-1]
    loc_id = "_".join(parts[2:-1])
    loc = next((l for l in LOCATIONS if l["id"] == loc_id), None)
    if not loc:
        await q.answer("❌ Unknown location")
        return
    _s(_lc_key(loc_id, "cols"), cols)
    await q.answer(f"✅ {cols} column(s)")
    await _show_location_panel(q, loc_id, loc)


# ── Reset Location ──

async def lc_reset_callback(update, context):
    """Reset a location's customizations to defaults."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    loc_id = q.data.replace("lc_reset_", "")
    loc = next((l for l in LOCATIONS if l["id"] == loc_id), None)
    if not loc:
        await q.answer("❌ Unknown location")
        return
    # Clear all settings for this location
    _s(_lc_key(loc_id, "header"), "")
    _s(_lc_key(loc_id, "sep"),    "line")
    _s(_lc_key(loc_id, "cols"),   "2")
    await q.answer(f"✅ {loc['name']} reset to default!")
    await _show_location_panel(q, loc_id, loc)


# ─────────────────────────────────────────────────────────────
# 🆕 v95: ADD CUSTOM LOCATION FLOW
# ─────────────────────────────────────────────────────────────
LC_ADD_ID     = 9540
LC_ADD_NAME   = 9541
LC_ADD_HEADER = 9542


async def lc_add_custom_start(update, context):
    """Entry: admin taps ➕ Add Custom Location."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return -1
    await q.answer()
    text = (
        "➕ *Add Custom Location*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Step 1/3: send a short *id* (lowercase, letters/numbers/underscores).\n\n"
        "Examples: `vip_zone`, `promo_hub`, `contest`\n\n"
        "This id will identify the location internally.\n\n"
        "Send /cancel to abort."
    )
    try:
        await q.edit_message_text(text, parse_mode="Markdown")
    except Exception:
        await q.message.reply_text(text, parse_mode="Markdown")
    return LC_ADD_ID


async def lc_add_id_received(update, context):
    if not _is_admin(update.effective_user.id):
        return -1
    raw = (update.message.text or "").strip().lower().replace(" ", "_")
    if not raw or not raw.replace("_", "").isalnum():
        await update.message.reply_text(
            "❌ Invalid id. Must be lowercase letters, numbers, underscores only.\n"
            "Try again or /cancel.")
        return LC_ADD_ID
    context.user_data["lc_add_id"] = raw
    await update.message.reply_text(
        f"✅ id: `{raw}`\n\n"
        f"Step 2/3: send the *display name* (with emoji).\n\n"
        f"Example: `💎 VIP Zone`",
        parse_mode="Markdown")
    return LC_ADD_NAME


async def lc_add_name_received(update, context):
    if not _is_admin(update.effective_user.id):
        return -1
    raw = (update.message.text or "").strip()
    if not raw:
        await update.message.reply_text("❌ Empty. Try again or /cancel.")
        return LC_ADD_NAME
    context.user_data["lc_add_name"] = raw
    await update.message.reply_text(
        f"✅ Name: `{raw}`\n\n"
        f"Step 3/3: send the *header text* for this screen (with emoji).\n\n"
        f"Example:\n"
        f"`💎 *VIP Zone*\\n━━━━━━━━━━━━━━━━`\n\n"
        f"Send `-` to auto-generate from name.",
        parse_mode="Markdown")
    return LC_ADD_HEADER


async def lc_add_header_received(update, context):
    if not _is_admin(update.effective_user.id):
        return -1
    raw = (update.message.text or "").strip()
    loc_id = context.user_data.get("lc_add_id", "")
    name = context.user_data.get("lc_add_name", "")
    if raw == "-":
        header = f"{name}\n━━━━━━━━━━━━━━━━"
    else:
        header = raw

    try:
        from custom_locations import add_custom_location
        ok, msg = add_custom_location(loc_id, name, header)
    except Exception as e:
        ok, msg = False, f"❌ Error: {e}"

    kb = [[InlineKeyboardButton("🔙 Back to Locations", callback_data="lc_panel")]]
    if ok:
        await update.message.reply_text(
            f"{msg}\n\n"
            f"📍 It now appears in:\n"
            f"• Location Customizer\n"
            f"• Custom Buttons → 'where to place' dropdown\n"
            f"• Any panel that lists locations",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))

    # Clear session state
    for k in ("lc_add_id", "lc_add_name"):
        context.user_data.pop(k, None)
    return -1


async def lc_add_cancel(update, context):
    for k in ("lc_add_id", "lc_add_name"):
        context.user_data.pop(k, None)
    try:
        await update.message.reply_text("❎ Cancelled.")
    except Exception:
        pass
    return -1


async def lc_noop_callback(update, context):
    await update.callback_query.answer()


# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
#  PART 2 — 📝 MESSAGE TEMPLATE EDITOR
# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════

# All editable templates — broadcast + reviews
TEMPLATES = [
    # ── FAKE BROADCAST ──
    {
        "id":      "bc_purchase",
        "name":    "🛒 Purchase",
        "section": "📢 Fake Broadcast",
        "vars":    "{user}, {product}, {qty}, {amount}",
        "default": (
            "🛒 *New Purchase!* 🏪\n\n"
            "👤 User: {user}\n"
            "📦 Product: {product}\n"
            "🔢 QTY: {qty}\n\n"
            "_Thank you for choosing us_ 🛡️"
        ),
        "sample":  {"user": "b***l", "product": "ChatGPT Plus", "qty": "1", "amount": "5.00"},
    },
    {
        "id":      "bc_deposit",
        "name":    "💳 Deposit",
        "section": "📢 Fake Broadcast",
        "vars":    "{user}, {amount}, {method}",
        "default": (
            "💳 *New Deposit!* 💲\n\n"
            "👤 User: {user}\n"
            "💰 Amount: ${amount}\n"
            "🔵 Method: {method}\n\n"
            "_Processed automatically_ ⚡"
        ),
        "sample":  {"user": "a***d", "amount": "10.00", "method": "Binance Pay"},
    },
    {
        "id":      "bc_referral",
        "name":    "🏆 Referral Milestone",
        "section": "📢 Fake Broadcast",
        "vars":    "{user}, {referrals}, {reward}, {total_ref}",
        "default": (
            "🏆 *Referral Milestone!*\n\n"
            "👤 User: {user}\n"
            "✅ Active Referrals: *{referrals}*\n"
            "💰 Reward Earned: *+${reward}*\n"
            "📊 Total from Referrals: *${total_ref}*"
        ),
        "sample":  {"user": "z***n", "referrals": "50", "reward": "0.30", "total_ref": "5.70"},
    },
    {
        "id":      "bc_active_referral",
        "name":    "📈 New Active Referral",
        "section": "📢 Fake Broadcast",
        "vars":    "{user}, {referrals}, {more}",
        "default": (
            "📈 *New Active Referral!*\n\n"
            "👤 Referrer: {user}\n"
            "✅ Active Referrals: *{referrals}*\n"
            "⏳ *{more} more* to earn next reward"
        ),
        "sample":  {"user": "m***d", "referrals": "25", "more": "5"},
    },
    {
        "id":      "tier_display",
        "name":    "📊 Bulk Discounts (Tiered)",
        "section": "🛒 Product Page",
        "vars":    "{product}, {base_price}, {tiers}, {currency}",
        "default": (
            "📊 *Bulk Discounts — Quantity Pricing*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "{tiers}\n"
            "_Buy more, save more!_ 🎉"
        ),
        "sample":  {"product": "🤖 Gemini Pro", "base_price": "1.00",
                    "tiers": "🛒 1+ qty → 💵 **$1.00** each\n🎉 10+ qty → 💵 **$0.89** each"},
    },
    {
        "id":      "tier_line",
        "name":    "📊 Tier Line (per tier)",
        "section": "🛒 Product Page",
        "vars":    "{qty}, {price}, {product}, {base_price}",
        "default": (
            "🎉 {qty}+ qty → 💵 **${price}** each"
        ),
        "sample":  {"qty": "10", "price": "0.89"},
    },
    {
        "id":      "bc_tier",
        "name":    "🎖️ Tier Upgrade",
        "section": "📢 Fake Broadcast",
        "vars":    "{user}, {tier}",
        "default": (
            "🎖️ *Loyalty Tier Upgrade!*\n\n"
            "👤 User: {user}\n"
            "🏆 New Tier: *{tier}*\n\n"
            "_Keep shopping to unlock more rewards!_ 💎"
        ),
        "sample":  {"user": "s***a", "tier": "🥇 Gold"},
    },
    {
        "id":      "bc_discount",
        "name":    "📉 Discount Alert",
        "section": "📢 Fake Broadcast",
        "vars":    "{product}, {old_price}, {new_price}",
        "default": (
            "📉 *Amazing Discount!* 🔥\n\n"
            "Product: {product}\n"
            "Old price: ~~${old_price}~~\n"
            "New price: *${new_price} only!*\n\n"
            "Hurry and buy now from the store!"
        ),
        "sample":  {"product": "ChatGPT Plus", "old_price": "8.0", "new_price": "6.5"},
    },
    {
        "id":      "bc_bulkdeal",
        "name":    "📊 Bulk Deal Hype",
        "section": "📢 Fake Broadcast",
        "vars":    "{user}, {product}, {qty}, {price}, {base_price}, {saving}",
        "default": (
            "📊 *Bulk Deal Alert!* 🎉\n\n"
            "👤 {user} just grabbed {product} at bulk price!\n"
            "🛒 {qty}+ qty → 💵 ${price} each\n"
            "❌ Base: ${base_price} | 💸 Save ${saving} per unit\n\n"
            "🔥 Buy more, save more — tap below!"
        ),
        "sample":  {"user": "b***l", "product": "🤖 Gemini Pro", "qty": "10",
                    "price": "0.89", "base_price": "1.00", "saving": "0.11"},
    },
    {
        "id":      "bc_reseller",
        "name":    "🔗 Reseller Purchase",
        "section": "📢 Fake Broadcast",
        "vars":    "{user}, {product}, {qty}, {amount}, {reseller}",
        "default": (
            "🔗 *Reseller Purchase!* 🚀\n\n"
            "👤 Reseller: {reseller}\n"
            "📦 Product: {product}\n"
            "🔢 QTY: {qty}\n"
            "💰 Amount: ${amount}\n\n"
            "⚡ Auto-delivered via Reseller API!"
        ),
        "sample":  {"user": "r***r", "product": "Acc ChatGPT", "qty": "2",
                    "amount": "13.40", "reseller": "AlexShop"},
    },
    {
        "id":      "bc_stock",
        "name":    "🔔 Restock Alert (Auto)",
        "section": "📢 Fake Broadcast",
        # 🆕 v94: added {added} placeholder — populated by
        # restock_alerts.fire_restock_alert() when stock actually goes up
        # during supplier auto-sync / bulk sync.
        "vars":    "{product}, {added}, {stock}, {price}",
        "default": (
            "🤖 {product}\n\n"
            "➕ Added: {added}\n"
            "📦 Current stock: {stock}\n"
            "💰 Price: ${price}"
        ),
        "sample":  {"product": "ChatGPT Plus Apple Pay Vietnamese card Gmail 1M - 15D warranty",
                     "added": "18", "stock": "24", "price": "4.57"},
    },
    {
        "id":      "bc_review",
        "name":    "🗣 Review Broadcast",
        "section": "📢 Fake Broadcast",
        "vars":    "{user}, {product}, {stars}, {review}",
        "default": (
            "🗣 New Review!\n\n"
            "👤 {user} {stars}\n"
            "📦 {product}\n"
            "💬 {review}"
        ),
        "sample":  {"user": "a***d", "product": "ChatGPT Plus", "stars": "⭐⭐⭐⭐⭐", "review": "works perfectly!"},
    },
    # ── NEW USER JOIN ──
    {
        "id":      "bc_new_user",
        "name":    "🎉 New User Joined",
        "section": "📢 Fake Broadcast",
        "vars":    "{name}, {count}",
        "default": (
            "🎉 *New member joined Bite Store!* 🛍️\n\n"
            "👤 {name} just joined our community!\n"
            "👥 Members: *{count}*\n\n"
            "_Welcome to the family!_ 🚀"
        ),
        "sample":  {"name": "Ali", "count": "1,247"},
    },
    # ── FAKE REVIEWS ──
    {
        "id":      "rv_urdu",
        "name":    "🇵🇰 Urdu Review (Roman)",
        "section": "⭐ Fake Reviews",
        "vars":    "No variables — these are the sentence pool (one per line, bot picks randomly)",
        "default": (
            "bohat acha product hai\n"
            "bilkul original mila\n"
            "delivery bht fast thi\n"
            "price ke hisaab se bohot acha hai\n"
            "works perfectly\n"
            "shukriya bite store\n"
            "highly recommend karta hoon\n"
            "awesome bro\n"
            "ekdum sahi cheez hai\n"
            "dobara zaroor lunga\n"
            "quality se khush hoon\n"
            "phir se order karunga\n"
            "mast experience tha\n"
            "trust this store\n"
            "no issues at all\n"
            "seedha kaam kiya\n"
            "genuine product hai\n"
            "zabardast service\n"
            "fast delivery and original\n"
            "bahut khush hoon"
        ),
        "sample":  {},
    },
    {
        "id":      "rv_english",
        "name":    "🌍 English Review",
        "section": "⭐ Fake Reviews",
        "vars":    "No variables — these are the sentence pool (one per line, bot picks randomly)",
        "default": (
            "works perfectly\n"
            "great product\n"
            "highly recommend\n"
            "legit and fast\n"
            "totally worth it\n"
            "no issues at all\n"
            "exactly as described\n"
            "works like a charm\n"
            "super fast delivery\n"
            "very satisfied\n"
            "good quality\n"
            "genuine product\n"
            "amazing service\n"
            "will buy again\n"
            "loved it\n"
            "solid purchase\n"
            "great value for money\n"
            "100% legit\n"
            "fast and reliable\n"
            "no complaints\n"
            "got it within minutes and everything works fine\n"
            "was skeptical at first but turned out great\n"
            "really happy with this purchase\n"
            "better than I expected honestly\n"
            "smooth transaction and fast delivery\n"
            "trusted seller will definitely come back\n"
            "quick delivery and genuine product\n"
            "completely satisfied with the purchase"
        ),
        "sample":  {},
    },
]


# ════════════════════════════════════════════════════════════════
# 🆕 SELECTABLE TEMPLATE VARIANTS (10 each, attention-seeking, NO * or ~~)
# The admin picks one variant per template; bot uses the selected one.
# All variants are PLAIN text + emojis so users never see raw * _ ~~ symbols.
# ════════════════════════════════════════════════════════════════
TEMPLATE_VARIANTS = {
    "bc_purchase": [
        "🛒 New Purchase! 🏪\n\n👤 {user}\n📦 {product}\n🔢 Qty: {qty}\n💰 ${amount}\n\n⚡ Delivered instantly ✅",
        "🎉 Someone just bought! 🎉\n\n👤 {user} grabbed {product}\n💵 ${amount} ({pkr_amount})\n\n🔥 Get yours too!",
        "✅ Order Completed!\n\n👤 {user}\n📦 {product} x{qty}\n🧾 {txid}\n\n🚀 Instant delivery done!",
        "💸 Sale Alert! 💸\n\n{user} purchased {product}\n💰 Total: ${amount}\n\n🛒 Limited stock — hurry!",
        "🔥 Hot Sale! 🔥\n\n👤 {user}\n🛍 {product} (x{qty})\n💵 ${amount} ~ {pkr_amount}\n\n✨ Tap Buy Now!",
        "🏪 Fresh Order!\n\n👤 Buyer: {user}\n📦 {product}\n💰 ${amount}\n\n⚡ Auto-delivered in seconds!",
        "🎊 Cha-ching! 🎊\n\n{user} just ordered {product}\n🔢 Qty: {qty} | 💵 ${amount}\n\n🛒 Don't miss out!",
        "📦 Order Confirmed!\n\n👤 {user}\n🛍 {product}\n🧾 {txid}\n💰 ${amount}\n\n✅ Delivered ✅",
        "⚡ Instant Sale! ⚡\n\n👤 {user} bought {product}\n💵 ${amount} ({pkr_amount})\n\n🔥 Going fast!",
        "🛒 Bite Store Sale!\n\n👤 {user}\n📦 {product} x{qty}\n💰 ${amount}\n\n🎯 Your turn next!",
    ],
    "bc_deposit": [
        "💳 New Deposit! 💲\n\n👤 {user}\n💰 ${amount} ({pkr_amount})\n🔵 {method}\n\n⚡ Processed automatically!",
        "💵 Wallet Topped Up!\n\n👤 {user} added ${amount}\n🏦 via {method}\n\n🚀 Instant credit!",
        "🤑 Funds Added! 🤑\n\n👤 {user}\n💰 +${amount}\n🔵 {method}\n🧾 {txid}",
        "✅ Deposit Success!\n\n👤 {user}\n💲 ${amount} ~ {pkr_amount}\n🏦 {method}\n\n⚡ Ready to shop!",
        "💰 Balance Loaded!\n\n👤 {user} deposited ${amount}\n🔵 {method}\n\n🛒 Time to grab deals!",
        "🔔 Top-up Alert!\n\n👤 {user}\n💵 ${amount} ({pkr_amount})\n🏦 {method}\n\n✅ Done instantly!",
        "💸 Money In! 💸\n\n👤 {user}\n➕ ${amount}\n🔵 {method}\n\n⚡ Wallet ready!",
        "🏦 Deposit Received!\n\n👤 {user}\n💰 ${amount}\n🧾 {txid}\n\n🚀 Shop now!",
        "🎉 Wallet Funded!\n\n👤 {user} loaded ${amount}\n🔵 {method}\n\n💎 Enjoy instant buys!",
        "⚡ Quick Deposit!\n\n👤 {user}\n💵 ${amount} ~ {pkr_amount}\n🏦 {method}\n\n✅ Confirmed!",
    ],
    "bc_active_referral": [
        "📈 New Active Referral!\n\n👤 {user}\n✅ Active Referrals: {referrals}\n⏳ {more} more to next reward!",
        "🤝 Referral Power! 🤝\n\n👤 {user} now has {referrals} active referrals\n🎯 {more} more for a bonus!",
        "🔥 Referral Streak!\n\n👤 {user}\n✅ {referrals} active invites\n💰 {more} away from reward!",
        "🎉 Invite Win!\n\n👤 {user} reached {referrals} referrals\n⏳ {more} more to earn!",
        "📊 Growing Fast!\n\n👤 {user}\n👥 {referrals} active referrals\n🎁 {more} more = reward!",
        "🚀 Referral Boost!\n\n👤 {user}\n✅ {referrals} active\n⏳ Only {more} more to go!",
        "💎 Referral Milestone Soon!\n\n👤 {user} — {referrals} active\n🎯 {more} left for bonus!",
        "🏆 On Fire!\n\n👤 {user}\n👥 {referrals} referrals active\n⏳ {more} more to win!",
        "✨ Referral Update!\n\n👤 {user}\n✅ {referrals} active invites\n🎁 {more} to next reward!",
        "📣 Keep Going!\n\n👤 {user} has {referrals} active referrals\n⏳ {more} more for a payout!",
    ],
    "bc_discount": [
        "📉 Amazing Discount! 🔥\n\n{product}\n❌ Old: ${old_price}\n✅ Now: ${new_price}!\n\n🛒 Hurry, buy now!",
        "💥 Price Drop! 💥\n\n{product}\n💵 Only ${new_price} (was ${old_price})\n\n⚡ Grab it fast!",
        "🔥 Deal Alert! 🔥\n\n{product}\n🏷️ ${new_price} only!\n📉 Down from ${old_price}\n\n🛒 Limited time!",
        "🎯 Big Savings!\n\n{product}\n✅ Now ${new_price}\n❌ Was ${old_price}\n\n💨 Don't wait!",
        "🛍 Discount Live!\n\n{product}\n💰 ${new_price} (old ${old_price})\n\n🔥 Shop before it ends!",
        "⚡ Flash Discount!\n\n{product}\n💵 ${new_price} only!\n\n📉 Save big vs ${old_price}!",
        "🎉 Mega Offer!\n\n{product}\n🏷️ ${new_price}\n❌ ${old_price}\n\n🛒 Tap to grab!",
        "💸 Cheaper Now!\n\n{product}\n✅ ${new_price} (was ${old_price})\n\n🚀 Buy today!",
        "🔥 Hot Price!\n\n{product}\n💰 ${new_price} only\n\n📉 Down from ${old_price}!",
        "📢 Special Deal!\n\n{product}\n💵 ${new_price}\n❌ ${old_price}\n\n⏳ Hurry up!",
    ],
    "bc_tier": [
        "🎖️ Loyalty Tier Upgrade!\n\n👤 {user}\n🏆 New Tier: {tier}\n\n💎 Keep shopping for more!",
        "🏆 Level Up! 🏆\n\n👤 {user} reached {tier}\n\n✨ More perks unlocked!",
        "💎 Tier Promotion!\n\n👤 {user}\n⬆️ Now {tier}\n\n🎁 Enjoy exclusive rewards!",
        "🎉 Congrats! 🎉\n\n👤 {user} is now {tier}\n\n🚀 Higher tier = better deals!",
        "⭐ New Rank!\n\n👤 {user}\n🏅 {tier} unlocked\n\n💪 Keep it up!",
        "🥇 Upgrade Unlocked!\n\n👤 {user} → {tier}\n\n💎 Special pricing awaits!",
        "🔥 Tier Boost!\n\n👤 {user}\n🏆 {tier}\n\n🎯 Loyalty pays off!",
        "✨ Status Up!\n\n👤 {user} achieved {tier}\n\n🎁 More rewards coming!",
        "🏅 Well Done!\n\n👤 {user}\n⬆️ {tier} member now\n\n💎 Shop & climb higher!",
        "🎊 Tier Achieved!\n\n👤 {user} is {tier}\n\n🚀 Unlock even more perks!",
    ],
    "bc_referral": [
        "🏆 Referral Milestone!\n\n👤 {user}\n✅ Active Referrals: {referrals}\n💰 Reward: +${reward}\n📊 Total Earned: ${total_ref}",
        "🎉 Referral Reward Unlocked!\n\n👤 {user} hit {referrals} referrals\n💵 Earned +${reward}\n🤝 Keep inviting!",
        "💰 Referral Payout!\n\n👤 {user}\n👥 {referrals} active invites\n🎁 +${reward} added (total ${total_ref})",
        "🤝 Big Referrer!\n\n👤 {user} reached {referrals} referrals\n💸 Reward: +${reward}",
        "🚀 Referral Goal Hit!\n\n👤 {user}\n✅ {referrals} referrals\n💰 +${reward} (lifetime ${total_ref})",
        "🎯 Milestone Reached!\n\n👤 {user} — {referrals} active referrals\n🎁 Bonus +${reward}!",
        "💎 Referral Star!\n\n👤 {user}\n👥 {referrals} invites\n💵 +${reward} reward earned",
        "🔥 Referral Win!\n\n👤 {user} got {referrals} referrals\n💰 +${reward} (total ${total_ref})",
        "🏅 Top Referrer!\n\n👤 {user}\n✅ {referrals} active\n🎁 +${reward} just credited!",
        "📣 Referral Bonus!\n\n👤 {user} — {referrals} referrals done\n💸 +${reward} reward!",
    ],
    "bc_stock": [
        # 🆕 v94: Fresh set of 10 restock templates matching user's format.
        # Each shows: product name · ➕ Added · 📦 Current stock · 💰 Price
        # Placeholders: {product}, {added}, {stock}, {price}
        # Admin can use premium <tg-emoji> in any of these via Edit Templates.
        "🤖 {product}\n\n➕ Added: {added}\n📦 Current stock: {stock}\n💰 Price: ${price}",
        "🔔 New Stock Alert!\n\n🏪 {product}\n➕ Added: {added} units\n📦 Now in stock: {stock}\n💰 Price: ${price}\n\n🛒 Grab yours before they're gone!",
        "📦 Restocked!\n\n🆕 {product}\n➕ Fresh units: {added}\n✅ Available: {stock}\n💵 ${price}\n\n⚡ Fast delivery — order now!",
        "🚨 Stock Update!\n\n🏪 {product}\n📈 +{added} added\n📊 Total stock: {stock}\n💰 ${price}\n\n🔥 Selling fast!",
        "✨ Back in Stock!\n\n📦 {product}\n➕ {added} new units added\n✅ Currently: {stock}\n💵 Only ${price}\n\n🚀 Order today!",
        "💎 Fresh Restock!\n\n{product}\n➕ Added: {added}\n📦 Available now: {stock}\n💰 Just ${price}\n\n🛒 Don't wait!",
        "🔥 Hot Stock Drop!\n\n🏪 {product}\n➕ Just added: {added}\n📊 Total in stock: {stock}\n💵 ${price}\n\n⚡ Limited quantity!",
        "📢 Restock Announcement!\n\n📦 {product}\n➕ New: +{added}\n✅ Available: {stock}\n💰 ${price} each\n\n🛒 Tap Buy Now to grab yours",
        "🆕 Now Available!\n\n🏪 {product}\n➕ Freshly stocked: {added} units\n📦 In stock: {stock}\n💵 ${price}\n\n💨 Move fast — hot item!",
        "⚡ Quick Restock!\n\n📦 {product}\n➕ Added: +{added}\n✅ Now: {stock} in stock\n💰 Price: ${price}\n\n🎯 Your chance — buy now!",
    ],
    "bc_new_user": [
        "🎉 New member joined Bite Store! 🛍️\n\n👤 {name} just joined!\n👥 Members: {count}\n\nWelcome to the family! 🚀",
        "👋 Welcome aboard!\n\n🎊 {name} joined our community\n👥 Total Members: {count}",
        "🆕 New Shopper!\n\n👤 {name} is now part of Bite Store\n👥 {count} members & growing!",
        "🎉 Community Growing!\n\n👤 {name} joined us\n👥 We're now {count} strong! 💪",
        "🚀 Fresh Face!\n\n👋 {name} just signed up\n👥 Members: {count}",
        "💫 Welcome {name}!\n\n🛍️ Another happy shopper joined\n👥 {count} members now",
        "🎊 New Join Alert!\n\n👤 {name}\n👥 Family size: {count}\n\nWelcome! 🤝",
        "🆕 Say Hi to {name}!\n\n👥 Bite Store now has {count} members\n🚀 Join the fun!",
        "🌟 Growing Strong!\n\n👤 {name} joined\n👥 {count} total members",
        "🎉 +1 Member!\n\n👋 {name} is here\n👥 Community: {count} people!",
    ],
    "bc_review": [
        "🗣 New Review!\n\n👤 {user} {stars}\n📦 {product}\n💬 {review}",
        "⭐ Customer Loved It!\n\n👤 {user}\n📦 {product}\n{stars}\n💬 {review}",
        "💬 Fresh Feedback!\n\n👤 {user} rated {product}\n{stars}\n“{review}”",
        "🌟 Happy Buyer!\n\n👤 {user} {stars}\n📦 {product}\n💬 {review}",
        "✅ Verified Review!\n\n👤 {user}\n📦 {product} {stars}\n💬 {review}",
        "🔥 People Love This!\n\n👤 {user} {stars}\n📦 {product}\n💬 {review}",
        "💎 Top Rated!\n\n👤 {user}\n📦 {product}\n{stars}\n💬 {review}",
        "📣 Real Feedback!\n\n👤 {user} {stars}\n{product}\n💬 {review}",
        "🎉 5-Star Vibes!\n\n👤 {user}\n📦 {product} {stars}\n💬 {review}",
        "👍 Recommended!\n\n👤 {user} {stars}\n📦 {product}\n💬 {review}",
    ],
    # 🆕 v161.12: BULK DISCOUNT HYPE (fake) — fired when admin adds a tier +
    # periodically for products that have bulk tiers.
    # Placeholders: {user}, {product}, {qty}, {price}, {base_price}, {saving}
    "bc_bulkdeal": [
        "📊 *Bulk Deal Alert!* 🎉\n\n👤 {user} just grabbed {product} at bulk price!\n🛒 {qty}+ qty → 💵 ${price} each\n❌ Base: ${base_price} | 💸 Save ${saving} per unit\n\n🔥 Buy more, save more — tap below!",
        "🚀 *Bulk Buying is LIVE!*\n\n👤 {user} ordered {qty}+ units of {product}\n💰 Unit price: ${price} (was ${base_price})\n💎 You save ${saving} each!\n\n🛍️ Grab your bulk deal now!",
        "🔥 *Hot Bulk Deal!*\n\n📦 {product}\n🎯 {qty}+ qty → ${price} each\n❌ Normal: ${base_price}\n💸 Save ${saving}/unit\n\n👤 {user} & many more already buying!",
        "💥 *Quantity Discount!*\n\n{product}\n🛒 Buy {qty}+ → only ${price} each\n❌ Regular price: ${base_price}\n💎 Save ${saving} per item\n\n⚡ Stocks moving fast — order now!",
        "🎉 *People Are Bulk-Buying!*\n\n📦 {product}\n👤 {user} just bought {qty} units\n💰 Bulk price: ${price} (normal ${base_price})\n\n🛒 Tap Buy Now & save ${saving}/unit!",
        "📢 *Mega Bulk Offer!*\n\n{product}\n🛒 {qty}+ qty → 💵 ${price} each\n❌ Was ${base_price}\n💸 Save ${saving} per unit\n\n🔥 Join the rush — limited bulk stock!",
        "⚡ *Bulk Sale Spreading!*\n\n👤 {user} ordered {qty}+ of {product}\n🏷️ Only ${price} each (base ${base_price})\n💎 Save ${saving}/unit\n\n🛍️ Don't miss the bulk price!",
        "💎 *Smart Buyers Know This Deal!*\n\n📦 {product}\n🎯 {qty}+ qty → ${price} each\n❌ Normal: ${base_price}\n💸 Save ${saving}/unit\n\n👤 {user} just stocked up!",
        "🛒 *Bulk Discount Running!*\n\n{product}\n📊 {qty}+ qty → 💵 ${price} each\n❌ Regular ${base_price} | 💎 Save ${saving}\n\n🔥 Many orders coming in — grab yours!",
        "🎊 *Big Buy Alert!*\n\n👤 {user} purchased {qty} units of {product}\n💰 Bulk price: ${price} each\n❌ Base: ${base_price}\n💸 Save ${saving}/unit — Buy Now!",
    ],
    # 🆕 v161.12: RESELLER API PURCHASE (fake + real hype) — fired when an order
    # comes through the Reseller API, plus periodic fake ones to hype the API.
    # Placeholders: {user}, {product}, {qty}, {amount}, {reseller}
    "bc_reseller": [
        "🔗 *Reseller Purchase!* 🚀\n\n👤 Reseller: {reseller}\n📦 Product: {product}\n🔢 QTY: {qty}\n💰 Amount: ${amount}\n\n⚡ Auto-delivered via Reseller API!",
        "💼 *API Order In!*\n\n🛒 {product} x{qty}\n👤 Via reseller {reseller}\n💰 ${amount}\n\n✅ Delivered instantly through the API!",
        "🤝 *Reseller Sold!*\n\n📦 {product} (x{qty})\n👤 Reseller: {reseller}\n💰 ${amount}\n\n🔗 Powered by Bite Store Reseller API!",
        "🛍️ *New Reseller Order!*\n\n👤 {reseller} sold {product}\n🔢 Qty: {qty} | 💵 ${amount}\n\n⚡ Auto-fulfilled by our suppliers — instantly!",
        "💎 *Reseller Growth!*\n\n{reseller} just delivered {product} x{qty}\n💰 ${amount}\n\n🔗 Sell our products on YOUR bot too!",
        "🚀 *API Selling Live!*\n\n{product} x{qty} sold via API\n👤 Reseller: {reseller}\n💰 ${amount}\n\n⚡ Instant delivery — no manual work!",
        "💰 *Passive Reseller Income!*\n\n👤 {reseller}\n📦 {product} x{qty}\n💵 ${amount}\n\n🔗 Want your own store? Get an API key!",
        "📦 *Wholesale Order!*\n\n{product} (x{qty})\n👤 Reseller {reseller}\n💰 ${amount}\n\n✅ Auto-delivered via Reseller API!",
        "🎉 *Reseller Success!*\n\n{reseller} just earned from {product} x{qty}\n💰 ${amount}\n\n🔗 Join the Reseller API and sell too!",
        "⚡ *Instant API Delivery!*\n\n📦 {product} x{qty}\n👤 Reseller: {reseller}\n💰 ${amount}\n\n🛒 Fully automated by Bite Store!",
    ],
}


def _tpl_key(tpl_id):
    return f"tpl_{tpl_id}"


def _tpl_sel_key(tpl_id):
    return f"tplsel_{tpl_id}"


def get_template_variants(tpl_id):
    """Return the list of selectable variants for a template (may be empty)."""
    return TEMPLATE_VARIANTS.get(tpl_id, [])


def get_selected_variant_index(tpl_id):
    variants = get_template_variants(tpl_id)
    if not variants:
        return 0
    try:
        i = int(_g(_tpl_sel_key(tpl_id), "0") or 0)
    except Exception:
        i = 0
    return max(0, min(len(variants) - 1, i))


def set_selected_variant_index(tpl_id, i):
    _s(_tpl_sel_key(tpl_id), int(i))


def get_template(tpl_id):
    """Get current template text.
    Priority: admin custom text  →  selected variant  →  variant[0]  →  legacy default.
    """
    tpl = next((t for t in TEMPLATES if t["id"] == tpl_id), None)
    # 1. Admin's own custom text wins.
    custom = _g(_tpl_key(tpl_id), "")
    if custom:
        return custom
    # 2. Selected variant from the 10 options.
    variants = get_template_variants(tpl_id)
    if variants:
        return variants[get_selected_variant_index(tpl_id)]
    # 3. Legacy default.
    if tpl:
        return tpl["default"]
    return ""


def render_template(tpl_id, data: dict):
    """
    Render a template with actual data.
    Used by fake_broadcast.py to build messages.

    Args:
        tpl_id: template ID (e.g. 'bc_purchase')
        data:   dict of variable values

    Returns:
        rendered message string
    """
    text = get_template(tpl_id)
    try:
        # 🐛 v149 FIX: case-insensitive placeholder fill. Old code used
        # `.format(**data)` with exact keys — `{Product}` vs `product` threw
        # KeyError → returned the RAW template (placeholders sent literally).
        # Now any casing works; unknown keys stay untouched.
        import re as _re
        low_map = {str(k).lower(): v for k, v in (data or {}).items()}
        def _sub(m):
            key = m.group(1)
            spec = m.group(2) or ""
            v = low_map.get(key.lower())
            if v is None:
                return m.group(0)
            try:
                return format(str(v), spec) if spec else str(v)
            except Exception:
                return str(v)
        return _re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)(:[^}]*)?\}", _sub, text)
    except Exception:
        return text  # Return unformatted if variable missing


def get_review_sentences(language):
    """
    Get the review sentence pool for a language.

    Args:
        language: 'urdu' or 'english'

    Returns:
        list of sentences (strings)
    """
    tpl_id = "rv_urdu" if language == "urdu" else "rv_english"
    text = get_template(tpl_id)
    # Each line is one sentence
    sentences = [line.strip() for line in text.split("\n") if line.strip()]
    return sentences if sentences else ["good product"]


# ── Main Template Panel ──

async def template_editor_panel_callback(update, context):
    """
    Main Template Editor panel.
    Shows all templates grouped by section.
    Access: Admin Panel → 📝 Message Templates
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    text = (
        "📝 *Message Template Editor*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Customize the exact text of every fake message.\n\n"
        "*📢 Fake Broadcast templates:*\n"
        "  🛒 Purchase • 💳 Deposit • 🏆 Referral\n"
        "  📈 Active Referral • 🎖️ Tier • 📉 Discount\n"
        "  🔔 Stock Alert\n\n"
        "*⭐ Fake Review templates:*\n"
        "  🇵🇰 Urdu sentence pool\n"
        "  🌍 English sentence pool\n\n"
        "_Select a template to edit:_"
    )

    # Group by section
    sections = {}
    for tpl in TEMPLATES:
        sec = tpl["section"]
        if sec not in sections:
            sections[sec] = []
        sections[sec].append(tpl)

    keyboard = []
    for sec_name, tpls in sections.items():
        keyboard.append([InlineKeyboardButton(f"── {sec_name} ──", callback_data="tpl_noop")])
        row = []
        for tpl in tpls:
            row.append(InlineKeyboardButton(tpl["name"], callback_data=f"tpl_pick_{tpl['id']}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

    # 🆕 Store announcement templates (selectable 1..10 each)
    keyboard.append([InlineKeyboardButton("── 📣 Store Announcements ──", callback_data="tpl_noop")])
    keyboard.append([
        InlineKeyboardButton("⚡ Flash Sale Templates", callback_data="sbtpl_flash"),
        InlineKeyboardButton("🆕 New Product Templates", callback_data="sbtpl_newprod"),
    ])

    keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")])
    await _edit(q, text, keyboard)


# ════════════════════════════════════════════════════════════════
# 🆕 STORE-BROADCAST TEMPLATE PICKERS (Flash Sale / New Product)
# ════════════════════════════════════════════════════════════════

def _sb_meta(kind):
    """Return (templates, get_index, set_index, sample_product, title, emoji)."""
    import fake_engagement as sb
    sample = {"name": "ChatGPT Plus 1 Month", "flash_price": 3.80, "price": 4.00,
              "description": "Premium account, instant delivery", "stock": 10}
    if kind == "flash":
        return (sb.FLASH_TEMPLATES, sb.get_flash_template_index, sb.set_flash_template_index,
                sample, "Flash Sale", "⚡")
    return (sb.NEW_PRODUCT_TEMPLATES, sb.get_newprod_template_index, sb.set_newprod_template_index,
            sample, "New Product", "🆕")


async def sb_template_panel_callback(update, context):
    """Show the selectable Flash Sale / New Product templates (1..10) + preview."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True); return
    await q.answer()
    kind = q.data.replace("sbtpl_", "")
    import fake_engagement as sb
    templates, get_idx, set_idx, sample, title, emoji = _sb_meta(kind)
    cur = get_idx()
    custom = sb.get_flash_custom() if kind == "flash" else sb.get_newprod_custom()
    # Build preview of the active template (custom wins)
    if kind == "flash":
        preview = sb.build_flash_message(sample, timer_text="2️⃣3️⃣➖5️⃣9️⃣➖5️⃣9️⃣")
    else:
        preview = sb.build_newproduct_message(sample)

    active_label = "✏️ Custom" if custom else f"#{cur+1}"
    text = (
        f"{emoji} *{title} Templates*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Currently using: *{active_label}* of {len(templates)} ready-made.\n"
        f"_A 🛒 Buy Now button is added automatically._\n\n"
        f"👁️ *Live Preview:*\n\n{preview}"
    )
    keyboard = []
    row = []
    for i in range(len(templates)):
        label = f"✅ {i+1}" if (i == cur and not custom) else f"{i+1}"
        row.append(InlineKeyboardButton(label, callback_data=f"sbset_{kind}_{i}"))
        if len(row) == 5:
            keyboard.append(row); row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("✏️ Add / Edit Custom Template", callback_data=f"sbcustom_{kind}")])
    keyboard.append([InlineKeyboardButton("🧪 Test (send to my location)", callback_data=f"sbtest_{kind}")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Templates", callback_data="tpl_panel")])
    await _edit(q, text, keyboard)


async def sb_custom_start_callback(update, context):
    """Ask admin to type a custom Flash Sale / New Product template."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True); return ConversationHandler.END
    await q.answer()
    kind = q.data.replace("sbcustom_", "")
    context.user_data["sb_custom_kind"] = kind
    if kind == "flash":
        vars_help = "{product}, {price}, {regular}, {save}, {timer}"
    else:
        vars_help = "{product}, {price}, {desc}, {stock}"
    title = "Flash Sale" if kind == "flash" else "New Product"
    text = (
        f"✏️ *Custom {title} Template*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Available variables:*\n`{vars_help}`\n\n"
        f"• Use `*text*` for bold\n"
        f"• 🛒 Buy Now button is added automatically\n\n"
        f"Send your custom template now (or send `-` to clear & use ready-made):"
    )
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=f"sbtpl_{kind}")]]
    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        pass
    return SB_CUSTOM_TEXT


async def sb_custom_received(update, context):
    """Save the custom Flash / New Product template text."""
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END
    kind = context.user_data.get("sb_custom_kind")
    if not kind:
        return ConversationHandler.END
    import fake_engagement as sb
    # 🆕 Premium-emoji aware: capture HTML form when admin used custom emojis
    raw_txt = (update.message.text or "").strip()
    try:
        html_txt = (update.message.text_html_urled or "").strip()
    except Exception:
        html_txt = ""
    has_custom_emoji = any(
        getattr(e, "type", "") == "custom_emoji"
        for e in (update.message.entities or [])
    )
    has_entities = bool(update.message.entities)
    if html_txt and has_custom_emoji:
        txt = "[[HTML]]" + html_txt
    else:
        txt = raw_txt
    title = "Flash Sale" if kind == "flash" else "New Product"
    if raw_txt == "-":
        if kind == "flash": sb.set_flash_custom("")
        else: sb.set_newprod_custom("")
        msg = f"✅ Custom {title} template cleared. Using ready-made templates now."
    else:
        if kind == "flash": sb.set_flash_custom(txt)
        else: sb.set_newprod_custom(txt)
        msg = f"✅ Custom {title} template saved!"
    context.user_data.pop("sb_custom_kind", None)
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data=f"sbtpl_{kind}")]]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


async def sb_test_callback(update, context):
    """Send a Flash Sale / New Product sample to the configured destination."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True); return
    kind = q.data.replace("sbtest_", "")
    import fake_engagement as sb
    _, _, _, sample, title, _ = _sb_meta(kind)
    await q.answer("📤 Sending test to your location…")
    # Use a real product if available so the Buy Now button works
    pid = None
    prod = sample
    try:
        from database import get_all_active_products
        prods = get_all_active_products()
        if prods:
            prod = prods[0]; pid = prod["id"]
    except Exception:
        pass
    if kind == "flash":
        # ensure a flash price exists for preview maths
        d = dict(prod)
        if not d.get("flash_price"):
            d["flash_price"] = round(float(d.get("price", 4) or 4) * 0.8, 2)
        text = sb.build_flash_message(d, timer_text=sb._flash_timer_text(""))
    else:
        text = sb.build_newproduct_message(prod)
    try:
        sent = await sb.broadcast_store_message(context.bot, text, pid=pid)
        from database import get_setting
        mode = get_setting("dest_mode", "bot_only")
        dest_label = {"bot_only": "🤖 Bot users", "group_only": "👥 Group", "both": "🤖+👥 Both"}.get(mode, mode)
        note = f"✅ *Test sent!*\n\nDelivered to: {dest_label}\nReached: *{sent}* destination(s)."
    except Exception as e:
        note = f"⚠️ Test failed: {e}"
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data=f"sbtpl_{kind}")]]
    await _edit(q, note, keyboard)


async def sb_template_set_callback(update, context):
    """Select a Flash Sale / New Product template. Callback: sbset_{kind}_{index}"""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True); return
    raw = q.data.replace("sbset_", "")
    kind, _, idx_s = raw.rpartition("_")
    try:
        idx = int(idx_s)
    except ValueError:
        await q.answer("Bad index", show_alert=True); return
    _, get_idx, set_idx, _, title, _ = _sb_meta(kind)
    set_idx(idx)
    await q.answer(f"✅ {title} template #{idx+1} selected!")
    q.data = f"sbtpl_{kind}"
    await sb_template_panel_callback(update, context)


# ── Template Detail ──

async def tpl_pick_callback(update, context):
    """
    Show a specific template with edit/reset/preview options.
    Callback: tpl_pick_{tpl_id}
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    tpl_id = q.data.replace("tpl_pick_", "")
    tpl = next((t for t in TEMPLATES if t["id"] == tpl_id), None)
    if not tpl:
        await q.answer("❌ Not found", show_alert=True)
        return

    current = get_template(tpl_id)
    is_custom = _g(_tpl_key(tpl_id), "") != ""

    # Is this a review sentence pool?
    is_pool = tpl_id.startswith("rv_")
    count_info = ""
    if is_pool:
        sentences = [l.strip() for l in current.split("\n") if l.strip()]
        count_info = f"\n_Pool has {len(sentences)} sentences — bot picks 1-2 randomly_\n"

    variants = get_template_variants(tpl_id)
    sel_idx = get_selected_variant_index(tpl_id)
    var_info = ""
    if variants and not is_custom:
        var_info = f"\n_Using template *#{sel_idx+1}* of {len(variants)}. Tap a number below to switch._\n"

    text = (
        f"📝 *{tpl['name']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Variables:* `{tpl['vars']}`\n"
        f"{count_info}{var_info}\n"
        f"*{'Custom' if is_custom else f'Template #{sel_idx+1}'}:*\n"
        f"```\n{current[:600]}{'...' if len(current)>600 else ''}\n```"
    )

    keyboard = []
    # 🆕 10 selectable variant buttons (1..10), current one marked.
    if variants:
        row = []
        for i in range(len(variants)):
            label = f"✅ {i+1}" if (i == sel_idx and not is_custom) else f"{i+1}"
            row.append(InlineKeyboardButton(label, callback_data=f"tpl_setvar_{tpl_id}_{i}"))
            if len(row) == 5:
                keyboard.append(row); row = []
        if row:
            keyboard.append(row)

    keyboard.append([InlineKeyboardButton("✏️ Edit (Custom)", callback_data=f"tpl_edit_{tpl_id}")])

    # 🆕 v43: Per-template button text editor (only for templates that ship
    # with a Buy-Now-style inline button). Premium-emoji aware.
    try:
        from button_system import (
            template_has_button as _tpl_has_btn,
            get_button_text as _gbt,
            get_button_emoji_id as _gbei,
        )
        if _tpl_has_btn(tpl_id):
            cur_btn_txt   = _gbt(tpl_id)
            cur_btn_emoji = _gbei(tpl_id)
            preview = cur_btn_txt[:18] + ("…" if len(cur_btn_txt) > 18 else "")
            emoji_mark = "  ⭐" if cur_btn_emoji else ""
            keyboard.append([InlineKeyboardButton(
                f"🔘 Edit Button Text  [{preview}]{emoji_mark}",
                callback_data=f"tplbtn_edit_{tpl_id}"
            )])
    except Exception:
        pass

    keyboard.append([
        InlineKeyboardButton("👁️ Live Preview",       callback_data=f"tpl_preview_{tpl_id}"),
        InlineKeyboardButton("🔄 Reset to Default",   callback_data=f"tpl_reset_{tpl_id}"),
    ])
    # 🆕 Test → sends this template to the configured destination (bot/group/both)
    keyboard.append([InlineKeyboardButton("🧪 Test (send to my location)", callback_data=f"tpl_test_{tpl_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Templates", callback_data="tpl_panel")])
    await _edit(q, text, keyboard)


async def tpl_setvar_callback(update, context):
    """🆕 Select one of the 10 variants for a template.
    Callback: tpl_setvar_{tpl_id}_{index}
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    raw = q.data.replace("tpl_setvar_", "")
    # tpl_id may contain underscores; index is the last segment
    tpl_id, _, idx_s = raw.rpartition("_")
    try:
        idx = int(idx_s)
    except ValueError:
        await q.answer("Bad index", show_alert=True); return
    # Selecting a variant clears any custom override so the choice takes effect.
    _s(_tpl_key(tpl_id), "")
    set_selected_variant_index(tpl_id, idx)
    await q.answer(f"✅ Template #{idx+1} selected!")
    # Re-render the detail screen
    q.data = f"tpl_pick_{tpl_id}"
    await tpl_pick_callback(update, context)


# ── Edit Template ──

async def tpl_edit_callback(update, context):
    """Ask admin to type the new template text."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()

    tpl_id = q.data.replace("tpl_edit_", "")
    tpl = next((t for t in TEMPLATES if t["id"] == tpl_id), None)
    if not tpl:
        return ConversationHandler.END

    context.user_data["tpl_edit_id"] = tpl_id
    current = get_template(tpl_id)
    is_pool = tpl_id.startswith("rv_")

    if is_pool:
        instructions = (
            f"📝 *Edit {tpl['name']} Pool*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Write one sentence per line.\n"
            f"Bot will randomly pick 1-2 sentences per review.\n\n"
            f"*Rules:*\n"
            f"• One sentence per line\n"
            f"• No special formatting needed\n"
            f"• Keep them natural and human-like\n"
            f"• Min 10 sentences recommended\n\n"
            f"*Current (first 5 lines):*\n"
            f"`{chr(10).join(current.split(chr(10))[:5])}`\n\n"
            f"Send your full new list now:"
        )
    else:
        instructions = (
            f"📝 *Edit {tpl['name']} Template*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*Available variables:*\n`{tpl['vars']}`\n\n"
            f"*Formatting options:*\n"
            f"• Use `{{variable}}` for dynamic values\n"
            f"• Use `*text*` for bold (markdown)\n"
            f"• Use `_text_` for italic\n"
            f"• Use `~~text~~` for strikethrough\n\n"
            f"⭐ *Premium / Custom Emojis:*\n"
            f"• Type the message in Telegram using your keyboard\n"
            f"• Insert premium emojis the normal way (long-press / picker)\n"
            f"• Bot will auto-detect & save them with full HTML formatting\n"
            f"• Premium emojis will broadcast correctly (visible to Premium users;\n"
            f"  others see the fallback standard emoji)\n\n"
            f"*Current template:*\n"
            f"`{current[:300]}`\n\n"
            f"Send your new template now:"
        )

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=f"tpl_pick_{tpl_id}")]]
    try:
        await q.edit_message_text(instructions, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        pass
    return TPL_TEXT


async def tpl_text_received(update, context):
    """Save the new template text.

    🆕 PREMIUM EMOJI FIX:
    If the admin sent the message with Telegram's native formatting
    (bold/italic/custom_emoji etc.), `update.message.text_html_urled`
    returns the full HTML representation INCLUDING
    <tg-emoji emoji-id="...">😀</tg-emoji> tags for premium emojis.
    We save that HTML version (prefixed with a sentinel marker), so the
    broadcast sender can switch to parse_mode="HTML" and keep premium emojis.
    """
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    tpl_id = context.user_data.get("tpl_edit_id")
    if not tpl_id:
        return ConversationHandler.END

    tpl = next((t for t in TEMPLATES if t["id"] == tpl_id), None)

    # --- premium-emoji aware extraction ---
    raw_text = (update.message.text or "").strip()
    try:
        html_text = (update.message.text_html_urled or "").strip()
    except Exception:
        html_text = ""

    has_entities = bool(update.message.entities)
    has_custom_emoji = any(
        getattr(e, "type", "") == "custom_emoji"
        for e in (update.message.entities or [])
    )

    if html_text and has_custom_emoji:
        # Store HTML version with sentinel so sender switches to HTML parse_mode
        new_text = "[[HTML]]" + html_text
    else:
        new_text = raw_text

    _s(_tpl_key(tpl_id), new_text)

    is_pool = tpl_id.startswith("rv_")
    is_html = new_text.startswith("[[HTML]]")
    if is_pool:
        count = len([l for l in new_text.split("\n") if l.strip()])
        confirm = f"✅ *{tpl['name']} Updated!*\n\n{count} sentences saved in pool."
    elif is_html:
        confirm = (
            f"✅ *{tpl['name']} Template Saved!*\n\n"
            f"🎉 Custom / Premium emoji detected and preserved!\n"
            f"Broadcast will use HTML mode so premium emojis render correctly.\n\n"
            f"_Note: Premium emojis only appear for users with Telegram Premium._\n"
            f"_Non-premium users see the fallback standard emoji._\n\n"
            f"Tap 👁️ Preview to see the live render."
        )
    else:
        confirm = f"✅ *{tpl['name']} Template Saved!*\n\nPreview:\n{new_text[:200]}"

    keyboard = [
        [
            InlineKeyboardButton("👁️ Preview",           callback_data=f"tpl_preview_{tpl_id}"),
            InlineKeyboardButton("🔙 Back to Templates", callback_data="tpl_panel"),
        ]
    ]
    await update.message.reply_text(confirm, parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


# ── Preview ──

async def tpl_preview_callback(update, context):
    """
    Show a live preview of the template rendered with sample data.
    Callback: tpl_preview_{tpl_id}
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    tpl_id = q.data.replace("tpl_preview_", "")
    tpl = next((t for t in TEMPLATES if t["id"] == tpl_id), None)
    if not tpl:
        await q.answer("❌ Not found", show_alert=True)
        return

    is_pool = tpl_id.startswith("rv_")

    if is_pool:
        import random
        sentences = get_review_sentences("urdu" if "urdu" in tpl_id else "english")
        picked = random.sample(sentences, min(2, len(sentences)))
        preview = " ".join(picked)
        lang_flag = "🇵🇰" if "urdu" in tpl_id else "🌍"
        text = (
            f"👁️ *Preview — {tpl['name']}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*Sample review text (random pick):*\n\n"
            f"{lang_flag} Ahmed ⭐⭐⭐⭐⭐\n"
            f"_{preview}_\n\n"
            f"_Bot picks 1-2 random sentences from your pool each time_"
        )
    else:
        rendered = render_template(tpl_id, tpl["sample"])
        # 🆕 If template was saved with custom/premium emojis ([[HTML]] sentinel),
        # send a separate HTML-formatted preview message so emojis render natively.
        if isinstance(rendered, str) and rendered.startswith("[[HTML]]"):
            html_body = rendered[len("[[HTML]]"):]
            text = (
                f"👁️ *Preview — {tpl['name']}*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"_HTML/premium-emoji template detected. Live render sent below ⬇️_"
            )
            keyboard = [
                [
                    InlineKeyboardButton("✏️ Edit",              callback_data=f"tpl_edit_{tpl_id}"),
                    InlineKeyboardButton("🔙 Back to Templates", callback_data="tpl_panel"),
                ]
            ]
            await _edit(q, text, keyboard)
            # Now send the real HTML preview as a separate message
            try:
                await q.message.reply_text(html_body, parse_mode="HTML")
            except Exception:
                try:
                    await q.message.reply_text(html_body)
                except Exception:
                    pass
            return
        text = (
            f"👁️ *Preview — {tpl['name']}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*This is how it looks to users:*\n\n"
            f"{rendered}"
        )

    keyboard = [
        [
            InlineKeyboardButton("✏️ Edit",              callback_data=f"tpl_edit_{tpl_id}"),
            InlineKeyboardButton("🔙 Back to Templates", callback_data="tpl_panel"),
        ]
    ]
    await _edit(q, text, keyboard)


# ── Reset Template ──

async def tpl_reset_callback(update, context):
    """Reset a template to its default."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return

    tpl_id = q.data.replace("tpl_reset_", "")
    tpl = next((t for t in TEMPLATES if t["id"] == tpl_id), None)
    if not tpl:
        await q.answer("❌ Not found", show_alert=True)
        return

    # Clear custom — will fall back to default
    _s(_tpl_key(tpl_id), "")
    await q.answer(f"✅ {tpl['name']} reset to default!")
    await tpl_pick_callback(update, context)


async def tpl_noop_callback(update, context):
    await update.callback_query.answer()


# ════════════════════════════════════════════════════════════════
# 🧪 TEST → send a real sample of this template to the configured
#    destination (bot / group / both), exactly like fake activity.
# ════════════════════════════════════════════════════════════════
def _render_sample_for_test(tpl_id):
    """Return a fully-rendered sample message for any template id.
    For the review sentence pools it builds a sample review message."""
    tpl = next((t for t in TEMPLATES if t["id"] == tpl_id), None)
    if tpl_id.startswith("rv_"):
        import random
        sentences = get_review_sentences("urdu" if "urdu" in tpl_id else "english")
        picked = " ".join(random.sample(sentences, min(2, len(sentences))))
        flag = "🇵🇰" if "urdu" in tpl_id else "🌍"
        return f"🗣 {flag} Ahmed ⭐⭐⭐⭐⭐\n{picked}"
    if tpl:
        return render_template(tpl_id, tpl.get("sample", {}))
    return None


async def tpl_test_callback(update, context):
    """Send a sample of the selected template to the admin's chosen destination.

    🔧 v44 FIX: We now explicitly pass tpl_id through to
    broadcast_store_message so the EXACT button (with its premium-emoji
    icon, if any) saved for THIS template is used. Earlier the broadcast
    function auto-guessed the btn_key from text content, which mismatched
    the saved-per-template key and dropped the icon.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    tpl_id = q.data.replace("tpl_test_", "")
    msg = _render_sample_for_test(tpl_id)
    if not msg:
        await q.answer("❌ Template not found", show_alert=True)
        return
    await q.answer("📤 Sending test to your location…")
    try:
        from fake_engagement import broadcast_store_message
        # Attach a Buy Now button if there's at least one product (best-effort)
        pid = None
        try:
            from database import get_all_active_products
            prods = get_all_active_products()
            if prods:
                pid = prods[0]["id"]
        except Exception:
            pid = None
        # 🆕 v44: forward tpl_id so the per-template button (with icon) is used
        sent = await broadcast_store_message(context.bot, msg, pid=pid, tpl_id=tpl_id)
        from database import get_setting
        mode = get_setting("dest_mode", "bot_only")
        dest_label = {"bot_only": "🤖 Bot users", "group_only": "👥 Group", "both": "🤖+👥 Both"}.get(mode, mode)

        # 🆕 v44: Show diagnostic — what icon (if any) was attached?
        diag_extra = ""
        try:
            from button_system import get_button_emoji_id, diagnose_send
            eid = get_button_emoji_id(tpl_id)
            if eid:
                d = diagnose_send()
                diag_extra = (
                    f"\n\n⭐ *Premium icon attached:* `{eid}`\n"
                    f"PTB: `{d['ptb_version']}` · ready={d['ready']}\n"
                    f"_Agar test message me icon NAHI dikha to:_\n"
                    f"• Make sure bot owner ke account par Telegram Premium *active* hai\n"
                    f"• Destination *channel* na ho (channels block icons)\n"
                    f"• Apna Telegram app latest update karein"
                )
        except Exception:
            pass

        note = (f"✅ *Test sent!*\n\n"
                f"Delivered to: {dest_label}\n"
                f"Destinations reached: *{sent}*\n\n"
                f"_This is exactly how it appears live._{diag_extra}")
    except Exception as e:
        note = f"⚠️ Test failed: {e}"
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data=f"tpl_pick_{tpl_id}")]]
    await _edit(q, note, keyboard)


# ════════════════════════════════════════════════════════════════
# 🆕 v43: PER-TEMPLATE BUTTON TEXT EDITOR (premium-emoji aware)
# ════════════════════════════════════════════════════════════════
# Callback patterns:
#   tplbtn_edit_<tpl_id>   → ask admin for new button text + optional premium emoji
#   tplbtn_reset_<tpl_id>  → clear customization (use default "🛒 Buy Now")
#
# ConversationHandler state:
TPL_BTN_INPUT = 905


async def tplbtn_edit_callback(update, context):
    """Show button-editor for a specific template's inline button."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()

    tpl_id = q.data.replace("tplbtn_edit_", "")
    try:
        from button_system import (
            template_has_button, get_button_text, get_button_emoji_id,
            supports_button_icons,
        )
    except Exception as e:
        await q.answer(f"❌ Module load error: {e}", show_alert=True)
        return ConversationHandler.END

    if not template_has_button(tpl_id):
        await q.answer("ℹ️ This template has no inline button.", show_alert=True)
        return ConversationHandler.END

    tpl = next((t for t in TEMPLATES if t["id"] == tpl_id), None)
    tpl_name = tpl["name"] if tpl else tpl_id

    cur_text = get_button_text(tpl_id)
    cur_emoji_id = get_button_emoji_id(tpl_id)
    icons_supported = supports_button_icons()

    context.user_data["tplbtn_edit_id"] = tpl_id

    info = (
        f"🔘 *Edit Button Text — {tpl_name}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Current button:* `{cur_text}`\n"
    )
    if cur_emoji_id:
        info += f"*Current premium icon:* `{cur_emoji_id}` ⭐\n"
    info += (
        f"\n📝 Send the new button text now.\n"
        f"_e.g._ `🛒 Shop Now`  or  `💎 Order Karein`\n\n"
        f"⭐ *Premium / Custom Emoji Support:*\n"
    )
    if icons_supported:
        info += (
            f"• Telegram premium emojis ki *icon* button par dikh sakti hai!\n"
            f"• Premium emoji ko message ke *start* mein insert karo (e.g. `[🔥] Buy Now`).\n"
            f"• Bot uska `custom_emoji_id` automatically detect karke icon\n"
            f"  banayega aur baqi text button label me daal dega.\n"
            f"• Aap ko Telegram Premium hai ✅ — yeh feature kaam karega.\n"
        )
    else:
        info += (
            f"⚠️ *Note:* PTB library purani hai (`InlineKeyboardButton.icon_custom_emoji_id`\n"
            f"  parameter detect nahi hua). `requirements.txt` update karke\n"
            f"  `python-telegram-bot >= 22.7` install karein for premium icon support.\n"
            f"• Tab tak: button text plain bheji jayegi (fallback standard emoji dikhega).\n"
        )
    info += (
        f"\nSend `-` to reset to default `🛒 Buy Now`.\n"
        f"Send /cancel to abort."
    )

    kb = [
        [InlineKeyboardButton("♻️ Reset to Default", callback_data=f"tplbtn_reset_{tpl_id}")],
        [InlineKeyboardButton("🔙 Cancel",           callback_data=f"tpl_pick_{tpl_id}")],
    ]
    await _edit(q, info, kb)
    return TPL_BTN_INPUT


async def tplbtn_input_received(update, context):
    """Save the new button text the admin sent.
    If a custom_emoji entity is present, capture the id for the icon."""
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    tpl_id = context.user_data.get("tplbtn_edit_id")
    if not tpl_id:
        return ConversationHandler.END

    try:
        from button_system import (
            set_button, reset_button, extract_custom_emoji,
            supports_button_icons,
        )
    except Exception:
        return ConversationHandler.END

    raw = (update.message.text or "").strip()
    tpl = next((t for t in TEMPLATES if t["id"] == tpl_id), None)
    tpl_name = tpl["name"] if tpl else tpl_id

    # Reset shortcut
    if raw == "-" or raw.lower() == "reset":
        reset_button(tpl_id)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Template", callback_data=f"tpl_pick_{tpl_id}")
        ]])
        await update.message.reply_text(
            f"♻️ *{tpl_name}* button reset to default 🛒 Buy Now",
            parse_mode="Markdown", reply_markup=kb,
        )
        context.user_data.pop("tplbtn_edit_id", None)
        return ConversationHandler.END

    if not raw:
        await update.message.reply_text("⚠️ Khali text save nahi ho sakti. Phir try karein:")
        return TPL_BTN_INPUT

    if len(raw) > 64:
        await update.message.reply_text(
            "⚠️ Button text 64 chars se zyada nahi ho sakta. Phir try karein:"
        )
        return TPL_BTN_INPUT

    # 🎯 Premium-emoji detection
    emoji_id, plain_text = extract_custom_emoji(update.message)

    # If admin sent ONLY a custom emoji, plain_text will be ''. Keep at least
    # a space or default label so the button isn't empty.
    if not plain_text and emoji_id:
        plain_text = "Buy Now"

    set_button(tpl_id, text=plain_text or raw, emoji_id=emoji_id or "")

    icons_ok = supports_button_icons()
    if emoji_id:
        if icons_ok:
            note = (
                f"✅ *{tpl_name} button saved!*\n\n"
                f"📝 Label: `{plain_text or raw}`\n"
                f"⭐ Premium icon: `{emoji_id}` (detected!)\n\n"
                f"_Button ab broadcast me icon + text ke sath jayega._"
            )
        else:
            note = (
                f"✅ *{tpl_name} button saved!*\n\n"
                f"📝 Label: `{plain_text or raw}`\n"
                f"⭐ Premium icon detected (`{emoji_id}`) lekin PTB version\n"
                f"   purani hai. Update karein for icon to render."
            )
    else:
        note = (
            f"✅ *{tpl_name} button saved!*\n\n"
            f"📝 New label: `{plain_text or raw}`\n"
            f"_Premium icon not detected. Aap chahein to message ke shuru me\n"
            f"   premium emoji insert karke dobara save karein._"
        )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧪 Test Broadcast",  callback_data=f"tpl_test_{tpl_id}")],
        [InlineKeyboardButton("🔙 Back to Template", callback_data=f"tpl_pick_{tpl_id}")],
    ])
    await update.message.reply_text(note, parse_mode="Markdown", reply_markup=kb)
    context.user_data.pop("tplbtn_edit_id", None)
    return ConversationHandler.END


async def tplbtn_input_cancel(update, context):
    """Cancel the per-template button-editor conversation.

    Works for BOTH a /cancel command AND a callback-query tap (e.g. when
    user taps the inline "🔙 Cancel" button which goes to tpl_pick_<id>).
    """
    context.user_data.pop("tplbtn_edit_id", None)

    # Case A: triggered by /cancel command → reply with a note
    if update.message:
        await update.message.reply_text(
            "❌ Cancelled.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Templates", callback_data="tpl_panel")
            ]]),
        )
        return ConversationHandler.END

    # Case B: triggered by an inline-button tap → silently end and re-render
    # the template picker so the user lands back where they expected.
    if update.callback_query:
        try:
            await tpl_pick_callback(update, context)
        except Exception:
            try:
                await update.callback_query.answer("Cancelled.")
            except Exception:
                pass
    return ConversationHandler.END


async def tplbtn_reset_callback(update, context):
    """Reset a template's button to default."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True); return
    tpl_id = q.data.replace("tplbtn_reset_", "")
    try:
        from button_system import reset_button
        reset_button(tpl_id)
        await q.answer("♻️ Reset to default!")
    except Exception as e:
        await q.answer(f"❌ {e}", show_alert=True)
        return
    # Re-show the template picker
    context.user_data.pop("tplbtn_edit_id", None)
    # Mimic tpl_pick_callback by re-dispatching
    await tpl_pick_callback(update, context)


# ============================================================
# 📄 ORIGINAL FILE: handlers_screen_editor.py
# ============================================================

# ════════════════════════════════════════════════════════════════
# 🌳 v50: SCREEN-BY-SCREEN EDITOR — Handlers
# ════════════════════════════════════════════════════════════════
# Lets admin drill into any user-side screen and edit its buttons + texts
# (with full premium emoji support) from one unified UI.
#
# Architecture — pure orchestration:
#   - This file ONLY navigates the SCREEN_TREE and hands off to existing
#     handlers (button styler, response editor, manage_one_button screen).
#   - No new DB tables, no new storage. Single source of truth = SCREEN_TREE
#     (in screen_tree.py).
#
# Callback prefix:  se_*   (Screen Editor)
# ════════════════════════════════════════════════════════════════
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID, DEFAULT_RESPONSES
from utils import smart_text_and_mode, escape_md, html_strip_tags, is_html_value
from database import get_response_with_auto_register
# [v77-merge] from screen_tree import (
# [v77-merge] SCREEN_TREE, ROOT_SCREEN,
# [v77-merge] get_screen, is_valid_screen, get_breadcrumb, summary_counts,
# [v77-merge] )
logger = logging.getLogger(__name__)


async def _safe_edit(q, text, **kwargs):
    """🆕 v57: Robust message editor with logging + plain-text fallback so the
    bot NEVER appears 'stuck' to the admin (silent failures fixed)."""
    import logging
    _log = logging.getLogger(__name__)
    send_text, send_mode = smart_text_and_mode(text, kwargs.get("parse_mode", "Markdown"))
    send_kwargs = dict(kwargs); send_kwargs["parse_mode"] = send_mode
    cb = getattr(q, "data", "?")

    # 1) edit_message_text
    try:
        await q.edit_message_text(send_text, **send_kwargs); return
    except Exception as e:
        _log.warning(f"[screen_editor._safe_edit] edit_text failed cb={cb}: {e}")
        if "parse" in str(e).lower():
            kw = {k: v for k, v in send_kwargs.items() if k != "parse_mode"}
            try:
                await q.edit_message_text(send_text, **kw); return
            except Exception: pass

    # 2) edit_message_caption
    try:
        await q.edit_message_caption(caption=send_text, **send_kwargs); return
    except Exception as e:
        if "parse" in str(e).lower():
            kw = {k: v for k, v in send_kwargs.items() if k != "parse_mode"}
            try:
                await q.edit_message_caption(caption=send_text, **kw); return
            except Exception: pass

    # 3) reply_text
    try:
        await q.message.reply_text(send_text, **send_kwargs); return
    except Exception as e:
        if "parse" in str(e).lower():
            kw = {k: v for k, v in send_kwargs.items() if k != "parse_mode"}
            try:
                await q.message.reply_text(send_text, **kw); return
            except Exception: pass

    # 4) 🆕 v57: ABSOLUTE last resort — plain text (strip HTML), so admin
    # always sees something instead of bot freezing silently.
    try:
        from utils import html_strip_tags
        plain = html_strip_tags(send_text)[:3500]
        plain += "\n\n_(⚠️ Display fallback)_"
        kw = {k: v for k, v in send_kwargs.items() if k != "parse_mode"}
        await q.message.reply_text(plain, **kw); return
    except Exception as e:
        _log.error(f"[screen_editor._safe_edit] ALL fallbacks failed cb={cb}: {e}")
        try:
            await q.answer("⚠️ Display error — try /start", show_alert=True)
        except Exception:
            pass


def _is_admin(uid):
    return int(uid) == int(ADMIN_ID)


def _short_preview(s, n=50):
    """Strip HTML and shorten for inline preview labels."""
    if not s:
        return "_(empty)_"
    if is_html_value(s):
        s = html_strip_tags(s)
    s = str(s).replace("\n", " ").replace("`", "").replace("*", "").replace("_", "")
    if len(s) > n:
        s = s[:n] + "…"
    return s


# ════════════════════════════════════════════════════════════════
# 1. ENTRY: from Manage Buttons → 🌳 Screen-by-Screen Editor
# ════════════════════════════════════════════════════════════════

# ── v130: NEW recursive screen editor ─────────────────────────
# Structure (user-specified):
#   Root → list of main screens
#   Tap screen → 2 options: [🎛️ Button Editor] [📂 Sub Menu]
#   Button Editor → per-button: rename / color / premium emoji / hide / reset / size
#   Sub Menu → renders the REAL screen; tapping any button → same 2 options
#   (recursive drill-down)

MAIN_SCREENS = [
    ("main_menu", "🏠 Main Menu"),
    ("shop_screen", "🛒 Shop"),
    ("product_detail_screen", "📦 Product Detail"),
    ("confirm_purchase_screen", "🛒 Confirm Purchase"),
    ("buy_points_screen", "💎 Buy Points"),
    ("buy_points_payment_screen", "💎 Buy Points — Payment"),
    ("my_account_screen", "📊 My Account"),
    ("my_orders_screen", "📜 My Orders"),
    ("my_transactions_screen", "💱 Transactions"),
    ("referral_screen", "🎁 Referrals"),
    ("support_screen", "📞 Support"),
    ("warranty_screen", "🛡️ Warranty"),
    ("reviews_screen", "⭐ Reviews"),
    ("loyalty_screen", "🏆 Loyalty"),
    ("language_screen", "🌐 Language"),
    ("reseller_api_screen", "🔗 Reseller API"),  # 🆕 v161.11
    ("freeclaim_screens", "🎁 Free Claim"),
    ("terms_screen", "📜 Terms"),
    # Payment flows
    ("binance_flow_screen", "🔶 Binance Flow"),
    ("bybit_flow_screen", "🟡 Bybit Flow"),
    ("crypto_usdt_flow_screen", "🪙 Crypto USDT"),
    ("easypaisa_flow_screen", "📱 EasyPaisa Flow"),
    ("jazzcash_flow_screen", "📱 JazzCash Flow"),
    ("order_created_screen", "📜 Order Created/Status"),
    ("error_messages_screen", "❌ Error Messages"),
]

# Map a registry button id → the screen it opens (for Sub Menu recursion).
BTN_TARGET_SCREEN = {
    "main_shop": "shop_screen", "main_points": "buy_points_screen",
    "main_account": "my_account_screen", "main_orders": "my_orders_screen",
    "main_transactions": "my_transactions_screen", "main_support": "support_screen",
    "main_referral": "referral_screen", "main_price_list": "shop_screen",
    "main_loyalty": "loyalty_screen", "main_language": "language_screen",
    "main_reviews": "reviews_screen", "main_warranty": "warranty_screen",
    "main_reseller_api": "reseller_api_screen",  # 🆕 v161.11
    "pay_binance": "binance_flow_screen", "pay_usdt_trc20": "crypto_usdt_flow_screen",
    "pay_usdt_bep20": "crypto_usdt_flow_screen", "pay_bybit_pay": "bybit_flow_screen",
    "pay_bybit_usdt_trc20": "bybit_flow_screen", "pay_bybit_usdt_bep20": "bybit_flow_screen",
    "pay_easypaisa": "easypaisa_flow_screen", "pay_jazzcash": "jazzcash_flow_screen",
    "pay_pts": "buy_points_payment_screen",
}


async def se_root_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📋 Screen Editor root — list of main screens."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    await q.answer()
    header = (
        "📋 *Screen-by-Screen Editor*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Pick a screen. Each screen gives you:\n"
        "🎛️ *Button Editor* — rename / color / premium emoji / hide / reset\n"
        "📂 *Sub Menu* — see the real screen; tap any button to keep editing\n\n"
        "_Tap a screen below:_"
    )
    kb = []
    for sid, label in MAIN_SCREENS:
        kb.append([InlineKeyboardButton(label, callback_data=f"se_open_{sid}")])
    kb.append([InlineKeyboardButton("🔙 Back to Manage Buttons", callback_data="admin_buttons")])
    await _safe_edit(q, header, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def se_open_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Screen panel — [🎛️ Button Editor] [📂 Sub Menu] + editable texts."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    await q.answer()
    sid = q.data.replace("se_open_", "", 1)
    if not is_valid_screen(sid):
        await _safe_edit(q, f"❌ Unknown screen: `{sid}`",
                         parse_mode="Markdown",
                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                             "📋 Back to Screens", callback_data="se_root")]]))
        return
    # Layout screens open their picker directly
    if sid.endswith("_layouts"):
        _lm = {
            "bybit_pay_layouts": "bybit_pay",
            "bybit_usdt_flow_layouts": "bybit_usdt_flow",
            "bybit_uid_layouts": "bybit_uid",
            "binance_pay_layouts": "binance_pay",
            "binance_usdt_layouts": "binance_usdt",
            "easypaisa_layouts": "easypaisa",
            "jazzcash_layouts": "jazzcash",
            "order_flow_layouts": "order_flow",
        }
        if sid in _lm:
            await _show_screen_layouts(q, _lm[sid], context)
            return
    await _show_screen_editor(q, sid, context)


async def _show_screen_editor(q, sid, context):
    """Render the 2-option panel for a screen."""
    node = get_screen(sid) or {}
    icon = node.get("icon", "📄")
    title = node.get("title", sid)
    desc = node.get("description", "")
    n_btns = len(node.get("buttons", []) or [])
    n_texts = len(node.get("texts", []) or [])
    text = (
        f"{icon} *{escape_md(title)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + (f"_{escape_md(desc)}_\n\n" if desc else "\n")
        + f"🎛️ Buttons: *{n_btns}*  ·  📝 Texts: *{n_texts}*\n\n"
        f"_Choose what you want to edit:_"
    )
    kb = [
        [InlineKeyboardButton("🎛️ Button Editor", callback_data=f"se_btns_{sid}"),
         InlineKeyboardButton("📂 Sub Menu", callback_data=f"se_sub_{sid}")],
    ]
    # 🎨 v130: keep readymade layouts reachable from flow screens (children)
    for ch in (node.get("children", []) or []):
        if str(ch).endswith("_layouts") and is_valid_screen(ch):
            kb.insert(0, [InlineKeyboardButton("🎨 Readymade Layouts", callback_data=f"se_open_{ch}")])
            break
    kb.append([InlineKeyboardButton("📋 Back to Screens", callback_data="se_root")])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════════════════════════
# 2. Render a screen node
# ════════════════════════════════════════════════════════════════

async def _show_screen(q, sid, context):
    node = get_screen(sid)
    if not node:
        await _safe_edit(q, "❌ Screen not found",
                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                             "🌳 Back to Tree", callback_data="se_root")]]))
        return
    # 🔧 v119/v120: readymade-layouts pickers (special render)
    _layout_map = {
        "bybit_pay_layouts": "bybit_pay",
        "bybit_usdt_layouts": "bybit_usdt",
        "binance_pay_layouts": "binance_pay",
        "binance_usdt_layouts": "binance_usdt",
        "easypaisa_layouts": "easypaisa",
        "jazzcash_layouts": "jazzcash",
        "order_flow_layouts": "order_flow",
        "bybit_uid_layouts": "bybit_uid",
        "bybit_usdt_flow_layouts": "bybit_usdt_flow",
    }
    if sid in _layout_map:
        await _show_screen_layouts(q, _layout_map[sid], context)
        return
    if sid == "bybit_pay_layouts":
        await _show_bybit_pay_layouts(q, sid, context)
        return

    icon = node.get("icon", "📄")
    title = node.get("title", sid)
    desc = node.get("description", "")
    texts = node.get("texts", []) or []
    buttons = node.get("buttons", []) or []
    children = node.get("children", []) or []

    # Build breadcrumb header
    crumbs = get_breadcrumb(sid)
    crumb_line = " ⏵ ".join(escape_md(t) for _, t in crumbs) if crumbs else escape_md(title)

    n_texts, n_buttons, n_children = summary_counts(sid)
    header = (
        f"🌳 *Screen Editor*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 _{crumb_line}_\n\n"
        f"{icon} *{escape_md(title)}*\n"
        + (f"_{escape_md(desc)}_\n\n" if desc else "\n")
        + f"📝 Editable texts: *{n_texts}*\n"
        f"🎛️ Buttons on this screen: *{n_buttons}*\n"
        f"➡️ Drill-down screens: *{n_children}*\n\n"
        "_Tap any item below to edit it._"
    )

    kb = []

    # ── A. Texts section ──
    if texts:
        kb.append([InlineKeyboardButton(f"━━━━ 📝 Texts ({len(texts)}) ━━━━",
                                        callback_data="se_noop")])
        for resp_key, friendly in texts:
            cur = get_response_with_auto_register(
                resp_key, DEFAULT_RESPONSES.get(resp_key, ""))
            preview = _short_preview(cur, 35)
            # Truncate the label to fit Telegram button width
            lbl = f"{friendly}  ·  {preview}"
            if len(lbl) > 64:
                lbl = lbl[:61] + "…"
            kb.append([InlineKeyboardButton(lbl, callback_data=f"se_edittext_{resp_key}")])

    # ── B. Buttons section ──
    if buttons:
        kb.append([InlineKeyboardButton(f"━━━━ 🎛️ Buttons ({len(buttons)}) ━━━━",
                                        callback_data="se_noop")])
        for b in buttons:
            bid = b.get("id")
            kind = b.get("kind", "registry")
            label = _button_friendly_label(bid, kind)
            cb = _button_callback_for(bid, kind)
            if cb:
                lbl_display = label
                if len(lbl_display) > 64:
                    lbl_display = lbl_display[:61] + "…"
                kb.append([InlineKeyboardButton(lbl_display, callback_data=cb)])

    # ── C. Drill-down children ──
    if children:
        kb.append([InlineKeyboardButton(f"━━━━ ➡️ Drill Into ({len(children)}) ━━━━",
                                        callback_data="se_noop")])
        for ch_id in children:
            ch = SCREEN_TREE.get(ch_id, {})
            ch_icon = ch.get("icon", "📄")
            ch_title = ch.get("title", ch_id)
            kb.append([InlineKeyboardButton(
                f"{ch_icon} {ch_title}  ⏵",
                callback_data=f"se_open_{ch_id}")])

    # ── D. Footer (parent / root) ──
    kb.append([InlineKeyboardButton("━━━━━━━━━━━━━━", callback_data="se_noop")])
    # Parent (if not root)
    parent_id = _parent_of(sid)
    if parent_id:
        kb.append([
            InlineKeyboardButton("⬆️ Up One Level",  callback_data=f"se_open_{parent_id}"),
            InlineKeyboardButton("🌳 Root",          callback_data="se_root"),
        ])
    kb.append([InlineKeyboardButton("🔙 Back to Manage Buttons",
                                    callback_data="admin_buttons")])

    await _safe_edit(q, header, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


def _parent_of(sid):
    """Find the parent of a screen by scanning children lists. Returns None for root."""
    if sid == ROOT_SCREEN:
        return None
    for pid, node in SCREEN_TREE.items():
        if sid in (node.get("children") or []):
            return pid
    return None


# ════════════════════════════════════════════════════════════════
# 3. Helpers for displaying buttons in the screen view
# ════════════════════════════════════════════════════════════════

def _button_friendly_label(bid, kind):
    """Pretty label showing current button text + any styling indicators."""
    try:
        if kind == "registry":
            from button_system import BUTTONS, is_button_hidden
            from button_system import get_button_text as _gbt
            info = BUTTONS.get(bid, {})
            default_med = info.get("medium", bid)
            # Custom rename text overrides default
            custom_med = ""
            try:
                custom_med = _gbt(f"{bid}_medium", "") or ""
            except Exception:
                pass
            label_core = custom_med or default_med
            hidden = ""
            try:
                if is_button_hidden(bid):
                    hidden = " 🔴"
            except Exception:
                pass
            return f"🎛️ {label_core}{hidden}"

        if kind == "dynamic":
            # Use sample label that the existing button styler resolves
            try:
                from handlers_buttons import _sample_label_for
                return f"🎛️ {_sample_label_for(bid)}"
            except Exception:
                return f"🎛️ {bid}"

        if kind == "fj_verify":
            try:
                from database import get_fj_verify_button
                vb = get_fj_verify_button()
                lbl = vb.get("label") or "✅ I Joined — Verify"
                return f"✅ {lbl}"
            except Exception:
                return "✅ Verify Button"
        if kind == "fj_targets":
            try:
                from database import list_fj_targets
                n = len(list_fj_targets(enabled_only=True))
                return f"🔗 Join Targets ({n})"
            except Exception:
                return "🔗 Join Targets"

        return f"🎛️ {bid}"
    except Exception:
        return f"🎛️ {bid}"


def _button_callback_for(bid, kind):
    """Return the callback that opens THIS button's edit screen.
    Registry → existing 'mbedit_<bid>' (full panel: rename / color / hide / style)
    Dynamic  → existing 'bs_edit_<key>' (styler: size / align / pad)
    🆕 v141: force-join kinds → dedicated editors (verify button / targets list)
    """
    if kind == "registry":
        return f"mbedit_{bid}"
    if kind == "dynamic":
        return f"bs_edit_{bid}"
    if kind == "fj_verify":
        return "fj_vbtn"          # ✅ Verify-Button Editor (rename/color/premium emoji)
    if kind == "fj_targets":
        return "fj_panel"         # 🔗 Force Join Setup (all targets, add/delete)
    return None


# ════════════════════════════════════════════════════════════════
# 4. Text editor — taps "📝 ..." entry → reuse existing response editor
# ════════════════════════════════════════════════════════════════

async def se_edittext_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the response editor for a key, but with a back-link to the
    originating screen editor node so admin returns to where they came from.

    Callback: se_edittext_<response_key>
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    await q.answer()

    resp_key = q.data.replace("se_edittext_", "", 1)
    # Find which screen this key belongs to (so we can offer a smart back link)
    parent_sid = None
    for sid, node in SCREEN_TREE.items():
        for k, _lbl in node.get("texts", []):
            if k == resp_key:
                parent_sid = sid; break
        if parent_sid: break

    # Show current value + Edit button (taps into existing flow)
    cur = get_response_with_auto_register(
        resp_key, DEFAULT_RESPONSES.get(resp_key, ""))

    # 🐞 v58 FIX: When the raw value contains Markdown special chars (e.g.
    # `{qty_text}` has an underscore, or `*{product}*` has asterisks), the
    # OLD code embedded raw text inside a Markdown header → unbalanced * or _
    # caused Telegram "Can't parse entities" error → bot appeared stuck.
    #
    # NEW: Force HTML mode AND wrap the preview value inside <pre>...</pre>
    # (Telegram <pre> blocks render any chars literally — no markdown parsing).
    # Premium emojis are still rendered above the preview as a separate line.
    import html as _hlib
    from utils import is_html_value, contains_premium_markup, strip_html_prefix, html_strip_tags

    # Show preview using HTML-aware rendering so premium emojis render in preview
    if is_html_value(cur) or contains_premium_markup(cur):
        # Premium emoji content → render HTML form (bare, NOT inside <pre>)
        preview_text, _ = smart_text_and_mode(cur, "HTML")
        preview_is_html_rendered = True
    else:
        # Plain text → keep literal (will go inside <pre> for safety)
        preview_text = cur or "_(empty)_"
        preview_is_html_rendered = False

    # Truncate displayed value to keep message short
    if len(preview_text) > 1200:
        preview_text = preview_text[:1200] + "\n\n… (truncated for preview)"

    # Find friendly label
    friendly = resp_key
    if parent_sid:
        for k, lbl in SCREEN_TREE[parent_sid].get("texts", []):
            if k == resp_key:
                friendly = lbl; break

    # Build the edit prompt — set the same context flags the existing
    # response-editor MessageHandler watches for.
    context.user_data['erk'] = resp_key  # 🔁 existing flag used by response_value_received
    context.user_data['se_back_sid'] = parent_sid or ROOT_SCREEN  # for our smart back

    back_cb = f"se_open_{parent_sid}" if parent_sid else "se_root"

    # 🆕 v58: Always use HTML mode. Wrap the preview body inside <pre> when
    # it's plain text — this makes Telegram render the raw value LITERALLY
    # (no markdown parsing) so unbalanced *, _, ` from `{qty_text}` etc. can't
    # break the message and freeze the bot.
    if preview_is_html_rendered:
        # Premium-emoji content — render inline so emojis show
        preview_block = preview_text
    else:
        # Plain text — escape HTML special chars + wrap in <pre> for safety
        preview_block = f"<pre>{_hlib.escape(preview_text)}</pre>"

    header = (
        f"📝 <b>Edit Text:</b> <code>{_hlib.escape(friendly)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Key: <code>{_hlib.escape(resp_key)}</code>\n\n"
        f"<b>Current value (preview):</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{preview_block}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📥 <b>Send the new text now.</b>\n"
        f"⭐ Premium emojis supported — type/insert them normally.\n"
        f"✨ Markdown formatting (<code>*bold*</code> <code>_italic_</code> <code>`code`</code>) supported.\n\n"
        f"Or tap <b>Cancel</b> to keep the current text."
    )
    send_mode = "HTML"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👁️ Send Live Preview to me",
                              callback_data=f"se_preview_{resp_key}")],
        [InlineKeyboardButton("♻️ Reset to Default",
                              callback_data=f"se_reset_{resp_key}")],
        [InlineKeyboardButton("❌ Cancel", callback_data=back_cb)],
    ])
    await _safe_edit(q, header, parse_mode=send_mode, reply_markup=kb)


# ════════════════════════════════════════════════════════════════
# 5. Text input handler — admin replies with new text
#    Hook into bot.py::handle_text via the EXISTING 'erk' flag.
#    Our addition: after save, redirect back to the screen editor.
# ════════════════════════════════════════════════════════════════

async def se_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called from bot.py::handle_text() when 'erk' flag is set AND we have
    'se_back_sid' (i.e. user entered text edit via screen editor, not the
    old response editor). Saves the text AND returns to screen editor.

    Returns True if it handled the message.
    """
    if not _is_admin(update.effective_user.id):
        return False
    if not context.user_data.get("se_back_sid"):
        # Not our flow — let the existing response_value_received handle it
        return False
    erk = context.user_data.get("erk")
    if not erk:
        return False

    # Capture with premium emoji preservation (v48 helper)
    from utils import capture_user_text, safe_display
    val = capture_user_text(update.message) or ""

    # Save via existing API
    try:
        from database import set_response, log_change, get_response
        old = get_response(erk, DEFAULT_RESPONSES.get(erk, ""))
        log_change("response", erk, old, val, f"Response: {erk} (via Screen Editor)")
        set_response(erk, val)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Save failed: `{e}`",
                                        parse_mode="Markdown")
        return True

    # Build confirmation echo (premium emoji aware)
    # 🆕 v53: pass message so premium emoji entities (even where fallback char is
    # plain text) are properly rendered in the echo.
    disp, disp_mode = safe_display(val, preferred_mode="Markdown", message=update.message)
    back_sid = context.user_data.pop("se_back_sid", ROOT_SCREEN)
    context.user_data.pop("erk", None)

    back_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👁️ Live Preview",
                              callback_data=f"se_preview_{erk}")],
        [InlineKeyboardButton(f"🔙 Back to Screen",
                              callback_data=f"se_open_{back_sid}")],
        [InlineKeyboardButton("🌳 Screen Tree Root",
                              callback_data="se_root")],
    ])

    if disp_mode == "HTML":
        msg = (
            f"✅ <b>Text saved!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 Key: <code>{erk}</code>\n\n"
            f"<b>Saved value (preview):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{disp}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        msg = (
            f"✅ *Text saved!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 Key: `{erk}`\n\n"
            f"*Saved value (preview):*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{disp}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    await update.message.reply_text(msg, parse_mode=disp_mode, reply_markup=back_kb)
    return True


# ════════════════════════════════════════════════════════════════
# 6. Live preview — admin gets the saved text sent to them as a real message
# ════════════════════════════════════════════════════════════════

async def se_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    await q.answer("📤 Sending preview...", show_alert=False)
    erk = q.data.replace("se_preview_", "", 1)
    val = get_response_with_auto_register(erk, DEFAULT_RESPONSES.get(erk, ""))

    send_text, send_mode = smart_text_and_mode(val or "_(empty)_", "Markdown")
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"👁️ *Live preview of* `{erk}` *as users will see it:*\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown")
        await context.bot.send_message(
            ADMIN_ID, send_text, parse_mode=send_mode)
    except Exception as e:
        try:
            # Parse-mode fallback
            await context.bot.send_message(ADMIN_ID, send_text)
        except Exception as e2:
            await context.bot.send_message(
                ADMIN_ID, f"⚠️ Preview failed: `{e2}`",
                parse_mode="Markdown")


# ════════════════════════════════════════════════════════════════
# 7. Reset to default — restore the value from DEFAULT_RESPONSES
# ════════════════════════════════════════════════════════════════

async def se_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    erk = q.data.replace("se_reset_", "", 1)
    default = DEFAULT_RESPONSES.get(erk, "")
    try:
        from database import set_response, log_change, get_response
        old = get_response(erk, "")
        log_change("response", erk, old, default,
                   f"Response RESET to default: {erk} (via Screen Editor)")
        set_response(erk, default)
    except Exception as e:
        await q.answer(f"⚠️ {e}", show_alert=True); return
    await q.answer("♻️ Reset to default", show_alert=False)

    back_sid = context.user_data.get("se_back_sid")
    # Clean up the edit flags so we don't accidentally capture next message
    context.user_data.pop("se_back_sid", None)
    context.user_data.pop("erk", None)

    if back_sid and is_valid_screen(back_sid):
        await _show_screen(q, back_sid, context)
    else:
        await _show_screen(q, ROOT_SCREEN, context)


# ════════════════════════════════════════════════════════════════
# 8. Noop callback (for section headers)
# ════════════════════════════════════════════════════════════════

async def se_noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except Exception:
        pass


# ============================================================
# 📄 ORIGINAL FILE: screen_tree.py
# ============================================================

# ════════════════════════════════════════════════════════════════
# 🌳 v50: SCREEN-BY-SCREEN EDITOR TREE
# ════════════════════════════════════════════════════════════════
# This module defines the USER-SIDE screen hierarchy.
# Each "screen node" has:
#   - id        : unique string id (used in callback_data)
#   - title     : display title in admin panel
#   - icon      : emoji prefix for nav
#   - buttons   : list of button registry IDs OR dynamic styler keys
#                 that appear on this screen
#   - texts     : list of (response_key, friendly_label) for editable text
#   - children  : list of child screen ids (drill-down)
#
# Single source of truth — no DB tables created. All edits go via existing:
#   - button_registry / button_styler / template_buttons  (for buttons)
#   - bot_responses table via get_response_with_auto_register (for text)
# ════════════════════════════════════════════════════════════════

# Each node format:
#   "screen_id": {
#       "icon": "🏠",
#       "title": "Main Menu",
#       "buttons": [
#           # Each entry is a dict:
#           #   {"id": "main_shop", "kind": "registry"}      → BUTTONS["main_shop"]
#           #   {"id": "prod_buy",  "kind": "dynamic"}       → button_styler dynamic key
#           #   {"id": "fc_btn_5",  "kind": "perproduct"}    → already covered elsewhere
#       ],
#       "texts": [
#           # Each entry: (response_key, friendly_label)
#           ("welcome", "Welcome Text"),
#       ],
#       "children": ["shop_screen", "my_account_screen", ...],
#   }

SCREEN_TREE = {
    # ═══════════════════════════════════════════════════════════
    # ROOT — Main Menu
    # ═══════════════════════════════════════════════════════════
    "main_menu": {
        "icon": "🏠",
        "title": "Main Menu",
        "description": "The first screen users see when they /start the bot",
        "texts": [
            ("welcome", "📝 Welcome Text"),
            ("cancelled_message", "❌ 'Cancelled' Message"),
        ],
        "buttons": [
            {"id": "main_shop",         "kind": "registry"},
            {"id": "main_points",       "kind": "registry"},
            {"id": "main_account",      "kind": "registry"},
            {"id": "main_orders",       "kind": "registry"},
            {"id": "main_transactions", "kind": "registry"},
            {"id": "main_referral",     "kind": "registry"},
            {"id": "main_support",      "kind": "registry"},
            {"id": "main_warranty",     "kind": "registry"},
            {"id": "main_reviews",      "kind": "registry"},
            {"id": "main_loyalty",      "kind": "registry"},
            {"id": "main_language",     "kind": "registry"},
            # 🆕 v161.11: Reseller API button (editable in Screen Editor)
            {"id": "main_reseller_api", "kind": "registry"},
        ],
        "children": [
            "force_join_screen",
            "shop_screen",
            "buy_points_screen",
            "my_account_screen",
            "my_orders_screen",
            "my_transactions_screen",
            "referral_screen",
            "support_screen",
            "warranty_screen",
            "reviews_screen",
            "loyalty_screen",
            "language_screen",
            "reseller_api_screen",   # 🆕 v161.11
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # 🆕 v161.11: RESELLER API SCREEN (editable texts in Screen Editor)
    "reseller_api_screen": {
        "icon": "🔗",
        "title": "Reseller API",
        "description": "User taps '🔗 Reseller API Key' from main menu",
        "texts": [
            ("reseller_api_landing",    "📝 Landing (no key yet)"),
            ("reseller_api_generated",  "✅ Key Generated"),
            ("reseller_api_panel",      "🔗 API Access Panel"),
            ("reseller_api_fullkey",    "🔑 Show Full Key"),
            ("reseller_api_regenerate", "🔄 Regenerate"),
        ],
        "buttons": [
            {"id": "main_reseller_api",      "kind": "registry"},
            # 🆕 v161.13: full reseller API flow buttons (editable)
            {"id": "reseller_api_generate_btn", "kind": "registry"},
            {"id": "reseller_api_show_btn",     "kind": "registry"},
            {"id": "reseller_api_regenerate_btn", "kind": "registry"},
            {"id": "reseller_api_docs_btn",     "kind": "registry"},
        ],
        "children": [],
    },

    # ═══════════════════════════════════════════════════════════
    # 🛒 SHOP SCREEN
    # ═══════════════════════════════════════════════════════════
    "force_join_screen": {
        "icon": "🔗",
        "title": "Force Join (Join Message + Verify)",
        "description": "Join message text, Verified response, and the Verify button users tap after joining",
        "texts": [
            ("fj_message", "📝 Join Message"),
            ("fj_verified_done", "📝 Verified Response"),
        ],
        "buttons": [
            {"id": "fj_verify", "kind": "fj_verify"},
            {"id": "fj_targets", "kind": "fj_targets"},
        ],
        "children": [],
    },
    "shop_screen": {
        "icon": "🛒",
        "title": "Shop / Product List",
        "description": "The screen with categories + paginated product list",
        "texts": [
            ("shop_title",            "📝 Shop Title"),
            ("shop_categories_title", "📝 Categories Title"),
            ("no_products",           "📝 'No Products' Message"),
        ],
        "buttons": [
            {"id": "shop_product",        "kind": "dynamic"},
            {"id": "shop_category",       "kind": "dynamic"},
            # 🆕 v52: pagination + home + categories-back are now registry buttons
            # so admin can rename/recolor/add premium emoji icons (not just size/pad).
            {"id": "nav_shop_prev_page",  "kind": "registry"},
            {"id": "nav_shop_next_page",  "kind": "registry"},
            {"id": "nav_shop_home",       "kind": "registry"},
            {"id": "nav_categories_back", "kind": "registry"},
            {"id": "shop_buy_points",     "kind": "dynamic"},
            {"id": "shop_view_all",       "kind": "dynamic"},
        ],
        "children": [
            "product_detail_screen",
            "freeclaim_screens",
        ],
    },

    # ═══════════════════════════════════════════════════════════
    # 📦 PRODUCT DETAIL
    # ═══════════════════════════════════════════════════════════
    "product_detail_screen": {
        "icon": "📦",
        "title": "Product Detail Page",
        "description": "Shown when user taps a product name",
        "texts": [
            ("product_detail", "📝 Product Detail Text"),
            ("out_of_stock",   "📝 'Out of Stock' Message"),
        ],
        "buttons": [
            {"id": "prod_buy",            "kind": "dynamic"},
            {"id": "prod_buyx",           "kind": "dynamic"},
            {"id": "prod_review",         "kind": "dynamic"},
            # 🆕 v52: Back-to-Shop + Home nav buttons are now registry (full editor)
            {"id": "nav_prod_back_shop",  "kind": "registry"},
            {"id": "nav_prod_home",       "kind": "registry"},
        ],
        "children": [
            "confirm_purchase_screen",
            "bulk_purchase_screen",
            "carousel_screen",
        ],
    },

    "carousel_screen": {
        "icon": "🎠",
        "title": "Product Carousel (Navigation)",
        "description": "Prev/Next product navigation buttons",
        "texts": [],
        "buttons": [
            # 🆕 v52: Prev/Next now registry buttons (full editor)
            {"id": "nav_carousel_prev", "kind": "registry"},
            {"id": "nav_carousel_next", "kind": "registry"},
            {"id": "cnav_buy",          "kind": "dynamic"},
            {"id": "cnav_list",         "kind": "dynamic"},
        ],
        "children": [],
    },

    # ═══════════════════════════════════════════════════════════
    # 🛒 CONFIRM PURCHASE → PAYMENT METHODS
    # ═══════════════════════════════════════════════════════════
    "confirm_purchase_screen": {
        "icon": "🛒",
        "title": "Confirm Purchase (Pick Payment)",
        "description": "Shown when user taps 'Buy Now'. Lists payment methods.",
        "texts": [
            ("confirm_purchase", "📝 Confirm Purchase Text"),
        ],
        "buttons": [
            # 🆕 v57: 'Pay with Points' is now editable (was hardcoded before)
            {"id": "pay_pts",         "kind": "registry"},
            {"id": "pay_group_binance", "kind": "registry"},
            {"id": "pay_group_bybit",   "kind": "registry"},
            {"id": "pay_binance",     "kind": "registry"},
            {"id": "pay_easypaisa",   "kind": "registry"},
            {"id": "pay_jazzcash",    "kind": "registry"},
            {"id": "pay_method",      "kind": "dynamic"},
            # 🆕 v52: Cancel button on payment picker screen — editable
            {"id": "nav_pay_cancel",  "kind": "registry"},
        ],
        "children": [
            "binance_flow_screen",
            "bybit_flow_screen",
            "crypto_usdt_flow_screen",
            "easypaisa_flow_screen",
            "jazzcash_flow_screen",
            "order_created_screen",
        ],
    },

    "bulk_purchase_screen": {
        "icon": "🛒×",
        "title": "Bulk Purchase",
        "description": "Shown when user taps 'Buy Multiple'",
        "texts": [
            ("confirm_bulk_purchase", "📝 Bulk Purchase Prompt"),
            ("bulk_confirmed",        "📝 Bulk Confirmed Text"),
        ],
        "buttons": [],
        "children": ["confirm_purchase_screen"],
    },

    # ═══════════════════════════════════════════════════════════
    # 🔶 BINANCE FLOW
    # ═══════════════════════════════════════════════════════════
    "binance_flow_screen": {
        "icon": "🔶",
        "title": "Binance Payment Flow",
        "description": "All text shown during Binance Pay verification",
        "texts": [
            ("payment_binance_menu_text", "📝 Binance Method Menu"),
            ("payment_binance_pay_orderid", "📝 Binance Pay Checkout"),
            ("payment_binance_usdt", "📝 Binance USDT Checkout"),
                                    ("binance_instructions",     "📝 Important Note"),
                                    ("payment_verified_points",  "📝 Verified — Points Added"),
            ("payment_verified_product", "📝 Verified — Product Delivered"),
                    ],
        "buttons": [
            {"id": "pay_binance", "kind": "registry"},
            {"id": "pay_usdt_bep20", "kind": "registry"},
            {"id": "pay_usdt_trc20", "kind": "registry"},
            # 🆕 v144.1: Binance flow editable buttons (mirror of Bybit)
            {"id": "pay_copy_binance_payid", "kind": "registry"},
            {"id": "pay_copy_usdt_address", "kind": "registry"},
            {"id": "pay_cancel_payment", "kind": "registry"},
        ],
        "children": ["error_messages_screen", "binance_pay_layouts", "binance_usdt_layouts"],
    },

    "binance_pay_layouts": {
        "icon": "🎨",
        "title": "Binance Pay Readymade Layouts",
        "description": "Apply a readymade Binance Pay checkout layout (preview first).",
        "texts": [],
        "buttons": [],
        "children": [],
    },
    "binance_usdt_layouts": {
        "icon": "🎨",
        "title": "Binance USDT Readymade Layouts",
        "description": "Apply a readymade Binance USDT checkout layout (preview first).",
        "texts": [],
        "buttons": [],
        "children": [],
    },

    "bybit_flow_screen": {
        "icon": "🟡",
        "title": "Bybit Payment Flow",
        "description": "Bybit Pay and Bybit USDT payment screens",
        "texts": [
            ("payment_bybit_menu_text", "📝 Bybit Method Menu"),
            ("payment_bybit_pay", "📝 Bybit Pay Checkout"),
            # 🔧 v119: per-order Reference ID line (editable)
            ("payment_bybit_pay_reference", "📝 Bybit Pay Reference ID Line"),
            ("payment_bybit_usdt", "📝 Bybit USDT Checkout"),
            ("payment_not_found_txid", "📝 Payment Not Found / Retry Text"),
            # 🔧 v122: new UID-flow screens
            ("bybit_warning_text", "📝 Warning — Decimals (Screen 1)"),
            ("bybit_uid_prompt", "📝 Enter Bybit UID (Screen 2)"),
            ("bybit_uid_invalid", "📝 Invalid UID"),
            ("bybit_amount_prompt", "📝 Enter Deposit Amount (Screen 3)"),
            ("bybit_amount_invalid", "📝 Invalid Amount"),
            ("bybit_deposit_instructions", "📝 Deposit Instructions (Screen 4)"),
            ("bybit_cancelled", "📝 Flow Cancelled"),
            # 🔧 v123: Bybit USDT flow screens
            ("bybit_usdt_warning_text", "📝 USDT Warning (Screen 1)"),
            ("bybit_usdt_amount_prompt", "📝 USDT Amount Prompt (Screen 2)"),
            ("bybit_usdt_amount_invalid", "📝 USDT Invalid Amount"),
            ("bybit_usdt_deposit_instructions", "📝 USDT Deposit Instructions (Screen 3)"),
                    ],
        "buttons": [
            {"id": "pay_bybit_pay", "kind": "registry"},
            # 🔧 v119: editable copy buttons (rename + premium emoji + color)
            {"id": "pay_copy_reference", "kind": "registry"},
            {"id": "pay_copy_bybitpay", "kind": "registry"},
            {"id": "pay_bybit_usdt_bep20", "kind": "registry"},
            {"id": "pay_bybit_usdt_trc20", "kind": "registry"},
            # 🔧 v122: UID-flow buttons
            {"id": "bybit_continue", "kind": "registry"},
            {"id": "bybit_cancel_flow", "kind": "registry"},
            {"id": "bybit_copy_amount", "kind": "registry"},
            {"id": "bybit_copy_uid", "kind": "registry"},
            {"id": "bybit_check_payment", "kind": "registry"},
            {"id": "bybit_cancel_payment", "kind": "registry"},
            # 🔧 v123: USDT flow buttons
            {"id": "bybit_copy_address", "kind": "registry"},
        ],
        "children": ["error_messages_screen", "bybit_pay_layouts", "bybit_usdt_layouts",
                     "bybit_warning_screen", "bybit_uid_screen", "bybit_amount_screen",
                     "bybit_deposit_screen", "bybit_uid_layouts",
                     "bybit_usdt_warning_screen", "bybit_usdt_amount_screen",
                     "bybit_usdt_deposit_screen", "bybit_usdt_flow_layouts"],
    },

    # 🔧 v123: Bybit USDT flow screen nodes
    "bybit_usdt_warning_screen": {
        "icon": "⚠️",
        "title": "USDT Warning (Screen 1)",
        "description": "Decimals + fee warning before USDT deposit",
        "texts": [("bybit_usdt_warning_text", "📝 Warning Text")],
        "buttons": [
            {"id": "bybit_continue", "kind": "registry"},
            {"id": "bybit_cancel_flow", "kind": "registry"},
        ],
        "children": [],
    },
    "bybit_usdt_amount_screen": {
        "icon": "🟡",
        "title": "USDT Amount Prompt (Screen 2)",
        "description": "Bot asks deposit amount (min $1)",
        "texts": [("bybit_usdt_amount_prompt", "📝 Amount Prompt"),
                  ("bybit_usdt_amount_invalid", "📝 Invalid Amount")],
        "buttons": [{"id": "bybit_cancel_flow", "kind": "registry"}],
        "children": [],
    },
    "bybit_usdt_deposit_screen": {
        "icon": "💸",
        "title": "USDT Deposit Instructions (Screen 3)",
        "description": "Address + unique amount + copy/check/cancel buttons",
        "texts": [("bybit_usdt_deposit_instructions", "📝 Deposit Instructions")],
        "buttons": [
            {"id": "bybit_copy_address", "kind": "registry"},
            {"id": "bybit_copy_amount", "kind": "registry"},
            {"id": "bybit_check_payment", "kind": "registry"},
            {"id": "bybit_cancel_payment", "kind": "registry"},
        ],
        "children": [],
    },
    "bybit_usdt_flow_layouts": {
        "icon": "🎨",
        "title": "USDT Deposit Readymade Layouts",
        "description": "Apply a readymade Bybit USDT deposit layout (preview first).",
        "texts": [],
        "buttons": [],
        "children": [],
    },

    # 🔧 v122: UID-flow screen nodes
    "bybit_warning_screen": {
        "icon": "⚠️",
        "title": "Bybit Warning (Screen 1)",
        "description": "Decimals warning shown first. Buttons: Continue / Cancel",
        "texts": [("bybit_warning_text", "📝 Warning Text")],
        "buttons": [
            {"id": "bybit_continue", "kind": "registry"},
            {"id": "bybit_cancel_flow", "kind": "registry"},
        ],
        "children": [],
    },
    "bybit_uid_screen": {
        "icon": "🆔",
        "title": "Enter Bybit UID (Screen 2)",
        "description": "Bot asks the customer for their Bybit UID",
        "texts": [("bybit_uid_prompt", "📝 UID Prompt"), ("bybit_uid_invalid", "📝 Invalid UID")],
        "buttons": [{"id": "bybit_cancel_flow", "kind": "registry"}],
        "children": [],
    },
    "bybit_amount_screen": {
        "icon": "🟡",
        "title": "Enter Deposit Amount (Screen 3)",
        "description": "Bot asks how much to deposit (min $1)",
        "texts": [("bybit_amount_prompt", "📝 Amount Prompt"), ("bybit_amount_invalid", "📝 Invalid Amount")],
        "buttons": [{"id": "bybit_cancel_flow", "kind": "registry"}],
        "children": [],
    },
    "bybit_deposit_screen": {
        "icon": "💸",
        "title": "Deposit Instructions (Screen 4)",
        "description": "Unique amount + reference + copy/check/cancel buttons",
        "texts": [("bybit_deposit_instructions", "📝 Deposit Instructions")],
        "buttons": [
            {"id": "bybit_copy_amount", "kind": "registry"},
            {"id": "bybit_copy_uid", "kind": "registry"},
            {"id": "bybit_check_payment", "kind": "registry"},
            {"id": "bybit_cancel_payment", "kind": "registry"},
        ],
        "children": [],
    },
    "bybit_uid_layouts": {
        "icon": "🎨",
        "title": "Bybit Deposit Readymade Layouts",
        "description": "Apply a readymade Bybit UID-flow deposit layout (preview first).",
        "texts": [],
        "buttons": [],
        "children": [],
    },

    "bybit_usdt_layouts": {
        "icon": "🎨",
        "title": "Bybit USDT Readymade Layouts",
        "description": "Apply a readymade Bybit USDT checkout layout (preview first).",
        "texts": [],
        "buttons": [],
        "children": [],
    },

    # 🔧 v119: readymade Bybit Pay checkout layouts with preview + apply
    "bybit_pay_layouts": {
        "icon": "🎨",
        "title": "Bybit Pay Readymade Layouts",
        "description": "Apply a readymade checkout layout (text + reference line). Preview first, then apply.",
        "texts": [],
        "buttons": [],
        "children": [],
    },

    "crypto_usdt_flow_screen": {
        "icon": "🪙",
        "title": "Crypto USDT Shared Screens",
        "description": "Shared on-chain TXID verification response text",
        "texts": [
            ("payment_not_found_txid", "📝 Payment Not Found / Retry Text"),
        ],
        "buttons": [
            {"id": "pay_usdt_bep20", "kind": "registry"},
            {"id": "pay_usdt_trc20", "kind": "registry"},
            {"id": "pay_bybit_usdt_bep20", "kind": "registry"},
            {"id": "pay_bybit_usdt_trc20", "kind": "registry"},
        ],
        "children": ["error_messages_screen"],
    },

    # ═══════════════════════════════════════════════════════════
    # 📱 EASYPAISA FLOW
    # ═══════════════════════════════════════════════════════════
    "easypaisa_flow_screen": {
        "icon": "📱",
        "title": "EasyPaisa Payment Flow",
        "description": "All text shown during EasyPaisa TID verification",
        "texts": [
                                                                                ],
        "buttons": [],
        "children": ["error_messages_screen", "easypaisa_layouts"],
    },

    "easypaisa_layouts": {
        "icon": "🎨",
        "title": "EasyPaisa Readymade Layouts",
        "description": "Apply a readymade EasyPaisa payment layout (preview first).",
        "texts": [],
        "buttons": [],
        "children": [],
    },

    # ═══════════════════════════════════════════════════════════
    # 📱 JAZZCASH FLOW
    # ═══════════════════════════════════════════════════════════
    "jazzcash_flow_screen": {
        "icon": "📱",
        "title": "JazzCash Payment Flow",
        "description": "All text shown during JazzCash TID verification",
        "texts": [
                                                                    ],
        "buttons": [],
        "children": ["error_messages_screen", "jazzcash_layouts"],
    },

    "jazzcash_layouts": {
        "icon": "🎨",
        "title": "JazzCash Readymade Layouts",
        "description": "Apply a readymade JazzCash payment layout (preview first).",
        "texts": [],
        "buttons": [],
        "children": [],
    },

    "order_created_screen": {
        "icon": "📜",
        "title": "Order Created / Status",
        "description": "Messages shown after order is created or status changes",
        "texts": [
                        ("order_rejected",  "📝 Order Rejected Text"),


        ],
        "buttons": [],
        "children": ["order_flow_layouts"],
    },

    "order_flow_layouts": {
        "icon": "🎨",
        "title": "Order Flow Readymade Layouts",
        "description": "Apply a readymade order created/cancelled/rejected layout set (preview first).",
        "texts": [],
        "buttons": [],
        "children": [],
    },

    # ═══════════════════════════════════════════════════════════
    # 💎 BUY POINTS
    # ═══════════════════════════════════════════════════════════
    "buy_points_screen": {
        "icon": "💎",
        "title": "Buy Points",
        "description": "User taps '💎 Buy Points' from main menu",
        "texts": [
            ("buy_points",                "📝 Buy Points Main Text"),
                                            ],
        "buttons": [
            # 🆕 v52: Back-to-main editable
            {"id": "nav_points_back", "kind": "registry"},
        ],
        "children": ["buy_points_payment_screen"],
    },

    "buy_points_payment_screen": {
        "icon": "💳",
        "title": "Buy Points — Pick Payment Method",
        "description": "After selecting amount, pick how to pay",
        "texts": [
                                            ],
        "buttons": [
            {"id": "pay_binance",       "kind": "registry"},
            {"id": "pay_easypaisa",     "kind": "registry"},
            {"id": "pay_jazzcash",      "kind": "registry"},
            # 🆕 v52: Cancel button editable
            {"id": "nav_points_cancel", "kind": "registry"},
        ],
        "children": [],
    },

    # ═══════════════════════════════════════════════════════════
    # 👤 USER PERSONAL SCREENS
    # ═══════════════════════════════════════════════════════════
    "my_account_screen": {
        "icon": "👤",
        "title": "My Account",
        "description": "Profile + balances screen",
        "texts": [
            ("my_account", "📝 My Account Text"),
        ],
        "buttons": [
            # 🆕 v52: Back button editable
            {"id": "nav_back_main", "kind": "registry"},
        ],
        "children": [],
    },

    "my_orders_screen": {
        "icon": "📜",
        "title": "My Orders / History",
        "description": "User's purchase history",
        "texts": [
            ("orders_title", "📝 Orders Title"),
            ("no_orders",    "📝 'No Orders' Text"),
        ],
        "buttons": [
            {"id": "nav_back_main", "kind": "registry"},
        ],
        "children": [],
    },

    "my_transactions_screen": {
        "icon": "💵",
        "title": "My Transactions",
        "description": "User's deposit / points-buy history",
        "texts": [
            ("no_transactions", "📝 'No Transactions' Text"),
        ],
        "buttons": [
            {"id": "nav_back_main", "kind": "registry"},
        ],
        "children": [],
    },

    "referral_screen": {
        "icon": "🎁",
        "title": "Referral Program",
        "description": "User's referral link + stats",
        "texts": [
            ("referral_text",                 "📝 Referral Page Text"),

            ("new_user_notification",         "📝 'New User Joined' Notification"),
        ],
        "buttons": [
            {"id": "nav_back_main", "kind": "registry"},
        ],
        "children": [],
    },

    # ═══════════════════════════════════════════════════════════
    # 🎫 SUPPORT / WARRANTY / REVIEWS / LOYALTY / LANGUAGE
    # ═══════════════════════════════════════════════════════════
    "support_screen": {
        "icon": "🎫",
        "title": "Support Center",
        "description": "Support menu + tickets",
        "texts": [
            ("support_menu_header", "📝 Support Menu Header"),
            ("support_text",        "📝 Support Page Text"),
        ],
        "buttons": [],
        "children": [],
    },

    "warranty_screen": {
        "icon": "🛡️",
        "title": "Warranty / Refund",
        "description": "Warranty request flow",
        "texts": [
            ("warranty_menu_header", "📝 Warranty Menu Header"),
            ("warranty_no_orders",   "📝 'No Eligible Orders' Text"),
        ],
        "buttons": [],
        "children": [],
    },

    "reviews_screen": {
        "icon": "⭐",
        "title": "Reviews & Ratings",
        "description": "Customer reviews flow",
        "texts": [
            ("reviews_menu_header", "📝 Reviews Menu Header"),
        ],
        "buttons": [],
        "children": [],
    },

    "loyalty_screen": {
        "icon": "🏆",
        "title": "Loyalty Program",
        "description": "VIP tiers screen",
        "texts": [
            ("loyalty_menu_header", "📝 Loyalty Menu Header"),
        ],
        "buttons": [],
        "children": [],
    },

    "language_screen": {
        "icon": "🌐",
        "title": "Language Picker",
        "description": "User language selection",
        "texts": [
            ("language_menu_header", "📝 Language Menu Header"),
        ],
        "buttons": [],
        "children": [],
    },

    # ═══════════════════════════════════════════════════════════
    # 🎁 FREE CLAIM USER SCREENS
    # ═══════════════════════════════════════════════════════════
    "freeclaim_screens": {
        "icon": "🎁",
        "title": "Free Claim (Referrals)",
        "description": "All text shown to users in the free-claim flow",
        "texts": [
            ("freeclaim_user_screen",      "📝 Free Claim Page (eligible)"),
            ("freeclaim_not_enough",       "📝 'Not Enough Refs' Page"),

                        ("freeclaim_share_message",    "📝 Pre-filled Share Message"),
            ("freeclaim_share_screen",     "📝 Share Screen Text"),

        ],
        "buttons": [],
        "children": [],
    },

    # ═══════════════════════════════════════════════════════════
    # ❌ ERROR MESSAGES (cross-screen)
    # ═══════════════════════════════════════════════════════════
    "error_messages_screen": {
        "icon": "❌",
        "title": "Error Messages (All Payment Errors)",
        "description": "Reusable error texts across all payment screens",
        "texts": [
                                                                                                        ],
        "buttons": [],
        "children": [],
    },

    # ═══════════════════════════════════════════════════════════
    # 📜 TERMS
    # ═══════════════════════════════════════════════════════════
    "terms_screen": {
        "icon": "📜",
        "title": "Terms & Conditions",
        "description": "Shown when user opens Terms page",
        "texts": [
            ("terms", "📝 Terms & Conditions Text"),
        ],
        "buttons": [],
        "children": [],
    },
}


# Root screen of the tree (the one shown first)
ROOT_SCREEN = "main_menu"


def get_screen(screen_id):
    """Return the node dict for a screen id, or None if not found."""
    return SCREEN_TREE.get(screen_id)


def is_valid_screen(screen_id):
    return screen_id in SCREEN_TREE


def get_breadcrumb(screen_id):
    """Build a breadcrumb path by walking parent → child relationships.
    Returns list of (screen_id, title). Best-effort: O(N) DFS from root."""
    target = screen_id
    parents = {}
    stack = [ROOT_SCREEN]
    visited = {ROOT_SCREEN}
    while stack:
        cur = stack.pop()
        node = SCREEN_TREE.get(cur, {})
        for ch in node.get("children", []):
            if ch not in visited:
                parents[ch] = cur
                visited.add(ch)
                stack.append(ch)
    path = []
    cur = target
    safety = 0
    while cur and safety < 50:
        path.append(cur)
        cur = parents.get(cur)
        safety += 1
    path.reverse()
    return [(sid, SCREEN_TREE.get(sid, {}).get("title", sid)) for sid in path]


def summary_counts(screen_id):
    """Return (n_texts, n_buttons, n_children) for a screen."""
    node = SCREEN_TREE.get(screen_id, {})
    return (
        len(node.get("texts", [])),
        len(node.get("buttons", [])),
        len(node.get("children", [])),
    )



# ════════════════════════════════════════════════════════════
# 🎨 v119 — BYBIT PAY READYMADE LAYOUTS (preview + apply)
# ════════════════════════════════════════════════════════════

# Readymade Bybit Pay checkout layouts. Each sets the checkout instructions
# (payment_bybit_pay) and the Reference ID line (payment_bybit_pay_reference).
# Admin can preview how the customer will see it, then apply. After applying,
# every field remains editable in the screen editor as usual.
BYBIT_PAY_LAYOUTS = {
    "simple": {
        "name": "Simple",
        "emoji": "🔖",
        "checkout": (
            "🟡 *Bybit Pay — Order #{order_id}*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💰 Amount: *{amount} USDT*\n"
            "📥 Pay to UID: `{pay_id}`\n\n"
            "*Steps:*\n"
            "1. Open Bybit → Bybit Pay → Send\n"
            "2. Send exactly *{amount} USDT* to the UID above\n"
            "3. Done — that's it! ✅\n\n"
            "🤖 Payment is detected automatically and credited within seconds.\n"
            "_No need to paste any ID._"
        ),
        "reference": (
            "🔖 *Optional — YOUR REFERENCE ID:* `{reference_id}`\n"
            "_Tip: paste it in the Reference field when sending to match instantly. Not required._"
        ),
    },
    "pro": {
        "name": "Pro",
        "emoji": "🟡",
        "checkout": (
            "🟡 *Bybit Pay — Secure Checkout*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🧾 Order: `#{order_id}`\n"
            "💰 Amount: *{amount} USDT*\n"
            "📥 Bybit Pay ID / UID: `{pay_id}`\n\n"
            "1. Open Bybit app → Bybit Pay → Send\n"
            "2. Enter UID above, amount *{amount} USDT*\n"
            "3. Confirm & send\n\n"
            "🔒 Payment is auto-detected from your Bybit account and credited instantly.\n"
            "_No pasting required._"
        ),
        "reference": (
            "🔖 *Optional — YOUR REFERENCE ID:* `{reference_id}`\n"
            "_Paste it in the Reference field when sending for instant matching. Not required._"
        ),
    },
    "minimal": {
        "name": "Minimal",
        "emoji": "⚡",
        "checkout": (
            "🟡 *Bybit Pay*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💰 *{amount} USDT* to `{pay_id}`\n\n"
            "Send — the bot auto-detects and credits it. ✅"
        ),
        "reference": (
            "🔖 *Reference ID:* `{reference_id}` (optional)"
        ),
    },
}


def _bypl_sample_render(layout_key):
    """Render what the customer would see for a layout (sample values)."""
    lay = BYBIT_PAY_LAYOUTS.get(layout_key) or BYBIT_PAY_LAYOUTS["simple"]
    sample = {
        "order_id": "12345",
        "amount": "1.00",
        "pay_id": "503209510",
        "reference_id": "48271936",
    }
    out = lay["checkout"].format(**sample)
    ref = lay["reference"].format(**sample)
    return out + "\n\n" + ref


async def _show_bybit_pay_layouts(q, sid, context):
    """Render the Bybit Pay readymade-layouts picker inside the screen editor."""
    header = (
        "🎨 *Bybit Pay — Readymade Layouts*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Pick a layout to see how the checkout screen will look,\n"
        "then *Preview* it and *Apply* it.\n\n"
        "After applying, every text stays editable in the screen editor."
    )
    kb = []
    for key, lay in BYBIT_PAY_LAYOUTS.items():
        kb.append([
            InlineKeyboardButton(f"{lay['emoji']} {lay['name']} Layout",
                                 callback_data=f"bypl_preview_{key}"),
            InlineKeyboardButton(f"✅ Apply {lay['name']}",
                                 callback_data=f"bypl_apply_{key}"),
        ])
    kb.append([InlineKeyboardButton("⬆️ Back to Bybit Flow",
                                    callback_data="se_open_bybit_flow_screen")])
    kb.append([InlineKeyboardButton("🔙 Back to Manage Buttons",
                                    callback_data="admin_buttons")])
    await _safe_edit(q, header, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def bypl_apply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apply a readymade Bybit Pay layout (sets the editable texts)."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    key = q.data.replace("bypl_apply_", "")
    lay = BYBIT_PAY_LAYOUTS.get(key)
    if not lay:
        await q.answer("Unknown layout", show_alert=True); return
    try:
        from database import set_response
        set_response("payment_bybit_pay", lay["checkout"])
        set_response("payment_bybit_pay_reference", lay["reference"])
    except Exception as e:
        await q.answer(f"Apply failed: {e}", show_alert=True); return
    await q.answer(f"✅ {lay['name']} layout applied!", show_alert=True)
    await _show_bybit_pay_layouts(q, "bybit_pay_layouts", context)


async def bypl_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show a preview of the chosen Bybit Pay layout (as the customer sees it)."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    key = q.data.replace("bypl_preview_", "")
    lay = BYBIT_PAY_LAYOUTS.get(key)
    if not lay:
        await q.answer("Unknown layout", show_alert=True); return
    await q.answer(f"Previewing {lay['name']} layout…")
    sample = _bypl_sample_render(key)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Apply {lay['name']}", callback_data=f"bypl_apply_{key}")],
        [InlineKeyboardButton("⬆️ Back to Layouts", callback_data="se_open_bybit_pay_layouts")],
    ])
    await _safe_edit(q,
                     f"👁 *Preview — {lay['name']} Layout*\n"
                     f"━━━━━━━━━━━━━━━━━━━━\n\n{sample}\n\n"
                     f"_(Sample values shown; real values come from the order.)_",
                     parse_mode="Markdown", reply_markup=kb)


# ════════════════════════════════════════════════════════════
# 🎨 v120 — GENERIC READYMADE LAYOUTS for every flow screen
# ════════════════════════════════════════════════════════════
# Same preview+apply pattern as the Bybit Pay layouts, but generic:
# each group defines which response keys it rewrites + the sample
# values used for previews. Add a group here → it appears in the
# screen editor automatically.
SCREEN_LAYOUT_GROUPS = {
    # ── Binance Pay checkout ──
    "binance_pay": {
        "name": "Binance Pay Checkout",
        "icon": "🔶",
        "sample": {"order_id": "12345", "title": "Order #12345",
                   "amount": "1.00", "pay_id": "887012522",
                   "holder": "Trendbite Services"},
        "keys": ["payment_binance_pay_orderid"],
        "layouts": {
            "simple": {"name": "Simple", "emoji": "🔶", "texts": {
                "payment_binance_pay_orderid": (
                    "🔶 *Binance Pay — Checkout*\n━━━━━━━━━━━━━━━━━━━━\n"
                    "{title}\n💰 Amount: *{amount} USDT*\n📋 Pay ID: `{pay_id}`\n"
                    "👤 Holder: *{holder}*\n\n"
                    "1. Open Binance → Pay\n2. Send exactly *{amount} USDT*\n"
                    "3. Copy the Order ID from your receipt\n4. Paste it here"
                )}},
            "pro": {"name": "Pro", "emoji": "🔶", "texts": {
                "payment_binance_pay_orderid": (
                    "🔶 *Binance Pay — Secure Checkout*\n━━━━━━━━━━━━━━━━━━━━\n"
                    "🧾 {title}\n💰 Amount: *{amount} USDT*\n"
                    "📋 Pay ID: `{pay_id}`\n👤 {holder}\n\n"
                    "*Steps:*\n1. Open Binance app → Binance Pay\n"
                    "2. Send *{amount} USDT* to the Pay ID above\n"
                    "3. After payment, copy the *Order ID*\n"
                    "4. Paste it here — auto-verified instantly"
                )}},
            "minimal": {"name": "Minimal", "emoji": "⚡", "texts": {
                "payment_binance_pay_orderid": (
                    "🔶 *Binance Pay*\n━━━━━━━━━━━━━━━━━━━━\n"
                    "💰 *{amount} USDT* → `{pay_id}`\n\n"
                    "Send, paste Order ID, done."
                )}},
        },
    },
    # ── Binance USDT on-chain ──
    "binance_usdt": {
        "name": "Binance USDT (on-chain)",
        "icon": "🪙",
        "sample": {"method_label": "USDT TRC20", "order_id": "12345",
                   "amount": "1.00", "network_label": "TRC20",
                   "address": "TAYv4LPE92rixGsr2sKe3Pz8mGfFU5cDW7"},
        "keys": ["payment_binance_usdt"],
        "layouts": {
            "simple": {"name": "Simple", "emoji": "🪙", "texts": {
                "payment_binance_usdt": (
                    "🪙 *{method_label} — Order #{order_id}*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n💰 Amount: *{amount} USDT*\n"
                    "🌐 Network: *{network_label}*\n\n📥 Send to:\n`{address}`\n\n"
                    "Send exact amount, then paste the *TXID*."
                )}},
            "pro": {"name": "Pro", "emoji": "🪙", "texts": {
                "payment_binance_usdt": (
                    "🪙 *{method_label} — Order #{order_id}*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n💰 Amount: *{amount} USDT*\n"
                    "🌐 Network: *{network_label}*\n\n📥 *Send to address*\n`{address}`\n\n"
                    "*Important:*\n✅ Coin: USDT\n✅ Network: {network_label}\n"
                    "❌ Wrong network = lost funds\n\nAfter sending, paste the *TXID*."
                )}},
            "minimal": {"name": "Minimal", "emoji": "⚡", "texts": {
                "payment_binance_usdt": (
                    "🪙 *{method_label}*\n━━━━━━━━━━━━━━━━━━━━\n"
                    "💰 *{amount} USDT* ({network_label})\n`{address}`\n\n"
                    "Send → paste TXID."
                )}},
        },
    },
    # ── Bybit USDT on-chain ──
    "bybit_usdt": {
        "name": "Bybit USDT (on-chain)",
        "icon": "🟡",
        "sample": {"method_label": "USDT TRC20", "order_id": "12345",
                   "amount": "1.00", "network_label": "TRC20",
                   "address": "TF4dCTJw42VT99NfUg95YNi5yF6uK7P2FG"},
        "keys": ["payment_bybit_usdt"],
        "layouts": {
            "simple": {"name": "Simple", "emoji": "🟡", "texts": {
                "payment_bybit_usdt": (
                    "🟡 *{method_label} — Order #{order_id}*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n💰 Amount: *{amount} USDT*\n"
                    "🌐 Network: *{network_label}*\n\n📥 Send to:\n`{address}`\n\n"
                    "Send exact amount, then paste the *Transaction Hash*."
                )}},
            "pro": {"name": "Pro", "emoji": "🟡", "texts": {
                "payment_bybit_usdt": (
                    "🟡 *{method_label} — Order #{order_id}*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n💰 Amount: *{amount} USDT*\n"
                    "🌐 Network: *{network_label}*\n\n📥 *Send to address*\n`{address}`\n\n"
                    "*Important:*\n✅ Coin: USDT\n✅ Network: {network_label}\n"
                    "❌ Wrong network = lost funds\n\nAfter sending, paste the *Transaction Hash*."
                )}},
            "minimal": {"name": "Minimal", "emoji": "⚡", "texts": {
                "payment_bybit_usdt": (
                    "🟡 *{method_label}*\n━━━━━━━━━━━━━━━━━━━━\n"
                    "💰 *{amount} USDT* ({network_label})\n`{address}`\n\n"
                    "Send → paste hash."
                )}},
        },
    },
    # ── EasyPaisa ──
    "easypaisa": {
        "name": "EasyPaisa Payment",
        "icon": "📱",
        "sample": {"order_id": "12345", "product": "Product",
                   "qty_text": "", "amount": "1.00", "pkr": "Rs. 300",
                   "rs_amount": "300", "number": "923193840214",
                   "holder": "Zayam Iqbal", "tid": "50568603579"},
        "keys": ["easypaisa_pay_instructions"],
        "layouts": {
            "simple": {"name": "Simple", "emoji": "📱", "texts": {
                "easypaisa_pay_instructions": (
                    "📱 *Order #{order_id} — EasyPaisa*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n📦 {product}{qty_text}\n"
                    "💰 Pay: *Rs.{rs_amount}*\n\n📲 *Send to:* `{number}`\n"
                    "Name: {holder}\n\n1. Send Rs.{rs_amount}\n"
                    "2. Enter the Trx ID from SMS below"
                )}},
            "pro": {"name": "Pro", "emoji": "📱", "texts": {
                "easypaisa_pay_instructions": (
                    "📱 *Order #{order_id} — EasyPaisa Payment*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n📦 {product}{qty_text}\n"
                    "💰 Amount: *Rs.{rs_amount}*\n\n📲 *Send Rs.{rs_amount} to:*\n"
                    "  Number: `{number}`\n  Name: {holder}\n\n"
                    "📝 *Instructions:*\n1. Send exact amount\n"
                    "2. EasyPaisa sends SMS with Trx ID\n"
                    "3. Enter the Trx ID below — bot checks itself!"
                )}},
            "minimal": {"name": "Minimal", "emoji": "⚡", "texts": {
                "easypaisa_pay_instructions": (
                    "📱 *EasyPaisa*\n━━━━━━━━━━━━━━━━━━━━\n"
                    "Rs.{rs_amount} → `{number}`\n\nSend → enter Trx ID."
                )}},
        },
    },
    # ── JazzCash ──
    "jazzcash": {
        "name": "JazzCash Payment",
        "icon": "📱",
        "sample": {"order_id": "12345", "product": "Product",
                   "qty_text": "", "amount": "1.00", "pkr": "Rs. 300",
                   "rs_amount": "300", "number": "923193840214",
                   "holder": "Zayam Iqbal"},
        "keys": ["jazzcash_pay_instructions"],
        "layouts": {
            "simple": {"name": "Simple", "emoji": "📱", "texts": {
                "jazzcash_pay_instructions": (
                    "📱 *Order #{order_id} — JazzCash*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n📦 {product}{qty_text}\n"
                    "💰 Pay: *Rs.{rs_amount}*\n\n📲 *Send to:* `{number}`\n"
                    "Name: {holder}\n\n1. Send Rs.{rs_amount}\n"
                    "2. Upload the transaction screenshot"
                )}},
            "pro": {"name": "Pro", "emoji": "📱", "texts": {
                "jazzcash_pay_instructions": (
                    "📱 *Order #{order_id} — JazzCash Payment*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n📦 {product}{qty_text}\n"
                    "💰 Amount: *Rs.{rs_amount}*\n\n📲 *Send Rs.{rs_amount} to:*\n"
                    "  Number: `{number}`\n  Name: {holder}\n\n"
                    "📸 *Instructions:*\n1. Send via JazzCash\n"
                    "2. Screenshot 'Transaction Successful'\n"
                    "3. Upload here — bot verifies automatically"
                )}},
            "minimal": {"name": "Minimal", "emoji": "⚡", "texts": {
                "jazzcash_pay_instructions": (
                    "📱 *JazzCash*\n━━━━━━━━━━━━━━━━━━━━\n"
                    "Rs.{rs_amount} → `{number}`\n\nSend → upload screenshot."
                )}},
        },
    },
    # ── Bybit USDT deposit screen (v123) ──
    "bybit_usdt_flow": {
        "name": "Bybit USDT Deposit",
        "icon": "💸",
        "sample": {"network_label": "TRC-20", "address": "TF4dCTJw42VT99NfUg95YNi5yF6uK7P2FG",
                   "amount": "1.4800", "reference_id": "48271936"},
        "keys": ["bybit_usdt_deposit_instructions", "bybit_usdt_warning_text",
                 "bybit_usdt_amount_prompt"],
        "layouts": {
            "simple": {"name": "Simple", "emoji": "💸", "texts": {
                "bybit_usdt_deposit_instructions": (
                    "💸 *Bybit — USDT — {network_label} Network*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "✉️ *Address:*\n`{address}`\n\n"
                    "💰 *Amount (exactly):*\n*{amount}*\n\n"
                    "⚠️ *Make sure you use the correct network — sending on the wrong network loses the amount.*\n"
                    "⏰ Expiry: 30 minutes\n"
                    "✨ The balance is added automatically after confirmation"
                ),
                "bybit_usdt_warning_text": (
                    "⚠️ *Before you transfer — read carefully*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "🔢 *Copy the full amount with all decimals* (e.g. 5.0087)\n\n"
                    "💯 *Send the exact same amount shown in the Bybit app*\n\n"
                    "❗️ Any small difference in the decimals = the bot won't detect your transfer.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "💸 *Fee note:* if the network deducts any fee, add it on top.\n"
                    "We are not responsible for network fees."
                ),
                "bybit_usdt_amount_prompt": (
                    "🟡 *Deposit via USDT — {network_label} Network*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "💡 *Send the USD amount you want to deposit:*\n\n"
                    "📌 Examples: 5 / 10 / 25 / 50\n⚠️ Minimum: $1"
                )}},
            "pro": {"name": "Pro", "emoji": "🟡", "texts": {
                "bybit_usdt_deposit_instructions": (
                    "💸 *Bybit — USDT — {network_label} Network*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "✉️ *Address:*\n`{address}`\n\n"
                    "💰 *Amount (exactly):*\n*{amount}*\n\n"
                    "⚠️ *Make sure you use the correct network — sending on the wrong network loses the amount.*\n"
                    "⏰ Expiry: 30 minutes\n"
                    "✨ The balance is added automatically after confirmation"
                ),
                "bybit_usdt_warning_text": (
                    "⚠️ *Before you transfer — read carefully*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "🔢 *Copy the full amount with all decimals* (e.g. 5.0087)\n\n"
                    "💯 *Send the exact same amount shown in the Bybit app*\n\n"
                    "🧾 The amount we receive must match exactly — decimals included\n\n"
                    "❗️ Any small difference in the decimals = the bot won't detect your transfer.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "💸 *Fee note:* if the network deducts any fee, add it on top so the full required amount reaches us.\n"
                    "We are not responsible for network fees."
                ),
                "bybit_usdt_amount_prompt": (
                    "🟡 *Deposit via USDT — {network_label} Network*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "💡 *Send the USD amount you want to deposit:*\n\n"
                    "📌 Examples: 5 / 10 / 25 / 50\n"
                    "⚠️ Minimum: $1\n\n"
                    "_Type the amount (numbers only)._\n"
                    "Your *exact unique payment amount* will be shown next."
                )}},
            "minimal": {"name": "Minimal", "emoji": "⚡", "texts": {
                "bybit_usdt_deposit_instructions": (
                    "💸 *Bybit USDT ({network_label})*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "💰 *{amount}* USDT →\n`{address}`\n\n"
                    "Correct network = auto-credit. ✅"
                ),
                "bybit_usdt_warning_text": (
                    "⚠️ Send the *exact amount with decimals* — difference = not detected."
                ),
                "bybit_usdt_amount_prompt": (
                    "🟡 *Deposit via USDT — {network_label}*\n"
                    "Amount (min $1):"
                )}},
        },
    },
    # ── Bybit UID-flow deposit screen (v122) ──
    "bybit_uid": {
        "name": "Bybit Deposit (UID flow)",
        "icon": "💸",
        "sample": {"store_uid": "503209510", "amount": "1.9700",
                   "reference_id": "82863628"},
        "keys": ["bybit_deposit_instructions"],
        "layouts": {
            "simple": {"name": "Simple", "emoji": "💸", "texts": {
                "bybit_deposit_instructions": (
                    "💸 *Bybit — internal transfer (UID)*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "1️⃣ Open Bybit ← Bybit Pay ← Send\n"
                    "2️⃣ Send to UID: `{store_uid}`\n"
                    "3️⃣ Send USDT exactly: *{amount}*\n"
                    "✏️ Reference: `{reference_id}`\n\n"
                    "⚠️ Exact amount = how we recognize you.\n"
                    "✨ Balance added automatically"
                )}},
            "pro": {"name": "Pro", "emoji": "🟡", "texts": {
                "bybit_deposit_instructions": (
                    "💸 *Bybit — internal transfer (UID)*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "1️⃣ Open the Bybit application ← Bybit Pay ← Send\n\n"
                    "2️⃣ Send to the UID:\n`{store_uid}`\n\n"
                    "3️⃣ Send USDT with this amount exactly:\n*{amount}*\n\n"
                    "✏️ Your reference id: `{reference_id}`\n\n"
                    "⚠️ The amount must be exactly the same — this is how we recognize your transfer.\n"
                    "⏰ Valid for: 30 minutes\n"
                    "✨ The balance is added automatically"
                )}},
            "minimal": {"name": "Minimal", "emoji": "⚡", "texts": {
                "bybit_deposit_instructions": (
                    "💸 *Bybit Deposit*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Send *{amount}* USDT → `{store_uid}`\n"
                    "Ref: `{reference_id}`\n\n"
                    "Exact amount = auto-credit. ✅"
                )}},
        },
    },
    # ── Order flow messages ──
    "order_flow": {
        "name": "Order Created / Status",
        "icon": "📜",
        "sample": {"order_id": "12345", "product": "Product", "price": "1.00",
                   "amount": "1.00", "reason": "out of stock", "points": "10",
                   "new_balance": "50"},
        "keys": ["order_created", "order_cancelled", "order_cancelled_no_reason",
                 "order_cancelled_with_reason", "order_rejected"],
        "layouts": {
            "standard": {"name": "Standard", "emoji": "📜", "texts": {
                "order_created": "✅ *Order #{order_id} Created!*\n━━━━━━━━━━━━━━━━━━━━\n📦 *{product}* — ${price}",
                "order_cancelled": "❌ *Order #{order_id} Cancelled.*",
                "order_cancelled_no_reason": "❌ *Order Cancelled*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Order: `#{order_id}`\n📌 Product: *{product}*\n💰 Amount: `${amount}`\n\nYour order has been cancelled.",
                "order_cancelled_with_reason": "❌ *Order Cancelled*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Order: `#{order_id}`\n📌 Product: *{product}*\n📋 *Reason:* _{reason}_",
                "order_rejected": "❌ Order #{order_id} was rejected.\nContact support for help.",
            }},
            "friendly": {"name": "Friendly", "emoji": "💬", "texts": {
                "order_created": "🎉 *Order #{order_id} is in!*\n━━━━━━━━━━━━━━━━━━━━\n📦 {product} — ${price}",
                "order_cancelled": "🙏 *Order #{order_id} cancelled.*\nAnything else we can help with?",
                "order_cancelled_no_reason": "🙏 *Order Cancelled*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Order: `#{order_id}`\n📌 Product: *{product}*\n\nIf you already paid, contact support for a refund.",
                "order_cancelled_with_reason": "🙏 *Order Cancelled*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Order: `#{order_id}`\n📋 *Reason:* _{reason}_",
                "order_rejected": "❌ Order #{order_id} could not be processed.\nPlease contact support.",
            }},
        },
    },
}


def _scl_group_has(group_key):
    return group_key in SCREEN_LAYOUT_GROUPS


def _scl_sample_render(group_key, layout_key):
    """Render what the customer would see for a layout (sample values)."""
    group = SCREEN_LAYOUT_GROUPS.get(group_key)
    if not group:
        return ""
    lay = group.get("layouts", {}).get(layout_key)
    if not lay:
        lay = list(group.get("layouts", {}).values())[0]
    sample = group.get("sample", {})
    lines = []
    for key in group.get("keys", []):
        txt = lay.get("texts", {}).get(key)
        if txt:
            try:
                lines.append(txt.format(**sample))
            except Exception:
                lines.append(txt)
    return "\n\n".join(lines)


async def _show_screen_layouts(q, group_key, context):
    """Generic readymade-layouts picker for a flow screen group."""
    group = SCREEN_LAYOUT_GROUPS.get(group_key)
    if not group:
        await _safe_edit(q, "❌ Unknown layout group.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🌳 Back to Tree", callback_data="se_root")]]))
        return
    header = (
        f"{group['icon']} *{group['name']} — Readymade Layouts*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Pick a layout to preview, then apply.\n"
        f"_After applying, every text stays editable in the screen editor._"
    )
    kb = []
    for key, lay in group.get("layouts", {}).items():
        kb.append([
            InlineKeyboardButton(f"{lay['emoji']} {lay['name']}",
                                 callback_data=f"scl_preview_{group_key}_{key}"),
            InlineKeyboardButton(f"✅ Apply {lay['name']}",
                                 callback_data=f"scl_apply_{group_key}_{key}"),
        ])
    kb.append([InlineKeyboardButton("⬆️ Back to Tree", callback_data="se_root")])
    kb.append([InlineKeyboardButton("🔙 Back to Manage Buttons",
                                    callback_data="admin_buttons")])
    await _safe_edit(q, header, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def scl_apply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apply a readymade layout for any flow screen group."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    data = q.data.replace("scl_apply_", "", 1)
    parts = data.split("_", 1)
    group_key = parts[0]
    layout_key = parts[1] if len(parts) > 1 else ""
    group = SCREEN_LAYOUT_GROUPS.get(group_key)
    lay = (group or {}).get("layouts", {}).get(layout_key) if group else None
    if not group or not lay:
        await q.answer("Unknown layout", show_alert=True); return
    try:
        from database import set_response
        for key, txt in lay.get("texts", {}).items():
            set_response(key, txt)
    except Exception as e:
        await q.answer(f"Apply failed: {e}", show_alert=True); return
    await q.answer(f"✅ {lay['name']} layout applied!", show_alert=True)
    await _show_screen_layouts(q, group_key, context)


async def scl_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Preview a readymade layout for any flow screen group."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    data = q.data.replace("scl_preview_", "", 1)
    parts = data.split("_", 1)
    group_key = parts[0]
    layout_key = parts[1] if len(parts) > 1 else ""
    group = SCREEN_LAYOUT_GROUPS.get(group_key)
    lay = (group or {}).get("layouts", {}).get(layout_key) if group else None
    if not group or not lay:
        await q.answer("Unknown layout", show_alert=True); return
    await q.answer(f"Previewing {lay['name']}…")
    sample = _scl_sample_render(group_key, layout_key)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Apply {lay['name']}", callback_data=f"scl_apply_{group_key}_{layout_key}")],
        [InlineKeyboardButton("⬆️ Back to Layouts", callback_data=f"se_open_{group_key}_layouts")],
    ])
    await _safe_edit(q,
                     f"👁 *Preview — {group['icon']} {group['name']} / {lay['name']}*\n"
                     f"━━━━━━━━━━━━━━━━━━━━\n\n{sample}\n\n"
                     f"_(Sample values shown; real values come from the order.)_",
                     parse_mode="Markdown", reply_markup=kb)




# ════════════════════════════════════════════════════════════
# 🎛️ v130 — BUTTON EDITOR + SUB MENU (recursive)
# ════════════════════════════════════════════════════════════

async def se_btns_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎛️ Button Editor — list buttons of a screen; tap → full edit panel."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    await q.answer()
    sid = q.data.replace("se_btns_", "", 1)
    node = get_screen(sid) or {}
    buttons = node.get("buttons", []) or []
    title = node.get("title", sid)
    if not buttons:
        # 🔧 v131: never a blank screen — show the real registry buttons for this
        # screen's group (or a clear note + link to the full Manage Buttons panel).
        try:
            from button_system import BUTTONS, GROUP_NAMES
            group_btns = [bid for bid, info in BUTTONS.items()
                          if info.get("group") in (node.get("button_group", ""),) or
                          (str(sid).startswith(str(info.get("group", ""))))]
            # fallback group inference from sid prefix
            if not group_btns:
                g = sid.split("_")[0]
                group_btns = [bid for bid, info in BUTTONS.items()
                              if info.get("group") == g]
        except Exception:
            group_btns = []
        text = (
            f"🎛️ *Button Editor — {escape_md(title)}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"_This screen has no dedicated buttons here._\n"
            f"Use the full *Manage Buttons* panel below to edit any button "
            f"(rename + premium emoji · color · hide/show · reset)."
        )
        kb = [[InlineKeyboardButton("🎛️ Manage All Buttons", callback_data="admin_buttons")],
              [InlineKeyboardButton("🔙 Back to Screen", callback_data=f"se_open_{sid}")]]
        await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return
    text = (
        f"🎛️ *Button Editor — {escape_md(title)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Tap a button to edit it:\n"
        f"(rename + premium emoji · color · hide/show · reset)"
    )
    kb = []
    for b in buttons:
        bid = b.get("id")
        kind = b.get("kind", "registry")
        lbl = _button_friendly_label(bid, kind)
        cb = _button_callback_for(bid, kind)  # mbedit_<bid> (full panel) or bs_edit_<key>
        if cb:
            kb.append([InlineKeyboardButton(lbl, callback_data=cb)])
    kb.append([InlineKeyboardButton("🔙 Back to Screen", callback_data=f"se_open_{sid}")])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def se_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📂 Sub Menu — render the REAL screen; each button taps back into the editor."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    await q.answer()
    sid = q.data.replace("se_sub_", "", 1)
    node = get_screen(sid) or {}
    buttons = node.get("buttons", []) or []
    title = node.get("title", sid)
    icon = node.get("icon", "📄")
    texts = node.get("texts", []) or []

    # Header = screen title; also list first editable text as the screen body
    body = f"{icon} *{escape_md(title)}*"
    if texts:
        try:
            from database import get_response_with_auto_register
            from config import DEFAULT_RESPONSES
            rk = texts[0][0]
            t = get_response_with_auto_register(rk, DEFAULT_RESPONSES.get(rk, ""))
            body += "\n\n" + t[:300]
        except Exception:
            pass

    kb = []
    if not buttons:
        kb.append([InlineKeyboardButton("🔙 Back to Screen", callback_data=f"se_open_{sid}")])
        await _safe_edit(q, body + "\n\n_This screen has no dedicated buttons — "
                         "its navigation uses shared buttons (Manage Buttons)._",
                         parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return
    for b in buttons:
        bid = b.get("id")
        kind = b.get("kind", "registry")
        # Real-looking button: styled label (rename + premium emoji) + color,
        # but callback goes back into the editor (recursion).
        try:
            from button_system import get_button_label, resolve_button_style, make_premium_button
            from database import get_setting as _gs
            size = _gs("button_size", "large")
            _alias = {"small": "short", "full": "xl"}
            size = _alias.get(size, size)
            label = get_button_label(bid, size)
            if not label:
                label = bid
            style = resolve_button_style(bid)
            btn = make_premium_button(label, callback_data=f"se_subbtn_{sid}|{bid}", style=style)
        except Exception:
            btn = InlineKeyboardButton(str(bid), callback_data=f"se_subbtn_{sid}|{bid}")
        kb.append([btn])
    kb.append([InlineKeyboardButton("🔙 Back to Screen", callback_data=f"se_open_{sid}")])
    await _safe_edit(q, body, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def se_subbtn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A button tapped inside Sub Menu → 2 options for the screen it opens."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌", show_alert=True); return
    await q.answer()
    raw = q.data.replace("se_subbtn_", "", 1)
    # format: <current_sid>|<bid> — pipe separator keeps multi-underscore
    # button ids (e.g. pay_binance) intact. 🔧 v132 fix.
    if "|" in raw:
        cur_sid, bid = raw.split("|", 1)
    else:
        # legacy fallback
        *sid_parts, bid = raw.rsplit("_", 1)
        cur_sid = "_".join(sid_parts)
    target = BTN_TARGET_SCREEN.get(bid, cur_sid)
    if not is_valid_screen(target):
        target = cur_sid
    node = get_screen(target) or {}
    t_icon = node.get("icon", "📄")
    t_title = node.get("title", target)
    text = (
        f"{t_icon} *{escape_md(t_title)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"_Button `{escape_md(bid)}` opens this screen._\n\n"
        f"Choose what to edit:"
    )
    kb = [
        [InlineKeyboardButton("🎛️ Button Editor", callback_data=f"se_btns_{target}"),
         InlineKeyboardButton("📂 Sub Menu", callback_data=f"se_sub_{target}")],
        [InlineKeyboardButton("🔙 Back to Sub Menu", callback_data=f"se_sub_{cur_sid}")],
        [InlineKeyboardButton("📋 Back to Screens", callback_data="se_root")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════════════════════
# ⚡ v133 — PER-RESPONSE AUTO-REACTION (merged into customization)
# ============================================================


def reaction_enabled() -> bool:
    """Master toggle for auto-reactions.
    🆕 v140.1: response-reaction feature REMOVED (owner request) → default OFF."""
    try:
        from database import get_setting
        val = get_setting("react_enabled", "0")
        if val is None or str(val).strip() == "":
            return False
        return str(val).strip() == "1"
    except Exception:
        return False


def set_reaction_enabled(on: bool):
    try:
        from database import set_setting
        set_setting("react_enabled", "1" if on else "0")
    except Exception:
        pass


def get_reaction(response_key: str) -> str:
    """Return the stored reaction spec for a response key ('' = none)."""
    try:
        from database import get_setting
        return (get_setting(f"react_{response_key}", "") or "").strip()
    except Exception:
        return ""


def set_reaction(response_key: str, spec: str):
    """spec: '' (none), '👍' (regular), or 'premium:<emoji_id>'."""
    try:
        from database import set_setting
        set_setting(f"react_{response_key}", (spec or "").strip())
    except Exception:
        pass


# 🆕 v140.1: default-reaction / auto-react REMOVED (owner request).
# Per-response react_to_message is kept only as an inert helper; nothing
# calls it anymore and the master toggle defaults to OFF.

async def react_to_message(bot, chat_id, message_id, response_key):
    """React to a message the bot just sent, if a reaction is configured for
    that response key. Never raises. (v140.1: no callers — feature removed.)"""
    try:
        if not reaction_enabled():
            return
        spec = get_reaction(response_key)
        if not spec:
            return
        from telegram import ReactionTypeEmoji, ReactionTypeCustomEmoji
        if str(spec).startswith("premium:"):
            eid = str(spec).split(":", 1)[1].strip()
            if not eid:
                return
            reaction = [ReactionTypeCustomEmoji(custom_emoji_id=eid)]
        else:
            emoji = str(spec).strip()
            if not emoji:
                return
            reaction = [ReactionTypeEmoji(emoji=emoji)]
        await bot.set_message_reaction(chat_id=chat_id, message_id=message_id, reaction=reaction)
    except Exception as e:
        logger.debug(f"[React] failed for {response_key}: {e}")
