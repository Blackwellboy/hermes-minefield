# wtf classification rules

Implemented in `hermes_minefield/incident/rules.py`, one pure function per rule. `classify()` returns the **first** rule that fires. Each rule has a fixture in `fixtures/rules/`, and `tests/test_rules.py` fails if a rule has none.

| # | Rule | Fires when | Classification | Severity | Verdict |
|---|---|---|---|---|---|
| 1 | `auth_failure` | ≥ 1 `api.error` with HTTP 401/403 | `CONFIGURATION_ERROR` | HIGH | FAIL |
| 2 | `rate_limited` | ≥ 3 HTTP 429 | `PERFORMANCE_CONTENTION` | MEDIUM | FAIL |
| 3 | `server_errors` | ≥ 3 errors with 5xx or no status (connection) | `MODEL_SERVER_BUG` | MEDIUM | FAIL |
| 4 | `tool_hang` | a `tool.requested` with no matching `tool.executed` (by call id) for > 120 s | `TOOL_BUG` | MEDIUM | FAIL |
| 5 | `tool_loop` | longest **consecutive** run, per session, of `tool.executed` with identical (tool, args, result) ≥ `loop_streak_threshold` (5). Pollers (`process_manage`, `*_poll`, `*_get_result`) are exempt | `AGENT_TOOL_LOOP` | HIGH (confidence HIGH for idempotent tools, MEDIUM otherwise) | FAIL |
| 6 | `failure_storm` | one tool failed ≥ 5 times, and ≥ 50% of its executions | `TOOL_BUG` | MEDIUM | FAIL |
| 7 | `not_dispatched` | ≥ 10 prepared with ≤ max(2, 15%) dispatched, or ≥ 5 prepared call ids never dispatched | `HERMES_UI_ORCHESTRATION` | ANNOYING / MEDIUM | FAIL |
| 8 | `slow_model` | ≥ 3 responses with p95 latency > 60 s or p95 TTFT > 20 s | `PERFORMANCE_CONTENTION` | LOW | FAIL |
| 9 | `quiet` | no tool or API activity at all | `UNKNOWN` | LOW | UNKNOWN |
| 10 | `aligned` | every dispatched call finished or is still in flight, and nothing above fired | `EXPECTED_BEHAVIOUR` | LOW | PASS* |
| — | `fallback` | anything else | `UI_RENDERING_BUG` / `UNKNOWN` | LOW | FAIL / UNKNOWN |

\* `PASS` needs recorded events. A window that hit `recorder_max_events` (so it may be truncated) is `UNKNOWN`, never `PASS`.

Why "same arguments **and** same result": repeating a call is only a loop if it makes no progress. Polling `git status` while a build runs, or re-reading a file after editing it, changes the result, so it isn't a loop. This mirrors Hermes's own `tool_loop_guardrails` ("idempotent no-progress").

Only serving-side classifications (`MODEL_SERVER_BUG`, `PERFORMANCE_CONTENTION`, …) are compared against the Minefield trap registry. Product and agent bugs are explicitly **not** Minefield traps.
