"""Offline regressions for v170.59 static Freebies and all-tier broadcasts.

Run with:
    python -m unittest tests/test_v170_59_static_freebies_and_bulk_broadcast.py -v
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

# Test-only runtime configuration, before application imports.
os.environ["BOT_TOKEN"] = "test-token-not-real"
os.environ["ADMIN_ID"] = "424242"
_IMPORT_TEMP = tempfile.TemporaryDirectory()
os.environ["DB_PATH"] = str(Path(_IMPORT_TEMP.name) / "import.db")
for _key in (
    "RAILWAY_DEPLOYMENT_ID", "RAILWAY_GIT_COMMIT_SHA", "RENDER_DEPLOY_ID",
    "RENDER_GIT_COMMIT", "SOURCE_VERSION", "RAILWAY_ENVIRONMENT",
    "RAILWAY_PROJECT_ID", "RENDER", "RENDER_SERVICE_ID", "RENDER_EXTERNAL_URL",
):
    os.environ.pop(_key, None)

import customization
import database
import fake_engagement
import handlers_admin
import handlers_freebies

ADMIN_ID = 424242
CUSTOMER_ID = 777001


class _FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, *args, **kwargs):
        self.replies.append((text, args, kwargs))
        return SimpleNamespace(message_id=len(self.replies))


class _FakeQuery:
    def __init__(self, data, user_id=ADMIN_ID):
        self.data = data
        self.from_user = SimpleNamespace(
            id=user_id,
            username="test_customer" if user_id != ADMIN_ID else "owner",
            first_name="Test Customer" if user_id != ADMIN_ID else "Owner",
        )
        self.message = _FakeMessage()
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return SimpleNamespace(message_id=1)


class _FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, *args, **kwargs):
        self.calls.append((chat_id, text, args, kwargs))
        return SimpleNamespace(message_id=len(self.calls))


class StaticFreebieAndBulkBroadcastTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        for key in database._DEPLOYMENT_ID_ENV_KEYS + database._PLATFORM_ENV_KEYS:
            os.environ.pop(key, None)
        database.setup_database()
        self.category_id = database.add_category("Regression")

    def tearDown(self):
        self.tmp.cleanup()

    def _add_product(self, *, name="Gemini 18 Month Link", price=0.67, stock=5,
                     delivery_text=""):
        return database.add_product(
            self.category_id, name, "Regression product", price, 0.0, stock,
            delivery_text=delivery_text,
        )

    def test_zero_stock_static_delivery_is_unlimited_and_never_decrements_stock(self):
        pid = self._add_product(stock=0, delivery_text="Reusable static link: https://example.test")
        self.assertTrue(database.has_static_text_delivery(database.get_product(pid)))

        result = database.build_delivery_detailed(pid, order_id=991, qty=3, buyer_uid=CUSTOMER_ID)

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "static")
        self.assertEqual(result["requested"], 3)
        self.assertEqual(result["delivered"], 3)
        self.assertIn("Bulk Order × 3", result["text"])
        self.assertIn("Reusable static link", result["text"])
        self.assertEqual(int(dict(database.get_product(pid))["stock"]), 0)

    def test_static_zero_stock_freebie_claims_once_and_keeps_claim_limit(self):
        pid = self._add_product(
            name="Static Freebie", stock=0,
            delivery_text="Unlimited freebie instructions",
        )
        self.assertTrue(database.set_freebie_config(
            pid, enabled=1, claim_limit=1, reclaim_refs=0, max_claims=0,
        ))
        bot = _FakeBot()
        context = SimpleNamespace(bot=bot, user_data={})

        first_query = _FakeQuery(f"freebie_do_{pid}", CUSTOMER_ID)
        asyncio.run(handlers_freebies.freebie_do_callback(
            SimpleNamespace(callback_query=first_query), context,
        ))

        orders = []
        conn = database.get_connection()
        try:
            orders = [dict(row) for row in conn.execute("SELECT * FROM orders ORDER BY id")]
        finally:
            conn.close()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["status"], "delivered")
        self.assertEqual(database.freebie_claims_count(CUSTOMER_ID, pid), 1)
        self.assertEqual(int(dict(database.get_product(pid))["stock"]), 0)
        self.assertFalse(any("Out of stock" in str(text) for text, _ in first_query.edits))

        # The stock bypass did not bypass the configured per-user claim limit.
        second_query = _FakeQuery(f"freebie_do_{pid}", CUSTOMER_ID)
        asyncio.run(handlers_freebies.freebie_do_callback(
            SimpleNamespace(callback_query=second_query), context,
        ))
        self.assertTrue(any("Claim limit reached" in str(text)
                            for text, _ in second_query.edits))
        self.assertEqual(database.freebie_claims_count(CUSTOMER_ID, pid), 1)

    def test_static_zero_stock_freebie_still_honors_total_max_claims(self):
        pid = self._add_product(
            name="Static Limited Freebie", stock=0,
            delivery_text="Reusable but freebie-limited content",
        )
        database.set_freebie_config(pid, enabled=1, claim_limit=0, reclaim_refs=0, max_claims=1)
        bot = _FakeBot()
        context = SimpleNamespace(bot=bot, user_data={})

        first_query = _FakeQuery(f"freebie_do_{pid}", CUSTOMER_ID)
        asyncio.run(handlers_freebies.freebie_do_callback(
            SimpleNamespace(callback_query=first_query), context,
        ))
        self.assertEqual(database.freebie_claims_count(CUSTOMER_ID, pid), 1)
        self.assertEqual(database.get_freebie_config(pid)["enabled"], 0)

        second_query = _FakeQuery(f"freebie_do_{pid}", CUSTOMER_ID + 1)
        asyncio.run(handlers_freebies.freebie_do_callback(
            SimpleNamespace(callback_query=second_query), context,
        ))
        self.assertTrue(any("not available" in str(text).lower()
                            for text, _ in second_query.edits))
        self.assertEqual(database.freebie_claims_count(CUSTOMER_ID + 1, pid), 0)

    def test_all_tiers_render_in_order_and_legacy_custom_template_gets_safe_append(self):
        pid = self._add_product(price=0.67, stock=50)
        self.assertTrue(database.set_product_tier(pid, 30, 0.57))
        self.assertTrue(database.set_product_tier(pid, 10, 0.62))

        message = handlers_admin.build_bulkdeal_broadcast_message(pid, "a***l")
        self.assertIn("10+ qty", message)
        self.assertIn("$0.62", message)
        self.assertIn("30+ qty", message)
        self.assertIn("$0.57", message)
        self.assertLess(message.index("10+ qty"), message.index("30+ qty"))
        self.assertNotIn("$62 each", message)

        # Existing custom text that predates {tiers} cannot hide the new tiers.
        database.set_setting("tpl_bc_bulkdeal", "Legacy: {product} / {qty}+ / ${price}")
        legacy_message = handlers_admin.build_bulkdeal_broadcast_message(pid, "a***l")
        self.assertIn("Legacy:", legacy_message)
        self.assertIn("Configured bulk tiers", legacy_message)
        self.assertIn("10+ qty", legacy_message)
        self.assertIn("30+ qty", legacy_message)
        database.set_setting("tpl_bc_bulkdeal", "")

    def test_save_and_broadcast_callback_sends_all_configured_tiers(self):
        pid = self._add_product(price=0.67, stock=50)
        database.set_product_tier(pid, 10, 0.62)
        database.set_product_tier(pid, 30, 0.57)
        sent = []
        original = fake_engagement.broadcast_store_message

        async def _capture(_bot, text, **kwargs):
            sent.append((text, kwargs))
            return 1

        fake_engagement.broadcast_store_message = _capture
        try:
            query = _FakeQuery(f"bdisc_broadcast_{pid}")
            asyncio.run(handlers_admin.bdisc_broadcast_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(bot=_FakeBot(), user_data={}),
            ))
        finally:
            fake_engagement.broadcast_store_message = original

        self.assertEqual(len(sent), 1)
        text, kwargs = sent[0]
        self.assertEqual(kwargs["pid"], pid)
        self.assertEqual(kwargs["tpl_id"], "bc_bulkdeal")
        self.assertIn("10+ qty", text)
        self.assertIn("$0.62", text)
        self.assertIn("30+ qty", text)
        self.assertIn("$0.57", text)

    def test_bulk_template_and_per_tier_line_are_in_edit_templates(self):
        entries = {entry["id"]: entry for entry in customization.TEMPLATES}
        self.assertIn("bc_bulkdeal", entries)
        self.assertIn("bc_bulkdeal_tier_line", entries)
        self.assertIn("{tiers}", entries["bc_bulkdeal"]["vars"])
        self.assertIn("{saving}", entries["bc_bulkdeal_tier_line"]["vars"])
        self.assertEqual(entries["bc_bulkdeal"]["section"], "📢 Fake Broadcast")
        self.assertTrue(all("{tiers}" in variant
                            for variant in customization.TEMPLATE_VARIANTS["bc_bulkdeal"]))

    def test_bulk_price_parser_preserves_dot_and_comma_decimals(self):
        self.assertAlmostEqual(handlers_admin.parse_bulk_discount_unit_price("0.62"), 0.62)
        self.assertAlmostEqual(handlers_admin.parse_bulk_discount_unit_price("0,62"), 0.62)
        self.assertAlmostEqual(handlers_admin.parse_bulk_discount_unit_price("$1.000,50"), 1000.50)
        self.assertAlmostEqual(handlers_admin.parse_bulk_discount_unit_price("1,000.50"), 1000.50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
