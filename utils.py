# ============================================
# 🛠️ UTILITY HELPERS
# ============================================
# Small helper functions used across the bot

from datetime import datetime
from urllib.parse import quote
import re
import html as _html


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
    _protect(r'<tg-emoji\s+emoji-id=["\']\d+["\']\s*>[^<]*</tg-emoji>', 'TG')
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
    return markdownish_to_html(s), "HTML"


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
    if html_v and has_custom_emoji:
        return "[[HTML]]" + html_v
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
    """🆕 Send a tracking message to admin (silent if fails)"""
    try:
        from config import ADMIN_ID
        await bot.send_message(ADMIN_ID, message, parse_mode=parse_mode)
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
