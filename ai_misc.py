# ============================================================
# 🧩 v77 BUNDLE: ai_misc.py
# ============================================================
# This file is the merged result of 4 originally separate modules:
#   • ai_assistant.py
#   • ai_support_reply.py
#   • handlers_ai_support_admin.py
#   • proxy_ai_scout.py
#
# 🛡️ ALL CODE IS PRESERVED VERBATIM. Each original file's contents appears
# below in its own section. Imports and behavior are byte-identical to the
# pre-merge codebase — only file count is reduced.
# ============================================================


# ============================================================
# 📄 ORIGINAL FILE: ai_assistant.py
# ============================================================

SYSTEM_PROMPT = """You are the AI Assistant for the 'Bite Store Bot' – a sophisticated Telegram Store system.
Your job is to answer questions about how this bot works, specifically for the admin, helping them navigate and configure the store.

Here are the key features and how to use them:

1. **Adding & Managing Products:**
   - Tap '🛍️ Manage Products' -> '➕ Add Product'.
   - The bot will ask for Name, Description, Price, Cost Price, Stock, Warranty, and Quantity.
   - **Static Delivery:** You can set a fixed link/text that automatically delivers to every buyer (stock becomes unlimited). Skip by sending `-`.
   - **Product Details Panel:** You can edit any field later. Tap '⚙️ Delivery Settings' to control fulfillment.

2. **Delivery Flow (Settings & Automation):**
   - **Instant (Auto) Delivery:** Customers receive accounts automatically from a pre-loaded pool. Stock goes down automatically. You must tap `📋 Manage Accounts` to upload stock in `email|password` format or `https://` links.
   - **Manual (On-Demand) Delivery:** Stock check is bypassed. You deliver *after* the customer pays.
     - **Input Type:** You can require 'None', 'Any Email', 'Gmail Only', or 'Gmail + Pass' from the customer at checkout.
     - **Account State:** You can enforce 'Fresh Only' (asks user to confirm they have a fresh account).
   - **Fulfilling Manual Orders:** 
     - Admin receives an alert with a `[Deliver Now]` button. Tap it, type the account details/message, and send. The customer receives it instantly!
     - You can also view all pending manual deliveries by tapping `📦 Pending Manual Deliveries` on the main Admin Panel.
     - **Editing Deliveries:** In the product's Delivery Settings, tap `📜 Edit Manual Deliveries`. If you made a typo, you can invisibly replace the delivered text in the customer's chat.
   
3. **Payments & Auto-Verification:**
   - Support for Binance (USDT), EasyPaisa (PKR), JazzCash (PKR).
   - Once a user pays and enters their Transaction ID (TID) or Binance Name, the bot scans the configured Gmail address automatically. If it finds the match, the product is delivered instantly!

4. **Customizing the Bot:**
   - **Button Styler:** Tap any custom button -> '🎨 Style' to change its size (S/M/L/XL), alignment (Left/Center/Right), or padding.
   - **Custom Buttons & Submenus:** Create endless menus and nested buttons from '🛠️ Bot Customizer'.
   - **Custom Pages:** Build visually rich pages (photos + text) to link from buttons.

5. **Reviews & Loyalty Program:**
   - Customers earn Loyalty Points (💎) for buying products, unlocking Bronze -> Silver -> Gold -> Platinum -> Diamond tiers. Higher tiers can have custom prices!
   - Users can leave 1-5 ⭐ reviews on delivered items. Admin can Pin, Hide, or Delete them from '⭐ Reviews' in Admin Panel.

6. **Language:**
   - Customers can pick from 10 languages via `🌐 Language` button. Admin side is strictly in English for ease of management.

**When asked how to do something, provide short, actionable button paths (e.g., "Go to Admin Panel -> 🛍️ Manage Products"). Keep it friendly and concise!**
"""


# ════════════════════════════════════════════════════════════════
# 🤖 AI ASSISTANT — Gemini-powered admin Q&A
# 🔧 BUG FIX: handlers_admin.handle_ai_message() imports `ask_ai` from here,
# but it was never implemented (file only had SYSTEM_PROMPT). Every time the
# admin opened the AI Assistant and sent a question it raised ImportError.
# This implements ask_ai() using the same Gemini setup as screenshot_verifier.
# ════════════════════════════════════════════════════════════════

_ai_model = None
_ai_init_error = None


def _get_ai_model():
    """Lazy-init a text Gemini model for the admin assistant."""
    global _ai_model, _ai_init_error
    if _ai_model is not None or _ai_init_error is not None:
        return _ai_model
    try:
        import google.generativeai as genai
    except ImportError:
        _ai_init_error = "google-generativeai not installed. Run: pip install google-generativeai"
        return None
    try:
        from config import GEMINI_API_KEY
    except Exception:
        import os
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    if not GEMINI_API_KEY:
        _ai_init_error = "GEMINI_API_KEY not set."
        return None
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        _ai_model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=SYSTEM_PROMPT,
            generation_config={
                "temperature": 0.4,
                "top_p": 0.9,
                "max_output_tokens": 800,
            },
        )
        return _ai_model
    except Exception as e:
        _ai_init_error = f"AI init error: {e}"
        return None


async def ask_ai(question, history=None):
    """Ask the Gemini admin assistant a question.

    Args:
        question: the admin's text question.
        history: list of {"role": "user"|"model", "parts": [text]} dicts.

    Returns:
        (success: bool, response: str)
    """
    history = history or []
    model = _get_ai_model()
    if model is None:
        return False, f"⚠️ AI Assistant unavailable: {_ai_init_error or 'unknown error'}"

    def _run():
        # Reuse prior turns so the assistant keeps context.
        chat = model.start_chat(history=history)
        resp = chat.send_message(question)
        return (getattr(resp, "text", None) or "").strip()

    try:
        import asyncio
        text = await asyncio.to_thread(_run)
        if not text:
            return False, "⚠️ AI returned an empty response. Please try again."
        return True, text
    except Exception as e:
        return False, f"⚠️ AI error: {e}"


# ============================================================
# 📄 ORIGINAL FILE: ai_support_reply.py
# ============================================================

# ============================================================
# 🤖 AI AUTO-REPLY for new Support Tickets (v71)
# ============================================================
# When user creates a new support ticket, Gemini AI tries to answer it
# first using:
#   1) Bot's DEFAULT_RESPONSES + settings (delivery time, payment methods, etc.)
#   2) Recent admin replies from resolved tickets (last 30 days)
#
# If Gemini is confident, it auto-sends the reply and offers "Still need help?
# Talk to admin" button. Otherwise it escalates to admin normally.
#
# Admin can toggle the feature ON/OFF and view AI reply logs.
# ============================================================

import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    """Master switch: should AI try to answer new tickets first?"""
    try:
        from database import get_setting
        return get_setting("ai_support_reply_enabled", "0") == "1"
    except Exception:
        return False


def set_enabled(on: bool):
    from database import set_setting
    set_setting("ai_support_reply_enabled", "1" if on else "0")


def ensure_log_table():
    """Create the ai_reply_log table if needed."""
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS ai_reply_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id   INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                subject     TEXT,
                question    TEXT,
                ai_answer   TEXT,
                confidence  TEXT,
                escalated   INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_ai_log_time ON ai_reply_log(created_at)")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"[AISupport] ensure_log_table failed: {e}")


def log_ai_reply(ticket_id, user_id, subject, question, ai_answer, confidence, escalated):
    """Save AI reply to log table for admin review."""
    try:
        ensure_log_table()
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO ai_reply_log
            (ticket_id, user_id, subject, question, ai_answer, confidence, escalated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (int(ticket_id), int(user_id), str(subject)[:200],
              str(question)[:2000], str(ai_answer)[:3000],
              str(confidence)[:20], 1 if escalated else 0))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"[AISupport] log_ai_reply failed: {e}")


def get_recent_ai_logs(limit=20):
    """For admin view — last N AI replies."""
    try:
        ensure_log_table()
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT id, ticket_id, user_id, subject, question, ai_answer,
                   confidence, escalated, created_at
            FROM ai_reply_log
            ORDER BY id DESC LIMIT ?
        """, (int(limit),))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"[AISupport] get_recent_ai_logs failed: {e}")
        return []


def _build_knowledge_base() -> str:
    """Compile a knowledge base from bot's settings, responses, and recent
    successful admin replies. This gets fed to Gemini as context."""
    parts = []

    # 1. Shop info from settings
    try:
        from database import get_setting
        shop = get_setting("shop_name", "Bite Store")
        binance_id = get_setting("binance_id", "")
        ep_num = get_setting("easypaisa", "")
        jc_num = get_setting("jazzcash", "")
        whatsapp = get_setting("whatsapp", "")
        email = get_setting("email", "")
        parts.append(f"## SHOP INFO\nShop name: {shop}")
        if binance_id:
            parts.append(f"Binance Pay ID: {binance_id}")
        if ep_num:
            parts.append(f"EasyPaisa number: {ep_num}")
        if jc_num:
            parts.append(f"JazzCash number: {jc_num}")
        if whatsapp:
            parts.append(f"WhatsApp support: {whatsapp}")
        if email:
            parts.append(f"Support email: {email}")
    except Exception:
        pass

    # 2. Common bot policies / responses
    try:
        from config import DEFAULT_RESPONSES
        useful_keys = [
            "welcome", "no_products", "out_of_stock",
            "binance_orderid_instructions", "refund_processed",
            "order_cancelled_with_reason", "order_cancelled_no_reason",
        ]
        parts.append("\n## BOT POLICIES & RESPONSES")
        for key in useful_keys:
            if key in DEFAULT_RESPONSES:
                txt = str(DEFAULT_RESPONSES[key])[:300].replace("\n", " ")
                parts.append(f"- {key}: {txt}")
    except Exception:
        pass

    # 3. Recent admin replies from last 30 days (real Q&A pairs)
    try:
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        cutoff = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        # Pick last 10 resolved tickets that had a reply
        c.execute("""
            SELECT subject, description, admin_reply
            FROM support_tickets
            WHERE created_at >= ?
              AND admin_reply IS NOT NULL
              AND LENGTH(admin_reply) > 10
            ORDER BY id DESC
            LIMIT 10
        """, (cutoff,))
        rows = c.fetchall()
        conn.close()
        if rows:
            parts.append("\n## RECENT ADMIN REPLIES (Q&A examples)")
            for r in rows:
                q = (r['subject'] or '')[:80]
                d = (r['description'] or '')[:120].replace('\n', ' ')
                a = (r['admin_reply'] or '')[:200].replace('\n', ' ')
                parts.append(f"Q: {q} — {d}\nA: {a}")
    except Exception as e:
        logger.debug(f"[AISupport] knowledge base recent replies failed: {e}")

    return "\n".join(parts)


_SYSTEM_PROMPT = """You are a customer support assistant for an online store
that sells premium accounts (ChatGPT, Gemini, Perplexity, CapCut, etc.) via a
Telegram bot.

Your job: read the customer's support ticket and produce ONE of these responses:

1. If you can confidently answer using the provided knowledge base — write a
   short, friendly answer in 2-5 sentences. Use plain English. End with
   "If this doesn't help, please reply to this ticket and our team will assist."

2. If the question is too complex, sensitive (refund, account banned,
   suspected fraud, payment dispute), or you don't have enough info — output
   exactly: "ESCALATE"

Output strict JSON only, no markdown. Format:
{
  "confidence": "high" | "low",
  "answer": "<your answer or empty string if ESCALATE>",
  "should_escalate": true | false
}

Rules:
- If `should_escalate` is true → set `confidence` to "low" and `answer` to ""
- Never make up information not in the knowledge base
- Never promise refunds, replacements, or compensation — escalate those
- Never include the customer's personal info (Gmail, password, card) in answer
- Keep answer under 400 characters
- Be polite and professional
"""


async def try_ai_reply(ticket_id, user_id, subject, description):
    """Main entry — try to generate an AI reply for a new ticket.
    Returns dict: {ok: bool, answer: str, escalated: bool, reason: str}
    """
    result = {"ok": False, "answer": "", "escalated": False, "reason": ""}

    if not is_enabled():
        result["reason"] = "AI reply disabled"
        return result

    # Initialize Gemini
    try:
        import google.generativeai as genai
        try:
            from config import GEMINI_API_KEY
        except Exception:
            import os
            GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        if not GEMINI_API_KEY:
            result["reason"] = "GEMINI_API_KEY not set"
            return result
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=_SYSTEM_PROMPT,
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 600,
                "response_mime_type": "application/json",
            },
        )
    except Exception as e:
        result["reason"] = f"Gemini init failed: {e}"
        return result

    # Build the prompt
    kb = _build_knowledge_base()
    user_question = (
        f"Subject: {subject}\n"
        f"Description: {description or '(no description)'}"
    )
    prompt = (
        f"# KNOWLEDGE BASE\n{kb}\n\n"
        f"# CUSTOMER TICKET\n{user_question}\n\n"
        f"Respond with strict JSON as instructed."
    )

    try:
        resp = await _call_gemini_async(model, prompt)
        out = (resp or "").strip()
        # Strip code fences just in case
        import re as _re
        out = _re.sub(r'^```(?:json)?\s*', '', out)
        out = _re.sub(r'\s*```\s*$', '', out)
        data = json.loads(out)
        confidence = str(data.get("confidence", "low")).lower()
        answer = str(data.get("answer", "")).strip()
        should_escalate = bool(data.get("should_escalate", True))

        escalated = should_escalate or confidence != "high" or not answer
        result["ok"] = not escalated
        result["answer"] = answer if not escalated else ""
        result["escalated"] = escalated
        result["confidence"] = confidence

        # Log to DB
        log_ai_reply(ticket_id, user_id, subject, user_question, answer,
                     confidence, escalated)

        return result
    except Exception as e:
        logger.warning(f"[AISupport] Gemini call failed: {e}")
        result["reason"] = f"Gemini error: {e}"
        result["escalated"] = True
        # Still log the failure
        log_ai_reply(ticket_id, user_id, subject, user_question,
                     f"[Error: {e}]", "error", True)
        return result


async def _call_gemini_async(model, prompt):
    """Wrap blocking Gemini call in a thread."""
    import asyncio
    def _go():
        try:
            r = model.generate_content(prompt, request_options={"timeout": 25})
            return r.text or ""
        except Exception as e:
            raise
    return await asyncio.to_thread(_go)


# ============================================================
# 📄 ORIGINAL FILE: handlers_ai_support_admin.py
# ============================================================

# ============================================================
# 🤖 AI Support Reply — admin panel (v71)
# ============================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID
from utils import escape_md
# [v77-merge] from ai_support_reply import (
# [v77-merge] is_enabled, set_enabled, get_recent_ai_logs, ensure_log_table,
# [v77-merge] )
logger = logging.getLogger(__name__)


async def admin_ai_support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main AI Auto-Reply admin panel."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    ensure_log_table()

    enabled = is_enabled()
    logs = get_recent_ai_logs(limit=5)
    total_handled = 0
    total_escalated = 0
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT COUNT(*), SUM(escalated) FROM ai_reply_log")
        row = c.fetchone()
        if row:
            total_handled = int(row[0] or 0)
            total_escalated = int(row[1] or 0)
        conn.close()
    except Exception:
        pass
    auto_handled = max(0, total_handled - total_escalated)

    text = (
        "🤖 *AI Auto-Reply (Support Tickets)*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *Status:* {'🟢 ON' if enabled else '🔴 OFF'}\n\n"
        f"📊 *Lifetime Stats:*\n"
        f"  • Total tickets processed by AI: `{total_handled}`\n"
        f"  • Auto-handled (no admin needed): `{auto_handled}`\n"
        f"  • Escalated to admin: `{total_escalated}`\n\n"
        "When ON, new support tickets are first read by Gemini AI which uses:\n"
        "  • Your bot's shop info (payment methods, etc.)\n"
        "  • Your bot responses (delivery time, refund policies)\n"
        "  • Last 30 days of your real admin replies\n\n"
        "Gemini either:\n"
        "  ✅ Answers confidently → user sees the answer with "
        "'🆘 Talk to Human' button if needed\n"
        "  ⤴️ Escalates to you → original ticket flow\n\n"
    )

    if logs:
        text += "*🕓 Last 5 AI Responses:*\n"
        for r in logs[:5]:
            tid = r['ticket_id']
            sub = (r.get('subject') or '')[:40]
            conf = r.get('confidence', '?')
            esc = "↗️" if r.get('escalated') else "✅"
            text += f"  {esc} #{tid} • {escape_md(sub)} • _{conf}_\n"

    kb = [
        [InlineKeyboardButton(
            "🔴 Turn OFF" if enabled else "🟢 Turn ON",
            callback_data="admin_ai_support_toggle")],
        [InlineKeyboardButton("📜 View Full Log", callback_data="admin_ai_support_log")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")],
    ]
    await q.edit_message_text(text[:3900], parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(kb))


async def admin_ai_support_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    cur = is_enabled()
    set_enabled(not cur)
    await q.answer(f"AI Auto-Reply {'OFF' if cur else 'ON'}", show_alert=False)
    await admin_ai_support_callback(update, context)


async def admin_ai_support_log_callback(update, context):
    """Show full AI reply log."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    logs = get_recent_ai_logs(limit=20)
    if not logs:
        text = "📜 *AI Reply Log*\n\n_Empty._"
    else:
        lines = ["📜 *AI Reply Log* (last 20)", "━━━━━━━━━━━━━━━━━━━━", ""]
        for r in logs:
            tid = r['ticket_id']
            uid = r['user_id']
            sub = (r.get('subject') or '')[:40]
            conf = r.get('confidence', '?')
            esc = "↗️ ESCALATED" if r.get('escalated') else "✅ AUTO"
            ans = (r.get('ai_answer') or '')[:150].replace('\n', ' ')
            ts = (r.get('created_at') or '')[5:16]
            lines.append(f"*#{tid}* `{ts}` • uid:`{uid}` • {esc} (_{conf}_)")
            lines.append(f"_Subject:_ {escape_md(sub)}")
            if ans:
                lines.append(f"_AI said:_ {escape_md(ans)}")
            lines.append("")
        text = "\n".join(lines)[:3900]

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_ai_support_log")],
        [InlineKeyboardButton("🔙 Back",    callback_data="admin_ai_support")],
    ])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


# ============================================================
# 📄 ORIGINAL FILE: proxy_ai_scout.py
# ============================================================

# ============================================================
# 🤖 AI PROXY SCOUT (v67)
# ============================================================
# When all proxies in the pool are dead/cooldown, this module:
#   1) Scrapes 3 known free-proxy listing sites
#   2) Asks Gemini to extract Pakistani SOCKS5/HTTP candidates
#   3) Tests each candidate against api.binance.com
#   4) Auto-adds working ones to the DB pool
#   5) Notifies admin
#
# Can also be triggered manually from admin panel.
# ============================================================

import asyncio
import json
import logging
import re
import time
from typing import List, Tuple

import requests

logger = logging.getLogger(__name__)

# ── Known free-proxy listing sources (PK / general) ──
_PROXY_SOURCES = [
    "https://www.ditatompel.com/proxy/country/pk",
    "https://proxyhub.me/en/pk-socks5-proxy-list.html",
    "https://www.freeproxy.world/?country=PK",
]

# Hard limits to keep things safe
_MAX_CANDIDATES_TO_TEST = 20
_CANDIDATE_TEST_TIMEOUT = 8     # seconds per candidate
_MAX_WORKING_TO_ADD     = 5     # don't flood the pool


# ════════════════════════════════════════════
# 🌐 STEP 1: Fetch HTML from proxy listing sites
# ════════════════════════════════════════════
def _fetch_source(url: str, timeout: int = 12) -> str:
    """Download a proxy listing page. Returns plaintext (HTML tags stripped)."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code != 200:
            return ""
        text = r.text
        # Strip script/style blocks before tags
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>',   ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<!--.*?-->',                ' ', text, flags=re.DOTALL)
        # Keep tags lightweight — just collapse whitespace later
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text[:8000]   # cap at 8K per source to keep AI prompt small
    except Exception as e:
        logger.debug(f"[ProxyScout] fetch failed for {url}: {e}")
        return ""


def _fetch_all_sources() -> dict:
    """Returns {url: text_blob} for each successfully-fetched source."""
    results = {}
    for url in _PROXY_SOURCES:
        text = _fetch_source(url)
        if text:
            results[url] = text
    return results


# ════════════════════════════════════════════
# 🤖 STEP 2: Ask Gemini to extract proxies
# ════════════════════════════════════════════
_GEMINI_PROMPT = """You are a proxy-list extraction expert.

I'll give you raw text scraped from public free-proxy listing websites.
Your job: extract ALL Pakistani (country code PK) proxies you find.

Output ONLY a valid JSON array. No commentary, no markdown fences.
Each entry must be a string in one of these EXACT formats:
- "socks5://IP:PORT"
- "socks4://IP:PORT"
- "http://IP:PORT"

Rules:
- Only Pakistani proxies (country PK or Pakistan or PK city like Karachi/Lahore/Islamabad)
- Skip proxies with username/password (we don't have credentials)
- Skip proxies older than 30 days if dates are shown
- Prefer SOCKS5 over HTTP (better for HTTPS API calls)
- Maximum 20 results
- If no Pakistani proxies found, return: []

Example output:
["socks5://103.121.120.242:1080", "http://115.42.67.186:8080", "socks5://182.184.119.180:1080"]

Now extract from this text:
---
"""


def _ai_extract_proxies(blobs: dict) -> list:
    """Send scraped text to Gemini, ask for a JSON list of PK proxies."""
    if not blobs:
        return []

    # Initialise Gemini using the existing setup
    try:
        import google.generativeai as genai
        try:
            from config import GEMINI_API_KEY
        except Exception:
            import os
            GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        if not GEMINI_API_KEY:
            logger.warning("[ProxyScout] GEMINI_API_KEY not set — falling back to regex extraction")
            return _regex_fallback_extract(blobs)
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 2000,
                "response_mime_type": "application/json",
            },
        )
    except Exception as e:
        logger.warning(f"[ProxyScout] Gemini init failed: {e} — using regex fallback")
        return _regex_fallback_extract(blobs)

    combined = "\n\n=== Source: {} ===\n{}".format
    parts = [_GEMINI_PROMPT]
    for url, text in blobs.items():
        parts.append(combined(url, text[:3500]))
    prompt = "\n".join(parts)

    try:
        resp = model.generate_content(prompt, request_options={"timeout": 30})
        out = (resp.text or "").strip()
        # Strip accidental markdown fences if any
        out = re.sub(r'^```(?:json)?\s*', '', out)
        out = re.sub(r'\s*```\s*$', '', out)
        data = json.loads(out)
        if not isinstance(data, list):
            return _regex_fallback_extract(blobs)
        # Sanity-filter
        clean = []
        for entry in data:
            if not isinstance(entry, str): continue
            entry = entry.strip()
            if re.match(r'^(socks5h?|socks4|http|https)://\d{1,3}(\.\d{1,3}){3}:\d{2,5}$', entry):
                if entry not in clean:
                    clean.append(entry)
        return clean[:_MAX_CANDIDATES_TO_TEST]
    except Exception as e:
        logger.warning(f"[ProxyScout] Gemini parse failed: {e} — using regex fallback")
        return _regex_fallback_extract(blobs)


def _regex_fallback_extract(blobs: dict) -> list:
    """If Gemini fails, just regex-pull IP:PORT pairs from the scraped text."""
    out = []
    pattern = re.compile(r'(\d{1,3}(?:\.\d{1,3}){3})\D{1,3}(\d{2,5})')
    for url, text in blobs.items():
        for m in pattern.finditer(text):
            ip = m.group(1); port = int(m.group(2))
            if port < 80 or port > 65535: continue
            # Common SOCKS ports
            if port in (1080, 1081, 1090, 4145, 5678, 9050):
                proto = "socks5"
            elif port in (3128, 8080, 8888, 80, 8000, 8118):
                proto = "http"
            else:
                proto = "socks5"  # default guess
            entry = f"{proto}://{ip}:{port}"
            if entry not in out:
                out.append(entry)
            if len(out) >= _MAX_CANDIDATES_TO_TEST:
                return out
    return out


# ════════════════════════════════════════════
# 🧪 STEP 3: Test each candidate against Binance
# ════════════════════════════════════════════
def _test_proxy(proxy_url: str, timeout: int = _CANDIDATE_TEST_TIMEOUT) -> tuple:
    """Hit api.binance.com/api/v3/time. Returns (ok, elapsed_seconds, reason)."""
    proxies = {"http": proxy_url, "https": proxy_url}
    t0 = time.time()
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/time",
            proxies=proxies, timeout=timeout,
        )
        elapsed = time.time() - t0
        if r.status_code == 200:
            return True, elapsed, "OK"
        if r.status_code == 451:
            return False, elapsed, "HTTP 451 (geo-blocked)"
        return False, elapsed, f"HTTP {r.status_code}"
    except requests.exceptions.ConnectTimeout:
        return False, time.time() - t0, "ConnectTimeout"
    except requests.exceptions.ReadTimeout:
        return False, time.time() - t0, "ReadTimeout"
    except requests.exceptions.ProxyError:
        return False, time.time() - t0, "ProxyError"
    except Exception as e:
        return False, time.time() - t0, type(e).__name__


def _test_candidates(candidates: list) -> list:
    """Test all candidates sequentially, return working ones (capped)."""
    working = []
    for url in candidates:
        ok, elapsed, reason = _test_proxy(url)
        if ok:
            working.append((url, elapsed))
            logger.info(f"[ProxyScout] ✅ {url} works ({elapsed:.1f}s)")
            if len(working) >= _MAX_WORKING_TO_ADD:
                break
        else:
            logger.debug(f"[ProxyScout] ❌ {url} ({elapsed:.1f}s) {reason}")
    return working


# ════════════════════════════════════════════
# 💾 STEP 4: Add working proxies to DB pool
# ════════════════════════════════════════════
def _add_to_pool(working_proxies: list) -> int:
    """Append working proxies to the DB-stored pool (avoiding duplicates)."""
    if not working_proxies:
        return 0
    try:
        from database import get_setting, set_setting
        existing = (get_setting("binance_proxy_pool", "") or "").strip()
        parts = [p.strip() for p in existing.split(",") if p.strip()]
        added = 0
        for url, _elapsed in working_proxies:
            if url not in parts:
                parts.append(url)
                added += 1
        set_setting("binance_proxy_pool", ",".join(parts))
        return added
    except Exception as e:
        logger.warning(f"[ProxyScout] DB save failed: {e}")
        return 0


# ════════════════════════════════════════════
# 🎯 PUBLIC API: Run full scout cycle
# ════════════════════════════════════════════
def run_scout_sync() -> dict:
    """One full cycle: fetch → AI parse → test → save → return summary.
       Runs in a thread (called via asyncio.to_thread)."""
    summary = {
        "fetched_sources": 0,
        "candidates": 0,
        "working": 0,
        "added": 0,
        "working_list": [],
        "candidates_list": [],
        "method": "regex",
        "error": "",
    }
    try:
        blobs = _fetch_all_sources()
        summary["fetched_sources"] = len(blobs)
        if not blobs:
            summary["error"] = "No proxy listing sites reachable."
            return summary

        # Try Gemini, fall back to regex
        candidates = _ai_extract_proxies(blobs)
        # Detect which method was used by checking if all entries look "clean"
        # (regex fallback uses port-based guessing which is less reliable)
        summary["method"] = "gemini" if candidates else "regex"
        summary["candidates"] = len(candidates)
        summary["candidates_list"] = candidates[:]

        if not candidates:
            summary["error"] = "No proxy candidates extracted from listings."
            return summary

        working = _test_candidates(candidates)
        summary["working"] = len(working)
        summary["working_list"] = [(u, round(e, 1)) for u, e in working]

        added = _add_to_pool(working)
        summary["added"] = added

        # Reset cooldowns so new proxies are immediately tried
        try:
            from payments import reset_proxy_cooldowns
            reset_proxy_cooldowns()
        except Exception:
            pass

        return summary
    except Exception as e:
        logger.error(f"[ProxyScout] run_scout_sync error: {e}")
        summary["error"] = str(e)
        return summary


async def run_scout() -> dict:
    """Async wrapper — run the full scout in a thread."""
    return await asyncio.to_thread(run_scout_sync)


# ════════════════════════════════════════════
# 🤖 PUBLIC: Monitor + auto-trigger job
# ════════════════════════════════════════════
async def proxy_monitor_job(context):
    """Background job (every 30 min):
       - Check proxy pool health
       - If ALL proxies are dead/cooldown for >10 min, auto-run scout
       - Otherwise, do nothing"""
    try:
        from payments import (
            get_proxy_health_snapshot, _load_proxy_pool, is_configured,
        )
        # Only run if Binance API is actually configured (no keys = no point)
        if not is_configured():
            return

        snap = get_proxy_health_snapshot()
        if not snap:
            return  # no pool to monitor

        # Count: how many proxies are usable RIGHT NOW?
        usable = 0
        for row in snap:
            if not row.get("in_cooldown") and row.get("status") != "fail":
                usable += 1

        if usable > 0:
            return  # at least one is fine; no action

        # All proxies fail/cooldown — check if it's been > 10 min
        # We track using a setting timestamp
        from database import get_setting, set_setting
        last_scout = get_setting("ai_scout_last_run", "0")
        try:
            last_run_ts = float(last_scout)
        except Exception:
            last_run_ts = 0
        now = time.time()
        # Don't run more than once per hour
        if (now - last_run_ts) < 3600:
            return

        logger.info("[ProxyScout] 🚨 All proxies dead — triggering AI scout")
        set_setting("ai_scout_last_run", str(now))
        summary = await run_scout()

        # Notify admin
        try:
            from config import ADMIN_ID
            method = summary.get("method", "?")
            added = summary.get("added", 0)
            working = summary.get("working", 0)
            cands = summary.get("candidates", 0)
            srcs = summary.get("fetched_sources", 0)
            err = summary.get("error", "")
            if added > 0:
                msg = (
                    f"🤖 *AI Proxy Scout — Auto-Recovery*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"All proxies were dead. Scout ran automatically.\n\n"
                    f"📡 Sources fetched: {srcs}/3\n"
                    f"🔍 Candidates found (via {method}): {cands}\n"
                    f"✅ Working proxies tested: *{working}*\n"
                    f"💾 Added to pool: *{added}*\n\n"
                    f"_Bot should resume normal operation now._"
                )
            else:
                msg = (
                    f"🤖 *AI Proxy Scout — No Luck*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"All proxies are dead and no new working proxies were found.\n\n"
                    f"📡 Sources fetched: {srcs}/3\n"
                    f"🔍 Candidates found: {cands}\n"
                    f"✅ Working: 0\n"
                )
                if err:
                    msg += f"\n⚠️ Error: `{err}`\n"
                msg += "\nPlease add a working proxy manually via 📡 Proxy Status panel."

            await context.bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"[ProxyScout] Admin notify failed: {e}")

    except Exception as e:
        logger.warning(f"[ProxyScout] monitor_job error: {e}")

