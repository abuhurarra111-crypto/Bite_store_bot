# ════════════════════════════════════════════════════════════════
# 🆕 v170.91 — CUSTOM FAKE REVIEWS (owner's own review texts)
# ════════════════════════════════════════════════════════════════
# Owner ka flow (user demand, 2026-09-09):
#   Admin Panel → ⭐ Fake Reviews → ➕ Add Custom Reviews
#     1. Admin apni reviews bhejta hai — HAR LINE EK REVIEW
#        (premium emojis allowed: "Osm 😍", "Excellent 🔥", ...)
#     2. Bot categories dikhata hai → admin category select karta hai
#     3. Us category ke products dikhte hain → admin product tap karta hai
#     4. SARI reviews us product par add ho jati hain — har review ke liye
#        bot khud FAKE PROFILE banata hai (fake naam + fake 9B user ID +
#        random 3–5 stars, kabhi 3 se kam nahi — real lagne ke liye).
#     5. Reviews random times par khud-ba-khud broadcast hote hain —
#        HAR REVIEW SIRF EK BAR — selected destination par
#        (wahi destination jo Fake Activity me set hai).
#
# Restart-safe: queue DB table me hai (pending/sent status).
# ════════════════════════════════════════════════════════════════

import asyncio
import logging
import random
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
except Exception:  # pragma: no cover
    InlineKeyboardButton = InlineKeyboardMarkup = None

from config import ADMIN_ID

# ConversationHandler state for review-lines input
CFR_LINES = 1


# ────────────────────────────────────────────────────────────────
# DB — custom_review_queue table
# ────────────────────────────────────────────────────────────────

def _ensure_queue_table():
    from database import get_connection
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS custom_review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            review_text TEXT NOT NULL,
            rating INTEGER NOT NULL DEFAULT 5,
            fake_name TEXT NOT NULL DEFAULT '',
            fake_uid INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            sent_at TEXT DEFAULT ''
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_crq_status ON custom_review_queue(status)")
    conn.commit(); conn.close()


def pending_queue_count() -> int:
    try:
        _ensure_queue_table()
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM custom_review_queue WHERE status='pending'")
        n = int(c.fetchone()[0] or 0)
        conn.close()
        return n
    except Exception:
        return 0


def sent_queue_count() -> int:
    try:
        _ensure_queue_table()
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM custom_review_queue WHERE status='sent'")
        n = int(c.fetchone()[0] or 0)
        conn.close()
        return n
    except Exception:
        return 0


# ────────────────────────────────────────────────────────────────
# CORE — insert reviews with auto fake profiles
# ────────────────────────────────────────────────────────────────

def _random_rating():
    """Random 3–5 stars — kabhi 3 se kam nahi (real lagta hai)."""
    return random.choices([5, 4, 3], weights=[55, 30, 15])[0]


def add_custom_reviews(product_id: int, review_lines, product_name: str = ""):
    """Har line = ek review. Fake profile + product_reviews insert + broadcast
    queue row. Returns (inserted_count, skipped_count)."""
    from fake_engagement import generate_fake_reviewer, generate_fake_user_id, _log_review
    from database import get_connection
    _ensure_queue_table()

    inserted = skipped = 0
    conn = get_connection(); c = conn.cursor()
    try:
        for line in review_lines:
            txt = str(line or "").strip()
            if not txt:
                continue
            if len(txt) > 300:
                txt = txt[:300]
            # unique fake profile per review
            name, language = generate_fake_reviewer(pk_ratio=60)
            rating = _random_rating()
            ok = False
            for _attempt in range(10):
                fake_uid = generate_fake_user_id()
                c.execute("""INSERT OR IGNORE INTO product_reviews
                             (product_id, user_id, order_id, rating, review_text)
                             VALUES (?, ?, 0, ?, ?)""",
                          (product_id, fake_uid, rating, txt))
                if c.rowcount > 0:
                    # fake reviewer users table me — naam reviews me dikhe
                    c.execute("""INSERT OR IGNORE INTO users
                                 (user_id, first_name, username, joined_at,
                                  wallet_balance, points, referred_by, referral_count)
                                 VALUES (?, ?, ?, CURRENT_TIMESTAMP, 0, 0, 0, 0)""",
                              (fake_uid, name, f"fake_reviewer_{fake_uid}"))
                    # broadcast queue (har review SIRF EK bar broadcast hoga)
                    c.execute("""INSERT INTO custom_review_queue
                                 (product_id, review_text, rating, fake_name, fake_uid)
                                 VALUES (?, ?, ?, ?, ?)""",
                              (product_id, txt, rating, name, fake_uid))
                    ok = True
                    break
            if ok:
                inserted += 1
                try:
                    _log_review(name, language, product_name or f"#{product_id}", rating, txt)
                except Exception:
                    pass
            else:
                skipped += 1
        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass
    if inserted:
        logger.info(f"[CustomReviews] +{inserted} reviews → product {product_id} "
                    f"({product_name}); {skipped} skipped")
    return inserted, skipped


# ────────────────────────────────────────────────────────────────
# BROADCAST JOB — random times, har review sirf ek bar
# ────────────────────────────────────────────────────────────────

_BCAST_MIN_MIN = 45     # default random interval (minutes)
_BCAST_MAX_MIN = 180


def _get_interval_range():
    try:
        from database import get_setting
        mn = int(get_setting("cfr_bcast_min_min") or _BCAST_MIN_MIN)
        mx = int(get_setting("cfr_bcast_max_min") or _BCAST_MAX_MIN)
        if 1 <= mn <= mx:
            return mn, mx
    except Exception:
        pass
    return _BCAST_MIN_MIN, _BCAST_MAX_MIN


def _requeue_stale_sending(max_minutes: int = 10):
    """Crash/restart ke baad 'sending' mein phansi rows wapas pending karo."""
    from database import get_connection
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("""UPDATE custom_review_queue
                     SET status='pending', sent_at=NULL
                     WHERE status='sending'
                       AND sent_at IS NOT NULL
                       AND (julianday('now') - julianday(sent_at)) * 1440 > ?""",
                  (max_minutes,))
        n = c.rowcount
        conn.commit(); conn.close()
        if n:
            logger.info(f"[CustomReviews] requeued {n} stale 'sending' rows")
        return n
    except Exception:
        return 0


def _pop_next_pending():
    """Atomically claim ONE pending review row (id, product_id, review_text,
    rating, fake_name). Returns None if queue empty."""
    _ensure_queue_table()
    from database import get_connection
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("""SELECT id, product_id, review_text, rating, fake_name
                     FROM custom_review_queue WHERE status='pending'
                     ORDER BY id LIMIT 1""")
        row = c.fetchone()
        if row is None:
            return None
        d = dict(row)
        c.execute("""UPDATE custom_review_queue
                     SET status='sending', sent_at=CURRENT_TIMESTAMP
                     WHERE id=? AND status='pending'""",
                  (d["id"],))
        conn.commit()
        if c.rowcount != 1:   # koi aur worker le gaya
            return None
        return d
    finally:
        try: conn.close()
        except Exception: pass


async def custom_review_broadcast_job(context):
    """Ek pending review ko destination par bhejo → sent mark → next schedule."""
    bot = context.bot
    try:
        _requeue_stale_sending()
        row = _pop_next_pending()
        if row is None:
            # 🐛 v170.94 STORM FIX: queue khali → chain YAHIN ruk jati hai.
            # Purana code yahan _reschedule karta tha AUR finally BHI —
            # har idle run par 2 nayi jobs → chain DOUBLE → exponential
            # job storm (Railway: 1,800 log lines/min, 500 logs/sec cap,
            # misfires, bot unresponsive). Watchdog pending rows aane par
            # chain dobara start kar dega.
            return
        from database import get_connection, get_product
        sent_ok = False
        try:
            p = get_product(int(row["product_id"]))
            pname = ""
            pid_for_btn = 0
            if p:
                pd = dict(p)
                pid_for_btn = int(pd.get("id") or 0)
                try:
                    from button_system import extract_emoji_from_html
                    _eid, plain = extract_emoji_from_html(pd.get("name") or "")
                    pname = (plain or str(pd.get("name") or ""))[:40]
                except Exception:
                    pname = str(pd.get("name") or "")[:40]
            from utils import escape_md
            stars = "⭐" * int(row["rating"] or 5)
            msg = (
                f"{stars}\n"
                f"💬 *New Customer Review!*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 *{escape_md(pname or 'Product')}*\n\n"
                f"_\"{escape_md(str(row['review_text'])[:200])}\"_\n\n"
                f"— {escape_md(str(row['fake_name'])[:30])}, verified buyer ✅"
            )
            # destination-based broadcast + Buy Now button (agar product valid)
            from fake_engagement import broadcast_store_message
            n = await broadcast_store_message(bot, msg, pid=pid_for_btn or None,
                                              bypass_maintenance=True)
            sent_ok = n > 0
        except Exception as e:
            logger.error(f"[CustomReviews] broadcast failed: {e}")
        # status update: sent ya wapas pending (fail par retry agli schedule par)
        try:
            conn = get_connection(); c = conn.cursor()
            if sent_ok:
                c.execute("""UPDATE custom_review_queue
                             SET status='sent', sent_at=CURRENT_TIMESTAMP WHERE id=?""",
                          (row["id"],))
            else:
                c.execute("UPDATE custom_review_queue SET status='pending' WHERE id=?",
                          (row["id"],))
            conn.commit(); conn.close()
        except Exception:
            pass
        if sent_ok:
            logger.info(f"[CustomReviews] broadcast sent: review #{row['id']} "
                        f"→ product {row['product_id']}")
    except Exception as e:
        logger.error(f"[CustomReviews] job error: {e}")
    finally:
        _reschedule(context.application)


_JOB_NAME = "custom_review_broadcast"


def _reschedule(app):
    """🆕 v170.94 STORM FIX — teen guards:
    (1) dedup: pehle se koi broadcast job scheduled ho → SKIP
    (2) pending-only: queue khali → kuch schedule NAHI karo
    (3) ek hi job add karo (named) — multi-chain impossible."""
    try:
        if app is None or getattr(app, "job_queue", None) is None:
            return
        try:
            existing = app.job_queue.get_jobs_by_name(_JOB_NAME)
        except Exception:
            existing = []
        if existing:
            return
        if pending_queue_count() <= 0:
            return
        mn, mx = _get_interval_range()
        delay = random.randint(mn * 60, mx * 60)
        logger.info(f"[CustomReviews] next broadcast in {delay // 60}m")
        app.job_queue.run_once(custom_review_broadcast_job, when=delay,
                               name=_JOB_NAME)
    except Exception as e:
        logger.error(f"[CustomReviews] reschedule failed: {e}")


async def custom_review_watchdog_job(context):
    """🆕 v170.94: har 30 min — agar pending reviews hon lekin koi broadcast
    job scheduled nahi (crash/hiccup ke baad), chain dobara start karo."""
    try:
        _reschedule(context.application)
    except Exception:
        pass


def schedule_custom_review_broadcasts(app):
    """post_init se call hota hai. 🆕 v170.94: sirf pending rows par chain
    start hoti hai (empty par nahi) + 30-min self-heal watchdog."""
    _ensure_queue_table()
    _requeue_stale_sending()
    try:
        _reschedule(app)
    except Exception:
        pass
    try:
        if app is not None and getattr(app, "job_queue", None) is not None:
            app.job_queue.run_repeating(custom_review_watchdog_job,
                                        interval=1800, first=1800,
                                        name="custom_review_watchdog")
    except Exception as e:
        logger.error(f"[CustomReviews] watchdog setup failed: {e}")


# ────────────────────────────────────────────────────────────────
# ADMIN PANEL FLOW
# ────────────────────────────────────────────────────────────────

def _cfr_state(context):
    return context.user_data.setdefault("cfr_flow", {})


async def cfr_add_callback(update, context):
    """Entry: ➕ Add Custom Reviews — admin se review lines maango.
    (ConversationHandler entry — CFR_LINES return karta hai taake agla TEXT
    message cfr_lines_received catch kare.)"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data["cfr_lines"] = []
    await q.edit_message_text(
        "➕ *Add Custom Reviews*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send your reviews — *each line is one review*:\n\n"
        "Osm 😍\n"
        "Excellent 🔥\n"
        "Nice product 🪪\n\n"
        "✅ Premium emojis allowed\n"
        "✅ The bot creates a fake profile for every review\n"
        "(random 3–5 ⭐, fake name + ID)\n"
        "✅ Reviews are broadcast to the destination at random times\n"
        "(each review exactly once)\n\n"
        "_(/cancel to cancel)_",
        parse_mode="Markdown")
    return CFR_LINES


async def cfr_lines_received(update, context):
    """Admin ne lines bheje → categories dikhao."""
    if update.effective_user.id != ADMIN_ID:
        return None
    text = (update.message.text or "").strip()
    if text.startswith("/"):
        return None
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        await update.message.reply_text("❌ No lines found. Please try again.")
        return None
    if len(lines) > 100:
        lines = lines[:100]
    context.user_data["cfr_lines"] = lines
    # categories dikhao (enabled + jo products rakhti hain)
    from database import get_connection
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("""SELECT cat.id, cat.name,
                            (SELECT COUNT(*) FROM products p
                             WHERE p.category_id=cat.id AND p.is_active=1) AS pc
                     FROM categories cat
                     WHERE cat.is_active=1 AND cat.is_hidden=0
                     ORDER BY pc DESC, cat.display_order ASC, cat.id ASC LIMIT 40""")
        cats = [dict(r) for r in c.fetchall()]
    except Exception:
        # older schema fallback: hidden column na ho to
        c.execute("""SELECT cat.id, cat.name,
                            (SELECT COUNT(*) FROM products p
                             WHERE p.category_id=cat.id AND p.is_active=1) AS pc
                     FROM categories cat WHERE cat.is_active=1
                     ORDER BY pc DESC, cat.id ASC LIMIT 40""")
        cats = [dict(r) for r in c.fetchall()]
    finally:
        try: conn.close()
        except Exception: pass
    if not cats:
        await update.message.reply_text("❌ No categories found.")
        return None
    from utils import html_strip_tags, escape_md
    lines_txt = [f"✅ *{len(lines)} reviews* saved — now choose a product:", ""]
    kb = []
    for cat in cats:
        pc = int(cat.get("pc") or 0)
        if pc <= 0:
            continue
        cname = escape_md(html_strip_tags(str(cat.get("name") or "?"))[:28])
        kb.append([InlineKeyboardButton(
            f"📂 {html_strip_tags(str(cat.get('name') or '?'))[:30]} ({pc})",
            callback_data=f"cfr_cat_{cat['id']}")])
    if not kb:
        await update.message.reply_text("❌ No category has any products.")
        return None
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="cfr_cancel")])
    await update.message.reply_text("\n".join(lines_txt), parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(kb))
    return None


async def cfr_cat_callback(update, context):
    """Category select → us ke products dikhao."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        cat_id = int(q.data.replace("cfr_cat_", ""))
    except Exception:
        return
    _cfr_state(context)["cat_id"] = cat_id
    from database import get_connection
    from utils import html_strip_tags
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT id, name, stock FROM products
                 WHERE category_id=? AND is_active=1 ORDER BY id LIMIT 60""", (cat_id,))
    prods = [dict(r) for r in c.fetchall()]
    conn.close()
    if not prods:
        await q.edit_message_text("❌ No active products in this category.",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("🔙 Back", callback_data="cfr_add")]]))
        return
    kb = []
    for p in prods:
        try:
            from button_system import extract_emoji_from_html
            _eid, plain = extract_emoji_from_html(p.get("name") or "")
            nm = (plain or html_strip_tags(p.get("name") or "?"))[:32]
        except Exception:
            nm = html_strip_tags(p.get("name") or "?")[:32]
        stock = int(p.get("stock") or 0)
        kb.append([InlineKeyboardButton(
            f"📦 {nm} [{'🟢' if stock > 0 else '🔴'}]",
            callback_data=f"cfr_prod_{p['id']}")])
    kb.append([InlineKeyboardButton("🔙 Categories", callback_data="cfr_cats_back")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="cfr_cancel")])
    await q.edit_message_text(
        f"✅ *{len(context.user_data.get('cfr_lines') or [])} reviews* — product select karo:",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cfr_cats_back_callback(update, context):
    """Wapas categories dikhane ke liye lines dobara se render (cached)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    # reuse cfr_cat flow ka renderer — fake update se dobara categories
    from database import get_connection
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("""SELECT cat.id, cat.name,
                            (SELECT COUNT(*) FROM products p
                             WHERE p.category_id=cat.id AND p.is_active=1) AS pc
                     FROM categories cat
                     WHERE cat.is_active=1 AND cat.is_hidden=0
                     ORDER BY pc DESC, cat.display_order ASC, cat.id ASC LIMIT 40""")
        cats = [dict(r) for r in c.fetchall()]
    except Exception:
        c.execute("""SELECT cat.id, cat.name,
                            (SELECT COUNT(*) FROM products p
                             WHERE p.category_id=cat.id AND p.is_active=1) AS pc
                     FROM categories cat WHERE cat.is_active=1
                     ORDER BY pc DESC, cat.id ASC LIMIT 40""")
        cats = [dict(r) for r in c.fetchall()]
    finally:
        try: conn.close()
        except Exception: pass
    from utils import html_strip_tags
    kb = []
    for cat in cats:
        pc = int(cat.get("pc") or 0)
        if pc <= 0:
            continue
        kb.append([InlineKeyboardButton(
            f"📂 {html_strip_tags(str(cat.get('name') or '?'))[:30]} ({pc})",
            callback_data=f"cfr_cat_{cat['id']}")])
    if not kb:
        kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cfr_cancel")]]
    else:
        kb.append([InlineKeyboardButton("❌ Cancel", callback_data="cfr_cancel")])
    await q.edit_message_text(
        f"✅ *{len(context.user_data.get('cfr_lines') or [])} reviews* — product choose karo:",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cfr_prod_callback(update, context):
    """Product tap → SARI reviews add + confirm."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("cfr_prod_", ""))
    except Exception:
        return
    lines = context.user_data.get("cfr_lines") or []
    if not lines:
        await q.edit_message_text("❌ Reviews missing — please add them again.",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("➕ Add Reviews", callback_data="cfr_add")]]))
        return
    from database import get_product
    p = get_product(pid)
    if not p:
        await q.edit_message_text("❌ Product not found.")
        return
    pd = dict(p)
    from utils import html_strip_tags, escape_md
    try:
        from button_system import extract_emoji_from_html
        _eid, plain = extract_emoji_from_html(pd.get("name") or "")
        nm = plain or html_strip_tags(pd.get("name") or "?")
    except Exception:
        nm = html_strip_tags(pd.get("name") or "?")
    inserted, skipped = add_custom_reviews(pid, lines, product_name=nm)
    # 🆕 v170.94: naye reviews a gaye → broadcast chain start (agar already
    # chal rahi ho to dedup guard skip kar dega)
    try:
        _reschedule(context.application)
    except Exception:
        pass
    context.user_data.pop("cfr_lines", None)
    context.user_data.pop("cfr_flow", None)
    await q.edit_message_text(
        f"✅ *Reviews Added!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Product: *{escape_md(nm[:40])}*\n"
        f"➕ Inserted: *{inserted}* reviews (fake profiles + 3–5⭐)\n"
        f"📤 Broadcast queue: *{pending_queue_count()}* pending — they will be\n"
        f"broadcast to the destination at random times (each review exactly once).",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📋 Queue Status", callback_data="cfr_queue")],
             [InlineKeyboardButton("🔙 Fake Activity Panel", callback_data="act_panel")]]))


async def cfr_cancel_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data.pop("cfr_lines", None)
    context.user_data.pop("cfr_flow", None)
    await q.edit_message_text("❌ Cancelled.",
                              reply_markup=InlineKeyboardMarkup(
                                  [[InlineKeyboardButton("🔙 Fake Activity Panel",
                                                         callback_data="act_panel")]]))


async def cfr_queue_callback(update, context):
    """Queue status: pending/sent + recent entries."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    _ensure_queue_table()
    from database import get_connection
    from utils import html_strip_tags, escape_md
    conn = get_connection(); c = conn.cursor()
    pend = int(c.execute("SELECT COUNT(*) FROM custom_review_queue WHERE status='pending'").fetchone()[0] or 0)
    sent = int(c.execute("SELECT COUNT(*) FROM custom_review_queue WHERE status='sent'").fetchone()[0] or 0)
    c.execute("""SELECT crq.*, p.name AS pname FROM custom_review_queue crq
                 LEFT JOIN products p ON p.id=crq.product_id
                 ORDER BY crq.id DESC LIMIT 8""")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    from utils import escape_md as _em
    text = (
        f"📋 *Custom Review Broadcast Queue*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ Pending: *{pend}*  |  ✅ Sent: *{sent}*\n\n")
    if rows:
        text += "*Recent:*\n"
        for r in rows:
            st = {"pending": "⏳", "sending": "📤", "sent": "✅"}.get(r.get("status"), "❔")
            try:
                from button_system import extract_emoji_from_html
                _e, plain = extract_emoji_from_html(r.get("pname") or "")
                nm = plain or html_strip_tags(r.get("pname") or "?")
            except Exception:
                nm = html_strip_tags(r.get("pname") or "?")
            text += (f"{st} {r.get('fake_name', '?')[:18]} → {_em(str(nm)[:22])}: "
                     f"\"{_em(str(r.get('review_text') or '')[:36])}\"\n")
    else:
        text += "_(queue is empty — add some via ➕ Add Custom Reviews)_"
    kb = [[InlineKeyboardButton("🗑️ Clear Pending Queue", callback_data="cfr_clear")],
          [InlineKeyboardButton("🔙 Fake Activity Panel", callback_data="act_panel")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cfr_clear_callback(update, context):
    """Pending queue clear (sent history rehne do)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    _ensure_queue_table()
    from database import get_connection
    conn = get_connection(); c = conn.cursor()
    c.execute("DELETE FROM custom_review_queue WHERE status='pending'")
    n = c.rowcount
    conn.commit(); conn.close()
    await q.answer(f"🗑️ {n} pending broadcast(s) hata diye", show_alert=False)
    await cfr_queue_callback(update, context)
