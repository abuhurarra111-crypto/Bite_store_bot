# ============================================================
# 🧪 BITE STORE — v144.4: fake-activity group-job stuck-flag FIX
# Run:  pytest _test_v1444_fakeact.py -v
# ============================================================
import os, tempfile

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="v1444_"), "t.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["BOT_TOKEN"] = "8826914364:AAHMuODKCwvYFB3qX5723-5LbTjRzhkEoms"
os.environ["ADMIN_ID"] = "7105782769"
os.environ["BYBIT_API_KEY"] = "K"
os.environ["BYBIT_API_SECRET"] = "S"

import database
from database import setup_database, migrate_all, set_setting
setup_database(); migrate_all()

import per_user_activity as P
from per_user_activity import (_group_job_actually_scheduled,
                               schedule_group_activity_job,
                               is_globally_enabled)


class FakeJobQueue:
    def __init__(self):
        self._jobs = []
    def jobs(self):
        return list(self._jobs)
    def run_once(self, fn, when, name=None, **kw):
        from types import SimpleNamespace
        self._jobs.append(SimpleNamespace(name=name or "", callback=fn))
        return SimpleNamespace()
    def run_repeating(self, *a, **k):
        return None


class FakeApp:
    def __init__(self):
        self.job_queue = FakeJobQueue()
        self.bot = None
        self.user_data = {}


class TestStuckFlagFix:
    def test_actually_scheduled_empty_queue(self):
        app = FakeApp()
        assert _group_job_actually_scheduled(app) is False

    def test_actually_scheduled_with_job(self):
        app = FakeApp()
        schedule_group_activity_job(app)
        assert _group_job_actually_scheduled(app) is True

    def test_stuck_flag_does_not_block(self):
        """The bug: flag stuck True but queue empty → old code returned early.
        New code checks the actual queue and re-schedules."""
        app = FakeApp()
        P._group_job_scheduled = True  # simulate stuck flag
        assert _group_job_actually_scheduled(app) is False
        schedule_group_activity_job(app)
        assert len(app.job_queue.jobs()) == 1
        assert P._group_job_scheduled is True

    def test_normal_schedule(self):
        app = FakeApp()
        P._group_job_scheduled = False
        schedule_group_activity_job(app)
        assert P._group_job_scheduled is True
        assert _group_job_actually_scheduled(app) is True

    def test_double_schedule_skips(self):
        app = FakeApp()
        schedule_group_activity_job(app)
        schedule_group_activity_job(app)
        assert len(app.job_queue.jobs()) == 1  # no duplicate


class TestWatchdog:
    def test_watchdog_uses_actual_check(self):
        src = open("per_user_activity.py", encoding="utf-8").read()
        assert "_group_job_actually_scheduled(app)" in src
        assert "_group_job_scheduled = False" in src  # reset before reschedule
