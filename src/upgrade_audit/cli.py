# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Command-line entry points used by scripts/ and the /upgrade-audit skill."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

from .board import grok_command, load_repo_report, project_board, suggest_ids
from .catalog import Catalog, default_catalog, load_catalog, select_repos, write_catalog
from .constants import SUGGEST_PRESETS
from .context import collect_context
from .findings import ValidationError, validate_or_raise
from .github import GitHubError, current_login, list_owned_repos
from .inventory import adopt_new, classify, result_to_dict
from .ledger import compare_runs, latest_completed_run
from .pack import doctor, install_skill
from .paths import catalog_path, isolated_tmp, package_checkout, repo_root, runs_dir, schema_dir
from .policy import (
    KILL_HELP,
    KILLS,
    MODE_HELP,
    MODES,
    Policy,
    PolicyError,
    STALL_SECONDS_DEFAULT,
    load_policy,
    parse_kill,
    parse_mode,
    parse_stall_seconds,
    save_policy,
)
from .pdf import build_pdf, build_repo_pdf, safe_repo_filename
from .send_grok import SendGrokError, launch_send
from .queue import (
    QueueError,
    clear_queue,
    load_queue,
    public_payload,
    queue_path,
    require_walk,
    resolve_requested,
    save_queue,
    validate_ids,
)
from .rundir import allocate_run_dir, pdf_path, read_json, write_json, write_manifest
from .schema_emit import finding_schema, queue_schema, repo_report_schema, run_manifest_schema
from .sync import results_to_dict, sync_all
from .walk import load_walk, save_walk, seed_walk, step as walk_step


def _add_only(p: argparse.ArgumentParser) -> None:
    p.add_argument("--only", action="append", default=[], help="Restrict to catalog id (repeatable)")


def _add_walk(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--walk",
        default=None,
        help="Restrict to one catalog walk named in catalog/walks.yaml",
    )


def _add_catalog(p: argparse.ArgumentParser) -> None:
    p.add_argument("--catalog", type=Path, default=None)


def _add_run(p: argparse.ArgumentParser) -> None:
    p.add_argument("--run-dir", type=Path, required=True)


def cmd_print_root(_args: argparse.Namespace) -> int:
    print(repo_root())
    return 0


def cmd_install_skill(args: argparse.Namespace) -> int:
    root = args.root or package_checkout()
    if not (root / "catalog" / "repos.yaml").is_file():
        print("install-skill: {0} is not a pack checkout".format(root), file=sys.stderr)
        return 1
    for line in install_skill(root):
        print(line)
    if args.mode or args.kill or args.ask_each_run or args.ask_kill_each_run or args.stall_seconds is not None:
        try:
            current = load_policy()
        except PolicyError:
            current = Policy()
        try:
            mode = parse_mode(args.mode) if args.mode else current.mode
            kill = parse_kill(args.kill) if args.kill else current.kill
            stall = (
                parse_stall_seconds(args.stall_seconds)
                if args.stall_seconds is not None
                else current.stall_seconds
            )
            if args.ask_each_run:
                mode = None
            if args.ask_kill_each_run:
                kill = None
            path = save_policy(
                Policy(
                    mode=mode,
                    ask_each_run=args.ask_each_run or (current.ask_each_run and not args.mode),
                    kill=kill,
                    ask_kill_each_run=args.ask_kill_each_run
                    or (current.ask_kill_each_run and not args.kill),
                    stall_seconds=stall,
                )
            )
        except PolicyError as exc:
            print("install-skill: {0}".format(exc), file=sys.stderr)
            return 1
        print("policy → {0}".format(path))
        print(
            "mode={0} kill={1}".format(
                mode or ("(ask)" if args.ask_each_run else "(unset)"),
                "(ask)" if args.ask_kill_each_run else (kill or "(unset)"),
            )
        )
    else:
        try:
            current = load_policy()
        except PolicyError:
            current = Policy()
        if current.resolved_mode() and current.resolved_kill():
            print(
                "policy unchanged: mode={0} kill={1}".format(
                    current.resolved_mode(), current.resolved_kill()
                )
            )
            return 0
        print("Device policy incomplete. Anyone who downloads chooses:")
        print("Action mode (after the PDF):")
        for name in MODES:
            print("  {0}: {1}".format(name, MODE_HELP[name]))
        print("Child kill (during the walk):")
        for name in KILLS:
            print("  {0}: {1}".format(name, KILL_HELP[name]))
        print("Then: upgrade-audit configure --mode audit|fix|pr --kill none|stall")
        print("Or:   upgrade-audit configure --ask-each-run --ask-kill-each-run")
    return 0


def cmd_configure(args: argparse.Namespace) -> int:
    try:
        current = load_policy()
    except PolicyError as exc:
        print("configure: {0}".format(exc), file=sys.stderr)
        return 1
    mode = current.mode
    ask = current.ask_each_run
    kill = current.kill
    ask_kill = current.ask_kill_each_run
    stall_seconds = current.stall_seconds
    if args.mode:
        try:
            mode = parse_mode(args.mode)
        except PolicyError as exc:
            print("configure: {0}".format(exc), file=sys.stderr)
            return 1
        ask = False
    if args.ask_each_run:
        ask = True
        mode = None
    if args.kill:
        try:
            kill = parse_kill(args.kill)
        except PolicyError as exc:
            print("configure: {0}".format(exc), file=sys.stderr)
            return 1
        ask_kill = False
    if args.ask_kill_each_run:
        ask_kill = True
        kill = None
    if args.stall_seconds is not None:
        try:
            stall_seconds = parse_stall_seconds(args.stall_seconds)
        except PolicyError as exc:
            print("configure: {0}".format(exc), file=sys.stderr)
            return 1
    touched = any(
        (
            args.mode,
            args.ask_each_run,
            args.kill,
            args.ask_kill_each_run,
            args.stall_seconds is not None,
        )
    )
    if not touched:
        print(
            json.dumps(
                {
                    "mode": current.resolved_mode(),
                    "ask_each_run": current.ask_each_run,
                    "stored_mode": current.mode,
                    "kill": current.resolved_kill(),
                    "ask_kill_each_run": current.ask_kill_each_run,
                    "stored_kill": current.kill,
                    "stall_seconds": current.stall_seconds,
                },
                indent=2,
            )
        )
        missing = []
        if current.resolved_mode() is None:
            missing.append("upgrade-audit configure --mode audit|fix|pr")
        if current.resolved_kill() is None:
            missing.append("upgrade-audit configure --kill none|stall")
        if missing:
            print("Choose: {0}".format("; ".join(missing)), file=sys.stderr)
            return 2
        return 0
    path = save_policy(
        Policy(
            mode=mode,
            ask_each_run=ask,
            kill=kill,
            ask_kill_each_run=ask_kill,
            stall_seconds=stall_seconds,
        )
    )
    print(path)
    print(
        "mode={0} ask_each_run={1} kill={2} ask_kill_each_run={3} stall_seconds={4}".format(
            mode or "(ask)",
            ask,
            kill or "(ask)",
            ask_kill,
            stall_seconds,
        )
    )
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    code, lines = doctor()
    for line in lines:
        print(line)
    return code


def cmd_write_schemas(_args: argparse.Namespace) -> int:
    dest = schema_dir()
    dest.mkdir(parents=True, exist_ok=True)
    mapping = {
        "finding.schema.json": finding_schema(),
        "repo_report.schema.json": repo_report_schema(),
        "run_manifest.schema.json": run_manifest_schema(),
        "queue.schema.json": queue_schema(),
    }
    for name, payload in mapping.items():
        (dest / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(dest / name)
    try:
        from .self_audit import available as self_audit_available
        from .self_audit import write_schema as write_self_audit_schema
    except ImportError:
        return 0
    if self_audit_available():
        print(write_self_audit_schema(dest))
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog) if args.catalog else default_catalog()
    if not catalog.owner:
        try:
            login = current_login()
        except GitHubError as exc:
            print("inventory: catalog owner is empty and gh login failed: {0}".format(exc), file=sys.stderr)
            return 1
        catalog = Catalog(
            owner=login,
            in_scope=list(catalog.in_scope),
            excluded=list(catalog.excluded),
            source=catalog.source,
            clone_root_raw=catalog.clone_root_raw,
            walks=catalog.walks,
        )
        print("inventory: using gh login {0} as catalog owner".format(login), file=sys.stderr)
    try:
        remotes = list_owned_repos(catalog.owner)
    except GitHubError as exc:
        print("inventory: {0}".format(exc), file=sys.stderr)
        return 1
    adopted: list = []
    auto_forks: list = []
    if args.adopt:
        catalog, adopted, auto_forks = adopt_new(catalog, remotes)
        if adopted or auto_forks:
            dest = args.catalog or catalog.source
            write_catalog(catalog, dest)
            catalog = load_catalog(dest)
    result = classify(catalog, remotes)
    payload = result_to_dict(result)
    payload["owner"] = catalog.owner
    payload["adopted"] = adopted
    payload["adopted_walks"] = {
        rid: catalog.effective_walk(catalog.in_scope_by_id(rid)) for rid in adopted
    }
    payload["auto_excluded_forks"] = auto_forks
    if args.out:
        write_json(args.out, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if result.uncategorized_non_forks:
        print(
            "inventory HALT: uncategorized non-forks={0}".format(payload["uncategorized_non_forks"]),
            file=sys.stderr,
        )
        return 2
    if result.missing_from_github:
        print(
            "inventory HALT: catalog rows missing on GitHub={0}".format(payload["missing_from_github"]),
            file=sys.stderr,
        )
        return 2
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog) if args.catalog else default_catalog()
    items = select_repos(catalog, args.only or None)
    results = sync_all(items)
    payload = results_to_dict(results)
    if args.out:
        write_json(args.out, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if any(not r.ok for r in results):
        return 1
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog) if args.catalog else default_catalog()
    item = catalog.in_scope_by_id(args.repo)
    sync_payload = read_json(args.sync) if args.sync else None
    read_path = None
    sha = ""
    if sync_payload:
        for row in sync_payload.get("repos") or []:
            if row.get("repo_id") == item.id:
                if not row.get("ok"):
                    print("collect: sync failed for {0}: {1}".format(item.id, row.get("error")), file=sys.stderr)
                    return 1
                read_path = Path(row["read_path"])
                sha = row.get("audited_sha") or ""
                break
        if read_path is None:
            print("collect: {0} missing from --sync file".format(item.id), file=sys.stderr)
            return 1
    if read_path is None:
        read_path = item.local_path
    ctx = collect_context(item.id, item.github, read_path, sha)
    if args.out:
        write_json(args.out, ctx)
    print(json.dumps(ctx, indent=2, sort_keys=True))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.report).read_text(encoding="utf-8"))
    try:
        validate_or_raise(payload)
    except ValidationError as exc:
        for err in exc.errors:
            print(err, file=sys.stderr)
        return 1
    print("ok {0}".format(args.report))
    return 0


def cmd_ledger(args: argparse.Namespace) -> int:
    current = args.current
    if args.prior:
        prior = args.prior
    else:
        try:
            prior = latest_completed_run(args.runs_root or runs_dir(), exclude=current)
        except FileNotFoundError as exc:
            payload = {
                "prior": None,
                "current": str(current),
                "still_open": [],
                "gone": [],
                "new": [],
                "counts": {"still_open": 0, "gone": 0, "new": 0},
                "note": str(exc),
            }
            if args.out:
                write_json(args.out, payload)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
    payload = compare_runs(current, prior)
    if args.out:
        write_json(args.out, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_walk_step(args: argparse.Namespace) -> int:
    if args.snapshot is not None:
        snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    else:
        snapshot = json.loads(sys.stdin.read() or "{}")
    if not isinstance(snapshot, dict):
        print("walk-step: snapshot must be an object", file=sys.stderr)
        return 1
    if args.now:
        snapshot["now"] = args.now
    if "now" not in snapshot:
        print("walk-step: snapshot needs now (ISO timestamp)", file=sys.stderr)
        return 1
    try:
        state = load_walk(args.run_dir)
    except FileNotFoundError as exc:
        print("walk-step: {0}".format(exc), file=sys.stderr)
        return 1
    kill_override = None
    need_kill_policy = False
    try:
        pol = load_policy()
        resolved = pol.resolved_kill(override=args.kill)
        if resolved is None:
            need_kill_policy = True
            kill_override = "none"
        else:
            kill_override = resolved
            snapshot.setdefault("stall_seconds", pol.stall_seconds)
    except PolicyError as exc:
        print("walk-step: {0}".format(exc), file=sys.stderr)
        return 1
    if args.kill:
        kill_override = parse_kill(args.kill)
        need_kill_policy = False
    from datetime import datetime as _dt

    now = _dt.fromisoformat(str(snapshot["now"]).replace("Z", "+00:00")) if snapshot.get("now") else None
    try:
        actions = walk_step(state, snapshot, now=now, kill_override=kill_override)
    except (ValueError, PolicyError) as exc:
        print("walk-step: {0}".format(exc), file=sys.stderr)
        return 1
    actions["need_kill_policy"] = need_kill_policy
    save_walk(args.run_dir, state)
    print(json.dumps(actions, indent=2, sort_keys=True))
    return 0


def cmd_walk_status(args: argparse.Namespace) -> int:
    try:
        state = load_walk(args.run_dir)
    except FileNotFoundError as exc:
        print("walk-status: {0}".format(exc), file=sys.stderr)
        return 1
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0


def cmd_pdf(args: argparse.Namespace) -> int:
    dest = args.out or pdf_path(args.run_dir, args.from_ver, args.to_ver)
    built = build_pdf(
        args.run_dir,
        dest,
        from_ver=args.from_ver,
        to_ver=args.to_ver,
        day=args.date,
    )
    print(built)
    return 0


def cmd_send_grok(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog) if args.catalog else default_catalog()
    root = repo_root()
    ids = list(args.only or [])
    frm = args.from_ver
    to = args.to_ver
    if not ids:
        queued = load_queue(queue_path(root))
        if queued is None or not queued.get("ids"):
            print(
                "send-grok: empty queue; pass --only or Save ids in the console",
                file=sys.stderr,
            )
            return 1
        ids = list(queued.get("ids") or [])
        frm = frm or queued.get("from_version")
        to = to or queued.get("to_version")
    if not frm or not to:
        print("send-grok: --from and --to are required", file=sys.stderr)
        return 1
    try:
        ids = validate_ids(catalog, ids)
        sent = launch_send(from_version=str(frm), to_version=str(to), ids=ids, cwd=root)
    except (SendGrokError, QueueError) as exc:
        print("send-grok: {0}".format(exc), file=sys.stderr)
        return 1
    print(sent["prompt"])
    print(sent["script"])
    return 0


def cmd_repo_pdf(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog) if args.catalog else default_catalog()
    runs = args.runs_root or runs_dir(repo_root())
    try:
        report = load_repo_report(catalog, runs, args.repo)
    except KeyError as exc:
        print("repo-pdf: {0}".format(exc), file=sys.stderr)
        return 1
    if report is None:
        print("repo-pdf: no report for {0}".format(args.repo), file=sys.stderr)
        return 1
    name = safe_repo_filename(args.repo)
    dest = args.out or (isolated_tmp() / "upgrade-audit" / "repo-pdfs" / "upgrade-audit-{0}.pdf".format(name))
    built = build_repo_pdf(report, dest)
    print(built)
    return 0


def cmd_init_run(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog) if args.catalog else default_catalog()
    day = args.date or date.today().isoformat()
    try:
        path = allocate_run_dir(
            args.from_ver,
            args.to_ver,
            day=day,
            resume=args.resume,
        )
    except FileNotFoundError as exc:
        print("init-run: {0}".format(exc), file=sys.stderr)
        return 1
    root = repo_root()
    if args.catalog:
        catalog_src = args.catalog
        root = args.catalog.resolve().parents[1] if args.catalog.name == "repos.yaml" else root
    else:
        catalog_src = catalog_path()
    if args.resume:
        manifest = path / "manifest.json"
        if not manifest.is_file():
            print("init-run: resume needs an existing manifest.json", file=sys.stderr)
            return 1
        existing = read_json(manifest)
        repos = list(existing.get("repos") or [])
        source = "resume"
    else:
        try:
            repos, source = resolve_requested(
                catalog,
                only=args.only,
                walk_all=bool(args.walk_all),
                walk=getattr(args, "walk", None),
                root=root,
            )
        except QueueError as exc:
            print("init-run: {0}".format(exc), file=sys.stderr)
            return 1
        excluded = [{"github": e.github, "reason": e.reason} for e in catalog.excluded]
        write_json(path / "excluded.json", excluded)
        shutil.copy2(catalog_src, path / "catalog_snapshot.yaml")
        write_manifest(
            path,
            {
                "from_version": args.from_ver,
                "to_version": args.to_ver,
                "date": day,
                "status": "in_progress",
                "repos": repos,
                "scope_source": source,
            },
        )
    print("scope={0} n={1}".format(source, len(repos)), file=sys.stderr)
    try:
        pol = load_policy()
        kill = pol.resolved_kill() or "none"
        stall = pol.stall_seconds
    except PolicyError:
        kill = "none"
        stall = STALL_SECONDS_DEFAULT
    seed_walk(
        path,
        repos,
        kill=kill,
        stall_seconds=stall,
        resume=args.resume,
    )
    print(path)
    return 0


def _policy_public() -> dict:
    try:
        pol = load_policy()
    except PolicyError:
        return {}
    return {
        "mode": pol.resolved_mode(),
        "kill": pol.resolved_kill(),
        "stall_seconds": pol.stall_seconds,
    }


def cmd_board(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog) if args.catalog else default_catalog()
    root = repo_root()
    runs = args.runs_root or runs_dir(root)
    try:
        queued = load_queue(queue_path(root))
    except QueueError as exc:
        print("board: {0}".format(exc), file=sys.stderr)
        return 1
    payload = project_board(
        catalog,
        runs_root=runs,
        queue=queued,
        policy=_policy_public(),
    )
    payload["command"] = grok_command(
        payload.get("from_version"),
        payload.get("to_version"),
        (queued or {}).get("ids") or [],
    )
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.out and str(args.out) != "-":
        write_json(args.out, json.loads(text))
        print(args.out)
    else:
        print(text)
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog) if args.catalog else default_catalog()
    root = repo_root()
    path = queue_path(root)
    actions = [bool(args.clear), bool(args.suggest), args.set_ids is not None]
    if sum(1 for x in actions if x) > 1:
        print("queue: pass only one of --set, --clear, --suggest", file=sys.stderr)
        return 1
    if args.clear:
        clear_queue(path)
        print(json.dumps({"present": False, "cleared": True}, indent=2))
        return 0
    walk = (getattr(args, "walk", None) or "").strip() or None
    if args.suggest:
        runs = args.runs_root or runs_dir(root)
        try:
            queued = load_queue(path)
        except QueueError as exc:
            print("queue: {0}".format(exc), file=sys.stderr)
            return 1
        board = project_board(catalog, runs_root=runs, queue=queued, policy=_policy_public())
        if catalog.walks is not None:
            name = walk or catalog.walks.default
            if name not in catalog.walks.by_id:
                print(
                    "queue: unknown --walk {0} (have {1})".format(name, ", ".join(catalog.walks.order)),
                    file=sys.stderr,
                )
                return 1
            board = dict(board)
            board["repos"] = [
                row
                for row in board["repos"]
                if catalog.effective_walk(catalog.in_scope_by_id(row["id"])) == name
            ]
        elif walk:
            print("queue: this catalog has no walks.yaml; omit --walk", file=sys.stderr)
            return 1
        try:
            ids = suggest_ids(board, args.suggest)
        except ValueError as exc:
            print("queue: {0}".format(exc), file=sys.stderr)
            return 1
        frm = args.from_ver or (queued or {}).get("from_version") or board.get("from_version")
        to = args.to_ver or (queued or {}).get("to_version") or board.get("to_version")
        try:
            payload = save_queue(
                path,
                ids,
                from_version=str(frm or ""),
                to_version=str(to or ""),
                reason=args.suggest,
                catalog=catalog,
            )
        except QueueError as exc:
            print("queue: {0}".format(exc), file=sys.stderr)
            return 1
        print(json.dumps({"present": True, **payload}, indent=2, sort_keys=True))
        return 0
    if args.set_ids is not None:
        frm = args.from_ver
        to = args.to_ver
        if not frm or not to:
            existing = None
            try:
                existing = load_queue(path)
            except QueueError:
                existing = None
            board = None
            if not frm or not to:
                runs = args.runs_root or runs_dir(root)
                board = project_board(catalog, runs_root=runs, queue=existing)
            frm = frm or (existing or {}).get("from_version") or (board or {}).get("from_version")
            to = to or (existing or {}).get("to_version") or (board or {}).get("to_version")
        try:
            set_ids = list(args.set_ids)
            if walk:
                set_ids = require_walk(catalog, validate_ids(catalog, set_ids), walk)
            payload = save_queue(
                path,
                set_ids,
                from_version=str(frm or ""),
                to_version=str(to or ""),
                reason=args.reason or "",
                catalog=catalog,
            )
        except QueueError as exc:
            print("queue: {0}".format(exc), file=sys.stderr)
            return 1
        print(json.dumps({"present": True, **payload}, indent=2, sort_keys=True))
        return 0
    try:
        payload = public_payload(path)
    except QueueError as exc:
        print("queue: {0}".format(exc), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("present") else 2


def cmd_console(args: argparse.Namespace) -> int:
    root = repo_root()
    app_file = root / "console" / "app.py"
    if not app_file.is_file():
        print(
            "console: this tree has no console/ (operator checkout only; not in the public plugin zip)",
            file=sys.stderr,
        )
        return 1
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from console.app import serve
    except ImportError as exc:
        print("console: {0}".format(exc), file=sys.stderr)
        print("console: pip install -e '.[console]'", file=sys.stderr)
        return 1
    host = args.host
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("console: warning: bind {0} is not loopback".format(host), file=sys.stderr)
    serve(host=host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="upgrade-audit")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("print-root", help="Print the pack checkout this device should use")
    s.set_defaults(func=cmd_print_root)

    s = sub.add_parser("install-skill", help="Copy /upgrade-audit into GROK_HOME and record the pack root")
    s.add_argument("--root", type=Path, default=None)
    s.add_argument("--mode", choices=list(MODES), default=None)
    s.add_argument("--kill", choices=list(KILLS), default=None)
    s.add_argument("--stall-seconds", type=int, default=None)
    s.add_argument(
        "--ask-each-run",
        action="store_true",
        help="Do not save a default mode; the skill asks audit / fix / pr every run",
    )
    s.add_argument(
        "--ask-kill-each-run",
        action="store_true",
        help="Do not save a default kill policy; the skill asks none / stall every run",
    )
    s.set_defaults(func=cmd_install_skill)

    s = sub.add_parser(
        "configure",
        help="Set or print this device's action mode and child-kill policy",
    )
    s.add_argument("--mode", choices=list(MODES), default=None)
    s.add_argument("--kill", choices=list(KILLS), default=None)
    s.add_argument("--stall-seconds", type=int, default=None)
    s.add_argument("--ask-each-run", action="store_true")
    s.add_argument("--ask-kill-each-run", action="store_true")
    s.set_defaults(func=cmd_configure)

    s = sub.add_parser("doctor", help="Check this device can run a model-upgrade audit")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("write-schemas")
    s.set_defaults(func=cmd_write_schemas)

    s = sub.add_parser("init-run")
    _add_catalog(s)
    _add_only(s)
    _add_walk(s)
    s.add_argument("--from", dest="from_ver", required=True)
    s.add_argument("--to", dest="to_ver", required=True)
    s.add_argument("--date", default=None)
    s.add_argument("--resume", action="store_true")
    s.add_argument(
        "--all",
        dest="walk_all",
        action="store_true",
        help="Ignore queue.json and walk the default catalog walk (all in-scope ids if walks.yaml is absent)",
    )
    s.set_defaults(func=cmd_init_run)

    s = sub.add_parser("board", help="JSON board over catalog plus last-run findings (no walk)")
    _add_catalog(s)
    s.add_argument("--runs-root", type=Path, default=None)
    s.add_argument("--out", type=Path, default=None)
    s.set_defaults(func=cmd_board)

    s = sub.add_parser("queue", help="Print or write the next-walk queue")
    _add_catalog(s)
    _add_walk(s)
    s.add_argument("--runs-root", type=Path, default=None)
    s.add_argument("--set", nargs="*", dest="set_ids", default=None, help="Replace queue ids")
    s.add_argument("--clear", action="store_true", help="Delete queue.json (catalog default returns)")
    s.add_argument("--suggest", choices=list(SUGGEST_PRESETS), default=None)
    s.add_argument("--from", dest="from_ver", default=None)
    s.add_argument("--to", dest="to_ver", default=None)
    s.add_argument("--reason", default="")
    s.set_defaults(func=cmd_queue)

    s = sub.add_parser("console", help="Localhost decision board (operator tree; not the marketplace zip)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_console)

    s = sub.add_parser("inventory")
    _add_catalog(s)
    s.add_argument("--out", type=Path, default=None)
    s.add_argument(
        "--adopt",
        action="store_true",
        help="Add new owned non-forks to catalog/repos.yaml (in-scope). Auto-exclude new forks.",
    )
    s.set_defaults(func=cmd_inventory)

    s = sub.add_parser("sync")
    _add_catalog(s)
    _add_only(s)
    s.add_argument("--out", type=Path, default=None)
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("collect")
    _add_catalog(s)
    s.add_argument("--repo", required=True)
    s.add_argument("--sync", type=Path, default=None)
    s.add_argument("--out", type=Path, default=None)
    s.set_defaults(func=cmd_collect)

    s = sub.add_parser("validate")
    s.add_argument("report", type=Path)
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("ledger")
    s.add_argument("--current", type=Path, required=True)
    s.add_argument("--prior", type=Path, default=None)
    s.add_argument("--runs-root", type=Path, default=None)
    s.add_argument("--out", type=Path, default=None)
    s.set_defaults(func=cmd_ledger)

    s = sub.add_parser("pdf")
    _add_run(s)
    s.add_argument("--from", dest="from_ver", required=True)
    s.add_argument("--to", dest="to_ver", required=True)
    s.add_argument("--date", default=None)
    s.add_argument("--out", type=Path, default=None)
    s.set_defaults(func=cmd_pdf)

    s = sub.add_parser(
        "send-grok",
        help="Save-or-use the queue and open a new Grok TUI with that walk",
    )
    _add_catalog(s)
    _add_only(s)
    s.add_argument("--from", dest="from_ver", default=None)
    s.add_argument("--to", dest="to_ver", default=None)
    s.set_defaults(func=cmd_send_grok)

    s = sub.add_parser(
        "repo-pdf",
        help="Write a PDF of every confirmed finding for one catalog id (critical, major, minor)",
    )
    _add_catalog(s)
    s.add_argument("--repo", required=True)
    s.add_argument("--runs-root", type=Path, default=None)
    s.add_argument("--out", type=Path, default=None)
    s.set_defaults(func=cmd_repo_pdf)

    s = sub.add_parser("walk-step", help="Non-blocking walk scheduler: snapshot in, next actions out")
    _add_run(s)
    s.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="JSON snapshot (spawned, agents, skip, now). Default: stdin",
    )
    s.add_argument("--kill", choices=list(KILLS), default=None)
    s.add_argument("--now", default=None, help="ISO timestamp override for tests")
    s.set_defaults(func=cmd_walk_step)

    s = sub.add_parser("walk-status", help="Print walk.json for a run")
    _add_run(s)
    s.set_defaults(func=cmd_walk_status)

    _maybe_add_self_audit(sub)
    return p


def _maybe_add_self_audit(sub: argparse._SubParsersAction) -> None:
    """Operator-only. Missing protocol (public plugin tree) omits the command."""
    try:
        from .self_audit import add_cli, available
    except ImportError:
        return
    if not available():
        return
    add_cli(sub)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


def _script_main(cmd: str) -> int:
    """Allow scripts/*.py to inject their subcommand as argv[0] equivalent."""
    return main([cmd, *sys.argv[1:]])
