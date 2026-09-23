# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""JSON Schema documents generated from constants (one home for enums)."""

from __future__ import annotations

from .constants import BOARD_STATUSES, ERROR_CLASSES, SEVERITIES, STATUSES, SUGGEST_PRESETS


def finding_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Upgrade-audit finding",
        "type": "object",
        "additionalProperties": False,
        "required": [
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
        ],
        "properties": {
            "repo": {"type": "string", "minLength": 1},
            "commit": {"type": "string", "minLength": 1},
            "file": {"type": "string", "minLength": 1},
            "line": {"type": "integer", "minimum": 1},
            "error_class": {"type": "string", "enum": list(ERROR_CLASSES)},
            "claim": {"type": "string", "minLength": 1},
            "evidence": {"type": "string", "minLength": 1},
            "proposed_fix": {"type": "string", "minLength": 1},
            "severity": {"type": "string", "enum": list(SEVERITIES)},
            "status": {"type": "string", "enum": list(STATUSES)},
            "verifier_evidence": {"type": "string"},
        },
        "if": {"properties": {"status": {"const": "confirmed"}}},
        "then": {"required": ["verifier_evidence"]},
    }


def repo_report_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Upgrade-audit per-repo report",
        "type": "object",
        "required": [
            "repo",
            "github",
            "local_path",
            "audited_ref",
            "audited_sha",
            "dirty",
            "files_read",
            "findings",
        ],
        "properties": {
            "repo": {"type": "string", "minLength": 1},
            "github": {"type": "string", "minLength": 1},
            "local_path": {"type": "string", "minLength": 1},
            "audited_ref": {"type": "string", "minLength": 1},
            "audited_sha": {"type": "string", "minLength": 1},
            "dirty": {"type": "boolean"},
            "dirty_paths": {"type": "array", "items": {"type": "string"}},
            "sync_note": {"type": "string"},
            "files_read": {"type": "array", "items": {"type": "string", "minLength": 1}},
            "findings": {"type": "array", "items": {"$ref": "finding.schema.json"}},
            "auditor_notes": {"type": "string"},
        },
    }


def run_manifest_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Upgrade-audit run manifest",
        "type": "object",
        "required": ["from_version", "to_version", "date", "status"],
        "properties": {
            "from_version": {"type": "string", "minLength": 1},
            "to_version": {"type": "string", "minLength": 1},
            "date": {"type": "string", "minLength": 1},
            "status": {"type": "string", "enum": ["in_progress", "complete", "halted"]},
            "repos": {"type": "array", "items": {"type": "string"}},
            "halt_reason": {"type": "string"},
        },
    }


def queue_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Upgrade-audit walk queue",
        "type": "object",
        "additionalProperties": False,
        "required": ["from_version", "to_version", "ids"],
        "properties": {
            "from_version": {"type": "string", "minLength": 1},
            "to_version": {"type": "string", "minLength": 1},
            "ids": {"type": "array", "items": {"type": "string", "minLength": 1}},
            "reason": {"type": "string"},
            "updated_at": {"type": "string"},
        },
    }


def board_row_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Upgrade-audit board repo row",
        "type": "object",
        "required": ["id", "status", "queued"],
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "status": {"type": "string", "enum": list(BOARD_STATUSES)},
            "queued": {"type": "boolean"},
            "suggest_presets": {"type": "array", "items": {"type": "string", "enum": list(SUGGEST_PRESETS)}},
        },
    }
