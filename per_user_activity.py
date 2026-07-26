# ================================================================
# 🎭 PER-USER LIFETIME FAKE ACTIVITY SYSTEM
# ================================================================
# File: per_user_activity.py
#
# WHAT THIS DOES:
# ───────────────
# When any real user starts the bot for the first time (/start),
# this system launches a PERSONAL fake activity job for that user.
#
# That job runs FOREVER (lifetime) — sending that specific user
# fake purchase, deposit, referral, discount, review messages.
#
# Every user gets DIFFERENT messages at DIFFERENT times.
# No two users see the same sequence.
#
# HOW IT WORKS:
# ─────────────
#   1. User sends /start → start_personal_activity(bot, app, user_id) called
#   2. First message sent within 15 seconds (immediate wow effect)
#   3. After that, random interval 1–60 min between each message
#   4. Each message is picked randomly from all enabled types
#   5. Fake names are random Pakistani + Indian realistic names
#   6. Job stores itself in DB so it survives bot restarts
#   7. Admin can stop/start per user from Admin Panel
#
# ADMIN CONTROLS (Admin Panel → 🎭 Fake Activity):
# ──────────────────────────────────────────────────
#   ✅ Global ON/OFF switch
#   ✅ Per-user stop/start
#   ✅ Speed control (min/max interval)
#   ✅ Message type toggles
#   ✅ View which users have active jobs
#   ✅ View last message sent to each user
#
# DB TABLE: user_activity_jobs
#   user_id     — Telegram user ID
#   is_active   — 1 = running, 0 = stopped
#   last_sent   — timestamp of last message
#   msg_count   — total messages sent to this user
#   created_at  — when job was started
# ================================================================

import random
import logging
import asyncio
from datetime import datetime
from utils import smart_text_and_mode

logger = logging.getLogger(__name__)

# ── Fake Name Pools ──────────────────────────────────────────────
# Pakistani + Indian realistic first names (mix)

PAKISTANI_NAMES = [
    "Ahmed", "Ali", "Usman", "Hassan", "Bilal", "Zain", "Hamza",
    "Omer", "Faisal", "Asad", "Saad", "Waqar", "Farhan", "Imran",
    "Kamran", "Shahzaib", "Danyal", "Haris", "Muneeb", "Talha",
    "Waleed", "Junaid", "Arslan", "Shoaib", "Adnan", "Rizwan",
    "Ayesha", "Fatima", "Zara", "Hina", "Sara", "Maham", "Noor",
    "Iqra", "Sana", "Rabia", "Amna", "Areeba", "Kiran", "Maryam",
    "Laiba", "Nimra", "Rida", "Saba", "Zahra", "Zainab", "Alishba",
    "Bisma", "Dua", "Eman", "Kinza", "Madiha", "Sheeza", "Tayyaba",
]

INDIAN_NAMES = [
    "Rahul", "Arjun", "Rohan", "Vikram", "Aditya", "Kabir", "Aarav",
    "Priya", "Anjali", "Pooja", "Neha", "Riya", "Divya", "Kavya",
    "Amit", "Raj", "Suresh", "Manish", "Deepak", "Ravi", "Sanjay",
    "Sunita", "Meena", "Rekha", "Geeta", "Anita", "Shweta", "Komal",
    "Ayaan", "Dev", "Ishaan", "Kunal", "Nikhil", "Pranav", "Shreya",
    "Tanvi", "Tanya", "Ruchi", "Swati", "Preeti", "Nisha", "Monika",
]

ALL_NAMES = PAKISTANI_NAMES + INDIAN_NAMES

PAYMENT_METHODS = ["Binance Pay ⚡", "JazzCash 📱", "EasyPaisa 📲"]


def _enabled_payment_methods():
    """🆕 v102: return ONLY the payment methods the admin has enabled.
    Bug: fake purchase/deposit broadcasts used to advertise EasyPaisa and
    JazzCash even when admin had disabled those methods → customers would
    tap 'Buy Now' + get 'method unavailable' error. Now filters random pick
    to enabled-only.

    Fallback: if admin somehow disabled everything, return the full list so
    fake activity keeps working (never break the broadcast pipeline).
    """
    try:
        from database import is_payment_enabled
        pairs = [
            ("binance",   "Binance Pay ⚡"),
            ("jazzcash",  "JazzCash 📱"),
            ("easypaisa", "EasyPaisa 📲"),
        ]
        enabled = [label for method, label in pairs if is_payment_enabled(method)]
        return enabled or PAYMENT_METHODS  # never empty
    except Exception:
        return PAYMENT_METHODS

# ── Settings Keys ────────────────────────────────────────────────
S_GLOBAL_ON    = "pua_global_enabled"   # "1"/"0" — master switch
S_MIN_INTERVAL = "pua_min_interval"     # minutes (default 1)
S_MAX_INTERVAL = "pua_max_interval"     # minutes (default 60)
S_FIRST_DELAY  = "pua_first_delay"      # seconds before first msg (default 10)
S_TYPE_PURCHASE= "pua_type_purchase"    # "1"/"0"
S_TYPE_DEPOSIT = "pua_type_deposit"     # "1"/"0"
S_TYPE_REFERRAL= "pua_type_referral"    # "1"/"0"
S_TYPE_DISCOUNT= "pua_type_discount"    # "1"/"0"
S_TYPE_REVIEW  = "pua_type_review"      # "1"/"0"
S_TYPE_TIER    = "pua_type_tier"        # "1"/"0"
# 🆕 Extra toggleable types
S_TYPE_MILESTONE = "pua_type_milestone"   # 🏆 Referral milestone reward
S_TYPE_STOCK     = "pua_type_stock"       # 🔔 New stock alert
S_TYPE_NEWUSER   = "pua_type_newuser"     # 🎉 New user joined
S_TYPE_FLASH     = "pua_type_flash"       # 🛍 Flash sale (real events only)
S_TYPE_NEWPROD   = "pua_type_newprod"     # 🆕 New product (real + fake)
S_TYPE_PRICE_DROP= "pua_type_price_drop"  # 🆕 v66 Big Price Drop alerts


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


def is_globally_enabled():
    """Returns True if fake activity system is ON globally."""
    return _g(S_GLOBAL_ON, "1") == "1"


def get_speed():
    """Returns (min_minutes, max_minutes) interval between messages."""
    try:
        mn = max(1, int(_g(S_MIN_INTERVAL, "1")))
        mx = max(mn, int(_g(S_MAX_INTERVAL, "60")))
        return mn, mx
    except Exception:
        return 1, 60


def get_speed_seconds():
    """Returns (min_seconds, max_seconds) interval between messages based on unit."""
    try:
        unit = _g("pua_interval_unit", "minutes")
        mn, mx = get_speed()
        if unit == "minutes":
            return mn * 60, mx * 60
        else:
            return mn, mx
    except Exception:
        return 60, 3600


def get_first_delay():
    """Seconds before first message after user joins. Default 10."""
    try:
        return max(5, int(_g(S_FIRST_DELAY, "10")))
    except Exception:
        return 10


def is_type_on(type_key):
    """Check if a message type is enabled. Default all ON."""
    key_map = {
        "purchase":  S_TYPE_PURCHASE,
        "deposit":   S_TYPE_DEPOSIT,
        "referral":  S_TYPE_REFERRAL,
        "discount":  S_TYPE_DISCOUNT,
        "review":    S_TYPE_REVIEW,
        "tier":      S_TYPE_TIER,
        # 🆕 extra types
        "milestone": S_TYPE_MILESTONE,
        "stock":     S_TYPE_STOCK,
        "newuser":   S_TYPE_NEWUSER,
        "flash":     S_TYPE_FLASH,
        "newprod":   S_TYPE_NEWPROD,
        "price_drop": S_TYPE_PRICE_DROP,   # 🆕 v66
    }
    k = key_map.get(type_key)
    return _g(k, "1") == "1" if k else False


# ── Database Functions ────────────────────────────────────────────

def setup_activity_table():
    """Create the user_activity_jobs table if it doesn't exist."""
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_activity_jobs (
                user_id    INTEGER PRIMARY KEY,
                is_active  INTEGER DEFAULT 1,
                last_sent  TEXT DEFAULT '',
                msg_count  INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[Activity] Table setup error: {e}")


def register_user_job(user_id):
    """
    Register a user for lifetime fake activity.
    Called once when user first starts the bot.
    If already registered, does nothing (safe to call multiple times).
    """
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO user_activity_jobs
                (user_id, is_active, msg_count)
            VALUES (?, 1, 0)
        """, (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[Activity] register_user_job error: {e}")


def is_user_active(user_id):
    """Returns True if this user's fake activity is ON."""
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT is_active FROM user_activity_jobs WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return bool(row and row[0] == 1)
    except Exception:
        return False


def set_user_active(user_id, active: bool):
    """Enable or disable fake activity for a specific user."""
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE user_activity_jobs SET is_active=? WHERE user_id=?
        """, (1 if active else 0, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[Activity] set_user_active error: {e}")


def update_user_activity_log(user_id, msg_preview):
    """Update last_sent timestamp and increment msg_count."""
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE user_activity_jobs
            SET last_sent=?, msg_count=msg_count+1
            WHERE user_id=?
        """, (datetime.now().strftime("%Y-%m-%d %H:%M"), user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[Activity] log error: {e}")


def get_all_activity_jobs():
    """Get all registered users and their activity status."""
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT j.user_id, j.is_active, j.last_sent, j.msg_count, j.created_at,
                   u.first_name, u.username
            FROM user_activity_jobs j
            LEFT JOIN users u ON j.user_id = u.user_id
            ORDER BY j.msg_count DESC
        """)
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"[Activity] get_all error: {e}")
        return []


def get_active_user_ids():
    """Get list of user_ids that have is_active=1."""
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT user_id FROM user_activity_jobs
            WHERE is_active=1
        """)
        rows = c.fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def stop_all_jobs():
    """Stop fake activity for ALL users."""
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE user_activity_jobs SET is_active=0")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[Activity] stop_all error: {e}")


def start_all_jobs():
    """Start fake activity for ALL registered users."""
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE user_activity_jobs SET is_active=1")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[Activity] start_all error: {e}")


# ── Message Generators ────────────────────────────────────────────

def _random_name():
    """Pick a random realistic name from Pakistani+Indian pool."""
    return random.choice(ALL_NAMES)


def _mask_name(name):
    """Convert name to masked style like b•••l.
    🔧 Uses the bullet '•' (NOT '*') so it never breaks Telegram Markdown
    or shows raw asterisks to users."""
    if len(name) <= 2:
        return name + "•••"
    dots = "•" * random.randint(2, 4)
    return name[0] + dots + name[-1]


def _get_random_product():
    """
    Get a random in-stock product from your REAL store DB only.
    Returns (id, name, price) or None if no products in stock.
    NO fake fallback list — only real products you added.

    Premium/custom-emoji HTML is kept intact so fake activity can render it
    through smart_text_and_mode() instead of leaking raw [[HTML]].
    """
    try:
        # 🆕 v60: get_all_products() excludes hidden by default. Also re-check
        # stock + hide flag here so a freshly-hidden product can't leak into
        # a per-user fake broadcast (and look fake when the user taps it).
        from database import get_all_products, is_product_hidden
        products = []
        for p in get_all_products():
            d = dict(p) if not isinstance(p, dict) else p
            pid_ = d.get("id")
            if not pid_: continue
            stock_v = (p["stock"] if isinstance(p, dict) else p[6])
            if int(stock_v or 0) <= 0:
                continue
            try:
                if is_product_hidden(pid_): continue
            except Exception:
                pass
            products.append(p)
        if products:
            p     = random.choice(products)
            pid   = p["id"] if isinstance(p, dict) else p[0]
            name  = p["name"] if isinstance(p, dict) else p[2]
            price = float(p["price"] if isinstance(p, dict) else p[4] or 5.0)
            return pid, name, price
    except Exception:
        pass
    return None  # No products in stock — caller must handle this

async def build_fake_message(bot, user_id: int) -> tuple[str, any]:
    """
    Build one random fake message.

    Active types:
      purchase (30%) — ONLY real in-stock products; skips if no stock
      deposit  (20%) — always works, no product needed
      referral (10%) — fake active referral notification
      discount (15%) — fake discount deal alerts with PKR equivalents
      review   (15%) — fake review broadcasts (English & Roman Urdu)
      tier     (10%) — fake tier upgrade announcements
    """
    type_pool = []
    weights   = []
    all_types = [
        ("purchase", 26),
        ("deposit",  16),
        ("referral", 8),
        ("discount", 12),
        ("review",   12),
        ("tier",     8),
        # 🆕 extra fake types
        ("milestone", 6),
        ("stock",     6),
        ("newuser",   4),
        ("newprod",   2),
        ("price_drop", 5),   # 🆕 v66 — Big Price Drop alerts
        # NOTE: 'flash' is NOT in the random pool — flash sale only broadcasts
        # for REAL flash sales the admin sets (its toggle gates that broadcast).
    ]
    for t, w in all_types:
        if is_type_on(t):
            type_pool.append(t)
            weights.append(w)

    if not type_pool:
        type_pool = ["deposit"]
        weights   = [1]

    chosen = random.choices(type_pool, weights=weights)[0]
    name   = _random_name()
    masked = _mask_name(name)

    try:
        from customization import render_template
    except Exception:
        render_template = None

    # Get USD TO PKR conversion rate
    try:
        from database import get_setting
        pkr_rate = float(get_setting("usd_to_pkr_rate", "280"))
    except Exception:
        pkr_rate = 280.0

    def _render(tpl_id, data):
        if render_template:
            try:
                return render_template(tpl_id, data)
            except Exception:
                pass
        return None

    # ── PURCHASE ─────────────────────────────────
    if chosen == "purchase":
        product = _get_random_product()
        if product:
            pid, pname, price = product
            qty    = random.choices([1, 1, 1, 2, 3], weights=[60, 20, 10, 7, 3])[0]
            amount = round(price * qty, 2)
            pkr_amount = f"Rs {int(amount * pkr_rate):,}"
            txid = f"BITE-{random.randint(100000, 999999)}-PK"
            
            msg = _render("bc_purchase", {
                "user":    masked,
                "product": pname,
                "qty":     str(qty),
                "amount":  f"{amount:.2f}",
                "pkr_amount": pkr_amount,
                "txid": txid,
            })
            
            try:
                bot_me = await bot.get_me()
                bot_username = bot_me.username
            except Exception:
                bot_username = "BiteStoreBot"
                
            deep_link = f"https://t.me/{bot_username}?start=buy_{pid}"
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            # 🆕 v43: per-template button (premium-emoji-icon aware)
            try:
                from button_system import build_button as _bb
                _btn = _bb("bc_purchase", "🛒 Buy Now", url=deep_link)
            except Exception:
                _btn = InlineKeyboardButton("🛒 Buy Now", url=deep_link)
            kb = InlineKeyboardMarkup([[_btn]])
            
            if msg:
                return msg, kb
            return (
                f"🛒 *New Purchase!* 🏪\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 *Buyer:* {masked}\n"
                f"📦 *Product:* {pname}\n"
                f"🔢 *Quantity:* {qty}\n"
                f"💰 *Total:* ${amount:.2f} (~{pkr_amount})\n"
                f"🧾 *Order ID:* `{txid}`\n\n"
                f"⚡ _Status: Delivered Instantly_ ✅"
            ), kb
        # No real stock — fall through to deposit
        chosen = "deposit"

    # ── DEPOSIT ──────────────────────────────────
    if chosen == "deposit":
        amount = round(round(random.uniform(2, 30) * 2) / 2, 2)
        method = random.choice(_enabled_payment_methods())
        pkr_amount = f"Rs {int(amount * pkr_rate):,}"
        txid = f"{'EP' if 'Easy' in method else 'JC' if 'Jazz' in method else 'BIN'}-{random.randint(10000000, 99999999)}"
        
        msg = _render("bc_deposit", {
            "user":   masked,
            "amount": f"{amount:.2f}",
            "method": method,
            "pkr_amount": pkr_amount,
            "txid": txid,
        })
        if msg:
            return msg, None
        return (
            f"💳 *New Deposit Alert!* 💲\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 *User:* {masked}\n"
            f"💰 *Added Amount:* ${amount:.2f} (~{pkr_amount})\n"
            f"🔵 *Gateway:* {method}\n"
            f"🧾 *Transaction ID:* `{txid}`\n\n"
            f"⚡ _Status: Auto-Credited via API_ 🟢"
        ), None

    # ── REFERRAL ─────────────────────────────────
    if chosen == "referral":
        referrals = random.randint(5, 250)
        more      = random.randint(1, 15)
        msg = _render("bc_active_referral", {
            "user":      masked,
            "referrals": str(referrals),
            "more":      str(more),
        })
        if msg:
            return msg, None
        return (
            f"📈 *Referral Joined!* 🎁\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 *Referrer:* {masked}\n"
            f"✅ *Active Network:* {referrals} members\n"
            f"⏳ *{more} more* invites to unlock next reward milestone!\n\n"
            f"🚀 _Invite friends and earn free balance!_"
        ), None

    # ── DISCOUNT ─────────────────────────────────
    if chosen == "discount":
        product = _get_random_product()
        if product:
            pid, pname, price = product
            discount_pct = random.choice([50, 60, 70, 75, 80])
            old_price = round((price / (1 - discount_pct / 100)) * 2) / 2
            if old_price <= price:
                old_price = price + 10.0
            
            saved_usd = old_price - price
            old_pkr = f"Rs {int(old_price * pkr_rate):,}"
            new_pkr = f"Rs {int(price * pkr_rate):,}"
            saved_pkr = f"Rs {int(saved_usd * pkr_rate):,}"
            
            old_price_str = f"${old_price:.2f} (~{old_pkr})"
            new_price_str = f"${price:.2f} (~{new_pkr})"
            saved_price_str = f"${saved_usd:.2f} (~{saved_pkr})"
            
            left_stock = random.choice([2, 3, 4, 5])
            
            msg = _render("bc_discount", {
                "product":     pname,
                "old_price":   old_price_str,
                "new_price":   new_price_str,
                "saved_price": saved_price_str,
                "pct_off":     str(discount_pct),
                "stock":       str(left_stock),
            })
            
            try:
                bot_me = await bot.get_me()
                bot_username = bot_me.username
            except Exception:
                bot_username = "BiteStoreBot"
                
            deep_link = f"https://t.me/{bot_username}?start=buy_{pid}"
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            # 🆕 v43: per-template button (premium-emoji-icon aware)
            try:
                from button_system import build_button as _bb
                _btn = _bb("bc_discount", "🛒 Buy Now", url=deep_link)
            except Exception:
                _btn = InlineKeyboardButton("🛒 Buy Now", url=deep_link)
            kb = InlineKeyboardMarkup([[_btn]])
            
            if msg:
                return msg, kb
            return (
                f"🔥 Big Price Drop! Hurry Up! ⏰\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 Product: {pname}\n"
                f"📉 Was: {old_price_str}\n"
                f"💥 Now Only: {new_price_str}\n"
                f"🎯 You Save: {saved_price_str} ({discount_pct}% OFF!)\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ Limited Stock: Only {left_stock} Left!\n"
                f"⏳ Offer Ends: Tonight at Midnight!\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🛒 Buy Now Before It's Gone!\n\n"
                f"⚡ Status: Limited Time Offer 🔴"
            ), kb
        chosen = "deposit"

    # ── REVIEW ───────────────────────────────────
    if chosen == "review":
        product = _get_random_product()
        if product:
            pid, pname, price = product
            try:
                from fake_engagement import generate_fake_reviewer, generate_review_text, generate_star_rating
                reviewer_name, language = generate_fake_reviewer(60) # 60% urdu, 40% english
                stars_count = generate_star_rating()
                review_text = generate_review_text(language, include_text=True)
            except Exception:
                reviewer_name = _random_name()
                language = "urdu"
                stars_count = 5
                review_text = "Bohat acha product hai, highly recommend!"
                
            masked = _mask_name(reviewer_name)
            stars_str = "⭐" * stars_count
            
            msg = _render("bc_review", {
                "user":      masked,
                "product":   pname,
                "stars":     stars_str,
                "review":    review_text,
            })
            
            try:
                bot_me = await bot.get_me()
                bot_username = bot_me.username
            except Exception:
                bot_username = "BiteStoreBot"
                
            deep_link = f"https://t.me/{bot_username}?start=buy_{pid}"
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            # 🆕 v43: per-template button (premium-emoji-icon aware)
            try:
                from button_system import build_button as _bb
                _btn = _bb("bc_review", "🛒 Buy Now", url=deep_link)
            except Exception:
                _btn = InlineKeyboardButton("🛒 Buy Now", url=deep_link)
            kb = InlineKeyboardMarkup([[_btn]])
            
            if msg:
                return msg, kb
            return (
                f"⭐ New Product Review! ⭐\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 User: {masked}\n"
                f"📦 Product: {pname}\n"
                f"🏅 Rating: {stars_str}\n"
                f"💬 Review:\n"
                f"{review_text}\n\n"
                f"⚡ Status: Verified Buyer Feedback ✅"
            ), kb
        chosen = "deposit"

    # ── 🆕 REFERRAL MILESTONE (reward earned) ─────
    if chosen == "milestone":
        referrals = random.choice([10, 25, 50, 100])
        reward = round(random.uniform(0.20, 1.50), 2)
        total_ref = round(reward * random.uniform(3, 12), 2)
        msg = _render("bc_referral", {
            "user": masked, "referrals": str(referrals),
            "reward": f"{reward:.2f}", "total_ref": f"{total_ref:.2f}",
        })
        if msg:
            return msg, None
        return (
            f"🏆 Referral Milestone!\n\n"
            f"👤 {masked}\n"
            f"✅ Active Referrals: {referrals}\n"
            f"💰 Reward Earned: +${reward:.2f}\n"
            f"📊 Total from Referrals: ${total_ref:.2f}"
        ), None

    # ── 🆕 NEW STOCK ALERT ────────────────────────
    if chosen == "stock":
        product = _get_random_product()
        if product:
            pid, pname, price = product
            stock_n = random.choice([5, 10, 15, 20, 25])
            # 🆕 v94: {added} placeholder — for fake random broadcasts we
            # simulate a plausible "added" number (2-8 units)
            added_fake = random.choice([2, 3, 5, 8, 10, 12])
            msg = _render("bc_stock", {
                "product": pname, "added": str(added_fake),
                "stock": str(stock_n), "price": f"{price:.2f}",
            })
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            try:
                bot_me = await bot.get_me(); bot_username = bot_me.username
            except Exception:
                bot_username = "BiteStoreBot"
            # 🆕 v43: per-template button (premium-emoji-icon aware)
            _url = f"https://t.me/{bot_username}?start=buy_{pid}"
            # 🆕 v94: product-name prefix + global broadcast color
            try:
                from fake_engagement import _buy_now_label, _get_broadcast_global_color
                _lbl = _buy_now_label(pid, "🛒 Buy Now")
                _color = _get_broadcast_global_color("bc_stock")
            except Exception:
                _lbl = "🛒 Buy Now"
                _color = ""
            try:
                from button_system import build_button as _bb
                _btn = _bb("bc_stock", _lbl, url=_url)
                if _color:
                    try:
                        _btn = InlineKeyboardButton(
                            _btn.text, url=_url,
                            api_kwargs={"style": _color},
                        )
                    except Exception:
                        pass
            except Exception:
                _btn = InlineKeyboardButton(_lbl, url=_url)
            kb = InlineKeyboardMarkup([[_btn]])
            if msg:
                return msg, kb
            return (
                f"🔔 New stock available!\n\n"
                f"🏪 Product: {pname}\n"
                f"✅ Available Now: {stock_n}\n"
                f"💰 Price: ${price:.2f}\n\n"
                f"Hurry up and buy now from the store! 🛒"
            ), kb
        chosen = "deposit"

    # ── 🆕 NEW USER JOINED ────────────────────────
    if chosen == "newuser":
        try:
            from database import get_user_count
            count = get_user_count() + int(_g("fake_user_offset", "500"))
        except Exception:
            count = random.randint(500, 2000)
        msg = _render("bc_new_user", {"name": name, "count": f"{count:,}"})
        if msg:
            return msg, None
        return (
            f"🎉 New member joined Bite Store! 🛍️\n\n"
            f"👤 {name} just joined our community!\n"
            f"👥 Members: {count:,}\n\n"
            f"Welcome to the family! 🚀"
        ), None

    # ── 🆕 v66: BIG PRICE DROP (fake random — picks any product + fake "old price") ──
    if chosen == "price_drop":
        product = _get_random_product()
        if product:
            pid, pname, price = product
            # Fake old price = current × 1.3–1.8 (so 30–80% higher)
            old_price = price * random.uniform(1.3, 1.8)
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            try:
                bot_me = await bot.get_me(); bot_username = bot_me.username
            except Exception:
                bot_username = "BiteStoreBot"
            try:
                from templates_bundle import render_price_drop
                msg = render_price_drop(pname, old_price, price)
            except Exception:
                msg = ""
            if msg:
                _url = f"https://t.me/{bot_username}?start=buy_{pid}"
                try:
                    from button_system import build_button as _bb
                    _btn = _bb("bc_discount", "🛒 Buy Now", url=_url)
                except Exception:
                    _btn = InlineKeyboardButton("🛒 Buy Now", url=_url)
                kb = InlineKeyboardMarkup([[_btn]])
                return msg, kb
        chosen = "discount"  # fallback if no product

    # ── 🆕 NEW PRODUCT (fake random) ──────────────
    if chosen == "newprod":
        product = _get_random_product()
        if product:
            pid, pname, price = product
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            try:
                bot_me = await bot.get_me(); bot_username = bot_me.username
            except Exception:
                bot_username = "BiteStoreBot"
            # 🆕 v43: per-template button (premium-emoji-icon aware)
            _url = f"https://t.me/{bot_username}?start=buy_{pid}"
            # 🐛 v95 FIX: use v94 helpers for product-name prefix + global color
            try:
                from fake_engagement import _buy_now_label, _get_broadcast_global_color
                _lbl = _buy_now_label(pid, "🛒 Buy Now")
                _color = _get_broadcast_global_color("bc_newprod")
            except Exception:
                _lbl = "🛒 Buy Now"
                _color = ""
            try:
                from button_system import build_button as _bb
                _btn = _bb("bc_newprod", _lbl, url=_url)
                if _color:
                    try:
                        _btn = InlineKeyboardButton(
                            _btn.text, url=_url,
                            api_kwargs={"style": _color},
                        )
                    except Exception:
                        pass
            except Exception:
                _btn = InlineKeyboardButton(_lbl, url=_url)
            kb = InlineKeyboardMarkup([[_btn]])
            # 🐛 v95 FIX: use admin's custom template via _render() instead
            # of hardcoded English. Falls back to English if no template set.
            msg = _render("bc_newprod", {
                "product": pname,
                "price": f"{price:.2f}",
                "desc": "Auto-delivery",
                "stock": "in stock",
            })
            if msg:
                return msg, kb
            # Fallback (only if bc_newprod template completely missing)
            return (
                f"🆕 NEW PRODUCT ADDED! 🛍\n\n"
                f"📦 {pname}\n"
                f"💵 Price: ${price:.2f}\n\n"
                f"🛒 Available now — tap Buy Now!"
            ), kb
        chosen = "deposit"

    # ── TIER ─────────────────────────────────────
    if chosen == "tier" or chosen == "deposit": # fallback to tier if somehow selected
        tier_data = random.choice([
            {"prev": "🥉 Bronze", "new": "🥈 Silver", "spent": random.uniform(20, 45), "benefit": "5% Permanent Discount"},
            {"prev": "🥈 Silver", "new": "🥇 Gold", "spent": random.uniform(100, 140), "benefit": "10% Permanent Discount"},
            {"prev": "🥇 Gold", "new": "💎 Platinum", "spent": random.uniform(300, 450), "benefit": "15% Permanent Discount"},
            {"prev": "💎 Platinum", "new": "💠 Diamond", "spent": random.uniform(1000, 1200), "benefit": "20% Permanent Discount"},
        ])
        
        spent_usd = tier_data["spent"]
        spent_pkr = f"Rs {int(spent_usd * pkr_rate):,}"
        spent_str = f"${spent_usd:.2f} (~{spent_pkr})"
        
        from datetime import datetime
        date_str = datetime.now().strftime("%d %b %Y")
        
        msg = _render("bc_tier", {
            "user":        masked,
            "tier":        tier_data["new"],
            "prev_tier":   tier_data["prev"],
            "new_tier":    tier_data["new"],
            "total_spent": spent_str,
            "benefit":     tier_data["benefit"],
            "date":        date_str,
        })
        if msg:
            return msg, None
        return (
            f"💎 Loyalty Tier Update! 🏆\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 User: {masked}\n"
            f"🎖️ Previous Tier: {tier_data['prev']}\n"
            f"🚀 New Tier: {tier_data['new']}\n"
            f"🛍️ Total Spent: {spent_str}\n"
            f"🎁 Tier Benefit: {tier_data['benefit']}\n"
            f"📅 Upgraded On: {date_str}\n\n"
            f"⚡ Status: Tier Upgraded Automatically 🟢"
        ), None

    # ── ULTIMATE FALLBACK ─────────────────────────
    amount = round(round(random.uniform(2, 20) * 2) / 2, 2)
    method = random.choice(_enabled_payment_methods())
    pkr_amount = f"Rs {int(amount * pkr_rate):,}"
    txid = f"GEN-{random.randint(100000, 999999)}"
    return (
        f"💳 *New Deposit Alert!* 💲\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *User:* {masked}\n"
        f"💰 *Added Amount:* ${amount:.2f} (~{pkr_amount})\n"
        f"🔵 *Gateway:* {method}\n"
        f"🧾 *Transaction ID:* `{txid}`\n\n"
        f"⚡ _Status: Auto-Credited via API_ 🟢"
    ), None




# ── Per-User Job Runner ───────────────────────────────────────────

# In-memory set of user_ids that have a scheduled job this session
# (Jobs are re-created on bot restart via restore_all_jobs)
_scheduled_users: set = set()


async def _send_activity_to_user(bot, user_id: int):
    """
    Send ONE fake message to a specific user.
    Called by the scheduled job.
    """
    if not is_globally_enabled():
        return
    if not is_user_active(user_id):
        return

    msg, kb = await build_fake_message(bot, user_id)
    try:
        # If mode is both, the per-user job should only send to the user's private chat.
        # If mode is bot_only, it only sends to the user's private chat.
        # If mode is group_only, per-user jobs do nothing (or shouldn't send to user).
        mode = _g("dest_mode", "bot_only")
        if mode in ("bot_only", "both"):
            # 🆕 Premium/custom emoji aware everywhere in the message
            _text, _pm = smart_text_and_mode(msg, "Markdown")
            try:
                await bot.send_message(
                    chat_id=user_id, text=_text, parse_mode=_pm, reply_markup=kb)
            except Exception as e:
                try:
                    await bot.send_message(chat_id=user_id, text=_text, reply_markup=kb)
                except Exception as e2:
                    logger.debug(f"[Activity] Private send to {user_id} failed: {e2}")
            update_user_activity_log(user_id, msg[:50])
            logger.info(f"[Activity] ✅ Sent private activity to {user_id}")
    except Exception as e:
        logger.debug(f"[Activity] Send to {user_id} failed: {e}")
        logger.debug(f"[Activity] Send to {user_id} failed: {e}")
        logger.debug(f"[Activity] Send to {user_id} failed: {e}")


def _schedule_next_for_user(app, user_id: int, delay_seconds: int = None):
    """
    Schedule the NEXT fake message for a specific user.
    After sending, re-schedules itself automatically.
    """
    if delay_seconds is None:
        mn_s, mx_s = get_speed_seconds()
        delay_seconds = random.randint(mn_s, mx_s)

    async def _job(context):
        if not is_globally_enabled() or not is_user_active(user_id):
            # User stopped or global off — remove from scheduled set
            # so admin can restart cleanly without double-scheduling
            _scheduled_users.discard(user_id)
            return  # Do NOT re-schedule — job ends here

        try:
            await _send_activity_to_user(context.bot, user_id)
        except Exception as e:
            logger.error(f"[Activity] Exception in job for {user_id}: {e}")
        finally:
            # Remove before re-scheduling (to allow clean re-entry)
            _scheduled_users.discard(user_id)
            # Schedule the NEXT one
            _schedule_next_for_user(context.application, user_id)

    try:
        app.job_queue.run_once(_job, when=delay_seconds,
                               name=f"pua_{user_id}")
        _scheduled_users.add(user_id)
    except Exception as e:
        logger.error(f"[Activity] Schedule error for {user_id}: {e}")


async def start_personal_activity(bot, app, user_id: int):
    """
    START lifetime fake activity for one user.

    Call this from handlers_start.py when user does /start.
    Safe to call multiple times — won't double-schedule.

    First message fires in ~10 seconds (configurable).
    After that, random 1–60 min intervals forever.
    """
    setup_activity_table()

    # Register in DB
    register_user_job(user_id)

    # Don't double-schedule
    if user_id in _scheduled_users:
        logger.debug(f"[Activity] {user_id} already scheduled, skip")
        return  # Job already running for this user

    if not is_globally_enabled():
        logger.debug(f"[Activity] Global OFF, not scheduling {user_id}")
        return

    first_delay = get_first_delay()  # default 10 seconds
    logger.info(f"[Activity] Starting lifetime job for {user_id} "
                f"(first msg in {first_delay}s)")

    _schedule_next_for_user(app, user_id, delay_seconds=first_delay)


_group_job_scheduled = False

def schedule_group_activity_job(app):
    """
    Schedules a single central job to send fake activity directly to the group.
    Runs if global fake activity is ON and dest_mode is 'group_only' or 'both'.
    Keeps the group active even if there are 0 users in the bot.
    """
    global _group_job_scheduled
    if _group_job_scheduled:
        logger.debug("[Activity] Group job already scheduled, skipping.")
        return

    # Let's get the interval range
    mn_s, mx_s = get_speed_seconds()
    delay_seconds = random.randint(mn_s, mx_s)

    logger.info(f"[Activity] Scheduling group-only central job in {delay_seconds} seconds")

    async def _group_job(context):
        global _group_job_scheduled
        _group_job_scheduled = False  # Reset so next one can be scheduled

        # Check if still enabled and correct mode
        mode = _g("dest_mode", "bot_only")
        dest_chat = _g("dest_chat_id", "").strip()

        if is_globally_enabled() and mode in ("group_only", "both") and dest_chat:
            try:
                # Generate and send message directly to group
                # Build fake message (using a dummy user_id 0)
                msg, kb = await build_fake_message(context.bot, 0)
                from ui_extras import _resolve_chat_id
                resolved_chat = await _resolve_chat_id(context.bot, dest_chat)
                # 🆕 Premium/custom emoji aware (see _send_activity_to_user)
                _text, _pm = smart_text_and_mode(msg, "Markdown")
                try:
                    await context.bot.send_message(
                        chat_id=resolved_chat, text=_text, parse_mode=_pm, reply_markup=kb)
                    logger.info(f"[Activity] Central group job sent message to {dest_chat}")
                except Exception as e:
                    # Fallback to plain text if parsing fails
                    try:
                        await context.bot.send_message(chat_id=resolved_chat, text=_text, reply_markup=kb)
                        logger.info(f"[Activity] Central group job sent message (fallback) to {dest_chat}")
                    except Exception as e2:
                        logger.warning(f"[Activity] Central group job send failed: {e2}")
            except Exception as e:
                logger.error(f"[Activity] Error in central group job send: {e}")

        # Re-schedule next central job
        schedule_group_activity_job(context.application)

    try:
        app.job_queue.run_once(_group_job, when=delay_seconds, name="pua_group_central")
        _group_job_scheduled = True
    except Exception as e:
        logger.error(f"[Activity] Central group job scheduling failed: {e}")


def restore_all_jobs(app):
    """
    Re-schedule jobs for ALL active users after bot restart.
    Call this from post_init() in bot.py.

    Without this, jobs would be lost on every bot restart.
    Each restored job gets a random initial delay so they don't
    all fire at the same time when bot restarts.
    """
    setup_activity_table()

    # Always schedule/restore the group central job too!
    try:
        schedule_group_activity_job(app)
    except Exception as e:
        logger.error(f"[Activity] Group job restore error: {e}")

    if not is_globally_enabled():
        logger.info("[Activity] Global OFF — skipping restore")
        return

    active_ids = get_active_user_ids()
    logger.info(f"[Activity] Restoring {len(active_ids)} user jobs...")

    for uid in active_ids:
        if uid not in _scheduled_users:
            # Stagger restart — spread over 0-5 min so bot isn't flooded
            delay = random.randint(30, 300)
            _schedule_next_for_user(app, uid, delay_seconds=delay)

    logger.info(f"[Activity] ✅ Restored {len(active_ids)} jobs")
