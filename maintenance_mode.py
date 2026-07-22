# ============================================================
# 🛠️ v84: MAINTENANCE MODE
# ============================================================
# Blocks EVERY user command / button / message while admin
# is working on the bot. Admin (ADMIN_ID) is exempt.
# Running orders (payment/delivery in progress) are allowed
# to complete — only NEW actions are blocked.
#
# Storage: bot_settings keys:
#   maint_enabled   → "1" / "0"
#   maint_template  → integer 1..5  OR  "custom"
#   maint_custom    → free-text (may include [[HTML]] + <tg-emoji> for
#                     premium emojis — rendered via smart_text_and_mode)
#
# Admin toggles via 🛠️ Maintenance panel (in Admin → Settings).
# No new env vars, safe additive migration.
# ============================================================

import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ApplicationHandlerStop

from config import ADMIN_ID
from database import get_setting, set_setting
from utils import smart_text_and_mode

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 5 ready-made templates (mix tone — professional/casual/emoji-heavy/
# apology/short). Admin can pick any by number, or write a custom one.
# Users can copy-paste premium <tg-emoji> markup into custom too.
# ------------------------------------------------------------
MAINT_TEMPLATES = {
    1: (
        "🛠️ *BITE STORE — Under Maintenance*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Bot ko thoda upgrade dia ja raha hai 🚀\n"
        "Please thodi der baad wapas try karein.\n\n"
        "🙏 Sabar ka shukriya!\n"
        "💬 Support: @bite_storee_bot"
    ),
    2: (
        "⚙️ *Quick Maintenance in Progress*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "New features add ho rahe hain — bot 5-15 min mein wapas online.\n"
        "Aap ke pending orders safe hain ✅\n\n"
        "Meanwhile, follow @bite_alerts for updates 📢"
    ),
    3: (
        "🚧 Yaar, thora sa kaam chal raha hai bot pe 🛠️\n\n"
        "5-10 min ruk jao, sab kuch behtar ho ke wapas ayega 💪\n"
        "Order karne ki fikar mat karo — jaise hi ready hoga, bata denge 🔔"
    ),
    4: (
        "😔 *Sorry for the inconvenience!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Hum abhi kuch important updates lagane mein busy hain.\n"
        "Ye maintenance zaroori thi taake aap ko behtar service mile.\n\n"
        "⏱️ Bot jald hi wapas active hoga.\n"
        "❤️ Aap ki wafadari ka shukriya!"
    ),
    5: (
        "⏳ *Maintenance…* Bot busy hai, thori der baad try karein 🙏"
    ),
}

# ------------------------------------------------------------
# Storage helpers
# ------------------------------------------------------------
def is_maintenance_on() -> bool:
    return str(get_setting("maint_enabled", "0")) == "1"

def set_maintenance(on: bool):
    set_setting("maint_enabled", "1" if on else "0")

def get_maintenance_template() -> str:
    """Returns the currently-selected template key ('1'..'5' or 'custom')."""
    v = str(get_setting("maint_template", "1")).strip()
    if v == "custom":
        return "custom"
    try:
        n = int(v)
        if n in MAINT_TEMPLATES:
            return str(n)
    except Exception:
        pass
    return "1"

def set_maintenance_template(key: str):
    set_setting("maint_template", str(key))

def get_maintenance_custom() -> str:
    return str(get_setting("maint_custom", "") or "")

def set_maintenance_custom(text: str):
    set_setting("maint_custom", text or "")

def get_maintenance_message() -> str:
    """Return the actual text to send to users."""
    tpl = get_maintenance_template()
    if tpl == "custom":
        txt = get_maintenance_custom().strip()
        if txt:
            return txt
        # If custom selected but empty, fall through to template 1
        tpl = "1"
    try:
        return MAINT_TEMPLATES[int(tpl)]
    except Exception:
        return MAINT_TEMPLATES[1]


# ------------------------------------------------------------
# Rate-limiter — don't spam the same user 20 times/second
# ------------------------------------------------------------
_LAST_SENT = {}   # user_id → last epoch seconds
_COOLDOWN = 8.0   # seconds between maintenance replies to the same user

def _cooled_down(uid: int) -> bool:
    now = time.time()
    last = _LAST_SENT.get(uid, 0)
    if now - last < _COOLDOWN:
        return False
    _LAST_SENT[uid] = now
    return True


# ------------------------------------------------------------
# Callback allow-list (running orders allowed to complete)
# ------------------------------------------------------------
# These callbacks let a user FINISH a running order/payment flow.
# They do NOT let the user start something new.
_ORDER_COMPLETION_CALLBACKS = (
    # Payment method screens for an already-created order:
    "pay_screenshot_",         # user uploads payment screenshot
    "pay_binance_tx_",         # user submits Binance TxID
    "confirm_pay_",             # user confirms a running pay flow
    "cancel_order_",            # user cancels their own pending order
    # Support tickets already open — let them reply/close so nothing hangs
    "st_reply_",
    "st_close_",
    "st_view_",
    # Warranty/replacement in progress
    "user_replace_reason_",
    # ext-suppliers order completion (auto-fulfil path — bot-side, but a
    # button press could trigger it)
    "vpoid_",
)

def _is_completion_callback(data: str) -> bool:
    if not data:
        return False
    for pfx in _ORDER_COMPLETION_CALLBACKS:
        if data.startswith(pfx):
            return True
    return False


# ------------------------------------------------------------
# BLOCKER — the actual gate (runs at group=-90, before everything)
# ------------------------------------------------------------
async def maintenance_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Runs on EVERY incoming update at high priority (group=-90).
    - Admin: always allowed through (return, don't raise).
    - Maintenance OFF: allowed through.
    - Callback matching completion allow-list: allowed through.
    - Everything else: send maintenance message + swallow update.
    """
    try:
        if not is_maintenance_on():
            return  # fall through to normal handlers

        user = update.effective_user
        if not user:
            return
        uid = user.id
        if uid == ADMIN_ID:
            return  # admin bypass

        # Allow-list check for callbacks so a user in the middle of a
        # payment flow doesn't get stuck.
        if update.callback_query and _is_completion_callback(update.callback_query.data or ""):
            return

        # We're blocking this update. Reply with the maintenance message.
        text = get_maintenance_message()
        # premium_emoji_guard's smart_text_and_mode handles [[HTML]] + <tg-emoji>
        cleaned, mode = smart_text_and_mode(text, "Markdown")

        # For callback queries, answer + send a NEW message so the user sees it
        # in-chat (edit_message_text would silently rewrite whatever they're on).
        if update.callback_query:
            try:
                await update.callback_query.answer("🛠️ Under maintenance",
                                                    show_alert=False)
            except Exception:
                pass
            if _cooled_down(uid):
                try:
                    await context.bot.send_message(chat_id=uid, text=cleaned,
                                                    parse_mode=mode,
                                                    disable_web_page_preview=True)
                except Exception as e:
                    logger.debug(f"[Maint] send fail cq: {e}")
        elif update.message:
            if _cooled_down(uid):
                try:
                    await update.message.reply_text(cleaned, parse_mode=mode,
                                                    disable_web_page_preview=True)
                except Exception as e:
                    logger.debug(f"[Maint] send fail msg: {e}")

        # SWALLOW the update so no downstream handler runs.
        # ApplicationHandlerStop is the ONLY exception PTB honours to abort
        # all further handler groups for this update.
        raise ApplicationHandlerStop

    except ApplicationHandlerStop:
        raise
    except Exception as e:
        # Never break the bot because of maintenance code
        logger.warning(f"[Maint] gate exception: {e}")
        return


class _MaintBlocked(Exception):
    """(Legacy) marker — kept for import compat, no longer raised."""
    pass


# ============================================================
# ADMIN PANEL — 🛠️ Maintenance Mode
# ============================================================
# Callbacks:
#   maint_panel              → open panel
#   maint_toggle             → flip on/off
#   maint_preview            → send preview to admin
#   maint_pick_<n|custom>    → set active template
#   maint_edit_custom        → begin conversation to set custom text
#
# Custom text is captured via a ConversationHandler state:
#   MAINT_CUSTOM_TEXT = 9284
# ============================================================

MAINT_CUSTOM_TEXT = 9284  # unique state id


def _panel_kb() -> InlineKeyboardMarkup:
    on = is_maintenance_on()
    tpl = get_maintenance_template()
    rows = []
    rows.append([InlineKeyboardButton(
        ("🟢 ON  (tap to turn OFF)" if on else "🔴 OFF  (tap to turn ON)"),
        callback_data="maint_toggle")])
    rows.append([InlineKeyboardButton("👁️ Preview msg to me",
                                       callback_data="maint_preview")])
    rows.append([InlineKeyboardButton("━━ Choose Template ━━",
                                       callback_data="maint_noop")])
    for n in (1, 2, 3, 4, 5):
        mark = "⦿ " if tpl == str(n) else "   "
        rows.append([InlineKeyboardButton(f"{mark}Template #{n}",
                                           callback_data=f"maint_pick_{n}")])
    mark_c = "⦿ " if tpl == "custom" else "   "
    rows.append([InlineKeyboardButton(f"{mark_c}✏️ Custom Message",
                                       callback_data="maint_pick_custom")])
    rows.append([InlineKeyboardButton("📝 Edit Custom Text",
                                       callback_data="maint_edit_custom")])
    rows.append([InlineKeyboardButton("🔙 Back to Settings",
                                       callback_data="admin_settings")])
    return InlineKeyboardMarkup(rows)


def _panel_text() -> str:
    on = is_maintenance_on()
    tpl = get_maintenance_template()
    if tpl == "custom":
        preview = (get_maintenance_custom() or "*(custom not set — falls back to Template #1)*")
        preview = preview[:200] + ("…" if len(preview) > 200 else "")
        active_label = f"✏️ Custom\n_Preview:_ {preview}"
    else:
        try:
            preview = MAINT_TEMPLATES[int(tpl)]
            preview = preview[:200] + ("…" if len(preview) > 200 else "")
            active_label = f"Template #{tpl}\n_Preview:_ {preview}"
        except Exception:
            active_label = "Template #1"

    status = "🟢 *ON* — users are blocked" if on else "🔴 *OFF* — normal operation"
    return (
        "🛠️ *Maintenance Mode*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Status: {status}\n\n"
        f"Active reply: {active_label}\n\n"
        "_When ON, every user command / button / message gets the "
        "maintenance reply. Admin (you) can still use the bot normally. "
        "Users mid-payment can finish that payment._"
    )


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


async def maint_panel_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    await _safe_edit(q, _panel_text(), parse_mode="Markdown",
                     reply_markup=_panel_kb(), disable_web_page_preview=True)


async def maint_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    set_maintenance(not is_maintenance_on())
    await q.answer("Toggled ✅")
    await _safe_edit(q, _panel_text(), parse_mode="Markdown",
                     reply_markup=_panel_kb(), disable_web_page_preview=True)


async def maint_noop_callback(update, context):
    await update.callback_query.answer()


async def maint_preview_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    text = get_maintenance_message()
    cleaned, mode = smart_text_and_mode(text, "Markdown")
    try:
        await context.bot.send_message(chat_id=q.from_user.id,
                                        text=cleaned, parse_mode=mode,
                                        disable_web_page_preview=True)
    except Exception:
        try:
            await context.bot.send_message(chat_id=q.from_user.id, text=cleaned)
        except Exception:
            pass


async def maint_pick_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    key = (q.data or "").replace("maint_pick_", "", 1).strip()
    if key == "custom":
        set_maintenance_template("custom")
    else:
        try:
            n = int(key)
            if n in MAINT_TEMPLATES:
                set_maintenance_template(str(n))
        except Exception:
            pass
    await q.answer("Saved ✅")
    await _safe_edit(q, _panel_text(), parse_mode="Markdown",
                     reply_markup=_panel_kb(), disable_web_page_preview=True)


# ---- Conversation: edit custom text ----------------------------------
async def maint_edit_custom_entry(update, context):
    """Entry point of the custom-text conversation."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return -1
    await q.answer()
    current = get_maintenance_custom() or "_(none set)_"
    await q.message.reply_text(
        "📝 *Custom Maintenance Message*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Send me the exact text you want users to see when maintenance is ON.\n\n"
        "✅ You can use *Markdown* / [[HTML]] / premium `<tg-emoji>` emojis — "
        "they render properly.\n"
        "✅ Reply with `-` (single dash) to clear it and fall back to Template #1.\n"
        "✅ Send /cancel to keep the current text.\n\n"
        f"*Current:*\n{current[:1500]}",
        parse_mode="Markdown", disable_web_page_preview=True)
    return MAINT_CUSTOM_TEXT


async def maint_custom_received(update, context):
    """Save the admin-supplied custom text."""
    if update.effective_user.id != ADMIN_ID:
        return -1
    # Grab the message — text OR html_text (to preserve <tg-emoji> markup
    # from copy-pasted premium emojis)
    msg = update.message
    if msg is None:
        return -1
    # Prefer text_html so pasted premium <tg-emoji> tags survive as HTML.
    raw_html = None
    try:
        raw_html = msg.text_html
    except Exception:
        raw_html = None
    raw_plain = (msg.text or "").strip()
    if raw_plain == "-":
        set_maintenance_custom("")
        await msg.reply_text("🧹 Custom message cleared. Will fall back to Template #1.",
                              reply_markup=InlineKeyboardMarkup([[
                                  InlineKeyboardButton("🛠️ Back to Maintenance",
                                                        callback_data="maint_panel")]]))
        return -1

    # Detect premium emoji entities in the message → save as [[HTML]] blob
    has_premium = False
    try:
        for ent in (msg.entities or []):
            if getattr(ent, "type", "") == "custom_emoji":
                has_premium = True; break
    except Exception:
        pass

    if has_premium and raw_html:
        # Save HTML representation with sentinel so smart_text_and_mode picks HTML
        to_save = "[[HTML]]" + raw_html
    else:
        to_save = raw_plain

    if not to_save.strip():
        await msg.reply_text("⚠️ Empty — nothing saved.")
        return -1

    set_maintenance_custom(to_save)
    set_maintenance_template("custom")  # auto-activate custom on save

    # Preview back to admin
    cleaned, mode = smart_text_and_mode(to_save, "Markdown")
    await msg.reply_text(
        "✅ *Saved as active custom message.*\nPreview below:",
        parse_mode="Markdown")
    try:
        await msg.reply_text(cleaned, parse_mode=mode,
                              disable_web_page_preview=True,
                              reply_markup=InlineKeyboardMarkup([[
                                  InlineKeyboardButton("🛠️ Back to Maintenance",
                                                        callback_data="maint_panel")]]))
    except Exception:
        await msg.reply_text(cleaned, disable_web_page_preview=True)
    return -1


async def maint_custom_cancel(update, context):
    try:
        await update.message.reply_text("❎ Cancelled — custom text unchanged.")
    except Exception:
        pass
    return -1
