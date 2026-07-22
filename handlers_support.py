# ============================================
# 🎫 SUPPORT + 🛡️ WARRANTY + 📦 DELIVERY
# ============================================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler  # 🔧 BUG FIX: used (ConversationHandler.END) but never imported → NameError
from config import ADMIN_ID, DEFAULT_RESPONSES, POINTS_PER_DOLLAR
from database import *
from keyboards import back_btn
from utils import escape_md, nav_push, set_cb_data, smart_text_and_mode, contains_premium_markup
from datetime import datetime
from templates_bundle import render_delivery_bundle, normalize_product_format, format_label, format_hint, format_example
# 🆕 v73: two-way ticket chat (text + photo + video + document)
from support_replacement import (
    add_ticket_message, get_ticket_messages, get_ticket_message_count,
    extract_media, relay_media_to, ensure_ticket_messages_table,
)


# 🔧 BUG FIX: _safe_edit() was used (e.g. Pending Manual Deliveries screen)
# but never defined/imported in this module → NameError crash.
async def _safe_edit(q, text, **kwargs):
    send_text, send_mode = smart_text_and_mode(text, kwargs.get("parse_mode", "Markdown"))
    k0 = dict(kwargs)
    k0["parse_mode"] = send_mode
    try:
        await q.edit_message_text(send_text, **k0); return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in k0:
            k = dict(k0); k.pop("parse_mode")
            try:
                await q.edit_message_text(send_text, **k); return
            except Exception: pass
    try:
        await q.edit_message_caption(caption=send_text, **k0); return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in k0:
            k = dict(k0); k.pop("parse_mode")
            try:
                await q.edit_message_caption(caption=send_text, **k); return
            except Exception: pass
    try:
        await q.message.reply_text(send_text, **k0)
    except Exception:
        k = dict(k0); k.pop("parse_mode", None)
        try: await q.message.reply_text(send_text, **k)
        except Exception: pass

def _r(key, user_id=None):
    """🆕 v79: per-language lookup when user_id provided."""
    if user_id is not None:
        try:
            from i18n_responses import get_translated_response
            tr = get_translated_response(key, user_id=user_id)
            if tr is not None:
                return tr
        except Exception:
            pass
    from database import get_response_with_auto_register
    return get_response_with_auto_register(key, DEFAULT_RESPONSES.get(key, ""))


def _render_delivery_message_for_order(order, product, raw_content):
    """Render the customer-facing delivery using the selected Bite Store template.

    🆕 v72: raw_content is preserved byte-for-byte. Order id is passed so
    integrity events can be logged with proper attribution.
    """
    if not order:
        return "⚠️ Order not found."
    pd = dict(product) if product else {}
    fmt = normalize_product_format(pd.get('product_format', 'email_pass'))
    try:
        tpl = int(pd.get('delivery_template', 1) or 1)
    except Exception:
        tpl = 1
    product_name = order['product_name'] if 'product_name' in order.keys() else pd.get('name', 'Product')
    oid = order['id'] if 'id' in order.keys() else 0
    pid = order['product_id'] if 'product_id' in order.keys() else 0
    return render_delivery_bundle([raw_content], product_name=product_name,
                                  product_format=fmt, template_id=tpl,
                                  order_id=oid, product_id=pid)


def _fmt_msg_name(value):
    return str(value or "") if contains_premium_markup(value) else escape_md(value)


# ════════════════════════════════════════════
# 🎫 SUPPORT TICKETS — User Side
# ════════════════════════════════════════════

SUPPORT_SUBJECT = 400
SUPPORT_DESC = 401
WARRANTY_REASON = 402
MANUAL_DELIVERY_TEXT = 403


async def support_menu_callback(update, context):
    """🎫 Support ticket main menu"""
    q = update.callback_query
    await q.answer()
    nav_push(context, 'support_menu')
    user_id = q.from_user.id

    # Count user's tickets
    tickets = get_user_tickets(user_id)
    open_count = sum(1 for t in tickets if t['status'] in ('open', 'in_progress'))

    from config import WHATSAPP_NUMBER
    # 🆕 v46: editable header (admin can change via Edit Responses)
    try:
        text = _r("support_menu_header").format(
            whatsapp=WHATSAPP_NUMBER, total=len(tickets), open=open_count)
    except Exception:
        text = (f"🎫 *Support Center*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Need help? Create a support ticket!\n"
                f"📞 *WhatsApp Support:* `+{WHATSAPP_NUMBER}`\n\n"
                f"📋 *Your Tickets:* {len(tickets)} total\n"
                f"🟡 *Open:* {open_count}\n\nChoose an option:")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎫 New Ticket", callback_data="st_new")],
        [InlineKeyboardButton("📋 My Tickets", callback_data="st_list")],
        [InlineKeyboardButton("🔙 Back", callback_data="go_back")],
    ])
    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except:
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def st_new_callback(update, context):
    """Start new ticket — ask subject"""
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "🎫 *New Support Ticket*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "📝 *Step 1/2:* Enter ticket subject:\n\n"
        "Example: `Payment issue`, `Product not working`, `Account problem`\n\n"
        "_Max 200 characters_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="support_menu")]]))
    return SUPPORT_SUBJECT


async def st_subject_received(update, context):
    """Subject received — ask description"""
    if update.effective_user.id != context.user_data.get('_st_user_id', update.effective_user.id):
        return SUPPORT_SUBJECT
    subject = update.message.text.strip()
    if not subject or len(subject) < 3:
        await update.message.reply_text("❌ Subject too short. Enter at least 3 characters:")
        return SUPPORT_SUBJECT
    context.user_data['st_subject'] = subject[:200]
    await update.message.reply_text(
        f"✅ Subject: *{escape_md(subject[:200])}*\n\n"
        "📝 *Step 2/2:* Describe your issue in detail:\n\n"
        "_The more detail you provide, the faster we can help._\n\n"
        "Type `-` to skip description",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="support_menu")]]))
    return SUPPORT_DESC


async def st_desc_received(update, context):
    """Description received — create ticket"""
    desc = update.message.text.strip()
    if desc == "-":
        desc = ""
    subject = context.user_data.pop('st_subject', 'Support Request')
    user_id = update.effective_user.id

    tid = create_ticket(user_id, subject, desc[:2000])

    # 🆕 v71: try AI auto-reply BEFORE notifying admin
    ai_handled = False
    try:
        from ai_misc import is_enabled as _ai_on, try_ai_reply
        if _ai_on():
            ai_result = await try_ai_reply(tid, user_id, subject, desc)
            if ai_result.get("ok") and ai_result.get("answer"):
                # AI confidently answered — send to user, save reply to ticket
                ai_answer = ai_result["answer"]
                try:
                    from database import update_ticket
                    update_ticket(tid, admin_reply=f"[🤖 AI] {ai_answer}",
                                  status="awaiting_user")
                except Exception:
                    pass

                await update.message.reply_text(
                    f"🎫 *Ticket #{tid} — Quick Answer*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📝 Subject: {escape_md(subject)}\n\n"
                    f"🤖 *Our assistant suggests:*\n\n"
                    f"{escape_md(ai_answer)}\n\n"
                    f"_If this doesn't help, tap below to talk to a human._",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🆘 Talk to Human",
                                              callback_data=f"st_escalate_{tid}")],
                        [InlineKeyboardButton("✅ Issue Solved!",
                                              callback_data=f"st_resolved_user_{tid}")],
                        [InlineKeyboardButton("📋 My Tickets", callback_data="st_list")],
                        [InlineKeyboardButton("🏠 Main Menu",  callback_data="main_menu")],
                    ]))

                # Quiet admin notification (info only — no action needed)
                try:
                    user_name = update.effective_user.first_name or str(user_id)
                    await context.bot.send_message(ADMIN_ID,
                        f"🤖 *AI Auto-Handled Ticket #{tid}*\n"
                        f"👤 {escape_md(user_name)} (`{user_id}`)\n"
                        f"📝 Subject: {escape_md(subject)}\n\n"
                        f"_AI suggested an answer. Tap below if you want to override._",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📝 Override Reply", callback_data=f"adm_st_reply_{tid}"),
                             InlineKeyboardButton("📋 All Tickets",   callback_data="adm_tickets")],
                        ]))
                except Exception:
                    pass

                ai_handled = True
                context.user_data.pop('_st_user_id', None)
                return ConversationHandler.END
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[AISupport] try_ai_reply failed: {e}")

    # ── Original flow (AI disabled, AI escalated, or AI failed) ──
    await update.message.reply_text(
        f"✅ *Ticket Created!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎫 Ticket #{tid}\n"
        f"📝 Subject: {escape_md(subject)}\n"
        f"📊 Status: 🟡 Open\n\n"
        f"Admin will review your ticket and reply.\n"
        f"You'll be notified when there's an update.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 My Tickets", callback_data="st_list")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
        ]))

    # Notify admin
    try:
        user_name = update.effective_user.first_name or str(user_id)
        await context.bot.send_message(ADMIN_ID,
            f"🎫 *New Support Ticket #{tid}*\n"
            f"👤 {escape_md(user_name)} (`{user_id}`)\n"
            f"📝 Subject: {escape_md(subject)}\n"
            f"{'📄 ' + escape_md(desc[:100]) if desc else ''}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Reply", callback_data=f"adm_st_reply_{tid}"),
                 InlineKeyboardButton("✅ Resolve", callback_data=f"adm_st_resolve_{tid}")],
                [InlineKeyboardButton("📋 All Tickets", callback_data="adm_tickets")],
            ]))
    except:
        pass

    context.user_data.pop('_st_user_id', None)
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════
# 🆕 v71: User-side callbacks after AI auto-reply
# ════════════════════════════════════════════════════════════
async def st_escalate_callback(update, context):
    """User tapped '🆘 Talk to Human' on AI's suggested answer."""
    q = update.callback_query
    await q.answer()
    try:
        tid = int(q.data.replace("st_escalate_", ""))
    except Exception:
        await q.answer("Invalid ticket", show_alert=True); return
    # Reopen ticket as open + notify admin
    try:
        from database import update_ticket, get_ticket
        update_ticket(tid, status="open")
        t = get_ticket(tid)
    except Exception:
        t = None
    if t:
        try:
            await context.bot.send_message(ADMIN_ID,
                f"🆘 *User wants human help — Ticket #{tid}*\n"
                f"👤 `{t['user_id']}`\n"
                f"📝 Subject: {escape_md(t['subject'] or '')}\n\n"
                f"_AI's suggested answer didn't help. Please reply manually._",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 Reply",   callback_data=f"adm_st_reply_{tid}"),
                     InlineKeyboardButton("✅ Resolve", callback_data=f"adm_st_resolve_{tid}")],
                ]))
        except Exception:
            pass
    await q.edit_message_text(
        f"✅ *Ticket #{tid} escalated*\n\n"
        f"A human admin will reply soon. You'll get a notification.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 My Tickets", callback_data="st_list")],
            [InlineKeyboardButton("🏠 Main Menu",  callback_data="main_menu")],
        ]))


async def st_resolved_user_callback(update, context):
    """User tapped '✅ Issue Solved!' on AI's answer."""
    q = update.callback_query
    await q.answer("Marked as resolved 🎉", show_alert=False)
    try:
        tid = int(q.data.replace("st_resolved_user_", ""))
    except Exception:
        await q.answer("Invalid ticket", show_alert=True); return
    try:
        from database import update_ticket
        update_ticket(tid, status="resolved")
    except Exception:
        pass
    await q.edit_message_text(
        f"🎉 *Thank you!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Ticket #{tid} marked as resolved.\n\n"
        f"If anything else comes up, you can open a new ticket anytime.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Shop More", callback_data="shop")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
        ]))


async def st_list_callback(update, context):
    """Show user's tickets"""
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    tickets = get_user_tickets(user_id)

    if not tickets:
        await q.edit_message_text(
            "📋 *No tickets yet*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "You haven't created any support tickets.\n"
            "Tap 'New Ticket' to get help!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎫 New Ticket", callback_data="st_new")],
                [InlineKeyboardButton("🔙 Back", callback_data="support_menu")],
            ]))
        return

    text = "📋 *Your Tickets*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    status_map = {'open': '🟡 Open', 'in_progress': '🔄 In Progress',
                  'resolved': '✅ Resolved', 'closed': '🔒 Closed'}
    kb = []
    for t in tickets[:10]:
        s = status_map.get(t['status'], t['status'])
        try:
            dt = datetime.strptime(str(t['created_at'])[:19], "%Y-%m-%d %H:%M:%S")
            dt_str = dt.strftime("%d %b %I:%M %p")
        except:
            dt_str = str(t['created_at'])[:16]
        text += f"🎫 *#{t['id']}* {s}\n  📝 {escape_md(t['subject'][:50])}\n  📅 {dt_str}\n\n"
        kb.append([InlineKeyboardButton(f"🎫 #{t['id']} — {t['subject'][:30]} ({s})",
                                         callback_data=f"st_view_{t['id']}")])

    kb.append([InlineKeyboardButton("🎫 New Ticket", callback_data="st_new")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="support_menu")])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def st_view_callback(update, context):
    """View single ticket detail"""
    q = update.callback_query
    await q.answer()
    tid = int(q.data.replace("st_view_", ""))
    t = get_ticket(tid)
    if not t or t['user_id'] != q.from_user.id:
        await q.answer("❌ Not found", show_alert=True)
        return

    status_map = {'open': '🟡 Open', 'in_progress': '🔄 In Progress',
                  'resolved': '✅ Resolved', 'closed': '🔒 Closed'}
    s = status_map.get(t['status'], t['status'])

    try:
        dt = datetime.strptime(str(t['created_at'])[:19], "%Y-%m-%d %H:%M:%S")
        dt_str = dt.strftime("%d %b %Y %I:%M %p")
    except:
        dt_str = str(t['created_at'])[:16]

    text = (f"🎫 *Ticket #{t['id']}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 *Subject:* {escape_md(t['subject'])}\n"
            f"📊 *Status:* {s}\n"
            f"📅 *Created:* {dt_str}\n\n")

    if t['description']:
        text += f"📄 *Your Message:*\n{escape_md(t['description'])}\n\n"

    if t['admin_reply']:
        try:
            upt = datetime.strptime(str(t['updated_at'])[:19], "%Y-%m-%d %H:%M:%S")
            upt_str = upt.strftime("%d %b %I:%M %p")
        except:
            upt_str = str(t['updated_at'])[:16]
        text += (f"━━━━━━━━━━━━━━━━━━━━\n"
                 f"💬 *Admin Reply:* ({upt_str})\n"
                 f"{escape_md(t['admin_reply'])}\n")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 My Tickets", callback_data="st_list")],
        [InlineKeyboardButton("🔙 Back", callback_data="support_menu")],
    ])
    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except:
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ════════════════════════════════════════════
# 🛡️ WARRANTY/REFUND — User Side
# ════════════════════════════════════════════

async def warranty_menu_callback(update, context):
    """🛡️ Warranty/Refund menu — user selects an order"""
    q = update.callback_query
    await q.answer()
    nav_push(context, 'warranty_menu')
    user_id = q.from_user.id
    orders = get_user_product_orders(user_id)

    # Only show delivered orders (eligible for warranty/refund)
    delivered = [o for o in orders if o['status'] == 'delivered']

    if not delivered:
        await q.edit_message_text(
            _r("warranty_no_orders"),
            parse_mode="Markdown",
            reply_markup=back_btn(location="warranty"))
        return

    text = _r("warranty_menu_header") + "\n"
    kb = []
    for o in delivered[:10]:
        label = f"📦 #{o['id']} {o['product_name'][:25]} — ${o['price']:.2f}"
        kb.append([InlineKeyboardButton(label, callback_data=f"wr_order_{o['id']}")])

    # 🆕 v38: Inject custom buttons for warranty screen
    try:
        from keyboards import _custom_buttons_for
        kb.extend(_custom_buttons_for("warranty"))
    except Exception:
        pass
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="go_back")])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def wr_order_callback(update, context):
    """User selected an order — choose warranty or refund"""
    q = update.callback_query
    await q.answer()
    oid = int(q.data.replace("wr_order_", ""))
    o = get_order(oid)
    if not o:
        await q.answer("❌ Order not found", show_alert=True)
        return

    # Check if already requested
    existing = get_user_warranty_requests(q.from_user.id)
    for w in existing:
        if w['order_id'] == oid and w['status'] == 'pending':
            await q.answer("⚠️ You already have a pending request for this order", show_alert=True)
            return

    p = get_product(o['product_id']) if o['product_id'] else None
    try:
        warranty = p['warranty'] or "N/A"
    except Exception:
        warranty = "N/A"

    text = (f"📦 *Order #{oid}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 Product: {_fmt_msg_name(o['product_name'])}\n"
            f"💰 Price: ${o['price']:.2f}\n"
            f"🛡️ Warranty: {escape_md(warranty)}\n\n"
            f"What do you need?")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ Warranty Claim", callback_data=f"wr_type_{oid}_warranty")],
        [InlineKeyboardButton("💰 Refund Request", callback_data=f"wr_type_{oid}_refund")],
        [InlineKeyboardButton("🔙 Back", callback_data="warranty_menu")],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def wr_type_callback(update, context):
    """User chose warranty or refund — ask reason"""
    q = update.callback_query
    await q.answer()
    # data: wr_type_{oid}_{type}
    parts = q.data.replace("wr_type_", "").rsplit("_", 1)
    oid = int(parts[0])
    req_type = parts[1]  # 'warranty' or 'refund'
    context.user_data['wr_oid'] = oid
    context.user_data['wr_type'] = req_type

    type_label = "🛡️ Warranty Claim" if req_type == 'warranty' else "💰 Refund Request"
    await q.edit_message_text(
        f"{type_label}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 Describe your reason in detail:\n\n"
        f"Example: 'Product stopped working after 2 days'\n"
        f"or 'Wrong product delivered'\n\n"
        f"_The more detail, the faster we can help_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="warranty_menu")]]))
    return WARRANTY_REASON


async def wr_reason_received(update, context):
    """Reason received — create warranty/refund request"""
    reason = update.message.text.strip()
    if not reason or len(reason) < 5:
        await update.message.reply_text("❌ Please provide at least 5 characters.")
        return WARRANTY_REASON

    oid = context.user_data.pop('wr_oid', None)
    req_type = context.user_data.pop('wr_type', 'warranty')
    user_id = update.effective_user.id

    if not oid:
        await update.message.reply_text("❌ Session expired. Try again.")
        return ConversationHandler.END

    wid = create_warranty_request(user_id, oid, req_type, reason[:1000])

    type_label = "🛡️ Warranty" if req_type == 'warranty' else "💰 Refund"
    await update.message.reply_text(
        f"✅ *{type_label} Request Created!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 Request #{wid}\n"
        f"📦 Order #{oid}\n"
        f"📊 Status: 🟡 Pending\n\n"
        f"Admin will review your request.\n"
        f"You'll be notified when there's an update.",
        parse_mode="Markdown",
        reply_markup=back_btn())

    # Notify admin
    try:
        o = get_order(oid)
        user_name = update.effective_user.first_name or str(user_id)
        await context.bot.send_message(ADMIN_ID,
            f"{'🛡️' if req_type=='warranty' else '💰'} *New {type_label} Request #{wid}*\n"
            f"👤 {escape_md(user_name)} (`{user_id}`)\n"
            f"📦 Order #{oid}: {escape_md(o['product_name'] if o else 'N/A')}\n"
            f"📝 Reason: {escape_md(reason[:200])}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Approve", callback_data=f"adm_wr_approve_{wid}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"adm_wr_reject_{wid}")],
                [InlineKeyboardButton("📋 All Requests", callback_data="adm_warranty")],
            ]))
    except:
        pass

    return ConversationHandler.END


# ════════════════════════════════════════════
# 🎫 ADMIN — Support Ticket Management
# ════════════════════════════════════════════

async def adm_tickets_callback(update, context):
    """Admin: Show all support tickets"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    nav_push(context, 'adm_tickets')

    tickets = get_all_tickets()
    open_count = sum(1 for t in tickets if t['status'] in ('open', 'in_progress'))

    text = (f"🎫 *Support Tickets*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 Total: {len(tickets)}\n"
            f"🟡 Open: {open_count}\n\n"
            f"Filter by status:")

    kb = [
        [InlineKeyboardButton(f"🟡 Open ({open_count})", callback_data="adm_tickets_open")],
        [InlineKeyboardButton("📋 All Tickets", callback_data="adm_tickets_all")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")],
    ]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def adm_tickets_list_callback(update, context):
    """Admin: Show ticket list filtered by status"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    status_filter = q.data.replace("adm_tickets_", "")
    if status_filter == "all":
        tickets = get_all_tickets()
        title = "📋 *All Tickets*"
    else:
        tickets = get_all_tickets(status_filter)
        title = "🟡 *Open Tickets*"

    if not tickets:
        await q.edit_message_text(f"{title}\n━━━━━━━━━━━━━━━━━━━━\n\nNo tickets found.",
                                   parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_tickets")]]))
        return

    text = f"{title}\n━━━━━━━━━━━━━━━━━━━━\n\n"
    kb = []
    status_map = {'open': '🟡', 'in_progress': '🔄', 'resolved': '✅', 'closed': '🔒'}
    for t in tickets[:15]:
        s = status_map.get(t['status'], '❓')
        try:
            u = get_user(t['user_id'])
            uname = u['first_name'] if u else str(t['user_id'])
        except:
            uname = str(t['user_id'])
        text += f"{s} #{t['id']} {escape_md(uname)}: {escape_md(t['subject'][:40])}\n"
        kb.append([InlineKeyboardButton(f"{s} #{t['id']} {uname[:15]}: {t['subject'][:25]}",
                                         callback_data=f"adm_st_view_{t['id']}")])

    kb.append([InlineKeyboardButton("🔙 Back", callback_data="adm_tickets")])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def adm_st_view_callback(update, context):
    """Admin: View ticket detail"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    tid = int(q.data.replace("adm_st_view_", ""))
    t = get_ticket(tid)
    if not t:
        await q.answer("Not found", show_alert=True); return

    status_map = {'open': '🟡 Open', 'in_progress': '🔄 In Progress',
                  'resolved': '✅ Resolved', 'closed': '🔒 Closed'}
    s = status_map.get(t['status'], t['status'])

    try:
        u = get_user(t['user_id'])
        uname = u['first_name'] if u else 'N/A'
    except:
        uname = 'N/A'

    text = (f"🎫 *Ticket #{t['id']}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 User: {escape_md(uname)} (`{t['user_id']}`)\n"
            f"📝 Subject: {escape_md(t['subject'])}\n"
            f"📊 Status: {s}\n"
            f"📅 Created: {t['created_at'][:16]}\n\n")

    if t['description']:
        text += f"📄 *User's Message:*\n{escape_md(t['description'][:500])}\n\n"
    if t['admin_reply']:
        text += f"💬 *Last Admin Reply:*\n{escape_md(t['admin_reply'][:500])}\n\n"

    # 🆕 v73: show chat message count (text + media)
    try:
        msg_count = get_ticket_message_count(tid)
        if msg_count:
            text += f"💬 *Chat messages exchanged:* {msg_count}\n"
    except Exception:
        pass

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Reply (text/photo/video)",
                              callback_data=f"adm_st_reply_{tid}")],
        [InlineKeyboardButton("💬 View Full Chat",
                              callback_data=f"adm_st_chat_{tid}")],
        [
            InlineKeyboardButton("✅ Resolve", callback_data=f"adm_st_resolve_{tid}"),
            InlineKeyboardButton("🔄 In Progress", callback_data=f"adm_st_progress_{tid}"),
        ],
        [InlineKeyboardButton("🔒 Close", callback_data=f"adm_st_close_{tid}")],
        [InlineKeyboardButton("🔙 Back", callback_data="adm_tickets")],
    ])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def adm_st_reply_callback(update, context):
    """Admin: Start reply to ticket.
    🆕 v73: prompt accepts text OR photo OR video OR document (with caption).
    """
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return ConversationHandler.END
    await q.answer()

    tid = int(q.data.replace("adm_st_reply_", ""))
    context.user_data['adm_reply_tid'] = tid
    await q.edit_message_text(
        f"📝 *Reply to Ticket #{tid}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send your reply now. You can send:\n"
        "• ✏️ Text message\n"
        "• 📷 Photo (with optional caption)\n"
        "• 🎬 Video (with optional caption)\n"
        "• 📎 Document (with optional caption)\n\n"
        "_The user will receive it instantly and can reply back with media too._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"adm_st_view_{tid}")]]))
    return 450  # Admin reply state


async def adm_reply_received(update, context):
    """🆕 v73: Save admin reply (text OR photo/video/document with caption) and
    relay it to the user. Both sides of the conversation are recorded in
    `ticket_messages` for full chat history.
    """
    tid = context.user_data.pop('adm_reply_tid', None)
    if not tid:
        return ConversationHandler.END

    ensure_ticket_messages_table()
    msg = update.message

    # Detect media first
    media_type, media_id, caption = extract_media(msg)
    text_body = ""
    if media_type:
        text_body = caption or ""
    else:
        text_body = (msg.text or "").strip() if msg.text else ""

    if not media_type and not text_body:
        await msg.reply_text("⚠️ Empty reply ignored. Please send text or media.")
        return ConversationHandler.END

    # Persist (cap text to 2000 for the legacy single admin_reply field)
    safe_text = text_body[:2000]
    update_ticket(tid, admin_reply=safe_text or ("[media]" if media_type else ""),
                  status='in_progress')
    add_ticket_message(tid, "admin", ADMIN_ID,
                       text=safe_text, media_type=media_type, media_id=media_id)

    t = get_ticket(tid)

    # Confirm to admin
    await msg.reply_text(
        f"✅ *Reply sent for Ticket #{tid}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Continue Chat",
                                  callback_data=f"adm_st_reply_{tid}")],
            [InlineKeyboardButton("📋 All Tickets", callback_data="adm_tickets")],
        ]))

    # Relay to user
    if t:
        user_id = t['user_id']
        header = (f"💬 *Support Ticket Update*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                  f"🎫 Ticket #{tid}: {escape_md(t['subject'])}\n"
                  f"📊 Status: 🔄 In Progress\n\n"
                  f"💬 *Admin replied:*")
        try:
            await context.bot.send_message(user_id, header, parse_mode="Markdown")
        except Exception:
            pass
        # Send media (if any) — caption already contains the admin's text
        if media_type:
            await relay_media_to(context.bot, user_id, media_type, media_id,
                                 caption=safe_text)
        elif safe_text:
            try:
                await context.bot.send_message(user_id, safe_text)
            except Exception:
                pass
        # Tail: reply button so user can keep chatting from their side
        try:
            await context.bot.send_message(
                user_id,
                "_Reply to admin below — you can also send photo/video/document._",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 Reply with Media/Text",
                                          callback_data=f"st_user_reply_{tid}")],
                    [InlineKeyboardButton("💬 View Chat",
                                          callback_data=f"st_user_chat_{tid}")],
                ]))
        except Exception:
            pass
    return ConversationHandler.END


# ───────────────────────────────────────────
# 🆕 v73: USER-SIDE reply (with media)
# ───────────────────────────────────────────

async def st_user_reply_callback(update, context):
    """User taps 'Reply with Media/Text' on an admin ticket update."""
    q = update.callback_query
    await q.answer()
    try:
        tid = int(q.data.replace("st_user_reply_", ""))
    except Exception:
        return ConversationHandler.END
    t = get_ticket(tid)
    if not t or t['user_id'] != q.from_user.id:
        await q.answer("❌ Not your ticket", show_alert=True)
        return ConversationHandler.END
    context.user_data['user_reply_tid'] = tid
    try:
        await q.edit_message_text(
            f"📝 *Reply to Ticket #{tid}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Send your reply now. You can send:\n"
            f"• ✏️ Text\n"
            f"• 📷 Photo (with caption)\n"
            f"• 🎬 Video (with caption)\n"
            f"• 📎 Document (with caption)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="support_menu")
            ]]))
    except Exception:
        await q.message.reply_text(
            f"📝 Reply to Ticket #{tid} — send text/photo/video now.")
    return 460  # USER reply state


async def st_user_reply_received(update, context):
    """🆕 v73: User sends a reply (text/photo/video/document) to their ticket."""
    tid = context.user_data.pop('user_reply_tid', None)
    if not tid:
        return ConversationHandler.END
    ensure_ticket_messages_table()
    msg = update.message
    uid = msg.from_user.id

    media_type, media_id, caption = extract_media(msg)
    text_body = caption if media_type else ((msg.text or "").strip() if msg.text else "")
    if not media_type and not text_body:
        await msg.reply_text("⚠️ Empty reply ignored. Send text or media.")
        return ConversationHandler.END

    safe_text = text_body[:2000]
    add_ticket_message(tid, "user", uid,
                       text=safe_text, media_type=media_type, media_id=media_id)
    # Reopen ticket if it was resolved/closed
    try:
        t = get_ticket(tid)
        if t and t['status'] in ('resolved', 'closed'):
            update_ticket(tid, status='in_progress')
    except Exception:
        pass

    await msg.reply_text(
        f"✅ *Reply sent for Ticket #{tid}*\n\n_Admin will see it shortly._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎫 My Tickets", callback_data="support_menu")
        ]]))

    # Notify admin
    try:
        header = (f"📩 *New reply on Ticket #{tid}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                  f"👤 From user `{uid}`")
        await context.bot.send_message(ADMIN_ID, header, parse_mode="Markdown")
        if media_type:
            await relay_media_to(context.bot, ADMIN_ID, media_type, media_id,
                                 caption=safe_text)
        elif safe_text:
            await context.bot.send_message(ADMIN_ID, safe_text)
        await context.bot.send_message(
            ADMIN_ID,
            f"_Open ticket to reply ↓_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Reply", callback_data=f"adm_st_reply_{tid}"),
                 InlineKeyboardButton("👀 View",  callback_data=f"adm_st_view_{tid}")],
            ]))
    except Exception:
        pass
    return ConversationHandler.END


# ───────────────────────────────────────────
# 🆕 v73: Chat history viewer (both sides)
# ───────────────────────────────────────────

def _format_chat_header(tid: int, t) -> str:
    return (f"💬 *Chat History — Ticket #{tid}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 Subject: {escape_md(t['subject']) if t else 'N/A'}\n\n")


async def adm_st_chat_callback(update, context):
    """Admin views full chat history (replays text + media)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        tid = int(q.data.replace("adm_st_chat_", ""))
    except Exception:
        return
    t = get_ticket(tid)
    await _replay_chat(context, q.message.chat_id, tid, t, is_admin=True)


async def st_user_chat_callback(update, context):
    """User views full chat history."""
    q = update.callback_query
    await q.answer()
    try:
        tid = int(q.data.replace("st_user_chat_", ""))
    except Exception:
        return
    t = get_ticket(tid)
    if not t or t['user_id'] != q.from_user.id:
        await q.answer("❌ Not your ticket", show_alert=True); return
    await _replay_chat(context, q.message.chat_id, tid, t, is_admin=False)


async def _replay_chat(context, chat_id, tid, t, is_admin: bool):
    """Send chat history as a sequence of messages (text + media replays)."""
    msgs = get_ticket_messages(tid, limit=200)
    header = _format_chat_header(tid, t)
    if not msgs:
        await context.bot.send_message(chat_id, header + "_No messages yet._",
                                        parse_mode="Markdown")
        return
    await context.bot.send_message(chat_id, header + f"_Replaying {len(msgs)} message(s)..._",
                                    parse_mode="Markdown")
    for m in msgs:
        sender_label = "👨‍💼 *Admin*" if m['sender'] == 'admin' else "👤 *User*"
        when = (m.get('created_at') or '')[:16]
        caption_prefix = f"{sender_label}  ·  _{when}_"
        text = m.get('text') or ""
        media_type = m.get('media_type') or ""
        media_id = m.get('media_id') or ""
        try:
            if media_type and media_id:
                # Build caption: header + text (truncate to fit Telegram caption ~1024)
                full_caption = caption_prefix
                if text:
                    full_caption += f"\n{text}"
                full_caption = full_caption[:1020]
                if media_type == "photo":
                    await context.bot.send_photo(chat_id, photo=media_id,
                                                 caption=full_caption,
                                                 parse_mode="Markdown")
                elif media_type == "video":
                    await context.bot.send_video(chat_id, video=media_id,
                                                 caption=full_caption,
                                                 parse_mode="Markdown")
                elif media_type == "document":
                    await context.bot.send_document(chat_id, document=media_id,
                                                    caption=full_caption,
                                                    parse_mode="Markdown")
                else:
                    await context.bot.send_message(chat_id,
                        f"{caption_prefix}\n{text}", parse_mode="Markdown")
            else:
                body = f"{caption_prefix}\n{text or '_(empty)_'}"
                await context.bot.send_message(chat_id, body, parse_mode="Markdown")
        except Exception as e:
            # Fail-safe — never lose the chat history if one message fails
            try:
                await context.bot.send_message(chat_id,
                    f"⚠️ Could not replay message {m.get('id')}: {e}")
            except Exception:
                pass


async def adm_st_resolve_callback(update, context):
    """Resolve a ticket"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("✅ Resolved!")
    tid = int(q.data.replace("adm_st_resolve_", ""))
    update_ticket(tid, status='resolved')
    t = get_ticket(tid)
    if t:
        try:
            await context.bot.send_message(t['user_id'],
                f"✅ *Ticket #{tid} Resolved!*\n\n{escape_md(t['subject'])}\n\n"
                f"Admin has resolved your ticket. Thank you!",
                parse_mode="Markdown")
        except:
            pass
    set_cb_data(update, f"adm_st_view_{tid}"); u = update
    await adm_st_view_callback(u, context)


async def adm_st_progress_callback(update, context):
    """Mark ticket as in progress"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("🔄 In Progress!")
    tid = int(q.data.replace("adm_st_progress_", ""))
    update_ticket(tid, status='in_progress')
    set_cb_data(update, f"adm_st_view_{tid}"); u = update
    await adm_st_view_callback(u, context)


async def adm_st_close_callback(update, context):
    """Close a ticket"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("🔒 Closed!")
    tid = int(q.data.replace("adm_st_close_", ""))
    update_ticket(tid, status='closed')
    set_cb_data(update, f"adm_st_view_{tid}"); u = update
    await adm_st_view_callback(u, context)


# ════════════════════════════════════════════
# 🛡️ ADMIN — Warranty/Refund Management
# ════════════════════════════════════════════

async def adm_warranty_callback(update, context):
    """Admin: Show all warranty/refund requests"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    nav_push(context, 'adm_warranty')

    requests = get_all_warranty_requests()
    pending = [w for w in requests if w['status'] == 'pending']

    text = (f"🛡️ *Warranty & Refund Requests*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 Total: {len(requests)}\n"
            f"🟡 Pending: {len(pending)}\n\n"
            f"Filter:")

    kb = [
        [InlineKeyboardButton(f"🟡 Pending ({len(pending)})", callback_data="adm_wr_pending")],
        [InlineKeyboardButton("📋 All Requests", callback_data="adm_wr_all")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")],
    ]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def adm_wr_list_callback(update, context):
    """Admin: Show warranty/refund list"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    status_filter = q.data.replace("adm_wr_", "")
    if status_filter == "all":
        reqs = get_all_warranty_requests()
        title = "📋 *All Requests*"
    else:
        reqs = get_all_warranty_requests('pending')
        title = "🟡 *Pending Requests*"

    if not reqs:
        await q.edit_message_text(f"{title}\n━━━━━━━━━━━━━━━━━━━━\n\nNo requests found.",
                                   parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_warranty")]]))
        return

    text = f"{title}\n━━━━━━━━━━━━━━━━━━━━\n\n"
    kb = []
    for w in reqs[:15]:
        o = get_order(w['order_id'])
        icon = "🛡️" if w['request_type'] == 'warranty' else "💰"
        status_icon = {'pending': '🟡', 'approved': '✅', 'rejected': '❌'}.get(w['status'], '❓')
        pname = o['product_name'][:25] if o else 'N/A'
        text += f"{icon} #{w['id']} Order#{w['order_id']}: {escape_md(pname)} {status_icon}\n"
        kb.append([InlineKeyboardButton(f"{icon} #{w['id']} Order#{w['order_id']} — {pname} {status_icon}",
                                         callback_data=f"adm_wr_view_{w['id']}")])

    kb.append([InlineKeyboardButton("🔙 Back", callback_data="adm_warranty")])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def adm_wr_view_callback(update, context):
    """Admin: View warranty/refund detail"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()

    wid = int(q.data.replace("adm_wr_view_", ""))
    w = get_warranty_request(wid)
    if not w:
        await q.answer("Not found", show_alert=True); return

    o = get_order(w['order_id'])
    try:
        u = get_user(w['user_id'])
        uname = u['first_name'] if u else 'N/A'
    except:
        uname = 'N/A'

    type_label = "🛡️ Warranty" if w['request_type'] == 'warranty' else "💰 Refund"
    status_map = {'pending': '🟡 Pending', 'approved': '✅ Approved', 'rejected': '❌ Rejected'}

    text = (f"{type_label} Request #{wid}\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 User: {escape_md(uname)} (`{w['user_id']}`)\n"
            f"📦 Order #{w['order_id']}: {escape_md(o['product_name'] if o else 'N/A')}\n"
            f"💰 Amount: ${o['price']:.2f}\n" if o else ""
            )
    text += (f"📊 Status: {status_map.get(w['status'], w['status'])}\n"
             f"📅 Date: {w['created_at'][:16]}\n\n"
             f"📝 *Reason:*\n{escape_md(w['reason'][:500])}\n")
    if w['admin_notes']:
        text += f"\n💬 *Admin Notes:* {escape_md(w['admin_notes'])}\n"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"adm_wr_approve_{wid}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"adm_wr_reject_{wid}")],
        [InlineKeyboardButton("🔙 Back", callback_data="adm_warranty")],
    ])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def adm_wr_approve_callback(update, context):
    """Admin approves warranty/refund"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("✅ Approved!")

    wid = int(q.data.replace("adm_wr_approve_", ""))
    w = get_warranty_request(wid)
    if not w:
        return

    update_warranty_request(wid, status='approved', admin_notes='Approved by admin')

    o = get_order(w['order_id'])

    # If refund → add points back to user
    if w['request_type'] == 'refund' and o:
        pts_refund = int(o['price'] * POINTS_PER_DOLLAR)
        add_points(w['user_id'], pts_refund)
    else:
        pts_refund = 0

    type_label = "🛡️ Warranty" if w['request_type'] == 'warranty' else "💰 Refund"
    
    user_msg = f"✅ *{type_label} Request Approved!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    user_msg += f"📦 Order #{w['order_id']}\n"
    if pts_refund > 0:
        user_msg += f"💎 *{pts_refund} points* refunded to your account!\n"
    else:
        user_msg += "Admin will process your warranty claim shortly.\n"

    try:
        await context.bot.send_message(w['user_id'], user_msg, parse_mode="Markdown")
    except:
        pass

    set_cb_data(update, f"adm_wr_view_{wid}"); u = update
    await adm_wr_view_callback(u, context)


async def adm_wr_reject_callback(update, context):
    """Admin rejects warranty/refund"""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("❌ Rejected!")

    wid = int(q.data.replace("adm_wr_reject_", ""))
    w = get_warranty_request(wid)
    if not w:
        return

    update_warranty_request(wid, status='rejected', admin_notes='Rejected by admin')

    type_label = "🛡️ Warranty" if w['request_type'] == 'warranty' else "💰 Refund"
    try:
        await context.bot.send_message(w['user_id'],
            f"❌ *{type_label} Request Rejected*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 Order #{w['order_id']}\n\n"
            f"Your request was not approved. Contact support for more info.",
            parse_mode="Markdown")
    except:
        pass

    set_cb_data(update, f"adm_wr_view_{wid}"); u = update
    await adm_wr_view_callback(u, context)


# ════════════════════════════════════════════
# 📦 MANUAL DELIVERY (Admin side)
# ════════════════════════════════════════════

async def adm_pending_delivery_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return

    from database import get_pending_deliveries
    orders = get_pending_deliveries()

    if not orders:
        await q.answer("No pending manual deliveries!", show_alert=True)
        await q.edit_message_text(
            "🎉 *All Caught Up!*\n━━━━━━━━━━━━━━━━━━━━\n\nThere are no pending manual deliveries at the moment.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]))
        return

    await q.answer()

    txt = "📦 *Pending Manual Deliveries*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    kb = []
    from database import get_product, get_user
    for idx, o in enumerate(orders[:8], start=1):
        p = get_product(o['product_id']) if o['product_id'] else None
        pd = dict(p) if p else {}
        fmt = normalize_product_format(pd.get('product_format', 'email_pass'))
        req_type = pd.get('req_account_type', 'none') or 'none'
        req_pass = bool(pd.get('req_password', 0))
        creds = (dict(o) if o else {}).get('customer_credentials', '') or ''
        pay = (o['payment_method'] or 'manual').title()
        amount = o['price'] or 0
        user = get_user(o['user_id'])
        username = (user['username'] if user and 'username' in user.keys() else '') or ''
        uname = f"@{username}" if username else escape_md(o['user_name'] or 'Customer')
        txt += (
            f"*{idx}) Order #{o['id']}* — {_fmt_msg_name(o['product_name'])}\n"
            f"👤 Customer: {uname} (`{o['user_id']}`)\n"
            f"💳 Payment: *{escape_md(pay)}* | Amount: `${amount}`\n"
            f"🧩 Format: *{escape_md(format_label(fmt))}*\n"
            f"⚙️ Requirement: `{escape_md(req_type)}` | Password: `{'Yes' if req_pass else 'No'}`\n"
        )
        if creds:
            preview = creds.replace('\n', ' | ')
            txt += f"📨 Customer Details: `{escape_md(preview[:120])}`\n"
        txt += "\n"
        # Direct Telegram deep link may work in Telegram clients; internal chat always works via bot.
        kb.append([
            InlineKeyboardButton(f"💬 Chat #{o['id']}", callback_data=f"adm_chat_{o['user_id']}"),
            InlineKeyboardButton(f"📦 Deliver #{o['id']}", callback_data=f"adm_deliver_{o['id']}")
        ])
        # 🆕 v65: Refund + Cancel buttons per pending order
        kb.append([
            InlineKeyboardButton(f"🔄 Refund #{o['id']}", callback_data=f"adm_refund_{o['id']}"),
            InlineKeyboardButton(f"❌ Cancel #{o['id']}",  callback_data=f"adm_cancel_{o['id']}")
        ])
        kb.append([InlineKeyboardButton(f"🔗 Open Telegram Chat #{o['id']}", url=f"tg://user?id={o['user_id']}")])

    if len(orders) > 8:
        txt += f"\n_Showing 8 of {len(orders)} pending orders._\n"
    kb.append([InlineKeyboardButton("🔄 Refresh", callback_data="adm_pending_delivery")])
    kb.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")])
    await _safe_edit(q, txt[:3900], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def adm_deliver_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return 403
    await q.answer()
    oid = int(q.data.replace("adm_deliver_", ""))
    from database import get_order, get_product
    o = get_order(oid)
    if not o:
        await q.edit_message_text("Order not found.")
        return ConversationHandler.END

    p = get_product(o['product_id']) if o['product_id'] else None
    pd = dict(p) if p else {}
    fmt = normalize_product_format(pd.get('product_format', 'email_pass'))
    context.user_data['manual_deliver_oid'] = oid
    context.user_data['manual_deliver_format'] = fmt

    creds = (dict(o) if o else {}).get('customer_credentials', '')
    txt = (
        f"📦 *Deliver Manual Order #{oid}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 Product: *{_fmt_msg_name(o['product_name'])}*\n"
        f"👤 Customer: `{o['user_id']}`\n"
        f"🧩 Required Format: *{escape_md(format_label(fmt))}*\n\n"
    )
    if creds:
        txt += f"📨 *Customer Provided Details:*\n`{escape_md(creds)}`\n\n"
    txt += (
        f"✍️ *Send delivery details now.*\n"
        f"Hint: {escape_md(format_hint(fmt))}\n\n"
        f"*Example:*\n`{escape_md(format_example(fmt))}`\n\n"
        f"After you send it, the customer will receive a professional Order Completed message with Buy More and Order History buttons.\n\n"
        f"Use /cancel to abort."
    )

    await q.edit_message_text(txt, parse_mode="Markdown")
    return 403


async def adm_delivery_text_received(update, context):
    oid = context.user_data.pop('manual_deliver_oid', None)
    context.user_data.pop('manual_deliver_format', None)
    if not oid:
        return ConversationHandler.END

    # 🆕 v72 BUG FIX: preserve admin's exact bytes — only check emptiness via
    # strip(), never modify what we save/deliver.
    delivery_text = update.message.text or ""
    if not delivery_text.strip():
        await update.message.reply_text("❌ Delivery text is empty. Please try again.")
        return 403

    from database import update_order_status, get_order, add_points, get_connection, save_order_delivery_content
    from config import POINTS_PER_DOLLAR

    o = get_order(oid)
    if o:
        p = get_product(o['product_id']) if o['product_id'] else None
        update_order_status(oid, 'delivered')
        save_order_delivery_content(oid, delivery_text)
        # 🆕 v69 BUG FIX: NO points credit on product delivery.
        pts = 0

        msg = _render_delivery_message_for_order(o, p, delivery_text)
        complete_header = (
            f"🎉 *Order Completed!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Your order has been completed successfully.\n"
            f"🧾 Order ID: `#{oid}`\n\n"
            f"📨 See the delivery details below."
        )
        # 🆕 v72: receipt header + delivery content sent separately so neither
        # mode interferes with the other. msg is the rendered HTML template
        # with [[HTML]] sentinel.

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Buy More", callback_data="shop")],
            [InlineKeyboardButton("📜 Order History", callback_data="my_orders")],
        ])
        try:
            # 🆕 v72: Send receipt header first (Markdown), then templated
            # delivery in HTML mode (preserves all bytes via <code> blocks).
            try:
                await context.bot.send_message(o['user_id'], complete_header,
                                                parse_mode="Markdown")
            except Exception:
                pass  # header is cosmetic — never block on its failure
            send_text, send_mode = smart_text_and_mode(msg, "Markdown")
            sent = await context.bot.send_message(o['user_id'], send_text,
                                                    parse_mode=send_mode,
                                                    reply_markup=kb)
            try:
                conn = get_connection(); cur = conn.cursor()
                cur.execute("UPDATE orders SET delivery_msg_id=? WHERE id=?", (sent.message_id, oid))
                conn.commit(); conn.close()
            except Exception:
                pass
        except Exception as e:
            await update.message.reply_text(f"⚠️ Order marked delivered, but message failed: {e}")
            return ConversationHandler.END

    await update.message.reply_text(
        f"✅ Order #{oid} delivered successfully!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Pending Manual Delivery", callback_data="adm_pending_delivery")],
            [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
        ])
    )
    return ConversationHandler.END


# ════════════════════════════════════════════
# 📦 DELIVERY MODE TOGGLE (per product)
# ════════════════════════════════════════════

async def adm_delivery_mode_callback(update, context):
    """Automation-only mode: always keep product delivery on auto."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer("Manual delivery removed", show_alert=True)

    pid = int(q.data.replace("adm_dmode_", ""))
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("UPDATE products SET delivery_mode='auto' WHERE id=?", (pid,))
        conn.commit(); conn.close()
    except Exception:
        pass

    from handlers_admin import admin_products_callback
    set_cb_data(update, "admin_products"); u = update
    await admin_products_callback(u, context)

async def adm_upacct_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: return
    await q.answer()
    oid = int(q.data.replace("adm_upacct_", ""))
    o = get_order(oid)
    p = get_product(o['product_id']) if o and o['product_id'] else None
    fmt = normalize_product_format((dict(p) if p else {}).get('product_format', 'email_pass'))
    c.user_data['upacct_oid'] = oid
    c.user_data['upacct_step'] = 'email'
    c.user_data['upacct_format'] = fmt
    c.user_data['upacct_raw_only'] = (fmt != 'email_pass')
    if fmt == 'email_pass':
        prompt = f"📤 *Upload Account for #{oid}*\n\n📝 Send the **Email**:"
    elif fmt == 'redeem_link':
        prompt = f"📤 *Upload Redeem Link for #{oid}*\n\n🖇️ Send the unique redeem link now:"
    else:
        prompt = f"📤 *Upload Coupon Code for #{oid}*\n\n🎁 Send the unique coupon code now:"
    await q.edit_message_text(prompt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]))

async def upacct_email_received(update, context):
    oid = context.user_data.get('upacct_oid')
    if not oid: return False
    if context.user_data.get('upacct_raw_only'):
        context.user_data['upacct_raw'] = update.message.text.strip()
        context.user_data['upacct_step'] = 'inst'
        kb = [[InlineKeyboardButton("⏭️ Skip Instructions", callback_data="upacct_skip_inst")]]
        await update.message.reply_text("ℹ️ Send optional **usage instructions** (or click Skip):", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return True
    context.user_data['upacct_email'] = update.message.text.strip()
    context.user_data['upacct_step'] = 'pass'
    await update.message.reply_text("🔑 Send the **Password**:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]))
    return True

async def upacct_pass_received(update, context):
    context.user_data['upacct_pass'] = update.message.text.strip()
    context.user_data['upacct_step'] = 'inst'
    kb = [[InlineKeyboardButton("⏭️ Skip Instructions", callback_data="upacct_skip_inst")]]
    await update.message.reply_text("ℹ️ Send **How to login/use instructions** (or click Skip):", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return True

async def upacct_skip_inst_callback(u, c):
    q = u.callback_query
    await q.answer()
    c.user_data['upacct_inst'] = ""
    await _finalize_upacct(q.message, c, is_query=True)

async def upacct_inst_received(update, context):
    context.user_data['upacct_inst'] = update.message.text.strip()
    await _finalize_upacct(update.message, context, is_query=False)
    return True

async def _finalize_upacct(msg_obj, context, is_query=False):
    oid = context.user_data.pop('upacct_oid', None)
    if not oid: return
    email = context.user_data.pop('upacct_email', '')
    pwd = context.user_data.pop('upacct_pass', '')
    raw_only = context.user_data.pop('upacct_raw_only', False)
    raw_value = context.user_data.pop('upacct_raw', '')
    inst = context.user_data.pop('upacct_inst', '')
    context.user_data.pop('upacct_format', None)
    context.user_data.pop('upacct_step', None)

    if raw_only:
        content = raw_value
    else:
        content = f"Email: {email}\nPassword: {pwd}"
    if inst:
        content += f"\n\nInstructions:\n{inst}"

    from database import get_order, update_order_status, add_points, get_connection
    from config import POINTS_PER_DOLLAR
    o = get_order(oid)
    if not o: return
    p = get_product(o['product_id']) if o['product_id'] else None

    update_order_status(oid, 'delivered')
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE orders SET delivery_content=? WHERE id=?", (content, oid))
    conn.commit(); conn.close()

    # 🆕 v69 BUG FIX: NO points credit on product delivery (was a free-refund bug)
    pts = 0

    msg = _render_delivery_message_for_order(o, p, content)

    try:
        send_text, send_mode = smart_text_and_mode(msg, "Markdown")
        await context.bot.send_message(o['user_id'], send_text, parse_mode=send_mode, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Buy More", callback_data="shop")],[InlineKeyboardButton("📜 Order History", callback_data="my_orders")]]))
    except: pass

    if is_query: await msg_obj.edit_text(f"✅ Delivered order #{oid} successfully!")
    else: await msg_obj.reply_text(f"✅ Delivered order #{oid} successfully!")

async def adm_chat_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: return
    await q.answer()
    uid = int(q.data.replace("adm_chat_", ""))
    c.user_data['admin_chat_uid'] = uid
    await q.edit_message_text(f"💬 Type the message you want to send to the customer (`{uid}`):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]))

async def admin_chat_received(update, context):
    uid = context.user_data.pop('admin_chat_uid', None)
    if not uid: return False
    msg = update.message.text
    try:
        kb = [[InlineKeyboardButton("💬 Reply to Admin", callback_data="reply_to_admin")]]
        await context.bot.send_message(uid, f"💬 *Message from Admin:*\n\n{escape_md(msg)}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("✅ Message sent to customer.")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send to customer (Maybe they blocked the bot?): {e}")
    return True

async def user_reply_to_admin_callback(u, c):
    q = u.callback_query
    await q.answer()
    c.user_data['user_chat_reply'] = True
    await q.message.reply_text("💬 *Type your reply to the Admin below:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_user_chat")]]))

async def cancel_user_chat_callback(u, c):
    q = u.callback_query
    await q.answer()
    c.user_data.pop('user_chat_reply', None)
    await q.edit_message_text("💬 Reply cancelled.")

async def user_reply_received(update, context):
    if not context.user_data.pop('user_chat_reply', False): return False
    msg = update.message.text
    uid = update.message.from_user.id
    uname = update.message.from_user.username or update.message.from_user.first_name
    from config import ADMIN_ID
    try:
        kb = [[InlineKeyboardButton("💬 Reply to User", callback_data=f"adm_chat_{uid}")]]
        await context.bot.send_message(ADMIN_ID, f"📩 *New Reply from Customer (@{escape_md(uname)} | `{uid}`):*\n\n{escape_md(msg)}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("✅ Your reply has been sent to the Admin.")
    except Exception as e:
        await update.message.reply_text("❌ Failed to send your reply.")
    return True

async def adm_ownmaildone_callback(u, c):
    q = u.callback_query
    if q.from_user.id != ADMIN_ID: return
    await q.answer()
    oid = int(q.data.replace("adm_ownmaildone_", ""))
    
    from database import get_order, update_order_status, add_points, get_connection
    from config import POINTS_PER_DOLLAR
    o = get_order(oid)
    if not o: return
    
    update_order_status(oid, 'delivered')
    content = "Done ✅ Own Mail Activation"
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE orders SET delivery_content=? WHERE id=?", (content, oid))
    conn.commit(); conn.close()
    
    # 🆕 v69 BUG FIX: NO points credit on product delivery (was a free-refund bug)
    msg = f"🎉 *Order Completed!*\n\n📦 *{o['product_name']}*\n\n✅ *Completed on your own account!*"
    
    try:
        send_text, send_mode = smart_text_and_mode(msg, "Markdown")
        await c.bot.send_message(o['user_id'], send_text, parse_mode=send_mode, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Buy More", callback_data="shop")],[InlineKeyboardButton("📜 Order History", callback_data="my_orders")]]))
    except: pass
    
    await q.edit_message_text(f"✅ Order #{oid} marked as Done (Own Mail).")

async def adm_restock_reqs_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: return
    
    from database import get_restock_requests
    reqs = get_restock_requests()
    
    if not reqs:
        await q.answer("No restock requests!", show_alert=True)
        await _safe_edit(q, "🎉 *All Good!*\n━━━━━━━━━━━━━━━━━━━━\n\nThere are no pending restock requests.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]))
        return
        
    await q.answer()
    txt = "🔄 *Product Restock Requests*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    kb = []
    for r in reqs[:15]:
        txt += f"📦 *{escape_md(r['name'])}* — {r['req_count']} requests\n"
        kb.append([InlineKeyboardButton(f"Add Stock: {r['name']} ({r['req_count']})", callback_data=f"prodaccounts_manage_{r['product_id']}")])
        
    kb.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")])
    await _safe_edit(q, txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
