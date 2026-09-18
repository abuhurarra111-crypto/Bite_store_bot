# -*- coding: utf-8 -*-
"""
v170.100 REGRESSION SUITE:
1. Fake activity 1-60s interval guaranteed on selected destination.
2. Products ranking by sales/orders (single continuous list).
3. Mass refund flow: Time filters (24h, 7d, 30d, custom days, all time).
4. Product actions: Deactivate, Delete, Keep Active.
5. Idempotent ledger credit & prevention of duplicate refunds.
"""

import os, sys, shutil, tempfile, asyncio, sqlite3
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

_TMPDIR = tempfile.mkdtemp(prefix="v170100_regr_")
_REGDB = os.path.join(_TMPDIR, "regression.db")
os.environ["DB_PATH"] = _REGDB
os.environ.setdefault("BOT_TOKEN", "1:test")
os.environ.setdefault("ADMIN_ID", "7105782769")
os.environ.setdefault("GEMINI_API_KEY", "x")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_SRC_DB = "/home/user/bite_store_restore_ready.db"
if os.path.exists(_SRC_DB):
    shutil.copy(_SRC_DB, _REGDB)

import pytest
import database
import per_user_activity
import ranked_products_admin
from ranked_products_admin import (
    get_ranked_products_for_admin,
    _fetch_eligible_refund_orders,
    handle_custom_days_input
)
from utils import points_from_usd


def _db():
    conn = sqlite3.connect(_REGDB)
    conn.row_factory = sqlite3.Row
    return conn


class TestFakeActivityTiming:
    def test_destination_interval_strictly_1_to_60(self):
        """Owner rule: Destination fake activity must be between 1 and 60 seconds."""
        mn, mx = per_user_activity.get_dest_interval_seconds()
        assert mn >= 1
        assert mx <= 60
        assert mn <= mx

    def test_destination_interval_custom_setting(self):
        """Custom setting for destination interval is clamped to 1-60."""
        database.set_setting("pua_dest_min_sec", "5")
        database.set_setting("pua_dest_max_sec", "45")
        mn, mx = per_user_activity.get_dest_interval_seconds()
        assert mn == 5
        assert mx == 45

        # Edge case: max exceeds 60 -> clamped to 60
        database.set_setting("pua_dest_max_sec", "120")
        mn, mx = per_user_activity.get_dest_interval_seconds()
        assert mx == 60


class TestRankedProducts:
    def test_ranked_products_query(self):
        """Top products are sorted by real_sold + delivered orders."""
        ranked = get_ranked_products_for_admin()
        assert len(ranked) > 0
        # Check that scores are descending
        scores = [p['rank_score'] for p in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_eligible_orders_fetching_and_windows(self):
        """Ensure order filtering by product, status, and time window."""
        conn = _db()
        # Insert a test product and test orders
        c = conn.cursor()
        c.execute("INSERT INTO products (name, price, stock, is_active) VALUES ('Test Rank Prod', 2.0, 10, 1)")
        test_pid = c.lastrowid
        now = datetime.now()
        yesterday = (now - timedelta(days=1, hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        last_week = (now - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S")
        old_date = (now - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")

        # Order 1: within 24h
        c.execute("""INSERT INTO orders (user_id, product_id, product_name, price, status, payment_method, created_at)
                     VALUES (101, ?, 'Test Rank Prod', 2.0, 'delivered', 'binance', ?)""",
                  (test_pid, now.strftime("%Y-%m-%d %H:%M:%S")))
        # Order 2: within 7 days
        c.execute("""INSERT INTO orders (user_id, product_id, product_name, price, status, payment_method, created_at)
                     VALUES (102, ?, 'Test Rank Prod', 2.0, 'delivered', 'wallet', ?)""",
                  (test_pid, last_week))
        # Order 3: 40 days ago
        c.execute("""INSERT INTO orders (user_id, product_id, product_name, price, status, payment_method, created_at)
                     VALUES (103, ?, 'Test Rank Prod', 2.0, 'delivered', 'wallet', ?)""",
                  (test_pid, old_date))
        # Order 4: freebie (should be excluded)
        c.execute("""INSERT INTO orders (user_id, product_id, product_name, price, status, payment_method, created_at)
                     VALUES (104, ?, 'Test Rank Prod', 0.0, 'delivered', 'freebie', ?)""",
                  (test_pid, now.strftime("%Y-%m-%d %H:%M:%S")))
        # Order 5: cancelled/pending (should be excluded)
        c.execute("""INSERT INTO orders (user_id, product_id, product_name, price, status, payment_method, created_at)
                     VALUES (105, ?, 'Test Rank Prod', 2.0, 'pending', 'binance', ?)""",
                  (test_pid, now.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

        # Test windows
        all_orders = _fetch_eligible_refund_orders(test_pid, "all")
        assert len(all_orders) == 3  # orders 1, 2, 3 (freebie and pending excluded)

        orders_24h = _fetch_eligible_refund_orders(test_pid, "24h")
        assert len(orders_24h) == 1
        assert orders_24h[0]['user_id'] == 101

        orders_7d = _fetch_eligible_refund_orders(test_pid, "7d")
        assert len(orders_7d) == 2  # orders 1 and 2

        orders_custom_10d = _fetch_eligible_refund_orders(test_pid, "10d")
        assert len(orders_custom_10d) == 2

        orders_custom_50d = _fetch_eligible_refund_orders(test_pid, "50d")
        assert len(orders_custom_50d) == 3


@pytest.mark.asyncio
class TestMassRefundExecution:
    async def test_mass_refund_and_idempotency(self):
        """Test points crediting, idempotency, and status update."""
        conn = _db()
        c = conn.cursor()
        c.execute("INSERT INTO products (name, price, stock, is_active) VALUES ('Refundable Tool', 5.0, 5, 1)")
        pid = c.lastrowid
        # Create test buyer user
        test_uid = 999111222
        c.execute("INSERT OR REPLACE INTO users (user_id, points) VALUES (?, 10.0)", (test_uid,))
        c.execute("""INSERT INTO orders (user_id, product_id, product_name, price, status, payment_method, created_at)
                     VALUES (?, ?, 'Refundable Tool', 5.0, 'delivered', 'wallet', ?)""",
                  (test_uid, pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        oid = c.lastrowid
        conn.commit()
        conn.close()

        pts = points_from_usd(5.0)
        event_id = f"mass_product_refund_{oid}"

        # 1. Credit refund
        ok1 = database.add_points(
            uid=test_uid,
            pts=pts,
            tx_type="mass_product_refund",
            description="Mass refund test",
            event_id=event_id,
            order_id=oid
        )
        assert ok1 is True

        user = database.get_user(test_uid)
        assert float(user['points']) == 10.0 + pts

        # 2. Duplicate credit attempt with same event_id must fail (idempotency)
        ok2 = database.add_points(
            uid=test_uid,
            pts=pts,
            tx_type="mass_product_refund",
            description="Duplicate attempt",
            event_id=event_id,
            order_id=oid
        )
        assert ok2 is False
        # Balance must remain unchanged
        user_after = database.get_user(test_uid)
        assert float(user_after['points']) == 10.0 + pts

        # 3. Eligible orders query now ignores already refunded order
        database.update_order_status(oid, 'refunded')
        rem = _fetch_eligible_refund_orders(pid, "all")
        assert len(rem) == 0

    async def test_product_deactivation_and_deletion(self):
        """Verify product can be deactivated or deleted as part of refund."""
        conn = _db()
        c = conn.cursor()
        c.execute("INSERT INTO products (name, price, stock, is_active) VALUES ('Deactivatable Tool', 1.0, 5, 1)")
        pid = c.lastrowid
        conn.commit()
        conn.close()

        # Deactivate
        database.set_product_active(pid, False)
        p = database.get_product(pid)
        assert p['is_active'] == 0

        # Permanent delete
        database.delete_product_permanently(pid)
        p_deleted = database.get_product(pid)
        assert p_deleted is None

    async def test_custom_days_input_handler(self):
        """Test custom days text parsing."""
        update = MagicMock()
        update.effective_user.id = int(os.environ["ADMIN_ID"])
        update.message.text = "14"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {'mass_refund_custom_pid': 123}

        # Mock show_mass_refund_preview so it doesn't need full DB data
        orig_show = ranked_products_admin.show_mass_refund_preview
        show_mock = AsyncMock()
        ranked_products_admin.show_mass_refund_preview = show_mock

        try:
            res = await handle_custom_days_input(update, context)
            assert res is True
            assert 'mass_refund_custom_pid' not in context.user_data
            show_mock.assert_called_once()
            args = show_mock.call_args[0]
            assert args[2] == 123  # pid
            assert args[3] == "14d"  # window
        finally:
            ranked_products_admin.show_mass_refund_preview = orig_show
