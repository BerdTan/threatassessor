# Dimensions of an underdetermined prompt

A diagnostic checklist. Walk it, classify each dimension (stated / inferable / open-and-consequential / open-but-minor), and ask only about the third category.

**Inferable test:** if you stated the inference out loud, would the user say *"obviously"*? If they might say *"actually, no"* — it is open, not inferable.

**Consequential test — get this one right, it's where triage fails.**

A dimension is low-impact **only if every reasonable answer produces the same output.** Nothing else qualifies. Ask: *would two reasonable users answer this differently — and would their answers change what comes out?* If both are yes, it is consequential, and it counts toward your routing number.

Two ways this goes wrong, both of which look like sound reasoning:

- **Resolving it, then calling it closed.** You invent a policy — *"follow whatever precision the input carries"* — and classify the dimension as settled because your policy settles it. It isn't settled. You answered it yourself without noticing you were the one answering.
- **Treating cheap-to-fix as doesn't-matter.** *"Any answer here is a one-line edit"* is true and irrelevant. A one-line edit still produces wrong output on every run until someone makes it. Cost-to-change and impact-on-output are unrelated quantities.

A dimension that survives this test earns a question, however short the finished prompt will be.

---

## Start here — the four that punch above their weight

When you only have room for a few, these are almost always the most informative:

- ***What's it doing now that you don't want?*** — for any revision, better than every forward-looking question combined. Free, and it localizes the fault.
- ***What would make this output a failure?*** — surfaces constraints the user never thought to state. Reliably produces the single best line in the finished prompt.
- ***Who reads this and what do they do next?*** — collapses audience, tone, format, and purpose into one answer.
- ***Is there an existing output you'd point at and say "like this" — or "not like this"?*** — one artifact beats a paragraph of description. Ask for both; the rejected one is often sharper.

If you're on the Light path with two questions, take two of these.

---

The rest, ordered roughly by how often the answer changes the output.

## 1. Goal and success criteria

What is this output *for*, downstream? A summary for a decision meeting and a summary for an archive are different documents.

Ask when: the brief names an artifact but not a purpose. "Write me a competitor analysis" — to decide whether to enter a market, or to brief a new hire?

## 2. Audience

Who reads it, and what do they already know? Drives vocabulary, assumed background, length, and what needs defending versus asserting.

Ask when: unstated and the plausible audiences differ in expertise. "Explain our auth flow" — to a new backend engineer, or to a customer's security team?

## 3. Output format and length

The single biggest source of disappointment. Vague prompts produce essays when someone wanted a table.

Cover: medium (prose / table / list / code / structured data), length, and structural constraints.

Ask when: almost always worth confirming, but cheap to fold into another question. Often inferable from context — if it is, infer and log it.

## 4. Scope boundaries

What's deliberately *out*. Underspecified scope is why outputs sprawl.

Ask when: the topic has obvious adjacent territory. "Prompt for onboarding docs" — does that include environment setup? Team norms? Codebase tour?

Probe: *What should it explicitly not cover?*

## 5. Voice, tone, and persona

Not decoration. A persona changes what the model attends to — a "skeptical reviewer" surfaces different content than a "helpful assistant," not just different phrasing.

Ask when: the task involves judgment, critique, or writing meant for humans to read. Skip for mechanical transforms.

## 6. Hard constraints

Must-haves, must-nots, formats to match, things to never say, compliance requirements, house style.

Ask when: the domain has obvious landmines, or the user is producing something in a regulated or brand-governed context.

## 7. Context the model won't have

Domain facts, internal jargon, prior decisions, file contents, links. The most common cause of a well-structured prompt producing generic output.

Ask when: the brief references anything specific to the user's world. Don't ask them to explain it in the abstract — ask what the model needs to be *given*.

## 8. Examples and quality bar

One concrete example of good output outperforms three paragraphs describing one.

Ask when: the user has existing outputs they liked or disliked. If they don't, **do not manufacture examples** — leave `[FILL IN]` or write a contrast in the user's own words.

## 9. Failure modes

What has gone wrong before. Especially valuable when the user is here because an existing prompt underperformed — this is the entry point for the whole Revision path.

## 10. Execution environment

Where the prompt runs, because it changes what's possible:

- **Chat, one-shot** — self-contained; no follow-up assumed.
- **Chat, iterative** — can defer detail to conversation.
- **Agentic (Claude Code, Cowork)** — tools, files, multi-step work; needs stopping conditions and verification steps.
- **API / programmatic** — deterministic structure, parseable output, XML tags, no conversational framing.
- **System prompt / reusable template** — must generalize across many inputs; variable slots instead of specifics.

Ask when: not obvious. Often inferable — if the user is in Claude Code, they're probably writing an agentic prompt.

## 11. Target model and budget

Which model runs this, and does cost or latency bind?

- **Frontier (Opus/Sonnet class)** — needs less scaffolding. Over-structuring actively hurts; it follows nuance and a rigid schema flattens it.
- **Small/fast (Haiku class)** — needs explicit structure, literal schemas, and few-shot examples. Implicit instructions get dropped.
- **Non-Claude** — XML delimiters are a Claude-tuned convention; other models may prefer markdown or JSON-mode. Don't port blindly.
- **High-volume / cost-bound** — every unnecessary line is paid for on every call. Trim harder; consider whether the static portion can be cached.

Ask when: the prompt is going into production, is called at volume, or the user mentioned a specific model. Skip for one-off chat prompts.

## 12. Reasoning visibility

Should the model show its work, or just deliver? Affects length substantially and is easy to get wrong in both directions.

Ask when: the task involves analysis, judgment, or debugging. Skip for generation tasks.

## 13. Behavior on bad input

What should the model do when the input is empty, malformed, out of scope, or contradicts the instructions? Unhandled, this is where production prompts fail first — the model improvises, confidently.

Cover: refuse, ask, proceed with a stated assumption, or emit a defined error shape.

Ask when: the prompt is a reusable template, runs unattended, or processes input the user doesn't control. Skip for one-off chat prompts where the user is watching.
