# TMbench Baseline Results — v1

**Spec version:** threatmodel/0.1  
**Date:** 2026-11-01  
**Scorer:** tmbench-check.py + tmbench_runner.py  

---

## Leaderboard

| Tool | Type | Archs | Mean | Pass rate | Δ vs GT |
|---|---|---|---|---|---|
| Ground truth ceiling | corpus GT | 10/10 | 13.00/13 | 10/10 | 0 |
| hetzner (Qwen3.6-35B) | LLM → threatmodel/0.1 | 10/10 | 12.10/13 | 10/10 | −0.90 |
| axios THREATMODEL.md | human-authored Markdown | 1/1 | 6/13 | 0/1 | n/a |
| openai/skills security-threat-model | skill → Markdown | 1/1 | 6/13 | 0/1 | n/a |

### TATB breakdown

| Tool | TR | TA | RD | PA | Bonus | Total |
|---|---|---|---|---|---|---|
| Ground truth | 3 | 3 | 3 | 3 | +1 | **13** |
| hetzner | 3 | 3 | 3 | 3 | +0 | **12** |
| axios THREATMODEL.md | 3 | 0 | 3 | 0 | +0 | **6** |
| openai/skills TM skill | 3 | 0 | 3 | 0 | +0 | **6** |

**Pattern:** Every approach scores TR=3 and RD=3 — threat reasoning and risk calibration are table stakes. The differentiator is TA (ATT&CK grounding) and PA (control references). Neither real-world TM documents nor the OpenAI skill output include ATT&CK IDs or NIST/CIS control references — the two dimensions that require deliberate spec compliance investment.

---

## Coverage grid

| arch_id | tier | GT | hetzner |
|---|---|---|---|
| t1_web_app | T1 | 13 | 12 |
| t1_rest_api | T1 | 13 | 12 |
| t2_microservices | T2 | 13 | 12 |
| t2_cicd_pipeline | T2 | 13 | 12 |
| t2_saas_integration | T2 | 13 | 12 |
| t3_multicloud_data | T3 | 13 | 12 |
| t3_hybrid_identity | T3 | 13 | 12 |
| t3_container_orchestration | T3 | 13 | 12 |
| t4_rag_pipeline | T4 | 13 | 12 |
| t4_agent_fleet | T4 | 13 | **13** |

---

## Findings

### Finding 1 — Agentic over-generation (9/10 archs)

**Gap:** `[High] agentic architecture requires at least one MITRE ATLAS technique (AML.T*)`

**Root cause:** Qwen3.6-35B includes a `governance.agentic` block for every architecture regardless of whether the architecture contains an AI/ML or agent component. The spec states the agentic block is required only when the architecture contains an autonomous agent component. Adding the block to a T1 web app or T2 microservices deployment triggers the ATLAS technique requirement, which is then unmet — costing the completeness bonus on all non-agentic architectures.

**Signal value:** The model's TATB quality is max (3/3 on all four dimensions) for all 10 architectures. The only failure is spec compliance on the agentic block trigger condition. This is a meaningful distinction: a tool can produce high-quality substantive threat models and still fail on structural spec compliance.

**t4_agent_fleet exception:** The one genuinely agentic architecture (multi-tenant LLM, prompt guard, agent orchestration) scored 13/13 — the model correctly included ATLAS techniques and a full agentic governance block.

### Finding 2 — Max token budget for T3/T4 archs

T3 architectures (20-25 components, 8+ paths) require ~12,000 tokens for a complete TM JSON. The generator's default was raised to 14,000 to prevent mid-JSON truncation.

---

## Spec feedback surfaced

From finding 1: The `governance.agentic` trigger condition in §1.6 ("architectures with autonomous agents, LLM-driven components, or tool-calling pipelines") may benefit from an explicit component role list (agent | llm | tool_caller | ai | ml) to give tool implementors a deterministic trigger rule. This is already noted in spec-review mode as a candidate patch.

---

## Next tools

To add a second tool entry:
```bash
python3 scripts/tmbench/tmbench_generate.py --tool gpt4o --all    # requires OPENAI_API_KEY
python3 scripts/tmbench/tmbench_generate.py --tool ta_v3 --all    # requires running TA API
```

After generation, the leaderboard updates automatically.
