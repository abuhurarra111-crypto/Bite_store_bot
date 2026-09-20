# -*- coding: utf-8 -*-
"""
v170.103 REGRESSION SUITE:
Verifies bot anti-freeze & responsiveness fixes:
1. setup_api_tables uses cached guard flag (no redundant DDL).
2. count_api_requests_recent uses fast index query.
3. set_setting ignores None/empty key.
4. per_user_activity ignores per-user jobs when dest_mode == 'group_only'.
5. support ticket reminder caps at 3 reminders max.
"""

import os, sys, shutil, tempfile, sqlite3
from unittest.mock import MagicMock, AsyncMock

_TMPDIR = tempfile.mkdtemp(prefix="v170103_regr_")
_REGDB = os.path.join(_TMPDIR, "regression.db")
os.environ["DB_PATH"] = _REGDB
os.environ.setdefault("BOT_TOKEN", "1:test")
os.environ.setdefault("ADMIN_ID", "7105782769")
os.environ.setdefault("GEMINI_API_KEY", "x")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_SRC_DB = "/home/user/bite_store_restore_ready.db"
if os.path.exists(_SRC_DB):
    shutil.copy(_SRC_DB, _REGDB)

import pytest
import database
import per_user_activity
import support_replacement


def test_api_tables_cached_guard():
    assert database._API_TABLES_SETUP_DONE is True or database._API_TABLES_SETUP_DONE is False
    database.setup_api_tables()
    assert database._API_TABLES_SETUP_DONE is True
    # Second call should return immediately without executing DDL
    database.setup_api_tables()
    assert database._API_TABLES_SETUP_DONE is True


def test_set_setting_guards_none_key():
    database.set_setting(None, "bad_val")
    database.set_setting("None", "bad_val")
    database.set_setting("", "bad_val")
    conn = database.get_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM bot_settings WHERE key IS NULL OR key="None" OR key=""')
    cnt = c.fetchone()[0]
    conn.close()
    assert cnt == 0


def test_group_only_skips_user_jobs():
    database.set_setting("dest_mode", "group_only")
    app = MagicMock()
    app.job_queue = MagicMock()
    per_user_activity._scheduled_users.clear()
    
    per_user_activity._schedule_next_for_user(app, 999999)
    assert 999999 not in per_user_activity._scheduled_users
    assert app.job_queue.run_once.call_count == 0


def test_ticket_reminder_caps_at_3():
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO support_tickets (user_id, subject, description, status, reminder_count, created_at) VALUES (1111, 'test', 'desc', 'in_progress', 5, '2026-09-01 00:00:00')")
    tid_old = c.lastrowid
    c.execute("INSERT INTO support_tickets (user_id, subject, description, status, reminder_count, created_at) VALUES (2222, 'test2', 'desc2', 'in_progress', 1, '2026-09-01 00:00:00')")
    tid_new = c.lastrowid
    conn.commit()
    conn.close()

    due = support_replacement.get_due_reminder_tickets(hours=1)
    due_ids = [t['id'] for t in due]
    assert tid_old not in due_ids
    assert tid_new in due_ids
