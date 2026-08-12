# ============================================
# 🌍 INTERNATIONALIZATION (i18n)
# ============================================
from database import get_connection

# ── Supported languages ──
LANGUAGES = {
    "en": {"name": "English",     "flag": "🇬🇧", "native": "English"},
    "ur": {"name": "Urdu",        "flag": "🇵🇰", "native": "اردو"},
    "ru": {"name": "Roman Urdu",  "flag": "🇵🇰", "native": "Roman Urdu"},
    "hi": {"name": "Hindi",       "flag": "🇮🇳", "native": "हिन्दी"},
    "ar": {"name": "Arabic",      "flag": "🇸🇦", "native": "العربية"},
    "es": {"name": "Spanish",     "flag": "🇪🇸", "native": "Español"},
    "fr": {"name": "French",      "flag": "🇫🇷", "native": "Français"},
    "ru_lang": {"name": "Russian", "flag": "🇷🇺", "native": "Русский"},
    "zh": {"name": "Chinese",     "flag": "🇨🇳", "native": "中文"},
    "de": {"name": "German",      "flag": "🇩🇪", "native": "Deutsch"},
}

DEFAULT_LANG = "en"

# Display-time translation cache. This never mutates products/supplier DB data.
# It only translates what is shown to a user and caches result in bot_settings.
def _display_lang_code(lang):
    if not lang:
        return DEFAULT_LANG
    # i18n.py uses "ru" for Roman Urdu and "ru_lang" for Russian.
    return str(lang)


def _display_lang_name(lang):
    lang = _display_lang_code(lang)
    return {
        "en": "English",
        "ur": "Urdu",
        "ru": "Roman Urdu (Urdu written in English/Latin letters)",
        "hi": "Hindi (हिन्दी)",
        "ar": "Arabic",
        "es": "Spanish",
        "fr": "French",
        "ru_lang": "Russian",
        "zh": "Chinese",
        "de": "German",
    }.get(lang, LANGUAGES.get(lang, {}).get('name', lang))


def _display_cache_key(text, lang):
    import hashlib
    raw = f"{lang}||{text}".encode('utf-8', errors='ignore')
    return "i18n_display_" + hashlib.md5(raw).hexdigest()[:24]


# ─────────────────────────────────────────────────────────────
# 🐛 v161.21 FIX (bot SLOW): translate_display_text() used to call the
# Gemini API SYNCHRONOUSLY on the asyncio event loop. Product-detail renders
# call tr_user() ~16× per view → every product tap by a non-English user did
# 16 blocking network calls → the ENTIRE bot froze for seconds → every user's
# clicks felt slow.
#
# New behaviour (never blocks the loop):
#   1. In-process LRU cache  → microseconds.
#   2. DB cache (bot_settings) → one fast local read.
#   3. On MISS → return the ORIGINAL text immediately and translate in a
#      background daemon thread (rate-limited, deduped) so the NEXT view is
#      already translated. The event loop is NEVER blocked by Gemini.
# ─────────────────────────────────────────────────────────────
import threading

_mem_cache = {}
_mem_lock = threading.Lock()
_pending = set()                 # keys currently being translated in background
_gemini_sem = threading.BoundedSemaphore(3)   # max 3 concurrent Gemini calls
_MEM_CACHE_MAX = 2000
_MAX_PENDING = 60                # don't queue unbounded background translations


def _cache_get(key):
    with _mem_lock:
        return _mem_cache.get(key)


def _cache_put(key, value):
    global _mem_cache
    with _mem_lock:
        if len(_mem_cache) >= _MEM_CACHE_MAX:
            # cheap eviction: drop ~20% oldest keys
            _mem_cache = dict(list(_mem_cache.items())[len(_mem_cache) // 5:])
        _mem_cache[key] = value


def _gemini_translate_blocking(text, target, key):
    """Blocking Gemini call — runs ONLY inside a worker thread (never the loop)."""
    import google.generativeai as genai
    from config import GEMINI_API_KEY
    if not GEMINI_API_KEY:
        return None
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    prompt = (
        f"Translate the following Telegram bot UI text to {target}.\n"
        "Rules:\n"
        "1. Preserve emojis exactly.\n"
        "2. Preserve HTML tags and [[HTML]] markers exactly.\n"
        "3. Preserve placeholders like {name}, {price}, {qty}, and callback-like IDs.\n"
        "4. Preserve URLs, emails, codes, and text inside <code> or `backticks`.\n"
        "5. Do not translate brand/product names like ChatGPT, Netflix, Adobe, Canva, Binance, EasyPaisa, JazzCash.\n"
        "6. Keep line breaks and separators. Output only translated text.\n\n"
        f"Text:\n{text}"
    )
    resp = model.generate_content(
        prompt,
        generation_config={"temperature": 0.15,
                           "max_output_tokens": max(500, int(len(text) * 2.5))})
    out = (getattr(resp, 'text', '') or '').strip()
    if not out:
        return None
    out = out.strip('`').strip()
    _cache_put(key, out)
    try:
        from database import set_setting
        set_setting(key, out)
    except Exception:
        pass
    return out


def _warm_translation(text, target, key):
    """Schedule a background translation — returns immediately, never blocks."""
    with _mem_lock:
        if key in _pending or len(_pending) >= _MAX_PENDING:
            return
        _pending.add(key)

    def _run():
        try:
            with _gemini_sem:
                try:
                    _gemini_translate_blocking(text, target, key)
                except Exception:
                    pass
        finally:
            with _mem_lock:
                _pending.discard(key)

    threading.Thread(target=_run, daemon=True).start()


def translate_display_text(text, user_id=None, lang=None, max_len=1800):
    """Translate user-visible text at display-time only — ALWAYS non-blocking.

    v161.21: Gemini translation never runs on the event loop. On a cache miss
    the original text is returned instantly and the translation is warmed in a
    background thread, so the bot can NEVER be frozen by translation again.
    """
    if text is None:
        return ""
    text = str(text)
    if not text.strip():
        return text
    try:
        lang = lang or get_user_lang(user_id)
    except Exception:
        lang = lang or DEFAULT_LANG
    lang = _display_lang_code(lang)
    if lang == DEFAULT_LANG:
        return text
    # Avoid translating huge deliveries/account data. Product descriptions and
    # UI screens are okay, credentials are handled elsewhere.
    if len(text) > max_len:
        return text
    # Keep pure URLs / code-ish strings unchanged.
    if text.strip().startswith(('http://', 'https://')):
        return text

    key = _display_cache_key(text, lang)
    # 1) in-process cache (microseconds)
    cached = _cache_get(key)
    if cached:
        return cached
    # 2) DB cache (fast local read)
    try:
        from database import get_setting
        cached = get_setting(key, "")
        if cached:
            _cache_put(key, cached)
            return cached
    except Exception:
        pass
    # 3) MISS → return original NOW, translate in background (never blocks)
    try:
        from config import GEMINI_API_KEY
        if GEMINI_API_KEY:
            _warm_translation(text, _display_lang_name(lang), key)
    except Exception:
        pass
    return text


def tr_user(text, user_id=None, lang=None):
    return translate_display_text(text, user_id=user_id, lang=lang)


# ── Master translations dictionary ──
TRANSLATIONS = {
    # ══════════ COMMON ══════════
    "btn_back":            {"en": "🔙 Back",            "ur": "🔙 واپس",          "ru": "🔙 Wapas",        "hi": "🔙 Wapas"},
    "btn_home":            {"en": "🏠 Home",            "ur": "🏠 مرکزی صفحہ",     "ru": "🏠 Home",         "hi": "🏠 Home"},
    "btn_main_menu":       {"en": "🏠 Main Menu",       "ur": "🏠 مرکزی مینو",     "ru": "🏠 Main Menu",    "hi": "🏠 Main Menu"},
    "btn_cancel":          {"en": "❌ Cancel",          "ur": "❌ منسوخ",          "ru": "❌ Cancel",        "hi": "❌ Cancel"},
    "btn_yes":             {"en": "✅ Yes",             "ur": "✅ ہاں",           "ru": "✅ Haan",         "hi": "✅ Haan"},
    "btn_no":              {"en": "❌ No",              "ur": "❌ نہیں",          "ru": "❌ Nahi",         "hi": "❌ Nahi"},
    "loading":             {"en": "⏳ Loading...",      "ur": "⏳ لوڈ ہو رہا ہے...", "ru": "⏳ Load ho raha hai...", "hi": "⏳ Load ho raha hai..."},
    "done":                {"en": "✅ Done",            "ur": "✅ ہو گیا",        "ru": "✅ Ho gaya",      "hi": "✅ Ho gaya"},
    "error":               {"en": "❌ Error occurred",  "ur": "❌ خرابی ہوئی",    "ru": "❌ Koi error aa gaya", "hi": "❌ Error aa gaya"},
    "access_denied":       {"en": "❌ Access denied",   "ur": "❌ رسائی نہیں",     "ru": "❌ Access nahi",  "hi": "❌ Access nahi"},

    # ══════════ MAIN MENU BUTTONS ══════════
    "menu_shop":           {"en": "🛍️ Shop",           "ur": "🛍️ دکان",         "ru": "🛍️ Shop",        "hi": "🛍️ दुकान"},
    "menu_my_orders":      {"en": "📦 My Orders",      "ur": "📦 میرے آرڈرز",    "ru": "📦 Mere Orders",  "hi": "📦 मेरे ऑर्डर"},
    "menu_my_account":     {"en": "👤 My Account",     "ur": "👤 میرا اکاؤنٹ",    "ru": "👤 Mera Account", "hi": "👤 मेरा खाता"},
    "menu_buy_points":     {"en": "💎 Buy Points",     "ur": "💎 پوائنٹس خریدیں", "ru": "💎 Points Khareedo", "hi": "💎 पॉइंट्स खरीदें"},
    "menu_referral":       {"en": "🎁 Referral",       "ur": "🎁 ریفرل",          "ru": "🎁 Referral",     "hi": "🎁 रेफरल"},
    "menu_transactions":   {"en": "📜 Transactions",   "ur": "📜 لین دین",        "ru": "📜 Transactions", "hi": "📜 लेन-देन"},
    "menu_support":        {"en": "🎫 Support",        "ur": "🎫 سپورٹ",          "ru": "🎫 Support",      "hi": "🎫 सहायता"},
    "menu_warranty":       {"en": "🛡️ Warranty/Refund","ur": "🛡️ وارنٹی/ریفنڈ",  "ru": "🛡️ Warranty/Refund", "hi": "🛡️ वारंटी/रिफंड"},
    "menu_reviews":        {"en": "⭐ Reviews",         "ur": "⭐ جائزے",          "ru": "⭐ Reviews",      "hi": "⭐ समीक्षाएँ"},
    "menu_loyalty":        {"en": "🏆 Loyalty",         "ur": "🏆 لائلٹی",         "ru": "🏆 Loyalty",      "hi": "🏆 वफादारी"},
    "menu_admin":          {"en": "👑 Admin Panel",    "ur": "👑 ایڈمن پینل",     "ru": "👑 Admin Panel",  "hi": "👑 एडमिन पैनल"},
    "menu_language":       {"en": "🌐 Language",       "ur": "🌐 زبان",           "ru": "🌐 Language",     "hi": "🌐 भाषा"},
    # 🆕 v161.18: missing main-menu buttons so they translate when language changes
    "menu_price_list":     {"en": "📊 Price List",     "ur": "📊 قیمت کی فہرست", "ru": "📊 Price List",   "hi": "📊 मूल्य सूची"},
    "menu_reseller_api":   {"en": "🔗 Reseller API Key","ur": "🔗 ریزیلر API کلید","ru": "🔗 Reseller API Key","hi": "🔗 रिसेलर API कुंजी"},

    # ══════════ LANGUAGE SELECTOR ══════════
    "lang_select_title":   {"en": "🌐 Select Your Language\n━━━━━━━━━━━━━━━━━━━━\nChoose your preferred language:",
                            "ur": "🌐 اپنی زبان منتخب کریں\n━━━━━━━━━━━━━━━━━━━━\nاپنی پسندیدہ زبان منتخب کریں:",
                            "ru": "🌐 Apni Language Select Karein\n━━━━━━━━━━━━━━━━━━━━\nApni pasandida language chunein:",
                            "hi": "🌐 Apni Language Select Karo\n━━━━━━━━━━━━━━━━━━━━\nApni pasandida language choose karo:"},
    "lang_changed":        {"en": "✅ Language changed to English",
                            "ur": "✅ زبان تبدیل ہو گئی اردو",
                            "ru": "✅ Language change ho gayi: Roman Urdu",
                            "hi": "✅ Language change ho gayi: Hinglish"},
    "lang_current":        {"en": "Current: ",          "ur": "موجودہ: ",          "ru": "Abhi: ",          "hi": "Abhi: "},

    # ══════════ REVIEWS ══════════
    "rev_title":           {"en": "⭐ Product Reviews", "ur": "⭐ پروڈکٹ کے جائزے", "ru": "⭐ Product Reviews", "hi": "⭐ Product Reviews"},
    "rev_avg":             {"en": "Average Rating: ",    "ur": "اوسط ریٹنگ: ",     "ru": "Average Rating: ", "hi": "Average Rating: "},
    "rev_count":           {"en": "Total Reviews: ",     "ur": "کل جائزے: ",       "ru": "Total Reviews: ",  "hi": "Total Reviews: "},
    "rev_no_reviews":      {"en": "📭 No reviews yet. Be the first!",
                            "ur": "📭 ابھی کوئی جائزہ نہیں۔ پہلے بنیں!",
                            "ru": "📭 Abhi koi review nahi. Pehlay banein!",
                            "hi": "📭 Abhi koi review nahi. Pehle bano!"},
    "rev_write":           {"en": "✍️ Write Review",     "ur": "✍️ جائزہ لکھیں",   "ru": "✍️ Review Likhein",     "hi": "✍️ Review Likho"},
    "rev_my":              {"en": "📝 My Reviews",       "ur": "📝 میرے جائزے",    "ru": "📝 Mere Reviews",       "hi": "📝 Mere Reviews"},
    "rev_pick_order":      {"en": "📦 Choose an order to review:",
                            "ur": "📦 جائزہ دینے کے لیے آرڈر منتخب کریں:",
                            "ru": "📦 Review dene k liye order chunein:",
                            "hi": "📦 Review dene ke liye order choose karo:"},
    "rev_no_eligible":     {"en": "❌ You need a delivered order to write a review.",
                            "ur": "❌ جائزہ لکھنے کے لیے آپ کے پاس ڈلیورڈ آرڈر ہونا چاہیے۔",
                            "ru": "❌ Review likhne k liye aap k pas delivered order hona chahiye.",
                            "hi": "❌ Review likhne ke liye aapke paas delivered order hona chahiye."},
    "rev_pick_rating":     {"en": "⭐ Rate this product:\nTap stars below",
                            "ur": "⭐ اس پروڈکٹ کی درجہ بندی کریں:\nنیچے ستارے پر کلک کریں",
                            "ru": "⭐ Is product ko rate karein:\nNiche stars tap karein",
                            "hi": "⭐ Is product ko rate karo:\nNiche stars tap karo"},
    "rev_enter_text":      {"en": "✍️ Now write your review (or /skip):",
                            "ur": "✍️ اب اپنا جائزہ لکھیں (یا /skip):",
                            "ru": "✍️ Ab apna review likhein (ya /skip):",
                            "hi": "✍️ Ab apna review likho (ya /skip):"},
    "rev_submitted":       {"en": "✅ Thank you! Your {stars} review has been submitted.",
                            "ur": "✅ شکریہ! آپ کا {stars} جائزہ جمع ہو گیا۔",
                            "ru": "✅ Shukriya! Aap ka {stars} review submit ho gaya.",
                            "hi": "✅ Thanks! Aapka {stars} review submit ho gaya."},
    "rev_already":         {"en": "ℹ️ You've already reviewed this product.",
                            "ur": "ℹ️ آپ پہلے ہی اس پروڈکٹ کا جائزہ دے چکے ہیں۔",
                            "ru": "ℹ️ Aap pehlay hi is product ka review de chuke hain.",
                            "hi": "ℹ️ Aap pehle hi is product ka review de chuke ho."},
    "rev_skip":            {"en": "⏭️ Skip text",       "ur": "⏭️ متن چھوڑیں",    "ru": "⏭️ Text Skip",    "hi": "⏭️ Text Skip"},

    # ══════════ LOYALTY TIERS ══════════
    "tier_bronze":         {"en": "🥉 Bronze",           "ur": "🥉 برونز",          "ru": "🥉 Bronze",        "hi": "🥉 Bronze"},
    "tier_silver":         {"en": "🥈 Silver",           "ur": "🥈 سلور",          "ru": "🥈 Silver",        "hi": "🥈 Silver"},
    "tier_gold":           {"en": "🥇 Gold",             "ur": "🥇 گولڈ",          "ru": "🥇 Gold",          "hi": "🥇 Gold"},
    "tier_platinum":       {"en": "💎 Platinum",         "ur": "💎 پلاٹینم",       "ru": "💎 Platinum",      "hi": "💎 Platinum"},
    "tier_diamond":        {"en": "💠 Diamond",          "ur": "💠 ڈائمنڈ",        "ru": "💠 Diamond",       "hi": "💠 Diamond"},
    "tier_your":           {"en": "🏆 Your Tier: ",      "ur": "🏆 آپ کی سطح: ",    "ru": "🏆 Aap ka Tier: ",  "hi": "🏆 Aapka Tier: "},
    "tier_progress":       {"en": "📈 Progress to next tier:",
                            "ur": "📈 اگلی سطح تک پیش رفت:",
                            "ru": "📈 Next tier tak progress:",
                            "hi": "📈 Next tier tak progress:"},
    "tier_total_spent":    {"en": "💰 Total Spent: ",    "ur": "💰 کل خرچ: ",       "ru": "💰 Total Spent: ",  "hi": "💰 Total Spent: "},
    "tier_total_orders":   {"en": "📦 Total Orders: ",   "ur": "📦 کل آرڈرز: ",     "ru": "📦 Total Orders: ", "hi": "📦 Total Orders: "},
    "tier_max":            {"en": "🎉 You're at the highest tier!",
                            "ur": "🎉 آپ سب سے اعلیٰ سطح پر ہیں!",
                            "ru": "🎉 Aap sab se top tier pe hain!",
                            "hi": "🎉 Aap sabse top tier pe ho!"},
    "tier_benefits":       {"en": "🎁 Your Benefits:",   "ur": "🎁 آپ کے فوائد:",   "ru": "🎁 Aap ke Benefits:", "hi": "🎁 Aapke Benefits:"},
    "tier_upgraded":       {"en": "🎉 Congratulations! You've been upgraded to {tier} tier!",
                            "ur": "🎉 مبارک ہو! آپ کو {tier} سطح پر اپ گریڈ کر دیا گیا!",
                            "ru": "🎉 Mubarak ho! Aap ko {tier} tier pe upgrade kar diya gaya!",
                            "hi": "🎉 Congrats! Aap ko {tier} tier pe upgrade kar diya gaya!"},

    # ══════════ ANALYTICS (admin) ══════════
    "an_title":            {"en": "📊 Analytics Dashboard", "ur": "📊 تجزیاتی ڈیش بورڈ", "ru": "📊 Analytics Dashboard", "hi": "📊 Analytics Dashboard"},
    "an_today":            {"en": "📅 Today",            "ur": "📅 آج",            "ru": "📅 Aaj",           "hi": "📅 Aaj"},
    "an_week":             {"en": "📆 Last 7 Days",      "ur": "📆 پچھلے 7 دن",     "ru": "📆 Last 7 Din",     "hi": "📆 Last 7 Din"},
    "an_month":            {"en": "🗓️ Last 30 Days",    "ur": "🗓️ پچھلے 30 دن",   "ru": "🗓️ Last 30 Din",   "hi": "🗓️ Last 30 Din"},
    "an_all_time":         {"en": "♾️ All Time",         "ur": "♾️ تمام وقت",      "ru": "♾️ Sara Time",     "hi": "♾️ Sara Time"},
    "an_top_products":     {"en": "🏆 Top Products",     "ur": "🏆 ٹاپ پروڈکٹس",   "ru": "🏆 Top Products",  "hi": "🏆 Top Products"},
    "an_top_customers":    {"en": "👑 Top Customers",    "ur": "👑 ٹاپ گاہک",      "ru": "👑 Top Customers", "hi": "👑 Top Customers"},
    "an_payment_methods":  {"en": "💳 Payment Methods",  "ur": "💳 ادائیگی کے طریقے", "ru": "💳 Payment Methods", "hi": "💳 Payment Methods"},
    "an_revenue":          {"en": "💰 Revenue: ",        "ur": "💰 آمدنی: ",       "ru": "💰 Revenue: ",     "hi": "💰 Revenue: "},
    "an_orders":           {"en": "🛒 Orders: ",         "ur": "🛒 آرڈرز: ",       "ru": "🛒 Orders: ",      "hi": "🛒 Orders: "},
    "an_new_users":        {"en": "👥 New Users: ",      "ur": "👥 نئے صارفین: ",  "ru": "👥 Naye Users: ",  "hi": "👥 Naye Users: "},
    "an_avg_order":        {"en": "💵 Avg Order Value: ", "ur": "💵 اوسط آرڈر ویلیو: ", "ru": "💵 Avg Order Value: ", "hi": "💵 Avg Order Value: "},
    "an_conversion":       {"en": "📈 Conversion Rate: ", "ur": "📈 کنورژن ریٹ: ",   "ru": "📈 Conversion Rate: ", "hi": "📈 Conversion Rate: "},
    "an_no_data":          {"en": "📭 No data yet",      "ur": "📭 ابھی کوئی ڈیٹا نہیں", "ru": "📭 Abhi data nahi", "hi": "📭 Abhi data nahi"},

    # ══════════ MISC ══════════
    "stars_5":             {"en": "⭐⭐⭐⭐⭐",            "ur": "⭐⭐⭐⭐⭐",          "ru": "⭐⭐⭐⭐⭐",         "hi": "⭐⭐⭐⭐⭐"},
}



# ─────────────────────────────────────────────────────────────
# 🆕 v161.20: FULL 10-LANGUAGE COVERAGE — Arabic / Spanish / French /
# German / Russian / Chinese added for every TRANSLATIONS key, so the main
# menu buttons + language selector + reviews/loyalty/analytics labels all
# translate natively in ALL supported languages (not just en/ur/ru/hi).
# ─────────────────────────────────────────────────────────────
LANG_FILL = {
    # ────────── COMMON ──────────
    "btn_back": {
        "ar": "🔙 رجوع", "es": "🔙 Atrás", "fr": "🔙 Retour",
        "de": "🔙 Zurück", "ru_lang": "🔙 Назад", "zh": "🔙 返回",
    },
    "btn_home": {
        "ar": "🏠 الرئيسية", "es": "🏠 Inicio", "fr": "🏠 Accueil",
        "de": "🏠 Startseite", "ru_lang": "🏠 Главная", "zh": "🏠 主页",
    },
    "btn_main_menu": {
        "ar": "🏠 القائمة الرئيسية", "es": "🏠 Menú Principal", "fr": "🏠 Menu Principal",
        "de": "🏠 Hauptmenü", "ru_lang": "🏠 Главное меню", "zh": "🏠 主菜单",
    },
    "btn_cancel": {
        "ar": "❌ إلغاء", "es": "❌ Cancelar", "fr": "❌ Annuler",
        "de": "❌ Abbrechen", "ru_lang": "❌ Отмена", "zh": "❌ 取消",
    },
    "btn_yes": {
        "ar": "✅ نعم", "es": "✅ Sí", "fr": "✅ Oui",
        "de": "✅ Ja", "ru_lang": "✅ Да", "zh": "✅ 是",
    },
    "btn_no": {
        "ar": "❌ لا", "es": "❌ No", "fr": "❌ Non",
        "de": "❌ Nein", "ru_lang": "❌ Нет", "zh": "❌ 否",
    },
    "loading": {
        "ar": "⏳ جارٍ التحميل...", "es": "⏳ Cargando...", "fr": "⏳ Chargement...",
        "de": "⏳ Wird geladen...", "ru_lang": "⏳ Загрузка...", "zh": "⏳ 加载中...",
    },
    "done": {
        "ar": "✅ تم", "es": "✅ Hecho", "fr": "✅ Terminé",
        "de": "✅ Fertig", "ru_lang": "✅ Готово", "zh": "✅ 完成",
    },
    "error": {
        "ar": "❌ حدث خطأ", "es": "❌ Ocurrió un error", "fr": "❌ Une erreur est survenue",
        "de": "❌ Ein Fehler ist aufgetreten", "ru_lang": "❌ Произошла ошибка", "zh": "❌ 发生错误",
    },
    "access_denied": {
        "ar": "❌ تم رفض الوصول", "es": "❌ Acceso denegado", "fr": "❌ Accès refusé",
        "de": "❌ Zugriff verweigert", "ru_lang": "❌ Доступ запрещён", "zh": "❌ 拒绝访问",
    },
    # ────────── MAIN MENU BUTTONS ──────────
    "menu_shop": {
        "ar": "🛍️ المتجر", "es": "🛍️ Tienda", "fr": "🛍️ Boutique",
        "de": "🛍️ Shop", "ru_lang": "🛍️ Магазин", "zh": "🛍️ 商店",
    },
    "menu_my_orders": {
        "ar": "📦 طلباتي", "es": "📦 Mis Pedidos", "fr": "📦 Mes Commandes",
        "de": "📦 Meine Bestellungen", "ru_lang": "📦 Мои заказы", "zh": "📦 我的订单",
    },
    "menu_my_account": {
        "ar": "👤 حسابي", "es": "👤 Mi Cuenta", "fr": "👤 Mon Compte",
        "de": "👤 Mein Konto", "ru_lang": "👤 Мой аккаунт", "zh": "👤 我的账户",
    },
    "menu_buy_points": {
        "ar": "💎 شراء نقاط", "es": "💎 Comprar Puntos", "fr": "💎 Acheter des Points",
        "de": "💎 Punkte Kaufen", "ru_lang": "💎 Купить баллы", "zh": "💎 购买积分",
    },
    "menu_referral": {
        "ar": "🎁 إحالة", "es": "🎁 Referidos", "fr": "🎁 Parrainage",
        "de": "🎁 Empfehlung", "ru_lang": "🎁 Рефералы", "zh": "🎁 推荐",
    },
    "menu_transactions": {
        "ar": "📜 المعاملات", "es": "📜 Transacciones", "fr": "📜 Transactions",
        "de": "📜 Transaktionen", "ru_lang": "📜 Транзакции", "zh": "📜 交易记录",
    },
    "menu_support": {
        "ar": "🎫 الدعم", "es": "🎫 Soporte", "fr": "🎫 Support",
        "de": "🎫 Support", "ru_lang": "🎫 Поддержка", "zh": "🎫 支持",
    },
    "menu_warranty": {
        "ar": "🛡️ الضمان/الاسترداد", "es": "🛡️ Garantía/Reembolso", "fr": "🛡️ Garantie/Remboursement",
        "de": "🛡️ Garantie/Erstattung", "ru_lang": "🛡️ Гарантия/Возврат", "zh": "🛡️ 保修/退款",
    },
    "menu_reviews": {
        "ar": "⭐ التقييمات", "es": "⭐ Reseñas", "fr": "⭐ Avis",
        "de": "⭐ Bewertungen", "ru_lang": "⭐ Отзывы", "zh": "⭐ 评价",
    },
    "menu_loyalty": {
        "ar": "🏆 الولاء", "es": "🏆 Lealtad", "fr": "🏆 Fidélité",
        "de": "🏆 Treueprogramm", "ru_lang": "🏆 Лояльность", "zh": "🏆 忠诚度",
    },
    "menu_admin": {
        "ar": "👑 لوحة الإدارة", "es": "👑 Panel Admin", "fr": "👑 Panneau Admin",
        "de": "👑 Admin-Panel", "ru_lang": "👑 Панель админа", "zh": "👑 管理面板",
    },
    "menu_language": {
        "ar": "🌐 اللغة", "es": "🌐 Idioma", "fr": "🌐 Langue",
        "de": "🌐 Sprache", "ru_lang": "🌐 Язык", "zh": "🌐 语言",
    },
    "menu_price_list": {
        "ar": "📊 قائمة الأسعار", "es": "📊 Lista de Precios", "fr": "📊 Liste des Prix",
        "de": "📊 Preisliste", "ru_lang": "📊 Прайс-лист", "zh": "📊 价格表",
    },
    "menu_reseller_api": {
        "ar": "🔗 مفتاح API للبائع", "es": "🔗 Clave API Revendedor", "fr": "🔗 Clé API Revendeur",
        "de": "🔗 Reseller-API-Schlüssel", "ru_lang": "🔗 API-ключ реселлера", "zh": "🔗 经销商 API 密钥",
    },
    # ────────── LANGUAGE SELECTOR ──────────
    "lang_select_title": {
        "ar": "🌐 اختر لغتك\n━━━━━━━━━━━━━━━━━━━━\nاختر لغتك المفضلة:",
        "es": "🌐 Selecciona tu idioma\n━━━━━━━━━━━━━━━━━━━━\nElige tu idioma preferido:",
        "fr": "🌐 Choisissez votre langue\n━━━━━━━━━━━━━━━━━━━━\nSélectionnez votre langue :",
        "de": "🌐 Wählen Sie Ihre Sprache\n━━━━━━━━━━━━━━━━━━━━\nWählen Sie Ihre bevorzugte Sprache:",
        "ru_lang": "🌐 Выберите язык\n━━━━━━━━━━━━━━━━━━━━\nВыберите предпочитаемый язык:",
        "zh": "🌐 选择您的语言\n━━━━━━━━━━━━━━━━━━━━\n请选择您喜欢的语言:",
    },
    "lang_changed": {
        "ar": "✅ تم تغيير اللغة إلى العربية",
        "es": "✅ Idioma cambiado a Español",
        "fr": "✅ Langue changée en Français",
        "de": "✅ Sprache geändert auf Deutsch",
        "ru_lang": "✅ Язык изменён на Русский",
        "zh": "✅ 语言已更改为中文",
    },
    "lang_current": {
        "ar": "الحالية: ", "es": "Actual: ", "fr": "Actuel : ",
        "de": "Aktuell: ", "ru_lang": "Текущий: ", "zh": "当前: ",
    },
    # ────────── REVIEWS ──────────
    "rev_title": {
        "ar": "⭐ تقييمات المنتج", "es": "⭐ Reseñas de Producto", "fr": "⭐ Avis sur le Produit",
        "de": "⭐ Produktbewertungen", "ru_lang": "⭐ Отзывы о товаре", "zh": "⭐ 产品评价",
    },
    "rev_avg": {
        "ar": "متوسط التقييم: ", "es": "Calificación Promedio: ", "fr": "Note moyenne : ",
        "de": "Durchschnittsbewertung: ", "ru_lang": "Средний рейтинг: ", "zh": "平均评分: ",
    },
    "rev_count": {
        "ar": "إجمالي التقييمات: ", "es": "Total de Reseñas: ", "fr": "Total des avis : ",
        "de": "Gesamtbewertungen: ", "ru_lang": "Всего отзывов: ", "zh": "总评价数: ",
    },
    "rev_no_reviews": {
        "ar": "📭 لا توجد تقييمات بعد. كن الأول!",
        "es": "📭 Aún no hay reseñas. ¡Sé el primero!",
        "fr": "📭 Aucun avis pour le moment. Soyez le premier !",
        "de": "📭 Noch keine Bewertungen. Seien Sie der Erste!",
        "ru_lang": "📭 Отзывов пока нет. Будьте первым!",
        "zh": "📭 暂无评价。成为第一个吧！",
    },
    "rev_write": {
        "ar": "✍️ كتابة تقييم", "es": "✍️ Escribir Reseña", "fr": "✍️ Écrire un Avis",
        "de": "✍️ Bewertung Schreiben", "ru_lang": "✍️ Написать отзыв", "zh": "✍️ 写评价",
    },
    "rev_my": {
        "ar": "📝 تقييماتي", "es": "📝 Mis Reseñas", "fr": "📝 Mes Avis",
        "de": "📝 Meine Bewertungen", "ru_lang": "📝 Мои отзывы", "zh": "📝 我的评价",
    },
    "rev_pick_order": {
        "ar": "📦 اختر طلبًا للتقييم:",
        "es": "📦 Elige un pedido para reseñar:",
        "fr": "📦 Choisissez une commande à évaluer :",
        "de": "📦 Wählen Sie eine Bestellung zum Bewerten:",
        "ru_lang": "📦 Выберите заказ для отзыва:",
        "zh": "📦 选择要评价的订单:",
    },
    "rev_no_eligible": {
        "ar": "❌ يجب أن يكون لديك طلب مُسلَّم لكتابة تقييم.",
        "es": "❌ Necesitas un pedido entregado para escribir una reseña.",
        "fr": "❌ Vous devez avoir une commande livrée pour écrire un avis.",
        "de": "❌ Sie benötigen eine gelieferte Bestellung für eine Bewertung.",
        "ru_lang": "❌ Для отзыва нужен выполненный заказ.",
        "zh": "❌ 需要已完成的订单才能写评价。",
    },
    "rev_pick_rating": {
        "ar": "⭐ قيّم هذا المنتج:\nاضغط على النجوم أدناه",
        "es": "⭐ Califica este producto:\nToca las estrellas",
        "fr": "⭐ Notez ce produit :\nTouchez les étoiles ci-dessous",
        "de": "⭐ Bewerten Sie dieses Produkt:\nTippen Sie auf die Sterne",
        "ru_lang": "⭐ Оцените товар:\nНажмите на звёзды",
        "zh": "⭐ 为此产品评分:\n点击下方星星",
    },
    "rev_enter_text": {
        "ar": "✍️ الآن اكتب تقييمك (أو /skip):",
        "es": "✍️ Ahora escribe tu reseña (o /skip):",
        "fr": "✍️ Écrivez maintenant votre avis (ou /skip) :",
        "de": "✍️ Schreiben Sie jetzt Ihre Bewertung (oder /skip):",
        "ru_lang": "✍️ Теперь напишите отзыв (или /skip):",
        "zh": "✍️ 现在写下您的评价（或 /skip）:",
    },
    "rev_submitted": {
        "ar": "✅ شكرًا! تم إرسال تقييمك {stars}.",
        "es": "✅ ¡Gracias! Tu reseña {stars} ha sido enviada.",
        "fr": "✅ Merci ! Votre avis {stars} a été soumis.",
        "de": "✅ Vielen Dank! Ihre {stars}-Bewertung wurde gesendet.",
        "ru_lang": "✅ Спасибо! Ваш отзыв {stars} отправлен.",
        "zh": "✅ 谢谢！您的 {stars} 评价已提交。",
    },
    "rev_already": {
        "ar": "ℹ️ لقد قيّمت هذا المنتج بالفعل.",
        "es": "ℹ️ Ya has reseñado este producto.",
        "fr": "ℹ️ Vous avez déjà évalué ce produit.",
        "de": "ℹ️ Sie haben dieses Produkt bereits bewertet.",
        "ru_lang": "ℹ️ Вы уже оставили отзыв об этом товаре.",
        "zh": "ℹ️ 您已经评价过此产品。",
    },
    "rev_skip": {
        "ar": "⏭️ تخطي النص", "es": "⏭️ Omitir Texto", "fr": "⏭️ Passer le Texte",
        "de": "⏭️ Text Überspringen", "ru_lang": "⏭️ Пропустить текст", "zh": "⏭️ 跳过文本",
    },
    # ────────── LOYALTY TIERS ──────────
    "tier_bronze": {
        "ar": "🥉 برونزي", "es": "🥉 Bronce", "fr": "🥉 Bronze",
        "de": "🥉 Bronze", "ru_lang": "🥉 Бронза", "zh": "🥉 青铜",
    },
    "tier_silver": {
        "ar": "🥈 فضي", "es": "🥈 Plata", "fr": "🥈 Argent",
        "de": "🥈 Silber", "ru_lang": "🥈 Серебро", "zh": "🥈 白银",
    },
    "tier_gold": {
        "ar": "🥇 ذهبي", "es": "🥇 Oro", "fr": "🥇 Or",
        "de": "🥇 Gold", "ru_lang": "🥇 Золото", "zh": "🥇 黄金",
    },
    "tier_platinum": {
        "ar": "💎 بلاتيني", "es": "💎 Platino", "fr": "💎 Platine",
        "de": "💎 Platin", "ru_lang": "💎 Платина", "zh": "💎 铂金",
    },
    "tier_diamond": {
        "ar": "💠 ألماسي", "es": "💠 Diamante", "fr": "💠 Diamant",
        "de": "💠 Diamant", "ru_lang": "💠 Алмаз", "zh": "💠 钻石",
    },
    "tier_your": {
        "ar": "🏆 مستواك: ", "es": "🏆 Tu Nivel: ", "fr": "🏆 Votre Niveau : ",
        "de": "🏆 Ihre Stufe: ", "ru_lang": "🏆 Ваш уровень: ", "zh": "🏆 您的等级: ",
    },
    "tier_progress": {
        "ar": "📈 التقدم إلى المستوى التالي:",
        "es": "📈 Progreso al siguiente nivel:",
        "fr": "📈 Progression vers le niveau suivant :",
        "de": "📈 Fortschritt zur nächsten Stufe:",
        "ru_lang": "📈 Прогресс до следующего уровня:",
        "zh": "📈 下一等级进度:",
    },
    "tier_total_spent": {
        "ar": "💰 إجمالي الإنفاق: ", "es": "💰 Total Gastado: ", "fr": "💰 Total Dépensé : ",
        "de": "💰 Gesamtausgaben: ", "ru_lang": "💰 Всего потрачено: ", "zh": "💰 总消费: ",
    },
    "tier_total_orders": {
        "ar": "📦 إجمالي الطلبات: ", "es": "📦 Total de Pedidos: ", "fr": "📦 Total des Commandes : ",
        "de": "📦 Gesamtbestellungen: ", "ru_lang": "📦 Всего заказов: ", "zh": "📦 总订单数: ",
    },
    "tier_max": {
        "ar": "🎉 أنت في أعلى مستوى!",
        "es": "🎉 ¡Estás en el nivel más alto!",
        "fr": "🎉 Vous êtes au niveau le plus élevé !",
        "de": "🎉 Sie sind auf der höchsten Stufe!",
        "ru_lang": "🎉 Вы на самом высоком уровне!",
        "zh": "🎉 您已达到最高等级！",
    },
    "tier_benefits": {
        "ar": "🎁 مزاياك:", "es": "🎁 Tus Beneficios:", "fr": "🎁 Vos Avantages :",
        "de": "🎁 Ihre Vorteile:", "ru_lang": "🎁 Ваши преимущества:", "zh": "🎁 您的福利:",
    },
    "tier_upgraded": {
        "ar": "🎉 مبروك! تمت ترقيتك إلى مستوى {tier}!",
        "es": "🎉 ¡Felicidades! Has subido al nivel {tier}!",
        "fr": "🎉 Félicitations ! Vous êtes passé au niveau {tier} !",
        "de": "🎉 Glückwunsch! Sie wurden auf Stufe {tier} hochgestuft!",
        "ru_lang": "🎉 Поздравляем! Вы повышены до уровня {tier}!",
        "zh": "🎉 恭喜！您已升级到 {tier} 等级！",
    },
    # ────────── ANALYTICS ──────────
    "an_title": {
        "ar": "📊 لوحة التحليلات", "es": "📊 Panel de Analíticas", "fr": "📊 Tableau d'Analyse",
        "de": "📊 Analyse-Dashboard", "ru_lang": "📊 Панель аналитики", "zh": "📊 分析面板",
    },
    "an_today": {
        "ar": "📅 اليوم", "es": "📅 Hoy", "fr": "📅 Aujourd'hui",
        "de": "📅 Heute", "ru_lang": "📅 Сегодня", "zh": "📅 今天",
    },
    "an_week": {
        "ar": "📆 آخر 7 أيام", "es": "📆 Últimos 7 Días", "fr": "📆 7 Derniers Jours",
        "de": "📆 Letzte 7 Tage", "ru_lang": "📆 Последние 7 дней", "zh": "📆 最近 7 天",
    },
    "an_month": {
        "ar": "🗓️ آخر 30 يومًا", "es": "🗓️ Últimos 30 Días", "fr": "🗓️ 30 Derniers Jours",
        "de": "🗓️ Letzte 30 Tage", "ru_lang": "🗓️ Последние 30 дней", "zh": "🗓️ 最近 30 天",
    },
    "an_all_time": {
        "ar": "♾️ كل الأوقات", "es": "♾️ Todo el Tiempo", "fr": "♾️ Tout le Temps",
        "de": "♾️ Gesamte Zeit", "ru_lang": "♾️ За всё время", "zh": "♾️ 全部时间",
    },
    "an_top_products": {
        "ar": "🏆 أفضل المنتجات", "es": "🏆 Mejores Productos", "fr": "🏆 Meilleurs Produits",
        "de": "🏆 Top-Produkte", "ru_lang": "🏆 Лучшие товары", "zh": "🏆 热门产品",
    },
    "an_top_customers": {
        "ar": "👑 أفضل العملاء", "es": "👑 Mejores Clientes", "fr": "👑 Meilleurs Clients",
        "de": "👑 Top-Kunden", "ru_lang": "👑 Лучшие клиенты", "zh": "👑 最佳客户",
    },
    "an_payment_methods": {
        "ar": "💳 طرق الدفع", "es": "💳 Métodos de Pago", "fr": "💳 Méthodes de Paiement",
        "de": "💳 Zahlungsmethoden", "ru_lang": "💳 Способы оплаты", "zh": "💳 支付方式",
    },
    "an_revenue": {
        "ar": "💰 الإيرادات: ", "es": "💰 Ingresos: ", "fr": "💰 Revenus : ",
        "de": "💰 Umsatz: ", "ru_lang": "💰 Доход: ", "zh": "💰 收入: ",
    },
    "an_orders": {
        "ar": "🛒 الطلبات: ", "es": "🛒 Pedidos: ", "fr": "🛒 Commandes : ",
        "de": "🛒 Bestellungen: ", "ru_lang": "🛒 Заказы: ", "zh": "🛒 订单数: ",
    },
    "an_new_users": {
        "ar": "👥 مستخدمون جدد: ", "es": "👥 Nuevos Usuarios: ", "fr": "👥 Nouveaux Utilisateurs : ",
        "de": "👥 Neue Benutzer: ", "ru_lang": "👥 Новые пользователи: ", "zh": "👥 新用户: ",
    },
    "an_avg_order": {
        "ar": "💵 متوسط قيمة الطلب: ", "es": "💵 Valor Promedio: ", "fr": "💵 Valeur Moyenne : ",
        "de": "💵 Durchschnittswert: ", "ru_lang": "💵 Средний заказ: ", "zh": "💵 平均订单额: ",
    },
    "an_conversion": {
        "ar": "📈 معدل التحويل: ", "es": "📈 Tasa de Conversión: ", "fr": "📈 Taux de Conversion : ",
        "de": "📈 Konversionsrate: ", "ru_lang": "📈 Конверсия: ", "zh": "📈 转化率: ",
    },
    "an_no_data": {
        "ar": "📭 لا توجد بيانات بعد", "es": "📭 Aún no hay datos", "fr": "📭 Pas encore de données",
        "de": "📭 Noch keine Daten", "ru_lang": "📭 Пока нет данных", "zh": "📭 暂无数据",
    },
    "stars_5": {
        "ar": "⭐⭐⭐⭐⭐", "es": "⭐⭐⭐⭐⭐", "fr": "⭐⭐⭐⭐⭐",
        "de": "⭐⭐⭐⭐⭐", "ru_lang": "⭐⭐⭐⭐⭐", "zh": "⭐⭐⭐⭐⭐",
    },
}

# fill in missing language entries at load time (existing keys keep their
# current values; only missing langs are added)
for _key, _entries in LANG_FILL.items():
    _base = TRANSLATIONS.get(_key)
    if not _base:
        TRANSLATIONS[_key] = {}
        _base = TRANSLATIONS[_key]
    for _lang, _txt in _entries.items():
        if _lang not in _base:
            _base[_lang] = _txt

_lang_cache = {}

def get_user_lang(user_id):
    """Get user's preferred language. Falls back to DEFAULT_LANG."""
    if not user_id:
        return DEFAULT_LANG
    if user_id in _lang_cache:
        return _lang_cache[user_id]
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
        r = c.fetchone(); conn.close()
        lang = DEFAULT_LANG
        if r and r['language'] and r['language'] in LANGUAGES:
            lang = r['language']
        _lang_cache[user_id] = lang
        return lang
    except Exception:
        pass
    return DEFAULT_LANG

def set_user_lang(user_id, lang):
    """Set user's preferred language."""
    if lang not in LANGUAGES:
        return False
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))
        conn.commit(); conn.close()
        _lang_cache[user_id] = lang
        return True
    except Exception:
        return False

def t(key, user_id=None, lang=None, **kwargs):
    if lang is None and user_id is not None:
        lang = get_user_lang(user_id)
    if lang is None:
        lang = DEFAULT_LANG

    entry = TRANSLATIONS.get(key)
    if not entry:
        return key

    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key

    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text

def lang_name(lang_code):
    info = LANGUAGES.get(lang_code, {})
    return f"{info.get('flag', '')} {info.get('native', lang_code)}"
