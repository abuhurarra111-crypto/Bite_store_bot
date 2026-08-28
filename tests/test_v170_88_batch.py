"""v170.88 batch tests:
1. Assign pool excludes enabled freebies + already-categorized products.
2. Uncategorized full settings (label/header/color/hide/reset) drive shop.
3. View-toggle button honors Customization color (btn_style_shop_mode_toggle).
4. bc_freebie broadcasts bypass the v60 buyability pre-flight.
5. All categories always visible (no limit; empty/OOS cats shown; heal flag).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class V17088BatchTests(unittest.TestCase):
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

    def tearDown(self):
        import database
        if self._wal is not None:
            database._WAL_SETUP_DONE = self._wal
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def _product(self, name, cat_id=None, stock=5):
        conn = self.database.get_connection()
        try:
            cur = conn.execute(
                "INSERT INTO products (name, price, stock, category_id, is_active)"
                " VALUES (?, 100, ?, ?, 1)",
                (name, stock, cat_id),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    # ── #1 assign pool ────────────────────────────────────────────────
    def test_assign_pool_excludes_enabled_freebies_and_categorized(self):
        db = self.database
        cat = db.add_category("Cat", "📦")
        in_cat = self._product("InCat", cat_id=cat)
        loose = self._product("Loose")
        freebie = self._product("FreebieProd", stock=0)
        conn = db.get_connection()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS freebies (id INTEGER PRIMARY KEY,"
                " product_id INTEGER, enabled INTEGER DEFAULT 1)"
            )
            conn.execute(
                "INSERT INTO freebies (product_id, enabled) VALUES (?, 1)",
                (freebie,),
            )
            conn.commit()
        finally:
            conn.close()
        pool_ids = {int(p["id"]) for p in db.get_unassigned_in_stock_products()}
        self.assertIn(loose, pool_ids)
        self.assertNotIn(in_cat, pool_ids, "already-categorized must not appear")
        self.assertNotIn(freebie, pool_ids, "enabled freebie must not appear")

    # ── #2 uncat settings drive grouped + keyboard ────────────────────
    def test_uncat_settings_label_desc_style_hide(self):
        db = self.database
        self._product("LooseA")
        db.set_setting("shop_uncat_label", "⭐ Others")
        db.set_setting("shop_uncat_desc", "Baqi sab yahan")
        db.set_setting("shop_uncat_style", "success")
        db.invalidate_settings_cache()
        grouped = db.get_products_grouped_by_category()
        self.assertIn(0, grouped)
        self.assertIn("Others", str(grouped[0]["name"]))
        self.assertEqual(grouped[0]["button_style"], "success")
        self.assertIn("Baqi sab", str(grouped[0].get("description") or ""))

        import keyboards
        markup = keyboards.shop_categories_keyboard(grouped)
        tiles = [b for r in markup.inline_keyboard for b in r
                 if b.callback_data == "shopcat_0"]
        self.assertEqual(len(tiles), 1)
        style = getattr(tiles[0], "style", None) or (
            (tiles[0].api_kwargs or {}).get("style"))
        self.assertEqual(style, "success")

        db.set_setting("shop_uncat_hidden", "1")
        db.invalidate_settings_cache()
        markup = keyboards.shop_categories_keyboard(
            db.get_products_grouped_by_category())
        tiles = [b for r in markup.inline_keyboard for b in r
                 if b.callback_data == "shopcat_0"]
        self.assertEqual(tiles, [], "hidden uncat tile must disappear")

    # ── #3 toggle color ───────────────────────────────────────────────
    def test_view_toggle_uses_customization_color(self):
        db = self.database
        self._product("LooseB")
        db.set_setting("btn_style_shop_mode_toggle", "success")
        db.invalidate_settings_cache()
        import keyboards
        markup = keyboards.shop_categories_keyboard(
            db.get_products_grouped_by_category())
        toggles = [b for r in markup.inline_keyboard for b in r
                   if str(b.callback_data or "").startswith("shopmode_")]
        self.assertTrue(toggles)
        style = getattr(toggles[0], "style", None) or (
            (toggles[0].api_kwargs or {}).get("style"))
        self.assertEqual(style, "success")

    # ── #4 freebie broadcast bypass ───────────────────────────────────
    def test_bc_freebie_bypasses_buyability_preflight(self):
        import asyncio
        from types import SimpleNamespace
        db = self.database
        oos = self._product("OOSFree", stock=0)
        db.set_setting("dest_mode", "group_only")
        db.set_setting("dest_chat_id", "-100555")
        db.set_setting("maint_enabled", "0")
        db.invalidate_settings_cache()
        import fake_engagement
        self.assertFalse(fake_engagement._is_product_broadcastable(oos))
        sent = []

        class MockBot:
            async def get_me(self):
                return SimpleNamespace(username="Bite_storee_bot")

            async def get_chat(self, chat_id):
                return SimpleNamespace(id=-100555)

            async def send_message(self, chat_id=None, text=None, **k):
                sent.append(chat_id)
                return SimpleNamespace(message_id=1,
                                       chat=SimpleNamespace(id=chat_id))

        n = asyncio.run(fake_engagement.broadcast_store_message(
            MockBot(), "🎁 claim!", pid=oos, tpl_id="bc_freebie"))
        self.assertEqual(n, 1, "freebie alert must reach the destination")
        n2 = asyncio.run(fake_engagement.broadcast_store_message(
            MockBot(), "🛒 buy!", pid=oos, tpl_id="bc_purchase"))
        self.assertEqual(n2, 0, "non-freebie OOS broadcast stays blocked")

    # ── #5 all categories always visible ─────────────────────────────
    def test_all_categories_visible_no_limit(self):
        db = self.database
        ids = [db.add_category(f"Cat{i}", "📦") for i in range(15)]
        oos_cat = db.add_category("OOSCat", "📦")
        self._product("OOSOnly", cat_id=oos_cat, stock=0)
        grouped = db.get_products_grouped_by_category()
        for cid in ids + [oos_cat]:
            self.assertIn(cid, grouped, f"category {cid} must be on the page")

        import self_heal
        db.set_setting("all_cats_visible_v17088", "")
        conn = db.get_connection()
        try:
            conn.execute("UPDATE categories SET show_when_empty=0")
            conn.commit()
        finally:
            conn.close()
        db.invalidate_settings_cache()
        self_heal._heal_all_categories_always_visible()
        db.invalidate_settings_cache()
        self.assertEqual(db.get_setting("all_cats_visible_v17088", ""), "1")
        conn = db.get_connection()
        try:
            zero = conn.execute(
                "SELECT COUNT(*) FROM categories WHERE COALESCE(show_when_empty,0)=0"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(zero, 0, "heal must flip every category to visible")
        # one-time: second run must be a no-op even after manual re-hide
        conn = db.get_connection()
        try:
            conn.execute(
                "UPDATE categories SET show_when_empty=0 WHERE name='Cat0'")
            conn.commit()
        finally:
            conn.close()
        self_heal._heal_all_categories_always_visible()
        conn = db.get_connection()
        try:
            manual = conn.execute(
                "SELECT show_when_empty FROM categories WHERE name='Cat0'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(manual, 0, "one-time heal must respect admin choice")


if __name__ == "__main__":
    unittest.main()
