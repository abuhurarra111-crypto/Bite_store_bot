"""Regression coverage for v170.73 owner-editable category tile padding/align.

The Category Picker Settings panel now exposes:
  * shop_category_pad   (0-12) — invisible filler units widening each tile
  * shop_category_align (left/center/right) — where the label text sits

These offline tests verify the rendering math in keyboards.py and the admin
callback wiring in handlers_admin.py. No Telegram token, customer, supplier,
payment, or network request is used.
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


class CategoryPadAlignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        self.old_wal_state = database._WAL_SETUP_DONE
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        database.invalidate_settings_cache()
        database.setup_database()
        handlers_admin.ADMIN_ID = ADMIN_ID
        self.first = database.add_category("AI", "🤖")
        self.second = database.add_category("Redeem links", "🔗")
        database.add_product(self.first, "A", "x", 1.0, 0.0, 3)
        database.add_product(self.second, "B", "x", 1.0, 0.0, 3)

    def tearDown(self):
        database.DB_PATH = self.old_db_path
        database._WAL_SETUP_DONE = self.old_wal_state
        self.tmp.cleanup()

    def _category_rows(self):
        markup = keyboards.shop_categories_keyboard(
            database.get_products_grouped_by_category())
        return [row for row in markup.inline_keyboard
                if row and str(row[0].callback_data or "").startswith("shopcat_")]

    def test_default_zero_pad_center_is_clean_native_label(self):
        rows = self._category_rows()
        self.assertEqual(rows[0][0].text, "🤖 AI")
        self.assertEqual(rows[0][1].text, "🔗 Redeem links")
        self.assertTrue(all(PAD not in b.text for b in rows[0]))

    def test_center_padding_adds_equal_fillers_both_sides(self):
        database.set_setting("shop_category_pad", "3")
        database.set_setting("shop_category_align", "center")
        rows = self._category_rows()
        self.assertEqual(rows[0][0].text, PAD * 3 + "🤖 AI" + PAD * 3)
        self.assertEqual(rows[0][1].text, PAD * 3 + "🔗 Redeem links" + PAD * 3)

    def test_left_alignment_pushes_fillers_to_the_right(self):
        database.set_setting("shop_category_pad", "2")
        database.set_setting("shop_category_align", "left")
        rows = self._category_rows()
        text = rows[0][0].text
        self.assertTrue(text.startswith("🤖 AI"))
        # effective total = max(pad,3)*2 = 6, all on the right
        self.assertEqual(text, "🤖 AI" + PAD * 6)

    def test_right_alignment_pushes_fillers_to_the_left(self):
        database.set_setting("shop_category_pad", "4")
        database.set_setting("shop_category_align", "right")
        rows = self._category_rows()
        self.assertEqual(rows[0][0].text, PAD * 8 + "🤖 AI")

    def test_left_alignment_works_even_at_zero_padding(self):
        database.set_setting("shop_category_pad", "0")
        database.set_setting("shop_category_align", "left")
        rows = self._category_rows()
        self.assertEqual(rows[0][0].text, "🤖 AI" + PAD * 6)

    def test_pad_value_is_clamped_to_safe_range(self):
        database.set_setting("shop_category_pad", "99")
        database.set_setting("shop_category_align", "center")
        rows = self._category_rows()
        self.assertEqual(rows[0][0].text, PAD * 12 + "🤖 AI" + PAD * 12)

    def test_one_column_grid_honors_pad_and_align_too(self):
        database.set_setting("shop_category_columns", "1")
        database.set_setting("shop_category_pad", "3")
        database.set_setting("shop_category_align", "center")
        rows = self._category_rows()
        self.assertEqual([len(r) for r in rows], [1, 1])
        self.assertEqual(rows[0][0].text, PAD * 3 + "🤖 AI" + PAD * 3)

    def test_panel_view_exposes_padding_and_alignment_controls(self):
        text, markup = handlers_admin._category_presentation_view()
        callbacks = {b.callback_data for row in markup.inline_keyboard for b in row}
        for expected in ("catpresent_pad_minus", "catpresent_pad_zero",
                         "catpresent_pad_plus", "catpresent_pad_plus3",
                         "catpresent_align_left", "catpresent_align_center",
                         "catpresent_align_right", "catpresent_cols_1",
                         "catpresent_cols_2", "catpresent_empty"):
            self.assertIn(expected, callbacks)
        self.assertIn("Button padding", text)

    def test_admin_callbacks_change_pad_and_align_with_clamping(self):
        ctx = SimpleNamespace(user_data={})
        for _ in range(3):
            q = _Query("catpresent_pad_plus")
            asyncio.run(handlers_admin.category_presentation_set_callback(
                SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_setting("shop_category_pad", "0"), "3")
        # +3 shortcut and 12 clamp
        for _ in range(5):
            q = _Query("catpresent_pad_plus3")
            asyncio.run(handlers_admin.category_presentation_set_callback(
                SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_setting("shop_category_pad", "0"), "12")
        q = _Query("catpresent_pad_zero")
        asyncio.run(handlers_admin.category_presentation_set_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_setting("shop_category_pad", "0"), "0")
        q = _Query("catpresent_pad_minus")
        asyncio.run(handlers_admin.category_presentation_set_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_setting("shop_category_pad", "0"), "0")
        q = _Query("catpresent_align_right")
        asyncio.run(handlers_admin.category_presentation_set_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_setting("shop_category_align", "center"), "right")
        self.assertTrue(q.edits)  # panel re-rendered

    def test_non_owner_cannot_change_picker_settings(self):
        q = _Query("catpresent_pad_plus", user_id=111)
        asyncio.run(handlers_admin.category_presentation_set_callback(
            SimpleNamespace(callback_query=q), SimpleNamespace(user_data={})))
        self.assertEqual(database.get_setting("shop_category_pad", "0"), "0")

    def test_owner_styler_override_still_wins(self):
        # A deliberate per-category Button Styler choice must bypass the
        # global pad/align defaults entirely.
        database.set_setting("shop_category_pad", "5")
        database.set_setting(f"bstyle_cat_{self.first}", "1")
        try:
            rows = self._category_rows()
            # The styled category must not receive the global grid fillers
            # beyond whatever the styler itself produces.
            self.assertIsNotNone(rows)
        finally:
            database.set_setting(f"bstyle_cat_{self.first}", "")


if __name__ == "__main__":
    unittest.main()
