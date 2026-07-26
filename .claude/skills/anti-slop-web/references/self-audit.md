# Self-audit

Work this list **out loud, line by line, before you deliver**. One sentence of evidence per line: a number from `measured.json`, a value from your token block, or something you saw in the PNG. "Looks fine" is not evidence. A line you skip is a line you failed.

`check.py` covers section A. Sections B–E it cannot see, which is the entire reason this file exists.

Format each as: `n. PASS/FAIL — evidence`.

---

## A. Mechanical — the script checks these, confirm it ran

1. `check.py` exits 0 on the final file, not an earlier draft.
2. **Retrofit only, and it outranks everything:** `content.py <original> <rebuilt>` exits 0. Every price, quantity, standard, list item and quoted block survived. Then read the tier-by-tier mapping yourself — the script proves nothing was *deleted*, not that facts stayed attached to the right thing.
3. Every colour, size and space value in the file appears in your token block. Sweep for strays; retrofits characteristically leave forty behind.
4. **Every fact on the page traces to the brief.** Walk the page and name the source of each number, claim, quote, credential and comparison. Anything you supplied yourself is invented — including data behind a chart and anything said about a competitor. Remove it or mark it visibly as a placeholder at the point the claim is made. This outranks every design consideration below it; see `banned-defaults.md` → *Invented facts*.

## B. Measured — cross-check against `measured.json`

4. **Type range.** Measured range matches what you intended. If it's under 5×, say why that's right for this page rather than quietly moving on.
5. **Hero is strongest.** `biggestTypeBlock` is block 0. If it isn't, either fix the hero or justify it — an editorial page may legitimately lead quietly.
6. **Density varies.** Block heights are not all within 25% of each other. Uniform rhythm is the loudest generic tell and it survives every token fix.
7. **No horizontal overflow at 390px.** `horizontalOverflow` is empty.
8. **Body contrast ≥ 4.5:1**, or measured as unmeasurable (text on a gradient/image) and checked by eye.
9. **Focus is visible.** `focusRemovedOn` is 0.

## C. Seen — only answerable from the PNGs

10. **Name what you saw first, second, third** on the desktop full-page shot. If the honest answer is "everything at once", there is no hierarchy.
11. **The 5× range is felt, not just measured.** A single giant orphan number satisfying the arithmetic does not count.
12. **The accent looks deliberate.** It reads as a decision, not as leftover default styling or an accident.
13. **Nothing collides or nearly collides.** Check 390px especially: descenders into rules, text touching container edges, buttons wrapping mid-word.
14. **Mobile is designed, not stacked.** If 390px is the desktop layout in one column at the same sizes, it hasn't been designed.
15. **The grid break earns its place.** Exactly one element escapes the container, and it looks intentional rather than broken.

## D. Fit — the part no checker will ever reach

Evidence for this section should come from the **independent reviewer** (Phase 4, step three) wherever possible. Your own answer here is worth less than theirs, because you know what you were going for and will see it whether or not it landed.

16. **The premise is visible.** Could the reviewer infer your ATTITUDE line from the screenshots alone? Quote what they said. If they couldn't, it didn't reach the pixels.
17. **Swap test.** Would this design work just as well for a competitor in an adjacent industry? If yes, it's fitted to a category, not to this subject. This is a Phase 1 problem, not a CSS problem — go back and re-argue the attitude.
17a. **The reviewer didn't call it templated.** If they did, take it at face value — they are the only party here without a stake in the answer.
18. **The user's answer from Phase 0 is honoured.** They named a direction and a feeling. Point at where each one landed. If you overrode either, say so and why.
19. **Copy is specific.** Every headline says something falsifiable. No banned phrasing. The number of items in each group is the true number, not the number the grid wanted.
20. **You did not build weird instead of good.** Distinctive but unrelated to what the product is, is boutique slop — same failure, better wardrobe.

## E. Floor

21. Responsive to 360px without horizontal scroll.
22. `prefers-reduced-motion` respected if anything moves.
23. Real alt text on meaningful images, empty `alt=""` on decorative ones.
24. Heading levels descend without skipping.

---

## Scoring

- **A2 or A4 fails** → stop. Restore missing content, or remove invented content, before anything else. A redesign that drops the product's facts — or adds facts the product never claimed — is the wrong deliverable, not a draft.
- **Any other A, or any E** → fix before showing the user. No discussion.
- **Any B or C** → fix, then re-shoot to confirm. These do not verify from source.
- **Any D** → usually Phase 1. Revisit the premise rather than patching CSS.

## Reporting

Tell the user: the premise, what the revision pass changed and why, and anything you deliberately left alone. Two or three lines. **Do not paste this list back at them** — they asked for a page, not a checklist. If something is still weak and you chose to ship it, say which and why.
