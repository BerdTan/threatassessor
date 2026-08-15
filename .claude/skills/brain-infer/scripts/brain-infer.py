#!/usr/bin/env python3
"""brain-infer.py — run infer mode against hold-out or all corpus archs, show predictions vs ground truth."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from chatbot.modules.ta_brain_query import query_brain, INSTANCES_PATH
from chatbot.modules.ta_brain_builder import HOLD_OUT_ARCHS, REPORT_DIR, _report_dir

# ── Colour helpers ────────────────────────────────────────────────────────────
def _c(t, code): return f"\033[{code}m{t}\033[0m"
def bold(t):  return _c(t, "1")
def green(t): return _c(t, "92")
def amber(t): return _c(t, "33")
def red(t):   return _c(t, "31")
def grey(t):  return _c(t, "2")
def cyan(t):  return _c(t, "36")


def _pct(num, denom):
    if not denom:
        return grey("n/a")
    p = round(100 * num / denom)
    if p >= 70: return green(f"{p}%")
    if p >= 40: return amber(f"{p}%")
    return red(f"{p}%")


def _conf_color(v):
    if v is None: return grey("n/a")
    if v >= 0.7: return green(f"{v:.2f}")
    if v >= 0.4: return amber(f"{v:.2f}")
    return red(f"{v:.2f}")


def _action_hint(arch_type: str, pub_conf: float, precision_tech: float, precision_ctrl: float) -> str:
    if pub_conf < 0.15:
        return red(f"Published confidence VERY LOW — run brain-grow to add more {arch_type} synthetic instances")
    if pub_conf < 0.4:
        return amber(f"Under-calibrated — run brain-grow to improve {arch_type} benchmark confidence")
    if precision_tech < 0.3 and precision_ctrl < 0.3:
        return amber("Both technique and control predictions are imprecise — more training data needed")
    return green("Predictions within acceptable range")


def _infer_arch(arch_name: str) -> dict:
    arch_dir = REPORT_DIR / arch_name
    gt_path = arch_dir / "ground_truth.json"
    if not gt_path.exists():
        return {"error": f"ground_truth.json not found for {arch_name}"}

    gt = json.loads(gt_path.read_text())
    meta = gt.get("metadata", {})
    arch_type = meta.get("architecture_type", gt.get("arch_type", ""))

    actual_techs = gt.get("techniques", [])
    if isinstance(actual_techs, dict):
        actual_techs = list(actual_techs.keys())
    actual_techs_set = set(actual_techs)

    actual_controls = gt.get("controls_missing", [])
    actual_controls_set = {c.lower() for c in actual_controls}

    result = query_brain(mode="infer", arch_type=arch_type, caller_type="brain-infer")
    preds = result.get("predictions", {})
    pred_techs = set(preds.get("techniques", []))
    pred_controls = {c.lower() for c in preds.get("missing_controls", [])}
    patterns_fired = result.get("patterns_fired", [])
    pub_conf = result.get("confidence", 0)

    tech_hit = len(pred_techs & actual_techs_set)
    ctrl_hit = len(pred_controls & actual_controls_set)

    prec_tech = tech_hit / len(pred_techs) if pred_techs else 0
    prec_ctrl = ctrl_hit / len(pred_controls) if pred_controls else 0
    rec_tech = tech_hit / len(actual_techs_set) if actual_techs_set else 0
    rec_ctrl = ctrl_hit / len(actual_controls_set) if actual_controls_set else 0

    return {
        "arch_name": arch_name,
        "arch_type": arch_type,
        "pub_conf": pub_conf,
        "patterns_fired": patterns_fired,
        "pred_techs": len(pred_techs),
        "actual_techs": len(actual_techs_set),
        "tech_hit": tech_hit,
        "prec_tech": prec_tech,
        "rec_tech": rec_tech,
        "pred_controls": len(pred_controls),
        "actual_controls": len(actual_controls_set),
        "ctrl_hit": ctrl_hit,
        "prec_ctrl": prec_ctrl,
        "rec_ctrl": rec_ctrl,
    }


def _print_arch_result(r: dict):
    if "error" in r:
        print(f"  {red(r['error'])}")
        return
    arch = r["arch_name"]
    arch_type = r["arch_type"]
    conf = _conf_color(r["pub_conf"])
    pat = ", ".join(r["patterns_fired"]) or grey("none")
    print(f"{bold(arch)} ({arch_type})  published_conf={conf}  patterns={pat}")
    print(f"  Techniques — predicted: {r['pred_techs']:3d}  actual: {r['actual_techs']:3d}  "
          f"hit: {r['tech_hit']:3d}  precision: {_pct(r['tech_hit'], r['pred_techs'])}  "
          f"recall: {_pct(r['tech_hit'], r['actual_techs'])}")
    print(f"  Controls   — predicted: {r['pred_controls']:3d}  actual: {r['actual_controls']:3d}  "
          f"hit: {r['ctrl_hit']:3d}  precision: {_pct(r['ctrl_hit'], r['pred_controls'])}  "
          f"recall: {_pct(r['ctrl_hit'], r['actual_controls'])}")
    print(f"  Action: {_action_hint(arch_type, r['pub_conf'], r['prec_tech'], r['prec_ctrl'])}")
    print()


def main():
    ap = argparse.ArgumentParser(description="TA Brain infer — predictions vs ground truth")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--arch", help="single arch name (from report/)")
    grp.add_argument("--hold-out", action="store_true", default=True, help="run against hold-out archs (default)")
    grp.add_argument("--all", action="store_true", help="run against all corpus archs")
    ap.add_argument("--json", action="store_true", dest="json_out", help="output raw JSON")
    args = ap.parse_args()

    if args.arch:
        arch_names = [args.arch]
    elif args.all:
        instances_path = INSTANCES_PATH
        seen = {}
        if instances_path.exists():
            for line in instances_path.read_text().strip().splitlines():
                try:
                    inst = json.loads(line)
                    seen[inst["arch_id"]] = inst
                except Exception:
                    pass
        arch_names = sorted(seen.keys())
    else:
        arch_names = sorted(HOLD_OUT_ARCHS)

    results = [_infer_arch(n) for n in arch_names]

    if args.json_out:
        print(json.dumps(results, indent=2))
        sys.exit(0)

    # Sort worst first by pub_conf
    results.sort(key=lambda r: r.get("pub_conf", 1.0))

    print(bold(f"Brain Infer — {len(results)} arch(s)"))
    print()
    for r in results:
        _print_arch_result(r)

    if len(results) > 1:
        # Summary table
        valid = [r for r in results if "error" not in r]
        if valid:
            avg_prec_tech = sum(r["prec_tech"] for r in valid) / len(valid)
            avg_prec_ctrl = sum(r["prec_ctrl"] for r in valid) / len(valid)
            avg_conf = sum(r["pub_conf"] for r in valid) / len(valid)
            print(bold("─" * 50))
            print(bold("Summary"))
            print(f"  Avg published conf    : {_conf_color(avg_conf)}")
            print(f"  Avg technique precision: {_pct(round(avg_prec_tech * 100), 100)}")
            print(f"  Avg control precision  : {_pct(round(avg_prec_ctrl * 100), 100)}")


if __name__ == "__main__":
    main()
