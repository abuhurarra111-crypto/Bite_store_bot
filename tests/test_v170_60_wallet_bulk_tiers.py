"""Offline regressions for v170.60 wallet checkout tier pricing.

The wallet/points route must use the exact same quantity-tier unit price as
Binance, EasyPaisa, JazzCash, USDT and Bybit checkout routes.
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

import database
import handlers_order

CUSTOMER_ID = 880001


class _FakeMessage:
    async def reply_text(self, *_args, **_kwargs):
        return SimpleNamespace(message_id=1)


class _FakeQuery:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(
            id=CUSTOMER_ID, username="wallet_customer", first_name="Wallet Customer",
        )
        self.message = _FakeMessage()
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return SimpleNamespace(message_id=len(self.edits))


class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, *args, **kwargs):
        self.sent.append((chat_id, text, args, kwargs))
        return SimpleNamespace(message_id=len(self.sent))


class WalletBulkTierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        for key in database._DEPLOYMENT_ID_ENV_KEYS + database._PLATFORM_ENV_KEYS:
            os.environ.pop(key, None)
        database.setup_database()
        category = database.add_category("Wallet tier regression")
        self.pid = database.add_product(
            category, "Gemini 18 Month Link No Warranty", "Tier test", 0.67,
            0.0, 0, delivery_text="Reusable static delivery",
        )
        database.set_product_tier(self.pid, 10, 0.62)
        database.set_product_tier(self.pid, 30, 0.57)

    def tearDown(self):
        self.tmp.cleanup()

    def _context(self):
        return SimpleNamespace(bot=_FakeBot(), user_data={})

    def test_insufficient_wallet_message_uses_10_qty_tier_not_base_price(self):
        database.add_points(CUSTOMER_ID, 2.1, description="test balance")
        query = _FakeQuery(f"pay_pts_{self.pid}_10")

        asyncio.run(handlers_order.pay_pts_callback(
            SimpleNamespace(callback_query=query), self._context(),
        ))

        self.assertTrue(query.edits)
        text = query.edits[-1][0]
        # $0.62 × 10 × 10 points/USD = 62 points. Old bug showed 67.
        self.assertIn("Required: *62 💎*", text)
        self.assertIn("Short by: *59.9 💎*", text)
        self.assertNotIn("Required: *67 💎*", text)
        self.assertAlmostEqual(database.get_combined_points(CUSTOMER_ID), 2.1)

        conn = database.get_connection()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)
        finally:
            conn.close()

    def test_wallet_debits_tier_total_and_saves_tier_total_on_order(self):
        database.add_points(CUSTOMER_ID, 70, description="test balance")
        query = _FakeQuery(f"pay_pts_{self.pid}_10")
        context = self._context()

        asyncio.run(handlers_order.pay_pts_callback(
            SimpleNamespace(callback_query=query), context,
        ))

        # 70 - (10 × $0.62 × 10 points/USD) = 8 points remaining.
        self.assertAlmostEqual(database.get_combined_points(CUSTOMER_ID), 8.0)
        conn = database.get_connection()
        try:
            order = dict(conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 1").fetchone())
        finally:
            conn.close()
        self.assertEqual(order["status"], "delivered")
        self.assertAlmostEqual(float(order["price"]), 6.2)
        self.assertAlmostEqual(float(order["binance_amount"]), 62.0)
        self.assertTrue(any("Deducted: `-62`" in str(text)
                            for text, _kwargs in query.edits))


if __name__ == "__main__":
    unittest.main(verbosity=2)
