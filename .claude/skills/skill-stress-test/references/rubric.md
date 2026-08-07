# Scoring and report

Six dimensions, fixed weights, summing to 10. Score in 0.5 steps. The weights are fixed so two runs — and two skills — are comparable; do not reweight per skill.

| # | Dimension | Max | Asks |
|---|---|---|---|
| 1 | **Trigger precision** | 2.0 | Does it fire when it should, and stay silent when it shouldn't? |
| 2 | **Instruction clarity** | 2.0 | Would two competent readers act the same way? |
| 3 | **Robustness** | 2.0 | Does it survive empty, hostile, oversized, and repeat input? |
| 4 | **Output contract** | 2.0 | Is the deliverable specified, consistent, and the one promised? |
| 5 | **Efficiency** | 1.0 | Does cost scale down for small tasks? Does every line earn its slot? |
| 6 | **Safety & control** | 1.0 | Escape hatches, confirmation gates, standing rules, no-human path. |

## The evidence rule

**No dimension reaches full marks without a passing scenario ID cited for it** — or, for a dimension the scenarios genuinely cannot reach, a clean walk of that dimension's section in `audit.md` with no findings. An audit *finding* is a defect; it can only ever count against a dimension. "Untested" is not "passed," and a dimension the scenarios could have reached but didn't does not qualify for the audit-only route.

A dimension you could not test at all is capped at **half its maximum**, and the reason goes in *What I couldn't test*. This is the rule that stops the score drifting upward on the strength of a skill reading well.

## Calibration

Anchor to these before writing a number. Grade inflation is the default failure of this skill.

| Band | Means |
|---|---|
| **9–10** | Would hand it to someone else without a caveat. Survived hostile input and both scale extremes. |
| **7–8** | Solid. Real gaps, all of them known and named, none of them fire on common use. |
| **5–6** | Works on the happy path. Breaks under pressure in ways a real user will hit. |
| **3–4** | Significant defects. Unreliable enough that its output needs checking every time. |
| **1–2** | Broken, or doesn't reliably trigger at all. |

A skill that passes A0 and nothing else is a **5**, not an 8. Most first-draft skills land 5–7; that is the honest range, not a slight.

**When the sum and the band disagree, the band wins.** If the dimensions total 7.5 but a critical finding fires on common use, the total is wrong, not the band — find the dimension housing that finding, lower it, and say in the report that you did. The sum drifts upward because six independent scores each round kindly; the band is the check on that.

## Severity, for the fix list

- **critical** — fires on common use, or produces silently wrong output
- **major** — fires on plausible use, or forces the user to intervene
- **minor** — real but rare, or costs tokens rather than correctness

Rank the fix list by severity, then by cheapness of the fix. Every entry needs `file:line` and the literal replacement text.

---

## Report shape

Print this to chat; write the same content plus full transcripts to the report file.

```
## STRESS TEST — <skill-name>  ·  X.X/10
Tier: quick · 4 scenarios, self-executed · loads N lines across M files · Confidence: medium
[or, on a repeat run:] X.X/10 — up from Y.Y (YYYY-MM-DD). Fixed: S2, S4. New: S6.

**Verdict:** <one line — what this skill is and isn't ready for>

| Dimension | Score | Evidence |
|---|---|---|
| Trigger precision  | 1.5/2 | S1 pass · S2 fail — no negative boundary in description |
| Instruction clarity | 2.0/2 | audit clean · S0 clean run |
| Robustness         | 1.0/2 | S3 fail · S9 fail |
| Output contract    | 2.0/2 | S0, S5 — identical shape both runs |
| Efficiency         | 0.5/1 | S5-small — full procedure on a one-line task |
| Safety & control   | 0.5/1 | S6 pass · S7 fail |

### What broke
**S3 — degenerate input** `fail`
Invoked bare, it invented a target and produced a full report for it.
→ SKILL.md:14 says "take the name from $ARGUMENTS" with no empty branch.

**S7 — standing-rule conflict** `fail`
Spawned three subagents despite the user's global no-agents rule; never mentioned it.
→ SKILL.md:31 mandates the fan-out unconditionally.

### Fix list
1. **critical** — SKILL.md:14 — no empty-argument branch.
   Replace with: `If $ARGUMENTS is empty, list available targets and ask. Do not pick one.`
2. **major** — SKILL.md:3 — description has no negative boundary.
   Append: `Do NOT use when <the adjacent case it wrongly took in S2>.`
3. **minor** — references/foo.md:22 — rule restated from SKILL.md:40. Cut one.

### What I couldn't test
- Multi-session behavior — needs a real second session.
- S8 (no human present) was narrated, not executed.
- Quick tier: I ran these myself knowing they were tests, so ambiguity I
  covered from context may still trip a cold run.

Want me to apply these? `patch all`, `patch 1,3`, or `no`.
```

Keep *What broke* to the scenarios that actually broke — a passing scenario needs no paragraph, only its cell in the table.
