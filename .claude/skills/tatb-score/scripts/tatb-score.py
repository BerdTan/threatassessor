#!/usr/bin/env python3
"""
tatb-score.py — TATB (TA Test Benchmark) scorer for a single architecture.

Usage:
    python3 tatb-score.py                       # most recent report in report/
    python3 tatb-score.py 01_minimal_vulnerable_2
    python3 tatb-score.py 01_minimal_vulnerable_2 --json
"""
import json
import os
import re
import sys
import argparse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

# ─── Colour helpers ──────────────────────────────────────────────────────────

def _c(t, code): return f"\033[{code}m{t}\033[0m"
def bold(t):   return _c(t, "1")
def green(t):  return _c(t, "92")
def olive(t):  return _c(t, "32")
def amber(t):  return _c(t, "33")
def red(t):    return _c(t, "31")
def cyan(t):   return _c(t, "36")
def grey(t):   return _c(t, "2")
def reset(t):  return t


def band_color(s):
    if s is None:   return grey
    if s >= 85:     return green
    if s >= 70:     return olive
    if s >= 50:     return amber
    return red


def band_label(s):
    if s is None:   return "N/A"
    if s >= 85:     return "Excellent"
    if s >= 70:     return "Solid"
    if s >= 50:     return "Weak"
    return "Draft"


def score_bar(s, width=20):
    if s is None:
        return grey("?" * width)
    filled = round(s / 100 * width)
    col    = band_color(s)
    return col("█" * filled) + grey("░" * (width - filled))


def signal_line(label, value, unit="", context="", ok_threshold=75):
    """Print one sub-signal row with coloured value."""
    if value is None:
        mark = grey("○")
        val  = grey("N/A")
    else:
        ok   = value >= ok_threshold
        mark = green("✓") if ok else (amber("●") if value >= 50 else red("✗"))
        col  = green if ok else (amber if value >= 50 else red)
        val  = col(f"{value:3d}%")
    ctx = grey(f"  {context}") if context else ""
    print(f"    {mark}  {label:<26} {val}{unit}{ctx}")


# ─── Scoring (mirrors _computeTatbScores in dashboard.js) ────────────────────

def _adr_pop(v):
    if v is None: return False
    if isinstance(v, str): return len(v.strip()) > 20
    if isinstance(v, list): return len(v) > 0
    if isinstance(v, dict): return len(v) > 0
    return False


def score_threat(gt):
    aps    = gt.get("expected_attack_paths", [])
    pn     = (gt.get("metadata") or {}).get("parsed_nodes", {})
    pn_ids = list(pn.keys())

    bound, nodes_in = 0, set()
    for ap in aps:
        entry = ap.get("entry_node") or ap.get("entry") or (ap.get("path") or [None])[0]
        if entry and entry in pn_ids:
            bound += 1
        for n in (ap.get("path") or []):
            if n in pn_ids: nodes_in.add(n)
        e = ap.get("entry_node") or ap.get("entry")
        if e and e in pn_ids: nodes_in.add(e)

    node_binding  = round(bound / len(aps) * 100) if aps else 0
    node_coverage = round(len(nodes_in) / len(pn_ids) * 100) if pn_ids else 50
    all_techs     = set(t for ap in aps for t in ap.get("techniques", []))
    tech_variety  = min(100, round(len(all_techs) / 12 * 100))
    sigs          = [",".join(sorted(ap.get("techniques", []))) for ap in aps]
    identical     = len(sigs) >= 2 and len(set(sigs)) == 1
    penalty       = 20 if identical else 0
    score = max(0, round(node_binding * 0.40 + node_coverage * 0.25 + tech_variety * 0.35 - penalty))
    return dict(score=score, node_binding=node_binding, node_coverage=node_coverage,
                tech_variety=tech_variety, identical=identical, n_aps=len(aps),
                n_nodes=len(pn_ids), n_techs=len(all_techs))


CTRL_SYNONYMS = {
    "mfa":                   ["multi-factor","authentication","account use policies"],
    "waf":                   ["filter network","web application firewall","application layer","exploit protection","application isolation"],
    "edr":                   ["endpoint detection","behavior prevention","endpoint","software configuration","audit"],
    "dlp":                   ["data loss prevention"],
    "backup":                ["data backup","recovery","backup"],
    "least privilege":       ["privileged account","account management","restrict","limit access","disable or remove"],
    "rate limiting":         ["filter network traffic","limit access to resource","restrict","account use policies"],
    "input validation":      ["exploit protection","application isolation","update software"],
    "vulnerability scanning":["update software","patch","vulnerability","exploit protection","disable or remove"],
    "logging":               ["audit","monitoring","log"],
    "audit log":             ["audit","monitoring","log"],
    "patching":              ["update software","patch","exploit protection","disable or remove","software configuration"],
    "user training":         ["user training","security awareness","out-of-band"],
    "network segmentation":  ["network segmentation","segment","filter network"],
    "api gateway":           ["filter network","application layer","web application"],
    "behavioral analysis":   ["behavior prevention","restrict execution","audit"],
    "web content filtering": ["restrict web-based","filter network"],
    "ids/ips":               ["intrusion prevention","network intrusion","filter network traffic"],
    "ids":                   ["intrusion prevention","network intrusion"],
    "ips":                   ["intrusion prevention","network intrusion"],
    "encryption":            ["encrypt sensitive","ssl/tls","encrypt"],
    "secrets management":    ["privileged account","credential","account management"],
    "access control":        ["account management","privileged account","limit access","restrict"],
    "authentication":        ["multi-factor","password policies","account use policies","user account management"],
    "code signing":          ["execution prevention","operating system configuration","update software"],
    "sandbox":               ["application isolation","application developer","exploit protection"],
    "monitoring":            ["audit","software configuration","network intrusion prevention"],
}


def _ctrl_matches(ctrl, mit_name):
    c, m = ctrl.lower(), mit_name.lower()
    if c in m or m in c: return True
    for abbrev, exps in CTRL_SYNONYMS.items():
        if abbrev in c or c in abbrev:
            if any(e in m for e in exps): return True
    cw = set(w for w in c.split() if len(w) > 4)
    mw = set(w for w in m.split() if len(w) > 4)
    return bool(cw & mw)


def score_ttp(gt, moe, mitre_mits, mit_names):
    tv = gt.get("technique_validation") or \
         gt.get("validation_report", {}).get("validations", {}).get("technique_relevance", [])

    confirmed = sum(1 for v in tv if v.get("valid") is True
                    and "[plausible]" not in (v.get("reason") or "").lower()
                    and "generic" not in (v.get("reason") or "").lower()
                    and "keyword" not in (v.get("reason") or "").lower())
    plausible = sum(1 for v in tv if v.get("valid") is True
                    and ("[plausible]" in (v.get("reason") or "").lower()
                         or "generic" in (v.get("reason") or "").lower()
                         or "keyword" in (v.get("reason") or "").lower()))
    failed    = sum(1 for v in tv if v.get("valid") is False)
    val_pct   = round((confirmed * 1.0 + plausible * 0.5) / len(tv) * 100) if tv else 50

    # Cross-critic
    cross_pct = 0
    ev = (moe or {}).get("expert_validations", {})
    crit_techs = {}
    for k in ["architect","tester","red_team","purple_team","blackhat"]:
        blob = json.dumps(ev.get(k, {}))
        crit_techs[k] = set(re.findall(r"(?:AML\.T\d{4}(?:\.\d{3})?|T\d{4}(?:\.\d{3})?)", blob))
    all_t  = set(t for s in crit_techs.values() for t in s)
    cross_v = sum(1 for t in all_t if sum(1 for s in crit_techs.values() if t in s) >= 2)
    cross_pct = round(cross_v / len(all_t) * 100) if all_t else 0

    # MoE lift
    mc  = (moe or {}).get("confidence", {})
    lift = ((mc.get("final", 0) - mc.get("base", 0)) / 100
            if mc.get("final") is not None and mc.get("base") is not None else 0)
    moe_score = max(0, min(100, 50 + lift * 500))

    # MITRE alignment
    ctrls  = gt.get("control_recommendations", [])
    aligned, checked, seen = 0, 0, set()
    mismatches = []
    for c in ctrls:
        ctrl_name = (c.get("control") or "").lower()
        for tid in (c.get("mitre_techniques") or c.get("techniques") or []):
            if tid.startswith("AML."): continue  # ATLAS techniques — no ATT&CK M-ID mapping
            pair = f"{tid}::{ctrl_name}"
            if pair in seen: continue
            seen.add(pair)
            mids = mitre_mits.get(tid, [])
            if not mids: continue
            checked += 1
            names = [mit_names.get(mid, "") for mid in mids]
            ok = any(_ctrl_matches(ctrl_name, n) for n in names if n)
            if ok: aligned += 1
            else:  mismatches.append({"technique": tid, "control": c.get("control"),
                                       "mitre_suggests": ", ".join(n for n in names[:3] if n)})
    mitre_pct = round(aligned / checked * 100) if checked else 50

    score = round(val_pct * 0.30 + mitre_pct * 0.30 + cross_pct * 0.25 + moe_score * 0.15)
    return dict(score=score, val_pct=val_pct, confirmed=confirmed, plausible=plausible,
                failed=failed, cross_pct=cross_pct, moe_lift_pp=round(lift * 100, 1),
                mitre_pct=mitre_pct, mitre_checked=checked, mismatches=mismatches,
                has_moe=moe is not None)


def score_risk(gt, gov):
    aps   = gt.get("expected_attack_paths", [])
    adrs  = gt.get("architecture_decision_records", [])
    rr    = (gt.get("residual_risks") or {}).get("per_threat", {})
    ctrls = gt.get("control_recommendations", [])

    ap_techs  = set(t for ap in aps for t in ap.get("techniques", []))
    mit_techs = set(t for c in ctrls for t in (c.get("mitre_techniques") or c.get("techniques") or []))
    tech_cov  = round(len(ap_techs & mit_techs) / len(ap_techs) * 100) if ap_techs else 50

    # ap_coverage: per-(AP-index, technique) pairs that have an aligned control.
    # Stronger than tech_cov: requires the control to explicitly list that AP index,
    # not just the technique somewhere in the architecture.
    ap_tech_pairs = {
        (ap_idx, t)
        for ap_idx, ap in enumerate(aps)
        for t in ap.get("techniques", [])
    }
    covered_pairs = set()
    for c in ctrls:
        c_aps   = set(c.get("attack_paths") or [])
        c_techs = set(c.get("mitre_techniques") or c.get("techniques") or [])
        for pair in ap_tech_pairs:
            if pair[0] in c_aps and pair[1] in c_techs:
                covered_pairs.add(pair)
    ap_cov = round(len(covered_pairs) / len(ap_tech_pairs) * 100) if ap_tech_pairs else 50

    all_hops  = [h for a in adrs for h in a.get("hops", [])]
    full_hops = sum(1 for h in all_hops
                    if "missing" not in (h.get("gap_note") or h.get("gap_type") or "").lower())
    hop_pct   = round(full_hops / len(all_hops) * 100) if all_hops else 50

    rr_vals  = list(rr.values())
    hard_ct  = sum(1 for r in rr_vals if r.get("status") in ("MONITOR","MITIGATE"))
    hard_pct = round((len(rr_vals) - hard_ct) / len(rr_vals) * 100) if rr_vals else 50

    # Score: tech_cov stays (architecture-wide baseline), ap_cov adds per-AP alignment signal
    score = round(tech_cov * 0.30 + ap_cov * 0.15 + hop_pct * 0.30 + hard_pct * 0.25)
    return dict(score=score, tech_cov=tech_cov, ap_cov=ap_cov, hop_pct=hop_pct, hard_pct=hard_pct,
                n_hops=len(all_hops), full_hops=full_hops,
                hard_threats=hard_ct, total_threats=len(rr_vals),
                n_ap_pairs=len(ap_tech_pairs), covered_pairs=len(covered_pairs))


SPEC_RE = re.compile(
    r"\b(install|deploy|configure|enable|enforce|integrate|add|block|scan|segment|monitor|"
    r"firewall|WAF|ACL|IAM|MFA|RASP|DAM|SIEM|DLP|EDR|Snyk|Grype|OWASP|Docker|Redis|node|"
    r"database|pipeline|CI.?CD|policy|rule|cert|token|AP-\d+|T\d{4})\b", re.I)


def score_plan(gt, sm):
    aps   = gt.get("expected_attack_paths", [])
    items = (sm or {}).get("action_plan", [])
    if not items:
        return dict(score=None, reason="no SM data — run full_moe scenario")

    complete  = [it for it in items
                 if len((it.get("action") or "").strip()) > 10
                 and len((it.get("rationale") or "").strip()) > 10
                 and len((it.get("first_step") or "").strip()) > 10
                 and len((it.get("effort") or "").strip()) > 0]
    comp_pct  = round(len(complete) / len(items) * 100)

    measurable = [it for it in items
                  if float(it.get("confidence_gain") or 0) > 0
                  or (it.get("risk_reduction_estimate") or "").lower() in ("high","medium")]
    meas_pct  = round(len(measurable) / len(items) * 100)

    effort_set = set((it.get("effort") or "").lower() for it in items if it.get("effort"))
    prio_set   = set((it.get("priority") or "").lower() for it in items if it.get("priority"))
    all_cw     = all(it.get("priority") == "critical" and it.get("effort") == "weeks" for it in items)
    sprint_pct = (30 if all_cw else
                  100 if len(effort_set) >= 2 and len(prio_set) >= 2 else
                  65 if len(effort_set) >= 2 or len(prio_set) >= 2 else 40)

    spec_ct  = sum(1 for it in items if SPEC_RE.search((it.get("first_step") or "") + " " + (it.get("action") or "")))
    spec_pct = round(spec_ct / len(items) * 100)

    crit_aps = [ap for ap in aps if ap.get("criticality_tier") == "CRITICAL"]
    addr     = [ap for ap in crit_aps
                if any(ap.get("id","") in ((it.get("action") or "") + (it.get("rationale") or ""))
                       for it in items)]
    closure_pct = round(len(addr) / len(crit_aps) * 100) if crit_aps else 100
    anti_bonus  = 5 if any(str(it.get("is_antipattern","")).lower() == "true" for it in items) else 0

    # ADR alignment: do high-priority action items recommend controls that the ADR mandated?
    # Each ADR hop lists controls by type. We check whether each action item's first_step/action
    # names at least one control that appears in any ADR hop for the corresponding path.
    adrs = gt.get("architecture_decision_records", [])
    adr_controls = set()
    for adr in adrs:
        for hop in (adr.get("hops") or []):
            for ctrl in (hop.get("controls") or []):
                # ADR hop controls use "control" field (not "name")
                name = (ctrl.get("control") or ctrl.get("name") or "").lower().strip()
                if name:
                    adr_controls.add(name)
    if adr_controls and items:
        high_items = [it for it in items if (it.get("priority") or "").lower() in ("critical", "high")]
        if high_items:
            aligned = sum(1 for it in high_items
                          if any(c in ((it.get("first_step") or "") + " " + (it.get("action") or "") + " " + (it.get("rationale") or "")).lower()
                                 for c in adr_controls))
            adr_align_pct = round(aligned / len(high_items) * 100)
        else:
            adr_align_pct = 50
    else:
        adr_align_pct = 50  # no ADR data — neutral

    # Reweight: spec_pct and adr_align_pct share the specificity slot (10% each)
    score = min(100, round(comp_pct * 0.25 + meas_pct * 0.20 + sprint_pct * 0.15
                           + spec_pct * 0.10 + adr_align_pct * 0.10 + closure_pct * 0.20 + anti_bonus))
    return dict(score=score, comp_pct=comp_pct, meas_pct=meas_pct,
                sprint_pct=sprint_pct, spec_pct=spec_pct, adr_align_pct=adr_align_pct,
                closure_pct=closure_pct, n_items=len(items), n_crit_aps=len(crit_aps),
                n_addr=len(addr), effort_set=sorted(effort_set), prio_set=sorted(prio_set),
                anti_bonus=anti_bonus, n_adr_controls=len(adr_controls))


# ─── MITRE fetch ─────────────────────────────────────────────────────────────

def fetch_mitre(tech_ids):
    if not tech_ids:
        return {}, {}
    try:
        url  = f"http://localhost:8000/api/v1/technique-mitigations?technique_ids={','.join(tech_ids)}"
        mits = json.loads(urllib.request.urlopen(url, timeout=5).read()).get("mappings", {})
        all_mids = list({m for ml in mits.values() for m in ml})
        if not all_mids: return mits, {}
        url2  = f"http://localhost:8000/api/v1/mitigations?mitigation_ids={','.join(all_mids)}"
        names = json.loads(urllib.request.urlopen(url2, timeout=5).read()).get("mitigations", {})
        return mits, names
    except Exception as e:
        print(grey(f"  MITRE fetch unavailable ({e}) — alignment uses 50% neutral"), file=sys.stderr)
        return {}, {}


# ─── Rendering ───────────────────────────────────────────────────────────────

def print_rubric(icon, title, s, sub_lines, note=None):
    col   = band_color(s)
    lbl   = band_label(s)
    score = f"{s:3d}" if s is not None else "N/A"
    bar   = score_bar(s)
    print()
    print(bold(f"  {icon}  {title}") + f"  {col(score)}  {bar}  {grey(lbl)}")
    if note:
        print(grey(f"     {note}"))
    for fn in sub_lines:
        fn()


def stage_attr(signal, value, stage_hint):
    """Print stage attribution line only when signal is weak."""
    if value is not None and value < 70:
        col = band_color(value)
        print(grey(f"     → Fix: {stage_hint}"))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arch", nargs="?", help="Architecture name (default: most recent)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()

    # Suppress colour when piped or --no-color
    use_color = not args.no_color and sys.stdout.isatty()
    if not use_color:
        for fn_name in ["bold","green","olive","amber","red","cyan","grey"]:
            globals()[fn_name] = reset

    report_dir = REPO / "report"
    if args.arch:
        arch_dir = report_dir / args.arch
    else:
        candidates = sorted([d for d in report_dir.iterdir()
                             if d.is_dir() and (d / "ground_truth.json").exists()],
                            key=lambda d: d.stat().st_mtime, reverse=True)
        if not candidates:
            print(red("No architectures found in report/"), file=sys.stderr)
            sys.exit(1)
        arch_dir = candidates[0]

    if not (arch_dir / "ground_truth.json").exists():
        print(red(f"ground_truth.json not found for {arch_dir.name}"), file=sys.stderr)
        sys.exit(1)

    def _load(name):
        p = arch_dir / name
        return json.load(open(p)) if p.exists() else None

    gt  = _load("ground_truth.json")
    gov = _load("governance_signals.json")
    moe = _load("07_moe_orchestrator.json")
    sm  = _load("08_scrum_master.json")

    # Fetch MITRE data
    tech_ids = list({t for ap in gt.get("expected_attack_paths", []) for t in ap.get("techniques", [])})
    mitre_mits, mit_names = fetch_mitre(tech_ids)

    # Score
    t_s = score_threat(gt)
    ttp = score_ttp(gt, moe, mitre_mits, mit_names)
    r_s = score_risk(gt, gov)
    p_s = score_plan(gt, sm)
    valid = [s["score"] for s in [t_s, ttp, r_s, p_s] if isinstance(s,dict) and s.get("score") is not None]
    overall = round(sum(valid)/len(valid)) if valid else None

    if args.json:
        print(json.dumps({"arch": arch_dir.name, "overall": overall,
                          "threat": t_s, "ttp": ttp, "risk": r_s, "plan": p_s}, indent=2, default=str))
        return

    # ── Header ───────────────────────────────────────────────────────────────
    avail = []
    if gov: avail.append("gov")
    if moe: avail.append("moe")
    if sm:  avail.append("sm")
    avail_str = "+".join(avail) if avail else "GT only"
    col = band_color(overall)
    print()
    print(bold(f"🧪 TATB Scorecard — {arch_dir.name}"))
    print(f"  Data: gt+{avail_str}   Overall: {col(str(overall) if overall is not None else 'N/A')}/100"
          f"  {col(band_label(overall))}  {score_bar(overall, 30)}")
    print(grey("  ─" * 36))

    # ── Threat-Relevant ───────────────────────────────────────────────────────
    print_rubric("🎯","Threat-Relevant", t_s["score"], [
        lambda: signal_line("Node binding",    t_s["node_binding"],  "%",
                            f"{t_s['n_aps']} paths, {t_s['n_nodes']} diagram nodes"),
        lambda: signal_line("Node coverage",   t_s["node_coverage"], "%",
                            f"nodes touched by any path"),
        lambda: signal_line("Technique variety",t_s["tech_variety"],  "%",
                            f"{t_s['n_techs']} unique techniques (12=max)"),
        lambda: print(grey(f"     {'⚠ Generic-fallback detected — all paths identical' if t_s['identical'] else '✓ Paths have distinct technique sets'}")),
    ])
    stage_attr("node_binding", t_s["node_binding"],   "AnalysisStage → ground_truth_generator (entry node extraction)")
    stage_attr("node_coverage",t_s["node_coverage"],  "AnalysisStage → path-finding hop depth")
    stage_attr("tech_variety", t_s["tech_variety"],   "AnalysisStage → RAPIDS + structural technique inference")

    # ── TTP-Accurate ──────────────────────────────────────────────────────────
    moe_sign = "+" if ttp["moe_lift_pp"] >= 0 else ""
    print_rubric("🎭","TTP-Accurate", ttp["score"], [
        lambda: signal_line("Validation depth",  ttp["val_pct"],   "%",
                            f"{ttp['confirmed']} CONFIRMED · {ttp['plausible']} PLAUSIBLE · {ttp['failed']} FAILED"),
        lambda: signal_line("MITRE alignment",   ttp["mitre_pct"], "%",
                            f"{ttp['mitre_checked']} technique-control pairs checked"
                            if ttp["mitre_checked"] else "MITRE data unavailable (50% neutral)"),
        lambda: signal_line("Cross-critic",      ttp["cross_pct"], "%",
                            f"{'MoE data available' if ttp['has_moe'] else 'no MoE — run full_moe'}"),
        lambda: signal_line("MoE lift",          None if not ttp["has_moe"] else
                            round(50 + ttp["moe_lift_pp"] * 5),
                            "",
                            f"{moe_sign}{ttp['moe_lift_pp']}pp confidence delta"),
    ])
    if ttp["mismatches"]:
        print(amber(f"     ⚠ {len(ttp['mismatches'])} MITRE alignment mismatches — click TATB tab for details"))
    stage_attr("val_pct",   ttp["val_pct"],   "QualityStage → self_validation.py (tighten heuristic thresholds)")
    stage_attr("mitre_pct", ttp["mitre_pct"], "ReportStage → exhaustive_mitigation_mapper (add missing M-ID mappings)")
    stage_attr("cross_pct", ttp["cross_pct"], "CriticStage → run full_moe to get multi-critic technique agreement")

    # ── Risk-Defensible ───────────────────────────────────────────────────────
    print_rubric("⚖️ ","Risk-Defensible", r_s["score"], [
        lambda: signal_line("Technique mitigation", r_s["tech_cov"],  "%",
                            f"attack-path techniques with a mapped control (arch-wide)"),
        lambda: signal_line("AP-aligned mitigation", r_s["ap_cov"],  "%",
                            f"{r_s['covered_pairs']}/{r_s['n_ap_pairs']} (AP, technique) pairs with a targeted control"),
        lambda: signal_line("Hop layer coverage",   r_s["hop_pct"],   "%",
                            f"{r_s['full_hops']}/{r_s['n_hops']} hops have all 4 zero-trust layers"),
        lambda: signal_line("Residual exposure",    r_s["hard_pct"],  "%",
                            f"{r_s['hard_threats']}/{r_s['total_threats']} threats at MONITOR/MITIGATE after controls"),
    ])
    if r_s["hop_pct"] < 70 and r_s["n_hops"] > 0:
        print(amber(f"     ⚠ {r_s['n_hops'] - r_s['full_hops']} hops missing detect/isolate/respond layers"))
    if r_s["hard_threats"] > 0:
        print(amber(f"     ⚠ {r_s['hard_threats']} threats structurally hard to defend — architecture review may be needed"))
    stage_attr("tech_cov", r_s["tech_cov"], "ReportStage → control_recommendations technique mapping (arch-wide)")
    stage_attr("ap_cov",   r_s["ap_cov"],  "ReportStage → control_recommendations attack_paths field (per-AP technique alignment)")
    stage_attr("hop_pct",  r_s["hop_pct"],  "ReportStage → ADR generator (dir_category assignment — ensure all 4 layers)")

    # ── Plan-Actionable ───────────────────────────────────────────────────────
    if p_s.get("score") is None:
        print()
        print(bold("  ✅  Plan-Actionable") + f"  {grey('N/A')}  {score_bar(None, 20)}  {grey('N/A')}")
        print(grey(f"     {p_s.get('reason','')}"))
    else:
        print_rubric("✅","Plan-Actionable", p_s["score"], [
            lambda: signal_line("Item completeness",   p_s["comp_pct"],      "%",
                                f"{p_s['n_items']} action items, all 4 fields present"),
            lambda: signal_line("Measurable outcomes", p_s["meas_pct"],      "%",
                                f"confidence_gain or risk_reduction_estimate present"),
            lambda: signal_line("Sprint spreadability",p_s["sprint_pct"],    "%",
                                f"effort: {'/'.join(p_s['effort_set'])} · priority: {'/'.join(p_s['prio_set'])}"),
            lambda: signal_line("Control specificity", p_s["spec_pct"],      "%",
                                f"items naming a specific tool/node/technique"),
            lambda: signal_line("ADR alignment",       p_s["adr_align_pct"], "%",
                                f"high-priority items referencing ADR-mandated controls"
                                + (f" ({p_s['n_adr_controls']} ADR controls)" if p_s["n_adr_controls"] else " (no ADR data — neutral 50%)")),
            lambda: signal_line("AP plan closure",     p_s["closure_pct"],   "%",
                                f"{p_s['n_addr']}/{p_s['n_crit_aps']} CRITICAL paths have an explicit plan item"),
        ])
        if p_s["anti_bonus"]:
            print(green(f"     +5% anti-pattern bonus — SM identified structural design flaws"))
        if p_s["adr_align_pct"] < 70 and p_s["n_adr_controls"] > 0:
            print(amber(f"     ⚠ High-priority items don't consistently reference ADR-mandated controls — plan may conflict with architecture decisions"))
        if p_s["closure_pct"] < 100 and p_s["n_crit_aps"] > 0:
            print(amber(f"     ⚠ {p_s['n_crit_aps'] - p_s['n_addr']} CRITICAL path(s) not explicitly addressed in plan"))
        stage_attr("comp_pct",      p_s["comp_pct"],      "ScrumMasterStage → SM prompt (ensure all 4 item fields generated)")
        stage_attr("adr_align_pct", p_s["adr_align_pct"], "ScrumMasterStage → SM prompt (reference ADR controls in action items) + threat_report.py ADR filter")
        stage_attr("closure_pct",   p_s["closure_pct"],   "ScrumMasterStage → SM prompt (add: reference AP-IDs in action items)")

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print(grey("  ─" * 36))
    print(f"  Overall: {band_color(overall)(str(overall) if overall is not None else 'N/A')}/100"
          f"  {band_color(overall)(band_label(overall))}")
    print(grey("  Scores are read-only diagnostics. See TATB tab in dashboard for full evidence."))
    print()


if __name__ == "__main__":
    main()
