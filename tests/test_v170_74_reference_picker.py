"""Regression coverage for v170.74 — reference-style category picker.

Covers:
  * the new default picker title ("📁 Categories / Pick a category to browse.")
  * the self-heal that refreshes ONLY the untouched old stored default
  * owner-customized titles are never overwritten
  * the premium-icon wizard end to end: a custom-emoji message saved through
    the existing Change Icon flow must surface as ``icon_custom_emoji_id`` on
    the buyer picker tile with a clean text label (reference look).

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
from config import DEFAULT_RESPONSES

ADMIN_ID = 424242
OLD_TITLE = ("🛍️ *Shop — Categories*\n━━━━━━━━━━━━━━━━━━━━\n\n"
             "Select a category to browse:")
NEW_TITLE = DEFAULT_RESPONSES["shop_categories_title"]


class _PremiumEmojiMessage:
    """A Telegram message carrying one premium custom emoji (brand logo)."""

    def __init__(self, emoji_id="5310129635848103696"):
        self.text = "⭐"
        self.caption = None
        self.text_html_urled = f'<tg-emoji emoji-id="{emoji_id}">⭐</tg-emoji>'
        self.caption_html_urled = None
        self.entities = [SimpleNamespace(type="custom_emoji",
                                         custom_emoji_id=emoji_id,
                                         offset=0, length=1)]
        self.caption_entities = []
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=len(self.replies))


class ReferencePickerTests(unittest.TestCase):
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

    def test_new_default_title_matches_reference_screenshot(self):
        self.assertEqual(NEW_TITLE, "📁 *Categories*\n\n_Pick a category to browse._")
        self.assertNotIn("Shop —", NEW_TITLE)

    def test_heal_refreshes_only_the_untouched_old_default(self):
        conn = database.get_connection()
        conn.execute("INSERT OR REPLACE INTO bot_responses(key, value) VALUES (?,?)",
                     ("shop_categories_title", OLD_TITLE))
        conn.commit(); conn.close()
        self_heal._heal_category_picker_title()
        conn = database.get_connection()
        value = conn.execute("SELECT value FROM bot_responses WHERE key='shop_categories_title'").fetchone()[0]
        conn.close()
        self.assertEqual(value, NEW_TITLE)

    def test_heal_never_overwrites_owner_customized_title(self):
        custom = "🌟 My own title"
        conn = database.get_connection()
        conn.execute("INSERT OR REPLACE INTO bot_responses(key, value) VALUES (?,?)",
                     ("shop_categories_title", custom))
        conn.commit(); conn.close()
        self_heal._heal_category_picker_title()
        conn = database.get_connection()
        value = conn.execute("SELECT value FROM bot_responses WHERE key='shop_categories_title'").fetchone()[0]
        conn.close()
        self.assertEqual(value, custom)

    def test_icon_wizard_saves_premium_emoji_and_picker_shows_brand_icon(self):
        cid = database.add_category("Chatgpt", "🤖")
        database.add_product(cid, "P", "x", 1.0, 0.0, 3)
        msg = _PremiumEmojiMessage()
        update = SimpleNamespace(effective_user=SimpleNamespace(id=ADMIN_ID), message=msg)
        context = SimpleNamespace(user_data={"edit_cat_id": cid, "edit_cat_field": "emoji"})
        done = asyncio.run(handlers_admin.edit_category_field_received(update, context))
        self.assertTrue(done)
        self.assertIn('emoji-id="5310129635848103696"',
                      str(dict(database.get_category(cid))["emoji"]))

        markup = keyboards.shop_categories_keyboard(
            database.get_products_grouped_by_category())
        tile = [r for r in markup.inline_keyboard
                if str(r[0].callback_data or "").startswith("shopcat_")][0][0]
        icon = (getattr(tile, "icon_custom_emoji_id", None)
                or (tile.api_kwargs or {}).get("icon_custom_emoji_id"))
        self.assertEqual(icon, "5310129635848103696")
        # v170.75: reference look — text pulled snugly beside the pinned icon
        # via right-side fillers only (owner-editable gap fill, default 8).
        self.assertEqual(tile.text, "Chatgpt" + "\u3164" * 8)
        self.assertFalse(tile.text.startswith("\u3164"))

    def test_normal_emoji_icon_still_works_without_premium(self):
        cid = database.add_category("Netflix", "📦")
        database.add_product(cid, "P", "x", 1.0, 0.0, 3)
        msg = _PremiumEmojiMessage()
        msg.text = "🎬"
        msg.text_html_urled = "🎬"
        msg.entities = []
        update = SimpleNamespace(effective_user=SimpleNamespace(id=ADMIN_ID), message=msg)
        context = SimpleNamespace(user_data={"edit_cat_id": cid, "edit_cat_field": "emoji"})
        self.assertTrue(asyncio.run(handlers_admin.edit_category_field_received(update, context)))
        markup = keyboards.shop_categories_keyboard(
            database.get_products_grouped_by_category())
        tile = [r for r in markup.inline_keyboard
                if str(r[0].callback_data or "").startswith("shopcat_")][0][0]
        self.assertEqual(tile.text, "🎬 Netflix")


if __name__ == "__main__":
    unittest.main()
