"""Gate A scenario suite (plan §4.0 / T3.8).

Every scenario runs as real, separate processes: a Hermes "session" process
(tests/e2e/hermes_session.py) that loads the plugin through Hermes's own
PluginManager and fires hooks through Hermes's own invoke_hook; then the real
``hermes minefield ...`` CLI in another process reads the result from disk.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("hermes_cli")
pytestmark = pytest.mark.gate_a

ROOT = Path(__file__).resolve().parents[2]
SESSION = Path(__file__).with_name("hermes_session.py")
DEAD = "http://127.0.0.1:9/v1"


@pytest.fixture(scope="module")
def home(tmp_path_factory):
    h = tmp_path_factory.mktemp("gate_a_home")
    (h / "plugins").mkdir()
    os.symlink(ROOT, h / "plugins" / "hermes-minefield")
    (h / "config.yaml").write_text(
        f"model:\n  default: test-model\n  base_url: {DEAD}\nplugins:\n  enabled: [hermes-minefield]\n",
        encoding="utf-8",
    )
    return h


def _env(home: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["HERMES_HOME"] = str(home)
    env.pop("MINEFIELD_SOURCE", None)
    return env


def session(home: Path, scenario: str, sid: str, n: int = 6) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(SESSION), scenario, sid, str(n)],
        env=_env(home),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def run_session(home: Path, scenario: str, sid: str, n: int = 6) -> None:
    p = session(home, scenario, sid, n)
    out, err = p.communicate(timeout=300)
    assert p.returncode == 0, f"session process failed:\n{out}\n{err}"


def hermes(home: Path, *args: str) -> subprocess.CompletedProcess:
    exe = shutil.which("hermes")
    cmd = [exe, *args] if exe else [sys.executable, "-m", "hermes_cli.main", *args]
    return subprocess.run(cmd, env=_env(home), capture_output=True, text=True, timeout=300)


def field(text: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}[=:]\s*(\S+)", text, re.M)
    assert m, f"{name} not in output:\n{text}"
    return m.group(1)


def wtf(home: Path, sid: str) -> tuple[int, str]:
    r = hermes(home, "minefield", "wtf", "10m", "--session", sid)
    return r.returncode, r.stdout + r.stderr


def test_normal_tool_use_is_expected_and_pass(home):
    run_session(home, "normal", "gate-normal", 6)
    rc, out = wtf(home, "gate-normal")
    assert field(out, "Classification") == "EXPECTED_BEHAVIOUR", out
    assert field(out, "Verdict") == "PASS", out
    assert field(out, "ACTUAL_EXECUTIONS") == "7"
    assert field(out, "TOOL_FAILURES") == "0"
    assert rc == 0


def test_intentional_tool_errors_are_failures(home):
    run_session(home, "errors", "gate-errors", 6)
    rc, out = wtf(home, "gate-errors")
    assert field(out, "TOOL_FAILURES") == "6", out
    assert field(out, "Classification") == "TOOL_BUG", out
    assert field(out, "Verdict") == "FAIL"
    assert rc == 1


def test_real_no_progress_loop_is_detected(home):
    run_session(home, "loop", "gate-loop", 12)
    rc, out = wtf(home, "gate-loop")
    assert field(out, "Classification") == "AGENT_TOOL_LOOP", out
    assert field(out, "Verdict") == "FAIL"
    assert rc == 1


def test_distinct_calls_at_loop_volume_are_not_a_loop(home):
    """F1 regression at the process level: 12 distinct reads used to be AGENT_TOOL_LOOP/HIGH."""
    run_session(home, "normal", "gate-distinct", 12)
    _, out = wtf(home, "gate-distinct")
    assert field(out, "Classification") != "AGENT_TOOL_LOOP", out


def test_dead_endpoint_is_unknown_and_not_cached(home):
    r = hermes(home, "minefield", "check")
    out = r.stdout + r.stderr
    assert field(out, "Verdict") == "UNKNOWN", out
    assert r.returncode == 3
    status = hermes(home, "minefield", "status")
    assert re.search(r"cache:\s+none", status.stdout), status.stdout


def test_two_concurrent_hermes_processes_lose_nothing(home):
    n = 300
    procs = [session(home, "normal", sid, n) for sid in ("gate-conc-a", "gate-conc-b")]
    for p in procs:
        out, err = p.communicate(timeout=300)
        assert p.returncode == 0, f"{out}\n{err}"
    for sid in ("gate-conc-a", "gate-conc-b"):
        _, out = wtf(home, sid)
        assert field(out, "ACTUAL_EXECUTIONS") == str(n + 1), out
        assert field(out, "Verdict") == "PASS", out


def test_empty_session_is_unknown_not_pass(home):
    rc, out = wtf(home, "gate-never-happened")
    assert field(out, "Verdict") == "UNKNOWN", out
    assert rc == 3
