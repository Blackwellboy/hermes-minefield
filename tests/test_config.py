"""Canonical, validated plugin config (plan T2.2)."""

from __future__ import annotations

import pytest

from hermes_minefield.config import MinefieldPluginConfig, load_plugin_config


def entry(body: dict) -> dict:
    return {"plugins": {"entries": {"hermes-minefield": body}}}


@pytest.mark.parametrize(
    "cfg",
    [
        entry({"settings": {"lite_max_requests": 3}}),  # canonical
        entry({"config": {"lite_max_requests": 3}}),  # Hermes legacy subtree
        entry({"lite_max_requests": 3}),  # plugin legacy: direct entry
        {"minefield": {"lite_max_requests": 3}},  # plugin legacy: top-level block
    ],
)
def test_all_locations(cfg):
    assert MinefieldPluginConfig.from_mapping(cfg).lite_max_requests == 3


def test_settings_wins_over_direct_entry_keys():
    cfg = entry({"lite_max_requests": 1, "settings": {"lite_max_requests": 4}})
    assert MinefieldPluginConfig.from_mapping(cfg).lite_max_requests == 4


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        ("lite_max_requests", "abc", 5),
        ("lite_max_requests", 99, 5),  # clamped to the Lite ceiling
        ("lite_max_requests", -2, 0),
        ("lite_max_requests", True, 5),  # bools are not ints here
        ("recorder_retention_seconds", 5, 60),
        ("recorder_max_bytes", 10**12, 256 * 1024 * 1024),
        ("fingerprint_cache_ttl_days", None, 30),
    ],
)
def test_bad_values_fall_back_safely(key, raw, expected):
    cfg = MinefieldPluginConfig.from_mapping(entry({"settings": {key: raw}}))
    assert getattr(cfg, key) == expected


def test_privacy_defaults_are_off():
    cfg = MinefieldPluginConfig.from_mapping({})
    assert cfg.remote_dedupe is False
    assert cfg.allow_submit_from_chat is False
    assert cfg.expose_agent_tool is False


def test_bool_parsing():
    cfg = MinefieldPluginConfig.from_mapping(
        entry({"settings": {"remote_dedupe": "yes", "expose_agent_tool": 7}})
    )
    assert cfg.remote_dedupe is True
    assert cfg.expose_agent_tool is False


def test_auto_lite_prompt_is_retired():
    assert (
        MinefieldPluginConfig.from_mapping(entry({"settings": {"auto_lite": "prompt"}})).auto_lite == "false"
    )
    assert MinefieldPluginConfig.from_mapping(entry({"settings": {"auto_lite": True}})).auto_lite == "true"


def test_allowlist_filters_malformed_repos():
    cfg = MinefieldPluginConfig.from_mapping(
        entry({"settings": {"repo_allowlist": ["a/b", "nope", "x/y/z"]}})
    )
    assert cfg.repo_allowlist == ("a/b",)


def test_garbage_config_never_raises():
    assert load_plugin_config({"plugins": "garbage"}).lite_max_requests == 5
    assert load_plugin_config({"plugins": {"entries": {"hermes-minefield": ["x"]}}}).lite_max_requests == 5


def test_register_survives_bad_config(tmp_hermes_home):
    (tmp_hermes_home / "config.yaml").write_text(
        "plugins:\n  entries:\n    hermes-minefield:\n      settings:\n        lite_max_requests: abc\n"
        "        recorder_max_events: lots\n",
        encoding="utf-8",
    )
    from hermes_minefield.plugin import register

    class Ctx:
        def __getattr__(self, name):
            return lambda *a, **k: None

    register(Ctx())  # must not raise
