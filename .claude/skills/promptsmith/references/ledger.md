# Step 7 — Close the loop honestly

The last step of every path. This is where the skill's core promise is either kept or quietly broken.


### Placeholder manifest

Anything the user must supply goes in as `[FILL IN: what's needed and why]`. **Never invent a plausible-looking stand-in** — a fake example silently becomes the spec, and gaps get noticed while fakes don't.

Then, **above** the prompt block, state the count: *"3 placeholders to fill before this will run: X, Y, Z."* A prompt with an unfilled `[FILL IN]` is a broken prompt, and this skill does not ship broken artifacts quietly.

### Promote the riskiest assumption

The ledger sits *below* the prompt, and users copy the prompt and go. An assumption disclosed underneath the thing they already pasted is disclosed too late to stop the wrong output.

So pick the **one** `[mine]` decision most likely to be wrong — the one where, if you've misread them, they get output they didn't want — and put it **above the block**, one line, next to the placeholder count:

> *Before you use this: I made it preserve the input's time when present, rather than always returning date-only. If that's backwards, say so — it's a one-line change.*

Exactly one. This is a safety net for what triage misclassified, not a second ledger; promoting three lines promotes nothing. Pick by consequence, not by how uncertain you felt — the decisions that feel most obvious while you're making them are the ones that turn out to be yours alone.

### Assumptions ledger

List every decision the user didn't hand you — including safely-inferable ones, skipped questions, and any conflict you resolved.

**Build it mechanically, not by introspection.** Scan the finished prompt for every **proper noun, number, named audience, format, tone word, and constraint**. For each, point at where it came from. Everything that isn't the user's own words is a ledger line.

This is a lookup, not a memory exercise. The whole reason the ledger exists is that the model which smoothly fills a gap is the model that won't recall filling it — so asking "what did I invent?" queries exactly the faculty that has the blind spot. Asking "the word *Python* is in this prompt; where did it come from?" does not.

### Provenance tags — required on every line

Three sources, and they are **not** interchangeable:

| Tag | Means | Trust |
|---|---|---|
| `[stated]` | the user's own words, from the brief or a volunteered answer | high — don't re-litigate |
| `[chose 2a]` | the user picked this **from options you wrote** | medium — they chose, but *you* built the menu |
| `[mine]` | you decided it | low — the user has never seen this decision before |

**Never write "you said X" for a `[chose]` item.** The user did not say it; you offered it and they picked it. Cite the question — `[chose 2a]` — so the choice stays traceable to the menu it came from. Collapsing a selection into "you said" is how an invention becomes indistinguishable from a requirement, and it is the single easiest way to corrupt this whole mechanism.

### The options you didn't offer

A menu is a decision. When you gave 2–4 options on a **consequential** dimension, you also silently eliminated everything you didn't list — and that elimination never felt like a choice, so nothing else in this skill will catch it.

For each consequential question you asked, add one line naming the plausible option you left out:

```
- Delivery medium: I offered email / in-app banner / changelog page, and not
  a docs update or a blog post [menu was mine] — say if I cut the right one.
```

If you can't think of an option you left out, you probably didn't scope the question — that's worth a second look, not a shrug.

```
## Assumptions I made
- Audience is internal engineers, not customers [mine] — inferred from "for the team"
- Length capped at ~800 words [mine] — you didn't say, and unbounded prompts drift long
- Blunt register [chose 2a] — you picked it off my list; I wrote the list, so if none of
  the three options was your actual register, say so
- Severity levels (blocker/nit) [mine] — you didn't ask for these; say the word and I'll cut them
- Reasoning hidden [mine] — Q4 went unanswered, this is my default, not yours
- Output shape: offered table / prose / bullets, not a diff or a checklist [menu was mine]
```

Every line must be something the user could **disagree with**. "I assumed you wanted good output" is filler; cut it.

**The tags are the deliverable, not decoration.** A user scanning this should be able to tell in one pass which lines are their own words coming back to them and which are yours wearing their voice.

---
