"""Regression coverage for v170.82 — seeded reference categories removed.

The owner now builds categories himself with the bulk-select Add Category
flow (name → tick products → ✅ Create & Assign Selected), so the one-time
v170.82 heal deletes every still-untouched v170.79 seeded category.  Products
are only UNASSIGNED — stock, pricing, delivery, orders stay untouched — and
owner-renamed categories survive.

No Telegram token, customer, supplier, payment, or network request is used.
"""

import asyncio
import os
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
import self_heal

ADMIN_ID = 424242


def _seeded_name(base, eid="5310129635848103696", emoji="🤖"):
    return f'[[HTML]]<tg-emoji emoji-id="{eid}">{emoji}</tg-emoji> {base}'


class _Query:
    def __init__(self, data, user_id=ADMIN_ID):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace()

    async def answer(self, *args, **kwargs):
        pass

    async def edit_message_text(self, text, **kwargs):
        self.last = text
        return SimpleNamespace(message_id=1)

    async def edit_message_caption(self, caption, **kwargs):
        self.last = caption
        return SimpleNamespace(message_id=1)


class SeedRemovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        self.old_wal_state = database._WAL_SETUP_DONE
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        database.invalidate_settings_cache()
        database.setup_database()
        handlers_admin.ADMIN_ID = ADMIN_ID

    def tearDown(self):
        database.DB_PATH = self.old_db_path
        database._WAL_SETUP_DONE = self.old_wal_state
        self.tmp.cleanup()

    def test_heal_deletes_seeded_categories_but_products_survive_unassigned(self):
        cid = database.add_category(_seeded_name("Chatgpt"), "")
        pid = database.add_product(cid, "P", "x", 1.0, 0.0, 3)
        self_heal._heal_remove_seeded_reference_categories()
        self.assertEqual(database.get_all_categories(include_inactive=True), [])
        row = database.get_connection().execute(
            "SELECT category_id, stock FROM products WHERE id=?", (pid,)).fetchone()
        self.assertIsNone(row["category_id"])   # unassigned only
        self.assertEqual(int(row["stock"]), 3)  # stock untouched

    def test_heal_spares_owner_renamed_and_owner_made_categories_and_runs_once(self):
        renamed = database.add_category("My Own Category", "📦")
        seeded = database.add_category(_seeded_name("Netflix"), "")
        self_heal._heal_remove_seeded_reference_categories()
        left = [int(c["id"]) for c in database.get_all_categories(include_inactive=True)]
        self.assertEqual(left, [renamed])
        # one-time guard: newly re-added seeded-style names are never touched
        again = database.add_category(_seeded_name("Claude"), "")
        self_heal._heal_remove_seeded_reference_categories()
        left = {int(c["id"]) for c in database.get_all_categories(include_inactive=True)}
        self.assertEqual(left, {renamed, again})

    def test_bulk_select_add_category_assigns_all_ticked_products(self):
        pids = [database.add_product(None, f"P{i}", "x", 1.0, 0.0, 2)
                for i in range(3)]
        ctx = SimpleNamespace(user_data={})

        class _Msg:
            text = "Bulk Cat"
            async def reply_text(self, text, **kwargs):
                _Msg.last = text
                return SimpleNamespace(message_id=2)

        update = SimpleNamespace(effective_user=SimpleNamespace(id=ADMIN_ID),
                                 message=_Msg())
        asyncio.run(handlers_admin.cat_name_received(update, ctx))
        self.assertIn("Select Products", _Msg.last)
        for pid in pids[:2]:
            q = _Query(f"catpick_tgl_{pid}_0")
            asyncio.run(handlers_admin.category_product_picker_toggle_callback(
                SimpleNamespace(callback_query=q), ctx))
        q = _Query("catpick_finish")
        asyncio.run(handlers_admin.category_product_picker_finish_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertIn("Category Created", q.last)
        cat = [c for c in database.get_all_categories(include_inactive=True)
               if "Bulk Cat" in str(c["name"])]
        inside = {int(p["id"]) for p in
                  database.get_products_in_category(int(cat[0]["id"]))}
        self.assertEqual(inside, set(pids[:2]))  # exactly the ticked two

    def test_non_admin_cannot_finish_bulk_flow(self):
        ctx = SimpleNamespace(user_data={"cat_n": "X"})
        q = _Query("catpick_finish", user_id=999)
        asyncio.run(handlers_admin.category_product_picker_finish_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_all_categories(include_inactive=True), [])


if __name__ == "__main__":
    unittest.main()
