# Technique library

Techniques for constructing the prompt in Step 5. Each has a cost — length, rigidity, or wasted attention — so each must earn its place. Reach for these based on what the task needs, not to demonstrate thoroughness.

---

## Role assignment

Opening with who the model is being. Works because it shifts what the model attends to, not just how it phrases things.

**Use when** the task involves judgment or a specific stance. **Skip when** the task is mechanical — a role on a format-conversion prompt is decoration.

Specific beats grand. "A staff engineer reviewing a junior's first PR" outperforms "a world-class expert programmer," because the first implies a posture and the second implies nothing.

## Few-shot examples

One to three input/output pairs showing the target.

The highest-leverage technique available when the user has real examples, and among the most dangerous when they don't — a fabricated example silently becomes the spec. If the user can't supply one, use `[FILL IN: an example of output you'd consider good]` rather than inventing.

Two examples beat one (one gets over-imitated). Include an edge case if the task has messy inputs. Wrap them in `<example>` tags so the model can tell demonstration from instruction.

## Output schemas

Specifying exact structure — field names, section headers, a JSON shape.

**Use when** output feeds a downstream process, or consistency across runs matters. **Skip when** the user wants exploration; a rigid schema will flatten it.

State the schema literally rather than describing it. Showing the shape works better than explaining it.

## Reasoning scaffolds

Asking the model to work through something before answering — "identify the constraints, then evaluate each option against them, then recommend."

**Use when** the task has real analytical depth, or a first-instinct answer is likely wrong. **Skip for** straightforward generation, where it adds length without accuracy.

Naming the *specific* steps of the task beats a generic "think step by step."

On models with extended thinking, don't hand-roll a scaffold the thinking budget already covers — you'll get the reasoning twice. Scaffold the parts that are task-specific (*"check the boundary conditions first"*), not the generic ones.

## Negative constraints

Explicit prohibitions. Punch above their weight because they encode hard-won knowledge about what goes wrong.

Be specific about the behavior, not the vibe. "Don't hedge every recommendation with caveats" is actionable; "don't be annoying" isn't.

Pair with a positive alternative where you can — "instead of X, do Y" — since a prohibition alone leaves the model guessing at the replacement.

## Delimiters and structure

XML tags or clear markers separating instructions from content.

**Essential when** the prompt embeds documents, user-supplied text, or anything long. Without boundaries, pasted content gets read as instructions — which is a correctness problem and a security one.

`<document>...</document>` is the standard wrapper for anything pasted in.

## Ordering for long inputs

**Put long documents near the top, instructions after them.** On long-context inputs this is one of the largest single wins available and it costs nothing — a prompt that leads with 30 pages and closes with the task outperforms the reverse, because the final instruction sits closest to where generation begins.

Corollary: the constraint you care about most goes last, not buried mid-paragraph. "It ignored my constraint" is usually a placement bug, not a phrasing one.

## System vs. user message split

For API prompts: **role, persona, standing rules, and output contract go in the system prompt. The specific task and its inputs go in the user turn.**

Getting this wrong is common and costly — persona in the user turn gets diluted by each subsequent message, and per-task detail in the system prompt makes the prompt un-reusable. If the prompt is destined for an API, say explicitly which half is which; the user will otherwise paste the whole thing into one field.

## Prefilling the response

For API prompts, seeding the start of the assistant turn (`{` for JSON, `<analysis>` for a known structure) to force format and skip preamble.

**Use when** you need parseable output or want to eliminate "Sure, here's...". **Not available** in chat interfaces, and incompatible with extended thinking — don't hand a chat user a prompt that depends on it.

## Stopping conditions and verification

For agentic prompts: when is the task done, and how does the model check its own work.

**Use when** the prompt drives multi-step tool work. This is the most commonly missing piece in agentic prompts and a frequent cause of models stopping early or grinding on past the point of usefulness.

Include what to do when blocked — ask, or proceed with a stated assumption.

## Variable slots

For reusable templates: `{{INPUT_DOCUMENT}}`, `{{TARGET_AUDIENCE}}`.

**Use when** the prompt runs repeatedly with different inputs. Mark them consistently and list them at the top so the user knows what to fill.

Keep the static part contiguous and first — it's what gets cached, and a variable spliced into the middle invalidates everything after it.

## Length calibration

Explicit bounds. Unbounded prompts drift long by default.

Anchor to something concrete where possible — "about as long as a standard commit message," "fits on one screen" — since word counts get approximated loosely anyway.

## Prompt chains

When the user needs several prompts in a pipeline, the interfaces matter more than the prompts.

**Stage N's output schema is stage N+1's input spec.** Write that contract once, literally, and paste it into both. Most chain failures are a stage emitting something slightly different from what the next one expects, and they're invisible until the last stage produces nonsense.

Also decide, per boundary: what happens when a stage returns nothing or fails? A chain with no error path silently propagates garbage.

---

## What to leave out

- **Politeness padding and flattery.** No measurable effect on output quality; consumes attention.
- **Threats, urgency, fake stakes.** "This is critical to my career" is folklore. Don't put it in prompts you hand someone.
- **Redundant restatement.** Saying the same constraint three ways doesn't triple its weight; it dilutes the surrounding instructions.
- **Technique for its own sake.** A prompt with a role, five-shot examples, a reasoning scaffold, and a JSON schema, for a task that needed two sentences, is a worse prompt than the two sentences.
