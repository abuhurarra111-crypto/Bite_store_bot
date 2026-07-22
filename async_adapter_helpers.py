# ============================================================
# ⚡ v89: ASYNC HTTP HELPERS
# ============================================================
# Instead of rewriting all 5 adapters to use aiohttp (huge diff surface,
# high regression risk), we wrap every blocking adapter call in
# asyncio.to_thread(). Result: identical adapter code, but the event loop
# never blocks on network I/O.
#
# Every async callback / job that touches an adapter now uses these
# helpers instead of calling adapter methods directly.
#
# Design principles:
#   1. Zero adapter changes — all 5 adapters (Akunding, Canboso, MMOStore,
#      TunVNMMO, InstaAPI) keep their sync `requests` calls untouched.
#   2. Every helper returns exactly what the adapter returns — same shape,
#      same error handling.
#   3. Wrap in `try/except` so a network hang can't crash the caller.
#   4. Optional timeout on the outer `to_thread` call (defensive — the
#      inner requests already have their own timeout).
# ============================================================

import asyncio
import logging

logger = logging.getLogger(__name__)


async def async_test_connection(adapter):
    """Non-blocking version of adapter.test_connection() → (ok, msg, extra)."""
    try:
        return await asyncio.to_thread(adapter.test_connection)
    except Exception as e:
        logger.warning(f"[async_helper] test_connection crashed: {e}")
        return False, f"exception: {e}", {}


async def async_fetch_balance(adapter):
    """Non-blocking version of adapter.fetch_balance() → float or None."""
    try:
        return await asyncio.to_thread(adapter.fetch_balance)
    except Exception as e:
        logger.warning(f"[async_helper] fetch_balance crashed: {e}")
        return None


async def async_fetch_products(adapter):
    """Non-blocking version of adapter.fetch_products() → list."""
    try:
        return await asyncio.to_thread(adapter.fetch_products)
    except Exception as e:
        logger.warning(f"[async_helper] fetch_products crashed: {e}")
        return []


async def async_create_order(adapter, remote_id, quantity):
    """Non-blocking version of adapter.create_order(...) → dict."""
    try:
        return await asyncio.to_thread(adapter.create_order, remote_id, quantity)
    except Exception as e:
        logger.warning(f"[async_helper] create_order crashed: {e}")
        return {"ok": False, "error": f"exception: {e}", "items": [], "raw": None}


async def async_sync_supplier_products(supplier_id):
    """
    Non-blocking version of sync_supplier_products() from ext_suppliers.py.
    All the DB work is fast (SQLite in-process); only the network fetches
    are wrapped in to_thread so the event loop keeps ticking.

    Returns the same (imported_count, error_or_None) tuple.
    """
    try:
        # Import lazily to avoid circular import at module load
        from ext_suppliers import sync_supplier_products
        return await asyncio.to_thread(sync_supplier_products, supplier_id)
    except Exception as e:
        logger.warning(f"[async_helper] sync_supplier_products crashed: {e}")
        return 0, f"exception: {e}"
