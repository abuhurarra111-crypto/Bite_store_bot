# ════════════════════════════════════════════
# ✨ v170.46: TELEGRAM MESSAGE EFFECTS — GLOBAL + PER-COMMAND
# ════════════════════════════════════════════
# Telegram `message_effect_id` — sirf PRIVATE (1:1) chats me chalta hai.
#
# Admin Settings → "✨ Message Effects" panel:
#   • Global default  (fx_global)     → har bot message par lagega
#   • Per-command     (fx_cmd_<cmd>)  → /start, /help, ... ka apna effect
#
# Resolution (send wrapper me): per-command override > global > kuch nahi.
#   "off" = explicit NO effect (global ko bhi rok de).

import contextvars

from database import get_setting, set_setting

# Verified IDs (single source of truth utils.MESSAGE_EFFECTS me hai)
try:
    from utils import MESSAGE_EFFECTS
except Exception:
    MESSAGE_EFFECTS = {
        "5104841245755180586": "🔥 Fire",
        "5159385139981059251": "❤️ Heart",
        "5107584321108051014": "👍 Like",
        "5104858069142078462": "👎 Dislike",
        "5046509860389126442": "🎉 Party",
        "5046589136895476101": "💩 Poop",
    }

OFF = "off"          # explicit no-effect
INHERIT = "inherit"  # (sirf command) → global use karo

# Jin commands ke liye panel me per-command effect dikhana hai
FX_COMMANDS = [
    ("start",    "🚀 /start"),
    ("help",     "❓ /help"),
    ("shop",     "🛒 /shop"),
    ("orders",   "📜 /orders"),
    ("balance",  "💎 /balance"),
    ("deposit",  "💰 /deposit"),
    ("freebies", "🎁 /freebies"),
    ("support",  "🎧 /support"),
    ("apikey",   "🔑 /apikey"),
    ("language", "🌐 /language"),
]

# Abhi kaunsa command chal raha hai (bot.py ka -95 probe set karta hai)
CURRENT_COMMAND = contextvars.ContextVar("bite_fx_command", default="")

# Abhi kaunsa event chal raha hai (e.g. "delivered" — bot.py/probe ya
# handlers set karte hain; jis se event-specific effect lagta hai)
CURRENT_EVENT = contextvars.ContextVar("bite_fx_event", default="")


def set_current_command(cmd):
    CURRENT_COMMAND.set(cmd or "")


def set_event(ev):
    CURRENT_EVENT.set(ev or "")


# Auto-message events (commands ke ilawa) — panel me dikhte hain
FX_EVENTS = [
    ("delivered", "📦 Order Delivered"),
]


# ── Global ──────────────────────────────────
def global_effect():
    return str(get_setting("fx_global", "") or "").strip()


def set_global_effect(eid):
    set_setting("fx_global", str(eid or ""))


# ── Per-command ─────────────────────────────
def command_effect(cmd):
    return str(get_setting(f"fx_cmd_{cmd}", "") or "").strip()


def set_command_effect(cmd, val):
    set_setting(f"fx_cmd_{cmd}", str(val or ""))


# ── Per-event ───────────────────────────────
def event_effect(ev):
    return str(get_setting(f"fx_event_{ev}", "") or "").strip()


def set_event_effect(ev, val):
    set_setting(f"fx_event_{ev}", str(val or ""))


# ── Resolution ──────────────────────────────
def resolve_effect():
    """Effect id (str) ya None. Per-event override > per-command > global."""
    ev = CURRENT_EVENT.get()
    if ev:
        v = event_effect(ev)
        if v == OFF:
            return None        # explicit off → global ignore
        if v:
            return v
    cmd = CURRENT_COMMAND.get()
    if cmd:
        v = command_effect(cmd)
        if v == OFF:
            return None        # explicit off → global ignore
        if v:
            return v
    g = global_effect()
    if g and g != OFF:
        return g
    return None


def attach_effect(kwargs, chat_id):
    """send_message wrapper se call hota hai — effect inject karo (safe)."""
    try:
        if kwargs.get("message_effect_id"):
            return  # already set (caller ka apna effect respect karo)
        # Telegram effects sirf private chats me: positive numeric chat_id
        if not (isinstance(chat_id, int) and chat_id > 0):
            return
        eff = resolve_effect()
        if eff:
            kwargs["message_effect_id"] = eff
    except Exception:
        pass
