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
BACKUP_CHANNEL_ID = 0
# How often to auto-backup (in hours). e.g. 6 = every 6 hours.
BACKUP_INTERVAL_HOURS = 6

# 💰 Payment
EASYPAISA_NUMBER = "923193840214"
JAZZCASH_NUMBER = "923193840214"
ACCOUNT_NAME = "Zayam Iqbal"

# 🔶 Binance
BINANCE_PAY_ID = "887012522"

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
WHATSAPP_NUMBER = "923193840214"
SUPPORT_EMAIL = "trendbiteservices@gmail.com"

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

    "shop_categories_title": """🛍️ *Shop — Categories*
━━━━━━━━━━━━━━━━━━━━

Select a category to browse:""",

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

    "binance_pay_instructions": """🔶 *Binance Pay*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*{qty_text}
💰 *Total: ${total}*

📋 *Send to:*
  Binance Pay ID: `{pay_id}`
  Holder: {holder}

━━━━━━━━━━━━━━━━━━━━
💵 *Step 1/2:* Enter the *exact USD amount* you sent:
*(e.g.* `{amount}` *or* `${amount}`*)*""",

    "binance_order_created": """✅ *Order #{order_id} Created — Amount: ${amount}*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*

📋 *Send ${amount} to:*
  Binance Pay ID: `{pay_id}`
  Holder: {holder}

━━━━━━━━━━━━━━━━━━━━
📸 *Step 2/2: Upload Payment Screenshot*

After sending payment, take a screenshot of the
*'Payment Successful'* page (with Order ID visible)
and upload it here.

🤖 Bot will read the screenshot automatically
and verify amount + Order ID in 5-15 seconds.""",

    "screenshot_received": """✅ *Screenshot Received!*
━━━━━━━━━━━━━━━━━━━━

Order #{order_id} | Amount: ${amount}

📋 *Now tap 'Verify Payment' below.*

🤖 Bot will:
  • Read your screenshot with AI
  • Verify amount + Order ID match
  • Check it's real (not fake)
  • Add points to your account

*Takes 5-15 seconds*""",

    "analyzing_screenshot": """🤖 *Analyzing screenshot...*

Order #{order_id} | Amount: ${amount}

*AI reading payment details... (5-15 sec)*""",

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

    "jazzcash_pay_instructions": """📱 *Order #{order_id} — JazzCash Payment*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*{qty_text}
💰 Amount: *${amount}* ≈ *{pkr}*

📲 *Send Rs.{rs_amount} to:*
  Number: `{number}`
  Name: {holder}

━━━━━━━━━━━━━━━━━━━━
📸 *INSTRUCTIONS:*

1. Open JazzCash app
2. Send *Rs.{rs_amount}* to number above
3. Take screenshot of *'Transaction Successful'* page
4. Upload that screenshot here

🤖 Bot will read your screenshot,
verify everything, and deliver your product automatically!

⚠️ Make sure Transaction ID is visible.""",

    "easypaisa_pay_instructions": """📱 *Order #{order_id} — EasyPaisa Payment*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*{qty_text}
💰 Amount: *${amount}* ≈ *{pkr}*

📲 *Send Rs.{rs_amount} to:*
  Number: `{number}`
  Name: {holder}

━━━━━━━━━━━━━━━━━━━━
📝 *Instructions:*
1. Send the exact amount to Easypaisa account above 💳
2. EasyPaisa will send you SMS with Trx ID
3. Enter only the *Trx ID* below — bot will check itself!

🔢 *Enter your Trx ID (11 digits):*
*(From EasyPaisa SMS — example:* `50568603579`*)*""",

    "jc_screenshot_received": """✅ *Screenshot Received!*
━━━━━━━━━━━━━━━━━━━━

Order #{order_id} | Expected: Rs.{amount}

📋 *Now tap 'Verify Payment' below.*

🤖 Bot will:
  • Read your screenshot with AI
  • Verify amount + Transaction ID
  • Check it's real (not fake)
  • Deliver product / add points

*Takes 5-15 seconds*""",

    # ══════════════════════════════════════
    # ✅ VERIFICATION SUCCESS MESSAGES
    # ══════════════════════════════════════
    "jc_payment_verified_points": """🎉 *Payment Verified!* ✅
━━━━━━━━━━━━━━━━━━━━

💎 *{pts} Points* added to your account!

💰 Amount: Rs.{amount}
🆔 TID: `{tid}`

📊 Check 'My Account' for new balance.
Thank you! 🙏""",

    "jc_payment_verified_product": """🎉 *Order Delivered!* ✅
━━━━━━━━━━━━━━━━━━━━

📦 {product}

📨 *Your Product:*
━━━━━━━━━━━━━━━━━━
{delivery}
━━━━━━━━━━━━━━━━━━

💎 +{pts} bonus points!
Thank you! 🙏""",

    "ep_payment_verified_points": """🎉 *Payment Verified!* ✅
━━━━━━━━━━━━━━━━━━━━

💎 *{pts} Points* added to your account!

💰 Amount: Rs.{amount}
👤 From: {name}
🔢 TID: `{tid}`

Thank you! 🙏""",

    "ep_payment_verified_product": """🎉 *Order Delivered!* ✅
━━━━━━━━━━━━━━━━━━━━

📦 {product}

📨 *Your Product:*
━━━━━━━━━━━━━━━━━━
{delivery}
━━━━━━━━━━━━━━━━━━

💎 +{pts} points!
Thank you! 🙏""",

    # ══════════════════════════════════════
    # ❌ ERROR MESSAGES
    # ══════════════════════════════════════
    "order_created": """✅ *Order #{order_id} Created!*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}* — ${price}""",

    "order_rejected": "❌ Order #{order_id} was rejected.\nContact support for help.",

    "order_cancelled": "❌ *Order #{order_id} Cancelled.*\n\nMarked as canceled in your transaction history.",

    "error_duplicate_screenshot": """❌ Duplicate Screenshot!
━━━━━━━━━━━━━━━━━━━━

{reason}

Each payment Order ID can be used only ONCE. Order rejected.""",

    "error_suspicious_screenshot": """🚨 Suspicious Screenshot!
━━━━━━━━━━━━━━━━━━━━

{reason}

Order rejected for security. Contact admin if genuine.""",

    "error_not_screenshot": """❌ Not a Valid Screenshot
━━━━━━━━━━━━━━━━━━━━

{reason}

📸 Upload a real payment 'Successful' screenshot.""",

    "error_payment_not_successful": """❌ Payment Not Successful
━━━━━━━━━━━━━━━━━━━━

{reason}

📸 Send screenshot of the SUCCESS page only.""",

    "error_amount_mismatch": """❌ Amount Mismatch
━━━━━━━━━━━━━━━━━━━━

{reason}

Make sure you sent the EXACT amount and uploaded right screenshot.""",

    "error_no_order_id": """⚠️ Order ID Not Readable
━━━━━━━━━━━━━━━━━━━━

{reason}

📸 Upload a CLEARER screenshot with Order ID visible.""",

    "error_wrong_receiver": """❌ Wrong Receiver!
━━━━━━━━━━━━━━━━━━━━

{reason}""",

    "error_verification": """⚠️ Verification Error
━━━━━━━━━━━━━━━━━━━━

{reason}""",

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

    "buy_points_title": """💎 *Buy {pts} Points*
━━━━━━━━━━━━━━━━━━━━
💰 ${amt} = {pts} Points

Select payment method:""",

    "buy_points_custom": "💎 Enter amount ($):",

    "buy_points_custom_confirmed": """💎 *{pts} Points* — ${amt}

Select payment method:""",

    "binance_points_instructions": """🔶 *Order #{order_id} — Buy {pts} Points (${amount})*
━━━━━━━━━━━━━━━━━━━━

📋 *Send ${amount} to:*
  Binance Pay ID: `{pay_id}`
  Holder: {holder}

━━━━━━━━━━━━━━━━━━━━
📸 *INSTRUCTIONS:*

1. Open Binance app
2. Pay *${amount}* to Pay ID above
3. Take screenshot of *'Payment Successful'* page
4. Upload that screenshot here

🤖 Bot will read your screenshot,
verify everything, and add *{pts} points* automatically!

⚠️ Make sure Order ID is visible in screenshot.""",

    "easypaisa_points_instructions": """📱 *Order #{order_id} — EasyPaisa Buy {pts} Points*
━━━━━━━━━━━━━━━━━━━━
💎 You will receive: *{pts} Points*
💰 Pay: *Rs.{rs_amount}* (= ${amount})

📲 *Send Rs.{rs_amount} to:*
  Number: `{number}`
  Name: {holder}

━━━━━━━━━━━━━━━━━━━━
📝 *Instructions:*
1. Send Rs.{rs_amount} to Easypaisa account above 💳
2. EasyPaisa will send SMS with Trx ID
3. Enter only the *Trx ID* below — bot will check itself!

🔢 *Enter Trx ID (11 digits):*
*(From EasyPaisa SMS — example:* `50568603579`*)*""",

    "jazzcash_points_instructions": """📱 *Order #{order_id} — JazzCash Buy {pts} Points*
━━━━━━━━━━━━━━━━━━━━
💎 You will receive: *{pts} Points*
💰 Pay: *Rs.{rs_amount}* (= ${amount})

📲 *Send Rs.{rs_amount} to:*
  Number: `{number}`
  Name: {holder}

━━━━━━━━━━━━━━━━━━━━
📸 *INSTRUCTIONS:*

1. Send Rs.{rs_amount} via JazzCash to number above
2. Take screenshot of *'Transaction Successful'* page
3. Upload screenshot here

🤖 Bot will read & verify automatically in 5-15 sec!""",

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
    "ep_tid_received": """🔢 *Trx ID Received:* `{tid}` ✅
━━━━━━━━━━━━━━━━━━━━
📋 Order #{order_id}
💰 Expected: *Rs.{expected_rs}*

📲 *Make sure:*
• Payment is sent to our EasyPaisa account
• You have forwarded the SMS to bot's Gmail
• Wait ~30 seconds for email to arrive

🤖 *Now tap 'Verify Payment'*
Bot will check Gmail, read amount + name automatically,
and add points to your account!""",

    "ep_tid_invalid": "❌ Trx ID must be *10-13 digits*!\nYou entered: {count} digits\n_Check EasyPaisa SMS._",

    "ep_tid_already_used": """❌ *This Trx ID is already used!*

Each transaction can be used ONCE.

*Already used at: {date}*""",

    # ══════════════════════════════════════
    # 📸 SCREENSHOT UPLOAD
    # ══════════════════════════════════════
    "upload_image_only": """❌ Please upload an *image* (photo).

📸 Take screenshot of 'Payment Successful' page and send it.""",

    "reupload_screenshot": """📸 *Please upload your new payment screenshot now.*

Make sure it shows 'Payment Successful' with Order ID visible.""",

    "jc_reupload_screenshot": """📸 *Please upload your new JazzCash screenshot now.*

Make sure it shows 'Transaction Successful' with TID visible.""",

    "screenshot_no_pending": "❓ No pending order. /start",

    "screenshot_received_manual": "✅ Screenshot received! Order #{order_id} — verifying ⏳",

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

    "referral_success_notification": "🎁 {name} joined via your link! +{points} point!",

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
    "freeclaim_already_claimed": "✅ *You already claimed this product for free.*\n\nEach user can claim a free product only once.",
    "freeclaim_success": "🎉 *Claim Successful!*\n\n📦 *{product}*\n👥 Referrals spent: *{refs}*\n\n✅ Your product has been delivered above.\n💡 Keep referring to claim more free products!",

    # ══════════════════════════════════════
    # 🆕 v48 — Smart Share + Referral Points
    # ══════════════════════════════════════
    "freeclaim_share_message": "🎁 I'm getting {product} for FREE on {shop}!\n\nWant one too? Super easy:\n1️⃣ Click my link below\n2️⃣ Open it in Telegram\n3️⃣ Tap Start — and you're in!\n\n👇 My personal link:\n{link}",
    "freeclaim_share_screen": "🔗 *Your Personal Share Link*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 *{product}*\n🎁 Need: *{required}* referrals\n📊 You have: *{available}*\n\n🔗 *Long-press to copy your link:*\n`{link}`\n\n📲 *Or use the share buttons below* — pick any platform.\n_When anyone clicks your link & starts the bot, you instantly get *1 Referral Point*!_\n\n📝 *Preview of share message:*\n```\n{preview}\n```",
    "referral_blocked_by_admin": "🚫 Your referral was blocked.\nReason: {reason}\n\n_If you think this is a mistake, contact support._",

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
    "binance_orderid_processing": "⏳ *Processing your payment…*\n━━━━━━━━━━━━━━━━━━━━\n\nOrder #{order_id}  •  ${amount}\nOrder ID: `{binance_order_id}`\n\n_Please wait a few seconds._",
    "binance_orderid_not_confirmed": "⏳ *Payment not confirmed yet*\n━━━━━━━━━━━━━━━━━━━━\n\nOrder #{order_id}  •  ${amount}\nOrder ID: `{binance_order_id}`\n\n📌 Please make sure:\n  • You sent *exactly ${amount}* to Pay ID `{pay_id}`\n  • The Order ID above matches the one in your Binance app\n\nPayments can take up to 2 minutes to confirm. Tap *Check Again* to retry, or open a *Support Ticket* if you need help.",
    "binance_orderid_already_confirmed": "✅ *Your payment is already confirmed!*\n\nCheck your account / order history.",
    "binance_orderid_already_used": "❌ *This payment has already been used.*\n\nOrder #{order_id} has been rejected. If you think this is a mistake, please open a support ticket.",
    "binance_orderid_invalid": "❌ That doesn't look like a valid Order ID.\n\nPlease copy the *Order ID* from your Binance app transaction screen and paste it here (it's usually a long string of letters and numbers).",

    # 🆕 v65: Refund + Cancel texts
    "refund_processed": "💸 *Refund Processed*\n━━━━━━━━━━━━━━━━━━━━\n\nThis product is currently unavailable, so your payment is being refunded.\n\n📦 Order: `#{order_id}`\n📌 Product: *{product}*\n💰 Amount: *${amount}*\n\n✅ *{points} Points have been credited* to your wallet as an instant refund.\n💎 New balance: *{new_balance} Points*\n\nYou can use these Points to buy other products in the store. We apologise for the inconvenience.",
    "order_cancelled_with_reason": "❌ *Order Cancelled*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Order: `#{order_id}`\n📌 Product: *{product}*\n💰 Amount: `${amount}`\n\n📋 *Reason from the store:*\n_{reason}_\n\nIf you have already paid, please contact support to arrange a refund.",
    "order_cancelled_no_reason":   "❌ *Order Cancelled*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Order: `#{order_id}`\n📌 Product: *{product}*\n💰 Amount: `${amount}`\n\nYour order has been cancelled. If you have already paid, please contact support to arrange a refund.",

    # 🆕 v68: Default tier upgrade message (when admin hasn't set custom)
    "tier_upgrade_default":   "🎉 *Congratulations!*\n━━━━━━━━━━━━━━━━━━━━\n\nYou've reached *{tier}* tier!\n\nKeep shopping to unlock more rewards.",
    "tier_progress_hint":     "🏆 Tier: {tier} — *{hint}* for {next_tier}",
    "tier_progress_max":      "🏆 Tier: {tier} (Max tier reached!)",
    "tier_bonus_credited":    "💎 *Tier bonus: +{points} points*",
}
