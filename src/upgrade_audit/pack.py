# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Install the pack on this device and check that it can run."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

from . import __version__
from .catalog import default_catalog
from .policy import KILL_HELP, MODE_HELP, load_policy
from .paths import (
    catalog_path,
    grok_home,
    package_checkout,
    protocol_path,
    repo_root,
    root_marker_path,
    skill_dest,
    skill_source,
)


def _ok(cmd: List[str]) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or str(proc.returncode)).strip()
    return True, (proc.stdout or "").strip()


def install_skill(root: Path) -> List[str]:
    """Copy the skill into GROK_HOME and remember this checkout."""
    notes: List[str] = []
    src = skill_source(root)
    if not src.is_file():
        raise FileNotFoundError("skill missing in pack: {0}".format(src))
    dest = skill_dest()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    notes.append("skill → {0}".format(dest))
    marker = root_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(root.resolve()) + "\n", encoding="utf-8")
    notes.append("root marker → {0}".format(marker))
    return notes


def doctor() -> Tuple[int, List[str]]:
    """Return (exit_code, lines). Non-zero if the pack cannot run on this device."""
    lines: List[str] = []
    failed = False
    root = repo_root()
    lines.append("upgrade-audit {0}".format(__version__))
    lines.append("python {0}".format(sys.version.split()[0]))
    lines.append("root {0}".format(root))
    lines.append("GROK_HOME {0}".format(grok_home()))
    lines.append("clone_root {0}".format(os.environ.get("UPGRADE_AUDIT_CLONE_ROOT") or "(home)"))

    if sys.version_info < (3, 9):
        lines.append("FAIL python 3.9+ required")
        failed = True

    for mod in ("yaml", "reportlab", "pypdf"):
        try:
            __import__(mod)
            lines.append("ok import {0}".format(mod))
        except ImportError:
            lines.append(
                "FAIL import {0} (pip install -r requirements.txt or pip install -e .)".format(mod)
            )
            failed = True

    for label, cmd in (("git", ["git", "--version"]), ("gh", ["gh", "--version"])):
        ok, out = _ok(cmd)
        if ok:
            lines.append("ok {0} {1}".format(label, out.splitlines()[0] if out else ""))
        else:
            lines.append("FAIL {0}: {1}".format(label, out or "not on PATH"))
            failed = True

    gh_ok, gh_out = _ok(["gh", "auth", "status"])
    if gh_ok:
        lines.append("ok gh auth")
    else:
        lines.append("FAIL gh auth: {0}".format(gh_out or "not logged in"))
        failed = True

    if not catalog_path(root).is_file():
        lines.append("FAIL catalog missing: {0}".format(catalog_path(root)))
        failed = True
    if not protocol_path(root).is_file():
        lines.append("FAIL protocol missing: {0}".format(protocol_path(root)))
        failed = True
    try:
        cat = default_catalog()
        lines.append("ok catalog {0} in-scope={1}".format(cat.owner, len(cat.in_scope)))
    except Exception as exc:  # noqa: BLE001
        lines.append("FAIL catalog load: {0}".format(exc))
        failed = True

    dest = skill_dest()
    if dest.is_file():
        lines.append("ok skill {0}".format(dest))
    else:
        lines.append("WARN skill not installed ({0}). Run: upgrade-audit install-skill".format(dest))

    try:
        pol = load_policy()
        mode = pol.resolved_mode()
        if mode:
            lines.append("ok mode {0}: {1}".format(mode, MODE_HELP[mode]))
            if pol.ask_each_run:
                lines.append("ok ask_each_run: skill will confirm mode every run")
        else:
            lines.append(
                "WARN no action mode. Run: upgrade-audit configure --mode audit|fix|pr"
            )
        kill = pol.resolved_kill()
        if kill:
            lines.append("ok kill {0}: {1}".format(kill, KILL_HELP[kill]))
            if pol.ask_kill_each_run:
                lines.append("ok ask_kill_each_run: skill will confirm kill every run")
        else:
            lines.append(
                "WARN no kill policy. Run: upgrade-audit configure --kill none|stall"
            )
    except Exception as exc:  # noqa: BLE001
        lines.append("FAIL policy: {0}".format(exc))
        failed = True

    checkout = package_checkout()
    if root.resolve() != checkout.resolve() and not os.environ.get("UPGRADE_AUDIT_ROOT"):
        lines.append(
            "WARN UPGRADE_AUDIT_ROOT/marker {0} differs from this package {1}".format(root, checkout)
        )

    return (1 if failed else 0, lines)
