# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Classify gh repo list against the catalog. Fail closed on new products."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Sequence, Tuple

from .catalog import Catalog, ExcludedRepo, draft_in_scope, with_added
from .walks import match_walk
from .github import RemoteRepo


@dataclass
class InventoryResult:
    in_scope: List[str] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)
    uncategorized_forks: List[str] = field(default_factory=list)
    uncategorized_non_forks: List[str] = field(default_factory=list)
    missing_from_github: List[str] = field(default_factory=list)

    @property
    def halt(self) -> bool:
        return bool(self.uncategorized_non_forks or self.missing_from_github)


def classify(catalog: Catalog, remotes: Sequence[RemoteRepo]) -> InventoryResult:
    result = InventoryResult()
    remote_names = {r.name: r for r in remotes}
    for item in catalog.in_scope:
        if item.name in remote_names:
            result.in_scope.append(item.id)
        else:
            result.missing_from_github.append(item.github)
    for item in catalog.excluded:
        if item.name in remote_names:
            result.excluded.append(item.github)
    known = catalog.github_names()
    for remote in remotes:
        if remote.name in known:
            continue
        if remote.is_fork:
            result.uncategorized_forks.append(remote.name)
        else:
            result.uncategorized_non_forks.append(remote.name)
    return result


def result_to_dict(result: InventoryResult) -> dict:
    return {
        "in_scope": list(result.in_scope),
        "excluded": list(result.excluded),
        "uncategorized_forks": list(result.uncategorized_forks),
        "uncategorized_non_forks": list(result.uncategorized_non_forks),
        "missing_from_github": list(result.missing_from_github),
        "halt": result.halt,
    }


def adopt_new(
    catalog: Catalog,
    remotes: Sequence[RemoteRepo],
    *,
    today: Optional[str] = None,
) -> Tuple[Catalog, List[str], List[str]]:
    """Add new owned non-forks as in-scope. Auto-exclude new forks.

    Does not drop in-scope rows that disappeared from GitHub.
    """
    result = classify(catalog, remotes)
    day = today or date.today().isoformat()
    added_ids: List[str] = []
    excluded_forks: List[str] = []
    new_scope = []
    clone_root = catalog.in_scope[0].clone_root if catalog.in_scope else ""
    for name in result.uncategorized_non_forks:
        item = draft_in_scope(
            catalog.owner,
            name,
            clone_root=clone_root,
            notes="adopted {0} from gh; exclude with a reason if this is not a product".format(day),
            walk=match_walk(name, catalog.walks),
        )
        new_scope.append(item)
        added_ids.append(item.id)
    new_ex = []
    for name in result.uncategorized_forks:
        new_ex.append(
            ExcludedRepo(
                github="{0}/{1}".format(catalog.owner, name),
                reason="fork (auto-adopt {0})".format(day),
            )
        )
        excluded_forks.append(name)
    if not new_scope and not new_ex:
        return catalog, [], []
    updated = with_added(catalog, in_scope=new_scope, excluded=new_ex)
    return updated, added_ids, excluded_forks
