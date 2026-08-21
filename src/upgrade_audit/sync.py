# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Fetch catalog repos. Never discard dirty trees. Audit shipped SHA."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from .catalog import InScopeRepo
from . import gitops
from .github import clone_repo


@dataclass
class SyncResult:
    repo_id: str
    github: str
    local_path: str
    cloned: bool = False
    dirty: bool = False
    dirty_paths: List[str] = field(default_factory=list)
    pulled: bool = False
    audit_remote: str = "origin"
    default_branch: str = ""
    audited_ref: str = ""
    audited_sha: str = ""
    read_path: str = ""
    used_worktree: bool = False
    note: str = ""
    ok: bool = True
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


CloneFn = Callable[[str, str], None]


def sync_one(
    item: InScopeRepo,
    clone: CloneFn = clone_repo,
) -> SyncResult:
    result = SyncResult(
        repo_id=item.id,
        github=item.github,
        local_path=str(item.local_path),
        audit_remote=item.audit_remote,
    )
    try:
        path = item.local_path
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            clone(item.github, str(path))
            result.cloned = True
            result.note = "cloned {0}".format(item.github)
        if not gitops.is_git_repo(path):
            raise gitops.GitError("not a git repo: {0}".format(path))

        gitops.fetch_remote(path, "origin")
        if item.audit_remote != "origin":
            gitops.ensure_remote(
                path, item.audit_remote, "https://github.com/{0}.git".format(item.github)
            )
            gitops.fetch_remote(path, item.audit_remote)

        branch = gitops.remote_default_branch(path, item.audit_remote)
        audited_ref = "{0}/{1}".format(item.audit_remote, branch)
        audited_sha = gitops.rev_parse(path, audited_ref)
        result.default_branch = branch
        result.audited_ref = audited_ref
        result.audited_sha = audited_sha

        dirt = gitops.dirty_paths(path)
        result.dirty = bool(dirt)
        result.dirty_paths = dirt

        head = gitops.rev_parse(path, "HEAD")
        _local_ahead, remote_ahead = gitops.ahead_behind(path, head, audited_sha)
        current = gitops.current_branch(path)
        upstream = gitops.upstream_ref(path)

        can_ff_pull = (
            item.audit_remote == "origin"
            and not result.dirty
            and remote_ahead
            and current == branch
            and upstream == audited_ref
        )
        if can_ff_pull:
            gitops.pull_ff_only(path)
            result.pulled = True
            head = gitops.rev_parse(path, "HEAD")
            result.note = (result.note + "; " if result.note else "") + "ff-only pull"
            remote_ahead = False

        if result.dirty:
            result.note = (result.note + "; " if result.note else "") + (
                "local finish-later, not in this audit"
            )

        if head == audited_sha and not result.dirty:
            result.read_path = str(path)
            result.used_worktree = False
        else:
            wt = gitops.ensure_detached_worktree(path, audited_sha, item.id)
            result.read_path = str(wt)
            result.used_worktree = True
            if remote_ahead and result.dirty:
                result.note = (result.note + "; " if result.note else "") + (
                    "origin ahead and dirty; audited detached worktree"
                )
            elif head != audited_sha:
                result.note = (result.note + "; " if result.note else "") + (
                    "HEAD is not {0}; audited detached worktree".format(audited_ref)
                )
        result.ok = True
        return result
    except Exception as exc:  # noqa: BLE001  surface any sync failure; do not discard
        result.ok = False
        result.error = str(exc)
        if not result.note:
            result.note = "sync failed"
        return result


def sync_all(
    items: Sequence[InScopeRepo],
    clone: CloneFn = clone_repo,
) -> List[SyncResult]:
    return [sync_one(item, clone=clone) for item in items]


def results_to_dict(results: Sequence[SyncResult]) -> dict:
    return {"repos": [r.to_dict() for r in results]}


def read_path_for(results: Sequence[SyncResult], repo_id: str) -> Optional[Path]:
    for row in results:
        if row.repo_id == repo_id and row.ok and row.read_path:
            return Path(row.read_path)
    return None
