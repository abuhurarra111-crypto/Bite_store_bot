# ============================================================
# 🌐 v87: AUTO-TRANSLATOR SYSTEM
# ============================================================
# Admin sets 2 languages:
#   - FROM (source): the language to detect and translate away from
#   - TO   (target): the language to translate into
#
# Actions:
#   1. "🌐 Scan & Translate Full Bot" button → scans EVERY user-facing
#      string field (bot_responses, categories.name/description,
#      products.description, ext_products.description, pinned announcements,
#      DEFAULT_RESPONSES, custom button labels, delivery templates) and if
#      text is in the source language → translates + saves back.
#
#   2. Auto-trigger on product sync (backend, silent):
#      Every time `sync_supplier_products()` runs OR a per-product manual
#      sync happens, each product's DESCRIPTION gets language-detected;
#      if source-language → translated + saved. No confirmation dialog.
#
# 🚫 PRODUCT NAMES ARE NEVER TRANSLATED (per user request — names stay
#     original because they include emoji + brand + SKU codes).
#
# Storage (bot_settings keys, all optional):
#   translator_enabled       "0" / "1"      (default "0" = OFF)
#   translator_from_lang     e.g. "ar", "vi", "id", "auto"
#   translator_to_lang       e.g. "en"      (default "en" if unset)
#   translator_last_scan_at  ISO timestamp
#   translator_cache_<hash>  cached translation for dedup (never re-translate
#                            the same input twice)
#
# Uses:
#   Gemini 2.5 Flash (already used by ai_misc.py) — cheap, fast, quality
#
# Language codes (39 supported by BCP-47 short codes):
#   auto, en, ar, vi, id, ms, hi, ur, es, fr, de, it, pt, ru, ja, zh, ko, tr,
#   nl, pl, uk, cs, sv, no, da, fi, el, he, th, ro, hu, bg, sk, hr, sr, sl, et, lv, lt
#
# Cost: fully additive — no schema changes. Uses existing GEMINI_API_KEY env
# var. Cache prevents re-translation → typically <5 API calls per full scan.
# ============================================================

import hashlib
import json
import logging
import re
import time
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_ID
from database import get_connection, get_setting, set_setting

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# Language registry (BCP-47 short codes + display names)
# ------------------------------------------------------------
LANGUAGES = {
    "auto": "🔍 Auto-detect",
    "en":   "🇬🇧 English",
    "ar":   "🇸🇦 Arabic",
    "vi":   "🇻🇳 Vietnamese",
    "id":   "🇮🇩 Indonesian",
    "ms":   "🇲🇾 Malay",
    "hi":   "🇮🇳 Hindi",
    "ur":   "🇵🇰 Urdu",
    "es":   "🇪🇸 Spanish",
    "fr":   "🇫🇷 French",
    "de":   "🇩🇪 German",
    "it":   "🇮🇹 Italian",
    "pt":   "🇵🇹 Portuguese",
    "ru":   "🇷🇺 Russian",
    "ja":   "🇯🇵 Japanese",
    "zh":   "🇨🇳 Chinese",
    "ko":   "🇰🇷 Korean",
    "tr":   "🇹🇷 Turkish",
    "th":   "🇹🇭 Thai",
    "fa":   "🇮🇷 Persian",
    "he":   "🇮🇱 Hebrew",
    "nl":   "🇳🇱 Dutch",
    "pl":   "🇵🇱 Polish",
    "uk":   "🇺🇦 Ukrainian",
    "el":   "🇬🇷 Greek",
    "ro":   "🇷🇴 Romanian",
    "hu":   "🇭🇺 Hungarian",
    "cs":   "🇨🇿 Czech",
    "sv":   "🇸🇪 Swedish",
    "no":   "🇳🇴 Norwegian",
    "da":   "🇩🇰 Danish",
    "fi":   "🇫🇮 Finnish",
    "bg":   "🇧🇬 Bulgarian",
}

# Fast Unicode-block based language detector — no API call needed
# Returns a BCP-47 language code, or "en" as fallback.
_SCRIPT_HINTS = [
    ("ar", re.compile(r"[\u0600-\u06FF\u0750-\u077F]"), 0.15),  # Arabic
    ("fa", re.compile(r"[\u0600-\u06FF\u067E\u0686\u0698\u06A9\u06AF]"), 0.15),
    ("he", re.compile(r"[\u0590-\u05FF]"), 0.15),                 # Hebrew
    ("ur", re.compile(r"[\u0600-\u06FF\u0679\u067E\u0686\u0688\u0691\u0698\u06A9\u06AF\u06BA\u06BE\u06C1-\u06C3\u06CC\u06D2]"), 0.15),
    ("zh", re.compile(r"[\u4E00-\u9FFF]"), 0.05),                 # Chinese
    ("ja", re.compile(r"[\u3040-\u309F\u30A0-\u30FF]"), 0.05),    # Japanese kana
    ("ko", re.compile(r"[\uAC00-\uD7AF]"), 0.05),                 # Korean
    ("hi", re.compile(r"[\u0900-\u097F]"), 0.10),                 # Devanagari (Hindi)
    ("th", re.compile(r"[\u0E00-\u0E7F]"), 0.10),                 # Thai
    ("el", re.compile(r"[\u0370-\u03FF]"), 0.10),                 # Greek
    ("ru", re.compile(r"[\u0400-\u04FF]"), 0.10),                 # Cyrillic
    ("uk", re.compile(r"[\u0400-\u04FF\u0490\u0491\u0404\u0454\u0406\u0456\u0407\u0457]"), 0.10),
]

# Language-specific keyword hints for scripts that can't be detected via
# Unicode blocks alone (all latin-alphabet languages).
_KEYWORD_HINTS = {
    "vi": re.compile(r"\b(?:tài khoản|mật khẩu|bảo hành|không|và|của|với|cho|một|này|đó|những|các|được|nhật|bản|mật)\b", re.IGNORECASE),
    "id": re.compile(r"\b(?:dan|yang|dengan|untuk|akan|adalah|tidak|garansi|akun|kata sandi|dari|ini|itu|kami|kamu)\b", re.IGNORECASE),
    "ms": re.compile(r"\b(?:dan|yang|dengan|untuk|adalah|tidak|akaun|kata laluan|dari|ini|itu|kami|awak|jaminan)\b", re.IGNORECASE),
    "tr": re.compile(r"\b(?:ve|için|ile|bir|bu|şu|hesap|şifre|garanti|değil|olan|yok|var)\b", re.IGNORECASE),
    "es": re.compile(r"\b(?:cuenta|contraseña|garantía|para|con|una|los|las|del|por|más|pero)\b", re.IGNORECASE),
    "fr": re.compile(r"\b(?:compte|mot de passe|garantie|pour|avec|une|les|des|par|plus|mais)\b", re.IGNORECASE),
    "de": re.compile(r"\b(?:konto|passwort|garantie|für|mit|eine|einen|und|oder|aber|nicht)\b", re.IGNORECASE),
    "it": re.compile(r"\b(?:account|password|garanzia|per|con|una|gli|dei|dal|più|non)\b", re.IGNORECASE),
    "pt": re.compile(r"\b(?:conta|senha|garantia|para|com|uma|dos|pela|mais|não)\b", re.IGNORECASE),
    "pl": re.compile(r"\b(?:konto|hasło|gwarancja|dla|nie|jest|się|oraz|jak)\b", re.IGNORECASE),
    "nl": re.compile(r"\b(?:account|wachtwoord|garantie|voor|niet|met|een|zijn)\b", re.IGNORECASE),
}


def detect_language(text: str) -> str:
    """Fast, offline language detection.

    Uses:
      1. Unicode script blocks for non-latin (Arabic, Chinese, Cyrillic, etc.)
      2. Keyword frequency for latin-script languages (VI, ID, ES, FR, etc.)
      3. Fallback: 'en' for pure ASCII text with no strong signal
    Returns a BCP-47 code.
    """
    if not text or not text.strip():
        return "en"
    text = str(text)
    n = max(1, len(text))

    # Tier 1: Unicode-block detection (script-based, super reliable)
    for lang, pattern, threshold in _SCRIPT_HINTS:
        matches = pattern.findall(text)
        if matches and (len(matches) / n) >= threshold:
            # Ambiguity: Urdu vs Arabic (both use Arabic script). Prefer Urdu
            # only if we see Urdu-specific letters (ں, ے, ٹ, ڈ, ڑ).
            if lang == "ar":
                if re.search(r"[\u0679\u0688\u0691\u06BA\u06D2]", text):
                    return "ur"
                return "ar"
            return lang

    # Tier 2: Latin-script keyword detection
    scores = {}
    for lang, pattern in _KEYWORD_HINTS.items():
        hits = len(pattern.findall(text))
        if hits >= 2:  # need at least 2 keyword hits to declare
            scores[lang] = hits
    if scores:
        return max(scores, key=scores.get)

    # Fallback
    return "en"


# ------------------------------------------------------------
# Settings storage
# ------------------------------------------------------------
def is_translator_enabled() -> bool:
    return str(get_setting("translator_enabled", "0")) == "1"

def set_translator_enabled(on: bool):
    set_setting("translator_enabled", "1" if on else "0")

def get_from_lang() -> str:
    return str(get_setting("translator_from_lang", "auto") or "auto")

def set_from_lang(code: str):
    if code in LANGUAGES:
        set_setting("translator_from_lang", code)

def get_to_lang() -> str:
    return str(get_setting("translator_to_lang", "en") or "en")

def set_to_lang(code: str):
    if code in LANGUAGES and code != "auto":
        set_setting("translator_to_lang", code)


# ------------------------------------------------------------
# Translation cache — never call Gemini twice for the same text
# Cache is stored in bot_settings so it survives restart.
# ------------------------------------------------------------
def _cache_key(text: str, to_lang: str) -> str:
    h = hashlib.md5(f"{to_lang}||{text}".encode("utf-8")).hexdigest()[:24]
    return f"trxl_cache_{h}"

def _cache_get(text: str, to_lang: str):
    key = _cache_key(text, to_lang)
    v = get_setting(key, "")
    return v if v else None

def _cache_put(text: str, to_lang: str, translated: str):
    key = _cache_key(text, to_lang)
    # Cap size at ~4000 chars each (Telegram msg limit-ish)
    if translated and len(translated) < 4000:
        set_setting(key, translated)


# ------------------------------------------------------------
# The actual translator call (uses Gemini 2.5 Flash)
# ------------------------------------------------------------
def _lang_name(code: str) -> str:
    """Return a plain English name for a lang code, for the prompt."""
    return {
        "en": "English", "ar": "Arabic", "vi": "Vietnamese", "id": "Indonesian",
        "ms": "Malay", "hi": "Hindi", "ur": "Urdu", "es": "Spanish",
        "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
        "ru": "Russian", "ja": "Japanese", "zh": "Chinese", "ko": "Korean",
        "tr": "Turkish", "th": "Thai", "fa": "Persian", "he": "Hebrew",
        "nl": "Dutch", "pl": "Polish", "uk": "Ukrainian", "el": "Greek",
        "ro": "Romanian", "hu": "Hungarian", "cs": "Czech", "sv": "Swedish",
        "no": "Norwegian", "da": "Danish", "fi": "Finnish", "bg": "Bulgarian",
    }.get(code, code.upper())


def translate_text(text: str, to_lang: str, from_lang: str = "auto") -> str:
    """
    Translate text using Gemini 2.5 Flash.
    - Returns original text if any error / API missing / text too short.
    - Uses persistent cache so identical inputs never re-hit the API.
    - Preserves <tg-emoji> tags, [[HTML]] sentinels, URLs, and emoji chars
      byte-perfect (instructs the model to do so).
    """
    if not text or not text.strip() or len(text.strip()) < 2:
        return text
    if to_lang not in LANGUAGES or to_lang == "auto":
        return text

    # Cache check
    cached = _cache_get(text, to_lang)
    if cached:
        return cached

    try:
        import google.generativeai as genai
    except Exception as e:
        logger.warning(f"[translator] genai not available: {e}")
        return text
    try:
        from config import GEMINI_API_KEY
    except Exception:
        import os
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    if not GEMINI_API_KEY:
        logger.warning("[translator] GEMINI_API_KEY not set — skip")
        return text

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")

        src = _lang_name(from_lang) if from_lang != "auto" else "the source language"
        dst = _lang_name(to_lang)
        prompt = (
            f"You are a professional translator. Translate the following text "
            f"from {src} to {dst}.\n\n"
            f"STRICT RULES:\n"
            f"1. Preserve ALL HTML tags exactly as-is (e.g. <tg-emoji ...>, "
            f"<b>, <code>) — do NOT translate their content or attributes.\n"
            f"2. Preserve ALL emoji characters (✅ 🚀 ❤️ etc.) exactly as-is.\n"
            f"3. Preserve the literal marker [[HTML]] at the start if present.\n"
            f"4. Preserve URLs, email addresses, and file paths byte-perfect.\n"
            f"5. Preserve line breaks (\\n) and separators like '|' '━'.\n"
            f"6. Do NOT add any commentary, preamble, or explanation.\n"
            f"7. Output ONLY the translated text — nothing else.\n"
            f"8. If a word is a proper noun / brand name (ChatGPT, Netflix, "
            f"Adobe, Canva, etc.), keep it as-is.\n\n"
            f"Text to translate:\n{text}"
        )
        resp = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": max(400, int(len(text) * 2.5)),
            },
        )
        translated = (resp.text or "").strip()
        if not translated:
            return text
        # Strip anything that looks like a wrapping block (some models
        # add ``` ... ``` around the output despite instructions)
        translated = re.sub(r"^```\w*\n?", "", translated).rstrip("`").strip()
        if translated:
            _cache_put(text, to_lang, translated)
            return translated
    except Exception as e:
        logger.warning(f"[translator] Gemini call failed: {e}")
    return text


# ============================================================
# 🆕 v89: BATCH TRANSLATOR — 20x faster full-bot scan
# ============================================================
BATCH_SIZE = 20   # texts per Gemini call

def translate_batch(texts, to_lang, from_lang="auto"):
    """
    Translate a list of texts in ONE Gemini call. Returns a list of
    translated strings (same length + order as input).

    - Automatically skips items that are:
        * empty / whitespace-only
        * < 2 chars
        * already cached (uses cache)
    - Splits into chunks of BATCH_SIZE if the input list is bigger.
    - On any batch failure, falls back to per-item translate_text() for
      that batch so partial results still work.
    - Cache is populated for every successful translation.

    Speed: 1 batch of 20 texts ≈ 1 API call ≈ 2-3 seconds
    vs. 20 individual calls ≈ 40-60 seconds → ~20x speedup.
    """
    if not texts:
        return []
    if to_lang not in LANGUAGES or to_lang == "auto":
        return list(texts)

    # Prepare output slots + figure out which need translation
    out = [None] * len(texts)
    todo = []          # list of (original_index, text)
    for i, t in enumerate(texts):
        if not t or not str(t).strip() or len(str(t).strip()) < 2:
            out[i] = t
            continue
        cached = _cache_get(t, to_lang)
        if cached:
            out[i] = cached
            continue
        todo.append((i, str(t)))

    if not todo:
        return out

    # Lazy-load Gemini
    try:
        import google.generativeai as genai
    except Exception as e:
        logger.warning(f"[batch] genai not available: {e}")
        for i, t in todo:
            out[i] = t
        return out
    try:
        from config import GEMINI_API_KEY
    except Exception:
        import os
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    if not GEMINI_API_KEY:
        logger.warning("[batch] GEMINI_API_KEY not set — falling back to originals")
        for i, t in todo:
            out[i] = t
        return out

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")

    # Process in chunks
    src = _lang_name(from_lang) if from_lang != "auto" else "the source language"
    dst = _lang_name(to_lang)

    for chunk_start in range(0, len(todo), BATCH_SIZE):
        chunk = todo[chunk_start:chunk_start + BATCH_SIZE]
        # Build a JSON array prompt — most reliable format for structured output
        input_json = json.dumps([t for (_, t) in chunk], ensure_ascii=False)
        prompt = (
            f"Translate each string in the following JSON array from {src} to {dst}.\n\n"
            "STRICT RULES:\n"
            "1. Preserve ALL HTML tags exactly as-is (<tg-emoji ...>, <b>, <code>).\n"
            "2. Preserve ALL emoji characters (✅ 🚀 ❤️ etc.).\n"
            "3. Preserve the literal marker [[HTML]] at the start if present.\n"
            "4. Preserve URLs, email addresses, and file paths byte-perfect.\n"
            "5. Preserve line breaks (\\n) and separators like '|' '━'.\n"
            "6. Do NOT translate brand/proper nouns (ChatGPT, Netflix, Adobe, Canva, etc.).\n"
            "7. If a string is already in the target language, return it UNCHANGED.\n"
            "8. Output ONLY a valid JSON array of the same length, in the SAME order.\n"
            "9. NO commentary, NO markdown code fences — just the raw JSON array.\n\n"
            f"Input array:\n{input_json}"
        )
        translated_list = None
        try:
            resp = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": max(600, int(len(input_json) * 2.5)),
                    "response_mime_type": "application/json",
                },
            )
            raw = (resp.text or "").strip()
            # Strip markdown fences if the model added them despite instructions
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw).rstrip("`").strip()
            parsed = json.loads(raw)
            if isinstance(parsed, list) and len(parsed) == len(chunk):
                translated_list = [str(x) for x in parsed]
            else:
                logger.warning(f"[batch] mismatched length: got {len(parsed)}, expected {len(chunk)}")
        except Exception as e:
            logger.warning(f"[batch] chunk failed: {e} — falling back to per-item")

        if translated_list is None:
            # Fallback: translate each item individually (slow but reliable)
            translated_list = []
            for (_, t) in chunk:
                translated_list.append(translate_text(t, to_lang=to_lang,
                                                       from_lang=from_lang))

        # Save to cache + output
        for (orig_idx, orig_text), translated in zip(chunk, translated_list):
            if translated and translated != orig_text:
                _cache_put(orig_text, to_lang, translated)
            out[orig_idx] = translated or orig_text

    return out


# ------------------------------------------------------------
# Backend auto-translate hook — called by ext_suppliers on sync
# ------------------------------------------------------------
def maybe_auto_translate_description(description: str) -> str:
    """
    Backend silent auto-translate. Called after fetching a product's
    description from a supplier. Only runs if:
      - translator is enabled AND
      - detected source language == configured FROM lang (or FROM==auto and
        detected != TO)
    Returns translated OR original text — never raises.
    """
    if not description or not description.strip():
        return description
    if not is_translator_enabled():
        return description

    from_lang = get_from_lang()
    to_lang = get_to_lang()
    if to_lang == "auto" or not to_lang:
        return description

    try:
        detected = detect_language(description)
    except Exception:
        return description

    should = False
    if from_lang == "auto":
        # Auto mode: translate anything that isn't already in the target
        should = (detected != to_lang and detected != "en")
        # Special case: if TO is not English but source is English, still translate
        if to_lang != "en" and detected == "en":
            should = True
    else:
        should = (detected == from_lang and detected != to_lang)

    if not should:
        return description

    try:
        translated = translate_text(description, to_lang=to_lang,
                                     from_lang=detected)
        return translated
    except Exception as e:
        logger.warning(f"[translator] auto-translate fail: {e}")
        return description


# ============================================================
# FULL BOT SCAN — translates every user-facing field in-place
# ============================================================
def _scan_and_translate_all(context=None):
    """
    Do a full bot scan. Returns a stats dict:
      {
        checked, translated, skipped,
        by_table: {table_name: {checked, translated}}
      }
    Never raises — catches everything per row.
    """
    stats = {"checked": 0, "translated": 0, "skipped": 0,
             "by_table": {}, "error": None}
    if not is_translator_enabled():
        stats["error"] = "translator is OFF — enable it first"
        return stats
    to_lang = get_to_lang()
    from_lang = get_from_lang()
    if not to_lang or to_lang == "auto":
        stats["error"] = "target language not set"
        return stats

    conn = get_connection(); c = conn.cursor()

    # 🆕 v89: BATCH-OPTIMIZED SCAN — 20x faster than per-row translate calls.
    # Two-phase per table:
    #   Phase 1: scan all rows, count "checked", find rows that need translation
    #            (detect_language + should-translate check)
    #   Phase 2: batch-translate the flagged texts in chunks of BATCH_SIZE
    #   Phase 3: write updates back to DB
    #
    # A batch of 20 = 1 API call ≈ 2-3s (vs 20 calls ≈ 40-60s serial).

    def _scan_table(table_name, column_name, update_stmt, table_key):
        """Runs the 3-phase pattern for a (table, description-column) pair."""
        try:
            c.execute(f"SELECT id, {column_name} FROM {table_name}")
            rows = c.fetchall()
        except Exception as e:
            logger.warning(f"[scan] {table_key}: {e}")
            return

        stats["by_table"].setdefault(table_key, {"checked": 0, "translated": 0})

        # Phase 1: figure out which rows need translation
        to_translate = []       # list of (row_id, original_text, detected_lang)
        for r in rows:
            stats["checked"] += 1
            stats["by_table"][table_key]["checked"] += 1
            text = r[column_name] or ""
            if not text.strip():
                stats["skipped"] += 1
                continue
            try:
                detected = detect_language(text)
            except Exception:
                stats["skipped"] += 1
                continue
            if from_lang == "auto":
                should = (detected != to_lang and detected != "en") or \
                         (to_lang != "en" and detected == "en")
            else:
                should = (detected == from_lang and detected != to_lang)
            if not should:
                stats["skipped"] += 1
                continue
            to_translate.append((r["id"], text, detected))

        if not to_translate:
            return

        # Phase 2: batch-translate. Group by detected source language so the
        # Gemini prompt tells the model the right FROM language.
        by_src = {}
        for rid, text, det in to_translate:
            by_src.setdefault(det, []).append((rid, text))

        translations = {}   # row_id → translated text
        for src_lang, items in by_src.items():
            texts_only = [t for (_, t) in items]
            translated_list = translate_batch(texts_only, to_lang=to_lang,
                                               from_lang=src_lang)
            for (rid, orig), new in zip(items, translated_list):
                if new and new != orig:
                    translations[rid] = new

        # Phase 3: write back
        for rid, new in translations.items():
            try:
                c.execute(update_stmt, (new, rid))
                stats["translated"] += 1
                stats["by_table"][table_key]["translated"] += 1
            except Exception as e:
                logger.debug(f"[scan] update fail {table_key}#{rid}: {e}")

    # 🆕 v88: SCOPE STRICTLY LIMITED to product descriptions only.
    _scan_table("products", "description",
                "UPDATE products SET description=? WHERE id=?",
                "products.description")
    _scan_table("ext_products", "description",
                "UPDATE ext_products SET description=? WHERE id=?",
                "ext_products.description")

    conn.commit(); conn.close()

    set_setting("translator_last_scan_at",
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return stats


# ============================================================
# ADMIN PANEL — 🌐 Translator
# ============================================================
async def _safe_edit(q, text, **kw):
    try:
        await q.edit_message_text(text, **kw)
    except Exception:
        try:
            kw.pop("parse_mode", None)
            await q.edit_message_text(text, **kw)
        except Exception:
            try:
                await q.message.reply_text(text)
            except Exception:
                pass


def _translator_panel_text() -> str:
    on = is_translator_enabled()
    fl = get_from_lang()
    tl = get_to_lang()
    last = get_setting("translator_last_scan_at", "never")
    fl_lbl = LANGUAGES.get(fl, fl)
    tl_lbl = LANGUAGES.get(tl, tl)
    status = "🟢 ON" if on else "🔴 OFF"
    return (
        "🌐 *Auto-Translator*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Status: {status}\n"
        f"📥 From: {fl_lbl}\n"
        f"📤 To: {tl_lbl}\n"
        f"🕐 Last scan: `{last}`\n\n"
        "*Scope (v88 — locked):*\n"
        "✅ Only product *descriptions* (shop + supplier)\n"
        "❌ Nothing else — names, categories, buttons, responses,"
        " past deliveries all stay untouched.\n\n"
        "*When ON:*\n"
        "• Backend auto-translates supplier descriptions on every sync\n"
        "• Tap 🌐 Scan Descriptions Now to sweep all existing rows\n\n"
        "_Uses Gemini 2.5 Flash — cached, fast, free tier._"
    )


def _translator_panel_kb() -> InlineKeyboardMarkup:
    on = is_translator_enabled()
    kb = []
    kb.append([InlineKeyboardButton(
        ("🔴 Turn OFF" if on else "🟢 Turn ON"),
        callback_data="trxl_toggle")])
    kb.append([InlineKeyboardButton("📥 Set FROM Language",
                                     callback_data="trxl_pick_from_0")])
    kb.append([InlineKeyboardButton("📤 Set TO Language",
                                     callback_data="trxl_pick_to_0")])
    kb.append([InlineKeyboardButton("🌐 Scan Descriptions Now",
                                     callback_data="trxl_scan_confirm")])
    kb.append([InlineKeyboardButton("🧹 Clear Translation Cache",
                                     callback_data="trxl_clear_cache")])
    kb.append([InlineKeyboardButton("🔙 Back to Settings",
                                     callback_data="admin_settings")])
    return InlineKeyboardMarkup(kb)


async def admin_translator_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    await _safe_edit(q, _translator_panel_text(), parse_mode="Markdown",
                     reply_markup=_translator_panel_kb())


async def trxl_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    set_translator_enabled(not is_translator_enabled())
    await q.answer("Toggled ✅")
    await _safe_edit(q, _translator_panel_text(), parse_mode="Markdown",
                     reply_markup=_translator_panel_kb())


# ---- Language picker (paginated 10 per page, exclude AUTO for TO) ----
LANGS_PER_PAGE = 10


def _pick_kb(direction: str, page: int) -> InlineKeyboardMarkup:
    codes = list(LANGUAGES.keys())
    if direction == "to":
        codes = [c for c in codes if c != "auto"]
    total_pages = max(1, (len(codes) + LANGS_PER_PAGE - 1) // LANGS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * LANGS_PER_PAGE
    end = start + LANGS_PER_PAGE
    kb = []
    current = get_from_lang() if direction == "from" else get_to_lang()
    for code in codes[start:end]:
        mark = "⦿ " if code == current else "   "
        kb.append([InlineKeyboardButton(
            f"{mark}{LANGUAGES[code]}",
            callback_data=f"trxl_set_{direction}_{code}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️",
            callback_data=f"trxl_pick_{direction}_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}",
        callback_data="trxl_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️",
            callback_data=f"trxl_pick_{direction}_{page+1}"))
    if len(nav) > 1:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 Back to Translator",
                                     callback_data="admin_translator")])
    return InlineKeyboardMarkup(kb)


async def trxl_pick_from_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        page = int((q.data or "").replace("trxl_pick_from_", ""))
    except Exception:
        page = 0
    await _safe_edit(q,
        "📥 *Pick FROM Language*\n\n_Source language to detect & translate away from._",
        parse_mode="Markdown", reply_markup=_pick_kb("from", page))


async def trxl_pick_to_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        page = int((q.data or "").replace("trxl_pick_to_", ""))
    except Exception:
        page = 0
    await _safe_edit(q,
        "📤 *Pick TO Language*\n\n_Everything gets translated INTO this language._",
        parse_mode="Markdown", reply_markup=_pick_kb("to", page))


async def trxl_set_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    data = (q.data or "").replace("trxl_set_", "")
    try:
        direction, code = data.split("_", 1)
    except Exception:
        await q.answer("bad"); return
    if code not in LANGUAGES:
        await q.answer("bad lang"); return
    if direction == "from":
        set_from_lang(code)
    else:
        set_to_lang(code)
    await q.answer(f"Set {LANGUAGES[code]} ✅")
    await _safe_edit(q, _translator_panel_text(), parse_mode="Markdown",
                     reply_markup=_translator_panel_kb())


async def trxl_noop_callback(update, context):
    await update.callback_query.answer()


async def trxl_scan_confirm_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    if not is_translator_enabled():
        await _safe_edit(q,
            "⚠️ Translator is OFF. Turn it ON first, then scan.",
            reply_markup=_translator_panel_kb())
        return
    tl = get_to_lang()
    fl = get_from_lang()
    text = (
        "⚠️ *Confirm Description Scan*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"This will scan *product descriptions only* (both shop `products` "
        f"and supplier `ext_products` tables) and translate any that are in "
        f"{LANGUAGES.get(fl, fl)} into {LANGUAGES.get(tl, tl)}.\n\n"
        "✅ Affected: `products.description`, `ext_products.description`\n"
        "❌ NOT affected: names, categories, buttons, responses, past deliveries.\n\n"
        "This may take 30-60 seconds and use some Gemini API quota.\n\n"
        "Continue?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, Run Full Scan",
                               callback_data="trxl_scan_run")],
        [InlineKeyboardButton("❌ Cancel",
                               callback_data="admin_translator")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def trxl_scan_run_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("⏳ Scanning… may take a while")
    # Send a status message that we'll update
    try:
        await _safe_edit(q,
            "⏳ *Scan in progress…*\n\nPlease wait — do not close this screen.",
            parse_mode="Markdown")
    except Exception:
        pass

    stats = await _run_scan_async(context)

    lines = [
        "✅ *Description Scan Complete*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📊 Descriptions checked: *{stats['checked']}*",
        f"🌐 Translated: *{stats['translated']}*",
        f"⏭️ Skipped (already target lang / empty): *{stats['skipped']}*",
    ]
    if stats.get("error"):
        lines.append(f"⚠️ Error: {stats['error']}")
    if stats.get("by_table"):
        lines.append("")
        lines.append("*Per-table breakdown:*")
        for tbl, s in stats["by_table"].items():
            if s["translated"] > 0 or s["checked"] > 0:
                lines.append(f"  • `{tbl}` — {s['translated']}/{s['checked']}")

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back to Translator",
                              callback_data="admin_translator")
    ]])
    try:
        await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                         reply_markup=kb)
    except Exception:
        await q.message.reply_text("\n".join(lines), parse_mode="Markdown",
                                    reply_markup=kb)


async def _run_scan_async(context):
    """Run the (blocking) scan in a thread to avoid stalling the event loop."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scan_and_translate_all, context)


async def trxl_clear_cache_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    conn = get_connection(); c = conn.cursor()
    c.execute("DELETE FROM bot_settings WHERE key LIKE 'trxl_cache_%'")
    n = c.rowcount
    conn.commit(); conn.close()
    await q.answer(f"Cleared {n} cached translations ✅", show_alert=True)
    await _safe_edit(q, _translator_panel_text(), parse_mode="Markdown",
                     reply_markup=_translator_panel_kb())
