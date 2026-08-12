# ============================================================
# 🧪 BITE STORE — v134: referral math verification + 30s activity
# observation + BOTH users get the admin-set points
# Run:  pytest _test_v134_ref_math.py -v   (isolated DB)
# ============================================================
import os, tempfile
from types import SimpleNamespace

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="v134_"), "t.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["BOT_TOKEN"] = "1:2"
os.environ["ADMIN_ID"] = "9"
os.environ["BYBIT_API_KEY"] = "K"
os.environ["BYBIT_API_SECRET"] = "S"

import database
from database import (setup_database, migrate_all, get_setting, set_setting,
                      get_referral_math_enabled, set_referral_math_enabled,
                      add_ref_points, get_ref_points, get_user, save_user,
                      add_pending_referral, get_pending_referral_for_user,
                      mark_pending_referral_done, bump_pending_referral_activity,
                      get_connection, get_ref_points_per_ref, set_ref_points_per_ref)
setup_database(); migrate_all()

import handlers_start as HS
from handlers_start import (_parse_start_arg, _new_math_question,
                            _referral_math_enabled, _DEFAULT_REFERRED_REWARD_TEMPLATE,
                            _render_referral_template)


# ── fakes ────────────────────────────────────────────────────
class FakeBot:
    async def send_message(self, chat_id, text, **kw):
        return None
    async def send_photo(self, *a, **k):
        return None
    async def get_me(self):
        return SimpleNamespace(username="bite_storee_bot", id=123)


class FakeJobQueue:
    def __init__(self): self.jobs = []
    def run_once(self, fn, when, data=None, name=None):
        self.jobs.append((fn, when, data, name))
        return SimpleNamespace()


def _ctx():
    app = SimpleNamespace()
    jq = FakeJobQueue()
    return SimpleNamespace(bot=FakeBot(), job_queue=jq, application=app, user_data={})


def _user(uid, first="U", username="u"):
    return SimpleNamespace(id=uid, first_name=first, username=username, is_bot=False)


class TestMathToggle:
    def test_default_on(self):
        assert get_referral_math_enabled() is True

    def test_toggle_off_on(self):
        set_referral_math_enabled(False)
        assert get_referral_math_enabled() is False
        set_referral_math_enabled(True)
        assert get_referral_math_enabled() is True


class TestParseStartArg:
    def test_plain_ref(self):
        assert _parse_start_arg("12345") == (12345, 0, 0)

    def test_ref_product(self):
        assert _parse_start_arg("ref_12345_7") == (12345, 7, 0)

    def test_buy(self):
        assert _parse_start_arg("buy_9") == (0, 9, 0)

    def test_checkout(self):
        # 🐛 v147 (Bug7): chk_<pid> → direct checkout deep link
        assert _parse_start_arg("chk_214") == (0, 0, 214)

    def test_empty(self):
        assert _parse_start_arg("") == (0, 0, 0)

    def test_garbage(self):
        assert _parse_start_arg("xyz") == (0, 0, 0)


class TestMathQuestion:
    def test_valid(self):
        for _ in range(50):
            a, op, b, ans = _new_math_question()
            assert op in ("+", "-")
            assert a > 0 and b > 0
            if op == "+":
                assert ans == a + b
            else:
                assert ans == a - b and ans >= 0

    def test_randomness(self):
        seen = {_new_math_question() for _ in range(30)}
        assert len(seen) >= 5  # not constant


class TestPendingActivityObservation:
    def test_bump_increments(self):
        add_pending_referral(500, 501, 0, 'test')
        assert bump_pending_referral_activity(501) == 1
        assert bump_pending_referral_activity(501) == 2
        row = get_pending_referral_for_user(501)
        assert int(row['activity_count']) == 2

    def test_bump_no_pending(self):
        assert bump_pending_referral_activity(999999) == 0

    def test_mark_done_stops(self):
        add_pending_referral(500, 502, 0, 'test')
        mark_pending_referral_done(502, 'approved', 'x')
        assert get_pending_referral_for_user(502) is None


class TestBothUsersGetPoints:
    def test_approve_credits_both(self):
        import asyncio
        set_ref_points_per_ref(2.5)
        # clean slate
        conn = get_connection(); c = conn.cursor()
        c.execute("DELETE FROM referral_log")
        c.execute("DELETE FROM pending_referrals")
        conn.commit(); conn.close()
        save_user(701, "ref", "Referrer")
        save_user(702, "fri", "Friend")
        referrer = _user(701, "Referrer", "referrer_x")
        referred = _user(702, "Friend", "friend_y")
        ctx = _ctx()
        # run attribution with approve_now=True (the post-observation approval)
        asyncio.run(HS._process_referral_attribution(
            ctx, referred, 701, True, product_id=0, approve_now=True))
        assert abs(get_ref_points(701) - 2.5) < 0.001
        assert abs(get_ref_points(702) - 2.5) < 0.001

    def test_blocked_never_credits(self):
        import asyncio
        # self-referral is blocked — nobody gets points
        set_ref_points_per_ref(1)
        conn = get_connection(); c = conn.cursor()
        c.execute("DELETE FROM referral_log")
        conn.commit(); conn.close()
        save_user(703, "me", "me")
        me = _user(703, "me", "me")
        ctx = _ctx()
        ok = asyncio.run(HS._process_referral_attribution(
            ctx, me, 703, True, product_id=0, approve_now=False))
        assert ok is False
        assert get_ref_points(703) == 0


class TestReferredTemplate:
    def test_renders(self):
        values = {'reward_points': '2.5', 'referred_id': '42',
                  'referrer_name': 'Ali'}
        out = _render_referral_template('ref_tpl_referred',
                                        _DEFAULT_REFERRED_REWARD_TEMPLATE, values)
        assert '+2.5' in out
        assert '42' in out
        assert 'Ali' in out

    def test_placeholder_listing(self):
        from handlers_referral_admin import REF_TPL_PLACEHOLDERS
        assert 'referred' in REF_TPL_PLACEHOLDERS


class TestConfigKey:
    def test_fj_verified_done_registered(self):
        from config import DEFAULT_RESPONSES
        assert 'fj_verified_done' in DEFAULT_RESPONSES
        assert 'Verified' in DEFAULT_RESPONSES['fj_verified_done']


class TestVerifiedContinuation:
    def test_no_referral_returns_false(self):
        """Without a referral deep-link, the force-join continuation must NOT
        claim it handled the flow (so fj_verified shows the verified message)."""
        import asyncio
        from types import SimpleNamespace
        upd = SimpleNamespace(effective_message=SimpleNamespace(reply_text=lambda *a, **k: SimpleNamespace()))
        ctx = SimpleNamespace(user_data={}, bot=FakeBot(), job_queue=FakeJobQueue(), application=SimpleNamespace())
        u = _user(777, "Normal", "normal_u")
        out = asyncio.run(HS.continue_after_force_join_verified(upd, ctx, u))
        assert out is False

    def test_welcome_helper_exists(self):
        assert hasattr(HS, "_send_welcome_message")
        assert hasattr(HS, "_parse_start_arg")
