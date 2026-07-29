# ============================================
# 🏠 START & MENU
# ============================================
from telegram import Update
from telegram.ext import ContextTypes
from config import *
from keyboards import *
from database import *
from utils import escape_md, format_date, notify_admin, nav_push, nav_pop, set_cb_data, smart_text_and_mode, fmt_price, fmt_points

def _r(key, user_id=None):
    """🆕 v79: Optional user_id triggers per-language lookup first.
    Falls back to admin-customizable English when no translation exists.
    """
    if user_id is not None:
        try:
            from i18n_responses import get_translated_response
            tr = get_translated_response(key, user_id=user_id)
            if tr is not None:
                return tr
        except Exception:
            pass
    from database import get_response_with_auto_register
    return get_response_with_auto_register(key, DEFAULT_RESPONSES.get(key,""))


async def _safe_edit(q, text, **kwargs):
    send_text, send_mode = smart_text_and_mode(text, kwargs.get("parse_mode", "Markdown"))
    send_kwargs = dict(kwargs)
    send_kwargs["parse_mode"] = send_mode
    # 1. Try editing as a regular text message
    try:
        await q.edit_message_text(send_text, **send_kwargs)
        return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in send_kwargs:
            kwargs_no_md = dict(send_kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.edit_message_text(send_text, **kwargs_no_md)
                return
            except Exception:
                pass

    # 2. Fallback: edit caption (works on photo/video messages)
    try:
        await q.edit_message_caption(caption=send_text, **send_kwargs)
        return
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in send_kwargs:
            kwargs_no_md = dict(send_kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.edit_message_caption(caption=send_text, **kwargs_no_md)
                return
            except Exception:
                pass

    # 3. Last resort: reply_text
    try:
        await q.message.reply_text(send_text, **send_kwargs)
    except Exception as e:
        if "parse entities" in str(e).lower() and "parse_mode" in send_kwargs:
            kwargs_no_md = dict(send_kwargs)
            kwargs_no_md.pop("parse_mode")
            try:
                await q.message.reply_text(send_text, **kwargs_no_md)
            except Exception:
                pass


async def _panic_reset_user_session(update: Update, context: ContextTypes.DEFAULT_TYPE, *, keep_language=True):
    """Force-close every active conversation/session for this user.

    Used by /start and persistent 🏠 Main Menu. This is intentionally aggressive:
    any admin/user flow, payment step, supplier wizard, broadcast state, etc. is
    wiped so the requested command/menu runs cleanly.
    """
    try:
        safe_keys = {"language"} if keep_language else set()
        ud = context.user_data
        if ud is not None:
            for k in list(ud.keys()):
                if k not in safe_keys:
                    ud.pop(k, None)
    except Exception:
        pass
    try:
        from telegram.ext import ConversationHandler
        chat_id = update.effective_chat.id if update.effective_chat else 0
        user_id = update.effective_user.id if update.effective_user else 0
        app = context.application if hasattr(context, "application") else None
        if app is not None and (chat_id or user_id):
            for _group, handlers in list(app.handlers.items()):
                for h in handlers:
                    if not isinstance(h, ConversationHandler):
                        continue
                    conv_map = getattr(h, "_conversations", None)
                    if conv_map is None:
                        continue
                    for key in list(conv_map.keys()):
                        if isinstance(key, tuple) and ((chat_id and chat_id in key) or (user_id and user_id in key)):
                            conv_map.pop(key, None)
    except Exception as _e:
        import logging as _l
        _l.getLogger(__name__).debug(f"[panic_reset] end-conv err: {_e}")

# ════════════════════════════════════════════════════════════════
# 🆕 v48: Referral attribution with anti-fake checks (instant, no delay)
# ════════════════════════════════════════════════════════════════

REFERRAL_MILESTONE_EVERY = 20
REFERRAL_MILESTONE_BONUS_POINTS = 10

_DEFAULT_REFERRER_REFERRAL_TEMPLATE = """🎉 *New Referral Joined!*\n━━━━━━━━━━━━━━━━━━━━\n\n👤 Referred user: *{referred_name}*\n🆔 Referred ID: `{referred_id}`\n\n✅ Reward: *+{reward_points} referral point*\n📊 Your direct referrals: *{total_referrals}*\n🎯 Next bonus: *{remaining_to_bonus}* more referrals → *+{milestone_bonus} wallet points* ($1)\n\nKeep sharing your link and earning rewards! 🚀"""

_DEFAULT_ADMIN_REFERRAL_TEMPLATE = """🎁 *New Direct Referral*\n━━━━━━━━━━━━━━━━━━━━\n\n👑 Referrer:\n• Name: *{referrer_name}*\n• Username: @{referrer_username}\n• ID: `{referrer_id}`\n\n🆕 Referred User:\n• Name: *{referred_name}*\n• Username: @{referred_username}\n• ID: `{referred_id}`\n\n🎯 Reward: +{reward_points} referral point\n📊 Referrer's direct referrals: {total_referrals}"""

_DEFAULT_MILESTONE_TEMPLATE = """🏆 *Referral Milestone Unlocked!*\n━━━━━━━━━━━━━━━━━━━━\n\n🔥 You reached *{milestone_number} direct referrals*!\n🎁 Bonus reward: *+{milestone_bonus} wallet points* ($1)\n💎 Wallet bonus has been added to your balance.\n\nNext milestone: *{next_milestone} referrals* 🚀"""

_DEFAULT_PRODUCT_REFERRER_TEMPLATE = """🎁 *Product Referral Counted!*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Product: *{product_name}*\n👤 New user: *{referred_name}*\n🆔 User ID: `{referred_id}`\n\n📊 Your progress: *{product_referrals}/{product_required}*\n🎯 Need *{product_remaining}* more referral(s) to claim this product free.\n\nKeep sharing this product link! 🚀"""

_DEFAULT_PRODUCT_UNLOCK_TEMPLATE = """🎉 *Free Product Unlocked!*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Product: *{product_name}*\n✅ Progress complete: *{product_referrals}/{product_required}*\n\nYou can now claim this product for FREE. Tap the button below."""

_DEFAULT_PRODUCT_ADMIN_TEMPLATE = """🎁 *Product Referral Counted*\n━━━━━━━━━━━━━━━━━━━━\n\n📦 Product: *{product_name}* (`#{product_id}`)\n📊 Progress: *{product_referrals}/{product_required}*\n🎯 Remaining: *{product_remaining}*\n\n👑 Referrer:\n• Name: *{referrer_name}*\n• Username: @{referrer_username}\n• ID: `{referrer_id}`\n\n🆕 Referred User:\n• Name: *{referred_name}*\n• Username: @{referred_username}\n• ID: `{referred_id}`"""


def _ref_display_user(user_or_row, fallback_id=0):
    """Return safe referral display data for Telegram user object or DB row."""
    try:
        uid = int(getattr(user_or_row, 'id', 0) or (user_or_row.get('user_id') if hasattr(user_or_row, 'get') else user_or_row['user_id']) or fallback_id)
    except Exception:
        uid = int(fallback_id or 0)
    try:
        first = getattr(user_or_row, 'first_name', None)
        if first is None:
            first = user_or_row.get('first_name') if hasattr(user_or_row, 'get') else user_or_row['first_name']
    except Exception:
        first = ''
    try:
        username = getattr(user_or_row, 'username', None)
        if username is None:
            username = user_or_row.get('username') if hasattr(user_or_row, 'get') else user_or_row['username']
    except Exception:
        username = ''
    return {
        'id': uid,
        'name': escape_md(first or 'User'),
        'username': escape_md((username or 'no_username').lstrip('@')),
    }


def _render_referral_template(setting_key, default_template, values):
    try:
        from database import get_setting
        tpl = get_setting(setting_key, default_template) or default_template
    except Exception:
        tpl = default_template
    safe_values = {k: escape_md(v) if isinstance(v, str) else v for k, v in (values or {}).items()}
    try:
        return tpl.format(**safe_values)
    except Exception:
        return default_template.format(**safe_values)


async def _send_referral_message(bot, chat_id, text, **kwargs):
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    try:
        return await bot.send_message(chat_id, send_text, parse_mode=send_mode, **kwargs)
    except Exception:
        kwargs.pop('reply_markup', None)
        try:
            return await bot.send_message(chat_id, send_text, parse_mode=send_mode)
        except Exception:
            return None


async def _send_direct_referral_notifications(context, referrer_id, new_user, reward_points, direct_count):
    """Notify referrer + admin for accepted direct referral and pay milestone."""
    try:
        from database import get_user, add_points, get_setting, set_setting
        ref_row = get_user(referrer_id)
    except Exception:
        ref_row = None
    ref = _ref_display_user(ref_row, referrer_id)
    new = _ref_display_user(new_user, getattr(new_user, 'id', 0))
    remaining = REFERRAL_MILESTONE_EVERY - (int(direct_count) % REFERRAL_MILESTONE_EVERY)
    if remaining == REFERRAL_MILESTONE_EVERY:
        remaining = 0
    next_milestone = ((int(direct_count) // REFERRAL_MILESTONE_EVERY) + 1) * REFERRAL_MILESTONE_EVERY
    values = {
        'referrer_id': ref['id'], 'referrer_name': ref['name'], 'referrer_username': ref['username'],
        'referred_id': new['id'], 'referred_name': new['name'], 'referred_username': new['username'],
        'reward_points': fmt_points(reward_points),
        'total_referrals': int(direct_count),
        'remaining_to_bonus': int(remaining),
        'milestone_bonus': fmt_points(REFERRAL_MILESTONE_BONUS_POINTS),
        'milestone_number': int(direct_count),
        'next_milestone': int(next_milestone),
    }
    # Referrer notification
    try:
        await _send_referral_message(
            context.bot, referrer_id,
            _render_referral_template('ref_tpl_referrer', _DEFAULT_REFERRER_REFERRAL_TEMPLATE, values))
    except Exception:
        pass
    # Admin notification
    try:
        await notify_admin(context.bot,
            _render_referral_template('ref_tpl_admin', _DEFAULT_ADMIN_REFERRAL_TEMPLATE, values))
    except Exception:
        pass
    # Every 20 direct referrals: +10 wallet points bonus, paid once per milestone.
    try:
        if int(direct_count) > 0 and int(direct_count) % REFERRAL_MILESTONE_EVERY == 0:
            key = f"ref_milestone_paid_{int(referrer_id)}"
            last_paid = int(get_setting(key, '0') or 0)
            if last_paid < int(direct_count):
                add_points(referrer_id, REFERRAL_MILESTONE_BONUS_POINTS, tx_type='referral_milestone', description='20 referral milestone', event_id=f"ref_milestone_{int(referrer_id)}_{int(direct_count)}")
                set_setting(key, str(int(direct_count)))
                values['next_milestone'] = int(direct_count) + REFERRAL_MILESTONE_EVERY
                await _send_referral_message(
                    context.bot, referrer_id,
                    _render_referral_template('ref_tpl_milestone', _DEFAULT_MILESTONE_TEMPLATE, values))
    except Exception:
        pass


async def _send_product_referral_notifications(context, referrer_id, new_user,
                                               product_id, product_name,
                                               current, required, unlocked=False):
    try:
        from database import get_user
        ref_row = get_user(referrer_id)
    except Exception:
        ref_row = None
    ref = _ref_display_user(ref_row, referrer_id)
    new = _ref_display_user(new_user, getattr(new_user, 'id', 0))
    remaining = max(0, int(required) - int(current))
    values = {
        'referrer_id': ref['id'], 'referrer_name': ref['name'], 'referrer_username': ref['username'],
        'referred_id': new['id'], 'referred_name': new['name'], 'referred_username': new['username'],
        'product_id': int(product_id), 'product_name': product_name,
        'product_referrals': int(current), 'product_required': int(required),
        'product_remaining': int(remaining),
    }
    try:
        if unlocked:
            from telegram import InlineKeyboardMarkup
            try:
                from button_system import build_button, wrap_button
                btn = build_button('ref_unlock_claim_btn', '🎁 Claim FREE Now', callback_data=f"freeclaim_do_{int(product_id)}")
                btn = wrap_button('ref_unlock_claim_btn', btn)
            except Exception:
                from telegram import InlineKeyboardButton
                btn = InlineKeyboardButton("🎁 Claim FREE Now", callback_data=f"freeclaim_do_{int(product_id)}")
            kb = InlineKeyboardMarkup([[btn]])
            await _send_referral_message(
                context.bot, referrer_id,
                _render_referral_template('ref_tpl_product_unlock', _DEFAULT_PRODUCT_UNLOCK_TEMPLATE, values),
                reply_markup=kb)
        else:
            await _send_referral_message(
                context.bot, referrer_id,
                _render_referral_template('ref_tpl_product_referrer', _DEFAULT_PRODUCT_REFERRER_TEMPLATE, values))
    except Exception:
        pass
    try:
        await notify_admin(context.bot,
            _render_referral_template('ref_tpl_product_admin', _DEFAULT_PRODUCT_ADMIN_TEMPLATE, values))
    except Exception:
        pass


async def _process_referral_attribution(context, new_user, referrer_id, is_new_user,
                                        product_id=0, approve_now=False):
    """Process a referral attempt instantly. Always logs to referral_log.

    🆕 v102: `product_id` param. When set (>0), this is a "free-via-referrals"
    link — the referral counts ONLY toward that product's requirement, and
    NO reward point is added to the general ref_points pool. When 0, it's
    a normal direct referral link → +1 ref_point as before.

    🆕 v110: ATTRIBUTION RULES OVERHAUL based on pro Telegram referral bots
    (BotFather Deep Link docs + top-tier referral bots research).

    The old rule "block if user already existed in DB" caused MASSIVE silent
    losses — Telegram shows the START button even for users who already
    interacted with the bot (per official docs), so a "not new" user tapping
    a friend's link would be silently rejected. Zero counts in real DB
    proved this.

    NEW rule set:
      1. Block if new user is a bot                                     (dead)
      2. Block self-referral                                            (essential)
      3. Block if the user ALREADY HAS a referrer set                   (one-time credit)
      4. [REMOVED] "must be brand new user" — replaced by rule #3
      5. Block if referrer is banned                                    (abuse gate)
      6. Block if referrer doesn't exist                                 (bad link)
      7. Anti-burst: ONLY for GENERAL referrals (product mode is exempt
         because no ref_points reward → nothing to abuse). Threshold
         relaxed from 5→10 in 60s.
      8. Anti-duplicate-name: same (only when username empty)
      9. Block if BOTH first_name AND username empty                     (bot detect)

    Every event is logged AND admin gets a compact DM notification for
    both counted + blocked attempts (so future issues are diagnosable).

    On success: +1 ref_point to referrer (direct mode only), notify referrer
    + admin, fire fake-activity broadcast.
    """
    from database import (
        get_user, set_referred_by, increment_referral_count,
        add_ref_points, is_referrer_banned, log_referral_attempt,
        count_referrals_by_referrer_recent, get_recent_referred_first_names,
        get_referral_count, add_pending_referral, mark_pending_referral_done,
    )

    def _reject(reason):
        log_referral_attempt(referrer_id, new_user.id, "blocked", reason)
        # Notify admin so abuse is visible (silent to user)
        try:
            import asyncio
            asyncio.create_task(notify_admin(context.bot,
                f"🚫 *Referral Blocked*\n"
                f"From: `{referrer_id}`\n"
                f"To:   `{new_user.id}` ({escape_md(new_user.first_name or 'N/A')})\n"
                f"Reason: _{reason}_"))
        except Exception:
            pass
        return False

    # ── 1. Bot check ──
    if getattr(new_user, "is_bot", False):
        return _reject("new_user_is_bot")

    # ── 2. Self-referral ──
    if int(referrer_id) == int(new_user.id):
        return _reject("self_referral")

    # ── 3. Already has a referrer? (one-time credit only) ──
    # 🆕 v110: removed the "must-be-brand-new-user" block. Telegram's own
    # docs confirm the Start button appears with the deep-link parameter
    # even for returning users, so rejecting non-new users silently killed
    # 100% of real-world referrals. We now only guard against DOUBLE
    # attribution via referred_by column.
    db_new = get_user(new_user.id)
    if db_new is not None:
        try:
            if db_new["referred_by"] and int(db_new["referred_by"]) != 0:
                return _reject("already_has_referrer")
        except Exception:
            pass

    # ── 5. Referrer banned? ──
    if is_referrer_banned(referrer_id):
        return _reject("referrer_banned")

    # ── 6. Referrer exists? ──
    referrer_row = get_user(referrer_id)
    if referrer_row is None:
        return _reject("referrer_unknown")

    # ── 7. Anti-burst: too many referrals in last 60s ──
    # 🆕 v110: RELAXED — threshold 5→10 (viral products can bring 10+ users/min)
    # + EXEMPT for product-mode (no ref_points reward means no abuse incentive)
    if not (product_id and int(product_id) > 0):
        recent_60s = count_referrals_by_referrer_recent(referrer_id, minutes=1)
        if recent_60s >= 10:
            return _reject(f"burst_10_in_60s ({recent_60s} found)")

    # ── 8. Anti-duplicate-name within 60 min ──
    new_fn = (new_user.first_name or "").strip().lower()
    new_un = (new_user.username or "").strip().lower()
    if new_fn and not new_un:
        # Only check when username is empty (real users with usernames are usually distinct)
        recent_names = get_recent_referred_first_names(referrer_id, minutes=60)
        same_pattern = sum(
            1 for fn, un in recent_names
            if (fn or "").strip().lower() == new_fn and not (un or "").strip()
        )
        if same_pattern >= 2:
            return _reject(f"duplicate_first_name ({new_fn!r} seen {same_pattern}x)")

    # ── 9. Both first_name AND username empty = highly suspicious ──
    if not new_fn and not new_un:
        return _reject("empty_name_and_username")

    # ── v128: pending approval gate ──
    # Referral is recorded after /start + force-join check, but reward is only
    # credited when the referred user opens Shop or stays active for 30 seconds.
    if not approve_now:
        try:
            add_pending_referral(referrer_id, new_user.id, int(product_id or 0), 'start_complete')
            log_referral_attempt(referrer_id, new_user.id, 'pending', f'pending_pid_{int(product_id or 0)}')
            # Schedule 30-second active approval as fallback; opening Shop also approves immediately.
            try:
                if getattr(context, 'job_queue', None):
                    context.job_queue.run_once(_pending_referral_job, 30, data={'uid': int(new_user.id)}, name=f'pending_ref_{int(new_user.id)}')
            except Exception:
                pass
            try:
                await notify_admin(context.bot,
                    f"⏳ *Referral Pending*\n"
                    f"Referrer: `{referrer_id}`\n"
                    f"New user: `{new_user.id}` ({escape_md(new_user.first_name or 'N/A')})\n"
                    f"Product: `{int(product_id or 0)}`\n"
                    f"Reward will be approved when user opens Shop or stays active 30s.")
            except Exception:
                pass
        except Exception:
            pass
        return True

    try:
        mark_pending_referral_done(new_user.id, 'approved', 'activity_verified')
    except Exception:
        pass

    # ─────────────  ACCEPTED — AWARD AFTER APPROVAL ─────────────
    set_referred_by(new_user.id, referrer_id)
    increment_referral_count(referrer_id)  # lifetime stat (both modes)

    # 🆕 v102: BRANCH — product-specific vs general referral
    if product_id and int(product_id) > 0:
        # Product-specific: counts toward THIS product's requirement only,
        # NO ref_point reward
        from database import (add_product_ref, count_product_refs,
                              get_product_free_config, get_product,
                              clear_product_refs)
        added = add_product_ref(referrer_id, int(product_id), new_user.id)
        # dedupe: same friend already counted for this product → do nothing extra
        if not added:
            log_referral_attempt(referrer_id, new_user.id, "counted",
                                 f"dup_product_ref_pid_{product_id}")
        else:
            log_referral_attempt(referrer_id, new_user.id, "counted",
                                 f"product_ref_pid_{product_id}")
            cfg = get_product_free_config(int(product_id))
            required = int(cfg.get("required_refs", 5) or 5)
            current = count_product_refs(referrer_id, int(product_id))
            product = get_product(int(product_id))
            pname = (dict(product).get("name", "product") if product else "product")
            try:
                from utils import name_for_button
                pname_display = name_for_button(pname) or pname
            except Exception:
                pname_display = pname

            # Product-specific referral notifications (separate from direct referral rewards)
            await _send_product_referral_notifications(
                context, referrer_id, new_user, int(product_id),
                pname_display, current, required, unlocked=(current >= required))
    else:
        # General direct referral: +1 spendable ref_point
        add_ref_points(referrer_id, REFERRAL_POINTS)
        log_referral_attempt(referrer_id, new_user.id, "counted", "ok")
        try:
            direct_total = get_direct_referral_count(referrer_id)
        except Exception:
            direct_total = get_referral_count(referrer_id)
        await _send_direct_referral_notifications(
            context, referrer_id, new_user, REFERRAL_POINTS, direct_total)

    # Broadcast (existing fake-activity destination)
    try:
        from per_user_activity import (
            is_globally_enabled, _random_name, _mask_name
        )
        from database import get_all_users_for_broadcast
        from customization import render_template
        if is_globally_enabled():
            ref_count = get_referral_count(referrer_id)
            more = max(1, 10 - (ref_count % 10))
            rname = _mask_name(_random_name())
            real_msg = render_template("bc_active_referral", {
                "user": rname, "referrals": str(ref_count), "more": str(more),
            })
            for usr in get_all_users_for_broadcast():
                try:
                    uid_b = usr["user_id"] if isinstance(usr, dict) else usr[0]
                    await context.bot.send_message(uid_b, real_msg, parse_mode="Markdown")
                except Exception:
                    pass
    except Exception:
        pass

    return True


async def approve_pending_referral_for_user(context, user_id, reason='activity'):
    """Approve one pending referral after Shop open or 30s active fallback."""
    try:
        from database import get_pending_referral_for_user, get_user, mark_pending_referral_done
        row = get_pending_referral_for_user(int(user_id))
        if not row:
            return False
        urow = get_user(int(user_id))
        if not urow:
            return False
        class _User:
            pass
        u = _User()
        u.id = int(user_id)
        u.first_name = urow['first_name'] if 'first_name' in urow.keys() else ''
        u.username = urow['username'] if 'username' in urow.keys() else ''
        u.is_bot = False
        ok = await _process_referral_attribution(
            context, u, int(row['referrer_id']), False,
            product_id=int(row['product_id'] or 0), approve_now=True)
        if not ok:
            mark_pending_referral_done(int(user_id), 'blocked', f'approval_failed_{reason}')
        return bool(ok)
    except Exception as e:
        logging.getLogger(__name__).debug(f"[pending-ref] approve failed: {e}")
        return False


async def _pending_referral_job(context):
    try:
        uid = int((context.job.data or {}).get('uid') or 0)
    except Exception:
        uid = 0
    if uid:
        await approve_pending_referral_for_user(context, uid, reason='30s_active')


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _panic_reset_user_session(update, context)
    u = update.effective_user
    # 🔗 Force Join check — must be FIRST before any other logic
    try:
        from ui_extras import check_force_join
        if not await check_force_join(update, context):
            return  # User not in channel/group — join message sent, stop here
    except Exception:
        pass  # If force join system errors, don't block user

    # 📡 Track: is this a new user?
    is_new = get_user(u.id) is None
    save_user(u.id, u.username or "", u.first_name or "")
    if is_new and u.id != ADMIN_ID:
        await notify_admin(context.bot,
            f"👤 *New User Joined!*\n"
            f"Name: {escape_md(u.first_name or 'N/A')}\n"
            f"Username: @{escape_md(u.username or 'N/A')}\n"
            f"ID: `{u.id}`")
        # 📢 Broadcast new user join to all existing users (if enabled)
        try:
            from fake_engagement import broadcast_new_user_join
            await broadcast_new_user_join(context.bot, u.first_name or "Someone")
        except Exception:
            pass

    # 🎭 Start per-user lifetime fake activity (for ALL users incl admin)
    # This is safe to call every /start — won't double-schedule
    if u.id != ADMIN_ID:
        try:
            from per_user_activity import start_personal_activity
            await start_personal_activity(context.bot, context.application, u.id)
        except Exception:
            pass
            
    # ──────────────────────────────────────────────────────────────
    # 🆕 v48: Unified deep-link parser
    #   buy_<pid>            → open product detail (existing)
    #   ref_<rid>_<pid>      → referral + open product detail
    #   <rid>                → legacy plain referral
    # ──────────────────────────────────────────────────────────────
    arg = context.args[0] if context.args else ""
    rid = 0
    open_pid = 0
    if arg:
        try:
            if arg.startswith("ref_"):
                rest = arg[4:]
                if "_" in rest:
                    rid_s, pid_s = rest.split("_", 1)
                    rid = int(rid_s); open_pid = int(pid_s)
                else:
                    rid = int(rest)
            elif arg.startswith("buy_"):
                open_pid = int(arg[4:])
            else:
                rid = int(arg)
        except Exception:
            rid, open_pid = 0, 0

    # ─── Referral attribution (instant, anti-fake but no delay) ───
    # 🆕 v102: pass open_pid → if the link was ref_<uid>_<pid> (product-specific
    # share link), route into the per-product referral pool (no ref_point
    # reward, counts toward that product's requirement only).
    if rid and rid != u.id:
        try:
            await _process_referral_attribution(context, u, rid, is_new,
                                                 product_id=open_pid)
        except Exception as _e:
            import logging
            logging.getLogger(__name__).error(f"[referral] {_e}")

    # ─── Deep-link to product detail ───
    if open_pid:
        try:
            from handlers_shop import show_product_detail_direct
            await show_product_detail_direct(context.bot, u.id, open_pid)
            return  # Stop here, we showed them the product
        except Exception:
            pass

    shop = get_setting("shop_name", SHOP_NAME)
    text = _r("welcome", user_id=u.id).format(shop_name=shop, user_id=u.id)
    # v133: Pinned announcements are real pinned messages only; do not prepend them to welcome.
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    await update.message.reply_text("👋", reply_markup=persistent_menu())
    await update.message.reply_text(send_text, parse_mode=send_mode,
        reply_markup=main_menu_keyboard(u.id == ADMIN_ID, user_id=u.id))

async def handle_how_to_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🆕 v78: Handler for the 📚 How to Use button on the persistent reply
    keyboard. Opens the same guide hub that the inline button would open,
    but via reply_text (since the trigger is a text message, not callback).
    """
    from ui_extras import how_to_hub_from_text
    await how_to_hub_from_text(update, context)


async def handle_main_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🔧 BUG #8 FIX: Show welcome (persistent keyboard already attached on /start)
    Inline keyboard goes in the welcome message itself.

    🆕 v81.1 PANIC RESET: The persistent-keyboard 🏠 Main Menu button is a
    UNIVERSAL exit — closes ALL active conversations + wipes ALL session
    state before showing the menu. So no matter what step the user is stuck
    in (mid-payment / mid-form / mid-supplier-wizard), tapping 🏠 gives
    them a clean fresh main menu.
    """
    u = update.effective_user; save_user(u.id, u.username or "", u.first_name or "")
    await _panic_reset_user_session(update, context)

    shop = get_setting("shop_name", SHOP_NAME)
    text = _r("welcome", user_id=u.id).format(shop_name=shop, user_id=u.id)
    # v133: Pinned announcements are real pinned messages only; do not prepend them to welcome.
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    await update.message.reply_text(send_text, parse_mode=send_mode,
        reply_markup=main_menu_keyboard(u.id == ADMIN_ID, user_id=u.id))

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); u = q.from_user
    nav_push(context, 'main_menu')  # 🔙 Track navigation
    shop = get_setting("shop_name", SHOP_NAME)
    text = _r("welcome", user_id=u.id).format(shop_name=shop, user_id=u.id)
    # v133: Pinned announcements are real pinned messages only; do not prepend them to welcome.
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=main_menu_keyboard(u.id == ADMIN_ID, user_id=u.id))

async def my_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); u = q.from_user; db = get_user(u.id)
    nav_push(context, 'my_account')  # 🔙 Track navigation
    from database import get_ref_points  # 🆕 v48
    # 🔧 FIXED: escape markdown + format date nicely
    # 🆕 v48: extra placeholders {ref_points} {ref_points_label} for admin to use
    fmt_dict = dict(
        name=escape_md(u.first_name or 'N/A'),
        user_id=u.id,
        username=escape_md(u.username or 'N/A'),
        points=get_user_points(u.id),
        referrals=get_referral_count(u.id),
        ref_points=get_ref_points(u.id),
        joined=format_date(db['joined_at'] if db else None)
    )
    tpl = _r("my_account", user_id=u.id)
    try:
        text = tpl.format(**fmt_dict)
    except KeyError:
        # Admin's custom my_account text may not include all placeholders
        try:
            text = tpl.format_map(_SafeDict(**fmt_dict))
        except Exception:
            text = tpl
    # If admin hasn't included {ref_points} placeholder, append a one-line balance hint
    if "{ref_points}" not in tpl and "Referral Points" not in tpl:
        text += f"\n🎁 Referral Points: *{get_ref_points(u.id)}*"
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=back_btn(location="my_account"))


async def referral_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); u = q.from_user
    nav_push(context, 'referral')  # 🔙 Track navigation
    from database import get_ref_points  # 🆕 v48
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={u.id}"
    rp = get_ref_points(u.id)
    rc = get_referral_count(u.id)
    fmt_dict = dict(
        ref_link=link, ref_count=rc,
        ref_points=rp, points_per_ref=REFERRAL_POINTS,
    )
    tpl = _r("referral_text")
    try:
        text = tpl.format(**fmt_dict)
    except KeyError:
        text = tpl.format_map(_SafeDict(**fmt_dict))
    rules = (
        "\n\n📌 *How your referral counts:*\n"
        "1️⃣ Friend must open your link and press */start*.\n"
        "2️⃣ If Force Join is enabled, they must join/verify required channel or group.\n"
        "3️⃣ Referral reward is approved when they open *Shop* or stay active for about 30 seconds.\n"
        "4️⃣ Self-referrals, duplicate users, or suspicious activity are blocked.\n\n"
        "🎁 *Rewards:* +1 referral point per approved direct referral. Every 20 direct referrals = +10 wallet points bonus."
    )
    text += rules
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=back_btn(location="referral"))


class _SafeDict(dict):
    """Used with str.format_map — missing keys leave the placeholder untouched
    instead of raising KeyError. Lets admin custom templates be tolerant."""
    def __missing__(self, key):
        return "{" + key + "}"

async def buy_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    nav_push(context, 'buy_points')  # 🔙 Track navigation
    pts = get_user_points(q.from_user.id)
    # 🔧 v39 Bug #9: Append custom buttons for buy_points screen
    base_kb = buy_points_keyboard()
    rows = list(base_kb.inline_keyboard)
    try:
        from keyboards import _custom_buttons_for
        for r in _custom_buttons_for("buy_points"):
            rows.insert(-1, r)  # insert before last row (which is usually the back/cancel)
    except Exception:
        pass
    from telegram import InlineKeyboardMarkup as _IKM
    await _safe_edit(q,
        f"💎 *Buy Points*\n━━━━━━━━━━━━━━━━━━━━\n\n💎 Your Points: *{pts}*\n💰 Rate: $1 = {POINTS_PER_DOLLAR} Points\n\nSelect payment method:",
        parse_mode="Markdown", reply_markup=_IKM(rows))

async def transactions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nav_push(context, 'transactions')  # 🔙 Track navigation
    """🔄 Transaction History — Deposits only with date/time + status"""
    q = update.callback_query; await q.answer()
    txns = get_user_transactions(q.from_user.id)
    if not txns:
        await _safe_edit(q, "🔄 *No deposits yet!*\n\nUse 💎 Buy Points to deposit funds.",
                        parse_mode="Markdown", reply_markup=back_btn(location="transactions"))
        return

    from datetime import datetime
    text = "🔄 *Transaction History*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    # Status → emoji + label
    status_map = {
        'pending':         ('🟡', 'Pending'),
        'screenshot_sent': ('⏳', 'Processing'),
        'binance_waiting': ('⏳', 'Processing'),
        'delivered':       ('✅', 'Paid'),
        'cancelled':       ('❌', 'Canceled'),
        'rejected':        ('❌', 'Canceled'),
    }
    for t in txns[:15]:
        emoji, label = status_map.get(t['status'], ('❓', t['status'].title()))
        # Parse date/time
        try:
            dt = datetime.strptime(str(t['created_at'])[:19], "%Y-%m-%d %H:%M:%S")
            dt_str = dt.strftime("%d %b %Y  %I:%M %p")
        except Exception:
            dt_str = str(t['created_at'])[:16]
        # Method emoji
        m = (t['payment_method'] or '').lower()
        if 'binance' in m: method = "🔶 Binance"
        elif 'easy' in m:  method = "📱 EasyPaisa"
        elif 'jazz' in m:  method = "📱 JazzCash"
        else:              method = "💳 Manual"
        # Build entry
        pname = t['product_name'][:35] + "…" if len(t['product_name']) > 35 else t['product_name']
        # 🆕 v24: Show TXID if Binance
        txid_line = ""
        try:
            txid = t['binance_txid'] or ''
        except (IndexError, KeyError):
            txid = ''
        if txid:
            txid_line = f"\n🆔 TXID: `{escape_md(txid[:25])}...`"
        text += (f"{emoji} *{label}* — #{t['id']}\n"
                 f"💎 {escape_md(pname)}\n"
                 f"💰 {fmt_price(t['price'])}  |  {method}{txid_line}\n"
                 f"📅 {dt_str}\n"
                 f"━━━━━━━━━━━━━━━━━━━━\n")
    if len(txns) > 15:
        text += f"\n_+{len(txns)-15} more older deposits_"
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=back_btn(location="transactions"))

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: await update.message.reply_text("❌"); return
    await update.message.reply_text("*Admin Menu Panel:*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌", show_alert=True); return
    await q.answer()
    await _safe_edit(q, "*Admin Menu Panel:*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())


# ════════════════════════════════════════════
# 🔙 UNIVERSAL BACK BUTTON (Navigation Stack)
# ════════════════════════════════════════════

async def go_back_callback(update, context):
    """🔙 Universal back — goes to previous screen from navigation stack.
    Each callback pushes its ID before navigating to a new screen.
    """
    q = update.callback_query
    await q.answer()
    target = nav_pop(context)

    # Map targets to handler functions
    target_map = {
        'main_menu': main_menu_callback,
        'shop': _shop_handler,
        'my_account': my_account_callback,
        'buy_points': buy_points_callback,
        'transactions': transactions_callback,
        'referral': referral_callback,
        'my_orders': _my_orders_handler,
        'admin_panel': _admin_panel_handler,
        # 🆕 v73: 'admin_orders' (Pending Orders) REMOVED. Use 'admin_completed' instead.
        'admin_completed': _admin_completed_handler,
        'admin_deposits': _admin_deposits_handler,
        # 🔧 v39 Bug #5: Missing screens added
        'support_menu':  _support_menu_handler,
        'warranty_menu': _warranty_menu_handler,
        'reviews_menu':  _reviews_menu_handler,
        'loyalty_menu':  _loyalty_menu_handler,
        'language_menu': _language_menu_handler,
        'adm_tickets':   _adm_tickets_handler,
        'adm_warranty':  _adm_warranty_handler,
    }

    handler = target_map.get(target)
    if handler:
        try:
            await handler(update, context)
        except Exception:
            await main_menu_callback(update, context)
    else:
        # Fallback to main menu
        await main_menu_callback(update, context)


# ── Wrapper handlers for go_back redirects ──
async def _shop_handler(update, context):
    """Redirect to shop"""
    from handlers_shop import shop_callback
    set_cb_data(update, "shop")
    await shop_callback(update, context)

async def _my_orders_handler(update, context):
    """Redirect to my orders"""
    from handlers_order import my_orders_callback
    set_cb_data(update, "my_orders")
    await my_orders_callback(update, context)

async def _admin_panel_handler(update, context):
    """Redirect to admin panel"""
    set_cb_data(update, "admin_panel")
    await admin_panel_callback(update, context)

async def _admin_completed_handler(update, context):
    """🆕 v73: Redirect to admin completed orders panel"""
    from admin_panels import admin_completed_orders_callback
    set_cb_data(update, "admin_completed")
    await admin_completed_orders_callback(update, context)

async def _admin_deposits_handler(update, context):
    """Redirect to admin deposits"""
    from handlers_admin import admin_deposit_history_callback
    set_cb_data(update, "admin_deposits")
    await admin_deposit_history_callback(update, context)


# 🔧 v39 Bug #5: Wrappers for go_back to new screens
async def _support_menu_handler(update, context):
    from handlers_support import support_menu_callback
    set_cb_data(update, "support_menu")
    await support_menu_callback(update, context)

async def _warranty_menu_handler(update, context):
    from handlers_support import warranty_menu_callback
    set_cb_data(update, "warranty_menu")
    await warranty_menu_callback(update, context)

async def _reviews_menu_handler(update, context):
    from handlers_reviews import reviews_menu_callback
    set_cb_data(update, "reviews_menu")
    await reviews_menu_callback(update, context)

async def _loyalty_menu_handler(update, context):
    from loyalty_extras import loyalty_callback
    set_cb_data(update, "loyalty_menu")
    await loyalty_callback(update, context)

async def _language_menu_handler(update, context):
    from ui_extras import language_menu_callback
    set_cb_data(update, "language_menu")
    await language_menu_callback(update, context)

async def _adm_tickets_handler(update, context):
    from handlers_support import adm_tickets_callback
    set_cb_data(update, "adm_tickets")
    await adm_tickets_callback(update, context)

async def _adm_warranty_handler(update, context):
    from handlers_support import adm_warranty_callback
    set_cb_data(update, "adm_warranty")
    await adm_warranty_callback(update, context)
