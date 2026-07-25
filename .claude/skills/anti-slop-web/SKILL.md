---
name: anti-slop-web
description: Build web pages and UI that don't look AI-generated. Use whenever building or restyling a landing page, marketing site, portfolio, dashboard, app UI, or any HTML/React/Tailwind interface — and especially when the user says the result looks generic, templated, "like AI made it", "AI slop", soulless, or asks for something distinctive, opinionated, or with real personality. Enforces a commit-to-one-direction workflow, bans default tokens (Inter, blue-600, uniform rounded-lg, gradient hero, glass cards), derives all tokens from a small number of decisions, and closes the loop by screenshotting the built page and looking at it before delivering.
---

# Anti-Slop Web

## Why generic output happens

AI design output looks samey for one mechanical reason: at every decision point the model independently picks the highest-probability option. Inter. `blue-600`. `rounded-lg`. `shadow-sm`. Three-up feature grid. Identical `py-20` on every section. Each choice is individually defensible — which is exactly why it gets picked — but they were made independently, so nothing agrees with anything else.

Design personality is *correlation*. A human designer commits to one premise, and the type, spacing, color, layout, and copy all fall out of it. That shared origin is what reads as intentional. Forty uncorrelated safe choices read as a template, because statistically a template is precisely that.

So the job here is not "add creativity." It's: **reduce the number of independent decisions, ban the modal option on the ones that remain, and verify by looking.**

Work through the four phases in order. Don't skip to code.

---

## Phase 1 — Commit (before any code)

Write a **premise block**. It is short and it is binding — every later choice must be traceable to it.

```
SUBJECT:      what this actually is, who uses it, the page's one job
ATTITUDE:     one sentence, opinionated, arguable
DIRECTION:    house style name (or "custom" + why the house styles don't fit)
NON-NEGOTIABLES: three constraints this build will not violate
SIGNATURE:    the one element the page is remembered by
```

Two rules for the premise:

**Argue it from the subject, not from a mood board.** A payroll compliance tool and a natural wine shop should not arrive at the same attitude. If the attitude sentence would fit any other product in the brief's category, it isn't a premise yet — it's a vibe. Rewrite it.

**Commit to a direction rather than deriving one from scratch.** Read `references/house-styles.md` and pick one. Each entry ships real typefaces, a scale base and ratio, a spacing unit, a palette, and a radius/shadow policy. A fully specified system you commit to beats a mediocre one you invent mid-build. Deviate deliberately and say so; drifting is what produces mush.

If the brief already pins down a visual direction, the brief wins — including when it asks for something on the banned list. Constraints from the user are not slop.

---

## Phase 2 — Derive the tokens

The point is arithmetic, not taste. Four decisions should generate forty values.

**Type.** One base size, one ratio, one step count. Everything else is computed.
`base 16px, ratio 1.333, steps -1..6` → 12 / 16 / 21 / 28 / 38 / 50 / 67 / 89.
Larger ratios (1.5, 1.618) give more drama and need more discipline in the quiet areas. Set the scale as CSS custom properties and use only those values.

**Spacing.** One unit, geometric or fibonacci-ish. `8 → 8/16/24/40/64/104/168`. No arbitrary in-between values.

**Color.** Pick a background posture (light / dark / tinted) and exactly one accent. The accent may appear at most three times on a viewport. Neutrals are tinted toward the accent's hue rather than pure grey — pure `#888` is a tell.

**Weight and width.** Decide the two type weights you'll use and stick to them. Three or more weights usually means the hierarchy is being carried by weight instead of by size and space, which flattens everything.

Emit the token block as code before building the layout. If a value in the finished page isn't in the token block, it's a mistake.

---

## Phase 3 — Build under constraint

Read `references/banned-defaults.md` before writing markup. It's the highest-leverage part of this skill: blocking the modal option forces the second choice, and the second choice is at least a *choice*.

Four structural rules, all numeric so they're checkable:

1. **Dynamic range ≥ 5×.** Largest type on the page at least five times the smallest. Slop has a range of about 2.5× and reads flat.
2. **One breathing section.** At least one section that is ≥ 60% negative space. Uniform density is uniform boredom.
3. **Break the grid once.** Exactly one element that escapes the container — full-bleed, overlapping, offset, oversized. Once. Twice is noise.
4. **Vary section rhythm.** At least three distinct vertical padding values across sections. Identical padding everywhere is the single loudest generic tell.

On content: write the real copy, not lorem and not the marketing-voice placeholder ("Empower your workflow. Seamlessly."). Generic copy makes a good layout look generic. Let the number of features be the number of real features — if it's four, do not build a three-up grid.

On complexity: match execution to the direction. Minimal directions fail on imprecise spacing; maximalist directions fail on thin execution. Don't pick maximalist and then build three sections.

---

## Phase 4 — Look at it, then fix it

**This is the phase that actually separates this skill from a list of opinions.** Everything above is a proxy for a visual judgment made blind. Close the loop.

```bash
python scripts/check.py <path-to-html-or-dir>          # static audit, stdlib only
python scripts/shoot.py <url-or-file> --out .shots     # needs playwright
```

`check.py` catches the mechanical failures — banned tokens, insufficient type range, uniform padding, uniform radius, glass/gradient tells. Run it first; it's fast and it has no opinions to argue with.

`shoot.py` renders at 390 / 768 / 1440 plus full-page. **Then actually open the images with the view/read tool and look at them.** Reading the code you just wrote is not seeing the page. The failures that only appear visually are: unintended near-collisions, a hero that's weaker than the section below it, an accent that reads as a mistake, type that's technically 5× but doesn't feel it, and mobile reflow that stacks into an undifferentiated column.

Then grade against `references/audit-rubric.md` and revise. **One full revision pass is mandatory, not optional** — the first render is a draft. Say what you changed and why.

If playwright isn't installed: `pip install playwright && playwright install chromium`. If the environment genuinely can't render, say so plainly rather than pretending the page was verified — an unverified build is a guess with better priors.

---

## Failure modes of this skill

Worth knowing, because both are real:

**Weird instead of good.** Off-the-mode is not the same as fitted. If the premise is distinctive but unrelated to what the product is, you've traded generic slop for boutique slop. The fix is always Phase 1: argue the attitude from the subject.

**Rule-satisfying instead of designed.** A page can pass every numeric check and still be dead — 5× range achieved by one giant orphan number, negative space achieved by one empty div. The checks are a floor, not a target. This is why Phase 4 requires looking rather than just running the script.

---

## Reference files

- `references/banned-defaults.md` — the block list and what to reach for instead. Read before writing markup.
- `references/house-styles.md` — six fully specified directions with real tokens. Read during Phase 1.
- `references/audit-rubric.md` — the grading pass. Read during Phase 4.
- `scripts/check.py` — static token/range audit. Python stdlib, no install.
- `scripts/shoot.py` — multi-viewport screenshots via playwright.
