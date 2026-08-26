"""End-to-end offline state-flow regression for Admin → Refund by User ID."""

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

ADMIN_ID = 424242
TARGET_ID = 771001


class _Message:
    def __init__(self, text=""):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=len(self.replies))


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=ADMIN_ID, first_name="Owner")
        self.message = _Message()
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return SimpleNamespace(message_id=len(self.edits))

    async def edit_message_caption(self, *args, **kwargs):
        return None


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, *args, **kwargs):
        self.sent.append((chat_id, text, args, kwargs))
        return SimpleNamespace(message_id=len(self.sent))


class RefundByUserIdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        database.setup_database()
        database.save_user(TARGET_ID, "refund_target", "Refund Target")
        # handlers_admin imports the constant at module load, so make the test
        # robust if another test imported config before this test's env setup.
        handlers_admin.ADMIN_ID = ADMIN_ID
        self.context = SimpleNamespace(bot=_Bot(), user_data={})

    def tearDown(self):
        self.tmp.cleanup()

    def _text_update(self, text):
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN_ID),
            message=_Message(text),
        )

    def test_callback_then_id_amount_reason_confirm_credits_wallet(self):
        # The exact callback that formerly matched the generic adm_refund_
        # route must enter this specialized flow without a generic error.
        entry_q = _Query("adm_refund_uid")
        asyncio.run(handlers_admin.adm_refund_uid_callback(
            SimpleNamespace(callback_query=entry_q), self.context,
        ))
        self.assertEqual(self.context.user_data.get("ruid_step"), "id")
        self.assertTrue(entry_q.edits)
        self.assertIn("Refund by User ID", entry_q.edits[-1][0])

        id_update = self._text_update(str(TARGET_ID))
        self.assertTrue(asyncio.run(handlers_admin.adm_refund_uid_received(id_update, self.context)))
        self.assertEqual(self.context.user_data.get("ruid_step"), "amt")
        self.assertEqual(self.context.user_data.get("ruid_user"), TARGET_ID)
        self.assertIn("User mil gaya", id_update.message.replies[-1][0])

        amount_update = self._text_update("2.5")
        self.assertTrue(asyncio.run(handlers_admin.adm_refund_uid_amt_received(amount_update, self.context)))
        self.assertEqual(self.context.user_data.get("ruid_step"), "reason")
        self.assertAlmostEqual(self.context.user_data.get("ruid_amt"), 2.5)

        reason_update = self._text_update("Delivery issue")
        self.assertTrue(asyncio.run(handlers_admin.adm_refund_uid_reason_received(reason_update, self.context)))
        self.assertEqual(self.context.user_data.get("ruid_step"), "confirm")
        self.assertIn("Refund Confirm", reason_update.message.replies[-1][0])

        confirm_q = _Query("ruid_confirm")
        asyncio.run(handlers_admin.adm_refund_uid_confirm_callback(
            SimpleNamespace(callback_query=confirm_q), self.context,
        ))
        expected = handlers_admin.points_from_usd(2.5)
        self.assertAlmostEqual(database.get_user_points(TARGET_ID), expected)
        self.assertNotIn("ruid_step", self.context.user_data)
        self.assertTrue(confirm_q.edits)
        self.assertIn("Refund Done", confirm_q.edits[-1][0])

    def test_direct_user_button_skips_id_step(self):
        direct_q = _Query(f"adm_refund_uid_{TARGET_ID}")
        asyncio.run(handlers_admin.adm_refund_uid_callback(
            SimpleNamespace(callback_query=direct_q), self.context,
        ))
        self.assertEqual(self.context.user_data.get("ruid_step"), "amt")
        self.assertEqual(self.context.user_data.get("ruid_user"), TARGET_ID)
        self.assertIn("Refund amount", direct_q.edits[-1][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
