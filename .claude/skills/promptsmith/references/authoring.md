# Authoring and testing

Steps 5–7. Every path arrives here.

---

## Step 5 — Write the prompt

Start from the smallest structure that carries the spec, and add only what the task needs.

```
## Task          — the single clear thing to produce. One sentence if possible.
## Output format — structure, length, medium. Be specific; this is where vague prompts leak most.
## Constraints   — hard requirements and explicit exclusions.
```

Add, only when they earn it:

```
## Role / context — who the model is being. Skip for mechanical transforms.
## Inputs         — what the model is given, and where it comes from.
## Approach       — method or order of operations, only where it genuinely matters.
## Quality bar    — see below.
```

**Three sections is a normal prompt. Seven is a system prompt.** Padding to seven is the bloat anti-pattern with extra steps.

### Quality bar, honestly

A concrete example beats any adjective — but you may not invent one. Resolve in this order:

1. **User supplied an example** (or a rejected output) → use it. This section is now the strongest in the prompt.
2. **No example, but you have their words** → write a *contrast* built from them: *"good = names the specific tradeoff; bad = lists considerations without ranking them."*
3. **Neither** → `[FILL IN: an output you'd call good]`, and say why it matters.

Never an unsupported adjective. Never a fabricated sample.

### Preserve their words

Specific phrasing, examples, and constraints from the brief survive **verbatim** into the final prompt. Expanding is not paraphrasing.

### Format choice

XML tags (`<role>`, `<task>`, `<constraints>`) when the prompt targets an API, embeds long pasted documents, or is assembled programmatically. Markdown when someone pastes it into a chat box.

See `references/techniques.md` for the technique library and when each earns its place.

### Delivery

A copy-pasteable block, clearly bounded from your commentary. If it's **over ~40 lines**, or it's a reusable template, system prompt, or agent instruction set — **write it to a file and give the path.** Those live in files in every real workflow, and long blocks in a terminal are miserable to select.

---

## Step 6 — Test it

**Do not skip this because the prompt looks good. Looking good is the failure mode.**

Before delivering, run the prompt against one realistic input and read what comes back.

- **If you have tools** — actually run it. Use the user's real example if they gave one; otherwise construct a *representative* input. (Constructing a test **input** is fine. Fabricating an example **output** as spec is not — that's Step 5's rule and it still holds.)
- **If you can't run it** — written dry-run: walk the prompt as the target model would and name where it goes wrong. Which instruction is ambiguous on this input? Where does it default to something unstated?

Look for these specifically:

| Symptom | Usual cause |
|---|---|
| Longer than expected | no length bound |
| Wrong shape | format described instead of shown |
| Generic, could-be-anyone | missing domain context (dimension 7) |
| Ignored a constraint | constraint buried mid-paragraph instead of listed |
| Over-imitates the example | only one few-shot example given |
| Inconsistent across runs | no literal schema |

Fix what the test surfaced, then deliver.

### Say which kind of test you ran, and prove the strong one

Two claims are available and they are **not** interchangeable:

- **"I ran it."** Only sayable if you can **show the captured output** — paste it, or give the file path. A run with no artifact is not a run you may claim.
- **"Dry-run, not executed."** The honest default. Say it plainly whenever you could not execute, and describe what you walked through.

**If you find yourself writing a test narrative — "my first draft failed in three places, so I added these three constraints" — with no captured output to point at, that is a dry-run.** Label it as one. Writing the constraints first and narrating a discovery afterwards is the most natural thing in the world and it reads exactly like evidence, which is why the artifact is the line and not your confidence.

A dry-run is worth doing and worth reporting. Passing one off as an execution is not.

---

## Step 6.5 — Edit it

Two fast passes. Skipping this is why a careful prompt ends up twice as long as a good one while covering less.

Everything before this step was about getting the prompt *right*. This step is about making it *good*, and they are not the same work. A prompt that says the correct things at twice the necessary length is a worse prompt, because every wasted line competes for attention with the lines that matter.

### Cut pass — every line must earn its slot

Walk the prompt line by line and **name what each line changes about the output.** If you cannot name it, delete the line. Not "it adds context" — name the behavior that would differ without it.

The four things that reliably need cutting:

- **Rationale.** *"Preserve the input's precision, because normalizing invents data the user never supplied."* The model does not need persuading — it needs instructing. **The prompt instructs; the ledger explains.** Move the "because" clause to the ledger, where the person who can act on it will read it.
- **The same constraint twice.** Saying it in Role and again in Constraints doesn't double its weight, it halves the weight of everything nearby.
- **Over-definition.** *"the rate limit, which is the number of requests you are allowed to make in a given period"* — if the original brief said define terms *briefly*, a full sentence per term is a violation dressed as diligence.
- **Decorative role lines.** A persona on a format conversion is a costume. Cut it.

If the prompt got shorter and you cannot point to a behavior you lost, the cut was correct.

### Edge pass — then spend what you saved

Now name **the three inputs most likely to break this prompt.** Empty, malformed, ambiguous, adversarial, or simply weirder than the happy path you had in mind while writing.

Check each against the prompt. **An unhandled edge case is worth more than any line you just cut** — an incomplete rule fails silently on real data, whereas a verbose one merely wastes tokens.

Two-digit years, mixed date conventions, an empty list, a document in the wrong language, a diff with no code changes: these are the lines that make a prompt survive contact.

**Net effect should be a prompt that is shorter and covers more.** If it got longer, say which edge case bought the length.

---

## Step 7 — Close the loop honestly

Placeholder manifest, the promoted assumption, and the provenance-tagged ledger — all in `references/ledger.md`. Load it now; it is not optional, and it is where this skill's central guarantee actually lives.


## Worked example

**Brief:** *"write a prompt to help me review PRs"*

**Step 0:** No existing prompt, user present. Five survivors of the consequential test — priority focus, register, output shape, target language, severity handling. The artifact is agent instructions, so **N = 4**. Ranked; the fifth (severity) went to the ledger, not to a question.

**Restate:** You want a prompt that turns a model into a code reviewer for your PRs — catching problems before a human reviewer sees them.

**Asked (4):** priority focus · bluntness · output shape · reasoning visibility.
**Answered:** `1a` correctness only · `2a` direct · `3c` summary then line comments · Q4 skipped.

**Step 6 — ran it** against a 40-line diff carrying an off-by-one and a naming inconsistency; output captured at `/tmp/pr-review-test1.txt`. First draft flagged both *and* three style nits, despite `1a`. Cause: "review this code" in the Task line reintroduced the general scope that Constraints excluded. Retightened Task to *"identify correctness defects"*; second run (`test2.txt`) flagged only the off-by-one and a boundary condition.

**Step 6.5 — edited.**

*Cut pass* — removed three lines. The Role paragraph explained *why* correctness beats style ("because style nits bury real defects in a long review"): true, and the model doesn't need convincing, so it moved to the ledger. "Be thorough" changed nothing that "identify correctness defects" didn't already say. And a second no-style reminder in Constraints was the same rule twice.

*Edge pass* — named three breaking inputs: a diff with **no code changes** (docs only), a diff **too large to read whole**, and one where **the bug is in unchanged code the diff exposes**. The third was unhandled and is the one that matters — a reviewer that only looks at `+` lines misses the caller it just broke. Added one line for it.

**Net: 6 lines shorter, one real gap closed.**

**Delivered** with `[FILL IN: your language and framework]` — 1 placeholder, flagged above the block.

```
## Assumptions I made
- Severity levels: blocker / should-fix / nit [mine] — you didn't ask. They were the
  cheapest way to make "direct" survive contact with a long diff. Easy to cut.
- Blunt register [chose 2a] — picked off my list. I offered direct / collegial /
  socratic and not "terse, findings only" [menu was mine], which may be closer.
- Reasoning hidden [mine] — Q4 went unanswered; this is my default, not your choice.
- One PR at a time, not a batch [mine] — changes the output format if wrong.
- Correctness over style [chose 1a] — and the reason it's worth it: style nits bury
  real defects in a long review. That rationale lives here, not in the prompt.
```
