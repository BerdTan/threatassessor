#!/usr/bin/env python3
"""
aivss-gate.py — Show per-critic AIVSS gate config and last SIEM event summary.
Reads settings.critics + logs/siem.jsonl (no LLM calls, no side effects).

Usage:
    python3 aivss-gate.py
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))


def _col(t, code): return f"\033[{code}m{t}\033[0m"
def bold(t):   return _col(t, "1")
def green(t):  return _col(t, "32")
def yellow(t): return _col(t, "33")
def red(t):    return _col(t, "31")
def cyan(t):   return _col(t, "36")
def dim(t):    return _col(t, "2")


def _sev_color(s):
    if not s: return dim("—")
    c = {"CRITICAL": red, "HIGH": yellow, "MEDIUM": yellow, "LOW": green}.get(s, str)
    return c(s)


def show_gate_table():
    print(bold("\n=== Per-Critic AIVSS Gate Config ===\n"))
    try:
        from chatbot.config.settings import get_settings
        settings = get_settings()
        critics = settings.critics  # Dict[str, CriticSettings]
    except Exception as e:
        print(f"  Could not load settings: {e}")
        critics = {}

    CRITIC_ORDER = ["architect", "tester", "red_team", "purple_team", "blackhat", "scrum_master"]
    header = f"  {'Critic':<16} {'Allowed Models':<22} {'Allowed Tools':<22} {'Gate Threshold':<16}"
    print(header)
    print("  " + "-" * 76)

    for name in CRITIC_ORDER:
        cfg = critics.get(name)
        if cfg:
            models = ", ".join(cfg.allowed_models) if cfg.allowed_models else "[any]"
            tools  = ", ".join(cfg.allowed_tools)  if cfg.allowed_tools  else "[any]"
            thresh = f"{cfg.max_aivss_score:.1f}" + (" (disabled)" if cfg.max_aivss_score >= 10.0 else " ← active gate")
            thresh_str = dim(thresh) if cfg.max_aivss_score >= 10.0 else yellow(thresh)
        else:
            models, tools, thresh_str = dim("[any]"), dim("[any]"), dim("10.0 (not configured)")

        print(f"  {name:<16} {models:<22} {tools:<22} {thresh_str}")

    print()


def show_agent_model_config():
    print(bold("=== Per-Agent Model Config (HarnessModelGuardian) ===\n"))
    try:
        from chatbot.config.settings import get_settings
        swarm = get_settings().agent_models
    except Exception as e:
        print(f"  Could not load agent_models: {e}\n")
        return

    AGENTS = ["architect", "tester", "red_team", "purple_team", "blackhat",
              "storycaster", "scrum_master", "moe_orchestrator", "threat_analyst"]
    any_configured = False
    for name in AGENTS:
        cfg = getattr(swarm, name, None)
        if cfg and cfg.model:
            any_configured = True
            fallbacks = f" → {', '.join(cfg.fallbacks)}" if cfg.fallbacks else ""
            print(f"  {name:<20} {cyan(cfg.model)}{dim(fallbacks)}")
        else:
            print(f"  {name:<20} {dim('env-var default (not configured)')}")

    if not any_configured:
        print(f"\n  {yellow('No per-agent models configured.')} "
              "All agents use the LLM_PROVIDER env-var default.\n"
              "  To configure: add an 'agent_models' block to chatbot/config/user_config.json\n"
              "  or run: /harness to open the Harness tab → Harness Config section.")
    print()


def show_last_siem():
    print(bold("=== Last SIEM Event ===\n"))
    siem_path = REPO / "logs" / "siem.jsonl"
    if not siem_path.exists():
        print(f"  {dim('No SIEM log found at logs/siem.jsonl — no pipeline run yet.')}\n")
        return

    lines = [l.strip() for l in siem_path.read_text().splitlines() if l.strip()]
    if not lines:
        print(f"  {dim('SIEM log is empty.')}\n")
        return

    try:
        ev = json.loads(lines[-1])
    except json.JSONDecodeError:
        print(f"  {red('Could not parse last SIEM line.')}\n")
        return

    arch  = ev.get("architecture", "—")
    ts    = ev.get("ts", "—")
    run   = ev.get("run_id", "—")
    print(f"  Architecture : {cyan(arch)}")
    print(f"  Timestamp    : {ts}")
    print(f"  Run ID       : {dim(run)}")

    # AIVSS scores
    ai, ii, oi = ev.get("aivss_inbound"), ev.get("aivss_internal"), ev.get("aivss_outbound")
    overall    = ev.get("overall_severity", "—")
    oc         = red if overall == "CRITICAL" else yellow if overall in ("HIGH","MEDIUM") else green
    print(f"\n  AIVSS   "
          f"Inbound {ai if ai is not None else '—'}  "
          f"Internal {ii if ii is not None else '—'}  "
          f"Outbound {oi if oi is not None else '—'}  "
          f"Overall {oc(overall)}")

    # Top threat
    top = ev.get("top_threat", {})
    if top and top.get("technique_id"):
        sc = top.get("aivss_score", "—")
        sv = top.get("severity", "—")
        print(f"\n  Top threat  {cyan(top['technique_id'])}  {top.get('technique_name',''):<40}  "
              f"score {sc}  {_sev_color(sv)}")

    # Governance dims
    dims = ev.get("governance_dims", {})
    if dims:
        row = "  ".join(f"{k}:{_sev_color(v)}" for k,v in sorted(dims.items()))
        print(f"\n  Gov dims    {row}")

    # Tightening advisory
    if ai is not None:
        if ai >= 9.0:
            print(f"\n  {red('⚠  Inbound CRITICAL')} — gate tightened: all non-essential critic tools disabled, forced minimum model.")
        elif ai >= 7.0:
            print(f"\n  {yellow('⚠  Inbound HIGH')} — gate tightened: critic tool calls restricted.")
    print()


def main():
    show_gate_table()
    show_agent_model_config()
    show_last_siem()


if __name__ == "__main__":
    main()
