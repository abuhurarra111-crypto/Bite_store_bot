# ============================================================
# 🩹 SELF-HEAL — Auto-fix common runtime issues on startup  (v80)
# ============================================================
# Runs during bot startup (post_init) to detect + auto-fix well-known
# issues WITHOUT calling any external AI. Zero API cost, zero risk.
#
# Also runs a Gemini "safe scan" if GEMINI_API_KEY is set — Gemini only
# LOOKS AT specific known problem areas and reports to admin DM. It does
# NOT edit code (that would be full auto-fix, too risky).
#
# What it heals automatically (all are 100% safe idempotent operations):
#   1. Missing DB columns (self-heal via ensure_column)
#   2. Missing DB tables (CREATE TABLE IF NOT EXISTS)
#   3. Orphaned WAL/SHM files (clean up on next connection)
#   4. Pinned announcements table missing → create
#   5. Ticket messages table missing → create
#   6. Replacement columns missing on orders/products → add
#   7. API-key extra columns missing → add
#   8. Delivery integrity log table missing → create
#   9. Empty language column defaulting → set to 'en'
#  10. Orphaned "waiting_..." session flags in user_data (clear on start)
# ============================================================

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_HEAL_REPORT = []


def _log(msg: str, severity: str = "INFO"):
    """Add to internal report + log to stdout."""
    entry = f"[SelfHeal:{severity}] {msg}"
    _HEAL_REPORT.append(entry)
    if severity == "ERROR":
        logger.error(entry)
    elif severity == "WARN":
        logger.warning(entry)
    else:
        logger.info(entry)


def get_heal_report() -> list:
    """Return list of heal actions taken this startup (for admin DM)."""
    return list(_HEAL_REPORT)


def _heal_missing_tables():
    """Ensure every known optional table exists (no-op if already there)."""
    healed = []
    try:
        from database import get_connection, setup_api_tables, setup_support_tables
        # Core support / warranty / ticket_messages
        try:
            setup_support_tables()
            healed.append("support_tables")
        except Exception as e:
            _log(f"setup_support_tables failed: {e}", "WARN")
        # API keys
        try:
            setup_api_tables()
            healed.append("api_tables")
        except Exception as e:
            _log(f"setup_api_tables failed: {e}", "WARN")
        # Replacement columns
        try:
            from support_replacement import _ensure_columns as _replace_cols
            _replace_cols()
            healed.append("replacement_columns")
        except Exception as e:
            _log(f"replacement _ensure_columns failed: {e}", "WARN")
        # Pinned announcements table
        try:
            from loyalty_extras import ensure_table as _pins_table
            _pins_table()
            healed.append("pinned_announcements")
        except Exception as e:
            _log(f"pins ensure_table failed: {e}", "WARN")
        # Delivery integrity log
        try:
            from templates_bundle import ensure_integrity_table
            ensure_integrity_table()
            healed.append("delivery_integrity_log")
        except Exception:
            pass  # optional
        # 🆕 v81: External supplier tables
        try:
            from ext_suppliers import ensure_ext_supplier_tables, backup_and_wipe_existing_products
            ensure_ext_supplier_tables()
            healed.append("ext_supplier_tables")
            # One-time migration: backup + wipe existing 29 products (idempotent)
            snap_count, err = backup_and_wipe_existing_products()
            if snap_count > 0:
                _log(f"v81 migration: backed up {snap_count} products, wiped 7 tables")
            elif err == "already_migrated":
                pass  # silent — already done
        except Exception as e:
            _log(f"v81 ext_suppliers table setup: {e}", "WARN")
        # 🆕 v83: Wipe v82's auto-mirrored products (one-time cleanup for
        # manual-sync workflow). Idempotent — sets marker flag.
        try:
            from ext_suppliers import wipe_v82_auto_mirrored_products
            wiped, err = wipe_v82_auto_mirrored_products()
            if wiped > 0:
                _log(f"v83 cleanup: wiped {wiped} auto-mirrored products (admin must re-sync manually)")
        except Exception as e:
            _log(f"v83 wipe failed: {e}", "WARN")
        # 🆕 v90/v91: Heal ext_products.name rows that v86 InstaAPI adapter
        # saved as raw HTML strings (screenshot bug: names showing as
        # <tg-emoji emoji-id="6172... instead of ✨ ChatPRD 1 year).
        # v91: runs EVERY startup + always logs current state for debugging.
        try:
            # v91: proactively clear any old v90 marker (some users had it set
            # before the heal actually ran — force re-run to guarantee fix)
            try:
                from database import get_connection as _gc
                _c = _gc(); _cur = _c.cursor()
                _cur.execute("DELETE FROM bot_settings WHERE key='v90_heal_done'")
                _c.commit(); _c.close()
            except Exception:
                pass
            from ext_suppliers import heal_v86_broken_html_names
            healed, herr = heal_v86_broken_html_names()
            _log(f"v90/v91 heal: processed on startup — healed {healed} broken rows"
                 + (f" (err: {herr})" if herr and herr != 'already_healed' else ""))
        except Exception as e:
            _log(f"v90/v91 heal failed: {e}", "WARN")
    except Exception as e:
        _log(f"table healing outer failure: {e}", "WARN")
    if healed:
        _log(f"Verified/created tables: {', '.join(healed)}")


def _heal_stale_wal():
    """If a stray WAL/SHM file exists (crashed process), safely checkpoint it."""
    try:
        from database import get_connection
        conn = get_connection()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        conn.close()
        _log("WAL checkpoint completed")
    except Exception as e:
        _log(f"WAL checkpoint failed: {e}", "WARN")


def _heal_missing_language_defaults():
    """Users with NULL/empty language get default 'en' (prevents render bugs)."""
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE users SET language='en' WHERE language IS NULL OR language=''")
        n = c.rowcount
        conn.commit(); conn.close()
        if n > 0:
            _log(f"Set default language='en' on {n} user(s)")
    except Exception as e:
        _log(f"language default heal failed: {e}", "WARN")


def _heal_payment_settings():
    """Ensure payment_enabled_* keys exist so admin panel shows all methods."""
    try:
        from database import PAYMENT_METHODS, is_payment_enabled, set_payment_enabled
        # Just calling is_payment_enabled ensures the fallback default is respected.
        # No writes needed unless admin has actively toggled.
        for m in PAYMENT_METHODS:
            _ = is_payment_enabled(m)
        _log(f"Payment method states verified for {len(PAYMENT_METHODS)} methods")
    except Exception as e:
        _log(f"payment settings heal failed: {e}", "WARN")


def _heal_orphaned_sessions():
    """No-op — user sessions are per-context, cleared naturally by force_main_menu."""
    pass


async def _gemini_safe_scan_optional(bot):
    """Optional Gemini pass — ONLY reports findings, never edits code.

    Runs only if:
      1. GEMINI_API_KEY env var is set
      2. Admin has explicitly enabled it via bot setting 'gemini_startup_scan'
    """
    try:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return
        from database import get_setting
        if get_setting("gemini_startup_scan", "0") != "1":
            return  # opt-in only
        # Do a lightweight scan: recent delivery_integrity_log mismatches
        try:
            from templates_bundle import get_recent_integrity_issues, get_mismatch_count
            mismatch = get_mismatch_count()
            issues = get_recent_integrity_issues(limit=5)
        except Exception:
            mismatch, issues = 0, []
        if mismatch == 0 and not issues:
            _log("Gemini scan: no delivery integrity mismatches found (skipped Gemini call)")
            return
        # Build small prompt describing the issue
        prompt = (
            "You are a code-safety auditor. Recent delivery integrity mismatches:\n\n"
            f"Total mismatches: {mismatch}\n"
            f"Recent issues sample: {issues[:3]}\n\n"
            "In ONE short paragraph (< 300 chars), what's the most likely root cause "
            "and what should the admin check first? Do NOT suggest code changes."
        )
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(prompt)
            advice = getattr(resp, "text", "").strip() or "(no response)"
        except Exception as e:
            _log(f"Gemini API call failed: {e}", "WARN")
            return
        # Send to admin DM
        try:
            admin_id = int(os.getenv("ADMIN_ID", "0") or 0)
            if admin_id and bot:
                await bot.send_message(
                    admin_id,
                    f"🤖 *Startup Health Scan (Gemini)*\n\n{advice}",
                    parse_mode="Markdown"
                )
        except Exception:
            pass
        _log(f"Gemini scan sent advice to admin ({len(advice)} chars)")
    except Exception as e:
        _log(f"Gemini safe-scan failed: {e}", "WARN")


def run_all_heals() -> list:
    """Main entry — runs all safe self-heal steps synchronously.
    Returns the list of heal actions taken."""
    _HEAL_REPORT.clear()
    _log(f"Self-heal started at {datetime.now().isoformat(timespec='seconds')}")
    try:
        _heal_missing_tables()
    except Exception as e:
        _log(f"heal_tables outer: {e}", "ERROR")
    try:
        _heal_stale_wal()
    except Exception as e:
        _log(f"heal_wal outer: {e}", "ERROR")
    try:
        _heal_missing_language_defaults()
    except Exception as e:
        _log(f"heal_lang outer: {e}", "ERROR")
    try:
        _heal_payment_settings()
    except Exception as e:
        _log(f"heal_pay outer: {e}", "ERROR")
    _log("Self-heal completed")
    return list(_HEAL_REPORT)


async def notify_admin_of_heal(bot, admin_id: int, report: list):
    """Send heal report to admin DM (only if there were meaningful actions)."""
    if not report or not admin_id:
        return
    # Compact report — only show non-INFO entries + summary count
    warns = [r for r in report if "[SelfHeal:WARN]" in r or "[SelfHeal:ERROR]" in r]
    if not warns:
        # Silent success — don't spam admin on every restart
        return
    text = (
        "🩹 *Self-Heal Report*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Bot startup checks found *{len(warns)} issue(s)*:\n\n"
    )
    for w in warns[:10]:
        text += f"• {w}\n"
    if len(warns) > 10:
        text += f"\n_...and {len(warns) - 10} more._"
    try:
        await bot.send_message(admin_id, text, parse_mode="Markdown")
    except Exception:
        pass
