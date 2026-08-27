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
        # 🆕 v81: External supplier tables — SAFE ONLY.
        # Legacy backup/wipe migrations are intentionally DISABLED in production.
        # They could wipe restored shop products on startup, causing the exact
        # Render restore/reset issue the owner reported.
        try:
            from ext_suppliers import (ensure_ext_supplier_tables, ensure_env_supplier_presets,
                                       ensure_env_sinhle_supplier)
            ensure_ext_supplier_tables()
            healed.append("ext_supplier_tables")
            sid, status = ensure_env_supplier_presets()
            if sid:
                _log(f"env supplier preset Shop Cron {status} (#{sid})")
            try:
                sid2, status2 = ensure_env_sinhle_supplier()
                if sid2:
                    _log(f"env supplier preset sinhle store bot {status2} (#{sid2})")
            except Exception as _sh2:
                _log(f"sinhle preset: {_sh2}", "WARN")
            _log("v81/v83 destructive product-wipe migrations skipped safely")
        except Exception as e:
            _log(f"v81 ext_suppliers table setup: {e}", "WARN")
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
            healed_count, herr = heal_v86_broken_html_names()
            _log(f"v90/v91 heal: processed on startup — healed {healed_count} broken rows"
                 + (f" (err: {herr})" if herr and herr != 'already_healed' else ""))
        except Exception as e:
            _log(f"v90/v91 heal failed: {e}", "WARN")
    except Exception as e:
        _log(f"table healing outer failure: {e}", "WARN")
    if healed:
        _log(f"Verified/created tables: {', '.join(healed)}")


def _heal_sqlite_integrity_indexes():
    """Repair recoverable SQLite index/table-index issues after DB restore.

    Some Telegram/Render backup restores can leave broken indexes while table
    data is still readable. This safely rebuilds bot_settings + user_clicks
    indexes, then REINDEX/VACUUM. It does NOT touch orders/products data.
    """
    try:
        from database import get_connection
        conn = get_connection(); conn.row_factory = None; c = conn.cursor()
        try:
            rows = c.execute('PRAGMA integrity_check').fetchall()
            issues = [str(r[0]) for r in rows if str(r[0]).lower() != 'ok']
        except Exception as e:
            issues = [str(e)]
        if not issues:
            conn.close(); return
        joined = '\n'.join(issues[:20]).lower()
        repaired = []
        # Rebuild bot_settings when its UNIQUE index is inconsistent.
        if 'bot_settings' in joined or 'sqlite_autoindex_bot_settings' in joined:
            try:
                c.execute('CREATE TABLE IF NOT EXISTS bot_settings_repair (key TEXT PRIMARY KEY, value TEXT DEFAULT "")')
                c.execute('DELETE FROM bot_settings_repair')
                data = []
                for row in c.execute('SELECT rowid, key, value FROM bot_settings ORDER BY rowid'):
                    key = row[1]
                    if key is not None:
                        data.append((str(key), '' if row[2] is None else str(row[2])))
                for key, val in data:
                    c.execute('INSERT OR REPLACE INTO bot_settings_repair (key,value) VALUES (?,?)', (key, val))
                c.execute('DROP TABLE bot_settings')
                c.execute('ALTER TABLE bot_settings_repair RENAME TO bot_settings')
                repaired.append(f'bot_settings rebuilt ({len(data)} rows)')
            except Exception as e:
                _log(f'bot_settings repair failed: {e}', 'WARN')
        # Rebuild known user_click indexes when damaged.
        if 'idx_uc_' in joined or 'user_click' in joined:
            try:
                c.execute('DROP INDEX IF EXISTS idx_uc_time')
                c.execute('DROP INDEX IF EXISTS idx_uc_user_time')
                c.execute('CREATE INDEX IF NOT EXISTS idx_uc_time ON user_clicks(created_at)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_uc_user_time ON user_clicks(user_id, created_at)')
                repaired.append('user_clicks indexes rebuilt')
            except Exception as e:
                _log(f'user_click index repair failed: {e}', 'WARN')
        try:
            c.execute('REINDEX')
            repaired.append('REINDEX ok')
        except Exception as e:
            _log(f'REINDEX failed after repair: {e}', 'WARN')
        conn.commit()
        try:
            c.execute('VACUUM')
            repaired.append('VACUUM ok')
        except Exception as e:
            _log(f'VACUUM skipped/failed after repair: {e}', 'WARN')
        conn.close()
        if repaired:
            _log('SQLite integrity repair: ' + '; '.join(repaired))
    except Exception as e:
        _log(f'SQLite integrity repair outer failed: {e}', 'WARN')


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


def _heal_activity_flood_settings():
    """🔧 v123: per-user fake-activity settings that would flood Telegram
    (seconds unit + tiny intervals + many users = FloodWait/429 = bot stuck).
    Restores a sane floor so the bot can never lock itself up on restore."""
    try:
        from database import get_setting, set_setting
        unit = (get_setting("pua_interval_unit", "minutes") or "minutes").strip().lower()
        if unit == "seconds":
            mn = int(get_setting("pua_min_interval", "1") or 1)
            mx = int(get_setting("pua_max_interval", "10") or 10)
            if mn < 30 or mx < 60:
                set_setting("pua_min_interval", "1")
                set_setting("pua_max_interval", "60")
                set_setting("pua_interval_unit", "minutes")
                _log("PUA flood settings corrected: seconds→minutes (min=1, max=60)")
    except Exception as e:
        _log(f"activity flood heal failed: {e}", "WARN")


def _heal_orphaned_sessions():
    """No-op — user sessions are per-context, cleared naturally by force_main_menu."""
    pass


def _heal_icon_fill_one_time_reset():
    """🆕 v170.78 one-time: the owner lowered the icon gap fill to 4 while
    debugging the old fixed-fill logic.  Under the new AUTO-snug math the
    neutral value 8 is required for the text to reach the icon.  This runs
    exactly once (guarded by a settings flag) so any later manual choice by
    the owner is respected forever after.
    """
    try:
        from database import get_setting, set_setting
        if get_setting("icon_fill_v17078_reset", "") == "1":
            return
        set_setting("icon_fill_v17078_reset", "1")
        current = str(get_setting("shop_category_icon_fill", "8") or "8")
        if current != "8" and current != "0":
            set_setting("shop_category_icon_fill", "8")
            _log(f"Icon gap fill one-time reset {current} → 8 (auto-snug neutral)")
    except Exception as e:
        _log(f"heal_icon_fill: {e}", "ERROR")


def _heal_category_picker_title():
    """🆕 v170.74: refresh the buyer category picker title to the new
    reference-style default ("📁 Categories / Pick a category to browse.")
    ONLY while the stored text is still the untouched old default.
    Admin-customized titles are never overwritten.
    """
    try:
        from database import get_connection
        from config import DEFAULT_RESPONSES
        old_default = ("🛍️ *Shop — Categories*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                       "Select a category to browse:")
        new_default = DEFAULT_RESPONSES.get("shop_categories_title", "")
        if not new_default or new_default == old_default:
            return
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT value FROM bot_responses WHERE key='shop_categories_title'")
            row = c.fetchone()
            if row and str(row[0]) == old_default:
                c.execute("UPDATE bot_responses SET value=? WHERE key='shop_categories_title'",
                          (new_default,))
                conn.commit()
                _log("Category picker title refreshed to the new reference default")
        finally:
            conn.close()
    except Exception as e:
        _log(f"heal_cat_title: {e}", "ERROR")


def _heal_bybit_instruction_text():
    """🆕 v112: update the Bybit Pay instruction default ONLY when it is still
    the untouched old default ("Transaction Hash"). Admin-customized text is
    never overwritten. Internal Bybit transfers have a *Transfer ID*, not a
    blockchain hash — telling customers to paste a "hash" caused mismatches.
    """
    try:
        from database import get_connection, get_setting, set_setting
        old_default = ("4. Copy the *Transaction Hash* from Bybit receipt."
                       "\n5. Paste the Transaction Hash here in chat.")
        cur = get_connection()
        c = cur.cursor()
        try:
            c.execute("SELECT value FROM bot_responses WHERE key='payment_bybit_pay'")
            row = c.fetchone()
            if row:
                val = str(row[0] or '')
                if "Transaction Hash" in val and "Transfer ID" not in val:
                    updated = val.replace("4. Copy the *Transaction Hash* from Bybit receipt.",
                                          "4. Copy the *Transfer ID* from your Bybit receipt (transaction history).")
                    updated = updated.replace("5. Paste the Transaction Hash here in chat.",
                                              "5. Paste the Transfer ID here in chat.")
                    c.execute("UPDATE bot_responses SET value=? WHERE key='payment_bybit_pay'", (updated,))
                    cur.commit()
                    _log("Bybit Pay instruction updated to 'Transfer ID' (was old default)")
            # 🔧 v121: the bot now AUTO-DETECTS Bybit payments — no pasting needed.
            # Update any old paste-style wording (default OR the common edited
            # variant "Paste it here in chat") to the new no-paste text.
            _old_paste_markers = ("Paste the Transfer ID here in chat",
                                  "Paste it here in chat",
                                  "Copy the *Transfer ID* from your Bybit receipt")
            if any(m in val for m in _old_paste_markers):
                new_default = (
                    "🟡 *Bybit Pay — Order #{order_id}*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "💰 Amount: *{amount} USDT*\n"
                    "📥 Bybit Pay ID / UID: `{pay_id}`\n\n"
                    "*How to pay:*\n"
                    "1. Open Bybit app → Bybit Pay → Send\n"
                    "2. Send exactly *{amount} USDT* to the UID above\n"
                    "3. Done — that's it! ✅\n\n"
                    "🤖 Your payment is detected automatically from your Bybit account and credited within seconds.\n"
                    "_No need to paste any ID or screenshot._"
                )
                c.execute("UPDATE bot_responses SET value=? WHERE key='payment_bybit_pay'", (new_default,))
                cur.commit()
                _log("Bybit Pay instruction updated to auto-detect wording (no paste)")
            # Reference line: mark as optional (auto-detect works without it).
            c.execute("SELECT value FROM bot_responses WHERE key='payment_bybit_pay_reference'")
            row_ref = c.fetchone()
            if row_ref:
                val_ref = str(row_ref[0] or '')
                if "tap 'Reference' / 'Note' and paste this ID" in val_ref:
                    new_ref = (
                        "🔖 *Optional — YOUR REFERENCE ID:* `{reference_id}`\n"
                        "_Tip: paste it in the 'Reference' field when sending so we can match it instantly. Not required — payment is auto-detected either way._"
                    )
                    c.execute("UPDATE bot_responses SET value=? WHERE key='payment_bybit_pay_reference'", (new_ref,))
                    cur.commit()
                    _log("Bybit Pay reference line updated to optional wording")
            # Generic "not found" message — same Transfer-ID wording for Bybit.
            c.execute("SELECT value FROM bot_responses WHERE key='payment_not_found_txid'")
            row2 = c.fetchone()
            if row2:
                val2 = str(row2[0] or '')
                if "Transaction Hash Not Found Yet" in val2 and "Transfer ID" not in val2:
                    c.execute("UPDATE bot_responses SET value=? WHERE key='payment_not_found_txid'",
                              (val2.replace("Transaction Hash Not Found Yet", "Transaction Not Found Yet")
                                   .replace("paste the correct Transaction Hash again",
                                            "paste the correct Transaction / Transfer ID again"),))
                    cur.commit()
                    _log("Generic TXID not-found message updated to 'Transfer ID' wording")
        except Exception as e:
            _log(f"bybit instruction heal failed: {e}", "WARN")
        finally:
            try: cur.close()
            except Exception: pass
    except Exception:
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
        _heal_sqlite_integrity_indexes()
    except Exception as e:
        _log(f"heal_integrity outer: {e}", "ERROR")
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
    try:
        _heal_activity_flood_settings()
    except Exception as e:
        _log(f"heal_activity outer: {e}", "ERROR")
    try:
        _heal_bybit_instruction_text()
    except Exception as e:
        _log(f"heal_bybit outer: {e}", "ERROR")
    try:
        _heal_category_picker_title()
    except Exception as e:
        _log(f"heal_cat_title outer: {e}", "ERROR")
    try:
        _heal_icon_fill_one_time_reset()
    except Exception as e:
        _log(f"heal_icon_fill outer: {e}", "ERROR")
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
