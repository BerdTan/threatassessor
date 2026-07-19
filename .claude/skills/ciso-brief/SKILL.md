---
name: ciso-brief
description: CISO-ready one-page security brief. Pipeline — PLAN (data inventory) → BUILD (metrics + LLM narrative) → LOOK (trend delta vs previous snapshot) → RELEASE (print brief + write snapshot JSON + dated MD). Multi-critic-corroborated findings sorted by critic breadth. Investment tier bars. Snapshot stored at ciso_brief_latest.json; each run produces a dated MD archive. Runs on one architecture or the full corpus.
allowed-tools: Bash(python3:*) Bash(source:*)
compatibility: Requires ground_truth.json. For full brief (confidence, tiers, LLM narrative), also needs 07_moe_orchestrator.json and 08_scrum_master.json — run /run-er --full first.
---

# ciso-brief — CISO Security Brief

Produces a structured one-page brief designed for executives and CISOs:
- Visual risk/confidence/defensibility gauges
- Top findings sorted by **critic breadth first** (multi-critic confirmed findings lead, single-critic follow) — prevents bias toward any one reviewer
- Investment tier table with risk-reduction progress bars and cost/effort
- LLM-generated 2-sentence assessment and first-action recommendation (plain English, no jargon)

## Run

```bash
# Single architecture
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/ciso-brief/scripts/ciso-brief.py 21_agentic_ai_system

# Skip LLM narrative (faster, deterministic only)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/ciso-brief/scripts/ciso-brief.py 21_agentic_ai_system --no-llm

# Most recent report
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/ciso-brief/scripts/ciso-brief.py

# All architectures — one brief per arch, corpus summary table at end
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/ciso-brief/scripts/ciso-brief.py --corpus

# Top 5 highest-risk architectures only
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/ciso-brief/scripts/ciso-brief.py --corpus --top 5 --no-llm
```

## Output sections

```
┌──────────────────────────────────────────────────────────────┐
│  CISO BRIEF — 21_agentic_ai_system      2026-07-19           │
│  Confidence: 56.8%  ACTION REQUIRED                           │
└──────────────────────────────────────────────────────────────┘

RISK AT A GLANCE
  Confidence    56.8%  ███████████░░░░░░░░░  ACTION REQUIRED
  Attack risk    76/100  ███████████████░░░░░  HIGH EXPOSURE
  Defensibility  55/100  ███████████░░░░░░░░░  PARTIAL
  Attack paths  15  (8 critical confirmed · 45 techniques)
  ⚠ REDESIGN SIGNAL

TOP FINDINGS — KNOWN CONFIRMED  (3 multi-critic · 2 single-critic confirmed)
  Sorted by: critic breadth (multi-critic first) then severity

  1. CRITICAL  [Blackhat + Red Team]
     WebUI pivot allows T1190 exploitation to reach 14 targets without WAF.
     → Deploy WAF at WebUI ingress with OWASP Top 10 ruleset.

  2. CRITICAL  [Red Team + Blackhat]
     No MFA — credential attacks effective across all 14 user journeys.
     → Enforce MFA at Users authentication boundary.

INVESTMENT OPTIONS
  Tier          Cost          Effort        Risk score after controls
  Quick Win     $17K–$41K     1–2 weeks     50 → 28  ██████░░░░░░  −44%  [YES]
  Recommended   $27K–$68K     1–2 weeks     50 → 12  ██░░░░░░░░░░  −76%  [YES]
  Maximum        $7K–$20K     1–2 weeks     50 →  6  █░░░░░░░░░░░  −87%  [MAYBE]

ASSESSMENT
  This AI system is vulnerable to a single breach that exposes 14 connected systems…

RECOMMENDED FIRST ACTION
  Deploy MFA and network segmentation at WebUI to break the primary attack chain…
```

## Finding selection logic

- **KNOWN only** — `confidence_label == "KNOWN"` in `consensus_recommendations`. UNSURE items excluded.
- **Sorted by critic breadth first** — `"blackhat+red_team"` (2 critics) ranks above `"purple_team"` (1 critic) regardless of severity. Within same breadth, CRITICAL before HIGH.
- This prevents the brief from being biased toward any single critic's perspective.

## LLM narrative

Two sentences generated per architecture:
1. **Assessment** — current posture and the single biggest structural risk (board language, no jargon)
2. **Recommended First Action** — what to do, where, and expected outcome

The LLM receives only structured facts (risk score, top 2 findings, investment tier data) — it synthesises language, not analysis. Use `--no-llm` to skip (deterministic only, ~1s per arch).

## Prerequisites

| Data | Required for |
|---|---|
| `ground_truth.json` | All sections |
| `07_moe_orchestrator.json` | Confidence, top findings, investment tiers |
| `08_scrum_master.json` | Redesign signal, SM confidence, narrative context |

Run `/run-er 21_agentic_ai_system --full` first if MoE/SM files are missing.

## Related skills

- `/run-er` — run Expert Review to generate the ER data
- `/summarise-er` — engineer-level ER digest (more technical detail)
- `/review-unsure` — triage UNSURE items excluded from the brief
- `/tatb-corpus` — corpus-wide quality scores
