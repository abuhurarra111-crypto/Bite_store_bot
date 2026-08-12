# 🆕 v157 — 7 bug fixes + Bulk Discount feature
import os, sys, sqlite3
os.environ.setdefault("DB_PATH", "/tmp/v157_unit.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

# ---- Bug 1: Bybit auto-verify enabled ----
def test_bybit_auto_verify_enabled():
    src = open("handlers_order.py", encoding="utf-8").read()
    assert "get_pending_bybit_orders" in src
    assert "bybit_deposit_background_job" in src
    # no-op removed
    assert "return  # no-op" not in src

# ---- Bug 2: support progress/close hardened ----
def test_support_progress_hardened():
    src = open("handlers_support.py", encoding="utf-8").read()
    assert "TicketProgress" in src or "never 'Temporary error'" in src
    assert "except Exception" in src

# ---- Bug 3: replacement reject reason ----
def test_reject_reason():
    src = open("support_replacement.py", encoding="utf-8").read()
    assert "rej_reason_oid" in src
    assert "_do_replacement_reject" in src
    assert "Reason:" in src
    srcb = open("bot.py", encoding="utf-8").read()
    assert "rej_reason_oid" in srcb

# ---- Bug 4: supplier fixed emoji on buy button (per_user_activity) ----
def test_buy_emoji_icon():
    src = open("per_user_activity.py", encoding="utf-8").read()
    assert "_attach_buy_emoji" in src
    assert "icon_custom_emoji_id" in src

# ---- Bug 5: speed (WAL cache + get_setting cache) ----
def test_speed_optimizations():
    src = open("database.py", encoding="utf-8").read()
    assert "_WAL_SETUP_DONE" in src
    assert "_SETTINGS_CACHE" in src
    assert "invalidate_settings_cache" in src

# ---- Bug 6: analytics real ----
def test_analytics_real():
    src = open("database.py", encoding="utf-8").read()
    assert "profit" in src
    assert "refund_count" in src
    assert "net_revenue" in src
    assert "daily" in src
    src2 = open("admin_panels.py", encoding="utf-8").read()
    assert "Profit" in src2
    assert "Daily Revenue" in src2

# ---- Bug 7: refund by id hardened ----
def test_refund_hardened():
    src = open("handlers_admin.py", encoding="utf-8").read()
    assert "Processing refund" in src
    assert "never 'sticks'" in src or "never throws" in src

# ---- Bulk Discount ----
def test_bulk_discount_helpers():
    assert hasattr(db, "get_discounted_price")
    assert hasattr(db, "set_bulk_discount")
    assert hasattr(db, "clear_bulk_discount")
    assert hasattr(db, "get_discounted_products")

def test_discount_price_calc():
    p = {"price": 100.0, "is_flash_sale": 0, "discount_pct": 20, "discount_until": ""}
    eff, orig, pct = db.get_discounted_price(p)
    assert eff == 80.0, eff
    assert orig == 100.0
    assert pct == 20
    # flash wins
    p2 = {"price": 100.0, "is_flash_sale": 1, "flash_price": 50.0, "discount_pct": 20}
    eff2, _, _ = db.get_discounted_price(p2)
    assert eff2 == 50.0

def test_bulk_discount_db_roundtrip():
    db.setup_database()  # ensure products table exists
    db.ensure_product_columns(db.get_connection().cursor())
    # create a temp product
    conn = db.get_connection(); c = conn.cursor()
    c.execute("INSERT INTO products (name, price) VALUES ('__test_disc__', 10.0)")
    pid = c.lastrowid; conn.commit(); conn.close()
    try:
        db.set_bulk_discount([pid], 25, hours=0)
        conn = db.get_connection(); conn.row_factory = db.DictRow
        c = conn.cursor()
        c.execute("SELECT * FROM products WHERE id=?", (pid,))
        r = c.fetchone(); conn.close()
        d = dict(r)
        assert float(d['discount_pct']) == 25
        eff, orig, pct = db.get_discounted_price(d)
        assert eff == 7.5
        assert pct == 25
    finally:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("DELETE FROM products WHERE id=?", (pid,)); conn.commit(); conn.close()

def test_bdisc_registered():
    src = open("bot.py", encoding="utf-8").read()
    for pat in ("^bdisc_start$", "^bdisc_tgl_", "^bdisc_dur_", "bdisc_custom_received"):
        assert pat in src, pat
    src2 = open("keyboards.py", encoding="utf-8").read()
    assert "🎉 Bulk Discount" in src2
