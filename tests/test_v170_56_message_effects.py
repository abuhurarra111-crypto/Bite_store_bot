"""Offline regression tests for v170.56 message-effect event expansion.

Run with:
    python -m unittest tests/test_v170_56_message_effects.py -v
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

# Deliberately fake test-only runtime values, set before application imports.
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
import message_effects

ADMIN_ID = 424242
PARTY = "5046509860389126442"
FIRE = "5104841245755180586"
LIKE = "5107584321108051014"


class _EffectCapturingBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, *args, **kwargs):
        # Intentionally do not emulate bot.py's production wrapper: this proves
        # send_event_message itself is safe and usable by a lightweight Bot.
        self.calls.append((chat_id, text, args, kwargs))
        return SimpleNamespace(message_id=len(self.calls))


class _FakeMessage:
    async def reply_text(self, *_args, **_kwargs):
        return SimpleNamespace(message_id=1)


class _FakeQuery:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=ADMIN_ID)
        self.message = _FakeMessage()
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class MessageEffectEventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        for key in database._DEPLOYMENT_ID_ENV_KEYS + database._PLATFORM_ENV_KEYS:
            os.environ.pop(key, None)
        database.setup_database()

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_suggested_events_are_registered_and_recommended_pack_maps_them(self):
        expected = {
            "delivered", "points_deposit_confirmed", "freebie_claimed",
            "referral_reward", "tier_upgrade", "support_resolved",
            "warranty_approved", "replacement_approved", "restock_alert",
            "refund_completed",
        }
        registered = {event for event, _label in message_effects.FX_EVENTS}
        self.assertTrue(expected.issubset(registered))
        message_effects.set_global_effect(FIRE)
        message_effects.set_command_effect("start", LIKE)
        self.assertEqual(
            message_effects.apply_recommended_event_effects(),
            len(message_effects.RECOMMENDED_EVENT_EFFECTS),
        )
        self.assertEqual(message_effects.global_effect(), FIRE)
        self.assertEqual(message_effects.command_effect("start"), LIKE)
        for event, effect_id in message_effects.RECOMMENDED_EVENT_EFFECTS.items():
            self.assertEqual(message_effects.event_effect(event), effect_id)
        self.assertEqual(message_effects.event_label("freebie_claimed"), "🎁 Freebie Claimed")

    def test_event_command_global_precedence_and_nested_context_cleanup(self):
        message_effects.set_global_effect(FIRE)
        message_effects.set_command_effect("start", LIKE)
        message_effects.set_current_command("start")
        message_effects.set_event_effect("tier_upgrade", PARTY)
        message_effects.set_event_effect("refund_completed", LIKE)
        self.assertEqual(message_effects.resolve_effect(), LIKE)  # command > global

        with message_effects.event_scope("tier_upgrade"):
            self.assertEqual(message_effects.resolve_effect(), PARTY)  # event > command
            with message_effects.event_scope("refund_completed"):
                self.assertEqual(message_effects.resolve_effect(), LIKE)
            self.assertEqual(message_effects.resolve_effect(), PARTY)
        self.assertEqual(message_effects.resolve_effect(), LIKE)
        self.assertEqual(message_effects.CURRENT_EVENT.get(), "")
        message_effects.set_current_command("")
        self.assertEqual(message_effects.resolve_effect(), FIRE)

    def test_event_send_attaches_to_private_chats_only_and_does_not_leak(self):
        message_effects.set_event_effect("freebie_claimed", PARTY)
        bot = _EffectCapturingBot()

        asyncio.run(message_effects.send_event_message(bot, "freebie_claimed", 777, "success"))
        self.assertEqual(bot.calls[0][3]["message_effect_id"], PARTY)
        self.assertEqual(message_effects.CURRENT_EVENT.get(), "")

        asyncio.run(message_effects.send_event_message(bot, "freebie_claimed", -100777, "group"))
        self.assertNotIn("message_effect_id", bot.calls[1][3])

    def test_admin_panel_exposes_all_events_and_one_tap_recommended_pack(self):
        query = _FakeQuery("fxpanel")
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={})
        asyncio.run(handlers_admin.admin_effects_callback(update, context))

        self.assertTrue(query.edits)
        markup = query.edits[-1][1]["reply_markup"].to_dict()
        callbacks = [button["callback_data"] for row in markup["inline_keyboard"] for button in row]
        self.assertIn("fxpack", callbacks)
        for event, _label in message_effects.FX_EVENTS:
            self.assertIn(f"fxee_{event}", callbacks)

        pack_query = _FakeQuery("fxpack")
        asyncio.run(handlers_admin.admin_effects_recommended_callback(
            SimpleNamespace(callback_query=pack_query), SimpleNamespace(user_data={})
        ))
        self.assertEqual(message_effects.event_effect("delivered"), PARTY)
        self.assertEqual(message_effects.event_effect("restock_alert"), FIRE)
        self.assertEqual(message_effects.event_effect("refund_completed"), LIKE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
