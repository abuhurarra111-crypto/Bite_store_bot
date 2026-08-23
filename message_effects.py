# ════════════════════════════════════════════
# ✨ TELEGRAM MESSAGE EFFECTS — GLOBAL + COMMAND + EVENT
# ════════════════════════════════════════════
# Telegram `message_effect_id` sirf PRIVATE (1:1) chats me chalta hai.
# Resolution: per-event override > per-command override > global > nothing.

import contextvars
from contextlib import contextmanager

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
INHERIT = "inherit"  # command/event → global use karo

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

# User-facing auto-message events. Every event below is attached only at the
# exact success/notification message, never to generic errors or all messages.
FX_EVENTS = [
    ("delivered",                "📦 Order Delivered"),
    ("points_deposit_confirmed", "💎 Points Deposit Confirmed"),
    ("freebie_claimed",          "🎁 Freebie Claimed"),
    ("referral_reward",          "👥 Referral Reward / Milestone"),
    ("tier_upgrade",             "🏆 Loyalty Tier Upgrade"),
    ("support_resolved",         "🎫 Support Ticket Resolved"),
    ("warranty_approved",        "🛡️ Warranty Approved"),
    ("replacement_approved",     "🔁 Replacement Approved"),
    ("restock_alert",            "🔔 Restock Alert"),
    ("refund_completed",         "💸 Refund Completed"),
]

# One-tap optional configuration from the admin panel. Global and command
# settings are deliberately untouched; the owner stays in full control.
RECOMMENDED_EVENT_EFFECTS = {
    "delivered":                "5046509860389126442",  # 🎉 Party
    "points_deposit_confirmed": "5107584321108051014",  # 👍 Like
    "freebie_claimed":          "5046509860389126442",  # 🎉 Party
    "referral_reward":          "5159385139981059251",  # ❤️ Heart
    "tier_upgrade":             "5046509860389126442",  # 🎉 Party
    "support_resolved":         "5107584321108051014",  # 👍 Like
    "warranty_approved":        "5159385139981059251",  # ❤️ Heart
    "replacement_approved":     "5159385139981059251",  # ❤️ Heart
    "restock_alert":            "5104841245755180586",  # 🔥 Fire
    "refund_completed":         "5107584321108051014",  # 👍 Like
}

# Abhi kaunsa command / event chal raha hai. The class-level Bot send wrapper
# reads these context vars immediately before it sends a private-chat message.
CURRENT_COMMAND = contextvars.ContextVar("bite_fx_command", default="")
CURRENT_EVENT = contextvars.ContextVar("bite_fx_event", default="")


def set_current_command(cmd):
    CURRENT_COMMAND.set(cmd or "")


def set_event(ev):
    """Backward-compatible setter for legacy call sites."""
    CURRENT_EVENT.set(ev or "")


def push_event(ev):
    """Set an event and return a token that restores the prior nested context."""
    return CURRENT_EVENT.set(ev or "")


def reset_event(token):
    """Restore a token created by :func:`push_event` safely."""
    if token is None:
        return
    try:
        CURRENT_EVENT.reset(token)
    except Exception:
        pass


@contextmanager
def event_scope(ev):
    """Temporarily apply one event without leaking it to later bot messages."""
    token = push_event(ev)
    try:
        yield
    finally:
        reset_event(token)


def event_label(ev):
    """Human-readable event name for the admin editor."""
    return dict(FX_EVENTS).get(ev, str(ev or "").replace("_", " ").title())


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


def apply_recommended_event_effects():
    """Apply the suggested mapping to event settings only.

    Returns the number of configured events. This does not change Global or
    command-level preferences, so existing owner customizations stay intact.
    """
    applied = 0
    for ev, _label in FX_EVENTS:
        effect_id = RECOMMENDED_EVENT_EFFECTS.get(ev, "")
        if effect_id:
            set_event_effect(ev, effect_id)
            applied += 1
    return applied


# ── Resolution ──────────────────────────────
def resolve_effect():
    """Effect id (str) ya None. Per-event > per-command > global."""
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
            return  # caller ka explicit effect respect karo
        # Telegram effects sirf private chats me: positive numeric chat_id
        if not (isinstance(chat_id, int) and chat_id > 0):
            return
        eff = resolve_effect()
        if eff:
            kwargs["message_effect_id"] = eff
    except Exception:
        pass


async def send_event_message(bot, event, chat_id, text, *args, **kwargs):
    """Send one message while the supplied event effect is active.

    It injects ``message_effect_id`` directly and also remains compatible with
    the main application's class-level Bot wrapper. Private-chat guards keep
    groups, channels, and test doubles safe.
    """
    with event_scope(event):
        # Inject directly as well as leaving the context available to the main
        # class-level wrapper. This makes targeted event sends reliable even in
        # a lightweight test/different Bot implementation where that wrapper
        # has not yet been installed.
        attach_effect(kwargs, chat_id)
        return await bot.send_message(chat_id, text, *args, **kwargs)
