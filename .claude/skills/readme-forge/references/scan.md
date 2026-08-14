# Phase 2 — Scan the project

Goal: after this phase you can answer, without guessing — what does it do, who runs it, how does a request or command flow through it, what are the moving parts, how is it configured, how is it deployed, and what did the author tell future contributors.

Write everything you learn into `.readme-forge/scan-notes.md` **as you go**, and resume from it if the scan runs long. That project-local path is the default because a sandboxed or delegated run may have no session scratchpad it is allowed to reach; use the scratchpad only when writing into the project is not permitted.

**The first write into `.readme-forge/` carries the ignore with it.** Do the `.gitignore` step from `SKILL.md` Phase 6 now, at directory creation, rather than at the end — a run that stops at the scale gate, or that the user abandons mid-scan, otherwise leaves an untracked and un-ignored directory in the project, and Phase 6 never arrives to clean up after it. Phase 6 then only confirms. If you leave anything behind on an aborted run, say so in the chat report.

If the **codemap** skill is installed and an index already exists, read it first — it seeds the inventory and the import graph for free. Do not build one just for this.

---

## Step 1 — Inventory before reading

Build the file list first. Classify every path into three tiers, and count each.

**Tier A — always read in full, first, before anything else.** These define intent, and they are what a stranger and a model both need most.

- Every `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `.github/copilot-instructions.md`, at every depth
- `README*`, `CONTRIBUTING*`, `ARCHITECTURE*`, `docs/**` index pages, `CHANGELOG*`, `LICENSE*`
- Manifests: `package.json`, `pyproject.toml`, `requirements*.txt`, `go.mod`, `Cargo.toml`, `pom.xml`, `*.csproj`, `Gemfile`, `composer.json`
- `Dockerfile*`, `docker-compose*`, `.github/workflows/*`, `Makefile`, `justfile`, `Procfile`, IaC files
- `.env.example` / `.env.sample` (**names only — never values, and never read `.env` itself for content**)
- Declared entrypoints: whatever `main`/`bin`/`scripts`/`CMD`/`ENTRYPOINT` actually point at

**Tier B — read in full.** All first-party source, tests, and docs not in Tier A.

**Tier C — never read; count and name only.** Apply this filter *before* tiering anything else, since these paths sit anywhere in the tree:

- **Secret-bearing, never opened for content at all:** `.env`, `.env.*` (except `.env.example` / `.env.sample`), `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `credentials*`, `secrets*`, `*.tfstate*`, `*service-account*.json`, `.npmrc`, `.netrc`, `.aws/`, `.ssh/`
- **Bulk and generated:** `.git`, `node_modules`, `vendor`, `.venv`, `__pycache__`, `dist`, `build`, `out`, `target`, `.next`, lockfiles, `*.min.*`, generated clients, binaries, media, anything over ~1 MB, anything gitignored
- **Your own working directory:** `.readme-forge/`. Never counts toward the measurement — otherwise your scan notes and README backups grow the tree every run and can push a project off the cheap path by their own accumulation

You may record that a secret-bearing file *exists* and list the variable names from `.env.example`. You may not open the file it shadows.

## Step 2 — Size the tree, then pick a path

Both gates — the cheap path and the scale gate — are decided here, and both key on **bytes of readable content and distinct file contents**, not on file count. File count alone is the wrong metric: five hundred two-line files are smaller than twenty real modules, and a tree can be simultaneously huge by count and trivial by content.

**What counts as readable content:** Tier A + Tier B, and nothing else. Tier C is excluded entirely. Manifests, docs, licences, and `.env.example` all count — you read them, so they count.

Compute three numbers. Do not estimate them; if you cannot compute them, say so and take the full path.

- **bytes** — total bytes across Tier A + Tier B
- **unique** — distinct file contents, by hash, so duplicated files count once
- **files** — the Tier A + Tier B count, reported but never decisive

| Condition | Path |
|---|---|
| bytes < 12 KB **and** unique ≤ 25 **and** the project is single-surface | **Cheap path** — one question, `SKILL.md` Phase 1 |
| bytes > 1.5 MB **or** unique > 400 | **Scale gate** — stop and ask, below |
| everything else | **Full path** — no gate, no question, no announcement |

**Bytes are decisive; `unique` is only a guard** against a small-bytes tree that is nonetheless structurally wide. A project whose entire readable content fits in twelve kilobytes does not earn three rounds of questions no matter how many files it is spread across. A 4 KB project of twelve two-page modules is a small project.

Boundaries favour the smaller path: exactly 12 KB with exactly 25 unique files is cheap. A tree of 520 near-identical stubs has a high file count, a low `unique`, and modest bytes — it takes the full path and fires no gate, which is the intended behavior.

**Single-surface** means one way in: a library, or a script, or one service — not two. A project that declares more than one entrypoint class (a CLI *and* an HTTP surface), ships more than one deployable, or carries a multi-service compose file is **never cheap**, whatever it measures. Those are exactly the projects whose architecture diagram and request-flow diagram are the whole point of the document, and the cheap path's *Minimal and elegant* shape has no section to put them in. Bytes alone cannot see this: a Redis-backed job queue with an HTTP control plane, a CLI, a worker, a three-service compose file and CI fits in under 10 KB of Python and still needs every section the full path gives it.

When the scale gate fires, stop and ask, with the real numbers and the five largest directories in the question:

> 4.1 MB across 812 distinct files — `src/` 1.4 MB · `services/` 1.1 MB · `web/` 900 KB · `packages/` 400 KB · `tools/` 300 KB.

Options to offer (4 max, recommend the second):

1. **Read all of it anyway** — highest fidelity; will be slow and may exhaust context mid-run, in which case I resume from my notes.
2. **Full-read the directories you care about, symbol-index the rest** — name them and I'll go deep there *(recommended; ask which)*.
3. **Full-read entrypoints, configs and instruction files; symbol-index everything else** — fastest, and the architecture section gets shallower.
4. **Split it** — document one sub-project now, the rest in later runs.

**Symbol-index** means: path, exported/public symbols, imports out, one line of purpose. Not a full read, and say so in the report.

**A programmatic full read counts as a full read.** Where the tree is large but repetitive, verifying every file by script — hashing, grepping for imports across all of them, diffing against an expected pattern — is stronger evidence than symbol-indexing and cheaper than opening each one. Record it as `scan_mode: "full"` and say in the report how you verified.

## Step 3 — Read for these seven answers

Reading order matters — instruction files, then manifests, then entrypoints, then follow the imports outward. Do not read alphabetically.

1. **Purpose** — what problem, for whom. From instruction files and the manifest description, never from your impression of the code.
2. **Surface** — how it is invoked: CLI commands, HTTP routes, exported API, UI entry, cron. This becomes Usage.
3. **Architecture** — the real components and their edges. Name every module the way the repo names it.
4. **Flow** — one representative end-to-end path, traced through actual functions. This becomes the sequence diagram, and it is the single highest-value thing you produce.
5. **Configuration** — every env var, flag, and config key, with defaults, from the code that reads them. Names and defaults only if the default is in source; never a real value.
6. **Install / run / test / deploy** — copied verbatim from scripts, Makefile, CI, or Dockerfile. If a step exists nowhere, it becomes `[FILL IN]`.
7. **Author intent and constraints** — what the instruction files demand of contributors. Anything a newcomer would get wrong.

## Step 4 — Reconcile before writing

- **Multiple instruction files** — the nearest-scoped one wins inside its subtree. Where a root file and a sub-project file conflict, describe both scopes.
- **Docs vs code** — the code wins in the document. Note the drift in the chat report only.
- **Multiple sub-projects / monorepo** — decide, and say which: one document covering all, or the sub-project the user named.
- **Nearly empty repo** — do not fabricate a project. Produce the skeleton with `[FILL IN]` at each unknown and say what's missing.

## Secrets

Tier C above already keeps the secret-bearing files closed. One case it doesn't cover: **a secret hardcoded in source you legitimately read.** Keep it out of the document, and tell the user in chat — that's a finding worth having.
