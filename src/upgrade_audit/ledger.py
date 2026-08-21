# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Compare confirmed findings across two runs (4.7 vs 4.6, etc.)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def fingerprint(finding: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(finding.get("repo") or ""),
        str(finding.get("file") or ""),
        str(finding.get("error_class") or ""),
        _norm(str(finding.get("claim") or "")),
    )


def _load_reports(run_dir: Path) -> List[dict]:
    repos = run_dir / "repos"
    if not repos.is_dir():
        return []
    out: List[dict] = []
    for path in sorted(repos.glob("*.json")):
        if path.name.endswith(".unverified.json"):
            continue
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def _confirmed(reports: Iterable[Mapping[str, Any]]) -> Dict[Tuple[str, str, str, str], dict]:
    table: Dict[Tuple[str, str, str, str], dict] = {}
    for report in reports:
        for finding in report.get("findings") or []:
            if finding.get("status") != "confirmed":
                continue
            table[fingerprint(finding)] = dict(finding)
    return table


def compare_runs(current_dir: Path, prior_dir: Path) -> dict:
    current = _confirmed(_load_reports(current_dir))
    prior = _confirmed(_load_reports(prior_dir))
    still_open = []
    gone = []
    new = []
    for key, finding in sorted(current.items()):
        if key in prior:
            still_open.append(finding)
        else:
            new.append(finding)
    for key, finding in sorted(prior.items()):
        if key not in current:
            gone.append(finding)
    return {
        "prior": str(prior_dir),
        "current": str(current_dir),
        "still_open": still_open,
        "gone": gone,
        "new": new,
        "counts": {
            "still_open": len(still_open),
            "gone": len(gone),
            "new": len(new),
        },
    }


def latest_completed_run(runs_root: Path, exclude: Optional[Path] = None) -> Path:
    """Most recent sibling of runs/* that has a complete manifest."""
    candidates = []
    if not runs_root.is_dir():
        raise FileNotFoundError("no runs directory: {0}".format(runs_root))
    skip = exclude.resolve() if exclude is not None else None
    for path in runs_root.iterdir():
        if not path.is_dir():
            continue
        if path.name.startswith("_"):
            continue
        if skip is not None and path.resolve() == skip:
            continue
        manifest = path / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("status") == "complete":
            candidates.append(path)
    if not candidates:
        raise FileNotFoundError("no completed run under {0}".format(runs_root))
    return sorted(candidates, key=lambda p: p.name)[-1]
