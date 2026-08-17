# ============================================================
# 🎨 RESPONSE TEMPLATES  (v170.22)
# ============================================================
# ✏️ Edit Responses (Admin → ⚙️ Settings → ✏️ Edit Responses) ab
# har response ke liye 2 READYMADE templates dikhata hai + custom
# option (placeholders ke sath).
#
#   • Template 1 ("Style A") = DEFAULT_RESPONSES[key]  (classic)
#   • Template 2 ("Style B") = RESPONSE_TEMPLATE_B[key] (alternative)
#
# 🛡️ SAFETY RULE: har template sirf WAHI placeholders use kar sakta hai
# jo us key ke DEFAULT me already maujood hain — warna runtime `.format()`
# crash ho sakta hai (KeyError). Test karta hai ye (see test_response_templates).
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


# ── Style B (alternative) templates ─────────────────────────
# Har key ke liye 1 alternative. Template 1 hamesha default hota hai.
RESPONSE_TEMPLATE_B = {
    # 🏠 MAIN MENU & NAVIGATION
    "welcome": """👋 Welcome to {shop_name}!

━━━━━━━━━━━━━━━━━━━━

🆔 Your User ID: `{user_id}`

⚡ Pay with Binance Pay — instant auto-verification.""",

    "fj_verified_done": """✅ Verified!

Welcome aboard {shop_name}! 🛍️

Ab aap bot use kar sakte hain. Enjoy!""",

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

Koi ek category choose karo:""",

    "product_detail": """📦 *{name}*
━━━━━━━━━━━━━━━━━━━━

📝 {description}

💰 Price: *${price}* (~ *{pkr}*)
📊 Stock: *{stock}*""",

    "no_products": "🛒 Abhi koi product available nahi hai.\nJald wapis aana!",

    "out_of_stock": "😔 Ye product abhi out of stock hai.",

    "confirm_purchase": """🛒 *Purchase Confirm Karein*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*
💰 Price: *${price}* ≈ *{pkr}*
🔢 Quantity: *1*

Payment method chunein:""",

    "confirm_bulk_purchase": """🛒× *Buy Multiple*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*
💰 Unit Price: *${price}* ≈ *{pkr}*
📊 Stock: *{stock}*

✍️ Quantity likhein (sirf number):
*Example: 5*

Max: {stock}""",

    "bulk_confirmed": """🛒× *Bulk Purchase Confirm*
━━━━━━━━━━━━━━━━━━━━
📦 *{product}*
💰 Unit: ${unit_price} × *{qty}*
━━━━━━━━━━━━━━━━━━━━
💵 *Total: ${total}* ≈ *{pkr}*

Payment method chunein:""",

    # 💳 PAYMENT SCREENS
    "buy_points": """💎 *Points Khareedein*
━━━━━━━━━━━━━━━━━━━━

💎 Aapke Points: *{points}*
💰 Rate: $1 = {rate} Points

Payment method chunein:""",

    "payment_verified_points": """✅ *Payment Verified!*
━━━━━━━━━━━━━━━━━━━━

💎 *{pts} Points* added!

💰 Amount: ${amount} {currency}
🆔 Order ID: `{order_id}`

Shukriya! 🙏""",

    "payment_verified_product": """🎉 *Order #{order_id} Delivered!* ✅
━━━━━━━━━━━━━━━━━━━━

📦 {product}

📨 *Aapka Product:*
━━━━━━━━━━━━━━━━━━━━
{delivery}
━━━━━━━━━━━━━━━━━━━━

💎 +{points} points earned!
Thank you! 🙏""",

    "order_rejected": "❌ Order #{order_id} reject ho gaya.\nMadad ke liye support se raabta karein.",

    "referral_text": """🎁 *Referral Program*
━━━━━━━━━━━━━━━━━━━━

🔗 Aapka Link:
`{ref_link}`

👥 Referrals: *{ref_count}*
💎 Points: *{ref_points}*

📋 Share → Wo join kare → Aapko *{points_per_ref} point* mile!""",

    "no_transactions": "💳 Abhi koi deposit nahi.\n\n💎 Buy Points se funds add karein.",

    "no_orders": "📜 Abhi koi order nahi hai.",

    "orders_title": "🧾 *Aapke Orders:*\n━━━━━━━━━━━━━━━━━━━━",

    # 📞 SUPPORT & OTHER
    "support_text": """🎧 *Support*
━━━━━━━━━━━━━━━━━━━━

Apna tareeqa chunein:""",

    "terms": """📜 *Terms & Conditions*
━━━━━━━━━━━━━━━━━━━━

1. All sales are final — no refunds
2. Digital products delivered instantly
3. Do not share purchased items
4. Payment within 30 minutes

*Last updated: May 2026*""",

    "binance_instructions": """⚠️ *Zaroori Instructions:*
• Apna *exact Binance sender name* likhein
• *Exact* amount pay karein
• Payment ke baad *Verify Payment* tap karein
• Verify na ho to *1 minute* baad dobara try karein""",

    "new_user_notification": """👤 *Naya User Aaya!*
Name: {name}
Username: @{username}
ID: `{user_id}`""",

    "cancelled_message": "❌ *Cancel ho gaya.*\n\nMain menu par wapas aa gaye.",

    "support_menu_header": """🎫 *Support Center*
━━━━━━━━━━━━━━━━━━━━

Help chahiye? Ticket banayein!
📞 *WhatsApp:* `+{whatsapp}`

📋 *Aapke Tickets:* {total}
🟡 *Open:* {open}

Option chunein:""",

    "warranty_menu_header": """🛡️ *Warranty & Refund*
━━━━━━━━━━━━━━━━━━━━

Koi order chunein:""",

    "warranty_no_orders": """🛡️ *Warranty & Refund*
━━━━━━━━━━━━━━━━━━━━

Koi delivered order nahi mila.
Warranty/refund sirf delivered orders ke liye hai.""",

    "reviews_menu_header": """⭐ *Reviews & Ratings*
━━━━━━━━━━━━━━━━━━━━

📝 Mere reviews: {my}
✍️ Review baqi: {pending}

Apna tajurba share karein!""",

    "loyalty_menu_header": """🏆 *Loyalty Program*
━━━━━━━━━━━━━━━━━━━━""",

    "language_menu_header": """🌐 *Language Chunein*
━━━━━━━━━━━━━━━━━━━━

Apni pasand ki language select karein:""",

    # 🎁 FREE CLAIM / FREEBIES
    "freeclaim_user_screen": """🎁 *Ye Product FREE Paayein!*

📦 *{product}*
👥 Required Referrals: *{required}*
✅ Aapke Referrals: *{available}*

🎉 *Aap eligible hain!* *Claim Now* tap karein.""",

    "freeclaim_not_enough": """🎁 *Ye Product FREE Paayein!*

📦 *{product}*
👥 Required: *{required}*
📊 Aapke paas: *{available}*
📉 *{missing}* aur referrals chahiye.

🔗 Apna referral link share karein — jo /start karega, count barhega!""",

    "freebies_menu_header": """🎁 *Freebies*
━━━━━━━━━━━━━━━━━━━━

_Ye products bilkul FREE hain — abhi claim karo!_""",

    "freebies_empty": """🎁 *Freebies*
━━━━━━━━━━━━━━━━━━━━

_Abhi koi free product nahi. Baad mein aana!_""",

    "freebie_success": """🎉 *Freebie Claimed!*
━━━━━━━━━━━━━━━━━━━━

📦 {product}
✅ Upar FREE deliver ho gaya.

🔁 Dobara claim ke liye: {reclaim} referrals.""",

    "freebie_need_refs": """🔁 Dobara claim ke liye *{required} referrals* chahiye.
👥 Aapke referrals: *{have}*
⭐ Aur *{missing}* chahiye.""",

    "freebie_claim_limit": "❌ Is product ki claim limit poori ho gayi.",

    "freebie_out_of_stock": "😔 Abhi out of stock hai. Thori dair baad try karein.",

    "freeclaim_share_message": """🎁 Mein {product} FREE le raha hoon {shop} par!

Aap bhi chahiye? Bohat asaan:
1️⃣ Neeche mera link click karein
2️⃣ Telegram mein open karein
3️⃣ Start tap karein — bas ho gaya!

👇 Mera link:
{link}""",

    "freeclaim_share_screen": """🔗 *Aapka Share Link*
━━━━━━━━━━━━━━━━━━━━

📦 *{product}*
🎁 Chahiye: *{required}* referrals
📊 Aapke paas: *{available}*

🔗 *Copy karne ke liye long-press karein:*
`{link}`

📝 *Share message preview:*
```
{preview}
```""",

    "shop_no_unavailable": """✅ *Sab Available Hai!*
━━━━━━━━━━━━━━━━━━━━

Abhi koi out-of-stock product nahi — sab kuch available hai!

*📋 Show All Products* tap karein.""",

    "shop_no_available": """😔 *Sab products out of stock hain.*
━━━━━━━━━━━━━━━━━━━━

Jald restock ho raha hai! *📋 Show All Products* se wapis aane wale products dekhein, ya out-of-stock list se 🔔 stock alert lagayein.""",

    # 🔶 BINANCE
    "binance_orderid_instructions": """🟡 *Binance Pay Checkout*
━━━━━━━━━━━━━━━━━━━━

{title}
💵 Amount: *${amount}*

📋 *Step 1 — Payment bhejein*
  • Pay ID:  `{pay_id}`
  • Name:    *{holder}*
  • Amount:  *${amount}*

📨 *Step 2 — Order ID bhejein*
Payment ke baad Binance app se *Order ID* copy karein aur yahan paste karein.

_Order kuch seconds mein auto-confirm ho jayega._""",

    "refund_processed": """💸 *Refund Processed*
━━━━━━━━━━━━━━━━━━━━

Ye product abhi unavailable hai, is liye aapki payment refund ho rahi hai.

📦 Order: `#{order_id}`
📌 Product: *{product}*
💰 Amount: *${amount}*

✅ *{points} Points credited* aapke wallet mein (instant refund).
💎 Naya balance: *{new_balance} Points*

Ye points aap store ke doosre products ke liye use kar sakte hain.""",

    "order_cancelled_with_reason": """❌ *Order Cancelled*
━━━━━━━━━━━━━━━━━━━━

📦 Order: `#{order_id}`
📌 Product: *{product}*
💰 Amount: `${amount}`

📋 *Wajah:* _{reason}_

Agar aapne pay kar diya hai to refund ke liye support se raabta karein.""",

    "order_cancelled_no_reason": """❌ *Order Cancelled*
━━━━━━━━━━━━━━━━━━━━

📦 Order: `#{order_id}`
📌 Product: *{product}*
💰 Amount: `${amount}`

Agar aapne pay kar diya hai to refund ke liye support se raabta karein.""",

    "payment_binance_menu_text": """🔶 *Binance Payment Methods*
━━━━━━━━━━━━━━━━━━━━
Binance se pay karne ka tareeqa chunein.

• Binance Pay — payment ke baad Order ID paste karein
• USDT BEP20 — payment ke baad TXID paste karein
• USDT TRC20 — payment ke baad TXID paste karein""",

    "payment_bybit_menu_text": """🟡 *Bybit Payment Methods*
━━━━━━━━━━━━━━━━━━━━
Bybit se pay karne ka tareeqa chunein.

• Bybit Pay — payment ke baad Transaction Hash paste karein
• USDT BEP20 — payment ke baad Transaction Hash paste karein
• USDT TRC20 — payment ke baad Transaction Hash paste karein""",

    "payment_binance_pay_orderid": """🔶 *Binance Pay — Checkout*
━━━━━━━━━━━━━━━━━━━━
{title}
💰 Amount: *{amount} USDT*
📋 Binance Pay ID: `{pay_id}`
👤 Holder: *{holder}*

*Pay kaise karein:*
1. Binance app kholein.
2. Binance Pay mein jayein.
3. Exact amount bhejein.
4. Receipt se *Order ID* copy karein.
5. Yahan chat mein paste karein.

⚠️ Sirf exact amount bhejein.""",

    "payment_binance_usdt": """🪙 *Binance {method_label} — Order #{order_id}*
━━━━━━━━━━━━━━━━━━━━
💰 Amount: *{amount} USDT*
🌐 Network: *{network_label}*

📥 *Is address par bhejein*
`{address}`

*Zaroori:*
✅ Coin USDT ho
✅ Network {network_label} ho
✅ Exact amount bhejein
❌ Galat network/coin use na karein

*Bhejne ke baad:*
1️⃣ Wallet → transaction kholen
2️⃣ 🧾 *TXID (transaction hash)* copy karein
3️⃣ 📨 *Yahan chat mein paste karein*

🤖 Bot blockchain check karke balance add kar dega.""",

    "payment_bybit_pay": """🟡 *Bybit — Order #{order_id}*
━━━━━━━━━━━━━━━━━━━━
💰 Amount: *{amount} USDT*
📥 Bybit UID par bhejein: `{pay_id}`

📲 *Steps (sirf Internal Transfer — Bybit Pay nahi):*
1️⃣ Bybit App → *Assets* → *Withdraw*
2️⃣ *Crypto Withdrawal* chunein
3️⃣ *USDT* coin chunein
4️⃣ Transfer Type → *Internal Transfer* 🔁
5️⃣ Upar *UID* select karein
6️⃣ Ye UID paste karein: `{pay_id}`
7️⃣ Exact amount: *{amount} USDT*
8️⃣ *Withdraw* tap karein ✅

🔙 Bot par wapas → *🔍 Check Payment* tap karein.

⚠️ Bybit Pay use NA karein — sirf Internal Transfer auto-detect hota hai.""",

    "payment_bybit_pay_reference": """🔖 *Aapka Reference ID:* `{reference_id}`
_Tip: bhejte waqt Reference/Note field mein paste karein taake turant match ho. Zaroori nahi — UID + exact amount kaafi hai._""",

    "payment_bybit_usdt": """🟡 *{method_label} — Order #{order_id}*
━━━━━━━━━━━━━━━━━━━━
💰 Amount: *{amount} USDT*
🌐 Network: *{network_label}*

📥 *Is address par bhejein*
`{address}`

*Zaroori:*
✅ Coin USDT ho
✅ Network {network_label} ho
✅ Exact amount bhejein
❌ Galat network/address verify nahi hoga

Payment ke baad *Transaction Hash* yahan paste karein.""",

    "payment_not_found_txid": """⏳ *Transaction Abhi Nahi Mili*
━━━━━━━━━━━━━━━━━━━━
Agar pay kar diya hai to thori dair mein *🔄 Check Again* tap karein — ya sahi Transaction / Transfer ID paste karein.

Yaqeeni banayein:
• amount exact ho
• sahi network/payment method use kiya ho
• ID Bybit receipt se match kare

📲 *Bybit tip:* Bybit app mein *Bybit Pay → balance* check karein. Agar payment wahan dikhe to *Funding account* mein *Transfer* karein, phir bot mein *Check Payment* dabayen.

Phir bhi verify na ho to support se raabta karein.""",

    # ⭐ STARS
    "stars_pay_instructions": """⭐ *Telegram Stars se Pay Karein*
━━━━━━━━━━━━━━━━━━━━

🧾 Order: `#{order_id}`
💰 Amount: *${amount}*
⭐ Stars chahiye: *{stars} Stars*
📊 Rate: 1$ = {rate} Stars

👇 Neeche button tap karein — Telegram ki secure payment window khulegi.
_Stars foran credit ho jayenge._""",

    "stars_payment_success": """🎉 *Deposit Successful!*
━━━━━━━━━━━━━━━━━━━━

✅ Aapki Stars payment confirm ho gayi.
💎 Points Added: *{points}*
💰 Amount: *${amount}*
🧾 Order ID: *#{order_id}*

_Shukriya!_""",

    "payment_stars_checkout": """⭐ *Stars — Product Checkout*
━━━━━━━━━━━━━━━━━━━━

📦 Product: *{product}*
🧾 Order: `#{order_id}`
💰 Total: *${amount}*
⭐ Stars: *{stars} Stars*
📊 Rate: 1$ = {rate} Stars

👇 Button tap karein — payment ke foran product deliver hoga!""",

    "payment_stars_deposit": """⭐ *Stars — Deposit*
━━━━━━━━━━━━━━━━━━━━

🧾 Order: `#{order_id}`
💰 Deposit: *${amount}*
⭐ Stars: *{stars} Stars*
📊 Rate: 1$ = {rate} Stars

👇 Button tap karein — points foran wallet mein aa jayenge!""",

    "payment_stars_success": """🎉 *Payment Successful!*
━━━━━━━━━━━━━━━━━━━━

✅ Stars payment confirm.
💎 Points Added: *{points}*
💰 Amount: *${amount}*
🧾 Order ID: `#{order_id}`

_Shukriya!_""",

    "payment_stars_menu_text": """⭐ *Telegram Stars Payment*
━━━━━━━━━━━━━━━━━━━━
Telegram ke andar hi fast & secure payment.

• 1$ = 120 Stars (Admin Edit kar sakta hai)
• Koi external wallet/UID/TXID nahi chahiye.
• Payment confirm hote hi instant delivery.""",

    # 🟡 BYBIT
    "bybit_warning_text": """⚠️ *Transfer se pehle dhyan se parhein*
━━━━━━━━━━━━━━━━━━━━

🔢 *Poori amount decimals ke sath copy karein* (e.g. 5.0087)

💯 *Bybit app mein jo amount dikhe WAHI bhejein*

🧾 Amount bilkul match honi chahiye — decimals samet

❗️ Decimals mein zara sa farq = bot transfer detect nahi karega.

_Continue tap karein, ya Cancel se wapas jayein._""",

    "bybit_uid_prompt": """🆔 *Apna Bybit UID likhein*
━━━━━━━━━━━━━━━━━━━━

Bybit app → Profile (naam ke paas) mein milega.

Sirf digits, e.g. `543120799`

_Transfer auto-detect karne ke liye chahiye._""",

    "bybit_uid_invalid": """❌ *Galat Bybit UID*
━━━━━━━━━━━━━━━━━━━━

Bybit UID sirf numbers hota hai (e.g. `543120799`).

Dobara bhejein — Bybit app → Profile mein milega.""",

    "bybit_amount_prompt": """🟡 *Bybit se Deposit — UID*
━━━━━━━━━━━━━━━━━━━━

💡 *Kitna deposit karna hai? (USD amount likhein):*

📌 Examples: 5 / 10 / 25 / 50
⚠️ Minimum: $1

_Sirf number likhein._""",

    "bybit_amount_invalid": """❌ *Galat amount*
━━━━━━━━━━━━━━━━━━━━

Sirf number likhein, e.g. `1`, `5`, `10`.
Minimum: $1""",

    "bybit_deposit_instructions": """💸 *Bybit Internal Transfer se Bhejein* (Bybit → Bybit)
━━━━━━━━━━━━━━━━━━━━

💰 Amount: *{amount} USDT*
📥 Bybit UID par bhejein: `{store_uid}`

📲 *Steps:*
1️⃣ Bybit App → *Assets*
2️⃣ *Withdraw* tap karein
3️⃣ *Crypto Withdrawal* chunein 💱
4️⃣ *USDT* coin chunein
5️⃣ Transfer Type → *Internal Transfer* 🔁
6️⃣ Upar *UID* select karein 🆔
7️⃣ Ye UID paste karein: `{store_uid}`
8️⃣ Exact amount: *{amount}*

9️⃣ *Withdraw* ✅ → confirm
🔟 Bot par wapas → *🔍 Check Payment*

⚠️ *Bybit Pay* use NA karein.
✏️ Reference (optional): `{reference_id}`
⏰ Valid for: 30 minutes""",

    "bybit_check_payment_ok": """✅ *Bybit Payment Verified!*
━━━━━━━━━━━━━━━━━━━━
Amount: *{amount} USDT*
Sender UID: `{uid}`

Aapka balance add ho gaya.""",

    "bybit_cancelled": """❌ *Bybit payment cancel.*
━━━━━━━━━━━━━━━━━━━━

Koi amount charge nahi hui.""",

    "bybit_usdt_warning_text": """⚠️ *Transfer se pehle dhyan se parhein*
━━━━━━━━━━━━━━━━━━━━

🔢 *Poori amount decimals ke sath copy karein* (e.g. 5.0087)

💯 *Bybit app mein jo amount dikhe WAHI bhejein*

🧾 Amount bilkul match honi chahiye — decimals samet

❗️ Decimals mein zara sa farq = bot transfer detect nahi karega.

━━━━━━━━━━━━━━━━━━━━
💸 *Fee note:* network fee kat ti hai to upar se add karein taake poori amount pahunchay.
Network fees ki zimmedari hum par nahi.

_Continue tap karein, ya Cancel se wapas jayein._""",

    "bybit_usdt_amount_prompt": """🟡 *USDT se Deposit — {network_label} Network*
━━━━━━━━━━━━━━━━━━━━

💡 *Kitna deposit karna hai? (USD amount likhein):*

📌 Examples: 5 / 10 / 25 / 50
⚠️ Minimum: $1

_Sirf number likhein._""",

    "bybit_usdt_amount_invalid": """❌ *Galat amount*
━━━━━━━━━━━━━━━━━━━━

Sirf number likhein, e.g. `1`, `5`, `10`.
Minimum: $1""",

    "bybit_usdt_deposit_instructions": """💸 *Bybit — USDT — {network_label} Network*
━━━━━━━━━━━━━━━━━━━━

✉️ *Address:*
`{address}`

💰 *Amount (exact):*
*{amount}*

⚠️ *Sahi network use karein — galat network par bhejne se amount loss ho jati hai.*
⏰ Expiry: 30 minutes
✨ Confirm hote hi balance add ho jayega""",

    "bybit_usdt_cancelled": """❌ *Bybit USDT payment cancel.*
━━━━━━━━━━━━━━━━━━━━

Koi amount charge nahi hui.""",

    # 🔗 RESELLER API
    "reseller_api_landing": """🔗 *Reseller API*
━━━━━━━━━━━━━━━━━━━━

👉 Hamare products apne bot ya website par bechein!

🔑 *Generate API Key* tap karke apni key banayein.
💳 Key aapke wallet se judi hai (💎 Buy Points se top-up karein).
📦 Har order auto-deliver hota hai aapke bot par.

_Key sirf EK baar dikhti hai — save kar lein!_""",

    "reseller_api_generated": """✅ *Nayi API Key Ban Gayi!*
━━━━━━━━━━━━━━━━━━━━

🔑 *Aapki Key:*
`{api_key}`

⚠️ *Abhi save kar lein — agli baar masked dikhegi.*

📡 Header: `X-API-Key: {api_key}`""",

    "reseller_api_panel": """🔗 *API Access*
━━━━━━━━━━━━━━━━━━━━
Apni API key se products apne bot/website par bechein.

🔑 *API Key:*
`{prefix}....`

💳 Balance: *${balance:.2f}*
📨 Total requests: *{requests}*
📅 Created: *{created}*""",

    "reseller_api_fullkey": """🔑 *Aapki Poori Key*
━━━━━━━━━━━━━━━━━━━━

`{api_key}`

📡 Header: `X-API-Key: {api_key}`""",

    "reseller_api_regenerate": """🔄 *Nayi Key Ban Gayi!* (purani revoke)
━━━━━━━━━━━━━━━━━━━━

🔑 `{api_key}`

⚠️ *Abhi save karein — sirf EK baar dikhegi.*

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
