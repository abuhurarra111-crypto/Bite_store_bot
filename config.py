# ============================================
# ⚙️ BOT SETTINGS
# ============================================
import os

# Load .env BEFORE reading any config values.
# Secrets must live in environment variables or a local .env file.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _env_str(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)).strip() or default)
    except (TypeError, ValueError):
        return default


# 🔐 Required secrets — DO NOT hardcode real values here.
BOT_TOKEN = _env_str("BOT_TOKEN")
ADMIN_ID = _env_int("ADMIN_ID", 0)


def validate_required_config():
    """Raise a clear error when required runtime secrets are missing."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not ADMIN_ID:
        missing.append("ADMIN_ID")
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing) +
            ". Create a local .env from .env.example or set them in hosting dashboard."
        )


# ☁️ FREE TELEGRAM CLOUD BACKUP
# Bot will auto-send the shop.db database file to this chat/channel on a schedule,
# so your data is always safe in Telegram's free unlimited storage.
# HOW TO SET UP:
#   1. Make a NEW PRIVATE Telegram channel (e.g. "My Bot Backups").
#   2. Add your bot as an ADMIN of that channel (with "Post Messages" right).
#   3. Forward any message from the channel to @userinfobot to get its ID
#      (looks like -1001234567890), OR leave 0 to send backups to your own DM (ADMIN_ID).
#   4. Paste the ID below.
# Set to 0 to send backups to the admin's private chat instead.
# 🔧 AUDIT-FIX M3 (2026-07-31): all business values below are now
# env-overridable (e.g. BACKUP_CHANNEL_ID=-100123456789) while keeping the
# original defaults when the variable is not set — zero behavior change for
# existing deployments. Payment numbers still honor their bot_settings
# overrides (easypaisa / jazzcash / binance_name / account_name) first.
BACKUP_CHANNEL_ID = _env_int("BACKUP_CHANNEL_ID", 0)
# How often to auto-backup (in hours). v120: owner requested every 3 hours.
BACKUP_INTERVAL_HOURS = max(1, _env_int("BACKUP_INTERVAL_HOURS", 3))

# 💰 Payment
EASYPAISA_NUMBER = _env_str("EASYPAISA_NUMBER", "923193840214")
JAZZCASH_NUMBER = _env_str("JAZZCASH_NUMBER", "923193840214")
ACCOUNT_NAME = _env_str("ACCOUNT_NAME", "Zayam Iqbal")

# 🔶 Binance
BINANCE_PAY_ID = _env_str("BINANCE_PAY_ID", "887012522")

# 🤖 Gemini AI (for AI Admin Assistant)
# RECOMMENDED: Put this in .env file instead of here
# Get key from: https://aistudio.google.com/app/apikey
GEMINI_API_KEY = _env_str("GEMINI_API_KEY")

# 💱 Currency Conversion (USD → PKR)
# Admin can change this from Settings panel
USD_TO_PKR_RATE = 300

# 🔶 Binance API (Read-Only) — v24
# RECOMMENDED: Put these in .env file instead of here
# Create API key at: https://www.binance.com/en/my/settings/api-management
# ⚠️ Enable ONLY "Read Info" permission — NO trade, NO withdraw
BINANCE_API_KEY = _env_str("BINANCE_API_KEY")
BINANCE_API_SECRET = _env_str("BINANCE_API_SECRET")

# 📧 Gmail credentials for EasyPaisa auto-verify (v25)
# RECOMMENDED: Put these in .env file
# Use Gmail App Password (NOT regular password):
# https://myaccount.google.com/apppasswords
EMAIL_ADDRESS = _env_str("EMAIL_ADDRESS")
EMAIL_PASSWORD = _env_str("EMAIL_PASSWORD")

# 📧 Binance Gmail credentials (Gmail auto-verify for Binance Pay)
# RECOMMENDED: Put these in .env file
# Binance payment notification emails come to this Gmail
BINANCE_EMAIL = _env_str("BINANCE_EMAIL")
BINANCE_EMAIL_PASSWORD = _env_str("BINANCE_EMAIL_PASSWORD")

# 🏪 Shop
SHOP_NAME = "BITE STORE"

# 📞 Support
WHATSAPP_NUMBER = _env_str("WHATSAPP_NUMBER", "923193840214")
SUPPORT_EMAIL = _env_str("SUPPORT_EMAIL", "trendbiteservices@gmail.com")

# 🎁 Referral
REFERRAL_POINTS = 1
POINTS_PER_DOLLAR = 10

# 💬 DEFAULT RESPONSES
DEFAULT_RESPONSES = {
    # ══════════════════════════════════════
    # 🏠 MAIN MENU & NAVIGATION
    # ══════════════════════════════════════
    "welcome": """🛍️ Welcome to {shop_name}!

━━━━━━━━━━━━━━━━━━━━

🆔 Account User ID: {user_id}

⚡ Pay via Binance Pay – Automatic Verification""",

    # 🆕 v138: shown AFTER the user taps "I Joined — Verify" (editable,
    # premium emoji allowed, auto-deletes after 5 seconds from user chat).
    "fj_verified_done": """✅ *Verified!*

Welcome to *{shop_name}*! 🛍️

You're all set to use the bot.""",

    "my_account": """📊 *My Account*
━━━━━━━━━━━━━━━━━━━━

👤 Name: *{name}*
🆔 User ID: `{user_id}`
📛 Username: @{username}
💎 Points: *{points}*
👥 Referrals: *{referrals}*
📅 Joined: {joined}""",

    # ══════════════════════════════════════
    # 🛒 SHOP & PRODUCTS
    # ══════════════════════════════════════
    "shop_title": "🛍️ Product List\n(Page {page}/{total_pages})",

    "shop_categories_title": """📁 *Categories*

_Pick a category to browse._""",

    "product_detail": """📦 *{name}*
━━━━━━━━━━━━━━━━━━━━

📝 {description}

💰 Price: *${price}* ≈ *{pkr}*
📊 In Stock: *{stock}*""",

    "no_products": "😔 No products available yet.\nCheck back soon!",

    "out_of_stock": "😔 Out of stock!",

    "confirm_purchase": """🛒 *Confirm Purchase*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*
💰 Price: *${price}* ≈ *{pkr}*
📦 Quantity: *1*

Select payment method:""",

    "confirm_bulk_purchase": """🛒× *Buy Multiple*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*
💰 Unit Price: *${price}* ≈ *{pkr}*
📊 Stock Available: *{stock}*

📝 Type quantity (number):
*Example: 5*

Max: {stock} (current stock)""",

    "bulk_confirmed": """🛒× *Confirm Bulk Purchase*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*
💰 Unit Price: ${unit_price}
📦 Quantity: *{qty}*
━━━━━━━━━━━━━━━━━━━━
💵 *Total: ${total}* ≈ *{pkr}*

Select payment method:""",

    # ══════════════════════════════════════
    # 💳 PAYMENT SCREENS
    # ══════════════════════════════════════
    "buy_points": """💎 *Buy Points*
━━━━━━━━━━━━━━━━━━━━

💎 Your Points: *{points}*
💰 Rate: $1 = {rate} Points

Select payment method:""",

    "payment_verified_points": """🎉 *Payment Verified!* ✅
━━━━━━━━━━━━━━━━━━━━

💎 *{pts} Points* added to your account!

💰 Amount: ${amount} {currency}
🆔 Order ID: `{order_id}`

📊 Tap 'My Account' to see new balance.
Thank you! 🙏""",

    "payment_verified_product": """🎉 *Order #{order_id} Delivered!* ✅
━━━━━━━━━━━━━━━━━━━━

📦 {product}

📨 *Your Product:*
━━━━━━━━━━━━━━━━━━
{delivery}
━━━━━━━━━━━━━━━━━━

💎 +{points} points earned!
Thank you! 🙏""",

    # ══════════════════════════════════════
    # ✅ VERIFICATION SUCCESS MESSAGES
    # ══════════════════════════════════════

    # ══════════════════════════════════════
    # ❌ ERROR MESSAGES
    # ══════════════════════════════════════

    "order_rejected": "❌ Order #{order_id} was rejected.\nContact support for help.",

    # ══════════════════════════════════════
    # 💎 POINTS & REFERRALS
    # ══════════════════════════════════════
    "referral_text": """🎁 *Referral Program*
━━━━━━━━━━━━━━━━━━━━

🔗 Your Link:
`{ref_link}`

👥 Referrals: *{ref_count}*
💎 Points Earned: *{ref_points}*

📋 Share → They join → You get *{points_per_ref} point*!""",

    # ══════════════════════════════════════
    # 📜 HISTORY & TRANSACTIONS
    # ══════════════════════════════════════
    "no_transactions": "🔄 *No deposits yet!*\n\nUse 💎 Buy Points to deposit funds.",

    "no_orders": "📜 *No orders yet!*",

    "orders_title": "📜 *Order History:*\n━━━━━━━━━━━━━━━━━━━━",

    # ══════════════════════════════════════
    # 📞 SUPPORT & TERMS
    # ══════════════════════════════════════
    "support_text": """👨‍💼 *Contact Support*
━━━━━━━━━━━━━━━━━━━━

Choose your preferred method:""",

    "terms": """📜 *Terms & Conditions*
━━━━━━━━━━━━━━━━━━━━

1. All sales are final — no refunds
2. Digital products delivered instantly
3. Do not share purchased items
4. Payment within 30 minutes

*Last updated: May 2026*""",

    # ══════════════════════════════════════
    # 📱 EASYPAISA TID FLOW
    # ══════════════════════════════════════

    # ══════════════════════════════════════
    # 📸 SCREENSHOT UPLOAD
    # ══════════════════════════════════════

    "binance_instructions": """⚠️ *Important:*
• Please enter your *exact Binance sender name*
• Pay the *exact* amount
• After payment, tap *Verify Payment*
• If not verified, try again after *1 minute*""",

    # ══════════════════════════════════════
    # 🛒 ADMIN NOTIFICATIONS (sent to users by bot)
    # ══════════════════════════════════════
    "new_user_notification": """👤 *New User Joined!*
Name: {name}
Username: @{username}
ID: `{user_id}`""",

    "cancelled_message": "❌ *Cancelled.*\n\nReturned to main menu.",
    # 🆕 v46: editable headers for previously-hardcoded feature screens.
    # Placeholders in {curly braces} are filled by the bot — keep them.
    "support_menu_header": "🎫 *Support Center*\n━━━━━━━━━━━━━━━━━━━━\n\nNeed help? Create a support ticket!\n📞 *WhatsApp Support:* `+{whatsapp}`\n\n📋 *Your Tickets:* {total} total\n🟡 *Open:* {open}\n\nChoose an option:",
    "warranty_menu_header": "🛡️ *Warranty & Refund*\n━━━━━━━━━━━━━━━━━━━━\n\nSelect an order:\n",
    "warranty_no_orders": "🛡️ *Warranty & Refund*\n━━━━━━━━━━━━━━━━━━━━\n\nNo delivered orders found.\nYou can request warranty/refund for delivered orders only.",
    "reviews_menu_header": "⭐ *Reviews & Ratings*\n━━━━━━━━━━━━━━━━━━━━\n\n📝 My reviews: {my}\n✍️ Pending to review: {pending}\n\nShare your experience and help others!",
    "loyalty_menu_header": "🏆 *Loyalty Program*\n━━━━━━━━━━━━━━━━━━━━\n",
    "language_menu_header": "🌐 *Choose Your Language*\n━━━━━━━━━━━━━━━━━━━━\n\nSelect your preferred language:",

    # ══════════════════════════════════════
    # 🎁 FREE CLAIM (via Referrals) — v47
    # ══════════════════════════════════════
    "freeclaim_user_screen": "🎁 *Get this product FREE!*\n\n📦 *{product}*\n👥 Required Referrals: *{required}*\n✅ Your Available Referrals: *{available}*\n\n🎉 *You're eligible!* Tap *Claim Now* to receive your product instantly.",
    "freeclaim_not_enough":  "🎁 *Get this product FREE!*\n\n📦 *{product}*\n👥 Required Referrals: *{required}*\n📊 Your Available Referrals: *{available}*\n📉 Need *{missing}* more referrals.\n\n🔗 Share your referral link with friends — when they /start the bot, your referral count goes up!",

    # ══════════════════════════════════════
    # 🆕 v170.13 — Freebies (free products for every user)
    # ══════════════════════════════════════
    "freebies_menu_header": "🎁 *Freebies*\n━━━━━━━━━━━━━━━━━━━━\n\n_These products are 100% FREE — claim yours now!_",
    "freebies_empty": "🎁 *Freebies*\n━━━━━━━━━━━━━━━━━━━━\n\n_No free products available right now. Check back soon!_",
    "freebie_success": "🎉 *Freebie Claimed!*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 {product}\n✅ Delivered FREE above.\n\n🔁 To claim again: {reclaim} referrals.",
    "freebie_need_refs": "🔁 To claim again you need *{required} referrals*.\n👥 Your referrals: *{have}*\n⭐ You need *{missing}* more.",
    "freebie_claim_limit": "❌ You reached the claim limit for this product.",
    "freebie_out_of_stock": "😔 Out of stock right now. Please try later.",

    # ══════════════════════════════════════
    # 🆕 v48 — Smart Share + Referral Points
    # ══════════════════════════════════════
    "freeclaim_share_message": "🎁 I'm getting {product} for FREE on {shop}!\n\nWant one too? Super easy:\n1️⃣ Click my link below\n2️⃣ Open it in Telegram\n3️⃣ Tap Start — and you're in!\n\n👇 My personal link:\n{link}",
    "freeclaim_share_screen": "🔗 *Your Personal Share Link*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 *{product}*\n🎁 Need: *{required}* referrals\n📊 You have: *{available}*\n\n🔗 *Long-press to copy your link:*\n`{link}`\n\n📲 *Or use the share buttons below* — pick any platform.\n_When anyone clicks your link & starts the bot, you instantly get *1 Referral Point*!_\n\n📝 *Preview of share message:*\n```\n{preview}\n```",

    # ══════════════════════════════════════
    # 🆕 v59: Shop stock-based filter (All / Available / Unavailable)
    # ══════════════════════════════════════
    "shop_no_unavailable": "✅ *Great news!*\n━━━━━━━━━━━━━━━━━━━━\n\nThere are no out-of-stock products right now — everything is available!\n\nTap *📋 Show All Products* below to see what's in store.",
    "shop_no_available":   "😔 *All products currently out of stock.*\n━━━━━━━━━━━━━━━━━━━━\n\nWe're restocking soon! Tap *📋 Show All Products* to see what's coming back, or check the out-of-stock list to set up 🔔 stock alerts.",

    # ══════════════════════════════════════
    # 🆕 v68: Missing responses from v62–v67
    # (Editable via Admin → ⚙️ Settings → ✏️ Edit Responses)
    # ══════════════════════════════════════

    # 🆕 v62: Binance Order-ID flow texts
    "binance_orderid_instructions": "🟡 *Binance Pay Checkout*\n━━━━━━━━━━━━━━━━━━━━\n\n{title}\n💵 Amount: *${amount}*\n\n📋 *Step 1 — Send the payment*\n  • Pay ID:  `{pay_id}`\n  • Name:    *{holder}*\n  • Amount:  *${amount}*\n\n📨 *Step 2 — Send your Order ID*\nAfter completing the payment, open the transaction in your Binance app, copy the *Order ID*, and paste it below.\n\n_Your order will be confirmed automatically within a few seconds._",

    # 🆕 v65: Refund + Cancel texts
    "refund_processed": "💸 *Refund Processed*\n━━━━━━━━━━━━━━━━━━━━\n\nThis product is currently unavailable, so your payment is being refunded.\n\n📦 Order: `#{order_id}`\n📌 Product: *{product}*\n💰 Amount: *${amount}*\n\n✅ *{points} Points have been credited* to your wallet as an instant refund.\n💎 New balance: *{new_balance} Points*\n\nYou can use these Points to buy other products in the store. We apologise for the inconvenience.",
    "order_cancelled_with_reason": "❌ *Order Cancelled*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Order: `#{order_id}`\n📌 Product: *{product}*\n💰 Amount: `${amount}`\n\n📋 *Reason from the store:*\n_{reason}_\n\nIf you have already paid, please contact support to arrange a refund.",
    "order_cancelled_no_reason":   "❌ *Order Cancelled*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Order: `#{order_id}`\n📌 Product: *{product}*\n💰 Amount: `${amount}`\n\nYour order has been cancelled. If you have already paid, please contact support to arrange a refund.",

    # 🆕 v68: Default tier upgrade message (when admin hasn't set custom)
}

# 🆕 v148: Editable payment screen texts (auto-registered in bot_responses)
DEFAULT_RESPONSES.update({
    "payment_binance_menu_text": """🔶 *Binance Payment Methods*\n━━━━━━━━━━━━━━━━━━━━\nChoose how you want to pay via Binance.\n\n• Binance Pay — paste Order ID after payment\n• USDT BEP20 — paste TXID after payment\n• USDT TRC20 — paste TXID after payment""",
    "payment_bybit_menu_text": """🟡 *Bybit Payment Methods*\n━━━━━━━━━━━━━━━━━━━━\nChoose how you want to pay via Bybit.\n\n• Bybit Pay — paste Transaction Hash after payment\n• USDT BEP20 — paste Transaction Hash after payment\n• USDT TRC20 — paste Transaction Hash after payment""",
    "payment_binance_pay_orderid": """🔶 *Binance Pay — Checkout*\n━━━━━━━━━━━━━━━━━━━━\n{title}\n💰 Amount: *{amount} USDT*\n📋 Binance Pay ID: `{pay_id}`\n👤 Holder: *{holder}*\n\n*How to pay:*\n1. Open Binance app.\n2. Go to Binance Pay.\n3. Send the exact amount shown above.\n4. After payment, copy the *Order ID* from Binance receipt.\n5. Paste the Order ID here in chat.\n\n⚠️ Send exact amount only. Wrong amount may not verify automatically.""",
    "payment_binance_usdt": """🪙 *Binance {method_label} — Order #{order_id}*\n━━━━━━━━━━━━━━━━━━━━\n💰 Amount: *{amount} USDT*\n🌐 Network: *{network_label}*\n\n📥 *Send to address*\n`{address}`\n\n*Important:*\n✅ Coin must be USDT\n✅ Network must be {network_label}\n✅ Send exact amount\n❌ Do not use another network or coin\n\n*After sending:*\n1️⃣ Open your wallet → find the transaction\n2️⃣ 🧾 *Copy the TXID (transaction hash)*\n3️⃣ 📨 *Paste the TXID here in chat*\n\n🤖 The bot checks the blockchain and adds your balance automatically.""",
    "payment_bybit_pay": """🟡 *Bybit — Order #{order_id}*\n━━━━━━━━━━━━━━━━━━━━\n💰 Amount: *{amount} USDT*\n📥 Send to Bybit UID: `{pay_id}`\n\n📲 *How to pay (Internal Transfer only — NOT Bybit Pay):*\n1️⃣ Open Bybit App → *Assets* → *Withdraw*\n2️⃣ Withdrawal Method → *Crypto Withdrawal*\n3️⃣ Choose *USDT* (the coin you have)\n4️⃣ Transfer Type → *Internal Transfer* 🔁\n5️⃣ At the top select *UID*\n6️⃣ Paste this UID: `{pay_id}`\n7️⃣ Paste amount exactly: *{amount} USDT*\n8️⃣ Tap *Withdraw* ✅\n\n🔙 Back to bot → tap *🔍 Check Payment*\n\n✨ Balance is added automatically.\n\n⚠️ Do NOT send via Bybit Pay — only Internal Transfer works for auto-detection.""",
    "payment_bybit_pay_reference": """🔖 *Your Reference ID:* `{reference_id}`\n_Tip: paste it in the *Reference/Note* field when sending so we can match it instantly. Not required — UID + exact amount is enough for auto-detection._""",
    "payment_bybit_usdt": """🟡 *{method_label} — Order #{order_id}*\n━━━━━━━━━━━━━━━━━━━━\n💰 Amount: *{amount} USDT*\n🌐 Network: *{network_label}*\n\n📥 *Send to address*\n`{address}`\n\n*Important:*\n✅ Coin must be USDT\n✅ Network must be {network_label}\n✅ Send exact amount\n❌ Wrong network/address will not verify\n\nAfter payment, paste the *Transaction Hash* here.""",
    "payment_not_found_txid": """⏳ *Transaction Not Found Yet*\n━━━━━━━━━━━━━━━━━━━━\nIf you already paid, tap *🔄 Check Again* in a moment — or paste the correct Transaction / Transfer ID.\n\nPlease make sure:\n• amount is exact\n• correct network/payment method was used\n• the ID matches the one in your Bybit receipt\n\n📲 *Bybit to Bybit tip:* Bybit app mein *Bybit Pay → balance* check karein. Agar payment wahan dikhe to usay *Funding account* mein *Transfer* karein, phir bot mein *Check Payment* dabayen — turant verify ho jayegi.\n\nIf it still doesn't verify, contact support — the store will check manually.""",
})

# ⭐ v162: Telegram Stars Editable Payment Screen Texts
DEFAULT_RESPONSES.update({
    "stars_pay_instructions": """⭐ *Pay with Telegram Stars*
━━━━━━━━━━━━━━━━━━━━

🧾 Order: `#{order_id}`
💰 Amount: *${amount}*
⭐ Stars needed: *{stars} Stars*
📊 Rate: 1$ = {rate} Stars

👇 Tap the button below — Telegram will open its secure payment window.
_No ID or screenshot needed — Stars credit instantly._""",
    "stars_payment_success": """🎉 *Deposit Successful!*
━━━━━━━━━━━━━━━━━━━━

✅ Your Telegram Stars payment has been confirmed.
💎 Points Added: *{points}*
💰 Amount: *${amount}*
🧾 Order ID: *#{order_id}*

_Thank you for your deposit!_""",
    "payment_stars_checkout": """⭐ *Telegram Stars — Product Checkout*
━━━━━━━━━━━━━━━━━━━━

📦 Product: *{product}*
🧾 Order: `#{order_id}`
💰 Total Amount: *${amount}*
⭐ Stars needed: *{stars} Stars*
📊 Exchange Rate: 1$ = {rate} Stars

👇 Tap the button below to complete your purchase via Telegram's secure payment window.
_Your product will be delivered instantly upon payment!_""",
    "payment_stars_deposit": """⭐ *Telegram Stars — Buy Points Deposit*
━━━━━━━━━━━━━━━━━━━━

🧾 Order: `#{order_id}`
💰 Deposit Amount: *${amount}*
⭐ Stars needed: *{stars} Stars*
📊 Exchange Rate: 1$ = {rate} Stars

👇 Tap the button below to deposit via Telegram's secure payment window.
_Points will be credited to your wallet instantly!_""",
    "payment_stars_success": """🎉 *Payment Successful!*
━━━━━━━━━━━━━━━━━━━━

✅ Your Telegram Stars payment has been confirmed.
💎 Points / Balance Added: *{points}*
💰 Amount: *${amount}*
🧾 Order ID: `#{order_id}`

_Thank you for your purchase!_""",
    "payment_stars_menu_text": """⭐ *Telegram Stars Payment*
━━━━━━━━━━━━━━━━━━━━
Fast, secure native payment inside Telegram.

• 1$ = 120 Stars (Admin Editable)
• No external wallets, UIDs, or TXIDs required.
• Instant delivery upon payment confirmation.""",
})


# 🔧 v122: Bybit Pay new UID-flow screens (auto-match by UID + unique amount)
DEFAULT_RESPONSES.update({
    "bybit_warning_text": (
        "⚠️ *Before you transfer — read carefully*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔢 *Copy the full amount with all decimals* (e.g. 5.0087)\n\n"
        "💯 *Send the exact same amount shown in the Bybit app*\n\n"
        "🧾 The amount we receive must match exactly — decimals included\n\n"
        "❗️ Any small difference in the decimals = the bot won't detect your transfer.\n\n"
        "_Tap Continue to proceed, or Cancel to go back._"
    ),
    "bybit_uid_prompt": (
        "🆔 *Enter your Bybit UID*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Find it in: Bybit app → your Profile (next to your name).\n\n"
        "Digits only, e.g. `543120799`\n\n"
        "_We need it to detect your transfer automatically._"
    ),
    "bybit_uid_invalid": (
        "❌ *Invalid Bybit UID*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Your Bybit UID is numbers only (e.g. `543120799`).\n\n"
        "Please send it again — find it in Bybit app → Profile."
    ),
    "bybit_amount_prompt": (
        "🟡 *Deposit via Bybit — UID*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 *Send the USD amount you want to deposit:*\n\n"
        "📌 Examples: 5 / 10 / 25 / 50\n"
        "⚠️ Minimum: $1\n\n"
        "_Type the amount (numbers only)._\n"
        "Your *exact unique payment amount* will be shown next."
    ),
    "bybit_amount_invalid": (
        "❌ *Invalid amount*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter a number, e.g. `1`, `5`, `10`.\n"
        "Minimum: $1"
    ),
    "bybit_deposit_instructions": (
        "💸 *Send via Bybit Internal Transfer* (Bybit → Bybit)\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💰 Amount: *{amount} USDT*\n"
        "📥 Send to Bybit UID: `{store_uid}`\n\n"
        "📲 *Step-by-step:*\n"
        "1️⃣ Open Bybit App → *Assets*\n"
        "2️⃣ Tap *Withdraw* → Withdrawal Method\n"
        "3️⃣ Select *Crypto Withdrawal* 💱\n"
        "4️⃣ Choose *USDT* (the coin you have)\n"
        "5️⃣ Transfer Type → *Internal Transfer* 🔁\n"
        "6️⃣ At the top select *UID* 🆔\n"
        "7️⃣ Paste this UID: `{store_uid}`\n"
        "8️⃣ Paste the amount exactly: *{amount}*\n\n"
        "9️⃣ Tap *Withdraw* ✅ → confirm\n"
        "🔟 Back to bot → tap *🔍 Check Payment*\n\n"
        "⚠️ Do NOT use *Bybit Pay* — only *Internal Transfer* is auto-detected.\n"
        "✏️ Optional reference: `{reference_id}`\n"
        "⏰ Valid for: 30 minutes"
    ),
    "bybit_check_payment_ok": (
        "✅ *Bybit Payment Verified!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Amount: *{amount} USDT*\n"
        "Sender UID: `{uid}`\n\n"
        "Your balance has been added."
    ),
    "bybit_cancelled": (
        "❌ *Bybit payment cancelled.*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Your order was cancelled. No amount was charged."
    ),
})

# ⭐ v161.25: Telegram Stars payment responses
DEFAULT_RESPONSES.update({
    "stars_pay_instructions": (
        "⭐ *Pay with Telegram Stars*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🧾 Order: `#{order_id}`\n"
        "💰 Amount: *${amount}*\n"
        "⭐ Stars needed: *{stars} Stars*\n"
        "📊 Rate: 1$ = {rate} Stars\n\n"
        "👇 Tap the button below — Telegram opens its secure payment window.\n"
        "_No ID or screenshot needed — Stars credit instantly._"
    ),
})


# 🔧 v123: Bybit USDT (TRC-20 / BEP-20) new UID-free deposit flow
DEFAULT_RESPONSES.update({
    "bybit_usdt_warning_text": (
        "⚠️ *Before you transfer — read carefully*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔢 *Copy the full amount with all decimals* (e.g. 5.0087)\n\n"
        "💯 *Send the exact same amount shown in the Bybit app*\n\n"
        "🧾 The amount we receive must match exactly — decimals included\n\n"
        "❗️ Any small difference in the decimals = the bot won't detect your transfer.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💸 *Fee note:* if the network deducts any fee, add it on top so the full required amount reaches us.\n"
        "We are not responsible for network fees.\n\n"
        "_Tap Continue to proceed, or Cancel to go back._"
    ),
    "bybit_usdt_amount_prompt": (
        "🟡 *Deposit via USDT — {network_label} Network*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 *Send the USD amount you want to deposit:*\n\n"
        "📌 Examples: 5 / 10 / 25 / 50\n"
        "⚠️ Minimum: $1\n\n"
        "_Type the amount (numbers only)._\n"
        "Your *exact unique payment amount* will be shown next."
    ),
    "bybit_usdt_amount_invalid": (
        "❌ *Invalid amount*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter a number, e.g. `1`, `5`, `10`.\n"
        "Minimum: $1"
    ),
    "bybit_usdt_deposit_instructions": (
        "💸 *Bybit — USDT — {network_label} Network*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✉️ *Address:*\n`{address}`\n\n"
        "💰 *Amount (exactly):*\n*{amount}*\n\n"
        "⚠️ *Make sure you use the correct network — sending on the wrong network loses the amount.*\n"
        "⏰ Expiry: 30 minutes\n"
        "✨ The balance is added automatically after confirmation"
    ),
    "bybit_usdt_cancelled": (
        "❌ *Bybit USDT payment cancelled.*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Your order was cancelled. No amount was charged."
    ),
})


# ════════════════════════════════════════════════════════════════
# 🆕 v161.11: RESELLER API — EDITABLE RESPONSES (English + emojis)
# (Auto-registered into bot_responses via migrate_all; editable in
#  Admin → Settings → Edit Responses, and Customization → Screen Editor)
# ════════════════════════════════════════════════════════════════
DEFAULT_RESPONSES.update({
    # ── Landing screen (user taps 🔗 Reseller API Key, no key yet) ──
    "reseller_api_landing": (
        "🔗 *Reseller API*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👉 Sell our products on your own bot or website!\n\n"
        "🔑 Tap **Generate API Key** to create your personal key.\n"
        "💳 Your key is linked to your wallet (💎 Buy Points to top up).\n"
        "📦 Every order is auto-delivered to your bot.\n\n"
        "_Your key is shown only ONCE after generating — save it!_"
    ),
    # ── Key generated screen ──
    "reseller_api_generated": (
        "✅ *New API Key Generated!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔑 *Your Key:*\n`{api_key}`\n\n"
        "⚠️ *Save this key now — it will be masked next time.*\n\n"
        "📡 Use header: `X-API-Key: {api_key}`\n"
        "🛒 Use it to sell our products on your own bot or website."
    ),
    # ── API Access panel (existing key) ──
    "reseller_api_panel": (
        "🔗 *API Access*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Use your API key to sell products on your own bot or website.\n\n"
        "🔑 *Your API Key:*\n`{prefix}....`\n\n"
        "💳 Balance: *${balance:.2f}*\n"
        "📨 Total requests: *{requests}*\n"
        "📅 Created: *{created}*"
    ),
    # ── Show Full Key screen ──
    "reseller_api_fullkey": (
        "🔑 *Your Full Key*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "`{api_key}`\n\n"
        "📡 Use header: `X-API-Key: {api_key}`"
    ),
    # ── Regenerate screen ──
    "reseller_api_regenerate": (
        "🔄 *New API Key Generated!* (old key revoked)\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔑 `{api_key}`\n\n"
        "⚠️ *Save now — shown only ONCE.*\n\n"
        "📡 Use header: `X-API-Key: {api_key}`"
    ),
})


# 🔖 Version indicator (exposed at /health for deploy verification)
BOT_VERSION = "v170.87"
