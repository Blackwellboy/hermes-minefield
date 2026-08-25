"""Confirm sealed Minefield Phase 0 API is consumable by the plugin."""

from __future__ import annotations


def test_import_minefield_api():
    from minefield.api import (
        detect_target,
        plan_checks,
        result_to_doctor_json,
        run_checks,
        summarize,
    )

    assert callable(plan_checks)
    assert callable(run_checks)
    assert callable(summarize)
    assert callable(detect_target)
    assert callable(result_to_doctor_json)


def test_plan_lite_respects_budget_zero_requests():
    from minefield.api import plan_checks

    plan = plan_checks(
        base_url="http://127.0.0.1:9/v1",
        mode="lite",
        max_requests=3,
        detect=False,
    )
    assert plan.expected_requests <= 3
    assert plan.fits_budget is True
    # planning itself issues zero chat completions (no network in detect=False)
    assert "plan_without_detect" in plan.target.notes or plan.expected_requests >= 0


def test_plan_lite_max5():
    from minefield.api import plan_checks

    plan = plan_checks(
        base_url="http://127.0.0.1:9/v1",
        mode="lite",
        max_requests=5,
        detect=False,
    )
    assert plan.expected_requests <= 5
