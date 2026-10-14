"""Loopback reference receiver. No production deployment claim or raw body logs."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from shared_contracts.diagnostic_batch import COUNTS, MAX_BYTES, ContractError, decode


class Collector:
    def __init__(self, path, *, admin_token, clock=time.time, capacity=10000):
        if len(admin_token) < 32:
            raise ValueError("strong separately configured admin token required")
        self.admin_token = admin_token
        self.clock, self.capacity = clock, capacity
        self.lock = threading.RLock()
        # Restrictive creation mode on POSIX; Windows inherits the caller's ACL.
        if str(path) != ":memory:":
            fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS packages(id TEXT PRIMARY KEY, body BLOB, delete_hash TEXT, created REAL)"
        )
        self.db.execute("PRAGMA user_version=1")
        self.replays = self.rejections = 0
        self.rate_window, self.rate_count = clock(), 0

    def expire(self):
        with self.lock, self.db:
            self.db.execute("DELETE FROM packages WHERE created <= ?", (self.clock() - 30 * 86400,))

    def ingest(self, raw, deletion_token):
        batch = decode(raw)
        if (
            not isinstance(deletion_token, str)
            or len(deletion_token) != 64
            or any(c not in "0123456789abcdef" for c in deletion_token)
        ):
            raise ContractError("deletion credential")
        digest = hashlib.sha256(deletion_token.encode("ascii")).hexdigest()
        with self.lock, self.db:
            self.expire()
            now = self.clock()
            if now - self.rate_window >= 60:
                self.rate_window, self.rate_count = now, 0
            self.rate_count += 1
            if self.rate_count > 120:
                return 429, {"error": "rate_limit"}
            old = self.db.execute(
                "SELECT body, delete_hash FROM packages WHERE id=?", (batch["package_id"],)
            ).fetchone()
            if old:
                if bytes(old[0]) != raw or not secrets.compare_digest(old[1], digest):
                    return 409, {"error": "conflicting_duplicate"}
                self.replays += 1
            else:
                if self.db.execute("SELECT COUNT(*) FROM packages").fetchone()[0] >= self.capacity:
                    return 503, {"error": "storage_full"}
                self.db.execute(
                    "INSERT INTO packages VALUES(?,?,?,?)", (batch["package_id"], raw, digest, now)
                )
            return 200, {"package_id": batch["package_id"], "retention_days": 30, "accepted": True}

    def delete(self, package_id, token):
        with self.lock, self.db:
            row = self.db.execute("SELECT delete_hash FROM packages WHERE id=?", (package_id,)).fetchone()
            if row is None:
                return 200, {"deleted": True}
            if not secrets.compare_digest(row[0], hashlib.sha256(token.encode()).hexdigest()):
                return 403, {"error": "denied"}
            self.db.execute("DELETE FROM packages WHERE id=?", (package_id,))
            return 200, {"deleted": True}

    def workbench(self, token):
        if not secrets.compare_digest(token, self.admin_token):
            return 403, {"error": "denied"}
        with self.lock:
            self.expire()
            groups = {}
            for pid, raw, created in self.db.execute("SELECT id, body, created FROM packages"):
                for cell in decode(bytes(raw))["cells"]:
                    key = (
                        cell["origin"],
                        cell["observation"],
                        cell["outcome"],
                        cell["stack"],
                        cell["feedback"],
                    )
                    group = groups.setdefault(
                        key, {"packages": set(), "counts": dict.fromkeys(COUNTS, 0), "periods": []}
                    )
                    group["packages"].add(pid)
                    group["periods"].append(int(created // (7 * 86400)))
                    for name in COUNTS:
                        group["counts"][name] += cell["counts"][name]
            # One fixed partition, no totals, filters, arbitrary grouping or drill-down.
            # Package threshold is not unique people or a mathematical anonymity proof.
            rows = []
            for key, group in sorted(groups.items()):
                if len(group["packages"]) < 3:
                    continue
                rows.append(
                    {
                        "origin": key[0],
                        "observation": key[1],
                        "outcome": key[2],
                        "stack": key[3],
                        "feedback": key[4],
                        "packages": len(group["packages"]),
                        "counts": group["counts"],
                        "first_week": min(group["periods"]),
                        "last_week": max(group["periods"]),
                        "status": "needs_corroboration",
                    }
                )
            return 200, {
                "clusters": rows,
                "minimum_packages": 3,
                "unique_users": "not_measured",
                "replays": self.replays,
                "rejections": self.rejections,
                "warning": "unverified reports; suppression is not anonymity",
            }

    def close(self):
        self.db.close()


def make_server(collector, *, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log paths, credentials, arbitrary body or parser errors.

        def reply(self, status, payload):
            raw = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            self.connection.settimeout(2)
            if self.path != "/v1/diagnostic-batches":
                return self.reply(404, {"error": "not_found"})
            try:
                if (
                    self.headers.get("Content-Type") != "application/json"
                    or self.headers.get("Content-Encoding")
                    or self.headers.get("Transfer-Encoding")
                ):
                    raise ContractError("media")
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= MAX_BYTES:
                    raise ContractError("size")
                raw = self.rfile.read(int(lengths[0]))
                status, response = collector.ingest(raw, self.headers.get("X-Deletion-Credential", ""))
                return self.reply(status, response)
            except (ContractError, OSError):
                collector.rejections += 1
                return self.reply(400, {"error": "invalid_package"})

        def do_GET(self):
            if self.path != "/v1/workbench":
                return self.reply(404, {"error": "not_found"})
            self.reply(*collector.workbench(self.headers.get("Authorization", "").removeprefix("Bearer ")))

        def do_DELETE(self):
            prefix = "/v1/diagnostic-batches/"
            if not self.path.startswith(prefix) or len(self.path) != len(prefix) + 36:
                return self.reply(404, {"error": "not_found"})
            self.reply(
                *collector.delete(self.path[len(prefix) :], self.headers.get("X-Deletion-Credential", ""))
            )

    class RetainingServer(HTTPServer):
        def service_actions(self):
            # Runs while idle too, rather than depending on the next ingest.
            collector.expire()

        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(2)
            return connection, address

    server = RetainingServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    return server
