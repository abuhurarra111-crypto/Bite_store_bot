# ============================================================
# 🔗 BITE STORE — RESELLER API (v161.2)
# ProdSeller-compatible reseller API server.
#
# Resellers generate a key (bsk_...) → put it in their own bot
# with header `X-API-Key: <key>` → call /v1/products, /v1/balance,
# /v1/orders — exactly like the ProdSeller / Canboso style buyer
# APIs, so any bot that already supports ProdSeller can connect
# directly to your store's URL.
#
# Payment model (owner's design):
#   Reseller deposits 💎 points in the main bot (Buy Points) →
#   every API order deducts points from their wallet → order is
#   fulfilled from your own suppliers / stock → delivery keys
#   are returned to the reseller bot.
#
# v161.2 adds:
#   - per-key pricing (markup %, base = cost OR selling price, can be -discount)
#   - per-key security (spend limit, allowed products, IP whitelist)
#   - webhooks (order.delivered / order.pending / order.failed)
#   - GET /v1/transactions (wallet history)
#   - GET /v1/files/{order_id} (file deliveries across bots)
#   - /v1/products pagination + search + optional live stock refresh
#   - API server thread auto-restart
# ============================================================
import os
import json
import time as _time
import threading

try:
    from fastapi import FastAPI, Request, Header, HTTPException, Depends, Query
    from fastapi.responses import JSONResponse, RedirectResponse, Response, HTMLResponse
    from pydantic import BaseModel
    _FASTAPI_OK = True
except Exception as _fe:  # allow import in non-API environments
    _FASTAPI_OK = False
    FastAPI = None

from database import (
    get_connection, get_product, get_user, get_user_points,
    get_setting, verify_api_key_v74, log_api_request,
    count_api_requests_recent, deduct_points_if_enough,
    add_points, consume_product_account, count_product_accounts,
    create_reseller_order, update_reseller_order, get_reseller_order,
    list_reseller_orders, migrate_reseller_tables,
    get_api_key_row, reseller_key_total_spent, complete_reseller_order,
    mark_reseller_webhook_sent,
    get_or_create_webhook_secret, enqueue_webhook_event,
    get_due_webhook_events, mark_webhook_event, sign_webhook_payload,
    _hash_api_key, setup_api_tables,
)
from config import POINTS_PER_DOLLAR as _CFG_PPD

# ────────────────────────────────────────────────────────────
# KEY MANAGEMENT
# ────────────────────────────────────────────────────────────

def generate_reseller_key(user_id: int, label: str = "") -> tuple:
    """Generate a bsk_... key linked to the reseller's user_id.
    Plaintext is Fernet-encrypted at rest (key_encrypted) so the owner/user can
    "Show Full Key" later — matching the ProdSeller interface. Plaintext is
    returned exactly once for display."""
    import secrets
    migrate_reseller_tables()
    raw = secrets.token_urlsafe(32)
    plaintext = f"bsk_{raw}"
    prefix = plaintext[:14]
    key_hash = _hash_api_key(plaintext)
    enc = ""
    try:
        from database import _encrypt_secret
        enc = _encrypt_secret(plaintext)
    except Exception:
        enc = ""
    conn = get_connection(); c = conn.cursor()
    c.execute("""INSERT INTO api_keys
        (api_key, bot_name, owner_id, is_active, key_hash, key_prefix, label, key_encrypted)
        VALUES (?, ?, ?, 1, ?, ?, ?, ?)""",
        (key_hash, "Reseller", int(user_id or 0), key_hash, prefix, str(label or "")[:60], enc))
    conn.commit(); conn.close()
    return plaintext, prefix


def get_user_reseller_key(user_id: int):
    """Active reseller key row for a user (or None)."""
    migrate_reseller_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT * FROM api_keys
                 WHERE owner_id=? AND bot_name='Reseller' AND is_active=1
                 ORDER BY id DESC LIMIT 1""", (int(user_id),))
    r = c.fetchone(); conn.close()
    return dict(r) if r else None


def reveal_reseller_key(key_id: int):
    """Decrypt and return the plaintext key ('' when not recoverable)."""
    try:
        from database import _decrypt_secret
        row = get_api_key_row(int(key_id))
        if not row:
            return ""
        enc = str(row.get("key_encrypted") or "").strip()
        if enc:
            return _decrypt_secret(enc)
    except Exception:
        pass
    return ""


def list_reseller_keys(user_id: int = None) -> list:
    """List reseller keys (key_prefix, owner, active, stats, config)."""
    migrate_reseller_tables()
    conn = get_connection(); c = conn.cursor()
    if user_id:
        c.execute("""SELECT id, key_prefix, label, owner_id, is_active, created_at,
                            last_used_at, request_count, reseller_markup,
                            reseller_base_mode, webhook_url, spend_limit_usd,
                            allowed_products, ip_whitelist
                     FROM api_keys WHERE owner_id=? AND bot_name='Reseller'
                     ORDER BY id DESC""", (int(user_id),))
    else:
        c.execute("""SELECT id, key_prefix, label, owner_id, is_active, created_at,
                            last_used_at, request_count, reseller_markup,
                            reseller_base_mode, webhook_url, spend_limit_usd,
                            allowed_products, ip_whitelist
                     FROM api_keys WHERE bot_name='Reseller'
                     ORDER BY id DESC""")
    rows = [dict(r) for r in c.fetchall()]; conn.close()
    return rows


def revoke_reseller_key(key_id: int) -> bool:
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE api_keys SET is_active=0 WHERE id=? AND bot_name='Reseller'", (int(key_id),))
    n = c.rowcount; conn.commit(); conn.close()
    return n > 0


# ────────────────────────────────────────────────────────────
# PRICING (per-key aware) + STOCK HELPERS
# ────────────────────────────────────────────────────────────

def _points_per_dollar() -> float:
    try:
        v = float(get_setting("reseller_points_per_dollar") or get_setting("points_per_dollar") or _CFG_PPD)
        return v if v > 0 else float(_CFG_PPD)
    except Exception:
        return float(_CFG_PPD)


def _global_markup() -> float:
    try:
        return float(get_setting("reseller_markup_pct") or 0)
    except Exception:
        return 0.0


def _base_mode_for(key=None) -> str:
    """'cost' (your supplier cost) or 'price' (your selling price)."""
    try:
        km = ((key or {}).get("reseller_base_mode") or "").strip().lower()
        if km in ("cost", "price"):
            return km
    except Exception:
        pass
    try:
        gm = (get_setting("reseller_base_mode") or "price").strip().lower()
        return gm if gm in ("cost", "price") else "price"
    except Exception:
        return "price"


def _markup_for(key=None) -> float:
    """Markup % for a key (can be negative = discount). Per-key wins; else global."""
    try:
        km = (key or {}).get("reseller_markup")
        if km is not None:
            f = float(km)
            return max(-90.0, min(1000.0, f))
    except Exception:
        pass
    return max(-90.0, min(1000.0, _global_markup()))


def reseller_price_for(pd: dict, key=None) -> float:
    """Reseller price in USD, key-aware.
    Explicit per-product reseller_price wins; else base(cost|price) × (1+markup)."""
    try:
        explicit = float(pd.get("reseller_price") or 0)
        if explicit > 0:
            return explicit
    except Exception:
        pass
    base = 0.0
    try:
        if _base_mode_for(key) == "cost":
            base = float(pd.get("cost_price") or 0)
        if base <= 0:
            base = float(pd.get("price") or 0)
    except Exception:
        base = 0.0
    if base <= 0:
        try:
            base = float(pd.get("price") or 0)
        except Exception:
            base = 0.0
    price = base * (1 + _markup_for(key) / 100.0)
    return round(max(0.01, price), 2)


def _live_stock(pd: dict) -> int:
    """Real stock: live account-pool count first; supplier products prefer the
    ext-products stock (freshest from periodic sync); else DB stock."""
    pid = pd.get("id")
    if pid:
        try:
            n = int(count_product_accounts(pid, "available") or 0)
            if n > 0:
                return n
        except Exception:
            pass
    if (pd.get("ext_product_id") or 0) and (pd.get("ext_supplier_id") or 0):
        try:
            from ext_suppliers import get_ext_product as _gep
            ep = _gep(pd.get("ext_product_id"))
            if ep:
                s = int(ep.get("stock") or 0)
                if s > 0:
                    return s
        except Exception:
            pass
    try:
        return max(0, int(pd.get("stock") or 0))
    except Exception:
        return 0


def _sold_count(pd: dict) -> int:
    try:
        return int(pd.get("real_sold") or 0) + int(pd.get("fake_sold") or 0)
    except Exception:
        return 0


def _first_emoji(text: str) -> str:
    import re as _re
    m = _re.search(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", text or "")
    return m.group(0) if m else ""


def _clean_name(value) -> str:
    """Plain-text product name: strips [[HTML]] + all tags, keeps the emoji
    char so a plain-text bot still shows the product's emoji (no raw HTML)."""
    try:
        from utils import html_strip_tags
        return html_strip_tags(value) or ""
    except Exception:
        s = str(value or "").replace("[[HTML]]", "")
        import re as _re
        s = _re.sub(r"<[^>]+>", "", s)
        return s.strip()


def _name_html(value) -> str:
    """HTML-mode product name: keeps <tg-emoji emoji-id=...> markup so premium
    emoji renders properly in bots that send parse_mode=HTML."""
    try:
        from utils import name_for_message_html
        return name_for_message_html(value) or ""
    except Exception:
        s = str(value or "").replace("[[HTML]]", "")
        return s


def _extract_emoji(value) -> tuple:
    """Return (emoji_char, emoji_id) from a (possibly premium-marked) name."""
    import re as _re
    s = str(value or "")
    m = _re.search(r'<tg-emoji\s+emoji-id=["\']([^"\']+)["\']\s*>([^<]*)</tg-emoji>', s)
    if m:
        return (m.group(2) or "").strip(), m.group(1).strip()
    return _first_emoji(s), ""


def _delivery_type(pd: dict) -> str:
    """How the product is delivered: supplier | text | file | accounts | manual."""
    try:
        if (pd.get("ext_product_id") or 0) and (pd.get("ext_supplier_id") or 0):
            return "supplier"
        if str(pd.get("delivery_file_id") or "").strip():
            return "file"
        if str(pd.get("delivery_text") or "").strip():
            return "text"
        if str(pd.get("delivery_mode") or "") == "manual":
            return "manual"
        return "accounts"
    except Exception:
        return "text"


def _product_payload(pd: dict, key=None) -> dict:
    """ProdSeller-compatible product object, key-aware price. NO supplier info
    is ever exposed — only product data."""
    raw_name = pd.get("name") or "Product"
    emoji_char, emoji_id = _extract_emoji(raw_name)
    return {
        "id": str(pd.get("id")),
        "name": _clean_name(raw_name),
        "name_html": _name_html(raw_name),
        "description": _clean_name(pd.get("description") or "")[:1500],
        "price": round(reseller_price_for(pd, key), 2),
        "stock": _live_stock(pd),
        "inStock": _live_stock(pd) > 0,
        "sold": _sold_count(pd),
        "categoryId": pd.get("category_id"),
        "deliveryType": _delivery_type(pd),
        "emoji": emoji_char,
        "emoji_id": emoji_id,
        "currency": "USD",
    }


def _resellable_products() -> list:
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT * FROM products
                 WHERE is_active=1 AND COALESCE(is_hidden,0)=0
                   AND COALESCE(reseller_enabled,1)=1
                 ORDER BY category_id, id""")
    rows = [dict(r) for r in c.fetchall()]; conn.close()
    return rows


def _allowed_product_set(key) -> set or None:
    """None = all products allowed. Else a set of allowed product ids."""
    try:
        raw = ((key or {}).get("allowed_products") or "").strip()
        if not raw or raw.lower() == "all":
            return None
        out = set()
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                out.add(int(part))
        return out
    except Exception:
        return None


def _ip_allowed(key, client_ip) -> bool:
    try:
        raw = ((key or {}).get("ip_whitelist") or "").strip()
        if not raw or raw.lower() == "all":
            return True
        allowed = {p.strip() for p in raw.split(",") if p.strip()}
        return (client_ip or "") in allowed
    except Exception:
        return True


# ────────────────────────────────────────────────────────────
# LIVE STOCK REFRESH (throttled background sync)
# ────────────────────────────────────────────────────────────
_LIVE_THROTTLE = {}          # supplier_id -> last refresh ts
_LIVE_LOCK = threading.Lock()

def _refresh_supplier_stocks_async():
    """Kick a background sync of supplier stocks (max once / 45s per supplier)."""
    def _worker():
        try:
            seen = {}
            for p in _resellable_products():
                sid = p.get("ext_supplier_id") or 0
                if sid:
                    seen.setdefault(int(sid), 0)
            now = _time.time()
            for sid in seen:
                with _LIVE_LOCK:
                    last = _LIVE_THROTTLE.get(sid, 0)
                    if now - last < 45:
                        continue
                    _LIVE_THROTTLE[sid] = now
                try:
                    from ext_suppliers import sync_supplier_products
                    sync_supplier_products(sid)
                except Exception:
                    pass
        except Exception:
            pass
    try:
        threading.Thread(target=_worker, daemon=True, name="reseller-live-stock").start()
    except Exception:
        pass


# ────────────────────────────────────────────────────────────
# FULFILLMENT (no Telegram coupling — delivery is RETURNED)
# ────────────────────────────────────────────────────────────

def _fulfill_reseller_order(pd: dict, qty: int, user_id: int, reseller_oid: int):
    """Fulfill one reseller order. Returns (ok, items, status, error, file_ref).

    Supplier → real purchase. Static text → atomic stock. Accounts → consume.
    File product → store file ref (delivered). True manual → 'pending'.

    🔒 SECURITY: `error` is ALWAYS generic — full supplier details are logged
    internally only, so the reseller can never see your suppliers / URLs / keys.
    """
    import logging as _lg
    _log = _lg.getLogger("reseller_api")
    try:
        pid = pd.get("id")
        ext_pid = pd.get("ext_product_id") or 0
        ext_sid = pd.get("ext_supplier_id") or 0
        delivery_mode = str(pd.get("delivery_mode") or "")

        # 1) SUPPLIER-LINKED PRODUCT (auto-buy from your supplier — invisible)
        if ext_pid and ext_sid:
            try:
                from ext_suppliers import get_ext_product as _gep
                from ext_suppliers import get_supplier as _gs
                from ext_suppliers import get_adapter_for_supplier as _gad
                ep = _gep(ext_pid)
                sup = _gs(ext_sid)
                ad = _gad(sup) if sup else None
                if ep and ad:
                    remote_id = str(ep.get("remote_id") or ext_pid)
                    res = ad.create_order(remote_id, qty)
                    if res and res.get("ok"):
                        items = [str(i) for i in (res.get("items") or []) if str(i).strip()]
                        if items:
                            return True, items, "delivered", None, None
                        _log.error(f"reseller order #{reseller_oid}: supplier returned empty delivery")
                        return False, [], "failed", "supplier returned empty delivery, retry later", None
                    err = str((res or {}).get("error") or "supplier_order_failed")
                    _log.error(f"reseller order #{reseller_oid}: supplier order failed: {err}")
                    return False, [], "failed", "order failed at source, retry later", None
                _log.error(f"reseller order #{reseller_oid}: supplier link broken ep={ext_pid} sup={ext_sid}")
                return False, [], "failed", "order failed at source, retry later", None
            except Exception:
                _log.exception(f"reseller order #{reseller_oid}: supplier exception")
                return False, [], "failed", "order failed at source, retry later", None

        # 2) STATIC TEXT DELIVERY — atomic stock guard
        static_text = (pd.get("delivery_text") or "").strip()
        if static_text:
            conn = get_connection(); c = conn.cursor()
            try:
                c.execute("UPDATE products SET stock=stock-? WHERE id=? AND stock>=?", (qty, pid, qty))
                fulfilled = c.rowcount == 1
                conn.commit()
            except Exception:
                try: conn.rollback()
                except Exception: pass
                fulfilled = False
            finally:
                try: conn.close()
                except Exception: pass
            if not fulfilled:
                return False, [], "failed", "out_of_stock", None
            body = static_text
            if qty > 1:
                body = f"📦 Bulk Order × {qty}\n\n{body}"
            return True, [body], "delivered", None, None

        # 3) ACCOUNT POOL
        parts = []
        for _ in range(int(qty)):
            acct = consume_product_account(pid, reseller_oid, user_id)
            if acct:
                parts.append(acct)
        if parts:
            try:
                from templates_bundle import render_delivery_bundle, normalize_product_format
                pname = pd.get("name") or "Product"
                pf = normalize_product_format(pd.get("product_format") or "email_pass")
                tid = int(pd.get("delivery_template") or 1)
                text = render_delivery_bundle(parts, product_name=pname,
                                              product_format=pf, template_id=tid)
            except Exception:
                text = "\n".join(str(p) for p in parts)
            return len(parts) >= int(qty), [text] if str(text).strip() else parts, "delivered", None, None

        # 4) FILE DELIVERY (Telegram file_id) — file fetched by reseller via
        #    GET /v1/files/{order_id} (file_id is bot-specific, so we serve bytes)
        file_id = (pd.get("delivery_file_id") or "").strip()
        if file_id:
            return True, [], "delivered", None, {
                "file_id": file_id,
                "file_name": (pd.get("delivery_file_name") or f"delivery_{reseller_oid}").strip(),
                "file_type": (pd.get("delivery_file_type") or "").strip(),
            }

        # 5) TRUE MANUAL (no instant content) — pending; admin completes
        if delivery_mode == "manual":
            return True, [], "pending", None, None

        return False, [], "failed", "no_delivery_source", None
    except Exception:
        _log.exception("reseller fulfillment internal error")
        return False, [], "failed", "internal_error", None


def _fire_reseller_alert(order_row):
    """🆕 v161.12: send a Reseller-API purchase hype alert to the configured
    fake-activity destination (raw Telegram HTTP — no PTB bot needed here)."""
    try:
        import threading as _th
        def _worker():
            try:
                from fake_engagement import notify_reseller_purchase_raw, is_type_enabled
                # only when the reseller-hype type is enabled (default ON)
                try:
                    if not is_type_enabled("reseller"):
                        return
                except Exception:
                    pass
                notify_reseller_purchase_raw(
                    product_name=(order_row or {}).get("product_name") or "Product",
                    qty=int((order_row or {}).get("qty") or 1),
                    amount_usd=float((order_row or {}).get("usd_amount") or 0),
                    pid=int((order_row or {}).get("product_id") or 0),
                    reseller_label="",  # masked fake reseller used inside
                )
            except Exception:
                pass
        _th.Thread(target=_worker, daemon=True, name="reseller-alert").start()
    except Exception:
        pass


def _apply_fulfill_result(oid, ok, items, status, err, file_ref, key_row):
    """Persist fulfillment result + send webhook. Returns response dict."""
    out = {"status": status or "failed", "items": items or [], "error": err,
           "file_ref": file_ref, "refunded_points": 0}
    try:
        order = get_reseller_order(oid) or {}
        amount = round(float(order.get("usd_amount") or 0), 2)
    except Exception:
        amount = 0.0
    if ok and status == "delivered":
        # 🆕 v161.12: real reseller order → hype alert to destination
        try:
            _fire_reseller_alert(get_reseller_order(oid))
        except Exception:
            pass
        if file_ref:
            update_reseller_order(oid, status="delivered", delivery_text="",
                                  delivered_keys="[]",
                                  delivery_file_id=file_ref.get("file_id", ""),
                                  delivery_file_name=file_ref.get("file_name", ""),
                                  delivery_file_type=file_ref.get("file_type", ""),
                                  delivered_at=_time.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            update_reseller_order(oid, status="delivered",
                                  delivery_text="\n".join(str(i) for i in (items or [])),
                                  delivered_keys=json.dumps(items or []),
                                  delivered_at=_time.strftime("%Y-%m-%d %H:%M:%S"))
        _send_webhook(key_row, "order.delivered", {
            "orderId": str(oid), "status": "delivered",
            "deliveredKeys": items or [],
            "deliveredFileRef": str(oid) if file_ref else "",
            "amount": amount})
        return out
    if ok and status == "pending":
        update_reseller_order(oid, status="pending")
        _send_webhook(key_row, "order.pending", {
            "orderId": str(oid), "status": "pending", "amount": amount})
        return out
    # failed → auto-refund
    try:
        pts = float((get_reseller_order(oid) or {}).get("points_amount") or 0)
        uid = int((get_reseller_order(oid) or {}).get("user_id") or 0)
    except Exception:
        pts, uid = 0.0, 0
    try:
        if pts > 0 and uid:
            add_points(uid, pts, tx_type="refund",
                       description=f"Reseller API refund: order #{oid}",
                       event_id=f"rs-refund-{oid}")
    except Exception:
        pass
    update_reseller_order(oid, status="failed", error=str(err or "fulfillment_failed"))
    out["refunded_points"] = pts
    _send_webhook(key_row, "order.failed", {
        "orderId": str(oid), "status": "failed",
        "error": str(err or "fulfillment_failed"), "refundedPoints": pts})
    return out


def _fulfill_async(pd, qty, uid, oid, points, event_id, amount, key):
    """Background fulfillment for slow supplier orders (async path)."""
    try:
        ok, items, status, err, file_ref = _fulfill_reseller_order(pd, qty, uid, oid)
        _apply_fulfill_result(oid, ok, items, status, err, file_ref, key)
    except Exception:
        try:
            update_reseller_order(oid, status="failed", error="internal_error")
            if points and uid:
                add_points(uid, points, tx_type="refund",
                           description=f"Reseller API refund: order #{oid}",
                           event_id=f"rs-refund-{oid}-bg")
            _send_webhook(key, "order.failed", {
                "orderId": str(oid), "status": "failed", "error": "internal_error",
                "refundedPoints": points})
        except Exception:
            pass


# ────────────────────────────────────────────────────────────
# WEBHOOKS (fire-and-forget push to the reseller's server)
# ────────────────────────────────────────────────────────────

def _send_webhook(key_row, event: str, payload: dict):
    """Queue a webhook event (persisted + HMAC-signed + auto-retried)."""
    try:
        url = ((key_row or {}).get("webhook_url") or "").strip()
        if not url:
            return
        kid = int((key_row or {}).get("id") or 0)
        secret = get_or_create_webhook_secret(kid) if kid else ""
        body = {"event": event}
        if isinstance(payload, dict):
            body.update(payload)
        enqueue_webhook_event(kid, event, body, secret)
    except Exception:
        pass


def _webhook_worker_loop():
    """Background retry worker: sends due webhook events with HMAC header."""
    import requests as _rq
    from datetime import datetime, timedelta
    while True:
        try:
            for ev in get_due_webhook_events(limit=10):
                eid = int(ev.get("id") or 0)
                kid = int(ev.get("key_id") or 0)
                url = ""
                try:
                    krow = get_api_key_row(kid)
                    url = ((krow or {}).get("webhook_url") or "").strip()
                except Exception:
                    url = ""
                if not url:
                    mark_webhook_event(eid, False, int(ev.get("attempts") or 0) + 1)
                    continue
                try:
                    payload = ev.get("payload")
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        pass
                    r = _rq.post(url, json=payload,
                                 headers={"Content-Type": "application/json",
                                          "X-Bite-Signature": str(ev.get("signature") or "")},
                                 timeout=8)
                    ok = r.status_code < 300
                except Exception:
                    ok = False
                attempts = int(ev.get("attempts") or 0) + 1
                mark_webhook_event(eid, ok, attempts)
        except Exception:
            pass
        _time.sleep(20)


def _notify_admin(text: str):
    """Send a Telegram alert to the store owner (used for API health)."""
    try:
        import requests as _rq
        token = os.getenv("BOT_TOKEN", "").strip()
        aid = os.getenv("ADMIN_ID", "").strip()
        if token and aid:
            _rq.post(f"https://api.telegram.org/bot{token}/sendMessage",
                     json={"chat_id": int(aid), "text": text}, timeout=10)
    except Exception:
        pass


# ────────────────────────────────────────────────────────────
# FASTAPI APP (only when fastapi/uvicorn are installed)
# ────────────────────────────────────────────────────────────

if _FASTAPI_OK:
    # 🆕 v161.6: custom gradient-themed docs page (red→green→blue) — default
    # FastAPI /docs is disabled; we serve our own styled Swagger UI instead.
    app = FastAPI(
        title="Bite Store — Reseller API",
        description=(
            "# Bite Store Reseller API\n\n"
            "Sell our products in **your own bot** — everything is auto-delivered.\n\n"
            "## 🔑 Authentication\n"
            "Send your key in every request header:\n\n"
            "```\nX-API-Key: bsk_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX\n```\n"
            "Without a valid key you get `401`.\n\n"
            "## 📦 How it works\n"
            "1. **Top up** your wallet (deposit points with the store owner).\n"
            "2. `GET /v1/products` — browse products (price + REAL live stock).\n"
            "3. `POST /v1/orders` — buy → your wallet is debited → the product is\n"
            "   **auto-delivered instantly** as `deliveredKeys`.\n"
            "4. Send those keys to your customer.\n\n"
            "## ✅ Auto-delivery — ALL product types\n"
            "- **Our own stock** (auto/static/accounts) → instant delivery keys.\n"
            "- **Products synced from our suppliers** → bought & delivered automatically.\n"
            "- **File products** → `deliveredFileRef` returned; fetch bytes via\n"
            "  `GET /v1/files/{orderId}` and re-upload to your own bot.\n"
            "- **Manual products** (no instant content) → `status: \"pending\"`; delivery\n"
            "  arrives when the store completes it — poll `GET /v1/orders/{id}`.\n\n"
            "## 🔒 Privacy (important)\n"
            "- The API **never exposes our suppliers** — no supplier names, URLs or keys.\n"
            "- Every order is charged from **your wallet balance**.\n"
            "- Your key may have a **spend limit**, **allowed products** list and\n"
            "  **IP whitelist** configured by the store owner.\n\n"
            "## 🪙 Emoji rendering (no raw HTML)\n"
            "Each product returns THREE name fields so any bot can render the emoji:\n"
            "- `name` — plain text (emoji char included, no markup).\n"
            "- `name_html` — send this with `parse_mode=HTML` to render **premium emoji**.\n"
            "- `emoji` + `emoji_id` — the emoji char and its premium id.\n\n"
            "## 🔔 Webhooks\n"
            "If the store owner set a webhook URL on your key, your server gets\n"
            "`POST` notifications: `order.delivered`, `order.pending`,\n"
            "`order.failed`, `order.pending_completed`.\n\n"
            "## ⚠️ Error codes\n"
            "| Code | Meaning |\n"
            "|---|---|\n"
            "| 401 | Missing / invalid API key |\n"
            "| 402 | Insufficient wallet balance |\n"
            "| 403 | Not allowed (product / IP / spend limit) |\n"
            "| 404 | Product or order not found |\n"
            "| 429 | Rate limit (60 req/min) |\n"
            "| 502 | Fulfillment failed — points auto-refunded |\n\n"
            "## 🧾 Idempotency\n"
            "Send header `Idempotency-Key: <unique>` with orders — if the same order is\n"
            "re-sent, you get the same result back instead of a duplicate delivery."
        ),
        version="1.6.0",
        docs_url=None,
        redoc_url=None,
    )

    class _OrderBody(BaseModel):
        productId: str
        quantity: int = 1

    def _require_key(request: Request, x_api_key: str = Header(None)):
        if not x_api_key or not str(x_api_key).strip():
            raise HTTPException(status_code=401, detail="missing X-API-Key header")
        row = verify_api_key_v74(str(x_api_key).strip())
        if not row:
            raise HTTPException(status_code=401, detail="invalid API key")
        if not row.get("is_active"):
            raise HTTPException(status_code=401, detail="API key revoked")
        # IP whitelist
        client_ip = request.client.host if request.client else ""
        if not _ip_allowed(row, client_ip):
            raise HTTPException(status_code=403, detail="IP not allowed for this key")
        try:
            rl = int(row.get("rate_limit") or 60)
            if rl <= 0:
                rl = 60
            if count_api_requests_recent(row.get("id"), 60) >= rl:
                raise HTTPException(status_code=429,
                                    detail=f"rate limit exceeded ({rl} req/min)")
        except HTTPException:
            raise
        except Exception:
            pass
        try:
            log_api_request(row.get("id"), request.url.path, 200, client_ip)
        except Exception:
            pass
        return row

    @app.get("/", include_in_schema=False)
    async def _root():
        return {"service": "Bite Store Reseller API", "docs": "/api-docs/", "status": "ok"}

    @app.get("/health", include_in_schema=False)
    async def _health():
        return {"status": "ok"}

    @app.get("/api-docs/", include_in_schema=False)
    async def _api_docs():
        return RedirectResponse("/docs")

    @app.get("/static/reseller_docs_logo.png", include_in_schema=False)
    async def _docs_logo():
        try:
            _p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "reseller_docs_logo.png")
            with open(_p, "rb") as _f:
                return Response(content=_f.read(), media_type="image/png")
        except Exception:
            raise HTTPException(status_code=404, detail="logo not found")

    @app.get("/static/reseller_docs_favicon.png", include_in_schema=False)
    async def _docs_favicon():
        try:
            _p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "reseller_docs_favicon.png")
            with open(_p, "rb") as _f:
                return Response(content=_f.read(), media_type="image/png")
        except Exception:
            raise HTTPException(status_code=404, detail="favicon not found")

    @app.get("/favicon.ico", include_in_schema=False)
    async def _favicon_ico():
        return await _docs_favicon()

    @app.get("/docs", include_in_schema=False)
    async def _docs():
        return HTMLResponse(_DOCS_HTML, status_code=200)

    _DOCS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Bite Store — Reseller API Docs</title>
<link rel="icon" type="image/png" href="/static/reseller_docs_favicon.png"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"/>
<style>
  :root { --g1:#e53935; --g2:#fb8c00; --g3:#43a047; --g4:#1e88e5; --ink:#0f172a; }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    margin:0; padding:0; min-height:100%;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: var(--ink);
    background: linear-gradient(135deg, var(--g1) 0%, var(--g2) 30%, var(--g3) 65%, var(--g4) 100%);
    background-attachment: fixed;
  }
  /* sticky top nav */
  .topnav {
    position: sticky; top:0; z-index: 50;
    display:flex; align-items:center; gap:12px;
    padding: 10px 18px; backdrop-filter: blur(10px);
    background: rgba(255,255,255,.14); border-bottom:1px solid rgba(255,255,255,.25);
  }
  .topnav img { width: 34px; height:34px; border-radius:50%; box-shadow:0 4px 12px rgba(0,0,0,.3); background:#fff; }
  .topnav .brand { color:#fff; font-weight:700; font-size:16px; text-shadow:0 1px 6px rgba(0,0,0,.4); }
  .topnav .spacer { flex:1; }
  .topnav a { color:#fff; text-decoration:none; font-size:13px; padding:6px 12px; border-radius:999px; background:rgba(255,255,255,.18); transition:.2s; }
  .topnav a:hover { background:rgba(255,255,255,.32); }
  .page { padding: 30px 16px 70px; }
  /* glass hero */
  .hero {
    max-width: 1040px; margin: 0 auto 26px; color:#fff;
    background: rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.35);
    border-radius: 22px; padding: 26px 28px; backdrop-filter: blur(10px);
    box-shadow: 0 18px 50px rgba(0,0,0,.28);
  }
  .hero-top { display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
  .hero img.logo { width: 84px; height:84px; border-radius:50%; background:#fff; padding:4px; box-shadow:0 10px 30px rgba(0,0,0,.35); }
  .hero h1 { margin:0 0 4px; font-size:30px; letter-spacing:.3px; text-shadow:0 2px 10px rgba(0,0,0,.4); }
  .hero p { margin:0; font-size:15px; opacity:.97; }
  .badges { margin-top:14px; }
  .badge { display:inline-block; background:rgba(255,255,255,.2); border:1px solid rgba(255,255,255,.5); padding:4px 13px; border-radius:999px; font-size:12.5px; margin-right:7px; transition:.2s; }
  .badge:hover { transform: translateY(-2px); background:rgba(255,255,255,.3); }
  /* quick start cards */
  .quick { max-width:1040px; margin:0 auto 26px; display:grid; grid-template-columns: repeat(auto-fit,minmax(210px,1fr)); gap:14px; }
  .qcard {
    background: rgba(255,255,255,.94); border-radius:14px; padding:14px 16px;
    box-shadow: 0 10px 30px rgba(0,0,0,.22); border-top:4px solid var(--g4);
  }
  .qcard h3 { margin:0 0 8px; font-size:14px; color:var(--ink); }
  .qcard code { display:block; background:#0f172a; color:#e2e8f0; padding:9px 11px; border-radius:8px; font-size:11.5px; overflow-x:auto; white-space:pre; }
  .qcard .m { font-size:12px; color:#64748b; margin-top:6px; }
  /* swagger card */
  .swagger-wrap { max-width:1040px; margin:0 auto; background:rgba(255,255,255,.98); border-radius:18px; box-shadow:0 22px 60px rgba(0,0,0,.4); overflow:hidden; }
  .swagger-top { height:7px; background: linear-gradient(90deg,var(--g1),var(--g2),var(--g3),var(--g4)); }
  .swagger-ui { padding:12px 22px 34px; color:var(--ink); }
  .swagger-ui .topbar { display:none; }
  .swagger-ui .btn.authorize { border-color:var(--g3); color:var(--g3); }
  .swagger-ui .btn.authorize svg { fill:var(--g3); }
  .swagger-ui .opblock-tag { border-bottom:2px solid var(--g3); }
  .swagger-ui .opblock.opblock-get { border-color:var(--g3); background:rgba(67,160,71,.05); }
  .swagger-ui .opblock.opblock-post { border-color:var(--g4); background:rgba(30,136,229,.05); }
  .swagger-ui .opblock-summary-method { background:linear-gradient(135deg,var(--g2),var(--g3)); }
  .swagger-ui .scheme-container { background:#f1f5f9; border-radius:10px; }
  .swagger-ui .info .title { color:var(--ink); }
  .swagger-ui .info h2, .swagger-ui .info p, .swagger-ui .info .markdown { color:#334155; }
  .swagger-ui .info .markdown table { color:#334155; }
  .swagger-ui .model-box { background:#f1f5f9; }
  .swagger-ui a { color:var(--g4); }
  /* formats */
  .formats { max-width:1040px; margin:26px auto 0; background:rgba(255,255,255,.97); border-radius:16px; box-shadow:0 18px 50px rgba(0,0,0,.35); overflow:hidden; }
  .formats-top { height:6px; background:linear-gradient(90deg,var(--g1),var(--g2),var(--g3),var(--g4)); }
  .formats-body { padding:18px 22px 26px; color:var(--ink); }
  .formats-body h2 { margin:0 0 4px; font-size:21px; }
  .formats-body p { margin:0 0 14px; color:#475569; font-size:14px; }
  .fmt-table { width:100%; border-collapse:collapse; font-size:13.5px; }
  .fmt-table th { text-align:left; padding:9px 10px; background:linear-gradient(90deg,var(--g1),var(--g2),var(--g3),var(--g4)); color:#fff; font-weight:600; }
  .fmt-table td { padding:9px 10px; border-bottom:1px solid #e2e8f0; vertical-align:top; }
  .fmt-table tr:nth-child(even) td { background:#f8fafc; }
  .fmt-table code { background:#f1f5f9; padding:2px 7px; border-radius:6px; font-size:12.5px; }
  .prod-note { background:#f8fafc; border-left:4px solid var(--g4); border-radius:8px; padding:12px 16px; margin-top:16px; font-size:13.5px; color:#334155; }
  .prod-note code { background:#e2e8f0; padding:2px 7px; border-radius:6px; }
  footer { text-align:center; margin-top:24px; font-size:12.5px; color:rgba(255,255,255,.9); text-shadow:0 1px 6px rgba(0,0,0,.5); }
  @media (max-width:640px) {
    .hero h1 { font-size:23px; } .hero { padding:18px 16px; }
    .swagger-ui { padding:8px 10px 22px; } .fmt-table { font-size:12px; }
    .topnav a { display:none; } .topnav .brand { font-size:14px; }
  }
</style>
</head>
<body>
  <div class="topnav">
    <img src="/static/reseller_docs_logo.png" alt="Bite Store"/>
    <span class="brand">Bite Store — Reseller API</span>
    <span class="spacer"></span>
    <a href="#endpoints">Endpoints</a>
    <a href="#formats">Formats</a>
  </div>
  <div class="page">
    <div class="hero">
      <div class="hero-top">
        <img class="logo" src="/static/reseller_docs_logo.png" alt="Bite Store"/>
        <div>
          <h1>🔗 Reseller API</h1>
          <p>Sell our products in your own bot — everything auto-delivered.</p>
          <div class="badges">
            <span class="badge">🔑 X-API-Key auth</span>
            <span class="badge">📦 Auto-delivery</span>
            <span class="badge">🪙 Points wallet</span>
            <span class="badge">🔒 No supplier info exposed</span>
          </div>
        </div>
      </div>
    </div>

    <div class="quick">
      <div class="qcard">
        <h3>🛍️ List products</h3>
        <code>curl -H "X-API-Key: bsk_..." \\<br/>  /v1/products</code>
        <div class="m">Real live stock + premium emoji.</div>
      </div>
      <div class="qcard">
        <h3>💳 Balance</h3>
        <code>curl -H "X-API-Key: bsk_..." \\<br/>  /v1/balance</code>
        <div class="m">Wallet in USD + points.</div>
      </div>
      <div class="qcard">
        <h3>🛒 Place order</h3>
        <code>POST /v1/orders<br/>{"productId":"87","quantity":2}</code>
        <div class="m">Auto-delivered as deliveredKeys.</div>
      </div>
    </div>

    <div class="swagger-wrap" id="endpoints">
      <div class="swagger-top"></div>
      <div id="swagger-ui" class="swagger-ui"></div>
    </div>

    <div class="formats" id="formats">
      <div class="formats-top"></div>
      <div class="formats-body">
        <h2>📦 Delivery Formats (13)</h2>
        <p>Every product is delivered in one of these formats. <code>deliveredKeys</code> always follows the product's format.</p>
        <table class="fmt-table">
          <tr><th>Format</th><th>Spec</th><th>Example</th></tr>
          <tr><td>📧 Email + Password</td><td>Email | Password</td><td><code>demo@gmail.com|MyPass123</code></td></tr>
          <tr><td>🔐 Email + Password + 2FA</td><td>Email | Password | 2FA</td><td><code>demo@gmail.com|MyPass123|JBSWY3DPEHPK3PXP</code></td></tr>
          <tr><td>🎯 Email + Password + Token + Client ID</td><td>Email | Password | Refresh Token | Client ID</td><td><code>demo@hotmail.com|MyPass123|rtoken|client_id</code></td></tr>
          <tr><td>🛡️ Email + Password + Recovery</td><td>Email | Password | Recovery</td><td><code>demo@gmail.com|MyPass123|recovery@x.com</code></td></tr>
          <tr><td>🧩 Email + Password + Cookies</td><td>Email | Password | Cookie</td><td><code>demo@gmail.com|MyPass123|cookie_here</code></td></tr>
          <tr><td>👤 Username + Password</td><td>Username | Password</td><td><code>user123|MyPass123</code></td></tr>
          <tr><td>🔗 Redeem Link / Activation URL</td><td>Link</td><td><code>https://redeem.example.com/claim/ABC123</code></td></tr>
          <tr><td>🎁 Coupon / Redemption Code</td><td>Code</td><td><code>BITE-STORE-2026-PRO</code></td></tr>
          <tr><td>🗝️ License / Serial Key</td><td>Key</td><td><code>XXXXX-XXXXX-XXXXX-XXXXX</code></td></tr>
          <tr><td>📱 Phone Number (PVA)</td><td>Phone</td><td><code>+14155552671</code></td></tr>
          <tr><td>🍪 Cookies / Session</td><td>Cookie</td><td><code>sessionid=abc; token=xyz</code></td></tr>
          <tr><td>🔑 API Token / Bearer Key</td><td>Token</td><td><code>sk-abcdef1234567890</code></td></tr>
          <tr><td>📝 Raw Text (any format)</td><td>Content</td><td><code>any-delivery-text</code></td></tr>
        </table>
        <div class="prod-note">
          <strong>🪙 Emoji rendering:</strong> each product returns <code>name</code> (plain text with the emoji char),
          <code>name_html</code> (premium emoji markup — send with <code>parse_mode=HTML</code>),
          and <code>emoji</code> / <code>emoji_id</code> for custom emoji. Descriptions are clean plain text —
          no HTML tags, no <code>[[HTML]]</code> sentinels.
        </div>
      </div>
    </div>
    <footer>Bite Store Reseller API · Auto-delivery · Live stock · v1.6</footer>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function() {
      window.ui = SwaggerUIBundle({ url:'/openapi.json', dom_id:'#swagger-ui', deepLinking:true, presets:[SwaggerUIBundle.presets.apis], layout:'BaseLayout' });
    };
  </script>
</body>
</html>
"""

    @app.get("/v1/products", summary="List resellable products (live stock, pagination, search)",
             description=(
                 "Returns products enabled for resellers with REAL live stock.\n\n"
                 "Query params: `category` (category id), `search` (name text),\n"
                 "`page` (default 1), `per_page` (default 100, max 500),\n"
                 "`live=1` (background-refresh supplier stock from the source).\n\n"
                 "Each product: `id`, `name` (plain), `name_html` (premium emoji),\n"
                 "`description`, `price`, `stock`, `inStock`, `sold`, `emoji`,\n"
                 "`emoji_id`, `currency`. NO supplier information is exposed."
             ))
    async def _products(key=Depends(_require_key),
                        category: int = Query(None),
                        search: str = Query(None),
                        page: int = Query(1, ge=1),
                        per_page: int = Query(100, ge=1, le=500),
                        live: int = Query(0)):
        prods = _resellable_products()
        allowed = _allowed_product_set(key)
        if allowed is not None:
            prods = [p for p in prods if int(p.get("id") or 0) in allowed]
        if category:
            prods = [p for p in prods if int(p.get("category_id") or 0) == int(category)]
        if search and str(search).strip():
            q = str(search).strip().lower()
            prods = [p for p in prods if q in _clean_name(p.get("name") or "").lower()]
        total = len(prods)
        start = (int(page) - 1) * int(per_page)
        prods = prods[start:start + int(per_page)]
        if live:
            _refresh_supplier_stocks_async()
        out = []
        for p in prods:
            try:
                out.append(_product_payload(p, key))
            except Exception:
                continue
        return {"products": out, "count": len(out), "page": int(page),
                "perPage": int(per_page), "total": total}

    @app.get("/v1/balance", summary="Wallet balance (USD + points)",
             description="Returns your current wallet balance in USD and points.")
    async def _balance(key=Depends(_require_key)):
        uid = int(key.get("owner_id") or 0)
        pts = _points_float(get_user_points(uid))
        ppd = _points_per_dollar()
        usd = pts / ppd if ppd else 0.0
        return {"balance": round(usd, 2), "points": round(pts, 2),
                "currency": "USD", "pointsPerDollar": ppd}

    @app.get("/v1/transactions", summary="Wallet history + your orders",
             description=(
                 "Returns your recent point transactions (ledger) and your recent\n"
                 "reseller orders. Query: `limit` (default 30, max 100)."
             ))
    async def _transactions(key=Depends(_require_key), limit: int = Query(30, ge=1, le=100)):
        uid = int(key.get("owner_id") or 0)
        try:
            from database import get_points_ledger
            ledger = get_points_ledger(user_id=uid, limit=int(limit))
            ledger = [dict(r) if hasattr(r, "keys") else r for r in (ledger or [])]
        except Exception:
            ledger = []
        orders = list_reseller_orders(user_id=uid, limit=int(limit))
        return {"transactions": ledger, "orders": orders, "count": len(ledger)}

    @app.post("/v1/orders", summary="Place order → auto-delivery keys",
              description=(
                  "Debits your wallet and auto-delivers the product.\n\n"
                  "Request body:\n"
                  "```json\n{\"productId\": \"87\", \"quantity\": 2}\n```\n\n"
                  "Success (HTTP 200):\n"
                  "```json\n{\"ok\": true, \"orderId\": \"42\",\n"
                  " \"deliveredKeys\": [\"account1:pass1\"], \"amount\": 12.0,\n"
                  " \"status\": \"delivered\"}\n```\n\n"
                  "File product → `deliveredFileRef` set; fetch bytes via\n"
                  "`GET /v1/files/{orderId}`.\n\n"
                  "Insufficient balance → HTTP 402. Not allowed → HTTP 403.\n"
                  "Optional header `Idempotency-Key: <unique>` prevents duplicates."
              ))
    async def _create_order(body: _OrderBody, request: Request,
                            key=Depends(_require_key),
                            idempotency_key: str = Header(None, alias="Idempotency-Key")):
        uid = int(key.get("owner_id") or 0)
        kid = int(key.get("id") or 0)
        try:
            pid = int(str(body.productId).strip())
        except Exception:
            raise HTTPException(status_code=400, detail="invalid productId")
        qty = max(1, min(9999, int(body.quantity or 1)))

        pd = get_product(pid)
        if not pd:
            raise HTTPException(status_code=404, detail="product not found")
        pd = dict(pd)
        if not pd.get("is_active") or int(pd.get("is_hidden") or 0):
            raise HTTPException(status_code=404, detail="product not available")
        if int(pd.get("reseller_enabled") if pd.get("reseller_enabled") is not None else 1) != 1:
            raise HTTPException(status_code=403, detail="product not enabled for resellers")
        allowed = _allowed_product_set(key)
        if allowed is not None and pid not in allowed:
            raise HTTPException(status_code=403, detail="product not in your allowed list")

        price_usd = reseller_price_for(pd, key)
        ppd = _points_per_dollar()
        points = round(price_usd * qty * ppd, 2)

        # Spend limit (per key, USD)
        try:
            limit = float(key.get("spend_limit_usd") or 0)
            if limit > 0:
                spent = reseller_key_total_spent(kid)
                if spent + round(price_usd * qty, 2) > limit:
                    raise HTTPException(status_code=403, detail="spend limit reached for this key")
        except HTTPException:
            raise
        except Exception:
            pass

        # Idempotency: same key + idempotency-key → return existing order
        if idempotency_key and str(idempotency_key).strip():
            try:
                conn = get_connection(); c = conn.cursor()
                c.execute("""SELECT * FROM reseller_orders
                             WHERE user_id=? AND product_id=? AND qty=?
                               AND idem_key=? ORDER BY id DESC LIMIT 1""",
                          (uid, pid, qty, str(idempotency_key).strip()[:64]))
                r = c.fetchone(); conn.close()
                if r:
                    r = dict(r)
                    items = _parse_keys(r.get("delivered_keys"))
                    return {"ok": r.get("status") == "delivered",
                            "orderId": str(r["id"]),
                            "deliveredKeys": items,
                            "deliveredKey": items[0] if items else "",
                            "deliveredFileRef": str(r["id"]) if r.get("delivery_file_id") else "",
                            "amount": round(float(r.get("usd_amount") or 0), 2),
                            "status": r.get("status")}
            except Exception:
                pass

        event_id = f"reseller-{kid}-{pid}-{qty}-{_time.time_ns()}"
        if idempotency_key and str(idempotency_key).strip():
            event_id = f"reseller-{kid}-{pid}-{qty}-{str(idempotency_key).strip()[:48]}"
        if not deduct_points_if_enough(
                uid, points, tx_type="debit",
                description=f"Reseller API: {(pd.get('name') or 'Product')[:80]} x{qty}",
                event_id=event_id):
            bal = _points_float(get_user_points(uid))
            return JSONResponse(status_code=402, content={
                "ok": False, "error": "insufficient_balance",
                "balance": round(bal / ppd, 2) if ppd else 0.0,
                "points": round(bal, 2),
                "requiredPoints": points,
            })

        oid = create_reseller_order(
            key_id=kid, user_id=uid, product_id=pid,
            product_name=(pd.get("name") or "Product")[:200],
            qty=qty, usd_amount=round(price_usd * qty, 2), points_amount=points,
            status="pending",
            idem_key=str(idempotency_key).strip()[:64] if idempotency_key else "")

        is_supplier = bool((pd.get("ext_product_id") or 0) and (pd.get("ext_supplier_id") or 0))

        # ── ASYNC PATH: supplier products (slow upstream API) → return
        #    orderId instantly ("processing"), fulfill in background, then
        #    webhook + reseller polls GET /v1/orders/{id} for the delivery.
        if is_supplier:
            update_reseller_order(oid, status="processing")
            _ctx = {"pd": pd, "qty": qty, "uid": uid, "oid": oid,
                    "points": points, "event_id": event_id,
                    "amount": round(price_usd * qty, 2), "key": dict(key)}
            try:
                threading.Thread(target=_fulfill_async, kwargs=_ctx,
                                 daemon=True, name=f"rs-order-{oid}").start()
            except Exception:
                _fulfill_async(**_ctx)
            return {"ok": True, "orderId": str(oid), "deliveredKeys": [],
                    "deliveredKey": "", "deliveredFileRef": "",
                    "amount": round(price_usd * qty, 2), "status": "processing"}

        # ── SYNC PATH: instant products (text / accounts / file / manual)
        ok, items, status, err, file_ref = _fulfill_reseller_order(pd, qty, uid, oid)
        result = _apply_fulfill_result(oid, ok, items, status, err, file_ref, key)
        if result["status"] == "delivered":
            return {"ok": True, "orderId": str(oid), "deliveredKeys": result["items"],
                    "deliveredKey": result["items"][0] if result["items"] else "",
                    "deliveredFileRef": str(oid) if result["file_ref"] else "",
                    "amount": round(price_usd * qty, 2), "status": "delivered"}
        if result["status"] == "pending":
            return {"ok": True, "orderId": str(oid), "deliveredKeys": [],
                    "deliveredKey": "", "deliveredFileRef": "",
                    "amount": round(price_usd * qty, 2), "status": "pending"}
        # failed → refund already applied in _apply_fulfill_result
        return JSONResponse(status_code=502, content={
            "ok": False, "orderId": str(oid), "error": result["error"],
            "refundedPoints": result["refunded_points"],
        })

    @app.get("/v1/orders/{order_id}", summary="Order status / delivery")
    async def _order_status(order_id: int, key=Depends(_require_key)):
        uid = int(key.get("owner_id") or 0)
        r = get_reseller_order(order_id)
        if not r or int(r.get("user_id") or 0) != uid:
            raise HTTPException(status_code=404, detail="order not found")
        items = _parse_keys(r.get("delivered_keys"))
        return {"orderId": str(r["id"]), "status": r.get("status"),
                "productId": str(r.get("product_id") or ""),
                "qty": int(r.get("qty") or 1),
                "amount": round(float(r.get("usd_amount") or 0), 2),
                "deliveredKeys": items,
                "deliveredKey": items[0] if items else "",
                "deliveredFileRef": str(r["id"]) if r.get("delivery_file_id") else "",
                "deliveryText": r.get("delivery_text") or "",
                "error": r.get("error") or "",
                "createdAt": r.get("created_at") or "",
                "deliveredAt": r.get("delivered_at") or ""}

    @app.get("/v1/files/{order_id}", summary="Download file delivery bytes",
             description=(
                 "For file-based products: returns the raw file bytes of a delivered\n"
                 "order so your bot can re-upload it to Telegram (Telegram file IDs\n"
                 "do not work across bots). Scoped to your own orders only."
             ))
    async def _file_download(order_id: int, key=Depends(_require_key)):
        uid = int(key.get("owner_id") or 0)
        r = get_reseller_order(order_id)
        if not r or int(r.get("user_id") or 0) != uid:
            raise HTTPException(status_code=404, detail="order not found")
        fid = (r.get("delivery_file_id") or "").strip()
        if not fid:
            raise HTTPException(status_code=404, detail="no file for this order")
        try:
            import requests as _rq
            token = os.getenv("BOT_TOKEN", "").strip()
            j = _rq.post(f"https://api.telegram.org/bot{token}/getFile",
                         json={"file_id": fid}, timeout=20).json()
            if not j.get("ok"):
                raise HTTPException(status_code=502, detail="file source unavailable")
            path = j["result"]["file_path"]
            data = _rq.get(f"https://api.telegram.org/file/bot{token}/{path}",
                           timeout=40)
            if data.status_code != 200:
                raise HTTPException(status_code=502, detail="file source unavailable")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=502, detail="file source unavailable")
        fname = (r.get("delivery_file_name") or f"delivery_{order_id}").strip()
        ftype = (r.get("delivery_file_type") or _guess_mime(fname))
        from urllib.parse import quote
        return Response(content=data.content, media_type=ftype or "application/octet-stream",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{fname}"; filename*=UTF-8\'\'{quote(fname)}"'})

    @app.get("/v1/products/{product_id}/image", summary="Product image bytes",
             description=(
                 "Returns the product's photo bytes (from the store bot) so your\n"
                 "bot can show it. `photo_id`-based; scoped to a valid API key.\n"
                 "404 when the product has no photo."
             ))
    async def _product_image(product_id: int, key=Depends(_require_key)):
        pd = get_product(product_id)
        if not pd:
            raise HTTPException(status_code=404, detail="product not found")
        photo = str(dict(pd).get("photo_id") or "").strip()
        if not photo:
            raise HTTPException(status_code=404, detail="no image for this product")
        try:
            import requests as _rq
            token = os.getenv("BOT_TOKEN", "").strip()
            j = _rq.post(f"https://api.telegram.org/bot{token}/getFile",
                         json={"file_id": photo}, timeout=20).json()
            if not j.get("ok"):
                raise HTTPException(status_code=502, detail="image source unavailable")
            path = j["result"]["file_path"]
            data = _rq.get(f"https://api.telegram.org/file/bot{token}/{path}",
                           timeout=40)
            if data.status_code != 200:
                raise HTTPException(status_code=502, detail="image source unavailable")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=502, detail="image source unavailable")
        return Response(content=data.content,
                        media_type=_guess_mime(path) or "image/jpeg")

    def _guess_mime(fname: str) -> str:
        import mimetypes
        return mimetypes.guess_type(str(fname))[0] or "application/octet-stream"

    def _parse_keys(blob):
        try:
            if not blob:
                return []
            parsed = json.loads(blob)
            if isinstance(parsed, list):
                return [str(i) for i in parsed]
        except Exception:
            pass
        return [str(blob).strip()] if str(blob).strip() else []

    def _points_float(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0


# ────────────────────────────────────────────────────────────
# SERVER STARTER (uvicorn in a daemon thread + AUTO-RESTART)
# ────────────────────────────────────────────────────────────

def start_reseller_api_server(port: int):
    """Start the FastAPI app on 0.0.0.0:port in a background thread with
    auto-restart + health alert to the owner + webhook retry worker.
    Never crashes the bot — logs a warning on failure."""
    if not _FASTAPI_OK:
        print("⚠️ Reseller API disabled — install fastapi+uvicorn to enable")
        return None
    try:
        import uvicorn
    except Exception as e:
        print(f"⚠️ Reseller API disabled — uvicorn not installed ({e})")
        return None

    # Webhook retry worker (one per process)
    try:
        threading.Thread(target=_webhook_worker_loop, daemon=True,
                         name="reseller-webhook-worker").start()
    except Exception:
        pass

    _last_alert = {"ts": 0.0}

    def _run():
        while True:
            try:
                uvicorn.run(app, host="0.0.0.0", port=int(port), log_level="warning")
            except Exception as e:
                print(f"⚠️ Reseller API server error: {e} — restarting in 8s")
            now = _time.time()
            if now - _last_alert["ts"] > 600:  # max one alert / 10 min
                _last_alert["ts"] = now
                _notify_admin("⚠️ *Reseller API* restarted on Railway (server crash/restart).")
            _time.sleep(8)

    t = threading.Thread(target=_run, daemon=True, name="reseller-api")
    t.start()
    print(f"🔗 Reseller API running on 0.0.0.0:{port} (docs: /api-docs/, products: /v1/products)")
    return t
