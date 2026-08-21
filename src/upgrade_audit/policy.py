# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Per-device policy. Anyone who installs the pack chooses mode and kill."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Optional

from .paths import policy_file_path

MODES = ("audit", "fix", "pr")

MODE_HELP = {
    "audit": "Read-only. PDF of confirmed issues and proposed fixes. No product edits.",
    "fix": "After the PDF, apply confirmed findings on a branch. Do not open a PR. Do not merge.",
    "pr": "After the PDF, apply confirmed findings on a branch and open a GitHub PR. Do not merge.",
}

KILLS = ("none", "stall")

KILL_HELP = {
    "none": "Never auto-kill a child. Slow or silent agents run until they finish or you stop them.",
    "stall": "Kill a child only if a snapshot shows no progress for stall_seconds. No wall-clock cap.",
}

STALL_SECONDS_DEFAULT = 480


@dataclass
class Policy:
    mode: Optional[str] = None
    ask_each_run: bool = False
    kill: Optional[str] = None
    ask_kill_each_run: bool = False
    stall_seconds: int = STALL_SECONDS_DEFAULT

    def resolved_mode(self, override: Optional[str] = None) -> Optional[str]:
        if override:
            return parse_mode(override)
        if self.ask_each_run:
            return None
        env = os.environ.get("UPGRADE_AUDIT_MODE")
        if env:
            return parse_mode(env)
        if self.mode:
            return parse_mode(self.mode)
        return None

    def resolved_kill(self, override: Optional[str] = None) -> Optional[str]:
        if override:
            return parse_kill(override)
        if self.ask_kill_each_run:
            return None
        env = os.environ.get("UPGRADE_AUDIT_KILL")
        if env:
            return parse_kill(env)
        if self.kill:
            return parse_kill(self.kill)
        return None


class PolicyError(ValueError):
    pass


def parse_mode(raw: str) -> str:
    mode = (raw or "").strip().lower()
    if mode not in MODES:
        raise PolicyError("mode must be audit, fix, or pr (got {0!r})".format(raw))
    return mode


def parse_kill(raw: str) -> str:
    kill = (raw or "").strip().lower()
    if kill not in KILLS:
        raise PolicyError("kill must be none or stall (got {0!r})".format(raw))
    return kill


def parse_stall_seconds(raw) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise PolicyError("stall_seconds must be an integer (got {0!r})".format(raw)) from exc
    if value < 1:
        raise PolicyError("stall_seconds must be >= 1 (got {0})".format(value))
    return value


def policy_path():
    return policy_file_path()


def load_policy() -> Policy:
    path = policy_path()
    env_mode = os.environ.get("UPGRADE_AUDIT_MODE")
    env_kill = os.environ.get("UPGRADE_AUDIT_KILL")
    if not path.is_file():
        return Policy(
            mode=parse_mode(env_mode) if env_mode else None,
            kill=parse_kill(env_kill) if env_kill else None,
            ask_each_run=False,
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PolicyError("invalid policy file {0}: {1}".format(path, exc)) from exc
    if not isinstance(raw, dict):
        raise PolicyError("policy file must be an object")
    mode = raw.get("mode")
    if mode in ("", None):
        mode = None
    else:
        mode = parse_mode(str(mode))
    kill = raw.get("kill")
    if kill in ("", None):
        kill = None
    else:
        kill = parse_kill(str(kill))
    stall = raw.get("stall_seconds", STALL_SECONDS_DEFAULT)
    return Policy(
        mode=mode,
        ask_each_run=bool(raw.get("ask_each_run")),
        kill=kill,
        ask_kill_each_run=bool(raw.get("ask_kill_each_run")),
        stall_seconds=parse_stall_seconds(stall),
    )


def save_policy(policy: Policy):
    path = policy_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(policy)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
