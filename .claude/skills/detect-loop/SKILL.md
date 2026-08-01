---
name: detect-loop
description: DETECT feedback loop — observe rule coverage across all corpus architectures, diagnose uncovered rules, prescribe a new incident scenario, gate on human approval, apply (writes scenario to incident_simulator.py + test assertion), verify with /check-detect, and log delta to docs/DECISIONS.md. Mirrors the tatb-loop pattern for the SOC detection layer. Use when DETECT rules have zero or thin real-corpus coverage, or when a new real-world AI security incident should be grounded into the ruleset.
allowed-tools: Bash(python3:*) Bash(source:*) Bash(git:*) Bash(grep:*)
---

# detect-loop — Evidence-Driven DETECT Coverage Improvement

Runs an observe→diagnose→prescribe→gate→apply→verify cycle. Each iteration finds
the rule with the worst real-corpus coverage, identifies which architecture type
would realistically produce that signal, synthesises a minimal scenario payload,
waits for human approval, adds the scenario to incident_simulator.py + a test
assertion, then re-runs /check-detect to confirm the delta.

## Run

```bash
# Full corpus — find and fix the worst-covered rule
python3 .claude/skills/detect-loop/scripts/detect-loop.py

# Target a specific uncovered rule
python3 .claude/skills/detect-loop/scripts/detect-loop.py --rule DETECT-014

# Observe only — show coverage matrix, no changes
python3 .claude/skills/detect-loop/scripts/detect-loop.py --observe-only

# Add a new real-world incident as a scenario
python3 .claude/skills/detect-loop/scripts/detect-loop.py --incident "OpenAI GPT-4o jailbreak 2026"
```

## What it does

1. **Observe** — runs the rule evaluator over all corpus governance_signals.json files.
   Produces a coverage matrix: rule × arch (fire/no-fire). Computes a coverage score
   per rule: (archs_fired / total_archs_with_signals) × 100.

2. **Diagnose** — identifies the rule with the lowest real-corpus coverage score.
   Maps the rule to which signal fields it reads, and which arch type in the corpus
   would realistically produce those signals.

3. **Prescribe** — generates a minimal scenario payload (governance_signals dict) that
   fires the target rule on the target arch type. Shows the payload for review.
   Also generates the test assertion stub.

4. **Gate** — prints the full prescription (scenario signals + expected rules + target
   arch + test stub) and waits for `y / n / skip`:
   - `y`   — apply the scenario and test
   - `n`   — abort, do not write anything
   - `skip` — skip this rule, diagnose the next worst

5. **Apply** — adds the scenario function and SCENARIOS/EXPECTED_RULES entry to
   incident_simulator.py. Adds the test assertion to test_incident_simulator.py.
   Optionally writes the simulated governance_signals to report/<arch>/.

6. **Verify** — re-runs the full /check-detect suite. Shows before/after coverage
   delta per rule. Confirms no regressions.

7. **Log** — prepends a dated entry to docs/DECISIONS.md:
   rule, arch type, scenario name, signal fields used, before/after coverage.

## Coverage score

  coverage_score(rule) = (archs_where_rule_fired / archs_with_governance_signals) × 100

  Rules with 0% real-corpus coverage are prioritised. Among tied rules, higher
  severity rules are prescribed first.

## Safety

- Never writes to source files without explicit `y` approval at the gate.
- Never modifies existing scenarios — only adds new ones.
- Never deletes test assertions.
- Does NOT git-commit. Run `git diff` after apply to review before committing.
