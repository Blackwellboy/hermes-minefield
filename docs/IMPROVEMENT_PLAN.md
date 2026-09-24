# hermes-minefield: Improvement & Hermes Integration Plan

> **Who this is for:** a coding agent (GLM, DeepSeek, or similar) working through the plan one task at a time, and the repo owner reviewing each PR.
> **Written:** 2026-09-24, from a full review of `main` @ `6479671`. **Revised** the same day after owner review: added the diagnostic-integrity rule, T0.5 (Hermes compatibility matrix), T1.8 (verdicts), milestone ordering (hot-path safety moved into Milestone A), F6/F15/F16 raised in severity, and privacy-first remote dedupe.
>
> **Status:** `hermes-minefield` is **experimental**. Don't rely on its diagnoses until Gate A (§4.0) passes. This is about the Hermes adapter only. The `model-serving-minefield` registry and Doctor underneath are a separate, healthy system.
> **Verified against:** hermes-agent `d350422b15863fc4c0b7962b122b625a0271516c` (v0.21.5) and model-serving-minefield `7b324f86d424c20bce177200851c968c1d70c536`.

---

## 0. How to execute this plan (read first, every session)

1. **Work in milestone order.** Follow the order in **§4.0 Milestones**, not the numeric order of the task IDs (IDs are stable references, the milestone list is the schedule). Don't start a task until every task before it in that list is ticked `[x]`. Don't start a milestone until the previous milestone's gate has passed.
2. **One task = one branch = one PR.** Name the branch `plan/<task-id>-<short-slug>`, for example `plan/t1.1-hook-contract`. Keep each PR limited to its task. If you notice another problem while working, add a bullet to **§6 Parking lot** at the bottom of this file. Don't fix it in the current PR.
3. **Read before you write.** Before changing a file, read all of it, plus every file that imports it (`grep -rn "<module>" hermes_minefield tests`).
4. **Tests first when fixing a bug.** Write the failing test and run it to watch it fail. Then fix the code and run it to watch it pass. Put the failing output in the PR description.
5. **Gate every PR on the checks in §0.1.** All of them must pass locally before you push.
6. **Don't improvise on facts.** Section 2 lists the Hermes hook argument names, which were checked against Hermes source. If the code you see disagrees with this plan, or a step is ambiguous, **stop**. Write down the discrepancy in the PR description and ask the owner. Don't guess.
7. **Diagnostic integrity (the most important rule in this plan).** Every command result carries an explicit `verdict`:
   - `PASS`: the target was tested and the findings are valid,
   - `FAIL`: the target was tested and something is wrong,
   - `UNKNOWN`: the target could not be meaningfully tested (unreachable, no probes ran, no recorder data, stale or missing evidence).

   **Missing evidence must never become negative evidence. `UNKNOWN` is not `PASS`.** This applies to `check`, `doctor`, `wtf`, cache reads, recorder gaps, and target resolution. Any change that can turn "couldn't test" into something that looks clean is a release blocker.
8. **Never do these things** (they are hard rules, even if a task seems to need one):
   - Weaken, skip, or delete an existing test to make CI pass. You may *rewrite* a test when a task explicitly changes that behaviour. Say so in the PR.
   - Add automatic GitHub submission. Let model output approve anything. Allow conversation text, tool arguments, or tool results to leave the machine.
   - Store raw tool arguments, tool results, prompts, or API keys on disk. Store hashes, lengths, and counts only.
   - Add new runtime dependencies. The only runtime dependency is `model-serving-minefield`, and PyYAML stays optional.
   - Open PRs or issues against `NousResearch/hermes-agent` or any repo other than `Blackwellboy/hermes-minefield`. T6.4 is the only exception, and it needs **written owner approval**.
   - Change a public command name or flag without keeping the old one as an alias.
9. **Tick the box.** When a task is merged, change its `- [ ]` to `- [x]` in this file (in the same PR is fine).
10. **Commit style:** `<area>: <imperative summary> (T<id>)`, for example `recorder: read Hermes 'args' kwarg for tool fingerprints (T1.1)`.

### 0.1 The local check gate (run before every push)

```bash
# one-time setup (T0.1 creates this script)
./scripts/dev_setup.sh
source .venv/bin/activate

# every time
ruff check hermes_minefield tests              # lint (T0.2 adds config)
ruff format --check hermes_minefield tests     # formatting (T0.2)
python -m compileall -q hermes_minefield tests
pytest -q                                      # unit + contract tests
hermes plugins validate .                      # Hermes admission check (T0.4)
```

Paste the tail of each command's output into the PR description under a `## Checks` heading.

---

## 1. Review summary: what's wrong today

The architecture is sound: a thin, opt-in Hermes adapter over the Minefield library, with metadata-only recording and a human-gated issue workflow. The safety intent is strong. The main problem is that **the flight recorder was built against guessed hook signatures, not Hermes's real ones.** So on a real Hermes install, the core `wtf` feature gets the wrong answer. The unit tests didn't catch it because they feed the plugin the same guessed kwargs.

Each finding below was reproduced during the review. Severity: 🔴 critical, 🟠 high, 🟡 medium, ⚪ low.

| # | Sev | Finding | Evidence | Fixed in |
|---|---|---|---|---|
| F1 | 🔴 | `pre_tool_call`/`post_tool_call` read `params=`, but Hermes passes `args=`. Every tool call gets the fingerprint of `None`, so **any 10+ tool calls get labelled `AGENT_TOOL_LOOP` / HIGH**. | 12 different `read_file` calls with Hermes kwargs → `AGENT_TOOL_LOOP HIGH … (11 equivalent-argument repeats)` | T1.1 |
| F2 | 🔴 | Tool failures are never recorded. Hermes sends `status="error"`, `error_type`, and `error_message`, never an `error`/`exception` object, so `success` is always `True` and `tool.failed` never happens. | 6 of the 12 calls above returned errors; no `tool.failed` events | T1.1 |
| F3 | 🟠 | API hooks read the wrong keys: `status`/`http_status` (should be `status_code`), `wall_ms`/`duration_ms` (should be `api_duration` in **seconds**), `ttft_ms` (should be derived from `first_chunk_at - started_at`), `request_id` (should be `api_request_id`), `content_len` (should be `assistant_content_chars`). `api_request_error` passes `error` as a **dict**, so `error_class` is recorded as `"dict"`. | Recorded rows: `{'type':'api.error', 'error_class':'dict'}`; latency, status, and TTFT always missing | T1.1 |
| F4 | 🟠 | `post_llm_call` reads `content`/`response`, but Hermes sends `assistant_response`, so `content_len` is always 0. | `turn.end … content_len: 0` for `"hello world"` | T1.1 |
| F5 | 🟠 | `hermes plugins validate .` **fails**: `plugin.yaml` uses `hooks:`, but admission requires `provides_hooks:`. This blocks catalog submission. | `✗ declared hooks — undeclared hooks registered` | T0.4 |
| F6 | 🔴 | `check` against an unreachable endpoint prints an empty "0 clean / 0 problems" report, **exits 0, and caches it** as the last good check. `RunResult.reachable`/`.error` are ignored. | `hermes minefield check` with the server down → rc=0, cached | T1.3 |
| F7 | 🟠 | The loop detector counts *total* identical-argument calls over the whole window, with no notion of progress. Legitimate polling (`terminal "git status"` × 10) and re-reading a file after editing it both count as loops. Hermes's own guardrails use "same args **and** same result" plus idempotent/mutating tool classes. | Design review vs `agent/tool_guardrails.py` | T1.2, T3.2 |
| F8 | 🟠 | `check`/`doctor` never send an API key, and target resolution re-implements a small part of Hermes's provider logic. Authenticated endpoints fail, and so do named providers and env-configured endpoints. | `minefield.api.run_checks(api_key=…)` exists but is never passed | T2.3 |
| F9 | 🟡 | Cache TTL is never enforced (`is_fresh` and `fingerprint_cache_ttl_days` are unused), so a cached result is served forever. | grep: no callers | T1.4 |
| F10 | 🟡 | The `auto_lite` config option is dead code: it's parsed and displayed but never acted on. | grep: only logged/rendered | T5.3 |
| F11 | 🟡 | Incidents are never linked to the GitHub issue after submission (`update_incident_status` has no callers), so `issues --refresh` has nothing to refresh. | grep: no callers | T4.1 |
| F12 | 🟡 | `contribute` lists the incident itself as its own "duplicate". It also silently falls back to the latest incident when `--incident` is wrong. | `search_local(symptom, known=list_incidents())` includes itself | T1.6, T4.3 |
| F13 | 🟡 | Uncaught exceptions reach Hermes: no `base_url` configured, `--max-requests abc` in slash mode, and so on. | `resolve_target` raises `ValueError`; `int(mr)` unguarded | T1.5 |
| F14 | 🟡 | Every `wtf` run writes an incident file, even for quiet or expected windows, which clutters `issues`. `index.jsonl` grows without bound. | quiet `wtf` → `INC-…json` written | T1.6, T2.7 |
| F15 | 🟠 | Disk writes happen inside hook callbacks (`record()` → `_flush_locked()`). `pre_tool_call` is timeout-bounded and **fails closed** in Hermes, so a slow disk can block the agent's tools. Minefield itself could become the reason Hermes stops working. | Hermes `hooks.md`: `pre_tool_call` timeout → tool blocked | T2.4 |
| F16 | 🟠 | Several Hermes processes (CLI and gateway) append to *and rotate* one shared `events.jsonl` with read-modify-write, which loses data under concurrency. For an evidence tool, silently losing evidence is high severity. Cache, incident, and draft writes aren't atomic. Files are created world-readable by default umask. | `_rotate_disk` uses `write_text` on the shared file | T2.5, T2.6 |
| F17 | 🟡 | Config is read from `plugins.entries.<id>` directly, but Hermes's canonical location is `plugins.entries.<id>.settings` (`ctx.get_config`). Bad values (`lite_max_requests: abc`) crash `register()`. | `config.py` | T2.2 |
| F18 | ⚪ | `HERMES_HOME` env is checked *before* `hermes_constants.get_hermes_home()`, which bypasses Hermes's context-local/profile override. | `paths.py` | T2.1 |
| F19 | ⚪ | The root `__init__.py` inserts the plugin directory at `sys.path[0]` for the whole Hermes process. | `__init__.py` | T2.8 |
| F20 | ⚪ | Lint: `Mapping` is undefined in `issues/dedupe.py` (F821). There are 12 unused imports and f-strings without placeholders. | `ruff check` | T0.2 |
| F21 | ⚪ | Budget enforcement uses `assert`, which is stripped under `python -O`. | `commands/check.py` | T1.7 |
| F22 | ⚪ | CI checks out Minefield `main` unpinned (flaky). There's no lint, and no Hermes validation. | `ci.yml` | T0.3, T0.4 |
| F23 | ⚪ | The README says to install via the `hermes_agent.plugins` entry point, but `pyproject.toml` deliberately doesn't declare one. The version is duplicated in 3 places. | README vs pyproject | T6.1 |
| F24 | ⚪ | The `HERMES_UI_ORCHESTRATION` ("prepare storm") rule can't be reached with real hooks: `pre_tool_call` emits both PREPARED and REQUESTED, so prepared always equals executed. It only fires in synthetic fixtures. | `recorder/hooks.py` | T3.1 |
| F25 | ⚪ | Tests assert with loose `or` chains (`assert "X" in t or "Minefield" in t`) that pass almost regardless of behaviour. | `tests/test_commands_dispatch.py` | T3.7 |

**Strengths to keep:** a hard request budget for Lite, a concurrency guard before Doctor, strict human-only approval (`looks_like_approval`), repo allowlist and routing that ignores model-suggested repos, the "closed ≠ fixed" rule, secret redaction, and bounded, validated replay of persisted events. None of the tasks below may weaken these.

---

## 2. Hermes facts the executor must use (don't guess these)

Source: hermes-agent @ `d350422b`. Paths are relative to that repo.

### 2.1 Hook kwargs (all hooks are called with **keyword args only**; always accept `**kwargs`)

| Hook | Kwargs Hermes actually sends (relevant ones) | Fire site |
|---|---|---|
| `pre_tool_call` | `tool_name: str`, `args: dict`, `task_id`, `session_id`, `turn_id`, `tool_call_id` (IDs may be `""`) | `model_tools.py` → `hermes_cli/plugins.py::_dispatch_pre_tool_call_hooks` |
| `post_tool_call` | `tool_name`, `args: dict`, `result: str` (always a JSON string), `task_id`, `session_id`, `tool_call_id`, `turn_id`, `api_request_id`, `duration_ms: int`, `status: "ok"\|"error"`, `error_type: str\|None`, `error_message: str\|None`, `middleware_trace` | `model_tools.py` ~L680–700 |
| `pre_llm_call` | `session_id`, `user_message`, `conversation_history`, `is_first_turn`, `model`, `platform`. **The return value is injected into the user message, so ALWAYS return `None`.** | `agent/turn_context.py` |
| `post_llm_call` | `session_id`, `user_message`, `assistant_response: str`, `conversation_history`, `model`, `platform` (only on successful turns) | `agent/turn_finalizer.py` |
| `pre_api_request` | `task_id`, `turn_id`, `api_request_id`, `session_id`, `platform`, `model`, `provider`, `base_url`, `api_mode`, `api_call_count`, `retry_count`, `message_count`, `tool_count`, `approx_input_tokens`, `request_char_count`, `max_tokens`, `started_at` (epoch s), `request` (sanitized). ⚠ It also sends `user_message`, `conversation_history`, `request_messages`, and `system_prompt` **raw**. Never read or store these. | `agent/turn_api_request.py` |
| `post_api_request` | `task_id`, `turn_id`, `api_request_id`, `session_id`, `platform`, `model`, `provider`, `base_url`, `api_mode`, `api_call_count`, `api_duration` (**seconds**, float), `started_at`, `ended_at`, `first_chunk_at` (epoch s or `None`), `finish_reason`, `message_count`, `response_model`, `response` (sanitized dict; tool calls at `response["assistant_message"]["tool_calls"]`, each normally `{"id","type","function":{"name","arguments"}}`; read defensively), `usage`, `assistant_message` (raw; don't store), `assistant_content_chars: int`, `assistant_tool_call_count: int` | `agent/turn_response_intake.py` |
| `api_request_error` | `task_id`, `turn_id`, `api_request_id`, `session_id`, `platform`, `model`, `provider`, `base_url`, `api_mode`, `api_call_count`, `api_duration`, `started_at`, `ended_at`, `status_code: int\|None`, `retry_count`, `max_retries`, `retryable: bool\|None`, `reason: str\|None`, `error: {"type": str, "message": str}` (a **dict**; the message may contain user data, so never store it) | `agent/api_request_hooks.py` |
| `on_session_start` | `session_id`, `model`, `platform`. Fires once per **new** session. | `agent/conversation_loop.py` |
| `on_session_end` | `session_id`, `completed: bool`, `interrupted: bool`, `model`, `platform`. ⚠ Fires at the end of **every turn** (`run_conversation()`), not once per session. | `agent/turn_finalizer.py`, `cli.py` |
| `on_session_finalize` | `session_id: str\|None`, `platform`. Fires on real teardown (`/new`, quit). | CLI/gateway teardown |
| `agent_loop_stopped` | `session_key`, `platform`, `reason`, `invalidation_reason` (a turn was interrupted mid-run) | `gateway/run_agent_cache.py` |

Hook runtime rules (`website/docs/user-guide/features/hooks.md`, section "Plugin Hooks"):
- Callback exceptions are logged and skipped, **except `pre_tool_call`**: if it raises or times out, Hermes **fails closed and blocks the tool**. So the plugin's `pre_tool_call` callback must be trivial, must never do I/O, and must never raise.
- Hot-path hooks have a default 30 s timeout (`plugins.hook_callback_timeout`).

### 2.2 Plugin API (`hermes_cli/plugins.py`)

- `ctx.register_cli_command(name, help, setup_fn, handler_fn=None, description="")`: the handler gets an `argparse.Namespace` and returns an int exit code.
- `ctx.register_command(name, handler, description="", args_hint="", argument_mode=None)`: `handler(raw_args: str) -> str | None`. It may be **sync or async**. It can't shadow a built-in command.
- `ctx.register_hook(name, callback)`: the name must be in `hermes_cli.plugins.VALID_HOOKS`.
- `ctx.get_config(key, default)`: reads `plugins.entries.<plugin_id>.settings.<key>`, falling back to the legacy `.config.<key>`.
- `ctx.on_unload(callback)`: cleanup when the plugin is unloaded or reloaded.
- `ctx.register_tool(...)`: lets the agent call a plugin tool (used in T5.4).
- Manifest (`hermes_cli/plugins_manifest.py`, `SUPPORTED_MANIFEST_VERSION = 2`) fields: `name`, `version`, `description`, `author`, `license`, `manifest_version`, `requires_hermes` (e.g. `">=0.21"`), `provides_hooks`, `provides_tools`, `requires_env`, `python_dependencies` (validated, never auto-installed), `config_schema` (types: `str|int|float|bool|list|dict|secret`), `capabilities`, `platforms`.
- `hermes plugins validate <dir>` is the catalog admission check: manifest schema, isolated `register()` probe, declared-vs-registered hooks and tools, security scan. There's a reusable action: `NousResearch/hermes-agent/.github/actions/plugin-validate`.
- Provider/credential resolution: `hermes_cli.runtime_provider.resolve_runtime_provider(requested=None, explicit_api_key=None, explicit_base_url=None, target_model=None) -> dict` with keys including `provider`, `base_url`, `api_key`, `api_mode`.
- Hermes home: `hermes_constants.get_hermes_home()` (honours context-local overrides, then `HERMES_HOME`, then the default).
- Tool-loop guardrails: `agent/tool_guardrails.py` (`IDEMPOTENT_TOOL_NAMES`, `MUTATING_TOOL_NAMES`, "idempotent_no_progress" = same args + same result). `agent/tool_result_classification.py::is_guardrail_refusal(result) -> bool` detects synthetic guardrail refusals in tool results.

### 2.3 Minefield API (`minefield/api.py` @ `7b324f86`)

- `plan_checks(*, target=None, base_url=None, mode="lite", max_requests=None, capabilities=None, api_key=None, model=None, hf_repo=None, detect=False) -> ProbePlan`
- `run_checks(plan, *, api_key=None, hf_repo=None, hf_revision="main", model=None) -> RunResult`
- `RunResult` fields: `requests_planned`, `requests_executed`, `request_budget`, `findings`, `budget_exceeded: bool`, **`error: str|None`**, **`reachable: bool`**, `stack`, `coverage_line`.
- `detect_target(base_url, *, api_key=None, model=None, …) -> TargetInfo` (GET probes only).

---

## 3. Target architecture (where we're heading)

```
Hermes hooks ──► recorder/hooks.py  (pure mapping: Hermes kwargs → RecorderEvent; no I/O; never raises)
                     │  enqueue (lock-free-ish, O(1))
                     ▼
              recorder/store.py  (ring buffer + background flusher thread → per-process segment files)
                     │
   /minefield wtf ──►│ freeze (memory + bounded tail of recent segments, dedupe)
                     ▼
              incident/signals.py (pure) → incident/rules.py (one pure fn per rule, priority-ordered)
                     ▼
              IncidentArtifact → render (human text | --json) → optional save → contribute (human-gated)

/minefield check|doctor ──► target.py (Hermes runtime_provider → base_url + api_key)
                          ──► minefield.api (budgeted) ──► result validation (reachable/error) ──► cache (TTL)
```

Principles: hooks are pure mappers; all I/O happens off the hot path; every classification rule is a small pure function with its own fixture; every command returns a structured dict, and the text is rendered from it.

---

## 4. The plan

### 4.0 Milestones (the schedule)

**Milestone A: make it trustworthy.** Order matters. Hot-path safety comes right after the hook fix, because once T1.1 lands the plugin records real data and people start relying on it.

1. T0.1 dev environment → T0.2 lint → T0.3 pinned CI → T0.4 Hermes validator → **T0.5 Hermes compatibility matrix**
2. T1.1 real Hermes hook contract
3. T1.3 unreachable endpoint is never green, and **T1.8 diagnostic-integrity verdicts** on every command
4. T2.4 no I/O on the hot hook path
5. T1.2 same-args + same-result loop detection
6. T2.5 multi-process-safe recorder
7. T1.4 cache TTL (a cache read is evidence too)
8. T3.8 real Hermes end-to-end scenario suite

**Gate A:** install into one real Hermes environment and run the T3.8 scenario suite: a normal tool-using turn, intentional tool errors, a real no-progress loop, a dead endpoint, and two concurrent Hermes processes. Minefield must classify every scenario correctly, and every command must report an honest `verdict`. Nothing in Milestone B starts until Gate A passes.

**Milestone B: robustness and better diagnosis.** T1.5, T1.6, T1.7, T2.1, T2.2, T2.3, T2.6, T2.7, T2.8, T2.9, T3.1, T3.2, T3.3, T3.4, T3.5, T3.6, T3.7.

**Milestone C: contribution workflow and Hermes-native features.** T4.1–T4.5, T5.1–T5.5.

**Milestone D: release.** T6.1, T6.2, T6.3. T6.4 (catalog) stays locked until the owner approves it in writing **and** Gate A's scenario suite passes on the release commit.

### Phase 0: Baseline and tooling (no behaviour change)

- [x] **T0.1 Reproducible dev environment script**
  - **Why:** Every later task needs the same local setup, including a real Hermes install for contract tests.
  - **Do:**
    1. Create `scripts/dev_setup.sh` (bash, `set -euo pipefail`). It should:
       - Create `.venv` with `python3 -m venv .venv`, unless it already exists.
       - Clone `https://github.com/Blackwellboy/model-serving-minefield` into `_deps/model-serving-minefield`, check out the SHA in `MINEFIELD_REF` (default `7b324f86d424c20bce177200851c968c1d70c536`), and `pip install -e` it.
       - `pip install "git+https://github.com/NousResearch/hermes-agent@${HERMES_REF}"` with `HERMES_REF` defaulting to `d350422b15863fc4c0b7962b122b625a0271516c`.
       - `pip install pytest PyYAML ruff` and `pip install -e . --no-deps`.
    2. Add `_deps/` and `.venv/` to `.gitignore` (`.venv/` is already there; add `_deps/`).
    3. Update the README "Development" section to use the script.
  - **Accept:** On a clean checkout, `./scripts/dev_setup.sh && source .venv/bin/activate && pytest -q && hermes --help` all succeed.

- [x] **T0.2 Lint and format config; fix real lint errors**
  - **Why:** F20. `Mapping` is actually undefined in `issues/dedupe.py`. It works today only because of `from __future__ import annotations`.
  - **Do:**
    1. In `pyproject.toml` add:
       ```toml
       [tool.ruff]
       target-version = "py310"
       line-length = 110
       [tool.ruff.lint]
       select = ["E", "F", "W", "I", "B", "UP"]
       ignore = ["E501"]
       ```
    2. In `hermes_minefield/issues/dedupe.py` change `from typing import Any, Optional, Sequence` to `from typing import Any, Mapping, Optional, Sequence`.
    3. Run `ruff check --fix hermes_minefield tests`, then `ruff format hermes_minefield tests`. Review the diff. Only mechanical changes are allowed.
    4. Fix anything that remains by hand. Don't add blanket `# noqa`. A targeted `# noqa: <code>` with a reason is fine.
  - **Accept:** `ruff check` and `ruff format --check` are clean, and `pytest -q` still gives 58 passed.

- [x] **T0.3 CI: pin dependencies, add lint and Python 3.13**
  - **Why:** F22.
  - **Do:** In `.github/workflows/ci.yml`:
    1. Add `ref: 7b324f86d424c20bce177200851c968c1d70c536` to the Minefield checkout step, with a comment explaining how to bump it.
    2. Change the matrix to `["3.11", "3.12", "3.13"]`. *(Done. The plan originally said 3.10, but Hermes itself requires Python `>=3.11,<3.14` and the plugin runs in Hermes's interpreter, so `requires-python` is now `>=3.11`.)*
    3. Add a `lint` job: set up Python 3.12, `pip install ruff`, then `ruff check` and `ruff format --check`.
  - **Accept:** CI is green on the PR.

- [x] **T0.4 Fix manifest for Hermes admission and add Hermes validation to CI**
  - **Why:** F5. `hermes plugins validate .` fails today.
  - **Do:**
    1. In `plugin.yaml`, rename the key `hooks:` to `provides_hooks:`. Keep the same list.
    2. Add a `validate` job to CI:
       ```yaml
       validate:
         runs-on: ubuntu-latest
         steps:
           - uses: actions/checkout@v4
           - uses: NousResearch/hermes-agent/.github/actions/plugin-validate@d350422b15863fc4c0b7962b122b625a0271516c
             with:
               path: .
               hermes-ref: d350422b15863fc4c0b7962b122b625a0271516c
       ```
       If the validator can't import `minefield`, first add a step that pip-installs Minefield at the pinned SHA. Note in the PR whether that step was needed.

       *As implemented:* the upstream `plugin-validate` action can't be used. It runs `pip install git+…hermes-agent`, and Hermes's `setup.py` refuses wheel builds outside Nix. CI clones Hermes and installs it editable instead. The validator's security scan walks the whole directory, so `scripts/validate_plugin.sh` validates a scratch copy of the git-tracked files. That keeps `.venv/` and `_deps/` out of the scan, and it matches what the catalog installs.
  - **Accept:** `hermes plugins validate .` prints `✓ declared hooks — matches registrations` and exits 0, both locally and in CI.

- [x] **T0.5 Hermes compatibility matrix** (depends on T0.4)
  - **Why:** The original bug came from coding against an assumed Hermes contract. Pinning one Hermes SHA reproduces today's behaviour, but the manifest will advertise a *range* (`requires_hermes`). CI has to prove that range.
  - **Do:**
    1. Declare the supported range as `>=0.21,<0.22` for now. Widen it only after CI proves the wider range.
    2. Add a CI job `hermes-compat` with a matrix over three Hermes refs:
       - minimum supported release: `v2026.8.31` (0.21.0), commit `29112bef099274229cadff79cdff7bf7b99c4b77`
       - pinned known-good: `d350422b15863fc4c0b7962b122b625a0271516c`
       - latest release: `v2026.9.24` (0.21.5), commit `f97608f178d1ffeca59860195ab7da295f7c8e5f`

       Add a fourth, non-blocking (`continue-on-error: true`) entry for Hermes `main`, so upcoming breaks show up early.
    3. Each matrix entry installs that Hermes ref, runs `hermes plugins validate .`, and runs `tests/test_hermes_contract.py`. That test:
       - asserts every hook in `plugin.yaml` `provides_hooks` is in that version's `hermes_cli.plugins.VALID_HOOKS`,
       - parses Hermes's own fire sites for the kwargs names the plugin relies on (for example, `ast`-walk `model_tools.py` for the `invoke_hook("post_tool_call", ...)` call and collect its keyword names). It fails if a key listed in `tests/fixtures/hermes_hook_payloads.json` is missing from that Hermes version,
       - replays the contract fixtures through Hermes's own `invoke_hook` with the plugin loaded.
    4. When bumping the known-good pin or widening the range, update this list and the §2 tables in the same PR.
  - **Accept:** All three blocking matrix entries are green. Deliberately renaming a key in the fixture makes the job fail.
  - *As implemented:* the matrix found two real differences in 0.21.0: it doesn't send `post_api_request.first_chunk_at`, and it never fires `agent_loop_stopped`. It also has no `hermes plugins validate` command. The fixture marks those as `optional_reads`/`optional_hook`. The plugin must record UNKNOWN when they're absent, and every other key is enforced on every version. The validator step runs only where the command exists.

---

### Phase 1: Critical correctness (make `wtf` and `check` tell the truth)

- [x] **T1.1 Match the recorder hooks to Hermes's real kwargs** (depends on T0.1)
  - **Why:** F1, F2, F3, F4. This is the most important task in the plan.
  - **Do:**
    1. Create `tests/fixtures/hermes_hook_payloads.json`. It holds one realistic kwargs example per hook, copied from the tables in §2.1 with fake values: `session_id: "sess-1"`, `args: {"path": "a.py"}`, `result: "{\"ok\": true}"`, and so on. Include one `post_tool_call` with `status: "error"`, `error_type: "tool_error"`, and one `api_request_error` with `status_code: 503, error: {"type": "APIStatusError", "message": "secret-ish text"}`. This fixture is the **contract**. Add a header field `"_source": "hermes-agent@d350422b hooks.md + fire sites"`.
    2. Create `tests/test_hook_contract.py`. Load the fixture, call each `hermes_minefield.recorder.hooks.on_*` function with `**payload`, then assert on the recorded events:
       - Two `pre_tool_call` payloads with different `args` produce **different** `tool_arg_fingerprint` values. Identical `args` produce the same one.
       - `post_tool_call` with `status="error"` produces `tool.executed(success=False)` plus `tool.failed` with `error_class == "tool_error"`. With `status="ok"` it produces `tool.completed`.
       - `post_tool_call` records `wall_ms == duration_ms`.
       - `post_api_request` records `wall_ms == api_duration * 1000`, `ttft_ms == (first_chunk_at - started_at) * 1000` (only when both are numbers), `content_len == assistant_content_chars`, `finish_reason`, and `request_id_hash` derived from `api_request_id`.
       - `api_request_error` records `http_status == status_code` and `error_class == error["type"]`. The error **message string must not appear anywhere** in `json.dumps(event.to_dict())`.
       - `post_llm_call` records `content_len == len(assistant_response)`.
       - No event's `to_dict()` contains the raw `args` values, `result` text, `user_message`, `conversation_history`, or `system_prompt`. Grep the JSON for the fixture's sentinel strings.
       - Every hook function returns `None`. This matters for `pre_llm_call`, because anything else gets injected into the prompt.
       - Run the tests and watch them fail before changing code.
    3. Fix `hermes_minefield/recorder/hooks.py`:
       - `on_pre_tool_call(tool_name="", args=None, **kwargs)`: fingerprint `args`. For backwards compatibility, if `args is None` use `kwargs.get("params")`.
       - `on_post_tool_call(tool_name="", args=None, result=None, **kwargs)`: same `args` fallback. `success = (kwargs.get("status") != "error")` when `status` is present. Otherwise fall back to the old `error`/`exception` check. `error_class = kwargs.get("error_type") or ("error" if not success else None)`. `wall_ms = _as_float(kwargs.get("duration_ms"))`. **Never** record `error_message`.
       - Add a helper `_req_hash(kw)` that returns `stable_hash(kw.get("api_request_id") or kw.get("request_id"), n=12)` or `None`. Use it in all API and turn hooks.
       - `on_post_api_request`: `http_status` isn't sent on success, so leave it `None`. `wall_ms = api_duration * 1000` when numeric, else the legacy `wall_ms`/`duration_ms`. Compute `ttft_ms` from `first_chunk_at - started_at` when both are numbers and the result is ≥ 0. `content_len = assistant_content_chars` (legacy fallback `content_len`). Put `tool_calls_requested = assistant_tool_call_count` in `extra`.
       - `on_api_request_error`: `err = kw.get("error")`. If it's a dict, `error_class = str(err.get("type") or "error")`. If it's an exception, use `type(err).__name__`. Otherwise use `kw.get("error_class") or "error"`. `http_status = status_code` (legacy `status`/`http_status`). Put `retryable` and `retry_count` in `extra` (bool/int only).
       - `on_post_llm_call`: `content = kw.get("assistant_response") or kw.get("content") or kw.get("response") or ""`.
       - `on_session_end`: store `completed` and `interrupted` as bools in `extra`.
    4. Update the existing fixtures and tests that relied on `params=` only if they break, and say which ones in the PR.
  - **Accept:** The new contract tests pass. The review repro now classifies 12 distinct `read_file` calls as **not** `AGENT_TOOL_LOOP`. Add that repro as a test named `test_distinct_reads_are_not_a_loop`.

- [x] **T1.2 Loop detection needs "same args AND same result"** (depends on T1.1)
  - **Why:** F7. Repeating a call is only a loop if it makes no progress.
  - **Do:**
    1. Add an optional field `result_fingerprint: Optional[str] = None` to `RecorderEvent` in `recorder/events.py`. Parse it in `from_dict`.
    2. In `on_post_tool_call`, set `result_fingerprint = stable_hash(result, n=16)` when `result` is a `str`. Otherwise hash `json.dumps(result, sort_keys=True, default=str)`. Store the hash only.
    3. In `incident/classify.py::compute_signals`, key equivalence on `(tool_arg_fingerprint, result_fingerprint)` when `result_fingerprint` is present. When it's missing (old persisted events), fall back to args only.
    4. Tests:
       - 12× same args + same result → `AGENT_TOOL_LOOP`.
       - 12× same args + different results (for example `terminal "date"`) → **not** a loop.
       - Old-format events without `result_fingerprint` still classify as before, using the existing fixture `fixtures/wtf_real_tool_loop.json`.
  - **Accept:** All three tests pass, and the existing fixture tests still pass.

- [x] **T1.3 `check`/`doctor` must fail loudly when nothing ran**
  - **Why:** F6.
  - **Do:** In `commands/check.py` and `commands/doctor.py`, after `run_checks(...)`:
    1. If `getattr(result, "reachable", True) is False` or `getattr(result, "error", None)`, return `{"ok": False, "text": "Minefield Lite could not reach <redacted url shape>: <error>", "requests_executed": result.requests_executed, "error": result.error}`. Use `privacy.redact_text` on anything you print. **Don't cache.**
    2. If `result.requests_executed == 0` and there are no findings, return `ok: False` with the text "No probes executed (endpoint unreachable, or no applicable probes for this stack). Nothing cached." **Don't cache.**
    3. If `getattr(result, "budget_exceeded", False)`, return `ok: False` with the text `HARD_BUDGET_VIOLATION`. Don't cache.
    4. Tests: monkeypatch `minefield.api.plan_checks/run_checks/summarize` (see `tests/test_doctor_exit.py` for the pattern) to return a result with `reachable=False`. Assert `ok is False`, `get_entry(fp) is None`, and the CLI exit code is 1. Do the same for the zero-requests case.
  - **Accept:** Tests pass. Manually, `hermes minefield check --base-url http://127.0.0.1:9/v1` exits 1 with a clear message, and `hermes minefield status` shows `cache: none`.

- [x] **T1.4 Enforce cache TTL**
  - **Why:** F9.
  - **Do:** `cache.get_entry(fingerprint, *, ttl_days: Optional[int] = None)` returns `None` when `ttl_days` is set and `not is_fresh(entry, ttl_days=ttl_days)`. Pass `cfg.fingerprint_cache_ttl_days` from `check.py`. `status.py` should show stale entries as `"<age> ago (lite, STALE)"` rather than hiding them. Add tests with a monkeypatched `time.time`.
  - **Accept:** A cached entry older than the TTL causes `check` to re-run (not return `cached: True`).

- [x] **T1.5 No exception ever escapes a command**
  - **Why:** F13. Slash-command exceptions surface as raw tracebacks in chat.
  - **Do:**
    1. In `commands/dispatch.py`, add `_guard(fn, **kw) -> dict`. It calls `fn(**kw)` and catches `ValueError` and `PermissionError`, returning `{"ok": False, "text": str(e)}`. It catches any other `Exception`, returning `{"ok": False, "text": f"minefield: internal error ({type(e).__name__}). Run with HERMES_PLUGINS_DEBUG=1 for details."}`, and logs it with `logger.debug(..., exc_info=True)`. Use it for every command in both `handle_cli` and `handle_slash`.
    2. In the slash path, parse `--max-requests` with try/except, and reply "`--max-requests` must be an integer" on error.
    3. Document exit codes in the README, as defined in T1.8: `0` PASS, `1` FAIL or internal error, `2` blocked/needs confirmation, `3` UNKNOWN.
    4. Tests: slash `check` with no config and no base_url returns a string containing "base_url", with no raise. Slash `check --max-requests abc` returns the integer message. CLI returns 1 for both.
  - **Accept:** Tests pass. `grep -n "raise" hermes_minefield/commands/*.py` shows only deliberate raises inside helpers.

- [x] **T1.6 `wtf` doesn't save noise; contribute doesn't match itself**
  - **Why:** F12, F14.
  - **Do:**
    1. In `commands/wtf.py`, add a `save: Optional[bool] = None` parameter. The default rule is: persist unless `classification in {"UNKNOWN", "EXPECTED_BEHAVIOUR"}` and `severity == "LOW"`. Add CLI flags `--save`/`--no-save` and the slash equivalents. When not saved, the rendered text ends with "(not saved — quiet window; use --save to keep)" and the `contribute` hints are left out. Note: `analyze_events(persist=...)` already exists. Compute first, then decide, then call `save_incident`.
    2. In `commands/contribute.py`, filter the current `incident_id` out of `known` before calling `search_local`.
    3. Tests for both behaviours.
  - **Accept:** A quiet `wtf` writes no file in `incidents/`. `contribute` never lists its own incident as a duplicate.

- [x] **T1.7 Replace `assert` with real checks**
  - **Why:** F21.
  - **Do:** In `commands/check.py`, replace both `assert`s with `if …: raise RuntimeError("HARD_BUDGET_VIOLATION: …")`. They're caught by T1.5's guard and reported. Remove the `assert` in `render.extract_summary_counts`, which is unreachable. Keep the logic.
  - **Accept:** `grep -rn "^\s*assert " hermes_minefield` returns nothing.

- [x] **T1.8 Diagnostic-integrity verdicts on every command** (Milestone A, alongside T1.3)
  - **Why:** It enforces §0 rule 7 in code, not just in prose.
  - **Do:**
    1. Add `hermes_minefield/verdict.py` with `PASS = "PASS"`, `FAIL = "FAIL"`, `UNKNOWN = "UNKNOWN"`.
    2. Every command result dict gets a `verdict` key, and the rendered text starts or ends with `Verdict: <X>`:
       - `check`/`doctor`: `UNKNOWN` when unreachable, when zero probes ran, or when the target can't be resolved. `FAIL` when any finding is a problem. `PASS` only when probes ran and every finding is clean. Inconclusive findings with no problems → `UNKNOWN`.
       - `wtf`: `UNKNOWN` when the frozen window has no events, or when the recorder reports a gap. `FAIL` when the classification is an anomaly. `PASS` only for `EXPECTED_BEHAVIOUR` with events present.
       - `status`: shows the cached verdict and marks a stale cache as `UNKNOWN (stale)`.
    3. Exit codes: `PASS` → 0, `FAIL` → 1, `UNKNOWN` → 3, blocked/needs confirmation → 2, internal error → 1.
    4. A test per command proves that "couldn't test" never renders as `PASS`.
  - **Accept:** `grep -rn "verdict" hermes_minefield/commands` shows every command setting it. The tests pass.

---

### Phase 2: Robustness and correct Hermes plumbing

- [x] **T2.1 Resolve Hermes home the Hermes way**
  - **Why:** F18.
  - **Do:** In `paths.hermes_home()`, first try `from hermes_constants import get_hermes_home; return Path(get_hermes_home()).expanduser().resolve()`. On `ImportError`, fall back to `HERMES_HOME`/`HERMES_HOME_DIR`, then to `~/.hermes`. Tests: with `hermes_constants` importable (Hermes is installed in the dev env), `HERMES_HOME` set via monkeypatch is still honoured, because Hermes reads it. With `sys.modules["hermes_constants"] = None` (which simulates it being absent), the env fallback works.
  - **Accept:** Tests pass. The existing `tmp_hermes_home` fixture still isolates everything.

- [x] **T2.2 Canonical, validated config**
  - **Why:** F17.
  - **Do:**
    1. In `MinefieldPluginConfig.from_mapping`, the lookup order is: `plugins.entries["hermes-minefield"].settings` → `plugins.entries["hermes-minefield"].config` → `plugins.entries["hermes-minefield"]` (legacy) → top-level `minefield:` (legacy).
    2. Add a helper `_int(section, key, default, lo, hi)` that coerces and clamps, and on bad input logs one warning and uses the default. Bounds: `lite_max_requests` 0–5; `recorder_retention_seconds` 60–86400; `recorder_max_events` 100–100000; `recorder_max_bytes` 64 KiB–256 MiB; `fingerprint_cache_ttl_days` 1–365.
    3. `register()` must never raise because of config. Test this with `lite_max_requests: "abc"`.
    4. Add a README section showing the canonical YAML:
       ```yaml
       plugins:
         enabled: [hermes-minefield]
         entries:
           hermes-minefield:
             settings:
               lite_max_requests: 5
               recorder_retention_seconds: 600
               repo_allowlist: [Blackwellboy/model-serving-minefield, NousResearch/hermes-agent]
       ```
  - **Accept:** Tests cover all 4 lookup locations and the bad-value cases.

- [x] **T2.3 Target resolution through Hermes, with API key support**
  - **Why:** F8.
  - **Do:**
    1. Add an `api_key: Optional[str] = field(default=None, repr=False)` field to `ResolvedTarget`. Use `repr=False` so it never prints.
    2. In `resolve_target`, when no explicit `base_url` is given, first try:
       ```python
       from hermes_cli.runtime_provider import resolve_runtime_provider

       rt = resolve_runtime_provider(target_model=model)  # may raise
       ```
       Use `rt.get("base_url")`, `rt.get("api_key")`, and `rt.get("provider")`, with `source="hermes_runtime"`. On any exception, or when there's no `base_url`, fall back to the existing config parsing, which stays as-is.
    3. With an explicit `--base-url`, don't attach Hermes credentials unless the URL equals the runtime `base_url` after `rstrip("/")`. This avoids sending a key to a different host.
    4. Pass `api_key=target.api_key` to `plan_checks`, `run_checks`, and `detect_target`. In `concurrency.probe_concurrency(base_url, api_key=None)`, add an `Authorization: Bearer` header when a key is present.
    5. The key must never appear in output, cache, incidents, drafts, or logs. Add a test that sets a sentinel key and greps all files under `tmp_hermes_home` and all returned `text` for it.
    6. Tests use monkeypatched `resolve_runtime_provider` (success, raises, and returns no base_url).
  - **Accept:** Tests pass. The sentinel key is never found.

- [x] **T2.4 No disk I/O on the hook hot path**
  - **Why:** F15.
  - **Do:**
    1. In `FlightRecorder.record()`: append to the ring buffer and `_pending_flush`, then `self._wake.set()` if the pending count is ≥ 32. **No file I/O here.**
    2. Add a daemon flusher thread, started lazily on the first `record()` when `persist=True`. It loops `self._wake.wait(timeout=2.0)`, then swaps out the pending list under the lock and writes it **outside** the lock. Add `stop()` to set a stop flag, wake the thread, join with a 2 s timeout, and do a final flush.
    3. `flush()` and `freeze_detailed()` still flush synchronously. They run in command context, not hooks.
    4. `register()` calls `ctx.on_unload(lambda: get_recorder().stop())` when `hasattr(ctx, "on_unload")`, and also `atexit.register(...)`.
    5. `reset_recorder_for_tests()` must stop any previous global recorder.
    6. Tests: `record()` doesn't touch disk (monkeypatch `Path.open` to raise; `record()` must still succeed). After `flush()`, the events are on disk. `stop()` is idempotent.
  - **Accept:** Tests pass. A microbench (`python -m timeit`) on `record()` shows no regression from the ~10 µs/event in `docs/DOGFOOD_20260825.md`. Report the numbers in the PR.

- [x] **T2.5 Multi-process-safe persistence (segment files)**
  - **Why:** F16. The CLI and gateway can run at the same time.
  - **Do:**
    1. Each `FlightRecorder` writes only to its own segment, `recorder/events-<pid>-<start_ts_int>.jsonl`, in append-only mode. Nothing ever rewrites another process's file.
    2. Rotation: when your own segment exceeds `max_bytes / 4`, close it and start a new segment. Cleanup is done by whichever process flushes. It deletes segments whose **mtime** is older than `retention_seconds + 60`. If total size is over `max_bytes`, it deletes the oldest segments until it's under. Deleting a file another process has open is safe on POSIX. On Windows, catch `PermissionError` and skip.
    3. `load_recent_persisted_events()` reads the newest segments by mtime, tail-reading at most `max_bytes` in total. It keeps reading the legacy `events.jsonl` if present, for one release.
    4. Keep all the existing validation (schema, timestamp sanity, dedupe).
    5. Tests: two recorder instances with different `path`/segment dirs write interleaved events, and a third process-free reader sees all of them. Rotation deletes old segments. The legacy file is still read.
  - **Accept:** Tests pass. `tests/test_cross_process_wtf.py` still passes, possibly adapted to segments. Explain any adaptation.

- [x] **T2.6 Atomic, private file writes**
  - **Why:** F16.
  - **Do:** Add a helper `paths.atomic_write_text(path, text)`. It writes to a `NamedTemporaryFile` in the same dir, fsyncs, `os.chmod(tmp, 0o600)`, then `os.replace`. `paths.minefield_root()` and its subdirs are created with mode `0o700`. Use `os.chmod` after `mkdir`, and ignore errors on Windows. Use the helper in `cache.save_cache`, `incident.store.save_incident`/`update_incident_status`, `issues.draft.save_draft`, and `contribute.candidate.save_candidate`. Segment files from T2.5 are opened with `os.open(..., 0o600)`.
  - **Accept:** A test asserts the file modes are `0o600` (skip on Windows), and that no partial file is left behind if `json.dumps` raises.

- [ ] **T2.7 Bounded incident storage**
  - **Why:** F14.
  - **Do:** Add the config `incident_retention_days` (default 90, range 1–3650) and a new command `hermes minefield prune [--older-than 30d] [--dry-run]`, also available as slash `/minefield prune`. It deletes old `INC-*.json`, `CAND-*.json`, and `draft-*.json` files. `save_incident` compacts `index.jsonl` to the last 1000 lines whenever it has more than 2000. Incidents linked to an open GitHub issue (T4.1) are never pruned.
  - **Accept:** Tests pass. `--dry-run` deletes nothing.

- [x] **T2.8 Stop mutating `sys.path` at plugin load**
  - **Why:** F19.
  - **Do:** Change the root `__init__.py` to `from .hermes_minefield.plugin import register`, and delete the `sys.path` code. All intra-package imports in `hermes_minefield/` are already relative. Check with `grep -rn "^from hermes_minefield\|^import hermes_minefield" hermes_minefield`, which must return nothing. Tests keep working through `pythonpath = ["."]`.
  - **Accept:** `hermes plugins validate .` passes. After symlinking into `$HERMES_HOME/plugins/`, `hermes minefield status` works (use the e2e script from T3.8). If Hermes turns out not to load the root as a package, **stop**. Record it in the PR and in §6.

- [x] **T2.9 Flush on real session teardown only**
  - **Why:** `on_session_end` fires on every turn (§2.1). Recording `session.end` every turn is misleading.
  - **Do:** Map `on_session_end` to a new event type `TURN_FINISHED = "turn.finished"` with `completed`/`interrupted` in `extra`. Map `on_session_finalize` to `SESSION_END` and flush. Register `agent_loop_stopped` → `ORCH_CANCEL`, with `reason` in `extra` only if it's a short enum-like string (≤ 40 chars, `[a-z_]+`). Add `agent_loop_stopped` to `provides_hooks`. Keep `from_dict` accepting `session.*` and `turn.*`.
  - **Accept:** Contract tests are updated and pass. The validator passes.

---

### Phase 3: Diagnostics quality (make `wtf` genuinely useful)

- [x] **T3.1 Honest tool lifecycle: prepared → requested → executed**
  - **Why:** F24.
  - **Do:**
    1. `on_pre_tool_call` emits **only** `TOOL_REQUESTED`, with `request_id_hash` and, when present, `tool_call_id_hash` in `extra`.
    2. `on_post_api_request` emits one `TOOL_PREPARED` per entry in `response["assistant_message"]["tool_calls"]`, holding the tool name only (`tc.get("function", {}).get("name")`) and `tool_call_id_hash`. It must read defensively and never store `arguments`.
    3. `on_post_tool_call` is unchanged: `TOOL_EXECUTED` plus `COMPLETED`/`FAILED`.
    4. Update the classifier so the UI rule means: **the model emitted tool calls that Hermes never executed**. Compare prepared vs requested per `tool_call_id_hash` when available, otherwise by count. Rename its root-cause text accordingly ("model-emitted tool calls were not dispatched: blocked by guardrail/approval, dropped, or orchestration bug"). Keep the classification constant `HERMES_UI_ORCHESTRATION` for compatibility, and add an `extra` note.
    5. Add a new signal, `STARTED_NOT_FINISHED`: a `tool.requested` event with no matching `tool.executed` (by `tool_call_id_hash`) for more than 120 s at freeze time. Report it as "tool appears hung: `<tool>`".
    6. Create new fixtures `fixtures/wtf_v2_*.json` using the new semantics. **Keep** the old fixtures and their tests as `legacy` to prove that events persisted by older versions still classify.
  - **Accept:** On a real Hermes session (T3.8 e2e), a normal turn with tool calls classifies as `EXPECTED_BEHAVIOUR`, not `UNKNOWN`.

- [x] **T3.2 Streak-based loop detection that mirrors Hermes guardrails**
  - **Why:** F7, and it makes the `NO_PROGRESS_STREAK` field real instead of approximated.
  - **Do:**
    1. Move `compute_signals` into a new module, `incident/signals.py`. Leave a re-export in `classify.py`.
    2. Compute, per session and in timestamp order, `longest_no_progress_streak`: the longest **consecutive** run of `tool.executed` events with identical `(tool_name, tool_arg_fingerprint, result_fingerprint)`.
    3. Vendor a copy of Hermes's `IDEMPOTENT_TOOL_NAMES` into `incident/tool_classes.py`, with a comment citing `agent/tool_guardrails.py@d350422b`. Try importing the live set from `agent.tool_guardrails` at runtime first, and fall back to the copy.
    4. `AGENT_TOOL_LOOP` fires when `longest_no_progress_streak >= loop_streak_threshold` (new config, default 5, range 3–50). For mutating tools, it also needs the same result, and the confidence is `MEDIUM` rather than `HIGH`.
    5. `render_incident` prints the real `NO_PROGRESS_STREAK`.
  - **Accept:** Tests: 6 identical `read_file` calls in a row → loop, HIGH. The same 6 interleaved with other tools (streak ≤ 2) → not a loop. 6 `terminal` calls with the same args and same result → loop, MEDIUM.

- [x] **T3.3 Guardrail visibility**
  - **Why:** It replaces the `GUARD_WARNINGS=unknown` and `GUARD_BLOCKS=unknown` placeholders.
  - **Do:** In `on_post_tool_call`, try `from agent.tool_result_classification import is_guardrail_refusal`, cached at module import inside a try. When it returns True for the result, set `extra["guardrail_refusal"] = True`. Count these in signals as `guard_blocks`. If the import isn't available, the counts render as `unknown`, the same as today. Warnings aren't observable through hooks, so keep `GUARD_WARNINGS=unknown` and add a parking-lot note.
  - **Accept:** A test with a monkeypatched `is_guardrail_refusal` shows `GUARD_BLOCKS=1`.

- [x] **T3.4 New classification rules (one pure function each)**
  - **Why:** Real incidents are mostly API errors, rate limits, slowness, and tool failures, not just loops.
  - **Do:**
    1. Create `incident/rules.py` with `RULES: list[Callable[[Signals], Optional[ClassificationResult]]]` in priority order. `classify()` returns the first non-None result, or the fallback. Port the existing rules first with **no behaviour change**, and prove it with the existing tests. Then add these:

       | Priority | Rule | Condition (defaults are configurable) | Classification | Severity |
       |---|---|---|---|---|
       | 1 | auth failure | ≥ 1 `api.error` with `http_status in {401, 403}` | `CONFIGURATION_ERROR` | HIGH |
       | 2 | rate limited | ≥ 3 `api.error` with 429 | `PERFORMANCE_CONTENTION` | MEDIUM |
       | 3 | server errors | ≥ 3 `api.error` with 5xx or no status | `MODEL_SERVER_BUG` | MEDIUM |
       | 4 | tool hang | `STARTED_NOT_FINISHED` ≥ 1 | `TOOL_BUG` | MEDIUM |
       | 5 | tool loop | T3.2 | `AGENT_TOOL_LOOP` | HIGH/MEDIUM |
       | 6 | tool failure storm | ≥ 5 `tool.failed` for one tool | `TOOL_BUG` | MEDIUM |
       | 7 | not dispatched | T3.1 | `HERMES_UI_ORCHESTRATION` | ANNOYING/MEDIUM |
       | 8 | slow model | p95 `api.response.wall_ms` > 60 s, or p95 TTFT > 20 s, with ≥ 3 samples | `PERFORMANCE_CONTENTION` | LOW |
       | 9 | quiet | no tool/API events | `UNKNOWN` | LOW |
       | 10 | aligned | prepared ≈ executed | `EXPECTED_BEHAVIOUR` | LOW |

    2. Each rule gets a fixture in `fixtures/rules/<rule>.json` and a parametrized test. There's also one test that asserts priority order: a window with both 401s and a loop → `CONFIGURATION_ERROR`.
    3. Update `issues/routing.py` if a new classification appears. `TOOL_BUG` → Hermes is already mapped. `CONFIGURATION_ERROR` stays ambiguous, so the user must select.
  - **Accept:** All rule tests pass, and no existing test changes its expected classification.

- [x] **T3.5 Scope `wtf` to the current session by default**
  - **Why:** In multi-session or gateway setups, a window mixes unrelated sessions.
  - **Do:** The recorder tracks `last_session_hash` (updated in every hook that has a `session_id`). Store it in `extra` for persisted rows, so a fresh CLI process can take the session hash of the newest persisted event. `wtf` defaults to `--session current`, which resolves to that hash. `--session all` keeps today's behaviour. The rendered header shows `scope: current session (abc123…)` or `scope: all sessions`.
  - **Accept:** A test with two interleaved sessions, where the looping one is older and the newest is quiet, shows the quiet one by default and the loop with `--session all`.

- [ ] **T3.6 Machine-readable output**
  - **Do:** Add a global `--json` flag to every `hermes minefield` subcommand. It prints `json.dumps(result_without_text, indent=2, sort_keys=True, default=str)`, run through `privacy.sanitize_mapping`. In `render_incident`, remove the duplicated human lines (`Actual executions:`, `Preparations:`, `Repeated equivalent calls:`), which repeat the `KEY=VALUE` block.
  - **Accept:** `hermes minefield wtf --json | python -m json.tool` succeeds. There's a test for each command's JSON shape.

- [ ] **T3.7 Tighten weak tests**
  - **Why:** F25.
  - **Do:** Replace every `assert A or B` in `tests/` with exact assertions against the structured result dict (`classification`, `ok`, `blocked`, …) instead of substring checks on text. Remove the `__import__("yaml").dump(cfg) if False else …` construct in `test_commands_dispatch.py`. List every assertion you changed in the PR.
  - **Accept:** `grep -rn "assert .* or " tests` returns nothing. Coverage (`pytest --cov=hermes_minefield`, dev-only dependency) is ≥ 85%. Report the number.

- [x] **T3.8 End-to-end test against a real Hermes plugin loader**
  - **Why:** It's the regression net for the whole F1–F5 class of bugs.
  - **Do:** Create `tests/e2e/test_hermes_load.py`, marked `@pytest.mark.e2e` and skipped when `hermes_cli` isn't importable. It:
    1. Makes a temporary `HERMES_HOME` with `plugins/hermes-minefield` symlinked to the repo, plus a config that enables it.
    2. Loads plugins with Hermes's own `PluginManager` (find the public loader in `hermes_cli/plugins.py`, for example the function that `hermes plugins list` uses). Asserts the `minefield` command and all `provides_hooks` are registered.
    3. Fires the hooks through Hermes's own `invoke_hook(...)` with the §2.1 kwargs. Runs `handle_slash("wtf 1m --json")` and asserts on the classification.
    4. Adds a CI job `e2e` that installs Hermes at the pinned ref and runs `pytest -m e2e`.
    5. Scenario suite (Gate A). Each scenario drives Hermes's `invoke_hook` with realistic kwargs, then asserts both the classification and the verdict:
       - normal tool use (distinct reads, one write) → `EXPECTED_BEHAVIOUR`, `PASS`
       - intentional tool errors (`status="error"`) → failures recorded, not counted as success
       - a real no-progress loop (same args, same result, consecutive) → `AGENT_TOOL_LOOP`, `FAIL`
       - a dead endpoint for `check` → `UNKNOWN`, nothing cached, exit 3
       - two concurrent recorder processes (use `multiprocessing`) writing at the same time → a fresh `wtf` process sees every event from both, with none lost
  - **Accept:** The e2e job is green in CI and on all T0.5 matrix entries. If the loader API is private or unstable, fall back to calling `hermes minefield status` as a subprocess, and document that.

---

### Phase 4: Contribution workflow hardening

- [ ] **T4.1 Link incidents to submitted issues**
  - **Why:** F11.
  - **Do:** After a successful **non-dry-run** `submit_issue`, parse `owner/repo#number` from the returned `html_url`. Call `update_incident_status(incident_id, "SUBMITTED", github={"repo": …, "number": …, "html_url": …})`. Add `STATUS_SUBMITTED = "SUBMITTED"` to `incident/types.py`. `issues --refresh` then works as designed.
  - **Accept:** A test with a monkeypatched `urllib.request.urlopen` returns a fake issue. The incident JSON then contains `github.number`, and `run_issues(refresh=True)` shows `[OPEN]`.

- [ ] **T4.2 Submit exactly what was previewed**
  - **Why:** The draft is rebuilt between preview and submit. What's submitted should be byte-identical to what the human approved.
  - **Do:** `contribute --github` saves the draft and prints its `draft_id`, which is the file stem. Add a new flag, `contribute --submit-draft <draft_id> --i-approve-submit --submit`. It loads that exact saved draft, shows its SHA-256 (first 12 chars) in both the preview and the confirmation, re-checks `assert_repo_allowed`, and submits the saved `title`/`body` unchanged. The old combined flow stays working.
  - **Accept:** A test proves that the submitted body equals the saved draft body, and that a tampered draft file (hash mismatch against a stored `body_sha256`) is refused.

- [ ] **T4.3 No silent fallback to the wrong incident**
  - **Why:** F12.
  - **Do:** If `--incident X` is given and not found, return `ok: False` with "Incident X not found. Recent: …" (list the 5 newest IDs). The fallback to the latest incident applies only when `--incident` is omitted, and then the output says `using latest incident <id>`.
  - **Accept:** A test covers both paths.

- [ ] **T4.4 Remote duplicate search before submit (read-only)**
  - **Why privacy-first:** Even sanitized title tokens can contain model names, runtime names, failure signatures, or private project terms. The plugin promises local, metadata-only diagnosis, with publication only as a deliberate human step.
  - **Do:** Remote search is **off by default** (`remote_dedupe: false`). It runs only when the user passes `--remote-dedupe` during `contribute --github`, or has set `remote_dedupe: true`. Before anything leaves the machine, print `Searching GitHub for these sanitized terms: <terms>`. Then call `GET /search/issues?q=repo:<repo>+is:issue+in:title+<top 5 tokens>` with a 10 s timeout and show up to 3 hits as "Possible upstream duplicates". Treat any failure as "(remote dedupe unavailable)", never as an error. Nothing except those printed terms is sent.
  - **Accept:** A test with a monkeypatched `urlopen` covers the hits, a timeout, the default-off case (no network call at all), and that the printed terms equal the terms sent.

- [ ] **T4.5 Gateway safety for `--submit`**
  - **Why:** In gateway mode (Telegram, Discord), anyone who can type in the chat can run `/minefield contribute --submit`, and the host's `GITHUB_TOKEN` would be used.
  - **Do:** Add the config `allow_submit_from_chat: false` (default). Slash-mode `--submit` (not dry-run) is refused unless it's enabled. The response says: "Real submission is CLI-only by default. Run: hermes minefield contribute --submit-draft <id> --i-approve-submit --submit". Dry-run stays allowed.
  - **Accept:** A test shows slash `--submit` is refused by default and allowed when configured. The CLI is unaffected.

---

### Phase 5: Hermes-native integration

- [ ] **T5.1 Manifest v2**
  - **Do:** Rewrite `plugin.yaml`:
    ```yaml
    manifest_version: 2
    name: hermes-minefield
    version: 0.2.0            # must equal hermes_minefield/version.py (T6.1 adds a test)
    description: >-
      Model Serving Minefield for Hermes: budgeted Lite check, guarded full Doctor,
      metadata-only flight recorder, /minefield wtf incident analysis, and
      human-gated issue drafting. Opt-in. Never auto-uploads.
    author: Blackwellboy
    license: MIT
    kind: standalone
    requires_hermes: ">=0.21,<0.22"   # must match T0.5's proven range
    python_dependencies:
      - "model-serving-minefield @ git+https://github.com/Blackwellboy/model-serving-minefield@7b324f86d424c20bce177200851c968c1d70c536"
    provides_hooks: [ …the exact registered list… ]
    config_schema:
      lite_max_requests: {type: int, default: 5, description: "Lite request budget (0-5)"}
      recorder_retention_seconds: {type: int, default: 600}
      recorder_max_events: {type: int, default: 5000}
      recorder_max_bytes: {type: int, default: 8388608}
      fingerprint_cache_ttl_days: {type: int, default: 30}
      incident_retention_days: {type: int, default: 90}
      loop_streak_threshold: {type: int, default: 5}
      repo_allowlist: {type: list}
      remote_dedupe: {type: bool, default: false}
      allow_submit_from_chat: {type: bool, default: false}
      auto_lite: {type: str, default: "false", description: "false | true"}
    ```
    **First** read `hermes_cli/plugins_manifest.py::validate_config_schema` at the pinned SHA to confirm the exact `config_schema` entry shape (keys like `type`/`default`/`description`), and adjust to match. If `python_dependencies` doesn't accept a PEP 508 URL, use `model-serving-minefield>=0.1.0` and document the git install in the README.
  - **Accept:** `hermes plugins validate .` is fully green, including `config schema`, `requires_hermes`, and `python dependencies`.

- [ ] **T5.2 Use `ctx.get_config` when available**
  - **Do:** In `register(ctx)`, build the config dict from `ctx.get_config(key, default)` for each schema key when `hasattr(ctx, "get_config")`. Otherwise use T2.2's mapping parser. Store the resolved config in a module-level holder that the commands use, instead of re-reading YAML on every command. Commands still work standalone in tests.
  - **Accept:** A test with a fake ctx exposing `get_config` shows the settings flowing through to `run_check`.

- [ ] **T5.3 Implement or remove `auto_lite`**
  - **Why:** F10. Recommended: implement a **safe** version.
  - **Do:** On the first `on_session_start` per process, if `auto_lite == "true"` and the cache entry for the current target is missing or stale, start a **daemon thread**. It runs `probe_concurrency` first and **skips** unless `known_concurrency >= 2`, then runs `run_check()`. It never blocks the hook and never prints into the chat. The result lands in the cache, and `status` shows it. Drop the `"prompt"` value: map it to `"false"` with a one-time deprecation log.
  - **Accept:** Tests: the hook returns in < 5 ms (thread is mocked). The check is skipped when single-slot or unknown. It runs at most once per process.

- [ ] **T5.4 Optional read-only agent tool (off by default)**
  - **Why:** It lets users say "why did you just do that?" in natural language, and the agent can pull the incident report itself.
  - **Do:** Add the config `expose_agent_tool: false`. When true, `ctx.register_tool(...)` registers a tool `minefield_recent_incident`. Check the exact `register_tool` signature at the pinned SHA first. It takes `{window: "5m"}`, runs `run_wtf(save=False)`, and returns the **structured** artifact: counts, classification, recommendation. It is **read-only**: it can't call contribute, can't save, and can't touch the network. Add it to `provides_tools` only when registered. If the validator requires static declaration, always register it but make it return "disabled in config" when off, and explain which choice you made.
  - **Accept:** The validator passes. A test confirms the tool output contains no file paths, hashes of args, or raw events, just the summary.

- [ ] **T5.5 Async slash handlers for long commands**
  - **Why:** `/minefield doctor --yes` can take minutes and blocks the chat UI thread.
  - **Do:** Register the slash handler as `async def`, and run the sync dispatch in `asyncio.to_thread(...)`. Confirm at the pinned SHA that both CLI and gateway accept async handlers (§2.2 says "sync or async", but verify the CLI path by reading the code that calls plugin command handlers).
  - **Accept:** A test with `asyncio.run(handler("status"))` returns text. The e2e test still passes.

---

### Phase 6: Packaging, docs, release, and getting into Hermes

- [ ] **T6.1 Single version source and README truth**
  - **Do:** `hermes_minefield/version.py` is the source of truth. `pyproject.toml` uses `dynamic = ["version"]` with `[tool.setuptools.dynamic] version = {attr = "hermes_minefield.version.__version__"}`. A test asserts `plugin.yaml` `version` equals `__version__`. Rewrite the README:
    - Install: `hermes plugins install Blackwellboy/hermes-minefield --ref <release-sha> --enable` (the `owner/repo` and `--ref` form is documented in hermes-agent `website/docs/user-guide/features/plugins.md`). Once it's in the catalog: `hermes plugins install hermes-minefield`. The symlink method stays as a "development install".
    - Remove the claim about the `hermes_agent.plugins` entry point.
    - Add sections: config (the T2.2 YAML), exit codes, privacy model (exactly what is and isn't stored), and troubleshooting (`HERMES_PLUGINS_DEBUG=1`).
  - **Accept:** The version test passes. Every command in the README has been run once, and the output is in the PR.

- [ ] **T6.2 CHANGELOG and docs cleanup**
  - **Do:** Add `CHANGELOG.md` (Keep a Changelog format). Its `0.2.0` entry lists F1–F25 fixes by task. Move the dated `docs/*_20260825.md` notes into `docs/history/`. Add `docs/ARCHITECTURE.md` describing the §3 diagram and the event schema, and `docs/CLASSIFICATION.md` with the T3.4 rule table.
  - **Accept:** Links in the README resolve.

- [ ] **T6.3 Release v0.2.0**
  - **Do:** When every task above is ticked, bump the version to `0.2.0`, run the full gate and the e2e suite, and create the tag `v0.2.0` and a GitHub release with the CHANGELOG entry. **The owner creates the tag.** The executor prepares the PR and a release-notes draft only.
  - **Accept:** The release exists, and CI is green on the tagged commit.

- [ ] **T6.4 Hermes plugin catalog submission** 🔒 *Needs written owner approval before starting.*
  - **Why:** This is the proper way into Hermes. The catalog is human-reviewed and pins an exact SHA, and users get `hermes plugins install hermes-minefield`. Upstreaming into Hermes core isn't needed and isn't recommended: Minefield is framework-neutral, and this plugin is the adapter.
  - **Do (after approval):**
    1. Read `plugin-catalog/README.md` in hermes-agent at the then-current `main` for the exact checklist.
    2. Draft `plugin-catalog/hermes-minefield.yaml`: `name`, `repo`, `sha` = the full 40-hex SHA of the `v0.2.0` tag commit, `tier: community`, `category: tools`, `maintainer: Blackwellboy`, `version: "0.2.0"`, `requires_hermes` matching the manifest, and `capabilities` matching the manifest.
    3. Hand the YAML and a PR description to the owner. **The owner opens the PR**, because catalog admission requires the PR author to own the plugin repo.
  - **Accept:** The owner has a ready-to-submit entry, and `hermes plugins validate` is green at the pinned SHA.

---

## 5. Definition of done (whole plan)

- Every task is ticked. CI is green: lint, unit tests on 3.10/3.12/3.13, Hermes `plugins validate`, the T0.5 compatibility matrix, and e2e.
- Every command reports an honest `verdict`. No path turns missing evidence into `PASS`.
- On a real Hermes session, `hermes minefield wtf`:
  - classifies a normal tool-using turn as `EXPECTED_BEHAVIOUR`,
  - flags a genuine same-args/same-result streak as `AGENT_TOOL_LOOP`,
  - flags a 401 as `CONFIGURATION_ERROR`,
  - and never writes raw args, results, prompts, or keys to disk.
- `check` exits non-zero with a clear message when the endpoint is down, and never caches a failed run.
- `v0.2.0` is released, and the catalog entry is ready for the owner.

## 6. Parking lot (executors: append here; don't fix out of scope)

- Salted (per-install HMAC) fingerprints instead of plain SHA-256, so low-entropy args (short paths) can't be brute-forced from local recorder files. Low risk while the files stay local and `0600`. Consider it after T2.6.
- `privacy._IP_LIKE` also redacts 4-part version strings (for example `1.2.3.4`). Consider requiring a non-version context.
- `privacy._ABS_HOME` doesn't cover `/root/` or non-`C:` Windows drives.
- Hermes doesn't expose guardrail *warnings* to plugins (only refusals, through tool results). Suggest an observer hook upstream **only with owner approval**.
- `IncidentArtifact.new_id()` uses 4 hex chars, about 65k per day. Consider 8.
