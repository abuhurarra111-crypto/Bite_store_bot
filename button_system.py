# ============================================================
# 🧩 v77 BUNDLE: button_system.py
# ============================================================
# This file is the merged result of 7 originally separate modules:
#   • button_registry.py
#   • button_styler.py
#   • button_actions.py
#   • button_colors.py
#   • button_text_editor.py
#   • template_buttons.py
#   • styles.py
#
# 🛡️ ALL CODE IS PRESERVED VERBATIM. Each original file's contents appears
# below in its own section. Imports and behavior are byte-identical to the
# pre-merge codebase — only file count is reduced.
# ============================================================


# ============================================================
# 📄 ORIGINAL FILE: button_registry.py
# ============================================================

# ============================================
# 🎛️ BUTTON REGISTRY
# ============================================
# All customizable buttons in one place.
# Admin can rename or hide any button from Admin Panel.
#
# Each button has:
#   id           = unique key (used in DB)
#   group        = screen group (main/admin/settings/shop/payment/customization)
#   short        = small size label (emoji)
#   medium       = medium size label
#   large        = large size label
#   xl           = xl size label
#   callback     = callback_data (or None for url buttons)
#   essential    = if True, can't be hidden (e.g. Back buttons)

BUTTONS = {
    # ── MAIN MENU ──
    "main_shop": {
        "group": "main", "essential": False,
        "short": "🛒", "medium": "🛒 Shop",
        "large": "🛒 Shop Now", "xl": "🛒 Shop Now — Browse all items",
        "callback": "shop",
    },
    "main_points": {
        "group": "main", "essential": False,
        "short": "💎", "medium": "💎 Points",
        "large": "💎 Buy Points", "xl": "💎 Buy Points — Top up wallet",
        "callback": "buy_points",
    },
    # 🆕 v69: Price List button — plain list of all products with sort filters
    "main_price_list": {
        "group": "main", "essential": False,
        "short": "📊", "medium": "📊 Price List",
        "large": "📊 Price List", "xl": "📊 Price List — All products & prices",
        "callback": "price_list",
    },
    "main_account": {
        "group": "main", "essential": False,
        "short": "📊", "medium": "📊 Account",
        "large": "📊 My Account", "xl": "📊 My Account — Profile & balance",
        "callback": "my_account",
    },
    "main_orders": {
        "group": "main", "essential": False,
        "short": "📜", "medium": "📜 Orders",
        "large": "📜 Order History", "xl": "📜 Order History — Past purchases",
        "callback": "my_orders",
    },
    "main_transactions": {
        "group": "main", "essential": False,
        "short": "🔄", "medium": "🔄 Txns",
        "large": "🔄 Transactions", "xl": "🔄 Transaction History — All activity",
        "callback": "transactions",
    },
    # 🆕 v75: main_api button REMOVED — API system disabled on Worker deployment.
    # 🆕 v78: main_how_to inline button REMOVED — now on persistent reply
    # keyboard (always visible at bottom of chat next to 🏠 Main Menu).
    "main_referral": {
        "group": "main", "essential": False,
        "short": "🎁", "medium": "🎁 Refer",
        "large": "🎁 Referral", "xl": "🎁 Referral — Earn points",
        "callback": "referral",
    },
    # 🆕 v46: previously-hardcoded main-menu buttons now registered so admin can
    # rename / hide / set background color from Manage Buttons.
    "main_support": {
        "group": "main", "essential": False,
        "short": "📞", "medium": "📞 Support",
        "large": "📞 Support", "xl": "📞 Support — Get help",
        "callback": "support_menu",
    },
    "main_warranty": {
        "group": "main", "essential": False,
        "short": "🛡️", "medium": "🛡️ Warranty",
        "large": "🛡️ Warranty", "xl": "🛡️ Warranty / Refund",
        "callback": "warranty_menu",
    },
    "main_reviews": {
        "group": "main", "essential": False,
        "short": "⭐", "medium": "⭐ Reviews",
        "large": "⭐ Reviews", "xl": "⭐ Reviews — Read & rate",
        "callback": "reviews_menu",
    },
    "main_loyalty": {
        "group": "main", "essential": False,
        "short": "🏆", "medium": "🏆 Loyalty",
        "large": "🏆 Loyalty", "xl": "🏆 Loyalty — Tiers & perks",
        "callback": "loyalty_menu",
    },
    "main_language": {
        "group": "main", "essential": False,
        "short": "🌐", "medium": "🌐 Language",
        "large": "🌐 Language", "xl": "🌐 Language — Change language",
        "callback": "language_menu",
    },
    "main_admin": {
        "group": "main", "essential": True,  # admin-only, can't be hidden by accident
        "short": "🤖", "medium": "🤖 Admin",
        "large": "🤖 Admin Panel", "xl": "🤖 Admin Menu Panel",
        "callback": "admin_panel",
    },

    # ── ADMIN PANEL ──
    "admin_items": {
        "group": "admin", "essential": True,
        "short": "📝", "medium": "📝 Items",
        "large": "📝 Edit Items", "xl": "📝 Edit Items — Add/Delete products",
        "callback": "admin_products",
    },
    "admin_categories": {
        "group": "admin", "essential": True,
        "short": "🏷️", "medium": "🏷️ Cats",
        "large": "🏷️ Categories", "xl": "🏷️ Categories — Manage categories",
        "callback": "admin_categories",
    },
    "admin_users": {
        "group": "admin", "essential": False,
        "short": "👤", "medium": "👤 Users",
        "large": "👤 Users", "xl": "👤 Users — View all users",
        "callback": "admin_users",
    },
    "admin_profit": {
        "group": "admin", "essential": False,
        "short": "📊", "medium": "📊 Profit",
        "large": "📊 Profit/Loss", "xl": "📊 Profit/Loss — Sales analytics",
        "callback": "admin_profit",
    },
    "admin_settings": {
        "group": "admin", "essential": True,
        "short": "⚙️", "medium": "⚙️ Settings",
        "large": "⚙️ Settings", "xl": "⚙️ Settings — Bot config",
        "callback": "admin_settings",
    },
    "admin_customization": {
        "group": "admin", "essential": True,
        "short": "🎨", "medium": "🎨 Custom",
        "large": "🎨 Customization", "xl": "🎨 Customization — Look & feel",
        "callback": "admin_customization",
    },
    "admin_buttons": {
        # 🆕 v52: Moved from "admin" → "customization" so it's grouped with other
        # look-&-feel features. Single source of truth for all button editing.
        "group": "customization", "essential": True,
        "short": "🎨", "medium": "🎨 Buttons",
        "large": "🎨 Buttons (All)", "xl": "🎨 Buttons — Rename / Color / Hide / Style",
        "callback": "admin_buttons",
    },
    "admin_broadcast": {
        "group": "admin", "essential": False,
        "short": "🌐", "medium": "🌐 Broadcast",
        "large": "🌐 Global Message", "xl": "🌐 Global Message — Send to all",
        "callback": "admin_broadcast",
    },
    # 🆕 v73: "admin_orders" (Pending Orders button) REMOVED permanently per user request.
    # Replaced by "admin_completed" (Completed Orders with Delivered/Refunded/Cancelled tabs)
    # plus "admin_pending_delivery" which already covers manual delivery queue.
    "admin_completed": {
        "group": "admin", "essential": True,
        "short": "✅", "medium": "✅ Completed",
        "large": "✅ Completed Orders", "xl": "✅ Completed Orders — Grouped by User",
        # 🆕 v84: routes to grouped-by-user v2 screen
        "callback": "admin_completed_v2",
    },
    "admin_replacements": {
        "group": "admin", "essential": False,
        "short": "🔁", "medium": "🔁 Replace",
        "large": "🔁 Replacement History", "xl": "🔁 Replacement Requests — Manage History",
        "callback": "admin_replacements",
    },
    # 🆕 v81: External Suppliers (REST API stock — Akunding/Canboso/MMOStore/TunVNMMO)
    "admin_suppliers": {
        "group": "admin", "essential": True,
        "short": "📦", "medium": "📦 Suppliers",
        "large": "📦 External Suppliers", "xl": "📦 External Suppliers — REST API stock",
        "callback": "admin_suppliers",
    },
    "admin_ai": {
        "group": "admin", "essential": False,
        "short": "💬", "medium": "💬 AI",
        "large": "💬 AI Assistant", "xl": "💬 AI Admin Assistant — Ask anything",
        "callback": "admin_ai",
    },
    "admin_reset": {
        "group": "admin", "essential": False,
        "short": "🔄", "medium": "🔄 Reset",
        "large": "🔄 Reset & Undo", "xl": "🔄 Reset All / Undo Changes",
        "callback": "admin_reset_undo",
    },
    "admin_backup": {
        "group": "admin", "essential": False,
        "short": "💾", "medium": "💾 Backup",
        "large": "💾 Backup & Restore", "xl": "💾 Backup / Restore Database",
        "callback": "admin_backup",
    },
    # 🆕 v46: previously-hardcoded Admin Panel buttons now registered so they
    # appear in Manage Buttons and support rename / color / hide.
    "admin_deposits": {
        "group": "admin", "essential": False,
        "short": "📊", "medium": "📊 Deposits",
        "large": "📊 All Deposits & History", "xl": "📊 All Deposits & History",
        "callback": "admin_deposits",
    },
    "admin_analytics": {
        "group": "admin", "essential": False,
        "short": "📈", "medium": "📈 Analytics",
        "large": "📊 Analytics Dashboard", "xl": "📊 Analytics Dashboard",
        "callback": "admin_analytics",
    },
    "admin_reviews": {
        "group": "admin", "essential": False,
        "short": "⭐", "medium": "⭐ Reviews",
        "large": "⭐ Reviews", "xl": "⭐ Reviews Management",
        "callback": "admin_reviews",
    },
    "admin_loyalty": {
        "group": "admin", "essential": False,
        "short": "🏆", "medium": "🏆 Loyalty",
        "large": "🏆 Loyalty Tiers", "xl": "🏆 Loyalty Tiers",
        "callback": "admin_loyalty",
    },
    "admin_tickets": {
        "group": "admin", "essential": False,
        "short": "🎫", "medium": "🎫 Tickets",
        "large": "🎫 Support Tickets", "xl": "🎫 Support Tickets",
        "callback": "adm_tickets",
    },
    "admin_warranty": {
        "group": "admin", "essential": False,
        "short": "🛡️", "medium": "🛡️ Warranty",
        "large": "🛡️ Warranty/Refund", "xl": "🛡️ Warranty / Refund",
        "callback": "adm_warranty",
    },
    "admin_pending_delivery": {
        "group": "admin", "essential": False,
        "short": "📦", "medium": "📦 Deliveries",
        "large": "📦 Pending Manual Deliveries", "xl": "📦 Pending Manual Deliveries",
        "callback": "adm_pending_delivery",
    },
    "admin_restock_reqs": {
        # 🆕 v94: HIDDEN from admin panel — user requested removal (no use case).
        # Kept in registry for backward-compat only (existing callback resolver
        # would break if we deleted it). Marked hidden=True so it never renders.
        "group": "admin", "essential": False, "hidden": True,
        "short": "🔄", "medium": "🔄 Restock",
        "large": "🔄 Product Restock Requests", "xl": "🔄 Product Restock Requests",
        "callback": "adm_restock_reqs",
    },
    "admin_diagnostics": {
        "group": "admin", "essential": False,
        "short": "🧪", "medium": "🧪 Diagnostics",
        "large": "🧪 System Diagnostics & Test", "xl": "🧪 System Diagnostics & Test",
        "callback": "adm_diagnostics",
    },
    # 🆕 v48: Referral abuse panel
    "admin_referrals": {
        "group": "admin", "essential": False,
        "short": "🛡️", "medium": "🛡️ Referrals",
        "large": "🛡️ Referral Abuse Control", "xl": "🛡️ Referral Abuse Control — Audit, ban, adjust",
        "callback": "refadm_panel",
    },
    "admin_cbtns": {
        "group": "admin", "essential": False,
        "short": "➕", "medium": "➕ Custom Btns",
        "large": "➕ Custom Buttons", "xl": "➕ Custom Buttons",
        "callback": "admin_cbtns",
    },
    "admin_cpages": {
        "group": "admin", "essential": False,
        "short": "📄", "medium": "📄 Pages",
        "large": "📄 Custom Pages", "xl": "📄 Custom Pages",
        "callback": "admin_cpages",
    },
    "admin_fake_activity": {
        "group": "admin", "essential": False,
        "short": "🎭", "medium": "🎭 Activity",
        "large": "🎭 Fake Activity", "xl": "🎭 Fake Activity",
        "callback": "act_panel",
    },
    # 🆕 v78: admin_api button REMOVED — API Management feature deprecated
    # (handlers_admin_api.py functions still in admin_panels.py but unreachable
    # via UI now; user is on Worker deployment where REST API can't be hosted).
    "admin_location_styles": {
        "group": "admin", "essential": False,
        "short": "📍", "medium": "📍 Locations",
        "large": "📍 Location Styles", "xl": "📍 Location Styles",
        "callback": "lc_panel",
    },
    "admin_force_join": {
        "group": "admin", "essential": False,
        "short": "🔗", "medium": "🔗 Force Join",
        "large": "🔗 Force Join Setup", "xl": "🔗 Force Join Setup",
        "callback": "fj_panel",
    },

    # ── SETTINGS ──
    "set_shop_name": {
        "group": "settings", "essential": False,
        "short": "🏪", "medium": "🏪 Shop",
        "large": "🏪 Shop Name", "xl": "🏪 Edit Shop Name",
        "callback": "set_shop_name",
    },
    "set_whatsapp": {
        "group": "settings", "essential": False,
        "short": "📞", "medium": "📞 WA",
        "large": "📞 WhatsApp", "xl": "📞 Edit WhatsApp Number",
        "callback": "set_whatsapp",
    },
    "set_binance": {
        "group": "settings", "essential": False,
        "short": "🔶", "medium": "🔶 Binance",
        "large": "🔶 Binance ID", "xl": "🔶 Edit Binance Pay ID",
        "callback": "set_binance",
    },
    "set_easypaisa": {
        "group": "settings", "essential": False,
        "short": "📱", "medium": "📱 EP",
        "large": "📱 EasyPaisa", "xl": "📱 Edit EasyPaisa Number",
        "callback": "set_easypaisa",
    },
    "set_easypaisa_name": {
        "group": "settings", "essential": False,
        "short": "👤", "medium": "👤 EP Name",
        "large": "👤 EasyPaisa Name", "xl": "👤 EasyPaisa Account Holder Name",
        "callback": "set_easypaisa_name",
    },
    "set_jazzcash_name": {
        "group": "settings", "essential": False,
        "short": "👤", "medium": "👤 JC Name",
        "large": "👤 JazzCash Name", "xl": "👤 JazzCash Account Holder Name",
        "callback": "set_jazzcash_name",
    },
    "set_binance_name": {
        "group": "settings", "essential": False,
        "short": "👤", "medium": "👤 BN Name",
        "large": "👤 Binance Name", "xl": "👤 Binance Account Holder Name",
        "callback": "set_binance_name",
    },
    "set_jazzcash": {
        "group": "settings", "essential": False,
        "short": "📱", "medium": "📱 JC",
        "large": "📱 JazzCash", "xl": "📱 Edit JazzCash Number",
        "callback": "set_jazzcash",
    },
    "set_email": {
        "group": "settings", "essential": False,
        "short": "📧", "medium": "📧 Email",
        "large": "📧 Support Email", "xl": "📧 Edit Support Email",
        "callback": "set_email",
    },
    "set_pkr_rate": {
        "group": "settings", "essential": False,
        "short": "💱", "medium": "💱 Rate",
        "large": "💱 USD→PKR Rate", "xl": "💱 Edit USD to PKR Conversion Rate",
        "callback": "set_pkr_rate",
    },
    "settings_responses": {
        "group": "settings", "essential": False,
        "short": "✏️", "medium": "✏️ Responses",
        "large": "✏️ Edit Responses", "xl": "✏️ Edit Bot Responses",
        "callback": "admin_responses",
    },
    "settings_terms": {
        "group": "settings", "essential": False,
        "short": "📜", "medium": "📜 Terms",
        "large": "📜 Terms", "xl": "📜 Terms & Conditions",
        "callback": "admin_terms",
    },

    # ── SHOP / PRODUCT ──
    "shop_buy": {
        "group": "shop", "essential": True,
        "short": "🛒", "medium": "🛒 Buy",
        "large": "🛒 Buy Now", "xl": "🛒 Buy Now — Order this item",
        "callback": None,  # dynamic (buy_{pid})
    },

    # ── PAYMENT METHODS ──
    "pay_pts": {
        # 🆕 v57: Pay with Points (Wallet) was previously hardcoded in
        # keyboards.py:payment_method_keyboard() — now a proper registry
        # button so Screen Editor → Payment Methods shows it editable too.
        "group": "payment", "essential": False,
        "short": "💎", "medium": "💎 Pay with Points",
        "large": "💎 Pay with Points (Wallet)",
        "xl": "💎 Pay with Points (Wallet)",
        "callback": None,  # dynamic — actual callback set at render: pay_pts_<pid>_<qty>
    },
    "pay_binance": {
        "group": "payment", "essential": False,
        "short": "🔶", "medium": "🔶 Binance Auto",
        "large": "🔶 Binance Pay ⚡ Auto", "xl": "🔶 Binance Pay — Auto Verify ⚡",
        "callback": None,  # dynamic
    },
    "pay_easypaisa": {
        "group": "payment", "essential": False,
        "short": "📱", "medium": "📱 EasyPaisa Auto",
        "large": "📱 EasyPaisa ⚡ Auto", "xl": "📱 EasyPaisa — Auto Verify ⚡",
        "callback": None,
    },
    "pay_jazzcash": {
        "group": "payment", "essential": False,
        "short": "📱", "medium": "📱 JazzCash Auto",
        "large": "📱 JazzCash ⚡ Auto", "xl": "📱 JazzCash — Auto Verify ⚡",
        "callback": None,
    },

    # ── POINTS BUY ──
    "pts_custom": {
        "group": "points", "essential": False,
        "short": "💎", "medium": "💎 Custom",
        "large": "💎 Custom Amount", "xl": "💎 Custom Amount — Type your own",
        "callback": "pts_custom",
    },

    # ── CUSTOMIZATION ──
    "cust_toggles": {
        "group": "customization", "essential": True,
        "short": "👁️", "medium": "👁️ Toggles",
        "large": "👁️ Product Toggles", "xl": "👁️ Product Detail Toggles",
        "callback": "admin_toggles",
    },
    "cust_size": {
        "group": "customization", "essential": True,
        "short": "📏", "medium": "📏 Size",
        "large": "📏 Button Sizes", "xl": "📏 Button Sizes (Small/Med/Large/XL)",
        "callback": "admin_btn_size",
    },
    "cust_styles": {
        "group": "customization", "essential": True,
        "short": "🎨", "medium": "🎨 Styles",
        "large": "🎨 Menu Styles", "xl": "🎨 Menu Styles (10 looks)",
        "callback": "admin_menu_style",
    },
    "cust_format": {
        "group": "customization", "essential": True,
        "short": "🎠", "medium": "🎠 Format",
        "large": "🎠 Display Format", "xl": "🎠 Display Format (Raw / Carousel)",
        "callback": "admin_display_format",
    },
    "cust_colors": {
        "group": "customization", "essential": True,
        "short": "🎨", "medium": "🎨 Colors",
        "large": "🎨 Product Colors", "xl": "🎨 Product Color Indicators (Stock-based)",
        "callback": "admin_colors",
    },

    # ════════════════════════════════════════════════════════════
    # 🆕 v52: USER-SIDE NAVIGATION BUTTONS (back / home / cancel / pagination)
    # Now fully editable: rename per size, premium emoji icon, background
    # color, size, alignment, padding. Use _rb("nav_<id>") in keyboards.py
    # to render them — admin overrides apply automatically.
    # ════════════════════════════════════════════════════════════
    "nav_prod_back_shop": {
        "group": "navigation", "essential": True,
        "short": "🔙", "medium": "🔙 Back",
        "large": "🔙 Back to Shop", "xl": "🔙 Back to Shop",
        "callback": "shop",
    },
    "nav_prod_home": {
        "group": "navigation", "essential": True,
        "short": "🏠", "medium": "🏠 Home",
        "large": "🏠 Home", "xl": "🏠 Main Menu",
        "callback": "main_menu",
    },
    "nav_pay_cancel": {
        "group": "navigation", "essential": True,
        "short": "❌", "medium": "❌ Cancel",
        "large": "❌ Cancel", "xl": "❌ Cancel — Back to shop",
        "callback": "shop",
    },
    "nav_order_cancel": {
        "group": "navigation", "essential": True,
        "short": "❌", "medium": "❌ Cancel",
        "large": "❌ Cancel Order", "xl": "❌ Cancel Order",
        "callback": "cancel_order",
    },
    "nav_order_home": {
        "group": "navigation", "essential": True,
        "short": "🏠", "medium": "🏠 Home",
        "large": "🏠 Home", "xl": "🏠 Main Menu",
        "callback": "main_menu",
    },
    "nav_points_back": {
        "group": "navigation", "essential": True,
        "short": "🔙", "medium": "🔙 Back",
        "large": "🔙 Back", "xl": "🔙 Back to Main Menu",
        "callback": "main_menu",
    },
    "nav_points_cancel": {
        "group": "navigation", "essential": True,
        "short": "❌", "medium": "❌ Cancel",
        "large": "❌ Cancel", "xl": "❌ Cancel",
        "callback": "buy_points",
    },
    "nav_back_main": {
        "group": "navigation", "essential": True,
        "short": "🔙", "medium": "🔙 Back",
        "large": "🔙 Back", "xl": "🔙 Back to Main Menu",
        "callback": "main_menu",
    },
    "nav_back_generic": {
        "group": "navigation", "essential": True,
        "short": "🔙", "medium": "🔙 Back",
        "large": "🔙 Back", "xl": "🔙 Back",
        "callback": "go_back",
    },
    "nav_shop_prev_page": {
        "group": "navigation", "essential": True,
        "short": "⬅️", "medium": "⬅️ Previous",
        "large": "⬅️ Previous Page", "xl": "⬅️ Previous Page",
        "callback": "shop_prev",  # placeholder; real callback set inline per page
    },
    "nav_shop_next_page": {
        "group": "navigation", "essential": True,
        "short": "➡️", "medium": "Next ➡️",
        "large": "Next Page ➡️", "xl": "Next Page ➡️",
        "callback": "shop_next",  # placeholder; real callback set inline per page
    },
    "nav_shop_home": {
        "group": "navigation", "essential": True,
        "short": "🏠", "medium": "🏠 Home",
        "large": "🏠 Back to Main Menu", "xl": "🏠 Back to Main Menu",
        "callback": "main_menu",
    },
    "nav_categories_back": {
        "group": "navigation", "essential": True,
        "short": "🔙", "medium": "🔙 Categories",
        "large": "🔙 Back to Categories", "xl": "🔙 Back to Categories",
        "callback": "shop",
    },
    "nav_carousel_prev": {
        "group": "navigation", "essential": True,
        "short": "⬅️", "medium": "⬅️ Prev",
        "large": "⬅️ Previous Product", "xl": "⬅️ Previous Product",
        "callback": "carousel_prev",  # placeholder
    },
    "nav_carousel_next": {
        "group": "navigation", "essential": True,
        "short": "➡️", "medium": "Next ➡️",
        "large": "Next Product ➡️", "xl": "Next Product ➡️",
        "callback": "carousel_next",  # placeholder
    },

    # ════════════════════════════════════════════════════════════
    # 🆕 v68: Admin-side buttons added in v61-v67 (admin group ONLY)
    # These let admin rename / restyle / hide them via Customization.
    # IMPORTANT: ALL in "admin" group so they don't leak into delivery/payment
    # screens (the v66 regression we explicitly want to avoid).
    # ════════════════════════════════════════════════════════════

    # 🪙 v61: Binance Pay API panel
    "admin_binance_api": {
        "group": "admin", "essential": False,
        "short": "🪙", "medium": "🪙 Binance API",
        "large": "🪙 Binance Pay API", "xl": "🪙 Binance Pay REST API",
        "callback": "admin_binance_api",
    },
    # 🩺 v61: Test connection
    "admin_binance_api_test": {
        "group": "admin", "essential": False,
        "short": "🩺", "medium": "🩺 Test API",
        "large": "🩺 Test Connection", "xl": "🩺 Test Binance API Connection",
        "callback": "admin_binance_api_test",
    },
    # 📜 v61: Recent payments list
    "admin_binance_api_list": {
        "group": "admin", "essential": False,
        "short": "📜", "medium": "📜 Pay List",
        "large": "📜 Recent Payments", "xl": "📜 Recent Binance Payments",
        "callback": "admin_binance_api_list",
    },
    # 📡 v63: Proxy Status panel
    "admin_binance_proxies": {
        "group": "admin", "essential": False,
        "short": "📡", "medium": "📡 Proxies",
        "large": "📡 Proxy Status", "xl": "📡 Binance Proxy Pool",
        "callback": "admin_binance_proxies",
    },
    # 🤖 v67: AI Scout
    "admin_proxy_ai_scout": {
        "group": "admin", "essential": False,
        "short": "🤖", "medium": "🤖 AI Find Proxies",
        "large": "🤖 AI Find New Proxies",
        "xl": "🤖 Gemini AI — Auto-Find Working Proxies",
        "callback": "admin_proxy_ai_scout",
    },
    # 🏆 v68: Tier Configuration
    "admin_tier_cfg": {
        "group": "admin", "essential": False,
        "short": "⚙️", "medium": "⚙️ Tier Cfg",
        "large": "⚙️ Configure Tiers", "xl": "⚙️ Configure Loyalty Tiers",
        "callback": "admin_tier_cfg",
    },
}


# Friendly screen names
GROUP_NAMES = {
    "main": "🏠 Main Menu",
    "admin": "👑 Admin Panel",
    "settings": "⚙️ Settings",
    "shop": "🛒 Shop / Product",
    "payment": "💳 Payment Methods",
    "points": "💎 Points Buy",
    "customization": "🎨 Customization",
    "navigation": "🔙 Navigation Buttons (Back / Home / Cancel / Prev / Next)",  # 🆕 v52
}


def get_button_label(btn_id, size="medium"):
    """Get button label — admin override OR default.
    Returns None if button is hidden.
    """
    from database import get_setting

    btn = BUTTONS.get(btn_id)
    if not btn:
        return None

    # 🆕 v94: registry-level `hidden` flag — for buttons we permanently
    # removed (e.g. admin_restock_reqs) without deleting from registry
    # (backward-compat with callback resolver). Returns None → skipped.
    if btn.get("hidden"):
        return None

    # 🔧 BUGFIX: the global button_size setting uses "small"/"full" but the
    # registry + saved label keys use "short"/"xl". Without this mapping, the
    # "small" size always fell back to the medium default — so a renamed button
    # showed its OLD default text when button_size was Small.
    _size_alias = {"small": "short", "full": "xl"}
    size = _size_alias.get(size, size)

    # Check hidden (essential buttons cannot be hidden)
    if not btn.get("essential"):
        hidden = get_setting(f"btn_hidden_{btn_id}", "0")
        if hidden == "1":
            return None  # hidden

    # Custom label override (per size, falls back to default)
    custom = get_setting(f"btn_label_{btn_id}_{size}", "")
    if custom:
        return custom

    # 🔧 BUGFIX (premium emoji not showing for some sizes):
    # If THIS size has no override but ANOTHER size was saved WITH a premium
    # emoji ([[HTML]]/<tg-emoji>), prefer that so the premium icon shows on the
    # main menu regardless of the current global button_size setting.
    for _sz in ("xl", "large", "medium", "short"):
        if _sz == size:
            continue
        other = get_setting(f"btn_label_{btn_id}_{_sz}", "")
        if other and ("[[HTML]]" in other or "<tg-emoji" in other.lower()):
            return other

    # Default label
    return btn.get(size) or btn.get("medium")


def is_button_hidden(btn_id):
    """True if button hidden by admin (only non-essential)"""
    from database import get_setting
    btn = BUTTONS.get(btn_id)
    if not btn or btn.get("essential"):
        return False
    return get_setting(f"btn_hidden_{btn_id}", "0") == "1"


def get_buttons_by_group(group):
    """Return list of (btn_id, info) for a given group"""
    return [(k, v) for k, v in BUTTONS.items() if v.get("group") == group]


def reset_button(btn_id):
    """Reset a button: unhide + clear all custom labels + clear color + clear styler.
    🆕 v54: now ALSO clears size/align/pad (button_styler) AND custom order so a
    'Reset to default' is truly complete — no leftover customization anywhere.
    """
    from database import set_setting
    set_setting(f"btn_hidden_{btn_id}", "0")
    for size in ("short", "medium", "large", "xl"):
        set_setting(f"btn_label_{btn_id}_{size}", "")
    set_setting(f"btn_style_{btn_id}", "")
    # 🆕 v54: also clear button_styler settings (size/align/pad)
    try:
        # [v77-merge] self-bundle import removed: from button_styler import reset_style
        reset_style(btn_id)
    except Exception:
        pass
    # 🆕 v54: also clear sort order so button returns to its registry position
    set_setting(f"btn_order_{btn_id}", "")


# ════════════════════════════════════════════
# 🎨 BUTTON BACKGROUND COLOR (Bot API 9.4 'style')
# ════════════════════════════════════════════
# Telegram supports 3 button background colors via the `style` field:
#   "primary" (blue), "success" (green), "danger" (red).
# Requires the bot OWNER to have Telegram Premium to render.
VALID_BUTTON_STYLES = ("primary", "success", "danger")


def get_button_style(btn_id):
    """Return saved Telegram button style ('primary'/'success'/'danger') or ''."""
    from database import get_setting
    s = (get_setting(f"btn_style_{btn_id}", "") or "").strip().lower()
    return s if s in VALID_BUTTON_STYLES else ""


def set_button_style(btn_id, style):
    """Persist a button background color. Pass '' to clear (default look)."""
    from database import set_setting
    style = (style or "").strip().lower()
    if style not in VALID_BUTTON_STYLES:
        style = ""
    set_setting(f"btn_style_{btn_id}", style)


def get_group_style(group):
    """🆕 v46: a single background color applied to ALL buttons in a group/location.
    Per-button color (btn_style_<id>) still wins over this group default."""
    from database import get_setting
    s = (get_setting(f"grpstyle_{group}", "") or "").strip().lower()
    return s if s in VALID_BUTTON_STYLES else ""


def set_group_style(group, style):
    """🆕 v46: set/clear one color for an entire group/location in one click."""
    from database import set_setting
    style = (style or "").strip().lower()
    if style not in VALID_BUTTON_STYLES:
        style = ""
    set_setting(f"grpstyle_{group}", style)


def resolve_button_style(btn_id, group=None):
    """🆕 v46: effective color for a button:
       per-button override → else group/location default → else none."""
    s = get_button_style(btn_id)
    if s:
        return s
    if group is None:
        g = BUTTONS.get(btn_id, {})
        group = g.get("group")
    if group:
        return get_group_style(group)
    return ""



# ════════════════════════════════════════════
# 🔄 BUTTON REORDERING (Phase C)
# ════════════════════════════════════════════

def get_button_order(btn_id):
    """Get sort order for a button. Default = position in BUTTONS dict."""
    from database import get_setting
    # Custom order from DB
    custom = get_setting(f"btn_order_{btn_id}", "")
    if custom:
        try: return int(custom)
        except ValueError: pass
    # Default: position in registry (multiplied for spacing)
    keys = list(BUTTONS.keys())
    try:
        return (keys.index(btn_id) + 1) * 10
    except ValueError:
        return 9999


def set_button_order(btn_id, order):
    """Save sort order"""
    from database import set_setting
    set_setting(f"btn_order_{btn_id}", str(int(order)))


def get_ordered_button_ids(group):
    """Return button ids in a group, sorted by current order.
    🆕 v94: registry-level `hidden` flag filtered out completely."""
    items = [(bid, get_button_order(bid)) for bid, info in BUTTONS.items()
             if info.get("group") == group and not info.get("hidden")]
    items.sort(key=lambda x: (x[1], x[0]))  # by order, then by id for stability
    return [bid for bid, _ in items]


def move_button_up(btn_id):
    """Swap order with the button above in same group"""
    btn = BUTTONS.get(btn_id)
    if not btn: return False
    group = btn.get("group")
    ordered = get_ordered_button_ids(group)
    try:
        idx = ordered.index(btn_id)
    except ValueError:
        return False
    if idx == 0:
        return False  # already at top
    above_id = ordered[idx - 1]
    # Swap orders
    my_order = get_button_order(btn_id)
    above_order = get_button_order(above_id)
    set_button_order(btn_id, above_order)
    set_button_order(above_id, my_order)
    return True


def move_button_down(btn_id):
    """Swap order with the button below in same group"""
    btn = BUTTONS.get(btn_id)
    if not btn: return False
    group = btn.get("group")
    ordered = get_ordered_button_ids(group)
    try:
        idx = ordered.index(btn_id)
    except ValueError:
        return False
    if idx >= len(ordered) - 1:
        return False  # already at bottom
    below_id = ordered[idx + 1]
    my_order = get_button_order(btn_id)
    below_order = get_button_order(below_id)
    set_button_order(btn_id, below_order)
    set_button_order(below_id, my_order)
    return True


def reset_button_order(btn_id):
    """Reset order to default"""
    from database import set_setting
    set_setting(f"btn_order_{btn_id}", "")


# ============================================================
# 📄 ORIGINAL FILE: button_styler.py
# ============================================================

# ============================================================
# 🎨 BUTTON STYLER (v41-clean)
# ============================================================
# Per-button visual customization for inline keyboard buttons.
#
# Telegram khud button ki width fix nahi karta — woh text length aur
# columns par depend karti hai. Yeh module non-trimmable invisible chars
# inject karke buttons ko visually bara/centered/aligned dikhata hai.
#
# Per-button settings (DB `bot_settings` mein):
#   bstyle_<key>_size   → "auto" | "small" | "medium" | "large" | "xl" | "full"
#   bstyle_<key>_align  → "auto" | "left" | "center" | "right"
#   bstyle_<key>_pad    → "0".."40"  (extra width units; 0 = no padding)
#
# `key` examples:
#   reg_<button_id>           — registry button (e.g. reg_main_shop)
#   shop_product              — Shop screen ka product button
#   shop_pagination           — Shop pagination buttons
#   shop_buy                  — Buy Now button
#   pd_<product_id>           — specific product override (future use)
#   custom_<bid>              — admin's custom button
#
# Public API:
#   style_label(key, label)               -> styled label str
#   wrap_button(key, btn)                 -> InlineKeyboardButton (in-place ok)
#   get_style(key)                        -> {"size","align","pad"}
#   set_style(key, **kwargs)              -> persist
#   reset_style(key)
#   list_known_keys()                     -> [(key, friendly_name), ...]
# ============================================================

from telegram import InlineKeyboardButton

# ── Constants ────────────────────────────────────────────────
SIZES        = ("auto", "small", "medium", "large", "xl", "full")
ALIGNS       = ("auto", "left", "center", "right")
MAX_PAD      = 40

# Visual width target per size (in "space units").
# Telegram clients render width based on label char-width; these numbers are
# tuned for mobile (Telegram Android/iOS) where ~28-32 chars fills a single
# column row. FULL pushes it to absolute max (~44 units).
SIZE_WIDTH = {
    "small":  8,
    "medium": 16,
    "large":  24,
    "xl":     32,
    "full":   44,
}

# Hangul Filler — ye ek Unicode LETTER hai (Lo category), whitespace nahi.
# Is wajah se Telegram isy TRIM nahi karta. Visually blank dikhta hai
# lekin button width bara karne ke liye perfect hai.
PAD_CHAR = "\u3164"

# ── DB helpers ───────────────────────────────────────────────
def _gs(k, d=""):
    try:
        from database import get_setting
        return get_setting(k, d)
    except Exception:
        return d

def _ss(k, v):
    try:
        from database import set_setting
        set_setting(k, str(v))
    except Exception:
        pass


def get_style(key: str) -> dict:
    """Return current style dict for a button key. Defaults to 'auto'."""
    return {
        "size":  _gs(f"bstyle_{key}_size",  "auto"),
        "align": _gs(f"bstyle_{key}_align", "auto"),
        "pad":   int(_gs(f"bstyle_{key}_pad", "0") or 0),
    }


def set_style(key: str, size=None, align=None, pad=None):
    if size is not None and size in SIZES:
        _ss(f"bstyle_{key}_size", size)
    if align is not None and align in ALIGNS:
        _ss(f"bstyle_{key}_align", align)
    if pad is not None:
        try:
            p = max(0, min(MAX_PAD, int(pad)))
            _ss(f"bstyle_{key}_pad", p)
        except (TypeError, ValueError):
            pass


def reset_style(key: str):
    _ss(f"bstyle_{key}_size", "auto")
    _ss(f"bstyle_{key}_align", "auto")
    _ss(f"bstyle_{key}_pad", "0")


# ════════════════════════════════════════════
# 📐 v46: SCREEN-LEVEL PADDING (whole menu/screen at once)
# ════════════════════════════════════════════
# Stored per location/group as `scrpad_<location>` (0..MAX_PAD).
# Applied to EVERY button rendered on that screen so the admin can make a whole
# menu wider/narrower in one place — without editing each button.

def get_screen_pad(location: str) -> int:
    try:
        return max(0, min(MAX_PAD, int(_gs(f"scrpad_{location}", "0") or 0)))
    except (TypeError, ValueError):
        return 0


def set_screen_pad(location: str, pad) -> int:
    try:
        p = max(0, min(MAX_PAD, int(pad)))
    except (TypeError, ValueError):
        p = 0
    _ss(f"scrpad_{location}", p)
    return p


def apply_screen_pad(label: str, location: str) -> str:
    """Add the screen's extra padding to a single button label.
    Premium-emoji aware: keeps the icon glued to its text (padding on the right).
    """
    if not label:
        return label
    pad = get_screen_pad(location)
    if pad <= 0:
        return label
    s = str(label)
    # Separate a leading premium-emoji tag so the icon stays glued to its text.
    prefix = ""
    core = s
    if "[[HTML]]" in core or "<tg-emoji" in core.lower():
        import re as _re
        m = _re.match(
            r'^\s*(\[\[HTML\]\])?\s*(<tg-emoji\s+emoji-id=["\']\d+["\']\s*>[^<]*</tg-emoji>)\s*',
            core, flags=_re.IGNORECASE)
        if m:
            prefix = (m.group(1) or "") + m.group(2)
            core = core[m.end():]
    padstr = PAD_CHAR * pad
    if prefix:
        return prefix + (" " if core else "") + core + padstr
    return core + padstr


def is_styled(key: str) -> bool:
    """True if admin has set any non-auto/non-zero override."""
    s = get_style(key)
    return s["size"] != "auto" or s["align"] != "auto" or s["pad"] > 0


# ── Core: apply size + alignment + padding ───────────────────
def _visual_len(s: str) -> int:
    """Rough visual length (counts each char as 1; emoji as ~2)."""
    n = 0
    for ch in s:
        cp = ord(ch)
        # Wide / emoji range — count as 2
        if cp >= 0x1F000 or (0x2600 <= cp <= 0x27BF):
            n += 2
        else:
            n += 1
    return n


def style_label(key: str, label: str) -> str:
    """
    Apply per-button visual styling: size (target width), alignment, extra pad.
    Returns new label string (may include invisible padding).
    If admin hasn't overridden anything, returns label unchanged.

    🔧 v46: premium-emoji aware. A label may be a premium sentinel like
    "[[HTML]]<tg-emoji emoji-id='X'>🔥</tg-emoji> Shop". The <tg-emoji> tag is
    rendered as the button ICON (before the text), so padding must be applied to
    the VISIBLE TEXT ONLY and the icon tag must stay glued to the front —
    otherwise the emoji ends up far left while the text drifts right.
    """
    if not label:
        return label
    s = get_style(key)
    size  = s["size"]
    align = s["align"]
    pad   = s["pad"]

    # ── 🔧 v46: separate a leading premium-emoji tag from the visible text ──
    prefix = ""          # the [[HTML]]<tg-emoji ...></tg-emoji> part (icon)
    core = str(label)    # the part we actually pad
    if "[[HTML]]" in core or "<tg-emoji" in core.lower():
        import re as _re
        m = _re.match(
            r'^\s*(\[\[HTML\]\])?\s*(<tg-emoji\s+emoji-id=["\']\d+["\']\s*>[^<]*</tg-emoji>)\s*',
            core, flags=_re.IGNORECASE)
        if m:
            prefix = (m.group(1) or "") + m.group(2)
            core = core[m.end():]

    # Target visual width — bigger = wider rendered button
    target = SIZE_WIDTH.get(size, 0)
    if pad > 0:
        target = max(target, _visual_len(core) + pad)

    if target <= 0 and align in ("auto", "center"):
        return label

    cur = _visual_len(core)
    extra = max(0, target - cur)

    if extra == 0 and align in ("auto", "center"):
        return label

    # Split extra into left/right based on alignment
    if align == "left":
        left, right = 0, extra
    elif align == "right":
        left, right = extra, 0
    else:  # center / auto
        left = extra // 2
        right = extra - left

    # Use Hangul Filler for padding — ye trim nahi hota kyunke ye letter hai
    def _pad(n):
        if n <= 0:
            return ""
        return PAD_CHAR * n

    # 🔧 v46: For premium-emoji buttons the ICON always renders first (Telegram
    # can't place padding before the icon). To keep emoji+text glued together
    # with the exact spacing admin set, put ALL extra padding on the RIGHT and
    # keep the icon immediately followed by its text.
    if prefix:
        return prefix + (" " if core else "") + core + _pad(left + right)
    return _pad(left) + core + _pad(right)


def wrap_button(key: str, btn: InlineKeyboardButton) -> InlineKeyboardButton:
    """
    Re-create an InlineKeyboardButton with styled label.
    Preserves callback_data / url / web_app / switch_inline_query.
    """
    if btn is None:
        return None
    new_label = style_label(key, btn.text or "")
    if new_label == (btn.text or ""):
        return btn  # no change

    kwargs = {}
    for attr in ("callback_data", "url", "web_app", "switch_inline_query",
                 "switch_inline_query_current_chat", "pay", "login_url",
                 "callback_game"):
        v = getattr(btn, attr, None)
        if v is not None:
            kwargs[attr] = v
    return InlineKeyboardButton(new_label, **kwargs)


# ── Known styler keys (for admin panel listing) ──────────────
# Dynamic keys (shop_product etc.) + registry keys are discovered on the fly.
# Categories:
#   1. Registry buttons     → reg_<button_id>
#   2. Dynamic system keys  → shop_product, prod_buy, etc.
#   3. Per-product           → prod_<product_id>     (each individual product)
#   4. Per-category          → cat_<category_id>     (each individual category)
#   5. Per-custom-button     → custom_<bid>          (each admin custom button)

# Static dynamic keys (system-wide, not tied to a specific row in DB)
EXTRA_KEYS = [
    # ── SHOP / PRODUCT LIST ──
    ("shop_product",     "🛍️ Shop — All Product Buttons (default)"),
    ("shop_pagination",  "⬅️➡️ Shop — Pagination (Prev/Next)"),
    ("shop_home",        "🏠 Shop — Home Button"),
    ("shop_buy_points",  "💎 Shop — Buy Points Button"),
    ("shop_view_all",    "📋 Shop — View All Products"),
    ("shop_category",    "📂 Shop — Category Buttons (default)"),
    ("shop_back_cats",   "🔙 Shop — Back to Categories"),
    # ── PRODUCT DETAIL ──
    ("prod_buy",         "🛒 Product Detail — Buy Now"),
    ("prod_buyx",        "🛒× Product Detail — Buy Multiple"),
    ("prod_review",      "⭐ Product Detail — View Reviews"),
    ("prod_back_shop",   "🔙 Product Detail — Back to Shop"),
    ("prod_home",        "🏠 Product Detail — Home"),
    # ── CAROUSEL ──
    ("cnav_prev",        "⬅️ Carousel — Previous"),
    ("cnav_next",        "➡️ Carousel — Next"),
    ("cnav_buy",         "🛒 Carousel — Buy Now"),
    ("cnav_list",        "📋 Carousel — List View"),
    # ── ADMIN / PAYMENT / SUBMENU ──
    ("admin_order_row",  "📦 Admin — Order Row"),
    ("pay_method",       "💳 Payment Method Buttons"),
    # ── CUSTOM BUTTONS (admin's custom buttons get this default) ──
    ("custom_default",   "🎨 Custom Buttons — Default Style"),
    ("custom_submenu",   "📂 Custom Submenu Buttons — Default Style"),
    # ── BACK / NAVIGATION (universal) ──
    ("back_btn",         "🔙 Back Buttons — Universal Default"),
    ("home_btn",         "🏠 Home Buttons — Universal Default"),
]


def list_known_keys(include_per_item=True):
    """All styleable keys: registry + dynamic + per-product + per-category + per-custom.
    Returns list of (key, friendly_name).

    Args:
        include_per_item: If True (default), include per-product, per-category,
                          and per-custom-button keys. Set False for compact view.
    """
    out = []

    # 1. Registry buttons (main menu, admin panel, etc.)
    try:
        # [v77-merge] self-bundle import removed: from button_registry import BUTTONS, GROUP_NAMES
        for bid, info in BUTTONS.items():
            grp = GROUP_NAMES.get(info.get("group", ""), info.get("group", ""))
            label = info.get("medium", bid)
            out.append((f"reg_{bid}", f"{label}  ·  {grp}"))
    except Exception:
        pass

    # 2. Static dynamic keys (shop_product, prod_buy, etc.)
    out.extend(EXTRA_KEYS)

    if not include_per_item:
        return out

    # 3. Per-product (each product gets its own override slot)
    try:
        from database import get_all_active_products
        for p in get_all_active_products():
            name = p['name'][:25]
            out.append((f"prod_{p['id']}",
                        f"🛍️ Product #{p['id']}: {name}"))
    except Exception:
        pass

    # 4. Per-category
    try:
        from database import get_all_categories
        for c in get_all_categories():
            emoji = c['emoji'] if 'emoji' in c.keys() else '🏷️'
            name = c['name'][:25]
            out.append((f"cat_{c['id']}",
                        f"{emoji} Category #{c['id']}: {name}"))
    except Exception:
        pass

    # 5. Per-custom-button (admin's custom buttons)
    try:
        from database import get_all_custom_buttons
        for b in get_all_custom_buttons():
            label = (b['label'] or '?')[:25]
            loc = b['location']
            out.append((f"custom_{b['id']}",
                        f"🎨 Custom #{b['id']}: {label} ({loc})"))
    except Exception:
        pass

    # 🆕 v49: 6. Per-product Free-Claim broadcast button
    try:
        from database import get_all_free_claim_products, get_product
        from utils import html_strip_tags, is_html_value
        for row in get_all_free_claim_products():
            pid = row.get("product_id")
            if not pid: continue
            p = get_product(pid)
            if not p: continue
            nm = p["name"]
            if is_html_value(nm):
                nm = html_strip_tags(nm)
            out.append((f"fc_btn_{pid}",
                        f"🎁 Free Claim #{pid}: {nm[:25]}"))
    except Exception:
        pass

    return out


def get_grouped_keys():
    """Return keys grouped by category for cleaner admin UI.
    Returns: dict { group_name: [(key, friendly), ...] }
    """
    groups = {
        "🏠 Main Menu Buttons":     [],
        "👑 Admin Panel Buttons":   [],
        "⚙️ Settings Buttons":       [],
        "🎨 Customization Buttons": [],
        "💳 Payment Buttons":        [],
        "🛒 Shop Screen":            [],
        "📦 Product Detail":          [],
        "🎠 Carousel":               [],
        "🎨 Custom Buttons":         [],
        "🔙 Navigation (Back/Home)": [],
        "🛍️ Individual Products":    [],
        "🏷️ Individual Categories":  [],
        "🎁 Free-Claim Buttons":     [],   # 🆕 v49
        "📌 Other":                  [],
    }

    try:
        # [v77-merge] self-bundle import removed: from button_registry import BUTTONS
        for bid, info in BUTTONS.items():
            grp = info.get("group", "")
            label = info.get("medium", bid)
            key = f"reg_{bid}"
            entry = (key, label)
            if grp == "main":           groups["🏠 Main Menu Buttons"].append(entry)
            elif grp == "admin":        groups["👑 Admin Panel Buttons"].append(entry)
            elif grp == "settings":     groups["⚙️ Settings Buttons"].append(entry)
            elif grp == "customization": groups["🎨 Customization Buttons"].append(entry)
            elif grp == "payment":      groups["💳 Payment Buttons"].append(entry)
            elif grp == "shop":         groups["🛒 Shop Screen"].append(entry)
            else:                       groups["📌 Other"].append(entry)
    except Exception:
        pass

    # Static dynamic
    shop_keys     = {"shop_product", "shop_pagination", "shop_home",
                      "shop_buy_points", "shop_view_all", "shop_category",
                      "shop_back_cats"}
    prod_keys     = {"prod_buy", "prod_buyx", "prod_review",
                      "prod_back_shop", "prod_home"}
    car_keys      = {"cnav_prev", "cnav_next", "cnav_buy", "cnav_list"}
    custom_keys   = {"custom_default", "custom_submenu"}
    nav_keys      = {"back_btn", "home_btn"}
    pay_keys      = {"pay_method"}

    for key, name in EXTRA_KEYS:
        entry = (key, name)
        if key in shop_keys:     groups["🛒 Shop Screen"].append(entry)
        elif key in prod_keys:   groups["📦 Product Detail"].append(entry)
        elif key in car_keys:    groups["🎠 Carousel"].append(entry)
        elif key in custom_keys: groups["🎨 Custom Buttons"].append(entry)
        elif key in nav_keys:    groups["🔙 Navigation (Back/Home)"].append(entry)
        elif key in pay_keys:    groups["💳 Payment Buttons"].append(entry)
        else:                    groups["📌 Other"].append(entry)

    # Per-product
    try:
        from database import get_all_active_products
        for p in get_all_active_products():
            name = p['name'][:30]
            groups["🛍️ Individual Products"].append(
                (f"prod_{p['id']}", f"#{p['id']}: {name}")
            )
    except Exception:
        pass

    # Per-category
    try:
        from database import get_all_categories
        for c in get_all_categories():
            emoji = c['emoji'] if 'emoji' in c.keys() else '🏷️'
            name = c['name'][:30]
            groups["🏷️ Individual Categories"].append(
                (f"cat_{c['id']}", f"{emoji} #{c['id']}: {name}")
            )
    except Exception:
        pass

    # Per-custom-button
    try:
        from database import get_all_custom_buttons
        for b in get_all_custom_buttons():
            label = (b['label'] or '?')[:30]
            groups["🎨 Custom Buttons"].append(
                (f"custom_{b['id']}", f"#{b['id']}: {label}")
            )
    except Exception:
        pass

    # 🆕 v49: Per-product Free-Claim buttons
    try:
        from database import get_all_free_claim_products, get_product
        from utils import html_strip_tags, is_html_value
        for row in get_all_free_claim_products():
            pid = row.get("product_id")
            if not pid: continue
            p = get_product(pid)
            if not p: continue
            nm = p["name"]
            if is_html_value(nm):
                nm = html_strip_tags(nm)
            groups["🎁 Free-Claim Buttons"].append(
                (f"fc_btn_{pid}", f"#{pid}: {nm[:30]}")
            )
    except Exception:
        pass

    # Remove empty groups
    return {g: items for g, items in groups.items() if items}


# ── Pretty status for admin UI ───────────────────────────────
def style_summary(key: str) -> str:
    s = get_style(key)
    parts = []
    if s["size"] != "auto":
        parts.append({"small": "S", "medium": "M",
                      "large": "L", "xl": "XL", "full": "F"}.get(s["size"], s["size"]))
    if s["align"] != "auto":
        parts.append({"left": "⇤", "center": "↔", "right": "⇥"}[s["align"]])
    if s["pad"] > 0:
        parts.append(f"+{s['pad']}")
    return " ".join(parts) if parts else "default"


# ============================================================
# 📄 ORIGINAL FILE: button_actions.py
# ============================================================

# ============================================================
# 🎯 BUTTON ACTIONS — What happens when a custom button is clicked
# ============================================================
#
# HOW CUSTOM BUTTONS WORK (Read this first!):
# ─────────────────────────────────────────────
# When admin adds a Custom Button in the bot's Admin Panel, they need to:
#
#   STEP 1 → Choose a LOCATION  (where the button appears — e.g. Main Menu)
#   STEP 2 → Give it a LABEL    (what the button says — e.g. "📢 Announcement")
#   STEP 3 → Choose an ACTION   (what it DOES when clicked — e.g. show a message)
#   STEP 4 → Enter a VALUE      (only some actions need this — e.g. the message text)
#
# That's it! No coding needed. Just fill those 3-4 fields in Admin Panel.
#
# ──────────────────────────────────────────────────────────────
# 📋 QUICK REFERENCE — All Available Action Types:
# ──────────────────────────────────────────────────────────────
#
#   🔗 url            → Opens a website or Telegram link in browser
#   📝 text           → Shows a custom text message to user
#   📂 submenu        → Opens a submenu with more buttons inside
#   📄 page           → Shows a rich content page (text + image)
#   🧭 nav            → Goes to a built-in screen (Shop, Account, Orders, etc.)
#   🛒 buy_product    → Starts purchase flow for a specific product
#   💎 buy_points_amt → Lets user quickly buy a preset number of points
#   📱 whatsapp       → Opens WhatsApp chat with your number
#   📧 email          → Opens email compose window
#   💬 telegram_chat  → Opens a Telegram chat/channel
#   ☎️  phone_call     → Opens phone dialer
#   🔔 alert          → Shows a small popup notification (no screen change)
#   📋 copy           → Shows text for user to copy (e.g. promo code)
#   📤 share_bot      → Generates user's referral link and lets them share
#   📸 send_photo     → Sends a stored photo to user
#   🎬 send_video     → Sends a stored video to user
#   📎 send_document  → Sends a stored file (PDF, ZIP, etc.) to user
#   🎵 send_audio     → Sends a stored audio/voice to user
#   🌐 webapp         → Opens a Telegram Mini App (needs HTTPS URL)
#   ⚡ command        → Runs a bot command (e.g. /start)
#
# ──────────────────────────────────────────────────────────────

import re


# ════════════════════════════════════════════════════════════════
# 🔍 VALIDATORS — These check if the value entered is correct
# ════════════════════════════════════════════════════════════════
# Each validator returns: (True/False, "error message if False")
# Admin will see the error message if they enter something wrong.

def _v_url(v):
    """
    Checks if a URL is valid.
    Must start with http://, https://, or tg://
    Example: https://t.me/yourchannel
    """
    if not v:
        return False, "URL cannot be empty."
    if not (v.startswith("http://") or v.startswith("https://") or v.startswith("tg://")):
        return False, "URL must start with http://, https://, or tg://"
    if len(v) > 500:
        return False, "URL is too long (max 500 characters)."
    return True, ""


def _v_text(v):
    """
    Checks if a text message is valid.
    Supports Markdown: *bold*, _italic_, `code`
    Max 4000 characters.
    """
    if not v:
        return False, "Message text cannot be empty."
    if len(v) > 4000:
        return False, "Message is too long (max 4000 characters)."
    return True, ""


def _v_callback(v):
    """
    Checks if a navigation target is valid.
    Must match one of the built-in screen IDs in NAVIGATION_TARGETS below.
    """
    valid = {t["id"] for t in NAVIGATION_TARGETS}
    if v in valid:
        return True, ""
    return False, "Invalid screen. Please choose from the picker."


def _v_username(v):
    """
    Checks if a Telegram username is valid.
    Can be entered with or without @ sign.
    Example: @mybotname  or  mybotname
    """
    v = v.lstrip("@")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]{4,31}$", v):
        return False, "Invalid username. Example: @yourchannel or yourchannel"
    return True, ""


def _v_phone(v):
    """
    Checks if a phone number is valid.
    Must be 7 to 15 digits with country code.
    Example: 923001234567  (92 = Pakistan, 300 = Jazz, 1234567 = number)
    """
    digits = re.sub(r"\D", "", v)
    if len(digits) < 7 or len(digits) > 15:
        return False, "Invalid phone number. Use country code format (e.g. 923001234567)."
    return True, ""


def _v_email(v):
    """
    Checks if an email address is valid.
    Example: support@mystore.com
    """
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
        return False, "Invalid email format. Example: support@mystore.com"
    return True, ""


def _v_file_id(v):
    """
    Checks if a Telegram File ID is valid.
    File ID is given automatically when admin uploads a photo/video/file.
    Admin doesn't need to type this manually — bot handles it.
    """
    if not v or len(v) < 10:
        return False, "Invalid File ID. Please upload the file to get its ID."
    return True, ""


def _v_alert(v):
    """
    Checks if an alert/popup message is valid.
    Must be short — max 200 characters.
    Example: "Promo code: SAVE20"
    """
    if not v:
        return False, "Alert message cannot be empty."
    if len(v) > 200:
        return False, "Alert message is too long (max 200 characters)."
    return True, ""


def _v_none(v):
    """No value needed — always valid."""
    return True, ""


# ════════════════════════════════════════════════════════════════
# 🧭 NAVIGATION TARGETS
# ════════════════════════════════════════════════════════════════
# These are the built-in screens that a 'nav' action button can go to.
# When admin picks action type = "Open Built-in Menu", they choose
# one of these destinations from a picker list.
#
# HOW TO USE:
#   Action Type  → "🧭 Open Built-in Menu"
#   Destination  → Pick one from list below (e.g. "Shop")
#   Result       → Clicking the button opens the Shop screen

NAVIGATION_TARGETS = [
    {"id": "main_menu",     "icon": "🏠", "label": "Main Menu",         "callback": "main_menu"},
    {"id": "shop",          "icon": "🛍️", "label": "Shop",              "callback": "shop"},
    {"id": "my_account",    "icon": "👤", "label": "My Account",        "callback": "my_account"},
    {"id": "my_orders",     "icon": "📦", "label": "My Orders",         "callback": "my_orders"},
    {"id": "buy_points",    "icon": "💎", "label": "Buy Points",        "callback": "buy_points"},
    {"id": "transactions",  "icon": "📜", "label": "Transactions",      "callback": "transactions"},
    {"id": "referral",      "icon": "🎁", "label": "Referral",          "callback": "referral"},
    {"id": "support_menu",  "icon": "🎫", "label": "Support",           "callback": "support_menu"},
    {"id": "warranty_menu", "icon": "🛡️", "label": "Warranty / Refund", "callback": "warranty_menu"},
    {"id": "reviews_menu",  "icon": "⭐", "label": "Reviews",           "callback": "reviews_menu"},
    {"id": "loyalty_menu",  "icon": "🏆", "label": "Loyalty Program",   "callback": "loyalty_menu"},
    {"id": "language_menu", "icon": "🌐", "label": "Language Settings", "callback": "language_menu"},
    {"id": "admin_panel",   "icon": "👑", "label": "Admin Panel",       "callback": "admin_panel"},
    {"id": "go_back",       "icon": "🔙", "label": "Back (Previous)",   "callback": "go_back"},
]


# ════════════════════════════════════════════════════════════════
# 📍 BUTTON LOCATIONS
# ════════════════════════════════════════════════════════════════
# These are the screens where a custom button can be PLACED/SHOWN.
# When admin creates a custom button, they pick where it appears.
#
# HOW TO USE:
#   In Admin Panel → Custom Buttons → Add Button → "Where to show?"
#   Pick a location from this list.
#
# EXAMPLES:
#   "Main Menu"       → Button appears on the first screen users see
#   "Shop Screen"     → Button appears when user is browsing products
#   "My Account"      → Button appears on user's profile screen
#   "Support Screen"  → Button appears in the support/help section

BUTTON_LOCATIONS = [
    {"id": "main",          "icon": "🏠", "label": "Main Menu"},
    {"id": "admin",         "icon": "👑", "label": "Admin Panel"},
    {"id": "settings",      "icon": "⚙️", "label": "Settings"},
    {"id": "customization", "icon": "🎨", "label": "Customization"},
    {"id": "my_account",    "icon": "👤", "label": "My Account Screen"},
    {"id": "shop",          "icon": "🛍️", "label": "Shop Screen"},
    {"id": "my_orders",     "icon": "📦", "label": "My Orders Screen"},
    {"id": "support",       "icon": "🎫", "label": "Support Screen"},
    {"id": "warranty",      "icon": "🛡️", "label": "Warranty Screen"},
    {"id": "reviews",       "icon": "⭐", "label": "Reviews Screen"},
    {"id": "loyalty",       "icon": "🏆", "label": "Loyalty Screen"},
    {"id": "payment",       "icon": "💳", "label": "Payment Screen"},
    {"id": "product_detail","icon": "📦", "label": "Product Detail (all products)"},
    {"id": "transactions",  "icon": "📜", "label": "Transactions Screen"},
    {"id": "referral",      "icon": "🎁", "label": "Referral Screen"},
    {"id": "buy_points",    "icon": "💎", "label": "Buy Points Screen"},
]


# ════════════════════════════════════════════════════════════════
# 🎯 ACTION TYPES
# ════════════════════════════════════════════════════════════════
# This is the main list — every possible action a custom button can do.
#
# Each action has these fields:
#   id           → Internal code (don't change these)
#   icon         → Emoji shown in Admin Panel
#   label        → Short name shown in Admin Panel
#   description  → Explanation shown to admin (what does this action do?)
#   needs_value  → Does admin need to enter extra info? True or False
#   value_hint   → Instruction shown to admin: what value to enter
#   validator    → Function that checks if the entered value is correct
#
# ──────────────────────────────────────────────────────────────
# 📌 HOW TO READ EACH ACTION:
#
#   needs_value = False  → Just pick the action, no extra input needed
#   needs_value = True   → Admin must also enter a value (URL, text, etc.)
#                          The "value_hint" field tells them exactly what to type
# ──────────────────────────────────────────────────────────────

ACTION_TYPES = [

    # ════════════════════════════════════
    # 📌 SECTION 1 — CONTENT ACTIONS
    # Show something to the user when they click the button
    # ════════════════════════════════════

    {
        "id": "url",
        "icon": "🔗",
        "label": "URL Link",
        "description": (
            "Opens a website or Telegram link in the user's browser.\n"
            "Use for: website, channel link, Instagram, YouTube, etc."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter a full URL.\n"
            "Examples:\n"
            "  https://t.me/yourchannel\n"
            "  https://yourwebsite.com\n"
            "  tg://resolve?domain=username"
        ),
        "validator": _v_url,
    },

    {
        "id": "text",
        "icon": "📝",
        "label": "Show Text Message",
        "description": (
            "Sends a custom text message to the user when they click.\n"
            "Use for: announcements, rules, info, FAQs, any custom message.\n"
            "Supports Telegram Markdown formatting."
        ),
        "needs_value": True,
        "value_hint": (
            "Type the message you want to show.\n"
            "Markdown is supported:\n"
            "  *bold text*\n"
            "  _italic text_\n"
            "  `inline code`\n"
            "  [link text](https://url.com)\n"
            "Max 4000 characters."
        ),
        "validator": _v_text,
    },

    {
        "id": "alert",
        "icon": "🔔",
        "label": "Popup Alert (Toast)",
        "description": (
            "Shows a small popup notification at top of screen.\n"
            "Screen does NOT change — it's just a quick notification.\n"
            "Use for: short tips, reminders, promo codes."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter a short message (max 200 characters).\n"
            "Examples:\n"
            "  Promo code: SAVE20\n"
            "  Sale ends tonight!"
        ),
        "validator": _v_alert,
    },

    {
        "id": "copy",
        "icon": "📋",
        "label": "Copy Text (Promo Code etc.)",
        "description": (
            "Shows the text to user so they can copy it.\n"
            "Use for: promo codes, wallet addresses, account numbers, any copyable text."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter the text to copy.\n"
            "Examples:\n"
            "  DISCOUNT50\n"
            "  0x1234abcd5678...  (wallet address)\n"
            "Max 200 characters."
        ),
        "validator": _v_alert,
    },

    {
        "id": "page",
        "icon": "📄",
        "label": "Custom Page (Text + Image)",
        "description": (
            "Opens a rich content page with text and optional image.\n"
            "Pages are created separately in Admin Panel → Pages.\n"
            "Use for: product announcements, tutorials, menus, rules."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter the Page ID.\n"
            "How to find Page ID:\n"
            "  Admin Panel → Custom Pages → see number next to each page.\n"
            "Example: 3"
        ),
        "validator": lambda v: (
            (bool(v) and v.isdigit() and int(v) > 0),
            "" if (bool(v) and v.isdigit() and int(v) > 0) else "Enter a valid Page ID (a positive number)."
        ),
    },


    # ════════════════════════════════════
    # 📌 SECTION 2 — NAVIGATION ACTIONS
    # Take the user to a different screen inside the bot
    # ════════════════════════════════════

    {
        "id": "nav",
        "icon": "🧭",
        "label": "Go to Built-in Screen",
        "description": (
            "Takes the user to one of the bot's existing screens.\n"
            "Use for: shortcut to Shop, Account, Orders, Support, etc.\n"
            "Choose destination from the picker that appears."
        ),
        "needs_value": True,
        "value_hint": (
            "Choose a destination screen from the picker.\n"
            "Available screens:\n"
            "  🏠 Main Menu\n"
            "  🛍️ Shop\n"
            "  👤 My Account\n"
            "  📦 My Orders\n"
            "  💎 Buy Points\n"
            "  🎁 Referral\n"
            "  🎫 Support\n"
            "  🔙 Back (previous screen)\n"
            "  ... and more"
        ),
        "validator": _v_callback,
    },

    {
        "id": "submenu",
        "icon": "📂",
        "label": "Open a Submenu",
        "description": (
            "Opens a nested submenu with more buttons inside.\n"
            "Use for: grouping related buttons together.\n"
            "Example: 'Contact Us' button → submenu with WhatsApp, Email, Telegram.\n"
            "No value needed — just create the submenu buttons separately."
        ),
        "needs_value": False,
        "value_hint": "",
        "validator": _v_none,
    },

    {
        "id": "command",
        "icon": "⚡",
        "label": "Run a Bot Command",
        "description": (
            "Runs a bot command as if the user typed it.\n"
            "Use for: shortcuts to /start, /admin, or other commands."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter the command with / at the start.\n"
            "Examples:\n"
            "  /start\n"
            "  /admin\n"
            "  /help"
        ),
        "validator": lambda v: (
            (bool(v) and v.startswith("/") and len(v) > 1),
            "" if (bool(v) and v.startswith("/") and len(v) > 1) else "Command must start with / (e.g. /start)"
        ),
    },


    # ════════════════════════════════════
    # 📌 SECTION 3 — SHOP ACTIONS
    # Directly trigger buying/payment flows
    # ════════════════════════════════════

    {
        "id": "buy_product",
        "icon": "🛒",
        "label": "Buy Specific Product",
        "description": (
            "Directly starts the purchase flow for one specific product.\n"
            "User clicks → immediately sees that product's buy screen.\n"
            "Use for: featured product button, promotional button for a specific item."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter the Product ID.\n"
            "How to find Product ID:\n"
            "  Admin Panel → Items → see number next to each product.\n"
            "Example: 5"
        ),
        "validator": lambda v: (
            (bool(v) and v.isdigit() and int(v) > 0),
            "" if (bool(v) and v.isdigit() and int(v) > 0) else "Enter a valid Product ID (a positive number)."
        ),
    },

    {
        "id": "buy_points_amount",
        "icon": "💎",
        "label": "Quick Buy Points (Preset Amount)",
        "description": (
            "Lets user instantly buy a specific preset number of points.\n"
            "User clicks → goes directly to payment for that points amount.\n"
            "Use for: '💎 Buy 100 Points' or '💎 Top Up $5' shortcut buttons."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter the number of points.\n"
            "Examples:\n"
            "  100\n"
            "  500\n"
            "  1000"
        ),
        "validator": lambda v: (
            (bool(v) and v.isdigit() and int(v) > 0),
            "" if (bool(v) and v.isdigit() and int(v) > 0) else "Enter a positive number (e.g. 100)."
        ),
    },


    # ════════════════════════════════════
    # 📌 SECTION 4 — CONTACT ACTIONS
    # Open external contact apps
    # ════════════════════════════════════

    {
        "id": "whatsapp",
        "icon": "📱",
        "label": "Open WhatsApp Chat",
        "description": (
            "Opens WhatsApp and starts a chat with your number.\n"
            "Use for: customer support, direct contact button."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter phone number WITH country code (no spaces or dashes).\n"
            "Examples:\n"
            "  923001234567   (Pakistan +92)\n"
            "  14155552671    (USA +1)\n"
            "  447911123456   (UK +44)"
        ),
        "validator": _v_phone,
    },

    {
        "id": "telegram_chat",
        "icon": "💬",
        "label": "Open Telegram Chat / Channel",
        "description": (
            "Opens a specific Telegram chat, channel, or user profile.\n"
            "Use for: directing users to your support account, channel, or group."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter the Telegram username.\n"
            "Examples:\n"
            "  @yourchannel\n"
            "  yourchannel   (without @ also works)"
        ),
        "validator": _v_username,
    },

    {
        "id": "email",
        "icon": "📧",
        "label": "Send Email",
        "description": (
            "Opens the user's email app with your address pre-filled.\n"
            "Use for: formal support contact, order queries via email."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter your email address.\n"
            "Example:\n"
            "  support@mystore.com"
        ),
        "validator": _v_email,
    },

    {
        "id": "phone_call",
        "icon": "☎️",
        "label": "Phone Call",
        "description": (
            "Opens the phone dialer with your number pre-filled.\n"
            "Use for: direct call support button."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter phone number WITH country code (no spaces or dashes).\n"
            "Examples:\n"
            "  923001234567   (Pakistan)\n"
            "  14155552671    (USA)"
        ),
        "validator": _v_phone,
    },


    # ════════════════════════════════════
    # 📌 SECTION 5 — MEDIA ACTIONS
    # Send files to the user when they click
    # ════════════════════════════════════

    {
        "id": "send_photo",
        "icon": "📸",
        "label": "Send Photo",
        "description": (
            "Sends a photo to the user when they click the button.\n"
            "Use for: product images, banners, guides, menus.\n"
            "Admin uploads the photo during button setup — File ID is saved automatically."
        ),
        "needs_value": True,
        "value_hint": (
            "Upload a photo when prompted.\n"
            "The bot will save the File ID automatically.\n"
            "You do NOT need to enter anything manually."
        ),
        "validator": _v_file_id,
    },

    {
        "id": "send_video",
        "icon": "🎬",
        "label": "Send Video",
        "description": (
            "Sends a video to the user when they click the button.\n"
            "Use for: tutorial videos, product demos, ads."
        ),
        "needs_value": True,
        "value_hint": (
            "Upload a video when prompted.\n"
            "The bot will save the File ID automatically."
        ),
        "validator": _v_file_id,
    },

    {
        "id": "send_document",
        "icon": "📎",
        "label": "Send Document / File",
        "description": (
            "Sends a file to the user when they click the button.\n"
            "Use for: PDF guides, ZIP files, invoices, account credentials file."
        ),
        "needs_value": True,
        "value_hint": (
            "Upload a document/file when prompted.\n"
            "The bot will save the File ID automatically.\n"
            "Supports: PDF, ZIP, TXT, DOCX, etc."
        ),
        "validator": _v_file_id,
    },

    {
        "id": "send_audio",
        "icon": "🎵",
        "label": "Send Audio / Voice",
        "description": (
            "Sends an audio file or voice message to the user.\n"
            "Use for: voice announcements, audio guides."
        ),
        "needs_value": True,
        "value_hint": (
            "Upload an audio file when prompted.\n"
            "The bot will save the File ID automatically."
        ),
        "validator": _v_file_id,
    },


    # ════════════════════════════════════
    # 📌 SECTION 6 — ADVANCED ACTIONS
    # Special features for advanced use
    # ════════════════════════════════════

    {
        "id": "share_bot",
        "icon": "📤",
        "label": "Share Bot (Referral Link)",
        "description": (
            "Automatically generates the user's unique referral link.\n"
            "Opens Telegram share dialog so they can forward it to friends.\n"
            "Use for: referral program promotion button.\n"
            "No value needed."
        ),
        "needs_value": False,
        "value_hint": "",
        "validator": _v_none,
    },

    {
        "id": "webapp",
        "icon": "🌐",
        "label": "Open Mini App (Telegram WebApp)",
        "description": (
            "Opens a Telegram Mini App (WebApp) inside the bot.\n"
            "Use for: custom web interfaces, games, advanced forms.\n"
            "Requires a working HTTPS website URL."
        ),
        "needs_value": True,
        "value_hint": (
            "Enter the HTTPS URL of your WebApp.\n"
            "Must start with https:// (not http://).\n"
            "Example:\n"
            "  https://myapp.vercel.app"
        ),
        "validator": lambda v: (
            v.startswith("https://"),
            "" if v.startswith("https://") else "WebApp URL must start with https://"
        ),
    },

]


# ════════════════════════════════════════════════════════════════
# 🛠️ HELPER FUNCTIONS
# Used by the bot internally — admin does not interact with these
# ════════════════════════════════════════════════════════════════

def get_action(action_id):
    """Find and return an action by its id. Returns None if not found."""
    for a in ACTION_TYPES:
        if a["id"] == action_id:
            return a
    return None


def get_location(loc_id):
    """
    Find and return a location by its id.
    Also handles submenu locations which start with 'sub_'
    """
    if loc_id and loc_id.startswith("sub_"):
        return {"id": loc_id, "icon": "📂", "label": f"Inside Submenu #{loc_id[4:]}"}
    for loc in BUTTON_LOCATIONS:
        if loc["id"] == loc_id:
            return loc
    return {"id": loc_id, "icon": "❓", "label": loc_id or "Unknown"}


def get_nav_target(target_id):
    """Find and return a navigation target by its id. Returns None if not found."""
    for t in NAVIGATION_TARGETS:
        if t["id"] == target_id:
            return t
    return None


def action_icon(action_id):
    """Returns the emoji icon for an action. Returns ❓ if action not found."""
    a = get_action(action_id)
    return a["icon"] if a else "❓"


def action_label(action_id):
    """Returns the display label for an action. Returns the raw id if not found."""
    a = get_action(action_id)
    return a["label"] if a else action_id


def location_label(loc_id):
    """Returns formatted 'icon label' string for a location."""
    loc = get_location(loc_id)
    return f"{loc['icon']} {loc['label']}"


def validate_action_value(action_id, value):
    """
    Validates the value entered by admin for a given action type.
    Returns (is_valid: bool, error_message: str)

    Usage example:
        ok, err = validate_action_value("url", "https://example.com")
        if not ok:
            print(f"Error: {err}")
    """
    action = get_action(action_id)
    if not action:
        return False, f"Unknown action type: {action_id}"
    if not action["needs_value"]:
        return True, ""  # No value needed for this action
    validator = action.get("validator", _v_none)
    return validator(value)


# ============================================================
# 📄 ORIGINAL FILE: button_colors.py
# ============================================================

"""
🆕 v46: Telegram Premium Button Background Colors
Supported colors for Premium users
"""

BUTTON_COLORS = {
    "red": "🔴",
    "orange": "🟠",
    "yellow": "🟡",
    "green": "🟢",
    "blue": "🔵",
    "purple": "🟣",
    "brown": "🟤",
    "black": "⚫",
    "white": "⚪",
    "none": "⬜"
}

def get_color_emoji(color_key):
    return BUTTON_COLORS.get(color_key, "⬜")

def color_picker_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = []
    row = []
    for key, emoji in BUTTON_COLORS.items():
        row.append(InlineKeyboardButton(f"{emoji} {key.title()}", callback_data=f"btncolor_{key}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton("❌ No Color", callback_data="btncolor_none")])
    return InlineKeyboardMarkup(kb)

# ============================================================
# 📄 ORIGINAL FILE: button_text_editor.py
# ============================================================

# ============================================================
# 📝 BUTTON TEXT EDITOR — v1
# ============================================================
# Admin can edit the TEXT (label) of inline buttons that appear
# inside fake-activity / broadcast / template messages.
#
# Why this exists:
#   - Telegram does NOT allow custom/premium emojis inside button
#     labels (only in message body). So this editor focuses on
#     standard text + standard emojis the admin types.
#   - Admin can change "🛒 Buy Now" → "💎 Shop Now" or whatever
#     they like, per-button-type.
#
# Stored in `bot_settings` as `btn_text_<key>` (string).
# If unset → default (passed by caller) is used.
# ============================================================

from typing import Dict, List, Tuple


# Registry of button keys we expose to the admin.
# (key, default_label, friendly_name, where_used)
BUTTON_KEYS: List[Tuple[str, str, str, str]] = [
    # ── Fake Activity / Per-User Activity buttons ──
    ("act_buy_purchase",  "🛒 Buy Now", "🛒 Fake Activity — Purchase",   "When fake 'New Purchase' message goes"),
    ("act_buy_discount",  "🛒 Buy Now", "🛒 Fake Activity — Discount",   "When fake 'Price Drop' goes"),
    ("act_buy_review",    "🛒 Buy Now", "🛒 Fake Activity — Review",     "When fake review message goes"),
    ("act_buy_stock",     "🛒 Buy Now", "🛒 Fake Activity — Stock Alert","When 'New stock available' goes"),
    ("act_buy_newprod",   "🛒 Buy Now", "🛒 Fake Activity — New Product","When 'New product added' goes"),

    # ── Store Broadcast (Flash / New product / Tier) ──
    ("sb_buy_flash",      "🛒 Buy Now", "⚡ Store Broadcast — Flash Sale Buy",       "Flash sale broadcast"),
    ("sb_buy_newprod",    "🛒 Buy Now", "🆕 Store Broadcast — New Product Buy",      "New product broadcast"),
    ("sb_buy_generic",    "🛒 Buy Now", "🛍️ Store Broadcast — Generic Buy",          "Other store broadcasts"),

    # ── Universal fallback ──
    ("buy_now_default",   "🛒 Buy Now", "🛒 Universal Default Buy Now",  "Fallback for any unrecognized broadcast"),
]


def _setting_key(key: str) -> str:
    return f"btn_text_{key}"


def get_button_text(key: str, default: str = None) -> str:
    """Get admin-customized label for a button key.
    Falls back to provided default → registry default → key itself.
    """
    try:
        from database import get_setting
        val = get_setting(_setting_key(key), "")
    except Exception:
        val = ""
    if val:
        return val
    if default is not None:
        return default
    # Lookup registry default
    for k, d, _, _ in BUTTON_KEYS:
        if k == key:
            return d
    return key


def set_button_text(key: str, text: str):
    """Persist a custom button label. Empty string clears it (uses default)."""
    try:
        from database import set_setting
        set_setting(_setting_key(key), text or "")
    except Exception:
        pass


def reset_button_text(key: str):
    set_button_text(key, "")


def reset_all_button_texts():
    for k, _, _, _ in BUTTON_KEYS:
        reset_button_text(k)


def list_button_keys() -> List[Tuple[str, str, str, str]]:
    """Return the registry as-is."""
    return list(BUTTON_KEYS)


def get_button_state() -> Dict[str, Dict[str, str]]:
    """For UI rendering: returns dict of key → {current, default, friendly, where}."""
    out = {}
    for k, d, friendly, where in BUTTON_KEYS:
        out[k] = {
            "current": get_button_text(k, d),
            "default": d,
            "friendly": friendly,
            "where": where,
            "is_custom": get_button_text(k, d) != d,
        }
    return out


# ============================================================
# 📄 ORIGINAL FILE: template_buttons.py
# ============================================================

# ============================================================
# 🔘 PER-TEMPLATE BUTTON TEXT EDITOR — v43
# ============================================================
# Har broadcast/fake-activity template ke ander hi uska button
# (e.g. "🛒 Buy Now") customize karne ka backend.
#
# Storage (DB `bot_settings`):
#   tplbtn_<tpl_id>           → button label text (str, may be "")
#   tplbtnemoji_<tpl_id>      → custom_emoji_id for icon (str, may be "")
#                                Bot API 9.4 (Feb 2026) — bot owner needs
#                                Telegram Premium for this to render.
#
# Templates that HAVE a Buy-Now style button:
#   bc_purchase   → "🛒 Buy Now" → activity_buy_<pid>
#   bc_discount   → "🛒 Buy Now"
#   bc_review     → "🛒 Buy Now"
#   bc_stock      → "🛒 Buy Now"
#   bc_new_user   → no button (just a notice)
#   bc_deposit    → no button
#   bc_referral   → no button
#   bc_active_referral → no button
#   bc_tier       → no button
#
# Store broadcasts (Flash Sale / New Product etc.) also use this same
# system via tpl_id mappings declared below.
# ============================================================

# Mapping of every template_id → default button label (or None if no button)
TEMPLATE_BUTTONS = {
    # ── Fake broadcast / activity ──
    "bc_purchase":         "🛒 Buy Now",
    "bc_discount":         "🛒 Buy Now",
    "bc_review":           "🛒 Buy Now",
    "bc_stock":            "🛒 Buy Now",
    "bc_newprod":          "🛒 Buy Now",     # if you add this template
    "bc_new_user":         None,             # no button
    "bc_deposit":          None,
    "bc_referral":         None,
    "bc_active_referral":  None,
    "bc_tier":             None,
    # ── Store broadcast ──
    "sb_flash":            "🛒 Buy Now",
    "sb_newprod":          "🛒 Buy Now",
    "sb_generic":          "🛒 Buy Now",
    # ── Review pools — no buttons ──
    "rv_urdu":             None,
    "rv_english":          None,
}


def _setting_text_key(tpl_id):
    return f"tplbtn_{tpl_id}"


def _setting_emoji_key(tpl_id):
    return f"tplbtnemoji_{tpl_id}"


def template_has_button(tpl_id):
    """True if this template normally ships with an inline Buy-Now button."""
    return TEMPLATE_BUTTONS.get(tpl_id) is not None


def get_button_text(tpl_id, default=None):
    """Return the (possibly admin-customised) button text for a template.
    Falls back to default → registry default → '🛒 Buy Now'."""
    try:
        from database import get_setting
        v = get_setting(_setting_text_key(tpl_id), "")
    except Exception:
        v = ""
    if v:
        return v
    if default is not None:
        return default
    return TEMPLATE_BUTTONS.get(tpl_id) or "🛒 Buy Now"


def get_button_emoji_id(tpl_id):
    """Return the custom_emoji_id (str) saved for this template's button icon,
    or '' if none."""
    try:
        from database import get_setting
        return get_setting(_setting_emoji_key(tpl_id), "") or ""
    except Exception:
        return ""


def set_button(tpl_id, text="", emoji_id=""):
    """Persist customized text + (optional) custom_emoji_id for a button.
    Pass empty strings to clear (use defaults)."""
    try:
        from database import set_setting
        set_setting(_setting_text_key(tpl_id), text or "")
        set_setting(_setting_emoji_key(tpl_id), emoji_id or "")
    except Exception:
        pass


def reset_button(tpl_id):
    set_button(tpl_id, "", "")


def extract_custom_emoji(message):
    """Inspect a Telegram Message and pull out (custom_emoji_id, plain_text).

    Returns: (emoji_id or '', plain_text without leading custom_emoji char)
      - emoji_id: the FIRST custom_emoji entity's id (if any)
      - plain_text: the message's plain text, with the fallback char of the
                    custom emoji stripped from the front if it was there.

    Why: For Telegram inline button labels we MUST send plain text (string),
    AND optionally `icon_custom_emoji_id` (which Telegram renders BEFORE
    the text automatically). If admin typed "🔥 Buy Now" where 🔥 is a
    PREMIUM custom emoji, we should:
      - save emoji_id = "<the id>"
      - save text     = "Buy Now"
    So at render time the button shows: [premium-🔥] Buy Now
    """
    if message is None:
        return "", ""
    text = message.text or ""
    entities = message.entities or []

    first_ce = None
    for e in entities:
        if getattr(e, "type", "") == "custom_emoji":
            first_ce = e
            break

    if not first_ce:
        return "", text

    emoji_id = getattr(first_ce, "custom_emoji_id", "") or ""

    # If the custom emoji is at the very start, strip its fallback char
    # so it doesn't appear twice in the rendered button (icon + same char).
    offset = getattr(first_ce, "offset", -1)
    length = getattr(first_ce, "length", 0)
    if offset == 0 and length > 0:
        stripped = text[length:].lstrip()
        return emoji_id, stripped

    return emoji_id, text


def build_button(tpl_id, default_text="🛒 Buy Now", *,
                 callback_data=None, url=None, web_app=None):
    """Construct an InlineKeyboardButton honouring admin's per-template
    customisations.

    - Uses admin's saved text if any (else default_text).
    - If admin saved a custom_emoji_id we attach `icon_custom_emoji_id` so
      Telegram shows the PREMIUM emoji icon before the button text
      (Bot API 9.4 / Feb 2026).

    🔧 v44 FIX: Earlier we tried `InlineKeyboardButton(..., icon_custom_emoji_id=...)`
    which silently became a no-op on PTB < 22.7 (TypeError caught). That meant
    even when admin saw "detected!" message, the icon NEVER reached Telegram
    if the running PTB was older. We now ALSO inject the field via PTB's
    public `api_kwargs` parameter which is preserved during JSON serialization
    on EVERY PTB version (>= 20.x). So the icon goes out regardless of PTB
    version — Telegram server then decides if it can render it (requires:
    bot owner has Telegram Premium ✅ + chat is private/group/supergroup).
    """
    from telegram import InlineKeyboardButton
    text = get_button_text(tpl_id, default_text)
    emoji_id = get_button_emoji_id(tpl_id)

    kwargs = {}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if web_app is not None:
        kwargs["web_app"] = web_app

    if not emoji_id:
        return InlineKeyboardButton(text, **kwargs)

    # Path A: Modern PTB (>=22.7) accepts the kwarg natively. Best path.
    try:
        return InlineKeyboardButton(text,
                                    icon_custom_emoji_id=str(emoji_id),
                                    **kwargs)
    except TypeError:
        pass  # Older PTB — try the universal path below

    # Path B: Universal — inject via api_kwargs (PTB ≥ 20 supports this).
    # The value lands in the JSON sent to Telegram's HTTP API verbatim.
    try:
        return InlineKeyboardButton(
            text,
            api_kwargs={"icon_custom_emoji_id": str(emoji_id)},
            **kwargs,
        )
    except TypeError:
        pass

    # Path C: Absolute fallback — plain button (still better than crashing).
    return InlineKeyboardButton(text, **kwargs)


# ════════════════════════════════════════════════════════════════
# 🆕 v45: GLOBAL premium-emoji-aware button factory
# ════════════════════════════════════════════════════════════════
# Yeh function bot ki har jagah use ho sakta hai jaha
# InlineKeyboardButton banti hai. Yeh automatically detect karta hai:
#
#   • Agar label me [[HTML]]<tg-emoji emoji-id="X">f</tg-emoji>... ho
#     to first <tg-emoji> ki ID extract karke icon_custom_emoji_id me
#     daal deta hai, aur baqi text plain button label me chala jata hai.
#   • Agar label sirf plain text/emoji hai to wese hi normal button banta hai.
#   • Agar admin ne explicit emoji_id pass kiya ho to woh use hoti hai.
#
# Use case examples:
#   from template_buttons import make_premium_button
#   btn = make_premium_button("[[HTML]]<tg-emoji emoji-id='5301...'>🔥</tg-emoji> ChatGPT",
#                              callback_data="prod_1")
#   # → button with premium icon + text "ChatGPT"


def extract_emoji_from_html(html_label):
    """Parse a label that may contain [[HTML]]...<tg-emoji emoji-id="X">F</tg-emoji>...
    and return (emoji_id, plain_text_WITHOUT_the_premium_emoji_char).

    🔧 BUGFIX (double emoji): When a premium emoji is present, it renders as the
    button ICON (icon_custom_emoji_id). The fallback char `F` is therefore
    REMOVED from the returned text — otherwise the same emoji appeared twice
    (once as the premium icon, once as a plain char in the text).

    Notes:
      - The premium icon only renders when the bot OWNER has Telegram Premium.
      - Only the FIRST <tg-emoji> is treated as the icon; any other plain emojis
        in the text are left as-is.

    If no <tg-emoji> tag is found → returns ("", original_text_stripped_of_html)
    with all normal emojis/text preserved.
    """
    if not html_label:
        return "", ""
    import re

    def _unescape(x):
        return (x.replace("&amp;", "&").replace("&lt;", "<")
                 .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))

    s = str(html_label)
    # Strip the sentinel (anywhere, not just leading)
    s = s.replace("[[HTML]]", "")
    # Match a <tg-emoji emoji-id="X">F</tg-emoji> AT/NEAR THE START
    # (allowing optional leading whitespace)
    m = re.match(
        r'^\s*<tg-emoji\s+emoji-id=["\'](?P<id>\d+)["\']\s*>'
        r'(?P<fallback>[^<]*)</tg-emoji>\s*',
        s, flags=re.IGNORECASE,
    )
    if m:
        emoji_id = m.group("id")
        rest = s[m.end():]
        rest = re.sub(r"<[^>]+>", "", rest)
        rest = _unescape(rest).strip()
        # 🔧 Drop the fallback char — the premium icon already shows the emoji
        return emoji_id, rest

    # No leading tg-emoji — also search anywhere (still extract first one)
    m2 = re.search(
        r'<tg-emoji\s+emoji-id=["\'](?P<id>\d+)["\']\s*>'
        r'(?P<fallback>[^<]*)</tg-emoji>',
        s, flags=re.IGNORECASE,
    )
    if m2:
        emoji_id = m2.group("id")
        # 🔧 Remove the tag AND its fallback char (icon shows the emoji)
        s_no_tag = s[:m2.start()] + s[m2.end():]
        s_no_tag = re.sub(r"<[^>]+>", "", s_no_tag)
        s_no_tag = _unescape(s_no_tag)
        return emoji_id, s_no_tag.strip()

    # No custom emoji at all → strip any other tags too
    s = re.sub(r"<[^>]+>", "", s)
    s = _unescape(s)
    return "", s.strip()


def make_premium_button(label, *, emoji_id=None, style=None,
                        callback_data=None, url=None, web_app=None,
                        login_url=None, switch_inline_query=None,
                        switch_inline_query_current_chat=None,
                        copy_text=None, pay=None):
    """🚀 Universal helper to construct an InlineKeyboardButton that
    automatically renders the premium emoji ICON when the label contains
    a `<tg-emoji>` tag (the format saved by every editor in this bot).

    Args:
        label: the button label string. May be:
            - plain text   ("🛒 Buy Now")
            - HTML-marked  ("[[HTML]]<tg-emoji emoji-id='X'>🔥</tg-emoji> Buy")
            - Or anything in between (other HTML tags get stripped from the
              button text — buttons only accept plain string).
        emoji_id: explicit custom_emoji_id to override extraction.
        callback_data/url/web_app/...: standard PTB kwargs (passed through).

    Returns: InlineKeyboardButton with icon_custom_emoji_id wired up via
             api_kwargs (works on ALL PTB versions ≥ 20).
    """
    from telegram import InlineKeyboardButton

    # Detect emoji + clean text
    if emoji_id is None:
        # extract_emoji_from_html already drops the premium emoji's fallback
        # char from the text, so no double emoji here.
        eid, plain = extract_emoji_from_html(label or "")
    else:
        # Caller forced an emoji_id. The label text may still START with the
        # plain fallback emoji char (e.g. the product list builds "🔥 Name").
        # Since the forced premium icon already shows that emoji, strip ONE
        # leading emoji/symbol cluster to avoid a DOUBLE emoji.
        from utils import html_strip_tags
        eid = str(emoji_id)
        plain = html_strip_tags(label or "")
        if plain:
            import re as _re
            stripped = _re.sub(r'^\s*[^\w\s]+\uFE0F?\s*', '', plain, count=1).strip()
            plain = stripped if stripped else " "

    plain = plain or " "  # button text cannot be empty per Telegram

    # Collect optional kwargs (only non-None ones)
    kw = {}
    if callback_data is not None: kw["callback_data"] = callback_data
    if url is not None: kw["url"] = url
    if web_app is not None: kw["web_app"] = web_app
    if login_url is not None: kw["login_url"] = login_url
    if switch_inline_query is not None: kw["switch_inline_query"] = switch_inline_query
    if switch_inline_query_current_chat is not None:
        kw["switch_inline_query_current_chat"] = switch_inline_query_current_chat
    if copy_text is not None: kw["copy_text"] = copy_text
    if pay is not None: kw["pay"] = pay

    # 🎨 Button background color (Bot API 9.4): primary/success/danger
    style = (style or "").strip().lower() or None
    if style not in ("primary", "success", "danger"):
        style = None

    # No premium icon — but maybe a color style
    if not eid:
        if style:
            try:
                return InlineKeyboardButton(plain, style=style, **kw)
            except TypeError:
                try:
                    return InlineKeyboardButton(plain, api_kwargs={"style": style}, **kw)
                except TypeError:
                    pass
        return InlineKeyboardButton(plain, **kw)

    # Has premium icon (+ optional color)
    # Path A: native PTB kwargs (>=22.7)
    try:
        if style:
            return InlineKeyboardButton(plain, icon_custom_emoji_id=eid, style=style, **kw)
        return InlineKeyboardButton(plain, icon_custom_emoji_id=eid, **kw)
    except TypeError:
        pass
    # Path B: universal api_kwargs injection
    try:
        ak = {"icon_custom_emoji_id": eid}
        if style:
            ak["style"] = style
        return InlineKeyboardButton(plain, api_kwargs=ak, **kw)
    except TypeError:
        pass
    # Path C: plain fallback
    return InlineKeyboardButton(plain, **kw)


def wrap_button_for_premium_emoji(btn):
    """Take an existing InlineKeyboardButton and (if its text contains a
    [[HTML]]<tg-emoji>...) rebuild it as a premium-icon button.

    Useful for legacy code paths that already created a button — just
    pass the button through this wrapper to upgrade it in-place.
    """
    if btn is None:
        return None
    text = getattr(btn, "text", "") or ""
    if "[[HTML]]" not in text and "<tg-emoji" not in text.lower():
        return btn  # nothing to upgrade

    # Preserve all the original action attributes
    kw = {}
    for attr in ("callback_data", "url", "web_app", "login_url",
                 "switch_inline_query", "switch_inline_query_current_chat",
                 "copy_text", "pay"):
        v = getattr(btn, attr, None)
        if v is not None:
            kw[attr] = v
    return make_premium_button(text, **kw)


def supports_button_icons():
    """True if the installed PTB version supports icon_custom_emoji_id natively.
    Note: even when False, we still inject via api_kwargs in build_button(),
    so the icon will still be sent — this flag is only for UI hints.
    """
    try:
        from telegram import InlineKeyboardButton
        import inspect
        sig = inspect.signature(InlineKeyboardButton.__init__)
        return "icon_custom_emoji_id" in sig.parameters
    except Exception:
        return False


def diagnose_send(bot=None):
    """Return a human-readable diagnostic dict explaining whether premium
    button icons can/cannot render right now. Useful for admin UI.

    Returns: dict with keys
        ptb_version        – installed PTB version string
        ptb_native_support – True if PTB >= 22.7 (native kwarg)
        api_kwargs_path    – True if api_kwargs fallback available (always True on >=20)
        ready              – overall True if at least one path is wired
        notes              – list of human notes
    """
    info = {"ptb_version": "?", "ptb_native_support": False,
            "api_kwargs_path": True, "ready": False, "notes": []}
    try:
        import telegram
        info["ptb_version"] = getattr(telegram, "__version__", "unknown")
        info["ptb_native_support"] = supports_button_icons()
    except Exception as e:
        info["notes"].append(f"PTB import error: {e}")
        return info

    info["ready"] = True  # api_kwargs path always works on PTB ≥ 20
    if info["ptb_native_support"]:
        info["notes"].append("✅ Native icon_custom_emoji_id support (PTB ≥ 22.7).")
    else:
        info["notes"].append(
            "ℹ️ Native PTB kwarg not detected — using api_kwargs fallback "
            "(Telegram receives the field regardless). Consider upgrading PTB."
        )
    info["notes"].append(
        "⭐ For the icon to render: bot OWNER must have Telegram Premium and "
        "the chat must be private/group/supergroup (NOT channel)."
    )
    info["notes"].append(
        "⚠️ Recipient also needs Premium to see ANIMATED form; non-premium "
        "users see the fallback static emoji char."
    )
    return info


# ============================================================
# 📄 ORIGINAL FILE: styles.py
# ============================================================

# ============================================
# 🎨 MENU STYLES (10 different looks)
# ============================================
# Each style decorates button labels differently.
# Combined with Button Size (small/medium/large/xl)
# for maximum customization flexibility.

STYLES = {
    1: {
        "name": "🎯 Classic",
        "desc": "Default look — clean emoji + text",
        "preview": "🛒 Shop",
    },
    2: {
        "name": "✨ Minimal",
        "desc": "Just text, no emojis — pure & clean",
        "preview": "Shop",
    },
    3: {
        "name": "🔷 Diamond",
        "desc": "Diamond decoration around labels",
        "preview": "◆ 🛒 Shop ◆",
    },
    4: {
        "name": "➜ Arrow",
        "desc": "Sleek arrow style — modern",
        "preview": "➜ 🛒 Shop",
    },
    5: {
        "name": "🔠 UPPERCASE",
        "desc": "BOLD UPPERCASE TEXT — strong look",
        "preview": "🛒 SHOP",
    },
    6: {
        "name": "⭐ Premium",
        "desc": "Gold stars — premium feel",
        "preview": "⭐ 🛒 Shop ⭐",
    },
    7: {
        "name": "▪️ Modern Box",
        "desc": "Square bullets — UI style",
        "preview": "▪️ 🛒 Shop",
    },
    8: {
        "name": "《》 Brackets",
        "desc": "Japanese brackets — aesthetic",
        "preview": "《 🛒 Shop 》",
    },
    9: {
        "name": "• Bullet",
        "desc": "Round bullets — playful",
        "preview": "• 🛒 Shop •",
    },
    10: {
        "name": "✨ Fancy Sparkle",
        "desc": "Sparkles all around — luxury",
        "preview": "✨ 🛒 Shop ✨",
    },
}


def get_style_id():
    """Get current menu style ID from DB. Default: 1 (Classic)"""
    try:
        from database import get_setting
        s = get_setting("menu_style", "1")
        i = int(s)
        return i if 1 <= i <= 10 else 1
    except Exception:
        return 1


def strip_leading_emoji(s):
    """Strip leading emoji/symbols, keep from first letter onwards"""
    import re
    stripped = re.sub(r'^[^A-Za-z0-9]+', '', s).strip()
    return stripped if stripped else s  # fallback to original if empty


def decorate(label):
    """Apply current menu style decoration to a label.
    Should only be called on menu/nav button labels — NOT on
    dynamic items like product lists (those have prices/stock).
    """
    style = get_style_id()
    s = str(label)

    # 🔧 BUGFIX: Never decorate premium-emoji HTML labels. Wrapping/upper-casing
    # the raw [[HTML]]<tg-emoji ...> sentinel both corrupted the visible text
    # ("HTML]] Shop Now") and broke later premium-icon extraction, so the
    # custom emoji never showed on the main menu. Leave such labels untouched;
    # the premium-emoji renderer (make_premium_button) handles them.
    if "[[HTML]]" in s or "<tg-emoji" in s.lower():
        return s

    if style == 1:   # 🎯 Classic
        return s
    elif style == 2:  # ✨ Minimal — strip emojis
        return strip_leading_emoji(s)
    elif style == 3:  # 🔷 Diamond
        return f"◆ {s} ◆"
    elif style == 4:  # ➜ Arrow
        return f"➜ {s}"
    elif style == 5:  # 🔠 UPPERCASE
        # Upper-case only the letters, keep emojis intact
        return s.upper()
    elif style == 6:  # ⭐ Premium
        return f"⭐ {s} ⭐"
    elif style == 7:  # ▪️ Modern Box
        return f"▪️ {s}"
    elif style == 8:  # 《》 Brackets
        return f"《 {s} 》"
    elif style == 9:  # • Bullet
        return f"• {s} •"
    elif style == 10:  # ✨ Fancy Sparkle
        return f"✨ {s} ✨"
    return s

