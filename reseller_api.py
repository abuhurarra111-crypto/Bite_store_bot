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
    from fastapi.responses import JSONResponse, RedirectResponse, Response
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
    mark_reseller_webhook_sent, enqueue_reseller_webhook,
    fetch_pending_webhooks, webhook_queue_bump,
    _hash_api_key, setup_api_tables,
)
from config import POINTS_PER_DOLLAR as _CFG_PPD

# API liveness heartbeat (bot job checks this to alert if the server died)
_API_LAST_PING = 0.0

# ────────────────────────────────────────────────────────────
# KEY MANAGEMENT
# ────────────────────────────────────────────────────────────

def generate_reseller_key(user_id: int, label: str = "") -> tuple:
    """Generate a bsk_... key linked to the reseller's user_id.
    Returns (plaintext_key, prefix). Plaintext shown exactly once."""
    import secrets
    migrate_reseller_tables()
    raw = secrets.token_urlsafe(32)
    plaintext = f"bsk_{raw}"
    prefix = plaintext[:14]
    key_hash = _hash_api_key(plaintext)
    conn = get_connection(); c = conn.cursor()
    c.execute("""INSERT INTO api_keys
        (api_key, bot_name, owner_id, is_active, key_hash, key_prefix, label)
        VALUES (?, ?, ?, 1, ?, ?, ?)""",
        (key_hash, "Reseller", int(user_id or 0), key_hash, prefix, str(label or "")[:60]))
    conn.commit(); conn.close()
    return plaintext, prefix


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
    """Tell the reseller how the delivery arrives:
    supplier | text | accounts | file | manual | none"""
    try:
        if (pd.get("ext_product_id") or 0) and (pd.get("ext_supplier_id") or 0):
            return "supplier"
        if (pd.get("delivery_file_id") or "").strip():
            return "file"
        if (pd.get("delivery_text") or "").strip():
            return "text"
        if (pd.get("req_account_type") or "") not in ("", "none"):
            return "accounts"
        try:
            if int(count_product_accounts(pd.get("id"), "available") or 0) > 0:
                return "accounts"
        except Exception:
            pass
        if str(pd.get("delivery_mode") or "") == "manual":
            return "manual"
        return "none"
    except Exception:
        return "none"


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
        "photoRef": str(pd.get("id")) if (pd.get("photo_id") or "").strip() else "",
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


_FULFILL_EVENTS = {}   # order_id -> threading.Event (async fulfillment)


def _apply_fulfill_result(oid, pd, qty, uid, key_row, points, event_id, result):
    """Apply a fulfillment result: DB update + webhook + refund-on-fail.
    Returns 'delivered' | 'pending' | 'failed'."""
    ok, items, status, err, file_ref = result
    now = _time.strftime("%Y-%m-%d %H:%M:%S")
    if ok and status == "delivered":
        if file_ref:
            update_reseller_order(oid, status="delivered", delivery_text="",
                                  delivered_keys="[]",
                                  delivery_file_id=file_ref.get("file_id", ""),
                                  delivery_file_name=file_ref.get("file_name", ""),
                                  delivery_file_type=file_ref.get("file_type", ""),
                                  delivered_at=now)
        else:
            update_reseller_order(oid, status="delivered",
                                  delivery_text="\n".join(str(i) for i in items),
                                  delivered_keys=json.dumps(items),
                                  delivered_at=now)
        _send_webhook(key_row, "order.delivered", {
            "orderId": str(oid), "status": "delivered",
            "deliveredKeys": items,
            "deliveredFileRef": str(oid) if file_ref else "",
            "amount": round(reseller_price_for(pd, key_row) * qty, 2)}, order_id=oid)
        return "delivered"
    if ok and status == "pending":
        update_reseller_order(oid, status="pending")
        _send_webhook(key_row, "order.pending", {
            "orderId": str(oid), "status": "pending",
            "amount": round(reseller_price_for(pd, key_row) * qty, 2)}, order_id=oid)
        return "pending"
    # failed → auto-refund points
    try:
        add_points(uid, points, tx_type="refund",
                   description=f"Reseller API refund: order #{oid}",
                   event_id=event_id + "-refund")
    except Exception:
        pass
    update_reseller_order(oid, status="failed", error=str(err or "fulfillment_failed"))
    _send_webhook(key_row, "order.failed", {
        "orderId": str(oid), "status": "failed",
        "error": str(err or "fulfillment_failed"),
        "refundedPoints": points}, order_id=oid)
    return "failed"


def _start_async_fulfill(oid, pd, qty, uid, key_row, points, event_id):
    """Fulfill in a background thread; signal the event when done."""
    ev = threading.Event()
    _FULFILL_EVENTS[oid] = ev

    def _worker():
        try:
            res = _fulfill_reseller_order(pd, qty, uid, oid)
            _apply_fulfill_result(oid, pd, qty, uid, key_row, points, event_id, res)
        except Exception:
            try:
                update_reseller_order(oid, status="failed", error="internal_error")
            except Exception:
                pass
        finally:
            try:
                ev.set()
            except Exception:
                pass
            _FULFILL_EVENTS.pop(oid, None)

    threading.Thread(target=_worker, daemon=True, name=f"reseller-fulfill-{oid}").start()
    return ev


# ────────────────────────────────────────────────────────────
# WEBHOOKS (fire-and-forget push to the reseller's server)
# ────────────────────────────────────────────────────────────

def _webhook_signature(key_row, body_bytes: bytes) -> str:
    """HMAC-SHA256 of the JSON body using the key's webhook_secret (if set)."""
    try:
        import hashlib, hmac as _hmac
        secret = ((key_row or {}).get("webhook_secret") or "").strip()
        if not secret:
            return ""
        return _hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    except Exception:
        return ""


def _send_webhook(key_row, event: str, payload: dict, order_id: int = 0):
    """POST {event, ...payload} to the key's webhook_url with HMAC signature.
    Event is queued for retry (5 attempts, backoff) if the first send fails."""
    try:
        kid = int((key_row or {}).get("id") or 0)
        url = ((key_row or {}).get("webhook_url") or "").strip()
        if not url:
            return
        body = {"event": event}
        if isinstance(payload, dict):
            body.update(payload)
        qid = enqueue_reseller_webhook(kid, int(order_id or 0), event, body)

        def _post():
            try:
                import requests as _rq
                data = json.dumps(body).encode()
                headers = {"Content-Type": "application/json"}
                sig = _webhook_signature(key_row, data)
                if sig:
                    headers["X-Bite-Signature"] = sig
                    headers["X-Bite-Key"] = str((key_row or {}).get("key_prefix") or "")
                r = _rq.post(url, data=data, headers=headers, timeout=8)
                ok = r.status_code < 300
            except Exception:
                ok = False
            if ok:
                try:
                    webhook_queue_bump(qid, 5, "sent", _time.strftime("%Y-%m-%d %H:%M:%S"))
                except Exception:
                    pass
            else:
                try:
                    from database import get_api_key_row as _gar
                    k = _gar(kid)
                    if k:
                        _retry_single_webhook(qid, k, url, body, attempt=1)
                except Exception:
                    pass
        threading.Thread(target=_post, daemon=True, name="reseller-webhook").start()
    except Exception:
        pass


def _retry_single_webhook(qid, key_row, url, body, attempt=1):
    """Retry a single webhook with backoff (max 5 attempts)."""
    try:
        import requests as _rq
        if attempt > 5:
            webhook_queue_bump(qid, attempt, "failed", _time.strftime("%Y-%m-%d %H:%M:%S"))
            return
        _time.sleep(min(60, 5 * attempt))
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        sig = _webhook_signature(key_row, data)
        if sig:
            headers["X-Bite-Signature"] = sig
        try:
            r = _rq.post(url, data=data, headers=headers, timeout=8)
            ok = r.status_code < 300
        except Exception:
            ok = False
        if ok:
            webhook_queue_bump(qid, attempt, "sent", _time.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            _retry_single_webhook(qid, key_row, url, body, attempt + 1)
    except Exception:
        pass


def _webhook_retry_loop():
    """Background loop: retries stale queued webhooks every 60s (starts a
    single retry chain per pending item, keeps DB 'pending' until done)."""
    while True:
        try:
            pending = fetch_pending_webhooks(limit=10)
            for row in pending:
                try:
                    from database import get_api_key_row as _gar
                    k = _gar(row.get("key_id") or 0)
                    if not k or not (k.get("webhook_url") or "").strip():
                        webhook_queue_bump(row["id"], 5, "failed",
                                           _time.strftime("%Y-%m-%d %H:%M:%S"))
                        continue
                    import json as _json
                    body = _json.loads(row.get("payload") or "{}")
                    url = k["webhook_url"]
                    # in-flight → mark first attempt
                    webhook_queue_bump(row["id"], max(1, int(row.get("attempts") or 1)),
                                       "pending", _time.strftime("%Y-%m-%d %H:%M:%S"))
                    def _retry_chain(qid=r["id"], krow=k, u=url, b=body):
                        try:
                            import requests as _rq
                            data = json.dumps(b).encode()
                            headers = {"Content-Type": "application/json"}
                            sig = _webhook_signature(krow, data)
                            if sig:
                                headers["X-Bite-Signature"] = sig
                            r = _rq.post(u, data=data, headers=headers, timeout=8)
                            ok = r.status_code < 300
                            if ok:
                                webhook_queue_bump(qid, 5, "sent", _time.strftime("%Y-%m-%d %H:%M:%S"))
                        except Exception:
                            pass
                    threading.Thread(target=_retry_chain, daemon=True).start()
                except Exception:
                    continue
        except Exception:
            pass
        _time.sleep(60)


# ────────────────────────────────────────────────────────────
# FASTAPI APP (only when fastapi/uvicorn are installed)
# ────────────────────────────────────────────────────────────

if _FASTAPI_OK:
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
        version="1.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
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
        # Rate limit: per-key override else default 60/min
        try:
            rl = int(row.get("rate_limit") or 0)
        except Exception:
            rl = 0
        limit = rl if rl > 0 else 60
        try:
            if count_api_requests_recent(row.get("id"), 60) >= limit:
                raise HTTPException(status_code=429, detail=f"rate limit exceeded ({limit} req/min)")
        except HTTPException:
            raise
        except Exception:
            pass
        try:
            log_api_request(row.get("id"), request.url.path, 200, client_ip)
        except Exception:
            pass
        global _API_LAST_PING
        _API_LAST_PING = _time.time()
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

        # SUPPLIER-LINKED products: async fulfillment (max 15s wait).
        # Fast suppliers → instant deliveredKeys; slow ones → "processing"
        # (background thread finishes + webhooks/poll deliver the result).
        is_supplier = bool((pd.get("ext_product_id") or 0) and (pd.get("ext_supplier_id") or 0))

        if is_supplier:
            ev = _start_async_fulfill(oid, pd, qty, uid, key, points, event_id)
            if not ev.wait(15):
                return {"ok": True, "orderId": str(oid), "deliveredKeys": [],
                        "deliveredKey": "", "deliveredFileRef": "",
                        "amount": round(price_usd * qty, 2), "status": "processing",
                        "note": "delivery will arrive shortly — poll GET /v1/orders/{id} or wait for webhook"}
            r = get_reseller_order(oid)
            st = (r or {}).get("status")
            if st == "delivered":
                items = _parse_keys((r or {}).get("delivered_keys"))
                return {"ok": True, "orderId": str(oid), "deliveredKeys": items,
                        "deliveredKey": items[0] if items else "",
                        "deliveredFileRef": str(oid) if (r or {}).get("delivery_file_id") else "",
                        "amount": round(price_usd * qty, 2), "status": "delivered"}
            if st == "failed":
                return JSONResponse(status_code=502, content={
                    "ok": False, "orderId": str(oid),
                    "error": (r or {}).get("error") or "fulfillment_failed",
                    "refundedPoints": points})
            return {"ok": True, "orderId": str(oid), "deliveredKeys": [],
                    "deliveredKey": "", "deliveredFileRef": "",
                    "amount": round(price_usd * qty, 2), "status": st or "pending"}

        # NON-supplier: synchronous fulfillment (static / accounts / file / manual)
        outcome = _apply_fulfill_result(
            oid, pd, qty, uid, key, points, event_id,
            _fulfill_reseller_order(pd, qty, uid, oid))
        if outcome == "delivered":
            r = get_reseller_order(oid)
            items = _parse_keys((r or {}).get("delivered_keys"))
            return {"ok": True, "orderId": str(oid), "deliveredKeys": items,
                    "deliveredKey": items[0] if items else "",
                    "deliveredFileRef": str(oid) if (r or {}).get("delivery_file_id") else "",
                    "amount": round(price_usd * qty, 2), "status": "delivered"}
        if outcome == "pending":
            return {"ok": True, "orderId": str(oid), "deliveredKeys": [],
                    "deliveredKey": "", "deliveredFileRef": "",
                    "amount": round(price_usd * qty, 2), "status": "pending"}
        r = get_reseller_order(oid)
        return JSONResponse(status_code=502, content={
            "ok": False, "orderId": str(oid),
            "error": (r or {}).get("error") or "fulfillment_failed",
            "refundedPoints": points,
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

    @app.get("/v1/images/{product_id}", summary="Product photo bytes",
             description=(
                 "Returns the product photo as bytes so your bot can show an\n"
                 "image (Telegram file IDs don't work across bots). Scoped to\n"
                 "products enabled for resellers."
             ))
    async def _product_image(product_id: int, key=Depends(_require_key)):
        pd = get_product(product_id)
        if not pd:
            raise HTTPException(status_code=404, detail="product not found")
        pd = dict(pd)
        if not pd.get("is_active") or int(pd.get("is_hidden") or 0):
            raise HTTPException(status_code=404, detail="product not available")
        if int(pd.get("reseller_enabled") if pd.get("reseller_enabled") is not None else 1) != 1:
            raise HTTPException(status_code=403, detail="product not enabled for resellers")
        photo_id = (pd.get("photo_id") or "").strip()
        if not photo_id:
            raise HTTPException(status_code=404, detail="no photo for this product")
        try:
            import requests as _rq
            token = os.getenv("BOT_TOKEN", "").strip()
            j = _rq.post(f"https://api.telegram.org/bot{token}/getFile",
                         json={"file_id": photo_id}, timeout=20).json()
            if not j.get("ok"):
                raise HTTPException(status_code=502, detail="image source unavailable")
            path = j["result"]["file_path"]
            data = _rq.get(f"https://api.telegram.org/file/bot{token}/{path}", timeout=40)
            if data.status_code != 200:
                raise HTTPException(status_code=502, detail="image source unavailable")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=502, detail="image source unavailable")
        return Response(content=data.content,
                        media_type=data.headers.get("content-type", "image/jpeg"))

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
    auto-restart (if the server dies it comes back after 8s). Also starts a
    heartbeat + webhook-retry loop. Never crashes the bot."""
    if not _FASTAPI_OK:
        print("⚠️ Reseller API disabled — install fastapi+uvicorn to enable")
        return None
    try:
        import uvicorn
    except Exception as e:
        print(f"⚠️ Reseller API disabled — uvicorn not installed ({e})")
        return None

    def _run():
        while True:
            try:
                uvicorn.run(app, host="0.0.0.0", port=int(port), log_level="warning")
            except Exception as e:
                print(f"⚠️ Reseller API server error: {e} — restarting in 8s")
            _time.sleep(8)

    def _heartbeat():
        global _API_LAST_PING
        while True:
            _API_LAST_PING = _time.time()
            _time.sleep(30)

    threading.Thread(target=_run, daemon=True, name="reseller-api").start()
    threading.Thread(target=_heartbeat, daemon=True, name="reseller-api-heartbeat").start()
    threading.Thread(target=_webhook_retry_loop, daemon=True, name="reseller-webhook-retry").start()
    print(f"🔗 Reseller API running on 0.0.0.0:{port} (docs: /api-docs/, products: /v1/products)")
    return True


def api_last_ping() -> float:
    """When the API server last proved it was alive (seconds since epoch)."""
    return _API_LAST_PING
