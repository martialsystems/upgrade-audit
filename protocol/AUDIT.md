# Upgrade-audit protocol

**Copyright (c) 2026 Martial Systems LLC. All rights reserved.**

Read-only review of **shipped** logic under a newer Grok generation. This is not `/review` of a diff and not a style pass.

Runtime enums live in `src/upgrade_audit/constants.py`. A finding whose `error_class` is not in that list is invalid.

## What you read

`scripts/collect_context.py` (or `python3 -m upgrade_audit collect`) writes a map of the **read_path**. That path is a clean checkout of `{audit_remote}/{default}` HEAD, often a detached worktree. Do not read the operator's dirty working tree and call it shipped.

You must `read_file` / `grep` files in `read_path`. Do not answer from memory of other sessions.

## Error classes (closed)

1. `inverted_or_broken_invariant`: off-by-one, wrong comparison, fail-open where the product requires fail-closed.
2. `silent_fallback`: catch / prefer-A-else-B that hides the real path or swallows the bug.
3. `dead_or_duplicate_path`: mirrored HTML/JS, two engines, cached old asset still dominant.
4. `law_vs_code_drift`: AGENTS.md, product-law file, `verify.sh` freeze, or checklist says X; code does Y.
5. `look_ahead_leakage`: features, labels, or eval that use future information.
6. `numeric_money_time`: units, timezone, window alignment, EV gate, paper vs live mix-up.
7. `state_cache_persistence`: localStorage, `.env`, seed files, module globals.
8. `safety_privacy_claim`: extension saves data it claims not to; a draft bot can post; live trading is the default; a public site can regress.
9. `test_lie`: test name or comment claims a behavior the assertion does not check.
10. `stale_model_era_assumption`: comments, defaults, or "the model cannot X" that the newer generation should revisit.

## Finding object

Required: `repo`, `commit`, `file`, `line`, `error_class`, `claim`, `evidence`, `proposed_fix`, `severity` (`critical` | `major` | `minor`), `status` (`confirmed` | `rejected` | `unverified`).

`confirmed` also requires `verifier_evidence` written by the **second** agent, not the auditor.

`claim` is what is wrong, specific to this file. `evidence` quotes code or a test you actually opened. `proposed_fix` is prose. The audit walk does not apply it. Apply only later, and only if this device's policy mode is `fix` or `pr`.

## Rules

- Empty `findings` is valid only when `files_read` names the files you opened.
- Do not invent issues to fill space.
- During the audit walk: do not edit product trees.
- Cap for the PDF body is 8 confirmed findings per repo (highest severity first). You may report more; overflow is titled only.
- A finding is PDF-eligible only after a verifier subagent tries to refute it and still finds the evidence. Failed or missing verify: `unverified`.

## After the PDF (device policy)

Anyone who installs the pack chooses a mode. Resolve with `upgrade-audit configure` (or `$UPGRADE_AUDIT_MODE`, or `--mode` on this run). If none is set, ask once and save.

| Mode | What happens after the PDF |
|------|----------------------------|
| `audit` | Stop. No product edits. |
| `fix` | Apply **confirmed** findings only, on a new branch from the audited SHA. Do not open a PR. Do not merge. Never `reset --hard`. Skip a repo whose working tree is dirty unless you can work on a detached branch without touching dirt. |
| `pr` | Same as `fix`, then `gh pr create`. Do not merge. |

Do not apply rejected or unverified findings. Do not deploy. Record what you applied in `<run>/applied.json`.

## Walk join

The parent must not wait-all on a wave. After spawn, take a **non-blocking** snapshot (`get_command_or_subagent_output` with `timeout_ms: 0`, or `wait_any` with `timeout_ms` at most 5000 if that tool exists). Never pass a positive timeout on a list of ids.

`upgrade-audit walk-step --run-dir <run> --snapshot <json>` is the scheduler. Obey its `spawn`, `kill`, `validate`, and `join` objects. One repo per agent. As soon as an auditor completes, spawn that repo's verifier. Do not wait for the slowest peer.

Child **kill** is a per-device choice, same as action mode. Anyone who downloads the pack sets it with `upgrade-audit configure --kill none|stall` (or `--ask-kill-each-run`).

| Kill | Meaning |
|------|---------|
| `none` | Never auto-kill. Slow or silent agents run until they finish or the operator stops them. |
| `stall` | Kill only if a snapshot shows no progress for `stall_seconds` (default 480). No wall-clock cap. A 14-minute auditor that is still calling tools is left alone. |

On stall kill: auditor: skip record, not clean. verifier: write the draft with findings `unverified`. fix/test: leave the finding open; do not merge.

Cancelled with no output: respawn once, then skip `cancelled`. That is not a stall kill.

Manifest `complete` only when every requested repo has a validated report or a recorded skip (`sync_fail`, `stall`, `cancelled`). A skip is listed in the PDF. It is not an empty-findings clean repo.

## Verifier

Read the cited file at `read_path`. Set `status` to `confirmed` only with independent evidence. Otherwise `rejected` (the claim is false) or `unverified` (you could not check). Do not raise severity. Do not add new findings.
