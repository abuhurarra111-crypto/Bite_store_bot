# 🆕 v152 — POLL FORWARD FLOW (admin creates original Telegram poll → bot
# rebroadcasts to all users in background; no more wizard-stuck / 429 spam).
import os
import sys
import asyncio

os.environ.setdefault("DB_PATH", "/tmp/v152_unit.db")
os.environ.setdefault("ADMIN_ID", "7105782769")
os.environ.setdefault("BOT_TOKEN", "test:token")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers_admin as HA
import database as db


def _ctx():
    class C:
        user_data = {}
        bot = None
    return C()


def _msg():
    class O:
        def __init__(self, t):
            self.text = t
    class P:
        question = "Q?"
        options = [O("A"), O("B"), O("C")]
        is_anonymous = True
        allows_multiple_answers = False
        type = "regular"
        close_date = None
    class M:
        poll = P()
        from_user = type("U", (), {"id": 7105782769})()
        chat = type("C", (), {"type": "private"})()
        message_id = 1
        async def reply_text(self, *a, **k):
            return None
    return M()


def _upd():
    class U:
        def __init__(self):
            self.message = _msg()
    return U()


def test_capture_admin_poll():
    c = _ctx()
    loop = asyncio.new_event_loop()
    try:
        r = loop.run_until_complete(HA.handle_admin_poll_message(_upd(), c))
    finally:
        loop.close()
    assert r is True
    assert c.user_data["fwd_poll"]["question"] == "Q?"
    assert c.user_data["fwd_poll"]["options"] == ["A", "B", "C"]


def test_ignore_non_admin_poll():
    class O:
        def __init__(self, t):
            self.text = t
    class P:
        question = "Q?"
        options = [O("A"), O("B")]
        is_anonymous = True
        allows_multiple_answers = False
        type = "regular"
        close_date = None
    class M:
        poll = P()
        from_user = type("U", (), {"id": 999})()
        chat = type("C", (), {"type": "private"})()
        async def reply_text(self, *a, **k):
            return None
    class U:
        message = M()
    c = _ctx()
    loop = asyncio.new_event_loop()
    try:
        r = loop.run_until_complete(HA.handle_admin_poll_message(U(), c))
    finally:
        loop.close()
    assert r is None
    assert "fwd_poll" not in c.user_data


def test_create_from_forwarded_poll():
    pid = db.create_poll("Q?", ["A", "B", "C"], is_anonymous=True, allows_multiple=False)
    assert pid > 0
    p = db.get_poll(pid)
    assert p["question"] == "Q?"
    db.delete_poll_row(pid)


def test_background_broadcast_task_ok():
    class Bot:
        async def send_poll(self, *a, **k):
            class M:
                def __init__(self):
                    self.poll = type("P", (), {"id": "tg_1"})()
            return M()
        async def send_message(self, *a, **k):
            return None
    pid = db.create_poll("Q?", ["A", "B"], is_anonymous=True)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(HA._broadcast_poll_task(Bot(), pid, notify_uid=None))
    finally:
        loop.close()
    db.delete_poll_row(pid)


def test_wizard_removed_from_panel():
    src = open("handlers_admin.py", encoding="utf-8").read()
    # new English instructions must be present; old poll wizard entry gone
    assert "Send / Forward a Poll" in src
    assert "Create Poll — Step 1/3" not in src
    assert "How it works (easy)" in src


def test_bot_registered():
    src = open("bot.py", encoding="utf-8").read()
    assert "filters.POLL" in src
    assert "fwd_poll_yes" in src
    assert "fwd_poll_no" in src


# 🐛 v153 — row_uid (DictRow fix) + PTB poll parsing patch + English UI
import database as db


def test_row_uid_dictrow():
    import sqlite3
    try:
        users = db.get_all_users_for_broadcast()
    except sqlite3.OperationalError:
        users = []
    if users:
        u = users[0]
        uid = db.row_uid(u)
        assert uid == u["user_id"], f"row_uid {uid} != user_id {u['user_id']}"
    # tuple fallback (always works)
    assert db.row_uid((5, 123456789, "x")) == 123456789


def test_ptb_poll_patch_present():
    src = open("bot.py", encoding="utf-8").read()
    assert "_patch_ptb_poll_parsing" in src
    assert "option_persistent_ids" in src


def test_english_poll_ui():
    src = open("handlers_admin.py", encoding="utf-8").read()
    assert "sab users" not in src
    assert "dabao" not in src
    assert "Poll Forward Karein" not in src


# 🆕 v154 — Poll destination chooser (group / dm / both)
def test_v154_chooser_removed():
    # owner only ASKED — v154 chooser was reverted back to v153 direct DM flow
    src = open("handlers_admin.py", encoding="utf-8").read()
    src_bot = open("bot.py", encoding="utf-8").read()
    assert "fwd_where" not in src
    assert "fwd_where" not in src_bot
    assert "_broadcast_poll_to_group" not in src


# 🆕 v155 — premium emoji poll + who-voted (v154 chooser removed)
def test_v155_premium_entities():
    src = open("handlers_admin.py", encoding="utf-8").read()
    assert "question_entities" in src
    assert "options_entities" in src
    assert "InputPollOption" in src
    assert "MessageEntity.de_json" in src


def test_v155_who_voted():
    src = open("handlers_admin.py", encoding="utf-8").read()
    assert "voters" in src
    src_db = open("database.py", encoding="utf-8").read()
    assert "user_name" in src_db
    assert "username" in src_db


def test_v155_chooser_removed():
    src = open("handlers_admin.py", encoding="utf-8").read()
    src_bot = open("bot.py", encoding="utf-8").read()
    assert "fwd_where" not in src
    assert "fwd_where" not in src_bot
    assert "_broadcast_poll_to_group" not in src


def test_v155_who_voted_db_flow():
    import json as _j
    pid = db.create_poll("Q?", ["A", "B"], is_anonymous=False)
    db.record_poll_answer(pid, 9001, [0], user_name="Ali", username="ali_k")
    res = db.get_poll_results(pid)
    assert res and res["options"][0]["voters"][0]["username"] == "ali_k"
    db.delete_poll_row(pid)


# 🆕 v156 — Broadcast progress animation + bot-startup fix (stale poll regs removed)
def test_v156_broadcast_progress():
    from utils import BroadcastProgress
    import inspect
    assert inspect.iscoroutinefunction(BroadcastProgress.start)
    assert inspect.iscoroutinefunction(BroadcastProgress.bump)
    assert inspect.iscoroutinefunction(BroadcastProgress.finish)


def test_v156_poll_regs_fixed():
    src = open("bot.py", encoding="utf-8").read()
    # stale wizard registrations removed (were crashing startup with NameError)
    assert "poll_anon_callback" not in src
    assert "poll_duration_callback" not in src
    # new flow regs present
    assert "fwd_poll_yes" in src
    assert "admin_polls" in src


def test_v156_progress_wired():
    src = open("handlers_admin.py", encoding="utf-8").read()
    assert "BroadcastProgress" in src
    assert "notify_uid=ADMIN_ID" in src
    src2 = open("loyalty_extras.py", encoding="utf-8").read()
    assert "BroadcastProgress" in src2
    assert 'title="📌 Pinned Broadcast"' in src2
