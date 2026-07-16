"""Message framing for the debugger's own JSON-over-TCP-loopback protocol.

Not a port of anything -- there's no legacy debugger code in this repo at
all (see qtedit/qtedit/debugger/tracee.py's docstring), and no real DBGP
interop need (nothing here talks to Xdebug/pydbgp), so a plain,
unambiguous 4-byte-length-prefix framing was chosen over both DBGP's
XML-over-TCP wire format and codeintel_client.py's delimiter-less
"<decimal-digits><json>" framing (that one only looks the way it does
because it has to match codeintel2's own oop/driver.py exactly -- there's
no such constraint here).

Two flavors of the same framing: `MessageBuffer` for the Qt side
(session.py), which gets raw bytes in arbitrary chunks from
QTcpSocket.readyRead and needs to reassemble them incrementally; and
`send_message`/`recv_message` for the debuggee side (tracee.py), a plain
blocking `socket.socket` with no event loop.
"""
import json
import struct

HEADER_SIZE = 4  # big-endian uint32 payload length


def encode_message(obj):
    payload = json.dumps(obj).encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


class MessageBuffer:
    """Feed it raw bytes as they arrive; get back a list of complete
    decoded messages (usually 0 or 1, but a burst can deliver more)."""

    def __init__(self):
        self._buf = b""

    def feed(self, data):
        self._buf += bytes(data)
        messages = []
        while True:
            if len(self._buf) < HEADER_SIZE:
                break
            (length,) = struct.unpack(">I", self._buf[:HEADER_SIZE])
            if len(self._buf) < HEADER_SIZE + length:
                break
            payload = self._buf[HEADER_SIZE : HEADER_SIZE + length]
            self._buf = self._buf[HEADER_SIZE + length :]
            messages.append(json.loads(payload.decode("utf-8")))
        return messages


def send_message(sock, obj):
    sock.sendall(encode_message(obj))


def recv_message(sock):
    """Blocking read of exactly one full message. Returns None if the
    peer closed the connection before a complete message arrived."""
    header = _recv_exact(sock, HEADER_SIZE)
    if header is None:
        return None
    (length,) = struct.unpack(">I", header)
    payload = _recv_exact(sock, length)
    if payload is None:
        return None
    return json.loads(payload.decode("utf-8"))


def _recv_exact(sock, n):
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
