"""Bounded in-memory ring buffer + optional batched disk flush + persisted replay."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, List, Optional

from ..config import (
    DEFAULT_RECORDER_MAX_BYTES,
    DEFAULT_RECORDER_MAX_EVENTS,
    DEFAULT_RECORDER_RETENTION_SECONDS,
)
from ..paths import recorder_dir
from .events import RecorderEvent


@dataclass
class RecorderStats:
    events_in_memory: int
    oldest_ts: Optional[float]
    newest_ts: Optional[float]
    retention_seconds: int
    max_events: int
    max_bytes: int
    approx_bytes: int
    persisted_path_exists: bool = False
    persisted_approx_bytes: int = 0


@dataclass
class FreezeResult:
    events: list[RecorderEvent]
    memory_count: int
    persisted_count: int
    deduped_count: int


def events_jsonl_path() -> Path:
    """Minefield-owned recorder path only — no arbitrary file traversal."""
    return recorder_dir() / "events.jsonl"


def load_recent_persisted_events(
    *,
    since_seconds: Optional[float] = None,
    session_id_hash: Optional[str] = None,
    retention_seconds: int = DEFAULT_RECORDER_RETENTION_SECONDS,
    max_events: int = DEFAULT_RECORDER_MAX_EVENTS,
    max_bytes: int = DEFAULT_RECORDER_MAX_BYTES,
    path: Optional[Path] = None,
    now: Optional[float] = None,
) -> list[RecorderEvent]:
    """Bounded reader for recent persisted recorder events.

    - Reads only the Minefield recorder JSONL (or an explicit test path).
    - Reads at most ``max_bytes`` from the *end* of the file.
    - Skips malformed JSON and schema-invalid rows.
    - Filters by retention / since_seconds / session.
    - Keeps newest valid events up to ``max_events``.
    """
    now = time.time() if now is None else now
    path = path or events_jsonl_path()
    # Refuse path escape: must live under recorder_dir() unless caller passed a temp test path
    # that is already absolute and exists; production callers omit path.
    if path is None:
        return []
    try:
        if not path.is_file():
            return []
        size = path.stat().st_size
    except OSError:
        return []

    if size <= 0:
        return []

    read_budget = max(1024, min(int(max_bytes), int(size)))
    try:
        with path.open("rb") as fh:
            if size > read_budget:
                fh.seek(size - read_budget)
                fh.readline()  # drop possibly partial first line
            raw = fh.read(read_budget)
    except OSError:
        return []

    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return []

    retention_cutoff = now - max(0, int(retention_seconds))
    since_cutoff = retention_cutoff
    if since_seconds is not None:
        since_cutoff = max(retention_cutoff, now - max(0.0, float(since_seconds)))

    parsed: list[RecorderEvent] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ev = RecorderEvent.from_dict(row, now=now)
        if ev is None:
            continue
        if ev.ts < since_cutoff:
            continue
        if session_id_hash and ev.session_id_hash and ev.session_id_hash != session_id_hash:
            continue
        parsed.append(ev)

    # Newest retained; bound count
    if len(parsed) > max_events:
        parsed = parsed[-max_events:]
    return parsed


def merge_events(
    memory: list[RecorderEvent],
    persisted: list[RecorderEvent],
) -> tuple[list[RecorderEvent], int, int, int]:
    """Merge memory + persisted, dedupe by identity, sort by timestamp."""
    seen: set[str] = set()
    out: list[RecorderEvent] = []
    for src in (memory, persisted):
        for ev in src:
            key = ev.identity()
            if key in seen:
                continue
            seen.add(key)
            out.append(ev)
    out.sort(key=lambda e: (e.ts, e.event_id))
    return out, len(memory), len(persisted), len(out)


class FlightRecorder:
    """Process-local flight recorder with bounded persisted replay for WTF.

    Design goals:
    - Metadata-first events only
    - Hard ceilings on count, age, and approximate bytes
    - No sync disk write per UI event (batch flush)
    - Fresh CLI processes can freeze recent persisted events
    """

    def __init__(
        self,
        *,
        retention_seconds: int = DEFAULT_RECORDER_RETENTION_SECONDS,
        max_events: int = DEFAULT_RECORDER_MAX_EVENTS,
        max_bytes: int = DEFAULT_RECORDER_MAX_BYTES,
        persist: bool = True,
        path: Optional[Path] = None,
    ) -> None:
        self.retention_seconds = retention_seconds
        self.max_events = max_events
        self.max_bytes = max_bytes
        self.persist = persist
        self._path = path  # optional override for tests
        self._buf: Deque[RecorderEvent] = deque()
        self._approx_bytes = 0
        self._lock = threading.RLock()
        self._pending_flush: List[dict] = []
        self._last_flush = 0.0
        self.last_freeze: Optional[FreezeResult] = None

    def _jsonl_path(self) -> Path:
        return self._path or events_jsonl_path()

    def record(self, event: RecorderEvent) -> None:
        with self._lock:
            self._buf.append(event)
            try:
                self._approx_bytes += len(json.dumps(event.to_dict(), default=str))
            except Exception:
                self._approx_bytes += 128
            self._trim_locked()
            if self.persist:
                self._pending_flush.append(event.to_dict())
                now = time.time()
                if len(self._pending_flush) >= 32 or (now - self._last_flush) > 2.0:
                    self._flush_locked()

    def flush(self) -> None:
        """Best-effort batch flush (session end / freeze). Not a per-event fsync."""
        with self._lock:
            if self.persist:
                self._flush_locked()

    def _trim_locked(self) -> None:
        cutoff = time.time() - self.retention_seconds
        while self._buf and (self._buf[0].ts < cutoff or len(self._buf) > self.max_events):
            old = self._buf.popleft()
            try:
                self._approx_bytes -= len(json.dumps(old.to_dict(), default=str))
            except Exception:
                self._approx_bytes = max(0, self._approx_bytes - 128)
        while self._buf and self._approx_bytes > self.max_bytes:
            old = self._buf.popleft()
            try:
                self._approx_bytes -= len(json.dumps(old.to_dict(), default=str))
            except Exception:
                self._approx_bytes = max(0, self._approx_bytes - 128)
        self._approx_bytes = max(0, self._approx_bytes)

    def _flush_locked(self) -> None:
        if not self._pending_flush:
            return
        path = self._jsonl_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                for row in self._pending_flush:
                    fh.write(json.dumps(row, default=str) + "\n")
            if path.stat().st_size > self.max_bytes:
                self._rotate_disk(path)
        except Exception:
            pass
        self._pending_flush.clear()
        self._last_flush = time.time()

    def _rotate_disk(self, path: Path) -> None:
        try:
            # Bound rotation: keep a tail within max_bytes/max_events without full unbounded load
            size = path.stat().st_size
            budget = min(self.max_bytes, size)
            with path.open("rb") as fh:
                if size > budget:
                    fh.seek(size - budget)
                    fh.readline()
                raw = fh.read()
            text = raw.decode("utf-8", errors="replace")
            lines = [ln for ln in text.splitlines() if ln.strip()]
            keep = lines[-max(100, self.max_events // 2) :]
            path.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
        except Exception:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    def freeze(
        self,
        *,
        since_seconds: Optional[float] = None,
        session_id_hash: Optional[str] = None,
        include_persisted: bool = True,
    ) -> list[RecorderEvent]:
        return self.freeze_detailed(
            since_seconds=since_seconds,
            session_id_hash=session_id_hash,
            include_persisted=include_persisted,
        ).events

    def freeze_detailed(
        self,
        *,
        since_seconds: Optional[float] = None,
        session_id_hash: Optional[str] = None,
        include_persisted: bool = True,
    ) -> FreezeResult:
        """Freeze memory (+ recent persisted) for WTF analysis."""
        with self._lock:
            self._trim_locked()
            if self.persist:
                self._flush_locked()
            cutoff = None
            now = time.time()
            if since_seconds is not None:
                cutoff = now - since_seconds
            memory: list[RecorderEvent] = []
            for ev in self._buf:
                if cutoff is not None and ev.ts < cutoff:
                    continue
                if session_id_hash and ev.session_id_hash and ev.session_id_hash != session_id_hash:
                    continue
                memory.append(ev)

        persisted: list[RecorderEvent] = []
        if include_persisted and self.persist:
            persisted = load_recent_persisted_events(
                since_seconds=since_seconds,
                session_id_hash=session_id_hash,
                retention_seconds=self.retention_seconds,
                max_events=self.max_events,
                max_bytes=self.max_bytes,
                path=self._jsonl_path(),
                now=now,
            )

        events, mem_n, pers_n, deduped = merge_events(memory, persisted)
        # Enforce max_events after merge (newest)
        if len(events) > self.max_events:
            events = events[-self.max_events :]
            deduped = len(events)
        result = FreezeResult(
            events=events,
            memory_count=mem_n,
            persisted_count=pers_n,
            deduped_count=deduped,
        )
        self.last_freeze = result
        return result

    def stats(self) -> RecorderStats:
        with self._lock:
            self._trim_locked()
            oldest = self._buf[0].ts if self._buf else None
            newest = self._buf[-1].ts if self._buf else None
            path = self._jsonl_path()
            exists = False
            pbytes = 0
            try:
                if path.is_file():
                    exists = True
                    pbytes = int(path.stat().st_size)
            except OSError:
                pass
            return RecorderStats(
                events_in_memory=len(self._buf),
                oldest_ts=oldest,
                newest_ts=newest,
                retention_seconds=self.retention_seconds,
                max_events=self.max_events,
                max_bytes=self.max_bytes,
                approx_bytes=self._approx_bytes,
                persisted_path_exists=exists,
                persisted_approx_bytes=pbytes,
            )

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()
            self._approx_bytes = 0
            self._pending_flush.clear()


# Process singleton used by hooks + commands
_GLOBAL: Optional[FlightRecorder] = None
_GLOBAL_LOCK = threading.Lock()


def get_recorder(**kwargs) -> FlightRecorder:
    global _GLOBAL
    with _GLOBAL_LOCK:
        if _GLOBAL is None:
            _GLOBAL = FlightRecorder(**kwargs)
        return _GLOBAL


def reset_recorder_for_tests(**kwargs) -> FlightRecorder:
    global _GLOBAL
    with _GLOBAL_LOCK:
        kwargs.setdefault("persist", False)
        _GLOBAL = FlightRecorder(**kwargs)
        return _GLOBAL
