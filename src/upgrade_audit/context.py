# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Collect a compact map of a shipped tree for the auditor."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from . import gitops

ENTRY_CANDIDATES = (
    "AGENTS.md",
    "README.md",
    "README",
    "CHECKLIST.md",
    "METHODOLOGY.md",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "manifest.json",
    "engine_pin.json",
    "product_laws.py",
    "src/main.py",
    "scripts/verify.sh",
)

LAW_NAMES = ("engine_pin.json", "product_laws.py", "AGENTS.md")


def _tracked_files(root: Path) -> List[str]:
    proc = gitops.run_git(["ls-files", "-z"], cwd=root)
    raw = proc.stdout or ""
    return [p for p in raw.split("\0") if p]


def collect_context(repo_id: str, github: str, read_path: Path, audited_sha: str) -> Dict:
    root = Path(read_path)
    tracked = _tracked_files(root)
    by_ext: Dict[str, int] = {}
    for rel in tracked:
        suffix = Path(rel).suffix.lower() or "<none>"
        by_ext[suffix] = by_ext.get(suffix, 0) + 1
    tests = [
        rel
        for rel in tracked
        if "/test" in ("/" + rel.replace("\\", "/")).lower()
        or Path(rel).name.startswith("test_")
        or Path(rel).name.endswith("_test.py")
        or Path(rel).name.endswith(".test.js")
    ]
    laws = [rel for rel in tracked if Path(rel).name in LAW_NAMES]
    present = [name for name in ENTRY_CANDIDATES if (root / name).is_file()]
    top = sorted({rel.split("/", 1)[0] for rel in tracked})
    return {
        "repo": repo_id,
        "github": github,
        "read_path": str(root),
        "audited_sha": audited_sha,
        "tracked_file_count": len(tracked),
        "by_ext": dict(sorted(by_ext.items(), key=lambda kv: (-kv[1], kv[0]))),
        "top_level": top[:80],
        "entry_points_present": present,
        "law_files": laws,
        "test_files": tests[:200],
        "test_file_count": len(tests),
    }
