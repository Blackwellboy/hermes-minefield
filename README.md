# hermes-minefield

A standalone **Hermes Agent plugin** that brings [Model Serving Minefield](https://github.com/Blackwellboy/model-serving-minefield) into Hermes without modifying Hermes core.

Minefield stays framework-neutral. This plugin is the Hermes-specific adapter:

```
model-serving-minefield   registry, Doctor, traps (framework-neutral)
          ↑
hermes-minefield          check / doctor adapter, flight recorder, wtf, contribution workflow
          ↑
Hermes
```

> **Status: experimental (0.2.0).** 0.1.x read the wrong Hermes hook arguments and could report the opposite of what happened. 0.2.0 fixes that and is tested against real Hermes processes on 0.21.0–0.21.5. See [CHANGELOG.md](CHANGELOG.md) and [docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md).

## The integrity rule

Every diagnostic result carries an explicit **verdict**:

| Verdict | Meaning | Exit code |
|---|---|---|
| `PASS` | the target was tested and every finding is clean | 0 |
| `FAIL` | the target was tested and something is wrong | 1 |
| `UNKNOWN` | it could not be meaningfully tested: unreachable, no probes ran, no recorder events, stale cache, a provider Minefield can't probe | 3 |
| (blocked) | needs confirmation, e.g. Doctor on a single-slot server without `--yes` | 2 |

**Missing evidence never becomes negative evidence. `UNKNOWN` is not `PASS`.** Internal errors exit 1 with a message, never a traceback.

## Commands

| CLI (terminal) | Slash (inside a Hermes chat) | What it does |
|---|---|---|
| `hermes minefield check` | `/minefield check` | Lite preflight: at most 5 requests; cached per endpoint fingerprint (30-day TTL) |
| `hermes minefield doctor` | `/minefield doctor` | Full Doctor. Explicit only; asks for `--yes` on single-slot or unknown-concurrency servers |
| `hermes minefield wtf [5m]` | `/minefield wtf [5m]` | Freeze the flight recorder and explain what just happened (current session by default; `--session all`) |
| `hermes minefield incident` | `/minefield incident` | Alias for `wtf` |
| `hermes minefield contribute` | `/minefield contribute` | Sanitized candidate and optional GitHub issue **draft** |
| `hermes minefield issues` | `/minefield issues` | Local incidents and linked GitHub status (`--refresh`) |
| `hermes minefield status` | `/minefield status` | Fingerprint, cached verdict, recorder health |
| `hermes minefield prune` | `/minefield prune` | Delete old local incidents, candidates and drafts (`--older-than 30d`, `--dry-run`) |
| `hermes minefield clear-cache` | `/minefield clear-cache` | Clear the Lite result cache |

Every command accepts `--json` for machine-readable output, which goes through the privacy sanitizer. `/minefield <cmd> -h` shows help in chat.

`/minefield …` is a Hermes slash command: type it in a Hermes session. From a shell, use `hermes minefield …`. There is no `/minefield-doctor`.

### What `wtf` detects

The rules are evaluated in priority order (details in [docs/CLASSIFICATION.md](docs/CLASSIFICATION.md)):

- 401/403 from the model endpoint → `CONFIGURATION_ERROR`
- 429 storm → `PERFORMANCE_CONTENTION`
- 5xx / connection-error storm → `MODEL_SERVER_BUG`
- a tool dispatched more than 2 minutes ago that never finished → `TOOL_BUG` (hang)
- consecutive identical calls with the **same arguments and the same result**, ≥ 5 in a row → `AGENT_TOOL_LOOP`
- one tool failing repeatedly → `TOOL_BUG`
- model-emitted tool calls that were never dispatched → `HERMES_UI_ORCHESTRATION`
- very slow responses (p95 latency or time-to-first-token) → `PERFORMANCE_CONTENTION`
- nothing happened → `UNKNOWN`; everything lined up → `EXPECTED_BEHAVIOUR` (`PASS`)

Loop detection mirrors Hermes's own tool-loop guardrails: polling tools such as `process_manage` are exempt, and repeated calls whose results change count as progress.

## Install

Requires Hermes `>=0.21,<0.22`, the range CI proves (see "Compatibility" below).

```bash
# 1) Minefield (not on PyPI) at the version CI tests against
pip install "model-serving-minefield @ git+https://github.com/Blackwellboy/model-serving-minefield@7b324f86d424c20bce177200851c968c1d70c536"

# 2) The plugin, pinned to a release commit
hermes plugins install Blackwellboy/hermes-minefield --ref <release-sha> --enable
```

**Development install:** link a checkout instead:

```bash
ln -sfn /path/to/hermes-minefield ~/.hermes/plugins/hermes-minefield
# then in ~/.hermes/config.yaml:
# plugins:
#   enabled: [hermes-minefield]
```

## Configuration

Settings live where Hermes keeps plugin settings (the Desktop settings page edits the same place):

```yaml
plugins:
  enabled: [hermes-minefield]
  entries:
    hermes-minefield:
      settings:
        lite_max_requests: 5            # 0-5
        recorder_retention_seconds: 600
        recorder_max_events: 5000
        recorder_max_bytes: 8388608
        fingerprint_cache_ttl_days: 30  # older Lite results are stale → UNKNOWN
        incident_retention_days: 90     # default for `prune`
        loop_streak_threshold: 5
        repo_allowlist: [Blackwellboy/model-serving-minefield, NousResearch/hermes-agent, ggerganov/llama.cpp]
        # Privacy-first switches, all off by default:
        remote_dedupe: false            # search GitHub for duplicates while drafting
        allow_submit_from_chat: false   # real submission from a chat slash command
        expose_agent_tool: false        # offer the read-only minefield_recent_incident tool to the model
        auto_lite: "false"              # "true": background Lite once per process, multi-slot servers only
```

Invalid values never break Hermes: each one falls back to its default, with one warning. Legacy locations (`…hermes-minefield.config`, the entry itself, or a top-level `minefield:` block) are still read.

`check` and `doctor` resolve the endpoint through **Hermes's own provider logic** (named providers, env config, credential pools) and pass its API key to Minefield. The key is never printed, cached or stored. An explicit `--base-url` only gets Hermes's key if it *is* Hermes's endpoint, and `--base-url` isn't accepted from chat. If Hermes's active provider isn't an OpenAI-compatible chat-completions API (for example Bedrock), the verdict is `UNKNOWN`: Minefield can't probe it.

## Privacy model

Everything stays under `$HERMES_HOME/minefield/` (directories `0700`, files `0600`, atomic writes).

| Stored | Never stored |
|---|---|
| event types, timestamps, tool **names** | tool arguments or results |
| SHA-256 fingerprints of arguments and results | prompts, messages, conversation history |
| lengths, counts, durations, HTTP status codes | API keys (exact-value scrubbed from probe output as well) |
| short enum-like error types and reasons | error **messages**, URLs, hostnames |
| hashed session, request and tool-call ids | raw ids |

The recorder writes one segment file per Hermes process (`recorder/events-<pid>-….jsonl`), so the CLI, the gateway and a fresh `wtf` process never overwrite each other. Recording does no disk I/O on the hook thread. A background thread flushes about every 2 s, so Hermes never waits on disk.

## Publishing is always a human step

- No automatic upload, and model output can never approve anything.
- A draft is saved with the SHA-256 of its exact title and body. `hermes minefield contribute --submit-draft <id> --i-approve-submit --submit` sends **exactly** those bytes. Tampered drafts are refused.
- Without `--submit` it's a dry run. From a chat surface, real submission is refused unless `allow_submit_from_chat: true`, because anyone in a room can type slash commands.
- The target repo comes from a deterministic classification → repo map, or an explicit `--repo`. Model-suggested repos are ignored. The recommended repo is only a recommendation, not approval.
- Remote duplicate search is opt-in (`--remote-dedupe`), and it prints the exact sanitized terms before sending them.
- A closed GitHub issue is never assumed to be fixed.

## Optional agent tool

With `expose_agent_tool: true`, the model can call `minefield_recent_incident` when you ask something like "why did you just do that?". It returns only a summary: classification, verdict, counts and a recommendation. It never saves, contributes, or touches the network.

## Troubleshooting

- `HERMES_PLUGINS_DEBUG=1 hermes minefield status` shows plugin loading and any hook errors.
- `wtf` says `UNKNOWN — no recorder events`: either the plugin isn't enabled in the Hermes process that did the work, or nothing happened in that window. Try `hermes minefield wtf 30m --session all`.
- `check` says `UNKNOWN — endpoint could not be tested`: the server is down or unreachable. Nothing was cached.

## Compatibility

CI (`hermes-compat`) loads the plugin into, and replays the hook contract against:

- Hermes `v2026.8.31` (0.21.0, the minimum),
- the pinned known-good commit,
- the latest release `v2026.9.24` (0.21.5),
- Hermes `main` (non-blocking).

It also runs the Gate A scenario suite, with real processes, on each of them. `tests/test_hermes_contract.py` reads Hermes's own source and fails if any hook argument the plugin relies on disappears.

## Development

```bash
./scripts/dev_setup.sh          # venv + pinned Minefield + pinned Hermes (editable)
source .venv/bin/activate
ruff check hermes_minefield tests && ruff format --check hermes_minefield tests
pytest -q                       # unit + contract + real-loader tests
pytest -q -m gate_a tests/e2e   # Gate A: real Hermes + CLI processes (~5 min)
./scripts/validate_plugin.sh    # `hermes plugins validate` on a clean copy
```

Override the pinned refs with `MINEFIELD_REF=<sha>` / `HERMES_REF=<sha>`. Coding agents: read [AGENTS.md](AGENTS.md).

Don't open NousResearch PRs, or submit to the Hermes plugin catalog, from this repo without separate owner approval.
