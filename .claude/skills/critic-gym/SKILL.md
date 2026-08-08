---
name: critic-gym
description: Audit and improve MoE critic system prompts. Reads each critic's system prompt, scores it against a rubric (specificity, rubric clarity, output schema, adversarial edge cases, role separation), proposes targeted rewrites, and optionally runs a before/after TATB delta on a corpus architecture to measure quality impact. Uses promptsmith interview logic for rewrites — the goal is a prompt that earns its results, not one that looks polished.
argument-hint: "[critic-name] [--audit-only] [--rewrite <critic>] [--delta <arch>]"
---

# critic-gym — MoE Critic Prompt Auditor

The critics are the quality layer of ThreatAssessor. If their prompts are underspecified,
the analysis is thin regardless of how good the engine is. This skill runs a structured
audit of each critic's system prompt and proposes targeted rewrites.

Not a style pass. A specificity pass: does the prompt tell the model exactly what a strong
finding looks like, what a weak one looks like, and where the line is between the two?

## Run

```bash
# Audit all critics — read-only, no rewrites
python3 .claude/skills/critic-gym/scripts/critic_gym.py --audit-only

# Audit one critic
python3 .claude/skills/critic-gym/scripts/critic_gym.py --audit-only --critic architect

# Propose rewrite for one critic (prompts for approval before writing)
python3 .claude/skills/critic-gym/scripts/critic_gym.py --rewrite architect

# Full loop: audit → rewrite → TATB delta on corpus arch
python3 .claude/skills/critic-gym/scripts/critic_gym.py --rewrite architect --delta web_app
```

## Five phases

### PHASE 1 — INVENTORY
Reads all critic system prompts from `chatbot/modules/agents/critics/`.
Extracts: role statement, rubric structure, output schema, scoring dimensions,
adversarial guidance, separation from other critics.

### PHASE 2 — SCORE
Scores each critic prompt against 6 dimensions (0–2 each, 12 points max):

| Dimension | What it checks |
|---|---|
| Role specificity | Is the critic's unique angle clearly stated? Could another critic be confused for this one? |
| Rubric clarity | Are scoring bands defined with concrete examples (not just "high/medium/low")? |
| Output schema | Is the expected JSON shape fully specified with field names and types? |
| Adversarial edge cases | Does the prompt tell the model what a deliberately misleading finding looks like? |
| Separation | Does the prompt explicitly say what this critic does NOT cover (to avoid overlap)? |
| Actionability | Do findings include enough detail for a sprint ticket, not just a flag? |

Score ≤ 6: needs rewrite. Score 7–9: targeted fix. Score 10+: healthy.

### PHASE 3 — DIAGNOSE
For each dimension that scored 0 or 1, generates a one-line diagnosis:
what is missing, and what a good version would say instead.

### PHASE 4 — REWRITE (gated)
Proposes a targeted rewrite of the weak sections — not a full prompt replacement.
Shows diff of old vs new text. Waits for `y / n / skip`:
- `y` — writes the rewrite to the critic file
- `n` — abort, no changes
- `skip` — skip this critic, move to next

Uses promptsmith-style specificity rules: every claim about behavior is falsifiable,
every scoring band has a concrete example, every output field has a name and type.

### PHASE 5 — DELTA (optional, requires API running)
If `--delta <arch>` provided: runs TATB on the arch before and after the rewrite.
Shows the four-rubric delta (Threat-Relevant, TTP-Accurate, Risk-Defensible, Plan-Actionable).
A rewrite that scores lower on TATB is reverted automatically.

## What NOT to change
- Critic Python logic (scoring weights, orchestration, retry handling)
- The rubric dict structure (`ARCHITECT_RUBRIC`, `TESTER_RUBRIC`, etc.)
- Output JSON schema shapes that downstream code parses

Only the system prompt text and inline rubric descriptions are in scope.

## Critic files
- `chatbot/modules/agents/critics/architect_critic.py` — ARCHITECT_SYSTEM_PROMPT
- `chatbot/modules/agents/critics/tester_critic.py` — TESTER_SYSTEM_PROMPT
- `chatbot/modules/agents/critics/red_teamer_critic.py` — inline in `_create_system_prompt()`
- `chatbot/modules/agents/critics/purple_teamer_critic.py` — inline in `_build_prompt()`
- `chatbot/modules/agents/critics/blackhat_critic.py` — inline in `_build_prompt()`
- `chatbot/modules/agents/critics/scrum_master_critic.py` — multiple inline prompts

## Related
- `/skill-stress-test` — red-teams skill instructions (not LLM prompts)
- `/promptsmith` — interactive prompt interview for new prompts
- `/run-er` — run expert review to see critic output quality live
- `/tatb-score` — measure output quality before/after a change
