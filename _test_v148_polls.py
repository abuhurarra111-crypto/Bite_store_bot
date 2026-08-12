# 🆕 v148 — Polls: create + broadcast to all users + vote tracking + results
import os
import sys
import json

os.environ.setdefault("DB_PATH", "/tmp/test_v148.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db


class TestPollDB:
    def setup_method(self):
        db.ensure_poll_tables()

    def test_create_poll(self):
        pid = db.create_poll("Question?", ["A", "B", "C"])
        assert pid > 0
        p = db.get_poll(pid)
        assert p is not None
        assert p["question"] == "Question?"
        opts = json.loads(p["options_json"])
        assert opts == ["A", "B", "C"]
        db.delete_poll_row(pid)

    def test_answers_and_results(self):
        pid = db.create_poll("Q", ["X", "Y"])
        db.record_poll_answer(pid, 1001, [0])
        db.record_poll_answer(pid, 1002, [0])
        db.record_poll_answer(pid, 1003, [1])
        res = db.get_poll_results(pid)
        assert res is not None
        assert res["total_voters"] == 3
        votes = {o["option"]: o["votes"] for o in res["options"]}
        assert votes["X"] == 2
        assert votes["Y"] == 1
        db.delete_poll_row(pid)

    def test_revote_replaces(self):
        pid = db.create_poll("Q", ["A", "B"])
        db.record_poll_answer(pid, 2001, [0])
        db.record_poll_answer(pid, 2001, [1])  # switch vote
        res = db.get_poll_results(pid)
        votes = {o["option"]: o["votes"] for o in res["options"]}
        assert res["total_voters"] == 1
        assert votes["A"] == 0
        assert votes["B"] == 1
        db.delete_poll_row(pid)

    def test_tg_id_mapping(self):
        pid = db.create_poll("Q", ["A", "B"])
        db.add_tg_poll_ids(pid, ["tg_1", "tg_2", "tg_1"])  # dedupe
        assert db.find_poll_by_tg_id("tg_1") == pid
        assert db.find_poll_by_tg_id("tg_2") == pid
        assert db.find_poll_by_tg_id("nope") == 0
        db.delete_poll_row(pid)

    def test_close_and_delete(self):
        pid = db.create_poll("Q", ["A", "B"])
        db.set_poll_active(pid, False)
        assert db.get_poll_results(pid)["closed"] is True
        db.delete_poll_row(pid)
        assert db.get_poll(pid) is None


class TestPollAdminHandlers:
    def test_functions_exist(self):
        import handlers_admin as HA
        for name in ("admin_polls_callback", "poll_create_start_callback",
                     "poll_question_received", "poll_options_received",
                     "poll_anon_callback", "poll_duration_callback",
                     "poll_results_callback", "poll_detail_callback",
                     "poll_close_callback", "poll_delete_callback",
                     "handle_poll_answer"):
            assert hasattr(HA, name), f"missing {name}"

    def test_broadcast_helper_exists(self):
        import handlers_admin as HA
        import inspect
        assert inspect.iscoroutinefunction(HA._broadcast_poll_to_users)

    def test_button_registered(self):
        import button_system as BS
        assert "admin_polls" in BS.BUTTONS
        assert BS.BUTTONS["admin_polls"]["callback"] == "admin_polls"

    def test_bot_registered(self):
        src = open("bot.py", encoding="utf-8").read()
        assert "^admin_polls$" in src
        assert "PollAnswerHandler" in src or "filters.POLL_ANSWER" in src
