# -*- coding: utf-8 -*-
"""
v170.99 REGRESSION SUITE — CAPCUT 6M refund-loop fix (2 bugs, 2026-09-12)

Bug A (loop): ProdSeller $slice server bug par product out-of-stock mark hota
  tha, LEKIN autosync (3 min) supplier ki JHOOTI listed stock se 0→restore kar
  deta tha → naya order → fail → auto-refund (orders #4295/#4296/#4322).
  FIX: ext_products.stock_broken_until cooldown flag — active ho to autosync
  stock apply SKIP; delivery success par flag clear.

Bug B (deadline reset): _set_order_supplier_retry_pending HAR failure par
  due=now+300 reset karta tha → infinite retry loop possible.
  FIX: already-pending + future due → original deadline preserve.
  PLUS: supplier_retry_refund_job me AUTO-RETRY (+60s/+120s staggered,
  max 2 attempts) — transient failures khud recover ho jayen.

Run: python3 -m pytest test_v170_99_regression.py -v
"""
import os, sys, shutil, tempfile, asyncio, sqlite3, random

# ── env PEHLE — database import se pehle ──
_TMPDIR = tempfile.mkdtemp(prefix="v17099_regr_")
_REGDB = os.path.join(_TMPDIR, "regression.db")
os.environ["DB_PATH"] = _REGDB
os.environ.setdefault("BOT_TOKEN", "1:test")
os.environ.setdefault("ADMIN_ID", "7105782769")
os.environ.setdefault("GEMINI_API_KEY", "x")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_SRC_DB = "/home/user/bite_store_restore_ready.db"
if os.path.exists(_SRC_DB):
    shutil.copy(_SRC_DB, _REGDB)

import pytest


def _db():
    conn = sqlite3.connect(_REGDB, timeout=10); conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


# ══════════════════════════════════════════════════════════════
# Fix A — stock_broken_until cooldown flag
# ══════════════════════════════════════════════════════════════
class TestStockBrokenFlag:
    def test_ensure_column_stock_broken_until(self):
        from ext_suppliers import ensure_ext_supplier_tables
        ensure_ext_supplier_tables()
        conn = _db()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(ext_products)")]
        conn.close()
        assert "stock_broken_until" in cols, "stock_broken_until column missing"

    def test_update_ext_product_accepts_flag(self):
        from ext_suppliers import ensure_ext_supplier_tables, get_ext_product, update_ext_product
        ensure_ext_supplier_tables()
        conn = _db()
        conn.execute("DELETE FROM ext_products WHERE remote_id='v999flag'")
        cur = conn.execute(
            """INSERT INTO ext_products (supplier_id, remote_id, name, cost_usd, stock)
               VALUES (1, 'v999flag', 'V99 Flag Test', 1.0, 5)""")
        epid = cur.lastrowid; conn.commit(); conn.close()
        assert update_ext_product(epid, stock_broken_until=12345.5) is not False
        ep = get_ext_product(epid)
        assert float(ep.get("stock_broken_until") or 0) == 12345.5
        # clear bhi kaam kare
        assert update_ext_product(epid, stock_broken_until=0) is not False
        assert float(get_ext_product(epid).get("stock_broken_until") or 0) == 0.0

    def test_mark_unavailable_sets_cooldown(self):
        import time as _t
        from ext_suppliers import (ensure_ext_supplier_tables, get_ext_product,
                                   update_ext_product, _mark_supplier_product_unavailable,
                                   _stock_broken_cooldown)
        from database import set_setting
        ensure_ext_supplier_tables()
        conn = _db()
        conn.execute("DELETE FROM ext_products WHERE remote_id='v999mark'")
        cur = conn.execute(
            """INSERT INTO ext_products (supplier_id, remote_id, name, cost_usd, stock)
               VALUES (1, 'v999mark', 'V99 Mark Test', 2.0, 7)""")
        epid = cur.lastrowid; conn.commit(); conn.close()
        ep = get_ext_product(epid)

        was = set_setting("supplier_stock_broken_cooldown", "900")
        try:
            before = _t.time()
            _mark_supplier_product_unavailable(ep, 0, "plan executor $slice test")
            after = _t.time()
            ep2 = get_ext_product(epid)
            assert int(ep2.get("stock") or 0) == 0, "stock 0 hona chahiye"
            until = float(ep2.get("stock_broken_until") or 0)
            assert until >= before + 899, f"cooldown flag set nahi hua: {until}"
            assert until <= after + _stock_broken_cooldown() + 5
        finally:
            if was is not None:
                set_setting("supplier_stock_broken_cooldown", was)
            else:
                conn = _db()
                conn.execute("DELETE FROM bot_settings WHERE key='supplier_stock_broken_cooldown'")
                conn.commit(); conn.close()

    def test_cooldown_setting_clamp(self):
        from ext_suppliers import _stock_broken_cooldown
        from database import set_setting
        # default (koi setting nahi)
        conn = _db()
        conn.execute("DELETE FROM bot_settings WHERE key='supplier_stock_broken_cooldown'")
        conn.commit(); conn.close()
        assert _stock_broken_cooldown() == 900
        # custom 60 → 60
        set_setting("supplier_stock_broken_cooldown", "60")
        assert _stock_broken_cooldown() == 60
        # 10 → clamp to 60 (minimum)
        set_setting("supplier_stock_broken_cooldown", "10")
        assert _stock_broken_cooldown() == 60
        conn = _db()
        conn.execute("DELETE FROM bot_settings WHERE key='supplier_stock_broken_cooldown'")
        conn.commit(); conn.close()

    def test_sync_blocked_helper(self):
        import time as _t
        from supplier_automation import _stock_sync_blocked
        now = _t.time()
        assert _stock_sync_blocked({"stock_broken_until": now + 500}, now) is True
        assert _stock_sync_blocked({"stock_broken_until": now - 500}, now) is False
        assert _stock_sync_blocked({"stock_broken_until": 0}, now) is False
        assert _stock_sync_blocked({}, now) is False
        assert _stock_sync_blocked(None, now) is False
        assert _stock_sync_blocked({"stock_broken_until": "garbage"}, now) is False


# ══════════════════════════════════════════════════════════════
# Fix A END-TO-END — autosync jhooti stock restore NAHI kare
# ══════════════════════════════════════════════════════════════
class TestAutosyncBrokenLoopGuard:
    def _setup(self):
        import ext_suppliers as ex
        conn = _db()
        conn.execute("DELETE FROM ext_products WHERE remote_id='v999loop'")
        conn.execute("DELETE FROM ext_suppliers WHERE name='V99 Loop Supplier'")
        cur = conn.execute(
            "INSERT INTO ext_suppliers (name, base_url, api_key, adapter, enabled) "
            "VALUES ('V99 Loop Supplier', 'https://v99.test', 'k', 'prodseller', 1)")
        sid = cur.lastrowid
        ecur = conn.execute(
            """INSERT INTO ext_products (supplier_id, remote_id, name, cost_usd, stock,
               sell_price, markup_pct, synced_to_shop, owner_active, source_active)
               VALUES (?, 'v999loop', 'V99 Loop Product', 1.0, 0, 1.4, 40, 1, 1, 1)""", (sid,))
        epid = ecur.lastrowid
        conn.commit(); conn.close()
        pid, _ = ex.mirror_ext_to_products(epid)
        return sid, epid, pid

    def test_autosync_skips_broken_then_recovers(self):
        import time as _t
        import ext_suppliers as ex
        import supplier_automation as sauto
        import async_adapter_helpers as aah

        sid, epid, pid = self._setup()
        sent = []

        class FakeBot:
            async def send_message(self, chat_id, text, **kw):
                sent.append(text); return True
        class FakeCtx:
            bot = FakeBot()

        # fresh fetch: supplier JHOOTI listed stock=50 deta hai (real ProdSeller scenario)
        async def fake_fetch(ad):
            return [{"remote_id": "v999loop", "name": "V99 Loop Product",
                     "cost_usd": 1.0, "stock": 50, "raw": {"inStock": True}}]

        orig = {"ls": ex.list_suppliers, "ga": ex.get_adapter_for_supplier,
                "afc": aah.async_fetch_products, "en": sauto.is_autosync_enabled}
        ex.list_suppliers = lambda include_disabled=False: [
            {"id": sid, "name": "V99 Loop Supplier", "enabled": 1,
             "base_url": "https://v99.test", "api_key": "k"}]
        ex.get_adapter_for_supplier = lambda sup: object()
        aah.async_fetch_products = fake_fetch
        sauto.is_autosync_enabled = lambda: True
        try:
            # ── STEP 1: broken flag SET (mark→cooldown) → autosync ko skip karna hai ──
            from ext_suppliers import update_ext_product
            update_ext_product(epid, stock=0, stock_broken_until=_t.time() + 900)
            asyncio.run(sauto.autosync_price_stock_job(FakeCtx()))
            conn = _db()
            row = conn.execute(
                "SELECT stock, stock_broken_until FROM ext_products WHERE id=?", (epid,)).fetchone()
            conn.close()
            assert int(row["stock"]) == 0, \
                f"BROKEN FLAG ACTIVE hone par bhi autosync stock restore kar gaya ({row['stock']}) — LOOP BUG!"
            assert float(row["stock_broken_until"] or 0) > _t.time(), "flag clear ho gaya ( hona nahi tha)"

            # ── STEP 2: flag EXPIRED → autosync wapas fresh stock lagaye (recovery) ──
            update_ext_product(epid, stock_broken_until=_t.time() - 1)
            asyncio.run(sauto.autosync_price_stock_job(FakeCtx()))
            conn = _db()
            row = conn.execute(
                "SELECT stock FROM ext_products WHERE id=?", (epid,)).fetchone()
            conn.close()
            assert int(row["stock"]) == 50, \
                f"flag expire hone par stock restore nahi hua ({row['stock']}) — recovery broken!"
        finally:
            ex.list_suppliers = orig["ls"]
            ex.get_adapter_for_supplier = orig["ga"]
            aah.async_fetch_products = orig["afc"]
            sauto.is_autosync_enabled = orig["en"]


# ══════════════════════════════════════════════════════════════
# Fix A — delivery success → flag clear
# ══════════════════════════════════════════════════════════════
class TestDeliveredClearsFlag:
    def test_clear_broken_for_order_oid(self):
        import time as _t
        import ext_suppliers as ex
        conn = _db()
        conn.execute("DELETE FROM ext_products WHERE remote_id='v999clr'")
        cur = conn.execute(
            """INSERT INTO ext_products (supplier_id, remote_id, name, cost_usd, stock,
               sell_price, markup_pct, synced_to_shop, owner_active, source_active)
               VALUES (1, 'v999clr', 'V99 Clear Test', 1.0, 0, 1.4, 40, 1, 1, 1)""")
        epid = cur.lastrowid; conn.commit(); conn.close()
        pid, _ = ex.mirror_ext_to_products(epid)
        ex.update_ext_product(epid, stock_broken_until=_t.time() + 900)

        uid = 910000000 + random.randint(1, 999999)
        conn = _db()
        cur = conn.execute(
            """INSERT INTO orders (user_id, product_id, product_name, price, order_qty,
               status, order_type, created_at)
               VALUES (?, ?, 'V99 Clear Test', 1.0, 1, 'delivered', 'account', datetime('now'))""",
            (uid, pid))
        oid = cur.lastrowid; conn.commit(); conn.close()

        ex._clear_broken_for_order_oid(oid)
        ep = ex.get_ext_product(epid)
        assert float(ep.get("stock_broken_until") or 0) == 0.0, \
            "delivery success par flag clear hona chahiye (recovery proof)"

    def test_clear_supplier_stock_broken_direct(self):
        import time as _t
        import ext_suppliers as ex
        conn = _db()
        conn.execute("DELETE FROM ext_products WHERE remote_id='v999clr2'")
        cur = conn.execute(
            """INSERT INTO ext_products (supplier_id, remote_id, name, cost_usd, stock)
               VALUES (1, 'v999clr2', 'V99 Clear2', 1.0, 0)""")
        epid = cur.lastrowid; conn.commit(); conn.close()
        ex.update_ext_product(epid, stock_broken_until=_t.time() + 900)
        ep = ex.get_ext_product(epid)
        ex._clear_supplier_stock_broken(ep)
        assert float(ex.get_ext_product(epid).get("stock_broken_until") or 0) == 0.0
        # invalid inputs crash nahi karte
        ex._clear_supplier_stock_broken(None)
        ex._clear_supplier_stock_broken({})
        ex._clear_broken_for_order_oid(999999999)
        ex._clear_broken_for_order_oid(None)


# ══════════════════════════════════════════════════════════════
# Fix B — retry deadline preserve (window-reset bug)
# ══════════════════════════════════════════════════════════════
class TestRetryDeadlinePreserve:
    def _mk_order(self, status, due, count):
        conn = _db()
        pid = conn.execute("SELECT id FROM products LIMIT 1").fetchone()["id"]
        uid = 920000000 + random.randint(1, 999999)
        conn.execute(
            """INSERT INTO orders (user_id, product_id, product_name, price, order_qty,
               status, order_type, supplier_refund_due_at, supplier_retry_count,
               supplier_failure_reason, created_at)
               VALUES (?, ?, 'RegrProd', 5.0, 1, ?, 'account', ?, ?, 'test reason', datetime('now'))""",
            (uid, pid, status, due, count))
        oid = conn.execute(
            "SELECT id FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()["id"]
        conn.commit(); conn.close()
        return oid

    def test_pending_future_due_preserved(self):
        import time as _t
        from ext_suppliers import _set_order_supplier_retry_pending
        orig_due = _t.time() + 300
        oid = self._mk_order("supplier_retry_pending", orig_due, 1)
        new_due, count = _set_order_supplier_retry_pending(oid, "second failure")
        assert count == 2, f"retry_count 2 hona chahiye, got {count}"
        assert abs(new_due - orig_due) < 2.0, \
            f"original deadline preserve hona chahiye ({orig_due}) — got {new_due} (window-reset bug!)"

    def test_expired_due_resets(self):
        import time as _t
        from ext_suppliers import _set_order_supplier_retry_pending, _SUPPLIER_RETRY_WINDOW_SECONDS
        oid = self._mk_order("supplier_retry_pending", _t.time() - 10, 2)
        before = _t.time()
        new_due, count = _set_order_supplier_retry_pending(oid, "failure after expiry")
        assert count == 3
        assert new_due >= before and new_due <= _t.time() + _SUPPLIER_RETRY_WINDOW_SECONDS + 2

    def test_fresh_pending_gets_window(self):
        import time as _t
        from ext_suppliers import _set_order_supplier_retry_pending, _SUPPLIER_RETRY_WINDOW_SECONDS
        oid = self._mk_order("pending", 0, 0)
        before = _t.time()
        new_due, count = _set_order_supplier_retry_pending(oid, "first failure")
        assert count == 1
        assert new_due >= before + _SUPPLIER_RETRY_WINDOW_SECONDS - 2
        assert new_due <= _t.time() + _SUPPLIER_RETRY_WINDOW_SECONDS + 2


# ══════════════════════════════════════════════════════════════
# Fix B — auto-retry eligibility matrix
# ══════════════════════════════════════════════════════════════
class TestAutoRetryReady:
    def test_matrix(self):
        import time as _t
        from ext_suppliers import _supplier_auto_retry_ready
        t = 1000000.0
        W = 300
        # window [t, t+300], first_pending = t
        assert _supplier_auto_retry_ready({"supplier_refund_due_at": t + W, "supplier_retry_count": 1}, t + 60) is True
        assert _supplier_auto_retry_ready({"supplier_refund_due_at": t + W, "supplier_retry_count": 1}, t + 59) is False
        assert _supplier_auto_retry_ready({"supplier_refund_due_at": t + W, "supplier_retry_count": 2}, t + 120) is True
        assert _supplier_auto_retry_ready({"supplier_refund_due_at": t + W, "supplier_retry_count": 2}, t + 119) is False
        # 3+ attempts → koi auto-retry nahi
        assert _supplier_auto_retry_ready({"supplier_refund_due_at": t + W, "supplier_retry_count": 3}, t + 180) is False
        # count 0 → nahi (scheduled nahi hua)
        assert _supplier_auto_retry_ready({"supplier_refund_due_at": t + W, "supplier_retry_count": 0}, t + 60) is False
        # expired / no due → nahi
        assert _supplier_auto_retry_ready({"supplier_refund_due_at": t - 1, "supplier_retry_count": 1}, t) is False
        assert _supplier_auto_retry_ready({"supplier_refund_due_at": 0, "supplier_retry_count": 1}, t) is False
        assert _supplier_auto_retry_ready({}, t) is False
        assert _supplier_auto_retry_ready(None, t) is False


# ══════════════════════════════════════════════════════════════
# Sanity — purane v170.91 markers ab bhi kaam karte hain
# ══════════════════════════════════════════════════════════════
class TestSliceMarkerStillWorks:
    def test_stock_pool_broken_detection(self):
        from ext_suppliers import _supplier_error_is_stock_pool_broken
        msg = ("Plan executor error during findAndModify :: caused by :: "
               "Third argument to $slice must be positive: 0")
        assert _supplier_error_is_stock_pool_broken({"raw": msg}) is True
        assert _supplier_error_is_stock_pool_broken({"error": "out of stock"}) is True
        assert _supplier_error_is_stock_pool_broken({"status_code": 409}) is True
        assert _supplier_error_is_stock_pool_broken({"error": "invalid api key"}) is False
