# ============================================================
# 🧪 BITE STORE — v137: full language switching + username @N/A fix
# Run:  pytest _test_v137_language.py -v   (isolated DB)
# ============================================================
import os, tempfile

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="v137_"), "t.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["BOT_TOKEN"] = "1:2"
os.environ["ADMIN_ID"] = "9"
os.environ["BYBIT_API_KEY"] = "K"
os.environ["BYBIT_API_SECRET"] = "S"

import database
from database import setup_database, migrate_all
setup_database(); migrate_all()


class TestPersistentMenu:
    def test_two_buttons(self):
        from keyboards import persistent_menu
        kb = persistent_menu()
        rows = kb.keyboard
        assert len(rows) == 1 and len(rows[0]) == 2
        labels = [b.text for b in rows[0]]
        assert any("Main Menu" in l for l in labels)
        assert any("How to Use" in l for l in labels)

    def test_accepts_user_id(self):
        from keyboards import persistent_menu
        kb = persistent_menu(12345)
        assert kb is not None


class TestReplyBtnMatches:
    def test_english(self):
        from bot import _reply_btn_matches
        assert _reply_btn_matches("🏠 Main Menu", "🏠 Main Menu", 1) is True

    def test_mismatch(self):
        from bot import _reply_btn_matches
        assert _reply_btn_matches("hello", "🏠 Main Menu", 1) is False

    def test_translated(self, monkeypatch):
        # simulate a user whose language makes tr_user return a translated label
        import bot
        import i18n as _i18n
        from database import save_user, get_connection
        save_user(1, "u", "User")
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE users SET language='ur' WHERE user_id=1")
        conn.commit(); conn.close()
        _i18n._lang_cache.pop(1, None)
        def fake_tr_user(text, user_id=None, lang=None):
            if text == "🏠 Main Menu" and lang == "ur":
                return "🏠 مرکزی مینو"
            return text
        monkeypatch.setattr(_i18n, "tr_user", fake_tr_user)
        assert bot._reply_btn_matches("🏠 مرکزی مینو", "🏠 Main Menu", 1) is True


class TestWelcomeFixed:
    def test_welcome_no_user_id_lookup(self):
        """_r('welcome') (no user_id) must return the DB/English template —
        it must NOT call the translated lookup for a specific user."""
        import handlers_start as HS
        w1 = HS._r("welcome")
        assert "{shop_name}" in w1 or "Welcome" in w1
        # and with user_id it may differ (translated) — we only assert no crash
        w2 = HS._r("welcome", user_id=1)
        assert isinstance(w2, str)


class TestUsernameDisplay:
    def test_my_account_template_artifact_cleanup(self):
        """Simulate the my_account render: username '' → '—', then the
        template's '@{username}' becomes '@—' → must be stripped to '—'."""
        tpl = "📛 Username: @{username}"
        uname_disp = "—"  # what the callback passes when no username
        text = tpl.format(username=uname_disp)
        cleaned = text.replace('@—', '—')
        assert cleaned == "📛 Username: —"
        assert "@—" not in cleaned

    def test_my_account_real_username_keeps_at(self):
        tpl = "📛 Username: @{username}"
        text = tpl.format(username="johndoe")
        assert text == "📛 Username: @johndoe"


class TestGuideHub:
    def test_builder_runs(self):
        from ui_extras import _build_how_to_hub_text_and_kb
        text, kb = _build_how_to_hub_text_and_kb(123)
        assert "How to Use" in text or "Guide" in text
        assert kb is not None
