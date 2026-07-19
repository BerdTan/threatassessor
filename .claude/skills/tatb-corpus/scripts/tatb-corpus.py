#!/usr/bin/env python3
"""
TATB Corpus Scorer — TA Test Benchmark across all /report/ architectures.

Usage:
    python3 .claude/skills/tatb-corpus [--report-dir PATH] [--json] [--sort RUBRIC]

Outputs a visual map showing all four TATB dimensions per architecture.
No UI required — pure CLI. Gracefully degrades when only GT is available.

Sort options: threat, ttp, risk, plan, overall (default: overall)

Exit codes: 0=ok, 1=no reports found
"""

import json
import os
import re
import sys
import argparse
import urllib.request
from pathlib import Path
from typing import Optional


# ─── Rubric scoring (mirrors _computeTatbScores in dashboard.js) ─────────────

def _adr_populated(v):
    if v is None: return False
    if isinstance(v, str): return len(v.strip()) > 20
    if isinstance(v, list): return len(v) > 0
    if isinstance(v, dict): return len(v) > 0
    return False


def score_threat(gt: dict) -> dict:
    aps     = gt.get('expected_attack_paths', [])
    pn      = (gt.get('metadata') or {}).get('parsed_nodes', {})
    pn_ids  = list(pn.keys())

    bound, nodes_in, entry_nodes = 0, set(), set()
    for ap in aps:
        entry = ap.get('entry_node') or ap.get('entry') or (ap.get('path') or [None])[0]
        if entry and entry in pn_ids:
            bound += 1
            entry_nodes.add(entry)
        for n in (ap.get('path') or []):
            if n in pn_ids: nodes_in.add(n)
        if entry and entry in pn_ids: nodes_in.add(entry)

    node_binding   = round(bound / len(aps) * 100) if aps else 0
    node_coverage  = round(len(nodes_in) / len(pn_ids) * 100) if pn_ids else 50
    all_techs      = set(t for ap in aps for t in ap.get('techniques', []))
    tech_variety   = min(100, round(len(all_techs) / 12 * 100))
    sigs           = [','.join(sorted(ap.get('techniques', []))) for ap in aps]
    all_identical  = len(sigs) >= 2 and len(set(sigs)) == 1
    penalty        = 20 if all_identical else 0

    score = max(0, round(node_binding * 0.40 + node_coverage * 0.25 + tech_variety * 0.35 - penalty))
    return {
        'score': score,
        'node_binding': node_binding,
        'node_coverage': node_coverage,
        'tech_variety': tech_variety,
        'all_identical': all_identical,
        'n_aps': len(aps),
        'n_nodes': len(pn_ids),
        'n_techs': len(all_techs),
    }


def score_ttp(gt: dict, moe: Optional[dict], mitre_mits: dict, mit_names: dict) -> dict:
    tv = gt.get('technique_validation') or \
         (gt.get('validation_report', {}).get('validations', {}).get('technique_relevance', []))

    confirmed = sum(1 for v in tv if v.get('valid') is True
                    and 'generic' not in (v.get('reason') or '').lower()
                    and 'keyword' not in (v.get('reason') or '').lower())
    plausible = sum(1 for v in tv if v.get('valid') is True
                    and ('generic' in (v.get('reason') or '').lower()
                         or 'keyword' in (v.get('reason') or '').lower()))
    val_pct   = round((confirmed * 1.0 + plausible * 0.5) / len(tv) * 100) if tv else 50

    # Cross-critic from MoE.
    # Use technique_support counts when available (Phase 4+) — excludes mandatory=True
    # (Blackhat/RedTeam-only chain findings never expected to appear in other critics).
    # Falls back to blob regex for pre-Phase-4 reports.
    cross_pct = 0
    ts = (moe or {}).get('technique_support')
    if ts:
        eligible = {t: d for t, d in ts.items() if not d.get('mandatory', False)}
        cross_v  = sum(1 for d in eligible.values() if d.get('count', 0) >= 2)
        cross_pct = round(cross_v / len(eligible) * 100) if eligible else 0
    else:
        ev = (moe or {}).get('expert_validations', {})
        if ev:
            crit_techs = {}
            for k in ['architect', 'tester', 'red_team', 'purple_team', 'blackhat']:
                blob = json.dumps(ev.get(k, {}))
                ids  = list(set(re.findall(r'T\d{4}(?:\.\d{3})?', blob)))
                crit_techs[k] = set(ids)
            all_t = set(t for s in crit_techs.values() for t in s)
            cross_v = sum(1 for t in all_t if sum(1 for s in crit_techs.values() if t in s) >= 2)
            cross_pct = round(cross_v / len(all_t) * 100) if all_t else 0

    # MoE lift
    moe_conf   = (moe or {}).get('confidence', {})
    moe_lift   = ((moe_conf.get('final', 0) - moe_conf.get('base', 0)) / 100
                  if moe_conf.get('final') is not None and moe_conf.get('base') is not None else 0)
    moe_score  = max(0, min(100, 50 + moe_lift * 500))

    # MITRE alignment
    SYNONYMS = {
        'mfa': ['multi-factor','authentication'],
        'waf': ['filter network','web application firewall','application layer'],
        'edr': ['endpoint detection','behavior prevention','endpoint'],
        'dlp': ['data loss prevention'],
        'backup': ['data backup','recovery','backup'],
        'least privilege': ['privileged account','account management','restrict','limit access'],
        'rate limiting': ['filter network traffic','limit access to resource','restrict'],
        'input validation': ['exploit protection','application isolation','update software'],
        'vulnerability scanning': ['update software','patch','vulnerability'],
        'logging': ['audit','monitoring','log'],
        'audit log': ['audit','monitoring','log'],
        'patching': ['update software','patch'],
        'user training': ['user training','security awareness'],
        'network segmentation': ['network segmentation','segment'],
        'api gateway': ['filter network','application layer','web application'],
        'behavioral analysis': ['behavior prevention','restrict execution','audit'],
        'web content filtering': ['restrict web-based','filter network'],
    }

    def ctrl_matches(ctrl, mit_name):
        c, m = ctrl.lower(), mit_name.lower()
        if c in m or m in c: return True
        for abbrev, exps in SYNONYMS.items():
            if abbrev in c or c in abbrev:
                if any(e in m for e in exps): return True
        cw = set(w for w in c.split() if len(w) > 4)
        mw = set(w for w in m.split() if len(w) > 4)
        return bool(cw & mw)

    # MITRE alignment — primary: M-ID set intersection; fallback: name/synonym matching.
    ctrls = gt.get('control_recommendations', [])
    aligned, checked, seen = 0, 0, set()
    for c in ctrls:
        ctrl_name = (c.get('control') or '').lower()
        ctrl_mids  = set(c.get('mitigations') or [])
        for tid in (c.get('mitre_techniques') or c.get('techniques') or []):
            if tid.startswith("AML."): continue
            pair = f'{tid}::{ctrl_name}'
            if pair in seen: continue
            seen.add(pair)
            mitre_mids_for_t = set(mitre_mits.get(tid, []))
            if not mitre_mids_for_t: continue
            checked += 1
            if ctrl_mids & mitre_mids_for_t:
                aligned += 1
            else:
                names = [mit_names.get(mid, '') for mid in mitre_mids_for_t]
                if ctrl_mids or any(ctrl_matches(ctrl_name, n) for n in names if n):
                    aligned += 1
    mitre_pct = round(aligned / checked * 100) if checked else 50

    score = round(val_pct * 0.30 + mitre_pct * 0.30 + cross_pct * 0.25 + moe_score * 0.15)
    return {
        'score': score,
        'val_pct': val_pct,
        'confirmed': confirmed, 'plausible': plausible,
        'cross_pct': cross_pct,
        'moe_lift_pp': round(moe_lift * 100, 1),
        'mitre_pct': mitre_pct,
        'mitre_checked': checked,
        'has_moe': moe is not None,
    }


def score_risk(gt: dict, gov: Optional[dict]) -> dict:
    aps   = gt.get('expected_attack_paths', [])
    adrs  = gt.get('architecture_decision_records', [])
    rr    = (gt.get('residual_risks') or {}).get('per_threat', {})
    ctrls = gt.get('control_recommendations', [])

    # A. Technique mitigation coverage (arch-wide)
    ap_techs    = set(t for ap in aps for t in ap.get('techniques', []))
    mit_techs   = set(t for c in ctrls for t in (c.get('mitre_techniques') or c.get('techniques') or []))
    tech_cov    = round(len(ap_techs & mit_techs) / len(ap_techs) * 100) if ap_techs else 50

    # A2. Per-(AP-index, technique) alignment — stronger than tech_cov
    ap_tech_pairs = {(i, t) for i, ap in enumerate(aps) for t in ap.get('techniques', [])}
    covered_pairs = set()
    for c in ctrls:
        c_aps   = set(c.get('attack_paths') or [])
        c_techs = set(c.get('mitre_techniques') or c.get('techniques') or [])
        for pair in ap_tech_pairs:
            if pair[0] in c_aps and pair[1] in c_techs:
                covered_pairs.add(pair)
    ap_cov = round(len(covered_pairs) / len(ap_tech_pairs) * 100) if ap_tech_pairs else 50

    # B. Hop layer completeness
    all_hops    = [h for a in adrs for h in a.get('hops', [])]
    full_hops   = sum(1 for h in all_hops
                      if 'missing' not in (h.get('gap_note') or h.get('gap_type') or '').lower())
    hop_pct     = round(full_hops / len(all_hops) * 100) if all_hops else 50

    # C. Hard-to-defend residual
    rr_vals     = list(rr.values())
    hard_ct     = sum(1 for r in rr_vals if r.get('status') in ('MONITOR', 'MITIGATE'))
    hard_pct    = round((len(rr_vals) - hard_ct) / len(rr_vals) * 100) if rr_vals else 50

    score = round(tech_cov * 0.30 + ap_cov * 0.15 + hop_pct * 0.30 + hard_pct * 0.25)
    return {
        'score': score,
        'tech_cov': tech_cov,
        'ap_cov': ap_cov,
        'hop_pct': hop_pct,
        'hard_pct': hard_pct,
        'n_hops': len(all_hops),
        'full_hops': full_hops,
        'hard_threats': hard_ct,
        'total_threats': len(rr_vals),
        'has_gov': gov is not None,
    }


def score_plan(gt: dict, sm: Optional[dict]) -> dict:
    aps   = gt.get('expected_attack_paths', [])
    adrs  = gt.get('architecture_decision_records', [])
    items = (sm or {}).get('action_plan', [])

    if not items:
        return {'score': None, 'reason': 'no SM data'}

    # A. Item completeness
    complete = [it for it in items
                if len((it.get('action') or '').strip()) > 10
                and len((it.get('rationale') or '').strip()) > 10
                and len((it.get('first_step') or '').strip()) > 10
                and len((it.get('effort') or '').strip()) > 0]
    comp_pct = round(len(complete) / len(items) * 100)

    # B. Measurable outcomes
    measurable = [it for it in items
                  if float(it.get('confidence_gain') or 0) > 0
                  or (it.get('risk_reduction_estimate') or '').lower() in ('high', 'medium')]
    meas_pct = round(len(measurable) / len(items) * 100)

    # C. Sprint spreadability
    effort_set = set((it.get('effort') or '').lower() for it in items if it.get('effort'))
    prio_set   = set((it.get('priority') or '').lower() for it in items if it.get('priority'))
    all_crit_w = all(it.get('priority') == 'critical' and it.get('effort') == 'weeks' for it in items)
    sprint_pct = 30 if all_crit_w else (100 if len(effort_set) >= 2 and len(prio_set) >= 2
                                        else 65 if len(effort_set) >= 2 or len(prio_set) >= 2 else 40)

    # D. Control specificity
    SPEC = re.compile(
        r'\b(install|deploy|configure|enable|enforce|integrate|add|block|scan|segment|monitor|'
        r'firewall|WAF|ACL|IAM|MFA|RASP|DAM|SIEM|DLP|EDR|Snyk|Grype|OWASP|Docker|Redis|node|'
        r'database|pipeline|CI.?CD|policy|rule|cert|token|AP-\d+|T\d{4})\b', re.I)
    spec_ct = sum(1 for it in items if SPEC.search((it.get('first_step') or '') + ' ' + (it.get('action') or '')))
    spec_pct = round(spec_ct / len(items) * 100)

    # E. ADR alignment — high-priority items should reference ADR-mandated controls
    adr_controls = set()
    for adr in adrs:
        for hop in (adr.get('hops') or []):
            for ctrl in (hop.get('controls') or []):
                name = (ctrl.get('name') or '').lower().strip()
                if name:
                    adr_controls.add(name)
    if adr_controls:
        high_items = [it for it in items if (it.get('priority') or '').lower() in ('critical', 'high')]
        if high_items:
            aligned = sum(1 for it in high_items
                          if any(c in ((it.get('first_step') or '') + ' ' + (it.get('action') or '')).lower()
                                 for c in adr_controls))
            adr_align_pct = round(aligned / len(high_items) * 100)
        else:
            adr_align_pct = 50
    else:
        adr_align_pct = 50

    # F. AP closure
    crit_aps = [ap for ap in aps if ap.get('criticality_tier') == 'CRITICAL']
    addr     = [ap for ap in crit_aps
                if any(ap.get('id', '') in ((it.get('action') or '') + (it.get('rationale') or ''))
                       for it in items)]
    closure_pct = round(len(addr) / len(crit_aps) * 100) if crit_aps else 100
    anti_bonus  = 5 if any(str(it.get('is_antipattern', '')).lower() == 'true' for it in items) else 0

    score = min(100, round(comp_pct * 0.25 + meas_pct * 0.20 + sprint_pct * 0.15
                           + spec_pct * 0.10 + adr_align_pct * 0.10 + closure_pct * 0.20 + anti_bonus))
    return {
        'score': score,
        'comp_pct': comp_pct,
        'meas_pct': meas_pct,
        'sprint_pct': sprint_pct,
        'spec_pct': spec_pct,
        'adr_align_pct': adr_align_pct,
        'closure_pct': closure_pct,
        'n_items': len(items),
        'n_crit_aps': len(crit_aps),
        'n_addr': len(addr),
        'n_adr_controls': len(adr_controls),
    }


# ─── Loading ──────────────────────────────────────────────────────────────────

def load_arch(arch_dir: Path):
    def _load(name):
        p = arch_dir / name
        return json.load(open(p)) if p.exists() else None

    return (
        _load('ground_truth.json'),
        _load('governance_signals.json'),
        _load('07_moe_orchestrator.json'),
        _load('08_scrum_master.json'),
    )


def fetch_mitre_data(tech_ids: list) -> tuple[dict, dict]:
    """Fetch technique→M-ID mappings and M-ID→name from the API in batches of 50."""
    if not tech_ids:
        return {}, {}
    try:
        mits: dict = {}
        # API limit: max 50 technique IDs per request
        for i in range(0, len(tech_ids), 50):
            batch = tech_ids[i:i + 50]
            url = f'http://localhost:8000/api/v1/technique-mitigations?technique_ids={",".join(batch)}'
            batch_mits = json.loads(urllib.request.urlopen(url, timeout=10).read()).get('mappings', {})
            mits.update(batch_mits)
        all_mids = list({m for mlist in mits.values() for m in mlist})
        if not all_mids:
            return mits, {}
        url2  = f'http://localhost:8000/api/v1/mitigations?mitigation_ids={",".join(all_mids)}'
        names = json.loads(urllib.request.urlopen(url2, timeout=10).read()).get('mitigations', {})
        return mits, names
    except Exception:
        return {}, {}


# ─── Visual output ────────────────────────────────────────────────────────────

BANDS = [
    (85, '■', '\033[92m'),   # Excellent — bright green
    (70, '▲', '\033[32m'),   # Solid     — green
    (50, '●', '\033[33m'),   # Weak      — amber
    (0,  '▼', '\033[31m'),   # Draft     — red
]
RESET = '\033[0m'
GREY  = '\033[90m'
BOLD  = '\033[1m'


def band(s):
    """Return (char, ansi_color, label) for a score 0-100 or None."""
    if s is None:
        return ('?', GREY, 'N/A')
    for threshold, char, color in BANDS:
        if s >= threshold:
            return (char, color, ['Excellent','Solid','Weak','Draft'][[85,70,50,0].index(threshold)])
    return ('▼', '\033[31m', 'Draft')


def bar(s, width=10):
    """Text progress bar — filled blocks proportional to score."""
    if s is None:
        return GREY + '?' * width + RESET
    filled = round(s / 100 * width)
    _, color, _ = band(s)
    return color + '█' * filled + GREY + '░' * (width - filled) + RESET


def render_table(results: list, sort_col: str, use_color: bool):
    """Render the main corpus table."""

    def _s(r, col):
        v = r['scores'].get(col)
        return v.get('score') if isinstance(v, dict) else None

    results.sort(key=lambda r: (_s(r, sort_col) or -1), reverse=True)

    W = 14  # bar width
    # Header
    cols = ['Threat-Rel', 'TTP-Acc', 'Risk-Def', 'Plan-Act', 'Overall']
    hdr_name = f"{'Architecture':<30}"
    hdr_cols = '  '.join(f'{c:<{W+6}}' for c in cols)
    sep = '─' * (30 + 2 + (W + 8) * 5)

    if use_color:
        print(BOLD + hdr_name + '  ' + hdr_cols + RESET)
    else:
        print(hdr_name + '  ' + hdr_cols)
    print(sep)

    for r in results:
        name = r['arch'][:29]
        scores_row = []
        for col in ['threat', 'ttp', 'risk', 'plan', 'overall']:
            v   = r['scores'].get(col)
            scr = v.get('score') if isinstance(v, dict) else None
            ch, col_c, lbl = band(scr)
            num = f'{scr:3d}' if scr is not None else ' N/A'
            b   = bar(scr, W)
            if use_color:
                cell = f'{col_c}{ch}{RESET} {num} {b}'
            else:
                cell = f'{ch} {num} {"█"*round((scr or 0)/100*W) if scr else "?"*W}'
            scores_row.append(cell)
        print(f'{name:<30}  ' + '  '.join(scores_row))

    print(sep)


def render_heatmap(results: list, use_color: bool):
    """Render a compact heatmap — one char per arch per dimension."""
    dims   = ['threat', 'ttp', 'risk', 'plan']
    labels = ['Threat', 'TTP  ', 'Risk ', 'Plan ']
    print()
    if use_color:
        print(BOLD + 'Corpus heatmap — each column = one architecture' + RESET)
    else:
        print('Corpus heatmap — each column = one architecture')

    # Sort architectures by overall for heatmap
    sorted_r = sorted(results, key=lambda r: (r['scores'].get('overall', {}).get('score') or 0))
    names_row = ''.join(r['arch'][0].upper() for r in sorted_r)

    for i, (dim, lbl) in enumerate(zip(dims, labels)):
        row = ''
        for r in sorted_r:
            v   = r['scores'].get(dim, {})
            scr = v.get('score') if isinstance(v, dict) else None
            ch, col, _ = band(scr)
            row += (col + ch + RESET) if use_color else ch
        print(f'  {lbl}  {row}')

    # Architecture labels (abbreviated)
    print(f'  {"Arch ":6}', end='')
    for r in sorted_r:
        sys.stdout.write(GREY + r['arch'][0].upper() + RESET if use_color else r['arch'][0].upper())
    print()
    print(f'         (sorted worst→best by overall score)')


def render_stage_attribution(results: list, use_color: bool):
    """Show which pipeline stages to investigate based on corpus patterns."""
    dim_scores = {d: [] for d in ['threat', 'ttp', 'risk', 'plan']}
    sub_scores = {
        'node_binding': [], 'node_coverage': [], 'tech_variety': [],
        'val_pct': [], 'mitre_pct': [], 'cross_pct': [],
        'tech_cov': [], 'ap_cov': [], 'hop_pct': [], 'hard_pct': [],
        'comp_pct': [], 'meas_pct': [], 'closure_pct': [],
    }
    for r in results:
        for dim in ['threat', 'ttp', 'risk', 'plan']:
            v = r['scores'].get(dim, {})
            if isinstance(v, dict) and v.get('score') is not None:
                dim_scores[dim].append(v['score'])
        for sub, lst in sub_scores.items():
            for dim in ['threat', 'ttp', 'risk', 'plan']:
                v = r['scores'].get(dim, {})
                if isinstance(v, dict) and sub in v:
                    lst.append(v[sub])

    def avg(lst):
        return round(sum(lst) / len(lst)) if lst else None

    print()
    if use_color:
        print(BOLD + 'Pipeline stage attribution — corpus averages' + RESET)
    else:
        print('Pipeline stage attribution — corpus averages')
    print('─' * 60)

    STAGE_MAP = [
        ('node_binding',   'AnalysisStage → ground_truth_generator (entry node extraction)'),
        ('node_coverage',  'AnalysisStage → path-finding hop depth'),
        ('tech_variety',   'AnalysisStage → RAPIDS + structural technique inference'),
        ('val_pct',        'QualityStage → self_validation.py (heuristic thresholds)'),
        ('mitre_pct',      'ReportStage → exhaustive_mitigation_mapper (M-ID coverage)'),
        ('cross_pct',      'CriticStage → MoE critic diversity (run full_moe)'),
        ('tech_cov',       'ReportStage → control_recommendations technique mapping (arch-wide)'),
        ('ap_cov',         'ReportStage → control_recommendations attack_paths field (per-AP alignment)'),
        ('hop_pct',        'ReportStage → ADR generator (dir_category assignment)'),
        ('hard_pct',       'Architecture — structural exposure (design change needed)'),
        ('comp_pct',       'ScrumMasterStage → SM prompt (item field completeness)'),
        ('meas_pct',       'ScrumMasterStage → SM prompt (confidence_gain/risk_reduction)'),
        ('closure_pct',    'ScrumMasterStage → SM prompt (AP-ID references in actions)'),
    ]

    for sub, stage in STAGE_MAP:
        a = avg(sub_scores[sub])
        if a is None: continue
        ch, col, lbl = band(a)
        line = f'  {sub:<20}  avg={a:3d}%  {stage}'
        if use_color:
            print(col + ch + RESET + '  ' + line)
        else:
            print(ch + '  ' + line)

    print()
    weakest_dim = min(dim_scores.items(), key=lambda kv: avg(kv[1] or [100]) or 100)
    wa = avg(weakest_dim[1])
    print(f'  Weakest dimension across corpus: {weakest_dim[0].upper()}  (avg {wa}%)')
    print(f'  → Prioritise the stage(s) marked ▼ or ● above for the highest corpus-wide gain.')


# ─── Main ─────────────────────────────────────────────────────────────────────

def _resolve_labeller_model() -> str:
    """Return the configured TATB labeller model, falling back to Haiku if unset."""
    raw = os.getenv('AGENT_MODEL_TATB_LABELLER', 'bedrock/us.amazon.nova-pro-v1:0')
    return raw if raw.startswith('bedrock/') else f'bedrock/{raw}'


def _mmd_for_arch(arch_name: str, report_dir: Path) -> Optional[str]:
    """Find the .mmd source for an arch — checks report dir first, then tests/data."""
    repo = Path(__file__).parents[4]  # …/DEV-TEST
    candidates = [
        report_dir / arch_name / 'before.mmd',
        repo / 'tests' / 'data' / 'architectures' / f'{arch_name}.mmd',
        # strip trailing _N suffix and retry
        repo / 'tests' / 'data' / 'architectures' / (re.sub(r'_\d+$', '', arch_name) + '.mmd'),
    ]
    for p in candidates:
        if p.exists():
            return p.read_text(encoding='utf-8')
    return None


def auto_label(report_dir: Path, force: bool, use_color: bool):
    """
    Auto-generate expected_threats.json for each arch that is missing one,
    using the TATB labeller model (Nova Pro by default — independent of pipeline).

    Writes to report/<arch>/expected_threats.json (co-located with ground_truth.json).
    Idempotent — skips existing labels unless --force.
    """
    sys.path.insert(0, str(Path(__file__).parents[4]))
    try:
        from agentic.helper import load_env
        load_env()
        from agentic.llm_client import LLMClient, LLMProvider
    except ImportError as e:
        print(f'  Auto-label requires agentic/llm_client — {e}', file=sys.stderr)
        return

    model    = _resolve_labeller_model()
    fallback = os.getenv('AGENT_MODEL_TATB_LABELLER_FALLBACK', 'bedrock/us.anthropic.claude-haiku-4-20250514-v1:0')
    client   = LLMClient(primary_provider=LLMProvider.BEDROCK)

    arch_dirs = sorted([d for d in report_dir.iterdir()
                        if d.is_dir() and (d / 'ground_truth.json').exists()])
    if not arch_dirs:
        print('  No architectures found.', file=sys.stderr)
        return

    skipped = labeled = failed = 0
    for arch_dir in arch_dirs:
        label_path = arch_dir / 'expected_threats.json'
        if label_path.exists() and not force:
            skipped += 1
            continue

        mmd = _mmd_for_arch(arch_dir.name, report_dir)
        if not mmd:
            print((('\033[33m' if use_color else '') +
                   f'  SKIP {arch_dir.name} — no .mmd source found' +
                   ('\033[0m' if use_color else '')))
            skipped += 1
            continue

        prompt = f"""You are an independent threat-modelling expert acting as a TATB (TA Test Benchmark) verifier.
Your task: given only the architecture diagram below, identify the MITRE ATT&CK technique IDs that a competent threat analyst should expect to find in a thorough threat model for this architecture.

Rules:
- Base your answer ONLY on the topology shown — do not assume techniques the diagram does not support.
- Include techniques that are clearly applicable given the node types and connectivity.
- Output ONLY valid JSON in this exact format, no prose:
{{"techniques": ["T1190", "T1059", ...], "notes": "one sentence rationale"}}

Architecture diagram ({arch_dir.name}):
{mmd[:6000]}"""

        try:
            for attempt_model in [model, fallback]:
                try:
                    resp = client.generate(prompt=prompt, model=attempt_model, max_tokens=400)
                    text = resp.content if hasattr(resp, 'content') else str(resp)
                    # Extract JSON from response
                    match = re.search(r'\{[^{}]*"techniques"\s*:\s*\[[^\]]*\][^{}]*\}', text, re.DOTALL)
                    if not match:
                        raise ValueError(f'No valid JSON found in response: {text[:200]}')
                    label = json.loads(match.group(0))
                    if not isinstance(label.get('techniques'), list):
                        raise ValueError('techniques must be a list')
                    # Normalise — uppercase, filter valid T-IDs
                    label['techniques'] = sorted(set(
                        t.upper() for t in label['techniques']
                        if re.match(r'^T\d{4}(\.\d{3})?$', str(t).strip(), re.I)
                    ))
                    label['labeller_model'] = attempt_model
                    label['arch']           = arch_dir.name
                    label_path.write_text(json.dumps(label, indent=2))
                    col = '\033[92m' if use_color else ''
                    rst = '\033[0m'  if use_color else ''
                    print(f"  {col}LABELLED{rst} {arch_dir.name} — {len(label['techniques'])} techniques via {attempt_model.split('/')[-1]}")
                    labeled += 1
                    break
                except Exception as inner:
                    if attempt_model == fallback:
                        raise inner
                    continue
        except Exception as e:
            col = '\033[31m' if use_color else ''
            rst = '\033[0m'  if use_color else ''
            print(f"  {col}FAILED{rst}  {arch_dir.name} — {str(e)[:120]}")
            failed += 1

    print()
    print(f'  Auto-label complete: {labeled} labelled, {skipped} skipped, {failed} failed')
    if labeled:
        print(f'  Labels written to report/<arch>/expected_threats.json')
        print(f'  Run with --regression to score recall/precision against these labels.')


def run_regression(report_dir: Path, label_dir: Path, use_color: bool):
    """
    Labelled-corpus regression: compare detected technique IDs against expected_threats.json.

    Label files are resolved in priority order:
      1. report/<arch>/expected_threats.json  (auto-labeller writes here)
      2. <label_dir>/<arch>/expected_threats.json  (manual labels)
    """
    # Collect all label files — co-located in report/ first, then label_dir
    seen = {}
    for lf in sorted(report_dir.glob('*/expected_threats.json')):
        seen[lf.parent.name] = lf
    for lf in sorted(label_dir.glob('*/expected_threats.json')):
        if lf.parent.name not in seen:
            seen[lf.parent.name] = lf

    if not seen:
        if use_color:
            print(GREY + '  No expected_threats.json files found.' + RESET)
        else:
            print('  No expected_threats.json files found.')
        print('  Run --auto-label to generate labels via Nova Pro, or create manually.')
        print('  Format: { "techniques": ["T1190", "T1059", ...], "notes": "optional" }')
        return

    rows = []
    for arch_name, lf in sorted(seen.items()):
        arch_dir  = report_dir / arch_name
        gt_path   = arch_dir / 'ground_truth.json'
        if not gt_path.exists():
            continue
        try:
            gt       = json.load(open(gt_path))
            expected = set(json.load(open(lf)).get('techniques', []))
            detected = set(t for ap in gt.get('expected_attack_paths', [])
                           for t in ap.get('techniques', []))
            # Parent-ID rollup: T1021 in detected covers T1021.001 in expected.
            # A subtechnique expected is satisfied if its parent (before the dot) was detected.
            def parent(t): return t.split('.')[0]
            detected_parents = {parent(t) for t in detected}
            covered = {t for t in expected if t in detected or parent(t) in detected_parents}
            uncovered = expected - covered
            tp       = len(covered)
            fp       = len(detected - expected)   # FP stays exact — no rollup for overcounting
            fn       = len(uncovered)
            recall    = round(tp / len(expected) * 100) if expected else 100
            precision = round(tp / (tp + fp) * 100)     if (tp + fp) else 0
            f1_num    = 2 * recall * precision
            f1        = round(f1_num / (recall + precision)) if (recall + precision) else 0
            rows.append({
                'arch': arch_name,
                'recall': recall, 'precision': precision, 'f1': f1,
                'tp': tp, 'fp': fp, 'fn': fn,
                'missed': sorted(uncovered),
                'extra':  sorted(detected - expected),
            })
        except Exception as e:
            rows.append({'arch': arch_name, 'error': str(e)})

    if not rows:
        print('  No labelled architectures matched report directories.')
        return

    def _col(v):
        if v is None: return GREY
        if v >= 90:   return '\033[92m'
        if v >= 75:   return '\033[32m'
        if v >= 60:   return '\033[33m'
        return '\033[31m'

    print()
    if use_color:
        print(BOLD + '📐 Labelled-Corpus Regression' + RESET)
    else:
        print('Labelled-Corpus Regression')
    print(f'  {len(rows)} labelled architecture(s) found\n')

    hdr = f"  {'Architecture':<30}  {'Recall':>7}  {'Precision':>9}  {'F1':>5}  {'TP':>4}  {'FP':>4}  {'FN':>4}"
    sep = '  ' + '─' * (len(hdr) - 2)
    print(hdr)
    print(sep)

    for r in rows:
        if 'error' in r:
            print(f"  {r['arch']:<30}  ERROR: {r['error']}")
            continue
        rc = _col(r['recall'])
        pc = _col(r['precision'])
        fc = _col(r['f1'])
        row = (f"  {r['arch']:<30}  "
               + (rc if use_color else '') + f"{r['recall']:>6}%" + (RESET if use_color else '') + '  '
               + (pc if use_color else '') + f"{r['precision']:>8}%" + (RESET if use_color else '') + '  '
               + (fc if use_color else '') + f"{r['f1']:>4}%" + (RESET if use_color else '') + '  '
               + f"{r['tp']:>4}  {r['fp']:>4}  {r['fn']:>4}")
        print(row)
        if r['missed']:
            missed_str = ', '.join(r['missed'][:8]) + (f' +{len(r["missed"])-8} more' if len(r['missed']) > 8 else '')
            print((GREY if use_color else '') + f"    ↳ Missed: {missed_str}" + (RESET if use_color else ''))

    # Corpus averages
    valid = [r for r in rows if 'error' not in r]
    if not valid:
        return

    avg_r = round(sum(r['recall']    for r in valid) / len(valid))
    avg_p = round(sum(r['precision'] for r in valid) / len(valid))
    avg_f = round(sum(r['f1']        for r in valid) / len(valid))
    print(sep)
    print(f"  {'Corpus average':<30}  {avg_r:>6}%  {avg_p:>8}%  {avg_f:>4}%")

    # ── Corpus health bar ─────────────────────────────────────────────────────
    print()
    rc = _col(avg_r); pc = _col(avg_p); fc = _col(avg_f)
    def _hbar(v, w=20):
        filled = round(v / 100 * w)
        _, color, _ = band(v) if v is not None else ('?', GREY, '')
        return (color if use_color else '') + '█'*filled + (GREY if use_color else '') + '░'*(w-filled) + (RESET if use_color else '')
    print(f"  Corpus health:")
    print(f"    Recall    {_hbar(avg_r)}  {(rc if use_color else '')}{avg_r}%{(RESET if use_color else '')}")
    print(f"    Precision {_hbar(avg_p)}  {(pc if use_color else '')}{avg_p}%{(RESET if use_color else '')}")
    print(f"    F1        {_hbar(avg_f)}  {(fc if use_color else '')}{avg_f}%{(RESET if use_color else '')}")

    # ── Top missed techniques frequency ──────────────────────────────────────
    from collections import Counter
    missed_freq = Counter(t for r in valid for t in r.get('missed', []))
    extra_freq  = Counter(t for r in valid for t in r.get('extra',  []))

    TECHNIQUE_NAMES = {
        # Initial Access
        'T1190': 'Exploit Public-Facing App',  'T1133': 'External Remote Services',
        'T1566': 'Phishing',                   'T1078': 'Valid Accounts',
        'T1189': 'Drive-by Compromise',        'T1199': 'Trusted Relationship',
        'T1195': 'Supply Chain Compromise',
        # Execution
        'T1059': 'Command & Scripting',        'T1203': 'Exploit Client Execution',
        'T1204.003': 'User Exec: Malicious Image',
        # Persistence
        'T1098': 'Account Manipulation',       'T1136': 'Create Account',
        'T1505': 'Server Software Component',  'T1505.003': 'Web Shell',
        'T1556': 'Modify Auth Process',
        # Privilege Escalation
        'T1068': 'Exploit Priv Escalation',    'T1548': 'Abuse Elevation Control',
        'T1134': 'Access Token Manipulation',
        # Defense Evasion
        'T1027': 'Obfuscated Files',           'T1036': 'Masquerading',
        'T1055': 'Process Injection',          'T1055.012': 'Process Hollowing',
        'T1070': 'Indicator Removal',          'T1078.004': 'Valid Cloud Accounts',
        'T1207': 'Rogue Domain Controller',    'T1562': 'Impair Defenses',
        'T1562.001': 'Disable Security Tools', 'T1578': 'Modify Cloud Compute',
        # Credential Access
        'T1003': 'OS Credential Dumping',      'T1040': 'Network Sniffing',
        'T1056': 'Input Capture',              'T1056.001': 'Keylogging',
        'T1056.002': 'GUI Input Capture',      'T1110': 'Brute Force',
        'T1111': 'MFA Interception',           'T1185': 'Browser Session Hijack',
        'T1212': 'Exploit Credential Access',  'T1539': 'Steal Web Session Cookie',
        'T1550': 'Use Alt Auth Material',      'T1552': 'Unsecured Credentials',
        'T1552.001': 'Credentials In Files',   'T1557': 'AiTM / MitM',
        # Discovery
        'T1018': 'Remote System Discovery',    'T1046': 'Network Svc Discovery',
        'T1049': 'System Network Connections', 'T1057': 'Process Discovery',
        'T1069': 'Permission Groups Discovery','T1082': 'System Info Discovery',
        'T1083': 'File & Dir Discovery',       'T1087': 'Account Discovery',
        'T1119': 'Automated Collection',       'T1135': 'Network Share Discovery',
        'T1201': 'Password Policy Discovery',  'T1482': 'Domain Trust Discovery',
        'T1590': 'Gather Victim Network Info', 'T1592': 'Gather Victim Host Info',
        'T1595': 'Active Scanning',
        # Lateral Movement
        'T1021': 'Remote Services',            'T1021.001': 'Remote Desktop Protocol',
        'T1021.002': 'SMB/Windows Admin Shares','T1021.004': 'SSH',
        'T1021.007': 'Cloud Services',         'T1210': 'Exploit Remote Services',
        'T1563': 'Remote Service Session Hijack','T1570': 'Lateral Tool Transfer',
        # Collection
        'T1005': 'Data from Local System',     'T1039': 'Data from Network Share',
        'T1074': 'Data Staged',                'T1114': 'Email Collection',
        'T1213': 'Data from Info Repositories','T1213.002': 'SharePoint',
        'T1530': 'Data from Cloud Storage',    'T1560': 'Archive Collected Data',
        # C2
        'T1071': 'Application Layer Protocol', 'T1071.001': 'Web Protocols',
        'T1090': 'Proxy',                      'T1102': 'Web Service',
        'T1572': 'Protocol Tunneling',         'T1573': 'Encrypted Channel',
        # Exfiltration
        'T1020': 'Automated Exfiltration',     'T1041': 'Exfil over C2 Channel',
        'T1048': 'Exfil Over Alt Protocol',    'T1537': 'Transfer to Cloud Account',
        'T1567': 'Exfil to Web Service',
        # Impact
        'T1485': 'Data Destruction',           'T1486': 'Data Encrypted for Impact',
        'T1489': 'Service Stop',               'T1490': 'Inhibit System Recovery',
        'T1491': 'Defacement',                 'T1496': 'Resource Hijacking',
        'T1498': 'Network DoS',                'T1499': 'Endpoint DoS',
        'T1529': 'System Shutdown/Reboot',     'T1531': 'Account Access Removal',
        'T1565': 'Data Manipulation',          'T1565.001': 'Stored Data Manipulation',
        # Reconnaissance
        'T1588.001': 'Obtain: Malware',        'T1588.002': 'Obtain: Tool',
        'T1588.006': 'Obtain: Vuln',           'T1589': 'Gather Victim Identity',
        # Resource Development / Other
        'T1648': 'Serverless Execution',
    }
    TACTIC_MAP = {
        # Initial Access
        'T1190': 'Initial Access',  'T1133': 'Initial Access',  'T1566': 'Initial Access',
        'T1078': 'Initial Access',  'T1189': 'Initial Access',  'T1199': 'Initial Access',
        'T1195': 'Initial Access',
        # Execution
        'T1059': 'Execution',       'T1203': 'Execution',       'T1648': 'Execution',
        # Persistence
        'T1098': 'Persistence',     'T1136': 'Persistence',     'T1505': 'Persistence',
        'T1505.003': 'Persistence', 'T1556': 'Persistence',
        # Privilege Escalation
        'T1068': 'Priv Escalation', 'T1548': 'Priv Escalation', 'T1134': 'Priv Escalation',
        # Defense Evasion
        'T1027': 'Defense Evasion', 'T1036': 'Defense Evasion', 'T1055': 'Defense Evasion',
        'T1055.012': 'Defense Evasion', 'T1070': 'Defense Evasion', 'T1078.004': 'Defense Evasion',
        'T1207': 'Defense Evasion', 'T1562': 'Defense Evasion', 'T1562.001': 'Defense Evasion',
        'T1578': 'Defense Evasion',
        # Credential Access
        'T1003': 'Credential Access', 'T1040': 'Discovery',     'T1056': 'Credential Access',
        'T1056.001': 'Credential Access', 'T1056.002': 'Credential Access',
        'T1110': 'Credential Access', 'T1111': 'Credential Access', 'T1185': 'Credential Access',
        'T1212': 'Credential Access', 'T1539': 'Credential Access', 'T1550': 'Credential Access',
        'T1552': 'Credential Access', 'T1552.001': 'Credential Access', 'T1557': 'Credential Access',
        # Discovery
        'T1018': 'Discovery',       'T1046': 'Discovery',       'T1049': 'Discovery',
        'T1057': 'Discovery',       'T1069': 'Discovery',       'T1082': 'Discovery',
        'T1083': 'Discovery',       'T1087': 'Discovery',       'T1119': 'Collection',
        'T1135': 'Discovery',       'T1201': 'Discovery',       'T1482': 'Discovery',
        'T1590': 'Reconnaissance',  'T1592': 'Reconnaissance',  'T1595': 'Reconnaissance',
        # Lateral Movement
        'T1021': 'Lateral Movement', 'T1021.001': 'Lateral Movement', 'T1021.002': 'Lateral Movement',
        'T1021.004': 'Lateral Movement', 'T1021.007': 'Lateral Movement',
        'T1210': 'Lateral Movement', 'T1563': 'Lateral Movement', 'T1570': 'Lateral Movement',
        # Collection
        'T1005': 'Collection',      'T1039': 'Collection',      'T1074': 'Collection',
        'T1114': 'Collection',      'T1213': 'Collection',      'T1213.002': 'Collection',
        'T1530': 'Collection',      'T1560': 'Collection',
        # C2
        'T1071': 'C2',              'T1071.001': 'C2',          'T1090': 'C2',
        'T1102': 'C2',              'T1572': 'C2',              'T1573': 'C2',
        # Exfiltration
        'T1020': 'Exfiltration',    'T1041': 'Exfiltration',    'T1048': 'Exfiltration',
        'T1537': 'Exfiltration',    'T1567': 'Exfiltration',
        # Impact
        'T1485': 'Impact',          'T1486': 'Impact',          'T1489': 'Impact',
        'T1490': 'Impact',          'T1491': 'Impact',          'T1496': 'Impact',
        'T1498': 'Impact',          'T1499': 'Impact',          'T1529': 'Impact',
        'T1531': 'Impact',          'T1565': 'Impact',          'T1565.001': 'Impact',
        # Resource Development
        'T1588.001': 'Resource Dev', 'T1588.002': 'Resource Dev', 'T1588.006': 'Resource Dev',
        'T1589': 'Reconnaissance',
    }

    n_archs = len(valid)
    top_missed = missed_freq.most_common(12)
    if top_missed:
        print()
        print((BOLD if use_color else '') + '  Top missed techniques (engine detection gaps):' + (RESET if use_color else ''))
        print(f"  {'Technique':<8}  {'Name':<34}  {'Tactic':<20}  {'Archs':<6}  Fix priority")
        print('  ' + '─'*85)
        for tid, cnt in top_missed:
            name   = TECHNIQUE_NAMES.get(tid, tid)
            tactic = TACTIC_MAP.get(tid, '?')
            pct    = round(cnt / n_archs * 100)
            bar_w  = round(pct / 100 * 14)
            pri    = 'HIGH' if pct >= 60 else 'MED' if pct >= 35 else 'LOW'
            pri_c  = ('\033[31m' if pct>=60 else '\033[33m' if pct>=35 else '\033[32m') if use_color else ''
            bar_s  = (pri_c if use_color else '') + '█'*bar_w + (GREY if use_color else '') + '░'*(14-bar_w) + (RESET if use_color else '')
            print(f"  {tid:<8}  {name:<34}  {tactic:<20}  {bar_s}  {cnt}/{n_archs} archs  {pri_c}{pri}{RESET if use_color else ''}")

    # ── Tactic coverage heatmap ───────────────────────────────────────────────
    tactic_missed = Counter(TACTIC_MAP.get(t, 'Other') for r in valid for t in r.get('missed', []))
    tactic_total  = Counter(TACTIC_MAP.get(t, 'Other') for r in valid
                            for t in (r.get('missed', []) + r.get('tp_list', r.get('missed', []))))
    if tactic_missed:
        print()
        print((BOLD if use_color else '') + '  Tactic coverage gaps (missed technique distribution):' + (RESET if use_color else ''))
        tactic_order = ['Initial Access','Execution','Persistence','Privilege Escalation',
                        'Defense Evasion','Credential Access','Discovery','Lateral Movement',
                        'Collection','C2','Exfiltration','Impact']
        for tac in tactic_order:
            cnt = tactic_missed.get(tac, 0)
            if cnt == 0: continue
            bar_w  = min(round(cnt / max(tactic_missed.values()) * 18), 18)
            _, color, _ = band(max(0, 100 - round(cnt / n_archs * 10)))
            bar_s  = (color if use_color else '') + '█'*bar_w + (GREY if use_color else '') + '░'*(18-bar_w) + (RESET if use_color else '')
            print(f"  {tac:<22}  {bar_s}  {cnt} gaps")

    # ── Fix-priority advice ───────────────────────────────────────────────────
    print()
    print((BOLD if use_color else '') + '  Fix-priority advice:' + (RESET if use_color else ''))
    high = [(tid, cnt) for tid, cnt in top_missed if round(cnt/n_archs*100) >= 60]
    med  = [(tid, cnt) for tid, cnt in top_missed if 35 <= round(cnt/n_archs*100) < 60]
    if high:
        ids = ', '.join(f"{tid} ({TECHNIQUE_NAMES.get(tid,tid)})" for tid,_ in high[:4])
        print(f"  HIGH  Fix in per_node_ttp_mapper.py: {ids}")
        print(f"        These are missed in ≥60% of labelled architectures — systematic gap.")
    if med:
        ids = ', '.join(f"{tid}" for tid,_ in med[:4])
        print(f"  MED   Review: {ids} — missed in 35–60% of archs.")
    if avg_r < 80:
        print()
        print((('\033[33m' if use_color else '') +
               f'  ⚠ Corpus recall {avg_r}% < 80% target — apply HIGH fixes then re-run --regression to verify lift.' +
               (RESET if use_color else '')))


def main():
    parser = argparse.ArgumentParser(description='TATB Corpus Scorer')
    parser.add_argument('--report-dir', default='report', help='Path to report directory')
    parser.add_argument('--json',       action='store_true', help='Output raw JSON instead of visual')
    parser.add_argument('--sort',       default='overall',
                        choices=['threat', 'ttp', 'risk', 'plan', 'overall'],
                        help='Sort column (default: overall)')
    parser.add_argument('--no-color',   action='store_true', help='Disable ANSI colours')
    parser.add_argument('--regression', action='store_true',
                        help='Run labelled-corpus regression against expected_threats.json files')
    parser.add_argument('--label-dir',  default='tests/data/architectures',
                        help='Fallback directory for manual label files (default: tests/data/architectures)')
    parser.add_argument('--auto-label', action='store_true',
                        help='Auto-generate expected_threats.json via Nova Pro labeller (skips existing)')
    parser.add_argument('--force',      action='store_true',
                        help='With --auto-label: regenerate labels even if they already exist')
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    if not report_dir.exists():
        print(f'Error: report directory not found: {report_dir}', file=sys.stderr)
        sys.exit(1)

    use_color = not args.no_color and sys.stdout.isatty()

    # Auto-label mode — run labeller then exit (or continue to scoring if --regression also set)
    if args.auto_label:
        print()
        print(('\033[1m' if use_color else '') + '🏷  TATB Auto-Labeller — Nova Pro' + ('\033[0m' if use_color else ''))
        print(f'  Model: {_resolve_labeller_model()}')
        print(f'  Fallback: {os.getenv("AGENT_MODEL_TATB_LABELLER_FALLBACK", "bedrock/us.anthropic.claude-haiku-4-20250514-v1:0")}')
        print()
        auto_label(report_dir, args.force, use_color)
        if not args.regression:
            return

    # Collect all architectures that have at least ground_truth.json
    arch_dirs = sorted([d for d in report_dir.iterdir()
                        if d.is_dir() and (d / 'ground_truth.json').exists()])
    if not arch_dirs:
        print('No architectures with ground_truth.json found.', file=sys.stderr)
        sys.exit(1)

    # Pre-fetch MITRE data: collect all technique IDs across all archs in one batch
    print(f'Scoring {len(arch_dirs)} architectures…', file=sys.stderr)
    all_tech_ids = set()
    gt_cache     = {}
    for d in arch_dirs:
        try:
            gt = json.load(open(d / 'ground_truth.json'))
            gt_cache[d.name] = gt
            for ap in gt.get('expected_attack_paths', []):
                all_tech_ids.update(ap.get('techniques', []))
        except Exception:
            pass

    print('Fetching MITRE mitigation data…', file=sys.stderr)
    mitre_mits, mit_names = fetch_mitre_data(list(all_tech_ids))
    if mitre_mits:
        print(f'  MITRE data loaded: {len(mitre_mits)} techniques, {len(mit_names)} mitigation names',
              file=sys.stderr)
    else:
        print('  MITRE data unavailable — alignment scores will be N/A (50% neutral)',
              file=sys.stderr)

    # Score each architecture
    results = []
    for d in arch_dirs:
        gt  = gt_cache.get(d.name)
        if gt is None: continue
        gov, moe, sm = None, None, None
        try:
            gov_p = d / 'governance_signals.json'
            if gov_p.exists(): gov = json.load(open(gov_p))
        except Exception: pass
        try:
            moe_p = d / '07_moe_orchestrator.json'
            if moe_p.exists(): moe = json.load(open(moe_p))
        except Exception: pass
        try:
            sm_p = d / '08_scrum_master.json'
            if sm_p.exists(): sm = json.load(open(sm_p))
        except Exception: pass

        t_scores = score_threat(gt)
        ttp_s    = score_ttp(gt, moe, mitre_mits, mit_names)
        r_scores = score_risk(gt, gov)
        p_scores = score_plan(gt, sm)

        valid_scores = [s['score'] for s in [t_scores, ttp_s, r_scores, p_scores]
                        if isinstance(s, dict) and s.get('score') is not None]
        overall = round(sum(valid_scores) / len(valid_scores)) if valid_scores else None

        results.append({
            'arch': d.name,
            'scores': {
                'threat':  t_scores,
                'ttp':     ttp_s,
                'risk':    r_scores,
                'plan':    p_scores,
                'overall': {'score': overall},
            },
            'data_available': {
                'gt': True, 'gov': gov is not None,
                'moe': moe is not None, 'sm': sm is not None,
            },
        })

    if args.json:
        print(json.dumps(results, indent=2, default=str))
        return

    # Visual output
    print()
    if use_color:
        print(BOLD + f'🧪 TATB Corpus — {len(results)} architectures' + RESET)
    else:
        print(f'TATB Corpus — {len(results)} architectures')
    print(f'Sorted by: {args.sort}   Legend: {RESET}■ Excellent(≥85) ▲ Solid(≥70) ● Weak(≥50) ▼ Draft(<50) ? N/A')
    print()

    render_table(results, args.sort, use_color)
    render_heatmap(results, use_color)
    render_stage_attribution(results, use_color)

    # Summary stats
    all_overalls = [r['scores']['overall']['score'] for r in results
                    if r['scores']['overall']['score'] is not None]
    if all_overalls:
        print()
        print(f'  Corpus overall: min={min(all_overalls)}  max={max(all_overalls)}'
              f'  avg={round(sum(all_overalls)/len(all_overalls))}  n={len(all_overalls)}')

    print()

    if args.regression:
        run_regression(report_dir, Path(args.label_dir), use_color)


if __name__ == '__main__':
    main()
