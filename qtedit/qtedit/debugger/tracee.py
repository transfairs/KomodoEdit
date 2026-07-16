"""Debuggee-side process: runs a target Python script under `bdb.Bdb`
(stdlib's own trace engine, the same one `pdb` is built on) and speaks
qtedit's own JSON debug protocol (protocol.py) back to session.py over a
TCP loopback connection.

There is no legacy Komodo debugger code anywhere in this repo to port --
searched exhaustively (koIDebugger*/koDBGP*/DBGP, see the plan doc's
Debugger phase) and found only three dangling references to a feature that
apparently never shipped in Komodo Edit (it may have existed in the
commercial Komodo IDE, but nothing survives here). This is a from-scratch
build. `user_line`/`user_return` below follow the same basic
stop-and-wait-for-a-command shape stdlib `pdb.Pdb` uses (see
pdb.py's `user_line`/`user_return`/`interaction`), just driven by socket
messages instead of a console command loop.

The target script's own stdout/stderr are left completely alone -- only
the debug *control* messages go over the TCP socket, so QProcess on the
session.py side can capture real program output normally, the same way it
already does for Toolbox command execution.
"""
import bdb
import os
import socket
import sys
import traceback

from qtedit.debugger import protocol


def _safe_repr(value):
    try:
        text = repr(value)
    except Exception as exc:
        return f"<repr() failed: {exc}>"
    return text if len(text) <= 500 else text[:500] + "..."


class Tracee(bdb.Bdb):
    def __init__(self, sock):
        super().__init__()
        self._sock = sock
        self._frames = []  # list[(frame, lineno)], innermost first
        self._entry_seen = False

    def do_clear(self, arg):
        # Only relevant for temporary breakpoints, which qtedit doesn't
        # set (set_break's temporary=False default) -- implemented anyway
        # since Bdb.break_here() requires the method to exist.
        self.clear_bpbynumber(arg)

    def user_line(self, frame):
        # bdb.Bdb.reset() leaves stopframe=None, which makes stop_here()
        # return True unconditionally -- so the very first traced line
        # always triggers user_line before any real code has run (the
        # same reason `python -m pdb script.py` always stops at line 1
        # before you type anything). qtedit has no "break on entry"
        # feature for v1: skip straight past this one *unless* it happens
        # to coincide with a real breakpoint, so "Start Debugging" reads
        # as "run until the first breakpoint", not "always stop at line 1".
        if not self._entry_seen:
            self._entry_seen = True
            if not self.break_here(frame):
                self.set_continue()
                return
        reason = "breakpoint" if self.break_here(frame) else "step"
        self._interact(frame, reason)

    def user_return(self, frame, _return_value):
        # Fires for the *returning* frame itself, at its return statement
        # -- not yet back in the caller (matches pdb's "--Return--", which
        # shows the same frame one last time before it actually pops).
        # One more step/continue from here lands in the caller.
        self._interact(frame, "return")

    def _interact(self, frame, reason):
        stack, _ = self.get_stack(frame, None)
        # get_stack() walks all the way to self.botframe, which is
        # Bdb.run()'s own `exec(cmd, globals, locals)` frame inside bdb.py
        # itself -- not useful to show the user, filtered out here rather
        # than in every display-facing caller.
        self._frames = [
            (f, lineno) for f, lineno in reversed(stack) if f.f_code.co_filename != bdb.__file__
        ]
        self._send_stopped(reason)
        while True:
            msg = protocol.recv_message(self._sock)
            if msg is None:
                self.set_quit()
                return
            cmd = msg.get("cmd")
            if cmd == "continue":
                self.set_continue()
                return
            if cmd == "step_over":
                self.set_next(frame)
                return
            if cmd == "step_into":
                self.set_step()
                return
            if cmd == "step_out":
                self.set_return(frame)
                return
            if cmd == "stop":
                self.set_quit()
                return
            if cmd == "get_locals":
                self._send_locals(msg.get("frame_index", 0))
                continue
            if cmd == "set_breakpoints":
                self._apply_breakpoints(msg)
                continue
            # Unknown command -- ignore and keep waiting rather than
            # silently resuming execution the user didn't ask for.

    def _apply_breakpoints(self, msg):
        self.clear_all_breaks()
        path = msg.get("path")
        for line in msg.get("lines", []):
            self.set_break(path, line)
        protocol.send_message(self._sock, {"event": "breakpoints_set"})

    def _send_stopped(self, reason):
        entries = [
            {
                "function": frame.f_code.co_name,
                "filename": frame.f_code.co_filename,
                "line": lineno,
            }
            for frame, lineno in self._frames
        ]
        protocol.send_message(self._sock, {"event": "stopped", "reason": reason, "stack": entries})

    def _send_locals(self, frame_index):
        if 0 <= frame_index < len(self._frames):
            frame, _lineno = self._frames[frame_index]
            variables = [
                {"name": name, "type": type(value).__name__, "value": _safe_repr(value)}
                for name, value in frame.f_locals.items()
            ]
        else:
            variables = []
        protocol.send_message(
            self._sock, {"event": "locals", "frame_index": frame_index, "variables": variables}
        )


def main():
    port = int(os.environ["QTEDIT_DEBUG_PORT"])
    script_path = os.path.abspath(sys.argv[1])
    sock = socket.create_connection(("127.0.0.1", port))
    tracee = Tracee(sock)

    protocol.send_message(sock, {"event": "ready"})
    # Handshake before the target script runs at all -- breakpoints must
    # be set before bdb.run() starts tracing, so this loop only handles
    # set_breakpoints/start/stop, not the full step/continue command set
    # (those only make sense once a frame is actually stopped).
    while True:
        msg = protocol.recv_message(sock)
        if msg is None:
            sock.close()
            return
        cmd = msg.get("cmd")
        if cmd == "set_breakpoints":
            tracee._apply_breakpoints(msg)
        elif cmd == "start":
            break
        elif cmd == "stop":
            sock.close()
            return

    with open(script_path, "r", encoding="utf-8") as f:
        source = f.read()
    code = compile(source, script_path, "exec")
    globs = {"__name__": "__main__", "__file__": script_path}

    exit_code = 0
    try:
        tracee.run(code, globs, globs)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else (1 if exc.code else 0)
    except BaseException:
        traceback.print_exc()
        exit_code = 1
    finally:
        protocol.send_message(sock, {"event": "terminated", "exit_code": exit_code})
        sock.close()


if __name__ == "__main__":
    main()
