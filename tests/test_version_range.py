"""plugin.yaml ``requires_hermes`` and the CI matrix that proves it must agree.

Hermes 0.22+ refuses to load a plugin whose range rejects the running version. 0.2.0 shipped
``<0.23`` and Hermes 0.23.1 dropped ``/minefield`` on update, while CI stayed green: a checkout
pinned by SHA has no release tag, so Hermes reported "unknown" and accepted any range.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = yaml.safe_load((ROOT / "plugin.yaml").read_text())["requires_hermes"]
MATRIX = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]["hermes-compat"][
    "strategy"
]["matrix"]["include"]
RELEASES = [row["release"] for row in MATRIX if row.get("release")]


def _tuple(version: str) -> tuple[int, int, int]:
    parts = (version.strip().lstrip("v").split(".") + ["0", "0"])[:3]
    return tuple(int(re.match(r"\d+", p).group(0)) for p in parts)  # type: ignore[union-attr]


def _admits(spec: str, version: str) -> bool:
    ops = {">=": "__ge__", "<=": "__le__", ">": "__gt__", "<": "__lt__", "==": "__eq__"}
    for clause in (c.strip() for c in spec.split(",") if c.strip()):
        op, target = re.fullmatch(r"(>=|<=|==|>|<)\s*(.+)", clause).groups()  # type: ignore[union-attr]
        if not getattr(_tuple(version), ops[op])(_tuple(target)):
            return False
    return True


def test_the_range_has_a_lower_and_an_upper_bound():
    assert re.fullmatch(r">=\d+\.\d+,<\d+\.\d+", SPEC), SPEC


@pytest.mark.parametrize("release", RELEASES)
def test_every_release_ci_runs_is_admitted(release):
    assert _admits(SPEC, release), f"plugin.yaml requires_hermes {SPEC!r} rejects Hermes {release}"


def test_the_newest_admitted_minor_has_a_blocking_ci_lane():
    """Widen only with CI proof: ``<0.24`` needs a blocking lane on a tagged 0.23.x release."""
    upper = _tuple(SPEC.split("<")[1])
    newest_minor = (upper[0], upper[1] - 1)
    proven = {_tuple(row["release"])[:2] for row in MATRIX if row.get("release") and not row["experimental"]}
    assert newest_minor in proven, f"no blocking hermes-compat lane on {newest_minor[0]}.{newest_minor[1]}.x"


def test_release_lanes_tag_the_checkout_so_the_gate_is_real():
    steps = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]["hermes-compat"][
        "steps"
    ]
    assert any("tag -f" in str(step.get("run", "")) and "matrix.release" in str(step) for step in steps)


def test_hermes_agrees_with_this_reading_of_the_range():
    manifest = pytest.importorskip("hermes_cli.plugins_manifest")
    satisfies = getattr(manifest, "version_satisfies", None)
    if satisfies is None:
        pytest.skip("this Hermes has no requires_hermes gate")
    for release in RELEASES:
        assert satisfies(SPEC, release), release
    upper = SPEC.split("<")[1]
    assert not satisfies(SPEC, upper)
