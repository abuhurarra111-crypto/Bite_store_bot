# ============================================================
# 🌍 v79: User-facing TEXT TEMPLATE translations (per language)
# ============================================================
# This module provides translations for DEFAULT_RESPONSES keys.
# When a user has set their language (via 🌐 Language), the bot looks up
# the key here first → if a translation exists for that user's language,
# it's used. Otherwise it falls back to the admin-customizable English
# template in config.DEFAULT_RESPONSES.
#
# Supported langs (matches i18n.py): en, ur, ru (Roman Urdu), hi, ar,
# es, fr, ru_lang (Russian), zh, de.
#
# Admins still control the English baseline. Translations here are baked-in
# defaults — users who pick non-English get a native experience automatically.
# ============================================================

# Each key maps to a dict of {lang_code → translated text}.
# 'en' entries are optional (fallback to DEFAULT_RESPONSES). We include them
# only for safety.
RESPONSE_TRANSLATIONS = {
    # ─────────── 🏠 WELCOME / MAIN MENU ───────────
    "welcome": {
        "ur":  """🛍️ {shop_name} میں خوش آمدید!

━━━━━━━━━━━━━━━━━━━━

🆔 آپ کا یوزر آئی ڈی: {user_id}

⚡ Binance Pay سے ادائیگی کریں – خودکار تصدیق""",
        "ru":  """🛍️ {shop_name} mein khush amdeed!

━━━━━━━━━━━━━━━━━━━━

🆔 Aap ka User ID: {user_id}

⚡ Binance Pay sy payment karein – Automatic Verify""",
        "hi":  """🛍️ {shop_name} mein swagat hai!

━━━━━━━━━━━━━━━━━━━━

🆔 Aapka User ID: {user_id}

⚡ Binance Pay se payment karo – Auto Verify""",
        "ar":  """🛍️ مرحبًا بك في {shop_name}!

━━━━━━━━━━━━━━━━━━━━

🆔 معرف المستخدم: {user_id}

⚡ ادفع عبر Binance Pay – تحقق تلقائي""",
        "es":  """🛍️ ¡Bienvenido a {shop_name}!

━━━━━━━━━━━━━━━━━━━━

🆔 Tu ID de usuario: {user_id}

⚡ Paga con Binance Pay – Verificación automática""",
        "fr":  """🛍️ Bienvenue chez {shop_name} !

━━━━━━━━━━━━━━━━━━━━

🆔 Votre ID utilisateur : {user_id}

⚡ Payez via Binance Pay – Vérification automatique""",
        "ru_lang": """🛍️ Добро пожаловать в {shop_name}!

━━━━━━━━━━━━━━━━━━━━

🆔 Ваш ID пользователя: {user_id}

⚡ Оплата через Binance Pay – автоматическая проверка""",
        "zh":  """🛍️ 欢迎来到 {shop_name}！

━━━━━━━━━━━━━━━━━━━━

🆔 您的用户 ID: {user_id}

⚡ 通过 Binance Pay 支付 – 自动验证""",
        "de":  """🛍️ Willkommen bei {shop_name}!

━━━━━━━━━━━━━━━━━━━━

🆔 Ihre Benutzer-ID: {user_id}

⚡ Bezahlen via Binance Pay – Automatische Verifizierung""",
    },

    "my_account": {
        "ur":  """📊 *میرا اکاؤنٹ*
━━━━━━━━━━━━━━━━━━━━

👤 نام: *{name}*
🆔 یوزر آئی ڈی: `{user_id}`
📛 یوزر نیم: @{username}
💎 پوائنٹس: *{points}*
👥 ریفرلز: *{referrals}*
📅 شامل ہوئے: {joined}""",
        "ru":  """📊 *Mera Account*
━━━━━━━━━━━━━━━━━━━━

👤 Naam: *{name}*
🆔 User ID: `{user_id}`
📛 Username: @{username}
💎 Points: *{points}*
👥 Referrals: *{referrals}*
📅 Join Kiya: {joined}""",
        "hi":  """📊 *Mera Account*
━━━━━━━━━━━━━━━━━━━━

👤 Naam: *{name}*
🆔 User ID: `{user_id}`
📛 Username: @{username}
💎 Points: *{points}*
👥 Referrals: *{referrals}*
📅 Join Kiya: {joined}""",
        "ar":  """📊 *حسابي*
━━━━━━━━━━━━━━━━━━━━

👤 الاسم: *{name}*
🆔 معرف المستخدم: `{user_id}`
📛 اسم المستخدم: @{username}
💎 النقاط: *{points}*
👥 الإحالات: *{referrals}*
📅 تاريخ الانضمام: {joined}""",
        "es":  """📊 *Mi Cuenta*
━━━━━━━━━━━━━━━━━━━━

👤 Nombre: *{name}*
🆔 ID de usuario: `{user_id}`
📛 Usuario: @{username}
💎 Puntos: *{points}*
👥 Referidos: *{referrals}*
📅 Se unió: {joined}""",
        "fr":  """📊 *Mon Compte*
━━━━━━━━━━━━━━━━━━━━

👤 Nom : *{name}*
🆔 ID utilisateur : `{user_id}`
📛 Nom d'utilisateur : @{username}
💎 Points : *{points}*
👥 Parrainages : *{referrals}*
📅 Inscrit : {joined}""",
        "ru_lang": """📊 *Мой Аккаунт*
━━━━━━━━━━━━━━━━━━━━

👤 Имя: *{name}*
🆔 ID пользователя: `{user_id}`
📛 Имя пользователя: @{username}
💎 Очки: *{points}*
👥 Рефералы: *{referrals}*
📅 Дата регистрации: {joined}""",
        "zh":  """📊 *我的账户*
━━━━━━━━━━━━━━━━━━━━

👤 姓名: *{name}*
🆔 用户 ID: `{user_id}`
📛 用户名: @{username}
💎 积分: *{points}*
👥 推荐人数: *{referrals}*
📅 加入日期: {joined}""",
        "de":  """📊 *Mein Konto*
━━━━━━━━━━━━━━━━━━━━

👤 Name: *{name}*
🆔 Benutzer-ID: `{user_id}`
📛 Benutzername: @{username}
💎 Punkte: *{points}*
👥 Empfehlungen: *{referrals}*
📅 Beigetreten: {joined}""",
    },

    # ─────────── 🛒 SHOP ───────────
    "shop_title": {
        "ur": "🛍️ پروڈکٹ کی فہرست\n(صفحہ {page}/{total_pages})",
        "ru": "🛍️ Product List\n(Page {page}/{total_pages})",
        "hi": "🛍️ Product List\n(Page {page}/{total_pages})",
        "ar": "🛍️ قائمة المنتجات\n(صفحة {page}/{total_pages})",
        "es": "🛍️ Lista de Productos\n(Página {page}/{total_pages})",
        "fr": "🛍️ Liste des Produits\n(Page {page}/{total_pages})",
        "ru_lang": "🛍️ Список Товаров\n(Страница {page}/{total_pages})",
        "zh": "🛍️ 产品列表\n(第 {page}/{total_pages} 页)",
        "de": "🛍️ Produktliste\n(Seite {page}/{total_pages})",
    },

    "shop_categories_title": {
        "ur":  "🛍️ *دکان — زمرے*\n━━━━━━━━━━━━━━━━━━━━\n\nبراؤز کرنے کے لیے زمرہ منتخب کریں:",
        "ru":  "🛍️ *Shop — Categories*\n━━━━━━━━━━━━━━━━━━━━\n\nBrowse k liye category select karein:",
        "hi":  "🛍️ *Shop — Categories*\n━━━━━━━━━━━━━━━━━━━━\n\nBrowse karne ke liye category choose karo:",
        "ar":  "🛍️ *المتجر — الفئات*\n━━━━━━━━━━━━━━━━━━━━\n\nاختر فئة للتصفح:",
        "es":  "🛍️ *Tienda — Categorías*\n━━━━━━━━━━━━━━━━━━━━\n\nSelecciona una categoría:",
        "fr":  "🛍️ *Boutique — Catégories*\n━━━━━━━━━━━━━━━━━━━━\n\nSélectionnez une catégorie :",
        "ru_lang": "🛍️ *Магазин — Категории*\n━━━━━━━━━━━━━━━━━━━━\n\nВыберите категорию:",
        "zh":  "🛍️ *商店 — 分类*\n━━━━━━━━━━━━━━━━━━━━\n\n选择一个分类浏览:",
        "de":  "🛍️ *Shop — Kategorien*\n━━━━━━━━━━━━━━━━━━━━\n\nWähle eine Kategorie:",
    },

    "product_detail": {
        "ur":  "📦 *{name}*\n━━━━━━━━━━━━━━━━━━━━\n\n📝 {description}\n\n💰 قیمت: *${price}* ≈ *{pkr}*\n📊 اسٹاک میں: *{stock}*",
        "ru":  "📦 *{name}*\n━━━━━━━━━━━━━━━━━━━━\n\n📝 {description}\n\n💰 Price: *${price}* ≈ *{pkr}*\n📊 Stock Available: *{stock}*",
        "hi":  "📦 *{name}*\n━━━━━━━━━━━━━━━━━━━━\n\n📝 {description}\n\n💰 Price: *${price}* ≈ *{pkr}*\n📊 Stock me hai: *{stock}*",
        "ar":  "📦 *{name}*\n━━━━━━━━━━━━━━━━━━━━\n\n📝 {description}\n\n💰 السعر: *${price}* ≈ *{pkr}*\n📊 المخزون: *{stock}*",
        "es":  "📦 *{name}*\n━━━━━━━━━━━━━━━━━━━━\n\n📝 {description}\n\n💰 Precio: *${price}* ≈ *{pkr}*\n📊 En Stock: *{stock}*",
        "fr":  "📦 *{name}*\n━━━━━━━━━━━━━━━━━━━━\n\n📝 {description}\n\n💰 Prix : *${price}* ≈ *{pkr}*\n📊 En Stock : *{stock}*",
        "ru_lang": "📦 *{name}*\n━━━━━━━━━━━━━━━━━━━━\n\n📝 {description}\n\n💰 Цена: *${price}* ≈ *{pkr}*\n📊 На складе: *{stock}*",
        "zh":  "📦 *{name}*\n━━━━━━━━━━━━━━━━━━━━\n\n📝 {description}\n\n💰 价格: *${price}* ≈ *{pkr}*\n📊 库存: *{stock}*",
        "de":  "📦 *{name}*\n━━━━━━━━━━━━━━━━━━━━\n\n📝 {description}\n\n💰 Preis: *${price}* ≈ *{pkr}*\n📊 Auf Lager: *{stock}*",
    },

    "no_products": {
        "ur": "😔 ابھی کوئی پروڈکٹ دستیاب نہیں۔\nجلد دوبارہ چیک کریں!",
        "ru": "😔 Abhi koi product available nahi.\nThodi der baad check karein!",
        "hi": "😔 Abhi koi product available nahi.\nThodi der baad check karo!",
        "ar": "😔 لا توجد منتجات متاحة حاليًا.\nيُرجى المراجعة لاحقًا!",
        "es": "😔 No hay productos disponibles aún.\n¡Vuelve pronto!",
        "fr": "😔 Aucun produit disponible pour le moment.\nRevenez bientôt !",
        "ru_lang": "😔 Пока нет товаров в наличии.\nЗайдите позже!",
        "zh": "😔 暂无产品。\n请稍后再来！",
        "de": "😔 Noch keine Produkte verfügbar.\nSchauen Sie bald wieder vorbei!",
    },

    "out_of_stock": {
        "ur": "😔 اسٹاک ختم!",
        "ru": "😔 Stock khatam!",
        "hi": "😔 Stock khatam!",
        "ar": "😔 نفد المخزون!",
        "es": "😔 ¡Agotado!",
        "fr": "😔 En rupture de stock !",
        "ru_lang": "😔 Нет в наличии!",
        "zh": "😔 缺货！",
        "de": "😔 Ausverkauft!",
    },

    "confirm_purchase": {
        "ur":  "🛒 *خریداری کی تصدیق*\n━━━━━━━━━━━━━━━━━━━━\n📦 *{product}*\n💰 قیمت: *${price}* ≈ *{pkr}*\n📦 مقدار: *1*\n\nادائیگی کا طریقہ منتخب کریں:",
        "ru":  "🛒 *Confirm Purchase*\n━━━━━━━━━━━━━━━━━━━━\n📦 *{product}*\n💰 Price: *${price}* ≈ *{pkr}*\n📦 Quantity: *1*\n\nPayment method select karein:",
        "hi":  "🛒 *Confirm Purchase*\n━━━━━━━━━━━━━━━━━━━━\n📦 *{product}*\n💰 Price: *${price}* ≈ *{pkr}*\n📦 Quantity: *1*\n\nPayment method choose karo:",
        "ar":  "🛒 *تأكيد الشراء*\n━━━━━━━━━━━━━━━━━━━━\n📦 *{product}*\n💰 السعر: *${price}* ≈ *{pkr}*\n📦 الكمية: *1*\n\nاختر طريقة الدفع:",
        "es":  "🛒 *Confirmar Compra*\n━━━━━━━━━━━━━━━━━━━━\n📦 *{product}*\n💰 Precio: *${price}* ≈ *{pkr}*\n📦 Cantidad: *1*\n\nSelecciona método de pago:",
        "fr":  "🛒 *Confirmer l'achat*\n━━━━━━━━━━━━━━━━━━━━\n📦 *{product}*\n💰 Prix : *${price}* ≈ *{pkr}*\n📦 Quantité : *1*\n\nChoisissez un mode de paiement :",
        "ru_lang": "🛒 *Подтвердить покупку*\n━━━━━━━━━━━━━━━━━━━━\n📦 *{product}*\n💰 Цена: *${price}* ≈ *{pkr}*\n📦 Количество: *1*\n\nВыберите способ оплаты:",
        "zh":  "🛒 *确认购买*\n━━━━━━━━━━━━━━━━━━━━\n📦 *{product}*\n💰 价格: *${price}* ≈ *{pkr}*\n📦 数量: *1*\n\n选择付款方式:",
        "de":  "🛒 *Kauf Bestätigen*\n━━━━━━━━━━━━━━━━━━━━\n📦 *{product}*\n💰 Preis: *${price}* ≈ *{pkr}*\n📦 Menge: *1*\n\nZahlungsmethode wählen:",
    },

    # Add more keys as needed — these are the 8 most-visible. Other keys will
    # fall back to admin-customizable English from config.DEFAULT_RESPONSES.
}


def get_translated_response(key: str, user_id=None, lang=None) -> str:
    """Look up a translated DEFAULT_RESPONSES entry.

    Returns:
        - Translated string if key + lang exists in RESPONSE_TRANSLATIONS
        - None otherwise (caller should fall back to admin-customizable English)
    """
    if lang is None and user_id is not None:
        try:
            from i18n import get_user_lang
            lang = get_user_lang(user_id)
        except Exception:
            lang = "en"
    if not lang or lang == "en":
        return None
    entry = RESPONSE_TRANSLATIONS.get(key)
    if not entry:
        return None
    return entry.get(lang)
