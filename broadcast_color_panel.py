# ============================================================
# 🎨 v94: BROADCAST BUTTON COLOR PANEL
# ============================================================
# Admin can set a global background color for ALL broadcast
# "Buy Now" buttons (fake purchase, deposit, restock, discount,
# tier, referral, review — all of them). This is a fallback —
# per-template color (set via Edit Templates panel) still wins.
#
# Bot API 9.4 colors:
#   • primary → Blue
#   • success → Green
#   • danger  → Red
#   • (unset) → default gray
#
# Requires bot owner to have Telegram Premium subscription.
# ============================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_ID
from fake_engagement import _get_broadcast_global_color, set_broadcast_global_color

logger = logging.getLogger(__name__)

_COLOR_LABELS = {
    "": "⚪ Default (no color)",
    "primary": "🔵 Blue (Primary)",
    "success": "🟢 Green (Success)",
    "danger":  "🔴 Red (Danger)",
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


def _panel_text() -> str:
    current = _get_broadcast_global_color() or ""
    lbl = _COLOR_LABELS.get(current, current)
    return (
        "🎨 *Broadcast Button Color*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"*Global color:* {lbl}\n\n"
        "This color is applied to EVERY broadcast \"Buy Now\" button — "
        "fake purchases, deposits, restock alerts, discount alerts, "
        "review broadcasts, etc.\n\n"
        "*Priority:*\n"
        "1. Per-template color (set via 📝 Edit Templates → tap template) — highest\n"
        "2. This global color — used when a template has none\n"
        "3. No color (gray) — if neither is set\n\n"
        "⚠️ Requires bot owner to have Telegram Premium to render."
    )


def _panel_kb() -> InlineKeyboardMarkup:
    current = _get_broadcast_global_color() or ""
    rows = []
    for code, label in _COLOR_LABELS.items():
        mark = "⦿ " if code == current else "   "
        rows.append([InlineKeyboardButton(
            f"{mark}{label}", callback_data=f"bcolor_set_{code or 'none'}"
        )])
    rows.append([InlineKeyboardButton("🔙 Back to Customization",
                                       callback_data="admin_customization")])
    return InlineKeyboardMarkup(rows)


async def broadcast_color_panel_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    await _safe_edit(q, _panel_text(), parse_mode="Markdown",
                     reply_markup=_panel_kb())


async def broadcast_color_set_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    code = (q.data or "").replace("bcolor_set_", "").strip()
    if code == "none":
        code = ""
    set_broadcast_global_color(code)
    label = _COLOR_LABELS.get(code, code or "Default")
    await q.answer(f"✅ Set: {label}", show_alert=True)
    await _safe_edit(q, _panel_text(), parse_mode="Markdown",
                     reply_markup=_panel_kb())
