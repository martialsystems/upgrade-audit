---
name: upgrade-audit
description: >
  Walk product repos on GitHub and run a model-upgrade logic audit when a
  new Grok generation ships. Confirms findings adversarially and writes a
  PDF. Device policy chooses what happens next: audit (read-only), fix
  (branch only), or pr (branch + GitHub PR). Use when the user runs
  /upgrade-audit, asks to check previous Grok projects, pick audit vs fix
  vs PR, install the pack on a device, or rerun the model-upgrade audit.
---

# Upgrade audit

Do not copy a repo list into this skill.

Resolve the **runner** root (call this ROOT), not only the plugin folder. In order:

1. `$UPGRADE_AUDIT_ROOT` if set
2. `upgrade-audit print-root` if `upgrade-audit` is on PATH
3. `$GROK_HOME/upgrade-audit.root` (one line)
4. A directory the user unpacked from the **Release zip** that contains `bin/upgrade-audit` and `catalog/`
5. If none of those exist: stop. Tell them to download `upgrade-audit-<ver>.zip` from https://github.com/martialsystems/upgrade-audit/releases (the asset, not Source code zip) and run `upgrade-audit install-skill` from that unpack. Product page: https://martialgames.net/tools/upgrade-audit/

`GROK_PLUGIN_ROOT` is the installed plugin (this skill). It is **not** the runner. Do not treat it as ROOT unless it also contains `bin/upgrade-audit`.

Read `$ROOT/protocol/AUDIT.md` and `$ROOT/catalog/repos.yaml` before spawning anyone.

If `upgrade-audit doctor` has not been run on this device, run it first. Any `FAIL` line stops the audit.

## Action mode (required)

Anyone who installs chooses how to proceed. Resolve MODE in this order:

1. `--mode audit|fix|pr` on this invocation
2. `$UPGRADE_AUDIT_MODE`
3. `upgrade-audit configure`
4. If unset or `ask_each_run`: **ask the user** and save with `upgrade-audit configure --mode <choice>` unless they want `--ask-each-run`

| Mode | After the PDF |
|------|----------------|
| `audit` | Stop. No product edits. |
| `fix` | Apply confirmed findings on a branch. No PR. No merge. |
| `pr` | Same as fix, then open a GitHub PR. No merge. |

The **audit walk** is always read-only. Never `reset --hard`, never merge, never deploy.

## Args

- `--from <ver>`: prior generation. Default: last completed run's `--to`, else `4.5`.
- `--to <ver>`: current session model family.
- `--only <id>`: one catalog id (repeatable).
- `--resume`: continue today's run dir if it exists.
- `--mode audit|fix|pr`: override the saved device policy for this run only.

## Procedure

Work from ROOT. Command: `upgrade-audit` on PATH, else `$ROOT/bin/upgrade-audit`, else `PYTHONPATH=$ROOT/src python3 -m upgrade_audit`.

1. **Inventory first**

```bash
upgrade-audit inventory --adopt --out /tmp/upgrade-audit-inv.json
```

If catalog `owner` is empty, the CLI uses the logged-in `gh` user. New owned non-forks are appended. New forks are auto-excluded. Halt only if a **cataloged** repo is missing on GitHub.

2. **Init run dir**

```bash
upgrade-audit init-run --from <from> --to <to> [--resume] [--only <id> ...]
```

Move the inventory JSON to `<run>/inventory.json`.

3. **Sync.** Never discard dirt.

```bash
upgrade-audit sync --out <run>/sync.json [--only <id> ...]
```

4. **Walk** catalog order in waves of 3 to 4. After each repo: collect context, read-only auditor, independent verifier, `upgrade-audit validate`. Empty findings only with a real `files_read` list.

5. **Ledger** then **PDF**.

6. **Act on MODE.** `audit`: stop. `fix` / `pr`: branch from audited SHA, apply confirmed findings only, write `<run>/applied.json`. `pr`: `gh pr create`, do not merge.

7. **Report:** MODE, PDF path, counts, applied/PRs, skips, dirt. Do not claim a live site was play-tested.

## Resume

Do not redo `repos/*.json` already in the run dir.

## Defaults

PDF body cap: 8 confirmed findings per repo.
