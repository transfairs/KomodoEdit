"""Client for Komodo's existing codeintel2 out-of-process (OOP) driver.

src/codeintel/lib/codeintel2/oop/driver.py already runs standalone, talking
JSON over stdio with a simple <decimal-byte-length><json-bytes> framing (no
delimiter -- the reader stops consuming digits as soon as it sees the JSON's
opening "{"). Every request carries a "command" and a "req_id"; every
response echoes that "req_id" back so callers can be matched to callbacks.
This client re-implements that framing in Python 3/Qt (QProcess) so the new
frontend can drive the *existing*, unmodified codeintel2 engine -- it does
not touch codeintel2 itself.

codeintel2 only runs under Python 2 (its own oop/driver.py is
`#!/usr/bin/env python2` and imports Python-2-only stdlib names), so the
driver itself is spawned as a Python 2 subprocess; this client is plain
Python 3 talking to it over a pipe, so the language split is invisible past
this module.
"""
import itertools
import json
import os

from PySide6.QtCore import QObject, QProcess, Signal

KOMODO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OOP_DRIVER = os.path.join(KOMODO_ROOT, "src", "codeintel", "bin", "oop-driver.py")
DEFAULT_PYTHON2 = os.path.expanduser("~/.cache/komodo-repro/python2.7/bin/python2.7")

# codeintel2 needs a handful of compiled/pure-Python dependencies
# (SilverCity, apsw, ciElementTree, langinfo) that aren't on a plain
# bootstrap Python 2.7's path. A full `bk build` would assemble these into
# one siloed site-packages tree; short of that, a prior partial build
# already produced the compiled pieces under build/release/, so point
# straight at those rather than rebuilding them.
DEFAULT_IMPORT_PATHS = [
    os.path.join(KOMODO_ROOT, "build", "release", "silvercity", "build", "lib.linux-x86_64-2.7"),
    os.path.join(KOMODO_ROOT, "build", "release", "apsw", "build", "lib.linux-x86_64-2.7"),
    os.path.join(KOMODO_ROOT, "build", "release", "codeintel", "lib"),
    os.path.join(KOMODO_ROOT, "src", "python-sitelib"),
    os.path.join(KOMODO_ROOT, "build", "release", "contrib", "zope", "cachedescriptors", "build", "lib"),
]


class CodeIntelClient(QObject):
    """Async client for the codeintel2 OOP driver.

    Fire-and-forget requests go through `request()`, which returns the
    req_id; pass a callback to get invoked with the matching response dict
    once it arrives. Unsolicited driver messages (progress/logging, and the
    initial handshake) are dropped unless a callback is registered for them,
    which is fine for this MVP -- nothing here depends on them yet.
    """

    errorOccurred = Signal(str)

    def __init__(self, python2_exe=None, import_paths=None, extra_args=None, parent=None):
        super().__init__(parent)
        self._python2_exe = python2_exe or DEFAULT_PYTHON2
        self._req_ids = itertools.count(1)
        self._callbacks = {}
        self._recv_buf = b""
        self._expected_len = None

        # Deliberately no --log-file: passing the magic values "stdout" or
        # "stderr" makes oop-driver.py repoint sys.stdout at sys.stderr's
        # stream object, which then makes it hand us stderr's fd as the
        # protocol channel -- silently breaking framing. Omitting it lets
        # oop-driver.py's own DummyStream swallow log output and leaves the
        # stdio fds alone. (Pass extra_args=["--log-file", "/some/real/path",
        # ...] for debugging -- a real file path is fine, just not the
        # "stdout"/"stderr" magic values.)
        args = [OOP_DRIVER]
        for path in import_paths if import_paths is not None else DEFAULT_IMPORT_PATHS:
            args += ["--import-path", path]
        if extra_args:
            args += extra_args

        self._proc = QProcess(self)
        self._proc.setProgram(self._python2_exe)
        self._proc.setArguments(args)
        self._proc.readyReadStandardOutput.connect(self._on_ready_read)
        self._proc.readyReadStandardError.connect(self._on_stderr)
        self._proc.errorOccurred.connect(
            lambda err: self.errorOccurred.emit(f"codeintel2 process error: {err}")
        )
        self._proc.start()

    def is_running(self):
        return self._proc.state() == QProcess.ProcessState.Running

    def request(self, command, callback=None, **kwargs):
        req_id = next(self._req_ids)
        payload = dict(kwargs)
        payload["command"] = command
        payload["req_id"] = req_id
        if callback is not None:
            self._callbacks[req_id] = callback
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        frame = str(len(data)).encode("ascii") + data
        self._proc.write(frame)
        return req_id

    def scan_document(self, path, text, language="Python", callback=None):
        return self.request(
            "scan-document",
            path=path,
            text=text,
            language=language,
            priority=1,
            callback=callback,
        )

    def trg_from_pos(self, path, pos, callback, implicit=False):
        return self.request(
            "trg-from-pos", path=path, pos=pos, implicit=implicit, callback=callback
        )

    def eval_trigger(self, trg, callback):
        return self.request("eval", trg=trg, callback=callback)

    def _on_stderr(self):
        # codeintel2's own logging; surfaced for debugging, not parsed.
        self._proc.readAllStandardError()

    def _on_ready_read(self):
        self._recv_buf += bytes(self._proc.readAllStandardOutput())
        while True:
            if self._expected_len is None:
                split = self._split_length_prefix()
                if split is None:
                    return
                self._expected_len, self._recv_buf = split
            if len(self._recv_buf) < self._expected_len:
                return
            frame, self._recv_buf = (
                self._recv_buf[: self._expected_len],
                self._recv_buf[self._expected_len :],
            )
            self._expected_len = None
            self._dispatch(frame)

    def _split_length_prefix(self):
        for i, byte in enumerate(self._recv_buf):
            char = chr(byte)
            if char == "{":
                if i == 0:
                    # No digits at all -- malformed; drop the byte and retry.
                    return None
                length = int(self._recv_buf[:i], 10)
                return length, self._recv_buf[i:]
            if not char.isdigit():
                # Unexpected byte where a length digit was expected; drop it
                # so a single corrupt byte can't wedge the parser forever.
                self._recv_buf = self._recv_buf[i + 1 :]
                return self._split_length_prefix()
        return None

    def _dispatch(self, frame):
        try:
            data = json.loads(frame.decode("utf-8"))
        except ValueError:
            self.errorOccurred.emit(f"codeintel2: malformed frame: {frame!r}")
            return
        req_id = data.get("req_id")
        callback = self._callbacks.pop(req_id, None) if req_id is not None else None
        if callback is not None:
            callback(data)

    def shutdown(self):
        # Killing/terminating the process fires errorOccurred asynchronously;
        # by the time it does, this CodeIntelClient (and its `errorOccurred`
        # signal) may already be gone if the whole window is closing, which
        # crashes with "Signal source has been deleted". We're intentionally
        # tearing down here, so that signal is uninteresting -- disconnect
        # first rather than trying to outrace teardown order.
        self._proc.errorOccurred.disconnect()
        if self.is_running():
            self.request("quit")
            self._proc.waitForFinished(2000)
        if self.is_running():
            self._proc.kill()
            self._proc.waitForFinished(1000)
