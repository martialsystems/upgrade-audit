# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Closed enums for findings, reports, and JSON Schema emission.

One home for the error-class list. protocol/AUDIT.md and schema/*.json
are generated from these values (or must match them). Runtime validation
imports this module; it does not re-state the list.
"""

from __future__ import annotations

from typing import FrozenSet, Tuple

ERROR_CLASSES: Tuple[str, ...] = (
    "inverted_or_broken_invariant",
    "silent_fallback",
    "dead_or_duplicate_path",
    "law_vs_code_drift",
    "look_ahead_leakage",
    "numeric_money_time",
    "state_cache_persistence",
    "safety_privacy_claim",
    "test_lie",
    "stale_model_era_assumption",
)

ERROR_CLASS_TITLES = {
    "inverted_or_broken_invariant": "Inverted or broken invariant",
    "silent_fallback": "Silent fallback",
    "dead_or_duplicate_path": "Dead or duplicate path",
    "law_vs_code_drift": "Law vs code drift",
    "look_ahead_leakage": "Look-ahead / leakage",
    "numeric_money_time": "Numeric / money / time",
    "state_cache_persistence": "State / cache / persistence",
    "safety_privacy_claim": "Safety / privacy / claim",
    "test_lie": "Test lie",
    "stale_model_era_assumption": "Stale model-era assumption",
}

SEVERITIES: Tuple[str, ...] = ("critical", "major", "minor")
SEVERITY_RANK = {"critical": 0, "major": 1, "minor": 2}

STATUSES: Tuple[str, ...] = ("confirmed", "rejected", "unverified")

PDF_CONFIRMED_CAP = 8

BOARD_STATUSES: Tuple[str, ...] = (
    "never_audited",
    "in_progress",
    "skipped",
    "open",
    "unverified",
    "unchecked",
    "clean",
)

SUGGEST_PRESETS: Tuple[str, ...] = (
    "open-critical",
    "open",
    "never-audited",
    "skipped",
    "unverified",
    "all-in-scope",
)

ERROR_CLASS_SET: FrozenSet[str] = frozenset(ERROR_CLASSES)
SEVERITY_SET: FrozenSet[str] = frozenset(SEVERITIES)
STATUS_SET: FrozenSet[str] = frozenset(STATUSES)
