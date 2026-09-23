---
name: upgrade-audit
description: >
  Walk product repos on GitHub and run a model-upgrade logic audit when a
  new Grok generation ships. Confirms findings adversarially and writes a
  PDF. Device policy chooses action mode (audit, fix, pr) and child kill
  (none or stall). Use when the user runs /upgrade-audit, asks to check
  previous Grok projects, pick audit vs fix vs PR, install the pack on a
  device, or rerun the model-upgrade audit.
---

# Upgrade audit

Do not copy a repo list into this skill.

Resolve the **runner** root (call this ROOT). In order:

1. `$UPGRADE_AUDIT_ROOT` if set
2. `upgrade-audit print-root` if `upgrade-audit` is on PATH
3. `$GROK_HOME/upgrade-audit.root` (one line)
4. `$GROK_PLUGIN_ROOT` if it contains `bin/upgrade-audit` and `catalog/repos.yaml`
5. Two directories above this `SKILL.md` if that tree contains `bin/upgrade-audit` and `catalog/repos.yaml` (the helper `upgrade-audit` next to this file lives there)
6. If none of those exist: stop. Tell them to `grok plugin install upgrade-audit --trust` or `git clone https://github.com/martialsystems/upgrade-audit`. The pinned git tree includes the Python runner. Product page: https://martialgames.net/tools/upgrade-audit/

`GROK_PLUGIN_ROOT` is the installed plugin. After 1.2.0 it **is** the runner when it contains `bin/upgrade-audit`.

Read `$ROOT/protocol/AUDIT.md` and `$ROOT/catalog/repos.yaml` before spawning anyone.

If `upgrade-audit doctor` has not been run on this device, run it first. Any `FAIL` line stops the audit.

## Device policy (required)

Anyone who installs chooses **both**. Per device, not baked into the tree.

Resolve MODE: `--mode`, then `$UPGRADE_AUDIT_MODE`, then `upgrade-audit configure`. If unset, ask and save.

| Mode | After the PDF |
|------|---------------|
| `audit` | Stop. No product edits. |
| `fix` | Apply confirmed findings on a branch. No PR. No merge. |
| `pr` | Same as fix, then open a GitHub PR. No merge. |

Resolve KILL: `--kill`, then `$UPGRADE_AUDIT_KILL`, then `configure`. If unset, ask and save.

| Kill | During the walk |
|------|-----------------|
| `none` | Never auto-kill. Leave agents running. |
| `stall` | Kill only if a snapshot shows no progress for `stall_seconds` (default 480). No wall-clock cap. |

The **audit walk** is always read-only. Never `reset --hard`, never merge, never deploy. Never wait-all on a wave.

## Args

- `--from <ver>`: prior generation. Default: last completed run's `--to`, else `4.5`.
- `--to <ver>`: current session model family.
- `--only <id>`: one catalog id (repeatable).
- `--all`: ignore `queue.json` and walk every in-scope catalog id.
- `--resume`: continue today's run dir if it exists.
- `--mode audit|fix|pr`: override saved action mode for this run only.
- `--kill none|stall`: override saved child-kill policy for this run only.

If `$ROOT/queue.json` is present, `init-run` walks those ids when `--only` and `--all` are omitted. A missing file still walks the whole in-scope catalog.

## Procedure

Work from ROOT. Command: `upgrade-audit` on PATH, else `$ROOT/bin/upgrade-audit`, else this skill directory's `upgrade-audit` helper, else `PYTHONPATH=$ROOT/src python3 -m upgrade_audit`.

1. **Inventory first**

```bash
upgrade-audit inventory --adopt --out /tmp/upgrade-audit-inv.json
```

If catalog `owner` is empty, the CLI uses the logged-in `gh` user. New owned non-forks are appended. New forks are auto-excluded. Halt only if a **cataloged** repo is missing on GitHub.

2. **Init run dir**

```bash
upgrade-audit init-run --from <from> --to <to> [--resume] [--only <id> ...]   # or --all
```

Move the inventory JSON to `<run>/inventory.json`.

3. **Sync.** Never discard dirt.

```bash
upgrade-audit sync --out <run>/sync.json [--only <id> ...]
```

4. **Walk** with `upgrade-audit walk-step`. Snapshot in-flight agents with `timeout_ms: 0`. Spawn a repo's verifier as soon as its auditor finishes. One repo per agent. Obey `kill` / `unverify` / `validate` from walk-step. Empty findings only with a real `files_read` list.

5. **Ledger** then **PDF**. Complete only when every requested repo has a validated report or a recorded skip. A skip is not clean.

6. **Act on MODE.** `audit`: stop. `fix` / `pr`: branch from audited SHA, apply confirmed findings only, write `<run>/applied.json`. `pr`: `gh pr create`, do not merge.

7. **Report:** MODE, PDF path, counts, applied/PRs, skips, dirt. Do not claim a live site was play-tested.

## Resume

Do not redo `repos/*.json` already in the run dir.

## Defaults

Fleet PDF body cap: 8 confirmed findings per repo. Full dump for one catalog id: `upgrade-audit repo-pdf --repo <id>` (critical, major, and minor; no cap). New TUI for a queued walk: `upgrade-audit send-grok --from <from> --to <to>`.
