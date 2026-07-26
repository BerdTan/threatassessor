# Staying honest

`check.py` is an enumerable rule set and you can read it. That makes it a target, and a target gets optimised for — not deliberately, just by the ordinary pull toward the cheapest thing that turns the output green. This file is the countermeasure, and it is steps rather than code because no rule can catch a rule being gamed.

The failure has a name in this skill already: **rule-satisfying instead of designed**. A page can pass every check and be dead.

---

## Before you build

**1. Do not read `check.py` to plan the design.** Read `banned-defaults.md` — the *reasons* — and build from the premise. The script exists to catch what you missed, not to specify what to make. A design derived from the checker inherits exactly the checker's blind spots, and there are always blind spots.

**2. Write the token block before the markup, and treat it as the spec.** Everything traceable to four decisions is the durable half of this skill. The block list is the gameable half — you can dodge every banned token and still ship a template. If a value in the finished page isn't derived from the token block, it's a stray, whether or not anything flagged it.

## While fixing failures

**3. Fix the cause, never the symptom.** For each failure, say what the rule is protecting before you touch anything. Then fix that.

| The lazy fix | What it's protecting | The real fix |
|---|---|---|
| swap `blue-600` for `blue-500` | one accent, argued from the subject | pick a colour from the subject's world |
| add a fourth padding value | rhythm varies with importance | size each section by what it's worth |
| bump `h1` until the range clears 5× | felt hierarchy | make the hero actually lead |
| rename a card class to break the grid check | item count should be real | build the layout the real count wants |
| add one `100vw` div | one deliberate escape | make something escape *because it should* |

**4. If a change only makes sense as "this will clear the check", stop.** That is the signal, and it is reliable. Either you don't understand the rule yet — go read why it exists — or the rule is wrong here, in which case say so out loud and move on. Both are fine. Silently satisfying it is not.

**5. A rule that's wrong for this page is allowed to be wrong.** Dense app UI has compressed type range. A docs page has uniform padding. A 12-item photo grid is content-driven. State the exception and why; `--app` exists for exactly this. Overriding a check with a reason is honest work. Overriding it by rewriting the value until it passes is not.

## After it's green

**6. Green means nothing was obviously wrong.** It does not mean the page is good, and the scripts say so on every PASS. The real verdict comes from the screenshots and the independent reviewer.

**7. Ask the question the checker can't.** *If I showed this to someone who didn't know what it was for, would they guess right?* No static rule reaches it. It's also the whole point.

**8. Answer before you check.** `shoot.py` prints questions, not findings, for a reason: an observation you formed after reading the answer is not an observation. Write yours first, then reconcile.

## When something slips through

**9. A page that passed and still looks generic is the most valuable thing you'll find.** It's a hole in the checks, and it will recur. Say so explicitly, describe what's generic about it in one line, and — if the user keeps a test suite for this skill — add that page as a fixture. The suite should be a record of every dodge found in the wild, not a fixed exam that gets easier each time it's taken.

**10. Say what you left unfixed.** "The hero is still weaker than section two and I ran out of room to fix it" is worth more than a clean report that quietly isn't true. The user can act on the first one.

---

## If you want to know whether this skill is actually working

Not a per-page step — the thing to do occasionally, because compliance scores can rise while quality doesn't:

1. Take a brief. Build it twice: once following this skill, once ignoring it entirely.
2. Screenshot both. Strip anything identifying which is which.
3. Have someone — a person, or a model with no part in either build — pick the better one and say why.
4. If the skill's version doesn't win, the checker score is irrelevant. Fix the skill, not the page.

That comparison is the only measure here that can't be gamed by choosing different tokens.
