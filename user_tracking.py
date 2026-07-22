# ============================================================
# 📊 USER TRACKING — Per-user activity log (v65)
# ============================================================
# Logs EVERY callback button click + text command per user, so admin can
# see exactly where each user clicked, when, and how often.
#
# Lightweight: a single SQLite table with index on (user_id, created_at).
# Auto-wipes records older than 60 days every 24h.
#
# Used by admin panel:
#   Admin → 👤 Users → [user] → 📊 View Activity
# ============================================================

import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# Human-friendly labels for known callback prefixes (admin view formatting)
_LABELS = {
    "shop":            "🛒 Opened Shop",
    "buy_points":      "💎 Buy Points screen",
    "my_account":      "📊 My Account",
    "my_orders":       "📜 Order History",
    "transactions":    "🔄 Transactions",
    "referral":        "🎁 Referral",
    "support_menu":    "📞 Support",
    "warranty_menu":   "🛡 Warranty",
    "reviews_menu":    "⭐ Reviews",
    "loyalty_menu":    "🏆 Loyalty",
    "language_menu":   "🌐 Language",
    "main_menu":       "🏠 Main Menu",
    "admin_panel":     "🤖 Admin Panel",
    "/start":          "🚀 Started bot",
    "buy_":            "🛍 View / Buy product",
    "prod_":           "📦 Opened product",
    "pay_binance_":    "🟡 Binance Pay clicked",
    "pay_ep_":         "📱 EasyPaisa clicked",
    "pay_jc_":         "📱 JazzCash clicked",
    "pay_pts_":        "💎 Pay-with-points clicked",
    "ptspay_binance_": "💎+🟡 Buy Points via Binance",
    "ptspay_ep_":      "💎+📱 Buy Points via EasyPaisa",
    "ptspay_jc_":      "💎+📱 Buy Points via JazzCash",
    "vpay_":           "🔄 Verify Payment",
    "vpoid_":          "🔄 Check Payment Again",
    "epv_":            "🔄 Verify EasyPaisa",
    "jcv_":            "🔄 Verify JazzCash",
    "cancel_order":    "❌ Cancelled Payment",
    "st_new":          "🎫 New Support Ticket",
    "freeclaim_":      "🎉 Free Claim screen",
    "shopfilter_":     "🔍 Shop filter changed",
    "lang_":           "🌐 Changed language",
    "review_":         "⭐ Review action",
    "rate_":           "⭐ Rated product",
}


def _pretty_event(cb_or_cmd: str) -> str:
    """Map a raw callback_data / command string to a human-readable label."""
    if not cb_or_cmd:
        return "❓ Unknown"
    s = str(cb_or_cmd)
    # Exact match first
    if s in _LABELS:
        return _LABELS[s]
    # Prefix match (longest first)
    for prefix in sorted(_LABELS.keys(), key=len, reverse=True):
        if prefix.endswith("_") and s.startswith(prefix):
            return _LABELS[prefix]
    # Unknown — return raw
    return f"📌 {s[:30]}"


def ensure_table():
    """Create the tracking table if it doesn't exist."""
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_clicks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                action     TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_uc_user_time ON user_clicks(user_id, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_uc_time      ON user_clicks(created_at)")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"[Tracking] ensure_table failed: {e}")


def log_click(user_id, action):
    """Log a single user click/command. Silently no-op on any error."""
    if not user_id or not action:
        return
    # Skip admin's own clicks (avoid polluting DB with admin testing)
    try:
        from config import ADMIN_ID
        if int(user_id) == int(ADMIN_ID):
            return
    except Exception:
        pass
    # Skip noisy generic callbacks
    skip_prefixes = ("act_noop", "noop", "_noop")
    if any(str(action).startswith(p) for p in skip_prefixes):
        return
    try:
        ensure_table()
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO user_clicks (user_id, action) VALUES (?, ?)",
            (int(user_id), str(action)[:60]),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"[Tracking] log_click failed: {e}")


def get_user_clicks(user_id, limit=30):
    """Return recent clicks for one user, newest first."""
    try:
        ensure_table()
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            "SELECT action, created_at FROM user_clicks "
            "WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (int(user_id), int(limit)),
        )
        rows = c.fetchall()
        conn.close()
        return [(r[0], r[1]) for r in rows]
    except Exception as e:
        logger.warning(f"[Tracking] get_user_clicks failed: {e}")
        return []


def get_user_stats(user_id, days=None):
    """Return summary stats for a user.
       days=None → lifetime;  days=1 → today;  days=7 → week;  days=30 → month."""
    try:
        ensure_table()
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        if days:
            since = (datetime.utcnow() - timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
            c.execute(
                "SELECT action, COUNT(*) FROM user_clicks "
                "WHERE user_id=? AND created_at >= ? "
                "GROUP BY action ORDER BY 2 DESC",
                (int(user_id), since),
            )
        else:
            c.execute(
                "SELECT action, COUNT(*) FROM user_clicks "
                "WHERE user_id=? "
                "GROUP BY action ORDER BY 2 DESC",
                (int(user_id),),
            )
        rows = c.fetchall()
        # Total
        if days:
            c.execute(
                "SELECT COUNT(*), MIN(created_at), MAX(created_at) "
                "FROM user_clicks WHERE user_id=? AND created_at >= ?",
                (int(user_id), since),
            )
        else:
            c.execute(
                "SELECT COUNT(*), MIN(created_at), MAX(created_at) "
                "FROM user_clicks WHERE user_id=?",
                (int(user_id),),
            )
        total, first_seen, last_seen = c.fetchone()
        conn.close()
        return {
            "total": int(total or 0),
            "first_seen": first_seen,
            "last_seen": last_seen,
            "by_action": [(r[0], r[1]) for r in rows],
        }
    except Exception as e:
        logger.warning(f"[Tracking] get_user_stats failed: {e}")
        return {"total": 0, "first_seen": None, "last_seen": None, "by_action": []}


def wipe_old(older_than_days=60):
    """Delete tracking rows older than N days. Called by daily background job.
       Pass 0 to wipe ALL tracking (used by admin 'Wipe All Now' button)."""
    try:
        ensure_table()
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        if int(older_than_days) <= 0:
            c.execute("DELETE FROM user_clicks")
        else:
            cutoff = (datetime.utcnow() - timedelta(days=int(older_than_days))).strftime("%Y-%m-%d %H:%M:%S")
            c.execute("DELETE FROM user_clicks WHERE created_at < ?", (cutoff,))
        deleted = c.rowcount
        conn.commit()
        conn.close()
        if deleted:
            logger.info(f"[Tracking] wiped {deleted} click rows (older_than_days={older_than_days})")
        return deleted
    except Exception as e:
        logger.warning(f"[Tracking] wipe failed: {e}")
        return 0


# Background job — runs daily, wipes >60 day records (= 2 months)
async def tracking_wipe_job(context):
    try:
        from asyncio import to_thread
        await to_thread(wipe_old, 60)
    except Exception as e:
        logger.debug(f"[Tracking] wipe job error: {e}")


def pretty_event(cb_or_cmd: str) -> str:
    """Public alias for the admin panel."""
    return _pretty_event(cb_or_cmd)
