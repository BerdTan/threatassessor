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

    # Cross-critic from MoE
    cross_pct = 0
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

    ctrls = gt.get('control_recommendations', [])
    aligned, checked, seen = 0, 0, set()
    for c in ctrls:
        ctrl_name = (c.get('control') or '').lower()
        for tid in (c.get('mitre_techniques') or c.get('techniques') or []):
            pair = f'{tid}::{ctrl_name}'
            if pair in seen: continue
            seen.add(pair)
            mids = mitre_mits.get(tid, [])
            if not mids: continue
            checked += 1
            names = [mit_names.get(mid, '') for mid in mids]
            if any(ctrl_matches(ctrl_name, n) for n in names if n):
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

    # A. Technique mitigation coverage
    ap_techs    = set(t for ap in aps for t in ap.get('techniques', []))
    mit_techs   = set(t for c in ctrls for t in (c.get('mitre_techniques') or c.get('techniques') or []))
    tech_cov    = round(len(ap_techs & mit_techs) / len(ap_techs) * 100) if ap_techs else 50

    # B. Hop layer completeness
    all_hops    = [h for a in adrs for h in a.get('hops', [])]
    full_hops   = sum(1 for h in all_hops
                      if 'missing' not in (h.get('gap_note') or h.get('gap_type') or '').lower())
    hop_pct     = round(full_hops / len(all_hops) * 100) if all_hops else 50

    # C. Hard-to-defend residual
    rr_vals     = list(rr.values())
    hard_ct     = sum(1 for r in rr_vals if r.get('status') in ('MONITOR', 'MITIGATE'))
    hard_pct    = round((len(rr_vals) - hard_ct) / len(rr_vals) * 100) if rr_vals else 50

    score = round(tech_cov * 0.40 + hop_pct * 0.35 + hard_pct * 0.25)
    return {
        'score': score,
        'tech_cov': tech_cov,
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

    # E. AP closure
    crit_aps = [ap for ap in aps if ap.get('criticality_tier') == 'CRITICAL']
    addr     = [ap for ap in crit_aps
                if any(ap.get('id', '') in ((it.get('action') or '') + (it.get('rationale') or ''))
                       for it in items)]
    closure_pct = round(len(addr) / len(crit_aps) * 100) if crit_aps else 100
    anti_bonus  = 5 if any(str(it.get('is_antipattern', '')).lower() == 'true' for it in items) else 0

    score = min(100, round(comp_pct * 0.25 + meas_pct * 0.20 + sprint_pct * 0.15
                           + spec_pct * 0.20 + closure_pct * 0.20 + anti_bonus))
    return {
        'score': score,
        'comp_pct': comp_pct,
        'meas_pct': meas_pct,
        'sprint_pct': sprint_pct,
        'spec_pct': spec_pct,
        'closure_pct': closure_pct,
        'n_items': len(items),
        'n_crit_aps': len(crit_aps),
        'n_addr': len(addr),
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
    """Fetch technique→M-ID mappings and M-ID→name from the API."""
    if not tech_ids:
        return {}, {}
    try:
        url  = f'http://localhost:8000/api/v1/technique-mitigations?technique_ids={",".join(tech_ids)}'
        mits = json.loads(urllib.request.urlopen(url, timeout=5).read()).get('mappings', {})
        all_mids = list({m for mlist in mits.values() for m in mlist})
        if not all_mids:
            return mits, {}
        url2  = f'http://localhost:8000/api/v1/mitigations?mitigation_ids={",".join(all_mids)}'
        names = json.loads(urllib.request.urlopen(url2, timeout=5).read()).get('mitigations', {})
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
        'tech_cov': [], 'hop_pct': [], 'hard_pct': [],
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
        ('tech_cov',       'ReportStage → control_recommendations technique mapping'),
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

def main():
    parser = argparse.ArgumentParser(description='TATB Corpus Scorer')
    parser.add_argument('--report-dir', default='report', help='Path to report directory')
    parser.add_argument('--json',       action='store_true', help='Output raw JSON instead of visual')
    parser.add_argument('--sort',       default='overall',
                        choices=['threat', 'ttp', 'risk', 'plan', 'overall'],
                        help='Sort column (default: overall)')
    parser.add_argument('--no-color',   action='store_true', help='Disable ANSI colours')
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    if not report_dir.exists():
        print(f'Error: report directory not found: {report_dir}', file=sys.stderr)
        sys.exit(1)

    # Collect all architectures that have at least ground_truth.json
    arch_dirs = sorted([d for d in report_dir.iterdir()
                        if d.is_dir() and (d / 'ground_truth.json').exists()])
    if not arch_dirs:
        print('No architectures with ground_truth.json found.', file=sys.stderr)
        sys.exit(1)

    use_color = not args.no_color and sys.stdout.isatty()

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


if __name__ == '__main__':
    main()
