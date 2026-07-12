---
name: codemap
description: Build and maintain a lightweight structural index (file tree + one-line purpose + top-level function/class/route names) of a codebase so you can jump straight to the right file instead of repeatedly running broad find/grep/glob searches or opening files just to see what's in them. Use this whenever you're about to work in a repo with more than a handful of files and don't already know exactly where the relevant code lives — orienting in an unfamiliar or large codebase, tracking down a bug whose location isn't obvious, adding a feature that likely touches multiple files, or any task where you'd otherwise need several exploratory searches before you could even start. Also use it to keep the index current after making edits, so the next search in the same session stays cheap. Skip it for small projects (single-file tools, short scripts) or when you already know exactly which file to open — building an index there costs more than it saves.
---

# Codemap

## The problem this solves

Without a map, orienting in a codebase means running broad searches over and over: `grep -r` across the whole tree, `find . -name`, opening files just to check if they're relevant. Each of those costs tokens, and the cost repeats every time — you re-discover the same structure on every task because nothing persists between searches.

A codemap flips this: spend a bit of effort once building a structural index (paths, one-line purpose, top-level symbols), then consult that index before searching. Most tasks after that need zero or one targeted read instead of several rounds of exploration.

The map is a **navigation aid, not ground truth**. It tells you *where to look*; you still read the actual file before editing it. Treat a mismatch between the map and the real file as the map being stale, not the file being wrong.

## Step 0: decide if it's worth it

Run a quick size check before doing anything else:

```bash
python3 scripts/build_codemap.py stat --root <project-root>
```

This returns `file_count` and `total_lines` in under a second, without extracting any symbols.

- **Small project** (rough guide: well under ~15-20 relevant files, or a codebase you can already see in full from one `view` of the directory) — skip the codemap entirely. A direct `grep`/`glob`/`view` will already be cheap, and standing up an index costs more than it saves. Just work directly.
- **Larger or unfamiliar project** — build the map. The bigger and less familiar the repo, the more this pays off.

If you're unsure, err toward building it — the build itself is fast (see below), and a stale-but-present map is still cheaper to skim than a cold search.

## Step 1: build or update the map

```bash
python3 scripts/build_codemap.py build --root <project-root> \
  --state .claude/codemap/state.json \
  --output .claude/codemap/codemap.md
```

This is safe to run repeatedly: it's incremental by default. Each file's mtime is checked against the stored state; unchanged files are skipped entirely and changed/new files are re-extracted. Deleted files drop out automatically — this holds for both a full rebuild (no `--paths`) and a targeted rescan (`--paths a.py b.py`); either way, anything no longer on disk is pruned from the map, not just files inside the `--paths` list. A full rebuild of a mid-size repo runs in a couple seconds; incremental updates are near-instant since only touched files get re-read, and no file's content is ever read more than once per run.

Since the project lives on disk in Claude Code and persists across sessions, leave `.claude/codemap/` in place rather than deleting it when you're done — the next session in the same repo gets to start from an already-built map and only pays the cost of re-scanning whatever changed since. Suggest the user add `.claude/codemap/` to `.gitignore` if they don't want the cache tracked (it's a local index, not something that needs to be shared or committed).

Read the resulting `codemap.md` — it's a plain markdown tree, safe to read in full for small-to-medium repos. For very large repos, `grep` it for the directory or filename you care about rather than reading the whole thing.

### After making edits

Don't rebuild the whole thing. Rescan just the files you touched:

```bash
python3 scripts/build_codemap.py build --root <project-root> \
  --state .claude/codemap/state.json \
  --output .claude/codemap/codemap.md \
  --paths path/to/edited_file.py path/to/new_file.js
```

This keeps the map fresh for the rest of the session at near-zero cost, so later searches in the same task still benefit.

## Scaling to large or polyglot repos

Past a certain size, dumping every file into one flat `codemap.md` defeats the point — you'd be reading hundreds of lines to find the one you need. The renderer handles this automatically: any directory subtree with more than 30 files (tune with `--collapse-threshold N`) gets collapsed to a single pointer line in the parent map, and its full detail is written to its own file under `.claude/codemap/dirs/`:

```
- src/ (312 files — see dirs/src.md)
```

Open `dirs/src.md` and you get that subtree's own tree, which may itself collapse further sub-directories into `dirs/src__core.md` and so on — it nests as deep as it needs to. Small repos (nothing over the threshold) render exactly as a single flat `codemap.md`, same as always; this only kicks in once a directory is actually big enough that collapsing helps.

For a hard cap instead of (or in addition to) the size threshold, `--depth N` limits how many directory levels get expanded inline before collapsing, regardless of file count.

`dirs/` is fully regenerated on every `build` or `set-purpose` call — it's cleared and rebuilt from the current state each time, so it never accumulates stale submaps for directories that got renamed, merged, or shrank below the threshold.

## Step 2: fill in purposes for files that matter

The script extracts structure (paths, symbols, line counts) mechanically — it has no understanding of what a file is *for*. That one-line purpose is worth adding yourself for the files you actually end up opening, since it's what makes future "where is X handled" questions answerable from the map alone instead of needing to reopen the file.

Don't try to annotate everything up front — that defeats the point. Add purposes lazily, only for files you've already read for some other reason:

```bash
python3 scripts/build_codemap.py set-purpose \
  --state .claude/codemap/state.json \
  --output .claude/codemap/codemap.md \
  --set "src/api/routes.py=FastAPI routes for findings CRUD" "src/auth/middleware.py=JWT check on all /api/* routes"
```

Keep each purpose to a genuine one-liner — what the file is responsible for, not a summary of its contents.

For a large repo where you want to annotate many files in one pass (e.g. after skimming a whole directory), use `--set-purpose-file` instead of many `--set` calls:

```bash
python3 scripts/build_codemap.py set-purpose \
  --state .claude/codemap/state.json \
  --output .claude/codemap/codemap.md \
  --set-purpose-file purposes.json
```

`purposes.json` can be either a flat JSON object (`{"src/api/routes.py": "FastAPI routes for findings CRUD", ...}`) or a newline-delimited text file of `path=purpose` lines — the same format `--set` takes, one per line instead of one per shell argument. Either format works; use whichever is easier to generate for the batch you're annotating.

## Step 3: use the map before searching

When asked to fix a bug, add a feature, or explain how something works:

1. Skim (or grep) `codemap.md` for filenames, purposes, or symbol names matching the task.
2. Open only the file(s) that look relevant — not the whole directory.
3. Read the actual file before editing. If what you find doesn't match what the map said (symbol renamed, file's role changed), trust the file, then rescan that path with `--paths` so the map is correct for next time.

If nothing in the map looks relevant, that's a real signal the feature doesn't exist yet or lives somewhere unexpected — a targeted `grep` at that point is well-justified, not a fallback you're avoiding.

## Symbol extraction coverage

The script recognizes top-level structure for:

- **Python** — `class`/`def`, plus the decorator directly above (FastAPI/Flask routes show up as `@router.get("/x") def handler`)
- **JavaScript/TypeScript** — `function`, `class`, arrow-function consts, `export`, Express-style `router.get(...)`/`app.post(...)`, Socket.io `socket.on(...)`
- **Go** — `func`/method receivers, `type ... struct|interface`, `router.GET(...)`-style route registration
- **Rust** — `fn`/`pub fn`, `struct`/`enum`/`trait`, `impl` blocks, the attribute macro directly above (`#[get("/x")]`), Axum-style `.route(...)`
- **Java** — `class`/`interface`/`enum`/`record`, method signatures with a visibility modifier, the annotation directly above (Spring's `@GetMapping` etc.)
- **Kotlin** — `fun`, `class`/`interface`/`object`, the annotation directly above, Ktor-style route DSL
- **C#** — `class`/`interface`/`struct`/`enum`/`record`, method signatures with a visibility modifier, the attribute directly above (`[HttpGet("x")]`)
- **Ruby** — `def`/`def self.`, `class`/`module`, Rails-style `get '/x', to: ...`
- **PHP** — `function`, `class`/`interface`/`trait`, the PHP8 attribute directly above, Laravel-style `Route::get(...)`
- **Swift** — `func`, `class`/`struct`/`enum`/`protocol`/`extension`, Vapor-style `app.get("x") { ... }`
- **Shell/Bash** — `function name` and `name() {` style definitions
- **SQL** — `CREATE TABLE|VIEW|FUNCTION|PROCEDURE|INDEX|TRIGGER` statements
- **C/C++** — `class`/`struct`/`namespace`, top-level function signatures
- **HTML** — `<title>`, top-level `function` declarations inside inline `<script>` blocks

Other file types are still listed in the tree with size and line count, just without a symbol list — that's normal, not a bug.

This is regex-based heuristic extraction, not a real parser. It'll miss unusual formatting (a signature split across many lines, an unconventional style) and won't catch language patterns it doesn't have a rule for — Java/C# method detection in particular relies on the method having an explicit visibility modifier on its own line, which is common but not universal. That's fine — the goal is "good enough to point you at the right file," not a complete symbol table. For a language entirely outside this list, the file tree and purpose annotations are still useful even with empty symbol lists.

A file's symbol list is capped at 40 entries for readability. If a file has more, the map shows the first 40 and a trailing `… +N more` line rather than silently dropping the rest — that's a signal the file is doing a lot and might be worth splitting, or just a big generated/config file where you'd grep for the specific name you need.

## Format reference

`codemap.md` for a small repo looks like this:

```
# Codemap
Generated: 2026-07-12T03:36:48+00:00 | 5 files

- src/
  - api/
    - routes.py — FastAPI routes for findings CRUD (14 lines)
      · @router.get("/findings") def list_findings
      · @router.post("/findings") def create_finding
      · class RouteError
  - utils.js (2 lines)
- index.html (9 lines)
  · <title>Test Page</title>
```

A file with more symbols than the display cap adds a trailing marker instead of silently truncating:

```
- big.py (103 lines)
  · def handler_0
  · def handler_1
  ...
  · def handler_39
  … +10 more
```

Once a subtree collapses (see "Scaling to large or polyglot repos" above), the parent map shows a pointer instead of the nested listing, and the detail moves to its own file:

```
- src/ (312 files — see dirs/src.md)
- README.md (40 lines)
```

`state.json` (same directory as `codemap.md`) is the underlying data everything is rendered from — mtimes, line counts, symbols (plus each file's true symbol count, for the truncation marker), and purposes per file. You generally don't need to read or edit it directly; use `build` and `set-purpose` instead. If you ever need to force a full rescan ignoring the mtime cache (e.g. the state file looks corrupted, or files were edited by something that didn't update mtimes), add `--force` to `build`. Binary files are detected both by extension and by a cheap null-byte sniff of the file's contents, so unfamiliar binary formats without a recognized extension still get skipped instead of being read as garbage text.
