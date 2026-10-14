"""Test-process network fence: only listeners created by this process are reachable.

Not shipped as a runtime security mechanism. Public dependency installation runs
separately. Children inherit this fence, never real credentials or profiles.
"""

import socket

_ports = set()
_bind = socket.socket.bind
_connect = socket.socket.connect


def bind(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        if address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise PermissionError("isolated tests may bind only loopback")
        result = _bind(self, address)
        _ports.add(self.getsockname()[1])
        return result
    return _bind(self, address)


def connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        if address[0] not in ("127.0.0.1", "::1", "localhost") or address[1] not in _ports:
            raise PermissionError("network denied: not a test-owned loopback listener")
    return _connect(self, address)


socket.socket.bind = bind
socket.socket.connect = connect
