# Path A — Revision · Path B — Autonomous

Two procedures that replace the interview. You arrived here from Step 0 triage.

---

# Path A — Revision (an existing prompt)

Most of the specification is already written down. Your job is **diagnosis, not elicitation.**

Skip Step 1 — restating a vision that's written down in front of you is theater. If your reading of *why* it's failing might be wrong, restate the **diagnosis** instead, and invite correction on that.

## A1 — Read the prompt against the dimensions

Walk `references/dimensions.md`, but read the answers out of **the artifact, not the brief.** Dimensions the existing prompt already pins down are *stated* — they're stated in the prompt. Typically 7 of 11 are already covered, which is why this path is short.

What remains open is usually: the thing that's broken, and whatever the original author never considered.

## A2 — Ask the highest-yield question first

> *What is it doing now that you don't want?*

For a revision this beats every forward-looking question combined. Then:

> *Do you have an output it produced that was wrong — and one that was right?*

A single bad output localizes the fault faster than any amount of description. Ask for both; the rejected one is often sharper than the accepted one.

If the user already told you the symptom, don't re-ask it. Go to A3.

## A3 — Localize

Name the **specific line or specific absence** causing the symptom. Do not rewrite the whole prompt to fix one line.

| Symptom | Look first at |
|---|---|
| Bullets everything | a format instruction saying "concise" / "key points", or no format instruction at all |
| Too long | no length bound, or a bound stated as an adjective |
| Generic, could-be-anyone | missing domain context (dimension 7) |
| Ignores a constraint | constraint buried mid-paragraph instead of listed — usually a **placement** bug, not a phrasing one |
| Inconsistent run to run | format described instead of shown; no literal schema |
| Over-imitates one case | a single few-shot example |
| Refuses or hedges | an over-broad prohibition colliding with the task |

## A4 — Prefer the minimal edit

A rewrite loses the user's hard-won phrasing and resets whatever tuning they'd already done into it. Rewrite only when the **structure itself** is the fault — and when you do, say why.

## A5 — Deliver a diff, not a replacement

Show what changed and **which symptom each change targets.** One line per change. Then go to `references/authoring.md` for Steps 6–7 (test it, ledger it) — testing matters more here than anywhere, because you have a known symptom to check against.

---

# Path B — Autonomous (nobody to ask)

You cannot interview. **The ledger does all the work the questions would have done.**

## B1 — Classify normally

Run the Step 0 classification against `references/dimensions.md`. Nothing changes except that the "ask" bucket has nowhere to go.

## B2 — Choose for widest recovery

For each open-and-consequential dimension, take the option that is **cheapest to change later, or fails most visibly if wrong.** Concretely:

- **Verbose beats terse** — cutting is easier than discovering what's missing.
- **Explicit beats implicit** — a wrong stated rule gets spotted; a wrong assumed one doesn't.
- **General beats narrow** — over-scoping wastes tokens, under-scoping loses information the user can't recover.
- **A stated assumption beats a silent default**, always.

## B3 — Lead with the forks

Write the prompt, then put a `## Forks I resolved for you` block **above** the normal ledger, naming the top 3 decisions and the alternative you rejected:

```
## Forks I resolved for you
- Audience → internal engineers (not customers). Rejected: customer-facing, which
  would have cut the internal jargon and roughly doubled the explanation.
- Output → table. Rejected: prose, better for nuance, worse for scanning.
- Scope → excluded environment setup. Rejected: including it, ~2x length.
```

A returning human must be able to flip any of these in one read. That is the whole point of the block.

## B4 — Still no fabrication

`[FILL IN]` applies harder here, not less. Nobody is watching, so a plausible invented specific has no chance of being caught. Do not invent examples, names, numbers, or domain facts.

Then go to `references/authoring.md`.
