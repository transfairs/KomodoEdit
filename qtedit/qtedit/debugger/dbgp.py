"""PHP debugging via the real DBGP protocol (what Xdebug speaks) -- the
second protocol adapter alongside session.py's bespoke JSON protocol for
Python. Unlike the Python case, there's a real external interop partner
here (Xdebug) that qtedit doesn't control, so this wire format is not
invented -- it was captured empirically against a real `php`+Xdebug 3.5.0
process (see the plan doc's PHP-Debugger phase) rather than reconstructed
from memory, and every command/response shape below is exactly what that
probe observed, not a guess:

- Framing is asymmetric: responses/the init packet (Xdebug -> IDE) are
  "<decimal-length>\\0<xml>\\0"; commands (IDE -> Xdebug) are plain text
  "command -i <transaction_id> -flag value ...\\0" with NO length prefix.
- Every command gets exactly one response, correlated by transaction_id --
  there is no separate asynchronous event channel the way session.py's
  protocol has one. The "stopped at a line" information rides inside the
  response to whatever run/step command caused it
  (status="break" + a nested <xdebug:message filename=".." lineno=".."/>),
  but that response does NOT include the full call stack -- a follow-up
  stack_get command is needed for that, which is why _on_run_or_step_response
  below chains into a stack_get before finally emitting `stopped`.
- All paths are file:// URIs, not raw paths.

DbgpSession exposes the exact same signal/method surface as
session.DebugSession (stopped/localsReceived/output/terminated,
start/continue_/step_over/step_into/step_out/stop/get_locals) so
main_window.py's existing debug UI wiring works unmodified for either
language -- only the choice of which class to instantiate differs.
"""
import base64
import os
import xml.etree.ElementTree as ET

from PySide6.QtCore import QObject, QProcess, Signal
from PySide6.QtNetwork import QHostAddress, QTcpServer

DBGP_NS = "urn:debugger_protocol_v1"
XDEBUG_NS = "https://xdebug.org/dbgp/xdebug"


def _to_file_uri(path):
    return f"file://{os.path.abspath(path)}"


def _from_file_uri(uri):
    return uri[len("file://") :] if uri.startswith("file://") else uri


class DbgpBuffer:
    """Incremental reassembler for DBGP's "<decimal-length>\\0<xml>\\0"
    framing (the Xdebug -> IDE direction only -- outgoing commands aren't
    framed this way, see module docstring)."""

    def __init__(self):
        self._buf = b""

    def feed(self, data):
        self._buf += bytes(data)
        messages = []
        while True:
            msg = self._try_extract()
            if msg is None:
                break
            messages.append(msg)
        return messages

    def _try_extract(self):
        if b"\x00" not in self._buf:
            return None
        length_part, rest = self._buf.split(b"\x00", 1)
        try:
            length = int(length_part)
        except ValueError:
            # Corrupt stream -- drop the bad length field and keep going
            # rather than wedging the parser forever on one bad byte run.
            self._buf = rest
            return None
        if len(rest) < length + 1:  # +1 for the trailing \0 after the XML
            return None
        xml_bytes = rest[:length]
        self._buf = rest[length + 1 :]
        return xml_bytes.decode("utf-8", errors="replace")


class DbgpSession(QObject):
    stopped = Signal(str, list)  # reason, stack (list of dicts)
    localsReceived = Signal(int, list)  # frame_index, variables
    output = Signal(str, bool)  # text, is_stderr
    terminated = Signal(int)  # exit_code

    DEFAULT_PORT = 9003

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self._socket = None
        self._buffer = DbgpBuffer()
        self._next_transaction_id = 1
        self._pending = {}  # transaction_id -> callback(root_element)
        self._pending_breakpoint_lines = []
        self._script_uri = None
        self._got_init = False

        self._server = QTcpServer(self)
        self._server.listen(QHostAddress.LocalHost, self.DEFAULT_PORT)
        self._server.newConnection.connect(self._on_new_connection)

    def is_running(self):
        return self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning

    def start(self, script_path, breakpoint_lines):
        if self.is_running():
            return
        self._script_uri = _to_file_uri(script_path)
        self._pending_breakpoint_lines = list(breakpoint_lines)
        self._got_init = False

        self._proc = QProcess(self)
        self._proc.setProgram("php")
        self._proc.setArguments(
            [
                "-dxdebug.mode=debug",
                "-dxdebug.start_with_request=yes",
                f"-dxdebug.client_port={self._server.serverPort()}",
                "-dxdebug.client_host=127.0.0.1",
                script_path,
            ]
        )
        self._proc.setWorkingDirectory(os.path.dirname(script_path))
        self._proc.readyReadStandardOutput.connect(self._on_stdout)
        self._proc.readyReadStandardError.connect(self._on_stderr)
        self._proc.finished.connect(self._on_process_finished)
        self._proc.start()

    def continue_(self):
        self._send_run_like("continue", "run")

    def step_over(self):
        self._send_run_like("step", "step_over")

    def step_into(self):
        self._send_run_like("step", "step_into")

    def step_out(self):
        self._send_run_like("step", "step_out")

    def get_locals(self, frame_index):
        self._send("context_get", {"d": frame_index}, self._on_context_get_response, frame_index)

    def stop(self):
        self._send("stop", {}, None)
        if self._proc is not None:
            self._proc.kill()

    def _send_run_like(self, reason, command):
        self._send(command, {}, lambda root: self._on_run_or_step_response(root, reason))

    def _send(self, command, flags, callback, *callback_extra_args):
        if self._socket is None:
            return
        tid = self._next_transaction_id
        self._next_transaction_id += 1
        if callback is not None:
            self._pending[tid] = (callback, callback_extra_args)
        parts = [command, "-i", str(tid)]
        for flag, value in flags.items():
            parts += [f"-{flag}", str(value)]
        self._socket.write((" ".join(parts) + "\x00").encode("utf-8"))

    def _on_new_connection(self):
        self._socket = self._server.nextPendingConnection()
        self._socket.readyRead.connect(self._on_socket_ready_read)

    def _on_socket_ready_read(self):
        for xml_text in self._buffer.feed(self._socket.readAll()):
            try:
                root = ET.fromstring(xml_text)
            except ET.ParseError:
                continue
            self._handle_message(root)

    def _handle_message(self, root):
        if not self._got_init:
            self._got_init = True
            self._on_init()
            return
        tid_text = root.get("transaction_id")
        if tid_text is None:
            return
        entry = self._pending.pop(int(tid_text), None)
        if entry is None:
            return
        callback, extra_args = entry
        callback(root, *extra_args)

    def _on_init(self):
        self._send_next_breakpoint()

    def _send_next_breakpoint(self):
        if self._pending_breakpoint_lines:
            line = self._pending_breakpoint_lines.pop(0)
            self._send(
                "breakpoint_set",
                {"t": "line", "f": self._script_uri, "n": line},
                lambda _root: self._send_next_breakpoint(),
            )
        else:
            self._send_run_like("breakpoint", "run")

    def _on_run_or_step_response(self, root, reason):
        status = root.get("status")
        if status == "break":
            self._send("stack_get", {}, lambda stack_root: self._emit_stopped(stack_root, reason))
        elif status in ("stopping", "stopped"):
            # Empirically verified: Xdebug does not let the script actually
            # finish running after reporting "stopping" until it receives
            # an explicit stop command (a probe that just closed the
            # socket at this point also worked, but sending `stop` is the
            # documented, clean way to do it without dropping the
            # connection out from under any still-buffering stdout/stderr).
            # `terminated` itself is still emitted from QProcess.finished
            # (see _on_process_finished), not here -- same reasoning as
            # session.py's DebugSession: guarantees any already-buffered
            # stdout/stderr has been delivered to Qt first.
            self._send("stop", {}, None)

    def _emit_stopped(self, stack_root, reason):
        entries = []
        for elem in stack_root.findall(f"{{{DBGP_NS}}}stack"):
            entries.append(
                {
                    "function": elem.get("where", ""),
                    "filename": _from_file_uri(elem.get("filename", "")),
                    "line": int(elem.get("lineno", "0")),
                }
            )
        self.stopped.emit(reason, entries)

    def _on_context_get_response(self, root, frame_index):
        variables = []
        for prop in root.findall(f"{{{DBGP_NS}}}property"):
            name = prop.get("name", "")
            var_type = prop.get("type", "")
            text = prop.text or ""
            if prop.get("encoding") == "base64":
                try:
                    text = base64.b64decode(text).decode("utf-8", errors="replace")
                except Exception:
                    pass
            variables.append({"name": name, "type": var_type, "value": text})
        self.localsReceived.emit(frame_index, variables)

    def _on_stdout(self):
        if self._proc is not None:
            text = bytes(self._proc.readAllStandardOutput()).decode("utf-8", errors="replace")
            self.output.emit(text, False)

    def _on_stderr(self):
        if self._proc is not None:
            text = bytes(self._proc.readAllStandardError()).decode("utf-8", errors="replace")
            self.output.emit(text, True)

    def _on_process_finished(self, exit_code, _exit_status):
        self._socket = None
        self._buffer = DbgpBuffer()
        self._pending = {}
        # Release port 9003 so a later debug run's fresh DbgpSession can
        # bind it again -- unlike session.py's ephemeral-port DebugSession,
        # this port is fixed (Xdebug's own default), so a lingering bound
        # QTcpServer here would make every subsequent PHP debug run fail
        # to bind silently.
        self._server.close()
        self.terminated.emit(exit_code)
