# 🆕 v151 — Bot boots FRESH (no bundled DB); admin restores their own DB via
# Admin → Backup & Restore. Tests:
#   1. Fresh DB (no file) → setup creates a working empty schema
#   2. Restore-ready DB (admin's latest, modified) → migrate_all clean,
#      all key features present
#   3. No bundle references remain in the source
import os
import sys
import shutil
import sqlite3

os.environ.setdefault("DB_PATH", "/tmp/v151_unit.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db


def test_no_bundle_code_remains():
    src_bot = open("bot.py", encoding="utf-8").read()
    src_db = open("database.py", encoding="utf-8").read()
    assert "restore_bundled_db_if_needed" not in src_db, "bundle fn must be removed"
    assert "latest_shop" not in src_bot, "bundle ref must be removed"


def test_fresh_boot_creates_schema():
    p = "/tmp/v151_fresh.db"
    if os.path.exists(p):
        os.remove(p)
    db.DB_PATH = p
    stats = db.migrate_all()  # what main() runs after startup
    assert len(stats.get("errors") or []) == 0, stats.get("errors")
    c = sqlite3.connect(p)
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("users", "orders", "products", "bot_settings", "ext_suppliers",
              "ext_products", "polls", "poll_answers", "force_join_targets"):
        assert t in tables, f"fresh boot missing table {t}"
    c.close()
    print("  fresh boot tables:", len(tables))


def test_restore_ready_db_boots():
    """Simulate the admin restoring the modified latest DB through the bot:
    upload → migrate_all → all features available."""
    src = "/home/user/bite_store_restore_ready.db"
    if not os.path.exists(src):
        pytest.skip("restore-ready DB not present")
    p = "/tmp/v151_restore.db"
    shutil.copy2(src, p)
    db.DB_PATH = p
    stats = db.migrate_all()
    assert len(stats.get("errors") or []) == 0, stats.get("errors")
    c = sqlite3.connect(p)
    users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    orders = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    c.close()
    assert users > 800 and orders > 300, f"restore data wrong: users={users} orders={orders}"
    print(f"  restore DB: users={users} orders={orders}")
