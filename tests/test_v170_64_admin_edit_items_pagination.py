"""Regression coverage for owner Edit Items pagination.

The realistic restored catalog has 120 products. Telegram rejects inline
keyboards with more than 100 total buttons, so these offline tests assert that
all owner product pages remain safely under that limit while preserving every
existing item/action callback. No Telegram token, customer, supplier, payment,
or network request is used.
"""

import ast
import asyncio
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOT_TOKEN", "test-token-not-real")
os.environ["ADMIN_ID"] = "424242"
_IMPORT_TEMP = tempfile.TemporaryDirectory()
os.environ["DB_PATH"] = str(Path(_IMPORT_TEMP.name) / "import.db")

import database
import handlers_admin
import keyboards

ADMIN_ID = 424242


class _Message:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=len(self.replies))


class _Query:
    def __init__(self, data, user_id=ADMIN_ID):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _Message()
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return SimpleNamespace(message_id=len(self.edits))

    async def edit_message_caption(self, caption, **kwargs):
        self.edits.append((caption, kwargs))
        return SimpleNamespace(message_id=len(self.edits))


class AdminEditItemsPaginationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        self.old_wal_state = database._WAL_SETUP_DONE
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        database.setup_database()
        handlers_admin.ADMIN_ID = ADMIN_ID
        self.category_id = database.add_category("Pagination test category", "📦")
        for number in range(1, 121):
            database.add_product(self.category_id, f"Catalog item {number:03d}",
                                 "test", 4.0, 0.0, 5)

    def tearDown(self):
        database.DB_PATH = self.old_db_path
        database._WAL_SETUP_DONE = self.old_wal_state
        self.tmp.cleanup()

    @staticmethod
    def _buttons(markup):
        return [button for row in markup.inline_keyboard for button in row]

    def test_120_item_catalog_is_safely_paginated_and_preserves_actions(self):
        products = database.get_all_products(include_hidden=True, include_inactive=True)
        markup = keyboards.admin_products_keyboard(products)
        buttons = self._buttons(markup)
        callbacks = [button.callback_data for button in buttons]
        product_callbacks = [value for value in callbacks if value.startswith("viewprod_")]

        self.assertEqual(len(products), 120)
        self.assertEqual(len(product_callbacks), keyboards.ADMIN_PRODUCTS_PAGE_SIZE)
        # Preserve the existing database sort order (newest product first).
        self.assertEqual(product_callbacks,
                         [f"viewprod_{int(product['id'])}" for product in products[:20]])
        self.assertLessEqual(len(buttons), 100)
        self.assertTrue(all(len(row) <= 8 for row in markup.inline_keyboard))
        self.assertIn("adminprodpg_1", callbacks)
        self.assertNotIn("adminprodpg_0", callbacks)  # heading is the non-clickable page indicator
        self.assertTrue({"add_product", "bulkprice_start", "bdisc_start",
                         "bulkprod_start", "admin_panel"}.issubset(callbacks))

        last_page = keyboards.admin_products_keyboard(products, page=999)
        last_callbacks = [button.callback_data for button in self._buttons(last_page)]
        self.assertEqual([value for value in last_callbacks if value.startswith("viewprod_")],
                         [f"viewprod_{int(product['id'])}" for product in products[100:]])
        self.assertIn("adminprodpg_4", last_callbacks)
        self.assertNotIn("adminprodpg_6", last_callbacks)
        self.assertLessEqual(len(last_callbacks), 100)

    def test_direct_handler_and_page_callback_render_realistic_catalog(self):
        query = _Query("admin_products")
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={})

        asyncio.run(handlers_admin.admin_products_callback(update, context))
        self.assertEqual(len(query.answers), 1)
        self.assertEqual(len(query.edits), 1)
        first_text, first_kwargs = query.edits[-1]
        self.assertIn("Edit Items", first_text)
        self.assertIn("120", first_text)
        self.assertIn("1/6", first_text)
        self.assertLessEqual(len(self._buttons(first_kwargs["reply_markup"])), 100)

        query.data = "adminprodpg_5"
        asyncio.run(handlers_admin.admin_products_page_callback(update, context))
        last_text, last_kwargs = query.edits[-1]
        self.assertIn("6/6", last_text)
        last_callbacks = [button.callback_data
                          for button in self._buttons(last_kwargs["reply_markup"])]
        self.assertIn("adminprodpg_4", last_callbacks)
        self.assertNotIn("adminprodpg_6", last_callbacks)
        self.assertLessEqual(len(last_callbacks), 100)

        # A stale paginator callback after a catalog change must clamp safely.
        query.data = "adminprodpg_999"
        asyncio.run(handlers_admin.admin_products_page_callback(update, context))
        self.assertIn("6/6", query.edits[-1][0])

    def test_defensive_page_size_cap_remains_under_telegram_limit(self):
        products = database.get_all_products(include_hidden=True, include_inactive=True)
        markup = keyboards.admin_products_keyboard(products, per_page=999)
        buttons = self._buttons(markup)
        self.assertEqual(sum(button.callback_data.startswith("viewprod_")
                             for button in buttons), 80)
        # First/last pages have one navigation control; middle pages can have
        # two, so every direct caller stays at or below 87 buttons.
        self.assertEqual(len(buttons), 86)
        self.assertLessEqual(len(buttons), 87)
        self.assertLessEqual(len(buttons), 100)

    def test_non_owner_cannot_render_or_browse_owner_catalog(self):
        query = _Query("admin_products", user_id=999999)
        update = SimpleNamespace(callback_query=query)
        asyncio.run(handlers_admin.admin_products_callback(update, SimpleNamespace(user_data={})))
        self.assertEqual(query.edits, [])
        self.assertEqual(query.answers[-1][0], ("❌",))

        page_query = _Query("adminprodpg_1", user_id=999999)
        asyncio.run(handlers_admin.admin_products_page_callback(
            SimpleNamespace(callback_query=page_query), SimpleNamespace(user_data={})))
        self.assertEqual(page_query.edits, [])
        self.assertEqual(page_query.answers[-1][0], ("❌",))

    def test_dispatcher_has_one_non_conflicting_page_route(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        def list_elements(expr):
            if isinstance(expr, (ast.List, ast.Tuple)):
                return list(expr.elts)
            if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
                return list_elements(expr.left) + list_elements(expr.right)
            return []

        matches = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.For):
                continue
            for pair in list_elements(node.iter):
                if not (isinstance(pair, ast.Tuple) and len(pair.elts) >= 2):
                    continue
                pattern, handler = pair.elts[:2]
                if not (isinstance(pattern, ast.Constant)
                        and isinstance(pattern.value, str)
                        and isinstance(handler, ast.Name)):
                    continue
                if re.match(pattern.value, "adminprodpg_123"):
                    matches.append((pattern.value, handler.id))

        self.assertEqual(matches,
                         [("^adminprodpg_\\d+$", "admin_products_page_callback")])
        self.assertIn('(\"^admin_products$\", admin_products_callback)', source)


if __name__ == "__main__":
    unittest.main()
