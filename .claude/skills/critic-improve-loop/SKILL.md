---
name: critic-improve-loop
description: Self-improvement loop for MoE critics targeting a specific architecture. Scores all 6 critics (including SM), prioritises by gap, runs critic-gym on the weakest, verifies improvement via re-bench, then contributes the improved run to Brain and Workspace. SM branches on lever type — prompt rewrite vs code flag.
argument-hint: "--arch <arch> [--target <score>] [--rounds <n>] [--dry-run]"
---

# critic-improve-loop — Critic Self-Improvement Loop

Closes the critic quality flywheel for a specific architecture:
score → prioritise → improve → verify → contribute.

Not a blind rewrite tool. Each improvement is gated against a re-bench;
a change that doesn't move the score ≥ 0.5/12 is reverted automatically.

## Prerequisites

- API running: `./scripts/api/api_start.sh`
- Arch has existing `report/<arch>/ground_truth.json` (analysed at least once)
- `.env` has `API_KEY` and LLM provider set

---

## Step 1 — Score all critics on the target arch

```bash
python3 .claude/skills/critic-improve-loop/scripts/critic_improve_loop.py \
    --arch <arch> --score-only
```

Reads existing bench summary if present, or triggers a fresh single-arch bench run.
Prints the priority table: critic | score/12 | gap | lever | hint.

**SM lever detection** (automatic):
- `coverage` lever — when `action_plan / impediments_found < 0.6` → code issue, not prompt
- `completeness` lever — when coverage ≥ 0.6 but first_steps thin or tiers missing → prompt issue

Show the table to the user. Ask: **"Proceed with this priority order, or skip any critics?"**

---

## Step 2 — Improve lowest-scoring critic (one at a time)

For each critic in priority order (largest gap first, skip those ≥ target):

```bash
# Non-SM critics — prompt rewrite via critic-gym
python3 .claude/skills/critic-gym/scripts/critic_gym.py \
    --rewrite <critic> --delta <arch>

# SM: completeness/breadth lever — prompt rewrite targeting proposals
python3 .claude/skills/critic-gym/scripts/critic_gym.py \
    --rewrite scrum_master --delta <arch>

# SM: coverage lever — flag for manual code review, do not call critic-gym
echo "SM coverage gap is a code issue — see scrum_master_critic.py harmony branch"
```

After each rewrite, wait for user approval of the diff before writing.

---

## Step 3 — Re-bench to verify improvement

```bash
python3 scripts/bench_critics.py --mode critics --archs <arch>
python3 .claude/skills/critic-improve-loop/scripts/critic_improve_loop.py \
    --arch <arch> --compare <prev_run_id> <new_run_id>
```

Show delta table: critic | before | after | delta | verdict (keep / revert).

**Gate rule**: keep if delta ≥ +0.5/12. Revert prompt change via git if not:
```bash
git checkout HEAD -- chatbot/modules/agents/critics/<critic>_critic.py
```

---

## Step 4 — Loop or graduate

- If any critic still below target AND rounds remaining → go back to Step 2 for next-lowest.
- If all critics ≥ target OR rounds exhausted → proceed to Step 5.

Report round summary: which critics improved, which didn't move, which were skipped.
Ask: **"Contribute this run to Brain and Workspace?"**

---

## Step 5 — Contribute back

```bash
# Ingest improved run into Brain instance layer
python3 .claude/skills/brain-ingest/scripts/brain_ingest.py --arch <arch>

# Rebuild Brain pattern layer to pick up the new instance
python3 .claude/skills/brain-grow/scripts/brain_grow.py --rounds 0
```

Then commit the improved critic prompts:
```bash
git add chatbot/modules/agents/critics/
git commit -m "feat(critics): <arch> improve loop — <summary of changes>"
```

---

## Priority ordering

Critic scoring uses gap from target (default 11.5/12), largest gap first.
Tie-break rules (applied in order):
1. Smaller gap-to-fix first — prefer critics where a prompt change reliably moves score
2. `red_team` and `blackhat` before `purple_team` — adversarial depth is faster to improve
3. `architect` before `tester` — structural gaps unlock downstream gains
4. SM last unless its gap is the largest — two-lever complexity makes it slowest

---

## SM improvement guide

| SM score | Coverage | Completeness | Action |
|---|---|---|---|
| < 7/12 | < 0.6 | any | Code flag — harmony branch not covering enough impediments |
| < 7/12 | ≥ 0.6 | < 0.7 | Prompt: improve proposal specificity in `_formulate_proposals` LLM call |
| 7–9/12 | ≥ 0.6 | ≥ 0.7 | Prompt: improve `first_step` concreteness + tier labelling |
| > 9/12 | any | any | Prompt: acceptance criteria + impact/effort matrix |

---

## Contribute-back flow

```
bench score improved
      ↓
brain-ingest <arch>       ← instance layer updated
      ↓
brain-grow --rounds 0     ← pattern layer distilled from new instance
      ↓
commit critic prompt changes
      ↓
(optional) rerun-moe --all  ← apply improved prompts corpus-wide overnight
```

The Workspace reflects the next analysis run automatically — no separate step needed.

---

## What this skill does NOT do

- Does not auto-push to GitHub — commit and push are manual steps
- Does not run full corpus rerun — that's `rerun-moe --all` (overnight task)
- Does not modify critic Python logic — only system prompt text and rubric descriptions
- Does not touch Brain hold-out archs (`HOLD_OUT_ARCHS`) — those remain unseen by the pattern layer
