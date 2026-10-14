"""Test-process network fence: only listeners created by this process are reachable.

Not shipped as a runtime security mechanism. Public dependency installation runs
separately. Children inherit this fence, never real credentials or profiles.
"""

import socket
import weakref
import secrets

_ports = weakref.WeakValueDictionary()
_bind = socket.socket.bind
_connect = socket.socket.connect


def bind(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        if address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise PermissionError("isolated tests may bind only loopback")
        if address[1] == 0:
            # Windows may repeatedly allocate the same server port with reuse
            # enabled, exhausting the client tuple space in large fixture suites.
            # Spread test listeners without changing system TCP settings.
            for _ in range(128):
                candidate = (address[0], 20000 + secrets.randbelow(28000), *address[2:])
                try:
                    result = _bind(self, candidate)
                    break
                except OSError:
                    continue
            else:
                raise OSError("test listener port allocation exhausted")
        else:
            result = _bind(self, address)
        _ports[self.getsockname()[1]] = self
        return result
    return _bind(self, address)


def connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        listener = _ports.get(address[1])
        if (address[0] not in ("127.0.0.1", "::1", "localhost") or listener is None
                or listener.fileno() < 0):
            raise PermissionError("network denied: not a test-owned loopback listener")
    return _connect(self, address)


socket.socket.bind = bind
socket.socket.connect = connect


def connect_ex(self, address):
    connect(self, address)
    return 0


def sendto(self, *args):
    raise PermissionError("datagram network disabled in isolated tests")


socket.socket.connect_ex = connect_ex
socket.socket.sendto = sendto
