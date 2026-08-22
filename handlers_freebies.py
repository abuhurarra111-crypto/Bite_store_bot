# ============================================================
# 🎁 v170.13 — FREEBIES (free products for every user)
# ============================================================
# User demand:
#   - Persistent reply-keyboard button "🎁 Freebies"
#   - Free products har user free claim kar sake (pehli baar 0 referrals)
#   - Admin settings: kaunsa product freebie hai, claim limit (kitni baar),
#     reclaim_refs (dobara claim ke liye referrals chahiye)
# Freebies = free-via-referrals (product_free_claim) se ALAG system hai.
# ============================================================

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID, SHOP_NAME
from utils import escape_md, smart_text_and_mode, html_strip_tags

logger = logging.getLogger(__name__)


def _r(key, default="", user_id=None):
    """Editable response with fallback."""
    try:
        from database import get_response_with_auto_register
        from config import DEFAULT_RESPONSES
        return get_response_with_auto_register(key, DEFAULT_RESPONSES.get(key, default))
    except Exception:
        return default


async def _safe_edit(q, text, **kwargs):
    try:
        await q.edit_message_text(text, **kwargs)
        return
    except Exception:
        if "parse" in str(kwargs).lower() and "parse_mode" in kwargs:
            k = dict(kwargs); k.pop("parse_mode", None)
            try:
                await q.edit_message_text(text, **k); return
            except Exception:
                pass
    try:
        await q.message.reply_text(text, **kwargs)
    except Exception:
        pass


def _clean_name(raw, limit=28):
    from utils import html_strip_tags
    s = html_strip_tags(str(raw or "")) or "Product"
    return s[:limit]


# ════════════════════════════════════════════════════════════════
# 👤 USER FLOW
# ════════════════════════════════════════════════════════════════

async def freebies_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎁 Freebies list (inline callback se) — enabled freebie products."""
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    uid = q.from_user.id
    await _show_freebies_menu(q, uid, from_text=False)


async def freebies_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎁 Freebies list (persistent reply-keyboard button se — text trigger)."""
    msg = update.message
    uid = update.effective_user.id
    await _show_freebies_menu(msg, uid, from_text=True)


async def _show_freebies_menu(target, uid, from_text=False):
    from database import get_all_freebie_products
    freebies = get_all_freebie_products()
    try:
        from button_system import make_premium_button, extract_emoji_from_html
        _have = True
    except Exception:
        _have = False

    try:
        from keyboards import _rb
    except Exception:
        _rb = None

    def _back_btn():
        if _rb:
            b = _rb("freebie_back", callback_data="main_menu")
            return b if b else InlineKeyboardButton("🔙 Back", callback_data="main_menu")
        return InlineKeyboardButton("🔙 Back", callback_data="main_menu")

    if not freebies:
        txt = _r("freebies_empty",
                 "🎁 *Freebies*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                 "_No free products available right now. Check back soon!_")
        kb = InlineKeyboardMarkup([[_back_btn()]])
    else:
        header = _r("freebies_menu_header",
                    "🎁 *Freebies*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    "_These products are 100% FREE — claim yours now!_")
        lines = header.split("\n") + [""]
        kb_rows = []
        for f in freebies:
            pid = int(f.get("product_id") or 0)
            raw = str(f.get("name") or f"#{pid}")
            # 🆕 v170.42: freebie display name (custom) — set ho to use karo
            try:
                from database import get_freebie_display_name
                _dn = get_freebie_display_name(pid)
                if _dn:
                    raw = _dn
            except Exception:
                pass
            plain, eid = raw, ""
            if _have:
                try:
                    _eid, _plain = extract_emoji_from_html(raw)
                    if _plain:
                        plain = _plain
                    eid = _eid or ""
                except Exception:
                    pass
            # Button aur upar wali bullet list DONO ek hi complete visible
            # name source use karein. Pehle top list _product_name_with_fixed_emoji
            # ke alag path se banti thi; Telegram premium-emoji rendering mein
            # us path ka naam pehle word tak reh jata tha, jabke button full tha.
            import html as _hlib
            import re as _re
            from utils import html_strip_tags
            _btnlbl = str(html_strip_tags(plain or raw or f"#{pid}")).strip() or f"#{pid}"

            if eid:
                # Premium icon ko preserve karke uske baad EXACT button wala
                # complete name lagao. Fallback emoji original <tg-emoji> tag
                # se lo; na mile to harmless 🎁 fallback use karo.
                _m = _re.search(
                    r'<tg-emoji\s+emoji-id=["\'][^"\']+["\']\s*>([^<]*)</tg-emoji>',
                    str(raw), flags=_re.IGNORECASE)
                _fallback = html_strip_tags(_m.group(1) if _m else "") or "🎁"
                _nm = (f'<tg-emoji emoji-id="{_hlib.escape(str(eid), quote=True)}">'
                       f'{_hlib.escape(_fallback)}</tg-emoji> '
                       f'{_hlib.escape(_btnlbl)}')
            else:
                _nm = _hlib.escape(_btnlbl)
            lines.append(f"• {_nm}")

            # Button par bhi POORA product name bhejo. Telegram client apni
            # screen width ke mutabiq visually wrap/clip kar sakta hai, lekin
            # bot naam ko khud truncate nahi karta.
            if _have:
                kb_rows.append([make_premium_button(
                    f"🎁 {_btnlbl}", emoji_id=eid or None,
                    style="success", callback_data=f"freebie_open_{pid}")])
            else:
                kb_rows.append([InlineKeyboardButton(
                    f"🎁 {_btnlbl}", callback_data=f"freebie_open_{pid}")])
        kb_rows.append([_back_btn()])
        txt = "\n".join(lines)
        kb = InlineKeyboardMarkup(kb_rows)

    _st, _sm = smart_text_and_mode(txt, "Markdown")
    try:
        if from_text:
            await target.reply_text(_st, parse_mode=_sm, reply_markup=kb)
        else:
            await target.edit_message_text(_st, parse_mode=_sm, reply_markup=kb)
    except Exception:
        try:
            if from_text:
                await target.reply_text(txt, reply_markup=kb)
            else:
                await target.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass


async def freebie_open_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User taps a freebie product → claim screen (status + rules)."""
    q = update.callback_query
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_open_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id")
        return
    uid = q.from_user.id
    await _show_freebie_product(q, uid, pid)


async def _show_freebie_product(q, uid, pid):
    from database import (get_product, get_freebie_config, freebie_claims_count,
                          get_referral_count, get_freebie_remaining_claims)
    prod = get_product(pid)
    cfg = get_freebie_config(pid)

    # 🆕 v170.43: freebie disabled/out-of-stock → "🔔 Notify Me" button
    try:
        _active = int((dict(prod) or {}).get("is_active") or 1) == 1
        from database import is_product_hidden
        _hidden = is_product_hidden(pid)
    except Exception:
        _active, _hidden = True, False
    if not prod or not _active or _hidden or not cfg.get("enabled"):
        from database import freebie_restock_request
        _msg = ("ℹ️ *This freebie is not available right now.*\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🔔 *Notify Me* tap karo — jab ye freebie wapas aayega, "
                "bot aapko message bhejega.")
        try:
            from keyboards import _rb
            back = _rb("freebie_back", callback_data="main_menu")
            menu = _rb("freebie_menu_back", callback_data="freebies_menu")
        except Exception:
            back = menu = None
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔔 Notify Me", callback_data=f"freebie_notify_{pid}")],
            [(menu if menu else InlineKeyboardButton("🎁 Freebies", callback_data="freebies_menu")),
             (back if back else InlineKeyboardButton("🔙 Back", callback_data="main_menu"))],
        ])
        _st, _sm = smart_text_and_mode(_msg, "Markdown")
        await _safe_edit(q, _st, parse_mode=_sm, reply_markup=kb)
        return

    claims = freebie_claims_count(uid, pid)
    limit = int(cfg.get("claim_limit") or 1)
    reclaim = int(cfg.get("reclaim_refs") or 0)
    refs_have = int(get_referral_count(uid) or 0)
    remaining = get_freebie_remaining_claims(pid)

    # Required refs for THIS claim: pehli claim 0, har agli claim reclaim × claims
    required_refs = 0 if claims == 0 else reclaim * claims

    try:
        from keyboards import _rb
    except Exception:
        _rb = None
    def _btn(reg_id, fallback_label, cb):
        if _rb:
            b = _rb(reg_id, callback_data=cb)
            return b if b else InlineKeyboardButton(fallback_label, callback_data=cb)
        return InlineKeyboardButton(fallback_label, callback_data=cb)
    def _back_btn():
        return _btn("freebie_back", "🔙 Back", "main_menu")
    def _menu_btn():
        return _btn("freebie_menu_back", "🎁 Freebies", "freebies_menu")

    # 🆕 v170.34: product name PREMIUM emoji ke saath render — FIXED emoji ya
    # name ke andar ka emoji, dono support (pehle sirf name wala).
    try:
        from fake_engagement import _product_name_with_fixed_emoji
        name_line = _product_name_with_fixed_emoji(prod)
    except Exception:
        try:
            from handlers_order import _fmt_msg_name
            name_line = _fmt_msg_name(prod.get("name") or "")
        except Exception:
            name_line = escape_md(_clean_name(prod.get("name") or "", 40))

    lines = [
        f"🎁 {name_line}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👥 Your claims: *{claims}*"
    ]
    if limit > 0:
        lines.append(f"🔢 Claim limit: *{limit}* (total)")
    else:
        lines.append("🔢 Claim limit: *Unlimited*")
    if reclaim > 0:
        lines.append(f"🔁 Re-claim rule: *{reclaim} referrals* per extra claim")
    # 🆕 v170.43: freebie ka apna stock (remaining claims)
    if remaining is not None:
        lines.append(f"📦 Remaining: *{remaining}* claims")
    lines.append("")

    # 🆕 v170.43: freebie stock khatam → Notify Me
    if remaining is not None and remaining <= 0:
        from database import freebie_restock_request
        lines.append("😔 Ye freebie abhi khatam ho gaya hai.")
        lines.append("🔔 *Notify Me* tap karo — wapas aane par bot batayega.")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔔 Notify Me", callback_data=f"freebie_notify_{pid}")],
            [_menu_btn(), _back_btn()],
        ])
    # limit check
    elif limit > 0 and claims >= limit and reclaim == 0:
        lines.append("❌ You reached the claim limit for this product.")
        kb = InlineKeyboardMarkup([[
            _menu_btn(),
            _back_btn(),
        ]])
    elif required_refs > 0 and refs_have < required_refs:
        lines.append(f"🔁 To claim again you need *{required_refs} referrals*.")
        lines.append(f"👥 Your referrals: *{refs_have}*")
        lines.append(f"⭐ You need *{required_refs - refs_have}* more.")
        kb = InlineKeyboardMarkup([
            [_btn("freebie_refer_earn", "🔗 Refer & Earn", "referral")],
            [_menu_btn(), _back_btn()],
        ])
    else:
        lines.append("✅ Ready to claim — FREE!")
        if required_refs > 0:
            lines.append(f"🔁 ({required_refs} referrals requirement met)")
        kb = InlineKeyboardMarkup([
            [_btn("freebie_claim_now", "🎉 Claim FREE Now", f"freebie_do_{pid}")],
            [_menu_btn(), _back_btn()],
        ])

    txt = "\n".join(lines)
    _st, _sm = smart_text_and_mode(txt, "Markdown")
    await _safe_edit(q, _st, parse_mode=_sm, reply_markup=kb)


async def freebie_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎉 User confirms freebie claim → deliver product."""
    q = update.callback_query
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_do_", ""))
    except Exception:
        await _safe_edit(q, "❌ Bad id")
        return

    # 🆕 v170.43: FORCE-JOIN zaroori — freebie claim se pehle membership check
    # (global gate ke sath sath yahan bhi explicit, defense-in-depth).
    try:
        from ui_extras import force_join_action_gate
        if await force_join_action_gate(update, context):
            return
    except Exception:
        pass

    uid = q.from_user.id
    user_obj = q.from_user

    from database import (get_product, get_freebie_config, freebie_claims_count,
                          get_referral_count, create_order, update_order_status,
                          get_order, get_freebie_remaining_claims)
    prod = get_product(pid)
    cfg = get_freebie_config(pid)
    if not prod or not cfg.get("enabled"):
        await _safe_edit(q, "ℹ️ This freebie is not available right now.")
        return
    # 🐛 v170.38 FIX: deleted/unsynced/hidden products claim nahi ho sakte
    try:
        if int((dict(prod) or {}).get("is_active") or 0) == 0:
            await _safe_edit(q, "ℹ️ This freebie is not available right now.")
            return
        from database import is_product_hidden
        if is_product_hidden(pid):
            await _safe_edit(q, "ℹ️ This freebie is not available right now.")
            return
    except Exception:
        pass

    # 🆕 v170.43: freebie ka apna stock (max_claims) — khatam to block
    remaining = get_freebie_remaining_claims(pid)
    if remaining is not None and remaining <= 0:
        await _safe_edit(q, "😔 Ye freebie abhi khatam ho gaya hai. "
                            "🔔 Notify Me se wapas aane par pata chalega.",
                         reply_markup=InlineKeyboardMarkup([[
                             InlineKeyboardButton("🔔 Notify Me",
                                                  callback_data=f"freebie_notify_{pid}"),
                             InlineKeyboardButton("🎁 Freebies", callback_data="freebies_menu")]]))
        return

    claims = freebie_claims_count(uid, pid)
    limit = int(cfg.get("claim_limit") or 1)
    reclaim = int(cfg.get("reclaim_refs") or 0)
    refs_have = int(get_referral_count(uid) or 0)
    required_refs = 0 if claims == 0 else reclaim * claims

    # limit + refs gates (race-safe re-check)
    if limit > 0 and claims >= limit and reclaim == 0:
        await _safe_edit(q, "❌ Claim limit reached.")
        return
    if required_refs > 0 and refs_have < required_refs:
        await _show_freebie_product(q, uid, pid)
        return

    # stock check
    try:
        stock_val = int(prod.get("stock") or 0)
    except Exception:
        stock_val = 0
    if stock_val <= 0:
        await _safe_edit(q, "😔 Out of stock right now. Please try later.",
                         reply_markup=InlineKeyboardMarkup([[
                             InlineKeyboardButton("🎁 Freebies", callback_data="freebies_menu")]]))
        return

    # create FREE order
    uname = user_obj.username or user_obj.first_name or ""
    try:
        oid = create_order(uid, uname, pid, prod.get("name") or "", 0.0,
                           method="freebie", bname="", bamt=0, bcur="",
                           otype="product", creds="")
        update_order_status(oid, "paid")
    except Exception as e:
        logger.exception("[freebie] create_order failed")
        await _safe_edit(q, f"⚠️ Could not create order: `{e}`", parse_mode="Markdown")
        return

    # record claim
    try:
        from database import record_freebie_claim
        record_freebie_claim(uid, pid, oid, required_refs)
    except Exception as e:
        logger.exception("[freebie] record failed")

    # 🆕 v170.28: DETAILED admin notification — supplier orders-delivered wali
    # tarah (username + premium emoji + claim # + PKT time + cost).
    try:
        from utils import notify_admin, fmt_price
        from datetime import datetime, timezone, timedelta
        # 🆕 v170.34: product premium emoji (FIXED ya name) — _fmt_msg_name sirf
        # name dekhta tha; fixed emoji products par simple emoji aata tha.
        try:
            from fake_engagement import _product_name_with_fixed_emoji as _pfn
            _prod_line = _pfn(prod)
        except Exception:
            from handlers_order import _fmt_msg_name
            _prod_line = _fmt_msg_name(prod.get('name'))
        # buyer name + @username
        fname = user_obj.first_name or ''
        uname = user_obj.username or ''
        try:
            from database import get_user as _gu
            _urow = _gu(uid)
            if _urow:
                if not fname:
                    fname = str(_urow.get('first_name') or '')
                if not uname:
                    uname = str(_urow.get('username') or '')
        except Exception:
            pass
        def _sp(s):
            try:
                import html as _h
                from utils import html_strip_tags as _hst
                s = _h.escape(_hst(s or '') or '')
            except Exception:
                pass
            return (str(s).replace('`', "'").replace('_', '&#95;')
                     .replace('*', '&#42;').replace('[', '&#91;').replace(']', '&#93;'))
        name_line = f"{_sp(fname)} (@{_sp(uname)})" if (fname and uname) else (_sp(fname) or _sp(uname) or '—')
        pk_time = datetime.now(timezone(timedelta(hours=5))).strftime('%Y-%m-%d %I:%M:%S %p PKT')
        try:
            cost = float((dict(prod) or {}).get('cost_price') or 0)
        except Exception:
            cost = 0.0
        await notify_admin(context.bot,
            f"🎁 *FREEBIE CLAIMED!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛒 Order: `#{oid}`\n"
            f"🕒 Time: `{pk_time}`\n"
            f"👤 Customer: `{name_line}` (`{uid}`)\n"
            f"📦 Product: {_prod_line}\n"
            f"🔁 Claim: #{claims + 1}\n"
            f"💳 Payment: `freebie`\n"
            f"💰 Cost: `{fmt_price(cost)}` · Sold: `$0`\n"
            f"📉 Loss: `{fmt_price(-cost)}`")
    except Exception:
        pass

    # deliver via central router
    try:
        from handlers_order import fulfill_paid_product_order
        order = get_order(oid)
        await fulfill_paid_product_order(
            context.bot, order, paid_amount=0.0,
            payment_method_label="🎁 FREEBIE", award_bonus=False)
    except Exception as e:
        logger.exception("[freebie] fulfill failed")
        try:
            await context.bot.send_message(uid, "⚠️ Delivery hiccup — admin will deliver manually.")
        except Exception:
            pass

    # confirmation
    try:
        confirm = _r("freebie_success",
                     "🎉 *Freebie Claimed!*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                     "📦 {product}\n✅ Delivered FREE above.\n\n"
                     "🔁 To claim again: {reclaim} referrals.")
        # 🆕 v170.34: product PREMIUM emoji (fixed ya name) ke saath render
        try:
            from fake_engagement import _product_name_with_fixed_emoji
            pname_line = _product_name_with_fixed_emoji(prod)
        except Exception:
            try:
                from handlers_order import _fmt_msg_name
                pname_line = _fmt_msg_name(prod.get('name') or "")
            except Exception:
                pname_line = escape_md(_clean_name(prod.get('name') or '', 60))
        confirm = confirm.replace("{product}", pname_line)
        confirm = confirm.replace("{reclaim}", str(reclaim))
        _st, _sm = smart_text_and_mode(confirm, "Markdown")
        await context.bot.send_message(uid, _st, parse_mode=_sm,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎁 Freebies", callback_data="freebies_menu")]]))
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# 🛠️ ADMIN PANEL (v170.42: management upgrade — tabs, search, sort,
#    pagination, stats, claim log, bulk, add, remove, display name)
# ════════════════════════════════════════════════════════════════

def _fb_view_state(context):
    return dict(context.user_data.get("fb_view") or {
        "tab": "freebies", "search": "", "sort": "recent", "page": 1,
        "claims_page": 0, "add_page": 0})


async def freebies_admin_panel_callback(update, context):
    """🎁 Freebies admin — management dashboard."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    st = _fb_view_state(context)
    st.update({"tab": "freebies", "page": 1, "search": "", "sort": "recent"})
    context.user_data["fb_view"] = st
    await _render_freebies_admin(q, context)


async def _render_freebies_admin(q, context):
    from database import get_freebies_management, get_freebies_stats
    try:
        from button_system import make_premium_button, extract_emoji_from_html
        _have = True
    except Exception:
        _have = False
    st = _fb_view_state(context)
    tab = st.get("tab", "freebies")
    search = st.get("search", "")
    sort = st.get("sort", "recent")
    page = int(st.get("page", 1))
    stats = get_freebies_stats()

    head_lines = [
        "🎁 *Freebies Admin*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📦 Freebies: *{stats['total']}* · 🧾 Claims: *{stats['claims']}* "
        f"(aaj {stats['today']})",
        f"💸 Total cost: *${stats['cost']:.2f}*",
        "",
    ]
    kb = []

    kb.append([
        InlineKeyboardButton(("🟢 " if tab == "freebies" else "⚪ ") + "Freebies",
                             callback_data="fb_tab_freebies"),
        InlineKeyboardButton(("🛒 " if tab == "all" else "⚪ ") + "All Products",
                             callback_data="fb_tab_all"),
        InlineKeyboardButton(("➕ " if tab == "add" else "⚪ ") + "Add Freebie",
                             callback_data="fb_tab_add"),
    ])

    kb.append([
        InlineKeyboardButton("🔍 Search" + (f": {search[:10]}" if search else ""),
                             callback_data="fb_search"),
        InlineKeyboardButton("📜 Claim Log", callback_data="fb_claimslog"),
    ])
    kb.append([
        InlineKeyboardButton("📊 Analytics", callback_data="fb_analytics"),
        InlineKeyboardButton("🔔 Restock Requests", callback_data="fb_restock_list"),
    ])
    if search:
        kb.append([InlineKeyboardButton("❌ Clear Search", callback_data="fb_clearsearch")])

    if tab == "add":
        from database import get_products_not_in_freebies
        res = get_products_not_in_freebies(search=search, page=page)
        items = res["items"]
        body = head_lines + [
            "_➕ Freebie banao — product tap karo:_",
            f"📄 Page {res['page']}/{res['total_pages']} · Total {res['total']}",
            "",
        ]
        for p in items:
            pid = int(p["id"])
            raw = str(p.get("name") or f"#{pid}")
            plain, eid = raw, ""
            if _have:
                try:
                    _eid, _plain = extract_emoji_from_html(raw)
                    if _plain:
                        plain = _plain
                    eid = _eid or ""
                except Exception:
                    pass
            body.append(f"🎁 #{pid} · {plain[:30]}")
            if _have:
                kb.append([make_premium_button(
                    f"🎁 Make Freebie — {plain[:22]}", emoji_id=eid or None,
                    style="primary", callback_data=f"fb_make_{pid}")])
            else:
                kb.append([InlineKeyboardButton(
                    f"🎁 Make Freebie — {plain[:22]}", callback_data=f"fb_make_{pid}")])
        _append_pager(kb, res["page"], res["total_pages"], "fb_addpage_")

    else:
        only_enabled = (tab == "freebies")
        res = get_freebies_management(search=search, only_enabled=only_enabled,
                                      sort=sort, page=page)
        items = res["items"]
        label = "Freebies (ON)" if tab == "freebies" else "All Products"
        body = head_lines + [f"_{label} — Page {res['page']}/{res['total_pages']}_", ""]
        if not items:
            body.append("_Koi products nahi milay._")
        for f in items:
            pid = int(f["product_id"])
            raw = str(f.get("display_name") or f.get("name") or f"#{pid}")
            plain, eid = raw, ""
            if _have:
                try:
                    _eid, _plain = extract_emoji_from_html(raw)
                    if _plain:
                        plain = _plain
                    eid = _eid or ""
                except Exception:
                    pass
            claims = int(f.get("claims") or 0)
            stock = int(f.get("stock") or 0)
            cost = float(f.get("cost_price") or 0)
            on = bool(f.get("enabled"))
            body.append(
                f"{'🟢' if on else '🔴'} #{pid} · {plain[:26]}\n"
                f"    🧾 {claims} claims · 📦 stock {stock} · 💸 ${cost * claims:.2f}")
            lbl = f"{'🟢 ON' if on else '🔴 OFF'} — {plain[:18]} ({claims})"
            if _have:
                kb.append([make_premium_button(
                    lbl, emoji_id=eid or None,
                    style="success" if on else "danger",
                    callback_data=f"freebie_cfg_{pid}")])
            else:
                kb.append([InlineKeyboardButton(lbl, callback_data=f"freebie_cfg_{pid}")])
        _append_pager(kb, res["page"], res["total_pages"], "fb_page_")

    if tab != "add":
        row = []
        for lbl, key in (("⏰ Recent", "recent"), ("🔥 Popular", "popular"),
                         ("📉 Low Stock", "lowstock"), ("🆕 New", "new")):
            row.append(InlineKeyboardButton(("✅ " if sort == key else "") + lbl,
                                            callback_data=f"fb_sort_{key}"))
        kb.append(row)

    kb.append([
        InlineKeyboardButton("🟢 All ON", callback_data="fb_bulk_on"),
        InlineKeyboardButton("🔴 All OFF", callback_data="fb_bulk_off"),
        InlineKeyboardButton("🔢 All Limit", callback_data="fb_bulk_limit"),
    ])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
    await _safe_edit(q, "\n".join(body), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


def _append_pager(kb, page, total_pages, prefix):
    if total_pages <= 1:
        return
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀", callback_data=f"{prefix}{page-1}"))
    nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="fb_noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶", callback_data=f"{prefix}{page+1}"))
    kb.append(nav)


async def fb_tab_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    tab = q.data.replace("fb_tab_", "")
    st = _fb_view_state(context)
    st.update({"tab": tab, "page": 1, "search": ""})
    context.user_data["fb_view"] = st
    await _render_freebies_admin(q, context)


async def fb_page_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        page = int(q.data.replace("fb_page_", ""))
    except Exception:
        return
    st = _fb_view_state(context)
    st["page"] = max(1, page)
    context.user_data["fb_view"] = st
    await _render_freebies_admin(q, context)


async def fb_addpage_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        page = int(q.data.replace("fb_addpage_", ""))
    except Exception:
        return
    st = _fb_view_state(context)
    st["add_page"] = max(1, page)
    st["page"] = st["add_page"]
    context.user_data["fb_view"] = st
    await _render_freebies_admin(q, context)


async def fb_sort_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    key = q.data.replace("fb_sort_", "")
    st = _fb_view_state(context)
    st["sort"] = key
    st["page"] = 1
    context.user_data["fb_view"] = st
    await _render_freebies_admin(q, context)


async def fb_clearsearch_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    st = _fb_view_state(context)
    st["search"] = ""
    st["page"] = 1
    context.user_data["fb_view"] = st
    await _render_freebies_admin(q, context)


async def fb_search_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    context.user_data["freebie_step"] = {"action": "search"}
    await _safe_edit(q,
        "🔍 *Freebies Search*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Product ka naam (ya part) bhejo — matching freebies/products dikhenge:\n\n"
        "_(/cancel to cancel)_", parse_mode="Markdown")


async def fb_bulk_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    action = q.data.replace("fb_bulk_", "")
    from database import set_all_freebies_enabled, set_all_freebies_claim_limit
    if action == "on":
        n = set_all_freebies_enabled(True)
        await q.answer(f"🟢 {n} freebies ON ✅", show_alert=True)
    elif action == "off":
        n = set_all_freebies_enabled(False)
        await q.answer(f"🔴 {n} freebies OFF ❌", show_alert=True)
    elif action == "limit":
        context.user_data["freebie_step"] = {"action": "bulk_limit"}
        await _safe_edit(q,
            "🔢 *All Freebies — Claim Limit*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "Sab freebies ke liye ek hi claim limit set karo (number, `0`=unlimited):\n\n"
            "_(/cancel to cancel)_", parse_mode="Markdown")
        return
    await _render_freebies_admin(q, context)


async def fb_make_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("fb_make_", ""))
    except Exception:
        return
    from database import set_freebie_config, get_product
    set_freebie_config(pid, enabled=1, claim_limit=1, reclaim_refs=0)
    name = _clean_name((get_product(pid) or {}).get("name") or f"#{pid}", 30)
    await q.answer(f"🎁 Freebie ban gaya: {name} ✅", show_alert=True)
    await _render_freebies_admin(q, context)


async def fb_remove_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("fb_remove_", ""))
    except Exception:
        return
    from database import remove_freebie, get_product
    name = _clean_name((get_product(pid) or {}).get("name") or f"#{pid}", 30)
    remove_freebie(pid)
    await q.answer(f"🗑 Freebie hata diya: {name}", show_alert=True)
    await _render_freebies_admin(q, context)


async def fb_claimslog_callback(update, context):
    """📜 Global freebie claim log (paginated, 15/page + filters: user/date)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    st = _fb_view_state(context)
    page = int(st.get("claims_page", 0))
    flt_user = st.get("claims_user", 0)
    flt_days = st.get("claims_days", 0)
    from database import get_all_freebie_claims
    rows = get_all_freebie_claims(limit=1000, user_id=flt_user or None,
                                  days=flt_days or None)
    per = 15
    total_pages = max(1, (len(rows) + per - 1) // per)
    page = max(0, min(page, total_pages - 1))
    st["claims_page"] = page
    context.user_data["fb_view"] = st
    chunk = rows[page * per:(page + 1) * per]
    fdesc = []
    if flt_user:
        fdesc.append(f"user `{flt_user}`")
    if flt_days:
        fdesc.append(f"last {flt_days}d")
    fdesc_txt = (" · " + ", ".join(fdesc)) if fdesc else ""
    lines = [f"📜 *Freebie Claims Log*{fdesc_txt}",
             f"━━━━━━━━━━━━━━━━━━━━",
             f"Total: *{len(rows)}* · page {page+1}/{total_pages}", ""]
    if not chunk:
        lines.append("_Koi claims nahi._")
    for r in chunk:
        uid = r.get("user_id")
        uname = f"@{r.get('username')}" if r.get("username") else (r.get("first_name") or "")
        who = " ".join(x for x in (uname, f"`{uid}`") if x)
        pname = _clean_name(r.get("product_name") or f"#{r.get('product_id')}", 20)
        at = str(r.get("claimed_at") or "")[:16]
        lines.append(f"• {pname} — {who}\n  #{r.get('id')} · {at}")
    kb = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀", callback_data=f"fb_clpage_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶", callback_data=f"fb_clpage_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([
        InlineKeyboardButton("👤 By User" + (" ✅" if flt_user else ""),
                             callback_data="fb_clfilter_user"),
        InlineKeyboardButton("🕐 Today" + (" ✅" if flt_days == 1 else ""),
                             callback_data="fb_clfilter_1d"),
        InlineKeyboardButton("📅 7d" + (" ✅" if flt_days == 7 else ""),
                             callback_data="fb_clfilter_7d"),
    ])
    kb.append([
        InlineKeyboardButton("🗓️ All", callback_data="fb_clfilter_all"),
        InlineKeyboardButton("🔙 Freebies Admin", callback_data="freebies_admin_panel"),
    ])
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def fb_clfilter_callback(update, context):
    """📜 Claim log filter (user id / date range)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    key = q.data.replace("fb_clfilter_", "")
    st = _fb_view_state(context)
    if key == "all":
        st["claims_user"] = 0; st["claims_days"] = 0
    elif key == "1d":
        st["claims_days"] = 1; st["claims_user"] = 0
    elif key == "7d":
        st["claims_days"] = 7; st["claims_user"] = 0
    elif key == "user":
        context.user_data["freebie_step"] = {"action": "claims_user"}
        await _safe_edit(q,
            "👤 *Claims — By User*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "User ka Telegram ID bhejo (sirf number):\n\n"
            "_(/cancel to cancel)_", parse_mode="Markdown")
        return
    st["claims_page"] = 0
    context.user_data["fb_view"] = st
    await fb_claimslog_callback(update, context)


async def fb_restock_list_callback(update, context):
    """🔔 Pending 'Notify Me' requests (freebies) list."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        from database import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("""SELECT r.product_id, p.name, COUNT(r.id) n
                     FROM restock_requests r
                     JOIN products p ON p.id = r.product_id
                     GROUP BY r.product_id ORDER BY n DESC LIMIT 20""")
        rows = [dict(r) for r in c.fetchall()]; conn.close()
    except Exception as e:
        await _safe_edit(q, f"❌ {e}"); return
    lines = ["🔔 *Freebie Restock Requests*",
             "━━━━━━━━━━━━━━━━━━━━"]
    if not rows:
        lines.append("_Koi pending requests nahi._")
    for r in rows:
        pname = _clean_name(r.get("name") or f"#{r.get('product_id')}", 30)
        lines.append(f"• #{r.get('product_id')} {pname}: *{r.get('n')}* users")
    kb = [[InlineKeyboardButton("🔙 Freebies Admin", callback_data="freebies_admin_panel")]]
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def fb_analytics_callback(update, context):
    """📊 Freebies analytics — 7-day trend + top freebies (text bar chart)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    from database import get_freebies_analytics
    an = get_freebies_analytics(days=7)
    daily = an["daily"]
    top = an["top"]
    lines = ["📊 *Freebies Analytics (7 days)*",
             "━━━━━━━━━━━━━━━━━━━━", ""]
    mx = max([d["count"] for d in daily] + [1])
    for d in daily:
        bar = "█" * max(1, round(d["count"] / mx * 14)) if d["count"] > 0 else "·"
        lines.append(f"`{d['date']}` {bar} {d['count']}")
    total_week = sum(d["count"] for d in daily)
    lines += ["", f"📅 Week total: *{total_week}* claims", "", "*🏆 Top Freebies:*"]
    if not top:
        lines.append("_(koi claims nahi)_")
    for t in top:
        pname = _clean_name(t.get("name") or f"#{t.get('id')}", 26)
        lines.append(f"• {pname}: *{t.get('n')}* claims")
    kb = [[InlineKeyboardButton("🔙 Freebies Admin", callback_data="freebies_admin_panel")]]
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def fb_clpage_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        page = int(q.data.replace("fb_clpage_", ""))
    except Exception:
        return
    st = _fb_view_state(context)
    st["claims_page"] = max(0, page)
    context.user_data["fb_view"] = st
    await fb_claimslog_callback(update, context)


async def fb_noop_callback(update, context):
    try:
        await update.callback_query.answer()
    except Exception:
        pass


async def _render_freebie_config(q, pid):
    """Shared render — freebie config screen (toggle + rules + stats + remove)."""
    from database import (get_product, get_freebie_config, get_freebie_total_claims,
                          get_freebie_display_name)
    prod = get_product(pid)
    cfg = get_freebie_config(pid)
    name = _clean_name(prod.get("name") or "", 40) if prod else f"#{pid}"
    claims = get_freebie_total_claims(pid)
    dname = get_freebie_display_name(pid)
    on = "🟢 ON" if cfg.get("enabled") else "🔴 OFF"
    maxc = int(cfg.get("max_claims") or 0)
    maxc_txt = "∞ (unlimited)" if maxc <= 0 else f"{maxc} (remaining {max(0, maxc-claims)})"
    dname_line = f"\n🏷️ Display name: *{escape_md(dname)}*" if dname else "\n🏷️ Display name: _(product name)_"
    text = (
        f"🎁 *Freebie — #{pid}*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 {escape_md(name)}\n"
        f"Status: *{on}* · 🧾 Claims: *{claims}*\n"
        f"🔢 Claim limit: *{cfg.get('claim_limit')}* (0=unlimited)\n"
        f"🔁 Re-claim refs: *{cfg.get('reclaim_refs')}* (0=free forever)\n"
        f"📦 Freebie stock: *{maxc_txt}*\n"
        f"{dname_line}\n\n"
        f"_Claim rule: pehli claim FREE; har agli claim ke liye "
        f"reclaim_refs × claims referrals chahiye._\n"
        f"_Freebie stock khatam hote hi auto-OFF ho jata hai._"
    )
    kb = [
        [InlineKeyboardButton("🔄 Toggle ON/OFF", callback_data=f"freebie_toggle_{pid}")],
        [InlineKeyboardButton("🔢 Set Claim Limit", callback_data=f"freebie_limit_{pid}"),
         InlineKeyboardButton("🔁 Set Re-claim Refs", callback_data=f"freebie_refs_{pid}")],
        [InlineKeyboardButton("📦 Set Freebie Stock", callback_data=f"freebie_maxclaims_{pid}")],
        [InlineKeyboardButton("🏷️ Display Name", callback_data=f"fb_dname_{pid}"),
         InlineKeyboardButton("📜 Claims", callback_data=f"fb_claims_{pid}")],
        [InlineKeyboardButton("🗑 Remove Freebie", callback_data=f"fb_remove_{pid}")],
        [InlineKeyboardButton("🔙 Freebies", callback_data="freebies_admin_panel")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def fb_claims_callback(update, context):
    """📜 Per-product freebie claim log."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("fb_claims_", ""))
    except Exception:
        return
    from database import get_freebie_claims_for_product, get_product, get_freebie_total_claims
    rows = get_freebie_claims_for_product(pid, limit=30)
    prod = get_product(pid)
    pname = _clean_name((prod.get("name") if prod else "") or f"#{pid}", 25)
    lines = [f"📜 *Claims — #{pid} {pname}*",
             f"━━━━━━━━━━━━━━━━━━━━",
             f"Total: *{get_freebie_total_claims(pid)}*", ""]
    if not rows:
        lines.append("_Koi claims nahi._")
    for r in rows:
        uid = r.get("user_id")
        uname = f"@{r.get('username')}" if r.get("username") else (r.get("first_name") or "")
        who = " ".join(x for x in (uname, f"`{uid}`") if x)
        at = str(r.get("claimed_at") or "")[:16]
        lines.append(f"• #{r.get('id')} — {who}\n  {at}")
    kb = [[InlineKeyboardButton("🔙 Freebie Config", callback_data=f"freebie_cfg_{pid}")]]
    await _safe_edit(q, "\n".join(lines), parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


async def fb_dname_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("fb_dname_", ""))
    except Exception:
        return
    context.user_data["freebie_step"] = {"action": "dname", "pid": pid}
    await _safe_edit(q,
        f"🏷️ *Display Name — #{pid}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Freebie ka custom naam bhejo (premium emoji ke saath):\n"
        f"Ya `-` bhejo to product ka asli naam use hoga.\n\n"
        f"_(/cancel to cancel)_", parse_mode="Markdown")


async def freebie_config_callback(update, context):
    """Per-product freebie config: toggle + claim limit + reclaim refs."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_cfg_", ""))
    except Exception:
        return
    await _render_freebie_config(q, pid)


async def freebie_toggle_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    try:
        pid = int(q.data.replace("freebie_toggle_", ""))
    except Exception:
        return
    from database import get_freebie_config, set_freebie_config
    cfg = get_freebie_config(pid)
    new_on = not bool(cfg.get("enabled"))
    set_freebie_config(pid, enabled=new_on)
    # 🆕 v170.43: freebie ON hone par "Notify Me" users ko batao + clear
    if new_on:
        try:
            await _notify_freebie_restock_users(context.bot, pid)
        except Exception:
            pass
    try:
        await q.answer(
            f"{'🟢 Freebie ON ✅' if new_on else '🔴 Freebie OFF ❌'}",
            show_alert=True)
    except Exception:
        pass
    await _render_freebie_config(q, pid)


async def _notify_freebie_restock_users(bot, pid):
    """🆕 v170.43: freebie wapas ON hone par pending 'Notify Me' users ko DM."""
    from database import freebie_restock_users, get_product, get_freebie_display_name
    try:
        users = freebie_restock_users(pid)
        if not users:
            return 0
        prod = get_product(pid)
        raw = (get_freebie_display_name(pid)
               or (str((dict(prod) if prod else {}).get("name") or f"#{pid}")))
        try:
            from utils import html_strip_tags
            pname = html_strip_tags(raw) or raw
        except Exception:
            pname = raw
        sent = 0
        for uid in users:
            try:
                await bot.send_message(
                    uid,
                    f"🔔 *Freebie Wapas Available!* 🎁\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📦 {pname[:60]}\n\n"
                    f"🎁 *FREE* — jaldi claim karo, stock khatam ho sakta hai!",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🎁 Claim FREE",
                                             callback_data=f"freebie_open_{pid}")]]))
                sent += 1
            except Exception:
                pass
        return sent
    except Exception:
        return 0


async def freebie_notify_callback(update, context):
    """🔔 User taps 'Notify Me' for a disabled/out-of-stock freebie."""
    q = update.callback_query
    await q.answer("🔔 Alert Set! Freebie wapas aane par bot batayega.", show_alert=True)
    try:
        pid = int(q.data.replace("freebie_notify_", ""))
    except Exception:
        return
    from database import freebie_restock_request
    freebie_restock_request(pid, q.from_user.id)


async def freebie_maxclaims_callback(update, context):
    """📦 Admin sets freebie ka apna stock (max claims; 0 = unlimited)."""
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_maxclaims_", ""))
    except Exception:
        return
    context.user_data["freebie_step"] = {"action": "maxclaims", "pid": pid}
    await _safe_edit(q,
        f"📦 *Freebie Stock — #{pid}*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Total kitne claims allow karne hain (poore freebie ke liye, sab users "
        f"mil kar)?\n"
        f"`0` = unlimited (kabhi khatam nahi)\n\n"
        f"⚠️ Stock khatam hote hi freebie *auto-OFF* ho jayega.\n\n"
        f"_(/cancel to cancel)_", parse_mode="Markdown")


async def freebie_limit_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_limit_", ""))
    except Exception:
        return
    context.user_data["freebie_step"] = {"action": "limit", "pid": pid}
    await _safe_edit(q,
        f"🔢 *Claim limit for #{pid}*\\n\\n"
        f"Send number (kitni baar claim kar sake; `0` = unlimited):\\n"
        f"_(/cancel to cancel)_", parse_mode="Markdown")


async def freebie_limit_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_limit_", ""))
    except Exception:
        return
    context.user_data["freebie_step"] = {"action": "limit", "pid": pid}
    await _safe_edit(q,
        f"🔢 *Claim limit for #{pid}*\n\n"
        f"Send number (kitni baar claim kar sake; `0` = unlimited):\n"
        f"_(/cancel to cancel)_", parse_mode="Markdown")


async def freebie_refs_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("❌", show_alert=True); return
    await q.answer()
    try:
        pid = int(q.data.replace("freebie_refs_", ""))
    except Exception:
        return
    context.user_data["freebie_step"] = {"action": "refs", "pid": pid}
    await _safe_edit(q,
        f"🔁 *Re-claim referrals for #{pid}*\n\n"
        f"Send number (dobara claim ke liye kitne referrals; `0` = free forever):\n"
        f"_(/cancel to cancel)_", parse_mode="Markdown")


async def freebie_step_received(update, context):
    """Admin text input: claim limit / reclaim refs / search / bulk limit / display name."""
    step = context.user_data.get("freebie_step")
    if not step:
        return False
    txt = (update.message.text or "").strip()
    if txt == "/cancel":
        context.user_data.pop("freebie_step", None)
        await update.message.reply_text("❌ Cancelled.")
        return True
    action = step.get("action")

    # 🆕 v170.42: search (free text)
    if action == "search":
        context.user_data.pop("freebie_step", None)
        st = _fb_view_state(context)
        st["search"] = txt
        st["page"] = 1
        context.user_data["fb_view"] = st
        await update.message.reply_text(
            f"🔍 Search set: *{txt}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎁 Freebies Admin", callback_data="freebies_admin_panel")]]))
        return True

    # 🆕 v170.43: claim log user filter
    if action == "claims_user":
        context.user_data.pop("freebie_step", None)
        try:
            uid = int(txt)
        except Exception:
            await update.message.reply_text("❌ Sirf number (Telegram ID) bhejo.")
            context.user_data["freebie_step"] = {"action": "claims_user"}
            return True
        st = _fb_view_state(context)
        st["claims_user"] = uid
        st["claims_days"] = 0
        st["claims_page"] = 0
        context.user_data["fb_view"] = st
        await update.message.reply_text(
            f"👤 Claims filter: user `{uid}` ✅",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📜 Claim Log", callback_data="fb_claimslog")]]))
        return True

    # 🆕 v170.42: display name (free text, premium emoji supported)
    if action == "dname":
        pid = int(step.get("pid") or 0)
        context.user_data.pop("freebie_step", None)
        from database import set_freebie_display_name
        if txt == "-":
            set_freebie_display_name(pid, "")
            await update.message.reply_text(
                f"🏷️ Display name for #{pid} → *(product name)*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data=f"freebie_cfg_{pid}")]]))
        else:
            try:
                html_v = (update.message.text_html_urled or "").strip()
            except Exception:
                html_v = ""
            if html_v and update.message.entities:
                val = "[[HTML]]" + html_v
            else:
                val = txt
            set_freebie_display_name(pid, val)
            await update.message.reply_text(
                f"🏷️ Display name for #{pid} saved ✅",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data=f"freebie_cfg_{pid}")]]))
        return True

    # numeric actions (limit / refs / bulk_limit)
    try:
        val = int(txt)
        if val < 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("❌ Enter a whole number ≥ 0.")
        return True

    if action == "bulk_limit":
        context.user_data.pop("freebie_step", None)
        from database import set_all_freebies_claim_limit
        n = set_all_freebies_claim_limit(val)
        await update.message.reply_text(
            f"✅ Claim limit for *{n} freebies* → *{val}*" + (" (unlimited)" if val == 0 else ""),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎁 Freebies Admin", callback_data="freebies_admin_panel")]]))
        return True

    from database import set_freebie_config
    pid = int(step.get("pid") or 0)
    if action == "limit":
        set_freebie_config(pid, claim_limit=val)
        await update.message.reply_text(
            f"✅ Claim limit for #{pid} → *{val}*" + (" (unlimited)" if val == 0 else ""),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data=f"freebie_cfg_{pid}")]]))
    elif action == "maxclaims":
        set_freebie_config(pid, max_claims=val)
        await update.message.reply_text(
            f"✅ Freebie stock for #{pid} → *{val}*" + (" (unlimited)" if val == 0 else ""),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data=f"freebie_cfg_{pid}")]]))
    else:
        set_freebie_config(pid, reclaim_refs=val)
        await update.message.reply_text(
            f"✅ Re-claim referrals for #{pid} → *{val}*" + (" (free forever)" if val == 0 else ""),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data=f"freebie_cfg_{pid}")]]))
    context.user_data.pop("freebie_step", None)
    return True
