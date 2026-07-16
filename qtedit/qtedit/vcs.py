"""Git integration -- no Qt, no XPCOM.

Legacy Komodo Edit has no working VCS/SCC backend to port or reimplement
against: `koIFileStatusService.idl`'s `koIFileStatusChecker` interface only
ever got a disk-mtime implementation (`KoDiskFileChecker`,
src/filesystem/fileStatusUtils.p.py:263-297); `koChangeTracker.py` builds a
`koSCC?type=git` contract ID that resolves to nothing, and the one project-
tree SCC context-menu hook (project_places_SPV.js) calls a function that's
never defined anywhere in this tree. SCC was a commercial Komodo IDE
feature that never shipped in Edit's open-source code. This module is a
from-scratch build, informed only by the status vocabulary that survives in
skin/global/components/scc.less (ok/add/delete/edit/conflict) as rough
orientation, not a port of anything.

Thin subprocess wrapper around the `git` CLI -- no GitPython/pygit2
dependency, matching the rest of this project's "wrap the real tool" style
(codeintel_client.py drives a real process; this does too).
"""
import subprocess
from dataclasses import dataclass


@dataclass
class FileStatus:
    path: str
    index_code: str  # git status --porcelain's X column (staged state)
    worktree_code: str  # Y column (unstaged state)

    @property
    def is_untracked(self):
        return self.index_code == "?" and self.worktree_code == "?"

    @property
    def is_staged(self):
        return self.index_code not in (" ", "?")


@dataclass
class LogEntry:
    short_hash: str
    author: str
    date: str
    subject: str


def _run(base_dir, args):
    result = subprocess.run(
        ["git", "-C", base_dir, *args],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def is_git_repo(base_dir):
    code, out, _err = _run(base_dir, ["rev-parse", "--is-inside-work-tree"])
    return code == 0 and out.strip() == "true"


def git_status(base_dir):
    code, out, _err = _run(base_dir, ["status", "--porcelain=v1"])
    if code != 0:
        return []
    statuses = []
    for line in out.splitlines():
        if not line:
            continue
        index_code, worktree_code = line[0], line[1]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        statuses.append(FileStatus(path=path, index_code=index_code, worktree_code=worktree_code))
    return statuses


def git_diff(base_dir, path, staged=False):
    args = ["diff", "--cached"] if staged else ["diff"]
    args += ["--", path]
    code, out, err = _run(base_dir, args)
    return out if code == 0 else err


def git_stage(base_dir, paths):
    _run(base_dir, ["add", "--", *paths])


def git_unstage(base_dir, paths):
    _run(base_dir, ["reset", "--", *paths])


def git_commit(base_dir, message):
    code, out, err = _run(base_dir, ["commit", "-m", message])
    return code == 0, out if code == 0 else err


def git_log(base_dir, limit=50):
    fmt = "%h\x1f%an\x1f%ad\x1f%s"
    code, out, _err = _run(
        base_dir, ["log", f"--pretty=format:{fmt}", "--date=short", f"-{limit}"]
    )
    if code != 0:
        return []
    entries = []
    for line in out.splitlines():
        if not line:
            continue
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        short_hash, author, date, subject = parts
        entries.append(LogEntry(short_hash=short_hash, author=author, date=date, subject=subject))
    return entries
