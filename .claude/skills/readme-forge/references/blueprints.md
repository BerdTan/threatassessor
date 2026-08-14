# Document blueprints

Two targets, four shapes. The shape is chosen in Phase 3 — you recommend, the user picks.

A section that would be empty or `[FILL IN]`-only gets **cut, not stubbed**. A README with a hollow Roadmap heading reads worse than one without a Roadmap.

**Precedence, because these two rules collide:** cut-not-stubbed holds only while the *other* sections carry real content. In a near-empty repo — `scan.md` Step 4 — where nearly every section would be a placeholder, the skeleton rule wins instead: keep the sections, mark each unknown, and say what is missing. Cutting there leaves a title and nothing else, which tells the reader nothing about what the project lacks.

---

## The four shapes (GitHub)

Recommend by what the scan found; say which and why in the option description.

**1. Polished OSS product** — for a tool, library, or app someone installs.
Title + one-line tagline · badge row · one hero diagram or screenshot slot · **What it does** (3–5 sentences) · **Features** (table or tight bullets, each naming a real capability) · **Quick Start** (copy-pasteable, verified) · **Usage** (the 3 most common real invocations) · **Configuration** (env/flag table) · **Architecture** (diagram + 1 paragraph) · **Development** (test, lint, build) · **Contributing** · **License**.

**2. Architecture-first** — for infra, services, internal platforms, anything with ≥3 moving parts.
Title + what problem it solves · **System overview** (architecture diagram, then component table: component / responsibility / where it lives) · **How a request flows** (sequence diagram + numbered walkthrough) · **Data model** · **Design decisions** (only ones evidenced in the repo or instruction files) · **Running it locally** · **Deployment** · **Operations** (config, failure modes, logs) · **Repo layout**.

**3. Minimal and elegant** — for small, sharp, self-evident projects.
Title · one paragraph · one diagram · Install · Usage · Configuration table · License. Nothing else, and no badges. **Extras chosen in Phase 1 are honored — except one the repo carries no evidence for, which is cut like any other hollow section, and named in the chat report as cut.** If the surviving extras would push the document past six sections, say so during Phase 3 and let the user drop either the extras or the shape.

**4. Detected per project** — you classify (library / CLI / service / app / infra / skill-or-agent), pick one of the three above, and **state the classification and the pick at the top of your chat report**, not in the document.

**When two shapes genuinely both fit** — a small service, a documented library — decide by what the request emphasizes: someone who says "people keep getting the config wrong" wants shape 1, where Configuration is a top-level section, not shape 2, where it sits inside Operations. If the request emphasizes nothing, decide by **readable bytes first, module count second**: under 25 KB the simpler shape wins regardless of module count; above it, three or more modules wins the more detailed shape. A small project with five small modules is still a small project, and architecture-first would hand it *Data model*, *Deployment*, and *Operations* headings it cannot fill — which the cut-not-stubbed rule then deletes, leaving the simpler shape by demolition. Name the runner-up in the chat report so the user can overrule you cheaply.

Extras chosen in Phase 1 slot in at their natural position: Troubleshooting/FAQ after Usage, Roadmap before Contributing, Security after Configuration, Benchmarks after Features. When an extra duplicates a section the shape already carries — Quick Start against architecture-first's *Running it locally* — merge them under the shape's heading rather than shipping two near-identical sections.

## Medium adaptation

Same understanding, different document. A Medium piece is a **narrative about building the thing**, not a manual for running it.

- **Open with the problem**, in the user's domain terms — not "X is a tool that…".
- Structure: the problem → why the obvious approach falls short → how it's built (diagrams live here) → the interesting decision or two → what it looks like in use (short code blocks) → what's next → link to the repo.
- **Trim reference material.** Config tables, full flag lists, and contributing instructions belong in the README, not the article. One or two illustrative snippets, not exhaustive usage.
- Longer prose paragraphs; Medium punishes bullet-dense writing.
- No Mermaid (see `visuals.md`). No badge row. No HTML.
- Suggest a title and subtitle at the top of the file as `<!-- title -->` comments; Medium takes the first `#` as the title on import.
- Length: 1,200–2,000 words unless the user says otherwise.
- **Voice.** The piece publishes under the user's name, not yours. Make no first-person claims about intent, memory, or feeling — no *"I decided"*, no *"I haven't got to it yet"* — unless the repo already carries prose in that voice for you to follow. Attribute decisions to the project rather than to a person: *"the flag is unwired"*, not *"I never wired the flag"*. Say in the chat report that the byline and any first-person framing are theirs to set.

**Both targets** = two files from one scan, not one file with two modes.

## The changelog section (update runs)

Only the approved changes from Phase 4, and only ever in the document when `[first version]` framing does not apply.

- **GitHub** — a `## What's New` section directly under the intro, holding the current version's approved changes as human-level bullets, **at most 7 — a ceiling, not a quota.** One approved change is one bullet. Previous runs' entries move down into `<details><summary>Previous updates</summary>`, newest first, each dated. Never let it grow past two collapsed runs — older ones go to `CHANGELOG.md` if one exists.
- **Medium** — no changelog section. Instead, a short italic note under the title: *"Updated 12 Aug 2026 — now covers the JWT migration and the new worker pool."* Changes get folded into the narrative where they belong.

A change is a statement about the project, not about files: *"Auth moved from session cookies to JWT, so deployments no longer need sticky sessions."*

## First-version framing

When the user said this is v1: no changelog, no "recently added", no version history. Write it as the current state of the world, in present tense.

When they said the project already shipped but this is its first generated README: same — current state, no changelog. The changelog begins at the *next* run.

When they said this updates a README they didn't write: there is no baseline to diff against, so still no changelog. Mine the existing README for facts the code cannot supply — author, credits, acknowledgements, external links, stated intent — carry them forward, and list in the chat report what you dropped from it and why. The changelog begins at the next run.

## Style floor, whatever the shape

- Length is a **ceiling, never a floor**: 400 lines for shapes 1 and 2, 80 for shape 3. A small project that fills half of it is finished, not thin — never pad to reach a number. Over budget, cut the **least informative** section — never one carrying information no other section holds, and never buy the budget by dropping the part that makes the document worth reading. If every remaining section earns its place, **exceed the ceiling** and say in the chat report by how much and why.
- The first two sentences must let a stranger decide whether this project is for them.
- Every claim about behavior traces to code you read.
- Second person for instructions ("run", "set"), third for description. Never first person plural about the maintainers unless the repo already writes that way.
- No filler sections: no "Introduction" that repeats the tagline, no "Conclusion", no "Note: this project is under active development" unless the repo says so.
