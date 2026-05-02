# Testing Documentation

---
**Last Updated:** 2026-05-02  
**Status:** Current
---

## Quick Links

### For Users: How to Run Tests
👉 **[../../tests/README.md](../../tests/README.md)** - Start here for running tests

### For Developers: Testing Strategy

- **[TESTING_STRATEGY.md](TESTING_STRATEGY.md)** - Why we test this way (iterative validation)
- **[DATA_STRATEGY.md](DATA_STRATEGY.md)** - How to generate test data

---

## Documentation Structure

**Single source of truth:**

```
tests/                              User-facing: How to use tests
├── README.md                       → Quick start, run commands, results
├── TEST_DATA_ASSESSMENT.md         → Coverage analysis (17/703 techniques)
└── FALLBACK_ANALYSIS.md            → Fallback algorithm quality (30% accuracy)

docs/testing/                       Developer-facing: Testing philosophy
├── TESTING_STRATEGY.md             → Why we test this way (stages 0-4)
└── DATA_STRATEGY.md                → How to generate test queries
```

**Clear separation:**
- `tests/` = Executable knowledge (run this, see results)
- `docs/testing/` = Strategic knowledge (planning, methodology)

---

## Quick Start

**Run tests:**
```bash
# See tests/README.md for complete guide
pytest tests/ -v                     # Full suite
python3 -m chatbot.main --self-test  # Quick validation (8s)
```

**Understand strategy:**
```bash
# Read docs/testing/TESTING_STRATEGY.md for iterative approach
# Stage 0: Infrastructure (65% confidence)
# Stage 1: Tactic coverage (75% confidence)
# Stage 4: Production feedback (ongoing)
```

---

## Test Results

**Latest: Phase 2.2**
- Overall accuracy: 84.9% (146 queries)
- Tactic coverage: 14/14 (100%)
- Confidence: 79% (production-ready)

**See:** [../../tests/results/phase2.2/summary.md](../../tests/results/phase2.2/summary.md)

---

**No duplication. Single source of truth. Clear intent.**
