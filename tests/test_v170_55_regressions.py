"""Offline regression tests for v170.55.

No network calls and no production DB are used. Run with:
    python -m unittest tests/test_v170_55_regressions.py -v
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

# Must be set before config/handler imports. These are deliberately fake values.
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
import handlers_admin

ADMIN_ID = 424242


class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=len(self.sent))


class _FakeQuery:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=ADMIN_ID)
        self.answers = []
        self.edits = []
        self.message = _FakeMessage("")

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class _FakeMessage:
    def __init__(self, text, entities=None):
        self.text = text
        self.entities = entities or []
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=len(self.replies))


class _FakeContext:
    def __init__(self):
        self.bot = _FakeBot()
        self.user_data = {}


class V17055RegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "shop.db")
        database.DB_PATH = self.db_path
        database._WAL_SETUP_DONE = False
        # Make every individual test local-only unless it deliberately sets a
        # hosted deployment identity itself.
        for key in database._DEPLOYMENT_ID_ENV_KEYS + database._PLATFORM_ENV_KEYS:
            os.environ.pop(key, None)
        database.setup_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _row_value(self, query, params=()):
        conn = database.get_connection()
        try:
            row = conn.execute(query, params).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def test_new_deployment_resets_but_same_deployment_preserves_manual_restore(self):
        # Give this database a hosted deployment identity and create a sentinel
        # representing a manual Ready-DB restore.
        os.environ["RAILWAY_ENVIRONMENT"] = "production"
        os.environ["RAILWAY_DEPLOYMENT_ID"] = "test-deploy-A"
        database.setup_database()
        conn = database.get_connection()
        conn.execute("INSERT OR REPLACE INTO bot_settings(key,value) VALUES('manual_restore_sentinel','kept')")
        conn.commit()
        conn.close()

        # A process restart under the same deployed release must not wipe it.
        database.setup_database()
        self.assertEqual(
            self._row_value("SELECT value FROM bot_settings WHERE key='manual_restore_sentinel'"),
            "kept",
        )

        # A new deployment identity must boot a fresh DB.
        os.environ["RAILWAY_DEPLOYMENT_ID"] = "test-deploy-B"
        database.setup_database()
        self.assertIsNone(
            self._row_value("SELECT value FROM bot_settings WHERE key='manual_restore_sentinel'")
        )
        self.assertEqual(self._row_value("SELECT COUNT(*) FROM users"), 0)

    def test_order_fk_repair_preserves_history_and_new_points_orders_use_null(self):
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO categories(name) VALUES ('Test')")
        c.execute("INSERT INTO products(category_id,name,price) VALUES (1,'Live product',1)")
        c.execute("""INSERT INTO orders(user_id,product_id,product_name,price,status,order_type)
                     VALUES (1,1,'Live product',1,'delivered','product')""")
        c.execute("""INSERT INTO orders(user_id,product_id,product_name,price,status,order_type)
                     VALUES (2,0,'100 Points',3,'delivered','points')""")
        c.execute("""INSERT INTO orders(user_id,product_id,product_name,price,status,order_type)
                     VALUES (3,999,'Deleted product snapshot',4,'delivered','product')""")
        conn.commit()
        conn.close()

        self.assertEqual(database.repair_orphan_order_product_references(), 2)
        conn = database.get_connection()
        try:
            repaired = conn.execute(
                "SELECT product_id,product_name,price,status FROM orders WHERE user_id IN (2,3) ORDER BY user_id"
            ).fetchall()
            self.assertEqual([row[0] for row in repaired], [None, None])
            self.assertEqual([row[1] for row in repaired], ["100 Points", "Deleted product snapshot"])
            self.assertEqual([row[2] for row in repaired], [3.0, 4.0])
            self.assertEqual([row[3] for row in repaired], ["delivered", "delivered"])
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            conn.close()

        order_id = database.create_order(4, "Test", 0, "50 Points", 5, otype="points")
        self.assertIsNone(self._row_value("SELECT product_id FROM orders WHERE id=?", (order_id,)))
        conn = database.get_connection()
        try:
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            conn.close()

    def test_color_save_sends_fresh_reply_markup_with_style_and_custom_emoji(self):
        database.set_setting("persist_emoji_home", "1234567890123456789")
        context = _FakeContext()
        query = _FakeQuery("persist_setcol_home_green")
        update = SimpleNamespace(callback_query=query)

        asyncio.run(handlers_admin.persist_setcol_callback(update, context))

        self.assertEqual(len(context.bot.sent), 1)
        sent = context.bot.sent[0]
        self.assertEqual(sent["chat_id"], ADMIN_ID)
        self.assertTrue(sent["disable_notification"])
        payload = sent["reply_markup"].to_dict()
        home = next(button for row in payload["keyboard"] for button in row if button["text"] == "🏠 Menu")
        self.assertEqual(home["style"], "success")
        self.assertEqual(home["icon_custom_emoji_id"], "1234567890123456789")
        self.assertTrue(query.edits, "settings panel should still re-render after save")

    def test_rename_reply_attaches_fresh_persistent_markup(self):
        database.set_setting("persist_color_howto", "blue")
        context = _FakeContext()
        context.user_data["persist_ren_pid"] = "howto"
        message = _FakeMessage("Guide")
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=ADMIN_ID),
        )

        self.assertTrue(asyncio.run(handlers_admin.persist_rename_received(update, context)))
        self.assertEqual(len(message.replies), 1)
        _, kwargs = message.replies[0]
        self.assertIn("reply_markup", kwargs)
        payload = kwargs["reply_markup"].to_dict()
        howto = next(button for row in payload["keyboard"] for button in row if button["text"] == "Guide")
        self.assertEqual(howto["style"], "primary")  # explicitly configured blue


if __name__ == "__main__":
    unittest.main(verbosity=2)
