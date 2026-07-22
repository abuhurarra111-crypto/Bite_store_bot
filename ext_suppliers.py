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
from datetime import datetime, timedelta
from typing import Optional

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID
from database import get_connection, ensure_column, get_setting, set_setting
from utils import escape_md, html_code_block, html_escape_plain, smart_text_and_mode

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


def delete_supplier(sid):
    """Hard-delete a supplier (and CASCADE its products/orders)."""
    ensure_ext_supplier_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("DELETE FROM ext_products WHERE supplier_id=?", (int(sid),))
    c.execute("DELETE FROM ext_orders   WHERE supplier_id=?", (int(sid),))
    c.execute("DELETE FROM ext_suppliers WHERE id=?", (int(sid),))
    conn.commit(); conn.close()


def _compute_sell_price(cost_usd, markup_pct, fixed_price, fixed_price_base):
    """🆕 v81.1: SMART PRICE calculation.

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
            return round(float(fixed_price), 2)
        # Cost went UP → increase sell by exact delta
        delta = cost - base
        return round(float(fixed_price) + delta, 2)
    # Auto-markup mode
    mkp = float(markup_pct or 40)
    return round(cost * (1 + mkp / 100.0), 2)


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
        c.execute("""UPDATE ext_products
                     SET name=?, description=?, cost_usd=?, stock=?,
                         sell_price=?, last_synced_at=CURRENT_TIMESTAMP,
                         raw_json=?
                     WHERE id=?""",
                  (name[:250], description[:3000], float(cost_usd),
                   int(stock), sell, raw_json[:8000], existing["id"]))
        pid = existing["id"]
    else:
        markup = 40.0
        sell = _compute_sell_price(cost_usd, markup, 0, 0)
        c.execute("""INSERT INTO ext_products
                     (supplier_id, remote_id, name, description, cost_usd,
                      stock, markup_pct, sell_price, category_id, raw_json)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (int(supplier_id), str(remote_id), name[:250],
                   description[:3000], float(cost_usd), int(stock),
                   markup, sell, int(category_id), raw_json[:8000]))
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
               # 🆕 v83: format + sync
               "delivery_format", "format_detected", "synced_to_shop"}
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
    stock = int(ep.get("stock") or 0)
    cat_id = int(ep.get("category_id") or 0)
    desc = str(ep.get("description") or "")
    is_active = 1 if ep.get("active") else 0

    if row:
        # Update existing mirror row
        c.execute("""UPDATE products
                     SET name=?, description=?, price=?, cost_price=?,
                         stock=?, category_id=?, is_active=?, product_format=?
                     WHERE id=?""",
                  (display_name, desc, sell, cost, stock,
                   cat_id or 1, is_active, "email_pass", shop_pid))
        was_new = False
        pid = shop_pid
    else:
        # Create new mirror row
        c.execute("""INSERT INTO products
                     (category_id, name, description, price, cost_price, stock,
                      delivery_text, warranty, quantity, photo_id,
                      is_active, product_format, delivery_template,
                      ext_supplier_id, ext_product_id)
                     VALUES (?, ?, ?, ?, ?, ?, '', '', '', '', ?, 'email_pass', 1, ?, ?)""",
                  (cat_id or 1, display_name, desc, sell, cost, stock,
                   is_active,
                   int(ep.get("supplier_id") or 0),
                   int(ep.get("id"))))
        pid = c.lastrowid
        was_new = True
        # Save the link back to ext_products
        c.execute("UPDATE ext_products SET shop_product_id=? WHERE id=?",
                  (pid, int(ep.get("id"))))

    conn.commit(); conn.close()
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
    """When admin deletes/hides a supplier product, deactivate the shop row too."""
    ep = get_ext_product(ext_product_id)
    if not ep or not ep.get("shop_product_id"):
        return
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE products SET is_active=0, stock=0 WHERE id=?",
              (int(ep["shop_product_id"]),))
    conn.commit(); conn.close()


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

    def _get(self, path, timeout=20):
        url = self.base_url + path
        try:
            r = requests.get(url, headers=self._headers(),
                             params=self._params(), timeout=timeout)
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


class AkundingAdapter(SupplierAdapterBase):
    KEY_ID = "akunding"
    LABEL = "🌐 Akunding"
    DEFAULT_BASE_URL = "https://akunding.shop"
    DOCS_URL = "https://akunding.shop/api/docs"
    AUTH_STYLE = "bearer"

    def test_connection(self):
        r = self._get("/api/v1/me")
        if r is None or r.status_code != 200:
            code = r.status_code if r else "no-response"
            return False, f"HTTP {code}", {}
        try:
            j = r.json()
            bal = float(j.get("balance", 0) or 0)
            # Also fetch product count
            r2 = self._get("/api/v1/products")
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
        r = self._get("/api/v1/products")
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
        # Use a stable idempotency key based on order body (retryable)
        idem = f"{remote_id}-{quantity}-{_uu.uuid4().hex[:16]}"
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
                    "items": [], "raw": r.text[:500]}
        if r.status_code >= 400:
            msg = j.get("message") or j.get("error") or f"HTTP {r.status_code}"
            return {"ok": False, "error": str(msg), "items": [], "raw": j}
        # Extract items from common response shapes
        items = j.get("items") or j.get("accounts") or j.get("data") or j.get("credentials") or []
        if not items and j.get("account"):
            items = [j["account"]]
        if not isinstance(items, list):
            items = [str(items)]
        # Convert dict items to string form (email|password style)
        norm = []
        for it in items:
            if isinstance(it, dict):
                em = it.get("email") or it.get("user") or it.get("username", "")
                pw = it.get("password") or it.get("pass", "")
                if em and pw:
                    norm.append(f"{em}|{pw}")
                elif it.get("code") or it.get("link"):
                    norm.append(str(it.get("code") or it.get("link")))
                else:
                    norm.append(json.dumps(it, ensure_ascii=False))
            else:
                norm.append(str(it))
        return {"ok": True, "items": norm,
                "order_id": str(j.get("order_id") or j.get("id") or ""),
                "raw": j}


class CanbosoAdapter(SupplierAdapterBase):
    KEY_ID = "canboso"
    LABEL = "🎯 Canboso"
    DEFAULT_BASE_URL = "https://canboso.com"
    DOCS_URL = "https://canboso.com/api/swagger"
    AUTH_STYLE = "x_api_key"

    def test_connection(self):
        """🐛 v99 FIX: also fetch wallet balance so admin dashboard shows
        the correct Canboso balance (was always $0 because 'balance' key
        was missing from the extra dict — callers do `extra.get("balance", 0)`)."""
        r = self._get("/api/telegram-buyer/products")
        if r is None or r.status_code != 200:
            code = r.status_code if r else "no-response"
            return False, f"HTTP {code}", {}
        try:
            j = r.json()
            if not j.get("success"):
                return False, j.get("message", "unknown error"), {}
            products = j.get("products", [])
            req = j.get("requester", {})

            # 🆕 v99: piggyback the balance call so callers get it in `extra`
            # Best-effort — never break test_connection if balance fetch fails.
            balance = 0.0
            try:
                balance = self.fetch_balance()
            except Exception:
                pass

            return True, (f"Connected as {req.get('name', 'unknown')}. "
                          f"{len(products)} products. Balance: ${balance:.2f}"), {
                "count": len(products),
                "user": req.get("name", ""),
                "wallet_currency": j.get("walletCurrency", "USD"),
                "balance": balance,   # 🆕 v99: consumed by ext_sup_test_callback → update_supplier
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
        r = self._get("/api/telegram-buyer/balance")
        if r is None or r.status_code != 200:
            return 0.0
        try:
            j = r.json()
            if not j.get("success"):
                return 0.0
            # Prefer USD, fallback to raw balance
            for k in ("balanceUsd", "balance", "usdtBalance"):
                v = j.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        continue
            return 0.0
        except Exception:
            return 0.0

    def fetch_products(self):
        r = self._get("/api/telegram-buyer/products")
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
            usd = float(p.get("usdPricing", 0) or 0)
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
                "remote_id": str(p.get("_id")),
                "name": p.get("product_name") or "",
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
        Docs mention 'buyer must top up wallet first' — so this call deducts from
        Canboso wallet + returns items.
        """
        body = {"product_id": str(remote_id), "quantity": int(quantity)}
        r = self._post("/api/telegram-buyer/purchase", body, timeout=45)
        if r is None:
            return {"ok": False, "error": "network_error", "items": [], "raw": None}
        try:
            j = r.json()
        except Exception:
            return {"ok": False, "error": f"bad_response_{r.status_code}",
                    "items": [], "raw": r.text[:500]}
        if not j.get("success", r.status_code < 400):
            return {"ok": False,
                    "error": j.get("message") or f"HTTP {r.status_code}",
                    "items": [], "raw": j}
        # Canboso response usually has {orders: [{...credentials...}]} or {items:[]}
        items = j.get("items") or j.get("accounts") or []
        if not items and j.get("orders"):
            for o in j["orders"]:
                if isinstance(o, dict):
                    em = o.get("email") or o.get("username") or ""
                    pw = o.get("password") or ""
                    code = o.get("code") or o.get("link") or ""
                    if em and pw:
                        items.append(f"{em}|{pw}")
                    elif code:
                        items.append(str(code))
                    else:
                        items.append(json.dumps(o, ensure_ascii=False))
                else:
                    items.append(str(o))
        if not isinstance(items, list):
            items = [str(items)]
        return {"ok": True, "items": items,
                "order_id": str(j.get("orderId") or j.get("order_id") or ""),
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
        r = self._get("/api/v1/balance")
        if r and r.status_code == 200:
            try:
                return float(r.json().get("data", {}).get("balance_usd", 0) or 0)
            except Exception:
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
            usd = float(p.get("price_usd", 0) or 0)
            out.append({
                "remote_id": str(p.get("id")),
                "name": p.get("name_en") or p.get("name") or "",
                "description": p.get("description_en") or p.get("description") or "",
                "cost_usd": usd,
                "stock": int(p.get("stock", 0) or 0),
                "raw": p,
            })
        return out

    def create_order(self, remote_id, quantity):
        """MMOStore POST /api/v1/orders {product_id, qty, currency, reserve}.
        Documented response: {ok: true, data: {order_id, items:[...]}} """
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
            return {"ok": False,
                    "error": j.get("error") or j.get("message") or f"HTTP {r.status_code}",
                    "items": [], "raw": j}
        data = j.get("data") or {}
        items_raw = data.get("items") or data.get("accounts") or []
        items = []
        for it in items_raw:
            if isinstance(it, dict):
                em = it.get("email") or it.get("username") or it.get("user") or ""
                pw = it.get("password") or it.get("pass") or ""
                if em and pw:
                    items.append(f"{em}|{pw}")
                elif it.get("credentials"):
                    items.append(str(it["credentials"]))
                elif it.get("account"):
                    items.append(str(it["account"]))
                else:
                    items.append(json.dumps(it, ensure_ascii=False))
            else:
                items.append(str(it))
        return {"ok": True, "items": items,
                "order_id": str(data.get("order_id") or ""),
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
        items = j.get("items") or []
        norm = []
        for it in items:
            if isinstance(it, dict):
                em = it.get("email") or it.get("username") or ""
                pw = it.get("password") or ""
                if em and pw:
                    norm.append(f"{em}|{pw}")
                else:
                    norm.append(json.dumps(it, ensure_ascii=False))
            else:
                norm.append(str(it))
        order = j.get("order") or {}
        return {"ok": True, "items": norm,
                "order_id": str(order.get("order_group") or ""),
                "raw": j}


# Registry: adapter_key → class
ADAPTERS = {
    "akunding": AkundingAdapter,
    "canboso":  CanbosoAdapter,
    "mmostore": MMOStoreAdapter,
    "tunvnmmo": TunVNMMOAdapter,
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
    # Also refresh balance
    try:
        bal = ad.fetch_balance()
        if bal is not None:
            update_supplier(supplier_id, balance_usd=float(bal),
                            balance_updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            last_sync_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
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
    # 🆕 v83: DO NOT auto-mirror. Admin must click "🔄 Sync to Shop" per product.
    # (was in v82 — auto-mirrored everything, removed per user request)
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
    """Step 1: pick adapter type."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    text = (
        "➕ *Add New Supplier — Step 1/3*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Pick supplier type:*\n"
        "(All 4 use REST API with different auth styles)"
    )
    kb = []
    for k, cls in ADAPTERS.items():
        # 🆕 v86: insta_api adapter has its own dedicated flow (connection string).
        # Hide it from the manual "add supplier" dropdown to avoid double-add UX.
        if k == "insta_api":
            continue
        kb.append([InlineKeyboardButton(cls.LABEL, callback_data=f"ext_sup_add_type_{k}")])
    # 🆕 v86: shortcut to the connection-string flow (visible on this screen too)
    kb.append([InlineKeyboardButton("🔗 Or paste a Connection String",
                                     callback_data="ext_sup_add_conn")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_suppliers")])
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


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
    bal = extra.get("balance", 0)
    count = extra.get("count", 0)
    user = extra.get("user", "")
    if bal:
        update_supplier(sid, balance_usd=float(bal),
                        balance_updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    context.user_data.pop("ext_sup_wizard", None)

    text = (
        f"✅ *{cls.LABEL} added! (#{sid})*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Account: `{escape_md(user)}`\n"
        f"💰 Balance: `${bal:.2f}`\n"
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

    # 🆕 v101: silent balance refresh — never breaks the view if it fails
    try:
        ad = get_adapter_for_supplier(s)
        if ad:
            from async_adapter_helpers import async_fetch_balance
            live_bal = await async_fetch_balance(ad)
            if live_bal is not None:
                bal_f = float(live_bal)
                update_supplier(sid, balance_usd=bal_f,
                                balance_updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                # Re-read so the display below is fresh
                s = get_supplier(sid) or s
    except Exception as _e:
        logger.debug(f"[ext_sup_view] auto-refresh balance failed for sid={sid}: {_e}")

    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM ext_products WHERE supplier_id=?", (sid,))
    total_p = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM ext_products WHERE supplier_id=? AND active=1", (sid,))
    active_p = c.fetchone()[0] or 0
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
        f"💰 Balance: `${bal:.2f}` (updated: {bal_when})\n"
        f"⚠️ Low-bal threshold: `${s.get('low_bal_threshold', 5):.2f}`\n"
        f"🔄 Auto sync: `{auto_label}`\n"
        f"📦 Products: *{active_p}/{total_p}* active\n"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Test & Refresh", callback_data=f"ext_sup_test_{sid}"),
         InlineKeyboardButton("📥 Import Products", callback_data=f"ext_sup_import_all_{sid}")],
        [InlineKeyboardButton("☑️ Browse Products", callback_data=f"ext_sup_import_pick_{sid}_0")],
        # 🆕 v85: Bulk sync (1 tap → refreshes cost+stock on all live products)
        [InlineKeyboardButton("🔁 Bulk Sync All Products",
                              callback_data=f"ext_sup_bulk_sync_{sid}")],
        # 🆕 v85: Low-balance threshold editor
        [InlineKeyboardButton(f"⚠️ Low-Bal Alert (${s.get('low_bal_threshold', 3):.2f})",
                              callback_data=f"ext_sup_lowbal_{sid}")],
        # 🆕 v96: rename supplier (admin dashboard label only)
        [InlineKeyboardButton("✏️ Rename Supplier",
                              callback_data=f"ext_sup_rename_{sid}")],
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
        bal = extra.get("balance", 0)
        update_supplier(sid, balance_usd=float(bal),
                        balance_updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    alert = f"{'✅' if ok else '❌'} {msg}"
    await q.answer(alert[:190], show_alert=True)
    # Refresh view
    _set_q_data(q, f"ext_sup_view_{sid}")
    await ext_sup_view_callback(update, context)


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
        f"This will delete supplier #{sid} + ALL its imported products + order history.\n\n"
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
    delete_supplier(sid)
    await q.answer("🗑 Deleted.", show_alert=True)
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
            f"   Current sell: <b>${p['sell_price']:.2f}</b>\n"
            f"   <i>(rises if supplier cost goes up, stays if cost drops)</i>\n"
        )
    else:
        price_mode_lines = (
            f"📈 <b>Price Mode: AUTO-MARKUP</b>\n"
            f"   Markup: <b>{p['markup_pct']:.0f}%</b>\n"
            f"   Sell price: <b>${p['sell_price']:.2f}</b>\n"
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
        f"💰 Cost: <b>${p['cost_usd']:.2f}</b>\n"
        f"{price_mode_lines}"
        f"📊 Stock: <b>{p['stock']}</b>\n\n"
        f"🧩 Delivery Format: <b>{fmt_meta['label']}</b>  <i>({fmt_source})</i>\n\n"
        f"{emoji_line}"
        f"Status: {'🟢 Active' if p['active'] else '🔴 Inactive'}\n"
        f"Shop: {sync_line}"
    )
    kb = [
        # 🆕 v83: SYNC TO SHOP button (per-product manual sync)
        [InlineKeyboardButton(
            "🔴 Unsync (Hide from Shop)" if synced else "🔄 Sync to Shop (Make Live)",
            callback_data=f"ext_prod_sync_{eid}")],
        [InlineKeyboardButton("📈 Auto-Markup %",   callback_data=f"ext_prod_markup_{eid}"),
         InlineKeyboardButton("🔒 Fixed Price",      callback_data=f"ext_prod_fixprice_{eid}")],
        [InlineKeyboardButton("🧩 Change Format",   callback_data=f"ext_prod_fmt_{eid}"),
         InlineKeyboardButton("🎨 Fix Emoji",        callback_data=f"ext_prod_emoji_{eid}")],
        [InlineKeyboardButton("🏷 Set Category",     callback_data=f"ext_prod_cat_{eid}")],
        [InlineKeyboardButton("🔴 Deactivate" if p["active"] else "🟢 Activate",
                              callback_data=f"ext_prod_toggle_{eid}")],
        [InlineKeyboardButton("🔙 Browse Products",
                              callback_data=f"ext_sup_import_pick_{p['supplier_id']}_0")],
    ]
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
        f"💰 Cost: `${p['cost_usd']:.2f}`\n"
        f"📈 Current: `{p['markup_pct']:.0f}%` → sell `${p['sell_price']:.2f}`\n\n"
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
    await q.answer(f"✅ Markup set: {pct:.0f}% → ${p['sell_price']:.2f}", show_alert=True)
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
            f"💰 Current cost: `${p['cost_usd']:.2f}`\n"
            f"🏷 Current sell: `${p['sell_price']:.2f}`\n\n"
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
            f"💰 Current cost: `${p['cost_usd']:.2f}`\n"
            f"📈 Current sell (auto-markup {p['markup_pct']:.0f}%): `${p['sell_price']:.2f}`\n\n"
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
        f"💰 Current cost: `${p['cost_usd']:.2f}`\n\n"
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

    # Detect quantity from stored order
    qty = 1
    try:
        # If admin/customer used bulk quantity, stored in product_name suffix like "×5"
        import re as _re
        m = _re.search(r"×\s*(\d+)", order.get('product_name') or "")
        if m: qty = int(m.group(1))
    except Exception:
        pass

    ad = get_adapter_for_supplier(sup)
    if not ad:
        logger.error(f"[router] no adapter for supplier #{ext_sid}")
        await _refund_and_notify(bot, order, sup, ep, qty,
                                  "Supplier adapter not available.")
        return True

    logger.info(f"[router] calling {sup['adapter']}.create_order(remote={ep['remote_id']}, qty={qty})")
    try:
        result = await asyncio.to_thread(ad.create_order, ep['remote_id'], qty)
    except Exception as e:
        logger.error(f"[router] adapter crashed: {e}")
        await _refund_and_notify(bot, order, sup, ep, qty, f"Adapter error: {e}")
        return True

    log_ext_order(
        internal_order_id=order['id'],
        supplier_id=ext_sid, ext_product_id=ext_pid,
        quantity=qty, cost_usd=(ep.get('cost_usd') or 0) * qty,
        remote_order_id=result.get('order_id', ''),
        status=("delivered" if result.get('ok') else "failed"),
        raw_response=json.dumps(result.get('raw', ''), default=str)[:5000],
        error_msg=result.get('error', ''),
    )

    if not result.get('ok'):
        logger.error(f"[router] supplier returned error: {result.get('error')}")
        await _refund_and_notify(bot, order, sup, ep, qty, result.get('error', 'unknown'))
        return True

    items = result.get('items') or []
    if not items:
        await _refund_and_notify(bot, order, sup, ep, qty,
                                  "Supplier returned no items.")
        return True

    # ✅ Success — build v83 FORMAT-AWARE byte-perfect delivery
    # Use per-product delivery_format (auto-detected or admin-overridden)
    fmt_key = ep.get('delivery_format') or 'email_pass'
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

    # Bulk delivery as .txt file (>3 items)
    if len(items) > 3:
        try:
            import io
            buf = io.BytesIO()
            for i, item in enumerate(items, 1):
                buf.write(f"{i}. {item}\n".encode('utf-8'))
            buf.seek(0)
            fname = f"order_{order['id']}_{len(items)}accounts.txt"
            await bot.send_document(
                order['user_id'],
                document=buf, filename=fname,
                caption=f"📄 *{len(items)} accounts for Order #{order['id']}*\n"
                        f"_Each line = 1 account. Save this file safely._",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"[router] bulk .txt file send failed: {e}")

    # Notify admin
    try:
        from config import ADMIN_ID as _AID
        await bot.send_message(_AID,
            f"✅ *Supplier order delivered!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛒 Order: `#{order['id']}`\n"
            f"🏬 Supplier: {sup['name']}\n"
            f"📦 Product: {escape_md(ep['name'][:40])}\n"
            f"🔢 Qty: {qty}\n"
            f"💰 Cost: `${(ep.get('cost_usd') or 0)*qty:.2f}` · Sold: `${order['price']:.2f}`\n"
            f"📈 Profit: `${order['price'] - (ep.get('cost_usd') or 0)*qty:.2f}`",
            parse_mode="Markdown")
    except Exception:
        pass

    # Refresh supplier balance in background (best effort)
    # 🆕 v89: async wrap so this doesn't block the event loop
    try:
        from async_adapter_helpers import async_fetch_balance
        bal = await async_fetch_balance(ad)
        if bal is not None:
            update_supplier(ext_sid, balance_usd=float(bal),
                            balance_updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass

    return True


async def _refund_and_notify(bot, order, sup, ep, qty, reason):
    """Supplier failed → auto-refund customer + notify admin."""
    from database import add_points, update_order_status, get_user
    from config import POINTS_PER_DOLLAR
    price_usd = float(order.get('price') or 0)
    refund_points = int(round(price_usd * POINTS_PER_DOLLAR))
    # Refund to points wallet (customer can use immediately)
    try:
        add_points(order['user_id'], refund_points)
    except Exception as e:
        logger.error(f"[refund] add_points failed: {e}")
    update_order_status(order['id'], 'refunded')

    # Notify customer
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        await bot.send_message(
            order['user_id'],
            f"⚠️ *Order #{order['id']} — Refund issued*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 {escape_md(order.get('product_name','?')[:60])}\n\n"
            f"We could not complete this order from our supplier right now:\n"
            f"_{escape_md(str(reason)[:150])}_\n\n"
            f"💎 *{refund_points} points* have been refunded to your wallet.\n"
            f"You can use them to buy this or any other product.\n\n"
            f"Sorry for the inconvenience! 🙏",
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
            f"💎 Refunded: `{refund_points}` points to user `{order['user_id']}`\n\n"
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
    if any(kw in text for kw in ["refresh token", "refresh tokens",
                                   "client id", "client_id",
                                   "client secret", "access token"]):
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


def render_v83_delivery(items, fmt_key, product_name="Product",
                        order_id=0, product_id=0):
    """v83: Format-aware BYTE-PERFECT delivery renderer.

    Uses HTML mode with <code> wrapping (v72 pattern) → every char preserved.
    Each item gets a beautiful per-field breakdown based on format definition.
    """
    from utils import html_code_block, html_escape_plain
    fmt = V83_FORMATS.get(fmt_key) or V83_FORMATS["raw_text"]
    fields = fmt.get("fields", ["content"])
    icons  = fmt.get("icons", ["📝 Content"])
    sep    = fmt.get("separator", "")

    safe_items = [str(x) for x in (items or []) if x is not None and str(x) != ""]
    if not safe_items:
        return "⚠️ Delivery is empty. Please contact admin."

    total = len(safe_items)
    blocks = []

    for idx, raw_item in enumerate(safe_items, start=1):
        # Item header
        header_prefix = f"🧾 <b>Item:</b> {idx}/{total}\n" if total > 1 else ""

        # Split & render per-field
        body_parts = []
        if sep and len(fields) > 1:
            parts = _split_item(raw_item, sep)
            for i, val in enumerate(parts):
                if i < len(icons):
                    label = icons[i]
                else:
                    label = f"📎 Field {i+1}"
                body_parts.append(f"<b>{label}:</b>\n{html_code_block(val)}")
            # If supplier sent MORE parts than expected, show extras verbatim
            if len(parts) > len(fields):
                extras = parts[len(fields):]
                for j, ex in enumerate(extras):
                    body_parts.append(f"<b>📎 Extra {j+1}:</b>\n{html_code_block(ex)}")
        else:
            # Single-field format (link, code, raw)
            label = icons[0] if icons else "📝 Content"
            body_parts.append(f"<b>{label}:</b>\n{html_code_block(raw_item)}")

        body = "\n\n".join(body_parts)
        block = (
            f"{header_prefix}"
            f"🧩 <b>Format:</b> {fmt['label']}\n\n"
            f"{body}"
        )
        blocks.append(block)

    # For BULK (>3 items), show a compact summary + hint that .txt file included
    if total > 3:
        # Show first + last + note that all are in the .txt file
        summary_block = (
            f"📦 <b>{total} accounts delivered!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{blocks[0]}\n\n"
            f"⋯\n\n"
            f"{blocks[-1]}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📄 <b>All {total} accounts are also in the .txt file below.</b>\n"
            f"<i>Format: {fmt['label']}</i>"
        )
        return "[[HTML]]🎉 <b>Bite Store Delivery</b>\n━━━━━━━━━━━━━━━━━━━━\n" + \
               f"📦 <b>Product:</b> {html_escape_plain(product_name)}\n\n" + \
               summary_block + \
               "\n\n🙏 Thank you for shopping with <b>Bite Store</b>!"

    # For 1–3 items, show each item's block fully
    joined = "\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(blocks)
    return (
        "[[HTML]]🎉 <b>Bite Store Delivery</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Product:</b> {html_escape_plain(product_name)}\n\n"
        f"{joined}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>Tip:</b> Save these details securely. Reply to your Order History message if you need help.\n"
        f"🙏 Thank you for shopping with <b>Bite Store</b>!"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v83: MANUAL SYNC TO SHOP + FORMAT PICKER (admin panel)
# ═══════════════════════════════════════════════════════════════════════════

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
        # Currently synced → UNSYNC (deactivate shop mirror)
        update_ext_product(eid, synced_to_shop=0)
        unmirror_ext_product(eid)
        await q.answer("🔴 Unsynced from Shop", show_alert=True)
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
