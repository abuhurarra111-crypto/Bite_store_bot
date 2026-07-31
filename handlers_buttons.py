# ============================================================
# 🧩 v77 BUNDLE: handlers_buttons.py
# ============================================================
# This file is the merged result of 4 originally separate modules:
#   • handlers_button_styler.py
#   • handlers_button_text.py
#   • handlers_custom_actions.py
#   • handlers_product_design.py
#
# 🛡️ ALL CODE IS PRESERVED VERBATIM. Each original file's contents appears
# below in its own section. Imports and behavior are byte-identical to the
# pre-merge codebase — only file count is reduced.
# ============================================================


# ============================================================
# 📄 ORIGINAL FILE: handlers_button_styler.py
# ============================================================

# ============================================================
# 🎨 BUTTON STYLER — ADMIN PANEL HANDLERS (v41-clean)
# ============================================================
# Admin per-button size / alignment / pad settings ka UI.
#
# Callback patterns:
#   bs_panel                    → main list (paginated)
#   bs_pg_<page>                → page navigation
#   bs_edit_<key>               → single button editor
#   bs_size_<key>_<size>        → set size
#   bs_align_<key>_<align>      → set alignment
#   bs_pad_<key>_<delta>        → adjust pad (+5 / -5 / 0)
#   bs_reset_<key>              → reset this button
#   bs_resetall                 → confirm + reset all
#   bs_resetall_yes             → actually reset all
#   bs_preview_<key>            → live preview popup
# ============================================================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from config import ADMIN_ID
from button_system import (
    SIZES, ALIGNS, MAX_PAD,
    get_style, set_style, reset_style,
    style_label, style_summary, list_known_keys, get_grouped_keys,
)

PER_PAGE = 10


# ── safe edit helper (matches project style) ─────────────────
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

def _admin_only(q):
    return q.from_user.id == ADMIN_ID


# ════════════════════════════════════════════════════════════
# MAIN PANEL — grouped categories + drill-down to individual buttons
# ════════════════════════════════════════════════════════════
async def bs_panel_callback(u, c):
    """Main entry — shows group categories."""
    q = u.callback_query
    if not _admin_only(q):
        await q.answer("❌", show_alert=True); return
    await q.answer()
    await _show_groups(q)


async def _show_groups(q):
    """Top-level: show all groups (Main Menu, Admin, Shop, Products, Categories, Custom, etc.)"""
    groups = get_grouped_keys()
    total_buttons = sum(len(items) for items in groups.values())

    kb = []
    for group_name, items in groups.items():
        # Count how many are customized in this group
        customized = sum(1 for k, _ in items if style_summary(k) != "default")
        suffix = f"  ({len(items)})" if customized == 0 else f"  ({customized}/{len(items)} ✏️)"
        kb.append([InlineKeyboardButton(
            f"{group_name}{suffix}",
            callback_data=f"bs_grp_{_safe_group_id(group_name)}"
        )])

    kb.append([InlineKeyboardButton("♻️ Reset ALL to default", callback_data="bs_resetall")])
    kb.append([InlineKeyboardButton("🔙 Back to Customization", callback_data="admin_customization")])

    text = (
        "🎨 *Inline Button Styler*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Control the *size*, *alignment*, and *padding* of each inline button "
        "individually set kar sakte hain.\n\n"
        "📏 *Size*: S / M / L / XL / **Full**\n"
        "↔️ *Align*: Left / Center / Right\n"
        "📐 *Pad*: 0-40 spaces\n\n"
        f"📊 Total styleable buttons: *{total_buttons}*\n\n"
        "👇 *Group chunein:*\n"
        "_Brackets ka number: total buttons (customized/total ✏️)_"
    )
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


# Map between display name ↔ short callback id (Telegram callback_data ≤ 64 bytes)
_GROUP_IDS = {}  # short_id → full_name
_GROUP_RID = {}  # full_name → short_id

def _safe_group_id(name):
    """Stable short id for a group name."""
    if name not in _GROUP_RID:
        sid = f"g{len(_GROUP_IDS)}"
        _GROUP_IDS[sid] = name
        _GROUP_RID[name] = sid
    return _GROUP_RID[name]


async def bs_group_callback(u, c):
    """Show buttons inside a specific group (paginated)."""
    q = u.callback_query
    if not _admin_only(q):
        await q.answer("❌", show_alert=True); return
    await q.answer()
    parts = q.data.split("_")
    sid = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    group_name = _GROUP_IDS.get(sid)
    if not group_name:
        await _show_groups(q); return
    await _show_group_items(q, group_name, page)


async def _show_group_items(q, group_name, page=0):
    groups = get_grouped_keys()
    items = groups.get(group_name, [])
    if not items:
        await _show_groups(q); return

    total = len(items)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, pages - 1))
    chunk = items[page * PER_PAGE:(page + 1) * PER_PAGE]

    kb = []
    for key, friendly in chunk:
        summary = style_summary(key)
        mark = "✏️" if summary != "default" else "▫️"
        label = f"{mark} {friendly[:42]}  [{summary}]"
        kb.append([InlineKeyboardButton(label, callback_data=f"bs_edit_{key}")])

    sid = _safe_group_id(group_name)
    # Pagination within group
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev",
                    callback_data=f"bs_grp_{sid}_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{pages}", callback_data="bs_noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️",
                    callback_data=f"bs_grp_{sid}_{page+1}"))
    if nav:
        kb.append(nav)

    kb.append([InlineKeyboardButton("🔙 Back to Groups", callback_data="bs_panel")])

    text = (
        f"🎨 *{group_name}*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 Buttons: *{total}*\n"
        "✏️ = customized | ▫️ = default\n\n"
        "_Tap any button to edit._"
    )
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


# Legacy page handler — redirect to groups view
async def bs_page_callback(u, c):
    q = u.callback_query
    if not _admin_only(q):
        await q.answer("❌", show_alert=True); return
    await q.answer()
    await _show_groups(q)


# ════════════════════════════════════════════════════════════
# SINGLE BUTTON EDITOR
# ════════════════════════════════════════════════════════════
async def bs_edit_callback(u, c):
    q = u.callback_query
    if not _admin_only(q):
        await q.answer("❌", show_alert=True); return
    await q.answer()
    key = q.data[len("bs_edit_"):]
    await _show_editor(q, key, c)


def _friendly_for(key):
    # 🆕 v49: Pretty name for per-product free-claim broadcast button
    if key.startswith("fc_btn_") and key[7:].isdigit():
        try:
            from database import get_product
            from utils import html_strip_tags, is_html_value, fmt_price
            p = get_product(int(key[7:]))
            if p:
                nm = p["name"]
                if is_html_value(nm):
                    nm = html_strip_tags(nm)
                return f"🎁 Free Claim Button — {nm[:30]}"
        except Exception:
            pass
        return f"🎁 Free Claim Button — Product #{key[7:]}"
    for k, name in list_known_keys():
        if k == key:
            return name
    return key


def _sample_label_for(key):
    """Pick a representative sample label so admin can see effect of styling."""
    # Registry buttons → use their medium label
    if key.startswith("reg_"):
        bid = key[len("reg_"):]
        try:
            from button_system import BUTTONS
            info = BUTTONS.get(bid, {})
            return info.get("medium") or info.get("large") or bid
        except Exception:
            return bid

    # Per-product sample = actual product name + price
    if key.startswith("prod_") and key[5:].isdigit():
        try:
            from database import get_product
            p = get_product(int(key[5:]))
            if p:
                s = p['stock']
                if s > 0:
                    return f"🛍️ {p['name']} — {fmt_price(p['price'])}"
                else:
                    return f"🛍️ {p['name']} ❌ Out of Stock"
        except Exception:
            pass
        return f"🛍️ Product"

    # Per-category sample = actual emoji + name
    if key.startswith("cat_") and key[4:].isdigit():
        try:
            from database import get_connection
            conn = get_connection(); c = conn.cursor()
            c.execute("SELECT * FROM categories WHERE id=?", (int(key[4:]),))
            row = c.fetchone(); conn.close()
            if row:
                emoji = row['emoji'] if 'emoji' in row.keys() else '🏷️'
                return f"{emoji} {row['name']}"
        except Exception:
            pass
        return f"🏷️ Category"

    # Per-custom-button sample = actual label
    if key.startswith("custom_") and key[7:].isdigit():
        try:
            from database import get_custom_button
            b = get_custom_button(int(key[7:]))
            if b:
                return b['label']
        except Exception:
            pass
        return "🎨 Custom Button"

    # 🆕 v49: Free-Claim per-product broadcast button
    if key.startswith("fc_btn_") and key[7:].isdigit():
        try:
            from button_system import get_button_text
            from database import get_product
            from utils import html_strip_tags, is_html_value
            saved = get_button_text(key, "") or "🛒 Buy Now"
            p = get_product(int(key[7:]))
            pname = p["name"] if p else ""
            # Strip [[HTML]] / <tg-emoji> garbage from product name preview
            if is_html_value(pname):
                pname = html_strip_tags(pname)
            if pname:
                return f"{saved}  ·  ({pname[:20]})"
            return saved
        except Exception:
            pass
        return "🛒 Buy Now (Free Claim)"

    # Static dynamic keys
    samples = {
        "shop_product":     "🛍️ Sample Product — $9.99",
        "shop_pagination":  "Next ➡️",
        "shop_home":        "🏠 Home",
        "shop_buy_points":  "💎 Buy Points",
        "shop_view_all":    "📋 View All Products",
        "shop_category":    "📂 Category Name (5/10)",
        "shop_back_cats":   "🔙 Categories",
        "prod_buy":         "🛒 Buy Now",
        "prod_buyx":        "🛒× Buy Multiple",
        "prod_review":      "⭐ View Reviews",
        "prod_back_shop":   "🔙 Back to Shop",
        "prod_home":        "🏠 Home",
        "cnav_prev":        "⬅️ Prev",
        "cnav_next":        "Next ➡️",
        "cnav_buy":         "🛒 Buy Now",
        "cnav_list":        "📋 List View",
        "admin_order_row":  "🟡 #123 Sample Product",
        "pay_method":       "💳 EasyPaisa",
        "custom_default":   "🎨 My Custom Button",
        "custom_submenu":   "📂 Submenu Item",
        "back_btn":         "🔙 Back",
        "home_btn":         "🏠 Home",
    }
    return samples.get(key, key)


def _back_target_for_key(key):
    """Decide which group this key belongs to for a smarter Back button."""
    try:
        groups = get_grouped_keys()
        for group_name, items in groups.items():
            if any(k == key for k, _ in items):
                return _safe_group_id(group_name)
    except Exception:
        pass
    return None


def _custom_return_target(c, key):
    """If styler was opened from a custom-button manage screen, return there.
    🆕 v49: Also honor explicit bs_return_cb for per-product editor (fc_btn_*).
    """
    try:
        # v49: explicit callback target wins (set by Free-Claim button editor)
        explicit = c.user_data.get('bs_return_cb')
        if explicit:
            return explicit
        if key.startswith('custom_'):
            return c.user_data.get('bs_return')
    except Exception:
        pass
    return None


async def _show_editor(q, key, c=None):
    s = get_style(key)
    friendly = _friendly_for(key)
    sample = _sample_label_for(key)
    styled = style_label(key, sample)

    kb = []

    # ── Size row ──
    size_row1, size_row2 = [], []
    for sz, lbl in (("auto", "Auto"), ("small", "S"), ("medium", "M"),
                    ("large", "L"), ("xl", "XL"), ("full", "Full")):
        mark = " ✅" if s["size"] == sz else ""
        btn = InlineKeyboardButton(f"{lbl}{mark}", callback_data=f"bs_size_{key}_{sz}")
        if sz in ("auto", "small", "medium"):
            size_row1.append(btn)
        else:
            size_row2.append(btn)
    kb.append([InlineKeyboardButton("📏 Size", callback_data="bs_noop")])
    kb.append(size_row1)
    kb.append(size_row2)

    # ── Alignment row ──
    kb.append([InlineKeyboardButton("↔️ Alignment", callback_data="bs_noop")])
    align_row = []
    for al, lbl in (("auto", "Auto"), ("left", "⇤ Left"),
                    ("center", "↔ Center"), ("right", "Right ⇥")):
        mark = " ✅" if s["align"] == al else ""
        align_row.append(InlineKeyboardButton(f"{lbl}{mark}", callback_data=f"bs_align_{key}_{al}"))
    # split into 2 rows of 2
    kb.append(align_row[:2])
    kb.append(align_row[2:])

    # ── Padding row ──
    kb.append([InlineKeyboardButton(f"📐 Extra Padding: {s['pad']}", callback_data="bs_noop")])
    kb.append([
        InlineKeyboardButton("➖ 5", callback_data=f"bs_pad_{key}_-5"),
        InlineKeyboardButton("🧹 0", callback_data=f"bs_pad_{key}_0"),
        InlineKeyboardButton("➕ 5", callback_data=f"bs_pad_{key}_5"),
    ])
    kb.append([
        InlineKeyboardButton("➕ 10", callback_data=f"bs_pad_{key}_10"),
        InlineKeyboardButton("➕ 20", callback_data=f"bs_pad_{key}_20"),
        InlineKeyboardButton(f"MAX ({MAX_PAD})", callback_data=f"bs_pad_{key}_max"),
    ])

    # ── Preview ──
    kb.append([InlineKeyboardButton("👁️ LIVE PREVIEW", callback_data=f"bs_preview_{key}")])

    # ── Reset / back ──
    kb.append([InlineKeyboardButton("♻️ Reset this button", callback_data=f"bs_reset_{key}")])
    # Smart back: return to the group this button belongs to
    custom_return = _custom_return_target(c, key) if c else None
    sid = _back_target_for_key(key)
    if custom_return:
        # 🆕 v49: cleaner label for any per-feature host (Free Claim button, custom btn, etc.)
        back_label = "🔙 Back"
        if key.startswith("fc_btn_"):
            back_label = "🔙 Back to Button Editor"
        elif key.startswith("custom_"):
            back_label = "🔙 Back to Custom Button"
        kb.append([
            InlineKeyboardButton(back_label, callback_data=custom_return),
            InlineKeyboardButton("🏠 All Groups", callback_data="bs_panel"),
        ])
    elif sid:
        kb.append([
            InlineKeyboardButton("🔙 Back to Group", callback_data=f"bs_grp_{sid}"),
            InlineKeyboardButton("🏠 All Groups", callback_data="bs_panel"),
        ])
    else:
        kb.append([InlineKeyboardButton("🔙 Back to Groups", callback_data="bs_panel")])

    text = (
        f"🎨 *Editing:* `{friendly}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔑 *Key:* `{key}`\n"
        f"📋 *Sample:* {sample}\n"
        f"🪟 *Current preview:* `[{styled}]`\n\n"
        f"⚙️ *Current style:*\n"
        f"   • Size: `{s['size']}`\n"
        f"   • Align: `{s['align']}`\n"
        f"   • Pad: `{s['pad']}`\n\n"
        "_Changes apply immediately. Tap '👁️ LIVE PREVIEW' "
        "to see an actual button below the message._"
    )
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════════════════════
# SETTERS
# ════════════════════════════════════════════════════════════
async def bs_size_callback(u, c):
    q = u.callback_query
    if not _admin_only(q):
        await q.answer("❌", show_alert=True); return
    # bs_size_<key>_<size>   — key may contain underscores
    raw = q.data[len("bs_size_"):]
    # last segment = size
    idx = raw.rfind("_")
    key, size = raw[:idx], raw[idx+1:]
    if size not in SIZES:
        await q.answer("❌ Invalid size", show_alert=True); return
    set_style(key, size=size)
    await q.answer(f"✅ Size set: {size}")
    await _show_editor(q, key, c)


async def bs_align_callback(u, c):
    q = u.callback_query
    if not _admin_only(q):
        await q.answer("❌", show_alert=True); return
    raw = q.data[len("bs_align_"):]
    idx = raw.rfind("_")
    key, align = raw[:idx], raw[idx+1:]
    if align not in ALIGNS:
        await q.answer("❌ Invalid align", show_alert=True); return
    set_style(key, align=align)
    await q.answer(f"✅ Align: {align}")
    await _show_editor(q, key, c)


async def bs_pad_callback(u, c):
    q = u.callback_query
    if not _admin_only(q):
        await q.answer("❌", show_alert=True); return
    raw = q.data[len("bs_pad_"):]
    idx = raw.rfind("_")
    key, delta_s = raw[:idx], raw[idx+1:]
    current = get_style(key)["pad"]
    if delta_s == "max":
        new_pad = MAX_PAD
    elif delta_s == "0":
        new_pad = 0
    else:
        try:
            new_pad = current + int(delta_s)
        except ValueError:
            await q.answer("❌", show_alert=True); return
    new_pad = max(0, min(MAX_PAD, new_pad))
    set_style(key, pad=new_pad)
    await q.answer(f"📐 Pad: {new_pad}")
    await _show_editor(q, key, c)


async def bs_reset_callback(u, c):
    q = u.callback_query
    if not _admin_only(q):
        await q.answer("❌", show_alert=True); return
    key = q.data[len("bs_reset_"):]
    reset_style(key)
    await q.answer("♻️ Reset to default")
    await _show_editor(q, key, c)


# ════════════════════════════════════════════════════════════
# LIVE PREVIEW — sends a fresh message with the styled button
# ════════════════════════════════════════════════════════════
async def bs_preview_callback(u, c):
    q = u.callback_query
    if not _admin_only(q):
        await q.answer("❌", show_alert=True); return
    await q.answer("👁️ Sending preview…")
    key = q.data[len("bs_preview_"):]
    sample = _sample_label_for(key)
    styled = style_label(key, sample)
    s = get_style(key)
    preview_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(styled, callback_data="bs_noop")],
        [InlineKeyboardButton("🔙 Back to Editor", callback_data=f"bs_edit_{key}")],
    ])
    msg = (
        f"👁️ *Live Preview*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 `{key}`\n"
        f"📏 Size: `{s['size']}` | ↔️ Align: `{s['align']}` | 📐 Pad: `{s['pad']}`\n\n"
        f"📋 Raw: `{sample}`\n"
        f"✨ Styled: `[{styled}]`\n\n"
        "_Niche button real form mein:_"
    )
    try:
        await c.bot.send_message(q.from_user.id, msg,
                                  parse_mode="Markdown",
                                  reply_markup=preview_kb)
    except Exception:
        await q.answer("❌ Preview failed", show_alert=True)


# ════════════════════════════════════════════════════════════
# RESET ALL
# ════════════════════════════════════════════════════════════
async def bs_resetall_confirm_callback(u, c):
    q = u.callback_query
    if not _admin_only(q):
        await q.answer("❌", show_alert=True); return
    await q.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ YES — Reset all to default",
                               callback_data="bs_resetall_yes")],
        [InlineKeyboardButton("❌ NO — Cancel", callback_data="bs_panel")],
    ])
    await _safe_edit(q,
        "⚠️ *Reset ALL Button Styles?*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Yeh saari per-button size / alignment / padding settings "
        "delete kar dega. Sab buttons default behavior par wapas chale jayenge.\n\n"
        "*Yaqeen hai?*",
        parse_mode="Markdown", reply_markup=kb)


async def bs_resetall_yes_callback(u, c):
    q = u.callback_query
    if not _admin_only(q):
        await q.answer("❌", show_alert=True); return
    await q.answer("♻️ Resetting…")
    for key, _ in list_known_keys():
        reset_style(key)
    await _show_groups(q)


# ════════════════════════════════════════════════════════════
# NOOP
# ════════════════════════════════════════════════════════════
async def bs_noop_callback(u, c):
    await u.callback_query.answer()


# ════════════════════════════════════════════════════════════
# HANDLER REGISTRATION HELPER
# ════════════════════════════════════════════════════════════
def get_button_styler_handlers():
    """Return list of (pattern, callback) tuples for registration in bot.py."""
    return [
        (r"^bs_panel$",        bs_panel_callback),
        (r"^bs_grp_",          bs_group_callback),   # group drill-down
        (r"^bs_pg_\d+$",       bs_page_callback),
        (r"^bs_edit_.+$",      bs_edit_callback),
        (r"^bs_size_.+$",      bs_size_callback),
        (r"^bs_align_.+$",     bs_align_callback),
        (r"^bs_pad_.+$",       bs_pad_callback),
        (r"^bs_reset_.+$",     bs_reset_callback),
        (r"^bs_preview_.+$",   bs_preview_callback),
        (r"^bs_resetall$",     bs_resetall_confirm_callback),
        (r"^bs_resetall_yes$", bs_resetall_yes_callback),
        (r"^bs_noop$",         bs_noop_callback),
    ]


# ============================================================
# 📄 ORIGINAL FILE: handlers_button_text.py
# ============================================================

# ============================================================
# 📝 BUTTON TEXT EDITOR — Admin Handlers
# ============================================================
# Admin panel UI for editing the text/label of broadcast & fake-
# activity inline buttons (e.g. "🛒 Buy Now" → "💎 Shop Now").
#
# Callback patterns:
#   btxt_panel                → main list of editable buttons
#   btxt_edit_<key>           → ask admin for new text
#   btxt_reset_<key>          → reset one button to default
#   btxt_resetall             → confirm reset all
#   btxt_resetall_yes         → reset all
#
# ConversationHandler state: BTXT_INPUT
# ============================================================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from config import ADMIN_ID
from button_system import (
    BUTTON_KEYS, get_button_text, set_button_text,
    reset_button_text, reset_all_button_texts, get_button_state,
)

# 🐛 v95 FIX: moved to 9110 below to avoid collision with ACT_DELAY=911
# Old value retained here for grep-ability only:
# BTXT_INPUT = 911  # (COLLIDED — do not use)


def _is_admin(uid):
    return uid == ADMIN_ID


async def _safe_edit(q, text, **kwargs):
    try:
        await q.edit_message_text(text, **kwargs); return
    except Exception as e:
        if "parse" in str(e).lower() and "parse_mode" in kwargs:
            k = dict(kwargs); k.pop("parse_mode")
            try:
                await q.edit_message_text(text, **k); return
            except Exception: pass
    try:
        await q.edit_message_caption(caption=text, **kwargs); return
    except Exception: pass
    try:
        await q.message.reply_text(text, **kwargs)
    except Exception:
        k = dict(kwargs); k.pop("parse_mode", None)
        try: await q.message.reply_text(text, **k)
        except Exception: pass


# ════════════════════════════════════════════════════════════
# MAIN PANEL
# ════════════════════════════════════════════════════════════
# 🐛 v95 FIX: BTXT_INPUT was 911, collided with ui_extras.ACT_DELAY=911.
# Bumped so activity delay input can't hijack button-text edits.
BTXT_INPUT = 9110

async def btxt_panel_callback(u, c):
    q = u.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True); return
    await q.answer()

    state = get_button_state()
    customized = sum(1 for v in state.values() if v["is_custom"])
    total = len(state)

    text = (
        "📝 *Broadcast Button Text Editor*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Yaha aap fake-activity / broadcast messages ke saath jane wale "
        "inline buttons (jaise 🛒 Buy Now) ka *text aur emoji* customize "
        "kar sakte ho.\n\n"
        f"✏️ *Customized:* {customized}/{total}\n\n"
        "⚠️ *Telegram Limitation Note:*\n"
        "_Button labels mein sirf standard emojis aur text use ho sakte hain. "
        "Premium/Custom emoji button text ke andar Telegram support hi nahi "
        "karta (sirf message body mein ja sakti hai). Yeh editor standard "
        "emojis ke liye hai._\n\n"
        "👇 Edit karne ke liye button choose karein:"
    )

    kb = []
    for key, default, friendly, where in BUTTON_KEYS:
        current = get_button_text(key, default)
        is_custom = current != default
        mark = "✏️" if is_custom else "▫️"
        # Show current text in brackets (truncated)
        preview = current[:20] + ("…" if len(current) > 20 else "")
        kb.append([InlineKeyboardButton(
            f"{mark} {friendly[:30]}  [{preview}]",
            callback_data=f"btxt_edit_{key}"
        )])

    kb.append([InlineKeyboardButton("♻️ Reset ALL to default", callback_data="btxt_resetall")])
    kb.append([InlineKeyboardButton("🔙 Back to Customization", callback_data="admin_customization")])

    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))


# ════════════════════════════════════════════════════════════
# EDIT ONE BUTTON
# ════════════════════════════════════════════════════════════
async def btxt_edit_callback(u, c):
    q = u.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return ConversationHandler.END
    await q.answer()

    key = q.data[len("btxt_edit_"):]
    # Find registry entry
    entry = next((e for e in BUTTON_KEYS if e[0] == key), None)
    if not entry:
        await q.answer("❌ Unknown button", show_alert=True)
        return ConversationHandler.END

    _, default, friendly, where = entry
    current = get_button_text(key, default)

    c.user_data["btxt_edit_key"] = key

    text = (
        f"✏️ *Edit Button Text*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📍 *Where used:* {where}\n"
        f"🏷️ *Friendly name:* {friendly}\n\n"
        f"*Current label:* `{current}`\n"
        f"*Default label:* `{default}`\n\n"
        f"📝 Send the new button text now.\n"
        f"_Use standard emojis (😀) from your keyboard._\n"
        f"_Keep it short — Telegram clips long button labels._\n\n"
        f"Send `-` to reset to default and exit.\n"
        f"Send /cancel to cancel."
    )
    kb = [
        [InlineKeyboardButton("♻️ Reset to default", callback_data=f"btxt_reset_{key}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="btxt_panel")],
    ]
    await _safe_edit(q, text, parse_mode="Markdown",
                     reply_markup=InlineKeyboardMarkup(kb))
    return BTXT_INPUT


async def btxt_input_received(u, c):
    """Save the new button text the admin typed."""
    if not _is_admin(u.effective_user.id):
        return ConversationHandler.END

    key = c.user_data.get("btxt_edit_key")
    if not key:
        return ConversationHandler.END

    entry = next((e for e in BUTTON_KEYS if e[0] == key), None)
    if not entry:
        return ConversationHandler.END
    _, default, friendly, _ = entry

    new_text = (u.message.text or "").strip()

    if new_text == "-" or new_text.lower() == "reset":
        reset_button_text(key)
        await u.message.reply_text(
            f"♻️ *{friendly}* reset to default:\n`{default}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to List", callback_data="btxt_panel")
            ]]),
        )
        c.user_data.pop("btxt_edit_key", None)
        return ConversationHandler.END

    # Length safety — Telegram allows up to 64 chars for button text
    if len(new_text) > 64:
        await u.message.reply_text(
            "⚠️ Button text 64 chars se zyada nahi ho sakta. Phir try karein:",
        )
        return BTXT_INPUT

    if not new_text:
        await u.message.reply_text("⚠️ Khali text save nahi ho sakti. Phir try karein:")
        return BTXT_INPUT

    set_button_text(key, new_text)

    await u.message.reply_text(
        f"✅ *Button text saved!*\n\n"
        f"🏷️ {friendly}\n"
        f"📝 New label: `{new_text}`\n\n"
        f"_Ab har broadcast/fake-activity message mein yeh naya text use hoga._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to List", callback_data="btxt_panel")
        ]]),
    )
    c.user_data.pop("btxt_edit_key", None)
    return ConversationHandler.END


async def btxt_input_cancel(u, c):
    c.user_data.pop("btxt_edit_key", None)
    await u.message.reply_text(
        "❌ Cancelled.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to List", callback_data="btxt_panel")
        ]]),
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════
# RESET ONE
# ════════════════════════════════════════════════════════════
async def btxt_reset_callback(u, c):
    q = u.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True); return
    key = q.data[len("btxt_reset_"):]
    reset_button_text(key)
    await q.answer("♻️ Reset to default!")
    # Re-show the panel
    await btxt_panel_callback(u, c)


# ════════════════════════════════════════════════════════════
# RESET ALL
# ════════════════════════════════════════════════════════════
async def btxt_resetall_callback(u, c):
    q = u.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True); return
    await q.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ YES — reset ALL button texts", callback_data="btxt_resetall_yes")],
        [InlineKeyboardButton("❌ NO — cancel", callback_data="btxt_panel")],
    ])
    await _safe_edit(q,
        "⚠️ *Reset ALL Button Texts?*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Yeh saari button text customizations delete kar dega aur har "
        "broadcast/activity button apne default text par wapas chala jayega.\n\n"
        "*Yaqeen hai?*",
        parse_mode="Markdown", reply_markup=kb,
    )


async def btxt_resetall_yes_callback(u, c):
    q = u.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True); return
    reset_all_button_texts()
    await q.answer("♻️ All button texts reset!")
    await btxt_panel_callback(u, c)


# ════════════════════════════════════════════════════════════
# REGISTRATION HELPER
# ════════════════════════════════════════════════════════════
def get_button_text_handlers():
    """Return list of (pattern, callback) for CallbackQueryHandler registration."""
    return [
        (r"^btxt_panel$",        btxt_panel_callback),
        (r"^btxt_reset_[^y].*$", btxt_reset_callback),  # exclude resetall
        (r"^btxt_resetall$",     btxt_resetall_callback),
        (r"^btxt_resetall_yes$", btxt_resetall_yes_callback),
    ]


# ============================================================
# 📄 ORIGINAL FILE: handlers_custom_actions.py
# ============================================================

# ============================================
# 🎯 CUSTOM BUTTON ACTION EXECUTORS (v38)
# ============================================
# When a user clicks a custom button, the right action runs from here.
# Each action type has its own executor function.
# ============================================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote

from config import ADMIN_ID
from database import get_custom_button, get_product
from button_system import get_nav_target
from utils import escape_md, set_cb_data, location_back_callback


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

def _back_btn(parent="main_menu"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=parent)]])


def _parent_cb_for_button(b):
    try:
        return location_back_callback((dict(b) if b else {}).get('location', 'main'))
    except Exception:
        return 'main_menu'


# ════════════════════════════════════════════════════════════════
# UNIFIED EXECUTOR
# ════════════════════════════════════════════════════════════════
# All custom button clicks (except submenu/page/url which are special)
# go through callback pattern: cbact_<bid>
# This single callback reads the button's btype + action and dispatches.

async def custom_button_action_callback(update, context):
    """Master executor for ALL action-based custom buttons."""
    q = update.callback_query
    try:
        bid = int(q.data.split("_", 1)[1])
    except (ValueError, IndexError):
        await q.answer("❌ Invalid", show_alert=True); return

    b = get_custom_button(bid)
    if not b or not b['is_active']:
        await q.answer("❌ Button not available", show_alert=True); return

    btype = b['btype']
    action_val = b['action'] or ""

    # ── Dispatch ──
    handler = ACTION_HANDLERS.get(btype)
    if handler:
        await handler(update, context, b, action_val)
    else:
        # Unknown type
        await q.answer(f"❌ Unsupported action: {btype}", show_alert=True)


# ════════════════════════════════════════════════════════════════
# INDIVIDUAL ACTION HANDLERS
# ════════════════════════════════════════════════════════════════

async def _act_text(update, context, b, val):
    """Show a text message."""
    q = update.callback_query
    await q.answer()
    text = val or "(no message set)"
    parent_cb = _parent_cb_for_button(b)
    try:
        await _safe_edit(q, text, parse_mode="Markdown", reply_markup=_back_btn(parent_cb))
    except Exception:
        try:
            await _safe_edit(q, text, reply_markup=_back_btn(parent_cb))
        except Exception:
            await context.bot.send_message(q.from_user.id, text, reply_markup=_back_btn(parent_cb))


async def _act_nav(update, context, b, val):
    """Navigate to a built-in screen by simulating a callback."""
    q = update.callback_query
    target = get_nav_target(val)
    if not target:
        await q.answer("❌ Invalid navigation target", show_alert=True); return
    # Rewrite the callback data and dispatch
    new_cb = target['callback']
    # Modify the callback_query data so downstream handler picks it up
    set_cb_data(update, new_cb)
    # Route to the corresponding handler
    from handlers_start import (
        main_menu_callback, my_account_callback,
        referral_callback, buy_points_callback, transactions_callback,
        admin_panel_callback, go_back_callback
    )
    from handlers_shop import shop_callback
    from handlers_order import my_orders_callback
    from handlers_support import support_menu_callback, warranty_menu_callback
    from handlers_reviews import reviews_menu_callback
    from loyalty_extras import loyalty_callback
    from ui_extras import language_menu_callback

    routes = {
        "main_menu": main_menu_callback,
        "shop": shop_callback,
        "my_account": my_account_callback,
        "my_orders": my_orders_callback,
        "buy_points": buy_points_callback,
        "transactions": transactions_callback,
        "referral": referral_callback,
        "support_menu": support_menu_callback,
        "warranty_menu": warranty_menu_callback,
        "reviews_menu": reviews_menu_callback,
        "loyalty_menu": loyalty_callback,
        "language_menu": language_menu_callback,
        "admin_panel": admin_panel_callback,
        "go_back": go_back_callback,
    }
    fn = routes.get(new_cb)
    if fn:
        await fn(update, context)
    else:
        await q.answer(f"❌ Route not found: {new_cb}", show_alert=True)


async def _act_buy_product(update, context, b, val):
    """Direct buy: simulate clicking the 'Buy' button on a product."""
    q = update.callback_query
    try:
        pid = int(val)
    except ValueError:
        await q.answer("❌ Invalid product ID", show_alert=True); return
    p = get_product(pid)
    if not p or not p['is_active']:
        await q.answer("❌ Product not available", show_alert=True); return
    # Simulate buy_<pid> callback
    set_cb_data(update, f"buy_{pid}")
    from handlers_order import buy_callback
    await buy_callback(update, context)


async def _act_buy_points_amount(update, context, b, val):
    """Direct points purchase with preset amount."""
    q = update.callback_query
    try:
        amt = int(val)
    except ValueError:
        await q.answer("❌ Invalid amount", show_alert=True); return
    set_cb_data(update, f"pts_{amt}")
    from handlers_order import points_amount_callback
    await points_amount_callback(update, context)


async def _act_whatsapp(update, context, b, val):
    """Open WhatsApp chat — uses URL button."""
    q = update.callback_query
    await q.answer()
    digits = "".join(c for c in val if c.isdigit())
    url = f"https://wa.me/{digits}"
    text = "📱 *WhatsApp Contact*\n━━━━━━━━━━━━━━━━━━━━\n\nTap below to chat on WhatsApp:"
    parent_cb = _parent_cb_for_button(b)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💬 Open WhatsApp (+{digits})", url=url)],
        [InlineKeyboardButton("🔙 Back", callback_data=parent_cb)],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def _act_email(update, context, b, val):
    """Open email composer."""
    q = update.callback_query
    await q.answer()
    url = f"mailto:{val}"
    text = f"📧 *Email Contact*\n━━━━━━━━━━━━━━━━━━━━\n\n`{val}`\n\nTap below to compose email:"
    parent_cb = _parent_cb_for_button(b)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📧 Send Email", url=url)],
        [InlineKeyboardButton("🔙 Back", callback_data=parent_cb)],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def _act_telegram_chat(update, context, b, val):
    """Open another Telegram chat."""
    q = update.callback_query
    await q.answer()
    uname = val.lstrip("@")
    url = f"https://t.me/{uname}"
    text = f"💬 *Open Telegram Chat*\n━━━━━━━━━━━━━━━━━━━━\n\n@{uname}"
    parent_cb = _parent_cb_for_button(b)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💬 Open @{uname}", url=url)],
        [InlineKeyboardButton("🔙 Back", callback_data=parent_cb)],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def _act_phone_call(update, context, b, val):
    q = update.callback_query
    await q.answer()
    digits = "".join(c for c in val if c.isdigit() or c == "+")
    if not digits.startswith("+"):
        digits = "+" + digits
    url = f"tel:{digits}"
    text = f"☎️ *Phone Call*\n━━━━━━━━━━━━━━━━━━━━\n\n`{digits}`"
    parent_cb = _parent_cb_for_button(b)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"☎️ Call {digits}", url=url)],
        [InlineKeyboardButton("🔙 Back", callback_data=parent_cb)],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def _act_alert(update, context, b, val):
    """Show a popup toast — no screen change."""
    q = update.callback_query
    text = (val or "")[:200]
    await q.answer(text, show_alert=True)


async def _act_copy(update, context, b, val):
    """'Copy to clipboard' — Telegram doesn't have native copy, so show in alert
    + as a code-formatted message so user can long-press to copy."""
    q = update.callback_query
    await q.answer(f"📋 Copy this:\n\n{val[:150]}", show_alert=True)
    parent_cb = _parent_cb_for_button(b)
    # Also send as code block message for easy copy
    try:
        await context.bot.send_message(
            q.from_user.id,
            f"📋 *Copy & paste this:*\n\n`{val}`\n\n_(Tap to select)_",
            parse_mode="Markdown",
            reply_markup=_back_btn(parent_cb)
        )
    except Exception:
        pass


async def _act_share_bot(update, context, b, val):
    """Generate referral link + share button."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={uid}"
    share_url = f"https://t.me/share/url?url={quote(ref_link)}&text={quote('🛍️ Check out this amazing shop!')}"
    parent_cb = _parent_cb_for_button(b)

    text = (f"📤 *Share Bot*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Your referral link:\n`{ref_link}`\n\n"
            f"_Tap to copy, or share using the button below_")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Share Now", url=share_url)],
        [InlineKeyboardButton("🔙 Back", callback_data=parent_cb)],
    ])
    await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def _act_send_photo(update, context, b, val):
    """Send a stored photo (val = file_id)."""
    q = update.callback_query
    await q.answer("📸 Sending...")
    parent_cb = _parent_cb_for_button(b)
    try:
        await context.bot.send_photo(q.from_user.id, photo=val, caption=b['label'],
                                       reply_markup=_back_btn(parent_cb))
    except Exception as e:
        await q.answer(f"❌ Failed: {str(e)[:100]}", show_alert=True)


async def _act_send_video(update, context, b, val):
    q = update.callback_query
    await q.answer("🎬 Sending...")
    parent_cb = _parent_cb_for_button(b)
    try:
        await context.bot.send_video(q.from_user.id, video=val, caption=b['label'],
                                       reply_markup=_back_btn(parent_cb))
    except Exception as e:
        await q.answer(f"❌ Failed: {str(e)[:100]}", show_alert=True)


async def _act_send_document(update, context, b, val):
    q = update.callback_query
    await q.answer("📎 Sending...")
    parent_cb = _parent_cb_for_button(b)
    try:
        await context.bot.send_document(q.from_user.id, document=val, caption=b['label'],
                                          reply_markup=_back_btn(parent_cb))
    except Exception as e:
        await q.answer(f"❌ Failed: {str(e)[:100]}", show_alert=True)


async def _act_send_audio(update, context, b, val):
    q = update.callback_query
    await q.answer("🎵 Sending...")
    parent_cb = _parent_cb_for_button(b)
    try:
        await context.bot.send_audio(q.from_user.id, audio=val, caption=b['label'],
                                       reply_markup=_back_btn(parent_cb))
    except Exception as e:
        # Maybe it's a voice message
        try:
            await context.bot.send_voice(q.from_user.id, voice=val,
                                           reply_markup=_back_btn(parent_cb))
        except Exception:
            await q.answer(f"❌ Failed: {str(e)[:100]}", show_alert=True)


async def _act_webapp(update, context, b, val):
    """Open Telegram Mini App."""
    from telegram import WebAppInfo
    q = update.callback_query
    await q.answer()
    text = f"🌐 *{escape_md(b['label'])}*\n━━━━━━━━━━━━━━━━━━━━\n\nTap below to open Mini App:"
    parent_cb = _parent_cb_for_button(b)
    try:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Open App", web_app=WebAppInfo(url=val))],
            [InlineKeyboardButton("🔙 Back", callback_data=parent_cb)],
        ])
        await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        # Fallback to URL button
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Open", url=val)],
            [InlineKeyboardButton("🔙 Back", callback_data=parent_cb)],
        ])
        await _safe_edit(q, text, parse_mode="Markdown", reply_markup=kb)


async def _act_command(update, context, b, val):
    """Execute a bot command shortcut (/start or /admin).

    🔧 v39 FIX: Can't reassign update.message (frozen). Instead, we directly
    invoke the equivalent flow as callbacks. /start → show welcome via main_menu_callback,
    /admin → check admin & show admin_panel_callback.
    """
    q = update.callback_query
    await q.answer()
    cmd = val.strip().lstrip("/").lower()

    if cmd == "start":
        # /start ka end-result: welcome screen + main menu
        from handlers_start import main_menu_callback
        await main_menu_callback(update, context)
    elif cmd == "admin":
        if q.from_user.id != ADMIN_ID:
            await q.answer("❌ Admin only", show_alert=True)
            return
        from handlers_start import admin_panel_callback
        await admin_panel_callback(update, context)
    else:
        await q.answer(f"❌ Unsupported command: /{cmd}", show_alert=True)


# ── Dispatcher map ──
ACTION_HANDLERS = {
    "text":               _act_text,
    "nav":                _act_nav,
    "buy_product":        _act_buy_product,
    "buy_points_amount":  _act_buy_points_amount,
    "whatsapp":           _act_whatsapp,
    "email":              _act_email,
    "telegram_chat":      _act_telegram_chat,
    "phone_call":         _act_phone_call,
    "alert":              _act_alert,
    "copy":               _act_copy,
    "share_bot":          _act_share_bot,
    "send_photo":         _act_send_photo,
    "send_video":         _act_send_video,
    "send_document":      _act_send_document,
    "send_audio":         _act_send_audio,
    "webapp":             _act_webapp,
    "command":            _act_command,
}


# ============================================================
# 📄 ORIGINAL FILE: handlers_product_design.py
# ============================================================

# ============================================================
# 🎨 PRODUCT DISPLAY DESIGN SYSTEM — handlers_product_design.py
# ============================================================
#
# Admin Panel → 🎨 Customization → 🛍️ Product Design
#
# WHAT THIS DOES:
# ───────────────
# Lets admin fully customize how products look in the shop.
# ALL changes show a LIVE PREVIEW right inside the panel.
#
# CUSTOMIZATION OPTIONS:
# ──────────────────────
#   📐 Layout:
#       • Compact    — name + price in one short line
#       • Standard   — name, price, stock on separate lines  (default)
#       • Detailed   — full info: name, desc, price, stock, warranty
#       • Card       — boxed card style with decorative borders
#
#   📏 Button Size:
#       • Small  — emoji only (🛒)
#       • Medium — emoji + short text (🛒 Buy)
#       • Large  — emoji + full text (🛒 Buy Now)
#       • XL     — full descriptive text
#
#   🎨 Style / Theme:
#       • Classic   — clean, minimal
#       • Bold      — uppercase, strong
#       • Fancy     — decorative borders ◆ ═══
#       • Minimal   — text only, no emojis
#       • Neon      — bright emojis, energetic
#
#   📊 Info Fields (toggle each):
#       • Show/hide price
#       • Show/hide stock count
#       • Show/hide description
#       • Show/hide warranty
#       • Show/hide PKR equivalent
#
#   🔢 Products per page: 5 / 8 / 10 / 15
#
# HOW TO REGISTER IN bot.py:
# ────────────────────────────
#   from handlers_product_design import (
#       product_design_panel_callback,
#       pd_layout_callback,
#       pd_style_callback,
#       pd_field_toggle_callback,
#       pd_perpage_callback,
#       pd_btnsize_callback,
#       pd_reset_callback,
#   )
#   app.add_handler(CallbackQueryHandler(product_design_panel_callback, pattern="^pd_panel$"))
#   app.add_handler(CallbackQueryHandler(pd_layout_callback,     pattern="^pd_layout_"))
#   app.add_handler(CallbackQueryHandler(pd_style_callback,      pattern="^pd_style_"))
#   app.add_handler(CallbackQueryHandler(pd_field_toggle_callback,pattern="^pd_field_"))
#   app.add_handler(CallbackQueryHandler(pd_perpage_callback,    pattern="^pd_perpage_"))
#   app.add_handler(CallbackQueryHandler(pd_btnsize_callback,    pattern="^pd_btnsize_"))
#   app.add_handler(CallbackQueryHandler(pd_reset_callback,      pattern="^pd_reset$"))
#
# ADD BUTTON IN keyboards.py admin_menu_keyboard():
#   kb.append([InlineKeyboardButton("🛍️ Product Design", callback_data="pd_panel")])
#
# ──────────────────────────────────────────────────────────────

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# ⚙️ SETTINGS KEYS
# ════════════════════════════════════════════════════════════════

S_LAYOUT   = "pd_layout"      # compact / standard / detailed / card
S_STYLE    = "pd_style"       # classic / bold / fancy / minimal / neon
S_BTNSIZE  = "pd_btnsize"     # small / medium / large / xl
S_PERPAGE  = "pd_perpage"     # 5 / 8 / 10 / 15
S_SHOW_PRICE  = "pd_show_price"    # 1/0
S_SHOW_STOCK  = "pd_show_stock"    # 1/0
S_SHOW_DESC   = "pd_show_desc"     # 1/0
S_SHOW_WARRANTY = "pd_show_warranty"  # 1/0
S_SHOW_PKR    = "pd_show_pkr"      # 1/0


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


def _is_admin(uid):
    from config import ADMIN_ID
    return uid == ADMIN_ID


def _ico(val, default="1"):
    return "✅" if _g(val, default) == "1" else "❌"


# ════════════════════════════════════════════════════════════════
# 🖼️ LIVE PREVIEW GENERATOR
# ════════════════════════════════════════════════════════════════

LAYOUT_NAMES = {
    "compact":  "📦 Compact",
    "standard": "📋 Standard",
    "detailed": "📄 Detailed",
    "card":     "🃏 Card",
}

STYLE_NAMES = {
    "classic": "🎯 Classic",
    "bold":    "💪 Bold",
    "fancy":   "✨ Fancy",
    "minimal": "🔲 Minimal",
    "neon":    "⚡ Neon",
}

BTNSIZE_NAMES = {
    "small":  "🔹 Small (emoji only)",
    "medium": "▪️ Medium (emoji + text)",
    "large":  "🔷 Large (full label)",
    "xl":     "🔶 XL (descriptive)",
}


def generate_preview(layout=None, style=None, btnsize=None):
    """
    Generate a live preview of how a product will look.
    Uses current settings if parameters not given.
    """
    layout  = layout  or _g(S_LAYOUT,  "standard")
    style   = style   or _g(S_STYLE,   "classic")
    btnsize = btnsize or _g(S_BTNSIZE, "medium")

    show_price   = _g(S_SHOW_PRICE,   "1") == "1"
    show_stock   = _g(S_SHOW_STOCK,   "1") == "1"
    show_desc    = _g(S_SHOW_DESC,    "1") == "1"
    show_warranty= _g(S_SHOW_WARRANTY,"1") == "1"
    show_pkr     = _g(S_SHOW_PKR,     "1") == "1"

    # Sample product data
    name      = "ChatGPT Plus 1 Month"
    desc      = "Original ChatGPT Plus subscription"
    price     = 5.00
    pkr       = int(price * 280)
    stock     = 8
    warranty  = "30 days"

    # ── Apply style to name ──
    if style == "bold":
        display_name = f"*{name.upper()}*"
    elif style == "fancy":
        display_name = f"✦ *{name}* ✦"
    elif style == "minimal":
        display_name = name
    elif style == "neon":
        display_name = f"⚡ *{name}* ⚡"
    else:  # classic
        display_name = f"*{name}*"

    # ── Build product card by layout ──
    if layout == "compact":
        line = display_name
        if show_price:
            line += f"  💰 ${price:.2f}"
            if show_pkr:
                line += f" ≈ Rs.{pkr}"
        if show_stock:
            line += f"  📦 {stock}"
        preview = line

    elif layout == "detailed":
        lines = [display_name]
        if show_desc:
            lines.append(f"_{desc}_")
        lines.append("─────────────────")
        if show_price:
            pkr_str = f" ≈ *Rs.{pkr}*" if show_pkr else ""
            lines.append(f"💰 Price: *${price:.2f}*{pkr_str}")
        if show_stock:
            lines.append(f"📦 In Stock: *{stock}*")
        if show_warranty:
            lines.append(f"🛡️ Warranty: {warranty}")
        lines.append("─────────────────")
        preview = "\n".join(lines)

    elif layout == "card":
        sep = "━━━━━━━━━━━━━━━━"
        lines = [sep, display_name, sep]
        if show_desc:
            lines.append(f"_{desc}_")
        if show_price:
            pkr_str = f"\n   ≈ *Rs.{pkr}*" if show_pkr else ""
            lines.append(f"💰 *${price:.2f}*{pkr_str}")
        if show_stock:
            color = "🟢" if stock > 5 else "🟡" if stock > 0 else "🔴"
            lines.append(f"{color} Stock: *{stock}*")
        if show_warranty:
            lines.append(f"🛡️ {warranty}")
        lines.append(sep)
        preview = "\n".join(lines)

    else:  # standard (default)
        lines = [display_name]
        if show_desc:
            lines.append(f"_{desc}_")
        if show_price:
            pkr_str = f" ≈ Rs.{pkr}" if show_pkr else ""
            lines.append(f"💰 ${price:.2f}{pkr_str}")
        if show_stock:
            lines.append(f"📦 Stock: {stock}")
        if show_warranty:
            lines.append(f"🛡️ {warranty}")
        preview = "\n".join(lines)

    # ── Button label by size ──
    btn_labels = {
        "small":  "🛒",
        "medium": "🛒 Buy",
        "large":  "🛒 Buy Now",
        "xl":     "🛒 Buy Now — Order this item",
    }
    btn_label = btn_labels.get(btnsize, "🛒 Buy")

    return preview, btn_label


# ════════════════════════════════════════════════════════════════
# 🏠 MAIN PANEL
# ════════════════════════════════════════════════════════════════

async def product_design_panel_callback(update, context):
    """
    Main Product Design panel.
    Access: Admin Panel → 🛍️ Product Design
    Shows current settings + LIVE PREVIEW.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return
    await q.answer()
    await _show_panel(q)


async def _show_panel(q):
    """Build and show the full design panel with live preview."""
    layout  = _g(S_LAYOUT,  "standard")
    style   = _g(S_STYLE,   "classic")
    btnsize = _g(S_BTNSIZE, "medium")
    perpage = _g(S_PERPAGE, "8")

    preview_text, btn_label = generate_preview(layout, style, btnsize)

    text = (
        f"🛍️ *Product Display Design*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Current Settings:*\n"
        f"  📐 Layout: `{LAYOUT_NAMES.get(layout, layout)}`\n"
        f"  🎨 Style:  `{STYLE_NAMES.get(style, style)}`\n"
        f"  📏 Button: `{BTNSIZE_NAMES.get(btnsize, btnsize)}`\n"
        f"  🔢 Per Page: `{perpage} products`\n\n"
        f"*Info Fields:*\n"
        f"  {_ico(S_SHOW_PRICE)} Price  "
        f"  {_ico(S_SHOW_STOCK)} Stock  "
        f"  {_ico(S_SHOW_DESC)} Description\n"
        f"  {_ico(S_SHOW_WARRANTY)} Warranty  "
        f"  {_ico(S_SHOW_PKR)} PKR Price\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👁️ *LIVE PREVIEW:*\n\n"
        f"{preview_text}\n\n"
        f"  [ {btn_label} ]\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = [
        # ── LAYOUT ──
        [InlineKeyboardButton("━━━ 📐 Layout ━━━", callback_data="pd_noop")],
        [
            InlineKeyboardButton(f"{'✅' if layout=='compact'  else '▫️'} Compact",  callback_data="pd_layout_compact"),
            InlineKeyboardButton(f"{'✅' if layout=='standard' else '▫️'} Standard", callback_data="pd_layout_standard"),
        ],
        [
            InlineKeyboardButton(f"{'✅' if layout=='detailed' else '▫️'} Detailed", callback_data="pd_layout_detailed"),
            InlineKeyboardButton(f"{'✅' if layout=='card'     else '▫️'} Card",     callback_data="pd_layout_card"),
        ],
        # ── STYLE ──
        [InlineKeyboardButton("━━━ 🎨 Style / Theme ━━━", callback_data="pd_noop")],
        [
            InlineKeyboardButton(f"{'✅' if style=='classic' else '▫️'} Classic", callback_data="pd_style_classic"),
            InlineKeyboardButton(f"{'✅' if style=='bold'    else '▫️'} Bold",    callback_data="pd_style_bold"),
            InlineKeyboardButton(f"{'✅' if style=='fancy'   else '▫️'} Fancy",   callback_data="pd_style_fancy"),
        ],
        [
            InlineKeyboardButton(f"{'✅' if style=='minimal' else '▫️'} Minimal", callback_data="pd_style_minimal"),
            InlineKeyboardButton(f"{'✅' if style=='neon'    else '▫️'} Neon",    callback_data="pd_style_neon"),
        ],
        # ── BUTTON SIZE ──
        [InlineKeyboardButton("━━━ 📏 Buy Button Size ━━━", callback_data="pd_noop")],
        [
            InlineKeyboardButton(f"{'✅' if btnsize=='small'  else '▫️'} 🛒",           callback_data="pd_btnsize_small"),
            InlineKeyboardButton(f"{'✅' if btnsize=='medium' else '▫️'} 🛒 Buy",        callback_data="pd_btnsize_medium"),
        ],
        [
            InlineKeyboardButton(f"{'✅' if btnsize=='large'  else '▫️'} 🛒 Buy Now",    callback_data="pd_btnsize_large"),
            InlineKeyboardButton(f"{'✅' if btnsize=='xl'     else '▫️'} 🛒 Buy Now — Order", callback_data="pd_btnsize_xl"),
        ],
        # ── INFO FIELDS ──
        [InlineKeyboardButton("━━━ 📊 Info Fields ━━━", callback_data="pd_noop")],
        [
            InlineKeyboardButton(f"{_ico(S_SHOW_PRICE)} Price",       callback_data="pd_field_price"),
            InlineKeyboardButton(f"{_ico(S_SHOW_STOCK)} Stock",       callback_data="pd_field_stock"),
            InlineKeyboardButton(f"{_ico(S_SHOW_DESC)} Description",  callback_data="pd_field_desc"),
        ],
        [
            InlineKeyboardButton(f"{_ico(S_SHOW_WARRANTY)} Warranty", callback_data="pd_field_warranty"),
            InlineKeyboardButton(f"{_ico(S_SHOW_PKR)} PKR Price",     callback_data="pd_field_pkr"),
        ],
        # ── PER PAGE ──
        [InlineKeyboardButton("━━━ 🔢 Products Per Page ━━━", callback_data="pd_noop")],
        [
            InlineKeyboardButton(f"{'✅' if perpage=='5'  else '▫️'} 5",  callback_data="pd_perpage_5"),
            InlineKeyboardButton(f"{'✅' if perpage=='8'  else '▫️'} 8",  callback_data="pd_perpage_8"),
            InlineKeyboardButton(f"{'✅' if perpage=='10' else '▫️'} 10", callback_data="pd_perpage_10"),
            InlineKeyboardButton(f"{'✅' if perpage=='15' else '▫️'} 15", callback_data="pd_perpage_15"),
        ],
        # ── ACTIONS ──
        [InlineKeyboardButton("━━━━━━━━━━━━━━━━", callback_data="pd_noop")],
        [
            InlineKeyboardButton("🔄 Reset to Default", callback_data="pd_reset"),
            InlineKeyboardButton("🔙 Back",             callback_data="admin_customization"),
        ],
    ]

    try:
        await q.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        try:
            await q.edit_message_caption(
                caption=text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════
# 📐 LAYOUT HANDLER
# ════════════════════════════════════════════════════════════════

async def pd_layout_callback(update, context):
    """
    Set product layout.
    Callback: pd_layout_compact / pd_layout_standard / pd_layout_detailed / pd_layout_card
    Immediately shows updated preview.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return

    layout = q.data.replace("pd_layout_", "")
    _s(S_LAYOUT, layout)
    await q.answer(f"✅ Layout: {LAYOUT_NAMES.get(layout, layout)}")
    await _show_panel(q)


# ════════════════════════════════════════════════════════════════
# 🎨 STYLE HANDLER
# ════════════════════════════════════════════════════════════════

async def pd_style_callback(update, context):
    """
    Set product display style/theme.
    Callback: pd_style_classic / pd_style_bold / pd_style_fancy / pd_style_minimal / pd_style_neon
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return

    style = q.data.replace("pd_style_", "")
    _s(S_STYLE, style)
    await q.answer(f"✅ Style: {STYLE_NAMES.get(style, style)}")
    await _show_panel(q)


# ════════════════════════════════════════════════════════════════
# 📏 BUTTON SIZE HANDLER
# ════════════════════════════════════════════════════════════════

async def pd_btnsize_callback(update, context):
    """
    Set buy button size/label.
    Callback: pd_btnsize_small / pd_btnsize_medium / pd_btnsize_large / pd_btnsize_xl
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return

    size = q.data.replace("pd_btnsize_", "")
    _s(S_BTNSIZE, size)
    await q.answer(f"✅ Button: {BTNSIZE_NAMES.get(size, size)}")
    await _show_panel(q)


# ════════════════════════════════════════════════════════════════
# 📊 FIELD TOGGLE HANDLER
# ════════════════════════════════════════════════════════════════

_FIELD_MAP = {
    "price":    (S_SHOW_PRICE,   "Price"),
    "stock":    (S_SHOW_STOCK,   "Stock"),
    "desc":     (S_SHOW_DESC,    "Description"),
    "warranty": (S_SHOW_WARRANTY,"Warranty"),
    "pkr":      (S_SHOW_PKR,     "PKR Price"),
}


async def pd_field_toggle_callback(update, context):
    """
    Toggle a product info field on/off.
    Callback: pd_field_price / pd_field_stock / pd_field_desc / pd_field_warranty / pd_field_pkr
    Preview updates instantly.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return

    field = q.data.replace("pd_field_", "")
    entry = _FIELD_MAP.get(field)
    if not entry:
        await q.answer("❌ Unknown field")
        return

    setting_key, label = entry
    current = _g(setting_key, "1")
    new_val = "0" if current == "1" else "1"
    _s(setting_key, new_val)
    status = "ON ✅" if new_val == "1" else "OFF ❌"
    await q.answer(f"{label}: {status}")
    await _show_panel(q)


# ════════════════════════════════════════════════════════════════
# 🔢 PER PAGE HANDLER
# ════════════════════════════════════════════════════════════════

async def pd_perpage_callback(update, context):
    """
    Set how many products show per page.
    Callback: pd_perpage_5 / pd_perpage_8 / pd_perpage_10 / pd_perpage_15
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return

    n = q.data.replace("pd_perpage_", "")
    _s(S_PERPAGE, n)
    await q.answer(f"✅ {n} products per page")
    await _show_panel(q)


# ════════════════════════════════════════════════════════════════
# 🔄 RESET HANDLER
# ════════════════════════════════════════════════════════════════

async def pd_reset_callback(update, context):
    """
    Reset all product design settings to defaults.
    """
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer("❌ Admin only!", show_alert=True)
        return

    # Reset all to defaults
    _s(S_LAYOUT,       "standard")
    _s(S_STYLE,        "classic")
    _s(S_BTNSIZE,      "medium")
    _s(S_PERPAGE,      "8")
    _s(S_SHOW_PRICE,   "1")
    _s(S_SHOW_STOCK,   "1")
    _s(S_SHOW_DESC,    "1")
    _s(S_SHOW_WARRANTY,"1")
    _s(S_SHOW_PKR,     "1")

    await q.answer("✅ Reset to defaults!")
    await _show_panel(q)


# ════════════════════════════════════════════════════════════════
# 🔇 NOOP
# ════════════════════════════════════════════════════════════════

async def pd_noop_callback(update, context):
    """Separator button — does nothing."""
    await update.callback_query.answer()


# ════════════════════════════════════════════════════════════════
# 📦 PRODUCT FORMATTER — Used by handlers_shop.py
# ════════════════════════════════════════════════════════════════

def format_product_text(product, usd_to_pkr=280):
    """
    Format a product's display text using current design settings.

    Args:
        product: product dict or Row from DB
        usd_to_pkr: conversion rate

    Returns:
        formatted text string (Markdown)

    HOW TO USE IN handlers_shop.py:
        # [v77-merge] self-bundle import removed: from handlers_product_design import format_product_text
        text = format_product_text(product)
    """
    # Extract fields
    if isinstance(product, dict):
        name     = product.get("name", "Product")
        desc     = product.get("description", "")
        price    = float(product.get("price", 0))
        stock    = int(product.get("stock", 0))
        warranty = product.get("warranty", "") or ""
    else:
        name     = product[2]  if len(product) > 2  else "Product"
        desc     = product[3]  if len(product) > 3  else ""
        price    = float(product[4] or 0) if len(product) > 4 else 0
        stock    = int(product[6] or 0)   if len(product) > 6 else 0
        warranty = product[8]  if len(product) > 8  else ""

    pkr = int(price * usd_to_pkr)

    layout  = _g(S_LAYOUT,  "standard")
    style   = _g(S_STYLE,   "classic")

    show_price   = _g(S_SHOW_PRICE,    "1") == "1"
    show_stock   = _g(S_SHOW_STOCK,    "1") == "1"
    show_desc    = _g(S_SHOW_DESC,     "1") == "1"
    show_warranty= _g(S_SHOW_WARRANTY, "1") == "1"
    show_pkr     = _g(S_SHOW_PKR,      "1") == "1"

    # Style the name
    if style == "bold":
        dn = f"*{name.upper()}*"
    elif style == "fancy":
        dn = f"✦ *{name}* ✦"
    elif style == "minimal":
        dn = name
    elif style == "neon":
        dn = f"⚡ *{name}* ⚡"
    else:
        dn = f"*{name}*"

    pkr_str = f" ≈ Rs.{pkr}" if show_pkr else ""

    if layout == "compact":
        line = dn
        if show_price:
            line += f"  💰 ${price:.2f}{pkr_str}"
        if show_stock:
            line += f"  📦 {stock}"
        return line

    elif layout == "detailed":
        lines = [dn]
        if show_desc and desc:
            lines.append(f"_{desc}_")
        lines.append("─────────────────")
        if show_price:
            lines.append(f"💰 Price: *${price:.2f}*{pkr_str}")
        if show_stock:
            lines.append(f"📦 In Stock: *{stock}*")
        if show_warranty and warranty:
            lines.append(f"🛡️ Warranty: {warranty}")
        lines.append("─────────────────")
        return "\n".join(lines)

    elif layout == "card":
        sep = "━━━━━━━━━━━━━━━━"
        lines = [sep, dn, sep]
        if show_desc and desc:
            lines.append(f"_{desc}_")
        if show_price:
            lines.append(f"💰 *${price:.2f}*{pkr_str}")
        if show_stock:
            color = "🟢" if stock > 5 else "🟡" if stock > 0 else "🔴"
            lines.append(f"{color} Stock: *{stock}*")
        if show_warranty and warranty:
            lines.append(f"🛡️ {warranty}")
        lines.append(sep)
        return "\n".join(lines)

    else:  # standard
        lines = [dn]
        if show_desc and desc:
            lines.append(f"_{desc}_")
        if show_price:
            lines.append(f"💰 ${price:.2f}{pkr_str}")
        if show_stock:
            lines.append(f"📦 Stock: {stock}")
        if show_warranty and warranty:
            lines.append(f"🛡️ {warranty}")
        return "\n".join(lines)


def get_buy_button_label():
    """
    Returns the current buy button label based on admin's button size setting.
    Use this in shop keyboards instead of hardcoded text.
    """
    btnsize = _g(S_BTNSIZE, "medium")
    labels = {
        "small":  "🛒",
        "medium": "🛒 Buy",
        "large":  "🛒 Buy Now",
        "xl":     "🛒 Buy Now — Order this item",
    }
    return labels.get(btnsize, "🛒 Buy")


def get_products_per_page():
    """Returns how many products to show per page (int)."""
    try:
        return int(_g(S_PERPAGE, "8"))
    except Exception:
        return 8

