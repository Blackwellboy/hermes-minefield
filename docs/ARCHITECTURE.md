# Architecture

```
Hermes hooks ──► recorder/hooks.py   pure mapping: Hermes kwargs → RecorderEvent
                     │                (no I/O, never raises, returns None)
                     ▼
              recorder/store.py      ring buffer (memory) + daemon flusher thread
                     │                → recorder/events-<pid>-<start>-<rand>-<n>.jsonl (one file per process)
                     │
 /minefield wtf ─────┤ freeze: memory + bounded tail of recent segments (all processes), dedupe
                     ▼
              incident/signals.py    pure: counts, streaks, hangs, API status buckets, latency
              incident/rules.py      pure: one function per rule, priority-ordered (docs/CLASSIFICATION.md)
                     ▼
              IncidentArtifact ─► render (text | --json) ─► save (anomalies only) ─► contribute (human-gated)

 /minefield check|doctor ─► target.py (Hermes runtime provider → base_url + api_key)
                          ─► minefield.api (hard request budget)
                          ─► commands/_probe.py (reachable? probes ran? → verdict; secret scrub)
                          ─► cache (fingerprint, TTL) — only valid runs are cached
```

## Principles

1. **Hooks are pure mappers.** No file I/O, network or locks held for I/O on the hook thread. If `pre_tool_call` fails or times out, Hermes blocks the user's tool.
2. **Metadata only.** Names, hashes, lengths, counts, durations and enum-like codes. Never arguments, results, messages, prompts, error text, URLs or keys.
3. **Honest verdicts.** `PASS` / `FAIL` / `UNKNOWN` everywhere. Missing evidence is `UNKNOWN`.
4. **Human-gated publication.** Drafts are hashed. Submission is explicit, and never from model output.
5. **Hermes contract is tested, not assumed.** `tests/fixtures/hermes_hook_payloads.json` is checked against Hermes's own fire sites on every supported version.

## Event schema (`recorder/events.py`)

| Type | Emitted by | Key fields |
|---|---|---|
| `tool.prepared` | `post_api_request` (one per model-emitted tool call) | `tool_name`, `extra.tool_call_id_hash` |
| `tool.requested` | `pre_tool_call` (Hermes dispatched it) | `tool_name`, `tool_arg_fingerprint`, `extra.tool_call_id_hash` |
| `tool.executed` | `post_tool_call` | `success`, `wall_ms`, `result_bytes`, `result_fingerprint`, `extra.guardrail_refusal` |
| `tool.completed` / `tool.failed` | `post_tool_call` | `error_class` (enum-like, e.g. `tool_error`) |
| `turn.start` / `turn.end` | `pre_llm_call` / `post_llm_call` | `content_len` |
| `turn.finished` | `on_session_end` (every turn) | `extra.completed`, `extra.interrupted` |
| `api.request` / `api.response` / `api.error` | API hooks | `wall_ms`, `ttft_ms`, `http_status`, `error_class`, `extra.retryable` |
| `session.start` / `session.end` | `on_session_start` / `on_session_finalize` | |
| `orch.cancel` | `agent_loop_stopped` (Hermes ≥ 0.21.x where available) | `extra.reason` (enum-like) |

All ids (`session_id`, `api_request_id`, `tool_call_id`) are stored as truncated SHA-256 hashes. Events persisted by 0.1.x are still read: `tool.prepared` rows with `extra.phase == "pre_tool_call"` are treated as the duplicates they were.

## Storage (`$HERMES_HOME/minefield/`, dirs 0700, files 0600)

| Path | Contents | Bounds |
|---|---|---|
| `recorder/events-*.jsonl` | recorder segments, one writer each | `recorder_retention_seconds`, `recorder_max_bytes` (whole-segment deletes) |
| `cache/fingerprint_cache.json` | last valid Lite result per endpoint fingerprint | 200 entries, `fingerprint_cache_ttl_days` |
| `incidents/INC-*.json`, `index.jsonl` | saved anomalies | `prune`, index compacted at 2000 → 1000 rows |
| `candidates/`, `drafts/` | contribution packets, hashed issue drafts | `prune` |
