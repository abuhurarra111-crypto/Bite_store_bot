# ============================================================
# 🧪 BITE STORE — v141: button editor covers force-join + shape/padding
# + back buttons everywhere
# Run:  pytest _test_v141_editor.py -v
# ============================================================
import os, tempfile

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="v141_"), "t.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["BOT_TOKEN"] = "8826914364:AAHMuODKCwvYFB3qX5723-5LbTjRzhkEoms"
os.environ["ADMIN_ID"] = "7105782769"
os.environ["BYBIT_API_KEY"] = "K"
os.environ["BYBIT_API_SECRET"] = "S"

import database
from database import setup_database, migrate_all
setup_database(); migrate_all()

import customization as CZ


class TestForceJoinScreenInEditor:
    def test_screen_exists(self):
        assert "force_join_screen" in CZ.SCREEN_TREE

    def test_screen_in_main_menu_children(self):
        children = CZ.SCREEN_TREE["main_menu"]["children"]
        assert "force_join_screen" in children

    def test_screen_has_verify_and_targets(self):
        node = CZ.SCREEN_TREE["force_join_screen"]
        kinds = {b["kind"] for b in node["buttons"]}
        assert "fj_verify" in kinds
        assert "fj_targets" in kinds
        texts = [k for k, _l in node["texts"]]
        assert "fj_message" in texts
        assert "fj_verified_done" in texts

    def test_button_callback_for_fj(self):
        assert CZ._button_callback_for("x", "fj_verify") == "fj_vbtn"
        assert CZ._button_callback_for("x", "fj_targets") == "fj_panel"


class TestManageOneButtonKeyboard:
    def test_has_shape_padding_button(self):
        from keyboards import manage_one_button_keyboard
        kb = manage_one_button_keyboard("main_shop")
        labels = []
        for row in kb.inline_keyboard:
            for b in row:
                labels.append(b.text)
        assert any("Shape" in l or "Padding" in l for l in labels), labels
        assert any("Premium Emoji" in l for l in labels), labels
        assert any("Background Color" in l for l in labels), labels

    def test_has_back(self):
        from keyboards import manage_one_button_keyboard
        kb = manage_one_button_keyboard("main_shop")
        labels = []
        for row in kb.inline_keyboard:
            for b in row:
                labels.append(b.text)
        assert any("Back" in l for l in labels), labels


class TestForceJoinBackButtons:
    def test_add_prompt_has_back(self):
        src = open("ui_extras.py", encoding="utf-8").read()
        # fj_add prompt back button
        assert 'InlineKeyboardButton("🔙 Back to Force Join", callback_data="fj_panel")' in src
        # per-target prompts
        assert 'callback_data=f"fjm_{tid}"' in src

    def test_verify_editor_back(self):
        src = open("ui_extras.py", encoding="utf-8").read()
        assert 'InlineKeyboardButton("🔙 Back", callback_data="fj_vbtn")' in src

    def test_no_cancel_only_in_fj_add(self):
        src = open("ui_extras.py", encoding="utf-8").read()
        # the fj_add prompt should not be a bare Cancel button
        idx = src.find('context.user_data["fj_add_link"] = True')
        chunk = src[idx:idx+400]
        assert "🔙 Back" in chunk
        assert "❌ Cancel" not in chunk.split("text = (")[0]


class TestRegistryStyler:
    def test_reg_key_supported(self):
        from handlers_buttons import _sample_label_for, _friendly_for
        # reg_ keys must resolve (used by bs_edit_reg_<bid>)
        sample = _sample_label_for("reg_main_shop")
        assert sample  # non-empty
        assert _friendly_for("reg_main_shop")
