# ============================================
# 🛠️ UTILITY HELPERS
# ============================================
# Small helper functions used across the bot

from datetime import datetime
from urllib.parse import quote
import re
import html as _html
from decimal import Decimal, InvalidOperation


def _to_decimal(value, default="0"):
    try:
        return Decimal(str(value if value is not None and value != "" else default))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(str(default))


def points_from_usd(amount, rate=None):
    """Convert USD to wallet points without truncating cents.

    v120: Old code used int(amount * POINTS_PER_DOLLAR), so $1.05 became
    10 points instead of 10.5. This helper preserves decimal points.
    """
    if rate is None:
        try:
            from config import POINTS_PER_DOLLAR as _R
            rate = _R
        except Exception:
            rate = 10
    return float(_to_decimal(amount) * _to_decimal(rate))


def fmt_points(value, suffix=""):
    """Pretty points display: 10.5000 -> 10.5, 10.000 -> 10."""
    d = _to_decimal(value)
    if d == d.to_integral_value():
        s = str(d.quantize(Decimal("1")))
    else:
        s = format(d.normalize(), "f").rstrip("0").rstrip(".")
    return f"{s}{suffix}"


def escape_md(text):
    """
    🔒 Escape Telegram Markdown special characters
    Prevents crash when user name/username has _ * ` [ etc.

    🆕 v42: If `text` starts with the [[HTML]] sentinel (premium-emoji
    HTML representation of a product name etc.), first strip the prefix
    and HTML tags so we don't render visible <tg-emoji> garbage inside
    Markdown messages. (HTML rendering is handled separately by
    name_for_message_html / _build_detail_text.)
    """
    if text is None:
        return ""
    text = str(text)
    if text.startswith("[[HTML]]"):
        # Defer to html_strip_tags for clean fallback text
        text = html_strip_tags(text)
    for ch in ['_', '*', '`', '[', ']']:
        text = text.replace(ch, '\\' + ch)
    return text  # 🆕 v80.1 CRITICAL BUG FIX — return was missing → caused
                 # `None` to appear everywhere escape_md() was called (pins,
                 # names, admin panels, ticket subjects, etc.)


# 🆕 v80: BYTE-PERFECT display helpers — use these anywhere account data,
# credentials, links, tokens, coupons, or ANY user-supplied content needs to
# be shown inside a message.
def html_code_block(text):
    """Wrap raw user content in an HTML <code>...</code> block, escaping only
    the 3 HTML-mandatory chars (< > &). Telegram unescapes them client-side
    when the user copies the text — so what the customer copies is byte-identical
    to what the admin uploaded.

    USE THIS instead of `escape_md(account_data)` — Markdown escapes _ * ` etc.
    which visually looks like `/` or `\\` in some fonts.
    """
    if text is None:
        return "<code></code>"
    s = str(text)
    # ORDER MATTERS: & must be first, otherwise later &lt; becomes &amp;lt;
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<code>{s}</code>"


def html_escape_plain(text):
    """Escape < > & for display in HTML mode WITHOUT wrapping in <code>."""
    if text is None:
        return ""
    s = str(text)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text


# 🆕 v42: Premium / custom emoji helpers
HTML_PREFIX = "[[HTML]]"


def is_html_value(value):
    """True if the string starts with the [[HTML]] sentinel."""
    return isinstance(value, str) and value.startswith(HTML_PREFIX)


def strip_html_prefix(value):
    """Remove the [[HTML]] sentinel if present, otherwise return unchanged."""
    if is_html_value(value):
        return value[len(HTML_PREFIX):]
    return value


def html_strip_tags(value):
    """Quick & dirty HTML → plain text (for fallback in places that
    must show pure text, e.g. button labels). Keeps the emoji char
    inside <tg-emoji>...</tg-emoji> but drops the tag wrapper."""
    if value is None:
        return ""
    s = strip_html_prefix(str(value))
    import re
    s = re.sub(r"<[^>]+>", "", s)  # strip every tag
    # Unescape common HTML entities
    s = (s.replace("&amp;", "&").replace("&lt;", "<")
           .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))
    return s


def name_for_button(value):
    """Safe rendering of a (possibly HTML-encoded) product name inside a
    Telegram inline button label. Button labels do NOT support entities,
    so we strip HTML tags & keep just the fallback chars/emojis."""
    return html_strip_tags(value)


def name_for_message_html(value):
    """Render a (possibly HTML-encoded) value for inclusion in an HTML message."""
    if value is None:
        return ""
    if is_html_value(value):
        return strip_html_prefix(value)
    return _html.escape(str(value))


def contains_premium_markup(value):
    """True if a string contains saved premium/custom-emoji HTML markup."""
    if value is None:
        return False
    s = str(value)
    return ('[[HTML]]' in s) or ('<tg-emoji' in s.lower())


def _unescape_markdown_escapes(text):
    if text is None:
        return ""
    return re.sub(r'\\([_*`\[\]~])', r'\1', str(text))


def markdownish_to_html(text):
    """Best-effort conversion of our project's Markdown-ish text to HTML.

    This lets us send one message in HTML mode when a premium emoji exists
    anywhere inside it, without leaking `[[HTML]]` or raw tags.
    Existing safe HTML tags are preserved.

    🆕 v55: CRITICAL FIX — When input already contains HTML entities
    (e.g. `&amp;` `&lt;` `&gt;` `&quot;` from Telegram's text_html_urled
    output), `_html.escape()` was double-escaping them → `&amp;amp;` →
    `&amp;amp;amp;` on repeat displays. Now we PROTECT existing entities
    before escape and restore them after.
    """
    if text is None:
        return ""
    s = str(text).replace('[[HTML]]', '')

    protected = {}
    def _protect(pattern, prefix, dotall=False):
        nonlocal s
        flags = re.I | (re.S if dotall else 0)
        def _sub(m):
            key = f"@@{prefix}{len(protected)}@@"
            protected[key] = m.group(0)
            return key
        s = re.sub(pattern, _sub, s, flags=flags)

    # Protect premium emoji tags + already-saved safe HTML tags before escaping.
    _protect(r'<tg-emoji\s+emoji-id=["\'][^"\']+["\']\s*>[^<]*</tg-emoji>', 'TG')
    # 🆕 v58: Protect ENTIRE <pre>...</pre> and <code>...</code> blocks
    # (CONTENT included) so Markdown chars inside them don't get converted.
    # Critical when admin opens "Edit Text" screen for a response that contains
    # raw `{placeholders}` with underscores — without this protection,
    # markdownish_to_html sees `{qty_text}` inside <pre> and converts
    # `_text}` → `<i>text}</i>` → invalid HTML.
    # MUST use dotall=True so <pre> blocks spanning multiple lines are matched.
    _protect(r'<pre\b[^>]*>.*?</pre>', 'PRE', dotall=True)
    _protect(r'<code\b[^>]*>.*?</code>', 'CODE', dotall=True)
    _protect(r'</?(?:b|i|u|s|blockquote)\b[^>]*>', 'HT')
    _protect(r'<a\s+href=["\'][^"\']+["\'][^>]*>.*?</a>', 'HTA', dotall=True)
    # 🆕 v55: PROTECT already-escaped HTML entities so they aren't escaped again.
    # Without this, "Reviews &amp; Ratings" would become "Reviews &amp;amp; Ratings"
    # and on the next display "Reviews &amp;amp;amp; Ratings" (compounding bug).
    _protect(r'&(?:amp|lt|gt|quot|apos|nbsp|#\d+|#x[0-9a-fA-F]+);', 'ENT')

    s = _unescape_markdown_escapes(s)
    s = _html.escape(s)

    # Code blocks first
    s = re.sub(r'```(.*?)```', lambda m: f"<pre>{m.group(1)}</pre>", s, flags=re.S)
    # Inline code
    s = re.sub(r'`([^`\n]+)`', lambda m: f"<code>{m.group(1)}</code>", s)
    # Strikethrough
    s = re.sub(r'~~([^~]+)~~', lambda m: f"<s>{m.group(1)}</s>", s)
    # Bold
    s = re.sub(r'\*([^*\n]+)\*', lambda m: f"<b>{m.group(1)}</b>", s)
    # Italic
    s = re.sub(r'_([^_\n]+)_', lambda m: f"<i>{m.group(1)}</i>", s)

    for key, val in protected.items():
        s = s.replace(key, val)

    # 🐛 v170.21 FIX: safety net — koi leftover @@XX<digits>@@ marker (e.g.
    # @@TG0@@) agar restore se reh gaya ho to hatao (premium emoji ke badle
    # marker text user ko kabhi na dikhe).
    try:
        s = re.sub(r'@@[A-Z]{1,8}\d+@@', '', s)
    except Exception:
        pass

    # 🆕 v56: BELT + SUSPENDERS — final safety pass. Even if some upstream
    # path slipped a double-escape past us (e.g. legacy data from before v55),
    # collapse any &amp;amp; / &amp;lt; / &amp;gt; / &amp;quot; chains here.
    # This makes markdownish_to_html() the LAST LINE OF DEFENSE against the
    # compounding bug, ensuring no &amp;amp;amp; ever reaches the user.
    try:
        # Repeatedly collapse until stable (max 5 iterations for deeply nested)
        for _ in range(5):
            new_s = re.sub(r'&(?:amp;){2,}', '&amp;', s)
            new_s = re.sub(r'&amp;(lt|gt|quot|apos|nbsp);', r'&\1;', new_s)
            if new_s == s:
                break
            s = new_s
    except Exception:
        pass
    return s


def sanitize_html_tags(text):
    """🐛 v143 FIX: make arbitrary admin text SAFE for Telegram HTML parsing.

    Telegram's HTML parser is strict: an unmatched closing tag (e.g. </b> with
    no open) or wrong nesting (<b><i>x</b></i>) raises
    'Can't parse entities: unmatched end tag...' — which made bot panels
    fail to update and look 'stuck' (the exact log error in the screenshot).

    This helper scans block tags (b/i/u/s/code/pre/a/blockquote/strong/em/
    tg-emoji) and:
      - drops orphan closing tags,
      - auto-closes unclosed tags at the end,
      - forces correct nesting by popping mismatched opens.
    It never raises and leaves plain text untouched.
    """
    import re as _re
    if not text or not isinstance(text, str):
        return text or ""
    s = str(text)
    if '<' not in s:
        return s
    tag_re = _re.compile(r'<(/?)(b|i|u|s|code|pre|a|blockquote|strong|em|tg-emoji)\b[^>]*>', _re.I)
    # collect tag positions
    ops = []
    for m in tag_re.finditer(s):
        closing = bool(m.group(1))
        name = m.group(2).lower()
        # self-closing tg-emoji has no explicit close
        if '/>' in m.group(0):
            continue
        ops.append((m.start(), m.end(), name, closing))
    if not ops:
        return s
    stack = []
    out = list(s)
    drops = []
    for i, (st, en, name, closing) in enumerate(ops):
        if not closing:
            # 🐛 v147 FIX: nested SAME-name tag (`<b><b>x</b></b>`) — the old
            # code kept the inner opening tag text but did NOT push it, so its
            # matching close was later treated as orphan and dropped → the outer
            # <b> never closed → Telegram "Can't find end tag corresponding to
            # start tag b" (this broke Buy Now on manual products whose names
            # contain <b> tags, e.g. "Canva 500 User Panel"). Now we DROP the
            # duplicate inner opening tag so the outer tag stays balanced.
            if stack and stack[-1] == name:
                drops.append((st, en))
                continue
            stack.append(name)
        else:
            if not stack:
                drops.append((st, en))  # orphan close → drop
            elif stack[-1] == name:
                stack.pop()
            elif name in stack:
                # wrong nesting (<b><i>x</b>) → drop this close entirely; the
                # final pass auto-closes the still-open <i> and <b> correctly.
                drops.append((st, en))
            else:
                drops.append((st, en))  # close for tag not open → drop
    # drop orphan closes (from end to start)
    for st, en in reversed(drops):
        del out[st:en]
    result = ''.join(out)
    # auto-close any remaining open tags (in reverse order)
    for name in reversed(stack):
        if name == 'tg-emoji':
            continue
        # find if there's a dangling close after all — just append close at end
        result += f"</{name}>"
    return result


def smart_text_and_mode(text, preferred_mode="Markdown"):
    """Return (text, parse_mode) with premium/custom emoji support.

    - Plain text stays in the preferred mode.
    - Any saved [[HTML]] / <tg-emoji> markup switches to HTML automatically.
    - Prevents raw [[HTML]] from leaking to users.
    """
    if text is None:
        return "", preferred_mode
    s = str(text)
    if not contains_premium_markup(s) and not re.search(r'</?(?:b|i|u|s|code|pre|a|blockquote)\b', s, flags=re.I):
        return s, preferred_mode
    html_out = markdownish_to_html(s)
    html_out = sanitize_html_tags(html_out)
    return html_out, "HTML"


# ════════════════════════════════════════════════════════════════
# 🆕 v48: Centralised premium-emoji-aware text capture & display
# ════════════════════════════════════════════════════════════════

def capture_user_text(message):
    """Extract text from a Telegram message preserving premium/custom emojis.

    Use this in EVERY text-input handler instead of `message.text`.
    Returns either:
      - "[[HTML]]<html with <tg-emoji> tags>"  if message contains premium emojis
      - plain text string                       otherwise

    The returned value can be saved to DB and later passed through
    `smart_text_and_mode()` to render correctly in any chat (with or without
    premium emojis).
    """
    if message is None:
        return ""
    raw = (message.text or message.caption or "") or ""
    try:
        html_v = (message.text_html_urled or message.caption_html_urled or "") or ""
        html_v = html_v.strip()
    except Exception:
        html_v = ""
    try:
        entities = list(message.entities or message.caption_entities or [])
    except Exception:
        entities = []
    has_custom_emoji = any(
        getattr(e, "type", "") == "custom_emoji" for e in entities
    )
    has_formatting = any(
        getattr(e, "type", "") in {"bold", "italic", "underline", "strikethrough",
                                    "code", "pre", "text_link", "blockquote",
                                    "spoiler", "expandable_blockquote"}
        for e in entities
    )
    # Promote to HTML form ONLY when premium emoji is present so we don't
    # break admin's existing Markdown-style messages.
    if has_custom_emoji:
        if html_v:
            return "[[HTML]]" + html_v
        # Fallback for tests/clients where text_html_urled is unavailable:
        # wrap custom emoji fallback chars with <tg-emoji>. Offsets are usually
        # UTF-16 in Telegram, but for leading emojis/text-input use this safe
        # best-effort rather than dropping the premium emoji entirely.
        try:
            pieces = []
            last = 0
            for e in sorted([x for x in entities if getattr(x, 'type', '') == 'custom_emoji'], key=lambda x: getattr(x, 'offset', 0)):
                off = int(getattr(e, 'offset', 0) or 0)
                ln = int(getattr(e, 'length', 1) or 1)
                eid = getattr(e, 'custom_emoji_id', '') or ''
                pieces.append(_html.escape(raw[last:off]))
                fallback = _html.escape(raw[off:off+ln] or '⭐')
                pieces.append(f'<tg-emoji emoji-id="{_html.escape(str(eid))}">{fallback}</tg-emoji>')
                last = off + ln
            pieces.append(_html.escape(raw[last:]))
            return "[[HTML]]" + ''.join(pieces)
        except Exception:
            return raw
    # If admin used formatting but no premium emoji, keep plain text so the
    # rest of the code path (which expects Markdown) still works.
    return raw


def has_premium_emoji(message):
    """🆕 v55: Return True if Telegram message has at least one premium/custom emoji entity.

    Use INSTEAD of `bool(message.entities)` when deciding whether to save the
    `[[HTML]]` form. Plain entities (bold/italic/urls) saved as HTML caused
    double-escape bugs (e.g. "Reviews &amp; Ratings" → "&amp;amp;") because
    text_html_urled returns text with HTML entities pre-escaped.

    Only when admin actually inserts a premium emoji do we need the HTML form.
    """
    if message is None:
        return False
    try:
        ents = (getattr(message, "entities", None) or
                getattr(message, "caption_entities", None) or [])
    except Exception:
        return False
    return any(getattr(e, "type", "") == "custom_emoji" for e in ents)


def safe_display(value, *, preferred_mode="Markdown", message=None):
    """Return (text, parse_mode) tuple safe to send back as a confirmation
    or echo. Handles all four cases:
      1. value starts with [[HTML]]  → unwrap and use HTML mode
      2. value contains <tg-emoji>   → use HTML mode
      3. message provided AND contains premium emoji entities → use HTML form
      4. plain text                  → escape for Markdown / pass through

    🆕 v53: If `message` parameter is provided AND it contains custom_emoji
    entities, we re-derive the HTML form from `message.text_html_urled` so
    confirmation echoes RENDER premium emojis even if `value` was the plain
    `message.text` (without [[HTML]] prefix). This fixes the common bug
    where admin types premium emoji → save logic preserves entities but
    echo path only uses plain text → premium emoji "disappears" in echo.

    Use:
        text, mode = safe_display(value, message=u.message)
        await reply_text(f"Saved: {text}", parse_mode=mode)
    """
    if value is None:
        return ("", preferred_mode)
    s = str(value)

    # 🆕 v53: If a Telegram Message was given and it has premium emoji entities,
    # prefer its HTML representation (renders premium emojis correctly).
    if message is not None:
        try:
            ents = list(getattr(message, "entities", None) or
                        getattr(message, "caption_entities", None) or [])
        except Exception:
            ents = []
        has_ce = any(getattr(e, "type", "") == "custom_emoji" for e in ents)
        if has_ce:
            try:
                html_form = (getattr(message, "text_html_urled", None) or
                             getattr(message, "caption_html_urled", None) or "")
                html_form = (html_form or "").strip()
            except Exception:
                html_form = ""
            if html_form:
                return (markdownish_to_html("[[HTML]]" + html_form), "HTML")

    if is_html_value(s) or contains_premium_markup(s):
        rendered = markdownish_to_html(s)
        return (rendered, "HTML")
    # 🆕 v56: even plain values may have leaked &amp;amp; corruption from
    # legacy data — collapse before showing.
    if '&amp;amp' in s or '&amp;lt' in s or '&amp;gt' in s or '&amp;quot' in s:
        try:
            for _ in range(5):
                ns = re.sub(r'&(?:amp;){2,}', '&amp;', s)
                ns = re.sub(r'&amp;(lt|gt|quot|apos|nbsp);', r'&\1;', ns)
                if ns == s: break
                s = ns
        except Exception:
            pass
    # Plain — escape only Markdown specials so caller can wrap in *bold* etc.
    return (escape_md(s), preferred_mode)


def safe_display_inline(value):
    """Like safe_display, but for embedding inside a larger Markdown message
    where you cannot switch parse_mode. Falls back to fallback-emoji text
    (no premium emoji shown but no garbage either).
    """
    if value is None:
        return ""
    s = str(value)
    if is_html_value(s) or contains_premium_markup(s):
        # Strip tags to get fallback text with standard emojis
        return escape_md(html_strip_tags(s))
    return escape_md(s)


def format_date(raw_date):
    """
    🗓️ Convert ugly DB date to user-friendly format
    '2026-05-27 14:30:15' → '27 May 2026'
    """
    if not raw_date:
        return "N/A"
    try:
        # Try with microseconds first
        try:
            dt = datetime.strptime(str(raw_date), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            dt = datetime.strptime(str(raw_date)[:19], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d %b %Y")
    except Exception:
        return str(raw_date)[:10]


def format_pkr(usd_amount, rate):
    """
    💱 Convert USD to PKR with thousand separator
    1.50 (rate 300) → 'Rs. 450'
    3.99 (rate 300) → 'Rs. 1,197'
    """
    try:
        pkr = float(usd_amount) * float(rate)
        return f"Rs. {int(round(pkr)):,}"
    except Exception:
        return "Rs. 0"


def get_product_delivery_mode(product):
    """Return product delivery mode as 'auto' or 'manual'."""
    try:
        if product is None:
            return 'auto'
        mode = product['delivery_mode']
    except Exception:
        try:
            mode = product.get('delivery_mode', 'auto')
        except Exception:
            mode = 'auto'
    return 'manual' if str(mode or 'auto').strip().lower() == 'manual' else 'auto'


def get_product_mode_tag(product, short=False):
    """Human-friendly mode tag for UI labels."""
    mode = get_product_delivery_mode(product)
    if short:
        return '✋ MANUAL' if mode == 'manual' else '🤖 AUTO'
    return '✋ Manual Order' if mode == 'manual' else '🤖 Auto Delivery'


def normalize_whatsapp_number(number):
    """Keep only digits for wa.me links."""
    return ''.join(ch for ch in str(number or '') if ch.isdigit())


def build_manual_order_message(product, user=None, quantity=None):
    """Prefilled WhatsApp text for manual-order products."""
    try:
        name = str(product['name'] or 'Product').strip()
    except Exception:
        name = str(getattr(product, 'name', 'Product')).strip()
    try:
        desc = str(product['description'] or '').strip()
    except Exception:
        desc = ''
    try:
        price = float(product['price'] or 0)
    except Exception:
        price = 0.0
    try:
        pid = product['id']
    except Exception:
        pid = ''

    if len(desc) > 220:
        desc = desc[:220].rstrip() + '...'

    if isinstance(user, dict):
        uid = user.get('id')
        first_name = user.get('first_name', '')
        username = user.get('username', '')
    else:
        uid = getattr(user, 'id', None) if user is not None else None
        first_name = getattr(user, 'first_name', '') if user is not None else ''
        username = getattr(user, 'username', '') if user is not None else ''

    lines = [
        'Assalam o Alaikum! I want to place a manual order.',
        '',
        f'Product: {name}',
        f'Product ID: {pid}',
        f'Mode: {get_product_mode_tag(product, short=True)}',
        f'Price: ${price:.2f}',
    ]
    if quantity:
        lines.append(f'Quantity: {quantity}')
    if desc:
        lines.append(f'Description: {desc}')
    lines.extend([
        '',
        'Delivery Required On Email: Yes',
        'Customer Email: ',
        '',
    ])
    if first_name:
        lines.append(f'Telegram Name: {first_name}')
    if username:
        lines.append(f'Telegram Username: @{username}')
    if uid:
        lines.append(f'Telegram User ID: {uid}')
    lines.extend([
        '',
        'Please share payment / next step.',
    ])
    return '\n'.join(lines)


def build_manual_order_whatsapp_url(product, user=None, quantity=None):
    """Build a wa.me URL with product/order details for manual products."""
    try:
        from database import get_setting
        from config import WHATSAPP_NUMBER
        wa_number = get_setting('whatsapp', WHATSAPP_NUMBER)
    except Exception:
        try:
            from config import WHATSAPP_NUMBER
            wa_number = WHATSAPP_NUMBER
        except Exception:
            wa_number = ''
    clean_wa = normalize_whatsapp_number(wa_number)
    if not clean_wa:
        return ''
    message = build_manual_order_message(product, user=user, quantity=quantity)
    return f"https://wa.me/{clean_wa}?text={quote(message)}"


def location_back_callback(location, default='main_menu'):
    """Map a custom-button location to the correct back callback.

    Supports nested submenus (`sub_<id>`) so Back returns to the submenu the
    user was inside, not always the main menu.
    """
    loc = str(location or '').strip()
    if not loc:
        return default
    if loc.startswith('sub_'):
        return f"cbsub_{loc.replace('sub_', '', 1)}"
    mapping = {
        'main': 'main_menu',
        'admin': 'admin_panel',
        'settings': 'admin_settings',
        'customization': 'admin_customization',
        'my_account': 'my_account',
        'shop': 'shop',
        'my_orders': 'my_orders',
        'support': 'support_menu',
        'warranty': 'warranty_menu',
        'reviews': 'reviews_menu',
        'loyalty': 'loyalty_menu',
        'transactions': 'transactions',
        'referral': 'referral',
        'buy_points': 'buy_points',
        'payment': 'go_back',
        'product_detail': 'go_back',
    }
    return mapping.get(loc, default)


def safe_edit_or_send(query, text, **kwargs):
    """
    🛡️ Safe message edit — falls back to caption edit if it was a photo
    Returns True if successful, False otherwise
    """
    pass  # implemented inline in handlers for simplicity



async def notify_admin(bot, message, parse_mode="Markdown"):
    """Send a tracking message to admin (silent if fails).

    v132: premium-emoji safe globally — if message contains [[HTML]]/<tg-emoji>,
    smart_text_and_mode automatically switches to HTML so premium emojis render.
    """
    try:
        from config import ADMIN_ID
        send_text, send_mode = smart_text_and_mode(message, parse_mode)
        await bot.send_message(ADMIN_ID, send_text, parse_mode=send_mode)
    except Exception:
        pass


# ════════════════════════════════════════════
# 🔙 NAVIGATION STACK (Back Button Fix)
# ════════════════════════════════════════════
# Tracks where user came from so Back button
# goes to PREVIOUS screen, not always Main Menu.

def nav_push(context, screen_id):
    """Push current screen onto navigation stack.
    Call this BEFORE showing a new screen.
    screen_id = callback_data of current screen (e.g. 'shop', 'my_account')
    """
    try:
        stack = context.user_data.get('nav_stack', [])
        # Don't push if same as top (prevents duplicates)
        if stack and stack[-1] == screen_id:
            return
        stack.append(screen_id)
        # Keep only last 10 entries to prevent memory bloat
        context.user_data['nav_stack'] = stack[-10:]
    except Exception:
        pass


def nav_pop(context):
    """🔧 v39 Bug #22 FIX: Return PREVIOUS screen (not current).

    Each handler pushes its own screen_id. To "go back", we need the screen
    BEFORE the current one. So we pop the current top (which is where we are now)
    AND return the next-to-top (where we came from).

    Returns 'main_menu' if no previous screen exists.
    """
    try:
        stack = context.user_data.get('nav_stack', [])
        if not stack:
            return 'main_menu'
        # Pop current (where we are now)
        stack.pop()
        # Return previous (where we came from)
        if stack:
            return stack[-1]
    except Exception:
        pass
    return 'main_menu' 


def nav_clear(context):
    """Clear navigation stack (used on cancel/reset)"""
    try:
        context.user_data.pop('nav_stack', None)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# 🔧 v39 FIX: Safe callback data reassignment (PTB 21 frozen objects)
# ════════════════════════════════════════════════════════════════
def set_cb_data(update_or_query, new_data):
    """Safely re-set callback_query.data on a frozen TelegramObject.
    PTB 21+ uses immutable objects — use the built-in _unfrozen() context.

    Usage:
        set_cb_data(update, "new_callback")
        # ... then call the target handler
    """
    try:
        q = update_or_query.callback_query if hasattr(update_or_query, 'callback_query') else update_or_query
        if q is None:
            return False
        with q._unfrozen():
            q.data = new_data
        return True
    except Exception:
        # Best effort; some PTB versions may not have _unfrozen
        try:
            object.__setattr__(q, 'data', new_data)
            return True
        except Exception:
            return False


# ════════════════════════════════════════════════════════════════
# 🆕 v98: AUTO-GROUP PRODUCTS BY FIRST WORD (case-insensitive)
# ════════════════════════════════════════════════════════════════
# Groups product list so that products whose FIRST WORD (after stripping
# emoji + [[HTML]]/<tg-emoji> markup) matches case-insensitively appear
# together, one below the other.
#
# Behaviour:
#   • Toggle key: bot_settings["auto_group_by_name"]  ("1"=ON default, "0"=OFF)
#   • Groups sorted alphabetically by first word (predictable UX)
#   • Products within a group keep their original relative order
#   • Products with no extractable first word land at the end
#   • Works for BOTH admin-added AND supplier-imported products
#     (input is the same product list from the DB in either case)
# ════════════════════════════════════════════════════════════════

def _extract_first_word(name):
    """Strip [[HTML]]/<tg-emoji> markup + leading emoji, return lowercase
    first alphanumeric word. Returns "" if nothing usable found."""
    import re as _re
    if not name:
        return ""
    s = str(name)

    # Strip [[HTML]] prefix
    if s.startswith("[[HTML]]"):
        s = s[len("[[HTML]]"):]

    # Strip <tg-emoji>...</tg-emoji> entirely (leading premium emoji)
    s = _re.sub(
        r"^\s*<tg-emoji\s+emoji-id=[\"'][^\"']+[\"']\s*>[^<]{0,8}</tg-emoji>\s*",
        "", s
    )
    # Strip any residual HTML tags
    s = _re.sub(r"<[^>]+>", "", s).strip()

    # Strip leading regular emoji + symbols + punctuation
    s = _re.sub(
        r"^[\s\U0001F000-\U0001FFFF\u2600-\u27BF\U00002B00-\U00002BFF"
        r"\U0001F300-\U0001F9FF\u2700-\u27BF\u203C-\u2049\ufe0f"
        r"\-\*\_\|\+\=\#\@\!\?\.\,\:\;\(\)\[\]\{\}\'\"~`^<>/\\]+",
        "", s
    ).strip()

    if not s:
        return ""

    # Take first whitespace-separated token
    first = s.split()[0] if s.split() else ""
    if not first:
        return ""

    # Keep only alphanumerics from that token (e.g. "grok!" → "grok",
    # "3M" → "3m", "1-Month" → "1")
    first = _re.sub(r"[^a-zA-Z0-9]", "", first).lower()
    return first


def is_auto_group_enabled():
    """Check admin toggle; default ON.

    Uses the same toggle_* infrastructure as other Customization panel toggles
    (so it lives under bot_settings key 'toggle_auto_group_by_name').
    """
    try:
        from database import get_toggle
        return get_toggle("auto_group_by_name", "1") == "1"
    except Exception:
        return True   # safe default


def sort_products_by_first_word(products, force=False):
    """Return a NEW list of the same product rows re-ordered so that products
    with matching first word cluster together. Groups sorted alphabetically
    by first word. Preserves original order within each group (stable sort).

    Args:
        products: iterable of dict/Row with a 'name' key
        force: if True, ignore the admin toggle and always group

    Returns:
        list — reordered products
    """
    try:
        lst = list(products or [])
        if not lst:
            return lst
        if not force and not is_auto_group_enabled():
            return lst

        # Assign each product to a group key + preserve original index for stability
        indexed = []
        for i, p in enumerate(lst):
            try:
                name = p.get("name") if hasattr(p, "get") else p["name"]
            except Exception:
                name = ""
            fw = _extract_first_word(name)
            # Products with no first word bucket into "~unclassified~" (sorts last)
            group_key = fw if fw else "~"
            indexed.append((group_key, i, p))

        # Stable sort: primary = group key, secondary = original index
        indexed.sort(key=lambda t: (t[0], t[1]))
        return [t[2] for t in indexed]
    except Exception:
        # Never break the shop — return original on any error
        return list(products or [])


# ════════════════════════════════════════════════════════════════
# 🆕 v104: HEAL escaped <tg-emoji> in stored delivery_content
# ════════════════════════════════════════════════════════════════
# Old bug (v83..v103): render_v83_delivery() ran html_escape_plain()
# on the product name, converting premium <tg-emoji> markup into
# &lt;tg-emoji&gt; literal text. That garbage got saved to
# orders.delivery_content AND sent to the customer.
#
# This heal function auto-fixes stored content at DISPLAY time so:
#   • Admin "User-Side Delivery Preview" (v101) shows clean
#   • Customer's "My Orders → View" (v100 patched) shows clean
#   • Re-send / re-preview of old orders shows clean
#
# Pure display-time fix — doesn't touch DB (safe, reversible).
# ════════════════════════════════════════════════════════════════

def heal_escaped_delivery_content(text):
    """Un-escape any accidentally-escaped <tg-emoji ...> and [[HTML]] markers
    that leaked into stored delivery_content. Never raises."""
    if not text:
        return text
    try:
        import re as _re
        s = str(text)

        # Case A: `[[HTML]]&lt;tg-emoji emoji-id="X"&gt;📱&lt;/tg-emoji&gt;`
        # → strip inner [[HTML]] wart + unescape the tg-emoji tag
        # We do NOT touch legitimate escaped content elsewhere (only the
        # tg-emoji block gets un-escaped).
        pattern = _re.compile(
            r'(\[\[HTML\]\])?'
            r'&lt;tg-emoji\s+emoji-id=(?:&quot;|")(\d+)(?:&quot;|")\s*&gt;'
            r'([^<&]{0,8})'
            r'&lt;/tg-emoji&gt;',
            flags=_re.IGNORECASE,
        )
        def _replace(m):
            emoji_id = m.group(2)
            fallback = m.group(3)
            return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
        s = pattern.sub(_replace, s)

        # Case B: any leftover `[[HTML]]` sentinel embedded mid-text
        # (from double-wrapping) — strip only the ones that aren't at start
        # because the leading [[HTML]] is meaningful (parse_mode selector).
        if s.startswith("[[HTML]]"):
            head, tail = s[:len("[[HTML]]")], s[len("[[HTML]]"):]
            s = head + tail.replace("[[HTML]]", "")
        else:
            s = s.replace("[[HTML]]", "")

        return s
    except Exception:
        return text


# ════════════════════════════════════════════════════════════════
# 🆕 v105: FULL-PRECISION PRICE FORMATTING (never truncate/round)
# ════════════════════════════════════════════════════════════════
# User complaint: "Amount supplier ny 0.103 rkhi hoti or mere pas 0.02 bot
# dekhata hai... ma b kisi product ki price agr asi rkh do 0.024 ya 0.0030003
# to lgti hi ni."
#
# Root cause: everywhere in the codebase used `${price:.2f}` which rounds
# to 2 decimals → 0.103 → $0.10, 0.024 → $0.02, 0.003 → $0.00.
# Also _compute_sell_price() called round(..., 2) which truncated to
# 2 decimals BEFORE saving to DB.
#
# fmt_price() rules:
#   • Preserves FULL precision as stored
#   • Drops trailing zeros for cleanliness
#   • Whole dollars → "$5"  (not "$5.00")
#   • Sub-cent → "$0.103"  "$0.024"  "$0.0030003"  "$0.00030003"
#   • Handles None / int / float / str inputs safely
# ════════════════════════════════════════════════════════════════

def fmt_price(value, prefix="$", fallback="—"):
    """Format a monetary value with FULL precision (no rounding).

    Examples:
        fmt_price(5)          → "$5"
        fmt_price(5.00)       → "$5"
        fmt_price(5.10)       → "$5.1"
        fmt_price(0.103)      → "$0.103"
        fmt_price(0.024)      → "$0.024"
        fmt_price(0.0030003)  → "$0.0030003"
        fmt_price("2.1500")   → "$2.15"
        fmt_price(None)       → "—"
        fmt_price(0)          → "$0"
    """
    if value is None or value == "":
        return fallback
    try:
        v = float(value)
    except (TypeError, ValueError):
        return fallback

    # Very-small numbers may lose precision in float; use repr() for max digits
    # then trim trailing zeros
    if v == 0:
        return f"{prefix}0"
    if v == int(v):
        return f"{prefix}{int(v)}"

    # For non-integer: convert to string with up to 10 decimal places, strip trailing zeros
    s = f"{v:.10f}".rstrip("0").rstrip(".")
    return f"{prefix}{s}"


def fmt_price_precise(value):
    """Like fmt_price but WITHOUT currency prefix (for embedding in formatted strings).
    Same precision rules. Empty on None/invalid."""
    if value is None or value == "":
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    if v == 0:
        return "0"
    if v == int(v):
        return f"{int(v)}"
    return f"{v:.10f}".rstrip("0").rstrip(".")



def order_payment_context(oid):
    """🐛 v145: build a rich context line for ADMIN payment notifications.
    Extracts product name, supplier (if any), supplier cost, selling price,
    qty and total from an order — so every 'pending' alert shows what the
    user is actually buying and the margin.
    Returns a list of display lines (already markdown-safe) or [] if nothing.
    """
    lines = []
    try:
        from database import get_order, get_product, get_connection
        o = get_order(int(oid))
        if not o:
            return lines
        pname = (o.get('product_name') or '').strip()
        qty = int(o.get('order_qty') or 1)
        selling = 0.0
        try:
            selling = float(o.get('price') or 0)
        except Exception:
            selling = 0.0
        total = round(selling * qty, 2)

        # Points purchase?
        order_type = (o.get('order_type') or '')
        if 'point' in str(order_type).lower() or 'buy_points' in str(order_type).lower() or pname.lower().startswith('💎'):
            lines.append(f"💎 *Buying:* Points (amount ${total:.2f})")
            return lines

        if pname:
            lines.append(f"📦 *Product:* {pname[:40]}{' × '+str(qty) if qty>1 else ''}")
        if selling and total:
            lines.append(f"💰 *Selling:* ${selling:.2f}/pc · Total ${total:.2f}")

        # Supplier cost via ext_product link
        try:
            pid = o.get('product_id')
            if pid:
                p = get_product(int(pid))
                if p:
                    pd = dict(p)
                    ext_sid = int(pd.get('ext_supplier_id') or 0)
                    ext_pid = int(pd.get('ext_product_id') or 0)
                    cost = None
                    sup_name = None
                    if ext_sid:
                        conn = get_connection(); c = conn.cursor()
                        c.execute("SELECT name FROM ext_suppliers WHERE id=?", (ext_sid,))
                        r = c.fetchone()
                        if r:
                            sup_name = r[0]
                        if ext_pid:
                            c.execute("SELECT cost_usd FROM ext_products WHERE id=?", (ext_pid,))
                            r2 = c.fetchone()
                            if r2:
                                try:
                                    cost = float(r2[0] or 0)
                                except Exception:
                                    cost = None
                        conn.close()
                    if sup_name:
                        lines.append(f"🔗 *Supplier:* {sup_name[:30]}")
                    if cost is not None:
                        lines.append(f"🧾 *Supplier cost:* ${cost:.2f}/pc")
                        if selling > 0:
                            margin = round((selling - cost) * qty, 2)
                            lines.append(f"📈 *Margin:* ${margin:.2f}")
        except Exception:
            pass
    except Exception:
        pass
    return lines


def payment_method_label(method):
    """Friendly + network-aware label for a payment method string."""
    m = (method or '').lower()
    if 'bybit_pay' in m:
        return "💳 Bybit Pay"
    if 'bybit_usdt_trc20' in m:
        return "💎 Bybit USDT (TRC20)"
    if 'bybit_usdt_bep20' in m:
        return "💎 Bybit USDT (BEP20)"
    if 'bybit' in m:
        return "💳 Bybit"
    if 'binance_pay' in m or ('binance' in m and 'usdt' not in m):
        return "🪙 Binance Pay"
    if 'binance_usdt_trc20' in m or ('binance' in m and 'trc20' in m):
        return "🪙 Binance USDT (TRC20)"
    if 'binance_usdt_bep20' in m or ('binance' in m and 'bep20' in m):
        return "🪙 Binance USDT (BEP20)"
    if 'binance' in m:
        return "🪙 Binance"
    if 'easy' in m:
        return "📱 EasyPaisa"
    if 'jazz' in m:
        return "📞 JazzCash"
    if 'usdt_trc20' in m:
        return "💎 USDT (TRC20)"
    if 'usdt_bep20' in m:
        return "💎 USDT (BEP20)"
    if 'point' in m:
        return "💎 Points"
    return (method or 'Payment').title()


# ════════════════════════════════════════════════════════════════
# 📣 v156: BROADCAST PROGRESS — live counting animation for big sends
# (poll broadcasts, pinned-post pushes, global broadcasts). The admin gets
# a single message that keeps EDITING itself with a progress bar + live
# count ("sent 123 / 900"), so it feels like the bot is counting in real
# time. Rate-limit-safe: refreshes at most every ~1.2s.
# ════════════════════════════════════════════════════════════════

class BroadcastProgress:
    """Live-updating progress message for long broadcasts.

    Usage:
        prog = BroadcastProgress(bot, chat_id, title="📣 Broadcasting", total=900)
        await prog.start()
        ...
        await prog.bump()          # after each successful send
        ...
        await prog.finish(done_msg="✅ Broadcast complete!")
    """

    def __init__(self, bot, chat_id, title="📣 Broadcasting", total=0):
        self.bot = bot
        self.chat_id = chat_id
        self.title = title
        self.total = max(1, int(total or 0))
        self.done = 0
        self.msg_id = None
        self._last_refresh = 0.0
        self._refresh_gap = 1.2  # seconds — safe for Telegram edit limits
        self._emoji_cycle = ["🎯", "📡", "📤", "⏳", "🚀", "✨"]
        self._cycle_i = 0

    def _bar(self):
        pct = min(1.0, (self.done / self.total) if self.total else 0)
        filled = int(pct * 12)
        return "█" * filled + "░" * (12 - filled)

    def _render(self):
        pct = int((self.done / self.total) * 100) if self.total else 0
        emo = self._emoji_cycle[self._cycle_i % len(self._emoji_cycle)]
        return (
            f"{emo} *{self.title}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"`{self._bar()}` *{pct}%*\n"
            f"📤 Sent: *{self.done:,}* / {self.total:,}\n"
            f"_Live — har user pe update ho raha hai..._"
        )

    async def start(self):
        try:
            m = await self.bot.send_message(self.chat_id, self._render(),
                                            parse_mode="Markdown")
            self.msg_id = m.message_id
        except Exception:
            self.msg_id = None

    async def _refresh(self):
        import time as _t
        now = _t.time()
        if now - self._last_refresh < self._refresh_gap:
            return
        self._last_refresh = now
        self._cycle_i += 1
        if self.msg_id:
            try:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id, message_id=self.msg_id,
                    text=self._render(), parse_mode="Markdown")
            except Exception:
                pass

    async def bump(self, n=1):
        self.done += int(n or 0)
        await self._refresh()

    async def finish(self, done_msg=None):
        if self.msg_id:
            try:
                final = done_msg or (
                    f"✅ *{self.title} — Complete!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📤 Sent: *{self.done:,}* / {self.total:,} ✅")
                await self.bot.edit_message_text(
                    chat_id=self.chat_id, message_id=self.msg_id,
                    text=final, parse_mode="Markdown")
                self.msg_id = None
            except Exception:
                pass
        elif done_msg:
            try:
                await self.bot.send_message(self.chat_id, done_msg,
                                            parse_mode="Markdown")
            except Exception:
                pass
