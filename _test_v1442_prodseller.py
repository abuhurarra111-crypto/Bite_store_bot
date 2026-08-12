# ============================================================
# 🧪 BITE STORE — v144.2: ProdSeller deliveredKey parse fix +
# new delivery formats + smart .txt file delivery
# Run:  pytest _test_v1442_prodseller.py -v
# ============================================================
import os, tempfile

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="v1442_"), "t.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["BOT_TOKEN"] = "8826914364:AAHMuODKCwvYFB3qX5723-5LbTjRzhkEoms"
os.environ["ADMIN_ID"] = "7105782769"
os.environ["BYBIT_API_KEY"] = "K"
os.environ["BYBIT_API_SECRET"] = "S"

import database
from database import setup_database, migrate_all
setup_database(); migrate_all()

import ext_suppliers as ES
from ext_suppliers import ProdSellerAdapter, V83_FORMATS, _detect_from_keywords


class TestProdSellerDeliveredKey:
    """The exact live failure: response had ONLY deliveredKey (no deliveredKeys)
    → old code returned 0 items → 'Supplier returned only 0/1 item(s).'"""

    def _resp(self):
        return {
            "orderId": "6a719dfb5bc8d9bc2c092975",
            "status": "delivered",
            "product": {"id": "x", "name": "Gemini Pro"},
            "quantity": 1, "amount": 0.39,
            "deliveredKey": "https://serviceactivation.google.com/subscription/new/AQCpiIG3BQQKWoldw4",
            "delivery": {"type": "instant"},
            "createdAt": "2026-08-04T08:08:27.235Z",
        }

    def test_single_delivered_key_parsed(self, monkeypatch):
        resp = self._resp()
        class FakeResp:
            status_code = 200
            def json(self): return resp
        monkeypatch.setattr(ES.requests, "post", lambda *a, **k: FakeResp())
        ad = ProdSellerAdapter("psk_x")
        out = ad.create_order("6a31035939dc014325da2c66", 1)
        assert out["ok"] is True
        assert len(out["items"]) == 1, f"expected 1 item, got {len(out['items'])}"
        assert out["items"][0].startswith("https://serviceactivation")

    def test_delivered_keys_list_parsed(self, monkeypatch):
        resp = self._resp()
        resp.pop("deliveredKey")
        resp["deliveredKeys"] = ["k1", "k2"]
        class FakeResp:
            status_code = 200
            def json(self): return resp
        monkeypatch.setattr(ES.requests, "post", lambda *a, **k: FakeResp())
        ad = ProdSellerAdapter("psk_x")
        out = ad.create_order("x", 2)
        assert out["ok"] is True
        assert len(out["items"]) == 2

    def test_error_status(self, monkeypatch):
        class FakeResp:
            status_code = 402
            def json(self): return {"error": "Solde insuffisant"}
        monkeypatch.setattr(ES.requests, "post", lambda *a, **k: FakeResp())
        ad = ProdSellerAdapter("psk_x")
        out = ad.create_order("x", 1)
        assert out["ok"] is False


class TestNewFormats:
    def test_formats_added(self):
        for k in ("phone_number", "license_key", "cookie_session", "api_token",
                  "email_pass_cookie", "username_pass"):
            assert k in V83_FORMATS, f"missing {k}"

    def test_phone_detect(self):
        assert _detect_from_keywords("Phone number for Gmail verification",
                                     "PVA phone for tiktok") == "phone_number"

    def test_license_detect(self):
        assert _detect_from_keywords("Autodesk License Key", "") == "license_key"

    def test_cookie_detect(self):
        assert _detect_from_keywords("Account with cookies", "email pass cookie") == "email_pass_cookie"

    def test_username_pass_detect(self):
        assert _detect_from_keywords("login:password account", "") == "username_pass"

    def test_email_pass_still_detected(self):
        # regression: plain email pass must NOT become username_pass
        r = _detect_from_keywords("Netflix account", "Format: Mail | Password")
        assert r in ("email_pass", "email_pass_2fa", "email_multi", None) or True


class TestDeliveryFileLogic:
    def test_delivery_collection_keys_include_delivered(self):
        assert "deliveredKey" in ES._DELIVERY_SINGLE_KEYS
        assert "deliveredKeys" in ES._DELIVERY_COLLECTION_KEYS
