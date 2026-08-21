#!/bin/sh
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src:$ROOT"
python3 -m pytest tests -q
python3 -m upgrade_audit write-schemas
python3 - <<'PY'
import os
from pathlib import Path
from upgrade_audit.pdf import build_pdf
from upgrade_audit.paths import isolated_tmp
from tests.test_pdf import _write_mini
run = isolated_tmp() / "upgrade-audit-fixture-run"
if run.exists():
    import shutil
    shutil.rmtree(run)
_write_mini(run)
dest = isolated_tmp() / "upgrade-audit-fixture.pdf"
build_pdf(run, dest, from_ver="4.5", to_ver="4.6", day="2026-08-17")
print(dest)
PY
