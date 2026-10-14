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
