"""Bounded in-memory ring buffer + background batched persistence + persisted replay.

Persistence is multi-process safe: every recorder appends only to its *own*
segment file (``recorder/events-<pid>-<start>-<rand>.jsonl``) and nothing ever
rewrites another process's file. CLI + gateway + a fresh ``hermes minefield wtf``
can run concurrently without losing each other's evidence. Cleanup only deletes
whole segments (expired, or oldest-first when over the byte budget).
"""

from __future__ import annotations

import json
import os
import secrets
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

SEGMENT_GLOB = "events-*.jsonl"
LEGACY_NAME = "events.jsonl"  # single shared file used by <=0.1.x; read-only now
CLEANUP_INTERVAL = 30.0


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
    persisted_segments: int = 0


@dataclass
class FreezeResult:
    events: list[RecorderEvent]
    memory_count: int
    persisted_count: int
    deduped_count: int


def events_jsonl_path() -> Path:
    """Legacy single-file location (read for compatibility, never written)."""
    return recorder_dir() / LEGACY_NAME


def persisted_files(directory: Path) -> list[Path]:
    """Segment files + legacy file in ``directory``, newest (mtime) first."""
    files: list[tuple[float, Path]] = []
    try:
        candidates = list(directory.glob(SEGMENT_GLOB))
        legacy = directory / LEGACY_NAME
        if legacy.is_file():
            candidates.append(legacy)
    except OSError:
        return []
    for p in candidates:
        try:
            files.append((p.stat().st_mtime, p))
        except OSError:
            continue  # deleted concurrently
    files.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in files]


def _read_tail(path: Path, budget: int) -> str:
    try:
        size = path.stat().st_size
        if size <= 0 or budget <= 0:
            return ""
        with path.open("rb") as fh:
            if size > budget:
                fh.seek(size - budget)
                fh.readline()  # drop possibly partial first line
            raw = fh.read(budget)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


def load_recent_persisted_events(
    *,
    since_seconds: float | None = None,
    session_id_hash: str | None = None,
    retention_seconds: int = DEFAULT_RECORDER_RETENTION_SECONDS,
    max_events: int = DEFAULT_RECORDER_MAX_EVENTS,
    max_bytes: int = DEFAULT_RECORDER_MAX_BYTES,
    path: Path | None = None,
    directory: Path | None = None,
    now: float | None = None,
) -> list[RecorderEvent]:
    """Bounded reader for recent persisted recorder events.

    - ``path``: read that single file (tests / legacy). Otherwise read every
      segment in ``directory`` (default: the Minefield recorder dir).
    - Reads at most ``max_bytes`` in total, from the *end* of the newest files.
    - Skips malformed JSON and schema-invalid rows.
    - Filters by retention / since_seconds / session.
    - Keeps newest valid events up to ``max_events``, sorted by time.
    """
    now = time.time() if now is None else now
    retention_cutoff = now - max(0, int(retention_seconds))
    since_cutoff = retention_cutoff
    if since_seconds is not None:
        since_cutoff = max(retention_cutoff, now - max(0.0, float(since_seconds)))

    if path is not None:
        files = [path]
    else:
        files = persisted_files(directory or recorder_dir())

    budget = max(1024, int(max_bytes))
    parsed: list[RecorderEvent] = []
    for f in files:
        if budget <= 0:
            break
        try:
            st = f.stat()
        except OSError:
            continue
        if path is None and st.st_mtime < since_cutoff:
            continue  # last write predates the window: every row in it is older
        text = _read_tail(f, min(budget, st.st_size))
        budget -= min(budget, st.st_size)
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = RecorderEvent.from_dict(row, now=now)
            if ev is None or ev.ts < since_cutoff:
                continue
            if session_id_hash and ev.session_id_hash and ev.session_id_hash != session_id_hash:
                continue
            parsed.append(ev)

    parsed.sort(key=lambda e: (e.ts, e.event_id))
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


def _append_private(path: Path, data: str) -> None:
    """Append ``data`` to ``path``, creating it 0600. One open per batch, so a
    segment deleted by another process's cleanup is simply recreated."""
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(data)


class FlightRecorder:
    """Process-local flight recorder with bounded persisted replay for WTF.

    Design goals:
    - Metadata-first events only
    - Hard ceilings on count, age, and approximate bytes
    - ``record()`` does no file I/O: it runs inside Hermes hooks, and a slow or
      failing ``pre_tool_call`` callback makes Hermes block the user's tool.
      A daemon flusher thread writes batches (every ~2s or 32 events).
    - Each process appends only to its own segment file (multi-process safe)
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
        directory: Path | None = None,
    ) -> None:
        self.retention_seconds = retention_seconds
        self.max_events = max_events
        self.max_bytes = max_bytes
        self.persist = persist
        self._path = path  # single-file mode (tests); None = segment mode
        self._directory = directory
        self._segment: Path | None = None
        self._segment_seq = 0
        self._started = int(time.time())
        self._last_cleanup = 0.0
        self._buf: deque[tuple[RecorderEvent, int]] = deque()  # (event, serialized size)
        self._approx_bytes = 0
        self._lock = threading.RLock()  # guards _buf / _pending (memory only, never held for I/O)
        self._io_lock = threading.Lock()  # serializes this recorder's file writes
        self._pending: list[str] = []  # serialized rows awaiting flush
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_freeze: FreezeResult | None = None
        self.last_session_hash: str | None = None

    # -- locations ----------------------------------------------------------

    def _dir(self) -> Path:
        if self._path is not None:
            return self._path.parent
        return self._directory or recorder_dir()

    def _new_segment_path(self) -> Path:
        self._segment_seq += 1
        name = f"events-{os.getpid()}-{self._started}-{secrets.token_hex(3)}-{self._segment_seq}.jsonl"
        return self._dir() / name

    def _write_target(self) -> Path:
        if self._path is not None:
            return self._path
        if self._segment is None:
            self._segment = self._new_segment_path()
        return self._segment

    # -- hot path (called from Hermes hooks) -------------------------------

    def record(self, event: RecorderEvent) -> None:
        """Append to memory. No file I/O, never blocks on disk."""
        try:
            row = json.dumps(event.to_dict(), default=str)
        except Exception:
            row = None
        size = len(row) if row is not None else 128
        if event.session_id_hash:
            self.last_session_hash = event.session_id_hash
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
            now = time.time()
            if self._path is None and now - self._last_cleanup > CLEANUP_INTERVAL:
                self._last_cleanup = now
                self.cleanup_segments(now=now)

    def _append_rows(self, rows: list[str]) -> None:
        try:
            target = self._write_target()
            target.parent.mkdir(parents=True, exist_ok=True)
            _append_private(target, "\n".join(rows) + "\n")
            size = target.stat().st_size
            if self._path is not None:
                if size > self.max_bytes:
                    self._rotate_single_file(target)
            elif size > max(64 * 1024, self.max_bytes // 4):
                self._segment = None  # next batch starts a new segment
        except Exception:
            pass

    def cleanup_segments(self, *, now: float | None = None) -> int:
        """Delete expired segments, then oldest-first while over ``max_bytes``.

        Whole-file deletes only; never truncates or rewrites a file. Returns the
        number of files removed. Safe to run from several processes at once.
        """
        now = time.time() if now is None else now
        removed = 0
        files = persisted_files(self._dir())  # newest first
        keep: list[tuple[Path, int]] = []
        expiry = now - self.retention_seconds - 60
        for f in files:
            try:
                st = f.stat()
            except OSError:
                continue
            if st.st_mtime < expiry and f != self._segment:
                removed += self._unlink(f)
            else:
                keep.append((f, st.st_size))
        total = sum(size for _, size in keep)
        for f, size in reversed(keep):  # oldest first
            if total <= self.max_bytes:
                break
            if f == self._segment:
                continue
            removed += self._unlink(f)
            total -= size
        return removed

    @staticmethod
    def _unlink(path: Path) -> int:
        try:
            path.unlink()
            return 1
        except (FileNotFoundError, PermissionError, OSError):
            return 0  # already gone, or held open on Windows

    def _rotate_single_file(self, path: Path) -> None:
        """Single-file (test) mode only: keep a bounded tail."""
        try:
            text = _read_tail(path, self.max_bytes)
            lines = [ln for ln in text.splitlines() if ln.strip()]
            keep = lines[-max(100, self.max_events // 2) :]
            path.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
        except Exception:
            try:
                path.unlink(missing_ok=True)
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

    # -- reading ------------------------------------------------------------

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
        """Freeze memory (+ recent persisted, all processes) for WTF analysis."""
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
                path=self._path,
                directory=self._dir(),
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

    def current_session_hash(self) -> str | None:
        """The most recently active session: in-memory first (inside Hermes), else the
        newest persisted event that carries one (a fresh CLI process)."""
        if self.last_session_hash:
            return self.last_session_hash
        if not self.persist:
            return None
        recent = load_recent_persisted_events(
            retention_seconds=self.retention_seconds,
            max_events=self.max_events,
            max_bytes=self.max_bytes,
            path=self._path,
            directory=self._dir(),
        )
        for ev in reversed(recent):
            if ev.session_id_hash:
                return ev.session_id_hash
        return None

    def stats(self) -> RecorderStats:
        with self._lock:
            self._trim_locked()
            oldest = self._buf[0][0].ts if self._buf else None
            newest = self._buf[-1][0].ts if self._buf else None
            in_memory = len(self._buf)
            approx = self._approx_bytes
        files = [self._path] if self._path is not None else persisted_files(self._dir())
        pbytes = 0
        n = 0
        for f in files:
            try:
                pbytes += int(f.stat().st_size)
                n += 1
            except OSError:
                continue
        return RecorderStats(
            events_in_memory=in_memory,
            oldest_ts=oldest,
            newest_ts=newest,
            retention_seconds=self.retention_seconds,
            max_events=self.max_events,
            max_bytes=self.max_bytes,
            approx_bytes=approx,
            persisted_path_exists=n > 0,
            persisted_approx_bytes=pbytes,
            persisted_segments=n,
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
