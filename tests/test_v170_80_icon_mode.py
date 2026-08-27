"""Regression coverage for v170.80 — centered emoji mode vs premium-left mode.

Telegram pins a premium image icon at the LEFT edge of an inline button (a
client limitation no bot can change).  The owner asked for emoji + name
centered together, so the picker gained an icon-style toggle:
  * "emoji"   → the premium emoji's plain fallback stays inside the text and
                the pair renders perfectly centered (no API icon, no fillers)
  * "premium" → the real premium image icon, left-pinned with snug text

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
PAD = "\u3164"
NAME = '[[HTML]]<tg-emoji emoji-id="5310129635848103696">⭐</tg-emoji> Chatgpt'


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


class IconModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        self.old_wal_state = database._WAL_SETUP_DONE
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        database.invalidate_settings_cache()
        database.setup_database()
        handlers_admin.ADMIN_ID = ADMIN_ID
        self.cid = database.add_category(NAME, "")
        database.add_product(self.cid, "P", "x", 1.0, 0.0, 3)

    def tearDown(self):
        database.DB_PATH = self.old_db_path
        database._WAL_SETUP_DONE = self.old_wal_state
        self.tmp.cleanup()

    def _tile(self):
        markup = keyboards.shop_categories_keyboard(
            database.get_products_grouped_by_category())
        return [b for r in markup.inline_keyboard for b in r
                if str(b.callback_data or "").startswith("shopcat_")][0]

    @staticmethod
    def _icon_of(btn):
        return (getattr(btn, "icon_custom_emoji_id", None)
                or (btn.api_kwargs or {}).get("icon_custom_emoji_id"))

    def test_emoji_mode_renders_fallback_inside_centered_clean_text(self):
        database.set_setting("shop_category_icon_mode", "emoji")
        tile = self._tile()
        self.assertIsNone(self._icon_of(tile))
        self.assertEqual(tile.text, "⭐ Chatgpt")
        self.assertNotIn(PAD, tile.text)

    def test_premium_mode_uses_shop_now_formula_icon_plus_clean_centered_text(self):
        # v170.81: the live Shop Now button proved icon + clean text render
        # CENTERED together — so premium tiles carry ZERO filler characters.
        database.set_setting("shop_category_icon_mode", "premium")
        tile = self._tile()
        self.assertEqual(self._icon_of(tile), "5310129635848103696")
        self.assertEqual(tile.text, "Chatgpt")
        self.assertNotIn(PAD, tile.text)

    def test_panel_toggle_saves_both_modes(self):
        ctx = SimpleNamespace(user_data={})
        q = _Query("catpresent_iconmode_emoji")
        asyncio.run(handlers_admin.category_presentation_set_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_setting("shop_category_icon_mode", ""), "emoji")
        q = _Query("catpresent_iconmode_premium")
        asyncio.run(handlers_admin.category_presentation_set_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_setting("shop_category_icon_mode", ""), "premium")
        text, markup = handlers_admin._category_presentation_view()
        callbacks = {b.callback_data for row in markup.inline_keyboard for b in row}
        self.assertIn("catpresent_iconmode_emoji", callbacks)
        self.assertIn("catpresent_iconmode_premium", callbacks)

    def test_heal_sets_centered_mode_and_themes_seeded_fallbacks_once(self):
        self_heal._heal_icon_mode_and_themed_fallbacks()
        database.invalidate_settings_cache()
        self.assertEqual(database.get_setting("shop_category_icon_mode", ""), "emoji")
        name = str(database.get_category(self.cid)["name"])
        self.assertIn(">🤖</tg-emoji> Chatgpt", name)  # ⭐ → themed 🤖
        # owner later switches back — the one-time heal must not force again
        database.set_setting("shop_category_icon_mode", "premium")
        self_heal._heal_icon_mode_and_themed_fallbacks()
        database.invalidate_settings_cache()
        self.assertEqual(database.get_setting("shop_category_icon_mode", ""), "premium")

    def test_both_mode_keeps_premium_icon_and_centered_emoji_text(self):
        database.set_setting("shop_category_icon_mode", "both")
        tile = self._tile()
        # premium image icon still attached (left-pinned by Telegram)...
        self.assertEqual(self._icon_of(tile), "5310129635848103696")
        # ...while the fallback emoji rides inside clean CENTERED text.
        self.assertEqual(tile.text, "⭐ Chatgpt")
        self.assertNotIn(PAD, tile.text)

    def test_both_heal_sets_mode_once_and_respects_owner(self):
        self_heal._heal_icon_mode_both_upgrade()
        database.invalidate_settings_cache()
        self.assertEqual(database.get_setting("shop_category_icon_mode", ""), "premium")
        database.set_setting("shop_category_icon_mode", "premium")
        self_heal._heal_icon_mode_both_upgrade()
        database.invalidate_settings_cache()
        self.assertEqual(database.get_setting("shop_category_icon_mode", ""), "premium")

    def test_panel_offers_all_three_modes(self):
        text, markup = handlers_admin._category_presentation_view()
        callbacks = {b.callback_data for row in markup.inline_keyboard for b in row}
        self.assertIn("catpresent_iconmode_both", callbacks)
        ctx = SimpleNamespace(user_data={})
        q = _Query("catpresent_iconmode_both")
        asyncio.run(handlers_admin.category_presentation_set_callback(
            SimpleNamespace(callback_query=q), ctx))
        self.assertEqual(database.get_setting("shop_category_icon_mode", ""), "both")
        database.set_setting("shop_category_icon_mode", "both")
        tile = self._tile()
        # hybrid: premium icon attached AND fallback emoji inside clean text
        self.assertEqual(self._icon_of(tile), "5310129635848103696")
        self.assertEqual(tile.text, "⭐ Chatgpt")

    def test_heal_never_touches_owner_renamed_categories(self):
        database.update_category(self.cid, name="My Custom Name")
        self_heal._heal_icon_mode_and_themed_fallbacks()
        self.assertEqual(str(database.get_category(self.cid)["name"]), "My Custom Name")


if __name__ == "__main__":
    unittest.main()
