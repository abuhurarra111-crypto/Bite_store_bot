# ============================================
# 🤖 BITE STORE BOT
# ============================================
import logging
import sys
import os
import warnings
from telegram.warnings import PTBUserWarning
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ApplicationHandlerStop,
    PreCheckoutQueryHandler, ChatMemberHandler)
from telegram.request import HTTPXRequest

# Keep Render logs clean: PTB emits noisy ConversationHandler warnings for
# callback fallbacks inside text conversations. These are non-fatal and expected
# in this bot's mixed callback/text admin flows.
warnings.filterwarnings(
    "ignore",
    message=r"If 'per_message=False'.*CallbackQueryHandler.*",
    category=PTBUserWarning,
)
from config import BOT_TOKEN, validate_required_config
from database import setup_database

# ════════════════════════════════════════════
# 🌐 TELEGRAM PROXY SUPPORT (v26)
# ════════════════════════════════════════════
# If you can't reach Telegram from your country, set TELEGRAM_PROXY in .env
# Format: http://user:pass@host:port OR socks5://host:port
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "").strip()
from handlers_start import *
from handlers_start import go_back_callback  # 🔙 Universal back button
# 🆕 v69: Price List screen (separate module — won't touch shop flow)
from admin_panels import price_list_callback
# 🆕 v70: Pinned Announcements + Share Product Link
from loyalty_extras import (
    admin_pins_callback, admin_pins_add_callback, admin_pin_text_received,
    admin_pin_expiry_callback, admin_pin_cancel_add_callback,
    admin_pin_del_callback, admin_pin_toggle_callback,
    # 🆕 v79: Pin templates (readymade situational pins)
    admin_pins_templates_callback, admin_pin_use_template_callback,
    # 🆕 v101: Real Pin Mode (broadcast + pin in each user's DM + auto-unpin)
    admin_pin_realmode_toggle_callback, admin_pin_push_callback,
    admin_pin_unpush_callback,  # 🐛 v147 (Bug8): delete-push = unpin everywhere
    pin_expiry_watchdog_job,
)
from loyalty_extras import share_product_callback, share_qr_callback
# 🆕 v71: AI Auto-Reply for Support + Per-Product Replacement System
from ai_misc import (
    admin_ai_support_callback, admin_ai_support_toggle_callback,
    admin_ai_support_log_callback,
)
from handlers_support import (
    st_escalate_callback, st_resolved_user_callback,
)
from support_replacement import (
    user_replace_start_callback, user_replace_reason_callback,
    admin_replace_approve_callback, admin_replace_reject_callback,
    admin_replace_reject_do_callback, admin_replace_reject_cancel_callback,
    admin_replace_reject_reason_received,
    admin_replace_api_callback, admin_replace_upload_callback,
    admin_replace_upload_received, admin_replace_stock_callback,
    ticket_reminder_job, st_user_close_callback,
)
# 🆕 v72: Delivery integrity dashboard
from admin_panels import (
    admin_integrity_callback, admin_integrity_bad_callback,
)
from handlers_shop import (shop_flash_callback, req_restock_callback, shop_callback, page_callback, product_detail_callback,
                            carousel_nav_callback, shop_all_callback,
                            shop_category_callback, shop_category_page_callback,
                            shop_filter_callback, favorite_toggle_callback, favorites_callback)  # 🆕 v59/v142
from handlers_order import *
from handlers_order import pay_pts_callback, binance_note_background_job, orders_layout_picker_callback, set_orders_layout_callback
# 🆕 v65: Refund + Cancel handlers
from admin_panels import (
    adm_refund_callback, adm_refund_confirm_callback, adm_refund_abort_callback,
    adm_cancel_callback, adm_cancel_skip_callback, adm_cancel_abort_callback,
    adm_cancel_reason_received,
)
# 🆕 v65: User tracking — daily wipe job
from user_tracking import tracking_wipe_job
# 🆕 v69: 24h post-delivery review reminder
from support_replacement import review_reminder_job
# ⭐ v161.25: Telegram Stars payment
from handlers_stars import (
    points_stars_callback, product_stars_callback,
    stars_pay_callback, stars_precheckout_callback,
    stars_successful_payment,
)
from handlers_support import (adm_upacct_callback, upacct_skip_inst_callback, adm_chat_callback, adm_ownmaildone_callback, user_reply_to_admin_callback, cancel_user_chat_callback)
from handlers_admin import (flash_toggle_callback, manual_hist_callback, edit_manual_order_callback, delivery_settings_callback, pdm_callback, pfmt_callback, pmt_callback, pmail_callback, ppass_callback, pfb_freebie_callback, ds_toggle_callback, ds_format_pick_callback, ds_set_format_callback, ds_template_pick_callback, ds_set_template_callback, cb_style_callback,
    stars_rate_start_callback, stars_rate_received)  # ⭐ v161.25 Stars rate
from handlers_admin import (flash_toggle_callback, adm_manage_pts_callback, adm_pts_uid_received, adm_pts_amt_received)
from handlers_admin import *
from handlers_admin import adm_diagnostics_callback
from handlers_admin import (adm_users_search_callback, adm_users_search_received,
                            cz_noop_callback, cz_search_callback, cz_search_received,
                            cz_theme_callback, cz_theme_apply_callback,
                            cz_backup_callback, cz_import_callback, cz_import_received,
                            cz_banner_callback, cz_banner_toggle_callback,
                            cz_banner_text_callback, cz_banner_text_received,
                            cz_catcolors_callback, cz_catcolor_set_callback,
                            cz_format_callback, cz_fmt_callback)
from handlers_admin import (flash_toggle_callback, edit_product_field_callback, edit_product_field_received,
                             EDIT_PRODUCT_VALUE, EDIT_CATEGORY_VALUE)
from handlers_support import (support_menu_callback, st_list_callback, st_view_callback,
                               st_new_callback, st_subject_received, st_desc_received,
                               admin_direct_chat_start_callback, admin_direct_chat_uid_received,
                               ADMIN_DIRECT_CHAT_UID, ADMIN_DIRECT_CHAT_MSG,
                               warranty_menu_callback, wr_order_callback, wr_type_callback,
                               wr_reason_received,
                               adm_tickets_callback, adm_tickets_list_callback,
                               adm_st_view_callback, adm_st_resolve_callback,
                               adm_st_progress_callback, adm_st_close_callback,
                               adm_st_reply_callback, adm_reply_received,
                               adm_warranty_callback, adm_wr_list_callback,
                               adm_wr_view_callback, adm_wr_approve_callback,
                               adm_wr_reject_callback, adm_wr_reject_do_callback,
                               adm_wr_reject_cancel_callback, adm_wr_reject_reason_received,
                               adm_pending_delivery_callback, adm_delivery_mode_callback, adm_restock_reqs_callback,
                               adm_deliver_callback, adm_delivery_text_received)
from handlers_admin import admin_deposit_history_callback, admin_deposit_page_callback, admin_deposit_detail_callback, admin_responses_category_callback, bybit_test_callback  # 📊 Deposit + ✏️ Responses
from handlers_admin import resp_template_apply_callback, resp_custom_callback, resp_reset_callback  # 🆕 v170.22: response templates
from handlers_admin import make_freebie_callback  # 🆕 v170.29: Add Product → Make This a Freebie
from handlers_admin import (ban_panel_callback, ban_input_start, unban_input_start,
                            ban_input_received, unban_input_received)  # 🆕 v170.37 ban panel
# 🆕 v37: Language, Reviews, Loyalty, Analytics
from ui_extras import language_menu_callback, set_language_callback
from handlers_reviews import (
    reviews_menu_callback, rev_pick_order_callback, rev_start_callback,
    rev_rate_callback, rev_text_received, rev_skip_callback, rev_skip_command,
    rev_my_list_callback, product_reviews_view_callback,
    admin_reviews_callback, admrev_pin_callback, admrev_hide_callback, admrev_del_callback,
    REV_TEXT
)
from loyalty_extras import (
    loyalty_callback, admin_loyalty_callback, notify_tier_upgrade,
    # 🆕 v68: tier customization
    admin_tier_cfg_callback, admin_tier_toggle_bonus_callback,
    admin_tier_toggle_msg_callback, admin_tier_edit_callback,
    admin_tier_field_callback, admin_tier_value_received,
    admin_tier_reset_confirm_callback, admin_tier_reset_do_callback,
)
# 🆕 v38: Advanced action system
from handlers_buttons import custom_button_action_callback
from handlers_admin import cb_nav_target_callback
from admin_panels import (
    analytics_callback, analytics_period_callback,
    analytics_top_products_callback, analytics_top_customers_callback,
    analytics_payment_callback, analytics_chart_callback,
)
# 🆕 v73: Supplier Panel imports REMOVED (user requested permanent removal).
# Supplier handler files deleted. DB tables (suppliers, supplier_stock, etc.)
# left intact for data safety — they are simply unused now.

# 🆕 v73: Completed Orders + Replacement History panels
from admin_panels import (
    admin_completed_orders_callback, admin_completed_filter_callback,
    # 🆕 v80: Payment Methods Enable/Disable
    admin_payment_toggle_callback, admin_payment_toggle_action_callback,
    admin_payment_msg_start_callback, admin_payment_msg_received,
)
# 🆕 v81: External Suppliers (Akunding/Canboso/MMOStore/TunVNMMO)
from ext_suppliers import (
    admin_suppliers_callback, ext_sup_add_callback, ext_sup_add_type_callback,
    ext_sup_api_key_received, ext_sup_view_callback, ext_sup_test_callback,
    ext_sup_api_update_callback, ext_sup_api_update_received,
    ext_sup_toggle_callback, ext_sup_del_callback, ext_sup_del_confirm_callback,
    ext_sup_import_all_callback, ext_sup_import_pick_callback,
    ext_prod_view_callback, ext_prod_toggle_callback,
    ext_prod_markup_callback, ext_prod_set_mkp_callback,
    ext_sup_bulk_markup_callback, ext_sup_bulk_set_callback,
    ext_sup_preset_callback, ext_sup_noop_callback,
    ext_prod_emoji_callback, ext_prod_emoji_received,
    ext_prod_cat_callback, ext_prod_setcat_callback,
    # 🆕 v81.1: Fixed price (Smart Lock)
    ext_prod_fixprice_callback, ext_prod_fixprice_set_callback,
    ext_prod_fixprice_received, ext_prod_fixprice_clear_callback,
    # 🆕 v83: Manual sync + format picker
    ext_prod_sync_callback, ext_prod_refresh_callback, ext_prod_fmt_callback, ext_prod_setfmt_callback,
    # 🆕 v136: supplier failure retry window + delayed refund
    supplier_retry_delivery_callback, supplier_retry_refund_job,
)
from support_replacement import (
    admin_replacement_history_callback, admin_replacement_filter_callback,
    admin_replacement_view_callback, admin_replacement_action_callback,
)

# 🆕 v84: Maintenance Mode + Completed Orders (grouped by user, searchable)
from maintenance_mode import (
    maintenance_gate, _MaintBlocked,
    maint_panel_callback, maint_toggle_callback, maint_preview_callback,
    maint_pick_callback, maint_noop_callback,
    maint_edit_custom_entry, maint_custom_received, maint_custom_cancel,
    MAINT_CUSTOM_TEXT,
)
from completed_orders_v2 import (
    admin_completed_v2_callback, ac2_page_callback,
    ac2_user_callback, ac2_order_callback, ac2_userview_callback, ac2_noop_callback,
    ac2_dlfile_callback, ac2_allfiles_callback, ac2_dlv_callback, ac2_dlvopen_callback,  # v161.20 + v170.5
    ac2_sf_callback, ac2_resend_callback,  # 🆕 v170.17
    ac2_clear_search_callback,
    ac2_search_entry, ac2_search_received, ac2_search_cancel,
    AC2_SEARCH_TEXT,
)
# 🆕 v85: Supplier automation — auto-sync + bulk sync + low-bal alerts + finance
from supplier_automation import (
    autosync_price_stock_job, autosync_balance_job,
    AUTOSYNC_PRICE_STOCK_INTERVAL, AUTOSYNC_BALANCE_INTERVAL,
    ext_sup_bulk_sync_callback,
    ext_sup_bulk_unsync_callback,
    ext_sup_lowbal_callback, ext_sup_lowbal_received, ext_sup_lowbal_cancel,
    LOWBAL_EDIT_STATE,
    # 🆕 v96: supplier rename
    ext_sup_rename_callback, ext_sup_rename_received, ext_sup_rename_cancel,
    SUP_RENAME_STATE,
    admin_finance_callback, fin_p_callback,
    admin_autosync_callback, autosync_toggle_callback,
)
# 🆕 v86: InstaAPI supplier — add via connection string (single paste)
from insta_api_flow import (
    ext_sup_add_conn_callback, ext_sup_add_conn_received,
    ext_sup_add_conn_cancel, CONN_STRING_STATE,
)
# 🆕 v87: Auto-Translator (Gemini-powered, from→to, full scan + backend hook)
from auto_translator import (
    admin_translator_callback, trxl_toggle_callback,
    trxl_pick_from_callback, trxl_pick_to_callback,
    trxl_set_callback, trxl_noop_callback,
    trxl_scan_confirm_callback, trxl_scan_run_callback,
    trxl_clear_cache_callback,
)
# 🆕 v92: Main Menu Layout Picker (50 layouts + auto-fit custom buttons)
from main_menu_layout_picker import (
    mml_hub_callback, mml_cat_callback, mml_view_callback,
    mml_apply_callback, mml_preview_callback, mml_reset_callback,
    main_more_expand_callback,
)
# 🆕 v94: Global broadcast button color picker
from broadcast_color_panel import (
    broadcast_color_panel_callback, broadcast_color_set_callback,
)

# 🆕 v75: User-facing API Management REMOVED (user keeping Worker deployment).

# 🆕 v76: Universal Main Menu force-exit + How-to-Use guide hub
from ui_extras import force_main_menu_callback
from ui_extras import how_to_hub_callback, guide_screen_callback
# 🆕 Force Join + Activity Destinations
from ui_extras import (
    fj_panel_callback, fj_toggle_callback,
    fj_set_msg_callback, fj_msg_received,
    fj_test_callback, fj_verified_callback,
    fj_reset_msg_callback, fj_noop_callback,
    fj_add_callback, fj_add_link_received,
    fjm_callback, fjm_ren_callback, fjm_ren_received,
    fjm_col_callback, fjm_emo_callback, fjm_emo_received,
    fjm_emo_clear_callback, fjm_link_callback, fjm_link_received,
    fjm_del_callback, fjm_del_yes_callback, fjm_move_callback,
    fj_bulk_callback, fjb_t_callback, fjb_all_callback,
    fjb_none_callback, fjb_del_callback,
    fj_vbtn_callback, fj_vbtn_col_callback, fj_vbtn_ren_callback,
    fj_vbtn_ren_received, fj_vbtn_emo_callback, fj_vbtn_emo_received,
    fj_vbtn_emo_clear_callback,
    dest_panel_callback, dest_set_callback, dest_clear_chat_callback,
    dest_set_chat_callback, dest_chat_received,
    FJ_MSG, DEST_CHAT,
    admin_lang_system_callback, langsys_preview_callback,  # 🆕 v161.20 Language System
)
# 🆕 Per-User Lifetime Fake Activity
from per_user_activity import restore_all_jobs, setup_activity_table, activity_watchdog_job, fake_activity_status_message
from ui_extras import (
    activity_panel_callback,
    act_toggle_global_callback, act_toggle_unit_callback, act_toggle_type_callback,
    act_set_speed_callback, act_speed_received,
    act_set_delay_callback, act_delay_received,
    act_users_callback, act_user_toggle_callback,
    act_stop_all_callback, act_start_all_callback,
    act_noop_callback, ACT_SPEED, ACT_DELAY,
    act_set_offset_callback, act_offset_received, act_offset_random_callback, ACT_OFFSET,
)
# 🆕 Location Customizer + Template Editor
from customization import (
    location_customizer_panel_callback,
    # 🆕 v95: Add Custom Location conversation
    lc_add_custom_start, lc_add_id_received, lc_add_name_received,
    lc_add_header_received, lc_add_cancel,
    LC_ADD_ID, LC_ADD_NAME, LC_ADD_HEADER,
    lc_pick_location_callback,
    lc_set_header_callback, lc_header_received,
    lc_set_cols_callback, lc_set_sep_callback,
    lc_reset_callback, lc_noop_callback,
    LC_HEADER,
    # Template editor kept accessible via act_panel → 📝 Templates
    template_editor_panel_callback,
    tpl_pick_callback, tpl_edit_callback,
    tpl_text_received, tpl_reset_callback,
    tpl_preview_callback, tpl_noop_callback,
    tpl_setvar_callback, tpl_test_callback,
    sb_template_panel_callback, sb_template_set_callback,
    sb_custom_start_callback, sb_custom_received, sb_test_callback, SB_CUSTOM_TEXT,
    TPL_TEXT,
)
# 🆕 Product Design System
from handlers_buttons import (
    product_design_panel_callback,
    pd_layout_callback, pd_style_callback,
    pd_field_toggle_callback, pd_perpage_callback,
    pd_btnsize_callback, pd_reset_callback, pd_noop_callback,
)
# 🆕 v40: Inline Button Styler — per-button size/align/pad
from handlers_buttons import get_button_styler_handlers
# 🆕 v78: API Management UI imports REMOVED — admin panel button gone.
# Functions still exist in admin_panels.py for safety but never invoked.
# 🆕 v47-49: Free-via-Referrals (admin config + user claim flow + smart share + button editor)
from handlers_free_claim import (
    fcrf_panel_callback, fcrf_toggle_callback,
    fcrf_setrefs_callback, fcrf_tpllist_callback, fcrf_pick_callback,
    fcrf_custom_callback, fcrf_preview_callback, fcrf_test_callback,
    fcrf_history_callback, fcrf_text_received,
    fcrf_refs_callback,  # 🆕 v110 — per-product referrals tracker
    freeclaim_open_callback, freeclaim_do_callback,
    freeclaim_share_callback,  # 🆕 v48
    # 🆕 v49 — per-product broadcast button editor
    fcb_panel_callback, fcb_settext_callback, fcb_setemoji_callback,
    fcb_styler_callback, fcb_color_callback, fcb_pickcolor_callback,
    fcb_preview_callback, fcb_reset_callback, fcb_text_received,
)
# 🆕 v170.13 — Freebies (free products for every user)
from handlers_freebies import (
    freebies_menu_callback, freebies_from_text, freebie_open_callback,
    freebie_do_callback, freebies_admin_panel_callback, freebie_config_callback,
    freebie_toggle_callback, freebie_limit_callback, freebie_refs_callback,
    freebie_step_received,
)
# 🆕 v48: Referral Abuse admin panel
from handlers_referral_admin import (
    refadm_panel_callback, refadm_top_callback, refadm_log_callback, refadm_banlist_callback,
    refadm_ban_start, refadm_unban_start, refadm_adjust_start,
    refadm_tpl_panel_callback, refadm_tpl_edit_callback,
    refadm_tpl_ready_callback, refadm_tpl_apply_callback,
    refadm_tpl_preview_callback, refadm_tpl_reset_all_callback,
    refadm_btn_panel_callback, refadm_btn_edit_callback,
    refadm_btn_color_callback, refadm_btn_reset_callback,
    refadm_text_received,
    refadm_set_points_start, refadm_set_points_received,
    refadm_prod_panel_callback, refadm_prod_detail_callback,
    refadm_math_toggle_callback, refadm_bonus_start,  # 🆕 v161.20 milestone bonus
)
# 🆕 v50: Screen-by-Screen Editor (drill-down user-side editor)
from customization import (
    se_root_callback, se_open_callback,
    se_btns_callback, se_sub_callback, se_subbtn_callback,
    se_edittext_callback, se_text_received,
    se_preview_callback, se_reset_callback,
    se_allcolor_callback, se_setallcol_callback,
    se_noop_callback,
    bypl_apply_callback, bypl_preview_callback,
    scl_apply_callback, scl_preview_callback,
)
# 🆕 Fake Broadcast & Fake Reviews systems
# fake_broadcast + fake_reviews panels removed (use Fake Activity instead)
# broadcast_new_user_join kept for new-user join notification
from fake_engagement import broadcast_new_user_join, admin_bcast_test_callback
# 🆕 v24: Removed gmail_checker (replaced by Binance API)
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)




async def global_error_handler(update, context):
    """Log uncaught handler errors so bugs are visible instead of silent."""
    logging.getLogger(__name__).exception("Unhandled bot error", exc_info=context.error)
    try:
        if update and getattr(update, "effective_message", None):
            # 🐛 v147 FIX: never reply "Temporary error" inside a group — the
            # bot must stay silent in groups (see _is_group_chat).
            if _is_group_chat(update):
                return
            await update.effective_message.reply_text("⚠️ Temporary error. Please try again.")
    except Exception:
        pass


def _is_group_chat(update) -> bool:
    """🐛 v147 FIX (Bug4): True when the incoming update is from a GROUP or
    SUPERGROUP. The owner wants the bot to NEVER auto-respond to any user
    message in a group (text / voice / photo / anything) — whether or not the
    bot is admin there. All main message/command handlers early-return on this.
    """
    try:
        chat = update.effective_chat
        if chat is None:
            return False
        ct = str(getattr(chat, "type", "") or "")
        return ct in ("group", "supergroup")
    except Exception:
        return False


async def _flush_tier_notifications(context):
    """🆕 v37: Notify any users who got tier upgrades."""
    try:
        from database import pop_pending_tier_upgrades
        for uid, tier_key in pop_pending_tier_upgrades():
            await notify_tier_upgrade(context.bot, uid, tier_key)
    except Exception:
        pass


async def payment_flow_text_handler(update, context):
    """🔧 v124 CRITICAL FIX: payment text inputs must NEVER be swallowed by a
    stale ConversationHandler (support ticket / warranty / admin chat states are
    allow_reentry=True with NO timeout — a user who started and abandoned one
    stays 'in conversation' forever, so their later text (e.g. a Bybit amount)
    was claimed by that conversation and the bot appeared STUCK).

    This handler is registered in a NEGATIVE group (before all conversations)
    and only consumes text when a payment-flow step is actually active; otherwise
    it returns None and the update flows on to normal handlers.
    """
    ud = context.user_data
    # 🐛 v147 FIX (Bug4): never consume/answer payment-flow steps from group
    # messages — bot must be silent in groups.
    if _is_group_chat(update):
        return None
    # 🟡 v125: unified Bybit flow (warning → UID → amount → deposit)
    # 🔧 v127: never silent — any flow exception is logged and the customer gets
    # a visible fallback instead of nothing.
    _bf = ud.get('bybit_flow') or {}
    try:
        if _bf.get('step') == 'waiting_uid':
            if await bybit_flow_uid_received(update, context): return True
        if _bf.get('step') == 'waiting_amount':
            if await bybit_flow_amount_received(update, context): return True
    except Exception as _e:
        logging.getLogger(__name__).exception("[BybitFlow] priority handler error")
        try:
            await update.effective_message.reply_text(
                "⚠️ *Oops — something went wrong with your payment step.*\n"
                "Please try again, or open a support ticket if it keeps happening.",
                parse_mode="Markdown")
        except Exception:
            pass
        return True
    # TXID / TID pastes (crypto + EP/JC + points custom)
    if ud.get('usdt_step') == 'waiting_txid':
        if await usdt_txid_received(update, context): return True
    if ud.get('bybit_step') == 'waiting_txid':
        if await bybit_txid_received(update, context): return True
    if ud.get('ep_step') == 'waiting_tid':
        if await ep_tid_received(update, context): return True
    if ud.get('jc_step') == 'waiting_tid':
        if await jc_tid_received(update, context): return True
    if ud.get('points_step') == 'waiting_custom_amount':
        if await points_custom_amount_received(update, context): return True
    # Not a payment-flow step — let other handlers process it
    return None


def _reply_btn_matches(t, english_label, user_id=None):
    """🆕 v137: true when the tapped reply-keyboard text equals the English
    label OR any of its translations for this user (persistent keyboard
    labels now follow the selected language)."""
    if t == english_label:
        return True
    try:
        from i18n import tr_user, get_user_lang
        lang = get_user_lang(user_id) if user_id else None
        for lng in ([lang] if lang else []):
            try:
                if t == tr_user(english_label, user_id=user_id, lang=lng):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


async def handle_text(update, context):
    # 🐛 v147 FIX (Bug4): groups — bot never auto-responds to any user text.
    if _is_group_chat(update):
        return
    t = update.message.text
    # 🆕 v134: referral MATH verification answer — MUST run first so a wrong
    # answer never leaks into other flows.
    if context.user_data.get('fj_math'):
        from handlers_start import handle_math_answer
        if await handle_math_answer(update, context):
            return
    # 🆕 v135: force-join admin text-input steps (add target / rename / emoji / link / verify-btn)
    if context.user_data.get('fj_add_link'):
        if await fj_add_link_received(update, context): return
    if context.user_data.get('fj_ren_target'):
        if await fjm_ren_received(update, context): return
    if context.user_data.get('fj_emo_target'):
        if await fjm_emo_received(update, context): return
    if context.user_data.get('fj_link_target'):
        if await fjm_link_received(update, context): return
    if context.user_data.get('fj_vbtn_ren'):
        if await fj_vbtn_ren_received(update, context): return
    if context.user_data.get('fj_vbtn_emo'):
        if await fj_vbtn_emo_received(update, context): return
    # 🆕 v144: customization text inputs (search / import / banner)
    if context.user_data.get('adm_users_search'):
        if await adm_users_search_received(update, context): return
    if context.user_data.get('cz_search'):
        if await cz_search_received(update, context): return
    if context.user_data.get('cz_import'):
        if await cz_import_received(update, context): return
    if context.user_data.get('cz_banner_text'):
        if await cz_banner_text_received(update, context): return
    # 🆕 v170.12: persistent button rename text input
    if context.user_data.get('persist_ren_pid'):
        from handlers_admin import persist_rename_received
        if await persist_rename_received(update, context): return
    # 🆕 v170.13: freebie admin text input (claim limit / reclaim refs)
    if context.user_data.get('freebie_step'):
        from handlers_freebies import freebie_step_received
        if await freebie_step_received(update, context): return
    # 🆕 v170.11: dynamic-button rename text input (product-detail buttons etc.)
    if context.user_data.get('bs_ren_key'):
        from handlers_buttons import bs_rename_received
        if await bs_rename_received(update, context): return
    # 🆕 v144.3: replacement upload text
    if context.user_data.get('rep_upload_oid'):
        if await admin_replace_upload_received(update, context): return
    # v132: global premium-emoji capture foundation. Any future text-input
    # feature can read these keys instead of losing premium emoji entities.
    try:
        from utils import capture_user_text, has_premium_emoji
        context.user_data['_last_captured_text'] = capture_user_text(update.message) or (t or '')
        context.user_data['_last_has_premium_emoji'] = bool(has_premium_emoji(update.message))
    except Exception:
        context.user_data['_last_captured_text'] = t or ''
        context.user_data['_last_has_premium_emoji'] = False
    # 🔧 BUG FIX #3: Removed _flush_tier_notifications() from here.
    # It was called on EVERY text message from EVERY user, querying the DB
    # and trying to send messages. The background job (every 30s) already
    # handles this — no need to duplicate it here. This caused unnecessary
    # DB queries and potential message sending delays.
    # 🆕 v170.19: persistent reply-keyboard dispatch — CURRENT label se match
    # (custom rename + translation dono handle). 🐛 FIX: pehle hardcoded emoji
    # label match hota tha → admin ne emoji hata kar rename kiya to buttons
    # kaam karna band ho gaye (freebies/reseller/howto teeno dead).
    try:
        from keyboards import persist_button_from_text
        _pid = persist_button_from_text(t, update.effective_user.id)
        if _pid == "home":
            await handle_main_menu_button(update, context); return
        if _pid == "howto":
            from handlers_start import handle_how_to_button
            await handle_how_to_button(update, context); return
        if _pid == "reseller":
            from handlers_start import handle_reseller_button
            await handle_reseller_button(update, context); return
        if _pid == "freebies":
            from handlers_start import handle_freebies_button
            await handle_freebies_button(update, context); return
        if _pid == "shop":
            from handlers_start import handle_shop_button
            await handle_shop_button(update, context); return
        if _pid == "balance":
            from handlers_start import handle_balance_button
            await handle_balance_button(update, context); return
        if _pid == "deposit":
            from handlers_start import handle_deposit_button
            await handle_deposit_button(update, context); return
        if _pid == "history":
            from handlers_start import handle_history_button
            await handle_history_button(update, context); return
        if _pid == "language":
            from handlers_start import handle_language_button
            await handle_language_button(update, context); return
    except Exception as _pe:
        pass
    # 🆕 v50: Screen-by-Screen Editor text input MUST run BEFORE any other 'erk'
    # consumer so admin's response edits go through our flow (with smart back).
    if context.user_data.get('se_back_sid'):
        if await se_text_received(update, context): return
    # 🤖 AI mode — admin's text goes to AI (only when admin enabled it)
    if context.user_data.get('ai_mode'):
        if await handle_ai_message(update, context): return
    # 🆕 Binance Gmail flow (name → amount)
    if context.user_data.get('binance_step') == 'waiting_name':
        if await binance_name_received(update, context): return
    if context.user_data.get('binance_step') == 'waiting_amount':
        if await binance_amount_received(update, context): return
    # 🆕 v62: Binance Order-ID flow (clean professional flow when API toggle ON)
    if context.user_data.get('binance_step') == 'waiting_order_id':
        from handlers_order import binance_order_id_received
        if await binance_order_id_received(update, context): return
    # 🆕 v63: Admin adding a proxy URL via 📡 Proxy Status → Add Proxy
    if context.user_data.get('admin_proxy_step') == 'waiting_url':
        from handlers_admin import admin_proxy_url_received
        if await admin_proxy_url_received(update, context): return
    # 🆕 v65: Admin typing cancellation reason for an order
    if context.user_data.get('adm_cancel_step') == 'waiting_reason':
        if await adm_cancel_reason_received(update, context): return
    # 🆕 v68: Admin typing tier config value (threshold / bonus / message)
    if context.user_data.get('admin_tier_edit_step') == 'waiting_value':
        if await admin_tier_value_received(update, context): return
    # 🆕 v70: Admin typing pinned-announcement text
    if context.user_data.get('admin_pin_step') == 'waiting_text':
        if await admin_pin_text_received(update, context): return
    # 🆕 v80: Admin editing payment method unavailable message
    if context.user_data.get('admin_pay_msg_editing'):
        if await admin_payment_msg_received(update, context): return
    # 🆕 v136: External supplier API update for one existing supplier
    if context.user_data.get('ext_sup_api_update_sid'):
        if await ext_sup_api_update_received(update, context): return
    # 🆕 v81: External Suppliers — admin sending API key or premium emoji
    if context.user_data.get('ext_sup_wizard', {}).get('step') == 'waiting_api_key':
        if await ext_sup_api_key_received(update, context): return
    if context.user_data.get('ext_prod_emoji_pending'):
        if await ext_prod_emoji_received(update, context): return
    # 🆕 v81.1: Admin typing fixed selling price
    if context.user_data.get('ext_prod_fixprice_pending'):
        if await ext_prod_fixprice_received(update, context): return
    # 🆕 v30: waiting_screenshot is handled by handle_screenshot (MessageHandler)
    # 🆕 v25: EasyPaisa flow (amount → TID → name)
    # 🆕 v31: EasyPaisa simplified — only TID input needed
    if context.user_data.get('ep_step') == 'waiting_tid':
        if await ep_tid_received(update, context): return
    # 🆕 v40.2: JazzCash now also TID-only flow (auto-verify via backend)
    if context.user_data.get('jc_step') == 'waiting_tid':
        if await jc_tid_received(update, context): return
    if context.user_data.get('points_step') == 'waiting_custom_amount':
        if await points_custom_amount_received(update, context): return
    if context.user_data.get('usdt_step') == 'waiting_txid':
        if await usdt_txid_received(update, context): return
    if context.user_data.get('bybit_step') == 'waiting_txid':
        if await bybit_txid_received(update, context): return
    # 🟡 v125: Bybit UID/amount text is handled by payment_flow_text_handler (group -80).
    if context.user_data.get('ownmail_step') == 'email':
        from handlers_order import ownmail_email_received
        if await ownmail_email_received(update, context): return
    if context.user_data.get('ownmail_step') == 'pass':
        from handlers_order import ownmail_pass_received
        if await ownmail_pass_received(update, context): return
    # DB-backed post-payment manual details flow (works even for background payment confirmations)
    try:
        from handlers_order import handle_waiting_manual_details
        if await handle_waiting_manual_details(update, context): return
    except Exception as e:
        logging.getLogger(__name__).error(f"[ManualDetails] handler error: {e}")
    if context.user_data.get('upacct_step') == 'email':
        from handlers_support import upacct_email_received
        if await upacct_email_received(update, context): return
    if context.user_data.get('upacct_step') == 'pass':
        from handlers_support import upacct_pass_received
        if await upacct_pass_received(update, context): return
    if context.user_data.get('upacct_step') == 'inst':
        from handlers_support import upacct_inst_received
        if await upacct_inst_received(update, context): return
    if context.user_data.get('admin_chat_uid'):
        from handlers_support import admin_chat_received
        if await admin_chat_received(update, context): return
    if context.user_data.get('user_chat_reply'):
        from handlers_support import user_reply_received
        if await user_reply_received(update, context): return
    # 🆕 v78: API Management removed — api_adding_external text-input flow gone.
    # 🆕 v47: Free-via-Referrals admin text inputs (required refs / custom text)
    if context.user_data.get('fcrf_step'):
        if await fcrf_text_received(update, context): return
    # 🆕 v48: Referral Abuse admin inputs (ban / unban / adjust)
    if context.user_data.get('refadm_step') == 'set_points':
        if await refadm_set_points_received(update, context): return
    if context.user_data.get('refadm_step'):
        if await refadm_text_received(update, context): return
    # ⭐ v161.25: Telegram Stars rate input
    if context.user_data.get('pm_stars_rate'):
        if await stars_rate_received(update, context): return
    # 🆕 v49: Per-product broadcast button editor inputs (text / premium emoji)
    if context.user_data.get('fcb_step'):
        if await fcb_text_received(update, context): return
    if context.user_data.get('editing_manual_oid'):
        from handlers_admin import manual_edit_received
        if await manual_edit_received(update, context): return
    if context.user_data.get('order_req_step') == 'waiting_email':
        from handlers_order import order_email_received
        if await order_email_received(update, context): return
    if context.user_data.get('order_req_step') == 'waiting_pass':
        from handlers_order import order_pass_received
        if await order_pass_received(update, context): return
    # 🆕 Bulk qty input
    if context.user_data.get('bulk_step') == 'waiting_qty':
        if await bulk_qty_received(update, context): return
    if context.user_data.get('bulk_price_step') == 'custom_percent':
        if await bulk_price_custom_received(update, context): return
    # 🆕 v158: bulk discount tier input (qty → price)
    if context.user_data.get('bdisc_step') == 'qty':
        if await bdisc_qty_received(update, context): return
    if context.user_data.get('bdisc_step') == 'price':
        if await bdisc_price_received(update, context): return
    if context.user_data.get('broadcast_button_step') == 'name':
        if await broadcast_button_name_received(update, context): return
    # 🐛 v147 FIX (Bug7): broadcast button custom-link input
    if context.user_data.get('broadcast_button_step') == 'url':
        if await broadcast_button_url_received(update, context): return
    # 🐛 v157: replacement rejection reason input
    if context.user_data.get('rej_reason_oid'):
        if await admin_replace_reject_reason_received(update, context): return
    # 🆕 v161.12: warranty/refund rejection reason input
    if context.user_data.get('wr_reject_wid'):
        if await adm_wr_reject_reason_received(update, context): return
    # 🆕 v148: Poll creation text steps (question → options)
    if context.user_data.get('poll_step') == 'poll_q':
        if await poll_question_received(update, context): return
    if context.user_data.get('poll_step') == 'poll_options':
        if await poll_options_received(update, context): return
    # 🆕 v149: Refund-by-User-ID text steps (id → amount → reason) + history-id
    if context.user_data.get('ruid_step') == 'id':
        if await adm_refund_uid_received(update, context): return
    if context.user_data.get('ruid_step') == 'amt':
        if await adm_refund_uid_amt_received(update, context): return
    if context.user_data.get('ruid_step') == 'reason':
        if await adm_refund_uid_reason_received(update, context): return
    if context.user_data.get('ruid_step') == 'uhist_id':
        if await adm_uhist_id_received(update, context): return
    if context.user_data.get('fake_custom_broadcast'):
        if await handle_fake_custom_broadcast_message(update, context): return
    if context.user_data.get('broadcasting'):
        await handle_broadcast_message(update, context); return
    # 🆕 FIX: Payment-email edit (Change Email / Change App Password)
    if context.user_data.get('pem_edit'):
        from handlers_admin import admin_pem_value_received
        if await admin_pem_value_received(update, context): return
    # 🆕 FIX: Edit product/category/account fields (no longer in ConversationHandler)
    if context.user_data.get('edit_pid'):
        if await edit_product_field_received(update, context): return
    if context.user_data.get('edit_cat_id'):
        if await edit_category_field_received(update, context): return
    if context.user_data.get('edit_acct_id'):
        if await edit_account_field_received(update, context): return


async def force_main_menu_text_callback(update, context):
    """High-priority persistent keyboard Main Menu panic reset."""
    await handle_main_menu_button(update, context)
    raise ApplicationHandlerStop


def _jobs_paused_for_maintenance() -> bool:
    try:
        from maintenance_mode import is_maintenance_on
        return bool(is_maintenance_on())
    except Exception:
        return False


async def _tier_flush_job(context):
    if _jobs_paused_for_maintenance():
        return
    """🆕 v37: Periodic flush of pending tier upgrade notifications."""
    try:
        from database import pop_pending_tier_upgrades
        for uid, tier_key in pop_pending_tier_upgrades():
            await notify_tier_upgrade(context.bot, uid, tier_key)
    except Exception:
        pass


async def _flash_expiry_job(context):
    if _jobs_paused_for_maintenance():
        return
    """🆕 Auto-disable flash sales whose timer has ended."""
    try:
        from database import expire_old_flash_sales
        expire_old_flash_sales()
    except Exception:
        pass


async def _purchase_broadcast_job(context):
    if _jobs_paused_for_maintenance():
        return
    """🆕 Drain queued REAL purchases → broadcast to fake-activity destination.

    🆕 v170.25: real FREEBIE claims bhi yahan drain hote hain (bc_freebie
    template, gated by fbc_type_freebie toggle) — "new purchase" nahi."""
    try:
        from database import pop_pending_purchase_broadcasts
        from fake_engagement import build_real_purchase_message, broadcast_store_message
        for item in pop_pending_purchase_broadcasts():
            try:
                text = build_real_purchase_message(item["product_name"], item.get("qty", 1), pid=item["product_id"])
                await broadcast_store_message(context.bot, text, pid=item["product_id"])
            except Exception as e:
                print(f"[PurchaseBroadcast] item failed: {e}")
    except Exception:
        pass
    # 🆕 v170.25: FREEBIE broadcasts (toggle-gated)
    try:
        from database import pop_pending_freebie_broadcasts
        from fake_engagement import (build_real_freebie_message,
                                     broadcast_store_message, is_type_enabled)
        if is_type_enabled("freebie"):
            for item in pop_pending_freebie_broadcasts():
                try:
                    text = build_real_freebie_message(item["product_name"], pid=item["product_id"])
                    await broadcast_store_message(context.bot, text, pid=item["product_id"],
                                                  tpl_id="bc_freebie")
                except Exception as e:
                    print(f"[FreebieBroadcast] item failed: {e}")
        else:
            pop_pending_freebie_broadcasts()  # toggle OFF → clear queue
    except Exception:
        pass


async def _payment_pending_reminder_job(context):
    if _jobs_paused_for_maintenance(): return
    try:
        from database import get_pending_payment_reminders, mark_payment_reminder
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        for o in get_pending_payment_reminders(limit=30):
            try:
                count = int(o.get('payment_reminder_count') or 0)
                msg = (
                    f"⏳ *Payment Reminder — Order #{o['id']}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📦 {o['product_name']}\n"
                    f"💰 Amount: ${float(o['price'] or 0):.2f}\n\n"
                    f"Your order is still waiting for payment. Complete it soon, or create a new order if you changed your mind."
                    if count == 0 else
                    f"⚠️ *Final Payment Reminder — Order #{o['id']}*\n\nThis unpaid order may expire soon."
                )
                await context.bot.send_message(o['user_id'], msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📜 Order History', callback_data='my_orders')],
                    [InlineKeyboardButton('❌ Cancel Payment', callback_data='cancel_order')],
                ]))
                mark_payment_reminder(o['id'])
            except Exception:
                pass
    except Exception as e:
        print(f'[PaymentReminder] job failed: {e}')


async def _abandoned_cart_job(context):
    if _jobs_paused_for_maintenance(): return
    try:
        from database import get_abandoned_cart_due, mark_abandoned_cart_sent
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        for r in get_abandoned_cart_due(minutes=30, limit=30):
            try:
                await context.bot.send_message(
                    r['user_id'],
                    f"👀 *Still interested?*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📦 {r['name']}\n"
                    f"💰 Price: ${float(r['price'] or 0):.2f}\n"
                    f"📊 Stock: {int(r['stock'] or 0)}\n\n"
                    f"Tap below to continue your order.",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🛒 View Product', callback_data=f"prod_{r['product_id']}")]])
                )
                mark_abandoned_cart_sent(r['user_id'], r['product_id'])
            except Exception:
                pass
    except Exception as e:
        print(f'[AbandonedCart] job failed: {e}')


async def _daily_admin_summary_job(context):
    try:
        from datetime import datetime, timezone, timedelta
        from database import get_setting, set_setting, get_daily_summary_stats
        pk = datetime.now(timezone(timedelta(hours=5)))
        if not (pk.hour == 23 and pk.minute == 59):
            return
        key = f"daily_summary_sent_{pk.date().isoformat()}"
        if get_setting(key, '0') == '1':
            return
        st = get_daily_summary_stats()
        await context.bot.send_message(
            ADMIN_ID,
            f"📊 *Daily Summary — {pk.strftime('%Y-%m-%d')}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛒 Delivered orders: *{st['orders']}*\n"
            f"💰 Revenue: *${st['revenue']:.2f}*\n"
            f"💸 Refunds: *{st['refunds']}*\n"
            f"👥 New users: *{st['new_users']}*\n"
            f"🏆 Top product: *{st['top_product'] or 'N/A'}* ({st['top_count']})",
            parse_mode='Markdown'
        )
        set_setting(key, '1')
    except Exception as e:
        print(f'[DailySummary] failed: {e}')


async def _supplier_new_products_job(context):
    if _jobs_paused_for_maintenance(): return
    try:
        from ext_suppliers import list_suppliers, get_adapter_for_supplier, get_ext_products, upsert_ext_product, detect_product_format, update_ext_product
        from async_adapter_helpers import async_fetch_products
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        for sup in list_suppliers(include_disabled=False):
            sid = int(sup.get('id') or 0)
            ad = get_adapter_for_supplier(sup)
            if not ad: continue
            fresh = await async_fetch_products(ad)
            if not fresh: continue
            existing = {str(ep.get('remote_id')) for ep in get_ext_products(supplier_id=sid)}
            new_items = [p for p in fresh if str(p.get('remote_id')) not in existing]
            if not new_items: continue
            shown=[]
            for p in new_items[:10]:
                try:
                    eid = upsert_ext_product(sid, p.get('remote_id'), p.get('name') or '', p.get('description') or '', p.get('cost_usd') or 0, p.get('stock') or 0, raw_json=__import__('json').dumps(p.get('raw') or {}, ensure_ascii=False))
                    fmt = detect_product_format(p)
                    if fmt: update_ext_product(eid, delivery_format=fmt, format_detected=1)
                    shown.append((eid, p))
                except Exception:
                    pass
            if shown:
                lines=[f"🆕 *New Supplier Products Detected*", "━━━━━━━━━━━━━━━━━━━━", f"🏬 Supplier: *{sup.get('name','?')}*", ""]
                kb=[]
                for eid,p in shown[:5]:
                    lines.append(f"• {p.get('name','?')[:70]} — cost ${float(p.get('cost_usd') or 0):.2f}, stock {int(p.get('stock') or 0)}")
                    kb.append([InlineKeyboardButton(f"🔄 Sync {str(p.get('name','?'))[:30]}", callback_data=f"ext_prod_sync_{eid}")])
                kb.append([InlineKeyboardButton('⚙️ Supplier Panel', callback_data=f"ext_sup_view_{sid}")])
                await context.bot.send_message(ADMIN_ID, '\n'.join(lines), parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        print(f'[SupplierNewProducts] failed: {e}')


async def _payment_risk_alert_job(context):
    try:
        from database import get_unnotified_payment_risks, mark_payment_risk_notified
        for r in get_unnotified_payment_risks(limit=20):
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"⚠️ *Payment Risk Alert*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 User: `{r['user_id']}`\n"
                    f"🛒 Order: `#{r['order_id']}`\n"
                    f"📊 Score: *{r['score']}*\n"
                    f"💰 Amount: `{r['amount']}`\n"
                    f"🧾 TXID: `{str(r['txid'])[:60]}`\n"
                    f"❌ Reason: {r['reason']}",
                    parse_mode='Markdown'
                )
                mark_payment_risk_notified(r['id'])
            except Exception:
                pass
    except Exception as e:
        print(f'[PaymentRisk] alert job failed: {e}')


async def _delayed_live_notify_job(context):
    """Send BOSS BOT IS LIVE only after DB looks stable for restore workflow.
    🔧 v131: includes maintenance status + 2 buttons: turn OFF maintenance now,
    or keep the bot under maintenance (for manual control after deploy)."""
    try:
        from config import ADMIN_ID as _LIVE_ADMIN_ID
        from database import get_connection, get_setting
        if not _LIVE_ADMIN_ID:
            return
        conn = get_connection(); c = conn.cursor()
        try:
            c.execute("SELECT COUNT(*) FROM products")
            products = int(c.fetchone()[0] or 0)
            c.execute("SELECT COUNT(*) FROM orders")
            orders = int(c.fetchone()[0] or 0)
        finally:
            conn.close()
        from maintenance_mode import is_maintenance_on
        maint = is_maintenance_on()
        status = "🛠️ *UNDER MAINTENANCE*" if maint else "✅ *LIVE*"
        text = (
            f"BOSS BOT IS LIVE\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{status}\n"
            f"DB stable ✅ Products: {products} | Orders: {orders}\n\n"
            f"{'The bot is in maintenance — customers are blocked until you turn it OFF.' if maint else 'The bot is live and serving customers.'}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Turn OFF Maintenance", callback_data="maint_live_off")],
            [InlineKeyboardButton("🛠️ Under Maintenance (keep ON)", callback_data="maint_live_keep")],
        ])
        await context.bot.send_message(_LIVE_ADMIN_ID, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        print(f'[LiveNotify] delayed send failed: {e}')


async def maint_live_off_callback(update, context):
    """Admin taps 'Turn OFF Maintenance' on the live message → bot goes live."""
    q = update.callback_query
    try:
        if q.from_user.id != int(os.getenv("ADMIN_ID", "0") or 0):
            await q.answer("❌", show_alert=True); return
    except Exception:
        pass
    try:
        from maintenance_mode import set_maintenance
        set_maintenance(False)
        await q.answer("✅ Maintenance OFF — bot is LIVE", show_alert=True)
        try:
            await q.edit_message_text(
                "✅ *Maintenance turned OFF*\n━━━━━━━━━━━━━━━━━━━━\n"
                "The bot is now LIVE and serving customers.",
                parse_mode="Markdown")
        except Exception:
            pass
    except Exception as e:
        await q.answer(f"Error: {e}", show_alert=True)


async def maint_live_keep_callback(update, context):
    """Admin taps 'Under Maintenance (keep ON)' → stays in maintenance."""
    q = update.callback_query
    try:
        if q.from_user.id != int(os.getenv("ADMIN_ID", "0") or 0):
            await q.answer("❌", show_alert=True); return
    except Exception:
        pass
    try:
        from maintenance_mode import set_maintenance
        set_maintenance(True)
        await q.answer("🛠️ Bot stays under maintenance", show_alert=True)
        try:
            await q.edit_message_text(
                "🛠️ *Bot stays UNDER MAINTENANCE*\n━━━━━━━━━━━━━━━━━━━━\n"
                "Customers are blocked. Turn it OFF from Settings or the "
                "Admin → Maintenance panel when you're ready.",
                parse_mode="Markdown")
        except Exception:
            pass
    except Exception as e:
        await q.answer(f"Error: {e}", show_alert=True)


def _apply_startup_maintenance():
    """🔧 v131: on Render deploy, start in maintenance when MAINT_ON_START=1
    (set in render.yaml). Admin turns it OFF via the live message button or
    the Maintenance panel."""
    try:
        if os.getenv("MAINT_ON_START", "0") == "1":
            from maintenance_mode import set_maintenance
            set_maintenance(True)
            print("🛠️ MAINT_ON_START=1 → bot started in maintenance mode (admin controls OFF)")
    except Exception as e:
        print(f"⚠️ startup maintenance failed: {e}")


async def post_init(app):
    # 🆕 v80: SELF-HEAL on startup — auto-fix common issues before anything else.
    # Runs missing-table / missing-column / stale-WAL / language-default checks.
    # If Gemini API key is set AND admin has enabled it, also runs a safe
    # advisory scan (no code edits).
    try:
        from self_heal import run_all_heals, notify_admin_of_heal, _gemini_safe_scan_optional
        report = run_all_heals()
        try:
            admin_id = int(os.getenv("ADMIN_ID", "0") or 0)
            if admin_id and app.bot:
                await notify_admin_of_heal(app.bot, admin_id, report)
        except Exception:
            pass
        try:
            await _gemini_safe_scan_optional(app.bot)
        except Exception:
            pass
    except Exception as _sh_e:
        import logging as _l
        _l.getLogger(__name__).warning(f"[SelfHeal] outer failure (safe to ignore): {_sh_e}")

    # 🆕 v170.19: BLUE MENU BUTTON — bot command menu (Telegram input ke left
    # side wala blue Menu button). Commands set + menu button = commands list.
    try:
        from telegram import BotCommand, MenuButtonCommands
        _cmds = [
            BotCommand("start",    "🛍️ Open Shop"),
            BotCommand("balance",  "💰 My Balance"),
            BotCommand("deposit",  "💎 Buy Points"),
            BotCommand("orders",   "📜 My Orders"),
            BotCommand("freebies", "🎁 Free Products"),
            BotCommand("apikey",   "🔗 Reseller API Key"),
            BotCommand("language", "🌐 Change Language"),
            BotCommand("support",  "🎫 Support & Contact"),
            BotCommand("help",     "📚 How to Use"),
        ]
        await app.bot.set_my_commands(_cmds)
        await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        print("[Commands] ✅ Blue Menu Button commands set")
    except Exception as _ce:
        import logging as _l
        _l.getLogger(__name__).warning(f"[Commands] set_my_commands failed: {_ce}")

    # 🆕 v24: No more Gmail loop. Binance API verifies on-demand only.
    # 🆕 v37: Periodic tier upgrade notifier (every 30s)
    try:
        if app.job_queue:
            app.job_queue.run_repeating(_tier_flush_job, interval=30, first=10)
            # 🆕 Flash-sale auto-expiry (every 60s)
            app.job_queue.run_repeating(_flash_expiry_job, interval=60, first=30)
            # 🆕 Real-purchase broadcast drainer (every 15s)
            app.job_queue.run_repeating(_purchase_broadcast_job, interval=15, first=15)
            # 🔶 Binance Transfer Note auto-checker (silent background payment detection)
            app.job_queue.run_repeating(binance_note_background_job, interval=20, first=5, name="binance_note_checker")
            # 🪙 USDT TRC20/BEP20 on-chain deposit checker
            app.job_queue.run_repeating(usdt_deposit_background_job, interval=45, first=15, name="usdt_deposit_checker")
            # 🆕 v161.24: Bybit auto-check job REMOVED (user demand) — verification
            # only happens when the customer taps 🔍 Check Payment.
            # 🆕 v161.3: Pending reseller order reminder to admin
            app.job_queue.run_repeating(_reseller_pending_reminder_job, interval=900, first=300, name="reseller_pending_reminder")
    except Exception:
        pass
    # Fake Broadcast + Fake Reviews schedulers removed (use 🎭 Fake Activity instead)
    # 🆕 v73: Supplier System REMOVED — table setup + background jobs disabled.
    # Existing supplier DB tables are left intact (data preserved, just unused).

    # 🆕 v75: REST API server REMOVED — bot runs as Render Background Worker
    # (no public port). To re-enable: convert service to Web Service + restore api_server.py.

    # ☁️ FREE TELEGRAM CLOUD BACKUP — auto-send shop.db to a channel/DM on schedule
    try:
        if app.job_queue:
            from config import BACKUP_INTERVAL_HOURS
            interval = max(1, int(BACKUP_INTERVAL_HOURS)) * 3600
            app.job_queue.run_repeating(
                _cloud_backup_job, interval=interval, first=120,
                name="cloud_backup"
            )
            print(f"[CloudBackup] Scheduled every {BACKUP_INTERVAL_HOURS}h")
    except Exception as e:
        print(f'[CloudBackup] Job setup error: {e}')

    # 🧹 Auto-cancel unpaid payment-waiting orders older than 60 minutes
    try:
        if app.job_queue:
            app.job_queue.run_repeating(
                _cancel_unpaid_orders_job, interval=900, first=240,
                name="cancel_unpaid_old_orders",
            )
            print("[AutoCancel] Scheduled — cancels unpaid orders older than 60 min")
    except Exception as e:
        print(f'[AutoCancel] Job setup error: {e}')

    # 🗑️ Auto-purge sold accounts older than 2 months (runs daily)
    try:
        if app.job_queue:
            app.job_queue.run_repeating(
                _purge_sold_accounts_job, interval=86400, first=300,
                name="purge_sold_accounts"
            )
    except Exception as e:
        print(f'[SoldPurge] Job setup error: {e}')

    # 🆕 v65: User-click tracking wipe (daily, deletes rows older than 60 days)
    try:
        if app.job_queue:
            app.job_queue.run_repeating(
                tracking_wipe_job, interval=86400, first=600,
                name="user_tracking_wipe",
            )
    except Exception as e:
        print(f'[TrackingWipe] Job setup error: {e}')

    # 🆕 v101: Pin-expiry watchdog — every 5 min, unpin expired announcements
    # from every user's chat + mark them inactive in DB.
    try:
        if app.job_queue:
            app.job_queue.run_repeating(
                pin_expiry_watchdog_job, interval=300, first=90,
                name="pin_expiry_watchdog",
            )
            print("[PinWatchdog] Scheduled — checks every 5 min for expired pins")
    except Exception as e:
        print(f'[PinWatchdog] Job setup error: {e}')

    # 🆕 v69: 24h post-delivery review reminder (runs hourly, sends English msg)
    try:
        if app.job_queue:
            app.job_queue.run_repeating(
                review_reminder_job, interval=3600, first=300,
                name="review_reminder_24h",
            )
            print("[ReviewReminder] Hourly job scheduled — asks for review 24h after delivery")
            # 🆕 v145: auto-close stale support tickets (30 min no user reply)
            try:
                app.job_queue.run_repeating(
                    ticket_reminder_job, interval=1800, first=360,
                    name="ticket_reminder_3h")
                print("[TicketAutoClose] scheduled — resolves tickets with no reply for 30 min")
            except Exception as e:
                print(f"[TicketAutoClose] schedule error: {e}")
    except Exception as e:
        print(f'[ReviewReminder] Job setup error: {e}')

    # 🆕 v67: AI Proxy Scout — monitor proxy health, auto-find new PK proxies
    try:
        if app.job_queue:
            from ai_misc import proxy_monitor_job
            app.job_queue.run_repeating(
                proxy_monitor_job, interval=600, first=120,
                name="proxy_ai_scout_monitor",
            )
            print("[ProxyScout] AI proxy monitor scheduled (every 10 min, auto-recovers when all proxies dead)")
    except Exception as e:
        print(f'[ProxyScout] Job setup error: {e}')

    # 🆕 Per-User Lifetime Activity — restore all active user jobs on restart
    try:
        setup_activity_table()
        restore_all_jobs(app)
        # 🔧 v131: self-healing watchdog so fake activity never silently dies
        if app.job_queue:
            app.job_queue.run_repeating(activity_watchdog_job, interval=60, first=90,
                                        name="activity_watchdog")
            app.job_queue.run_once(fake_activity_status_message, when=120,
                                   name="fake_activity_status")
            print("[Activity] Watchdog + status DM scheduled")
    except Exception as e:
        print(f'[Activity] Restore error: {e}')

    # 🆕 v85/v138: Supplier auto-sync jobs
    #   - Every 30s: price+stock refresh for products with synced_to_shop=1
    #   - Every 5 min: balance refresh + admin notifications/cooldowns
    try:
        if app.job_queue:
            app.job_queue.run_repeating(
                autosync_price_stock_job,
                interval=AUTOSYNC_PRICE_STOCK_INTERVAL,
                first=45,
                name="v85_autosync_price_stock",
            )
            app.job_queue.run_repeating(
                autosync_balance_job,
                interval=AUTOSYNC_BALANCE_INTERVAL,
                first=75,
                name="v85_autosync_balance",
            )
            print(f"[v85 AutoSync] price+stock every {AUTOSYNC_PRICE_STOCK_INTERVAL}s; "
                  f"balance every {AUTOSYNC_BALANCE_INTERVAL}s")
    except Exception as e:
        print(f'[v85 AutoSync] Job setup error: {e}')

    # 🆕 v136: Supplier retry window auto-refund job
    try:
        if app.job_queue:
            app.job_queue.run_repeating(
                supplier_retry_refund_job, interval=30, first=30,
                name="supplier_retry_auto_refund",
            )
            print("[SupplierRetry] Auto-refund job scheduled — checks every 30s")
    except Exception as e:
        print(f'[SupplierRetry] Job setup error: {e}')


    # 🆕 v142: business automation jobs
    try:
        if app.job_queue:
            app.job_queue.run_repeating(_payment_pending_reminder_job, interval=300, first=180, name="payment_pending_reminders")
            app.job_queue.run_repeating(_abandoned_cart_job, interval=600, first=600, name="abandoned_cart_recovery")
            app.job_queue.run_repeating(_daily_admin_summary_job, interval=60, first=30, name="daily_admin_summary_2359_pkt")
            app.job_queue.run_repeating(_supplier_new_products_job, interval=1800, first=300, name="supplier_new_products_detector")
            app.job_queue.run_repeating(_payment_risk_alert_job, interval=300, first=240, name="payment_risk_alerts")
    except Exception as e:
        print(f'[BizJobs] setup error: {e}')

    # 🆕 v141: Live notification is delayed until startup DB checks/jobs settle.
    # This prevents admin restoring DB right after an early message while old
    # startup self-heals/jobs are still mutating the database.
    try:
        if app.job_queue:
            app.job_queue.run_once(_delayed_live_notify_job, when=180, name="boss_live_notify_stable")
        else:
            # Local tests/no job queue: do nothing; Render worker has job_queue.
            pass
    except Exception as e:
        print(f'[LiveNotify] schedule failed: {e}')


# 🔧 v39 Bug #21: Proper async cancel handlers (replacing broken sync lambdas)
async def _cancel_adm_reply(update, context):
    """Cancel admin reply conversation."""
    context.user_data.pop('adm_reply_tid', None)
    try:
        await update.message.reply_text("❌ Cancelled.")
    except Exception:
        pass
    return ConversationHandler.END


async def _cancel_adm_deliver(update, context):
    """Cancel admin manual delivery conversation."""
    context.user_data.pop('manual_deliver_oid', None)
    try:
        await update.message.reply_text("❌ Cancelled.")
    except Exception:
        pass
    return ConversationHandler.END


async def _cloud_backup_job(context):
    """☁️ Send the shop.db database file to the backup channel (or admin DM).
    Telegram gives free unlimited file storage, so this keeps your data safe."""
    import os, shutil
    from datetime import datetime as _dt
    try:
        from config import BACKUP_CHANNEL_ID, ADMIN_ID
        from database import DB_PATH
        target = BACKUP_CHANNEL_ID or ADMIN_ID
        if not os.path.exists(DB_PATH):
            return
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        tmp = os.path.join("/tmp", f"autobackup_{ts}.db") if os.path.exists("/tmp") else f"autobackup_{ts}.db"
        shutil.copy2(DB_PATH, tmp)
        size_kb = os.path.getsize(tmp) / 1024
        with open(tmp, "rb") as f:
            await context.bot.send_document(
                chat_id=target,
                document=f,
                filename=f"shop_backup_{ts}.db",
                caption=(
                    f"☁️ *Auto Backup*\n"
                    f"📅 {_dt.now().strftime('%d %b %Y %I:%M %p')}\n"
                    f"💾 {size_kb:.1f} KB\n\n"
                    f"_Restore via Admin → Backup → Restore from File_"
                ),
                parse_mode="Markdown",
            )
        try:
            from database import set_setting
            set_setting('backup_last_status', 'ok')
            set_setting('backup_last_at', _dt.now().strftime('%Y-%m-%d %H:%M:%S'))
            set_setting('backup_last_size_kb', f'{size_kb:.1f}')
        except Exception:
            pass
        try: os.remove(tmp)
        except Exception: pass
    except Exception as e:
        try:
            from database import set_setting
            set_setting('backup_last_status', f'error: {str(e)[:160]}')
            set_setting('backup_last_at', _dt.now().strftime('%Y-%m-%d %H:%M:%S'))
        except Exception:
            pass
        import logging
        logging.getLogger(__name__).error(f"[CloudBackup] {e}")


async def _cancel_unpaid_orders_job(context):
    """Cancel unpaid payment-waiting orders older than the timeout window.

    🔧 AUDIT-FIX H3 (2026-07-31): the old query only covered
    binance/easypaisa/jazzcash — USDT TRC20/BEP20 and Bybit waiting orders were
    never cancelled and could sit in 'usdt_waiting'/'bybit_waiting' forever.

    Window: default 60 minutes (same as before). Admins can override per
    deployment via bot_settings key 'unpaid_order_timeout_minutes' (the value
    is cached in the DB row, so it applies from the next run of this job).
    """
    try:
        from database import get_connection, get_setting
        conn = get_connection(); c = conn.cursor()
        try:
            timeout_min = max(5, int(get_setting('unpaid_order_timeout_minutes', '60') or 60))
        except Exception:
            timeout_min = 60
        c.execute("""
            UPDATE orders
               SET status='cancelled'
             WHERE status IN ('binance_waiting','screenshot_sent','pending',
                              'usdt_waiting','bybit_waiting')
               AND LOWER(COALESCE(payment_method,'')) IN
                   ('binance','easypaisa','jazzcash',
                    'usdt_trc20','usdt_bep20',
                    'bybit_pay','bybit_usdt_trc20','bybit_usdt_bep20')
               AND datetime(created_at, '+' || ? || ' minutes') < CURRENT_TIMESTAMP
        """, (int(timeout_min),))
        changed = c.rowcount
        conn.commit(); conn.close()
        if changed:
            print(f"[AutoCancel] cancelled {changed} unpaid old order(s) (window {timeout_min} min)")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[AutoCancel] {e}")


async def _purge_sold_accounts_job(context):
    """🗑️ Auto-delete sold accounts older than 2 months (runs daily)."""
    try:
        from database import purge_expired_sold_accounts
        deleted = purge_expired_sold_accounts(60)
        if deleted:
            import logging
            logging.getLogger(__name__).info(f"[SoldPurge] Deleted {deleted} expired sold accounts")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[SoldPurge] {e}")


async def _sale_notification_job(context):
    """🆕 v73: Supplier sale notification job DEPRECATED. No-op kept for safety."""
    return


async def _stock_expiry_job(context):
    """🆕 v73: Supplier stock expiry job DEPRECATED. No-op kept for safety."""
    return


async def _auto_refund_job(context):
    """🆕 v73: Supplier auto-refund job DEPRECATED. No-op kept for safety."""
    return
    # Unused stub below — kept commented out for historical reference.

async def catch_all_callback(update, context):
    try:
        await update.callback_query.answer("⚠️ Session expired or action unavailable. Type /start", show_alert=True)
    except:
        pass


async def unhandled_cbq_fallback(update, context):
    try:
        await update.callback_query.answer("⚠️ Please cancel the current process first (send /cancel or tap Cancel)", show_alert=True)
    except:
        pass
    return

async def handle_media_router(update, context):
    """Route admin media to broadcast/static-delivery flows before payment screenshot handler."""
    # 🐛 v147 FIX (Bug4): groups — never process/respond to media in groups.
    if _is_group_chat(update):
        return
    try:
        if update.effective_user and update.effective_user.id == ADMIN_ID:
            if context.user_data.get('broadcasting'):
                await handle_broadcast_message(update, context); return
            if context.user_data.get('fake_custom_broadcast'):
                if await handle_fake_custom_broadcast_message(update, context): return
            if context.user_data.get('edit_field') == 'deliverytext' and context.user_data.get('edit_pid'):
                if await handle_static_delivery_media_message(update, context): return
    except Exception as e:
        logging.getLogger(__name__).warning(f"[media_router] admin media route failed: {e}")
    # Fallback to existing payment screenshot/document handler
    await handle_screenshot(update, context)

# ════════════════════════════════════════════
# 🆕 v134: REFERRAL ACTIVITY OBSERVATION HOOKS
# Runs BEFORE every other handler (group -100). Counts the referred user's
# real actions (button taps / typed text) — after 2+ actions the pending
# referral reward unlocks (real-human signal). Never raises; never blocks.
# ════════════════════════════════════════════

async def _activity_hook_callback(update, context):
    # 🆕 v135: global force-join gate for EXISTING users — any button tap is
    # blocked until they (re)join all targets and verify.
    try:
        from ui_extras import force_join_action_gate
        if await force_join_action_gate(update, context):
            raise ApplicationHandlerStop
    except ApplicationHandlerStop:
        raise
    except Exception:
        pass
    try:
        from handlers_start import notify_user_activity
        await notify_user_activity(context, update.effective_user.id)
    except Exception:
        pass
    return None  # continue to the real handler


async def _activity_hook_text(update, context):
    # 🐛 v147 FIX (Bug4): groups — bot never reacts to any user message.
    if _is_group_chat(update):
        return None
    # 🆕 v135: global force-join gate for EXISTING users — any text action is
    # blocked until they (re)join all targets and verify.
    try:
        from ui_extras import force_join_action_gate
        if await force_join_action_gate(update, context):
            raise ApplicationHandlerStop
    except ApplicationHandlerStop:
        raise
    except Exception:
        pass
    try:
        from handlers_start import notify_user_activity
        await notify_user_activity(context, update.effective_user.id)
    except Exception:
        pass
    return None  # continue to the real handler


def _patch_ptb_poll_parsing():
    """🐛 v153 FIX: PTB 22.8 (Bot API 9.6) REQUIRES fields that real Telegram
    poll updates sometimes omit (PollAnswer.option_persistent_ids,
    PollOption.persistent_id, Poll.allows_revoting). When missing, PTB raises
    TypeError while parsing the update → every user vote logged an error and
    the vote was NEVER recorded (no live results). This patch makes those
    fields default to safe values so parsing never crashes."""
    try:
        import telegram as _tg

        try:
            _orig_pa = _tg.PollAnswer.__init__
            def _pa_init(self, *a, **kw):
                if kw.get("option_persistent_ids") is None:
                    kw["option_persistent_ids"] = ()
                return _orig_pa(self, *a, **kw)
            _tg.PollAnswer.__init__ = _pa_init
        except Exception:
            pass

        try:
            _orig_po = _tg.PollOption.__init__
            def _po_init(self, *a, **kw):
                if kw.get("persistent_id") is None:
                    kw["persistent_id"] = ""
                return _orig_po(self, *a, **kw)
            _tg.PollOption.__init__ = _po_init
        except Exception:
            pass

        try:
            _orig_p = _tg.Poll.__init__
            def _p_init(self, *a, **kw):
                if kw.get("allows_revoting") is None:
                    kw["allows_revoting"] = False
                if kw.get("members_only") is None:
                    kw["members_only"] = False
                return _orig_p(self, *a, **kw)
            _tg.Poll.__init__ = _p_init
        except Exception:
            pass
        print("[PollPatch] PTB poll parsing tolerance installed")
    except Exception as e:
        print(f"[PollPatch] not installed: {e}")


async def _reseller_pending_reminder_job(context):
    """🆕 v161.3: remind admin about pending/processing reseller orders (30+ min)."""
    try:
        from database import get_connection, get_setting
        conn = get_connection(); c = conn.cursor()
        try:
            c.execute("""SELECT id, product_name, qty, usd_amount, created_at, status
                         FROM reseller_orders
                         WHERE status IN ('pending','processing')
                           AND datetime(created_at) <= datetime('now','-30 minutes')
                         ORDER BY id DESC LIMIT 10""")
            rows = [dict(r) for r in c.fetchall()]
        except Exception:
            rows = []
        finally:
            try: conn.close()
            except Exception: pass
        if not rows:
            return
        noted = set(context.bot_data.get("rs_pending_notified", []))
        fresh = [r for r in rows if int(r.get("id") or 0) not in noted]
        if not fresh:
            return
        lines = ["⏳ *Reseller orders pending manual delivery (30+ min):*\n"]
        for r in fresh[:6]:
            lines.append(f"• #{r['id']} · {str(r.get('product_name'))[:22]} ×{r.get('qty')} · {r.get('status')}")
        if len(fresh) > 6:
            lines.append(f"… +{len(fresh)-6} more")
        try:
            await context.bot.send_message(int(os.getenv("ADMIN_ID", "0") or 0),
                                           "\n".join(lines), parse_mode="Markdown")
        except Exception:
            pass
        context.bot_data["rs_pending_notified"] = list(noted | {int(r.get("id")) for r in fresh})[-100:]
    except Exception:
        pass


async def _cmd_help(update, context):
    """📚 How to Use — blue menu button command."""
    try:
        from ui_extras import how_to_hub_from_text
        await how_to_hub_from_text(update, context)
    except Exception as e:
        logging.getLogger(__name__).debug(f"[cmd help] {e}")


async def _cmd_apikey(update, context):
    """🔗 Reseller API Key — blue menu button command."""
    try:
        from handlers_admin import reseller_api_from_text
        await reseller_api_from_text(update, context)
    except Exception as e:
        logging.getLogger(__name__).debug(f"[cmd apikey] {e}")


async def _cmd_ban(update, context):
    """🚫 v170.35: admin command — global user ban.
    Usage: /ban <user_id> [reason]
    Also accepts a reply to a forwarded message from that user."""
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args or []
    uid = None
    reason = ""
    try:
        # reply-to-forward: take the forwarded user's id
        if update.message.reply_to_message:
            fwd = update.message.reply_to_message
            if getattr(fwd, "forward_from", None):
                uid = fwd.forward_from.id
            elif getattr(fwd, "from_user", None):
                uid = fwd.from_user.id
            reason = " ".join(args) if args else ""
        if uid is None and args:
            try:
                uid = int(str(args[0]).lstrip("@"))
                reason = " ".join(args[1:])
            except Exception:
                uid = None
    except Exception:
        uid = None
    if uid is None:
        await update.message.reply_text(
            "❌ *Usage:* `/ban <user_id> [reason]`\n"
            "Ya kisi forwarded message par reply karke `/ban` bhejo.",
            parse_mode="Markdown")
        return
    if uid == ADMIN_ID:
        await update.message.reply_text("❌ Apne aap ko ban nahi kar sakte.")
        return
    from database import ban_user, get_user
    try:
        u = get_user(uid)
        uname = f"@{u['username']}" if u and u.get("username") else ""
        fname = (u.get("first_name") or "") if u else ""
    except Exception:
        uname, fname = "", ""
    ok = ban_user(uid, reason)
    who = " ".join(x for x in (fname, uname) if x) or str(uid)
    await update.message.reply_text(
        f"🚫 *Banned!*\n"
        f"👤 {who} (`{uid}`)\n"
        f"📝 Reason: {reason or '—'}\n\n"
        f"_Ab ye user bot use nahi kar sakta (orders/freebies/deposit sab block)._",
        parse_mode="Markdown")


async def _cmd_unban(update, context):
    """🔓 v170.35: admin command — global user unban. Usage: /unban <user_id>"""
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args or []
    try:
        uid = int(str(args[0]).lstrip("@")) if args else None
    except Exception:
        uid = None
    if uid is None:
        await update.message.reply_text("❌ *Usage:* `/unban <user_id>`",
                                        parse_mode="Markdown")
        return
    from database import unban_user, is_user_banned
    ok = unban_user(uid)
    await update.message.reply_text(
        f"🔓 *Unbanned* `{uid}` — ab ye user dobara bot use kar sakta hai." if ok
        else f"⚠️ User `{uid}` ban list me nahi tha.",
        parse_mode="Markdown")


async def _cmd_freebies(update, context):
    """🎁 Freebies — blue menu button command."""
    try:
        from handlers_freebies import freebies_from_text
        await freebies_from_text(update, context)
    except Exception as e:
        logging.getLogger(__name__).debug(f"[cmd freebies] {e}")


async def _cmd_support(update, context):
    """🎫 Support & Contact — blue menu button command."""
    try:
        from handlers_support import get_user_tickets
        from database import get_response_with_auto_register
        from config import DEFAULT_RESPONSES, WHATSAPP_NUMBER
        uid = update.effective_user.id
        tickets = get_user_tickets(uid)
        open_count = sum(1 for t in tickets if t.get("status") in ("open", "in_progress"))
        try:
            text = get_response_with_auto_register(
                "support_menu_header",
                DEFAULT_RESPONSES.get("support_menu_header", "")).format(
                whatsapp=WHATSAPP_NUMBER, total=len(tickets), open=open_count)
        except Exception:
            text = (f"🎫 *Support Center*\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Need help? Create a support ticket!\n"
                    f"📞 *WhatsApp Support:* `+{WHATSAPP_NUMBER}`\n\n"
                    f"📋 *Your Tickets:* {len(tickets)} total\n"
                    f"🟡 *Open:* {open_count}\n\nChoose an option:")
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎫 New Ticket", callback_data="st_new")],
            [InlineKeyboardButton("📋 My Tickets", callback_data="st_list")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
        ])
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        logging.getLogger(__name__).debug(f"[cmd support] {e}")

def main():
    print("=" * 50)
    print("🤖 BITE STORE")
    print("=" * 50)
    # Fail fast with a clear message instead of silently using leaked/default secrets.
    validate_required_config()
    # 🐛 v153: PTB poll parsing tolerance (must run before app starts polling)
    try:
        _patch_ptb_poll_parsing()
    except Exception as _pe:
        print(f"[PollPatch] error: {_pe}")
    # 🆕 v151: bot boots FRESH — no bundled DB. The admin restores their own
    # database via Admin → 💾 Backup & Restore whenever they want.
    _apply_startup_maintenance()
    setup_database()
    # 🛡️ v51: Install GLOBAL premium-emoji rendering guard BEFORE any Bot
    # instance is created. Patches telegram.Bot / Message / CallbackQuery so
    # EVERY outgoing text auto-applies smart_text_and_mode() — even from
    # legacy code paths that forget to call it manually. Bulletproof safety
    # net so admin's premium-emoji edits never leak as raw [[HTML]] / <tg-emoji>.
    try:
        from premium_emoji_guard import install as install_premium_guard
        install_premium_guard()
    except Exception as _e:
        print(f"⚠️ premium_emoji_guard install failed: {_e}")
    # 🆕 v43: Full schema self-heal — runs every migration so that even if
    # admin replaced shop.db file manually with an older backup, missing
    # columns/tables get added automatically and buttons don't stay stuck.
    try:
        from database import migrate_all
        migrate_all()
    except Exception as _me:
        print(f"⚠️ migrate_all() at startup failed: {_me}")

    # 🌐 v26: Use proxy for Telegram connection if set in .env
    if TELEGRAM_PROXY:
        print(f"🌐 Using Telegram proxy: {TELEGRAM_PROXY[:40]}...")
        request = HTTPXRequest(proxy=TELEGRAM_PROXY, connect_timeout=30, read_timeout=30)
        get_updates_request = HTTPXRequest(proxy=TELEGRAM_PROXY, connect_timeout=30, read_timeout=30)
        app = (Application.builder()
                          .token(BOT_TOKEN)
                          .request(request)
                          .get_updates_request(get_updates_request)
                          .post_init(post_init)
                          .build())
    else:
        app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_error_handler(global_error_handler)

    # ── 🆕 v134: Referral activity observation (runs before all others) ──
    app.add_handler(CallbackQueryHandler(_activity_hook_callback), group=-100)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _activity_hook_text), group=-100)
    # 🆕 v170.2: instant force-join leave detection — jab koi user kisi target
    # chat se leave/join kare to membership cache turant invalidate hoti hai.
    try:
        from ui_extras import fj_chat_member_handler
        app.add_handler(ChatMemberHandler(
            fj_chat_member_handler,
            chat_member_types=ChatMemberHandler.ANY_CHAT_MEMBER), group=-100)
    except Exception as _fe:
        print(f"[ForceJoin] chat_member handler register failed: {_fe}")

    # ── Conversations ──
    # 1. Add Category
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(add_category_callback, pattern="^add_category$")],
        states={
            CAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cat_name_received)],
            CAT_EMOJI: [CommandHandler("skip", cat_emoji_skip),
                        MessageHandler(filters.TEXT & ~filters.COMMAND, cat_emoji_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # 2. Add Product (10 steps including photo, warranty, quantity)
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(add_product_callback, pattern="^add_product$")],
        states={
            PROD_CAT: [CallbackQueryHandler(select_category_for_product, pattern="^selcat_")],
            PROD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_name_received),
                        CallbackQueryHandler(prod_back_callback, pattern="^prodback_")],
            PROD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_desc_received),
                        CallbackQueryHandler(prod_back_callback, pattern="^prodback_")],
            PROD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_price_received),
                         CallbackQueryHandler(prod_back_callback, pattern="^prodback_")],
            PROD_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_cost_received),
                        CallbackQueryHandler(prod_back_callback, pattern="^prodback_")],
            PROD_STOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_stock_received),
                         CallbackQueryHandler(prod_back_callback, pattern="^prodback_")],
            PROD_WARRANTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_warranty_received),
                            CallbackQueryHandler(prod_warranty_callback, pattern="^pwar_"),
                            CallbackQueryHandler(prod_skip_callback, pattern="^prodskip_"),
                            CallbackQueryHandler(prod_back_callback, pattern="^prodback_")],
            PROD_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_quantity_received),
                            CallbackQueryHandler(prod_skip_callback, pattern="^prodskip_"),
                            CallbackQueryHandler(prod_back_callback, pattern="^prodback_")],
            PROD_PHOTO: [
                # PROD_PHOTO state now handles delivery mode callback (no photo asked)
                CallbackQueryHandler(delivery_mode_callback, pattern="^dmode_"),
            ],
            PROD_DELIVERY_TEXT: [
                MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.VIDEO | filters.Document.ALL, prod_delivery_received),
                CallbackQueryHandler(prod_skip_callback, pattern="^prodskip_"),
                CallbackQueryHandler(prod_back_callback, pattern="^prodback_"),
                CallbackQueryHandler(pdm_callback, pattern="^pdm_"),
                CallbackQueryHandler(pfmt_callback, pattern="^pfmt_"),
                CallbackQueryHandler(pfb_freebie_callback, pattern="^pfb_"),
                CallbackQueryHandler(pmt_callback, pattern="^pmt_"),
                CallbackQueryHandler(pmail_callback, pattern="^pmail_"),
                CallbackQueryHandler(ppass_callback, pattern="^ppass_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # 3. Settings Edit
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(set_setting_callback, pattern="^set_")],
        states={SET_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_value_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # 3b. 🆕 v170.37: Ban / Unban user input (admin panel buttons)
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=300,
        entry_points=[
            CallbackQueryHandler(ban_input_start, pattern="^ban_input$"),
            CallbackQueryHandler(unban_input_start, pattern="^unban_input$"),
        ],
        states={
            BAN_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_input_received)],
            UNBAN_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, unban_input_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # 4. Edit Responses  (🆕 v170.22: + 2 readymade templates, custom, reset, real cancel)
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(edit_response_callback, pattern="^editresp_")],
        states={EDIT_RESP_VALUE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, response_value_received),
            CallbackQueryHandler(resp_template_apply_callback, pattern="^resptpl_"),
            CallbackQueryHandler(resp_custom_callback, pattern="^respcustom_"),
            CallbackQueryHandler(resp_reset_callback, pattern="^respreset_"),
        ]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # 5. 🆕 Rename Button (Manage Buttons)
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(rename_button_callback, pattern="^mbrenm_")],
        states={MB_RENAME_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, rename_button_value_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # 5b. 🆕 Custom whole-screen padding number
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900,
        entry_points=[CallbackQueryHandler(group_screen_pad_custom_start_callback, pattern="^mbscrpadcustom_")],
        states={MB_SCREEN_PAD_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, group_screen_pad_custom_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # 6. 🆕 v38: New Custom Button (type → label → action → location)
    # Now supports 17+ action types including file uploads (photo, video, doc, audio)
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(cb_type_callback, pattern="^cbtype_")],
        states={
            CB_NEW_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, cb_new_label_received)],
            CB_NEW_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cb_new_action_received),
                MessageHandler(filters.PHOTO, cb_new_action_received),
                MessageHandler(filters.VIDEO, cb_new_action_received),
                MessageHandler(filters.Document.ALL, cb_new_action_received),
                MessageHandler(filters.AUDIO | filters.VOICE, cb_new_action_received),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # 7. 🆕 v38: Edit existing custom button (label or action) — supports file uploads
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[
            CallbackQueryHandler(cb_edit_label_callback, pattern="^cbedit_label_"),
            CallbackQueryHandler(cb_edit_action_callback, pattern="^cbedit_action_"),
        ],
        states={CB_EDIT_VALUE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, cb_edit_value_received),
            MessageHandler(filters.PHOTO, cb_edit_value_received),
            MessageHandler(filters.VIDEO, cb_edit_value_received),
            MessageHandler(filters.Document.ALL, cb_edit_value_received),
            MessageHandler(filters.AUDIO | filters.VOICE, cb_edit_value_received),
        ]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # 8. 🆕 Phase D: New Custom Page (title → content → photo)
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(cp_new_callback, pattern="^cpnew$")],
        states={
            CP_NEW_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cp_new_title_received)],
            CP_NEW_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cp_new_content_received)],
            CP_NEW_PHOTO: [MessageHandler(filters.PHOTO | filters.Document.ALL | (filters.TEXT & ~filters.COMMAND), cp_new_photo_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # 9. 🆕 Phase D: Edit page title/content
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[
            CallbackQueryHandler(cp_edit_title_callback, pattern="^cpedit_title_"),
            CallbackQueryHandler(cp_edit_content_callback, pattern="^cpedit_content_"),
        ],
        states={CP_EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cp_edit_value_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # 10. 🆕 Phase D: Edit page photo
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(cp_edit_photo_callback, pattern="^cpedit_photo_")],
        states={CP_EDIT_PHOTO: [MessageHandler(filters.PHOTO | filters.Document.ALL | (filters.TEXT & ~filters.COMMAND), cp_edit_photo_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(adm_manage_pts_callback, pattern="^adm_manage_pts$")],
        states={
            901: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_pts_uid_received)],
            902: [
                CallbackQueryHandler(adm_pts_mode_callback, pattern="^adm_pts_mode_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, adm_pts_amt_received),
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")]
    ))
    # 🆕 v65: Central click logger — runs BEFORE all other handlers (group=-100)
    # Tracks every callback button press + /command so admin can see per-user activity.
    from telegram.ext import TypeHandler
    from telegram import Update as _Upd

    async def _click_logger(update, context):
        try:
            from user_tracking import log_click
            uid = None; action = None
            if update.callback_query:
                uid = update.callback_query.from_user.id
                action = update.callback_query.data or ""
            elif update.message:
                u = update.effective_user
                if u: uid = u.id
                # Only log /commands here (regular text is logged differently if needed)
                txt = (update.message.text or "")
                if txt.startswith("/"):
                    action = txt.split()[0][:30]  # /start, /admin, etc.
            if uid and action:
                log_click(uid, action)
        except Exception:
            pass
        # Important: do NOT raise — let the actual handler chain run
    app.add_handler(TypeHandler(_Upd, _click_logger), group=-100)

    # 🆕 v84: MAINTENANCE MODE GATE — runs at group=-90 (before all normal handlers,
    # after click logger). When maintenance is ON, every non-admin update gets
    # the maintenance reply and downstream handlers are skipped. Admin bypasses.
    app.add_handler(TypeHandler(_Upd, maintenance_gate), group=-90)

    # 🆕 v76: UNIVERSAL MAIN MENU FORCE-EXIT — runs BEFORE every ConversationHandler.
    # When user taps any 🏠 / Main Menu button, all active sessions are wiped and
    # the main menu is shown — no matter what step they're stuck in.
    app.add_handler(CallbackQueryHandler(force_main_menu_callback,
                                         pattern=r"^main_menu$"),
                    group=-50)
    app.add_handler(MessageHandler(filters.Regex(r"^🏠 Main Menu$"),
                                   force_main_menu_text_callback),
                    group=-49)

    # 🆕 v84: Conversation — admin sets custom maintenance text
    from telegram.ext import ConversationHandler as _CH
    app.add_handler(_CH(
        entry_points=[CallbackQueryHandler(maint_edit_custom_entry,
                                            pattern=r"^maint_edit_custom$")],
        states={
            MAINT_CUSTOM_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, maint_custom_received),
            ],
        },
        fallbacks=[CommandHandler("cancel", maint_custom_cancel)],
        per_message=False, allow_reentry=True, conversation_timeout=900,
    ), group=0)

    # 🆕 v84: Conversation — admin searches users on Completed Orders v2
    app.add_handler(_CH(
        entry_points=[CallbackQueryHandler(ac2_search_entry,
                                            pattern=r"^ac2_search$")],
        states={
            AC2_SEARCH_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ac2_search_received),
            ],
        },
        fallbacks=[CommandHandler("cancel", ac2_search_cancel)],
        per_message=False, allow_reentry=True, conversation_timeout=900,
    ), group=0)

    # 🆕 v85: Conversation — admin edits low-bal threshold per supplier
    app.add_handler(_CH(
        entry_points=[CallbackQueryHandler(ext_sup_lowbal_callback,
                                            pattern=r"^ext_sup_lowbal_")],
        states={
            LOWBAL_EDIT_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                                ext_sup_lowbal_received),
            ],
        },
        fallbacks=[CommandHandler("cancel", ext_sup_lowbal_cancel)],
        per_message=False, allow_reentry=True, conversation_timeout=900,
    ), group=0)

    # 🆕 v96: Conversation — admin renames a supplier (admin dashboard only)
    app.add_handler(_CH(
        entry_points=[CallbackQueryHandler(ext_sup_rename_callback,
                                            pattern=r"^ext_sup_rename_")],
        states={
            SUP_RENAME_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                                ext_sup_rename_received),
            ],
        },
        fallbacks=[CommandHandler("cancel", ext_sup_rename_cancel)],
        per_message=False, allow_reentry=True, conversation_timeout=900,
    ), group=0)

    # 🆕 v86: Conversation — admin adds InstaAPI supplier via connection string
    app.add_handler(_CH(
        entry_points=[CallbackQueryHandler(ext_sup_add_conn_callback,
                                            pattern=r"^ext_sup_add_conn$")],
        states={
            CONN_STRING_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                                ext_sup_add_conn_received),
            ],
        },
        fallbacks=[CommandHandler("cancel", ext_sup_add_conn_cancel)],
        per_message=False, allow_reentry=True, conversation_timeout=900,
    ), group=0)

    # 🆕 v95: Conversation — admin adds new custom Location (auto-syncs everywhere)
    app.add_handler(_CH(
        entry_points=[CallbackQueryHandler(lc_add_custom_start,
                                            pattern=r"^lc_add_custom$")],
        states={
            LC_ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                          lc_add_id_received)],
            LC_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                            lc_add_name_received)],
            LC_ADD_HEADER: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                              lc_add_header_received)],
        },
        fallbacks=[CommandHandler("cancel", lc_add_cancel)],
        per_message=False, allow_reentry=True, conversation_timeout=900,
    ), group=0)

    app.add_handler(CommandHandler("start", start_command), group=-49)
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("resetbot", resetbot_command))
    app.add_handler(CommandHandler("deliver", deliver_command))
    # 🆕 v170.35: global user ban / unban (scam protection)
    app.add_handler(CommandHandler("ban", _cmd_ban))
    app.add_handler(CommandHandler("unban", _cmd_unban))

    # 🆕 v161.4: reseller system is BUTTON-DRIVEN (no commands).
    # User: main-menu "🔗 Reseller API Key" button → ProdSeller-style panel.
    # Admin: Admin panel → "🔗 Reseller API" → full management panel.
    app.add_handler(MessageHandler(filters.TEXT, reseller_wizard_text), group=-50)

    # 🆕 v75: /api command REMOVED (Worker deployment, no REST endpoints).

    # 🆕 v44: Premium-button-icon diagnostic command
    # 🆕 v45: now also includes product names + registry buttons + custom buttons
    async def _diagbtn_command(update, context):
        from config import ADMIN_ID
        if update.effective_user.id != ADMIN_ID:
            return
        try:
            from button_system import (
                diagnose_send, TEMPLATE_BUTTONS, get_button_text,
                get_button_emoji_id, build_button, extract_emoji_from_html,
                make_premium_button,
            )
            import json as _json
            d = diagnose_send(context.bot)

            # Section 1: template-button overrides
            saved_tpl = []
            for tpl_id in TEMPLATE_BUTTONS:
                eid = get_button_emoji_id(tpl_id)
                txt = get_button_text(tpl_id)
                if eid or TEMPLATE_BUTTONS[tpl_id]:
                    mark = "⭐" if eid else "▫️"
                    saved_tpl.append(f"{mark} `{tpl_id}` → `{txt[:20]}`"
                                     + (f" icon=`{eid[:18]}…`" if eid else ""))

            # Section 2: products with premium emoji in name
            products_with_premium = []
            try:
                from database import get_all_active_products
                for p in get_all_active_products():
                    raw = p['name'] or ''
                    eid, plain = extract_emoji_from_html(raw)
                    if eid:
                        products_with_premium.append(
                            f"⭐ #{p['id']} `{plain[:25]}` icon=`{eid[:18]}…`"
                        )
            except Exception:
                pass

            # Section 3: registry buttons with premium emoji custom labels
            reg_with_premium = []
            try:
                from button_system import BUTTONS
                from database import get_setting
                for bid in BUTTONS:
                    for sz in ("short", "medium", "large", "xl"):
                        v = get_setting(f"btn_label_{bid}_{sz}", "")
                        if v and ("[[HTML]]" in v or "<tg-emoji" in v.lower()):
                            eid, plain = extract_emoji_from_html(v)
                            if eid:
                                reg_with_premium.append(
                                    f"⭐ `{bid}.{sz}` → `{plain[:20]}` icon=`{eid[:18]}…`"
                                )
            except Exception:
                pass

            # Section 4: custom buttons with premium emoji
            custom_with_premium = []
            try:
                from database import get_all_custom_buttons
                for b in get_all_custom_buttons():
                    lbl = b['label'] or ''
                    if "[[HTML]]" in lbl or "<tg-emoji" in lbl.lower():
                        eid, plain = extract_emoji_from_html(lbl)
                        if eid:
                            custom_with_premium.append(
                                f"⭐ #{b['id']} `{plain[:20]}` icon=`{eid[:18]}…`"
                            )
            except Exception:
                pass

            # Sample JSON
            sample_tpl = next((t for t in TEMPLATE_BUTTONS
                               if get_button_emoji_id(t)), "bc_purchase")
            sample = build_button(sample_tpl, "🛒 Buy Now", callback_data="x")
            sample_json = _json.dumps(sample.to_dict(), ensure_ascii=False, indent=2)

            try:
                me = await context.bot.get_me()
                bot_name = f"@{me.username} (id={me.id})"
            except Exception:
                bot_name = "?"

            def _list_or_none(items):
                return "\n".join(items) if items else "_(none)_"

            msg = (
                "🔧 *Premium Button Icon Diagnostic v45*\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🤖 *Bot:* `{bot_name}`\n"
                f"📦 *PTB version:* `{d['ptb_version']}`\n"
                f"⚙️ *Native icon kwarg:* `{d['ptb_native_support']}`\n"
                f"✅ *Ready to send icons:* `{d['ready']}`\n\n"
                f"*📝 Template button overrides:*\n{_list_or_none(saved_tpl)}\n\n"
                f"*📦 Products with premium emoji name:*\n{_list_or_none(products_with_premium)}\n\n"
                f"*🏠 Registry buttons (admin-renamed with premium):*\n{_list_or_none(reg_with_premium)}\n\n"
                f"*🎨 Custom buttons with premium:*\n{_list_or_none(custom_with_premium)}\n\n"
                f"*Sample JSON for `{sample_tpl}`:*\n```json\n{sample_json}\n```\n\n"
                "_Agar JSON me `icon_custom_emoji_id` present hai but icon_\n"
                "_phir bhi nahi dikhta to Telegram side ki shartein check karein:_\n"
                "1. Bot OWNER ke account par Telegram Premium *active*?\n"
                "2. Chat private/group/supergroup hai (NOT channel)?\n"
                "3. Telegram app latest update hai (>= Feb 2026)?\n"
                "4. Wo custom_emoji_id valid (sticker pack delete to nahi)?"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Diag failed: {e}")
    app.add_handler(CommandHandler("diagbtn", _diagbtn_command))

    # ── 🆕 v170.19: BLUE MENU BUTTON commands (bot command menu) ──
    try:
        from handlers_start import (handle_shop_button, handle_balance_button,
                                    handle_deposit_button, handle_history_button,
                                    handle_language_button)
        app.add_handler(CommandHandler("shop", handle_shop_button))
        app.add_handler(CommandHandler("balance", handle_balance_button))
        app.add_handler(CommandHandler("deposit", handle_deposit_button))
        app.add_handler(CommandHandler("orders", handle_history_button))
        app.add_handler(CommandHandler("language", handle_language_button))
        app.add_handler(CommandHandler("help", _cmd_help))
        app.add_handler(CommandHandler("apikey", _cmd_apikey))
        app.add_handler(CommandHandler("freebies", _cmd_freebies))
        app.add_handler(CommandHandler("support", _cmd_support))
    except Exception as _ce:
        print(f"[Commands] register failed: {_ce}")

    # ── Callback handlers ──
    for pat, fn in [
        ("^main_menu$", main_menu_callback), ("^my_account$", my_account_callback),
        ("^referral$", referral_callback),  # 🔧 support_callback removed
        ("^buy_points$", buy_points_callback), ("^transactions$", transactions_callback),
        ("^shop$", shop_callback), ("^favorites$", favorites_callback), ("^fav_toggle_", favorite_toggle_callback),
        ("^page_", page_callback), ("^prod_", product_detail_callback),
        # 🆕 v69: Price List screen + sort filters
        ("^price_list$",       price_list_callback),
        ("^price_list_",       price_list_callback),
        # 🆕 v70: Share Product Link + QR
        ("^sharep_",           share_product_callback),
        ("^shareqr_",          share_qr_callback),
        # 🆕 v70: Pinned Announcements admin
        ("^admin_pins$",                admin_pins_callback),
        ("^admin_pins_add$",            admin_pins_add_callback),
        ("^admin_pin_cancel_add$",      admin_pin_cancel_add_callback),
        ("^admin_pin_exp_",             admin_pin_expiry_callback),
        ("^admin_pin_del_",             admin_pin_del_callback),
        ("^admin_pin_toggle_",          admin_pin_toggle_callback),
        # 🆕 v101: real-pin-mode toggle + manual broadcast push
        ("^admin_pin_realmode_toggle$", admin_pin_realmode_toggle_callback),
        ("^admin_pin_push_",            admin_pin_push_callback),
        ("^admin_pin_unpush_",          admin_pin_unpush_callback),
        # 🆕 v79: Pin templates
        ("^admin_pins_templates$",      admin_pins_templates_callback),
        ("^admin_pin_tpl_",             admin_pin_use_template_callback),
        # 🆕 v71: AI Support Auto-Reply admin
        ("^admin_ai_support$",          admin_ai_support_callback),
        ("^admin_ai_support_toggle$",   admin_ai_support_toggle_callback),
        ("^admin_ai_support_log$",      admin_ai_support_log_callback),
        # 🆕 v71: User escalate / mark-resolved after AI reply
        ("^st_escalate_",               st_escalate_callback),
        ("^st_resolved_user_",          st_resolved_user_callback),
        # 🆕 v71: Replacement system — user side
        ("^reprep_",                    user_replace_start_callback),
        ("^reprsn_",                    user_replace_reason_callback),
        # 🆕 v71: Replacement system — admin side
        ("^adm_repap_",                 admin_replace_approve_callback),
        ("^adm_repx_api_",              admin_replace_api_callback),
        ("^adm_repx_up_",               admin_replace_upload_callback),
        ("^adm_repx_stock_",            admin_replace_stock_callback),
        ("^adm_reprj_do_",              admin_replace_reject_do_callback),
        ("^adm_reprj_cancel_",          admin_replace_reject_cancel_callback),
        ("^adm_reprj_",                 admin_replace_reject_callback),
        # 🆕 v71: Per-product replacement window — apply set
        # (the picker callback is registered earlier, near ^editfield_)
        ("^repwin_set_",                admin_repwin_set_callback),
        # 🆕 v72: Delivery integrity dashboard
        ("^admin_integrity$",           admin_integrity_callback),
        ("^admin_integrity_bad$",       admin_integrity_bad_callback),
        # 🆕 v59: Stock-based shop filter (All / Available / Unavailable)
        ("^shopfilter_", shop_filter_callback),
        # Specific payment submenus MUST come before generic ^pay_binance_/^pay_bybit_
        ("^pay_binance_menu_", payment_binance_menu_callback),
        ("^pay_bybit_menu_", payment_bybit_menu_callback),
        ("^pay_usdt_", payment_usdt_callback),
        ("^pay_bybit_", payment_bybit_callback),
        ("^usdtv_", usdt_verify_callback),
        ("^bybitv_", bybit_verify_callback),
        ("^bybit_manual_confirm_", bybit_manual_confirm_callback),
                # ⭐ v161.25: Telegram Stars payment
        ("^ptspay_stars_",                 points_stars_callback),
        ("^pay_stars_",                    product_stars_callback),
        ("^stars_pay_",                    stars_pay_callback),
("^bybit_flow_continue$", bybit_flow_continue_callback),
        ("^bybit_flow_cancel$", bybit_flow_cancel_callback),
        ("^buy_", buy_callback), ("^pay_binance_", payment_binance_callback),
        ("^pay_easy_", payment_easypaisa_callback), ("^pay_jazz_", payment_jazzcash_callback),
        # 🆕 Buy Multiple (bulk)
        ("^buyx_", buy_multiple_callback),
        # 🆕 v31: Binance Verify Payment button (Gemini screenshot analysis)
        ("^vpay_", verify_screenshot_callback),
        ("^reupload_", reupload_screenshot_callback),
        # 🆕 v62: Binance Order-ID flow — Check Again button
        ("^vpoid_", verify_order_id_callback),
        # 🆕 v32: JazzCash Verify Payment (same AI flow)
        ("^jcv_", jc_verify_callback),
        ("^jcreupload_", jc_reupload_callback),
        # 🆕 v25: Verify EasyPaisa Payment
        ("^epv_", ep_verify_callback),
        # 🆕 v12: Cancel pending order/deposit
        ("^cancel_order$", cancel_pending_order_callback),
        # 🆕 v16: AI Admin Assistant
        ("^admin_ai$", admin_ai_callback),
        ("^ai_exit$", ai_exit_callback),
        ("^ai_clear$", ai_clear_callback),
        # 🆕 v21: Reset & Undo
        ("^admin_reset_undo$", admin_reset_undo_callback),
        ("^undo_view$", undo_view_callback),
        ("^undo_one$", undo_one_callback),
        ("^undo_clear$", undo_clear_callback),
        ("^reset_confirm$", reset_confirm_callback),
        ("^reset_do$", reset_do_callback),
        # 🆕 v22: Backup & Restore
        ("^admin_backup$", admin_backup_callback),
        ("^bk_download$", backup_download_callback),
        ("^bk_cloud_now$", backup_cloud_now_callback),
        ("^bk_restore_start$", backup_restore_start_callback),
        ("^bk_reset_start$", backup_reset_start_callback),
        ("^bk_reset_do$", backup_reset_do_callback),
        ("^bk_reset_cancel$", backup_reset_cancel_callback),
        ("^bk_cancel_restore$", backup_cancel_restore_callback),
        ("^bk_restore_do$", backup_restore_do_callback),
        ("^bk_restore_cancel_file$", backup_restore_cancel_file_callback),
        ("^bk_list_auto$", backup_list_auto_callback),
        # 🆕 v24: Binance API test
        ("^admin_test_binance$", admin_test_binance_api_callback),
        # 🆕 v25: EasyPaisa Email test
        ("^admin_test_email$", admin_test_email_callback),
        # 🆕 Binance Gmail test
        ("^admin_test_binance_gmail$", admin_test_binance_gmail_callback),
        # 🆕 v61: Binance Pay REST API (direct, with Pakistani proxy)
        ("^admin_binance_api$",        admin_binance_api_panel_callback),
        ("^admin_binance_api_toggle$", admin_binance_api_toggle_callback),
        ("^admin_binance_api_test$",   admin_binance_api_test_callback),
        ("^admin_binance_api_list$",   admin_binance_api_list_callback),
        # 🆕 v63: Proxy pool rotation panel
        ("^admin_binance_proxies$",    admin_binance_proxies_callback),
        ("^admin_proxy_add$",          admin_proxy_add_callback),
        ("^admin_proxy_del_",          admin_proxy_del_callback),
        ("^admin_proxy_test_all$",     admin_proxy_test_all_callback),
        ("^admin_proxy_reset$",        admin_proxy_reset_callback),
        # 🆕 v67: AI Proxy Scout — Gemini auto-finds new PK proxies
        ("^admin_proxy_ai_scout$",     admin_proxy_ai_scout_callback),
        # 🆕 v65: Refund + Cancel order flow (specific suffixes first!)
        ("^adm_refund_confirm_",       adm_refund_confirm_callback),
        ("^adm_refund_abort_",         adm_refund_abort_callback),
        ("^adm_refund_",               adm_refund_callback),
        ("^adm_cancel_skip_",          adm_cancel_skip_callback),
        ("^adm_cancel_abort_",         adm_cancel_abort_callback),
        ("^adm_cancel_",               adm_cancel_callback),
        # 🆕 v65: User pagination + per-user activity viewer
        ("^admin_users_p",             admin_users_callback),
        ("^adm_uact_wipe_confirm$",    adm_user_activity_wipe_confirm_callback),
        ("^adm_uact_wipe_do$",         adm_user_activity_wipe_do_callback),
        ("^adm_uact_",                 adm_user_activity_callback),
        # 🆕 v66: Price-drop broadcast confirm
        ("^pdrop_yes_",                adm_price_drop_yes_callback),
        ("^pdrop_no$",                 adm_price_drop_no_callback),
        # 🆕 Payment Email Settings
        ("^admin_payment_emails$", admin_payment_emails_callback),
        # 🆕 v59: Default shop filter (Settings → 🛒 Default Shop Filter)
        ("^admin_shop_filter$", admin_shop_filter_callback),
        ("^setshopfilter_", set_shop_filter_callback),
        ("^pem_edit_email_", admin_pem_edit_email_callback),
        ("^pem_edit_pass_", admin_pem_edit_pass_callback),
        ("^pem_view_", admin_pem_view_callback),
        ("^pem_test_all$", admin_pem_test_all_callback),
        ("^pem_test_", admin_pem_test_callback),
        # 🆕 v33: Payment Methods (grouped)
        ("^admin_payments$", admin_payments_callback),
        ("^pm_binance$", admin_pm_binance_callback),
        ("^pm_easypaisa$", admin_pm_easypaisa_callback),
        ("^pm_jazzcash$", admin_pm_jazzcash_callback),
        ("^pm_crypto$", admin_pm_crypto_callback),
        ("^set_stars_rate$", stars_rate_start_callback),
        ("^bybit_test$", bybit_test_callback),
        # 🆕 v30: Binance proxy removed (screenshot verifier doesn't need it)
        # 🆕 v23: Product Color Indicators
        ("^admin_colors$", admin_colors_callback),
        ("^cl_toggle$", color_toggle_callback),
        ("^cl_pick_", color_pick_callback),
        ("^cl_set_", color_set_callback),
        ("^cl_threshold$", color_threshold_callback),
        ("^cl_thr_", color_set_threshold_callback),
        ("^cl_preview$", color_preview_callback),
        ("^cl_reset$", color_reset_callback),
        ("^my_orders$", my_orders_callback),
        ("^myordspg_", my_orders_callback),   # 🆕 v170.5: receipt pagination
        ("^myords_", my_orders_callback),     # 🆕 v170.6: receipt filter+page
        ("^myord_resend_", my_order_resend_callback),
        ("^myord_", my_order_detail_callback),
        ("^orders_layout_picker$", orders_layout_picker_callback),
        ("^set_orders_layout_", set_orders_layout_callback),
        ("^pts_custom$", points_custom_callback),
        ("^ptspay_binance_menu_", points_binance_menu_callback),
        ("^ptspay_bybit_menu_", points_bybit_menu_callback),
        ("^ptspay_usdt_", points_usdt_callback),
        ("^ptspay_bybit_", points_bybit_callback),
        ("^ptspay_binance_", points_binance_callback),
        ("^ptspay_easy_", points_easypaisa_callback),
        ("^ptspay_jazz_", points_jazzcash_callback),
        ("^ptspay_usdt_", points_usdt_callback),
        ("^pay_usdt_", payment_usdt_callback),
        ("^usdtv_", usdt_verify_callback),
        ("^ptspay_binance_menu_", points_binance_menu_callback),
        ("^pay_binance_menu_", payment_binance_menu_callback),
        ("^ptspay_bybit_menu_", points_bybit_menu_callback),
        ("^pay_bybit_menu_", payment_bybit_menu_callback),
        ("^ptspay_bybit_", points_bybit_callback),
        ("^pay_bybit_", payment_bybit_callback),
        ("^bybitv_", bybit_verify_callback),
        ("^bybit_manual_confirm_", bybit_manual_confirm_callback),
        ("^bybit_flow_continue$", bybit_flow_continue_callback),
        ("^bybit_flow_cancel$", bybit_flow_cancel_callback),
        ("^pay_pts_", pay_pts_callback),
        ("^admin_panel$", admin_panel_callback),
        ("^admin_categories$", admin_categories_callback), ("^delcat_", delete_category_callback),
        ("^admin_products$", admin_products_callback), ("^delprod_", delete_product_callback),
        ("^viewcat_", view_category_callback),
                ("^manhist_", manual_hist_callback),
        ("^editman_", edit_manual_order_callback),
        ("^delset_", delivery_settings_callback),
        ("^pdm_", pdm_callback),
        ("^pfmt_", pfmt_callback),
        ("^pmt_", pmt_callback),
        ("^pmail_", pmail_callback),
        ("^ppass_", ppass_callback),
        ("^adm_upacct_", adm_upacct_callback),
        ("^upacct_skip_inst$", upacct_skip_inst_callback),
        ("^adm_chat_", adm_chat_callback),
        ("^reply_to_admin$", user_reply_to_admin_callback),
        ("^cancel_user_chat$", cancel_user_chat_callback),
        ("^adm_ownmaildone_", adm_ownmaildone_callback),
        ("^ord_fresh_yes_", ord_fresh_yes_callback),
        ("^ownmail_fresh_yes_", ownmail_fresh_yes_callback),
        ("^ownmail_fresh_no_", ownmail_fresh_no_callback),
        ("^dsfmtpick_", ds_format_pick_callback),
        ("^dsfmt_", ds_set_format_callback),
        ("^dstplpick_", ds_template_pick_callback),
        ("^dstpl_", ds_set_template_callback),
        ("^ds_", ds_toggle_callback),
        ("^viewprod_", view_product_callback),
        # Admin product active/deactivated + hide/unhide toggles
        ("^prodactive_", toggle_product_active_callback),
        ("^prodhide_", toggle_product_hidden_callback),
        ("^prodfake_", toggle_product_fake_off_callback),   # 🆕 v170.5
        ("^delcatdo_", delete_category_do_callback),
        ("^delproddo_", delete_product_do_callback),
        ("^bulkprod_start$", bulk_product_delete_start_callback),
        ("^bulkprod_tgl_", bulk_product_delete_toggle_callback),
        ("^bulkprod_page_", bulk_product_delete_page_callback),
        ("^bulkprod_clear_", bulk_product_delete_clear_callback),
        ("^bulkprod_confirm$", bulk_product_delete_confirm_callback),
        ("^bulkprod_do$", bulk_product_delete_do_callback),
        ("^bulkprice_start$", bulk_price_start_callback),
        ("^bulkprice_tgl_", bulk_price_toggle_callback),
        ("^bulkprice_page_", bulk_price_page_callback),
        ("^bulkprice_custom$", bulk_price_custom_callback),
        ("^bulkprice_apply_", bulk_price_apply_callback),
        # 🆕 v157/v158: Bulk Discount (tiered quantity pricing)
        ("^bdisc_start$", bulk_discount_start_callback),
        ("^bdisc_page_", bdisc_page_callback),
        ("^bdisc_prod_", bdisc_prod_callback),
        ("^bdisc_addq_", bdisc_addq_callback),
        ("^bdisc_rm_",          bdisc_rm_callback),
        ("^bdisc_broadcast_",   bdisc_broadcast_callback),  # 🆕 v170.14
        ("^bdisc_cancel$", bdisc_cancel_callback),
        ("^togglemode_", toggle_delivery_mode_callback),
        # 🆕 v71: replacement window picker — MUST come before generic ^editfield_
        ("^editfield_repwin_", admin_repwin_picker_callback),
        ("^editfield_", edit_product_field_callback),
        ("^editcat_", edit_category_field_callback),
        ("^prodaccounts_manage_", manage_product_accounts_callback),
        ("^prodaccounts_show_", show_product_accounts_callback),
        ("^prodaccounts_delall_confirm_", delete_all_accounts_confirm_callback),
        ("^prodaccounts_delall_do_", delete_all_accounts_do_callback),
        ("^prodaccounts_delone_", delete_single_account_callback),
        ("^prodaccount_view_", view_single_account_callback),
        ("^prodaccount_edit_", edit_single_account_callback),
        ("^prodaccount_del_confirm_", delete_single_account_confirm_callback),
        ("^prodaccount_del_do_", delete_single_account_do_callback),
        # 🆕 v73: ^admin_orders$ pattern REMOVED (Pending Orders button deprecated).
        # Kept view_order_ for direct deep-links from notifications & for view-only.
        ("^view_order_", view_order_callback),
        ("^approve_", approve_order_callback), ("^reject_", reject_order_callback),
        ("^admin_users$", admin_users_callback),
        ("^ban_panel$", ban_panel_callback),          # 🆕 v170.37 banned users panel
        # 🆕 v149: refund-by-user-ID + per-user full history
        ("^adm_refund_uid$", adm_refund_uid_callback),
        ("^adm_refund_uid_", adm_refund_uid_callback),
        ("^adm_uhist_enter$", adm_uhist_enter_callback),
        ("^adm_uhist_", adm_uhist_callback),
        ("^ruid_confirm$", adm_refund_uid_confirm_callback),
        ("^ruid_cancel$", adm_refund_uid_cancel_callback),
        ("^admin_settings$", admin_settings_callback),
        ("^admin_terms$", admin_terms_callback),
        ("^admin_responses$", admin_responses_callback),
        ("^admin_broadcast$", broadcast_callback),
        # 🆕 v148: Polls (create / results / manage / answers)
        ("^admin_polls$", admin_polls_callback),
        ("^poll_create$", poll_create_start_callback),
        # 🆕 v152: forwarded-poll confirm (background broadcast)
        ("^fwd_poll_yes$", fwd_poll_yes_callback),
        ("^fwd_poll_no$", fwd_poll_no_callback),

        ("^poll_results$", poll_results_callback),
        ("^poll_detail_", poll_detail_callback),
        ("^poll_close_", poll_close_callback),
        ("^poll_del_", poll_delete_callback),
        ("^poll_cancel$", poll_cancel_callback),
        ("^poll_list$", poll_list_callback),
        ("^bcbtn_(yes|no)$", broadcast_button_choice_callback),
        ("^bcbtn_color_", broadcast_button_color_callback),
        ("^bcbtn_cancel$", broadcast_button_color_callback),
        ("^bcbtn_send_", broadcast_button_send_callback),
        ("^bcbtn_action_", broadcast_button_action_callback),
        ("^bcbtn_pick_", broadcast_button_pick_callback),
        ("^bcbtn_ppage_", broadcast_button_product_page_callback),
        ("^bcbtn_noop$", broadcast_button_noop_callback),
        ("^fake_custom_broadcast$", fake_custom_broadcast_callback),
        ("^admin_profit$", admin_profit_callback),
        ("^profit_all$", profit_all_callback),
        # 🆕 Customization handlers
        ("^admin_customization$", admin_customization_callback),
        ("^persist_panel$", persist_panel_callback),                       # 🆕 v170.12
        ("^persist_ren_", persist_rename_callback),                        # 🆕 v170.12
        ("^persist_move_.+_(up|down)$", persist_move_callback),            # 🆕 v170.12
        ("^persist_color_", persist_color_callback),                       # 🆕 v170.14
        ("^persist_setcol_.+_(green|blue|red|none)$", persist_setcol_callback),  # 🆕 v170.14
        # 🆕 v144: new customization tools
        ("^adm_users_search$",     adm_users_search_callback),
        ("^cz_noop$",              cz_noop_callback),
        ("^cz_search$",            cz_search_callback),
        ("^cz_theme$",             cz_theme_callback),
        ("^cz_theme_",             cz_theme_apply_callback),
        ("^cz_backup$",            cz_backup_callback),
        ("^cz_import$",            cz_import_callback),
        ("^cz_banner$",            cz_banner_callback),
        ("^cz_banner_toggle$",     cz_banner_toggle_callback),
        ("^cz_banner_text$",       cz_banner_text_callback),
        ("^cz_catcolors$",         cz_catcolors_callback),
        ("^cz_catcolor_",          cz_catcolor_set_callback),
        ("^cz_fmt_",               cz_fmt_callback),
        ("^admin_toggles$", admin_toggles_callback),
        ("^toggle_show_", toggle_field_callback),
        ("^toggle_auto_product_colors$", toggle_field_callback),
        # 🆕 v98: auto-group products by first word toggle
        ("^toggle_auto_group_by_name$", toggle_field_callback),
        # 🆕 Step 2: Button Size handlers
        ("^admin_btn_size$", admin_btn_size_callback),
        ("^setsize_", set_button_size_callback),
        # 🆕 Step 3: Menu Style handlers
        ("^admin_menu_style$", admin_menu_style_callback),
        ("^setstyle_", set_menu_style_callback),
        # 🆕 Step 4: Display Format (Carousel)
        ("^admin_display_format$", admin_display_format_callback),
        ("^setformat_", set_display_format_callback),
        ("^cnav_", carousel_nav_callback),
        # 🆕 Phase A: Manage Buttons
        ("^admin_buttons$", admin_buttons_callback),
        ("^mbgrp_", manage_buttons_group_callback),
        ("^mbedit_", manage_one_button_callback),
        ("^mbtog_", toggle_button_visibility_callback),
        ("^mbrst_", reset_button_callback),
        ("^mbcolor_", button_color_callback),
        ("^mbsetcol_", button_set_color_callback),
        ("^mbgcolor_", group_color_callback),
        ("^mbgsetcol_", group_set_color_callback),
        ("^mbscrpad_", group_screen_pad_callback),
        ("^cbcolor_", custom_button_color_callback),
        ("^cbsetcol_", custom_button_set_color_callback),
        ("^noop$", noop_callback),
        ("^locked$", locked_callback),
        # 🆕 Phase B: Custom Buttons
        ("^admin_cbtns$", admin_cbtns_callback),
        # 🆕 v54: mblist_all_custom — list view that returns to admin_buttons (the new Manage hub)
        ("^mblist_all_custom$", mblist_all_custom_callback),
        ("^cblist_", cb_list_callback),
        ("^cbview_", cb_view_callback),
        ("^cbdel_", cb_delete_callback),
        ("^cbnew$", cb_new_callback),
        ("^cbloc_", cb_location_callback),
        ("^cbsubmgmt_", cb_submenu_mgmt_callback),
        ("^cbedit_location_", cb_edit_location_callback),
        ("^cbstyle_", cb_style_callback),
        # 🆕 Phase C: Reorder
        ("^mbup_", move_system_btn_up_callback),
        ("^mbdn_", move_system_btn_down_callback),
        ("^cbup_", move_custom_btn_up_callback),
        ("^cbdn_", move_custom_btn_down_callback),
        # 🆕 Phase D: Custom Pages
        ("^admin_cpages$", admin_cpages_callback),
        ("^cpview_", cp_view_callback),
        ("^cpdel_", cp_delete_callback),
        ("^cprmphoto_", cp_rmphoto_callback),
        ("^cpnew$", cp_new_callback),
        ("^cppreview_", cp_preview_callback),
        ("^cppick_", cppick_callback),
        # 🆕 Phase D: Categorized shop
        ("^shopall$", shop_all_callback),
        ("^flashtoggle_", flash_toggle_callback),
        ("^flashdur_", flash_duration_callback),
        ("^shop_flash$", shop_flash_callback),
        ("^req_restock_", req_restock_callback),
        ("^shopcat_", shop_category_callback),
        ("^shopcatpg_", shop_category_page_callback),
        ("^toggle_shop_cat$", toggle_shop_categorized_callback),
        # User-side custom button clicks:
        ("^cbtn_", cbtn_text_callback),          # legacy text-only buttons
        ("^cbsub_", cbsub_open_callback),
        ("^cbpage_", cbpage_open_callback),
        # 🆕 v38: Unified action executor — handles all 17+ action types
        ("^cbact_", custom_button_action_callback),
        # 🆕 v38: Admin navigation target picker
        ("^cbnav_", cb_nav_target_callback),
        # 🆕 Universal cancel for inline Cancel button (outside conversations)
        ("^conv_cancel$", conv_cancel_callback),
        # 🔙 Universal back button (navigation stack)
        ("^go_back$", go_back_callback),
        # 🎫 Support Tickets (user side)
        ("^support_menu$", support_menu_callback),
        ("^st_list$", st_list_callback),
        ("^st_view_", st_view_callback),
        # 🛡️ Warranty/Refund (user side)
        ("^warranty_menu$", warranty_menu_callback),
        ("^wr_order_", wr_order_callback),
        # 🎫 Support Tickets (admin side)
        ("^adm_tickets$", adm_tickets_callback),
        ("^adm_tickets_open$", adm_tickets_list_callback),
        ("^adm_tickets_all$", adm_tickets_list_callback),
        ("^adm_st_view_", adm_st_view_callback),
        ("^adm_st_resolve_", adm_st_resolve_callback),
        ("^adm_st_progress_", adm_st_progress_callback),
        ("^adm_st_close_", adm_st_close_callback),
        # 🛡️ Warranty/Refund (admin side)
        ("^adm_warranty$", adm_warranty_callback),
        ("^adm_wr_pending$", adm_wr_list_callback),
        ("^adm_wr_all$", adm_wr_list_callback),
        ("^adm_wr_view_", adm_wr_view_callback),
        ("^adm_wr_approve_", adm_wr_approve_callback),
        # 🆕 v161.12: specific reject-reason buttons BEFORE the generic reject
        ("^adm_wr_reject_do_\\d+$", adm_wr_reject_do_callback),
        ("^adm_wr_reject_cancel_\\d+$", adm_wr_reject_cancel_callback),
        ("^adm_wr_reject_\\d+$", adm_wr_reject_callback),
        # 📦 Manual Delivery (admin side)
        ("^adm_pending_delivery$", adm_pending_delivery_callback),
        ("^adm_restock_reqs$", adm_restock_reqs_callback),
        ("^adm_dmode_", adm_delivery_mode_callback),
        ("^dmode_auto$", delivery_mode_callback),
        ("^dmode_manual$", delivery_mode_callback),
        # 📊 Admin Deposit History
        ("^admin_deposits$", admin_deposit_history_callback),
        ("^adm_diagnostics$", adm_diagnostics_callback),
        ("^adm_pts_audit_", adm_pts_audit_callback),
        ("^dephist_", admin_deposit_page_callback),
        ("^depview_", admin_deposit_detail_callback),
        # 💰 Sold Accounts (delivered accounts log)
        ("^sold_accounts", sold_accounts_callback),
        ("^sold_view_", sold_account_view_callback),
        # ✏️ Responses categories
        ("^respcat_", admin_responses_category_callback),
        # 🆕 v37: Language Selector
        ("^language_menu$", language_menu_callback),
        ("^setlang_", set_language_callback),
        # 🆕 v161.20: Language System admin panel + previews
        ("^admin_lang_system$", admin_lang_system_callback),
        ("^langsys_",           langsys_preview_callback),
        # 🆕 v37: Reviews (user side)
        ("^reviews_menu$", reviews_menu_callback),
        ("^rev_pick_order$", rev_pick_order_callback),
        ("^rev_start_", rev_start_callback),
        ("^revskip_", rev_skip_callback),
        ("^rev_my_list$", rev_my_list_callback),
        ("^prodrev_", product_reviews_view_callback),
        # 🆕 v37: Reviews (admin side)
        ("^admin_reviews$", admin_reviews_callback),
        ("^admrev_pin_", admrev_pin_callback),
        ("^admrev_hide_", admrev_hide_callback),
        ("^admrev_del_", admrev_del_callback),
        # 🆕 v37: Loyalty Tiers
        ("^loyalty_menu$", loyalty_callback),
        ("^admin_loyalty$", admin_loyalty_callback),
        # 🆕 v68: Tier customization
        ("^admin_tier_cfg$",                admin_tier_cfg_callback),
        ("^admin_tier_toggle_bonus$",       admin_tier_toggle_bonus_callback),
        ("^admin_tier_toggle_msg$",         admin_tier_toggle_msg_callback),
        ("^admin_tier_edit_",               admin_tier_edit_callback),
        ("^admin_tier_field_",              admin_tier_field_callback),
        ("^admin_tier_reset_confirm$",      admin_tier_reset_confirm_callback),
        ("^admin_tier_reset_do$",           admin_tier_reset_do_callback),
        # 🆕 v37: Analytics Dashboard
        ("^admin_analytics$", analytics_callback),
        # 🆕 v161.3: Reseller API admin panel (buttons)
        ("^reseller_panel$", admin_reseller_callback),
        ("^reseller_gen_panel$", reseller_gen_panel_callback),
        ("^reseller_keys_panel$", reseller_keys_panel_callback),
        ("^reseller_keycfg_panel_\\d+$", reseller_keycfg_panel_callback),
        ("^reseller_keyaction_\\d+_[a-z_]+$", reseller_keyaction_callback),
        ("^reseller_pricing_panel$", reseller_pricing_panel_callback),
        ("^reseller_keyprices_\\d+$", reseller_keyprices_callback),   # 🆕 v170.6
        ("^reseller_setprice_\\d+_\\d+$", reseller_setprice_callback),  # 🆕 v170.6
        ("^reseller_price_markup$", reseller_price_markup_callback),
        ("^reseller_base_mode_(cost|price)$", reseller_base_mode_callback),
        ("^reseller_orders_panel$", reseller_orders_panel_callback),
        ("^reseller_orders_filter_(status|range)_(.+)$", reseller_orders_filter_callback),
        ("^reseller_deliver_panel_\\d+$", reseller_deliver_panel_callback),
        ("^reseller_order_view_\\d+$", reseller_order_view_callback),  # 🆕 v170.40 full order detail
        ("^reseller_stats_panel$", reseller_stats_panel_callback),
        ("^reseller_dashboard_panel$", reseller_dashboard_callback),
        ("^reseller_admin_products$", reseller_admin_products_callback),
        ("^reseller_prod_all_(on|off)$", reseller_prod_all_callback),  # 🆕 v170.12
        ("^reseller_prod_toggle_\\d+$", reseller_prod_toggle_callback),
        ("^reseller_prod_price_\\d+$", reseller_prod_price_callback),
        ("^reseller_prod_page_\\d+$", reseller_prod_page_callback),
        # 🆕 v161.6: reseller tracking (per-key orders, top-up, webhook log, export)
        ("^reseller_orders_key_\\d+$", reseller_orders_key_callback),
        ("^reseller_topup_\\d+$", reseller_topup_callback),
        ("^reseller_webhooks_panel$", reseller_webhooks_callback),
        ("^reseller_export_panel$", reseller_export_callback),
        ("^reseller_export_key_\\d+$", reseller_export_key_callback),
        # 🆕 v161.4: user-facing ProdSeller-style API Access panel (any user)
        ("^cz_admin_all_green$", cz_admin_all_green_callback),
        ("^reseller_api_user$", reseller_api_user_callback),
        ("^reseller_api_generate$", reseller_api_generate_callback),
        ("^reseller_api_show$", reseller_api_show_callback),
        ("^reseller_api_regenerate$", reseller_api_regenerate_callback),
        ("^an_p_", analytics_period_callback),
        ("^an_top_prod_", analytics_top_products_callback),
        ("^an_top_cust_", analytics_top_customers_callback),
        ("^an_pay_", analytics_payment_callback),
        ("^an_chart_", analytics_chart_callback),
        # 🆕 v73: Supplier Panel + Supplier Admin Panel callbacks REMOVED.
        # 🆕 v73: Completed Orders + Replacement History callbacks (old flat view kept)
        ("^admin_completed$",            admin_completed_orders_callback),
        ("^admin_completed_filter_",     admin_completed_filter_callback),
        # 🆕 v84: Completed Orders v2 — grouped by user, searchable
        ("^admin_completed_v2$",         admin_completed_v2_callback),
        ("^ac2_page_",                   ac2_page_callback),
        ("^ac2_user_",                   ac2_user_callback),
        ("^ac2_order_",                  ac2_order_callback),
        # 🆕 v101: user-side delivery preview (admin sees exactly what customer got)
        ("^ac2_userview_",               ac2_userview_callback),
        ("^ac2_allfiles_",               ac2_allfiles_callback),   # 🆕 v170.5
        ("^ac2_sf_(all|delivered|refunded|cancelled)$", ac2_sf_callback),  # 🆕 v170.17
        ("^ac2_resend_",                 ac2_resend_callback),      # 🆕 v170.17
        ("^ac2_dlfile_",                 ac2_dlfile_callback),
        # 🆕 v161.20: delivered-items audit (voice/video/pic/file/text)
        ("^ac2_dlv_",                    ac2_dlv_callback),
        ("^ac2_dlvopen_",                ac2_dlvopen_callback),
        ("^ac2_clear_search$",           ac2_clear_search_callback),
        ("^ac2_noop$",                   ac2_noop_callback),
        # 🆕 v84: Maintenance Mode admin panel
        ("^maint_panel$",                maint_panel_callback),
        ("^maint_toggle$",               maint_toggle_callback),
        ("^maint_live_off$",             maint_live_off_callback),
        ("^maint_live_keep$",            maint_live_keep_callback),
        ("^maint_preview$",              maint_preview_callback),
        ("^maint_pick_",                 maint_pick_callback),
        ("^maint_noop$",                 maint_noop_callback),
        # 🆕 v80: Payment Methods Enable/Disable
        ("^admin_pay_toggle$",           admin_payment_toggle_callback),
        ("^admin_pay_toggle_",           admin_payment_toggle_action_callback),
        ("^admin_pay_msg_",              admin_payment_msg_start_callback),
        # 🆕 v81: External Suppliers admin panel
        ("^admin_suppliers$",            admin_suppliers_callback),
        ("^ext_sup_add$",                ext_sup_add_callback),
        ("^ext_sup_add_type_",           ext_sup_add_type_callback),
        ("^ext_sup_preset_",             ext_sup_preset_callback),
        ("^ext_sup_noop$",               ext_sup_noop_callback),
        ("^ext_sup_view_",               ext_sup_view_callback),
        ("^ext_sup_test_",               ext_sup_test_callback),
        ("^ext_sup_apiupd_",             ext_sup_api_update_callback),
        ("^ext_sup_toggle_",             ext_sup_toggle_callback),
        ("^ext_sup_del_confirm_",        ext_sup_del_confirm_callback),
        ("^ext_sup_del_",                ext_sup_del_callback),
        ("^ext_sup_import_all_",         ext_sup_import_all_callback),
        ("^ext_sup_import_pick_",        ext_sup_import_pick_callback),
        ("^ext_sup_bulk_markup_",        ext_sup_bulk_markup_callback),
        ("^ext_sup_bulk_set_",           ext_sup_bulk_set_callback),
        ("^ext_prod_view_",              ext_prod_view_callback),
        ("^ext_prod_toggle_",            ext_prod_toggle_callback),
        ("^ext_prod_markup_",            ext_prod_markup_callback),
        ("^ext_prod_set_mkp_",           ext_prod_set_mkp_callback),
        ("^ext_prod_emoji_",             ext_prod_emoji_callback),
        ("^ext_prod_cat_",               ext_prod_cat_callback),
        ("^ext_prod_setcat_",            ext_prod_setcat_callback),
        # 🆕 v81.1: Fixed price (Smart Lock) — ORDER MATTERS:
        # More specific patterns MUST come first, else generic ext_prod_fixprice_
        # would match ext_prod_fixprice_set_ etc.
        ("^ext_prod_fixprice_set_",      ext_prod_fixprice_set_callback),
        ("^ext_prod_fixprice_clear_",    ext_prod_fixprice_clear_callback),
        ("^ext_prod_fixprice_",          ext_prod_fixprice_callback),
        # 🆕 v83: Manual sync + format picker (order matters, specific first)
        ("^ext_prod_setfmt_",            ext_prod_setfmt_callback),
        ("^ext_prod_sync_",              ext_prod_sync_callback),
        # 🆕 v107: force-refresh a single product from supplier (pro Shopify overwrite pattern)
        ("^ext_prod_refresh_",           ext_prod_refresh_callback),
        ("^ext_prod_fmt_",               ext_prod_fmt_callback),
        ("^supplier_retry_",             supplier_retry_delivery_callback),
        # 🆕 v85: Bulk sync + low-bal threshold editor + finance + autosync toggle
        ("^ext_sup_bulk_sync_",          ext_sup_bulk_sync_callback),
        ("^ext_sup_bulk_unsync_",        ext_sup_bulk_unsync_callback),
        ("^admin_finance$",              admin_finance_callback),
        ("^fin_p_",                      fin_p_callback),
        ("^admin_autosync$",             admin_autosync_callback),
        ("^autosync_toggle$",            autosync_toggle_callback),
        # 🆕 v92: Main Menu Layout Picker — order matters (specific first)
        ("^admin_main_layout$",          mml_hub_callback),
        ("^mml_cat_",                    mml_cat_callback),
        ("^mml_view_",                   mml_view_callback),
        ("^mml_apply_",                  mml_apply_callback),
        ("^mml_preview_",                mml_preview_callback),
        ("^mml_reset$",                  mml_reset_callback),
        ("^main_more_expand$",           main_more_expand_callback),
        # 🆕 v94: Global broadcast button color picker
        ("^admin_broadcast_color$",      broadcast_color_panel_callback),
        ("^bcolor_set_",                 broadcast_color_set_callback),
        # 🆕 v87: Auto-translator — order matters (specific patterns first)
        ("^admin_translator$",           admin_translator_callback),
        ("^trxl_toggle$",                trxl_toggle_callback),
        ("^trxl_pick_from_",             trxl_pick_from_callback),
        ("^trxl_pick_to_",               trxl_pick_to_callback),
        ("^trxl_set_",                   trxl_set_callback),
        ("^trxl_scan_confirm$",          trxl_scan_confirm_callback),
        ("^trxl_scan_run$",              trxl_scan_run_callback),
        ("^trxl_clear_cache$",           trxl_clear_cache_callback),
        ("^trxl_noop$",                  trxl_noop_callback),
        ("^admin_replacements$",         admin_replacement_history_callback),
        ("^admin_replacements_filter_",  admin_replacement_filter_callback),
        ("^admin_replacement_view_",     admin_replacement_view_callback),
        ("^admin_replacement_act_",      admin_replacement_action_callback),

        # 🆕 v75: User-facing API callbacks REMOVED (Worker deployment, no public URL).

        # 🆕 v76: How-to-Use guide hub + individual guide screens
        ("^how_to_hub$",  how_to_hub_callback),
        ("^guide_",       guide_screen_callback),
        # 🆕 Force Join handlers
        ("^fj_panel$",          fj_panel_callback),
        ("^fj_toggle$",         fj_toggle_callback),
        ("^fj_test$",           fj_test_callback),
        ("^fj_verified$",       fj_verified_callback),
        ("^fj_reset_msg$",      fj_reset_msg_callback),
        ("^fj_noop$",           fj_noop_callback),
        # 🆕 v135: unlimited targets + editable buttons + verify button editor
        ("^fj_add$",                  fj_add_callback),
        ("^fj_bulk$",                 fj_bulk_callback),
        ("^fjb_t_",                   fjb_t_callback),
        ("^fjb_all$",                 fjb_all_callback),
        ("^fjb_none$",                fjb_none_callback),
        ("^fjb_del$",                 fjb_del_callback),
        ("^fj_vbtn_col_",             fj_vbtn_col_callback),
        ("^fj_vbtn_emo_clear$",       fj_vbtn_emo_clear_callback),
        ("^fj_vbtn_emo$",             fj_vbtn_emo_callback),
        ("^fj_vbtn_ren$",             fj_vbtn_ren_callback),
        ("^fj_vbtn$",                 fj_vbtn_callback),
        ("^fjm_ren_",                 fjm_ren_callback),
        ("^fjm_col_",                 fjm_col_callback),
        ("^fjm_emo_clear_",           fjm_emo_clear_callback),
        ("^fjm_emo_",                 fjm_emo_callback),
        ("^fjm_link_",                fjm_link_callback),
        ("^fjm_del_yes_",             fjm_del_yes_callback),
        ("^fjm_del_",                 fjm_del_callback),
        ("^fjm_up_|^fjm_down_",       fjm_move_callback),
        ("^fjm_",                     fjm_callback),
        # 🆕 Destinations handlers
        ("^dest_panel$",        dest_panel_callback),
        ("^dest_clear_chat$",   dest_clear_chat_callback),
        # 🆕 Per-User Activity handlers
        ("^act_panel$",        activity_panel_callback),
        ("^admin_bcast_test$", admin_bcast_test_callback),
        ("^act_toggle_global$", act_toggle_global_callback),
        ("^act_toggle_unit$",   act_toggle_unit_callback),
        ("^act_offset_random$", act_offset_random_callback),
        ("^act_users$",         act_users_callback),
        ("^act_stop_all$",      act_stop_all_callback),
        ("^act_start_all$",     act_start_all_callback),
        ("^act_noop$",          act_noop_callback),
        # 🆕 Location Customizer handlers
        ("^lc_panel$",    location_customizer_panel_callback),
        ("^lc_noop$",     lc_noop_callback),
        # 🆕 Template Editor handlers
        ("^tpl_panel$",   template_editor_panel_callback),
        ("^tpl_noop$",    tpl_noop_callback),
        # 🆕 Product Design handlers
        ("^pd_panel$",    product_design_panel_callback),
        ("^pd_reset$",    pd_reset_callback),
        ("^pd_noop$",     pd_noop_callback),
        # fbc/frv removed — use 🎭 Fake Activity instead
        # 🆕 v78: API Management handlers REMOVED (admin panel button deprecated).
        # 🆕 v47: Free-via-Referrals — admin config
        ("^fcrf_panel_",        fcrf_panel_callback),
        ("^fcrf_toggle_",       fcrf_toggle_callback),
        ("^fcrf_setrefs_",      fcrf_setrefs_callback),
        ("^fcrf_tpllist_",      fcrf_tpllist_callback),
        ("^fcrf_pick_",         fcrf_pick_callback),
        ("^fcrf_custom_",       fcrf_custom_callback),
        ("^fcrf_preview_",      fcrf_preview_callback),
        ("^fcrf_test_",         fcrf_test_callback),
        ("^fcrf_history$",      fcrf_history_callback),
        # 🆕 v110: Per-product referrals tracker (fcrf_refs_<pid>_<page>)
        ("^fcrf_refs_",         fcrf_refs_callback),
        # 🆕 v47-48: Free-via-Referrals — user claim flow
        ("^freeclaim_open_",    freeclaim_open_callback),
        ("^freeclaim_do_",      freeclaim_do_callback),
        ("^freeclaim_share_",   freeclaim_share_callback),  # 🆕 v48
        # 🆕 v170.13 — Freebies
        ("^freebies_menu$",     freebies_menu_callback),
        ("^freebie_open_",      freebie_open_callback),
        ("^freebie_do_",        freebie_do_callback),
        ("^freebies_admin_panel$", freebies_admin_panel_callback),
        ("^freebie_cfg_",       freebie_config_callback),
        ("^freebie_toggle_",    freebie_toggle_callback),
        ("^freebie_limit_",     freebie_limit_callback),
        ("^freebie_refs_",      freebie_refs_callback),
        ("^make_freebie_",      make_freebie_callback),
        # 🆕 v48: Referral Abuse admin panel
        ("^refadm_panel$",      refadm_panel_callback),
        ("^refadm_top$",        refadm_top_callback),   # 🆕 v170.9 top referrers
        ("^refadm_set_points_start$", refadm_set_points_start),
        ("^refadm_bonus_start$",      refadm_bonus_start),  # 🆕 v161.20 milestone bonus
        ("^refadm_prod_panel$",       refadm_prod_panel_callback),
        ("^refadm_prod_detail_",      refadm_prod_detail_callback),
        ("^refadm_math_toggle$",      refadm_math_toggle_callback),
        # 🆕 v102: alias — Settings → 🔍 Referral Diagnostics button
        ("^admin_ref_diag$",    refadm_panel_callback),
        ("^refadm_log_",        refadm_log_callback),
        ("^refadm_banlist$",    refadm_banlist_callback),
        ("^refadm_ban_start$",  refadm_ban_start),
        ("^refadm_unban_start$", refadm_unban_start),
        ("^refadm_adjust_start$", refadm_adjust_start),
        ("^refadm_tpl_panel$", refadm_tpl_panel_callback),
        ("^refadm_tpl_edit_", refadm_tpl_edit_callback),
        ("^refadm_tpl_ready_", refadm_tpl_ready_callback),
        ("^refadm_tpl_apply_", refadm_tpl_apply_callback),
        ("^refadm_tpl_preview_", refadm_tpl_preview_callback),
        ("^refadm_tpl_reset_all$", refadm_tpl_reset_all_callback),
        ("^refadm_btn_panel$", refadm_btn_panel_callback),
        ("^refadm_btn_edit$", refadm_btn_edit_callback),
        ("^refadm_btn_color_", refadm_btn_color_callback),
        ("^refadm_btn_reset$", refadm_btn_reset_callback),
        # 🆕 v49: Per-product broadcast button editor
        ("^fcb_panel_",         fcb_panel_callback),
        ("^fcb_settext_",       fcb_settext_callback),
        ("^fcb_setemoji_",      fcb_setemoji_callback),
        ("^fcb_styler_",        fcb_styler_callback),
        ("^fcb_color_",         fcb_color_callback),
        ("^fcb_pickcolor_",     fcb_pickcolor_callback),
        ("^fcb_preview_",       fcb_preview_callback),
        ("^fcb_reset_",         fcb_reset_callback),
        # 🆕 v50: Screen-by-Screen Editor (user-side drill-down editor)
        ("^se_root$",           se_root_callback),
        ("^se_open_",           se_open_callback),
        ("^se_btns_",           se_btns_callback),
        ("^se_sub_",            se_sub_callback),
        ("^se_subbtn_",         se_subbtn_callback),
        ("^bypl_apply_",        bypl_apply_callback),
        ("^bypl_preview_",      bypl_preview_callback),
        ("^scl_apply_",         scl_apply_callback),
        ("^scl_preview_",       scl_preview_callback),
        ("^se_edittext_",       se_edittext_callback),
        ("^se_preview_",        se_preview_callback),
        ("^se_reset_",          se_reset_callback),
        ("^se_allcolor_",       se_allcolor_callback),
        ("^se_setallcol_",      se_setallcol_callback),
        ("^se_noop$",           se_noop_callback),
    ] + get_button_styler_handlers():  # 🆕 v40: Inline Button Styler handlers
        app.add_handler(CallbackQueryHandler(fn, pattern=pat))

    # 🆕 v73: ALL supplier ConversationHandlers REMOVED (Supplier panel deprecated).
    # ── 📤 Destination Chat Link Input ──
    # MUST be before dest_set_ prefix handler so ConversationHandler catches it first
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(dest_set_chat_callback, pattern="^dest_set_chat$")],
        states={DEST_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, dest_chat_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))
    # ── 🔗 Force Join Conversations (v135: only join-message text input) ──
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(fj_set_msg_callback, pattern="^fj_set_msg$")],
        states={FJ_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, fj_msg_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))
    # Pattern-based handlers (prefix match — must be after exact matches)
    # dest_set_chat handled by ConversationHandler above
    # 🆕 v73: All sadm_*/sup_* dynamic CallbackQueryHandlers REMOVED.
    app.add_handler(CallbackQueryHandler(dest_set_callback, pattern="^dest_set_(?!chat$)"))
    app.add_handler(CallbackQueryHandler(act_toggle_type_callback,    pattern="^act_type_"))
    app.add_handler(CallbackQueryHandler(act_user_toggle_callback,  pattern="^act_utog_"))
    app.add_handler(CallbackQueryHandler(lc_pick_location_callback,  pattern="^lc_loc_"))
    app.add_handler(CallbackQueryHandler(lc_set_cols_callback,         pattern="^lc_cols_"))
    app.add_handler(CallbackQueryHandler(lc_set_sep_callback,          pattern="^lc_sep_"))
    app.add_handler(CallbackQueryHandler(lc_reset_callback,            pattern="^lc_reset_"))
    app.add_handler(CallbackQueryHandler(tpl_setvar_callback,          pattern="^tpl_setvar_"))
    app.add_handler(CallbackQueryHandler(sb_template_set_callback,     pattern="^sbset_"))
    app.add_handler(CallbackQueryHandler(sb_test_callback,             pattern="^sbtest_"))
    app.add_handler(CallbackQueryHandler(sb_template_panel_callback,   pattern="^sbtpl_"))
    # 🆕 Custom Flash/New-Product template input conversation
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900,
        entry_points=[CallbackQueryHandler(sb_custom_start_callback, pattern="^sbcustom_")],
        states={SB_CUSTOM_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sb_custom_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(sb_template_panel_callback, pattern="^sbtpl_")],
    ))
    app.add_handler(CallbackQueryHandler(tpl_pick_callback,            pattern="^tpl_pick_"))
    app.add_handler(CallbackQueryHandler(tpl_reset_callback,           pattern="^tpl_reset_"))
    app.add_handler(CallbackQueryHandler(tpl_preview_callback,         pattern="^tpl_preview_"))
    app.add_handler(CallbackQueryHandler(tpl_test_callback,            pattern="^tpl_test_"))
    app.add_handler(CallbackQueryHandler(pd_layout_callback,      pattern="^pd_layout_"))
    app.add_handler(CallbackQueryHandler(pd_style_callback,       pattern="^pd_style_"))
    app.add_handler(CallbackQueryHandler(pd_field_toggle_callback,pattern="^pd_field_"))
    app.add_handler(CallbackQueryHandler(pd_perpage_callback,     pattern="^pd_perpage_"))
    app.add_handler(CallbackQueryHandler(pd_btnsize_callback,     pattern="^pd_btnsize_"))
    # fbc/frv prefix handlers removed

    # [conv handlers moved above prefix section]
    # ── 🎭 Fake Activity Speed ──
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(act_set_speed_callback, pattern="^act_set_speed$")],
        states={ACT_SPEED: [MessageHandler(filters.TEXT & ~filters.COMMAND, act_speed_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$"),
                   CallbackQueryHandler(activity_panel_callback, pattern="^act_panel$")],
    ))
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(act_set_delay_callback, pattern="^act_set_delay$")],
        states={ACT_DELAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, act_delay_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$"),
                   CallbackQueryHandler(activity_panel_callback, pattern="^act_panel$")],
    ))
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(act_set_offset_callback, pattern="^act_set_offset$")],
        states={ACT_OFFSET: [MessageHandler(filters.TEXT & ~filters.COMMAND, act_offset_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$"),
                   CallbackQueryHandler(activity_panel_callback, pattern="^act_panel$")],
    ))
    # 🔧 BUG FIX: Removed ConversationHandler wrappers for editfield_/editcat_.
    # These patterns were also registered as standalone CallbackQueryHandlers.
    # The ConversationHandler intercepted the callback, returned a STATE constant,
    # and then blocked all subsequent callbacks (like prodaccounts_manage_*, viewprod_, etc.)
    # because it was waiting for TEXT messages. This caused the bot to freeze/stuck
    # when clicking any edit button on already-added products.
    # The standalone handlers already set user_data['edit_pid'] / user_data['edit_field']
    # and manage their own edit flow — no ConversationHandler needed.
    # ── 📍 Location Header Editor ──
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(lc_set_header_callback, pattern="^lc_header_")],
        states={LC_HEADER: [MessageHandler(filters.TEXT & ~filters.COMMAND, lc_header_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))
    # ── 📝 Template Text Editor ──
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(tpl_edit_callback, pattern="^tpl_edit_")],
        states={TPL_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tpl_text_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation),
                   CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$")],
    ))

    # ── 🆕 v42: Edit Product List Emoji ──
    try:
        from handlers_admin import (
            EDIT_PRODUCT_EMOJI as _EDIT_EMOJI_STATE,
            edit_product_emoji_callback as _edit_emoji_cb,
            edit_product_emoji_received as _edit_emoji_recv,
        )
        app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900,
            entry_points=[CallbackQueryHandler(_edit_emoji_cb, pattern=r"^edit_product_emoji$")],
            states={_EDIT_EMOJI_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _edit_emoji_recv),
            ]},
            fallbacks=[
                CommandHandler("cancel", cancel_conversation),
                CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$"),
            ],
        ))
    except Exception as _e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"[bot.py] Product-Emoji editor not loaded: {_e}")

    # ── 🆕 v42 (kept for backward-compat): Broadcast Button Text Editor ──
    # Note: The standalone Customization-menu entry was removed in v43 at
    # admin's request — editing now lives inside each template (tplbtn_*).
    # The btxt_* backend remains registered so any older callback data still works.
    try:
        from handlers_buttons import (
            BTXT_INPUT,
            btxt_edit_callback as _btxt_edit_cb,
            btxt_input_received as _btxt_input_received,
            btxt_input_cancel as _btxt_input_cancel,
            btxt_panel_callback as _btxt_panel_cb,
            btxt_reset_callback as _btxt_reset_cb,
            btxt_resetall_callback as _btxt_resetall_cb,
            btxt_resetall_yes_callback as _btxt_resetall_yes_cb,
        )
        app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900,
            entry_points=[CallbackQueryHandler(_btxt_edit_cb, pattern=r"^btxt_edit_")],
            states={BTXT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _btxt_input_received),
            ]},
            fallbacks=[
                CommandHandler("cancel", _btxt_input_cancel),
                CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$"),
            ],
        ))
        app.add_handler(CallbackQueryHandler(_btxt_panel_cb,        pattern=r"^btxt_panel$"))
        app.add_handler(CallbackQueryHandler(_btxt_resetall_yes_cb, pattern=r"^btxt_resetall_yes$"))
        app.add_handler(CallbackQueryHandler(_btxt_resetall_cb,     pattern=r"^btxt_resetall$"))
        app.add_handler(CallbackQueryHandler(_btxt_reset_cb,        pattern=r"^btxt_reset_"))
    except Exception as _e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"[bot.py] Legacy Button Text Editor not loaded: {_e}")

    # ── 🆕 v43: PER-TEMPLATE Button Text Editor (premium emoji aware) ──
    try:
        from customization import (
            TPL_BTN_INPUT,
            tplbtn_edit_callback as _tplbtn_edit_cb,
            tplbtn_input_received as _tplbtn_input_received,
            tplbtn_input_cancel as _tplbtn_input_cancel,
            tplbtn_reset_callback as _tplbtn_reset_cb,
        )
        app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900,
            entry_points=[CallbackQueryHandler(_tplbtn_edit_cb, pattern=r"^tplbtn_edit_")],
            states={TPL_BTN_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _tplbtn_input_received),
            ]},
            fallbacks=[
                CommandHandler("cancel", _tplbtn_input_cancel),
                CallbackQueryHandler(_tplbtn_reset_cb, pattern=r"^tplbtn_reset_"),
                CallbackQueryHandler(conv_cancel_callback, pattern="^conv_cancel$"),
                # Cancel link inside the edit screen goes back to tpl_pick_*
                CallbackQueryHandler(_tplbtn_input_cancel, pattern=r"^tpl_pick_"),
            ],
        ))
        # Outside-conversation reset (button below the inline picker) also works
        app.add_handler(CallbackQueryHandler(_tplbtn_reset_cb, pattern=r"^tplbtn_reset_"))
    except Exception as _e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"[bot.py] Per-template button editor not loaded: {_e}")

    # fbc/frv conversation handlers removed

    app.add_handler(CallbackQueryHandler(points_amount_callback, pattern=r"^pts_\d+$"))
    app.add_handler(CallbackQueryHandler(profit_product_callback, pattern=r"^profit_\d+$"))

    # 🆕 v37: Review writing conversation (star rating → text)
    app.add_handler(ConversationHandler(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(rev_rate_callback, pattern=r"^revrate_\d+_\d+$")],
        states={REV_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, rev_text_received),
            CallbackQueryHandler(rev_skip_callback, pattern=r"^revskip_\d+$"),
        ]},
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CommandHandler("skip", rev_skip_command),  # 🔧 v39 fix: use command-safe handler
            CallbackQueryHandler(reviews_menu_callback, pattern="^reviews_menu$"),
        ],
    ))
    # ── Support/Warranty/Delivery Conversations ──
    from telegram.ext import ConversationHandler as _CH
    app.add_handler(_CH(allow_reentry=True, conversation_timeout=600,
        entry_points=[CallbackQueryHandler(st_new_callback, pattern="^st_new$")],
        states={400: [MessageHandler(filters.TEXT & ~filters.COMMAND, st_subject_received)],
                401: [MessageHandler(filters.TEXT & ~filters.COMMAND, st_desc_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    ))
    app.add_handler(_CH(allow_reentry=True, conversation_timeout=600,
        entry_points=[CallbackQueryHandler(wr_type_callback, pattern="^wr_type_")],
        states={402: [MessageHandler(filters.TEXT & ~filters.COMMAND, wr_reason_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    ))

    # 🆕 v137: Admin initiated direct user chat — user ID → first message/media
    app.add_handler(_CH(allow_reentry=True, conversation_timeout=900,
        entry_points=[CallbackQueryHandler(admin_direct_chat_start_callback, pattern="^admin_direct_chat$")],
        states={
            ADMIN_DIRECT_CHAT_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_direct_chat_uid_received)],
            ADMIN_DIRECT_CHAT_MSG: [MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL)
                & ~filters.COMMAND,
                adm_reply_received)],
        },
        fallbacks=[CommandHandler("cancel", _cancel_adm_reply)],
    ))

    # 🆕 v73: admin reply now accepts text/photo/video/document
    app.add_handler(_CH(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(adm_st_reply_callback, pattern="^adm_st_reply_")],
        states={450: [
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL)
                & ~filters.COMMAND,
                adm_reply_received),
        ]},
        fallbacks=[CommandHandler("cancel", _cancel_adm_reply)],
    ))
    # 🆕 v73: USER side reply with text/photo/video/document
    from handlers_support import (
        st_user_reply_callback, st_user_reply_received,
        adm_st_chat_callback, st_user_chat_callback,
    )
    app.add_handler(_CH(allow_reentry=True, conversation_timeout=900,
        entry_points=[CallbackQueryHandler(st_user_reply_callback, pattern=r"^st_user_reply_\d+$")],
        states={460: [
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL)
                & ~filters.COMMAND,
                st_user_reply_received),
        ]},
        fallbacks=[CommandHandler("cancel", _cancel_adm_reply)],
    ))
    # 🆕 v73: Chat history viewers (both sides)
    app.add_handler(CallbackQueryHandler(adm_st_chat_callback,    pattern=r"^adm_st_chat_\d+$"))
    app.add_handler(CallbackQueryHandler(st_user_chat_callback,   pattern=r"^st_user_chat_\d+$"))
    # 🆕 v158: user closes their own ticket via the 3h reminder button
    app.add_handler(CallbackQueryHandler(st_user_close_callback,  pattern=r"^st_uclose_\d+$"))
    app.add_handler(_CH(allow_reentry=True, conversation_timeout=900, 
        entry_points=[CallbackQueryHandler(adm_deliver_callback, pattern="^adm_deliver_")],
        states={403: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_delivery_text_received)]},
        fallbacks=[CommandHandler("cancel", _cancel_adm_deliver)],
    ))

    # 🔧 v124: payment-flow text runs BEFORE all ConversationHandlers so stale
    # conversation states can never swallow amounts/TXIDs/TIDs.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, payment_flow_text_handler), group=-80)

    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.VOICE | filters.Document.ALL, handle_media_router))
    # 🆕 v152: admin sends/forwards a POLL to the bot → rebroadcast to all users
    try:
        from telegram.ext import MessageHandler as _MH
        app.add_handler(_MH(filters.POLL, handle_admin_poll_message))
    except Exception:
        pass
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # ⭐ v161.25: Telegram Stars — pre-checkout + successful payment
    app.add_handler(PreCheckoutQueryHandler(stars_precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, stars_successful_payment))

    # 🆕 v148: Poll answers — users voting in broadcast polls
    try:
        from telegram.ext import PollAnswerHandler
        app.add_handler(PollAnswerHandler(handle_poll_answer))
    except Exception:
        try:
            app.add_handler(MessageHandler(filters.POLL_ANSWER, handle_poll_answer))
        except Exception:
            pass

    app.add_handler(CallbackQueryHandler(catch_all_callback))
    print("✅ Running!")

    # ════════════════════════════════════════════
    # 🌐 RENDER / WEBHOOK SUPPORT (v40)
    # ════════════════════════════════════════════
    # If RENDER env is set (Render.com), use webhook.
    # Otherwise run polling (local / VPS).

    RENDER_EXTERNAL = os.getenv("RENDER_EXTERNAL_URL", "").strip()
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
    PORT = int(os.getenv("PORT", "10000"))

    if RENDER_EXTERNAL or WEBHOOK_URL:
        # ── Webhook mode (for Render.com / Railway / Koyeb etc) ──
        # 🔧 BUG FIX: previously a raw HTTPServer was started on PORT *and*
        # PTB's start_webhook() was started on the SAME PORT, which crashed
        # with "Address already in use" on Render. PTB's own webhook server
        # binds the port and answers Render's health probe, so we use ONLY it.

        # Determine webhook URL
        if WEBHOOK_URL:
            webhook_url = WEBHOOK_URL.rstrip("/") + "/webhook"
        else:
            # Infer from Render's RENDER_EXTERNAL_URL
            ext_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
            if ext_url:
                webhook_url = ext_url.rstrip("/") + "/webhook"
            else:
                # fallback: cannot determine webhook URL
                print("⚠️ Cannot determine webhook URL. Set WEBHOOK_URL env var.")
                sys.exit(1)

        print(f"🔗 Setting webhook: {webhook_url}")
        print(f"🤖 Bot running via webhook on port {PORT}")

        # run_webhook() binds PORT, sets the webhook, and serves both the
        # Telegram updates (/webhook) and acts as the open port Render needs.
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=webhook_url,
            drop_pending_updates=True,
        )

    else:
        # Polling mode (Render Background Worker / local / VPS)
        #
        # 🔧 v136 CRASH FIX:
        # Do NOT run app.bot.get_me() on a temporary event loop before polling.
        # That binds PTB/httpx internals to a loop that is then closed, causing:
        #   RuntimeError("Event loop is closed")
        #   RuntimeWarning: Updater.start_polling was never awaited
        #
        # Also do NOT retry app.run_polling() with the same Application object
        # after an exception. If polling crashes, the __main__ supervisor below
        # creates a fresh Application and fresh event loop.
        print("🤖 Bot running via polling (Render Background Worker safe)")
        app.run_polling(drop_pending_updates=True, close_loop=False)


if __name__ == "__main__":
    # Render Worker safe supervisor: on transient Telegram/network startup
    # errors, rebuild the whole Application instead of reusing a possibly
    # closed event loop / half-started updater.
    import time as _time
    import logging as _logging
    try:
        from telegram.error import Conflict as _PTBConflict, NetworkError as _PTBNetworkError, TimedOut as _PTBTimedOut
    except Exception:  # compile/test fallback
        _PTBConflict = type("_PTBConflict", (Exception,), {})
        _PTBNetworkError = type("_PTBNetworkError", (Exception,), {})
        _PTBTimedOut = type("_PTBTimedOut", (Exception,), {})

    # 🆕 v161: Reseller API server — ProdSeller-compatible buyer API for
    # resellers (same process, binds Railway's PORT). Started ONCE here so
    # polling crash-restarts never stack a second server. Skipped in webhook
    # mode (webhook already binds PORT) and when RESELLER_API_ENABLED=0.
    try:
        _webhook_mode = bool((os.getenv("RENDER_EXTERNAL_URL") or os.getenv("WEBHOOK_URL") or "").strip())
        if not _webhook_mode and os.getenv("RESELLER_API_ENABLED", "1") != "0":
            try:
                from reseller_api import start_reseller_api_server
                _api_port = int(os.getenv("PORT") or os.getenv("RESELLER_API_PORT") or "8000")
                start_reseller_api_server(_api_port)
            except Exception as _api_err:
                print(f"⚠️ Reseller API server failed to start: {_api_err}")
    except Exception:
        pass

    while True:
        try:
            main()
            break  # graceful shutdown
        except _PTBConflict as _e:
            print(f"⚠️ Telegram polling conflict (another instance/webhook). Retrying fresh in 15s: {_e}")
            _time.sleep(15)
        except (_PTBNetworkError, _PTBTimedOut) as _e:
            print(f"⚠️ Telegram network error. Retrying fresh in 15s: {_e}")
            _time.sleep(15)
        except RuntimeError as _e:
            if "event loop is closed" in str(_e).lower():
                print("⚠️ Event loop was closed by previous polling attempt. Rebuilding fresh in 5s...")
                _time.sleep(5)
                continue
            raise
        except Exception as _e:
            _logging.exception("💥 Bot crashed; rebuilding fresh in 15s")
            _time.sleep(15)
# Force restart marker - Thu Aug 13 09:02:52 UTC 2026
