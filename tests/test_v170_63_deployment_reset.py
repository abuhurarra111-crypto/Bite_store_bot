"""Regression coverage for the owner-approved fresh-DB deployment policy."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_IMPORT_TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault("DB_PATH", str(Path(_IMPORT_TEMP.name) / "import.db"))

import database


class FreshDeploymentDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        self.old_wal_state = database._WAL_SETUP_DONE
        self.old_deploy_id = os.environ.get("RAILWAY_DEPLOYMENT_ID")
        self.db_path = str(Path(self.tmp.name) / "shop.db")
        database.DB_PATH = self.db_path
        database._WAL_SETUP_DONE = False
        os.environ["RAILWAY_DEPLOYMENT_ID"] = "unit-deploy-a"

    def tearDown(self):
        database.DB_PATH = self.old_db_path
        database._WAL_SETUP_DONE = self.old_wal_state
        if self.old_deploy_id is None:
            os.environ.pop("RAILWAY_DEPLOYMENT_ID", None)
        else:
            os.environ["RAILWAY_DEPLOYMENT_ID"] = self.old_deploy_id
        self.tmp.cleanup()

    def test_new_deployment_resets_but_same_deployment_preserves_manual_data(self):
        database.setup_database()
        cid = database.add_category("Manual restore candidate", "📦")
        self.assertIsNotNone(database.get_category(cid))

        # A restart of the exact same deployment preserves data, which lets the
        # owner manually restore the Ready DB without a later restart erasing it.
        database.setup_database()
        self.assertIsNotNone(database.get_category(cid))

        # A different Railway deployment identity gets a clean database.
        os.environ["RAILWAY_DEPLOYMENT_ID"] = "unit-deploy-b"
        database.setup_database()
        self.assertEqual(database.get_categories(include_inactive=True), [])
        marker = Path(self.tmp.name) / ".bite_store_deployment_marker"
        self.assertEqual(marker.read_text(encoding="utf-8"),
                         "RAILWAY_DEPLOYMENT_ID:unit-deploy-b")


if __name__ == "__main__":
    unittest.main()
