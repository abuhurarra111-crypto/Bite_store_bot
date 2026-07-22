# ============================================================
# 🔗 v86: INSTA API ADAPTER (5th supplier type)
# ============================================================
# Generic instance-based REST API supplier — connection is fed as a
# single base64-encoded string of the form:
#   conn_<base64 of {"k":"<api_key>","u":"<base_url>"}>
#
# Endpoints (auto-detected from live probing):
#   GET  /balance           → {success, balance, user_id}
#   GET  /products          → {success, products:[...]}   (rich schema)
#   GET  /orders            → {success, orders:[...]}
#   POST /purchase          → {product_id, quantity} → account items
#
# Auth: `Authorization: Bearer <api_key>`
# Rate limit: 30 req/min per instance (adapter respects with 2s backoff)
#
# Product schema is RICHER than the other 4 suppliers — provides:
#   name_en / name_ar (bilingual, we use name_en)
#   name_en_html — premium emoji already wrapped in <tg-emoji>
#   custom_emoji_id — direct emoji ID, no extraction needed
#   store_price / your_price / price_locked
#   stock, is_manual
#   discount_tiers — supplier's own bulk discount ladder
#
# Naming: displayed as "🔗 Instant API" in admin panel to keep supplier
# origin private (no branding leak).
# ============================================================

import base64
import json
import logging
# 🆕 v89: removed `import time` — was only used for time.sleep(1.2) which
# we deleted (was blocking the thread pool worker unnecessarily).
import requests

logger = logging.getLogger(__name__)

# Standalone base — same protocol as ext_suppliers.SupplierAdapterBase but
# self-contained so this module has no reverse-import dependency on
# ext_suppliers (which imports us at the end of its module load).
class _StandaloneBase:
    KEY_ID = ""
    LABEL = ""
    DEFAULT_BASE_URL = ""
    DOCS_URL = ""
    AUTH_STYLE = "bearer"

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
        try:
            return requests.get(self.base_url + path,
                                 headers=self._headers(),
                                 params=self._params(), timeout=timeout)
        except Exception as e:
            logger.warning(f"[{self.KEY_ID}] GET {path}: {e}")
            return None

    def _post(self, path, body, timeout=20):
        try:
            return requests.post(self.base_url + path,
                                  headers=self._headers(),
                                  params=self._params(), json=body,
                                  timeout=timeout)
        except Exception as e:
            logger.warning(f"[{self.KEY_ID}] POST {path}: {e}")
            return None


# Backwards-compat alias — some callers may use this name
SupplierAdapterBase = _StandaloneBase


class InstaAPIAdapter(_StandaloneBase):
    """Adapter for the connection-string style supplier."""
    KEY_ID = "insta_api"
    LABEL = "🔗 Instant API"
    DEFAULT_BASE_URL = ""     # per-instance URL, set via wizard
    DOCS_URL = ""             # opaque — no public docs page
    AUTH_STYLE = "bearer"

    # --------------------------------------------------------
    # test_connection — pings /balance + counts /products
    # --------------------------------------------------------
    def test_connection(self):
        r = self._get("/balance")
        if r is None:
            return False, "Network error", {}
        if r.status_code == 401:
            return False, "Invalid API key (401)", {}
        if r.status_code == 429:
            return False, "Rate limited — try again in 60s", {}
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}", {}
        try:
            j = r.json()
        except Exception as e:
            return False, f"Bad response: {e}", {}
        if not j.get("success"):
            return False, j.get("error", "Auth failed"), {}
        bal = float(j.get("balance", 0) or 0)
        user_id = j.get("user_id", "")

        # Product count — separate call; may hit rate limit if called back-to-back
        # 🆕 v89: removed time.sleep(1.2) — was blocking the thread pool worker
        # even though we're in to_thread. If we get a 429 here we just skip
        # the count (test still succeeds — balance alone is enough proof).
        count = 0
        try:
            r2 = self._get("/products")
            if r2 and r2.status_code == 200:
                j2 = r2.json()
                if j2.get("success"):
                    count = len(j2.get("products", []))
            elif r2 and r2.status_code == 429:
                logger.debug("[insta_api] test_connection: 429 on /products — skip count")
        except Exception:
            pass

        # Deliberately generic message — hides supplier branding
        msg = f"Connected. Balance ${bal:.2f}, {count} products."
        return True, msg, {"balance": bal, "count": count,
                           "user": str(user_id or "")}

    # --------------------------------------------------------
    def fetch_balance(self):
        r = self._get("/balance")
        if r and r.status_code == 200:
            try:
                j = r.json()
                if j.get("success"):
                    return float(j.get("balance", 0) or 0)
            except Exception:
                return None
        return None

    # --------------------------------------------------------
    def fetch_products(self):
        r = self._get("/products", timeout=30)
        if not r or r.status_code != 200:
            return []
        try:
            j = r.json()
        except Exception:
            return []
        if not j.get("success"):
            return []
        arr = j.get("products", [])
        out = []
        for p in arr:
            # Prefer your_price (locked custom price), else store_price
            yp = p.get("your_price")
            sp = p.get("store_price")
            try:
                cost = float(yp if (yp is not None and yp != "") else sp or 0)
            except Exception:
                cost = 0.0

            # 🆕 v90 FIX: keep NAME as clean plain text (no HTML wrapping).
            # The premium emoji (if present) is passed via emoji_char + emoji_id
            # in the raw dict. mirror_ext_to_products() will re-wrap the name
            # in [[HTML]]<tg-emoji ...> at the ONE right moment (shop display).
            #
            # v86 bug was: putting "[[HTML]]<tg-emoji ...>✨</tg-emoji> Name"
            # directly into ext_products.name broke every panel that shows the
            # name as raw text (Browse Products list, buttons, admin listings)
            # because those don't parse HTML.
            name_en = (p.get("name_en") or p.get("name_ar") or "").strip()
            # Strip any accidental leading emoji from the name to avoid dupes
            # when we prepend emoji_char below (Telegram premium emojis need
            # the visible char attached to the tg-emoji tag).
            emoji_char = ""
            emoji_id = str(p.get("custom_emoji_id") or "").strip()
            if p.get("has_premium_emoji") and emoji_id:
                # Extract the visible emoji char from the HTML representation
                # provided by the API: "<tg-emoji emoji-id='...'>✨</tg-emoji> Name"
                import re as _re
                html_src = p.get("name_en_html") or p.get("name_ar_html") or ""
                m = _re.search(r'<tg-emoji[^>]*>([^<]+)</tg-emoji>', html_src)
                if m:
                    emoji_char = m.group(1).strip()
                # Fallback: first character of name_en if it looks like emoji
                if not emoji_char and name_en:
                    first_char = name_en[0]
                    # Simple emoji-range check
                    if ord(first_char) > 127:
                        emoji_char = first_char
                        name_en = name_en[1:].lstrip()
            # Build the STORED name: "✨ ChatGPT Go 3 months" (plain)
            if emoji_char and not name_en.startswith(emoji_char):
                display_name = f"{emoji_char} {name_en}"
            else:
                display_name = name_en

            desc_en = p.get("desc_en") or p.get("desc_ar") or ""

            # Handle stock — API may return "unlimited", a string number,
            # or a real int. Treat "unlimited" / negative as 9999.
            raw_stock = p.get("stock", 0)
            try:
                if isinstance(raw_stock, str) and raw_stock.strip().lower() in (
                        "unlimited", "infinite", "∞", "inf"):
                    stock_val = 9999
                else:
                    stock_val = int(float(raw_stock or 0))
                if stock_val < 0:
                    stock_val = 9999
            except Exception:
                stock_val = 0

            out.append({
                "remote_id": str(p.get("id")),
                "name": display_name,          # plain "✨ ChatGPT Go 3 months"
                "description": desc_en,
                "cost_usd": cost,
                "stock": stock_val,
                # 🆕 v90: normalize emoji fields so the sync loop can save
                # them into ext_products.emoji_char / emoji_id columns —
                # mirror_ext_to_products() then reconstructs the [[HTML]]
                # wrapping at the ONE correct moment (shop display).
                "emoji_char": emoji_char,
                "emoji_id":   emoji_id,
                # 🆕 v87: do NOT hardcode unit_label — let v83 3-tier detector
                # fall through to Tier 3 (keyword-based) which correctly
                # identifies CDK / gift-link / coupon products.
                "raw": {
                    **p,
                    "custom_emoji_id": p.get("custom_emoji_id", ""),
                    "has_premium_emoji": bool(p.get("has_premium_emoji")),
                    "emoji_char": emoji_char,
                    "emoji_id": emoji_id,
                },
            })
        return out

    # --------------------------------------------------------
    # create_order — POST /purchase {product_id, quantity}
    # --------------------------------------------------------
    def create_order(self, remote_id, quantity):
        body = {"product_id": str(remote_id), "quantity": int(quantity)}
        r = self._post("/purchase", body, timeout=60)
        if r is None:
            return {"ok": False, "error": "network_error",
                    "items": [], "raw": None}
        try:
            j = r.json()
        except Exception:
            return {"ok": False,
                    "error": f"bad_response_{r.status_code}",
                    "items": [], "raw": (r.text or "")[:500]}

        # Known error codes based on live probing:
        #   400 → product_id required
        #   401 → Invalid API key
        #   402 → Insufficient balance
        #   404 → Product not found
        #   429 → Rate limit exceeded
        if r.status_code == 402:
            return {"ok": False, "error": "insufficient_balance",
                    "items": [], "raw": j}
        if r.status_code == 404:
            return {"ok": False, "error": "product_not_found",
                    "items": [], "raw": j}
        if r.status_code == 429:
            return {"ok": False, "error": "rate_limited",
                    "items": [], "raw": j}
        if r.status_code == 401:
            return {"ok": False, "error": "auth_failed",
                    "items": [], "raw": j}
        if r.status_code >= 400:
            return {"ok": False,
                    "error": j.get("error") or j.get("message") or f"HTTP {r.status_code}",
                    "items": [], "raw": j}

        # Success response shape (inferred from other suppliers + generic
        # patterns — actual shape confirmed on first real purchase and code
        # tolerates all common variants):
        #   {success: true, order_id: "...", accounts: ["..."]}   OR
        #   {success: true, items: [{...}]}                        OR
        #   {success: true, data: "email|pass\nemail|pass"}
        if not (j.get("success") or j.get("ok")):
            return {"ok": False,
                    "error": j.get("error") or j.get("message") or "unknown",
                    "items": [], "raw": j}

        items = _extract_items(j)
        order_id = str(j.get("order_id") or j.get("id") or "")
        return {"ok": True, "items": items,
                "order_id": order_id, "raw": j}


# ============================================================
# Item extraction (handles all common response shapes)
# ============================================================
def _extract_items(j):
    """Pull the actual account-content strings out of a success response."""
    # Preferred keys in order
    for key in ("accounts", "items", "data", "products", "results"):
        v = j.get(key)
        if v is None:
            continue
        if isinstance(v, list):
            out = []
            for it in v:
                if isinstance(it, dict):
                    # Try common shapes
                    for combo in (("email", "password"),
                                  ("username", "password"),
                                  ("user", "pass"),
                                  ("login", "pass")):
                        em = it.get(combo[0]); pw = it.get(combo[1])
                        if em and pw:
                            out.append(f"{em}|{pw}")
                            break
                    else:
                        # Fallbacks
                        for k in ("account", "credentials", "content",
                                 "code", "link", "text"):
                            if it.get(k):
                                out.append(str(it[k])); break
                        else:
                            out.append(json.dumps(it, ensure_ascii=False))
                else:
                    out.append(str(it))
            return out
        if isinstance(v, str):
            # Newline-separated dump
            lines = [ln.strip() for ln in v.split("\n") if ln.strip()]
            return lines
    # Nothing recognised — return the whole thing as one string
    return [json.dumps(j, ensure_ascii=False)]


# ============================================================
# Connection-string parser
# ============================================================
def parse_conn_string(s):
    """
    Parse a `conn_...` string.
    Returns (ok, {"key": ..., "url": ...}) or (False, "error message").
    """
    if not s:
        return False, "empty input"
    s = s.strip()
    if s.lower().startswith("conn_"):
        s = s[5:]
    # Attempt base64 decode (handle url-safe + padding)
    try:
        # Add padding if missing
        padding = "=" * (-len(s) % 4)
        raw = base64.b64decode(s + padding, validate=False)
        j = json.loads(raw.decode("utf-8"))
    except Exception as e:
        # Try urlsafe variant
        try:
            padding = "=" * (-len(s) % 4)
            raw = base64.urlsafe_b64decode(s + padding)
            j = json.loads(raw.decode("utf-8"))
        except Exception:
            return False, f"cannot decode: {e}"
    if not isinstance(j, dict):
        return False, "decoded payload is not an object"
    key = j.get("k") or j.get("key") or j.get("api_key")
    url = j.get("u") or j.get("url") or j.get("base_url")
    if not key:
        return False, "missing 'k' (api key)"
    if not url:
        return False, "missing 'u' (base url)"
    return True, {"key": str(key).strip(), "url": str(url).strip().rstrip("/")}
