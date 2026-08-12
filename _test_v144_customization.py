# ============================================================
# 🧪 BITE STORE — v144: REBUILT Customization (hub, search,
# themes, backup, banner, formats grid/list, category colors)
# Run:  pytest _test_v144_customization.py -v
# ============================================================
import os, tempfile, json, asyncio

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="v144_"), "t.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["BOT_TOKEN"] = "8826914364:AAHMuODKCwvYFB3qX5723-5LbTjRzhkEoms"
os.environ["ADMIN_ID"] = "7105782769"
os.environ["BYBIT_API_KEY"] = "K"
os.environ["BYBIT_API_SECRET"] = "S"

import database
from database import (setup_database, migrate_all, get_setting, set_setting,
                      get_connection)
setup_database(); migrate_all()

import handlers_admin as HA
from handlers_admin import (_render_customization_hub, _cz_summary_lines,
                            _collect_backup, _THEMES, cz_theme_apply_callback,
                            cz_fmt_callback, cz_banner_toggle_callback,
                            cz_catcolor_set_callback)
import customization as CZ


class TestHub:
    def test_summary_lines(self):
        lines = _cz_summary_lines()
        assert len(lines) >= 3
        assert any("Size" in l for l in lines)
        assert any("Toggles" in l for l in lines)

    def test_themes_defined(self):
        for k in ("classic", "colorful", "dark", "minimal", "premium"):
            assert k in _THEMES
            cfg = _THEMES[k]
            assert "button_size" in cfg
            assert "display_format" in cfg

    def test_backup_collects_json(self):
        set_setting("btn_label_main_shop_medium", "🛒 Shop")
        raw = _collect_backup()
        data = json.loads(raw)
        assert isinstance(data, dict)
        assert "btn_label_main_shop_medium" in data


class TestFormatSupport:
    def test_display_format_valid(self):
        from handlers_shop import _get_display_format
        for v in ("raw", "carousel", "grid", "list"):
            set_setting("display_format", v)
            assert _get_display_format() == v
        set_setting("display_format", "bogus")
        assert _get_display_format() == "raw"
        set_setting("display_format", "raw")


class TestBanner:
    def test_banner_default_off(self):
        assert get_setting("home_banner_enabled", "0") == "0"

    def test_banner_text_stored(self):
        set_setting("home_banner_text", "🔥 SALE {shop_name}")
        set_setting("home_banner_enabled", "1")
        assert get_setting("home_banner_text", "") == "🔥 SALE {shop_name}"
        assert get_setting("home_banner_enabled", "0") == "1"


class TestCategoryColors:
    def test_catcolor_stored(self):
        set_setting("catcolor_5", "success")
        assert get_setting("catcolor_5", "") == "success"

    def test_catcolor_cleared(self):
        set_setting("catcolor_5", "")
        assert get_setting("catcolor_5", "") == ""


class TestGridKeyboard:
    def test_grid_packs_two_per_row(self):
        """all_products_keyboard in grid format → buttons 2 per row."""
        from keyboards import all_products_keyboard
        from types import SimpleNamespace
        set_setting("display_format", "grid")
        set_setting("button_size", "medium")
        prods = [
            {"id": 1, "name": "Netflix", "price": 5.0, "stock": 3, "category_id": 0},
            {"id": 2, "name": "Spotify", "price": 2.0, "stock": 5, "category_id": 0},
            {"id": 3, "name": "Canva", "price": 4.0, "stock": 0, "category_id": 0},
        ]
        kb, _pg, _tp = all_products_keyboard(prods, page=1, per_page=10, user=None)
        rows = kb.inline_keyboard
        product_rows = [r for r in rows if any("prod_" in (b.callback_data or "") for b in r)]
        # first two products should be in ONE row (2 per row)
        assert len(product_rows[0]) == 2, f"grid should pack 2/row, got {len(product_rows[0])}"
        assert len(product_rows[1]) == 1  # third product alone
        set_setting("display_format", "raw")


class TestBinanceFlowButtons:
    """🐛 v144.1: Binance flow ke saare buttons editor mein aane chahiye."""

    def test_registry_buttons_exist(self):
        from button_system import BUTTONS
        for bid in ("pay_copy_binance_payid", "pay_copy_usdt_address",
                    "pay_cancel_payment"):
            assert bid in BUTTONS, f"missing registry button {bid}"
            assert BUTTONS[bid]["group"] == "pay"

    def test_binance_flow_screen_has_all(self):
        import customization as CZ
        node = CZ.SCREEN_TREE["binance_flow_screen"]
        ids = {b["id"] for b in node["buttons"]}
        for bid in ("pay_binance", "pay_usdt_bep20", "pay_usdt_trc20",
                    "pay_copy_binance_payid", "pay_copy_usdt_address",
                    "pay_cancel_payment"):
            assert bid in ids, f"missing in screen: {bid}"

    def test_make_flow_btn_renders(self):
        from handlers_order import _make_flow_btn
        import telegram
        b1 = _make_flow_btn("pay_copy_binance_payid",
                            copy_text=telegram.CopyTextButton("123"))
        b2 = _make_flow_btn("pay_cancel_payment", callback_data="cancel_order")
        assert "Binance Pay ID" in b1.text or "Pay ID" in b1.text
        assert "Cancel" in b2.text
        assert b2.callback_data == "cancel_order"
