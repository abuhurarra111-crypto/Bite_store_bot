# ============================================================
# 🧪 BITE STORE — v136: ProdSeller adapter + supplier presets + bulk unsync
# Run:  pytest _test_v136_suppliers.py -v   (isolated DB)
# ============================================================
import os, tempfile, json
from types import SimpleNamespace

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="v136_"), "t.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["BOT_TOKEN"] = "1:2"
os.environ["ADMIN_ID"] = "9"
os.environ["BYBIT_API_KEY"] = "K"
os.environ["BYBIT_API_SECRET"] = "S"

import database
from database import (setup_database, migrate_all, get_connection,
                      add_supplier, get_product, ensure_product_accounts_table)
setup_database(); migrate_all()

import ext_suppliers as ES
from ext_suppliers import (ProdSellerAdapter, SUPPLIER_PRESETS, ADAPTERS,
                           add_supplier as es_add, get_supplier,
                           upsert_ext_product, mirror_ext_to_products,
                           ensure_ext_supplier_tables)


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload) if not isinstance(payload, str) else payload
        self.headers = {}

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError(self._payload)
        return self._payload


PRODUCTS_PAYLOAD = {"products": [
    {"id": "64abc", "name": "Netflix 1 Month", "description": "Premium account",
     "price": 4.99, "publicPrice": 5.99, "inStock": True},
    {"id": "64xyz", "name": "Spotify", "description": "", "price": 2.5,
     "publicPrice": 3.0, "inStock": False},
]}


def _fake_requests(monkeypatch, get_payload=PRODUCTS_PAYLOAD, bal=25.5):
    class _R:
        def __init__(self, payload, status=200):
            self.payload, self.status_code = payload, status
        def json(self):
            return self.payload
    def fake_get(url, **kw):
        if url.endswith("/balance"):
            return _R({"balance": bal})
        return _R(get_payload)
    def fake_post(url, headers=None, **kw):
        body = kw.get("json", {})
        return _R({"orderId": "64xyz", "status": "delivered", "amount": 4.99,
                   "deliveredKey": "email:pass123",
                   "deliveredKeys": ["email:pass123", "email2:pass2"]})
    monkeypatch.setattr(ES.requests, "get", fake_get)
    monkeypatch.setattr(ES.requests, "post", fake_post)


class TestProdSellerAdapter:
    def test_registered(self):
        assert "prodseller" in ADAPTERS
        assert ADAPTERS["prodseller"] is ProdSellerAdapter

    def test_headers(self):
        ad = ProdSellerAdapter("psk_123", None)
        h = ad._headers()
        assert h.get("X-API-Key") == "psk_123"

    def test_fetch_products(self, monkeypatch):
        _fake_requests(monkeypatch)
        ad = ProdSellerAdapter("psk_123", None)
        prods = ad.fetch_products()
        assert len(prods) == 2
        p0 = prods[0]
        assert p0["remote_id"] == "64abc"
        assert abs(p0["cost_usd"] - 4.99) < 0.001
        assert p0["stock"] >= 1  # v145: real stock (was hardcoded 999)
        assert prods[1]["stock"] == 0

    def test_fetch_balance(self, monkeypatch):
        _fake_requests(monkeypatch)
        ad = ProdSellerAdapter("psk_123", None)
        assert abs(ad.fetch_balance() - 25.5) < 0.001

    def test_create_order(self, monkeypatch):
        _fake_requests(monkeypatch)
        ad = ProdSellerAdapter("psk_123", None)
        out = ad.create_order("64abc", 2)
        assert out["ok"] is True
        assert len(out["items"]) == 2
        assert out["order_id"] == "64xyz"

    def test_create_order_error(self, monkeypatch):
        class _R:
            status_code = 402
            def json(self):
                return {"error": "Solde insuffisant"}
        monkeypatch.setattr(ES.requests, "post", lambda *a, **k: _R())
        ad = ProdSellerAdapter("psk_123", None)
        out = ad.create_order("64abc", 1)
        assert out["ok"] is False
        assert "Solde" in out["error"]


class TestPresets:
    def test_all_presets_present(self):
        for k in ("canboso", "shop_cron", "sinhle", "akunding", "mmostore",
                  "tunvnmmo", "prodseller"):
            assert k in SUPPLIER_PRESETS, k
            pr = SUPPLIER_PRESETS[k]
            assert pr["adapter"] in ADAPTERS
            assert pr["base_url"]

    def test_prodseller_preset(self):
        pr = SUPPLIER_PRESETS["prodseller"]
        assert pr["adapter"] == "prodseller"
        assert "51.77.244.194" in pr["base_url"]


class TestBulkUnsync:
    def _seed(self):
        ensure_ext_supplier_tables()
        sid = es_add("TestSup", "prodseller", "http://51.77.244.194/v1", "psk_x")
        # catalog + mirror to shop
        eid = upsert_ext_product(sid, "r1", "Netflix", "d", 4.99, 10)
        mirror_ext_to_products(eid)
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT shop_product_id FROM ext_products WHERE id=?", (eid,))
        pid = c.fetchone()[0]
        conn.close()
        return sid, eid, pid

    def test_unsync_removes_shop_keeps_catalog(self):
        from supplier_automation import _unsync_supplier_shop_products
        sid, eid, pid = self._seed()
        n_shop, n_ext = _unsync_supplier_shop_products(sid)
        assert n_shop >= 1
        # shop product gone
        assert get_product(pid) is None
        # catalog row still exists but unlinked
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT synced_to_shop, shop_product_id FROM ext_products WHERE id=?", (eid,))
        row = c.fetchone(); conn.close()
        assert int(row["synced_to_shop"]) == 0
        assert int(row["shop_product_id"]) == 0
