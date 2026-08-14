# State and change detection

State lives at `<root>/.readme-forge/state.json`. Git is used as well when the project has it; neither source alone is sufficient — git misses uncommitted work and non-git projects, the manifest misses intent.

---

## Schema

```json
{
  "schema": 1,
  "project_root": "c:/path/to/project",
  "created": "2026-08-12",
  "runs": [
    {
      "n": 1,
      "date": "2026-08-12",
      "targets": ["github"],
      "shape": "oss-product",
      "framing": "first",
      "visuals": ["mermaid", "ascii", "badges"],
      "extras": ["quickstart", "faq"],
      "git_head": "a1b2c3d",
      "scan_mode": "full",
      "scope": null,
      "consent": "human",
      "published": ["Initial documentation of the job runner and worker pool"],
      "withheld": ["Vendor contract terms in docs/legal"]
    }
  ],
  "hash_algo": "sha256-8",
  "manifest": {
    "src/index.ts": { "hash": "9f2a41c8", "bytes": 4210 }
  }
}
```

`scope` is the list of paths this run actually covered — set it when the scale gate's Option 2 or Option 4 narrowed the run, and leave it `null` when the whole tree was covered. **A path outside the previous run's `scope` is not a change; it was never documented.** Report it as newly covered rather than listing it in the change list, or you will publish "the worker service was added" about a service that has been there since before run 1.

`hash` is the first 8 hex characters of the SHA-256 of the file's bytes, and `"hash_algo": "sha256-8"` is recorded alongside `manifest` so a future run can tell whether it can compare. **A manifest whose `hash_algo` you do not recognise, or which carries none, is unusable** — say so in the report and fall back to git. `manifest` covers Tier A + Tier B paths only. Keep the last 5 runs; drop older entries but keep their `published` and `withheld` lists merged into the most recent retained run. `git_head` is `null` on a project with no git.

**`consent` records how the run's publishing decisions were approved**, and it is not optional:

| Value | Means |
|---|---|
| `"human"` | a person answered the Phase 4 review gate |
| `"defaults"` | no human was available; the changelog was omitted entirely |
| `"escape-hatch"` | the user waved off the questions; the changelog was omitted entirely |

Only `"human"` may carry a non-empty `published` list. If a later run finds the most recent run marked `"defaults"` or `"escape-hatch"`, **say so at the next review gate** — the baseline it is diffing against was never approved, so changes from that run are still unpublished and belong in this run's gate.

Write state **only after** the document is written and verified. A run that failed halfway must not shift the baseline.

## Deriving the change list (Phase 4)

Three inputs, combined:

1. **Manifest diff** — added, removed, and modified paths since the last run's manifest.
2. **Git** — `git log --oneline <last git_head>..HEAD` plus `git diff --stat`, and `git status --porcelain` for uncommitted work. If `git_head` is unreachable (rebase, force-push, shallow clone), fall back to manifest-only and say so.
3. **A re-read of what changed** — open the modified files that matter. This is what turns a file list into a statement about the project.

**Say out loud how many of the three you actually got.** An empty or missing `manifest` silently reduces this to git alone; a project with no git reduces it to the manifest alone; both together mean you have **no change detection at all** — in that case say so plainly, treat the run as a first run for changelog purposes, and rebuild the manifest for next time rather than inventing a change list.

Then **synthesize, don't enumerate**. Group the raw signal into at most 7 statements a reader would care about — a **ceiling, not a quota**. One commit that changed one thing is one statement; never pad toward a range. Drop anything a reader wouldn't: formatting, lockfile churn, dependency bumps with no behavior change, test-only edits, typo fixes.

Each statement carries its evidence for the review question — the user needs to know what they're approving:

> **Auth moved from session cookies to JWT** — `src/auth/*`, 6 commits, removes `express-session`

## The review gate

Ask with multiSelect: **"Tick anything that should NOT go in the published document."** Every derived change is an option; add an open door for "something else here shouldn't ship — I'll tell you."

Rules:

- **Withheld means absent everywhere.** Not just missing from the changelog — no section may describe the withheld state of the world. If auth is withheld, the Architecture section keeps its previous description of auth, and you say so in the chat report.
- **Withheld persists.** It stays in `withheld` and is re-suppressed on every future run without re-asking. Mention once per run that N items remain suppressed, and that they can be released on request.
- **Cascades get flagged, not guessed.** If withholding one change makes another statement incoherent — a diagram that can't be drawn, a config table that would be wrong — say so during the gate and ask, rather than publishing something half-true.
- **Nothing changed** → say so, ask whether to regenerate anyway. If yes, the document is rewritten and the changelog is untouched.

## Edge cases

- **State records a run whose output isn't there** — no `README.md`, or one byte-identical to `README.prev.md`. That run never completed, or was reverted. Trust the document on disk over what state claims was published: treat the on-disk file as the baseline, and move that run's `published` entries back into this run's review gate so they get approved rather than assumed.
- **State exists, `project_root` doesn't match** — the project moved or was copied. Treat as an update run, update the path, mention it.
- **Schema is newer than you understand** — do not overwrite. Report it and stop.
- **`--fresh`** — copy the current state to `.readme-forge/state.prev.json`, start a new state with `runs: []` and `framing: "first"`. Withheld items carry over; they were withheld for a reason.
- **Existing README not written by this skill** — copy it to `.readme-forge/README.prev.md` before writing, and mine it first for facts worth keeping (author intent, credits, acknowledgements, links) that the code cannot tell you.
