# ============================================================
# FAITHFUL PTB ROUTER TEST — FULL journey:
# edit response → picker → custom emoji → type emoji
# (Edit-Response conversation stays active the whole time!)
# ============================================================
import os, sys, asyncio, json
os.environ['DB_PATH'] = '/tmp/live_test.db'
os.environ['BOT_TOKEN'] = '8826914364:AAHMuODKCwvYFB3qX5723-5LbTjRzhkEoms'
os.environ['ADMIN_ID'] = '7105782769'
os.environ['BYBIT_API_KEY'] = 'K'; os.environ['BYBIT_API_SECRET'] = 'S'
sys.path.insert(0, '/home/user/Bite_store_bot')

import telegram
from telegram.ext import (Application, CallbackQueryHandler, ConversationHandler,
                          MessageHandler, CommandHandler, filters)
from telegram.request import BaseRequest
from http import HTTPStatus

CALLS = []
class FakeRequest(BaseRequest):
    @property
    def read_timeout(self): return None
    async def initialize(self): pass
    async def shutdown(self): pass
    async def do_request(self, url, method='POST', request_data=None, **kw):
        name = url.rstrip('/').split('/')[-1]
        CALLS.append(name)
        if name == 'getMe':
            return HTTPStatus.OK, json.dumps({'ok': True, 'result': {'id': 8826914364, 'is_bot': True,
                'first_name': 'Bite Store', 'username': 'Bite_storee_bot'}}).encode()
        if name == 'sendMessage':
            return HTTPStatus.OK, json.dumps({'ok': True, 'result': {'message_id': 1001, 'date': 0,
                'chat': {'id': 7105782769, 'type': 'private'}, 'text': 'ok'}}).encode()
        return HTTPStatus.OK, json.dumps({'ok': True, 'result': True}).encode()

import handlers_admin as HA
from handlers_admin import (resp_react_callback, resp_react_set_callback,
                            resp_react_clear_callback, resp_react_prem_callback,
                            resp_react_custom_callback, resp_react_input_received,
                            resp_react_global_toggle_callback, edit_response_callback,
                            response_value_received, cancel_conversation,
                            EDIT_RESP_VALUE)

def build():
    app = (Application.builder().token(os.environ['BOT_TOKEN'])
           .request(FakeRequest()).get_updates_request(FakeRequest()).build())
    # ── bot.py order (v139.5: reaction conversation FIRST) ──
    # Reaction ConversationHandler FIRST (state 99 claims emoji text before
    # the still-active Edit Response conversation can swallow it)
    app.add_handler(ConversationHandler(
        allow_reentry=True, conversation_timeout=300,
        entry_points=[CallbackQueryHandler(resp_react_prem_callback, pattern=r"^resp_react_prem_"),
                      CallbackQueryHandler(resp_react_custom_callback, pattern=r"^resp_react_custom_")],
        states={99: [MessageHandler(filters.TEXT & ~filters.COMMAND, resp_react_input_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    ))
    # Edit Response conversation (line ~1303)
    app.add_handler(ConversationHandler(
        allow_reentry=True, conversation_timeout=900,
        entry_points=[CallbackQueryHandler(edit_response_callback, pattern="^editresp_")],
        states={EDIT_RESP_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, response_value_received)]},
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    ))
    # Reaction table (line ~1889)
    app.add_handler(CallbackQueryHandler(resp_react_set_callback,    pattern="^resp_react_set_"))
    app.add_handler(CallbackQueryHandler(resp_react_clear_callback,  pattern="^resp_react_clear_"))
    app.add_handler(CallbackQueryHandler(resp_react_callback,        pattern="^resp_react_(?!set_|clear_|prem_|custom_)"))
    app.add_handler(CallbackQueryHandler(resp_react_global_toggle_callback, pattern="^resp_react_global_toggle$"))
    # generic text handler last (like handle_text)
    async def generic_text(u, c):
        CALLS.append("GENERIC-TEXT:" + (u.message.text or ""))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generic_text))
    return app

def cb_update(app, data):
    upd = telegram.Update.de_json({"update_id": 1, "callback_query": {"id": "9", "chat_instance": "c",
        "from": {"id": 7105782769, "first_name": "A", "is_bot": False}, "data": data,
        "message": {"message_id": 500, "date": 0, "chat": {"id": 7105782769, "type": "private"},
                    "text": "old", "from": {"id": 7105782769, "first_name": "A", "is_bot": False}}}}, app.bot)
    return upd

def text_update(app, text, entities=None):
    msg = {"message_id": 501, "date": 0, "chat": {"id": 7105782769, "type": "private"},
           "from": {"id": 7105782769, "first_name": "A", "is_bot": False}, "text": text}
    if entities:
        msg["entities"] = entities
    upd = telegram.Update.de_json({"update_id": 2, "message": msg}, app.bot)
    return upd

async def main():
    from customization import get_reaction, set_reaction
    from database import get_connection, get_response
    # baseline welcome text
    conn = get_connection(); c = conn.cursor()
    welcome_before = c.execute("SELECT value FROM bot_responses WHERE key='welcome'").fetchone()[0]
    conn.close()

    set_reaction("welcome", "")
    app = build()
    async def _err(update, context):
        import traceback
        print("  [ERROR HANDLER] update_id:", update.update_id if update else None)
        traceback.print_exception(type(context.error), context.error, context.error.__traceback__)
    app.add_error_handler(_err)
    await app.initialize()

    # 1) Admin opens Edit Response for welcome (edit conversation ACTIVE)
    CALLS.clear()
    await app.process_update(cb_update(app, "editresp_welcome"))
    print("1) editresp_welcome →", CALLS[:4])
    assert "editMessageText" in CALLS, "edit panel should show"
    print("   ✅ edit panel open (edit conversation active)")

    # 2) Admin clicks ⚡ Set/Change Reaction → picker
    CALLS.clear()
    await app.process_update(cb_update(app, "resp_react_welcome"))
    print("2) resp_react_welcome →", CALLS[:4])
    assert "editMessageText" in CALLS
    print("   ✅ picker shown")

    # 3) Admin clicks 🖊️ Type custom emoji
    CALLS.clear()
    await app.process_update(cb_update(app, "resp_react_custom_welcome"))
    print("3) resp_react_custom_welcome →", CALLS[:4])
    assert "editMessageText" in CALLS, "custom prompt must show"
    print("   ✅ custom prompt shown (reaction conversation active state 99)")

    # 4) Admin types the emoji 🔥
    CALLS.clear()
    await app.process_update(text_update(app, "🔥"))
    print("4) type 🔥 →", CALLS[:6])
    assert "sendMessage" in CALLS, "must reply with confirmation"
    print("   ✅ confirmation reply sent")
    assert get_reaction("welcome") == "🔥", f"reaction={get_reaction('welcome')!r}"
    print("   ✅ reaction saved:", repr(get_reaction("welcome")))

    # 5) welcome text STILL intact
    conn = get_connection(); c = conn.cursor()
    welcome_after = c.execute("SELECT value FROM bot_responses WHERE key='welcome'").fetchone()[0]
    conn.close()
    assert welcome_after == welcome_before, "WELCOME OVERWRITTEN!"
    print("   ✅ welcome text untouched (", len(welcome_after), "chars )")

    # 6) premium path
    set_reaction("welcome", "")
    CALLS.clear()
    await app.process_update(cb_update(app, "resp_react_prem_welcome"))
    assert "editMessageText" in CALLS
    ent = {"type": "custom_emoji", "offset": 0, "length": 1, "custom_emoji_id": "5458672938212345678"}
    CALLS.clear()
    await app.process_update(text_update(app, "🔥", entities=[ent]))
    assert get_reaction("welcome") == "premium:5458672938212345678", get_reaction("welcome")
    print("6) premium path ✅ saved:", repr(get_reaction("welcome")))

    # 7) DEFAULT reaction applied to EVERY send via the guard
    from customization import (set_default_reaction, get_default_reaction,
                               reaction_enabled, set_reaction_enabled)
    set_reaction_enabled(True)   # copied DB has react_enabled=0
    set_default_reaction("🎉")
    from premium_emoji_guard import install as guard_install
    guard_install()
    CALLS.clear()
    # capture task exceptions so silent failures surface
    loop = asyncio.get_event_loop()
    def _exc_handler(loop, ctx):
        print("  [LOOP EXC]", ctx)
    loop.set_exception_handler(_exc_handler)
    # send a plain message through the PATCHED bot (guard auto-react)
    await app.bot.send_message(chat_id=7105782769, text="hello test")
    assert "sendMessage" in CALLS, "message must be sent"
    # guard schedules the reaction as a task → give it a tick
    await asyncio.sleep(0.6)
    print("   step7 CALLS:", CALLS)
    for t in asyncio.all_tasks():
        if t is not asyncio.current_task() and t.done():
            try:
                t.result()
            except Exception as e:
                print("   [TASK ERROR]", repr(e))
    assert "setMessageReaction" in CALLS, f"guard must auto-react, calls={CALLS}"
    print("7) ✅ GUARD auto-reacts to every send (setMessageReaction after sendMessage)")
    set_default_reaction("")

    await app.shutdown()
    print("\n🎉 FULL ROUTER JOURNEY PASS — custom + premium + GLOBAL auto-react, welcome safe")

asyncio.run(main())
