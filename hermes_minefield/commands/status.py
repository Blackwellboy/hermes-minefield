""" /minefield status """

from __future__ import annotations

import time
from typing import Any, Optional

from ..cache import get_entry, load_cache
from ..config import load_plugin_config
from ..fingerprint import fingerprint_for_hermes_target
from ..recorder.store import get_recorder
from ..render import extract_summary_counts, render_status
from ..target import resolve_target


def run_status(*, base_url: Optional[str] = None, model: Optional[str] = None) -> dict[str, Any]:
    cfg = load_plugin_config()
    fp_short = None
    cache_age = None
    last_summary = None
    try:
        target = resolve_target(base_url=base_url, model=model)
        # Must match check()'s Lite-cache key (includes reasoning_mode=from_config).
        fp = fingerprint_for_hermes_target(model=target.model, base_url=target.base_url)
        fp_short = fp.short()
        entry = get_entry(fp.key)
        if entry:
            age_s = time.time() - entry.checked_at
            cache_age = f"{age_s/60:.1f}m ago ({entry.mode})"
            _, clean, problem, inconclusive = extract_summary_counts(entry.summary)
            # Prefer repaired counts from findings when legacy cache stored zeros.
            if (entry.clean, entry.problem, entry.inconclusive) == (0, 0, 0) and (
                clean,
                problem,
                inconclusive,
            ) != (0, 0, 0):
                c, p, i = clean, problem, inconclusive
            else:
                c, p, i = entry.clean, entry.problem, entry.inconclusive
            last_summary = (
                f"  clean={c} problem={p} "
                f"inconclusive={i} requests={entry.requests_executed}"
            )
    except Exception as e:
        cache_age = f"target unresolved: {type(e).__name__}"

    rec = get_recorder()
    stats = rec.stats()
    # Cheap recent persisted peek (bounded) so status reflects cross-process activity.
    recent_persisted = 0
    try:
        from ..recorder.store import load_recent_persisted_events

        recent_persisted = len(
            load_recent_persisted_events(
                since_seconds=min(stats.retention_seconds, 600),
                retention_seconds=stats.retention_seconds,
                max_events=min(200, stats.max_events),
                max_bytes=min(256_000, stats.max_bytes),
            )
        )
    except Exception:
        recent_persisted = 0
    text = render_status(
        fingerprint_short=fp_short,
        fingerprint_kind="lite-cache (config-resolved)",
        cache_age=cache_age,
        recorder_stats={
            "events_in_memory": stats.events_in_memory,
            "retention_seconds": stats.retention_seconds,
            "max_bytes": stats.max_bytes,
            "persisted_recent": recent_persisted,
            "persisted_bytes": stats.persisted_approx_bytes,
        },
        last_summary=last_summary,
        auto_lite=cfg.auto_lite,
    )
    n_cache = len((load_cache().get("entries") or {}))
    return {"ok": True, "text": text, "cache_entries": n_cache, "recorder": stats.__dict__}
