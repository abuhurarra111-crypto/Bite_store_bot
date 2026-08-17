# ============================================================
# 🧩 v77 BUNDLE: fake_engagement.py
# ============================================================
# This file is the merged result of 5 originally separate modules:
#   • fake_broadcast.py
#   • fake_reviews.py
#   • handlers_fake_broadcast.py
#   • handlers_fake_reviews.py
#   • store_broadcast.py
#
# 🛡️ ALL CODE IS PRESERVED VERBATIM. Each original file's contents appears
# below in its own section. Imports and behavior are byte-identical to the
# pre-merge codebase — only file count is reduced.
# ============================================================


# ============================================================
# 📄 ORIGINAL FILE: fake_broadcast.py
# ============================================================

# ============================================================
# 📢 FAKE BROADCAST SYSTEM — fake_broadcast.py
# ============================================================
#
# WHAT IS THIS?
# ─────────────
# This system makes your bot look very active and busy to users.
# Even if no one is buying, the bot sends realistic-looking
# notifications to all users — fake purchases, deposits,
# new stock alerts (for REAL stock only), referral milestones, etc.
#
# All messages look exactly like real bot notifications.
#
# ──────────────────────────────────────────────────────────
# HOW IT WORKS (Simple Explanation):
# ──────────────────────────────────────────────────────────
#
#   1. Every 0–60 minutes (random interval) a job runs
#   2. It picks a random message type (purchase, deposit, referral, etc.)
#   3. It uses fake names + real product names from your DB
#   4. It sends that fake message to ALL real users
#   5. New Stock messages ONLY go when admin adds real stock
#
# ──────────────────────────────────────────────────────────
# ADMIN CONTROL (Full control from Admin Panel):
# ──────────────────────────────────────────────────────────
#
#   ✅ Enable / Disable entire fake broadcast system
#   ✅ Set minimum interval (e.g. 5 min)
#   ✅ Set maximum interval (e.g. 60 min)
#   ✅ Enable / Disable each message type individually:
#        - Fake Purchases
#        - Fake Deposits
#        - Fake Referral Milestones
#        - New Stock Alerts (only sent when stock is real)
#        - Tier Upgrade Announcements
#   ✅ View log of last 20 fake broadcasts sent
#   ✅ Trigger a fake broadcast manually (test button)
#   ✅ Set fake user name style (random / initials / stars like b***l)
#
# ──────────────────────────────────────────────────────────
# IMPORTANT NOTES:
# ──────────────────────────────────────────────────────────
#
#   - Fake messages use REAL product names from your shop
#   - Products with stock=0 are NEVER used in fake messages
#   - New Stock alerts only fire when admin adds real stock via Admin Panel
#   - Real purchases ALSO send real notifications (both real + fake work together)
#   - Fake user names are randomly generated (look realistic)
#
# ──────────────────────────────────────────────────────────

import random
import asyncio
import logging
from datetime import datetime, timedelta
from utils import smart_text_and_mode

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 🎭 FAKE NAME GENERATOR
# ════════════════════════════════════════════════════════════════
# Generates realistic-looking masked usernames like: b***l, a***d, z***n
# These are shown in broadcast messages to look like real users.

# Pool of realistic first-letter + last-letter combinations
_FAKE_NAMES = [
    ("a", "d"), ("b", "l"), ("z", "n"), ("m", "d"), ("s", "a"),
    ("h", "n"), ("k", "r"), ("f", "i"), ("r", "a"), ("u", "r"),
    ("o", "n"), ("t", "k"), ("y", "b"), ("j", "d"), ("w", "z"),
    ("e", "h"), ("c", "o"), ("p", "l"), ("i", "s"), ("n", "l"),
    ("g", "r"), ("d", "n"), ("q", "m"), ("v", "t"), ("x", "r"),
    ("l", "k"), ("a", "n"), ("m", "r"), ("h", "d"), ("s", "r"),
]


def generate_fake_username(style="stars"):
    """
    Generate a masked fake username.

    Styles:
      'stars'    →  b***l       (default — looks like Telegram masked name)
      'initials' →  B.L.        (initials style)
      'random'   →  User#4821   (random user ID style)
    """
    if style == "stars":
        first, last = random.choice(_FAKE_NAMES)
        stars = "*" * random.randint(2, 4)
        return f"{first}{stars}{last}"
    elif style == "initials":
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return f"{random.choice(letters)}.{random.choice(letters)}."
    else:  # random
        return f"User#{random.randint(1000, 9999)}"


# ════════════════════════════════════════════════════════════════
# 💬 FAKE MESSAGE TEMPLATES
# ════════════════════════════════════════════════════════════════
# These are the message formats sent to users.
# {user} = fake masked username
# {product} = real product name from your DB
# {amount} = realistic random price
# {qty} = quantity
# {method} = payment method
# {referrals} = referral count
# {reward} = reward amount
# {total_ref} = total referral earnings
# {more} = how many more to next milestone
# {tier} = loyalty tier name

def make_purchase_msg(user, product, qty, amount):
    """🛒 New Purchase — uses admin-editable template."""
    try:
        from customization import render_template
        return render_template("bc_purchase", {
            "user": user, "product": product,
            "qty": str(qty), "amount": f"{amount:.2f}"
        })
    except Exception:
        return f"🛒 *New Purchase!* 🏪\n\n👤 User: {user}\n📦 Product: {product}\n🔢 QTY: {qty}\n\n_Thank you for choosing us_ 🛡️"


def make_deposit_msg(user, amount, method):
    """💳 New Deposit — uses admin-editable template."""
    try:
        from customization import render_template
        # 🆕 v170.5: pkr_amount + txid bhi pass karo (naya default template
        # inhe use karta hai — warna literal {pkr_amount}/{txid} dikh jata)
        import random as _rnd
        try:
            from database import get_setting
            pkr_rate = float(get_setting("usd_to_pkr_rate", "280") or 280)
        except Exception:
            pkr_rate = 280.0
        pkr_amount = f"Rs {int(float(amount) * pkr_rate):,}"
        txid = f"GEN-{_rnd.randint(100000, 999999)}"
        return render_template("bc_deposit", {
            "user": user, "amount": f"{amount:.2f}", "method": method,
            "pkr_amount": pkr_amount, "txid": txid,
        })
    except Exception:
        return f"💳 *New Deposit!* 💲\n\n👤 User: {user}\n💰 Amount: ${amount:.2f}\n🔵 Method: {method}\n\n_Processed automatically_ ⚡"


def make_referral_milestone_msg(user, referrals, reward, total_ref):
    """🏆 Referral Milestone — uses admin-editable template."""
    try:
        from customization import render_template
        return render_template("bc_referral", {
            "user": user, "referrals": str(referrals),
            "reward": f"{reward:.2f}", "total_ref": f"{total_ref:.2f}"
        })
    except Exception:
        return f"🏆 *Referral Milestone!*\n\n👤 User: {user}\n✅ Active Referrals: *{referrals}*"


def make_new_active_referral_msg(user, referrals, more):
    """📈 New Active Referral — uses admin-editable template."""
    try:
        from customization import render_template
        return render_template("bc_active_referral", {
            "user": user, "referrals": str(referrals), "more": str(more)
        })
    except Exception:
        return f"📈 *New Active Referral!*\n\n👤 Referrer: {user}\n✅ Active Referrals: *{referrals}*\n⏳ *{more} more* to earn next reward"


def make_tier_upgrade_msg(user, tier):
    """🎖️ Tier Upgrade — uses admin-editable template."""
    try:
        from customization import render_template
        return render_template("bc_tier", {"user": user, "tier": tier})
    except Exception:
        return f"🎖️ *Loyalty Tier Upgrade!*\n\n👤 User: {user}\n🏆 New Tier: *{tier}*\n\n_Keep shopping!_ 💎"


def make_new_stock_msg(product, stock, price_usd, pkr_rate=280):
    """
    🔔 New Stock Alert — REAL message, only sent when admin adds actual stock.

    This is NOT fake. This fires automatically when:
      - Admin adds a new product with stock > 0
      - Admin updates stock on an existing product from 0 → positive

    pkr_rate is fetched from DB settings (USD_TO_PKR_RATE).
    """
    pkr = int(price_usd * pkr_rate)
    return (
        f"🔔 *New stock available!*\n\n"
        f"🏪 Product: {product}\n"
        f"✅ Available Now: {stock}\n\n"
        f"_Hurry up and buy now from the store!_ 🛒\n\n"
        f"💰 Price: ${price_usd:.2f}"
    )


def make_discount_msg(product, old_price, new_price):
    """🔥 Discount — uses admin-editable template."""
    try:
        from customization import render_template
        return render_template("bc_discount", {
            "product": product,
            "old_price": f"{old_price:.1f}",
            "new_price": f"{new_price:.1f}"
        })
    except Exception:
        return f"📉 *Amazing Discount!* 🔥\n\nProduct: {product}\nOld price: ~~${old_price:.1f}~~\nNew price: *${new_price:.1f} only!*\n\nHurry and buy now!"


# ════════════════════════════════════════════════════════════════
# 🎲 FAKE DATA GENERATORS
# ════════════════════════════════════════════════════════════════
# These functions pick realistic random values for fake messages.

PAYMENT_METHODS = ["Binance Pay", "JazzCash", "EasyPaisa"]


def _enabled_payment_methods():
    """🆕 v102 / 🐛 v147 FIX (Bug5): return ONLY the payment methods admin has
    enabled via the payment toggles. The old list had only 3 entries
    (Binance/JazzCash/EasyPaisa) and NO Bybit/USDT entries — so with
    jazzcash+easypaisa off, EVERY fake deposit alert said "Binance Pay".
    Now every toggleable external method participates; disabled ones never
    appear. "points" is excluded (it's not an external deposit method)."""
    try:
        from database import is_payment_enabled
        pairs = [
            ("binance",         "Binance Pay"),
            ("usdt_trc20",      "Binance USDT TRC20"),
            ("usdt_bep20",      "Binance USDT BEP20"),
            ("bybit",           "Bybit"),
            ("bybit_pay",       "Bybit Pay"),
            ("bybit_usdt_trc20", "Bybit USDT TRC20"),
            ("bybit_usdt_bep20", "Bybit USDT BEP20"),
            ("jazzcash",        "JazzCash"),
            ("easypaisa",       "EasyPaisa"),
        ]
        enabled = [label for method, label in pairs if is_payment_enabled(method)]
        return enabled or ["Binance Pay"]
    except Exception:
        return PAYMENT_METHODS

REFERRAL_MILESTONES = [10, 25, 50, 100, 150, 200, 250, 300, 500]

TIER_NAMES = [
    "🥉 Bronze", "🥈 Silver", "🥇 Gold", "💎 Platinum", "💠 Diamond"
]


def random_amount(min_usd=1.5, max_usd=50.0):
    """Generate a realistic random USD amount."""
    # Weighted towards smaller amounts (more realistic for a digital store)
    weights = [40, 30, 20, 10]  # small, medium, large, xlarge
    ranges = [(1.5, 5), (5, 15), (15, 30), (30, max_usd)]
    chosen_range = random.choices(ranges, weights=weights)[0]
    amount = random.uniform(*chosen_range)
    # Round to nearest .5 or .0 to look clean
    return round(round(amount * 2) / 2, 2)


def random_qty():
    """Generate a realistic quantity (mostly 1, sometimes more)."""
    return random.choices([1, 1, 1, 2, 3, 5, 10], weights=[50, 20, 15, 8, 4, 2, 1])[0]


def random_referral_data():
    """Generate realistic referral milestone data."""
    milestone = random.choice(REFERRAL_MILESTONES)
    extra = random.randint(0, 5)
    referrals = milestone + extra
    reward = round(milestone * 0.003, 2)  # ~$0.03 per 10 referrals
    total_ref = round(reward * random.uniform(1.5, 8), 2)
    more = random.randint(1, 15)
    return referrals, reward, total_ref, more


# ════════════════════════════════════════════════════════════════
# ⚙️ SETTINGS KEYS (stored in bot_settings DB table)
# ════════════════════════════════════════════════════════════════
# These are the keys used to store admin preferences in the database.
# Admin changes these from the Fake Broadcast Panel in Admin Panel.
# You don't need to change anything here manually.

SETTING_ENABLED        = "fbc_enabled"           # "1" or "0" — master on/off switch
SETTING_FAKE_OFFSET    = "fake_user_offset"       # baseline fake user number           # "1" or "0" — master on/off switch
SETTING_MIN_INTERVAL   = "fbc_min_interval"       # minimum minutes between broadcasts (default: 5)
SETTING_MAX_INTERVAL   = "fbc_max_interval"       # maximum minutes between broadcasts (default: 60)
SETTING_TYPE_PURCHASE  = "fbc_type_purchase"      # "1" or "0" — send fake purchases?
SETTING_TYPE_DEPOSIT   = "fbc_type_deposit"       # "1" or "0" — send fake deposits?
SETTING_TYPE_REFERRAL  = "fbc_type_referral"      # "1" or "0" — send fake referrals?
SETTING_TYPE_TIER      = "fbc_type_tier"          # "1" or "0" — send fake tier upgrades?
SETTING_TYPE_STOCK     = "fbc_type_stock"         # "1" or "0" — send real new stock alerts?
SETTING_TYPE_DISCOUNT  = "fbc_type_discount"      # "1" or "0" — send fake discount alerts?
SETTING_TYPE_FREECLAIM = "fbc_type_freeclaim"     # 🆕 v110: fake free-via-referrals claims (uses per-product fc_btn)
SETTING_TYPE_FREEBIE   = "fbc_type_freebie"       # 🆕 v170.14: fake freebie claims
SETTING_TYPE_BULKDEAL  = "fbc_type_bulkdeal"      # 🆕 v161.12: fake bulk-discount hype (products WITH tiers)
SETTING_TYPE_RESELLER  = "fbc_type_reseller"      # 🆕 v161.12: reseller API purchase hype
SETTING_TYPE_NEWUSER   = "fbc_type_newuser"       # 🆕 v161.19: new member joined
SETTING_TYPE_NEWPROD   = "fbc_type_newprod"       # 🆕 v161.19: new product announcement
SETTING_TYPE_FLASH     = "fbc_type_flash"         # 🆕 v161.19: flash sale hype
SETTING_TYPE_PRICEDROP = "fbc_type_pricedrop"     # 🆕 v161.19: big price drop
SETTING_TYPE_REVIEW    = "fbc_type_review"        # 🆕 v161.19: new product review
SETTING_TYPE_MILESTONE = "fbc_type_milestone"     # 🆕 v161.19: referral milestone reached
SETTING_NAME_STYLE     = "fbc_name_style"         # "stars" / "initials" / "random"
SETTING_LOG_ENABLED    = "fbc_log_enabled"        # "1" or "0" — save broadcast log to DB?


def _get(key, default=""):
    """Safely get a setting from DB."""
    try:
        from database import get_setting
        return get_setting(key, default)
    except Exception:
        return default


def _set(key, value):
    """Safely set a setting in DB."""
    try:
        from database import set_setting
        set_setting(key, str(value))
    except Exception:
        pass


def is_enabled():
    """Returns True if fake broadcast system is turned ON by admin."""
    return _get(SETTING_ENABLED, "0") == "1"


def get_interval_range():
    """
    Returns (min_minutes, max_minutes) for random broadcast scheduling.
    Default: 5 to 60 minutes.
    """
    try:
        min_m = int(_get(SETTING_MIN_INTERVAL, "5"))
        max_m = int(_get(SETTING_MAX_INTERVAL, "60"))
        if min_m < 1:
            min_m = 1
        if max_m < min_m:
            max_m = min_m + 5
        return min_m, max_m
    except Exception:
        return 5, 60


def get_name_style():
    """Returns the current fake name style: 'stars', 'initials', or 'random'."""
    return _get(SETTING_NAME_STYLE, "stars")


def _get_freeclaim_broadcastable_products():
    """🆕 v110: Return list of product_ids that are enabled for
    Free-via-Referrals AND still buyable (in-stock, not hidden). Used by
    the fake-broadcast engine to pick a random product for the fake
    'someone just claimed X for free' announcement.
    """
    try:
        from database import (get_connection, is_product_hidden,
                              get_product)
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT product_id FROM product_free_claim WHERE enabled=1")
        raw = [int(r["product_id"]) for r in (c.fetchall() or [])]
        conn.close()
    except Exception:
        return []
    out = []
    for pid in raw:
        try:
            p = get_product(pid)
            if not p: continue
            if int(p["stock"] or 0) <= 0: continue
            try:
                if is_product_hidden(pid): continue
            except Exception: pass
            out.append(pid)
        except Exception:
            pass
    return out


def _get_freebie_broadcastable_products():
    """🆕 v170.14: freebie product ids jo enabled + in-stock + not-hidden hain.
    Fake freebie-claim broadcasts inhi se pick karte hain."""
    out = []
    try:
        from database import (get_all_freebie_products, get_product,
                              is_product_hidden)
        for f in get_all_freebie_products():
            pid = int(f.get("product_id") or 0)
            if not pid:
                continue
            try:
                p = get_product(pid)
                if not p or int(p["stock"] or 0) <= 0:
                    continue
                if is_product_hidden(pid):
                    continue
                out.append(pid)
            except Exception:
                pass
    except Exception:
        pass
    return out


def _get_products_with_tiers():
    """🆕 v161.12: product ids that have at least one bulk-discount tier AND are
    buyable (in-stock, not hidden). Used by fake bulk-deal hype broadcasts."""
    out = []
    try:
        from database import (get_connection, is_product_hidden, get_product,
                              get_product_tiers)
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT DISTINCT product_id FROM product_tier_discounts")
        raw = [int(r["product_id"]) for r in (c.fetchall() or [])]
        conn.close()
        for pid in raw:
            try:
                p = get_product(pid)
                if not p:
                    continue
                if int(p["stock"] or 0) <= 0:
                    continue
                try:
                    if is_product_hidden(pid):
                        continue
                except Exception:
                    pass
                if get_product_tiers(pid):
                    out.append(pid)
            except Exception:
                pass
    except Exception:
        pass
    return out


def _get_lowest_tier(pid):
    """🆕 v161.12: return (qty, unit_price) of the cheapest tier for a product."""
    try:
        from database import get_product_tiers
        tiers = get_product_tiers(pid) or []
        if not tiers:
            return None
        best = None
        for t in tiers:
            q = int(t.get("min_qty") or 0)
            u = float(t.get("unit_price") or 0)
            if u > 0 and (best is None or u < best[1]):
                best = (q, u)
        return best
    except Exception:
        return None


def notify_reseller_purchase_raw(product_name, qty, amount_usd, pid=0,
                                 reseller_label="", bot_token="", dest_override=None):
    """🆕 v161.12: fire a Reseller-API purchase alert to the configured fake-activity
    destination via RAW Telegram HTTP API (no PTB bot object — called from the
    FastAPI reseller module). Returns number of successful sends."""
    try:
        import requests as _rq
        if not bot_token:
            import os as _os
            bot_token = (_os.getenv("BOT_TOKEN") or "").strip()
        if not bot_token:
            return 0
        from customization import render_template as _rt
        user = generate_fake_username(get_name_style())
        reseller = (reseller_label or user)
        text = _rt("bc_reseller", {
            "user": user, "product": (str(product_name) or "Product")[:200],
            "qty": str(qty), "amount": f"{float(amount_usd or 0):.2f}",
            "reseller": reseller,
        }) or (f"🔗 *Reseller Purchase!* 🚀\n\n👤 Reseller: {reseller}\n"
               f"📦 Product: {product_name}\n🔢 QTY: {qty}\n💰 ${amount_usd:.2f}\n\n"
               f"⚡ Auto-delivered via Reseller API!")
        t, m = smart_text_and_mode(text, "Markdown")
        kb = None
        if pid:
            try:
                me = _rq.get(f"https://api.telegram.org/bot{bot_token}/getMe",
                             timeout=10).json()
                _uname = (me.get("result") or {}).get("username", "")
                if _uname:
                    deep = f"https://t.me/{_uname}?start=buy_{pid}"
                    kb = {"inline_keyboard": [[{"text": "🛒 Buy Now", "url": deep}]]}
            except Exception:
                kb = None
        mode = dest_override or _g("dest_mode", "bot_only")
        dest_chat = _g("dest_chat_id", "").strip()
        sent = 0

        def _send(chat_id, is_group=False):
            nonlocal sent
            try:
                payload = {"chat_id": chat_id, "text": t, "parse_mode": m,
                           "disable_web_page_preview": True}
                if kb and is_group:
                    payload["reply_markup"] = kb
                r = _rq.post(f"https://api.telegram.org/bot{bot_token}/sendMessage",
                             json=payload, timeout=15)
                if r.status_code < 300:
                    sent += 1
            except Exception:
                pass

        # group/channel destination always gets the alert (with Buy Now button)
        if mode in ("group_only", "both") and dest_chat:
            _send(dest_chat, is_group=True)
        if mode in ("bot_only", "both"):
            try:
                from database import get_all_users_for_broadcast, row_uid
                for usr in get_all_users_for_broadcast() or []:
                    uid = row_uid(usr)
                    _send(uid, is_group=False)
            except Exception:
                pass
        return sent
    except Exception:
        return 0


def is_type_enabled(type_key):
    """
    Check if a specific broadcast type is enabled.
    type_key values: 'purchase', 'deposit', 'referral', 'tier', 'stock', 'discount'
    """
    setting_map = {
        "purchase": SETTING_TYPE_PURCHASE,
        "deposit":  SETTING_TYPE_DEPOSIT,
        "referral": SETTING_TYPE_REFERRAL,
        "tier":     SETTING_TYPE_TIER,
        "stock":    SETTING_TYPE_STOCK,
        "discount": SETTING_TYPE_DISCOUNT,
        "freeclaim": SETTING_TYPE_FREECLAIM,  # 🆕 v110
        "freebie":  SETTING_TYPE_FREEBIE,    # 🆕 v170.14
        "bulkdeal": SETTING_TYPE_BULKDEAL,    # 🆕 v161.12
        "reseller": SETTING_TYPE_RESELLER,    # 🆕 v161.12
        "newuser":   SETTING_TYPE_NEWUSER,    # 🆕 v161.19
        "newprod":   SETTING_TYPE_NEWPROD,    # 🆕 v161.19
        "flash":     SETTING_TYPE_FLASH,      # 🆕 v161.19
        "pricedrop": SETTING_TYPE_PRICEDROP,  # 🆕 v161.19
        "review":    SETTING_TYPE_REVIEW,     # 🆕 v161.19
        "milestone": SETTING_TYPE_MILESTONE,  # 🆕 v161.19
    }
    key = setting_map.get(type_key)
    if not key:
        return False
    return _get(key, "1") == "1"   # Default: all ON


# ════════════════════════════════════════════════════════════════
# 📋 BROADCAST LOG
# ════════════════════════════════════════════════════════════════
# Keeps track of the last broadcasts sent.
# Stored in memory (resets on bot restart).
# Max 50 entries kept.

_broadcast_log = []   # list of dicts: {time, type, message_preview, recipients}
MAX_LOG = 50


def _log_broadcast(btype, preview, recipients):
    """Add entry to broadcast log."""
    _broadcast_log.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "type": btype,
        "preview": preview[:60] + "..." if len(preview) > 60 else preview,
        "recipients": recipients,
    })
    # Keep only last MAX_LOG entries
    if len(_broadcast_log) > MAX_LOG:
        _broadcast_log.pop(0)


def get_broadcast_log():
    """Returns list of recent broadcasts (newest first)."""
    return list(reversed(_broadcast_log))


# ════════════════════════════════════════════════════════════════
# 📤 CORE SENDER
# ════════════════════════════════════════════════════════════════
# This function does the actual sending to all users.

async def send_to_all_users(bot, message: str, parse_mode="Markdown", max_recipients=0):
    """
    Send a message to ALL real registered users.
    Uses get_all_users_for_broadcast() which already excludes fake reviewer entries.
    Returns (success_count, fail_count)

    🆕 v168 SPEED OPTIMIZATION: Uses asyncio.gather() batches of 15 concurrent
    sends instead of one-by-one sequential. Reduces broadcast time from 3+ min
    to ~15 seconds for 1100 users. Sleep reduced from 0.05s/msg to 0.1s/batch.

    🆕 PREMIUM EMOJI SUPPORT:
    If the message starts with the "[[HTML]]" sentinel (added by the
    template editor when the admin used premium / custom emojis or
    native Telegram formatting), strip the marker and send with
    parse_mode="HTML". This preserves <tg-emoji emoji-id="...">😀</tg-emoji>
    tags so premium emojis are rendered for premium users.
    Requires the bot OWNER to have Telegram Premium (per Bot API spec).

    🆕 v168 max_recipients: if >0, only send to first N users (useful for
    non-critical broadcasts to save API quota).
    """
    try:
        from database import get_all_users_for_broadcast
        users = get_all_users_for_broadcast()  # Real users only, no fake reviewers
    except Exception as e:
        logger.error(f"[FakeBroadcast] Could not fetch users: {e}")
        return 0, 0

    # 🆕 v168: optional cap on recipients
    if max_recipients and max_recipients > 0 and len(users) > max_recipients:
        import random as _rnd
        users = _rnd.sample(list(users), max_recipients)

    # Auto-detect premium/custom emoji markup anywhere in the message
    effective_text, effective_mode = smart_text_and_mode(message, parse_mode)

    success = 0
    fail = 0
    # 🐛 v153 FIX: row_uid handles DictRow — old code sent to the auto-increment
    # id column instead of the real Telegram user_id.
    try:
        from database import row_uid as _row_uid
    except Exception:
        _row_uid = None

    # 🆕 v168: BATCH SENDING with asyncio.gather() for 10x speed
    BATCH_SIZE = 15  # Safe under Telegram's 30 msg/sec limit

    async def _send_one(uid):
        try:
            await bot.send_message(chat_id=uid, text=effective_text, parse_mode=effective_mode)
            return True
        except Exception:
            try:
                await bot.send_message(chat_id=uid, text=effective_text)
                return True
            except Exception:
                return False

    # Process in batches
    for i in range(0, len(users), BATCH_SIZE):
        batch = users[i:i + BATCH_SIZE]
        tasks = []
        for user in batch:
            try:
                uid = _row_uid(user) if _row_uid else (user["user_id"] if isinstance(user, dict) else user[1])
                if uid:
                    tasks.append(_send_one(uid))
            except Exception:
                fail += 1
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if r is True:
                    success += 1
                else:
                    fail += 1
        # Short pause between batches (safe under rate limit)
        await asyncio.sleep(0.1)

    return success, fail


# ════════════════════════════════════════════════════════════════
# 🎯 FAKE BROADCAST SELECTOR
# ════════════════════════════════════════════════════════════════
# Picks which type of fake message to send based on:
#   1. Which types are enabled by admin
#   2. Weighted random selection (purchases most common, tier rarest)
#   3. Real products from DB (only in-stock products used)

async def run_fake_broadcast(bot, force_type=None):
    """
    Main function: picks a fake message type, generates the message,
    and sends it to all users.

    Args:
        bot: Telegram Bot instance
        force_type: if set, skip random selection and use this type
                    ('purchase', 'deposit', 'referral', 'tier', 'discount')
                    When force_type is set, ALL checks are bypassed (for testing).

    Returns:
        (type_sent, success_count, fail_count) or (None, 0, 0) if skipped
    """
    is_test = force_type is not None  # Test mode — bypass all guards

    # ── Master switch check (skip only for non-test calls) ──
    if not is_enabled() and not is_test:
        return None, 0, 0

    # 🐛 v147 FIX: fake broadcast must NOT run during maintenance mode.
    if not is_test:
        try:
            from maintenance_mode import is_maintenance_on
            if is_maintenance_on():
                logger.info("[FakeBroadcast] SKIPPED — maintenance ON")
                return None, 0, 0
        except Exception:
            pass

    # ── Get real in-stock, NOT-hidden products ──
    # 🆕 v60: get_all_products() now excludes hidden by default. Belt-and-suspenders:
    # also explicitly re-check stock + is_hidden so a race-condition (admin hiding
    # a product mid-cycle) can't sneak a hidden product into a fake broadcast.
    try:
        from database import get_all_products, is_product_hidden, is_product_fake_off
        all_products = []
        for p in get_all_products():
            d = dict(p) if not isinstance(p, dict) else p
            pid_ = d.get("id")
            if not pid_: continue
            if int(d.get("stock", 0) or 0) <= 0:   # out of stock → skip
                continue
            try:
                if is_product_hidden(pid_):         # hidden → skip
                    continue
            except Exception:
                pass
            # 🆕 v169: Exclude test/API products from broadcasts
            pname = (d.get("name") or "").lower()
            if "api test" in pname or "apitest" in pname:
                continue
            # 🆕 v170.5: admin ka per-product "fake activity OFF" flag
            try:
                if is_product_fake_off(pid_):
                    continue
            except Exception:
                pass
            all_products.append(p)
    except Exception:
        all_products = []

    # Fallback product info for test mode when shop is empty
    product_pid = None
    if not all_products:
        if is_test:
            product_name = "ChatGPT Plus 1 Month"
            product_price = 5.0
        else:
            logger.info("[FakeBroadcast] No in-stock products — skipping.")
            return None, 0, 0
    else:
        product = random.choice(all_products)
        if isinstance(product, dict):
            product_name = product.get("name", "Unknown Product")
            product_price = float(product.get("price", 5.0))
            try:
                product_pid = product.get("id")
            except Exception:
                product_pid = None
        else:
            product_name = product[2]
            product_price = float(product[4] or 5.0)
            try:
                product_pid = product[0]
            except Exception:
                product_pid = None

    # ── Determine which types are available (for non-test auto mode) ──
    type_weights = {
        "purchase": 40,
        "deposit":  25,
        "referral": 20,
        "tier":     10,
        "discount":  5,
        # 🆕 v110: fake free-via-referrals claims. Only shown when there's at
        # least one enabled + in-stock free-claim product; auto-eligibility
        # filter happens below in the availability check.
        "freeclaim": 15,
        # 🆕 v170.14: fake freebie claims (free products)
        "freebie": 12,
        # 🆕 v161.12: fake bulk-deal hype (products WITH tiers) + reseller hype
        "bulkdeal": 10,
        "reseller": 6,
        # 🆕 v161.19: extra hype types
        "newuser":   4,
        "newprod":   4,
        "flash":     4,
        "pricedrop": 5,
        "review":    6,
        "milestone": 4,
    }

    if is_test:
        # Test mode — use force_type directly, no enable-check needed
        chosen_type = force_type
    else:
        # 🆕 v110: also skip 'freeclaim' if no eligible product available
        freeclaim_ready = bool(_get_freeclaim_broadcastable_products())
        # 🆕 v170.14: freebie only when a freebie product exists
        freebie_ready = bool(_get_freebie_broadcastable_products())
        # 🆕 v161.12: bulkdeal only when a product with tiers exists
        bulkdeal_ready = bool(_get_products_with_tiers())
        available_types = []
        weights = []
        for ttype, weight in type_weights.items():
            if not is_type_enabled(ttype):
                continue
            if ttype == "freeclaim" and not freeclaim_ready:
                continue
            if ttype == "freebie" and not freebie_ready:
                continue
            if ttype == "bulkdeal" and not bulkdeal_ready:
                continue
            available_types.append(ttype)
            weights.append(weight)

        if not available_types:
            logger.info("[FakeBroadcast] All types disabled — nothing to send.")
            return None, 0, 0

        chosen_type = random.choices(available_types, weights=weights)[0]

    # ── Get name style & fake user ──
    name_style = get_name_style()
    user = generate_fake_username(name_style)

    # ── Build the message ──
    msg = None

    if chosen_type == "purchase":
        qty = random_qty()
        amount = round(product_price * qty, 2)
        msg = make_purchase_msg(user, product_name, qty, amount)

    elif chosen_type == "deposit":
        amount = random_amount()
        method = random.choice(_enabled_payment_methods())
        msg = make_deposit_msg(user, amount, method)

    elif chosen_type == "referral":
        referrals, reward, total_ref, more = random_referral_data()
        # 50/50: either milestone or new active referral
        if random.random() < 0.5:
            msg = make_referral_milestone_msg(user, referrals, reward, total_ref)
        else:
            msg = make_new_active_referral_msg(user, referrals, more)

    elif chosen_type == "tier":
        tier = random.choice(TIER_NAMES)
        msg = make_tier_upgrade_msg(user, tier)

    elif chosen_type == "discount":
        old_price = product_price
        discount_pct = random.choice([5, 10, 12.5, 15, 20])
        new_price = round(old_price * (1 - discount_pct / 100) * 2) / 2
        if new_price >= old_price:
            new_price = round(old_price - 0.5, 1)
        msg = make_discount_msg(product_name, old_price, new_price)

    elif chosen_type == "freeclaim":
        # 🆕 v110: Fake free-via-referrals claim broadcast.
        # Picks a random enabled+in-stock free-claim product, renders the
        # per-product custom template (or per-product picked template, or
        # global) with a masked fake username, then routes through the
        # normal broadcast_store_message so the per-product `fc_btn_<pid>`
        # button (text + premium emoji + size + color) is attached.
        try:
            eligible = _get_freeclaim_broadcastable_products()
            if not eligible:
                logger.info("[FakeBroadcast] freeclaim: no eligible product — skip")
                return None, 0, 0
            fc_pid = random.choice(eligible)
            from database import get_product_free_config as _gpfc, get_product as _gp
            fc_prod = _gp(fc_pid)
            fc_cfg = _gpfc(fc_pid) or {}
            fc_pname = (dict(fc_prod).get("name", "product") if fc_prod else "product")
            try:
                from templates_bundle import build_free_claim_message
            except Exception:
                from handlers_free_claim import build_free_claim_message
            fc_msg = build_free_claim_message(
                user_name=user,
                product_name=fc_pname,
                refs_used=int(fc_cfg.get("required_refs") or 5),
                tpl_index=(int(fc_cfg.get("tpl_index"))
                           if fc_cfg.get("tpl_index") is not None else -1),
                custom_text=fc_cfg.get("custom_text") or "",
                shop_name=None,  # auto SHOP_NAME
            )
            # Route through broadcast_store_message so fc_btn_<pid> styled
            # button (color, emoji, size) is attached to the fake claim.
            try:
                from handlers_free_claim import fc_btn_has_custom as _fcb
                _use_key = f"fc_btn_{fc_pid}" if _fcb(fc_pid) else None
            except Exception:
                _use_key = None
            success = await broadcast_store_message(
                bot, fc_msg, pid=fc_pid,
                tpl_id=_use_key,
                btn_key=(None if _use_key else "sb_buy_generic"),
            )
            fail = 0  # broadcast_store_message returns sent count only
            _log_broadcast("freeclaim", fc_msg, success)
            logger.info(f"[FakeBroadcast] Done freeclaim — ✅ {success} sent")
            return chosen_type, success, fail
        except Exception as _e:
            logger.exception(f"[FakeBroadcast] freeclaim failed: {_e}")
            return None, 0, 0

    # 🆕 v170.14: FAKE FREEBIE CLAIM — "someone got a free product"
    if chosen_type == "freebie":
        try:
            eligible = _get_freebie_broadcastable_products()
            if not eligible:
                logger.info("[FakeBroadcast] freebie: no eligible product — skip")
                return None, 0, 0
            fb_pid = random.choice(eligible)
            from database import get_product as _gp2
            fb_prod = _gp2(fb_pid)
            fb_name = (dict(fb_prod).get("name", "product") if fb_prod else "product")
            try:
                from utils import html_strip_tags as _hst2
                fb_name = _hst2(fb_name)
            except Exception:
                pass
            fb_msg = _rt("bc_freebie", {"user": user, "product": fb_name})
            if not fb_msg:
                fb_msg = (f"🎁 *FREEBIE CLAIMED!* 🎉\\n\\n"
                          f"👤 {user} just got {fb_name} for FREE!\\n"
                          f"🆓 100% free — tap below and grab yours too!")
            success = await broadcast_store_message(bot, fb_msg, pid=fb_pid,
                                                    tpl_id="bc_freebie")
            _log_broadcast("freebie", fb_msg, success)
            logger.info(f"[FakeBroadcast] Done freebie — ✅ {success} sent")
            return chosen_type, success, 0
        except Exception as _e:
            logger.exception(f"[FakeBroadcast] freebie failed: {_e}")
            return None, 0, 0

    # 🆕 v161.12: FAKE BULK-DEAL HYPE — "people are bulk-buying this product"
    # picks a random product that HAS bulk tiers and routes through
    # broadcast_store_message so the styled Buy Now button is attached.
    if chosen_type == "bulkdeal":
        try:
            from database import get_product as _gp
            eligible = _get_products_with_tiers()
            if not eligible:
                logger.info("[FakeBroadcast] bulkdeal: no tiered product — skip")
                return None, 0, 0
            bd_pid = random.choice(eligible)
            _tier = _get_lowest_tier(bd_pid)
            p = _gp(bd_pid)
            if not _tier or not p:
                return None, 0, 0
            bd_qty, bd_price = _tier
            bd_name = (dict(p).get("name", "product") if p else "product")
            try:
                from utils import html_strip_tags as _hst
                bd_name = _hst(bd_name)
            except Exception:
                pass
            try:
                bd_base = float(dict(p).get("price") or bd_price)
            except Exception:
                bd_base = float(bd_price)
            saving = round(max(0.0, bd_base - bd_price), 2)
            try:
                from customization import render_template as _rt
                bd_msg = _rt("bc_bulkdeal", {
                    "user": user, "product": bd_name, "qty": str(bd_qty),
                    "price": f"{bd_price:.2f}", "base_price": f"{bd_base:.2f}",
                    "saving": f"{saving:.2f}"})
            except Exception:
                bd_msg = None
            if not bd_msg:
                bd_msg = (f"📊 *Bulk Deal Alert!* 🎉\n\n"
                          f"👤 {user} just grabbed {bd_name} at bulk price!\n"
                          f"🛒 {bd_qty}+ qty → 💵 ${bd_price:.2f} each\n"
                          f"❌ Base: ${bd_base:.2f} | 💸 Save ${saving:.2f} per unit\n\n"
                          f"🔥 Buy more, save more — tap below!")
            success = await broadcast_store_message(bot, bd_msg, pid=bd_pid,
                                                    tpl_id="bc_bulkdeal")
            _log_broadcast("bulkdeal", bd_msg, success)
            logger.info(f"[FakeBroadcast] Done bulkdeal — ✅ {success} sent")
            return chosen_type, success, 0
        except Exception as _e:
            logger.exception(f"[FakeBroadcast] bulkdeal failed: {_e}")
            return None, 0, 0

    # 🆕 v161.12: FAKE RESELLER PURCHASE HYPE — makes the reseller API look
    # busy ("a reseller just sold X through the API"). No product required;
    # when a product is available we attach its Buy Now button.
    if chosen_type == "reseller":
        try:
            _pid_for_btn = None
            _prod_for_btn = None
            if all_products:
                _prod_for_btn = random.choice(all_products)
                try:
                    _pid_for_btn = _prod_for_btn.get("id") if isinstance(_prod_for_btn, dict) else _prod_for_btn[0]
                except Exception:
                    _pid_for_btn = None
                _pname_for_btn = (dict(_prod_for_btn).get("name", "Product")
                                  if _prod_for_btn else "Product")
                _pprice_for_btn = float(dict(_prod_for_btn).get("price", 5.0)
                                        if _prod_for_btn else 5.0)
            else:
                _pname_for_btn = "Premium Product"
                _pprice_for_btn = 5.0
            r_qty = random_qty()
            r_amount = round(_pprice_for_btn * r_qty, 2)
            r_reseller = generate_fake_username(name_style)
            try:
                from customization import render_template as _rt
                r_msg = _rt("bc_reseller", {
                    "user": user, "product": _pname_for_btn, "qty": str(r_qty),
                    "amount": f"{r_amount:.2f}", "reseller": r_reseller})
            except Exception:
                r_msg = None
            if not r_msg:
                r_msg = (f"🔗 *Reseller Purchase!* 🚀\n\n"
                         f"👤 Reseller: {r_reseller}\n"
                         f"📦 Product: {_pname_for_btn}\n"
                         f"🔢 QTY: {r_qty}\n"
                         f"💰 Amount: ${r_amount:.2f}\n\n"
                         f"⚡ Auto-delivered via Reseller API!")
            success = await broadcast_store_message(bot, r_msg,
                                                    pid=_pid_for_btn,
                                                    tpl_id="bc_reseller")
            _log_broadcast("reseller", r_msg, success)
            logger.info(f"[FakeBroadcast] Done reseller — ✅ {success} sent")
            return chosen_type, success, 0
        except Exception as _e:
            logger.exception(f"[FakeBroadcast] reseller failed: {_e}")
            return None, 0, 0

    # 🆕 v161.19: NEW MEMBER JOINED
    if chosen_type == "newuser":
        try:
            from database import get_user_count as _guc
            count = _guc() or 0
            nm = generate_fake_username(name_style)
            try:
                from customization import render_template as _rt
                n_msg = _rt("bc_new_user", {"name": nm, "count": str(count)})
            except Exception:
                n_msg = None
            if not n_msg:
                n_msg = f"🎉 New member joined Bite Store! 🛍️\n\n👤 {nm} just joined!\n👥 Members: {count}"
            success = await broadcast_store_message(bot, n_msg, pid=None, tpl_id="bc_new_user")
            _log_broadcast("newuser", n_msg, success)
            return chosen_type, success, 0
        except Exception as _e:
            logger.exception(f"[FakeBroadcast] newuser failed: {_e}")
            return None, 0, 0

    # 🆕 v161.19: NEW PRODUCT ANNOUNCEMENT
    if chosen_type == "newprod":
        try:
            _pid = None
            if all_products:
                _p = random.choice(all_products)
                try:
                    _pid = _p.get("id") if isinstance(_p, dict) else _p[0]
                except Exception:
                    _pid = None
                _pn = (dict(_p).get("name", "Product") if _p else "Product")
                _pr = float(dict(_p).get("price", 5.0) if _p else 5.0)
            else:
                _pn, _pr = "New Premium Product", 5.0
            try:
                from customization import render_template as _rt
                n_msg = _rt("bc_newprod", {"product": _pn, "price": f"{_pr:.2f}"})
            except Exception:
                n_msg = None
            if not n_msg:
                n_msg = f"🆕 *New Product Available!*\n\n📦 {_pn}\n💰 ${_pr:.2f}\n\n🔥 Fresh stock — get yours now!"
            success = await broadcast_store_message(bot, n_msg, pid=_pid, tpl_id="bc_newprod")
            _log_broadcast("newprod", n_msg, success)
            return chosen_type, success, 0
        except Exception as _e:
            logger.exception(f"[FakeBroadcast] newprod failed: {_e}")
            return None, 0, 0

    # 🆕 v161.19: FLASH SALE HYPE
    if chosen_type == "flash":
        try:
            _pid = None
            _pn, _pr = "Premium Product", 5.0
            if all_products:
                _p = random.choice(all_products)
                try:
                    _pid = _p.get("id") if isinstance(_p, dict) else _p[0]
                except Exception:
                    _pid = None
                _pn = (dict(_p).get("name", "Product") if _p else "Product")
                _pr = float(dict(_p).get("price", 5.0) if _p else 5.0)
            flash_price = round(_pr * 0.6, 2)  # 40% off fake flash
            try:
                from customization import render_template as _rt
                n_msg = _rt("sb_flash", {"product": _pn, "old_price": f"{_pr:.2f}", "new_price": f"{flash_price:.2f}"})
            except Exception:
                n_msg = None
            if not n_msg:
                n_msg = f"⚡ *FLASH SALE!* 🔥\n\n📦 {_pn}\n❌ Was ${_pr:.2f}\n💥 Now ${flash_price:.2f}\n\n⏰ Limited time only!"
            success = await broadcast_store_message(bot, n_msg, pid=_pid, tpl_id="sb_flash")
            _log_broadcast("flash", n_msg, success)
            return chosen_type, success, 0
        except Exception as _e:
            logger.exception(f"[FakeBroadcast] flash failed: {_e}")
            return None, 0, 0

    # 🆕 v161.19: PRICE DROP HYPE
    if chosen_type == "pricedrop":
        try:
            _pid = None
            _pn, _pr = "Premium Product", 5.0
            if all_products:
                _p = random.choice(all_products)
                try:
                    _pid = _p.get("id") if isinstance(_p, dict) else _p[0]
                except Exception:
                    _pid = None
                _pn = (dict(_p).get("name", "Product") if _p else "Product")
                _pr = float(dict(_p).get("price", 5.0) if _p else 5.0)
            old_price = round(_pr * 1.25, 2)
            try:
                from customization import render_template as _rt
                n_msg = _rt("bc_pricedrop", {"product": _pn, "old_price": f"{old_price:.2f}", "new_price": f"{_pr:.2f}"})
            except Exception:
                n_msg = None
            if not n_msg:
                n_msg = f"💥 *PRICE DROP!* 📉\n\n📦 {_pn}\n❌ Was ${old_price:.2f}\n✅ Now ${_pr:.2f}\n\n🛒 Grab it before it goes back up!"
            success = await broadcast_store_message(bot, n_msg, pid=_pid, tpl_id="bc_pricedrop")
            _log_broadcast("pricedrop", n_msg, success)
            return chosen_type, success, 0
        except Exception as _e:
            logger.exception(f"[FakeBroadcast] pricedrop failed: {_e}")
            return None, 0, 0

    # 🆕 v161.19: NEW REVIEW HYPE
    if chosen_type == "review":
        try:
            _pid = None
            _pn = "Premium Product"
            if all_products:
                _p = random.choice(all_products)
                try:
                    _pid = _p.get("id") if isinstance(_p, dict) else _p[0]
                except Exception:
                    _pid = None
                _pn = (dict(_p).get("name", "Product") if _p else "Product")
            nm = generate_fake_username(name_style)
            stars = "⭐" * random.choice([4, 4, 5, 5, 5])
            review = "Bohat acha product hai, highly recommended!"
            try:
                from customization import render_template as _rt
                n_msg = _rt("bc_review", {"user": nm, "product": _pn, "stars": stars, "review": review})
            except Exception:
                n_msg = None
            if not n_msg:
                n_msg = f"⭐ *New Review!*\n\n👤 {nm} {stars}\n📦 {_pn}\n💬 {review}"
            success = await broadcast_store_message(bot, n_msg, pid=_pid, tpl_id="bc_review")
            _log_broadcast("review", n_msg, success)
            return chosen_type, success, 0
        except Exception as _e:
            logger.exception(f"[FakeBroadcast] review failed: {_e}")
            return None, 0, 0

    # 🆕 v161.19: REFERRAL MILESTONE HYPE
    if chosen_type == "milestone":
        try:
            nm = generate_fake_username(name_style)
            refs = random.choice([10, 25, 50, 100])
            reward = round(random.uniform(0.2, 1.5), 2)
            total = round(reward * random.uniform(3, 12), 2)
            try:
                from customization import render_template as _rt
                n_msg = _rt("bc_referral", {"user": nm, "referrals": str(refs), "reward": f"{reward:.2f}", "total_ref": f"{total:.2f}"})
            except Exception:
                n_msg = None
            if not n_msg:
                n_msg = f"🏆 *Referral Milestone!*\n\n👤 {nm}\n✅ Active Referrals: {refs}\n💰 Reward Earned: +${reward:.2f}"
            success = await broadcast_store_message(bot, n_msg, pid=None, tpl_id="bc_referral")
            _log_broadcast("milestone", n_msg, success)
            return chosen_type, success, 0
        except Exception as _e:
            logger.exception(f"[FakeBroadcast] milestone failed: {_e}")
            return None, 0, 0

    if not msg:
        return None, 0, 0

    # 🆕 v161.20 (user demand): ANY activity broadcast whose message mentions a
    # product name MUST carry the 🛒 Buy Now button — labelled
    # "{emoji} First Two Words Buy Now" (green by default). purchase/discount
    # used to go through send_to_all_users() with NO button; now they route
    # through broadcast_store_message() with pid + per-template button so the
    # styled Buy Now button is ALWAYS attached (auto-detected per product,
    # including newly added products).
    if chosen_type in ("purchase", "discount") and product_pid:
        try:
            success = await broadcast_store_message(
                bot, msg, pid=product_pid, tpl_id=f"bc_{chosen_type}")
        except Exception as _be:
            logger.exception(f"[FakeBroadcast] {chosen_type} button send failed: {_be}")
            success, _ = await send_to_all_users(bot, msg)
        _log_broadcast(chosen_type, msg, success)
        logger.info(f"[FakeBroadcast] Done {chosen_type} — ✅ {success} sent (Buy Now attached)")
        return chosen_type, success, 0

    # ── Send to all users ──
    logger.info(f"[FakeBroadcast] Sending '{chosen_type}' broadcast...")
    success, fail = await send_to_all_users(bot, msg)

    # ── Log it ──
    _log_broadcast(chosen_type, msg, success)
    logger.info(f"[FakeBroadcast] Done — ✅ {success} sent, ❌ {fail} failed")

    return chosen_type, success, fail


# ════════════════════════════════════════════════════════════════
# 🔔 REAL STOCK ALERT SENDER
# ════════════════════════════════════════════════════════════════
# Called automatically from handlers_admin.py when:
#   - Admin adds a new product with stock > 0
#   - Admin increases stock on an existing product that was 0
#
# This is NOT fake. It sends real info about real products.

async def send_real_stock_alert(bot, product_name, stock, price_usd):
    """
    Send a real "New Stock Available" alert to all users.

    Call this from handlers_admin.py after adding/restocking a product.
    Only fires if admin has stock alerts enabled.

    Args:
        bot: Telegram Bot instance
        product_name: the actual product name (string)
        stock: how many units are available (int)
        price_usd: price in USD (float)
    """
    # Check if stock alerts are enabled
    if not is_type_enabled("stock"):
        logger.info(f"[StockAlert] Stock alerts disabled — skipping for '{product_name}'")
        return 0, 0

    # Get PKR rate from settings
    try:
        from database import get_setting
        pkr_rate = int(get_setting("usd_to_pkr_rate", "280"))
    except Exception:
        pkr_rate = 280

    msg = make_new_stock_msg(product_name, stock, price_usd, pkr_rate)
    logger.info(f"[StockAlert] Sending real stock alert for '{product_name}'...")
    success, fail = await send_to_all_users(bot, msg)

    _log_broadcast("stock_alert", msg, success)
    logger.info(f"[StockAlert] Done — ✅ {success} sent, ❌ {fail} failed")

    return success, fail


# ════════════════════════════════════════════════════════════════
# ⏰ SCHEDULER JOB
# ════════════════════════════════════════════════════════════════
# This is called by bot.py's job queue.
# It schedules the NEXT broadcast randomly within admin's interval range.
#
# HOW TO ADD TO bot.py (add in post_init function):
# ──────────────────────────────────────────────────
#   from fake_broadcast import schedule_next_fake_broadcast
#   schedule_next_fake_broadcast(app)
#
# That's it! The system handles all scheduling automatically.

def schedule_next_fake_broadcast(app):
    """
    Schedule the first fake broadcast job.
    After each broadcast runs, it re-schedules itself automatically.
    Call this once in post_init() in bot.py.
    """
    min_m, max_m = get_interval_range()
    delay_seconds = random.randint(min_m * 60, max_m * 60)

    logger.info(f"[FakeBroadcast] Next broadcast in {delay_seconds // 60} min {delay_seconds % 60} sec")

    async def _job(context):
        """The actual job that runs and re-schedules itself."""
        try:
            await run_fake_broadcast(context.bot)
        except Exception as e:
            logger.error(f"[FakeBroadcast] Error in job: {e}")
        finally:
            # Re-schedule next one with a new random interval
            schedule_next_fake_broadcast(context.application)

    try:
        app.job_queue.run_once(_job, when=delay_seconds)
    except Exception as e:
        logger.error(f"[FakeBroadcast] Could not schedule job: {e}")


# ============================================================
# 📄 ORIGINAL FILE: fake_reviews.py
# ============================================================

# ============================================================
# ⭐ FAKE REVIEWS SYSTEM — fake_reviews.py
# ============================================================
#
# WHAT IS THIS?
# ─────────────
# This system automatically inserts fake 5-star (or 4-star) reviews
# into your product review section so every product looks well-reviewed.
#
# Reviews come with realistic names from:
#   - 🇵🇰 Pakistani names → Roman Urdu review text (natural, human-like)
#   - 🌍 International names → English review text (natural, human-like)
#
# Sometimes ONLY a star rating is posted (no text) — just like real users.
# Sometimes a full review with text is posted — also like real users.
#
# Real user reviews ALWAYS show up alongside fake ones — this system
# only ADDS fake ones, it never replaces or hides real reviews.
#
# ──────────────────────────────────────────────────────────
# HOW IT WORKS:
# ──────────────────────────────────────────────────────────
#
#   1. Admin turns ON fake reviews from Admin Panel
#   2. A background job runs every X–Y minutes (admin configurable)
#   3. It picks a random in-stock product
#   4. It picks a random fake name (Pakistani or International)
#   5. It picks a fake user_id (large number, won't clash with real users)
#   6. It inserts the review directly into the reviews DB table
#   7. The review shows up publicly in the product listing
#
# ──────────────────────────────────────────────────────────
# ADMIN CONTROL (from Admin Panel → ⭐ Fake Reviews):
# ──────────────────────────────────────────────────────────
#
#   ✅ Master ON/OFF switch
#   ✅ Set interval range (e.g. 10–90 min)
#   ✅ Set Pakistani vs International name mix ratio
#   ✅ Toggle: Allow 4-star ratings (or only 5-star)
#   ✅ Toggle: Allow text-only ratings (no review text)
#   ✅ Toggle: Allow full reviews (rating + text)
#   ✅ View fake review log (last 30)
#   ✅ Inject a fake review NOW (test button)
#   ✅ Clear ALL fake reviews from DB (reset button)
#
# ──────────────────────────────────────────────────────────
# IMPORTANT:
# ──────────────────────────────────────────────────────────
#   - Fake reviews use user_ids starting from 9_000_000_000
#     (real Telegram IDs never go this high — safe to use)
#   - product_reviews table has UNIQUE(product_id, user_id)
#     so each fake user can only review each product ONCE
#   - If all products are already reviewed by all fake users,
#     new fake user IDs are automatically generated
#
# ──────────────────────────────────────────────────────────

import random
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 🇵🇰 PAKISTANI NAMES
# ════════════════════════════════════════════════════════════════
# Common Pakistani first names — both male and female.
# These are the names shown in reviews from "Pakistani" users.

PAKISTANI_MALE_NAMES = [
    "Ahmed", "Ali", "Usman", "Hassan", "Bilal", "Zain", "Hamza",
    "Omer", "Faisal", "Asad", "Saad", "Waqar", "Farhan", "Imran",
    "Kamran", "Shahzaib", "Danyal", "Haris", "Muneeb", "Talha",
    "Waleed", "Junaid", "Arslan", "Shoaib", "Adnan", "Rizwan",
    "Taimur", "Usama", "Wahaj", "Sibtain", "Zubair", "Shehryar",
    "Babar", "Daniyal", "Huzaifa", "Jawad", "Kashif", "Luqman",
    "Moeez", "Noman", "Qasim", "Rehan", "Salman", "Tariq",
]

PAKISTANI_FEMALE_NAMES = [
    "Ayesha", "Fatima", "Zara", "Hina", "Sara", "Maham", "Noor",
    "Iqra", "Sana", "Rabia", "Amna", "Areeba", "Kiran", "Maryam",
    "Laiba", "Nimra", "Rida", "Saba", "Ume", "Zahra", "Zainab",
    "Alishba", "Bisma", "Dua", "Eman", "Fariha", "Gulnaz",
    "Hajra", "Iram", "Javeria", "Kinza", "Lubna", "Madiha",
    "Nabeela", "Palwasha", "Rania", "Sheeza", "Tayyaba",
]

# ────────────────────────────────────────────────────────────────
# 🇵🇰 ROMAN URDU REVIEWS — Natural, human-like, no dashes
# ────────────────────────────────────────────────────────────────
# These are what Pakistani users would actually write.
# Written in Roman Urdu (Urdu words using English letters).
# Range: short to medium length. Clean. No marketing fluff.
#
# FORMAT: Each is a list of sentences. We randomly pick 1-3 to combine.

# NOTE: These are DEFAULT sentences.
# Admin can edit them from: Admin Panel → 📝 Message Templates → 🇵🇰 Urdu Review
# Changes there override these defaults automatically.
ROMAN_URDU_SENTENCES = [
    # Positive experience
    "bohat acha product hai",
    "bilkul original mila",
    "delivery bht fast thi",
    "price ke hisaab se bohot acha hai",
    "works perfectly",
    "shukriya bite store",
    "highly recommend karta hoon",
    "awesome bro",
    "ekdum sahi cheez hai",
    "dobara zaroor lunga",
    "quality se khush hoon",
    "phir se order karunga",
    "highly recommended",
    "mast experience tha",
    "trust this store",
    "no issues at all",
    "seedha kaam kiya",
    "looks completely legit",
    "genuine product hai",
    "was hesitant but now a regular buyer",
    "yaar sach mein acha hai",
    "zabardast service",
    "fast delivery and original",
    "no risk at all",
    "bahut khush hoon",
    "superb product",
    "outstanding quality",
    "ekdum original",
    "good price and great quality",
    "recommend karta hoon dosto ko",
    "satisfied hoon",
    "sab kuch theek tha",
    "no complaints",
    "acha laga",
    "pehle doubt tha par sab theek nikla",
    "good seller hai",
    "trusted store hai",
    "jaldi deliver hua",
    "2 ghante mein mil gaya",
    "behtareen experience tha",
    "ek dum fresh account",
    "sab features chal rahe hain",
    "subscription work kar raha hai",
    "nice, worked straight away",
    "worth the price",
    "mujhe bohot zyada pasand aaya",
]

# ────────────────────────────────────────────────────────────────
# 🌍 INTERNATIONAL NAMES
# ────────────────────────────────────────────────────────────────
# Names from various countries — looks global and realistic.

INTERNATIONAL_NAMES = [
    # USA
    "James", "Michael", "John", "David", "Chris", "Daniel", "Matthew",
    "Ryan", "Tyler", "Justin", "Emma", "Olivia", "Sophia", "Isabella",
    "Mia", "Charlotte", "Amelia", "Harper", "Emily", "Abigail",
    # UK
    "Oliver", "Jack", "George", "Harry", "William", "Noah", "Alfie",
    "Freya", "Poppy", "Isla", "Ava", "Lily", "Grace", "Evie",
    # India
    "Rahul", "Arjun", "Rohan", "Vikram", "Aditya", "Kabir", "Aarav",
    "Priya", "Anjali", "Pooja", "Neha", "Riya", "Divya", "Kavya",
    # Arab
    "Omar", "Khalid", "Yousef", "Tariq", "Faisal", "Salim", "Nasser",
    "Layla", "Nadia", "Hana", "Reem", "Dina", "Salma", "Lina",
    # Turkey
    "Emre", "Burak", "Kemal", "Mert", "Berk", "Oguz", "Enes",
    "Elif", "Aylin", "Buse", "Merve", "Selin", "Ceren", "Ekin",
    # Nigeria / Africa
    "Emeka", "Chidi", "Seun", "Tunde", "Bayo", "Tobi", "Kola",
    "Amina", "Chisom", "Funmi", "Ngozi", "Adaeze", "Zainab",
    # Indonesia / Malaysia
    "Rizky", "Fajar", "Aldi", "Bima", "Hendra", "Daffa", "Reza",
    "Siti", "Dewi", "Rina", "Nurul", "Wulan", "Putri", "Ayu",
    # Russia / Eastern Europe
    "Alexei", "Dmitri", "Ivan", "Mikhail", "Pavel", "Sergei",
    "Natasha", "Anya", "Olga", "Katya", "Daria", "Irina",
    # Bangladesh
    "Rahim", "Karim", "Shakil", "Faruk", "Milon", "Sumon", "Roni",
    "Nasrin", "Shirin", "Rima", "Tania", "Lima", "Mitu",
    # Philippines
    "Juan", "Jose", "Carlo", "Paolo", "Marco", "Angelo", "Luis",
    "Maria", "Ana", "Rosa", "Liza", "Jenny", "Joy", "Christine",
]

# ────────────────────────────────────────────────────────────────
# 🌍 ENGLISH REVIEWS — Natural, human-like, no dashes
# ────────────────────────────────────────────────────────────────
# What international users would actually write.
# Mix of short and medium length sentences.

ENGLISH_SENTENCES = [
    # Very short
    "works perfectly",
    "great product",
    "highly recommend",
    "legit and fast",
    "totally worth it",
    "no issues at all",
    "exactly as described",
    "works like a charm",
    "super fast delivery",
    "very satisfied",
    "good quality",
    "genuine product",
    "amazing service",
    "will buy again",
    "loved it",
    "solid purchase",
    "great value for money",
    "100% legit",
    "fast and reliable",
    "no complaints",
    # Medium
    "got it within minutes and everything works fine",
    "was skeptical at first but turned out great",
    "the product is working perfectly so far",
    "really happy with this purchase",
    "better than I expected honestly",
    "smooth transaction and fast delivery",
    "exactly what was advertised",
    "trusted seller will definitely come back",
    "works on all my devices no issues",
    "quick delivery and genuine product",
    "gave it to my friend too she loves it",
    "been using it for a week all good",
    "completely satisfied with the purchase",
    "nice experience overall will recommend",
    "product quality is top notch",
    "good communication from seller too",
    "fast response and genuine item",
    "second time buying here always good",
    "cheapest price I found anywhere",
    "seamless experience from start to finish",
    "activated instantly no waiting",
    "premium quality at a fair price",
    "great store definitely trust them",
    "the subscription activated right away",
    "everything is working as expected",
    "would recommend to anyone looking for this",
    "bought for my team and everyone is happy",
    "much better than other sellers I tried",
    "came with full instructions very helpful",
    "support replied quickly when I had a question",
]


# ════════════════════════════════════════════════════════════════
# ⚙️ SETTINGS KEYS
# ════════════════════════════════════════════════════════════════
# All stored in bot_settings DB table.
# Admin changes these from Admin Panel → ⭐ Fake Reviews.

SETTING_ENABLED        = "frv_enabled"          # "1" or "0" — master ON/OFF
SETTING_MIN_INTERVAL   = "frv_min_interval"      # min minutes between fake reviews
SETTING_MAX_INTERVAL   = "frv_max_interval"      # max minutes between fake reviews
SETTING_PK_RATIO       = "frv_pk_ratio"          # 0–100 → % Pakistani names (default 60)
SETTING_ALLOW_4STAR    = "frv_allow_4star"        # "1" = allow some 4-star, "0" = only 5-star
SETTING_TEXT_ONLY      = "frv_text_only"          # "1" = always include text, "0" = sometimes skip
SETTING_RATINGS_ONLY   = "frv_ratings_only"       # "1" = sometimes post rating-only (no text)
SETTING_LOG_ENABLED    = "frv_log_enabled"        # "1" = log to memory


def _get(key, default=""):
    try:
        from database import get_setting
        return get_setting(key, default)
    except Exception:
        return default


def _set(key, value):
    try:
        from database import set_setting
        set_setting(key, str(value))
    except Exception:
        pass


def is_enabled():
    """Returns True if fake reviews system is turned ON."""
    return _get(SETTING_ENABLED, "0") == "1"


def get_interval_range():
    """Returns (min_minutes, max_minutes). Default: 15 to 90."""
    try:
        min_m = int(_get(SETTING_MIN_INTERVAL, "15"))
        max_m = int(_get(SETTING_MAX_INTERVAL, "90"))
        if min_m < 1: min_m = 1
        if max_m < min_m: max_m = min_m + 15
        return min_m, max_m
    except Exception:
        return 15, 90


def get_pk_ratio():
    """
    Returns 0-100 integer = % chance of Pakistani name.
    Default 60 = 60% Pakistani, 40% International.
    """
    try:
        return max(0, min(100, int(_get(SETTING_PK_RATIO, "60"))))
    except Exception:
        return 60


def allow_4star():
    """If True, ~20% of reviews will be 4-star (more realistic). Default ON."""
    return _get(SETTING_ALLOW_4STAR, "1") == "1"


def ratings_only_enabled():
    """If True, ~30% of fake reviews have NO text (only stars). Default ON."""
    return _get(SETTING_RATINGS_ONLY, "1") == "1"


# ════════════════════════════════════════════════════════════════
# 🎭 NAME & REVIEW GENERATOR
# ════════════════════════════════════════════════════════════════

def generate_fake_reviewer(pk_ratio=60):
    """
    Returns (display_name, language) where language is 'urdu' or 'english'.

    pk_ratio: 0–100. 60 means 60% chance of Pakistani name.
    """
    is_pakistani = random.randint(1, 100) <= pk_ratio

    if is_pakistani:
        # Pick male or female randomly
        if random.random() < 0.55:
            name = random.choice(PAKISTANI_MALE_NAMES)
        else:
            name = random.choice(PAKISTANI_FEMALE_NAMES)
        return name, "urdu"
    else:
        name = random.choice(INTERNATIONAL_NAMES)
        return name, "english"


def generate_review_text(language, include_text=True):
    """
    Generate a review text using admin-editable sentence pool.

    Args:
        language: 'urdu' or 'english'
        include_text: if False, returns empty string (rating-only review)

    Returns:
        review text string (may be empty if include_text=False)
    """
    if not include_text:
        return ""  # Rating only — no text

    # Try to get sentences from admin-editable template pool first
    try:
        from customization import get_review_sentences
        sentences = get_review_sentences(language)
    except Exception:
        # Fallback to hardcoded defaults
        sentences = ROMAN_URDU_SENTENCES if language == "urdu" else ENGLISH_SENTENCES

    if language == "urdu":
        num = random.choices([1, 2, 3], weights=[40, 40, 20])[0]
    else:
        num = random.choices([1, 2], weights=[60, 40])[0]

    picked = random.sample(sentences, min(num, len(sentences)))
    return " ".join(picked)


def generate_star_rating():
    """
    Generate a star rating (4 or 5 stars).

    If allow_4star is enabled:
        80% chance → 5 stars
        20% chance → 4 stars

    If allow_4star is disabled:
        100% → 5 stars
    """
    if allow_4star():
        return random.choices([5, 4], weights=[80, 20])[0]
    return 5


def generate_fake_user_id():
    """
    Generate a fake Telegram user ID that will NEVER clash with real users.
    Real Telegram IDs are much smaller numbers.
    We use the range 9_000_000_000 to 9_999_999_999.
    """
    return random.randint(9_000_000_000, 9_999_999_999)


# ════════════════════════════════════════════════════════════════
# 📋 FAKE REVIEW LOG
# ════════════════════════════════════════════════════════════════

_review_log = []   # List of dicts: {time, name, product, rating, text_preview}
MAX_LOG = 50


def _log_review(name, language, product, rating, text):
    """Add to in-memory log."""
    _review_log.append({
        "time":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "name":    name,
        "lang":    "🇵🇰" if language == "urdu" else "🌍",
        "product": product[:40],
        "rating":  rating,
        "preview": text[:50] if text else "(rating only)",
    })
    if len(_review_log) > MAX_LOG:
        _review_log.pop(0)


def get_review_log():
    """Returns list of recent fake reviews (newest first)."""
    return list(reversed(_review_log))


# ════════════════════════════════════════════════════════════════
# 🎯 CORE — Insert One Fake Review
# ════════════════════════════════════════════════════════════════

def insert_fake_review(product_id=None, product_name=None, force_language=None, force_no_text=False):
    """
    Insert one fake review into the database.

    Args:
        product_id:    specific product to review (or None = random)
        product_name:  name for logging (optional, auto-fetched if None)
        force_language: 'urdu' or 'english' (or None = auto by pk_ratio)
        force_no_text: if True, ALWAYS post rating only — no review text

    Returns:
        dict with review details, or None if failed
    """
    # ── Pick product (v60: hidden + OOS excluded) ──
    try:
        from database import get_all_products, is_product_hidden, is_product_fake_off
        all_products = get_all_products()  # already excludes hidden after v60
        # Only use in-stock + not-hidden products (belt + suspenders)
        in_stock = []
        for p in all_products:
            d = dict(p) if not isinstance(p, dict) else p
            pid_ = d.get("id")
            stock_v = (p["stock"] if isinstance(p, dict) else p[6])
            if int(stock_v or 0) <= 0:
                continue
            try:
                if pid_ and is_product_hidden(pid_):
                    continue
            except Exception:
                pass
            # 🆕 v169: Exclude test/API products from fake reviews too
            pname = (d.get("name") or "").lower()
            if "api test" in pname or "apitest" in pname:
                continue
            # 🆕 v170.5: admin ka per-product "fake activity OFF" flag
            try:
                if pid_ and is_product_fake_off(pid_):
                    continue
            except Exception:
                pass
            in_stock.append(p)

        if not in_stock:
            logger.info("[FakeReviews] No buyable products — skipping.")
            return None

        if product_id is None:
            chosen = random.choice(in_stock)
            if isinstance(chosen, dict):
                product_id = chosen["id"]
                product_name = chosen.get("name", f"Product #{product_id}")
            else:
                product_id = chosen[0]
                product_name = chosen[2]
        elif product_name is None:
            # Fetch product name
            try:
                from database import get_product
                p = get_product(product_id)
                product_name = p["name"] if p else f"Product #{product_id}"
            except Exception:
                product_name = f"Product #{product_id}"

    except Exception as e:
        logger.error(f"[FakeReviews] DB error fetching products: {e}")
        return None

    # ── Generate reviewer ──
    pk_ratio = get_pk_ratio()
    if force_language:
        name = (random.choice(PAKISTANI_MALE_NAMES + PAKISTANI_FEMALE_NAMES)
                if force_language == "urdu"
                else random.choice(INTERNATIONAL_NAMES))
        language = force_language
    else:
        name, language = generate_fake_reviewer(pk_ratio)

    # ── Generate rating ──
    rating = generate_star_rating()

    # ── Generate text ──
    # force_no_text=True  → always rating only, no text (used by test button)
    # ratings_only_enabled → 30% chance of no text (random behavior)
    # otherwise           → always include text
    if force_no_text:
        include_text = False
    elif ratings_only_enabled():
        include_text = random.random() > 0.30  # 30% chance rating-only
    else:
        include_text = True

    text = generate_review_text(language, include_text=include_text)

    # ── Generate fake user_id ──
    # Try up to 10 times to find a unique combination
    for attempt in range(10):
        fake_uid = generate_fake_user_id()
        try:
            from database import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Insert review with fake user info
            # We use the product_reviews table directly
            cursor.execute("""
                INSERT OR IGNORE INTO product_reviews
                    (product_id, user_id, order_id, rating, review_text)
                VALUES (?, ?, ?, ?, ?)
            """, (product_id, fake_uid, 0, rating, text))

            inserted = cursor.rowcount > 0

            if inserted:
                # Insert fake reviewer into users table so their name shows in reviews.
                # These users have IDs >= 9_000_000_000 so:
                #   - fake_broadcast.send_to_all_users() skips them (ID check)
                #   - They never receive any Telegram messages
                #   - They only exist so product_reviews JOIN shows the name
                cursor.execute("""
                    INSERT OR IGNORE INTO users
                        (user_id, first_name, username, joined_at,
                         wallet_balance, points, referred_by, referral_count)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, 0, 0, 0, 0)
                """, (fake_uid, name, f"fake_reviewer_{fake_uid}"))

            conn.commit()
            conn.close()

            if inserted:
                _log_review(name, language, product_name, rating, text)
                logger.info(
                    f"[FakeReviews] ✅ {name} ({language}) → '{product_name}' "
                    f"{'⭐' * rating} | "
                    f"text: {text[:40] if text else '(none)'!r}"
                )
                return {
                    "name":     name,
                    "language": language,
                    "product":  product_name,
                    "rating":   rating,
                    "text":     text,
                    "user_id":  fake_uid,
                }
            # If INSERT was ignored (duplicate), try again with new uid

        except Exception as e:
            logger.error(f"[FakeReviews] DB insert error (attempt {attempt+1}): {e}")
            try: conn.close()
            except: pass

    logger.warning(f"[FakeReviews] Could not insert review after 10 attempts.")
    return None


# ════════════════════════════════════════════════════════════════
# 🗑️ CLEAR ALL FAKE REVIEWS
# ════════════════════════════════════════════════════════════════

def clear_all_fake_reviews():
    """
    Deletes ALL fake reviews from the database.
    Fake reviews are identified by user_id >= 9_000_000_000.
    Also removes fake reviewer entries from users table.
    Real user reviews and real user accounts are NOT touched.

    Returns: number of reviews deleted
    """
    try:
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM product_reviews WHERE user_id >= 9000000000"
        )
        deleted = cursor.rowcount
        # Clean up fake reviewer records from users table
        # Only removes fake_reviewer_ entries (username starts with fake_reviewer_)
        cursor.execute(
            "DELETE FROM users WHERE user_id >= 9000000000 AND username LIKE 'fake_reviewer_%'"
        )
        conn.commit()
        conn.close()
        _review_log.clear()
        logger.info(f"[FakeReviews] Cleared {deleted} fake reviews from DB.")
        return deleted
    except Exception as e:
        logger.error(f"[FakeReviews] Error clearing reviews: {e}")
        return 0


def get_fake_review_count():
    """Returns how many fake reviews are currently in DB."""
    try:
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM product_reviews WHERE user_id >= 9000000000"
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


# ════════════════════════════════════════════════════════════════
# ⏰ SCHEDULER
# ════════════════════════════════════════════════════════════════
# Call schedule_fake_reviews(app) once in post_init() in bot.py.
# It automatically re-schedules itself after each run.
#
# HOW TO ADD TO bot.py:
# ──────────────────────
#   from fake_reviews import schedule_fake_reviews
#
#   async def post_init(app):
#       ...
#       schedule_fake_reviews(app)

import asyncio


async def _fake_review_job(context):
    """
    The background job that runs periodically.
    Inserts one fake review, then re-schedules itself.
    """
    try:
        if not is_enabled():
            # Re-check after 5 min even when disabled (in case admin turns on)
            context.application.job_queue.run_once(_fake_review_job, when=300)
            return

        result = insert_fake_review()
        if result:
            logger.info(
                f"[FakeReviews] Job done — {result['name']} reviewed '{result['product']}'"
            )
    except Exception as e:
        logger.error(f"[FakeReviews] Job error: {e}")
    finally:
        # Re-schedule next run
        schedule_fake_reviews(context.application)


def schedule_fake_reviews(app):
    """
    Schedule next fake review insertion.
    Call this once from post_init() — it will keep re-scheduling itself.
    """
    min_m, max_m = get_interval_range()
    delay = random.randint(min_m * 60, max_m * 60)
    logger.info(f"[FakeReviews] Next review in {delay // 60}m {delay % 60}s")
    try:
        app.job_queue.run_once(_fake_review_job, when=delay)
    except Exception as e:
        logger.error(f"[FakeReviews] Could not schedule: {e}")


# ============================================================
# 📄 ORIGINAL FILE: handlers_fake_broadcast.py
# ============================================================

# ============================================================
# 🎛️ FAKE BROADCAST ADMIN PANEL — handlers_fake_broadcast.py
# ============================================================
#
# This file handles ALL admin panel interactions for the
# Fake Broadcast system. Admins access it via:
#   Admin Panel → 📢 Fake Broadcast
#
# FEATURES IN THIS PANEL:
# ────────────────────────
#   ✅ Master ON/OFF switch
#   ✅ Set min/max interval (how often broadcasts fire)
#   ✅ Toggle each message type (purchases, deposits, referrals, etc.)
#   ✅ Set fake name style (stars / initials / random)
#   ✅ View broadcast log (last 20 sent)
#   ✅ Send a test broadcast manually RIGHT NOW
#   ✅ Real stock alert toggle (on/off)
#
# HOW TO REGISTER IN bot.py:
# ────────────────────────────
#   from handlers_fake_broadcast import (
#       fake_broadcast_panel_callback,
#       fbc_toggle_main_callback,
#       fbc_toggle_type_callback,
#       fbc_set_interval_callback,
#       fbc_interval_value_received,
#       fbc_name_style_callback,
#       fbc_test_callback,
#       fbc_log_callback,
#       FBC_INTERVAL,
#   )
#
#   # Add to ConversationHandler in main():
#   app.add_handler(ConversationHandler(
#       entry_points=[CallbackQueryHandler(fbc_set_interval_callback, pattern="^fbc_set_interval$")],
#       states={FBC_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, fbc_interval_value_received)]},
#       fallbacks=[CommandHandler("cancel", cancel_conversation)],
#   ))
#
#   # Add individual callback handlers:
#   app.add_handler(CallbackQueryHandler(fake_broadcast_panel_callback, pattern="^fbc_panel$"))
#   app.add_handler(CallbackQueryHandler(fbc_toggle_main_callback,   pattern="^fbc_toggle_main$"))
#   app.add_handler(CallbackQueryHandler(fbc_toggle_type_callback,   pattern="^fbc_type_"))
#   app.add_handler(CallbackQueryHandler(fbc_name_style_callback,    pattern="^fbc_style_"))
#   app.add_handler(CallbackQueryHandler(fbc_test_callback,          pattern="^fbc_test"))
#   app.add_handler(CallbackQueryHandler(fbc_log_callback,           pattern="^fbc_log$"))
#
# ──────────────────────────────────────────────────────────────

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

# [v77-merge] from fake_broadcast import (

# [v77-merge] is_enabled, is_type_enabled, get_interval_range, get_name_style,

# [v77-merge] get_broadcast_log, run_fake_broadcast, schedule_next_fake_broadcast,

# [v77-merge] SETTING_ENABLED, SETTING_MIN_INTERVAL, SETTING_MAX_INTERVAL,

# [v77-merge] SETTING_TYPE_PURCHASE, SETTING_TYPE_DEPOSIT, SETTING_TYPE_REFERRAL,

# [v77-merge] SETTING_TYPE_TIER, SETTING_TYPE_STOCK, SETTING_TYPE_DISCOUNT,

# [v77-merge] SETTING_NAME_STYLE,

# [v77-merge] )
logger = logging.getLogger(__name__)

# ConversationHandler state for interval input
FBC_INTERVAL  = 900
FBC_USER_COUNT = 903   # For fake user count input


# ════════════════════════════════════════════════════════════════
# 🔧 HELPERS
# ════════════════════════════════════════════════════════════════

def _toggle_icon(val):
    """Returns ✅ or ❌ based on boolean-like value."""
    if isinstance(val, str):
        return "✅" if val == "1" else "❌"
    return "✅" if val else "❌"


def _set(key, value):
    """Save a setting to the database."""
    try:
        from database import set_setting
        set_setting(key, str(value))
    except Exception as e:
        logger.error(f"[FBC Panel] DB write error: {e}")


def _get(key, default=""):
    """Read a setting from the database."""
    try:
        from database import get_setting
        return get_setting(key, default)
    except Exception:
        return default


def _is_admin(user_id):
    """Check if this user is the bot admin."""
    from config import ADMIN_ID
    return user_id == ADMIN_ID


async def _safe_edit(q, text, keyboard):
    """Edit message safely — try text edit, fallback to caption edit."""
    try:
        await q.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        try:
            await q.edit_message_caption(
                caption=text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════
# 🏠 MAIN PANEL
# ════════════════════════════════════════════════════════════════

async def fake_broadcast_panel_callback(update, context):
    """
    Main Fake Broadcast control panel.
    Accessed via: Admin Panel → 📢 Fake Broadcast

    Shows current status and all control options.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    # ── Read current settings ──
    enabled = is_enabled()
    min_m, max_m = get_interval_range()
    name_style = get_name_style()

    # ── Type toggles ──
    t_purchase = is_type_enabled("purchase")
    t_deposit  = is_type_enabled("deposit")
    t_referral = is_type_enabled("referral")
    t_tier     = is_type_enabled("tier")
    t_discount = is_type_enabled("discount")
    t_stock    = is_type_enabled("stock")
    t_freeclaim = is_type_enabled("freeclaim")  # 🆕 v110
    t_freebie   = is_type_enabled("freebie")    # 🆕 v170.14
    t_bulkdeal  = is_type_enabled("bulkdeal")   # 🆕 v161.12
    t_reseller  = is_type_enabled("reseller")   # 🆕 v161.12
    t_newuser   = is_type_enabled("newuser")    # 🆕 v161.19
    t_newprod   = is_type_enabled("newprod")    # 🆕 v161.19
    t_flash     = is_type_enabled("flash")      # 🆕 v161.19
    t_pricedrop = is_type_enabled("pricedrop")  # 🆕 v161.19
    t_review    = is_type_enabled("review")     # 🆕 v161.19
    t_milestone = is_type_enabled("milestone")  # 🆕 v161.19

    # ── Get user counts ──
    try:
        from database import get_user_count, get_displayed_user_count
        real_users   = get_user_count()
        shown_users  = get_displayed_user_count()
        fake_offset  = shown_users - real_users
    except Exception:
        real_users = shown_users = fake_offset = 0

    # ── Build status text ──
    status_icon = "🟢 *ACTIVE*" if enabled else "🔴 *INACTIVE*"
    text = (
        f"📢 *Fake Broadcast Control Panel*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔌 Status: {status_icon}\n"
        f"⏱️ Interval: Every {min_m}–{max_m} minutes (random)\n"
        f"👤 Name Style: `{name_style}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 *User Counter:*\n"
        f"  📊 Real Users: *{real_users}*\n"
        f"  🎭 Fake Offset: *+{fake_offset}*\n"
        f"  📣 Shown to others: *{shown_users}* users\n"
        f"  _(Real joins auto-increase shown count)_\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*Message Types:*\n"
        f"  {_toggle_icon(t_purchase)} Fake Purchases\n"
        f"  {_toggle_icon(t_deposit)} Fake Deposits\n"
        f"  {_toggle_icon(t_referral)} Fake Referrals\n"
        f"  {_toggle_icon(t_tier)} Tier Upgrades\n"
        f"  {_toggle_icon(t_discount)} Discount Alerts\n"
        f"  {_toggle_icon(t_stock)} Real Stock Alerts *(auto)*\n"
        f"  {_toggle_icon(t_freeclaim)} Fake Free-Claims *(uses per-product fc button)*\n"
        f"  {_toggle_icon(t_freebie)} Freebie Claims *(free products)*\n"
        f"  {_toggle_icon(t_bulkdeal)} Bulk-Deal Hype *(products with tiers)*\n"
        f"  {_toggle_icon(t_reseller)} Reseller Purchase Hype\n"
        f"  {_toggle_icon(t_newuser)} New Member Joined\n"
        f"  {_toggle_icon(t_newprod)} New Product\n"
        f"  {_toggle_icon(t_flash)} Flash Sale\n"
        f"  {_toggle_icon(t_pricedrop)} Price Drop\n"
        f"  {_toggle_icon(t_review)} New Review\n"
        f"  {_toggle_icon(t_milestone)} Referral Milestone\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *How it works:*\n"
        f"• Fake msgs fire every {min_m}–{max_m} min randomly\n"
        f"• Goes to ALL real users of your bot\n"
        f"• Uses REAL product names (only in-stock)\n"
        f"• New joins show as: Bite Store 🛍️ users: {shown_users}+"
    )

    # ── Build keyboard ──
    master_label = "🔴 Turn OFF Fake Broadcast" if enabled else "🟢 Turn ON Fake Broadcast"
    keyboard = [
        [InlineKeyboardButton(master_label, callback_data="fbc_toggle_main")],
        [InlineKeyboardButton("━━━━━ Message Types ━━━━━", callback_data="fbc_noop")],
        [
            InlineKeyboardButton(f"{_toggle_icon(t_purchase)} Purchases", callback_data="fbc_type_purchase"),
            InlineKeyboardButton(f"{_toggle_icon(t_deposit)} Deposits",   callback_data="fbc_type_deposit"),
        ],
        [
            InlineKeyboardButton(f"{_toggle_icon(t_referral)} Referrals", callback_data="fbc_type_referral"),
            InlineKeyboardButton(f"{_toggle_icon(t_tier)} Tiers",         callback_data="fbc_type_tier"),
        ],
        [
            InlineKeyboardButton(f"{_toggle_icon(t_discount)} Discounts", callback_data="fbc_type_discount"),
            InlineKeyboardButton(f"{_toggle_icon(t_stock)} Stock Alerts", callback_data="fbc_type_stock"),
        ],
        # 🆕 v110: Fake Free-Claims toggle
        [
            InlineKeyboardButton(f"{_toggle_icon(t_freeclaim)} Fake Free-Claims", callback_data="fbc_type_freeclaim"),
            InlineKeyboardButton(f"{_toggle_icon(t_freebie)} Freebie Claims", callback_data="fbc_type_freebie"),
        ],
        # 🆕 v161.12: Bulk-Deal + Reseller hype toggles
        [
            InlineKeyboardButton(f"{_toggle_icon(t_bulkdeal)} Bulk-Deal Hype", callback_data="fbc_type_bulkdeal"),
            InlineKeyboardButton(f"{_toggle_icon(t_reseller)} Reseller Hype", callback_data="fbc_type_reseller"),
        ],
        # 🆕 v161.19: extra hype toggles
        [
            InlineKeyboardButton(f"{_toggle_icon(t_newuser)} New Member", callback_data="fbc_type_newuser"),
            InlineKeyboardButton(f"{_toggle_icon(t_newprod)} New Product", callback_data="fbc_type_newprod"),
        ],
        [
            InlineKeyboardButton(f"{_toggle_icon(t_flash)} Flash Sale", callback_data="fbc_type_flash"),
            InlineKeyboardButton(f"{_toggle_icon(t_pricedrop)} Price Drop", callback_data="fbc_type_pricedrop"),
        ],
        [
            InlineKeyboardButton(f"{_toggle_icon(t_review)} New Review", callback_data="fbc_type_review"),
            InlineKeyboardButton(f"{_toggle_icon(t_milestone)} Milestone", callback_data="fbc_type_milestone"),
        ],
        [InlineKeyboardButton("━━━━━ Settings ━━━━━", callback_data="fbc_noop")],
        [
            InlineKeyboardButton(f"⏱️ Set Interval ({min_m}–{max_m} min)", callback_data="fbc_set_interval"),
        ],
        [
            InlineKeyboardButton("👤 Name Style: Stars (b***l)",    callback_data="fbc_style_stars"),
            InlineKeyboardButton("👤 Initials (B.L.)",              callback_data="fbc_style_initials"),
        ],
        [
            InlineKeyboardButton("👤 Random (User#1234)",           callback_data="fbc_style_random"),
        ],
        [InlineKeyboardButton("━━━━━ Actions ━━━━━", callback_data="fbc_noop")],
        [
            InlineKeyboardButton("🧪 Test: Send NOW (Purchase)",    callback_data="fbc_test_purchase"),
            InlineKeyboardButton("🧪 Test: Send NOW (Deposit)",     callback_data="fbc_test_deposit"),
        ],
        [
            InlineKeyboardButton("🧪 Test: Send NOW (Referral)",    callback_data="fbc_test_referral"),
            InlineKeyboardButton("🧪 Test: Random Type",            callback_data="fbc_test_random"),
        ],
        [InlineKeyboardButton("📋 View Broadcast Log (Last 20)",    callback_data="fbc_log")],
        [InlineKeyboardButton("━━━━━ User Counter ━━━━━", callback_data="fbc_noop")],
        [
            InlineKeyboardButton(f"👥 Set Fake User Count ({shown_users} shown)", callback_data="fbc_set_usercount"),
            InlineKeyboardButton("🎲 Random (100–2500)", callback_data="fbc_usercount_random"),
        ],
        [InlineKeyboardButton("📝 Edit Templates",              callback_data="tpl_panel")],
        [InlineKeyboardButton("🔙 Back to Admin Panel",         callback_data="admin_panel")],
    ]

    await _safe_edit(q, text, keyboard)


# ════════════════════════════════════════════════════════════════
# 🔌 MASTER ON/OFF TOGGLE
# ════════════════════════════════════════════════════════════════

async def fbc_toggle_main_callback(update, context):
    """
    Toggle the entire fake broadcast system ON or OFF.
    When turned ON, schedules the first broadcast job.
    When turned OFF, existing jobs will still complete but no new ones scheduled.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    current = _get(SETTING_ENABLED, "0")
    new_val = "0" if current == "1" else "1"
    _set(SETTING_ENABLED, new_val)

    if new_val == "1":
        # Schedule first broadcast when turned ON
        try:
            schedule_next_fake_broadcast(context.application)
            await q.answer("✅ Fake Broadcast ENABLED! First message coming soon.", show_alert=True)
        except Exception as e:
            logger.error(f"[FBC Panel] Schedule error: {e}")
            await q.answer("✅ Enabled. Restart bot for scheduling to work.", show_alert=True)
    else:
        await q.answer("🔴 Fake Broadcast DISABLED.", show_alert=True)

    # Refresh panel
    await fake_broadcast_panel_callback(update, context)


# ════════════════════════════════════════════════════════════════
# 🎛️ TYPE TOGGLES (Purchase / Deposit / Referral / Tier / Discount / Stock)
# ════════════════════════════════════════════════════════════════

# Maps callback_data suffix to DB setting key
_TYPE_MAP = {
    "purchase": SETTING_TYPE_PURCHASE,
    "deposit":  SETTING_TYPE_DEPOSIT,
    "referral": SETTING_TYPE_REFERRAL,
    "tier":     SETTING_TYPE_TIER,
    "discount": SETTING_TYPE_DISCOUNT,
    "stock":    SETTING_TYPE_STOCK,
    "freeclaim": SETTING_TYPE_FREECLAIM,  # 🆕 v110
        "freebie":  SETTING_TYPE_FREEBIE,    # 🆕 v170.14
    "bulkdeal":  SETTING_TYPE_BULKDEAL,   # 🆕 v161.12
    "reseller":  SETTING_TYPE_RESELLER,   # 🆕 v161.12
    "newuser":   SETTING_TYPE_NEWUSER,    # 🆕 v161.19
    "newprod":   SETTING_TYPE_NEWPROD,    # 🆕 v161.19
    "flash":     SETTING_TYPE_FLASH,      # 🆕 v161.19
    "pricedrop": SETTING_TYPE_PRICEDROP,  # 🆕 v161.19
    "review":    SETTING_TYPE_REVIEW,     # 🆕 v161.19
    "milestone": SETTING_TYPE_MILESTONE,  # 🆕 v161.19
}

_TYPE_LABELS = {
    "purchase": "Fake Purchases",
    "deposit":  "Fake Deposits",
    "referral": "Fake Referrals",
    "tier":     "Tier Upgrades",
    "discount": "Discount Alerts",
    "stock":    "Real Stock Alerts",
    "freeclaim": "Fake Free-Claims",  # 🆕 v110
    "freebie":   "Freebie Claims",     # 🆕 v170.14
    "bulkdeal":  "Bulk-Deal Hype",    # 🆕 v161.12
    "reseller":  "Reseller Hype",     # 🆕 v161.12
    "newuser":   "New Member Joined", # 🆕 v161.19
    "newprod":   "New Product",       # 🆕 v161.19
    "flash":     "Flash Sale",        # 🆕 v161.19
    "pricedrop": "Price Drop",        # 🆕 v161.19
    "review":    "New Review",        # 🆕 v161.19
    "milestone": "Referral Milestone",# 🆕 v161.19
}


async def fbc_toggle_type_callback(update, context):
    """
    Toggle a specific message type ON or OFF.
    Callback pattern: fbc_type_{type_key}
    Example: fbc_type_purchase, fbc_type_deposit
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return

    # Extract type key from callback data: "fbc_type_purchase" → "purchase"
    type_key = q.data.replace("fbc_type_", "")
    setting_key = _TYPE_MAP.get(type_key)

    if not setting_key:
        await q.answer("❌ Unknown type.", show_alert=True)
        return

    current = _get(setting_key, "1")
    new_val = "0" if current == "1" else "1"
    _set(setting_key, new_val)

    label = _TYPE_LABELS.get(type_key, type_key)
    status = "✅ Enabled" if new_val == "1" else "❌ Disabled"
    await q.answer(f"{label}: {status}", show_alert=False)

    # Refresh panel
    await fake_broadcast_panel_callback(update, context)


# ════════════════════════════════════════════════════════════════
# 👤 NAME STYLE TOGGLE
# ════════════════════════════════════════════════════════════════

_STYLE_LABELS = {
    "stars":    "⭐ Stars  (b***l)",
    "initials": "🔤 Initials  (B.L.)",
    "random":   "🎲 Random  (User#1234)",
}


async def fbc_name_style_callback(update, context):
    """
    Set the fake username display style.
    Callback pattern: fbc_style_{style_key}
    Options: fbc_style_stars, fbc_style_initials, fbc_style_random
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return

    # Extract style key: "fbc_style_stars" → "stars"
    style = q.data.replace("fbc_style_", "")
    if style not in ("stars", "initials", "random"):
        await q.answer("❌ Invalid style.", show_alert=True)
        return

    _set(SETTING_NAME_STYLE, style)
    label = _STYLE_LABELS.get(style, style)
    await q.answer(f"✅ Name style set to: {label}", show_alert=False)

    # Refresh panel
    await fake_broadcast_panel_callback(update, context)


# ════════════════════════════════════════════════════════════════
# ⏱️ INTERVAL SETTER (ConversationHandler)
# ════════════════════════════════════════════════════════════════

async def fbc_set_interval_callback(update, context):
    """
    Entry point: ask admin to enter new interval range.
    Format: MIN MAX  (e.g. "10 45" means 10–45 minutes)
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()

    min_m, max_m = get_interval_range()
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="fbc_panel")]]

    text = (
        f"⏱️ *Set Broadcast Interval*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: *{min_m}–{max_m} minutes*\n\n"
        f"Type new range as: `MIN MAX`\n\n"
        f"Examples:\n"
        f"  `5 30`   → every 5 to 30 min\n"
        f"  `10 60`  → every 10 to 60 min\n"
        f"  `1 5`    → very fast (testing only)\n"
        f"  `30 120` → slow, less frequent\n\n"
        f"⚠️ Min must be ≥ 1. Max must be > Min."
    )

    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        pass

    return FBC_INTERVAL


async def fbc_interval_value_received(update, context):
    """
    Receive and save the new interval values from admin.
    Expected format: "MIN MAX" (two numbers separated by space)
    """
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()
    parts = text.split()

    error_msg = None

    if len(parts) != 2:
        error_msg = (
            "❌ *Wrong format!*\n\n"
            "Send two numbers separated by space.\n"
            "Example: `10 60`"
        )
    else:
        try:
            min_m = int(parts[0])
            max_m = int(parts[1])
            if min_m < 1:
                error_msg = "❌ Minimum must be at least 1 minute."
            elif max_m <= min_m:
                error_msg = f"❌ Maximum ({max_m}) must be greater than minimum ({min_m})."
        except ValueError:
            error_msg = "❌ Both values must be whole numbers. Example: `10 60`"

    if error_msg:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="fbc_panel")]]
        await update.message.reply_text(
            error_msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    # Save new interval
    _set(SETTING_MIN_INTERVAL, str(min_m))
    _set(SETTING_MAX_INTERVAL, str(max_m))

    keyboard = [[InlineKeyboardButton("🔙 Back to Fake Broadcast Panel", callback_data="fbc_panel")]]
    await update.message.reply_text(
        f"✅ *Interval Updated!*\n\n"
        f"New range: *{min_m}–{max_m} minutes*\n\n"
        f"Next broadcast will use this new interval.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════
# 🧪 TEST SENDER (Admin can manually trigger a fake broadcast)
# ════════════════════════════════════════════════════════════════

async def fbc_test_callback(update, context):
    """
    Admin manually triggers a fake broadcast for testing.
    Callback patterns:
      fbc_test_purchase  → sends a fake purchase right now
      fbc_test_deposit   → sends a fake deposit right now
      fbc_test_referral  → sends a fake referral right now
      fbc_test_random    → sends a random type right now

    This ignores the ON/OFF switch — useful for testing even when system is disabled.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer("⏳ Sending test broadcast...", show_alert=False)

    # Extract type from callback data
    suffix = q.data.replace("fbc_test_", "")
    force_type = None if suffix == "random" else suffix

    try:
        btype, success, fail = await run_fake_broadcast(context.bot, force_type=force_type)

        if btype:
            if success == 0 and fail == 0:
                result_text = (
                    f"✅ *Message Generated — No Users Yet*\n\n"
                    f"Type: `{btype}`\n\n"
                    f"⚠️ No users in your bot yet.\n"
                    f"Once users start /start, they will receive broadcasts.\n\n"
                    f"_Message was created successfully — system works!_ ✅"
                )
            else:
                result_text = (
                    f"✅ *Test Broadcast Sent!*\n\n"
                    f"Type: `{btype}`\n"
                    f"✅ Delivered: {success} users\n"
                    f"❌ Failed: {fail} users"
                )
        else:
            result_text = (
                "⚠️ *Test broadcast skipped.*\n\n"
                "Possible reasons:\n"
                "• No in-stock products in your shop\n"
                "• All message types are disabled"
            )
    except Exception as e:
        result_text = f"❌ *Error sending test broadcast:*\n`{str(e)}`"

    keyboard = [[InlineKeyboardButton("🔙 Back to Fake Broadcast Panel", callback_data="fbc_panel")]]

    try:
        await q.edit_message_text(
            result_text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        try:
            await q.message.reply_text(
                result_text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════
# 📋 BROADCAST LOG VIEWER
# ════════════════════════════════════════════════════════════════

async def fbc_log_callback(update, context):
    """
    Show the last 20 broadcasts that were sent.
    Displays: time, type, preview of message, and how many users received it.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    log = get_broadcast_log()

    if not log:
        text = (
            "📋 *Broadcast Log*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "No broadcasts have been sent yet.\n\n"
            "Turn on Fake Broadcast or send a test to see logs here."
        )
    else:
        lines = ["📋 *Broadcast Log (Last 20)*\n━━━━━━━━━━━━━━━━━━━━\n"]
        for i, entry in enumerate(log[:20], 1):
            type_icon = {
                "purchase":    "🛒",
                "deposit":     "💳",
                "referral":    "🎁",
                "tier":        "🎖️",
                "discount":    "📉",
                "stock_alert": "🔔",
            }.get(entry["type"], "📢")

            lines.append(
                f"*{i}.* {type_icon} `{entry['type']}`\n"
                f"   ⏰ {entry['time']} — 👥 {entry['recipients']} users\n"
                f"   _{entry['preview']}_\n"
            )

        text = "\n".join(lines)
        # Telegram has 4096 char limit
        if len(text) > 4000:
            text = text[:3950] + "\n\n_(truncated)_"

    keyboard = [[InlineKeyboardButton("🔙 Back to Fake Broadcast Panel", callback_data="fbc_panel")]]
    await _safe_edit(q, text, keyboard)


# ════════════════════════════════════════════════════════════════
# 🔇 NO-OP HANDLER (for separator buttons)
# ════════════════════════════════════════════════════════════════

async def fbc_noop_callback(update, context):
    """
    Handles clicks on separator/label buttons in the panel.
    These are decorative buttons (━━━ labels) — clicking them does nothing.
    """
    q = update.callback_query
    await q.answer()  # Just dismiss the loading spinner, do nothing


# ════════════════════════════════════════════════════════════════
# 👥 FAKE USER COUNT SYSTEM
# ════════════════════════════════════════════════════════════════
# This controls the "displayed user count" shown in broadcast messages.
# Example: "Bite Store 🛍️ users: 1,247"
#
# HOW IT WORKS:
#   displayed_count = real_users + fake_offset
#   - real_users:   actual bot users in DB (auto updates as people join)
#   - fake_offset:  number set by admin (100 to 2500, or custom)
#   - displayed:    what users see in new-user join broadcasts
#
# When a new REAL user joins → displayed count auto-increases by 1
# When admin sets offset to 500 and has 3 real users → shows 503
#
# BROADCAST MESSAGE EXAMPLE:
#   🎉 New member joined Bite Store 🛍️
#   👥 Community: 1,247 members
#   Welcome aboard! 🚀


async def fbc_set_usercount_callback(update, context):
    """Ask admin to type a custom fake user count number."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()

    try:
        from database import get_user_count, get_displayed_user_count
        real = get_user_count()
        shown = get_displayed_user_count()
        offset = shown - real
    except Exception:
        real = shown = offset = 0

    keyboard = [
        [InlineKeyboardButton("🎲 Set Random (100–2500)", callback_data="fbc_usercount_random")],
        [InlineKeyboardButton("❌ Cancel", callback_data="fbc_panel")],
    ]
    text = (
        f"👥 *Set Fake User Count*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Current:*\n"
        f"  Real users: {real}\n"
        f"  Fake offset: +{offset}\n"
        f"  Shown total: {shown}\n\n"
        f"*Enter a number (100 to 99999):*\n"
        f"This will be the DISPLAYED count.\n"
        f"Real users will be added on top automatically.\n\n"
        f"*Examples:*\n"
        f"  `500`  → shows 500 + real users\n"
        f"  `1200` → shows 1200 + real users\n"
        f"  `0`    → shows only real users (no fake)"
    )
    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        pass
    return FBC_USER_COUNT


async def fbc_usercount_received(update, context):
    """Save custom user count offset."""
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip().replace(",", "").replace(".", "")
    keyboard = [[InlineKeyboardButton("🔙 Back to Fake Broadcast", callback_data="fbc_panel")]]

    try:
        n = int(text)
        if n < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Enter a valid positive number. Example: `500`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    try:
        from database import set_fake_user_offset, get_user_count
        set_fake_user_offset(n)
        real = get_user_count()
        shown = real + n
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}",
                                        reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ *User Count Updated!*\n\n"
        f"Fake offset: *+{n}*\n"
        f"Real users: *{real}*\n"
        f"Now showing: *{shown} users*\n\n"
        f"_New real joins will auto-increase this count!_",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


async def fbc_usercount_random_callback(update, context):
    """Set a random user count between 100 and 2500."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    import random
    try:
        from database import set_fake_user_offset, get_user_count
        offset = random.randint(100, 2500)
        set_fake_user_offset(offset)
        real = get_user_count()
        shown = real + offset
        await q.answer(f"✅ Set to {shown} users!", show_alert=True)
    except Exception as e:
        await q.answer(f"❌ {e}", show_alert=True)

    await fake_broadcast_panel_callback(update, context)


# ════════════════════════════════════════════════════════════════
# 🆕 NEW USER JOIN BROADCAST
# ════════════════════════════════════════════════════════════════
# Called from handlers_start.py when a new user joins.
# Sends a "New member joined" message to all existing users.
# Shows the fake displayed user count.

async def broadcast_new_user_join(bot, new_user_name: str):
    """
    Send a "New member joined" broadcast to all users.
    Shows the displayed (fake+real) user count.

    Call this from handlers_start.py after a new user joins:
        # [v77-merge] self-bundle import removed: from handlers_fake_broadcast import broadcast_new_user_join
        if is_new and fbc_enabled:
            await broadcast_new_user_join(context.bot, u.first_name)

    The message is only sent if fake broadcast is ENABLED by admin.
    """
    try:
        # [v77-merge] self-bundle import removed: from fake_broadcast import is_enabled, send_to_all_users
        if not is_enabled():
            return

        from database import get_displayed_user_count
        shown = get_displayed_user_count()

        # Use template if admin has customized it
        try:
            from customization import render_template, get_template
            # Check if new_user template exists
            tpl = get_template("bc_new_user")
            if tpl:
                msg = render_template("bc_new_user", {
                    "name": new_user_name or "Someone",
                    "count": f"{shown:,}"
                })
            else:
                raise ValueError("no custom template")
        except Exception:
            # Default template
            import random
            n = new_user_name
            c = f"{shown:,}"
            greetings = [
                f"🎉 *New member joined Bite Store!* 🛍️\n\n"
                f"👤 {n} just joined our community!\n"
                f"👥 Members: *{c}*\n\n"
                f"_Welcome to the family!_ 🚀",

                f"🔔 *New User Alert!*\n\n"
                f"🛍️ Bite Store community grows!\n"
                f"👤 {n} is now member #{c}\n\n"
                f"_Our community is growing fast!_ 📈",

                f"👋 *{n} just joined Bite Store!*\n\n"
                f"👥 We now have *{c}* members!\n\n"
                f"_Join the #1 digital store!_ 🛍️",
            ]
            msg = random.choice(greetings)

        # 🆕 v168.1: Route through destination-based broadcast (not user inbox)
        await broadcast_store_message(bot, msg, bypass_maintenance=True)

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[NewUserBroadcast] Error: {e}")


# ============================================================
# 📄 ORIGINAL FILE: handlers_fake_reviews.py
# ============================================================

# ============================================================
# 🎛️ FAKE REVIEWS ADMIN PANEL — handlers_fake_reviews.py
# ============================================================
#
# Admin Panel → ⭐ Fake Reviews
#
# FEATURES:
#   ✅ Master ON/OFF toggle
#   ✅ Interval control (how often a review is posted)
#   ✅ Pakistani vs International name ratio slider
#   ✅ Toggle: Allow 4-star ratings (more realistic)
#   ✅ Toggle: Allow rating-only posts (no text)
#   ✅ Test: Insert ONE fake review right now
#   ✅ View log (last 30 inserted fake reviews)
#   ✅ View stats (how many fake reviews in DB per product)
#   ✅ Clear all fake reviews (reset button)
#
# REGISTRATION IN bot.py:
# ─────────────────────────
#   from handlers_fake_reviews import (
#       fake_reviews_panel_callback,
#       frv_toggle_main_callback,
#       frv_toggle_setting_callback,
#       frv_set_interval_callback,
#       frv_interval_received,
#       frv_set_ratio_callback,
#       frv_ratio_received,
#       frv_test_callback,
#       frv_log_callback,
#       frv_stats_callback,
#       frv_clear_callback,
#       frv_clear_confirm_callback,
#       frv_noop_callback,
#       FRV_INTERVAL, FRV_RATIO,
#   )
#
#   # ConversationHandlers:
#   app.add_handler(ConversationHandler(
#       entry_points=[CallbackQueryHandler(frv_set_interval_callback, pattern="^frv_set_interval$")],
#       states={FRV_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, frv_interval_received)]},
#       fallbacks=[CommandHandler("cancel", cancel_conversation)],
#   ))
#   app.add_handler(ConversationHandler(
#       entry_points=[CallbackQueryHandler(frv_set_ratio_callback, pattern="^frv_set_ratio$")],
#       states={FRV_RATIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, frv_ratio_received)]},
#       fallbacks=[CommandHandler("cancel", cancel_conversation)],
#   ))
#
#   # CallbackQueryHandlers:
#   app.add_handler(CallbackQueryHandler(fake_reviews_panel_callback,  pattern="^frv_panel$"))
#   app.add_handler(CallbackQueryHandler(frv_toggle_main_callback,     pattern="^frv_toggle_main$"))
#   app.add_handler(CallbackQueryHandler(frv_toggle_setting_callback,  pattern="^frv_toggle_"))
#   app.add_handler(CallbackQueryHandler(frv_test_callback,            pattern="^frv_test"))
#   app.add_handler(CallbackQueryHandler(frv_log_callback,             pattern="^frv_log$"))
#   app.add_handler(CallbackQueryHandler(frv_stats_callback,           pattern="^frv_stats$"))
#   app.add_handler(CallbackQueryHandler(frv_clear_callback,           pattern="^frv_clear$"))
#   app.add_handler(CallbackQueryHandler(frv_clear_confirm_callback,   pattern="^frv_clear_yes$"))
#   app.add_handler(CallbackQueryHandler(frv_noop_callback,            pattern="^frv_noop$"))
#
# ──────────────────────────────────────────────────────────────

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

# [v77-merge] from fake_reviews import (

# [v77-merge] is_enabled, get_interval_range, get_pk_ratio,

# [v77-merge] allow_4star, ratings_only_enabled,

# [v77-merge] insert_fake_review, clear_all_fake_reviews,

# [v77-merge] get_fake_review_count, get_review_log,

# [v77-merge] schedule_fake_reviews,

# [v77-merge] SETTING_ENABLED, SETTING_MIN_INTERVAL, SETTING_MAX_INTERVAL,

# [v77-merge] SETTING_PK_RATIO, SETTING_ALLOW_4STAR, SETTING_RATINGS_ONLY,

# [v77-merge] )
logger = logging.getLogger(__name__)

# Conversation states
FRV_INTERVAL = 901   # For interval input
FRV_RATIO    = 902   # For PK ratio input


# ════════════════════════════════════════════════════════════════
# 🔧 HELPERS
# ════════════════════════════════════════════════════════════════

def _is_admin(user_id):
    from config import ADMIN_ID
    return user_id == ADMIN_ID


def _set(key, value):
    try:
        from database import set_setting
        set_setting(key, str(value))
    except Exception as e:
        logger.error(f"[FRV Panel] DB write error: {e}")


def _get(key, default=""):
    try:
        from database import get_setting
        return get_setting(key, default)
    except Exception:
        return default


def _icon(val):
    """✅ or ❌ based on bool or '1'/'0' string."""
    if isinstance(val, str):
        return "✅" if val == "1" else "❌"
    return "✅" if val else "❌"


async def _safe_edit(q, text, keyboard):
    """Try to edit message, fallback to caption edit."""
    try:
        await q.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        try:
            await q.edit_message_caption(
                caption=text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════
# 🏠 MAIN PANEL
# ════════════════════════════════════════════════════════════════

async def fake_reviews_panel_callback(update, context):
    """
    Main Fake Reviews control panel.
    Access: Admin Panel → ⭐ Fake Reviews
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    # ── Read all settings ──
    enabled    = is_enabled()
    min_m, max_m = get_interval_range()
    pk_ratio   = get_pk_ratio()
    intl_ratio = 100 - pk_ratio
    a4star     = allow_4star()
    rat_only   = ratings_only_enabled()
    total_fake = get_fake_review_count()

    status_icon = "🟢 *ACTIVE*" if enabled else "🔴 *INACTIVE*"

    text = (
        f"⭐ *Fake Reviews Control Panel*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔌 Status: {status_icon}\n"
        f"⏱️ Interval: Every {min_m}–{max_m} min (random)\n"
        f"🗃️ Total Fake Reviews in DB: *{total_fake}*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*Name Mix Ratio:*\n"
        f"  🇵🇰 Pakistani: *{pk_ratio}%*  🌍 International: *{intl_ratio}%*\n\n"
        f"*Review Settings:*\n"
        f"  {_icon(a4star)} Allow 4-star ratings (more realistic)\n"
        f"  {_icon(rat_only)} Allow rating-only posts (no text, ~30%)\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*How it works:*\n"
        f"• Real Pakistani names → Roman Urdu text\n"
        f"• International names → English text\n"
        f"• Only in-stock products get reviews\n"
        f"• Real user reviews always show too\n"
        f"• Fake users use IDs 9B+ (safe range)"
    )

    master_label = "🔴 Turn OFF Fake Reviews" if enabled else "🟢 Turn ON Fake Reviews"

    keyboard = [
        [InlineKeyboardButton(master_label, callback_data="frv_toggle_main")],
        [InlineKeyboardButton("━━━━━ Settings ━━━━━", callback_data="frv_noop")],
        [InlineKeyboardButton(f"⏱️ Set Interval ({min_m}–{max_m} min)", callback_data="frv_set_interval")],
        [InlineKeyboardButton(f"🇵🇰 PK Ratio: {pk_ratio}% / 🌍 Intl: {intl_ratio}%", callback_data="frv_set_ratio")],
        [InlineKeyboardButton("━━━━━ Toggles ━━━━━", callback_data="frv_noop")],
        [
            InlineKeyboardButton(f"{_icon(a4star)} 4-Star Ratings", callback_data="frv_toggle_4star"),
            InlineKeyboardButton(f"{_icon(rat_only)} Rating-Only Posts", callback_data="frv_toggle_ratingonly"),
        ],
        [InlineKeyboardButton("━━━━━ Actions ━━━━━", callback_data="frv_noop")],
        [
            InlineKeyboardButton("🧪 Test: Post Pakistani Review", callback_data="frv_test_pk"),
            InlineKeyboardButton("🧪 Test: Post Intl Review",      callback_data="frv_test_intl"),
        ],
        [
            InlineKeyboardButton("🧪 Test: Rating Only",    callback_data="frv_test_rating"),
            InlineKeyboardButton("🧪 Test: Random Review",  callback_data="frv_test_random"),
        ],
        [InlineKeyboardButton("📋 View Review Log",     callback_data="frv_log")],
        [InlineKeyboardButton("📊 Stats by Product",    callback_data="frv_stats")],
        [InlineKeyboardButton("🗑️ Clear ALL Fake Reviews", callback_data="frv_clear")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")],
    ]

    await _safe_edit(q, text, keyboard)


# ════════════════════════════════════════════════════════════════
# 🔌 MASTER TOGGLE
# ════════════════════════════════════════════════════════════════

async def frv_toggle_main_callback(update, context):
    """Toggle the entire fake reviews system ON or OFF."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    current = _get(SETTING_ENABLED, "0")
    new_val = "0" if current == "1" else "1"
    _set(SETTING_ENABLED, new_val)

    if new_val == "1":
        # Start the scheduler
        try:
            schedule_fake_reviews(context.application)
            await q.answer("✅ Fake Reviews ENABLED! First review coming soon.", show_alert=True)
        except Exception as e:
            logger.error(f"[FRV] Schedule error: {e}")
            await q.answer("✅ Enabled. Restart bot for scheduler to work.", show_alert=True)
    else:
        await q.answer("🔴 Fake Reviews DISABLED.", show_alert=True)

    await fake_reviews_panel_callback(update, context)


# ════════════════════════════════════════════════════════════════
# 🎛️ TOGGLE SETTINGS (4-star / rating-only)
# ════════════════════════════════════════════════════════════════

# Maps callback suffix → (setting_key, label)
_TOGGLE_MAP = {
    "4star":       (SETTING_ALLOW_4STAR,   "4-Star Ratings"),
    "ratingonly":  (SETTING_RATINGS_ONLY,  "Rating-Only Posts"),
}


async def frv_toggle_setting_callback(update, context):
    """
    Toggle a specific review setting.
    Callback patterns:
      frv_toggle_4star       → toggle 4-star ratings
      frv_toggle_ratingonly  → toggle rating-only posts
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return

    # Extract key from "frv_toggle_4star" → "4star"
    suffix = q.data.replace("frv_toggle_", "")
    if suffix in ("main",):  # handled by other callback
        await q.answer()
        return

    entry = _TOGGLE_MAP.get(suffix)
    if not entry:
        await q.answer("❌ Unknown toggle.", show_alert=True)
        return

    setting_key, label = entry
    current = _get(setting_key, "1")
    new_val = "0" if current == "1" else "1"
    _set(setting_key, new_val)

    status = "✅ Enabled" if new_val == "1" else "❌ Disabled"
    await q.answer(f"{label}: {status}", show_alert=False)

    await fake_reviews_panel_callback(update, context)


# ════════════════════════════════════════════════════════════════
# ⏱️ INTERVAL SETTER
# ════════════════════════════════════════════════════════════════

async def frv_set_interval_callback(update, context):
    """Ask admin to enter new review interval range."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()

    min_m, max_m = get_interval_range()
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="frv_panel")]]

    text = (
        f"⏱️ *Set Review Interval*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: *{min_m}–{max_m} minutes*\n\n"
        f"Enter new range as: `MIN MAX`\n\n"
        f"Examples:\n"
        f"  `15 60`   → a review every 15–60 min\n"
        f"  `5 30`    → faster (more reviews per day)\n"
        f"  `60 240`  → slow (few reviews per day)\n"
        f"  `1 5`     → very fast (testing only)\n\n"
        f"⚠️ Min must be ≥ 1. Max must be > Min."
    )

    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        pass
    return FRV_INTERVAL


async def frv_interval_received(update, context):
    """Save new interval values."""
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()
    parts = text.split()
    error = None

    if len(parts) != 2:
        error = "❌ Send two numbers separated by space.\nExample: `15 90`"
    else:
        try:
            min_m, max_m = int(parts[0]), int(parts[1])
            if min_m < 1:
                error = "❌ Minimum must be at least 1 minute."
            elif max_m <= min_m:
                error = f"❌ Maximum ({max_m}) must be greater than minimum ({min_m})."
        except ValueError:
            error = "❌ Use whole numbers only. Example: `15 90`"

    kb = [[InlineKeyboardButton("🔙 Back to Fake Reviews Panel", callback_data="frv_panel")]]

    if error:
        await update.message.reply_text(error, parse_mode="Markdown",
                                        reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    _set(SETTING_MIN_INTERVAL, str(min_m))
    _set(SETTING_MAX_INTERVAL, str(max_m))

    await update.message.reply_text(
        f"✅ *Interval Updated!*\n\nNew range: *{min_m}–{max_m} minutes*",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════
# 🇵🇰 PK RATIO SETTER
# ════════════════════════════════════════════════════════════════

async def frv_set_ratio_callback(update, context):
    """Ask admin to enter Pakistani name percentage (0–100)."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()

    pk = get_pk_ratio()
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="frv_panel")]]

    text = (
        f"🇵🇰 *Set Pakistani Name Ratio*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: *{pk}% Pakistani / {100-pk}% International*\n\n"
        f"Enter a number from 0 to 100:\n\n"
        f"Examples:\n"
        f"  `100`  → All Pakistani names\n"
        f"  `60`   → 60% Pakistani, 40% International (default)\n"
        f"  `50`   → Equal mix\n"
        f"  `0`    → All International names\n\n"
        f"Pakistani names → Roman Urdu reviews\n"
        f"International names → English reviews"
    )

    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        pass
    return FRV_RATIO


async def frv_ratio_received(update, context):
    """Save new PK ratio."""
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()
    kb = [[InlineKeyboardButton("🔙 Back to Fake Reviews Panel", callback_data="frv_panel")]]

    try:
        ratio = int(text)
        if not 0 <= ratio <= 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Enter a number between 0 and 100.\nExample: `60`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
        )
        return ConversationHandler.END

    _set(SETTING_PK_RATIO, str(ratio))
    intl = 100 - ratio

    await update.message.reply_text(
        f"✅ *Name Ratio Updated!*\n\n"
        f"🇵🇰 Pakistani: *{ratio}%*\n"
        f"🌍 International: *{intl}%*",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════
# 🧪 TEST SENDER
# ════════════════════════════════════════════════════════════════

async def frv_test_callback(update, context):
    """
    Manually insert one fake review for testing.
    Callback patterns:
      frv_test_pk       → force Pakistani name + Urdu text
      frv_test_intl     → force International name + English text
      frv_test_rating   → rating only (no text)
      frv_test_random   → fully random
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer("⏳ Inserting test review...", show_alert=False)

    suffix = q.data.replace("frv_test_", "")

    # Temporarily override settings for specific test types
    force_lang = None

    force_no_text = False
    if suffix == "pk":
        force_lang = "urdu"
    elif suffix == "intl":
        force_lang = "english"
    elif suffix == "rating":
        # Force rating-only — no text at all
        force_no_text = True
        force_lang = None
    # "random" = no overrides

    try:
        result = insert_fake_review(force_language=force_lang, force_no_text=force_no_text)

        if result:
            lang_flag = "🇵🇰" if result["language"] == "urdu" else "🌍"
            stars = "⭐" * result["rating"]
            text_preview = result["text"][:80] if result["text"] else "_(rating only — no text)_"
            msg = (
                f"✅ *Fake Review Inserted!*\n\n"
                f"👤 Name: *{result['name']}* {lang_flag}\n"
                f"📦 Product: *{result['product']}*\n"
                f"Rating: {stars}\n"
                f"Text: _{text_preview}_"
            )
        else:
            msg = (
                "⚠️ *Could not insert test review.*\n\n"
                "Possible reasons:\n"
                "• No in-stock products in your shop\n"
                "• All fake users already reviewed all products"
            )
    except Exception as e:
        msg = f"❌ *Error:*\n`{str(e)}`"
    finally:
        pass  # No temp settings to restore

    keyboard = [[InlineKeyboardButton("🔙 Back to Fake Reviews Panel", callback_data="frv_panel")]]

    try:
        await q.edit_message_text(msg, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        try:
            await q.message.reply_text(msg, parse_mode="Markdown",
                                       reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════
# 📋 LOG VIEWER
# ════════════════════════════════════════════════════════════════

async def frv_log_callback(update, context):
    """Show last 30 fake reviews that were inserted this session."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    log = get_review_log()
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="frv_panel")]]

    if not log:
        text = (
            "📋 *Fake Review Log*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "No fake reviews inserted yet this session.\n"
            "Use a test button or wait for the scheduler."
        )
    else:
        lines = [f"📋 *Fake Review Log (Last {min(len(log), 30)})*\n━━━━━━━━━━━━━━━━━━━━\n"]
        for i, entry in enumerate(log[:30], 1):
            stars = "⭐" * entry["rating"]
            lines.append(
                f"*{i}.* {entry['lang']} *{entry['name']}*\n"
                f"   📦 {entry['product']}\n"
                f"   {stars}\n"
                f"   _{entry['preview']}_\n"
                f"   ⏰ {entry['time']}\n"
            )
        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3950] + "\n\n_(truncated)_"

    await _safe_edit(q, text, keyboard)


# ════════════════════════════════════════════════════════════════
# 📊 STATS BY PRODUCT
# ════════════════════════════════════════════════════════════════

async def frv_stats_callback(update, context):
    """Show how many fake reviews each product has."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="frv_panel")]]

    try:
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Get fake review count per product
        cursor.execute("""
            SELECT pr.product_id,
                   p.name as product_name,
                   COUNT(*) as fake_count,
                   AVG(pr.rating) as avg_rating,
                   COUNT(CASE WHEN pr.review_text != '' THEN 1 END) as with_text
            FROM product_reviews pr
            LEFT JOIN products p ON pr.product_id = p.id
            WHERE pr.user_id >= 9000000000
            GROUP BY pr.product_id
            ORDER BY fake_count DESC
            LIMIT 20
        """)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            text = (
                "📊 *Fake Reviews Stats*\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "No fake reviews in database yet."
            )
        else:
            lines = ["📊 *Fake Reviews by Product*\n━━━━━━━━━━━━━━━━━━━━\n"]
            for row in rows:
                name = (row["product_name"] or f"#{row['product_id']}")[:30]
                avg  = row["avg_rating"] or 0
                stars_count = int(round(avg))
                stars_str = "⭐" * stars_count
                lines.append(
                    f"📦 *{name}*\n"
                    f"   Reviews: *{row['fake_count']}* "
                    f"({row['with_text']} with text)\n"
                    f"   Avg: {stars_str} {avg:.1f}\n"
                )
            text = "\n".join(lines)
            if len(text) > 4000:
                text = text[:3950] + "\n\n_(truncated)_"

    except Exception as e:
        text = f"❌ Error fetching stats:\n`{str(e)}`"

    await _safe_edit(q, text, keyboard)


# ════════════════════════════════════════════════════════════════
# 🗑️ CLEAR ALL FAKE REVIEWS
# ════════════════════════════════════════════════════════════════

async def frv_clear_callback(update, context):
    """Ask admin to confirm before deleting all fake reviews."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    total = get_fake_review_count()
    text = (
        f"🗑️ *Clear All Fake Reviews?*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"This will permanently delete *{total} fake reviews* from the database.\n\n"
        f"⚠️ *Real user reviews will NOT be affected.*\n\n"
        f"Are you sure?"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, Delete All", callback_data="frv_clear_yes"),
            InlineKeyboardButton("❌ Cancel",          callback_data="frv_panel"),
        ]
    ]
    await _safe_edit(q, text, keyboard)


async def frv_clear_confirm_callback(update, context):
    """Execute the clear — delete all fake reviews from DB."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer("🗑️ Deleting...", show_alert=False)

    deleted = clear_all_fake_reviews()

    keyboard = [[InlineKeyboardButton("🔙 Back to Fake Reviews Panel", callback_data="frv_panel")]]
    text = (
        f"✅ *Done!*\n\n"
        f"Deleted *{deleted} fake reviews* from the database.\n\n"
        f"Real user reviews are all safe. ✅"
    )
    await _safe_edit(q, text, keyboard)


# ════════════════════════════════════════════════════════════════
# 🔇 NO-OP (separator buttons)
# ════════════════════════════════════════════════════════════════

async def frv_noop_callback(update, context):
    """Handles clicks on decorative separator buttons — does nothing."""
    await update.callback_query.answer()


# ============================================================
# 📄 ORIGINAL FILE: store_broadcast.py
# ============================================================

# ════════════════════════════════════════════════════════════════
# 📣 STORE BROADCAST — Flash Sale + New Product announcements
# ════════════════════════════════════════════════════════════════
# Sends real store announcements (flash sale, new product) to the SAME
# destination configured for Fake Activity:
#   dest_mode = "bot_only" | "group_only" | "both"
#   dest_chat_id = group/channel @username or numeric id
#
# Also holds the 10 selectable templates for Flash Sale and New Product.
# ════════════════════════════════════════════════════════════════

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils import smart_text_and_mode

logger = logging.getLogger(__name__)


def _is_product_broadcastable(pid):
    """🆕 v60: Decide whether a product is safe to broadcast about.

    A product is BROADCASTABLE only when ALL of these are true:
      1. Product exists in DB (not deleted by admin)
      2. is_active == 1 (not soft-deleted)
      3. is_hidden == 0 (admin hasn't hidden it)
      4. stock > 0  (currently buyable)
      5. 🆕 v169: name doesn't contain "api test" AND pid not excluded

    Defensive: any DB error → return False (skip broadcast = safe).
    """
    try:
        from database import get_product, is_product_hidden, get_setting
        pid = int(pid)
        p = get_product(pid)
        if not p:
            return False
        d = dict(p)
        if int(d.get("is_active", 0) or 0) != 1:
            return False
        if is_product_hidden(pid):
            return False
        if int(d.get("stock", 0) or 0) <= 0:
            return False
        # 🆕 v169: Exclude test/API products from ALL broadcasts
        name = (d.get("name") or "").lower()
        if "api test" in name or "apitest" in name:
            return False
        # Also check admin-configured exclusion list
        exclude_ids = str(get_setting("broadcast_exclude_products", "") or "").strip()
        if exclude_ids:
            excluded = [int(x.strip()) for x in exclude_ids.split(",") if x.strip().isdigit()]
            if pid in excluded:
                return False
        return True
    except Exception as e:
        logger.warning(f"[_is_product_broadcastable] pid={pid} check failed: {e} → skipping broadcast")
        return False


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


# ════════════════════════════════════════════════════════════════
# 📋 SELECTABLE TEMPLATES
# ════════════════════════════════════════════════════════════════
# Each template uses {placeholders}. A "🛒 Buy Now" button is added
# automatically by the sender — do NOT put it in the text.
#
# Flash sale vars: {product} {price} {regular} {save} {timer}
# New product vars: {product} {price} {desc} {stock}
# ════════════════════════════════════════════════════════════════

FLASH_TEMPLATES = [
    # 1 — the default one provided by the owner
    ("🛍 *FLASH SALE — LIMITED TIME!*\n\n"
     "💝 *{product}*\n\n"
     "💵 Sale Price: *${price}*\n"
     "Regular: ${regular} — Save ${save}\n\n"
     "🕐 Ends in: {timer}\n\n"
     "Hurry — grab it before time runs out!"),
    # 2
    ("⚡⚡ *FLASH DEAL ALERT!* ⚡⚡\n\n"
     "🔥 *{product}*\n\n"
     "💸 Now only *${price}* (was ${regular})\n"
     "🎯 You save *${save}!*\n\n"
     "⏳ Offer ends in: {timer}\n\n"
     "👉 Tap *Buy Now* before it's gone!"),
    # 3
    ("🚨 *MEGA FLASH SALE!* 🚨\n\n"
     "🛒 *{product}*\n"
     "━━━━━━━━━━━━━━━━━━━━\n"
     "💵 Flash Price: *${price}*\n"
     "❌ Old Price: ${regular}\n"
     "💰 Savings: *${save}*\n"
     "━━━━━━━━━━━━━━━━━━━━\n"
     "⌛ Hurry! Ends in {timer}"),
    # 4
    ("🔥 *HOT DEAL — TODAY ONLY!* 🔥\n\n"
     "✨ *{product}* ✨\n\n"
     "🎉 Special Price: *${price}*\n"
     "🏷️ Regular: ${regular} | Save ${save}\n\n"
     "⏰ Time left: {timer}\n\n"
     "💥 Don't miss out — buy now!"),
    # 5
    ("💎 *EXCLUSIVE FLASH OFFER!* 💎\n\n"
     "🛍 *{product}*\n\n"
     "💵 Just *${price}* (normally ${regular})\n"
     "📉 Discount saves you *${save}!*\n\n"
     "🕐 Ending in: {timer}\n\n"
     "⚡ Limited stock — grab yours fast!"),
    # 6
    ("⏰ *LIGHTNING SALE!* ⚡\n\n"
     "📦 *{product}*\n\n"
     "🔻 Price slashed to *${price}!*\n"
     "Was ${regular} — Save ${save}\n\n"
     "⌛ Hurry! Only {timer} left\n\n"
     "🛒 Tap below to order instantly!"),
    # 7
    ("🎁 *FLASH SALE BONANZA!* 🎁\n\n"
     "🌟 *{product}*\n"
     "💵 Sale: *${price}* 🔥\n"
     "🚫 Regular: ${regular}\n"
     "✅ You Save: *${save}*\n\n"
     "⏳ Deal expires in {timer}\n\n"
     "Don't sleep on this one! 😴➡️🛒"),
    # 8
    ("🛎️ *DON'T MISS THIS DEAL!* 🛎️\n\n"
     "🔥 *{product}* is on FLASH SALE!\n\n"
     "💲 Now: *${price}* (save ${save})\n"
     "💤 Was: ${regular}\n\n"
     "⏱️ Countdown: {timer}\n\n"
     "🚀 Buy now before the price jumps back!"),
    # 9
    ("💰 *PRICE DROP!* 💰\n\n"
     "🎯 *{product}*\n\n"
     "🤑 Flash Price: *${price}*\n"
     "📊 Normal: ${regular} → Save *${save}*\n\n"
     "🔔 Ends in: {timer}\n\n"
     "⚡ Instant delivery — order today!"),
    # 10
    ("🏆 *BEST DEAL OF THE DAY!* 🏆\n\n"
     "🛍 *{product}*\n"
     "━━━━━━━━━━━━━━━━━━━━\n"
     "💵 *${price}* only!\n"
     "🏷️ Regular ${regular} • Save ${save}\n"
     "━━━━━━━━━━━━━━━━━━━━\n"
     "⏳ {timer} remaining\n\n"
     "🔥 Grab it before it's too late!"),
]

NEW_PRODUCT_TEMPLATES = [
    # 1 — default
    ("🆕 *NEW PRODUCT ADDED!* 🛍\n\n"
     "📦 *{product}*\n\n"
     "💵 Price: *${price}*\n"
     "{desc}\n"
     "🛒 Available now — tap Buy Now!"),
    # 2
    ("✨ *JUST ARRIVED!* ✨\n\n"
     "🎉 *{product}* is now in stock!\n\n"
     "💰 Only *${price}*\n"
     "{desc}\n"
     "⚡ Be the first to grab it!"),
    # 3
    ("📢 *FRESH STOCK ALERT!* 📢\n\n"
     "🆕 *{product}*\n"
     "━━━━━━━━━━━━━━━━━━━━\n"
     "💵 Price: *${price}*\n"
     "📦 In Stock: {stock}\n"
     "{desc}"
     "━━━━━━━━━━━━━━━━━━━━\n"
     "🛒 Order now!"),
    # 4
    ("🔥 *NEW DROP!* 🔥\n\n"
     "🛍 *{product}* just landed!\n\n"
     "💸 Grab it for *${price}*\n"
     "{desc}\n"
     "🚀 Limited stock — buy fast!"),
    # 5
    ("🎊 *NEW ADDITION TO THE STORE!* 🎊\n\n"
     "📦 *{product}*\n\n"
     "💵 Launch Price: *${price}*\n"
     "{desc}\n"
     "✅ Instant delivery available!"),
    # 6
    ("💥 *CHECK THIS OUT!* 💥\n\n"
     "🆕 *{product}*\n\n"
     "🤑 Only *${price}*\n"
     "{desc}\n"
     "🛒 Tap Buy Now to order!"),
    # 7
    ("🌟 *NOW AVAILABLE!* 🌟\n\n"
     "🎁 *{product}*\n"
     "💰 Price: *${price}*\n"
     "{desc}\n"
     "⚡ Get yours before stock runs out!"),
    # 8
    ("🛎️ *STORE UPDATE!* 🛎️\n\n"
     "We just added *{product}*! 🎉\n\n"
     "💵 Price: *${price}*\n"
     "{desc}\n"
     "🛒 Order now for instant delivery!"),
    # 9
    ("🚀 *NEW LAUNCH!* 🚀\n\n"
     "🔥 *{product}*\n\n"
     "💲 Introductory Price: *${price}*\n"
     "{desc}\n"
     "🏃 Hurry — grab it today!"),
    # 10
    ("📦 *NEW IN STORE!* 📦\n\n"
     "✨ *{product}* ✨\n"
     "━━━━━━━━━━━━━━━━━━━━\n"
     "💵 *${price}*\n"
     "{desc}"
     "━━━━━━━━━━━━━━━━━━━━\n"
     "🛒 Buy now & enjoy!"),
]

# Setting keys for the selected template index (0-based).
FLASH_TPL_KEY = "flash_tpl_index"
NEWPROD_TPL_KEY = "newprod_tpl_index"


_EMOJI_DIGITS = {
    "0": "0️⃣", "1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣",
    "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣",
}


def _flash_timer_text(until_str):
    """Build a remaining-time string like 2️⃣3️⃣➖5️⃣9️⃣➖5️⃣9️⃣ from an expiry datetime string."""
    from datetime import datetime
    try:
        until = datetime.strptime(until_str, "%Y-%m-%d %H:%M:%S")
        delta = until - datetime.now()
        secs = int(delta.total_seconds())
        if secs < 0:
            secs = 0
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        # cap hours display at 99 for layout
        hh = f"{min(h,99):02d}"
        mm = f"{m:02d}"
        ss = f"{s:02d}"
        def emj(t):
            return "".join(_EMOJI_DIGITS.get(ch, ch) for ch in t)
        return f"{emj(hh)}➖{emj(mm)}➖{emj(ss)}"
    except Exception:
        return "2️⃣3️⃣➖5️⃣9️⃣➖5️⃣9️⃣"


def get_flash_template_index():
    try:
        return max(0, min(len(FLASH_TEMPLATES) - 1, int(_g(FLASH_TPL_KEY, "0") or 0)))
    except Exception:
        return 0


def get_newprod_template_index():
    try:
        return max(0, min(len(NEW_PRODUCT_TEMPLATES) - 1, int(_g(NEWPROD_TPL_KEY, "0") or 0)))
    except Exception:
        return 0


def set_flash_template_index(i):
    _s(FLASH_TPL_KEY, int(i))


def set_newprod_template_index(i):
    _s(NEWPROD_TPL_KEY, int(i))


# ════════════════════════════════════════════════════════════════
# 🧱 MESSAGE BUILDERS
# ════════════════════════════════════════════════════════════════

# Custom-template override keys (admin's own text). Empty = use selected variant.
FLASH_CUSTOM_KEY = "flash_tpl_custom"
NEWPROD_CUSTOM_KEY = "newprod_tpl_custom"


def get_flash_custom():
    return _g(FLASH_CUSTOM_KEY, "")


def get_newprod_custom():
    return _g(NEWPROD_CUSTOM_KEY, "")


def set_flash_custom(text):
    _s(FLASH_CUSTOM_KEY, text or "")


def set_newprod_custom(text):
    _s(NEWPROD_CUSTOM_KEY, text or "")


def build_flash_message(product, timer_text="23-59-59", tpl_index=None):
    """Return the flash-sale broadcast text (no button).
    Uses admin custom text if set, else the selected variant."""
    d = dict(product)
    price = float(d.get('flash_price', 0) or 0)
    regular = float(d.get('price', 0) or 0)
    save = round(regular - price, 2)
    custom = get_flash_custom()
    if custom and tpl_index is None:
        tpl = custom
    else:
        idx = get_flash_template_index() if tpl_index is None else tpl_index
        idx = max(0, min(len(FLASH_TEMPLATES) - 1, idx))
        tpl = FLASH_TEMPLATES[idx]
    # 🐛 v144.3 FIX: `.format()` raised KeyError when a custom template used a
    # placeholder not in the args (e.g. {old_price}) → except returned the RAW
    # template → all placeholders (incl. {price}) were sent literally.
    # 🐛 v149 FIX: case-insensitive filling — custom template had `{Product}`
    # (capital P) which the old exact-key map left LITERAL. Now any casing works.
    try:
        _pname = _product_name_with_fixed_emoji(d)
        return _fill_placeholders_ci(tpl, {
            'product': _pname,
            'product_name': _pname,
            'price': f"{price:.2f}",
            'old_price': f"{regular:.2f}",
            'regular': f"{regular:.2f}",
            'save': f"{save:.2f}",
            'discount': f"{save:.2f}",
            'timer': timer_text,
            'timer_text': timer_text,
        })
    except Exception:
        return tpl  # custom text with no/odd placeholders


def build_newproduct_message(product, tpl_index=None):
    """Return the new-product broadcast text (no button).
    Uses admin custom text if set, else the selected variant."""
    d = dict(product)
    price = float(d.get('price', 0) or 0)
    desc_raw = (d.get('description') or '').strip()
    desc = f"📝 {desc_raw}\n\n" if desc_raw else ""
    stock = d.get('stock', 0)
    custom = get_newprod_custom()
    if custom and tpl_index is None:
        tpl = custom
    else:
        idx = get_newprod_template_index() if tpl_index is None else tpl_index
        idx = max(0, min(len(NEW_PRODUCT_TEMPLATES) - 1, idx))
        tpl = NEW_PRODUCT_TEMPLATES[idx]
    try:
        _pname = _product_name_with_fixed_emoji(d)
        return _fill_placeholders_ci(tpl, {
            'product': _pname,
            'product_name': _pname,
            'price': f"{price:.2f}",
            'desc': desc,
            'stock': stock,
        })
    except Exception:
        return tpl


def build_real_purchase_message(product_name, qty=1, amount=None, pid=None):
    """Build a REAL purchase announcement using the admin's selected
    bc_purchase template (mask the buyer as a generic happy customer)."""
    import random
    masked = random.choice(["a•••i", "m•••d", "s•••a", "z•••n", "h•••a", "k•••l", "f•••z"])
    # Work out amount + PKR (best effort)
    amt = amount
    pkr_amount = ""
    try:
        if amt is None and pid is not None:
            from database import get_product
            pr = get_product(pid)
            if pr:
                base = float(dict(pr).get('flash_price') or 0) if dict(pr).get('is_flash_sale') else float(dict(pr).get('price') or 0)
                amt = round(base * max(1, int(qty)), 2)
        if amt is not None:
            from database import get_setting
            rate = float(get_setting("usd_to_pkr_rate", get_setting("usd_pkr_rate", "280")) or 280)
            pkr_amount = f"Rs {int(amt * rate):,}"
    except Exception:
        pass
    amount_txt = f"{amt:.2f}" if isinstance(amt, (int, float)) else "—"
    try:
        from customization import render_template
        msg = render_template("bc_purchase", {
            "user": masked,
            "product": product_name,
            "qty": str(qty),
            "amount": amount_txt,
            "pkr_amount": pkr_amount or "—",
            "txid": f"BITE-{random.randint(100000, 999999)}-PK",
        })
        if msg:
            return msg
    except Exception:
        pass
    return (f"🛒 New Purchase! 🏪\n\n"
            f"📦 {product_name}\n"
            f"🔢 Qty: {qty}\n\n"
            f"⚡ Delivered instantly ✅")


def build_real_freebie_message(product_name, pid=None):
    """🆕 v170.25: REAL freebie claim → admin's bc_freebie template (masked
    username), so destination par "freebies" wala alert jaye — "new purchase"
    wala nahi."""
    import random
    masked = random.choice(["a•••i", "m•••d", "s•••a", "z•••n", "h•••a", "k•••l", "f•••z"])
    try:
        from utils import html_strip_tags as _hst
        product = _hst(str(product_name or "")) or "a free product"
    except Exception:
        product = str(product_name or "a free product")
    product = product.strip()
    if len(product) > 200:
        product = product[:200]
    try:
        from customization import render_template
        msg = render_template("bc_freebie", {"user": masked, "product": product})
        if msg:
            return msg
    except Exception:
        pass
    return (f"🎁 *FREEBIE CLAIMED!* 🎉\n\n"
            f"👤 {masked} just got {product} for FREE!\n"
            f"🆓 100% free — tap below and grab yours too!")


def _fill_placeholders_ci(template, mapping):
    """🐛 v149 FIX: fill {Placeholders} CASE-INSENSITIVELY.

    The old code used `str.format_map({...})` with exact lowercase keys. The
    admin's custom flash template used `{Product}` (capital P) → the key didn't
    match `product` → the placeholder went out LITERALLY as "{Product}".
    Now any casing of {product}/{Product}/{PRODUCT} is filled; unknown keys
    stay untouched."""
    import re as _re
    if not template or "{" not in template:
        return template
    low_map = {str(k).lower(): v for k, v in (mapping or {}).items()}

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

    return _re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)(:[^}]*)?\}", _sub, template)


def _product_name_with_fixed_emoji(product):
    """🐛 v149 FIX: product name for templates, prefixed with its FIXED emoji
    (supplier ext emoji) when one exists — so flash/new-product broadcasts show
    the emoji with the name exactly like the shop.

    Rules:
      - name already contains premium <tg-emoji> markup → leave as-is (the
        shop name emoji is already there; no double emoji).
      - name already starts with the emoji char → leave as-is.
      - otherwise prepend the fixed emoji (premium when an id exists)."""
    try:
        d = dict(product) if product else {}
        raw = str(d.get("name") or "Product")
        pid = d.get("id")
        if not pid:
            return raw
        if "<tg-emoji" in raw.lower():
            return raw
        eid, ech = _product_buy_emoji(int(pid))
        if not ech:
            return raw
        plain = raw.replace("[[HTML]]", "")
        if plain.lstrip().startswith(ech):
            return raw
        if eid:
            return f'[[HTML]]<tg-emoji emoji-id="{eid}">{ech}</tg-emoji> {raw}'
        return f"{ech} {raw}"
    except Exception:
        return str(product.get("name") or "Product") if product else "Product"


# ─────────────────────────────────────────────
# 🆕 v161.20: auto-emoji for products whose name has no emoji — every Buy-Now
# button shows "{emoji} First Two Words Buy Now" consistently.
# _AUTO_FALLBACK_EMOJI / _AUTO_PRODUCT_EMOJI
# ─────────────────────────────────────────────
# 🆕 v161.20: auto-emoji for products whose name has no emoji — every Buy-Now
# button shows "{emoji} First Two Words Buy Now" consistently.
_AUTO_FALLBACK_EMOJI = "🛍️"
_AUTO_PRODUCT_EMOJI = [
    ("chatgpt", "🤖"), ("chat gpt", "🤖"), ("gpt", "🤖"), ("openai", "🤖"),
    ("gemini", "🤖"), ("bard", "🤖"), ("ai", "🤖"), ("claude", "🤖"),
    ("codex", "🧠"), ("midjourney", "🎨"), ("leonardo", "🎨"), ("canva", "🎨"),
    ("adobe", "🎨"), ("autodesk", "🎨"), ("autocad", "📐"), ("3ds max", "📐"),
    ("netflix", "🎬"), ("disney", "🎬"), ("prime", "🎬"), ("spotify", "🎵"),
    ("youtube", "▶️"), ("yt", "▶️"), ("video", "▶️"), ("mail", "📧"),
    ("outlook", "📧"), ("hotmail", "📧"), ("gmail", "📧"), ("email", "📧"),
    ("vpn", "🔐"), ("surfshark", "🔐"), ("proxy", "🔐"), ("instagram", "📱"),
    ("tiktok", "📱"), ("whatsapp", "📱"), ("telegram", "✈️"), ("twitter", "🐦"),
    ("capcut", "✴️"), ("cap cut", "✴️"), ("elevenlab", "🗣️"), ("voice", "🗣️"),
    ("scribd", "📖"), ("wink", "🔼"), ("meitu", "👍"), ("key", "🔑"),
    ("license", "🔑"), ("account", "👤"), ("subscription", "📅"), ("panel", "🖥️"),
    ("server", "🖥️"), ("hosting", "🖥️"), ("app", "📱"), ("movie", "🎬"),
    ("tv", "📺"), ("stream", "📺"), ("course", "🎓"), ("book", "📚"),
    ("game", "🎮"), ("gaming", "🎮"), ("xbox", "🎮"), ("playstation", "🎮"),
    ("nord", "🔐"), ("express vpn", "🔐"), ("glass", "💎"),
]
# ─────────────────────────────────────────────────────────────
# 🆕 v94: Buy Now button — product-name prefix + global color
# ─────────────────────────────────────────────────────────────
def _product_buy_emoji(pid):
    """🐛 v147 FIX (Bug6): return (emoji_id, emoji_char) for a product's
    Buy-Now button.

    Priority:
      1. SUPPLIER-LINKED products → the FIXED premium emoji the admin set in
         the supplier emoji library (`ext_products.emoji_id` / `emoji_char`).
         Supplier raw names carry no emoji; this fixed emoji is the source of
         truth the owner wants on the button.
      2. OWN (manual) products → the premium emoji inside the product NAME
         (the owner types it directly in the name, e.g.
         `[[HTML]]<tg-emoji ...>🎨</tg-emoji>Canva 500 User Panel`).
    Returns ("", "") when nothing is found.
    """
    try:
        from database import get_connection
        c = get_connection().cursor()
        # 1) supplier-linked → fixed emoji from ext_products
        c.execute(
            "SELECT e.emoji_id, e.emoji_char FROM ext_products e "
            "WHERE e.shop_product_id=? AND e.emoji_id IS NOT NULL AND e.emoji_id!='' "
            "LIMIT 1", (int(pid),))
        row = c.fetchone()
        if row:
            eid = str(row[0] or "").strip()
            ech = str(row[1] or "").strip()
            if eid or ech:
                return eid, ech
        # 2) own product → premium emoji from the NAME
        c.execute("SELECT name FROM products WHERE id=?", (int(pid),))
        row = c.fetchone()
        if row:
            try:
                import re as _re
                raw = str(row["name"] or "")
                # 🐛 v161.20 FIX: extract_emoji_from_html() returns (eid,
                # REST_TEXT_WITHOUT_EMOJI) — the old code used that rest text as
                # the emoji char → button labels like "Canva 500 User Panel Buy
                # Now" instead of "🎨 Canva 500 Buy Now". Grab the FALLBACK char
                # that lives INSIDE the <tg-emoji> tag instead.
                m = _re.search(
                    r'<tg-emoji\s+emoji-id=["\'](\d+)["\']\s*>\s*([^<]{1,8})\s*</tg-emoji>',
                    raw, flags=_re.I)
                if m:
                    return str(m.group(1)), str(m.group(2)).strip()
                # legacy: no <tg-emoji> tag → leading regular emoji chars
                em = _re.match(
                    r"^\s*([\U0001F000-\U0001FFFF\u2600-\u27BF"
                    r"\U00002B00-\U00002BFF\u203C-\u2049\ufe0f]+)\s*",
                    raw)
                if em:
                    return "", str(em.group(1)).strip()
            except Exception:
                pass
    except Exception:
        pass
    # 🆕 v161.20: products with NO emoji anywhere (name or supplier) still get a
    # sensible auto-emoji on their Buy-Now button so EVERY product shows
    # "{emoji} First Two Words Buy Now" consistently (user requirement).
    try:
        from database import get_connection as _gc2
        _c2 = _gc2().cursor()
        _c2.execute("SELECT name FROM products WHERE id=?", (int(pid),))
        _row2 = _c2.fetchone()
        if _row2:
            _nm = str(_row2["name"] or "").lower()
            for _kw, _em in _AUTO_PRODUCT_EMOJI:
                if _kw in _nm:
                    return "", _em
        return "", _AUTO_FALLBACK_EMOJI
    except Exception:
        return "", _AUTO_FALLBACK_EMOJI


def _buy_now_label(pid, default_suffix="🛒 Buy Now") -> str:
    """Return the Buy Now button label.

    🆕 v96 FORMAT: "{leading_emoji} {first_2_words} Buy Now"
      - leading_emoji: extracted from product name start (both regular emoji
        AND premium <tg-emoji> markup; for premium the visible fallback char
        is used in the button text since Telegram premium emojis inside
        button labels are not supported by the API — the visible char is
        the best UX we can do).
      - first_2_words: first two whitespace-separated tokens from the
        emoji-stripped product name (title-cased for polish).

    Examples:
      "🎮 Chatgpt Plus icloud mail nw"  →  "🎮 Chatgpt Plus Buy Now"
      "[[HTML]]<tg-emoji emoji-id='5' >🎮</tg-emoji> Netflix Premium 1 Month"
                                        →  "🎮 Netflix Premium Buy Now"
      "Spotify"                          →  "Spotify Buy Now"
      "" or missing product              →  "🛒 Buy Now"

    Cleans [[HTML]]/<tg-emoji> markup + truncates to Telegram button
    soft cap (~60 chars).

    v96 change: `default_suffix` is now used as the trailing text only
    (no dash separator). Old callers passing "🛒 Buy Now" get a nicer,
    shorter, product-branded button. Legacy full-name behavior removed
    per user request (2026-07-20).
    """
    import re as _re

    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT name FROM products WHERE id=?", (int(pid),))
        row = c.fetchone(); conn.close()
        if not row:
            return default_suffix
        raw = (row["name"] or "").strip()
    except Exception:
        return default_suffix

    if not raw:
        return default_suffix

    # ── Step 1: Extract leading emoji (regular OR premium fallback char) ──
    leading_emoji = ""
    body = raw

    # 🐛 v147 FIX (Bug6): supplier-linked products use their FIXED emoji from
    # ext_products; own products use the emoji in the name.
    try:
        _eid, _ech = _product_buy_emoji(int(pid))
        if _ech:
            leading_emoji = _ech
            # strip the fixed emoji prefix from the body so it isn't repeated
            if body.startswith(_ech):
                body = body[len(_ech):].lstrip()
    except Exception:
        pass

    # Case A: [[HTML]]<tg-emoji emoji-id="X">EMOJI</tg-emoji> rest...
    if body.startswith("[[HTML]]"):
        body = body[len("[[HTML]]"):]
    tg_match = _re.match(
        r"^\s*<tg-emoji\s+emoji-id=[\"'][^\"']+[\"']\s*>([^<]{1,8})</tg-emoji>\s*",
        body
    )
    if tg_match:
        leading_emoji = tg_match.group(1).strip()
        body = body[tg_match.end():]

    # Case B: leading regular emoji chars (unicode symbols/pictographs)
    if not leading_emoji:
        # Match any leading emoji-ish characters (broad unicode range)
        emo_match = _re.match(
            r"^\s*([\U0001F000-\U0001FFFF\u2600-\u27BF\U00002B00-\U00002BFF"
            r"\U0001F300-\U0001F9FF\u2700-\u27BF\u203C-\u2049\ufe0f]+)\s*",
            body
        )
        if emo_match:
            leading_emoji = emo_match.group(1).strip()
            body = body[emo_match.end():]

    # ── Step 2: Strip any residual HTML tags from body ──
    body = _re.sub(r"<[^>]+>", "", body).strip()

    # Fallback: also try name_for_button as safety net if body empty
    if not body:
        try:
            from utils import name_for_button
            body = (name_for_button(raw) or "").strip()
        except Exception:
            pass

    # ── Step 3: Take first 2 words (skip lone emoji-only bodies) ──
    words = body.split()
    # Guard: if body is only the same emoji we already extracted, drop it
    if len(words) == 1 and leading_emoji and words[0] == leading_emoji:
        words = []
    if len(words) >= 2:
        first2 = f"{words[0]} {words[1]}"
    elif len(words) == 1:
        first2 = words[0]
    else:
        first2 = ""

    # Title-case for polish (only if word is all-lower or all-upper for safety)
    def _polish(w):
        return w.title() if (w.islower() or w.isupper()) else w
    if first2:
        first2 = " ".join(_polish(w) for w in first2.split())

    # ── Step 4: Trailing suffix — strip cart emoji from default so we don't
    #           get "🛒 Buy Now" when user already has a product emoji.
    trail = default_suffix
    if leading_emoji:
        # Remove the 🛒 (or any leading cart-like emoji) from default suffix
        trail = _re.sub(r"^\s*[🛒🛍️🛍💰]+\s*", "", trail).strip() or "Buy Now"

    # ── Step 5: Assemble ──
    parts = []
    if leading_emoji:
        parts.append(leading_emoji)
    if first2:
        parts.append(first2)
    if trail:
        parts.append(trail)
    label = " ".join(parts).strip()

    if not label:
        return default_suffix

    # ── Step 6: Truncate to Telegram button soft cap (~60 chars) ──
    MAX = 60
    if len(label) > MAX:
        label = label[:MAX - 1].rstrip() + "…"
    return label


def _get_broadcast_global_color(tpl_id: str = None) -> str:
    """🆕 v94: return the color to apply on a broadcast button.

    Priority:
      1. Per-template color   (btn_style_<tpl_id> — set via Edit Templates)
      2. Global broadcast color (broadcast_btn_color — new v94 setting)
      3. 🆕 v96 default: "success" (green) — per user spec that Buy Now
         button should always render green for broadcast messages unless
         admin explicitly changes it.
    """
    try:
        from button_system import VALID_BUTTON_STYLES
        from database import get_setting
        if tpl_id:
            c = (get_setting(f"btn_style_{tpl_id}", "") or "").strip().lower()
            if c in VALID_BUTTON_STYLES:
                return c
        c = (get_setting("broadcast_btn_color", "") or "").strip().lower()
        if c in VALID_BUTTON_STYLES:
            return c
        # v96: green fallback when nothing else is set
        if "success" in VALID_BUTTON_STYLES:
            return "success"
    except Exception:
        pass
    return ""


def set_broadcast_global_color(color: str):
    """🆕 v94: persist the global broadcast button color."""
    try:
        from button_system import VALID_BUTTON_STYLES
        from database import set_setting
        c = (color or "").strip().lower()
        if c not in VALID_BUTTON_STYLES:
            c = ""
        set_setting("broadcast_btn_color", c)
    except Exception:
        pass


async def _buy_now_keyboard(bot, pid, btn_key="sb_buy_generic"):
    """🛒 Buy Now button.
    - For the bot's private chat: a normal callback (buy_<pid>).
    - For groups/channels: a deep link to the bot (since callbacks don't work there).
    Returns (private_kb, group_kb).

    🆕 v43: Per-template button text editor + premium-emoji icon support
    (Bot API 9.4 / PTB 22.7+). Map old btn_keys → template ids used by
    the new editor so admin's changes inside Edit Templates apply here too.

    🆕 v94: Button label is now "{product_name} - Buy Now" (product prefix).
    Also applies global/per-template color via _get_broadcast_global_color().

    🆕 v102 FIX: extract the PRODUCT's own <tg-emoji emoji-id="..."> premium
    markup from the product's name (if any) and attach it as
    icon_custom_emoji_id on the button. Previously only the regular emoji
    fallback char was shown → premium emoji got demoted to a plain unicode
    char. Now the actual premium emoji renders as the button icon.
    """
    _key_to_tpl = {
        "sb_buy_flash":   "sb_flash",
        "sb_buy_newprod": "sb_newprod",
        "sb_buy_generic": "sb_generic",
    }
    tpl_id = _key_to_tpl.get(btn_key, "sb_generic")

    # 🆕 v94: build product-prefixed label
    prefixed = _buy_now_label(pid, "🛒 Buy Now")
    color = _get_broadcast_global_color(tpl_id)

    # 🆕 v102 / 🐛 v147 FIX (Bug6): extract the product's premium emoji_id —
    # supplier-linked products use the FIXED emoji from ext_products, own
    # products use the emoji in the NAME — and render it as the button icon.
    product_emoji_id = ""
    try:
        _eid, _ = _product_buy_emoji(int(pid))
        if _eid:
            product_emoji_id = str(_eid)
            # Also strip the leading fallback char from the label if we
            # already put one there — otherwise emoji appears twice.
            # _buy_now_label(v96) returns "[emoji] first_2_words Buy Now"
            # so drop the leading emoji token when we're going to render
            # a proper premium icon.
            import re as _re
            # Match the first "word" (emoji cluster) and strip it if it's
            # a lone emoji-like character followed by space
            _stripped = _re.sub(
                r"^\s*[\U0001F000-\U0001FFFF\u2600-\u27BF"
                r"\U00002B00-\U00002BFF\U0001F300-\U0001F9FF"
                r"\u2700-\u27BF\u203C-\u2049\ufe0f]+\s+", "", prefixed
            )
            if _stripped and _stripped != prefixed:
                prefixed = _stripped
    except Exception:
        pass

    def _apply_color_and_icon(btn):
        """Attach both color and premium emoji icon via api_kwargs."""
        extras = {}
        if color:
            extras["style"] = color
        if product_emoji_id:
            extras["icon_custom_emoji_id"] = product_emoji_id
        if not extras:
            return btn
        try:
            return InlineKeyboardButton(
                btn.text,
                callback_data=getattr(btn, "callback_data", None),
                url=getattr(btn, "url", None),
                api_kwargs=extras,
            )
        except Exception:
            return btn

    try:
        from button_system import build_button as _bb
        private_btn = _apply_color_and_icon(_bb(tpl_id, prefixed, callback_data=f"buy_{pid}", force_default=True))
    except Exception:
        private_btn = _apply_color_and_icon(InlineKeyboardButton(prefixed, callback_data=f"buy_{pid}"))
    private_kb = InlineKeyboardMarkup([[private_btn]])

    try:
        me = await bot.get_me()
        username = me.username
    except Exception:
        username = None
    if username:
        deep = f"https://t.me/{username}?start=buy_{pid}"
        try:
            from button_system import build_button as _bb2
            group_btn = _apply_color_and_icon(_bb2(tpl_id, prefixed, url=deep, force_default=True))
        except Exception:
            group_btn = _apply_color_and_icon(InlineKeyboardButton(prefixed, url=deep))
        group_kb = InlineKeyboardMarkup([[group_btn]])
    else:
        group_kb = private_kb
    return private_kb, group_kb


# ════════════════════════════════════════════════════════════════
# 📤 DESTINATION-AWARE BROADCAST
# ════════════════════════════════════════════════════════════════

async def _alert_broadcast_dest_failure(bot, dest_ref, chat_id, err, cooldown_min=20):
    """🔧 v132: throttled admin alert when a broadcast cannot reach the
    destination group/channel — so dead destinations are VISIBLE."""
    import time as _t
    try:
        from database import get_setting, set_setting
        key = f"bcast_dest_alerted_{chat_id}"
        last = 0.0
        try:
            last = float(get_setting(key, "0") or 0)
        except Exception:
            last = 0.0
        now = _t.time()
        if now - last < cooldown_min * 60:
            return
        set_setting(key, f"{now}")
        from config import ADMIN_ID
        if not ADMIN_ID:
            return
        msg = (
            "🚨 *Broadcast destination FAILED*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Dest: `{dest_ref}` (chat `{chat_id}`)\n"
            f"Error: `{type(err).__name__}: {str(err)[:160]}`\n\n"
            f"_Fix: make sure the bot is an ADMIN in the group/channel, and "
            f"that dest_chat_id is correct (Settings → Fake Activity)._\n\n"
            f"_Real + fake broadcasts to this destination are being skipped._"
        )
        await bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
    except Exception:
        pass


async def broadcast_store_message(bot, text, pid=None, btn_key=None, tpl_id=None, bypass_maintenance=False, reply_markup=None):
    """Send `text` to the destination configured for fake activity:
       bot_only  → all bot users (DM)
       group_only→ the configured group/channel
       both      → users + group
    A 🛒 Buy Now button is attached when `pid` is given.

    🆕 v44: Pass `tpl_id` (e.g. "bc_purchase", "bc_discount", "sb_flash")
    to attach the EXACT per-template button (with admin-customized text
    and premium-emoji icon, if any). When tpl_id is None we fall back to
    auto-detecting btn_key from text content (legacy behaviour).

    🆕 v60: SKIP broadcast entirely if the referenced product is hidden,
    deleted, or out-of-stock — this prevents users from tapping a broadcast
    button and finding the product missing/unavailable (which would expose
    the bot's fake-activity system as obviously fake).

    Returns number of successful sends (0 if broadcast was skipped).
    """
    # 🐛 v170.26 FIX: empty/blank text guard — "Message text is empty" API
    # error + destination-failed admin alert spam rokne ke liye.
    if not text or not str(text).strip():
        logger.info("[broadcast_store_message] SKIPPED — empty text")
        return 0
    # 🆕 v96: maintenance mode gate — nothing goes out during maintenance
    try:
        from maintenance_mode import is_maintenance_on
        if is_maintenance_on() and not bypass_maintenance:
            logger.info(f"[broadcast_store_message] SKIPPED — maintenance ON")
            return 0
    except Exception:
        pass

    # 🆕 v60: Pre-flight check — abort broadcast if product is not buyable
    if pid is not None:
        if not _is_product_broadcastable(pid):
            logger.info(f"[broadcast_store_message] SKIPPED pid={pid} — product hidden/deleted/out-of-stock")
            return 0

    mode = _g("dest_mode", "bot_only")

    # 🆕 v96: bot-self self-protection for dest_chat (extra safety on top of
    # the save-time validation added in v95)
    try:
        _dest_chat = _g("dest_chat_id", "").strip()
        if _dest_chat and mode in ("group_only", "both"):
            me = await bot.get_me()
            own = f"@{(me.username or '').lower()}"
            if _dest_chat.lower() in (own, own.lstrip("@")):
                logger.warning(f"[broadcast_store_message] dest_chat is bot's own username — group send disabled")
                mode = "bot_only" if mode == "both" else "bot_only"
    except Exception:
        pass

    sent = 0

    private_kb = group_kb = reply_markup
    if pid is not None:
        # Priority 1: explicit tpl_id (NEW v44 — used by Edit Templates → Test)
        if tpl_id:
            try:
                from button_system import build_button as _bb
                # 🆕 v49: also apply size/align/pad styler + background color
                # so per-product fc_btn_<pid> customizations render fully.
                try:
                    from button_system import wrap_button as _wrap_style
                except Exception:
                    _wrap_style = lambda k, b: b  # noqa: E731
                # 🆕 v94: color resolution now respects global broadcast color
                # as a fallback (was per-template-only). Priority: per-template
                # > global broadcast > none.
                _color = _get_broadcast_global_color(tpl_id)

                # 🆕 v94: label now has product name prefix — "{product} - Buy Now"
                _btn_label = _buy_now_label(pid, "🛒 Buy Now")

                # 🆕 v102 / 🐛 v147 FIX (Bug6): pull the product's premium
                # emoji_id (supplier → fixed ext emoji; own → name emoji) and
                # strip the leading emoji fallback from the label so the
                # premium icon renders correctly.
                _product_emoji_id = ""
                try:
                    _eid, _ = _product_buy_emoji(int(pid))
                    if _eid:
                        _product_emoji_id = str(_eid)
                        import re as _re_local
                        _stripped = _re_local.sub(
                            r"^\s*[\U0001F000-\U0001FFFF\u2600-\u27BF"
                            r"\U00002B00-\U00002BFF\U0001F300-\U0001F9FF"
                            r"\u2700-\u27BF\u203C-\u2049\ufe0f]+\s+", "",
                            _btn_label
                        )
                        if _stripped and _stripped != _btn_label:
                            _btn_label = _stripped
                except Exception:
                    pass

                def _decorate(btn, key):
                    # Apply visual width/align/pad
                    try:
                        btn = _wrap_style(key, btn)
                    except Exception:
                        pass
                    # Combine color + premium emoji icon into a single api_kwargs
                    _extras = {}
                    if _color:
                        _extras["style"] = _color
                    if _product_emoji_id:
                        _extras["icon_custom_emoji_id"] = _product_emoji_id
                    if _extras:
                        try:
                            btn = InlineKeyboardButton(
                                btn.text,
                                callback_data=getattr(btn, "callback_data", None),
                                url=getattr(btn, "url", None),
                                api_kwargs=_extras,
                            )
                        except Exception:
                            pass
                    return btn

                private_btn = _decorate(
                    _bb(tpl_id, _btn_label, callback_data=f"buy_{pid}", force_default=True),
                    tpl_id)
                try:
                    me = await bot.get_me(); _u = me.username
                except Exception:
                    _u = None
                if _u:
                    deep = f"https://t.me/{_u}?start=buy_{pid}"
                    group_btn = _decorate(
                        _bb(tpl_id, _btn_label, url=deep, force_default=True),
                        tpl_id)
                    private_kb = InlineKeyboardMarkup([[private_btn]])
                    group_kb   = InlineKeyboardMarkup([[group_btn]])
                else:
                    private_kb = InlineKeyboardMarkup([[private_btn]])
                    group_kb   = private_kb
            except Exception as _e:
                # Fallback to legacy path below
                tpl_id = None

        if not tpl_id:
            # Priority 2: explicit btn_key (legacy)
            _bk = btn_key
            if not _bk:
                # Priority 3: auto-detect from text content
                tl = (text or "").lower()
                if "flash" in tl or "⚡" in (text or ""):
                    _bk = "sb_buy_flash"
                elif "new product" in tl or "🆕" in (text or ""):
                    _bk = "sb_buy_newprod"
                else:
                    _bk = "sb_buy_generic"
            private_kb, group_kb = await _buy_now_keyboard(bot, pid, btn_key=_bk)

    # 🆕 Premium/custom emoji aware everywhere (even if [[HTML]] appears in the middle)
    _text, _pm = smart_text_and_mode(text, "Markdown")

    async def _send(chat_id, kb, is_group=False):
        try:
            await bot.send_message(chat_id=chat_id, text=_text, parse_mode=_pm, reply_markup=kb)
            return True
        except Exception:
            # Parse-mode fallback → plain text
            try:
                await bot.send_message(chat_id=chat_id, text=_text, reply_markup=kb)
                return True
            except Exception as _e:
                # 🔧 v132: NEVER silent — log + alert the admin (throttled) so a
                # dead destination is visible, not invisible. This was why real
                # purchase/join/stock broadcasts silently stopped reaching the group.
                logger.warning(f"[StoreBroadcast] send failed chat={chat_id}: {type(_e).__name__}: {str(_e)[:150]}")
                try:
                    if is_group:
                        await _alert_broadcast_dest_failure(bot, dest_chat_ref, chat_id, _e)
                except Exception:
                    pass
                return False

    # ── Bot users ──
    if mode in ("bot_only", "both"):
        try:
            from database import get_all_users_for_broadcast
            users = get_all_users_for_broadcast()
            user_ids = [u["user_id"] for u in users]
        except Exception:
            user_ids = []
        # 🆕 v168: BATCH sending for 10x speed (15 concurrent sends per batch)
        _BATCH = 15
        for _i in range(0, len(user_ids), _BATCH):
            _batch_ids = user_ids[_i:_i + _BATCH]
            _results = await asyncio.gather(
                *[_send(uid, private_kb) for uid in _batch_ids],
                return_exceptions=True
            )
            for _r in _results:
                if _r is True:
                    sent += 1
            await asyncio.sleep(0.1)

    # ── Group / channel ──
    if mode in ("group_only", "both"):
        dest_chat = _g("dest_chat_id", "").strip()
        dest_chat_ref = dest_chat
        if dest_chat:
            try:
                from ui_extras import _resolve_chat_id
                resolved = await _resolve_chat_id(bot, dest_chat)
            except Exception:
                resolved = dest_chat
            if await _send(resolved, group_kb, is_group=True):
                sent += 1

    logger.info(f"[StoreBroadcast] Sent to {sent} destinations (mode={mode}, pid={pid})")
    return sent



# ════════════════════════════════════════════════════════════
# 🔧 v132 — BROADCAST DESTINATION SELF-TEST (admin panel)
# ════════════════════════════════════════════════════════════

async def admin_bcast_test_callback(u, c):
    """Test: can the bot post to the fake-activity destination group/channel?
    Checks bot's member status, resolves dest, sends a test message, and
    reports the exact result to the admin.
    🐛 v139 FIX: ADMIN_ID was used without import → NameError on tap."""
    from config import ADMIN_ID
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Testing destination…")
    from database import get_setting
    dest = get_setting("dest_chat_id", "").strip()
    mode = get_setting("dest_mode", "bot_only")
    lines = ["🛰️ *Broadcast Destination Test*\n━━━━━━━━━━━━━━━━━━━━",
             f"Dest: `{dest or '—'}`", f"Mode: `{mode}`", ""]
    if not dest:
        lines.append("❌ No destination set. Set dest_chat_id in Fake Activity settings.")
        await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_fake_activity")]]))
        return
    try:
        from ui_extras import _resolve_chat_id
        resolved = await _resolve_chat_id(c.bot, dest)
        lines.append(f"✅ Resolved → `{resolved}`")
    except Exception as e:
        lines.append(f"❌ Resolve failed: `{str(e)[:120]}`")
        lines.append("_Check dest_chat_id — the bot must be a member._")
        await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_fake_activity")]]))
        return
    # Check bot's member status in the group
    try:
        me = await c.bot.get_me()
        mem = await c.bot.get_chat_member(chat_id=resolved, user_id=me.id)
        status = getattr(mem, "status", "?")
        lines.append(f"🤖 Bot status in chat: `{status}`")
        if status in ("administrator", "creator", "member"):
            lines.append("✅ Bot can post (member/admin)")
        else:
            lines.append(f"⚠️ Bot status `{status}` — may NOT be able to post. Make the bot an ADMIN.")
    except Exception as e:
        lines.append(f"⚠️ Could not check membership: `{str(e)[:100]}`")
    # Send a test message
    try:
        await c.bot.send_message(chat_id=resolved,
                                 text="✅ *Broadcast test OK*\nThe bot can post to this destination.",
                                 parse_mode="Markdown")
        lines.append("\n✅ *Test message sent successfully!*")
    except Exception as e:
        lines.append(f"\n❌ *Test send FAILED:* `{str(e)[:160]}`")
        lines.append("_Fix: add the bot as ADMIN in the group/channel._")
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_fake_activity")]]))

# 🆕 v94: Buy Now button — product-name prefix + global color
# ─────────────────────────────────────────────────────────────
def _product_buy_emoji(pid):
    """🐛 v147 FIX (Bug6): return (emoji_id, emoji_char) for a product's
    Buy-Now button.

    Priority:
      1. SUPPLIER-LINKED products → the FIXED premium emoji the admin set in
         the supplier emoji library (`ext_products.emoji_id` / `emoji_char`).
         Supplier raw names carry no emoji; this fixed emoji is the source of
         truth the owner wants on the button.
      2. OWN (manual) products → the premium emoji inside the product NAME
         (the owner types it directly in the name, e.g.
         `[[HTML]]<tg-emoji ...>🎨</tg-emoji>Canva 500 User Panel`).
    Returns ("", "") when nothing is found.
    """
    try:
        from database import get_connection
        c = get_connection().cursor()
        # 1) supplier-linked → fixed emoji from ext_products
        c.execute(
            "SELECT e.emoji_id, e.emoji_char FROM ext_products e "
            "WHERE e.shop_product_id=? AND e.emoji_id IS NOT NULL AND e.emoji_id!='' "
            "LIMIT 1", (int(pid),))
        row = c.fetchone()
        if row:
            eid = str(row[0] or "").strip()
            ech = str(row[1] or "").strip()
            if eid or ech:
                return eid, ech
        # 2) own product → premium emoji from the NAME
        c.execute("SELECT name FROM products WHERE id=?", (int(pid),))
        row = c.fetchone()
        if row:
            try:
                import re as _re
                raw = str(row["name"] or "")
                # 🐛 v161.20 FIX: extract_emoji_from_html() returns (eid,
                # REST_TEXT_WITHOUT_EMOJI) — the old code used that rest text as
                # the emoji char → button labels like "Canva 500 User Panel Buy
                # Now" instead of "🎨 Canva 500 Buy Now". Grab the FALLBACK char
                # that lives INSIDE the <tg-emoji> tag instead.
                m = _re.search(
                    r'<tg-emoji\s+emoji-id=["\'](\d+)["\']\s*>\s*([^<]{1,8})\s*</tg-emoji>',
                    raw, flags=_re.I)
                if m:
                    return str(m.group(1)), str(m.group(2)).strip()
                # legacy: no <tg-emoji> tag → leading regular emoji chars
                em = _re.match(
                    r"^\s*([\U0001F000-\U0001FFFF\u2600-\u27BF"
                    r"\U00002B00-\U00002BFF\u203C-\u2049\ufe0f]+)\s*",
                    raw)
                if em:
                    return "", str(em.group(1)).strip()
            except Exception:
                pass
    except Exception:
        pass
    # 🆕 v161.20: products with NO emoji anywhere (name or supplier) still get a
    # sensible auto-emoji on their Buy-Now button so EVERY product shows
    # "{emoji} First Two Words Buy Now" consistently (user requirement).
    try:
        from database import get_connection as _gc2
        _c2 = _gc2().cursor()
        _c2.execute("SELECT name FROM products WHERE id=?", (int(pid),))
        _row2 = _c2.fetchone()
        if _row2:
            _nm = str(_row2["name"] or "").lower()
            for _kw, _em in _AUTO_PRODUCT_EMOJI:
                if _kw in _nm:
                    return "", _em
        return "", _AUTO_FALLBACK_EMOJI
    except Exception:
        return "", _AUTO_FALLBACK_EMOJI


def _buy_now_label(pid, default_suffix="🛒 Buy Now") -> str:
    """Return the Buy Now button label.

    🆕 v96 FORMAT: "{leading_emoji} {first_2_words} Buy Now"
      - leading_emoji: extracted from product name start (both regular emoji
        AND premium <tg-emoji> markup; for premium the visible fallback char
        is used in the button text since Telegram premium emojis inside
        button labels are not supported by the API — the visible char is
        the best UX we can do).
      - first_2_words: first two whitespace-separated tokens from the
        emoji-stripped product name (title-cased for polish).

    Examples:
      "🎮 Chatgpt Plus icloud mail nw"  →  "🎮 Chatgpt Plus Buy Now"
      "[[HTML]]<tg-emoji emoji-id='5' >🎮</tg-emoji> Netflix Premium 1 Month"
                                        →  "🎮 Netflix Premium Buy Now"
      "Spotify"                          →  "Spotify Buy Now"
      "" or missing product              →  "🛒 Buy Now"

    Cleans [[HTML]]/<tg-emoji> markup + truncates to Telegram button
    soft cap (~60 chars).

    v96 change: `default_suffix` is now used as the trailing text only
    (no dash separator). Old callers passing "🛒 Buy Now" get a nicer,
    shorter, product-branded button. Legacy full-name behavior removed
    per user request (2026-07-20).
    """
    import re as _re

    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT name FROM products WHERE id=?", (int(pid),))
        row = c.fetchone(); conn.close()
        if not row:
            return default_suffix
        raw = (row["name"] or "").strip()
    except Exception:
        return default_suffix

    if not raw:
        return default_suffix

    # ── Step 1: Extract leading emoji (regular OR premium fallback char) ──
    leading_emoji = ""
    body = raw

    # 🐛 v147 FIX (Bug6): supplier-linked products use their FIXED emoji from
    # ext_products; own products use the emoji in the name.
    try:
        _eid, _ech = _product_buy_emoji(int(pid))
        if _ech:
            leading_emoji = _ech
            # strip the fixed emoji prefix from the body so it isn't repeated
            if body.startswith(_ech):
                body = body[len(_ech):].lstrip()
    except Exception:
        pass

    # Case A: [[HTML]]<tg-emoji emoji-id="X">EMOJI</tg-emoji> rest...
    if body.startswith("[[HTML]]"):
        body = body[len("[[HTML]]"):]
    tg_match = _re.match(
        r"^\s*<tg-emoji\s+emoji-id=[\"'][^\"']+[\"']\s*>([^<]{1,8})</tg-emoji>\s*",
        body
    )
    if tg_match:
        leading_emoji = tg_match.group(1).strip()
        body = body[tg_match.end():]

    # Case B: leading regular emoji chars (unicode symbols/pictographs)
    if not leading_emoji:
        # Match any leading emoji-ish characters (broad unicode range)
        emo_match = _re.match(
            r"^\s*([\U0001F000-\U0001FFFF\u2600-\u27BF\U00002B00-\U00002BFF"
            r"\U0001F300-\U0001F9FF\u2700-\u27BF\u203C-\u2049\ufe0f]+)\s*",
            body
        )
        if emo_match:
            leading_emoji = emo_match.group(1).strip()
            body = body[emo_match.end():]

    # ── Step 2: Strip any residual HTML tags from body ──
    body = _re.sub(r"<[^>]+>", "", body).strip()

    # Fallback: also try name_for_button as safety net if body empty
    if not body:
        try:
            from utils import name_for_button
            body = (name_for_button(raw) or "").strip()
        except Exception:
            pass

    # ── Step 3: Take first 2 words (skip lone emoji-only bodies) ──
    words = body.split()
    # Guard: if body is only the same emoji we already extracted, drop it
    if len(words) == 1 and leading_emoji and words[0] == leading_emoji:
        words = []
    if len(words) >= 2:
        first2 = f"{words[0]} {words[1]}"
    elif len(words) == 1:
        first2 = words[0]
    else:
        first2 = ""

    # Title-case for polish (only if word is all-lower or all-upper for safety)
    def _polish(w):
        return w.title() if (w.islower() or w.isupper()) else w
    if first2:
        first2 = " ".join(_polish(w) for w in first2.split())

    # ── Step 4: Trailing suffix — strip cart emoji from default so we don't
    #           get "🛒 Buy Now" when user already has a product emoji.
    trail = default_suffix
    if leading_emoji:
        # Remove the 🛒 (or any leading cart-like emoji) from default suffix
        trail = _re.sub(r"^\s*[🛒🛍️🛍💰]+\s*", "", trail).strip() or "Buy Now"

    # ── Step 5: Assemble ──
    parts = []
    if leading_emoji:
        parts.append(leading_emoji)
    if first2:
        parts.append(first2)
    if trail:
        parts.append(trail)
    label = " ".join(parts).strip()

    if not label:
        return default_suffix

    # ── Step 6: Truncate to Telegram button soft cap (~60 chars) ──
    MAX = 60
    if len(label) > MAX:
        label = label[:MAX - 1].rstrip() + "…"
    return label


def _get_broadcast_global_color(tpl_id: str = None) -> str:
    """🆕 v94: return the color to apply on a broadcast button.

    Priority:
      1. Per-template color   (btn_style_<tpl_id> — set via Edit Templates)
      2. Global broadcast color (broadcast_btn_color — new v94 setting)
      3. 🆕 v96 default: "success" (green) — per user spec that Buy Now
         button should always render green for broadcast messages unless
         admin explicitly changes it.
    """
    try:
        from button_system import VALID_BUTTON_STYLES
        from database import get_setting
        if tpl_id:
            c = (get_setting(f"btn_style_{tpl_id}", "") or "").strip().lower()
            if c in VALID_BUTTON_STYLES:
                return c
        c = (get_setting("broadcast_btn_color", "") or "").strip().lower()
        if c in VALID_BUTTON_STYLES:
            return c
        # v96: green fallback when nothing else is set
        if "success" in VALID_BUTTON_STYLES:
            return "success"
    except Exception:
        pass
    return ""


def set_broadcast_global_color(color: str):
    """🆕 v94: persist the global broadcast button color."""
    try:
        from button_system import VALID_BUTTON_STYLES
        from database import set_setting
        c = (color or "").strip().lower()
        if c not in VALID_BUTTON_STYLES:
            c = ""
        set_setting("broadcast_btn_color", c)
    except Exception:
        pass


async def _buy_now_keyboard(bot, pid, btn_key="sb_buy_generic"):
    """🛒 Buy Now button.
    - For the bot's private chat: a normal callback (buy_<pid>).
    - For groups/channels: a deep link to the bot (since callbacks don't work there).
    Returns (private_kb, group_kb).

    🆕 v43: Per-template button text editor + premium-emoji icon support
    (Bot API 9.4 / PTB 22.7+). Map old btn_keys → template ids used by
    the new editor so admin's changes inside Edit Templates apply here too.

    🆕 v94: Button label is now "{product_name} - Buy Now" (product prefix).
    Also applies global/per-template color via _get_broadcast_global_color().

    🆕 v102 FIX: extract the PRODUCT's own <tg-emoji emoji-id="..."> premium
    markup from the product's name (if any) and attach it as
    icon_custom_emoji_id on the button. Previously only the regular emoji
    fallback char was shown → premium emoji got demoted to a plain unicode
    char. Now the actual premium emoji renders as the button icon.
    """
    _key_to_tpl = {
        "sb_buy_flash":   "sb_flash",
        "sb_buy_newprod": "sb_newprod",
        "sb_buy_generic": "sb_generic",
    }
    tpl_id = _key_to_tpl.get(btn_key, "sb_generic")

    # 🆕 v94: build product-prefixed label
    prefixed = _buy_now_label(pid, "🛒 Buy Now")
    color = _get_broadcast_global_color(tpl_id)

    # 🆕 v102 / 🐛 v147 FIX (Bug6): extract the product's premium emoji_id —
    # supplier-linked products use the FIXED emoji from ext_products, own
    # products use the emoji in the NAME — and render it as the button icon.
    product_emoji_id = ""
    try:
        _eid, _ = _product_buy_emoji(int(pid))
        if _eid:
            product_emoji_id = str(_eid)
            # Also strip the leading fallback char from the label if we
            # already put one there — otherwise emoji appears twice.
            # _buy_now_label(v96) returns "[emoji] first_2_words Buy Now"
            # so drop the leading emoji token when we're going to render
            # a proper premium icon.
            import re as _re
            # Match the first "word" (emoji cluster) and strip it if it's
            # a lone emoji-like character followed by space
            _stripped = _re.sub(
                r"^\s*[\U0001F000-\U0001FFFF\u2600-\u27BF"
                r"\U00002B00-\U00002BFF\U0001F300-\U0001F9FF"
                r"\u2700-\u27BF\u203C-\u2049\ufe0f]+\s+", "", prefixed
            )
            if _stripped and _stripped != prefixed:
                prefixed = _stripped
    except Exception:
        pass

    def _apply_color_and_icon(btn):
        """Attach both color and premium emoji icon via api_kwargs."""
        extras = {}
        if color:
            extras["style"] = color
        if product_emoji_id:
            extras["icon_custom_emoji_id"] = product_emoji_id
        if not extras:
            return btn
        try:
            return InlineKeyboardButton(
                btn.text,
                callback_data=getattr(btn, "callback_data", None),
                url=getattr(btn, "url", None),
                api_kwargs=extras,
            )
        except Exception:
            return btn

    try:
        from button_system import build_button as _bb
        private_btn = _apply_color_and_icon(_bb(tpl_id, prefixed, callback_data=f"buy_{pid}", force_default=True))
    except Exception:
        private_btn = _apply_color_and_icon(InlineKeyboardButton(prefixed, callback_data=f"buy_{pid}"))
    private_kb = InlineKeyboardMarkup([[private_btn]])

    try:
        me = await bot.get_me()
        username = me.username
    except Exception:
        username = None
    if username:
        deep = f"https://t.me/{username}?start=buy_{pid}"
        try:
            from button_system import build_button as _bb2
            group_btn = _apply_color_and_icon(_bb2(tpl_id, prefixed, url=deep, force_default=True))
        except Exception:
            group_btn = _apply_color_and_icon(InlineKeyboardButton(prefixed, url=deep))
        group_kb = InlineKeyboardMarkup([[group_btn]])
    else:
        group_kb = private_kb
    return private_kb, group_kb


# ════════════════════════════════════════════════════════════════
# 📤 DESTINATION-AWARE BROADCAST
# ════════════════════════════════════════════════════════════════

async def _alert_broadcast_dest_failure(bot, dest_ref, chat_id, err, cooldown_min=20):
    """🔧 v132: throttled admin alert when a broadcast cannot reach the
    destination group/channel — so dead destinations are VISIBLE."""
    import time as _t
    try:
        from database import get_setting, set_setting
        key = f"bcast_dest_alerted_{chat_id}"
        last = 0.0
        try:
            last = float(get_setting(key, "0") or 0)
        except Exception:
            last = 0.0
        now = _t.time()
        if now - last < cooldown_min * 60:
            return
        set_setting(key, f"{now}")
        from config import ADMIN_ID
        if not ADMIN_ID:
            return
        msg = (
            "🚨 *Broadcast destination FAILED*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Dest: `{dest_ref}` (chat `{chat_id}`)\n"
            f"Error: `{type(err).__name__}: {str(err)[:160]}`\n\n"
            f"_Fix: make sure the bot is an ADMIN in the group/channel, and "
            f"that dest_chat_id is correct (Settings → Fake Activity)._\n\n"
            f"_Real + fake broadcasts to this destination are being skipped._"
        )
        await bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
    except Exception:
        pass


async def broadcast_store_message(bot, text, pid=None, btn_key=None, tpl_id=None, bypass_maintenance=False, reply_markup=None):
    """Send `text` to the destination configured for fake activity:
       bot_only  → all bot users (DM)
       group_only→ the configured group/channel
       both      → users + group
    A 🛒 Buy Now button is attached when `pid` is given.

    🆕 v44: Pass `tpl_id` (e.g. "bc_purchase", "bc_discount", "sb_flash")
    to attach the EXACT per-template button (with admin-customized text
    and premium-emoji icon, if any). When tpl_id is None we fall back to
    auto-detecting btn_key from text content (legacy behaviour).

    🆕 v60: SKIP broadcast entirely if the referenced product is hidden,
    deleted, or out-of-stock — this prevents users from tapping a broadcast
    button and finding the product missing/unavailable (which would expose
    the bot's fake-activity system as obviously fake).

    Returns number of successful sends (0 if broadcast was skipped).
    """
    # 🐛 v170.26 FIX: empty/blank text guard — "Message text is empty" API
    # error + destination-failed admin alert spam rokne ke liye.
    if not text or not str(text).strip():
        logger.info("[broadcast_store_message] SKIPPED — empty text")
        return 0
    # 🆕 v96: maintenance mode gate — nothing goes out during maintenance
    try:
        from maintenance_mode import is_maintenance_on
        if is_maintenance_on() and not bypass_maintenance:
            logger.info(f"[broadcast_store_message] SKIPPED — maintenance ON")
            return 0
    except Exception:
        pass

    # 🆕 v60: Pre-flight check — abort broadcast if product is not buyable
    if pid is not None:
        if not _is_product_broadcastable(pid):
            logger.info(f"[broadcast_store_message] SKIPPED pid={pid} — product hidden/deleted/out-of-stock")
            return 0

    mode = _g("dest_mode", "bot_only")

    # 🆕 v96: bot-self self-protection for dest_chat (extra safety on top of
    # the save-time validation added in v95)
    try:
        _dest_chat = _g("dest_chat_id", "").strip()
        if _dest_chat and mode in ("group_only", "both"):
            me = await bot.get_me()
            own = f"@{(me.username or '').lower()}"
            if _dest_chat.lower() in (own, own.lstrip("@")):
                logger.warning(f"[broadcast_store_message] dest_chat is bot's own username — group send disabled")
                mode = "bot_only" if mode == "both" else "bot_only"
    except Exception:
        pass

    sent = 0

    private_kb = group_kb = reply_markup
    if pid is not None:
        # Priority 1: explicit tpl_id (NEW v44 — used by Edit Templates → Test)
        if tpl_id:
            try:
                from button_system import build_button as _bb
                # 🆕 v49: also apply size/align/pad styler + background color
                # so per-product fc_btn_<pid> customizations render fully.
                try:
                    from button_system import wrap_button as _wrap_style
                except Exception:
                    _wrap_style = lambda k, b: b  # noqa: E731
                # 🆕 v94: color resolution now respects global broadcast color
                # as a fallback (was per-template-only). Priority: per-template
                # > global broadcast > none.
                _color = _get_broadcast_global_color(tpl_id)

                # 🆕 v94: label now has product name prefix — "{product} - Buy Now"
                _btn_label = _buy_now_label(pid, "🛒 Buy Now")

                # 🆕 v102 / 🐛 v147 FIX (Bug6): pull the product's premium
                # emoji_id (supplier → fixed ext emoji; own → name emoji) and
                # strip the leading emoji fallback from the label so the
                # premium icon renders correctly.
                _product_emoji_id = ""
                try:
                    _eid, _ = _product_buy_emoji(int(pid))
                    if _eid:
                        _product_emoji_id = str(_eid)
                        import re as _re_local
                        _stripped = _re_local.sub(
                            r"^\s*[\U0001F000-\U0001FFFF\u2600-\u27BF"
                            r"\U00002B00-\U00002BFF\U0001F300-\U0001F9FF"
                            r"\u2700-\u27BF\u203C-\u2049\ufe0f]+\s+", "",
                            _btn_label
                        )
                        if _stripped and _stripped != _btn_label:
                            _btn_label = _stripped
                except Exception:
                    pass

                def _decorate(btn, key):
                    # Apply visual width/align/pad
                    try:
                        btn = _wrap_style(key, btn)
                    except Exception:
                        pass
                    # Combine color + premium emoji icon into a single api_kwargs
                    _extras = {}
                    if _color:
                        _extras["style"] = _color
                    if _product_emoji_id:
                        _extras["icon_custom_emoji_id"] = _product_emoji_id
                    if _extras:
                        try:
                            btn = InlineKeyboardButton(
                                btn.text,
                                callback_data=getattr(btn, "callback_data", None),
                                url=getattr(btn, "url", None),
                                api_kwargs=_extras,
                            )
                        except Exception:
                            pass
                    return btn

                private_btn = _decorate(
                    _bb(tpl_id, _btn_label, callback_data=f"buy_{pid}", force_default=True),
                    tpl_id)
                try:
                    me = await bot.get_me(); _u = me.username
                except Exception:
                    _u = None
                if _u:
                    deep = f"https://t.me/{_u}?start=buy_{pid}"
                    group_btn = _decorate(
                        _bb(tpl_id, _btn_label, url=deep, force_default=True),
                        tpl_id)
                    private_kb = InlineKeyboardMarkup([[private_btn]])
                    group_kb   = InlineKeyboardMarkup([[group_btn]])
                else:
                    private_kb = InlineKeyboardMarkup([[private_btn]])
                    group_kb   = private_kb
            except Exception as _e:
                # Fallback to legacy path below
                tpl_id = None

        if not tpl_id:
            # Priority 2: explicit btn_key (legacy)
            _bk = btn_key
            if not _bk:
                # Priority 3: auto-detect from text content
                tl = (text or "").lower()
                if "flash" in tl or "⚡" in (text or ""):
                    _bk = "sb_buy_flash"
                elif "new product" in tl or "🆕" in (text or ""):
                    _bk = "sb_buy_newprod"
                else:
                    _bk = "sb_buy_generic"
            private_kb, group_kb = await _buy_now_keyboard(bot, pid, btn_key=_bk)

    # 🆕 Premium/custom emoji aware everywhere (even if [[HTML]] appears in the middle)
    _text, _pm = smart_text_and_mode(text, "Markdown")

    async def _send(chat_id, kb, is_group=False):
        try:
            await bot.send_message(chat_id=chat_id, text=_text, parse_mode=_pm, reply_markup=kb)
            return True
        except Exception:
            # Parse-mode fallback → plain text
            try:
                await bot.send_message(chat_id=chat_id, text=_text, reply_markup=kb)
                return True
            except Exception as _e:
                # 🔧 v132: NEVER silent — log + alert the admin (throttled) so a
                # dead destination is visible, not invisible. This was why real
                # purchase/join/stock broadcasts silently stopped reaching the group.
                logger.warning(f"[StoreBroadcast] send failed chat={chat_id}: {type(_e).__name__}: {str(_e)[:150]}")
                try:
                    if is_group:
                        await _alert_broadcast_dest_failure(bot, dest_chat_ref, chat_id, _e)
                except Exception:
                    pass
                return False

    # ── Bot users ──
    if mode in ("bot_only", "both"):
        try:
            from database import get_all_users_for_broadcast
            users = get_all_users_for_broadcast()
            user_ids = [u["user_id"] for u in users]
        except Exception:
            user_ids = []
        # 🆕 v168: BATCH sending for 10x speed (15 concurrent sends per batch)
        _BATCH = 15
        for _i in range(0, len(user_ids), _BATCH):
            _batch_ids = user_ids[_i:_i + _BATCH]
            _results = await asyncio.gather(
                *[_send(uid, private_kb) for uid in _batch_ids],
                return_exceptions=True
            )
            for _r in _results:
                if _r is True:
                    sent += 1
            await asyncio.sleep(0.1)

    # ── Group / channel ──
    if mode in ("group_only", "both"):
        dest_chat = _g("dest_chat_id", "").strip()
        dest_chat_ref = dest_chat
        if dest_chat:
            try:
                from ui_extras import _resolve_chat_id
                resolved = await _resolve_chat_id(bot, dest_chat)
            except Exception:
                resolved = dest_chat
            if await _send(resolved, group_kb, is_group=True):
                sent += 1

    logger.info(f"[StoreBroadcast] Sent to {sent} destinations (mode={mode}, pid={pid})")
    return sent



# ════════════════════════════════════════════════════════════
# 🔧 v132 — BROADCAST DESTINATION SELF-TEST (admin panel)
# ════════════════════════════════════════════════════════════

async def admin_bcast_test_callback(u, c):
    """Test: can the bot post to the fake-activity destination group/channel?
    Checks bot's member status, resolves dest, sends a test message, and
    reports the exact result to the admin.
    🐛 v139 FIX: ADMIN_ID was used without import → NameError on tap."""
    from config import ADMIN_ID
    q = u.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Testing destination…")
    from database import get_setting
    dest = get_setting("dest_chat_id", "").strip()
    mode = get_setting("dest_mode", "bot_only")
    lines = ["🛰️ *Broadcast Destination Test*\n━━━━━━━━━━━━━━━━━━━━",
             f"Dest: `{dest or '—'}`", f"Mode: `{mode}`", ""]
    if not dest:
        lines.append("❌ No destination set. Set dest_chat_id in Fake Activity settings.")
        await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_fake_activity")]]))
        return
    try:
        from ui_extras import _resolve_chat_id
        resolved = await _resolve_chat_id(c.bot, dest)
        lines.append(f"✅ Resolved → `{resolved}`")
    except Exception as e:
        lines.append(f"❌ Resolve failed: `{str(e)[:120]}`")
        lines.append("_Check dest_chat_id — the bot must be a member._")
        await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_fake_activity")]]))
        return
    # Check bot's member status in the group
    try:
        me = await c.bot.get_me()
        mem = await c.bot.get_chat_member(chat_id=resolved, user_id=me.id)
        status = getattr(mem, "status", "?")
        lines.append(f"🤖 Bot status in chat: `{status}`")
        if status in ("administrator", "creator", "member"):
            lines.append("✅ Bot can post (member/admin)")
        else:
            lines.append(f"⚠️ Bot status `{status}` — may NOT be able to post. Make the bot an ADMIN.")
    except Exception as e:
        lines.append(f"⚠️ Could not check membership: `{str(e)[:100]}`")
    # Send a test message
    try:
        await c.bot.send_message(chat_id=resolved,
                                 text="✅ *Broadcast test OK*\nThe bot can post to this destination.",
                                 parse_mode="Markdown")
        lines.append("\n✅ *Test message sent successfully!*")
    except Exception as e:
        lines.append(f"\n❌ *Test send FAILED:* `{str(e)[:160]}`")
        lines.append("_Fix: add the bot as ADMIN in the group/channel._")
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_fake_activity")]]))
