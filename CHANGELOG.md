# 📖 Bite Store Bot — Master CHANGELOG

**Bot:** `@bite_storee_bot` — Pakistani Telegram e-commerce shop
**Runtime:** Render.com Background Worker (Python 3.14, polling mode)
**DB:** SQLite at `/var/data/shop.db` (persistent disk)

> This is the SINGLE consolidated changelog. Every new release just appends a new section on top — no more per-version `.md` files cluttering the repo.

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
