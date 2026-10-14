"""Actual client-to-loopback receiver bytes; authority fixture is NOT host proof."""

import json
import secrets
import threading
import time

import pytest

from hermes_minefield.contributions.outbox import Contributions, FixtureTransport
from hermes_minefield.service.authority import Authority, Scope
from services.collector.server import Collector, make_server
from shared_contracts.diagnostic_batch import ContractError, decode, encode, package, project


@pytest.fixture
def rig(tmp_path):
    clock = [1_800_000_000.0]
    admin = secrets.token_hex(32)
    collector = Collector(tmp_path / "collector.sqlite", admin_token=admin, clock=lambda: clock[0])
    server = make_server(collector)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    # A synthetic trusted event source, explicitly not a production UI verifier.
    event = object()
    scope = Scope("fixture-profile", "fixture-connection", "fixture-session", "fixture-owner")
    authority = Authority(lambda e, s, a, d: e is event and s == scope)
    transport = FixtureTransport(f"http://127.0.0.1:{server.server_port}")
    client = Contributions(tmp_path / "client.sqlite", scope, authority, transport, clock=lambda: clock[0])

    def grant(action):
        return authority.approve(event, scope, action, client.digest)

    yield client, collector, grant, clock, admin
    client.close()
    server.shutdown()
    server.server_close()
    thread.join()
    collector.close()


def cell():
    return project(origin="synthetic", observation="empty_answer", outcome="observed")


def enable(client, grant):
    client.change("AUTO_METADATA_ENABLED", grant("consent:AUTO_METADATA_ENABLED"))


def test_receiver_retention_runs_while_idle(rig):
    client, collector, grant, clock, _ = rig
    enable(client, grant)
    client.observe(cell())
    client.seal()
    assert client.tick() == "SENT"
    clock[0] += 31 * 86400
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with collector.lock:
            count = collector.db.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
        if count == 0:
            break
        time.sleep(0.02)
    assert count == 0  # No ingest, workbench read or explicit expire call.


def test_off_forward_only_exact_bytes_retry_delete(rig):
    client, collector, grant, clock, admin = rig
    assert not client.observe(cell())
    assert client.tick() == "OFF"
    assert client.status()["pending"] == 0
    enable(client, grant)
    assert client.seal() is None  # no pre-consent data
    assert client.observe(cell())
    expected = client.seal()
    assert client.preview() == [expected]
    assert client.tick() == "SENT"
    pid, body, deletion_hash, _ = collector.db.execute("SELECT * FROM packages").fetchone()
    assert bytes(body) == expected
    assert client.status()["history"] == [{"package_id": pid, "state": "acknowledged"}]
    token = client.db.execute("SELECT deletion FROM receipts").fetchone()[0]
    assert deletion_hash != token and token not in json.dumps(client.status())
    assert collector.ingest(expected, token)[0] == 200
    changed = decode(expected)
    changed["cells"][0]["feedback"] = "unchanged"
    assert collector.ingest(encode(changed), token)[0] == 409
    client.delete_remote(pid, grant("delete:" + pid))
    assert collector.db.execute("SELECT COUNT(*) FROM packages").fetchone()[0] == 0


def test_lost_ack_retains_deletion_and_revocation_prevents_retry(rig):
    client, collector, grant, clock, _ = rig
    enable(client, grant)
    client.observe(cell())
    body = client.seal()
    send = client.transport.request

    def lost_ack(*args):
        send(*args)
        raise OSError("synthetic secret-canary@example.invalid")

    client.transport.request = lost_ack
    assert client.tick() == "RETRY_PENDING"
    assert client.preview() == [body]
    assert client.status()["history"][0]["state"] == "send_uncertain"
    pid = decode(body)["package_id"]
    client.change("REVOKED", grant("consent:REVOKED"))
    clock[0] += 500
    assert client.tick() == "OFF" and client.preview() == []
    client.transport.request = send
    client.delete_remote(pid, grant("delete:" + pid))


def test_lost_ack_retries_identical_bytes(rig):
    client, collector, grant, clock, _ = rig
    enable(client, grant)
    client.observe(cell())
    body = client.seal()
    send = client.transport.request
    calls = []

    def once(*args):
        calls.append(args[2])
        result = send(*args)
        if len(calls) == 1:
            raise OSError("lost acknowledgement")
        return result

    client.transport.request = once
    assert client.tick() == "RETRY_PENDING"
    clock[0] += 61
    assert client.tick() == "SENT"
    assert calls == [body, body]
    assert collector.replays == 1


def test_workbench_suppression_retention_and_actual_delivery(rig):
    client, collector, grant, clock, admin = rig
    enable(client, grant)
    for _ in range(2):
        client.observe(cell())
        client.seal()
        assert client.tick() == "SENT"
    assert collector.workbench(admin)[1]["clusters"] == []
    assert collector.workbench("forged")[0] == 403
    client.observe(cell())
    client.seal()
    assert client.tick() == "SENT"
    clusters = collector.workbench(admin)[1]["clusters"]
    assert len(clusters) == 1 and clusters[0]["packages"] == 3
    assert clusters[0]["origin"] == "synthetic"
    pid = client.status()["history"][0]["package_id"]
    client.delete_remote(pid, grant("delete:" + pid))
    assert collector.workbench(admin)[1]["clusters"] == []
    clock[0] += 30 * 86400
    collector.expire()
    assert collector.db.execute("SELECT COUNT(*) FROM packages").fetchone()[0] == 0


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"a":NaN}',
        b"[" * 2000,
        b"x" * 32769,
        b'{"name":"private-canary@example.invalid"}',
        b"\xff",
    ],
    ids=["duplicate", "nonfinite", "depth", "oversize", "unknown", "encoding"],
)
def test_reject_malformed_closed_schema(raw):
    with pytest.raises(ContractError):
        decode(raw)


def test_unknown_nested_boolean_counts_and_private_mapping():
    data = package([cell()])
    data["cells"][0]["counts"]["eligible"] = True
    with pytest.raises(ContractError):
        encode(data)
    data = package([cell()])
    data["cells"][0]["shape"]["secret"] = "private-canary"
    with pytest.raises(ContractError):
        encode(data)
    raw = encode(
        package(
            [
                project(
                    origin="passive",
                    observation="none",
                    outcome="scoped_clean",
                    stack="private-canary@example.invalid",
                )
            ]
        )
    )
    assert b"private-canary" not in raw and b"custom" in raw


def test_forged_replayed_wrong_scope_grants(rig):
    client, _, grant, _, _ = rig
    with pytest.raises(PermissionError):
        client.change("AUTO_METADATA_ENABLED", {"approved": True})
    approved = grant("consent:AUTO_METADATA_ENABLED")
    client.change("AUTO_METADATA_ENABLED", approved)
    with pytest.raises(PermissionError):
        client.change("AUTO_METADATA_ENABLED", approved)
    with pytest.raises(PermissionError):
        client.authority.approve(
            {"approved": True}, client.scope, "consent:AUTO_METADATA_ENABLED", client.digest
        )
