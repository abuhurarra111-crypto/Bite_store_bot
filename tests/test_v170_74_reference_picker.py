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

    def test_premium_emoji_in_name_becomes_brand_icon(self):
        cid = database.add_category("Chatgpt", "")
        database.add_product(cid, "P", "x", 1.0, 0.0, 3)
        # Rename with a premium custom emoji INSIDE the name (v170.76 flow).
        msg = _PremiumEmojiMessage()
        msg.text = "⭐ Chatgpt"
        msg.text_html_urled = ('<tg-emoji emoji-id="5310129635848103696">⭐</tg-emoji>'
                               " Chatgpt")
        update = SimpleNamespace(effective_user=SimpleNamespace(id=ADMIN_ID), message=msg)
        context = SimpleNamespace(user_data={"edit_cat_id": cid, "edit_cat_field": "name"})
        done = asyncio.run(handlers_admin.edit_category_field_received(update, context))
        self.assertTrue(done)
        self.assertIn('emoji-id="5310129635848103696"',
                      str(dict(database.get_category(cid))["name"]))

        markup = keyboards.shop_categories_keyboard(
            database.get_products_grouped_by_category())
        tile = [r for r in markup.inline_keyboard
                if str(r[0].callback_data or "").startswith("shopcat_")][0][0]
        icon = (getattr(tile, "icon_custom_emoji_id", None)
                or (tile.api_kwargs or {}).get("icon_custom_emoji_id"))
        self.assertEqual(icon, "5310129635848103696")
        # v170.77 auto-snug: "Chatgpt" width 7 → ceil((34-7)/2) = 14 fillers.
        self.assertEqual(tile.text, "Chatgpt" + "\u3164" * 14)
        self.assertFalse(tile.text.startswith("\u3164"))

    def test_legacy_emoji_field_never_becomes_api_icon_anymore(self):
        # v170.76: a premium emoji stored in the OLD icon field renders as its
        # plain fallback inline — the API icon comes only from the name.
        cid = database.add_category(
            "Redeem links",
            '[[HTML]]<tg-emoji emoji-id="5310129635848103696">🔗</tg-emoji>')
        database.add_product(cid, "P", "x", 1.0, 0.0, 3)
        markup = keyboards.shop_categories_keyboard(
            database.get_products_grouped_by_category())
        tile = [r for r in markup.inline_keyboard
                if str(r[0].callback_data or "").startswith("shopcat_")][0][0]
        icon = (getattr(tile, "icon_custom_emoji_id", None)
                or (tile.api_kwargs or {}).get("icon_custom_emoji_id"))
        self.assertIsNone(icon)
        self.assertEqual(tile.text, "🔗 Redeem links")

    def test_icon_edit_callback_is_rejected_with_guidance(self):
        cid = database.add_category("Netflix", "🎬")

        class _Q:
            data = f"editcat_emoji_{cid}"
            from_user = SimpleNamespace(id=ADMIN_ID)
            answers = []
            async def answer(self, *a, **k): _Q.answers.append((a, k))
            async def edit_message_text(self, *a, **k): return None
            async def edit_message_caption(self, *a, **k): return None

        state = asyncio.run(handlers_admin.edit_category_field_callback(
            SimpleNamespace(callback_query=_Q()), SimpleNamespace(user_data={})))
        from telegram.ext import ConversationHandler
        self.assertEqual(state, ConversationHandler.END)
        self.assertTrue(any("NAME" in str(a) for a, _ in _Q.answers))

    def test_detail_panel_no_longer_offers_change_icon(self):
        cid = database.add_category("Tools", "💻")

        class _Q:
            data = f"viewcat_{cid}"
            from_user = SimpleNamespace(id=ADMIN_ID)
            edits = []
            async def answer(self, *a, **k): pass
            async def edit_message_text(self, text, **k):
                _Q.edits.append((text, k)); return None
            async def edit_message_caption(self, caption, **k):
                _Q.edits.append((caption, k)); return None

        asyncio.run(handlers_admin._render_category_detail(_Q(), cid))
        _text, kwargs = _Q.edits[-1]
        callbacks = {b.callback_data for row in kwargs["reply_markup"].inline_keyboard
                     for b in row}
        self.assertNotIn(f"editcat_emoji_{cid}", callbacks)
        self.assertIn(f"editcat_name_{cid}", callbacks)

    def test_normal_emoji_in_name_still_works_without_premium(self):
        cid = database.add_category("🎬 Netflix", "")
        database.add_product(cid, "P", "x", 1.0, 0.0, 3)
        markup = keyboards.shop_categories_keyboard(
            database.get_products_grouped_by_category())
        tile = [r for r in markup.inline_keyboard
                if str(r[0].callback_data or "").startswith("shopcat_")][0][0]
        self.assertEqual(tile.text, "🎬 Netflix")


if __name__ == "__main__":
    unittest.main()
