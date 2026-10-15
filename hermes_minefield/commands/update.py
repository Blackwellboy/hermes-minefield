"""``update``: which Minefield you have, what is newest, and updating it.

- On its own: local facts only, no network (plugin version and checkout, core version,
  trap count, the Python that imports the core).
- ``--check``: also asks PyPI and GitHub what is newest. Read-only; it names every host
  before contacting it.
- ``--yes``: updates. Terminal only (anyone in a gateway room can type slash commands, so
  chat can show and check but never install). Prints each command before running it:
  ``git pull --ff-only`` for a clean plugin checkout, then a package upgrade of the core
  in the Python that imports it. ``--from-main`` installs the core from GitHub ``main``
  (traps merged since the last PyPI release).
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

from ..version import __version__

CORE_DIST = "model-serving-minefield"
CORE_SPEC = "model-serving-minefield>=0.2.1,<0.3"
CORE_MAIN_SPEC = "git+https://github.com/Blackwellboy/model-serving-minefield@main"
PYPI_URL = "https://pypi.org/pypi/model-serving-minefield/json"
CORE_MAIN_REGISTRY_URL = "https://raw.githubusercontent.com/Blackwellboy/model-serving-minefield/main/dist/MINEFIELD_REGISTRY.min.json"
PLUGIN_MAIN_URL = "https://api.github.com/repos/Blackwellboy/hermes-minefield/commits/main"
PLUGIN_DIR = Path(__file__).resolve().parents[2]

CHAT_APPLY_REFUSED = (
    "Updating installs software, so it runs only from a terminal: hermes minefield update --yes\n"
    "(chat can show what you have and check what is newest: /minefield update --check)"
)


def _show(argv: list[str]) -> str:
    """A command line to print: shell-quoted, with the home directory shown as ``~``."""
    home = str(Path.home())
    out = []
    for arg in argv:
        q = shlex.quote(arg)
        if q == arg and (arg == home or arg.startswith(home + "/")):
            q = "~" + arg[len(home) :]
        out.append(q)
    return " ".join(out)


def _run(argv: list[str], timeout: float = 30) -> tuple[int, str]:
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, type(e).__name__
    return out.returncode, ((out.stdout or "") + (out.stderr or "")).strip()


def _plugin_local() -> dict[str, Any]:
    info: dict[str, Any] = {"version": __version__, "dir": str(PLUGIN_DIR), "git": False}
    if not (PLUGIN_DIR / ".git").exists() or not shutil.which("git"):
        return info
    rc, head = _run(["git", "-C", str(PLUGIN_DIR), "rev-parse", "HEAD"])
    if rc != 0:
        return info
    _, branch = _run(["git", "-C", str(PLUGIN_DIR), "rev-parse", "--abbrev-ref", "HEAD"])
    _, dirty = _run(["git", "-C", str(PLUGIN_DIR), "status", "--porcelain", "--untracked-files=no"])
    info.update(git=True, commit=head[:40], branch=branch, clean=not dirty)
    return info


PM_NOTE = (
    "Hermes manages this environment (`hermes pm`) and rebuilds it from PyPI when plugins "
    "change, holding back releases younger than 3 days (its exclude-newer quarantine); "
    "an install from --from-main or of a newer release lasts until that rebuild"
)


def _core_python() -> tuple[str, bool]:
    """The Python whose environment holds the imported core, and whether Hermes PM manages it.

    Under Hermes 0.22 the process runs a shared base interpreter and adds a per-plugin-set
    environment (``.../environments/<id>/venv``) to ``sys.path``; installing into
    ``sys.executable`` would change the shared interpreter, not the environment that loads.
    """
    try:
        import minefield  # type: ignore[import-not-found]

        here = Path(minefield.__file__).resolve()
    except Exception:
        return sys.executable, False
    for d in here.parents:
        if (d / "pyvenv.cfg").is_file():
            py = d / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if py.exists():
                return str(py), d.parent.parent.name == "environments"
            break
    return sys.executable, False


def _core_local() -> dict[str, Any]:
    python, managed = _core_python()
    info: dict[str, Any] = {"python": python, "hermes_pm": managed, "installed": False}
    try:
        info["version"] = importlib.metadata.version(CORE_DIST)
        info["installed"] = True
    except importlib.metadata.PackageNotFoundError:
        return info
    try:
        from minefield.registry import load_registry  # type: ignore[import-not-found]

        info["traps"] = len(load_registry().get("entries") or [])
    except Exception:  # an old or broken core still reports its version
        info["traps"] = None
    return info


def _get_json(url: str, timeout: float = 15) -> Any:
    req = urllib.request.Request(
        url, headers={"User-Agent": "hermes-minefield", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _remote() -> dict[str, Any]:
    """Newest versions. Never raises: a host that cannot be reached is reported as such."""
    out: dict[str, Any] = {}
    for key, url, pick in (
        ("core_pypi", PYPI_URL, lambda d: d["info"]["version"]),
        ("core_main_traps", CORE_MAIN_REGISTRY_URL, lambda d: int(d["canonical_trap_count"])),
        ("plugin_main", PLUGIN_MAIN_URL, lambda d: str(d["sha"])[:40]),
    ):
        try:
            out[key] = pick(_get_json(url))
        except Exception as e:
            out[key + "_error"] = type(e).__name__
    return out


def _vkey(v: str) -> tuple[int, ...]:
    """Release part of a version ("0.2.1+f4db58fb" -> (0, 2, 1)); enough to order PyPI releases."""
    head = v.split("+", 1)[0]
    parts: list[int] = []
    for p in head.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _core_command(spec: str, python: str) -> list[str] | None:
    """Upgrade ``spec`` in ``python``'s environment (uv if present, else that Python's pip)."""
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip", "install", "--upgrade", "--python", python, spec]
    if python != sys.executable or importlib.util.find_spec("pip") is not None:
        return [python, "-m", "pip", "install", "--upgrade", spec]
    return None


def _plan(plugin: dict[str, Any], core: dict[str, Any], from_main: bool) -> tuple[list[list[str]], list[str]]:
    steps: list[list[str]] = []
    notes: list[str] = []
    if plugin.get("git"):
        if plugin.get("clean"):
            steps.append(["git", "-C", plugin["dir"], "pull", "--ff-only"])
        else:
            notes.append("plugin checkout has local changes: not pulled (commit or stash them first)")
    else:
        notes.append("plugin is not a git checkout: reinstall it to update the plugin itself")
    python = core.get("python") or sys.executable
    cmd = _core_command(CORE_MAIN_SPEC if from_main else CORE_SPEC, python)
    if cmd:
        steps.append(cmd)
    else:
        notes.append(
            f'no pip or uv for {python}: install the core yourself with "{CORE_SPEC}" in that Python'
        )
    if core.get("hermes_pm"):
        notes.append(PM_NOTE)
    return steps, notes


def run_update(
    *,
    check: bool = False,
    yes: bool = False,
    from_main: bool = False,
    surface: str = "cli",
) -> dict[str, Any]:
    plugin = _plugin_local()
    core = _core_local()
    result: dict[str, Any] = {"ok": True, "plugin": plugin, "core": core}
    lines = ["Minefield update", ""]
    if plugin.get("git"):
        state = "clean" if plugin.get("clean") else "local changes"
        where = f"git checkout at {plugin['commit'][:7]} ({plugin.get('branch')}, {state})"
    else:
        where = "installed copy"
    lines.append(f"  plugin  hermes-minefield {plugin['version']}, {where}")
    if core["installed"]:
        traps = f", {core['traps']} traps" if core.get("traps") is not None else ""
        lines.append(f"  core    {CORE_DIST} {core['version']}{traps}")
    else:
        lines.append(f"  core    not installed in this Python ({sys.executable})")
    if core.get("hermes_pm"):
        lines.append("          (in a Hermes-managed plugin environment)")

    if check:
        lines += ["", "Asking pypi.org, raw.githubusercontent.com and api.github.com (read-only)..."]
        remote = _remote()
        result["remote"] = remote
        if "plugin_main" in remote and plugin.get("git"):
            same = plugin["commit"] == remote["plugin_main"]
            lines.append(
                f"  plugin  main is {remote['plugin_main'][:7]}: "
                + ("up to date" if same else "newer commits on main")
            )
        elif "plugin_main_error" in remote:
            lines.append(f"  plugin  could not reach GitHub ({remote['plugin_main_error']})")
        if "core_pypi" in remote:
            newer = core["installed"] and _vkey(remote["core_pypi"]) > _vkey(core["version"])
            msg = (
                "newer release available" if newer or not core["installed"] else "you have the latest release"
            )
            lines.append(f"  core    PyPI {remote['core_pypi']}: {msg}")
        elif "core_pypi_error" in remote:
            lines.append(f"  core    could not reach PyPI ({remote['core_pypi_error']})")
        if "core_main_traps" in remote:
            have = core.get("traps")
            extra = ""
            if have is not None and remote["core_main_traps"] > have:
                extra = f" ({remote['core_main_traps'] - have} not in yours; --from-main installs them)"
            lines.append(f"  traps   main has {remote['core_main_traps']}{extra}")

    steps, notes = _plan(plugin, core, from_main)
    result["plan"] = {"steps": steps, "notes": notes}
    if not yes:
        lines += ["", "To update (terminal only), this would run:"]
        lines += [f"  $ {_show(s)}" for s in steps] + [f"  - {n}" for n in notes]
        lines.append("Run: hermes minefield update --yes   (add --from-main for traps not yet released)")
        if not check:
            lines.append("Check what is newest first: hermes minefield update --check")
        result["text"] = "\n".join(lines)
        return result
    if surface != "cli":
        result.update(ok=False, text="\n".join(lines + ["", CHAT_APPLY_REFUSED]))
        return result

    lines.append("")
    ran: list[dict[str, Any]] = []
    for argv in steps:
        lines.append(f"$ {_show(argv)}")
        rc, output = _run(argv, timeout=600)
        ran.append({"argv": argv, "rc": rc})
        tail = "\n".join(output.splitlines()[-3:])
        if tail:
            lines.append("  " + tail.replace("\n", "\n  "))
        if rc != 0:
            lines.append(f"  failed (exit {rc}); stopped here")
            result["ok"] = False
            break
    lines += [f"  - {n}" for n in notes]
    result["ran"] = ran
    if result["ok"]:
        lines.append("")
        lines.append("Done. Restart Hermes so the running gateway and app load it.")
    result["text"] = "\n".join(lines)
    return result
