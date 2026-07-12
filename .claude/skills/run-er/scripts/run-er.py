#!/usr/bin/env python3
"""
run-er — Expert Review runner for ThreatAssessor.

Streams the expert review SSE endpoint and prints a clean live summary.
Supports three modes:
  (default)       sequential: 3 core critics (Architect, Tester, Red Team)
  --full          full_moe:   5 critics + ScrumMaster (Plan-Actionable data)
  --critic <name> single:     one critic or SM on an existing MoE result

Usage:
  python3 run-er.py 04_zero_trust
  python3 run-er.py 04_zero_trust --full
  python3 run-er.py 04_zero_trust --critic purple_team
  python3 run-er.py 04_zero_trust --critic scrum_master
  python3 run-er.py 04_zero_trust --mode parallel
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────

API_BASE   = "http://localhost:8000"
_REPO_ROOT = Path(__file__).resolve().parents[4]
REPORT_DIR = _REPO_ROOT / "report"

CRITIC_LABELS = {
    "architect":    "Architect  ",
    "tester":       "Tester     ",
    "red_team":     "Red Team   ",
    "purple_team":  "Purple Team",
    "blackhat":     "Blackhat   ",
    "scrum_master": "ScrumMaster",
    "synthesis":    "Synthesis  ",
}

STATUS_ICON = {
    "PASS":        "✅",
    "MINOR_GAPS":  "⚠️ ",
    "MAJOR_GAPS":  "❌",
    "CRITICAL":    "🔴",
}

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"
BLUE   = "\033[34m"


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_api_key() -> str:
    env_path = _REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("API_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    key = os.getenv("TM_API_KEY", "")
    if not key:
        print(f"{RED}✗ TM-API-KEY not found in .env or TM_API_KEY env var{RESET}")
        sys.exit(1)
    return key


def check_api_running():
    try:
        requests.get(f"{API_BASE}/health", timeout=3)
    except Exception:
        print(f"{RED}✗ API server not running. Start it:{RESET}")
        print(f"  {DIM}./scripts/api/api_start.sh{RESET}")
        sys.exit(1)


def check_report_exists(arch: str):
    gt = REPORT_DIR / arch / "ground_truth.json"
    if not gt.exists():
        print(f"{RED}✗ No analysis found for '{arch}'{RESET}")
        print(f"  {DIM}Run analysis first from dashboard or:{RESET}")
        print(f"  {DIM}python3 -m chatbot.main --gen-arch-truth tests/data/architectures/{arch}.mmd{RESET}")
        sys.exit(1)


def score_color(score: int) -> str:
    if score >= 80: return GREEN
    if score >= 60: return YELLOW
    return RED


def bar(score: int, width: int = 24) -> str:
    filled = round(score / 100 * width)
    return f"{'█' * filled}{'░' * (width - filled)}"


# ── SSE stream consumer ────────────────────────────────────────────────────────

def stream_sse(url: str, api_key: str):
    """Yield (event_type, data_dict) pairs from a streaming SSE endpoint."""
    headers = {"TM-API-KEY": api_key, "Accept": "text/event-stream"}
    event_type = "message"
    buf = ""
    with requests.get(url, headers=headers, stream=True, timeout=300) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        for chunk in resp.iter_content(chunk_size=512, decode_unicode=True):
            buf += chunk
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.rstrip("\r")
                if not line:
                    event_type = "message"
                    continue
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str:
                        try:
                            yield event_type, json.loads(data_str)
                        except json.JSONDecodeError:
                            yield event_type, {"raw": data_str}


# ── Renderers ─────────────────────────────────────────────────────────────────

def render_critic_result(d: dict):
    critic    = d.get("critic", "?")
    label     = CRITIC_LABELS.get(critic, critic.ljust(11))
    status    = d.get("validation_status", "?")
    score     = d.get("score", 0)
    adj       = d.get("confidence_adjustment_pct", 0)
    gaps      = d.get("gap_count", 0)
    strengths = d.get("strength_count", 0)
    icon      = STATUS_ICON.get(status, "  ")
    adj_str   = f"{adj:+.1f}%" if adj != 0 else "  0.0%"
    adj_col   = GREEN if adj >= 0 else YELLOW if adj > -5 else RED
    sc_col    = score_color(score)

    print(f"  {icon} {BOLD}{label}{RESET}  "
          f"score={sc_col}{score:3d}{RESET}  "
          f"adj={adj_col}{adj_str}{RESET}  "
          f"gaps={gaps}  strengths={strengths}")

    for g in d.get("top_gaps", [])[:2]:
        sev  = g.get("severity", "")
        desc = g.get("description", "")[:90]
        sev_col = RED if sev == "CRITICAL" else YELLOW if sev in ("HIGH", "MEDIUM") else DIM
        print(f"      {sev_col}▸ [{sev}]{RESET} {DIM}{desc}…{RESET}")


def render_complete(d: dict):
    conf  = d.get("confidence", {})
    final = conf.get("final", d.get("final_confidence", 0))
    base  = conf.get("base", 0)
    delta = final - base if base else 0
    delta_str = f"{delta:+.1f}pp" if delta else ""
    delta_col = GREEN if delta >= 0 else YELLOW if delta > -5 else RED

    crit_items = len(d.get("critical_recommendations", []))
    high_items = len([r for r in d.get("recommendations", []) if r.get("priority") == "HIGH"])
    fc_col = score_color(int(final))

    print()
    print(f"  {BOLD}Final confidence:{RESET}  {fc_col}{final:.1f}%{RESET}  "
          f"{delta_col}({delta_str}){RESET}  {bar(int(final))}")
    print(f"  Critical items:   {RED if crit_items else DIM}{crit_items}{RESET}")
    print(f"  High-priority:    {YELLOW if high_items else DIM}{high_items}{RESET}")


def render_scrum_result(d: dict):
    items = d.get("action_plan", [])
    conf  = d.get("final_confidence", 0)
    note  = (d.get("synthesis_note") or "")[:120]
    print(f"  {BOLD}ScrumMaster:{RESET}  {len(items)} action items  "
          f"final confidence → {GREEN}{conf:.1f}%{RESET}")
    if note:
        print(f"  {DIM}{note}…{RESET}")
    for item in items[:3]:
        title    = (item.get("title") or item.get("action") or "?")[:70]
        priority = item.get("priority", "")
        effort   = item.get("effort", "")
        pcol = RED if priority == "CRITICAL" else YELLOW if priority == "HIGH" else DIM
        print(f"    {pcol}[{priority}]{RESET} {title}  {DIM}{effort}{RESET}")


# ── Run modes ─────────────────────────────────────────────────────────────────

def run_full_pipeline(arch: str, critic_mode: str, api_key: str):
    url = f"{API_BASE}/api/v1/expert-review?architecture_name={arch}&critic_mode={critic_mode}"
    print(f"\n{BOLD}{CYAN}Expert Review — {arch}{RESET}  {DIM}[mode: {critic_mode}]{RESET}")
    print(f"{DIM}{'─' * 60}{RESET}")

    last_stage = None
    start = time.time()

    try:
        for event, data in stream_sse(url, api_key):
            if event == "progress":
                stage = data.get("stage", "")
                msg   = data.get("message", "")
                pct   = data.get("progress", 0)
                if stage != last_stage and stage not in ("complete",):
                    stage_label = CRITIC_LABELS.get(stage, stage).strip()
                    print(f"\n{BLUE}▸ {stage_label}{RESET}")
                    last_stage = stage
                if stage == "synthesis" and pct < 97:
                    print(f"  {DIM}{msg}{RESET}")

            elif event == "critic_result":
                render_critic_result(data)

            elif event == "complete":
                print(f"\n{DIM}{'─' * 60}{RESET}")
                render_complete(data)
                sm = data.get("scrum_master")
                if sm:
                    print()
                    render_scrum_result(sm)

            elif event == "error":
                print(f"\n{RED}✗ Error: {data.get('detail', data)}{RESET}")
                sys.exit(1)

    except RuntimeError as e:
        print(f"\n{RED}✗ {e}{RESET}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted — cancelling review…{RESET}")
        _cancel(arch, api_key)
        sys.exit(130)

    elapsed = time.time() - start
    print(f"\n  {DIM}Elapsed: {elapsed:.0f}s{RESET}")
    print(f"{DIM}{'─' * 60}{RESET}\n")


def run_single_critic(arch: str, critic: str, api_key: str):
    url = f"{API_BASE}/api/v1/run-critic?architecture_name={arch}&critic={critic}"
    label = CRITIC_LABELS.get(critic, critic).strip()
    print(f"\n{BOLD}{CYAN}Single Critic — {label} on {arch}{RESET}")
    print(f"{DIM}{'─' * 60}{RESET}\n")

    try:
        for event, data in stream_sse(url, api_key):
            if event == "progress":
                print(f"  {DIM}{data.get('message', '')}{RESET}")
            elif event == "critic_result":
                render_critic_result(data)
            elif event == "complete":
                print(f"\n{DIM}{'─' * 60}{RESET}")
                if critic == "scrum_master":
                    render_scrum_result(data.get("scrum_master", data))
                elif "validation_status" in data:
                    render_critic_result(data)
                else:
                    render_complete(data)
            elif event == "error":
                print(f"\n{RED}✗ {data.get('detail', data)}{RESET}")
                sys.exit(1)
    except RuntimeError as e:
        print(f"\n{RED}✗ {e}{RESET}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted.{RESET}")
        sys.exit(130)

    print()


def _cancel(arch: str, api_key: str):
    try:
        requests.delete(
            f"{API_BASE}/api/v1/expert-review/cancel?architecture_name={arch}",
            headers={"TM-API-KEY": api_key},
            timeout=5,
        )
    except Exception:
        pass


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run Expert Review on a ThreatAssessor architecture.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 04_zero_trust                        # 3 core critics (sequential)
  %(prog)s 04_zero_trust --full                 # 5 critics + ScrumMaster
  %(prog)s 04_zero_trust --mode parallel        # 3 core critics in parallel
  %(prog)s 04_zero_trust --critic red_team      # Re-run Red Team only
  %(prog)s 04_zero_trust --critic scrum_master  # SM only (needs 07_moe_orchestrator.json)
        """,
    )
    parser.add_argument("arch", help="Architecture name (must match report/ directory)")
    parser.add_argument("--full", action="store_true",
                        help="Full MoE: 5 critics + ScrumMaster (generates Plan-Actionable data)")
    parser.add_argument("--critic", metavar="NAME",
                        choices=["architect", "tester", "red_team",
                                 "purple_team", "blackhat", "scrum_master"],
                        help="Run a single critic instead of the full pipeline")
    parser.add_argument("--mode", metavar="MODE", default="partial_parallel",
                        choices=["sequential", "partial_parallel", "parallel", "auto"],
                        help="Critic execution mode (default: partial_parallel). "
                             "sequential=full cross-reference; partial_parallel=Architect+RedTeam concurrent (recommended); "
                             "parallel=all critics blind; auto=complexity-adaptive")

    args = parser.parse_args()

    api_key = load_api_key()
    check_api_running()
    check_report_exists(args.arch)

    if args.critic:
        run_single_critic(args.arch, args.critic, api_key)
    else:
        mode = args.mode  # --full uses the selected mode (default: partial_parallel)
        run_full_pipeline(args.arch, mode, api_key)


if __name__ == "__main__":
    main()
