# The interview (Light and Full paths)

Steps 1–4. You arrived here from Step 0 triage with a **ranked list of open-and-consequential dimensions** and a count. That count is your question budget. Do not exceed it, and do not pad up to it.

---

## Step 1 — Restate the vision

Play back what you understood in 2–3 lines: what the prompt is trying to get the model to produce, and for what purpose. On the Light path, one line.

Do this first because every question you're about to ask is built on this reading. If the reading is wrong the questions are wrong too, and the user sits through a whole round before finding out.

Short and concrete. Invite correction: *"Correct me if I've read this wrong."*

## Step 2 — Rank

You classified in Step 0. Now order the open-and-consequential dimensions by **how much the answer would change the output**, and truncate to the budget. The four in the "punch above their weight" block at the top of `references/dimensions.md` are usually the right picks when the budget is small.

Everything that doesn't make the cut is a ledger line, not a forgotten thing.

## Step 3 — Ask, once

One batched round. **Ceiling of 6; no floor.**

**Use `AskUserQuestion` when it's available** — it renders options natively and costs the user a click instead of typing. It caps at 4 questions × 4 options, which is the right budget anyway; if you have a fifth question you have not ranked hard enough. Put the recommended option first and mark it `(Recommended)`. Fall back to numbered text only when the tool isn't available.

Each question needs:

- **2–4 concrete options.** Not "what tone?" but actual candidate tones.
- **A one-line consequence per option, including the downside.** This is what makes the choice informed rather than cosmetic: *"Skeptical reviewer — pushes back and finds holes, but will be blunt about work you're attached to."*
- **A marked recommendation** where you have a genuine view. Recommending is fine; applying it unasked is not.
- **An open door.** The options are prompts for thinking, not a closed menu.

**Keep the whole round readable in one screen.** The binding cost is reading, not typing. Six questions each with four annotated options is a wall, and a wall gets skimmed and answered badly. Fewer, sharper questions beat more, thorough ones.

### You are writing the option space — track what you cut

Every menu you write eliminates everything you didn't list, and that elimination will not feel like a decision, so nothing downstream catches it. A user picking (a) from your three options has not told you (a) was right — only that it beat the other two you happened to think of.

Two obligations, both cheap:

- **Before sending, name the option you left out.** If you offered email / newsletter / portal, note that you didn't offer a docs update. Carry it to the ledger as a `[menu was mine]` line. If nothing comes to mind, the question is probably underscoped.
- **Make the open door real.** Not "let me know if none fit" as boilerplate, but pointed: *"If your actual answer isn't on any of these lists, that's the most useful thing you could tell me."* The whole point of an option menu is to make thinking cheap, and it only works if departing from it stays cheap too.

When you record the answers, a selection is `[chose 2a]` — never *"you said."* See the provenance rules in `references/authoring.md`.

In text fallback: number the questions, letter the options, and say they can answer in shorthand — `1b, 2a, 3 skip, 4 — you pick`.

Ask about **the substance of what they want, not prompt-engineering mechanics.** "Should I use chain-of-thought?" is your problem. "Do you want the model to show its reasoning or just give the answer?" is theirs.

## Step 4 — Reconcile, then follow up

**First, check the answers against each other.** Terse output plus show-all-reasoning is a contradiction. Blunt critique plus never-discourage is a contradiction. Short output plus include-two-examples is a contradiction.

When two answers conflict, **say so and ask which wins** — one line, not a new round. Silently picking one is the confident invention wearing a permission slip.

If an answer opened a genuinely new fork — something previously settled is now ambiguous — ask a short second round, 1–3 questions.

Do not use this to mop up questions you skipped in round one. **Two rounds is the ceiling.** After that, resolve what's left yourself and ledger it.

**Unanswered and skipped questions become ledger lines.** Every one, named as such: *"Q4 (reasoning visibility) went unanswered — I defaulted to hiding it."*

---

Then go to `references/authoring.md`.
