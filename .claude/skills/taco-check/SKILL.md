---
name: taco-check
description: TACO Agent Phase 3 regression gate — unit tests (test_taco_agent + test_taco_rag + test_taco_benchmark) + benchmark sanity check. Run after any change to taco_agent.py, taco_benchmark.py, or taco.py route.
---

# taco-check

Regression gate for TACO Agent Phase 3 (TACOminiRAG + TACOBenchmark).

## What it checks

1. **Unit tests** — `tests/unit/test_taco_agent.py` (Phase 1+2), `tests/unit/test_taco_rag.py` (Phase 3 RAG), `tests/unit/test_taco_benchmark.py` (7-dimension scorer). Target: 48 tests, ~5s.
2. **Benchmark sanity** — instantiates `TACOBenchmark`, scores the first available HOLD_OUT_ARCH, asserts all 7 dims are float or None and overall is in [0, 100].

## Usage

```bash
python3 .claude/skills/taco-check/scripts/taco-check.py
```

Exits 0 on all pass, 1 on any failure. Prints a phase table with durations.

## When to run

- After any change to `chatbot/modules/taco_agent.py`
- After any change to `chatbot/modules/taco_benchmark.py`
- After any change to `chatbot/api/routes/taco.py`
- Before committing Phase 3+ TACO changes
