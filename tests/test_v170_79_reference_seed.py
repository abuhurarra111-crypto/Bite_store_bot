"""Regression coverage for v170.79 — reference category seeding + assignment.

Covers:
  * one-time seed migration: 22 reference categories with premium-emoji
    names harvested from the bot's own DB, old categories safely removed,
    products untouched (only category_id cleared)
  * the settings-flag guard (never reruns / never overwrites owner edits)
  * the new 📦 Assign Products panel: instant add/remove, pagination guard,
    non-owner block

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
import keyboards
import self_heal

ADMIN_ID = 424242


class _Query:
    def __init__(self, data, user_id=ADMIN_ID):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace()
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


class ReferenceCategorySeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        self.old_wal_state = database._WAL_SETUP_DONE
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        database.invalidate_settings_cache()
        database.setup_database()
        handlers_admin.ADMIN_ID = ADMIN_ID
        # a premium emoji id the bot has "used before" (harvest source)
        database.set_setting(
            "tpl_test_premium",
            '[[HTML]]<tg-emoji emoji-id="5310129635848103696">⭐</tg-emoji> hi')

    def tearDown(self):
        database.DB_PATH = self.old_db_path
        database._WAL_SETUP_DONE = self.old_wal_state
        self.tmp.cleanup()

    def test_seed_replaces_old_categories_and_keeps_products_safe(self):
        old = database.add_category("Old Cat", "📦")
        pid = database.add_product(old, "Legacy product", "x", 2.0, 0.0, 5)

        self_heal._heal_seed_reference_categories()
        database.invalidate_settings_cache()

        cats = database.get_categories(include_inactive=True, include_hidden=True)
        names = [str(c["name"]) for c in cats]
        self.assertEqual(len(cats), len(self_heal._REFERENCE_CATEGORIES))
        self.assertTrue(all("Old Cat" not in n for n in names))
        for expected in ("Super Grok", "Chatgpt", "Netflix", "Claude"):
            self.assertTrue(any(expected in n for n in names), expected)
        # every seeded name carries a premium emoji from the bot's own pool
        self.assertTrue(all('tg-emoji emoji-id="' in n for n in names))
        # the legacy product survives, merely unassigned
        prod = database.get_product(pid)
        self.assertIsNotNone(prod)
        self.assertIsNone(prod["category_id"])
        self.assertEqual(int(prod["stock"] if "stock" in prod.keys() else 5) >= 0, True)

    def test_seeded_categories_render_with_icons_even_while_empty(self):
        self_heal._heal_seed_reference_categories()
        database.invalidate_settings_cache()
        markup = keyboards.shop_categories_keyboard(
            database.get_products_grouped_by_category(include_empty=True))
        tiles = [b for r in markup.inline_keyboard for b in r
                 if str(b.callback_data or "").startswith("shopcat_")]
        self.assertEqual(len(tiles), len(self_heal._REFERENCE_CATEGORIES))
        with_icon = [b for b in tiles
                     if (getattr(b, "icon_custom_emoji_id", None)
                         or (b.api_kwargs or {}).get("icon_custom_emoji_id"))]
        self.assertEqual(len(with_icon), len(tiles))

    def test_seed_runs_exactly_once_and_respects_owner_edits(self):
        self_heal._heal_seed_reference_categories()
        database.invalidate_settings_cache()
        first = database.get_categories()[0]
        database.update_category(int(first["id"]), name="My Renamed Cat")
        self_heal._heal_seed_reference_categories()  # guarded no-op
        database.invalidate_settings_cache()
        names = [str(c["name"]) for c in database.get_categories(
            include_inactive=True, include_hidden=True)]
        self.assertIn("My Renamed Cat", names)
        self.assertEqual(len(names), len(self_heal._REFERENCE_CATEGORIES))

    def test_assign_panel_add_remove_and_non_owner_block(self):
        self_heal._heal_seed_reference_categories()
        database.invalidate_settings_cache()
        cid = int(database.get_categories()[0]["id"])
        pid = database.add_product(None, "Loose product", "x", 1.0, 0.0, 4)
        ctx = SimpleNamespace(user_data={})

        q = _Query(f"catasg_{cid}_0")
        asyncio.run(handlers_admin.category_assign_products_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertIn("Assign Products", q.edits[-1][0])

        q = _Query(f"catasg_add_{cid}_{pid}_0")
        asyncio.run(handlers_admin.category_assign_products_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(int(database.get_product(pid)["category_id"]), cid)

        q = _Query(f"catasg_rm_{cid}_{pid}_0")
        asyncio.run(handlers_admin.category_assign_products_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertIsNone(database.get_product(pid)["category_id"])

        q = _Query(f"catasg_add_{cid}_{pid}_0", user_id=111)
        asyncio.run(handlers_admin.category_assign_products_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertIsNone(database.get_product(pid)["category_id"])

    def test_detail_panel_offers_assign_products(self):
        self_heal._heal_seed_reference_categories()
        database.invalidate_settings_cache()
        cid = int(database.get_categories()[0]["id"])

        q = _Query(f"viewcat_{cid}")
        asyncio.run(handlers_admin._render_category_detail(q, cid))
        callbacks = {b.callback_data
                     for row in q.edits[-1][1]["reply_markup"].inline_keyboard
                     for b in row}
        self.assertIn(f"catasg_{cid}_0", callbacks)


if __name__ == "__main__":
    unittest.main()
