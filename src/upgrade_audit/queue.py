# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Persisted walk queue. A present file is the walk scope; missing means catalog default."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .catalog import Catalog
from .walks import WalksError
from .constants import SUGGEST_PRESETS
from .paths import repo_root
from .rundir import read_json, write_json

QUEUE_NAME = "queue.json"

SOURCE_ONLY = "only"
SOURCE_ALL = "all"
SOURCE_QUEUE = "queue"
SOURCE_CATALOG = "catalog"


class QueueError(ValueError):
    pass


def queue_path(root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / QUEUE_NAME


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_versions(from_version: str, to_version: str) -> Tuple[str, str]:
    frm = (from_version or "").strip()
    to = (to_version or "").strip()
    if not frm or not to:
        raise QueueError("from_version and to_version are required")
    return frm, to


def validate_ids(catalog: Catalog, ids: Sequence[str]) -> List[str]:
    """Unique in-scope ids, original order. Empty is valid."""
    known = set(catalog.in_scope_ids())
    out: List[str] = []
    seen = set()
    unknown: List[str] = []
    dups: List[str] = []
    for raw in ids:
        rid = str(raw).strip()
        if not rid:
            raise QueueError("queue id must be a non-empty string")
        if rid in seen:
            dups.append(rid)
            continue
        seen.add(rid)
        if rid not in known:
            unknown.append(rid)
        out.append(rid)
    if unknown or dups:
        parts = []
        if unknown:
            parts.append("unknown id(s): {0}".format(", ".join(unknown)))
        if dups:
            parts.append("duplicate id(s): {0}".format(", ".join(dups)))
        raise QueueError("; ".join(parts))
    return out


def load_queue(path: Path) -> Optional[dict]:
    """Return the object if the file exists. None if missing. Invalid file: QueueError."""
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except ValueError as exc:
        raise QueueError("queue.json is not JSON: {0}".format(exc)) from exc
    if not isinstance(data, dict):
        raise QueueError("queue.json must be an object")
    ids = data.get("ids")
    if not isinstance(ids, list) or any(not isinstance(x, str) or not x.strip() for x in ids):
        raise QueueError("queue.json ids must be a list of non-empty strings")
    frm = data.get("from_version")
    to = data.get("to_version")
    if not isinstance(frm, str) or not frm.strip() or not isinstance(to, str) or not to.strip():
        raise QueueError("queue.json needs from_version and to_version")
    reason = data.get("reason") or ""
    if not isinstance(reason, str):
        raise QueueError("queue.json reason must be a string")
    return {
        "from_version": frm.strip(),
        "to_version": to.strip(),
        "ids": [x.strip() for x in ids],
        "reason": reason,
        "updated_at": str(data.get("updated_at") or ""),
    }


def save_queue(
    path: Path,
    ids: Sequence[str],
    *,
    from_version: str,
    to_version: str,
    reason: str = "",
    catalog: Catalog,
) -> dict:
    frm, to = _validate_versions(from_version, to_version)
    clean = validate_ids(catalog, ids)
    try:
        catalog.walk_of_ids(clean)
    except WalksError as exc:
        raise QueueError(str(exc)) from exc
    payload = {
        "from_version": frm,
        "to_version": to,
        "ids": clean,
        "reason": reason or "",
        "updated_at": _iso_now(),
    }
    write_json(path, payload)
    return payload


def clear_queue(path: Path) -> None:
    if path.is_file():
        path.unlink()


def public_payload(path: Path) -> dict:
    data = load_queue(path)
    if data is None:
        return {
            "present": False,
            "from_version": None,
            "to_version": None,
            "ids": None,
            "reason": None,
            "updated_at": None,
        }
    out = dict(data)
    out["present"] = True
    return out


def _ids_for_walk(catalog: Catalog, walk: Optional[str]) -> List[str]:
    try:
        return catalog.ids_for_walk(walk)
    except WalksError as exc:
        raise QueueError(str(exc)) from exc


def require_walk(catalog: Catalog, ids: Sequence[str], walk: Optional[str]) -> List[str]:
    clean = list(ids)
    walk_id = (walk or "").strip() or None
    if walk_id and catalog.walks is None:
        raise QueueError("this catalog has no walks.yaml; omit --walk")
    if walk_id and catalog.walks is not None and walk_id not in catalog.walks.by_id:
        raise QueueError(
            "unknown --walk {0} (have {1})".format(walk_id, ", ".join(catalog.walks.order))
        )
    try:
        found = catalog.walk_of_ids(clean)
    except WalksError as exc:
        raise QueueError(str(exc)) from exc
    if walk_id and clean and found != walk_id:
        raise QueueError(
            "ids are walk {0}, not --walk {1}. Split into separate /upgrade-audit runs.".format(
                found or "(none)", walk_id
            )
        )
    return clean


def resolve_requested(
    catalog: Catalog,
    *,
    only: Optional[Sequence[str]] = None,
    walk_all: bool = False,
    walk: Optional[str] = None,
    root: Optional[Path] = None,
) -> Tuple[List[str], str]:
    """Walk ids and how they were chosen.

    --only (non-empty) wins. --all ignores the file. A present queue file,
    including empty ids, is the scope. A missing file is the catalog default
    (the default walk when catalog/walks.yaml exists).
    """
    walk_id = (walk or "").strip() or None
    if walk_id and catalog.walks is None:
        raise QueueError("this catalog has no walks.yaml; omit --walk")
    if walk_id and catalog.walks is not None and walk_id not in catalog.walks.by_id:
        raise QueueError(
            "unknown --walk {0} (have {1})".format(walk_id, ", ".join(catalog.walks.order))
        )
    only_ids = [str(x) for x in (only or []) if str(x).strip()]
    if only_ids and walk_all:
        raise QueueError("pass --only or --all, not both")
    if only_ids:
        return require_walk(catalog, validate_ids(catalog, only_ids), walk_id), SOURCE_ONLY
    if walk_all:
        return _ids_for_walk(catalog, walk_id), SOURCE_ALL
    queued = load_queue(queue_path(root))
    if queued is not None:
        return require_walk(catalog, validate_ids(catalog, queued["ids"]), walk_id), SOURCE_QUEUE
    return _ids_for_walk(catalog, walk_id), SOURCE_CATALOG
