# -*- coding: utf-8 -*-
"""
v170.91 REGRESSION SUITE — Task 2 (Bugs 1-4 + Update 1)
Repo ke andar persist karta hai (/tmp nahi). Run:
    python3 -m pytest test_v170_91_regression.py -v
"""
import os, sys, re, shutil, tempfile, asyncio, sqlite3, threading, http.server, socketserver, random

# ── env PEHLE — database import se pehle ──
_TMPDIR = tempfile.mkdtemp(prefix="v17091_regr_")
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
    # timeout=10 → concurrent database-module connections ke saath lock-wait
    conn = sqlite3.connect(_REGDB, timeout=10); conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _alter(table, col, decl):
    """Boot self-heal simulate karo (column add)."""
    conn = _db()
    if col not in [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    conn.commit(); conn.close()


# boot self-heal simulate (ready DB me ye columns bot-boot par aate hain)
_alter("products", "deliver_as_file", "INTEGER DEFAULT 0")


# ══════════════════════════════════════════════════════════════
# Bug 3 — Markdown escape
# ══════════════════════════════════════════════════════════════
class TestBug3Escape:
    def test_escape_md_special_chars(self):
        from utils import escape_md
        assert escape_md("@key40_osm") == "@key40\\_osm"
        assert escape_md("a*b") == "a\\*b"
        assert escape_md("c_d") == "c\\_d"
        assert escape_md("e`f") == "e\\`f"
        assert escape_md("[x](y)") == "\\[x\\](y)"   # parens MD-v1 me safe hain

    def test_escape_md_empty(self):
        from utils import escape_md
        assert escape_md("") == ""
        assert escape_md(None) == ""


# ══════════════════════════════════════════════════════════════
# Bug 1c — supplier error detection (auto-pause triggers)
# ══════════════════════════════════════════════════════════════
class TestBug1cErrorDetection:
    def test_not_found_variants(self):
        from ext_suppliers import _supplier_error_is_not_found as nf
        assert nf({"status_code": 404}) is True
        assert nf(reason="HTTP 404") is True
        assert nf(reason="Product not found") is True
        assert nf({"error": "not_found"}) is True
        assert nf(reason="product does not exist") is True
        assert nf(reason="unavailable") is True

    def test_not_found_negative(self):
        from ext_suppliers import _supplier_error_is_not_found as nf
        assert nf({"status_code": 500}) is False
        assert nf(reason="connection timeout") is False
        assert nf(reason="internal server error") is False

    def test_stock_pool_broken_variants(self):
        from ext_suppliers import _supplier_error_is_stock_pool_broken as spb
        assert spb(reason="Plan executor error during findAndModify :: caused by :: "
                          "Third argument to $slice must be positive: 0") is True
        assert spb({"error": "out of stock"}) is True
        assert spb({"status_code": 409, "error": "Conflict"}) is True
        assert spb(reason="sold out") is True
        assert spb(reason="stock is empty") is True

    def test_stock_pool_broken_negative(self):
        from ext_suppliers import _supplier_error_is_stock_pool_broken as spb
        # network/transient errors ko pause NAHI karna
        assert spb(reason="connection reset by peer") is False
        assert spb({"status_code": 500}) is False
        assert spb({"status_code": 502, "error": "bad gateway"}) is False


# ══════════════════════════════════════════════════════════════
# Bug 1b — file-format delivery
# ══════════════════════════════════════════════════════════════
class TestBug1bFileDelivery:
    @staticmethod
    def _file_auto(s):
        # router ka auto-detect predicate (v170.91)
        if "\n" in s:
            return True
        toks = [t for t in s.replace("\t", " ").split(" ") if t]
        return ("@" in s and len(toks) >= 3) or len(s) > 100

    def test_auto_detect_predicates(self):
        f = self._file_auto
        assert f("user@gmail.com pass123 notionpass456") is True   # Notion 3-field
        assert f("user@gmail.com|pass123") is False                # email|pass
        assert f("email: a\npass: b") is True                      # multiline
        assert f("x" * 101) is True                                # long link
        assert f("x" * 99) is False
        assert f("a@b.com\tpass\textra") is True                   # tab 3-field

    def test_deliver_as_file_flag_roundtrip(self):
        import database
        conn = _db()
        pid = conn.execute("SELECT id FROM products WHERE is_active=1 LIMIT 1").fetchone()["id"]
        conn.close()
        for val in (1, 2, 0):
            conn = _db()
            conn.execute("UPDATE products SET deliver_as_file=? WHERE id=?", (val, pid))
            conn.commit(); conn.close()
            p = dict(database.get_product(pid))
            assert int(p.get("deliver_as_file") or 0) == val, f"flag {val} roundtrip fail"

    def test_maybe_download_txt_url(self):
        from ext_suppliers import _maybe_download_delivery_file as dl
        payload = "line1: a@b.com pass\nline2: c@d.com pass2\n"
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = payload.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *a): pass
        srv = socketserver.TCPServer(("127.0.0.1", 0), H)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            lines, content = dl([f"http://127.0.0.1:{port}/keys.txt"])
            assert lines and len(lines) == 2, lines
            assert lines[0].startswith("line1") and lines[1].startswith("line2")
            assert content == payload
        finally:
            srv.shutdown(); srv.server_close()
        # non-txt URL → untouched (items, None)
        out = dl(["http://127.0.0.1:1/x.pdf"])
        assert out[1] is None and out[0] == ["http://127.0.0.1:1/x.pdf"]
        # plain key → untouched
        out = dl(["email|pass"])
        assert out[0] == ["email|pass"] and out[1] is None
        # dead URL → untouched (download fail safe)
        out = dl(["http://127.0.0.1:2/dead.txt"])
        assert out[1] is None


# ══════════════════════════════════════════════════════════════
# Bug 4 — exact calculations
# ══════════════════════════════════════════════════════════════
class TestBug4ExactCalc:
    @staticmethod
    def _mkorder(price, qty, status="delivered", order_type="product"):
        conn = _db()
        pid = conn.execute("SELECT id FROM products LIMIT 1").fetchone()["id"]
        uid = 800000000 + random.randint(1, 9999999)
        cur = conn.execute(
            """INSERT INTO orders (user_id, product_id, product_name, price, order_qty,
               status, order_type, created_at)
               VALUES (?, ?, 'RegrProd', ?, ?, ?, ?, datetime('now'))""",
            (uid, pid, price, qty, status, order_type))
        oid = cur.lastrowid
        conn.commit(); conn.close()
        return oid

    def test_order_profit_real_cost(self):
        import database
        from completed_orders_v2 import _order_profit
        conn = _db()
        pid = conn.execute("SELECT id FROM products LIMIT 1").fetchone()["id"]
        conn.execute("UPDATE products SET cost_price=0.5 WHERE id=?", (pid,))
        conn.commit(); conn.close()
        oid = self._mkorder(price=10.0, qty=3)
        try:
            # 1) real supplier charge path: ext_orders.cost_usd = 1.5 → profit 8.5
            conn = _db()
            conn.execute("DELETE FROM ext_orders WHERE internal_order_id=?", (oid,))
            conn.execute(
                """INSERT INTO ext_orders (internal_order_id, supplier_id, ext_product_id,
                   quantity, cost_usd, status) VALUES (?, 1, 'regr_ext', 3, 1.5, 'delivered')""",
                (oid,))
            conn.commit(); conn.close()
            o = database.get_order(oid)
            profit = _order_profit(o)
            assert abs(profit - 8.5) < 0.01, f"real-cost profit: {profit} != 8.5"
            # 2) charge 0 → estimate path: ext_products.cost_usd × qty (agar
            #    mapping hai) warna products.cost_price × qty — DONO me qty aata hai
            conn = _db()
            conn.execute("UPDATE ext_orders SET cost_usd=0 WHERE internal_order_id=?", (oid,))
            conn.commit(); conn.close()
            conn = _db()
            est = conn.execute(
                """SELECT ep.cost_usd AS ecd, p.cost_price AS pcp
                   FROM products p LEFT JOIN ext_products ep ON ep.id = p.ext_product_id
                   WHERE p.id=?""", (pid,)).fetchone()
            ecd = float(est["ecd"] or 0); pcp = float(est["pcp"] or 0)
            conn.close()
            unit = ecd if ecd > 0 else (pcp if pcp > 0 else 0)
            expected = round(10.0 - unit * 3, 4)
            profit2 = _order_profit(database.get_order(oid))
            assert abs(profit2 - expected) < 0.01, \
                f"estimate profit: {profit2} != {expected} (unit={unit}, qty=3 — qty IGNORE ho raha tha Bug4)"
        finally:
            conn = _db()
            conn.execute("DELETE FROM ext_orders WHERE internal_order_id=?", (oid,))
            conn.execute("DELETE FROM orders WHERE id=?", (oid,))
            conn.commit()
            conn.close()

    def test_completed_summary_points_not_in_product_spend(self):
        from completed_orders_v2 import _completed_summary
        base = _completed_summary()
        # points top-up delivered order — product spend/profit NAHI badhna chahiye
        oid = self._mkorder(price=948.0, qty=1, order_type="points")
        try:
            after = _completed_summary()
            assert abs(after["spend"] - base["spend"]) < 0.01, \
                f"points spend me ghus gaya: {base['spend']} -> {after['spend']}"
            assert abs(after["profit"] - base["profit"]) < 0.01, \
                f"points profit me ghus gaya: {base['profit']} -> {after['profit']}"
            assert after["points_orders"] == base["points_orders"] + 1
            assert abs(after["points_amount"] - base["points_amount"] - 948.0) < 0.01
        finally:
            conn = _db()
            conn.execute("DELETE FROM orders WHERE id=?", (oid,))
            conn.commit(); conn.close()


# ══════════════════════════════════════════════════════════════
# Bug 2 — reseller orders panel
# ══════════════════════════════════════════════════════════════
class TestBug2ResellerOrders:
    @staticmethod
    def _seed_reseller_order(**over):
        conn = _db()
        row = dict(
            key_id=41, user_id=123456, product_id=999001, product_name="Test `Prod` _X_",
            qty=2, usd_amount=1.2, points_amount=12.0, status="delivered",
            delivery_text="", delivered_keys="", remote_order_id="", idem_key="",
            error="", delivery_file_id="", delivery_file_name="", delivery_file_type="",
            webhook_sent=0, created_at="2026-09-09 10:00:00", delivered_at="2026-09-09 10:01:00")
        row.update(over)
        cols = ",".join(row.keys()); qs = ",".join("?" * len(row))
        cur = conn.execute(f"INSERT INTO reseller_orders ({cols}) VALUES ({qs})", list(row.values()))
        rid = cur.lastrowid
        conn.commit(); conn.close()
        return rid

    @staticmethod
    def _make_q(captured):
        class Q:
            data = "reseller_orders"
            class from_user: id = 7105782769
            @staticmethod
            async def answer(*a, **k): pass
            @staticmethod
            async def edit_message_text(text, **kw):
                captured.append({"text": text, "kb": kw.get("reply_markup")})
        return Q()

    @classmethod
    def _render(cls, search=""):
        import handlers_admin as ha
        captured = []
        q = cls._make_q(captured)
        class Ctx:
            user_data = {"rs_orders": {"status": "all", "range": "all"},
                         "rs_orders_search": search}
        asyncio.run(ha._render_reseller_orders_panel(object(), Ctx(), q))
        return captured

    def test_panel_render_filters_and_names(self):
        self._seed_reseller_order()
        self._seed_reseller_order(status="failed", product_name="Second `Prod` *Y*", user_id=777)
        captured = self._render()
        assert captured, "panel render ne kuch edit nahi kiya"
        kb = captured[0]["kb"]
        btns = [b.text for row in kb.inline_keyboard for b in row]
        # 7 filter buttons (4 status + 3 range) — Bug2c
        for label in ("📋 All", "✅ Del", "⏳ Pend", "❌ Fail",
                      "🕐 24h", "📅 7d", "🗓️ All"):
            assert any(label in b for b in btns), f"filter button missing: {label}"
        n_filters = sum(1 for b in btns if b.startswith(("📋", "✅", "⏳", "❌", "🕐", "📅", "🗓️")))
        assert n_filters == 7, f"filter count: {n_filters} != 7"
        # 📄 button par product NAME (Bug2b)
        det = [b for b in btns if b.startswith("📄")]
        assert det, "📄 details buttons missing"
        assert any(("Test" in b) or ("Second" in b) for b in det), f"name missing: {det[:3]}"
        # search button
        assert any("🔍" in b for b in btns)

    def test_panel_search_filter(self):
        rid = self._seed_reseller_order(user_id=987654321, product_name="Zebra `Search` Item")
        try:
            out = self._render(search="zebra")
            assert "Zebra" in out[0]["text"], "search match nahi dikha"
            out2 = self._render(search="no_such_thing_xyz")
            assert "Zebra" not in out2[0]["text"]
            # user id se bhi
            out3 = self._render(search="987654321")
            assert "Zebra" in out3[0]["text"], "user-id search fail"
        finally:
            conn = _db()
            conn.execute("DELETE FROM reseller_orders WHERE id=?", (rid,))
            conn.commit(); conn.close()


# ══════════════════════════════════════════════════════════════
# Update 1 — custom fake reviews
# ══════════════════════════════════════════════════════════════
class TestUpdate1CustomReviews:
    def test_add_queue_broadcast_clear(self):
        import custom_reviews as cr
        import fake_engagement as fe
        cr._ensure_queue_table()
        conn = _db()
        pid = conn.execute("SELECT id FROM products WHERE is_active=1 LIMIT 1").fetchone()["id"]
        conn.execute("DELETE FROM custom_review_queue WHERE product_id=?", (pid,))
        conn.commit(); conn.close()

        ins, skip = cr.add_custom_reviews(pid, ["Osm 😍", "Excellent 🔥", "Nice 🪪"],
                                          product_name="RegrProd")
        assert (ins, skip) == (3, 0)
        conn = _db()
        rats = [r[0] for r in conn.execute(
            "SELECT rating FROM custom_review_queue WHERE product_id=?", (pid,))]
        uids = [r[0] for r in conn.execute(
            "SELECT fake_uid FROM custom_review_queue WHERE product_id=?", (pid,))]
        conn.close()
        assert all(3 <= r <= 5 for r in rats), f"ratings: {rats}"
        assert all(u >= 9_000_000_000 for u in uids), f"uid <9B: {uids}"

        # broadcast: har review EXACTLY once
        sent = []
        async def fake_bcast(bot, text, **kw):
            sent.append(text); return 1
        orig = fe.broadcast_store_message
        fe.broadcast_store_message = fake_bcast
        class FJQ:
            def __init__(self): self.jobs = []
            def run_once(self, cb, when=None, **kw): self.jobs.append(cb)
        class FA: job_queue = FJQ()
        class FJob:
            application = FA(); bot = object()
        async def run():
            for _ in range(4):   # 3 rows + 1 empty run
                await cr.custom_review_broadcast_job(FJob())
        asyncio.run(run())
        fe.broadcast_store_message = orig
        assert len(sent) == 3, f"sent {len(sent)} != 3"
        assert cr.pending_queue_count() == 0

        # clear: pending delete
        conn = _db()
        conn.execute("UPDATE custom_review_queue SET status='pending', sent_at=NULL "
                     "WHERE product_id=?", (pid,))
        conn.commit(); conn.close()
        captured = []
        class Q2:
            data = "cfr_clear"
            class from_user: id = 7105782769
            @staticmethod
            async def answer(*a, **k): pass
            @staticmethod
            async def edit_message_text(text, **kw): captured.append(text)
        class Upd:
            callback_query = Q2()
            class effective_user: id = 7105782769
        asyncio.run(cr.cfr_clear_callback(Upd(), type("C", (), {"user_data": {}})()))
        assert cr.pending_queue_count() == 0
        # cleanup
        conn = _db()
        conn.execute("DELETE FROM custom_review_queue WHERE product_id=?", (pid,))
        conn.execute("DELETE FROM product_reviews WHERE product_id=? AND user_id>=9000000000 "
                     "AND review_text IN ('Osm 😍','Excellent 🔥','Nice 🪪')", (pid,))
        conn.execute("DELETE FROM users WHERE username LIKE 'fake_reviewer_%'")
        conn.commit(); conn.close()

    def test_stale_sending_requeue(self):
        import custom_reviews as cr
        cr._ensure_queue_table()
        conn = _db()
        pid = conn.execute("SELECT id FROM products WHERE is_active=1 LIMIT 1").fetchone()["id"]
        conn.close()
        cr.add_custom_reviews(pid, ["STALE-1"], product_name="RegrProd")
        conn = _db()
        conn.execute("UPDATE custom_review_queue SET status='sending', "
                     "sent_at=datetime('now','-15 minutes') WHERE review_text='STALE-1'")
        conn.commit(); conn.close()
        n = cr._requeue_stale_sending()
        assert n >= 1, "stale sending row requeue nahi hui"
        conn = _db()
        st = conn.execute("SELECT status FROM custom_review_queue WHERE review_text='STALE-1'").fetchone()
        conn.execute("DELETE FROM custom_review_queue WHERE review_text='STALE-1'")
        conn.execute("DELETE FROM product_reviews WHERE product_id=? AND user_id>=9000000000 "
                     "AND review_text='STALE-1'", (pid,))
        conn.execute("DELETE FROM users WHERE username LIKE 'fake_reviewer_%'")
        conn.commit(); conn.close()
        assert st and st[0] == "pending"


# ══════════════════════════════════════════════════════════════
# 🆕 v170.92 — Task 3: supplier delete/deactivate auto-remove
# ══════════════════════════════════════════════════════════════
class TestTask3SupplierRemoval:
    def test_source_active_instock_false(self):
        from ext_suppliers import source_product_is_active as sa
        # inStock=False → deactivated
        assert sa({"name": "x", "raw": {"inStock": False}}) is False
        assert sa({"inStock": False}) is False
        assert sa({"in_stock": False}) is False
        # inStock=True / absent / numeric stock 0 → available
        assert sa({"inStock": True}) is True
        assert sa({"stock": 0}) is True
        assert sa({}) is True
        # legacy flags
        assert sa({"is_active": False}) is False
        assert sa({"available": False}) is False

    def test_missing_onetshot_and_notification(self):
        import supplier_automation as sauto
        import ext_suppliers as ex
        import fake_engagement  # noqa
        conn = _db()
        # test supplier + product setup
        conn.execute("DELETE FROM ext_products WHERE remote_id='v921test'")
        conn.execute("DELETE FROM ext_suppliers WHERE name='V92 Test Supplier'")
        cur = conn.execute(
            "INSERT INTO ext_suppliers (name, base_url, api_key, adapter, enabled) "
            "VALUES ('V92 Test Supplier', 'https://v92.test', 'k', 'prodseller', 1)")
        sid = cur.lastrowid
        ecur = conn.execute(
            """INSERT INTO ext_products (supplier_id, remote_id, name, cost_usd, stock,
               sell_price, markup_pct, synced_to_shop, owner_active, source_active)
               VALUES (?, 'v921test', 'V92 Notion Test', 1.0, 50, 1.4, 40, 1, 1, 1)""", (sid,))
        epid = ecur.lastrowid
        conn.commit(); conn.close()
        # mirror to products
        pid, _ = ex.mirror_ext_to_products(epid)
        conn = _db()
        assert conn.execute("SELECT is_active FROM products WHERE id=?", (pid,)).fetchone()[0] == 1
        conn.close()

        # fake adapter: pehli baar → product LIST MEIN NAHI (deleted)
        class FakeAd:
            async def fetch_products(self):
                return []
        sent = []
        class FakeBot:
            async def send_message(self, chat_id, text, **kw):
                sent.append(text); return True
        class FakeCtx:
            bot = FakeBot()

        orig = {
            "ls": ex.list_suppliers, "ga": ex.get_adapter_for_supplier,
            "gep": ex.get_ext_products, "afc": None}
        ex.list_suppliers = lambda include_disabled=False: [{"id": sid, "name": "V92 Test Supplier", "enabled": 1, "base_url": "https://v92.test", "api_key": "k"}]
        ex.get_adapter_for_supplier = lambda sup: FakeAd()
        import async_adapter_helpers as aah
        async def fake_fetch(ad): return []
        orig_afc = aah.async_fetch_products
        aah.async_fetch_products = fake_fetch
        orig_enabled = sauto.is_autosync_enabled
        sauto.is_autosync_enabled = lambda: True

        try:
            # run 1: empty fetch → counter (glitch protection)
            asyncio.run(sauto.autosync_price_stock_job(FakeCtx()))
            # run 2: empty fetch confirmed → missing detection triggers
            asyncio.run(sauto.autosync_price_stock_job(FakeCtx()))
            # product ab shop me INACTIVE (auto-removed)
            conn = _db()
            st = conn.execute("SELECT is_active FROM products WHERE id=?", (pid,)).fetchone()[0]
            src = conn.execute("SELECT source_active FROM ext_products WHERE id=?", (epid,)).fetchone()[0]
            conn.close()
            assert st == 0, "product shop me active raha — auto-remove fail"
            assert src == 0
            # ENGLISH notification aayi — supplier + product + auto-removed
            assert any("Auto-Removed from Your Store" in t and "V92 Test Supplier" in t
                       and "V92 Notion Test" in t for t in sent), sent[:1]
            assert any("automatically removed from your bot" in t for t in sent)

            # ── ONE-SHOT: dobara run → notification DOBARA NAHI ──
            sent.clear()
            asyncio.run(sauto.autosync_price_stock_job(FakeCtx()))
            assert not any("Auto-Removed" in t for t in sent), "missing notification repeated (spam!)"

            # ── RESTORE (inStock=True) → product wapas active ──
            async def fake_fetch3(ad):
                return [{"remote_id": "v921test", "name": "V92 Notion Test",
                         "cost_usd": 1.0, "stock": 50, "raw": {"inStock": True}}]
            aah.async_fetch_products = fake_fetch3
            asyncio.run(sauto.autosync_price_stock_job(FakeCtx()))
            conn = _db()
            st = conn.execute("SELECT is_active FROM products WHERE id=?", (pid,)).fetchone()[0]
            conn.close()
            assert st == 1, "restore par product wapas active hona chahiye"

            # ── DEACTIVATED (listed hai magar inStock=False) ──
            async def fake_fetch2(ad):
                return [{"remote_id": "v921test", "name": "V92 Notion Test",
                         "cost_usd": 1.0, "stock": 50, "raw": {"inStock": False}}]
            aah.async_fetch_products = fake_fetch2
            sent.clear()
            asyncio.run(sauto.autosync_price_stock_job(FakeCtx()))
            conn = _db()
            src = conn.execute("SELECT source_active FROM ext_products WHERE id=?", (epid,)).fetchone()[0]
            st2 = conn.execute("SELECT is_active FROM products WHERE id=?", (pid,)).fetchone()[0]
            conn.close()
            assert src == 0, "inStock=False par source_active 0 hona chahiye (deactivated)"
            assert st2 == 0, "deactivated product shop se remove hona chahiye"
            assert any("Deactivated by the supplier" in t for t in sent), sent[:1]
            assert any("automatically removed from your bot" in t for t in sent)
        finally:
            ex.list_suppliers = orig["ls"]
            ex.get_adapter_for_supplier = orig["ga"]
            aah.async_fetch_products = orig_afc
            sauto.is_autosync_enabled = orig_enabled
            conn = _db()
            conn.execute("DELETE FROM products WHERE id=?", (pid,))
            conn.execute("DELETE FROM ext_products WHERE id=?", (epid,))
            conn.execute("DELETE FROM ext_suppliers WHERE id=?", (sid,))
            conn.commit(); conn.close()


# ══════════════════════════════════════════════════════════════
# 🆕 v170.92 — Task 4: no Roman Urdu anywhere (user-visible)
# ══════════════════════════════════════════════════════════════
URDU_TOKENS = re.compile(
    r'\b(kro|kardo|krdo|krdiya|kardiya|krna|karni|krny|karny|krke|karke|karo|karna|'
    r'karein|chahiye|chaiye|nahi|nhi|hoga|hogya|hojaye|gya|gaya|apna|apni|apne|apny|'
    r'aapka|aapki|aapke|kaise|kaisy|kasay|liye|lye|bataye|batayen|batao|btao|btaye|'
    r'milenge|milega|diya|lena|dena|sakta|skta|sakte|skte|jata|jati|aata|aati|kuch|'
    r'zaroori|zaruri|meherbani|shukriya|bohat|bohot|zyada|thoda|thori|acha|accha|'
    r'theek|thik|masla|mushkil|khatam|khtm|abhi|jaldi|foran|turant|waqt|dost|bhai|'
    r'hona|honi|hone|hony|hui|hua|honge|warna|magar|dobara|humesha|hamesha|kabhi|'
    r'kyun|kese|jaisa|jesa|aise|aysay|waise|kholo|chalu|shuru|ruko|dekho|dkho|dikhao|'
    r'likho|padho|bhejo|lelo|karlo|rakho|pata|pta|lazmi|sahi|galat|khud|hojata|hojta|'
    r'hota|hote|hoti|hoty|karta|karti|krta|krti|khareedo|khareedein|chunein|likhein|'
    r'likho|mere|mera|meri|paisa|paise|mein|khush|amdeed|swagat|naam|mubarak|pehlay|'
    r'pehle|dosto|chuke|banaye|tap karein|choose karo|check karein|check karo)\b', re.I)


class TestTask4NoRomanUrdu:
    def test_template_b_all_english(self):
        from response_templates import RESPONSE_TEMPLATE_B, extract_placeholders
        from config import DEFAULT_RESPONSES
        assert len(RESPONSE_TEMPLATE_B) >= 70
        for k, v in RESPONSE_TEMPLATE_B.items():
            assert not URDU_TOKENS.search(v), f"Template B '{k}' me Roman Urdu: {v[:60]!r}"
            # placeholder safety bhi
            d = DEFAULT_RESPONSES.get(k)
            if d is not None:
                extra = set(extract_placeholders(v)) - set(extract_placeholders(d))
                assert not extra, f"Template B '{k}' extra placeholders: {extra}"

    def test_review_text_always_english(self):
        from fake_engagement import generate_review_text, generate_fake_reviewer
        for _ in range(12):
            name, lang = generate_fake_reviewer(pk_ratio=100)  # force "urdu" language
            txt = generate_review_text(lang)
            assert not URDU_TOKENS.search(txt), f"Roman Urdu review ({lang}): {txt!r}"

    def test_i18n_ru_hi_no_roman_urdu(self):
        import i18n
        STR = r'"((?:[^"\\]|\\.)*)"'
        src = open("i18n.py", encoding="utf-8").read()
        bad = [m.group(0)[:80] for m in re.finditer(r'"(ru|hi)":\s*' + STR, src)
               if URDU_TOKENS.search(m.group(2))]
        assert not bad, f"i18n ru/hi Roman Urdu: {bad}"

    def test_i18n_responses_ru_hi_no_roman_urdu(self):
        import i18n_responses as ir
        bad = []
        for key, langs in ir.RESPONSE_TRANSLATIONS.items():
            for lang in ("ru", "hi"):
                v = langs.get(lang)
                if v and URDU_TOKENS.search(v):
                    bad.append((key, lang, v[:40]))
        assert not bad, f"i18n_responses ru/hi Roman Urdu: {bad}"

    def test_customization_defaults_no_roman_urdu(self):
        import customization as cz
        pools = cz.get_review_sentences("english") + cz.get_review_sentences("urdu")
        for p in pools:
            assert not URDU_TOKENS.search(p), f"Roman Urdu review sentence: {p!r}"

    def test_selfheal_roman_urdu_db(self):
        # ready DB copy par: Roman Urdu values → English (heal)
        import shutil as _sh, tempfile as _tf
        tmpd = _tf.mkdtemp()
        tmpdb = os.path.join(tmpd, "heal.db")
        _sh.copy("/home/user/bite_store_restore_ready.db", tmpdb)
        # Roman Urdu value inject karo (jaise purane production DB me tha)
        conn = sqlite3.connect(tmpdb)
        conn.execute("UPDATE bot_responses SET value=? WHERE key='payment_not_found_txid'",
                     ("⏳ test — agar aap ne pay kiya hai to Check Again dabayen turant verify ho jayegi",))
        conn.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('tpl_bc_freebie', "
                     "'🎁 FREEBIE! 100% free — koi payment nahi, koi referral nahi!')")
        conn.commit(); conn.close()
        # heal chalao
        os.environ["DB_PATH"] = tmpdb
        import importlib
        import database as dbm
        importlib.reload(dbm)
        import self_heal
        importlib.reload(self_heal)
        self_heal._heal_roman_urdu_responses()
        conn = sqlite3.connect(tmpdb)
        v1 = conn.execute("SELECT value FROM bot_responses WHERE key='payment_not_found_txid'").fetchone()[0]
        v2 = conn.execute("SELECT value FROM bot_settings WHERE key='tpl_bc_freebie'").fetchone()[0]
        conn.close()
        assert not URDU_TOKENS.search(v1), f"heal fail (bot_responses): {v1[:80]!r}"
        assert "koi payment nahi" not in v2.lower(), f"heal fail (tpl_bc_freebie): {v2[:80]!r}"
        # env wapas
        os.environ["DB_PATH"] = _REGDB
        importlib.reload(dbm)


# ═══════════════════════════════════════════════════════════════
# 🆕 v170.93 — BOT SPEED / FAKE-ACTIVITY STORM FIX
# Root cause (2026-09-09): pua_interval_unit=seconds (min=1 max=60)
# + 2,765 active per-user jobs = ~61 sends/sec aggregate demand →
# scheduler/event-loop/Telegram saturation → every button tap slow.
# Railway logs measured 366 job runs/min + 67 misfire warnings.
# ═══════════════════════════════════════════════════════════════
class TestSpeedStormFix:
    def test_global_throttle_caps_send_rate(self):
        """fake_send_allowed_now: do baar turant call → sirf pehli True."""
        import per_user_activity as pua
        pua._last_fake_send_ts = 0.0
        assert pua.fake_send_allowed_now() is True      # slot mila
        assert pua.fake_send_allowed_now() is False     # gap ke andar → block
        pua._last_fake_send_ts = 0.0                    # reset → phir slot
        assert pua.fake_send_allowed_now() is True

    def test_global_throttle_gap_configurable(self):
        import per_user_activity as pua
        from database import set_setting, get_setting
        old = get_setting("pua_global_min_gap", "")
        try:
            set_setting("pua_global_min_gap", "2")
            assert pua.fake_send_gap_seconds() == 2
            set_setting("pua_global_min_gap", "0")   # invalid → floor 1s
            assert pua.fake_send_gap_seconds() == 1
        finally:
            if old:
                from database import set_setting as _ss
                _ss("pua_global_min_gap", old)

    def test_seconds_misconfig_read_as_minutes(self):
        """unit=seconds + max<120 (e.g. 1-60 SECONDS) → minutes-scale."""
        import per_user_activity as pua
        from database import set_setting
        for k, v in (("pua_interval_unit", "seconds"),
                     ("pua_min_interval", "1"),
                     ("pua_max_interval", "60")):
            set_setting(k, v)
        mn_s, mx_s = pua.get_speed_seconds()
        assert mn_s >= 60 and mx_s >= 3600, f"misconfig guard fail: {mn_s},{mx_s}"
        # legit seconds config (>=120s) untouched
        set_setting("pua_min_interval", "150")
        set_setting("pua_max_interval", "300")
        mn_s2, mx_s2 = pua.get_speed_seconds()
        assert mn_s2 == 150 and mx_s2 == 300, f"legit seconds broken: {mn_s2},{mx_s2}"
        # cleanup
        set_setting("pua_interval_unit", "minutes")
        set_setting("pua_min_interval", "1")
        set_setting("pua_max_interval", "60")

    def test_heal_fixes_seconds_flood_config(self):
        """self-heal: unit=seconds → minutes 1-60 (incl. 30/60 edge)."""
        import self_heal
        from database import set_setting, get_setting
        for k, v in (("pua_interval_unit", "seconds"),
                     ("pua_min_interval", "30"),
                     ("pua_max_interval", "60")):
            set_setting(k, v)
        self_heal._heal_activity_flood_settings()
        assert get_setting("pua_interval_unit", "") == "minutes"
        assert get_setting("pua_min_interval", "") == "1"
        assert get_setting("pua_max_interval", "") == "60"

    def test_autosync_interval_default_180(self):
        """AutoSync 30s → 180s default (owner setting, floor 60s)."""
        import supplier_automation as sa
        from database import set_setting, get_setting
        assert sa.get_autosync_price_stock_interval() == 180   # default
        set_setting("autosync_interval_seconds", "60")
        assert sa.get_autosync_price_stock_interval() == 60    # override
        set_setting("autosync_interval_seconds", "10")
        assert sa.get_autosync_price_stock_interval() == 60    # floor 60
        from database import set_setting as _ss
        _ss("autosync_interval_seconds", "180")

    @pytest.mark.asyncio
    async def test_forbidden_auto_deactivates_user(self):
        """Blocked user → job auto-deactivate (no more doomed API calls)."""
        import per_user_activity as pua
        from database import set_setting

        class _ForbiddenBot:
            async def send_message(self, **kw):
                raise Exception("Forbidden: bot was blocked by the user")

        set_setting("pua_global_enabled", "1")
        set_setting("dest_mode", "bot_only")
        pua._last_fake_send_ts = 0.0
        pua.register_user_job(424242)
        pua.set_user_active(424242, True)
        assert pua.is_user_active(424242) is True

        _orig = pua.build_fake_message
        async def _fake_build(bot, uid):
            return "📦 Test message", None
        pua.build_fake_message = _fake_build
        try:
            await pua._send_activity_to_user(_ForbiddenBot(), 424242)
        finally:
            pua.build_fake_message = _orig
        assert pua.is_user_active(424242) is False, "Forbidden par deactivate nahi hua!"
        pua.set_user_active(424242, True)  # cleanup

    @pytest.mark.asyncio
    async def test_throttle_skips_send_entirely(self):
        """Global cap hit → _send_activity_to_user kuch bhi send nahi karta."""
        import per_user_activity as pua
        from database import set_setting

        class _CountingBot:
            sent = 0
            async def send_message(self, **kw):
                _CountingBot.sent += 1
                return True

        set_setting("pua_global_enabled", "1")
        set_setting("dest_mode", "bot_only")
        pua._last_fake_send_ts = 0.0
        pua.register_user_job(424243)
        pua.set_user_active(424243, True)

        _orig = pua.build_fake_message
        async def _fake_build(bot, uid):
            return "📦 Test message", None
        pua.build_fake_message = _fake_build
        try:
            await pua._send_activity_to_user(_CountingBot(), 424243)  # slot liya
            await pua._send_activity_to_user(_CountingBot(), 424243)  # throttled
            await pua._send_activity_to_user(_CountingBot(), 424243)  # throttled
        finally:
            pua.build_fake_message = _orig
        assert _CountingBot.sent == 1, f"throttle fail: {_CountingBot.sent} sends"
        pua.set_user_active(424243, True)  # cleanup


# ═══════════════════════════════════════════════════════════════
# 🆕 v170.94 — CUSTOM REVIEWS STORM FIX
# Bug: custom_review_broadcast_job empty-queue path _reschedule karta
# tha (early-return) AUR finally BHI → har idle run par chain DOUBLE →
# exponential job storm (Railway: 1,800 log lines/min, 500 logs/sec
# rate-limit, 454 jobs/13s, bot unresponsive 2026-09-11).
# ═══════════════════════════════════════════════════════════════
class TestCustomReviewStormFix:
    def test_reschedule_guards(self):
        """dedup + pending-only + exactly-one-named-add."""
        import custom_reviews as cr
        orig = cr.pending_queue_count

        class FJQ:
            def __init__(self, existing=None):
                self.existing = existing or []; self.added = []
            def get_jobs_by_name(self, name): return self.existing
            def run_once(self, cb, when=None, **kw): self.added.append(kw.get("name"))
        class FA:
            def __init__(self, jq): self.job_queue = jq
        try:
            # 1) job already scheduled → SKIP (multi-chain impossible)
            cr.pending_queue_count = lambda: 5
            jq = FJQ([object()])
            cr._reschedule(FA(jq)); assert jq.added == [], "dedup guard fail"
            # 2) queue empty → SKIP (idle par kuch schedule nahi)
            cr.pending_queue_count = lambda: 0
            jq2 = FJQ()
            cr._reschedule(FA(jq2)); assert jq2.added == [], "pending-only guard fail"
            # 3) pending + no job → EXACTLY ONE named add
            cr.pending_queue_count = lambda: 3
            jq3 = FJQ()
            cr._reschedule(FA(jq3))
            assert jq3.added == [cr._JOB_NAME], f"single-add fail: {jq3.added}"
        finally:
            cr.pending_queue_count = orig

    def test_empty_queue_run_adds_no_job(self):
        """Empty run → chain STOPS (pehle 2 jobs banati thi → storm)."""
        import custom_reviews as cr
        orig = cr.pending_queue_count

        class FJQ:
            def __init__(self): self.added = []
            def get_jobs_by_name(self, name): return []
            def run_once(self, cb, when=None, **kw): self.added.append(kw.get("name"))
        class FA: job_queue = FJQ()
        class FJob:
            application = FA(); bot = object()
        try:
            cr.pending_queue_count = lambda: 0
            asyncio.run(cr.custom_review_broadcast_job(FJob()))
            assert FJob.application.job_queue.added == [], \
                f"empty run par job add hua: {FJob.application.job_queue.added}"
        finally:
            cr.pending_queue_count = orig

    def test_watchdog_restarts_dead_chain(self):
        """Watchdog: pending rows + dead chain → dobara start."""
        import custom_reviews as cr
        orig = cr.pending_queue_count

        class FJQ:
            def __init__(self): self.added = []
            def get_jobs_by_name(self, name): return []
            def run_once(self, cb, when=None, **kw): self.added.append(kw.get("name"))
        class FA: job_queue = FJQ()
        class FJob:
            application = FA(); bot = object()
        try:
            cr.pending_queue_count = lambda: 7
            asyncio.run(cr.custom_review_watchdog_job(FJob()))
            assert FJob.application.job_queue.added == [cr._JOB_NAME]
        finally:
            cr.pending_queue_count = orig


# ═══════════════════════════════════════════════════════════════
# 🆕 v170.95 — RAILWAY VOLUME AUTO-DETECT (data-loss fix)
# Root cause: volume attached tha lekin DB_PATH set nahi → bot
# container-local shop.db likhta tha → har deploy par saara data
# WIPE (live DB 536KB/0 users paayi gayi 2026-09-11).
# ═══════════════════════════════════════════════════════════════
class TestRailwayVolumeAutoDetect:
    def test_explicit_db_path_wins(self):
        import os, importlib
        import database as dbm
        os.environ["DB_PATH"] = "/tmp/my_custom.db"
        os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = "/var/data"
        importlib.reload(dbm)
        try:
            assert dbm.DB_PATH == "/tmp/my_custom.db", dbm.DB_PATH
        finally:
            del os.environ["DB_PATH"]
            del os.environ["RAILWAY_VOLUME_MOUNT_PATH"]
            os.environ["DB_PATH"] = _REGDB
            importlib.reload(dbm)

    def test_volume_used_when_no_db_path(self):
        import os, importlib
        import database as dbm
        os.environ.pop("DB_PATH", None)
        os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = "/tmp/fake_vol"
        importlib.reload(dbm)
        try:
            assert dbm.DB_PATH == "/tmp/fake_vol/shop.db", dbm.DB_PATH
        finally:
            del os.environ["RAILWAY_VOLUME_MOUNT_PATH"]
            os.environ["DB_PATH"] = _REGDB
            importlib.reload(dbm)

    def test_default_local_when_no_env(self):
        import os, importlib
        import database as dbm
        os.environ.pop("DB_PATH", None)
        os.environ.pop("RAILWAY_VOLUME_MOUNT_PATH", None)
        importlib.reload(dbm)
        try:
            assert dbm.DB_PATH == "shop.db", dbm.DB_PATH
        finally:
            os.environ["DB_PATH"] = _REGDB
            importlib.reload(dbm)
