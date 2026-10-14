"""Bounded forward-only fixture contribution service, independent of diagnosis.

Production transport is deliberately unavailable until a reviewed service policy
exists. No worker is installed: host lifecycle owners call tick() when resident.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
import urllib.request
from urllib.parse import urlsplit

from shared_contracts.diagnostic_batch import COUNTS, encode, package, validate_cell


class FixtureTransport:
    def __init__(self, destination):
        p = urlsplit(destination)
        if (
            p.scheme != "http"
            or p.hostname != "127.0.0.1"
            or not p.port
            or p.path not in {"", "/"}
            or p.username
            or p.password
            or p.query
            or p.fragment
        ):
            raise ValueError("only an explicitly configured loopback fixture collector is supported")
        self.destination = destination.rstrip("/")

    def request(self, method, path, data, deletion):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise ValueError("redirect rejected")

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        req = urllib.request.Request(
            self.destination + path,
            data,
            method=method,
            headers={"Content-Type": "application/json", "X-Deletion-Credential": deletion},
        )
        with opener.open(req, timeout=2) as response:
            raw = response.read(2049)
            if len(raw) > 2048 or response.status != 200:
                raise ValueError("invalid acknowledgement")
            return json.loads(raw)


class Contributions:
    def __init__(self, path, scope, authority, transport=None, *, clock=time.time):
        self.scope, self.authority, self.transport, self.clock = scope, authority, transport, clock
        self.lock = threading.RLock()
        if not str(path) == ":memory:":
            fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            os.close(fd)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS owner(profile TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, body BLOB, deletion TEXT,
                epoch TEXT, created REAL, attempts INTEGER, due REAL);
            CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY, deletion TEXT, state TEXT);
        """)
        owner = self.db.execute("SELECT profile FROM owner").fetchone()
        if owner is not None and owner[0] != scope.profile:
            self.db.close()
            raise PermissionError("contribution store belongs to another profile")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO owner VALUES(?)", (scope.profile,))
        # Restart eligibility is ambiguous. Never resurrect historical consent or queues.
        with self.db:
            self.db.execute("DELETE FROM outbox")
        self.state, self.epoch, self.cells = "LOCAL_ONLY", None, []
        self.dropped = 0
        self.next_batch = clock() + 86400 + secrets.randbelow(3600)
        self.policy = {
            "recipient": "Minefield fixture (not Nous)",
            "destination": transport.destination if transport else None,
            "schema": "diagnostic_batch.v1",
            "purpose": "diagnostic prioritisation",
            "cadence_seconds": 86400,
            "retention_days": 30,
            "deletion": "receipt credential",
            "transport_visibility": "receiver sees IP; no anonymity guarantee",
        }
        self.digest = hashlib.sha256(json.dumps(self.policy, sort_keys=True).encode()).hexdigest()

    def change(self, mode, grant):
        if mode not in {"AUTO_METADATA_ENABLED", "PAUSED", "REVOKED", "PREVIEW_ONLY", "LOCAL_ONLY"}:
            raise ValueError("invalid consent state")
        self.authority.consume(grant, self.scope, "consent:" + mode, self.digest)
        if mode == "AUTO_METADATA_ENABLED" and self.transport is None:
            raise ValueError("no recipient configured")
        with self.lock, self.db:
            self.db.execute("DELETE FROM outbox")
            self.cells.clear()
            self.state = mode
            self.epoch = secrets.token_hex(16) if mode == "AUTO_METADATA_ENABLED" else None
            self.next_batch = self.clock() + 86400 + secrets.randbelow(3600)

    def observe(self, cell):
        validate_cell(cell)
        with self.lock:
            if self.state != "AUTO_METADATA_ENABLED":
                return False
            # Aggregate identical finite dimensions, bounded before any disk write.
            identity = {k: v for k, v in cell.items() if k != "counts"}
            for existing in self.cells:
                if {k: v for k, v in existing.items() if k != "counts"} == identity:
                    if any(existing["counts"][k] + cell["counts"][k] > 10000 for k in COUNTS):
                        self.dropped += 1
                        return False
                    for k in COUNTS:
                        existing["counts"][k] += cell["counts"][k]
                    return True
            if len(self.cells) >= 128:
                self.dropped += 1
                return False
            self.cells.append(json.loads(json.dumps(cell)))
            return True

    def preview(self):
        with self.lock:
            return [bytes(row[0]) for row in self.db.execute("SELECT body FROM outbox ORDER BY created")]

    def seal(self):
        with self.lock, self.db:
            if self.state != "AUTO_METADATA_ENABLED" or not self.cells:
                return None
            body = encode(package(self.cells))
            size = self.db.execute("SELECT COALESCE(SUM(LENGTH(body)),0) FROM outbox").fetchone()[0]
            if size + len(body) > 1048576:
                self.cells.clear()
                self.dropped += 1
                return None
            pid = json.loads(body)["package_id"]
            self.db.execute(
                "INSERT INTO outbox VALUES(?,?,?,?,?,0,?)",
                (pid, body, secrets.token_hex(32), self.epoch, self.clock(), self.clock()),
            )
            self.cells.clear()
            return body

    def tick(self):
        """One bounded automatic attempt. Failure never raises into Hermes work."""
        try:
            with self.lock:
                now = self.clock()
                with self.db:
                    self.db.execute(
                        "DELETE FROM outbox WHERE created <= ? OR attempts >= 5", (now - 72 * 3600,)
                    )
                if self.state != "AUTO_METADATA_ENABLED" or self.transport is None:
                    return "OFF"
                if self.transport.destination != self.policy["destination"]:
                    self.state, self.epoch = "REVOKED", None
                    self.cells.clear()
                    with self.db:
                        self.db.execute("DELETE FROM outbox")
                    return "POLICY_CHANGED"
                if self.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] >= 128:
                    return "RECEIPT_CAPACITY"
                if now >= self.next_batch:
                    self.seal()
                    self.next_batch = now + 86400 + secrets.randbelow(3600)
                row = self.db.execute(
                    "SELECT id,body,deletion,epoch,attempts FROM outbox WHERE due<=? ORDER BY created LIMIT 1",
                    (now,),
                ).fetchone()
                if not row:
                    return "IDLE"
                pid, body, deletion, epoch, attempts = row
                if epoch != self.epoch:
                    with self.db:
                        self.db.execute("DELETE FROM outbox WHERE id=?", (pid,))
                    return "INELIGIBLE"
                # Mark attempt and retain deletion credentials before wire activity:
                # a lost acknowledgement must not orphan a retained remote package.
                with self.db:
                    self.db.execute(
                        "UPDATE outbox SET attempts=?,due=? WHERE id=?",
                        (attempts + 1, now + min(3600, 60 * 2**attempts), pid),
                    )
                    self.db.execute(
                        "INSERT OR IGNORE INTO receipts VALUES(?,?,?)", (pid, deletion, "send_uncertain")
                    )
                # Lock defines send-start vs revocation. Revocation can take up to
                # the 2s transport timeout; already transmitted data cannot be unsent.
                ack = self.transport.request("POST", "/v1/diagnostic-batches", bytes(body), deletion)
                if ack != {"package_id": pid, "retention_days": 30, "accepted": True}:
                    raise ValueError("invalid acknowledgement")
                with self.db:
                    self.db.execute("DELETE FROM outbox WHERE id=?", (pid,))
                    self.db.execute("UPDATE receipts SET state='acknowledged' WHERE id=?", (pid,))
                return "SENT"
        except Exception:
            return "RETRY_PENDING"

    def delete_remote(self, pid, grant):
        self.authority.consume(grant, self.scope, "delete:" + pid, self.digest)
        with self.lock:
            row = self.db.execute("SELECT deletion FROM receipts WHERE id=?", (pid,)).fetchone()
            if row is None or self.transport is None:
                raise ValueError("no deletion receipt")
            response = self.transport.request("DELETE", "/v1/diagnostic-batches/" + pid, None, row[0])
            if response != {"deleted": True}:
                raise ValueError("deletion unconfirmed")
            with self.db:
                self.db.execute("DELETE FROM outbox WHERE id=?", (pid,))
                self.db.execute("UPDATE receipts SET state='deleted' WHERE id=?", (pid,))

    def status(self):
        with self.lock:
            return {
                "state": self.state,
                "recipient_configured": self.transport is not None,
                "pending": self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0],
                "history": [
                    {"package_id": p, "state": s}
                    for p, s in self.db.execute("SELECT id,state FROM receipts LIMIT 128")
                ],
                "dropped": self.dropped,
                "next_eligible": self.next_batch,
            }

    def purge_local(self, grant):
        """Forget local queue/history, not already received remote packages."""
        self.authority.consume(grant, self.scope, "purge_local", self.digest)
        with self.lock, self.db:
            self.state, self.epoch = "LOCAL_ONLY", None
            self.cells.clear()
            self.db.execute("DELETE FROM outbox")
            self.db.execute("DELETE FROM receipts")

    def close(self):
        with self.lock:
            self.db.close()
