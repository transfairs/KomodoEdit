"""Launcher for the ported codeintel3 OOP driver -- the Python-3
equivalent of src/codeintel/bin/oop-driver.py, which launches the
original codeintel2.oop.Driver as a subprocess for the legacy Python 2
path. Much simpler than the original launcher: no --import-path dance is
needed since codeintel3's dependencies (SilverCity shim, apsw, langinfo,
styles) already live as plain importable modules once
qtedit/qtedit/ is on sys.path (apsw is a real pip-installed package; the
rest are qtedit/qtedit/ siblings) -- see codeintel_client.py's Python-3
launch path for how this script is actually invoked.

fd_in/fd_out are plain text-mode streams, not binary -- codeintel3.oop.driver
speaks str (JSON text + a decimal-digit length prefix), not bytes,
matching how it already worked under Python 2 (where str was bytes-like).
The original oop-driver.py reopened stdout in binary "wb" mode as a
Python-2-era anti-buffering trick for Windows; the Python 3 equivalent is
reconfigure(write_through=True) below, keeping fd_out text-mode (matching
what Driver._send_proc's plain str writes expect) while still flushing
every write immediately so the Qt client isn't left waiting on a buffered
pipe.
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codeintel3.oop.driver import Driver


def main():
    if os.environ.get("QTEDIT_CODEINTEL_DEBUG_LOG"):
        logging.basicConfig(
            level=logging.DEBUG,
            filename=os.environ["QTEDIT_CODEINTEL_DEBUG_LOG"],
            filemode="w",
        )
    sys.stdout.reconfigure(write_through=True)
    db_base_dir = os.environ.get("QTEDIT_CODEINTEL_DB_BASE_DIR")
    driver = Driver(fd_in=sys.stdin, fd_out=sys.stdout, db_base_dir=db_base_dir)
    driver.start()
    driver.join()


if __name__ == "__main__":
    main()
