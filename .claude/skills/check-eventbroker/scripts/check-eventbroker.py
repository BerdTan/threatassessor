#!/usr/bin/env python3
"""
check-eventbroker — EventBroker + Sink regression + live status check.

Usage:
    python3 check-eventbroker.py                      # unit tests only
    python3 check-eventbroker.py 21_agentic_ai_system # tests + live status
    python3 check-eventbroker.py --all                # tests + all corpus archs
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[4]
REPORT_DIR = REPO_ROOT / "report"
TEST_FILE  = REPO_ROOT / "tests" / "test_harness_event_broker.py"
POLICY     = REPO_ROOT / "policies" / "agent_governance.yaml"
SIEM_LOG   = REPO_ROOT / "logs" / "siem.jsonl"

GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"
CYAN   = lambda s: f"\033[36m{s}\033[0m"


# ── Unit test runner ──────────────────────────────────────────────────────────

def run_unit_tests() -> bool:
    print(f"\n{BOLD(CYAN('EventBroker Regression'))} — {DIM(str(TEST_FILE.relative_to(REPO_ROOT)))}")
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TEST_FILE), "-v", "--tb=short", "-q"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    elapsed = time.time() - t0

    output = result.stdout + result.stderr
    summary_line = next(
        (l for l in reversed(output.splitlines()) if "passed" in l or "failed" in l or "error" in l),
        "no output"
    )

    if result.returncode == 0:
        print(f"  {GREEN(summary_line.strip())}  ({elapsed:.1f}s)")
    else:
        print(f"  {RED(summary_line.strip())}  ({elapsed:.1f}s)")
        for line in output.splitlines():
            if line.startswith("FAILED") or line.startswith("ERROR"):
                print(f"  {RED(line)}")

    return result.returncode == 0


# ── Live broker status ────────────────────────────────────────────────────────

def _load_policy() -> dict:
    if not POLICY.exists():
        return {}
    try:
        import yaml
        with open(POLICY) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _sink_status(sinks_cfg: dict, name: str) -> str:
    cfg = sinks_cfg.get(name, {})
    if not cfg.get("enabled"):
        return DIM("disabled")
    extra = ""
    if name == "siem":
        extra = f"  → {cfg.get('sink_path', 'logs/siem.jsonl')}"
    elif name == "langfuse":
        host = cfg.get("host", "http://localhost:3000")
        extra = f"  → {host}"
    elif name == "webhook":
        url = cfg.get("url", "")
        extra = f"  → {url}" if url else "  (no url set)"
    return GREEN("enabled") + DIM(extra)


def show_live_status(arch: str) -> None:
    policy = _load_policy()
    eb_cfg = policy.get("event_broker", {})
    sinks_cfg = eb_cfg.get("sinks", {})

    # Determine overall enabled state
    any_sink_enabled = any(
        v.get("enabled", False) for v in sinks_cfg.values() if isinstance(v, dict)
    )
    broker_status = GREEN("enabled") if any_sink_enabled else AMBER("disabled (no sinks enabled)")
    verbosity = eb_cfg.get("verbosity", "standard")

    print(f"\n{BOLD('Live Broker Status')} — {arch}")
    print(f"  broker:   {broker_status}  {DIM('verbosity=' + verbosity)}")
    print(f"  siem:     {_sink_status(sinks_cfg, 'siem')}")
    print(f"  langfuse: {_sink_status(sinks_cfg, 'langfuse')}")
    print(f"  webhook:  {_sink_status(sinks_cfg, 'webhook')}")

    # Last SIEM events (global log, not per-arch)
    if SIEM_LOG.exists():
        try:
            lines = SIEM_LOG.read_text().strip().splitlines()
            recent = [json.loads(l) for l in lines[-5:] if l.strip()]
            if recent:
                print(f"\n  {DIM('Last SIEM events (logs/siem.jsonl):')}")
                for rec in reversed(recent):
                    ts    = rec.get("ts", rec.get("timestamp", "?"))[:19]
                    etype = rec.get("event_type", "?")
                    sev   = rec.get("overall_severity", rec.get("severity", ""))
                    blk   = "  blocked=True" if rec.get("blocked") else ""
                    arch_tag = rec.get("architecture", rec.get("arch", ""))
                    arch_str = f"  {DIM(arch_tag)}" if arch_tag else ""
                    sev_str  = f"  {_sev_color(sev)}" if sev else ""
                    print(f"    [{DIM(ts)}] {etype:<30}{sev_str}{blk}{arch_str}")
            else:
                print(f"\n  {DIM('siem.jsonl exists but is empty')}")
        except Exception as e:
            print(f"\n  {AMBER(f'siem.jsonl parse error: {e}')}")
    else:
        print(f"\n  {DIM('logs/siem.jsonl not found — broker may not have run or SIEM sink is disabled')}")


def _sev_color(sev: str) -> str:
    s = (sev or "").upper()
    if s in ("CRITICAL", "HIGH"): return RED(s)
    if s == "MEDIUM": return AMBER(s)
    return GREEN(s) if s == "LOW" else DIM(s)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EventBroker regression + live status")
    parser.add_argument("arch", nargs="?", help="Architecture name for live status")
    parser.add_argument("--all", action="store_true", help="Show live status for all corpus archs")
    args = parser.parse_args()

    ok = run_unit_tests()

    if args.arch:
        show_live_status(args.arch)
    elif args.all:
        archs = sorted(
            d.name for d in REPORT_DIR.iterdir()
            if d.is_dir() and (d / "ground_truth.json").exists()
        )
        if not archs:
            print(f"\n  {DIM('No architectures found under report/')}")
        else:
            for arch in archs:
                show_live_status(arch)
    else:
        # No arch arg — just show global broker config summary
        policy = _load_policy()
        eb_cfg = policy.get("event_broker", {})
        sinks_cfg = eb_cfg.get("sinks", {})
        any_enabled = any(v.get("enabled", False) for v in sinks_cfg.values() if isinstance(v, dict))
        print(f"\n{BOLD('Broker Config')} — {DIM(str(POLICY.relative_to(REPO_ROOT)))}")
        print(f"  siem:     {_sink_status(sinks_cfg, 'siem')}")
        print(f"  langfuse: {_sink_status(sinks_cfg, 'langfuse')}")
        print(f"  webhook:  {_sink_status(sinks_cfg, 'webhook')}")
        if not any_enabled:
            print(f"  {AMBER('No sinks enabled — broker will not emit events')}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
