# tmbench-check — TMbench Spec Scorer + Flywheel

Score a threat model JSON against `docs/tmbench/threatmodel.md`, identify improvement areas,
and track spec quality over time. The flywheel: each run reveals both output gaps and
underspecified spec areas — both improve on each cycle.

## Run

```bash
# Score one TM JSON against the spec
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmbench-check/scripts/tmbench-check.py --score <path/to/tm.json>

# Compare multiple TMs (directory of JSON files) — leaderboard view
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmbench-check/scripts/tmbench-check.py --compare docs/tmbench/results/

# Spec review mode — identify spec gaps from patterns across all scored runs
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmbench-check/scripts/tmbench-check.py --spec-review

# Full pipeline: score + compare + spec-review in one pass
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmbench-check/scripts/tmbench-check.py --all
```

## Output

### --score mode

```
TMbench Score Report
Architecture: <arch_id>
Produced by: <tool>
Spec version: threatmodel/0.1

Section completeness:
  architecture_summary   ✓
  threat_actors          ✓ (non_capabilities missing on 1/2 actors)
  attack_paths           ✓ (4 paths — below T2 minimum of 5)
  mitigations            ⚠ 2 attack paths have no mitigation
  findings               ✓
  governance             ✗ agentic block required but absent

TATB Rubric:
  Threat-Relevant    2/3  — 1 path is generic (no component grounding)
  TTP-Accurate       3/3
  Risk-Defensible    1/3  — all findings rated High; no differentiation
  Plan-Actionable    2/3  — 2 findings have vague mitigations

Score: 8/13  [PASS — threshold 8, no zeros]

Gaps (priority order):
  [Critical] agentic governance block required for this architecture
  [High]     attack path count below T2 minimum (4/5)
  [High]     2 attack paths without mitigation
  [Medium]   non_capabilities missing on 1 threat actor
  [Low]      1 attack path has no component grounding

Confidence standing: PASS — borderline; address Critical + High gaps to reach solid standing
```

### --compare mode

Leaderboard table across all scored TMs in the target directory:
```
TMbench Leaderboard  (spec v0.1)
  Tool / Run              TR  TA  RD  PA  Score  Status
  ta_v3_microservices     3   3   2   3   11/13  PASS
  openai_skill_simple     2   1   2   2    7/13  FAIL (TTP-Accurate 1)
  manual_stride_complex   2   2   1   2    7/13  FAIL (Risk-Defensible 1)
  ta_v3_rag_pipeline      3   3   3   3   13/13  PASS
```

### --spec-review mode

Surfaces patterns that indicate the spec itself needs tightening:

```
Spec Review — patterns across N scored runs
  Pattern: "Risk-Defensible frequently scores 1 — all-same-severity"
    Seen in: 4/7 runs
    Possible spec gap: §2.3 does not define what constitutes a "materially different exposure"
    Suggested patch: add worked example with two paths at different likelihood — show expected rating spread

  Pattern: "agentic block absent even when agent component present"
    Seen in: 3/7 runs
    Possible spec gap: §1.6 agentic trigger condition is ambiguous — "autonomous agent" not defined
    Suggested patch: add component role list that triggers agentic requirement (role: agent|llm|tool_caller)

  Pattern: "non_capabilities field present but always empty list"
    Seen in: 5/7 runs
    Possible spec gap: §1.2 does not give examples of valid non_capabilities entries
    Suggested patch: add minimum 2 entries requirement + worked examples

Spec improvement candidates (rank by frequency):
  1. §2.3 Risk-Defensible — add worked example for rating spread (4/7 runs affected)
  2. §1.6 agentic trigger — tighten component role definition (3/7 runs affected)
  3. §1.2 non_capabilities — add minimum count + examples (5/7 runs affected — but low severity gap)
```

## Flywheel

Each `--spec-review` run produces spec patch candidates. The loop:

1. Score a batch of TMs with `--score`
2. Run `--spec-review` to surface spec gaps
3. Apply patches to `docs/tmbench/threatmodel.md`
4. Re-score the same TMs against the patched spec
5. Gaps that shrink confirm the patch was correct; gaps that persist reveal deeper issues
6. Log each spec version change in `docs/tmbench/CHANGELOG.md`

This is the same flywheel pattern as TAgym (Brier-driven iteration) applied to the spec itself
rather than to a model's output quality.

## Confidence standing labels

| Score | Label |
|---|---|
| 12–13 | Solid — production-grade TM |
| 10–11 | Good — minor gaps, addressable in one pass |
| 8–9 | Pass (borderline) — gaps present, not blocking |
| 5–7 | Fail — multiple dimension weaknesses |
| 0–4 | Reject — fundamental coverage missing |

A FAIL with any TATB dimension at 0 is an automatic Reject regardless of total score.

## Spec version tracking

Each scored result records `spec_version` so leaderboard comparisons stay valid across spec
updates. `--compare` warns when mixing results from different spec versions.
