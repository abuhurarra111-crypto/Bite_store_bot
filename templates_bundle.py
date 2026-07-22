# ============================================================
# 🧩 v77 BUNDLE: templates_bundle.py
# ============================================================
# This file is the merged result of 4 originally separate modules:
#   • delivery_templates.py
#   • price_drop_templates.py
#   • free_claim_templates.py
#   • raw_delivery.py
#
# 🛡️ ALL CODE IS PRESERVED VERBATIM. Each original file's contents appears
# below in its own section. Imports and behavior are byte-identical to the
# pre-merge codebase — only file count is reduced.
# ============================================================


# ============================================================
# 📄 ORIGINAL FILE: delivery_templates.py
# ============================================================

# ============================================
# 🎁 BITE STORE DELIVERY TEMPLATES
# ============================================
# Professional, emoji-rich templates for 3 product formats:
#   • email_pass
#   • redeem_link
#   • coupon_codes
#
# Admin can select 1 of 10 built-in templates per product.
#
# 🆕 v72 BUG FIX: All user-supplied content (email/password/link/code/notes/
# raw stock data) now passes through `wrap_raw_for_telegram()` which preserves
# every byte exactly as admin entered it. Templates switched from Markdown to
# HTML mode because Markdown auto-mangles _ * [ ] ` characters. HTML <code>
# blocks preserve EVERYTHING (whitespace, special chars, Unicode, emojis).
#
# Output is prefixed with [[HTML]] sentinel so the existing premium-emoji-guard
# send pipeline auto-detects HTML parse_mode.
# ============================================

from utils import html_strip_tags
# [v77-merge] self-bundle import removed: from raw_delivery import wrap_raw_for_telegram, html_safe_for_code_block

FORMAT_EMAIL_PASS = "email_pass"
FORMAT_REDEEM_LINK = "redeem_link"
FORMAT_COUPON_CODES = "coupon_codes"

FORMAT_META = {
    FORMAT_EMAIL_PASS: {
        "label": "Email+Pass",
        "icon": "📧",
        "hint": "One account per line: email|password",
        "example": "demo@gmail.com|MyPass123",
    },
    FORMAT_REDEEM_LINK: {
        "label": "Redeem Link",
        "icon": "🖇️",
        "hint": "One redeem link per line: https://...",
        "example": "https://redeem.example.com/claim/ABC123",
    },
    FORMAT_COUPON_CODES: {
        "label": "Coupon Codes",
        "icon": "🎁",
        "hint": "One coupon code per line",
        "example": "BITE-STORE-2026-PRO",
    },
}

# 🆕 v72: All templates now in HTML format (was Markdown which mangled
# special chars in delivery content). HTML preserves user bytes byte-perfect
# inside <code> blocks.
_TEMPLATE_STYLES = {
    1: {
        "name": "Classic Pro",
        "header": "🎉 <b>Bite Store Delivery</b>",
        "intro": "Your order is ready and delivered successfully.",
        "footer": "🙏 Thank you for shopping with <b>Bite Store</b>!",
        "tip_icon": "💡",
    },
    2: {
        "name": "Royal Access",
        "header": "👑 <b>Bite Store | Premium Access</b>",
        "intro": "Your premium item has been unlocked.",
        "footer": "✨ We appreciate your trust in <b>Bite Store</b>.",
        "tip_icon": "🛡️",
    },
    3: {
        "name": "Clean Receipt",
        "header": "🧾 <b>Bite Store Receipt</b>",
        "intro": "Below are your delivery details.",
        "footer": "📌 Keep these details private and secure.",
        "tip_icon": "📘",
    },
    4: {
        "name": "Gift Drop",
        "header": "🎁 <b>Bite Store Surprise Drop</b>",
        "intro": "Your purchase has landed successfully.",
        "footer": "💙 Enjoy your order from <b>Bite Store</b>!",
        "tip_icon": "🚀",
    },
    5: {
        "name": "Secure Vault",
        "header": "🔐 <b>Bite Store Secure Delivery</b>",
        "intro": "Your account details are now available.",
        "footer": "🛡️ For safety, do not share these details with anyone.",
        "tip_icon": "🔒",
    },
    6: {
        "name": "Lightning Fast",
        "header": "⚡ <b>Bite Store Instant Delivery</b>",
        "intro": "Delivered instantly — fast and smooth.",
        "footer": "⚙️ Need help? Support is always here for you.",
        "tip_icon": "⚡",
    },
    7: {
        "name": "Elite Panel",
        "header": "💼 <b>Bite Store Elite Panel</b>",
        "intro": "Your product has been prepared professionally.",
        "footer": "📈 Powered by <b>Bite Store</b> premium delivery system.",
        "tip_icon": "🎯",
    },
    8: {
        "name": "Luxury Box",
        "header": "💎 <b>Bite Store Luxury Delivery</b>",
        "intro": "A premium item has been delivered to you.",
        "footer": "🌟 Thank you for choosing the premium way — <b>Bite Store</b>.",
        "tip_icon": "💎",
    },
    9: {
        "name": "Minimal Modern",
        "header": "📦 <b>Bite Store Delivery Update</b>",
        "intro": "Order completed successfully.",
        "footer": "✅ Delivered by <b>Bite Store</b>.",
        "tip_icon": "🧠",
    },
    10: {
        "name": "Celebration Pack",
        "header": "🥳 <b>Bite Store | Order Completed</b>",
        "intro": "Great news — your item is now ready to use.",
        "footer": "🎊 We hope you love your Bite Store experience!",
        "tip_icon": "🎉",
    },
}


def get_template_style(template_id):
    try:
        template_id = int(template_id)
    except Exception:
        template_id = 1
    return _TEMPLATE_STYLES.get(template_id, _TEMPLATE_STYLES[1])


def get_template_choices():
    return [(tid, info["name"]) for tid, info in _TEMPLATE_STYLES.items()]


def normalize_product_format(value):
    value = str(value or "").strip().lower()
    return value if value in FORMAT_META else FORMAT_EMAIL_PASS


def format_label(value):
    meta = FORMAT_META.get(normalize_product_format(value), FORMAT_META[FORMAT_EMAIL_PASS])
    return f"{meta['icon']} {meta['label']}"


def format_hint(value):
    meta = FORMAT_META.get(normalize_product_format(value), FORMAT_META[FORMAT_EMAIL_PASS])
    return meta['hint']


def format_example(value):
    meta = FORMAT_META.get(normalize_product_format(value), FORMAT_META[FORMAT_EMAIL_PASS])
    return meta['example']


def format_short_badge(value):
    meta = FORMAT_META.get(normalize_product_format(value), FORMAT_META[FORMAT_EMAIL_PASS])
    return f"{meta['icon']} {meta['label']}"


def _split_instructions(raw):
    text = str(raw or "").strip()
    if not text:
        return "", ""
    marker = "\n\nInstructions:\n"
    if marker in text:
        main, notes = text.split(marker, 1)
        return main.strip(), notes.strip()
    marker2 = "\nInstructions:\n"
    if marker2 in text:
        main, notes = text.split(marker2, 1)
        return main.strip(), notes.strip()
    return text, ""


def parse_delivery_item(raw, product_format=FORMAT_EMAIL_PASS):
    """Parse one raw stock line (or saved manual-delivery text) into a dict.

    🆕 v72: This function ONLY analyses content for visual hints (which part
    is the 'email', which part is the 'password' etc.). The TRUE raw bytes
    are preserved verbatim in the `raw` field — that's what gets delivered.
    Visual hint fields (email/password/link/code) are *only* used to pick
    the right icon and label in the rendered template.
    """
    fmt = normalize_product_format(product_format)
    raw_str = str(raw or "")
    main, notes = _split_instructions(raw_str)
    lines = [ln for ln in str(main or "").splitlines() if ln.strip()]
    first = lines[0] if lines else str(main or "")
    # Strip manual/own-mail prefixes for visual hint only (raw is preserved separately)
    visual_first = first
    for prefix in ("[Manual] ", "[Own Mail] "):
        if visual_first.startswith(prefix):
            visual_first = visual_first[len(prefix):]
            break
    data = {
        "format": fmt,
        # 🛡️ raw = THE EXACT bytes admin saved. THIS is what gets delivered.
        # We intentionally do NOT .strip() here — caller wants byte-perfect.
        "raw": raw_str,
        # The fields below are only for visual analysis (icon/label hints) —
        # they are NEVER used for the actual delivered content in v72+.
        "notes": notes,
        "email": "",
        "password": "",
        "link": "",
        "code": "",
    }

    if fmt == FORMAT_EMAIL_PASS:
        lower_lines = [ln.lower() for ln in lines]
        if len(lines) >= 2 and lower_lines[0].startswith("email:") and lower_lines[1].startswith("password:"):
            data["email"] = lines[0].split(":", 1)[1].strip()
            data["password"] = lines[1].split(":", 1)[1].strip()
            return data
        first_line = visual_first
        sep = "|" if "|" in first_line else (":" if ":" in first_line else None)
        if sep:
            left, _, right = first_line.partition(sep)
            data["email"] = left.strip()
            data["password"] = right.strip()
        else:
            data["email"] = first_line.strip()
            data["password"] = ""
        return data

    if fmt == FORMAT_REDEEM_LINK:
        for ln in lines:
            if ln.lower().startswith(("http://", "https://")):
                data["link"] = ln  # raw line, no strip
                break
        if not data["link"]:
            data["link"] = visual_first
        return data

    # coupon_codes
    if lines:
        data["code"] = lines[0]  # raw line
        if len(lines) > 1 and not notes:
            data["notes"] = "\n".join(lines[1:])
    else:
        data["code"] = visual_first
    return data


def validate_account_line(raw, product_format=FORMAT_EMAIL_PASS):
    fmt = normalize_product_format(product_format)
    line = str(raw or "").strip()
    if not line:
        return False, "Empty line"

    if fmt == FORMAT_EMAIL_PASS:
        sep = "|" if "|" in line else (":" if ":" in line else None)
        if not sep:
            return False, "Use format: email|password"
        email_part, _, pass_part = line.partition(sep)
        email_part = email_part.strip()
        pass_part = pass_part.strip()
        if not email_part or not pass_part:
            return False, "Both email and password are required"
        if "@" not in email_part:
            return False, "Email part must contain @"
        return True, ""

    if fmt == FORMAT_REDEEM_LINK:
        if not line.lower().startswith(("http://", "https://")):
            return False, "Redeem link must start with http:// or https://"
        return True, ""

    # coupon code
    if line.lower().startswith(("http://", "https://")):
        return False, "Coupon code must be plain text, not a link"
    return True, ""


def _safe_product_name_html(product_name):
    """Product name for HTML template header.
    If admin used premium emoji ([[HTML]] sentinel), preserve the inner HTML.
    Otherwise HTML-escape the plain text so < > & display safely.
    """
    s = str(product_name or "Product")
    if s.startswith("[[HTML]]"):
        # Already HTML — strip the sentinel, trust the inner markup
        return s[len("[[HTML]]"):]
    # Plain text — only escape the 3 mandatory HTML chars
    return html_safe_for_code_block(s)


def _render_body_block_html(parsed, order_id=0, product_id=0):
    """🆕 v72: Render the delivery body using HTML <code> blocks for raw content.

    Telegram's HTML <code> preserves ALL bytes (whitespace, _, *, |, /, \\, :,
    =, ?, &, Urdu, Arabic, Chinese, emojis, etc.) inside its content. We only
    need to escape the 3 HTML-mandatory chars (< > &) and Telegram unescapes
    them client-side when user copies the text.
    """
    fmt = parsed["format"]
    raw = parsed.get("raw") or ""

    # ── For ALL formats: deliver the EXACT RAW content admin saved ──
    # We still display nicely-labelled fields when possible, but the
    # content is ALWAYS the byte-perfect raw — no .strip(), no escape_md.
    wrapped, ok, _hash = wrap_raw_for_telegram(raw, order_id=order_id,
                                                product_id=product_id)
    if not ok:
        # Should never happen, but fail-safe: deliver plain text
        return ("⚠️ <b>Integrity check failed</b> — please contact admin.")

    if fmt == FORMAT_EMAIL_PASS:
        return (
            f"📧 <b>Account Details:</b>\n"
            f"{wrapped}\n"
            f"<i>Format: email|password (one per line)</i>"
        )

    if fmt == FORMAT_REDEEM_LINK:
        return (
            f"🖇️ <b>Redeem Link:</b>\n"
            f"{wrapped}\n"
            f"🔓 Open the link and complete the redeem steps."
        )

    # coupon_codes
    return (
        f"🎁 <b>Coupon Code:</b>\n"
        f"{wrapped}\n"
        f"🛒 Apply this code at checkout or in the redeem section."
    )


def _render_format_tip(parsed):
    fmt = parsed["format"]
    if fmt == FORMAT_EMAIL_PASS:
        return "Change the password after first login for extra security."
    if fmt == FORMAT_REDEEM_LINK:
        return "If the link does not open instantly, copy it and open it in your browser/app."
    return "Keep this code private and use it before it expires."


# 🆕 v72: Sentinel prefix tells the existing premium-emoji guard that this
# message is HTML-formatted and Bot.send_message should use parse_mode='HTML'.
_HTML_SENTINEL = "[[HTML]]"


def render_delivery_item(raw_item, product_name="Product", product_format=FORMAT_EMAIL_PASS,
                         template_id=1, item_no=1, total_items=1, shop_name="Bite Store",
                         order_id=0, product_id=0):
    """🆕 v72: Renders ONE delivery item in HTML. The raw user content is
    preserved byte-for-byte inside <code> blocks. SHA-256 integrity check
    happens inside wrap_raw_for_telegram() — if it fails, delivery returns
    an error notice (NEVER the original content as a fallback)."""
    parsed = parse_delivery_item(raw_item, product_format)
    style = get_template_style(template_id)
    product_name_html = _safe_product_name_html(product_name)
    format_name = format_short_badge(parsed["format"])
    # NOTE: format_name comes from FORMAT_META which is admin-static (no user input)
    format_name_safe = html_safe_for_code_block(format_name)
    item_line = f"🧾 <b>Item:</b> {item_no}/{total_items}\n" if total_items > 1 else ""

    # Notes: user-supplied free text — also wrap in <code> for byte-safety
    notes_raw = parsed.get("notes") or ""
    notes_block = ""
    if notes_raw:
        notes_wrapped, _ok, _h = wrap_raw_for_telegram(notes_raw, order_id=order_id,
                                                        product_id=product_id)
        notes_block = f"\n\n📝 <b>Notes:</b>\n{notes_wrapped}"

    body = _render_body_block_html(parsed, order_id=order_id, product_id=product_id)

    return (
        f"{style['header']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Product:</b> {product_name_html}\n"
        f"{item_line}"
        f"🧩 <b>Format:</b> {format_name_safe}\n\n"
        f"{style['intro']}\n\n"
        f"{body}"
        f"{notes_block}\n\n"
        f"{style['tip_icon']} <b>Tip:</b> {_render_format_tip(parsed)}\n"
        f"{style['footer']}"
    )


def render_delivery_bundle(items, product_name="Product", product_format=FORMAT_EMAIL_PASS,
                           template_id=1, shop_name="Bite Store",
                           order_id=0, product_id=0):
    """🆕 v72: Render bundle of delivery items in HTML.

    CRITICAL: We do NOT call .strip() on items — admin's whitespace is sacred.
    We only filter out None/completely-empty items (empty string after coercion).
    """
    safe_items = [str(x) for x in (items or []) if x is not None and str(x) != ""]
    if not safe_items:
        # Plain text fallback (no [[HTML]] sentinel)
        return "⚠️ Delivery item is empty. Please contact admin."
    total = len(safe_items)
    blocks = [
        render_delivery_item(item, product_name=product_name,
                             product_format=product_format,
                             template_id=template_id,
                             item_no=i + 1, total_items=total,
                             shop_name=shop_name,
                             order_id=order_id, product_id=product_id)
        for i, item in enumerate(safe_items)
    ]
    output = "\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(blocks)
    # Prefix with [[HTML]] sentinel so premium_emoji_guard auto-switches
    # Bot.send_message parse_mode to 'HTML'.
    return _HTML_SENTINEL + output


# ============================================================
# 📄 ORIGINAL FILE: price_drop_templates.py
# ============================================================

# ============================================================
# 📉 PRICE DROP BROADCAST TEMPLATES (v66)
# ============================================================
# 10 unique professional templates. Used when:
#   1) Admin reduces a product price → confirm dialog → broadcast
#   2) Fake-activity sender randomly picks "price_drop" type
#
# Variables available in every template:
#   {product}       — product name
#   {old_price}     — "10.00"
#   {new_price}     — "6.50"
#   {discount_pct}  — "35"
#   {savings}       — "3.50"
# ============================================================

import random

PRICE_DROP_TEMPLATES = [
    # 1) Classic Big Drop
    (
        "📉 *BIG PRICE DROP!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔥 *{product}*\n\n"
        "~~${old_price}~~ ➜  *${new_price}* only!\n"
        "💰 You save: *${savings}* (*-{discount_pct}%*)\n\n"
        "_Limited stock — grab yours now!_ 🛒"
    ),
    # 2) Flash Crash
    (
        "⚡ *FLASH PRICE CRASH!* ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💎 *{product}*\n"
        "Price slashed: *${new_price}* (was ${old_price})\n\n"
        "🚀 *{discount_pct}% OFF* — Don't miss out!"
    ),
    # 3) Hot Deal
    (
        "🔥 *HOT DEAL ALERT!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📦 *{product}*\n"
        "💵 New price: *${new_price}*\n"
        "✂️ Cut from ${old_price} — save *${savings}*\n\n"
        "⏰ Limited-time offer. Order now!"
    ),
    # 4) Mega Sale
    (
        "🎯 *MEGA SALE!* 🎯\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🛍 *{product}*\n"
        "▫️ Was: ~~${old_price}~~\n"
        "▪️ Now: *${new_price}*\n"
        "▫️ Save: *${savings}* (*-{discount_pct}%*)\n\n"
        "🏃 Hurry — stocks running out!"
    ),
    # 5) Price Cut Announcement
    (
        "💸 *PRICE CUT JUST ANNOUNCED!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📌 *{product}*\n"
        "🔻 Reduced by *{discount_pct}%* — now only *${new_price}*\n"
        "_Originally ${old_price}_\n\n"
        "🛒 Visit shop to buy!"
    ),
    # 6) Discount Bomb
    (
        "💣 *DISCOUNT BOMB DROPPED!* 💣\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎁 *{product}*\n"
        "🔥 *{discount_pct}% OFF*\n"
        "💵 Was ~~${old_price}~~ → Now *${new_price}*\n\n"
        "_Grab it before it's gone!_"
    ),
    # 7) Lowest Ever
    (
        "🏷 *LOWEST PRICE EVER!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ *{product}*\n"
        "Price now: *${new_price}* (was ${old_price})\n"
        "🎉 You save: ${savings} ({discount_pct}% off)\n\n"
        "Best time to buy — secure yours today!"
    ),
    # 8) Special Offer Live
    (
        "🎊 *SPECIAL OFFER LIVE!* 🎊\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🛍 *{product}*\n"
        "💲 *${new_price}* (down from ${old_price})\n"
        "🎯 Save *{discount_pct}%* instantly\n\n"
        "🚀 Active now — limited time!"
    ),
    # 9) Insane Deal
    (
        "🤯 *INSANE DEAL!* 🤯\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📦 *{product}*\n"
        "Price slashed *{discount_pct}%*!\n"
        "Now only *${new_price}* (was ${old_price})\n\n"
        "_Treat yourself today!_ 🎁"
    ),
    # 10) Premium Cut
    (
        "💎 *PREMIUM PRICE DROP*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🏷 *{product}*\n"
        "Now: *${new_price}*\n"
        "Old: ~~${old_price}~~\n"
        "🎯 *{discount_pct}% OFF*  •  Save ${savings}\n\n"
        "Visit shop to claim!"
    ),
]


def render_price_drop(product_name: str, old_price: float, new_price: float) -> str:
    """Pick a random template and render it with the given product values.
    Returns "" on invalid input (old<=0, new<=0, or new >= old)."""
    try:
        old_price = float(old_price)
        new_price = float(new_price)
    except Exception:
        return ""
    if old_price <= 0 or new_price <= 0 or new_price >= old_price:
        return ""

    savings = old_price - new_price
    discount_pct = int(round((savings / old_price) * 100))

    tpl = random.choice(PRICE_DROP_TEMPLATES)
    return tpl.format(
        product=str(product_name or "Product"),
        old_price=f"{old_price:.2f}",
        new_price=f"{new_price:.2f}",
        discount_pct=discount_pct,
        savings=f"{savings:.2f}",
    )


def get_template_count() -> int:
    return len(PRICE_DROP_TEMPLATES)


# ============================================================
# 📄 ORIGINAL FILE: free_claim_templates.py
# ============================================================

# ════════════════════════════════════════════════════════════════
# 🎁 FREE CLAIM TEMPLATES — Broadcast announcements (v47)
# ════════════════════════════════════════════════════════════════
# When a user claims a product for free using their referrals, the bot
# announces it to the configured fake-activity destination (same chat
# used by store_broadcast → dest_chat_id).
#
# 10 ready-made templates + admin-customizable text.
# Each template uses {placeholders}:
#   {user}    — masked username (e.g. "a•••i")
#   {product} — product name
#   {refs}    — number of referrals used
#   {shop}    — shop name (from config.SHOP_NAME)
#
# A "🛍️ Visit Shop" / "🎁 Get Yours" button is added automatically by
# the sender — do NOT put it in the text.
# ════════════════════════════════════════════════════════════════

import random


FREE_CLAIM_TEMPLATES = [
    # 1
    ("🎁 *FREE CLAIM!* 🎁\n\n"
     "🎉 *{user}* just claimed *{product}* for FREE!\n\n"
     "💎 They used *{refs}* referrals to unlock it.\n"
     "🚀 You can too — just invite friends!\n\n"
     "_Welcome to {shop}_ ⭐"),
    # 2
    ("🥳 *Another FREE Winner!* 🥳\n\n"
     "👤 {user}\n"
     "📦 *{product}*\n"
     "👥 Referrals used: *{refs}*\n\n"
     "💡 Refer your friends and get yours for *FREE* too!"),
    # 3
    ("✨ *FREE PRODUCT UNLOCKED!* ✨\n"
     "━━━━━━━━━━━━━━━━━━━━\n"
     "🎁 *{product}*\n"
     "🏆 Claimed by: {user}\n"
     "👥 Friends invited: {refs}\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "🎯 *You're next!* Start referring today."),
    # 4
    ("🔥 *{user} got it for FREE!* 🔥\n\n"
     "📦 *{product}*\n"
     "💰 Saved: 100%\n"
     "👥 Used: *{refs}* referrals\n\n"
     "_Your turn — share your link & claim yours_ 🚀"),
    # 5
    ("💎 *Referral Reward Unlocked!* 💎\n\n"
     "🎉 *{user}* successfully claimed:\n"
     "📦 *{product}* — *FREE*\n\n"
     "🔗 Referrals used: *{refs}*\n"
     "🛍️ Shop: {shop}\n\n"
     "👉 Want one? Get referring!"),
    # 6
    ("🚨 *FREE CLAIM ALERT!* 🚨\n\n"
     "👤 {user} → *{product}*\n"
     "👥 Referrals: {refs}\n\n"
     "⚡ Delivered instantly. Zero cost.\n"
     "💯 Pure reward for inviting friends!"),
    # 7
    ("🏆 *NEW FREE WINNER!* 🏆\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "🎊 Congratulations *{user}*!\n\n"
     "📦 *{product}*\n"
     "👥 *{refs}* friends invited = FREE!\n\n"
     "_Your referral link is your money 💰_"),
    # 8
    ("🎉 *FREEBIE ALERT!* 🎉\n\n"
     "{user} just unlocked *{product}* completely free.\n\n"
     "All it took? *{refs} referrals.*\n\n"
     "🔗 Share your link → Get free products!\n"
     "🛍️ {shop}"),
    # 9
    ("⭐ *SHARED = REWARDED!* ⭐\n\n"
     "🎁 Free Claim by: *{user}*\n"
     "📦 Item: *{product}*\n"
     "👥 Referrals spent: *{refs}*\n\n"
     "Don't watch others win — *YOU* can claim too!"),
    # 10
    ("🌟 *REFERRAL REWARD CLAIMED!* 🌟\n"
     "━━━━━━━━━━━━━━━━━━━━\n"
     "🥇 Winner: {user}\n"
     "📦 Reward: *{product}*\n"
     "👥 Refs used: {refs}\n"
     "💵 Price paid: *$0.00*\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "🚀 Start sharing your link — be next!"),
]


# Bot-settings keys (global selection — same for every product unless admin overrides per-product)
FC_TPL_KEY     = "freeclaim_tpl_index"      # global default template index (0..9)
FC_CUSTOM_KEY  = "freeclaim_tpl_custom"     # global admin custom text (empty = use selected template)


# Per-product override keys (set in product_free_claim row):
#   tpl_index INTEGER DEFAULT -1   (-1 means: use global)
#   custom_text TEXT DEFAULT ''    (empty means: use global)


def _g(key, default=""):
    try:
        from database import get_setting
        return get_setting(key, default)
    except Exception:
        return default


def _s(key, val):
    try:
        from database import set_setting
        set_setting(key, str(val))
    except Exception:
        pass


def get_global_template_index():
    try:
        return max(0, min(len(FREE_CLAIM_TEMPLATES) - 1, int(_g(FC_TPL_KEY, "0") or 0)))
    except Exception:
        return 0


def set_global_template_index(i):
    _s(FC_TPL_KEY, int(i))


def get_global_custom_text():
    return _g(FC_CUSTOM_KEY, "")


def set_global_custom_text(text):
    _s(FC_CUSTOM_KEY, text or "")


def _mask_username(name):
    """Mask username like 'ali' → 'a•••i' (privacy-friendly)."""
    if not name:
        return random.choice(["a•••i", "m•••d", "s•••a", "z•••n", "h•••a", "k•••l", "f•••z"])
    name = str(name).strip()
    if len(name) <= 2:
        return name[0] + "•••"
    return name[0] + "•••" + name[-1]


def build_free_claim_message(*, user_name, product_name, refs_used,
                              tpl_index=None, custom_text=None, shop_name=None):
    """Build the announcement text.

    Priority for which template to use:
      1. explicit custom_text (non-empty)  — per-product custom from admin
      2. explicit tpl_index (>= 0)         — per-product picked template
      3. global custom text (non-empty)
      4. global selected template
    """
    if shop_name is None:
        try:
            from config import SHOP_NAME
            shop_name = SHOP_NAME
        except Exception:
            shop_name = "Shop"

    masked = _mask_username(user_name)

    # Resolve template text
    chosen = None
    if custom_text and str(custom_text).strip():
        chosen = str(custom_text)
    elif tpl_index is not None and tpl_index >= 0:
        idx = max(0, min(len(FREE_CLAIM_TEMPLATES) - 1, int(tpl_index)))
        chosen = FREE_CLAIM_TEMPLATES[idx]
    else:
        gcustom = get_global_custom_text()
        if gcustom.strip():
            chosen = gcustom
        else:
            idx = get_global_template_index()
            chosen = FREE_CLAIM_TEMPLATES[idx]

    try:
        return chosen.format(
            user=masked,
            product=product_name or "Product",
            refs=int(refs_used),
            shop=shop_name,
        )
    except Exception:
        return chosen  # in case admin's custom text has bad/no placeholders


# ============================================================
# 📄 ORIGINAL FILE: raw_delivery.py
# ============================================================

# ============================================================
# 🛡️ RAW DELIVERY INTEGRITY (v72)
# ============================================================
# Bug fix: prior versions were silently mutating delivered content
# through escape_md(), str.strip(), and Markdown re-parsing.
#
# This module guarantees:
#   1. Store Exactly As Received  — no .strip(), no escape, no encode
#   2. Deliver Exactly As Stored  — content goes through HTML <code>...
#      </code> wrapper (Telegram preserves ALL bytes inside code blocks)
#   3. SHA-256 integrity check at both stages
#   4. Mismatch → delivery BLOCKED + detailed log entry
#
# Core rule: "Store Exactly As Received, Deliver Exactly As Stored."
# ============================================================

import hashlib
import html as _stdlib_html
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def content_hash(content: str) -> str:
    """SHA-256 hex digest of content as UTF-8 bytes. Handles None safely."""
    if content is None:
        content = ""
    return hashlib.sha256(str(content).encode("utf-8")).hexdigest()


def ensure_integrity_table():
    """Create the delivery_integrity_log table for tracking mismatches."""
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS delivery_integrity_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id      INTEGER,
                product_id    INTEGER,
                stage         TEXT,                       -- 'save' / 'deliver'
                status        TEXT,                       -- 'ok' / 'mismatch' / 'blocked'
                stored_hash   TEXT,
                computed_hash TEXT,
                stored_len    INTEGER,
                computed_len  INTEGER,
                detail        TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_intg_order ON delivery_integrity_log(order_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_intg_status ON delivery_integrity_log(status)")
        conn.commit(); conn.close()
    except Exception as e:
        logger.debug(f"[RawDelivery] ensure_integrity_table failed: {e}")


def log_integrity(order_id, product_id, stage, status,
                  stored_hash="", computed_hash="",
                  stored_len=0, computed_len=0, detail=""):
    """Record an integrity event. Always best-effort."""
    try:
        ensure_integrity_table()
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("""
            INSERT INTO delivery_integrity_log
            (order_id, product_id, stage, status,
             stored_hash, computed_hash, stored_len, computed_len, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (int(order_id or 0), int(product_id or 0), str(stage)[:20],
              str(status)[:20], str(stored_hash)[:80], str(computed_hash)[:80],
              int(stored_len or 0), int(computed_len or 0),
              str(detail)[:500]))
        conn.commit(); conn.close()
    except Exception as e:
        logger.debug(f"[RawDelivery] log_integrity failed: {e}")


def verify_integrity(stored: str, computed: str) -> tuple:
    """Returns (ok: bool, stored_hash: str, computed_hash: str)."""
    if stored is None: stored = ""
    if computed is None: computed = ""
    sh = content_hash(stored)
    ch = content_hash(computed)
    return (sh == ch, sh, ch)


def get_recent_integrity_issues(limit=20):
    """Admin view — show last N integrity events (ok + mismatches)."""
    try:
        ensure_integrity_table()
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("""
            SELECT id, order_id, product_id, stage, status,
                   stored_len, computed_len, detail, created_at
            FROM delivery_integrity_log
            ORDER BY id DESC LIMIT ?
        """, (int(limit),))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_mismatch_count():
    """Count of mismatched / blocked events."""
    try:
        ensure_integrity_table()
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM delivery_integrity_log
            WHERE status IN ('mismatch', 'blocked')
        """)
        n = c.fetchone()[0]
        conn.close()
        return int(n or 0)
    except Exception:
        return 0


# ════════════════════════════════════════════════════════════
# 🛡️ Safe HTML wrapper for Telegram <code> blocks
# ════════════════════════════════════════════════════════════
# Telegram's HTML parse mode preserves ALL characters inside <code>...</code>
# and <pre>...</pre> tags EXCEPT four HTML-specific ones (<, >, &, ").
# We MUST escape those 4 chars (otherwise Telegram returns parse error and
# the user sees nothing), but everything else (whitespace, _, *, |, /, \,
# emojis, Urdu, Arabic, Chinese, Cyrillic, etc.) passes through byte-perfect.
#
# After Telegram delivers and the user copies the text out, those 4 chars
# render as their original form (Telegram un-escapes them client-side).
# ════════════════════════════════════════════════════════════
def html_safe_for_code_block(content: str) -> str:
    """Escape ONLY <, >, & for Telegram HTML <code> blocks.

    These 4 chars are mandatory HTML escapes — without them Telegram
    returns 'Bad Request: can't parse entities' and the message FAILS.

    When user copies the text from the rendered code block, Telegram's
    client converts the entities back to original chars, so the user
    pastes the EXACT original bytes anywhere else.

    All other characters — including _, *, [, ], `, |, /, \\, :, =, ?,
    spaces, tabs, newlines, emojis, Unicode (Urdu/Arabic/Chinese/etc.)
    — pass through 100% unchanged.
    """
    if content is None:
        return ""
    s = str(content)
    # NOTE: order matters — & MUST be first
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    return s


def unescape_html_for_verification(escaped: str) -> str:
    """Reverse the html_safe_for_code_block escaping — used for hash verify.

    After we wrap content in HTML, we need to know if 'what user effectively
    receives' (after Telegram un-escapes) matches the stored content.
    Python's html.unescape() handles all standard entities.
    """
    if escaped is None:
        return ""
    return _stdlib_html.unescape(str(escaped))


# ════════════════════════════════════════════════════════════
# 🎯 Public API — wrap raw content for delivery
# ════════════════════════════════════════════════════════════
def wrap_raw_for_telegram(raw_content: str, order_id=0, product_id=0) -> tuple:
    """Wrap raw content in a Telegram-safe HTML <code> block.

    Performs SHA-256 integrity verification:
      stored content → HTML escape → unescape → must equal stored content.

    Returns (wrapped_html: str, ok: bool, computed_hash: str).
    If ok is False, the caller should BLOCK delivery and notify admin.
    """
    if raw_content is None:
        raw_content = ""
    raw = str(raw_content)

    # 1. Escape for HTML <code> block
    escaped = html_safe_for_code_block(raw)
    wrapped = f"<code>{escaped}</code>"

    # 2. Verify round-trip: un-escape the escaped form must give back raw
    roundtrip = unescape_html_for_verification(escaped)
    ok, stored_hash, rt_hash = verify_integrity(raw, roundtrip)

    if not ok:
        # This should NEVER happen because we only escape 3 chars and the
        # escape is bijective. But just in case, log + block.
        log_integrity(
            order_id, product_id, stage="deliver", status="blocked",
            stored_hash=stored_hash, computed_hash=rt_hash,
            stored_len=len(raw), computed_len=len(roundtrip),
            detail=f"HTML round-trip mismatch (impossible)",
        )
        return ("", False, rt_hash)

    # 3. Success — log as ok (so admin can see normal operation count)
    log_integrity(
        order_id, product_id, stage="deliver", status="ok",
        stored_hash=stored_hash, computed_hash=rt_hash,
        stored_len=len(raw), computed_len=len(roundtrip),
        detail="",
    )
    return (wrapped, True, stored_hash)


def verify_storage(written_content: str, read_back_content: str,
                   order_id=0, product_id=0) -> bool:
    """After saving to DB, read it back and verify hash matches.
    Used by save paths to catch any mutation during storage."""
    ok, sh, ch = verify_integrity(written_content, read_back_content)
    log_integrity(
        order_id, product_id, stage="save",
        status="ok" if ok else "mismatch",
        stored_hash=sh, computed_hash=ch,
        stored_len=len(str(written_content or "")),
        computed_len=len(str(read_back_content or "")),
        detail="" if ok else "DB roundtrip mismatch",
    )
    return ok

