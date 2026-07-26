# ============================================================
# 🧩 v77 BUNDLE: payments.py
# ============================================================
# This file is the merged result of 5 originally separate modules:
#   • binance_pay_api.py
#   • binance_email_api.py
#   • easypaisa_api.py
#   • jazzcash_api.py
#   • screenshot_verifier.py
#
# 🛡️ ALL CODE IS PRESERVED VERBATIM. Each original file's contents appears
# below in its own section. Imports and behavior are byte-identical to the
# pre-merge codebase — only file count is reduced.
# ============================================================


# ============================================================
# 📄 ORIGINAL FILE: binance_pay_api.py
# ============================================================

# ============================================
# 🪙 BINANCE PAY API — Direct REST integration (v61)
# ============================================
# Replaces (or augments) the IMAP/Gmail email scraping approach.
# Uses Binance Spot SAPI to fetch recent Pay transactions and crypto deposits,
# matches them against pending bot orders.
#
# ⚠️ PROXY REQUIRED for Render.com (US/EU) deployments:
#    Binance returns HTTP 451 "restricted location" without a Pakistan / allowed proxy.
#    Set BINANCE_PROXY_URL env var to a Pakistani residential / data-center HTTPS proxy.
#    Format examples:
#        http://user:pass@host:port
#        http://host:port
#        socks5://user:pass@host:port
#
# Endpoints used:
#    GET /sapi/v1/pay/transactions   — Binance Pay history (most relevant)
#    GET /sapi/v1/capital/deposit/hisrec — crypto deposit history
#
# Auth: HMAC-SHA256 signed query (timestamp + recvWindow).

import os
import time
import hmac
import hashlib
import logging
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════
# 🔐 CREDENTIALS, PROXY POOL & ROTATION (v63)
# ════════════════════════════════════════════
BINANCE_API_KEY    = None
BINANCE_API_SECRET = None
BINANCE_PROXY_URL  = None       # single (back-compat)
BINANCE_PROXY_LIST = None       # comma-separated multi (v63)
BINANCE_API_BASE   = "https://api.binance.com"

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY")    or BINANCE_API_KEY
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET") or BINANCE_API_SECRET
BINANCE_PROXY_URL  = os.getenv("BINANCE_PROXY_URL")  or BINANCE_PROXY_URL
BINANCE_PROXY_LIST = os.getenv("BINANCE_PROXY_LIST") or BINANCE_PROXY_LIST

# Allow alternate base URLs (e.g. api1/api2/api3 / GCP / Tokyo)
_alt = os.getenv("BINANCE_API_BASE")
if _alt:
    BINANCE_API_BASE = _alt.rstrip("/")

# ── v63: built-in default pool of free PK proxies (last-resort) ──
# These are PUBLIC free proxies. Their lifetime is short; they're only
# used if neither BINANCE_PROXY_URL nor BINANCE_PROXY_LIST is set.
# Update via the admin panel any time without redeploying.
_DEFAULT_PROXY_POOL = [
    "socks5://103.121.120.242:1080",   # Logon Broadband
    "socks5://103.236.134.210:1080",   # Eurekanet Karachi
    "socks5://182.184.119.180:1080",   # PK SOCKS5 elite
    "http://103.198.154.151:8888",     # Play Broadband Lahore
]


def _load_proxy_pool() -> list[str]:
    """
    Build the live proxy candidate list, in priority order:
      1) DB-stored extra list (admin-added via panel) — highest priority
      2) BINANCE_PROXY_LIST env  (comma-separated)
      3) BINANCE_PROXY_URL  env  (single)
      4) Built-in default pool (last-resort)
    Duplicates removed, order preserved.
    """
    out: list[str] = []

    # 1) DB-stored list
    try:
        from database import get_setting
        raw = (get_setting("binance_proxy_pool", "") or "").strip()
        if raw:
            for p in raw.split(","):
                p = p.strip()
                if p and p not in out:
                    out.append(p)
    except Exception:
        pass

    # 2) env list
    if BINANCE_PROXY_LIST:
        for p in BINANCE_PROXY_LIST.split(","):
            p = p.strip()
            if p and p not in out:
                out.append(p)

    # 3) single env
    if BINANCE_PROXY_URL:
        p = BINANCE_PROXY_URL.strip()
        if p and p not in out:
            out.append(p)

    # 4) defaults (only if nothing else set)
    if not out:
        out.extend(_DEFAULT_PROXY_POOL)

    return out


# ── In-memory proxy health cache (per-process) ──
# { proxy_url: {"status": "ok"|"fail"|"unknown",
#               "last_ok": epoch,  "last_fail": epoch,
#               "cooldown_until": epoch,  "last_error": str } }
_PROXY_HEALTH: dict[str, dict] = {}
_COOLDOWN_SECS = 300   # 5 min cooldown after a proxy fails


def _is_in_cooldown(proxy_url: str) -> bool:
    h = _PROXY_HEALTH.get(proxy_url) or {}
    return time.time() < float(h.get("cooldown_until") or 0)


def _mark_proxy_ok(proxy_url: str):
    _PROXY_HEALTH[proxy_url] = {
        **(_PROXY_HEALTH.get(proxy_url) or {}),
        "status": "ok",
        "last_ok": time.time(),
        "cooldown_until": 0,
        "last_error": "",
    }


def _mark_proxy_fail(proxy_url: str, reason: str = ""):
    _PROXY_HEALTH[proxy_url] = {
        **(_PROXY_HEALTH.get(proxy_url) or {}),
        "status": "fail",
        "last_fail": time.time(),
        "cooldown_until": time.time() + _COOLDOWN_SECS,
        "last_error": str(reason)[:200],
    }


def get_proxy_health_snapshot() -> list[dict]:
    """For admin panel — returns ordered list of proxies + status."""
    pool = _load_proxy_pool()
    rows = []
    for p in pool:
        h = _PROXY_HEALTH.get(p) or {}
        rows.append({
            "url": p,
            "status": h.get("status", "unknown"),
            "last_ok": h.get("last_ok"),
            "last_fail": h.get("last_fail"),
            "cooldown_until": h.get("cooldown_until"),
            "in_cooldown": _is_in_cooldown(p),
            "last_error": h.get("last_error", ""),
        })
    return rows


def reset_proxy_cooldowns():
    """Admin button — clear all cooldowns so every proxy is re-tried."""
    for p in list(_PROXY_HEALTH.keys()):
        _PROXY_HEALTH[p]["cooldown_until"] = 0


def _proxies_for(proxy_url: str | None):
    """Build a `requests` proxies dict from a URL (or None)."""
    if not proxy_url:
        return None
    url = proxy_url.strip()
    return {"http": url, "https": url}


# Legacy single-proxy helper (kept for any external callers)
def _proxies():
    pool = _load_proxy_pool()
    return _proxies_for(pool[0]) if pool else None


def is_configured():
    return bool(BINANCE_API_KEY and BINANCE_API_SECRET)


def is_proxy_configured():
    return bool(_load_proxy_pool())


# ════════════════════════════════════════════
# 🔏 SIGNED REQUEST HELPER (with proxy rotation)
# ════════════════════════════════════════════
def _sign(query_string: str) -> str:
    return hmac.new(
        BINANCE_API_SECRET.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _do_request(method_url: str, headers: dict, timeout: int):
    """
    Try the configured proxy pool in order until one succeeds.
    Returns (status_code, response_obj_or_text, used_proxy_or_None).
    If proxy pool empty → direct (no proxy).
    """
    pool = _load_proxy_pool()
    if not pool:
        # No proxies — direct
        try:
            r = requests.get(method_url, headers=headers, timeout=timeout)
            return r.status_code, r, None
        except Exception as e:
            return -1, str(e), None

    last_err = "no candidates"
    for proxy_url in pool:
        if _is_in_cooldown(proxy_url):
            continue
        try:
            r = requests.get(
                method_url, headers=headers,
                proxies=_proxies_for(proxy_url), timeout=timeout,
            )
            # Treat HTTP 451 (geo-block) as a proxy failure so we rotate
            if r.status_code == 451:
                _mark_proxy_fail(proxy_url, "HTTP 451 (geo-blocked)")
                last_err = f"{proxy_url}: HTTP 451"
                continue
            _mark_proxy_ok(proxy_url)
            return r.status_code, r, proxy_url
        except requests.exceptions.ProxyError as e:
            _mark_proxy_fail(proxy_url, f"ProxyError: {e}")
            last_err = f"{proxy_url}: ProxyError"
        except requests.exceptions.ConnectTimeout as e:
            _mark_proxy_fail(proxy_url, "ConnectTimeout")
            last_err = f"{proxy_url}: ConnectTimeout"
        except requests.exceptions.ReadTimeout as e:
            _mark_proxy_fail(proxy_url, "ReadTimeout")
            last_err = f"{proxy_url}: ReadTimeout"
        except requests.exceptions.RequestException as e:
            _mark_proxy_fail(proxy_url, str(e)[:100])
            last_err = f"{proxy_url}: {type(e).__name__}"

    # All proxies failed or all in cooldown
    return -1, f"All proxies failed (last={last_err})", None


def _signed_get(path: str, params: dict | None = None, timeout: int = 15) -> tuple[int, dict | str]:
    """Signed GET with auto-rotating proxy pool."""
    if not is_configured():
        return -1, {"error": "BINANCE_API_KEY / BINANCE_API_SECRET not set"}

    params = dict(params or {})
    params["timestamp"]  = int(time.time() * 1000)
    params["recvWindow"] = 60000

    qs  = urlencode(params)
    sig = _sign(qs)
    url = f"{BINANCE_API_BASE}{path}?{qs}&signature={sig}"

    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}

    code, resp, used = _do_request(url, headers, timeout)
    if code == -1:
        logger.error(f"[BinancePayAPI] Request failed via proxy pool: {resp}")
        return -1, {"error": str(resp)}

    try:
        return code, resp.json()
    except Exception:
        return code, getattr(resp, "text", str(resp))


# ════════════════════════════════════════════
# 🩺 DIAGNOSTIC / TEST
# ════════════════════════════════════════════
def test_connection() -> tuple[bool, str]:
    """v63: Test each configured proxy until one works, plus signed account check.
       Used by admin panel "Test Binance API" button."""
    if not is_configured():
        return False, "❌ BINANCE_API_KEY / BINANCE_API_SECRET not set on server."

    pool = _load_proxy_pool()
    if not pool:
        # No proxies — try direct (will most likely fail with 451 on Render)
        try:
            r = requests.get(f"{BINANCE_API_BASE}/api/v3/time", timeout=12)
            if r.status_code == 451:
                return False, (
                    "❌ HTTP 451 — Binance blocks this server location.\n"
                    "Add at least one proxy via the 📡 Proxy Status panel, "
                    "or set BINANCE_PROXY_URL / BINANCE_PROXY_LIST in Render env."
                )
            if r.status_code != 200:
                return False, f"❌ Direct ping failed: HTTP {r.status_code}"
        except Exception as e:
            return False, f"❌ Direct ping error: {e}"
        code, data = _signed_get("/api/v3/account")
        if code == 200:
            return True, "✅ Binance API connected (direct, no proxy)."
        return False, f"❌ Account check failed: HTTP {code} — {str(data)[:200]}"

    # ── Try each proxy in the pool ──
    # First, force-clear cooldowns so admin gets a real picture
    reset_proxy_cooldowns()

    tried = []
    winner = None
    for proxy_url in pool:
        t0 = time.time()
        try:
            r = requests.get(
                f"{BINANCE_API_BASE}/api/v3/time",
                proxies=_proxies_for(proxy_url), timeout=10,
            )
            elapsed = time.time() - t0
            if r.status_code == 451:
                _mark_proxy_fail(proxy_url, "HTTP 451")
                tried.append(f"❌ `{proxy_url}` — HTTP 451 (geo-block)  [{elapsed:.1f}s]")
            elif r.status_code != 200:
                _mark_proxy_fail(proxy_url, f"HTTP {r.status_code}")
                tried.append(f"❌ `{proxy_url}` — HTTP {r.status_code}  [{elapsed:.1f}s]")
            else:
                _mark_proxy_ok(proxy_url)
                tried.append(f"✅ `{proxy_url}` — OK  [{elapsed:.1f}s]")
                winner = proxy_url
                break
        except requests.exceptions.ProxyError as e:
            _mark_proxy_fail(proxy_url, "ProxyError")
            tried.append(f"❌ `{proxy_url}` — proxy error  [{time.time()-t0:.1f}s]")
        except requests.exceptions.ConnectTimeout:
            _mark_proxy_fail(proxy_url, "ConnectTimeout")
            tried.append(f"❌ `{proxy_url}` — connect timeout  [{time.time()-t0:.1f}s]")
        except requests.exceptions.ReadTimeout:
            _mark_proxy_fail(proxy_url, "ReadTimeout")
            tried.append(f"❌ `{proxy_url}` — read timeout  [{time.time()-t0:.1f}s]")
        except Exception as e:
            _mark_proxy_fail(proxy_url, str(e)[:80])
            tried.append(f"❌ `{proxy_url}` — {type(e).__name__}  [{time.time()-t0:.1f}s]")

    summary = "\n".join(tried)
    if not winner:
        return False, (
            f"❌ All {len(pool)} proxies failed.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n{summary}\n\n"
            f"💡 Add a working proxy via 📡 Proxy Status → Add Proxy."
        )

    # We have a winning proxy. Now verify the signed account endpoint.
    code, data = _signed_get("/api/v3/account")
    if code == 200:
        return True, (
            f"✅ Binance API connected via:\n`{winner}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Pool ({len(pool)} proxies):\n{summary}"
        )
    if isinstance(data, dict) and data.get("code"):
        return False, (
            f"⚠️ Proxy works but key error.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"API error {data.get('code')}: {data.get('msg','')}\n\n"
            f"Check BINANCE_API_KEY / BINANCE_API_SECRET on Render."
        )
    return False, f"❌ Account check failed: HTTP {code} — {str(data)[:200]}"


# ════════════════════════════════════════════
# 💰 FETCH RECENT BINANCE PAY TRANSACTIONS
# ════════════════════════════════════════════
def get_recent_pay_transactions(lookback_hours: int = 48, limit: int = 100) -> list[dict]:
    """
    GET /sapi/v1/pay/transactions
    Returns a normalised list of dicts:
        {
          'order_id': str,
          'transaction_id': str,
          'amount': float,
          'currency': str,
          'counterparty': str,         # payer's name / nickname
          'order_type': str,           # 'PAY' / 'PAY_REFUND' / 'C2C' etc
          'time_ms': int,              # epoch ms
          'note': str,                 # transfer remarks (if any)
          'raw': dict,                 # full original
        }
    Only successful incoming-to-us transactions are returned.
    """
    if not is_configured():
        return []

    params = {
        "startTime": int((time.time() - lookback_hours * 3600) * 1000),
        "endTime":   int(time.time() * 1000),
        "limit":     min(max(int(limit or 10), 1), 100),
    }
    code, data = _signed_get("/sapi/v1/pay/transactions", params)
    if code != 200 or not isinstance(data, dict):
        logger.warning(f"[BinancePayAPI] pay/transactions failed: {code} {str(data)[:200]}")
        return []

    rows = data.get("data") or []
    out  = []
    for row in rows:
        try:
            # Binance Pay txn shape (subset):
            # orderType: PAY (sent), PAY_REFUND, C2C, CRYPTO_BOX, ...
            # transactionId, orderType, transactionTime, amount, currency, walletType
            # payerInfo: {name, accountId, type, email}  ← may be present
            # receiverInfo: ...
            otype = (row.get("orderType") or "").upper()

            # Only count incoming credits to us
            amt_raw = row.get("amount") or "0"
            try:
                amt = float(amt_raw)
            except Exception:
                amt = 0.0

            # An incoming transfer (us = receiver) is positive amount with orderType=PAY (others paid us)
            # Binance returns amount as positive for credits, negative for debits.
            # Filter: positive credits only.
            if amt <= 0:
                continue

            payer = row.get("payerInfo") or {}
            counterparty = (
                payer.get("name")
                or payer.get("nickName")
                or payer.get("accountId")
                or ""
            )
            note = row.get("note") or row.get("orderRemark") or ""

            out.append({
                "order_id":       str(row.get("transactionId") or row.get("orderId") or ""),
                "transaction_id": str(row.get("transactionId") or ""),
                "amount":         amt,
                "currency":       row.get("currency") or "USDT",
                "counterparty":   str(counterparty)[:60],
                "order_type":     otype,
                "time_ms":        int(row.get("transactionTime") or 0),
                "note":           str(note)[:200],
                "raw":            row,
            })
        except Exception as e:
            logger.warning(f"[BinancePayAPI] parse row failed: {e}")
            continue

    return out


# ════════════════════════════════════════════
# 💎 FETCH RECENT CRYPTO DEPOSITS (fallback for non-Pay transfers)
# ════════════════════════════════════════════
def get_recent_deposits(coin: str = "USDT", lookback_hours: int = 48, limit: int = 50) -> list[dict]:
    """GET /sapi/v1/capital/deposit/hisrec — recent on-chain deposits.
       Returns normalised dicts: {amount, currency, txid, address, time_ms, status}"""
    if not is_configured():
        return []

    params = {
        "coin":      coin,
        "startTime": int((time.time() - lookback_hours * 3600) * 1000),
        "endTime":   int(time.time() * 1000),
        "limit":     min(max(int(limit or 10), 1), 1000),
        "status":    1,  # 1 = success
    }
    code, data = _signed_get("/sapi/v1/capital/deposit/hisrec", params)
    if code != 200 or not isinstance(data, list):
        logger.warning(f"[BinancePayAPI] deposit/hisrec failed: {code} {str(data)[:200]}")
        return []

    out = []
    for row in data:
        try:
            amt = float(row.get("amount") or 0)
            if amt <= 0:
                continue
            out.append({
                "amount":   amt,
                "currency": row.get("coin") or coin,
                "txid":     str(row.get("txId") or ""),
                "address":  str(row.get("address") or ""),
                "network":  str(row.get("network") or ""),
                "time_ms":  int(row.get("insertTime") or 0),
                "status":   int(row.get("status") or 0),
                "raw":      row,
            })
        except Exception as e:
            logger.warning(f"[BinancePayAPI] parse deposit failed: {e}")
            continue
    return out


# ════════════════════════════════════════════
# 🎯 MATCH AGAINST AN ORDER
# ════════════════════════════════════════════
def find_matching_payment(
    *,
    expected_amount: float,
    sender_name: str | None = None,
    note_id: str | None = None,
    tolerance: float = 0.05,
    lookback_hours: int = 48,
) -> dict | None:
    """Scan recent Pay transactions and return the first one that matches the criteria.

    Match policy:
        - note_id provided → match if note contains it (strongest)
        - sender_name provided → fuzzy match on counterparty
        - expected_amount → always required, must match within tolerance
    """
    if not is_configured():
        return None
    try:
        expected_amount = float(expected_amount)
    except (TypeError, ValueError):
        return None

    txns = get_recent_pay_transactions(lookback_hours=lookback_hours, limit=100)
    note_id = (note_id or "").strip()
    sender_name = (sender_name or "").strip()

    for t in txns:
        try:
            # Amount check (always)
            if abs(t["amount"] - expected_amount) > tolerance:
                continue

            # Anti-reuse check
            try:
                from database import is_txid_used
                if t["transaction_id"] and is_txid_used(t["transaction_id"]):
                    continue
            except Exception:
                pass

            # Note ID match (if provided)
            if note_id:
                if note_id.lower() not in (t.get("note") or "").lower():
                    continue
                return t

            # Sender name match (if provided)
            if sender_name:
                cp = t.get("counterparty") or ""
                if _fuzzy_name(sender_name, cp):
                    return t
                continue

            # Neither note nor sender — accept on amount alone (risky, last resort)
            return t
        except Exception as e:
            logger.warning(f"[BinancePayAPI] match err: {e}")
            continue

    return None


# ════════════════════════════════════════════
# 🎯 v62: FIND PAYMENT BY ORDER ID
# ════════════════════════════════════════════
def find_payment_by_order_id(
    *,
    order_id: str,
    expected_amount: float | None = None,
    tolerance: float = 0.05,
    lookback_hours: int = 72,
) -> dict | None:
    """
    Find a Binance Pay transaction matching the user-supplied Order ID.

    The user copies "Order ID" from their Binance Pay receipt (visible in app
    under transaction details). That value can be:
      - transactionId (M_P_*** or pure digits, varies by orderType)
      - merchantTradeNo / prepayId for merchant pay
      - The trailing internal id (Y2026...) sometimes shown

    We match by case-insensitive substring against transactionId, raw row text.
    Returns a normalised dict (same shape as get_recent_pay_transactions rows)
    or None.
    """
    if not is_configured():
        return None
    order_id = (order_id or "").strip()
    if len(order_id) < 6:
        return None
    try:
        expected_amount = float(expected_amount) if expected_amount is not None else None
    except (TypeError, ValueError):
        expected_amount = None

    txns = get_recent_pay_transactions(lookback_hours=lookback_hours, limit=100)

    key = order_id.lower()
    for t in txns:
        try:
            txid = str(t.get("transaction_id") or "").lower()
            raw  = str(t.get("raw") or "").lower()
            # match: full equality, substring, or substring inside raw blob
            if key != txid and key not in txid and key not in raw:
                continue

            # Amount check if provided
            if expected_amount is not None and expected_amount > 0:
                if abs(t["amount"] - expected_amount) > tolerance:
                    continue

            # Anti-reuse
            try:
                from database import is_txid_used
                if t["transaction_id"] and is_txid_used(t["transaction_id"]):
                    continue
            except Exception:
                pass

            return t
        except Exception as e:
            logger.warning(f"[BinancePayAPI] order-id match err: {e}")
            continue
    return None


def _fuzzy_name(a: str, b: str) -> bool:
    import re as _re
    if not a or not b:
        return False
    aa = _re.sub(r"\s+", " ", a.lower().strip())
    bb = _re.sub(r"\s+", " ", b.lower().strip())
    if aa == bb:
        return True
    a_words = set(w for w in aa.split() if len(w) >= 3)
    b_words = set(w for w in bb.split() if len(w) >= 3)
    if a_words and b_words and (a_words & b_words):
        return True
    if len(aa) >= 3 and len(bb) >= 3 and (aa in bb or bb in aa):
        return True
    return False


# ════════════════════════════════════════════
# 🔗 UNIFIED VERIFY (Pay API → fall back to email)
# ════════════════════════════════════════════
def verify_payment_unified(
    *,
    expected_amount: float,
    sender_name: str | None = None,
    note_id: str | None = None,
    order_id: str | None = None,
    tolerance: float = 0.05,
    use_email_fallback: bool = True,
) -> dict:
    """
    Try Binance Pay API first; if unavailable / no match, fall back to Gmail IMAP.
    Returns the same shape used elsewhere:
        {'success': bool, 'status': str, 'reason': str,
         'amount': float, 'sender_name': str, 'email_hash': str, 'txid': str,
         'source': 'api' | 'email'}
    """
    result = {
        'success': False, 'status': '', 'reason': '',
        'amount': 0.0, 'sender_name': '', 'email_hash': '',
        'txid': '', 'source': '',
    }

    if is_configured():
        try:
            match = None
            # v62: Order ID match takes priority — most reliable
            if order_id:
                match = find_payment_by_order_id(
                    order_id=order_id,
                    expected_amount=expected_amount,
                    tolerance=tolerance,
                )
            if not match:
                match = find_matching_payment(
                    expected_amount=expected_amount,
                    sender_name=sender_name,
                    note_id=note_id,
                    tolerance=tolerance,
                )
            if match:
                result.update({
                    'success':     True,
                    'status':      'matched',
                    'reason':      'Payment verified successfully.',
                    'amount':      match.get('amount', 0.0),
                    'sender_name': match.get('counterparty') or (sender_name or ''),
                    'txid':        match.get('transaction_id') or '',
                    'email_hash':  f"binance-api:{match.get('transaction_id')}",
                    'source':      'api',
                })
                return result
        except Exception as e:
            logger.warning(f"[BinancePayAPI] API verify error, will fall back: {e}")

    if not use_email_fallback:
        result['status'] = 'not_found'
        result['reason'] = 'No matching Binance payment found via API.'
        return result

    # Fallback to Gmail IMAP method
    try:
        # [v77-merge] from binance_email_api import (
        # [v77-merge] verify_binance_payment, verify_binance_payment_by_note,
        # [v77-merge] verify_binance_payment_by_order_id,
        # [v77-merge] )
        if order_id:
            # v62: prefer order-id match in email body if available
            sub = verify_binance_payment_by_order_id(
                order_id, expected_amount=expected_amount, tolerance=tolerance)
        elif note_id:
            sub = verify_binance_payment_by_note(note_id, expected_amount=expected_amount, tolerance=tolerance)
        elif sender_name:
            sub = verify_binance_payment(sender_name, expected_amount, tolerance=tolerance)
        else:
            sub = {'success': False, 'status': 'invalid_input', 'reason': 'No matcher provided'}
        sub['source'] = 'email'
        return sub
    except Exception as e:
        logger.error(f"[BinancePayAPI] Email fallback error: {e}")
        result['status'] = 'imap_error'
        result['reason'] = 'Verification temporarily unavailable.'
        return result


# ============================================================
# 📄 ORIGINAL FILE: binance_email_api.py
# ============================================================

# ============================================
# 📧 BINANCE EMAIL API — DEPRECATED in v76
# ============================================
# 🆕 v76: Gmail IMAP fallback method PERMANENTLY DISABLED.
# Reason: the bot now uses Binance Pay REST API exclusively (v61 path), which
# is faster, more reliable, and doesn't need leaked Gmail credentials.
#
# This module is kept as a no-op stub so existing imports in
# handlers_admin.py / handlers_order.py / binance_pay_api.py keep working
# without raising ImportError, but every function now returns the same
# "not configured" / negative result.
# ============================================

import logging
logger = logging.getLogger(__name__)


def connect_imap():
    """🚫 Disabled in v76 — Gmail IMAP method removed."""
    raise RuntimeError("Binance Gmail IMAP is disabled in v76. Use Binance Pay API instead.")


def is_configured() -> bool:
    """🚫 Always returns False in v76 so all UI/code paths treat email as off."""
    return False


def test_connection():
    """🚫 Disabled in v76."""
    return False, "Binance Gmail IMAP disabled in v76. Use Binance Pay API."


def extract_binance_payment(msg):
    """🚫 No-op."""
    return None


def verify_binance_payment(sender_name, expected_amount, tolerance=0.05):
    """🚫 v76: always returns a negative result so callers fall through."""
    logger.debug("[BinanceEmail] verify_binance_payment called but module is "
                 "deprecated in v76 — returning negative.")
    return {
        "success": False,
        "error": "binance_email_disabled_v76",
        "message": ("Binance Gmail IMAP method is disabled. "
                    "Please use Binance Pay (API) — the bot will auto-verify "
                    "your Order ID."),
    }


def verify_binance_payment_by_note(note_id, expected_amount=None, tolerance=0.05):
    """🚫 v76: always returns negative."""
    return {
        "success": False,
        "error": "binance_email_disabled_v76",
        "message": "Binance Gmail IMAP method removed. Use Binance Pay API.",
    }


def verify_binance_payment_by_order_id(order_id, expected_amount=None, tolerance=0.05):
    """🚫 v76: always returns negative."""
    return {
        "success": False,
        "error": "binance_email_disabled_v76",
        "message": "Binance Gmail IMAP method removed. Use Binance Pay API.",
    }


# ============================================================
# 📄 ORIGINAL FILE: easypaisa_api.py
# ============================================================

# ============================================
# 📧 EASYPAISA AUTO-VERIFY via Gmail IMAP (v31 — Simpler)
# ============================================
# User sends only TRX ID → bot fetches Gmail → extracts EVERYTHING from email.
#
# Supported SMS formats (both SENT and RECEIVED):
#   "Rs 300.00 from Ayesha Ziam with Easypaisa Account ... Trx ID 50568603579"
#   "Rs. 600.0 sent to Ayesha Ziam with easypaisa account ... Trx ID 50562864797"

import os
import re
import imaplib
import email
from email.header import decode_header
import logging

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════
# 🔐 LOAD CREDENTIALS (.env)
# ════════════════════════════════════════════
EMAIL_ADDRESS = None
EMAIL_PASSWORD = None
try:
    from dotenv import load_dotenv
    load_dotenv()
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
except ImportError:
    pass

if not EMAIL_ADDRESS:
    try:
        from config import EMAIL_ADDRESS as _ea, EMAIL_PASSWORD as _ep
        EMAIL_ADDRESS = _ea
        EMAIL_PASSWORD = _ep
    except Exception:
        pass


# ════════════════════════════════════════════
# 🔌 IMAP CONNECTION
# ════════════════════════════════════════════
def connect_imap():
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        logger.error("EMAIL_ADDRESS/PASSWORD not set in .env")
        return None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        return mail
    except Exception as e:
        logger.error(f"Gmail IMAP connect failed: {e}")
        return None


def is_configured():
    return bool(EMAIL_ADDRESS and EMAIL_PASSWORD)


def test_connection():
    if not is_configured():
        return False, "EMAIL_ADDRESS / EMAIL_PASSWORD not set in .env file"
    mail = connect_imap()
    if not mail:
        return False, "Failed to connect/login to Gmail. Check app password."
    try:
        mail.select("INBOX")
        try: mail.logout()
        except: pass
        return True, f"✅ IMAP connected: {EMAIL_ADDRESS}"
    except Exception as e:
        try: mail.logout()
        except: pass
        return False, f"Connection error: {e}"


# ════════════════════════════════════════════
# 🔍 EMAIL PARSING (FLEXIBLE — handles all formats)
# ════════════════════════════════════════════
def _decode_subject(raw_subject):
    if not raw_subject: return ""
    out = ""
    for part, charset in decode_header(raw_subject):
        if isinstance(part, bytes):
            try: out += part.decode(charset or "utf-8", errors="ignore")
            except: out += part.decode("utf-8", errors="ignore")
        else:
            out += str(part)
    return out


def _get_email_body(msg):
    """v61: strip <script>/<style>/<!-- --> before tags to avoid CSS leakage."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode("utf-8", errors="ignore")
                except: continue
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            html = payload.decode("utf-8", errors="ignore")
                            html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL|re.IGNORECASE)
                            html = re.sub(r'<style[^>]*>.*?</style>',   ' ', html, flags=re.DOTALL|re.IGNORECASE)
                            html = re.sub(r'<!--.*?-->',                ' ', html, flags=re.DOTALL)
                            html = re.sub(r'<head[^>]*>.*?</head>',     ' ', html, flags=re.DOTALL|re.IGNORECASE)
                            html = re.sub(r'<[^>]+>', ' ', html)
                            html = html.replace('&nbsp;', ' ').replace('&amp;', '&')
                            html = html.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
                            html = re.sub(r'&#x?[\da-fA-F]+;', ' ', html)
                            html = re.sub(r'&[a-zA-Z]+;', ' ', html)
                            html = re.sub(r'\s+', ' ', html)
                            body += html
                    except: continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="ignore")
        except: pass
    return body


def extract_payment_info(msg):
    """Parse SMSForwarder-EasyPaisa email — FLEXIBLE regex.
    Returns dict {amount, tid, name, type} or None if not matching.
    """
    # Subject check — flexible
    subject = _decode_subject(msg.get("Subject", "")).lower()
    if "easypaisa" not in subject and "smsforwarder" not in subject:
        return None

    body = _get_email_body(msg)
    if not body:
        return None

    # 🔧 v31 FLEXIBLE REGEX — handles all variations:
    # "Rs 300.00", "Rs. 300.00", "Rs.300", "Rs 300", "RS 300.0" etc
    amount_match = re.search(r'Rs\.?\s*([\d,]+\.?\d*)', body, re.IGNORECASE)

    # TRX ID — 10-13 digits (covers all formats)
    tid_match = re.search(r'Trx\s*ID\s*[:\.]?\s*(\d{10,13})', body, re.IGNORECASE)

    # Type: "received" OR "sent"
    is_received = bool(re.search(r'received\s+Rs|have\s+Received', body, re.IGNORECASE))
    is_sent = bool(re.search(r'sent\s+to|debited|Rs\.?\s*[\d,\.]+\s+sent', body, re.IGNORECASE))

    # Name — handle BOTH formats:
    #   "from Ayesha Ziam with Easypaisa" (received)
    #   "sent to Ayesha Ziam with easypaisa" (sent)
    name = None
    name_patterns = [
        # "from NAME with" or "from NAME    with" (multiple spaces)
        r'from\s+([A-Za-z][A-Za-z\s\.\']{1,60}?)\s+with\s+(?:easypaisa|jazzcash|account)',
        # "sent to NAME with"
        r'sent\s+to\s+([A-Za-z][A-Za-z\s\.\']{1,60}?)\s+with\s+(?:easypaisa|jazzcash|account)',
        # Fallback: "from/to NAME ... Easypaisa"
        r'(?:from|to)\s+([A-Za-z][A-Za-z\s\.\']{1,60}?)\s+(?:easypaisa|jazzcash)',
    ]
    for pattern in name_patterns:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            # Clean up trailing whitespace/special chars
            name = re.sub(r'\s+', ' ', name).strip()
            if 2 <= len(name) <= 60:
                break
            name = None

    info = {}
    if amount_match:
        try:
            info['amount'] = float(amount_match.group(1).replace(',', ''))
        except ValueError:
            pass
    if tid_match:
        info['tid'] = tid_match.group(1).strip()
    if name:
        info['name'] = name
    info['type'] = 'received' if is_received else ('sent' if is_sent else 'unknown')
    info['subject'] = subject
    info['body_preview'] = body[:200]

    return info if (info.get('amount') and info.get('tid')) else None


# ════════════════════════════════════════════
# ✅ VERIFY BY TRX ID ONLY (Simpler!)
# ════════════════════════════════════════════
def verify_by_tid_only(tid):
    """🆕 v31: Verify ONLY by TRX ID. Bot extracts everything else from email.

    Args:
        tid: Transaction ID (11 digits)

    Returns dict:
        {
          'success': bool,
          'status': 'matched' | 'duplicate' | 'tid_not_found' | 'imap_error' | 'no_emails',
          'reason': str,
          'amount': float,
          'name': str,
          'type': str ('received' / 'sent'),
        }
    """
    result = {
        'success': False, 'status': '', 'reason': '',
        'amount': 0, 'name': '', 'type': '',
    }

    tid = (tid or "").strip()
    if not tid:
        result['status'] = 'invalid_tid'
        result['reason'] = "TID is empty"
        return result

    # Allow 10-13 digit TIDs
    if not re.fullmatch(r'\d{10,13}', tid):
        result['status'] = 'invalid_tid'
        result['reason'] = "TID must be 10-13 digits"
        return result

    # Anti-fraud: Already used?
    try:
        from database import is_txid_used, get_txid_record
        if is_txid_used(tid):
            rec = get_txid_record(tid)
            result['status'] = 'duplicate'
            result['reason'] = "This TID has already been used"
            if rec:
                result['reason'] += f" (used at {rec['verified_at'][:16]})"
            return result
    except Exception as e:
        logger.warning(f"DB check error: {e}")

    # Connect Gmail (backend — user never sees this)
    mail = connect_imap()
    if not mail:
        result['status'] = 'imap_error'
        result['reason'] = ("Payment verification service temporarily unavailable. "
                            "Please try again in 2 minutes.")
        return result

    try:
        mail.select("INBOX")
        # Search for SMSForwarder OR easypaisa subject
        all_ids = set()
        for query in [
            '(SUBJECT "SMSForwarder")',
            '(SUBJECT "easypaisa")',
            '(SUBJECT "Easypaisa")',
        ]:
            try:
                status, data = mail.search(None, query)
                if status == "OK" and data[0]:
                    all_ids.update(data[0].split())
            except: continue

        if not all_ids:
            try: mail.logout()
            except: pass
            result['status'] = 'no_emails'
            result['reason'] = ("Your payment notification has not arrived yet. "
                                "Please try again in 2 minutes.")
            return result

        # Check most recent 50 emails
        email_ids = sorted(all_ids)[-50:][::-1]
        matched_email = None
        for eid in email_ids:
            try:
                status, fetch = mail.fetch(eid, "(RFC822)")
                if status != "OK": continue
                msg = email.message_from_bytes(fetch[0][1])
                info = extract_payment_info(msg)
                if info and info.get('tid') == tid:
                    matched_email = info
                    break
            except Exception as e:
                logger.warning(f"Email parse error: {e}")
                continue

        try: mail.logout()
        except: pass

        if not matched_email:
            result['status'] = 'tid_not_found'
            result['reason'] = (
                "We couldn't find your payment yet. "
                "It may take a few minutes to process. "
                "Please try again in 2 minutes.\n\n"
                "If the issue persists:\n"
                "• Double-check the Transaction ID is correct\n"
                "• Make sure payment was sent to the correct account"
            )
            return result

        # ── SUCCESS ──
        result['success'] = True
        result['status'] = 'matched'
        result['reason'] = "Payment found in email"
        result['amount'] = matched_email.get('amount', 0)
        result['name'] = matched_email.get('name', '')
        result['type'] = matched_email.get('type', 'unknown')
        return result

    except Exception as e:
        logger.error(f"IMAP error: {e}")
        try: mail.logout()
        except: pass
        result['status'] = 'imap_error'
        result['reason'] = ("Payment verification service temporarily unavailable. "
                            "Please try again in 2 minutes.")
        return result


# ============================================================
# 📄 ORIGINAL FILE: jazzcash_api.py
# ============================================================

# ============================================
# 📧 JAZZCASH AUTO-VERIFY via Gmail IMAP
# ============================================
# User sends only TRX ID → bot fetches Gmail → extracts amount + name automatically.
#
# Supported SMS formats (JazzCash):
#   "Trx ID 1234567890123  Amount Rs.500.00 ... from MUHAMMAD ALI ..."
#   "TID: 1234567890  Rs.300 received from John Doe"
#   "You have received Rs.500 from AYESHA. TID: 1234567890123"
#
# Same Gmail credentials as EasyPaisa — uses .env EMAIL_ADDRESS / EMAIL_PASSWORD.

import os
import re
import imaplib
import email
from email.header import decode_header
import logging

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════
# 🔐 LOAD CREDENTIALS (.env) — shared with EasyPaisa
# ════════════════════════════════════════════
EMAIL_ADDRESS = None
EMAIL_PASSWORD = None
try:
    from dotenv import load_dotenv
    load_dotenv()
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
except ImportError:
    pass

if not EMAIL_ADDRESS:
    try:
        from config import EMAIL_ADDRESS as _ea, EMAIL_PASSWORD as _ep
        EMAIL_ADDRESS = _ea
        EMAIL_PASSWORD = _ep
    except Exception:
        pass


# ════════════════════════════════════════════
# 🔌 IMAP CONNECTION
# ════════════════════════════════════════════
def connect_imap():
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        logger.error("EMAIL_ADDRESS/PASSWORD not set in .env")
        return None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        return mail
    except Exception as e:
        logger.error(f"Gmail IMAP connect failed: {e}")
        return None


def is_configured():
    return bool(EMAIL_ADDRESS and EMAIL_PASSWORD)


def test_connection():
    if not is_configured():
        return False, "Email credentials not configured."
    mail = connect_imap()
    if not mail:
        return False, "Failed to connect to email server."
    try:
        mail.select("INBOX")
        try: mail.logout()
        except: pass
        return True, f"✅ Connected: {EMAIL_ADDRESS}"
    except Exception as e:
        try: mail.logout()
        except: pass
        return False, f"Connection error: {e}"


# ════════════════════════════════════════════
# 🔍 EMAIL PARSING
# ════════════════════════════════════════════
def _decode_subject(raw_subject):
    if not raw_subject: return ""
    out = ""
    for part, charset in decode_header(raw_subject):
        if isinstance(part, bytes):
            try: out += part.decode(charset or "utf-8", errors="ignore")
            except: out += part.decode("utf-8", errors="ignore")
        else:
            out += str(part)
    return out


def _get_email_body(msg):
    """v61: strip <script>/<style>/<!-- --> before tags to avoid CSS leakage."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode("utf-8", errors="ignore")
                except: continue
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            html = payload.decode("utf-8", errors="ignore")
                            html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL|re.IGNORECASE)
                            html = re.sub(r'<style[^>]*>.*?</style>',   ' ', html, flags=re.DOTALL|re.IGNORECASE)
                            html = re.sub(r'<!--.*?-->',                ' ', html, flags=re.DOTALL)
                            html = re.sub(r'<head[^>]*>.*?</head>',     ' ', html, flags=re.DOTALL|re.IGNORECASE)
                            html = re.sub(r'<[^>]+>', ' ', html)
                            html = html.replace('&nbsp;', ' ').replace('&amp;', '&')
                            html = html.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
                            html = re.sub(r'&#x?[\da-fA-F]+;', ' ', html)
                            html = re.sub(r'&[a-zA-Z]+;', ' ', html)
                            html = re.sub(r'\s+', ' ', html)
                            body += html
                    except: continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="ignore")
        except: pass
    return body


def extract_payment_info(msg):
    """Parse SMSForwarder-JazzCash email — FLEXIBLE regex.

    Returns dict {amount, tid, name, type} or None if not matching.
    """
    # Subject must mention JazzCash or SMSForwarder (case-insensitive)
    subject = _decode_subject(msg.get("Subject", "")).lower()
    body = _get_email_body(msg)

    # Filter: must be JazzCash-related (either subject or body)
    is_jazzcash = ("jazzcash" in subject or "jazz cash" in subject
                   or "jazzcash" in (body or "").lower()
                   or "jazz cash" in (body or "").lower())
    if not is_jazzcash and "smsforwarder" not in subject:
        return None
    if not is_jazzcash:
        # SMSForwarder generic subject — make sure body is jazzcash
        if "jazzcash" not in (body or "").lower() and "jazz cash" not in (body or "").lower():
            return None

    if not body:
        return None

    # Amount: "Rs.500", "Rs 500.00", "Rs. 500", "PKR 500", "Amount: Rs.500"
    amount_match = re.search(
        r'(?:Rs\.?|PKR|Amount\s*[:\-]?\s*Rs\.?)\s*([\d,]+\.?\d*)',
        body, re.IGNORECASE
    )

    # TRX ID — JazzCash formats:
    #   "Trx ID 1234567890"
    #   "TID: 1234567890"
    #   "Transaction ID: 1234567890"
    #   "TrxID 1234567890"
    tid_match = re.search(
        r'(?:Trx\s*ID|TID|Transaction\s*ID|TrxID|Txn\s*ID)\s*[:#\.]?\s*(\d{10,15})',
        body, re.IGNORECASE
    )

    # Type detection
    is_received = bool(re.search(
        r'received\s+Rs|have\s+received|credited|deposit',
        body, re.IGNORECASE
    ))
    is_sent = bool(re.search(
        r'sent\s+to|debited|paid\s+to|transferred\s+to|withdraw',
        body, re.IGNORECASE
    ))

    # Name extraction patterns
    name = None
    name_patterns = [
        # "from NAME with jazzcash/account"
        r'from\s+([A-Za-z][A-Za-z\s\.\']{1,60}?)\s+with\s+(?:jazzcash|jazz\s*cash|account)',
        # "sent to NAME with jazzcash"
        r'sent\s+to\s+([A-Za-z][A-Za-z\s\.\']{1,60}?)\s+with\s+(?:jazzcash|jazz\s*cash|account)',
        # "from NAME. TID" or "from NAME, TID"
        r'(?:received|from)\s+(?:Rs\.?\s*[\d,\.]+\s+)?from\s+([A-Za-z][A-Za-z\s\.\']{1,60}?)[\.,]',
        # "Sender Name: NAME" / "Sender: NAME"
        r'(?:Sender\s*Name|Sender|From\s*Name)\s*[:\-]\s*([A-Za-z][A-Za-z\s\.\']{1,60}?)(?:[\n\r]|$|TID|Trx)',
        # Generic "from NAME" before a number/separator
        r'from\s+([A-Z][A-Z\s]{2,60})(?:\s+(?:TID|Trx|Account|with|JazzCash))',
    ]
    for pattern in name_patterns:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            name = re.sub(r'\s+', ' ', name).strip()
            # Clean up trailing words like "JazzCash", "Account"
            name = re.sub(r'\s+(?:jazzcash|account|with|tid|trx).*$', '', name, flags=re.IGNORECASE).strip()
            if 2 <= len(name) <= 60:
                break
            name = None

    info = {}
    if amount_match:
        try:
            info['amount'] = float(amount_match.group(1).replace(',', ''))
        except ValueError:
            pass
    if tid_match:
        info['tid'] = tid_match.group(1).strip()
    if name:
        info['name'] = name
    info['type'] = 'received' if is_received else ('sent' if is_sent else 'unknown')
    info['subject'] = subject
    info['body_preview'] = body[:200]

    return info if (info.get('amount') and info.get('tid')) else None


# ════════════════════════════════════════════
# ✅ VERIFY BY TRX ID ONLY
# ════════════════════════════════════════════
def verify_by_tid_only(tid):
    """Verify ONLY by TRX ID. Bot extracts amount + name from email.

    Args:
        tid: Transaction ID (10-15 digits — JazzCash uses 10-13 typically)

    Returns dict:
        {
          'success': bool,
          'status': 'matched' | 'duplicate' | 'tid_not_found' | 'imap_error' | 'no_emails' | 'invalid_tid',
          'reason': str,
          'amount': float,
          'name': str,
          'type': str ('received' / 'sent'),
        }
    """
    result = {
        'success': False, 'status': '', 'reason': '',
        'amount': 0, 'name': '', 'type': '',
    }

    tid = (tid or "").strip()
    if not tid:
        result['status'] = 'invalid_tid'
        result['reason'] = "Transaction ID is empty."
        return result

    # Accept 10-15 digit TIDs (JazzCash varies)
    if not re.fullmatch(r'\d{10,15}', tid):
        result['status'] = 'invalid_tid'
        result['reason'] = "Transaction ID must be 10-15 digits."
        return result

    # Anti-fraud: Already used?
    try:
        from database import is_txid_used, get_txid_record
        if is_txid_used(tid):
            rec = get_txid_record(tid)
            result['status'] = 'duplicate'
            result['reason'] = "This Transaction ID has already been used."
            if rec:
                result['reason'] += f" (used at {rec['verified_at'][:16]})"
            return result
    except Exception as e:
        logger.warning(f"DB check error: {e}")

    # Connect Gmail
    mail = connect_imap()
    if not mail:
        result['status'] = 'imap_error'
        result['reason'] = "Payment verification service temporarily unavailable. Please try again in 2 minutes."
        return result

    try:
        mail.select("INBOX")
        # Search across multiple subjects
        all_ids = set()
        for query in [
            '(SUBJECT "SMSForwarder")',
            '(SUBJECT "JazzCash")',
            '(SUBJECT "jazzcash")',
            '(SUBJECT "Jazz Cash")',
        ]:
            try:
                status, data = mail.search(None, query)
                if status == "OK" and data[0]:
                    all_ids.update(data[0].split())
            except: continue

        if not all_ids:
            try: mail.logout()
            except: pass
            result['status'] = 'no_emails'
            result['reason'] = ("Your payment notification has not arrived yet. "
                                "Please try again in 2 minutes.")
            return result

        # Check most recent 50 emails
        email_ids = sorted(all_ids)[-50:][::-1]
        matched_email = None
        for eid in email_ids:
            try:
                status, fetch = mail.fetch(eid, "(RFC822)")
                if status != "OK": continue
                msg = email.message_from_bytes(fetch[0][1])
                info = extract_payment_info(msg)
                if info and info.get('tid') == tid:
                    matched_email = info
                    break
            except Exception as e:
                logger.warning(f"Email parse error: {e}")
                continue

        try: mail.logout()
        except: pass

        if not matched_email:
            result['status'] = 'tid_not_found'
            result['reason'] = (
                "We couldn't find your payment yet. "
                "It may take a few minutes to process. "
                "Please try again in 2 minutes.\n\n"
                "If the issue persists:\n"
                "• Double-check the Transaction ID is correct\n"
                "• Make sure payment was sent to the correct account"
            )
            return result

        # ── SUCCESS ──
        result['success'] = True
        result['status'] = 'matched'
        result['reason'] = "Payment verified successfully."
        result['amount'] = matched_email.get('amount', 0)
        result['name'] = matched_email.get('name', '')
        result['type'] = matched_email.get('type', 'unknown')
        return result

    except Exception as e:
        logger.error(f"IMAP error: {e}")
        try: mail.logout()
        except: pass
        result['status'] = 'imap_error'
        result['reason'] = "Payment verification service temporarily unavailable. Please try again in 2 minutes."
        return result


# ============================================================
# 📄 ORIGINAL FILE: screenshot_verifier.py
# ============================================================

# ============================================
# 📸 SCREENSHOT-BASED PAYMENT VERIFIER (v35)
# ============================================
# Uses Google Gemini Vision API to:
#   1. Read Binance/JazzCash payment screenshots
#   2. Extract amount, Transaction ID, receiver name
#   3. Detect if real (not fake/edited)
#   4. Detect if payment was SUCCESSFUL
#
# v35: Improved JazzCash/Easypaisa prompt
#      + Image preprocessing + Retry logic
#      + Support for Arena AI (OpenAI-compatible)

import os
import json
import logging
import re
import io

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════
# 🔐 LOAD API KEY (Gemini — primary)
# ════════════════════════════════════════════
GEMINI_API_KEY = None
try:
    from dotenv import load_dotenv
    load_dotenv()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
except ImportError:
    pass

if not GEMINI_API_KEY:
    try:
        from config import GEMINI_API_KEY as _key
        GEMINI_API_KEY = _key
    except Exception:
        pass

# ════════════════════════════════════════════
# 🔐 ARENA AI (OpenAI-compatible — secondary)
# ════════════════════════════════════════════
# Optional: If set, used as FALLBACK when Gemini fails
ARENA_API_KEY = os.getenv("ARENA_API_KEY", "")
ARENA_API_URL = os.getenv("ARENA_API_URL", "https://api.openai.com/v1/chat/completions")
ARENA_MODEL = os.getenv("ARENA_MODEL", "gpt-4o-mini")


# ════════════════════════════════════════════
# 🖼️ IMAGE PREPROCESSING
# ════════════════════════════════════════════
def _preprocess_image(image_bytes, max_size=1024*1024):
    """Resize image if too large for API. Returns processed bytes."""
    if not image_bytes or len(image_bytes) <= max_size:
        return image_bytes
    
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convert RGBA to RGB if needed
        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize while maintaining aspect ratio
        max_dimension = 1600
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        
        # Save as JPEG with compression
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85)
        return output.getvalue()
    except ImportError:
        # PIL not available — return as-is
        return image_bytes
    except Exception as e:
        logger.warning(f"Image preprocessing failed: {e}")
        return image_bytes


# ════════════════════════════════════════════
# 🧠 GEMINI VISION CLIENT
# ════════════════════════════════════════════
_model = None
_init_error = None


def _get_model():
    """Lazy init Gemini Vision model"""
    global _model, _init_error
    if _model is not None or _init_error is not None:
        return _model
    try:
        import google.generativeai as genai
        if not GEMINI_API_KEY:
            _init_error = "GEMINI_API_KEY not set in .env"
            return None
        genai.configure(api_key=GEMINI_API_KEY)
        _model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config={
                "temperature": 0.1,
                "top_p": 0.9,
                "max_output_tokens": 800,
            },
        )
        return _model
    except ImportError:
        _init_error = "google-generativeai not installed. Run: pip install google-generativeai"
        return None
    except Exception as e:
        _init_error = f"Init error: {e}"
        return None


def is_configured():
    _get_model()
    return _model is not None and _init_error is None

def get_init_error():
    return _init_error


# ════════════════════════════════════════════
# 📋 EXTRACTION PROMPTS (Platform-specific)
# ════════════════════════════════════════════
def _build_prompt(expected_amount=None, expected_receiver=None, expected_pay_id=None, platform="Binance"):
    """Build AI prompt for payment screenshot analysis."""

    if platform.lower() in ("jazzcash", "easypaisa", "jazz", "easy"):
        # 🔧 v35: MUCH more detailed JazzCash/Easypaisa prompt
        p = """You are a payment screenshot verification expert. Analyze this mobile wallet payment screenshot carefully.

IMPORTANT CONTEXT: This is a Pakistani mobile wallet app (JazzCash or Easypaisa). These apps have specific UI designs that are different from international payment apps. The screenshot may be in English or Urdu/Roman Urdu.

Return ONLY this JSON object (no other text, no markdown, no explanation):

{"is_payment_screenshot": true, "is_successful": true, "is_likely_fake": false, "amount": 0, "currency": "PKR", "order_id": "", "receiver_name": "", "receiver_pay_id": "", "sender_name": "", "platform": "JazzCash", "notes": ""}

DETAILED RULES:

1. is_payment_screenshot:
   - TRUE if screenshot shows: JazzCash app, Easypaisa app, money transfer, payment receipt, transaction confirmation
   - TRUE if you see: "Transferred to", "Sent to", "Payment Successful", green checkmark, transaction details
   - FALSE only if it's clearly not a payment screen (random photo, chat, game, etc.)

2. is_successful:
   - TRUE if you see ANY of these:
     * Green checkmark / green tick
     * "Successful" / "Transferred Successfully" / "Sent Successfully"
     * "Payment Successful" / "Transaction Complete"
     * "Securely Paid" / "Money Sent"
     * A receipt with transaction ID
     * "Transferred to JazzCash" / "Transferred to Easypaisa"
     * Any confirmation with amount and recipient
   - FALSE if: "Failed", "Pending", "Cancelled", or clearly shows an error

3. is_likely_fake:
   - ONLY true if OBVIOUSLY edited (mismatched fonts, blurred areas over text, screenshot of a screenshot with edits)
   - DEFAULT: false — most screenshots are genuine
   - Don't mark as fake just because quality is low or blurry

4. amount:
   - Extract the PKR/Rupee amount. Just the NUMBER, no currency symbol.
   - Look for patterns like: "Rs. 600", "PKR 600", "₨ 600", "600.00"
   - Look for: "Amount: 600", "You sent Rs 600"
   - If you see both sent and received amounts, use the TRANSFER amount (not balance)

5. order_id / Transaction ID:
   - Look for: "Transaction ID", "Trx ID", "TID", "Reference No", "Ref #", "RRN"
   - Usually 10-15 digit number
   - May appear near top or bottom of screenshot
   - If you can't find any ID, use empty string ""

6. receiver_name:
   - The person RECEIVING the money (the "To" field)
   - Look for: "To:", "Sent to:", "Beneficiary:", "Receiver:"
   - Example: "Zayam Iqbal", "Ziam Iqbal"

7. receiver_pay_id:
   - The mobile number of the receiver
   - Look for: 11-digit number starting with 03xx or 92xx
   - Examples: "03193840214", "923193840214"

8. sender_name:
   - The person SENDING money (the "From" field)
   - May not always be shown

CRITICAL INSTRUCTIONS:
- Return ONLY the JSON object
- No markdown formatting (no ```json```)
- No explanation before or after
- If unsure about a field, use empty string "" rather than guessing
- Amount must be a NUMBER (no "Rs." prefix)
- Be generous with is_payment_screenshot — if it looks like a mobile payment screen, it probably is"""

    else:
        # Default: Binance Pay (improved)
        p = """Analyze this Binance Pay payment screenshot. Return ONLY this JSON (no other text):

{"is_payment_screenshot": true, "is_successful": true, "is_likely_fake": false, "amount": 0, "currency": "USDT", "order_id": "", "receiver_name": "", "receiver_pay_id": "", "sender_name": "", "platform": "Binance Pay", "notes": ""}

Rules:
- is_payment_screenshot: true if it's a Binance Pay screenshot. false if random photo.
- is_successful: true if shows "Payment Successful", "Successful", green checkmark.
- is_likely_fake: true ONLY if clearly edited/fake. Default false.
- amount: USD/USDT number paid (e.g. 10 not "$10").
- currency: USDT, USD, BUSD, BTC, etc.
- order_id: The "Order ID" or "Transaction ID" number (15-25 digits). Empty string if missing.
- receiver_name: The "To" / "Nickname" field.
- receiver_pay_id: Binance Pay ID number (8-10 digits) under receiver.

CRITICAL: Return ONLY the JSON object. No explanations, no markdown, no extra text."""

    if expected_amount:
        p += f"\n\nThe payment SHOULD be: {expected_amount} (verify this matches)"
    if expected_receiver:
        p += f"\nThe receiver SHOULD be named: '{expected_receiver}' (verify this matches)"
    if expected_pay_id:
        p += f"\nThe receiver Pay ID/Number SHOULD be: {expected_pay_id} (verify this matches)"

    p += "\n\nReturn ONLY the JSON object. No other text."
    return p


# ════════════════════════════════════════════
# 🔍 PARSE AI RESPONSE (Robust)
# ════════════════════════════════════════════
def _parse_ai_response(text):
    """🔧 v35 ROBUST parser — extract JSON from any AI response format"""
    if not text:
        return None
    text = text.strip()

    # Remove markdown code blocks
    text = re.sub(r'```(?:json|JSON)?\s*', '', text)
    text = re.sub(r'```', '', text)
    text = text.strip()

    # Strategy 1: Try parsing whole text as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Find outermost JSON object
    start = text.find('{')
    if start == -1:
        logger.error(f"No JSON object found in response: {text[:300]}")
        return None

    # Find matching closing brace
    depth = 0
    in_string = False
    escape_next = False
    end = -1
    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        end = text.rfind('}')
        if end == -1 or end < start:
            logger.error(f"No closing brace: {text[:300]}")
            return None

    json_str = text[start:end+1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Clean common issues
        cleaned = re.sub(r',\s*}', '}', json_str)
        cleaned = re.sub(r',\s*\]', ']', cleaned)
        cleaned = re.sub(r"(\w+)\s*:\s*'([^']*)'", r'"\1": "\2"', cleaned)
        try:
            return json.loads(cleaned)
        except:
            pass
        logger.error(f"JSON parse failed: {json_str[:500]}")
        return None


# ════════════════════════════════════════════
# 🛡️ NAME MATCH (fuzzy)
# ════════════════════════════════════════════
def _names_match(expected, actual):
    """Check if names match (case-insensitive, allows partial)"""
    if not expected or not actual:
        return True
    a = re.sub(r'\s+', ' ', str(expected).lower().strip())
    b = re.sub(r'\s+', ' ', str(actual).lower().strip())
    if a == b:
        return True
    a_words = set(w for w in a.split() if len(w) >= 3)
    b_words = set(w for w in b.split() if len(w) >= 3)
    if a_words and b_words and (a_words & b_words):
        return True
    if a in b or b in a:
        return True
    return False


# ════════════════════════════════════════════
# 🤖 ARENA AI FALLBACK (OpenAI-compatible API)
# ════════════════════════════════════════════
def _verify_with_arena_ai(image_bytes, prompt):
    """Use Arena AI (or any OpenAI-compatible API) as fallback for screenshot verification.
    Returns parsed JSON dict or None.
    """
    if not ARENA_API_KEY:
        return None
    
    try:
        import requests
        import base64
        
        b64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        payload = {
            "model": ARENA_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 800,
            "temperature": 0.1
        }
        
        headers = {
            "Authorization": f"Bearer {ARENA_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(ARENA_API_URL, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            text = data['choices'][0]['message']['content']
            return _parse_ai_response(text)
        else:
            logger.error(f"Arena AI error: {response.status_code} {response.text[:200]}")
            return None
    except ImportError:
        logger.warning("requests library not installed for Arena AI fallback")
        return None
    except Exception as e:
        logger.error(f"Arena AI fallback error: {e}")
        return None


# ════════════════════════════════════════════
# ✅ MAIN VERIFY FUNCTION
# ════════════════════════════════════════════
def verify_payment_screenshot(image_bytes, expected_amount=None,
                              expected_receiver=None, expected_pay_id=None,
                              amount_tolerance=0.02, platform="Binance"):
    """Verify a payment screenshot using AI.

    Args:
        platform: "Binance", "JazzCash", or "Easypaisa"
        image_bytes: Raw bytes of the screenshot image
        expected_amount: Expected amount (optional but recommended)
        expected_receiver: Admin's receiver name
        expected_pay_id: Admin's Pay ID / mobile number
        amount_tolerance: Tolerance for amount match

    Returns dict with: success, status, reason, amount, order_id, currency, extracted
    """
    result = {
        'success': False,
        'status': '',
        'reason': '',
        'amount': 0,
        'order_id': '',
        'currency': '',
        'extracted': None,
    }

    if not image_bytes:
        result['status'] = 'api_error'
        result['reason'] = "No image provided"
        return result

    # Preprocess image (resize if too large)
    processed_bytes = _preprocess_image(image_bytes)

    # Build prompt
    prompt = _build_prompt(expected_amount, expected_receiver, expected_pay_id, platform=platform)

    # ── Try Gemini Vision first ──
    model = _get_model()
    extracted = None
    
    if model:
        try:
            image_part = {
                "mime_type": "image/jpeg",
                "data": processed_bytes
            }
            response = model.generate_content([prompt, image_part])
            if response and getattr(response, 'text', None):
                extracted = _parse_ai_response(response.text)
                if not extracted:
                    logger.error(f"Gemini response couldn't be parsed: {response.text[:500]}")
        except Exception as e:
            err = str(e).lower()
            if 'quota' in err or 'rate' in err:
                logger.warning(f"Gemini quota error, trying fallback: {e}")
            elif 'safety' in err or 'blocked' in err:
                result['status'] = 'api_error'
                result['reason'] = "AI blocked this image (safety filter). Try a different screenshot."
                return result
            else:
                logger.error(f"Gemini error: {e}")

    # ── Try Arena AI as fallback ──
    if not extracted:
        logger.info("Trying Arena AI fallback...")
        extracted = _verify_with_arena_ai(processed_bytes, prompt)

    # ── If both failed ──
    if not extracted:
        if not model and not ARENA_API_KEY:
            result['status'] = 'api_error'
            result['reason'] = (
                f"AI not configured: {_init_error}\n"
                f"Check GEMINI_API_KEY in .env file."
            )
        else:
            result['status'] = 'api_error'
            result['reason'] = (
                "AI couldn't read screenshot details.\n"
                "Make sure:\n"
                "• Screenshot is clear (not blurry)\n"
                "• Shows 'Successful' / 'Sent' / 'Transferred' page\n"
                "• Amount and Transaction ID are visible\n"
                "Try uploading again."
            )
        return result

    result['extracted'] = extracted

    # ── VALIDATE EXTRACTED DATA ──

    # 1. Is it a payment screenshot?
    if not extracted.get('is_payment_screenshot'):
        result['status'] = 'not_a_screenshot'
        result['reason'] = f"Not a payment screenshot. Please upload a valid {'JazzCash' if platform.lower() in ('jazzcash','jazz') else 'Binance'} screenshot."
        return result

    # 2. Is the payment successful?
    if not extracted.get('is_successful'):
        result['status'] = 'not_successful'
        result['reason'] = (
            "Screenshot does NOT show a successful payment.\n"
            "Make sure you upload the screenshot AFTER the payment is complete."
        )
        return result

    # 3. Fake detection
    if extracted.get('is_likely_fake'):
        result['status'] = 'fake_detected'
        notes = extracted.get('notes', '')
        result['reason'] = f"Suspicious screenshot detected. {notes}"
        return result

    # 4. Transaction ID
    order_id = str(extracted.get('order_id', '') or '').strip()
    # Also check for 'transaction_id' field (some AI responses use this)
    if not order_id or order_id.lower() in ('null', 'none', ''):
        order_id = str(extracted.get('transaction_id', '') or '').strip()
    
    if not order_id or order_id.lower() in ('null', 'none', ''):
        # 🔧 BUG FIX #5: Don't generate fake TIDs anymore.
        # Previously, JC-{timestamp} was generated and stored in used_txids,
        # polluting the anti-fraud table with meaningless entries.
        # Now: require a real TID for all platforms.
        result['status'] = 'no_order_id'
        result['reason'] = "Could not read Transaction ID from screenshot. Upload a clearer image."
        return result

    result['order_id'] = order_id

    # 5. Anti-fraud: Order ID not used before
    try:
        from database import is_txid_used, get_txid_record
        if is_txid_used(order_id):
            rec = get_txid_record(order_id)
            result['status'] = 'duplicate'
            result['reason'] = "This screenshot's Transaction ID has ALREADY been used!"
            if rec:
                result['reason'] += f"\n_Used at: {rec['verified_at'][:16]}_"
            return result
    except Exception as e:
        logger.warning(f"DB check error: {e}")

    # 6. Extract amount + currency
    try:
        actual_amount = float(extracted.get('amount', 0) or 0)
    except (ValueError, TypeError):
        actual_amount = 0
    currency = extracted.get('currency', 'PKR' if platform.lower() in ('jazzcash','easypaisa','jazz','easy') else 'USDT')
    result['amount'] = actual_amount
    result['currency'] = currency

    # 7. Amount check (with tolerance)
    if expected_amount is not None and actual_amount > 0:
        try:
            expected = float(expected_amount)
        except (ValueError, TypeError):
            expected = 0
        if abs(actual_amount - expected) > amount_tolerance:
            result['status'] = 'amount_mismatch'
            result['reason'] = (
                f"Amount mismatch!\n"
                f"Expected: {expected:.2f}\n"
                f"Screenshot shows: {actual_amount:.2f} {currency}"
            )
            return result

    # 8. Receiver name/ID check
    actual_receiver = extracted.get('receiver_name', '') or ''
    actual_pay_id = str(extracted.get('receiver_pay_id', '') or '').strip()

    if expected_pay_id:
        clean_expected = re.sub(r'\D', '', str(expected_pay_id))
        clean_actual = re.sub(r'\D', '', actual_pay_id)
        if clean_expected and clean_actual and clean_expected != clean_actual:
            # For mobile numbers, check last 10 digits (with/without country code)
            if clean_expected[-10:] != clean_actual[-10:]:
                result['status'] = 'name_mismatch'
                result['reason'] = (
                    f"Payment was sent to WRONG number!\n"
                    f"Required: {expected_pay_id}\n"
                    f"Screenshot shows: {actual_pay_id}"
                )
                return result

    if expected_receiver and actual_receiver:
        if not _names_match(expected_receiver, actual_receiver):
            result['status'] = 'name_mismatch'
            result['reason'] = (
                f"Receiver name doesn't match!\n"
                f"Expected: {expected_receiver}\n"
                f"Screenshot shows: {actual_receiver}"
            )
            return result

    # ── ALL CHECKS PASSED ──
    result['success'] = True
    result['status'] = 'matched'
    result['reason'] = "Payment verified successfully"
    return result


# ════════════════════════════════════════════
# 🧪 TEST CONNECTION
# ════════════════════════════════════════════
def test_connection():
    """Test if AI is ready"""
    if not is_configured():
        return False, f"Not configured: {_init_error}"
    try:
        model = _get_model()
        response = model.generate_content("Reply with: OK")
        if response and response.text:
            return True, f"✅ Gemini Vision API ready\nModel: gemini-2.5-flash\nResponse: {response.text.strip()[:50]}"
        return False, "Empty response"
    except Exception as e:
        return False, f"Error: {str(e)[:200]}"

