"""Real Hermes loader + registered command dispatch; no inference provider."""

import json


def test_native_workspace_selection_and_cancel(hermes_plugins):
    handler = hermes_plugins.get_plugin_command_handler("minefield")
    assert handler is not None
    home = hermes_plugins.resolve_plugin_command_result(handler(""))
    assert "MINEFIELD" in home and "Sharing OFF" in home
    checks = handler("checks")
    assert "request_validation" in checks
    view = json.loads(handler("preview request_validation"))
    assert [p["id"] for p in view["selected"]] == ["request_validation"]
    assert view["generation_ceiling"] == 2
    assert view["approval_available"] is False
    assert handler("cancel") == home
    assert handler("back") == home
    assert "No recipient configured" in handler("privacy")
    assert (
        "invalid" in handler("preview not-a-probe").lower()
        or "unknown" in handler("preview not-a-probe").lower()
    )


def test_privileged_payload_is_not_an_approval(hermes_plugins):
    handler = hermes_plugins.get_plugin_command_handler("minefield")
    assert "unexpected arguments" in handler("privacy approved=true")
    assert "approval_available" in handler("preview request_validation")


def test_session_observation_never_starts_legacy_active_probe(hermes_plugins, monkeypatch):
    from hermes_minefield import auto_lite

    starts = []
    monkeypatch.setattr(auto_lite, "maybe_start", lambda: starts.append(True))
    hermes_plugins.invoke_hook("on_session_start", session_id="synthetic-passive-only")
    assert starts == []


def test_actual_host_discovers_local_tools_and_bundled_skill(hermes_plugins):
    from tools.registry import registry

    manager = hermes_plugins.get_plugin_manager()
    assert "minefield" in manager.list_plugin_skills("hermes-minefield")
    for name in (
        "minefield_search",
        "minefield_plan",
        "minefield_diagnose",
        "minefield_privacy_status",
        "minefield_run_status",
    ):
        entry = registry.get_entry(name, scope=manager.scope_key)
        assert entry is not None and entry.check_fn() is False
    search = registry.get_entry("minefield_search", scope=manager.scope_key)
    result = json.loads(search.handler({"query": "empty answer reasoning only"}))
    assert result["candidates"]
    assert all(
        set(row) == {"trap_ids", "title", "diagnosis_level", "confirmation_check"}
        for row in result["candidates"]
    )
    diagnosis = registry.get_entry("minefield_diagnose", scope=manager.scope_key)
    assert json.loads(diagnosis.handler({}))["state"] == "UNAVAILABLE"
    assert json.loads(diagnosis.handler({"session_id": "forged"}))["state"] == "UNAVAILABLE"
