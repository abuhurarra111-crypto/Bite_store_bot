# ============================================
# 🌍 INTERNATIONALIZATION (i18n)
# ============================================
from database import get_connection

# ── Supported languages ──
LANGUAGES = {
    "en": {"name": "English",     "flag": "🇬🇧", "native": "English"},
    "ur": {"name": "Urdu",        "flag": "🇵🇰", "native": "اردو"},
    "ru": {"name": "Roman Urdu",  "flag": "🇵🇰", "native": "Roman Urdu"},
    "hi": {"name": "Hinglish",    "flag": "🇮🇳", "native": "Hinglish"},
    "ar": {"name": "Arabic",      "flag": "🇸🇦", "native": "العربية"},
    "es": {"name": "Spanish",     "flag": "🇪🇸", "native": "Español"},
    "fr": {"name": "French",      "flag": "🇫🇷", "native": "Français"},
    "ru_lang": {"name": "Russian", "flag": "🇷🇺", "native": "Русский"},
    "zh": {"name": "Chinese",     "flag": "🇨🇳", "native": "中文"},
    "de": {"name": "German",      "flag": "🇩🇪", "native": "Deutsch"},
}

DEFAULT_LANG = "en"

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
    "menu_shop":           {"en": "🛍️ Shop",           "ur": "🛍️ دکان",         "ru": "🛍️ Shop",        "hi": "🛍️ Shop"},
    "menu_my_orders":      {"en": "📦 My Orders",      "ur": "📦 میرے آرڈرز",    "ru": "📦 Mere Orders",  "hi": "📦 Mere Orders"},
    "menu_my_account":     {"en": "👤 My Account",     "ur": "👤 میرا اکاؤنٹ",    "ru": "👤 Mera Account", "hi": "👤 Mera Account"},
    "menu_buy_points":     {"en": "💎 Buy Points",     "ur": "💎 پوائنٹس خریدیں", "ru": "💎 Points Khareedo", "hi": "💎 Points Khareedo"},
    "menu_referral":       {"en": "🎁 Referral",       "ur": "🎁 ریفرل",          "ru": "🎁 Referral",     "hi": "🎁 Referral"},
    "menu_transactions":   {"en": "📜 Transactions",   "ur": "📜 لین دین",        "ru": "📜 Transactions", "hi": "📜 Transactions"},
    "menu_support":        {"en": "🎫 Support",        "ur": "🎫 سپورٹ",          "ru": "🎫 Support",      "hi": "🎫 Support"},
    "menu_warranty":       {"en": "🛡️ Warranty/Refund","ur": "🛡️ وارنٹی/ریفنڈ",  "ru": "🛡️ Warranty/Refund", "hi": "🛡️ Warranty/Refund"},
    "menu_reviews":        {"en": "⭐ Reviews",         "ur": "⭐ جائزے",          "ru": "⭐ Reviews",      "hi": "⭐ Reviews"},
    "menu_loyalty":        {"en": "🏆 Loyalty",         "ur": "🏆 لائلٹی",         "ru": "🏆 Loyalty",      "hi": "🏆 Loyalty"},
    "menu_admin":          {"en": "👑 Admin Panel",    "ur": "👑 ایڈمن پینل",     "ru": "👑 Admin Panel",  "hi": "👑 Admin Panel"},
    "menu_language":       {"en": "🌐 Language",       "ur": "🌐 زبان",           "ru": "🌐 Language",     "hi": "🌐 Language"},

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
