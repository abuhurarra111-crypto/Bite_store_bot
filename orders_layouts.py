"""
📦 ORDERS LAYOUTS - 10 Different Styles
Users ko apne orders shop jaisi style me dikhenge
"""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils import smart_text_and_mode
import re

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 🎨 10 ORDER LAYOUT TEMPLATES
# ════════════════════════════════════════════════════════════════

ORDERS_LAYOUTS = {
    # Layout 1: Classic List
    "classic": {
        "name": "📋 Classic List",
        "description": "Simple clean list with status icons",
        "render": lambda orders, user_id: _render_classic_list(orders, user_id)
    },
    
    # Layout 2: Premium Cards
    "premium": {
        "name": "💎 Premium Cards",
        "description": "Rich cards with premium emojis",
        "render": lambda orders, user_id: _render_premium_cards(orders, user_id)
    },
    
    # Layout 3: Status Grid
    "grid": {
        "name": "📊 Status Grid",
        "description": "Compact grid view grouped by status",
        "render": lambda orders, user_id: _render_status_grid(orders, user_id)
    },
    
    # Layout 4: Timeline
    "timeline": {
        "name": "⏱️ Timeline",
        "description": "Chronological timeline view",
        "render": lambda orders, user_id: _render_timeline(orders, user_id)
    },
    
    # Layout 5: Colorful
    "colorful": {
        "name": "🌈 Colorful",
        "description": "Colorful status indicators",
        "render": lambda orders, user_id: _render_colorful(orders, user_id)
    },
    
    # Layout 6: Minimal
    "minimal": {
        "name": "✨ Minimal",
        "description": "Clean minimal design",
        "render": lambda orders, user_id: _render_minimal(orders, user_id)
    },
    
    # Layout 7: Rich
    "rich": {
        "name": "💫 Rich Details",
        "description": "Detailed product info",
        "render": lambda orders, user_id: _render_rich(orders, user_id)
    },
    
    # Layout 8: Quick
    "quick": {
        "name": "⚡ Quick View",
        "description": "Fast scanable layout",
        "render": lambda orders, user_id: _render_quick(orders, user_id)
    },
    
    # Layout 9: Modern
    "modern": {
        "name": "🎯 Modern",
        "description": "Modern card design",
        "render": lambda orders, user_id: _render_modern(orders, user_id)
    },
    
    # Layout 10: VIP
    "vip": {
        "name": "👑 VIP",
        "description": "Premium VIP style",
        "render": lambda orders, user_id: _render_vip(orders, user_id)
    },
}


# ════════════════════════════════════════════════════════════════
# 🎨 LAYOUT RENDER FUNCTIONS
# ════════════════════════════════════════════════════════════════

def _render_classic_list(orders, user_id):
    """Layout 1: Simple clean list"""
    text = "📦 *My Orders*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"🛍️ You have *{len(orders)}* order(s)\n\n"
    
    buttons = []
    for o in orders[:15]:
        status_icon = _get_status_icon(o['status'])
        name = _clean_name(o.get('product_name', 'Product'))
        
        text += f"{status_icon} *{name}*\n"
        text += f"   Order #{o['id']} • ${o.get('price', 0):.2f}\n\n"
        
        btn_text = "📦 View Delivery" if o['status'] == 'delivered' else f"🔎 View #{o['id']}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"myord_{o['id']}")])
    
    return text, buttons


def _render_premium_cards(orders, user_id):
    """Layout 2: Rich cards with premium emojis"""
    text = "[[HTML]]"
    text += '<tg-emoji emoji-id="5361747135604070169">📦</tg-emoji> *My Orders*\n'
    text += '━━━━━━━━━━━━━━━━━━━━\n\n'
    text += f'<tg-emoji emoji-id="5361601022416888064">🛍️</tg-emoji> *{len(orders)}* product(s) ordered\n\n'
    
    buttons = []
    for o in orders[:15]:
        status_emoji = _get_status_emoji_html(o['status'])
        name = _clean_name(o.get('product_name', 'Product'))
        
        text += f'{status_emoji} *{name}*\n'
        text += f'├ 🆔 Order: #{o["id"]}\n'
        text += f'├ 💰 Price: *${o.get("price", 0):.2f}*\n'
        text += f'└ 📊 Status: *{_get_status_text(o["status"])}*\n\n'
        
        btn_text = "📦 View Delivery" if o['status'] == 'delivered' else f"🔎 View #{o['id']}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"myord_{o['id']}")])
    
    return text, buttons


def _render_status_grid(orders, user_id):
    """Layout 3: Grouped by status"""
    delivered = [o for o in orders if o['status'] == 'delivered']
    pending = [o for o in orders if o['status'] in ['pending', 'processing']]
    others = [o for o in orders if o not in delivered and o not in pending]
    
    text = "📦 *My Orders*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    buttons = []
    
    if delivered:
        text += f"✅ *Delivered* ({len(delivered)})\n"
        for o in delivered[:5]:
            name = _clean_name(o.get('product_name', 'Product'))
            text += f"  • {name} #{o['id']}\n"
            buttons.append([InlineKeyboardButton(f"📦 {name[:20]}", callback_data=f"myord_{o['id']}")])
        text += "\n"
    
    if pending:
        text += f"⏳ *Processing* ({len(pending)})\n"
        for o in pending[:5]:
            name = _clean_name(o.get('product_name', 'Product'))
            text += f"  • {name} #{o['id']}\n"
            buttons.append([InlineKeyboardButton(f"⏳ {name[:20]}", callback_data=f"myord_{o['id']}")])
        text += "\n"
    
    if others:
        text += f"📋 *Others* ({len(others)})\n"
        for o in others[:5]:
            name = _clean_name(o.get('product_name', 'Product'))
            text += f"  • {name} #{o['id']}\n"
            buttons.append([InlineKeyboardButton(f"🔎 {name[:20]}", callback_data=f"myord_{o['id']}")])
    
    return text, buttons


def _render_timeline(orders, user_id):
    """Layout 4: Chronological timeline"""
    text = "⏱️ *Order Timeline*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    buttons = []
    for i, o in enumerate(orders[:15], 1):
        status_icon = _get_status_icon(o['status'])
        name = _clean_name(o.get('product_name', 'Product'))
        
        text += f"*{i}.* {status_icon} {name}\n"
        text += f"   #{o['id']} • ${o.get('price', 0):.2f} • {_get_status_text(o['status'])}\n\n"
        
        btn_text = "📦 Delivery" if o['status'] == 'delivered' else f"#{o['id']}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"myord_{o['id']}")])
    
    return text, buttons


def _render_colorful(orders, user_id):
    """Layout 5: Colorful status"""
    text = "🌈 *My Orders*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    buttons = []
    for o in orders[:15]:
        color_icon = _get_colorful_status(o['status'])
        name = _clean_name(o.get('product_name', 'Product'))
        
        text += f"{color_icon} *{name}*\n"
        text += f"   #{o['id']} • ${o.get('price', 0):.2f}\n\n"
        
        buttons.append([InlineKeyboardButton(f"{color_icon} #{o['id']}", callback_data=f"myord_{o['id']}")])
    
    return text, buttons


def _render_minimal(orders, user_id):
    """Layout 6: Clean minimal"""
    text = f"📦 *{len(orders)}* Orders\n\n"
    
    buttons = []
    for o in orders[:15]:
        icon = "✅" if o['status'] == 'delivered' else "⏳"
        name = _clean_name(o.get('product_name', 'Product'))[:30]
        
        text += f"{icon} {name} - ${o.get('price', 0):.2f}\n"
        buttons.append([InlineKeyboardButton(f"{icon} #{o['id']}", callback_data=f"myord_{o['id']}")])
    
    return text, buttons


def _render_rich(orders, user_id):
    """Layout 7: Detailed info — 🆕 v170.4: product name ab PREMIUM EMOJI +
    supplier FIXED EMOJI ke saath render hota hai (waisa hi jaise product list
    mein). Pehle _clean_name() HTML tags hata deta tha → emoji gayab."""
    text = "[[HTML]]"
    text += "💫 <b>Order Details</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"

    buttons = []
    for o in orders[:10]:
        name = _render_product_name_html(o.get('product_name', 'Product'))

        text += f"📦 <b>{name}</b>\n"
        text += f"├ 🆔 Order ID: <code>{o['id']}</code>\n"
        text += f"├ 💰 Amount: <b>${o.get('price', 0):.2f}</b>\n"
        text += f"├ 📊 Status: {_get_status_icon(o['status'])} <b>{_get_status_text(o['status'])}</b>\n"
        text += f"└ 🎯 Qty: {o.get('quantity', 1)}\n\n"

        buttons.append([InlineKeyboardButton(f"📦 View #{o['id']}", callback_data=f"myord_{o['id']}")])

    return text, buttons


def _render_quick(orders, user_id):
    """Layout 8: Fast scanable"""
    text = "⚡ *Quick View*\n\n"
    
    buttons = []
    for o in orders[:20]:
        icon = "✅" if o['status'] == 'delivered' else "⏳"
        name = _clean_name(o.get('product_name', 'Product'))[:25]
        
        text += f"{icon} #{o['id']} {name} - ${o.get('price', 0):.2f}\n"
        buttons.append([InlineKeyboardButton(f"#{o['id']}", callback_data=f"myord_{o['id']}")])
    
    return text, buttons


def _render_modern(orders, user_id):
    """Layout 9: Modern cards"""
    text = "🎯 *My Orders*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    buttons = []
    for o in orders[:12]:
        name = _clean_name(o.get('product_name', 'Product'))
        status_badge = _get_status_badge(o['status'])
        
        text += f"┌─────────────────────┐\n"
        text += f"│ {name}\n"
        text += f"│ {status_badge} #{o['id']}\n"
        text += f"│ 💰 ${o.get('price', 0):.2f}\n"
        text += f"└─────────────────────┘\n\n"
        
        buttons.append([InlineKeyboardButton(f"📦 View #{o['id']}", callback_data=f"myord_{o['id']}")])
    
    return text, buttons


def _render_vip(orders, user_id):
    """Layout 10: Premium VIP style"""
    text = "[[HTML]]"
    text += '<tg-emoji emoji-id="5456449467390231543">👑</tg-emoji> *VIP Orders*\n'
    text += '━━━━━━━━━━━━━━━━━━━━\n\n'
    text += f'<tg-emoji emoji-id="5361601022416888064">🛍️</tg-emoji> *{len(orders)}* Premium Products\n\n'
    
    buttons = []
    for o in orders[:12]:
        premium_icon = _get_premium_status(o['status'])
        name = _clean_name(o.get('product_name', 'Product'))
        
        text += f'{premium_icon} *{name}*\n'
        text += f'   ✨ Order #{o["id"]} • 💎 ${o.get("price", 0):.2f}\n\n'
        
        btn_text = "📦 View Delivery" if o['status'] == 'delivered' else f"✨ View #{o['id']}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"myord_{o['id']}")])
    
    return text, buttons


# ════════════════════════════════════════════════════════════════
# 🛠️ HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════════

def _render_product_name_html(name):
    """🆕 v170.4: product name ko HTML mode ke liye render karo — premium
    emoji (<tg-emoji>) + supplier fixed emoji PRESERVE karo (waisa hi jaise
    product list mein dikhta hai). Agar name plain hai to HTML-escape karo."""
    try:
        from utils import name_for_message_html
        return name_for_message_html(name)
    except Exception:
        pass
    if name is None:
        return ""
    s = str(name)
    if s.startswith("[[HTML]]"):
        return s[len("[[HTML]]"):]
    return s


def _clean_name(name):
    """Remove HTML tags from product name"""
    clean = re.sub(r'<[^>]+>', '', name)
    clean = clean.replace('[[HTML]]', '')
    clean = re.sub(r'<tg-emoji[^>]*>([^<]*)</tg-emoji>', r'\1', clean)
    return clean[:40] if len(clean) > 40 else clean


def _get_status_icon(status):
    """Get emoji icon for status"""
    icons = {
        'delivered': '✅',
        'pending': '⏳',
        'processing': '🔄',
        'cancelled': '❌',
        'rejected': '❌',
        'refunded': '💸'
    }
    return icons.get(status, '❓')


def _get_status_text(status):
    """Get human readable status"""
    texts = {
        'delivered': 'Delivered',
        'pending': 'Pending',
        'processing': 'Processing',
        'cancelled': 'Cancelled',
        'rejected': 'Rejected',
        'refunded': 'Refunded'
    }
    return texts.get(status, status)


def _get_status_emoji_html(status):
    """Get premium emoji for status (HTML format)"""
    emojis = {
        'delivered': '<tg-emoji emoji-id="5361747135604070169">✅</tg-emoji>',
        'pending': '<tg-emoji emoji-id="5361747135604070169">⏳</tg-emoji>',
        'processing': '<tg-emoji emoji-id="5361747135604070169">🔄</tg-emoji>',
        'cancelled': '<tg-emoji emoji-id="5361747135604070169">❌</tg-emoji>',
        'rejected': '<tg-emoji emoji-id="5361747135604070169">❌</tg-emoji>',
        'refunded': '<tg-emoji emoji-id="5361747135604070169">💸</tg-emoji>'
    }
    return emojis.get(status, '❓')


def _get_colorful_status(status):
    """Get colorful status indicator"""
    colors = {
        'delivered': '🟢',
        'pending': '🟡',
        'processing': '🔵',
        'cancelled': '🔴',
        'rejected': '🔴',
        'refunded': '🟣'
    }
    return colors.get(status, '⚪')


def _get_status_badge(status):
    """Get status badge"""
    badges = {
        'delivered': '✅ Delivered',
        'pending': '⏳ Processing',
        'processing': '🔄 In Progress',
        'cancelled': '❌ Cancelled',
        'rejected': '❌ Rejected',
        'refunded': '💸 Refunded'
    }
    return badges.get(status, '❓ Unknown')


def _get_premium_status(status):
    """Get premium status indicator"""
    premium = {
        'delivered': '✨',
        'pending': '⏳',
        'processing': '🔄',
        'cancelled': '❌',
        'rejected': '❌',
        'refunded': '💎'
    }
    return premium.get(status, '❓')


# ════════════════════════════════════════════════════════════════
# 📊 ADMIN FUNCTIONS
# ════════════════════════════════════════════════════════════════

def get_orders_layout():
    """Get current orders layout from DB. 🆕 v170.4: default = rich (user choice)"""
    try:
        from database import get_setting
        return get_setting("orders_layout", "rich")
    except Exception:
        return "rich"


def set_orders_layout(layout_id):
    """Set orders layout in DB"""
    try:
        from database import set_setting
        set_setting("orders_layout", layout_id)
        return True
    except Exception:
        return False


def get_all_layouts():
    """Get all available layouts"""
    return ORDERS_LAYOUTS


def render_orders(orders, user_id=None):
    """Render orders with current layout
    
    Returns:
        tuple: (text, buttons_list) where buttons_list is a list of button rows
    """
    layout_id = get_orders_layout()
    layout = ORDERS_LAYOUTS.get(layout_id, ORDERS_LAYOUTS["rich"])
    
    try:
        text, buttons = layout["render"](orders, user_id)
        return text, buttons
    except Exception as e:
        logger.error(f"Error rendering orders: {e}")
        # Fallback to classic
        text, buttons = ORDERS_LAYOUTS["classic"]["render"](orders, user_id)
        return text, buttons
