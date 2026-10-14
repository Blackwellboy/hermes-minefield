"""Doctor's single-slot guard reads the real server (llama.cpp /props, /slots)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from hermes_minefield.concurrency import probe_concurrency, requires_doctor_confirm


def serve(routes: dict[str, object]):
    seen_auth: list[str | None] = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen_auth.append(self.headers.get("Authorization"))
            body = routes.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}/v1", seen_auth


@pytest.mark.parametrize(
    ("routes", "slots", "single"),
    [
        ({"/props": {"total_slots": 1}}, 1, True),
        ({"/props": {"total_slots": 4}}, 4, False),
        ({"/props": {"default_generation_settings": {"n_slots": 2}}}, 2, False),
        ({"/slots": [{"id": 0}]}, 1, True),
    ],
)
def test_probe_reads_slots(routes, slots, single):
    srv, url, _ = serve(routes)
    try:
        info = probe_concurrency(url)
    finally:
        srv.shutdown()
    assert (info.known_concurrency, info.single_slot_likely) == (slots, single)
    assert requires_doctor_confirm(info) is single


def test_unknown_requires_confirmation():
    srv, url, _ = serve({})
    try:
        info = probe_concurrency(url)
    finally:
        srv.shutdown()
    assert info.known_concurrency is None
    assert requires_doctor_confirm(info) is True  # unknown is not "safe"


def test_probe_sends_key_when_given():
    srv, url, auth = serve({"/props": {"total_slots": 2}})
    try:
        probe_concurrency(url, api_key="k-123")
        probe_concurrency(url)
    finally:
        srv.shutdown()
    assert auth == ["Bearer k-123", None]
