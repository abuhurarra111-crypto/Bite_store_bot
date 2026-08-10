# ============================================================
# 🔗 v86: "Add via Connection String" admin flow
# ============================================================
# Pro UX: single paste-and-go — user pastes a `conn_...` string, we
# decode it, test the connection, add the supplier and offer import.
#
# Callbacks:
#   ext_sup_add_conn                  → open the paste screen (starts conv)
#   Text message (conv state)         → parse + test + save
#
# The supplier row is always saved with the anonymous display name
# `🔗 Instant API` and adapter=`insta_api`. Auto-sync, bulk sync,
# low-bal alerts, finance dashboard — all work automatically because
# they use the standard `list_suppliers()` + `get_adapter_for_supplier()`
# machinery.
# ============================================================

import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_ID
from insta_api_adapter import InstaAPIAdapter, parse_conn_string

logger = logging.getLogger(__name__)

CONN_STRING_STATE = 9287   # unique conversation state


DISPLAY_NAME = "🔗 Instant API"    # anonymous — hides real supplier brand


async def ext_sup_add_conn_callback(update, context):
    """Entry point — prompt admin to paste a `conn_...` string."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return -1
    await q.answer()
    text = (
        "🔗 *Add via Connection String*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Paste your `conn_...` connection string as your next message.\n\n"
        "The string encodes both the API key *and* the private endpoint URL — "
        "no separate fields needed.\n\n"
        "Example format:\n"
        "`conn_eyJrIjoic2tfLi4uIiwidSI6Imh0dHBzOi8vLi4uIn0=`\n\n"
        "_Send /cancel to abort._"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Cancel", callback_data="admin_suppliers")
    ]])
    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb,
                                   disable_web_page_preview=True)
    except Exception:
        await q.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=kb,
                                    disable_web_page_preview=True)
    return CONN_STRING_STATE


async def ext_sup_add_conn_received(update, context):
    """Admin pasted the string — decode, test, save."""
    if update.effective_user.id != ADMIN_ID:
        return -1
    msg = update.message
    raw = (msg.text or "").strip()

    ok, parsed = parse_conn_string(raw)
    if not ok:
        await msg.reply_text(
            f"❌ *Invalid connection string.*\n\n_Reason:_ `{parsed}`\n\n"
            f"Please paste a valid `conn_...` string, or send /cancel.",
            parse_mode="Markdown")
        return CONN_STRING_STATE

    api_key = parsed["key"]
    base_url = parsed["url"]

    await msg.reply_text(
        f"⏳ *Decoded successfully.*\n"
        f"🌐 Endpoint: `{base_url[:70]}`{'...' if len(base_url) > 70 else ''}\n"
        f"🔑 Key: `{api_key[:8]}...`\n\n"
        f"Testing connection…",
        parse_mode="Markdown", disable_web_page_preview=True)

    # Test the connection
    # 🆕 v89: async wrap — event loop keeps ticking during HTTP call
    ad = InstaAPIAdapter(api_key=api_key, base_url=base_url)
    from async_adapter_helpers import async_test_connection
    conn_ok, conn_msg, extra = await async_test_connection(ad)

    if not conn_ok:
        await msg.reply_text(
            f"❌ *Connection test FAILED.*\n\n"
            f"_Reason:_ {conn_msg}\n\n"
            f"Verify the connection string is fresh (not expired) and try again "
            f"from 📦 Suppliers → 🔗 Add via Connection String.",
            parse_mode="Markdown")
        return -1

    # Save the supplier (import locally to avoid circular import at module load)
    from ext_suppliers import add_supplier, update_supplier
    sid = add_supplier(
        name=DISPLAY_NAME,
        adapter="insta_api",
        base_url=base_url,
        api_key=api_key,
        docs_url="",
    )
    bal = float(extra.get("balance", 0) or 0)
    count = int(extra.get("count", 0) or 0)
    try:
        update_supplier(sid,
                         balance_usd=bal,
                         balance_updated_at=datetime.now().strftime(
                             "%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        logger.debug(f"[InstaAPI add] balance update fail: {e}")

    text = (
        f"✅ *Supplier added! (#{sid})*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏪 Name: {DISPLAY_NAME}\n"
        f"💰 Balance: `${bal:.2f}`\n"
        f"📦 Products available: *{count}*\n\n"
        f"_Tap below to import products or manage this supplier._"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Import All Products",
                               callback_data=f"ext_sup_import_all_{sid}")],
        [InlineKeyboardButton("⚙️ View Supplier",
                               callback_data=f"ext_sup_view_{sid}")],
        [InlineKeyboardButton("📦 All Suppliers",
                               callback_data="admin_suppliers")],
    ])
    await msg.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return -1


async def ext_sup_add_conn_cancel(update, context):
    try:
        await update.message.reply_text("❎ Cancelled — nothing saved.")
    except Exception:
        pass
    return -1
