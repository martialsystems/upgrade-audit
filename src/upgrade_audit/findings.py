# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Validate finding objects and per-repo reports."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .constants import (
    ERROR_CLASS_SET,
    PDF_CONFIRMED_CAP,
    SEVERITY_RANK,
    SEVERITY_SET,
    STATUS_SET,
)


class ValidationError(ValueError):
    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _req_str(obj: Mapping[str, Any], key: str, errors: List[str], prefix: str) -> None:
    val = obj.get(key)
    if not isinstance(val, str) or not val.strip():
        errors.append("{0}{1} must be a non-empty string".format(prefix, key))


def validate_finding(obj: Any, index: int) -> List[str]:
    prefix = "finding[{0}].".format(index)
    errors: List[str] = []
    if not isinstance(obj, Mapping):
        return [prefix + "must be an object"]
    for key in (
        "repo",
        "commit",
        "file",
        "line",
        "error_class",
        "claim",
        "evidence",
        "proposed_fix",
        "severity",
        "status",
    ):
        if key == "line":
            line = obj.get("line")
            if not isinstance(line, int) or isinstance(line, bool) or line < 1:
                errors.append(prefix + "line must be a positive integer")
            continue
        _req_str(obj, key, errors, prefix)
    cls = obj.get("error_class")
    if isinstance(cls, str) and cls not in ERROR_CLASS_SET:
        errors.append(prefix + "error_class is not in the closed list: {0}".format(cls))
    sev = obj.get("severity")
    if isinstance(sev, str) and sev not in SEVERITY_SET:
        errors.append(prefix + "severity must be critical|major|minor")
    status = obj.get("status")
    if isinstance(status, str) and status not in STATUS_SET:
        errors.append(prefix + "status must be confirmed|rejected|unverified")
    if status == "confirmed":
        ev = obj.get("verifier_evidence")
        if not isinstance(ev, str) or not ev.strip():
            errors.append(prefix + "confirmed requires non-empty verifier_evidence")
    return errors


def validate_repo_report(obj: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(obj, Mapping):
        return ["report must be an object"]
    for key in ("repo", "github", "local_path", "audited_ref", "audited_sha"):
        _req_str(obj, key, errors, "")
    if "dirty" in obj and not isinstance(obj.get("dirty"), bool):
        errors.append("dirty must be a boolean")
    files_read = obj.get("files_read")
    if not isinstance(files_read, list) or any(not isinstance(x, str) or not x for x in files_read):
        errors.append("files_read must be a list of non-empty strings")
        files_read = []
    findings = obj.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        findings = []
    for i, finding in enumerate(findings):
        errors.extend(validate_finding(finding, i))
        if isinstance(finding, Mapping):
            if finding.get("repo") and obj.get("repo") and finding.get("repo") != obj.get("repo"):
                errors.append("finding[{0}].repo does not match report.repo".format(i))
    if isinstance(findings, list) and len(findings) == 0 and not files_read:
        errors.append("empty findings require a non-empty files_read list")
    return errors


def validate_or_raise(obj: Any) -> None:
    errors = validate_repo_report(obj)
    if errors:
        raise ValidationError(errors)


def confirmed_findings(report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows = [f for f in (report.get("findings") or []) if f.get("status") == "confirmed"]
    rows.sort(key=lambda f: (SEVERITY_RANK.get(f.get("severity"), 9), f.get("file", ""), f.get("line", 0)))
    return rows


def body_and_overflow(report: Mapping[str, Any], cap: int = PDF_CONFIRMED_CAP):
    confirmed = confirmed_findings(report)
    return confirmed[:cap], confirmed[cap:]


def count_by_severity(findings: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    counts = {"critical": 0, "major": 0, "minor": 0}
    for f in findings:
        sev = f.get("severity")
        if sev in counts:
            counts[sev] += 1
    return counts
