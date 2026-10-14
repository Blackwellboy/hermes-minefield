# Implementation status

State: IN_PROGRESS, not OFFLINE_BETA_READY.

| Milestone | State | Evidence / next action |
|---|---|---|
| M0 | partial | refreshed SHAs, full spec read, current-host loader baseline; review metadata/min-version campaign pending |
| M1 | partial | draft/main reconciled, ordering regression fixed; dependency pins/receipt integration pending |
| M2 | partial | closed schema, scoped one-use grants, exact fixture plans, all-HTTP bounds, cancellation, endpoint lock implemented; persistent receipts/restart recovery and other probe previews missing |
| M3 | partial | actual host-loaded home/checks/preview/privacy/back, five tools and skill; trusted stateful approval/progress/privacy controls missing |
| M4 | partial | real SDK pane/backend and source-level component tests; Electron/authenticated private-route/approval tests not run |
| M5 | partial | forward-only consent, aggregation, automatic tick/outbox/retries/deletion in fixture service; native bridge, hook/worker lifecycle and receipt rotation missing |
| M6 | partial | actual loopback intake, idempotence, deletion, suppression/workbench and idle retention; no production hardening/deployment |
| M7 | partial | wheel resource smoke, unified zip builder, current validator; full mapped acceptance, minimum-host/OS and install lifecycle missing |
| M8 | AWAITING_OWNER | no live tests, deployment, merge or release |

Native execution and contribution activation remain unavailable. Fixture authority
callbacks do not establish a trusted host event. The visible surface provides
catalogue selection and preview, but not the requested full diagnostic workflow.

## Candidate and actual evidence

Core: `3425846011fa65a27569eed6405e52d33431b16e`, branch
`codex/bounded-execution-20261014`, pushed, not merged. Adapter baseline checkpoint
`3baf85d`; integration checkpoint follows this document. Host: v0.21.7
`71d34bad1045610252eda02ee79549436896e784`. Windows Python 3.14.5 for host,
Python 3.12.7 wheel smoke, Node 24.19.0 SDK source tests. No other OS claim.

- Adapter `pytest -q -k 'not backend'`: 320 passed, 4 skipped, 8 deselected.
  Seven deselections are Gate A; backend separately passed 1. The idle-retention test also passed in the 20-test jobs/contributions run.
- Focused core execution/API/request-validation suite: 18 passed.
- Actual SDK source component tests: 2 passed. SDK/context/registry are real;
  backend boundary is synthetic. This is not an Electron verification claim.
- Current host validator passed, including security, no-core-override and SDK
  checks. Warnings retained: Git URL dependency needs external runtime; isolated
  host skips register_cli_command; backend responses are buffered.
- Ruff check/format passed. Wheel built; imports and packaged skill verified from
  a separate installed target outside source imports. Unified zip builder exists.

Broad core tests are NOT green. Baseline verdict tests also fail. Instrumentation
observed WinError 10048 (socket address exhaustion); fresh narrow tests pass. A
later broad attempt failed during import-time assertions. This does not prove all
failures are environmental. Complete core release gates remain unresolved.
Combined adapter/backend tests also hung under that load; separate invocations
are recorded rather than hidden. Final Gate A rerun: 7 passed, 7 deselected.

## CI follow-up

Initial remote run passed Python 3.11/3.12/3.13 unit jobs and minimum/current
stable Hermes compatibility. Admission failed because newly added registration
imports required the optional core before use; imports are now deferred. Core CI
found pytest in its unittest-only job; the same three tests now run as unittest.
Core bundle was regenerated and verified. Current core pin: `6c75e3097832419fb224a918b4d285f16f5bfb62`.
The rerun, including secret scan and generated-artifact checks, remains pending.
