# ============================================================
# 🧪 BITE STORE — v140.1: reaction feature REMOVED + force-join all-buttons fix
# Run:  pytest _test_v140_rollback.py -v
# ============================================================
import os, tempfile, asyncio

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="v1401_"), "t.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["BOT_TOKEN"] = "8826914364:AAHMuODKCwvYFB3qX5723-5LbTjRzhkEoms"
os.environ["ADMIN_ID"] = "7105782769"
os.environ["BYBIT_API_KEY"] = "K"
os.environ["BYBIT_API_SECRET"] = "S"

import database
from database import setup_database, migrate_all, get_setting, set_setting
setup_database(); migrate_all()

import customization as CZ


class TestReactionFeatureRemoved:
    def test_no_default_reaction_symbols(self):
        import customization as C
        assert not hasattr(C, "DEFAULT_REACTION_KEY")
        assert not hasattr(C, "auto_react_to_message")
        assert not hasattr(C, "get_default_reaction")

    def test_master_toggle_off_by_default(self):
        set_setting("react_enabled", "")
        assert CZ.reaction_enabled() is False

    def test_no_guard_reaction(self):
        src = open("premium_emoji_guard.py", encoding="utf-8").read()
        assert "_reaction_hook" not in src
        assert "auto_react" not in src

    def test_no_reaction_ui_in_edit_response(self):
        src = open("handlers_admin.py", encoding="utf-8").read()
        assert "resp_react_" not in src
        assert "Set/Change Reaction" not in src

    def test_no_reaction_registrations_in_bot(self):
        src = open("bot.py", encoding="utf-8").read()
        assert "resp_react_" not in src

    def test_welcome_has_no_react_call(self):
        src = open("handlers_start.py", encoding="utf-8").read()
        assert "react_to_message" not in src


class TestForceJoinAllButtons:
    def test_check_force_join_shows_all_targets(self):
        """Even when the bot is NOT admin in some targets (member check fails
        open), the join screen must still show a button for EVERY enabled
        target. (bug: only 1 of 3 showed)"""
        from types import SimpleNamespace
        from telegram.error import TelegramError
        from database import add_fj_target, delete_all_fj_targets
        from ui_extras import check_force_join

        delete_all_fj_targets()
        add_fj_target('@ch1', label='Channel 1', style='primary')
        add_fj_target('@grp2', label='Group 2', style='success')
        add_fj_target('https://t.me/+abc3', label='Group 3', style='danger')
        set_setting('fj_enabled', '1')
        set_setting('fj_message', '')

        class U:
            id = 999111; username = 'new'; first_name = 'New'
        class M:
            def __init__(self):
                self.replied = []; self.from_user = U(); self.chat = SimpleNamespace(id=999111)
            async def reply_text(self, *a, **k):
                self.replied.append((a, k))
                class S: message_id = 1; chat_id = 999111
                return S()
        class UP:
            def __init__(self):
                self.effective_user = U(); self.message = M()
                self.effective_message = self.message
                self.effective_chat = SimpleNamespace(id=999111)
        class BotNotAdminInSome:
            def __init__(self): self.calls = 0
            async def get_chat_member(self, chat_id=None, user_id=None):
                self.calls += 1
                if self.calls <= 1:
                    class MM: status = 'left'
                    return MM()
                raise TelegramError("Chat not found")
        class CTX:
            user_data = {}; bot = None; job_queue = None; application = None

        async def _run():
            ctx = CTX(); ctx.bot = BotNotAdminInSome(); upd = UP()
            await check_force_join(upd, ctx)
            n = 0
            for a, k in upd.message.replied:
                mk = k.get('reply_markup')
                if mk:
                    for row in mk.inline_keyboard:
                        n += len(row)
            return n

        n = asyncio.run(_run())
        assert n == 4, f"expected 4 buttons (3 join + verify), got {n}"


class TestHtmlSanitizer:
    """🐛 v143: Telegram strict HTML parser used to reject panels with
    unmatched/mis-nested tags → 'Can't parse entities' → bot looked stuck."""

    def test_normal_html_untouched(self):
        from utils import sanitize_html_tags
        assert sanitize_html_tags("<b>Hi</b> <i>there</i>") == "<b>Hi</b> <i>there</i>"

    def test_orphan_close_dropped(self):
        from utils import sanitize_html_tags
        out = sanitize_html_tags("</b> orphan")
        assert "orphan" in out
        assert "</b>" not in out

    def test_unclosed_open_autoclosed(self):
        from utils import sanitize_html_tags
        out = sanitize_html_tags("<b>unclosed bold")
        assert out.endswith("</b>")

    def test_misnested_fixed(self):
        # exact screenshot error: expected </i>, found </b>
        from utils import sanitize_html_tags
        import re
        out = sanitize_html_tags("<b>Bold <i>both</b> </i> end")
        # verify no mismatched pairs remain
        stack = []
        for m in re.finditer(r'</?(b|i|u|s|code|pre|a|blockquote|strong|em|tg-emoji)\b[^>]*>', out, re.I):
            tag = m.group(0); name = re.match(r'</?([a-zA-Z-]+)', tag).group(1).lower()
            if tag.startswith('</'):
                assert stack and stack[-1] == name, f"mismatch in {out!r}"
                stack.pop()
            else:
                if '/>' in tag: continue
                stack.append(name)
        assert not stack, f"unclosed in {out!r}"

    def test_smart_mode_sanitizes(self):
        from utils import smart_text_and_mode
        out, mode = smart_text_and_mode("<b>a <i>b</b></i>")
        assert mode == "HTML"
        assert "</b>" in out and "</i>" in out

    def test_premium_emoji_preserved(self):
        from utils import smart_text_and_mode
        t = '[[HTML]]<tg-emoji emoji-id="123">🔥</tg-emoji> <b>Shop</b>'
        out, mode = smart_text_and_mode(t)
        assert mode == "HTML"
        assert "tg-emoji" in out
