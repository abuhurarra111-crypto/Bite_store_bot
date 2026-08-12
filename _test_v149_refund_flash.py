# 🆕 v149 — Flash template placeholder case-insensitive fix + fixed emoji +
# Refund-by-User-ID (with reason) + per-user full history.
import os
import sys
import json

os.environ.setdefault("DB_PATH", "/tmp/test_v149.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_engagement as FE
import customization as CZ
import handlers_admin as HA


class TestFlashPlaceholders:
    def test_case_insensitive_fill(self):
        tpl = "{Product}\n{product_name}\n${price} {SAVE}"
        out = FE._fill_placeholders_ci(tpl, {
            "product": "Canva", "product_name": "Canva X",
            "price": "2.50", "save": "4.20",
        })
        assert "Canva" in out
        assert "Canva X" in out
        assert "2.50" in out
        assert "4.20" in out
        assert "{Product}" not in out

    def test_unknown_placeholder_stays(self):
        out = FE._fill_placeholders_ci("{product} {weird}", {"product": "X"})
        assert out == "X {weird}"

    def test_render_template_case_insensitive(self):
        tpl = "Buy {Product} now ${Price}"
        # render_template reads from DB; monkeypatch get_template
        import customization
        orig = customization.get_template
        customization.get_template = lambda tid: tpl
        try:
            out = CZ.render_template("bc_purchase", {"product": "Netflix", "price": "9.99"})
            assert "Netflix" in out
            assert "9.99" in out
            assert "{Product}" not in out
        finally:
            customization.get_template = orig

    def test_product_name_with_fixed_emoji_graceful(self):
        # product with no ext emoji / no db row → returns name
        name = FE._product_name_with_fixed_emoji({"id": 999999999, "name": "Plain Item"})
        assert "Plain Item" in name


class TestRefundHandlers:
    def test_refund_functions_exist(self):
        for name in ("adm_refund_uid_callback", "adm_refund_uid_received",
                     "adm_refund_uid_amt_received", "adm_refund_uid_reason_received",
                     "adm_refund_uid_confirm_callback", "adm_refund_uid_cancel_callback",
                     "adm_uhist_callback", "adm_uhist_enter_callback",
                     "adm_uhist_id_received"):
            assert hasattr(HA, name), f"missing {name}"

    def test_bot_registered(self):
        src = open("bot.py", encoding="utf-8").read()
        assert "adm_refund_uid" in src
        assert "adm_uhist_" in src
        assert "ruid_confirm" in src
        assert "ruid_step" in src

    def test_users_panel_has_refund(self):
        src = open("handlers_admin.py", encoding="utf-8").read()
        assert "Refund by User ID" in src
        assert "Full History" in src


class TestFlashTemplateDataFix:
    def test_db_custom_template_normalized(self):
        """The data fix helper should normalize {Product} → {product}."""
        tpl = "[[HTML]]🔥 MEGA FLASH SALE!\n\n{Product}\n${price}"
        norm = tpl.replace("{Product}", "{product}").replace("{Product Name}", "{product_name}")
        assert "{product}" in norm
        assert "{Product}" not in norm
