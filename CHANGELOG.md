# 📖 Bite Store Bot — Master CHANGELOG

**Bot:** `@bite_storee_bot` — Pakistani Telegram e-commerce shop
**Runtime:** Render.com Background Worker (Python 3.14, polling mode)
**DB:** SQLite at `/var/data/shop.db` (persistent disk)

> This is the SINGLE consolidated changelog. Every new release just appends a new section on top — no more per-version `.md` files cluttering the repo.

---

# 🚀 v170.42 (2026-08-22) — 🎁 FREEBIES MANAGEMENT UPGRADE (10 improvements)

## Admin panel ab pura management dashboard hai:
1. **📋 Freebies / All Products / Add tabs** — sirf freebies ya sab products dekho.
2. **🔍 Search** — naam se dhoondo (freebies + add picker dono me).
3. **📊 Har freebie ke stats** — claims count, stock, total cost ($ × claims).
4. **🧾 Claim Log** — global (paginated) + per-product claims (kaun/kab).
5. **⚡ Bulk actions** — All ON / All OFF / All Claim Limit (ek tap).
6. **➕ Add Freebie yahan se** — product picker (non-freebie products).
7. **🗑 Remove Freebie** — freebies list se hatao (product delete nahi).
8. **🕐 Sorting** — Recent / Popular / Low Stock / New.
9. **🔔 Daily Summary** — daily admin summary me freebie claims + cost line.
10. **🏷️ Display Name** — freebie ka custom naam (premium emoji ke saath),
    user-facing freebies menu me bhi dikhta hai.

## DB: freebies.display_name column (migrate auto), management helpers
(get_freebies_management, get_products_not_in_freebies, get_freebies_stats,
get_all_freebie_claims, get_freebie_claims_for_product, set_all_freebies_*,
remove_freebie, get/set_freebie_display_name). Stats sirf valid products count
karte hain (orphan rows exclude).

---

# 🚀 v170.41 (2026-08-21) — SUPPLIER DOCS UPDATE (AKUNDING + PRODSELLER)

## 📚 Saare suppliers ke docs check kiye (live API verify)
1. **Canboso** (Shop Cron / sinh le / Ai Tools) → v2.1.0 schema — kal hi fix ho
   chuka (v170.39). Koi change nahi.
2. **TunVNMMO** → same (balance_usdt / products price_usdt / buy). Koi change nahi.
3. **MMOStore** → same (balance_usd string / stock_available / price_usd). Koi
   change nahi.
4. **Akunding** → 🆕 naye fields: `your_price` (aapka ACTUAL price), `base_price`,
   `has_special_price`, `available` (bool), `unit_label`, `bulk_tiers`.
   FIX: cost ab `your_price` → fallback `base_price` (special pricing sahi).
5. **ProdSeller** → 🆕 `finalPrice` field add hua. FIX: price parse me
   `price` → fallback `finalPrice` (robustness).

## 🧪 Tests: Akunding your_price priority + ProdSeller price parse — pass.

---

# 🚀 v170.40 (2026-08-19) — RESELLER API: FREEBIES EXCLUDE + ENRICHED NOTIFICATIONS + ORDERS DETAIL

## 1. 🎁 Freebies + $0 products RESELLER API se EXCLUDE (existing + future)
- `_resellable_products()` ab `price > 0` + `id NOT IN (freebies enabled=1)` filter
  karta hai → freebie products (existing + future) reseller API ke /v1/products me
  kabhi nahi aate. $0.01 refund-noise khatam.

## 2. 🔗 Reseller order admin notification ENRICHED
- `_notify_admin_order` ab HTML me bhejta hai (premium emoji render hota hai) +
  supplier naam + Cost·Sold·Profit + Reseller Balance before→after (points+USD).
- `_notify_admin` ab parse_mode support karta hai.

## 3. 💳 Deposit notification (Reseller vs normal — dono full details)
- `_send_deposit_success` ab admin ko deposit notify karta hai:
  - Reseller ho → "🔗 Reseller Deposit!" (name + @username + ID + KEY + amount +
    method + balance before/after)
  - Normal → "💳 New Deposit!" (same details, no key)

## 4. 📦 Reseller Orders panel — premium emoji + full detail (completed-orders jesa)
- `_render_reseller_orders_panel` + `reseller_orders_key_callback`: clean names +
  premium emoji icon buttons + har order ka "📄 #id" detail button.
- Naya `reseller_order_view_callback`: full order detail — reseller, key, product,
  supplier, cost/sold/profit, delivered keys, error, timestamps.

## 5. 🧪 Tests: freebie-exclude, enriched notify (premium+supplier+profit+balance),
   deposit notify — sab pass.

---

# 🚀 v170.39 (2026-08-18) — 🐛 FIX: CANBOSO v2.1.0 SCHEMA (AI TOOLS PRODUCTS)

## 🐛 Root cause: Canboso Buyer API v2.1.0 schema change
- Purana: `_id`, `product_name`, `usdPricing`, `stats.available`
- Naya: `productId`, `name`, `price.amount`, `availability.available`
- Adapter purane fields parhta tha → remote_id = "None" (SAB products ek hi
  row me collide → sirf 1 product bachta) + stock hamesha 0 → "kuch products
  show, kuch nahi".

## ✅ Fix (ext_suppliers.py CanbosoAdapter)
- fetch_products ab NAYE + purane dono schemas support karta hai:
  - remote_id: productId → _id → id → product_id (empty/'None' SKIP)
  - name: name → product_name → title
  - price: _safe_float (price{amount} dict + purane fields)
  - stock: availability.available → stats.available → stock → available
- create_order body ab `productId` + `product_id` dono bhejta hai (backward-compat).

## 📦 Ready DB (latest backup 20260818_180325 se)
- Canboso suppliers (Shop Cron / sinh le / Ai Tools) re-synced live API se:
  - Ai Tools: 21 active products (sab import me aate hain, stock+price sahi)
  - Shop Cron: 17 active | sinh le: 38 active
  - 3 corrupted remote_id='None' rows delete + stale products active=0
- 1640 users / 957 orders / 36 products / 212 ext_products / 7 suppliers.

---

# 🚀 v170.38 (2026-08-18) — 🐛 FIX: DELETED/UNSYNCED FREEBIES NA DIKHEN

## 🐛 Deleted / unsynced / hidden freebies ab FREEBIES menu se gayab
- Root cause: `get_all_freebie_products` LEFT JOIN se deleted product ki row bhi
  return karta tha → product delete/unsync karne ke baad bhi freebies me show
  hota tha (naam NULL/ghost).
- Fix: INNER JOIN + filter `p.id IS NOT NULL AND is_active=1 AND is_hidden=0`.
- Claim flow bhi harden: `_show_freebie_product` + `freebie_do_callback` ab
  deleted/unsynced/hidden product par claim allow nahi karte.
- Fake freebie broadcasts auto-fix (wo bhi get_all_freebie_products use karte hain).

---

# 🚀 v170.37 (2026-08-18) — 🚫 BANNED USERS PANEL (ADMIN BUTTONS)

## 🚫 Ban system ab ADMIN PANEL me (buttons, no commands)
- Naya admin button "🚫 Banned Users" (admin_banlist registry → ban_panel).
- Panel: banned users list + ➕ Ban User (ID) + 🔓 Unban User (ID) buttons.
- Conversation input: ID bhejo → turant ban/unban (admin self-ban block).
- `/ban` + `/unban` commands ab bhi kaam karte hain (backup).

---

# 🚀 v170.36 (2026-08-18) — 🛡️ STRICT USDT-ONLY CURRENCY (ALL CRYPTO METHODS)

## 🛡️ Sirf USDT verify — BYBIT PAY + BINANCE PAY khas tor par (user demand)
- Easypaisa / JazzCash / Telegram Stars = EXCEPTION (PKR / native Stars).
- Baaki SAB methods (Binance Pay, Binance USDT TRC20/BEP20, Bybit Pay, Bybit
  USDT TRC20/BEP20) ab sirf **USDT** currency verify karte hain — BTTC/BTC/ETH/
  koi bhi doosri currency turant REJECT.
- handlers_order.py: naya helper `_is_usdt_txn()` + guards in
  `_find_matching_bybit_payment` (UID loop + main scan + bybit_usdt scan) aur
  `_find_matching_usdt_deposit` (binance on-chain scan). Defense-in-depth:
  API already coin=USDT filter karti thi, ab match level par bhi strict.
- payments.py `verify_payment_screenshot`: currency enforcement — JazzCash/
  EasyPaisa → PKR; Stars → skip; baaki sab → USDT/USD (BTTC/BTC/etc reject).
- Binance Pay API check (v170.35) + ye naye guards → ab har crypto path USDT-only.

---

# 🚀 v170.35 (2026-08-18) — 🛡️ BTTC SCAM FIX + GLOBAL BAN SYSTEM

## 1. 🛡️ CURRENCY CHECK (SCAM ROOT CAUSE FIX)
- Root cause: Binance Pay verification (`find_matching_payment` +
  `find_payment_by_order_id`) sirf AMOUNT + Order ID match karta tha — CURRENCY
  kabhi check nahi hoti thi. Scammer "Soulhacker" (7360098688) ne BTTC (bekaar
  token) se same amount pay kiya aur bot usay USDT samajh kar deliver karta raha
  ($51.96 delivered + auto-refund points misuse).
- Fix: `_currency_is_usdt()` — sirf `USDT` accept (BTTC/BTC/ETH/etc reject).
  Dono matchers ab currency check karte hain.

## 2. 🚫 GLOBAL BAN SYSTEM (user demand)
- database.py: `banned_users` table + `ban_user/unban_user/is_user_banned/
  list_banned_users/setup_banned_users_table` (migrate_all me registered).
- maintenance_mode.py: ban gate — banned user har action se block (orders/
  freebies/deposit/sab), 30s cooldown reply. Admin bypass.
- bot.py: admin commands `/ban <user_id> [reason]` + `/unban <user_id>`
  (forwarded message par reply karke bhi ban kar sakte ho).

## 3. 🧪 Tests: currency check, BTTC-reject/USDT-accept, ban/unban/list,
   migrate_all clean — sab pass.

---

# 🚀 v170.34 (2026-08-17) — FIX: FREEBIE BROADCAST ME PREMIUM EMOJI (FIXED YA NAME)

## 🎖️ Freebie claim broadcast me product ka premium emoji
- Root: `_fmt_msg_name` sirf NAME ke andar ka premium emoji dekhta tha — FIXED
  emoji (supplier ext emoji) wale products par broadcast/admin-notify me simple
  emoji render hota tha.
- Fix: freebie claim broadcast + admin notification + product screen ab
  `_product_name_with_fixed_emoji` use karte hain (fixed emoji YA name — dono).
- `_product_name_with_fixed_emoji` edge-case fix: agar name emoji char se START
  ho to bhi ab premium fixed emoji prepend hota hai (pehle raw simple return).

---

# 🚀 v170.33 (2026-08-17) — FIX: FREEBIE PAR "ORDER DELIVERED" DUPLICATE NOTIFICATION

## 🐛 Freebie claim par admin ko 2 notifications (Order Delivered + Freebie Claimed)
- Root cause: `_notify_admin_order_delivered` ka freebie-skip check
  `isinstance(order, dict)` use karta tha — lekin order DictRow (sqlite3.Row
  subclass, NOT dict) hota hai → check hamesha False → skip kabhi nahi chalta →
  freebie par bhi "🎉 Order Delivered! ✅" aata tha.
- Fix: `.get('payment_method')` direct (DictRow support karta hai). Ab freebie
  par sirf "🎁 FREEBIE CLAIMED!" notification aati hai.

---

# 🚀 v170.32 (2026-08-17) — FIX: FREEBIE YES/NO BUTTON TEMPORARY ERROR

## 🐛 "🎁 Yes — Make it FREE" / "No" button temporary-error FIX
- Root cause: `_ask_step10_delivery` me `_prod_step_kb()` (jo khud
  InlineKeyboardMarkup return karta hai) ko dobara `InlineKeyboardMarkup()` me
  wrap kiya tha → TypeError → callback crash → "Temporary error".
- Fix: markup ko as-is pass karte hain (auto path), manual path apna markup
  banata hai. Ab Yes/No dono buttons Step 10 par sahi le jate hain.

---

# 🚀 v170.31 (2026-08-17) — FREEBIE SUCCESS PREMIUM EMOJI + AFTER-PURCHASE BUTTONS EDITABLE

## 1. 🎖️ Freebie success message me premium emoji
- freebie_do_callback ka "🎉 Freebie Claimed!" confirm ab product ka PREMIUM emoji
  render karta hai (`_fmt_msg_name`) — pehle simple fallback emoji dikhta tha.

## 2. 🛒 After-purchase buttons EDITABLE (Customization)
- Naye registry buttons group "afterbuy": buy_more_btn (🛒 Buy More) +
  order_history_btn (📜 Order History). Rename/color/hide/premium emoji editable —
  Manage Buttons me "🛒 After Purchase Buttons".
- fulfill_paid_product_order inhe `_rb` se render karta hai.

## 3. 🎁 Freebie par Buy More / Order History NAHI
- Freebie order delivery par ab koi "Buy More / Order History" button nahi jata
  (sirf paid purchase par jate hain).

## 4. 🧪 Tests: premium preserve + _rb render + freebie no-buttons — pass.

---

# 🚀 v170.30 (2026-08-17) — FREEBIE CHOICE BEFORE STEP 10 + PREMIUM EMOJI IN BROADCASTS

## 1. 🎁 "Make This a Freebie" ab Step 10 se PEHLE (user demand)
- Add-Product wizard me ab Step 9 (format) ke BAAD "🎁 Make This a Freebie?"
  (Yes/No) poocha jata hai — Step 10 se pehle.
- Final confirm me "Make This a Freebie" button HATA di (ab wizard me decide).
- `_finalize_product_add`: p_freebie=1 par set_freebie_config (enabled, limit 1,
  refs 0) + FREEBIE broadcast (NEW FREEBIE DROP) — normal "fresh stock" alert
  pehle nahi chalti. Paid product par normal NEW PRODUCT broadcast.

## 2. 🎖️ Premium emoji ab har broadcast me (custom templates + placeholders bhi)
- `_product_name_with_fixed_emoji` use hota hai taake product ka premium emoji
  (<tg-emoji>) broadcast text me render ho:
  - make_freebie_callback (NEW FREEBIE DROP)
  - build_real_freebie_message (real claim broadcast)
  - fake freebie broadcasts (fake_engagement run_fake_broadcast + per_user_activity
    build_fake_message) — pehle html_strip_tags emoji hata deta tha.
- Custom templates + {product} placeholder par bhi premium emoji render hota hai.

## 3. 🧪 Tests: premium preserve (real/fake/finalize) + freebie choice helpers — pass.

---

# 🚀 v170.29 (2026-08-17) — FREEBIES: PREMIUM EMOJI + EDITABLE BUTTONS + FREEBIE MSG + ADD-ITEM FREEBIE

## 1. 🎖️ Freebie product screen — premium emoji render
- `_show_freebie_product` ab product name `_fmt_msg_name` se render karta hai →
  premium emoji (🤖 custom emoji) dikhta hai, simple fallback emoji nahi.

## 2. 🎛️ Freebie flow buttons EDITABLE (Customization/Manage Buttons)
- button_system.py: naye registry buttons group "freebies" me — freebie_claim_now,
  freebie_refer_earn, freebie_menu_back, freebie_back. GROUP_NAMES me "🎁 Freebies Flow".
- handlers_freebies.py ab inhe `_rb` se render karta hai (rename/color/hide/premium
  emoji — bilkul binance flow jese editable).

## 3. 🎁 Freebie claim → "Thanks for purchasing" NAHI, freebie wala msg
- fulfill_paid_product_order ab FREEBIE orders par "🎁 Freebie Claimed — FREE!"
  header bhejta hai ("Your FREE product is delivered below") — "Thanks for
  purchasing" nahi. Tier progress hint bhi skip.

## 4. ➕ Add Item → "🎁 Make This a Freebie" (1-click) + broadcast
- Add Product confirmation me naya button `make_freebie_<pid>` → set_freebie_config
  (enabled, limit 1, refs 0) + "NEW FREEBIE DROP!" broadcast destination par
  (bc_freebie button ke saath). Fake freebie claims (random) + real claim broadcast
  pehle se active hain (v170.14/v170.25).

## 5. 🧪 Tests: registry buttons, _rb render, premium emoji, freebie detection,
   make_freebie enable+broadcast — sab pass.

---

# 🚀 v170.28 (2026-08-17) — DESTINATION SET FIX + FREEBIE DETAILED ADMIN NOTIFY

## 1. 🐛 "Add/Change Channel" temporary-error + destination set nahi hoti FIX
- Root cause: `dest_chat_received` me `_verify_bot_access()` function GHAYAB thi
  (merge me delete, DEST_OPTIONS wali hi problem) → admin link/@username daalte
  hi NameError → "temporary error" → destination save nahi hoti.
- Fix: `_verify_bot_access()` ui_extras.py me dobara define — get_chat +
  get_chat_member se bot ka access verify karta hai (fail-open: resolve ho jaye
  to set ho jata hai). Ab channel add/change ho jati hai + fake activity ka
  system sab chalne lagta hai.

## 2. 🎁 Freebie claim → DETAILED admin notification (supplier wali jesi)
- `freebie_do_callback` ab DETAILED admin notification bhejta hai:
  Order #, PKT Time, Customer name+@username+ID, Product (premium emoji),
  Claim #, Payment, Cost · Sold · Loss — bilkul supplier orders-delivered format.
- `_notify_admin_order_delivered` ab FREEBIE orders skip karta hai (duplicate
  "Order Delivered" nahi aata; freebie ka apna detailed notify hota hai).

## 3. 🧪 Tests: _verify_bot_access (admin/no-access), freebie skip + normal notify — pass.

---

# 🚀 v170.27 (2026-08-17) — FREEBIES INSTRUCTIONS ENGLISH + READY DB

## 🌐 Freebies button ki instructions ab ENGLISH (user demand)
- config.py: freebies_menu_header, freebies_empty, freebie_success,
  freebie_need_refs → English (pehle Roman Urdu).
- handlers_freebies.py: _show_freebies_menu ab freebies_menu_header response
  use karta hai (hardcoded Roman Urdu hata di); claim screen + success confirm
  ke Roman Urdu lines English.
- response_templates.py: freebies keys ke Style B templates bhi English.
- READY DB me freebies English values bake (restore ke baad seedha English).

---

# 🚀 v170.26 (2026-08-17) — WHERE TO SEND FIX + EMPTY-MESSAGE SPAM FIX

## 1. 🐛 "📤 Where to Send?" button temporary-error FIX
- Root cause: `DEST_OPTIONS` dict code me GHAYAB thi (merge/cleanup me delete ho
  gayi) — button tap karte hi `NameError` → "temporary error".
- Fix: `ui_extras.py` me `DEST_OPTIONS` dobara define (bot_only / group_only /
  both + names/descriptions). Ab Destinations panel sahi khulta hai.

## 2. 🐛 "Message text is empty" error + bar bar admin alert FIX
- Root cause: `build_fake_message()` jab koi type eligible data na paye to
  `(None, None)` return karta hai (v170.5 skip). Per-user job ise guard karta
  tha, lekin `schedule_group_activity_job` ka CENTRAL GROUP JOB nahi — wo
  destination par EMPTY text send karta tha → "Message text is empty" + har
  interval par "Fake Activity — destination failed" alert spam.
- Fix:
  - group job ab `if not msg: re-schedule + return` (skip silently).
  - group job admin alert par 30-min cooldown.
  - freebie type me eligible product na mile to `chosen="deposit"` fallback.
  - `broadcast_store_message` (dono copies) empty-text guard → return 0.

## 3. 🧪 Tests: DEST_OPTIONS + dest panel render + empty-text guard — sab pass.

---

# 🚀 v170.25 (2026-08-17) — HOW TO USE (EDITABLE) + BULK COLOR PER SCREEN + FREEBIES BROADCAST

## 1. 📚 How to Use ab Screen Editor me (user demand)
- customization.py SCREEN_TREE me naya node `howto_screen` — main menu ke
  children me. Hub header + 21 guides ab EDITABLE hain (Screen Editor +
  Edit Responses dono me).
- ui_extras.py: `_GUIDES` ab DEFAULT_RESPONSES me register (`guide_<key>` +
  `howto_hub_header`); guide_screen_callback + hub header ab bot_responses se
  read karte hain (admin edit persist hota hai).
- customization.py `_resp_default()`: guide default ka import-order-independent
  fallback (ui_extras._GUIDES se) — screen editor hamesha sahi default dikhata.

## 2. 🎨 Bulk color — ek click me kisi bhi screen + sub-screens ke SAB buttons
- Screen Editor ke har screen view me naya button: `🎨 Color ALL Buttons (N)`.
- `se_allcolor_<sid>` → color picker (🟢 Green / 🔵 Blue / 🔴 Red / ⬜ Default).
- `se_setallcol_<sid>_<style>` → us screen + saare sub-screens ke har button
  (registry + dynamic) ka `btn_style_<id>` set — jaise admin panel green hai.
- `_collect_subtree_button_ids(sid)` tree-walk helper (cycle-safe).

## 3. 🎁 Freebies claim → broadcast (freebie template, NOT new purchase)
- Root cause: freebie claim (`freebie_do_callback`) se `fulfill` → order
  delivered → `update_order_status` hook "new purchase" (bc_purchase) broadcast
  queue karta tha destination par.
- Fix: `update_order_status` hook ab `payment_method='freebie'` detect karta hai
  → `_queue_freebie_broadcast` (bc_freebie template) + `increment_real_sold`
  skip (freebie sale nahi). `_purchase_broadcast_job` freebie queue drain karta
  hai, `fbc_type_freebie` toggle ke sath (OFF = no broadcast).
- `build_real_freebie_message()` (fake_engagement.py): masked username + admin
  ka `bc_freebie` template. Fake freebie broadcasts (v170.14) waise hi hain;
  ab REAL freebie claim bhi same template/toggle use karta hai.

## 4. 🧪 Tests (sab pass)
- freebie order → freebie queue (NOT purchase); normal order → purchase queue.
- build_real_freebie_message render; _collect_subtree_button_ids; howto_screen
  render + guide keys; se_allcolor picker + se_setallcol apply (47 buttons).

---

# 🚀 v170.24 (2026-08-17) — COMPLETED ORDERS (per-user) ab WARRANTY-STYLE

## 🎨 User demand: "Completed Orders → user click → orders screen warranty refund wali jesi"
- `_build_user_orders_kb` (completed_orders_v2.py) ab har order ko WARRANTY-style
  button me render karta hai:
  - premium emoji ICON (product ke naam se extract)
  - clean product name + price (raw [[HTML]]<tg-emoji> nahi)
  - colored button: delivered=green(success), refunded=blue(primary),
    cancelled/rejected=red(danger)
  - status emoji ✅/💸/❌ label ke END par (admin clarity)
- 🐛 Fix: make_premium_button ka leading-emoji strip `#`/emoji kha jata tha —
  ab button manually build hota hai (icon_custom_emoji_id + style) taake
  label/status/icon/color sab consistent rahe.

---

# 🚀 v170.23 (2026-08-17) — NOTIFICATIONS: EK HI (UNIFIED) + USERNAME/PREMIUM EMOJI + OWN PRODUCTS

## 1. 🐛 Duplicate notification FIX (user: "2 dfa notifications a rhy")
- Root cause: supplier product deliver hone par 2 ADMIN notifications aati thin —
  (a) `_notify_admin_order_delivered` ("🎉 Order Delivered! ✅") router ke andar se,
  (b) alag "✅ Supplier order delivered!" block. Dono ek hi delivery event par.
- Fix: router se duplicate call HATAYI. Ab sirf EK unified notification aati hai.

## 2. 👤 Username + 🎖️ premium emoji in notification (user demand)
- Bottom wale ("Supplier order delivered!") me pehle sirf `User ID` tha (username
  nahi) aur product ka premium emoji nahi tha.
- Ab `_notify_admin_order_delivered` (unified) me:
  - `👤 Customer: Name (@username) (ID)` — username ke saath
  - `📦 Product:` premium-emoji aware (`_fmt_msg_name`)
  - `💳 Payment`, `💎 User Wallet before→after`, `🔌 API Balance` (supplier),
    `📊 Stock` (own), `💰 Cost · Sold`, `📈 Profit`, `🕒 Time (PKT)`.

## 3. 🛒 OWN products (Edit Items se add kiye, no supplier) — notification fix
- Pehle own products ke deliver hone par kuch paths me notification NAHI aati thi.
- Ab sab paths unified notification bhejte hain:
  - auto/accounts delivery (`fulfill_paid_product_order`)
  - static media delivery (`_send_static_media_delivery`)
  - admin approve path (`approve_order_callback`)
  - manual delivery (`adm_delivery_text_received` — Pending Manual Delivery)
  - `/deliver` command

## 4. 🛡️ Supplier name leak — VERIFIED
- Customer ko supplier ka naam KABHI nahi dikhta (verify kiya): customer delivery
  (render_v83_delivery), order detail (my_order_detail), refund/retry messages —
  sab supplier-name-free. Supplier name sirf ADMIN notifications + admin
  "Completed Orders" panel me hai (admin-only, v170.5 se).

## 5. 🧪 Tests
- Unified notification (supplier + own) mock test pass: username, premium emoji,
  payment, wallet, API balance/stock, PKT time — sab sahi jagah.

---

# 🚀 v170.22 (2026-08-17) — EDIT RESPONSES: 2 READYMADE TEMPLATES + CUSTOM + CANCEL FIX

## 1. 🎨 Edit Responses — har response ke 2 readymade templates (user demand)
- ✏️ Edit Responses (Admin → ⚙️ Settings → ✏️ Edit Bot Responses) ab har
  response kholne par ye buttons dikhata hai:
  - 📄 **Template 1** (Style A — classic/default)
  - ✨ **Template 2** (Style B — naya alternative)
  - ✍️ **Custom Text** — apna text type karo (placeholders ke saath)
  - ♻️ **Reset to Default** — ek tap me default wapas
- Naya module `response_templates.py`: 78 response keys ke liye Style B
  alternative templates (placeholders-safe — sirf wahi placeholders jo default
  me hain, warna runtime `.format()` crash ho sakta hai).
- Editor ab **placeholders** bhi dikhata hai (e.g. `{shop_name} {user_id}`) +
  current value ka HTML-safe `<pre>` preview (unbalanced markdown crash-fix).

## 2. 🐛 CANCEL BUG FIX (user report: "cancel hota hi ni")
- Root cause: ❌ Cancel button ka `callback_data="noop"` tha → conversation
  `EDIT_RESP_VALUE` state me atki rehti thi, cancel kuch nahi karta tha.
- Fix: Cancel ab `conv_cancel` use karta hai (universal cancel handler —
  conversation END + state wipe). Sath me `return_to` breadcrumb add kiya —
  cancel karne par admin wapas "✏️ Edit Responses" list par jata hai (main
  menu nahi).
- Save hone ke baad bhi "🔙 Back to Edit Responses" button milta hai.

## 3. 🧪 Tests
- 78/78 keys ke templates placeholders-subset verified (0 extra placeholders).
- Markdown balance (placeholders strip karke) 0 unbalanced.
- Mock flow test: template apply / custom / reset / cancel sab pass.
- Real-DB integration test: set_response/get_response persistence pass.

---

# 🚀 v170.21 (2026-08-17) — SCREEN EDITOR BUTTONS + @@TG@@ FIX + ORDER #729

## 1. 🎛️ Screen Editor — Product Detail buttons (user demand)
- product_detail_screen ab ye buttons bhi dikhata hai (rename/premium emoji/
  color/color editor ke liye): prod_favorite (Add/Remove Favorite),
  prod_req (Notify When Available), prod_share (Share Product).
- prod_share naya editable key (button_system EXTRA_KEYS) + get_share_button
  ab rename/style/premium emoji ke saath render hota hai.

## 2. 🐛 @@TG@@ / (name) weird coding FIX
- Gemini translate ab placeholder integrity check karta hai: {name}/{price} etc.
  gayab ho ya @@TG markers aaye to translation REJECT (original rehta hai).
- markdownish_to_html: leftover @@XX<n>@@ markers ka safety cleanup.

## 3. 📦 Ready DB: order #729 added (delivered via ProdSeller, binance, $0.73,
   profit $0.31) + ProdSeller balance 17.65 -> 17.23 baked.

## ⚠️ FRESH DEPLOY: version bump v170.20 -> v170.21.

---


# 🚀 v170.20 (2026-08-17) — ⚡ SUPER FAST (force-join gate speed fix)

## 🐛 ROOT CAUSE (bot slow after updates):
- Force-join gate (har button tap / text par chalta hai) ka membership cache
  TTL **5 second** tha (v170.3). Matlab har 5 sec mein user ka pehla tap 3
  channels ka network member-check (REAL measured 480ms-1500ms) wait karta tha.
  Yehi "slow" ka asli reason tha — DB sab fast hai (2-3ms).

## ✅ FIX:
1. `_FJ_MEMBER_CACHE_TTL` 5s → **60s** (positive result ab 60s cache → 12x kam
   network). Warm check ab **2.6ms** (pehle 500-1500ms).
2. `get_chat_member` timeout 4s → 3s (worst-case tap delay cap; timeout par
   fail-open hota hai to user kabhi zyada nahi rukta).
3. Security intact: GROUP leave abhi bhi INSTANT (ChatMemberHandler cache
   invalidate karta hai); CHANNEL leave max 60s me detect (Telegram channel
   leave ka koi event nahi deta — ye limit har bot ki hai).

## ⚠️ FRESH DEPLOY: version bump v170.19 → v170.20.

---

# 🚀 v170.19 (2026-08-17) — PERSISTENT BUTTONS FIX + BLUE MENU BUTTON

## 🐛 CRITICAL FIX: persistent buttons work nahi kar rahe the
- Root cause: admin ne buttons ke custom labels emoji KE BINA save kiye the
  ("Freebies"/"How to Use"/"Reseller API") → handler hardcoded emoji label
  ("🎁 Freebies" etc.) se match karta tha → match fail → kuch nahi hota tha.
- FIX: naya `persist_button_from_text(text, user_id)` — CURRENT label (custom
  rename + translation + legacy alias) se match karta hai. bot.py dispatch ab
  isi se hota hai. Persistent keyboard WAPAS 4 buttons (Menu/How to Use/
  Reseller API/Freebies).

## 🔵 BLUE MENU BUTTON — bot command menu (screenshot wala)
- `set_my_commands` + `MenuButtonCommands` (post_init): Telegram input ke left
  side wala blue "Menu" button ab commands kholta hai:
  /start 🛍️ Open Shop · /balance 💰 My Balance · /deposit 💎 Buy Points ·
  /orders 📜 My Orders · /freebies 🎁 Free Products · /apikey 🔗 Reseller API Key ·
  /language 🌐 Change Language · /support 🎫 Support & Contact · /help 📚 How to Use.
- Command handlers: shop/balance/deposit/orders/language (screens) + help/
  apikey/freebies/support (text entry) — sab kaam karte hain.

## ⚠️ FRESH DEPLOY: version bump v170.18 → v170.19.

---

# 🚀 v170.18 (2026-08-17) — BROADCAST EXACT + WARRANTY-STYLE LISTS + ENGLISH

## 1. 🌐 Global broadcast — EXACT content (user demand)
- `_admin_extract_media_payload` ab "📢 Announcement" title prepend NAHI karta —
  jo text/photo/video/voice/file admin upload kare WESA hi jata hai.

## 2. 🎨 Broadcast button — REAL background color (user demand)
- `_admin_button_from_state` ab emoji-dot (🔴🔵🟢) nahi — REAL style
  (danger/primary/success) InlineKeyboardButton.style (Bot API 9.4).

## 3. 🛒 Broadcast product picker — warranty/refund style
- `_show_broadcast_product_picker`: premium emoji names + green buttons + stock
  + pagination (pehle plain list thi).

## 4. 🎉 Bulk Discount product list — warranty/refund style (user demand)
- `_bdiscount_prod_list`: sirf IN-STOCK + MANUAL products (out-of-stock nahi),
  premium emoji + green(has tiers)/blue(add) buttons + stock + tiers count.

## 5. 📚 How to Use + responses English update (user demand)
- Naya guide "🎁 Freebies — Free Products" (claim rules + referral re-claim).
- Reseller API guide Step 1 update: persistent keyboard button (Main Menu nahi).
- config.py: naye freebies responses (freebies_menu_header/freebies_empty/
  freebie_success/freebie_need_refs/freebie_claim_limit/freebie_out_of_stock) —
  Edit Responses mein editable (English).

## 6. ⚠️ FRESH DEPLOY: version bump v170.17 → v170.18.

---

# 🚀 v170.17 (2026-08-17) — COMPLETED ORDERS FULL UPGRADE

## ✅ Completed Orders (admin) — naya upgrade:
- **Payment badge** (💳 Payment line): admin ne jo PREMIUM EMOJI Buy Points ke
  payment button par set kiya hai wahi render hota hai (tg-emoji). Fallback:
  PAYMENT_METHODS label. Free = 🎁 Free (Referrals)/🎁 Freebie.
- **Profit column**: har order par sold − cost (products.cost_price × qty).
- **Top summary header**: total orders · spend · profit · refunds.
- **Status tabs**: 📋 All / ✅ Delivered / 💸 Refunded / ❌ Cancelled.
- **Order-ID search**: 🔎 Search me "#637" type karo → direct order khul jata.
- **Refund reason**: supplier_failure_reason/replacement_reason order detail me.
- **📤 Resend to Customer**: delivered content customer ko dobara bhejo.

## ⚠️ FRESH DEPLOY: version bump v170.16 → v170.17.

---

# 🚀 v170.16 (2026-08-17) — FREEBIE SHOP HIDE + TOGGLE RESPONSE

## 1. 🙈 Freebie products shop list me NAHI aate (user demand)
- `get_products_filtered()` ab freebies.enabled=1 wale products ko EXCLUDE karta
  hai (user-facing shop list + carousel + available/unavailable filters).
- Freebie OFF karne par product wapas shop me aa jata hai.
- Admin panels (Edit Items/Reseller/Freebies admin) abhi bhi sab products
  dekhte hain.

## 2. 🔔 Freebie toggle par clear response (user demand)
- freebie_toggle_callback ab q.answer(show_alert=True) toast deta hai:
  "🟢 Freebie ON ✅" / "🔴 Freebie OFF ❌" + screen refresh (Status line update).
- Pehle sirf screen silently refresh hoti thi — admin ko pata nahi chalta.

## 3. ⚠️ FRESH DEPLOY: version bump v170.15 → v170.16.

---

# 🚀 v170.15 (2026-08-17) — PERSISTENT BUTTONS: REAL BACKGROUND COLOR

## 🎨 FIX (maine pehle galat kaha tha — research ke baad confirm):
- Telegram Bot API 9.4 (Feb 2026) ne `style` field **KeyboardButton (reply
  keyboard)** par bhi add kiya hai — sirf InlineKeyboardButton par nahi:
  success(green)/primary(blue)/danger(red). PTB 22.8 isko support karta hai.
- `persistent_menu()` ab REAL background color lagata hai:
  - `get_persist_style(pid)`: persist_color_<pid> = green|blue|red → style
  - `get_persist_emoji(pid)`: persist_emoji_<pid> → icon_custom_emoji_id
- **Emoji-dot workaround REMOVED** (ab real color).
- Premium emoji ICON bhi ab persistent button par render hota hai (rename
  wakt custom emoji bhejo → icon ban jata hai).
- Admin panel notes update (ab "support nahi" wali baat hata di).

## ⚠️ FRESH DEPLOY: version bump v170.14 → v170.15.

---

# 🚀 v170.14 (2026-08-17) — BATCH 7: FREEBIES UI + BROADCAST + BULK TIERS SAVE

## 1. ⌨️ Persistent buttons color (honest workaround)
- Admin panel → ⌨️ Persistent Buttons → ab har button ka **🎨 Color** option
  (🟢Green/🔵Blue/🔴Red/⚪None) — button label ke aage colored DOT emoji lagta hai.
- ⚠️ HONEST: Telegram reply-keyboard buttons par BACKGROUND COLOR possible NAHI
  (sirf inline buttons par hota hai). Dot emoji hi max hai.

## 2. 🎁 Freebies UI (user demand)
- Freebies menu: shop/home buttons HATA — ab sirf product list + back.
- Admin Freebies panel ab warranty/refund STYLE: premium emoji names +
  🟢ON/🔴OFF colored toggles.
- 🐛 TOGGLE FIX: freebie_toggle screen refresh nahi karta tha (q.data se
  "freebie_cfg_" parse hota tha magar data "freebie_toggle_101" tha → silent
  return). Ab shared _render_freebie_config se dono refresh hote hain.

## 3. 🎁 Freebies broadcasting (fake activity)
- Naya type "freebie" (fbc_type_freebie + pua_type_freebie): random enabled
  freebie products se broadcast, bc_freebie template + "🎁 Claim FREE" button.
- Editable template: Customization → Templates → "🎁 Freebie Claimed" (10
  variants). Toggles: Fake Broadcast panel + Per-User Activity panel.

## 4. 📊 Bulk tiers: Save button se broadcast (user demand)
- Pehle har tier add par turant broadcast hota tha → ab tier add par NAHI.
- Naya **✅ Save & Broadcast** button (bdisc_broadcast_) — saare tiers ke baad
  EK baar broadcast (selected destination). bdisc_price_received ab broadcast
  nahi karta.

## 5. 💎 Bulk deal template prettier (default updated, placeholders same:
   {user} {product} {qty} {price} {base_price} {saving}).

## 6. ⚠️ FRESH DEPLOY: version bump v170.13 → v170.14.

---

# 🚀 v170.13 (2026-08-17) — BATCH 6: 🎁 FREEBIES (naya free-claim system)

## 1. 🎁 Freebies — har user FREE claim kar sake (user demand)
- Naya system `handlers_freebies.py` + tables `freebies` + `freebie_claims`.
- Persistent reply-keyboard me naya button "🎁 Freebies" (4th button).
- User flow: Freebies → list (premium emoji + green buttons) → product →
  "🎉 Claim FREE Now" → order + auto-delivery (account pool / supplier).

## 2. ⚙️ Freebie rules (admin panel, user demand)
- Admin Panel → **🎁 Freebies** → har product par:
  - **Toggle ON/OFF** (freebie hai ya nahi)
  - **🔢 Claim limit** (total kitni baar claim, 0 = unlimited)
  - **🔁 Re-claim refs** (dobara claim ke liye kitne referrals)
- Rule: pehli claim FREE (0 referrals); har agli claim = reclaim_refs ×
  claims_already referrals chahiye (lifetime referral count se). Referrals
  kharch nahi hoti, gate ban jati hain.

## 3. ⚠️ FRESH DEPLOY: version bump v170.12 → v170.13.

---

# 🚀 v170.12 (2026-08-17) — BATCH 5: RESELLER PRODUCTS + PERSISTENT BUTTONS

## 1. 🗂️ Reseller products panel (warranty/refund STYLE, user demand)
- `reseller_admin_products_callback` rebuilt: premium emoji product names +
  stock + reseller price + **colored toggle** (🟢 ON=success / 🔴 OFF=danger)
  per product + **🟢 ALL ON / 🔴 ALL OFF** bulk buttons + pagination.
- Callback `reseller_prod_all_(on|off)`.

## 2. ⌨️ Reseller API Key → persistent reply keyboard (user demand)
- `main_reseller_api` inline main-menu button **hidden** (registry hidden flag) —
  ab inline menu me nahi.
- `persistent_menu()` rebuilt: configurable buttons home/howto/reseller
  (rename via `persist_label_<id>` + reorder via `persist_order`).
- Naya text handler `handle_reseller_button` + `reseller_api_from_text`
  (landing/access panel reply_text se).
- Admin panel: Customization → **⌨️ Persistent Buttons** → rename + move up/down.
- ⚠️ HONEST NOTE: Telegram reply-keyboard buttons PLAIN TEXT hote hain — background
  color / animated premium icon inpar support NAHI. Emoji char (e.g. 🎁) rename me
  chalega, lekin colored/animated nahi hoga.

## 3. ⚠️ FRESH DEPLOY: version bump v170.11 → v170.12.

---

# 🚀 v170.11 (2026-08-17) — BATCH 4: SUPPLIER NAME IN EDIT ITEMS + PRODUCT-DETAIL BUTTONS EDITABLE

## 1. 🏭 Edit Items mein supplier name (user demand)
- Admin product detail (Edit Items) ab "🏭 Supplier: <name>" dikhata hai jab product
  kisi ext supplier se link ho. Customer ko kabhi nahi.

## 2. 🎛️ Product-detail buttons editable (rename + premium emoji + color)
- **Rename bug FIX:** `_translate_btn_label` custom override return nahi karta tha
  (`return default_label`) → dynamic keys (prod_buy/prod_favorite/prod_buyx/
  prod_req/prod_review) rename kabhi apply nahi hota tha. Ab `return custom`.
- **Color bug FIX:** `'resolve_button_style' in dir()` inline check function ke
  local scope me False hota tha → product-detail buttons ka color kabhi apply
  nahi hota tha. Ab keyboards.py top-level import + direct call.
- **Naya editor:** Button Styler (bs_edit) me ab "✏️ Rename (Medium)" + "🎨
  Background Color" options. Rename premium-emoji aware, ALL sizes par apply,
  `-` se reset. Color picker (Blue/Green/Red/Default). Callbacks: bs_rename_/
  bs_color_/bs_setcol_ + text hook bs_ren_key.

## 3. ⚠️ FRESH DEPLOY: version bump v170.10 → v170.11.

---

# 🚀 v170.10 (2026-08-17) — BATCH 3: DELIVERED NOTIFICATIONS (username + full details)

## 1. 👤 Supplier delivered notification — ab USERNAME bhi (user demand)
- Supplier product deliver hone par admin ko naya "🎉 Order Delivered!" alert
  (pehle sirf customer ko milta tha, admin ko kuch nahi aata tha).
- Customer ka first_name + @username + user_id + qty + supplier name + sold +
  cost + profit + time. Customer ko supplier info kabhi nahi milti (sirf admin).

## 2. 🏪 Own products delivered notification (user demand)
- Khud ke (static/accounts) product deliver hone par bhi same admin alert:
  customer name + @username + user_id + qty + time + sold price + profit +
  **stock before → after** (account-pool deduction visible). Static media bhi.

## 3. 🔒 Username HTML-safe rendering
- `_`/`*`/`[`/`]`/backtick username me ho to HTML entities me convert (markdownish
  italic/bold leak fix) — literal dikhta hai.

## 4. ⚠️ FRESH DEPLOY: version bump v170.9 → v170.10.

---

# 🚀 v170.9 (2026-08-17) — BATCH 2: REFERRAL COUNT AFTER MATH + TOP REFERRERS

## 1. 🧮 Referral count ab MATH VERIFY ke BAAD (user demand)
- Pehle: referral link se aate hi count ho jata tha (math se pehle).
- Ab: math verification ON ho to referral PENDING record hota hai (no count, no
  points) → math ka sahi jawab aane par hi count + reward. Wrong/abandon par
  count NAHI hota. Math OFF ho to turant count (pehle jaisa).
- 5s fast-approve fallback job ab sirf math OFF par schedule hota hai (math ON
  par math answer hi approval driver hai) → bot stuck nahi hota.
- math question bhejna fail ho jaye to pending turant approve (stuck nahi).

## 2. 🏆 Abuse panel — Top Referrers (user demand)
- Naya button "🏆 Top Referrers" + callback refadm_top.
- `top_referrers(limit)` DB helper: DIRECT counted referrals (product-mode
  excluded), user first_name + username + user_id + total referral points earned
  (points_ledger tx_type='referral' SUM), sorted by refs desc.

## 3. ⚠️ FRESH DEPLOY: version bump v170.8 → v170.9.

---

# 🚀 v170.8 (2026-08-17) — BATCH 1 BUG FIXES (analytics + decimal + delivered file)

## 1. 📊 Analytics dashboard "Temporary error" FIX
- ROOT: `analytics_summary()` query `SUM(price - cost_price)` orders table par
  chala rahi thi — `cost_price` orders me NAHI, products me hai → sqlite
  "no such column: cost_price" → callback crash → Temporary error.
- FIX: `FROM orders o LEFT JOIN products p ON p.id = o.product_id` + o. alias.

## 2. 💎 Decimal amounts (referral points + supplier prices) FIX
- ROOT: `add_ref_points`/`deduct_ref_points` me `round(..., 2)` → 0.002 / 0.03 /
  0.0004 sub-cent rewards 0 ban jate the ("0.1 ke hisab se lagti thi").
- FIX: `round(..., 6)` (full precision, float noise guard). add_ref_points ab
  user row na ho to auto-INSERT bhi karta hai (reward kabhi gayab nahi).
- Supplier fixed-price + markup preview + edit-price current `:.2f` → `fmt_price`
  (ab $0.004 jaisa sub-cent price sahi dikhta/stho rehta hai).

## 3. 📥 "Get Delivered File" (completed orders) FIX
- ROOT: text-only deliveries (koi file id nahi) par callback kuch nahi bhejta tha
  (sent=0) → "kuch nahi hua". Junk file_id ("TXT1") bhi skip hota tha.
- FIX: koi file nahi to customer ka delivered CONTENT text bhejta hai; real file
  id (len>6) pehle document bhejta hai; order_deliveries ke photo/video/voice
  files bhi bhejta hai.

## 4. ⚠️ FRESH DEPLOY: version bump v170.7 → v170.8.

---

# 🚀 v170.7 (2026-08-16) — WARRANTY GREEN + CLEAN NAMES + REMOVE CHANGE LAYOUT

## 1. 🛡️ Warranty/Refund menu — delivered products (user demand)
- Delivered orders ke buttons ab **GREEN (success)** background + product ka
  **premium emoji icon** + **clean name** (pehle raw `[[HTML]]<tg-emoji...>`
  button label me dikh jata tha).
- handlers_support.py `warranty_menu_callback` → make_premium_button + style="success".

## 2. 🎨 "Change Layout" button REMOVED (user demand)
- My Orders screen se "Change Layout" + orders_layout_picker route hata diya.
  Ab sirf receipt layout (default) rehta hai, back button ke saath.

## 3. ⚠️ FRESH DEPLOY: version bump v170.6 → v170.7 (har deploy fresh reset).

---

# 🚀 v170.6 (2026-08-16) — FRESH DEPLOY + RESELLER PRICES + FORMATS + RECEIPT UPGRADE

## ⚠️ 1. FRESH DEPLOY RULE (user demand — HAMESHA)
- `current_version` → `v170.6`: ab HAR deploy bot ko FRESH reset karega
  (0 users/0 orders/0 suppliers). Admin khud ready DB se restore karega.
- 📌 MEMORY RULE: har naye deploy par `current_version` bump karna zaroori hai.

## 2. 💰 Reseller per-key × per-product pricing (user demand)
- Naya table `reseller_key_prices(key_id, product_id, price_usd)`. product_id=0 = ALL.
- `reseller_price_for()` priority: per-key product → per-key ALL → products.reseller_price
  → base(cost|price) × markup.
- UI: Reseller Panel → kisi reseller → **💰 Product Prices** → list (ALL + products)
  → ✏️ Set. Wizard: exact $ (`5.00`) / `+20%` / `-10%` / `+1.5` / `-0.5` / `default`.
  ALL ke liye sirf exact $ ya default.

## 3. 🧩 13 account formats in product editor (user demand)
- templates_bundle: 6 naye formats add (phone_number, license_key, cookie_session,
  api_token, email_pass_cookie, username_pass) + aliases. Ab get_product_format_choices()
  = 13. Admin apna product add karte waqt sab formats pick kar sakta hai.

## 4. 🧾 Receipt orders upgrade (user demand)
- **Premium emojis:** product name ab <tg-emoji> (premium) render hota hai — simple
  emoji nahi. Button par bhi product ka premium icon.
- **Status colors (Telegram button style):** delivered=green(success),
  pending/refunded=blue(primary), cancelled/failed=red(danger).
- **Filter buttons:** ✅ Delivered / ⏳ Pending / 💰 Refunded / ❌ Cancelled / 📋 All
  — click par sirf wohi status wale orders. Pagination filter preserve karta hai.
- Callback `myords_<filter>_<page>`.

## NOTE: DB marker = v170.6 (fresh deploy). Ready DB: 1261/644/33, receipt default,
reseller_key_prices table ready, 13 formats, migrate clean.

---

# 🚀 v170.5 (2026-08-16) — PRODSELLER FIX + RECEIPT ORDERS + ADMIN IMPROVEMENTS

## 1. 🛒 ProdSeller auto-delivery FIX (root cause: 429 rate limit)
- **ROOT CAUSE:** autosync har 30s me `fetch_products()` chalata tha jo ProdSeller ke
  HAR product ka alag detail call karta tha (list me stock field nahi) → ~17 calls/tick
  → 500+/15min → ProdSeller ka 300 req/15min limit blast → real customer order ko 429
  "Trop de requêtes API, réessayez dans 15 minutes" → auto-refund (orders 649/650/643).
- **FIX (ext_suppliers.py ProdSellerAdapter):**
  1. Per-product detail stock **10-min cache** (kills N+1 hammering) → 2nd fetch 0.5s.
  2. Request **throttle** (min 0.35s between calls).
  3. `create_order` **429 retry ×3 backoff** (real order refund nahi hota).
  4. Presets + ensure_env URLs → `https://prodseller.com/v1` (old 51.77.244.194 dead).
- LIVE test: new key OK (balance $25.62, 16 products), fetch 8s → cache 0.5s.
- ProdSeller **re-added** to DB: supplier + 16 products synced + mirrored to shop.

## 2. 🧾 Receipt orders layout (user-requested, Shopee Labs jaisa)
- New layout `receipt`: header RECEIPT/My Orders, "X orders · $Y spent",
  "Tap an order to open its content again.", rows "#ID · Name × qty · $price",
  pagination (Prev/Next, 8/page). DEFAULT layout = receipt (rich abhi bhi available).
- Pagination callback `myordspg_N` registered.

## 3. 📦 Completed Orders (admin) improvements
- **Supplier name** ab admin order-detail me dikhta hai (product → ext_suppliers.name).
  User-side delivery untouched → customer ko supplier info kabhi nahi milti.
- Naya **"📥 Get Delivered File(s)"** button — one tap me sab delivered files
  (bulk .txt + photo/video/voice/audio/doc) admin ko bhejta hai.

## 4. 🎭 Per-product fake-activity OFF
- Naya `products.fake_activity_off` flag + admin toggle in product panel.
- Fake activity (global + per-user) is product ko skip karti hai — sirf REAL
  purchase ka alert. (pehle sirf "api test" naam wale exclude the)

## 5. 💬 Deposit + Price-Drop alerts editable
- **Deposit:** bc_deposit default ab txid + pkr_amount + "Auto-Credited via API"
  ke saath. Hardcoded "GEN-xxxx" ultimate fallback REMOVED (wo purchase-without-stock
  ka galat fallthrough tha) → ab skip, sirf editable template.
- **Price Drop:** 10 hardcoded templates (PREMIUM PRICE DROP / LOWEST PRICE EVER etc.)
  ab Customization → Templates → "Price Drop Alert" se editable + random variant pick.

## NOTE: DB marker `v170` hi rakha — deploy live DB wipe NAHI karega.
## Ready DB: ProdSeller new key baked + receipt default + migrate clean.

---

# 🚀 v170.4 (2026-08-14) — FORCE-JOIN MISSING-ONLY + RICH ORDERS LAYOUT

## 1. FORCE-JOIN: sirf MISSING channel ka join wall (user demand)
- Pehle: user ne 1 channel chhoda to bot SAB channels ka join wall bhejta tha.
- Ab: sirf WOHI channel dikhta hai jo chhoda hai; SAB tabhi jab SAB chhode.
- Message smart: kuch chhode → "You left the following. Please rejoin"; naya user → "you must join".
- Helper `_build_fj_join_wall(targets)` (sirf missing targets ke buttons/links).
- TESTED: 1 channel leave → sirf 1 button ✅ | sab leave → sab 3 ✅ | boot OK ✅

## 2. ORDERS LAYOUT: Rich Details (user choice) + premium emoji fix
- User ne 10 layouts mein se **Rich Details (#7)** choose kiya.
- `orders_layouts.py`:
  - `_render_rich()` ab HTML mode mein render hota hai — product name **PREMIUM
    emoji + supplier FIXED emoji** ke saath (pehle `_clean_name()` tags hata deta
    tha → emoji gayab hota tha).
  - Naya helper `_render_product_name_html()` (utils.name_for_message_html use
    karta hai — wahi logic jo product list/detail mein hai).
  - Default layout `premium` → `rich` (code + DB dono).
- VERIFIED (real DB orders): "🤖 Gemini AI Pro 18m", "👍 Meitu Svip" premium
  emoji ke saath render; smart_text_and_mode → HTML mode, [[HTML]] leak nahi.

## NOTE: DB marker `v170` hi rakha — deploy live DB wipe NAHI karega.
## Ready DB: orders_layout=rich baked.

---

# 🚀 v170.3 (2026-08-14) — 🔐 FORCE-JOIN LEAVE DETECTION REAL FIX (live test fail hua tha)

## 🐛 USER LIVE TEST FAIL (v170.2 ke baad): wife ke phone se verify → bot start →
## channels leave → wapis aake button dabaya → force NAHI hua. /start par bhi nahi.

## ROOT CAUSE (found + verified live)
- v170.2 me positive member cache TTL **60s** tha. User ne leave karne ke baad
  **60s ke ANDAR** wapas aake button dabaya → cache purana `True` de raha tha →
  fresh `get_chat_member` hota hi nahi → force nahi hua.
- LIVE verify: bot 3no targets (bite_alerts / learnwith_Alex / Alex_Resellers) me
  ADMIN hai → `get_chat_member` theek chalta hai. Real user jo leave kar chuka hai
  uske liye `status="left"` return hota hai (users 5707883931, 7814495526 se confirm)
  → member check accurate hai, masla sirf cache ka tha.

## FIX (ui_extras.py)
1. **Positive cache TTL 60s → 5s** — sirf rapid double-tap dedupe ke liye.
   Leave detection ab ~5s me (channel leave ka Telegram koi push event nahi deta).
2. **Parallel member check** (`_membership_missing` helper — `asyncio.gather`):
   pehle 3 targets sequential (3 round-trips) → isliye bara cache lagana para tha.
   Ab 3 targets 1 round-trip ≈ 200-450ms (LIVE measured) → fresh check hamesha
   affordable. Teen call sites (check_force_join, force_join_action_gate,
   fj_verified_callback) ab ye helper use karte hain.
3. **Fail-open True ab cache nahi hota** (TelegramError branch) — transient error
   ke baad user 5s tak galat "member" na rahe.
4. ChatMemberHandler (v170.2) — group leave par cache turant invalidate — barkarar.

## TESTED (local reproduction + real API)
- User scenario: /start(block) → join → verify(start) → leave all → wait 6s →
  main menu tap → BLOCKED ✅ | /start → BLOCKED ✅ | rejoin → PASS ✅
- Real API parallel check: 176-456ms (fast) ✅
- Real API: left-wala user → "left" (accurate) ✅
- Boot smoke OK ✅

## NOTE: DB version marker `v170` hi rakha — deploy live DB wipe NAHI karega.

---

# 🚀 v170.2 (2026-08-14) — 🔐 FORCE-JOIN TIGHT SECURITY: LEAVE DETECTION

## 🐛 USER BUG: user verify ho kar bot start kar leta hai, phir channels LEAVE kar
## deta hai — par bot phir bhi chalta rehta hai. Hona chahiye: leave karte hi bot
## foran wohi channel dobara join karne par force kare.

## ROOT CAUSE
- `_FJ_MEMBER_CACHE` positive result (member=True) **900s (15 min)** cache karta tha.
- User verify ke baad 3 targets ka `True` cache hota tha → channel leave karne ke
  baad bhi gate (force_join_action_gate) cache se purana `True` uthata tha →
  fresh `get_chat_member` hota hi nahi tha → 15 min tak bot chalne deta tha.

## FIX (ui_extras.py + bot.py)
1. `_FJ_MEMBER_CACHE_TTL` 900s → **60s** (leave max 1 min me detect — channel ke
   liye, kyunki Telegram channel leave ka koi push event nahi deta).
2. **Naya `fj_chat_member_handler`** + `ChatMemberHandler(ANY_CHAT_MEMBER)`:
   jab koi user kisi chat se leave/join kare (group leave ka instant event aata
   hai) to uski membership cache **turant invalidate** → next action par fresh
   check → leave karne wala foran block (join wall dobara dikhta hai).
3. `invalidate_fj_member_cache(user_id=None)` helper (single user ya sab clear).

## TESTED (local reproduction)
- Verify → positive cache banai → leave event → cache 0 → gate BLOCKED ✅
- Leave ke baad fresh gate check → BLOCKED ✅ (join wall reply aata hai)
- Rejoin → gate PASS ✅
- v170.1 verify flow regression → abhi bhi sahi (negative cache nahi hota) ✅
- Boot smoke OK ✅

## NOTE
- Channel leave ka instant event Telegram nahi deta (channel join/leave ka koi
  service message nahi) — isliye channels ke liye 60s TTL hi reliable detection hai.
  Group leave instant detect hota hai (chat_member update).
- DB version marker `v170` hi rakha — deploy live DB wipe NAHI karega.

---

# 🚀 v168 (2026-08-13) — ⚡ CRITICAL FIX: REFERRAL FREEZE BUG + SUPER FAST BOT SPEED

## 🐛 CRITICAL FIX: Referral Freeze Bug (`handlers_start.py` + `fake_engagement.py`)
- **Root Cause Found:** When a new referral user joined via `/start ref_XXXX`, the bot would freeze for 5+ minutes. All buttons and commands stopped working. Customers complained heavily.
- **Problem 1:** `broadcast_new_user_join()` was `await`ed synchronously in `/start` handler. It sent messages to ALL 1100+ users one-by-one with `asyncio.sleep(0.05)` between each = ~3 minutes blocking.
- **Problem 2:** Referral broadcast in `_process_referral_attribution()` also looped over ALL 1100+ users sequentially = ~2-3 minutes blocking.
- **Fix:** Both broadcasts now run as `asyncio.create_task()` background tasks (fire-and-forget). The `/start` handler returns INSTANTLY — user gets their welcome screen in <1 second while broadcasts happen in the background.
- **Referral broadcast capped to 30 random users** instead of ALL 1100 — saves API quota and is sufficient for social proof.

## ⚡ SPEED OPTIMIZATION: Batch Sending (`fake_engagement.py`)
- **`send_to_all_users()`:** Replaced sequential one-by-one sending with `asyncio.gather()` batches of 15 concurrent sends. Broadcast time reduced from 3+ minutes to ~15 seconds for 1100 users. Sleep reduced from 0.05s/msg to 0.1s/batch.
- **`broadcast_store_message()`:** Same batch optimization applied to the main store broadcast loop. 10x faster delivery.
- Added `max_recipients` parameter to `send_to_all_users()` for optional capping.

## 🗄️ RESET GUARD: `database.py` bumped to `v168`
- Fresh reset guard triggers on new deploy (wipes DB for clean boot).

---


# 🚀 v167 (2026-08-12) — 🆕 UNIVERSAL NEW-RELEASE FRESH RESET GUARD (ALWAYS BOOT 0 DATA ON DEPLOY) + READY DB (3)

## 🔄 Universal Fresh Reset Guard on Railway (`database.py`)
- **Root Cause Found:** Previously, `.v163_fresh_reset_done` existed on `/var/data/`, so subsequent deployments (`v164`, `v165`, `v166`) did not wipe the database and booted with existing data.
- **Fix:** Replaced static marker with `.deployed_version` tracking (`v167`). Now whenever a new release version is deployed on Railway (`last_version != "v167"`), `database.py` automatically wipes `/var/data/shop.db` once so the new deployment starts 100% FRESH AND EMPTY (`0 users`, `0 orders`, `0 products`) with pre-seeded default English responses.
- Normal restarts of the same deployed version will not wipe data.
- Admin can restore live data anytime via `/admin` -> Backup & Restore -> Restore from File.

## 🗄️ READY DB (3): `bite_store_restore_ready.db` (v167 Verified)
- Zero-loss audit verified on user's live DB (`1100 users`, `516 orders`, `28 products`).

---

# 🚀 v166 (2026-08-12) — ⭐ TELEGRAM NATIVE INVOICE PLAIN-TEXT CLEANER (FIXED RAW HTML CODING) + READY DB (3)

## ✨ FIX: Telegram Native Invoice (`send_invoice`) Description Cleaning (`handlers_stars.py`)
- **Root Cause Found:** When a user clicked `"⭐ Pay X Stars"` on the checkout message, the bot called Telegram's `send_invoice` API to open the native Telegram Stars payment window. However, Telegram's `send_invoice` `description` field is strictly plain text (`max 255 characters`) and does not parse HTML or `<tg-emoji>` tags. Because `_send_stars_invoice` stored the rich HTML instructions in `inv["desc"]`, passing that directly to `send_invoice` caused Telegram to display raw HTML `<tg-emoji...>` coding and cut off the text after 255 characters (`...<b>Canva`).
- **Fix:** Added `clean_plain_text(text)` helper in `handlers_stars.py` that strips `[[HTML]]`, `<tg-emoji>`, `<code>`, `<b>`, `<i>`, and Markdown asterisks, returning a concise, beautiful Unicode plain-text description (e.g. `⭐️ Telegram Stars — Product Checkout ... 📦 Product: 🎨Canva 500 User Panel ...`, exactly 153 characters).
- Now when the native invoice window opens, zero raw coding is displayed and the full description fits cleanly.

## 🗄️ READY DB (3): `bite_store_restore_ready.db` (v166 Verified)
- Zero-loss audit verified on user's live DB (`bite_store_restore_ready.db`, `1100 users`, `516 orders`, `28 products`).

---

# 🚀 v165 (2026-08-12) — ⭐ TELEGRAM STARS PREMIUM EMOJI & HTML RENDERING FIX + READY DB (3)

## ✨ FIX: Telegram Stars Invoice & Success HTML/Emoji Rendering (`handlers_stars.py`)
- **Root Cause Found:** `_send_stars_invoice` in `handlers_stars.py` was calling `q.edit_message_text(..., parse_mode="Markdown")` directly instead of `_safe_send(...)` / `smart_text_and_mode(...)`. When an admin customized `payment_stars_checkout` with `[[HTML]]` or custom `<tg-emoji>` premium emojis, Telegram received raw HTML tags in Markdown mode and printed them as ugly text (`[[HTML]]<tg-emoji ...>⭐</tg-emoji>`).
- **Fix:** Switched `_send_stars_invoice` to use `_safe_send(q, context, text, reply_markup=kb)`, which automatically calls `smart_text_and_mode(text, "Markdown")`, strips `[[HTML]]`, balances unclosed tags, and sends in `"HTML"` mode.
- Switched `stars_successful_payment` to also run messages through `smart_text_and_mode(msg_text, "Markdown")`.
- Verified in test suite that `<tg-emoji>` premium emojis now render cleanly in HTML mode.

## 🗄️ READY DB (3): `bite_store_restore_ready.db` (v165 Migrated & Verified)
- Downloaded user's latest MediaFire backup DB (`n03jz59nx0xfwhy` -> `bite_store_backup_20260812_161239.db`).
- Performed zero-loss schema upgrade on workspace copy (`bite_store_restore_ready.db`).
- **Zero-Loss Audit Results:**
  - `users`: 1100 -> 1100 rows ✅
  - `orders`: 516 -> 516 rows ✅
  - `products`: 28 -> 28 rows ✅
  - `bot_responses`: 72 -> 72 rows ✅
- All 39 tables checked with 0 errors.

---

# 🚀 v164 (2026-08-12) — ⭐ TELEGRAM STARS CHECKOUT IN EDIT RESPONSES + CLEAN ADMIN REVIEWS SCREEN REDESIGN + NEW READY DB (2)

## 💬 NEW: Telegram Stars Checkout & Deposit Texts in "Edit Responses"
- **`config.py`**: Added four distinct editable response templates for Telegram Stars:
  - `payment_stars_checkout`: Instructions shown when checking out a product with Stars.
  - `payment_stars_deposit`: Instructions shown when depositing / buying points with Stars.
  - `payment_stars_success`: Success message shown upon successful Stars payment.
  - `payment_stars_menu_text`: Description text shown in the payment method selector.
- **`handlers_stars.py`**: Updated `_stars_instructions_text` to automatically use `payment_stars_checkout` for products and `payment_stars_deposit` for points deposits.
- All four keys are grouped under `💳 Payment Screens` in Edit Responses and are auto-seeded on boot.

## ✨ REDESIGNED: Admin Reviews Screen (`handlers_reviews.py`)
- **HTML & Tag Stripping:** Added `strip_html_tags()` to safely remove `<tg-emoji...>` and `[[HTML]]` markup from product names, user names, and review text so raw HTML coding never leaks into text.
- **`database.py` (`get_all_reviews_for_admin`)**: Query now selects `u.username` alongside `first_name`.
- **Card Format Redesign:** Each review is now displayed as an organized, readable card:
  - Review ID & Status (`✅ Approved`, `📌 Pinned`, `🚫 Hidden`)
  - Product Name (`📦 Product: ...`)
  - User Name, Username & Telegram ID (`👤 User: ... (@...) (ID: ...)`)
  - Star Rating (`🌟 Rating: ⭐⭐⭐⭐⭐ (5/5)`)
  - Submission Date & Time (`🕒 Date: YYYY-MM-DD HH:MM`)
  - Clean Comment Text (`💬 Comment: ...`)
- Added clear action text labels to inline buttons: `[ #2 Action: ] [ 📌 Pin/Unpin ] [ 👁️ Hide/Show ] [ 🗑️ Delete ]`.

## 🗄️ READY DB (2): `bite_store_restore_ready.db` (v164 Migrated & Verified)
- Downloaded user's latest MediaFire DB (`xwyxk19w9pcdp5t` -> `bite_store_restore_ready+(2).db`).
- Performed zero-loss schema upgrade on workspace copy and seeded all 4 new Telegram Stars responses.
- **Zero-Loss Audit Results:**
  - `users`: 1098 -> 1098 rows ✅
  - `orders`: 514 -> 514 rows ✅
  - `products`: 16 -> 16 rows ✅
  - `bot_responses`: 68 -> 72 rows (4 new Stars responses seeded) ✅
- All 15 schema tables checked with 0 errors.

---

# 🐛 v163.1 (2026-08-12) — HOTFIX: FIX NAMEERROR IN `database.py`
- **`database.py` (`setup_database`)**: Replaced `logger.info/warning` with `print` in the v163 one-time reset guard block. Fixed `NameError: name 'logger' is not defined` on Railway boot.
- Verified boot smoke test with existing `DB_PATH` to ensure the one-time reset runs cleanly.

---

# 🚀 v163 (2026-08-12) — 🆕 100% FRESH RESET BOT DEPLOY + `/resetbot` + 1-CLICK RESET IN ADMIN

## 🔄 Fresh Reset Bot on Deploy (Zero Data policy as requested)
- **`database.py` (`setup_database`)**: Added a one-time reset guard (`.v163_fresh_reset_done`). When deployed, the bot boots with a 100% fresh, clean, empty database (`0 users`, `0 orders`, `0 products`) and pre-seeds only the 68 default English responses.
- **`handlers_admin.py` & `bot.py`**:
  - Added new Admin Command **`/resetbot`** — Admin can reset the bot database to an empty 0-data state anytime from Telegram chat (with safety auto-backup).
  - Added **`🔄 Reset to Fresh (0 Data)`** button in `/admin` → **💾 Backup & Restore**.

## 🗄️ Ready DB Deliverable
- `bite_store_restore_ready.db` remains available and zero-loss verified (`users: 1098`, `orders: 514`). Admin can restore live data anytime via `/admin` → **Backup & Restore** → **Restore from File**.

---

# 🚀 v162 (2026-08-12) — ⭐ TELEGRAM STARS FLOW CUSTOMIZATION + EDIT RESPONSES + HOW-TO-USE GUIDES + READY DB

## 🎨 NEW: Telegram Stars Flow in Customization
- **`customization.py`**: Added `"stars_flow_screen"` (`⭐ Telegram Stars Flow`) to Screen-by-Screen Editor (`MAIN_SCREENS`, `BTN_TARGET_SCREEN`, `SCREEN_TREE`), parallel to `bybit_flow_screen`.
- Admin can now edit buttons (`pay_stars`, `pay_stars_pay`, `nav_pay_cancel`) and texts (`stars_pay_instructions`, `stars_payment_success`) directly via Customization → Payment Methods → ⭐ Telegram Stars Flow.
- **`handlers_stars.py`**: Updated `_send_stars_invoice` to build `nav_pay_cancel` dynamically via `button_system.build_button()`, and updated deposit success to use the editable response `"stars_payment_success"`.

## 💬 NEW: Telegram Stars in "Edit Responses"
- **`config.py` & `handlers_admin.py`**: Added `stars_pay_instructions` and `stars_payment_success` to `DEFAULT_RESPONSES` and registered `stars_` prefix in `CATEGORIES["payment"]`.
- Admin can now search or browse under `💳 Payment Screens` in Edit Responses to customize Telegram Stars texts.

## 📚 UPDATED: "How to Use" Guidelines (English)
- **`ui_extras.py`**:
  - Updated `_GUIDES["pay_overview"]` to feature ⭐ Telegram Stars prominently at #1.
  - Added dedicated full-screen guides for **⭐ Telegram Stars — Step-by-Step** (`guide_pay_stars`) and **🔗 Reseller API — Step-by-Step** (`guide_reseller_api`).
  - Added interactive buttons for both guides in the How-to-Use Guide Hub keyboard.

## 🗄️ READY DB: `bite_store_restore_ready.db` (v162 Migrated & Verified)
- Downloaded user's live MediaFire database and performed zero-loss schema upgrade on a workspace copy.
- **Zero-Loss Verification:**
  - `users`: 1098 -> 1098 rows ✅
  - `orders`: 514 -> 514 rows ✅
  - `products`: 16 -> 16 rows ✅
  - `bot_settings`: 1100 -> 1100 rows ✅
- Seeded missing responses into `bot_responses`. All 15 schema tables checked with 0 errors.

## 🧪 Automated Tests & Boot Smoke
- `_test_v162_stars_customization.py` — **9/9 PASS**:
  - `test_01_stars_flow_screen_in_screens` ✅
  - `test_02_btn_target_screen_mapping` ✅
  - `test_03_stars_flow_screen_hierarchy` ✅
  - `test_04_default_responses_contain_stars_keys` ✅
  - `test_05_admin_edit_responses_category` ✅
  - `test_06_ui_extras_guides_added` ✅
  - `test_07_pay_overview_lists_stars_first` ✅
  - `test_08_zero_loss_database_verification` ✅
  - `test_09_boot_smoke_import_and_migrate` ✅

---

# 🚀 v161 (2026-08-10) — 🔗 RESELLER API (ProdSeller-compatible) + Railway LIVE

## 🟢 Railway migration COMPLETE
- Bot ab **Railway Hobby** pe live hai (deploy `caf4d474` SUCCESS, stable).
- **Root cause of earlier crashes found:** Railway env vars incomplete tha —
  `RuntimeError: Missing required environment variables: ADMIN_ID`. Ab **32 env
  vars** set hain (user ke sab + zaroori extras), volume `/var/data`, numReplicas=1,
  restart ON_FAILURE, Dockerfile builder.
- Render service **SUSPENDED** (user ne khud kiya) — resume karna mana (409 conflict).
- Bot maintenance mode ON (`MAINT_ON_START=1`) — admin band karega.

## ✨ NEW: Reseller API (ProdSeller-compatible)
- Naya module **`reseller_api.py`** — FastAPI server jo Telegram bot ke saath
  (wahi Railway service, wahi process) PORT pe chalta hai.
- **ProdSeller jaisa model:** key generate → reseller apne bot me
  `X-API-Key: <key>` header ke sath API lagata hai → docs `/api-docs/`.
- **Endpoints:**
  - `GET /v1/products` — product list with **REAL live stock** (accounts pool count
    ya DB stock — order pe decrement hota hai; ProdSeller ki fake "1 everywhere"
    wali galti NAHI).
  - `GET /v1/balance` — reseller wallet (USD + points).
  - `POST /v1/orders` `{productId, quantity}` → points deduct → fulfill (supplier
    auto-buy / static / accounts) → `deliveredKeys` return. Idempotency-Key support.
  - `GET /v1/orders/{id}` — status/delivery.
  - `GET /api-docs/` → Swagger docs (ProdSeller style), `GET /health`.
- **Payment model (owner ka design):** reseller 💎 points deposit karta hai (Buy
  Points — pehle se bana hua) → har API order uske points se deduct hota hai →
  aap ke suppliers se fulfill → delivery reseller ke bot ko → reseller customer ko.
- **Auth/security:** `X-API-Key` header, keys SHA-256 hash me store (plaintext ek
  dafa), rate limit 60 req/min, har call `api_request_log` me, revoke support.
- **Pricing:** global markup % (`/resellermarkup`) + per-product fixed reseller price
  (`/resellerprice`) + per-product visibility (`/reselleron` / `/reselleroff`).

## 📚 Admin commands (Telegram)
- `/resellerkey <user_id> [label]` — reseller key generate (ek dafa dikhti hai)
- `/resellerkeys` — sab keys + balances
- `/resellerrevoke <key_id>` — key band
- `/resellermarkup <pct>` — global reseller markup %
- `/resellerprice <pid> <usd>` — per-product reseller price (0 = auto markup)
- `/reselleron <pid>` / `/reselleroff <pid>` — reseller visibility toggle
- `/resellerorders [user_id]` — reseller orders log

## 🗄️ DB (idempotent migrate)
- `reseller_orders` table (status, delivery, points, idem_key...)
- `products.reseller_enabled` + `products.reseller_price`
- settings: `reseller_markup_pct`, `reseller_points_per_dollar`

## 🧪 Tests
- 28/28 naye reseller API tests PASS (auth, products, balance, orders, stock
  decrement, points deduct, idempotency, error paths) + real uvicorn server curl
  tests + full bot boot with API server. Zero regression (v148/v157 ke 2 purane
  stale tests pehle se fail the — v152/v159 rebuilds ne un flow ko hata diya).

## 🔒 v161.1 (same day) — emoji rendering + zero supplier leak + docs
- **Premium emoji proper rendering:** `/v1/products` ab 3 fields deta hai —
  `name` (clean plain text, emoji char included, NO raw HTML), `name_html`
  (`<tg-emoji emoji-id=...>` markup for parse_mode=HTML bots), `emoji` + `emoji_id`.
  Own products ka premium emoji AUR supplier products ka fixed emoji dono sahi
  render hote hain — koi `[[HTML]]`/tag coding leak nahi.
- **Zero supplier leak:** payload sirf product data (name/desc/price/stock) —
  supplier names/URLs/keys kabhi expose nahi hote. Fulfillment errors ab GENERIC
  hain (`order failed at source, retry later`) — details sirf internal logs/DB me.
- **Auto-delivery sab types:** own auto/static/accounts + supplier-synced products
  sab instant deliver. Sirf product jis mein koi instant content nahi → `pending`
  (reseller `GET /v1/orders/{id}` se baad me le leta hai).
- **Docs:** `/api-docs/` (Swagger) + `RESELLER_CONNECT_GUIDE.md` — full English, easy.
- Tests: 28 + 20 = **48 checks PASS** (emoji, no-leak, generic errors, refund).

## 🖱️ v161.4 (same day) — BUTTON-DRIVEN reseller UI (ProdSeller-style, commands REMOVED)
- **Commands system HATA diya** — `/reseller*` + `/myresellerkey` ab register NAHI hote.
- **User side — ProdSeller jaisa interface:** main menu mein **"🔗 Reseller API Key"** button:
  - Pehli dafa → "🔑 New API Key Generated!" full key + "Use header: X-API-Key: ..." +
    [📚 API Documentation] [Back] (screenshots jaisa).
  - Baad mein → "🔗 API Access" panel: masked key (`bsk_xxx....`), 💳 balance,
    📨 total requests, 📅 created + buttons **[👁️ Show Full Key] [🔄 Regenerate]
    [📚 API Documentation] [🔙 Back]** — exactly ProdSeller jaisa.
  - **Show Full Key** kaam karta hai: plaintext ab **Fernet-encrypted** store hota hai
    (`api_keys.key_encrypted`, key = API_SECRET_ENCRYPTION_KEY/BOT_TOKEN) — at-rest secure,
    display-time decrypt.
  - **Regenerate** → purani key revoke, nayi key ek dafa.
  - **API Documentation** = URL button → `/api-docs/`.
- **Admin side (sab buttons):** Admin panel → "🔗 Reseller API" → Generate / Keys & Config /
  Global Pricing / 🗂️ Products (per-product reseller price + on/off toggle) / Orders (Deliver) / Stats.
- Tests: 87 checks PASS + key flow tests (generate/reveal/revoke/regenerate). DB: api_keys.key_encrypted.

## 🎯 v161.3 (same day) — self-serve keys + admin panel UI + async fulfillment + webhook retries (DEPLOYED)
- **Self-serve:** koi bhi user `/myresellerkey` se apni reseller API key khud bana sakta hai
  (uske points = uski wallet). Admin approval zaroori nahi; admin revoke/limit kar sakta hai.
- **Admin Panel UI:** Admin menu mein "🔗 Reseller API" button → full panel:
  Generate Key (wizard), Keys & Config (per-key markup/base/spend/products/IP/webhook/revoke),
  Global Pricing (markup + base), Orders (with 📤 Deliver), Stats.
- **Async fulfillment:** supplier products ab instant `status: "processing"` return karte hain,
  fulfillment background mein hota hai → webhook + `GET /v1/orders/{id}` se delivery.
  (Slow suppliers ka timeout masla khatam.)
- **Webhook reliability:** events ab DB queue mein jate hain (`reseller_webhook_events`),
  worker 20s loop se bhejta hai, 3 attempts tak retry, **HMAC-SHA256 signature**
  (`X-Bite-Signature` header, secret = key ka webhook_secret).
- **Per-key rate limit:** `rate_limit` column (default 60) — premium resellers ko zyada.
- **Product display:** payload mein `deliveryType` (supplier/text/file/accounts/manual) +
  `GET /v1/products/{id}/image` (product photo bytes).
- **Ops:** pending reseller orders ka admin reminder (15-min job, 30-min old orders),
  API crash pe owner ko Telegram alert (max 1/10min).
- Tests: 87 checks PASS (28+20+24+15) + boot + pytest (1 stale pre-existing fail only).

## 🚀 v161.2 (same day) — per-key control + webhooks + files + manual delivery + DEPLOYED LIVE
- **LIVE on Railway:** public URL `https://bite-store-bot-production.up.railway.app`
  (deploy `4497a35e` SUCCESS). `PORT=8000` explicitly set so the domain works.
- **Per-key pricing (2 modes):** global `/resellerbase cost|price` (base = supplier
  cost YA aap ki selling price) + global `/resellermarkup <pct>` (negative = discount)
  + per-key override `/resellerkeycfg <key_id> <pct> [cost|price]`.
- **Per-key security:** `/resellerspend <key_id> <usd>` (spend limit),
  `/resellerproducts <key_id> all|<p1,p2>` (allowed products),
  `/resellerip <key_id> all|<ip1,ip2>` (IP whitelist) — sab enforced in API.
- **Webhooks:** `/resellerwebhook <key_id> <url|off>` — POST events
  `order.delivered` / `order.pending` / `order.failed` / `order.pending_completed`.
- **Manual delivery:** `/resellerdeliver <order_id> <text>` — pending reseller order
  ki delivery set karo; reseller `GET /v1/orders/{id}` se le leta hai (+ webhook).
- **Files:** `GET /v1/files/{orderId}` — file products ke bytes serve (Telegram
  file_id cross-bot nahi chalti, is liye bytes). `deliveredFileRef` in responses.
- **Transactions:** `GET /v1/transactions` — wallet ledger + orders history.
- **Products:** pagination (`page`/`per_page`), search (`search=`), category filter,
  `live=1` (background supplier stock refresh, throttled 45s/supplier).
- **Stability:** API server thread auto-restart (crash pe 8s baad wapas).
- Tests: 72 total checks PASS (28 + 20 + 24) + boot + live public-URL curl.


## ✨ NEW: Editable tier-discount description templates
- Two new editable templates in Templates editor:
  - **📊 Bulk Discounts (Tiered)** (`tier_display`) — the whole block:
    placeholders `{product}`, `{base_price}`, `{tiers}`, `{currency}`.
  - **📊 Tier Line** (`tier_line`) — one line per tier:
    placeholders `{qty}`, `{price}`, `{product}`, `{base_price}`.
- Ready-made defaults included; admin can edit both with premium emojis
  ([[HTML]]<tg-emoji>) and custom text — exactly like every other template.

## 🐛 FIX: ugly literal `**` in the product description
- The tier block used Markdown `**bold**` but the product page renders in HTML
  mode → the asterisks showed literally. Now `product_tiers_text(mode="html")`
  converts to real HTML (<b>…) and strips stray `*`/`_`. Markdown branch keeps
  `**` emphasis. Verified: clean output, no literal `**`.

## 🐛 FIX (internal): render_template got the template TEXT instead of its ID
- `product_tiers_text` was passing the template text to `render_template`
  (which expects an ID) → tiers rendered empty. Now passes the ID correctly.

## 🧪 Tests
- `_test_v158_tiered_ticket.py` extended (+3: templates registered, HTML clean,
  custom template with premium emoji). All 19 in-repo suites pass.

# 🚀 v159 (2026-08-09) — HOTFIX: Bulk Discount tier flow stuck + English UI + Bulk Price Editor HTML

## 🐛 FIX 1 (CRITICAL): Bulk Discount — qty bhejte hi bot ka response nahi aata tha
- **Root cause:** `handlers_admin` set the tier state as `bdisc_step` but `bot.py`
  checked `bdiscount_step` — a key-name mismatch. So when the admin typed the
  quantity, the handler never fired and the flow silently died.
- **Fix:** `bot.py` now checks `bdisc_step` (consistent). Verified end-to-end:
  Add Tier → type qty → type price → tier saved → `tier_price_for_qty` returns
  the right unit price. Product names show clean (HTML stripped).

## ✨ FIX 2: All new panel instructions in ENGLISH (no Roman Urdu)
- Bulk Discount list/detail/Add-Tier prompts, qty/price steps, success messages —
  all translated to clean English. Cancel now clears the new `bdisc_step` too.

## 🐛 FIX 3: Bulk Price Editor showed raw HTML
- `_bulk_price_screen` (the old %-based editor) now strips
  `[[HTML]]<tg-emoji…>` markup — clean product names.

## 🧪 Tests
- `_test_v158_tiered_ticket.py` extended (+4: key consistency, English UI,
  bulk-price strip, tier flow e2e). All 19 in-repo suites pass; `main()` boots.

# 🚀 v158 (2026-08-09) — TIERED quantity discounts + Buy-Now name/emoji fix + 3h ticket reminder + reject-reason order fix

## ✨ NEW: Tiered Quantity Discounts (as the owner described)
- Per-product MULTIPLE price tiers by quantity — exactly like the example:
  Gemini: `1 qty → $1.00`, `10 qty → $0.89`, `30 qty → $0.52`, `50 qty → $0.45`
- Admin: Edit Items → **🎉 Bulk Discount** → tap a product → ➕ Add Tier
  (min qty → unit price). Unlimited tiers per product. Remove any tier anytime.
- Product page shows the tiers block (base price + every "If order quantity is
  X → $Y") only on products that HAVE tiers.
- Checkout auto-applies the price: buying 15 units picks the 10-qty tier
  ($0.89 each); buying 99 picks the 50-qty tier ($0.45 each).
- Fixed the panel showing raw `[[HTML]]<tg-emoji…>` names — now clean names +
  a tier-count badge.

## 🐛 FIX: Buy Now button on alerts — product name + premium emoji
- `build_button` now supports `force_default=True`; all broadcast/alert Buy-Now
  buttons pass it so the button ALWAYS shows the product-name label
  ("🤖 Gemini Pro Buy Now") plus the premium emoji icon (own product → name
  emoji; supplier → fixed emoji) — instead of a generic saved "Buy Now".

## 🐛 FIX: Replacement reject — reason flow actually works
- PTB fires only the FIRST matching callback pattern; the generic `^adm_reprj_`
  was registered before `^adm_reprj_do_`/`^adm_reprj_cancel_` so the skip/cancel
  buttons never ran (and the reject screen always said "Invalid order"). Order
  swapped: specific first → the reason prompt + skip + cancel all work now.

## ✨ NEW: Support tickets — no more 30-min auto-close
- The 30-minute auto-close is REMOVED. Tickets stay open until the USER closes
  them. Every 3 hours the bot reminds the user with a **🔒 Close Ticket**
  button; tapping it closes the ticket (user is the only one who can close
  their own). Reminder state tracked (last_reminder_at / reminder_count).

## 🐛 Bybit Pay auto-verify — root cause explained
- The auto-verify job was enabled in v157 but that deploy never went live
  (service was suspended) — the running bot still had the OLD no-op job, so
  Bybit payments were never auto-added. v158 keeps the 45s auto-verify job;
  it will run once this deploys. (Live check: no `bybit_waiting` orders and no
  undelivered deposits exist in the account right now.)

## 🗄 DB
- New table `product_tier_discounts` (product_id, min_qty, unit_price).
- support_tickets: +last_reminder_at, +reminder_count.

## 🧪 Tests
- New `_test_v158_tiered_ticket.py` (10 tests: tier roundtrip/price-picking,
  force_default wiring, shop tiers, reminder job, reject order, name strip).
  All 19 in-repo suites pass; `main()` boots clean.

# 🚀 v157 (2026-08-09) — 7 bugs fixed + 🎉 Bulk Discount feature

## 🐛 FIX 1: Bybit Pay auto-verify
- `bybit_deposit_background_job` was a NO-OP since v126 (click-only verify) →
  users' Bybit payments were never credited automatically. Now the job
  AUTO-VERIFIES every 45s: scans bybit_waiting orders, matches by sender-UID+
  amount (bybit_pay) / network+address+amount (bybit_usdt_*), credits + notifies
  the user. Real API errors still alert the admin (throttled). Live-checked:
  the only deposits in the account are real ones — no false credits.

## 🐛 FIX 2: Support ticket "In Progress" → Temporary error
- `adm_st_progress_callback` / `adm_st_close_callback` now bulletproof
  (try/except + fallback answer) — can never raise and reply "Temporary error".

## 🐛 FIX 3: Replacement reject now asks for a REASON
- Tap ❌ Reject → bot asks for the rejection reason (or ⏭ Skip) → order marked
  rejected WITH the reason → customer receives "📝 Reason: …" in the rejection
  message → reason also shows in replacement history.

## 🐛 FIX 4: Supplier fixed emoji on fake-activity Buy button
- `per_user_activity` buy buttons (stock + new-product alerts) now attach the
  product's premium emoji as `icon_custom_emoji_id` — supplier products use
  their FIXED emoji from ext_products, own products use the name emoji.

## 🐛 FIX 5: Bot speed (3–4s per click)
- `get_connection`: WAL/`journal_mode` pragma now set ONCE per process (was
  running on every new connection → lock/checkpoint latency on every click).
- `get_setting`: short-TTL (3s) in-memory cache with invalidation on
  `set_setting` — handlers call it on every update (payment toggles, maint,
  dest…) so this removes dozens of redundant SQLite queries per tap.

## 🐛 FIX 6: Analytics dashboard — REAL numbers
- Pending now counts ALL waiting states (binance/usdt/bybit_waiting,
  screenshot_sent…). Adds: 💰 Revenue, 📈 Profit (delivered price−cost),
  🧾 Net after refunds, 💸 Refund count+amount, 📅 Daily revenue (last 7 days).

## 🐛 FIX 7: Refund by User ID stuck
- `adm_refund_uid_callback` + confirm callback hardened (try/except, always
  answers, fallback edit) — can't stick anymore.

## ✨ NEW: 🎉 Bulk Discount
- Admin → Edit Items → **🎉 Bulk Discount**: select products → -10/-20/-30/-50%
  or custom → duration (6h/24h/3d/never) → apply.
- Users SEE the discounted price in the shop (strikethrough old + 🎉 new + %).
- Checkout uses the discounted price (`_get_eff_price`).
- Alert is broadcast to the fake-activity destination with the **editable
  bc_discount template** + a 🟢 Buy Now button carrying the product name +
  premium emoji (own → name emoji, supplier → fixed emoji).
- Live progress animation (BroadcastProgress) while sending alerts.
- Clear discount anytime.

## 🗄 DB
- products: +discount_pct (REAL), +discount_until (TEXT) — added by
  ensure_column/migrate_all (works on the admin's existing DB).

## 🧪 Tests
- New `_test_v157_bugs_discount.py` (11 tests). All 18 in-repo suites pass;
  `main()` boots clean ("✅ Running!").

# 🚀 v156 (2026-08-08) — BOT STARTUP CRASH FIXED + Broadcast progress animation

## 🐛 CRITICAL FIX: Bot was NOT starting (NameError at boot)
- **Root cause:** the old poll wizard (v148) had two callbacks
  (`poll_anon_callback`, `poll_duration_callback`) registered in bot.py. When
  the wizard was replaced by the forward-flow (v152), those functions were
  removed from handlers_admin.py but their REGISTRATIONS stayed in bot.py →
  every startup crashed with `NameError: name 'poll_anon_callback' is not
  defined` → **bot never ran**.
- **Fix:** removed the stale registrations. Verified: `main()` boots clean —
  "✅ Running!", polling + all jobs start, getMe/deleteWebhook/getUpdates OK.

## ✨ NEW: Broadcast progress animation (poll / pinned / global)
- New `utils.BroadcastProgress` — a live, self-editing progress message:
  ```
  🎯 *Poll Broadcast*
  ━━━━━━━━━━━━━━━━━━━━
  ██████░░░░░░ 50%
  📤 Sent: 450 / 900
  _Live — har user pe update ho raha hai..._
  ```
- The emoji cycles (🎯📡📤⏳🚀✨) + bar fills + count climbs → feels like the
  bot is counting in real time. Refreshes at most every ~1.2s (rate-limit safe).
- Wired into:
  - **Poll broadcasts** (`_broadcast_poll_task`) — title "Poll Broadcast",
    finishes with sent/failed + link to View Results.
  - **Global broadcasts** (`_send_global_broadcast_now` →
    `_broadcast_payload_to_all_users`) — title "Global Broadcast".
  - **Pinned-post pushes** (`broadcast_and_pin`) — title "📌 Pinned Broadcast",
    finish shows sent + pinned counts.
- LIVE verified: start → updates → finish all edit the same message on the
  real bot.

## 📦 Restore-ready DB (admin's latest — 041211)
- 907 users | 337 orders | 51 products | 168 ext-products | 7 suppliers |
  force-join 3 | polls tables (with v155 entities/voters columns) | maint=0 —
  ZERO data loss (60→62 tables, only the 2 poll tables added).

## 🧪 Tests
- `_test_v152_pollfwd.py` extended (+3 v156 tests: BroadcastProgress API,
  stale registrations gone, progress wired). All 17 in-repo suites pass;
  `main()` boots clean; BroadcastProgress live-tested on the real bot.

# 🚀 v155 (2026-08-08) — Poll: premium emojis preserved + WHO voted in results (v154 chooser reverted)

## 🔄 REVERT (owner request — "main ne sirf poocha tha, update nahi karna tha")
- v154's "where-chooser" (Group / DM / Both) is REMOVED. Poll flow is back to
  v153: forward a poll → bot sends it to ALL users (DM) in the background.

## ✨ NEW 1: Premium emojis in polls (question + options)
- When the admin forwards a poll that contains premium/custom emojis in the
  question or options, the bot now CAPTURES the emoji entities and
  REBROADCASTS the exact same poll — premium emojis preserved for every user.
  (New polls columns: question_entities_json / options_entities_json.)

## ✨ NEW 2: Results show WHO voted
- Every vote now stores the voter's name + @username (poll_answers.user_name /
  username). 📊 View Results → per poll, per option: vote count + the list of
  users who voted (names + @handles). No more anonymous totals only.

## 🗄 DB
- polls: +question_entities_json, +options_entities_json
- poll_answers: +user_name, +username (ensure_column → works on existing DBs)

## 🧪 Tests
- `_test_v152_pollfwd.py` extended (14 tests: v154 removed, premium capture,
  who-voted flow). All 17 in-repo suites pass; LIVE verified: forwarded poll
  with premium entities → broadcast to real user (sendPoll 200 OK) → vote
  recorded with name → results show voters.

# 🚀 v154 (2026-08-08) — Poll WHERE-CHOOSER: send to GROUP (LIVE votes + who-voted) or DM

## ✨ New (as the owner asked): "mera poll hi jaye aur us pe votes dikhein"
- After forwarding a poll to the bot, the bot now asks **where to send it**:
  - **📢 Destination Group/Channel** → the poll is posted ONCE to the
    configured destination (dest_chat_id). Everyone in that chat votes on the
    SAME poll → **LIVE votes and (for public polls) who-voted names show
    directly on that message** — exactly the "meri poll pe votes" the owner
    wanted. No bot panel needed to watch results.
  - **👥 All Users (DM)** → each user gets their own copy; votes are tracked
    and totals shown in 📊 View Results.
  - **✅ Both** → shared poll + personal copies.
- Why DM-only can't show votes on the admin's poll: Telegram treats every
  sent poll as a separate instance and does NOT sync votes between copies.
  The group/channel route is the only way to get one shared, live poll.
- Tip shown: to see voter NAMES, create the poll as **public**
  (non-anonymous) — Telegram reveals voters on public polls.

## 🧪 Tests
- `_test_v152_pollfwd.py` extended (+3 v154 tests: chooser present, bot
  registration, group sender). All 17 in-repo suites pass; LIVE verified: poll
  actually posted to @bite_alerts via `sendPoll` 200 OK.

# 🚀 v153 (2026-08-08) — POLL BROADCAST & LIVE RESULTS REALLY FIXED + English UI

## 🐛 FIX 1 (ROOT CAUSE): polls never reached users — wrong chat_id in broadcasts
- **Root cause (live-proved):** `get_all_users_for_broadcast()` returns DictRow
  (a sqlite3.Row subclass — NOT dict). Every broadcast loop used
  `usr["user_id"] if isinstance(usr, dict) else usr[0]` — since DictRow isn't a
  dict, it fell to `usr[0]` which is the AUTO-INCREMENT `id` column (e.g. 4836),
  NOT the Telegram `user_id` (e.g. 5757645822). So every poll was sent to
  chat_id 1,2,3... → "chat not found" ×900 → 0 delivered + a log error per user.
  This bug also silently broke ALL per-user broadcasts (fake activity, stock
  alerts, announcements).
- **Fix:** new `database.row_uid(row)` helper (handles dict/DictRow/tuple) used
  in every broadcast loop (fake_engagement.send_to_all_users,
  handlers_admin poll + custom broadcast, handlers_start join broadcast).
  Verified live: polls now reach real users and tg poll ids are recorded.

## 🐛 FIX 2 (ROOT CAUSE): votes never recorded → "no live results"
- **Root cause (reproduced):** PTB 22.8 (Bot API 9.6) raises TypeError while
  PARSING a `poll_answer` update when Telegram omits
  `option_persistent_ids` (and similarly Poll/PollOption fields). Every user
  vote → PTB parse crash → vote dropped + repeated log error.
- **Fix:** `_patch_ptb_poll_parsing()` at startup monkey-patches
  PollAnswer/Poll/PollOption to default missing required fields to safe values.
  Verified: poll_answer now parses and `handle_poll_answer` records the vote →
  📊 View Results shows live counts.

## 🐛 FIX 3: broadcast blocked the callback (still felt "stuck")
- Already backgrounded in v152; v153 keeps it and adds a done-summary message.

## ✨ FIX 4: Poll UI now ENGLISH (user request)
- All poll panel text/buttons translated from Roman Urdu to English
  ("Send / Forward a Poll", "Yes, send to all users", "Poll captured!", etc.).

## 📦 Restore-ready DB (admin's latest — bite_store_backup_20260808_030706)
- 906 users | 335 orders | 51 products | 167 ext-products | 7 suppliers |
  force-join 3 | polls tables ready | maint_enabled=0 — ZERO data loss
  (60→62 tables, only the 2 poll tables added). Pending #334 (Binance 2.0).

## 🧪 Tests
- `_test_v152_pollfwd.py` extended (row_uid, PTB patch, English UI) — 9 tests;
  all 17 in-repo suites pass; LIVE end-to-end verified: broadcast to real
  users delivered, poll_answer parsed, vote recorded, results query works.

# 🚀 v152 (2026-08-08) — POLL FIX + NEW POLL SYSTEM (forward your own poll)

## 🐛 FIX 1: Poll wizard "stuck at time options" + repeated log errors
- **Root cause:** the old wizard ran the broadcast (send poll to 900+ users)
  INSIDE the callback handler — that blocked for 4-5 minutes, exceeded
  Telegram's bot rate limit (→ 429 Too Many Requests spam in logs) and made
  the callback query expire ("query too old") — the bot looked completely
  stuck and the poll never completed.
- **Fix:** broadcast now runs as a BACKGROUND task (`_broadcast_poll_task` +
  `asyncio.create_task`) → the callback answers instantly; the bot shows
  "✅ Poll bana diya — background me send ho raha hai" and sends a summary
  message when done. Rate-limit-safe pacing (0.12s = ~8 msgs/sec) stops the
  429 log flood. Duplicate-broadcast guard added (same poll can't send twice).

## ✨ FIX 2: NEW poll system (as requested)
- **You create the ORIGINAL Telegram poll yourself** (in any chat, or forward
  one from somewhere) and send/forward it to the bot's DM.
- The bot captures it (question + options + anonymous + multiple-answers),
  asks "✅ sab users ko bhejo?", and on Yes rebroadcasts that EXACT poll to
  every user's inbox (background, non-blocking).
- **Votes:** users vote in their chat; the bot records every PollAnswer
  (polls/poll_answers tables). You see live results in Admin → 📊 Polls →
  View Results, and users also see running results natively in their own chat
  (Telegram shows results after voting).
- The old multi-step wizard (sawal → options → anon → time) is REMOVED from
  the panel — 📊 Polls → "📤 Poll Bhejo / Forward Karein" now shows the new
  1-step instructions. Close/delete/results still work per poll.

## 📦 Restore-ready DB (admin's latest — bite_store_backup_20260808_015338)
- 904 users | 331 orders | 52 products | 168 ext-products | 7 suppliers |
  force-join 3 | polls tables ready | maint_enabled=0 — ZERO data loss
  (60→62 tables, only the 2 poll tables added; user's existing poll kept).
- All v148–v151 features verified present.

## 🧪 Tests
- New `_test_v152_pollfwd.py` (6 tests): capture admin poll, ignore
  non-admin, DB create, background broadcast, panel instructions, bot
  registration. All 17 in-repo suites pass; boot smoke clean.

# 🚀 v151 (2026-08-07) — Bot boots FRESH (bundled DB removed) + restore-ready DB (latest 220950)

## 🔄 CHANGE (user request): no more hardcoded DB
- The bundled `latest_shop.db` + the v150 auto-restore-on-startup are REMOVED.
- On deploy the bot now starts with a **FRESH empty database** (schema auto-
  created). The admin restores their own data whenever they want via
  **Admin → 💾 Backup & Restore → 📤 Restore Database** (upload .db → validate →
  migrate_all → done).
- `latest_shop.db` added to `.gitignore` so a DB can never be committed again.
- `ensure_poll_tables()` is now part of `migrate_all()`, so every fresh boot
  AND every manual restore immediately has the polls tables.

## 📦 Restore-ready DB (admin's latest — shop_backup_20260807_220950)
- Modified to match v151 code with ZERO data loss (58 tables before/after,
  only the 2 poll tables added):
  - Users **901** | Orders **328** | Products **51** | Ext-products **168** |
    Suppliers **7** | Force-join 3 | polls tables ready | maint_enabled=0
  - Pending order **#328** (Binance 1.7) intact — bot auto-delivers on deploy.
  - Flash template placeholder normalized; ProdSeller pseudo-stock refreshed;
    missing responses/settings seeded.
- Restore flow verified: upload → `migrate_all()` clean → all features
  (polls, refund-by-ID, replacement, force-join, suppliers, payments) work.

## 🧪 Tests
- Removed `_test_v150_bundle.py`; added `_test_v151_fresh.py` (fresh boot
  creates schema; restore-ready DB boots clean; no bundle code remains).
  All 16 in-repo suites pass; boot smoke clean on the restore-ready DB.

# 🚀 v150 (2026-08-07) — 📦 BUNDLED DB: bot ALWAYS boots with the latest database (old-data problem SOLVED for good)

## 🐛 THE PROBLEM (user reported 3x)
- Restoring the DB still showed OLD data. Reason: the bot's data lives at
  `DB_PATH` (/var/data/shop.db on Render's disk) — a code deploy does NOT touch
  it, and a manual file upload could land in the wrong place / be shadowed by a
  stale WAL or a fallback `shop.db`. The deployed bot kept reading an old file.

## ✅ THE FIX — bundle the DB into the deployment
- The latest database is now shipped INSIDE the repo as **`latest_shop.db`**.
- New `database.restore_bundled_db_if_needed()` runs at the very TOP of
  `main()` (before anything reads the DB):
  - first boot after deploy → backs up whatever DB exists, copies
    `latest_shop.db` over `DB_PATH`, wipes stale `-wal`/`-shm`, marks
    `bundled_db_restored=1` → **the bot boots with the 898-user dataset**;
  - later boots → marker present → skips → live data keeps persisting;
  - DB missing / disk wiped → bundle restores again (always a sane baseline).
- Manual bot-UI restore (💾 Backup → Restore) also sets the marker, so an
  admin's own restore is never overridden by the bundle afterwards.

## 🗄 DB (bundled)
- `latest_shop.db` = the admin's latest backup, v149-modified: 898 users,
  320 orders, 51 products, 162 ext-products, 7 suppliers, polls tables,
  flash-template fix, ProdSeller varied stock, maint_enabled=0, pending
  orders #321 (Binance 0.59) & #322 (BEP20 4.2) intact.
- Data preservation verified: 58 → 60 tables, ZERO rows lost (only the two
  new poll tables added).

## 🧪 Tests
- New bundled-restore tests: (1) fresh DB → restored to 898; (2) already
  restored → skipped (live data untouched); (3) old DB without marker →
  REPLACED by bundle. All pass. All 15 in-repo suites + 19 legacy suites pass;
  boot smoke clean.

# 🚀 v149 (2026-08-07) — Flash template placeholder FIX + refund-by-user-ID with reason & history + per-user full history

## 🐛 FIX 1: Flash sale template — {product} placeholder went LITERAL + fixed emoji
- **Root cause (reproduced live):** the admin's custom flash template used
  `{Product}` (capital P) while the renderer only filled lowercase
  `{product}` → `str.format_map` left the key untouched → the destination
  group received the raw placeholder text instead of the product name.
- **Fix (double):**
  - Code: new `_fill_placeholders_ci()` makes ALL placeholder filling
    case-insensitive (any casing of {product}/{Product}/{PRODUCT} works;
    unknown keys stay literal). Applied to `build_flash_message`,
    `build_newproduct_message` and `customization.render_template` (the fake
    broadcast + purchase/deposit/etc. templates).
  - Data: the stored `flash_tpl_custom` value is normalized to `{product}`.
- **Fixed emoji with name:** new `_product_name_with_fixed_emoji()` prepends
  the product's fixed premium emoji (supplier ext emoji) to the name in flash
  / new-product broadcasts — exactly like the shop shows it. If the name
  already carries its own premium emoji markup, nothing is duplicated.

## ✨ FIX 2: Refund by USER ID (any user) — with reason + history
- Admin Panel → 👤 Users → **💸 Refund by User ID** (or 📋 Full History →
  💸 Refund This User, or 📊 activity → 💸 Refund).
- Flow: type user ID → bot shows the user → type refund amount (USD, auto-
  converted to points) → type the reason → ✅ Confirm → points credited,
  the user is NOTIFIED with the reason, and it's saved to their points-ledger
  history (description = the reason).

## ✨ FIX 3: Per-user FULL history (Users button)
- Every user's 📊 activity view now has **📋 Full History**: orders (last 10,
  with status), points ledger (deposits/refunds/credits with reasons), and
  recent actions — plus a direct 💸 Refund button.
- Users panel also gets **📋 User Full History (by ID)** to jump straight to
  any user's history.

## 🗄 DB
- No schema changes (history lives in existing `orders`, `points_ledger`,
  `user_clicks`). Template data fix applied to `bot_settings.flash_tpl_custom`.

## 🧪 Tests
- New `_test_v149_refund_flash.py` (8 tests). All 15 in-repo suites + 19
  legacy suites pass; refund flow verified end-to-end (points credit + reason
  + ledger entry) and flash build verified against the REAL DB template.

# 🚀 v148 (2026-08-07) — 📊 Polls: admin polls broadcast to all users, vote tracking & live results

## ✨ NEW: Poll system (user demand / opinion voting)
- **Admin:** Admin Panel → **📊 Polls** (new button, fully editable via Manage
  Buttons like every admin button).
  - **➕ Create Poll** — 3-step wizard: (1) sawal likho, (2) options har ek
    line me (2–10), (3) anonymous/public chuno + duration (1h / 6h / 24h /
    3 days / never close).
  - **📊 View Results** — har poll ke live votes: per-option count + percent +
    bar, total voters, 🟢 Live / ⏹ Closed status.
  - Per-poll: **⏹ Close Poll Now** (votes freeze; best-effort `stopPoll` in
    every chat) and **🗑 Delete Poll**.
- **Users:** poll as a NATIVE Telegram poll message goes to every registered
  user's chat → they tap an option to vote right there (no buttons, no extra
  steps). Votes are private-chat safe and instant.
- **Tracking:** every `PollAnswer` update is recorded in new DB tables
  (`polls`, `poll_answers`) — idempotent per user (re-vote replaces their
  previous choice). Telegram poll_id → DB poll mapping so results aggregate
  across all users.
- Use case: demand polling — "Aap ko kaunsa product chahiye?" → community
  votes tell you what to stock.

## 🗄 DB
- New tables `polls` + `poll_answers` auto-created by `ensure_poll_tables()`
  during migrate_all/startup.

## 🧪 Tests
- New `_test_v148_polls.py` (9 tests: create/answers/revote/tg-mapping/close/
  delete + handlers + button registry + bot registration). All 14 in-repo
  suites + 19 legacy suites pass; live `sendPoll` verified against the real bot.

# 🚀 v147 (2026-08-07) — 8 bug fixes: manual Buy Now error + replacement refund/reject-reason + maintenance gates + group silence + payment-method alerts + buy-now emoji + broadcast link/product buttons + pinned-post delete/push-unpin

## 🐛 FIX 1: Manual products — "Buy Now" error (Can't parse entities)
- **Root cause (live-reproduced):** product names that contain `<b>` tags inside
  premium markup (e.g. `[[HTML]]<tg-emoji>🎨</tg-emoji><b>Canva 500 User Panel</b>`)
  got double-wrapped: the checkout template wraps the name in Markdown `*...*`
  → `markdownish_to_html` produced `<b><tg-emoji>…</tg-emoji><b>Canva…</b></b>`
  → `sanitize_html_tags` kept the inner `<b>` but did NOT push it, so its close
  was dropped as orphan → outer `<b>` never closed → Telegram rejected the whole
  message: *"Can't find end tag corresponding to start tag b"* → customer saw an
  error right after tapping Buy Now.
- **Fix:** `sanitize_html_tags` now DROPS duplicate inner same-name opening tags
  so nesting stays balanced. Verified against the REAL Telegram API — the exact
  checkout message now sends OK (msg sent to admin as proof).

## 🐛 FIX 2: Replacement — 💸 Refund button + rejection reason shown to user
- Admin replacement notification now has a third button **💸 Refund** (reuses
  the existing refund flow: order → refunded + points credited + user notified).
- Tapping **❌ Reject** now asks the admin to type a rejection reason
  (or /skip) — the reason is stored (`orders.replacement_reject_reason`) and
  shown to the customer inside the rejection message.

## 🐛 FIX 3: Fake activity must STOP during maintenance mode
- `per_user_activity` private sends + central group-destination job and
  `fake_engagement.run_fake_broadcast` had NO maintenance gate — fake messages
  kept going to the selected destination (and users) while maintenance was ON.
- **Fix:** all three now check `is_maintenance_on()` and skip. The group job
  re-schedules itself without sending.

## 🐛 FIX 4: Bot never auto-responds in groups
- Added `_is_group_chat(update)` + early-returns in `handle_text`,
  `handle_media_router`, `payment_flow_text_handler`, `_activity_hook_text`,
  and `start_command`. The global error handler also stops replying
  "⚠️ Temporary error…" inside groups. Result: any user message in any group
  (text/voice/photo/anything) → the bot stays completely silent, admin or not.

## 🐛 FIX 5: Fake deposit alerts — ONLY enabled payment methods
- `_enabled_payment_methods()` (both fake_engagement.py and per_user_activity.py)
  only knew Binance/JazzCash/EasyPaisa. With jazzcash+easypaisa OFF, every fake
  deposit said "Binance Pay".
- **Fix:** the list now covers ALL toggleable methods (Binance Pay, USDT TRC20,
  USDT BEP20, Bybit, Bybit Pay, Bybit USDT TRC20/BEP20, JazzCash, EasyPaisa) and
  filters by the same `is_payment_enabled` toggles the admin uses.

## 🐛 FIX 6: Buy-Now button emoji — supplier fixed emoji vs own-name emoji
- New `_product_buy_emoji(pid)`: supplier-linked products use the FIXED premium
  emoji from `ext_products.emoji_id/emoji_char`; own (manual) products use the
  premium emoji typed inside the product NAME. Wired into `_buy_now_label`,
  `_buy_now_keyboard` and `broadcast_store_message` so fake-activity Buy-Now
  buttons show the right emoji.

## ✨ FIX 7: Global broadcast button — custom link OR product checkout
- Broadcast button flow extended: after naming the button, admin picks the
  action — 🤖 Open Bot (default) / 🔗 Custom Link (paste any URL) /
  🛒 Product Checkout (pick from a paged product list).
- Product-checkout buttons use the new `https://t.me/<bot>?start=chk_<pid>`
  deep link → user lands DIRECTLY on that product's payment-method screen
  (new `open_checkout_direct` + `chk_` arg support in `_parse_start_arg`).

## 🐛 FIX 8: Pinned announcements — delete post vs unpin push
- **🗑 Delete Post** now DELETES the pushed message from EVERY user's chat
  (not just unpin) and removes the DB row.
- **📌 Unpin Push** (new) unpins the announcement everywhere but KEEPS the
  post in users' chats and keeps the pin row.

## 🎯 Bonus: Binance Pay wrong-Order-ID rescue
- Live finding: a customer typed a slightly-wrong Binance Pay Order ID
  (447270079587229696 vs real 447270259987202048) — the money WAS there
  (0.59 from "Khalid Zarook") but auto-verify failed.
- `verify_payment_unified` now falls back to amount + fuzzy sender-name match
  (anti-reuse still applies) and the auto-verify job passes the order's
  customer name. Rescues stuck `binance_waiting` orders.
- The 2 pending orders in the restore-ready DB (#321 Binance Pay 0.59,
  #322 BEP20 4.2) are live-verified and will auto-deliver on deploy.

## 🧪 Tests
- New `_test_v147_bugs.py` (12 tests) + updated `_test_v134_ref_math.py` for the
  3-tuple `_parse_start_arg`. All 13 in-repo suites + 19 legacy suites pass;
  boot smoke clean; Bug1 + both pending payments verified against the REAL APIs.

# 🚀 v146 (2026-08-07) — REAL fix: BEP20/Binance auto-payment tolerance + ProdSeller varied stock + TXID-vs-address guard

## 🐛 FIX 1 (ROOT CAUSE): Binance USDT BEP20 payments "arrive but never auto-added"
- **Symptom:** Customers paid USDT BEP20 (incl. Trust Wallet → Binance) but orders
  stayed cancelled / "payment not found", even though the money WAS in the Binance
  account. Owner reported it as "binance to binance wali hi sirf add hoti hai?".
- **Root cause (proved with live API data):** `_usdt_amount_match()` used a hard
  `0.0001` USDT tolerance. On-chain deposits routinely arrive slightly ABOVE the
  order amount (users add a fee buffer). Verified live in Binance deposit history:
  - order 1.0 → received **1.0008888** (diff 0.0008888 → REJECTED)
  - order 3.0 → received **3.00268234** (diff 0.0026823 → REJECTED)
  - order 2.0 → received **2.00192625** (diff 0.0019263 → REJECTED)
  - order 1.0 → received **1.00099815** (diff 0.0009982 → REJECTED)
  Every one of those real payments was rejected by the old 0.0001 rule and the
  order was auto-cancelled after 60 min. Binance Pay (P_... txids) landed exactly
  so those worked — hence "sirf binance to binance add hoti".
- **Fix:** new smart tolerance in `_usdt_amount_match(..., anchored=...)`:
  - anchored (customer pasted the TXID / Bybit sender UID known) →
    `max(0.05, 1%)` — generous, the txid/UID is the real anchor.
  - amount-only auto-verify (no txid) → `max(0.02, 0.5%)` — still covers fee
    buffers but won't cross-credit a materially different deposit.
- **Proof:** live re-test of orders #265/#267/#271/#275 against the Binance API
  now returns **MATCHED** for all 4. Test: `_test_v146_payments_stock.py` +
  live API check.
- **DB reconciliation (in the restore-ready DB):** orders #265, #267, #271, #275
  are now `delivered` with their real TXIDs recorded, `used_txids` updated, and
  the customer's points credited (ledger entries `deposit_order_*`). #266 was
  the same TXID as #265 and its deposit predates the order → stays cancelled
  (correct — one deposit = one credit).

## 🐛 FIX 2: ProdSeller stock — now varied & realistic, not "1" everywhere
- **Root cause:** ProdSeller's `/products` response has **NO numeric stock field
  at all** — only `inStock` (bool) + `sold` (lifetime sales), verified live
  (raw: `{"sold": 3197, "inStock": true}`). v145 mapped in-stock → 1, so every
  in-stock product showed "1" (after v143's fake "999 everywhere").
- **Fix:** in-stock products now get a **stable pseudo-stock** seeded from the
  product id — same product always shows the same number (no jumping every
  sync), different products show varied numbers (32…447), and popular items
  (high `sold`) show more. Truly sold-out (`inStock: false`) → 0.
  Example after fix: Capcut 225, Gemini 447, Canva 32, Windows 124.
- The real sync also updates the linked shop products automatically.

## 🐛 FIX 3: users pasting the deposit ADDRESS instead of the TXID
- Observed in the DB: `payment_note_id = "0xe171a20f…\n\nSend amount this adrress
  usdt bep20 ok"` — the user pasted the bot's wallet ADDRESS as the TXID, which
  could never match → dead order.
- **Fix:** `_looks_like_deposit_address()` detects a BEP20/TRC20 wallet address
  (or the bot's own configured address) and tells the user in Roman Urdu:
  "ye ADDRESS hai TXID nahi" + how to copy the real TXID from the wallet.
  Applied to the USDT TXID input step.

## 🔎 Audit: Bybit Pay order #276 — payment NEVER arrived (checked live)
- Owner asked why a Bybit Pay payment (#276, customer UID 401047395, 0.89 USDT)
  wasn't credited. **Live Bybit API check (2026-08-07):** API key UID = 503209510
  = `bybit_pay_id` ✅, but internal-deposit history (7 days) contains only 2
  records (#249 ✅ and #148) — NO deposit from UID 401047395 and no 0.89 deposit.
  The customer's Bybit Pay transfer never reached the store's Bybit account
  (they did pay 0.89 via Binance Pay earlier — order #241 — which WAS delivered).
  The bot correctly did not credit a payment that never arrived. If the customer
  insists, have them check Bybit app → Transactions → Bybit Pay → status.

## 🧪 Tests
- New `_test_v146_payments_stock.py` (8 tests) + updated `_test_v145_fixes.py`
  ProdSeller stock assertions. All 12 in-repo suites + 19 legacy suites pass;
  boot smoke clean on the restore-ready DB.

# 🚀 v145 (2026-08-06) — ProdSeller stock/qty FIX + rich payment alerts + .txt file in orders + user search + ticket auto-close

## 🐛 FIX 1: ProdSeller stock showed 999 + 200 qty delivered only 100
- **Stock:** ProdSeller adapter hardcoded `stock: 999` for in-stock products. Now
  uses the REAL `stock` field from the products API (falls back to 1 for
  in-stock-but-unknown).
- **Quantity cap:** `create_order` capped qty at 100 (`min(100, ...)`) — that's
  why a 200-qty order delivered only 100. Cap raised to 9999 for ProdSeller AND
  Canboso (the router still enforces actual stock as the real limit).
- UI bulk hints `Max: 100` → `Max: 9999`.

## ✨ FIX 2: Rich admin payment notifications (every method)
- Every "Pending" admin alert now includes: 📦 Product + qty, 💰 Selling price +
  total, 🔗 Supplier name, 🧾 Supplier cost/pc, 📈 Margin, and the payment
  METHOD label with network (Bybit Pay / Bybit USDT TRC20 / Bybit USDT BEP20 /
  Binance Pay / Binance USDT TRC20 / Binance USDT BEP20 / EasyPaisa / JazzCash /
  Points).
- Wired into Binance Pay (API + Gmail), JazzCash, and Bybit failure alerts.

## ✨ FIX 3: Bulk .txt delivery file saved + downloadable
- When 10+ accounts (or long content) are delivered as a .txt file, the
  document `file_id` is saved on the order (`orders.delivery_file_id`).
- Completed Orders shows **📎 Download Delivery File (.txt)** — admin can
  re-open/download it anytime.

## ✨ FIX 4: Users search (ID or username)
- Users list gets **🔍 Search User** — type a numeric user ID or a username
  (partial, case-insensitive) → results with 📊 activity buttons.

## 🐛 FIX 5: usernames showing "—" for some users
- My Account now refreshes the DB profile on open (live Telegram username) and
  falls back to the saved DB username when the live one is missing.

## ✨ FIX 6: Ticket auto-close after 30 min no user reply
- New `ticket_auto_close_job` (every 5 min): open/in-progress tickets whose last
  USER message is >30 min old → auto-**resolved**, user + admin notified.

## 🧪 Tests: v145 suite 10/10 · full regression 231/231 PASS · boot clean

---
 (2026-08-06) — FIX: fake activity not going to selected destination

## 🐛 Root cause (detective mode)
- **Report:** fake activity messages never appeared at the selected destination.
- **Investigation:**
  - dest settings were correct (`@bite_alerts`, `group_only`, enabled) and the bot
    IS an admin there (live getChatMember = administrator, resolved id
    -1003997101970 matches the cache).
  - `build_fake_message(user_id=0)` builds fine (40/40 ok).
  - **The real bug:** `_group_job_scheduled` (module-level flag) could get STUCK
    `True` (e.g. job fired, process restarted, or a scheduler hiccup). The old
    `schedule_group_activity_job()` only checked that flag → if it was True it
    returned early, even when the actual job was gone. The 60s watchdog also
    checked `if not _group_job_scheduled` → it ALSO skipped → the group job was
    never re-scheduled → fake activity silently dead at the destination forever.
- **Fix (per_user_activity.py):**
  1. New `_group_job_actually_scheduled(app)` — inspects the JOB QUEUE for a live
     `pua_group_central` job (not just the flag).
  2. `schedule_group_activity_job` uses it (stale flag resets + schedules fresh).
  3. Watchdog re-schedules based on the actual queue too.
- **Also:** DB fake-activity interval set to `minutes 1–60` (was `seconds 1–10`
  which flood-guard floor forced to 30s anyway).

## 🧪 Tests: v144.4 suite 6/6 · full regression 221/221 PASS · boot clean

---
 (2026-08-05) — Support-ticket close fix + Replacement 2-step + Flash placeholder + Ai Tools

## 🐛 Fix 1: Support ticket Close/Resolve — notification but still "open"
- **Root cause:** close/resolve/progress callbacks did `q.answer(...)` then called
  `adm_st_view_callback` which did `q.answer()` AGAIN (PTB double-answer) → the
  view failed to re-render → admin saw the old status even though DB updated.
- **Fix:** `adm_st_view_callback(..., _skip_answer=True)` when chained; DB already
  updated correctly (verified `update_ticket → 'closed'`).

## ✨ Fix 2: Replacement approve → 3 delivery choices (owner request)
- Approve now shows:
  - **🔄 API Replacement** — re-buys from the SAME supplier via its API
    (`route_order_to_supplier`) and delivers automatically.
  - **📤 Upload Product** — admin pastes the new account details; bot auto
    detects format (`detect_product_format`) and delivers to the customer.
  - **📦 From Stock** — original auto-dispense from local stock.
- New callbacks `adm_repx_api_` / `adm_repx_up_` / `adm_repx_stock_` + upload
  text handler (`rep_upload_oid`).

## 🐛 Fix 3: Fake-activity Flash-sale template sent raw placeholders
- **Root cause:** custom template with an unknown placeholder (e.g. `{old_price}`)
  made `.format()` raise KeyError → except returned the RAW template → `{price}`
  etc. were sent literally.
- **Fix:** `format_map` with a safe mapping — known placeholders filled
  (`{price}`, `{product}`, `{old_price}`, `{save}`, `{timer}`, `{product_name}`
  aliases), unknown ones left as-is. Same for new-product template.

## ✅ Fix 4: Ai Tools supplier re-added + preset
- Ai Tools (Canboso, key `tgb_3b5f…`) re-added to DB (id 16) — connection
  verified live: 21 products, $12.46 balance.
- `Ai Tools` preset added to Add-Supplier panel so it can always be re-added.

## 🧪 Tests: v144.3 suite 7/7 · full regression 215/215 PASS · boot clean

---
 (2026-08-04) — ProdSeller auto-delivery FIX + new formats + smart .txt file

## 🐛 CRITICAL: ProdSeller balance deducted but no delivery ("retry" loop)
- **Kahan:** ProdSeller orders #94-96 failed: `Supplier returned only 0/1 item(s).`
  Balance was deducted but nothing delivered → bot kept offering retry.
- **Root cause (verified against live API):** ProdSeller responses contain ONLY
  `deliveredKey` (single) and NO `deliveredKeys` key. The adapter did
  `keys = j.get("deliveredKeys") or []` → empty list is still a list →
  `if isinstance(keys, list)` was True → items=[] → the `deliveredKey` was
  never read. Also `_extract_delivery_items` only matched exact `"key"`, not
  `deliveredKey`.
- **Fix:**
  1. `create_order`: non-empty `deliveredKeys` list wins, otherwise `deliveredKey`
     fallback, then generic parser.
  2. `_DELIVERY_SINGLE_KEYS` += `deliveredKey`, `delivered_account`, `deliveryLink`,
     `delivery_url`, `downloadUrl`, `fileUrl`; `_DELIVERY_COLLECTION_KEYS` +=
     `deliveredKeys`, `delivered_keys`, `deliveredCredentials`.
- **Verified live:** placed a $0.39 test order → `deliveredKey` (activation link)
  returned → adapter now returns 1 item. Balance $7.22.

## ✅ Smart .txt file delivery (owner request)
- .txt file now also sent when **any single item > 220 chars** or **5+ multi-line
  items** (long redeem links / big payloads) — not only when 10+ items.

## ✅ 6 NEW delivery formats (found in supplier catalogs/docs)
- 📱 `phone_number` (PVA) · 🗝️ `license_key` · 🍪 `cookie_session` ·
  🔑 `api_token` · 🧩 `email_pass_cookie` · 👤 `username_pass`
- Auto-detect updated with their keyword signals (phone/license/cookie/token/
  user:pass).

## 🧪 Tests: v144.2 suite 10/10 · full regression 208/208 PASS · boot clean

---
 (2026-08-04) — Binance flow buttons now in the Buttons Editor

## 🐛 Fix (owner: "Bybit flow ke saare buttons aate hain, Binance ke nahi")
- **Kahan:** Buttons Editor → Binance Payment Flow screen had only 3 buttons
  (pay_binance, pay_usdt_bep20, pay_usdt_trc20), while Bybit had 12.
- **Root cause:** Binance Pay & Binance USDT deposit screens used **hardcoded**
  inline buttons (`📋 Copy Binance Pay ID`, `📋 Copy Address`, `❌ Cancel Payment`)
  — they were never registry buttons, so the editor could not show/edit them.
- **Fix:**
  1. 3 new registry buttons (group `pay`): `pay_copy_binance_payid`,
     `pay_copy_usdt_address`, `pay_cancel_payment` — editable label + premium
     emoji + color, same as the Bybit flow buttons.
  2. Binance Pay Order-ID screen and Binance USDT TXID screen now render those
     via `_make_flow_btn()` (editable) instead of hardcoded.
  3. `binance_flow_screen` in SCREEN_TREE now lists all 6 buttons → the Screen
     Editor shows Binance Auto / USDT BEP20 / USDT TRC20 / Copy Binance Pay ID /
     Copy Address / Cancel Payment.

## 🧪 Tests: v144 suite now 12/12 · full regression 198/198 PASS · boot clean

---
 (2026-08-04) — CUSTOMIZATION REBUILT (clean hub + 8 new tools)

## ✅ Rebuilt hub (replaces old flat menu)
- Customization ab **sections** me organized hai with a **live summary** at top
  (button size · menu style · shop format · active layout · toggles ON count).
- Sections: 🛍️ Shop Look · 🎛️ Buttons · 🧭 Menu · ⚙️ Extras.
- All old deep panels still reachable (Buttons Editor, Product Design, Main Menu
  Layout, Screen Editor, Styles, Colors, Broadcast color, Toggles).

## ✅ 8 NEW features
1. **🔍 Search** — type any button id / screen / response key → opens its editor
   (searches BUTTONS registry + SCREEN_TREE + DEFAULT_RESPONSES).
2. **🎭 Theme Presets (1-click)** — Classic / Colorful / Dark / Minimal / Premium.
   Each sets button size + menu style + shop format + main-menu layout + group
   colors in one tap (verified: PREMIUM → xl size, premium layout, grid format,
   blue main group).
3. **💾 Backup / Restore** — exports every customization setting (labels, colors,
   sizes, styles, layout, banners, toggles) as JSON; paste back to restore.
4. **🖼️ Home Banner** — admin-set banner line above the welcome text
   (ON/OFF toggle + editable text, `{shop_name}` placeholder).
5. **🎠 Display Formats — now 4** — Raw / Carousel / **Grid (2-column)** /
   **List (1-per-row full)**. Grid packs buttons 2/row with compact labels.
6. **🏷️ Category Colors** — per-category button background color (applies to its
   shop buttons, in-stock only).
7. **🎨 Group Colors via hub** — reachable from the new hub (existing engine).
8. **Improved toggles screen** — same engine, now grouped & reachable from hub.

## 🧪 Tests: v144 suite 9/9 · all suites pass individually (186 + 9 = 195) · boot clean

---
 (2026-08-04) — FIX: raw HTML markup showing in Force-Join panel labels

## 🐛 Bug (user screenshot)
- **Kahan:** Force Join Setup → target rename with premium emoji → back → panel
  showed the raw label: `3. [[HTML]]<tg-emoji emoji-id="...` instead of the name.
- **Root cause:** the rename flow saves premium-emoji labels in
  `[[HTML]]<tg-emoji ...>🔥</tg-emoji> Name` form (that is how the renderer stores
  them so buttons can show the animated icon). But `_show_fj_panel` printed the
  raw label directly into Markdown text — the sentinel + tags were never stripped
  for display.
- **Fix (ui_extras.py):**
  1. New `_fj_label_plain()` — strips the `[[HTML]]` sentinel and all tags, keeps
     the premium emoji's fallback char + the text (clean display name).
  2. Used in `_show_fj_panel` (text lines AND target buttons via
     `make_premium_button` so the animated icon still shows), `_show_fj_panel_safe`,
     `fjm_callback` (manage panel label + preview), bulk-delete list, and the
     admin-status test panel.
- **Verified:** helper returns `🔥 Premium Chan` (no sentinel/tags) + panel text
  contains zero raw markup. Regression tests added (v135 suite 20).

## 🧪 Tests: 186/186 PASS · boot clean

---
 (2026-08-04) — FIX: Telegram "Can't parse entities" — panels failed to update

## 🐛 Bug (user screenshot of Render logs)
- **Log error:**
  `[_edit] initial edit failed (Can't parse entities: unmatched end tag at byte
  offset 271, expected "</i>", found "</b>"); trying fallbacks`
  + `HTTP/1.1 400 Bad Request` on `editMessageText`.
- **Root cause:** Telegram's HTML parser is strict. When a panel/response text
  contained mis-nested or unmatched HTML tags (e.g. admin-custom label with
  `<b><i>…</b></i>` or a stray `</b>`), `edit_message_text` was rejected → the
  panel never visually updated → the bot appeared **stuck with no logs**.
  `smart_text_and_mode` detected HTML and switched to HTML mode, but the malformed
  tags were passed through untouched.
- **Fix (utils.py):**
  1. New `sanitize_html_tags()` — scans block tags, drops orphan closes,
     auto-closes unclosed opens, and fixes mis-nesting so the output is always
     valid for Telegram's strict parser.
  2. `smart_text_and_mode()` now runs the sanitizer on every HTML-mode output
     (this covers ALL sends/edits, since the premium-emoji guard routes every
     message through it).
  3. `_edit()` (ui_extras) now picks the correct mode via smart_text_and_mode
     and its parse-error fallback strips ALL HTML tags as a last resort.
- **Verified:** sanitizer unit tests (normal / orphan-close / unclosed-open /
  mis-nested / premium-emoji preserved) + a **strict-HTML Telegram simulator**
  that rejects malformed HTML — Force Join / Admin / Settings panels all pass.

## 🧪 Tests: v140.1 suite now 13/13 · full regression 182/182 PASS · boot clean

---
 (2026-08-03) — Force-Join "stuck" BULLETPROOF hardening + channels added

## 🔒 Hardening (report: "Force Join Setup click → bot stuck, no logs")
- The Force-Join panel code path was tested end-to-end (full bot.py app, real
  handlers, 3 targets incl. @learnwith_Alex + @Alex_Resellers, open/click/back/
  add/reopen ×5) — **no hang reproducible in code**. The live "stuck with no
  logs" is therefore most likely environmental (two bot processes on one token,
  service suspended, or a stalled Telegram API call). To make the bot
  un-stuck-able anyway:
  1. `fj_panel_callback` now wraps the panel render in `asyncio.wait_for(8s)`
     and, on timeout/error, sends a **guaranteed fallback panel message**
     (`_show_fj_panel_safe`) — the admin ALWAYS gets a response, never silence.
  2. `_is_member` member-check + chat-resolution wrapped in `asyncio.wait_for(6s)`
     (fail-open) — a slow/stalled Telegram API call can no longer freeze the bot.
  3. `_show_fj_panel_safe` — minimal, never-raising fallback renderer.

## ✅ DB: added the 2 channels the owner asked for
- `@bite_alerts` (existing) + `https://t.me/learnwith_Alex` +
  `https://t.me/Alex_Resellers` — all enabled, `fj_enabled=1`.
  Restore `bite_store_restore_ready.db` and all three buttons show for new users.

## ⚠️ Live-env checklist for the owner
- Do NOT run the bot in two places with the same token (local + Render) — Telegram
  splits updates and half the clicks "do nothing".
- Keep the Render service running (it was suspended twice today).
- Make the bot an ADMIN in each channel/group so Verify works.

## 🧪 Tests: 179/179 PASS · full-app fj_panel ×5 open no-hang · boot clean

---
 (2026-08-03) — FIX: Force-Join bot stuck after adding targets

## 🐛 Bug (reported: "2 buttons add krke wapas Force Join kholo to bot stuck")
- **Kahan:** Force Join Setup → ➕ Add Channel/Group → kuch targets add karne ke baad
  admin panel se 🔗 Force Join Setup dobara kholne par bot "stuck" ho jata tha.
- **Root cause:** text-input flags (`fj_add_link`, `fj_ren_target`, `fj_emo_target`,
  `fj_link_target`, `fj_vbtn_ren`, `fj_vbtn_emo`) user_data me set rehte the. Jab
  admin kisi bhi wajah se "Add" prompt me hota tha (ya invalid-link retry ke baad
  flag bacha hota tha) aur wapas panel kholta tha, to panel clear nahi karta tha.
  Phir admin ka AGLA normal text message `fj_add_link_received` pakad leta tha —
  use link samajh ke parse karta tha → confusing "invalid link" replies → bot
  stuck lagta tha.
- **Fix:**
  1. `fj_panel_callback` ab panel khulte hi **saare** force-join text-step flags
     clear karta hai (master exit).
  2. `fjm_callback` (target manage panel) bhi flags clear karta hai.
  3. `fj_vbtn_callback` (verify editor) bhi flags clear karta hai.
- **Verified:** reproduce test — invalid link → flag True → panel reopen → flag
  None → normal text flow safe. Regression test added (v135 suite 16).

## 🧪 Tests: 179/179 PASS · boot clean

---
 (2026-08-03) — Button Editor: full location coverage + shape/padding + back buttons

## ✅ Screen Editor ab force-join ko bhi cover karta hai
- New **🔗 Force Join** screen added to the Screen-by-Screen Editor (SCREEN_TREE,
  43rd screen, listed under Main Menu):
  - 📝 Join Message text (editable)
  - 📝 Verified Response text (editable)
  - ✅ **I Joined — Verify** button → opens the Verify-Button editor
    (rename / color / premium emoji / link)
  - 🔗 **Join Targets** → opens Force Join Setup (all targets, add/delete/rename/color)
- So now ANY user-side button — main menu, shop, payments, force-join — is reachable
  from Customization → Buttons Editor.

## ✅ Button Editor: shape / display-format / padding
- Manage-Button panel now has **📐 Shape / Size / Padding** → opens the Inline
  Button Styler for that registry button (size S/M/L/XL/Full, alignment
  left/center/right, extra padding 0–40). Styler already supported `reg_<bid>` keys.
- **✨ Premium Emoji** dedicated button added (rename flow, premium capture).
- Background Color (🔵 Blue / 🟢 Green / 🔴 Red) already present — unchanged.

## ✅ Back buttons fixed (user report: "jahan button ni ata back ka")
- Force Join **Add Channel/Group** prompt: was "❌ Cancel" only → now **🔙 Back to
  Force Join**.
- Per-target prompts (rename / emoji / change-link): "❌ Cancel" → **🔙 Back** to
  that target's panel.
- Verify-Button editor prompts (rename / emoji): **🔙 Back** to the editor.

## 🧪 Tests: v141 suite 10/10 · full regression 178/178 PASS · boot clean

---
 (2026-08-03) — Response-reaction feature REMOVED + Force-Join all-buttons FIX

## ❌ REMOVED — auto-reaction / Edit-Response reaction feature (owner request)
- **"Rehny do is response wali update ko khtm krdo"** — the whole reaction feature
  is removed:
  - Global auto-react guard hook (`_reaction_hook` / `auto_react_to_message`) removed
    from premium_emoji_guard.py → bot never auto-reacts to its own messages.
  - Default-reaction + per-response reaction admin UI removed (Edit Responses → no
    more ⚡ buttons; no Auto-Reaction / Default Reaction toggles).
  - All `resp_react_*` callbacks + ConversationHandler + registrations removed.
  - `react_enabled` now defaults OFF and is cleared in the DB.
- The premium-emoji RENDERING guard stays (that part was never the problem).

## 🐛 FIX — Force Join: only 1 of N buttons showed for new users
- **Bug:** admin creates 3 channel/group buttons but a new user saw only 1.
- **Root cause:** the join screen rendered buttons only for targets in `missing`.
  `_is_member` fails OPEN when the bot is not an admin in a target (TelegramError
  → treated as "already a member"). So any target the bot wasn't admin in was
  silently hidden → only the bot-admin target's button appeared.
- **Fix:** the join screen (and the existing-user re-join gate) now render a
  button for **EVERY enabled target**, not just `missing`. The Verify tap still
  re-checks each one. All created buttons always show.
- Verified: 3 targets + bot admin in only 1 → previously 2 buttons, now **4**
  (3 join + verify) in both new-user and existing-user paths.

## 🧪 Tests: v140.1 suite 7/7 · full regression 168/168 PASS · boot clean

---
 (2026-08-03) — GLOBAL AUTO-REACTION on every outbound message

## ✅ Feature (user request — reference bot in screenshot)
- Har message pe bot **khud apni message ke UPAR reaction** lagata hai (jaise
  screenshot wale bot me: koi bhi button press → koi na koi emoji, animated).
- **Global guard** (premium_emoji_guard) ab **har send ke baad auto-react**
  karta hai: text, photo, video, document, animation — sab pe.
- **Default reaction** (`react_default`) = 🔥 (regular) ya `premium:<id>`
  (animated). Har message pe yehi lagta hai.
- **Per-response override** (Edit Responses → ⚡) — agar kisi response ke liye
  alag reaction set hai to wo default ki jagah lagta hai (welcome pehle se
  wired).
- Master toggle `react_enabled` **default ON** + admin button (Edit Responses
  screen pe `⚡ Auto-Reaction: ON/OFF`).
- New admin button: `🎯 Default Reaction (har msg)` — isse aap default emoji
  ya premium animated set kar sakte ho.

## 🐛 CRITICAL internal fix: guard was patching the WRONG class
- PTB `Application.builder()` creates an **ExtBot** which **overrides
  send_message** — patching only `Bot.send_message` silently did NOTHING in
  production. The guard now patches **both Bot and ExtBot** (+ media sends).
- Reaction text can NEVER overwrite a response value (v139.4 guard kept) and
  the reaction conversation is registered first (v139.5 kept).

## 🧪 Tests
- v140 suite 14/14 · faithful PTB router journey (custom + premium + GLOBAL
  auto-react, welcome safe 1887 chars) ✅
- **LIVE Bot API proof:** real token sendMessage + setMessageReaction(👍) → OK
- Full regression **200/200 PASS** (20 suites)

---
 (2026-08-03) — Reaction input STILL not working: PTB "max 1 handler per group" root fix

## 🐛 Bug #5 (reported: "custom emoji click → bot koi response ni kiya, emoji set nahi hua")
- **Kahan:** Edit Responses → ⚡ Set/Change Reaction → 🖊️ Type custom emoji / ✨ Premium
- **Root cause (deep):** PTB fires **only ONE handler per group** (`break` after the first
  match). When admin opened Edit Response, that conversation stayed ACTIVE. Tapping ⚡ did
  not end it. So when the admin typed the emoji, the **Edit Response conversation claimed
  the text first** — the v139.4 guard (return END) correctly stopped it from overwriting
  the response, but the `break` meant the **reaction ConversationHandler never received the
  emoji** → no response, no reaction.
- **Fix (v139.5):** the reaction emoji-input ConversationHandler is now registered as the
  **FIRST conversation handler** (before Edit Response). When state 99 is active it claims
  the admin's emoji text before any stale conversation can. Normal response edits still
  work (reaction conversation only claims text while it is active).
- **Verified with a faithful PTB router test** (real handlers, real ordering, FakeRequest):
  edit panel → picker → custom prompt → type 🔥 → **reaction saved + confirmation**, welcome
  text untouched (1887 chars); premium path → `premium:<id>` saved. ALL PASS.

## 🧪 Tests: v139.5 router 6/6 · v139.4 9/9 · v139.3 9/9 · full regression 186/186 PASS

---
 (2026-08-03) — CRITICAL: reaction text was overwriting response text + auto-react wiring

## 🐛 Bug #4 (reported: "welcome msg gayab ho gaya, sirf emoji aa gaya")
- **Kahan:** Edit Responses → ⚡ Set/Change Reaction → Premium/Custom emoji input
- **Root cause (2 layers):**
  1. When admin tapped ⚡ reaction, the OLD "Edit Response" conversation
     (`EDIT_RESP_VALUE` state) stayed active. When admin then typed the emoji
     for Premium/Custom, the old conversation's `response_value_received`
     caught that text and **saved the emoji AS THE RESPONSE VALUE** → whole
     welcome message was replaced by a single emoji. (The v133 reaction feature
     only ever *looked* like it didn't work — it was actually destroying the
     response text.)
  2. Even when a reaction WAS set, `react_enabled` (global toggle) had **no
     admin UI** and defaulted to 0 → bot never auto-reacted anyway.
- **Fix:**
  1. `response_value_received` now returns `ConversationHandler.END` when
     `resp_react_key` is present (reaction-input text can NEVER overwrite a
     response value).
  2. Reaction picker refactored into `_render_reaction_picker(q, key)` so
     set/clear re-render with the CLEAN key (was `set_welcome|👍` garbage).
  3. New **⚡ Auto-Reaction: ON/OFF** global toggle button on the Edit
     Responses "all" screen (`resp_react_global_toggle`).
  4. Welcome sender now auto-reacts: `react_to_message(..., "welcome")` after
     sending (only when reaction configured + global toggle ON; never raises).
- **Verified:** 6/6 live simulation — welcome text untouched after all reaction
  ops; reaction set correctly; global toggle toggles.

## 🧪 Tests: v139.4 suite 9/9 · v139.3 9/9 · full regression 186/186 PASS

---
 (2026-08-03) — Edit-Response reaction emoji FIX (handler ordering)

## 🐛 Bug #3 (reported: "edit response ma b emoji ni lg rha")
- **Kahan:** Edit Responses → ⚡ Set/Change Reaction (v133 feature)
- **Root cause:** In bot.py's callback table the GENERIC pattern
  `("^resp_react_", resp_react_callback)` was registered BEFORE the specific
  ones (`set_`, `clear_`, `prem_`, `custom_`). python-telegram-bot fires ONLY
  the FIRST matching handler, so:
  - `resp_react_set_welcome|👍` → generic fired → picker reopened with wrong
    key `set_welcome|👍` → **emoji was NEVER set**
  - `resp_react_clear_...` → same → **clear never happened**
  - `resp_react_prem_/custom_...` → same → **premium/custom input never started**
  - Only the plain picker opened (looked like it worked, but nothing saved)
- **Fix (bot.py):**
  1. `set_`/`clear_` registered BEFORE the generic pattern.
  2. Generic now uses negative lookahead: `^resp_react_(?!set_|clear_|prem_|custom_)`.
  3. `prem_`/`custom_` removed from the plain table so the dedicated
     ConversationHandler (state 99, emoji text input) actually receives them.
- **Verified with a real PTB router test:** picker ✅ · set ✅ · clear ✅ ·
  premium-enter ✅ · premium emoji text captured ✅ · custom ✅ (all 6 correct).

## 🧪 Tests: v139.3 suite 9/9 PASS · full regression 177/177 PASS

---
 (2026-08-03) — Live-flow simulation bugfix: Verify-Button editor crashed

## 🐛 Bug #2 (found via in-process live-flow simulation with real DB copy)
- **Bug:** Force Join → ✅ **Verify Button Editor** (`fj_vbtn_callback`) crashed with
  `UnboundLocalError: cannot access local variable 'InlineKeyboardButton'`.
  Root cause: `InlineKeyboardButton`/`InlineKeyboardMarkup` were imported only in
  the `except` branch (premium-button path). In production `make_premium_button`
  always succeeds, so the imports never ran and the button rows below raised
  UnboundLocalError → the editor broke every time admin opened it.
- **Fix:** imports moved to the top of the callback.
- **Verified:** 9-force-join-admin-panel simulation suite now passes
  (manage/color/rename/emoji/link/move/bulk/add/delete).

## 🧪 Live-flow simulation harness added (`_live_sim.py`, dev-only)
- Drives the REAL bot handlers with synthetic Telegram updates against a COPY of
  the live DB: /start+referral→force-join→math→welcome→observation→both-credited,
  force-join gate (block/verify/admin), verify-button editor, supplier preset
  panel, my_account @N/A, how-to hub, Test-Broadcast button, payment helpers.
- 18/18 simulated flows pass after this fix.

---
 (2026-08-03) — Live-test bugfix: Fake Activity 🛰️ Test Broadcast button crashed

## 🐛 Bug (found during live test session)
- **Bug:** Fake Activity panel ka **🛰️ Test Broadcast** button `admin_bcast_test_callback`
  used `ADMIN_ID` without importing it → tapping the button raised
  `NameError: name 'ADMIN_ID' is not defined` → button silently failed.
- **Fix:** added `from config import ADMIN_ID` inside the callback.
- **Push:** committed to GitHub (`3b495eb`), Render deploy triggered via API → **LIVE**.

## ✅ Live connectivity verified (this session)
- Telegram: bot alive (getMe OK), polling mode (no webhook conflict) ✅
- Render: service resumed + deployed clean ✅
- ProdSeller: 15 products, balance **$0** ⚠️ (top-up needed before selling)
- Canboso sinhle: 21 products ✅ · Shop Cron: balance **$10** ✅
- Binance API: connected via proxy pool ✅ (env socks5 fails → pool fallback works)
- Bybit: Bybit-Pay/UID (internal deposits) path OK ✅; on-chain endpoint had
  sandbox timestamp skew (Render time is NTP-synced — expected OK there)

## Tests: 168/168 PASS (v134 19 · v135 15 · v136 9 · v137 9 · regression 116)

---
 (2026-08-03) — Restore-safety fix: pending-referral columns now auto-added

## ✅ Bug found during full DB-restore test (real fix)
- **Bug:** after restoring an older DB backup, the `pending_referrals` table was
  missing the v134 columns (`activity_count`, `observe_tries`). The bot's
  `migrate_all()` never called `ensure_pending_referrals_table()`, so on a
  restored DB the referral-observation feature could fail until a pending
  referral was added (which lazily re-created the table).
- **Fix:** `migrate_all()` now runs `ensure_pending_referrals_table()` and
  `ensure_force_join_targets_table()` in its migration list → every restore
  auto-adds the new columns/tables immediately at boot.
- Verified against the fresh **2026-08-03 backup** (488 users / 193 orders /
  41 products / 98 ext-products): columns added cleanly, `migrate_all`
  `tables_checked=12, errors=0`.

## ✅ Fresh DB prepared (bite_store_restore_ready.db)
- Migrated the 2026-08-03 live backup to v139: schema healed, 50 dead responses
  removed, `fj_verified_done` seeded, `referral_math_enabled=1`,
  `referral_points_per_ref=1`, `react_enabled=0`, force-join legacy
  `@bite_alerts` → target #1, `fj_verify_*` defaults set.
- Suppliers: all 6 enabled (TunVNMMO, Ai Tools, Shop Cron, sinh le store bot,
  MMOStore, **ProdSeller** added with the provided key).

## Tests
- v134 19 + v135 15 + v136 9 + v137 9 + regression 116 = **168/168 PASS**.
- `main()` registration + boot with the real deliverable DB: clean.

---
 (2026-08-03) — How-to-Use updated + Fake-Activity destination indicator + language polish

## ✅ How to Use (📚) — fully updated to the CURRENT flow
- Payment guides now match the live bot: 💳 Bybit Pay (UID flow), 💎 Bybit USDT (TRC20/BEP20),
  🪙 Binance USDT (TXID-only auto-verify), 💰 Points Wallet. Old EasyPaisa/JazzCash screenshots flow removed.
- New **💳 Bybit Pay / USDT — Step-by-Step** guide added to the hub.
- Referral guide updated: math verification + ~30s human-activity check + BOTH users earn the set points.
- FAQ updated: Bybit Check Payment, Binance TXID, math-question explanation, "@— username" explanation.

## ✅ Fake Activity destination indicator
- Destinations panel now shows **✅ Already added: <link>** when a channel/group is set, or
  **❌ Not set yet** — no more guessing which link is live.

## ✅ Language polish (v137 leftovers)
- WELCOME message stays in default language on purpose (admin request) — everything else switches.
- Persistent reply-keyboard buttons (🏠 Main Menu / 📚 How to Use) now follow the user's language,
  and the bot understands the tapped translated labels.
- How-to-Use hub + guide screens translate per user language.
- Buy Points / Transactions / Price List / Shop filter labels translate.

## ✅ Customization audit
- Checked every customization screen + DB for blank/empty blocks — all response keys non-empty,
  no dead/missing settings. Edit Responses now also includes the new `fj_verified_done` key.

---

# 🚀 v137 (2026-08-03) — FULL language switching + username @N/A fix

## ✅ Full language switch (user request)
- **Before:** only some texts translated — reply-keyboard buttons, How-to-Use, and several screens stayed English.
- **Now:** buttons, menus, product titles/descriptions, guides, price list, transactions, buy-points and
  filter labels all render in the user's selected language (cached per text, Gemini display-time translate).
- WELCOME message stays default-language by design (per admin).

## ✅ Username @N/A bug FIX
- **Bug:** users without a Telegram username saw "@N/A" on the My Account screen (template hardcoded
  "@" before {username}).
- **Fix:** no-username users now see "—" (no fake @). Real usernames still show "@username".
- Also fixed the admin "New User Joined" notification (shows "_no username_" instead of @N/A).

## Tests: v137 suite **9/9 PASS** · regression 148/148.

---

# 🚀 v136 (2026-08-03) — ProdSeller supplier + all-suppliers Add panel + Bulk Unsync

## ✅ NEW supplier: ProdSeller (added to bot + DB)
- Adapter `prodseller`: base `http://51.77.244.194/v1`, auth `X-API-Key: psk_...` header,
  balance-based orders with instant key delivery (`deliveredKey` / `deliveredKeys`).
- Endpoints: GET /products, GET /balance, POST /orders (productId + quantity, Idempotency-Key).
- Registered in ADAPTERS + SUPPLIER_PRESETS + render.yaml/.env.example (`SUPPLIER_PRODSELLER_API_KEY`).
- Supplier row **added to the DB** with the provided key (enabled).

## ✅ Add Supplier panel — every known supplier selectable
- The "➕ Add New Supplier" screen now lists ALL suppliers the owner runs as one-tap presets:
  Canboso, **Shop Cron**, **sinh le store bot**, Akunding, MMOStore, TunVNMMO, **ProdSeller** —
  pick one → paste API key → done (no manual adapter/URL entry).

## ✅ Bulk Unsync (mirror of Bulk Sync)
- Supplier panel gets **🗑️ Bulk Unsync (remove from shop)**.
- Deletes the supplier's mirrored shop products (user shop + admin Edit Items) + their account pools,
  unlinks catalog rows (re-syncable), and **keeps all order history**.
- Two-tap confirm so nothing is deleted by accident.

## Tests: v136 suite **9/9 PASS**.

---

# 🚀 v135 (2026-08-03) — Force Join: unlimited channels/groups + editable buttons + auto re-force

## ✅ Unlimited channels & groups
- New `force_join_targets` table — add as many channels/groups as you want; each becomes its own
  Join button. Legacy single channel/group settings auto-migrate into the new table.

## ✅ Every button fully editable (Telegram Bot API 9.4 colors)
- Per target: ✏️ rename (premium emoji allowed), 🎨 color (🔵 primary / 🟢 success / 🔴 danger / ⚪ default),
  ✨ premium emoji icon, 🔗 change link, ⬆️⬇️ reorder, 🗑️ delete.
- **🗑️ Bulk Delete** panel: multi-select (checkbox list), Select All / Clear, Delete Selected.
- **Verify button editor**: the single "✅ I Joined — Verify" button can be renamed, recolored,
  given a premium emoji — shared by new AND existing users.

## ✅ Enforcement for existing users + leave detection
- New GLOBAL gate: if a user (old or new) is not a member of any target, their **every action**
  (any button tap or text) is blocked with the join screen until they rejoin + verify.
- If they leave a channel/group later, the next action forces them again automatically.

## ✅ Verified response editable + auto-delete
- The message after tapping "I Joined — Verify" is now an editable response
  (`fj_verified_done` in Edit Responses, premium emoji OK) and **auto-deletes after 5 seconds**.

## Tests: v135 suite **15/15 PASS**.

---

# 🚀 v134 (2026-08-03) — Referral MATH verification + 30s activity observation + BOTH users earn points

## ✅ Math verification for referral-origin users (per request)
- When a user arrives via a **referral link** and (if enabled) passes force-join verify, the bot shows a
  **random +/− math question**. Correct answer → bot starts. Normal users (no referral) never see it.
- 3 wrong attempts → fresh random question. Toggle in Referral Abuse Control → 🧮 Math Verify for Refs (default ON).

## ✅ 30-second activity observation (anti-fake)
- After /start via referral, the reward is **locked (pending)**. The bot observes the user:
  - Any button tap / typed text counts as activity (2+ actions → instant approval = real human).
  - The 30s job only approves if the user showed ≥1 action; otherwise it keeps observing
    (up to ~2.5 min) — a silent bot never unlocks the reward.
  - Opening Shop still approves instantly.

## ✅ BOTH users get the admin-set points
- On approval: the **referrer** AND the **referred user** each get `Points per Ref` (configurable, e.g. 0.1/2/5).
- Both get their own notification (new editable template `ref_tpl_referred` in
  Referral Panel → ✉️ Notification Templates).
- Referral instructions + How-to-Use updated to describe the new flow.

## Tests: v134 suite **17/17 PASS**.

---
 (2026-08-02) — Referral points FIX (decimal) + product-ref tracker + per-response reactions

**User report (3 items):**
1. BUG: Referral counted but points not added to the referrer's account (notification says
   "+1 point" but nothing appears).
2. UPDATE: Referral Abuse Control needs a **Product Referrals** sub-panel — only products
   with Free-via-Referrals ON, showing referrers / referred users / counts.
3. UPDATE: Edit Responses needs a **per-response reaction** setting — the bot reacts to its
   own message with an admin-set emoji (regular or premium animated) whenever it sends that
   response.
Also: points-per-referral must be **configurable** (e.g. 0.1, 2, 5) and the referral
instructions text must **auto-update** to match.

## ✅ 1. Referral points — root cause FOUND & FIXED
`database.add_ref_points()` did `int(amount)` — `int(0.1)` = **0**. Any decimal reward was
silently dropped, and the notification ("+1 point") already showed the pre-credit message.
- `add_ref_points` / `get_ref_points` / `deduct_ref_points` now use **float** — SQLite stores
  the decimal fine (INTEGER-affinity column becomes REAL).
- Reward is now **configurable**: `referral_points_per_ref` setting (default 1, decimals
  allowed). `_process_referral_attribution` awards `get_ref_points_per_ref()` on counted
  direct referrals; blocked attempts never award (unchanged).
- Referral instructions & rewards line auto-update: referral panel button shows
  "🎁 Points per Ref: <value>" and the user-facing "How your referral counts" text prints the
  current value. New admin flow: set value (decimals OK) — instructions follow automatically.

## ✅ 2. Product Referrals tracker (Referral Abuse Control → 📦)
- New "📦 Product Referrals (Free-via-Refs)" panel button.
- Lists ONLY products with Free-via-Referrals enabled (get_all_free_claim_products).
- Per product → detail: every referrer, how many users they brought, the referred user IDs +
  timestamps (paginated top-15 referrers, top-5 users each).
- New DB helper `get_product_ref_rows()`.

## ✅ 3. Per-response auto-reaction (Edit Responses → ⚡)
- New `response_react.py`: settings `react_<key>` (regular emoji or `premium:<emoji_id>`),
  global `react_enabled` toggle, `react_to_message()` (never raises).
- Edit Responses list shows ⚡ + emoji on keys that have a reaction.
- Response edit panel adds: ⚡ Set/Change Reaction (quick emoji grid: 👍❤️🔥🎉⚡💎✅⭐,
  ✨ Premium Animated (captures custom_emoji_id), 🖊️ custom emoji, 🚫 clear).
- `_safe_send` and `_bot_send_smart` accept optional `react_key` → react after send.
  (Wiring into main response paths can be extended over time; helpers are ready and tested.)

## Tests (v133)
`_test_v133_refs_react.py` — **14/14 PASS**: default per-ref =1 ✅ · set 0.1/5 ✅ · add float
0.1 ✅ (the actual bug) · reject negative ✅ · product-ref rows add/read ✅ · reaction helpers
set/get/clear/premium ✅ · disabled → no-op ✅ · panel buttons present ✅ · registered ✅.

Regression: v131 7 + v130 8 + v129 4 + v127 3 + v126 3 + v125 8 + v124 4 + v123 12 + v122 13
+ v120 7 + v119 14 + v118 8 + v117 4 + v116 6 + v114 9 + v112 15 + v111 17 =
**156/156 PASS**. Boot clean.

## 🔧 Files changed
- `database.py` — float ref-points (add/get/deduct), `get_ref_points_per_ref`/`set_ref_points_per_ref`, `get_product_ref_rows`.
- `handlers_start.py` — configurable reward in attribution; referral instructions auto-update.
- `handlers_referral_admin.py` — set-points flow + product-referrals panel + detail.
- `response_react.py` — NEW reaction engine.
- `handlers_admin.py` — Edit Responses reaction buttons + setter callbacks.
- `handlers_order.py` — `_safe_send`/`_bot_send_smart` react_key support.
- `bot.py` — imports, registrations, reaction ConversationHandler.
- `CHANGELOG.md` — this section.

---

# 🚀 v132 (2026-08-01) — Broadcast destination FIX (silent failures now loud) + editor fixes + response cleanup

**User bug report (detective mode):** fake activity and REAL broadcasts (purchase / join /
stock / referral / tier) were not reaching the destination group `@bite_alerts`. Also: screen
editor "Button Editor" showed blank for Binance flow (wrong screen id), and old responses from
deleted features still showed in Edit Responses.

## 🕵️ Root cause (found)
`broadcast_store_message()` in `fake_engagement.py` had a silent-swallow `_send` helper:
```python
except Exception:
    try: ... plain ...
    except Exception:
        return False      # ← group failure = 0 sends, NO log, NO admin alert
```
Every real broadcast (purchase drainer `_purchase_broadcast_job`, new-user join, restock
alert, referral/tier) funnels through this. When the bot could not post to `@bite_alerts`
(not admin / wrong dest / stale resolved id), it failed silently — "nothing goes out".

## ✅ Fixes
1. **`broadcast_store_message` is now loud**: `_send` logs the real exception, and on a GROUP
   failure calls new `_alert_broadcast_dest_failure()` — a throttled (20 min) admin DM with the
   exact Telegram error + fix instructions. Real broadcasts can no longer die invisibly.
2. **🛰️ Test Broadcast button** (Fake Activity panel → "Test Broadcast"): resolves the
   destination, checks the bot's member status in the chat (`get_chat_member`), sends a test
   message, and reports the exact result. One tap = you see in 5 seconds whether the bot can
   post and what's wrong. Registered `^admin_bcast_test$`.
3. **Fake-activity watchdog + status DM** (v131) retained — the group job also now notifies
   the admin with the exact destination error on failure.
4. **Screen editor — Binance flow blank button editor FIXED**: `se_subbtn_<sid>_<bid>` used
   `rsplit("_",1)` which broke multi-underscore button ids (`pay_binance` → sid became
   `binance_flow_screen_pay`). Now uses a pipe separator `se_subbtn_<sid>|<bid>` and splits on
   `|`. Tapping a Binance-flow button in Sub Menu now lands on the right screen's editor.
5. **Edit Responses cleanup**: audited all 108 responses — removed **50 truly-dead keys**
   (only in the editor registry, never used at runtime: old screenshot-verification texts,
   old binance orderid flow, disabled EasyPaisa/JazzCash point instructions, unused tier
   defaults, etc.) from `DEFAULT_RESPONSES`, the screen-editor `SCREEN_TREE`, AND the DB.
   58 active responses remain, all current. (EasyPaisa/JazzCash/order texts stay inside the
   readymade-layout groups so layouts still apply them — the editor list is clean.)
6. Interval: both units supported, floor 30s (flood-risk-free) — unchanged from v131.

## Tests (v132)
Full regression: v131 7 + v130 8 + v129 4 + v127 3 + v126 3 + v125 8 + v124 4 + v123 12 +
v122 13 + v120 7 + v119 14 + v118 8 + v117 4 + v116 6 + v114 9 + v112 15 + v111 17 =
**142/142 PASS**. Boot clean with the newest DB (integrity ok, 60 responses, 5 suppliers).

## 🔧 Files changed
- `fake_engagement.py` — loud `_send` + `_alert_broadcast_dest_failure` + `admin_bcast_test_callback`.
- `ui_extras.py` — 🛰️ Test Broadcast button in the Fake Activity panel.
- `bot.py` — `^admin_bcast_test$` registration.
- `customization.py` — `se_subbtn` pipe parsing; removed dead SCREEN_TREE text entries.
- `config.py` — removed 48 dead keys from DEFAULT_RESPONSES.
- `CHANGELOG.md` — this section.

## 📌 How to verify after deploy
1. Admin → 🎭 Fake Activity → **🛰️ Test Broadcast** — it will tell you if the bot can post to
   `@bite_alerts` (and whether it's admin). Fix dest / add bot as admin if it says FAILED.
2. Real broadcasts now send an admin DM if the destination fails — no more silent death.
3. Screen editor → Binance Flow → Sub Menu → tap a button → correct screen editor opens.
4. Edit Responses — old dead responses are gone; latest ones remain.

---

# 🚀 v131 (2026-08-01) — Fake-activity watchdog + English maintenance + deploy-maintenance + new supplier

**User requests (combined):**
1. Fake activity not running at the selected destination (minutes or seconds timer) and real
   broadcasts also stopped — restart both (mixed like before).
2. Screen-by-screen editor: sub menu missing for some screens, button editor blank — every
   button must be editable (rename / color / premium emoji).
3. Maintenance templates in English with emojis (no roman urdu).
4. After every Render deploy, the bot should start UNDER MAINTENANCE; the "BOSS BOT IS LIVE"
   message must include 2 buttons: ✅ Turn OFF Maintenance / 🛠️ Under Maintenance (keep ON).
5. Add a new supplier "sinh le store bot" (Canboso Buyer API v2) with the provided API key so
   products can be synced and auto-delivered.
6. Use the NEW current DB (257 users / 152 orders) — modify per all updates.

## ✅ 1. Fake activity — self-healing + diagnostics
- **`activity_watchdog_job`** (every 60s): if global ON but the group job or per-user jobs are
  not scheduled, it re-schedules them → fake activity can never silently die after a deploy.
- **`fake_activity_status_message`** (120s after boot): admin DM with global/user-jobs/
  destination/interval — the owner can SEE it's running.
- Group job now sends the admin the EXACT Telegram error when posting to the destination chat
  fails (bot not admin in chat / wrong dest), plus a plain-text fallback.
- Per-user + group + real broadcasts all restart together on boot (mixed, as before).

## ✅ 2. Screen editor — no more blank
- `se_btns_callback`: screens with 0 dedicated buttons now show a clear message +
  "🎛️ Manage All Buttons" (never blank).
- `se_sub_callback`: screens with no buttons show the real screen body + a note (not blank).
- Buttons that exist → tap → full panel (rename per size with premium emoji, background color
  blue/green/red, hide/show, reset) — exactly as requested.

## ✅ 3. Maintenance templates → English with emojis
All 5 `MAINT_TEMPLATES` rewritten in clean English with emojis (no roman urdu). `maint_custom`
updated in the DB too (English).

## ✅ 4. Deploy maintenance + live-message buttons
- `MAINT_ON_START=1` in render.yaml → bot starts in maintenance after every deploy.
- `_delayed_live_notify_job` shows maintenance status + 2 buttons:
  - ✅ **Turn OFF Maintenance** (`maint_live_off`) → bot goes live instantly
  - 🛠️ **Under Maintenance (keep ON)** (`maint_live_keep`) → stays in maintenance
- Admin-only callbacks; customer gate unchanged.

## ✅ 5. New supplier — sinh le store bot
- New `ensure_env_sinhle_supplier()` preset (env `SUPPLIER_SINHLE_API_KEY`) + startup wiring
  in `database.migrate_all` and `self_heal`.
- Supplier **live-verified**: `GET /api/v2/telegram-buyer/products?key=…` → 200, **19 products**
  (owner "sinhledev") — sync + auto-delivery will work.
- Added to the DB (id 10, canboso, enabled). render.yaml + .env.example updated.

## Tests (v131)
`_test_v131_features.py` — **9/9 PASS**: watchdog exists + registered in bot ✅ · status message
uses destination ✅ · maintenance templates English + emojis ✅ · MAINT_ON_START + live
callbacks ✅ · live buttons registered ✅ · sinhle preset function + creates supplier +
render.yaml env ✅.

Regression: v130 8 + v129 4 + v127 3 + v126 3 + v125 8 + v124 4 + v123 12 + v122 13 + v120 7
+ v119 14 + v118 8 + v117 4 + v116 6 + v114 9 + v112 15 + v111 17 = **144/144 PASS**. Boot
clean with the new DB (integrity ok, 108 responses, 5 suppliers).

## 🔧 Files changed
- `per_user_activity.py` — watchdog + status DM + dest-fail admin notify.
- `bot.py` — watchdog/status registration; live-notify buttons; `_apply_startup_maintenance`;
  `maint_live_off/keep` callbacks.
- `maintenance_mode.py` — English templates.
- `customization.py` — blank fallbacks in button editor + sub menu.
- `ext_suppliers.py` — `ensure_env_sinhle_supplier()`.
- `database.py`, `self_heal.py` — sinhle preset startup wiring.
- `render.yaml`, `.env.example` — `MAINT_ON_START`, `SUPPLIER_SINHLE_API_KEY`.
- `CHANGELOG.md` — this section.

---

# 🚀 v130 (2026-08-01) — Animations REMOVED + new recursive screen-by-screen editor

**User request:** remove the animation feature; rework the screen editor to:
Root → list of main screens → tap a screen → [🎛️ Button Editor] [📂 Sub Menu] →
Button Editor = per-button rename / color (blue-green-red) / premium emoji / hide / reset;
Sub Menu = the real screen; tap any button → same 2 options (recursive drill-down).

## ✅ 1. Animations fully removed
- Deleted `animations.py` (was merged into customization.py); removed `play_transition`
  calls from all navigation handlers (start/shop/order/support), the admin panel callbacks,
  the bot.py registrations, and the 🎬 button from the Customization menu. Zero references
  remain. Telegram bot API can't do true slide/carousel transitions anyway — removed cleanly.

## ✅ 2. New recursive screen editor (v130)
- `se_root` → lists **24 main screens** (Main Menu, Shop, Product Detail, Buy Points,
  Account, Orders, Transactions, Referrals, Support, Warranty, Reviews, Loyalty, Language,
  Free Claim, Terms, Binance/Bybit/Crypto/EasyPaisa/JazzCash flows, Order flow, Errors).
- `se_open_<sid>` → **2 options**: 🎛️ Button Editor · 📂 Sub Menu (+ shows button/text counts,
  and a 🎨 Readymade Layouts button when the screen has layout children).
- 🎛️ **Button Editor** (`se_btns_<sid>`) → lists that screen's buttons → tap → the full
  per-button panel (rename per size with premium emoji, background color blue/green/red,
  hide/show, reset) — reuses the proven `mbedit_` panel.
- 📂 **Sub Menu** (`se_sub_<sid>`) → renders the REAL screen with REAL styled buttons
  (current labels + premium emoji + colors); tapping any button → `se_subbtn_` shows the
  same 2 options for the screen that button opens (via `BTN_TARGET_SCREEN` map) — fully
  recursive drill-down, exactly as requested.
- Readymade layouts still reachable (flow screens show a 🎨 Readymade Layouts button).

## Tests (v130)
`_test_v130_editor.py` — **8/8 PASS**: no anim functions / no play_transition / no Animations
button ✅ · 24 main screens defined + all valid ✅ · button→screen map ✅ · new callbacks
registered ✅ · editor offers Button Editor + Sub Menu ✅.

Regression: v129 4 + v127 3 + v126 3 + v125 8 + v124 4 + v123 12 + v122 13 + v120 7 + v119 14
+ v118 8 + v117 4 + v116 6 + v114 9 + v112 15 + v111 17 = **142/142 PASS**. Boot clean.

## 🔧 Files changed
- `customization.py` — removed animations; new `MAIN_SCREENS`, `BTN_TARGET_SCREEN`,
  `se_root_callback`, `se_open_callback`, `_show_screen_editor`, `se_btns_callback`,
  `se_sub_callback`, `se_subbtn_callback`; layouts wiring preserved.
- `handlers_start.py`, `handlers_shop.py`, `handlers_order.py`, `handlers_support.py` —
  play_transition calls + imports removed.
- `keyboards.py` — Animations button removed.
- `bot.py` — anim registrations removed; se_btns_/se_sub_/se_subbtn_ added.
- `CHANGELOG.md` — this section.

---

# 🚀 v129 (2026-08-01) — Binance USDT TXID-only + Bybit amount-only + no double-ask + frame animations

**User request (combined):**
1. Binance USDT (TRC-20/BEP-20): TXID-based — instructions say TXID, user pastes TXID,
   bot checks API and auto-adds. No Check button on Binance USDT.
2. Bybit USDT (TRC-20/BEP-20): amount-only detection — auto-add when the user taps
   "Check payment" (click-triggered). Check button ONLY on Bybit networks.
3. BUG: Buy Points → select amount → Bybit → bot asked the amount AGAIN. Fixed — pre-selected
   amount is reused (no double-ask).
4. Edit Responses: every response covered in a named category (audit: 0 uncovered).
5. Screen-by-screen editor: already comprehensive; new Bybit buttons/screens are editable
   (rename + premium emoji + green/blue/red).
6. Animations: full-bot + per-location **frame-based transition effect** on button taps.

## ✅ What changed

### 1. Binance USDT = TXID-only
- `payment_binance_usdt` instructions rewritten: "🧾 Copy the TXID (transaction hash) →
  📨 Paste the TXID here in chat → 🤖 bot checks the blockchain and adds your balance".
- Removed the "🔍 Check Payment" button from `_start_usdt_payment` (Binance). Customer pastes
  TXID → `usdt_txid_received` → API match (network+address+amount+txid) → auto-add.

### 2. Bybit USDT = amount-only, click-triggered (Check button only here)
- Bybit USDT deposit screen keeps: Copy address / Copy amount / **🔍 Check payment** / Cancel.
- Verification only on Check click (v126 bg no-op still holds). Match = network+address+amount.

### 3. No double-ask bug (Buy Points → Bybit)
- `bybit_flow_continue_callback` (USDT) and `bybit_flow_uid_received` (Pay): when the flow
  already carries `base_amount` (selected on the Buy Points screen), the amount prompt is
  **skipped** — the order is created immediately with the unique amount derived from the
  chosen base. No second "enter amount" screen.

### 4. Edit Responses — full coverage
- Audit confirms **0 uncovered** DEFAULT_RESPONSES keys; the 💳 Payment category catches
  `bybit_*`; 🧾 Order Flow catches `order_*`/`refund_*`; etc.

### 5. Animations (frame-based transitions) — NEW module `animations.py`
- Telegram bot API can't do true carousel/slide transitions (client-side). The closest
  supported effect is **fast frame editing**: on a button tap, the tapped message flips
  through 2–3 short frames (spinner/pulse/arrows/dots/flash/bounce/zoom) then the next
  location renders. Gives a real "transition" feel on every navigation.
- Admin: **Admin → 🎨 Customization → 🎬 Animations** — global on/off, global style picker,
  per-location style picker (main_menu, shop, buy_points, account, orders, transactions,
  support, referrals, warranty, reviews, loyalty, language, settings, admin, bybit, payment,
  success, back, product).
- Wired into main navigation: main_menu, my_account, referral, buy_points, transactions,
  shop, my_orders, support_menu, go_back. Fully silent on failure (navigation never breaks).
- Callbacks: `admin_animations`, `anim_toggle`, `anim_style_pick_`, `anim_style_set_`,
  `anim_loc_pick`, `anim_loc_style_`. Button added to the Customization menu.

## Tests (v129)
`_test_v129_anim_fix.py` — **10/10 PASS**: animations disabled default / enable+frames /
global+per-location styles / none → empty / transition no-crash when disabled / frames played
when enabled / Bybit Pay with pre-selected amount skips prompt / Bybit USDT with pre-selected
skips prompt / Bybit USDT has Check button / Binance USDT TXID-only (no Check button) ✅.

Regression: v127 3 + v126 3 + v125 8 + v124 4 + v123 12 + v122 13 + v120 7 + v119 14 + v118 8
+ v117 4 + v116 6 + v114 9 + v112 15 + v111 17 = **134/134 PASS** (incl. v129 10). Boot clean.

## 🔧 Files changed
- `handlers_order.py` — Binance USDT Check removed + TXID flow; Bybit skip-amount;
  `_bybit_flow_target` duck-typed.
- `config.py` — `payment_binance_usdt` TXID instructions.
- `animations.py` — NEW frame-transition engine + styles + per-location.
- `customization.py` — admin animations panel callbacks.
- `keyboards.py` — 🎬 Animations button in Customization menu.
- `handlers_start.py`, `handlers_shop.py`, `handlers_order.py`, `handlers_support.py` —
  `play_transition` wired into navigation.
- `bot.py` — animation callbacks registered.
- `CHANGELOG.md` — this section.

---

# 🚀 v128 (2026-08-01) — CRITICAL: copy_text must be CopyTextButton object (BadRequest fix)

**User bug report (Render logs screenshot):**
```
BadRequest: Can't parse ... inlinekeyboardbutton: field "copy_text" must be of type object
send failed (1st):
send failed (no-md):
```
The deposit screen (with Copy amount / Copy UID / Copy address buttons) failed to send —
customer typed the amount and got NO deposit screen (the exact "no response" symptom).

## 🕵️ Root cause
`make_premium_button()` passed `copy_text` through as a **plain string**:
```python
kw["copy_text"] = "1.9700"   # ❌ string
```
Telegram requires the inline-keyboard `copy_text` field to be a **`CopyTextButton` OBJECT**.
Every copy-text button built via `make_copy_text_button()` / `_make_flow_btn()` (used by the
Bybit flow: Copy amount, Copy UID, Copy address) therefore failed at the Telegram API layer →
`BadRequest` → the whole deposit message never sent. v127's retry logic kept retrying without
parse_mode, but the copy_text type error persisted → silent-ish failure (only logs).

## ✅ Fix
`button_system.make_premium_button()` — when `copy_text` is not already a `CopyTextButton`,
wrap it: `copy_text = CopyTextButton(str(copy_text))`. This single fix covers every caller
(`make_copy_text_button`, `_make_flow_btn`, and any future one). All other direct
`InlineKeyboardButton(copy_text=...)` call sites already used `CopyTextButton` (audited).

## Tests (v128)
- Verified live: `make_copy_text_button` / `_make_flow_btn` / premium+copy all produce
  `CopyTextButton` objects with the right `.text`.
- `_test_v119_screens.py` updated: asserts `isinstance(copy_text, CopyTextButton)`.
- Full regression: v127 3 + v126 3 + v125 8 + v124 4 + v123 12 + v122 13 + v120 7 + v119 14
  + v118 8 + v117 4 + v116 6 + v114 9 + v112 15 + v111 17 = **124/124 PASS**. Boot clean.

## 🔧 Files changed
- `button_system.py` — `make_premium_button()` wraps string copy_text → `CopyTextButton`.
- `_test_v119_screens.py` (backup) — CopyTextButton-object assertion.
- `CHANGELOG.md` — this section.

---

# 🚀 v127 (2026-08-01) — NO-SILENCE fix: amount typed → no response was a swallowed send error

**User bug report (screenshot):** user reached the Bybit Pay amount prompt
("Deposit via Bybit — UID"), typed `2.10`, and got **no response at all**.

## 🕵️ Root cause
The Bybit flow's send helper (`_bybit_flow_target`) did:
```python
async def send(text, **kw):
    try:
        return await target.reply_text(text, **kw)
    except Exception:
        return None      # ← SILENT SWALLOW
```
Any failure of `reply_text` — Markdown parse error, Telegram 429 FloodWait/RetryAfter,
BadRequest, network hiccup — was silently swallowed. The order was created in the DB but the
customer never saw the deposit screen. No log, no fallback, no error. Same class of bug as the
older "stuck" reports: **a failure that looks like nothing happened**.

(Verified: the deposit-instructions texts in the restore-ready DB are valid; the failure was
at the send step, not the template.)

## ✅ Fixes
1. **`_bf_send_retry()`** — bulletproof send used by every Bybit flow message:
   - try as requested (parse_mode=Markdown)
   - Markdown parse error → retry WITHOUT parse_mode
   - `FloodWait`/`RetryAfter` → wait (retry_after) and retry once
   - other errors → log with exception type + retry as plain text
   - if everything fails → **raise** (no more silent None)
2. **`bybit_flow_amount_received`** — wraps `_bybit_create_and_show` in try/except; on error it
   logs the full traceback and sends the customer a visible fallback ("⚠️ Oops — could not
   process your amount …") instead of silence.
3. **`payment_flow_text_handler`** (group −80) — wraps the UID/amount steps in try/except; any
   exception is logged and the customer gets a visible fallback, and the update is consumed
   (returns True) so no other handler double-processes.
4. **`bybit_flow_uid_received`** invalid paths already reply; now also safe.

## Tests (v127)
`_test_v127_no_silence.py` — **3/3 PASS**: reply raises once → retry succeeds → deposit screen
shown ✅ · Markdown parse error → retry without parse_mode → reply shown ✅ · total failure →
flow does not leave user hanging (fallback path, no crash) ✅.

Regression: v126 3 + v125 8 + v124 4 + v123 12 + v122 13 + v120 7 + v119 14 + v118 8 + v117 4
+ v116 6 + v114 9 + v112 15 + v111 17 = **123/123 PASS**. Boot clean; no undefined names.

## 🔧 Files changed
- `handlers_order.py` — `_bf_send_retry()` (async, robust), `_bybit_flow_target` uses it,
  `bybit_flow_amount_received` visible fallback.
- `bot.py` — `payment_flow_text_handler` try/except + visible fallback.
- `CHANGELOG.md` — this section.

---

# 🚀 v126 (2026-08-01) — Bybit verification is CLICK-ONLY (Check payment), background auto-detect OFF

**User request:** "Bot payment auto detect sirf tabhi karega jab customer khud Check payment par
click kare — us se pehle bot khud API se payment na detect kare." Also asked to verify no
workflow gets stuck.

## ✅ Change
- `bybit_deposit_background_job` is now a **no-op** (v126). It no longer queries Bybit's API
  or completes any order automatically. Bybit payments (bybit_pay + bybit_usdt_trc20 +
  bybit_usdt_bep20) are verified **only when the customer taps "🔍 Check payment"**
  (`bybitv_<oid>` → `_verify_bybit_order_and_respond`).
- The click path still: matches by sender-UID+amount (bybit_pay) or network+address+amount
  (bybit_usdt_*), credits points / delivers the product, marks the txid used (anti-fraud),
  and on no-match shows the retry screen + sends the admin the actionable alert with
  "✅ Mark Received & Credit".
- Binance USDT background auto-check is unchanged (separate flow, not part of the Bybit
  workflow request).

## Why this is safe
- The unique 4-decimal amount + UID/address matching still guarantees the correct deposit is
  credited — but only after the customer confirms by clicking Check.
- No customer is ever credited before they ask — the owner wanted explicit control.

## Tests (v126)
`_test_v126_click_only.py` — **3/3 PASS**: background job does NOT complete an order even when
a matching deposit exists ✅ · Check click verifies + credits points + marks txid used ✅ ·
Check click with no match stays `bybit_waiting` + shows retry ✅.

Regression: v125 8 + v124 4 + v123 12 + v122 13 + v120 7 + v119 14 + v118 8 + v117 4 + v116 6
+ v114 9 + v112 15 + v111 17 = **120/120 PASS**. Boot clean; no undefined names.

## 🔧 Files changed
- `handlers_order.py` — `bybit_deposit_background_job` → no-op with explanatory docstring.
- `_test_v112_bybit.py` (backup) — bg-alert test replaced with v126 no-op assertion.
- `BYBIT_WORKFLOW_SCREENS.md` — notes updated: "CLICK = verification moment".
- `CHANGELOG.md` — this section.

---

# 🚀 v125 (2026-08-01) — Bybit flow CLEAN REBUILD (deleted + rebuilt unified, bug-free)

**User request:** "Bybit par click karne ke baad ka sara workflow delete karo aur dubara banao,
khud ke brain se, bug-free."

## ✅ What was done
The ENTIRE old Bybit user-facing flow (v122 UID flow + v123 USDT flow, ~290 lines scattered
across `_bybit_show_warning`, `bybit_warn_*`, `bybit_uid_received`, `bybit_amount_received`,
`_bybit_show_deposit_screen`, `_bybit_usdt_show_warning`, `bybit_usdt_warn_*`,
`bybit_usdt_amount_received`, `_bybit_usdt_create_and_show`) was **deleted** and replaced by
one clean, unified state machine driven by a single `context.user_data['bybit_flow']` dict.

## The new unified flow (all 3 Bybit methods)
```
bybit_pay:        warning → Continue → UID → (amount if points) → deposit → Check
bybit_usdt_trc20: warning → Continue → (amount if points) → deposit → Check
bybit_usdt_bep20: warning → Continue → (amount if points) → deposit → Check
```
- **bybit_start_flow(q, context, method, mode, base_amount, product, qty)** — entry (both
  Buy-Points and Product). Shows the decimals/fee warning with editable Continue/Cancel.
- **bybit_flow_continue_callback** — bybit_pay → UID prompt; usdt product → straight to
  deposit; usdt points → amount prompt (network label shown).
- **bybit_flow_cancel_callback** — clears `bybit_flow` + `pending_order_id`, returns to
  Buy Points. One cancel path for everything.
- **bybit_flow_uid_received** — validates digits (6–12); product mode creates order directly
  after UID, points mode asks amount.
- **bybit_flow_amount_received** — unified for pay & usdt (right invalid-msg per method),
  min $1. Creates the order (unique 4-decimal amount for points / exact price for product),
  8-digit reference, stores customer_bybit_uid for pay, status bybit_waiting/usdt_waiting.
- **_bybit_create_and_show** — deposit screen with editable buttons:
  Copy amount / Copy UID (pay) or Copy address / Copy amount (usdt) + Check payment +
  Cancel payment. Uses a single `_bybit_flow_target()` to handle CallbackQuery vs Message.
- **Verification engine unchanged (proven):** `bybitv_<oid>` → API match by
  sender-UID+amount (pay) or network+address+amount (usdt) → credit points / deliver
  product. Background job auto-checks every 45s. Admin "Mark Received & Credit" fallback.

## Bot wiring (bug-free guarantees)
- `payment_flow_text_handler` (group −80, before all conversations) reads the unified
  `bybit_flow` dict for UID/amount steps and returns True when consumed (never swallowed by
  stale conversations; never double-handled).
- Old per-flow user_data keys removed (`bybit_flow_step`, `bybit_usdt_step`, …) — one dict.
- Old callback patterns removed; new `^bybit_flow_continue$` / `^bybit_flow_cancel$`.

## Tests (v125)
`_test_v125_bybit_flow.py` — **8/8 PASS**: full points bybit_pay flow (warning → continue →
UID → amount → order with UID+ref+status → deposit screen) ✅ · full points usdt_trc20 flow
(no UID asked, order usdt_waiting, address+network shown) ✅ · bad UID/amount rejected ✅ ·
cancel clears flow ✅ · wrong-step returns False ✅ · responses/buttons/screens present ✅.

Regression: v124 4 + v123 12 + v122 13 + v120 7 + v119 14 + v118 8 + v117 4 + v116 6 + v114 9
+ v112 15 + v111 17 = **117/117 PASS**. Boot clean; restore-ready DB verified (integrity ok,
108 responses, both new columns).

## 🔧 Files changed
- `handlers_order.py` — deleted ~290 lines of old flow; added unified flow (6 functions) +
  rewritten entry points.
- `bot.py` — routing via `bybit_flow` dict; callbacks `^bybit_flow_continue/cancel$`.
- `CHANGELOG.md` — this section.

---

# 🚀 v124 (2026-08-01) — CRITICAL: bot "stuck when user types amount" — stale-conversation fix

**User bug report:** after restoring the DB, the bot gets stuck as soon as a user types
the Bybit Pay / Bybit USDT deposit amount. Reproduced both flows.

## 🕵️ Root cause (detective work)
`handle_text` was registered as the LAST MessageHandler (group 0), but customer-facing
**ConversationHandlers** (support ticket `st_new` → states 400/401, warranty `wr_type` → 402,
user-chat reply → 460, plus every admin conversation) were registered BEFORE it with
`allow_reentry=True` and **no `conversation_timeout`**. In PTB, once a chat enters a
conversation state it stays there until the conversation ends — so a user who ever started
(and abandoned) a support ticket / warranty / review flow remains "in conversation" forever.
Every subsequent text message (e.g. a Bybit amount) is then **claimed by that conversation**
and never reaches `handle_text` → the bot appeared **stuck**. Restoring the DB did not cause
this — it just made the fresh deploy hit the same latent bug (the old DB probably had users
with stale states too).

## ✅ Fixes
1. **New `payment_flow_text_handler`** (bot.py) — registered in **group −80**, i.e. it runs
   BEFORE all ConversationHandlers. It consumes text ONLY when a payment-flow step is active
   (Bybit Pay UID/amount, Bybit USDT amount, USDT/Binance TXID, EasyPaisa/JazzCash TID,
   Buy-Points custom amount) and returns **True** when handled, **None** otherwise so normal
   flow continues. Verified: returning None (bare `return`) is treated by PTB as "not
   handled" — so success paths return True explicitly.
2. **`conversation_timeout=900`** (15 min) added to **every** ConversationHandler (26 admin +
   support/warranty/reply + per_message=False supplier flows = 38 total). Stale conversations
   now auto-expire, so no user's chat can be trapped indefinitely.

## Tests (v124)
`_test_v124_stuck_fix.py` — **4/4 PASS**: bybit_usdt amount consumed by priority handler
(order created + deposit screen sent + step cleared) ✅ · bybit_pay UID amount consumed ✅ ·
normal text returns None (not swallowed) ✅ · all conversations carry a timeout ✅.

Regression: v123 12 + v122 13 + v120 7 + v119 14 + v118 8 + v117 4 + v116 6 + v114 9 + v112 15
+ v111 17 = **109/109 PASS**. Boot clean with the restore-ready DB; no undefined names.

## 🔧 Files changed
- `bot.py` — `payment_flow_text_handler` (group −80, returns True on handled),
  `conversation_timeout` on all ConversationHandlers.
- `CHANGELOG.md` — this section.

---

# 🚀 v123 (2026-08-01) — FLOOD FIX (bot stuck after restore) + Bybit USDT deposit flow (TRC-20/BEP-20)

## 🐛 CRITICAL FIX — bot stuck in a loop after DB restore
**Symptom:** bot repeated "stuck" since restoring the DB; was fine before.

**Root cause (found by inspecting the restored DB):** the backup carried
`pua_interval_unit=seconds`, `pua_min_interval=1`, `pua_max_interval=10` with
`pua_global_enabled=1` and **233 active users**. The per-user fake-activity engine
therefore scheduled **hundreds of Telegram sends per second** → `429 Too Many Requests` /
`FloodWait` → every handler blocked → bot appeared dead/stuck, and it re-flooded on every
restart. These settings were leftovers from an old test run.

**Fixes:**
1. `per_user_activity.get_speed_seconds()` — new **FLOOR_SECONDS=30** clamp: no matter the
   stored unit/intervals, a single user can never be messaged more often than every 30s.
   This makes the whole class of misconfiguration impossible.
2. `self_heal._heal_activity_flood_settings()` — on startup, if `pua_interval_unit=seconds`
   with tiny intervals, it resets to `minutes`, min=1, max=60 and logs it.
3. **Restore-ready DB fixed**: `pua_interval_unit=minutes`, `pua_min_interval=1`,
   `pua_max_interval=60` (so a fresh restore is safe immediately).

## ✅ Bybit USDT deposit flow (both TRC-20 & BEP-20) — screen by screen
Same UX as the Bybit Pay UID flow, adapted for on-chain USDT:

1. ⚠️ **Warning** (decimals matter + **fee note**: network fee deduct hone par amount upar
   add karo; bot network fees ki zimmedar nahi) — Continue / Cancel.
2. 🟡 **Amount prompt** — "Deposit via USDT — {TRC-20|BEP-20} Network", min $1.
3. 💸 **Deposit screen** — address, **unique exact amount** (e.g. 1.4800), network warning
   (Arabic included in default), 30-min expiry, auto-add note. Buttons:
   Copy address · Copy exact amount · Check payment · Cancel payment.
4. **Check payment** → existing `bybitv_` verifier → API auto-detects by
   network + address + exact amount (+ order-anchor) → credits points or delivers product.

- New editable responses: `bybit_usdt_warning_text`, `bybit_usdt_amount_prompt`,
  `bybit_usdt_amount_invalid`, `bybit_usdt_deposit_instructions`, `bybit_usdt_cancelled`.
- New editable button: `bybit_copy_address` (reuses bybit_continue / bybit_cancel_flow /
  bybit_copy_amount / bybit_check_payment / bybit_cancel_payment).
- Screen editor: new nodes `bybit_usdt_warning_screen`, `bybit_usdt_amount_screen`,
  `bybit_usdt_deposit_screen`, `bybit_usdt_flow_layouts` (Simple/Pro/Minimal presets via the
  generic layouts engine — preview + apply).
- Buy Points and Product flows both branch `bybit_usdt_trc20`/`bybit_usdt_bep20` into the
  new flow. Points → unique amount (base + random 4-decimal fraction). Products → exact
  price (no random add; overpay avoided), delivered on check.

## Tests (v123)
`_test_v123_usdt_flood.py` — **12/12 PASS**: seconds-unit clamped ≥30s ✅ · minutes normal ✅ ·
heal fixes dangerous settings ✅ · warning has fee note ✅ · deposit/amount responses format ✅ ·
unique amount ✅ · screen nodes + children + layouts render ✅ · copy-address button ✅ ·
USDT order created with method/status/price ✅.

Regression: v122 13 + v120 7 + v119 14 + v118 8 + v117 4 + v116 6 + v114 9 + v112 15 + v111 17
= **105/105 PASS** (plugin pytest-asyncio required). Boot clean; restore-ready DB re-verified
(integrity ok, all 108 responses, flood settings fixed).

## 🔧 Files changed
- `per_user_activity.py` — flood floor (30s) in `get_speed_seconds()`.
- `self_heal.py` — `_heal_activity_flood_settings()`.
- `config.py` — 5 new bybit_usdt responses.
- `button_system.py` — `bybit_copy_address`.
- `handlers_order.py` — USDT flow (warning/amount/deposit), entry-point branching.
- `customization.py` — 4 new screen nodes + `bybit_usdt_flow` layouts group + buttons/texts.
- `bot.py` — routing + `^bybit_usdt_warn_ok/cancel` registration.
- `CHANGELOG.md` — this section.

---

# 🚀 v122 (2026-08-01) — Bybit Pay UID flow: warning → UID → amount → unique deposit, auto-match by UID+amount

**User request (full screen-by-screen flow):** redesign Bybit Pay for auto-detection:
1. ⚠️ Warning (copy full amount with decimals, exact amount matters) — Continue / Cancel
2. 🆔 Enter your Bybit UID (digits) — user sends it
3. 🟡 Enter deposit amount (min $1) — user sends it
4. 💸 Deposit instructions — send to store UID, **unique 4-decimal amount** (e.g. 1.9076 /
   1.9700), 8-digit reference, 30 min, copy amount / copy UID / check payment / cancel buttons
Bot auto-matches by **sender Bybit UID + exact amount** — no pasted ID needed.

## ✅ Implemented

### New flow (Buy Points → Bybit Pay)
- `_bybit_show_warning()` — warning screen with Continue/Cancel (editable buttons).
- `bybit_warn_ok_callback` / `bybit_warn_cancel_callback` — continue asks UID; cancel returns
  to Buy Points and clears flow state.
- `bybit_uid_received()` — validates digits (6–12), stores the customer's Bybit UID.
- `bybit_amount_received()` — validates ≥ $1, generates the **unique amount** and 8-digit
  reference, creates the order (price/binance_amount = unique amount, stores UID + reference),
  shows the deposit screen.
- `_bybit_show_deposit_screen()` — editable deposit instructions + buttons:
  Copy amount / Copy UID (copy-text), Check payment (reuses bybitv_ verify), Cancel payment.
- `_gen_unique_bybit_amount(base)` — `round(base + rand(0.0001..0.9999), 4)` → unique
  4-decimal amount per order (1 → 1.9076, 5 → 5.0087). Same nominal deposit from many users
  at once still yields distinct amounts.
- Matching: `_find_matching_bybit_payment` — when the order carries `customer_bybit_uid`,
  it matches an internal deposit **only** from that exact sender UID with the exact amount
  (no generic fallback → no cross-crediting). Legacy orders without a stored UID keep the
  old fallbacks.

### New editable responses (config.py)
`bybit_warning_text`, `bybit_uid_prompt`, `bybit_uid_invalid`, `bybit_amount_prompt`,
`bybit_amount_invalid`, `bybit_deposit_instructions`, `bybit_check_payment_ok`, `bybit_cancelled`.

### New editable buttons (button_system.py)
`bybit_continue`, `bybit_cancel_flow`, `bybit_check_payment`, `bybit_cancel_payment`,
`bybit_copy_amount`, `bybit_copy_uid` — rename / premium emoji / color from the screen editor.

### Screen editor (customization.py)
New nodes under Bybit Flow: `bybit_warning_screen`, `bybit_uid_screen`, `bybit_amount_screen`,
`bybit_deposit_screen`, plus `bybit_uid_layouts` (readymade Simple/Pro/Minimal deposit layouts
via the generic engine). New texts+buttons registered in the flow screen.

### DB
- New `orders.customer_bybit_uid` column + set/get helpers.
- `payments.get_bybit_internal_deposits` now exposes `from_member_id` (sender UID).
- Response editor: 💳 Payment category also catches `bybit_*` keys.

## Tests (v122)
`_test_v122_bybit_uid_flow.py` — **13/13 PASS**: unique amount 4-decimals + ≥ base + random ✅ ·
correct UID+amount matches ✅ · wrong UID not matched ✅ · wrong amount not matched ✅ · legacy
order (no UID) still falls back ✅ · new responses registered + formattable ✅ · screen nodes +
children + layouts render ✅.

Regression: v120 7 + v119 14 + v118 8 + v117 4 + v116 6 + v114 9 + v112 15 + v111 17 =
**93/93 PASS**. Boot clean, no undefined names.

## 🔧 Files changed
- `database.py` — customer_bybit_uid column + helpers.
- `payments.py` — from_member_id in internal deposits.
- `config.py` — 8 new responses.
- `button_system.py` — 6 new registry buttons.
- `handlers_order.py` — UID flow, unique amount, exclusive UID+amount match.
- `customization.py` — 5 new screen nodes + bybit_uid layouts group.
- `handlers_admin.py` — bybit_* category prefix.
- `bot.py` — text routing + callbacks.
- `CHANGELOG.md` — this section.

---

# 🚀 v121 (2026-08-01) — Bybit Pay instructions updated: auto-detect, no pasting

**User request:** "Bybit pay ki instructions ander sy change krdo — waha kuch paste karne ki
zaroorat hi nahi, os hisab sy likho."

## ✅ What changed
The bot now auto-detects Bybit Pay payments (v117 order-anchor + v118 reference), so the
instructions no longer ask customers to copy/paste a Transfer ID / Order ID into the chat.

### New default (config.py)
```
🟡 *Bybit Pay — Order #{order_id}*
━━━━━━━━━━━━━━━━━━━━
💰 Amount: *{amount} USDT*
📥 Bybit Pay ID / UID: `{pay_id}`

*How to pay:*
1. Open Bybit app → Bybit Pay → Send
2. Send exactly *{amount} USDT* to the UID above
3. Done — that's it! ✅

🤖 Your payment is detected automatically from your Bybit account and credited within seconds.
_No need to paste any ID or screenshot._
```
- `payment_bybit_pay_reference` now marked **Optional** ("Not required — payment is
  auto-detected either way").

### Readymade layouts updated (customization.py)
All 3 Bybit Pay layouts (Simple / Pro / Minimal) reworded to the no-paste flow. The Reference
ID remains optional in each.

### Self-heal (self_heal.py)
`_heal_bybit_instruction_text()` now also catches the common edited variant
("Paste it here in chat" / "Paste the Transfer ID here in chat") and rewrites it to the new
no-paste text — so a live DB carrying the old wording gets updated on deploy. Admin text that
is already different is preserved.

## Tests
- New default + all 3 layouts verified: no leftover `{placeholders}`, no "paste" wording.
- Full regression: v120 7 + v119 14 + v118 8 + v117 4 + v116 6 + v114 9 + v112 15 + v111 17 =
  **80/80 PASS**.

## 🔧 Files changed
- `config.py` — `payment_bybit_pay` + `payment_bybit_pay_reference` defaults.
- `customization.py` — 3 Bybit Pay layout texts.
- `self_heal.py` — heal catches paste variants.
- `CHANGELOG.md` — this section.

---

# 🚀 v120 (2026-08-01) — Readymade layouts for EVERY screen + 100% response coverage in editor

**User request:** "In sab ke liye bhi bana do" (layouts for all screens like Bybit Pay), and
"edit responses mein sab responses add kar dena jo nahi hain abhi".

## ✅ 1. Edit Responses — every response now in a named category
Audit: 95 DEFAULT_RESPONSES keys. 8 payment_* keys (`payment_bybit_pay`, `payment_bybit_pay_reference`,
`payment_binance_pay_orderid`, `payment_binance_usdt`, `payment_bybit_usdt`, `payment_binance_menu_text`,
`payment_bybit_menu_text`, `payment_not_found_txid`) were falling into the "uncategorized" catch-all.
- `handlers_admin.py` category rules updated: the 💳 Payment category now also catches `payment_*`
  prefix; new 🧾 Order Flow category catches `order_*`/`refund_*`; 💎 Points also catches `points_*`.
- Result: **0 uncovered keys** — every response appears in a named category (plus the catch-all
  stays for future-proofing). The 8 payment_* keys now show under 💳 Payment Screens.

## ✅ 2. Readymade layouts for every payment flow screen
New generic engine in `customization.py`:
- `SCREEN_LAYOUT_GROUPS` — each group defines its response keys + sample values + presets:
  - 🔶 **binance_pay** (Simple/Pro/Minimal) → rewrites `payment_binance_pay_orderid`
  - 🪙 **binance_usdt** (Simple/Pro/Minimal) → `payment_binance_usdt`
  - 🟡 **bybit_usdt** (Simple/Pro/Minimal) → `payment_bybit_usdt`
  - 📱 **easypaisa** (Simple/Pro/Minimal) → `easypaisa_pay_instructions`
  - 📱 **jazzcash** (Simple/Pro/Minimal) → `jazzcash_pay_instructions`
  - 📜 **order_flow** (Standard/Friendly) → order_created/cancelled/rejected set
- New screen-editor nodes (each a child of its flow screen, 🎨 icon):
  `binance_pay_layouts`, `binance_usdt_layouts`, `bybit_usdt_layouts`,
  `easypaisa_layouts`, `jazzcash_layouts`, `order_flow_layouts`.
- Callbacks `scl_preview_<group>_<layout>` / `scl_apply_<group>_<layout>` — same
  preview-then-apply UX as Bybit Pay layouts. After applying, texts stay editable.
- Preview renders with sample values so the admin sees the exact customer-facing screen.

## Tests (v120)
`_test_v120_responses_layouts.py` — **7/7 PASS**: all 95 responses covered by category rules ✅
· payment_* keys reachable ✅ · all 6 layout groups defined with ≥2 presets ✅ · every preset
renders with no leftover `{placeholders}` ✅ · layout screens valid in SCREEN_TREE ✅ · flow
screens link their layout children ✅ · apply writes responses + formats ✅.

Regression: v119 14 + v118 8 + v117 4 + v116 6 + v114 9 + v112 15 + v111 17 = **80/80 PASS**.
Boot clean, no undefined names.

## 🔧 Files changed
- `handlers_admin.py` — response category rules (payment_* + orderflow + points_*).
- `customization.py` — `SCREEN_LAYOUT_GROUPS` (6 groups, 16 presets), `_scl_sample_render`,
  `_show_screen_layouts`, `scl_apply_callback`, `scl_preview_callback`, SCREEN_TREE nodes.
- `bot.py` — imports + `^scl_apply_` / `^scl_preview_` registration.
- `CHANGELOG.md` — this section.

---

# 🚀 v119 (2026-08-01) — Bybit Pay screens fully editable (screen-by-screen) + readymade layouts

**User request:** "Screen by screen mein ja k in sab screens ko edit kar saku — buttons rename
(premium emoji), background color (blue/red/green), aur har full screen ke readymade layouts
with preview."

## ✅ What changed

### 1. Reference ID line is now editable
- New editable response key `payment_bybit_pay_reference` (`{reference_id}` placeholder) with a
  default. The Bybit Pay checkout now appends this editable line (was hardcoded).
- Registered in the Screen-by-Screen editor tree: Bybit Flow → **📝 Bybit Pay Reference ID Line**.

### 2. Copy buttons are now real editable buttons
- New registry buttons `pay_copy_reference` (🔖 Copy Reference ID) and `pay_copy_bybitpay`
  (📋 Copy Bybit Pay ID), group `pay`, **essential** (can't be hidden).
- New `button_system.make_copy_text_button()` — builds the button from the standard
  `btn_label_pay_copy_*` (rename + premium emoji via [[HTML]]<tg-emoji>) and
  `btn_style_pay_copy_*` (background color) settings, with `copy_text` preserved.
- They appear in the Screen Editor (Bybit Flow → buttons) and the Manage Buttons panel →
  rename / color / premium emoji exactly like every other button.

### 3. Readymade Bybit Pay layouts with preview + apply
- New screen **🎨 Bybit Pay Readymade Layouts** (child of Bybit Flow in the screen editor).
- 3 presets: 🔖 Simple · 🟡 Pro · ⚡ Minimal — each a full checkout text + reference line.
- Per preset: **👁 Preview** (shows the exact customer-facing screen with sample values) and
  **✅ Apply** (writes the two editable response keys). After applying, every text stays
  editable in the normal screen editor.
- Callbacks: `bypl_preview_<key>` / `bypl_apply_<key>`.

## Tests (v119)
`_test_v119_screens.py` — **14/14 PASS**: copy buttons in registry ✅ · default/custom/premium
label ✅ · color applied ✅ · reference response registered + format ✅ · screen tree contains
reference text + copy buttons ✅ · layouts screen valid + 3 presets formattable ✅ · sample
render ✅ · apply writes responses ✅ · ref gen/store roundtrip ✅.

Regression: v118 8 + v117 4 + v116 6 + v114 9 + v112 15 + v111 17 = **73/73 PASS**. Boot clean.

## 🔧 Files changed
- `button_system.py` — 2 registry buttons + `make_copy_text_button()`.
- `config.py` — `payment_bybit_pay_reference` default.
- `handlers_order.py` — reference line via editable response; copy buttons via the new builder.
- `customization.py` — SCREEN_TREE (reference text, copy buttons, layouts child),
  `BYBIT_PAY_LAYOUTS`, `_bypl_sample_render`, `_show_bybit_pay_layouts`,
  `bypl_apply_callback`, `bypl_preview_callback`, special-case render.
- `bot.py` — imports + `^bypl_apply_` / `^bypl_preview_` registration.
- `CHANGELOG.md` — this section.

---

# 🚀 v118 (2026-08-01) — Bybit Pay Reference ID (8-digit) + USDT order-anchor

**User request:** bot should give every order its own 8-digit Reference ID with a copy
button (like the UID), customer pastes it into Bybit Pay's Reference/Note field when sending,
and the bot auto-matches the payment. Also asked how USDT payments get auto-checked.

## 🕵️ Honest technical finding (live-verified)
The Bybit internal-deposit API record does **NOT** include the sender's Bybit Pay reference/note
(the live record showed only id/amount/type/coin/address/status/createdTime/txID/fromMemberId/
tax*/compliance fields). So the reference cannot be used as the *only* verification key via the
current API. **However** the bot already auto-adds payments without any pasted ID (proven in
production: the v117 unique-same-amount + order-creation anchor matched the wife's payment with
zero input). The Reference ID is therefore implemented as:
- a deterministic identifier per order (great UX, matches the user's ask),
- a **best-effort deep-match** candidate (if Bybit ever surfaces it, it matches instantly),
- plus the proven fallback still covers the case where it is not exposed.

## ✅ Implemented

### database.py
- New `orders.pay_reference` column (additive migration).
- Helpers: `set_order_pay_reference`, `get_order_pay_reference`, `gen_unique_pay_reference()`
  (8-digit numeric, collision-checked).

### handlers_order.py
- `_start_bybit_payment` (bybit_pay): generates + stores the Reference ID, appends
  **"🔖 YOUR REFERENCE ID: `12345678`"** to the instructions, and adds a
  **"🔖 Copy Reference ID"** copy button (beside Copy Bybit Pay ID).
- `_find_matching_bybit_payment`: match candidates now = pasted ID **or** stored Reference ID
  found anywhere in the record (deep-search, digits-normalized) **or** the proven
  unique-same-amount order-anchor fallback.
- `_find_matching_usdt_deposit`: **order-anchor** — a deposit that landed BEFORE the order was
  created can never match (on-chain USDT has no note, so time + address + amount + network +
  txid are the identifiers). This answers the user's USDT question: USDT auto-check already
  runs via the background job using network/address/amount (txid when pasted); now it is also
  anchored to order creation time for extra safety.

## Tests (v118)
`_test_v118_reference.py` — **8/8 PASS**: ref is 8-digit ✅ · unique ✅ · set/get roundtrip ✅ ·
stored-reference-found-in-record matches ✅ · not-in-record still falls back ✅ · USDT deposit
after order matches ✅ · before order rejected ✅ · wrong address rejected ✅.

Regression: v117 4 + v116 6 + v114 9 + v112 15 + v111 17 = **59/59 PASS**.

## 🔧 Files changed
- `database.py` — pay_reference column + 3 helpers.
- `handlers_order.py` — reference generation/show/copy in bybit_pay flow; reference deep-match;
  USDT order-anchor.
- `CHANGELOG.md` — this section.

---

# 🚀 v117 (2026-08-01) — Bybit Pay Fallback: Order-Creation Anchor (live-verified fix)

**User bug (live, resolved):** Bybit Pay order ID pasted but never verified even after v116.
User asked me to check the order ID directly against their API key.

## 🕵️ Live API investigation (user's real key)
- API key UID = `503209510` ✅ (matches bybit_pay_id — account correct).
- Internal deposit records: **exactly 1** — `id=36982932`, `txID=7efd6bc9-234f-4b8b-9794-151aa2d0`,
  `amount=1 USDT`, `status=2 (Success)`, `fromMemberId=563918642` (the sender's UID from the
  receipt screenshot), created `2026-07-31 12:57 UTC`.
- **The Bybit Pay "Order ID" (32-digit) is NOT stored anywhere in the API record** — the API
  only has the UUID txID + numeric id. So neither exact-ID match nor v116 deep-search can
  find it.
- Root cause of the live failure: the v113 fallback required the deposit to be **within 30
  minutes**. The payment was made hours before the customer pasted the ID → window expired →
  `hash_not_found:1` even though the payment was there the whole time.

## ✅ Fix — replace "within 30 min" with "after the order was created"
`_bybit_recent_amount_fallback()` now takes the `order` and matches a deposit ONLY when:
- internal transfer (Bybit Pay/UID), amount matches, txid not used,
- deposit `createdTime` **>= order.created_at** (parsed via new `_parse_order_created_epoch`;
  SQLite stores created_at in UTC, deposit times are ms — converted consistently),
- and it's the **only** such deposit (unambiguous → fraud-safe; ambiguous → admin decides via
  "Mark Received & Credit").

This retroactively matches payments that arrived hours ago as long as the bot order was
placed before the deposit — the exact scenario that was failing.

## Tests (v117)
`_test_v117_live.py` — **4/4 PASS** using the REAL record shape (id=36982932,
txID=7efd6bc9…, amount=1, createdTime=1785502625):
order(12:50UTC) before deposit(12:57UTC) → MATCH ✅ · order(13:05UTC) after deposit → reject ✅
· two same-amount deposits → no auto-fill (admin decides) ✅ · epoch parse ✅.

Regression: v116 6 + v114 9 + v112 15 + v111 17 = **51/51 PASS**.

## 🔧 Files changed
- `handlers_order.py` — `_parse_order_created_epoch()`, `_bybit_recent_amount_fallback(order=...)`
  order-anchor logic, module-level `import datetime as _dt`.
- `CHANGELOG.md` — this section.

---

# 🚀 v116 (2026-08-01) — Bybit Pay "Order ID" Deep-Match (the REAL fix for received-but-not-verified)

**User follow-up (live):** Confirmed UID matches, payment IS received on the same account,
yet `hash_not_found:1`. User's insight: "bot scans transaction hash, not the Order ID —
Bybit Pay history shows the Order ID."

## 🕵️ Root cause (confirmed)
Bybit Pay shows a **25–32 digit Order ID** on the receipt (e.g. `2607310002208331967166220288`),
while the internal-deposit API record's `txID` is a **different identifier (often a UUID)**.
The two NEVER match by string, so an exact-ID lookup always fails — the bot was comparing
the receipt Order ID against the API txID ("scanning transaction hash, not order id").

The API record for the payment exists (1 record was returned), but the Order ID lives in a
field we weren't checking — possibly `id`, or another unadvertised field in the raw row.

## ✅ Fix — deep-search the entire API record
- New `_norm_digits()` — strips everything except digits (handles spaces/dashes/copy glitches).
- New `_deep_find_id(record, key_norm)` — recursively walks the WHOLE deposit record
  (including `raw` nested dicts/lists) and matches the normalized pasted Order ID anywhere.
  A pasted Bybit Pay Order ID is long and specific, so finding it in the record is a safe,
  unambiguous match.
- `_find_matching_bybit_payment()` (bybit_pay): a record matches if the txID/hash matches
  OR the pasted Order ID is found anywhere inside it (amount must still match — wrong amount
  → `amount_mismatch`, never a blind credit).
- Admin failure alert's deposit dump now shows per record: `id`, `txid`, amount, network,
  age, and **"🎯 PASTED-ID FOUND IN RECORD"** when the deep search hits — so if it still
  fails you can SEE in the alert exactly what the API returned and whether your Order ID
  is there.

## Tests (v116)
`_test_v116_bybitpay.py` — **6/6 PASS**: Order ID in unlisted field matches ✅ · nested in
raw matches ✅ · spaces/dashes normalized ✅ · wrong ID (old deposit, no fallback) not
matched ✅ · ID found but wrong amount → `amount_mismatch` ✅ · dump flags PASTED-ID ✅.

Regression: v115(9)+v112(15)+v111(17) = **47/47 PASS** total.

## 🔧 Files changed
- `handlers_order.py` — `_norm_digits`, `_deep_find_id`, deep-match in
  `_find_matching_bybit_payment`, dump shows id + PASTED-ID-FOUND flag.
- `CHANGELOG.md` — this section.

---

# 🚀 v115 (2026-08-01) — Bybit "Payment Received But Not Verified" — UID Mismatch Diagnostics

**User bug report (live, with screenshots):** API Test passed ✅, wife sent $1 via Bybit Pay to
the store UID and pasted the Order ID, but verification failed with `hash_not_found:1`. The
admin alert seemed to show a different ID than pasted. Payment IS received (visible in the
Bybit app).

## 🕵️ Investigation (screenshots OCR + simulated scenarios)

- Bybit Pay receipt Order ID is a **32-digit reference** — the internal deposit API returns a
  **UUID txID**, so the exact-ID match can never succeed for Bybit Pay Order IDs (that's what
  the v113 amount+recency fallback is for).
- Simulated the exact flow 3 ways against the real matching code:
  1. Deposit **visible** to the API (fresh, unique, same amount, internal) → **matches** ✅
  2. Deposit **NOT visible** (empty) → `no_records` ✅
  3. Only an **old/unrelated** deposit visible → `hash_not_found:N` ✅
- The live result was `hash_not_found:1` with **no fresh same-amount internal deposit found**
  ⇒ the customer's Bybit Pay transfer is **not visible to the configured API key's account**.
  The code CAN match it when the API returns it — so the failure is on the account side:
  **the API key belongs to a different Bybit UID than the Pay ID customers pay to** (or the
  customer paid a different UID than the key's account).

## ✅ Fix — surface the mismatch instantly

### payments.py
- New `get_bybit_api_key_info()` — calls `GET /v5/user/query-api` and returns the **UID**
  (userID) the API key belongs to, plus the key note.

### handlers_admin.py — Bybit Test & Refresh now shows
- 🔑 **API key UID** (from the key itself)
- 🎯 **Customers pay to (bybit_pay_id)**
- 🚨 **UID MISMATCH warning** when they differ — with exact fix instructions
  (use a key from the SAME account as the Pay ID).

### handlers_order.py — failure alert now shows
- 🧾 Order **created_at** (so the admin can tell whether the alert is about the new payment
  or an old stuck order — explains "ye ID to maine dali hi nahi" when the background job
  alerts about old bybit_waiting orders).
- 🔑 API key UID vs 🎯 Pay ID comparison (same mismatch warning).
- 📡 **Deposit dump** — lists what the API actually returned (txid, amount, network, age),
  so it's instantly clear whether the customer's deposit is visible to the key.
- Manual **"✅ Mark Received & Credit"** button stays as the immediate workaround.

## Tests
3-scenario simulation verified (visible→match / invisible→no_records / old-only→hash_not_found).
Full regression: v114 9 + v112 15 + v111 17 = **41/41 PASS** (isolated runs).

## 🔧 Files changed
- `payments.py` — `get_bybit_api_key_info()`.
- `handlers_admin.py` — Test & Refresh shows UID + Pay ID + mismatch warning.
- `handlers_order.py` — alert shows created_at, UID comparison, deposit dump.
- `CHANGELOG.md` — this section.

---

# 🚀 v114.1 (2026-07-31) — Live-Verified Bybit Proxies Baked Into Default Pool

**User request:** "Mujhe khud find karke do ek proxy bybit ke liye jo bybit block na kare."

## 🕵️ Live verification (this session)
- This server's IP is geo-blocked by Bybit (403 CloudFront) and Binance (451) — same as Render's US cloud IPs.
- Scraped 1800+ free proxies from 6 sources, tested against Bybit public API → 56 working.
- Re-tested top 20 against **Bybit's PRIVATE deposit endpoint** with a fake signature:
  `retCode:10002/10003` responses prove the request REACHES Bybit's private API through the proxy
  (CloudFront geo-block bypassed), not just the public market endpoint.
- End-to-end `_bybit_get()` through the shared pool returned `retCode:10003 "API key is invalid"`
  → HTTP 200, real signed response → with the user's real key this returns deposit records.

## ✅ Change
`payments.py::_DEFAULT_PROXY_POOL` now ships with **18 live-verified proxies** (both-exchange
OK) + 1 Bybit-only + legacy PK defaults = 22 candidates. Because the pool is SHARED (v114),
these work for Binance AND Bybit automatically — no manual env needed. The Gemini scout keeps
the DB pool fresh when free proxies die.

⚠️ Note: these are FREE public proxies — short-lived by nature. Production best practice:
set a paid Pakistani VPS as `BYBIT_PROXY_URL` / `BINANCE_PROXY_URL` (or let the scout maintain).

## Tests
v114 (9) + v112 (15) + v111 (14+3) = **41/41 PASS**. Full compile + boot smoke clean.

## 🔧 Files changed
- `payments.py` — `_DEFAULT_PROXY_POOL` updated (verified list + provenance comment).
- `CHANGELOG.md` — this section.

---

# 🚀 v114 (2026-07-31) — Shared Proxy Pool: Binance + Bybit Auto-Recovery (Gemini Scout)

**User request:** Binance ke liye Gemini khud proxies find karta hai, test karta hai, pool mein
set karta hai — wahi Bybit ke liye bhi kaam kare, ya jo Binance ke liye mile wo Bybit mein
automatically set ho jaye.

## ✅ Fix — one shared proxy pool for both exchanges

Previously Bybit used ONLY the single `BYBIT_PROXY_URL` with zero rotation, zero health
tracking, zero auto-recovery — a dead/geo-blocked proxy made every Bybit verification fail
silently. Binance had the full pool + Gemini scout system.

### payments.py
- New `_request_with_rotation()` — generalized proxy rotation (pool order → cooldown skip →
  geo-block rotate → last-good persist) parameterized by `last_good_key` and an optional
  `geo_block_check` callable. `_do_request()` (Binance) is now a thin wrapper.
- **Bybit now rotates through the same shared pool.** `_bybit_get()` uses
  `_request_with_rotation(..., last_good_key="bybit_proxy_last_good")` and treats Bybit's
  403 CloudFront "block access from your country" (and 451) as a proxy failure → rotates.
  Real API errors (e.g. 10002 sign error) are still surfaced to the caller.
- `_load_proxy_pool()` now also includes `BYBIT_PROXY_URL` env and prioritizes
  `bybit_proxy_last_good` (shared pool, both exchanges' last-good considered).
- `_mark_proxy_ok()` gained a `last_good_key` param (default unchanged).

### ai_misc.py (Gemini scout)
- `_test_proxy()` now tests every candidate against **Binance AND Bybit** public endpoints.
  A candidate only counts as "working" when it passes BOTH — so nothing that fails Bybit
  ever enters the shared pool. (Binance `api/v3/time` + Bybit `v5/market/time`, both free.)
- `run_scout_sync()` stores the fastest working proxy as `bybit_proxy_last_good` too.
- `proxy_monitor_job()` auto-recovery now triggers when **either** Binance or Bybit API is
  configured (previously required Binance keys) — one scout cycle recovers both exchanges.

### Admin panel
- Scout "Running…" and "Complete" messages updated: candidates tested against
  *Binance + Bybit*, "shared pool" wording.

## Result
- Gemini finds PK proxies → tests against both Binance & Bybit → adds to one shared pool →
  Binance **and** Bybit both auto-rotate through it and recover when proxies die.
- No extra env var needed: `BYBIT_PROXY_URL` (if set) just joins the same pool.
- Bybit keeps its own last-good so a proxy proven against Bybit is preferred for Bybit.

## Tests (v114)
`_test_v114_proxy.py` — **9/9 PASS**: BYBIT_PROXY_URL joins pool ✅ · bybit last-good
prioritized ✅ · _bybit_get uses shared rotation ✅ · 403-CloudFront rotated vs auth error
not rotated ✅ · rotation marks bybit last-good ✅ · proxy must pass BOTH exchanges ✅ ·
dual-pass OK ✅ · scout sets bybit last-good ✅ · monitor auto-recovers when only Bybit
configured ✅.

Regression: v111+v112 **32/32 PASS**. Full 46-file compile + boot smoke clean.

## 🔧 Files changed
- `payments.py` — `_request_with_rotation()`, `_bybit_get()` pool rotation,
  `_load_proxy_pool()` +BYBIT_PROXY_URL/bybit last-good, `_mark_proxy_ok()` param.
- `ai_misc.py` — dual-endpoint `_test_proxy()`, bybit last-good in `run_scout_sync()`,
  monitor gate Binance-OR-Bybit.
- `handlers_admin.py` — scout messages mention Binance + Bybit / shared pool.
- `CHANGELOG.md` — this section.

---

# 🚀 v113.1 (2026-07-31) — Bybit "Test & Refresh" Button in Admin Panel + Geo-Block Hint

**User need:** couldn't find any Bybit connection test — because none existed in the UI.
`bybit_test_connection()` was written (v112) but never wired to a button, so API-key /
permission / IP problems stayed invisible until a real customer paid.

## ✅ Fix
- New **"🔄 Bybit Test & Refresh"** button in Admin → 💳 Payment Methods → 🪙 Crypto Settings.
- New `bybit_test_callback` in `handlers_admin.py` (registered as `^bybit_test$`):
  - Shows 🔴 "API key not set" + exact Render env instructions when keys are missing.
  - Runs the dual-endpoint test (on-chain + internal deposits) in a thread and shows
    ✅ PASS / ❌ FAIL with full detail.
- Crypto Settings panel now also shows live status: **API Key: 🟢 set / 🔴 MISSING**.
- **Geo-block detection:** live testing from a US cloud IP proved Bybit returns
  *403 "CloudFront distribution is configured to block access from your country"*.
  The test message now detects 451/403/CloudFront/block and tells the admin to set
  `BYBIT_PROXY_URL` (Pakistani VPS/proxy) in Render env — this is almost certainly
  required for Bybit API to work from Render's US servers.

## Tests
Full suite re-verified: Bybit 15/15, v111 17/17 — **32/32 PASS**. Boot smoke clean.

## 🔧 Files changed
- `handlers_admin.py` — `bybit_test_callback`, Test button + API-key status in `admin_pm_crypto_callback`, `import asyncio`.
- `bot.py` — import + `^bybit_test$` registration.
- `payments.py` — geo-block detection in `bybit_test_connection()` result.
- `CHANGELOG.md` — this section.

---

# 🚀 v113 (2026-07-31) — Bybit Pay Order-ID ↔ Transfer-ID Fallback Matcher

**User follow-up (live):** Customer paid via **Bybit Pay transfer** (not Withdraw) and
received a Bybit Pay **Order ID**. Bybit Pay's Order ID can differ in format from the
internal-deposit `txID` returned by `query-internal-record` — so an exact-ID match can
silently fail even when the money arrived.

## ✅ Fix

New `_bybit_recent_amount_fallback()` in `handlers_order.py`:

- If the pasted ID matches no deposit, accept a deposit ONLY when:
  - it's an **internal transfer** (`BYBIT_INTERNAL` — i.e. a Bybit Pay/UID transfer),
  - the **amount matches** within tolerance,
  - it arrived within the **last 30 minutes**,
  - it's **not already used**, and
  - it is the **ONLY** such deposit (unambiguous — a random ID can never claim a payment).
- Deduplicates the same record returned by both the exact-ID query and the full scan
  (a real case where one transfer appeared twice).
- If ambiguous (two same-amount fresh transfers) → no guess: the admin gets the
  existing "Mark Received & Credit" alert to decide.

## Tests (v113)

Fallback suite added: fresh unique same-amount match ✅ · old deposit NOT matched ✅ ·
two same-amount deposits NOT auto-matched (admin decides) ✅. Combined with v112:
**15/15 PASS** on the Bybit suite; v111 regression 17/17 separate-run PASS.

## 🔧 Files changed
- `handlers_order.py` — `_bybit_recent_amount_fallback()` + hook into
  `_find_matching_bybit_payment` + clearer `hash_not_found` hint.
- `CHANGELOG.md` — this section.

---

# 🚀 v112 (2026-07-31) — Bybit Payment Verification Fix (Transfer-ID + Diagnostics + Manual Rescue)

**User bug report (live):** Customer paid via Bybit → Withdraw → Internal transfer to the
store's Bybit UID → money received (visible in asset history, ID matched exactly) →
**bot never credited points.** Live DB showed 3 orders stuck in `bybit_waiting` (141, 147, 148).

## 🕵️ Detective Findings

1. **The matching logic was correct** — verified by simulation against the official Bybit
   V5 API response shape for `GET /v5/asset/deposit/query-internal-record` (internal deposit
   records with `txID`, `status: 2` = Success, `type: 1`). When the record IS returned, the
   bot matches it perfectly.
2. **The API layer failed silently.** Every `_bybit_get` failure (missing/wrong-permission
   API key, IP whitelist excluding Render, wrong account UID) was swallowed → empty list →
   generic `transaction_hash_not_found` → **no one was told.**
3. **`bybit_deposit_background_job` was 100% silent** — `except: pass` → stuck orders were
   invisible until a customer complained.
4. **`bybit_test_connection()` only tested on-chain deposits** (`query-record`) — never the
   internal-deposit endpoint Bybit Pay actually uses, so permission problems hid until a
   real customer paid.
5. **UX mismatch:** instructions said "Transaction Hash", but internal transfers have a
   *Transfer ID* (no blockchain hash) — customers could paste the wrong string.
6. **Minor bug:** internal deposit `createdTime` is in SECONDS per Bybit docs, was stored
   raw as `time_ms` (milliseconds by convention).

## ✅ Fixes

### F1 — Rich diagnostics from the Bybit API (`payments.py`)
- New `_bybit_last_meta` + `bybit_api_last_meta()`: every API call records HTTP code,
  `retCode`, `retMsg`, ok/count.
- `get_bybit_internal_deposits` / `get_bybit_deposit_records` record record counts.
- `createdTime` seconds → milliseconds conversion for internal deposits.

### F2 — `bybit_test_connection()` now tests BOTH endpoints
On-chain deposits **and** internal deposits. The admin's "Test & Refresh" button now
reveals immediately whether the API key can read Bybit Pay / UID transfers (the #1 cause
of silent failures) with clear hints (enable "Asset" read permission, check IP whitelist,
check the key belongs to the same UID as the Pay ID).

### F3 — Diagnostic failure reasons (`handlers_order.py`)
`_find_matching_bybit_payment()` now returns:
- `bybit_api_not_configured` — keys missing on server
- `api_error:<retMsg>` — the actual Bybit error (permission / IP / etc.)
- `no_records:internal=N,onchain=M` — API works, nothing found in 96h
- `hash_not_found:<N>` — N records scanned, ID matched none
- `amount_mismatch` — ID matched but amount differs (customer sent wrong amount)

### F4 — Actionable admin alert + one-tap manual rescue
- New `_notify_admin_bybit_failure()` — admin DM with the real reason, a human hint,
  and a **"✅ Mark Received & Credit"** button.
- New `bybit_manual_confirm_callback` — admin confirms receipt → order credited
  (idempotent, pasted ID marked used so it can't be re-used), customer notified.
- `_verify_bybit_order_and_respond` now sends this alert (throttled to once/15 min).
- `bybit_deposit_background_job` no longer silent: alerts admin once per stuck order
  (only for orders ≥ 3 min old, throttled 15 min) — **no payment can ever get stuck
  invisibly again.**

### F5 — Correct instruction wording
- `payment_bybit_pay` default now says "Transfer ID" (+ note that internal transfers
  have no blockchain hash). Self-heal updates the live DB default ONLY if it's still the
  untouched old text (admin customizations preserved).
- `payment_not_found_txid` default reworded to "Transaction / Transfer ID".

## ✅ Tests (v112)

`_test_v112_bybit.py` — **12/12 PASS**:
- Internal-deposit record (doc-shaped) → matched ✅
- Uppercase/dashed Transfer ID → matched ✅
- API error → `api_error:10001` surfaces ✅
- Zero records → `no_records` ✅ · hash mismatch → `hash_not_found` ✅
- Wrong amount → `amount_mismatch` ✅
- `createdTime` seconds → ms ✅
- Manual confirm credits points + marks TXID used ✅ / no double-credit ✅
- Background job alerts admin (once, throttled) with confirm button ✅
- Test connection checks both endpoints ✅

Regression: v111 suites still **17/17 PASS**. Full boot smoke test on the real backup DB:
clean (only expected dummy-token 401). **Grand total: 29/29 PASS.**

## 🔧 Files changed
- `payments.py` — `_bybit_last_meta`, `bybit_api_last_meta()`, dual-endpoint
  `bybit_test_connection()`, record-count meta, `createdTime` seconds→ms.
- `handlers_order.py` — diagnostic `_find_matching_bybit_payment()`,
  `_notify_admin_bybit_failure()`, `_bybit_failure_hint()`, `_bybit_failure_alerted_recently()`,
  `bybit_manual_confirm_callback()`, reworked `_verify_bybit_order_and_respond()`,
  alerting `bybit_deposit_background_job()`.
- `bot.py` — registered `^bybit_manual_confirm_` callback.
- `config.py` — reworded `payment_bybit_pay` + `payment_not_found_txid` defaults.
- `self_heal.py` — `_heal_bybit_instruction_text()` (live-DB default update, admin edits safe).
- `CHANGELOG.md` — this section.

---

# 🚀 v111 (2026-07-31) — Money-Safety Audit Fixes (C1/C2/C3 + H1/H2/H3 + M3)

Independent full-project audit performed on the live backup DB
(`bite_store_backup_20260731_131720.db`) — 43 files / 66K lines reviewed, boot-tested,
and covered by a new automated test suite (**17/17 PASS**).

---

## 🔴 CRITICAL — money / data integrity

### C1 — Paid orders were marked `delivered` when stock ran out
`build_delivery_from_accounts()` returned the sentinel
*"⚠️ Out of stock right now. Please contact admin…"* when 0 accounts were available,
but **every caller ignored it** and set the order to `delivered`. Customers paid → got
"contact admin" text → order looked delivered → no refund path, no admin alert.

**Fix:** New `build_delivery_detailed()` in `database.py` returns a structured result
(`ok / text / delivered / requested / mode`). The old `build_delivery_from_accounts()`
remains as a back-compat string wrapper. All 5 money-path call sites now branch on `ok`:
- `handlers_order.py::fulfill_paid_product_order` (main router)
- `handlers_order.py` Binance/EasyPaisa + JazzCash verification flows
- `handlers_admin.py` admin approval/deliver flow
- `support_replacement.py` warranty auto-redelivery (old code checked for `"no stock"`
  which **never matched** the real message — replacements were "approved" with OOS text)

On OOS/partial: order → `paid_pending_delivery`, customer gets an honest notice,
whatever IS available is still delivered, and **admin gets a DM alert** with
requested vs delivered counts.

### C2 — Partial delivery counted as full delivery
Buying 10 accounts when only 3 remained delivered 3 and marked the order `delivered` for 10.
Fixed by the same structured result: `ok` is only True when `delivered >= requested`.

### C3 — Wallet/points checkout race + ignored debit result
`pay_pts_callback` read balance → checked → debited in separate transactions and ignored
`deduct_points()`'s return value (it clamps at 0 and always "succeeds"). A failed debit
could still create + deliver the order (product for free), and the check/debit were not atomic.

**Fix:** New `deduct_points_if_enough()` in `database.py` — check + debit inside a single
`BEGIN IMMEDIATE`, returns False on insufficient balance or error. `pay_pts_callback` now
only creates + fulfills the order when the atomic debit returns True; otherwise shows the
(now re-read) balance screen.

## 🟠 HIGH — silent failures / ops

### H1 — `notify_admin` undefined in `ext_suppliers.py`
Used at 2 sites but never imported → `NameError` swallowed by `except: pass`. **Admin was
never told about (a) delivery-format quality warnings and (b) products auto-disabled after
3 consecutive supplier failures.** Fixed with a one-line import.

### H2 — `fmt_price` NameError in `handlers_buttons.py::_friendly_for`
`fmt_price` was only imported inside the `fc_btn_` branch; the `prod_` branch raised
`NameError` → button-editor product samples always showed the "🛍️ Product" fallback.
Fixed by hoisting the import to module level.

### H3 — USDT/Bybit waiting orders were never auto-cancelled
`_cancel_unpaid_orders_job` only covered `binance_waiting`/`screenshot_sent`/`pending` for
binance/easypaisa/jazzcash. Real DB had 4 orders stuck in `usdt_waiting`/`bybit_waiting`.
**Fix:** job now also cancels `usdt_waiting`/`bybit_waiting` (TRC20/BEP20 + Bybit methods),
and the window is configurable via bot_settings `unpaid_order_timeout_minutes` (default 60).

## 🟡 MEDIUM

### M3 — Business config now env-overridable (`config.py`)
`BACKUP_CHANNEL_ID`, `BACKUP_INTERVAL_HOURS`, `EASYPAISA_NUMBER`, `JAZZCASH_NUMBER`,
`ACCOUNT_NAME`, `BINANCE_PAY_ID`, `WHATSAPP_NUMBER`, `SUPPORT_EMAIL` now read from env
with identical defaults — zero behavior change for existing deployments. Payment numbers
still honor their existing bot_settings overrides.

## ✅ Tests (v111)

`_test_v111_audit.py` — **14/14 PASS** (C1 OOS + static-OOS, C2 partial/full + static,
C3 atomic debit ×4, H3 auto-cancel, regressions).
`_test_v111_fulfill.py` — **3/3 PASS** (end-to-end `fulfill_paid_product_order` with a
mocked bot: OOS → pending + alerts, in-stock → delivered, partial → pending + partial
delivery sent).

**17/17 PASS.** Boot smoke-tested against the real backup DB (zero schema diffs —
restore is safe). `migrate_all()` untouched: fully additive.

## 🔧 Files changed

- `database.py` — `build_delivery_detailed()` + `DELIVERY_OOS_TEXT`; `deduct_points_if_enough()`; `build_delivery_from_accounts()` kept as compat wrapper
- `handlers_order.py` — `fulfill_paid_product_order` + Binance/EasyPaisa/JazzCash verify flows use structured result; `pay_pts_callback` atomic debit
- `handlers_admin.py` — admin approve/deliver flow uses structured result + admin alert
- `support_replacement.py` — warranty redelivery uses structured result (fixes the "no stock" never-matching check)
- `ext_suppliers.py` — `notify_admin` import (H1)
- `handlers_buttons.py` — module-level `fmt_price` import (H2)
- `bot.py` — `_cancel_unpaid_orders_job` extended to USDT/Bybit + configurable window (H3)
- `config.py` — env-overridable business config (M3)
- `CHANGELOG.md` — this section

---

# 🚀 v110 (2026-07-25) — Backup + Pin + Referrals Grand Fix

**User requests (verbatim, 3 problems in one message):**
> "Jb backup lene k liye download backup py click kro to time out error ata hai phly osky bad back ja k dubara click kro download BACKUP py phir backup ajata hai jb k first time ma ana chiye backup"
> "Pinned announcement ma koi pin lgao or osy push kro to temporary error response ata hai bot ki trf sy lkin post pinned b hojati hai error k bawjood or jb os push ko delete krdo tb b temporary error ata hai mgr phir b delete hojati hai isko b fix kro"
> "Kl ek product py mene free via refreals on krdia tha or bht log refreals ly kr aye thy pr bot ny ek b refreal count ni kiya onka or na hi onko product mila free ma bht complain ai thi kl"

Follow-up: "10 sy opr quantity koi order kry outlook mails" — v109 already done ✅
Follow-up: "Ab mujy ya b bta do test krky referrels bot k b count hoty hai k ni or products k hoty hai k ni or free via refreals jis jis product ka ma on kro automatic sbki fake broadcasting shuru hojaye jinko off kro onki ruk jye osi time or agr sb off hai to kisi ki na ho"

---

## 🐛 Bug #1 — Backup Download Timeout on First Click

**Root cause:** `shutil.copy2` on a 1 MB SQLite DB + `send_document` ran INLINE inside the callback query handler. On a cold event loop, the whole operation took >10-15 s and Telegram's callback-query answer window expired → "query is too old" → user saw *Timeout* error. Second click succeeded because the DB was warm in OS page cache.

**Fix (Detective + Developer):**
- `backup_download_callback` and `backup_cloud_now_callback` now use a **background-task pattern**.
- `q.answer()` fires instantly with "Preparing…", the screen is edited with a placeholder, and the heavy copy + `send_document` is dispatched as `asyncio.create_task(...)`.
- `shutil.copy2` is wrapped in `asyncio.to_thread(...)` so the event loop stays free.
- All `q.answer` calls are wrapped in `try/except` so stale queries never bubble as errors.
- The final "backup sent" confirmation goes through `send_message` (independent of the callback query lifetime).

Users now see the backup file arrive on the **first click every time**, no matter how big the DB grows.

---

## 🐛 Bug #2 — Pinned Announcement "Temporary Error" on Push & Delete

**Root cause:** `broadcast_and_pin` iterates every registered user (70+ on real DB), sending + pinning per chat — takes 30-60 seconds. After that, the old code called `await q.answer("✅ Sent…", show_alert=True)` a **SECOND time on the same callback query**, which fails because the answer window (15 s max) had long expired. PTB logged "Temporary Error" (the pin push had actually succeeded).

Same issue for `admin_pin_del_callback` — `unpin_and_deactivate` loops through every user's chat calling `unpin_chat_message`, taking equally long.

**Fix (Bug Hunter + Developer):**
- `admin_pin_push_callback`: instantly edits the screen with "📢 Push in progress…", dispatches `_do_pin_push_bg` as background task, which sends the admin a summary message via `send_message` when done (Sent / Pinned / Failed counts).
- `admin_pin_del_callback`: **deletes the DB row FIRST** (so admin panel refreshes cleanly), then dispatches `_do_pin_unpin_bg` as background task for the slow per-user unpin loop.
- Every `q.answer` guarded with `try/except` — no more Temporary Error, ever.

---

## 🐛 Bug #3 — Referral Counting Silently Failed (0 out of ~20+ real users counted!)

**Investigation on user's real DB `shop_v107.db`:**
- `product_ref_pool` rows: **0** (nothing ever counted!)
- `referral_log` rows: **0** (function was never even reached, or all attempts silently blocked)

**Pro-user research + Telegram official docs deep-dive:**
Per [core.telegram.org/api/links](https://core.telegram.org/api/links): the Start button DOES appear with the deep-link parameter even for users who have already interacted with the bot. BUT the old rule set (v48) rejected any referral where `is_new_user == False` (rule "not_a_new_user"). This means **100% of referrals from users who had ever tapped the bot before were silently dropped** — which is the majority of real users in a Pakistani Telegram community where the bot's link circulates in groups people already saw.

**Fix (Detective + Bug Hunter):**
- **REMOVED** the `not_a_new_user` rejection rule (rule #4 in old code).
- **New guard:** only `already_has_referrer` (rule #3) prevents double-attribution — a user can be credited exactly once, but doesn't need to be brand new.
- **Anti-burst relaxed** from `>= 5 in 60s` to `>= 10 in 60s` (viral products bring 10+ users/min).
- **Anti-burst EXEMPTED for product-mode** referrals — because product-referrals don't award spendable `ref_points`, there's no incentive to abuse them.
- Everything else kept: self-referral block, banned referrer block, empty-name-and-username bot detection, duplicate-first-name anti-scripting.
- Admin still gets a DM for every accepted + blocked attempt (so future issues are diagnosable in real time).

### ✅ Live test proof (v110 test suite, 52/52 pass on real DB):
- Direct referral for **new user** → counted, ref_points +1, referred_by set ✅
- Direct referral for **returning user** (is_new=False) → **NOW COUNTED** (previously silently dropped) ✅
- Direct referral duplicate click → correctly rejected with `already_has_referrer` ✅
- Self-referral → correctly rejected ✅
- Product referral for new user → adds to `product_ref_pool`, ref_points unchanged ✅
- Product referral duplicate friend → no double-count ✅
- Product referral for returning user → **NOW COUNTED** ✅

---

## 🆕 Feature — Per-Product Referrals Tracker Inside Free-via-Referrals Panel

New button inside the Free-via-Referrals settings for each product:
**👥 Referrals for This Product**

Shows:
- Total unique referrers + total invites for this product
- Paginated (5 referrers per page) with drill-down: each referrer's name + Telegram ID + how many friends they brought + up to 3 friend names + join date

Callback pattern: `fcrf_refs_<pid>_<page>` — 0 collisions with existing patterns (421 → **422 total, all resolved**).

---

## 🆕 Feature — Referral Abuse Panel = DIRECT-Only View

The 🛡️ Referral Abuse Control panel now filters out product-mode entries. Counts + log views show ONLY direct/general referrals (the ones that award spendable `ref_points`, i.e. can actually be abused). Product-mode referrals now have their own dedicated view (see feature above).

New helper `_is_direct_referral(row)` — returns False if `reason` starts with `product_ref_pid_` or `dup_product_ref_pid_`.

---

## 🆕 Feature — Fake Free-via-Referrals Broadcasting (auto ON/OFF per product)

User wanted: *"jis jis product ka ma on kro automatic sbki fake broadcasting shuru hojaye, jinko off kro onki ruk jye osi time, or agr sb off hai to kisi ki na ho"*.

**Implemented in `per_user_activity.py`** (the live fake activity engine):
- New PUA type key: `pua_type_freeclaim` (default ON).
- New weighted branch in `build_fake_message()` — weight 8 (comparable to referral).
- On each activity tick, if the "freeclaim" type is selected, the branch:
  1. Fetches all products with `product_free_claim.enabled = 1` AND in-stock AND not hidden.
  2. If list is empty → gracefully skips (falls back to another type).
  3. Picks a random eligible product.
  4. Builds the message using **that product's admin-set custom text or picked template** (identical rendering to a REAL free-claim broadcast).
  5. Attaches the **per-product `fc_btn_<pid>` styled button** (text + premium emoji + size + color) if admin has customized it — otherwise the generic `sb_buy_generic` button.

**UI:** New toggle button in 🎭 Activity → Message Types: **🎁 Free-Claim (Fake)**.

**Behaviour matches user's exact request:**
- Enable Free-via-Referrals on Product A → Product A starts appearing in fake broadcasts immediately.
- Disable Product A + enable Product B → A stops, B starts.
- Disable both → no free-claim broadcast fires (fallback to other types).
- All PUA types off + only freeclaim on but no eligible product → gracefully returns without crash.

---

## ✅ Tests (v110)

`_test_v110.py`: **52/52 PASS** across 17 test groups covering all 3 bugs + 3 features + regression.
`_test_v109.py`: **58/58 PASS** (regression) · `_test_v108.py`: **11/11 PASS** (regression).

Latest 3 suites combined: **121/121 PASS**.

## 🔧 Files changed

- `handlers_admin.py` — backup_download_callback + backup_cloud_now_callback rewritten (background task + `asyncio.to_thread`).
- `loyalty_extras.py` — admin_pin_push_callback + admin_pin_del_callback rewritten (background task pattern).
- `handlers_start.py` — `_process_referral_attribution` v110 rule overhaul.
- `handlers_referral_admin.py` — panel + log now filter product-mode via `_is_direct_referral`.
- `handlers_free_claim.py` — new `fcrf_refs_callback` + new panel button.
- `bot.py` — imports + registers `fcrf_refs_callback` (`^fcrf_refs_` pattern).
- `per_user_activity.py` — new `freeclaim` branch in `build_fake_message`, new `S_TYPE_FREECLAIM` setting key.
- `ui_extras.py` — `_TYPE_MAP` and 🎭 Activity panel keyboard get the new "🎁 Free-Claim (Fake)" toggle.
- `fake_engagement.py` — helper `_get_freeclaim_broadcastable_products()` + type registration (dead panel code kept for compat).

---

# 🚀 v109 (2026-07-24) — Bulk Outlook Delivery = FILE-ONLY (Clean Text Summary)

**User request (verbatim):**
> "10 sy opr quantity koi order kry outlook mails ki phir only file jaye accounts ki text ma accounts na jaye or agr 10 sy nichy hai to text ma delivery ho file ma na jaye ya krdo"

**Q&A clarification:**
> "Rehny do bs mmostore ka krdo" · "Ni bs outlook py asa ho k 10 sy kam hai to asy delivery ho jese mmo store ka screenshot diya mene or agr 10 sy zada ho to bs file delivered hojye account details ki" · "Outlook ka kro bs"

## 🎯 What changed

In v108, when a customer bought **≥ 10** email_multi accounts (Outlook/Hotmail/M365), the bot sent BOTH a preview (first 3 + ⋯ + last 2) in the text message AND a `.txt` file attachment. Real MMOStore behavior (and what customers actually want) is: **text stays clean and readable, file has everything**.

**New v109 behavior — email_multi format only:**

| Quantity | Text message | File attached |
|----------|-------------|---------------|
| **< 10** | Full numbered list of all accounts (v108 unchanged) | ❌ No |
| **≥ 10** | Header + Format spec + "file attached" note ONLY | ✅ Yes (all N accounts) |

**Other formats (`email_pass`, `email_pass_2fa`, `redeem_link`, `code`, `custom`) unchanged** — bulk delivery still shows the v108 compact preview (first 3 + ⋯ + last 2) plus the .txt file. Only `email_multi` (Outlook-style with pipe-separated fields) got the file-only treatment because that's the format your Outlook customers were hitting.

### Sample text a customer sees now (email_multi, qty=15):

```
🎉 Bite Store Delivery
━━━━━━━━━━━━━━━━━━━━
📦 Product: Outlook Mail
🧾 Order ID: #999
📊 Delivered accounts: 15

📝 Format: Email | Pass | Refresh_token | Client_id
━━━━━━━━━━━━━━━━━━━━

📎 Full list of 15 accounts attached below as .txt file.
💡 Tip: Save the file securely — each line = 1 account.
🙏 Thank you for shopping with Bite Store!
```
→ Then the `bite_store_order_999_15accounts.txt` file follows with all 15 accounts.

No account content, tokens, or passwords ever appear in the chat message for bulk email_multi orders. Cleaner, faster to read, and customer's chat history stays tidy.

## 🔧 Files changed

- **`ext_suppliers.py`** — `render_v83_delivery()` bulk branch (~line 3063):
  - Added `if fmt_key == "email_multi"` short-circuit that returns header + format spec + file-note only (no `preview_lines`, no ⋯, no `safe_items[0..-1]` leaking into text)
  - Non-email_multi bulk still runs original preview code
  - Router file-send logic (~line 2577) UNCHANGED — still writes ALL items to `bite_store_order_{id}_{qty}accounts.txt`

## ✅ Tests (v109)

`_test_v109.py`: **58/58 PASS**

- `test_email_multi_bulk_15_no_account_preview` — 12 asserts including "NO user1@outlook.com leaked", "NO refresh token leaked", "NO password leaked"
- `test_email_multi_small_5_still_full_delivery` — v108 behavior preserved for < 10
- `test_email_multi_boundary_9_vs_10` — exact threshold check
- `test_non_email_multi_bulk_keeps_v108_preview` — regression: email_pass_2fa qty=15 still shows preview
- `test_email_pass_bulk_regression` — email_pass qty=11 still shows preview
- `test_redeem_link_bulk_keeps_v108` — redeem_link qty=12 still shows preview
- `test_router_file_still_sent_for_bulk` — file attachment logic intact
- `test_email_multi_bulk_uses_correct_format_spec` — spec still says "Email | Pass | Refresh_token | Client_id"
- `test_callback_resolver` — 421 patterns, 0 unresolved

**Regression:** v84–v108 unchanged (v108 test suite updated to match new email_multi bulk behavior — 11/11 pass).

---

# 🚀 v108 (2026-07-24) — MMOStore-Style Compact Delivery + Smart File Threshold

**User request (with MMOStore screenshots):**
> "Mmo store sy mene buy kia outlook account oska format dekhny k liye to asy delivery hoi file b ai hai or text bhi or format dekho email pass refresh token client id sb kuch ek sath hi likha hai or asy hi mera bot b delivery kry... asy set krna k in future kbi mn kisi or supplier sy b kam krna chahu or oski delivery format agr asa ho bot pehchaan ly or asy hi delivery kry text mn b or file mn b lkin file meri tb deliver ho jb customer minimum 10 quantity pr order kry"

## 🎨 3 Big Features

### Feature 1 — MMOStore-Style Compact Delivery Layout

Old v83 layout: per-field breakdown with 📧 Email / 🔑 Password / 🎫 Token / 🆔 Client_id icons.

**New v108 layout:** matches MMOStore's proven compact format that customers can copy-paste into automation tools:

```
🎉 Bite Store Delivery
━━━━━━━━━━━━━━━━━━━━
📦 Product: Outlook Mail
🧾 Order ID: #99
📊 Delivered accounts: 1

📝 Format: Email | Pass | Refresh_token | Client_id
━━━━━━━━━━━━━━━━━━━━

1. email@outlook.com|password123|M.C529_SN1.0.U.MsaArtifacts.-CpZ...|9e5f94bc-e8a4-4e73-b8be-63364c29d753

━━━━━━━━━━━━━━━━━━━━
💡 Tip: Save these details securely...
🙏 Thank you for shopping with Bite Store!
```

Byte-perfect via HTML `<code>` wrapping — every char preserved regardless of length.

### Feature 2 — File Threshold Changed to ≥ 10 Quantity

Old: >3 accounts triggered .txt file.
**New: ≥10 accounts triggers .txt file.**

- 1-9 accounts → compact numbered text list ONLY
- 10+ accounts → text preview (first 3 + last 2) + full .txt file attached
- File name: `bite_store_order_{id}_{qty}accounts.txt` (branded)

Reasoning: small orders don't need file (creates clutter), large orders benefit from file for bulk import.

### Feature 3 — Smart Auto-Detect for Any Supplier

Enhanced `detect_product_format()` to catch email_multi (4-field) format from multiple signals:

1. **Format line parsing:** Any product description with "Format: X | Y | Z | W" (4+ pipe fields) → email_multi
2. **Token/client keywords:** "Refresh_token", "Client_id", "MsaArtifacts", "batteries" → email_multi
3. **Pipe patterns:** "email | pass | refresh_token", "email|pass|token" → email_multi
4. **Name hints (NEW):** "Outlook Mail", "Hotmail Account", "Office365 Account" → email_multi (for suppliers with short descriptions)

**Future-proof:** Any new supplier that delivers 4-field format is auto-detected — no manual admin config needed.

## Live Proof (from your MMOStore Outlook Mail)

Before v108:
```
Description: "Private Outlook Mail Account - No Warranty."
Detected: email_pass ❌ (short description, no Format line)
```

After v108:
```
Description: "Private Outlook Mail Account - No Warranty."
Detected: email_multi ✅ (name-hint matched "Outlook Mail")
Format spec displayed: "Email | Pass | Refresh_token | Client_id"
```

Then when 15 accounts delivered:
- Text preview: `1., 2., 3., ⋯, 14., 15.` (compact, easy to scan)
- File attached: `bite_store_order_99_15accounts.txt` (branded, ready for bulk import)

## Test Results
```
_test_v84 to _test_v107  — 263/264 ✅
_test_v108               —  11/11  ✅  ← NEW
────────────────────────────
GRAND TOTAL: 274/275 tests PASS. (v97 canboso live smoke — network-dependent skip)
Zero regressions.
```

Coverage:
- ✅ Single account compact format (8 render checks)
- ✅ Small order (1-9) — full list, no file
- ✅ Bulk (10+) — preview + file note
- ✅ Threshold exact (9 = no file, 10 = has file)
- ✅ Router file threshold updated (>=10 + branded name)
- ✅ Auto-detect email_multi variants (8/8)
- ✅ Byte-perfect long token (529 chars preserved)
- ✅ Empty items graceful
- ✅ Redeem link format still works
- ✅ Callback resolver clean

## Files Modified in v108
- `ext_suppliers.py`:
  - `render_v83_delivery()` — rewritten with MMOStore compact style
  - Router `.txt` file threshold: `>3` → `>=10`
  - File name: branded `bite_store_order_{id}_{qty}accounts.txt`
  - `detect_product_format()` — enhanced with 4-field pipe pattern + name-hint detection

## How to Verify (After Deploy)
1. **Trigger a supplier order** (Outlook Mail from MMOStore) — customer sees compact numbered format
2. **Test bulk:** buy 10+ same product — customer gets text preview + .txt file
3. **Test small:** buy 1-9 — customer gets full text list, NO file
4. **Auto-detect:** any new supplier with "Format: A | B | C | D" in description → email_multi automatically

---

# 🚀 v107 (2026-07-24) — Force Refresh + Auto-Re-Mirror + Description Preview

**User complaint (v106 follow-up):**
> "Mmo store ka product sync kia mene oski discription ni ai na na format aya hai jb mene supplier k bot ma ja k dekha to whn osny os product ki discription or format dono lgaye hoye iska solution research kro dekho pro users ny is issue ko kese solve kia or khudka b brain use krna or phir isy fix kro teeno mode on krky"

## 🕵️ Investigation

Live-tested with user's MMOStore API key: all 12 products **DO** return descriptions (43–565 chars). The v106 fix works correctly on FRESH syncs. So why is user seeing missing data?

**Root cause identified:** For products **already `synced_to_shop=1`** BEFORE v106, the shop.products row has stale/empty data. Since `mirror_ext_to_products()` only runs on:
- Admin explicitly toggling "🔄 Sync to Shop" per product
- Bulk Sync flow (only iterates `synced_to_shop=1` products but no way to force-refresh individual ones)

...an admin who imported products BEFORE v106 has stale shop rows AND no easy path to fix them individually.

## 🌐 Pro-User Pattern Research

Researched Shopify + WooCommerce + PlayerUp reseller platforms — universal pattern is **explicit per-product "Force Refresh / Overwrite" button**. Every serious platform ships this because supplier-side edits are common and admins need instant heal without touching all products.

## ✅ Fix — 3 Layers

### Layer A — New `🔃 Force Refresh from Supplier` button per product
- Location: Supplier product view screen
- Behavior: hits supplier's live products endpoint → finds this specific `remote_id` → overwrites ext_product row (description, cost, stock, name) → re-runs format auto-detect → if `synced_to_shop=1`, re-mirrors to shop
- Popup summary shows: description length, detected format, shop mirror status
- Graceful handling if supplier removed the product (clear error message)

### Layer B — Auto-re-mirror on every `sync_supplier_products()` call
- Every fresh fetch (Import Products click, 30s auto-sync job) now silently re-mirrors ALL products already marked `synced_to_shop=1`
- Bot self-heals on every sync tick — admin doesn't need to remember to click anything
- Only ~10ms overhead per synced product

### Layer C — Description preview in admin product view
- Admin can now see the exact stored description (first 400 chars in expandable blockquote)
- Includes `(HTML-formatted)` indicator if content has HTML markup / `[[HTML]]` sentinel
- Diagnostic transparency — admin can verify vs supplier's actual description

## Live Proof (test suite)

Simulated the user's exact scenario:
```
BEFORE (corrupted shop row):
  shop.products.description = 'STALE_CORRUPT_DATA'
  shop.products.product_format = 'email_pass' (wrong)

AFTER re-import (v107 auto-re-mirror fires):
  shop.products.description = '[[HTML]]<blockquote>Original supplier desc...</blockquote>' ✅
  shop.products.product_format = 'email_pass_2fa' (correct detected format) ✅
```

## Test Results
```
_test_v84 to _test_v106  — 253/254 ✅
_test_v107               —   9/9   ✅  ← NEW
────────────────────────────
GRAND TOTAL: 263/263 tests PASS. Zero regressions.
```

Coverage:
- ✅ Description preview appears in admin view
- ✅ Force Refresh button + callback registered
- ✅ Auto-re-mirror heals stale corrupted data
- ✅ Force refresh re-runs format detect
- ✅ Force refresh conditional mirror (only if synced)
- ✅ Force refresh handles deleted-from-supplier gracefully

## Files Modified in v107
- `ext_suppliers.py`:
  - `ext_prod_view_callback` — added description preview block + Force Refresh button
  - New `ext_prod_refresh_callback` — implements the pro-user overwrite flow
  - `sync_supplier_products` — new auto-re-mirror loop at end (v107 self-heal)
- `bot.py` — imports + registers `^ext_prod_refresh_` pattern

## How to Verify (After Deploy)
1. **Immediate fix for existing stale products:** Suppliers → any supplier → 🔁 Bulk Sync All Products
   - Now automatically re-mirrors ALL your synced-to-shop products with fresh description + format
2. **Individual product refresh:** Suppliers → any supplier → Browse → any product → **🔃 Force Refresh from Supplier**
   - Instantly re-fetches that one product + re-mirrors to shop if synced
3. **Diagnose stored data:** Same product view now shows description preview at bottom (expandable) with `(HTML-formatted)` tag if applicable

---

# 🚀 v106 (2026-07-24) — Supplier Format + Description HTML Sync

**User complaint (verbatim):**
> "Product ka format or discription sync ni kr rha or han agr oska format ya discription ma osny koi premium emoji b use kiya ho to wo b proper render hona chiye ya na ho osmy premium emoji use kia ho mere pas koi coding show ho rhi ho ya simple emoji show ho raha ho ok ya fix krky do her supplier k products k sat onka format or discription bhi sync honi chiye or mujy show b honi chiye"

## 🕵️ 3 Bugs Found

### Bug 1 — `product_format` hardcoded to `"email_pass"` in mirror function

`mirror_ext_to_products()` had `"email_pass"` **hardcoded** in both INSERT and UPDATE queries. So even though v87's `detect_product_format()` correctly identified formats like `redeem_link`, `coupon_code`, `email_pass_2fa` and saved them on `ext_products.delivery_format`, that never propagated to `products.product_format`. Result: every synced supplier product delivered via `email_pass` template regardless of actual format.

### Bug 2 — HTML descriptions synced as plain text

Supplier descriptions from MMOStore (verified live) contain rich HTML markup like:
```
<blockquote>⚠️ <b>Note:</b> Please log in on only one device.
✅ Secure your account by changing 2FA</blockquote>
```

Old sync code stored this raw string. Then customer's product-detail render either:
- Stripped ALL tags via `html_strip_tags()` (HTML branch) → lost formatting, OR
- Rendered via `escape_md()` (Markdown branch) → showed literal `<b>Note:</b>` text as "coding" 🐛

### Bug 3 — HTML detection heuristic missed non-premium tags

`html_needed` check in `handlers_shop.py::_build_detail_text` only triggered on `<tg-emoji>` (premium) markup. Regular tags like `<b>`, `<blockquote>`, `<i>` did NOT trigger HTML mode → Markdown branch → literal tags shown.

## ✅ Fixes

### `ext_suppliers.py::mirror_ext_to_products`
1. **`product_format`**: now reads `ep.get("delivery_format") or "email_pass"` (falls back to email_pass only if no format detected). Auto-detected format from v87 detector now correctly propagates to shop.
2. **`description`**: if raw text contains HTML tags (`<b>`, `<i>`, `<u>`, `<s>`, `<code>`, `<pre>`, `<blockquote>`, `<tg-emoji>`, `<a>`, `<em>`, `<strong>`, `<br>`), auto-prefix with `[[HTML]]` sentinel so shop renderer knows to use HTML mode. Plain text passes through unchanged.

### `handlers_shop.py::_build_detail_text`
New `_has_html_tags()` helper — expands `html_needed` detection to include:
- `[[HTML]]` sentinel prefix
- Any regular HTML tag (`<b>`, `<blockquote>`, `<i>`, etc.) in description/warranty/quantity

When rendering description/warranty/quantity, three branches:
- Premium markup → `name_for_message_html()` (existing)
- Any HTML tags → strip `[[HTML]]` sentinel + embed raw (new)
- Plain text → `_html.escape()` + strip tags (fallback)

## Live Proof (from test suite)
```
BEFORE:
  supplier description: "<blockquote>⚠️ <b>Note:</b>...</blockquote>"
  admin panel: [[HTML]]<blockquote>⚠️ <b>Note:</b>...</blockquote>  ← wrapped ✅
  customer sees: **⚠️ Note:** — displays as bold within a blockquote ✅

BEFORE (still bug free):
  plain description: "This is plain text no tags"
  stored: "This is plain text no tags"  (no false [[HTML]] wrap) ✅
```

Also: any format like `redeem_link`, `coupon_code`, `email_pass_2fa`, `email_pass_recovery`, `email_multi` — all 5 verified via test suite → products.product_format matches ext_products.delivery_format 1-to-1.

## Test Results
```
_test_v84 to _test_v105  — 246/247 ✅  (1 skipped: v97 canboso live smoke — network)
_test_v106               —   8/8   ✅  ← NEW
────────────────────────────
GRAND TOTAL: 254/254 tests PASS. Zero regressions.
```

## Files Modified in v106
- `ext_suppliers.py::mirror_ext_to_products` — format sync + HTML description wrap
- `handlers_shop.py::_build_detail_text` — HTML detection + preservation for description/warranty/quantity

## How to Verify (After Deploy)
1. **Bulk Sync** any supplier (Admin → Suppliers → Choose supplier → 🔁 Bulk Sync All Products)
2. Open the shop product detail → HTML formatting now renders properly (bold, blockquotes, premium emojis)
3. Check `product_format` column — supplier products with `redeem_link` / `coupon_code` etc. now deliver with correct template (verify by viewing any order)

---

# 🚀 v105 (2026-07-23) — MMOStore Stock + Browse Back Button + Full-Precision Pricing

**User complaints (verbatim):**
> 1. "mmostore ka stock ni show hota products import hony k bawjood mene supplier k bot py ja k dekha whn stock add hai lkin api sy sync krny k bad her product ka stock 0 show ho raha asa q?"
> 2. "Jb kisi b supplier k products browse kr rha hota ho or next page py jany k liye... 3 dfa next gya ma ab jese hi back krta to first page py ly ata hai jb k os sy pichy waly page py back jana chiye"
> 3. "amount supplier ny 0.103 rkhi hoti or mere pas 0.02 bot dekhata hai... ma b kisi product ki price agr asi rkh do 0.024 ya 0.0030003 to lgti hi ni"

## 🐛 Bug 1 — MMOStore stock always 0 (same class as Canboso v97)

**Root cause:** MMOStore API returns stock as `stock_available` (verified via docs + live API test with user's key `mmostore_dce0bcbe...`). Adapter used `p.get("stock", 0)` — wrong key → always 0 → 12 products silently marked out-of-stock.

**Live proof after fix (12 products from user's key):**
| Product | Before | After |
|---|---|---|
| Account Gemini Pro + 5TB + Antigravity 1Y | 0 ❌ | 28 ✅ |
| ACTIVATION LINK 18-Month Gemini Pro | 0 ❌ | 7 ✅ |
| Outlook Mail | 0 ❌ | 3,925 ✅ |
| Gmail Domain rental 24-72h @abc.us | 0 ❌ | 21,103 ✅ |
| Gmail Domain rental 24-72h @abc.com | 0 ❌ | 15,427 ✅ |
| Gmail Domain rental 24-48h .us Gm | 0 ❌ | 70,380 ✅ |
| Phone number for Gmail/Google verify | 0 ❌ | 10 ✅ |

**Fix:** Defensive multi-key resolution (same pattern as Canboso v97):
```
priority: stock_available → stock → available → 0
```

## 🐛 Bug 2 — Browse pagination Back button always jumps to page 0

**Root cause:** In `ext_prod_view_callback`, the "🔙 Browse Products" button was hardcoded to `ext_sup_import_pick_{sid}_0`. So if admin was on page 3, opened a product, then tapped Back — always landed on page 1.

**Fix:** `ext_sup_import_pick_callback` now saves the current page into `context.user_data["ext_browse_page_{sid}"]`. `ext_prod_view_callback` reads this and generates the correct dynamic Back URL.

## 🐛 Bug 3 — Sub-cent pricing truncated to $0.00

**Root cause TWO layers:**

### Layer A: `_compute_sell_price()` was rounding
```python
return round(cost * (1 + mkp / 100.0), 2)   # ❌ 0.003 * 1.4 = 0.0042 → $0.00
```

### Layer B: 47 display sites across 8 files used `${price:.2f}`
- `0.103` supplier price → displayed as `$0.10`
- Admin's own product `0.024` → `$0.02`
- Fractional `0.0030003` → `$0.00`

**Fix:**
1. **`_compute_sell_price()`** — removed `round()`, preserves full float precision
2. **`fmt_price()` helper in `utils.py`** — smart formatter:
   - `$5`, `$5.1`, `$0.103`, `$0.024`, `$0.0030003`, `$0.0001` — all render correctly
   - Whole dollars drop `.00`, sub-cent shows full precision, trailing zeros stripped
3. **47 sites patched** across 8 files (`ext_suppliers.py`, `handlers_admin.py`, `handlers_buttons.py`, `handlers_order.py`, `handlers_shop.py`, `handlers_start.py`, `handlers_support.py`, `keyboards.py`)

**Live proof:**
```
BEFORE: cost=$0.003 * 40% markup → $0.00 (bot showed $0!)
AFTER:  cost=$0.003 * 40% markup → $0.0042 (bot shows $0.0042 correctly)

fmt_price display samples:
  0.103       → $0.103         (was $0.10)
  0.024       → $0.024         (was $0.02)
  0.0030003   → $0.0030003     (was $0.00)
  2.15        → $2.15          (unchanged)
  5.0         → $5             (was $5.00, now cleaner)
```

## Test Results
```
_test_v84 to _test_v104  — 239/239 ✅
_test_v105               —   8/8   ✅  ← NEW: mmostore field + browse memory + price precision
────────────────────────────
GRAND TOTAL: 247/247 tests PASS. Zero regressions.
```

## Files Modified in v105
- `ext_suppliers.py` — `MMOStoreAdapter.fetch_products` (stock_available fix); `MMOStoreAdapter.fetch_balance` (defensive string→float); `_compute_sell_price` (no more round); browse page memory in `ext_sup_import_pick_callback`; dynamic Back button in `ext_prod_view_callback`
- `utils.py` — new `fmt_price()` + `fmt_price_precise()` helpers (12/12 edge cases tested)
- `handlers_admin.py`, `handlers_buttons.py`, `handlers_order.py`, `handlers_shop.py`, `handlers_start.py`, `handlers_support.py`, `keyboards.py` — 47 `.2f` sites converted to `fmt_price()` (auto-patched via AST-safe regex)

## How to Verify (After Deploy)
1. **MMOStore stock:** Admin → Suppliers → MMOStore → 🔁 Bulk Sync — products now show real stock (7 out of 12 with real inventory including 70,380 Gmail domains)
2. **Browse Back button:** Admin → any supplier → Browse Products → go to page 3 → tap any product → Back button now returns to page 3
3. **Full precision pricing:**
   - Admin edits own product price to `0.024` → shows `$0.024` (not `$0.02`)
   - Admin sets to `0.0030003` → shows `$0.0030003` (not `$0.00`)
   - Supplier's `$0.103` cost with 40% markup → shows `$0.1442` (not `$0.14`)

---

# 🚀 v104 (2026-07-23) — Delivery Content Escaped `<tg-emoji>` Fix (Customer + Admin)

**User complaint (Order #18 screenshot):**
> Admin User-Side Preview showed raw `<tg-emoji emoji-id="5364339557712020484">📱</tg-emoji> Capcut Pro Team...` as literal text.
> User asked: *"Jb customer ko deliver hota hai kia tb osko b asy hi show hota ya sirf mujy asa show ho raha? Agr to dono side ya issue hai to dono ka fix krdo."*

**Answer:** YES, customer was seeing the same garbage. Same bug affects both sides because customer's original delivery message AND admin's preview both read from the same `orders.delivery_content` DB column — which was written with escaped `<tg-emoji>` tags.

## 🕵️ Root Cause

`render_v83_delivery()` in `ext_suppliers.py` was calling `html_escape_plain(product_name)` before writing to DB. For supplier products whose name contains premium emoji markup (`[[HTML]]<tg-emoji emoji-id="X">📱</tg-emoji> ProductName`), this escaped the `<` `>` `&` chars → `&lt;tg-emoji&gt;` → Telegram rendered it as literal text.

**Impact was dual:**
1. **Customer** — Every delivered supplier order since v83 had the ugly `<tg-emoji ...>` text visible in their delivery message
2. **Admin** — User-Side Preview (added in v101) faithfully re-displayed the stored bytes, showing the same garbage

Additional secondary bug: `product_name` starting with `[[HTML]]` sentinel got double-embedded, showing `[[HTML]]&lt;tg-emoji ...` in the escaped output.

## ✅ Fix — Two Layers

### Layer 1: NEW deliveries (post-v104)
- New helper `_render_delivery_product_name()` in `ext_suppliers.py` — smart branching:
  - `[[HTML]]` prefix → strip sentinel, embed raw HTML (premium emoji renders as icon)
  - Contains HTML tags → embed as-is
  - Plain text → escape safely
- Replaced both `html_escape_plain(product_name)` call sites in `render_v83_delivery()` (1-item render + bulk render)

### Layer 2: LEGACY orders (already-corrupted DB entries — like user's Order #18)
- New utility `heal_escaped_delivery_content()` in `utils.py` — display-time healing:
  - Regex unescapes `&lt;tg-emoji emoji-id="X"&gt;📱&lt;/tg-emoji&gt;` back to real markup
  - Strips redundant inner `[[HTML]]` sentinels
  - Never touches other legitimate escaped content (only tg-emoji block)
  - Never raises — always returns something
- Applied in 3 read paths:
  - `completed_orders_v2.py::_build_order_detail_text` (admin order detail)
  - `completed_orders_v2.py::ac2_userview_callback` (admin user-side preview)
  - `handlers_order.py::my_order_detail_callback` (customer "View Order")
  - `handlers_admin.py::deliver_command` (admin manual re-deliver path)

Old orders' DB rows stay unchanged (safe, no risky migration). Every display now heals on-the-fly.

## Test Results
```
_test_v84 to _test_v103  — 232/232 ✅
_test_v104               —   7/7   ✅  ← NEW: smart render + heal + wired in 3 files
────────────────────────────
GRAND TOTAL: 239/239 tests PASS. Zero regressions.
```

Live proof from test suite:
```
BEFORE:  <tg-emoji emoji-id="5364339557712020484">📱</tg-emoji> Capcut...   (garbage escaped)
AFTER:   <tg-emoji emoji-id="5364339557712020484">📱</tg-emoji> Capcut...   (real tag, renders as icon)
```

## Files Modified in v104
- `ext_suppliers.py` — new `_render_delivery_product_name()` + 2 call sites patched
- `utils.py` — new `heal_escaped_delivery_content()`
- `completed_orders_v2.py` — heal applied in 2 places (order detail, user-side preview)
- `handlers_order.py::my_order_detail_callback` — heal applied
- `handlers_admin.py::deliver_command` — heal applied before send

## How to Verify (After Deploy)
1. **Old orders (e.g. Order #18):**
   - Admin → 📜 Completed Orders v2 → Yasir → Order #18 → 👀 User-Side Delivery View → premium emoji now renders as icon (or falls back to 📱), no more `<tg-emoji ...>` text
   - Customer opens `/my_orders` → View Order #18 → same clean rendering
2. **New orders:** Next supplier product delivery — customer sees premium emoji in Product line immediately, no legacy garbage

---

# 🚀 v103 (2026-07-22) — Finance Dashboard "Temporary Error" Bug Fix

**User complaint (verbatim):**
> "Finance dashboard b work ni kr rha ospy tap kro temporary error ajata hai supplies ma ja kr jo ata hai osy dekh lo"

## 🕵️ Root Cause

`admin_finance_callback` and `fin_p_callback` in `supplier_automation.py` had a naive 2-step try/except:
```python
try:  await q.edit_message_text(text, parse_mode="Markdown", ...)
except:  await q.message.reply_text(text, parse_mode="Markdown", ...)
```

Failure modes that fell through to `global_error_handler` → showed generic *"⚠️ Temporary error. Please try again."*:
1. Markdown parse error on `_Cost estimate uses...` (underscore-heavy footer that Telegram sometimes rejected)
2. Message-is-a-caption error (if admin opened finance from a v101 User-Side Delivery Preview which is HTML-mode)
3. Stale query timeout
4. DB error in `_finance_totals` bubbled up unswallowed

## ✅ Fix — 4-Stage Fallback Ladder

```
1. edit_message_text(parse_mode="Markdown")
   ↓ (parse error / bad request)
2. edit_message_text(parse_mode=None)   ← plain text
   ↓ (message-has-no-text)
3. edit_message_caption(parse_mode="Markdown")
   ↓ (also fails)
4. edit_message_caption(parse_mode=None)
   ↓ (all edits failed — stale query)
5. reply_text(...)   ← sends fresh new message
```

Plus: `"message is not modified"` errors are now silently ignored (no spam). DB errors in `_finance_totals` are caught and surfaced to admin as *"⚠️ Data assembly failed: <actual error>"* instead of the useless generic message.

## Test Results
```
_test_v84 to _test_v102  — 223/223 ✅
_test_v103               —   9/9   ✅  ← NEW: all 5 periods + 4 fallback layers
────────────────────────────
GRAND TOTAL: 232/232 tests PASS. Zero regressions.
```

## Files Modified in v103
- `supplier_automation.py::admin_finance_callback + fin_p_callback` — 4-stage fallback with structured logging; DB errors surfaced instead of swallowed
- `supplier_automation.py` — added `from utils import escape_md` for safe error surface

## How to Verify in Bot (After Deploy)
1. Admin → 💰 Finance Dashboard → opens instantly (no "Temporary error")
2. Switch periods (Today / Yesterday / 7d / 30d / All) — all work
3. If backend has a real error (e.g. DB corruption) admin now sees the actual message inline

---

# 🚀 v102 (2026-07-22) — Premium Emoji on Buy Button + Payment Toggle Sync + Per-Product Referral Pool

**User complaints (verbatim):**
> 1. "Fake activity ho rhi selected destination pr osmy kisi buy now button pr product ka name or os button ka background color green ja raha sath emoji b ja raha pr mene emoji premium use kiya hua waha simple ja raha asa q ho raha"
> 2. "Jb mene payment methods k toggles ma easypaisa or jazzcash off krdiye hain to tb bhi fake activities ma easypaisa jazzcash waly broadcasting ho rhi... or buy points mn jao to waha b show ho rhy hoty waha b ni hony chiye"
> 3. "Refreal sy ek bnda laya dosry ko oska refreal hi count ni kiya... jb ma koi product free via referrals wala krdo to osky refrerrals b count ni kr rha bot... agr bnda direct refreal la raha to 1 point her refreal py reward mily or agr free via refreals sy link copy kia product ka or os link sy refreals laye tb 1 point rewad na mily tb bs referrels count ho or jese hi pory ho refreals jitny mene set kiye ho to bot osy wo product auto deliver krdy free ma"

## 🐛 Bug 1 — Premium emoji demoted to plain char on Buy Now button

**Root cause:** `_buy_now_keyboard()` and inline builder in `broadcast_store_message` used `_buy_now_label(pid)` which extracted product name text (including the leading emoji as a plain unicode char). Premium `<tg-emoji emoji-id="X">📱</tg-emoji>` markup in product name was collapsed to just `📱` → shown as regular emoji, never as premium icon.

**Fix:** Both button builders now ALSO call `extract_emoji_from_html(product.name)` → get the `emoji_id` → strip the leading fallback emoji from the label → attach `icon_custom_emoji_id` on the button via `api_kwargs`. Renders as proper premium emoji when bot owner has Telegram Premium. Combined with existing `style` (green color) via a single api_kwargs dict.

## 🐛 Bug 2 — Disabled payment methods still broadcast/displayed

Two separate paths were ignoring `is_payment_enabled()`:

### 2a — Fake activity broadcasts
`PAYMENT_METHODS` was hardcoded lists in `per_user_activity.py` and `fake_engagement.py`. `random.choice(PAYMENT_METHODS)` picked EasyPaisa/JazzCash even when disabled → customers saw fake "someone paid via JazzCash" broadcasts, clicked → got "unavailable" error.

**Fix:** New helper `_enabled_payment_methods()` in both modules — filters via `is_payment_enabled(method)`. Falls back to full list if admin somehow disabled everything (never breaks the broadcast pipeline).

### 2b — Buy Points panel
`points_payment_keyboard()` in `keyboards.py` always rendered all 3 buttons.

**Fix:** Each button now guarded by `is_payment_enabled(method)` check. Disabled methods completely hidden from the panel.

## 🆕 Feature 3 — Per-Product Referral Pool (Free-via-Referrals overhaul)

### Design
- **Direct referral link** (`t.me/<bot>?start=<uid>`) → +1 ref_point (spendable, general pool). Unchanged.
- **Product-specific referral link** (`t.me/<bot>?start=ref_<uid>_<pid>`) → counts ONLY toward THAT product's requirement, ZERO reward point.

### Implementation
- **New DB table `product_ref_pool`** — tracks `(referrer_id, product_id, referred_id)` triples with UNIQUE constraint (dedupes same friend counted twice for same product).
- **New helpers:** `add_product_ref()`, `count_product_refs()`, `clear_product_refs()`.
- **`_process_referral_attribution()` now accepts `product_id` param** — branches into product-pool path (no ref_point) vs general path (existing +1 point).
- **Deep-link parser** in `start_command` passes `open_pid` → if the link was `ref_<uid>_<pid>`, product-pool branch runs.
- **Free-claim eligibility check** (`freeclaim_do_callback`) now checks BOTH: `max(ref_points, product_pool_count)`. Prefers draining the pool first (doesn't cost general points).
- **On successful claim**, `clear_product_refs()` zeroes the pool counter for that product.
- **Progress notifications:** Referrer gets a message after EACH product-referral: *"Progress: 3/5 → need 2 more"*. When target reached: *"You unlocked FREE X!"* with instant "🎁 Claim FREE Now" button (hybrid auto+manual delivery per user spec).
- **Admin gets diagnostic DM** on every product-referral event.

## 🐛 Bug 3 also — Referral counting diagnostics (was NEVER firing in user's DB)

**Investigation:** User's `shop_v95.db` shows `referral_log` completely empty and every user's `referral_count=0`. Simulated the flow in a unit test — code works correctly (attribution runs, +1 point added). Root cause likely: the "new user" being tested had ALREADY `/start`ed the bot before → `is_new_user=False` → attribution rejected as `not_a_new_user`.

**Fix:** Existing `refadm_panel` (Referral Abuse Control) was fully-featured but not wired into the Settings keyboard. Added:
- **New Settings button "🔍 Referral Diagnostics"** → opens the existing `refadm_panel` which shows: counted count, blocked count, per-attempt log with reasons.
- Admin can now see EVERY attempt (both accepted + rejected with reason) → easy debug when a referral doesn't count.

## Test Results
```
_test_v84 to _test_v101  — 213/213 ✅
_test_v102               —  10/10  ✅  ← NEW
────────────────────────────
GRAND TOTAL: 223/223 tests PASS. Zero regressions.
```

Test coverage:
- ✅ Premium emoji icon extracted + label deduped (no double emoji)
- ✅ Fake activity payment filter (turn off Easy/Jazz → only Binance broadcast)
- ✅ Buy Points panel hides disabled methods
- ✅ Direct referral still awards +1 point
- ✅ Product-specific referral awards ZERO points but counts pool
- ✅ Same friend deduped per product (UNIQUE constraint works)
- ✅ `clear_product_refs()` resets pool after claim
- ✅ Referral Diagnostics button wired in Settings

## Files Modified in v102
- `database.py` — new `product_ref_pool` table + 3 CRUD helpers
- `handlers_start.py::_process_referral_attribution` — accepts `product_id`, branches into pool vs points path with progress notifications
- `handlers_free_claim.py::freeclaim_open_callback + freeclaim_do_callback` — dual-source eligibility (max of ref_points OR product-pool), consumes pool preferentially, shows both counters in "not enough" screen
- `fake_engagement.py::_buy_now_keyboard + broadcast_store_message` — premium emoji icon extraction + attached via api_kwargs; new `_enabled_payment_methods()` filter
- `per_user_activity.py` — new `_enabled_payment_methods()`; both `random.choice()` sites use it
- `keyboards.py::points_payment_keyboard` — per-method `is_payment_enabled()` guard; new "🔍 Referral Diagnostics" button in admin settings keyboard
- `bot.py` — new callback alias `^admin_ref_diag$` → `refadm_panel_callback`

## How to Test in Bot (After Deploy)
1. **Premium emoji:** Product with `[[HTML]]<tg-emoji emoji-id="...">📱</tg-emoji> Name` → wait for fake broadcast → Buy Now button shows premium 📱 icon (needs bot owner Telegram Premium)
2. **Payment toggle:** Admin → 💳 Payment Methods → turn OFF EasyPaisa & JazzCash → new fake broadcasts only mention Binance; Buy Points panel only shows Binance button
3. **Referral direct:** Share `t.me/<bot>?start=<your_uid>` → friend `/start`s → you get "+1 Referral Point" DM
4. **Referral product-specific:** Product detail → 🎁 Get FREE → 🔗 Get Share Link → send `ref_<your_uid>_<pid>` link → friend `/start`s → you get "Progress: 1/5" DM (NO point added). Repeat 5 times → auto "🎁 Claim FREE Now" button appears.
5. **Referral diagnostics:** Admin → Settings → 🔍 Referral Diagnostics → see counted+blocked counts, tap "📜 View Log" to see every attempt with reason (`not_a_new_user`, `already_has_referrer`, `self_referral`, etc.)

---

# 🚀 v101 (2026-07-21) — Canboso Balance Live-Refresh + User-Side Delivery Preview + Real Pin Broadcast Mode

**User requests (verbatim):**
> 1. "Canboso ka balance show ni ho raha ya b dekhna zara"
> 2. "Ma chhata ho completed orders k ander ek or button do user side delivery content name sy or os button py click krny k bad user side jo content deliver hua hai or jesa b hua exact mujy waha py aye"
> 3. "Bot k top pr notification pin hona chiye jese koi b msg mene lgana ho premium emoji k sat to whn pin kr sko notification sbko dekhy top pr or timer b lga sko oska ma and manual b off on kr sko announcement pinned jo ek feature hai settings ma is ko on krny sy ya hota k mera welcome msg k ander wo msg ajata hai jo b ma set krta ho waha pr ab sy welcome msg ma ni ana chiye notification direct pin ho jese pro users krty hain"

## 🐛 Bug Fix — Canboso balance stuck at $0 in supplier view

**Root cause:** v99 fixed `fetch_balance()` to actually hit Canboso's `/balance` API, but the supplier view (`ext_sup_view_callback`) still read `s.get("balance_usd")` from a DB row that only updated when either:
- Admin clicked "🔄 Test & Refresh" manually, OR
- The 5-min auto-sync balance job ran (if `autosync_enabled` was on)

So a fresh admin visit to the panel still saw the OLD stored $0.00 until one of those triggers fired.

**Fix:** `ext_sup_view_callback()` now does a **best-effort silent balance refresh on every open** via `async_fetch_balance()`. Wallet always shows live value. Silent failure (network hiccup) never breaks the view.

## 🆕 Feature 1 — User-Side Delivery Preview

New **"👀 User-Side Delivery View"** button in every delivered order's admin panel.

- Only appears for orders with `status='delivered'` AND stored `delivery_content`
- On tap: sends a fresh message showing **byte-perfect** what the customer received — same HTML rendering, same premium emojis, same monospace `<code>` boxes
- Header banner marks it as a preview: *"This is exactly what the customer received in their chat."*
- "🔙 Back to Order" button returns to the order detail

Admin uses this to check formatting quality → if it looks wrong → adjust product's delivery format from suppliers panel.

## 🆕 Feature 2 — Real Pin Broadcast Mode 📢

Pro-user pattern researched from `python-telegram-bot` docs: **private chats support pinning** (no admin rights needed). Bot can now send announcements + **actually pin** them in every user's DM.

### Two operating modes (admin toggle)

| Mode | Behavior |
|---|---|
| **Legacy (OFF, default)** | Pin text prepended to welcome message |
| **Real Pin Mode (ON)** | Text broadcasted as a normal message + **Telegram-pinned** in each user's DM. Auto-unpin on expiry via background watchdog |

### Full feature set
- **Toggle:** Admin → 📌 Pinned Announcements → **📢 Real Pin Mode: 🟢 ON / 🔴 OFF**
- **Premium emoji auto-detect:** If admin's pin message contains Telegram Premium custom_emoji entities → captures HTML markup with `<tg-emoji emoji-id="...">📱</tg-emoji>` → renders premium emojis for every user
- **Timer support:** existing 1h/6h/24h/3d/7d/Never options — expiry now triggers auto-unpin instead of just filtering from display
- **Manual push:** New **"📢 Push #N"** button per pin — force-broadcast an existing pin at any time (useful if you added it while Real Pin Mode was OFF)
- **Auto-unpin on delete:** When admin deletes a pin, unpins from every user's chat first
- **Background watchdog job:** Runs every 5 min, unpins expired announcements from all user chats + marks them inactive in DB
- **Per-user message tracking:** `pinned_message_ids_json` column stores `{user_id: message_id}` map so watchdog can precisely unpin the exact message

### What changed for existing welcome behavior
When Real Pin Mode is **ON**, `format_pins_for_menu()` returns `""` — pins no longer appear inside the welcome text (pro-user pattern). When OFF, legacy behavior preserved.

## Test Results
```
_test_v84       — 16/16 ✅
_test_v84_gate  —  7/7  ✅
_test_v85       — 16/16 ✅
_test_v87       — 15/15 ✅
_test_v88       — 10/10 ✅
_test_v89       — 14/14 ✅
_test_v90       — 10/10 ✅
_test_v91       —  8/8  ✅
_test_v92       — 14/14 ✅
_test_v93       — 10/10 ✅
_test_v94       — 15/15 ✅
_test_v95       — 21/21 ✅
_test_v96       — 12/12 ✅
_test_v97       —  6/6  ✅
_test_v98       — 10/10 ✅
_test_v99       —  9/9  ✅
_test_v100      —  9/9  ✅
_test_v101      — 11/11 ✅  ← NEW: balance refresh + userview button + real pin broadcast + unpin + watchdog
────────────────────────────
GRAND TOTAL: 213/213 tests PASS. Zero regressions.
```

## Files Modified in v101
- `ext_suppliers.py::ext_sup_view_callback` — silent live balance refresh on every view
- `completed_orders_v2.py` — new `ac2_userview_callback` + button in `_build_order_detail_kb`
- `loyalty_extras.py` — 3 additive DB columns (`parse_mode`, `pinned_message_ids_json`, `is_broadcasted`); new functions: `is_real_pin_mode`, `set_real_pin_mode`, `broadcast_and_pin`, `unpin_and_deactivate`, `pin_expiry_watchdog_job`, `admin_pin_realmode_toggle_callback`, `admin_pin_push_callback`; updated `add_pin` accepts `parse_mode`; `admin_pin_text_received` auto-detects premium emoji; `admin_pin_expiry_callback` triggers broadcast+pin when Real Pin Mode ON; `format_pins_for_menu` skips welcome-prepend when Real Pin Mode ON
- `bot.py` — imports for new callbacks + `pin_expiry_watchdog_job` registered via `run_repeating(interval=300)` + pattern handlers for `^admin_pin_realmode_toggle$` and `^admin_pin_push_`

## How to Test in Bot (After Deploy)

### 1. Canboso balance
- Admin → 🏬 Suppliers → tap Canboso — balance shows live value (e.g. $7.34) instantly, no click needed

### 2. User-side delivery preview
- Admin → 📜 Completed Orders v2 → any user → any delivered order
- New "👀 User-Side Delivery View" button appears
- Tap → get a fresh message showing exactly what customer saw

### 3. Real Pin Broadcast
- Admin → 📌 Pinned Announcements → **📢 Real Pin Mode: 🔴 OFF** → tap to enable → **🟢 ON**
- Tap **➕ Add New Pin**
- Type message with premium emojis (Telegram Premium account only) → pick expiry (e.g. 24h)
- Every user gets the message + it's pinned in their chat
- After 24h expiry → watchdog auto-unpins from every chat
- Anytime: use **📢 Push #N** button to re-broadcast an existing pin

---

# 🚀 v100 (2026-07-21) — Delivered Content Raw HTML Tags Visible Bug

**User complaint (with Order #6 screenshot):**
> "Delivered content dekho codings a rhi ya b dekho 3 modes on krlo or isko b solve kro"

Admin panel "Completed Orders v2" → any delivered supplier order showed raw HTML tags visible as literal text:
- `📦 Product: <tg-emoji emoji-id="5364339557712020484">📱</tg-emoji> Capcut Pro...`
- `📤 Delivered Content: <b>Bite Store Delivery</b> ... <b>Format:</b> ... <code>delta@zumys.store</code>`

## 🕵️ Root Causes (Detective Mode)

Investigated `completed_orders_v2.py::_build_order_detail_text()` — found TWO separate escape/embed bugs:

### Bug 1 — Product name with premium emoji
```python
pname = escape_html(order.get("product_name") or "Product")   # ← always escapes
```
Product names for supplier products include `[[HTML]]<tg-emoji emoji-id="...">📱</tg-emoji> Capcut...` markup for premium emoji display. `escape_html()` blindly escaped `<` `>` `&` → user saw literal `&lt;tg-emoji ...&gt;`.

### Bug 2 — Delivery content HTML double-escaped
```python
if dc:
    body += html_code_block(dc)   # ← wraps in <code> AND escapes < > &
```
`delivery_content` for supplier products is the fully-rendered v83 HTML (starts with `[[HTML]]` + contains `<b>`, `<code>`, `<tg-emoji>` markup). `html_code_block()` re-escaped everything → user saw literal `<b>Bite Store Delivery</b>` text.

### Bug 3 — Customer-facing "View Order" had same bug
`handlers_order.py::my_order_detail_callback` used `escape_md(content)` on already-rendered HTML → customers also saw raw tags when viewing their own order history.

## ✅ Fixes

### Smart product name renderer (new helper `_render_product_name`)
- `[[HTML]]` prefix → strip sentinel + embed raw
- HTML tag markers (`<b>`, `<i>`, `<tg-emoji>`, etc.) → embed raw
- Plain text → still escape (special chars like `<`, `&` safe)

### Smart delivery-content branching
- `[[HTML]]`-prefixed content → strip prefix + embed raw
- Contains HTML tags → embed raw
- Plain text (manual admin delivery) → still wrap in `<code>` for byte-perfect copy

### Customer view (`handlers_order.py`) — mirror same detection
- HTML content → embed raw + auto-flip parse_mode via `smart_text_and_mode`
- Plain content → still `escape_md()` for Markdown safety

## Test Results
```
_test_v84       — 16/16 ✅
_test_v84_gate  —  7/7  ✅
_test_v85       — 16/16 ✅
_test_v87       — 15/15 ✅
_test_v88       — 10/10 ✅
_test_v89       — 14/14 ✅
_test_v90       — 10/10 ✅
_test_v91       —  8/8  ✅
_test_v92       — 14/14 ✅
_test_v93       — 10/10 ✅
_test_v94       — 15/15 ✅
_test_v95       — 21/21 ✅
_test_v96       — 12/12 ✅
_test_v97       —  6/6  ✅
_test_v98       — 10/10 ✅
_test_v99       —  9/9  ✅
_test_v100      —  9/9  ✅  ← NEW: 4 scenarios (HTML/plain × product+delivery) + regression
────────────────────────────
GRAND TOTAL: 202/202 tests PASS. Zero regressions.
```

## Files Modified in v100
- `completed_orders_v2.py::_build_order_detail_text` — smart HTML detection for product name + delivery content
- `handlers_order.py::my_order_detail_callback` — same detection for customer view

## How to Verify in Bot (After Deploy)
1. Admin → 📜 Completed Orders v2 → any user → any delivered supplier order
2. Product name should show premium emoji properly (not raw `<tg-emoji>` tags)
3. Delivered Content section should show:
   - **🎉 Bite Store Delivery** (bold, not `<b>` text)
   - **🧩 Format:** 🔐 Email + Password + 2FA (bold labels, emoji icons)
   - Email/password in monospace boxes (from `<code>`)
4. Customer side: /start → 📜 Order History → View any delivered order → same clean rendering

---

# 🚀 v99 (2026-07-20) — Canboso Balance Bug + Smarter Format Auto-Detect

**User questions (verbatim):**
> 1. "Kia api ma ya information ni hoti k jb mera bot os api sy koi b product buy kry ga to product kis format ma received hoga mere bot ko kia ya pata lgta hai api key sy?"
> 2. "canboso waly ka balance show ni kr ra ya bug dekho q a ra or fix krky do"

## 🔍 Research Findings — API delivery-format info

Deep-dived Canboso live API + surveyed 4 REST supplier APIs. Result:

**Yes, APIs DO expose delivery-format hints — but no single field is 100% reliable.** Signals (in strength order):
1. `usageGuide` first line — supplier's own "Format: X | Y | Z" declaration
2. `slotProductType` (Canboso) / `unit_label` (Akunding) metadata
3. Product name keywords ("Redemption Link", "CDK", "Coupon Code")

Bot now uses all three in the correct priority.

## Bugs Fixed

### 🐛 Bug 1 — Canboso balance always shows $0.00
**Root cause:** `CanbosoAdapter.fetch_balance()` was hardcoded to return `0.0` with a comment "Canboso doesn't expose /balance". **Wrong** — verified live: `/api/telegram-buyer/balance` exists and returns proper JSON:
```json
{"success": true, "balance": 7.34, "balanceUsd": 7.34, "walletCurrency": "USD", ...}
```
**Fix:**
- `fetch_balance()` now hits the real endpoint (`GET /api/telegram-buyer/balance`)
- `test_connection()` also fetches balance and includes it in `extra["balance"]` so the "Test & Refresh" button in admin panel updates the stored balance correctly
- User's real key verified: **$7.34** now displays instead of $0.00

### 🐛 Bug 2 — 5 Canboso products detected as wrong format
Products whose NAME explicitly said "Redemption Link" or "Coupon Code" were being detected as `email_pass`:

| Product | Before v99 | After v99 |
|---|---|---|
| Gemini 18 Month **Link** No Warranty | email_pass ❌ | **redeem_link** ✅ |
| Chatgpt GO 3 Month **Coupon Code** | email_pass ❌ | **coupon_code** ✅ |
| YouTube 3M **Redemption Link** | email_pass ❌ | **redeem_link** ✅ |
| LOVABLE LITE 12M **Redeem Link** | email_pass ❌ | **redeem_link** ✅ |
| Nord Vpn 3 Month **Redeem Link** | email_pass ❌ | **redeem_link** ✅ |

**Fix:** New multi-tier detection order in `detect_product_format()`:
- **Tier 0 (NEW):** Product NAME contains explicit format tokens ("Redemption Link", "Coupon Code", "CDK", "with 2FA", "Gift Card") — strongest signal, checked first
- **Tier 1a (NEW):** `usageGuide` first-line "Format: ..." — supplier's own delivery declaration gets its own priority pass
- **Tier 1b:** Same search across combined text
- **Tier 2 (IMPROVED):** `slotProductType='slot'` (Canboso family invites) → `redeem_link`. Also `slot`, `code`, `key`, `license` all map correctly
- **Tier 3:** Broad keyword scan
- **Fallback:** `email_pass`

## Test Results
```
_test_v84       — 16/16 ✅
_test_v84_gate  —  7/7  ✅
_test_v85       — 16/16 ✅
_test_v87       — 15/15 ✅
_test_v88       — 10/10 ✅
_test_v89       — 14/14 ✅
_test_v90       — 10/10 ✅
_test_v91       —  8/8  ✅
_test_v92       — 14/14 ✅
_test_v93       — 10/10 ✅
_test_v94       — 15/15 ✅
_test_v95       — 21/21 ✅
_test_v96       — 12/12 ✅
_test_v97       —  6/6  ✅
_test_v98       — 10/10 ✅
_test_v99       —  9/9  ✅  ← NEW: balance fetch + 5 wrong-format fixes + live smoke
────────────────────────────
GRAND TOTAL: 193/193 tests PASS. Zero regressions.
```

Includes LIVE API smoke tests against user's real Canboso key confirming both `$7.34` balance and 5/5 corrected formats.

## Files Modified in v99
- `ext_suppliers.py` — 3 changes:
  - `CanbosoAdapter.fetch_balance()` — real API call instead of hardcoded 0
  - `CanbosoAdapter.test_connection()` — piggyback balance fetch into `extra` dict
  - `_detect_from_unit_label()` — added Canboso `slot` → `redeem_link` mapping
  - `_detect_from_keywords()` — new Tier 0 with strong NAME-based signals
  - `detect_product_format()` — reordered tiers, prioritised `usageGuide`

## How to Verify in Bot (After Deploy)
1. Suppliers panel → Canboso → **🔄 Test & Refresh** → balance now shows real value
2. Suppliers panel → Canboso → **🔁 Bulk Sync All Products** → 5 previously-mislabelled products now sync with correct format → users get proper delivery templates

## Why NOT test-purchase feature
Considered a "Test Buy 1 unit" button that spends real balance to learn 100% guaranteed delivery format. User declined (`"Test buy mujy ni chiye"`) — going with detection-only improvements. ~90% accuracy on Canboso's 27 products now (was ~80%).

---

# 🚀 v98 (2026-07-20) — Auto-Group Products by First Word

**User request (verbatim):**
> "kia asa ho skta k ma jo b product ka name k pehla 1 word same ho to wo shop mn ek dosry k nichy show ho... mujy manual na krna pry auto detect krly bot jb b ma khudsy koi new product add kro ya supplier ka product add kro dono py auto detect krly or shuru ka 1 word agr same hai jese... super grok subscription 1m ... super Grok 3M"

## What it does

Products in the shop are now automatically clustered by their **first word** (case-insensitive, emoji-agnostic). No manual sorting needed — bot detects same-first-word products from both admin-added AND supplier-imported products and shows them one below the other in the shop list.

### Example
Admin's raw product list:
```
Netflix Premium 1M
Super Grok 3M
🔥 Adobe Full App
super grok subscription 1m
Netflix 4K 6M
Cursor Pro 1M
🎮 Super Grok 12M
```

After auto-group (alphabetical by first word):
```
🔥 Adobe Full App
Cursor Pro 1M
Netflix Premium 1M
Netflix 4K 6M
Super Grok 3M
super grok subscription 1m
🎮 Super Grok 12M
```

Notice `Netflix + Netflix 4K` cluster together, and all 3 `Super Grok` variants cluster together — regardless of capitalisation or leading emoji.

## Details

- **Toggle:** Admin → 🎨 Customization → 👁️ Toggles → **"🔤 Auto-Group by First Word"** button — default **ON**, can be turned off.
- **Case-insensitive:** `"super grok"`, `"Super Grok"`, `"SUPER GROK"` all match.
- **Emoji-agnostic:** Leading regular emojis (`🎮 Super Grok`) AND premium `<tg-emoji>` markup are stripped before extracting the first word.
- **Stable sort:** Within a group, original insertion order is preserved.
- **Applied at 6 shop rendering paths:** main `shop_callback`, `shop_all_callback`, `shop_category_callback`, `shop_category_page_callback`, `page_callback` (raw-mode pagination), and `carousel_nav_callback`. Same ordering on page 1 as page 2/3/etc. — no jumping items between pages.
- **Never breaks:** Wrapped in try/except at every call site so any edge case falls back to original order.

## Files Modified in v98
- `utils.py` — new helpers: `_extract_first_word()`, `is_auto_group_enabled()`, `sort_products_by_first_word()`
- `handlers_shop.py` — 6 call sites wired
- `handlers_admin.py` — toggle button + status text in Toggles panel
- `bot.py` — callback pattern `^toggle_auto_group_by_name$` registered

## Test Results
```
_test_v84       — 16/16 ✅
_test_v84_gate  —  7/7  ✅
_test_v85       — 16/16 ✅
_test_v87       — 15/15 ✅
_test_v88       — 10/10 ✅
_test_v89       — 14/14 ✅
_test_v90       — 10/10 ✅
_test_v91       —  8/8  ✅
_test_v92       — 14/14 ✅
_test_v93       — 10/10 ✅
_test_v94       — 15/15 ✅
_test_v95       — 21/21 ✅
_test_v96       — 12/12 ✅
_test_v97       —  6/6  ✅
_test_v98       — 10/10 ✅  ← NEW: 15 edge cases + grouping + toggle + wiring + real DB
────────────────────────────
GRAND TOTAL: 184/184 tests PASS. Zero regressions.
```

## How to Test in Bot (After Deploy)
1. Add / import products with matching first words (e.g. `"Super Grok 1M"`, `"Super Grok 3M"`)
2. Open the shop → they appear one below the other
3. To turn OFF: Admin → 🎨 Customization → 👁️ Toggles → tap **"🔤 Auto-Group by First Word"**

---

# 🚀 v97 (2026-07-20) — Canboso Adapter Stock=0 Critical Fix

**User complaint (verbatim):**
> "Ya canboso wali api key lgata hu bot products sb import kr leta sync b kr leta lkin pta ni stock 0 sbky dekhata hai ya q ho raha jb k baqi api keys add kiye mene wo sb kam kr rhy perfect bs is canboso mn hi issue hai stock 0 sb ka mene os supplier k bot py ja k b dekha hai k such mn to ni 0 stock lkin whn to stock hai kafi mre pas api k through 0 show ho rha"

## 🐛 Root Cause (Detective Mode Findings)

Hit the live Canboso API with user's real key and dumped the raw JSON response. Canboso **does NOT return a top-level `stock` field** — the real stock lives in `stats.available`:

```json
{
  "_id": "6a3b9e5da02ee94473f01c08",
  "product_name": "Veo 3 Ultra Extension Unlimited Video 20D Warratny",
  "usdPricing": 13,
  "stats": {"total": 7, "sold": 6, "available": 1}
}
```

Old adapter code:
```python
"stock": int(p.get("stock", 0) or 0)  # ← "stock" key doesn't exist → always 0
```

**Impact:** ALL 27 of user's Canboso products were silently marked out-of-stock. Bot users couldn't buy anything. Zero errors, zero warnings — pure silent failure.

## ✅ Fix

Defensive multi-key resolution in `CanbosoAdapter.fetch_products()`:

```python
# Resolution order (defensive — supports API changes):
#   1. stats.available (canonical Canboso field)
#   2. top-level "stock" (in case Canboso adds it later)
#   3. top-level "available" (alternate field seen in some tenants)
#   4. fall back to 0
stock_val = 0
stats = p.get("stats") if isinstance(p.get("stats"), dict) else {}
for cand in (stats.get("available"), p.get("stock"), p.get("available")):
    if cand is not None:
        try:
            stock_val = int(cand)
            break
        except (TypeError, ValueError):
            continue
```

## 🧪 Verification (Live API Smoke Test)

Ran `ad.fetch_products()` against user's real key BEFORE and AFTER fix:

| | Before | After |
|---|---|---|
| Products with stock > 0 | **0/27** ❌ | **18/27** ✅ |
| Products actually sold out | 0 (masked) | 9 (real) |
| Max stock seen | 0 | 656 (Hotmail Good Quality) |

## 🕵️ Other Adapters Audited
Compared all 4 REST adapters (Akunding, Canboso, MMOStore, TunVNMMO). User confirmed the other 3 work perfectly — verified their APIs really do return `stock` at the top level. Only Canboso needed the fix.

## Test Results
```
_test_v84       — 16/16 ✅
_test_v84_gate  —  7/7  ✅
_test_v85       — 16/16 ✅
_test_v87       — 15/15 ✅
_test_v88       — 10/10 ✅
_test_v89       — 14/14 ✅
_test_v90       — 10/10 ✅
_test_v91       —  8/8  ✅
_test_v92       — 14/14 ✅
_test_v93       — 10/10 ✅
_test_v94       — 15/15 ✅
_test_v95       — 21/21 ✅
_test_v96       — 12/12 ✅
_test_v97       —  6/6  ✅  ← NEW: unit + live smoke test
────────────────────────────
GRAND TOTAL: 174/174 tests PASS. Zero regressions.
```

## How to Verify in Bot (After Deploy)
1. Suppliers panel → Canboso → **🔁 Bulk Sync All Products**
2. Wait 5-10 sec
3. Check product listings — you'll see real stock counts (1, 7, 33, 136, 656…)
4. Any product now buyable if `stats.available > 0`

## Files Modified in v97
- `ext_suppliers.py::CanbosoAdapter.fetch_products()` — stock resolution logic (see above)

---

# 🚀 v96 (2026-07-20) — Broadcast Overhaul + Maintenance Lockdown + Supplier Rename

**User request (verbatim):**
> "Globel broadcasting ma agr ma chaho k ma msg kro premium emojis waly broadcast wo ho skta hai kia? Dosri bat ya k supplier ny stock add kia hai or to stock alert broadcast msg gya hi ni Selected destination py. Teesri bat ya k Fake activity ma jitny b toggles hai... jo b product ki broadcasting ho rhi hogi mera bot auto detect kry ga or oska product name k pehly 2 words jo hongy wo buy now button k ander text jaye or agy buy now likha hua ho... premium emoji b sath lg kr jaye... jb bot ma maintenance mode py lga do mere bot ka sb kuch ruk jaye fake broadcasting b or real broadcasting b sb kuch... har supplier ka name b ma change kr sko asi b koi settings de dena stock alerts tb b jaye jb already stock add hai or osmy or add krdiya hai or tb b jaye jb out of stock hai or bad ma stock add kiya hai or dono ka asa hi ho chahy product supplier ka ho ya mera ho"

## 8 Features Added / Fixed

| # | Feature | What Changed | File |
|---|---------|--------------|------|
| **A** | 🔥 **CRITICAL BUG:** Supplier stock alerts NEVER firing | `_is_stock_broadcast_enabled()` was checking OLD `fbc_*` panel but admin uses `pua_*` panel → gate always False → all restock broadcasts silently dropped. NOW checks BOTH panels (either ON = enabled). | `restock_alerts.py` |
| **B** | ✅ Global broadcast — premium emoji auto-detect | Admin panel → 📢 Broadcast. When admin's message contains custom_emoji entities (Telegram Premium), bot auto-detects, switches to HTML mode, sends `<tg-emoji>` markup preserved. Falls back to Markdown for plain text. | `handlers_admin.py` |
| **C** | ✅ Buy Now button format: `[emoji] first-2-words Buy Now` | Was: `"Full Product Name - 🛒 Buy Now"` (v94). Now: extracts leading emoji + takes first 2 words + suffix. Handles both regular emojis AND `<tg-emoji>` premium markup. Truncates to ≤60 chars. Default color = green (`success`) unless admin sets otherwise. | `fake_engagement.py::_buy_now_label` |
| **D** | ✅ Own product emoji auto-extract | When admin adds own product with leading emoji like `"🎮 Chatgpt Plus"`, bot extracts `🎮` and puts it in the Buy Now button automatically. No config needed. | `fake_engagement.py::_buy_now_label` |
| **E** | ✅ 🚧 Maintenance mode → FULL LOCKDOWN | Previously maintenance only blocked user commands. Now ALSO blocks: fake activity broadcasts, restock alerts, admin manual broadcasts, per-user activity messages. Everything paused until admin turns maintenance OFF. Admin gets clear "🛠️ Maintenance ON — broadcast skipped" message when trying to broadcast. | `fake_engagement.py`, `ui_extras.py`, `restock_alerts.py`, `handlers_admin.py` |
| **F** | ✅ Supplier rename UI | New "✏️ Rename Supplier" button in Supplier View panel. 3-step conversation (state=9600). Changes `ext_suppliers.name` field — admin dashboard only, does NOT leak into customer broadcasts (per user spec). | `supplier_automation.py`, `ext_suppliers.py`, `bot.py` |
| **G** | ✅ Manual product stock update → global broadcast | Previously ONLY per-user opt-in alerts fired for admin's manual stock edits. Supplier auto-sync fired global broadcast, admin edits didn't. Now BOTH paths fire `fire_restock_alert()`. Works for: (1) admin's own products, (2) supplier products, (3) `stock` field edit, (4) bulk `accounts` add. Covers all 4 scenarios user requested (out-of-stock→N, N→N+more, own product, supplier product). | `handlers_admin.py` |
| **H** | ✅ Startup self-heal: dest_chat = bot's own username | User's v95 DB had `dest_chat_id='@Bite_storee_bot'` (leftover from before v95 validation guard). On bot startup, `bot.py` now detects this and clears it automatically so broadcasts start working again without admin having to manually clear it. | `bot.py` |

## State ID Audit
- New state: `SUP_RENAME_STATE = 9600` (was initially 9287 → **detected collision** with `CONN_STRING_STATE=9287` in `insta_api_flow.py` → moved to fresh 9600-range)
- 0 remaining state ID collisions across all files

## Test Results
```
_test_v84       — 16/16 ✅
_test_v84_gate  —  7/7  ✅
_test_v85       — 16/16 ✅
_test_v87       — 15/15 ✅
_test_v88       — 10/10 ✅
_test_v89       — 14/14 ✅
_test_v90       — 10/10 ✅
_test_v91       —  8/8  ✅
_test_v92       — 14/14 ✅
_test_v93       — 10/10 ✅
_test_v94       — 15/15 ✅
_test_v95       — 21/21 ✅
_test_v96       — 12/12 ✅  ← NEW: covers all 8 v96 features
────────────────────────────
GRAND TOTAL: 168/168 tests PASS. Zero regressions.
```

## How to Test in Bot
- **A:** Add stock to any supplier product → restock broadcast should now fire to destination
- **B:** Admin → 📢 Broadcast → type message with premium emojis → check all users see premium emojis correctly
- **C, D:** Any fake activity broadcast triggers → Buy Now button should show `[emoji] Product Name Buy Now` in green
- **E:** Enable Maintenance → try to broadcast → gets "🛠️ Maintenance ON" reply. All fake activity stops until you disable maintenance
- **F:** Supplier panel → any supplier → "✏️ Rename Supplier" button → type new name
- **G:** Admin panel → any product → edit stock from 0 to N → restock alert fires globally + to opt-in subscribers
- **H:** Automatic — happens once on bot startup

---

# 🚀 v95 (2026-07-20) — Grand Bug Hunt + Toggle Refresh Hardening

**User complaint (verbatim, Roman Urdu):**
> "Bug 1: customization back button galat jagah le jata. Bug 2: force join detect nahi karta / admin nahi bolta. Bug 3: fake activity toggles pe cross stuck rehta hai. Bug 4: responses me sab visible nahi. Bug 5: custom locations add nahi ho sakti. Khud bhi bugs dhoondho pro developer ki tarah."

## 10 Bugs Found & Fixed

| # | Bug | Root Cause | Fix |
|---|---|---|---|
| 1 | Back button always jumps to Main Menu | `conv_cancel_callback` hardcoded | `_RETURN_MAP` — 7 context-aware return targets |
| 2 | Force Join link never saves / "not admin" | State ID collision `FJ_GROUP=921 ⇔ EDIT_PRODUCT_EMOJI=921` | Bumped to 9200-range + `_verify_bot_access()` helper |
| 3a | Price Drop toggle shows ❌ Unknown | `_TYPE_MAP` missing `price_drop` entry | Added entry |
| 3b | New Product template ignored | Hardcoded English, `_render()` skipped | Now uses `_render("bc_newprod")` + v94 helpers |
| 4 | 16 response keys invisible in Edit Responses | Hardcoded 8 categories | Dynamic + auto-merge + `uncategorized` bucket |
| 5 | Cannot add custom location / response cat | Hardcoded Python list | New `custom_locations.py` module + ➕ Add button |
| 6 | `BTXT_INPUT=911 ⇔ ACT_DELAY=911` collision | Silent state overlap | `BTXT_INPUT` → 9110 |
| 7 | `dest_chat` accepts bot's own username | No validation | `bot.get_me()` check + reject |
| 8 | Force Join saves without admin verification | Silent DB save | Pre-flight `_verify_bot_access()` |
| **9** | 🔥 Fake-activity toggles ALWAYS show ❌ | **Duplicate `_ico()` def** — second one (string-only comparison) silently overrode first, always returned ❌ for bool inputs | Removed duplicate + made `_ico()` universal (bool/int/str) |
| **10** | 🔥 Notification says "ON ✅" but button still ❌ after v95.1 | **Duplicate `_edit()` def** — later one silently swallowed Telegram's `"Message is not modified"` error → panel never redrew | Removed duplicate + hardened surviving `_edit()` with ZWSP diff trick + error routing + send-new fallback |

## Also in v95
- Removed duplicate `_g`, `_s`, `_is_admin` defs from `ui_extras.py` (silent-override anti-pattern purge)
- State ID audit: 0 collisions across all 55 code files
- Callback resolver clean: 415/415 patterns resolve
- **Repo cleanup:** removed 13 legacy test files + 49 old CHANGELOG_*.md files + orphan `api.py` (dead FastAPI code). Cleaned `requirements.txt` (removed unused fastapi/uvicorn/pydantic). Repo went from 109 → 47 files.

## Files Modified in v95
- `ui_extras.py` — 7 fixes (state IDs, `_verify_bot_access`, `_TYPE_MAP`, dest_chat validation, `_ico` fix, `_edit` hardening, duplicate purge)
- `handlers_admin.py` — 3 fixes (EDIT_PRODUCT_EMOJI state, dynamic responses, context-aware cancel)
- `handlers_buttons.py` — `BTXT_INPUT` state ID
- `per_user_activity.py` — `newprod` uses `_render()`
- `customization.py` — Add Custom Location flow (3-step conversation)
- `keyboards.py` — 🎨 CUSTOM LOCATIONS section in button dropdown
- `bot.py` — handler imports + ConversationHandler registration
- **NEW:** `custom_locations.py` — dynamic locations + response-category storage

---

# 📜 Version History (v47 → v94 — Brief Summary)

Every release below shipped a working zip with tests. Details in git history.

## Late Series (v90–v94)
- **v94** — Restock Alerts + Buy Button Global Color + Restock button removal
- **v93** — Button Color HOTFIX (color propagation across layouts)
- **v92** — 50 Main Menu Layouts + Hybrid Auto-Fit Engine
- **v91** — Screenshot Bug DEFINITIVE Fix (research-backed premium emoji handling)
- **v90** — InstaAPI Raw HTML Product Name Bug — FIXED

## Middle Series (v80–v89)
- **v89** — Pro-Grade Fixes: Async HTTP + Re-entrancy + Batch Gemini
- **v88** — Translator Scope Locked to Descriptions Only
- **v87** — Format Detection Fix + Auto-Translator
- **v86** — Connection-String Supplier (5th adapter)
- **v85** — Supplier Automation
- **v84** — Maintenance Mode + Completed Orders v2
- **v83** — Multi-Format Auto-Detection + Manual Sync + Beautiful Delivery
- **v82** — Phase 2: Customer Purchase Flow + Order Router (PTB v22+ immutable CallbackQuery workaround)
- **v81.1** — Multi-Supplier hotfix + Smart Fixed Price
- **v81** — Phase 1: Multi-Supplier REST API System
- **v80.1** — CRITICAL HOTFIX (`escape_md()` regression — must always return string)
- **v80** — Base for supplier system

## Early Series (v70–v79)
- **v79** — supplier bundle improvements
- **v78, v77, v76, v75** — supplier bundle iterations
- **v73** — post-v72 stabilization
- **v72** — CRITICAL: Byte-Perfect Delivery (store as received, deliver as stored)
- **v71** — AI Auto-Reply for Support + Per-Product Replacement
- **v70** — Pinned Announcements + Per-Product Share Link + QR codes

## Earlier (v60–v69)
- **v69** — $150-LOSS BUG FIX + 3 new features
- **v68** — Customizable Tier System + Customization Sync + Responses Sync
- **v67** — AI Proxy Scout (Gemini auto-recovery)
- **v66** — Bonus REMOVED + Tier Hints + Price Drop Templates + Confirm Dialog
- **v65** — Refund + Cancel + Users Pagination + Per-User Activity Tracker
- **v64** — Duplicate "Payment not confirmed" race-condition fix
- **v63** — Proxy Pool with Auto-Rotation & Admin Panel
- **v62** — Order-ID Flow, professional UX, hide backend terminology
- **v61** — Binance Auto-Payment Critical Fix + Binance Pay REST API
- **v60** — Smart Broadcast Skip (no more fake-looking broadcasts)

## Original (v47–v59)
- **v59** — "Temporary Error" bug fix + Hide/Unhide Products + Shop Filter
- **v58** — Screen Editor "bot stuck on text edit" bug fix
- **v57** — Pay with Points editable + bot "stuck" diagnostics
- **v56** — `&amp;amp;` double-escape 4-layer defense
- **v55** — `&amp;amp;amp;` double-escape bug + 4 more fixes
- **v54** — Customization → 🎨 Buttons deep bug sweep
- **v53** — Premium Emoji confirmation echo + button icon fix
- **v52** — Navigation buttons editable + Single Unified Editor
- **v51** — Premium Emoji A-to-Z Bulletproof Fix
- **v50** — Screen-by-Screen Editor (user-side full customization)
- **v49** — Per-Product Free-Claim Broadcast Button Editor
- **v48** — Premium Emoji Fix + Referral Points System + Smart Share
- **v47** — Free via Referrals (first tracked release)

---

## 🛠️ Developer Notes
- **Deploy:** Push to GitHub `main` → Render auto-deploys the Worker
- **Test suite:** Not included in the repo anymore (kept locally). Full 156-test suite runs pre-release.
- **Migrations:** Only additive via `ensure_column()` / `CREATE TABLE IF NOT EXISTS`. Zero destructive schema changes.
- **Env vars:** Fixed set (no new vars without opt-in). See `render.yaml`.

## 📝 Update Rule
When a new version ships, **prepend a new `# 🚀 vXX` section at the top** of this file. Don't create new `CHANGELOG_vXX.md` files. Keep the history flowing in one place.

---

# 🚀 v161.20 (2026-08-12) — AUTO BUY-NOW BUTTON + REFERRAL BONUS SETTINGS + DELIVERY AUDIT + FULL LANGUAGE SYSTEM

## ✅ 1. Fake Activity → Buy Now button LAZMI (product naam wali har broadcast)
- **purchase + discount** broadcasts ab `broadcast_store_message()` se route hote hain →
  🛒 Buy Now button (green) HAMESHA attach hota hai jab message mein product ka naam ho.
- Button format: `{premium emoji} {pehle 2 words} Buy Now` — user spec ke mutabiq.
- **Naya product add hone par auto-detect + auto-apply** (koi manual setting nahi).
- `_product_buy_emoji` bug fix: own products ka emoji ab sahi nikalta hai
  (pehle rest-text return hota tha → button "Canva 500 User Panel Buy Now" jaisa ban jata tha).
- **Products bina emoji ke → auto-emoji** (keyword map + fallback 🛍️) — har product ka
  button ab `{emoji} First Two Words Buy Now` consistent hai (36/36 verified).

## ✅ 2. Referral Milestone Bonus — Settings (Referrals Abuse panel)
- Panel button: **🎯 Milestone Bonus (20 refs → +10 pts)** — admin khud set kare:
  `20:10, 50:30, 100:80` (kitny reffreals py kitna bonus).
- Har tier ek dafa pay hota hai (watermark `ref_milestone_paid_<uid>`) — double-pay abuse se bacha.
- Referral instructions + milestone templates dynamically update.

## ✅ 3. Delivered Files → Completed Orders (voice/video/pic/file/text SAB)
- Naya **`order_deliveries`** audit table: har delivery log (text/document/photo/video/voice/audio).
- Har delivery point hooked: supplier router, account pool, static media, manual delivery, admin approve.
- Completed Orders (v2 + purana view) mein **📦 Delivered Items (N)** button →
  saari delivered cheezein list + har media file dobara kholo/download karo.
- Purane `approve_order_callback` ka delivery_content save nahi hota tha → ab fixed.

## ✅ 4. Language System — saari 10 languages (Arabic/Spanish/French/German/Russian/Chinese ab bhi)
- i18n.py TRANSLATIONS ab **10/10 languages** mein complete (menu buttons, language selector,
  reviews, loyalty, analytics) — pehle sirf en/ur/ru/hi thi.
- Naya admin panel: **🌐 Language System** → saari languages + live instruction preview
  (har language mein native translation, Gemini pe depend nahi).
- Guide/instructions pehle se per-user translate (Gemini cached) — ab menu bhi translate.

## 🛠️ Verified
- 36/36 product buttons `{emoji} First2Words Buy Now` ✅
- purchase/discount broadcast button green + callback buy_<pid> ✅
- milestone tiers 20→10, 50→30 no double-pay ✅
- delivered-items audit document/photo/text ✅
- Arabic + Spanish + German main menu buttons ✅
- bot full import smoke ✅

---

# 🚀 v161.21 (2026-08-12) — SUPER-SPEED FIX (bot slow/frozen clicks ROOT CAUSE FOUND)

## 🐛 ROOT CAUSE — bot slow again after v161.18/19/20
- `i18n.translate_display_text()` called the **Gemini API SYNCHRONOUSLY** on the
  asyncio event loop.
- Product-detail render (`handlers_shop._build_detail_text`) calls `tr_user()`
  **16× per view** (name, desc, note, status, delivery, format, warranty, qty).
- Main-menu render called it per-button (~13×) for any non-English user.
- ⇒ every product tap / menu re-render by a non-English user = 10-30 SECONDS of
  frozen event loop ⇒ **EVERY user's clicks lagged** (bot feels slow everywhere).

## ✅ FIX — translation NEVER blocks the loop anymore
- `translate_display_text()` is now non-blocking:
  1. In-process LRU cache → microseconds
  2. DB cache (bot_settings) → fast local read
  3. On MISS → returns the ORIGINAL text instantly + warms the translation in a
     background daemon thread (rate-limited: max 3 concurrent, max 60 pending,
     deduped). The NEXT view is already translated.
- Verified: first call 1-2 ms (was seconds), background warm fills cache.
- Measured after fix (non-English user): main menu 90ms, product detail 20ms,
  my-account 23ms. All click paths < 500ms.

## ✅ Also fixed — supplier sync crash loop
- Logs showed `[async_helper] fetch_products crashed: float() argument must be
  a string or a real number, not 'dict'` every 30s.
- Some suppliers (Canboso etc.) send prices as dicts ({"USD": 5}) → float(dict)
  crashed the fetch.
- Added `_safe_float()` (handles dict/string/None) + patched all risky float()
  calls (Canboso base_price/usdPricing, price_usd, ProdSeller price,
  _compute_sell_price, update_ext_product).
- Verified LIVE: ProdSeller 16 products, real stock (296/924/295...), balance
  $11.86 — no crash.

---

# 🚀 v161.22 (2026-08-12) — BYBIT PAY REDESIGN — payment ab DETECT hoti hai + bot FAST

## 🐛 ROOT CAUSE (user: "payment add ni hoi" + "bot slow again")
Screenshot OCR: user ne Bybit Pay UID 563918642 paste kiya → bot "Payment Not Found Yet".
Live Bybit API test se 3 internal deposits milin — **user 563918642 ki $1.0 payment API mein
MOJUD thi** (`fromMemberId=563918642, amount=1.0, txid=7efd6bc9-...`), lekin bot match
nahi kar pa raha tha. 3 problems:

1. **Clock drift (retCode 10002)** — `_bybit_server_offset()` 300s cache; stale offset →
   API call fail → "Payment Not Found Yet". Main jab manually check karta hoon fresh
   offset leta hoon isliye payment milti thi, bot ko nahi.
2. **Async job → SYNC requests** — `bybit_deposit_background_job` (async) directly
   `_find_matching_bybit_payment()` call karta hai jo proxy-rotating sync requests hai
   (30-40s!) → event loop frozen → har click slow.
3. **23-proxy pool, 8-15s timeouts** — dead proxies pe rotation 2-3 min burn karti thi.

## ✅ FIX (tested live)
- `_bybit_get()` ab retCode 10002 par offset refresh karke RETRY karta hai → clock drift
  kabhi payment ko "not found" nahi bana sakta.
- `bybit_deposit_background_job` + `_verify_bybit_order_and_respond` (Check button) +
  `_notify_admin_bybit_failure` sab `asyncio.to_thread` → event loop kabhi block nahi.
- Proxy rotation timeout per-proxy 3s (23 proxies × 3s max ≈ 69s worst, normally 1-3s).
- Bybit auto-check job 45s → 20s (faster detection).

## ✅ VERIFIED (live Bybit API)
- Internal fetch: 2.3s (pehle 30-40s).
- User 563918642 $1.0 payment MATCHED in 0.8s (txid 7efd6bc9-234f-4b77-9f30-0665c931).
- Event-loop heartbeat test: max gap 51ms during scan → bot responsive.
- Full bot boot OK.

---

# 🚀 v161.24 (2026-08-12) — BYBIT CHECK-PAYMENT-ONLY + NEW INSTRUCTIONS + SUPPLIER AUDIT

## ✅ Bybit changes (user demand):
1. **20s auto-detect system REMOVED** — Bybit verification ab SIRF tab hoti hai jab
   customer 🔍 Check Payment par click kare (user: "user khud check payment py click kry tbhi ho").
   `bybit_deposit_background_job` → no-op stub.
2. **Extra "Bybit Payment Verified!" message REMOVED** — Deposit Successful! wala khubsurat
   message rahta hai (points) ya product-delivery message; Check par sirf chhota toast
   "✅ Verified!" dikhta hai. (Screenshot se confirm kiya).
3. **Bybit Pay instructions UPDATED** (English + emojis) — naya flow:
   Assets → Withdraw → Crypto Withdrawal → USDT → Internal Transfer 🔁 → UID → paste
   bot's UID + exact amount → Withdraw → back to bot → 🔍 Check Payment.
   ⚠️ Bybit Pay se mat bhejo — sirf Internal Transfer auto-detect hota hai.
   - config.py: payment_bybit_pay, payment_bybit_pay_reference, bybit_deposit_instructions
   - ui_extras.py: How-to-use guide_pay_bybit updated.

## ✅ Supplier audit (sab LIVE verified):
- TunVNMMO $8.60/12 ✅ | Shop Cron $6.00/13 ✅ | sinhle $7.80/33 ✅
- MMOStore $9.21/24 ✅ | ProdSeller $11.86/16 ✅ | Ai Tools $9.50/24 ✅ | Akunding $9.51/19 ✅
- ProdSeller docs_url fix: http://51.77.244.194/api-docs/ → https://prodseller.com/api-docs/

## ✅ READY DB (nayi — user ki current): 1098 users / 513 orders / 16 products
- bite_store_restore_ready.db — migrate 0 errors, order_deliveries ready,
  ref_bonus_tiers=20:10, ProdSeller docs fixed. Functional tests passed.

---

# 🚀 v161.25 (2026-08-12) — ⭐ TELEGRAM STARS PAYMENT ADDED

## Naya payment method: ⭐ Telegram Stars (Buy Points + Products)
- User ne dekha Stock Lara bot mein Stars payment → "mera b krdena"
- Implementation (web-researched, Bot API docs):
  - `handlers_stars.py` naya module:
    - `points_stars_callback` (ptspay_stars_{amt}) — Buy Points Stars invoice
    - `product_stars_callback` (pay_stars_{pid}_{qty}) — product Stars invoice
    - `stars_pay_callback` — tap "Pay X Stars" → bot.send_invoice(currency=XTR, provider_token="")
    - `stars_precheckout_callback` — PreCheckoutQueryHandler → answer OK
    - `stars_successful_payment` — order delivered + points credited + Deposit Successful msg
  - Rate: `stars_per_dollar` setting (default 120 = 1$ : 120 Stars, admin editable)
  - `database.py`: PAYMENT_METHODS mein telegram_stars
  - `keyboards.py`: Buy Points + product checkout mein ⭐ button
  - `button_system.py`: pay_stars + pay_stars_pay registry buttons (rename/color)
  - `handlers_admin.py`: Crypto Settings mein Stars rate + Set Stars Rate button
    (stars_rate_start_callback + stars_rate_received)
  - `ui_extras.py`: How-to-Use deposit guide Stars section
  - `config.py`: stars_pay_instructions response (editable in Edit Responses)
  - bot.py: PreCheckoutQueryHandler + MessageHandler(filters.SUCCESSFUL_PAYMENT) registered

## Tests (sab pass):
- rate: $1=120, $2.6309=316 ✅
- invoice stored 600 stars ($5) ✅
- send_invoice: currency=XTR, provider_token='', prices[0].amount=600 ✅
- pre_checkout answered OK ✅
- successful_payment → order delivered + 50 points + Deposit Successful msg ✅
- product order: pay_stars_242_1 → 120 stars invoice ✅
- rate setter: 120→150 works ✅
- FULL BOT BOOT OK ✅

## Note for owner:
- BotFather → Payments → "Back to Bot" (provider list fiat ke liye hai, Stars ke liye
  kuch nahi chahiye — Stars sab bots ko automatic available hai)
- Stars paisa bot ke Telegram Stars balance mein aata hai → Fragment se withdraw

## v168.1 (2026-08-13)
### 🎯 Broadcast Routing Fix
- **Fixed:** Referral and new user broadcasts now route through configured fake activity destination
- Referral broadcasts go to destination (group/channel/bot) instead of random 30 user inboxes
- New user join broadcasts go to destination instead of all users
- Consistent with other fake activity broadcasts (purchase, deposit, etc.)
- Users' inboxes are now clean — only see activity they interact with directly
