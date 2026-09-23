# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Read-only board over catalog + run JSON. Does not spawn auditors or apply fixes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .catalog import Catalog
from .constants import SEVERITIES, SUGGEST_PRESETS
from .ledger import latest_completed_run
from .queue import load_queue, queue_path
from .rundir import pdf_path


def classify_status(
    *,
    report: Optional[Mapping[str, Any]],
    skip_reason: Optional[str],
    in_progress: bool,
) -> str:
    if in_progress:
        return "in_progress"
    if skip_reason:
        return "skipped"
    if report is None:
        return "never_audited"
    findings = report.get("findings") if isinstance(report.get("findings"), list) else []
    files_read = report.get("files_read") if isinstance(report.get("files_read"), list) else []
    confirmed = [f for f in findings if isinstance(f, dict) and f.get("status") == "confirmed"]
    unverified = [f for f in findings if isinstance(f, dict) and f.get("status") == "unverified"]
    if confirmed:
        return "open"
    if not files_read:
        return "unchecked"
    if unverified:
        return "unverified"
    return "clean"


def _safe_json(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _runs(runs_root: Path) -> List[Path]:
    if not runs_root.is_dir():
        return []
    out = []
    for path in sorted(runs_root.iterdir(), key=lambda p: p.name):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        out.append(path)
    return out


def latest_run_with_status(runs_root: Path, status: str) -> Optional[Path]:
    found = None
    for path in _runs(runs_root):
        data = _safe_json(path / "manifest.json")
        if data and data.get("status") == status:
            found = path
    return found


def _skip_map(run_dir: Optional[Path]) -> Dict[str, str]:
    if run_dir is None:
        return {}
    walk = _safe_json(run_dir / "walk.json") or {}
    out: Dict[str, str] = {}
    for row in walk.get("skipped") or []:
        if isinstance(row, dict) and row.get("repo") and row.get("reason"):
            out[str(row["repo"])] = str(row["reason"])
    return out


def _in_progress_ids(run_dir: Optional[Path]) -> set:
    if run_dir is None:
        return set()
    walk = _safe_json(run_dir / "walk.json") or {}
    done = set(walk.get("done") or [])
    skipped = {row.get("repo") for row in (walk.get("skipped") or []) if isinstance(row, dict)}
    accounted = done | skipped
    ids = set()
    for rid in walk.get("queue") or []:
        ids.add(str(rid))
    for rid in walk.get("pending_verify") or []:
        ids.add(str(rid))
    for row in walk.get("in_flight") or []:
        if isinstance(row, dict) and row.get("repo"):
            ids.add(str(row["repo"]))
    return ids - accounted


def _load_report(run_dir: Optional[Path], repo_id: str) -> Optional[dict]:
    if run_dir is None:
        return None
    return _safe_json(run_dir / "repos" / "{0}.json".format(repo_id))


def _count_status(findings: Iterable[Mapping[str, Any]], status: str) -> int:
    return sum(1 for f in findings if isinstance(f, dict) and f.get("status") == status)


def _confirmed_by_severity(findings: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    counts = {name: 0 for name in SEVERITIES}
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("status") != "confirmed":
            continue
        sev = finding.get("severity")
        if sev in counts:
            counts[sev] += 1
    return counts


def _last_block(report: Optional[Mapping[str, Any]], run_dir: Optional[Path]) -> Optional[dict]:
    if report is None or run_dir is None:
        return None
    manifest = _safe_json(run_dir / "manifest.json") or {}
    findings = report.get("findings") if isinstance(report.get("findings"), list) else []
    return {
        "run": str(run_dir),
        "date": manifest.get("date") or "",
        "from_version": manifest.get("from_version") or "",
        "to_version": manifest.get("to_version") or "",
        "sha": report.get("audited_sha") or "",
        "dirty": bool(report.get("dirty")),
        "confirmed": _confirmed_by_severity(findings),
        "unverified": _count_status(findings, "unverified"),
        "rejected": _count_status(findings, "rejected"),
    }


def project_board(
    catalog: Catalog,
    *,
    runs_root: Path,
    queue: Optional[Mapping[str, Any]] = None,
    policy: Optional[Mapping[str, Any]] = None,
) -> dict:
    completed = None
    try:
        completed = latest_completed_run(runs_root)
    except FileNotFoundError:
        completed = None
    in_progress = latest_run_with_status(runs_root, "in_progress")
    if in_progress is not None and completed is not None and in_progress.resolve() == completed.resolve():
        in_progress = None
    active_ids = _in_progress_ids(in_progress)
    skips = _skip_map(in_progress) if in_progress is not None else _skip_map(completed)
    queued_ids = list(queue.get("ids") or []) if queue else []
    queued_set = set(queued_ids)
    rows = []
    for item in catalog.in_scope:
        report = _load_report(in_progress, item.id) or _load_report(completed, item.id)
        report_run = in_progress if _load_report(in_progress, item.id) else completed
        skip_reason = skips.get(item.id)
        status = classify_status(
            report=report,
            skip_reason=skip_reason,
            in_progress=item.id in active_ids,
        )
        rows.append(
            {
                "id": item.id,
                "github": item.github,
                "notes": item.notes,
                "local": item.local,
                "walk": catalog.effective_walk(item),
                "queued": item.id in queued_set,
                "status": status,
                "skip_reason": skip_reason,
                "last": _last_block(report, report_run),
            }
        )
    pdf = None
    if completed is not None:
        manifest = _safe_json(completed / "manifest.json") or {}
        candidate = pdf_path(
            completed,
            str(manifest.get("from_version") or "4.5"),
            str(manifest.get("to_version") or "4.6"),
        )
        if candidate.is_file():
            pdf = str(candidate)
    return {
        "from_version": (queue or {}).get("from_version")
        or (( _safe_json(completed / "manifest.json") or {}).get("from_version") if completed else None),
        "to_version": (queue or {}).get("to_version")
        or (( _safe_json(completed / "manifest.json") or {}).get("to_version") if completed else None),
        "completed_run": str(completed) if completed else None,
        "in_progress_run": str(in_progress) if in_progress else None,
        "pdf": pdf,
        "queue": {
            "present": queue is not None,
            "ids": queued_ids,
            "reason": (queue or {}).get("reason") or "",
        },
        "policy": policy or {},
        "repos": rows,
    }


def suggest_ids(board: Mapping[str, Any], preset: str) -> List[str]:
    if preset not in SUGGEST_PRESETS:
        raise ValueError("unknown suggest preset: {0}".format(preset))
    rows = board.get("repos") or []
    out: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "")
        if not rid:
            continue
        status = row.get("status")
        last = row.get("last") if isinstance(row.get("last"), dict) else {}
        confirmed = last.get("confirmed") if isinstance(last.get("confirmed"), dict) else {}
        if preset == "all-in-scope":
            out.append(rid)
        elif preset == "open" and status == "open":
            out.append(rid)
        elif preset == "open-critical" and status == "open" and int(confirmed.get("critical") or 0) > 0:
            out.append(rid)
        elif preset == "never-audited" and status == "never_audited":
            out.append(rid)
        elif preset == "skipped" and status == "skipped":
            out.append(rid)
        elif preset == "unverified" and status == "unverified":
            out.append(rid)
    return out


def repo_detail(
    catalog: Catalog,
    runs_root: Path,
    repo_id: str,
) -> dict:
    item = catalog.in_scope_by_id(repo_id)
    completed = None
    try:
        completed = latest_completed_run(runs_root)
    except FileNotFoundError:
        completed = None
    in_progress = latest_run_with_status(runs_root, "in_progress")
    report = _load_report(in_progress, item.id) or _load_report(completed, item.id)
    findings = []
    if report and isinstance(report.get("findings"), list):
        for finding in report["findings"]:
            if not isinstance(finding, dict):
                continue
            findings.append(
                {
                    "file": finding.get("file"),
                    "line": finding.get("line"),
                    "error_class": finding.get("error_class"),
                    "claim": finding.get("claim"),
                    "severity": finding.get("severity"),
                    "status": finding.get("status"),
                    "proposed_fix": finding.get("proposed_fix"),
                }
            )
    board = project_board(catalog, runs_root=runs_root, queue=None)
    row = next((r for r in board["repos"] if r["id"] == item.id), None)
    return {
        "id": item.id,
        "github": item.github,
        "notes": item.notes,
        "status": (row or {}).get("status"),
        "last": (row or {}).get("last"),
        "files_read": (report or {}).get("files_read") or [],
        "auditor_notes": (report or {}).get("auditor_notes") or "",
        "findings": findings,
    }


def load_repo_report(catalog: Catalog, runs_root: Path, repo_id: str) -> Optional[dict]:
    """Raw last report for one catalog id, or None if never audited."""
    item = catalog.in_scope_by_id(repo_id)
    completed = None
    try:
        completed = latest_completed_run(runs_root)
    except FileNotFoundError:
        completed = None
    in_progress = latest_run_with_status(runs_root, "in_progress")
    return _load_report(in_progress, item.id) or _load_report(completed, item.id)


def load_queue_for_root(root: Path) -> Optional[dict]:
    return load_queue(queue_path(root))


def grok_command(from_version: Optional[str], to_version: Optional[str], ids: Sequence[str]) -> str:
    frm = from_version or "4.5"
    to = to_version or "4.6"
    if ids:
        return "/upgrade-audit --from {0} --to {1}  (queue: {2})".format(
            frm, to, ", ".join(ids)
        )
    return "/upgrade-audit --from {0} --to {1} --all".format(frm, to)
