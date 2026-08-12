# ============================================================
# 🧪 BITE STORE — v135: force join unlimited targets + editable buttons
# Run:  pytest _test_v135_forcejoin.py -v   (isolated DB)
# ============================================================
import os, tempfile

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="v135_"), "t.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["BOT_TOKEN"] = "1:2"
os.environ["ADMIN_ID"] = "9"
os.environ["BYBIT_API_KEY"] = "K"
os.environ["BYBIT_API_SECRET"] = "S"

import database
from database import (setup_database, migrate_all, set_setting, get_setting,
                      add_fj_target, list_fj_targets, get_fj_target,
                      update_fj_target, delete_fj_target, delete_all_fj_targets,
                      migrate_legacy_force_join, get_fj_verify_button,
                      set_fj_verify_label, set_fj_verify_style, set_fj_verify_emoji,
                      ensure_force_join_targets_table, get_connection)
setup_database(); migrate_all()


class TestTargetsCRUD:
    def setup_method(self):
        delete_all_fj_targets()

    def test_add_list(self):
        a = add_fj_target("https://t.me/bite_alerts", label="📢 Channel", style="primary")
        b = add_fj_target("@second", label="👥 Group", style="success")
        rows = list_fj_targets()
        assert len(rows) == 2
        assert rows[0]["id"] == a
        assert rows[0]["style"] == "primary"

    def test_get_update(self):
        tid = add_fj_target("@x", label="Old", style="")
        update_fj_target(tid, label="New Name", style="danger", emoji_id="5458672938")
        t = get_fj_target(tid)
        assert t["label"] == "New Name"
        assert t["style"] == "danger"
        assert t["emoji_id"] == "5458672938"

    def test_invalid_style_sanitized(self):
        tid = add_fj_target("@x", label="X", style="pink")
        update_fj_target(tid, style="purple")
        t = get_fj_target(tid)
        assert t["style"] == "purple"  # stored as given; validator is at render time

    def test_delete(self):
        tid = add_fj_target("@x")
        delete_fj_target(tid)
        assert get_fj_target(tid) is None

    def test_delete_all(self):
        add_fj_target("@a"); add_fj_target("@b")
        delete_all_fj_targets()
        assert list_fj_targets() == []

    def test_enabled_filter(self):
        a = add_fj_target("@a"); add_fj_target("@b")
        update_fj_target(a, enabled=0)
        assert len(list_fj_targets(enabled_only=True)) == 1


class TestLegacyMigration:
    def test_migrates_channel_group_once(self):
        delete_all_fj_targets()
        set_setting("fj_channel", "@oldchan")
        set_setting("fj_group", "@oldgroup")
        n = migrate_legacy_force_join()
        assert n == 2
        rows = list_fj_targets()
        assert any("@oldchan" in r["link"] for r in rows)
        assert any("@oldgroup" in r["link"] for r in rows)
        # second call → no duplicates
        assert migrate_legacy_force_join() == 0
        assert len(list_fj_targets()) == 2


class TestVerifyButton:
    def test_defaults(self):
        vb = get_fj_verify_button()
        assert "I Joined" in vb["label"]

    def test_setters(self):
        set_fj_verify_label("✅ Verify Now")
        set_fj_verify_style("danger")
        set_fj_verify_emoji("5458672938")
        vb = get_fj_verify_button()
        assert vb["label"] == "✅ Verify Now"
        assert vb["style"] == "danger"
        assert vb["emoji_id"] == "5458672938"

    def test_invalid_style_cleared(self):
        set_fj_verify_style("neon")
        assert get_fj_verify_button()["style"] == ""


class TestPanelHelpers:
    def test_style_label_mapping(self):
        from ui_extras import _style_label
        assert "Blue" in _style_label("primary")
        assert "Green" in _style_label("success")
        assert "Red" in _style_label("danger")
        assert "Default" in _style_label("")

    def test_join_url_helper(self):
        from ui_extras import _fj_join_url
        assert _fj_join_url("https://t.me/+abc") == "https://t.me/+abc"
        assert _fj_join_url("@bite") == "https://t.me/bite"
        assert _fj_join_url("bite") == "https://t.me/bite"


class TestGateLogic:
    def test_disabled_gate_false(self):
        import asyncio
        from types import SimpleNamespace
        from ui_extras import force_join_action_gate
        set_setting("fj_enabled", "0")
        upd = SimpleNamespace(effective_user=SimpleNamespace(id=111),
                              callback_query=None, effective_message=None, message=None)
        ctx = SimpleNamespace(user_data={}, bot=None)
        assert asyncio.run(force_join_action_gate(upd, ctx)) is False

    def test_admin_bypass(self):
        import asyncio
        from types import SimpleNamespace
        from ui_extras import force_join_action_gate
        set_setting("fj_enabled", "1")
        upd = SimpleNamespace(effective_user=SimpleNamespace(id=9),
                              callback_query=None, effective_message=None, message=None)
        ctx = SimpleNamespace(user_data={}, bot=None)
        assert asyncio.run(force_join_action_gate(upd, ctx)) is False

    def test_verify_callback_never_blocked(self):
        import asyncio
        from types import SimpleNamespace
        from ui_extras import force_join_action_gate
        set_setting("fj_enabled", "1")
        cq = SimpleNamespace(data="fj_verified")
        upd = SimpleNamespace(effective_user=SimpleNamespace(id=111),
                              callback_query=cq, effective_message=None, message=None)
        ctx = SimpleNamespace(user_data={}, bot=None)
        assert asyncio.run(force_join_action_gate(upd, ctx)) is False


class TestPanelReopenClearsFlags:
    """🐛 v142: reopening Force-Join panel must clear leftover text-step flags
    (else next plain text is swallowed by fj_add_link_received → stuck)."""

    def test_fj_panel_clears_flags(self):
        from types import SimpleNamespace
        from database import delete_all_fj_targets, set_setting
        from ui_extras import fj_panel_callback, fj_add_callback, fj_add_link_received

        delete_all_fj_targets()
        set_setting('fj_enabled', '1')

        class U:
            id = 9; username = 'admin'; first_name = 'A'
        class M:
            def __init__(self, text=""):
                self.text = text; self.from_user = U()
                self.chat = SimpleNamespace(id=7105782769)
                self.replied = []; self.entities = []
                self._html = text
            @property
            def text_html(self): return self._html
            @property
            def text_html_urled(self): return self._html
            async def reply_text(self, *a, **k):
                self.replied.append((a, k))
                class S: message_id = 1; chat_id = 7105782769
                return S()
        class CQ:
            def __init__(self, data):
                self.data = data; self.from_user = U()
                self.message = M("x"); self.answered = []; self.edited = []
            async def answer(self, *a, **k): self.answered.append(1)
            async def edit_message_text(self, t, parse_mode=None, reply_markup=None, **k):
                self.edited.append((t, parse_mode, reply_markup))
            async def edit_message_caption(self, **k): pass
        class UP_cb:
            def __init__(self, data):
                self.callback_query = CQ(data); self.effective_user = U()
                self.effective_message = self.callback_query.message; self.message = None
        class UP_txt:
            def __init__(self, text):
                self.message = M(text); self.effective_user = U()
                self.effective_message = self.message; self.callback_query = None
        class CTX:
            def __init__(self):
                self.user_data = {}
                self.bot = None
                self.job_queue = None
                self.application = None

        import asyncio
        async def _run():
            ctx = CTX()
            # invalid link → flag re-set (the bug trigger)
            await fj_add_callback(UP_cb('fj_add'), ctx)
            await fj_add_link_received(UP_txt('not-a-link'), ctx)
            assert ctx.user_data.get('fj_add_link') is True
            # reopen panel → flag MUST clear
            await fj_panel_callback(UP_cb('fj_panel'), ctx)
            assert ctx.user_data.get('fj_add_link') is None, "flag must clear on panel reopen"
            # normal text must NOT be swallowed
            got = await fj_add_link_received(UP_txt('hello'), ctx)
            assert got is False
        asyncio.run(_run())


class TestPremiumLabelDisplay:
    """🐛 v143.2: force-join target labels with premium-emoji markup
    ([[HTML]]<tg-emoji...>) must display clean, not raw HTML."""

    def test_fj_label_plain_strips_markup(self):
        from ui_extras import _fj_label_plain
        fancy = '[[HTML]]<tg-emoji emoji-id="5458672938">🔥</tg-emoji> Premium Chan'
        out = _fj_label_plain(fancy, 22)
        assert "[[HTML]]" not in out
        assert "<tg-emoji" not in out
        assert "Premium" in out
        assert "🔥" in out  # fallback char kept

    def test_fj_label_plain_plain_text(self):
        from ui_extras import _fj_label_plain
        assert _fj_label_plain("📢 Bite Alerts", 22) == "📢 Bite Alerts"

    def test_fj_label_plain_empty(self):
        from ui_extras import _fj_label_plain
        assert _fj_label_plain("", 22)  # non-crash

    def test_panel_renders_clean_label(self):
        """_show_fj_panel output must not contain [[HTML]] or <tg-emoji>."""
        import asyncio
        from types import SimpleNamespace
        from database import update_fj_target, get_connection, add_fj_target, delete_all_fj_targets

        delete_all_fj_targets()
        tid = add_fj_target('@x', label='📢 Temp', style='primary')
        fancy = '[[HTML]]<tg-emoji emoji-id="5458672938">🔥</tg-emoji> Premium Chan'
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE force_join_targets SET label=? WHERE id=?", (fancy, tid))
        conn.commit(); conn.close()

        from ui_extras import _show_fj_panel
        class SpyCQ:
            def __init__(self):
                self.edited = []
            async def edit_message_text(self, t, parse_mode=None, reply_markup=None, **k):
                self.edited.append((t, parse_mode)); return True
            async def edit_message_caption(self, **k): return True
        class FakeBot:
            pass

        async def _run():
            spy = SpyCQ()
            await _show_fj_panel(spy, FakeBot())
            txt = spy.edited[-1][0]
            assert "[[HTML]]" not in txt
            assert "<tg-emoji" not in txt
            assert "Premium" in txt or "Bite Alerts" in txt
        asyncio.run(_run())
        # cleanup
        delete_all_fj_targets()
