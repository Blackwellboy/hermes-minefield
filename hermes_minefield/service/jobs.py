"""Scoped immutable plans and lifecycle-owned fixture execution.

Production surfaces do not construct this service until their host authority
bridge is verified. It accepts only an explicit fixture destination, never host
credential/config resolution. The neutral core owns all probe implementation.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from minefield.api import plan_checks, preview_requests, run_checks
from minefield.execution import ExecutionControl


@dataclass(frozen=True)
class Plan:
    id: str
    digest: str
    canonical: str


class Jobs:
    def __init__(self, scope, authority, fixture_url, model, coordinator, *, clock=time.time):
        p = urlsplit(fixture_url)
        if (
            p.scheme != "http"
            or p.hostname != "127.0.0.1"
            or not p.port
            or p.username
            or p.password
            or p.query
            or p.fragment
            or p.path != "/v1"
        ):
            raise ValueError("explicit loopback fixture /v1 target required")
        self.scope, self.authority, self.target, self.model = scope, authority, fixture_url, model
        self.clock = clock
        self.lock = threading.RLock()
        self.plans, self.jobs, self.controls = {}, {}, {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="minefield-job")
        self.db = sqlite3.connect(coordinator, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS endpoint_locks(target TEXT PRIMARY KEY, job TEXT)")
        self.target_key = hashlib.sha256(fixture_url.encode()).hexdigest()
        self.closed = False

    def plan(self, probe_ids):
        with self.lock:
            if self.closed or len(self.plans) >= 128:
                raise ValueError("workspace capacity reached")
            core = plan_checks(
                base_url=self.target,
                model=self.model,
                detect=False,
                mode="doctor",
                max_requests=2,
                probe_ids=probe_ids,
            )
            wire = preview_requests(core)
            value = {
                "scope": asdict(self.scope),
                "target": self.target,
                "model": self.model,
                "selected": list(core.selected_ids),
                "core_contract": "bounded-execution.v1",
                "wire": wire,
                "created": self.clock(),
                "expires": self.clock() + 120,
                "timeout": 2,
                "deadline": 20,
                "concurrency": 1,
                "sharing": "OFF",
            }
            canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
            plan = Plan(secrets.token_hex(16), hashlib.sha256(canonical.encode()).hexdigest(), canonical)
            self.plans[plan.id] = (plan, core)
            return plan

    def start(self, plan_id, grant):
        with self.lock:
            if self.closed or plan_id not in self.plans:
                raise ValueError("unknown or closed plan")
            plan, core = self.plans[plan_id]
            value = json.loads(plan.canonical)
            if (
                value["expires"] <= self.clock()
                or value["target"] != self.target
                or value["model"] != self.model
            ):
                raise PermissionError("expired or changed plan")
            self.authority.consume(grant, self.scope, "run:" + plan_id, plan.digest)
            if plan_id in self.jobs:
                raise PermissionError("plan already executed")
            with self.db:
                try:
                    self.db.execute("INSERT INTO endpoint_locks VALUES(?,?)", (self.target_key, plan_id))
                except sqlite3.IntegrityError:
                    raise PermissionError("endpoint busy or interrupted lock requires review") from None
            wire = value["wire"]
            self.jobs[plan_id] = {
                "state": "QUEUED",
                "plan_digest": plan.digest,
                "http": 0,
                "generations": 0,
                "progress": [],
                "probe_runs": [],
                "findings": [],
                "remote_compute_terminated": "UNKNOWN",
            }

            def progress(event):
                with self.lock:
                    row = self.jobs[plan_id]
                    row["http"], row["generations"] = event["http"], event["generations"]
                    row["progress"].append(event)

            control = ExecutionControl(
                origin=self.target,
                max_http=wire["max_http"],
                max_generations=wire["max_generations"],
                max_output_tokens=wire["max_output_tokens"],
                paths=[r["path"] for r in wire["requests"]],
                requests=wire["requests"],
                timeout=value["timeout"],
                deadline=value["deadline"],
                on_progress=progress,
                expected_model=self.model,
            )
            self.controls[plan_id] = control
            self.pool.submit(self._run, plan_id, core, control)
            return plan_id

    def _run(self, plan_id, core, control):
        with self.lock:
            self.jobs[plan_id]["state"] = "RUNNING"
        try:
            result = run_checks(core, execution=control)
            state = "COMPLETED"
            if result.error:
                state = {
                    "CANCELLED": "CANCELLED_PARTIAL" if control.http else "CANCELLED_BEFORE_START",
                    "BUDGET_EXHAUSTED": "BUDGET_EXHAUSTED",
                    "DEADLINE": "INTERRUPTED",
                }.get(result.error, "ERROR")
            with self.lock:
                self.jobs[plan_id].update(
                    state=state,
                    http=control.http,
                    generations=control.generations,
                    probe_runs=result.probe_runs,
                    findings=[{k: f.get(k) for k in ("level", "code", "traps")} for f in result.findings],
                    error=result.error,
                )
        except Exception:
            with self.lock:
                self.jobs[plan_id].update(
                    state="ERROR",
                    error="execution_failed",
                    http=control.http,
                    generations=control.generations,
                )
        finally:
            with self.lock, self.db:
                self.db.execute(
                    "DELETE FROM endpoint_locks WHERE target=? AND job=?", (self.target_key, plan_id)
                )

    def status(self, plan_id, scope):
        if scope != self.scope:
            raise PermissionError("wrong scope")
        with self.lock:
            if plan_id not in self.jobs:
                raise ValueError("job not found")
            return json.loads(json.dumps(self.jobs[plan_id]))

    def cancel(self, plan_id, scope):
        if scope != self.scope:
            raise PermissionError("wrong scope")
        with self.lock:
            self.controls[plan_id].cancel()

    def close(self):
        with self.lock:
            self.closed = True
            for control in self.controls.values():
                control.cancel()
            self.authority.invalidate(self.scope)
        self.pool.shutdown(wait=True, cancel_futures=False)
        self.db.close()
