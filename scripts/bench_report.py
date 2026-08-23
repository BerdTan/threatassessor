#!/usr/bin/env python3
"""
bench_report.py — Generate HTML visual diff report from bench_summary.json.

Usage:
    python3 scripts/bench_report.py bench_results/<run_id>/bench_summary.json
    python3 scripts/bench_report.py bench_results/<run_id>/bench_summary.json --open

Writes bench_report.html next to the input file.
"""

import argparse
import json
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Normalisation ─────────────────────────────────────────────────────────────
# Reference polygon represents "good enough" — not theoretical max, but a
# solid target. Radar area vs reference = the visual signal.
CRITIC_AXES = [
    {"key": "depth",      "label": "Depth",      "max": 12.0, "ref": 11.0, "higher": True},
    {"key": "unique_ttps","label": "Unique TTPs", "max": 8.0,  "ref": 6.0,  "higher": True},
    {"key": "tok_eff",    "label": "Tok Eff",     "max": 1.0,  "ref": 0.65, "higher": True},
    {"key": "lat_eff",    "label": "Latency",     "max": 1.0,  "ref": 0.60, "higher": True},
    {"key": "contrib",    "label": "Contrib",     "max": 1.0,  "ref": 0.70, "higher": True},
]

PANEL_AXES = [
    {"key": "tatb",      "label": "TATB",        "max": 100.0, "ref": 75.0, "higher": True},
    {"key": "breadth",   "label": "Breadth",      "max": 20.0,  "ref": 12.0, "higher": True},
    {"key": "defens",    "label": "Defensibility","max": 10.0,  "ref": 6.0,  "higher": True},
    {"key": "tok_eff",   "label": "Tok Eff",      "max": 1.0,   "ref": 0.60, "higher": True},
    {"key": "depth_avg", "label": "Avg Depth",    "max": 12.0,  "ref": 10.0, "higher": True},
]

CRITIC_NAMES = ["architect", "tester", "red_team", "purple_team", "blackhat", "scrum_master"]
MAX_TOK_PER_CRITIC = 20_000
MAX_TOK_PANEL      = 150_000
MAX_LAT_S          = 200.0


def _normalise_critic(arch_result: dict, critic: str, total_union: int) -> dict:
    depth = (arch_result.get("depth") or {}).get(critic) or 0
    cp    = (arch_result.get("tokens") or {}).get("per_critic", {}).get(critic, {})
    tok   = cp.get("total", 0) or 0
    lat   = cp.get("latency_s", 0.0) or 0.0
    uniq  = (arch_result.get("breadth") or {}).get("unique_per_critic", {}).get(critic, 0)
    pu    = (arch_result.get("breadth") or {}).get("per_critic", {}).get(critic, 0)
    contrib = (pu / total_union) if total_union > 0 else 0
    tok_eff = max(0, 1 - tok / MAX_TOK_PER_CRITIC)
    lat_eff = max(0, 1 - lat / MAX_LAT_S)
    return {
        "depth":       depth / 12.0,
        "unique_ttps": min(1.0, uniq / 8.0),
        "tok_eff":     tok_eff,
        "lat_eff":     lat_eff,
        "contrib":     min(1.0, contrib),
        # raw
        "raw_depth":   depth,
        "raw_tok":     tok,
        "raw_lat":     lat,
        "raw_uniq":    uniq,
        "model":       cp.get("model", ""),
    }


def _normalise_panel(arch_result: dict) -> dict:
    tatb    = (arch_result.get("tatb") or {}).get("overall", 0) or 0
    breadth = (arch_result.get("breadth") or {}).get("total_union", 0) or 0
    defens  = (arch_result.get("defensibility") or 0) or 0
    tok     = (arch_result.get("tokens") or {}).get("total_panel", 0) or 0
    depths  = [(arch_result.get("depth") or {}).get(c) or 0 for c in CRITIC_NAMES]
    depth_avg = sum(depths) / len(depths) if depths else 0
    tok_eff = max(0, 1 - tok / MAX_TOK_PANEL)
    return {
        "tatb":      tatb / 100.0,
        "breadth":   min(1.0, breadth / 20.0),
        "defens":    min(1.0, defens / 10.0),
        "tok_eff":   tok_eff,
        "depth_avg": depth_avg / 12.0,
        # raw
        "raw_tatb":  tatb,
        "raw_breadth": breadth,
        "raw_defens":  defens,
        "raw_tok":     tok,
        "raw_depth_avg": round(depth_avg, 1),
    }


def build_chart_data(summary: dict) -> dict:
    """Transform bench_summary into chart-ready structure."""
    models  = summary.get("models", [])
    results = summary.get("results", {})
    archs   = summary.get("archs", [])

    chart = {
        "run_id":       summary.get("run_id", ""),
        "mode":         summary.get("mode", "critics"),
        "archs":        archs,
        "models":       models,
        "model_strings": summary.get("model_strings", {}),
        "critics": {},
        "panel":   {},
        "gaps":    [],
        "critic_axes": CRITIC_AXES,
        "panel_axes":  PANEL_AXES,
    }

    # Per-arch aggregation
    for arch in archs:
        arch_res = results.get(arch, {})
        chart["critics"][arch] = {}
        chart["panel"][arch]   = {}

        for model in models:
            mr = arch_res.get(model, {})
            if "error" in mr:
                chart["critics"][arch][model] = {"error": mr["error"]}
                chart["panel"][arch][model]   = {"error": mr["error"]}
                continue
            total_union = (mr.get("breadth") or {}).get("total_union", 1)
            chart["critics"][arch][model] = {
                c: _normalise_critic(mr, c, total_union) for c in CRITIC_NAMES
            }
            chart["panel"][arch][model] = _normalise_panel(mr)

    # Gap detection — all pairs (model_a has higher score, model_b regressed)
    seen_gaps = set()
    for i, ma in enumerate(models):
        for mb in models[i+1:]:
            for arch in archs:
                for critic in CRITIC_NAMES:
                    da = chart["critics"][arch].get(ma, {}).get(critic, {}).get("raw_depth")
                    db = chart["critics"][arch].get(mb, {}).get(critic, {}).get("raw_depth")
                    if da is None or db is None:
                        continue
                    drop = round(da - db, 1)
                    if drop >= 2:
                        key = (arch, critic, ma, mb)
                        if key not in seen_gaps:
                            seen_gaps.add(key)
                            chart["gaps"].append({
                                "arch": arch, "critic": critic,
                                "score_a": da, "score_b": db,
                                "drop": drop, "model_a": ma, "model_b": mb,
                            })
    chart["gaps"].sort(key=lambda x: -x["drop"])

    return chart


HTML_TEMPLATE = r"""
<title>TA Bench {run_id}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;1,400&family=JetBrains+Mono:wght@400;600;700&display=swap">

<style>
:root {
  --ground:    #0d1117;
  --surface:   #161b27;
  --surface2:  #1a2235;
  --border:    #1e2535;
  --border2:   #253047;
  --text:      #e2e8f0;
  --text2:     #8899b0;
  --text3:     #4d607a;
  --model-a:   #3b82f6;
  --model-b:   #14b8a6;
  --model-c:   #f59e0b;
  --ref:       #2d3748;
  --good:      #10b981;
  --warn:      #f59e0b;
  --danger:    #ef4444;
  --gap-1:     #ef444422;
  --gap-2:     #f59e0b22;
  --accent:    #3b82f6;
  font-size: 14px;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --ground:   #f1f5f9;
    --surface:  #ffffff;
    --surface2: #f8fafc;
    --border:   #e2e8f0;
    --border2:  #cbd5e1;
    --text:     #0f172a;
    --text2:    #475569;
    --text3:    #94a3b8;
    --gap-1:    #ef444414;
    --gap-2:    #f59e0b14;
  }
}
:root[data-theme="light"] {
  --ground:   #f1f5f9;
  --surface:  #ffffff;
  --surface2: #f8fafc;
  --border:   #e2e8f0;
  --border2:  #cbd5e1;
  --text:     #0f172a;
  --text2:    #475569;
  --text3:    #94a3b8;
  --gap-1:    #ef444414;
  --gap-2:    #f59e0b14;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--ground);
  color: var(--text);
  font-family: 'Inter', system-ui, sans-serif;
  line-height: 1.5;
  min-height: 100vh;
}

/* ── Header ── */
.header {
  border-bottom: 1px solid var(--border);
  padding: 1rem 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}
.header-left { display: flex; flex-direction: column; gap: 0.35rem; }
.header-title {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 0.95rem;
  letter-spacing: -0.01em;
  color: var(--text);
}
.header-title span { color: var(--text2); font-weight: 400; }
.header-meta {
  display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center;
}
.pill {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem;
  padding: 0.18rem 0.55rem;
  border-radius: 2px;
  border: 1px solid var(--border2);
  color: var(--text2);
  background: var(--surface);
  white-space: nowrap;
}
.pill.a { border-color: var(--model-a); color: var(--model-a); background: color-mix(in srgb, var(--model-a) 10%, transparent); }
.pill.b { border-color: var(--model-b); color: var(--model-b); background: color-mix(in srgb, var(--model-b) 10%, transparent); }
.pill.c { border-color: var(--model-c); color: var(--model-c); background: color-mix(in srgb, var(--model-c) 10%, transparent); }

/* ── Legend ── */
.legend {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.4rem;
}
.legend-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  font-size: 0.7rem;
  color: var(--text2);
  font-family: 'JetBrains Mono', monospace;
}
.legend-item { display: flex; align-items: center; gap: 0.35rem; }
.legend-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.legend-dot.ref { background: none; border: 1.5px dashed var(--text3); border-radius: 50%; }
.legend-note { font-size: 0.62rem; color: var(--text3); font-style: italic; }

/* ── Verdict banner ── */
.verdict {
  border-left: 3px solid var(--border2);
  padding: 1rem 1.5rem;
  margin: 1.25rem 2rem;
  background: var(--surface);
  border-radius: 0 3px 3px 0;
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
}
.verdict-chip {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem;
  font-weight: 700;
  padding: 0.25rem 0.6rem;
  border-radius: 2px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  flex-shrink: 0;
  margin-top: 0.15rem;
}
.verdict-chip.good    { background: color-mix(in srgb,var(--good) 15%,transparent);   color: var(--good);   border: 1px solid color-mix(in srgb,var(--good) 35%,transparent); }
.verdict-chip.warn    { background: color-mix(in srgb,var(--warn) 15%,transparent);   color: var(--warn);   border: 1px solid color-mix(in srgb,var(--warn) 35%,transparent); }
.verdict-chip.danger  { background: color-mix(in srgb,var(--danger) 15%,transparent); color: var(--danger); border: 1px solid color-mix(in srgb,var(--danger) 35%,transparent); }
.verdict-body { flex: 1; min-width: 200px; }
.verdict-headline {
  font-weight: 600;
  font-size: 0.88rem;
  color: var(--text);
  margin-bottom: 0.2rem;
}
.verdict-detail {
  font-size: 0.78rem;
  color: var(--text2);
  line-height: 1.55;
}
.verdict-action {
  margin-top: 0.4rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem;
  color: var(--text3);
}

/* ── Main layout ── */
.main { padding: 1.5rem 2rem; max-width: 1400px; margin: 0 auto; }

/* ── Section titles ── */
.section-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.63rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text3);
  margin-bottom: 1rem;
}

/* ── Arch section (collapsible) ── */
.arch-section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 3px;
  margin-bottom: 1rem;
  overflow: hidden;
}
.arch-section summary {
  list-style: none;
  cursor: pointer;
  padding: 0.7rem 1.1rem;
  background: var(--surface2);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  user-select: none;
}
.arch-section summary::-webkit-details-marker { display: none; }
.arch-section summary::before {
  content: '▶';
  font-size: 0.6rem;
  color: var(--text3);
  transition: transform 0.15s;
  flex-shrink: 0;
}
.arch-section[open] summary::before { transform: rotate(90deg); }
.arch-section summary:hover { background: color-mix(in srgb, var(--accent) 6%, var(--surface2)); }

.arch-name-large {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--text);
}
.arch-meta-pills { display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center; }
.arch-summary-scores {
  margin-left: auto;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem;
  color: var(--text3);
}

/* ── Analysis layout: panel left | 3×2 critics grid right ── */
.analysis-grid {
  display: grid;
  grid-template-columns: 220px 1fr;
}

/* Critics 3×2 sub-grid */
.critics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-left: 1px solid var(--border);
}
.critics-grid .critic-col:nth-child(4),
.critics-grid .critic-col:nth-child(5),
.critics-grid .critic-col:nth-child(6) {
  border-top: 1px solid var(--border);
}

/* Panel column */
.panel-col {
  border-right: 1px solid var(--border);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
}
.panel-radar-wrap { display: flex; justify-content: center; }
.panel-col-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text3);
  text-align: center;
}
.panel-stats { display: flex; flex-direction: column; gap: 0; }
.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
  border-bottom: 1px solid var(--border);
  padding: 0.35rem 0;
}
.stat-row:last-child { border-bottom: none; }
.stat-label {
  font-size: 0.65rem;
  color: var(--text2);
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}
.dir { font-size: 0.55rem; }
.dir.up { color: var(--good); }
.dir.dn { color: var(--danger); }
.stat-vals { display: flex; gap: 0.4rem; font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; font-variant-numeric: tabular-nums; }
.val-a { color: var(--model-a); font-weight: 600; }
.val-b { color: var(--model-b); font-weight: 600; }
.val-c { color: var(--model-c); font-weight: 600; }
.val-delta { color: var(--text3); font-size: 0.62rem; }
.val-delta.up { color: var(--good); }
.val-delta.dn { color: var(--danger); }

/* Critic columns */
.critic-col {
  border-right: 1px solid var(--border);
  padding: 0.85rem 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.critic-improve {
  margin-top: auto;
  padding-top: 0.4rem;
  font-size: 0.58rem;
  color: var(--text3);
  line-height: 1.4;
  border-top: 1px dashed var(--border2);
}
.critic-improve-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.55rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text3);
  opacity: 0.7;
  margin-bottom: 0.15rem;
}
.critic-name {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text);
}
.critic-role {
  font-size: 0.6rem;
  color: var(--text3);
  font-style: italic;
  line-height: 1.35;
  margin-top: -0.2rem;
}
.depth-badge {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 1.25rem;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.depth-b { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; font-weight: 600; }
.depth-scale { font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; color: var(--text3); }
.depth-arrow { font-size: 0.65rem; color: var(--text3); margin: 0 0.15rem; }
.critic-model {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.58rem;
  color: var(--text3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.critic-detail {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.58rem;
  color: var(--text3);
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

/* ── Gap report ── */
.gap-section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.75rem;
}
.gap-section-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.75rem;
}
.gap-section-note {
  font-size: 0.68rem;
  color: var(--text3);
  font-style: italic;
}
.gap-list { display: flex; flex-direction: column; gap: 0.4rem; }
.gap-header-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto auto auto auto;
  gap: 0.75rem;
  padding: 0.25rem 0.75rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.gap-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto auto auto auto;
  gap: 0.75rem;
  align-items: center;
  padding: 0.5rem 0.75rem;
  border-radius: 2px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
}
.gap-row.sev-high { background: var(--gap-1); border-left: 2px solid var(--danger); }
.gap-row.sev-med  { background: var(--gap-2); border-left: 2px solid var(--warn); }
.gap-arch { color: var(--text2); font-size: 0.65rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gap-critic { color: var(--text); font-weight: 600; }
.gap-score-a { color: var(--model-a); }
.gap-score-b { color: var(--model-b); }
.gap-drop { color: var(--danger); font-weight: 700; }
.gap-sev  { font-size: 0.62rem; }
.no-gaps {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  color: var(--good);
}

/* arch tabs removed — sections use <details> collapsible */

/* ── Glossary ── */
.glossary {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 2rem;
}
.glossary-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.85rem 1.25rem;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text2);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  text-align: left;
}
.glossary-toggle:hover { background: var(--surface2); }
.glossary-caret { transition: transform 0.2s; font-style: normal; }
.glossary-caret.open { transform: rotate(180deg); }
.glossary-body { display: none; padding: 0 1.25rem 1.25rem; }
.glossary-body.open { display: block; }
.glossary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0;
  border-top: 1px solid var(--border);
}
.glossary-term {
  padding: 0.65rem 1rem;
  border-bottom: 1px solid var(--border);
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.75rem;
  align-items: start;
}
.glossary-term:nth-child(odd) { background: var(--surface2); }
.gt-key {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
  padding-top: 0.05rem;
}
.gt-dir { font-size: 0.6rem; vertical-align: super; margin-left: 2px; }
.gt-def { font-size: 0.72rem; color: var(--text2); line-height: 1.45; }
.gt-scale { font-family: 'JetBrains Mono', monospace; font-size: 0.65rem; color: var(--text3); margin-top: 0.15rem; }
.ref-explain {
  border-top: 1px solid var(--border);
  padding: 0.65rem 1rem;
  font-size: 0.72rem;
  color: var(--text2);
  line-height: 1.5;
}
.ref-explain strong { color: var(--text); font-weight: 600; }

svg text { font-family: 'JetBrains Mono', monospace; }
</style>

<!-- ── Header ──────────────────────────────────────────────────────────────── -->
<div class="header">
  <div class="header-left">
    <div class="header-title">TA Bench <span>/ {run_id}</span></div>
    <div class="header-meta" id="header-meta"></div>
  </div>
  <div class="legend">
    <div class="legend-row" id="legend-models"></div>
    <div class="legend-note">↑ all radar axes: higher is better &nbsp;·&nbsp; dashed ring = production target</div>
  </div>
</div>

<!-- ── Verdict banner ─────────────────────────────────────────────────────── -->
<div class="verdict" id="verdict-banner">
  <div class="verdict-chip" id="verdict-chip">—</div>
  <div class="verdict-body">
    <div class="verdict-headline" id="verdict-headline">Computing…</div>
    <div class="verdict-detail" id="verdict-detail"></div>
    <div class="verdict-action" id="verdict-action"></div>
  </div>
</div>

<!-- ── Charts ─────────────────────────────────────────────────────────────── -->
<div class="main">
  <div id="arch-panes"></div>
</div>

<!-- ── Gap report ─────────────────────────────────────────────────────────── -->
<div class="main" style="padding-top:0;">
  <div class="gap-section">
    <div class="gap-section-header">
      <div class="section-label" style="margin-bottom:0;">Gap Report</div>
      <span class="gap-section-note" id="gap-section-note"></span>
    </div>
    <div class="gap-list" id="gap-list"></div>
  </div>
</div>

<!-- ── Glossary ───────────────────────────────────────────────────────────── -->
<div class="main" style="padding-top:0;">
  <div class="glossary">
    <button class="glossary-toggle" id="glossary-toggle" onclick="toggleGlossary()">
      <span>What do these metrics mean?</span>
      <span class="glossary-caret" id="glossary-caret">▼</span>
    </button>
    <div class="glossary-body" id="glossary-body">
      <div class="glossary-grid">
        <div class="glossary-term">
          <div class="gt-key">Depth<span class="gt-dir" style="color:var(--good)">↑</span></div>
          <div><div class="gt-def">LLM-graded quality of the critic's analysis. Score derived from a 100-pt rubric then rescaled to 12. Measures how rigorous, specific, and well-reasoned the critique is — not just whether it found threats.</div>
          <div class="gt-scale">0–12, higher is better &nbsp;·&nbsp; ≥10 production-ready · 7–9 acceptable · &lt;7 needs critic-gym</div></div>
        </div>
        <div class="glossary-term">
          <div class="gt-key">Unique TTPs<span class="gt-dir" style="color:var(--good)">↑</span></div>
          <div><div class="gt-def">MITRE ATT&amp;CK techniques this critic identified that no other critic found. Measures independent coverage contribution. A critic with many unique TTPs spots blind spots that the rest of the panel misses.</div>
          <div class="gt-scale">Normalised to 8 unique TTPs = 1.0 on radar</div></div>
        </div>
        <div class="glossary-term">
          <div class="gt-key">Tok Eff<span class="gt-dir" style="color:var(--good)">↑</span></div>
          <div><div class="gt-def">Token efficiency: how much quality the critic delivers per token spent. Calculated as 1 − (tokens used ÷ 20 000). A critic that uses 5k tokens scores 0.75; one that uses 18k scores 0.10. Lower cost = higher score.</div>
          <div class="gt-scale">0–1, higher is better &nbsp;·&nbsp; &gt;0.65 efficient · &lt;0.3 expensive</div></div>
        </div>
        <div class="glossary-term">
          <div class="gt-key">Latency<span class="gt-dir" style="color:var(--good)">↑</span></div>
          <div><div class="gt-def">Response speed: 1 − (seconds ÷ 200). Faster critics score higher. Primarily informational — a slow critic is acceptable if depth is high and the pipeline can parallelize.</div>
          <div class="gt-scale">0–1, higher = faster</div></div>
        </div>
        <div class="glossary-term">
          <div class="gt-key">Contrib<span class="gt-dir" style="color:var(--good)">↑</span></div>
          <div><div class="gt-def">Contribution rate: this critic's TTP count as a fraction of the full panel's total union. A critic contributing 8 of 16 panel TTPs scores 0.5. Shows how additive each voice is to the overall coverage.</div>
          <div class="gt-scale">0–1, higher = more additive</div></div>
        </div>
        <div class="glossary-term">
          <div class="gt-key">TATB<span class="gt-dir" style="color:var(--good)">↑</span></div>
          <div><div class="gt-def">Threat Assessment Trust Benchmark: composite score across TTP coverage (60%) and mitigation plan quality (40%). The primary cross-architecture quality signal. Comparable across different architectures.</div>
          <div class="gt-scale">0–100, higher is better &nbsp;·&nbsp; ≥75 strong · 50–74 adequate · &lt;50 needs work</div></div>
        </div>
        <div class="glossary-term">
          <div class="gt-key">Breadth<span class="gt-dir" style="color:var(--good)">↑</span></div>
          <div><div class="gt-def">Total unique MITRE ATT&amp;CK techniques found across all critics combined (union). Higher breadth means the panel collectively covers more of the attack surface. A narrow panel misses whole technique families.</div>
          <div class="gt-scale">Normalised to 20 TTPs = 1.0 on panel radar</div></div>
        </div>
        <div class="glossary-term">
          <div class="gt-key">Defensibility<span class="gt-dir" style="color:var(--good)">↑</span></div>
          <div><div class="gt-def">AIVSS composite score: how well the architecture can withstand attacks given its current controls. Derived from the governance signals layer, not from the critics. Independent quality signal for the architecture itself.</div>
          <div class="gt-scale">0–10, higher is better &nbsp;·&nbsp; ≥7 well-defended · 4–6 moderate · &lt;4 exposed</div></div>
        </div>
        <div class="glossary-term">
          <div class="gt-key">Avg Depth<span class="gt-dir" style="color:var(--good)">↑</span></div>
          <div><div class="gt-def">Mean depth score across all 5 critics. The single most important panel-level health number — it answers "is the model producing rigorous critiques on average?" A model with high avg depth can be trusted for production MoE runs.</div>
          <div class="gt-scale">0–12, higher is better</div></div>
        </div>
      </div>
      <div class="ref-explain">
        <strong>Reference (dashed ring)</strong> — The production target, not the theoretical maximum. Each axis has its own reference value: e.g. Depth ref = 11/12, TATB ref = 75/100. A polygon that fills or exceeds the dashed ring is ready for production. Falling short on an axis means that dimension warrants a critic-gym session or model swap before full corpus rerun.
        &nbsp;·&nbsp; <strong>Gap Report</strong> — when comparing two models, critics where model B drops ≥2 depth points below model A are flagged as regressions. High-severity (red border) = ≥3 pt drop.
      </div>
    </div>
  </div>
</div>

<script>
const DATA = {DATA_PLACEHOLDER};

// ── Radar chart ───────────────────────────────────────────────────────────────
function radarPoints(values, cx, cy, r) {
  const n = values.length;
  return values.map((v, i) => {
    const angle = (2 * Math.PI / n) * i - Math.PI / 2;
    const d = Math.max(0, Math.min(1, v)) * r;
    return [cx + d * Math.cos(angle), cy + d * Math.sin(angle)];
  });
}

function ptStr(pts) { return pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' '); }

function buildRadar(svgEl, axesDef, modelsData, size) {
  const cx = size / 2, cy = size / 2, r = size * 0.36;
  const n = axesDef.length;
  const ns = 'http://www.w3.org/2000/svg';

  function el(tag, attrs, parent) {
    const e = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([k,v]) => e.setAttribute(k, v));
    if (parent) parent.appendChild(e);
    return e;
  }

  svgEl.setAttribute('viewBox', `0 0 ${size} ${size}`);
  svgEl.setAttribute('width', size);
  svgEl.setAttribute('height', size);

  [0.25, 0.5, 0.75, 1.0].forEach(frac => {
    el('circle', { cx, cy, r: r*frac, fill: 'none', stroke: 'var(--border)', 'stroke-width': 0.5 }, svgEl);
  });

  axesDef.forEach((ax, i) => {
    const angle = (2 * Math.PI / n) * i - Math.PI / 2;
    const x2 = cx + r * Math.cos(angle), y2 = cy + r * Math.sin(angle);
    el('line', { x1: cx, y1: cy, x2, y2, stroke: 'var(--border)', 'stroke-width': 0.8 }, svgEl);
    const lx = cx + (r + 14) * Math.cos(angle);
    const ly = cy + (r + 14) * Math.sin(angle);
    const t = el('text', {
      x: lx, y: ly,
      'text-anchor': 'middle', 'dominant-baseline': 'middle',
      'font-size': size < 180 ? 8 : 9, fill: 'var(--text3)',
      'font-family': "'JetBrains Mono',monospace"
    }, svgEl);
    t.textContent = ax.label;
  });

  // Reference polygon (dashed = production target)
  const refVals = axesDef.map(ax => ax.ref / ax.max);
  const refPts  = radarPoints(refVals, cx, cy, r);
  el('polygon', { points: ptStr(refPts), fill: 'none',
    stroke: 'var(--text3)', 'stroke-width': 1, 'stroke-dasharray': '3,2', opacity: 0.7 }, svgEl);

  const colors = ['var(--model-a)', 'var(--model-b)'];
  modelsData.forEach((vals, mi) => {
    if (!vals) return;
    const pts = radarPoints(vals, cx, cy, r);
    el('polygon', { points: ptStr(pts), fill: colors[mi], 'fill-opacity': 0.09,
      stroke: colors[mi], 'stroke-width': 1.5 }, svgEl);
    pts.forEach(p => {
      el('circle', { cx: p[0], cy: p[1], r: 2.5, fill: colors[mi], 'fill-opacity': 0.9 }, svgEl);
    });
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function _delta(a, b, higher = true) {
  if (a == null || b == null) return '';
  const d = b - a;
  if (Math.abs(d) < 0.5) return '<span class="val-delta">±0</span>';
  const sign = d > 0 ? '+' : '';
  const cls  = (d > 0) === higher ? 'up' : 'dn';
  return `<span class="val-delta ${cls}">${sign}${d.toFixed(1)}</span>`;
}

function _depthColor(v) {
  if (v == null) return 'var(--text3)';
  return v >= 10 ? 'var(--good)' : v >= 7 ? 'var(--warn)' : 'var(--danger)';
}

// ── Critic role descriptions ──────────────────────────────────────────────────
const CRITIC_ROLES = {
  architect:    'Control gaps & roadmap quality',
  tester:       'Fact-checks MITRE mappings',
  red_team:     'Adversarial attack paths',
  purple_team:  'Defence-attack parity',
  blackhat:     'Novel exploitation vectors',
  scrum_master: 'Synthesises critics → sprint plan',
};

// ── Improvement hints per critic × score band ─────────────────────────────────
function _improveHint(critic, score) {
  if (score == null || score >= 11.5) return '';
  const hints = {
    architect: [
      [10, 'Deepen trust boundary + data flow threat enumeration'],
      [8,  'Add lateral trust violations + privilege boundary failures'],
      [0,  'Full trust model missing — add attack surface + data flows'],
    ],
    tester: [
      [10, 'Add negative test cases + dependency trust scenarios'],
      [8,  'Cover auth edge cases, race conditions, input validation'],
      [0,  'MITRE mappings unverified — add test coverage per TTP'],
    ],
    red_team: [
      [10, 'Extend post-exploit scenarios + multi-hop chains'],
      [8,  'Add privilege escalation + lateral movement depth'],
      [0,  'Attack paths sparse — expand adversarial TTP coverage'],
    ],
    purple_team: [
      [10, 'Strengthen correlation rules + threat hunt playbooks'],
      [8,  'Map D3FEND mitigations + close detection gaps'],
      [0,  'Detection parity weak — map TTPs to detection controls'],
    ],
    blackhat: [
      [10, 'Add zero-day analogues + advanced persistence vectors'],
      [8,  'Explore supply chain + insider threat scenarios'],
      [0,  'Novel vectors missing — add unconventional attack paths'],
    ],
    scrum_master: [
      [10, 'Tighten first_step specificity + add acceptance criteria'],
      [8,  'Ensure both structural + immediate tiers are present in the plan'],
      [0,  'Action plan coverage low — more impediments need plan items'],
    ],
  };
  const bands = hints[critic] || [];
  for (const [threshold, msg] of bands) {
    if (score >= threshold) return msg;
  }
  return '';
}

// ── Verdict computation ───────────────────────────────────────────────────────
function computeVerdict() {
  const CRITICS = ['architect','tester','red_team','purple_team','blackhat','scrum_master'];
  const REF_DEPTH = 11.0;

  function aggPanel(model) {
    let tatb=0, depth=0, breadth=0, defens=0, tok=0, n=0;
    for (const a of archs) {
      const p = (DATA.panel[a] || {})[model] || {};
      if (!p.raw_tatb && p.raw_tatb !== 0) continue;
      tatb   += p.raw_tatb  || 0;
      depth  += p.raw_depth_avg || 0;
      breadth+= p.raw_breadth || 0;
      defens += p.raw_defens  || 0;
      tok    += p.raw_tok     || 0;
      n++;
    }
    if (!n) return null;
    return { tatb: tatb/n, depth: depth/n, breadth: breadth/n, defens: defens/n, tok: tok/n };
  }

  function refMet(model) {
    let met=0, total=0;
    for (const a of archs) {
      const cd = DATA.critics[a] || {};
      for (const c of CRITICS) {
        const d = ((cd[model] || {})[c] || {}).raw_depth;
        if (d == null) continue;
        total++;
        if (d >= REF_DEPTH) met++;
      }
    }
    return { met, total };
  }

  const panels = models.map(m => ({ model: m, panel: aggPanel(m) })).filter(x => x.panel);
  const verdict = document.getElementById('verdict-banner');
  const chip    = document.getElementById('verdict-chip');
  const headline= document.getElementById('verdict-headline');
  const detail  = document.getElementById('verdict-detail');
  const action  = document.getElementById('verdict-action');

  if (!panels.length) { headline.textContent = 'No data'; return; }

  if (panels.length === 1) {
    const { model, panel: pa } = panels[0];
    const ref0 = refMet(model);
    const refPct = ref0.total > 0 ? Math.round(ref0.met / ref0.total * 100) : 0;
    const status = pa.depth >= 10 ? 'good' : pa.depth >= 7 ? 'warn' : 'danger';
    chip.textContent = pa.depth >= 10 ? 'Strong' : pa.depth >= 7 ? 'Acceptable' : 'Needs Work';
    chip.className   = 'verdict-chip ' + status;
    headline.textContent = `${model} baseline — avg depth ${pa.depth.toFixed(1)}/12, TATB ${Math.round(pa.tatb)}/100`;
    detail.innerHTML = [
      `${ref0.met}/${ref0.total} critic×arch pairs meet ref depth 11/12 (${refPct}%).`,
      pa.breadth > 0 ? `${Math.round(pa.breadth)} unique TTPs avg.` : '',
      pa.defens  > 0 ? `Defensibility ${pa.defens.toFixed(2)}/10.` : '',
    ].filter(Boolean).join(' ');
    let worst = null, worstD = 99;
    for (const a of archs) for (const c of CRITICS) {
      const d = ((DATA.critics[a] || {})[model] || {})[c]?.raw_depth;
      if (d != null && d < worstD) { worstD = d; worst = c; }
    }
    action.textContent = worst && worstD < 10
      ? `Lowest scorer: ${worst.replace('_',' ')} (${worstD.toFixed(1)}/12) — consider: /critic-gym ${worst}`
      : 'All critics at or near reference. Ready for corpus-wide rerun.';
    verdict.style.borderLeftColor = status === 'good' ? 'var(--good)' : status === 'warn' ? 'var(--warn)' : 'var(--danger)';

  } else {
    // Multi-model comparison — rank by avg depth, pick winner
    const ranked = [...panels].sort((a, b) => b.panel.depth - a.panel.depth);
    const winner = ranked[0];
    const gapCount = DATA.gaps ? DATA.gaps.length : 0;
    const depthSpread = winner.panel.depth - ranked[ranked.length-1].panel.depth;
    const status = depthSpread >= 1.0 ? 'good' : depthSpread >= 0.3 ? 'warn' : 'warn';

    chip.textContent = `Winner: ${winner.model}`;
    chip.className   = 'verdict-chip ' + status;

    const rankStr = ranked.map((r, i) => `${i+1}. ${r.model} ${r.panel.depth.toFixed(1)}/12`).join(' · ');
    headline.textContent = `Depth ranking — ${rankStr}`;

    const tatbStr = panels.map(({model: m, panel: p}) => `${m} ${Math.round(p.tatb)}`).join(' → ');
    detail.innerHTML = [
      `TATB: ${tatbStr}.`,
      gapCount > 0 ? `${gapCount} depth regression${gapCount>1?'s':''} detected — see Gap Report below.` : 'No depth regressions detected.',
    ].filter(Boolean).join(' ');
    action.textContent = gapCount > 0
      ? `Next: /critic-gym ${DATA.gaps[0].critic} --model ${DATA.gaps[0].model_b} to address the largest gap.`
      : `No regressions. Consider promoting ${winner.model} to production and running rerun-moe --all.`;
    verdict.style.borderLeftColor = status === 'good' ? 'var(--good)' : 'var(--warn)';
  }
}

// ── Glossary toggle ───────────────────────────────────────────────────────────
function toggleGlossary() {
  const body  = document.getElementById('glossary-body');
  const caret = document.getElementById('glossary-caret');
  const open  = body.classList.toggle('open');
  caret.classList.toggle('open', open);
  try { localStorage.setItem('bench_glossary', open ? '1' : '0'); } catch(_) {}
}
(function() {
  try {
    if (localStorage.getItem('bench_glossary') !== '0') {
      document.getElementById('glossary-body').classList.add('open');
      document.getElementById('glossary-caret').classList.add('open');
    }
  } catch(_) {}
})();

// ── Render ────────────────────────────────────────────────────────────────────
const models  = DATA.models;
const archs   = DATA.archs;
const m0 = models[0], m1 = models[1], m2 = models[2];
const CRITIC_NAMES = ['architect','tester','red_team','purple_team','blackhat','scrum_master'];
const MODEL_CLASSES = ['a','b','c'];
const MODEL_CSS_VARS = ['var(--model-a)','var(--model-b)','var(--model-c)'];

// Header meta pills — show alias + actual model string
const metaCont = document.getElementById('header-meta');
const modelStrings = DATA.model_strings || {};
models.forEach((m, i) => {
  const p = document.createElement('div');
  p.className = 'pill ' + (MODEL_CLASSES[i] || 'b');
  const actual = modelStrings[m];
  p.innerHTML = actual && actual !== m
    ? `<strong>${m}</strong> <span style="opacity:0.7;font-size:0.78em">${actual}</span>`
    : m;
  if (actual) p.title = actual;
  metaCont.appendChild(p);
});
[
  { label: `${archs.length} arch${archs.length > 1 ? 's' : ''}` },
  { label: DATA.mode || 'critics' },
].forEach(({ label }) => {
  const p = document.createElement('div');
  p.className = 'pill';
  p.textContent = label;
  metaCont.appendChild(p);
});

// Legend
const legendModels = document.getElementById('legend-models');
models.forEach((m, i) => {
  const item = document.createElement('div');
  item.className = 'legend-item';
  item.innerHTML = `<div class="legend-dot" style="background:${MODEL_CSS_VARS[i]||MODEL_CSS_VARS[1]}"></div><span>${m}</span>`;
  legendModels.appendChild(item);
});
const refItem = document.createElement('div');
refItem.className = 'legend-item';
refItem.innerHTML = `<div class="legend-dot ref"></div><span>Reference target</span>`;
legendModels.appendChild(refItem);

// Verdict
computeVerdict();

// Arch sections (collapsible details)
const panesCont = document.getElementById('arch-panes');

archs.forEach((arch, ai) => {
  const panelData = DATA.panel[arch] || {};
  const panelAxes = DATA.panel_axes;
  // Per-model panel objects and radar datasets
  const panelObjs = models.map(m => panelData[m] || {});
  const radarDatasets = models.map(m => panelAxes.map(ax => (panelData[m] || {})[ax.key] ?? null));
  const pa = panelObjs[0], pb = panelObjs[1] || {}, pc = panelObjs[2] || {};

  const criticData = DATA.critics[arch] || {};

  // Quick depth summary for the summary line
  const depthAvgs = panelObjs.map(p => p.raw_depth_avg);
  const depthParts = depthAvgs.map((d, i) => d != null ? `${models[i]} ${d.toFixed(1)}` : null).filter(Boolean);
  const depthSummary = depthParts.length ? `avg depth ${depthParts.join(' → ')}/12` : 'avg depth —/12';

  const section = document.createElement('details');
  section.className = 'arch-section';
  section.open = ai === 0;

  const summary = document.createElement('summary');
  summary.innerHTML = `
    <span class="arch-name-large">${arch}</span>
    <div class="arch-meta-pills">
      ${models.map((m,i) => { const s = modelStrings[m]; return `<span class="pill ${i===0?'a':'b'}" title="${s||m}">${m}</span>`; }).join('')}
      ${DATA.run_id ? `<span class="pill">${DATA.run_id.replace(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/, '$1-$2-$3 $4:$5')}</span>` : ''}
    </div>
    <span class="arch-summary-scores">${depthSummary}</span>
  `;
  section.appendChild(summary);

  // Layout: panel left | 3×2 critics grid right
  const grid = document.createElement('div');
  grid.className = 'analysis-grid';

  // Panel column
  const panelCol = document.createElement('div');
  panelCol.className = 'panel-col';
  panelCol.innerHTML = `
    <div class="panel-col-label">Panel · all critics</div>
    <div class="panel-radar-wrap"><svg id="panel-radar-${ai}"></svg></div>
    <div class="panel-stats">
      ${[
        ['TATB',     p => p.raw_tatb != null ? p.raw_tatb : null,           false, '/100'],
        ['Breadth',  p => p.raw_breadth ?? null,                             false, ' TTPs'],
        ['Defens.',  p => p.raw_defens != null ? p.raw_defens : null,        false, '/10'],
        ['Tok ↓',   p => p.raw_tok ? Math.round(p.raw_tok/1000) : null,     true,  'k'],
        ['Avg dep.', p => p.raw_depth_avg ?? null,                           false, '/12'],
      ].map(([lbl, getter, invert, unit]) => {
        const vals = panelObjs.map(getter);
        const best = invert ? Math.min(...vals.filter(v=>v!=null)) : Math.max(...vals.filter(v=>v!=null));
        const spans = vals.map((v, i) => {
          if (v == null) return '';
          const isBest = vals.filter(x=>x!=null).length > 1 && v === best;
          const disp = (unit === '/10' ? v.toFixed(1) : v) + (v !== '—' ? unit : '');
          return `<span class="val-${MODEL_CLASSES[i]||'b'}"${isBest?' style="text-decoration:underline"':''}>${disp}</span>`;
        }).join(' ');
        return `<div class="stat-row"><span class="stat-label">${lbl}</span><span class="stat-vals">${spans||'—'}</span></div>`;
      }).join('')}
    </div>
  `;
  grid.appendChild(panelCol);

  // 3×2 critics sub-grid
  const criticsGrid = document.createElement('div');
  criticsGrid.className = 'critics-grid';

  CRITIC_NAMES.forEach(critic => {
    const criticObjs = models.map(m => (criticData[m] || {})[critic] || {});
    const depths = criticObjs.map(c => c.raw_depth != null ? c.raw_depth : null);

    const ca = criticObjs[0];
    const modelRaw = ca.model || '';
    const modelShort = modelRaw.replace(/^openrouter\/openrouter\//, 'or/').replace(/^openai\//, 'hetzner/').replace(/^openrouter\//, '');
    const hint = _improveHint(critic, depths[0]);

    const depthBadges = depths.map((d, i) => {
      const clr = _depthColor(d);
      const disp = d != null ? d.toFixed(1) : '—';
      const sep = i > 0 ? '<span class="depth-arrow">·</span>' : '';
      return `${sep}<span style="color:${clr};font-weight:600;font-family:\'JetBrains Mono\',monospace;font-size:${i===0?'1.1rem':'0.85rem'}">${disp}</span>`;
    }).join('');

    const col = document.createElement('div');
    col.className = 'critic-col';
    col.innerHTML = `
      <div class="critic-name">${critic.replace(/_/g,' ')}</div>
      <div class="critic-role">${CRITIC_ROLES[critic] || ''}</div>
      <div style="margin-top:0.3rem;display:flex;align-items:baseline;gap:0.2rem;flex-wrap:wrap;">
        ${depthBadges}
        <span class="depth-scale">/12</span>
      </div>
      <div class="critic-detail">
        <span class="critic-model" title="${modelRaw}">${modelShort || '—'}</span>
        <span>tok ${ca.raw_tok ? Math.round(ca.raw_tok/1000)+'k' : '—'}${ca.raw_lat ? ' · '+ca.raw_lat.toFixed(0)+'s' : ''}</span>
        ${ca.raw_uniq ? `<span>${ca.raw_uniq} uniq TTPs</span>` : ''}
      </div>
      ${hint ? `<div class="critic-improve"><div class="critic-improve-label">↑ to improve</div>${hint}</div>` : ''}
    `;
    criticsGrid.appendChild(col);
  });
  grid.appendChild(criticsGrid);

  section.appendChild(grid);
  panesCont.appendChild(section);

  // Panel radar only (no per-critic radars)
  const panelSvg = document.getElementById(`panel-radar-${ai}`);
  buildRadar(panelSvg, panelAxes, radarDatasets, 200);
});

// Gap report
const gapList = document.getElementById('gap-list');
const gapNote = document.getElementById('gap-section-note');
if (DATA.gaps && DATA.gaps.length > 0) {
  gapNote.textContent = `critics where model B drops ≥2 depth pts below model A`;
  const hdrRow = document.createElement('div');
  hdrRow.className = 'gap-header-row';
  hdrRow.innerHTML = `<span>Architecture</span><span>Critic</span><span>Model A</span><span>Model B</span><span>Drop</span><span>Sev</span>`;
  gapList.appendChild(hdrRow);

  DATA.gaps.forEach(g => {
    const row = document.createElement('div');
    const sev = g.drop >= 3 ? 'sev-high' : 'sev-med';
    const sevLabel = g.drop >= 3 ? 'HIGH' : 'MED';
    row.className = `gap-row ${sev}`;
    row.innerHTML = `
      <span class="gap-arch" title="${g.arch}">${g.arch}</span>
      <span class="gap-critic">${g.critic.replace(/_/g,' ')}</span>
      <span class="gap-score-a">${g.score_a.toFixed(1)}/12</span>
      <span class="gap-score-b">${g.score_b.toFixed(1)}/12</span>
      <span class="gap-drop">−${g.drop}</span>
      <span class="gap-sev" style="color:${g.drop>=3?'var(--danger)':'var(--warn)'}">${sevLabel}</span>
    `;
    gapList.appendChild(row);
  });
} else if (models.length >= 2) {
  gapNote.textContent = 'no depth regressions detected';
  gapList.innerHTML = '<div class="no-gaps">✓ All critics within 2 pts across models — no regressions.</div>';
} else {
  gapNote.textContent = 'gap detection requires two or more models';
  gapList.innerHTML = `<div style="font-size:0.72rem;color:var(--text3);font-family:'JetBrains Mono',monospace;">Run with two or more models (e.g. <code>--models hetzner gemini_flash</code>) to see regression gaps.</div>`;
}

// single arch — section auto-opens, nothing to hide
</script>
""".strip()


def merge_summaries(paths: list) -> dict:
    """Merge N bench_summary.json files (each with different models) into one summary dict.
    Archs are intersected — only archs present in ALL runs appear in the merged report.
    """
    merged_models = []
    merged_model_strings = {}
    merged_archs = None
    merged_results = {}
    run_ids = []

    for path in paths:
        s = json.loads(Path(path).read_text())
        run_ids.append(s.get("run_id", ""))
        for m in s.get("models", []):
            if m not in merged_models:
                merged_models.append(m)
        merged_model_strings.update(s.get("model_strings", {}))
        archs = s.get("archs", [])
        merged_archs = archs if merged_archs is None else [a for a in merged_archs if a in archs]
        for arch, model_results in s.get("results", {}).items():
            merged_results.setdefault(arch, {}).update(model_results)

    return {
        "run_id":       "+".join(run_ids),
        "mode":         "critics",
        "archs":        merged_archs or [],
        "models":       merged_models,
        "model_strings": merged_model_strings,
        "results":      merged_results,
    }


def generate(summary_path: Path) -> Path:
    summary = json.loads(summary_path.read_text())
    chart   = build_chart_data(summary)

    html = HTML_TEMPLATE.replace("{run_id}", chart["run_id"])
    html = html.replace("{DATA_PLACEHOLDER}", json.dumps(chart))

    out_path = summary_path.parent / "bench_report.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def generate_combined(paths: list, out_dir: Path) -> Path:
    """Merge N summary JSONs and write a combined report to out_dir."""
    merged = merge_summaries(paths)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "bench_summary.json"
    summary_path.write_text(json.dumps(merged, indent=2))
    return generate(summary_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("summary", nargs="?", help="Path to bench_summary.json")
    ap.add_argument("--combine", nargs="+", metavar="SUMMARY",
                    help="Merge N bench_summary.json files into one combined report")
    ap.add_argument("--out-dir", default=None,
                    help="Output directory for combined report (default: bench_results/combined_<timestamp>)")
    ap.add_argument("--open", action="store_true", help="Open report in browser after generating")
    args = ap.parse_args()

    if args.combine:
        import datetime
        out_dir = Path(args.out_dir) if args.out_dir else (
            Path("bench_results") / f"combined_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        out = generate_combined(args.combine, out_dir)
        print(f"Combined report: {out}")
    elif args.summary:
        summary_path = Path(args.summary)
        if not summary_path.exists():
            print(f"ERROR: {summary_path} not found", file=sys.stderr)
            sys.exit(1)
        out = generate(summary_path)
        print(f"Report: {out}")
    else:
        ap.print_help()
        sys.exit(1)

    if args.open:
        import webbrowser
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
