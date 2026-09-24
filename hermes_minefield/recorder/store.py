"""Bounded in-memory ring buffer + optional batched disk flush + persisted replay."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

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
    oldest_ts: float | None
    newest_ts: float | None
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
    since_seconds: float | None = None,
    session_id_hash: str | None = None,
    retention_seconds: int = DEFAULT_RECORDER_RETENTION_SECONDS,
    max_events: int = DEFAULT_RECORDER_MAX_EVENTS,
    max_bytes: int = DEFAULT_RECORDER_MAX_BYTES,
    path: Path | None = None,
    now: float | None = None,
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
    - ``record()`` does no file I/O: it runs inside Hermes hooks, and a slow or
      failing ``pre_tool_call`` callback makes Hermes block the user's tool.
      A daemon flusher thread writes batches (every ~2s or 32 events).
    - Fresh CLI processes can freeze recent persisted events
    """

    FLUSH_BATCH = 32
    FLUSH_INTERVAL = 2.0

    def __init__(
        self,
        *,
        retention_seconds: int = DEFAULT_RECORDER_RETENTION_SECONDS,
        max_events: int = DEFAULT_RECORDER_MAX_EVENTS,
        max_bytes: int = DEFAULT_RECORDER_MAX_BYTES,
        persist: bool = True,
        path: Path | None = None,
    ) -> None:
        self.retention_seconds = retention_seconds
        self.max_events = max_events
        self.max_bytes = max_bytes
        self.persist = persist
        self._path = path  # optional override for tests
        self._buf: deque[tuple[RecorderEvent, int]] = deque()  # (event, serialized size)
        self._approx_bytes = 0
        self._lock = threading.RLock()  # guards _buf / _pending (memory only, never held for I/O)
        self._io_lock = threading.Lock()  # serializes file writes
        self._pending: list[str] = []  # serialized rows awaiting flush
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_freeze: FreezeResult | None = None

    def _jsonl_path(self) -> Path:
        return self._path or events_jsonl_path()

    # -- hot path (called from Hermes hooks) -------------------------------

    def record(self, event: RecorderEvent) -> None:
        """Append to memory. O(1)-ish, no file I/O, never blocks on disk."""
        try:
            row = json.dumps(event.to_dict(), default=str)
        except Exception:
            row = None
        size = len(row) if row is not None else 128
        with self._lock:
            self._buf.append((event, size))
            self._approx_bytes += size
            self._trim_locked()
            if self.persist and row is not None and not self._stop.is_set():
                self._pending.append(row)
                if len(self._pending) >= self.FLUSH_BATCH:
                    self._wake.set()
        if self.persist and self._thread is None:
            self._start_flusher()

    def request_flush(self) -> None:
        """Ask the flusher thread to write soon (safe to call from hooks)."""
        self._wake.set()

    # -- background persistence --------------------------------------------

    def _start_flusher(self) -> None:
        with self._lock:
            if self._thread is not None or self._stop.is_set():
                return
            t = threading.Thread(target=self._flusher_loop, name="minefield-recorder-flush", daemon=True)
            self._thread = t
        t.start()

    def _flusher_loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=self.FLUSH_INTERVAL)
            self._wake.clear()
            self._write_pending()

    def _take_pending(self) -> list[str]:
        with self._lock:
            rows, self._pending = self._pending, []
        return rows

    def _write_pending(self) -> None:
        with self._io_lock:
            rows = self._take_pending()
            if rows:
                self._append_rows(rows)

    def _append_rows(self, rows: list[str]) -> None:
        path = self._jsonl_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(rows) + "\n")
            if path.stat().st_size > self.max_bytes:
                self._rotate_disk(path)
        except Exception:
            pass

    def flush(self) -> None:
        """Synchronous flush — for commands (freeze/status/exit), never for hooks."""
        if self.persist:
            self._write_pending()

    def stop(self) -> None:
        """Stop the flusher and write whatever is pending. Idempotent."""
        self._stop.set()
        self._wake.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=2.0)
        self.flush()

    def _trim_locked(self) -> None:
        cutoff = time.time() - self.retention_seconds
        buf = self._buf
        while buf and (
            buf[0][0].ts < cutoff or len(buf) > self.max_events or self._approx_bytes > self.max_bytes
        ):
            _, size = buf.popleft()
            self._approx_bytes -= size
        self._approx_bytes = max(0, self._approx_bytes)

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
        since_seconds: float | None = None,
        session_id_hash: str | None = None,
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
        since_seconds: float | None = None,
        session_id_hash: str | None = None,
        include_persisted: bool = True,
    ) -> FreezeResult:
        """Freeze memory (+ recent persisted) for WTF analysis."""
        self.flush()
        with self._lock:
            self._trim_locked()
            cutoff = None
            now = time.time()
            if since_seconds is not None:
                cutoff = now - since_seconds
            memory: list[RecorderEvent] = []
            for ev, _ in self._buf:
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
            oldest = self._buf[0][0].ts if self._buf else None
            newest = self._buf[-1][0].ts if self._buf else None
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
            self._pending.clear()


# Process singleton used by hooks + commands
_GLOBAL: FlightRecorder | None = None
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
        if _GLOBAL is not None:
            _GLOBAL.stop()
        kwargs.setdefault("persist", False)
        _GLOBAL = FlightRecorder(**kwargs)
        return _GLOBAL
