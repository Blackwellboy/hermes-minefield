# Acceptance matrix

No row is closed by a test count alone. Baseline coverage is not full feature acceptance.

| ID | Required proof | State | Evidence |
|---|---|---|---|
| UX-01 | `/minefield` opens inside a real supported Hermes session and presents real choices; opening it causes zero diagnostic HTTP/generation calls. | NOT_RUN | Pending implementation and mapped test |
| UX-02 | Each choice changes actual controller state. Back, edit and cancel do not run a test or lose the wrong session's state. | NOT_RUN | Pending implementation and mapped test |
| UX-03 | Probe selections, costs, required inputs and unavailable labels derive from the actual registry/planner. No stale hard-coded coverage counts. | NOT_RUN | Pending implementation and mapped test |
| UX-04 | Review shows the exact permitted scope and destinations. Declining approval yields zero HTTP calls, including GET discovery. | NOT_RUN | Pending implementation and mapped test |
| UX-05 | Trusted fixture approval starts exactly the selected work once, in the shown order; double-clicks/duplicate callbacks are idempotent. | NOT_RUN | Pending implementation and mapped test |
| UX-06 | Progress uses execution events; cancellation leaves a truthful partial receipt and never resets a serving process. | NOT_RUN | Pending implementation and mapped test |
| UX-07 | Results expose problem/clean/inconclusive/unavailable and invoked/not-run states, with readable evidence and no false global health score. | NOT_RUN | Pending implementation and mapped test |
| UX-08 | Fresh, empty, stale, disconnected, unsupported-transport, missing-backend and collector-unavailable views are usable and honest. | NOT_RUN | Pending implementation and mapped test |
| UX-09 | Desktop uses actual SDK entrypoints and backend handlers. Test every displayed control, keyboard focus, narrow layout and theme. | NOT_RUN | Pending implementation and mapped test |
| UX-10 | Changing gateway/profile/session invalidates approvals and stale responses; old data cannot reappear after a delayed response. | NOT_RUN | Pending implementation and mapped test |
| UX-11 | Gateway menu choices are actor/scope checked. A second participant cannot run probes, change privacy or inspect another user's incident. | NOT_RUN | Pending implementation and mapped test |
| UX-12 | Compatibility commands still work; scripts receive valid deterministic JSON and never hang waiting for human input. | NOT_RUN | Pending implementation and mapped test |
| UX-13 | Model-callable tools and bundled skill are actually registered and discovered. The local explanation tool works with no collector and no diagnostic model call. | NOT_RUN | Pending implementation and mapped test |
| RUN-01 | Unknown probe IDs, invalid budgets/inputs and unsupported transport fail before any network activity. | NOT_RUN | Pending implementation and mapped test |
| RUN-02 | Generation and total HTTP ceilings hold across all selected probe branches, discovery, retries, streaming and legacy completions. | NOT_RUN | Pending implementation and mapped test |
| RUN-03 | Synthetic fixture tests exercise baseline, clean controls, malformed payloads, rejected fields, missing fields, server errors and alternate-control paths. | NOT_RUN | Pending implementation and mapped test |
| RUN-04 | Active transport preserves the raw field/stream semantics under test. A high-level provider rewrite cannot create a misleading diagnosis. | NOT_RUN | Pending implementation and mapped test |
| RUN-05 | Plan target/model/revision/prompt-template drift invalidates approval. Redirects and wrong-origin credential forwarding are rejected. | NOT_RUN | Pending implementation and mapped test |
| RUN-06 | Plan order equals invocation order, and per-probe counts sum to observed transport counts and receipt totals. | NOT_RUN | Pending implementation and mapped test |
| RUN-07 | On cancellation/error/deadline/budget exhaustion, later probes are not run and earlier evidence remains available. | NOT_RUN | Pending implementation and mapped test |
| RUN-08 | One failed assertion or missing prerequisite cannot be turned into a clean trap by a second partial check. Historical and current runs are not conflated. | NOT_RUN | Pending implementation and mapped test |
| RUN-09 | Timeout, auth error, rate limit and malformed 200 do not count as successful request/model/tool validation. | NOT_RUN | Pending implementation and mapped test |
| RUN-10 | Cache keys and TTLs respect exact target/config/check scope; cached results are visibly not fresh execution. | NOT_RUN | Pending implementation and mapped test |
| RUN-11 | Competing windows/processes respect the shared endpoint job lock and cannot multiply budgets unnoticed. | NOT_RUN | Pending implementation and mapped test |
| RUN-12 | Restart after an unfinished job records interruption; no automatic resumption or model loading. | NOT_RUN | Pending implementation and mapped test |
| PRIV-01 | Default/local-only mode makes zero diagnostic-export requests. Passive hooks add zero active probe requests. | NOT_RUN | Pending implementation and mapped test |
| PRIV-02 | Owner/agent/export projections are distinct. Private operator details cannot enter a model-visible tool result accidentally. | NOT_RUN | Pending implementation and mapped test |
| PRIV-03 | Canary private content/secrets are absent from actual outgoing bytes, retry queues, side logs and collector error logs. | NOT_RUN | Pending implementation and mapped test |
| PRIV-04 | Unknown keys, arbitrary names, nested lists/objects, duplicate keys, Unicode tricks, NaN and oversize data fail closed. | NOT_RUN | Pending implementation and mapped test |
| PRIV-05 | No old local observations are transmitted after opt-in. Aggregates split at consent transitions and invalid/ambiguous epochs cannot send. | NOT_RUN | Pending implementation and mapped test |
| PRIV-06 | Turning off consent while a batch/retry is queued prevents new sends and clears unsent data. In-flight limits are disclosed. | NOT_RUN | Pending implementation and mapped test |
| PRIV-07 | Recipient, schema or purpose expansion requires new owner review. Nous consent cannot enable the Minefield recipient. | NOT_RUN | Pending implementation and mapped test |
| PRIV-08 | Agent output, forged `approved` arguments, replayed menu IDs and unauthorised chat users cannot enable sharing or public submission. | NOT_RUN | Pending implementation and mapped test |
| PRIV-09 | Public model/tool mapping rejects unknown private names rather than trusting their syntax or sending them for lookup. | NOT_RUN | Pending implementation and mapped test |
| PRIV-10 | Local correlations use protected scoped keys/tokens where required; no content hash or persistent installation ID appears in exported reports. | NOT_RUN | Pending implementation and mapped test |
| PRIV-11 | Contribution preview matches the canonical bytes sent. Idempotent retries are byte-identical; edited rich drafts require reapproval. | NOT_RUN | Pending implementation and mapped test |
| PRIV-12 | Local purge, consent reset, outbox expiry, receipt-based remote deletion and backup/aggregate effects are tested and described separately. | NOT_RUN | Pending implementation and mapped test |
| PRIV-13 | Service unavailable, outbox full, bad disk, worker failure and malformed return values do not stop the user's Hermes work. | NOT_RUN | Pending implementation and mapped test |
| PRIV-14 | Authenticated UI/socket routes enforce connection/profile/actor scope server-side; global events never leak incident contents. | NOT_RUN | Pending implementation and mapped test |
| INT-01 | Client-to-reference-collector end-to-end ingest, acknowledgement, identical retry, conflicting duplicate and lost-ack recovery work. | NOT_RUN | Pending implementation and mapped test |
| INT-02 | Invalid/abusive packages are bounded and rejected; no arbitrary URL fetching, attachment ingestion or command execution. | NOT_RUN | Pending implementation and mapped test |
| INT-03 | Denominators, sampling, organic/test evidence and user-reported outcomes remain distinct in the maintainer view. | NOT_RUN | Pending implementation and mapped test |
| INT-04 | Rare-cell coarsening/suppression works, including subtraction/drill-down cases; package count is never labelled unique users. | NOT_RUN | Pending implementation and mapped test |
| INT-05 | Retention and receiver deletion actually run and recompute/remove affected non-public retained aggregates as documented. | NOT_RUN | Pending implementation and mapped test |
| PKG-01 | Clean isolated installation includes resources, agent half and supported Desktop/backend halves; no source-checkout-only success. | NOT_RUN | Pending implementation and mapped test |
| PKG-02 | Upgrade, disable, uninstall and rollback preserve privacy boundaries and do not leave untracked workers/hooks or upload legacy data. | NOT_RUN | Pending implementation and mapped test |
| PKG-03 | Current documented host validator and existing core/adapter security/compatibility gates pass on the exact candidate. | NOT_RUN | Pending implementation and mapped test |
| PKG-04 | Supported minimum and stable Hermes versions are tested; rolling main is separate; OS/architecture claims match actual evidence. | NOT_RUN | Pending implementation and mapped test |
| PKG-05 | README commands, demos and screenshots match the built product and state fixture versus real-model provenance. | NOT_RUN | Pending implementation and mapped test |
| PKG-06 | No third-party issues, catalogue submissions, production services or live-model contacts occurred during M0–M7. | NOT_RUN | Pending implementation and mapped test |
