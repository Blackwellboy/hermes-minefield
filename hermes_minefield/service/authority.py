"""One-shot grants minted only after a host-owned verification callback.

The callback must validate a real host event. No production adapter may install
an always-true callback. Same-UID arbitrary code execution is outside this boundary.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
    profile: str
    connection: str
    session: str
    actor: str


@dataclass(frozen=True)
class Grant:
    nonce: str


class Authority:
    def __init__(self, verify_event, *, clock=time.monotonic):
        self._verify = verify_event
        self._clock = clock
        self._grants = {}
        self._lock = threading.Lock()

    def approve(self, event, scope, action, digest):
        if not self._verify(event, scope, action, digest):
            raise PermissionError("trusted owner action required")
        with self._lock:
            now = self._clock()
            self._grants = {k: v for k, v in self._grants.items() if v[3] > now}
            if len(self._grants) >= 128:
                raise PermissionError("approval capacity reached")
            grant = Grant(secrets.token_urlsafe(32))
            self._grants[grant.nonce] = (scope, action, digest, now + 120)
            return grant

    def consume(self, grant, scope, action, digest):
        with self._lock:
            row = self._grants.pop(grant.nonce, None) if type(grant) is Grant else None
            if row is None or row[:3] != (scope, action, digest) or row[3] <= self._clock():
                raise PermissionError("missing, stale, replayed or wrong-scope approval")

    def invalidate(self, scope):
        with self._lock:
            self._grants = {k: v for k, v in self._grants.items() if v[0] != scope}
