# ============================================================
# 🆕 v95: CUSTOM LOCATIONS + CUSTOM RESPONSE CATEGORIES
# ============================================================
# Bug 5 (user reported): "customization mn all settings sync ni hain,
# ma new location b create kro new response b create kro bot auto add
# krdy her zaroori jaga"
#
# What this module provides:
#   1. `get_all_locations()` — returns hardcoded LOCATIONS from
#      customization.py + admin-added custom locations from DB.
#   2. `add_custom_location(id, name, header)` — admin creates new location.
#      Automatically syncs into: Location Customizer, custom_buttons "where
#      to place" picker, and Response Editor category dropdown.
#   3. `get_all_response_categories()` — returns default categories +
#      admin-added ones. Custom categories auto-appear in Response Editor.
#   4. `add_custom_response_category(id, name)` — admin creates new category.
#      Any response key admin adds to it appears in Response Editor.
#
# Storage:
#   bot_settings.custom_locations_json = JSON list of
#     [{"id": "vip", "name": "💎 VIP Zone", "header": "..."}]
#   bot_settings.custom_resp_categories_json = JSON list of
#     [{"id": "promos", "name": "🎯 Promos", "keys": ["promo1", "promo2"]}]
#
# All existing hardcoded LOCATIONS / CATEGORIES stay intact — this only
# EXTENDS them, never replaces.
# ============================================================

import json
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Storage helpers
# ─────────────────────────────────────────────────────────────
_KEY_CUSTOM_LOCS   = "custom_locations_json"
_KEY_CUSTOM_CATS   = "custom_resp_categories_json"


def _load_json(key):
    try:
        from database import get_setting
        raw = get_setting(key, "")
        if not raw:
            return []
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except Exception as e:
        logger.debug(f"[custom_locations] load {key}: {e}")
        return []


def _save_json(key, data):
    try:
        from database import set_setting
        set_setting(key, json.dumps(data, ensure_ascii=False))
        return True
    except Exception as e:
        logger.warning(f"[custom_locations] save {key}: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Public API — locations
# ─────────────────────────────────────────────────────────────
def get_custom_locations():
    """Return admin-added locations as list of dicts."""
    return _load_json(_KEY_CUSTOM_LOCS)


def get_all_locations():
    """Return BOTH hardcoded + custom locations. Deduped by id."""
    try:
        from customization import LOCATIONS as _hardcoded
    except Exception:
        _hardcoded = []
    seen = set()
    out = []
    for loc in list(_hardcoded) + get_custom_locations():
        lid = loc.get("id")
        if lid and lid not in seen:
            seen.add(lid)
            out.append(loc)
    return out


def add_custom_location(loc_id: str, name: str, header: str = "") -> tuple:
    """Add a new custom location. Returns (ok, msg).

    Auto-syncs into:
      • Location Customizer panel
      • custom_buttons location dropdown (via get_all_locations())
      • Any panel that iterates get_all_locations()
    """
    loc_id = (loc_id or "").strip().lower().replace(" ", "_")
    name = (name or "").strip()
    header = header or f"{name}\n━━━━━━━━━━━━━━━━"
    if not loc_id or not name:
        return False, "❌ Location id and name required."
    if not loc_id.replace("_", "").isalnum():
        return False, "❌ id must be alphanumeric (a-z, 0-9, underscores)."
    # Check duplicate with hardcoded first
    try:
        from customization import LOCATIONS as _hardcoded
        if any(l.get("id") == loc_id for l in _hardcoded):
            return False, f"❌ '{loc_id}' is a built-in location (already exists)."
    except Exception:
        pass
    existing = get_custom_locations()
    if any(l.get("id") == loc_id for l in existing):
        return False, f"❌ Custom location '{loc_id}' already exists."
    existing.append({"id": loc_id, "name": name, "default_header": header})
    _save_json(_KEY_CUSTOM_LOCS, existing)
    return True, f"✅ Custom location '{loc_id}' added and now available everywhere."


def delete_custom_location(loc_id: str) -> tuple:
    """Remove a custom location (built-ins can't be deleted)."""
    existing = get_custom_locations()
    filtered = [l for l in existing if l.get("id") != loc_id]
    if len(filtered) == len(existing):
        return False, f"❌ No custom location '{loc_id}' found."
    _save_json(_KEY_CUSTOM_LOCS, filtered)
    return True, f"✅ Custom location '{loc_id}' removed."


# ─────────────────────────────────────────────────────────────
# Public API — response categories
# ─────────────────────────────────────────────────────────────
def get_custom_response_categories():
    return _load_json(_KEY_CUSTOM_CATS)


def add_custom_response_category(cat_id: str, name: str,
                                   response_keys: list = None) -> tuple:
    """Add a new response category with optional response keys."""
    cat_id = (cat_id or "").strip().lower().replace(" ", "_")
    name = (name or "").strip()
    keys = response_keys or []
    if not cat_id or not name:
        return False, "❌ Category id and name required."
    if not cat_id.replace("_", "").isalnum():
        return False, "❌ id must be alphanumeric."
    existing = get_custom_response_categories()
    if any(c.get("id") == cat_id for c in existing):
        return False, f"❌ Category '{cat_id}' already exists."
    existing.append({"id": cat_id, "name": name, "keys": keys})
    _save_json(_KEY_CUSTOM_CATS, existing)
    return True, f"✅ Category '{cat_id}' added — appears in Response Editor."


def delete_custom_response_category(cat_id: str) -> tuple:
    existing = get_custom_response_categories()
    filtered = [c for c in existing if c.get("id") != cat_id]
    if len(filtered) == len(existing):
        return False, f"❌ No custom category '{cat_id}' found."
    _save_json(_KEY_CUSTOM_CATS, filtered)
    return True, f"✅ Category '{cat_id}' removed."


def add_key_to_custom_category(cat_id: str, response_key: str) -> tuple:
    """Add a response key to an existing custom category."""
    existing = get_custom_response_categories()
    for c in existing:
        if c.get("id") == cat_id:
            keys = c.get("keys") or []
            if response_key in keys:
                return False, f"❌ Key '{response_key}' already in '{cat_id}'."
            keys.append(response_key)
            c["keys"] = keys
            _save_json(_KEY_CUSTOM_CATS, existing)
            return True, f"✅ Added '{response_key}' to '{cat_id}'."
    return False, f"❌ Category '{cat_id}' not found."


# ─────────────────────────────────────────────────────────────
# Introspection helpers
# ─────────────────────────────────────────────────────────────
def is_custom_location(loc_id: str) -> bool:
    return any(l.get("id") == loc_id for l in get_custom_locations())


def is_custom_response_category(cat_id: str) -> bool:
    return any(c.get("id") == cat_id for c in get_custom_response_categories())
