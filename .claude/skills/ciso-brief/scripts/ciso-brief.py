#!/usr/bin/env python3
"""
ciso-brief.py — CISO-ready one-page security brief.

Pipeline: PLAN → BUILD → LOOK → RELEASE

  PLAN    Inventory available data, emit a readiness table, gate if incomplete.
  BUILD   Compute all metrics, select findings, generate investment table + LLM narrative.
  LOOK    Load previous snapshot (ciso_brief_latest.json), compute deltas for trend view.
  RELEASE Write snapshot JSON + dated MD brief. Print the full brief with trend prepended.

Snapshot files written per architecture:
  report/<arch>/ciso_brief_latest.json   — machine-readable, always current
  report/<arch>/ciso_brief_<date>.md     — human-readable dated archive

Usage:
    python3 ciso-brief.py 21_agentic_ai_system      # single arch (all 4 stages)
    python3 ciso-brief.py                            # most recent report
    python3 ciso-brief.py --corpus                   # all architectures + corpus table
    python3 ciso-brief.py --corpus --top 5           # top 5 by risk score
    python3 ciso-brief.py 21_agentic_ai_system --no-llm   # skip LLM narrative
    python3 ciso-brief.py 21_agentic_ai_system --no-save  # skip snapshot write
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

# ── Colour helpers ─────────────────────────────────────────────────────────────
def _c(t, code): return f"\033[{code}m{t}\033[0m"
def bold(t):  return _c(t, "1")
def green(t): return _c(t, "92")
def amber(t): return _c(t, "33")
def red(t):   return _c(t, "31")
def cyan(t):  return _c(t, "36")
def dim(t):   return _c(t, "2")

def _strip_ansi(s: str) -> str:
    return re.sub(r'\033\[[^m]*m', '', s)

def _bar(val, max_val=100, width=20, color_fn=None):
    filled = int(width * val / max_val)
    bar = "█" * filled + "░" * (width - filled)
    if color_fn: return color_fn(bar)
    if val >= 70: return green(bar)
    if val >= 40: return amber(bar)
    return red(bar)

def _risk_bar(val, width=20):
    filled = int(width * val / 100)
    bar = "█" * filled + "░" * (width - filled)
    if val >= 70: return red(bar)
    if val >= 40: return amber(bar)
    return green(bar)

def _conf_color(pct):
    if pct >= 85: return green
    if pct >= 70: return amber
    return red

def _interp_label(pct) -> str:
    if pct >= 90: return green("STRONG")
    if pct >= 80: return green("GOOD")
    if pct >= 70: return amber("ADEQUATE")
    if pct >= 60: return amber("NEEDS REVIEW")
    return red("ACTION REQUIRED")

def _interp_plain(pct) -> str:
    if pct >= 90: return "STRONG"
    if pct >= 80: return "GOOD"
    if pct >= 70: return "ADEQUATE"
    if pct >= 60: return "NEEDS REVIEW"
    return "ACTION REQUIRED"

CRITIC_LABELS = {
    "architect": "Architect", "tester": "Tester", "red_team": "Red Team",
    "purple_team": "Purple Team", "blackhat": "Blackhat",
}

def _source_label(source: str) -> str:
    parts = [CRITIC_LABELS.get(s.strip(), s.strip()) for s in source.split("+")]
    return green(" + ".join(parts)) if len(parts) > 1 else dim(parts[0])

def _critic_count(source: str) -> int:
    return len(source.split("+"))


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — PLAN
# Inventory what data exists, emit a readiness table, return gaps.
# ══════════════════════════════════════════════════════════════════════════════

def stage_plan(report_dir: Path) -> dict:
    """
    Returns:
        data       — dict of loaded files (gt, moe, sm)
        gaps       — list of missing-data warnings (non-fatal)
        blocking   — True if no ground_truth (nothing to brief)
    """
    def _load(p: Path) -> dict:
        if p.exists():
            try: return json.loads(p.read_text())
            except Exception: pass
        return {}

    gt  = _load(report_dir / "ground_truth.json")
    moe = _load(report_dir / "07_moe_orchestrator.json")
    sm  = _load(report_dir / "08_scrum_master.json")

    gaps = []
    blocking = False

    if not gt:
        gaps.append("ground_truth.json missing — cannot generate brief")
        blocking = True
    else:
        if not gt.get("expected_attack_paths"):
            gaps.append("No attack paths in ground_truth — analysis may be incomplete")
        if not gt.get("control_recommendations"):
            gaps.append("No control recommendations — run analysis first")

    if not moe:
        gaps.append("07_moe_orchestrator.json missing — no confidence/investment tiers (run /run-er --full)")
    else:
        if not moe.get("improvement_options"):
            gaps.append("No improvement_options in MoE — investment tiers will be empty")
        if not moe.get("consensus_recommendations", {}).get("critical"):
            gaps.append("No critical findings in MoE — brief may be sparse")

    if not sm:
        gaps.append("08_scrum_master.json missing — no redesign signal or SM actions (run /run-er --full)")

    return {"gt": gt, "moe": moe, "sm": sm, "gaps": gaps, "blocking": blocking}


def print_plan(arch: str, plan: dict) -> None:
    gaps = plan["gaps"]
    has_moe = bool(plan["moe"])
    has_sm  = bool(plan["sm"])

    print(f"\n  {bold('PLAN')}  {dim(arch)}")
    rows = [
        ("ground_truth.json",         bool(plan["gt"]),  "Analysis base"),
        ("07_moe_orchestrator.json",   has_moe,           "ER confidence + investment tiers"),
        ("08_scrum_master.json",       has_sm,            "Redesign signal + SM actions"),
        ("ciso_brief_latest.json",     (Path(REPO / "report" / arch / "ciso_brief_latest.json")).exists(),
                                                           "Previous snapshot for trend comparison"),
    ]
    for fname, present, desc in rows:
        icon = green("✓") if present else amber("○")
        print(f"  {icon}  {fname:<35}  {dim(desc)}")

    if gaps:
        print()
        for g in gaps:
            icon = red("✗") if "missing" in g.lower() else amber("⚠")
            print(f"  {icon}  {dim(g)}")

    readiness = "FULL" if (plan["gt"] and has_moe and has_sm) else "PARTIAL" if plan["gt"] else "BLOCKED"
    color = green if readiness == "FULL" else amber if readiness == "PARTIAL" else red
    print(f"\n  Readiness: {color(readiness)}")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 — BUILD
# Compute all metrics, select findings, optionally call LLM for narrative.
# ══════════════════════════════════════════════════════════════════════════════

_HOUSEKEEPING_PATTERNS = re.compile(
    r"after\.mmd|NEW_\*|control.node|diagram.*sync|diagram.*gap|"
    r"missing.*control.node|control.node.*missing|"
    r"artifact.7|mmd.*contain|contain.*mmd|"
    r"\d+\s*NEW_\s*control|controls? visuali[sz]",
    re.I,
)

def _is_housekeeping(desc: str) -> bool:
    """Return True if the finding is an internal diagram/QA signal, not a security risk."""
    return bool(_HOUSEKEEPING_PATTERNS.search(desc))


def _top_findings(moe: dict, n: int = 5) -> list[dict]:
    """KNOWN security findings only — diagram/QA housekeeping entries are excluded.
    Sorted multi-critic first then severity."""
    cr = moe.get("consensus_recommendations", {})
    ev = moe.get("expert_validations", {})
    sev_rank = {"CRITICAL": 2, "HIGH": 1}

    # Build description-prefix → recommendation lookup from critic gaps.
    # Multi-depth keys (8/10/15/20 chars) because KNOWN multi-node descriptions
    # diverge from single-node gap descriptions at ~10–20 chars.
    io = moe.get("improvement_options", {})
    gap_recs: dict[str, str] = {}
    for v in ev.values():
        for g in (v.get("gaps") or []):
            desc = (g.get("description") or "")
            rec  = (g.get("recommendation") or "").strip()
            if desc and rec:
                for n in (20, 15, 10, 8):
                    k = desc[:n].lower().strip()
                    if k and k not in gap_recs:
                        gap_recs[k] = rec

    # Also index tier item control names for gaps with empty recommendations
    for tier in io.values():
        for item in (tier.get("items") or []):
            it = str(item)
            if it.startswith("[SM]"):
                continue
            dash = it.find("—")  # em-dash U+2014
            ctrl = (it[:dash].strip() if dash > -1 else it[:60].strip())
            at = ctrl.lower().find(" at ")
            if at > -1:
                ctrl = ctrl[:at].strip()
            ck = ctrl[:20].lower().strip()
            if ck and ck not in gap_recs:
                gap_recs[ck] = f"Deploy {ctrl}."

    def _find_rec(desc: str, cr_rec: str) -> str:
        if cr_rec:
            return cr_rec
        for n in (20, 15, 10, 8):
            k = desc[:n].lower().strip()
            if k in gap_recs:
                return gap_recs[k]
        # Regex fallback: "No X (ControlName) deployed" → "Deploy ControlName"
        m1 = re.search(r"\bNo\s+\w+\s+(?:controls?\s+)?\(([^)]+)\)\s+deploy", desc, re.I)
        if m1:
            return f"Deploy {m1.group(1).strip()} — no controls currently in place."
        m2 = re.search(r"No\s+([\w\s/]+?)\s+(?:deployed|present|found|exists)", desc, re.I)
        if m2:
            ctrl = m2.group(1).strip()
            if len(ctrl) < 40:
                return f"Deploy {ctrl}."
        return ""

    candidates = []
    for sev_key in ("critical", "high"):
        for r in cr.get(sev_key, []):
            if r.get("confidence_label") != "KNOWN":
                continue
            desc = r.get("description", "")
            if _is_housekeeping(desc):
                continue
            source = r.get("source", "")
            rec    = _find_rec(desc, r.get("recommendation", ""))
            candidates.append({
                "description":     desc,
                "recommendation":  rec,
                "severity":        r.get("severity", sev_key.upper()),
                "source":          source,
                "critic_count":    _critic_count(source),
                "sev_rank":        sev_rank.get(r.get("severity", "").upper(), 0),
            })
    candidates.sort(key=lambda x: (-x["critic_count"], -x["sev_rank"]))
    return candidates[:n]


def _generate_narrative(arch: str, data: dict, delta: dict) -> tuple[str, str]:
    try:
        from agentic.llm_client import LLMClient
        client = LLMClient()

        gt, moe, sm = data["gt"], data["moe"], data["sm"]
        risk    = gt.get("expected_risk_score", 0)
        defence = gt.get("expected_defensibility", 0)
        conf    = (moe.get("confidence") or {}).get("final", 0)
        redesign = sm.get("redesign_signal", False)
        n_paths  = len(gt.get("expected_attack_paths", []))

        top = _top_findings(moe, n=3)
        top_desc = "; ".join(f["description"][:80] for f in top[:2])

        io  = moe.get("improvement_options", {})
        qw  = io.get("quick_wins",  {})
        rec = io.get("recommended", {})

        crit_actions = [
            a.get("action", "")[:80]
            for a in sm.get("action_plan", [])
            if a.get("priority") == "critical" and not a.get("is_antipattern")
        ][:2]

        # Include trend context if available
        trend_ctx = ""
        if delta:
            conf_d = delta.get("confidence_delta", 0)
            risk_d = delta.get("risk_delta", 0)
            if conf_d or risk_d:
                trend_ctx = (
                    f"\nTrend since last brief: confidence {'+' if conf_d>=0 else ''}{conf_d:.1f}pp, "
                    f"risk score {'+' if risk_d>=0 else ''}{risk_d:+d}."
                )

        # The LLM's specific role here: cross-critic synthesis narrator.
        # All the data (findings, scores, tiers) is already displayed visually.
        # The LLM adds what the data alone cannot: a single coherent business risk
        # sentence that bridges all five critics' perspectives into one board-ready
        # statement, and a prioritised first action that reflects that synthesis.
        # This is NOT the StoryCaster (which narrates individual attack paths).
        # It is NOT the SM (which recommends sprint actions per control gap).
        # It is the voice that says: given everything five independent reviewers found,
        # here is the one thing that matters most and here is what you do Monday morning.

        multi_critic_findings = "; ".join(
            f['description'][:80]
            for f in top[:3]
            if f.get("critic_count", 1) > 1
        )
        single_critic_note = f"{sum(1 for f in top if f.get('critic_count',1)==1)} single-critic findings also present" if any(f.get('critic_count',1)==1 for f in top) else ""

        prompt = f"""You are the cross-critic synthesis narrator for a security brief on {arch}.{trend_ctx}

Your specific job: five independent security reviewers (Architect, Tester, Red Team, Purple Team, Blackhat) \
have each assessed this architecture. You have seen their combined findings. Write two sentences that \
synthesise ACROSS all their perspectives — not a summary of one critic, but the single coherent risk \
picture that emerges when all five are read together.

Assessment data:
- Expert review confidence: {conf:.1f}% ({_interp_plain(conf)}) — how much agreement exists across critics
- Attack risk score: {risk}/100, Defensibility: {defence}/100
- {n_paths} attack paths identified
- Multi-critic confirmed findings (highest confidence): {multi_critic_findings or 'none'}
- {single_critic_note}
- Redesign signal: {redesign} — {'architecture changes required, controls alone insufficient' if redesign else 'controls can close the gaps'}
- Fastest fix: {qw.get('cost','?')} / {qw.get('effort','?')} → reduces risk by ~{qw.get('risk_reduction','?')}
- Recommended investment: {rec.get('cost','?')} / {rec.get('effort','?')}
- Most critical SM actions: {'; '.join(crit_actions)}

Write exactly two sentences on separate lines:
VERDICT: What the combined assessment means for the business. One concrete consequence if the top gap is not addressed. Board language — assume the reader has no security background.
ACTION: The single most impactful first step. Name the specific control and where to deploy it. State the expected outcome in plain terms. No semicolons.

Output only the two sentences, no labels, no bullets."""

        resp  = client.generate(prompt, max_tokens=200, temperature=0.2)
        lines = [re.sub(r"^(VERDICT|ACTION)\s*:\s*", "", l.strip(), flags=re.I)
                 for l in (resp.content or "").strip().splitlines() if l.strip()]
        return (lines[0] if lines else ""), (lines[1] if len(lines) > 1 else "")
    except Exception as e:
        return f"[LLM unavailable: {e}]", ""


def stage_build(arch: str, data: dict, delta: dict, use_llm: bool) -> dict:
    """Compute all brief metrics and narrative. Returns a 'brief' dict."""
    gt, moe, sm = data["gt"], data["moe"], data["sm"]

    risk    = gt.get("expected_risk_score", 0)
    defence = gt.get("expected_defensibility", 0)
    n_paths = len(gt.get("expected_attack_paths", []))
    n_tech  = len({t for ap in gt.get("expected_attack_paths", [])
                   for t in ap.get("techniques", [])})

    conf_data = moe.get("confidence") or {}
    conf      = conf_data.get("final") or 0

    io  = moe.get("improvement_options", {})
    cr  = moe.get("consensus_recommendations", {})

    known_crit   = [r for r in cr.get("critical", []) if r.get("confidence_label") == "KNOWN"]
    known_high   = [r for r in cr.get("critical", []) + cr.get("high", [])
                    if r.get("confidence_label") == "KNOWN"]
    unsure_count = len(cr.get("review", []))
    top_findings = _top_findings(moe, n=5)

    # Enrich findings with AP context from ground_truth
    ap_map = {
        ap["id"]: {
            "path":        " → ".join(ap.get("path", [])[:6]),
            "criticality": ap.get("criticality_tier", ""),
            "techniques":  ap.get("techniques", [])[:8],
        }
        for ap in gt.get("expected_attack_paths", [])
    }

    def _enrich(f: dict) -> dict:
        desc     = f.get("description", "")
        ap_ids   = list(dict.fromkeys(re.findall(r"\bAP-\d+\b", desc)))[:4]
        t_codes  = list(dict.fromkeys(re.findall(r"\bT\d{4}(?:\.\d{3})?\b", desc)))[:4]
        if not ap_ids and t_codes:
            ap_ids = [
                ap_id for ap_id, ap_data in ap_map.items()
                if any(t in ap_data["techniques"] for t in t_codes)
            ][:4]
        return {**f,
                "ap_context": [{"id": i, **ap_map[i]} for i in ap_ids if i in ap_map],
                "t_codes":    t_codes}

    top_findings = [_enrich(f) for f in top_findings]

    redesign = sm.get("redesign_signal", False)

    verdict_txt, action_txt = "", ""
    if use_llm and moe:
        verdict_txt, action_txt = _generate_narrative(arch, data, delta)

    return {
        "arch":                arch,
        "date":                datetime.date.today().isoformat(),
        "risk":                risk,
        "defensibility":       defence,
        "confidence":          conf,
        "n_paths":             n_paths,
        "n_tech":              n_tech,
        "known_critical":      len(known_crit),
        "known_high":          len(known_high),
        "unsure_count":        unsure_count,
        "redesign":            redesign,
        "top_findings":        top_findings,
        "tiers":               {k: io.get(k, {}) for k in ("quick_wins", "recommended", "maximum")},
        "ciso_advisor_verdict": verdict_txt,
        "ciso_advisor_action":  action_txt,
        # Legacy keys for backward compat
        "verdict":             verdict_txt,
        "action":              action_txt,
    }


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — LOOK
# Load previous snapshot, compute deltas. Returns delta dict (empty if no prior).
# ══════════════════════════════════════════════════════════════════════════════

def stage_look(report_dir: Path, brief: dict) -> dict:
    """Load previous ciso_brief_latest.json and compute deltas."""
    snap_path = report_dir / "ciso_brief_latest.json"
    if not snap_path.exists():
        return {}
    try:
        prev = json.loads(snap_path.read_text())
    except Exception:
        return {}

    prev_date = prev.get("date", "?")
    delta = {
        "prev_date":         prev_date,
        "confidence_delta":  round(brief["confidence"] - prev.get("confidence", brief["confidence"]), 1),
        "risk_delta":        brief["risk"] - prev.get("risk", brief["risk"]),
        "defence_delta":     brief["defensibility"] - prev.get("defensibility", brief["defensibility"]),
        "known_crit_delta":  brief["known_critical"] - prev.get("known_critical", brief["known_critical"]),
        "unsure_delta":      brief["unsure_count"] - prev.get("unsure_count", brief["unsure_count"]),
    }

    # Find closed findings (in prev top_findings but not in current)
    prev_descs = {f["description"][:60] for f in prev.get("top_findings", [])}
    curr_descs = {f["description"][:60] for f in brief["top_findings"]}
    delta["closed_findings"] = list(prev_descs - curr_descs)
    delta["new_findings"]    = list(curr_descs - prev_descs)

    return delta


def print_look(delta: dict) -> None:
    if not delta:
        return

    prev_date = delta.get("prev_date", "?")
    print(f"\n  {bold('TREND')}  {dim('vs ' + prev_date)}")

    def _d(val, invert=False):
        """Format a delta: green if improving, red if worsening."""
        if val == 0:
            return dim("±0")
        improving = (val > 0) if not invert else (val < 0)
        sign = "+" if val > 0 else ""
        return green(f"{sign}{val}") if improving else red(f"{sign}{val}")

    conf_d   = delta.get("confidence_delta", 0)
    risk_d   = delta.get("risk_delta", 0)
    def_d    = delta.get("defence_delta", 0)
    crit_d   = delta.get("known_crit_delta", 0)
    unsure_d = delta.get("unsure_delta", 0)

    print(f"  Confidence    {_d(conf_d)}pp   "
          f"Risk {_d(risk_d, invert=True)}   "
          f"Defensibility {_d(def_d)}   "
          f"Critical findings {_d(crit_d, invert=True)}")

    closed = delta.get("closed_findings", [])
    new    = delta.get("new_findings",    [])
    if closed:
        print(f"  {green(f'✓ {len(closed)} finding(s) closed')}")
        for c in closed[:2]:
            print(f"    {dim('✓ ' + c[:80])}")
    if new:
        print(f"  {amber(f'+ {len(new)} new finding(s)')}")
        for n in new[:2]:
            print(f"    {amber('+ ' + n[:80])}")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — RELEASE
# Write snapshot files and print the final brief.
# ══════════════════════════════════════════════════════════════════════════════

def _tier_row_str(label: str, tier: dict) -> str:
    """Build one investment tier row for the terminal output."""
    if not tier:
        return ""
    cost    = tier.get("cost",   "—")
    effort  = tier.get("effort", "—")
    rr_raw  = tier.get("risk_reduction", "")
    verdict = (tier.get("practical_verdict") or "").split("—")[0].strip()
    nums = re.findall(r"[\d.]+", rr_raw)
    try:
        before_r, after_r = float(nums[0]), float(nums[1])
        pct_red  = round((before_r - after_r) / before_r * 100)
        bar_len  = 12
        after_b  = int(bar_len * after_r / before_r)
        bar      = red("█" * after_b) + green("░" * (bar_len - after_b))
        risk_str = f"{int(before_r)} → {int(after_r)}  {bar}  −{pct_red}%"
    except Exception:
        risk_str = rr_raw[:40] if rr_raw else "—"
    verdict_str = f"  [{amber(verdict[:8])}]" if verdict else ""
    return f"  {bold(label):<16}  {cost:<14}  {effort:<12}  {risk_str}{verdict_str}"


def _build_md(brief: dict, delta: dict, gaps: list[str]) -> str:
    """Build the markdown brief for file output."""
    arch  = brief["arch"]
    date  = brief["date"]
    conf  = brief["confidence"]
    risk  = brief["risk"]
    defe  = brief["defensibility"]

    lines = [
        f"# CISO Brief — {arch}",
        f"**Date:** {date}   **Confidence:** {conf:.1f}% ({_interp_plain(conf)})  "
        f"{'⚠ REDESIGN SIGNAL' if brief['redesign'] else ''}",
        "",
        "## Risk at a Glance",
        "",
        f"| Metric | Value | Status |",
        f"|--------|-------|--------|",
        f"| Confidence | {conf:.1f}% | {_interp_plain(conf)} |",
        f"| Attack risk | {risk}/100 | {'HIGH EXPOSURE' if risk >= 70 else 'MEDIUM' if risk >= 40 else 'MANAGED'} |",
        f"| Defensibility | {defe}/100 | {'STRONG' if defe >= 70 else 'PARTIAL' if defe >= 40 else 'WEAK'} |",
        f"| Attack paths | {brief['n_paths']} | {brief['known_critical']} critical confirmed |",
        "",
    ]

    if delta:
        prev = delta.get("prev_date", "?")
        lines += [
            f"## Trend vs {prev}",
            "",
            f"| Metric | Change |",
            f"|--------|--------|",
            f"| Confidence | {'+' if delta.get('confidence_delta',0)>=0 else ''}{delta.get('confidence_delta',0):.1f}pp |",
            f"| Risk score | {'+' if delta.get('risk_delta',0)>=0 else ''}{delta.get('risk_delta',0)} |",
            f"| Critical findings | {'+' if delta.get('known_crit_delta',0)>=0 else ''}{delta.get('known_crit_delta',0)} |",
            f"| UNSURE pending | {'+' if delta.get('unsure_delta',0)>=0 else ''}{delta.get('unsure_delta',0)} |",
            "",
        ]
        closed = delta.get("closed_findings", [])
        new    = delta.get("new_findings",    [])
        if closed:
            lines.append(f"**Closed ({len(closed)}):** " + "; ".join(c[:70] for c in closed[:3]))
        if new:
            lines.append(f"**New ({len(new)}):** " + "; ".join(n[:70] for n in new[:3]))
        if closed or new:
            lines.append("")

    lines += ["## Top Findings (KNOWN confirmed only)", ""]
    for i, f in enumerate(brief["top_findings"], 1):
        critics = " + ".join(
            CRITIC_LABELS.get(s.strip(), s.strip()) for s in f["source"].split("+")
        )
        desc = f["description"]
        m = re.match(r"^(.{20,}?[.!?])(?:\s|$)", desc)
        desc_s = m.group(1) if m else desc[:120]
        rec  = f["recommendation"]
        rm   = re.match(r"^(.{20,}?[.!?])(?:\s|$)", rec)
        rec_s = rm.group(1) if rm else rec[:100]
        lines.append(f"### {i}. {f['severity']} — [{critics}]")
        lines.append(f"{desc_s}")
        if rec_s:
            lines.append(f"> **Action:** {rec_s}")
        lines.append("")

    if brief.get("unsure_count"):
        lines += [f"*{brief['unsure_count']} UNSURE items excluded — run `/review-unsure {arch}` to triage.*", ""]

    lines += ["## Investment Options", "",
              "| Tier | Cost | Effort | Risk after | Verdict |",
              "|------|------|--------|------------|---------|"]
    for key, label in (("quick_wins","Quick Win"),("recommended","Recommended"),("maximum","Maximum")):
        t = brief["tiers"].get(key, {})
        if t:
            rr = t.get("risk_reduction","—")
            nums = re.findall(r"[\d.]+", rr)
            try:
                rr_str = f"{int(float(nums[0]))} → {int(float(nums[1]))} (−{round((float(nums[0])-float(nums[1]))/float(nums[0])*100)}%)"
            except Exception:
                rr_str = rr[:40]
            verdict = (t.get("practical_verdict","") or "").split("—")[0].strip()[:20]
            lines.append(f"| {label} | {t.get('cost','—')} | {t.get('effort','—')} | {rr_str} | {verdict} |")
    lines.append("")

    if brief.get("verdict"):
        lines += ["## Assessment", "", brief["verdict"], ""]
    if brief.get("action"):
        lines += ["## Recommended First Action", "", brief["action"], ""]

    if gaps:
        lines += ["## Data Gaps", ""]
        for g in gaps:
            lines.append(f"- {g}")
        lines.append("")

    lines += [f"---", f"*Generated by /ciso-brief · {date}*"]
    return "\n".join(lines) + "\n"


def stage_release(report_dir: Path, brief: dict, delta: dict,
                  gaps: list[str], save: bool) -> None:
    """Print the full brief (with trend prepended) and write snapshot files."""
    W     = 60
    arch  = brief["arch"]
    conf  = brief["confidence"]
    risk  = brief["risk"]
    defe  = brief["defensibility"]
    date  = brief["date"]

    # ── Header ────────────────────────────────────────────────────────────────
    print()
    print("┌" + "─" * W + "┐")
    title    = f"  CISO BRIEF — {arch}"
    subtitle = f"  {date}   Confidence: {conf:.1f}%  {_interp_label(conf)}"
    sub_c    = _strip_ansi(subtitle)
    print("│" + bold(title) + " " * (W - len(title)) + "│")
    print("│" + subtitle + " " * max(0, W - len(sub_c)) + "│")
    print("└" + "─" * W + "┘")

    # ── Trend (LOOK output) ────────────────────────────────────────────────────
    print_look(delta)

    # ── Risk at a glance ──────────────────────────────────────────────────────
    print(f"\n  {bold('RISK AT A GLANCE')}")
    conf_c = _conf_color(conf)
    print(f"  Confidence    {conf:.1f}%  {_bar(conf, color_fn=conf_c)}  {_interp_label(conf)}")
    print(f"  Attack risk   {risk:>3}/100  {_risk_bar(risk)}  "
          f"{'HIGH EXPOSURE' if risk >= 70 else 'MEDIUM' if risk >= 40 else 'MANAGED'}")
    print(f"  Defensibility {defe:>3}/100  {_bar(defe)}  "
          f"{'STRONG' if defe >= 70 else 'PARTIAL' if defe >= 40 else 'WEAK'}")
    print(f"  Attack paths  {brief['n_paths']}   "
          f"({brief['known_critical']} critical confirmed · {brief['n_tech']} techniques)")
    if brief["redesign"]:
        print(f"  {red('⚠ REDESIGN SIGNAL')}  Architecture changes required")

    # ── Top findings ──────────────────────────────────────────────────────────
    top = brief["top_findings"]
    multi  = sum(1 for f in top if f["critic_count"] > 1)
    single = sum(1 for f in top if f["critic_count"] == 1)
    print(f"\n  {bold('TOP FINDINGS — KNOWN CONFIRMED')}  ({multi} multi-critic · {single} single-critic)")
    print(f"  {dim('Multi-critic first — prevents single-reviewer bias')}")

    for i, f in enumerate(top, 1):
        sev   = f["severity"].upper()
        sev_c = red if sev == "CRITICAL" else amber
        desc  = f["description"]
        dm    = re.match(r"^(.{20,}?[.!?])(?:\s|$)", desc)
        desc_s = dm.group(1) if dm else desc[:110]
        rec   = f["recommendation"]
        rm    = re.match(r"^(.{20,}?[.!?])(?:\s|$)", rec)
        rec_s  = rm.group(1) if rm else rec[:90]
        print()
        print(f"  {dim(str(i)+'.')} {sev_c(sev):<10}  [{_source_label(f['source'])}]")
        print(f"     {desc_s}")
        if rec_s:
            print(f"     {dim('→')} {dim(rec_s)}")

    if brief["unsure_count"]:
        print(f"\n  {amber(str(brief['unsure_count']) + ' UNSURE')} excluded — "
              f"run {cyan('/review-unsure ' + arch)}")

    # ── Investment options ─────────────────────────────────────────────────────
    print(f"\n  {bold('INVESTMENT OPTIONS')}")
    print(f"  {'Tier':<16}  {'Cost':<14}  {'Effort':<12}  {'Risk score after controls'}")
    print(f"  {'─'*16}  {'─'*14}  {'─'*12}  {'─'*30}")
    for key, label in (("quick_wins","Quick Win"),("recommended","Recommended"),("maximum","Maximum")):
        row = _tier_row_str(label, brief["tiers"].get(key, {}))
        if row: print(row)

    # ── LLM narrative ─────────────────────────────────────────────────────────
    if brief.get("verdict"):
        print(f"\n  {bold('ASSESSMENT')}")
        print(f"  {brief['verdict']}")
    if brief.get("action"):
        print(f"\n  {bold('RECOMMENDED FIRST ACTION')}")
        print(f"  {brief['action']}")

    # ── Data gaps ─────────────────────────────────────────────────────────────
    if gaps:
        print(f"\n  {amber('DATA GAPS')}")
        for g in gaps:
            print(f"  {amber('⚠')} {dim(g)}")

    # ── Footer ─────────────────────────────────────────────────────────────────
    print(f"\n  {dim('─' * (W-2))}")
    snap_note = green("✓ snapshot saved") if save else dim("snapshot skipped (--no-save)")
    prev_note = dim(f"prev: {delta['prev_date']}") if delta else dim("first run")
    print(f"  {snap_note}   {prev_note}")
    print()

    if not save:
        return

    # ── Write snapshot JSON ────────────────────────────────────────────────────
    snap = {
        "arch":          brief["arch"],
        "date":          brief["date"],
        "confidence":    brief["confidence"],
        "risk":          brief["risk"],
        "defensibility": brief["defensibility"],
        "known_critical": brief["known_critical"],
        "known_high":    brief["known_high"],
        "unsure_count":  brief["unsure_count"],
        "redesign":      brief["redesign"],
        "top_findings":  [
            {"description":    f["description"][:200],
             "source":         f["source"],
             "severity":       f["severity"],
             "critic_count":   f["critic_count"],
             "recommendation": f.get("recommendation", "")[:300],
             "ap_context":     f.get("ap_context", []),
             "t_codes":        f.get("t_codes", [])}
            for f in brief["top_findings"]
        ],
        "tiers": {
            k: {"cost": v.get("cost"), "effort": v.get("effort"),
                "risk_reduction": v.get("risk_reduction"), "practical_verdict": v.get("practical_verdict"),
                "rationale": v.get("rationale", ""), "items": v.get("items", [])}
            for k, v in brief["tiers"].items() if v
        },
        "ciso_advisor_verdict": brief.get("ciso_advisor_verdict", ""),
        "ciso_advisor_action":  brief.get("ciso_advisor_action",  ""),
    }
    snap_path = report_dir / "ciso_brief_latest.json"
    snap_path.write_text(json.dumps(snap, indent=2))

    # ── Write dated MD brief ───────────────────────────────────────────────────
    md_content = _build_md(brief, delta, gaps)
    md_path = report_dir / f"ciso_brief_{brief['date']}.md"
    md_path.write_text(md_content)

    print(f"  {dim('Snapshot: ' + str(snap_path.relative_to(REPO)))}")
    print(f"  {dim('Brief MD: ' + str(md_path.relative_to(REPO)))}")


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR — run the 4-stage pipeline for one architecture
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(arch: str, report_root: Path,
                 use_llm: bool = True, save: bool = True,
                 show_plan: bool = True) -> dict:
    """Run PLAN → BUILD → LOOK → RELEASE for one architecture. Returns brief dict."""
    report_dir = report_root / arch

    # PLAN
    plan = stage_plan(report_dir)
    if show_plan:
        print_plan(arch, plan)

    if plan["blocking"]:
        print(f"\n  {red('BLOCKED')} — cannot generate brief without ground_truth.json")
        return {}

    # BUILD (delta needed for LLM narrative, compute LOOK first)
    # We do a pre-LOOK to pass delta to the LLM, then final LOOK after build
    pre_snap_path = report_dir / "ciso_brief_latest.json"
    pre_delta: dict = {}
    if pre_snap_path.exists():
        try:
            prev = json.loads(pre_snap_path.read_text())
            pre_delta = {"prev_date": prev.get("date", "?")}
        except Exception:
            pass

    print(f"\n  {bold('BUILD')}  {dim('computing metrics + narrative...')}")
    brief = stage_build(arch, plan, pre_delta, use_llm)

    # LOOK (full delta now that brief is built)
    delta = stage_look(report_dir, brief)

    # RELEASE (print + write)
    print(f"\n  {bold('RELEASE')}")
    stage_release(report_dir, brief, delta, plan["gaps"], save)

    return {
        "arch": arch, "risk": brief["risk"], "confidence": brief["confidence"],
        "defensibility": brief["defensibility"], "known_critical": brief["known_critical"],
        "unsure_count": brief["unsure_count"], "redesign": brief["redesign"],
        "has_delta": bool(delta),
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(description="CISO security brief (plan→build→look→release)")
    ap.add_argument("arch",      nargs="?",           help="Architecture name")
    ap.add_argument("--corpus",  action="store_true", help="Run on all architectures")
    ap.add_argument("--top",     type=int, default=0, help="Corpus: top N by risk score")
    ap.add_argument("--no-llm",  action="store_true", help="Skip LLM narrative")
    ap.add_argument("--no-save", action="store_true", help="Skip snapshot file write")
    args = ap.parse_args()

    report_root = REPO / "report"
    use_llm = not args.no_llm
    save    = not args.no_save

    if args.corpus:
        dirs = sorted(
            [d for d in report_root.iterdir()
             if d.is_dir() and (d / "ground_truth.json").exists()],
            key=lambda d: d.name
        )
        results = []
        for d in dirs:
            r = run_pipeline(d.name, report_root, use_llm=use_llm, save=save, show_plan=False)
            if r:
                results.append(r)

        results.sort(key=lambda x: -x["risk"])
        if args.top:
            results = results[:args.top]

        print(bold(f"\n  CORPUS SUMMARY — {len(results)} architectures"))
        print(f"  {'Architecture':<35}  {'Risk':>4}  {'Conf':>6}  {'Crit':>4}  {'Trend':>5}  Status")
        print(f"  {'─'*35}  {'─'*4}  {'─'*6}  {'─'*4}  {'─'*5}  {'─'*14}")
        for r in results:
            risk_c = red if r["risk"] >= 70 else amber if r["risk"] >= 40 else green
            conf_c = _conf_color(r["confidence"])
            conf_s = conf_c(f"{r['confidence']:.0f}%")
            trend  = green("↑") if r.get("has_delta") else dim("—")
            redesign_f = red(" ⚠") if r["redesign"] else ""
            print(f"  {r['arch']:<35}  {risk_c(str(r['risk'])):>4}  {conf_s:>6}  "
                  f"{r['known_critical']:>4}  {trend:>5}  "
                  f"{_interp_label(r['confidence'])}{redesign_f}")
        print()
    else:
        if args.arch:
            arch = args.arch
        else:
            dirs = sorted(
                [d for d in report_root.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime, reverse=True
            )
            if not dirs:
                print(red("No report directories found."), file=sys.stderr)
                sys.exit(1)
            arch = dirs[0].name

        if not (report_root / arch).exists():
            print(red(f"No report directory for '{arch}'"), file=sys.stderr)
            sys.exit(1)

        run_pipeline(arch, report_root, use_llm=use_llm, save=save)


if __name__ == "__main__":
    main()
