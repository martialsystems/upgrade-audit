# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Non-blocking fleet walk: snapshot join, per-repo pipeline, optional stall kill.

The parent never wait-alls. walk-step reads a snapshot and returns the next
collect / spawn / validate / kill / join actions. Kill policy is per-device
(none or stall). There is no wall-clock cap.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .policy import STALL_SECONDS_DEFAULT, parse_kill
from .rundir import read_json, write_json

WALK_NAME = "walk.json"
MAX_AUDITORS = 4
MAX_VERIFIERS = 4
ROLES = ("auditor", "verifier", "fix")
SKIP_REASONS = ("sync_fail", "stall", "cancelled")
AGENT_STATUSES = ("running", "completed", "failed", "cancelled")


def _parse_ts(raw: Optional[str]) -> datetime:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        return ts.isoformat(timespec="seconds")
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_utc_naive(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts
    return ts.astimezone(timezone.utc).replace(tzinfo=None)


def empty_walk(
    requested: Sequence[str],
    *,
    kill: str = "none",
    stall_seconds: int = STALL_SECONDS_DEFAULT,
    max_auditors: int = MAX_AUDITORS,
    max_verifiers: int = MAX_VERIFIERS,
) -> Dict[str, Any]:
    ids = [str(x) for x in requested]
    if len(ids) != len(set(ids)):
        raise ValueError("requested repo ids must be unique")
    return {
        "requested": list(ids),
        "queue": list(ids),
        "in_flight": [],
        "done": [],
        "skipped": [],
        "pending_verify": [],
        "respawned": [],
        "max_auditors": int(max_auditors),
        "max_verifiers": int(max_verifiers),
        "kill": parse_kill(kill),
        "stall_seconds": int(stall_seconds),
    }


def walk_path(run_dir: Path) -> Path:
    return Path(run_dir) / WALK_NAME


def load_walk(run_dir: Path) -> Dict[str, Any]:
    path = walk_path(run_dir)
    if not path.is_file():
        raise FileNotFoundError("no walk.json under {0}".format(run_dir))
    state = read_json(path)
    if not isinstance(state, dict):
        raise ValueError("walk.json must be an object")
    return state


def save_walk(run_dir: Path, state: Mapping[str, Any]) -> Path:
    dest = walk_path(run_dir)
    write_json(dest, state)
    return dest


def reconcile_with_reports(state: Dict[str, Any], run_dir: Path) -> Dict[str, Any]:
    """Treat existing validated reports as done. Do not re-queue them."""
    repos_dir = Path(run_dir) / "repos"
    present = set()
    if repos_dir.is_dir():
        for path in repos_dir.glob("*.json"):
            if path.name.endswith(".unverified.json"):
                continue
            present.add(path.stem)
    done = list(state.get("done") or [])
    for repo in present:
        if repo not in done:
            done.append(repo)
    state["done"] = done
    skipped_repos = {row.get("repo") for row in (state.get("skipped") or []) if isinstance(row, dict)}
    accounted = set(done) | skipped_repos
    state["queue"] = [r for r in (state.get("queue") or []) if r not in accounted]
    state["in_flight"] = [
        row
        for row in (state.get("in_flight") or [])
        if isinstance(row, dict) and row.get("repo") not in accounted
    ]
    state["pending_verify"] = [
        r for r in (state.get("pending_verify") or []) if r not in accounted
    ]
    return state


def seed_walk(
    run_dir: Path,
    requested: Sequence[str],
    *,
    kill: str = "none",
    stall_seconds: int = STALL_SECONDS_DEFAULT,
    resume: bool = False,
) -> Dict[str, Any]:
    dest = walk_path(run_dir)
    if resume and dest.is_file():
        state = load_walk(run_dir)
    else:
        state = empty_walk(requested, kill=kill, stall_seconds=stall_seconds)
    reconcile_with_reports(state, run_dir)
    save_walk(run_dir, state)
    return state


def _count_role(state: Mapping[str, Any], role: str) -> int:
    return sum(1 for row in (state.get("in_flight") or []) if row.get("role") == role)


def _find_flight(state: Mapping[str, Any], agent_id: str) -> Optional[Dict[str, Any]]:
    for row in state.get("in_flight") or []:
        if row.get("agent_id") == agent_id:
            return row
    return None


def _find_reserved(state: Mapping[str, Any], repo: str, role: str) -> Optional[Dict[str, Any]]:
    for row in state.get("in_flight") or []:
        if row.get("repo") == repo and row.get("role") == role and not row.get("agent_id"):
            return row
    return None


def _accounted(state: Mapping[str, Any]) -> set:
    skipped = {row.get("repo") for row in (state.get("skipped") or []) if isinstance(row, dict)}
    return set(state.get("done") or []) | skipped


def _progress_token(entry: Mapping[str, Any]) -> str:
    return "{0}|{1}|{2}".format(
        entry.get("status") or "",
        entry.get("progress") if entry.get("progress") is not None else "",
        (entry.get("output") or "")[:120],
    )


def _skip(state: Dict[str, Any], repo: str, reason: str, agent_id: Optional[str] = None) -> None:
    if reason not in SKIP_REASONS:
        raise ValueError("unknown skip reason: {0!r}".format(reason))
    if repo in _accounted(state):
        return
    state.setdefault("skipped", []).append(
        {"repo": repo, "reason": reason, "agent_id": agent_id}
    )
    state["queue"] = [r for r in (state.get("queue") or []) if r != repo]
    state["pending_verify"] = [r for r in (state.get("pending_verify") or []) if r != repo]
    state["in_flight"] = [row for row in (state.get("in_flight") or []) if row.get("repo") != repo]


def _remove_flight(state: Dict[str, Any], agent_id: Optional[str], repo: Optional[str] = None, role: Optional[str] = None) -> None:
    kept = []
    for row in state.get("in_flight") or []:
        if agent_id and row.get("agent_id") == agent_id:
            continue
        if repo and role and row.get("repo") == repo and row.get("role") == role and not row.get("agent_id"):
            continue
        kept.append(row)
    state["in_flight"] = kept


def apply_spawned(state: Dict[str, Any], spawned: Iterable[Mapping[str, Any]], now: datetime) -> None:
    """Parent acknowledges a spawn: bind agent_id onto the reserved slot."""
    stamp = _iso(now)
    for item in spawned:
        repo = item.get("repo")
        role = item.get("role")
        agent_id = item.get("id") or item.get("agent_id")
        if not repo or role not in ROLES or not agent_id:
            raise ValueError("spawned entry needs repo, role, and id")
        reserved = _find_reserved(state, str(repo), str(role))
        if reserved is not None:
            reserved["agent_id"] = str(agent_id)
            reserved["last_progress_at"] = stamp
            reserved["progress_token"] = "running|"
            continue
        state.setdefault("in_flight", []).append(
            {
                "repo": str(repo),
                "role": str(role),
                "agent_id": str(agent_id),
                "started_at": stamp,
                "last_progress_at": stamp,
                "progress_token": "running|",
            }
        )


def apply_skips(state: Dict[str, Any], skips: Iterable[Mapping[str, Any]]) -> None:
    for item in skips:
        repo = item.get("repo")
        reason = item.get("reason") or "sync_fail"
        if not repo:
            raise ValueError("skip entry needs repo")
        _skip(state, str(repo), str(reason), item.get("agent_id"))


def _reserve(state: Dict[str, Any], repo: str, role: str, now: datetime) -> Dict[str, str]:
    stamp = _iso(now)
    state.setdefault("in_flight", []).append(
        {
            "repo": repo,
            "role": role,
            "agent_id": None,
            "started_at": stamp,
            "last_progress_at": stamp,
            "progress_token": "",
        }
    )
    return {"repo": repo, "role": role}


def step(
    state: Dict[str, Any],
    snapshot: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
    kill_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Advance walk state from a non-blocking snapshot. Returns actions for the parent."""
    now_ts = now or _parse_ts(str(snapshot.get("now") or ""))
    kill = parse_kill(kill_override or state.get("kill") or "none")
    state["kill"] = kill
    if snapshot.get("stall_seconds") is not None:
        state["stall_seconds"] = int(snapshot["stall_seconds"])
    stall_seconds = int(state.get("stall_seconds") or STALL_SECONDS_DEFAULT)

    apply_spawned(state, snapshot.get("spawned") or [], now_ts)
    apply_skips(state, snapshot.get("skip") or [])

    actions: Dict[str, Any] = {
        "collect": [],
        "spawn": [],
        "validate": [],
        "kill": [],
        "unverify": [],
        "join": {"ids": [], "timeout_ms": 0},
        "walk_complete": False,
        "need_kill_policy": False,
    }

    by_id: Dict[str, Mapping[str, Any]] = {}
    for entry in snapshot.get("agents") or []:
        agent_id = entry.get("id") or entry.get("agent_id")
        if not agent_id:
            continue
        by_id[str(agent_id)] = entry

    unverify: List[Dict[str, str]] = []
    validate: List[str] = []
    kills: List[Dict[str, Any]] = []

    for row in list(state.get("in_flight") or []):
        agent_id = row.get("agent_id")
        if not agent_id:
            continue
        entry = by_id.get(str(agent_id))
        if entry is None:
            continue
        status = (entry.get("status") or "running").lower()
        token = _progress_token(entry)
        if token != (row.get("progress_token") or ""):
            row["progress_token"] = token
            row["last_progress_at"] = _iso(now_ts)
        repo = str(row.get("repo"))
        role = str(row.get("role"))

        if status == "completed":
            _remove_flight(state, str(agent_id))
            if role == "auditor":
                if repo not in (state.get("pending_verify") or []) and repo not in _accounted(state):
                    state.setdefault("pending_verify", []).append(repo)
            elif role in ("verifier", "fix"):
                if repo not in (state.get("done") or []):
                    state.setdefault("done", []).append(repo)
                validate.append("repos/{0}.json".format(repo))
            continue

        if status in ("failed", "cancelled"):
            _remove_flight(state, str(agent_id))
            already = repo in (state.get("respawned") or [])
            if already:
                if role == "verifier":
                    unverify.append({"repo": repo, "reason": "cancelled"})
                    if repo not in (state.get("done") or []):
                        state.setdefault("done", []).append(repo)
                    validate.append("repos/{0}.json".format(repo))
                else:
                    _skip(state, repo, "cancelled", str(agent_id))
            else:
                state.setdefault("respawned", []).append(repo)
                # Put back for a single respawn of the same role.
                if role == "auditor":
                    if repo not in (state.get("queue") or []) and repo not in _accounted(state):
                        state.setdefault("queue", []).insert(0, repo)
                elif role == "verifier":
                    if repo not in (state.get("pending_verify") or []) and repo not in _accounted(state):
                        state.setdefault("pending_verify", []).insert(0, repo)
            continue

        if status == "running" and kill == "stall":
            last = _parse_ts(str(row.get("last_progress_at") or row.get("started_at")))
            quiet = (_as_utc_naive(now_ts) - _as_utc_naive(last)).total_seconds()
            if quiet >= stall_seconds:
                kills.append(
                    {
                        "id": str(agent_id),
                        "repo": repo,
                        "role": role,
                        "reason": "stall",
                    }
                )
                _remove_flight(state, str(agent_id))
                if role == "verifier":
                    unverify.append({"repo": repo, "reason": "stall"})
                    if repo not in (state.get("done") or []):
                        state.setdefault("done", []).append(repo)
                    validate.append("repos/{0}.json".format(repo))
                else:
                    _skip(state, repo, "stall", str(agent_id))

    spawn: List[Dict[str, str]] = []
    while _count_role(state, "verifier") < int(state.get("max_verifiers") or MAX_VERIFIERS):
        pending = list(state.get("pending_verify") or [])
        if not pending:
            break
        repo = pending.pop(0)
        state["pending_verify"] = pending
        if repo in _accounted(state):
            continue
        spawn.append(_reserve(state, repo, "verifier", now_ts))

    while _count_role(state, "auditor") < int(state.get("max_auditors") or MAX_AUDITORS):
        queue = list(state.get("queue") or [])
        if not queue:
            break
        repo = queue.pop(0)
        state["queue"] = queue
        if repo in _accounted(state):
            continue
        if any(row.get("repo") == repo and row.get("role") == "auditor" for row in state.get("in_flight") or []):
            continue
        spawn.append(_reserve(state, repo, "auditor", now_ts))

    live_ids = [str(row["agent_id"]) for row in (state.get("in_flight") or []) if row.get("agent_id")]
    accounted = _accounted(state)
    requested = list(state.get("requested") or [])
    walk_complete = bool(requested) and all(r in accounted for r in requested)
    if not requested:
        walk_complete = not (state.get("queue") or state.get("in_flight") or state.get("pending_verify"))

    collect: List[str] = []
    for row in state.get("in_flight") or []:
        if row.get("role") == "auditor" and row.get("repo") not in collect:
            collect.append(str(row["repo"]))
    for repo in state.get("queue") or []:
        if repo not in collect:
            collect.append(str(repo))
        if len(collect) >= int(state.get("max_auditors") or MAX_AUDITORS):
            break

    actions.update(
        {
            "collect": collect,
            "spawn": spawn,
            "validate": validate,
            "kill": kills,
            "unverify": unverify,
            "join": {"ids": live_ids, "timeout_ms": 0},
            "walk_complete": walk_complete,
        }
    )
    if any(len(item.get("repo", "").split()) > 1 for item in spawn):
        raise ValueError("spawn must be one repo per agent")
    return actions
