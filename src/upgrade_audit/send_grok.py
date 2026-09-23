# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
"""Open a new Grok TUI with the queued walk. Does not spawn auditors itself."""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence


class SendGrokError(ValueError):
    pass


def grok_prompt(from_version: str, to_version: str, ids: Sequence[str]) -> str:
    frm = (from_version or "").strip()
    to = (to_version or "").strip()
    if not frm or not to:
        raise SendGrokError("from_version and to_version are required")
    parts = ["/upgrade-audit", "--from", frm, "--to", to]
    for raw in ids:
        rid = str(raw).strip()
        if not rid:
            raise SendGrokError("queue id must be a non-empty string")
        parts.extend(["--only", rid])
    return " ".join(parts)


def find_grok() -> Path:
    env = os.environ.get("GROK_BIN", "").strip()
    candidates = []
    if env:
        candidates.append(Path(os.path.expanduser(env)))
    which = shutil.which("grok")
    if which:
        candidates.append(Path(which))
    candidates.append(Path.home() / ".grok" / "bin" / "grok")
    seen = set()
    for path in candidates:
        resolved = path
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file() and os.access(path, os.X_OK):
            return path
    raise SendGrokError("grok not found on PATH or ~/.grok/bin/grok")


def write_launch_script(script: Path, *, grok: Path, cwd: Path, prompt: str) -> Path:
    script = Path(script)
    script.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "#!/bin/bash\n"
        "# Copyright (c) 2026 Martial Systems LLC. All rights reserved.\n"
        "set -euo pipefail\n"
        "cd {0}\n"
        "exec {1} --cwd {2} {3}\n"
    ).format(
        shlex.quote(str(cwd)),
        shlex.quote(str(grok)),
        shlex.quote(str(cwd)),
        shlex.quote(prompt),
    )
    script.write_text(body, encoding="utf-8")
    os.chmod(script, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    return script


def open_in_terminal(script: Path) -> None:
    script = Path(script)
    if sys.platform == "darwin":
        result = subprocess.run(
            ["open", "-a", "Terminal", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip() or str(result.returncode)
            raise SendGrokError("open Terminal failed: {0}".format(err))
        return
    raise SendGrokError(
        "no Terminal opener on this OS. Run {0}".format(script)
    )


def launch_send(
    *,
    from_version: str,
    to_version: str,
    ids: Sequence[str],
    cwd: Path,
    grok: Optional[Path] = None,
    script: Optional[Path] = None,
    opener: Optional[Callable[[Path], None]] = None,
) -> dict:
    cleaned = [str(x).strip() for x in ids if str(x).strip()]
    if not cleaned:
        raise SendGrokError("tick at least one catalog id; empty queue means walk nothing")
    prompt = grok_prompt(from_version, to_version, cleaned)
    grok_bin = grok or find_grok()
    if script is None:
        from .paths import isolated_tmp

        script = isolated_tmp() / "upgrade-audit" / "send-grok.command"
    path = write_launch_script(script, grok=grok_bin, cwd=Path(cwd), prompt=prompt)
    (opener or open_in_terminal)(path)
    return {
        "ok": True,
        "grok": str(grok_bin),
        "cwd": str(Path(cwd)),
        "prompt": prompt,
        "script": str(path),
        "ids": cleaned,
        "count": len(cleaned),
    }
