# Audit rubric

Run after `check.py` passes and after you have **actually opened the screenshots and looked at them**. Reading your own source is not seeing the page.

Grade each line pass/fail with one sentence of evidence. Any fail gets fixed in the mandatory revision pass.

## A. Mechanical (check.py covers most of this)

1. No banned typeface, no banned exact color, no gradient text, no backdrop-blur, no emoji-as-icon.
2. Every color, size, and space value in the output appears in the token block.
3. Type dynamic range ≥ 5×.
4. At least three distinct section padding values.
5. Radius is either uniformly 0 or derived by role — not one value applied to everything.
6. At most one accent hue, appearing ≤3 times per viewport.

## B. Visual — from the screenshots, not the code

7. **Hero is the strongest thing on the page.** If any section below it has more visual weight, the hero has failed. Common cause: hero is text-only while section two has a large image.
8. **The eye has a path.** Look at the full-page shot for two seconds. Name what you saw first, second, third. If the answer is "everything at once," hierarchy is missing.
9. **Density varies.** Scan the full-page shot top to bottom — do sections look interchangeable in height and rhythm? That's the loudest generic tell and it survives every code-level check.
10. **The 5× range is felt, not just measured.** A single giant orphan number satisfying the arithmetic doesn't count.
11. **The accent looks intentional.** If it reads as an accident or as leftover default styling, it's placed wrong or used too often.
12. **Nothing collides or nearly collides.** Check the 390px shot especially — descenders into rules, text touching container edges, buttons wrapping mid-word.
13. **Mobile is designed, not stacked.** If 390px is just the desktop layout in one column with everything the same size, it hasn't been designed.

## C. Fit

14. **The premise is visible.** Could someone infer the ATTITUDE line from the screenshot alone? If not, the premise didn't reach the pixels.
15. **Swap test.** Would this design work equally well for a competitor in an adjacent industry? If yes, it's fitted to a category, not to this subject.
16. **Copy is specific.** No banned marketing phrasing; every headline says something falsifiable.
17. **Content shaped the layout.** The number of items in each group is the true number, not the number the grid wanted.

## D. Floor

18. Responsive to 360px without horizontal scroll.
19. Visible keyboard focus states, not `outline: none`.
20. `prefers-reduced-motion` respected.
21. Body text contrast ≥ 4.5:1.

## Scoring

- Any fail in **A** or **D**: fix before showing the user, no discussion.
- Any fail in **B**: fix, and re-screenshot to confirm — these don't verify from source.
- Any fail in **C**: this is usually a Phase 1 problem, not a CSS problem. Revisit the premise rather than patching the styling.

## Reporting

Tell the user what you changed in the revision pass and why, in two or three lines. Don't paste the rubric.
