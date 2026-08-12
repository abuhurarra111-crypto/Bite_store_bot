# ============================================================
# 🧪 BITE STORE — v144.3: support-ticket close fix + replacement
# 2-step (API/upload/stock) + flash placeholder fix + Ai Tools
# Run:  pytest _test_v1443_fixes.py -v
# ============================================================
import os, tempfile

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="v1443_"), "t.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["BOT_TOKEN"] = "8826914364:AAHMuODKCwvYFB3qX5723-5LbTjRzhkEoms"
os.environ["ADMIN_ID"] = "7105782769"
os.environ["BYBIT_API_KEY"] = "K"
os.environ["BYBIT_API_SECRET"] = "S"

import database
from database import (setup_database, migrate_all, get_ticket, update_ticket,
                      get_connection)
setup_database(); migrate_all()


class TestSupportTicketClose:
    def test_update_ticket_closed(self):
        # create ticket
        from database import create_ticket
        tid = create_ticket(111, "Test", "desc")
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE support_tickets SET status='open' WHERE id=?", (tid,))
        conn.commit(); conn.close()
        update_ticket(tid, status='closed')
        assert get_ticket(tid)['status'] == 'closed'

    def test_view_skip_answer_param(self):
        import inspect
        from handlers_support import adm_st_view_callback
        sig = inspect.signature(adm_st_view_callback)
        assert '_skip_answer' in sig.parameters


class TestReplacementFlow:
    def test_new_callbacks_exist(self):
        import support_replacement as SR
        for fn in ("admin_replace_api_callback", "admin_replace_upload_callback",
                   "admin_replace_upload_received", "admin_replace_stock_callback"):
            assert hasattr(SR, fn), f"missing {fn}"

    def test_registered_in_bot(self):
        src = open("bot.py", encoding="utf-8").read()
        assert '("^adm_repx_api_",' in src
        assert '("^adm_repx_up_",' in src
        assert '("^adm_repx_stock_",' in src
        assert 'admin_replace_api_callback' in src


class TestFlashPlaceholder:
    def test_flash_price_replaced(self):
        from fake_engagement import build_flash_message
        p = {"id": 1, "name": "Netflix", "price": 10.0, "flash_price": 5.0}
        # custom template with {price} + a stray {old_price} alias
        from fake_engagement import set_flash_custom
        set_flash_custom("🔥 {product} SALE! Only ${price} (was ${old_price})")
        out = build_flash_message(p)
        assert "$5.00" in out, out
        assert "$10.00" in out, out
        assert "{price}" not in out, f"raw placeholder leaked: {out}"
        assert "{old_price}" not in out, f"raw placeholder leaked: {out}"
        set_flash_custom("")

    def test_flash_unknown_placeholder_safe(self):
        from fake_engagement import build_flash_message
        from fake_engagement import set_flash_custom
        p = {"id": 1, "name": "Spotify", "price": 9.0, "flash_price": 4.0}
        set_flash_custom("🎁 {product} now ${price} (custom {unknown_thing})")
        out = build_flash_message(p)
        assert "$4.00" in out, out  # price still filled
        set_flash_custom("")


class TestAiToolsSupplier:
    def test_supplier_registered(self):
        # Ai Tools is a Canboso adapter — check preset exists
        from ext_suppliers import SUPPLIER_PRESETS
        assert any('ai tools' in v['name'].lower() for v in SUPPLIER_PRESETS.values())
        assert 'canboso' in SUPPLIER_PRESETS["canboso"]["adapter"]
