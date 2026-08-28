"""Focused v170.65 category-management regressions.

Covers the owner-approved non-destructive category delete, atomic Add Category
assignment wizard, pagination selection state, supplier mirror persistence, and
the shared customer category navigation controls.  No network/API credentials
are used.
"""

import asyncio
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOT_TOKEN", "test-token-not-real")
os.environ.setdefault("ADMIN_ID", "424242")
_IMPORT_TEMP = tempfile.TemporaryDirectory()
os.environ["DB_PATH"] = str(Path(_IMPORT_TEMP.name) / "import.db")

import button_system
import customization
import database
import ext_suppliers
import handlers_admin
import handlers_shop
import keyboards


class _FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.caption = ""
        self.text_html_urled = ""
        self.caption_html_urled = ""
        self.entities = []
        self.caption_entities = []
        self.replies = []

    async def reply_text(self, text, *args, **kwargs):
        self.replies.append((text, args, kwargs))
        return SimpleNamespace(message_id=len(self.replies))


class _FakeQuery:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _FakeMessage()
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, *args, **kwargs):
        self.edits.append((text, args, kwargs))

    async def edit_message_caption(self, *args, **kwargs):
        raise RuntimeError("not a media message")


class CategoryManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        database.setup_database()

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _product(category_id, name, stock=5):
        return database.add_product(category_id, name, "description", 2.0, 0.5, stock)

    @staticmethod
    def _markup_callbacks(markup):
        return [[button.callback_data for button in row] for row in markup.inline_keyboard]

    def test_safe_delete_unassigns_only_and_reassignment_rules_hold(self):
        old_category = database.add_category("Old category")
        kept_category = database.add_category("Kept category")
        linked = self._product(old_category, "Linked in stock", stock=7)
        linked_out_of_stock = self._product(old_category, "Linked out of stock", stock=0)
        unassigned = self._product(None, "Already unassigned", stock=3)
        assigned_elsewhere = self._product(kept_category, "Already assigned", stock=9)
        out_of_stock = self._product(None, "Out of stock", stock=0)
        archived = self._product(None, "Archived", stock=5)
        invalid_legacy_link = self._product(999999, "Broken legacy link", stock=8)

        conn = database.get_connection()
        try:
            conn.execute("UPDATE products SET is_archived=1 WHERE id=?", (archived,))
            conn.execute("""INSERT INTO orders
                            (user_id, product_id, product_name, price, status)
                            VALUES (?,?,?,?,?)""",
                         (123, linked, "Linked in stock", 2.0, "delivered"))
            conn.commit()
        finally:
            conn.close()

        initial_candidates = {int(p["id"]) for p in database.get_unassigned_in_stock_products()}
        # v170.87: out-of-stock unassigned products are deliberately eligible
        # now, so the owner can pre-assign items before restocking them.
        self.assertEqual(initial_candidates,
                         {unassigned, invalid_legacy_link, out_of_stock})
        before = dict(database.get_product(linked))

        deleted = database.delete_category(old_category)
        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["unassigned_count"], 2)
        self.assertEqual(deleted["in_stock_count"], 1)
        self.assertIsNone(database.get_category(old_category))
        self.assertIsNone(database.get_product(linked_out_of_stock)["category_id"])
        after = dict(database.get_product(linked))
        self.assertIsNone(after["category_id"])
        # Required preservation invariants: no product lifecycle, stock or
        # order row changed while deleting a category.
        self.assertEqual(after["is_active"], before["is_active"])
        self.assertEqual(after["is_hidden"], before["is_hidden"])
        self.assertEqual(after["is_archived"], before["is_archived"])
        self.assertEqual(after["stock"], before["stock"])
        conn = database.get_connection()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders WHERE product_id=?", (linked,)).fetchone()[0], 1)
        finally:
            conn.close()

        after_delete_candidates = {int(p["id"]) for p in database.get_unassigned_in_stock_products()}
        # v170.87: zero-stock items (freshly unassigned or already loose) are
        # candidates too; archived mirrors stay excluded.
        self.assertEqual(after_delete_candidates,
                         {linked, linked_out_of_stock, unassigned,
                          invalid_legacy_link, out_of_stock})
        # v170.87: out-of-stock products re-enter the pool too (owner can
        # pre-assign them before restocking).
        self.assertIn(linked_out_of_stock, after_delete_candidates)
        self.assertIn(out_of_stock, after_delete_candidates)  # v170.87: eligible now
        self.assertNotIn(archived, after_delete_candidates)
        self.assertNotIn(assigned_elsewhere, after_delete_candidates)

        category_count_before_stale_submit = len(database.get_categories(include_inactive=True))
        stale_submit = database.create_category_with_unassigned_in_stock_products(
            "Must not partially create", "📦",
            product_ids=[linked, unassigned, assigned_elsewhere, out_of_stock, archived],
        )
        self.assertFalse(stale_submit["created"])
        self.assertEqual(stale_submit["requested_count"], 5)
        self.assertEqual(stale_submit["assigned_count"], 0)
        # v170.87: out_of_stock is eligible now, so only the two truly
        # unavailable picks (assigned_elsewhere + archived) block the submit.
        self.assertEqual(len(stale_submit["unavailable_product_ids"]), 2)
        self.assertEqual(len(database.get_categories(include_inactive=True)), category_count_before_stale_submit)
        self.assertIsNone(database.get_product(linked)["category_id"])
        self.assertIsNone(database.get_product(unassigned)["category_id"])

        # A fresh all-eligible confirmation assigns the selected products
        # together in the one category-creation transaction.
        created = database.create_category_with_unassigned_in_stock_products(
            "Rebuilt category", "📦", product_ids=[linked, unassigned])
        self.assertTrue(created["created"])
        new_category = created["category_id"]
        self.assertEqual(created["requested_count"], 2)
        self.assertEqual(created["assigned_count"], 2)
        self.assertEqual(int(database.get_product(linked)["category_id"]), new_category)
        self.assertEqual(int(database.get_product(unassigned)["category_id"]), new_category)
        self.assertEqual(int(database.get_product(assigned_elsewhere)["category_id"]), kept_category)
        self.assertIsNone(database.get_product(out_of_stock)["category_id"])
        self.assertIsNone(database.get_product(archived)["category_id"])

        later_candidates = {int(p["id"]) for p in database.get_unassigned_in_stock_products()}
        self.assertNotIn(linked, later_candidates)
        self.assertNotIn(unassigned, later_candidates)
        self.assertIn(invalid_legacy_link, later_candidates)

        deleted_again = database.delete_category_and_unassign_products(new_category)
        self.assertTrue(deleted_again["deleted"])
        eligible_again = {int(p["id"]) for p in database.get_unassigned_in_stock_products()}
        self.assertIn(linked, eligible_again)
        self.assertIn(unassigned, eligible_again)
        self.assertIn(out_of_stock, eligible_again)  # v170.87: eligible now

    def test_new_wizard_assignment_survives_supplier_mirror_refresh(self):
        ext_suppliers.ensure_ext_supplier_tables()
        supplier_id = ext_suppliers.add_supplier(
            "v170.65 supplier", "insta_api", "https://example.invalid", "test-key")
        ext_id = ext_suppliers.upsert_ext_product(
            supplier_id, "unassigned-ext", "Unassigned mirror", "desc", 1.0, 6,
            category_id=0, source_active=True)
        ext_suppliers.update_ext_product(ext_id, synced_to_shop=1)
        shop_id = int(ext_suppliers.get_ext_product(ext_id)["shop_product_id"])
        self.assertIsNone(database.get_product(shop_id)["category_id"])

        result = database.create_category_with_unassigned_in_stock_products(
            "Supplier assignment", product_ids=[shop_id])
        category_id = int(result["category_id"])
        self.assertEqual(result["assigned_count"], 1)
        self.assertEqual(int(ext_suppliers.get_ext_product(ext_id)["category_id"]), category_id)
        ext_suppliers.update_ext_product(ext_id, stock=7)
        self.assertEqual(int(database.get_product(shop_id)["category_id"]), category_id)

    def test_dangling_future_category_reference_is_assigned_explicitly(self):
        # A malformed old backup can contain category_id=1 before any category
        # exists.  Creating the first category must not make it look assigned
        # accidentally; the transaction captures eligibility first.
        dangling = self._product(1, "Future-ID dangling reference", stock=4)
        self.assertEqual({int(p["id"]) for p in database.get_unassigned_in_stock_products()}, {dangling})
        result = database.create_category_with_unassigned_in_stock_products(
            "First real category", product_ids=[dangling])
        self.assertEqual(result["category_id"], 1)
        self.assertEqual(result["assigned_count"], 1)
        self.assertEqual(int(database.get_product(dangling)["category_id"]), 1)

    def test_new_category_and_assignments_roll_back_together_on_error(self):
        candidate = self._product(None, "Atomic candidate", stock=4)
        before_category_count = len(database.get_categories(include_inactive=True))
        conn = database.get_connection()
        try:
            conn.execute("""CREATE TRIGGER test_abort_category_assignment
                            BEFORE UPDATE OF category_id ON products
                            WHEN NEW.category_id IS NOT NULL
                            BEGIN SELECT RAISE(ABORT, 'test assignment abort'); END""")
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(sqlite3.DatabaseError):
            database.create_category_with_unassigned_in_stock_products(
                "Must rollback", product_ids=[candidate])
        self.assertEqual(len(database.get_categories(include_inactive=True)), before_category_count)
        self.assertIsNone(database.get_product(candidate)["category_id"])

    def test_wizard_renders_paginated_checkbox_select_page_and_finalizes(self):
        candidates = [self._product(None, f"Wizard product {number:02d}", stock=number + 1)
                      for number in range(13)]
        context = SimpleNamespace(user_data={"cat_n": "Wizard Category"})
        message = _FakeMessage("📦")
        update = SimpleNamespace(effective_user=SimpleNamespace(id=handlers_admin.ADMIN_ID), message=message)

        state = asyncio.run(handlers_admin.cat_emoji_received(update, context))
        self.assertEqual(state, handlers_admin.CAT_PRODUCT_SELECT)
        self.assertEqual(len(database.get_categories(include_inactive=True)), 0,
                         "category must not exist before the final confirmation")
        first_text, _args, first_kwargs = message.replies[-1]
        first_markup = first_kwargs["reply_markup"]
        self.assertIn("Page *1/2*", first_text)
        first_callbacks = self._markup_callbacks(first_markup)
        item_callbacks = [callback for row in first_callbacks for callback in row
                          if callback and callback.startswith("catpick_tgl_")]
        self.assertEqual(len(item_callbacks), 12)
        self.assertIn("catpick_pageall_0", [callback for row in first_callbacks for callback in row])
        self.assertIn("catpick_clear_0", [callback for row in first_callbacks for callback in row])

        select_q = _FakeQuery("catpick_pageall_0", handlers_admin.ADMIN_ID)
        select_state = asyncio.run(handlers_admin.category_product_picker_select_page_callback(
            SimpleNamespace(callback_query=select_q), context))
        self.assertEqual(select_state, handlers_admin.CAT_PRODUCT_SELECT)
        self.assertEqual(len(context.user_data["cat_selected_products"]), 12)
        select_markup = select_q.edits[-1][2]["reply_markup"]
        self.assertIn("catpick_finish", [callback for row in self._markup_callbacks(select_markup) for callback in row])

        clear_q = _FakeQuery("catpick_clear_0", handlers_admin.ADMIN_ID)
        clear_state = asyncio.run(handlers_admin.category_product_picker_clear_callback(
            SimpleNamespace(callback_query=clear_q), context))
        self.assertEqual(clear_state, handlers_admin.CAT_PRODUCT_SELECT)
        self.assertEqual(context.user_data["cat_selected_products"], set())
        clear_callbacks = [callback for row in self._markup_callbacks(
            clear_q.edits[-1][2]["reply_markup"]) for callback in row]
        self.assertIn("catpick_empty", clear_callbacks)

        # Select page works again after a clear; selections persist when
        # moving to the later page for an individual checkbox tick.
        select_again_q = _FakeQuery("catpick_pageall_0", handlers_admin.ADMIN_ID)
        asyncio.run(handlers_admin.category_product_picker_select_page_callback(
            SimpleNamespace(callback_query=select_again_q), context))
        self.assertEqual(len(context.user_data["cat_selected_products"]), 12)

        page_q = _FakeQuery("catpick_page_1", handlers_admin.ADMIN_ID)
        asyncio.run(handlers_admin.category_product_picker_page_callback(
            SimpleNamespace(callback_query=page_q), context))
        second_markup = page_q.edits[-1][2]["reply_markup"]
        second_items = [callback for row in self._markup_callbacks(second_markup) for callback in row
                        if callback and callback.startswith("catpick_tgl_")]
        self.assertEqual(len(second_items), 1)

        toggle_q = _FakeQuery(second_items[0], handlers_admin.ADMIN_ID)
        asyncio.run(handlers_admin.category_product_picker_toggle_callback(
            SimpleNamespace(callback_query=toggle_q), context))
        self.assertEqual(len(context.user_data["cat_selected_products"]), 13)

        finish_q = _FakeQuery("catpick_finish", handlers_admin.ADMIN_ID)
        finish_state = asyncio.run(handlers_admin.category_product_picker_finish_callback(
            SimpleNamespace(callback_query=finish_q), context))
        self.assertEqual(finish_state, handlers_admin.ConversationHandler.END)
        categories = database.get_categories(include_inactive=True)
        self.assertEqual(len(categories), 1)
        category_id = int(categories[0]["id"])
        self.assertEqual({int(database.get_product(pid)["category_id"]) for pid in candidates}, {category_id})
        self.assertNotIn("cat_selected_products", context.user_data)
        self.assertIn("Assigned in-stock products: *13*", finish_q.edits[-1][0])

    def test_shared_category_footer_has_exactly_back_and_home_and_is_editable(self):
        cat_id = database.add_category("Navigation category")
        product_id = self._product(cat_id, "Navigation product", stock=4)
        product = database.get_product(product_id)
        database.set_setting("btn_label_nav_categories_back_medium", "↩️ Back to category picker")
        database.set_setting("btn_label_nav_shop_home_medium", "🏠 My Main Screen")
        button_system.set_button_style("nav_categories_back", "success")
        button_system.set_button_style("nav_shop_home", "danger")

        markup, page, total_pages = keyboards.shop_category_products_keyboard(
            [product], cat_id, page=1, user=SimpleNamespace(id=123))
        self.assertEqual((page, total_pages), (1, 1))
        footer = markup.inline_keyboard[-1]
        self.assertEqual(len(footer), 2)
        self.assertEqual([button.callback_data for button in footer], ["shop", "main_menu"])
        self.assertIn("Back to category picker", footer[0].text)
        self.assertIn("My Main Screen", footer[1].text)
        self.assertEqual(getattr(footer[0], "style", None) or footer[0].api_kwargs.get("style"), "success")
        self.assertEqual(getattr(footer[1], "style", None) or footer[1].api_kwargs.get("style"), "danger")
        callbacks = [callback for row in self._markup_callbacks(markup) for callback in row]
        self.assertNotIn("shopmode_classic", callbacks)
        self.assertTrue(all(len((callback or "").encode("utf-8")) <= 64 for callback in callbacks))

        # Category pagination remains separate, but the last row is always the
        # same two-control footer (never a Classic switch).
        extra_products = [database.get_product(self._product(cat_id, f"Page item {n}", stock=2))
                          for n in range(10)]
        paged_markup, _page, pages = keyboards.shop_category_products_keyboard(
            [product] + extra_products, cat_id, page=1, user=SimpleNamespace(id=123))
        self.assertEqual(pages, 2)
        self.assertEqual([button.callback_data for button in paged_markup.inline_keyboard[-1]],
                         ["shop", "main_menu"])
        self.assertIn(f"shopcatpg_{cat_id}_2",
                      [callback for row in self._markup_callbacks(paged_markup) for callback in row])

        # A buyer-visible empty category page gets the same reusable footer.
        empty_id = database.add_category("Visible empty", show_when_empty=True)
        empty_q = _FakeQuery(f"shopcat_{empty_id}", 123)
        asyncio.run(handlers_shop.shop_category_callback(
            SimpleNamespace(callback_query=empty_q), SimpleNamespace(user_data={})))
        empty_footer = empty_q.edits[-1][2]["reply_markup"].inline_keyboard[-1]
        self.assertEqual([button.callback_data for button in empty_footer], ["shop", "main_menu"])

        # The Shop screen editor exposes all shared controls used by category
        # pages: product buttons, shared prev/next, Back and Home.
        ids = {item["id"] for item in customization.SCREEN_TREE["shop_screen"]["buttons"]}
        self.assertTrue({"shop_product", "nav_shop_prev_page", "nav_shop_next_page",
                         "nav_categories_back", "nav_shop_home"}.issubset(ids))


if __name__ == "__main__":
    unittest.main()
