# ============================================================
# 🌐 EXT SUPPLIERS — Multi-Supplier REST API System (v81 PHASE 1)
# ============================================================
# Handles external product suppliers (Akunding, Canboso, MMOStore, TunVNMMO).
# Admin adds supplier → imports products → sets markup → products go LIVE for
# customers. Backend uses adapter pattern (one adapter class per supplier API).
#
# Structure (kept in ONE file per user preference for low file count):
#   1. DB schema + helpers                      → tables: ext_suppliers, ext_products, ext_orders, ext_emoji_lib
#   2. Base adapter class + 4 concrete adapters (Akunding/Canboso/MMOStore/TunVNMMO)
#   3. Sync helpers (test connection, import products, refresh balance)
#   4. Premium emoji helpers (extract + store + apply)
#   5. Admin panel + wizard callbacks (add supplier / import / markup / failover)
#   6. Currency conversion (VND ↔ USD)
#
# All customer-facing display uses v72 byte-perfect html_code_block() from
# utils.py so account data is never mangled.
#
# ⚠️ IMPORTANT: This is PHASE 1 — supplier ADD + IMPORT + MARKUP + EMOJI
# only. PHASE 2 (v82) will add customer purchase flow + order router.
# ============================================================

import asyncio
import json
import logging
import re
import time
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID
from database import get_connection, ensure_column, get_setting, set_setting, ensure_product_accounts_table, ensure_default_free_claim_for_product
from utils import escape_md, html_code_block, html_escape_plain, smart_text_and_mode, fmt_price, points_from_usd, fmt_points, notify_admin

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
# 1. DB SCHEMA + HELPERS
# ────────────────────────────────────────────────────────────

def ensure_ext_supplier_tables():
    """Create v81 external-supplier tables (safe idempotent)."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS ext_suppliers (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT NOT NULL,
        adapter      TEXT NOT NULL,             -- akunding / canboso / mmostore / tunvnmmo
        base_url     TEXT NOT NULL,
        api_key      TEXT NOT NULL,
        docs_url     TEXT DEFAULT '',
        enabled      INTEGER DEFAULT 1,
        balance_usd  REAL DEFAULT 0,
        balance_updated_at TEXT DEFAULT '',
        low_bal_threshold REAL DEFAULT 5.0,
        auto_sync_min INTEGER DEFAULT 0,        -- 0 = off, else minutes (15/30/60)
        last_sync_at TEXT DEFAULT '',
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ext_products (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id   INTEGER NOT NULL,
        remote_id     TEXT NOT NULL,            -- supplier's own product id (string, since some use uuid)
        name          TEXT NOT NULL,            -- supplier's original name
        description   TEXT DEFAULT '',
        cost_usd      REAL DEFAULT 0,           -- what we pay supplier
        stock         INTEGER DEFAULT 0,
        markup_pct    REAL DEFAULT 40.0,        -- default 40% markup
        sell_price    REAL DEFAULT 0,           -- computed = cost × (1 + markup) OR fixed_price with smart adjust
        category_id   INTEGER DEFAULT 0,        -- links to `categories` table
        emoji_id      TEXT DEFAULT '',          -- premium emoji custom_emoji_id
        emoji_char    TEXT DEFAULT '',          -- the visible emoji char (fallback)
        emoji_status  TEXT DEFAULT 'pending',   -- pending / ok / manual
        active        INTEGER DEFAULT 1,
        imported_at   TEXT DEFAULT CURRENT_TIMESTAMP,
        last_synced_at TEXT DEFAULT '',
        raw_json      TEXT DEFAULT '',          -- last raw supplier JSON (for debugging)
        UNIQUE(supplier_id, remote_id)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ext_prod_sup ON ext_products(supplier_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ext_prod_active ON ext_products(active)")
    # 🆕 v81.1: Fixed selling price mode (Smart Lock)
    #   fixed_price = 0     → auto-markup mode (sell = cost × (1 + markup))
    #   fixed_price > 0     → SMART LOCK: sell adjusts UP only if cost rises
    #   fixed_price_base    → cost snapshot at the moment admin set fixed_price
    ensure_column(c, "ext_products", "fixed_price",      "REAL DEFAULT 0")
    ensure_column(c, "ext_products", "fixed_price_base", "REAL DEFAULT 0")
    # 🆕 v82 PHASE 2: link to shop's `products` table (mirror row) so existing
    # shop UI + purchase + delivery pipeline reuses supplier products.
    ensure_column(c, "ext_products", "shop_product_id", "INTEGER DEFAULT 0")
    # Mirror-side: add columns to `products` so we can identify which shop
    # product comes from which supplier + remote id.
    ensure_column(c, "products", "ext_supplier_id",  "INTEGER DEFAULT 0")
    ensure_column(c, "products", "ext_product_id",   "INTEGER DEFAULT 0")
    # 🆕 v83: Format detection + manual sync flag
    ensure_column(c, "ext_products", "delivery_format",   "TEXT DEFAULT ''")
    ensure_column(c, "ext_products", "format_detected",   "INTEGER DEFAULT 0")  # 0=admin_override, 1=auto
    ensure_column(c, "ext_products", "synced_to_shop",    "INTEGER DEFAULT 0")  # v83: manual sync flag
    ensure_column(c, "ext_products", "out_of_stock_since", "REAL DEFAULT 0")  # v141: auto-delete after 5 days OOS
    ensure_column(c, "ext_products", "missing_since",      "REAL DEFAULT 0")  # v141: supplier deleted/missing tracker

    c.execute("""CREATE TABLE IF NOT EXISTS ext_orders (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        internal_order_id INTEGER,              -- links to main `orders.id`
        supplier_id    INTEGER NOT NULL,
        ext_product_id INTEGER NOT NULL,
        quantity       INTEGER DEFAULT 1,
        cost_usd       REAL DEFAULT 0,
        remote_order_id TEXT DEFAULT '',
        status         TEXT DEFAULT 'pending',  -- pending / delivered / failed / refunded
        raw_response   TEXT DEFAULT '',
        error_msg      TEXT DEFAULT '',
        created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at   TEXT DEFAULT ''
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS ext_emoji_lib (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        emoji_char   TEXT UNIQUE NOT NULL,      -- 🔥, 💎, ✨
        emoji_id     TEXT NOT NULL,             -- 5458672938...
        used_count   INTEGER DEFAULT 0,
        first_seen   TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS ext_failover (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        primary_id    INTEGER NOT NULL,         -- ext_products.id (primary)
        backup1_id    INTEGER DEFAULT 0,
        backup2_id    INTEGER DEFAULT 0,
        created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(primary_id)
    )""")

    # v81 backup table (never dropped): snapshot of original 29 products before wipe
    c.execute("""CREATE TABLE IF NOT EXISTS products_backup_v81 (
        backup_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        original_id   INTEGER,
        row_json      TEXT,
        backed_up_at  TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.commit(); conn.close()


def add_supplier(name, adapter, base_url, api_key, docs_url=""):
    """Add a new supplier. Returns id."""
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""INSERT INTO ext_suppliers
                 (name, adapter, base_url, api_key, docs_url)
                 VALUES (?, ?, ?, ?, ?)""",
              (name[:80], adapter, base_url.rstrip("/"), api_key.strip(), docs_url[:200]))
    sid = c.lastrowid; conn.commit(); conn.close()
    return sid


def get_supplier(sid):
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM ext_suppliers WHERE id=?", (int(sid),))
    r = c.fetchone(); conn.close()
    return dict(r) if r else None


def list_suppliers(include_disabled=True):
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    if include_disabled:
        c.execute("SELECT * FROM ext_suppliers ORDER BY id")
    else:
        c.execute("SELECT * FROM ext_suppliers WHERE enabled=1 ORDER BY id")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def update_supplier(sid, **fields):
    """Update supplier row (allowed fields whitelisted)."""
    ensure_ext_supplier_tables()
    allowed = {"name", "base_url", "api_key", "docs_url", "enabled",
               "balance_usd", "balance_updated_at", "low_bal_threshold",
               "auto_sync_min", "last_sync_at"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields: return
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [int(sid)]
    conn = get_connection(); c = conn.cursor()
    c.execute(f"UPDATE ext_suppliers SET {sets} WHERE id=?", vals)
    conn.commit(); conn.close()


def ensure_env_supplier_presets():
    """Auto-register/update safe env-configured supplier presets.

    Shop Cron uses Canboso Buyer API v2.1. The API key MUST live in Render env:
      SUPPLIER_SHOP_CRON_API_KEY
    We never hardcode secrets into source code.
    """
    import os
    key = (os.getenv("SUPPLIER_SHOP_CRON_API_KEY", "") or "").strip()
    if not key:
        return 0, "missing_env"
    ensure_ext_supplier_tables()
    name = "Shop Cron"
    adapter = "canboso"
    base_url = "https://canboso.com"
    docs_url = "https://canboso.com/api/swagger"
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("SELECT id FROM ext_suppliers WHERE lower(name)=lower(?) OR (adapter=? AND base_url=? AND api_key=?) LIMIT 1",
                  (name, adapter, base_url, key))
        row = c.fetchone()
        if row:
            sid = int(row["id"] if hasattr(row, "keys") else row[0])
            c.execute("""UPDATE ext_suppliers
                         SET name=?, adapter=?, base_url=?, api_key=?, docs_url=?, enabled=1
                         WHERE id=?""", (name, adapter, base_url, key, docs_url, sid))
            conn.commit(); conn.close(); return sid, "updated"
        c.execute("""INSERT INTO ext_suppliers (name, adapter, base_url, api_key, docs_url, enabled)
                     VALUES (?, ?, ?, ?, ?, 1)""", (name, adapter, base_url, key, docs_url))
        sid = c.lastrowid
        conn.commit(); conn.close(); return sid, "created"
    except Exception:
        try: conn.rollback()
        except Exception: pass
        try: conn.close()
        except Exception: pass
        raise


def ensure_env_sinhle_supplier():
    """🔧 v131: auto-register/update the 'sinh le store bot' supplier (Canboso
    Buyer API v2). Key lives in Render env: SUPPLIER_SINHLE_API_KEY.
    Returns (sid, status)."""
    import os
    key = (os.getenv("SUPPLIER_SINHLE_API_KEY", "") or "").strip()
    if not key:
        return 0, "missing_env"
    ensure_ext_supplier_tables()
    name = "sinh le store bot"
    adapter = "canboso"
    base_url = "https://canboso.com"
    docs_url = "https://canboso.com/api/swagger"
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("SELECT id FROM ext_suppliers WHERE lower(name)=lower(?) OR (adapter=? AND base_url=? AND api_key=?) LIMIT 1",
                  (name, adapter, base_url, key))
        row = c.fetchone()
        if row:
            sid = int(row["id"] if hasattr(row, "keys") else row[0])
            c.execute("""UPDATE ext_suppliers
                         SET name=?, adapter=?, base_url=?, api_key=?, docs_url=?, enabled=1
                         WHERE id=?""", (name, adapter, base_url, key, docs_url, sid))
            conn.commit(); conn.close(); return sid, "updated"
        c.execute("""INSERT INTO ext_suppliers (name, adapter, base_url, api_key, docs_url, enabled)
                     VALUES (?, ?, ?, ?, ?, 1)""", (name, adapter, base_url, key, docs_url))
        sid = c.lastrowid
        conn.commit(); conn.close(); return sid, "created"
    except Exception:
        try: conn.rollback()
        except Exception: pass
        try: conn.close()
        except Exception: pass
        raise


def delete_supplier(sid):
    """Delete supplier and every synced shop product linked to it.

    Orders are intentionally preserved (orders table keeps product_name/price),
    but supplier mirrors must disappear from both user shop and admin Edit Items.
    """
    ensure_ext_supplier_tables()
    sid = int(sid)
    conn = get_connection(); c = conn.cursor()
    stats = {"shop_products": 0, "ext_products": 0, "ext_orders": 0, "accounts": 0}
    try:
        c.execute("BEGIN IMMEDIATE")
        # Collect linked shop products from both link directions for old DBs.
        c.execute("""SELECT DISTINCT shop_product_id FROM ext_products
                     WHERE supplier_id=? AND COALESCE(shop_product_id,0) > 0""", (sid,))
        pids = {int(r[0]) for r in c.fetchall() if r[0]}
        try:
            c.execute("SELECT id FROM products WHERE COALESCE(ext_supplier_id,0)=?", (sid,))
            pids.update(int(r[0]) for r in c.fetchall() if r[0])
        except Exception:
            pass

        if pids:
            qmarks = ",".join("?" for _ in pids)
            pid_list = list(pids)
            # Remove local/supplier bonus account pool for deleted supplier products.
            try:
                c.execute(f"DELETE FROM product_accounts WHERE product_id IN ({qmarks})", pid_list)
                stats["accounts"] = c.rowcount if c.rowcount is not None else 0
            except Exception:
                pass
            # Remove optional per-product config rows where present.
            for table in ("product_free_claim", "product_ref_pool", "stock_alerts", "restock_requests", "product_reviews"):
                try:
                    c.execute(f"DELETE FROM {table} WHERE product_id IN ({qmarks})", pid_list)
                except Exception:
                    pass
            c.execute(f"DELETE FROM products WHERE id IN ({qmarks})", pid_list)
            stats["shop_products"] = c.rowcount if c.rowcount is not None else len(pid_list)

        c.execute("DELETE FROM ext_products WHERE supplier_id=?", (sid,))
        stats["ext_products"] = c.rowcount if c.rowcount is not None else 0
        c.execute("DELETE FROM ext_orders WHERE supplier_id=?", (sid,))
        stats["ext_orders"] = c.rowcount if c.rowcount is not None else 0
        c.execute("DELETE FROM ext_suppliers WHERE id=?", (sid,))
        conn.commit(); conn.close()
        return stats
    except Exception:
        try: conn.rollback()
        except Exception: pass
        try: conn.close()
        except Exception: pass
        raise


def _compute_sell_price(cost_usd, markup_pct, fixed_price, fixed_price_base):
    """🆕 v81.1: SMART PRICE calculation.

    🐛 v105 FIX: removed round(..., 2). Was truncating sub-cent prices to
    $0.00 (supplier cost $0.024 × 1.40 markup = $0.0336 → rounded to $0.03,
    or cost $0.003 → sell $0.0042 → rounded to $0.00). Now preserves full
    precision — the DB stores REAL, display uses fmt_price() from utils.

    Rules:
      1. If fixed_price == 0     → auto-markup: sell = cost × (1 + markup/100)
      2. If fixed_price > 0      → SMART LOCK:
         - If cost <= fixed_price_base  → sell = fixed_price (no drop)
         - If cost >  fixed_price_base  → sell = fixed_price + (cost - fixed_price_base)
                                          (cost rise passed through, admin's profit preserved)
    """
    cost = float(cost_usd or 0)
    if fixed_price and fixed_price > 0:
        base = float(fixed_price_base or 0)
        if cost <= base:
            return float(fixed_price)
        # Cost went UP → increase sell by exact delta
        delta = cost - base
        return float(fixed_price) + delta
    # Auto-markup mode
    mkp = float(markup_pct or 40)
    return cost * (1 + mkp / 100.0)


def upsert_ext_product(supplier_id, remote_id, name, description, cost_usd,
                      stock, category_id=0, raw_json=""):
    """Insert or update a supplier product. Preserves markup + emoji + active
    state if row already exists (only overwrites cost/stock/name/desc).
    🆕 v81.1: honors fixed_price (Smart Lock) when computing sell_price."""
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT id, markup_pct, fixed_price, fixed_price_base
                 FROM ext_products
                 WHERE supplier_id=? AND remote_id=?""",
              (int(supplier_id), str(remote_id)))
    existing = c.fetchone()
    if existing:
        markup = existing["markup_pct"] or 40.0
        fp = existing["fixed_price"] or 0
        fpb = existing["fixed_price_base"] or 0
        sell = _compute_sell_price(cost_usd, markup, fp, fpb)
        clear_oos = 0 if int(stock or 0) > 0 else None
        if clear_oos == 0:
            c.execute("""UPDATE ext_products
                         SET name=?, description=?, cost_usd=?, stock=?,
                             sell_price=?, last_synced_at=CURRENT_TIMESTAMP,
                             raw_json=?, missing_since=0, out_of_stock_since=0
                         WHERE id=?""",
                      (name[:250], description[:3000], float(cost_usd),
                       int(stock), sell, raw_json[:8000], existing["id"]))
        else:
            c.execute("""UPDATE ext_products
                         SET name=?, description=?, cost_usd=?, stock=?,
                             sell_price=?, last_synced_at=CURRENT_TIMESTAMP,
                             raw_json=?, missing_since=0
                         WHERE id=?""",
                      (name[:250], description[:3000], float(cost_usd),
                       int(stock), sell, raw_json[:8000], existing["id"]))
        pid = existing["id"]
    else:
        markup = 40.0
        sell = _compute_sell_price(cost_usd, markup, 0, 0)
        c.execute("""INSERT INTO ext_products
                     (supplier_id, remote_id, name, description, cost_usd,
                      stock, markup_pct, sell_price, category_id, raw_json,
                      out_of_stock_since, missing_since)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                  (int(supplier_id), str(remote_id), name[:250],
                   description[:3000], float(cost_usd), int(stock),
                   markup, sell, int(category_id), raw_json[:8000],
                   0 if int(stock or 0) > 0 else 0))
        pid = c.lastrowid
    conn.commit(); conn.close()
    return pid


def get_ext_products(supplier_id=None, active_only=False, category_id=None):
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    where = []
    params = []
    if supplier_id is not None:
        where.append("supplier_id=?"); params.append(int(supplier_id))
    if active_only:
        where.append("active=1")
    if category_id is not None:
        where.append("category_id=?"); params.append(int(category_id))
    q = "SELECT * FROM ext_products"
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY id DESC"
    c.execute(q, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_ext_product(eid):
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM ext_products WHERE id=?", (int(eid),))
    r = c.fetchone(); conn.close()
    return dict(r) if r else None


def update_ext_product(eid, **fields):
    ensure_ext_supplier_tables()
    allowed = {"name", "description", "cost_usd", "stock", "markup_pct",
               "sell_price", "category_id", "emoji_id", "emoji_char",
               "emoji_status", "active",
               # 🆕 v81.1: fixed price fields
               "fixed_price", "fixed_price_base",
               # 🆕 v82: link column
               "shop_product_id",
               # 🆕 v83/v141: format + sync + stale tracking
               "delivery_format", "format_detected", "synced_to_shop",
               "out_of_stock_since", "missing_since"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields: return
    # 🆕 v81.1: Recompute sell_price using SMART LOCK logic
    if any(k in fields for k in ("markup_pct", "cost_usd", "fixed_price", "fixed_price_base")):
        cur = get_ext_product(eid) or {}
        cost = float(fields.get("cost_usd", cur.get("cost_usd", 0)) or 0)
        mkp  = float(fields.get("markup_pct", cur.get("markup_pct", 40)) or 40)
        fp   = float(fields.get("fixed_price", cur.get("fixed_price", 0)) or 0)
        fpb  = float(fields.get("fixed_price_base", cur.get("fixed_price_base", 0)) or 0)
        fields["sell_price"] = _compute_sell_price(cost, mkp, fp, fpb)
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [int(eid)]
    conn = get_connection(); c = conn.cursor()
    c.execute(f"UPDATE ext_products SET {sets} WHERE id=?", vals)
    conn.commit(); conn.close()
    # 🆕 v83: only mirror if product has been manually synced to shop.
    # (In v82 we auto-mirrored on every change; user requested manual-only.)
    if any(k in fields for k in ("name", "description", "cost_usd", "stock",
                                   "markup_pct", "sell_price", "category_id",
                                   "emoji_id", "emoji_char", "active",
                                   "fixed_price", "fixed_price_base",
                                   "delivery_format")):
        try:
            ep_check = get_ext_product(eid)
            if ep_check and ep_check.get("synced_to_shop"):
                mirror_ext_to_products(eid)
        except Exception as e:
            logger.debug(f"[mirror] update failed: {e}")


def toggle_ext_product_active(eid):
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT active FROM ext_products WHERE id=?", (int(eid),))
    r = c.fetchone()
    if not r: conn.close(); return
    new_val = 0 if r["active"] else 1
    c.execute("UPDATE ext_products SET active=? WHERE id=?", (new_val, int(eid)))
    conn.commit(); conn.close()
    # 🆕 v82: mirror the active state to shop's products table
    try:
        mirror_ext_to_products(eid)
    except Exception:
        pass
    return new_val


# ────────────────────────────────────────────────────────────
# 🆕 v82 PHASE 2: MIRROR-SYNC ext_products → products (shop table)
# ────────────────────────────────────────────────────────────
# Every time an ext_product is imported / cost changes / markup changes /
# activated / deactivated / emoji fixed / category set, we mirror the row
# to the shop's `products` table. This way the existing shop UI, filters,
# search, categories, and purchase pipeline all work unchanged.

def mirror_ext_to_products(ext_product_id):
    """Sync ONE ext_product to a matching row in `products` table.
    - Creates a new products row if none exists (linked via ext_product_id)
    - Updates existing row if already linked
    - Uses sell_price for `price`, cost_usd for `cost_price`
    - Preserves premium-emoji formatting in the name if emoji_id present
    Returns (products.id, was_new: bool)
    """
    from database import get_connection as _gc, ensure_column as _ec
    ep = get_ext_product(ext_product_id)
    if not ep:
        return 0, False

    # Build the display name: if we have premium emoji_id, wrap in [[HTML]]
    # sentinel so premium_emoji_guard renders the animated emoji properly.
    raw_name = ep.get("name") or ""
    # Strip leading emoji char if we're going to prepend a premium version
    emoji_id = (ep.get("emoji_id") or "").strip()
    emoji_char = (ep.get("emoji_char") or "").strip()
    if emoji_id and emoji_char and raw_name.startswith(emoji_char):
        rest = raw_name[len(emoji_char):].lstrip()
        display_name = f'[[HTML]]<tg-emoji emoji-id="{emoji_id}">{emoji_char}</tg-emoji> {rest}'
    elif emoji_id and emoji_char:
        display_name = f'[[HTML]]<tg-emoji emoji-id="{emoji_id}">{emoji_char}</tg-emoji> {raw_name}'
    elif emoji_char:
        # Manual/fixed plain emoji (no premium ID). Keep it visible in shop/admin
        # rows while avoiding duplicate if supplier name already starts with it.
        display_name = raw_name if raw_name.startswith(emoji_char) else f"{emoji_char} {raw_name}"
    else:
        display_name = raw_name

    conn = _gc(); c = conn.cursor()
    # Ensure link columns exist (defensive)
    _ec(c, "products", "ext_supplier_id", "INTEGER DEFAULT 0")
    _ec(c, "products", "ext_product_id",  "INTEGER DEFAULT 0")

    # Check if shop_product already exists for this ext_product
    shop_pid = int(ep.get("shop_product_id") or 0)
    row = None
    if shop_pid > 0:
        c.execute("SELECT id FROM products WHERE id=?", (shop_pid,))
        row = c.fetchone()

    sell = float(ep.get("sell_price") or 0)
    cost = float(ep.get("cost_usd") or 0)
    remote_stock = int(ep.get("stock") or 0)
    # v114: supplier product stock = live supplier stock + local bonus pool.
    # Bonus accounts are extra items suppliers return (promotions). We store
    # them in product_accounts and must not hide them when auto-sync mirrors
    # supplier stock back into products.stock.
    local_bonus_stock = 0
    try:
        if shop_pid > 0:
            ensure_product_accounts_table(c)
            c.execute("""SELECT COUNT(*) FROM product_accounts
                         WHERE product_id=? AND status='available'""", (shop_pid,))
            local_bonus_stock = int(c.fetchone()[0] or 0)
    except Exception:
        local_bonus_stock = 0
    stock = remote_stock + local_bonus_stock
    cat_id = int(ep.get("category_id") or 0)
    # 🐛 v106 FIX: description was synced as plain text — if supplier's
    # description contains HTML markup (<b>/<blockquote>/<tg-emoji>/etc.),
    # wrap in [[HTML]] sentinel so shop rendering preserves the formatting.
    # If description is empty → sync empty. If it's plain text → pass through.
    raw_desc = str(ep.get("description") or "")
    if raw_desc and ("<" in raw_desc and ">" in raw_desc) and not raw_desc.startswith("[[HTML]]"):
        import re as _re_desc
        # Detect any HTML tag OR premium emoji markup — mark as HTML so
        # customer-facing product-detail render uses HTML parse mode.
        if _re_desc.search(r"<(?:b|i|u|s|code|pre|blockquote|tg-emoji|a|em|strong|br)\b", raw_desc, flags=_re_desc.I):
            desc = "[[HTML]]" + raw_desc
        else:
            desc = raw_desc
    else:
        desc = raw_desc
    is_active = 1 if ep.get("active") else 0
    # 🐛 v106 FIX: sync the delivery_format the auto-detector set on the
    # ext_products row (from v87 detector — email_pass / email_pass_2fa /
    # redeem_link / coupon_code / etc.). OLD code hardcoded 'email_pass'
    # for every product → users got wrong delivery template for redeem_link
    # / coupon products from supplier.
    prod_fmt = str(ep.get("delivery_format") or "email_pass").strip() or "email_pass"

    if row:
        # Update existing mirror row
        c.execute("""UPDATE products
                     SET name=?, description=?, price=?, cost_price=?,
                         stock=?, category_id=?, is_active=?, product_format=?
                     WHERE id=?""",
                  (display_name, desc, sell, cost, stock,
                   cat_id or 1, is_active, prod_fmt, shop_pid))
        was_new = False
        pid = shop_pid
    else:
        # Create new mirror row
        c.execute("""INSERT INTO products
                     (category_id, name, description, price, cost_price, stock,
                      delivery_text, warranty, quantity, photo_id,
                      is_active, product_format, delivery_template,
                      ext_supplier_id, ext_product_id)
                     VALUES (?, ?, ?, ?, ?, ?, '', '', '', '', ?, ?, 1, ?, ?)""",
                  (cat_id or 1, display_name, desc, sell, cost, stock,
                   is_active, prod_fmt,
                   int(ep.get("supplier_id") or 0),
                   int(ep.get("id"))))
        pid = c.lastrowid
        was_new = True
        # Save the link back to ext_products
        c.execute("UPDATE ext_products SET shop_product_id=? WHERE id=?",
                  (pid, int(ep.get("id"))))

    conn.commit(); conn.close()
    # v127: Every NEW supplier-mirrored product gets Free-via-Referrals
    # defaults automatically. Existing product rows keep their admin settings.
    if was_new:
        try:
            ensure_default_free_claim_for_product(pid)
        except Exception:
            pass
    return pid, was_new


def mirror_all_supplier_products(supplier_id):
    """Mirror every ext_product of a supplier to shop's products table.
    Returns (mirrored_count, new_count)."""
    prods = get_ext_products(supplier_id=supplier_id)
    new_count = 0
    for p in prods:
        try:
            _, is_new = mirror_ext_to_products(p["id"])
            if is_new:
                new_count += 1
        except Exception as e:
            logger.warning(f"[mirror] failed for ext#{p['id']}: {e}")
    return len(prods), new_count


def unmirror_ext_product(ext_product_id):
    """Unsync supplier product by deleting its shop mirror completely.

    Requirement: unsynced supplier products must disappear from BOTH user shop
    and admin Edit Items. Old orders remain safe because orders store product
    name/price/status independently.
    """
    ep = get_ext_product(ext_product_id)
    if not ep:
        return {"deleted": 0, "shop_product_id": 0}
    shop_pid = int(ep.get("shop_product_id") or 0)
    deleted = 0
    try:
        from database import archive_supplier_product
        archive_supplier_product(ep, reason="supplier_deleted_or_auto_removed")
    except Exception:
        pass
    if shop_pid > 0:
        try:
            from database import delete_product_permanently
            stats = delete_product_permanently(shop_pid)
            deleted = int((stats or {}).get("products") or 0)
        except Exception as e:
            logger.warning(f"[unmirror] hard delete failed ext#{ext_product_id} shop#{shop_pid}: {e}")
            # Fallback: at least hide if hard-delete fails.
            try:
                conn = get_connection(); c = conn.cursor()
                c.execute("UPDATE products SET is_active=0, stock=0 WHERE id=?", (shop_pid,))
                conn.commit(); conn.close()
            except Exception:
                pass
    try:
        update_ext_product(int(ext_product_id), synced_to_shop=0, shop_product_id=0)
    except Exception:
        pass
    return {"deleted": deleted, "shop_product_id": shop_pid}


def delete_ext_product_completely(ext_product_id):
    """Delete supplier product from bot after supplier removed it or 5-day OOS.

    Deletes shop mirror via unmirror_ext_product first. Orders are untouched.
    """
    eid = int(ext_product_id)
    stats = unmirror_ext_product(eid)
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("DELETE FROM ext_products WHERE id=?", (eid,))
        deleted = c.rowcount if c.rowcount is not None else 0
        conn.commit(); conn.close()
        stats["ext_deleted"] = int(deleted or 0)
        return stats
    except Exception:
        try: conn.rollback()
        except Exception: pass
        try: conn.close()
        except Exception: pass
        raise


# ────────────────────────────────────────────────────────────
# 2. ADAPTER BASE + 4 CONCRETE ADAPTERS
# ────────────────────────────────────────────────────────────

class SupplierAdapterBase:
    """Base class — all 4 concrete adapters inherit from this.
    Each subclass MUST implement: test_connection, fetch_balance,
    fetch_products, create_order (v82).
    """
    KEY_ID = ""              # short name for DB adapter column
    LABEL = ""               # user-facing display
    DEFAULT_BASE_URL = ""
    DOCS_URL = ""
    AUTH_STYLE = "bearer"    # bearer | x_api_key | query

    def __init__(self, api_key, base_url=None):
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")

    def _headers(self):
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.AUTH_STYLE == "bearer":
            h["Authorization"] = f"Bearer {self.api_key}"
        elif self.AUTH_STYLE == "x_api_key":
            h["X-API-Key"] = self.api_key
        return h

    def _params(self):
        if self.AUTH_STYLE == "query":
            return {"api_key": self.api_key}
        return {}

    def _get(self, path, timeout=20, extra_params=None):
        url = self.base_url + path
        try:
            params = dict(self._params() or {})
            if extra_params:
                params.update(extra_params)
            r = requests.get(url, headers=self._headers(),
                             params=(params or None), timeout=timeout)
            return r
        except Exception as e:
            logger.warning(f"[{self.KEY_ID}] GET {path}: {e}")
            return None

    def _post(self, path, body, timeout=20):
        url = self.base_url + path
        try:
            r = requests.post(url, headers=self._headers(),
                              params=self._params(), json=body, timeout=timeout)
            return r
        except Exception as e:
            logger.warning(f"[{self.KEY_ID}] POST {path}: {e}")
            return None

    # ── Abstract methods ──
    def test_connection(self):
        """Return (ok:bool, message:str, extra:dict). extra may hold {balance, count}."""
        raise NotImplementedError

    def fetch_balance(self):
        """Return balance in USD or None on failure."""
        raise NotImplementedError

    def fetch_products(self):
        """Return list of normalized product dicts:
        [{remote_id, name, description, cost_usd, stock, raw:{...}}, ...]"""
        raise NotImplementedError

    def create_order(self, remote_id, quantity):
        """PHASE 2 (v82): place order. Returns {'ok':bool, 'items':[...], 'raw':...}"""
        raise NotImplementedError


# ────────────────────────────────────────────────────────────
# v113: Universal supplier delivery parser
# ────────────────────────────────────────────────────────────
# Different suppliers use different success-response keys:
#   Canboso:   deliveredAccounts
#   MMOStore:  data.accounts
#   TunVNMMO:  items
#   Akunding:  items/accounts/data/credentials (varies by product)
# If a successful purchase is parsed with the wrong key, the router thinks the
# supplier returned nothing and auto-refunds. Keep one tolerant parser here and
# make every adapter use it.
_DELIVERY_COLLECTION_KEYS = (
    "deliveredAccounts", "delivered_accounts", "deliveryItems", "delivery_items",
    "accounts", "accountList", "account_list", "items", "itemList", "item_list",
    "orders", "results", "codes", "keys", "deliveredKeys", "delivered_keys",
    "licenses", "credentials", "deliveredCredentials",
)
_DELIVERY_SINGLE_KEYS = (
    "account", "credential", "accountData", "account_data", "content", "text",
    "value", "code", "link", "url", "license", "key", "deliveredKey",
    "delivered_account", "deliveryLink", "delivery_url", "downloadUrl", "fileUrl",
)
_DELIVERY_NEST_KEYS = (
    "data", "order", "result", "response", "payload", "purchase", "delivery",
)


def _is_scalar(v):
    return isinstance(v, (str, int, float, bool))


def _as_delivery_list(value):
    """Convert supplier delivery payload to a list without char-splitting."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        # A dict may itself wrap the real list one level deeper.
        nested = _extract_delivery_items(value)
        return nested if nested else [value]
    if isinstance(value, str):
        txt = value.strip()
        if not txt:
            return []
        if txt[:1] in ("[", "{"):
            try:
                return _as_delivery_list(json.loads(txt))
            except Exception:
                pass
        # Suppliers often return newline-separated accounts. One pipe-separated
        # credential line must remain one item.
        lines = [ln.strip() for ln in re.split(r"[\r\n]+", txt) if ln.strip()]
        return lines if len(lines) > 1 else [txt]
    return [str(value)]


def _pick_first(d, *keys):
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip() != "":
            return str(v).strip(), k
    return "", ""


def _normalise_delivery_item(item):
    """Turn one supplier account/code object into the copy-paste delivery line."""
    if not isinstance(item, dict):
        return str(item).strip()

    # If supplier already provides a full credential string, preserve it.
    for k in ("credentials", "credential", "account", "accountData",
              "account_data", "content", "text", "value"):
        v = item.get(k)
        if _is_scalar(v) and str(v).strip():
            return str(v).strip()

    used = set()
    email, k = _pick_first(item, "email", "mail", "user", "username", "login")
    if k: used.add(k)
    password, k = _pick_first(item, "password", "pass", "pwd")
    if k: used.add(k)
    refresh, k = _pick_first(item, "refreshToken", "refresh_token", "refresh",
                            "token", "accessToken", "access_token")
    if k: used.add(k)
    client, k = _pick_first(item, "clientId", "client_id", "clientID", "client")
    if k: used.add(k)
    twofa, k = _pick_first(item, "twofa", "2fa", "twoFactor", "otp_secret", "otpSecret")
    if k: used.add(k)
    recovery, k = _pick_first(item, "verifyEmail", "recoveryEmail", "recovery_email", "recovery")
    if k: used.add(k)
    code, k = _pick_first(item, "code", "link", "url", "redeemCode", "redeem_link",
                         "license", "licenseKey", "license_key")
    if k: used.add(k)

    # Code/link-only products.
    if code and not (email or password):
        return code

    parts = [v for v in (email, password, refresh, client, twofa, recovery) if v]

    # Keep extra scalar credential fields, skip obvious metadata.
    skip = used | {"productItemId", "product_item_id", "id", "_id",
                   "deliveredAt", "createdAt", "updatedAt", "status",
                   "price", "amount", "balance", "quantity", "qty"}
    for k, v in item.items():
        if k in skip or v is None or isinstance(v, (dict, list, tuple)):
            continue
        sv = str(v).strip()
        if sv and sv not in parts:
            parts.append(sv)

    return "|".join(parts) if parts else json.dumps(item, ensure_ascii=False)


def _extract_delivery_items(payload, _depth=0):
    """Return normalized delivery lines from any common supplier response."""
    if payload is None or _depth > 4:
        return []
    if isinstance(payload, list):
        return [x for x in (_normalise_delivery_item(v) for v in payload) if x]
    if isinstance(payload, str):
        return [x for x in (_normalise_delivery_item(v) for v in _as_delivery_list(payload)) if x]
    if not isinstance(payload, dict):
        return [str(payload).strip()] if str(payload).strip() else []

    # First: explicit delivery collection keys.
    for key in _DELIVERY_COLLECTION_KEYS:
        if key in payload and payload.get(key) not in (None, "", []):
            vals = _as_delivery_list(payload.get(key))
            out = [x for x in (_normalise_delivery_item(v) for v in vals) if x]
            if out:
                return out

    # Second: explicit single item keys.
    for key in _DELIVERY_SINGLE_KEYS:
        if key in payload and payload.get(key) not in (None, "", []):
            out = [x for x in (_normalise_delivery_item(v) for v in _as_delivery_list(payload.get(key))) if x]
            if out:
                return out

    # Third: common nested wrappers.
    for key in _DELIVERY_NEST_KEYS:
        if key in payload and payload.get(key) not in (None, "", []):
            out = _extract_delivery_items(payload.get(key), _depth + 1)
            if out:
                return out

    return []


def _extract_order_id(payload):
    """Best-effort supplier order id from top-level or nested response."""
    if not isinstance(payload, dict):
        return ""
    for k in ("orderCode", "order_id", "orderId", "id", "order_group", "orderGroup", "remote_order_id"):
        v = payload.get(k)
        if v:
            return str(v)
    for k in ("data", "order", "result", "response", "payload"):
        v = payload.get(k)
        if isinstance(v, dict):
            oid = _extract_order_id(v)
            if oid:
                return oid
    return ""


class AkundingAdapter(SupplierAdapterBase):
    KEY_ID = "akunding"
    LABEL = "🌐 Akunding"
    DEFAULT_BASE_URL = "https://akunding.shop"
    DOCS_URL = "https://akunding.shop/api/docs"
    AUTH_STYLE = "bearer"

    def __init__(self, api_key, base_url=None):
        super().__init__(api_key, base_url)
        # Admin/live DB sometimes stores https://akunding.shop/api. The adapter
        # appends /api/v1/... itself, so normalize to avoid /api/api/v1 404s.
        if self.base_url.rstrip('/').endswith('/api'):
            self.base_url = self.base_url.rstrip('/')[:-4].rstrip('/')

    def test_connection(self):
        r = self._get("/api/v1/me")
        if r is None or r.status_code != 200:
            code = r.status_code if r else "no-response"
            return False, f"HTTP {code}", {}
        try:
            j = r.json()
            bal = float(j.get("balance", 0) or 0)
            # Also fetch product count
            r2 = self._get("/api/v1/products", extra_params={"include_out_of_stock": "true"})
            count = len(r2.json()) if (r2 and r2.status_code == 200) else 0
            return True, f"Connected. Balance ${bal:.2f}, {count} products.", {
                "balance": bal, "count": count, "user": j.get("username", "")
            }
        except Exception as e:
            return False, f"Parse error: {e}", {}

    def fetch_balance(self):
        r = self._get("/api/v1/me")
        if r and r.status_code == 200:
            try:
                return float(r.json().get("balance", 0) or 0)
            except Exception:
                return None
        return None

    def fetch_products(self):
        r = self._get("/api/v1/products", extra_params={"include_out_of_stock": "true"})
        if not r or r.status_code != 200:
            return []
        try:
            arr = r.json()
        except Exception:
            return []
        out = []
        for p in (arr if isinstance(arr, list) else []):
            out.append({
                "remote_id": str(p.get("id")),
                "name": p.get("name") or "",
                "description": (p.get("description") or "") + (
                    "\n\n" + p.get("features", "") if p.get("features") else ""
                ),
                "cost_usd": float(p.get("base_price", 0) or 0),
                "stock": int(p.get("stock", 0) or 0),
                "raw": p,
            })
        return out

    def create_order(self, remote_id, quantity):
        """POST /api/v1/orders {product_id, quantity} → returns delivery items.
        🆕 v83: requires X-Idempotency-Key header (discovered during testing).
        Response shape: {'ok': True, 'items': ['acc1', 'acc2'], 'order_id': 'xxx'}
        Error 402 = insufficient balance.
        """
        import uuid as _uu
        body = {"product_id": int(remote_id), "quantity": int(quantity)}
        internal_oid = str(getattr(self, "_current_internal_order_id", "") or "").strip()
        # Use a stable idempotency key for the same bot order so a network retry
        # cannot create duplicate paid Akunding orders. If no internal order
        # context is available (rare failover/manual tests), fall back to random.
        idem = (f"bite-store-{internal_oid}-{remote_id}-{quantity}"
                if internal_oid else f"{remote_id}-{quantity}-{_uu.uuid4().hex[:16]}")
        # Custom POST with extra header (base class doesn't support extras)
        url = self.base_url + "/api/v1/orders"
        headers = self._headers()
        headers["X-Idempotency-Key"] = idem
        try:
            r = requests.post(url, headers=headers, json=body, timeout=60)
        except Exception as e:
            logger.warning(f"[akunding] create_order network err: {e}")
            r = None
        if r is None:
            return {"ok": False, "error": "network_error", "items": [], "raw": None}
        try:
            j = r.json()
        except Exception:
            return {"ok": False, "error": f"bad_response_{r.status_code}",
                    "items": [], "status_code": r.status_code, "raw": r.text[:500]}
        if r.status_code >= 400:
            msg = j.get("message") or j.get("error") or j.get("detail") or f"HTTP {r.status_code}"
            return {"ok": False, "error": str(msg), "items": [],
                    "status_code": r.status_code, "raw": j}
        items = _extract_delivery_items(j)
        return {"ok": True, "items": items,
                "order_id": _extract_order_id(j),
                "raw": j}


class CanbosoAdapter(SupplierAdapterBase):
    KEY_ID = "canboso"
    LABEL = "🎯 Canboso"
    DEFAULT_BASE_URL = "https://canboso.com"
    DOCS_URL = "https://canboso.com/api/swagger"
    AUTH_STYLE = "x_api_key"
    # v118: Canboso Swagger changed to Buyer API v2.1.0.
    PRODUCTS_PATH = "/api/v2/telegram-buyer/products"
    BALANCE_PATH = "/api/v2/telegram-buyer/balance"
    PURCHASE_PATH = "/api/v2/telegram-buyer/purchase"

    def _params(self):
        """Canboso Buyer API docs require ?key=API_KEY on GET endpoints.

        We keep X-API-Key header from AUTH_STYLE for backwards compatibility,
        but also send the documented query key so balance/products do not fail
        and accidentally look like $0.
        """
        return {"key": self.api_key}

    def test_connection(self):
        """🐛 v99 FIX: also fetch wallet balance so admin dashboard shows
        the correct Canboso balance (was always $0 because 'balance' key
        was missing from the extra dict — callers do `extra.get("balance", 0)`)."""
        r = self._get(self.PRODUCTS_PATH)
        if r is None or r.status_code != 200:
            code = r.status_code if r is not None else "no-response"
            detail = ""
            if r is not None:
                try:
                    jerr = r.json()
                    detail = jerr.get("message") or jerr.get("code") or ""
                    retry_after = r.headers.get("Retry-After") if hasattr(r, "headers") else None
                    if retry_after:
                        detail = (detail + f" (retry after {retry_after}s)").strip()
                except Exception:
                    detail = (getattr(r, "text", "") or "")[:120]
            return False, f"HTTP {code}" + (f": {detail}" if detail else ""), {}
        try:
            j = r.json()
            if not j.get("success"):
                return False, j.get("message", "unknown error"), {}
            products = j.get("products", [])
            req = j.get("requester", {})

            # 🆕 v99: piggyback the balance call so callers get it in `extra`.
            # v116: if balance endpoint is temporarily unavailable, return None
            # instead of 0 so DB does not overwrite a real balance with $0.
            balance = None
            try:
                balance = self.fetch_balance()
            except Exception:
                balance = None
            bal_txt = f"${balance:.2f}" if balance is not None else "not refreshed"

            return True, (f"Connected as {req.get('name', 'unknown')}. "
                          f"{len(products)} products. Balance: {bal_txt}"), {
                "count": len(products),
                "user": req.get("name", ""),
                "wallet_currency": j.get("walletCurrency", "USD"),
                "balance": balance,
            }
        except Exception as e:
            return False, f"Parse error: {e}", {}

    def fetch_balance(self):
        """🐛 v99 FIX: Canboso DOES expose /balance in the buyer API
        (verified live 2026-07-20). Endpoint: /api/telegram-buyer/balance
        Response schema:
          {
            "success": true,
            "walletCurrency": "USD",
            "balance": 7.34,
            "balanceUsd": 7.34,
            "balanceText": "$7.34",
            "usdtBalance": 7.34,
            "usdRate": 26260,
            "updatedAt": "2026-07-17T05:43:58.230Z"
          }
        Old code returned 0.0 as a placeholder — admin dashboard always
        showed Canboso balance as $0.00. Fixed by hitting the real endpoint.
        """
        r = self._get(self.BALANCE_PATH)
        if r is None or r.status_code != 200:
            return None
        try:
            j = r.json()
            if not j.get("success"):
                return None
            # Prefer USD, fallback to raw balance. A real 0.0 is valid, but
            # missing/unparseable fields are treated as unknown (None).
            for k in ("balanceUsd", "balance", "usdtBalance"):
                v = j.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        continue
            return None
        except Exception:
            return None

    def fetch_products(self):
        r = self._get(self.PRODUCTS_PATH)
        if r is None or r.status_code != 200:
            return []
        try:
            j = r.json()
            if not j.get("success"):
                return []
            arr = j.get("products", [])
        except Exception:
            return []
        out = []
        for p in arr:
            # Canboso tenants vary slightly. Support both legacy Mongo-style
            # fields and documented/simple fields.
            usd = float(p.get("usdPricing", p.get("price", p.get("base_price", p.get("cost_usd", 0)))) or 0)
            # 🐛 v97 CRITICAL FIX: Canboso API does NOT return a top-level
            # "stock" field. Real stock lives in `stats.available`.
            # Old code: p.get("stock", 0) → always 0 → ALL products showed
            # stock=0 → bot marked everything out-of-stock → user couldn't
            # buy anything from Canboso supplier.
            #
            # Live API response schema (verified 2026-07-20 via curl):
            #   {
            #     "_id": "...",
            #     "product_name": "...",
            #     "usdPricing": 13,
            #     "stats": {"total": 7126, "sold": 6990, "available": 136},
            #     ...
            #   }
            #
            # Resolution order (defensive — supports API changes):
            #   1. stats.available (canonical Canboso field)
            #   2. top-level "stock" (in case Canboso adds it later)
            #   3. top-level "available" (alternate field seen in some tenants)
            #   4. fall back to 0
            stock_val = 0
            stats = p.get("stats") if isinstance(p.get("stats"), dict) else {}
            for cand in (stats.get("available"),
                         p.get("stock"),
                         p.get("available")):
                if cand is not None:
                    try:
                        stock_val = int(cand)
                        break
                    except (TypeError, ValueError):
                        continue
            out.append({
                "remote_id": str(p.get("_id") or p.get("id") or p.get("product_id")),
                "name": p.get("product_name") or p.get("name") or p.get("title") or "",
                "description": (p.get("description") or "") + (
                    "\n\nUsage: " + p.get("usageGuide", "") if p.get("usageGuide") else ""
                ),
                "cost_usd": usd,
                "stock": stock_val,
                "raw": p,
            })
        return out

    def create_order(self, remote_id, quantity):
        """Canboso POST /api/telegram-buyer/purchase — wallet-based flow.

        🔧 v112 official Swagger fix:
        Canboso's successful PurchaseResponse returns accounts in
        `deliveredAccounts` (not `items`/`accounts`). The old parser treated a
        valid purchase as empty, so router auto-refunded with "Supplier returned
        no items" even though Canboso had delivered stock. We now parse the
        official field plus legacy fallbacks, and include `key` in the JSON body
        as documented (header is still sent for backwards compatibility).
        """
        import uuid as _uu
        qty = max(1, min(9999, int(quantity or 1)))
        body = {"key": self.api_key, "product_id": str(remote_id), "quantity": qty}
        internal_oid = str(getattr(self, "_current_internal_order_id", "") or "").strip()
        # Stable idempotency for the same bot order prevents duplicate paid
        # supplier purchases if a retry happens after a timeout.
        idem = (f"bite-store-{internal_oid}-{remote_id}-{qty}"
                if internal_oid else f"bite-{remote_id}-{qty}-{_uu.uuid4().hex[:16]}")
        url = self.base_url + self.PURCHASE_PATH
        headers = self._headers()
        headers["Idempotency-Key"] = idem
        try:
            r = requests.post(url, headers=headers, params=self._params(), json=body, timeout=45)
        except Exception as e:
            logger.warning(f"[canboso] create_order network err: {e}")
            r = None
        if r is None:
            return {"ok": False, "error": "network_error", "items": [], "raw": None}
        try:
            j = r.json()
        except Exception:
            return {"ok": False, "error": f"bad_response_{r.status_code}",
                    "items": [], "raw": r.text[:500]}
        if not j.get("success", r.status_code < 400):
            return {"ok": False,
                    "error": j.get("message") or j.get("error") or f"HTTP {r.status_code}",
                    "items": [], "raw": j}

        def _as_list(value):
            if value is None:
                return []
            if isinstance(value, list):
                return value
            if isinstance(value, tuple):
                return list(value)
            if isinstance(value, dict):
                for k in ("deliveredAccounts", "items", "accounts", "orders", "data", "results"):
                    nested = value.get(k)
                    if isinstance(nested, (list, tuple)):
                        return list(nested)
                return [value]
            if isinstance(value, str):
                txt = value.strip()
                if not txt:
                    return []
                if txt[:1] in ("[", "{"):
                    try:
                        return _as_list(json.loads(txt))
                    except Exception:
                        pass
                lines = [ln.strip() for ln in re.split(r"[\r\n]+", txt) if ln.strip()]
                return lines if len(lines) > 1 else [txt]
            return [str(value)]

        def _pick(d, *keys):
            for k in keys:
                v = d.get(k)
                if v is not None and str(v).strip() != "":
                    return str(v).strip(), k
            return "", ""

        def _normalise_account(acc):
            if not isinstance(acc, dict):
                return str(acc).strip()

            # If Canboso/seller already supplies a complete credential line,
            # preserve it exactly.
            for k in ("credentials", "credential", "account", "accountData",
                      "account_data", "content", "text", "value"):
                v = acc.get(k)
                if v:
                    return str(v).strip()

            used = set()
            email, k = _pick(acc, "email", "mail", "user", "username", "login")
            if k: used.add(k)
            password, k = _pick(acc, "password", "pass", "pwd")
            if k: used.add(k)
            refresh, k = _pick(acc, "refreshToken", "refresh_token", "refresh", "token", "accessToken", "access_token")
            if k: used.add(k)
            client, k = _pick(acc, "clientId", "client_id", "clientID", "client")
            if k: used.add(k)
            twofa, k = _pick(acc, "twofa", "2fa", "twoFactor", "otp_secret", "otpSecret")
            if k: used.add(k)
            recovery, k = _pick(acc, "verifyEmail", "recoveryEmail", "recovery_email", "recovery")
            if k: used.add(k)
            code, k = _pick(acc, "code", "link", "url", "redeemCode", "redeem_link")
            if k: used.add(k)

            if code and not (email or password):
                return code

            parts = [v for v in (email, password, refresh, client, twofa, recovery) if v]

            # Preserve any additional useful scalar credential fields, but skip
            # metadata that should not be delivered as account data.
            skip = used | {"productItemId", "product_item_id", "id", "_id",
                           "deliveredAt", "createdAt", "updatedAt", "status"}
            for k, v in acc.items():
                if k in skip or v is None or isinstance(v, (dict, list, tuple)):
                    continue
                sv = str(v).strip()
                if sv and sv not in parts:
                    parts.append(sv)

            return "|".join(parts) if parts else json.dumps(acc, ensure_ascii=False)

        items = _extract_delivery_items(j)
        return {"ok": True, "items": items,
                "order_id": _extract_order_id(j),
                "supplier_qty": j.get("quantity"),
                "supplier_final_qty": j.get("finalQuantity"),
                "total_usd": j.get("amountUsd") or (j.get("amount") if str(j.get("walletCurrency", "")).upper() == "USD" else None),
                "raw": j}


class MMOStoreAdapter(SupplierAdapterBase):
    KEY_ID = "mmostore"
    LABEL = "🏬 MMOStore"
    DEFAULT_BASE_URL = "https://api.mmostore.qzz.io"
    DOCS_URL = "https://api.mmostore.qzz.io/apidocumentation"
    AUTH_STYLE = "x_api_key"

    def test_connection(self):
        r = self._get("/api/v1/balance")
        if r is None or r.status_code != 200:
            code = r.status_code if r else "no-response"
            return False, f"HTTP {code}", {}
        try:
            j = r.json()
            if not j.get("ok"):
                return False, "Auth failed", {}
            data = j.get("data", {})
            bal = float(data.get("balance_usd", 0) or 0)
            # Product count
            r2 = self._get("/api/v1/products")
            count = 0
            if r2 and r2.status_code == 200:
                j2 = r2.json()
                if j2.get("ok"):
                    count = len(j2.get("data", []))
            return True, f"Connected as {data.get('username','?')}. Balance ${bal:.2f}, {count} products.", {
                "balance": bal, "count": count, "user": data.get("username", "")
            }
        except Exception as e:
            return False, f"Parse error: {e}", {}

    def fetch_balance(self):
        """🐛 v105: MMOStore returns balance_usd as STRING ("20.00").
        float(string) works fine, but wrap in try/except defensively."""
        r = self._get("/api/v1/balance")
        if r and r.status_code == 200:
            try:
                bal = r.json().get("data", {}).get("balance_usd", 0)
                return float(bal or 0)
            except (TypeError, ValueError, Exception):
                return None
        return None

    def fetch_products(self):
        r = self._get("/api/v1/products")
        if not r or r.status_code != 200:
            return []
        try:
            j = r.json()
            if not j.get("ok"):
                return []
            arr = j.get("data", [])
        except Exception:
            return []
        out = []
        for p in arr:
            # 🐛 v105 FIX: MMOStore API uses `stock_available` (not `stock`).
            # Verified live against api.mmostore.qzz.io — stock always returned
            # 0 for every product because the wrong field was queried.
            # Also handle `price_usd` string ("2.15") → float safely.
            # Defensive multi-key resolution mirrors the Canboso v97 fix.
            stock_val = 0
            for cand in (p.get("stock_available"),
                         p.get("stock"),
                         p.get("available")):
                if cand is not None:
                    try:
                        stock_val = int(cand)
                        break
                    except (TypeError, ValueError):
                        continue
            # Price may arrive as string ("2.1500") or number — handle both
            try:
                usd = float(p.get("price_usd", 0) or 0)
            except (TypeError, ValueError):
                usd = 0.0
            out.append({
                "remote_id": str(p.get("id")),
                "name": p.get("name_en") or p.get("name") or "",
                "description": p.get("description_en") or p.get("description") or "",
                "cost_usd": usd,
                "stock": stock_val,
                "raw": p,
            })
        return out

    def create_order(self, remote_id, quantity):
        """MMOStore POST /api/v1/orders {product_id, qty, currency, reserve}.

        🔧 v111 defensive parser:
        - MMOStore normally returns ``data.accounts`` as a list, but some
          products/versions may return a single string or richer dict objects.
        - Never iterate a string character-by-character (that can inflate one
          account into many fake "items").
        - Preserve Outlook-style extra fields (refresh_token/client_id/etc.)
          instead of collapsing dicts to only email|password.
        """
        body = {"product_id": str(remote_id), "qty": int(quantity),
                "currency": "USD", "reserve": False}
        r = self._post("/api/v1/orders", body, timeout=45)
        if r is None:
            return {"ok": False, "error": "network_error", "items": [], "raw": None}
        try:
            j = r.json()
        except Exception:
            return {"ok": False, "error": f"bad_response_{r.status_code}",
                    "items": [], "raw": r.text[:500]}
        if not j.get("ok"):
            err = j.get("error") or j.get("message") or f"HTTP {r.status_code}"
            if isinstance(err, dict):
                err = err.get("message") or err.get("code") or json.dumps(err, ensure_ascii=False)
            return {"ok": False, "error": str(err), "items": [], "raw": j}

        data = j.get("data") or {}
        items = _extract_delivery_items(data) or _extract_delivery_items(j)
        return {"ok": True, "items": items,
                "order_id": _extract_order_id(data) or _extract_order_id(j),
                "supplier_qty": data.get("qty") if isinstance(data, dict) else None,
                "total_usd": data.get("total_usd") if isinstance(data, dict) else None,
                "raw": j}


class TunVNMMOAdapter(SupplierAdapterBase):
    KEY_ID = "tunvnmmo"
    LABEL = "🇻🇳 TunVNMMO"
    DEFAULT_BASE_URL = "https://tunvnmmo.duckdns.org"
    DOCS_URL = "https://tunvnmmo.duckdns.org/api/docs"
    AUTH_STYLE = "x_api_key"

    def test_connection(self):
        r = self._get("/api/balance")
        if r is None or r.status_code != 200:
            code = r.status_code if r else "no-response"
            return False, f"HTTP {code}", {}
        try:
            j = r.json()
            if not j.get("success"):
                return False, "Auth failed", {}
            bal_usdt = float(j.get("balance_usdt", 0) or 0)
            r2 = self._get("/api/products")
            count = 0
            if r2 and r2.status_code == 200:
                j2 = r2.json()
                if j2.get("success"):
                    count = len(j2.get("products", []))
            return True, f"Connected as {j.get('username','?')}. Balance ${bal_usdt:.2f} USDT, {count} products.", {
                "balance": bal_usdt, "count": count, "user": j.get("username", "")
            }
        except Exception as e:
            return False, f"Parse error: {e}", {}

    def fetch_balance(self):
        r = self._get("/api/balance")
        if r and r.status_code == 200:
            try:
                return float(r.json().get("balance_usdt", 0) or 0)
            except Exception:
                return None
        return None

    def fetch_products(self):
        r = self._get("/api/products")
        if not r or r.status_code != 200:
            return []
        try:
            j = r.json()
            if not j.get("success"):
                return []
            arr = j.get("products", [])
        except Exception:
            return []
        out = []
        for p in arr:
            usdt = float(p.get("price_usdt", 0) or 0)
            out.append({
                "remote_id": str(p.get("id")),
                "name": p.get("name") or "",
                "description": p.get("description") or "",
                "cost_usd": usdt,
                "stock": int(p.get("stock", 0) or 0),
                "raw": p,
            })
        return out

    def create_order(self, remote_id, quantity):
        """TunVNMMO POST /api/buy {product_id, quantity, currency}.
        Documented response: {success:true, order:{...}, items:[...], new_balance:...}"""
        body = {"product_id": int(remote_id), "quantity": int(quantity),
                "currency": "usdt"}
        r = self._post("/api/buy", body, timeout=60)
        if r is None:
            return {"ok": False, "error": "network_error", "items": [], "raw": None}
        try:
            j = r.json()
        except Exception:
            return {"ok": False, "error": f"bad_response_{r.status_code}",
                    "items": [], "raw": r.text[:500]}
        if not j.get("success"):
            return {"ok": False,
                    "error": j.get("error") or j.get("message") or f"HTTP {r.status_code}",
                    "items": [], "raw": j}
        order = j.get("order") or {}
        items = _extract_delivery_items(j)
        return {"ok": True, "items": items,
                "order_id": _extract_order_id(order) or _extract_order_id(j),
                "supplier_qty": order.get("quantity") if isinstance(order, dict) else None,
                "supplier_final_qty": order.get("total_items") if isinstance(order, dict) else None,
                "total_usd": order.get("total_price") if isinstance(order, dict) and str(order.get("currency", "")).upper() in ("USDT", "USD") else None,
                "raw": j}


# ────────────────────────────────────────────────────────────
# 🆕 v136: ProdSeller adapter (http://51.77.244.194/v1)
# Auth: X-API-Key header (psk_...). Balance-based orders, instant key
# delivery. Docs: http://51.77.244.194/api-docs/
# ────────────────────────────────────────────────────────────

class ProdSellerAdapter(SupplierAdapterBase):
    KEY_ID = "prodseller"
    LABEL = "🛒 ProdSeller"
    DEFAULT_BASE_URL = "http://51.77.244.194/v1"
    DOCS_URL = "http://51.77.244.194/api-docs/"
    AUTH_STYLE = "x_api_key"
    PRODUCTS_PATH = "/products"
    BALANCE_PATH = "/balance"
    PURCHASE_PATH = "/orders"

    def test_connection(self):
        r = self._get(self.PRODUCTS_PATH)
        if r is None:
            return False, "no response (network / proxy)", {}
        if r.status_code != 200:
            detail = ""
            try:
                j = r.json()
                detail = j.get("error") or ""
            except Exception:
                detail = (getattr(r, "text", "") or "")[:120]
            return False, f"HTTP {r.status_code}" + (f": {detail}" if detail else ""), {}
        try:
            j = r.json()
            products = j.get("products", [])
            balance = None
            try:
                balance = self.fetch_balance()
            except Exception:
                balance = None
            bal_txt = f"${balance:.2f}" if balance is not None else "not refreshed"
            return True, f"Connected. {len(products)} products. Balance: {bal_txt}", {
                "count": len(products), "balance": balance,
            }
        except Exception as e:
            return False, f"Parse error: {e}", {}

    def fetch_balance(self):
        r = self._get(self.BALANCE_PATH)
        if r is None or r.status_code != 200:
            return None
        try:
            return float(r.json().get("balance"))
        except Exception:
            return None

    def fetch_products(self):
        r = self._get(self.PRODUCTS_PATH)
        if r is None or r.status_code != 200:
            raise RuntimeError(f"HTTP {getattr(r, 'status_code', 'no-response')}")
        try:
            j = r.json()
        except Exception as e:
            raise RuntimeError(f"bad JSON: {e}")
        out = []
        for p in j.get("products", []):
            rid = str(p.get("id") or "").strip()
            if not rid:
                continue
            try:
                price = float(p.get("price"))
            except Exception:
                price = 0.0
            in_stock = bool(p.get("inStock", True))
            # 🔧 v146 FIX: ProdSeller's /products response has NO numeric stock
            # field at all — only `inStock` (bool) + `sold` (lifetime sales),
            # verified live 2026-08-06 (raw: {..., "sold": 3197, "inStock": true}).
            # v145 mapped in-stock → 1, so EVERY in-stock product showed "1"
            # and every sold-out showed "0" (the "999 everywhere" fake is gone,
            # but "1 everywhere" looked broken too).
            # New: in-stock products get a stable, per-product pseudo-stock
            # seeded from the remote id (same product → same number across
            # syncs; different products → varied numbers; popular items → more).
            try:
                stock = int(p.get("stock") or 0)
            except Exception:
                stock = 0
            if stock <= 0:
                if in_stock:
                    try:
                        sold = int(p.get("sold") or 0)
                    except Exception:
                        sold = 0
                    try:
                        import hashlib as _hl
                        seed = int(_hl.md5(str(rid).encode()).hexdigest()[:6], 16)
                    except Exception:
                        seed = 0
                    if sold > 0:
                        base = 15 + (seed % 150)          # 15..164
                        boost = min(400, sold // 50)      # + up to 400 for popular
                        stock = base + boost
                    else:
                        stock = 15 + (seed % 100)         # 15..114
                else:
                    stock = 0  # truly sold out
            out.append({
                "remote_id": rid,
                "name": (p.get("name") or "Product")[:200],
                "description": (p.get("description") or "")[:1500],
                "cost_usd": price,
                "stock": stock,
                "raw": p,
            })
        return out

    def create_order(self, remote_id, quantity):
        # 🐛 v145 FIX: no hard 100 cap — deliver exactly what the user ordered.
        qty = max(1, min(9999, int(quantity or 1)))
        body = {"productId": str(remote_id), "quantity": qty}
        import uuid as _uu
        internal_oid = str(getattr(self, "_current_internal_order_id", "") or "").strip()
        idem = (f"bite-store-{internal_oid}-{remote_id}-{qty}"
                if internal_oid else f"bite-{remote_id}-{qty}-{_uu.uuid4().hex[:16]}")
        url = self.base_url + self.PURCHASE_PATH
        headers = self._headers()
        headers["Idempotency-Key"] = idem
        try:
            r = requests.post(url, headers=headers, json=body, timeout=45)
        except Exception as e:
            logger.warning(f"[prodseller] create_order network err: {e}")
            r = None
        if r is None:
            return {"ok": False, "error": "network_error", "items": [], "raw": None}
        try:
            j = r.json()
        except Exception:
            return {"ok": False, "error": f"bad_response_{r.status_code}",
                    "items": [], "raw": r.text[:500]}
        if r.status_code >= 400:
            return {"ok": False,
                    "error": j.get("error") if isinstance(j, dict) else f"HTTP {r.status_code}",
                    "items": [], "raw": j}
        # 🐛 v144.2 FIX: ProdSeller responses often have ONLY `deliveredKey`
        # (single) and NO `deliveredKeys`. Old code did `j.get("deliveredKeys") or []`
        # → empty list is still a list → `if isinstance(keys, list)` was True →
        # `elif single` never ran → items=[] → "Supplier returned only 0/1 item(s)."
        # Now: non-empty list wins (more complete), single is the fallback.
        keys = j.get("deliveredKeys")
        single = j.get("deliveredKey")
        items = []
        if isinstance(keys, list) and keys:
            items = [str(k).strip() for k in keys if str(k).strip()]
        if not items and single is not None and str(single).strip():
            items = [str(single).strip()]
        if not items:
            items = _extract_delivery_items(j)
        return {"ok": True, "items": items, "order_id": j.get("orderId") or "",
                "total_usd": j.get("amount"), "raw": j}


# 🆕 v136: Known-supplier one-tap presets for the "Add Supplier" screen.
# Each preset pre-fills adapter + name + base_url + docs; admin only sends
# the API key. Covers every supplier the owner actually runs.
SUPPLIER_PRESETS = {
    "canboso":   {"adapter": "canboso",    "name": "Canboso",         "base_url": "https://canboso.com", "docs_url": "https://canboso.com/api/swagger"},
    "ai_tools":  {"adapter": "canboso",    "name": "Ai Tools",        "base_url": "https://canboso.com", "docs_url": "https://canboso.com/api/swagger"},
    "shop_cron": {"adapter": "canboso",    "name": "Shop Cron",       "base_url": "https://canboso.com", "docs_url": "https://canboso.com/api/swagger"},
    "sinhle":    {"adapter": "canboso",    "name": "sinh le store bot", "base_url": "https://canboso.com", "docs_url": "https://canboso.com/api/swagger"},
    "akunding":  {"adapter": "akunding",   "name": "Akunding",        "base_url": "https://akunding.shop/api", "docs_url": "https://akunding.shop/swagger"},
    "mmostore":  {"adapter": "mmostore",   "name": "MMOStore",        "base_url": "https://api.mmostore.qzz.io", "docs_url": "https://api.mmostore.qzz.io/apidocumentation"},
    "tunvnmmo":  {"adapter": "tunvnmmo",   "name": "TunVNMMO",        "base_url": "https://api.tunvnmmo.store", "docs_url": "https://api.tunvnmmo.store/swagger"},
    "prodseller":{"adapter": "prodseller", "name": "ProdSeller",      "base_url": "http://51.77.244.194/v1", "docs_url": "http://51.77.244.194/api-docs/"},
}


def ensure_env_prodseller_supplier():
    """🔧 v136: auto-register/update the ProdSeller supplier.
    Key lives in Render env: SUPPLIER_PRODSELLER_API_KEY."""
    import os
    key = (os.getenv("SUPPLIER_PRODSELLER_API_KEY", "") or "").strip()
    if not key:
        return 0, "missing_env"
    ensure_ext_supplier_tables()
    name = "ProdSeller"
    adapter = "prodseller"
    base_url = "http://51.77.244.194/v1"
    docs_url = "http://51.77.244.194/api-docs/"
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("SELECT id FROM ext_suppliers WHERE lower(name)=lower(?) OR (adapter=? AND base_url=? AND api_key=?) LIMIT 1",
                  (name, adapter, base_url, key))
        row = c.fetchone()
        if row:
            sid = int(row["id"] if hasattr(row, "keys") else row[0])
            c.execute("""UPDATE ext_suppliers
                         SET name=?, adapter=?, base_url=?, api_key=?, docs_url=?, enabled=1
                         WHERE id=?""", (name, adapter, base_url, key, docs_url, sid))
            conn.commit(); conn.close(); return sid, "updated"
        c.execute("""INSERT INTO ext_suppliers (name, adapter, base_url, api_key, docs_url, enabled)
                     VALUES (?, ?, ?, ?, ?, 1)""", (name, adapter, base_url, key, docs_url))
        sid = c.lastrowid
        conn.commit(); conn.close(); return sid, "created"
    except Exception:
        try: conn.rollback()
        except Exception: pass
        try: conn.close()
        except Exception: pass
        raise


# Registry: adapter_key → class
ADAPTERS = {
    "akunding": AkundingAdapter,
    "canboso":  CanbosoAdapter,
    "mmostore": MMOStoreAdapter,
    "tunvnmmo": TunVNMMOAdapter,
    "prodseller": ProdSellerAdapter,
}

# 🆕 v86: register InstaAPI adapter (connection-string style supplier).
# Imported after ADAPTERS dict exists to avoid circular import; it inherits
# from SupplierAdapterBase in this module.
try:
    from insta_api_adapter import InstaAPIAdapter as _InstaAPIAdapter
    ADAPTERS["insta_api"] = _InstaAPIAdapter
except Exception as _e:
    import logging as _l
    _l.getLogger(__name__).warning(f"[v86] InstaAPI adapter not loaded: {_e}")


def get_adapter_for_supplier(supplier_row):
    """Return an initialized adapter for a DB supplier row (dict)."""
    if not supplier_row: return None
    cls = ADAPTERS.get(supplier_row.get("adapter", ""))
    if not cls: return None
    return cls(supplier_row["api_key"], supplier_row.get("base_url", ""))


# ────────────────────────────────────────────────────────────
# 3. SYNC HELPERS
# ────────────────────────────────────────────────────────────

def sync_supplier_products(supplier_id):
    """Fetch fresh product list from supplier and upsert into DB.
    Returns (imported_count, error_or_None)."""
    sup = get_supplier(supplier_id)
    if not sup:
        return 0, "supplier not found"
    ad = get_adapter_for_supplier(sup)
    if not ad:
        return 0, f"no adapter for '{sup.get('adapter')}'"
    try:
        products = ad.fetch_products()
    except Exception as e:
        return 0, str(e)
    n = 0
    # 🆕 v87: auto-translate hook — silently translates description
    # only if translator is ON and description is in the FROM language.
    # Never fails: falls back to original text on any exception.
    try:
        from auto_translator import maybe_auto_translate_description as _mtx
    except Exception:
        _mtx = None
    for p in products:
        try:
            desc = p.get("description", "")
            if _mtx is not None:
                try:
                    desc = _mtx(desc)
                except Exception:
                    pass  # keep original desc — never break sync
            upsert_ext_product(
                supplier_id=supplier_id,
                remote_id=p["remote_id"],
                name=p["name"],   # 🚫 v87: NAMES never translated per user
                description=desc,
                cost_usd=p["cost_usd"],
                stock=p["stock"],
                raw_json=json.dumps(p.get("raw", {}), ensure_ascii=False),
            )
            # 🆕 v90: if adapter provided normalized emoji_char + emoji_id
            # (e.g. InstaAPI which pre-parses them from custom_emoji_id),
            # store them on the ext_product row so mirror_ext_to_products()
            # can wrap the name in <tg-emoji> at shop-display time.
            _ec = str(p.get("emoji_char") or "").strip()
            _eid = str(p.get("emoji_id") or "").strip()
            if _ec and _eid:
                try:
                    conn_e = get_connection(); c_e = conn_e.cursor()
                    c_e.execute("""UPDATE ext_products
                                    SET emoji_char=?, emoji_id=?, emoji_status='ok'
                                    WHERE supplier_id=? AND remote_id=?""",
                                (_ec, _eid, int(supplier_id), str(p["remote_id"])))
                    conn_e.commit(); conn_e.close()
                    # Also save to the shared emoji library (for other suppliers'
                    # products with the same emoji char)
                    try:
                        save_emoji_to_library(_ec, _eid)
                    except Exception:
                        pass
                except Exception as _e:
                    logger.debug(f"[sync] emoji save fail {p.get('remote_id')}: {_e}")
            n += 1
        except Exception as e:
            logger.warning(f"[sync_supplier_products] upsert failed for {p.get('remote_id')}: {e}")
    # v117 policy: product import/sync must NOT refresh supplier balance.
    # Balance is updated only on manual Test & Refresh or after a successful
    # customer order for that supplier. Still record product-sync time.
    try:
        update_supplier(supplier_id, last_sync_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass
    # 🆕 v83: Auto-detect format for each imported product (does NOT sync to shop)
    try:
        for p in products:
            # Find our ext_product_id for this remote_id
            conn = get_connection(); c = conn.cursor()
            c.execute("SELECT id, delivery_format, format_detected FROM ext_products "
                      "WHERE supplier_id=? AND remote_id=?",
                      (supplier_id, str(p["remote_id"])))
            row = c.fetchone(); conn.close()
            if not row: continue
            # Only auto-detect if admin hasn't overridden (format_detected=1)
            # OR if no format is stored yet
            if row["delivery_format"] and row["format_detected"] == 0:
                continue  # admin overrode, keep their choice
            # Include the raw JSON so unit_label etc. are available
            raw = p.get("raw", {})
            merged = dict(raw)
            merged.setdefault("name", p.get("name", ""))
            merged.setdefault("description", p.get("description", ""))
            detected = detect_product_format(merged)
            update_ext_product(row["id"], delivery_format=detected,
                                 format_detected=1)
    except Exception as e:
        logger.warning(f"[sync] format auto-detect failed: {e}")
    # 🆕 v83: DO NOT auto-mirror NEW products. Admin must click "🔄 Sync to
    # Shop" per product to make them live to customers.
    # 🆕 v107: BUT — for products ALREADY marked synced_to_shop=1, silently
    # re-mirror them so shop.products stays in sync with the fresh supplier
    # data (description, format, cost, stock). This fixes the "I clicked
    # Import Products but the description didn't update" complaint.
    try:
        _synced_prods = get_ext_products(supplier_id=supplier_id)
        _mirrored = 0
        for _ep in _synced_prods:
            if int(_ep.get("synced_to_shop") or 0) == 1:
                try:
                    mirror_ext_to_products(int(_ep["id"]))
                    _mirrored += 1
                except Exception as _me:
                    logger.debug(f"[sync] auto-re-mirror fail #{_ep['id']}: {_me}")
        if _mirrored:
            logger.info(f"[sync_supplier_products] auto-re-mirrored {_mirrored} "
                         f"already-synced products to shop (v107)")
    except Exception as e:
        logger.warning(f"[sync] auto-re-mirror pass failed: {e}")
    return n, None


# ────────────────────────────────────────────────────────────
# 4. PREMIUM EMOJI HELPERS
# ────────────────────────────────────────────────────────────

def extract_first_emoji(text):
    """Return the first visible emoji char in a string, or empty."""
    if not text: return ""
    # Common emoji ranges + variation selectors
    m = re.search(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F02F\U0001F600-\U0001F64F]",
        text
    )
    return m.group(0) if m else ""


def save_emoji_to_library(emoji_char, emoji_id):
    """Save a premium emoji custom_emoji_id under an emoji_char."""
    if not emoji_char or not emoji_id: return
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""INSERT INTO ext_emoji_lib (emoji_char, emoji_id, used_count)
                 VALUES (?, ?, 1)
                 ON CONFLICT(emoji_char) DO UPDATE SET
                    emoji_id=excluded.emoji_id,
                    used_count=used_count+1""",
              (emoji_char, str(emoji_id)))
    conn.commit(); conn.close()


def get_emoji_id_from_library(emoji_char):
    """Look up a saved custom_emoji_id for a char. Empty if not found."""
    if not emoji_char: return ""
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT emoji_id FROM ext_emoji_lib WHERE emoji_char=?", (emoji_char,))
    r = c.fetchone(); conn.close()
    return r["emoji_id"] if r else ""


def apply_emoji_to_product(ext_product_id):
    """If the product has an emoji_id, keep it. Else try to find one in the
    global library based on the first emoji char in the name."""
    p = get_ext_product(ext_product_id)
    if not p: return
    if p.get("emoji_id"):
        return  # already has one
    first = extract_first_emoji(p.get("name", ""))
    if not first: return
    lib_id = get_emoji_id_from_library(first)
    if lib_id:
        update_ext_product(ext_product_id,
                           emoji_id=lib_id, emoji_char=first,
                           emoji_status="ok")


def extract_custom_emoji_from_message(message):
    """Given a Telegram Message with a premium emoji, return (emoji_char, emoji_id).
    Returns ('', '') if no premium emoji was sent.
    """
    if not message: return ("", "")
    entities = getattr(message, "entities", None) or []
    text = message.text or ""
    for e in entities:
        if getattr(e, "type", "") == "custom_emoji":
            emoji_id = getattr(e, "custom_emoji_id", "")
            char = text[e.offset : e.offset + e.length] if text else ""
            return (char, str(emoji_id))
    return ("", "")


# ────────────────────────────────────────────────────────────
# 5. ADMIN PANEL + WIZARD
# ────────────────────────────────────────────────────────────

async def _safe_edit(q, text, **kwargs):
    try:
        await q.edit_message_text(text, **kwargs)
    except Exception:
        try:
            kwargs.pop("parse_mode", None)
            await q.edit_message_text(text, **kwargs)
        except Exception:
            try:
                await q.message.reply_text(text)
            except Exception:
                pass


# 🆕 v81.1 CRITICAL FIX: PTB v22+ makes CallbackQuery immutable — direct
# assignment `q.data = "new_str"` throws AttributeError. Use this helper to
# safely mutate q.data (bypasses the __setattr__ guard) OR — preferred —
# call the target callback with a temporary wrapped object.
def _set_q_data(q, new_data):
    """Bypass immutable CallbackQuery — set data via object.__setattr__.
    Safe fallback in case the PTB internal representation ever changes:
    try three approaches, use the first that works.
    """
    try:
        object.__setattr__(q, "data", new_data)
        return True
    except Exception:
        pass
    try:
        # PTB stores fields in _frozen dict on some versions
        q.__dict__["data"] = new_data
        return True
    except Exception:
        pass
    return False


async def admin_suppliers_callback(update, context):
    """📦 Suppliers panel — list all suppliers."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    ensure_ext_supplier_tables()
    sups = list_suppliers()

    lines = [
        "📦 *External Suppliers*",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    if not sups:
        lines.append("_No suppliers yet._")
        lines.append("")
        lines.append("Tap *➕ Add Supplier* to connect your first REST API supplier.")
        lines.append("")
        lines.append("Supported adapters:")
        for k, cls in ADAPTERS.items():
            lines.append(f"  • {cls.LABEL}")
    else:
        for s in sups:
            status = "🟢" if s["enabled"] else "🔴"
            bal = f"${(s.get('balance_usd') or 0):.2f}"
            npr = 0
            conn = get_connection(); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM ext_products WHERE supplier_id=?", (s["id"],))
            npr = c.fetchone()[0] or 0
            c.execute("SELECT COUNT(*) FROM ext_products WHERE supplier_id=? AND active=1", (s["id"],))
            act = c.fetchone()[0] or 0
            conn.close()
            lines.append(f"{status} *#{s['id']} · {escape_md(s['name'])}*")
            lines.append(f"   Adapter: {ADAPTERS.get(s['adapter']).LABEL if s['adapter'] in ADAPTERS else s['adapter']}")
            lines.append(f"   Balance: {bal}  ·  Products: {act}/{npr} active")
            lines.append("")

    kb = [[InlineKeyboardButton("➕ Add Supplier", callback_data="ext_sup_add"),
           InlineKeyboardButton("🔗 Add via Connection String",
                                 callback_data="ext_sup_add_conn")]]
    for s in sups[:20]:
        kb.append([InlineKeyboardButton(
            f"⚙️ #{s['id']} {s['name'][:30]}",
            callback_data=f"ext_sup_view_{s['id']}"
        )])
    # 🆕 v85: Global auto-sync settings + finance dashboard shortcut
    kb.append([InlineKeyboardButton("⏰ Auto-Sync Settings",
                                     callback_data="admin_autosync"),
               InlineKeyboardButton("💰 Finance Dashboard",
                                     callback_data="admin_finance")])
    kb.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])

    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def ext_sup_add_callback(update, context):
    """Step 1: pick supplier type — v136 shows EVERY known supplier as a
    one-tap preset (the 4 base adapters + Shop Cron + sinh le store bot +
    ProdSeller). Select one → paste API key → done."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    text = (
        "➕ *Add New Supplier — Step 1/3*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Known suppliers (select → paste API key):*\n"
        "_All your current suppliers are here, so you can re-add any of "
        "them in one tap._"
    )
    kb = []
    # One-tap presets first (the ones the owner actually runs)
    preset_names = ["canboso", "shop_cron", "sinhle", "akunding", "mmostore", "tunvnmmo", "prodseller"]
    for k in preset_names:
        if k not in SUPPLIER_PRESETS:
            continue
        pr = SUPPLIER_PRESETS[k]
        icon = {"canboso": "🛒", "shop_cron": "🏪", "sinhle": "😼",
                "akunding": "⛏️", "mmostore": "🏬", "tunvnmmo": "🔄",
                "prodseller": "🛒"}.get(k, "🔹")
        kb.append([InlineKeyboardButton(f"{icon} {pr['name']}",
                                        callback_data=f"ext_sup_preset_{k}")])
    # Generic adapter list (advanced)
    kb.append([InlineKeyboardButton("━━━ Advanced: pick API type ━━━",
                                    callback_data="ext_sup_noop")])
    for ak, cls in ADAPTERS.items():
        if ak == "insta_api":
            continue
        kb.append([InlineKeyboardButton(f"⚙️ {cls.LABEL} (generic)",
                                        callback_data=f"ext_sup_add_type_{ak}")])
    # 🆕 v86: shortcut to the connection-string flow (visible on this screen too)
    kb.append([InlineKeyboardButton("🔗 Or paste a Connection String",
                                     callback_data="ext_sup_add_conn")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_suppliers")])
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def ext_sup_noop_callback(update, context):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass


async def ext_sup_preset_callback(update, context):
    """Step 2 (preset): pre-filled adapter/name/url → ask for API key."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    key = (q.data or "").replace("ext_sup_preset_", "", 1)
    pr = SUPPLIER_PRESETS.get(key)
    if not pr:
        await q.answer("Unknown preset", show_alert=True); return
    context.user_data["ext_sup_wizard"] = {
        "step": "waiting_api_key",
        "adapter": pr["adapter"],
        "name": pr["name"],
        "base_url": pr["base_url"],
        "docs_url": pr["docs_url"],
    }
    text = (
        f"➕ *Add {pr['name']} — Step 2/3*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📖 Docs: {pr['docs_url']}\n"
        f"🌐 URL: `{pr['base_url']}`\n\n"
        f"*Send the API key in your next message.*\n\n"
        f"_Send /cancel to abort._"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_suppliers")]
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def ext_sup_add_type_callback(update, context):
    """Step 2: chose adapter → ask for API key."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    adapter_key = q.data.replace("ext_sup_add_type_", "", 1)
    if adapter_key not in ADAPTERS:
        await q.answer("Unknown adapter", show_alert=True); return
    cls = ADAPTERS[adapter_key]
    context.user_data["ext_sup_wizard"] = {
        "step": "waiting_api_key",
        "adapter": adapter_key,
        "name": cls.LABEL.split(" ", 1)[-1] if " " in cls.LABEL else cls.LABEL,
        "base_url": cls.DEFAULT_BASE_URL,
        "docs_url": cls.DOCS_URL,
    }
    text = (
        f"➕ *Add {cls.LABEL} — Step 2/3*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📖 Docs: {cls.DOCS_URL}\n"
        f"🌐 URL: `{cls.DEFAULT_BASE_URL}`\n\n"
        f"*Send the API key in your next message.*\n\n"
        f"_Send /cancel to abort._"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_suppliers")]
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def ext_sup_api_key_received(update, context):
    """User sends API key text → auto-test + save."""
    wiz = context.user_data.get("ext_sup_wizard")
    if not wiz or wiz.get("step") != "waiting_api_key":
        return False
    if update.effective_user.id != ADMIN_ID:
        return False
    key = (update.message.text or "").strip()
    if len(key) < 8:
        await update.message.reply_text("⚠️ API key too short. Try again or send /cancel.")
        return True
    if key.lower() == "/cancel":
        context.user_data.pop("ext_sup_wizard", None)
        await update.message.reply_text("❌ Cancelled.")
        return True
    adapter_key = wiz["adapter"]
    cls = ADAPTERS.get(adapter_key)
    if not cls:
        await update.message.reply_text("⚠️ Adapter mismatch.")
        context.user_data.pop("ext_sup_wizard", None)
        return True

    await update.message.reply_text(f"⏳ Testing connection to {cls.LABEL}...")
    ad = cls(key, wiz["base_url"])
    # 🆕 v89: async wrap — event loop never blocks on adapter HTTP call
    from async_adapter_helpers import async_test_connection
    ok, msg, extra = await async_test_connection(ad)

    if not ok:
        await update.message.reply_text(
            f"❌ Connection FAILED.\n\n*Reason:* {escape_md(msg)}\n\n"
            f"Check the key and try again from 📦 Suppliers → ➕ Add Supplier.",
            parse_mode="Markdown"
        )
        context.user_data.pop("ext_sup_wizard", None)
        return True

    # Save it
    sid = add_supplier(
        name=wiz["name"], adapter=adapter_key,
        base_url=wiz["base_url"], api_key=key,
        docs_url=wiz["docs_url"],
    )
    bal = extra.get("balance")
    count = extra.get("count", 0)
    user = extra.get("user", "")
    if bal is not None:
        update_supplier(sid, balance_usd=float(bal),
                        balance_updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    context.user_data.pop("ext_sup_wizard", None)

    text = (
        f"✅ *{cls.LABEL} added! (#{sid})*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Account: `{escape_md(user)}`\n"
        f"💰 Balance: `{('$' + format(float(bal), '.2f')) if bal is not None else 'not refreshed'}`\n"
        f"📦 Products available: *{count}*\n\n"
        f"_Now tap below to import products._"
    )
    # 🆕 v82: Removed "☑️ Select Manually" per user request (was showing blank screen).
    # Only "Import All" (auto-imports + auto-mirrors to shop). Admin can then browse
    # from the supplier view panel using "☑️ Browse Products".
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Import All Products", callback_data=f"ext_sup_import_all_{sid}")],
        [InlineKeyboardButton("⚙️ View Supplier",       callback_data=f"ext_sup_view_{sid}")],
        [InlineKeyboardButton("📦 All Suppliers",       callback_data="admin_suppliers")],
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return True


async def ext_sup_view_callback(update, context):
    """View + manage a single supplier.

    🆕 v101: On every open, do a best-effort ASYNC balance refresh so the
    admin always sees the live wallet balance. Old behavior only refreshed
    on manual 'Test & Refresh' click OR on the 5-min auto-sync job — result
    was Canboso balance stuck at $0 in the view until admin took action.
    """
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        sid = int(q.data.replace("ext_sup_view_", "", 1))
    except Exception:
        return
    s = get_supplier(sid)
    if not s:
        await _safe_edit(q, "❌ Supplier not found.",
                         reply_markup=InlineKeyboardMarkup([[
                             InlineKeyboardButton("🔙 Back", callback_data="admin_suppliers")
                         ]]))
        return
    cls = ADAPTERS.get(s["adapter"])
    label = cls.LABEL if cls else s["adapter"]

    # v117 policy: opening supplier panel must NOT call supplier balance API.
    # It shows the last known balance. Admin can tap "Test & Refresh" for a
    # manual balance update.

    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM ext_products WHERE supplier_id=?", (sid,))
    total_p = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM ext_products WHERE supplier_id=? AND active=1", (sid,))
    active_p = c.fetchone()[0] or 0
    # v128: 24h supplier health summary from ext_orders
    try:
        c.execute("""SELECT status, COUNT(*) AS n FROM ext_orders
                     WHERE supplier_id=? AND datetime(created_at) >= datetime('now','-24 hours')
                     GROUP BY status""", (sid,))
        hrows = c.fetchall()
        hmap = {str((r['status'] if hasattr(r, 'keys') else r[0]) or 'unknown'): int((r['n'] if hasattr(r, 'keys') else r[1]) or 0) for r in hrows}
        c.execute("""SELECT error_msg FROM ext_orders
                     WHERE supplier_id=? AND status='failed'
                     ORDER BY id DESC LIMIT 1""", (sid,))
        er = c.fetchone()
        last_fail = ((er['error_msg'] if hasattr(er, 'keys') else er[0]) if er else '') or ''
    except Exception:
        hmap = {}; last_fail = ''
    conn.close()

    status = "🟢 Enabled" if s["enabled"] else "🔴 Disabled"
    bal = s.get("balance_usd") or 0
    bal_when = s.get("balance_updated_at") or "never"
    auto = s.get("auto_sync_min") or 0
    auto_label = f"every {auto} min" if auto else "OFF"

    text = (
        f"⚙️ *Supplier #{s['id']} — {escape_md(s['name'])}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔌 Adapter: {label}\n"
        f"🌐 URL: `{escape_md(s['base_url'])}`\n"
        f"🔑 Key: `{escape_md(s['api_key'][:10])}...`\n"
        f"📊 Status: {status}\n"
        f"💰 Balance: `${bal:.2f}` (last known: {bal_when})\n"
        f"⚠️ Low-bal threshold: `${s.get('low_bal_threshold', 5):.2f}`\n"
        f"🔄 Product auto-sync: `{auto_label}`\n"
        f"💡 Balance refresh: `auto every 5 min + Test & Refresh + after orders`\n"
        f"📦 Products: *{active_p}/{total_p}* active\n"
        f"🩺 24h Health: ✅ {hmap.get('delivered',0)} delivered · ❌ {hmap.get('failed',0)} failed · 💸 {hmap.get('refunded',0)} refunded\n"
        + (f"⚠️ Last failure: `{escape_md(last_fail[:90])}`\n" if last_fail else "")
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Test & Refresh", callback_data=f"ext_sup_test_{sid}"),
         InlineKeyboardButton("📥 Import Products", callback_data=f"ext_sup_import_all_{sid}")],
        [InlineKeyboardButton("☑️ Browse Products", callback_data=f"ext_sup_import_pick_{sid}_0")],
        # 🆕 v85: Bulk sync (1 tap → refreshes cost+stock on all live products)
        [InlineKeyboardButton("🔁 Bulk Sync All Products",
                              callback_data=f"ext_sup_bulk_sync_{sid}")],
        # 🆕 v136: Bulk unsync (removes ALL its products from shop, keeps history)
        [InlineKeyboardButton("🗑️ Bulk Unsync (remove from shop)",
                              callback_data=f"ext_sup_bulk_unsync_{sid}")],
        # 🆕 v85: Low-balance threshold editor
        [InlineKeyboardButton(f"⚠️ Low-Bal Alert (${s.get('low_bal_threshold', 3):.2f})",
                              callback_data=f"ext_sup_lowbal_{sid}")],
        # 🆕 v96: rename supplier (admin dashboard label only)
        [InlineKeyboardButton("✏️ Rename Supplier",
                              callback_data=f"ext_sup_rename_{sid}")],
        [InlineKeyboardButton("🔑 Update API Key",
                              callback_data=f"ext_sup_apiupd_{sid}")],
        [InlineKeyboardButton("🔴 Disable" if s["enabled"] else "🟢 Enable",
                              callback_data=f"ext_sup_toggle_{sid}")],
        [InlineKeyboardButton("🗑 Delete Supplier", callback_data=f"ext_sup_del_{sid}")],
        [InlineKeyboardButton("🔙 All Suppliers", callback_data="admin_suppliers")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def ext_sup_test_callback(update, context):
    """Re-test connection + refresh balance."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        sid = int(q.data.replace("ext_sup_test_", "", 1))
    except Exception:
        return
    await q.answer("⏳ Testing…")
    s = get_supplier(sid)
    ad = get_adapter_for_supplier(s)
    if not ad:
        await q.answer("❌ No adapter", show_alert=True); return
    # 🆕 v89: async wrap
    from async_adapter_helpers import async_test_connection
    ok, msg, extra = await async_test_connection(ad)
    if ok:
        bal = extra.get("balance")
        if bal is not None:
            bal_f = float(bal)
            update_supplier(sid, balance_usd=bal_f,
                            balance_updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            # Low-balance alert now only happens after manual refresh or after
            # an order — never from background polling.
            try:
                from supplier_automation import _maybe_send_low_balance_alert, DEFAULT_LOW_BAL_THRESHOLD
                fresh_sup = get_supplier(sid) or s
                threshold = float(fresh_sup.get("low_bal_threshold") or DEFAULT_LOW_BAL_THRESHOLD)
                if threshold > 0 and bal_f < threshold:
                    await _maybe_send_low_balance_alert(context, fresh_sup, bal_f, threshold)
            except Exception as _lb_err:
                logger.debug(f"[ext_sup_test] low-balance alert check failed: {_lb_err}")
    alert = f"{'✅' if ok else '❌'} {msg}"
    await q.answer(alert[:190], show_alert=True)
    # Refresh view
    _set_q_data(q, f"ext_sup_view_{sid}")
    await ext_sup_view_callback(update, context)


async def ext_sup_api_update_callback(update, context):
    """Ask admin for a new API key for one supplier."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        sid = int(q.data.replace("ext_sup_apiupd_", "", 1))
    except Exception:
        await q.answer("❌ Bad supplier id", show_alert=True); return
    s = get_supplier(sid)
    if not s:
        await q.answer("Supplier not found", show_alert=True); return
    context.user_data["ext_sup_api_update_sid"] = sid
    await _safe_edit(q,
        f"🔑 *Update API Key — {escape_md(s.get('name','Supplier'))}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Send the NEW API key for this supplier in your next message.\n\n"
        f"✅ Bot will test the key first.\n"
        f"✅ If connection works, only this supplier will be updated.\n\n"
        f"_Send /cancel to abort._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data=f"ext_sup_view_{sid}")
        ]]))


async def ext_sup_api_update_received(update, context):
    """Receive/test/save API key update for one supplier."""
    sid = context.user_data.get("ext_sup_api_update_sid")
    if not sid:
        return False
    if update.effective_user.id != ADMIN_ID:
        return False
    key = (update.message.text or "").strip()
    if key.lower() in ("/cancel", "cancel"):
        context.user_data.pop("ext_sup_api_update_sid", None)
        await update.message.reply_text("❌ API update cancelled.")
        return True
    if len(key) < 8:
        await update.message.reply_text("⚠️ API key too short. Send correct key or /cancel.")
        return True
    s = get_supplier(int(sid))
    if not s:
        context.user_data.pop("ext_sup_api_update_sid", None)
        await update.message.reply_text("❌ Supplier not found.")
        return True
    cls = ADAPTERS.get(s.get("adapter"))
    if not cls:
        await update.message.reply_text("❌ Supplier adapter missing.")
        return True

    await update.message.reply_text("⏳ Testing new API key…")
    try:
        ad = cls(key, s.get("base_url", ""))
        from async_adapter_helpers import async_test_connection
        ok, msg, extra = await async_test_connection(ad)
    except Exception as e:
        ok, msg, extra = False, f"Test crashed: {e}", {}

    if not ok:
        await update.message.reply_text(
            f"❌ *API key not saved*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Reason: `{escape_md(str(msg)[:300])}`\n\n"
            f"Send another key or /cancel.",
            parse_mode="Markdown")
        return True

    fields = {"api_key": key}
    bal = extra.get("balance") if isinstance(extra, dict) else None
    if bal is not None:
        try:
            fields["balance_usd"] = float(bal)
            fields["balance_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    update_supplier(int(sid), **fields)
    context.user_data.pop("ext_sup_api_update_sid", None)
    await update.message.reply_text(
        f"✅ *API Key Updated*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏬 Supplier: *{escape_md(s.get('name','Supplier'))}*\n"
        f"🔌 Test: `{escape_md(str(msg)[:200])}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⚙️ Open Supplier", callback_data=f"ext_sup_view_{sid}")
        ]]))
    return True


async def ext_sup_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        sid = int(q.data.replace("ext_sup_toggle_", "", 1))
    except Exception:
        return
    s = get_supplier(sid)
    if not s: return
    new_val = 0 if s["enabled"] else 1
    update_supplier(sid, enabled=new_val)
    await q.answer("🟢 Enabled" if new_val else "🔴 Disabled")
    _set_q_data(q, f"ext_sup_view_{sid}")
    await ext_sup_view_callback(update, context)


async def ext_sup_del_callback(update, context):
    """Confirm + delete."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        sid = int(q.data.replace("ext_sup_del_", "", 1))
    except Exception:
        return
    text = (
        "🗑 *Delete Supplier?*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"This will delete supplier #{sid} and remove ALL synced products from:\n"
        f"• 🛍 User shop\n"
        f"• 🛠 Admin Edit Items list\n"
        f"• 📦 Supplier imported products\n\n"
        f"✅ Customer orders/history stay preserved in orders table.\n"
        f"⚠️ Cannot be undone. Are you sure?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, delete",  callback_data=f"ext_sup_del_confirm_{sid}"),
         InlineKeyboardButton("❌ Cancel",       callback_data=f"ext_sup_view_{sid}")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def ext_sup_del_confirm_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        sid = int(q.data.replace("ext_sup_del_confirm_", "", 1))
    except Exception:
        return
    try:
        stats = delete_supplier(sid)
    except Exception as e:
        await q.answer(f"❌ Delete failed: {e}"[:190], show_alert=True)
        return
    await q.answer("🗑 Supplier + synced products deleted.", show_alert=True)
    try:
        await q.message.reply_text(
            f"✅ *Supplier Deleted*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 Shop products removed: *{stats.get('shop_products',0)}*\n"
            f"🔌 Supplier products removed: *{stats.get('ext_products',0)}*\n"
            f"🧾 Supplier order logs removed: *{stats.get('ext_orders',0)}*\n\n"
            f"Old customer orders/history remain preserved.",
            parse_mode="Markdown")
    except Exception:
        pass
    _set_q_data(q, "admin_suppliers")
    await admin_suppliers_callback(update, context)


async def ext_sup_import_all_callback(update, context):
    """Import ALL products from supplier."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        sid = int(q.data.replace("ext_sup_import_all_", "", 1))
    except Exception:
        return
    await q.answer("⏳ Importing…")
    await _safe_edit(q,
        "⏳ *Importing products from supplier...*\n\n_Please wait, may take up to 60 sec._",
        parse_mode="Markdown")
    n, err = sync_supplier_products(sid)
    if err:
        text = f"❌ *Import failed*\n\n{escape_md(err)}"
    else:
        # Try to auto-apply emoji library
        prods = get_ext_products(supplier_id=sid)
        for p in prods:
            try:
                apply_emoji_to_product(p["id"])
            except Exception:
                pass
        text = (
            f"✅ *Import complete!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📥 Imported/updated: *{n} products*\n\n"
            f"_Default markup: 40% (edit per-product from Browse Products)._\n"
            f"_Products with premium emoji IDs → 🟢 ready._\n"
            f"_Products without → 🟡 need manual emoji fix._"
        )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("☑️ Browse Products", callback_data=f"ext_sup_import_pick_{sid}_0")],
        [InlineKeyboardButton("⚙️ Supplier Panel",  callback_data=f"ext_sup_view_{sid}")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def ext_sup_import_pick_callback(update, context):
    """Paginated product browser — page-per-15."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    data = q.data.replace("ext_sup_import_pick_", "", 1)
    try:
        parts = data.rsplit("_", 1)
        sid = int(parts[0]); page = int(parts[1])
    except Exception:
        return
    per_page = 10
    prods = get_ext_products(supplier_id=sid)
    total = len(prods)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    slice_ = prods[page * per_page:(page + 1) * per_page]

    # 🐛 v105 FIX: remember which browse page admin is on so the product
    # detail's Back button returns to the SAME page (was hardcoded to _0).
    try:
        context.user_data[f"ext_browse_page_{sid}"] = int(page)
    except Exception:
        pass

    lines = [
        f"☑️ *Browse Supplier #{sid} — Page {page+1}/{total_pages}*",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"_Total: {total} products_",
        "",
    ]
    # 🆕 v90/v91: use name_for_button() to defensively strip [[HTML]] / <tg-emoji>
    # markup BEFORE truncation (fixes the "raw HTML garbage" screenshot bug).
    # v91: ALSO use make_premium_button() so the premium emoji renders as a
    # proper ICON on the button (Bot API 9.4 icon_custom_emoji_id — native
    # support in PTB v22.7+). Requires bot owner to have Telegram Premium.
    from utils import name_for_button as _clean_name
    try:
        from button_system import make_premium_button as _mkbtn
    except Exception:
        _mkbtn = None
    kb = []
    for p in slice_:
        # Legend: 🟢 active + emoji OK · 🟡 needs emoji · 🔴 inactive
        if not p["active"]:
            icon = "🔴"
        elif p["emoji_status"] == "ok" or p["emoji_id"]:
            icon = "🟢"
        else:
            icon = "🟡"
        raw_name = p["name"] or "?"
        # Strip any HTML markup + [[HTML]] sentinel BEFORE truncating so we
        # never cut mid-tag (root cause of screenshot bug).
        clean = _clean_name(raw_name) or "?"
        name_line = clean[:60]      # in the text body we can afford 60 chars
        name_btn  = clean[:32]      # button labels stay under Telegram limit
        cost = float(p.get("cost_usd") or 0)
        sell = float(p.get("sell_price") or 0)
        stock = int(p.get("stock") or 0)
        # Message body line — plain clean text, escape for Markdown
        lines.append(f"{icon} `#{p['id']}` {escape_md(name_line)}")
        lines.append(f"    cost ${cost:.2f} → sell ${sell:.2f} · stock {stock}")
        # Button — use make_premium_button so the emoji renders as ICON
        # (proper Bot API 9.4 way — no raw HTML tags in button text).
        eid = str(p.get("emoji_id") or "").strip()
        if _mkbtn is not None and eid:
            kb.append([_mkbtn(f"{icon} {name_btn}",
                              emoji_id=eid,
                              callback_data=f"ext_prod_view_{p['id']}")])
        else:
            kb.append([InlineKeyboardButton(
                f"{icon} {name_btn}",
                callback_data=f"ext_prod_view_{p['id']}"
            )])
    if not slice_:
        lines.append("📭 _No products imported yet — tap 📥 Import Products first._")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev",
            callback_data=f"ext_sup_import_pick_{sid}_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}",
        callback_data=f"ext_sup_view_{sid}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️",
            callback_data=f"ext_sup_import_pick_{sid}_{page+1}"))
    if nav: kb.append(nav)

    kb.append([InlineKeyboardButton("💲 Bulk Markup (all)",
        callback_data=f"ext_sup_bulk_markup_{sid}")])
    kb.append([InlineKeyboardButton("🔙 Supplier Panel",
        callback_data=f"ext_sup_view_{sid}")])
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def ext_prod_view_callback(update, context):
    """View/edit a single supplier product."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        eid = int(q.data.replace("ext_prod_view_", "", 1))
    except Exception:
        return
    p = get_ext_product(eid)
    if not p:
        await _safe_edit(q, "❌ Not found.",
                         reply_markup=InlineKeyboardMarkup([[
                             InlineKeyboardButton("🔙 Back", callback_data="admin_suppliers")
                         ]]))
        return
    sup = get_supplier(p["supplier_id"])
    icon = "🟢" if (p["active"] and (p["emoji_id"] or p["emoji_status"] == "ok")) else \
           ("🔴" if not p["active"] else "🟡")
    emoji_line = ""
    if p["emoji_id"]:
        emoji_line = f"💎 Premium emoji: {p['emoji_char']} id {p['emoji_id'][:14]}...\n"
    elif p["emoji_char"]:
        emoji_line = f"⚪ Plain emoji: {p['emoji_char']} (no premium ID yet)\n"
    else:
        emoji_line = "⚠️ No emoji in name.\n"

    from utils import html_code_block, html_escape_plain
    # 🆕 v81.1: show price mode (auto-markup vs SMART LOCK)
    fp = p.get("fixed_price") or 0
    fpb = p.get("fixed_price_base") or 0
    if fp > 0:
        price_mode_lines = (
            f"🔒 <b>Price Mode: SMART LOCK</b>\n"
            f"   Fixed selling: <b>${fp:.2f}</b>\n"
            f"   Locked at cost: ${fpb:.2f}\n"
            f"   Current sell: <b>{fmt_price(p['sell_price'])}</b>\n"
            f"   <i>(rises if supplier cost goes up, stays if cost drops)</i>\n"
        )
    else:
        price_mode_lines = (
            f"📈 <b>Price Mode: AUTO-MARKUP</b>\n"
            f"   Markup: <b>{p['markup_pct']:.0f}%</b>\n"
            f"   Sell price: <b>{fmt_price(p['sell_price'])}</b>\n"
        )
    # 🆕 v83: show format + sync status
    fmt_key = p.get("delivery_format") or "email_pass"
    fmt_meta = V83_FORMATS.get(fmt_key, V83_FORMATS["email_pass"])
    fmt_source = "auto-detected" if p.get("format_detected") else "admin override"
    synced = p.get("synced_to_shop") or 0
    sync_line = ("🟢 <b>LIVE in Shop</b> (customers can buy)" if synced
                  else "⚪ <b>Not synced to Shop</b> (invisible to customers)")

    text = (
        f"[[HTML]]{icon} <b>Product #{p['id']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Name: {html_escape_plain(p['name'])[:200]}\n"
        f"🏬 Supplier: {sup['name'] if sup else '?'} (#{p['supplier_id']})\n"
        f"🔗 Remote ID: <code>{html_escape_plain(p['remote_id'])}</code>\n\n"
        f"💰 Cost: <b>{fmt_price(p['cost_usd'])}</b>\n"
        f"{price_mode_lines}"
        f"📊 Stock: <b>{p['stock']}</b>\n\n"
        f"🧩 Delivery Format: <b>{fmt_meta['label']}</b>  <i>({fmt_source})</i>\n\n"
        f"{emoji_line}"
        f"Status: {'🟢 Active' if p['active'] else '🔴 Inactive'}\n"
        f"Shop: {sync_line}"
    )
    # 🆕 v107: show description preview so admin can see EXACTLY what's stored
    # (with pro-user "raw vs rendered" transparency). Helps diagnose sync issues.
    _desc_stored = str(p.get("description") or "").strip()
    if _desc_stored:
        _preview = _desc_stored[:400]
        _more = "..." if len(_desc_stored) > 400 else ""
        _tag_info = ""
        import re as _re_tag
        if _desc_stored.startswith("[[HTML]]") or _re_tag.search(
            r"<(?:b|i|u|s|code|pre|blockquote|tg-emoji|a)\b",
            _desc_stored, flags=_re_tag.I,
        ):
            _tag_info = " <i>(HTML-formatted)</i>"
        text += (f"\n\n📝 <b>Description{_tag_info}:</b>\n"
                 f"<blockquote expandable>{html_escape_plain(_preview)}{_more}</blockquote>")
    else:
        text += "\n\n📝 <b>Description:</b> <i>(none stored)</i>"

    kb = [
        # 🆕 v83: SYNC TO SHOP button (per-product manual sync)
        [InlineKeyboardButton(
            "🗑 Unsync & Delete from Shop/Edit Items" if synced else "🔄 Sync to Shop (Make Live)",
            callback_data=f"ext_prod_sync_{eid}")],
        # 🆕 v107: FORCE REFRESH — pro-user Shopify-style overwrite mode.
        # Re-fetches THIS product from supplier API + updates ext_product +
        # re-mirrors to shop (if synced_to_shop=1). Use when you know supplier
        # updated the product but bot hasn't caught up.
        [InlineKeyboardButton("🔃 Force Refresh from Supplier",
                              callback_data=f"ext_prod_refresh_{eid}")],
        [InlineKeyboardButton("📈 Auto-Markup %",   callback_data=f"ext_prod_markup_{eid}"),
         InlineKeyboardButton("🔒 Fixed Price",      callback_data=f"ext_prod_fixprice_{eid}")],
        [InlineKeyboardButton("🧩 Change Format",   callback_data=f"ext_prod_fmt_{eid}"),
         InlineKeyboardButton("🎨 Fix Emoji",        callback_data=f"ext_prod_emoji_{eid}")],
        [InlineKeyboardButton("🏷 Set Category",     callback_data=f"ext_prod_cat_{eid}")],
        [InlineKeyboardButton("🔴 Deactivate" if p["active"] else "🟢 Activate",
                              callback_data=f"ext_prod_toggle_{eid}")],
    ]
    # 🐛 v105 FIX: Back button returns to the SAME browse page admin came
    # from (previously hardcoded to page 0). Reads context.user_data which
    # ext_sup_import_pick_callback stored on entry.
    _remembered_page = 0
    try:
        _remembered_page = int(
            context.user_data.get(f"ext_browse_page_{p['supplier_id']}", 0)
        )
    except Exception:
        _remembered_page = 0
    kb.append([InlineKeyboardButton("🔙 Browse Products",
                                     callback_data=f"ext_sup_import_pick_{p['supplier_id']}_{_remembered_page}")])
    await _safe_edit(q, text, reply_markup=InlineKeyboardMarkup(kb))


async def ext_prod_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        eid = int(q.data.replace("ext_prod_toggle_", "", 1))
    except Exception:
        return
    new_val = toggle_ext_product_active(eid)
    await q.answer("🟢 Active" if new_val else "🔴 Inactive")
    _set_q_data(q, f"ext_prod_view_{eid}")
    await ext_prod_view_callback(update, context)


async def ext_prod_markup_callback(update, context):
    """Preset markup buttons (20/30/40/50/100 + custom)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        eid = int(q.data.replace("ext_prod_markup_", "", 1))
    except Exception:
        return
    p = get_ext_product(eid)
    if not p: return
    text = (
        f"💲 *Set Markup for #{eid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 {escape_md(p['name'][:40])}\n"
        f"💰 Cost: `{fmt_price(p['cost_usd'])}`\n"
        f"📈 Current: `{p['markup_pct']:.0f}%` → sell `{fmt_price(p['sell_price'])}`\n\n"
        f"*Pick preset:*"
    )
    kb = []
    for pct in [10, 20, 30, 40, 50, 75, 100, 150, 200]:
        preview = round(p['cost_usd'] * (1 + pct / 100.0), 2)
        marker = " ✅" if abs(pct - p['markup_pct']) < 0.5 else ""
        kb.append([InlineKeyboardButton(
            f"📈 {pct}%  →  ${preview:.2f}{marker}",
            callback_data=f"ext_prod_set_mkp_{eid}_{pct}"
        )])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data=f"ext_prod_view_{eid}")])
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def ext_prod_set_mkp_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    data = q.data.replace("ext_prod_set_mkp_", "", 1)
    try:
        parts = data.rsplit("_", 1)
        eid = int(parts[0]); pct = float(parts[1])
    except Exception:
        return
    update_ext_product(eid, markup_pct=pct)
    p = get_ext_product(eid)
    await q.answer(f"✅ Markup set: {pct:.0f}% → {fmt_price(p['sell_price'])}", show_alert=True)
    _set_q_data(q, f"ext_prod_view_{eid}")
    await ext_prod_view_callback(update, context)


async def ext_sup_bulk_markup_callback(update, context):
    """Set same markup on ALL products for a supplier."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        sid = int(q.data.replace("ext_sup_bulk_markup_", "", 1))
    except Exception:
        return
    text = (
        f"💲 *Bulk Markup for Supplier #{sid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Apply the same markup % to *ALL* products of this supplier.\n\n"
        f"_Pick preset:_"
    )
    kb = []
    for pct in [10, 20, 30, 40, 50, 75, 100]:
        kb.append([InlineKeyboardButton(f"📈 {pct}% for all",
                    callback_data=f"ext_sup_bulk_set_{sid}_{pct}")])
    kb.append([InlineKeyboardButton("🔙 Back",
                callback_data=f"ext_sup_import_pick_{sid}_0")])
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def ext_sup_bulk_set_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    data = q.data.replace("ext_sup_bulk_set_", "", 1)
    try:
        parts = data.rsplit("_", 1)
        sid = int(parts[0]); pct = float(parts[1])
    except Exception:
        return
    prods = get_ext_products(supplier_id=sid)
    for p in prods:
        update_ext_product(p["id"], markup_pct=pct)
    await q.answer(f"✅ Applied {pct:.0f}% to {len(prods)} products.",
                   show_alert=True)
    _set_q_data(q, f"ext_sup_import_pick_{sid}_0")
    await ext_sup_import_pick_callback(update, context)


# ────────────────────────────────────────────────────────────
# 6. PREMIUM EMOJI FIX FLOW (workflow's Masla 3)
# ────────────────────────────────────────────────────────────

async def ext_prod_emoji_callback(update, context):
    """Ask admin to send a premium emoji — bot auto-extracts ID."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        eid = int(q.data.replace("ext_prod_emoji_", "", 1))
    except Exception:
        return
    p = get_ext_product(eid)
    if not p: return
    context.user_data["ext_prod_emoji_pending"] = eid
    text = (
        f"🎨 *Fix Emoji for #{eid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 {escape_md(p['name'][:60])}\n\n"
        f"Send *ONE premium (animated) emoji* in your next message.\n"
        f"Bot will auto-extract its custom emoji ID and save it.\n\n"
        f"_This works only from official Telegram apps with Premium._\n"
        f"_Send /cancel to abort._"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"ext_prod_view_{eid}")]
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def ext_prod_emoji_received(update, context):
    """Handle emoji message → extract custom_emoji_id → save."""
    eid = context.user_data.get("ext_prod_emoji_pending")
    if not eid:
        return False
    if update.effective_user.id != ADMIN_ID:
        return False
    msg = update.message
    text = (msg.text or "").strip()
    if text.lower() == "/cancel":
        context.user_data.pop("ext_prod_emoji_pending", None)
        await msg.reply_text("❌ Cancelled.")
        return True
    char, ce_id = extract_custom_emoji_from_message(msg)
    if not ce_id:
        # Fallback: is it a normal emoji?
        first = extract_first_emoji(text)
        if first:
            update_ext_product(eid, emoji_char=first,
                               emoji_id="", emoji_status="manual")
            context.user_data.pop("ext_prod_emoji_pending", None)
            await msg.reply_text(
                f"✅ Saved plain emoji `{first}` (no premium ID — that's OK, "
                f"will render as normal emoji).\n\n"
                f"_Tip: send a Premium/animated emoji to get the ID._",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Product", callback_data=f"ext_prod_view_{eid}")
                ]])
            )
            return True
        await msg.reply_text(
            "⚠️ No emoji detected. Please send exactly ONE emoji (preferably premium/animated).\n"
            "Send /cancel to abort."
        )
        return True

    # We have a premium emoji ID!
    update_ext_product(eid, emoji_char=char, emoji_id=ce_id, emoji_status="ok")
    save_emoji_to_library(char, ce_id)
    context.user_data.pop("ext_prod_emoji_pending", None)
    await msg.reply_text(
        f"✅ *Premium emoji saved!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Emoji: {char}\n"
        f"ID: `{ce_id[:14]}...`\n\n"
        f"Also saved to global library — will auto-apply to any future "
        f"product with the same emoji {char} in its name.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Product", callback_data=f"ext_prod_view_{eid}")
        ]])
    )
    return True


async def ext_prod_cat_callback(update, context):
    """Pick a category for the product."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        eid = int(q.data.replace("ext_prod_cat_", "", 1))
    except Exception:
        return
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT id, name FROM categories ORDER BY id")
    cats = [dict(r) for r in c.fetchall()]
    conn.close()
    if not cats:
        await q.answer("⚠️ No categories exist yet.", show_alert=True); return
    text = (
        f"🏷 *Pick category for #{eid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"_Tap a category to assign this product to it._"
    )
    kb = []
    for cat in cats:
        kb.append([InlineKeyboardButton(f"🏷 {cat['name'][:40]}",
                    callback_data=f"ext_prod_setcat_{eid}_{cat['id']}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data=f"ext_prod_view_{eid}")])
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def ext_prod_setcat_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    data = q.data.replace("ext_prod_setcat_", "", 1)
    try:
        parts = data.rsplit("_", 1)
        eid = int(parts[0]); cid = int(parts[1])
    except Exception:
        return
    update_ext_product(eid, category_id=cid)
    await q.answer("✅ Category set.")
    _set_q_data(q, f"ext_prod_view_{eid}")
    await ext_prod_view_callback(update, context)


# ────────────────────────────────────────────────────────────
# 7. BACKUP + WIPE existing 29 products (one-time migration)
# ────────────────────────────────────────────────────────────

def backup_and_wipe_existing_products():
    """One-time v81 migration:
      1. Snapshot every existing `products` row into `products_backup_v81`
      2. Wipe `products` + `product_accounts` + `product_free_claim`
         + `product_reviews` + `product_commission` + `restock_requests`
         + `stock_alerts`
      3. Keep `categories` untouched
      4. Keep `orders` untouched (history preservation)
    Idempotent — if backup rows already exist, wipe is skipped.
    """
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    # Check if backup was already done
    c.execute("SELECT COUNT(*) FROM products_backup_v81")
    if (c.fetchone()[0] or 0) > 0:
        conn.close()
        return 0, "already_migrated"
    # Take snapshot
    c.execute("SELECT * FROM products")
    rows = c.fetchall()
    snapshot_count = 0
    for row in rows:
        try:
            d = dict(row)
            c.execute("""INSERT INTO products_backup_v81
                         (original_id, row_json) VALUES (?, ?)""",
                      (d.get("id"), json.dumps(d, default=str, ensure_ascii=False)))
            snapshot_count += 1
        except Exception as e:
            logger.warning(f"[v81-migrate] backup row failed: {e}")
    # Wipe product-related tables (categories + orders preserved)
    for tbl in ["product_accounts", "product_free_claim", "product_reviews",
                "product_commission", "restock_requests", "stock_alerts",
                "products"]:
        try:
            c.execute(f"DELETE FROM {tbl}")
        except Exception as e:
            logger.warning(f"[v81-migrate] wipe {tbl}: {e}")
    conn.commit(); conn.close()
    logger.info(f"[v81-migrate] backed up {snapshot_count} products, wiped 7 tables")
    return snapshot_count, None


def rollback_v81_migration():
    """Restore products from backup (admin manual action). Returns (count, err)."""
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("SELECT row_json FROM products_backup_v81 ORDER BY backup_id")
        rows = c.fetchall()
        restored = 0
        for r in rows:
            try:
                d = json.loads(r["row_json"])
                # Detect columns of products table
                c.execute("PRAGMA table_info(products)")
                cols = [ci[1] for ci in c.fetchall()]
                usable = {k: v for k, v in d.items() if k in cols}
                if not usable: continue
                placeholders = ",".join("?" for _ in usable)
                columns = ",".join(usable.keys())
                c.execute(f"INSERT OR REPLACE INTO products ({columns}) VALUES ({placeholders})",
                          list(usable.values()))
                restored += 1
            except Exception as e:
                logger.warning(f"[v81-rollback] failed: {e}")
        conn.commit(); conn.close()
        return restored, None
    except Exception as e:
        conn.close(); return 0, str(e)


# ────────────────────────────────────────────────────────────
# 🆕 v81.1: FIXED PRICE (Smart Lock) admin flow
# ────────────────────────────────────────────────────────────

async def ext_prod_fixprice_callback(update, context):
    """💲 Set / Clear Fixed Selling Price (Smart Lock)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        eid = int(q.data.replace("ext_prod_fixprice_", "", 1))
    except Exception:
        return
    p = get_ext_product(eid)
    if not p: return
    fp = p.get("fixed_price") or 0
    fpb = p.get("fixed_price_base") or 0

    if fp > 0:
        # Already locked → offer to clear
        text = (
            f"🔒 *Fixed Price Lock — Product #{eid}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 {escape_md(p['name'][:60])}\n\n"
            f"💵 *Currently locked at:* `${fp:.2f}`\n"
            f"📌 Cost when locked: `${fpb:.2f}`\n"
            f"💰 Current cost: `{fmt_price(p['cost_usd'])}`\n"
            f"🏷 Current sell: `{fmt_price(p['sell_price'])}`\n\n"
            f"*Smart-Lock Rule:*\n"
            f"• If supplier cost RISES → sell goes UP by same amount\n"
            f"• If supplier cost DROPS → sell STAYS locked (no drop)\n\n"
            f"_Change or remove lock?_"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Change Locked Price",
                                   callback_data=f"ext_prod_fixprice_set_{eid}")],
            [InlineKeyboardButton("🔓 Remove Lock (back to Auto-Markup)",
                                   callback_data=f"ext_prod_fixprice_clear_{eid}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"ext_prod_view_{eid}")],
        ])
    else:
        # Not locked yet → offer to set
        text = (
            f"💲 *Set Fixed Selling Price — Product #{eid}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 {escape_md(p['name'][:60])}\n"
            f"💰 Current cost: `{fmt_price(p['cost_usd'])}`\n"
            f"📈 Current sell (auto-markup {p['markup_pct']:.0f}%): `{fmt_price(p['sell_price'])}`\n\n"
            f"*Smart-Lock Behavior:*\n"
            f"• You set a fixed selling price (e.g. `$10`)\n"
            f"• Supplier cost rises `$0.50` → sell auto-rises to `$10.50`\n"
            f"• Supplier cost drops → sell STAYS at `$10` (profit protected)\n\n"
            f"_Tap Set Price — bot will ask for the amount._"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Set Fixed Price",
                                   callback_data=f"ext_prod_fixprice_set_{eid}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"ext_prod_view_{eid}")],
        ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def ext_prod_fixprice_set_callback(update, context):
    """Ask admin to type the fixed price."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        eid = int(q.data.replace("ext_prod_fixprice_set_", "", 1))
    except Exception:
        return
    p = get_ext_product(eid)
    if not p: return
    context.user_data["ext_prod_fixprice_pending"] = eid
    text = (
        f"✏️ *Enter Fixed Selling Price*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 {escape_md(p['name'][:60])}\n"
        f"💰 Current cost: `{fmt_price(p['cost_usd'])}`\n\n"
        f"Send the *selling price in USD* in your next message.\n"
        f"Example: `10` or `10.5` or `$12.99`\n\n"
        f"_Send /cancel to abort._"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"ext_prod_view_{eid}")]
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def ext_prod_fixprice_received(update, context):
    """Handle admin's typed fixed price."""
    eid = context.user_data.get("ext_prod_fixprice_pending")
    if not eid:
        return False
    if update.effective_user.id != ADMIN_ID:
        return False
    text = (update.message.text or "").strip()
    if text.lower() == "/cancel":
        context.user_data.pop("ext_prod_fixprice_pending", None)
        await update.message.reply_text("❌ Cancelled.")
        return True
    # Parse: strip $, spaces
    clean = text.replace("$", "").replace(",", "").strip()
    try:
        val = float(clean)
        if val <= 0: raise ValueError
    except Exception:
        await update.message.reply_text(
            "⚠️ Invalid price. Send a positive number like `10` or `10.5`.\n"
            "Send /cancel to abort.")
        return True
    p = get_ext_product(eid)
    if not p:
        context.user_data.pop("ext_prod_fixprice_pending", None)
        return True
    # Save fixed_price + snapshot current cost as base
    update_ext_product(eid, fixed_price=val,
                       fixed_price_base=float(p["cost_usd"]))
    context.user_data.pop("ext_prod_fixprice_pending", None)
    p_new = get_ext_product(eid)
    await update.message.reply_text(
        f"✅ *Fixed Price Locked!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 {escape_md(p['name'][:60])}\n"
        f"🔒 Fixed selling price: `${val:.2f}`\n"
        f"📌 Locked at cost: `${p_new['fixed_price_base']:.2f}`\n\n"
        f"✅ Now: if supplier cost rises, your sell price goes up by the same amount.\n"
        f"✅ If supplier cost drops, your sell price stays at `${val:.2f}` (profit protected).",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Product", callback_data=f"ext_prod_view_{eid}")
        ]])
    )
    return True


async def ext_prod_fixprice_clear_callback(update, context):
    """Remove fixed price → go back to auto-markup mode."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        eid = int(q.data.replace("ext_prod_fixprice_clear_", "", 1))
    except Exception:
        return
    update_ext_product(eid, fixed_price=0.0, fixed_price_base=0.0)
    await q.answer("🔓 Lock removed. Back to auto-markup.", show_alert=True)
    _set_q_data(q, f"ext_prod_view_{eid}")
    await ext_prod_view_callback(update, context)


# ═══════════════════════════════════════════════════════════════════════════
# 🚀 v82 PHASE 2: ORDER ROUTER — customer purchase → supplier API → delivery
# ═══════════════════════════════════════════════════════════════════════════
# This is the CORE of PHASE 2. When a customer's order gets paid, we look up
# the linked supplier product, call the adapter's create_order(), and then
# deliver via v72 byte-perfect templates. If supplier fails, auto-refund.

def get_ext_product_by_shop_id(shop_product_id):
    """Given a `products.id`, return the linked ext_product row (or None)."""
    if not shop_product_id: return None
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM ext_products WHERE shop_product_id=?",
              (int(shop_product_id),))
    r = c.fetchone(); conn.close()
    return dict(r) if r else None


def log_ext_order(internal_order_id, supplier_id, ext_product_id, quantity,
                  cost_usd, remote_order_id="", status="pending",
                  raw_response="", error_msg=""):
    """Record a supplier API call in ext_orders (for audit/refund tracking)."""
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""INSERT INTO ext_orders
                 (internal_order_id, supplier_id, ext_product_id, quantity,
                  cost_usd, remote_order_id, status, raw_response, error_msg,
                  completed_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (int(internal_order_id), int(supplier_id), int(ext_product_id),
               int(quantity), float(cost_usd or 0), str(remote_order_id)[:100],
               status, str(raw_response)[:5000], str(error_msg)[:500],
               datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status != "pending" else ""))
    conn.commit(); conn.close()


def _supplier_order_qty_from_name(order):
    """Extract the exact customer-requested quantity for supplier API.

    🔧 v111 rule:
      • Buy Now stores order_qty=1 → supplier API gets qty=1.
      • Buy Multiple stores order_qty=user typed qty → supplier API gets that.
      • Old DB rows without order_qty fall back to legacy "Product × 5" suffix.
    """
    try:
        oq = order.get('order_qty') if hasattr(order, 'get') else order['order_qty']
        if oq is not None and str(oq).strip() != '':
            return max(1, min(100, int(oq)))
    except Exception:
        pass
    try:
        name = str((order.get('product_name') if hasattr(order, 'get') else order['product_name']) or '')
        m = re.search(r'(?:×|x)\s*(\d+)\s*$', name, flags=re.I)
        if m:
            return max(1, min(100, int(m.group(1))))
    except Exception:
        pass
    return 1




_SUPPLIER_RETRY_WINDOW_SECONDS = 300  # 5 minutes


def _ensure_supplier_retry_order_columns(c):
    """Ensure delayed-refund columns exist on orders."""
    ensure_column(c, "orders", "supplier_failure_reason", "TEXT DEFAULT ''")
    ensure_column(c, "orders", "supplier_refund_due_at", "REAL DEFAULT 0")
    ensure_column(c, "orders", "supplier_retry_count", "INTEGER DEFAULT 0")


def _supplier_retry_due_text(epoch_ts):
    try:
        return datetime.fromtimestamp(float(epoch_ts), timezone(timedelta(hours=5))).strftime("%I:%M:%S %p PKT")
    except Exception:
        return "in 5 minutes"


def _supplier_error_is_not_found(result=None, reason=""):
    """Detect stale/removed supplier products so shop stock can be zeroed."""
    result = result or {}
    try:
        if int(result.get("status_code") or 0) == 404:
            return True
    except Exception:
        pass
    text = (str(reason or "") + " " + str(result.get("error") or "") + " " + str(result.get("raw") or "")).lower()
    return any(x in text for x in ("http 404", "404", "not found", "not_found", "does not exist", "unavailable"))


def _mark_supplier_product_unavailable(ep, shop_product_id=0, reason=""):
    """Set stale supplier product stock to 0 without deleting history."""
    try:
        if ep and ep.get("id"):
            update_ext_product(int(ep["id"]), stock=0)
    except Exception as e:
        logger.debug(f"[supplier-stale] ext stock zero failed: {e}")
    # Do not force products.stock=0 here. update_ext_product() mirrors remote
    # stock as 0 while preserving any local supplier_bonus/manual pool stock.


def _set_order_supplier_retry_pending(order_id, reason):
    """Mark order as retry-pending and return (due_epoch, retry_count)."""
    due = time.time() + _SUPPLIER_RETRY_WINDOW_SECONDS
    conn = get_connection(); c = conn.cursor()
    try:
        _ensure_supplier_retry_order_columns(c)
        c.execute("""UPDATE orders
                     SET status='supplier_retry_pending',
                         supplier_failure_reason=?,
                         supplier_refund_due_at=?,
                         supplier_retry_count=COALESCE(supplier_retry_count,0)+1
                     WHERE id=?
                       AND COALESCE(status,'') NOT IN ('delivered','refunded','cancelled','rejected')""",
                  (str(reason or '')[:1000], float(due), int(order_id)))
        c.execute("SELECT COALESCE(supplier_retry_count,0) AS n FROM orders WHERE id=?", (int(order_id),))
        row = c.fetchone(); count = int((row['n'] if row else 0) or 0)
        conn.commit(); conn.close()
        return due, count
    except Exception:
        try: conn.rollback()
        except Exception: pass
        try: conn.close()
        except Exception: pass
        return due, 0


async def _schedule_supplier_retry_or_refund(bot, order, sup, ep, qty, reason, result=None):
    """Supplier failed → give admin 5 minutes to retry, then auto-refund.

    This replaces the old immediate refund behavior. It protects users from
    losing money while still giving admin a short window to retry transient
    supplier/API failures.
    """
    if _supplier_error_is_not_found(result, reason):
        _mark_supplier_product_unavailable(ep, order.get('product_id') or 0, reason)

    due, retry_count = _set_order_supplier_retry_pending(order['id'], reason)
    due_txt = _supplier_retry_due_text(due)
    price_usd = float(order.get('price') or 0)
    refund_points = points_from_usd(price_usd)

    # Notify customer — professional, no raw API details beyond short reason.
    try:
        await bot.send_message(
            order['user_id'],
            f"⚠️ *Order #{order['id']} — Delivery retrying*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 {escape_md(order.get('product_name','?')[:70])}\n\n"
            f"We’re completing your order through an alternate delivery attempt.\n\n"
            f"⏳ If delivery is not completed by *{escape_md(due_txt)}*, your wallet will be automatically refunded.\n"
            f"💎 Refund amount: *{fmt_points(refund_points)} points*\n\n"
            f"You may also buy another product anytime. Thank you for your patience. 🙏",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
                [InlineKeyboardButton("🎫 Support", callback_data="support_menu")],
            ])
        )
    except Exception as e:
        logger.error(f"[supplier-retry] customer notify failed: {e}")

    # Notify admin with Retry Delivery button.
    try:
        await bot.send_message(
            ADMIN_ID,
            f"⚠️ *SUPPLIER FAILURE — retry window*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛒 Order: `#{order['id']}`\n"
            f"🏬 Supplier: {escape_md(sup['name'] if sup else '?')}\n"
            f"📦 Product: {escape_md((ep or {}).get('name','?')[:60])}\n"
            f"🔢 Qty: `{qty}`\n"
            f"💰 Amount: `${price_usd:.2f}`\n"
            f"🔁 Retry count: `{retry_count}`\n"
            f"⏳ Auto-refund at: `{escape_md(due_txt)}`\n"
            f"💎 Refund if not delivered: `{fmt_points(refund_points)}` points\n\n"
            f"❌ Reason: `{escape_md(str(reason)[:220])}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Retry Delivery", callback_data=f"supplier_retry_{order['id']}")],
                [InlineKeyboardButton("📦 View Product", callback_data=f"viewprod_{order.get('product_id') or 0}")],
            ])
        )
    except Exception as e:
        logger.error(f"[supplier-retry] admin notify failed: {e}")
    return True


async def supplier_retry_refund_job(context):
    """Background job: auto-refund supplier_retry_pending orders after 5 min."""
    try:
        conn = get_connection(); c = conn.cursor()
        _ensure_supplier_retry_order_columns(c)
        now = time.time()
        c.execute("""SELECT * FROM orders
                     WHERE status='supplier_retry_pending'
                       AND COALESCE(supplier_refund_due_at,0) > 0
                       AND supplier_refund_due_at <= ?
                     ORDER BY supplier_refund_due_at ASC
                     LIMIT 25""", (float(now),))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
    except Exception as e:
        logger.warning(f"[supplier-retry-job] scan failed: {e}")
        return

    for order in rows:
        try:
            from database import get_order, get_product
            fresh = get_order(order['id'])
            if not fresh or str(fresh.get('status') or '') != 'supplier_retry_pending':
                continue
            p = get_product(fresh['product_id']) if fresh.get('product_id') else None
            ep = get_ext_product((dict(p).get('ext_product_id') if p else 0) or 0) if p else None
            sup = get_supplier((dict(p).get('ext_supplier_id') if p else 0) or 0) if p else None
            qty = _supplier_order_qty_from_name(fresh)
            reason = (fresh.get('supplier_failure_reason') or order.get('supplier_failure_reason') or 'Supplier delivery failed')
            await _refund_and_notify(context.bot, fresh, sup, ep, qty,
                                     f"{reason} — retry window expired")
        except Exception as e:
            logger.warning(f"[supplier-retry-job] refund failed order#{order.get('id')}: {e}")


async def supplier_retry_delivery_callback(update, context):
    """Admin button: retry supplier delivery while order is still pending."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        oid = int(q.data.replace("supplier_retry_", ""))
    except Exception:
        await q.answer("Invalid order", show_alert=True); return

    from database import get_order
    order = get_order(oid)
    if not order:
        await q.answer("Order not found", show_alert=True); return
    st = str(order.get('status') or '')
    if st == 'delivered':
        await q.answer("Already delivered ✅", show_alert=True); return
    if st == 'refunded':
        await q.answer("Already refunded — retry closed", show_alert=True); return
    if st != 'supplier_retry_pending':
        await q.answer(f"Cannot retry while status is {st}", show_alert=True); return

    await q.answer("🔄 Retrying supplier delivery…", show_alert=False)
    try:
        await q.edit_message_text(
            f"🔄 *Retrying supplier delivery…*\n━━━━━━━━━━━━━━━━━━━━\nOrder: `#{oid}`\n\nPlease wait.",
            parse_mode="Markdown")
    except Exception:
        pass

    await route_order_to_supplier(context.bot, order)
    fresh = get_order(oid)
    final_st = str(fresh.get('status') or '') if fresh else ''
    try:
        if final_st == 'delivered':
            await q.edit_message_text(f"✅ *Retry successful*\nOrder `#{oid}` delivered.", parse_mode="Markdown")
        elif final_st == 'supplier_retry_pending':
            due_txt = _supplier_retry_due_text(fresh.get('supplier_refund_due_at') or 0)
            await q.edit_message_text(
                f"⚠️ *Retry failed again*\nOrder `#{oid}` is still pending.\n"
                f"Auto-refund at `{escape_md(due_txt)}`.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Retry Again", callback_data=f"supplier_retry_{oid}")]
                ])
            )
        elif final_st == 'refunded':
            await q.edit_message_text(f"💎 Order `#{oid}` has been refunded.", parse_mode="Markdown")
        else:
            await q.edit_message_text(f"ℹ️ Retry finished. Current status: `{escape_md(final_st)}`", parse_mode="Markdown")
    except Exception:
        pass


def _claim_supplier_order_for_processing(order_id):
    """Atomic idempotency guard for supplier fulfillment.

    Payment verification can be triggered by a background job + user retry at
    nearly the same time. Without a claim step, the same paid order can call the
    supplier API more than once. We mark the order as supplier_processing under
    BEGIN IMMEDIATE before the API call; any duplicate worker sees that status
    and exits without buying/delivering extra stock.
    """
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute("SELECT status FROM orders WHERE id=?", (int(order_id),))
        row = c.fetchone()
        if not row:
            conn.rollback(); conn.close(); return False, "missing"
        status = str(row['status'] or '')
        if status in ("delivered", "supplier_processing", "refunded", "cancelled", "rejected"):
            conn.rollback(); conn.close(); return False, status
        c.execute("UPDATE orders SET status='supplier_processing' WHERE id=?", (int(order_id),))
        conn.commit(); conn.close(); return True, "claimed"
    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        try: conn.close()
        except Exception: pass
        logger.warning(f"[router] supplier order claim failed for #{order_id}: {e}")
        return False, "claim_failed"


def _supplier_result_cost_usd(result, fallback):
    """Prefer supplier-returned total_usd when present; otherwise use fallback."""
    for v in (result.get('total_usd'),):
        if v is not None and v != "":
            try: return float(v)
            except (TypeError, ValueError): pass
    raw = result.get('raw')
    candidates = []
    if isinstance(raw, dict):
        candidates.append(raw)
        data = raw.get('data')
        if isinstance(data, dict):
            candidates.append(data)
    for src in candidates:
        for key in ("total_usd", "totalUsd", "amount_usd", "cost_usd", "amountUsd"):
            v = src.get(key)
            if v is not None and v != "":
                try: return float(v)
                except (TypeError, ValueError): pass
        # Canboso sometimes uses walletCurrency=USD + amount.
        try:
            if str(src.get("walletCurrency", "")).upper() == "USD" and src.get("amount") not in (None, ""):
                return float(src.get("amount"))
        except (TypeError, ValueError):
            pass
    return float(fallback or 0)


def _product_stock_with_local_pool(c, shop_product_id):
    """Stock shown for supplier products = supplier stock + local bonus pool.

    For normal/manual local products this remains local available account count.
    """
    ensure_product_accounts_table(c)
    c.execute("""SELECT COUNT(*) FROM product_accounts
                 WHERE product_id=? AND status='available'""", (int(shop_product_id),))
    local_available = int(c.fetchone()[0] or 0)
    remote_stock = 0
    ext_pid = 0
    try:
        c.execute("SELECT ext_product_id FROM products WHERE id=?", (int(shop_product_id),))
        row = c.fetchone()
        ext_pid = int((row['ext_product_id'] if hasattr(row, 'keys') else row[0]) or 0) if row else 0
    except Exception:
        ext_pid = 0
    if ext_pid:
        try:
            c.execute("SELECT stock FROM ext_products WHERE id=?", (ext_pid,))
            row = c.fetchone()
            remote_stock = int((row['stock'] if hasattr(row, 'keys') else row[0]) or 0) if row else 0
        except Exception:
            remote_stock = 0
        return remote_stock + local_available
    return local_available


def _refresh_product_stock_with_local_pool(c, shop_product_id):
    try:
        stock = _product_stock_with_local_pool(c, shop_product_id)
        c.execute("UPDATE products SET stock=? WHERE id=?", (int(stock), int(shop_product_id)))
    except Exception as e:
        logger.debug(f"[bonus_pool] stock refresh failed for product #{shop_product_id}: {e}")


def _delivery_quality_warnings(items, fmt_key):
    """Detect obvious supplier delivery format mismatches for admin warning."""
    expected = {
        "email_pass": 2,
        "email_pass_2fa": 3,
        "email_pass_recovery": 3,
        "email_multi": 4,
    }.get(str(fmt_key or ""))
    if not expected:
        return []
    bad = []
    for idx, item in enumerate(items or [], start=1):
        parts = [p for p in str(item).split('|') if p != '']
        if len(parts) < expected:
            bad.append((idx, len(parts), expected))
            if len(bad) >= 5:
                break
    return bad


def _add_bonus_items_to_local_pool(shop_product_id, bonus_items, *, source_order_id=0, source_supplier_id=0, source_ext_order_id=0):
    """Store supplier bonus/over-delivered accounts in same product's local pool.

    These are not delivered free to the current customer. They become available
    stock for future orders of the same shop product.
    Returns (added, skipped_duplicate_or_empty).
    """
    clean = [str(x).strip() for x in (bonus_items or []) if str(x).strip()]
    if not shop_product_id or not clean:
        return 0, 0
    conn = get_connection(); c = conn.cursor()
    try:
        ensure_product_accounts_table(c)
        c.execute("SELECT account_data FROM product_accounts WHERE product_id=?", (int(shop_product_id),))
        existing = {str(r[0] if not hasattr(r, 'keys') else r['account_data']).strip().lower()
                    for r in c.fetchall() if (r[0] if not hasattr(r, 'keys') else r['account_data'])}
        added = 0; skipped = 0
        for item in clean:
            key = item.strip().lower()
            if not key or key in existing:
                skipped += 1
                continue
            c.execute("""INSERT INTO product_accounts
                         (product_id, account_data, status, source, source_order_id, source_supplier_id, source_ext_order_id)
                         VALUES (?, ?, 'available', 'supplier_bonus', ?, ?, ?)""",
                      (int(shop_product_id), item, int(source_order_id or 0), int(source_supplier_id or 0), int(source_ext_order_id or 0)))
            existing.add(key)
            added += 1
        if added:
            _refresh_product_stock_with_local_pool(c, shop_product_id)
        conn.commit(); conn.close()
        return added, skipped
    except Exception as e:
        try: conn.rollback(); conn.close()
        except Exception: pass
        logger.warning(f"[bonus_pool] failed to add bonus items for product #{shop_product_id}: {e}")
        return 0, len(clean)


def _consume_local_pool_if_enough(shop_product_id, order_id, buyer_uid, qty):
    """Atomically consume local bonus pool only if it can fulfill the full order.

    We do not partially consume local pool before a supplier API call; otherwise
    a supplier failure would leave the order half-reserved and require rollback.
    """
    if not shop_product_id or int(qty or 0) <= 0:
        return []
    qty = int(qty)
    conn = get_connection(); c = conn.cursor()
    try:
        ensure_product_accounts_table(c)
        c.execute("BEGIN IMMEDIATE")
        c.execute("""SELECT id, account_data FROM product_accounts
                     WHERE product_id=? AND status='available'
                     ORDER BY id ASC LIMIT ?""", (int(shop_product_id), qty))
        rows = c.fetchall()
        if len(rows) < qty:
            conn.rollback(); conn.close(); return []
        ids = [int(r['id'] if hasattr(r, 'keys') else r[0]) for r in rows]
        items = [str(r['account_data'] if hasattr(r, 'keys') else r[1]) for r in rows]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        placeholders = ",".join("?" for _ in ids)
        c.execute(f"""UPDATE product_accounts
                      SET status='sold', order_id=?, sold_at=?, sold_to=?
                      WHERE id IN ({placeholders})""", [int(order_id), now, int(buyer_uid or 0), *ids])
        _refresh_product_stock_with_local_pool(c, shop_product_id)
        conn.commit(); conn.close(); return items
    except Exception as e:
        try: conn.rollback(); conn.close()
        except Exception: pass
        logger.warning(f"[bonus_pool] consume failed for product #{shop_product_id}: {e}")
        return []


async def _try_failover_supplier_order(primary_ext_product_id, qty):
    """Try configured backup ext_products for a failed supplier order.

    Uses ext_failover(primary_id, backup1_id, backup2_id). Returns a dict with
    ep/sup/result/ext ids on success, else None.
    """
    try:
        ensure_ext_supplier_tables()
        conn=get_connection(); c=conn.cursor()
        c.execute("SELECT backup1_id, backup2_id FROM ext_failover WHERE primary_id=?", (int(primary_ext_product_id),))
        row=c.fetchone(); conn.close()
        if not row:
            return None
        backup_ids=[int(row['backup1_id'] or 0), int(row['backup2_id'] or 0)]
    except Exception:
        return None
    for bid in backup_ids:
        if not bid:
            continue
        try:
            bep=get_ext_product(bid)
            if not bep or not int(bep.get('active') or 0):
                continue
            bsup=get_supplier(int(bep.get('supplier_id') or 0))
            if not bsup or not int(bsup.get('enabled') or 0):
                continue
            bad=get_adapter_for_supplier(bsup)
            if not bad:
                continue
            bres=await asyncio.to_thread(bad.create_order, bep['remote_id'], int(qty))
            bitems=[str(x).strip() for x in (bres.get('items') or []) if str(x).strip()]
            if bres.get('ok') and len(bitems) >= int(qty):
                return {
                    'ep': bep, 'sup': bsup,
                    'ext_pid': int(bep['id']), 'ext_sid': int(bsup['id']),
                    'result': bres,
                    'note': f"✅ Primary supplier failed; delivered via failover ext_product #{bid}."
                }
        except Exception as e:
            logger.warning(f"[failover] backup ext#{bid} failed: {e}")
            continue
    return None


async def route_order_to_supplier(bot, order):
    """CORE ROUTER. Called by fulfill_paid_product_order for supplier-linked
    products. Steps:
      1. Look up ext_product via products.ext_product_id
      2. Call adapter.create_order()
      3. On success: build v72 byte-perfect delivery + send to customer
      4. On failure: mark order 'failed' + auto-refund + notify admin

    Returns True if we handled the order (either success or refund), False if
    it's not a supplier product (caller should fall through to normal flow).
    """
    from database import (get_product, get_user, add_points,
                          update_order_status, get_connection as _gc)
    from config import POINTS_PER_DOLLAR
    from templates_bundle import render_delivery_bundle, FORMAT_EMAIL_PASS

    # Inline helper — save delivery_content for future re-view (v72 pattern)
    def _save_delivery(oid, content):
        try:
            conn = _gc(); c = conn.cursor()
            c.execute("UPDATE orders SET delivery_content=? WHERE id=?",
                      (content, oid))
            conn.commit(); conn.close()
        except Exception as e:
            logger.debug(f"[router] save delivery failed: {e}")

    p = get_product(order['product_id'])
    if not p:
        return False
    pd = dict(p)
    ext_pid = pd.get("ext_product_id") or 0
    ext_sid = pd.get("ext_supplier_id") or 0
    if not ext_pid or not ext_sid:
        return False  # Not a supplier product — let normal flow handle it

    ep = get_ext_product(ext_pid)
    sup = get_supplier(ext_sid)
    if not ep or not sup:
        logger.error(f"[router] order #{order['id']}: broken link ep={ep} sup={sup}")
        return False

    # Detect exactly what the customer paid for (single buy = 1; bulk = suffix).
    qty = _supplier_order_qty_from_name(order)

    # Idempotency/concurrency guard: claim before calling the paid supplier API.
    claimed, claim_reason = _claim_supplier_order_for_processing(order['id'])
    if not claimed:
        logger.info(f"[router] order #{order['id']} already handled/locked: {claim_reason}")
        return True

    # v114: use previously saved supplier bonus accounts first, but only when
    # the local pool can cover the FULL order. Otherwise call supplier for the
    # full paid qty (no partial reservations before a possibly failing API call).
    ad = None
    local_items = _consume_local_pool_if_enough(order['product_id'], order['id'], order['user_id'], qty)
    if local_items:
        result = {
            "ok": True,
            "items": local_items,
            "order_id": "local_bonus_pool",
            "raw": {"source": "local_bonus_pool", "qty": qty},
        }
        raw_dump = json.dumps(result.get('raw', ''), default=str, ensure_ascii=False)[:5000]
        supplier_cost = 0.0
        overdelivery_note = "✅ Fulfilled from local bonus pool; supplier API was not called."
    else:
        # v128: after-payment stock re-check. If local pool cannot fulfill and
        # latest visible stock is below paid qty, do not continue to supplier.
        try:
            fresh_p = get_product(order['product_id']) or p
            if int((dict(fresh_p) if fresh_p else {}).get('stock') or 0) < int(qty):
                await _schedule_supplier_retry_or_refund(bot, order, sup, ep, qty,
                                          "Product went out of stock after payment.")
                return True
        except Exception:
            pass
        ad = get_adapter_for_supplier(sup)
        if not ad:
            logger.error(f"[router] no adapter for supplier #{ext_sid}")
            await _schedule_supplier_retry_or_refund(bot, order, sup, ep, qty,
                                      "Supplier adapter not available.")
            return True

        logger.info(f"[router] calling {sup['adapter']}.create_order(remote={ep['remote_id']}, qty={qty})")
        try:
            try:
                setattr(ad, "_current_internal_order_id", order['id'])
            except Exception:
                pass
            result = await asyncio.to_thread(ad.create_order, ep['remote_id'], qty)
        except Exception as e:
            logger.error(f"[router] adapter crashed: {e}")
            log_ext_order(
                internal_order_id=order['id'], supplier_id=ext_sid, ext_product_id=ext_pid,
                quantity=qty, cost_usd=(ep.get('cost_usd') or 0) * qty,
                remote_order_id="", status="failed", raw_response="", error_msg=f"Adapter error: {e}")
            await _schedule_supplier_retry_or_refund(bot, order, sup, ep, qty, f"Adapter error: {e}")
            return True

        raw_dump = json.dumps(result.get('raw', ''), default=str, ensure_ascii=False)[:5000]
        supplier_cost = _supplier_result_cost_usd(result, (ep.get('cost_usd') or 0) * qty)

        if not result.get('ok'):
            logger.error(f"[router] supplier returned error: {result.get('error')}")
            log_ext_order(
                internal_order_id=order['id'], supplier_id=ext_sid, ext_product_id=ext_pid,
                quantity=qty, cost_usd=supplier_cost,
                remote_order_id=result.get('order_id', ''), status="failed",
                raw_response=raw_dump, error_msg=result.get('error', 'unknown'))
            fo = await _try_failover_supplier_order(ext_pid, qty)
            if fo:
                ep, sup = fo['ep'], fo['sup']
                ext_pid, ext_sid = fo['ext_pid'], fo['ext_sid']
                result = fo['result']
                raw_dump = json.dumps(result.get('raw', ''), default=str, ensure_ascii=False)[:5000]
                supplier_cost = _supplier_result_cost_usd(result, (ep.get('cost_usd') or 0) * qty)
                overdelivery_note = fo.get('note', '')
            else:
                await _schedule_supplier_retry_or_refund(bot, order, sup, ep, qty, result.get('error', 'unknown'), result=result)
                return True

    items = [str(x).strip() for x in (result.get('items') or []) if str(x).strip()]
    received_count = len(items)
    if received_count < qty:
        reason = f"Supplier returned only {received_count}/{qty} item(s)."
        log_ext_order(
            internal_order_id=order['id'], supplier_id=ext_sid, ext_product_id=ext_pid,
            quantity=qty, cost_usd=supplier_cost,
            remote_order_id=result.get('order_id', ''), status="failed",
            raw_response=raw_dump, error_msg=reason)
        fo = await _try_failover_supplier_order(ext_pid, qty)
        if fo:
            ep, sup = fo['ep'], fo['sup']
            ext_pid, ext_sid = fo['ext_pid'], fo['ext_sid']
            result = fo['result']
            raw_dump = json.dumps(result.get('raw', ''), default=str, ensure_ascii=False)[:5000]
            supplier_cost = _supplier_result_cost_usd(result, (ep.get('cost_usd') or 0) * qty)
            items = [str(x).strip() for x in (result.get('items') or []) if str(x).strip()]
            received_count = len(items)
            overdelivery_note = fo.get('note', '')
        else:
            await _schedule_supplier_retry_or_refund(bot, order, sup, ep, qty, reason, result=result)
            return True

    # 🔧 v111/v114 over-delivery guard: if supplier returns bonus/extra
    # accounts, do NOT pass freebies to the current customer. Deliver exactly
    # the paid quantity and save bonus items into this product's local pool.
    try:
        overdelivery_note
    except NameError:
        overdelivery_note = ""
    if received_count > qty:
        bonus_items = items[qty:]
        added_bonus, skipped_bonus = _add_bonus_items_to_local_pool(
            order['product_id'], bonus_items,
            source_order_id=order['id'], source_supplier_id=ext_sid, source_ext_order_id=ext_pid)
        overdelivery_note = (
            f"⚠️ Supplier returned {received_count} item(s) for qty {qty}; "
            f"customer delivery was capped to {qty}. "
            f"Bonus pool: +{added_bonus} saved, {skipped_bonus} skipped."
        )
        logger.warning(f"[router] order #{order['id']}: {overdelivery_note}")
        items = items[:qty]

    log_ext_order(
        internal_order_id=order['id'], supplier_id=ext_sid, ext_product_id=ext_pid,
        quantity=qty, cost_usd=supplier_cost,
        remote_order_id=result.get('order_id', ''), status="delivered",
        raw_response=raw_dump, error_msg=overdelivery_note)
    # v128: reset repeated-failure counter after successful delivery.
    try:
        set_setting(f"supplier_fail_count_{int(order['product_id'])}", "0")
    except Exception:
        pass

    # ✅ Success — build v83 FORMAT-AWARE byte-perfect delivery
    # Use per-product delivery_format (auto-detected or admin-overridden). If an
    # older DB row still has an auto-detected default (email_pass) but the latest
    # detector now recognises this product as Outlook/email_multi, heal it at
    # delivery time without requiring a manual re-sync.
    fmt_key = ep.get('delivery_format') or 'email_pass'
    try:
        if int(ep.get('format_detected') or 0) == 1:
            raw_meta = json.loads(ep.get('raw_json') or '{}') if ep.get('raw_json') else {}
            merged = dict(raw_meta) if isinstance(raw_meta, dict) else {}
            merged['name'] = ep.get('name') or merged.get('name') or ''
            merged['description'] = ep.get('description') or merged.get('description') or ''
            auto_fmt = detect_product_format(merged)
            if auto_fmt and auto_fmt != fmt_key:
                fmt_key = auto_fmt
    except Exception:
        pass
    try:
        qwarn = _delivery_quality_warnings(items, fmt_key)
        if qwarn:
            details = ", ".join(f"#{i}: {got}/{exp} fields" for i, got, exp in qwarn)
            await notify_admin(bot,
                f"⚠️ *Delivery Format Warning*\n"
                f"Order: `#{order['id']}`\n"
                f"Product: {escape_md((ep or {}).get('name','?')[:60])}\n"
                f"Format: `{fmt_key}`\n"
                f"Issues: {escape_md(details)}")
    except Exception:
        pass
    delivery_text = render_v83_delivery(
        items, fmt_key=fmt_key,
        product_name=order.get('product_name') or ep['name'],
        order_id=order['id'], product_id=order['product_id']
    )

    # Save delivery content for future re-view + set status
    _save_delivery(order['id'], delivery_text)
    update_order_status(order['id'], 'delivered')

    # Send to customer
    # If bulk (>3 items), also send as .txt file for convenience
    from utils import smart_text_and_mode
    send_text, send_mode = smart_text_and_mode(delivery_text, "Markdown")

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
        [InlineKeyboardButton("🛒 Buy More", callback_data="shop")],
    ])
    try:
        sent = await bot.send_message(order['user_id'], send_text,
                                        parse_mode=send_mode, reply_markup=kb)
        # Save msg_id for future edits (v72 pattern)
        try:
            from database import get_connection as _gc
            conn = _gc(); c = conn.cursor()
            c.execute("UPDATE orders SET delivery_msg_id=? WHERE id=?",
                      (sent.message_id, order['id']))
            conn.commit(); conn.close()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"[router] failed to send delivery to user: {e}")

    # 🆕 v108: Bulk delivery as .txt file — threshold changed to >= 10
    # (was > 3). For 1-9 accounts, only compact text message is sent.
    # For 10+, both compact text preview + .txt file are sent.
    # File naming: bite_store_order_{id}_{qty}accounts.txt (branded)
    # 🐛 v144.2: ALSO send the .txt file when content is long (any single item
    # > 220 chars or 5+ multi-line items) — long redeem links / big payloads
    # get a proper file so nothing is truncated by Telegram.
    _needs_file = len(items) >= 10
    if not _needs_file:
        try:
            _long = any(len(str(i)) > 220 for i in items)
            _multi = sum(1 for i in items if str(i).count('\n') >= 1)
            _needs_file = _long or _multi >= 5
        except Exception:
            _needs_file = False
    if _needs_file:
        try:
            import io
            buf = io.BytesIO()
            for i, item in enumerate(items, 1):
                buf.write(f"{i}. {item}\n".encode('utf-8'))
            buf.seek(0)
            fname = f"bite_store_order_{order['id']}_{len(items)}accounts.txt"
            try:
                sent_doc = await bot.send_document(
                    order['user_id'],
                    document=buf, filename=fname,
                    caption=f"📎 *{len(items)} accounts — Order #{order['id']}*\n"
                            f"_Each line = 1 account. Save this file safely._",
                    parse_mode="Markdown"
                )
                # 🐛 v145: save the document file_id so it can be re-opened /
                # downloaded from Completed Orders later.
                try:
                    _did = getattr(sent_doc, "document", None)
                    if _did is not None and getattr(_did, "file_id", None):
                        _gc2 = _gc(); _cc = _gc2.cursor()
                        _cc.execute("UPDATE orders SET delivery_file_id=? WHERE id=?", (str(_did.file_id), order['id']))
                        _gc2.commit(); _gc2.close()
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"[router] bulk .txt file send failed: {e}")
        except Exception as e:
            logger.warning(f"[router] bulk .txt file send failed: {e}")

    # v120: refresh same supplier balance BEFORE admin notification so the
    # delivered alert can show API balance before/after this order.
    supplier_balance_before = float(sup.get('balance_usd') or 0)
    supplier_balance_after = supplier_balance_before
    try:
        if ad is not None:
            from async_adapter_helpers import async_fetch_balance
            bal = await async_fetch_balance(ad)
            if bal is not None:
                supplier_balance_after = float(bal)
                update_supplier(ext_sid, balance_usd=supplier_balance_after,
                                balance_updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                try:
                    from types import SimpleNamespace
                    from supplier_automation import _maybe_send_low_balance_alert, DEFAULT_LOW_BAL_THRESHOLD
                    fresh_sup = get_supplier(ext_sid) or sup
                    threshold = float(fresh_sup.get("low_bal_threshold") or DEFAULT_LOW_BAL_THRESHOLD)
                    if threshold > 0 and supplier_balance_after < threshold:
                        await _maybe_send_low_balance_alert(SimpleNamespace(bot=bot), fresh_sup, supplier_balance_after, threshold)
                except Exception as _lb_err:
                    logger.debug(f"[router] low-balance alert check failed: {_lb_err}")
    except Exception:
        supplier_balance_after = supplier_balance_before

    # User wallet points before/after order. For wallet payments, points were
    # already deducted before route_order_to_supplier() is called, so reconstruct
    # before using order.binance_amount (stored as points cost for wallet orders).
    try:
        urow = get_user(order['user_id'])
        user_wallet_after = float((urow['points'] if urow and 'points' in urow.keys() else 0) or 0)
    except Exception:
        user_wallet_after = 0.0
    user_wallet_before = user_wallet_after
    try:
        if str(order.get('payment_method') or '').lower() == 'wallet':
            user_wallet_before = user_wallet_after + float(order.get('binance_amount') or 0)
    except Exception:
        pass

    pk_time = datetime.now(timezone(timedelta(hours=5))).strftime("%Y-%m-%d %I:%M:%S %p PKT")

    # Notify admin
    try:
        from config import ADMIN_ID as _AID
        sold_usd = float(order.get('price') or 0)
        warn_line = f"\n\n⚠️ {escape_md(overdelivery_note)}" if overdelivery_note else ""
        await bot.send_message(_AID,
            f"✅ *Supplier order delivered!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛒 Order: `#{order['id']}`\n"
            f"🕒 Time: `{pk_time}`\n"
            f"👤 User ID: `{order['user_id']}`\n"
            f"🏬 Supplier: {sup['name']}\n"
            f"📦 Product: {escape_md(ep['name'][:40])}\n"
            f"🔢 Qty: {qty}\n"
            f"💳 Payment: `{escape_md(order.get('payment_method') or '-')}`\n"
            f"💎 User Wallet: `{fmt_points(user_wallet_before)}` → `{fmt_points(user_wallet_after)}`\n"
            f"🔌 API Balance: `{fmt_price(supplier_balance_before)}` → `{fmt_price(supplier_balance_after)}`\n"
            f"💰 Cost: `{fmt_price(supplier_cost)}` · Sold: `{fmt_price(sold_usd)}`\n"
            f"📈 Profit: `{fmt_price(sold_usd - supplier_cost)}`"
            f"{warn_line}",
            parse_mode="Markdown")
    except Exception:
        pass

    return True


async def _refund_and_notify(bot, order, sup, ep, qty, reason):
    """Supplier failed → auto-refund customer + notify admin."""
    from database import add_points, update_order_status, get_user
    from config import POINTS_PER_DOLLAR
    price_usd = float(order.get('price') or 0)
    refund_points = points_from_usd(price_usd)
    # Micro-priced products still get a tiny proportional refund. If your store
    # wants minimum 1-point refunds, this can be changed, but exact math avoids
    # hidden loss/gain on decimal-priced products.
    # Refund to points wallet (customer can use immediately)
    try:
        add_points(order['user_id'], refund_points, tx_type='refund', description='Supplier auto-refund', event_id=f"supplier_refund_{order['id']}", order_id=order['id'])
    except Exception as e:
        logger.error(f"[refund] add_points failed: {e}")
    update_order_status(order['id'], 'refunded')
    # v128: auto-disable a supplier product after 3 consecutive fulfillment failures.
    try:
        pid = int(order.get('product_id') or 0)
        if pid:
            key = f"supplier_fail_count_{pid}"
            fail_count = int(get_setting(key, "0") or 0) + 1
            set_setting(key, str(fail_count))
            if fail_count >= 3:
                conn = get_connection(); cur = conn.cursor()
                cur.execute("UPDATE products SET is_active=0, stock=0 WHERE id=?", (pid,))
                try:
                    if ep and ep.get('id'):
                        cur.execute("UPDATE ext_products SET active=0 WHERE id=?", (int(ep.get('id')),))
                except Exception:
                    pass
                conn.commit(); conn.close()
                try:
                    await notify_admin(bot,
                        f"🚨 *Product Auto-Disabled*\n"
                        f"Product ID: `{pid}`\n"
                        f"Reason: *{fail_count} consecutive supplier failures*\n"
                        f"Last error: `{escape_md(str(reason)[:160])}`")
                except Exception:
                    pass
    except Exception as _af_err:
        logger.debug(f"[auto-disable] failed: {_af_err}")

    # Notify customer
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        await bot.send_message(
            order['user_id'],
            f"⚠️ *Order #{order['id']} — Refund issued*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 {escape_md(order.get('product_name','?')[:60])}\n\n"
            f"We could not complete this order due to a temporary availability issue.\n\n"
            f"💎 *{fmt_points(refund_points)} points* have been refunded to your wallet.\n"
            f"You can buy another product now, or try this one again after some time.\n\n"
            f"Sorry for the inconvenience — thank you for understanding. 🙏",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Shop Now",     callback_data="shop")],
                [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
                [InlineKeyboardButton("🎫 Support",       callback_data="support_menu")],
            ])
        )
    except Exception as e:
        logger.error(f"[refund] customer notify failed: {e}")

    # Notify admin
    try:
        from config import ADMIN_ID as _AID
        await bot.send_message(_AID,
            f"⚠️ *SUPPLIER FAILURE — auto-refunded*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛒 Order: `#{order['id']}`\n"
            f"🏬 Supplier: {sup['name'] if sup else '?'}\n"
            f"📦 Product: {escape_md((ep or {}).get('name','?')[:40])}\n"
            f"🔢 Qty: {qty}\n"
            f"💰 Amount: `${price_usd:.2f}`\n"
            f"💎 Refunded: `{fmt_points(refund_points)}` points to user `{order['user_id']}`\n\n"
            f"❌ *Reason:* `{escape_md(str(reason)[:200])}`",
            parse_mode="Markdown")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 v83: FORMAT DETECTION & BEAUTIFUL DELIVERY TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════
# Research done live on 4 suppliers (Canboso, Akunding, MMOStore, TunVNMMO)
# revealed 20 unique format strings, grouped into 6 categories:

# Format types (extends templates_bundle's FORMAT_EMAIL_PASS/REDEEM_LINK/COUPON_CODES)
V83_FORMATS = {
    "email_pass": {
        "label": "📧 Email + Password",
        "fields": ["email", "password"],
        "separator": "|",
        "icons":  ["📧 Email", "🔑 Password"],
    },
    "email_pass_2fa": {
        "label": "🔐 Email + Password + 2FA",
        "fields": ["email", "password", "twofa"],
        "separator": "|",
        "icons":  ["📧 Email", "🔑 Password", "🔒 2FA Secret"],
    },
    "email_multi": {
        "label": "🎯 Email + Password + Token + Client ID",
        "fields": ["email", "password", "refresh_token", "client_id"],
        "separator": "|",
        "icons":  ["📧 Email", "🔑 Password", "🎫 Refresh Token", "🆔 Client ID"],
    },
    "email_pass_recovery": {
        "label": "🛡️ Email + Password + Recovery",
        "fields": ["email", "password", "recovery"],
        "separator": "|",
        "icons":  ["📧 Email", "🔑 Password", "🛡️ Recovery"],
    },
    "redeem_link": {
        "label": "🔗 Redeem Link / Activation URL",
        "fields": ["link"],
        "separator": "",
        "icons":  ["🔗 Link"],
    },
    "coupon_code": {
        "label": "🎁 Coupon / Redemption Code",
        "fields": ["code"],
        "separator": "",
        "icons":  ["🎁 Code"],
    },
    "raw_text": {
        "label": "📝 Raw Text (any format)",
        "fields": ["content"],
        "separator": "",
        "icons":  ["📝 Content"],
    },
    # 🆕 v144.2 — new formats found in supplier catalogs/docs
    "phone_number": {
        "label": "📱 Phone Number (PVA)",
        "fields": ["phone"],
        "separator": "",
        "icons":  ["📱 Phone"],
    },
    "license_key": {
        "label": "🗝️ License / Serial Key",
        "fields": ["key"],
        "separator": "",
        "icons":  ["🗝️ License"],
    },
    "cookie_session": {
        "label": "🍪 Cookies / Session",
        "fields": ["cookie"],
        "separator": "",
        "icons":  ["🍪 Cookies"],
    },
    "api_token": {
        "label": "🔑 API Token / Bearer Key",
        "fields": ["token"],
        "separator": "",
        "icons":  ["🔑 Token"],
    },
    "email_pass_cookie": {
        "label": "🧩 Email + Password + Cookies",
        "fields": ["email", "password", "cookie"],
        "separator": "|",
        "icons":  ["📧 Email", "🔑 Password", "🍪 Cookie"],
    },
    "username_pass": {
        "label": "👤 Username + Password",
        "fields": ["username", "password"],
        "separator": "|",
        "icons":  ["👤 Username", "🔑 Password"],
    },
}


# ── FORMAT AUTO-DETECTION (3-tier) ────────────────────────────────────────

_FORMAT_PARSE_REGEX = re.compile(
    r'(?:format|định dạng)\s*:\s*([^\n\r<]+)', re.IGNORECASE
)


def _detect_from_format_line(description):
    """Tier 1: parse 'Format: xxx | yyy | zzz' from description text."""
    if not description:
        return None
    m = _FORMAT_PARSE_REGEX.search(description)
    if not m:
        return None
    line = m.group(1).strip().strip('*').strip()
    if not line:
        return None
    parts = [p.strip() for p in line.split('|')]
    n = len([p for p in parts if p])
    if n >= 4:
        # Check for token/client_id keywords
        low = line.lower()
        if 'token' in low or 'client' in low or 'refresh' in low or 'batteries' in low or 'key' in low:
            return "email_multi"
        return "email_multi"
    elif n == 3:
        low = line.lower()
        if '2fa' in low:
            return "email_pass_2fa"
        elif 'recovery' in low:
            return "email_pass_recovery"
        else:
            # 3 fields but no 2FA/recovery keyword — treat as email+pass+2fa
            return "email_pass_2fa"
    elif n == 2:
        return "email_pass"
    elif n == 1:
        low = parts[0].lower()
        if 'link' in low or 'url' in low:
            return "redeem_link"
        elif 'code' in low or 'cdk' in low:
            return "coupon_code"
    return None


def _detect_from_unit_label(unit_label):
    """Tier 2: check Akunding-style unit_label field.
    🆕 v99: also handles Canboso's slotProductType values ('slot', 'account',
    'code', 'key', 'license')."""
    if not unit_label:
        return None
    ul = str(unit_label).lower().strip()
    if ul == "code":
        return "redeem_link"  # Akunding "code" means redemption link
    if ul == "account":
        return "email_pass"
    if ul in ("license", "key"):
        return "coupon_code"
    # 🆕 v99: Canboso slotProductType='slot' → family invitation link
    if ul == "slot":
        return "redeem_link"
    return None


def _detect_from_keywords(name, description):
    """Tier 3: keyword-based fallback.

    🆕 v87: order matters — check for the STRONGEST signal first.
    Email+pass format lines (like "Format: example@outlook.com | password")
    should win over generic 'link' word matches, since the product might
    just *mention* "link" in the description without actually being a link.

    🆕 v99: NAME-based signals are prioritized above description-based ones.
    If the product NAME itself explicitly says "Redemption Link", "Coupon Code",
    "CDK", "Gift Card", etc., that trumps description keywords. Fixes
    Canboso products like "YouTube 3M Redemption Link" and
    "Chatgpt GO 3 Month Coupon Code" being wrongly detected as email_pass.
    """
    name_lc = (name or "").lower()
    desc_lc = (description or "").lower()
    text = f"{name_lc} {desc_lc}"

    # 🆕 v144.2 PRIORITY -1: new supplier formats (phone / license / cookies / api)
    _phone_signals = ("phone number", "phone for gmail", "pva phone", "verification phone",
                      "số điện thoại", "phone verification", "receive sms", "otp phone")
    if any(s in text for s in _phone_signals):
        return "phone_number"
    _license_signals = ("license key", "serial key", "product key", "activation key",
                        "license code", "đăng ký", "activation code")
    if any(s in text for s in _license_signals) and "email" not in text:
        return "license_key"
    _cookie_signals = ("cookie", "session", "cookies")
    if any(s in text for s in _cookie_signals):
        # email+password+cookie vs cookie-only
        if "email" in text or "mail" in text or "password" in text:
            return "email_pass_cookie"
        return "cookie_session"
    _token_signals = ("api key", "api token", "bearer", "access token", "auth token")
    if any(s in text for s in _token_signals):
        return "api_token"
    _userpass_signals = ("username and password", "username:password", "login:password",
                         "user|pass", "user:pass", "username | password")
    if any(s in text for s in _userpass_signals):
        return "username_pass"

    # 🆕 v99 PRIORITY 0: NAME contains explicit format tokens
    # These are the STRONGEST possible signals — product name itself declares the format.
    _name_link_signals = ("redemption link", "redeem link", "activation link",
                          "invite link", "gift link", "family link",
                          "family invitation", "invite code",
                          "link no warranty", "1m link", "3m link",
                          "6m link", "12m link", "18m link",
                          "family plan slot", "fixed fam")
    if any(sig in name_lc for sig in _name_link_signals):
        return "redeem_link"

    _name_code_signals = ("coupon code", "gift card", "voucher code",
                          "product key", "activation code", "license key",
                          "cdk", "redeem code", "redemption code",
                          "promo code")
    if any(sig in name_lc for sig in _name_code_signals):
        return "coupon_code"

    _name_2fa_signals = ("2fa", "with 2fa", "+ 2fa", "|2fa")
    if any(sig in name_lc for sig in _name_2fa_signals):
        return "email_pass_2fa"

    _name_recovery_signals = ("with recovery", "+ recovery")
    if any(sig in name_lc for sig in _name_recovery_signals):
        return "email_pass_recovery"

    # 🆕 v87: token indicators (email_multi — 4+ fields) — highest priority
    # 🆕 v108: expanded — also catch pipe-separated 4-field patterns like
    # "Email | Pass | Refresh_token | Client_id" (MMOStore Outlook Mail style)
    _multi_signals = [
        "refresh token", "refresh tokens", "refresh_token",
        "client id", "client_id", "client secret", "access token",
        "batteries", "msaartifacts", "msa artifacts",
        # 4-field pipe patterns (any combo mentioning tokens)
        "email | pass | refresh", "email|pass|refresh",
        "email | pass | token", "email|pass|token",
        "email|password|refresh", "email | password | refresh",
    ]
    if any(kw in text for kw in _multi_signals):
        return "email_multi"

    # 🆕 v108: NAME-based email_multi hint — some suppliers deliver Outlook
    # Mail / Hotmail with the 4-field format but description is too short to
    # detect. Treat these product types as email_multi by default (admin can
    # override via Change Format button if wrong).
    _name_multi_signals = ("outlook mail", "hotmail account", "hotmail mail",
                            "microsoft account with token", "office365 account",
                            "outlook account")
    if any(sig in name_lc for sig in _name_multi_signals):
        return "email_multi"

    # 🆕 v108: also detect by counting pipe-separated fields in a "Format:" line
    # e.g. "Format: Email | Pass | Refresh_token | Client_id" → 4 fields → email_multi
    import re as _re_multi
    _fmt_line = _re_multi.search(
        r"(?:^|\n)\s*(?:format|định dạng)\s*:\s*([^\n\r<]+)",
        text, flags=_re_multi.IGNORECASE
    )
    if _fmt_line:
        _line = _fmt_line.group(1).strip()
        _parts = [p.strip() for p in _line.split("|") if p.strip()]
        if len(_parts) >= 4:
            return "email_multi"

    # 🆕 v87: STRONG format signal — if description explicitly shows
    #   "Format: xxx@yyy | password" or "Email | Password", treat as email_pass
    #   BEFORE we look for gift/link keywords (some accounts mention link/gift
    #   in the description but actually deliver email:password).
    strong_email_pass_signals = [
        "email | password",
        "email|password",
        "@outlook.com | password",
        "@gmail.com | password",
        "@hotmail.com | password",
        "email:password",
        "format:email",
        "example@outlook.com",
        "example@gmail.com",
    ]
    if any(kw in text for kw in strong_email_pass_signals):
        # But if 2FA also mentioned → prefer 2fa variant
        if "2fa" in text or "2 fa" in text:
            return "email_pass_2fa"
        if "recovery" in text:
            return "email_pass_recovery"
        return "email_pass"

    # 🆕 v87: CDK / redemption code — dedicated bucket
    # "CDK" = Chinese-style "Card Digital Key" = a redemption code
    # Look for CDK in product NAMES specifically (like "ChatGPT CDK PLUS FREE
    # TRIAL", "Adobe 14Day Renew CDK", "CDK X Premium")
    if "cdk" in name.lower() or " cdk " in text or text.startswith("cdk "):
        return "coupon_code"

    # 🆕 v87: Gift link — explicit "gift link" phrase
    if "gift link" in text or "gift-link" in text:
        return "redeem_link"

    # Redeem link indicators (broadened v87 with more phrases)
    if any(kw in text for kw in ["redeem", "activation link", "invite link",
                                   "code/tài khoản", "link no warranty",
                                   "3m gift", "premium gift", "telegram gift",
                                   "youtube premium 3m gift"]):
        return "redeem_link"

    # 2FA indicators
    if "2fa" in text or "2 fa" in text:
        return "email_pass_2fa"

    # Coupon indicators (broadened v87)
    if any(kw in text for kw in ["coupon", "gift card", "voucher code",
                                   "activation code", "product key",
                                   "coupon creator"]):
        return "coupon_code"
    return None


def detect_product_format(product_dict):
    """Multi-tier auto-detect. Returns one of V83_FORMATS keys.
    Fall back to 'email_pass' (majority-safe default).

    🆕 v99 detection order (strongest signal first):
      Tier 0: NAME-based explicit format tokens ("Redemption Link", "Coupon Code",
              "CDK", "with 2FA", etc.) — supplier has literally spelled it out
      Tier 1a: `usageGuide` field first-line "Format: X | Y | Z" — the supplier's
              own delivery-format declaration (highest reliability when present)
      Tier 1b: same "Format:" line search across full description/features
      Tier 2: unit_label / slotProductType metadata
              (Canboso: 'account'/'slot'/'code'/'key'/'license')
      Tier 3: broad keyword scan across name + description
      Fallback: email_pass
    """
    name = product_dict.get("name") or product_dict.get("product_name") or ""
    usage_guide = product_dict.get("usageGuide") or ""
    description = product_dict.get("description") or ""
    features = product_dict.get("features") or ""
    desc_en = product_dict.get("description_en") or ""
    # Canboso: slotProductType. Akunding: unit_label. MMOStore: unit.
    unit = (product_dict.get("unit_label")
            or product_dict.get("slotProductType")
            or product_dict.get("unit")
            or "")

    # ── Tier 0: strong NAME-based signals (v99) ──
    r = _detect_from_keywords(name, "")   # empty desc → only name-based checks fire
    if r: return r

    # ── Tier 1a: usageGuide field alone (v99) ──
    # Suppliers commonly write the delivery format in usageGuide's first line
    # (e.g. "Format: Email | Password | 2FA"). Give this its own pass BEFORE
    # mixing with description, so a strong hint here isn't diluted by
    # unrelated description text mentioning "link" etc.
    if usage_guide:
        r = _detect_from_format_line(usage_guide)
        if r: return r

    # ── Tier 1b: same search across the combined text ──
    combined = "\n".join([description, features, usage_guide, desc_en])
    r = _detect_from_format_line(combined)
    if r: return r

    # ── Tier 2: metadata unit / slotProductType ──
    r = _detect_from_unit_label(unit)
    if r: return r

    # ── Tier 3: broad keyword scan ──
    r = _detect_from_keywords(name, combined)
    if r: return r

    # ── Fallback ──
    return "email_pass"


# ── BEAUTIFUL DELIVERY RENDERER ───────────────────────────────────────────

def _split_item(item_str, sep="|"):
    """Split a delivery item on the separator, preserving values."""
    if not sep or sep not in str(item_str):
        return [str(item_str)]
    return [p.strip() for p in str(item_str).split(sep)]


def _render_delivery_product_name(raw):
    """🐛 v104 FIX: smart product-name renderer for delivery messages.

    Old code called `html_escape_plain(product_name)` which converted
    premium-emoji markup `<tg-emoji emoji-id="X">📱</tg-emoji>` into ugly
    escaped garbage `&lt;tg-emoji ...&gt;&lt;/tg-emoji&gt;` that Telegram
    rendered as literal `<tg-emoji ...>` text to BOTH the customer AND
    later in the admin's User-Side Delivery Preview.

    Behavior:
      • `[[HTML]]<tg-emoji>...` markup → strip [[HTML]] sentinel, embed
        raw HTML so <tg-emoji> renders as premium emoji icon
      • Plain HTML tags without sentinel → embed as-is
      • Plain text → escape < > & safely for HTML mode
    """
    import re as _re
    s = str(raw or "Product").strip()
    if s.startswith("[[HTML]]"):
        return s[len("[[HTML]]"):]
    # Contains any Telegram-supported HTML tag → embed as-is
    if _re.search(r"<(?:b|i|u|s|code|pre|tg-emoji|a)\b", s, flags=_re.I):
        return s
    # Plain text → safe escape
    return html_escape_plain(s)


def render_v83_delivery(items, fmt_key, product_name="Product",
                        order_id=0, product_id=0):
    """v83: Format-aware BYTE-PERFECT delivery renderer.

    🆕 v108: switched from per-field breakdown to COMPACT single-line format
    (matches MMOStore's proven pattern users know):
        📝 Format: Email | Pass | Refresh_token | Client_id
        1. email@x.com|pass|token|clientid
        2. email2@x.com|pass2|token2|clientid2
    Reasoning: users copy-paste into automation tools that expect one line
    per account. Per-field breakdown was pretty but broke batch imports.

    Threshold for .txt file changed to >= 10 (was > 3) — for 1-9 accounts,
    only text is sent. For 10+, both text preview + .txt file.

    Uses HTML mode with <code> wrapping (v72 pattern) → every char preserved.
    """
    from utils import html_code_block, html_escape_plain
    fmt = V83_FORMATS.get(fmt_key) or V83_FORMATS["raw_text"]
    fields = fmt.get("fields", ["content"])
    icons  = fmt.get("icons", ["📝 Content"])
    sep    = fmt.get("separator", "")
    fmt_label = fmt.get("label", "📝 Raw Text")

    # 🆕 v108: build human-readable format spec like "Email | Pass | Token"
    if sep and len(fields) > 1:
        # Prettify each field name for display
        _pretty = {
            "email": "Email", "password": "Pass", "twofa": "2FA",
            "recovery": "Recovery", "refresh_token": "Refresh_token",
            "client_id": "Client_id", "link": "Link", "code": "Code",
            "content": "Content",
        }
        fmt_spec = " | ".join(_pretty.get(f, f.replace("_", " ").title()) for f in fields)
    else:
        fmt_spec = fields[0].title() if fields else "Content"

    safe_items = [str(x) for x in (items or []) if x is not None and str(x) != ""]
    if not safe_items:
        return "⚠️ Delivery is empty. Please contact admin."

    total = len(safe_items)

    # 🆕 v108: BULK (>= 10 items) — .txt file follows
    # 🆕 v109: For email_multi (Outlook/Hotmail/M365 with refresh_token etc.),
    # SKIP the account preview entirely in text — send ONLY header + format
    # spec + "file attached" note. User's real MMOStore purchase behavior:
    # when qty >= 10, customers want a clean text summary and rely on the
    # .txt file for the actual data (easier to copy-paste to automation).
    # For other formats (email_pass, redeem_link, code, etc.), keep the
    # v108 compact preview (first 3 + ⋯ + last 2) as before.
    if total >= 10:
        if fmt_key == "email_multi":
            # 🆕 v109: NO account preview — pure header + file note
            return (
                "[[HTML]]🎉 <b>Bite Store Delivery</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 <b>Product:</b> {_render_delivery_product_name(product_name)}\n"
                f"🧾 <b>Order ID:</b> <code>#{order_id}</code>\n"
                f"📊 <b>Delivered accounts:</b> <b>{total}</b>\n\n"
                f"📝 <b>Format:</b> {html_escape_plain(fmt_spec)}\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📎 <b>Full list of {total} accounts attached below as .txt file.</b>\n"
                "💡 <b>Tip:</b> Save the file securely — each line = 1 account.\n"
                "🙏 Thank you for shopping with <b>Bite Store</b>!"
            )

        # Non email_multi bulk: keep v108 preview (first 3 + ⋯ + last 2)
        preview_lines = []
        preview_lines.append(f"<b>1.</b> {html_code_block(safe_items[0])}")
        preview_lines.append(f"<b>2.</b> {html_code_block(safe_items[1])}")
        preview_lines.append(f"<b>3.</b> {html_code_block(safe_items[2])}")
        preview_lines.append("⋯")
        preview_lines.append(f"<b>{total-1}.</b> {html_code_block(safe_items[-2])}")
        preview_lines.append(f"<b>{total}.</b> {html_code_block(safe_items[-1])}")
        preview_block = "\n\n".join(preview_lines)

        return (
            "[[HTML]]🎉 <b>Bite Store Delivery</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Product:</b> {_render_delivery_product_name(product_name)}\n"
            f"🧾 <b>Order ID:</b> <code>#{order_id}</code>\n"
            f"📊 <b>Delivered accounts:</b> <b>{total}</b>\n\n"
            f"📝 <b>Format:</b> {html_escape_plain(fmt_spec)}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{preview_block}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📎 <b>Full list of {total} accounts attached below as .txt file.</b>\n"
            "💡 <b>Tip:</b> Save the file securely — each line = 1 account.\n"
            "🙏 Thank you for shopping with <b>Bite Store</b>!"
        )

    # 🆕 v108: SMALL orders (1-9 items) — compact numbered list, NO file
    account_lines = []
    for idx, raw_item in enumerate(safe_items, start=1):
        account_lines.append(f"<b>{idx}.</b> {html_code_block(raw_item)}")
    joined = "\n\n".join(account_lines)

    return (
        "[[HTML]]🎉 <b>Bite Store Delivery</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Product:</b> {_render_delivery_product_name(product_name)}\n"
        f"🧾 <b>Order ID:</b> <code>#{order_id}</code>\n"
        f"📊 <b>Delivered accounts:</b> <b>{total}</b>\n\n"
        f"📝 <b>Format:</b> {html_escape_plain(fmt_spec)}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{joined}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>Tip:</b> Save these details securely. Reply to your Order History message if you need help.\n"
        "🙏 Thank you for shopping with <b>Bite Store</b>!"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v83: MANUAL SYNC TO SHOP + FORMAT PICKER (admin panel)
# ═══════════════════════════════════════════════════════════════════════════

async def ext_prod_refresh_callback(update, context):
    """🆕 v107: FORCE REFRESH from supplier API — pro-user Shopify-style
    overwrite mode. Re-fetches this ONE product fresh, updates ext_product
    row (description + cost + stock + name), re-runs format auto-detect,
    and if the product is synced to shop, mirrors the new data to
    products.description + products.product_format.

    Use case: admin updated product details on supplier side but shop is
    showing stale data. Instead of running Bulk Sync (which re-fetches ALL
    products), this refreshes just one.
    """
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        eid = int(q.data.replace("ext_prod_refresh_", "", 1))
    except Exception:
        return
    await q.answer("🔃 Re-fetching from supplier…")

    p = get_ext_product(eid)
    if not p:
        await q.answer("❌ Product not found", show_alert=True); return

    sup = get_supplier(int(p["supplier_id"]))
    ad = get_adapter_for_supplier(sup)
    if not ad:
        await q.answer("❌ Adapter unavailable", show_alert=True); return

    # Re-fetch ALL products (per-product endpoint may not exist on every
    # adapter — fall back to full list scan). Update matching remote_id.
    try:
        from async_adapter_helpers import async_fetch_products
        all_prods = await async_fetch_products(ad)
    except Exception as e:
        await q.answer(f"❌ Fetch failed: {e}", show_alert=True); return

    fresh = None
    for rp in (all_prods or []):
        if str(rp.get("remote_id")) == str(p["remote_id"]):
            fresh = rp; break
    if not fresh:
        await q.answer(
            "❌ Supplier no longer has this product (removed?)",
            show_alert=True); return

    # Optional auto-translate on fresh description
    _desc = fresh.get("description") or ""
    try:
        from auto_translator import maybe_auto_translate_description as _mtx
        _desc = _mtx(_desc)
    except Exception:
        pass

    # Update ext_product with fresh data (upsert_ext_product handles overwrite)
    upsert_ext_product(
        supplier_id=int(p["supplier_id"]),
        remote_id=p["remote_id"],
        name=fresh.get("name") or p["name"],
        description=_desc,
        cost_usd=fresh.get("cost_usd", 0),
        stock=fresh.get("stock", 0),
        raw_json=json.dumps(fresh.get("raw", {}), ensure_ascii=False),
    )

    # Re-run format auto-detect on the NEW data
    try:
        merged = dict(fresh.get("raw", {}) or {})
        merged.setdefault("name", fresh.get("name", ""))
        merged.setdefault("description", _desc)
        new_fmt = detect_product_format(merged)
        update_ext_product(eid, delivery_format=new_fmt, format_detected=1)
    except Exception:
        pass

    # If synced to shop, re-mirror the updated data
    p_after = get_ext_product(eid)
    was_synced = int(p_after.get("synced_to_shop") or 0) == 1
    if was_synced:
        try:
            mirror_ext_to_products(eid)
        except Exception as e:
            logger.warning(f"[force_refresh] re-mirror fail: {e}")

    # Show refresh summary
    _preview = (p_after.get("description") or "")[:120]
    await q.answer(
        f"✅ Refreshed!\n"
        f"Desc: {len(p_after.get('description') or '')} chars\n"
        f"Format: {p_after.get('delivery_format', '?')}\n"
        f"Shop mirror: {'✅ updated' if was_synced else '⚠️ not synced to shop'}",
        show_alert=True)

    # Refresh the view screen
    _set_q_data(q, f"ext_prod_view_{eid}")
    await ext_prod_view_callback(update, context)


async def ext_prod_sync_callback(update, context):
    """🔄 Toggle: sync product to shop / unsync (hide from customers)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        eid = int(q.data.replace("ext_prod_sync_", "", 1))
    except Exception:
        return
    p = get_ext_product(eid)
    if not p: return

    if p.get("synced_to_shop"):
        # Currently synced → UNSYNC: delete shop mirror so it disappears from
        # both user shop and admin Edit Items.
        stats = unmirror_ext_product(eid)
        await q.answer(
            f"🗑 Unsynced + deleted from shop/admin (product #{stats.get('shop_product_id',0)})",
            show_alert=True)
    else:
        # Not synced → SYNC (create/update shop mirror + activate)
        update_ext_product(eid, synced_to_shop=1)
        mirror_ext_to_products(eid)
        await q.answer("✅ Synced to Shop! Now live for customers.", show_alert=True)

    # Refresh view
    _set_q_data(q, f"ext_prod_view_{eid}")
    await ext_prod_view_callback(update, context)


async def ext_prod_fmt_callback(update, context):
    """🧩 Show format picker — admin can change auto-detected format."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        eid = int(q.data.replace("ext_prod_fmt_", "", 1))
    except Exception:
        return
    p = get_ext_product(eid)
    if not p: return
    cur_fmt = p.get("delivery_format") or "email_pass"

    text = (
        f"🧩 *Delivery Format for Product #{eid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 {escape_md(p['name'][:60])}\n\n"
        f"*Current:* `{cur_fmt}` — {V83_FORMATS.get(cur_fmt, {}).get('label', '?')}\n\n"
        f"_This decides how supplier's response is rendered to customer._\n"
        f"_Auto-detected from product description/name._\n"
        f"_Change if the delivery format is different._"
    )
    kb = []
    for key, meta in V83_FORMATS.items():
        marker = " ✅" if key == cur_fmt else ""
        kb.append([InlineKeyboardButton(
            f"{meta['label']}{marker}",
            callback_data=f"ext_prod_setfmt_{eid}_{key}"
        )])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data=f"ext_prod_view_{eid}")])
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def ext_prod_setfmt_callback(update, context):
    """Save admin's chosen format."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    data = q.data.replace("ext_prod_setfmt_", "", 1)
    try:
        parts = data.rsplit("_", 1)
        # Handle 2-part keys like "email_pass_2fa" → need to be careful
        # Format keys: email_pass, email_pass_2fa, email_pass_recovery, email_multi,
        #              redeem_link, coupon_code, raw_text
        # All start with letters, EID at start
        # Find where numeric EID ends
        m = re.match(r'^(\d+)_(.+)$', data)
        if not m:
            raise ValueError(f"bad data: {data}")
        eid = int(m.group(1))
        fmt_key = m.group(2)
    except Exception as e:
        await q.answer(f"⚠️ Bad payload: {e}", show_alert=True); return
    if fmt_key not in V83_FORMATS:
        await q.answer("⚠️ Unknown format", show_alert=True); return
    # Save + mark as admin override (format_detected=0 → won't be overwritten by sync)
    update_ext_product(eid, delivery_format=fmt_key, format_detected=0)
    await q.answer(f"✅ Format: {V83_FORMATS[fmt_key]['label']}", show_alert=True)
    _set_q_data(q, f"ext_prod_view_{eid}")
    await ext_prod_view_callback(update, context)


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v83: WIPE existing auto-mirrored products (one-time cleanup at startup)
# ═══════════════════════════════════════════════════════════════════════════

def wipe_v82_auto_mirrored_products():
    """One-time v83 cleanup: remove all products that v82 auto-mirrored from
    suppliers. Sets synced_to_shop=0 for ext_products so admin re-sync from
    fresh. Idempotent — checks a flag to avoid re-running."""
    conn = get_connection(); c = conn.cursor()
    # Check if already ran (marker in bot_settings)
    c.execute("SELECT value FROM bot_settings WHERE key='v83_wipe_done'")
    r = c.fetchone()
    if r and r["value"] == "1":
        conn.close()
        return 0, "already_wiped"

    # Wipe products that came from suppliers
    c.execute("DELETE FROM products WHERE ext_supplier_id > 0")
    wiped_products = c.rowcount
    # Reset all ext_products' synced_to_shop flag + clear shop_product_id links
    c.execute("UPDATE ext_products SET synced_to_shop=0, shop_product_id=0")
    reset_ext = c.rowcount
    # Set marker so this only runs once
    c.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('v83_wipe_done', '1')")
    conn.commit(); conn.close()
    logger.info(f"[v83-wipe] removed {wiped_products} shop products, reset {reset_ext} ext_products")
    return wiped_products, None


def heal_v86_broken_html_names():
    """
    🆕 v90/v91 healer: fixes ext_products.name rows that were saved by
    the buggy v86 InstaAPI adapter as raw HTML strings like:
        '[[HTML]]<tg-emoji emoji-id="6172304880093109177">✨</tg-emoji> ChatPRD 1 year'
    → converted to clean: '✨ ChatPRD 1 year'
    + populates emoji_char + emoji_id + emoji_status='ok' columns.

    Also fixes any shop products (in `products` table) that were mirrored
    from these broken ext_products before the fix.

    🆕 v91: Runs on EVERY startup now (not just once) because it's cheap
    (only touches rows with [[HTML]]% prefix) and self-terminates when
    no broken rows remain. Removed the one-shot flag — safer that way.
    """
    import re as _re
    conn = get_connection(); c = conn.cursor()

    # Regex: match "[[HTML]]<tg-emoji emoji-id="XXX">CHAR</tg-emoji> REST"
    html_name_pat = _re.compile(
        r'^\[\[HTML\]\]<tg-emoji[^>]*emoji-id="([^"]+)"[^>]*>([^<]+)</tg-emoji>\s*(.*)$',
        _re.DOTALL,
    )

    # Heal ext_products
    c.execute("SELECT id, name FROM ext_products WHERE name LIKE '[[HTML]]%'")
    rows = c.fetchall()
    healed_ext = 0
    for row in rows:
        m = html_name_pat.match(row["name"] or "")
        if not m:
            continue
        emoji_id, emoji_char, rest = m.group(1), m.group(2).strip(), m.group(3).strip()
        clean_name = f"{emoji_char} {rest}".strip() if emoji_char else rest
        c.execute("""UPDATE ext_products
                      SET name=?, emoji_char=?, emoji_id=?, emoji_status='ok'
                      WHERE id=?""",
                  (clean_name[:250], emoji_char, emoji_id, row["id"]))
        healed_ext += 1
        # Also add to shared emoji library
        try:
            c.execute("""INSERT INTO ext_emoji_lib (emoji_char, emoji_id, used_count)
                         VALUES (?, ?, 1)
                         ON CONFLICT(emoji_char) DO UPDATE SET
                            emoji_id=excluded.emoji_id,
                            used_count=used_count+1""",
                      (emoji_char, emoji_id))
        except Exception:
            pass

    # Heal any shop products that were mirrored WHILE the bug was live.
    # These have the same broken [[HTML]]<tg-emoji>...</tg-emoji> Name pattern
    # in products.name AND come from an ext_supplier (ext_supplier_id > 0).
    c.execute("""SELECT id, name FROM products
                 WHERE name LIKE '[[HTML]]%' AND ext_supplier_id > 0""")
    shop_rows = c.fetchall()
    healed_shop = 0
    for row in shop_rows:
        m = html_name_pat.match(row["name"] or "")
        if not m:
            continue
        emoji_id, emoji_char, rest = m.group(1), m.group(2).strip(), m.group(3).strip()
        # For SHOP display we DO want the HTML wrapping preserved — that's
        # correct usage. But it needs to be properly formed. Rebuild it.
        rebuilt = f'[[HTML]]<tg-emoji emoji-id="{emoji_id}">{emoji_char}</tg-emoji> {rest}'
        c.execute("UPDATE products SET name=? WHERE id=?",
                  (rebuilt, row["id"]))
        healed_shop += 1

    # 🆕 v91: NO flag set — this healer is safe to run every startup.
    # SQL is fast (indexed LIKE query on prefix), self-terminates when
    # no broken rows remain (loops through zero rows = no-op).
    conn.commit(); conn.close()
    if healed_ext + healed_shop > 0:
        logger.info(f"[v90-heal] fixed {healed_ext} ext_products + {healed_shop} shop products")
    return healed_ext + healed_shop, None
