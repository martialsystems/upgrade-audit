# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Repo-root and run-directory layout. Device-portable: no hardcoded home."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

ROOT_MARKER = "upgrade-audit.root"
POLICY_NAME = "upgrade-audit.policy.json"


def grok_home() -> Path:
    env = os.environ.get("GROK_HOME")
    if env:
        return Path(os.path.expanduser(env)).resolve()
    return (Path.home() / ".grok").resolve()


def package_checkout() -> Path:
    """Directory that contains catalog/ when this file lives in a git checkout."""
    return Path(__file__).resolve().parents[2]


def root_marker_path() -> Path:
    return grok_home() / ROOT_MARKER


def policy_file_path() -> Path:
    return grok_home() / POLICY_NAME


def repo_root() -> Path:
    env = os.environ.get("UPGRADE_AUDIT_ROOT")
    if env:
        return Path(os.path.expanduser(env)).resolve()
    marker = root_marker_path()
    if marker.is_file():
        line = marker.read_text(encoding="utf-8").strip().splitlines()
        if line and line[0].strip():
            return Path(os.path.expanduser(line[0].strip())).resolve()
    return package_checkout()


def catalog_path(root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "catalog" / "repos.yaml"


def schema_dir(root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "schema"


def protocol_path(root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "protocol" / "AUDIT.md"


def runs_dir(root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "runs"


def skill_source(root: Optional[Path] = None) -> Path:
    """SKILL.md in an operator checkout, a public plugin tree, or a Release unpack."""
    base = root or repo_root()
    candidates = (
        base / ".grok" / "skills" / "upgrade-audit" / "SKILL.md",
        base / "skills" / "upgrade-audit" / "SKILL.md",
        base / "landing" / "skills" / "upgrade-audit" / "SKILL.md",
        base / "plugins" / "upgrade-audit" / "skills" / "upgrade-audit" / "SKILL.md",
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def skill_dest() -> Path:
    return grok_home() / "skills" / "upgrade-audit" / "SKILL.md"


def default_clone_root() -> Path:
    env = os.environ.get("UPGRADE_AUDIT_CLONE_ROOT")
    if env:
        return Path(os.path.expanduser(env)).resolve()
    return Path.home()


def expand_local(path: str, clone_root: Optional[Path] = None) -> Path:
    """Resolve a catalog local path.

    `~/name` is remapped through clone_root (default: the user home).
    Absolute paths stay absolute. Other relatives join clone_root.
    """
    raw = (path or "").strip()
    if not raw:
        raise ValueError("empty local path")
    root = clone_root if clone_root is not None else default_clone_root()
    if raw == "~":
        return root.resolve()
    if raw.startswith("~/") or raw.startswith("~\\"):
        return (root / raw[2:]).expanduser().resolve()
    expanded = Path(os.path.expandvars(os.path.expanduser(raw)))
    if expanded.is_absolute():
        return expanded.resolve()
    return (root / expanded).resolve()


def _user_tag() -> str:
    if hasattr(os, "getuid"):
        try:
            return str(os.getuid())
        except OSError:
            pass
    return os.environ.get("USERNAME") or os.environ.get("USER") or "user"


def isolated_tmp() -> Path:
    """Per-user scratch. Honors TMPDIR/TEMP. Never a shared world-writable /tmp."""
    tmp = os.environ.get("TMPDIR") or os.environ.get("TEMP") or tempfile.gettempdir()
    base = Path(tmp) / "grok-{0}".format(_user_tag())
    base.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base, 0o700)
    except OSError:
        pass
    return base


def worktree_parent() -> Path:
    d = isolated_tmp() / "upgrade-audit"
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d
