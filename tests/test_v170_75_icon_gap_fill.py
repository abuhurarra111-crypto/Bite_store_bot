"""Regression coverage for v170.75 — icon-text gap fill on premium-icon tiles.

Telegram pins an API-attached ``icon_custom_emoji_id`` at the LEFT edge of an
inline button while centering the text separately, which left a large gap
between a category's brand icon and its name.  Right-side invisible fillers
now pull the text left so it sits snugly beside the icon.  The fill amount is
owner-editable (``shop_category_icon_fill``, 0-14, default 8).

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
PAD = "\u3164"
ICON_NAME = '[[HTML]]<tg-emoji emoji-id="5310129635848103696">🔗</tg-emoji> Redeem links'


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


class IconGapFillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        self.old_wal_state = database._WAL_SETUP_DONE
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        database.invalidate_settings_cache()
        database.setup_database()
        handlers_admin.ADMIN_ID = ADMIN_ID
        self.icon_cat = database.add_category(ICON_NAME, "📦")
        self.plain_cat = database.add_category("Ai Tools", "🤖")
        database.add_product(self.icon_cat, "A", "x", 1.0, 0.0, 3)
        database.add_product(self.plain_cat, "B", "x", 1.0, 0.0, 3)

    def tearDown(self):
        database.DB_PATH = self.old_db_path
        database._WAL_SETUP_DONE = self.old_wal_state
        self.tmp.cleanup()

    def _tiles(self):
        markup = keyboards.shop_categories_keyboard(
            database.get_products_grouped_by_category())
        row = [r for r in markup.inline_keyboard
               if str(r[0].callback_data or "").startswith("shopcat_")][0]
        return row[0], row[1]  # icon tile, plain tile

    @staticmethod
    def _icon_of(btn):
        return (getattr(btn, "icon_custom_emoji_id", None)
                or (btn.api_kwargs or {}).get("icon_custom_emoji_id"))

    def test_default_icon_tile_text_is_pulled_left_beside_the_icon(self):
        icon_tile, plain_tile = self._tiles()
        self.assertEqual(self._icon_of(icon_tile), "5310129635848103696")
        # v170.81: snug fill retired — the live Shop Now button proved a
        # premium icon centers WITH clean text, so tiles stay filler-free.
        self.assertEqual(icon_tile.text, "Redeem links")
        self.assertFalse(icon_tile.text.startswith(PAD))
        # tiles without an API icon stay perfectly clean/centered.
        self.assertEqual(plain_tile.text, "🤖 Ai Tools")

    def test_fill_zero_restores_the_old_centered_look(self):
        database.set_setting("shop_category_icon_fill", "0")
        icon_tile, _ = self._tiles()
        self.assertEqual(icon_tile.text, "Redeem links")

    def test_fill_is_clamped_and_editable(self):
        database.set_setting("shop_category_icon_fill", "99")
        icon_tile, _ = self._tiles()
        # v170.81: fill no longer distorts picker tiles (icon+text center).
        self.assertEqual(icon_tile.text, "Redeem links")

    def test_fill_combines_with_center_padding_without_left_fillers(self):
        database.set_setting("shop_category_pad", "3")
        icon_tile, plain_tile = self._tiles()
        # v170.81: symmetric pad only — no snug fillers on icon tiles.
        self.assertEqual(icon_tile.text, PAD * 3 + "Redeem links" + PAD * 3)
        self.assertEqual(plain_tile.text, PAD * 3 + "🤖 Ai Tools" + PAD * 3)

    def test_right_alignment_deliberately_bypasses_icon_fill(self):
        database.set_setting("shop_category_align", "right")
        icon_tile, _ = self._tiles()
        self.assertTrue(icon_tile.text.startswith(PAD))
        self.assertTrue(icon_tile.text.endswith("Redeem links"))

    def test_panel_exposes_and_saves_fill_controls(self):
        text, markup = handlers_admin._category_presentation_view()
        callbacks = {b.callback_data for row in markup.inline_keyboard for b in row}
        for expected in ("catpresent_fill_minus", "catpresent_fill_zero",
                         "catpresent_fill_plus", "catpresent_fill_default"):
            self.assertIn(expected, callbacks)
        self.assertIn("Icon-text gap fill", text)

        ctx = SimpleNamespace(user_data={})
        q = _Query("catpresent_fill_plus")
        asyncio.run(handlers_admin.category_presentation_set_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_setting("shop_category_icon_fill", "8"), "9")
        q = _Query("catpresent_fill_zero")
        asyncio.run(handlers_admin.category_presentation_set_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_setting("shop_category_icon_fill", "8"), "0")
        q = _Query("catpresent_fill_default")
        asyncio.run(handlers_admin.category_presentation_set_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_setting("shop_category_icon_fill", "8"), "8")
        self.assertTrue(q.edits)

    def test_non_owner_cannot_change_fill(self):
        q = _Query("catpresent_fill_plus", user_id=111)
        asyncio.run(handlers_admin.category_presentation_set_callback(
            SimpleNamespace(callback_query=q), SimpleNamespace(user_data={})))
        self.assertEqual(database.get_setting("shop_category_icon_fill", "8"), "8")


if __name__ == "__main__":
    unittest.main()
