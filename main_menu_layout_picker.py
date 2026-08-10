# ============================================================
# 🎨 v92: MAIN MENU LAYOUT PICKER — Admin panel
# ============================================================
# Admin can browse 50 layouts, see previews, and select any.
# Located under: Admin → 🎨 Customization → 🎨 Main Menu Layout
#
# Features:
#   • Category tabs (5 categories × 10 layouts)
#   • Layout preview (name + description + tag)
#   • Live "Preview on my chat" button
#   • Apply button — persists selection
#   • "Show custom buttons in this layout" toggle
# ============================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_ID
from main_menu_layouts import (
    LAYOUTS, get_active_layout_id, set_active_layout_id, render_layout,
)

logger = logging.getLogger(__name__)

CATEGORIES = {
    1: ("📐 Pure Grid", "Classic geometric layouts"),
    2: ("⭐ Priority Hero", "One or two buttons dominate"),
    3: ("📂 Grouped", "Sectioned by function"),
    4: ("📊 Info-Rich", "Live data in welcome"),
    5: ("🎨 Creative", "Unusual, stand-out designs"),
}


async def _safe_edit(q, text, **kw):
    try:
        await q.edit_message_text(text, **kw)
    except Exception:
        try:
            kw.pop("parse_mode", None)
            await q.edit_message_text(text, **kw)
        except Exception:
            try:
                await q.message.reply_text(text)
            except Exception:
                pass


# ─────────────────────────────────────────
# Panel: main hub
# ─────────────────────────────────────────
def _hub_text() -> str:
    active_id = get_active_layout_id()
    active = LAYOUTS.get(active_id, {})
    return (
        "🎨 *Main Menu Layout Picker*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"*Active layout:* `{active.get('name', active_id)}`\n"
        f"_{active.get('description', '')}_\n\n"
        "*50 layouts across 5 categories.* Pick a category to preview:\n\n"
        "🎯 *Custom buttons auto-flow* into your chosen layout — no manual work needed.\n"
        "🎨 *Bot API 9.4* colored buttons + premium emojis supported.\n"
        "🛡️ *Preview first*, apply only if you like it."
    )


def _hub_kb() -> InlineKeyboardMarkup:
    rows = []
    for cat_id, (name, _) in CATEGORIES.items():
        # Count layouts in this cat
        n = sum(1 for L in LAYOUTS.values() if L.get("category") == cat_id)
        rows.append([InlineKeyboardButton(
            f"{name} ({n})", callback_data=f"mml_cat_{cat_id}")])
    rows.append([InlineKeyboardButton("👁️ Preview Current Layout",
                                       callback_data="mml_preview_active")])
    rows.append([InlineKeyboardButton("🔄 Reset to Classic (#01)",
                                       callback_data="mml_reset")])
    rows.append([InlineKeyboardButton("🔙 Back to Customization",
                                       callback_data="admin_customization")])
    return InlineKeyboardMarkup(rows)


async def mml_hub_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    await _safe_edit(q, _hub_text(), parse_mode="Markdown", reply_markup=_hub_kb())


# ─────────────────────────────────────────
# Panel: category listing
# ─────────────────────────────────────────
def _cat_text(cat_id: int) -> str:
    name, desc = CATEGORIES.get(cat_id, ("?", ""))
    layouts_in_cat = [(k, v) for k, v in LAYOUTS.items() if v.get("category") == cat_id]
    return (
        f"{name}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"_{desc}_\n\n"
        f"*{len(layouts_in_cat)} layouts available.*\n"
        "Tap any to see details + preview."
    )


def _cat_kb(cat_id: int) -> InlineKeyboardMarkup:
    active = get_active_layout_id()
    rows = []
    layouts_in_cat = [(k, v) for k, v in LAYOUTS.items() if v.get("category") == cat_id]
    for lid, L in layouts_in_cat:
        mark = "⦿ " if lid == active else "   "
        label = f"{mark}{L['name']}"[:60]
        rows.append([InlineKeyboardButton(label, callback_data=f"mml_view_{lid}")])
    rows.append([InlineKeyboardButton("🔙 Back to Categories",
                                       callback_data="admin_main_layout")])
    return InlineKeyboardMarkup(rows)


async def mml_cat_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        cat_id = int(q.data.replace("mml_cat_", ""))
    except Exception:
        cat_id = 1
    await _safe_edit(q, _cat_text(cat_id), parse_mode="Markdown",
                     reply_markup=_cat_kb(cat_id))


# ─────────────────────────────────────────
# Panel: layout view / apply
# ─────────────────────────────────────────
def _view_text(lid: str) -> str:
    L = LAYOUTS.get(lid)
    if not L:
        return "❌ Layout not found."
    active = (lid == get_active_layout_id())
    hero = L.get("hero") or []
    footer = L.get("footer") or []
    core_pattern = L.get("core_pattern", "cols:1")
    overflow_cols = L.get("overflow_cols", 2)
    extras = L.get("welcome_extras") or []

    header_line = f"🟢 *ACTIVE*" if active else "⚪ Available"
    lines = [
        f"🎨 *{L['name']}*",
        f"_{L.get('tag', '')} · Category {L.get('category', '?')}_",
        "━━━━━━━━━━━━━━━━━━━━",
        header_line,
        "",
        f"📝 _{L.get('description', '')}_",
        "",
        "*Recipe:*",
    ]
    if hero:
        lines.append(f"  • Hero row: `{', '.join(hero)}`")
    lines.append(f"  • Core pattern: `{core_pattern}`")
    lines.append(f"  • Overflow (custom btns): `{overflow_cols}-column`")
    if footer:
        lines.append(f"  • Footer row: `{', '.join(footer)}`")
    if extras:
        lines.append(f"  • 💡 Welcome extras: `{', '.join(extras)}`")

    return "\n".join(lines)


def _view_kb(lid: str) -> InlineKeyboardMarkup:
    active = (lid == get_active_layout_id())
    L = LAYOUTS.get(lid, {})
    cat_id = L.get("category", 1)
    rows = []
    if not active:
        rows.append([InlineKeyboardButton("✅ Apply This Layout",
                                            callback_data=f"mml_apply_{lid}")])
    rows.append([InlineKeyboardButton("👁️ Preview in My Chat",
                                       callback_data=f"mml_preview_{lid}")])
    rows.append([InlineKeyboardButton(f"🔙 Back to Category {cat_id}",
                                       callback_data=f"mml_cat_{cat_id}")])
    rows.append([InlineKeyboardButton("🏠 Back to All Layouts",
                                       callback_data="admin_main_layout")])
    return InlineKeyboardMarkup(rows)


async def mml_view_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    lid = q.data.replace("mml_view_", "")
    await _safe_edit(q, _view_text(lid), parse_mode="Markdown",
                     reply_markup=_view_kb(lid))


async def mml_apply_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    lid = q.data.replace("mml_apply_", "")
    if lid not in LAYOUTS:
        await q.answer("❌ Unknown layout"); return
    ok = set_active_layout_id(lid)
    L = LAYOUTS.get(lid, {})
    if ok:
        await q.answer(f"✅ Applied: {L.get('name', lid)}", show_alert=True)
        # Refresh view screen
        await _safe_edit(q, _view_text(lid), parse_mode="Markdown",
                         reply_markup=_view_kb(lid))
    else:
        await q.answer("❌ Save failed", show_alert=True)


async def mml_preview_callback(update, context):
    """Send the actual layout preview to admin's chat as a new message."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("📤 Sending preview…")
    lid = q.data.replace("mml_preview_", "")
    if lid == "active":
        lid = get_active_layout_id()
    L = LAYOUTS.get(lid)
    if not L:
        return
    # Temporarily override active layout for rendering
    try:
        from main_menu_layouts import _render_recipe
        markup = _render_recipe(L, is_admin=True, user_id=q.from_user.id)
        preview_text = (
            f"👁️ *Preview: {L['name']}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"_{L.get('description', '')}_\n\n"
            "🛍️ Welcome to your bot with this layout applied.\n"
            "_(This is a live preview — tap any button to test.)_"
        )
        await context.bot.send_message(chat_id=q.from_user.id,
                                        text=preview_text,
                                        parse_mode="Markdown",
                                        reply_markup=markup)
    except Exception as e:
        logger.warning(f"[mml] preview failed: {e}")
        await context.bot.send_message(chat_id=q.from_user.id,
                                        text=f"❌ Preview error: {e}")


async def mml_reset_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    set_active_layout_id("L01_classic_1col")
    await q.answer("✅ Reset to Classic (#01)", show_alert=True)
    await _safe_edit(q, _hub_text(), parse_mode="Markdown", reply_markup=_hub_kb())


# ─────────────────────────────────────────
# "More Options" expand — for L41 Minimalist
# ─────────────────────────────────────────
async def main_more_expand_callback(update, context):
    """When user taps '⚙️ More Options ▼' on Minimalist layout — show hidden buttons."""
    q = update.callback_query
    await q.answer()
    from main_menu_layouts import LAYOUTS as _L
    L = _L.get(get_active_layout_id(), {})
    # Build a simple all-buttons list
    from button_system import get_ordered_button_ids
    all_ids = get_ordered_button_ids("main")
    from keyboards import _rb
    rows = []
    for bid in all_ids:
        btn = _rb(bid, user_id=q.from_user.id)
        if btn:
            rows.append([btn])
    rows.append([InlineKeyboardButton("🔙 Back to Home",
                                       callback_data="main_menu")])
    try:
        await q.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(rows))
    except Exception:
        await q.message.reply_text("All options:",
                                    reply_markup=InlineKeyboardMarkup(rows))
