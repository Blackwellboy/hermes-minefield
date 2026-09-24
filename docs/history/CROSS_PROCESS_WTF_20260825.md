# Cross-process WTF replay — 2026-08-25

## Root cause

`FlightRecorder.freeze()` previously iterated only the process-local `_buf`.
Events were batched to `~/.hermes/minefield/recorder/events.jsonl`, but a fresh
`hermes minefield wtf` process never read them → quiet window after real Hermes activity.

## Fix

`freeze_detailed()` merges:

1. current in-memory buffer (after pending flush)
2. bounded recent persisted JSONL (`load_recent_persisted_events`)

Then dedupes by `event_id` (fallback: metadata identity hash).

Bounds: retention, max_events, max_bytes (tail-read). Malformed / invalid schema / far-future timestamps skipped.

## Flush semantics

- Batch flush at 32 events or ~2s idle between records
- `freeze()` flushes pending first
- `on_session_end` / `on_session_finalize` record + `flush()`

**Abrupt process death** can still lose the final pending batch (&lt;32 events, &lt;2s).
Documented limitation — no per-event fsync.

## Live dogfood

Harmless `hermes chat -Q -q … -t terminal` produced terminal prepare/execute.
Fresh shell `hermes minefield wtf 10m` saw 13 persisted events, classification
`EXPECTED_BEHAVIOUR` (aligned prepare/execute — not a bug).
