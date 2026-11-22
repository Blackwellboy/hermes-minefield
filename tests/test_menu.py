"""The numbered /minefield menu, and the guide / scan commands behind it."""

from __future__ import annotations

import pytest

from hermes_minefield import verdict as V
from hermes_minefield.commands import menu
from hermes_minefield.commands.dispatch import _slash_parser, handle_slash, slash_result


def test_bare_slash_shows_every_item_with_what_it_touches(tmp_hermes_home):
    text = handle_slash("")
    for item in menu.MENU:
        assert f"  {item.key}  {item.title}   (/minefield {item.command})" in text
        assert item.touches in text
    assert "/minefield help" in text


def test_keys_are_one_to_n_and_every_number_is_a_real_subcommand():
    assert [i.key for i in menu.MENU] == [str(n) for n in range(1, len(menu.MENU) + 1)]
    parser = _slash_parser()
    for item in menu.MENU:
        args = parser.parse_args(menu.translate([item.key]))
        assert args.minefield_command == item.command


def test_numbers_pass_their_arguments_through():
    assert menu.translate(["3", "blank", "replies"]) == ["guide", "blank", "replies"]
    assert menu.translate(["5", "--yes"]) == ["doctor", "--yes"]
    assert menu.translate(["status"]) == ["status"]
    assert menu.translate([]) == []


def test_numbers_keep_every_guard(tmp_hermes_home):
    out = slash_result("1 --base-url http://203.0.113.9:8000/v1")
    assert out["ok"] is False and "CLI-only" in out["text"]
    out = slash_result("5")  # no endpoint configured, no --yes: nothing runs
    assert out["verdict"] == V.UNKNOWN


def test_help_lists_commands(tmp_hermes_home):
    assert "/minefield guide" in handle_slash("help")


def test_guide_matches_the_registry(tmp_hermes_home):
    pytest.importorskip("minefield.render")
    out = slash_result("3 streaming replies are blank")
    assert out["ok"] is True
    assert "Trap 23" in out["text"]
    assert "\x1b[" not in out["text"]  # no terminal colour codes in chat
    assert "verdict" not in out  # a lookup is not a test of this machine


def test_guide_without_words_explains(tmp_hermes_home):
    out = slash_result("guide")
    assert out["ok"] is False and "say what you are seeing" in out["text"]


def test_scan_from_chat_reads_only_the_hermes_config(tmp_hermes_home):
    pytest.importorskip("minefield.scan")
    out = slash_result("4 /etc")
    assert out["ok"] is False and "CLI-only" in out["text"]
    (tmp_hermes_home / "config.yaml").write_text("agent:\n  reasoning_effort: high\n", encoding="utf-8")
    out = slash_result("4")
    assert out["ok"] is True
    assert out["scanned"] and out["scanned"][0].endswith("config.yaml")
    assert "\x1b[" not in out["text"]


def test_scan_with_nothing_readable_is_unknown(tmp_hermes_home):
    pytest.importorskip("minefield.scan")
    out = slash_result("scan")  # tmp home has no config.yaml
    assert out["verdict"] == V.UNKNOWN


def test_an_older_core_gets_an_upgrade_hint_not_an_internal_error(tmp_hermes_home, monkeypatch):
    import sys

    pytest.importorskip("minefield")
    monkeypatch.setitem(sys.modules, "minefield.scan", None)
    monkeypatch.setitem(sys.modules, "minefield.render", None)
    for cmd in ("4", "3 blank replies"):
        out = slash_result(cmd)
        assert out["verdict"] == V.UNKNOWN, cmd
        assert "0.2.1 or newer" in out["text"], cmd


# --- a bare /minefield asks where Hermes can ask (ctx.ask_choice) --------------


class _Picker:
    """A scripted ``ctx.ask_choice``: records every question, answers them in order, then None."""

    def __init__(self, *answers: str | None) -> None:
        self.answers = list(answers)
        self.asked: list[tuple[str, list]] = []

    def __call__(self, question: str, choices: list) -> str | None:
        self.asked.append((question, choices))
        return self.answers.pop(0) if self.answers else None


def test_bare_slash_asks_with_every_item_and_what_it_touches(tmp_hermes_home):
    ask = _Picker(None)
    text = handle_slash("", ask=ask)
    assert len(ask.asked) == 1
    question, choices = ask.asked[0]
    assert question == menu.QUESTION
    assert [c["value"] for c in choices] == [item.key for item in menu.MENU] + ["help"]
    for item, choice in zip(menu.MENU, choices, strict=False):
        assert item.title in choice["label"]
        assert item.touches in choice["description"]
    assert text == menu.render()  # nothing picked: the numbered list, as before


def test_no_picker_dismissed_or_unknown_answer_shows_the_list(tmp_hermes_home):
    assert handle_slash("") == menu.render()
    assert handle_slash("", ask=None) == menu.render()
    assert handle_slash("", ask=_Picker(None)) == menu.render()
    assert handle_slash("", ask=_Picker("nope")) == menu.render()
    assert handle_slash("menu", ask=_Picker("6")) == menu.render()  # `menu` always lists


def test_a_pick_runs_the_item_exactly_like_its_number(tmp_hermes_home):
    (tmp_hermes_home / "config.yaml").write_text(
        "model:\n  default: test\n  base_url: http://127.0.0.1:9/v1\n", encoding="utf-8"
    )
    assert handle_slash("", ask=_Picker("6")) == handle_slash("6")
    assert handle_slash("", ask=_Picker("help")) == handle_slash("help")


def test_a_symptom_lookup_needs_words_so_its_pick_says_what_to_type(tmp_hermes_home):
    text = handle_slash("", ask=_Picker("3"))
    assert "/minefield 3 " in text
    assert "say what you are seeing" in text.lower()


def test_the_doctor_pick_asks_again_and_sends_nothing_unless_told_to(tmp_hermes_home, monkeypatch):
    runs: list[dict] = []
    monkeypatch.setattr(
        "hermes_minefield.commands.dispatch.run_doctor",
        lambda **kw: runs.append(kw) or {"ok": True, "text": "doctor ran"},
    )
    declined = _Picker("5", "cancel")
    assert handle_slash("", ask=declined) == menu.CANCELLED
    assert declined.asked[1][0] == menu.DOCTOR_QUESTION
    assert "dozens of requests" in menu.DOCTOR_QUESTION
    assert handle_slash("", ask=_Picker("5")) == menu.CANCELLED  # question dismissed
    assert runs == []
    assert handle_slash("", ask=_Picker("5", "run")) == "doctor ran"
    assert runs and runs[-1]["yes"] is True


def test_a_broken_picker_never_reaches_the_chat(tmp_hermes_home):
    def boom(question, choices):
        raise RuntimeError("picker down")

    assert handle_slash("", ask=boom) == menu.render()


class _Ctx:
    """The parts of Hermes's PluginContext that register() touches."""

    plugin_id = "hermes-minefield"

    def __init__(self, *, can_ask: bool) -> None:
        self.commands: dict[str, object] = {}
        self.picks: list[str] = []
        if can_ask:
            self.ask_choice = lambda question, choices: self.picks.append(question) or "help"

    def register_cli_command(self, **kw):
        pass

    def register_command(self, name, handler, **kw):
        self.commands[name] = handler

    def register_hook(self, name, callback):
        pass

    def register_tool(self, **kw):
        pass

    def on_unload(self, callback):
        pass


@pytest.mark.parametrize("can_ask", [True, False])
def test_register_wires_ask_choice_when_this_hermes_has_it(tmp_hermes_home, fresh_recorder, can_ask):
    from hermes_minefield.config import set_plugin_id
    from hermes_minefield.plugin import register

    (tmp_hermes_home / "config.yaml").write_text(
        "model:\n  default: test\n  base_url: http://127.0.0.1:9/v1\n", encoding="utf-8"
    )
    ctx = _Ctx(can_ask=can_ask)
    try:
        register(ctx)
        handler = ctx.commands["minefield"]
        text = handler("")  # Hermes calls a one-argument handler with raw_args only
        if can_ask:
            assert ctx.picks == [menu.QUESTION]
            assert text == handle_slash("help")
        else:
            assert text == menu.render()
        assert handler("6").startswith("Minefield status")  # arguments bypass the picker
    finally:
        set_plugin_id(None)
