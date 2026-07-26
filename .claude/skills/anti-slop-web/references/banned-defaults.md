# Banned defaults

Each item below is banned because it is the *modal* choice, not because it is bad. Blocking the mode forces a second choice, and the second choice is at least a choice. If the user's brief explicitly asks for one of these, the brief wins — user constraints are not slop.

## Typefaces

**Banned:** Inter, Roboto, Open Sans, Lato, Montserrat, Poppins, Nunito, Raleway, Source Sans Pro, and `font-sans` left at the Tailwind default.

These aren't bad faces. Inter in particular is excellent and that's the problem — it is the single strongest visual tell of AI-generated UI.

**Reach for instead** (all Google Fonts, all free):

| Role | Options |
|---|---|
| Grotesk / neutral-with-character | Archivo, Libre Franklin, Chivo, Public Sans, Hanken Grotesk |
| Geometric with an edge | Space Grotesk, Sora, Outfit, Syne |
| Serif display | Instrument Serif, Fraunces, Newsreader, Bodoni Moda, Playfair Display SC |
| Serif body | Source Serif 4, Spectral, Lora, Crimson Pro |
| Mono | JetBrains Mono, IBM Plex Mono, Space Mono, DM Mono |
| Odd / high-personality | Bricolage Grotesque, Unbounded, Instrument Sans, Gabarito |

Pair a characterful display face with a quieter body face. Two families is usually right; three needs a reason.

## Color

**Banned exact values:** `#3B82F6`, `#2563EB`, `#6366F1`, `#4F46E5`, `#8B5CF6` (Tailwind blue/indigo/violet 500–600), `#D97757` and near-neighbours, `#F4F1EA` cream paired with a serif.

**Banned patterns:**
- Blue-as-default. If the accent is blue, it must be argued from the subject, and it should not be Tailwind's blue.
- Purple-to-blue gradients, anywhere.
- Gradient text on the hero headline (`background-clip: text` + `linear-gradient`).
- Pure-grey neutrals (`#888`, `#666`, `#333`). Tint neutrals toward the accent hue.
- More than one accent color.

**Reach for instead:** one accent chosen from the subject's own world — the color of the material, the industry's signal color, the thing on the shelf. Then build neutrals by desaturating and darkening that hue rather than importing a grey ramp.

## Surfaces and shape

**Banned:**
- `rounded-lg` (or any single radius) applied uniformly to every card, button, input, and image.
- `shadow-sm` / `shadow-md` cards floating on a light-grey background. The default card is the default page.
- Glassmorphism: `backdrop-filter: blur()` over a gradient.
- Neumorphism, in any form.
- Gradient hero background with a soft radial glow behind the headline.
- Border AND shadow AND radius on the same element. Pick one.

**Reach for instead:** commit to a shape language. Either everything is sharp (radius 0), or radius is *derived* by role (pills for controls, 2px for surfaces, 0 for images), or the separation is done entirely with rules and color and there are no cards at all. Cards are a default; sections divided by hairlines, background shifts, or nothing at all are choices.

## Layout

**Banned:**
- The three-up icon feature grid. Icon in a rounded square, bold title, two lines of grey text, ×3.
- Identical vertical padding on every section (`py-20`, `py-24` throughout).
- Centered-everything: centered hero, centered eyebrow, centered section headers, centered CTA, all the way down.
- Alternating image-left / image-right feature rows.
- Logo cloud labeled "Trusted by" immediately under the hero.
- Stat strip of three big numbers with small grey labels under the hero.
- A hero that is: eyebrow pill, 3-line headline, one-line subhead, two buttons, gradient blob.

**Reach for instead:** let the content shape the layout. Asymmetric splits (62/38 beats 50/50), a single column that is genuinely single-column, editorial grids where different sections use different column counts, sidebars, overlaps, sections that are one enormous element.

## Iconography and detail

**Banned:**
- Emoji used as interface icons (🚀 ⚡ 🎯 ✨ 🔒 in feature cards).
- Sparkle/star icons to denote "AI".
- Icon inside a tinted rounded square, repeated.
- Lucide/Heroicons default set used decoratively rather than functionally.

**Reach for instead:** numbers, letters, rules, typographic marks, or no icons at all. If icons are functional, use them functionally and don't decorate with them.

## Motion

**Banned:**
- Fade-up-on-scroll applied uniformly to every section.
- Floating/bobbing decorative blobs.
- Typewriter effect on the hero headline.
- Counting-up numbers.

**Reach for instead:** one orchestrated moment — a page-load sequence, one scroll-driven transformation, one hover behaviour that reveals real information. Scattered effects read as generated; a single deliberate moment reads as designed. Respect `prefers-reduced-motion`.

## Invented facts

Everything else in this file pushes toward specificity — a real number, the true sentence, the signature element the page is remembered by. **That pressure has a failure mode: when you don't have the real number, specificity turns into invention.** It is the most damaging thing this skill can cause, because the result passes every check, looks like the best work on the page, and is a lie about someone's business.

**Never invent, at any size or prominence:**

- Measurements, benchmarks, tolerances, test results, sample data.
- Comparative claims about competitors or alternative products — *especially* quantified ones. "Off-the-shelf wheels run ±22%" is a factual assertion about other companies' goods. Inventing it is not a design decision.
- Testimonials, quotes, or named customers. Never attach a name and a photo to words nobody said.
- Counts and social proof: users, downloads, teams, years, "trusted by N".
- Certifications, standards, compliance claims, awards, press mentions.
- Prices, terms, lead times, guarantees, or anything a customer could hold them to.

**If the design needs data you weren't given**, in order of preference: ask for it; design something that doesn't need it; or use *visibly* placeholder values — obviously round, clearly labelled inline where the claim is made, not in a caption underneath. A disclaimer in 9px grey under a chart does not qualify a headline number set in 40px.

**The test:** if the page went live tomorrow, would every number on it survive a customer asking "where did you get that?" If you cannot name the source, it does not go on the page.

This outranks the design. A page that is one element weaker but entirely true is the correct trade every time — and say so in your report, so the user can supply the real figures and get the element back.

## Copy

**Banned phrasing:** "Empower your…", "Seamlessly…", "Take your X to the next level", "Built for the modern…", "Supercharge", "The future of X, today", "Effortlessly", any headline of the form *Verb your Noun with Adjective Noun*.

Generic copy makes a good layout look generic. Write the specific true sentence: what it does, for whom, and the one thing it does that the alternatives don't.
