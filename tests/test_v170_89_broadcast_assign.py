"""v170.89 tests:
1. Assign pool excludes soft-deleted (is_active=0) zombie products.
2. Global broadcast classifies blocked users separately + retries flood.
3. BroadcastProgress carries a working 🛑 Stop button (registry + cancel).
"""
import asyncio
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class V17089BroadcastAssignTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.environ["DB_PATH"] = self._tmp.name
        import importlib
        import database
        self._wal = getattr(database, "_WAL_SETUP_DONE", None)
        importlib.reload(database)
        database.setup_database()
        database.invalidate_settings_cache()
        self.database = database

    def tearDown(self):
        import database
        if self._wal is not None:
            database._WAL_SETUP_DONE = self._wal
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def _product(self, name, cat_id=None, stock=5, active=1):
        conn = self.database.get_connection()
        try:
            cur = conn.execute(
                "INSERT INTO products (name, price, stock, category_id, is_active)"
                " VALUES (?, 100, ?, ?, ?)",
                (name, stock, cat_id, active),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def _user(self, uid):
        conn = self.database.get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                (uid, f"u{uid}"),
            )
            conn.commit()
        finally:
            conn.close()

    # ── #1 soft-deleted zombies ───────────────────────────────────────
    def test_pool_excludes_soft_deleted_products(self):
        db = self.database
        cat = db.add_category("ChatGPT", "🤖")
        real = self._product("ChatGPT Plus 30D", cat_id=cat)
        zombie = self._product("ChatGPT Plus 30D", stock=0, active=1)
        db.delete_product(zombie)  # soft delete → is_active=0
        loose = self._product("Loose")
        pool = {int(p["id"]) for p in db.get_unassigned_in_stock_products()}
        self.assertIn(loose, pool)
        self.assertNotIn(zombie, pool, "soft-deleted product must not appear")
        self.assertNotIn(real, pool)
        # atomic create path must also refuse the zombie
        res = db.create_category_with_unassigned_in_stock_products(
            "New", product_ids=[zombie])
        self.assertFalse(res["created"])

    # ── #2 blocked classification + flood retry ──────────────────────
    def test_broadcast_classifies_blocked_and_retries_flood(self):
        from telegram.error import Forbidden, RetryAfter
        import handlers_admin
        db = self.database
        for uid in (101, 102, 103, 104):
            self._user(uid)

        class MockBot:
            def __init__(self):
                self.sent, self.edits, self.flooded = [], [], set()

            async def send_message(self, chat_id, text=None, **k):
                cid = int(chat_id)
                if cid == 101:
                    raise Forbidden("bot was blocked by the user")
                if cid == 102 and cid not in self.flooded:
                    self.flooded.add(cid)
                    raise RetryAfter(0)
                self.sent.append(cid)
                return SimpleNamespace(message_id=1,
                                       chat=SimpleNamespace(id=cid))

            async def edit_message_text(self, chat_id=None, message_id=None,
                                        text=None, **k):
                self.edits.append(text)
                return True

        bot = MockBot()
        payload = {"type": "text", "text": "hi", "media_type": None}
        s, f, blocked = asyncio.run(
            handlers_admin._broadcast_payload_to_all_users(
                bot, payload, notify_uid=999, title="Global Broadcast"))
        self.assertEqual(blocked, 1, "Forbidden must count as blocked")
        self.assertEqual(f, 0, "flood-retried send must not count as failed")
        self.assertEqual(s, 3)
        self.assertIn(102, bot.sent, "RetryAfter user must get the message")

    # ── #3 stop button ────────────────────────────────────────────────
    def test_stop_button_halts_broadcast(self):
        import handlers_admin
        from utils import BroadcastProgress
        for uid in range(201, 261):
            self._user(uid)

        class SlowBot:
            def __init__(self):
                self.sent, self.edits, self.markup = [], [], None

            async def send_message(self, chat_id, text=None,
                                   reply_markup=None, **k):
                if reply_markup is not None and self.markup is None:
                    self.markup = reply_markup
                self.sent.append(int(chat_id))
                return SimpleNamespace(message_id=1,
                                       chat=SimpleNamespace(id=chat_id))

            async def edit_message_text(self, chat_id=None, message_id=None,
                                        text=None, **k):
                self.edits.append(text)
                return True

        async def run():
            bot = SlowBot()
            payload = {"type": "text", "text": "hi", "media_type": None}
            task = asyncio.create_task(
                handlers_admin._broadcast_payload_to_all_users(
                    bot, payload, notify_uid=999, title="Global Broadcast"))
            await asyncio.sleep(0.3)
            self.assertIsNotNone(bot.markup, "progress must carry the button")
            btn = bot.markup.inline_keyboard[0][0]
            self.assertTrue(str(btn.callback_data).startswith("bcstop_"))
            BroadcastProgress.request_stop(
                str(btn.callback_data).replace("bcstop_", "", 1))
            s, f, blocked = await task
            total = 60 + 1  # +1 = notify uid row not present; sends = users
            self.assertLess(s + f + blocked, total,
                            "broadcast must stop before finishing all users")
            self.assertTrue(any("Stopped" in (e or "") for e in bot.edits))
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
