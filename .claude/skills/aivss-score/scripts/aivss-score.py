#!/usr/bin/env python3
"""
aivss-score.py — Run AIVSS v4 scorer on a report directory and print full breakdown.

Usage:
    python3 aivss-score.py                    # most recent report in report/
    python3 aivss-score.py 00_serviceentry_3  # named architecture
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

SEV_COLOR = {"CRITICAL": red, "HIGH": yellow, "MEDIUM": yellow, "LOW": green}


def _sev(s):
    if not s: return dim("—")
    return SEV_COLOR.get(s, str)(s)


def _score_color(v):
    if v is None: return dim("—")
    if v >= 7.0: return red(f"{v:.2f}")
    if v >= 4.0: return yellow(f"{v:.2f}")
    return green(f"{v:.2f}")


def find_report_dir(arch_name: str | None) -> Path:
    base = REPO / "report"
    if arch_name:
        d = base / arch_name
        if not d.is_dir():
            print(f"  ERROR: report directory not found: {d}")
            sys.exit(1)
        return d
    # Most recent by mtime
    dirs = sorted([d for d in base.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
    candidates = [d for d in dirs if (d / "ground_truth.json").exists()]
    if not candidates:
        print("  ERROR: no report directories with ground_truth.json found.")
        sys.exit(1)
    return candidates[0]


def run_scorer(report_dir: Path):
    gt_path  = report_dir / "ground_truth.json"
    gov_path = report_dir / "governance_signals.json"

    if not gt_path.exists():
        print(f"  ERROR: ground_truth.json not found in {report_dir}")
        sys.exit(1)

    gt  = json.loads(gt_path.read_text())
    gov = json.loads(gov_path.read_text()) if gov_path.exists() else {}

    from chatbot.modules.harness_aivss import AIVSSFlowScorer
    from chatbot.config.settings import get_settings
    settings = get_settings()
    scorer   = AIVSSFlowScorer(industry=settings.governance.industry)
    result   = scorer.compute(gov, gt, None, None)
    return result, gov


def print_summary(result, arch_name: str):
    a = result
    print(bold(f"\n=== AIVSS v4 Score — {arch_name} ===\n"))

    # Summary row
    flows = [
        ("🔐 Ingress",  a.inbound),
        ("⚙️  Internal", a.internal),
        ("📤 Egress",   a.outbound),
    ]
    for label, f in flows:
        if f:
            print(f"  {label:<14}  composite {_score_color(f.composite)}  {_sev(f.severity)}  "
                  f"coverage {f.coverage_pct}%")
        else:
            print(f"  {label:<14}  {dim('—')}")

    overall_c = _score_color(a.overall)
    print(f"\n  {'Overall':<14}  {overall_c}  {_sev(a.overall_severity)}")
    print(f"  Industry     {cyan(scorer_industry)}")
    print()


def print_flow_detail(result):
    print(bold("=== Flow Metric Breakdown ===\n"))
    for flow_label, flow_obj in [("Inbound", result.inbound), ("Internal", result.internal), ("Outbound", result.outbound)]:
        if not flow_obj or not flow_obj.metrics:
            print(f"  {flow_label}: {dim('no signals')}")
            continue
        print(f"  {bold(flow_label)}  composite={_score_color(flow_obj.composite)}  coverage={flow_obj.coverage_pct}%")
        for metric_key, m in flow_obj.metrics.items():
            subs = "  ".join(f"{k}={_score_color(v)}" for k, v in (m.sub_scores or {}).items())
            print(f"    {metric_key:<6}  composite={_score_color(m.composite)}  sub_scores: {subs or dim('—')}")
        print()


def print_per_threat(result):
    if not result.per_threat:
        print(dim("  No per-threat scores (MoE not run — run Expert Review to enrich)."))
        return

    print(bold("=== Per-Threat Scores ===\n"))
    header = f"  {'Technique':<12} {'Name':<38} {'Score':<8} {'Severity':<12} {'Top Metric':<10} {'Mitig Mult'}"
    print(header)
    print("  " + "-" * 90)
    for t in sorted(result.per_threat, key=lambda x: -(x.composite or 0)):
        print(f"  {t.technique_id:<12} {(t.technique_name or '')[:37]:<38} "
              f"{_score_color(t.composite):<18} {_sev(t.severity):<22} "
              f"{(t.top_metric or '—'):<10} {t.mitigation_multiplier:.2f}")
    print()


def print_cached_vs_fresh(fresh, cached_gov: dict):
    cached_aivss = (cached_gov.get("aivss") or {})
    cached_overall = (cached_aivss.get("overall") or {})
    if not cached_overall.get("composite"):
        return

    cached_c = cached_overall["composite"]
    fresh_c  = fresh.overall
    delta    = round(fresh_c - cached_c, 3) if fresh_c is not None and cached_c is not None else None

    print(bold("=== Cached vs Fresh Comparison ===\n"))
    print(f"  Cached overall composite : {_score_color(cached_c)}")
    print(f"  Fresh  overall composite : {_score_color(fresh_c)}")
    if delta is not None:
        sign = "+" if delta > 0 else ""
        color = red if delta > 0 else green if delta < 0 else dim
        print(f"  Delta                    : {color(f'{sign}{delta}')}")
    print()


def main():
    arch_arg = sys.argv[1] if len(sys.argv) > 1 else None
    report_dir = find_report_dir(arch_arg)
    arch_name  = report_dir.name

    print(f"  Report: {cyan(str(report_dir))}")

    result, cached_gov = run_scorer(report_dir)

    global scorer_industry
    try:
        from chatbot.config.settings import get_settings
        scorer_industry = get_settings().governance.industry
    except Exception:
        scorer_industry = "unknown"

    print_summary(result, arch_name)
    print_flow_detail(result)
    print_per_threat(result)
    print_cached_vs_fresh(result, cached_gov)

    # Coverage warnings
    low_coverage = []
    for label, f in [("inbound", result.inbound), ("internal", result.internal), ("outbound", result.outbound)]:
        if f and f.coverage_pct < 50:
            low_coverage.append(f"{label} ({f.coverage_pct}%)")
    if low_coverage:
        print(f"  {yellow('⚠  Low signal coverage:')} {', '.join(low_coverage)}")
        print(f"  {dim('Run Expert Review to enrich internal/outbound scores with MoE + SM signals.')}\n")


if __name__ == "__main__":
    main()
