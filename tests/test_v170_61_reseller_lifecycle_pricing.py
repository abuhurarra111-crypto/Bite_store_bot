"""Focused v170.61 regressions for catalog lifecycle and live promotion rules.

These are database/API-unit tests: no real network, bot token, catalog provider,
or Telegram delivery is used.
"""

import asyncio
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOT_TOKEN", "test-token-not-real")
os.environ.setdefault("ADMIN_ID", "424242")
_IMPORT_TEMP = tempfile.TemporaryDirectory()
os.environ["DB_PATH"] = str(Path(_IMPORT_TEMP.name) / "import.db")

import database
import ext_suppliers
import handlers_order
import reseller_api
import supplier_automation
from utils import points_from_usd


class ResellerLifecyclePricingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        database.setup_database()
        database.migrate_reseller_tables()
        ext_suppliers.ensure_ext_supplier_tables()
        self.category_id = database.add_category("v170.61 test catalog")

    def tearDown(self):
        self.tmp.cleanup()

    def _product(self, name="Product", price=10.0, stock=50, delivery_text=""):
        return database.add_product(
            self.category_id, name, "test description", price, 0.0, stock,
            delivery_text=delivery_text,
        )

    def test_base_price_change_preserves_flash_and_every_tier_ratio(self):
        pid = self._product(price=3.0, stock=50)
        self.assertTrue(database.set_product_tier(pid, 10, 2.80))
        self.assertTrue(database.set_product_tier(pid, 30, 2.30))
        self.assertTrue(database.set_product_flash_price(pid, 2.50))

        self.assertTrue(database.update_product_base_price(pid, 4.50))
        p = database.get_product(pid)
        tiers = database.get_product_tiers(pid)
        self.assertEqual([t["min_qty"] for t in tiers], [10, 30])
        self.assertAlmostEqual(tiers[0]["unit_price"], 4.20, places=4)
        self.assertAlmostEqual(tiers[1]["unit_price"], 3.45, places=4)
        self.assertAlmostEqual(float(p["flash_price"]), 3.75, places=4)

        # Owner-confirmed priority: valid Flash beats the 30+ tier.
        unit, kind, tier = database.effective_product_unit_price(p, qty=30)
        self.assertEqual(kind, "flash")
        self.assertEqual(tier, 1)
        self.assertAlmostEqual(unit, 3.75, places=4)

        conn = database.get_connection()
        try:
            conn.execute("UPDATE products SET is_flash_sale=0 WHERE id=?", (pid,))
            conn.commit()
        finally:
            conn.close()
        p = database.get_product(pid)
        unit, kind, tier = database.effective_product_unit_price(p, qty=30)
        self.assertEqual((kind, tier), ("tier", 30))
        self.assertAlmostEqual(unit, 3.45, places=4)

    def test_stock_filters_tiers_and_expired_flash_does_not_hide_them(self):
        pid = self._product(price=10.0, stock=15)
        database.set_product_tier(pid, 10, 8.0)
        database.set_product_tier(pid, 30, 6.0)
        p = database.get_product(pid)

        visible = database.get_available_product_tiers(pid, stock=15)
        self.assertEqual([t["min_qty"] for t in visible], [10])
        unit, kind, tier = database.effective_product_unit_price(p, qty=30)
        self.assertEqual((kind, tier), ("tier", 10))
        self.assertAlmostEqual(unit, 8.0)

        database.update_product_stock(pid, 5)
        p = database.get_product(pid)
        self.assertEqual(database.get_available_product_tiers(pid, stock=5), [])
        unit, kind, tier = database.effective_product_unit_price(p, qty=10)
        self.assertEqual((kind, tier), ("normal", 1))
        self.assertAlmostEqual(unit, 10.0)

        # Existing catalog semantics are retained: a finite sold-out item is
        # listed with inStock=false, but every tier disappears and checkout
        # rejects it. Lifecycle revocations, unlike stock, remove the item.
        database.update_product_stock(pid, 0)
        listed = [x for x in reseller_api._resellable_products() if int(x["id"]) == pid]
        self.assertEqual(len(listed), 1)
        self.assertFalse(reseller_api._product_payload(listed[0])["inStock"])
        self.assertEqual(reseller_api._product_payload(listed[0])["promotion"]["quantityTiers"], [])

        database.update_product_stock(pid, 40)
        self.assertEqual([t["min_qty"] for t in database.get_available_product_tiers(pid, stock=40)], [10, 30])

        self.assertTrue(database.set_product_flash_price(pid, 7.0))
        conn = database.get_connection()
        try:
            past = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("UPDATE products SET flash_until=? WHERE id=?", (past, pid))
            conn.commit()
        finally:
            conn.close()
        p = database.get_product(pid)
        self.assertFalse(database.is_flash_sale_active(p))
        self.assertEqual([t["min_qty"] for t in database.get_available_product_tiers(pid, stock=40)], [10, 30])
        unit, kind, tier = database.effective_product_unit_price(p, qty=30)
        self.assertEqual((kind, tier), ("tier", 30))
        self.assertAlmostEqual(unit, 6.0)

    def test_reseller_payload_uses_live_promotion_rule_and_premium_only_emoji(self):
        pid = self._product(
            name='🔥 [[HTML]]<tg-emoji emoji-id="123456">⭐</tg-emoji> Gold Plan',
            price=10.0,
            stock=20,
        )
        database.set_product_tier(pid, 5, 8.0)
        database.set_bulk_discount([pid], 10)
        p = dict(database.get_product(pid))

        # Percentage campaign applies to one unit, but eligible tier wins at 5.
        self.assertAlmostEqual(reseller_api.reseller_price_for(p, quantity=1), 9.0)
        self.assertAlmostEqual(reseller_api.reseller_price_for(p, quantity=5), 8.0)
        payload = reseller_api._product_payload(p)
        self.assertEqual(payload["priceType"], "discount")
        self.assertEqual(payload["promotion"]["quantityTiers"], [{"minQty": 5, "unitPrice": 8.0}])
        self.assertNotIn("🔥", payload["name"])
        self.assertNotIn("🔥", payload["name_html"])
        self.assertIn("<tg-emoji", payload["emoji"])
        self.assertEqual(payload["emoji"], payload["premiumEmoji"])

        database.set_product_flash_price(pid, 7.0)
        p = dict(database.get_product(pid))
        payload = reseller_api._product_payload(p)
        self.assertAlmostEqual(payload["price"], 7.0)
        self.assertEqual(payload["priceType"], "flash")
        self.assertEqual(payload["promotion"]["quantityTiers"], [])
        self.assertAlmostEqual(reseller_api.reseller_price_for(p, quantity=5), 7.0)

    def test_unsync_source_state_supplier_toggle_and_resync_keep_same_local_row(self):
        sid = ext_suppliers.add_supplier("Test catalog", "insta_api", "https://example.invalid", "test-key")
        eid = ext_suppliers.upsert_ext_product(
            sid, "remote-1", "Catalog item", "desc", 4.0, 25,
            category_id=self.category_id, source_active=True,
        )
        # Setting synced_to_shop mirrors immediately; an explicit re-mirror is
        # safe and must retain that same linked row.
        ext_suppliers.update_ext_product(eid, synced_to_shop=1)
        shop_pid = int(ext_suppliers.get_ext_product(eid)["shop_product_id"])
        restored_pid, _ = ext_suppliers.mirror_ext_to_products(eid)
        self.assertEqual(restored_pid, shop_pid)
        self.assertGreater(shop_pid, 0)
        self.assertTrue(any(int(p["id"]) == shop_pid for p in reseller_api._resellable_products()))

        # Native admin deactivate/activate must be durable owner intent for a
        # mirror too; a future refresh must not resurrect it by accident.
        self.assertTrue(database.set_product_active(shop_pid, False))
        self.assertEqual(int(ext_suppliers.get_ext_product(eid)["owner_active"]), 0)
        self.assertFalse(database.product_is_catalog_available(database.get_product(shop_pid)))
        self.assertFalse(any(int(p["id"]) == shop_pid for p in reseller_api._resellable_products()))
        self.assertTrue(database.set_product_active(shop_pid, True))
        self.assertEqual(int(ext_suppliers.get_ext_product(eid)["owner_active"]), 1)
        self.assertTrue(any(int(p["id"]) == shop_pid for p in reseller_api._resellable_products()))

        # Owner unsync is externally delete-like but preserves IDs/settings.
        stats = ext_suppliers.unmirror_ext_product(eid)
        self.assertEqual(stats["shop_product_id"], shop_pid)
        retained = dict(database.get_product(shop_pid))
        self.assertEqual(retained["is_archived"], 1)
        self.assertNotIn(shop_pid, [int(p["id"]) for p in database.get_all_products(include_hidden=True, include_inactive=True)])
        self.assertFalse(any(int(p["id"]) == shop_pid for p in reseller_api._resellable_products()))

        ext_suppliers.update_ext_product(eid, synced_to_shop=1)
        restored_pid, was_new = ext_suppliers.mirror_ext_to_products(eid)
        self.assertEqual(restored_pid, shop_pid)
        self.assertFalse(was_new)
        self.assertEqual(int(dict(database.get_product(shop_pid))["is_archived"]), 0)
        self.assertTrue(any(int(p["id"]) == shop_pid for p in reseller_api._resellable_products()))

        # Owner active switch, source disappearance/reappearance, and catalog
        # owner enable switch all reach the reseller catalog immediately.
        self.assertEqual(ext_suppliers.toggle_ext_product_active(eid), 0)
        self.assertFalse(any(int(p["id"]) == shop_pid for p in reseller_api._resellable_products()))
        self.assertEqual(ext_suppliers.toggle_ext_product_active(eid), 1)
        self.assertTrue(any(int(p["id"]) == shop_pid for p in reseller_api._resellable_products()))

        ext_suppliers.set_ext_product_source_active(eid, False, missing=True)
        self.assertFalse(any(int(p["id"]) == shop_pid for p in reseller_api._resellable_products()))
        ext_suppliers.set_ext_product_source_active(eid, True)
        self.assertTrue(any(int(p["id"]) == shop_pid for p in reseller_api._resellable_products()))

        ext_suppliers.update_supplier(sid, enabled=0)
        ext_suppliers.refresh_supplier_mirrors(sid)
        self.assertFalse(any(int(p["id"]) == shop_pid for p in reseller_api._resellable_products()))
        ext_suppliers.update_supplier(sid, enabled=1)
        ext_suppliers.refresh_supplier_mirrors(sid)
        self.assertTrue(any(int(p["id"]) == shop_pid for p in reseller_api._resellable_products()))

    def test_direct_unavailable_status_is_normalized_as_source_inactive(self):
        self.assertFalse(ext_suppliers.source_product_is_active({"status": "unavailable"}))
        self.assertFalse(ext_suppliers.source_product_is_active({"available": "unavailable"}))
        self.assertFalse(ext_suppliers.source_product_is_active({"raw": {"status": "unavailable"}}))
        self.assertTrue(ext_suppliers.source_product_is_active({"status": "available"}))

    def test_insta_adapter_normalizes_unavailable_string_before_source_sync(self):
        # The adapter preserves an explicit provider string in its normalized
        # source_active field.  A direct ``available: unavailable`` value must
        # never be turned into a truthy Python string and republished.
        from insta_api_adapter import InstaAPIAdapter

        class _Response:
            status_code = 200
            def json(self):
                return {"success": True, "products": [{
                    "id": "insta-unavailable", "name_en": "Catalog item",
                    "store_price": 1.0, "stock": 5, "available": "unavailable",
                }]}

        adapter = InstaAPIAdapter("test-key", "https://example.invalid")
        with patch.object(adapter, "_get", return_value=_Response()):
            products = adapter.fetch_products()
        self.assertEqual(len(products), 1)
        self.assertFalse(ext_suppliers.source_product_is_active(products[0]))

    def test_bulk_unsync_then_bulk_restore_keeps_identity_and_skips_manual_unsync(self):
        sid = ext_suppliers.add_supplier("Bulk restore catalog", "insta_api", "https://example.invalid", "test-key")
        eids = []
        pids = []
        for remote_id in ("bulk-a", "bulk-b"):
            eid = ext_suppliers.upsert_ext_product(
                sid, remote_id, f"Bulk {remote_id}", "desc", 2.0, 20,
                category_id=self.category_id, source_active=True,
            )
            ext_suppliers.update_ext_product(eid, synced_to_shop=1)
            eids.append(eid)
            pids.append(int(ext_suppliers.get_ext_product(eid)["shop_product_id"]))
        database.set_product_tier(pids[0], 10, 8.0)
        database.set_product_flash_price(pids[0], 7.0)

        self.assertEqual(supplier_automation._unsync_supplier_shop_products(sid), (2, 2))
        for eid, pid in zip(eids, pids):
            ep = ext_suppliers.get_ext_product(eid)
            self.assertEqual((int(ep["synced_to_shop"]), int(ep["bulk_unsynced"])), (0, 1))
            self.assertTrue(int(dict(database.get_product(pid))["is_archived"]))
            self.assertFalse(any(int(x["id"]) == pid for x in reseller_api._resellable_products()))

        restored = ext_suppliers.restore_bulk_unsynced_supplier_products(sid)
        self.assertEqual(restored, eids)
        for eid, pid in zip(eids, pids):
            restored_pid, was_new = ext_suppliers.mirror_ext_to_products(eid)
            self.assertEqual((restored_pid, was_new), (pid, False))
            self.assertEqual((int(ext_suppliers.get_ext_product(eid)["synced_to_shop"]),
                              int(ext_suppliers.get_ext_product(eid)["bulk_unsynced"])), (1, 0))
            self.assertFalse(int(dict(database.get_product(pid))["is_archived"]))
            self.assertTrue(any(int(x["id"]) == pid for x in reseller_api._resellable_products()))
        self.assertAlmostEqual(database.get_product_tiers(pids[0])[0]["unit_price"], 8.0)
        self.assertAlmostEqual(float(database.get_product(pids[0])["flash_price"]), 7.0)

        # A normal per-product unsync is an explicit owner choice, not a bulk
        # restore candidate; the next Bulk Sync must leave it hidden.
        ext_suppliers.unmirror_ext_product(eids[1])
        self.assertEqual(int(ext_suppliers.get_ext_product(eids[1])["bulk_unsynced"]), 0)
        self.assertEqual(ext_suppliers.restore_bulk_unsynced_supplier_products(sid), [])
        self.assertFalse(any(int(x["id"]) == pids[1] for x in reseller_api._resellable_products()))

    def test_category_deactivation_keeps_linked_product_disabled_after_refresh(self):
        sid = ext_suppliers.add_supplier("Category lifecycle catalog", "insta_api", "https://example.invalid", "test-key")
        eid = ext_suppliers.upsert_ext_product(
            sid, "category-linked", "Category linked", "desc", 2.0, 10,
            category_id=self.category_id, source_active=True,
        )
        ext_suppliers.update_ext_product(eid, synced_to_shop=1)
        pid = int(ext_suppliers.get_ext_product(eid)["shop_product_id"])
        database.delete_category(self.category_id)
        self.assertEqual(int(ext_suppliers.get_ext_product(eid)["owner_active"]), 0)
        ext_suppliers.update_ext_product(eid, stock=12)  # ordinary source refresh
        self.assertFalse(database.product_is_catalog_available(database.get_product(pid)))
        self.assertFalse(any(int(x["id"]) == pid for x in reseller_api._resellable_products()))

    def test_credentials_continuation_rechecks_live_product_state(self):
        pid = self._product(name="Credential product", price=2.0, stock=3)
        conn = database.get_connection()
        try:
            conn.execute("UPDATE products SET req_account_type='gmail', req_password=1 WHERE id=?", (pid,))
            conn.commit()
        finally:
            conn.close()
        database.set_product_active(pid, False)

        class _Message:
            def __init__(self):
                self.text = "person@gmail.com | password"
                self.replies = []
            async def reply_text(self, text, *args, **kwargs):
                self.replies.append((text, args, kwargs))
                return SimpleNamespace(message_id=1)

        message = _Message()
        context = SimpleNamespace(user_data={
            "order_req_pid": pid, "order_req_qty": 1, "order_req_step": "credentials",
        })
        self.assertTrue(asyncio.run(handlers_order.order_creds_received(
            SimpleNamespace(message=message), context,
        )))
        self.assertTrue(message.replies)
        self.assertIn("no longer available", str(message.replies[-1][0]).lower())
        self.assertNotIn("order_req_pid", context.user_data)
        self.assertNotIn("order_creds", context.user_data)

    def test_native_paid_local_order_revoked_before_delivery_is_refunded(self):
        pid = self._product(name="Revoked local", price=3.0, stock=5, delivery_text="Should not send")
        uid = 7008
        database.save_user(uid, "", "Local customer")
        oid = database.create_order(uid, "Local customer", pid, "Revoked local", 3.0,
                                    "wallet", "", 30.0, "PTS", "product", qty=1)
        database.update_order_status(oid, "paid")
        database.set_product_active(pid, False)

        class _Bot:
            def __init__(self): self.messages = []
            async def send_message(self, chat_id, text, *args, **kwargs):
                self.messages.append((chat_id, text, args, kwargs))
                return SimpleNamespace(message_id=len(self.messages))

        self.assertTrue(asyncio.run(handlers_order.fulfill_paid_product_order(_Bot(), database.get_order(oid))))
        self.assertEqual(database.get_order(oid)["status"], "refunded")
        self.assertAlmostEqual(database.get_combined_points(uid), points_from_usd(3.0))

    def test_wallet_debit_is_reversed_when_product_revokes_during_checkout(self):
        pid = self._product(name="Wallet race", price=2.0, stock=5, delivery_text="Reusable")
        uid = 7009
        database.save_user(uid, "", "Wallet customer")
        database.add_points(uid, 30.0, description="test balance")

        class _Query:
            def __init__(self):
                self.data = f"pay_pts_{pid}_1"
                self.from_user = SimpleNamespace(id=uid, username="wallet", first_name="Wallet customer")
                self.edits = []
            async def answer(self, *args, **kwargs):
                return None
            async def edit_message_text(self, text, **kwargs):
                self.edits.append((text, kwargs))
                return SimpleNamespace(message_id=len(self.edits))

        class _Bot:
            async def send_message(self, *args, **kwargs):
                return SimpleNamespace(message_id=1)

        original_debit = database.deduct_combined_points
        def _debit_then_revoke(*args, **kwargs):
            ok = original_debit(*args, **kwargs)
            if ok:
                database.set_product_active(pid, False)
            return ok

        query = _Query()
        with patch.object(database, "deduct_combined_points", side_effect=_debit_then_revoke):
            asyncio.run(handlers_order.pay_pts_callback(
                SimpleNamespace(callback_query=query), SimpleNamespace(bot=_Bot(), user_data={}),
            ))
        self.assertAlmostEqual(database.get_combined_points(uid), 30.0)
        self.assertEqual(database.get_order_count(), 0)
        self.assertTrue(any("reversed" in str(text).lower() for text, _ in query.edits))

    def test_zero_stock_static_file_is_reusable_for_delivery_builder_native_and_reseller(self):
        pid = self._product(name="Static file", price=2.0, stock=0, delivery_text="file fallback")
        conn = database.get_connection()
        try:
            conn.execute("""UPDATE products
                            SET delivery_file_id=?, delivery_file_type=?,
                                delivery_file_name=?, delivery_caption=?
                            WHERE id=?""",
                         ("telegram-file-id", "document", "guide.pdf", "Reusable guide", pid))
            conn.commit()
        finally:
            conn.close()

        detailed = database.build_delivery_detailed(pid, order_id=5001, qty=3, buyer_uid=7001)
        self.assertTrue(detailed["ok"])
        self.assertEqual(detailed["mode"], "static_file")
        self.assertEqual(detailed["file_id"], "telegram-file-id")
        self.assertEqual((detailed["delivered"], detailed["requested"]), (3, 3))
        self.assertEqual(int(dict(database.get_product(pid))["stock"]), 0)

        pd = dict(database.get_product(pid))
        self.assertTrue(reseller_api.reseller_product_availability(pd, quantity=8)[0])
        ok, items, status, err, file_ref = reseller_api._fulfill_reseller_order(pd, 2, 7001, 8001)
        self.assertTrue(ok)
        self.assertEqual((items, status, err), ([], "delivered", None))
        self.assertEqual(file_ref["file_id"], "telegram-file-id")
        self.assertEqual(int(dict(database.get_product(pid))["stock"]), 0)

        uid = 7001
        database.save_user(uid, "", "File customer")
        oid = database.create_order(uid, "File customer", pid, "Static file × 2", 4.0,
                                    "wallet", "", 40.0, "PTS", "product", qty=2)
        database.update_order_status(oid, "paid")

        class _Bot:
            def __init__(self): self.documents = []; self.messages = []
            async def send_document(self, chat_id, document, *args, **kwargs):
                self.documents.append((chat_id, document, args, kwargs))
                return SimpleNamespace(message_id=1)
            async def send_message(self, chat_id, text, *args, **kwargs):
                self.messages.append((chat_id, text, args, kwargs))
                return SimpleNamespace(message_id=len(self.messages))

        bot = _Bot()
        self.assertTrue(asyncio.run(handlers_order.fulfill_paid_product_order(bot, database.get_order(oid))))
        self.assertEqual(database.get_order(oid)["status"], "delivered")
        self.assertEqual(database.get_order(oid)["delivery_file_id"], "telegram-file-id")
        self.assertEqual(len(bot.documents), 1)
        self.assertEqual(bot.documents[0][1], "telegram-file-id")
        self.assertEqual(int(dict(database.get_product(pid))["stock"]), 0)

    def test_hard_delete_refunds_unsubmitted_paid_linked_order_once(self):
        sid = ext_suppliers.add_supplier("Hard delete refund", "insta_api", "https://example.invalid", "test-key")
        eid = ext_suppliers.upsert_ext_product(
            sid, "remote-hard-delete", "Hard delete item", "desc", 2.0, 10,
            category_id=self.category_id, source_active=True,
        )
        ext_suppliers.update_ext_product(eid, synced_to_shop=1)
        pid = int(ext_suppliers.get_ext_product(eid)["shop_product_id"])
        uid = 7011
        database.save_user(uid, "", "Hard delete customer")
        oid = database.create_order(uid, "Hard delete customer", pid, "Hard delete item", 3.0,
                                    "wallet", "", 30.0, "PTS", "product", qty=1)
        database.update_order_status(oid, "paid")

        stats = database.delete_product_permanently(pid)
        self.assertEqual(stats["products"], 1)
        self.assertEqual(stats["refunded_orders"], 1)
        self.assertIsNone(database.get_product(pid))
        self.assertEqual(database.get_order(oid)["status"], "refunded")
        self.assertAlmostEqual(database.get_combined_points(uid), points_from_usd(3.0))
        self.assertEqual(int(ext_suppliers.get_ext_product(eid)["synced_to_shop"]), 0)
        self.assertFalse(any(int(x["id"]) == pid for x in reseller_api._resellable_products()))
        conn = database.get_connection()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM points_ledger WHERE order_id=?", (oid,)).fetchone()[0], 1)
        finally:
            conn.close()

    def test_hard_delete_preserves_already_processing_supplier_order_without_resubmit_or_refund(self):
        sid = ext_suppliers.add_supplier("Hard delete processing", "insta_api", "https://example.invalid", "test-key")
        eid = ext_suppliers.upsert_ext_product(
            sid, "remote-processing", "Processing item", "desc", 2.0, 10,
            category_id=self.category_id, source_active=True,
        )
        ext_suppliers.update_ext_product(eid, synced_to_shop=1)
        pid = int(ext_suppliers.get_ext_product(eid)["shop_product_id"])
        uid = 7012
        database.save_user(uid, "", "Processing customer")
        oid = database.create_order(uid, "Processing customer", pid, "Processing item", 3.0,
                                    "wallet", "", 30.0, "PTS", "product", qty=1)
        database.update_order_status(oid, "supplier_processing")

        stats = ext_suppliers.delete_ext_product_completely(eid)
        self.assertEqual(stats["deferred_inflight"], 1)
        self.assertEqual(stats["ext_deleted"], 0)
        self.assertIsNotNone(ext_suppliers.get_ext_product(eid))
        retained = dict(database.get_product(pid))
        self.assertEqual((retained["is_active"], retained["is_archived"]), (0, 1))
        self.assertEqual(database.get_order(oid)["status"], "supplier_processing")
        self.assertAlmostEqual(database.get_combined_points(uid), 0.0)
        self.assertEqual(int(ext_suppliers.get_ext_product(eid)["synced_to_shop"]), 0)
        self.assertFalse(any(int(x["id"]) == pid for x in reseller_api._resellable_products()))

        class _Bot:
            async def send_message(self, *args, **kwargs):
                return SimpleNamespace(message_id=1)

        with patch.object(ext_suppliers, "get_adapter_for_supplier") as adapter_factory:
            self.assertTrue(asyncio.run(ext_suppliers.route_order_to_supplier(_Bot(), database.get_order(oid))))
            adapter_factory.assert_not_called()
        self.assertEqual(database.get_order(oid)["status"], "supplier_processing")
        self.assertAlmostEqual(database.get_combined_points(uid), 0.0)

    def test_bulk_unsync_migrates_legacy_schema_inside_transaction(self):
        # Regression for the old SQLite migration path: is_archived did not
        # exist when BEGIN IMMEDIATE started. DDL must still commit together
        # with the reversible bulk archive, not fail or delete configuration.
        legacy_path = Path(self.tmp.name) / "legacy_unsync.db"
        database.DB_PATH = str(legacy_path)
        conn = database.get_connection()
        try:
            conn.executescript("""
                CREATE TABLE products (id INTEGER PRIMARY KEY, is_active INTEGER DEFAULT 1);
                CREATE TABLE ext_products (
                    id INTEGER PRIMARY KEY, supplier_id INTEGER,
                    shop_product_id INTEGER DEFAULT 0, synced_to_shop INTEGER DEFAULT 0
                );
                INSERT INTO products(id,is_active) VALUES(77,1);
                INSERT INTO ext_products(id,supplier_id,shop_product_id,synced_to_shop)
                    VALUES(1,9,77,1);
            """)
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(supplier_automation._unsync_supplier_shop_products(9), (1, 1))
        conn = database.get_connection()
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(products)")}
            row = conn.execute("SELECT is_active,is_archived FROM products WHERE id=77").fetchone()
            synced = conn.execute("SELECT synced_to_shop FROM ext_products WHERE id=1").fetchone()[0]
        finally:
            conn.close()
        self.assertIn("is_archived", cols)
        self.assertEqual(tuple(row), (0, 1))
        self.assertEqual(synced, 0)

    def test_http_catalog_and_checkout_share_stock_tier_flash_rules(self):
        # Exercise the real FastAPI route, not only helper functions.
        from fastapi.testclient import TestClient
        pid = self._product(name="🔥 API stock item", price=10.0, stock=5)
        database.set_product_tier(pid, 10, 8.0)
        api_key, _ = reseller_api.generate_reseller_key(990001, "v170.61 HTTP test")
        client = TestClient(reseller_api.app)
        headers = {"X-API-Key": api_key}

        # Published Swagger/OpenAPI and branded docs use neutral catalog/
        # fulfillment language; implementation details never leak publicly.
        for path in ("/openapi.json", "/docs"):
            public_text = client.get(path).text.lower()
            self.assertNotIn("supplier", public_text)
            self.assertNotIn("upstream", public_text)

        catalog = client.get("/v1/products", headers=headers)
        self.assertEqual(catalog.status_code, 200)
        item = next(x for x in catalog.json()["products"] if x["id"] == str(pid))
        self.assertTrue(item["inStock"])
        self.assertEqual(item["promotion"]["quantityTiers"], [])
        self.assertNotIn("🔥", item["name"])

        # Stock 5 cannot expose or charge the 10+ tier/request.
        rejected = client.post("/v1/orders", headers=headers,
                               json={"productId": str(pid), "quantity": 10})
        self.assertEqual(rejected.status_code, 409)
        conn = database.get_connection()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reseller_orders").fetchone()[0], 0)
        finally:
            conn.close()

        database.update_product_stock(pid, 20)
        database.set_product_flash_price(pid, 7.0)
        catalog = client.get("/v1/products", headers=headers)
        self.assertEqual(catalog.status_code, 200)
        item = next(x for x in catalog.json()["products"] if x["id"] == str(pid))
        self.assertEqual(item["priceType"], "flash")
        self.assertAlmostEqual(item["price"], 7.0)
        self.assertEqual(item["promotion"]["quantityTiers"], [])

    def test_full_source_sync_handles_inactive_missing_and_reappearing_items(self):
        sid = ext_suppliers.add_supplier("Sync state catalog", "insta_api", "https://example.invalid", "test-key")
        eid = ext_suppliers.upsert_ext_product(
            sid, "remote-sync-state", "Sync state item", "desc", 2.0, 10,
            category_id=self.category_id, source_active=True,
        )
        ext_suppliers.update_ext_product(eid, synced_to_shop=1)
        pid = int(ext_suppliers.get_ext_product(eid)["shop_product_id"])

        class _Adapter:
            products = []
            def fetch_products(self):
                return self.products

        adapter = _Adapter()
        with patch.object(ext_suppliers, "get_adapter_for_supplier", return_value=adapter):
            adapter.products = [{
                "remote_id": "remote-sync-state", "name": "Sync state item",
                "description": "desc", "cost_usd": 2.0, "stock": 10,
                "raw": {"active": False},
            }]
            self.assertEqual(ext_suppliers.sync_supplier_products(sid), (1, None))
            self.assertEqual(int(ext_suppliers.get_ext_product(eid)["source_active"]), 0)
            self.assertFalse(database.product_is_catalog_available(database.get_product(pid)))
            self.assertFalse(any(int(x["id"]) == pid for x in reseller_api._resellable_products()))

            adapter.products = []  # full fetch confirms upstream disappearance
            self.assertEqual(ext_suppliers.sync_supplier_products(sid), (0, None))
            self.assertGreater(float(ext_suppliers.get_ext_product(eid)["missing_since"] or 0), 0)
            self.assertFalse(any(int(x["id"]) == pid for x in reseller_api._resellable_products()))

            adapter.products = [{
                "remote_id": "remote-sync-state", "name": "Sync state item restored",
                "description": "desc", "cost_usd": 2.0, "stock": 12,
                "raw": {"active": True},
            }]
            self.assertEqual(ext_suppliers.sync_supplier_products(sid), (1, None))
        ep = ext_suppliers.get_ext_product(eid)
        self.assertEqual((int(ep["source_active"]), int(ep["shop_product_id"])), (1, pid))
        self.assertEqual(int(dict(database.get_product(pid))["is_active"]), 1)
        self.assertTrue(any(int(x["id"]) == pid for x in reseller_api._resellable_products()))

    def test_native_paid_supplier_order_revoked_before_submission_is_refunded(self):
        sid = ext_suppliers.add_supplier("Native refund catalog", "insta_api", "https://example.invalid", "test-key")
        eid = ext_suppliers.upsert_ext_product(
            sid, "remote-native-refund", "Native refund item", "desc", 2.0, 10,
            category_id=self.category_id, source_active=True,
        )
        ext_suppliers.update_ext_product(eid, synced_to_shop=1)
        pid = int(ext_suppliers.get_ext_product(eid)["shop_product_id"])
        user_id = 901002
        database.save_user(user_id, "", "Native customer")
        oid = database.create_order(
            user_id, "Native customer", pid, "Native refund item", 3.0,
            "wallet", "", 3.0, "USD", "product", qty=1,
        )
        database.update_order_status(oid, "paid")
        ext_suppliers.set_ext_product_source_active(eid, False, missing=True)

        class _Bot:
            def __init__(self): self.sent = []
            async def send_message(self, *args, **kwargs):
                self.sent.append((args, kwargs))

        asyncio.run(ext_suppliers.route_order_to_supplier(_Bot(), database.get_order(oid)))
        self.assertEqual(database.get_order(oid)["status"], "refunded")
        self.assertAlmostEqual(database.get_combined_points(user_id), points_from_usd(3.0))

    def test_hard_delete_removes_linked_product_from_reseller_catalog(self):
        sid = ext_suppliers.add_supplier("Delete catalog", "insta_api", "https://example.invalid", "test-key")
        eid = ext_suppliers.upsert_ext_product(
            sid, "remote-delete", "Delete item", "desc", 2.0, 10,
            category_id=self.category_id, source_active=True,
        )
        ext_suppliers.update_ext_product(eid, synced_to_shop=1)
        pid = int(ext_suppliers.get_ext_product(eid)["shop_product_id"])
        self.assertTrue(any(int(p["id"]) == pid for p in reseller_api._resellable_products()))
        result = database.delete_product_permanently(pid)
        self.assertEqual(result["products"], 1)
        self.assertIsNone(database.get_product(pid))
        ep = ext_suppliers.get_ext_product(eid)
        self.assertEqual((int(ep["shop_product_id"]), int(ep["synced_to_shop"])), (0, 0))
        self.assertFalse(any(int(p["id"]) == pid for p in reseller_api._resellable_products()))
        # Source refresh cannot recreate a deliberately hard-deleted row.
        ext_suppliers.update_ext_product(eid, stock=9)
        self.assertIsNone(database.get_product(pid))

    def test_revoked_before_submission_fails_and_refunds_without_upstream_call(self):
        sid = ext_suppliers.add_supplier("Fulfillment catalog", "insta_api", "https://example.invalid", "test-key")
        eid = ext_suppliers.upsert_ext_product(
            sid, "remote-refund", "Refund item", "desc", 2.0, 10,
            category_id=self.category_id, source_active=True,
        )
        ext_suppliers.update_ext_product(eid, synced_to_shop=1)
        pid, _ = ext_suppliers.mirror_ext_to_products(eid)
        user_id = 901001
        database.save_user(user_id, "", "Reseller")
        database.add_points(user_id, 100.0, description="test funds")
        self.assertTrue(database.deduct_points_if_enough(user_id, 10.0, event_id="v17061-debit"))
        oid = database.create_reseller_order(
            key_id=0, user_id=user_id, product_id=pid, product_name="Refund item",
            qty=1, usd_amount=1.0, points_amount=10.0, status="processing",
        )
        stale_product = dict(database.get_product(pid))
        ext_suppliers.set_ext_product_source_active(eid, False, missing=True)

        # This is the background pre-submission point. It reloads current state,
        # fails before adapter.create_order, and _apply_fulfill_result refunds.
        reseller_api._fulfill_async(stale_product, 1, user_id, oid, 10.0, "event", 1.0, {})
        order = database.get_reseller_order(oid)
        self.assertEqual(order["status"], "failed")
        self.assertAlmostEqual(database.get_combined_points(user_id), 100.0)

    def test_public_docs_are_neutral_and_callback_route_is_not_shadowed(self):
        description = reseller_api.app.description if reseller_api._FASTAPI_OK else ""
        docs = getattr(reseller_api, "_DOCS_HTML", "")
        public = (description + "\n" + docs).lower()
        self.assertNotIn("our suppliers", public)
        self.assertNotIn("supplier info", public)
        self.assertIn("premiumEmoji", docs)
        self.assertIn("stock-valid quantity tiers", description)

        bot_source = (ROOT / "bot.py").read_text()
        self.assertLess(bot_source.index('("^adm_refund_uid$"'), bot_source.index('("^adm_refund_",'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
