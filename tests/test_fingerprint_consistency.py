"""status and check must share the same Lite-cache fingerprint key."""

from __future__ import annotations

from hermes_minefield.fingerprint import build_fingerprint, fingerprint_for_hermes_target


def test_shared_helper_matches_check_formula():
    # Historical check() formula that produced the live cache key family.
    legacy = build_fingerprint(
        model="Qwen3.8-27B-OBLITERATED-Q4_K_M",
        base_url="http://127.0.0.1:8007/v1",
        reasoning_mode="from_config",
    )
    shared = fingerprint_for_hermes_target(
        model="Qwen3.8-27B-OBLITERATED-Q4_K_M",
        base_url="http://127.0.0.1:8007/v1",
    )
    assert shared.key == legacy.key


def test_status_without_reasoning_mode_diverged():
    """Documents the pre-fix bug: status omitted reasoning_mode."""
    with_rm = build_fingerprint(
        model="m",
        base_url="http://127.0.0.1:8007/v1",
        reasoning_mode="from_config",
    )
    without = build_fingerprint(model="m", base_url="http://127.0.0.1:8007/v1")
    assert with_rm.key != without.key
    assert with_rm.short() != without.short()


def test_status_and_check_same_key(tmp_hermes_home, monkeypatch):
    from hermes_minefield.commands.check import run_check
    from hermes_minefield.commands.status import run_status
    from hermes_minefield.cache import CacheEntry, put_entry
    from hermes_minefield.fingerprint import fingerprint_for_hermes_target
    import time

    (tmp_hermes_home / "config.yaml").write_text(
        "model:\n  default: test-model\n  base_url: http://127.0.0.1:8007/v1\n",
        encoding="utf-8",
    )
    fp = fingerprint_for_hermes_target(model="test-model", base_url="http://127.0.0.1:8007/v1")
    put_entry(
        CacheEntry(
            fingerprint=fp.key,
            checked_at=time.time(),
            mode="lite",
            summary={
                "clean": 4,
                "problem": 1,
                "inconclusive": 0,
                "findings": [
                    {"level": "PROBLEM", "title": "warn"},
                    {"level": "OK", "title": "a"},
                    {"level": "OK", "title": "b"},
                    {"level": "OK", "title": "c"},
                    {"level": "OK", "title": "d"},
                ],
            },
            requests_executed=5,
            clean=4,
            problem=1,
            inconclusive=0,
        )
    )
    st = run_status()
    assert fp.short() in st["text"]
    assert "none" not in st["text"].split("cache:")[1].splitlines()[0]
    # Cached check — no network
    ck = run_check(force=False)
    assert ck["cached"] is True
    assert ck["fingerprint"] == fp.short()
    assert "4 clean" in ck["text"]
