# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""GitHub listing via `gh`. Injectable runner for tests."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Sequence

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class RemoteRepo:
    name: str
    is_fork: bool
    is_archived: bool
    url: str = ""


class GitHubError(RuntimeError):
    pass


def list_owned_repos(
    owner: str,
    runner: Runner = subprocess.run,
    limit: int = 200,
) -> List[RemoteRepo]:
    cmd = [
        "gh",
        "repo",
        "list",
        owner,
        "--limit",
        str(limit),
        "--json",
        "name,isFork,isArchived,url",
    ]
    try:
        proc = runner(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise GitHubError("gh is not runnable: {0}".format(exc)) from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise GitHubError("gh repo list failed: {0}".format(err or proc.returncode))
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise GitHubError("gh returned non-JSON") from exc
    if not isinstance(rows, list):
        raise GitHubError("gh JSON was not a list")
    out: List[RemoteRepo] = []
    for row in rows:
        out.append(
            RemoteRepo(
                name=row["name"],
                is_fork=bool(row.get("isFork")),
                is_archived=bool(row.get("isArchived")),
                url=row.get("url") or "",
            )
        )
    return out


def current_login(runner: Runner = subprocess.run) -> str:
    """GitHub login of the authenticated gh user."""
    try:
        proc = runner(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise GitHubError("gh is not runnable: {0}".format(exc)) from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise GitHubError("gh api user failed: {0}".format(err or proc.returncode))
    login = (proc.stdout or "").strip()
    if not login:
        raise GitHubError("gh api user returned an empty login")
    return login


def clone_repo(
    github: str,
    dest: str,
    runner: Runner = subprocess.run,
) -> None:
    cmd: Sequence[str] = ["gh", "repo", "clone", github, dest]
    try:
        proc = runner(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise GitHubError("gh is not runnable: {0}".format(exc)) from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise GitHubError("gh repo clone {0} failed: {1}".format(github, err))
