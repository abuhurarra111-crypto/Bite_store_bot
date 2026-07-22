# ════════════════════════════════════════════════════════════════
# 🛡️ v51: GLOBAL PREMIUM-EMOJI RENDERING GUARD
# ════════════════════════════════════════════════════════════════
# Bulletproof safety net that AUTO-APPLIES smart_text_and_mode() to
# every outgoing text message in the bot.
#
# Problem this fixes:
#   - Across 30+ handler files, many places send DB-saved response text
#     without going through smart_text_and_mode → users see raw
#     "[HTML]<tg-emoji ...>" garbage.
#   - Manual auditing of every send call is fragile.
#
# Solution:
#   Monkey-patch telegram.Bot.send_message / .edit_message_text /
#                 .edit_message_caption / .send_photo / .send_document
#                 .send_animation
#   so that ANY text/caption passing through them is auto-cleaned:
#     - [[HTML]] sentinel → switch parse_mode to HTML
#     - <tg-emoji> tags → switch parse_mode to HTML
#     - Markdown-ish that's safe → keep as-is
#
# Result:
#   Every single message in the bot (regardless of handler) renders
#   premium emojis correctly. No more [[HTML]] / [HTML] / raw <tg-emoji>
#   leaks. Backwards compatible — plain Markdown messages stay Markdown.
# ════════════════════════════════════════════════════════════════

import logging
from utils import smart_text_and_mode, contains_premium_markup, is_html_value

logger = logging.getLogger(__name__)
_installed = False


def install():
    """Install the global guard. Call ONCE at bot startup (post_init)."""
    global _installed
    if _installed:
        return
    try:
        from telegram import Bot
    except Exception as e:
        logger.error(f"[premium_guard] telegram import failed: {e}")
        return

    # ── Helper: normalize one text/caption + parse_mode kwarg combo ──
    # 🆕 v56: catch-all entity-chain collapser used even for plain-text sends
    # so user NEVER sees &amp;amp;amp; even if upstream data is corrupted.
    import re as _re_guard
    _PAT_AMP_CHAIN = _re_guard.compile(r'&(?:amp;){2,}')
    _PAT_AMP_ENTITY = _re_guard.compile(r'&amp;(lt|gt|quot|apos|nbsp);')

    def _collapse_entity_chains(text):
        """Collapse repeating HTML-entity escapes back to single form.
        Idempotent — safe to call any number of times."""
        if not text or not isinstance(text, str):
            return text
        prev = None
        for _ in range(5):
            new = _PAT_AMP_CHAIN.sub('&amp;', text)
            new = _PAT_AMP_ENTITY.sub(r'&\1;', new)
            if new == text:
                break
            text = new
        return text

    def _normalize(kwargs, text_key):
        """Mutates kwargs in place. Auto-detects premium markup or [[HTML]]
        sentinel and ensures parse_mode is set correctly."""
        if text_key not in kwargs and len(kwargs) == 0:
            return
        text = kwargs.get(text_key)
        if text is None or not isinstance(text, str):
            return

        # If text contains the premium-emoji sentinel or any <tg-emoji>/HTML tags,
        # force HTML mode (or rewrite to clean HTML).
        if is_html_value(text) or contains_premium_markup(text):
            # Convert Markdown-ish content to HTML, strip [[HTML]] sentinel.
            cleaned, mode = smart_text_and_mode(text, kwargs.get('parse_mode') or 'Markdown')
            # 🆕 v56: extra collapse pass — bullet-proof against any leak
            cleaned = _collapse_entity_chains(cleaned)
            kwargs[text_key] = cleaned
            kwargs['parse_mode'] = mode
            return

        # 🆕 v56: Even for plain-text sends (no premium markup), if there is
        # any '&amp;amp' chain in the text — collapse it. This catches the
        # case where corrupted DB data was already produced before v55 patch
        # and the rendering path doesn't go through smart_text_and_mode.
        if '&amp;amp' in text or '&amp;lt' in text or '&amp;gt' in text or '&amp;quot' in text:
            kwargs[text_key] = _collapse_entity_chains(text)
            return

        # Otherwise leave as-is — caller's parse_mode (Markdown/HTML/None) wins.

    # ── Patch each Bot send/edit method (positional or keyword) ──
    # We need to handle both `send_message(chat_id, text, ...)` (positional)
    # and `send_message(chat_id=..., text=..., ...)` (keyword).
    def _wrap_text_method(orig_func, text_param='text'):
        async def wrapped(self, *args, **kwargs):
            # If text is positional (2nd arg after chat_id), promote to kwargs
            # send_message signature: (chat_id, text, ...)
            if text_param == 'text' and len(args) >= 2 and isinstance(args[1], str):
                args = list(args)
                kwargs['text'] = args[1]
                args[1] = None
                # Re-strip None placeholder by rebuilding
                args = [a for a in args if not (a is None and len(kwargs) > 0)]
                args = tuple(args)
            try:
                _normalize(kwargs, text_param)
            except Exception as e:
                logger.warning(f"[premium_guard] normalize failed: {e}")
            return await orig_func(self, *args, **kwargs)
        return wrapped

    def _wrap_caption_method(orig_func):
        async def wrapped(self, *args, **kwargs):
            try:
                _normalize(kwargs, 'caption')
            except Exception as e:
                logger.warning(f"[premium_guard] normalize caption failed: {e}")
            return await orig_func(self, *args, **kwargs)
        return wrapped

    # send_message — text is 2nd positional
    Bot.send_message = _wrap_text_method(Bot.send_message, 'text')
    # edit_message_text — text is 1st positional in newer PTB? Check signature.
    # PTB 22.x: edit_message_text(text, chat_id=None, message_id=None, ...)
    # So text is 1st positional. Need different wrapper for this one.

    def _wrap_edit_text():
        orig = Bot.edit_message_text
        async def wrapped(self, *args, **kwargs):
            # If 1st positional is text string, promote to kwargs
            if len(args) >= 1 and isinstance(args[0], str):
                args = list(args)
                kwargs['text'] = args[0]
                args = tuple(args[1:])
            try:
                _normalize(kwargs, 'text')
            except Exception as e:
                logger.warning(f"[premium_guard] normalize edit_text failed: {e}")
            return await orig(self, *args, **kwargs)
        return wrapped
    Bot.edit_message_text = _wrap_edit_text()

    # edit_message_caption — caption is keyword-only typically
    def _wrap_edit_caption():
        orig = Bot.edit_message_caption
        async def wrapped(self, *args, **kwargs):
            try:
                _normalize(kwargs, 'caption')
            except Exception as e:
                logger.warning(f"[premium_guard] normalize edit_caption failed: {e}")
            return await orig(self, *args, **kwargs)
        return wrapped
    Bot.edit_message_caption = _wrap_edit_caption()

    # send_photo / send_document / send_animation / send_video — caption arg
    for meth_name in ('send_photo', 'send_document', 'send_animation',
                      'send_video', 'send_audio', 'send_voice'):
        if hasattr(Bot, meth_name):
            orig = getattr(Bot, meth_name)
            setattr(Bot, meth_name, _wrap_caption_method(orig))

    # ── Patch Message convenience methods (reply_text / reply_photo / etc.) ──
    # In PTB, message.reply_text() ultimately calls Bot.send_message — so
    # patching Bot covers all of them. But to be extra safe, also patch the
    # Message-level shortcuts in case any code path calls them directly with
    # raw text that bypasses our chain.
    try:
        from telegram import Message
        # reply_text — text is 1st positional
        def _wrap_msg_reply_text():
            orig = Message.reply_text
            async def wrapped(self, *args, **kwargs):
                if len(args) >= 1 and isinstance(args[0], str):
                    args = list(args)
                    kwargs['text'] = args[0]
                    args = tuple(args[1:])
                try:
                    _normalize(kwargs, 'text')
                except Exception as e:
                    logger.warning(f"[premium_guard] normalize reply_text failed: {e}")
                return await orig(self, *args, **kwargs)
            return wrapped
        Message.reply_text = _wrap_msg_reply_text()

        # reply_photo / reply_document / etc. — caption is keyword
        for meth_name in ('reply_photo', 'reply_document', 'reply_animation',
                          'reply_video', 'reply_audio', 'reply_voice'):
            if hasattr(Message, meth_name):
                orig = getattr(Message, meth_name)
                def _make_wrap(o):
                    async def wrapped(self, *args, **kwargs):
                        try:
                            _normalize(kwargs, 'caption')
                        except Exception as e:
                            logger.warning(f"[premium_guard] normalize {meth_name} failed: {e}")
                        return await o(self, *args, **kwargs)
                    return wrapped
                setattr(Message, meth_name, _make_wrap(orig))

        # edit_text / edit_caption convenience
        if hasattr(Message, 'edit_text'):
            orig_et = Message.edit_text
            async def _wrap_edit_text_msg(self, *args, **kwargs):
                if len(args) >= 1 and isinstance(args[0], str):
                    args = list(args); kwargs['text'] = args[0]
                    args = tuple(args[1:])
                try:
                    _normalize(kwargs, 'text')
                except Exception:
                    pass
                return await orig_et(self, *args, **kwargs)
            Message.edit_text = _wrap_edit_text_msg

        if hasattr(Message, 'edit_caption'):
            orig_ec = Message.edit_caption
            async def _wrap_edit_caption_msg(self, *args, **kwargs):
                try:
                    _normalize(kwargs, 'caption')
                except Exception:
                    pass
                return await orig_ec(self, *args, **kwargs)
            Message.edit_caption = _wrap_edit_caption_msg
    except Exception as e:
        logger.warning(f"[premium_guard] Message patches partial: {e}")

    # ── Patch CallbackQuery.edit_message_text / edit_message_caption ──
    try:
        from telegram import CallbackQuery
        if hasattr(CallbackQuery, 'edit_message_text'):
            orig_q = CallbackQuery.edit_message_text
            async def _wrap_q_edit_text(self, *args, **kwargs):
                if len(args) >= 1 and isinstance(args[0], str):
                    args = list(args); kwargs['text'] = args[0]
                    args = tuple(args[1:])
                try:
                    _normalize(kwargs, 'text')
                except Exception:
                    pass
                return await orig_q(self, *args, **kwargs)
            CallbackQuery.edit_message_text = _wrap_q_edit_text

        if hasattr(CallbackQuery, 'edit_message_caption'):
            orig_qc = CallbackQuery.edit_message_caption
            async def _wrap_q_edit_caption(self, *args, **kwargs):
                try:
                    _normalize(kwargs, 'caption')
                except Exception:
                    pass
                return await orig_qc(self, *args, **kwargs)
            CallbackQuery.edit_message_caption = _wrap_q_edit_caption
    except Exception as e:
        logger.warning(f"[premium_guard] CallbackQuery patches partial: {e}")

    _installed = True
    logger.info("✅ [premium_guard] Global premium-emoji rendering guard installed")
    print("✅ [premium_guard] Global premium-emoji rendering guard installed")
