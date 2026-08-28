"""Regression coverage for v170.87.

* Uncategorized: full-width row, always BELOW every category, owner-editable
  label (settings panel in the Categories manager, premium emoji supported).
* Shop view switch: ONE toggle button that flips Classic ↔ Categorized.
* Assignment pools include out-of-stock products (pre-assign before restock).
* The add-product category picker uses the shop-style two-column blue grid.

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

ADMIN_ID = 424242


class _Query:
    def __init__(self, data, user_id=ADMIN_ID):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace()

    async def answer(self, *args, **kwargs):
        pass

    async def edit_message_text(self, text, **kwargs):
        self.text, self.kwargs = text, kwargs
        return SimpleNamespace(message_id=1)

    async def edit_message_caption(self, caption, **kwargs):
        self.text, self.kwargs = caption, kwargs
        return SimpleNamespace(message_id=1)


class V17087Tests(unittest.TestCase):
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

    def _picker(self, user_mode="categorized"):
        return keyboards.shop_categories_keyboard(
            database.get_products_grouped_by_category(), user_mode=user_mode)

    def test_uncategorized_renders_full_width_below_all_categories(self):
        cid = database.add_category("Tools", "💻")
        database.add_product(cid, "A", "x", 1.0, 0.0, 2)
        database.add_product(None, "Loose", "x", 1.0, 0.0, 2)
        rows = self._picker().inline_keyboard
        uncat = [(i, r) for i, r in enumerate(rows)
                 for b in r if b.callback_data == "shopcat_0"]
        cats = [i for i, r in enumerate(rows) for b in r
                if str(b.callback_data or "").startswith("shopcat_")
                and b.callback_data != "shopcat_0"]
        self.assertEqual(len(uncat), 1)
        self.assertEqual(len(uncat[0][1]), 1)          # full-width: alone in row
        self.assertGreater(uncat[0][0], max(cats))     # always below the grid

    def test_uncategorized_label_is_editable_with_premium_emoji(self):
        database.add_product(None, "Loose", "x", 1.0, 0.0, 2)
        database.set_setting(
            "shop_uncat_label",
            '[[HTML]]<tg-emoji emoji-id="9911">📦</tg-emoji> Other Stuff')
        tile = [b for r in self._picker().inline_keyboard
                for b in r if b.callback_data == "shopcat_0"][0]
        icon = (getattr(tile, "icon_custom_emoji_id", None)
                or (tile.api_kwargs or {}).get("icon_custom_emoji_id"))
        self.assertEqual(icon, "9911")
        self.assertEqual(tile.text.strip("\u3164").strip(), "Other Stuff")

    def test_uncat_settings_panel_and_text_flow(self):
        ctx = SimpleNamespace(user_data={})
        q = _Query("uncat_settings")
        asyncio.run(handlers_admin.uncat_settings_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertIn("Uncategorized", q.text)
        q = _Query("uncat_edit_label")
        asyncio.run(handlers_admin.uncat_settings_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertTrue(ctx.user_data.get("uncat_edit"))

        class _Msg:
            text = "🗃 Baqi Items"
            async def reply_text(self, text, **kwargs):
                return SimpleNamespace(message_id=2)

        done = asyncio.run(handlers_admin.uncat_label_received(
            SimpleNamespace(effective_user=SimpleNamespace(id=ADMIN_ID),
                            message=_Msg()), ctx))
        self.assertTrue(done)
        self.assertEqual(database.get_setting("shop_uncat_label", ""), "🗃 Baqi Items")
        # non-admin cannot use the panel
        q = _Query("uncat_reset", user_id=999)
        asyncio.run(handlers_admin.uncat_settings_callback(
            SimpleNamespace(callback_query=q), SimpleNamespace(user_data={})))
        self.assertEqual(database.get_setting("shop_uncat_label", ""), "🗃 Baqi Items")

    def test_single_view_toggle_flips_between_modes(self):
        cid = database.add_category("Tools", "💻")
        database.add_product(cid, "A", "x", 1.0, 0.0, 2)
        cbs = {b.callback_data for r in self._picker("categorized").inline_keyboard for b in r}
        self.assertIn("shopmode_classic", cbs)
        self.assertNotIn("shopmode_categorized", cbs)
        cbs = {b.callback_data for r in self._picker("classic").inline_keyboard for b in r}
        self.assertIn("shopmode_categorized", cbs)
        self.assertNotIn("shopmode_classic", cbs)

    def test_out_of_stock_products_are_assignable(self):
        oos = database.add_product(None, "OOS", "x", 1.0, 0.0, 0)
        pool = {int(p["id"]) for p in database.get_unassigned_in_stock_products()}
        self.assertIn(oos, pool)
        result = database.create_category_with_unassigned_in_stock_products(
            "Pre-stock", "📦", product_ids=[oos])
        self.assertTrue(result["created"])
        self.assertEqual(
            int(database.get_product(oos)["category_id"]),
            int(result["category_id"]))

    def test_add_product_category_picker_is_shop_style_grid(self):
        for i in range(3):
            database.add_category(f"Cat {i}", "📦")
        markup = keyboards.select_category_keyboard(database.get_all_categories())
        grid = [r for r in markup.inline_keyboard
                if any(str(b.callback_data or "").startswith("selcat_") for b in r)]
        self.assertTrue(grid)
        self.assertTrue(all(len(r) == 2 for r in grid))  # two-column like shop


if __name__ == "__main__":
    unittest.main()
