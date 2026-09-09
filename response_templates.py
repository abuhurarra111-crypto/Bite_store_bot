# ============================================================
# 🎨 RESPONSE TEMPLATES  (v170.22 → 🆕 v170.92 FULL ENGLISH)
# ============================================================
# ✏️ Edit Responses (Admin → ⚙️ Settings → ✏️ Edit Responses) ab
# har response ke liye 2 READYMADE templates dikhata hai + custom
# option (placeholders ke sath).
#
#   • Template 1 ("Style A") = DEFAULT_RESPONSES[key]  (classic)
#   • Template 2 ("Style B") = RESPONSE_TEMPLATE_B[key] (alternative)
#
# 🆕 v170.92: Style B ka poora text English kar diya gaya hai
# (pehle Roman Urdu me tha).
#
# 🛡️ SAFETY RULE: har template sirf WAHI placeholders use kar sakta hai
# jo us key ke DEFAULT me already maujood hain — warna runtime `.format()`
# crash ho sakta hai (KeyError). Test karta hai ye (test_v170_91_regression).
# ============================================================
import re

_PH_RE = re.compile(r"\{([a-z_][a-z0-9_]*)(?::[^}]*)?\}")


def extract_placeholders(text):
    """Return ordered-unique placeholder NAMES in a template string
    (ignores format-specs like {balance:.2f})."""
    if not text:
        return []
    seen, out = set(), []
    for m in _PH_RE.finditer(text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


# ── Style B (alternative) templates — 🆕 v170.92: ALL ENGLISH ──
# Har key ke liye 1 alternative. Template 1 hamesha default hota hai.
RESPONSE_TEMPLATE_B = {
    # 🏠 MAIN MENU & NAVIGATION
    "welcome": """👋 Welcome to {shop_name}!

━━━━━━━━━━━━━━━━━━━━

🆔 Your User ID: `{user_id}`

⚡ Pay with Binance Pay — instant auto-verification.""",

    "fj_verified_done": """✅ Verified!

Welcome aboard {shop_name}! 🛍️

You can now use the bot. Enjoy!""",

    "my_account": """👤 *{name}*
━━━━━━━━━━━━━━━━━━━━

🆔 ID: `{user_id}`
📛 Username: @{username}
💎 Points: *{points}*
👥 Referrals: *{referrals}*
📅 Joined: {joined}""",

    # 🛒 SHOP & PRODUCTS
    "shop_title": "🛒 Available Products\n(Page {page}/{total_pages})",

    "shop_categories_title": """🗂️ *Shop Categories*
━━━━━━━━━━━━━━━━━━━━

Pick a category to browse:""",

    "product_detail": """📦 *{name}*
━━━━━━━━━━━━━━━━━━━━

📝 {description}

💰 Price: *${price}* (~ *{pkr}*)
📊 Stock: *{stock}*""",

    "no_products": "🛒 No products available yet.\nCheck back soon!",

    "out_of_stock": "😔 This product is currently out of stock.",

    "confirm_purchase": """🛒 *Confirm Purchase*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*
💰 Price: *${price}* ≈ *{pkr}*
🔢 Quantity: *1*

Choose a payment method:""",

    "confirm_bulk_purchase": """🛒× *Buy Multiple*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*
💰 Unit Price: *${price}* ≈ *{pkr}*
📊 Stock: *{stock}*

✍️ Enter quantity (numbers only):
*Example: 5*

Max: {stock}""",

    "bulk_confirmed": """🛒× *Bulk Purchase Confirmed*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*
💰 Unit: ${unit_price} × *{qty}*
━━━━━━━━━━━━━━━━━━━━
💵 *Total: ${total}* ≈ *{pkr}*

Choose a payment method:""",

    # 💳 PAYMENT SCREENS
    "buy_points": """💎 *Buy Points*
━━━━━━━━━━━━━━━━━━━━

💎 Your Points: *{points}*
💰 Rate: $1 = {rate} Points

Choose a payment method:""",

    "payment_verified_points": """✅ *Payment Verified!*
━━━━━━━━━━━━━━━━━━━━

💎 *{pts} Points* added!

💰 Amount: ${amount} {currency}
🆔 Order ID: `{order_id}`

Thank you! 🙏""",

    "payment_verified_product": """🎉 *Order #{order_id} Delivered!* ✅
━━━━━━━━━━━━━━━━━━━━

📦 {product}

📨 *Your Product:*
━━━━━━━━━━━━━━━━━━━━
{delivery}
━━━━━━━━━━━━━━━━━━━━

💎 +{points} points earned!
Thank you! 🙏""",

    "order_rejected": "❌ Order #{order_id} was rejected.\nPlease contact support for help.",

    "referral_text": """🎁 *Referral Program*
━━━━━━━━━━━━━━━━━━━━

🔗 Your Link:
`{ref_link}`

👥 Referrals: *{ref_count}*
💎 Points: *{ref_points}*

📋 Share → They join → You get *{points_per_ref} point*!""",

    "no_transactions": "💳 No deposits yet.\n\nAdd funds via 💎 Buy Points.",

    "no_orders": "📜 No orders yet.",

    "orders_title": "🧾 *Your Orders:*\n━━━━━━━━━━━━━━━━━━━━",

    # 📞 SUPPORT & OTHER
    "support_text": """🎧 *Support*
━━━━━━━━━━━━━━━━━━━━

Choose how you'd like to get help:""",

    "terms": """📜 *Terms & Conditions*
━━━━━━━━━━━━━━━━━━━━

1. All sales are final — no refunds
2. Digital products delivered instantly
3. Do not share purchased items
4. Payment within 30 minutes

*Last updated: May 2026*""",

    "binance_instructions": """⚠️ *Important Instructions:*
• Enter your *exact Binance sender name*
• Pay the *exact* amount
• After payment, tap *Verify Payment*
• If it doesn't verify, try again after *1 minute*""",

    "new_user_notification": """👤 *New User Joined!*
Name: {name}
Username: @{username}
ID: `{user_id}`""",

    "cancelled_message": "❌ *Cancelled.*\n\nYou're back at the main menu.",

    "support_menu_header": """🎫 *Support Center*
━━━━━━━━━━━━━━━━━━━━

Need help? Create a ticket!
📞 *WhatsApp:* `+{whatsapp}`

📋 *Your Tickets:* {total}
🟡 *Open:* {open}

Choose an option:""",

    "warranty_menu_header": """🛡️ *Warranty & Refund*
━━━━━━━━━━━━━━━━━━━━

Pick an order:""",

    "warranty_no_orders": """🛡️ *Warranty & Refund*
━━━━━━━━━━━━━━━━━━━━

No delivered orders found.
Warranty/refund applies to delivered orders only.""",

    "reviews_menu_header": """⭐ *Reviews & Ratings*
━━━━━━━━━━━━━━━━━━━━

📝 My reviews: {my}
✍️ Reviews pending: {pending}

Share your experience!""",

    "loyalty_menu_header": """🏆 *Loyalty Program*
━━━━━━━━━━━━━━━━━━━━""",

    "language_menu_header": """🌐 *Choose Language*
━━━━━━━━━━━━━━━━━━━━

Select your preferred language:""",

    # 🎁 FREE CLAIM / FREEBIES
    "freeclaim_user_screen": """🎁 *Get This Product FREE!*

📦 *{product}*
👥 Required Referrals: *{required}*
✅ Your Referrals: *{available}*

🎉 *You're eligible!* Tap *Claim Now*.""",

    "freeclaim_not_enough": """🎁 *Get This Product FREE!*

📦 *{product}*
👥 Required: *{required}*
📊 You have: *{available}*
📉 You need *{missing}* more referrals.

🔗 Share your referral link — everyone who taps /start counts!""",

    "freebies_menu_header": """🎁 *Freebies*
━━━━━━━━━━━━━━━━━━━━

_These products are 100% FREE — grab yours now!_""",

    "freebies_empty": """🎁 *Freebies*
━━━━━━━━━━━━━━━━━━━━

_No free products right now. Check back soon!_""",

    "freebie_success": """🎉 *Freebie Claimed!*
━━━━━━━━━━━━━━━━━━━━

📦 {product}
✅ Delivered FREE above.

🔁 To claim again: {reclaim} referrals.""",

    "freebie_need_refs": """🔁 To claim again you need *{required} referrals*.
👥 Your referrals: *{have}*
⭐ You need *{missing}* more.""",

    "freebie_claim_limit": "❌ You reached the claim limit for this product.",

    "freebie_out_of_stock": "😔 Out of stock right now. Please try again later.",

    "freeclaim_share_message": """🎁 I'm getting {product} for FREE on {shop}!

Want one too? Super easy:
1️⃣ Click my link below
2️⃣ Open it in Telegram
3️⃣ Tap Start — and you're in!

👇 My link:
{link}""",

    "freeclaim_share_screen": """🔗 *Your Share Link*
━━━━━━━━━━━━━━━━━━━━

📦 *{product}*
🎁 Need: *{required}* referrals
📊 You have: *{available}*

🔗 *Long-press to copy your link:*
`{link}`

📝 *Share message preview:*
```
{preview}
```""",

    "shop_no_unavailable": """✅ *Everything Is Available!*
━━━━━━━━━━━━━━━━━━━━

There are no out-of-stock products right now — everything is available!

Tap *📋 Show All Products* below.""",

    "shop_no_available": """😔 *All products are currently out of stock.*
━━━━━━━━━━━━━━━━━━━━

We're restocking soon! See what's coming back via *📋 Show All Products*, or set up 🔔 stock alerts on the out-of-stock list.""",

    # 🔶 BINANCE
    "binance_orderid_instructions": """🟡 *Binance Pay Checkout*
━━━━━━━━━━━━━━━━━━━━

{title}
💵 Amount: *${amount}*

📋 *Step 1 — Send the payment*
  • Pay ID:  `{pay_id}`
  • Name:    *{holder}*
  • Amount:  *${amount}*

📨 *Step 2 — Send your Order ID*
After completing the payment, open the transaction in your Binance app, copy the *Order ID*, and paste it below.

_Your order will be confirmed automatically within a few seconds._""",

    "refund_processed": """💸 *Refund Processed*
━━━━━━━━━━━━━━━━━━━━

This product is currently unavailable, so your payment is being refunded.

📦 Order: `#{order_id}`
📌 Product: *{product}*
💰 Amount: *${amount}*

✅ *{points} Points have been credited* to your wallet as an instant refund.
💎 New balance: *{new_balance} Points*

You can use these Points to buy other products in the store.""",

    "order_cancelled_with_reason": """❌ *Order Cancelled*
━━━━━━━━━━━━━━━━━━━━

📦 Order: `#{order_id}`
📌 Product: *{product}*
💰 Amount: `${amount}`

📋 *Reason:* _{reason}_

If you have already paid, please contact support to arrange a refund.""",

    "order_cancelled_no_reason": """❌ *Order Cancelled*
━━━━━━━━━━━━━━━━━━━━

📦 Order: `#{order_id}`
📌 Product: *{product}*
💰 Amount: `${amount}`

If you have already paid, please contact support to arrange a refund.""",

    "payment_binance_menu_text": """🔶 *Binance Payment Methods*
━━━━━━━━━━━━━━━━━━━━
Choose how you want to pay via Binance.

• Binance Pay — paste the Order ID after payment
• USDT BEP20 — paste the TXID after payment
• USDT TRC20 — paste the TXID after payment""",

    "payment_bybit_menu_text": """🟡 *Bybit Payment Methods*
━━━━━━━━━━━━━━━━━━━━
Choose how you want to pay via Bybit.

• Bybit Pay — paste the Transaction Hash after payment
• USDT BEP20 — paste the Transaction Hash after payment
• USDT TRC20 — paste the Transaction Hash after payment""",

    "payment_binance_pay_orderid": """🔶 *Binance Pay — Checkout*
━━━━━━━━━━━━━━━━━━━━
{title}
💰 Amount: *{amount} USDT*
📋 Binance Pay ID: `{pay_id}`
👤 Holder: *{holder}*

*How to pay:*
1. Open the Binance app.
2. Go to Binance Pay.
3. Send the exact amount shown above.
4. Copy the *Order ID* from the Binance receipt.
5. Paste the Order ID here in chat.

⚠️ Send the exact amount only.""",

    "payment_binance_usdt": """🪙 *Binance {method_label} — Order #{order_id}*
━━━━━━━━━━━━━━━━━━━━
💰 Amount: *{amount} USDT*
🌐 Network: *{network_label}*

📥 *Send to address*
`{address}`

*Important:*
✅ Coin must be USDT
✅ Network must be {network_label}
✅ Send the exact amount
❌ Do not use another network or coin

*After sending:*
1️⃣ Open your wallet → find the transaction
2️⃣ 🧾 *Copy the TXID (transaction hash)*
3️⃣ 📨 *Paste the TXID here in chat*

🤖 The bot checks the blockchain and adds your balance automatically.""",

    "payment_bybit_pay": """🟡 *Bybit — Order #{order_id}*
━━━━━━━━━━━━━━━━━━━━
💰 Amount: *{amount} USDT*
📥 Send to Bybit UID: `{pay_id}`

📲 *Steps (Internal Transfer only — NOT Bybit Pay):*
1️⃣ Bybit App → *Assets* → *Withdraw*
2️⃣ Select *Crypto Withdrawal*
3️⃣ Select the *USDT* coin
4️⃣ Transfer Type → *Internal Transfer* 🔁
5️⃣ Select *UID* at the top
6️⃣ Paste this UID: `{pay_id}`
7️⃣ Exact amount: *{amount} USDT*
8️⃣ Tap *Withdraw* ✅

🔙 Back in the bot → tap *🔍 Check Payment*.

⚠️ Do NOT use Bybit Pay — only Internal Transfer is auto-detected.""",

    "payment_bybit_pay_reference": """🔖 *Your Reference ID:* `{reference_id}`
_Tip: paste it in the *Reference/Note* field when sending for an instant match. Not required — UID + exact amount is enough._""",

    "payment_bybit_usdt": """🟡 *{method_label} — Order #{order_id}*
━━━━━━━━━━━━━━━━━━━━
💰 Amount: *{amount} USDT*
🌐 Network: *{network_label}*

📥 *Send to address*
`{address}`

*Important:*
✅ Coin must be USDT
✅ Network must be {network_label}
✅ Send the exact amount
❌ A wrong network/address will not be verified

After sending, paste the *Transaction Hash* here.""",

    "payment_not_found_txid": """⏳ *Transaction Not Found Yet*
━━━━━━━━━━━━━━━━━━━━
If you already paid, tap *🔄 Check Again* in a moment — or paste the correct Transaction / Transfer ID.

Please make sure:
• the amount is exact
• the correct network/payment method was used
• the ID matches your Bybit receipt

📲 *Bybit tip:* in the Bybit app, check *Bybit Pay → balance*. If the payment appears there, *Transfer* it to your *Funding account*, then tap *Check Payment* in the bot.

If it still doesn't verify, contact support.""",

    # ⭐ STARS
    "stars_pay_instructions": """⭐ *Pay with Telegram Stars*
━━━━━━━━━━━━━━━━━━━━

🧾 Order: `#{order_id}`
💰 Amount: *${amount}*
⭐ Stars needed: *{stars} Stars*
📊 Rate: 1$ = {rate} Stars

👇 Tap the button below — Telegram's secure payment window will open.
_Stars are credited instantly._""",

    "stars_payment_success": """🎉 *Deposit Successful!*
━━━━━━━━━━━━━━━━━━━━

✅ Your Stars payment has been confirmed.
💎 Points Added: *{points}*
💰 Amount: *${amount}*
🧾 Order ID: *#{order_id}*

_Thank you!_""",

    "payment_stars_checkout": """⭐ *Stars — Product Checkout*
━━━━━━━━━━━━━━━━━━━━

📦 Product: *{product}*
🧾 Order: `#{order_id}`
💰 Total: *${amount}*
⭐ Stars: *{stars} Stars*
📊 Rate: 1$ = {rate} Stars

👇 Tap the button below — your product will be delivered instantly after payment!""",

    "payment_stars_deposit": """⭐ *Stars — Deposit*
━━━━━━━━━━━━━━━━━━━━

🧾 Order: `#{order_id}`
💰 Deposit: *${amount}*
⭐ Stars: *{stars} Stars*
📊 Rate: 1$ = {rate} Stars

👇 Tap the button below — Points will be added to your wallet instantly!""",

    "payment_stars_success": """🎉 *Payment Successful!*
━━━━━━━━━━━━━━━━━━━━

✅ Stars payment confirmed.
💎 Points Added: *{points}*
💰 Amount: *${amount}*
🧾 Order ID: `#{order_id}`

_Thank you!_""",

    "payment_stars_menu_text": """⭐ *Telegram Stars Payment*
━━━━━━━━━━━━━━━━━━━━
Fast & secure payment right inside Telegram.

• 1$ = 120 Stars (editable by Admin)
• No external wallet/UID/TXID needed.
• Instant delivery as soon as the payment is confirmed.""",

    # 🟡 BYBIT
    "bybit_warning_text": """⚠️ *Before you transfer — read carefully*
━━━━━━━━━━━━━━━━━━━━

🔢 *Copy the full amount with all decimals* (e.g. 5.0087)

💯 *Send EXACTLY the amount shown in the Bybit app*

🧾 The amount must match exactly — including decimals

❗️ Even a tiny difference in decimals = the bot will not detect your transfer.

_Tap Continue, or go back with Cancel._""",

    "bybit_uid_prompt": """🆔 *Enter Your Bybit UID*
━━━━━━━━━━━━━━━━━━━━

Find it in the Bybit app → Profile (next to your name).

Numbers only, e.g. `543120799`

_Required so the transfer can be auto-detected._""",

    "bybit_uid_invalid": """❌ *Invalid Bybit UID*
━━━━━━━━━━━━━━━━━━━━

Your Bybit UID is numbers only (e.g. `543120799`).

Please try again — find it in the Bybit app → Profile.""",

    "bybit_amount_prompt": """🟡 *Deposit via Bybit — UID*
━━━━━━━━━━━━━━━━━━━━

💡 *How much do you want to deposit? (USD amount):*

📌 Examples: 5 / 10 / 25 / 50
⚠️ Minimum: $1

_Numbers only._""",

    "bybit_amount_invalid": """❌ *Invalid amount*
━━━━━━━━━━━━━━━━━━━━

Please enter a number, e.g. `1`, `5`, `10`.
Minimum: $1""",

    "bybit_deposit_instructions": """💸 *Send via Bybit Internal Transfer* (Bybit → Bybit)
━━━━━━━━━━━━━━━━━━━━

💰 Amount: *{amount} USDT*
📥 Send to Bybit UID: `{store_uid}`

📲 *Steps:*
1️⃣ Bybit App → *Assets*
2️⃣ Tap *Withdraw*
3️⃣ Select *Crypto Withdrawal* 💱
4️⃣ Select the *USDT* coin
5️⃣ Transfer Type → *Internal Transfer* 🔁
6️⃣ Select *UID* at the top 🆔
7️⃣ Paste this UID: `{store_uid}`
8️⃣ Exact amount: *{amount}*

9️⃣ *Withdraw* ✅ → confirm
🔟 Back in the bot → *🔍 Check Payment*

⚠️ Do NOT use *Bybit Pay*.
✏️ Reference (optional): `{reference_id}`
⏰ Valid for: 30 minutes""",

    "bybit_check_payment_ok": """✅ *Bybit Payment Verified!*
━━━━━━━━━━━━━━━━━━━━
Amount: *{amount} USDT*
Sender UID: `{uid}`

Your balance has been added.""",

    "bybit_cancelled": """❌ *Bybit payment cancelled.*
━━━━━━━━━━━━━━━━━━━━

No amount was charged.""",

    "bybit_usdt_warning_text": """⚠️ *Before you transfer — read carefully*
━━━━━━━━━━━━━━━━━━━━

🔢 *Copy the full amount with all decimals* (e.g. 5.0087)

💯 *Send EXACTLY the amount shown in the Bybit app*

🧾 The amount must match exactly — including decimals

❗️ Even a tiny difference in decimals = the bot will not detect your transfer.

━━━━━━━━━━━━━━━━━━━━
💸 *Fee note:* network fees are deducted on the way — add them on top so the full amount arrives.
We are not responsible for network fees.

_Tap Continue, or go back with Cancel._""",

    "bybit_usdt_amount_prompt": """🟡 *Deposit via USDT — {network_label} Network*
━━━━━━━━━━━━━━━━━━━━

💡 *How much do you want to deposit? (USD amount):*

📌 Examples: 5 / 10 / 25 / 50
⚠️ Minimum: $1

_Numbers only._""",

    "bybit_usdt_amount_invalid": """❌ *Invalid amount*
━━━━━━━━━━━━━━━━━━━━

Please enter a number, e.g. `1`, `5`, `10`.
Minimum: $1""",

    "bybit_usdt_deposit_instructions": """💸 *Bybit — USDT — {network_label} Network*
━━━━━━━━━━━━━━━━━━━━

✉️ *Address:*
`{address}`

💰 *Amount (exact):*
*{amount}*

⚠️ *Use the correct network — sending on the wrong network will result in loss of funds.*
⏰ Expiry: 30 minutes
✨ Your balance will be added as soon as it confirms""",

    "bybit_usdt_cancelled": """❌ *Bybit USDT payment cancelled.*
━━━━━━━━━━━━━━━━━━━━

No amount was charged.""",

    # 🔗 RESELLER API
    "reseller_api_landing": """🔗 *Reseller API*
━━━━━━━━━━━━━━━━━━━━

👉 Sell our products on your own bot or website!

🔑 Tap *Generate API Key* to create your key.
💳 The key is linked to your wallet (top up via 💎 Buy Points).
📦 Every order is auto-delivered to your bot.

_The key is shown only ONCE — save it!_""",

    "reseller_api_generated": """✅ *New API Key Generated!*
━━━━━━━━━━━━━━━━━━━━

🔑 *Your Key:*
`{api_key}`

⚠️ *Save it now — next time it will be shown masked.*

📡 Header: `X-API-Key: {api_key}`""",

    "reseller_api_panel": """🔗 *API Access*
━━━━━━━━━━━━━━━━━━━━
Use your API key to sell products on your own bot/website.

🔑 *API Key:*
`{prefix}....`

💳 Balance: *${balance:.2f}*
📨 Total requests: *{requests}*
📅 Created: *{created}*""",

    "reseller_api_fullkey": """🔑 *Your Full Key*
━━━━━━━━━━━━━━━━━━━━

`{api_key}`

📡 Header: `X-API-Key: {api_key}`""",

    "reseller_api_regenerate": """🔄 *New Key Generated!* (old key revoked)
━━━━━━━━━━━━━━━━━━━━

🔑 `{api_key}`

⚠️ *Save it now — it will be shown only once.*

📡 Header: `X-API-Key: {api_key}`""",
}


def get_response_templates(key, default=""):
    """Return the 2 readymade templates for a key as [(label, text), ...].

    • Template 1 = default (DEFAULT_RESPONSES / passed-in default)
    • Template 2 = curated alternative (RESPONSE_TEMPLATE_B)
    """
    tpls = [("📄 Style A", default or "")]
    alt = RESPONSE_TEMPLATE_B.get(key)
    if alt:
        tpls.append(("✨ Style B", alt))
    return tpls


def get_key_placeholders(key, current="", default=""):
    """Ordered-unique placeholder names available for this response key
    (union of default + current + templates)."""
    names = []
    seen = set()
    for src in (default, current or "", *[t for _, t in get_response_templates(key, default) if t]):
        for p in extract_placeholders(src):
            if p not in seen:
                seen.add(p)
                names.append(p)
    return names
