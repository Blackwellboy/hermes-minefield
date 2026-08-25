"""Bounded in-memory ring buffer + optional batched disk flush."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Iterable, Iterator, List, Optional

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


class FlightRecorder:
    """Process-local flight recorder.

    Design goals:
    - Metadata-first events only
    - Hard ceilings on count, age, and approximate bytes
    - No sync disk write per UI event (batch flush)
    """

    def __init__(
        self,
        *,
        retention_seconds: int = DEFAULT_RECORDER_RETENTION_SECONDS,
        max_events: int = DEFAULT_RECORDER_MAX_EVENTS,
        max_bytes: int = DEFAULT_RECORDER_MAX_BYTES,
        persist: bool = True,
    ) -> None:
        self.retention_seconds = retention_seconds
        self.max_events = max_events
        self.max_bytes = max_bytes
        self.persist = persist
        self._buf: Deque[RecorderEvent] = deque()
        self._approx_bytes = 0
        self._lock = threading.RLock()
        self._pending_flush: List[dict] = []
        self._last_flush = 0.0

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

    def _trim_locked(self) -> None:
        cutoff = time.time() - self.retention_seconds
        while self._buf and (self._buf[0].ts < cutoff or len(self._buf) > self.max_events):
            old = self._buf.popleft()
            try:
                self._approx_bytes -= len(json.dumps(old.to_dict(), default=str))
            except Exception:
                self._approx_bytes = max(0, self._approx_bytes - 128)
        # Byte ceiling: drop oldest until under budget
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
        path = recorder_dir() / "events.jsonl"
        try:
            with path.open("a", encoding="utf-8") as fh:
                for row in self._pending_flush:
                    fh.write(json.dumps(row, default=str) + "\n")
            # Bound on-disk file size
            if path.stat().st_size > self.max_bytes:
                self._rotate_disk(path)
        except Exception:
            pass
        self._pending_flush.clear()
        self._last_flush = time.time()

    def _rotate_disk(self, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            keep = lines[- max(100, self.max_events // 2) :]
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
    ) -> list[RecorderEvent]:
        with self._lock:
            self._trim_locked()
            if self.persist:
                self._flush_locked()
            cutoff = None
            if since_seconds is not None:
                cutoff = time.time() - since_seconds
            out: list[RecorderEvent] = []
            for ev in self._buf:
                if cutoff is not None and ev.ts < cutoff:
                    continue
                if session_id_hash and ev.session_id_hash and ev.session_id_hash != session_id_hash:
                    continue
                out.append(ev)
            return out

    def stats(self) -> RecorderStats:
        with self._lock:
            self._trim_locked()
            oldest = self._buf[0].ts if self._buf else None
            newest = self._buf[-1].ts if self._buf else None
            return RecorderStats(
                events_in_memory=len(self._buf),
                oldest_ts=oldest,
                newest_ts=newest,
                retention_seconds=self.retention_seconds,
                max_events=self.max_events,
                max_bytes=self.max_bytes,
                approx_bytes=self._approx_bytes,
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


def reset_recorder_for_tests() -> FlightRecorder:
    global _GLOBAL
    with _GLOBAL_LOCK:
        _GLOBAL = FlightRecorder(persist=False)
        return _GLOBAL
