# 🆕 v147 — 8 bug fixes:
#   1. sanitize_html_tags nested same-tag balance (Buy Now on manual products)
#   2. replacement: refund button + rejection reason
#   3. fake activity blocked during maintenance
#   4. groups: bot never auto-responds (incl. Temporary error)
#   5. fake deposit alerts use ONLY enabled payment methods (all methods)
#   6. buy-now emoji: supplier fixed emoji vs own-name emoji
#   7. broadcast button: custom link / product checkout deep link
#   8. pinned announcements: delete post everywhere / unpin push only
import os
import sys
import pytest

os.environ.setdefault("DB_PATH", "/tmp/test_v147.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import utils
import fake_engagement as FE
import per_user_activity as PUA


# ── Bug1: nested same-tag balancing ──────────────────────────────
class TestSanitizeNestedSameTag:
    def test_nested_b_balanced(self):
        """<b><tg-emoji>🎨</tg-emoji><b>Canva</b></b> → must stay balanced."""
        html = '📦 <b><tg-emoji emoji-id="5">🎨</tg-emoji><b>Canva 500 User Panel</b></b>'
        out = utils.sanitize_html_tags(html)
        assert out.count("<b>") == out.count("</b>"), out
        assert "<b><tg-emoji" in out or "<b>🎨" in out or "tg-emoji" in out

    def test_normal_tags_untouched(self):
        out = utils.sanitize_html_tags("<b>Hello</b> <i>world</i>")
        assert out == "<b>Hello</b> <i>world</i>"

    def test_orphan_close_dropped(self):
        out = utils.sanitize_html_tags("</b>hello")
        assert out.count("<b>") == out.count("</b>")

    def test_smart_text_mode_nested_name(self):
        """The exact Bug1 repro: product name with <b> inside a Markdown bold."""
        name = '[[HTML]]<tg-emoji emoji-id="5309754771102525647">🎨</tg-emoji><b>Canva 500 User Panel</b>'
        msg = "📦 *" + name + "*\n🔢 Quantity: *1*"
        text, mode = utils.smart_text_and_mode(msg, "Markdown")
        assert mode == "HTML"
        assert text.count("<b>") == text.count("</b>"), text


# ── Bug3: maintenance gate in fake activity ──────────────────────
class TestMaintenanceGate:
    def test_helper_exists(self):
        assert hasattr(PUA, "_activity_blocked_by_maintenance")

    def test_fake_broadcast_has_maint_gate(self):
        src = open(FE.__file__, encoding="utf-8").read()
        assert "is_maintenance_on" in src
        assert "SKIPPED — maintenance ON" in src


# ── Bug5: enabled payment methods only ───────────────────────────
class TestEnabledPaymentMethods:
    def test_list_covers_all_methods(self):
        src = open(FE.__file__, encoding="utf-8").read()
        for m in ("bybit_pay", "usdt_trc20", "usdt_bep20", "bybit_usdt_bep20", "jazzcash", "easypaisa"):
            assert f'("{m}"' in src or f'("{m}",' in src, f"missing {m}"
        src2 = open(PUA.__file__, encoding="utf-8").read()
        for m in ("bybit_pay", "usdt_trc20", "usdt_bep20", "bybit_usdt_bep20", "jazzcash", "easypaisa"):
            assert f'("{m}"' in src2 or f'("{m}",' in src2, f"missing {m} in PUA"


# ── Bug6: buy-now emoji helper ───────────────────────────────────
class TestProductBuyEmoji:
    def test_helper_exists(self):
        assert hasattr(FE, "_product_buy_emoji")

    def test_own_product_uses_name_emoji(self):
        # with a DB that has no such product → graceful ("", "")
        eid, ech = FE._product_buy_emoji(999999999)
        assert eid == "" and ech == ""


# ── Bug7: checkout deep link ─────────────────────────────────────
class TestCheckoutDeepLink:
    def test_parse_chk_arg(self):
        from handlers_start import _parse_start_arg
        assert _parse_start_arg("chk_214") == (0, 0, 214)
        assert _parse_start_arg("buy_9") == (0, 9, 0)


# ── Bug8: pinned announcement delete/unpin helpers ───────────────
class TestPinnedAnnouncements:
    def test_unpin_delete_param(self):
        import inspect
        from loyalty_extras import unpin_and_deactivate
        sig = inspect.signature(unpin_and_deactivate)
        assert "delete_messages" in sig.parameters

    def test_admin_button_state_actions(self):
        """broadcast button builder supports bot/url/product actions."""
        import handlers_admin as HA
        from telegram import InlineKeyboardMarkup
        class Ctx:
            user_data = {"broadcast_button": {"label": "Buy", "color": "green", "action": "product", "pid": 214}}
        kb = HA._admin_button_from_state(Ctx(), bot_username="bite_storee_bot")
        assert kb is not None
        btn = kb.inline_keyboard[0][0]
        assert "chk_214" in (btn.url or ""), btn.url
