# TMbench — External Submission Guide

Submit your tool's threat models to the TMbench leaderboard. The benchmark is open: any tool that produces a compliant TM JSON can be scored and listed alongside existing entries.

---

## What you need

1. A tool that generates threat models (LLM agent, static analyser, manual process — anything)
2. Threat model JSON files for each of the 10 corpus architectures (see below)
3. This repo cloned, with `.venv` active

---

## Step 1 — Read the spec

[`docs/tmbench/threatmodel.md`](threatmodel.md) — the full output schema (CC BY 4.0).

Key required sections: Architecture Summary · Threat Actor Profile · Attack Paths (with MITRE technique IDs) · Mitigations (with control IDs) · Risk Summary · Assumptions and Limitations.

---

## Step 2 — Get the corpus architectures

The 10 reference architectures are in [`docs/tmbench/corpus/`](corpus/):

| ID | Tier | Description |
|---|---|---|
| `t1_rest_api` | T1 — Simple (≤5 components) | Minimal REST API |
| `t1_web_app` | T1 — Simple | Single-service web app |
| `t2_cicd_pipeline` | T2 — Moderate (6–15 components) | CI/CD pipeline |
| `t2_microservices` | T2 — Moderate | Multi-service backend |
| `t2_saas_integration` | T2 — Moderate | SaaS integration layer |
| `t3_container_orchestration` | T3 — Complex (16–30 components) | Container orchestration |
| `t3_hybrid_identity` | T3 — Complex | Hybrid identity / AD federation |
| `t3_multicloud_data` | T3 — Complex | Multi-cloud data pipeline |
| `t4_agent_fleet` | T4 — Agentic (AI/ML) | Autonomous agent fleet |
| `t4_rag_pipeline` | T4 — Agentic | RAG pipeline |

Each `.mmd` file is the Mermaid diagram your tool should use as input. Run your tool against each one and produce a TM JSON that conforms to the spec.

**T4 architectures require at least one MITRE ATLAS technique** (e.g. AML.T0043 Craft Adversarial Data). T1–T3 architectures use MITRE Enterprise techniques.

---

## Step 3 — Validate each TM before submission

```bash
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate

# Score a single TM JSON
python3 .claude/skills/tmbench-check/scripts/tmbench-check.py \
  --score path/to/your_tool_t1_rest_api.json \
  --arch t1_rest_api

# Score all 10 at once
for arch in t1_rest_api t1_web_app t2_cicd_pipeline t2_microservices t2_saas_integration \
            t3_container_orchestration t3_hybrid_identity t3_multicloud_data \
            t4_agent_fleet t4_rag_pipeline; do
  python3 .claude/skills/tmbench-check/scripts/tmbench-check.py \
    --score path/to/your_tool_${arch}.json --arch ${arch}
done
```

**Pass threshold:** ≥ 8/13 total TATB score, with no TATB dimension at 0.

TATB dimensions scored (0–3 each, 13-pt max):

| Dimension | What it measures |
|---|---|
| Threat coverage | Attack paths vs ground truth count and technique match |
| TTP accuracy | Technique IDs correct, tactics correctly assigned |
| Risk ranking | Severity ordering consistent with ground truth |
| Plan completeness | Mitigations present and correctly linked to techniques |

---

## Step 4 — Ingest into the leaderboard

Place all 10 TM JSON files in a directory named after your tool:

```
submissions/
  your_tool_name/
    t1_rest_api.json
    t1_web_app.json
    t2_cicd_pipeline.json
    ... (all 10)
```

Then run:

```bash
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate

python3 .claude/skills/tmleaderboard/scripts/tmleaderboard.py \
  --ingest submissions/your_tool_name/ \
  --tool-name "your_tool_name" \
  --tool-label "Your Tool Display Name"
```

This scores all 10 submissions, computes a total TATB score, and adds the entry to the leaderboard JSON. Run `/tmleaderboard` in Claude Code to view the updated leaderboard.

---

## Current leaderboard

| Rank | Tool | Score |
|---|---|---|
| 1 | deepseek_flash | 13.00 |
| 2 | ta_v3_1 | 12.90 |
| 3 | hetzner_27b / nemotron_ultra | 12.80 |
| 5 | gemini_flash | 12.40 |
| 6 | hetzner | 12.10 |

Pass threshold: ≥ 8/13, no TATB dimension at 0.

---

## Notes

- **Attribution:** `threatmodel.md` spec is CC BY 4.0. Attribution: "ThreatAssessor TMbench (github.com/breadtan88)".
- **Partial submissions:** You can submit fewer than 10 architectures. The score reflects the average over submitted arches only; a note flags incomplete coverage.
- **Ground truth files:** `corpus/<arch_id>_ground_truth.json` and `_scores.json` show how the reference TM was scored. Use them to understand scoring behaviour, not as a copy target.
- **Tool identity:** The `--tool-name` slug must be unique. Use lowercase with underscores (e.g. `gpt4o_vanilla`, `claude_haiku_cot`).
