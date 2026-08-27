"""Regression coverage for credential-safe hosted logging."""

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_IMPORT_TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault("BOT_TOKEN", "test-token-not-real")
os.environ["ADMIN_ID"] = "424242"
os.environ["DB_PATH"] = str(Path(_IMPORT_TEMP.name) / "import.db")

import bot


class HostedLogSecurityTests(unittest.TestCase):
    def test_token_shaped_values_are_redacted_before_emission(self):
        # Build synthetic fixtures at runtime; do not keep token-shaped literals
        # in source control even when they are deliberately fake.
        telegram_token = "123456789:" + ("a" * 31)
        github_token = "ghp_" + ("b" * 31)
        text = f"Telegram {telegram_token}; GitHub {github_token}; Bearer abc.def-123"
        redacted = bot._redact_sensitive_log_text(text)
        self.assertNotIn(telegram_token, redacted)
        self.assertNotIn(github_token, redacted)
        self.assertNotIn("abc.def-123", redacted)
        self.assertIn("[REDACTED_TELEGRAM_TOKEN]", redacted)
        self.assertIn("[REDACTED_GITHUB_TOKEN]", redacted)

        record = logging.LogRecord(
            "test", logging.ERROR, __file__, 1, "request to %s", (telegram_token,), None,
        )
        self.assertTrue(bot._sensitive_log_filter.filter(record))
        self.assertNotIn(telegram_token, record.getMessage())

    def test_http_request_loggers_cannot_emit_token_bearing_info_urls(self):
        self.assertGreaterEqual(logging.getLogger("httpx").getEffectiveLevel(), logging.WARNING)
        self.assertGreaterEqual(logging.getLogger("httpcore").getEffectiveLevel(), logging.WARNING)


if __name__ == "__main__":
    unittest.main()
