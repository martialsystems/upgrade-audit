#!/usr/bin/env python3
# Copyright (c) 2026 Martial Systems LLC. All rights reserved.
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src")]
from upgrade_audit.cli import _script_main

if __name__ == "__main__":
    raise SystemExit(_script_main("inventory"))
