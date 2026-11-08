"""One command that runs every check, in the order CI runs them. Cross-platform (Windows/macOS/Linux).

    python local/ci.py            # full run: pipeline, export check, dashboard parity, stress test, judge
    python local/ci.py --quick    # skips the stress test; used by the pre-commit hook
    python local/ci.py --judge-only   # only local/judge_check.py (no challenge data needed, ~1 s)

The committed dashboard/data/gilded_ace.json is the Databricks export. This script runs the local
pipeline into it, keeps the fresh copy in local/_work/fresh_export.json, puts the committed file back,
and has the judge compare the two, so running it never leaves the export modified.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "dashboard" / "data" / "gilded_ace.json"
FRESH = ROOT / "local" / "_work" / "fresh_export.json"
PY = sys.executable
steps: list[tuple[str, bool, float]] = []


def run(name: str, cmd: list[str]) -> bool:
    print(f"\n━━ {name} ━━", flush=True)
    t = time.time()
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONWARNINGS": "ignore"}
    ok = subprocess.run(cmd, cwd=ROOT, env=env).returncode == 0
    steps.append((name, ok, time.time() - t))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT.parent / "dashboard-royale" / "data"), help="challenge data folder")
    ap.add_argument("--quick", action="store_true", help="skip the stress test")
    ap.add_argument("--judge-only", action="store_true", help="only the judge guardrails")
    args = ap.parse_args()

    if args.judge_only:
        run("judge guardrails", [PY, "local/judge_check.py"])
    elif not Path(args.data).is_dir():
        print(f"challenge data not found at {args.data}\n"
              "clone it next to this repo: git clone --depth 1 https://github.com/tamu-datathon-org/dashboard-royale.git ../dashboard-royale\n"
              "running the judge guardrails only")
        run("judge guardrails", [PY, "local/judge_check.py"])
    else:
        committed = EXPORT.read_bytes()
        try:
            pipeline_ok = run("pipeline (run_local.py)", [PY, "local/run_local.py", "--data", args.data])
            if pipeline_ok:
                FRESH.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(EXPORT, FRESH)
        finally:
            EXPORT.write_bytes(committed)  # the committed (Databricks) export is what judges see
        run("dashboard parity (check_dashboard.js)", ["node", "local/check_dashboard.js"])
        if pipeline_ok and not args.quick:
            run("stress test", [PY, "local/stress_test.py", "--data", args.data])
        run("judge guardrails", [PY, "local/judge_check.py"] + (["--fresh", str(FRESH)] if pipeline_ok else []))

    print("\n━━ summary ━━")
    for name, ok, secs in steps:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  ({secs:.0f}s)")
    failed = [n for n, ok, _ in steps if not ok]
    print("all checks passed" if not failed else f"{len(failed)} step(s) failed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
