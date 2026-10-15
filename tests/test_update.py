"""`update`: local facts offline, read-only remote check, install only from a terminal;
and the `gh auth login` fallback for submissions."""

from __future__ import annotations

import subprocess
import sys

import pytest

from hermes_minefield.commands import update as U
from hermes_minefield.commands.dispatch import slash_result
from hermes_minefield.issues import github_client as G


@pytest.fixture()
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("update touched the network without --check")

    monkeypatch.setattr(U.urllib.request, "urlopen", boom)


@pytest.fixture()
def git_checkout(monkeypatch):
    monkeypatch.setattr(
        U,
        "_plugin_local",
        lambda: {
            "version": "0.2.0",
            "dir": "/plug",
            "git": True,
            "commit": "a" * 40,
            "branch": "main",
            "clean": True,
        },
    )
    monkeypatch.setattr(
        U,
        "_core_local",
        lambda: {"python": sys.executable, "installed": True, "version": "0.2.1", "traps": 159},
    )


@pytest.fixture()
def recorded_runs(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(argv, timeout=30):
        calls.append(list(argv))
        return 0, "ok"

    monkeypatch.setattr(U, "_run", fake_run)
    return calls


def test_default_is_offline_and_shows_the_plan(tmp_hermes_home, no_network, git_checkout, recorded_runs):
    out = slash_result("9")
    assert out["ok"] is True
    assert "core    model-serving-minefield 0.2.1, 159 traps" in out["text"]
    assert "git -C /plug pull --ff-only" in out["text"]
    assert "hermes minefield update --yes" in out["text"]
    # pasteable: the version range is quoted, so "<" is not a shell redirect
    assert "'model-serving-minefield>=0.2.1,<0.3'" in out["text"]
    assert recorded_runs == []  # nothing ran


def test_check_reports_newer_release_and_unreleased_traps(tmp_hermes_home, git_checkout, monkeypatch):
    monkeypatch.setattr(
        U, "_remote", lambda: {"core_pypi": "0.2.2", "core_main_traps": 166, "plugin_main": "b" * 40}
    )
    out = slash_result("update --check")
    assert "PyPI 0.2.2: newer release available" in out["text"]
    assert "main has 166 (7 not in yours; --from-main installs them)" in out["text"]
    assert "newer commits on main" in out["text"]


def test_check_says_up_to_date(tmp_hermes_home, git_checkout, monkeypatch):
    monkeypatch.setattr(
        U, "_remote", lambda: {"core_pypi": "0.2.1", "core_main_traps": 159, "plugin_main": "a" * 40}
    )
    out = slash_result("update --check")
    assert "you have the latest release" in out["text"]
    assert "main is aaaaaaa: up to date" in out["text"]
    assert "not in yours" not in out["text"]


def test_unreachable_hosts_are_reported_not_raised(tmp_hermes_home, git_checkout, monkeypatch):
    def down(url, timeout=15):
        raise OSError("down")

    monkeypatch.setattr(U, "_get_json", down)
    out = slash_result("update --check")
    assert out["ok"] is True
    assert "could not reach PyPI (OSError)" in out["text"]
    assert "could not reach GitHub (OSError)" in out["text"]


def test_chat_never_installs(tmp_hermes_home, git_checkout, recorded_runs):
    out = slash_result("9 --yes")
    assert out["ok"] is False
    assert "only from a terminal" in out["text"]
    assert recorded_runs == []


def test_terminal_yes_pulls_then_upgrades_the_core_in_this_python(git_checkout, recorded_runs):
    out = U.run_update(yes=True, surface="cli")
    assert out["ok"] is True
    assert recorded_runs[0] == ["git", "-C", "/plug", "pull", "--ff-only"]
    core = recorded_runs[1]
    assert U.CORE_SPEC in core and "--upgrade" in core
    assert sys.executable in core
    assert "Restart Hermes" in out["text"]


def test_from_main_installs_the_github_main_core(git_checkout, recorded_runs):
    U.run_update(yes=True, from_main=True, surface="cli")
    assert U.CORE_MAIN_SPEC in recorded_runs[1]


def test_dirty_checkout_is_not_pulled(monkeypatch, recorded_runs):
    monkeypatch.setattr(
        U,
        "_plugin_local",
        lambda: {
            "version": "0.2.0",
            "dir": "/plug",
            "git": True,
            "commit": "a" * 40,
            "branch": "main",
            "clean": False,
        },
    )
    monkeypatch.setattr(
        U,
        "_core_local",
        lambda: {"python": sys.executable, "installed": True, "version": "0.2.1", "traps": 159},
    )
    out = U.run_update(yes=True, surface="cli")
    assert all(c[:1] != ["git"] for c in recorded_runs)
    assert "local changes: not pulled" in out["text"]


def test_a_failed_step_stops_the_run(git_checkout, monkeypatch):
    calls = []

    def fail(argv, timeout=30):
        calls.append(argv)
        return 1, "error: cannot fast-forward"

    monkeypatch.setattr(U, "_run", fail)
    out = U.run_update(yes=True, surface="cli")
    assert out["ok"] is False and len(calls) == 1
    assert "failed (exit 1); stopped here" in out["text"]


def test_printed_commands_show_home_as_tilde_and_stay_quoted(monkeypatch):
    monkeypatch.setattr(U.Path, "home", staticmethod(lambda: U.Path("/home/someone")))
    line = U._show(
        [
            "/home/someone/.local/bin/uv",
            "pip",
            "install",
            "--python",
            "/home/someone/env/bin/python",
            "pkg>=1,<2",
        ]
    )
    assert line == "~/.local/bin/uv pip install --python ~/env/bin/python 'pkg>=1,<2'"
    assert U._show(["/home/someone x/y"]) == "'/home/someone x/y'"  # quoted tokens keep the real path


def test_version_ordering_ignores_local_labels():
    assert U._vkey("0.2.1+f4db58fb") == (0, 2, 1)
    assert U._vkey("0.2.2") > U._vkey("0.2.1+f4db58fb")
    assert not U._vkey("0.2.1") > U._vkey("0.2.1+f4db58fb")


# --- gh auth login fallback --------------------------------------------------------


def test_env_token_wins_over_gh(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setattr(G, "_gh_cli_token", lambda: pytest.fail("gh must not be asked"))
    assert G.github_token() == "env-token"


def test_gh_login_is_used_when_no_env_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(G, "_gh_cli_token", lambda: "gh-token")
    assert G.github_token() == "gh-token"


# conftest patches _gh_cli_token out for every test; keep the real one (bound at import,
# before any fixture runs) to exercise it with a fake `gh`.
REAL_GH_HELPER = G._gh_cli_token


def _real_gh_helper(monkeypatch, *, which, run):
    monkeypatch.setattr(G.shutil, "which", which)
    monkeypatch.setattr(G.subprocess, "run", run)
    return REAL_GH_HELPER


def test_gh_helper_reads_auth_token(monkeypatch):
    seen = {}

    def run(argv, **kw):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="gho_abc123\n", stderr="")

    helper = _real_gh_helper(monkeypatch, which=lambda name: "/usr/bin/gh", run=run)
    assert helper() == "gho_abc123"
    assert seen["argv"] == ["/usr/bin/gh", "auth", "token"]


@pytest.mark.parametrize(
    "which,rc,stdout",
    [
        (lambda n: None, 0, "x"),
        (lambda n: "/usr/bin/gh", 1, ""),
        (lambda n: "/usr/bin/gh", 0, "not logged in"),
    ],
)
def test_gh_helper_returns_none_when_unusable(monkeypatch, which, rc, stdout):
    helper = _real_gh_helper(
        monkeypatch,
        which=which,
        run=lambda argv, **kw: subprocess.CompletedProcess(argv, rc, stdout=stdout, stderr=""),
    )
    assert helper() is None


def test_missing_login_tells_the_user_how_to_sign_in(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    res = G.submit_issue(
        repo="o/r",
        title="t",
        body="b",
        allowlist=["o/r"],
        user_selected_repo=False,
        cli_approve=True,
        dry_run=False,
    )
    assert res.error == "missing_github_token"
    assert "gh auth login" in G.NO_TOKEN_HINT


# --- the core lives in a Hermes-managed environment, not in sys.executable ------------


def _fake_core_at(monkeypatch, tmp_path, parts):
    import types

    venv = tmp_path.joinpath(*parts)
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /base\n", encoding="utf-8")
    (venv / "bin" / "python").write_text("", encoding="utf-8")
    pkg = venv / "lib" / "python3.14" / "site-packages" / "minefield"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "minefield", types.SimpleNamespace(__file__=str(pkg / "__init__.py")))
    return venv


def test_core_python_finds_the_hermes_managed_environment(monkeypatch, tmp_path):
    venv = _fake_core_at(monkeypatch, tmp_path, ["installs", "x", "environments", "abc123", "venv"])
    python, managed = U._core_python()
    assert python == str(venv / "bin" / "python") and python != sys.executable
    assert managed is True


def test_core_python_in_a_plain_venv_is_not_managed(monkeypatch, tmp_path):
    venv = _fake_core_at(monkeypatch, tmp_path, ["myproject", ".venv"])
    assert U._core_python() == (str(venv / "bin" / "python"), False)


def test_plan_installs_into_the_core_environment_and_says_hermes_manages_it(monkeypatch):
    core = {"python": "/envs/abc/venv/bin/python", "hermes_pm": True, "installed": True, "version": "0.2.1"}
    plugin = {"version": "0.2.0", "dir": "/plug", "git": False}
    steps, notes = U._plan(plugin, core, from_main=True)
    assert steps and "/envs/abc/venv/bin/python" in steps[-1] and U.CORE_MAIN_SPEC in steps[-1]
    assert sys.executable not in steps[-1]
    assert U.PM_NOTE in notes
