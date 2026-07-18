---
name: cost-estimate
description: Compute investment tier effort and cost for one or all corpus architectures, using the shared CONTROL_BENCHMARK table (CIS/NIST/Gartner/SANS/OWASP). Also audits the benchmark table itself for missing entries, stale references, and suggested additions. Use after a new architecture analysis, after adding controls to the benchmark, or quarterly to verify industry references are current.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# cost-estimate — Investment Tier Cost/Effort Estimator

Reads investment tier items from `07_moe_orchestrator.json`, matches each control to the shared `CONTROL_BENCHMARK` table in `chatbot/modules/control_cost_benchmark.py`, and computes:

- **Effort** — critical-path control (longest calendar task sets the bottleneck)
- **Cost** — sum of per-control benchmark ranges across matched controls
- **Coverage** — % of tier items matched to the benchmark (unmatched items flagged for addition)
- **Attribution** — CIS Controls v8 IG1–IG3 / NIST SP 800-53 Rev 5 / Gartner Market Guide (2025) / SANS Spending Survey (2025) / NIST AI RMF 1.0 / OWASP LLM Top 10 (2025)

## Run

```bash
# Most recent report
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/cost-estimate/scripts/cost-estimate.py

# Single architecture
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/cost-estimate/scripts/cost-estimate.py 21_agentic_ai_system

# Full corpus — summary table
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/cost-estimate/scripts/cost-estimate.py --all

# Audit the benchmark table — find gaps, stale refs, suggested additions
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/cost-estimate/scripts/cost-estimate.py --self-eval

# JSON output (single arch, for piping)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/cost-estimate/scripts/cost-estimate.py 21_agentic_ai_system --json
```

## Output

### Single arch
```
Cost-Effort Estimate — 21_agentic_ai_system
  Source: Benchmark estimate — CIS Controls v8 IG1–IG3 / NIST SP 800-53 Rev 5 / …

  ⚡  Quick Wins
     Effort:   1–2 weeks
     Cost:     $15K–$35K
     Coverage: 83%  (5/6 controls matched)
     Breakdown:
       · MFA enforcement            2–4 hours    $500–$1K
       · WAF deployment             1–2 days     $1K–$3K
       · Service mesh               1–2 weeks    $10K–$20K
       …
     ⚠ 1 item not in benchmark: capability-based access control
```

### Corpus (--all)
```
Architecture                       ⚡ Quick Wins              ⭐ Recommended             🔒 Maximum           Cov%
21_agentic_ai_system               1–2 weeks / $15K–$35K     2–3 weeks / $30K–$70K     …                   83%
03_aws_3tier                       1–2 days  / $5K–$15K      …                          …                   91%
```

### Self-eval (--self-eval)
```
1. Controls appearing in corpus NOT in benchmark table
   ●●●●  4×  capability-based access control
   ●●●   3×  detection sla
   …

2. Benchmark table coverage by effort tier
   2–4 hours     13 entries  mfa, logging, rate limiting …
   1–2 weeks      7 entries  service mesh, network segmentation …

3. Industry reference health
   ✓ current   CIS Controls v8 IG1–IG3 (2021)
   ⚠ verify    Gartner Market Guide for Security Tools (2025) — Annual publication …
   …

4. Suggested additions to CONTROL_BENCHMARK
   "capability-based access control"
     → ("3–5 days", 3, 8)  # CIS Controls v8 IG2 safeguard 6.7
```

## When to run

| Trigger | Command |
|---------|---------|
| After a new ER run to see updated tier costs | `cost-estimate <arch>` |
| After adding entries to `CONTROL_BENCHMARK` | `cost-estimate --self-eval` to confirm coverage improved |
| After regenerating corpus reports | `cost-estimate --all` to spot low-coverage archs |
| Quarterly benchmark review | `cost-estimate --self-eval` to check reference freshness |

## Benchmark table

Source of truth: `chatbot/modules/control_cost_benchmark.py`

To add a missing control:
1. Run `--self-eval` to see candidates and suggested ranges
2. Add entry to `CONTROL_BENCHMARK` dict with `(effort_label, cost_low_k, cost_high_k)` and a comment citing the source
3. Re-run `cost-estimate --all` to verify coverage improved

## Notes

- Requires `07_moe_orchestrator.json` — only present after an Expert Review run
- Cost is **cumulative** (sum across tier) not per-control; effort is the **critical path** (longest single task)
- Unmatched controls still count toward tier totals in the UI — they just don't contribute to the cost sum
- `--self-eval` never modifies files — read-only audit
