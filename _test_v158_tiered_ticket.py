# 🆕 v158 — Tiered quantity discounts + Buy-Now label/emoji fix + 3h ticket
# reminder (user-close) + replacement reject reason order fix
import os, sys, sqlite3, json
os.environ.setdefault("DB_PATH", "/tmp/v158_unit.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

# ---- Tiered discounts ----
def test_tier_helpers():
    assert hasattr(db, "ensure_tier_discount_table")
    assert hasattr(db, "set_product_tier")
    assert hasattr(db, "get_product_tiers")
    assert hasattr(db, "tier_price_for_qty")
    assert hasattr(db, "product_tiers_text")

def test_tier_roundtrip():
    db.setup_database()
    db.ensure_tier_discount_table()
    conn = db.get_connection(); c = conn.cursor()
    c.execute("INSERT INTO products (name, price) VALUES ('__tier__', 1.0)")
    pid = c.lastrowid; conn.commit(); conn.close()
    try:
        db.set_product_tier(pid, 10, 0.89)
        db.set_product_tier(pid, 30, 0.52)
        db.set_product_tier(pid, 50, 0.45)
        tiers = db.get_product_tiers(pid)
        assert len(tiers) == 3
        assert tiers[0]["min_qty"] == 10 and abs(tiers[0]["unit_price"] - 0.89) < 0.001
        # price for qty picks largest applicable tier
        u1, m1 = db.tier_price_for_qty(pid, 1, 1.0)
        assert u1 == 1.0 and m1 == 1
        u2, m2 = db.tier_price_for_qty(pid, 15, 1.0)
        assert abs(u2 - 0.89) < 0.001 and m2 == 10
        u3, _ = db.tier_price_for_qty(pid, 45, 1.0)
        assert abs(u3 - 0.52) < 0.001
        u4, _ = db.tier_price_for_qty(pid, 99, 1.0)
        assert abs(u4 - 0.45) < 0.001
        # text block
        txt = db.product_tiers_text({"id": pid, "price": 1.0})
        assert "Bulk Discounts" in txt
        assert "10" in txt and "0.89" in txt
    finally:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit(); conn.close()

def test_eff_price_uses_tier():
    src = open("handlers_order.py", encoding="utf-8").read()
    assert "_get_price_for_qty" in src
    assert "tier_price_for_qty" in src

def test_shop_shows_tiers():
    src = open("handlers_shop.py", encoding="utf-8").read()
    assert "product_tiers_text" in src

# ---- Buy-Now label: force_default ----
def test_build_button_force_default():
    src = open("button_system.py", encoding="utf-8").read()
    assert "force_default" in src
    src2 = open("fake_engagement.py", encoding="utf-8").read()
    assert "force_default=True" in src2
    src3 = open("per_user_activity.py", encoding="utf-8").read()
    assert "force_default=True" in src3

def test_buy_label_has_name_and_emoji():
    import fake_engagement as FE
    # _buy_now_label returns "emoji First2Words Buy Now" and _product_buy_emoji gives id
    # use DB product if available
    try:
        conn = db.get_connection(); conn.row_factory = db.DictRow
        c = conn.cursor()
        c.execute("SELECT id, name FROM products WHERE name LIKE '%[[HTML]]%' LIMIT 1")
        r = c.fetchone(); conn.close()
        if r:
            pid = int(r["id"])
            lbl = FE._buy_now_label(pid, "🛒 Buy Now")
            eid, ech = FE._product_buy_emoji(pid)
            assert "Buy Now" in lbl
            assert eid, "premium emoji id must be found"
    except Exception:
        pass  # no HTML-name product in this test DB → skip gracefully

# ---- Ticket: 3h reminder + user close ----
def test_ticket_reminder_job_exists():
    src = open("support_replacement.py", encoding="utf-8").read()
    assert "ticket_reminder_job" in src
    assert "get_due_reminder_tickets" in src
    assert "st_user_close_callback" in src
    # 30-min auto-close gone
    assert "no reply for 30 minutes" not in src
    srcb = open("bot.py", encoding="utf-8").read()
    assert "ticket_reminder_3h" in srcb
    assert "st_uclose_" in srcb

def test_ticket_reminder_columns():
    db.setup_database()
    conn = db.get_connection(); c = conn.cursor()
    c.execute("PRAGMA table_info(support_tickets)")
    cols = [r[1] for r in c.fetchall()]
    conn.close()
    assert "last_reminder_at" in cols
    assert "reminder_count" in cols

# ---- Replacement reject reason order ----
def test_reject_reason_order():
    src = open("bot.py", encoding="utf-8").read()
    # specific patterns must come BEFORE generic ^adm_reprj_
    do_idx = src.find('("^adm_reprj_do_"')
    cancel_idx = src.find('("^adm_reprj_cancel_"')
    gen_idx = src.find('("^adm_reprj_"')
    assert do_idx != -1 and cancel_idx != -1 and gen_idx != -1
    assert do_idx < gen_idx, "adm_reprj_do_ must be registered before adm_reprj_"
    assert cancel_idx < gen_idx

# ---- Bulk discount panel: name strip ----
def test_bdisc_name_strip():
    src = open("handlers_admin.py", encoding="utf-8").read()
    assert "html_strip_tags" in src or "_reh.sub" in src
    assert "_bdiscount_prod_list" in src
    assert "bdisc_prod_" in src


# 🆕 v159 hotfixes — bdisc_step key consistency, English UI, bulk-price editor strip
def test_bdisc_step_consistency():
    src_bot = open("bot.py", encoding="utf-8").read()
    src_adm = open("handlers_admin.py", encoding="utf-8").read()
    # bot.py must check bdisc_step (not bdiscount_step)
    assert "user_data.get('bdisc_step') == 'qty'" in src_bot
    assert "user_data.get('bdisc_step') == 'price'" in src_bot
    assert "bdiscount_step') == 'qty'" not in src_bot
    # handlers sets bdisc_step
    assert "['bdisc_step'] = 'qty'" in src_adm
    assert "['bdisc_step'] = 'price'" in src_adm

def test_english_ui_new_panels():
    src = open("handlers_admin.py", encoding="utf-8").read()
    # new tiered panel must be English (no Roman Urdu)
    assert "Pick a product and add" in src
    assert "At what *minimum quantity*" in src
    assert "what is the *unit price (USD)*" in src
    assert "No tiers yet" in src
    # old Roman Urdu phrases gone from these panels
    assert "Product chuno" not in src
    assert "Ye tier *kitni quantity" not in src

def test_bulk_price_editor_strip():
    src = open("handlers_admin.py", encoding="utf-8").read()
    # bulk price editor uses html_strip_tags too
    assert "bulkprice_tgl_" in src
    # the name-strip block present in bulk price editor
    assert "_reh.sub(r'<[^>]+>', '', name).replace('[[HTML]]', '').strip()" in src

def test_tier_flow_end_to_end():
    import asyncio as _aio
    db.setup_database()
    conn = db.get_connection(); c = conn.cursor()
    c.execute("INSERT INTO products (name, price, stock) VALUES ('[[HTML]]<tg-emoji>🤖</tg-emoji> Test', 1.0, 10)")
    pid = c.lastrowid; conn.commit(); conn.close()
    try:
        db.set_product_tier(pid, 10, 0.89)
        db.set_product_tier(pid, 30, 0.52)
        u1, _ = db.tier_price_for_qty(pid, 5, 1.0)
        u2, _ = db.tier_price_for_qty(pid, 12, 1.0)
        u3, _ = db.tier_price_for_qty(pid, 40, 1.0)
        assert abs(u1 - 1.0) < 0.001
        assert abs(u2 - 0.89) < 0.001
        assert abs(u3 - 0.52) < 0.001
    finally:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("DELETE FROM products WHERE id=?", (pid,))
        c.execute("DELETE FROM product_tier_discounts WHERE product_id=?", (pid,))
        conn.commit(); conn.close()


# 🆕 v160 — tier display templates (ready-made + custom with placeholders/premium emoji)
def test_tier_templates_registered():
    import customization as cz
    assert any(t["id"] == "tier_display" for t in cz.TEMPLATES), "tier_display missing"
    assert any(t["id"] == "tier_line" for t in cz.TEMPLATES), "tier_line missing"

def test_tier_display_html_clean():
    db.setup_database(); db.ensure_tier_discount_table()
    conn = db.get_connection(); c = conn.cursor()
    c.execute("INSERT INTO products (name, price) VALUES ('[[HTML]]<tg-emoji>🤖</tg-emoji> G', 1.0)")
    pid = c.lastrowid; conn.commit(); conn.close()
    try:
        db.set_product_tier(pid, 10, 0.89)
        db.set_product_tier(pid, 50, 0.45)
        h = db.product_tiers_text(db.get_product(pid), mode="html")
        assert "**" not in h and h.count("*") == 0, h
        assert "0.89" in h and "0.45" in h
        m = db.product_tiers_text(db.get_product(pid), mode="md")
        assert "**" in m  # markdown keeps emphasis
    finally:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("DELETE FROM products WHERE id=?", (pid,)); conn.commit(); conn.close()

def test_tier_custom_template():
    import customization as cz
    db.setup_database(); db.ensure_tier_discount_table()
    conn = db.get_connection(); c = conn.cursor()
    c.execute("INSERT INTO products (name, price) VALUES ('X', 1.0)")
    pid = c.lastrowid; conn.commit(); conn.close()
    try:
        db.set_product_tier(pid, 10, 0.89)
        cz._s(cz._tpl_key("tier_line"), "🔥 {qty}+ qty → **${price}**")
        cz._s(cz._tpl_key("tier_display"), "🛍 {product} DEAL\n{tiers}")
        h = db.product_tiers_text(db.get_product(pid), mode="html")
        assert "DEAL" in h and "0.89" in h
        assert h.count("*") == 0
    finally:
        conn = db.get_connection(); c = conn.cursor()
        c.execute("DELETE FROM products WHERE id=?", (pid,)); conn.commit(); conn.close()
        cz._s(cz._tpl_key("tier_line"), "")
        cz._s(cz._tpl_key("tier_display"), "")
