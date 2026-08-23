"""Offline regression tests for v170.57 persistent-menu message effect.

Run with:
    python -m unittest tests/test_v170_57_persistent_menu_effect.py -v
"""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Test-only configuration must exist before importing application modules.
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
import handlers_start
import message_effects

PARTY = "5046509860389126442"


class _PersistentMenuMessage:
    """Fake incoming tap whose reply observes the production event context."""
    def __init__(self, chat_id=777):
        self.chat_id = chat_id
        self.calls = []

    async def reply_text(self, text, **kwargs):
        # PTB's Bot.send_message wrapper calls attach_effect before transmission.
        # Mirror that final handoff so the test verifies its actual payload too.
        context_event = message_effects.CURRENT_EVENT.get()
        message_effects.attach_effect(kwargs, self.chat_id)
        self.calls.append((text, kwargs, context_event))
        return SimpleNamespace(message_id=1)


class PersistentMenuEffectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        for key in database._DEPLOYMENT_ID_ENV_KEYS + database._PLATFORM_ENV_KEYS:
            os.environ.pop(key, None)
        database.setup_database()

    def tearDown(self):
        self.tmp.cleanup()

    def test_registry_and_recommended_pack_include_persistent_menu_event(self):
        labels = dict(message_effects.FX_EVENTS)
        self.assertEqual(labels["persistent_menu_opened"], "🏠 Persistent Menu Opened")
        self.assertEqual(message_effects.RECOMMENDED_EVENT_EFFECTS["persistent_menu_opened"], PARTY)
        message_effects.apply_recommended_event_effects()
        self.assertEqual(message_effects.event_effect("persistent_menu_opened"), PARTY)

    def test_persistent_home_handler_sends_effect_and_restores_context(self):
        message_effects.set_event_effect("persistent_menu_opened", PARTY)
        message = _PersistentMenuMessage(chat_id=777)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=777, username="customer", first_name="Customer"),
            message=message,
        )
        context = SimpleNamespace(user_data={}, application=None)

        with patch.object(handlers_start, "save_user"), \
             patch.object(handlers_start, "_panic_reset_user_session", new=AsyncMock()), \
             patch.object(handlers_start, "get_setting", return_value="Bite Store"), \
             patch.object(handlers_start, "_r", return_value="Welcome {shop_name} {user_id}"), \
             patch.object(handlers_start, "smart_text_and_mode", side_effect=lambda text, _mode: (text, "Markdown")), \
             patch.object(handlers_start, "main_menu_keyboard", return_value="menu-markup"):
            asyncio.run(handlers_start.handle_main_menu_button(update, context))

        self.assertEqual(len(message.calls), 1)
        _text, kwargs, active_event = message.calls[0]
        self.assertEqual(active_event, "persistent_menu_opened")
        self.assertEqual(kwargs.get("message_effect_id"), PARTY)
        self.assertEqual(message_effects.CURRENT_EVENT.get(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
