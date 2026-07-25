# House styles

Six fully specified directions. Pick one in Phase 1 and commit — a coherent pre-built system executed well beats a mediocre one derived from scratch mid-build.

Each entry lists a **fit rule** (what it's actually for), real tokens, a signature move, and the **adjacent cluster** — the nearby look that AI output already converges on, which this style must not drift into.

Deviate deliberately if the subject demands it, and say what you changed. Drifting without noticing is what produces mush.

---

## 1. Structural Swiss

**Fit:** tools, B2B, anything where precision is the product. Fails on anything that needs warmth.

- Display: Archivo, 700, tight tracking (-0.02em)
- Body: Archivo, 400
- Scale: base 16, ratio 1.5 → 11 / 16 / 24 / 36 / 54 / 81 / 122
- Spacing: unit 8 → 8 / 16 / 32 / 64 / 128 / 192
- Palette: `#0A0A0A` ink, `#FFFFFF` ground, `#E8E8E6` rule, accent `#E5341C` used ≤3× per viewport
- Radius: 0 everywhere. Shadows: none. Separation by 1px rules and whitespace.
- Grid: hard 12-column, visible alignment, generous outer margin

**Signature:** the grid is legible — elements align so obviously that the structure itself is the ornament.

**Adjacent cluster to avoid:** broadsheet pastiche — hairline rules everywhere plus dense newspaper columns plus a masthead. Swiss is about alignment and space, not about looking like a newspaper.

---

## 2. Terminal

**Fit:** developer tools, security, infrastructure, anything with a CLI. Fails on consumer and on anything aimed at non-technical buyers.

- Everything: JetBrains Mono or IBM Plex Mono, 400 and 700 only
- Scale: base 14, ratio 1.4 → 10 / 14 / 20 / 27 / 38 / 54 / 75
- Spacing: unit 12, strictly on a character-cell rhythm
- Palette: `#0D0D0F` ground, `#C8C8C2` text, `#5A5A55` dim, accent `#8FD14F` or `#FF6B35` — one, never both
- Radius: 0. Borders: 1px solid, used constantly. Shadows: none.
- Layout: fixed-width blocks, ASCII rules, bracketed labels `[01]`, tabular data

**Signature:** something genuinely functional in the type — live output, a real command, a status line that updates.

**Adjacent cluster to avoid:** near-black background with one acid-green accent and nothing else committed. If the mono, the cell rhythm, and the bracketed labels aren't all present, this is just a dark theme.

---

## 3. Editorial Ink

**Fit:** writing, research, media, long-form, anything where reading is the activity. Fails on dashboards and dense UI.

- Display: Instrument Serif or Newsreader, 400, large and unafraid
- Body: Source Serif 4, 400, measure capped at 68ch, leading 1.65
- Scale: base 19, ratio 1.618 → 12 / 19 / 31 / 50 / 80 / 130
- Spacing: unit 12 → 12 / 24 / 48 / 96 / 156
- Palette: `#FBFAF7` ground, `#141210` ink, `#6E6862` secondary, accent `#1F4D3A`
- Radius: 0 on images and rules; pills only on controls. Shadows: none.
- Layout: single column with a wide margin used for notes, figures, and pull quotes

**Signature:** the margin does real work — sidenotes, figure captions, running references.

**Adjacent cluster to avoid:** cream `#F4F1EA` + high-contrast serif + terracotta accent. That exact combination is the most common AI-design tell there is. The ground here is cooler, the accent is green, and the layout is asymmetric.

---

## 4. Dense Technical

**Fit:** dashboards, analytics, admin, anything where information density *is* the value. Fails on marketing pages.

- UI: IBM Plex Sans, 400/600. Numerals: IBM Plex Mono, tabular
- Scale: base 13, ratio 1.25 → 8 / 10 / 13 / 16 / 20 / 25 / 32 — plus one display size at 64 for the single headline number
- Spacing: unit 4 → 4 / 8 / 12 / 20 / 32 / 52
- Palette: `#F7F8F7` ground, `#1A1D1B` text, `#727872` dim, `#DCE0DC` rule, accent `#0B6E4F`, plus a muted diverging pair for data only
- Radius: 2px on surfaces, 0 on tables. Shadows: none — elevation by border and background step.
- Layout: real grid with rulers, tables with tabular figures, no cards

**Note:** this is the one style where the ≥5× type-range rule is met by the single display number against 8px labels. Keep everything else tight — that's the point.

**Adjacent cluster to avoid:** the shadow-card dashboard, where every metric floats in its own rounded white box on grey. Density means shared surfaces and shared rules.

---

## 5. Poster

**Fit:** launches, events, portfolios, single-message pages. Fails on anything with real navigation or more than ~4 sections.

- Display: Bricolage Grotesque or Syne, 800, set enormous — the type *is* the layout
- Body: Chivo or Public Sans, 400, deliberately small
- Scale: base 15, ratio 2.0 → 7.5 / 15 / 30 / 60 / 120 / 240
- Spacing: unit 16 → 16 / 32 / 64 / 128 / 256
- Palette: one saturated ground (`#12263A`, `#3D2B56`, or `#7A2E1E`), one near-white, one accent from the subject
- Radius: 0. Shadows: none. Overlap and bleed instead.
- Layout: type occupying 60%+ of the viewport, elements bleeding off-canvas, aggressive asymmetry

**Signature:** the headline set so large it is cropped by the viewport.

**Adjacent cluster to avoid:** big-gradient-hero-with-glow. Poster is flat, cropped, and typographic — no glow, no blur, no floating blobs.

---

## 6. Soft Utility

**Fit:** consumer apps, health, finance-for-humans, anything where approachability is the actual requirement. The hardest of the six to keep out of slop territory.

- Display: Gabarito or Outfit, 600
- Body: Hanken Grotesk, 400
- Scale: base 17, ratio 1.4 → 12 / 17 / 24 / 33 / 47 / 65 / 91
- Spacing: unit 10 → 10 / 20 / 34 / 56 / 92 / 148
- Palette: warm off-white ground `#FCF9F4`, text `#2B2622`, accent `#C2482B` **or** `#3B6E5F` — pick from the subject, never blue by default
- Radius: role-derived, not uniform — pills (999px) on controls, 4px on surfaces, 0 on images
- Shadows: at most one, large and soft, used on exactly one element

**Signature:** one oversized friendly element — an illustration, a huge input, a single large control — carrying the whole tone.

**Adjacent cluster to avoid:** rounded-lg-everything with `shadow-sm` cards and a blue accent. The role-derived radius and the non-blue accent are what keep this style out of the default. If you drop either, you are building slop.

---

## Going custom

Legitimate when the subject has a strong visual world of its own — a material, a craft, an era, an instrument, a chart type, an artifact. Then derive tokens from that world rather than from a style list, and write down what you derived and from what.

Not legitimate as a way to avoid committing. If the custom direction can't be stated in one sentence that would be false of a competitor's site, go back and pick one of the six.
