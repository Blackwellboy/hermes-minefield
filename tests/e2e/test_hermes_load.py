"""The plugin loads in real Hermes and registers what plugin.yaml declares."""

from __future__ import annotations

import yaml

from .conftest import ROOT


def test_plugin_loads_enabled_without_error(hermes_plugins):
    loaded = hermes_plugins.get_plugin_manager()._plugins.get("hermes-minefield")
    assert loaded is not None, "hermes-minefield was not discovered"
    assert loaded.error is None, loaded.error
    assert loaded.enabled is True


def test_declared_hooks_are_registered(hermes_plugins):
    declared = set(yaml.safe_load((ROOT / "plugin.yaml").read_text())["provides_hooks"])
    from hermes_cli.plugins import VALID_HOOKS

    for hook in declared & set(VALID_HOOKS):  # optional newer hooks are skipped on older Hermes
        assert hermes_plugins.has_hook(hook), f"{hook} declared but not registered"


def test_contract_payloads_replayed_through_hermes(hermes_plugins, hermes_home):
    """Fire every fixture payload through Hermes's own invoke_hook, then read what
    the plugin persisted (works whatever module name Hermes loaded it under)."""
    import json
    import time

    from hermes_minefield.recorder.store import load_recent_persisted_events

    fixture = json.loads((ROOT / "tests" / "fixtures" / "hermes_hook_payloads.json").read_text())["hooks"]
    for key, spec in fixture.items():
        results = hermes_plugins.invoke_hook(spec.get("hook", key), **spec["payload"])
        # pre_llm_call results would be injected into the user's prompt.
        assert all(r is None for r in results), f"{key} returned {results!r}"
    hermes_plugins.invoke_hook("on_session_end", session_id="sess-1", completed=True, interrupted=False)

    # Persistence is asynchronous (the flusher thread writes every ~2s, or
    # when on_session_end requests it), exactly as a separate wtf process sees it.
    wanted = {"tool.requested", "tool.executed", "tool.failed", "api.response", "api.error"}
    deadline = time.time() + 10
    while True:
        events = load_recent_persisted_events(since_seconds=600)
        types = {e.type for e in events}
        if wanted <= types or time.time() > deadline:
            break
        time.sleep(0.1)
    assert wanted <= types
    failed = [e for e in events if e.type == "tool.failed"]
    assert failed and failed[0].error_class == "tool_error"
    raw = "".join(p.read_text() for p in (hermes_home / "minefield" / "recorder").glob("*.jsonl"))
    assert "SENTINEL" not in raw, "persisted recorder leaked private fixture content"
    assert json.dumps([e.to_dict() for e in events])


def test_agent_tool_registered_but_hidden_by_default(hermes_plugins):
    from tools.registry import registry

    manager = hermes_plugins.get_plugin_manager()
    assert "minefield_recent_incident" in manager._plugin_tool_names
    entry = registry.get_entry("minefield_recent_incident", scope=manager.scope_key)
    assert entry is not None and entry.check_fn() is False  # expose_agent_tool defaults to false
