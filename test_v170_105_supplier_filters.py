import os
import sys
import tempfile
import sqlite3
import pytest

sys.path.insert(0, os.path.dirname(__file__))

def test_supplier_product_filtering_rules():
    """Verify supplier product filtering:
    1. Active + In stock -> SHOWN (🟢)
    2. Active + Out of stock (stock=0) -> SHOWN (🔴 OOS)
    3. Deactivated by admin (owner_active=0) -> HIDDEN
    4. Deactivated by supplier (source_active=0) -> HIDDEN
    5. active=0 -> HIDDEN
    6. Deleted by supplier (missing_since > 0) -> HIDDEN
    7. Linked shop product archived/deactivated -> HIDDEN
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()

    os.environ["DB_PATH"] = db_path
    os.environ["BOT_TOKEN"] = "12345:dummy"
    os.environ["ADMIN_ID"] = "7105782769"

    import database
    database.setup_database()
    import ext_suppliers
    ext_suppliers.ensure_ext_supplier_tables()

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Create supplier
    c.execute("INSERT INTO ext_suppliers (id, name, adapter, base_url, api_key, enabled) VALUES (1, 'Test Sup', 'custom', 'https://api.test.com', 'key123', 1)")

    # 1. Active + in stock
    c.execute("""INSERT INTO ext_products (id, supplier_id, remote_id, name, cost_usd, stock, owner_active, source_active, active, missing_since)
                 VALUES (1, 1, 'r1', 'Active In-Stock Prod', 5.0, 10, 1, 1, 1, NULL)""")

    # 2. Active + Out of stock (stock=0) -> MUST BE KEPT AND SHOWN!
    c.execute("""INSERT INTO ext_products (id, supplier_id, remote_id, name, cost_usd, stock, owner_active, source_active, active, missing_since)
                 VALUES (2, 1, 'r2', 'Active OOS Prod', 8.0, 0, 1, 1, 1, NULL)""")

    # 3. Deactivated by admin (owner_active=0) -> MUST BE HIDDEN
    c.execute("""INSERT INTO ext_products (id, supplier_id, remote_id, name, cost_usd, stock, owner_active, source_active, active, missing_since)
                 VALUES (3, 1, 'r3', 'Admin Deactivated Prod', 4.0, 10, 0, 1, 1, NULL)""")

    # 4. Deactivated by supplier (source_active=0) -> MUST BE HIDDEN
    c.execute("""INSERT INTO ext_products (id, supplier_id, remote_id, name, cost_usd, stock, owner_active, source_active, active, missing_since)
                 VALUES (4, 1, 'r4', 'Supplier Deactivated Prod', 6.0, 10, 1, 0, 1, NULL)""")

    # 5. active=0 -> MUST BE HIDDEN
    c.execute("""INSERT INTO ext_products (id, supplier_id, remote_id, name, cost_usd, stock, owner_active, source_active, active, missing_since)
                 VALUES (5, 1, 'r5', 'Inactive Prod', 7.0, 10, 1, 1, 0, NULL)""")

    # 6. Deleted by supplier (missing_since > 0) -> MUST BE HIDDEN
    c.execute("""INSERT INTO ext_products (id, supplier_id, remote_id, name, cost_usd, stock, owner_active, source_active, active, missing_since)
                 VALUES (6, 1, 'r6', 'Supplier Deleted Prod', 9.0, 10, 1, 1, 1, 1726900000.0)""")

    # 7. Linked to archived shop product -> MUST BE HIDDEN
    c.execute("""INSERT INTO products (id, name, price, is_active, is_archived) VALUES (101, 'Archived Shop Prod', 15.0, 1, 1)""")
    c.execute("""INSERT INTO ext_products (id, supplier_id, remote_id, name, cost_usd, stock, owner_active, source_active, active, missing_since, shop_product_id)
                 VALUES (7, 1, 'r7', 'Archived Shop Linked', 10.0, 5, 1, 1, 1, NULL, 101)""")

    # 8. Linked to deactivated shop product -> MUST BE HIDDEN
    c.execute("""INSERT INTO products (id, name, price, is_active, is_archived) VALUES (102, 'Deactivated Shop Prod', 12.0, 0, 0)""")
    c.execute("""INSERT INTO ext_products (id, supplier_id, remote_id, name, cost_usd, stock, owner_active, source_active, active, missing_since, shop_product_id)
                 VALUES (8, 1, 'r8', 'Deactivated Shop Linked', 8.0, 5, 1, 1, 1, NULL, 102)""")

    conn.commit()
    conn.close()

    active_prods = ext_suppliers.get_active_supplier_products(1)
    active_ids = {p["id"] for p in active_prods}

    # Verify:
    assert active_ids == {1, 2}, f"Expected only {{1, 2}}, got {active_ids}!"

    # Verify item 2 has stock=0 and is preserved
    oos_item = next(p for p in active_prods if p["id"] == 2)
    assert oos_item["stock"] == 0

    try:
        os.remove(db_path)
    except Exception:
        pass
    print("✅ All filtering rules PASSED perfectly!")

if __name__ == "__main__":
    test_supplier_product_filtering_rules()
