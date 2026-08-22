#!/usr/bin/env python3
"""
qualify-corpus — thin wrapper; delegates to bench_critics.py --qualify.
Invoked by the /qualify-corpus skill.
"""
import subprocess, sys
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent.parent.parent.parent
script = ROOT / "scripts" / "bench_critics.py"

mode = sys.argv[1] if len(sys.argv) > 1 else "critics"
subprocess.run([sys.executable, str(script), "--qualify", "--mode", mode], check=False)
