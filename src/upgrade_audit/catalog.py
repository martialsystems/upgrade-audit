# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Load and query catalog/repos.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import yaml

from .paths import catalog_path, default_clone_root, expand_local, repo_root
from .walks import WalksConfig, WalksError, load_walks_beside


@dataclass(frozen=True)
class InScopeRepo:
    id: str
    github: str
    local: str
    notes: str = ""
    audit_remote: str = "origin"
    clone_root: str = ""
    walk: str = ""

    @property
    def owner(self) -> str:
        return self.github.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.github.split("/", 1)[1]

    @property
    def local_path(self) -> Path:
        root = Path(self.clone_root) if self.clone_root else default_clone_root()
        return expand_local(self.local, clone_root=root)


@dataclass(frozen=True)
class ExcludedRepo:
    github: str
    reason: str

    @property
    def name(self) -> str:
        return self.github.split("/", 1)[1]


@dataclass(frozen=True)
class Catalog:
    owner: str
    in_scope: List[InScopeRepo]
    excluded: List[ExcludedRepo]
    source: Path
    clone_root_raw: str = "~"
    walks: Optional[WalksConfig] = None

    def in_scope_by_id(self, repo_id: str) -> InScopeRepo:
        for item in self.in_scope:
            if item.id == repo_id:
                return item
        raise KeyError("unknown in-scope id: {0}".format(repo_id))

    def in_scope_ids(self) -> List[str]:
        return [item.id for item in self.in_scope]

    def named(self, github_name: str) -> Optional[str]:
        """Return 'in_scope' | 'excluded' | None for a GitHub repo name."""
        for item in self.in_scope:
            if item.name == github_name:
                return "in_scope"
        for item in self.excluded:
            if item.name == github_name:
                return "excluded"
        return None

    def github_names(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for item in self.in_scope:
            out[item.name] = "in_scope"
        for item in self.excluded:
            out[item.name] = "excluded"
        return out

    def effective_walk(self, item: InScopeRepo) -> str:
        if item.walk:
            return item.walk
        if self.walks is not None:
            return self.walks.default
        return ""

    def ids_for_walk(self, walk_id: Optional[str] = None) -> List[str]:
        """Ids in one walk. No walks.yaml: every in-scope id (ignore walk_id unless set)."""
        if self.walks is None:
            if walk_id:
                raise WalksError("this catalog has no walks.yaml; omit --walk")
            return self.in_scope_ids()
        name = (walk_id or self.walks.default).strip()
        if name not in self.walks.by_id:
            raise WalksError(
                "unknown walk {0!r} (have {1})".format(name, ", ".join(self.walks.order))
            )
        return [item.id for item in self.in_scope if self.effective_walk(item) == name]

    def walk_of_ids(self, ids: Sequence[str]) -> Optional[str]:
        """Single walk covering ids, or None if empty. Mixed ids: WalksError."""
        found: List[str] = []
        for rid in ids:
            name = self.effective_walk(self.in_scope_by_id(rid))
            if name and name not in found:
                found.append(name)
        if len(found) > 1:
            raise WalksError(
                "mixed walks in one run: {0}. Split into separate /upgrade-audit runs.".format(
                    ", ".join(found)
                )
            )
        return found[0] if found else None


def load_catalog(path: Optional[Path] = None) -> Catalog:
    src = path or catalog_path()
    raw = yaml.safe_load(src.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("catalog must be a mapping: {0}".format(src))
    owner = raw.get("owner") or ""
    clone_root_raw = raw.get("clone_root") or "~"
    clone_root = os.environ.get("UPGRADE_AUDIT_CLONE_ROOT") or clone_root_raw
    in_scope: List[InScopeRepo] = []
    seen_ids = set()
    seen_github = set()
    for row in raw.get("in_scope") or []:
        item = InScopeRepo(
            id=row["id"],
            github=row["github"],
            local=row["local"],
            notes=row.get("notes") or "",
            audit_remote=row.get("audit_remote") or "origin",
            clone_root=str(Path(os.path.expanduser(str(clone_root))).resolve()),
            walk=str(row.get("walk") or "").strip(),
        )
        if item.id in seen_ids:
            raise ValueError("duplicate in-scope id: {0}".format(item.id))
        if item.github in seen_github:
            raise ValueError("duplicate github: {0}".format(item.github))
        seen_ids.add(item.id)
        seen_github.add(item.github)
        in_scope.append(item)
    excluded: List[ExcludedRepo] = []
    for row in raw.get("excluded") or []:
        item = ExcludedRepo(github=row["github"], reason=row["reason"])
        if item.github in seen_github:
            raise ValueError("github listed twice: {0}".format(item.github))
        seen_github.add(item.github)
        excluded.append(item)
    try:
        walks = load_walks_beside(src)
    except WalksError as exc:
        raise ValueError(str(exc)) from exc
    if walks is not None:
        known_walks = set(walks.by_id)
        for item in in_scope:
            if item.walk and item.walk not in known_walks:
                raise ValueError(
                    "unknown walk {0!r} on {1} (have {2})".format(
                        item.walk, item.id, ", ".join(walks.order)
                    )
                )
    return Catalog(
        owner=owner,
        in_scope=in_scope,
        excluded=excluded,
        source=src,
        clone_root_raw=str(clone_root_raw),
        walks=walks,
    )


def default_catalog() -> Catalog:
    return load_catalog(catalog_path(repo_root()))


def select_repos(catalog: Catalog, only: Optional[Sequence[str]] = None) -> List[InScopeRepo]:
    if not only:
        return list(catalog.in_scope)
    wanted = list(only)
    unknown = [rid for rid in wanted if rid not in set(catalog.in_scope_ids())]
    if unknown:
        raise KeyError("unknown --only id(s): {0}".format(", ".join(unknown)))
    by_id = {item.id: item for item in catalog.in_scope}
    return [by_id[rid] for rid in wanted]


_CATALOG_HEADER = """\
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
# Fleet scope. `upgrade-audit inventory --adopt` appends new owned
# non-forks. Move a row to excluded (with a reason) if it is not a product.
# Optional walk: family from catalog/walks.yaml when that file exists.

"""


def _scope_row(item: InScopeRepo, default_walk: str = "") -> dict:
    row = {"id": item.id, "github": item.github, "local": item.local}
    if item.audit_remote and item.audit_remote != "origin":
        row["audit_remote"] = item.audit_remote
    if item.walk and item.walk != default_walk:
        row["walk"] = item.walk
    if item.notes:
        row["notes"] = item.notes
    return row


def write_catalog(catalog: Catalog, path: Optional[Path] = None) -> Path:
    dest = path or catalog.source
    default_walk = catalog.walks.default if catalog.walks is not None else ""
    payload = {
        "owner": catalog.owner,
        "clone_root": catalog.clone_root_raw or "~",
        "in_scope": [_scope_row(item, default_walk) for item in catalog.in_scope],
        "excluded": [{"github": item.github, "reason": item.reason} for item in catalog.excluded],
    }
    body = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False, allow_unicode=True)
    dest.write_text(_CATALOG_HEADER + body, encoding="utf-8")
    return dest


def draft_in_scope(
    owner: str,
    repo_name: str,
    *,
    clone_root: str = "",
    notes: str = "",
    walk: str = "",
) -> InScopeRepo:
    """Default catalog row for a newly seen owned repo."""
    audit_remote = "origin"
    folder = repo_name
    if repo_name.endswith("-src") and len(repo_name) > 4:
        audit_remote = "src"
        folder = repo_name[: -len("-src")]
    return InScopeRepo(
        id=repo_name,
        github="{0}/{1}".format(owner, repo_name),
        local="~/{0}".format(folder),
        notes=notes,
        audit_remote=audit_remote,
        clone_root=clone_root,
        walk=walk,
    )


def with_added(
    catalog: Catalog,
    *,
    in_scope: Optional[Sequence[InScopeRepo]] = None,
    excluded: Optional[Sequence[ExcludedRepo]] = None,
) -> Catalog:
    scope = list(catalog.in_scope)
    extra_ex = list(catalog.excluded)
    known = catalog.github_names()
    for item in in_scope or []:
        if item.name in known or item.id in {s.id for s in scope}:
            raise ValueError("already in catalog: {0}".format(item.github))
        scope.append(item)
        known[item.name] = "in_scope"
    for item in excluded or []:
        if item.name in known:
            raise ValueError("already in catalog: {0}".format(item.github))
        extra_ex.append(item)
        known[item.name] = "excluded"
    return Catalog(
        owner=catalog.owner,
        in_scope=scope,
        excluded=extra_ex,
        source=catalog.source,
        clone_root_raw=catalog.clone_root_raw,
        walks=catalog.walks,
    )
