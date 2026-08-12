# ============================================================
# 🧪 BITE STORE — v145: ProdSeller stock/qty fix, notification
# enrich, .txt file save+download, user search, username sync,
# ticket auto-close
# Run:  pytest _test_v145_fixes.py -v
# ============================================================
import os, tempfile

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="v145_"), "t.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["BOT_TOKEN"] = "8826914364:AAHMuODKCwvYFB3qX5723-5LbTjRzhkEoms"
os.environ["ADMIN_ID"] = "7105782769"
os.environ["BYBIT_API_KEY"] = "K"
os.environ["BYBIT_API_SECRET"] = "S"

import database
from database import setup_database, migrate_all, get_connection, ensure_column
setup_database(); migrate_all()

import ext_suppliers as ES
from ext_suppliers import ProdSellerAdapter
from utils import order_payment_context, payment_method_label


class TestProdSellerStock:
    def test_stock_from_api_not_999(self, monkeypatch):
        """v146: real stock field respected; in-stock w/o stock field gets a
        stable pseudo-random number (not 999, not 1-for-everything)."""
        import json
        payload = {"products": [
            {"id": "a", "name": "X", "price": 1.0, "inStock": True, "stock": 12},
            {"id": "b", "name": "Y", "price": 2.0, "inStock": False, "stock": 0},
            {"id": "c", "name": "Z", "price": 3.0, "inStock": True},  # no stock field
            {"id": "d", "name": "W", "price": 4.0, "inStock": True, "sold": 50000},
        ]}
        class FR:
            status_code = 200
            def json(self): return payload
        monkeypatch.setattr(ES.requests, "get", lambda *a, **k: FR())
        ad = ProdSellerAdapter("psk_x")
        prods = ad.fetch_products()
        assert prods[0]["stock"] == 12, "must use real stock, not 999"
        assert prods[1]["stock"] == 0
        s_c = prods[2]["stock"]
        assert s_c > 0 and s_c != 999, f"in-stock w/o number → pseudo stock, got {s_c}"
        s_d = prods[3]["stock"]
        assert s_d > 0 and s_d != 999
        # stable: fetching again yields the same value for the same product
        prods2 = ad.fetch_products()
        assert prods2[2]["stock"] == s_c, "pseudo stock must be stable per product"
        # popular item (sold=50000) gets more stock than the modest one
        assert s_d > s_c, f"popular item should show more stock ({s_d} vs {s_c})"

    def test_quantity_cap_removed(self, monkeypatch):
        """create_order must NOT cap at 100 (was the 200→100 bug)."""
        import json
        captured = {}
        class FR:
            status_code = 200
            def json(self):
                return {"orderId": "o1", "status": "delivered", "quantity": 200,
                        "deliveredKeys": [f"k{i}" for i in range(200)]}
        def fake_post(url, headers=None, json=None, **k):
            captured['body'] = json
            return FR()
        monkeypatch.setattr(ES.requests, "post", fake_post)
        ad = ProdSellerAdapter("psk_x")
        out = ad.create_order("x", 200)
        assert captured['body']['quantity'] == 200, captured['body']
        assert len(out['items']) == 200


class TestPaymentContext:
    def test_points_order(self):
        lines = order_payment_context(999999)
        assert isinstance(lines, list)

    def test_method_labels(self):
        assert "Bybit" in payment_method_label("bybit_pay")
        assert "TRC20" in payment_method_label("binance_usdt_trc20")
        assert "BEP20" in payment_method_label("bybit_usdt_bep20")
        assert "EasyPaisa" in payment_method_label("easypaisa")
        assert "JazzCash" in payment_method_label("jazzcash")
        assert "Points" in payment_method_label("points")


class TestDeliveryFileColumn:
    def test_column_exists(self):
        conn = get_connection(); c = conn.cursor()
        cols = [r[1] for r in c.execute("PRAGMA table_info(orders)").fetchall()]
        conn.close()
        assert "delivery_file_id" in cols


class TestUserSearch:
    def test_callbacks_exist(self):
        import handlers_admin as HA
        assert hasattr(HA, "adm_users_search_callback")
        assert hasattr(HA, "adm_users_search_received")

    def test_registered_in_bot(self):
        src = open("bot.py", encoding="utf-8").read()
        assert '("^adm_users_search$",' in src


class TestTicketAutoClose:
    def test_job_exists(self):
        import support_replacement as SR
        assert hasattr(SR, "ticket_auto_close_job")
        assert hasattr(SR, "get_stale_open_tickets")

    def test_stale_scan(self):
        import support_replacement as SR
        stale = SR.get_stale_open_tickets(minutes=30)
        assert isinstance(stale, list)

    def test_scheduled_in_bot(self):
        src = open("bot.py", encoding="utf-8").read()
        assert "ticket_auto_close_job" in src
