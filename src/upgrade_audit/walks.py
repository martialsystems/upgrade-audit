# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Named catalog walks. Optional walks.yaml splits /upgrade-audit runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Optional, Tuple

import yaml

DEFAULT_WALK = "products"


class WalksError(ValueError):
    pass


@dataclass(frozen=True)
class WalkSpec:
    id: str
    title: str
    index: str = ""
    prefixes: Tuple[str, ...] = ()
    names: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class WalksConfig:
    default: str
    order: Tuple[str, ...]
    by_id: Dict[str, WalkSpec]
    source: Path


def walks_path(catalog_file: Path) -> Path:
    return catalog_file.parent / "walks.yaml"


def load_walks(path: Path) -> WalksConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise WalksError("walks.yaml must be a mapping: {0}".format(path))
    default = str(raw.get("default") or DEFAULT_WALK).strip()
    walks_raw = raw.get("walks")
    if not isinstance(walks_raw, dict) or not walks_raw:
        raise WalksError("walks.yaml needs a non-empty walks map: {0}".format(path))
    by_id: Dict[str, WalkSpec] = {}
    order = []
    for walk_id, body in walks_raw.items():
        name = str(walk_id).strip()
        if not name:
            raise WalksError("walk id must be a non-empty string")
        if not isinstance(body, dict):
            raise WalksError("walk {0} must be a mapping".format(name))
        match = body.get("match") or {}
        if match in ("", None):
            match = {}
        if not isinstance(match, dict):
            raise WalksError("walk {0} match must be a mapping".format(name))
        prefixes = tuple(str(x) for x in (match.get("prefixes") or []) if str(x).strip())
        names = frozenset(str(x) for x in (match.get("names") or []) if str(x).strip())
        by_id[name] = WalkSpec(
            id=name,
            title=str(body.get("title") or name).strip(),
            index=str(body.get("index") or "").strip(),
            prefixes=prefixes,
            names=names,
        )
        order.append(name)
    if default not in by_id:
        raise WalksError("walks.yaml default {0!r} is not a walk id".format(default))
    return WalksConfig(
        default=default,
        order=tuple(order),
        by_id=by_id,
        source=path,
    )


def load_walks_beside(catalog_file: Path) -> Optional[WalksConfig]:
    path = walks_path(catalog_file)
    if not path.is_file():
        return None
    return load_walks(path)


def match_walk(repo_name: str, walks: Optional[WalksConfig]) -> str:
    """Assign a GitHub repo name to a walk. Missing config: empty (one pool)."""
    if walks is None:
        return ""
    name = (repo_name or "").strip()
    for walk_id in walks.order:
        if walk_id == walks.default:
            continue
        spec = walks.by_id[walk_id]
        if name in spec.names:
            return walk_id
        for prefix in spec.prefixes:
            if name.startswith(prefix):
                return walk_id
    return walks.default
