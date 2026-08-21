# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Run directory layout and manifest helpers."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import runs_dir

_SAFE_VER = re.compile(r"^[A-Za-z0-9._-]+$")


def run_name(day: str, from_ver: str, to_ver: str) -> str:
    return "{0}-{1}-to-{2}".format(day, from_ver, to_ver)


def parse_versions(from_ver: str, to_ver: str) -> None:
    for label, val in (("from", from_ver), ("to", to_ver)):
        if not val or not _SAFE_VER.match(val):
            raise ValueError("invalid {0} version: {1!r}".format(label, val))


def allocate_run_dir(
    from_ver: str,
    to_ver: str,
    day: Optional[str] = None,
    root: Optional[Path] = None,
    resume: bool = False,
) -> Path:
    parse_versions(from_ver, to_ver)
    day = day or date.today().isoformat()
    path = (root or runs_dir()) / run_name(day, from_ver, to_ver)
    if resume:
        if not path.is_dir():
            raise FileNotFoundError("nothing to resume: {0}".format(path))
        return path
    path.mkdir(parents=True, exist_ok=True)
    (path / "repos").mkdir(exist_ok=True)
    (path / "context").mkdir(exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(run: Path, payload: Dict[str, Any]) -> None:
    write_json(run / "manifest.json", payload)


def pdf_path(run: Path, from_ver: str, to_ver: str) -> Path:
    return run / "model-upgrade-audit-{0}-to-{1}.pdf".format(from_ver, to_ver)
