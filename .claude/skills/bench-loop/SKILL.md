---
name: bench-loop
description: Full TA model evaluation loop — qualify corpus, run critic benchmark across models, generate visual radar diff report, identify gaps, optionally promote best model and rebuild brain. One command drives the complete cycle from corpus selection to verified improvement.
allowed-tools: Bash(python3:*) Bash(cat:*) Bash(ls:*)
---

# bench-loop — TA Model Evaluation Loop

Orchestrates the full benchmark cycle. Stop at each gate and confirm before proceeding.

## Prerequisites

- API running: `./scripts/api/api_start.sh`
- At least one analysed arch with `ground_truth.json` in `report/`
- `.env` has `API_KEY` set

---

## Step 1 — Qualify corpus

```bash
python3 scripts/bench_critics.py --qualify
```

Show the output table. Explain:
- Which archs were auto-selected and why (type coverage, median complexity)
- Estimated token cost and time per model
- Ask the user: **"Use auto-selected corpus, or specify different archs?"**

If user wants to adjust, re-run with `--archs <names>` to preview cost.

---

## Step 2 — Run critic benchmark

```bash
python3 scripts/bench_critics.py \
    --models <model_a> <model_b> \
    [--archs <confirmed archs if custom>]
```

Default model pair: `current openrouter_free`
If user specifies models, use those. Valid aliases: `current`, `hetzner`, `openrouter_free`, `openrouter_auto`.

This will:
- Run MoE-only for each arch × model (Analysis skipped — uses existing ground_truth.json)
- Print the terminal diff table
- Auto-generate `bench_results/<run_id>/bench_report.html`

Report the path to the HTML report so the user can open it.

---

## Step 3 — Interpret visual diff

Read `bench_results/<run_id>/bench_summary.json` and explain:

1. **Panel summary**: Which model has the larger radar polygon overall?
2. **Per-critic**: Which specific critics shrank on model B? Name them and their drop.
3. **Token efficiency**: Which model uses fewer tokens? Is the quality trade-off worth it?
4. **Gap report**: List any critics flagged (depth drop ≥ 2 pts). These need critic-gym rewrites before the model can be promoted.

Ask the user: **"Which model do you want to promote as the new default?"**

---

## Step 4 — Address gaps (if any)

For each flagged critic, recommend:

```
/critic-gym <critic_name>
```

The critic-gym skill will rewrite the prompt for that critic. After each rewrite,
re-run bench for that single critic to verify improvement before moving on.

Do NOT promote a model with unfixed gaps ≥ 3 pts — those are regressions that will
hurt corpus quality.

---

## Step 5 — Promote model (optional)

If user confirms a winner, guide them to update `.env`:

```bash
# Set all critic model vars to the winning model
AGENT_MODEL_ARCHITECT=<winning_model_id>
AGENT_MODEL_TESTER=<winning_model_id>
AGENT_MODEL_RED_TEAM=<winning_model_id>
AGENT_MODEL_PURPLE_TEAM=<winning_model_id>
AGENT_MODEL_BLACKHAT=<winning_model_id>
AGENT_MODEL_SCRUM_MASTER=<winning_model_id>
```

Then restart API: `./scripts/api/api_restart.sh`

---

## Step 6 — Rebuild corpus with new model (optional, overnight)

Only after model is promoted and gaps are fixed:

```bash
# Rerun MoE for all corpus archs with new model
python3 .claude/skills/rerun-moe/scripts/rerun_moe.py --all
```

Warn: this takes ~5h on free-tier OpenRouter. Recommend running overnight.

---

## Step 7 — Rebuild brain

After corpus rerun completes:

```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv('ROOT/.env')
from chatbot.modules.ta_brain_builder import build_brain
build_brain(incremental=False)
print('Brain rebuilt.')
"
```

Or use: `/brain-ingest`

---

## Step 8 — Verify brain improvement

```bash
python3 scripts/bench_critics.py --mode brain
```

This compares Brain predictions vs actual harness output on hold-out archs:
- **Prediction recall ≥ 60%**: Brain is predicting most of what harness finds
- **Divergence % dropping**: Brain learned from the better corpus
- **Brier ≤ 0.10**: Confidence is well-calibrated

If recall improved and divergence dropped → loop complete.
If not → investigate which arch types the brain is missing patterns for (`/qualify-corpus --mode brain`).

---

## Loop summary

```
qualify-corpus
  → bench_critics --models A B      (find best model)
    → gaps? → critic-gym → re-bench
  → promote model in .env
  → rerun-moe --all                  (overnight)
  → brain-ingest
  → bench_critics --mode brain       (verify brain improved)
    → recall/divergence improved? done : investigate
```

---

## Related skills

- `/qualify-corpus` — corpus selection only
- `/critic-gym` — rewrite a critic prompt
- `/rerun-moe` — batch MoE rerun
- `/brain-ingest` — rebuild ta_brain.json
