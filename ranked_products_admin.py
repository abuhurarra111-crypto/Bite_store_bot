# -*- coding: utf-8 -*-
"""
ranked_products_admin.py — 🏆 Products Ranking & Mass Refund System

Features:
1. Single continuous list of all products ranked automatically by sales & orders
   (Top selling / most orders first).
2. Styled with green "success" buttons matching Warranty/Refund screen.
3. 1-Click Mass Refund to all delivered buyers with:
   - Time filters: All Time, Last 24 Hours, Last 7 Days, Last 30 Days, Custom Days.
   - Confirmation preview with total buyers, orders, points & USD calculation.
   - Product fate choice: Deactivate Product, Delete Product, or Keep Active.
   - Atomic wallet credits via points_ledger with idempotency.
   - Professional English notification sent to each buyer with updated balance.
   - Non-blocking rate-limited sending to prevent Telegram flood blocks.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID
from database import (
    get_connection, get_product, set_product_active,
    delete_product_permanently, update_order_status,
    add_points, get_user
)
from utils import points_from_usd, escape_md, fmt_price, smart_text_and_mode

logger = logging.getLogger(__name__)

# Max buttons per single list message (Telegram limit is 100)
RANKED_PAGE_SIZE = 80


def get_ranked_products_for_admin():
    """Fetch all products sorted by sales ranking (real_sold + delivered orders)."""
    conn = get_connection()
    c = conn.cursor()
    query = """
        SELECT p.id, p.name, p.price, p.stock, p.is_active,
               COALESCE(p.real_sold, 0) as real_sold,
               COALESCE(ord_counts.deliv_orders, 0) as deliv_orders,
               COALESCE(ord_counts.unique_buyers, 0) as unique_buyers,
               COALESCE(ord_counts.total_rev, 0.0) as total_rev,
               (COALESCE(p.real_sold, 0) + COALESCE(ord_counts.deliv_orders, 0)) as rank_score
        FROM products p
        LEFT JOIN (
            SELECT product_id,
                   count(*) as deliv_orders,
                   count(DISTINCT user_id) as unique_buyers,
                   sum(price) as total_rev
            FROM orders
            WHERE status = 'delivered'
            GROUP BY product_id
        ) ord_counts ON ord_counts.product_id = p.id
        ORDER BY rank_score DESC, p.id DESC
    """
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _clean_pname(raw_name):
    """Extract plain text and emoji from HTML if present."""
    raw_name = str(raw_name or 'Product')
    plain = raw_name
    eid = ""
    try:
        from button_system import extract_emoji_from_html
        _eid, _plain = extract_emoji_from_html(raw_name)
        if _plain:
            plain = _plain
        eid = _eid or ""
    except Exception:
        pass
    return plain.strip(), eid


async def admin_ranked_products_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Render single ranked products list (starts at offset 0)."""
    q = update.callback_query
    if not q or q.from_user.id != ADMIN_ID:
        if q: await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()
    await _show_ranked_list(q, offset=0)


async def admin_ranked_products_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle overflow offset for remaining products."""
    q = update.callback_query
    if not q or q.from_user.id != ADMIN_ID:
        if q: await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()
    try:
        offset = int(str(q.data).replace("rk_page_", ""))
    except Exception:
        offset = 0
    await _show_ranked_list(q, offset=offset)


async def _show_ranked_list(q, offset=0):
    products = get_ranked_products_for_admin()
    total = len(products)
    active_count = sum(1 for p in products if p.get('is_active'))

    chunk = products[offset:offset + RANKED_PAGE_SIZE]
    has_more = (offset + RANKED_PAGE_SIZE) < total

    text = (
        f"🏆 *Products Sales Ranking & Mass Refund*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Sorted automatically by sales & delivered orders.\n"
        f"Tap any product to view buyers or issue *Mass Refunds*.\n\n"
        f"📊 *Total Products:* {total} | *Active:* {active_count}\n"
    )
    if offset > 0:
        text += f"Showing ranks *#{offset + 1}* to *#{min(offset + len(chunk), total)}*:\n"

    try:
        from button_system import make_premium_button
        _have_premium = True
    except Exception:
        _have_premium = False

    kb = []
    for idx, p in enumerate(chunk):
        rank_num = offset + idx + 1
        plain, eid = _clean_pname(p.get('name'))
        price = float(p.get('price') or 0.0)
        score = int(p.get('rank_score') or 0)
        status_dot = "🟢" if p.get('is_active') else "🔴"

        # Styled label: Rank + Name + Sales score + Price
        label = f"#{rank_num} {status_dot} {plain[:20]} — 🔥{score} | ${price:.2f}"
        pid = p['id']

        if _have_premium:
            try:
                btn = make_premium_button(label, emoji_id=eid or None, style="success",
                                           callback_data=f"rk_prod_{pid}")
            except Exception:
                btn = InlineKeyboardButton(label, callback_data=f"rk_prod_{pid}")
        else:
            btn = InlineKeyboardButton(label, callback_data=f"rk_prod_{pid}")

        kb.append([btn])

    # Smart Overflow / Navigation
    nav_row = []
    if offset > 0:
        prev_off = max(0, offset - RANKED_PAGE_SIZE)
        nav_row.append(InlineKeyboardButton("⬆️ Previous", callback_data=f"rk_page_{prev_off}"))
    if has_more:
        next_off = offset + RANKED_PAGE_SIZE
        nav_row.append(InlineKeyboardButton(f"⬇️ More Products (#{next_off + 1}+)", callback_data=f"rk_page_{next_off}"))
    if nav_row:
        kb.append(nav_row)

    kb.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")])

    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        logger.error(f"[RankedProducts] Render error: {e}")
        try:
            await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        except Exception:
            pass


async def rk_product_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product detail, analytics, and action choices."""
    q = update.callback_query
    if not q or q.from_user.id != ADMIN_ID:
        if q: await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()

    try:
        pid = int(str(q.data).replace("rk_prod_", ""))
    except Exception:
        await q.answer("❌ Invalid ID", show_alert=True)
        return

    p = get_product(pid)
    if not p:
        await q.answer("❌ Product not found", show_alert=True)
        return

    plain, _ = _clean_pname(p.get('name'))
    price = float(p.get('price') or 0.0)
    stock = p.get('stock')
    is_active = bool(p.get('is_active'))
    real_sold = int(p.get('real_sold') or 0)

    # Order stats from DB
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT count(*) as deliv_orders,
               count(DISTINCT user_id) as unique_buyers,
               sum(price) as total_rev
        FROM orders
        WHERE product_id = ? AND status = 'delivered'
    """, (pid,))
    row = c.fetchone()
    conn.close()

    deliv_orders = int(row['deliv_orders'] if row else 0)
    unique_buyers = int(row['unique_buyers'] if row else 0)
    total_rev = float(row['total_rev'] or 0.0)
    rank_score = real_sold + deliv_orders

    status_str = "🟢 Active (Visible)" if is_active else "🔴 Deactivated (Hidden)"

    text = (
        f"📦 *Product Details & Mass Actions*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📛 *Name:* {escape_md(plain)}\n"
        f"🆔 *Product ID:* `{pid}`\n"
        f"💵 *Price:* ${price:.2f} ({points_from_usd(price):,.1f} pts)\n"
        f"📦 *Stock:* `{stock}` | *Status:* {status_str}\n\n"
        f"📊 *Sales Analytics:*\n"
        f"🔥 Total Sales Score: *{rank_score}*\n"
        f"📦 Delivered Orders: *{deliv_orders}*\n"
        f"👥 Unique Buyers: *{unique_buyers} users*\n"
        f"💰 Estimated Revenue: *${total_rev:.2f}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Select an action below:"
    )

    toggle_btn_text = "⏸️ Deactivate Product" if is_active else "▶️ Reactivate Product"

    kb = [
        [InlineKeyboardButton("💸 Mass Refund Buyers", callback_data=f"rk_ref_menu_{pid}")],
        [
            InlineKeyboardButton(toggle_btn_text, callback_data=f"rk_toggle_{pid}"),
            InlineKeyboardButton("🗑️ Delete Product", callback_data=f"rk_del_confirm_{pid}"),
        ],
        [InlineKeyboardButton("✏️ Edit Product Details", callback_data=f"viewprod_{pid}")],
        [InlineKeyboardButton("🔙 Back to Ranked List", callback_data="admin_ranked_products")],
    ]

    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def rk_product_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle product active/deactive status."""
    q = update.callback_query
    if not q or q.from_user.id != ADMIN_ID: return
    try:
        pid = int(str(q.data).replace("rk_toggle_", ""))
    except Exception:
        await q.answer("❌ Invalid ID", show_alert=True); return

    p = get_product(pid)
    if not p:
        await q.answer("❌ Product not found", show_alert=True); return

    new_state = not bool(p.get('is_active'))
    set_product_active(pid, new_state)
    await q.answer("✅ Product Reactivated" if new_state else "🚫 Product Deactivated", show_alert=False)
    # Refresh
    q.data = f"rk_prod_{pid}"
    await rk_product_detail_callback(update, context)


async def rk_product_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmation prompt before hard deleting a product."""
    q = update.callback_query
    if not q or q.from_user.id != ADMIN_ID: return
    try:
        pid = int(str(q.data).replace("rk_del_confirm_", ""))
    except Exception:
        await q.answer("❌ Invalid ID", show_alert=True); return

    p = get_product(pid)
    plain, _ = _clean_pname(p.get('name') if p else '')

    text = (
        f"⚠️ *Confirm Product Deletion*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Are you sure you want to permanently delete:\n"
        f"📦 *{escape_md(plain)}* (ID: `{pid}`)?\n\n"
        f"This will remove the product and its unsold accounts pool.\n"
        f"Historical orders remain safely preserved."
    )
    kb = [
        [InlineKeyboardButton("🗑️ Yes, Delete Product", callback_data=f"rk_del_do_{pid}")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"rk_prod_{pid}")],
    ]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def rk_product_delete_execute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute product deletion."""
    q = update.callback_query
    if not q or q.from_user.id != ADMIN_ID: return
    try:
        pid = int(str(q.data).replace("rk_del_do_", ""))
    except Exception:
        await q.answer("❌ Invalid ID", show_alert=True); return

    try:
        delete_product_permanently(pid)
        await q.answer("✅ Product deleted permanently", show_alert=True)
    except Exception as e:
        await q.answer(f"❌ Delete failed: {e}", show_alert=True)
    await _show_ranked_list(q, offset=0)


async def rk_refund_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show time window choices for mass refund."""
    q = update.callback_query
    if not q or q.from_user.id != ADMIN_ID: return
    await q.answer()

    try:
        pid = int(str(q.data).replace("rk_ref_menu_", ""))
    except Exception:
        await q.answer("❌ Invalid ID", show_alert=True); return

    p = get_product(pid)
    if not p:
        await q.answer("❌ Product not found", show_alert=True); return

    plain, _ = _clean_pname(p.get('name'))

    text = (
        f"💸 *Mass Refund — Choose Time Window*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Product:* {escape_md(plain)} (ID: `{pid}`)\n\n"
        f"Select which buyers should receive wallet point refunds:\n\n"
        f"🌐 *All Time* — Every delivered order ever made\n"
        f"⏱️ *Last 24 Hours* — Orders placed in last 24h\n"
        f"📅 *Last 7 Days* — Orders placed in last 7 days\n"
        f"🗓️ *Last 30 Days* — Orders placed in last 30 days\n"
        f"✏️ *Custom Days* — Enter exact days (e.g. 3, 14, 45)"
    )

    kb = [
        [InlineKeyboardButton("🌐 All Time Buyers", callback_data=f"rk_rf_win_{pid}_all")],
        [
            InlineKeyboardButton("⏱️ Last 24 Hours", callback_data=f"rk_rf_win_{pid}_24h"),
            InlineKeyboardButton("📅 Last 7 Days", callback_data=f"rk_rf_win_{pid}_7d"),
        ],
        [
            InlineKeyboardButton("🗓️ Last 30 Days", callback_data=f"rk_rf_win_{pid}_30d"),
            InlineKeyboardButton("✏️ Custom Days", callback_data=f"rk_rf_win_{pid}_custom"),
        ],
        [InlineKeyboardButton("🔙 Back to Product", callback_data=f"rk_prod_{pid}")],
    ]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


def _fetch_eligible_refund_orders(pid, window_str):
    """Query orders eligible for mass refund based on time window."""
    conn = get_connection()
    c = conn.cursor()

    base_query = """
        SELECT id, user_id, price, product_name, created_at, status, payment_method
        FROM orders
        WHERE product_id = ?
          AND status = 'delivered'
          AND price > 0
          AND LOWER(payment_method) != 'freebie'
    """
    params = [pid]

    now = datetime.now()
    cutoff = None
    if window_str == "24h":
        cutoff = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    elif window_str == "7d":
        cutoff = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    elif window_str == "30d":
        cutoff = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    elif window_str.endswith("d") and window_str[:-1].isdigit():
        days = int(window_str[:-1])
        cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    if cutoff:
        base_query += " AND created_at >= ?"
        params.append(cutoff)

    base_query += " ORDER BY id ASC"
    c.execute(base_query, tuple(params))
    rows = c.fetchall()

    # Also check points_ledger to ensure none of these have already received mass_product_refund
    c.execute("SELECT order_id FROM points_ledger WHERE tx_type='mass_product_refund'")
    already_refunded_oids = set(int(r[0] or 0) for r in c.fetchall())
    conn.close()

    eligible = []
    for r in rows:
        d = dict(r)
        if d['id'] not in already_refunded_oids:
            eligible.append(d)
    return eligible


async def rk_refund_window_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle window selection or prompt custom days input."""
    q = update.callback_query
    if not q or q.from_user.id != ADMIN_ID: return
    await q.answer()

    # Format: rk_rf_win_{pid}_{win}
    parts = q.data.replace("rk_rf_win_", "").split("_", 1)
    if len(parts) != 2:
        await q.answer("❌ Invalid data", show_alert=True); return
    pid, win = int(parts[0]), parts[1]

    if win == "custom":
        context.user_data['mass_refund_custom_pid'] = pid
        text = (
            f"✏️ *Enter Custom Days for Mass Refund*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Please reply with the number of days back to refund (e.g. `3`, `5`, `14`, `45`).\n\n"
            f"_Type the number in chat, or tap Cancel below._"
        )
        kb = [[InlineKeyboardButton("❌ Cancel", callback_data=f"rk_prod_{pid}")]]
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    await show_mass_refund_preview(update, context, pid, win, query=q)


async def handle_custom_days_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check and handle custom days text from admin."""
    pid = context.user_data.get('mass_refund_custom_pid')
    if not pid:
        return False

    if update.effective_user.id != ADMIN_ID:
        return False

    text = update.message.text.strip()
    try:
        days = int(text)
        if days <= 0 or days > 3650:
            await update.message.reply_text("❌ Please enter a positive number of days between 1 and 3650:")
            return True
    except ValueError:
        await update.message.reply_text("❌ Invalid number. Please enter a valid number of days (e.g. `7`):")
        return True

    del context.user_data['mass_refund_custom_pid']
    win = f"{days}d"
    await show_mass_refund_preview(update, context, pid, win, message=update.message)
    return True


async def show_mass_refund_preview(update, context, pid, win, query=None, message=None):
    """Render preview of refund calculation and prompt for product action."""
    p = get_product(pid)
    if not p:
        err = "❌ Product not found"
        if query: await query.answer(err, show_alert=True)
        elif message: await message.reply_text(err)
        return

    plain, _ = _clean_pname(p.get('name'))
    orders = _fetch_eligible_refund_orders(pid, win)

    window_labels = {
        "all": "🌐 All Time",
        "24h": "⏱️ Last 24 Hours",
        "7d": "📅 Last 7 Days",
        "30d": "🗓️ Last 30 Days",
    }
    if win not in window_labels and win.endswith("d"):
        w_lbl = f"🗓️ Last {win[:-1]} Days"
    else:
        w_lbl = window_labels.get(win, win)

    if not orders:
        text = (
            f"ℹ️ *No Eligible Orders Found*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Product: *{escape_md(plain)}* (ID: `{pid}`)\n"
            f"Window: *{w_lbl}*\n\n"
            f"No delivered orders were found in this time period, or all buyers have already been refunded."
        )
        kb = [
            [InlineKeyboardButton("🔄 Choose Different Window", callback_data=f"rk_ref_menu_{pid}")],
            [InlineKeyboardButton("🔙 Back to Product", callback_data=f"rk_prod_{pid}")],
        ]
        if query:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        elif message:
            await message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    unique_users = len(set(o['user_id'] for o in orders))
    order_count = len(orders)
    total_pts = sum(points_from_usd(float(o['price'] or 0)) for o in orders)
    total_usd = sum(float(o['price'] or 0) for o in orders)

    # Store cache in context for execution
    context.user_data[f"mass_rf_{pid}"] = {
        "win": win,
        "orders": orders,
        "total_pts": total_pts,
        "unique_users": unique_users,
    }

    text = (
        f"⚠️ *MASS REFUND PREVIEW & PRODUCT ACTION*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Product:* {escape_md(plain)} (ID: `{pid}`)\n"
        f"⏱️ *Time Window:* {w_lbl}\n"
        f"👥 *Eligible Buyers:* *{unique_users} Users*\n"
        f"📦 *Delivered Orders:* *{order_count} Orders*\n"
        f"💎 *Total Points to Refund:* *{total_pts:,.1f} Points* (~${total_usd:.2f})\n\n"
        f"⚠️ *Important:* Each buyer will instantly receive their exact purchase points in their wallet with an English notification.\n\n"
        f"⚙️ *What should happen to this product?*\n"
        f"Choose an action below to proceed with refund:"
    )

    kb = [
        [InlineKeyboardButton("⏸️ Deactivate Product & Refund", callback_data=f"rk_rf_do_{pid}_{win}_deact")],
        [InlineKeyboardButton("🗑️ Delete Product & Refund", callback_data=f"rk_rf_do_{pid}_{win}_del")],
        [InlineKeyboardButton("🔄 Keep Product Active & Refund", callback_data=f"rk_rf_do_{pid}_{win}_keep")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"rk_prod_{pid}")],
    ]

    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    elif message:
        await message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def rk_refund_execute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute the mass refund and the chosen product action."""
    q = update.callback_query
    if not q or q.from_user.id != ADMIN_ID: return
    await q.answer()

    # Format: rk_rf_do_{pid}_{win}_{action}
    raw = q.data.replace("rk_rf_do_", "")
    parts = raw.split("_")
    if len(parts) < 3:
        await q.answer("❌ Invalid payload", show_alert=True); return

    pid = int(parts[0])
    action = parts[-1]  # 'deact', 'del', 'keep'
    win = "_".join(parts[1:-1])

    p = get_product(pid)
    plain_name, _ = _clean_pname(p.get('name') if p else 'Discontinued Product')

    # Fetch cached or fresh eligible orders
    cached = context.user_data.get(f"mass_rf_{pid}")
    if cached and cached.get('orders'):
        orders = cached['orders']
    else:
        orders = _fetch_eligible_refund_orders(pid, win)

    if not orders:
        await q.answer("❌ No eligible orders found", show_alert=True)
        q.data = f"rk_prod_{pid}"
        await rk_product_detail_callback(update, context)
        return

    await q.edit_message_text(
        f"⏳ *Processing Mass Refund...*\n"
        f"Refunds are being credited to {len(orders)} order(s). Please wait...",
        parse_mode="Markdown"
    )

    # 1. Product Action Execution
    action_label = "Keep Active"
    if action == "deact":
        set_product_active(pid, False)
        action_label = "Deactivated ⏸️"
    elif action == "del":
        action_label = "Deleted 🗑️ (Scheduled post-refund)"
    elif action == "keep":
        action_label = "Kept Active 🔄"

    # 2. Loop through orders, credit points, notify users
    success_orders = 0
    success_users = set()
    total_pts_credited = 0.0

    for ord_item in orders:
        oid = int(ord_item['id'])
        uid = int(ord_item['user_id'])
        price = float(ord_item.get('price') or 0.0)
        pts = points_from_usd(price)
        event_id = f"mass_product_refund_{oid}"

        # Add points via atomic idempotency function
        ok = add_points(
            uid=uid,
            pts=pts,
            tx_type="mass_product_refund",
            description=f"Mass refund for {plain_name} (#{oid})",
            event_id=event_id,
            order_id=oid
        )

        if ok:
            success_orders += 1
            success_users.add(uid)
            total_pts_credited += pts
            # Update order status to refunded
            try:
                update_order_status(oid, 'refunded')
            except Exception as ex:
                logger.warning(f"[MassRefund] order {oid} status update error: {ex}")

            # Send English customer notification
            try:
                u = get_user(uid)
                new_balance = float((u.get('points') if u else 0.0) or 0.0)
                buyer_msg = (
                    f"💰 *Wallet Refund Credited!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"We apologize for the inconvenience. Your purchased item has ceased working or been discontinued.\n\n"
                    f"📦 *Product:* {escape_md(plain_name)}\n"
                    f"🆔 *Order ID:* `#{oid}`\n"
                    f"➕ *Refund Credited:* `+{pts:,.1f} Points` (${price:.2f})\n"
                    f"💼 *New Wallet Balance:* `{new_balance:,.1f} Points`\n\n"
                    f"These points have been credited to your wallet balance and can be used immediately on any store product. Thank you for your patience!"
                )
                _t, _pm = smart_text_and_mode(buyer_msg, "Markdown")
                await context.bot.send_message(chat_id=uid, text=_t, parse_mode=_pm)
            except Exception as e_send:
                logger.info(f"[MassRefund] Could not notify user {uid}: {e_send}")

            # Safe spacing to prevent Telegram API flood
            await asyncio.sleep(0.04)

    # 3. If delete chosen, permanently delete product now
    if action == "del":
        try:
            delete_product_permanently(pid)
            action_label = "Deleted Permanently 🗑️"
        except Exception as e_del:
            action_label = f"Delete Error: {e_del}"

    # Clear cache
    context.user_data.pop(f"mass_rf_{pid}", None)

    summary_text = (
        f"✅ *Mass Refund Completed Successfully!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Product:* {escape_md(plain_name)}\n"
        f"👥 *Users Refunded:* *{len(success_users)} users*\n"
        f"📦 *Orders Refunded:* *{success_orders} orders*\n"
        f"💎 *Total Points Credited:* *{total_pts_credited:,.1f} Points*\n"
        f"⚙️ *Product Action:* *{action_label}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"All wallet points have been credited safely and notifications sent."
    )

    kb = [
        [InlineKeyboardButton("🏆 Back to Ranked Products", callback_data="admin_ranked_products")],
        [InlineKeyboardButton("🏠 Admin Panel", callback_data="admin_panel")],
    ]
    await q.edit_message_text(summary_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
