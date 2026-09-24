"""Hermes compatibility contract (plan T0.5).

Checks the *installed* Hermes against tests/fixtures/hermes_hook_payloads.json:

1. every hook in plugin.yaml ``provides_hooks`` is a valid Hermes hook;
2. every kwarg the plugin reads is sent by *every* Hermes fire site for that
   hook (found by AST-walking the Hermes source, so no Hermes code runs);
3. the fixture payloads only use kwargs Hermes really sends (keeps the
   fixture honest).

Run against several Hermes refs in CI (the ``hermes-compat`` matrix). Skipped
when Hermes is not installed.
"""

from __future__ import annotations

import ast
import json
import warnings
from functools import cache
from pathlib import Path

import pytest
import yaml

hermes_cli = pytest.importorskip("hermes_cli")

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "hermes_hook_payloads.json").read_text())["hooks"]
HERMES_ROOT = Path(hermes_cli.__file__).resolve().parent.parent
_SKIP_PARTS = {"tests", "node_modules", ".venv", "website", "evals", "plugins"}


def _hook_name(key: str, spec: dict) -> str:
    return spec.get("hook", key)


def _fire_call_keys(call: ast.Call) -> set[str] | None:
    """Keyword names passed at a fire site; None for pure ``**kwargs`` forwarders."""
    keys: set[str] = set()
    for kw in call.keywords:
        if kw.arg is not None:
            keys.add(kw.arg)
            continue
        # ``**Helper(a, b, c).hook_kwargs()`` -> the positional Name args are the keys.
        inner = kw.value
        while isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
            inner = inner.func.value
        if isinstance(inner, ast.Call):
            keys.update(a.id for a in inner.args if isinstance(a, ast.Name))
        else:
            return None if not keys and len(call.keywords) == 1 else keys
    return keys


@cache
def fire_sites() -> dict[str, list[tuple[str, set[str]]]]:
    wanted = {_hook_name(k, v) for k, v in FIXTURE.items()}
    sites: dict[str, list[tuple[str, set[str]]]] = {h: [] for h in wanted}
    for path in HERMES_ROOT.rglob("*.py"):
        rel = path.relative_to(HERMES_ROOT)
        if _SKIP_PARTS & set(rel.parts):
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                warnings.simplefilter("ignore", DeprecationWarning)
                tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)):
                continue
            hook = node.args[0].value
            if hook not in sites or "invoke" not in ast.unparse(node.func):
                continue
            keys = _fire_call_keys(node)
            if keys:
                sites[hook].append((f"{rel}:{node.lineno}", keys))
    return sites


def test_provides_hooks_are_valid_hermes_hooks():
    from hermes_cli.plugins import VALID_HOOKS

    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    declared = set(manifest.get("provides_hooks") or [])
    assert declared, "plugin.yaml must declare provides_hooks"
    optional = {_hook_name(k, v) for k, v in FIXTURE.items() if v.get("optional_hook")}
    missing = declared - set(VALID_HOOKS)
    assert missing <= optional, sorted(missing - optional)


@pytest.mark.parametrize("key", sorted(FIXTURE))
def test_plugin_reads_are_sent_by_every_fire_site(key):
    spec = FIXTURE[key]
    if spec.get("static_check") is False:
        pytest.skip("hook is only forwarded via **kwargs; no static contract")
    hook = _hook_name(key, spec)
    sites = fire_sites()[hook]
    if not sites and spec.get("optional_hook"):
        pytest.skip(f"{hook} is optional and this Hermes version never fires it")
    assert sites, f"no fire site found for {hook} in {HERMES_ROOT}"
    for where, keys in sites:
        missing = set(spec["reads"]) - keys
        assert not missing, f"{hook} @ {where} no longer sends {sorted(missing)}"


@pytest.mark.parametrize("key", sorted(FIXTURE))
def test_fixture_payload_matches_real_kwargs(key):
    spec = FIXTURE[key]
    if spec.get("static_check") is False:
        pytest.skip("hook is only forwarded via **kwargs; no static contract")
    hook = _hook_name(key, spec)
    sites = fire_sites()[hook]
    if not sites and spec.get("optional_hook"):
        pytest.skip(f"{hook} is optional and this Hermes version never fires it")
    sent = set().union(*(keys for _, keys in sites))
    extra = set(spec["payload"]) - sent - set(spec.get("optional_reads", []))
    assert not extra, f"fixture for {hook} uses kwargs Hermes never sends: {sorted(extra)}"
