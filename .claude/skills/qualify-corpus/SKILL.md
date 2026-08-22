---
name: qualify-corpus
description: Select a representative, time/cost-bounded benchmark corpus from all available report/ architectures. Groups by arch_type, picks median-complexity arch per type, enforces token budget, always includes AI hold-outs. Use before running bench_critics.py to avoid over-spending on redundant or low-value archs. Outputs a qualified corpus table, estimated time/tokens, and the exact --archs flag to copy into bench_critics.
allowed-tools: Bash(python3:*)
---

# qualify-corpus — Benchmark Corpus Selector

Selects a fit-for-purpose benchmark corpus from `report/` without running any analysis.
Reads `ground_truth.json` + existing `07_moe_orchestrator.json` (if present) to estimate
complexity and token cost. Produces a ranked, budget-aware list ready to paste into
`bench_critics.py`.

## Selection logic

| Step | Rule |
|------|------|
| Exclude | `syn_*`, `99_*`, `test_*`, versioned duplicates (`_1`, `_2`, ...) |
| Group | By `architecture_type` from `ground_truth.metadata` |
| Pick | Median `node_count` arch per type (avoids extremes) |
| Always include | Both `ai_system` hold-outs (most distinctive, never in brain training) |
| Cap | ≤ 8 archs total |
| Budget | ≤ 600k tokens per model (drops lowest-TTP non-hold-outs until under budget) |

## Token estimation

- Existing `07_moe_orchestrator.json`: reads `pipeline_perf.total_llm_tokens` (exact)
- No prior run: estimates from `node_count × 18,748` (calibrated on `01_minimal_vulnerable`)

## Modes

- `--mode critics` (default) — selects for critic depth/breadth benchmarking
- `--mode brain`   — selects HOLD_OUT_ARCHS only (honest brain eval set)

## Usage

```bash
python3 scripts/bench_critics.py --qualify                   # critics mode
python3 scripts/bench_critics.py --qualify --mode brain      # brain mode
python3 scripts/bench_critics.py --qualify --mode critics    # explicit
```

## Output example

```
Corpus Qualification — critics mode
────────────────────────────────────────────────────────────────
Arch                    Type         N   TTPs  Tok est   Hold  Sel
────────────────────────────────────────────────────────────────
21_agentic_ai_system    ai_system   19    46    356k    HOLD   ✓
10_complex_enterprise   web_app     18    37    337k    HOLD   ✓
13_iot_architecture     iot          7    21    131k            ✓
06_azure_hub_spoke      cloud        7    25    131k            ✓
19_blockchain_node      generic      7    29    131k            ✓
...

Bench corpus: 6 archs  ~750k tokens/model  ~72m/model
Full corpus:  28 archs ~2.1M tokens/model  ~5h36m/model

Run with: python3 scripts/bench_critics.py --archs 21_agentic_ai_system ...
```

## When to re-qualify

- After adding new architectures to `report/`
- After adding a new `arch_type` to the corpus
- Before any overnight benchmark run (verify budget is still within limits)
- After changing the token budget constant `MAX_BENCH_TOKENS` in `bench_critics.py`

## Related

- `bench-critics` — runs the actual benchmark after corpus is qualified
- `rerun-moe` — re-runs MoE on corpus with a new model (feeds brain re-ingest)
- `brain-ingest` — rebuilds `ta_brain.json` after corpus rerun
