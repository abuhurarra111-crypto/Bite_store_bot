"""v170.90 tests — supplier auto-sync must never eject a product from the
category the owner assigned ("5 minute baad Uncategorized" root-cause).

1. mirror_ext_to_products default (autosync path) preserves shop category.
2. Explicit category update via update_ext_product still syncs it.
3. assign/unassign from the shop side keep ext_products aligned.
4. One-time heal re-anchors drifted ext rows to the shop category.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class V17090SupplierCategoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.environ["DB_PATH"] = self._tmp.name
        import importlib
        import database
        self._wal = getattr(database, "_WAL_SETUP_DONE", None)
        importlib.reload(database)
        database.setup_database()
        database.invalidate_settings_cache()
        self.database = database
        import ext_suppliers
        ext_suppliers.ensure_ext_supplier_tables()
        self.ext = ext_suppliers
        # one supplier + one synced ext product mirrored to the shop
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO ext_suppliers (id, name, adapter, base_url, api_key, enabled)"
            " VALUES (1, 'Sup', 'insta', 'http://x', 'k', 1)")
        conn.execute(
            "INSERT INTO ext_products (id, supplier_id, remote_id, name,"
            " cost_usd, stock, markup_pct, sell_price, synced_to_shop,"
            " category_id, owner_active, source_active, active)"
            " VALUES (11, 1, 'r1', 'GPT Plus', 1.0, 10, 40, 1.4, 1, 0, 1, 1, 1)")
        conn.commit()
        conn.close()
        pid, was_new = ext_suppliers.mirror_ext_to_products(11)
        self.pid = pid
        self.assertTrue(was_new)

    def tearDown(self):
        import database
        if self._wal is not None:
            database._WAL_SETUP_DONE = self._wal
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def _shop_cat(self):
        p = self.database.get_product(self.pid)
        return p["category_id"]

    def _ext_cat(self):
        conn = self.database.get_connection()
        try:
            return conn.execute(
                "SELECT category_id FROM ext_products WHERE id=11"
            ).fetchone()[0]
        finally:
            conn.close()

    def test_autosync_tick_preserves_owner_category(self):
        db = self.database
        cat = db.add_category("ChatGPT", "🤖")
        self.assertTrue(db.assign_product_to_category(self.pid, cat))
        # shop-side assign must sync the supplier master record too
        self.assertEqual(self._ext_cat(), cat)
        # the EXACT call the 30s auto-sync job makes (cost/stock change):
        self.ext.update_ext_product(11, cost_usd=2.0, stock=55)
        self.assertEqual(self._shop_cat(), cat,
                         "supplier tick must NOT eject the product")
        p = db.get_product(self.pid)
        self.assertEqual(int(p["stock"]), 55, "stock must still mirror")

    def test_raw_mirror_default_never_touches_category(self):
        db = self.database
        cat = db.add_category("Tools", "🛠")
        conn = db.get_connection()
        conn.execute("UPDATE products SET category_id=? WHERE id=?",
                     (cat, self.pid))
        conn.commit()
        conn.close()
        # ext row still says 0 (drifted) — default mirror must not clobber
        self.ext.mirror_ext_to_products(11)
        self.assertEqual(self._shop_cat(), cat)

    def test_explicit_category_update_still_propagates(self):
        db = self.database
        cat = db.add_category("Gemini", "✨")
        self.ext.update_ext_product(11, category_id=cat)
        self.assertEqual(self._shop_cat(), cat,
                         "supplier-panel category change must still apply")

    def test_unassign_syncs_ext_and_survives_tick(self):
        db = self.database
        cat = db.add_category("VPN", "🛡")
        db.assign_product_to_category(self.pid, cat)
        self.assertTrue(db.unassign_product_from_category(self.pid, cat))
        self.assertEqual(int(self._ext_cat() or 0), 0)
        self.ext.update_ext_product(11, cost_usd=3.0, stock=7)
        self.assertIn(self._shop_cat(), (None, 0),
                      "tick must not re-attach the removed category")

    def test_one_time_heal_reanchors_drift(self):
        import self_heal
        db = self.database
        cat = db.add_category("Office", "📄")
        conn = db.get_connection()
        conn.execute("UPDATE products SET category_id=? WHERE id=?",
                     (cat, self.pid))
        conn.execute(
            "UPDATE ext_products SET category_id=0, shop_product_id=?"
            " WHERE id=11", (self.pid,))
        conn.commit()
        conn.close()
        db.set_setting("ext_cat_sync_v17090", "")
        db.invalidate_settings_cache()
        self_heal._heal_ext_mirror_category_backfill()
        self.assertEqual(int(self._ext_cat() or 0), cat)
        db.invalidate_settings_cache()
        self.assertEqual(db.get_setting("ext_cat_sync_v17090", ""), "1")
        # flag set → second run is a no-op
        conn = db.get_connection()
        conn.execute("UPDATE ext_products SET category_id=0 WHERE id=11")
        conn.commit()
        conn.close()
        self_heal._heal_ext_mirror_category_backfill()
        self.assertEqual(int(self._ext_cat() or 0), 0)


if __name__ == "__main__":
    unittest.main()
