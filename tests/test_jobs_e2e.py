"""Shared service with real Minefield probes and loopback wire receipts."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from hermes_minefield.service.authority import Authority, Scope
from hermes_minefield.service.jobs import Jobs


@pytest.fixture
def fixture_target():
    calls = []
    release = threading.Event()
    release.set()
    faults = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def do_GET(self):
            calls.append(("GET", self.path, None))
            self.reply(
                200 if self.path == "/v1/models" else 404, {"data": [{"id": faults.get("model", "fixture")}]}
            )

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(("POST", self.path, body))
            release.wait(1)
            if "__minefield_unvalidated_field_probe__" in body:
                self.reply(400, {"error": "unknown field"})
            else:
                self.reply(
                    200,
                    faults.get(
                        "baseline", {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
                    ),
                )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    release.faults = faults
    yield f"http://127.0.0.1:{server.server_port}/v1", calls, release
    release.set()
    server.shutdown()
    server.server_close()
    thread.join()


def wait(service, job, scope):
    for _ in range(300):
        row = service.status(job, scope)
        if row["state"] not in {"QUEUED", "RUNNING"}:
            return row
        time.sleep(0.01)
    raise AssertionError("job did not terminate")


def test_exact_review_grant_and_wire_counts(fixture_target, tmp_path):
    target, calls, _ = fixture_target
    scope = Scope("p", "c", "s", "owner")
    event = object()
    authority = Authority(lambda e, s, a, d: e is event and s == scope)
    service = Jobs(scope, authority, target, "fixture", tmp_path / "locks.sqlite")
    try:
        plan = service.plan(["request_validation"])
        assert calls == []
        with pytest.raises(PermissionError):
            service.start(plan.id, {"approved": True})
        grant = authority.approve(event, scope, "run:" + plan.id, plan.digest)
        job = service.start(plan.id, grant)
        result = wait(service, job, scope)
        assert result["state"] == "COMPLETED"
        expected = json.loads(plan.canonical)["wire"]["requests"]
        assert calls == [(r["method"], r["path"], r["body"]) for r in expected]
        assert result["http"] == 6 and result["generations"] == 2
        assert result["findings"][0]["code"] == "VALIDATION_REJECTS_UNKNOWN_FIELD"
        assert [p["id"] for p in result["probe_runs"]] == ["request_validation"]
        assert result["probe_runs"][0]["http_requests_made"] == 2
        with pytest.raises(PermissionError):
            service.start(plan.id, grant)
        with pytest.raises(PermissionError):
            service.status(job, Scope("other", "c", "s", "owner"))
    finally:
        service.close()


def test_cancel_stops_paired_request_and_endpoint_lock(fixture_target, tmp_path):
    target, calls, release = fixture_target
    release.clear()
    scope = Scope("p", "c", "s", "owner")
    event = object()
    authority = Authority(lambda e, s, a, d: e is event)
    first = Jobs(scope, authority, target, "fixture", tmp_path / "locks.sqlite")
    second = Jobs(scope, authority, target, "fixture", tmp_path / "locks.sqlite")
    try:
        plan = first.plan(["request_validation"])
        first.start(plan.id, authority.approve(event, scope, "run:" + plan.id, plan.digest))
        for _ in range(100):
            if any(method == "POST" for method, _, _ in calls):
                break
            time.sleep(0.01)
        competing = second.plan(["request_validation"])
        with pytest.raises(PermissionError, match="busy"):
            second.start(
                competing.id, authority.approve(event, scope, "run:" + competing.id, competing.digest)
            )
        first.cancel(plan.id, scope)
        release.set()
        result = wait(first, plan.id, scope)
        assert result["state"] == "CANCELLED_PARTIAL"
        assert result["generations"] == 1
        assert len([c for c in calls if c[0] == "POST"]) == 1
        assert result["remote_compute_terminated"] == "UNKNOWN"
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize(
    "baseline", [{}, {"choices": []}, {"error": "synthetic"}, {"choices": [{"message": {"content": ""}}]}]
)
def test_malformed_200_never_clean(fixture_target, tmp_path, baseline):
    target, calls, release = fixture_target
    release.faults["baseline"] = baseline
    scope = Scope("p", "c", "s", "owner")
    event = object()
    authority = Authority(lambda e, s, a, d: e is event)
    service = Jobs(scope, authority, target, "fixture", tmp_path / "locks.sqlite")
    try:
        plan = service.plan(["request_validation"])
        service.start(plan.id, authority.approve(event, scope, "run:" + plan.id, plan.digest))
        result = wait(service, plan.id, scope)
        assert result["generations"] == 1
        assert result["findings"][0]["code"] == "VALIDATION_NO_BASELINE"
        assert all(f["level"] != "OK" for f in result["findings"])
    finally:
        service.close()


def test_model_drift_stops_before_any_generation(fixture_target, tmp_path):
    target, calls, release = fixture_target
    release.faults["model"] = "changed-fixture-model"
    scope = Scope("p", "c", "s", "owner")
    event = object()
    authority = Authority(lambda e, s, a, d: e is event)
    service = Jobs(scope, authority, target, "fixture", tmp_path / "locks.sqlite")
    try:
        plan = service.plan(["request_validation"])
        service.start(plan.id, authority.approve(event, scope, "run:" + plan.id, plan.digest))
        result = wait(service, plan.id, scope)
        assert result["error"] == "MODEL_DRIFT"
        assert result["generations"] == 0
        assert not any(method == "POST" for method, _, _ in calls)
    finally:
        service.close()
