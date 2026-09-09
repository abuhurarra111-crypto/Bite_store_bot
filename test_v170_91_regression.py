# -*- coding: utf-8 -*-
"""
v170.91 REGRESSION SUITE — Task 2 (Bugs 1-4 + Update 1)
Repo ke andar persist karta hai (/tmp nahi). Run:
    python3 -m pytest test_v170_91_regression.py -v
"""
import os, sys, shutil, tempfile, asyncio, sqlite3, threading, http.server, socketserver, random

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
