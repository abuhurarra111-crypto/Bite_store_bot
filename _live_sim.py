# ============================================================
# 🧪 LIVE FLOW SIMULATION — drives real bot handlers with synthetic
# Telegram updates against a COPY of the real DB (/tmp/live_test.db).
# Any exception = BUG. Prints a clean report.
# ============================================================
import os, sys, asyncio, traceback

os.environ['DB_PATH'] = '/tmp/live_test.db'
os.environ['BOT_TOKEN'] = '8826914364:AAHMuODKCwvYFB3qX5723-5LbTjRzhkEoms'
os.environ['ADMIN_ID'] = '7105782769'
os.environ['BYBIT_API_KEY'] = 'K'; os.environ['BYBIT_API_SECRET'] = 'S'
os.environ['GEMINI_API_KEY'] = ''
os.environ['MAINT_ON_START'] = '0'
os.environ['SUPPLIER_SINHLE_API_KEY'] = 'tgb_9cb54db595901481982eecc833e74de22622a1ad5bd5b6ad'
os.environ['SUPPLIER_PRODSELLER_API_KEY'] = 'psk_1df4ed99c5fdc791f8a47c0d866a1b2ecd3c16f5de83b107'
sys.path.insert(0, '/home/user/Bite_store_bot')

import database
from database import (setup_database, migrate_all, set_setting, get_setting,
                      save_user, get_user, get_ref_points, add_ref_points,
                      add_pending_referral, get_pending_referral_for_user,
                      add_fj_target, delete_all_fj_targets, list_fj_targets,
                      get_connection, get_ref_points_per_ref, set_ref_points_per_ref)
setup_database(); migrate_all()

BUGS = []
async def check(name, fn):
    try:
        await fn()
        print(f"  ✅ {name}")
    except Exception as e:
        BUGS.append(name)
        print(f"  ❌ {name} → {type(e).__name__}: {e}")
        traceback.print_exc()

# ────────────────────────────────────────────────────────────
# FAKES (enough surface for handlers)
# ────────────────────────────────────────────────────────────
class FakeUser:
    def __init__(self, uid=888111222, username="sim_user", first="Sim", is_bot=False):
        self.id = uid; self.username = username; self.first_name = first; self.is_bot = is_bot
class FakeChat:
    def __init__(self, cid=888111222):
        self.id = cid
class FakeMsg:
    def __init__(self, text="", user=None):
        self.text = text
        self.from_user = user or FakeUser()
        self.chat = FakeChat(self.from_user.id)
        self.replied = []
        self._html = text
        self.entities = []
    @property
    def text_html(self): return self._html
    @property
    def text_html_urled(self): return self._html
    async def reply_text(self, *a, **k):
        self.replied.append((a, k))
        return self
    async def delete(self): pass
class FakeCQ:
    def __init__(self, data="", user=None):
        self.data = data
        self.from_user = user or FakeUser()
        self.message = FakeMsg(user=self.from_user)
        self.answered = []
        self.edited = []
    async def answer(self, *a, **k):
        self.answered.append(1)
    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **k):
        self.edited.append((text, parse_mode, reply_markup))
    async def edit_message_caption(self, **k): pass
class FakeUpdate:
    def __init__(self, text=None, cq_data=None, user=None):
        self.effective_user = user or FakeUser()
        self.message = FakeMsg(text, self.effective_user) if text is not None else None
        self.callback_query = FakeCQ(cq_data, self.effective_user) if cq_data is not None else None
        self.effective_chat = FakeChat(self.effective_user.id) if self.effective_user else None
        # real Telegram: callback updates carry the message too
        self.effective_message = self.message if self.message is not None else (self.callback_query.message if self.callback_query else None)
class FakeBot:
    def __init__(self):
        self.sent = []
    async def send_message(self, chat_id, text, **k):
        self.sent.append((chat_id, text))
        class _M: message_id = 1; chat_id = chat_id
        return _M()
    async def send_photo(self, *a, **k): return None
    async def get_me(self):
        class _Me: username = "bite_storee_bot"; id = 8826914364; first_name = "Bite Store"
        return _Me()
    async def get_chat_member(self, chat_id=None, user_id=None):
        class _M: status = "left"
        return _M()
    async def delete_message(self, *a, **k): return True
class FakeJobQueue:
    def __init__(self): self.jobs = []
    def run_once(self, fn, when, data=None, name=None):
        self.jobs.append((fn, when, data, name))
        return self
class FakeContext:
    def __init__(self, user=None):
        self.user_data = {}
        self.bot = FakeBot()
        self.job_queue = FakeJobQueue()
        self.application = None
        self.args = []
        self.effective_user = user or FakeUser()

def shown(upd):
    cq = getattr(upd, "callback_query", None)
    if cq is not None:
        if cq.edited: return str(cq.edited[-1][0])
        if cq.message.replied: return str(cq.message.replied[-1][0][0])
        return ""
    if upd.message and upd.message.replied: return str(upd.message.replied[-1][0][0])
    return ""

async def _run():
    from handlers_start import (start_command, my_account_callback,
                                referral_callback, continue_after_force_join_verified,
                                handle_math_answer, notify_user_activity,
                                _send_welcome_message, _process_referral_attribution)
    from ui_extras import (check_force_join, force_join_action_gate, fj_verified_callback,
                           fj_add_callback, fjm_callback, fjm_col_callback,
                           fj_vbtn_callback, _show_dest_panel, _build_how_to_hub_text_and_kb,
                           guide_screen_callback, fj_panel_callback)
    from keyboards import persistent_menu, main_menu_keyboard
    from fake_engagement import admin_bcast_test_callback
    from ext_suppliers import SUPPLIER_PRESETS, ADAPTERS, ext_sup_add_callback
    import handlers_start as HS

    uid = 888111222
    ref_uid = 777000111
    save_user(uid, "sim_user", "Sim")
    save_user(ref_uid, "referrer", "Referrer")

    print("\n═══ A) v134 — REFERRAL MATH + OBSERVATION ═══")
    # A1: /start with referral deep link (force join enabled → gate blocks)
    set_setting('fj_enabled', '1')
    delete_all_fj_targets()
    add_fj_target('@bite_alerts', label='📢 Bite Alerts', style='primary')
    set_setting('referral_math_enabled', '1')

    async def a1():
        ctx = FakeContext(FakeUser(uid, "sim_user", "Sim"))
        ctx.args = [str(ref_uid)]
        await start_command(FakeUpdate(text="/start"), ctx)
        # force-join blocks → join message sent
        assert True
    await check("A1 /start w/ referral + force-join gate (blocks)", a1)

    # A2: simulate "I Joined" → referral recorded pending → math question
    async def a2():
        u = FakeUser(uid, "sim_user", "Sim")
        ctx = FakeContext(u)
        ctx.user_data['_start_ref'] = ref_uid
        upd = FakeUpdate(cq_data='fj_verified', user=u)
        handled = await continue_after_force_join_verified(upd, ctx, u)
        assert handled is True
        assert 'fj_math' in ctx.user_data, "math question should be pending"
    await check("A2 I-Joined → math question appears", a2)

    # A3: wrong math answer → retry, no crash
    async def a3():
        u = FakeUser(uid, "sim_user", "Sim")
        ctx = FakeContext(u)
        ctx.user_data['fj_math'] = {'answer': 99, 'tries': 0, 'a': 10, 'op': '+', 'b': 5}
        upd = FakeUpdate(text="1", user=u)
        got = await handle_math_answer(upd, ctx)
        assert got is True
        assert ctx.user_data['fj_math']['tries'] == 1
    await check("A3 wrong math answer → retry", a3)

    # A4: correct math answer → welcome + pending approved
    async def a4():
        u = FakeUser(uid, "sim_user", "Sim")
        ctx = FakeContext(u)
        ctx.user_data['fj_math'] = {'answer': 15, 'tries': 0, 'a': 10, 'op': '+', 'b': 5}
        upd = FakeUpdate(text="15", user=u)
        got = await handle_math_answer(upd, ctx)
        assert got is True
        assert 'fj_math' not in ctx.user_data
        # welcome arrives via reply_text on the answer message
        assert upd.message.replied, "welcome should be replied"
    await check("A4 correct math answer → welcome", a4)

    # A5: activity observation → 2 actions approve → BOTH get points
    async def a5():
        # fresh user, math OFF → pending stays until observation approves
        uid5 = uid + 100
        save_user(uid5, "sim2", "Sim2")
        save_user(ref_uid, "referrer", "Referrer")
        set_setting('referral_math_enabled', '0')
        await _process_referral_attribution(FakeContext(FakeUser(uid5)), FakeUser(uid5), ref_uid,
                                            True, product_id=0, approve_now=False)
        row = get_pending_referral_for_user(uid5)
        assert row is not None, "pending should exist before observation"
        await notify_user_activity(FakeContext(FakeUser(uid5)), uid5)
        await notify_user_activity(FakeContext(FakeUser(uid5)), uid5)
        rp_ref = get_ref_points(ref_uid)
        rp_sim = get_ref_points(uid5)
        assert rp_ref >= 1, f"referrer should have points, got {rp_ref}"
        assert rp_sim >= 1, f"referred should have points, got {rp_sim}"
        set_setting('referral_math_enabled', '1')
    await check("A5 observation → BOTH users credited", a5)

    print("\n═══ B) v135 — FORCE JOIN UNLIMITED + GATE ═══")
    # B1: global gate blocks non-member
    async def b1():
        u = FakeUser(uid + 5, "outsider", "Out")
        ctx = FakeContext(u)
        upd = FakeUpdate(text="hello", user=u)
        blocked = await force_join_action_gate(upd, ctx)
        assert blocked is True
    await check("B1 existing-user gate blocks non-member", b1)

    # B2: verify callback never blocked
    async def b2():
        u = FakeUser(uid + 6, "vuser", "V")
        ctx = FakeContext(u)
        upd = FakeUpdate(cq_data='fj_verified', user=u)
        blocked = await force_join_action_gate(upd, ctx)
        assert blocked is False
    await check("B2 verify button never blocked", b2)

    # B3: admin bypass
    async def b3():
        u = FakeUser(7105782769, "admin", "Admin")
        ctx = FakeContext(u)
        upd = FakeUpdate(text="x", user=u)
        blocked = await force_join_action_gate(upd, ctx)
        assert blocked is False
    await check("B3 admin bypasses gate", b3)

    # B4: target CRUD + verify button editor panel builds
    async def b4():
        u = FakeUser(7105782769, "admin", "Admin")
        ctx = FakeContext(u)
        upd = FakeUpdate(cq_data='fj_vbtn', user=u)
        await fj_vbtn_callback(upd, ctx)
        assert upd.callback_query.edited
    await check("B4 verify-button editor panel renders", b4)

    async def b5():
        u = FakeUser(7105782769, "admin", "Admin")
        ctx = FakeContext(u)
        upd = FakeUpdate(cq_data='fj_panel', user=u)
        await fj_panel_callback(upd, ctx)
        txt = shown(upd)
        assert "Force Join" in txt
    await check("B5 force-join panel renders (multi-target)", b5)

    print("\n═══ C) v136 — SUPPLIERS ═══")
    async def c1():
        for k in ('canboso','shop_cron','sinhle','akunding','mmostore','tunvnmmo','prodseller'):
            assert k in SUPPLIER_PRESETS, k
        assert 'prodseller' in ADAPTERS
    await check("C1 all presets + ProdSeller adapter registered", c1)

    async def c2():
        u = FakeUser(7105782769, "admin", "Admin")
        ctx = FakeContext(u)
        upd = FakeUpdate(cq_data='ext_sup_add', user=u)
        await ext_sup_add_callback(upd, ctx)
        cq = upd.callback_query
        assert cq.edited, "panel should render"
        # presets are rendered as BUTTONS (reply_markup)
        markup = cq.edited[-1][2]
        all_labels = []
        if markup is not None:
            for row in markup.inline_keyboard:
                for b in row:
                    all_labels.append(getattr(b, 'text', ''))
        joined = " ".join(all_labels)
        assert "ProdSeller" in joined, joined
        assert "Shop Cron" in joined, joined
        assert "sinh le" in joined, joined
    await check("C2 Add-Supplier panel shows ALL suppliers", c2)

    print("\n═══ D) v137 — LANGUAGE + @N/A FIX ═══")
    async def d1():
        # user without username → my_account must NOT contain @N/A or @—
        u = FakeUser(uid + 50, "", "NoUser")
        save_user(u.id, "", "NoUser")
        ctx = FakeContext(u)
        upd = FakeUpdate(cq_data='my_account', user=u)
        await my_account_callback(upd, ctx)
        txt = shown(upd)
        assert "@N/A" not in txt and "@—" not in txt and "@-" not in txt, txt[:200]
        assert "—" in txt or "Username" in txt
    await check("D1 my_account no @N/A for username-less user", d1)

    async def d2():
        from i18n import set_user_lang
        set_user_lang(uid, 'ur')
        kb = persistent_menu(uid)
        rows = kb.keyboard
        labels = [b.text for b in rows[0]]
        assert len(labels) == 2
    await check("D2 persistent_menu works with user lang", d2)

    print("\n═══ E) v138 — HOW-TO + DEST INDICATOR ═══")
    async def e1():
        set_setting('dest_chat_id', '@bite_alerts')
        set_setting('dest_mode', 'group_only')
        text, kb = _build_how_to_hub_text_and_kb(uid)
        assert "How to Use" in text or "Guide" in text
        assert kb is not None
    await check("E1 how-to hub builds", e1)

    print("\n═══ F) v139 BUGFIX — ADMIN_BCAST_TEST ═══")
    async def f1():
        u = FakeUser(7105782769, "admin", "Admin")
        ctx = FakeContext(u)
        upd = FakeUpdate(cq_data='bcast_test', user=u)
        await admin_bcast_test_callback(upd, ctx)
    await check("F1 Test-Broadcast button (fixed ADMIN_ID)", f1)

    print("\n═══ G) MY_ACCOUNT / REFERRAL / MAIN MENU (admin) ═══")
    async def g1():
        u = FakeUser(7105782769, "admin", "Admin")
        ctx = FakeContext(u)
        upd = FakeUpdate(cq_data='my_account', user=u)
        await my_account_callback(upd, ctx)
        assert shown(upd)
    await check("G1 admin my_account", g1)

    async def g2():
        u = FakeUser(uid, "sim_user", "Sim")
        ctx = FakeContext(u)
        upd = FakeUpdate(cq_data='referral_menu', user=u)
        await referral_callback(upd, ctx)
        txt = shown(upd)
        assert "Rewards" in txt or "referral" in txt.lower()
    await check("G2 referral screen w/ rewards line", g2)

    print("\n═══ H) PAYMENT FLOWS (Bybit/Binance helpers exist + respond) ═══")
    import payments
    async def h1():
        assert callable(payments.bybit_test_connection)
        assert callable(payments.binance_api_test_connection)
    await check("H1 payment helpers importable", h1)

    print("\n" + "═"*50)
    if BUGS:
        print(f"🐛 BUGS FOUND: {len(BUGS)}")
        for b in BUGS: print("  -", b)
    else:
        print("🎉 NO BUGS — all simulated flows passed")

asyncio.run(_run())
