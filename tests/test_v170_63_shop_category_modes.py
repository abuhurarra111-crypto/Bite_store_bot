"""Focused v170.63 regressions for per-user Shop modes and category picker UX.

All tests use a temporary SQLite database and Telegram-shaped in-memory objects.
No real bot token, customer, supplier, payment, or network request is used.
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
import handlers_shop
import keyboards
import reseller_api

ADMIN_ID = 424242


class _Query:
    def __init__(self, data, user_id=7001):
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


class _Message:
    def __init__(self, text="", html="", entities=None):
        self.text = text
        self.caption = ""
        self.text_html_urled = html
        self.caption_html_urled = ""
        self.entities = entities or []
        self.caption_entities = []
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=len(self.replies))


class ShopCategoryModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        # A test changes the persisted grid setting below.  The production cache
        # is intentionally short-lived, but a new temporary DB must never read
        # that prior database's cached value.
        database.invalidate_settings_cache()
        database._WAL_SETUP_DONE = False
        database.setup_database()
        database.migrate_reseller_tables()

    def tearDown(self):
        self.tmp.cleanup()

    def _product(self, category_id, name="Product", stock=5):
        return database.add_product(
            category_id, name, "description", 4.0, 0.0, stock,
        )

    def test_unset_users_default_to_categorized_and_explicit_choice_persists(self):
        # The retired global toggle cannot change a new user's required default.
        database.set_setting("shop_categorized", "0")
        self.assertEqual(database.get_user_shop_mode(1001), "categorized")

        self.assertEqual(database.set_user_shop_mode(1001, "classic"), "classic")
        self.assertEqual(database.get_user_shop_mode(1001), "classic")
        self.assertEqual(database.get_user_shop_mode(1002), "categorized")
        # Invalid input fails safely to the default rather than storing junk.
        self.assertEqual(database.set_user_shop_mode(1003, "not-a-mode"), "categorized")
        self.assertEqual(database.get_user_shop_mode(1003), "categorized")

        conn = database.get_connection()
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(user_shop_preferences)")}
            self.assertTrue({"user_id", "shop_mode", "updated_at"}.issubset(cols))
        finally:
            conn.close()

    def test_picker_is_two_column_blue_ordered_and_premium_name_becomes_button_icon(self):
        first = database.add_category("Tools", "💻")
        second = database.add_category(
            '[[HTML]]<tg-emoji emoji-id="123456789">⭐</tg-emoji> Premium',
            "📦",
        )
        empty = database.add_category("Hidden Empty", "🫥")
        self._product(first, "A")
        self._product(second, "B")

        grouped = database.get_products_grouped_by_category()
        self.assertEqual(list(grouped), [first, second])
        self.assertNotIn(empty, grouped)  # default empty-category behavior
        markup = keyboards.shop_categories_keyboard(grouped)
        category_row = markup.inline_keyboard[0]
        self.assertEqual(len(category_row), 2)
        self.assertEqual(category_row[0].callback_data, f"shopcat_{first}")
        self.assertEqual(category_row[0].style, "primary")
        self.assertEqual(category_row[1].callback_data, f"shopcat_{second}")
        self.assertEqual(category_row[1].style, "primary")
        self.assertEqual(category_row[1].icon_custom_emoji_id, "123456789")
        # v170.75: premium-icon tiles get right-side snug fill (default 8) so
        # the centered text is pulled left beside the API-pinned icon; there
        # are never fillers on the LEFT of an icon tile.
        self.assertEqual(category_row[1].text, "Premium" + "\u3164" * 14)
        self.assertFalse(category_row[1].text.startswith("\u3164"))
        self.assertNotIn("\u3164", category_row[0].text)
        self.assertNotIn("[[HTML]]", category_row[1].text)
        self.assertNotIn("(", category_row[0].text)  # old stock/count UI is gone
        mode_callbacks = {button.callback_data for row in markup.inline_keyboard for button in row}
        self.assertIn("shopmode_categorized", mode_callbacks)
        self.assertIn("shopmode_classic", mode_callbacks)

        database.set_category_show_when_empty(empty, True)
        grouped = database.get_products_grouped_by_category()
        self.assertEqual(list(grouped), [first, second, empty])
        self.assertTrue(database.move_category(empty, "up"))
        self.assertEqual(list(database.get_products_grouped_by_category()), [first, empty, second])

    def test_category_picker_default_two_column_tiles_are_equal_width_with_safe_odd_spacer(self):
        first = database.add_category("AI", "🤖")
        second = database.add_category("Longer Category", "🧩")
        third = database.add_category("Last", "📦")
        self._product(first, "A")
        self._product(second, "B")
        self._product(third, "C")
        database.set_setting("shop_category_columns", "2")

        markup = keyboards.shop_categories_keyboard(database.get_products_grouped_by_category())
        category_rows = [row for row in markup.inline_keyboard
                         if row and str(row[0].callback_data or "").startswith("shopcat_")]
        self.assertEqual(len(category_rows), 2)
        self.assertEqual([b.callback_data for b in category_rows[0]],
                         [f"shopcat_{first}", f"shopcat_{second}"])
        # v170.72: default labels carry NO filler padding — Telegram renders
        # both buttons in a row at equal half-screen width and centers the
        # text natively, matching the owner's reference layout.
        self.assertEqual(category_rows[0][0].text, "🤖 AI")
        self.assertEqual(category_rows[0][1].text, "🧩 Longer Category")
        self.assertTrue(all("\u3164" not in b.text for b in category_rows[0]))

        # An odd final category deliberately keeps the left half of the grid;
        # the inert no-op cell prevents Telegram from stretching it full-width.
        self.assertEqual(category_rows[1][0].callback_data, f"shopcat_{third}")
        self.assertEqual(category_rows[1][1].callback_data, "noop")
        self.assertEqual(category_rows[1][0].text, "📦 Last")
        self.assertEqual(category_rows[1][1].text, "\u3164")

        # Existing buyer actions remain available after the grid, as chosen by
        # the owner: Classic and Buy Points are not removed for screenshot UX.
        callbacks = {button.callback_data for row in markup.inline_keyboard for button in row}
        self.assertTrue({"shopmode_categorized", "shopmode_classic", "buy_points", "main_menu"}
                        .issubset(callbacks))

        # The owner can still deliberately choose the legacy one-column layout.
        database.set_setting("shop_category_columns", "1")
        one_column = keyboards.shop_categories_keyboard(database.get_products_grouped_by_category())
        one_column_rows = [row for row in one_column.inline_keyboard
                           if row and str(row[0].callback_data or "").startswith("shopcat_")]
        self.assertEqual([len(row) for row in one_column_rows], [1, 1, 1])
        self.assertTrue(all("\u3164" not in row[0].text for row in one_column_rows))

    def test_category_visibility_applies_to_categorized_classic_and_reseller_catalog(self):
        first = database.add_category("Visible", "✅")
        hidden = database.add_category("Temporarily hidden", "🙈")
        first_pid = self._product(first, "Visible product")
        hidden_pid = self._product(hidden, "Hidden product")

        self.assertEqual({int(p["id"]) for p in database.get_products_filtered("all")},
                         {first_pid, hidden_pid})
        self.assertEqual(set(database.get_products_grouped_by_category()), {first, hidden})
        self.assertIn(hidden_pid, {int(p["id"]) for p in reseller_api._resellable_products()})

        database.set_category_hidden(hidden, True)
        self.assertEqual({int(p["id"]) for p in database.get_products_filtered("all")}, {first_pid})
        self.assertEqual(set(database.get_products_grouped_by_category()), {first})
        self.assertFalse(database.product_is_catalog_available(database.get_product(hidden_pid)))
        self.assertNotIn(hidden_pid, {int(p["id"]) for p in reseller_api._resellable_products()})

        database.set_category_hidden(hidden, False)
        database.set_category_active(hidden, False)
        self.assertEqual({int(p["id"]) for p in database.get_all_active_products()}, {first_pid})
        self.assertFalse(database.product_is_catalog_available(database.get_product(hidden_pid)))
        self.assertNotIn(hidden_pid, {int(p["id"]) for p in reseller_api._resellable_products()})

    def test_premium_category_create_and_edit_use_capture_user_text(self):
        premium = '[[HTML]]<tg-emoji emoji-id="987654321">🔥</tg-emoji> Deals'
        entities = [SimpleNamespace(type="custom_emoji")]
        context = SimpleNamespace(user_data={})
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN_ID),
            message=_Message(text="🔥 Deals", html='<tg-emoji emoji-id="987654321">🔥</tg-emoji> Deals',
                             entities=entities),
        )
        state = asyncio.run(handlers_admin.cat_name_received(update, context))
        # v170.76: the separate icon step is gone — name goes straight to the
        # product picker, and a premium emoji in the NAME becomes the icon.
        self.assertEqual(state, handlers_admin.CAT_PRODUCT_SELECT)
        self.assertEqual(context.user_data["cat_n"], premium)
        self.assertEqual(database.get_categories(), [],
                         "v170.65 creates the category only after picker confirmation")
        confirm = _Query("catpick_empty", user_id=ADMIN_ID)
        finish_state = asyncio.run(handlers_admin.category_product_picker_empty_callback(
            SimpleNamespace(callback_query=confirm), context))
        self.assertEqual(finish_state, handlers_admin.ConversationHandler.END)
        created = database.get_categories()[-1]
        self.assertEqual(created["name"], premium)
        self.assertEqual(created["button_style"], "primary")

        # v170.76: the legacy emoji field is no longer editable — an attempt
        # is safely refused and nothing is saved.
        context.user_data = {"edit_cat_id": int(created["id"]), "edit_cat_field": "emoji"}
        update.message = _Message(
            text="✨", html='<tg-emoji emoji-id="111222333">✨</tg-emoji>', entities=entities,
        )
        self.assertTrue(asyncio.run(handlers_admin.edit_category_field_received(update, context)))
        edited = database.get_category(created["id"])
        self.assertNotIn("111222333", str(edited["emoji"] or ""))
        button = keyboards.shop_categories_keyboard(
            database.get_products_grouped_by_category(include_empty=True)
        ).inline_keyboard[0][0]
        # The name's premium emoji has precedence as requested; either source is
        # retained in the DB and rendered through the proper Telegram field.
        self.assertEqual(button.icon_custom_emoji_id, "987654321")
        # The existing product-assignment category picker must not leak saved
        # Telegram HTML markup either.
        assignment_button = keyboards.select_category_keyboard(
            database.get_categories()).inline_keyboard[0][0]
        self.assertEqual(assignment_button.icon_custom_emoji_id, "987654321")
        self.assertNotIn("<tg-emoji", assignment_button.text)

    def test_shop_callback_renders_default_picker_then_remembers_classic_switch(self):
        first = database.add_category("Tools", "💻")
        second = database.add_category("Codes", "🎟️")
        self._product(first, "Tool A")
        self._product(second, "Code B")
        context = SimpleNamespace(user_data={})
        query = _Query("shop", user_id=7010)
        update = SimpleNamespace(callback_query=query)

        asyncio.run(handlers_shop.shop_callback(update, context))
        self.assertEqual(database.get_user_shop_mode(7010), "categorized")
        picker = query.edits[-1][1]["reply_markup"].inline_keyboard
        self.assertEqual([b.callback_data for b in picker[0]],
                         [f"shopcat_{first}", f"shopcat_{second}"])

        query.data = "shopmode_classic"
        asyncio.run(handlers_shop.shop_mode_callback(update, context))
        self.assertEqual(database.get_user_shop_mode(7010), "classic")
        classic = query.edits[-1][1]["reply_markup"].inline_keyboard
        callbacks = {b.callback_data for row in classic for b in row}
        self.assertIn("shopmode_categorized", callbacks)
        self.assertIn("shopfilter_all", callbacks)

    def test_optional_header_is_available_on_category_product_page(self):
        cid = database.add_category("Guides", "📚", description="Read this first")
        self._product(cid)
        info = database.get_products_grouped_by_category()[cid]
        self.assertEqual(info["description"], "Read this first")
        title = handlers_shop._category_page_title(info, 1, 1)
        self.assertIn("Read this first", title)
        self.assertIn("<b>", title)

    def test_stale_product_page_callbacks_clamp_after_live_catalog_changes(self):
        cid = database.add_category("Live catalog", "🔄")
        products = [database.get_product(self._product(cid, f"Item {i}")) for i in range(11)]

        category_markup, actual_page, total_pages = keyboards.shop_category_products_keyboard(
            products, cid, page=999,
        )
        self.assertEqual((actual_page, total_pages), (2, 2))
        category_labels = [button.text for row in category_markup.inline_keyboard for button in row]
        self.assertTrue(any("Item 10" in label for label in category_labels))

        classic_markup, classic_page, classic_total = keyboards.all_products_keyboard(products, page=999)
        self.assertEqual((classic_page, classic_total), (2, 2))
        classic_labels = [button.text for row in classic_markup.inline_keyboard for button in row]
        self.assertTrue(any("Item 10" in label for label in classic_labels))


if __name__ == "__main__":
    unittest.main()
