# ============================================================
# 🎨 v92: MAIN MENU LAYOUT ENGINE (Solution #4 — Hybrid)
# ============================================================
# Provides 50 pre-designed main-menu layouts. Admin picks one via
# Customization → Layout Picker. Layout is applied on every /start.
#
# ── HYBRID DESIGN ──
# Each layout is a "recipe" that defines:
#   - hero_row      → fixed top button(s), often colored
#   - middle_pattern → rows-of-N pattern for the middle grid
#   - core_order    → which core buttons go in the middle (in what order)
#   - overflow_pattern → how CUSTOM / EXTRA buttons flow in (auto)
#   - footer_row    → fixed bottom button(s) (usually admin)
#   - group_headers → optional section titles between groups
#   - hero_style / footer_style → color styles per Bot API 9.4
#
# ── AUTO-DETECTION FOR CUSTOM BUTTONS ──
# When admin adds custom buttons, the engine:
#   1. Places all "core" buttons per the layout's recipe
#   2. Automatically appends custom buttons using the layout's
#      `overflow_pattern` (matches the visual rhythm)
#   3. Footer stays at bottom
# → 50 layouts always look consistent, no matter how many buttons.
#
# ── STORAGE ──
# Admin's selected layout ID stored in bot_settings.main_layout_id
# (default: "L01_classic" — user's current 1-column look)
# ============================================================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


# ================================================================
# 50 LAYOUT RECIPES
# ================================================================
# Each recipe is a dict with these keys:
#   name              → display name
#   category          → 1=grid, 2=hero, 3=grouped, 4=info-rich, 5=creative
#   description       → short desc for admin picker
#   hero              → list of button_ids for the hero row (optional)
#   hero_full_width   → bool: if True, hero is one wide button per row
#   hero_style        → list of styles matching hero list ("primary"/"success"/None)
#   core_pattern      → list of column counts per row for CORE buttons
#                       e.g. [2,2,2,2,2,2] = 6 rows of 2
#                       or "cols:N" = auto-chunk into N-column grid
#                       or "cols:1" = 1-column
#   core_order        → ordered list of core button ids to place
#                       (if None, use registry default order)
#   overflow_cols     → columns for CUSTOM buttons (usually matches core)
#   footer            → list of button_ids for footer (usually ["main_admin"])
#   footer_style      → styles for footer buttons
#   group_headers     → optional dict: {row_index_before: "━━ TITLE ━━"}
#   emoji_only        → bool: if True, use short (emoji-only) labels

# Helper aliases for the 13 core buttons + admin
_CORE_BASE = [
    "main_shop", "main_points", "main_price_list", "main_account",
    "main_orders", "main_transactions", "main_referral", "main_support",
    "main_warranty", "main_reviews", "main_loyalty", "main_language",
]
_ADMIN = ["main_admin"]

LAYOUTS = {

    # ══════════════════════════════════════════════════════════
    # SECTION 1 · Pure Grid Layouts (1–10)
    # ══════════════════════════════════════════════════════════

    "L01_classic_1col": {
        "name": "1-Column Classic",
        "category": 1, "tag": "Baseline",
        "description": "Your current layout. Everyone knows this.",
        "hero": None,
        "core_pattern": "cols:1",
        "core_order": None,
        "overflow_cols": 1,
        "footer": _ADMIN,
    },

    "L02_2col_perfect": {
        "name": "2-Column Perfect",
        "category": 1, "tag": "App-like",
        "description": "6 rows of 2 + admin bottom. No empty slots.",
        "hero": None,
        "core_pattern": "cols:2",
        "overflow_cols": 2,
        "footer": _ADMIN,
    },

    "L03_3col_perfect": {
        "name": "3-Column Perfect",
        "category": 1, "tag": "Dense",
        "description": "4 rows of 3 buttons. Fits full screen tight.",
        "hero": None,
        "core_pattern": "cols:3",
        "overflow_cols": 3,
        "footer": _ADMIN,
    },

    "L04_4col_icons": {
        "name": "4-Column Icon Grid",
        "category": 1, "tag": "Icon Only",
        "description": "iOS-app-style. Emoji-only labels.",
        "hero": None,
        "core_pattern": "cols:4",
        "overflow_cols": 4,
        "footer": _ADMIN,
        "emoji_only": True,
    },

    "L05_hero_shop": {
        "name": "Hero Shop + 2-Column",
        "category": 1, "tag": "Hero CTA",
        "description": "Shop gets full-width top spot, colored blue.",
        "hero": ["main_shop"],
        "hero_full_width": True,
        "hero_style": ["primary"],
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b != "main_shop"],
        "overflow_cols": 2,
        "footer": _ADMIN,
    },

    "L06_pyramid": {
        "name": "Pyramid 1-2-3-3-3-1",
        "category": 1, "tag": "Pyramid",
        "description": "Priority-based. Top row = most important.",
        "hero": ["main_shop"],
        "hero_full_width": True,
        "hero_style": ["primary"],
        "core_pattern": [2, 3, 3, 3],
        "core_order": ["main_points", "main_price_list",
                        "main_account", "main_orders", "main_transactions",
                        "main_referral", "main_support", "main_warranty",
                        "main_reviews", "main_loyalty", "main_language"],
        "overflow_cols": 3,
        "footer": _ADMIN,
    },

    "L07_inverted_pyramid": {
        "name": "Inverted Pyramid (Thumb-Reach)",
        "category": 1, "tag": "Reverse",
        "description": "Extras top, hero at bottom (mobile-friendly).",
        "hero": None,
        "core_pattern": [3, 3, 3, 3],
        "core_order": ["main_language", "main_reviews", "main_admin",
                        "main_referral", "main_support", "main_warranty",
                        "main_account", "main_orders", "main_transactions",
                        "main_points", "main_price_list", "main_loyalty"],
        "overflow_cols": 3,
        "footer": ["main_shop"],
        "footer_full_width": True,
        "footer_style": ["primary"],
        "footer_label_override": {"main_shop": "🛒 SHOP NOW"},
    },

    "L08_2x6_symmetric": {
        "name": "Symmetric 2×6 + Admin",
        "category": 1, "tag": "Symmetric",
        "description": "Perfect symmetry. 6 pairs + solo admin.",
        "hero": None,
        "core_pattern": "cols:2",
        "overflow_cols": 2,
        "footer": _ADMIN,
    },

    "L09_text_icon_sandwich": {
        "name": "Text-Icon-Text Sandwich",
        "category": 1, "tag": "Mixed",
        "description": "Full labels top+bottom, icons in middle.",
        "hero": None,
        "core_pattern": [2, 2, 4, 4],
        "core_order": _CORE_BASE,
        "overflow_cols": 4,
        "footer": _ADMIN,
        "middle_emoji_only_rows": [2, 3],  # rows 3,4 = icon-only
    },

    "L10_hex_rhythm": {
        "name": "Hex 2-3-2-3-2-1",
        "category": 1, "tag": "Hex",
        "description": "Honeycomb-style alternating rhythm.",
        "hero": None,
        "core_pattern": [2, 3, 2, 3, 2],
        "overflow_cols": 2,
        "footer": _ADMIN,
    },

    # ══════════════════════════════════════════════════════════
    # SECTION 2 · Priority / Hero Layouts (11–20)
    # ══════════════════════════════════════════════════════════

    "L11_twin_hero": {
        "name": "Twin Hero (Shop + Points)",
        "category": 2, "tag": "Twin Hero",
        "description": "Two colored CTAs at top drive revenue.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b not in ("main_shop", "main_points")],
        "overflow_cols": 2,
        "footer": _ADMIN,
    },

    "L12_triple_hero": {
        "name": "Triple Hero Row",
        "category": 2, "tag": "Triple Hero",
        "description": "Shop / Buy / Track — 3 primary actions.",
        "hero": ["main_shop", "main_points", "main_orders"],
        "hero_style": ["primary", "success", None],
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b not in ("main_shop", "main_points", "main_orders")],
        "overflow_cols": 2,
        "footer": _ADMIN,
    },

    "L13_stacked_double_hero": {
        "name": "Stacked Double Hero",
        "category": 2, "tag": "Stacked Hero",
        "description": "Two full-width CTAs, then compact grid.",
        "hero": ["main_shop", "main_points"],
        "hero_full_width": True,
        "hero_style": ["primary", "success"],
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b not in ("main_shop", "main_points")],
        "overflow_cols": 2,
        "footer": _ADMIN,
    },

    "L14_asymmetric_wide_narrow": {
        "name": "Asymmetric Wide+Narrow",
        "category": 2, "tag": "Asymmetric",
        "description": "Big main action, small companion.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "hero_widths": [3, 1],   # 75% + 25%
        "core_pattern": "cols:2",
        "core_widths": [3, 1],
        "core_order": [b for b in _CORE_BASE if b not in ("main_shop", "main_points")],
        "overflow_cols": 2,
        "overflow_widths": [3, 1],
        "footer": _ADMIN,
    },

    "L15_corner_admin": {
        "name": "Corner Admin Badge",
        "category": 2, "tag": "Corner Admin",
        "description": "Admin sits as small corner badge.",
        "hero": ["main_shop", "main_admin"],
        "hero_style": ["primary", None],
        "hero_widths": [4, 1],
        "hero_admin_variant": True,  # admin appears in hero, not footer
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b != "main_shop"],
        "overflow_cols": 2,
        "footer": [],  # admin already in hero
    },

    "L16_diamond": {
        "name": "Diamond Centered",
        "category": 2, "tag": "Diamond",
        "description": "Focus narrows from top+bottom to middle.",
        "hero": ["main_shop"],
        "hero_full_width": True,
        "hero_style": ["primary"],
        "core_pattern": [2, 3, 4, 2],
        "core_order": ["main_points", "main_price_list",
                        "main_account", "main_orders", "main_transactions",
                        "main_referral", "main_support", "main_warranty", "main_reviews",
                        "main_loyalty", "main_language"],
        "overflow_cols": 2,
        "footer": _ADMIN,
    },

    "L17_hourglass": {
        "name": "Hourglass 3-2-1-2-3-2",
        "category": 2, "tag": "Hourglass",
        "description": "Wide-narrow-wide rhythm; middle draws eye.",
        "hero": None,
        "core_pattern": [3, 2, 1, 2, 3],
        "core_order": ["main_shop", "main_points", "main_price_list",
                        "main_account", "main_orders",
                        "main_referral",  # solo middle (or admin can override)
                        "main_transactions", "main_loyalty",
                        "main_support", "main_warranty", "main_reviews"],
        "overflow_cols": 2,
        "footer": ["main_language", "main_admin"],
    },

    "L18_zebra": {
        "name": "Zebra 1-2-1-2-1-2-1",
        "category": 2, "tag": "Zebra",
        "description": "Solo/pair alternating — feels rhythmic.",
        "hero": ["main_shop"],
        "hero_full_width": True,
        "hero_style": ["primary"],
        "core_pattern": [2, 1, 2, 1, 2, 1, 2],
        "core_order": ["main_points", "main_price_list",
                        "main_account",
                        "main_orders", "main_transactions",
                        "main_referral",
                        "main_support", "main_warranty",
                        "main_reviews",
                        "main_loyalty", "main_language"],
        "overflow_cols": 2,
        "footer": _ADMIN,
    },

    "L19_quick_strip": {
        "name": "Quick-Actions Strip",
        "category": 2, "tag": "Quick Strip",
        "description": "4 quick actions up top for speed.",
        "hero": ["main_shop", "main_points", "main_orders", "main_support"],
        "hero_style": ["primary", "success", None, None],
        "core_pattern": "cols:2",
        "core_order": ["main_price_list", "main_account",
                        "main_transactions", "main_referral",
                        "main_warranty", "main_reviews",
                        "main_loyalty", "main_language"],
        "overflow_cols": 2,
        "footer": _ADMIN,
    },

    "L20_tab_bar": {
        "name": "Bottom Tab-Bar Style",
        "category": 2, "tag": "Tab Bar",
        "description": "Mobile-app feel: content top, nav bottom.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": [2, 1, 3, 2],
        "core_order": ["main_price_list", "main_account",
                        "main_orders",
                        "main_referral", "main_loyalty", "main_transactions",
                        "main_reviews", "main_warranty"],
        "overflow_cols": 3,
        "footer": ["main_support", "main_language", "main_admin"],
    },

    # ══════════════════════════════════════════════════════════
    # SECTION 3 · Categorized / Grouped Layouts (21–30)
    # ══════════════════════════════════════════════════════════

    "L21_sectioned_headers": {
        "name": "Sectioned with Headers",
        "category": 3, "tag": "Sectioned",
        "description": "Text dividers group buttons by purpose.",
        "hero": None,
        "core_pattern": [2, 2, 3, 3, 2],
        "core_order": ["main_shop", "main_price_list",
                        "main_points", "main_transactions",
                        "main_account", "main_orders", "main_loyalty",
                        "main_support", "main_warranty", "main_reviews",
                        "main_referral", "main_language"],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "group_headers": {
            0: "━━ 🛒 Shopping ━━",
            1: "━━ 💰 Wallet ━━",
            2: "━━ 👤 Profile ━━",
            3: "━━ 💬 Help ━━",
            4: "━━ ⚙️ More ━━",
        },
        "hero_style_row_0": ["primary", None],
        "hero_style_row_1": ["success", None],
    },

    "L22_airy_dividers": {
        "name": "Airy Grouped (Whitespace)",
        "category": 3, "tag": "Airy",
        "description": "Groups separated by divider buttons.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": [2, 2, 2, 2, 2],
        "core_order": ["main_price_list", "main_account",
                        "main_orders", "main_transactions",
                        "main_referral", "main_loyalty",
                        "main_support", "main_warranty",
                        "main_reviews", "main_language"],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "divider_rows_after": [0, 2, 4],  # add divider after these row indices
    },

    "L23_tri_fold": {
        "name": "Tri-Fold Groups",
        "category": 3, "tag": "Tri-fold",
        "description": "Buy · Manage · Support — 3 clean zones.",
        "hero": None,
        "core_pattern": [3, 2, 3, 3, 2],
        "core_order": ["main_shop", "main_price_list", "main_points",
                        "main_account", "main_orders",
                        "main_transactions", "main_loyalty", "main_referral",
                        "main_support", "main_warranty", "main_reviews",
                        "main_language", "main_admin"],
        "overflow_cols": 3,
        "footer": [],
        "group_headers": {
            0: "💰 BUY",
            1: "👤 MANAGE",
            3: "🆘 HELP",
        },
        "hero_style_row_0": ["primary", None, "success"],
    },

    "L24_emoji_dividers": {
        "name": "Emoji-Only Dividers",
        "category": 3, "tag": "Emoji Divide",
        "description": "Emoji as visual separator, no text.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": [2, 2, 2, 2, 2],
        "core_order": ["main_price_list", "main_account",
                        "main_orders", "main_transactions",
                        "main_referral", "main_loyalty",
                        "main_support", "main_warranty",
                        "main_reviews", "main_language"],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "divider_style": "emoji",
        "divider_rows_after": [0, 2, 4],
    },

    "L25_above_fold_priority": {
        "name": "Above-the-Fold Priority",
        "category": 3, "tag": "Above-Fold",
        "description": "Top 4 = revenue drivers. Rest below fold.",
        "hero": None,
        "core_pattern": [2, 2, 4, 3, 2],
        "core_order": ["main_shop", "main_points",
                        "main_price_list", "main_referral",
                        "main_account", "main_orders", "main_transactions", "main_loyalty",
                        "main_support", "main_warranty", "main_reviews",
                        "main_language", "main_admin"],
        "overflow_cols": 3,
        "footer": [],
        "group_headers": {
            0: "━━ 💰 MAKE MONEY ━━",
            2: "━━ 📋 ACCOUNT ━━",
            3: "━━ 💬 SUPPORT ━━",
        },
        "hero_style_row_0": ["primary", "success"],
    },

    "L26_vip_highlighted": {
        "name": "VIP-Highlighted",
        "category": 3, "tag": "VIP Zone",
        "description": "Purple gradient VIP row = premium feel.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": [2, 2, 2, 2, 2],
        "core_order": ["main_price_list", "main_account",
                        "main_loyalty", "main_referral",  # VIP row
                        "main_orders", "main_transactions",
                        "main_support", "main_warranty",
                        "main_reviews", "main_language"],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "group_headers": {
            1: "━━ 🏆 VIP EXCLUSIVE ━━",
            2: "━━━━━━━━━━━━━━",
        },
    },

    "L27_color_coded": {
        "name": "Color-Coded Function Groups",
        "category": 3, "tag": "Color Coded",
        "description": "Blue=shop, Green=money, Gray=info.",
        "hero": None,
        "core_pattern": "cols:2",
        "core_order": ["main_shop", "main_price_list",
                        "main_points", "main_transactions",
                        "main_account", "main_orders",
                        "main_referral", "main_loyalty",
                        "main_support", "main_warranty",
                        "main_reviews", "main_language"],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "core_row_styles": {
            0: ["primary", "primary"],
            1: ["success", "success"],
        },
    },

    "L28_nav_drawer": {
        "name": "Nav-Drawer Style",
        "category": 3, "tag": "Nav Drawer",
        "description": "Long left-aligned labels, single column.",
        "hero": None,
        "core_pattern": "cols:1",
        "core_row_styles": {
            0: ["primary"], 1: ["success"],
        },
        "overflow_cols": 1,
        "footer": _ADMIN,
    },

    "L29_frequency_based": {
        "name": "Frequency-Based",
        "category": 3, "tag": "Frequency",
        "description": "Most-used = big + top. Rare = small + bottom.",
        "hero": ["main_shop"],
        "hero_full_width": True,
        "hero_style": ["primary"],
        "core_pattern": [2, 2, 3, 3],
        "core_order": ["main_points", "main_price_list",
                        "main_orders", "main_account",
                        "main_transactions", "main_referral", "main_loyalty",
                        "main_support", "main_warranty", "main_reviews"],
        "overflow_cols": 3,
        "footer": ["main_language", "main_admin"],
        "footer_widths": [1, 3],
    },

    "L30_persona_buyer_first": {
        "name": "Persona-Based (Buyer First)",
        "category": 3, "tag": "Persona",
        "description": "Buyers see buy stuff first, info stuff below.",
        "hero": None,
        "core_pattern": [1, 2, 3, 2, 3],
        "core_order": ["main_shop",
                        "main_points", "main_price_list",
                        "main_account", "main_orders", "main_transactions",
                        "main_loyalty", "main_referral",
                        "main_support", "main_warranty", "main_reviews"],
        "overflow_cols": 3,
        "footer": ["main_language", "main_admin"],
        "group_headers": {
            0: "━━ 🎯 START HERE ━━",
            2: "━━ 📊 YOUR STUFF ━━",
            4: "━━ ℹ️ INFO ━━",
        },
        "hero_style_row_0": ["primary"],
        "hero_style_row_1": ["success", None],
    },

    # ══════════════════════════════════════════════════════════
    # SECTION 4 · Info-Rich Welcome Layouts (31–40)
    # ══════════════════════════════════════════════════════════

    "L31_live_balance": {
        "name": "Live Balance Header",
        "category": 4, "tag": "Live Balance",
        "description": "Wallet + points always visible at top of welcome msg.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b not in ("main_shop", "main_points")],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["balance_header"],  # engine adds live data to msg
    },

    "L32_personal_greeting": {
        "name": "Personal Greeting",
        "category": 4, "tag": "Personal",
        "description": "Time-based greeting + name.",
        "hero": ["main_shop"],
        "hero_full_width": True,
        "hero_style": ["primary"],
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b != "main_shop"],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["greeting_time_name", "last_order_teaser"],
    },

    "L33_live_ticker": {
        "name": "Live Sales Ticker",
        "category": 4, "tag": "Live Ticker",
        "description": "Rotating stats: '47 sold today · ChatGPT trending'.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b not in ("main_shop", "main_points")],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["sales_ticker"],
    },

    "L34_streak_gamification": {
        "name": "Streak / Gamification",
        "category": 4, "tag": "Streak",
        "description": "Daily login streak = habit-forming.",
        "hero": ["main_loyalty"],  # loyalty gets the hero spot
        "hero_full_width": True,
        "hero_style": ["success"],
        "hero_label_override": {"main_loyalty": "🏆 Loyalty · Claim Streak Bonus"},
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b != "main_loyalty"],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["streak_days"],
    },

    "L35_trust_bar": {
        "name": "Trust Bar Layout",
        "category": 4, "tag": "Trust Bar",
        "description": "Verified customers count + rating on top.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b not in ("main_shop", "main_points")],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["trust_bar"],
    },

    "L36_featured_product": {
        "name": "Featured Product Hero",
        "category": 4, "tag": "Featured",
        "description": "Shop button doubles as today's deal CTA.",
        "hero": ["main_shop"],
        "hero_full_width": True,
        "hero_style": ["success"],
        "hero_label_override": {"main_shop": "🛒 Shop · Today's Deal"},
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b != "main_shop"],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["featured_product"],
    },

    "L37_multi_metric_dashboard": {
        "name": "Multi-Metric Dashboard",
        "category": 4, "tag": "Dashboard",
        "description": "Balance + Orders + Rank + Streak in header.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b not in ("main_shop", "main_points")],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["multi_metric"],
    },

    "L38_bilingual": {
        "name": "Bilingual Welcome",
        "category": 4, "tag": "Bilingual",
        "description": "Urdu + English side-by-side (Aslam-o-Alaikum).",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b not in ("main_shop", "main_points")],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["bilingual_greeting"],
    },

    "L39_order_in_progress": {
        "name": "Order-in-Progress Alert",
        "category": 4, "tag": "Order Alert",
        "description": "If pending order → show status right on top.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b not in ("main_shop", "main_points")],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["order_progress"],
    },

    "L40_new_user_cta": {
        "name": "Smart CTA (New User)",
        "category": 4, "tag": "Smart CTA",
        "description": "Refer button re-purposed as welcome bonus CTA.",
        "hero": ["main_referral", "main_shop"],
        "hero_full_width": True,
        "hero_style": ["success", "primary"],
        "hero_label_override": {
            "main_referral": "🎁 Refer & Claim 50 FREE Points",
            "main_shop": "🛒 Browse Products",
        },
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b not in ("main_referral", "main_shop")],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["welcome_bonus_new_user"],
    },

    # ══════════════════════════════════════════════════════════
    # SECTION 5 · Creative / Experimental (41–50)
    # ══════════════════════════════════════════════════════════

    "L41_minimalist_zen": {
        "name": "Minimalist Zen (Core+Expand)",
        "category": 5, "tag": "Minimalist",
        "description": "Only 5 core actions. Rest behind '⚙️ More'.",
        "hero": ["main_shop"],
        "hero_full_width": True,
        "hero_style": ["primary"],
        "core_pattern": [2, 2],
        "core_order": ["main_points", "main_orders",
                        "main_support", "main_loyalty"],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "hide_extras_under_more": True,  # rest under a "More" button
    },

    "L42_magazine_cover": {
        "name": "Magazine Cover Style",
        "category": 5, "tag": "Magazine",
        "description": "Bold headline, mixed button sizes.",
        "hero": ["main_shop"],
        "hero_full_width": True,
        "hero_style": ["primary"],
        "hero_label_override": {"main_shop": "🛒 SHOP THE DROP →"},
        "core_pattern": [3, 2, 1, 3, 3],
        "core_widths": {1: [1, 3], 2: None},  # wide-narrow variations
        "core_order": ["main_points", "main_price_list", "main_account",
                        "main_orders", "main_transactions",
                        "main_referral",  # solo big
                        "main_support", "main_warranty", "main_reviews",
                        "main_loyalty", "main_language", "main_admin"],
        "overflow_cols": 3,
        "footer": [],
        "hero_label_override_row_2": {"main_referral": "🎁 Refer & Earn"},
        "core_row_styles": {2: ["success"]},
    },

    "L43_gaming_hud": {
        "name": "Gaming HUD Style",
        "category": 5, "tag": "Gaming HUD",
        "description": "Level bar + XP + inventory feel.",
        "hero": ["main_shop", "main_points", "main_loyalty"],
        "hero_style": ["primary", "success", None],
        "hero_label_override": {
            "main_shop": "⚔️ SHOP",
            "main_points": "💰 WALLET",
            "main_loyalty": "🏆 RANK",
        },
        "core_pattern": [2, 2, 2, 2, 2],
        "core_order": ["main_price_list", "main_account",
                        "main_orders", "main_transactions",
                        "main_referral", "main_reviews",
                        "main_warranty", "main_support",
                        "main_language", "main_admin"],
        "core_label_override": {
            "main_price_list": "📊 Price Board",
            "main_account": "📊 My Character",
            "main_orders": "📜 Quest Log",
            "main_transactions": "🔄 Battle Log",
            "main_referral": "🎁 Invite Party",
        },
        "overflow_cols": 2,
        "footer": [],
        "welcome_extras": ["gaming_hud"],
    },

    "L44_restaurant_menu": {
        "name": "Restaurant Menu Style",
        "category": 5, "tag": "Restaurant",
        "description": "Fancy dividers + emoji categories.",
        "hero": None,
        "core_pattern": [2, 3, 3, 3, 2],
        "core_order": ["main_shop", "main_price_list",
                        "main_points", "main_referral", "main_loyalty",
                        "main_account", "main_orders", "main_transactions",
                        "main_support", "main_warranty", "main_reviews",
                        "main_language", "main_admin"],
        "overflow_cols": 3,
        "footer": [],
        "group_headers": {
            0: "🥇 MAINS",
            1: "🥈 SIDES",
            2: "🥉 SEATING",
            3: "🧾 MANAGEMENT",
        },
        "hero_style_row_0": ["primary", None],
        "hero_style_row_1": ["success", None, None],
    },

    "L45_terminal_hacker": {
        "name": "Terminal / Hacker Vibe",
        "category": 5, "tag": "Terminal",
        "description": "For tech-savvy audiences (nerd flex).",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "hero_label_override": {
            "main_shop": "$ shop",
            "main_points": "$ topup",
        },
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b not in ("main_shop", "main_points")],
        "core_label_override": {
            "main_price_list": "$ ls -prices",
            "main_account": "$ cat account",
            "main_orders": "$ history",
            "main_transactions": "$ transactions",
            "main_referral": "$ refer",
            "main_support": "$ help",
            "main_warranty": "$ warranty",
            "main_reviews": "$ reviews",
            "main_loyalty": "$ loyalty",
            "main_language": "$ lang",
            "main_admin": "$ sudo admin",
        },
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["terminal_greeting"],
    },

    "L46_storefront_signage": {
        "name": "Storefront Signage",
        "category": 5, "tag": "Storefront",
        "description": "Big shop sign + entrance CTA.",
        "hero": ["main_shop"],
        "hero_full_width": True,
        "hero_style": ["primary"],
        "hero_label_override": {"main_shop": "🚪 ENTER THE STORE →"},
        "core_pattern": "cols:2",
        "core_order": [b for b in _CORE_BASE if b != "main_shop"],
        "core_label_override": {
            "main_points": "💎 Cash Register",
            "main_price_list": "📊 Menu Board",
            "main_account": "📊 Loyalty Card",
            "main_orders": "📜 Receipts",
            "main_transactions": "🔄 Refund Desk",
            "main_referral": "🎁 Referrals",
            "main_support": "📞 Ask Staff",
            "main_warranty": "🛡️ Warranty",
            "main_reviews": "⭐ Guest Book",
            "main_loyalty": "🏆 VIP Lounge",
            "main_language": "🌐 Language",
            "main_admin": "🔑 Manager Office",
        },
        "overflow_cols": 2,
        "footer": _ADMIN,
        "welcome_extras": ["storefront_sign"],
    },

    "L47_big_emoji_small_label": {
        "name": "Big Emoji + Small Label",
        "category": 5, "tag": "Emoji-First",
        "description": "Prominent emoji, tiny caption underneath.",
        "hero": None,
        "core_pattern": "cols:3",
        "overflow_cols": 3,
        "footer": _ADMIN,
        "compact_labels": True,  # use "short" or "medium" size
    },

    "L48_wide_narrow_chunked": {
        "name": "Wide-Narrow Chunked",
        "category": 5, "tag": "Chunky",
        "description": "Mixed sizes create visual rhythm.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "hero_widths": [3, 1],
        "core_pattern": [2, 2, 2, 2, 2],
        "core_widths": {0: [3, 1], 1: [3, 1], 2: [3, 1], 3: [3, 1], 4: [3, 1]},
        "core_order": ["main_price_list", "main_account",
                        "main_orders", "main_transactions",
                        "main_referral", "main_loyalty",
                        "main_support", "main_warranty",
                        "main_reviews", "main_language"],
        "overflow_cols": 2,
        "footer": _ADMIN,
        "footer_full_width": True,
    },

    "L49_numbered_list": {
        "name": "Numbered List Style",
        "category": 5, "tag": "Numbered",
        "description": "Old-school BBS/telnet feel. Nostalgia.",
        "hero": None,
        "core_pattern": "cols:2",
        "core_order": _CORE_BASE,
        "overflow_cols": 2,
        "footer": _ADMIN,
        "numbered_labels": True,  # prepend [1] [2] [3] ...
    },

    "L50_full_color_rainbow": {
        "name": "Full-Color Rainbow",
        "category": 5, "tag": "Full Color",
        "description": "Every button styled — maximum visual impact.",
        "hero": ["main_shop", "main_points"],
        "hero_style": ["primary", "success"],
        "core_pattern": "cols:2",
        "core_order": ["main_price_list", "main_account",
                        "main_orders", "main_transactions",
                        "main_referral", "main_loyalty",
                        "main_support", "main_warranty",
                        "main_reviews", "main_language"],
        "core_row_styles": {
            0: ["primary", "primary"],
            1: ["success", "success"],
            2: [None, None],   # vip via css? Use None to preserve
            3: [None, None],
            4: [None, None],
        },
        "overflow_cols": 2,
        "footer": _ADMIN,
    },
}


# ================================================================
# STORAGE HELPERS
# ================================================================
DEFAULT_LAYOUT = "L01_classic_1col"


def get_active_layout_id() -> str:
    """Return the currently-selected layout id (from bot_settings)."""
    try:
        from database import get_setting
        v = get_setting("main_layout_id", DEFAULT_LAYOUT) or DEFAULT_LAYOUT
        if v in LAYOUTS:
            return v
    except Exception:
        pass
    return DEFAULT_LAYOUT


def set_active_layout_id(layout_id: str) -> bool:
    """Persist admin's layout choice. Returns True on success."""
    if layout_id not in LAYOUTS:
        return False
    try:
        from database import set_setting
        set_setting("main_layout_id", layout_id)
        return True
    except Exception as e:
        logger.warning(f"[layouts] set_active_layout_id fail: {e}")
        return False


def get_active_layout() -> dict:
    """Return the currently-selected layout's recipe."""
    return LAYOUTS[get_active_layout_id()]


# ================================================================
# THE ENGINE — turns recipe + button list → InlineKeyboardMarkup
# ================================================================
def _make_button(btn_id, label_override=None, style=None,
                 user_id=None, size_override=None):
    """
    Build one InlineKeyboardButton for a core registry button id.
    Respects hide/override, applies label override, applies style,
    uses make_premium_button for premium emoji support.

    🐛 v93 FIX: Now properly respects admin's per-button colors set via
    Customization → 🎨 Buttons → tap button → set color. Previously the
    layout recipe's `hero_style` was the ONLY color source, so admin's
    saved per-button colors were silently ignored. Now:
        1. Layout recipe forces a style?  → use it (highest priority)
        2. Else admin saved a per-button color?  → use it
        3. Else group has a default color?       → use it
        4. Else no color.
    """
    from button_system import BUTTONS, get_button_label, resolve_button_style
    try:
        from button_system import make_premium_button, extract_emoji_from_html
    except Exception:
        make_premium_button = None
        extract_emoji_from_html = None

    info = BUTTONS.get(btn_id, {})
    callback = info.get("callback")
    if not callback:
        return None

    # Get label (respects size + admin rename)
    size = size_override or "medium"
    if label_override is not None:
        label = label_override
    else:
        label = get_button_label(btn_id, size)
        if label is None:
            return None  # button hidden

    # Extract premium emoji id if present in label
    emoji_id = ""
    if extract_emoji_from_html:
        try:
            emoji_id, plain = extract_emoji_from_html(label)
            if emoji_id:
                label = plain  # use plain text; icon added via native API
        except Exception:
            pass

    # 🐛 v93 FIX: Resolve the effective style with proper priority:
    #   1. Explicit style from layout recipe (hero_style, core_row_styles, etc.)
    #   2. Admin's per-button override (btn_style_<id>)
    #   3. Group default (grpstyle_main)
    #   4. None
    if not style:
        try:
            style = resolve_button_style(btn_id) or None
        except Exception:
            style = None

    # Build the button
    if make_premium_button and emoji_id:
        return make_premium_button(label, emoji_id=emoji_id,
                                    style=style, callback_data=callback)
    if make_premium_button and style:
        return make_premium_button(label, style=style, callback_data=callback)
    return InlineKeyboardButton(label, callback_data=callback)


def _make_custom_button(cb_row):
    """
    Build InlineKeyboardButton for a custom_buttons row (admin-added).
    Returns None if inactive.

    🐛 v93 FIX: Previously rendered label as-is → raw HTML strings like
    '[[HTML]]<tg-emoji ...>👍</tg-emoji> WhatsApp Support' leaked into
    button text. Now:
        • Extracts premium emoji id + strips HTML from label
        • Applies per-custom-button color (btn_style_custom_<id>)
          OR the group default (grpstyle_main)
        • Uses make_premium_button so icon renders via Bot API 9.4
    """
    if not cb_row.get("is_active"):
        return None
    raw_label = cb_row.get("label", "").strip() or "Button"
    btype = cb_row.get("btype", "text")
    action = cb_row.get("action", "")

    # Extract premium emoji from HTML label + strip tags
    try:
        from button_system import make_premium_button, extract_emoji_from_html
    except Exception:
        make_premium_button = None
        extract_emoji_from_html = None
    from utils import name_for_button

    emoji_id = ""
    if extract_emoji_from_html:
        try:
            emoji_id, plain = extract_emoji_from_html(raw_label)
            label = plain if plain else name_for_button(raw_label)
        except Exception:
            label = name_for_button(raw_label)
    else:
        label = name_for_button(raw_label)
    label = label or "Button"

    # Resolve color for this custom button:
    #   1. Per-custom-button override (btn_style_custom_<id>)
    #   2. Group default (grpstyle_main)
    style = None
    try:
        from button_system import get_button_style, get_group_style
        style = get_button_style(f"custom_{cb_row['id']}") or get_group_style("main") or None
    except Exception:
        pass

    # Kwargs for the button
    kw = {}
    if btype == "url" and action:
        kw["url"] = action
    else:
        kw["callback_data"] = f"cbact_{cb_row['id']}"

    # Build with premium button helper (renders icon + color natively)
    if make_premium_button and (emoji_id or style):
        return make_premium_button(label,
                                    emoji_id=emoji_id or None,
                                    style=style,
                                    **kw)
    return InlineKeyboardButton(label, **kw)


def _chunk(items, cols):
    """Split flat list into rows of `cols` items each."""
    return [items[i:i + cols] for i in range(0, len(items), cols)]


def render_layout(is_admin=False, user_id=None):
    """
    Main entry point. Returns InlineKeyboardMarkup for the currently-
    selected main menu layout, with:
      - All core buttons in their recipe-defined positions
      - Custom buttons auto-flowed in the layout's overflow_cols pattern
      - Footer (usually admin) at bottom
      - Hidden buttons skipped
      - Premium emojis rendered as icons

    Args:
      is_admin: whether the current user is admin (controls main_admin visibility)
      user_id: for i18n label translation

    Returns: InlineKeyboardMarkup (never None; falls back to classic on error)
    """
    try:
        layout = get_active_layout()
    except Exception as e:
        logger.warning(f"[layouts] failed to load layout: {e}")
        layout = LAYOUTS[DEFAULT_LAYOUT]

    try:
        return _render_recipe(layout, is_admin=is_admin, user_id=user_id)
    except Exception as e:
        logger.exception(f"[layouts] render failed for {layout.get('name')}: {e}")
        # Emergency fallback: 1-column classic
        return _render_recipe(LAYOUTS[DEFAULT_LAYOUT],
                               is_admin=is_admin, user_id=user_id)


def _render_recipe(layout, is_admin=False, user_id=None):
    """The actual rendering logic. Turns a recipe dict → InlineKeyboardMarkup."""
    from button_system import BUTTONS

    hero_ids = layout.get("hero") or []
    hero_style = layout.get("hero_style") or []
    hero_widths = layout.get("hero_widths") or None
    hero_full = layout.get("hero_full_width", False)
    hero_label_ovr = layout.get("hero_label_override") or {}

    core_pattern = layout.get("core_pattern", "cols:1")
    core_order = layout.get("core_order")   # None = use registry default
    core_label_ovr = layout.get("core_label_override") or {}
    core_row_styles = layout.get("core_row_styles") or {}

    footer_ids = layout.get("footer") or []
    footer_style = layout.get("footer_style") or []
    footer_full = layout.get("footer_full_width", False)
    footer_label_ovr = layout.get("footer_label_override") or {}

    overflow_cols = layout.get("overflow_cols", 2)
    numbered = layout.get("numbered_labels", False)
    hide_under_more = layout.get("hide_extras_under_more", False)

    # ── Determine which core buttons to use, in what order ──
    if core_order is None:
        from button_system import get_ordered_button_ids
        all_core = [b for b in get_ordered_button_ids("main") if b != "main_admin"]
    else:
        all_core = [b for b in core_order if b != "main_admin"]

    # Exclude hero + footer buttons from core (they're placed separately)
    excluded = set(hero_ids) | set(footer_ids)
    if "main_admin" in hero_ids and layout.get("hero_admin_variant"):
        pass  # admin in hero, don't add to footer later
    core_ids = [b for b in all_core if b not in excluded]

    # If admin is user and admin button is not in hero/footer, add to footer
    if is_admin and "main_admin" not in hero_ids and "main_admin" not in footer_ids:
        footer_ids = list(footer_ids) + ["main_admin"]
    elif not is_admin:
        # Hide admin button for non-admin users
        hero_ids = [b for b in hero_ids if b != "main_admin"]
        footer_ids = [b for b in footer_ids if b != "main_admin"]

    # ── Build the rows list ──
    rows = []
    counter_holder = {"n": 0}

    def numbered_label(base):
        counter_holder["n"] += 1
        return f"[{counter_holder['n']}] {base}"

    # HERO row(s)
    if hero_ids:
        if hero_full:
            # One button per row, each full-width
            for i, bid in enumerate(hero_ids):
                sty = hero_style[i] if i < len(hero_style) else None
                lbl_ovr = hero_label_ovr.get(bid)
                if numbered and lbl_ovr is None:
                    from button_system import get_button_label
                    lbl_ovr = numbered_label(get_button_label(bid, "medium") or bid)
                elif numbered and lbl_ovr:
                    lbl_ovr = numbered_label(lbl_ovr)
                btn = _make_button(bid, label_override=lbl_ovr,
                                    style=sty, user_id=user_id)
                if btn:
                    rows.append([btn])
        else:
            # All hero buttons in one row
            hrow = []
            for i, bid in enumerate(hero_ids):
                sty = hero_style[i] if i < len(hero_style) else None
                lbl_ovr = hero_label_ovr.get(bid)
                if numbered and lbl_ovr is None:
                    from button_system import get_button_label
                    lbl_ovr = numbered_label(get_button_label(bid, "medium") or bid)
                elif numbered and lbl_ovr:
                    lbl_ovr = numbered_label(lbl_ovr)
                btn = _make_button(bid, label_override=lbl_ovr,
                                    style=sty, user_id=user_id)
                if btn:
                    hrow.append(btn)
            if hrow:
                rows.append(hrow)

    # CORE grid
    # Determine row pattern
    if isinstance(core_pattern, str) and core_pattern.startswith("cols:"):
        cols = int(core_pattern.split(":")[1])
        row_sizes = None  # dynamic chunking
    elif isinstance(core_pattern, list):
        row_sizes = core_pattern
        cols = None
    else:
        cols = 2; row_sizes = None

    if hide_under_more:
        # Only place first N core buttons per pattern; rest under "More"
        placed_n = 0
        if row_sizes:
            for sz in row_sizes:
                placed_n += sz
        else:
            placed_n = min(len(core_ids), 6)
        visible_core = core_ids[:placed_n]
        hidden_core = core_ids[placed_n:]
    else:
        visible_core = core_ids
        hidden_core = []

    # Build core rows
    if row_sizes:
        idx = 0
        for r_idx, sz in enumerate(row_sizes):
            row = []
            styles = core_row_styles.get(r_idx, [None] * sz)
            for c_idx in range(sz):
                if idx >= len(visible_core):
                    break
                bid = visible_core[idx]
                sty = styles[c_idx] if c_idx < len(styles) else None
                lbl_ovr = core_label_ovr.get(bid)
                if numbered:
                    from button_system import get_button_label
                    base = lbl_ovr or get_button_label(bid, "medium") or bid
                    lbl_ovr = numbered_label(base)
                btn = _make_button(bid, label_override=lbl_ovr,
                                    style=sty, user_id=user_id)
                if btn:
                    row.append(btn)
                idx += 1
            if row:
                rows.append(row)
        # Any leftover core buttons? Append with default cols
        while idx < len(visible_core):
            leftover = visible_core[idx:idx + overflow_cols]
            row = []
            for bid in leftover:
                lbl_ovr = core_label_ovr.get(bid)
                if numbered:
                    from button_system import get_button_label
                    base = lbl_ovr or get_button_label(bid, "medium") or bid
                    lbl_ovr = numbered_label(base)
                btn = _make_button(bid, label_override=lbl_ovr, user_id=user_id)
                if btn:
                    row.append(btn)
            if row:
                rows.append(row)
            idx += overflow_cols
    else:
        # cols:N mode — simple chunk
        for r_idx in range(0, len(visible_core), cols):
            chunk_ids = visible_core[r_idx:r_idx + cols]
            styles = core_row_styles.get(r_idx // cols, [None] * cols)
            row = []
            for c_idx, bid in enumerate(chunk_ids):
                sty = styles[c_idx] if c_idx < len(styles) else None
                lbl_ovr = core_label_ovr.get(bid)
                if numbered:
                    from button_system import get_button_label
                    base = lbl_ovr or get_button_label(bid, "medium") or bid
                    lbl_ovr = numbered_label(base)
                btn = _make_button(bid, label_override=lbl_ovr,
                                    style=sty, user_id=user_id)
                if btn:
                    row.append(btn)
            if row:
                rows.append(row)

    # OVERFLOW: custom buttons + hidden-under-more items
    try:
        from database import get_custom_buttons
        custom_rows = get_custom_buttons("main") or []
    except Exception:
        custom_rows = []

    overflow_buttons = []
    for cb in custom_rows:
        b = _make_custom_button(cb)
        if b:
            if numbered:
                b = InlineKeyboardButton(numbered_label(b.text),
                                          callback_data=b.callback_data,
                                          url=b.url)
            overflow_buttons.append(b)

    # Also add "More" button if hide_under_more and there are hidden
    if hide_under_more and hidden_core:
        overflow_buttons.append(
            InlineKeyboardButton("⚙️ More Options ▼",
                                  callback_data="main_more_expand")
        )

    if overflow_buttons:
        for i in range(0, len(overflow_buttons), overflow_cols):
            rows.append(overflow_buttons[i:i + overflow_cols])

    # FOOTER row(s)
    if footer_ids:
        if footer_full:
            for i, bid in enumerate(footer_ids):
                sty = footer_style[i] if i < len(footer_style) else None
                lbl_ovr = footer_label_ovr.get(bid)
                if numbered:
                    from button_system import get_button_label
                    base = lbl_ovr or get_button_label(bid, "medium") or bid
                    lbl_ovr = numbered_label(base)
                btn = _make_button(bid, label_override=lbl_ovr,
                                    style=sty, user_id=user_id)
                if btn:
                    rows.append([btn])
        else:
            frow = []
            for i, bid in enumerate(footer_ids):
                sty = footer_style[i] if i < len(footer_style) else None
                lbl_ovr = footer_label_ovr.get(bid)
                if numbered:
                    from button_system import get_button_label
                    base = lbl_ovr or get_button_label(bid, "medium") or bid
                    lbl_ovr = numbered_label(base)
                btn = _make_button(bid, label_override=lbl_ovr,
                                    style=sty, user_id=user_id)
                if btn:
                    frow.append(btn)
            if frow:
                rows.append(frow)

    return InlineKeyboardMarkup(rows) if rows else InlineKeyboardMarkup([[
        InlineKeyboardButton("🛒 Shop", callback_data="shop")
    ]])
