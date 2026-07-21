"""Client for the codeintel3 out-of-process (OOP) driver.

codeintel3 (qtedit/qtedit/codeintel3/) is a Python-3 port of Komodo's
original codeintel2 engine (src/codeintel/lib/codeintel2/), covering the
~19,800 LOC slice qtedit actually exercises (Python-language scan/trigger/
eval). See project memory (modernization_roadmap.md) for how the port was
scoped and verified. codeintel3/oop/driver.py runs standalone, talking JSON
over stdio with a simple <decimal-byte-length><json-bytes> framing (no
delimiter -- the reader stops consuming digits as soon as it sees the JSON's
opening "{"). Every request carries a "command" and a "req_id"; every
response echoes that "req_id" back so callers can be matched to callbacks.
This client re-implements that framing in Qt (QProcess).

Unlike codeintel2 (Python-2-only: `#!/usr/bin/env python2`, Python-2-only
stdlib imports), codeintel3 runs under the same Python 3 interpreter as
qtedit itself -- no separate bootstrap interpreter, no --import-path dance
(apsw is a real pip dependency; SilverCity/langinfo/textinfo/process/which
are qtedit/qtedit/ sibling modules already importable once that directory
is on sys.path, which oop_driver_main.py sets up itself).
"""
import itertools
import json
import os
import sys

from PySide6.QtCore import QObject, QProcess, Signal

OOP_DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "codeintel3", "oop_driver_main.py")


class CodeIntelClient(QObject):
    """Async client for the codeintel3 OOP driver.

    Fire-and-forget requests go through `request()`, which returns the
    req_id; pass a callback to get invoked with the matching response dict
    once it arrives. Unsolicited driver messages (progress/logging, and the
    initial handshake) are dropped unless a callback is registered for them,
    which is fine for this MVP -- nothing here depends on them yet.
    """

    errorOccurred = Signal(str)

    def __init__(self, python_exe=None, extra_args=None, parent=None):
        super().__init__(parent)
        self._python_exe = python_exe or sys.executable
        self._req_ids = itertools.count(1)
        self._callbacks = {}
        self._recv_buf = b""
        self._expected_len = None

        args = [OOP_DRIVER]
        if extra_args:
            args += extra_args

        self._proc = QProcess(self)
        self._proc.setProgram(self._python_exe)
        self._proc.setArguments(args)
        self._proc.readyReadStandardOutput.connect(self._on_ready_read)
        self._proc.readyReadStandardError.connect(self._on_stderr)
        self._proc.errorOccurred.connect(
            lambda err: self.errorOccurred.emit(f"codeintel3 process error: {err}")
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
        # codeintel3's own logging; surfaced for debugging, not parsed.
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
            self.errorOccurred.emit(f"codeintel3: malformed frame: {frame!r}")
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
