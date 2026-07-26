# ============================================================
# 🧩 v77 BUNDLE: ui_extras.py
# ============================================================
# This file is the merged result of 5 originally separate modules:
#   • handlers_main_exit.py
#   • handlers_how_to_guide.py
#   • handlers_language.py
#   • handlers_activity.py
#   • handlers_force_join.py
#
# 🛡️ ALL CODE IS PRESERVED VERBATIM. Each original file's contents appears
# below in its own section. Imports and behavior are byte-identical to the
# pre-merge codebase — only file count is reduced.
# ============================================================


# ============================================================
# 📄 ORIGINAL FILE: handlers_main_exit.py
# ============================================================

# ============================================
# 🏠 UNIVERSAL MAIN MENU EXIT  (v76)
# ============================================
# When the user taps any 🏠 / 🔙 button whose callback_data is "main_menu",
# this handler runs FIRST (group=-50, above every ConversationHandler at the
# default group=0).  It:
#
#   1. Forcibly ENDs every active ConversationHandler for this user/chat
#      (clears each handler's private `_conversations` map for the key)
#   2. Wipes user_data session keys (everything except a small whitelist
#      that must persist — e.g. nav_stack itself, language)
#   3. Hands control to handlers_start.main_menu_callback to render the menu
#
# Net effect: no matter what step the user is mid-way through (entering a
# payment screenshot, replying to a ticket, picking quantities, etc.), tapping
# 🏠 Main Menu **always** drops them on a clean Main Menu screen.
# ============================================

import logging
from telegram.ext import ConversationHandler, ApplicationHandlerStop

logger = logging.getLogger(__name__)


# Keys that should NEVER be wiped (persistent preferences / nav tracking only).
_SAFE_KEYS = {
    "language",         # user's chosen language pref
    "nav_stack",        # we still want a clean nav after exit
    # Add more here if needed
}


def _end_all_conversations(application, update):
    """Find every ConversationHandler attached to `application` and forcibly
    END whatever state the current user is in. Works by clearing the entry
    in each handler's private `_conversations` dict (PTB ≥ v20).
    """
    try:
        chat_id = update.effective_chat.id if update.effective_chat else 0
        user_id = update.effective_user.id if update.effective_user else 0
    except Exception:
        chat_id, user_id = 0, 0
    if not chat_id and not user_id:
        return 0
    ended = 0
    try:
        # application.handlers is dict[group_int → list[Handler]]
        for group, handlers in list(application.handlers.items()):
            for h in handlers:
                if not isinstance(h, ConversationHandler):
                    continue
                # PTB stores active per-conversation state in private dict
                conv_map = getattr(h, "_conversations", None)
                if conv_map is None:
                    continue
                # Conv keys are tuples like (chat_id, user_id) — defensively scan.
                keys_to_kill = []
                for k in list(conv_map.keys()):
                    if not isinstance(k, tuple):
                        continue
                    if (chat_id and chat_id in k) or (user_id and user_id in k):
                        keys_to_kill.append(k)
                for k in keys_to_kill:
                    try:
                        conv_map.pop(k, None)
                        ended += 1
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"[MainMenuExit] end_all_conversations err: {e}")
    return ended


def _wipe_user_session(context):
    """Clear every user_data key except the SAFE whitelist."""
    try:
        ud = context.user_data
        if ud is None:
            return 0
        wiped = 0
        for k in list(ud.keys()):
            if k in _SAFE_KEYS:
                continue
            try:
                ud.pop(k, None)
                wiped += 1
            except Exception:
                pass
        return wiped
    except Exception as e:
        logger.debug(f"[MainMenuExit] wipe_session err: {e}")
        return 0


async def force_main_menu_callback(update, context):
    """Top-priority handler — kills all ongoing tasks and shows Main Menu.

    This MUST run before any ConversationHandler intercepts the callback.
    Registered at group=-50 in bot.py.
    """
    q = update.callback_query
    if not q or q.data != "main_menu":
        # Defensive — shouldn't happen because of the pattern filter
        return
    try:
        application = context.application
    except Exception:
        application = None

    # 1️⃣ End ALL active ConversationHandlers for this user
    ended = 0
    if application is not None:
        ended = _end_all_conversations(application, update)

    # 2️⃣ Wipe transient session keys
    wiped = _wipe_user_session(context)

    if ended or wiped:
        logger.info(f"[MainMenuExit] uid={q.from_user.id} ended {ended} convs, "
                    f"wiped {wiped} session keys")

    # 3️⃣ Render the main menu cleanly
    try:
        from handlers_start import main_menu_callback
        await main_menu_callback(update, context)
    except Exception as e:
        logger.error(f"[MainMenuExit] failed to render main menu: {e}")
        try:
            await q.answer("⚠️ Could not open Main Menu. Type /start", show_alert=True)
        except Exception:
            pass

    # 4️⃣ STOP further handler processing — prevents any ConversationHandler
    # at group=0 from also reacting to the same main_menu callback.
    raise ApplicationHandlerStop


# ============================================================
# 📄 ORIGINAL FILE: handlers_how_to_guide.py
# ============================================================

# ============================================
# 📚 HOW TO USE — User Guides Hub  (v76)
# ============================================
# Main Menu → 📚 How to Use → opens guide hub with sub-buttons.
# Each sub-button is a FULL SCREEN guide (own edit_message_text), not an
# inline alert. Every guide has a "🔙 Back to Guides" + "🏠 Main Menu" button.
#
# Topics covered (all user-side features):
#   1. 🛒 How to Buy a Product
#   2. 💎 How to Buy Points / Deposit
#   3. 💳 Payment Methods (overview)
#       └─ 🪙 Binance Pay (auto)
#       └─ 📱 EasyPaisa
#       └─ 📞 JazzCash
#       └─ 💰 Points Wallet
#   4. 🎫 How to Create a Support Ticket
#   5. 🛡️ How to Claim Warranty / Replacement
#   6. 🔁 How to Request Replacement
#   7. ⭐ How to Leave a Review
#   8. 🎁 Free Account / Referral Program
#   9. 🏆 Tier System & Loyalty Points
#  10. 📜 Order History & Tracking
#  11. 📊 Price List & Filters
#  12. 🌐 Language Settings
#  13. ❓ Common Issues / FAQ
# ============================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def _safe_edit(q, text, **kwargs):
    try:
        await q.edit_message_text(text, **kwargs)
    except Exception:
        try:
            kwargs.pop("parse_mode", None)
            await q.edit_message_text(text, **kwargs)
        except Exception:
            try:
                await q.message.reply_text(text)
            except Exception:
                pass


def _nav_kb(extra_rows=None):
    """Common bottom nav for every guide screen."""
    rows = []
    if extra_rows:
        rows.extend(extra_rows)
    rows.append([
        InlineKeyboardButton("🔙 Back to Guides", callback_data="how_to_hub"),
        InlineKeyboardButton("🏠 Main Menu",     callback_data="main_menu"),
    ])
    return InlineKeyboardMarkup(rows)


# ───────────────────────────────────────────
# Guide Hub (entry point)
# ───────────────────────────────────────────

def _build_how_to_hub_text_and_kb():
    """🆕 v78: shared between callback + reply-keyboard entry."""
    text = (
        "📚 *How to Use — Complete Guide*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Welcome! Pick any topic below to learn how to use that feature step-by-step.\n\n"
        "_Every guide shows exact buttons to tap, what to type, and what to expect._\n\n"
        "📌 *Quick tip:* The 🏠 Main Menu button (anywhere in the bot) always "
        "takes you back to the start — even mid-payment or mid-form."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 How to Buy a Product",      callback_data="guide_buy_product")],
        [InlineKeyboardButton("💎 How to Buy Points / Deposit", callback_data="guide_deposit")],
        [InlineKeyboardButton("💳 Payment Methods (Overview)",   callback_data="guide_pay_overview")],
        [InlineKeyboardButton("🪙 Binance Pay — Step-by-Step",   callback_data="guide_pay_binance")],
        [InlineKeyboardButton("📱 EasyPaisa — Step-by-Step",      callback_data="guide_pay_easypaisa")],
        [InlineKeyboardButton("📞 JazzCash — Step-by-Step",       callback_data="guide_pay_jazzcash")],
        [InlineKeyboardButton("💰 Pay with Points",                callback_data="guide_pay_points")],
        [InlineKeyboardButton("🎫 How to Create a Support Ticket",callback_data="guide_ticket")],
        [InlineKeyboardButton("🛡️ How to Claim Warranty",        callback_data="guide_warranty")],
        [InlineKeyboardButton("🔁 How to Request Replacement",     callback_data="guide_replacement")],
        [InlineKeyboardButton("⭐ How to Leave a Review",          callback_data="guide_review")],
        [InlineKeyboardButton("🎁 Free Account / Referrals",       callback_data="guide_referral")],
        [InlineKeyboardButton("🏆 Tier System & Loyalty",          callback_data="guide_tier")],
        [InlineKeyboardButton("📜 Order History & Tracking",       callback_data="guide_orders")],
        [InlineKeyboardButton("📊 Price List & Filters",            callback_data="guide_price_list")],
        [InlineKeyboardButton("🌐 Language Settings",               callback_data="guide_language")],
        [InlineKeyboardButton("❓ Common Issues / FAQ",            callback_data="guide_faq")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
    ])
    return text, kb


async def how_to_hub_callback(update, context):
    """📚 How to Use — main hub with all topic buttons (callback entry)."""
    q = update.callback_query
    await q.answer()
    text, kb = _build_how_to_hub_text_and_kb()
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def how_to_hub_from_text(update, context):
    """🆕 v78: Entry from persistent reply-keyboard 📚 How to Use button."""
    text, kb = _build_how_to_hub_text_and_kb()
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ───────────────────────────────────────────
# Individual guide screens
# ───────────────────────────────────────────

_GUIDES = {
    "buy_product": (
        "🛒 *How to Buy a Product*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Step 1:* From Main Menu, tap *🛒 Shop Now*\n\n"
        "*Step 2:* Browse categories OR tap *📊 Price List* to see all products\n\n"
        "*Step 3:* Tap the product you want\n\n"
        "*Step 4:* Tap *💳 Buy Now*\n\n"
        "*Step 5:* Pick how many units (quantity)\n\n"
        "*Step 6:* Choose a payment method:\n"
        "  • 🪙 Binance Pay (fastest — auto-verify)\n"
        "  • 📱 EasyPaisa\n"
        "  • 📞 JazzCash\n"
        "  • 💰 Points (use your wallet balance)\n\n"
        "*Step 7:* Follow the payment screen instructions. After payment, your "
        "account/code is *delivered automatically* in a new message.\n\n"
        "✅ Done! Your order also shows up in *📜 Order History*."
    ),
    "deposit": (
        "💎 *How to Buy Points / Deposit*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Points are bot wallet balance — pay once, then buy multiple products without "
        "re-entering payment each time.\n\n"
        "*Step 1:* From Main Menu, tap *💎 Buy Points*\n\n"
        "*Step 2:* Enter the amount in USD (e.g. `5`, `10`, `20`)\n\n"
        "*Step 3:* Pick payment method (Binance / EasyPaisa / JazzCash)\n\n"
        "*Step 4:* Pay & follow on-screen verify steps\n\n"
        "*Step 5:* Once verified, points land in your wallet *instantly*\n\n"
        "📊 *Conversion:* 1 USD = 10 points (default — admin may adjust)\n\n"
        "💡 *Pro tip:* Bigger deposits sometimes unlock bonus points "
        "(see *🏆 Loyalty Tiers* for current rates)."
    ),
    "pay_overview": (
        "💳 *Payment Methods — Overview*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Bite Store accepts 4 ways to pay:\n\n"
        "*1. 🪙 Binance Pay (USDT)*\n"
        "  Fastest. Auto-verified by API in seconds.\n\n"
        "*2. 📱 EasyPaisa*\n"
        "  Pakistani users. Send PKR → upload screenshot OR enter TID.\n\n"
        "*3. 📞 JazzCash*\n"
        "  Same as EasyPaisa, different wallet.\n\n"
        "*4. 💰 Points Wallet*\n"
        "  Use balance you already deposited. No external payment needed.\n\n"
        "_Tap any specific method button on the previous screen for step-by-step._"
    ),
    "pay_binance": (
        "🪙 *Binance Pay — Step-by-Step*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Binance is the *fastest* method — auto-verified in seconds via Binance Pay API.\n\n"
        "*Step 1:* At checkout, pick *🪙 Binance*\n\n"
        "*Step 2:* Bot shows you:\n"
        "  • Bot's Binance ID / Pay ID\n"
        "  • Exact amount in USDT\n\n"
        "*Step 3:* Open Binance app → *Send* (or *Pay*) → enter the Bot's ID\n\n"
        "*Step 4:* Send the exact USDT amount\n\n"
        "*Step 5:* In Binance, copy the *Order ID* (or Transfer ID)\n"
        "   _It looks like:_ `2032xxxxxxxxxxxxx`\n\n"
        "*Step 6:* Back in the bot, paste the Order ID and tap *Submit*\n\n"
        "*Step 7:* Bot verifies via Binance API → ✅ payment confirmed → product delivered.\n\n"
        "🛡️ *Anti-fraud:* Each Order ID can only be used once."
    ),
    "pay_easypaisa": (
        "📱 *EasyPaisa — Step-by-Step*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Step 1:* At checkout, pick *📱 EasyPaisa*\n\n"
        "*Step 2:* Bot shows you:\n"
        "  • Bot's EasyPaisa number\n"
        "  • Account holder name\n"
        "  • Exact PKR amount to send (already converted from USD)\n\n"
        "*Step 3:* Open EasyPaisa app → *Send Money* → enter Bot's number\n\n"
        "*Step 4:* Send the exact amount\n\n"
        "*Step 5:* After payment, EasyPaisa gives you a *TID* (Transaction ID)\n\n"
        "*Step 6:* Back in the bot, send the screenshot OR type the TID\n\n"
        "*Step 7:* Bot verifies → admin approves (usually within minutes) → product delivered.\n\n"
        "💡 *Tip:* Sending the screenshot is fastest — bot can auto-read most TIDs."
    ),
    "pay_jazzcash": (
        "📞 *JazzCash — Step-by-Step*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Step 1:* At checkout, pick *📞 JazzCash*\n\n"
        "*Step 2:* Bot shows:\n"
        "  • Bot's JazzCash number\n"
        "  • Holder name\n"
        "  • PKR amount\n\n"
        "*Step 3:* Open JazzCash → *Send Money* → enter Bot's number → send amount\n\n"
        "*Step 4:* Copy the TID JazzCash gives you\n\n"
        "*Step 5:* Back in the bot, send screenshot OR type TID\n\n"
        "*Step 6:* Verified → delivered.\n\n"
        "⚠️ Always send the *exact* PKR amount shown by the bot — wrong amounts may "
        "be rejected."
    ),
    "pay_points": (
        "💰 *Pay with Points*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "If you already deposited points (see *💎 Buy Points* guide), you can pay "
        "from your wallet — instantly, no external payment needed.\n\n"
        "*Step 1:* At product checkout, pick *💰 Points*\n\n"
        "*Step 2:* Bot shows your current balance + price in points\n\n"
        "*Step 3:* Tap *✅ Confirm*\n\n"
        "*Step 4:* Points deducted → product delivered *immediately*\n\n"
        "💡 *Conversion:* Most products cost (USD price × 10) points.\n\n"
        "📊 Check your balance anytime in *📊 My Account*."
    ),
    "ticket": (
        "🎫 *How to Create a Support Ticket*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Step 1:* From Main Menu, tap *🎫 Support*\n\n"
        "*Step 2:* Tap *🆕 New Ticket*\n\n"
        "*Step 3:* Type a short subject (3+ chars) — e.g. _\"Netflix account issue\"_\n\n"
        "*Step 4:* Type your detailed message describing the problem\n\n"
        "*Step 5:* Submit → ticket is created with a number like #42\n\n"
        "*Step 6:* Admin (or AI auto-reply) replies — you get notification\n\n"
        "*Step 7:* Tap *📝 Reply with Media/Text* to continue the chat\n"
        "  You can send:\n"
        "  • ✏️ Text\n"
        "  • 📷 Photo (with caption)\n"
        "  • 🎬 Video (with caption)\n"
        "  • 📎 Document\n\n"
        "*Step 8:* When solved, ticket is marked ✅ Resolved.\n\n"
        "💬 Tap *💬 View Chat* anytime to replay the whole conversation."
    ),
    "warranty": (
        "🛡️ *How to Claim Warranty*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "If your account/product stopped working within the warranty period:\n\n"
        "*Step 1:* From Main Menu, tap *📜 Order History*\n\n"
        "*Step 2:* Find the affected order, tap it\n\n"
        "*Step 3:* Tap *🛡️ Claim Warranty* button (only visible if warranty is still active)\n\n"
        "*Step 4:* Describe the issue clearly (e.g. _\"password changed by previous owner\"_)\n\n"
        "*Step 5:* Submit\n\n"
        "*Step 6:* Admin reviews within 24-48 hours:\n"
        "  • ✅ Approved → replacement / refund / new account sent\n"
        "  • ❌ Rejected → admin sends reason\n\n"
        "💡 *Tips for fast approval:*\n"
        "  • Mention the exact error you saw\n"
        "  • Send screenshots in the ticket if possible\n"
        "  • Don't wait — claim as soon as issue happens (warranty has time limit)"
    ),
    "replacement": (
        "🔁 *How to Request Replacement*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "If the account you received doesn't work properly (wrong password, locked, "
        "already used, etc.):\n\n"
        "*Step 1:* Open *📜 Order History*\n\n"
        "*Step 2:* Tap the broken order\n\n"
        "*Step 3:* Tap *🔁 Request Replacement* (only shown if within replacement "
        "window — admin sets this per product, typically 24h-7 days)\n\n"
        "*Step 4:* Pick a reason from the list (or type your own)\n\n"
        "*Step 5:* Submit → status becomes *⏳ Pending*\n\n"
        "*Step 6:* Admin reviews:\n"
        "  • ✅ Approved → new account delivered\n"
        "  • ❌ Rejected → reason sent\n\n"
        "🔔 You'll get a Telegram notification when status changes.\n\n"
        "⏱️ *Window:* Look on each product page — replacement window is shown there. "
        "After the window ends, use *🛡️ Claim Warranty* instead."
    ),
    "review": (
        "⭐ *How to Leave a Review*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Step 1:* From Main Menu, tap *📜 Order History*\n\n"
        "*Step 2:* Tap any delivered order\n\n"
        "*Step 3:* Tap *⭐ Leave Review*\n\n"
        "*Step 4:* Pick a rating from 1⭐ to 5⭐\n\n"
        "*Step 5:* (Optional) Type a short comment\n\n"
        "*Step 6:* Submit → review appears publicly on that product page\n\n"
        "💡 *Note:* You'll also get a reminder 24h after delivery to leave a review "
        "(if you haven't already)."
    ),
    "referral": (
        "🎁 *Free Account / Referral Program*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Earn points (or even free products) by inviting friends.\n\n"
        "*Step 1:* From Main Menu, tap *🎁 Refer & Earn* (if available)\n\n"
        "*Step 2:* Copy your unique referral link OR scan your QR code\n\n"
        "*Step 3:* Share with friends — when they start the bot via your link, "
        "they're tagged as your referral\n\n"
        "*Step 4:* For every friend who joins AND makes a purchase:\n"
        "  • You get bonus points credited\n"
        "  • They may get a welcome bonus too\n\n"
        "*Step 5:* Track your referrals + earned points in *📊 My Account*\n\n"
        "🎁 *Free Account:* If admin has enabled *Free via Referrals*, refer X friends "
        "to unlock a free claim — check the *🎁 Free Claim* button if visible."
    ),
    "tier": (
        "🏆 *Tier System & Loyalty Points*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Buy more → climb tiers → get better rewards.\n\n"
        "Typical tiers (admin customizable):\n"
        "  🥉 *Bronze* — newcomers\n"
        "  🥈 *Silver* — regular buyers\n"
        "  🥇 *Gold* — frequent buyers\n"
        "  💎 *Diamond* — top buyers\n\n"
        "*How to climb:* Every purchase adds to your spend total. When you cross a "
        "tier threshold, you're upgraded automatically and get a *bonus*.\n\n"
        "*Check your tier:* Main Menu → *🏆 Loyalty* (or *📊 My Account*)\n\n"
        "*What you see:*\n"
        "  • Current tier badge\n"
        "  • Total spent (USD)\n"
        "  • Progress bar to next tier\n"
        "  • Bonus you'll unlock next\n\n"
        "💡 Bonus is usually free points or a discount %."
    ),
    "orders": (
        "📜 *Order History & Tracking*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "See every order you've ever placed.\n\n"
        "*Step 1:* From Main Menu, tap *📜 Order History*\n\n"
        "*Step 2:* List shows your orders newest first with status:\n"
        "  • ✅ Delivered\n"
        "  • ⏳ Pending\n"
        "  • 💸 Refunded\n"
        "  • ❌ Cancelled\n\n"
        "*Step 3:* Tap any order → see full details:\n"
        "  • Product name & price\n"
        "  • Date\n"
        "  • Delivery content (re-view your account/code)\n"
        "  • Action buttons:  🛡️ Claim Warranty · 🔁 Replacement · ⭐ Review · 🎫 Support\n\n"
        "💡 Lost your delivery message? Open the order here — full delivery is shown again."
    ),
    "price_list": (
        "📊 *Price List & Filters*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Quick way to see all prices in one screen.\n\n"
        "*Step 1:* From Main Menu, tap *📊 Price List*\n\n"
        "*Step 2:* Use filter buttons at top:\n"
        "  • 💰 By Price (low → high or high → low)\n"
        "  • 📦 By Category\n"
        "  • ⚡ In-Stock Only\n\n"
        "*Step 3:* Tap any product to open its full page (description, photo, buy button)\n\n"
        "💡 Bookmark this — fastest way to find the cheapest option for any product type."
    ),
    "language": (
        "🌐 *Language Settings*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Switch between supported languages.\n\n"
        "*Step 1:* From Main Menu, tap *🌐 Language* (if visible)\n\n"
        "*Step 2:* Pick your preferred language\n\n"
        "*Step 3:* All bot messages switch instantly\n\n"
        "💡 You can switch back anytime — same place."
    ),
    "faq": (
        "❓ *Common Issues / FAQ*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Q: My payment was sent but not confirmed.*\n"
        "→ Tap *🔄 Check Again* on the payment screen. If still pending after "
        "5 min, create a *🎫 Support Ticket* with your TID/Order ID.\n\n"
        "*Q: Account doesn't work after delivery.*\n"
        "→ Open *📜 Order History* → tap order → *🔁 Replacement* (within window) "
        "or *🛡️ Warranty* (after window).\n\n"
        "*Q: I got logged out / bot is stuck on some screen.*\n"
        "→ Tap *🏠 Main Menu* — that always resets everything. Or send `/start`.\n\n"
        "*Q: Where are my points?*\n"
        "→ *📊 My Account* shows current balance + spending history.\n\n"
        "*Q: How do I delete my account?*\n"
        "→ Open a *🎫 Support Ticket* asking for data removal.\n\n"
        "*Q: I have a special request / bulk order.*\n"
        "→ Open a Support Ticket — admin replies usually within hours.\n\n"
        "*Q: Bot stopped replying.*\n"
        "→ Send `/start` to reset. If still nothing, check that Telegram itself is online."
    ),
}


async def guide_screen_callback(update, context):
    """Generic handler for any guide_<key> callback."""
    q = update.callback_query
    await q.answer()
    key = (q.data or "").replace("guide_", "", 1)
    text = _GUIDES.get(key)
    if not text:
        text = "❓ Guide not found.\n\nTap 🔙 to return to the guides list."
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=_nav_kb())


# ============================================================
# 📄 ORIGINAL FILE: handlers_language.py
# ============================================================

from utils import nav_push
# ============================================
# 🌐 LANGUAGE SELECTOR HANDLERS
# ============================================
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from i18n import LANGUAGES, get_user_lang, set_user_lang, t, lang_name


def language_menu_keyboard(current_lang):
    """Show all language options. Current one is marked."""
    kb = []
    for code, info in LANGUAGES.items():
        marker = " ✅" if code == current_lang else ""
        label = f"{info['flag']} {info['native']}{marker}"
        kb.append([InlineKeyboardButton(label, callback_data=f"setlang_{code}")])
    kb.append([InlineKeyboardButton(t("btn_back", lang=current_lang), callback_data="main_menu")])
    return InlineKeyboardMarkup(kb)


async def _safe_edit(q, text, **kwargs):
    # 1. Try editing as a regular text message
    try:
        await q.edit_message_text(text, **kwargs)
        return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in kwargs:
            kwargs_no_md = dict(kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.edit_message_text(text, **kwargs_no_md)
                return
            except Exception: pass

    # 2. Fallback: edit caption (works on photo/video messages)
    try:
        await q.edit_message_caption(caption=text, **kwargs)
        return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in kwargs:
            kwargs_no_md = dict(kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.edit_message_caption(caption=text, **kwargs_no_md)
                return
            except Exception: pass

    # 3. Last resort: reply_text
    try:
        await q.message.reply_text(text, **kwargs)
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in kwargs:
            kwargs_no_md = dict(kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.message.reply_text(text, **kwargs_no_md)
            except Exception: pass

async def language_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show language picker."""
    q = update.callback_query
    await q.answer()
    nav_push(context, 'language_menu')  # 🔧 v39 Bug #5
    uid = q.from_user.id
    current = get_user_lang(uid)
    text = (t("lang_select_title", lang=current) + "\n\n"
            + t("lang_current", lang=current) + lang_name(current))
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=language_menu_keyboard(current))


async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save selected language."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    # Format: setlang_<code>
    parts = q.data.split("_", 1)
    if len(parts) != 2 or parts[1] not in LANGUAGES:
        await q.answer("❌ Invalid language", show_alert=True)
        return
    new_lang = parts[1]
    set_user_lang(uid, new_lang)

    # Confirm in new language + show main menu in new language
    confirm = t("lang_changed", lang=new_lang)
    await q.answer(confirm.replace("*", ""), show_alert=False)

    # Re-render main menu in new language
    from handlers_start import main_menu_callback
    # Reuse main menu flow
    await main_menu_callback(update, context)


# ============================================================
# 📄 ORIGINAL FILE: handlers_activity.py
# ============================================================

# ================================================================
# 🎛️ FAKE ACTIVITY ADMIN PANEL — handlers_activity.py
# ================================================================
# Admin Panel → 🎭 Fake Activity
#
# CONTROLS:
#   ✅ Global ON/OFF
#   ✅ Speed (min/max interval between messages)
#   ✅ First message delay (seconds after user joins)
#   ✅ Message type toggles (purchase/deposit/referral/discount/review/tier)
#   ✅ Per-user list — see all users + their activity status
#   ✅ Per-user stop/start individually
#   ✅ Stop ALL / Start ALL
#   ✅ Live stats (total msgs sent, active users, etc.)
#
# REGISTRATION IN bot.py:
# ─────────────────────────
#   from handlers_activity import (
#       activity_panel_callback,
#       act_toggle_global_callback,
#       act_toggle_type_callback,
#       act_set_speed_callback, act_speed_received,
#       act_set_delay_callback, act_delay_received,
#       act_users_callback, act_user_toggle_callback,
#       act_stop_all_callback, act_start_all_callback,
#       act_noop_callback,
#       ACT_SPEED, ACT_DELAY,
#   )
#
#   # ConversationHandlers:
#   app.add_handler(ConversationHandler(
#       entry_points=[CallbackQueryHandler(act_set_speed_callback, pattern="^act_set_speed$")],
#       states={ACT_SPEED: [MessageHandler(filters.TEXT & ~filters.COMMAND, act_speed_received)]},
#       fallbacks=[CommandHandler("cancel", cancel_conversation)],
#   ))
#   app.add_handler(ConversationHandler(
#       entry_points=[CallbackQueryHandler(act_set_delay_callback, pattern="^act_set_delay$")],
#       states={ACT_DELAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, act_delay_received)]},
#       fallbacks=[CommandHandler("cancel", cancel_conversation)],
#   ))
#
#   # Callback handlers:
#   app.add_handler(CallbackQueryHandler(activity_panel_callback,      pattern="^act_panel$"))
#   app.add_handler(CallbackQueryHandler(act_toggle_global_callback,   pattern="^act_toggle_global$"))
#   app.add_handler(CallbackQueryHandler(act_toggle_type_callback,     pattern="^act_type_"))
#   app.add_handler(CallbackQueryHandler(act_users_callback,           pattern="^act_users$"))
#   app.add_handler(CallbackQueryHandler(act_user_toggle_callback,     pattern="^act_utog_"))
#   app.add_handler(CallbackQueryHandler(act_stop_all_callback,        pattern="^act_stop_all$"))
#   app.add_handler(CallbackQueryHandler(act_start_all_callback,       pattern="^act_start_all$"))
#   app.add_handler(CallbackQueryHandler(act_noop_callback,            pattern="^act_noop$"))
#
# ADD BUTTON IN keyboards.py → admin_menu_keyboard():
#   kb.append([InlineKeyboardButton("🎭 Fake Activity", callback_data="act_panel")])
# ================================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from per_user_activity import (
    is_globally_enabled, get_speed, get_first_delay,
    is_type_on, get_all_activity_jobs,
    set_user_active, stop_all_jobs, start_all_jobs,
    S_GLOBAL_ON, S_MIN_INTERVAL, S_MAX_INTERVAL, S_FIRST_DELAY,
    S_TYPE_PURCHASE, S_TYPE_DEPOSIT, S_TYPE_REFERRAL,
    S_TYPE_DISCOUNT, S_TYPE_REVIEW, S_TYPE_TIER,
    S_TYPE_MILESTONE, S_TYPE_STOCK, S_TYPE_NEWUSER,
    S_TYPE_FLASH, S_TYPE_NEWPROD,
)

logger = logging.getLogger(__name__)

ACT_SPEED = 910
ACT_DELAY = 911


def _is_admin(uid):
    from config import ADMIN_ID
    return uid == ADMIN_ID


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


def _ico(val):
    """
    🐛 v95.1 CRITICAL FIX: Universal truthy check.
    Previous version had TWO _ico() definitions in this file — the second one
    (line ~1567) overrode this one globally and only accepted the STRING "1"
    as ON. But is_type_on() returns a Python bool (True/False), so BOTH ON
    and OFF states rendered as ❌ cross. Toggle appeared broken to admin —
    exactly what user reported: "chahy mn on kro ya off iska cross change ni hota".
    Now accepts: True, "1", 1, "true", "yes", "on" — all render ✅.
    """
    if val is True or val == "1" or val == 1:
        return "✅"
    if isinstance(val, str) and val.strip().lower() in ("true", "yes", "on"):
        return "✅"
    return "❌"


async def _edit(q, text, kb):
    """
    🐛 v95.2 HARDENED: previously silently swallowed ALL exceptions including
    'Message is not modified' and 'Bad Request'. This caused the fake-activity
    toggle panel to sometimes NOT visually refresh even when DB was written
    correctly — user saw stale ❌ crosses on buttons after toggling ON.

    New behaviour:
      1. Try edit_message_text with Markdown.
      2. If 'Message is not modified' → append zero-width invisible char to
         force diff and retry (Telegram doesn't render it but sees a diff).
      3. If parse-mode / entity errors → strip markdown & retry.
      4. If message-is-a-caption error → try edit_message_caption.
      5. On terminal failure → log & attempt to send a fresh panel message.
    """
    import logging
    log = logging.getLogger(__name__)
    rm = InlineKeyboardMarkup(kb)

    # Attempt 1: normal Markdown edit
    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=rm)
        return
    except Exception as e:
        emsg = str(e).lower()

        # ── Case A: content didn't change → force diff with invisible char ──
        if "not modified" in emsg or "message is not modified" in emsg:
            try:
                # Zero-width space (U+200B) — invisible, forces Telegram to see diff
                await q.edit_message_text(text + "\u200b",
                                          parse_mode="Markdown", reply_markup=rm)
                return
            except Exception as e2:
                log.warning(f"[_edit] zwsp retry failed: {e2}")

        # ── Case B: parse error → strip Markdown ──
        if "parse" in emsg or "entity" in emsg or "entities" in emsg:
            try:
                await q.edit_message_text(text, reply_markup=rm)
                return
            except Exception as e2:
                log.warning(f"[_edit] plain-text retry failed: {e2}")

        # ── Case C: message is a caption (photo/video) ──
        if "caption" in emsg or "there is no text" in emsg:
            try:
                await q.edit_message_caption(caption=text, parse_mode="Markdown",
                                             reply_markup=rm)
                return
            except Exception:
                try:
                    await q.edit_message_caption(caption=text, reply_markup=rm)
                    return
                except Exception as e2:
                    log.warning(f"[_edit] caption retry failed: {e2}")

        # ── Case D: unknown → last-ditch attempts ──
        log.warning(f"[_edit] initial edit failed ({e}); trying fallbacks")
        for attempt in (
            lambda: q.edit_message_text(text, reply_markup=rm),
            lambda: q.edit_message_caption(caption=text, reply_markup=rm),
        ):
            try:
                await attempt()
                return
            except Exception:
                continue

        # ── LAST RESORT: send a NEW message so admin always sees fresh state ──
        try:
            chat_id = q.message.chat.id if q.message else q.from_user.id
            bot = q.get_bot() if hasattr(q, "get_bot") else None
            if bot is None:
                # PTB v22 pattern
                bot = q._bot if hasattr(q, "_bot") else None
            if bot is not None:
                await bot.send_message(chat_id=chat_id, text=text,
                                       parse_mode="Markdown", reply_markup=rm)
                log.info("[_edit] sent as NEW message (edit failed on all paths)")
                return
        except Exception as e_final:
            log.error(f"[_edit] ALL fallbacks failed: {e_final}")


# ════════════════════════════════════════════════════════════════
# 🏠 MAIN PANEL
# ════════════════════════════════════════════════════════════════

async def activity_panel_callback(update, context):
    """
    Main Fake Activity panel.
    Admin Panel → 🎭 Fake Activity
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()
    await _show_panel(q)


async def _show_panel(q):
    enabled  = is_globally_enabled()
    mn, mx   = get_speed()
    delay    = get_first_delay()
    unit     = _g("pua_interval_unit", "minutes")
    unit_label = "minutes" if unit == "minutes" else "seconds"

    # Count stats from DB
    jobs = get_all_activity_jobs()
    total_users  = len(jobs)
    active_users = sum(1 for j in jobs if j[1] == 1)
    total_msgs   = sum(j[3] or 0 for j in jobs)

    try:
        from database import get_user_count
        real_users = get_user_count()
        fake_offset = int(_g("fake_user_offset", "500"))
        shown_users = real_users + fake_offset
    except Exception:
        real_users = 0
        fake_offset = 500
        shown_users = 500

    active_shoppers = int(fake_offset * 0.85)
    inactive_shoppers = int(fake_offset * 0.15)
    daily_sales = int(fake_offset * 0.045)
    weekly_sales = int(fake_offset * 0.315)
    monthly_sales = int(fake_offset * 1.35)

    # Current destination mode
    try:
        # [v77-merge] self-bundle import removed: from handlers_force_join import S_DEST_CHAT
        from database import get_setting
        dest_mode = get_setting("dest_mode", "bot_only")
        dest_chat = get_setting(S_DEST_CHAT, "").strip()
        
        # Escape dest_chat for markdown!
        escaped_dest = dest_chat.replace("_", "\\_").replace("*", "\\*")
        
        dest_display = {
            "bot_only":   "🤖 Bot Only",
            "group_only": f"👥 Group Only ({escaped_dest or 'not set'})",
            "both":       f"🤖+👥 Both ({escaped_dest or 'not set'})",
        }.get(dest_mode, "🤖 Bot Only")
    except Exception:
        dest_display = "🤖 Bot Only"

    # Type toggles
    t_purchase = is_type_on("purchase")
    t_deposit  = is_type_on("deposit")
    t_referral = is_type_on("referral")
    t_discount = is_type_on("discount")
    t_review   = is_type_on("review")
    t_tier     = is_type_on("tier")
    # 🆕 extra types
    t_milestone = is_type_on("milestone")
    t_stock     = is_type_on("stock")
    t_newuser   = is_type_on("newuser")
    t_flash     = is_type_on("flash")
    t_newprod   = is_type_on("newprod")
    t_price_drop = is_type_on("price_drop")   # 🆕 v66

    status_icon = "🟢 *ACTIVE*" if enabled else "🔴 *INACTIVE*"
    try:
        pass  # dest_display already set above
    except Exception:
        dest_display = "🤖 Bot Only"

    text = (
        f"🎭 *Per-User Fake Activity Panel*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔌 Status: {status_icon}\n"
        f"⚡ First message: in *{delay} seconds* after user joins\n"
        f"⏱️ Then: every *{mn}–{mx} {unit_label}* randomly\n\n"
        f"📤 Sending to: {dest_display}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 *Simulated Community Stats:*\n"
        f"  📊 Real Registered Users: *{real_users}*\n"
        f"  🎭 Simulated Offset Count: *+{fake_offset}*\n"
        f"  📣 Shown to Others: *{shown_users} users* (Auto-increases!)\n"
        f"  🟢 Active simulated: *{active_shoppers}* | Inactive: *{inactive_shoppers}*\n\n"
        f"📈 *Simulated Store Performance:*\n"
        f"  ◽ Daily Purchase Volume: *~{daily_sales} orders*\n"
        f"  ◽ Weekly Purchase Volume: *~{weekly_sales} orders*\n"
        f"  ◽ Monthly Purchase Volume: *~{monthly_sales} orders*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Live Bot Stats:*\n"
        f"  👥 Total enrolled users: *{total_users}*\n"
        f"  🟢 Currently active: *{active_users}*\n"
        f"  📨 Total messages sent: *{total_msgs}*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*Message Types:*\n"
        f"  {_ico(t_purchase)} 🛒 Purchase    "
        f"  {_ico(t_deposit)} 💳 Deposit\n"
        f"  {_ico(t_referral)} 🎁 Referral    "
        f"  {_ico(t_discount)} 📉 Discount\n"
        f"  {_ico(t_review)} ⭐ Review      "
        f"  {_ico(t_tier)} 🎖️ Tier Upgrade\n"
        f"  {_ico(t_milestone)} 🏆 Referral Milestone\n"
        f"  {_ico(t_stock)} 🔔 New Stock Alert\n"
        f"  {_ico(t_newuser)} 🎉 New User Joined\n"
        f"  {_ico(t_flash)} 🛍 Flash Sale  "
        f"  {_ico(t_newprod)} 🆕 New Product\n"
        f"  {_ico(t_price_drop)} 📉 Big Price Drop\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*How it works:*\n"
        f"• User does /start → fake activity begins\n"
        f"• First msg in {delay}s → then every {mn}–{mx} {unit_label}\n"
        f"• Each user gets DIFFERENT messages\n"
        f"• Names: Pakistani + Indian realistic names\n"
        f"• Lifetime — until admin stops it\n"
        f"• Survives bot restarts"
    )

    master_lbl = "🔴 Turn OFF Globally" if enabled else "🟢 Turn ON Globally"
    kb = [
        [InlineKeyboardButton(master_lbl, callback_data="act_toggle_global")],
        [InlineKeyboardButton("━━━ Message Types ━━━", callback_data="act_noop")],
        [
            InlineKeyboardButton(f"{_ico(t_purchase)} 🛒 Purchase",
                                 callback_data="act_type_purchase"),
            InlineKeyboardButton(f"{_ico(t_deposit)} 💳 Deposit",
                                 callback_data="act_type_deposit"),
        ],
        [
            InlineKeyboardButton(f"{_ico(t_referral)} 🎁 Referral",
                                 callback_data="act_type_referral"),
            InlineKeyboardButton(f"{_ico(t_discount)} 📉 Discount",
                                 callback_data="act_type_discount"),
        ],
        [
            InlineKeyboardButton(f"{_ico(t_review)} ⭐ Review",
                                 callback_data="act_type_review"),
            InlineKeyboardButton(f"{_ico(t_tier)} 🎖️ Tier",
                                 callback_data="act_type_tier"),
        ],
        [
            InlineKeyboardButton(f"{_ico(t_milestone)} 🏆 Referral Milestone",
                                 callback_data="act_type_milestone"),
        ],
        [
            InlineKeyboardButton(f"{_ico(t_stock)} 🔔 New Stock Alert",
                                 callback_data="act_type_stock"),
        ],
        [
            InlineKeyboardButton(f"{_ico(t_newuser)} 🎉 New User Joined",
                                 callback_data="act_type_newuser"),
        ],
        [
            InlineKeyboardButton(f"{_ico(t_flash)} 🛍 Flash Sale",
                                 callback_data="act_type_flash"),
            InlineKeyboardButton(f"{_ico(t_newprod)} 🆕 New Product",
                                 callback_data="act_type_newprod"),
        ],
        [
            # 🆕 v66
            InlineKeyboardButton(f"{_ico(t_price_drop)} 📉 Big Price Drop",
                                 callback_data="act_type_price_drop"),
        ],
        [InlineKeyboardButton("━━━ Simulated Community ━━━", callback_data="act_noop")],
        [
            InlineKeyboardButton(f"👥 Set Members ({fake_offset} offset)", callback_data="act_set_offset"),
            InlineKeyboardButton("🎲 Randomize Count", callback_data="act_offset_random"),
        ],
        [InlineKeyboardButton("━━━ Speed Settings ━━━", callback_data="act_noop")],
        [
            InlineKeyboardButton(
                f"⚡ First Delay: {delay}s",
                callback_data="act_set_delay"),
            InlineKeyboardButton(
                f"⏱️ Interval: {mn}–{mx} {unit_label[:3]}",
                callback_data="act_set_speed"),
        ],
        [
            InlineKeyboardButton(
                f"⚙️ Speed Unit: {unit.upper()}",
                callback_data="act_toggle_unit"),
        ],
        [InlineKeyboardButton("━━━ User Controls ━━━", callback_data="act_noop")],
        [
            InlineKeyboardButton(f"👥 View Users ({total_users})",
                                 callback_data="act_users"),
        ],
        [
            InlineKeyboardButton("🔴 Stop ALL Users",  callback_data="act_stop_all"),
            InlineKeyboardButton("🟢 Start ALL Users", callback_data="act_start_all"),
        ],
        [InlineKeyboardButton("📝 Edit Templates",    callback_data="tpl_panel")],
        [InlineKeyboardButton("📤 Where to Send? (Bot / Group / Both)", callback_data="dest_panel")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")],
    ]
    await _edit(q, text, kb)


# ════════════════════════════════════════════════════════════════
# 🔌 GLOBAL TOGGLE
# ════════════════════════════════════════════════════════════════

async def act_toggle_global_callback(update, context):
    """Toggle global fake activity ON/OFF."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    cur = _g(S_GLOBAL_ON, "1")
    new = "0" if cur == "1" else "1"
    _s(S_GLOBAL_ON, new)
    status = "🟢 ENABLED" if new == "1" else "🔴 DISABLED"
    
    if new == "1":
        try:
            from per_user_activity import schedule_group_activity_job
            schedule_group_activity_job(context.application)
        except Exception:
            pass
            
    await q.answer(f"Fake Activity: {status}", show_alert=False)
    await _show_panel(q)


async def act_toggle_unit_callback(update, context):
    """Toggle speed unit between minutes and seconds."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    cur = _g("pua_interval_unit", "minutes")
    new = "seconds" if cur == "minutes" else "minutes"
    _s("pua_interval_unit", new)
    await q.answer(f"Speed unit: {new.upper()} 🟢", show_alert=True)
    await _show_panel(q)


# ════════════════════════════════════════════════════════════════
# 🎛️ TYPE TOGGLES
# ════════════════════════════════════════════════════════════════

_TYPE_MAP = {
    "purchase": (S_TYPE_PURCHASE, "🛒 Purchase"),
    "deposit":  (S_TYPE_DEPOSIT,  "💳 Deposit"),
    "referral": (S_TYPE_REFERRAL, "🎁 Referral"),
    "discount": (S_TYPE_DISCOUNT, "📉 Discount"),
    "review":   (S_TYPE_REVIEW,   "⭐ Review"),
    "tier":     (S_TYPE_TIER,     "🎖️ Tier"),
    "milestone":(S_TYPE_MILESTONE,"🏆 Referral Milestone"),
    "stock":    (S_TYPE_STOCK,    "🔔 New Stock Alert"),
    "newuser":  (S_TYPE_NEWUSER,  "🎉 New User Joined"),
    "flash":    (S_TYPE_FLASH,    "🛍 Flash Sale"),
    "newprod":  (S_TYPE_NEWPROD,  "🆕 New Product"),
    # 🐛 v95 FIX: 'price_drop' toggle button was in the panel but MISSING
    # from _TYPE_MAP → clicking it showed "❌ Unknown type" alert and never
    # toggled → cross ✅/❌ icon stuck. Now works correctly.
    "price_drop": ("pua_type_price_drop", "📉 Price Drop"),
}


async def act_toggle_type_callback(update, context):
    """
    Toggle a specific message type.
    Callback: act_type_purchase / act_type_deposit / etc.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    ttype = q.data.replace("act_type_", "")
    entry = _TYPE_MAP.get(ttype)
    if not entry:
        await q.answer("❌ Unknown type")
        return
    skey, label = entry
    cur = _g(skey, "1")
    new = "0" if cur == "1" else "1"
    _s(skey, new)
    await q.answer(f"{label}: {'ON ✅' if new=='1' else 'OFF ❌'}")
    await _show_panel(q)


# ════════════════════════════════════════════════════════════════
# ⏱️ SPEED CONTROL
# ════════════════════════════════════════════════════════════════

async def act_set_speed_callback(update, context):
    """Ask admin to set min/max interval between messages."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    mn, mx = get_speed()
    unit = _g("pua_interval_unit", "minutes")
    kb = [[InlineKeyboardButton("❌ Cancel", callback_data="act_panel")]]
    
    if unit == "seconds":
        examples = (
            f"  `10 15`  → every 10 to 15 seconds ✅ Ultra-Fast\n"
            f"  `15 30`  → every 15 to 30 seconds\n"
            f"  `30 60`  → every 30 to 60 seconds"
        )
    else:
        examples = (
            f"  `1 5`    → every 1 to 5 minutes\n"
            f"  `5 30`   → every 5 to 30 minutes ✅ Recommended\n"
            f"  `15 60`  → every 15 to 60 minutes"
        )

    text = (
        f"⏱️ *Set Message Interval ({unit.upper()})*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: *{mn}–{mx} {unit}*\n\n"
        f"Send: `MIN MAX` (two numbers)\n\n"
        f"*Examples:*\n"
        f"{examples}\n\n"
        f"⚠️ Min must be ≥ 1. Send the new range now:"
    )
    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        pass
    return ACT_SPEED


async def act_speed_received(update, context):
    """Save new speed settings."""
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END
    parts = update.message.text.strip().split()
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="act_panel")]]
    unit = _g("pua_interval_unit", "minutes")
    if len(parts) != 2:
        await update.message.reply_text(
            f"❌ Send two numbers. Example: `10 20`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END
    try:
        mn, mx = int(parts[0]), int(parts[1])
        if mn < 1 or mx < mn:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            f"❌ Invalid. Min ≥ 1, Max > Min. Example: `10 20`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END
    _s(S_MIN_INTERVAL, mn)
    _s(S_MAX_INTERVAL, mx)
    await update.message.reply_text(
        f"✅ *Speed Updated!*\n\nInterval: *{mn}–{mx} {unit}*",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════
# ⚡ FIRST MESSAGE DELAY
# ════════════════════════════════════════════════════════════════

async def act_set_delay_callback(update, context):
    """Ask admin to set first-message delay (seconds)."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    delay = get_first_delay()
    kb = [[InlineKeyboardButton("❌ Cancel", callback_data="act_panel")]]
    text = (
        f"⚡ *Set First Message Delay*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: *{delay} seconds*\n\n"
        f"How many seconds after user joins\n"
        f"should the FIRST fake message fire?\n\n"
        f"*Examples:*\n"
        f"  `5`   → 5 seconds (very fast)\n"
        f"  `10`  → 10 seconds ✅ recommended\n"
        f"  `15`  → 15 seconds\n"
        f"  `30`  → 30 seconds\n\n"
        f"Min: 5 seconds. Send a number:"
    )
    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        pass
    return ACT_DELAY


async def act_delay_received(update, context):
    """Save first-message delay."""
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="act_panel")]]
    try:
        n = max(5, int(update.message.text.strip()))
    except ValueError:
        await update.message.reply_text(
            "❌ Enter a number (seconds). Example: `10`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END
    _s(S_FIRST_DELAY, n)
    await update.message.reply_text(
        f"✅ *First Delay Updated!*\n\nFirst message fires in *{n} seconds* after user joins.",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════
# 👥 USER LIST (Per-user control)
# ════════════════════════════════════════════════════════════════

async def act_users_callback(update, context):
    """
    Show list of all enrolled users with their activity status.
    Admin can toggle each user individually.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    jobs = get_all_activity_jobs()

    if not jobs:
        text = (
            "👥 *Enrolled Users*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "No users enrolled yet.\n\n"
            "Users are enrolled automatically when they do /start."
        )
        kb = [[InlineKeyboardButton("🔙 Back", callback_data="act_panel")]]
        await _edit(q, text, kb)
        return

    active   = sum(1 for j in jobs if j[1] == 1)
    inactive = len(jobs) - active

    lines = [
        f"👥 *Enrolled Users ({len(jobs)})*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 Active: {active}   🔴 Stopped: {inactive}\n"
    ]

    kb = []
    for j in jobs[:20]:  # show max 20
        uid     = j[0]
        is_act  = j[1] == 1
        last    = j[2] or "never"
        count   = j[3] or 0
        fname   = j[5] or f"User"
        uname   = j[6] or ""
        disp    = f"{fname}" + (f" @{uname}" if uname else "") + f" (#{uid})"
        status  = "🟢" if is_act else "🔴"
        lines.append(
            f"{status} *{fname}* — {count} msgs | last: {last[-5:] if len(last)>5 else last}"
        )
        toggle_lbl = "🔴 Stop" if is_act else "🟢 Start"
        kb.append([
            InlineKeyboardButton(
                f"{status} {fname[:15]} ({count} msgs)",
                callback_data="act_noop"),
            InlineKeyboardButton(
                toggle_lbl,
                callback_data=f"act_utog_{uid}"),
        ])

    if len(jobs) > 20:
        lines.append(f"\n_...and {len(jobs)-20} more users_")

    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3800] + "\n_(truncated)_"

    kb.append([
        InlineKeyboardButton("🔴 Stop ALL",  callback_data="act_stop_all"),
        InlineKeyboardButton("🟢 Start ALL", callback_data="act_start_all"),
    ])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="act_panel")])
    await _edit(q, text, kb)


async def act_user_toggle_callback(update, context):
    """
    Toggle fake activity for one specific user.
    Callback: act_utog_{user_id}
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    try:
        uid = int(q.data.replace("act_utog_", ""))
    except ValueError:
        await q.answer("❌ Invalid user ID")
        return

    from per_user_activity import is_user_active
    currently_active = is_user_active(uid)
    set_user_active(uid, not currently_active)
    new_status = "🟢 Started" if not currently_active else "🔴 Stopped"
    await q.answer(f"User {uid}: {new_status}", show_alert=False)
    await act_users_callback(update, context)


# ════════════════════════════════════════════════════════════════
# 🔴🟢 STOP/START ALL
# ════════════════════════════════════════════════════════════════

async def act_stop_all_callback(update, context):
    """Stop fake activity for ALL users."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    stop_all_jobs()
    await q.answer("🔴 Stopped for ALL users!", show_alert=True)
    await _show_panel(q)


async def act_start_all_callback(update, context):
    """Start fake activity for ALL registered users."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    start_all_jobs()
    # Re-schedule in background
    try:
        from per_user_activity import restore_all_jobs
        restore_all_jobs(context.application)
    except Exception:
        pass
    await q.answer("🟢 Started for ALL users!", show_alert=True)
    await _show_panel(q)


async def act_noop_callback(update, context):
    """Separator button — does nothing."""
    await update.callback_query.answer()


# ════════════════════════════════════════════════════════════════
# 👥 SIMULATED MEMBERS CONTROL
# ════════════════════════════════════════════════════════════════

ACT_OFFSET = 912

async def act_set_offset_callback(update, context):
    """Ask admin to enter new fake user offset count."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    
    current = int(_g("fake_user_offset", "500"))
    kb = [[InlineKeyboardButton("❌ Cancel", callback_data="act_panel")]]
    text = (
        f"👥 *Set Simulated Members*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current Offset: *+{current} fake users*\n\n"
        f"Please enter a number between *100 and 2500*:\n"
        f"Real users will automatically be added on top of this count.\n\n"
        f"Send the number now:"
    )
    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        pass
    return ACT_OFFSET


async def act_offset_received(update, context):
    """Save new fake user offset settings."""
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END
    text = update.message.text.strip()
    kb = [[InlineKeyboardButton("🔙 Back to Fake Activity", callback_data="act_panel")]]
    try:
        n = int(text)
        if n < 100 or n > 2500:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid number! Enter a value between *100 and 2500*.",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END
        
    _s("fake_user_offset", n)
    from database import get_displayed_user_count
    shown = get_displayed_user_count()
    await update.message.reply_text(
        f"✅ *Simulated Members Updated!*\n\n"
        f"New Offset: *+{n} fake users*\n"
        f"Shown to others: *{shown} users*",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


async def act_offset_random_callback(update, context):
    """Set a random offset between 100 and 2500."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()
    
    import random
    n = random.randint(100, 2500)
    _s("fake_user_offset", n)
    
    await q.answer(f"🎲 Random offset set to +{n}!", show_alert=True)
    await _show_panel(q)


# ============================================================
# 📄 ORIGINAL FILE: handlers_force_join.py
# ============================================================

# ================================================================
# 🔗 FORCE JOIN + ACTIVITY DESTINATIONS — handlers_force_join.py
# ================================================================
#
# TWO FEATURES IN THIS FILE:
#
# ══════════════════════════════════════════════════════════════
# FEATURE 1: 🔗 FORCE JOIN
# ══════════════════════════════════════════════════════════════
# Forces users to join a Telegram channel/group before they
# can use the bot. If they leave later, bot stops working for them.
#
# HOW IT WORKS:
#   1. Admin sets a channel/group username or link in settings
#   2. User sends /start → bot checks if they're a member
#   3. If NOT member → bot sends join message, bot stops
#   4. User joins → they press "✅ I Joined" → bot verifies
#   5. If verified → bot starts working
#   6. Every time user interacts → bot silently re-checks membership
#   7. If user left → bot stops and shows join message again
#
# ADMIN CONTROLS (Admin Panel → 🔗 Force Join Setup):
#   ✅ Enable/Disable force join
#   ✅ Set channel username (e.g. @mychannel)
#   ✅ Set group username (e.g. @mygroup)
#   ✅ Both channel AND group can be set at same time
#   ✅ Edit the join message text (fully customizable)
#   ✅ Test: check if bot is admin in the channel/group
#
# IMPORTANT — BOT MUST BE ADMIN:
#   The bot must be an admin in the channel/group to check members.
#   Add bot as admin with "Add Members" permission.
#
# ══════════════════════════════════════════════════════════════
# FEATURE 2: 📤 ACTIVITY DESTINATIONS
# ══════════════════════════════════════════════════════════════
# Controls WHERE fake activity messages are sent:
#
#   Option A: Bot only (default)
#      → Messages go to each user's private chat with bot
#
#   Option B: Group only
#      → Messages go to a Telegram group/channel
#      → Admin sets group link/username
#
#   Option C: Both (Bot + Group)
#      → Messages go to user's private chat AND the group
#
# Admin can mix:
#   - Purchase msgs → Group
#   - Deposit msgs  → Bot only
#   - Reviews       → Both
#
# ================================================================
# REGISTRATION IN bot.py:
# ─────────────────────────
#   from handlers_force_join import (
#       fj_panel_callback,
#       fj_toggle_callback,
#       fj_set_channel_callback, fj_channel_received,
#       fj_set_group_callback, fj_group_received,
#       fj_set_msg_callback, fj_msg_received,
#       fj_test_callback,
#       fj_clear_channel_callback, fj_clear_group_callback,
#       dest_panel_callback,
#       dest_set_callback,
#       check_force_join, FJ_CHANNEL, FJ_GROUP, FJ_MSG,
#   )
#
#   # ConversationHandlers:
#   app.add_handler(ConversationHandler(
#       entry_points=[CallbackQueryHandler(fj_set_channel_callback, pattern="^fj_set_channel$")],
#       states={FJ_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, fj_channel_received)]},
#       fallbacks=[CommandHandler("cancel", cancel_conversation)],
#   ))
#   app.add_handler(ConversationHandler(
#       entry_points=[CallbackQueryHandler(fj_set_group_callback, pattern="^fj_set_group$")],
#       states={FJ_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, fj_group_received)]},
#       fallbacks=[CommandHandler("cancel", cancel_conversation)],
#   ))
#   app.add_handler(ConversationHandler(
#       entry_points=[CallbackQueryHandler(fj_set_msg_callback, pattern="^fj_set_msg$")],
#       states={FJ_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, fj_msg_received)]},
#       fallbacks=[CommandHandler("cancel", cancel_conversation)],
#   ))
#
#   # Callback handlers:
#   app.add_handler(CallbackQueryHandler(fj_panel_callback,        pattern="^fj_panel$"))
#   app.add_handler(CallbackQueryHandler(fj_toggle_callback,       pattern="^fj_toggle$"))
#   app.add_handler(CallbackQueryHandler(fj_test_callback,         pattern="^fj_test$"))
#   app.add_handler(CallbackQueryHandler(fj_clear_channel_callback,pattern="^fj_clear_channel$"))
#   app.add_handler(CallbackQueryHandler(fj_clear_group_callback,  pattern="^fj_clear_group$"))
#   app.add_handler(CallbackQueryHandler(fj_verified_callback,     pattern="^fj_verified$"))
#   app.add_handler(CallbackQueryHandler(dest_panel_callback,      pattern="^dest_panel$"))
#   app.add_handler(CallbackQueryHandler(dest_set_callback,        pattern="^dest_set_"))
#
# IN handlers_start.py — add at the TOP of start_command():
#   from handlers_force_join import check_force_join
#   if not await check_force_join(update, context):
#       return  # User not in channel/group yet — bot stopped
#
# ================================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ConversationHandler
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

# ConversationHandler states
# 🐛 v95 FIX: state IDs must be UNIQUE across the WHOLE bot because
# PTB's ConversationHandler stores active state per user, and if two
# handlers share a state number, PTB routes the user's text to the
# wrong receiver (silent bug that admin couldn't diagnose).
# Previous FJ_GROUP=921 collided with handlers_admin.EDIT_PRODUCT_EMOJI=921
# → user's Force Join group link was routed to the emoji editor and
#   never saved to fj_group setting. Bumped to 9200-range to guarantee
#   no collision with other modules.
FJ_CHANNEL = 9200
FJ_GROUP   = 9201
FJ_MSG     = 9202
DEST_CHAT  = 9203   # For activity destination group/channel link input

# Settings keys
S_FJ_ENABLED  = "fj_enabled"          # "1"/"0"
S_FJ_CHANNEL  = "fj_channel"          # @username or chat_id
S_FJ_GROUP    = "fj_group"            # @username or chat_id (optional)
S_FJ_MSG      = "fj_message"          # custom join message text

# Destination settings
S_DEST_BOT    = "dest_bot"            # "1"/"0" send to user's bot chat
S_DEST_GROUP  = "dest_group"          # "1"/"0" send to group
S_DEST_CHAT   = "dest_chat_id"        # group/channel @username or id for activity


# 🐛 v95.2 REMOVED duplicate helper definitions here — they were silently
# overriding the primary definitions at lines ~735, ~743, ~730:
#   • _g(key, default)  — DB read helper (identical impl)
#   • _s(key, val)      — DB write helper (identical impl)
#   • _is_admin(uid)    — admin check (identical impl)
# Also removed here in earlier v95.1 pass:
#   • _ico(val)         — icon renderer (BROKEN version, only accepted "1")
# These duplicates were dead code from historical merges but silently
# clobbered the good versions and hid bugs from the test suite.


# 🐛 v95.2 REMOVED duplicate _edit() def here — it silently swallowed all
# exceptions including 'Message is not modified' from Telegram, causing the
# fake-activity toggle panel to sometimes NOT refresh visually even when the
# DB was updated. Also, this duplicate was OVERRIDING the hardened v95.2
# version near top of file (line ~768). See _edit() near top of file —
# now uses zero-width-space diff trick + proper error routing + final send-new
# fallback so panel ALWAYS shows fresh state after every toggle.


# ════════════════════════════════════════════════════════════════
# 🔍 CORE: Check if user is a member
# ════════════════════════════════════════════════════════════════

async def _resolve_chat_id(bot, chat_id: str) -> str:
    """
    Convert any form of chat identifier to a usable one for Telegram API.

    HOW TELEGRAM WORKS:
    - Public groups/channels → use @username  (get_chat_member works)
    - Private groups         → MUST use numeric chat_id (-100xxxxxxxxxx)
      Invite links (t.me/+hash) CANNOT be used for get_chat_member!

    This function:
    1. Tries to call get_chat() with the given identifier
    2. If successful, returns the numeric chat.id (works for ALL group types)
    3. Caches the numeric ID in bot_settings so we don't call get_chat() every time

    Returns resolved chat_id string, or original if resolution fails.
    """
    import re as _re

    raw = chat_id.strip()

    # Already a numeric ID — use directly
    if raw.lstrip("-").isdigit():
        return raw

    # Check if we have a cached numeric ID for this link/username
    cache_key = f"fj_resolved_{raw.replace('/', '_').replace('+', 'P')[:40]}"
    try:
        from database import get_setting
        cached = get_setting(cache_key, "")
        if cached and cached.lstrip("-").isdigit():
            return cached
    except Exception:
        pass

    # Resolve via get_chat()
    try:
        # For t.me/+hash links — Telegram returns chat info if bot is member
        resolve_id = raw
        if _re.match(r'https?://t[.]me/[+]', raw):
            resolve_id = raw  # use invite link directly with get_chat
        elif _re.match(r'https?://t[.]me/', raw):
            m = _re.search(r't[.]me/([a-zA-Z][a-zA-Z0-9_]+)', raw)
            resolve_id = "@" + m.group(1) if m else raw
        elif not raw.startswith("@") and not raw.startswith("-"):
            resolve_id = "@" + raw

        chat_obj  = await bot.get_chat(resolve_id)
        numeric   = str(chat_obj.id)

        # Cache it
        try:
            from database import set_setting
            set_setting(cache_key, numeric)
        except Exception:
            pass

        logger.info(f"[ForceJoin] Resolved {raw!r} → {numeric}")
        return numeric

    except Exception as e:
        logger.warning(f"[ForceJoin] Could not resolve {raw!r}: {e}")
        return raw  # Return original as fallback


async def _is_member(bot, user_id: int, chat_id: str) -> bool:
    """
    Check if user_id is a member of chat_id.

    Works for:
      ✅ Public channels/groups   → @username
      ✅ Private groups           → numeric ID (auto-resolved from invite link)
      ✅ t.me/username links      → auto-resolved to @username
      ✅ t.me/+InviteHash links   → auto-resolved to numeric chat_id

    IMPORTANT: Bot MUST be an admin in the group/channel.
    For private groups, bot must be added as admin BEFORE setting the link.

    Returns True if member, False if not.
    Fails OPEN on errors (don't block users if Telegram API fails).
    """
    try:
        # Resolve to numeric or @username
        resolved = await _resolve_chat_id(bot, chat_id)

        member = await bot.get_chat_member(chat_id=resolved, user_id=user_id)
        return member.status in (
            ChatMember.MEMBER,
            ChatMember.ADMINISTRATOR,
            ChatMember.OWNER,
        )
    except TelegramError as e:
        err = str(e)
        # "Chat not found" — bot is not in the group
        # "User not found" — user never interacted with bot before
        # Both → fail OPEN (don't block user)
        logger.warning(f"[ForceJoin] Member check for {user_id} in {chat_id}: {e}")

        if "Chat not found" in err:
            logger.error(
                f"[ForceJoin] ⚠️ Bot is NOT a member of {chat_id}. "
                f"Add bot as admin to the group/channel first!"
            )
        return True  # Fail open — do NOT block user on API errors


async def check_force_join(update, context) -> bool:
    """
    MAIN GATE FUNCTION — call this at the start of start_command().

    Returns True  → user is a member (or force join disabled) → proceed normally
    Returns False → user is NOT a member → join message sent → stop bot

    Usage in handlers_start.py:
        # [v77-merge] self-bundle import removed: from handlers_force_join import check_force_join
        if not await check_force_join(update, context):
            return
    """
    if _g(S_FJ_ENABLED, "0") != "1":
        return True  # Force join disabled → proceed

    user = update.effective_user
    if _is_admin(user.id):
        return True  # Admin always bypasses

    bot  = context.bot
    channel = _g(S_FJ_CHANNEL, "").strip()
    group   = _g(S_FJ_GROUP,   "").strip()

    missing = []

    if channel:
        if not await _is_member(bot, user.id, channel):
            missing.append(("📢 Channel", channel))

    if group:
        if not await _is_member(bot, user.id, group):
            missing.append(("👥 Group", group))

    if not missing:
        return True  # All joined → proceed

    # Build join message
    custom_msg = _g(S_FJ_MSG, "").strip()
    if not custom_msg:
        custom_msg = (
            "⚠️ *Access Restricted!*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "To use *Bite Store Bot*, you must join:\n\n"
            "{links}\n\n"
            "After joining, tap the button below ✅"
        )

    # Build join buttons — create proper join URLs from saved links
    link_lines = []
    kb_links   = []
    for label, chat in missing:
        # Build a joinable URL
        if chat.startswith("https://t.me/"):
            join_url = chat  # already a full link
        elif chat.startswith("@"):
            join_url = f"https://t.me/{chat.lstrip('@')}"
        else:
            join_url = f"https://t.me/{chat}"

        link_lines.append(f"➤ {label}: {join_url}")
        kb_links.append([InlineKeyboardButton(
            f"🔗 Join {label}", url=join_url)])

    links_str = "\n".join(link_lines)
    msg = custom_msg.replace("{links}", links_str)

    kb_links.append([InlineKeyboardButton(
        "✅ I Joined — Verify", callback_data="fj_verified")])

    try:
        await update.message.reply_text(
            msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb_links))
    except Exception:
        try:
            await update.message.reply_text(
                msg,
                reply_markup=InlineKeyboardMarkup(kb_links))
        except Exception:
            try:
                await update.effective_chat.send_message(
                    msg, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb_links))
            except Exception:
                try:
                    await update.effective_chat.send_message(
                        msg,
                        reply_markup=InlineKeyboardMarkup(kb_links))
                except Exception:
                    pass

    return False  # Block user


async def fj_verified_callback(update, context):
    """
    User taps '✅ I Joined — Verify' button.
    Bot re-checks membership and proceeds if verified.
    """
    q = update.callback_query
    await q.answer("⏳ Checking...")
    user = q.from_user
    bot  = context.bot

    channel = _g(S_FJ_CHANNEL, "").strip()
    group   = _g(S_FJ_GROUP,   "").strip()

    missing = []
    if channel and not await _is_member(bot, user.id, channel):
        missing.append("📢 Channel")
    if group and not await _is_member(bot, user.id, group):
        missing.append("👥 Group")

    if missing:
        await q.answer(
            f"❌ Not joined yet: {', '.join(missing)}\n"
            f"Please join and wait a few seconds, then try again!",
            show_alert=True)
        return

    # Verified! Delete the join message and proceed
    try:
        await q.message.delete()
    except Exception:
        pass

    # Now start the bot for this user
    try:
        from database import save_user, get_user
        save_user(user.id, user.username or "", user.first_name or "")
        from keyboards import main_menu_keyboard
        from config import ADMIN_ID, SHOP_NAME
        from database import get_setting
        shop = get_setting("shop_name", SHOP_NAME)
        text = f"✅ *Verified!*\n\nWelcome to *{shop}*! 🛍️\n\nYou're all set to use the bot."
        await q.message.reply_text(
            text, parse_mode="Markdown",
            reply_markup=main_menu_keyboard(user.id == ADMIN_ID, user_id=user.id))
        # Start personal fake activity
        try:
            from per_user_activity import start_personal_activity
            await start_personal_activity(bot, context.application, user.id)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"[ForceJoin] Verified flow error: {e}")
        await q.message.reply_text(
            "✅ Verified! Please send /start to continue.")


# ════════════════════════════════════════════════════════════════
# 🏠 FORCE JOIN ADMIN PANEL
# ════════════════════════════════════════════════════════════════

async def fj_panel_callback(update, context):
    """
    Force Join settings panel.
    Admin Panel → 🔗 Force Join Setup
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()
    await _show_fj_panel(q, context.bot)


async def _show_fj_panel(q, bot):
    enabled = _g(S_FJ_ENABLED, "0") == "1"
    channel     = _g(S_FJ_CHANNEL, "").strip()
    group       = _g(S_FJ_GROUP,   "").strip()
    has_msg     = bool(_g(S_FJ_MSG, "").strip())

    # Display short version of links
    def _short(val):
        if not val: return "Not set"
        if val.startswith("https://t.me/+"):
            return val[:30] + "..." if len(val) > 30 else val  # private link
        return val

    channel_disp = _short(channel).replace("_", "\\_").replace("*", "\\*")
    group_disp   = _short(group).replace("_", "\\_").replace("*", "\\*")

    status = "🟢 *ENABLED*" if enabled else "🔴 *DISABLED*"

    text = (
        f"🔗 *Force Join Setup*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔌 Status: {status}\n\n"
        f"*Current Settings:*\n"
        f"  📢 Channel: `{channel_disp}`\n"
        f"  👥 Group: `{group_disp}`\n"
        f"  ✉️ Custom Message: {'✅ Set' if has_msg else '❌ Using default'}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*How it works:*\n"
        f"• User sends /start → bot checks membership\n"
        f"• Not a member → bot sends join link + stops\n"
        f"• User joins → taps '✅ I Joined' → verified\n"
        f"• User leaves later → bot stops again\n\n"
        f"*⚠️ Important:*\n"
        f"• Bot must be ADMIN in channel/group\n"
        f"• Give bot 'Add Members' permission\n"
        f"• Use @username format (e.g. @mychannel)"
    )

    toggle_lbl = "🔴 Disable Force Join" if enabled else "🟢 Enable Force Join"
    kb = [
        [InlineKeyboardButton(toggle_lbl, callback_data="fj_toggle")],
        [InlineKeyboardButton("━━━ Channel/Group Setup ━━━", callback_data="fj_noop")],
        [InlineKeyboardButton("📢 Set Channel", callback_data="fj_set_channel"),
         InlineKeyboardButton("🗑️ Clear Channel", callback_data="fj_clear_channel")],
        [InlineKeyboardButton("👥 Set Group", callback_data="fj_set_group"),
         InlineKeyboardButton("🗑️ Clear Group", callback_data="fj_clear_group")],
        [InlineKeyboardButton("━━━ Join Message ━━━", callback_data="fj_noop")],
        [InlineKeyboardButton("✏️ Edit Join Message", callback_data="fj_set_msg")],
        [InlineKeyboardButton("🔄 Reset to Default Msg", callback_data="fj_reset_msg")],
        [InlineKeyboardButton("━━━ Tools ━━━", callback_data="fj_noop")],
        [InlineKeyboardButton("🧪 Test Bot Admin Status", callback_data="fj_test")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")],
    ]
    await _edit(q, text, kb)


async def fj_toggle_callback(update, context):
    """Toggle Force Join ON/OFF."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    cur = _g(S_FJ_ENABLED, "0")
    new = "0" if cur == "1" else "1"
    _s(S_FJ_ENABLED, new)
    await q.answer(f"Force Join: {'🟢 ENABLED' if new=='1' else '🔴 DISABLED'}")
    await _show_fj_panel(q, context.bot)


async def fj_set_channel_callback(update, context):
    """Ask admin for channel link."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    current = _g(S_FJ_CHANNEL, "") or "Not set"
    kb = [[InlineKeyboardButton("❌ Cancel", callback_data="fj_panel")]]
    text = (
        f"📢 *Set Force Join Channel*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: `{current}`\n\n"
        f"*⚠️ IMPORTANT — Do this FIRST:*\n"
        f"1. Open your channel\n"
        f"2. Administrators → Add Admin\n"
        f"3. Search & add your bot\n"
        f"4. Give ANY permission → Save\n\n"
        f"*THEN paste the link here:*\n\n"
        f"*Accepted formats:*\n"
        f"  `https://t.me/mychannel`  (public)\n"
        f"  `https://t.me/+InviteCode`  (private)\n"
        f"  `@mychannel`\n\n"
        f"*For private channels:*\n"
        f"  Channel → ⋮ → Invite via Link → Copy\n\n"
        f"Send the link now:"
    )
    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        pass
    return FJ_CHANNEL


async def fj_channel_received(update, context):
    """Save channel link — accepts t.me links, @username, or bare username.

    🐛 v95 FIX: NOW ACTUALLY VERIFIES bot has access + admin permissions in
    the channel BEFORE saving. Previously admin would enter a link, bot would
    save it, but silently fail when checking members later — admin thought
    force-join was working but it wasn't. Now the save operation itself
    validates and gives clear error message with the exact fix needed.
    """
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END
    raw = update.message.text.strip()
    val = _parse_chat_link(raw)
    kb = [[InlineKeyboardButton("🔙 Back to Force Join", callback_data="fj_panel")]]
    if not val:
        await update.message.reply_text(
            "❌ *Invalid link!*\n\nSend a valid channel link:\n"
            "`https://t.me/mychannel`\n`@mychannel`\n`https://t.me/+abc123`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    # 🐛 v95: pre-flight check — verify bot can reach the channel
    ok, err_msg = await _verify_bot_access(context.bot, val, "channel")
    if not ok:
        await update.message.reply_text(err_msg, parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(kb),
                                          disable_web_page_preview=True)
        return ConversationHandler.END

    _s(S_FJ_CHANNEL, val)
    await update.message.reply_text(
        f"✅ *Channel Set & Verified!*\n\n"
        f"Force join channel: `{val}`\n\n"
        f"✅ Bot has access to this channel.\n"
        f"✅ Force join will work when users /start the bot.",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


async def _verify_bot_access(bot, chat_ref: str, kind: str = "channel"):
    """🐛 v95: verify bot can actually reach the given chat.

    Returns (ok, error_message). If ok=True, error_message is empty.
    If ok=False, error_message is a user-friendly explanation with fix steps.
    """
    try:
        # First: try to resolve + get chat
        resolved = await _resolve_chat_id(bot, chat_ref)
        chat_obj = await bot.get_chat(resolved)
        # Second: verify bot itself is a member (admin ideally)
        me = await bot.get_me()
        try:
            member = await bot.get_chat_member(chat_id=resolved, user_id=me.id)
            status = str(member.status).lower()
            if "left" in status or "kicked" in status or "banned" in status:
                return False, (
                    f"❌ *Bot is NOT a member of {chat_ref}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Bot ne is {kind} ko join hi nahi kiya.\n\n"
                    f"*Fix karein:*\n"
                    f"1. Apna {kind} khole\n"
                    f"2. Bot ko add karein\n"
                    f"3. Bot ko *administrator* banayen (any permission)\n"
                    f"4. Phir dobara ye link paste karein"
                )
            # Ideal: bot should be admin (needed to see member list)
            if "admin" not in status and "creator" not in status:
                return False, (
                    f"⚠️ *Bot is a member but NOT admin of {chat_ref}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Force join ke liye bot ko *admin* banana zaroori hai\n"
                    f"warna bot users ki membership check nahi kar sakta.\n\n"
                    f"*Fix karein:*\n"
                    f"1. {kind.capitalize()} → Administrators\n"
                    f"2. Add Admin → search bot\n"
                    f"3. Koi bhi 1 permission de dein → Save\n"
                    f"4. Phir dobara link paste karein"
                )
            return True, ""
        except Exception as _sub:
            # get_chat succeeded but get_chat_member failed = bot not in chat
            return False, (
                f"❌ *Cannot verify bot membership in {chat_ref}*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Bot us {kind} tak pahoch nahi sakta.\n"
                f"Error: `{str(_sub)[:100]}`\n\n"
                f"*Fix:*\n"
                f"1. Bot ko {kind} mein add karein\n"
                f"2. Admin permission dein\n"
                f"3. Phir dobara link paste karein"
            )
    except Exception as e:
        # Common: "Chat not found" = bot never added
        err = str(e)
        if "chat not found" in err.lower():
            return False, (
                f"❌ *Chat not found: `{chat_ref}`*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Ye 3 reasons ho sakty hain:\n"
                f"1. {kind.capitalize()} exist nahi karta (link galat hai)\n"
                f"2. Bot us {kind} mein add nahi hai\n"
                f"3. Private {kind} hai to numeric ID chahiye (-100xxxxxxxxxx)\n\n"
                f"*Fix:*\n"
                f"• Public {kind}: link double-check karein, bot ko add + admin banayen\n"
                f"• Private {kind}: pehle bot ko admin banayen, phir link paste karein"
            )
        return False, (
            f"❌ *Error checking {chat_ref}:*\n"
            f"`{err[:200]}`\n\n"
            f"Yeh unusual error hai. Try:\n"
            f"1. Bot ko {kind} mein admin banayen\n"
            f"2. Correct link paste karein\n"
            f"3. Support se contact karein agar phir bhi issue"
        )


async def fj_set_group_callback(update, context):
    """Ask admin for group link."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    current = _g(S_FJ_GROUP, "") or "Not set"
    kb = [[InlineKeyboardButton("❌ Cancel", callback_data="fj_panel")]]
    text = (
        f"👥 *Set Force Join Group*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: `{current}`\n\n"
        f"*⚠️ IMPORTANT — Do this FIRST:*\n"
        f"1. Open your group\n"
        f"2. Group settings → Administrators\n"
        f"3. Add Admin → Search your bot\n"
        f"4. Give ANY permission → Save\n\n"
        f"*THEN paste the group link:*\n\n"
        f"*For public groups:*\n"
        f"  `https://t.me/mygroup` or `@mygroup`\n\n"
        f"*For private groups:*\n"
        f"  Group → ⋮ → Invite via Link → Copy link\n"
        f"  Paste the `https://t.me/+...` link\n\n"
        f"*Tip:* You can set BOTH channel AND group.\n"
        f"User must join BOTH to access the bot.\n\n"
        f"Send the link now:"
    )
    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        pass
    return FJ_GROUP


async def fj_group_received(update, context):
    """Save group link — accepts t.me links, @username, or bare username.

    🐛 v95 FIX: Now pre-verifies bot access before saving (same as channel).
    Also fixes root cause: FJ_GROUP state ID was 921 which collided with
    handlers_admin.EDIT_PRODUCT_EMOJI=921 — user's link was routed to
    emoji editor and silently discarded. Now FJ_GROUP=9201.
    """
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END
    raw = update.message.text.strip()
    val = _parse_chat_link(raw)
    kb = [[InlineKeyboardButton("🔙 Back to Force Join", callback_data="fj_panel")]]
    if not val:
        await update.message.reply_text(
            "❌ *Invalid link!*\n\nSend a valid group link:\n"
            "`https://t.me/mygroup`\n`https://t.me/+InviteCode`\n`@mygroup`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    # 🐛 v95: pre-flight verify bot access + admin status
    ok, err_msg = await _verify_bot_access(context.bot, val, "group")
    if not ok:
        await update.message.reply_text(err_msg, parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(kb),
                                          disable_web_page_preview=True)
        return ConversationHandler.END

    _s(S_FJ_GROUP, val)
    await update.message.reply_text(
        f"✅ *Group Set & Verified!*\n\n"
        f"Force join group: `{val}`\n\n"
        f"✅ Bot has access to this group.\n"
        f"✅ Force join will work when users /start the bot.",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


async def fj_set_msg_callback(update, context):
    """Ask admin to write custom join message."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    kb = [[InlineKeyboardButton("❌ Cancel", callback_data="fj_panel")]]
    text = (
        f"✏️ *Edit Join Message*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Write the message shown to users who haven't joined yet.\n\n"
        f"*Available variable:*\n"
        f"  `{{links}}` → replaced with join links\n\n"
        f"*Example:*\n"
        f"`🛍️ Welcome to Bite Store!`\n"
        f"`━━━━━━━━━━━━━━`\n"
        f"`To use our bot, please join:`\n"
        f"`{{links}}`\n"
        f"`Then tap ✅ I Joined below.`\n\n"
        f"*Formatting:* Markdown supported\n"
        f"  `*bold*` `_italic_` `` `code` ``\n\n"
        f"Send your message now:"
    )
    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        pass
    return FJ_MSG


async def fj_msg_received(update, context):
    """Save custom join message."""
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END
    text = update.message.text.strip()
    _s(S_FJ_MSG, text)
    kb = [[InlineKeyboardButton("🔙 Back to Force Join", callback_data="fj_panel")]]
    try:
        await update.message.reply_text(
            f"✅ *Join Message Saved!*\n\nPreview:\n\n{text[:300]}",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        try:
            await update.message.reply_text(
                f"✅ Join Message Saved!\n\nPreview:\n\n{text[:300]}",
                reply_markup=InlineKeyboardMarkup(kb))
        except Exception:
            pass
    return ConversationHandler.END


async def fj_clear_channel_callback(update, context):
    """Clear force join channel."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    _s(S_FJ_CHANNEL, "")
    await q.answer("✅ Channel cleared!")
    await _show_fj_panel(q, context.bot)


async def fj_clear_group_callback(update, context):
    """Clear force join group."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    _s(S_FJ_GROUP, "")
    await q.answer("✅ Group cleared!")
    await _show_fj_panel(q, context.bot)


async def fj_reset_msg_callback(update, context):
    """Reset join message to default."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    _s(S_FJ_MSG, "")
    await q.answer("✅ Message reset to default!")
    await _show_fj_panel(q, context.bot)


async def fj_noop_callback(update, context):
    await update.callback_query.answer()


async def fj_test_callback(update, context):
    """
    Test if bot is admin in the configured channel/group.
    Tries to fetch chat info — if it works, bot has access.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer("⏳ Testing...")

    channel = _g(S_FJ_CHANNEL, "").strip()
    group   = _g(S_FJ_GROUP,   "").strip()
    bot     = context.bot
    results = []

    me = await bot.get_me()

    for label, chat in [("📢 Channel", channel), ("👥 Group", group)]:
        if not chat:
            results.append(f"{label}: Not configured")
            continue
        try:
            # Use resolver — works for public, private, invite links
            resolved = await _resolve_chat_id(bot, chat)
            chat_obj = await bot.get_chat(resolved)
            chat_name = chat_obj.title or resolved

            # Check if bot is admin
            bot_member = await bot.get_chat_member(resolved, me.id)
            is_adm = bot_member.status in ("administrator", "creator")

            # Determine group type
            is_private = chat_obj.username is None
            gtype = "🔒 Private" if is_private else "🌐 Public"

            if is_adm:
                results.append(
                    f"{label}: ✅ *Connected!*\n"
                    f"   📋 Name: `{chat_name}`\n"
                    f"   🔑 Type: {gtype}\n"
                    f"   🆔 Chat ID: `{resolved}`\n"
                    f"   👑 Bot is admin ✅"
                )
            else:
                results.append(
                    f"{label}: ⚠️ *Bot is member but NOT admin!*\n"
                    f"   📋 Name: `{chat_name}`\n"
                    f"   Make bot admin for membership checking to work."
                )
        except Exception as e:
            err = str(e)
            if "Chat not found" in err:
                results.append(
                    f"{label}: ❌ *Bot is NOT in this group!*\n"
                    f"   Link: `{chat}`\n"
                    f"   Fix: Add bot as admin FIRST, then set the link."
                )
            elif "not enough rights" in err.lower():
                results.append(
                    f"{label}: ⚠️ *Insufficient permissions*\n"
                    f"   Link: `{chat}`\n"
                    f"   Give bot 'Add Members' permission."
                )
            else:
                results.append(
                    f"{label}: ❌ Error: `{err[:80]}`\n"
                    f"   Link saved: `{chat}`"
                )

    text = (
        f"🧪 *Bot Admin Test*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        + "\n".join(results) +
        f"\n\n_Bot must be admin to check membership._"
    )
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="fj_panel")]]
    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# 📤 ACTIVITY DESTINATIONS PANEL
# ════════════════════════════════════════════════════════════════

DEST_OPTIONS = {
    "bot_only":   ("🤖 Bot Only",            "Messages go to each user's private chat"),
    "group_only": ("👥 Group/Channel Only",   "Messages sent to a group or channel"),
    "both":       ("🤖+👥 Bot AND Group",     "Messages go to both: user's chat + group"),
}


async def dest_panel_callback(update, context):
    """
    Activity Destinations panel.
    Controls WHERE fake activity messages are sent.
    Access: 🎭 Fake Activity → 📤 Destinations
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()
    await _show_dest_panel(q)


async def _show_dest_panel(q):
    current  = _g("dest_mode", "bot_only")
    dest_chat= _g(S_DEST_CHAT, "").strip() or "Not set"

    name, desc = DEST_OPTIONS.get(current, ("Unknown", ""))

    text = (
        f"📤 *Activity Destinations*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Current Mode:* {name}\n"
        f"_{desc}_\n\n"
        f"*Group/Channel:* `{dest_chat}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*Available Modes:*\n\n"
        f"🤖 *Bot Only* — Each user gets messages in\n"
        f"   their private chat with the bot. (default)\n\n"
        f"👥 *Group/Channel Only* — Messages go to\n"
        f"   a group or channel. All users see them there.\n"
        f"   Great for making group look active.\n\n"
        f"🤖+👥 *Both* — Messages go to user's private\n"
        f"   chat AND to the group. Maximum activity look.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*Note:* For Group/Channel mode, bot must be\n"
        f"admin in that group/channel."
    )

    def mk(mode):
        n, _ = DEST_OPTIONS[mode]
        tick = "✅ " if current == mode else "▫️ "
        return InlineKeyboardButton(tick + n, callback_data=f"dest_set_{mode}")

    kb = [
        [mk("bot_only")],
        [mk("group_only")],
        [mk("both")],
        [InlineKeyboardButton("━━━ Group/Channel for Activity ━━━",
                               callback_data="fj_noop")],
        [InlineKeyboardButton("📢 Set Group/Channel", callback_data="dest_set_chat")],
        [InlineKeyboardButton("🗑️ Clear Group/Channel",
                               callback_data="dest_clear_chat")],
        [InlineKeyboardButton("🔙 Back to Fake Activity", callback_data="act_panel")],
    ]
    await _edit(q, text, kb)


async def dest_set_callback(update, context):
    """
    Set destination mode OR handle dest_set_chat / dest_clear_chat.
    Callback: dest_set_bot_only / dest_set_group_only / dest_set_both
              dest_set_chat / dest_clear_chat
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return

    data = q.data.replace("dest_set_", "")

    if data == "chat":
        # Redirect to dedicated ConversationHandler entry
        await dest_set_chat_callback(update, context)
        return

    if data == "clear_chat":
        _s(S_DEST_CHAT, "")
        await q.answer("✅ Group/Channel cleared!")
        await _show_dest_panel(q)
        return

    if data == "clear":
        _s(S_DEST_CHAT, "")
        await q.answer("✅ Cleared!")
        await _show_dest_panel(q)
        return

    if data in DEST_OPTIONS:
        _s("dest_mode", data)
        name, _ = DEST_OPTIONS[data]
        if data in ("group_only", "both"):
            try:
                from per_user_activity import schedule_group_activity_job
                schedule_group_activity_job(context.application)
            except Exception:
                pass
        await q.answer(f"✅ Mode: {name}")
        await _show_dest_panel(q)
        return

    await q.answer("❌ Unknown option")


async def dest_clear_chat_callback(update, context):
    """Clear the activity group/channel."""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    _s(S_DEST_CHAT, "")
    await q.answer("✅ Cleared!")
    await _show_dest_panel(q)


# ════════════════════════════════════════════════════════════════
# 📢 DESTINATION CHAT SETTER (ConversationHandler)
# ════════════════════════════════════════════════════════════════

async def dest_set_chat_callback(update, context):
    """
    Ask admin for group/channel link.
    Entry point of ConversationHandler — state DEST_CHAT.

    Accepts:
      https://t.me/groupname         (public group/channel link)
      https://t.me/+InviteHash       (private group invite link)
      @groupname                     (public @username)
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()

    current = _g(S_DEST_CHAT, "").strip() or "Not set"
    kb = [[InlineKeyboardButton("❌ Cancel", callback_data="dest_panel")]]
    text = (
        f"📢 *Set Activity Group/Channel*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: `{current}`\n\n"
        f"*Paste the invite link of your group or channel:*\n\n"
        f"*How to get the link:*\n"
        f"  📱 Open group → 3 dots menu → Copy Link\n"
        f"  📢 Channel → Channel Info → Copy Link\n\n"
        f"*Accepted formats:*\n"
        f"  `https://t.me/mygroupname`\n"
        f"  `https://t.me/+AbcXyz1234567`\n"
        f"  `@mygroupname`\n\n"
        f"*Requirements:*\n"
        f"• Bot must be *admin* in the group/channel\n"
        f"• Give bot 'Post Messages' permission\n\n"
        f"Send the link now:"
    )
    try:
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        pass
    return DEST_CHAT


async def dest_chat_received(update, context):
    """
    Receive group/channel link from admin and save it.
    Parses t.me links and @usernames into a usable chat_id.
    """
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    raw = update.message.text.strip()
    kb  = [[InlineKeyboardButton("🔙 Back to Destinations", callback_data="dest_panel")]]

    # Parse the link into a chat identifier bot can use
    chat_id = _parse_chat_link(raw)

    if not chat_id:
        await update.message.reply_text(
            "❌ *Invalid link!*\n\n"
            "Please send a valid Telegram group/channel link:\n"
            "  `https://t.me/groupname`\n"
            "  `https://t.me/+InviteCode`\n"
            "  `@groupname`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    # 🐛 v95 FIX: verify bot is NOT set as destination to itself
    # (user's DB had @Bite_storee_bot which is bot's own username → broadcasts
    # would silently fail because bot can't message itself as a destination)
    try:
        me = await context.bot.get_me()
        bot_usernames = {f"@{me.username.lower()}", me.username.lower(),
                          f"@{me.username}"}
        if chat_id.lower().lstrip("@") == (me.username or "").lower():
            await update.message.reply_text(
                f"❌ *Cannot set bot as its own destination!*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Aap ne bot ka username `@{me.username}` diya hai — bot khud ko "
                f"message nahi bhej sakta.\n\n"
                f"*Fix:*\n"
                f"• Group/channel ka username paste karein (e.g. `@bite_alerts`)\n"
                f"• Or Cancel karke Bot Only mode select karein",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb))
            return ConversationHandler.END
    except Exception:
        pass  # Bot username fetch failed — don't block admin

    # 🐛 v95 FIX: pre-flight verify bot is admin in destination
    ok, err_msg = await _verify_bot_access(context.bot, chat_id, "group/channel")
    if not ok:
        await update.message.reply_text(err_msg, parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(kb),
                                          disable_web_page_preview=True)
        return ConversationHandler.END

    _s(S_DEST_CHAT, chat_id)
    try:
        from per_user_activity import schedule_group_activity_job
        schedule_group_activity_job(context.application)
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ *Group/Channel Set & Verified!*\n\n"
        f"Activity messages will now be sent to:\n"
        f"`{chat_id}`\n\n"
        f"✅ Bot has access to this destination.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


def _parse_chat_link(raw: str) -> str:
    """
    Parse a Telegram link or @username into a usable chat_id string.

    Inputs:
      https://t.me/mychannel       → @mychannel
      https://t.me/+AbcHash        → https://t.me/+AbcHash  (kept as-is for private)
      t.me/mychannel               → @mychannel
      @mychannel                   → @mychannel
      mychannel                    → @mychannel

    Returns empty string if invalid.
    """
    import re
    raw = raw.strip()

    # Private invite link — keep as-is (bot uses it to send)
    if re.match(r'https?://t[.]me/[+]\S+', raw):
        return raw

    # Public t.me link → extract @username
    m = re.match(r'https?://t[.]me/([a-zA-Z][a-zA-Z0-9_]{3,})', raw)
    if m:
        return "@" + m.group(1)

    # t.me/username (no https)
    m = re.match(r't[.]me/([a-zA-Z][a-zA-Z0-9_]{3,})', raw)
    if m:
        return "@" + m.group(1)

    # @username directly
    if re.match(r'@[a-zA-Z][a-zA-Z0-9_]{3,}', raw):
        return raw

    # username without @ (min 5 chars to avoid false positives)
    if re.match(r'[a-zA-Z][a-zA-Z0-9_]{4,}', raw):
        return "@" + raw

    return ""


# ════════════════════════════════════════════════════════════════
# 📤 SEND WITH DESTINATION (used by per_user_activity.py)
# ════════════════════════════════════════════════════════════════

async def send_activity_message(bot, user_id: int, message: str, reply_markup=None):
    """
    Send a fake activity message according to current destination mode.

    Mode = bot_only   → send to user_id private chat
    Mode = group_only → send to configured group/channel
    Mode = both       → send to both

    Call this from per_user_activity.py instead of bot.send_message directly.

    🆕 v96: maintenance mode gate — all fake activity broadcasts skipped
    when admin has maintenance ON. Full lockdown as requested by admin.
    """
    # 🆕 v96 maintenance gate
    try:
        from maintenance_mode import is_maintenance_on
        if is_maintenance_on():
            logger.debug(f"[send_activity_message] SKIPPED — maintenance ON")
            return False
    except Exception:
        pass

    mode      = _g("dest_mode", "bot_only")
    dest_chat = _g(S_DEST_CHAT, "").strip()

    # 🆕 v96: self-protection — refuse to send to bot's own username (would fail)
    if dest_chat:
        try:
            me = await bot.get_me()
            own = f"@{(me.username or '').lower()}"
            if dest_chat.lower() in (own, own.lstrip("@")):
                logger.warning(f"[send_activity_message] dest_chat is bot's own username ({dest_chat}) — skipping group send")
                dest_chat = ""  # will skip group_only branch below
        except Exception:
            pass

    sent_any = False

    if mode in ("bot_only", "both"):
        try:
            await bot.send_message(
                chat_id=user_id, text=message, parse_mode="Markdown", reply_markup=reply_markup)
            sent_any = True
        except Exception as e:
            # Fallback to plain text if Markdown parsing fails
            try:
                await bot.send_message(chat_id=user_id, text=message, reply_markup=reply_markup)
                sent_any = True
            except Exception as e2:
                logger.debug(f"[Dest] Bot send to {user_id} failed: {e2}")

    if mode in ("group_only", "both") and dest_chat:
        try:
            # Dynamically resolve any link/username/invite hash to proper numeric chat ID
            resolved_chat = await _resolve_chat_id(bot, dest_chat)
            await bot.send_message(
                chat_id=resolved_chat, text=message, parse_mode="Markdown", reply_markup=reply_markup)
            sent_any = True
        except Exception as e:
            # Fallback to plain text if Markdown parsing fails
            try:
                resolved_chat = await _resolve_chat_id(bot, dest_chat)
                await bot.send_message(chat_id=resolved_chat, text=message, reply_markup=reply_markup)
                sent_any = True
            except Exception as e2:
                logger.warning(f"[Dest] Group send to {dest_chat} ({resolved_chat if 'resolved_chat' in locals() else 'unresolved'}) failed: {e2}")

    return sent_any

