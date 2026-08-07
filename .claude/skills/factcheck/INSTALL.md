# factcheck — install

A Claude Code skill that makes the model verify high-risk claims against real sources before stating them, and label anything it couldn't ground.

**Two files. Both are plain markdown — no dependencies, no build step, works on any machine that runs Claude Code (Windows, macOS, Linux).**

| File | Required? | Goes to | What it does |
|---|---|---|---|
| `SKILL.md` | Yes | `~/.claude/skills/factcheck/` | The procedure. Loads when invoked. |
| `factcheck-trigger.md` | Recommended | `~/.claude/rules/` | Makes it fire *without being asked*. Without this, the skill only runs when you type `/factcheck`. |

The second file is the one that matters. A skill only loads once something decides to load it — and a model about to state something false does not know it is about to. The trigger file sits in `~/.claude/rules/`, which is loaded into context at the start of every session, so the decision to check happens before the claim gets made.

---

## Install — Windows (PowerShell)

Run from the folder you unzipped into:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills\factcheck" | Out-Null
Copy-Item ".\SKILL.md" "$env:USERPROFILE\.claude\skills\factcheck\SKILL.md" -Force

New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\rules" | Out-Null
Copy-Item ".\factcheck-trigger.md" "$env:USERPROFILE\.claude\rules\factcheck-trigger.md" -Force
```

## Install — macOS / Linux

```bash
mkdir -p ~/.claude/skills/factcheck
cp ./SKILL.md ~/.claude/skills/factcheck/SKILL.md

mkdir -p ~/.claude/rules
cp ./factcheck-trigger.md ~/.claude/rules/factcheck-trigger.md
```

## Skill only, no always-on trigger

Run just the first two lines of either block. You'll get `/factcheck` as a manual audit command and nothing automatic.

## One project instead of every project

Put the skill at `<repo>/.claude/skills/factcheck/SKILL.md` instead of `~/.claude/`.

For the trigger, don't use a project `rules/` directory — instead paste the contents of `factcheck-trigger.md` into that repo's `CLAUDE.md`. `CLAUDE.md` is loaded into context automatically, so the trigger works the same way and is scoped to the one project.

---

## Verify it worked

1. **Restart Claude Code** — skills and rules are read at session start, so an already-running session won't see them.
2. Type `/factcheck` — it should load rather than erroring as unknown.
3. Ask something with a checkable fact in it (*"what parameters does this library's main function take?"*). With the trigger installed you should see a verification block with `[VERIFIED]` / `[UNVERIFIED]` lines and a quoted fragment from a real source, before the answer.

If nothing happens automatically, the trigger file is in the wrong place — confirm `~/.claude/rules/factcheck-trigger.md` exists.

## Uninstall

```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\skills\factcheck"
Remove-Item -Force "$env:USERPROFILE\.claude\rules\factcheck-trigger.md"
```

```bash
rm -rf ~/.claude/skills/factcheck ~/.claude/rules/factcheck-trigger.md
```

---

## What it costs

The trigger adds ~15 lines to the context of **every session on that machine, forever**. That's the honest price of it being always-on. The skill body itself costs nothing until invoked.

It also makes responses slower and longer when it fires, because grounding a claim means a real tool call and the evidence gets shown.

## What it does not do

- **It cannot verify what it cannot reach.** No network, no repo, no installed package means `UNVERIFIED` — which is the correct answer, not a bug.
- **It shares its own blind spots.** The model auditing its own draft holds the same beliefs that produced the claim. Tool-backed checking is what covers this; the self-audit alone does not. Getting past that needs a separate verifier process, which this is not.
- **It is not a guarantee.** It substantially raises the cost of stating something ungrounded. It does not make it impossible.

Graded 8/10 against an adversarial stress test with the trigger installed, 7/10 without.
