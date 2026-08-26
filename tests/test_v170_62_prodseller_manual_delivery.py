"""Offline regressions for ProdSeller server-error recovery and media delivery.

No real supplier request, customer, Telegram token, or provider credential is
used.  The tests exercise the owner-forwarded file + caption flow entirely with
in-memory Telegram-shaped objects and a temporary SQLite database.
"""

import asyncio
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOT_TOKEN", "test-token-not-real")
os.environ["ADMIN_ID"] = "424242"
_IMPORT_TEMP = tempfile.TemporaryDirectory()
os.environ["DB_PATH"] = str(Path(_IMPORT_TEMP.name) / "import.db")

import database
import ext_suppliers
import handlers_order

ADMIN_ID = 424242
BUYER_ID = 770062


class _Query:
    def __init__(self, data, user_id=ADMIN_ID):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return SimpleNamespace(message_id=len(self.edits))


class _Message:
    def __init__(self, text="", caption="", document=None):
        self.text = text
        self.caption = caption
        self.document = document
        self.photo = []
        self.video = None
        self.voice = None
        self.audio = None
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=len(self.replies))


class _Bot:
    def __init__(self):
        self.documents = []
        self.messages = []
        self.photos = []
        self.videos = []
        self.voices = []
        self.audio = []

    async def send_document(self, chat_id, document, **kwargs):
        self.documents.append((chat_id, document, kwargs))
        return SimpleNamespace(message_id=100 + len(self.documents))

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text, kwargs))
        return SimpleNamespace(message_id=200 + len(self.messages))

    async def send_photo(self, chat_id, photo, **kwargs):
        self.photos.append((chat_id, photo, kwargs))
        return SimpleNamespace(message_id=300 + len(self.photos))

    async def send_video(self, chat_id, video, **kwargs):
        self.videos.append((chat_id, video, kwargs))
        return SimpleNamespace(message_id=400 + len(self.videos))

    async def send_voice(self, chat_id, voice, **kwargs):
        self.voices.append((chat_id, voice, kwargs))
        return SimpleNamespace(message_id=500 + len(self.voices))

    async def send_audio(self, chat_id, audio, **kwargs):
        self.audio.append((chat_id, audio, kwargs))
        return SimpleNamespace(message_id=600 + len(self.audio))


class _Response500:
    status_code = 500
    text = "server error"

    def json(self):
        return {"error": "Plan executor error during findAndModify :: caused by :: Third argument to $slice must be positive: 0"}


class _JsonResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._body


class ProdSellerManualDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.tmp.name) / "shop.db")
        database._WAL_SETUP_DONE = False
        database.setup_database()
        ext_suppliers.ensure_ext_supplier_tables()
        ext_suppliers.ADMIN_ID = ADMIN_ID
        handlers_order.ADMIN_ID = ADMIN_ID
        ext_suppliers.ProdSellerAdapter._DETAIL_CACHE.clear()
        database.save_user(BUYER_ID, "media_buyer", "Media Buyer")
        cat = database.add_category("Supplier media recovery")
        self.pid = database.add_product(cat, "Notion Plus 12M", "test", 1.2, 0.9, 10)
        self.oid = database.create_order(BUYER_ID, "media_buyer", self.pid,
                                         "Notion Plus 12M", 1.2, method="wallet")
        self.reason = ("Plan executor error during findAndModify :: caused by :: "
                       "Third argument to $slice must be positive: 0")
        conn = database.get_connection()
        conn.execute("""UPDATE orders
                        SET status='supplier_retry_pending', supplier_failure_reason=?,
                            supplier_refund_due_at=?, supplier_retry_count=1
                        WHERE id=?""", (self.reason, time.time() + 300, self.oid))
        conn.commit()
        conn.close()
        self.bot = _Bot()
        self.context = SimpleNamespace(bot=self.bot, user_data={})

    def tearDown(self):
        self.tmp.cleanup()

    def _admin_callback_update(self, data):
        return SimpleNamespace(callback_query=_Query(data))

    def _media_update(self, caption, file_id="forwarded-doc-id"):
        msg = _Message(
            caption=caption,
            document=SimpleNamespace(file_id=file_id, file_name="notion_delivery.txt"),
        )
        return SimpleNamespace(effective_user=SimpleNamespace(id=ADMIN_ID), message=msg)

    def test_slice_error_retry_button_is_a_safe_chooser_not_a_purchase(self):
        update = self._admin_callback_update(f"supplier_retry_{self.oid}")
        with patch.object(ext_suppliers, "route_order_to_supplier", side_effect=AssertionError("must not buy")):
            asyncio.run(ext_suppliers.supplier_retry_delivery_callback(update, self.context))
        query = update.callback_query
        self.assertTrue(query.edits)
        message, kwargs = query.edits[-1]
        self.assertIn("Supplier API Server Error", message)
        self.assertIn("Deliver File + Caption", message)
        buttons = kwargs["reply_markup"].inline_keyboard
        callback_data = [button.callback_data for row in buttons for button in row]
        self.assertIn(f"supplier_manual_delivery_{self.oid}", callback_data)
        self.assertIn(f"supplier_force_retry_{self.oid}", callback_data)
        self.assertEqual(database.get_order(self.oid)["status"], "supplier_retry_pending")

    def test_forwarded_document_and_caption_deliver_in_one_customer_message_and_are_reusable(self):
        choose = self._admin_callback_update(f"supplier_manual_delivery_{self.oid}")
        asyncio.run(ext_suppliers.supplier_manual_delivery_callback(choose, self.context))
        self.assertEqual(self.context.user_data["supplier_manual_delivery_oid"], self.oid)
        self.assertEqual(database.get_order(self.oid)["status"], "supplier_manual_delivery_pending")

        source_caption = "notion_user@example.com:pass_word_[safe]\nUse this file with the included instructions."
        upload = self._media_update(source_caption)
        self.assertTrue(asyncio.run(ext_suppliers.supplier_manual_delivery_received(upload, self.context)))

        order = database.get_order(self.oid)
        self.assertEqual(order["status"], "delivered")
        self.assertEqual(order["delivery_file_id"], "forwarded-doc-id")
        self.assertNotIn("supplier_manual_delivery_oid", self.context.user_data)
        self.assertEqual(len(self.bot.documents), 1)
        chat_id, sent_file_id, kwargs = self.bot.documents[0]
        self.assertEqual((chat_id, sent_file_id), (BUYER_ID, "forwarded-doc-id"))
        self.assertEqual(kwargs["caption"], source_caption)
        self.assertNotIn("parse_mode", kwargs)  # credentials are sent literally
        self.assertIn(source_caption, order["delivery_content"])

        deliveries = database.get_order_deliveries(self.oid)
        self.assertEqual(len(deliveries), 1)
        self.assertEqual((deliveries[0]["kind"], deliveries[0]["file_id"], deliveries[0]["content"]),
                         ("document", "forwarded-doc-id", source_caption))

        # Customer's Order History resend must use this order's own file, not
        # mutate or use a product-wide static delivery file.
        resend_q = _Query(f"myord_resend_{self.oid}", user_id=BUYER_ID)
        asyncio.run(handlers_order.my_order_resend_callback(
            SimpleNamespace(callback_query=resend_q), self.context,
        ))
        self.assertEqual(len(self.bot.documents), 2)
        self.assertEqual(self.bot.documents[-1][1], "forwarded-doc-id")

    def test_manual_pending_order_cannot_be_claimed_for_another_supplier_purchase(self):
        ok, reason, _due = ext_suppliers._enter_supplier_manual_delivery(self.oid)
        self.assertTrue(ok)
        self.assertEqual(reason, "ready")
        claimed, why = ext_suppliers._claim_supplier_order_for_processing(self.oid)
        self.assertFalse(claimed)
        self.assertEqual(why, "supplier_manual_delivery_pending")

    def test_manual_pending_expiry_still_auto_refunds(self):
        ok, _reason, _due = ext_suppliers._enter_supplier_manual_delivery(self.oid)
        self.assertTrue(ok)
        conn = database.get_connection()
        conn.execute("UPDATE orders SET supplier_refund_due_at=? WHERE id=?", (time.time() - 1, self.oid))
        conn.commit()
        conn.close()

        asyncio.run(ext_suppliers.supplier_retry_refund_job(SimpleNamespace(bot=self.bot)))
        self.assertEqual(database.get_order(self.oid)["status"], "refunded")

    def test_prodseller_explicit_detail_zero_fails_closed_not_virtual_stock(self):
        adapter = ext_suppliers.ProdSellerAdapter("test-key", "https://provider.invalid/v1")
        listing = _JsonResponse({"products": [{
            "id": "notion-zero", "name": "Notion Plus 12M", "price": 0.9,
            "inStock": True,
        }]})
        detail = _JsonResponse({"id": "notion-zero", "stock": 0, "delivery": {"type": "instant"}})
        with patch.object(adapter, "_get", side_effect=[listing, detail]):
            products = adapter.fetch_products()
        self.assertEqual(products[0]["stock"], 0)

    def test_prodseller_explicit_custom_null_keeps_available_virtual_capacity_only(self):
        adapter = ext_suppliers.ProdSellerAdapter("test-key", "https://provider.invalid/v1")
        listing = _JsonResponse({"products": [{
            "id": "custom-null", "name": "Custom delivery", "price": 1.0,
            "inStock": True,
        }]})
        detail = _JsonResponse({"id": "custom-null", "stock": None, "delivery": {"type": "manual"}})
        with patch.object(adapter, "_get", side_effect=[listing, detail]):
            products = adapter.fetch_products()
        self.assertEqual(products[0]["stock"], 100)

    def test_prodseller_unknown_detail_fails_closed_not_virtual_stock(self):
        adapter = ext_suppliers.ProdSellerAdapter("test-key", "https://provider.invalid/v1")
        listing = _JsonResponse({"products": [{
            "id": "unreachable-detail", "name": "Unknown", "price": 1.0,
            "inStock": True,
        }]})
        with patch.object(adapter, "_get", side_effect=[listing, None]):
            products = adapter.fetch_products()
        self.assertEqual(products[0]["stock"], 0)

    def test_prodseller_500_preserves_status_and_provider_error(self):
        adapter = ext_suppliers.ProdSellerAdapter("test-key", "https://provider.invalid/v1")
        with patch.object(adapter, "_throttle"), patch.object(ext_suppliers.requests, "post", return_value=_Response500()):
            result = adapter.create_order("remote-notion", 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status_code"], 500)
        self.assertIn("findAndModify", result["error"])
        self.assertTrue(ext_suppliers._is_supplier_slice_server_error(result["error"]))


if __name__ == "__main__":
    unittest.main()
