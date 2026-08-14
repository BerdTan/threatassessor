# Visuals

A diagram earns its place by showing a relationship the prose can't. Four diagrams restating the file tree are worse than one that shows how a request flows. Two to four per document is normal; more than five means some are decorative.

**Every diagram must use this project's real names** — the actual modules, services, routes, and functions found in the scan. A generic Client → API → Database picture is a failure regardless of how it renders.

---

## What renders where

| Visual | GitHub | Medium |
|---|---|---|
| Mermaid | Renders natively | **Does not render** — must be exported to an image, or dropped |
| Shields.io badges | Renders | Renders, but reads as clutter in an article |
| ASCII / box-drawing | Renders everywhere | Renders everywhere |
| Committed SVG/PNG under `docs/assets/` | Renders | Renders (upload on paste) |
| HTML `<img align>`, `<details>`, `<picture>` | Renders | **Stripped** |

Tell the user this plainly when asking Phase 3's visuals question. For Medium, recommend ASCII plus exported assets; never hand a Medium draft a Mermaid block and call it a diagram.

## The four that usually earn their place

1. **System architecture** — `flowchart TD`, components as they're named in the repo, edges labeled with what actually crosses them (`HTTP /api/jobs`, `pg wire`, `SQS`). Subgraphs for process or deployment boundaries.
2. **Request / command flow** — `sequenceDiagram`, one representative end-to-end path through real functions and files. Usually the most informative thing in the whole document.
3. **Data or state model** — `erDiagram` for schemas, `stateDiagram-v2` for lifecycles. Only when the project has one worth showing.
4. **Repo layout** — an ASCII tree, pruned to the ~15 directories that matter, each with a trailing one-line purpose. Never a raw `tree` dump.

Optional when the project justifies it: module dependency graph (only if it stays readable — above ~20 nodes it's noise), CI/deploy pipeline, before/after for a migration described in the changelog.

## Mermaid syntax traps

**These are `flowchart` rules.** They govern node labels and edge labels in `flowchart`/`graph` blocks. `sequenceDiagram` participant aliases, `erDiagram` entities, and `stateDiagram-v2` states have different quoting rules — do not carry these across. In any diagram type, if you cannot state a label safely without a parser, **simplify the label rather than guessing at quoting**, and note it in the chat report.

Within a flowchart, these are the ones that produce a red error box on GitHub:

- **Quote any label containing `()`, `[]`, `{}`, `:`, `,`, `/`, or `-`** — `A["fetchJobs(): Job[]"]`. This is the most common break.
- No raw `<br>` — use `<br/>`.
- Node IDs: letters, digits, underscore. Never a dot, dash, or space. Put the pretty name in the label.
- `end` is reserved — never a bare node ID or unquoted label.
- Edge labels go `A -->|"label"| B`, quoted by the same rule.
- Keep it under ~25 nodes. Above that, split into two diagrams by concern.

**Subgraph membership is positional, and this one renders without erroring.** A node joins a subgraph by first being *mentioned* inside its block — so writing `client --> router` above the `subgraph` that is supposed to contain `router` silently pulls `router` out of it. Declare every node inside its intended subgraph before drawing any edge that crosses the boundary.

**Verify every diagram in Phase 6.** A parser is usually unavailable; when it is, this is a manual read and Phase 6 says so. Check the trap list character by character, then check the *structure* — syntactically valid and structurally wrong is the failure that survives a parse.

## Badges

Only ones backed by something you read. A build badge requires a workflow file; a version badge requires a published registry entry in the manifest; a license badge requires a LICENSE file. A badge also requires everything its URL needs — the repo slug, the registry name. If the project carries no remote URL, ship no badge rather than a `[FILL IN]` inside an image link. Cap at five, one row, directly under the title. If nothing qualifies, ship no badge row.

## Exported image assets

When the user picks exported assets (usually for Medium): write `.svg` into `docs/assets/`, hand-authored, one file per diagram, `viewBox` set and no external font or script references. Link them **relative to the document you are writing, not to the repo root** — from `docs/medium-writeup.md` that is `![alt](assets/name.svg)`; from a root `README.md` it is `![alt](docs/assets/name.svg)`. Getting this wrong fails Phase 6's own link check. Give every image real alt text describing what it shows — it is the only version a screen reader gets.

## Typography and tone of the page

- One `#` title, `##` for sections, `###` sparingly. Deep nesting reads as a spec, not a README.
- Tables for anything with two or more attributes per row — env vars, CLI flags, endpoints. Prose for reasoning.
- Every fenced code block gets a language tag.
- Emoji: at most one per section heading, or none at all. Pick one policy for the document and hold it.
- No horizontal-rule confetti, no centered marketing block unless the user asked for a hero.
