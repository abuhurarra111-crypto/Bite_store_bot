# ============================================
# ⭐ REVIEWS & RATINGS HANDLERS
# ============================================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
from config import ADMIN_ID
from database import (
    get_product, get_product_reviews, get_product_rating_stats,
    add_review, get_user_review, get_user_all_reviews,
    get_eligible_products_for_review, get_all_reviews_for_admin,
    toggle_review_visibility, toggle_review_pin, delete_review
)
from i18n import t, get_user_lang
from utils import escape_md, format_date, nav_push

# Conversation states for review writing
REV_TEXT = 600


def _r(key):
    """🆕 v46: fetch an editable response (auto-registers it for the editor)."""
    try:
        from database import get_response_with_auto_register
        from config import DEFAULT_RESPONSES
        return get_response_with_auto_register(key, DEFAULT_RESPONSES.get(key, ""))
    except Exception:
        from config import DEFAULT_RESPONSES
        return DEFAULT_RESPONSES.get(key, "")


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

def stars_display(rating, max_=5):
    return "⭐" * int(rating) + "☆" * (max_ - int(rating))


# ════════════════════════════════════════════
# USER-SIDE
# ════════════════════════════════════════════

async def reviews_menu_callback(update, context):
    """Main reviews menu — show pending reviews invite + my reviews."""
    q = update.callback_query
    await q.answer()
    nav_push(context, 'reviews_menu')  # 🔧 v39 Bug #5
    uid = q.from_user.id
    lang = get_user_lang(uid)

    eligible = get_eligible_products_for_review(uid)
    my = get_user_all_reviews(uid)

    # 🆕 v46: editable header (admin can change via Edit Responses)
    try:
        text = _r("reviews_menu_header").format(my=len(my), pending=len(eligible))
    except Exception:
        text = (f"⭐ *Reviews & Ratings*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📝 My reviews: {len(my)}\n"
                f"✍️ Pending to review: {len(eligible)}\n\n"
                f"Share your experience and help others!")

    kb = []
    if eligible:
        kb.append([InlineKeyboardButton(t("rev_write", lang=lang), callback_data="rev_pick_order")])
    if my:
        kb.append([InlineKeyboardButton(t("rev_my", lang=lang), callback_data="rev_my_list")])
    # 🆕 v38: Inject custom buttons for reviews screen
    try:
        from keyboards import _custom_buttons_for
        for row in _custom_buttons_for("reviews"):
            kb.append(row)
    except Exception:
        pass
    kb.append([InlineKeyboardButton(t("btn_back", lang=lang), callback_data="main_menu")])

    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def rev_pick_order_callback(update, context):
    """Show list of products user can review."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = get_user_lang(uid)

    eligible = get_eligible_products_for_review(uid)
    if not eligible:
        await _safe_edit(q, t("rev_no_eligible", lang=lang), parse_mode="Markdown",
                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                             t("btn_back", lang=lang), callback_data="reviews_menu")]]))
        return

    kb = []
    for row in eligible[:20]:
        pid = row['product_id']
        pname = row['product_name'] or f"Product #{pid}"
        kb.append([InlineKeyboardButton(f"📦 {pname[:40]}",
                                          callback_data=f"rev_start_{pid}")])
    kb.append([InlineKeyboardButton(t("btn_back", lang=lang), callback_data="reviews_menu")])
    await _safe_edit(q, t("rev_pick_order", lang=lang),
                     reply_markup=InlineKeyboardMarkup(kb))


async def rev_start_callback(update, context):
    """User picked a product — show star rating buttons."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = get_user_lang(uid)
    pid = int(q.data.split("_")[-1])

    # Anti-double review
    if get_user_review(pid, uid):
        await q.answer(t("rev_already", lang=lang).replace("ℹ️ ", ""), show_alert=True)
        return

    p = get_product(pid)
    if not p:
        await q.answer("❌ Product not found", show_alert=True)
        return

    context.user_data['rev_pid'] = pid
    pname = p['name']

    kb = [[
        InlineKeyboardButton("⭐", callback_data=f"revrate_{pid}_1"),
        InlineKeyboardButton("⭐⭐", callback_data=f"revrate_{pid}_2"),
        InlineKeyboardButton("⭐⭐⭐", callback_data=f"revrate_{pid}_3"),
    ], [
        InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"revrate_{pid}_4"),
        InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"revrate_{pid}_5"),
    ], [
        InlineKeyboardButton(t("btn_cancel", lang=lang), callback_data="reviews_menu"),
    ]]

    text = f"📦 *{escape_md(pname)}*\n\n{t('rev_pick_rating', lang=lang)}"
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def rev_rate_callback(update, context):
    """User picked rating — now ask for text (or skip)."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = get_user_lang(uid)
    # Format: revrate_{pid}_{rating}
    parts = q.data.split("_")
    pid, rating = int(parts[1]), int(parts[2])

    context.user_data['rev_pid'] = pid
    context.user_data['rev_rating'] = rating

    text = f"{stars_display(rating)}\n\n{t('rev_enter_text', lang=lang)}"
    kb = [[InlineKeyboardButton(t("rev_skip", lang=lang), callback_data=f"revskip_{pid}")],
          [InlineKeyboardButton(t("btn_cancel", lang=lang), callback_data="reviews_menu")]]
    await _safe_edit(q, text, reply_markup=InlineKeyboardMarkup(kb))
    return REV_TEXT


async def rev_text_received(update, context):
    """User typed the review text."""
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    pid = context.user_data.get('rev_pid')
    rating = context.user_data.get('rev_rating')
    if not pid or not rating:
        await update.message.reply_text("❌ Session expired.")
        return ConversationHandler.END

    text_input = (update.message.text or "").strip()[:500]
    add_review(pid, uid, rating, text_input)

    p = get_product(pid)
    pname = p['name'] if p else f"#{pid}"
    confirm = t("rev_submitted", lang=lang, stars=stars_display(rating))
    await update.message.reply_text(f"📦 *{escape_md(pname)}*\n\n{confirm}",
                                     parse_mode="Markdown")

    # Notify admin
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"⭐ *New Review!*\n"
            f"Product: {escape_md(pname)}\n"
            f"Rating: {stars_display(rating)}\n"
            f"User: {escape_md(update.effective_user.first_name or 'N/A')} (`{uid}`)\n"
            f"Text: _{escape_md(text_input[:200]) if text_input else '(no text)'}_",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    context.user_data.pop('rev_pid', None)
    context.user_data.pop('rev_rating', None)
    return ConversationHandler.END


async def rev_skip_callback(update, context):
    """User skipped the text — save with empty text."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = get_user_lang(uid)
    pid = context.user_data.get('rev_pid') or int(q.data.split("_")[-1])
    rating = context.user_data.get('rev_rating', 5)

    add_review(pid, uid, rating, "")
    p = get_product(pid)
    pname = p['name'] if p else f"#{pid}"
    confirm = t("rev_submitted", lang=lang, stars=stars_display(rating))
    await _safe_edit(q, f"📦 *{escape_md(pname)}*\n\n{confirm}",
                     parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                         t("btn_back", lang=lang), callback_data="reviews_menu")]]))

    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"⭐ *New Review (no text)*\n"
            f"Product: {escape_md(pname)}\n"
            f"Rating: {stars_display(rating)}\n"
            f"User: `{uid}`",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    context.user_data.pop('rev_pid', None)
    context.user_data.pop('rev_rating', None)
    return ConversationHandler.END


async def rev_skip_command(update, context):
    """🔧 v39 FIX: /skip COMMAND handler (message-based, no callback_query).
    Saves the review with empty text just like the callback version."""
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    pid = context.user_data.get('rev_pid')
    rating = context.user_data.get('rev_rating', 5)
    if not pid:
        await update.message.reply_text("❌ Session expired.")
        return ConversationHandler.END

    add_review(pid, uid, rating, "")
    p = get_product(pid)
    pname = p['name'] if p else f"#{pid}"
    confirm = t("rev_submitted", lang=lang, stars=stars_display(rating))
    await update.message.reply_text(f"📦 *{escape_md(pname)}*\n\n{confirm}",
                                     parse_mode="Markdown")
    # Notify admin
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"⭐ *New Review (skipped text)*\n"
            f"Product: {escape_md(pname)}\n"
            f"Rating: {stars_display(rating)}\n"
            f"User: `{uid}`",
            parse_mode="Markdown"
        )
    except Exception:
        pass
    context.user_data.pop('rev_pid', None)
    context.user_data.pop('rev_rating', None)
    return ConversationHandler.END


async def rev_my_list_callback(update, context):
    """Show user's own reviews."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = get_user_lang(uid)
    my = get_user_all_reviews(uid)

    if not my:
        await _safe_edit(q, t("rev_no_reviews", lang=lang),
                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                             t("btn_back", lang=lang), callback_data="reviews_menu")]]))
        return

    lines = [f"📝 *My Reviews* ({len(my)})\n━━━━━━━━━━━━━━━━━━━━\n"]
    for r in my[:15]:
        pname = r['product_name'] or "Unknown"
        txt = (r['review_text'] or "_(no text)_")[:80]
        lines.append(f"📦 *{escape_md(pname[:30])}*\n"
                     f"{stars_display(r['rating'])} • {format_date(r['created_at'])}\n"
                     f"_{escape_md(txt)}_\n")

    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                         t("btn_back", lang=lang), callback_data="reviews_menu")]]))


async def product_reviews_view_callback(update, context):
    """Show all public reviews for a specific product. Called from product detail."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = get_user_lang(uid)
    pid = int(q.data.split("_")[-1])

    p = get_product(pid)
    stats = get_product_rating_stats(pid)
    reviews = get_product_reviews(pid, limit=10)

    pname = p['name'] if p else f"#{pid}"
    if stats['count'] == 0:
        text = (f"📦 *{escape_md(pname)}*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n{t('rev_no_reviews', lang=lang)}")
    else:
        avg_stars = stars_display(round(stats['avg']))
        text = (f"📦 *{escape_md(pname)}*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{avg_stars} *{stats['avg']:.1f}/5* ({stats['count']} reviews)\n\n")
        for r in reviews[:6]:
            name = escape_md(r['first_name'] or "Anonymous")[:20]
            pin = "📌 " if r['is_pinned'] else ""
            txt = (r['review_text'] or "")[:120]
            text += (f"{pin}{stars_display(r['rating'])} *{name}* — {format_date(r['created_at'])}\n"
                     f"_{escape_md(txt) if txt else '(no text)'}_\n\n")

    kb = [[InlineKeyboardButton(t("btn_back", lang=lang), callback_data=f"prod_{pid}")]]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════
# ADMIN-SIDE
# ════════════════════════════════════════════

async def admin_reviews_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    all_reviews = get_all_reviews_for_admin(limit=20)
    if not all_reviews:
        await _safe_edit(q, "📭 No reviews yet.",
                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                             "🔙 Return", callback_data="admin_panel")]]))
        return

    lines = [f"⭐ *All Reviews* ({len(all_reviews)})\n━━━━━━━━━━━━━━━━━━━━\n"]
    kb = []
    for r in all_reviews[:15]:
        pname = (r['product_name'] or "?")[:25]
        uname = (r['first_name'] or "?")[:15]
        flag = "🚫" if r['is_hidden'] else ("📌" if r['is_pinned'] else "✅")
        lines.append(f"{flag} {stars_display(r['rating'])} *{escape_md(pname)}* — {escape_md(uname)}\n"
                     f"_{escape_md((r['review_text'] or '(no text)')[:60])}_\n")
        kb.append([
            InlineKeyboardButton(f"#{r['id']} {flag}", callback_data="noop"),
            InlineKeyboardButton("📌", callback_data=f"admrev_pin_{r['id']}"),
            InlineKeyboardButton("👁️", callback_data=f"admrev_hide_{r['id']}"),
            InlineKeyboardButton("🗑️", callback_data=f"admrev_del_{r['id']}"),
        ])
    kb.append([InlineKeyboardButton("🔙 Return", callback_data="admin_panel")])

    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def admrev_pin_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    rid = int(q.data.split("_")[-1])
    toggle_review_pin(rid)
    await q.answer("📌 Toggled pin")
    await admin_reviews_callback(update, context)


async def admrev_hide_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    rid = int(q.data.split("_")[-1])
    toggle_review_visibility(rid)
    await q.answer("👁️ Toggled visibility")
    await admin_reviews_callback(update, context)


async def admrev_del_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    rid = int(q.data.split("_")[-1])
    delete_review(rid)
    await q.answer("🗑️ Deleted")
    await admin_reviews_callback(update, context)
