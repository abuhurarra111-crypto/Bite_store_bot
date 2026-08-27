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

# 🆕 v161.20: milestone bonus is now admin-configurable via the Referral Abuse
# panel ("🎯 Milestone Bonus"). Stored as a compact string in bot_settings:
#   ref_bonus_tiers = "20:10, 50:30, 100:80"   (refs:bonus pairs)
# Legacy single-pair settings (ref_milestone_every / ref_milestone_bonus) are
# used as the fallback so existing installs keep working.
REFERRAL_MILESTONE_EVERY = 20
REFERRAL_MILESTONE_BONUS_POINTS = 10


def _ref_bonus_tiers():
    """Return sorted list of (refs, bonus_points) milestone tiers.

    e.g. [(20, 10), (50, 30)] means: 20 direct referrals → +10 wallet points,
    50 direct referrals → +30 wallet points. Falls back to the legacy single
    milestone (every 20 → +10) when nothing is configured.
    """
    tiers = []
    try:
        from database import get_setting as _gs
        raw = str(_gs("ref_bonus_tiers", "") or "").strip()
        if raw:
            for part in raw.split(","):
                part = part.strip()
                if ":" not in part:
                    continue
                r_s, b_s = part.split(":", 1)
                r = int(float(r_s.strip()))
                b = float(b_s.strip())
                if r > 0 and b > 0:
                    tiers.append((r, b))
            tiers.sort(key=lambda t: t[0])
            # dedupe same refs
            uniq = []
            for t in tiers:
                if not uniq or uniq[-1][0] != t[0]:
                    uniq.append(t)
                else:
                    uniq[-1] = t
            if uniq:
                return uniq
        # legacy fallback
        every = int(float(_gs("ref_milestone_every", "20") or 20))
        bonus = float(_gs("ref_milestone_bonus", "10") or 10)
        if every > 0 and bonus > 0:
            return [(every, bonus)]
    except Exception:
        pass
    return [(REFERRAL_MILESTONE_EVERY, REFERRAL_MILESTONE_BONUS_POINTS)]


def _ref_bonus_tiers_text():
    """Human-readable summary like '20 refs → +10 pts, 50 refs → +30 pts'."""
    parts = []
    for r, b in _ref_bonus_tiers():
        b_txt = str(int(b)) if float(b).is_integer() else f"{b:g}"
        parts.append(f"{r} refs → +{b_txt} pts")
    return ", ".join(parts) if parts else "—"

_DEFAULT_REFERRER_REFERRAL_TEMPLATE = """🎉 *New Referral Joined!*\n━━━━━━━━━━━━━━━━━━━━\n\n👤 Referred user: *{referred_name}*\n🆔 Referred ID: `{referred_id}`\n\n✅ Reward: *+{reward_points} referral point*\n📊 Your direct referrals: *{total_referrals}*\n🎯 Next bonus: *{remaining_to_bonus}* more referrals → *+{milestone_bonus} wallet points* ($1)\n\nKeep sharing your link and earning rewards! 🚀"""

_DEFAULT_ADMIN_REFERRAL_TEMPLATE = """🎁 *New Direct Referral*\n━━━━━━━━━━━━━━━━━━━━\n\n👑 Referrer:\n• Name: *{referrer_name}*\n• Username: @{referrer_username}\n• ID: `{referrer_id}`\n\n🆕 Referred User:\n• Name: *{referred_name}*\n• Username: @{referred_username}\n• ID: `{referred_id}`\n\n🎯 Reward: +{reward_points} referral point\n📊 Referrer's direct referrals: {total_referrals}"""

# 🆕 v134: notification sent to the REFERRED user when their referral is
# approved (after the bot observed their activity). Both users earn the
# same admin-set points per direct referral.
_DEFAULT_REFERRED_REWARD_TEMPLATE = """🎁 *Referral Reward Credited!*
━━━━━━━━━━━━━━━━━━━━

✅ You came from a friend's referral link and your activity was verified.

💎 *+{reward_points} point(s)* added to your Referral Points balance!

🆔 Your User ID: `{referred_id}`
👤 Referred by: *{referrer_name}*

You can spend Referral Points on free products or keep earning by sharing your own link. 🚀"""

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


async def _send_referral_message(bot, chat_id, text, *, effect_event="", **kwargs):
    """Send a referral notification, optionally with its own event effect."""
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    try:
        if effect_event:
            from message_effects import send_event_message
            return await send_event_message(
                bot, effect_event, chat_id, send_text, parse_mode=send_mode, **kwargs)
        return await bot.send_message(chat_id, send_text, parse_mode=send_mode, **kwargs)
    except Exception:
        kwargs.pop('reply_markup', None)
        try:
            if effect_event:
                from message_effects import send_event_message
                return await send_event_message(bot, effect_event, chat_id, send_text, parse_mode=send_mode)
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
    # 🆕 v161.20: milestone targets come from admin-configurable tiers.
    tiers = _ref_bonus_tiers()
    direct_count_i = int(direct_count)
    next_tier = next((t for t in tiers if t[0] > direct_count_i), None)
    if next_tier:
        remaining = next_tier[0] - direct_count_i
        next_milestone = int(next_tier[0])
        next_bonus = next_tier[1]
    else:
        remaining = 0
        next_milestone = int(tiers[-1][0])
        next_bonus = tiers[-1][1]
    values = {
        'referrer_id': ref['id'], 'referrer_name': ref['name'], 'referrer_username': ref['username'],
        'referred_id': new['id'], 'referred_name': new['name'], 'referred_username': new['username'],
        'reward_points': fmt_points(reward_points),
        'total_referrals': direct_count_i,
        'remaining_to_bonus': int(remaining),
        'milestone_bonus': fmt_points(next_bonus),
        'milestone_number': direct_count_i,
        'next_milestone': int(next_milestone),
    }
    # Referrer notification
    try:
        await _send_referral_message(
            context.bot, referrer_id,
            _render_referral_template('ref_tpl_referrer', _DEFAULT_REFERRER_REFERRAL_TEMPLATE, values),
            effect_event="referral_reward")
    except Exception:
        pass
    # 🆕 v134: REFERRED USER also gets points + a notification (both earn the
    # same admin-set per-ref reward, only after activity verification).
    try:
        await _send_referral_message(
            context.bot, int(new['id']),
            _render_referral_template('ref_tpl_referred', _DEFAULT_REFERRED_REWARD_TEMPLATE, values),
            effect_event="referral_reward")
    except Exception:
        pass
    # Admin notification
    try:
        await notify_admin(context.bot,
            _render_referral_template('ref_tpl_admin', _DEFAULT_ADMIN_REFERRAL_TEMPLATE, values))
    except Exception:
        pass
    # 🆕 v161.20: milestone bonus — pay EVERY admin-configured tier the user has
    # crossed since the last payment (e.g. tiers 20→10, 50→30: reaching 50 pays
    # the 20-tier bonus if never paid, plus the 50-tier bonus). Paid once per
    # tier via the ref_milestone_paid_<uid> watermark.
    try:
        if direct_count_i > 0:
            key = f"ref_milestone_paid_{int(referrer_id)}"
            last_paid = int(get_setting(key, '0') or 0)
            earned = [(r, b) for r, b in tiers if r <= direct_count_i and r > last_paid]
            if earned:
                highest = earned[-1]
                total_bonus = float(sum(b for _, b in earned))
                add_points(referrer_id, total_bonus, tx_type='referral_milestone',
                           description=f'{highest[0]} referral milestone',
                           event_id=f"ref_milestone_{int(referrer_id)}_{int(direct_count_i)}")
                set_setting(key, str(highest[0]))
                values['milestone_number'] = highest[0]
                values['milestone_bonus'] = fmt_points(total_bonus)
                # next milestone after this payment
                nxt = next((t for t in tiers if t[0] > highest[0]), None)
                values['next_milestone'] = int(nxt[0]) if nxt else int(highest[0])
                await _send_referral_message(
                    context.bot, referrer_id,
                    _render_referral_template('ref_tpl_milestone', _DEFAULT_MILESTONE_TEMPLATE, values),
                    effect_event="referral_reward")
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
                effect_event="referral_reward", reply_markup=kb)
        else:
            await _send_referral_message(
                context.bot, referrer_id,
                _render_referral_template('ref_tpl_product_referrer', _DEFAULT_PRODUCT_REFERRER_TEMPLATE, values),
                effect_event="referral_reward")
    except Exception:
        pass
    try:
        await notify_admin(context.bot,
            _render_referral_template('ref_tpl_product_admin', _DEFAULT_PRODUCT_ADMIN_TEMPLATE, values))
    except Exception:
        pass


async def _process_referral_attribution(context, new_user, referrer_id, is_new_user,
                                        product_id=0, approve_now=True):
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
        get_ref_points_per_ref,
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
            # 🆕 v170.9: math verification ON ho to fast-approve job MAT schedule
            # karo — math ka sahi jawab hi referral count karega (wrong/abandon
            # par count nahi hota). Math OFF ho to 5s fallback se stuck nahi hota.
            try:
                if not _referral_math_enabled():
                    if getattr(context, 'job_queue', None):
                        context.job_queue.run_once(_pending_referral_job, 5, data={'uid': int(new_user.id)}, name=f'pending_ref_{int(new_user.id)}')
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
        # General direct referral: award configurable points (default 1).
        # 🔧 v133: per-ref reward is admin-configurable (can be 0.1 / 2 / 5...).
        # 🆕 v134: BOTH the referrer AND the referred user earn the same
        # admin-set points (only after the bot verified real-human activity).
        reward = get_ref_points_per_ref()
        add_ref_points(referrer_id, reward)
        if int(getattr(new_user, 'id', 0)) and int(new_user.id) != int(referrer_id):
            try:
                add_ref_points(new_user.id, reward)
            except Exception:
                pass
        log_referral_attempt(referrer_id, new_user.id, "counted", "ok")
        try:
            direct_total = get_direct_referral_count(referrer_id)
        except Exception:
            direct_total = get_referral_count(referrer_id)
        await _send_direct_referral_notifications(
            context, referrer_id, new_user, reward, direct_total)

    # 🆕 v168.1: Referral broadcast → ONLY to fake activity destination (not user inbox)
    # Routes through broadcast_store_message() which respects dest_mode config
    # (group_only/bot_only/both) so referral activity only shows where admin wants it.
    try:
        from per_user_activity import (
            is_globally_enabled, _random_name, _mask_name
        )
        from customization import render_template
        if is_globally_enabled():
            ref_count = get_referral_count(referrer_id)
            more = max(1, 10 - (ref_count % 10))
            rname = _mask_name(_random_name())
            real_msg = render_template("bc_active_referral", {
                "user": rname, "referrals": str(ref_count), "more": str(more),
            })
            _bot = context.bot
            import asyncio
            async def _bg_referral_broadcast():
                try:
                    from fake_engagement import broadcast_store_message
                    await broadcast_store_message(_bot, real_msg, bypass_maintenance=True)
                except Exception:
                    pass
            asyncio.create_task(_bg_referral_broadcast())
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
    """🆕 v134 → v161.16: referral approval is now IMMEDIATE (approve_now=True
    default). This job is only a tiny safety net for legacy approve_now=False
    callers: approves after ONE fast round (5s), no observation lock, so a
    burst of referrals can never stall the bot."""
    try:
        uid = int((context.job.data or {}).get('uid') or 0)
    except Exception:
        uid = 0
    if not uid:
        return
    try:
        from database import get_pending_referral_for_user
        row = get_pending_referral_for_user(uid)
        if not row:
            return
        # Approve on first round — no multi-round observation.
        await approve_pending_referral_for_user(context, uid, reason='fast_approval')
    except Exception as e:
        logging.getLogger(__name__).debug(f"[pending-ref] fast job: {e}")


# ════════════════════════════════════════════════════════════════
# 🧮 v134 — REFERRAL MATH VERIFICATION + ACTIVITY OBSERVATION
# ════════════════════════════════════════════════════════════════
# Flow (per user request):
#   1. User arrives via a REFERRAL link → /start
#   2. Force-join (if enabled) → joins → taps "I Joined — Verify"
#   3. MATH QUESTION appears (random + or −, never repeated instantly)
#   4. Correct answer → bot starts. (Normal users never see math.)
#   5. Bot observes the referred user ~30s. Only a REAL human (taps/typing)
#      unlocks the reward — then BOTH the referrer AND the referred user
#      get the admin-set points, with notifications to each.
# ════════════════════════════════════════════════════════════════

def _parse_start_arg(arg):
    """Parse deep-link payload → (referrer_id, open_pid, checkout_pid, open_freebies).
    🐛 v147 FIX (Bug7): `chk_<pid>` deep link opens the product's CHECKOUT
    (payment-method screen) directly instead of the product detail page.
    🆕 v170.43: `freebies` → open freebies menu."""
    rid, open_pid, chk_pid, open_freebies = 0, 0, 0, False
    try:
        if not arg:
            return 0, 0, 0, False
        if arg.startswith("ref_"):
            rest = arg[4:]
            if "_" in rest:
                rid_s, pid_s = rest.split("_", 1)
                rid = int(rid_s); open_pid = int(pid_s)
            else:
                rid = int(rest)
        elif arg.startswith("chk_"):
            chk_pid = int(arg[4:])
        elif arg.startswith("buy_"):
            open_pid = int(arg[4:])
        elif arg == "freebies":
            open_freebies = True
        else:
            rid = int(arg)
    except Exception:
        rid, open_pid, chk_pid, open_freebies = 0, 0, 0, False
    return rid, open_pid, chk_pid, open_freebies


def _referral_math_enabled():
    try:
        from database import get_referral_math_enabled
        return get_referral_math_enabled()
    except Exception:
        return True


def _new_math_question():
    """Random addition/subtraction (result always >= 0)."""
    import random
    if random.random() < 0.5:
        a = random.randint(2, 50); b = random.randint(2, 50)
        op, ans = "+", a + b
    else:
        a = random.randint(12, 80); b = random.randint(1, min(11, a - 1))
        op, ans = "-", a - b
    return a, op, b, ans


async def _ask_math_question(reply_to, context, user_id, first_name=""):
    """Send the math verification question to a referral-origin user.
    Returns True if asked (caller should stop and wait for the answer)."""
    try:
        if not _referral_math_enabled():
            return False
    except Exception:
        return False
    a, op, b, ans = _new_math_question()
    context.user_data['fj_math'] = {'answer': ans, 'tries': 0,
                                    'a': a, 'op': op, 'b': b}
    name = escape_md(first_name or "Friend")
    text = (
        f"🧮 *Human Verification* 🔐\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Hi {name}! Since you joined through a referral link, "
        f"please solve this quick math check to start the bot:\n\n"
        f"🔢 *{a} {op} {b} = ?*\n\n"
        f"Type the *number* below (e.g. `17`)."
    )
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    try:
        await reply_to.reply_text(send_text, parse_mode=send_mode)
        return True
    except Exception:
        try:
            await reply_to.reply_text(f"🧮 Human Verification\n\n{a} {op} {b} = ?\n\nType the number:")
            return True
        except Exception:
            context.user_data.pop('fj_math', None)
            return False


async def handle_math_answer(update, context):
    """Consumed from the main text handler. Returns True when the message
    was a math answer (even wrong ones) so no other flow touches it."""
    state = context.user_data.get('fj_math')
    if not state:
        return False
    uid = update.effective_user.id
    txt = (update.message.text or '').strip()
    try:
        val = int(txt)
    except Exception:
        val = None
    if val is None:
        await update.message.reply_text("❌ Please type the answer as a number, e.g. `17`.")
        return True
    if val == int(state.get('answer')):
        context.user_data.pop('fj_math', None)
        # Math passed → real human → approve the pending referral now.
        try:
            from database import get_pending_referral_for_user
            if get_pending_referral_for_user(uid):
                await approve_pending_referral_for_user(context, uid, reason='math_verified')
        except Exception:
            pass
        await _complete_start_after_math(update, context)
        return True
    # Wrong answer → retry (3 wrongs → fresh question)
    tries = int(state.get('tries', 0)) + 1
    if tries >= 3:
        a2, op2, b2, ans2 = _new_math_question()
        context.user_data['fj_math'] = {'answer': ans2, 'tries': 0,
                                        'a': a2, 'op': op2, 'b': b2}
        await update.message.reply_text(
            f"❌ Wrong answer. New question:\n\n🔢 *{a2} {op2} {b2} = ?*\n\nType the number:",
            parse_mode="Markdown")
    else:
        state['tries'] = tries
        await update.message.reply_text(
            f"❌ Wrong. Try again — attempt *{tries}/3*:\n\n"
            f"🔢 *{state.get('a')} {state.get('op')} {state.get('b')} = ?*",
            parse_mode="Markdown")
    return True


async def _send_welcome_message(reply_to, context, u):
    """🆕 v138: shared welcome renderer (fixed default-language welcome).
    🆕 v139.4: auto-reacts to the welcome message when the admin set a
    reaction for 'welcome' and the global reaction toggle is ON."""
    from database import get_setting
    from keyboards import main_menu_keyboard, persistent_menu
    from config import ADMIN_ID, SHOP_NAME
    shop = get_setting("shop_name", SHOP_NAME)
    # 🆕 v137: WELCOME stays default-language (never switches) per admin request.
    text = _r("welcome").format(shop_name=shop, user_id=u.id)
    # 🆕 v144: Home Banner — admin-set banner line above the welcome text.
    try:
        from database import get_setting as _g4
        if _g4("home_banner_enabled", "0") == "1":
            _bn = (_g4("home_banner_text", "") or "").strip()
            if _bn:
                _bn = _bn.replace("{shop_name}", str(shop))
                from utils import smart_text_and_mode as _stm
                _bt, _bm = _stm(_bn, "Markdown")
                text = f"{_bt}\n\n{text}"
    except Exception:
        pass
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    # 🐛 v170.52 FIX: wave "👋" NAHI, Freebies inline NAHI.
    #  • NAYA user → persistent quick-bar (🏠 Menu/🎁 Freebies/...) WELCOME
    #    message par hi attach (bar isi se set hoti hai — koi extra message nahi).
    #  • PURANA user (bar pehle se cached) → inline main menu.
    try:
        _new_here = bool(context.user_data.pop('_is_new_user', False)) if context is not None else False
    except Exception:
        _new_here = False
    if _new_here:
        await reply_to.reply_text(send_text, parse_mode=send_mode,
            reply_markup=persistent_menu(u.id))
    else:
        await reply_to.reply_text(send_text, parse_mode=send_mode,
            reply_markup=main_menu_keyboard(u.id == ADMIN_ID, user_id=u.id))


async def _complete_start_after_math(update, context):
    """After math passes → open product (if deep link) or send welcome."""
    u = update.effective_user
    open_pid = context.user_data.pop('_start_pid', 0) or 0
    chk_pid = context.user_data.pop('_start_checkout_pid', 0) or 0
    context.user_data.pop('_start_ref', None)
    # 🐛 v147 FIX (Bug7): checkout deep link wins over product detail
    if chk_pid:
        try:
            from handlers_order import open_checkout_direct
            if await open_checkout_direct(context.bot, u.id, chk_pid):
                return
        except Exception:
            pass
    if open_pid:
        try:
            from handlers_shop import show_product_detail_direct
            await show_product_detail_direct(context.bot, u.id, open_pid)
            return
        except Exception:
            pass
    await _send_welcome_message(update.message, context, u)


async def notify_user_activity(context, user_id):
    """🆕 v134: called on ANY user action (button tap / text). Counts it as
    observed activity; after 2+ real actions the pending referral is approved
    immediately (strong real-human signal). Mid-math users are skipped so a
    wrong math answer never unlocks the reward."""
    try:
        if not user_id or int(user_id) == int(ADMIN_ID):
            return
        if context.user_data.get('fj_math'):
            return
        from database import (get_pending_referral_for_user,
                              bump_pending_referral_activity)
        row = get_pending_referral_for_user(int(user_id))
        if not row:
            return
        count = bump_pending_referral_activity(int(user_id))
        if count >= 2:
            await approve_pending_referral_for_user(context, int(user_id), reason='active_human')
    except Exception:
        pass


async def continue_after_force_join_verified(update, context, u):
    """🆕 v134: called from the 'I Joined — Verify' callback (ui_extras).
    Runs the referral attribution + math gate that /start would have run,
    because /start stopped early at the force-join wall. Returns True if
    the flow was fully handled here (welcome/math/product shown)."""
    rid = context.user_data.pop('_start_ref', 0) or 0
    open_pid = context.user_data.pop('_start_pid', 0) or 0
    chk_pid = context.user_data.pop('_start_checkout_pid', 0) or 0
    try:
        from database import get_user
        is_new = get_user(u.id) is None
        from database import save_user
        save_user(u.id, u.username or "", u.first_name or "")
    except Exception:
        is_new = False
    # 🐛 v170.52: is_new welcome renderer ke liye stash karo (persistent bar vs inline)
    try:
        context.user_data['_is_new_user'] = bool(is_new)
    except Exception:
        pass
    if rid and int(rid) != int(u.id):
        # 🆕 v170.9: math verification PEHLE, count BAAD
        _math_on = _referral_math_enabled()
        try:
            await _process_referral_attribution(context, u, int(rid), is_new,
                                                 product_id=int(open_pid or 0),
                                                 approve_now=(not _math_on))
        except Exception:
            pass
        # Math gate (referral users only)
        if _math_on:
            asked = False
            try:
                asked = await _ask_math_question(update.effective_message, context,
                                                 u.id, u.first_name)
                if asked:
                    # re-stash the product deep-link so it opens AFTER math passes
                    if open_pid:
                        context.user_data['_start_pid'] = int(open_pid)
                    return True
            except Exception:
                asked = False
            if not asked:
                try:
                    await approve_pending_referral_for_user(context, u.id, reason='math_ask_failed')
                except Exception:
                    pass
        # Math done / disabled → finish the start (product or welcome)
        # 🐛 v147 FIX (Bug7): checkout deep link wins
        if chk_pid:
            try:
                from handlers_order import open_checkout_direct
                if await open_checkout_direct(context.bot, u.id, chk_pid):
                    return True
            except Exception:
                pass
        if open_pid:
            try:
                from handlers_shop import show_product_detail_direct
                await show_product_detail_direct(context.bot, u.id, open_pid)
                return True
            except Exception:
                pass
        await _send_welcome_message(update.effective_message, context, u)
        return True
    # No referral → normal welcome (or product deep-link)
    # 🐛 v147 FIX (Bug7): checkout deep link wins
    if chk_pid:
        try:
            from handlers_order import open_checkout_direct
            if await open_checkout_direct(context.bot, u.id, chk_pid):
                return True
        except Exception:
            pass
    if open_pid:
        try:
            from handlers_shop import show_product_detail_direct
            await show_product_detail_direct(context.bot, u.id, open_pid)
            return True
        except Exception:
            pass
    return False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🐛 v147 FIX (Bug4): groups — bot never responds to /start (or any message)
    # inside a group/supergroup, whether or not the bot is admin there.
    try:
        chat = update.effective_chat
        ct = str(getattr(chat, "type", "") or "")
        if ct in ("group", "supergroup"):
            return
    except Exception:
        pass
    await _panic_reset_user_session(update, context)
    u = update.effective_user
    # 🆕 v134: parse deep-link EARLY so the force-join continuation knows it
    # came from a referral link (math verification happens after "I Joined").
    arg = context.args[0] if context.args else ""
    rid, open_pid, chk_pid, open_freebies = _parse_start_arg(arg)
    if rid and int(rid) != int(u.id):
        context.user_data['_start_ref'] = int(rid)
        context.user_data['_start_pid'] = int(open_pid or 0)
    # 🐛 v147 FIX (Bug7): chk_<pid> → open checkout directly after welcome
    if chk_pid:
        context.user_data['_start_checkout_pid'] = int(chk_pid)
    elif open_pid:
        context.user_data['_start_pid'] = int(open_pid)
    # 🆕 v170.43: freebies deep link → welcome ke baad freebies menu
    if open_freebies:
        context.user_data['_start_freebies'] = True
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
    # 🐛 v170.52: welcome renderer ke liye is_new stash (persistent bar vs inline)
    try:
        context.user_data['_is_new_user'] = bool(is_new)
    except Exception:
        pass
    if is_new and u.id != ADMIN_ID:
        _nu = (u.username or '').strip()
        await notify_admin(context.bot,
            f"👤 *New User Joined!*\n"
            f"Name: {escape_md(u.first_name or 'N/A')}\n"
            f"Username: {('@' + escape_md(_nu)) if _nu else '_no username_'}\n"
            f"ID: `{u.id}`")
        # 🆕 v168: 📢 Broadcast new user join — BACKGROUND TASK (fire-and-forget)
        # Previously this blocked the /start handler for 2-3 minutes while sending
        # to all 1100+ users. Now runs in background so user gets instant response.
        try:
            from fake_engagement import broadcast_new_user_join
            import asyncio
            asyncio.create_task(broadcast_new_user_join(context.bot, u.first_name or "Someone"))
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

    # ─── Referral attribution + math gate + welcome ───
    # 🆕 v134: referral is recorded as PENDING (reward locked). If math
    # verification is enabled, the referral-origin user must answer a random
    # +/− question before the bot starts. Reward only unlocks after the bot
    # observes real-human activity (~30s) → BOTH users get the set points.
    if rid and int(rid) != int(u.id):
        # 🆕 v170.9: math verification PEHLE, count BAAD (user demand).
        # Math ON → pending (no count) → math sahi jawab par hi count.
        # Math OFF → turant count (pehle jaisa).
        _math_on = _referral_math_enabled()
        try:
            await _process_referral_attribution(context, u, int(rid), is_new,
                                                 product_id=int(open_pid or 0),
                                                 approve_now=(not _math_on))
        except Exception as _e:
            import logging
            logging.getLogger(__name__).error(f"[referral] {_e}")
        if _math_on:
            asked = False
            try:
                asked = await _ask_math_question(update.message, context,
                                                 u.id, u.first_name)
                if asked:
                    return  # wait for the math answer
            except Exception:
                asked = False
            if not asked:
                # math question bhejna fail → pending approve (bot stuck na ho)
                try:
                    await approve_pending_referral_for_user(context, u.id, reason='math_ask_failed')
                except Exception:
                    pass

    # ─── Deep-link to product detail / checkout ───
    # 🐛 v147 FIX (Bug7): chk_<pid> → direct checkout screen (payment methods)
    chk_pid = context.user_data.pop('_start_checkout_pid', 0) or 0
    if chk_pid:
        try:
            from handlers_order import open_checkout_direct
            if await open_checkout_direct(context.bot, u.id, chk_pid):
                return  # Checkout shown
        except Exception:
            pass
    if open_pid:
        try:
            from handlers_shop import show_product_detail_direct
            await show_product_detail_direct(context.bot, u.id, open_pid)
            return  # Stop here, we showed them the product
        except Exception:
            pass
    # 🆕 v170.43: ?start=freebies → freebies menu khole (deep link se)
    if context.user_data.pop('_start_freebies', False):
        try:
            from handlers_freebies import freebies_from_text
            await freebies_from_text(update, context)
            return
        except Exception:
            pass

    shop = get_setting("shop_name", SHOP_NAME)
    # 🆕 v137: WELCOME stays default-language (never switches) per admin request.
    text = _r("welcome").format(shop_name=shop, user_id=u.id)
    # v133: Pinned announcements are real pinned messages only; do not prepend them to welcome.
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    # 🐛 v170.52: naya user → persistent bar welcome par hi (no wave);
    # purana user → inline main menu (bar already cached).
    if is_new:
        await update.message.reply_text(send_text, parse_mode=send_mode,
            reply_markup=persistent_menu(u.id))
    else:
        await update.message.reply_text(send_text, parse_mode=send_mode,
            reply_markup=main_menu_keyboard(u.id == ADMIN_ID, user_id=u.id))

async def handle_how_to_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🆕 v78: Handler for the 📚 How to Use button on the persistent reply
    keyboard. Opens the same guide hub that the inline button would open,
    but via reply_text (since the trigger is a text message, not callback).
    """
    from ui_extras import how_to_hub_from_text
    await how_to_hub_from_text(update, context)


async def handle_reseller_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🆕 v170.12: Handler for the 🔗 Reseller API persistent reply-keyboard
    button. Opens the same Reseller API screen (landing ya access panel) via
    reply_text — inline main menu wala button ab persistent par hai."""
    u = update.effective_user
    if not u:
        return
    try:
        from handlers_admin import reseller_api_from_text
        await reseller_api_from_text(update, context)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"[persist-reseller] {e}")


async def handle_freebies_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🆕 v170.13: Handler for the 🎁 Freebies persistent reply-keyboard button."""
    try:
        from handlers_freebies import freebies_from_text
        await freebies_from_text(update, context)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"[persist-freebies] {e}")


async def handle_shop_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the same persisted Shop mode from the persistent reply keyboard."""
    u = update.effective_user
    if not u:
        return
    save_user(u.id, u.username or "", u.first_name or "")
    await _panic_reset_user_session(update, context)
    try:
        from database import (get_products_filtered, get_products_grouped_by_category,
                              get_user_shop_mode, SHOP_MODE_CATEGORIZED,
                              SHOP_MODE_CLASSIC, get_response_with_auto_register)
        from keyboards import all_products_keyboard, shop_categories_keyboard
        from utils import sort_products_by_first_word, smart_text_and_mode
        user_mode = get_user_shop_mode(u.id)
        if user_mode == SHOP_MODE_CATEGORIZED:
            grouped = get_products_grouped_by_category()
            title = get_response_with_auto_register(
                "shop_categories_title", DEFAULT_RESPONSES.get("shop_categories_title", "🛍️ Shop Categories"))
            if not grouped:
                title = DEFAULT_RESPONSES.get("no_products", "No products available yet.")
            title, parse_mode = smart_text_and_mode(title, "Markdown")
            await update.message.reply_text(
                title, parse_mode=parse_mode,
                reply_markup=shop_categories_keyboard(
                    grouped, user_mode=SHOP_MODE_CATEGORIZED))
            return

        # Classic remains the existing flat/filter-compatible Shop list.
        products = get_products_filtered("all")
        try:
            products = sort_products_by_first_word(products)
        except Exception:
            pass
        if not products:
            await update.message.reply_text(
                "🛍️ *Shop*\n━━━━━━━━━━━━━━━━━━━━\n\n_No products yet._",
                parse_mode="Markdown",
                reply_markup=shop_categories_keyboard(
                    {}, user_mode=SHOP_MODE_CLASSIC))
            return
        kb, pg, tp = all_products_keyboard(
            products, 1, user=u, filter_mode="all", shop_mode=SHOP_MODE_CLASSIC)
        await update.message.reply_text(
            f"🛍️ *Shop* — page {pg}/{tp}",
            parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"[persist-shop] {e}")

async def handle_balance_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🆕 v170.19: 💰 Balance persistent button — compact account summary."""
    u = update.effective_user
    if not u:
        return
    save_user(u.id, u.username or "", u.first_name or "")
    await _panic_reset_user_session(update, context)
    try:
        from database import get_user_points, get_ref_points, get_user
        from utils import fmt_points
        pts = get_user_points(u.id)
        refs = get_ref_points(u.id)
        usr = get_user(u.id)
        uname = (usr.get("username") if usr else None) or u.username or "—"
        text = (
            "💰 *Balance*\n━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 User: `{escape_md(str(u.id))}`"
            + (f" (@{escape_md(str(uname))})" if uname and uname != "—" else "") + "\n"
            f"💎 Wallet Points: *{fmt_points(pts)}*\n"
            f"🎁 Referral Points: *{fmt_points(refs)}*"
        )
        from keyboards import main_menu_keyboard
        await update.message.reply_text(
            text, parse_mode="Markdown",
            reply_markup=main_menu_keyboard(u.id == ADMIN_ID, user_id=u.id))
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"[persist-balance] {e}")


async def handle_deposit_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🆕 v170.19: 💎 Deposit persistent button — Buy Points screen."""
    u = update.effective_user
    if not u:
        return
    save_user(u.id, u.username or "", u.first_name or "")
    await _panic_reset_user_session(update, context)
    try:
        from database import get_user_points
        from keyboards import buy_points_keyboard, _custom_buttons_for
        from config import POINTS_PER_DOLLAR
        from telegram import InlineKeyboardMarkup as _IKM
        pts = get_user_points(u.id)
        rows = list(buy_points_keyboard().inline_keyboard)
        try:
            for r in _custom_buttons_for("buy_points"):
                rows.insert(-1, r)
        except Exception:
            pass
        text = (f"💎 *Buy Points*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💎 Your Points: *{pts}*\n💰 Rate: $1 = {POINTS_PER_DOLLAR} Points\n\n"
                f"Select payment method:")
        await update.message.reply_text(text, parse_mode="Markdown",
                                        reply_markup=_IKM(rows))
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"[persist-deposit] {e}")


async def handle_history_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🆕 v170.19: 📜 History persistent button — My Orders (receipt)."""
    u = update.effective_user
    if not u:
        return
    save_user(u.id, u.username or "", u.first_name or "")
    await _panic_reset_user_session(update, context)
    try:
        from database import get_user_product_orders
        from orders_layouts import render_orders
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        orders = get_user_product_orders(u.id)
        if not orders:
            await update.message.reply_text(
                "📜 *No orders yet!*\n\nStart shopping to see your orders here.",
                parse_mode="Markdown", reply_markup=main_menu_keyboard(False, user_id=u.id))
            return
        text, buttons = render_orders(orders, u.id, page=0, page_size=8, status_filter="all")
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
        from utils import smart_text_and_mode
        send_text, send_mode = smart_text_and_mode(text[:3900], "Markdown")
        await update.message.reply_text(send_text, parse_mode=send_mode,
                                        reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"[persist-history] {e}")


async def handle_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🆕 v170.19: 🌐 Language persistent button — language picker."""
    u = update.effective_user
    if not u:
        return
    save_user(u.id, u.username or "", u.first_name or "")
    await _panic_reset_user_session(update, context)
    try:
        from i18n import get_user_lang, t, lang_name
        from ui_extras import language_menu_keyboard
        current = get_user_lang(u.id)
        text = (t("lang_select_title", lang=current) + "\n\n"
                + t("lang_current", lang=current) + lang_name(current))
        await update.message.reply_text(text, parse_mode="Markdown",
                                        reply_markup=language_menu_keyboard(current))
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"[persist-language] {e}")


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
    # 🆕 v137: WELCOME stays default-language (never switches) per admin request.
    text = _r("welcome").format(shop_name=shop, user_id=u.id)
    # v133: Pinned announcements are real pinned messages only; do not prepend them to welcome.
    send_text, send_mode = smart_text_and_mode(text, "Markdown")
    # The owner specifically chose an effect for the persistent reply-keyboard
    # menu/home button. Scope only this fresh bot reply—not the incoming tap or
    # routine inline ``main_menu`` navigation—and always restore the context.
    _fx_token = None
    try:
        from message_effects import push_event
        _fx_token = push_event("persistent_menu_opened")
    except Exception:
        pass
    try:
        await update.message.reply_text(send_text, parse_mode=send_mode,
            reply_markup=main_menu_keyboard(u.id == ADMIN_ID, user_id=u.id))
    finally:
        try:
            from message_effects import reset_event
            reset_event(_fx_token)
        except Exception:
            pass

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    q = update.callback_query; await q.answer(); u = q.from_user
    nav_push(context, 'main_menu')  # 🔙 Track navigation
    shop = get_setting("shop_name", SHOP_NAME)
    # 🆕 v137: WELCOME stays default-language (never switches) per admin request.
    text = _r("welcome").format(shop_name=shop, user_id=u.id)
    # v133: Pinned announcements are real pinned messages only; do not prepend them to welcome.
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=main_menu_keyboard(u.id == ADMIN_ID, user_id=u.id))

async def my_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    q = update.callback_query; await q.answer(); u = q.from_user; db = get_user(u.id)
    nav_push(context, 'my_account')  # 🔙 Track navigation
    from database import get_ref_points, save_user as _su  # 🆕 v48/v145
    # 🐛 v145 FIX: refresh the DB profile on every My-Account open so usernames
    # are never stale. Fall back to the saved DB username when Telegram's live
    # username is missing (some clients report it empty).
    try:
        _su(u.id, u.username or "", u.first_name or "")
    except Exception:
        pass
    _live_uname = (u.username or '').strip()
    _db_uname = ''
    try:
        if db is not None:
            _db_uname = str(db.get('username') or '').strip()
    except Exception:
        pass
    _uname = _live_uname or _db_uname
    _uname_disp = escape_md(_uname) if _uname else '—'
    from database import get_combined_points  # 🆕 v161.12
    total_pts = get_combined_points(u.id)
    w_pts, r_pts = 0, 0
    try:
        from database import get_wallet_vs_referral
        w_pts, r_pts = get_wallet_vs_referral(u.id)
    except Exception:
        pass
    fmt_dict = dict(
        name=escape_md(u.first_name or 'N/A'),
        user_id=u.id,
        username=_uname_disp,
        points=get_user_points(u.id),
        referrals=get_referral_count(u.id),
        ref_points=get_ref_points(u.id),
        total_points=total_pts,          # 🆕 v161.12: combined balance
        wallet_points=w_pts,
        referral_points=r_pts,
        joined=format_date(db['joined_at'] if db else None)
    )
    tpl = _r("my_account", user_id=u.id)
    try:
        text = tpl.format(**fmt_dict)
        # 🐛 v137: templates hardcode "@{username}" → "@—" for no-username users
        text = text.replace('@—', '—').replace('@–', '–').replace('@-', '-')
    except KeyError:
        # Admin's custom my_account text may not include all placeholders
        try:
            text = tpl.format_map(_SafeDict(**fmt_dict))
        except Exception:
            text = tpl
    # 🆕 v161.12: always show combined balance line (wallet + referral usable together)
    if "{total_points}" not in tpl and "Total Balance" not in tpl:
        text += f"\n💰 Total Balance: *{fmt_points(total_pts)}* (💳 {fmt_points(w_pts)} + 🎁 {fmt_points(r_pts)})"
    elif "{ref_points}" not in tpl and "Referral Points" not in tpl:
        text += f"\n🎁 Referral Points: *{get_ref_points(u.id)}*"
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=back_btn(location="my_account"))


async def referral_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    q = update.callback_query; await q.answer(); u = q.from_user
    nav_push(context, 'referral')  # 🔙 Track navigation
    from database import get_ref_points, get_ref_points_per_ref  # 🆕 v48/v133
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={u.id}"
    rp = get_ref_points(u.id)
    rc = get_referral_count(u.id)
    pp_ref = get_ref_points_per_ref()
    fmt_dict = dict(
        ref_link=link, ref_count=rc,
        ref_points=rp, points_per_ref=pp_ref,
    )
    tpl = _r("referral_text")
    try:
        text = tpl.format(**fmt_dict)
    except KeyError:
        text = tpl.format_map(_SafeDict(**fmt_dict))
    # 🔧 v133: rewards line reflects the CURRENT per-ref value automatically.
    # 🆕 v134: rules updated — math verification + 30s human check + BOTH earn.
    rules = (
        "\n\n📌 *How your referral counts:*\n"
        "1️⃣ Friend must open your link and press */start*.\n"
        "2️⃣ If Force Join is enabled, they must join/verify required channel or group.\n"
        "3️⃣ Referral users pass a quick *math verification* before the bot starts.\n"
        "4️⃣ The bot *observes activity for ~30 seconds* — the reward unlocks only for a real human.\n"
        "5️⃣ Self-referrals, duplicate users, or suspicious activity are blocked.\n\n"
        f"🎁 *Rewards:* +{pp_ref:g} point(s) per approved direct referral to **BOTH you and your friend**. "
        f"🏆 *Milestone bonus:* {_ref_bonus_tiers_text()}"
    )
    text += rules
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=back_btn(location="referral"))


class _SafeDict(dict):
    """Used with str.format_map — missing keys leave the placeholder untouched
    instead of raising KeyError. Lets admin custom templates be tolerant."""
    def __missing__(self, key):
        return "{" + key + "}"

async def buy_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
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
    _bp = (f"💎 *Buy Points*\n━━━━━━━━━━━━━━━━━━━━\n\n💎 Your Points: *{pts}*\n💰 Rate: $1 = {POINTS_PER_DOLLAR} Points\n\nSelect payment method:")
    try:
        from i18n import tr_user
        _bp = tr_user(_bp, user_id=q.from_user.id) or _bp
    except Exception:
        pass
    await _safe_edit(q, _bp, parse_mode="Markdown", reply_markup=_IKM(rows))

async def transactions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    nav_push(context, 'transactions')  # 🔙 Track navigation
    """🔄 Transaction History — Deposits only with date/time + status"""
    q = update.callback_query; await q.answer()
    txns = get_user_transactions(q.from_user.id)
    if not txns:
        _em = "🔄 *No deposits yet!*\n\nUse 💎 Buy Points to deposit funds."
        try:
            from i18n import tr_user
            _em = tr_user(_em, user_id=q.from_user.id) or _em
        except Exception:
            pass
        await _safe_edit(q, _em,
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
