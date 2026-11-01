# TMbench Corpus

Reference architectures with ground truth threat models, scored against `threatmodel.md` v0.1.

## Complexity tiers

| Tier | Component count | Attack paths (min) | Description |
|---|---|---|---|
| T1 — Simple | ≤ 5 | 3 | Single-service web app, basic API |
| T2 — Moderate | 6–15 | 5 | Multi-service, one trust boundary crossing |
| T3 — Complex | 16–30 | 8 | Multi-cloud, multiple trust boundaries |
| T4 — Agentic | any + AI/ML agent | 8 + ATLAS | LLM pipeline, autonomous agent fleet |

## Target inventory (Step B)

10 architectures covering all four tiers and at least:
- 2 T1 (simple web + simple API)
- 3 T2 (microservices, CI/CD pipeline, SaaS integration)
- 3 T3 (multi-cloud data pipeline, hybrid identity, container orchestration)
- 2 T4 (RAG pipeline, autonomous agent fleet — sourced from TA corpus)

## Entry format

Each entry:
```
corpus/
  <arch_id>.mmd                  # Mermaid architecture diagram
  <arch_id>_ground_truth.json    # Reference TM (threatmodel.md output schema)
  <arch_id>_scores.json          # TATB scores for the ground truth TM
```

## Status

Corpus population is Step B in the TMbench build sequence. Placeholder until Step B begins.
