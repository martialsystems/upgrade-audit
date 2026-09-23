# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Read-only-leaning git helpers. Never reset --hard or discard."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .paths import worktree_parent


class GitError(RuntimeError):
    pass


def run_git(args: Sequence[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise GitError("git {0} failed in {1}: {2}".format(args[0], cwd, err))
    return proc


def is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    proc = run_git(["rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
    return proc.returncode == 0 and (proc.stdout or "").strip() == "true"


def porcelain(path: Path) -> List[str]:
    proc = run_git(["status", "--porcelain"], cwd=path)
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return lines


def dirty_paths(path: Path) -> List[str]:
    out: List[str] = []
    for line in porcelain(path):
        # XY PATH or XY ORIG -> PATH
        body = line[3:] if len(line) > 3 else line
        if " -> " in body:
            body = body.split(" -> ", 1)[1]
        out.append(body.strip())
    return out


def ensure_remote(path: Path, name: str, url: str) -> None:
    proc = run_git(["remote", "get-url", name], cwd=path, check=False)
    if proc.returncode == 0:
        return
    run_git(["remote", "add", name, url], cwd=path)


def fetch_remote(path: Path, name: str) -> None:
    run_git(["fetch", name, "--prune"], cwd=path)


def remote_default_branch(path: Path, remote: str) -> str:
    proc = run_git(
        ["symbolic-ref", "--quiet", "refs/remotes/{0}/HEAD".format(remote)],
        cwd=path,
        check=False,
    )
    if proc.returncode == 0:
        ref = (proc.stdout or "").strip()
        prefix = "refs/remotes/{0}/".format(remote)
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    for candidate in ("main", "master"):
        chk = run_git(
            ["rev-parse", "--verify", "--quiet", "{0}/{1}".format(remote, candidate)],
            cwd=path,
            check=False,
        )
        if chk.returncode == 0 and (chk.stdout or "").strip():
            return candidate
    raise GitError("no default branch on remote {0} in {1}".format(remote, path))


def rev_parse(path: Path, rev: str) -> str:
    proc = run_git(["rev-parse", rev], cwd=path)
    return (proc.stdout or "").strip()


def current_branch(path: Path) -> Optional[str]:
    proc = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path, check=False)
    if proc.returncode != 0:
        return None
    name = (proc.stdout or "").strip()
    if not name or name == "HEAD":
        return None
    return name


def upstream_ref(path: Path) -> Optional[str]:
    proc = run_git(["rev-parse", "--abbrev-ref", "@{upstream}"], cwd=path, check=False)
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def is_ancestor(path: Path, older: str, newer: str) -> bool:
    proc = run_git(["merge-base", "--is-ancestor", older, newer], cwd=path, check=False)
    return proc.returncode == 0


def ahead_behind(path: Path, local_sha: str, remote_sha: str) -> Tuple[bool, bool]:
    """Return (local_ahead, remote_ahead)."""
    if local_sha == remote_sha:
        return False, False
    local_ahead = is_ancestor(path, remote_sha, local_sha)
    remote_ahead = is_ancestor(path, local_sha, remote_sha)
    return local_ahead, remote_ahead


def pull_ff_only(path: Path) -> None:
    run_git(["pull", "--ff-only"], cwd=path)


def _sha_matches(existing: str, sha: str) -> bool:
    if not existing or not sha:
        return False
    return existing == sha or existing.startswith(sha) or sha.startswith(existing)


def _discard_audit_worktree(repo: Path, dest: Path) -> None:
    """Remove an audit scratch worktree. Never touches the operator checkout."""
    parent = worktree_parent().resolve()
    try:
        resolved = dest.resolve()
    except OSError:
        resolved = dest
    if resolved != parent and parent not in resolved.parents:
        raise GitError("refuse to remove {0}: outside the audit worktree dir".format(dest))
    run_git(["worktree", "remove", "--force", str(dest)], cwd=repo, check=False)
    if dest.is_dir():
        shutil.rmtree(dest)
    elif dest.exists():
        dest.unlink()
    run_git(["worktree", "prune"], cwd=repo, check=False)


def ensure_detached_worktree(repo: Path, sha: str, repo_id: str) -> Path:
    dest = worktree_parent() / "{0}-{1}".format(repo_id, sha[:12])
    if dest.is_dir() and is_git_repo(dest):
        existing = rev_parse(dest, "HEAD")
        if _sha_matches(existing, sha):
            return dest
        _discard_audit_worktree(repo, dest)
    elif dest.exists():
        _discard_audit_worktree(repo, dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_git(["worktree", "add", "--detach", str(dest), sha], cwd=repo)
    checked = rev_parse(dest, "HEAD")
    if not _sha_matches(checked, sha):
        raise GitError("worktree HEAD {0} is not {1}".format(checked, sha))
    return dest
