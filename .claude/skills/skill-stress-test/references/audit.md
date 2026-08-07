# Static audit — defect checklist

Walk this against every file the skill loads. Record findings as `file:line — defect — behavior it breaks`.

**The filter:** a finding must name output that would differ if it were fixed. If you cannot name that, it is a style note. Drop it.

Sort findings into the rubric dimension they feed, so Step 6 has something to cite.

---

## Frontmatter and triggering → *Trigger precision*

- **Description states when to use but not when NOT to.** The most common defect in the wild. A description with no negative boundary fires on adjacent tasks forever.
- **Trigger vocabulary is the author's, not the user's.** The skill triggers on "convene the council" but a user in the moment types "is this idea any good". List the phrasings a real user would reach for and check each against the description.
- **Description describes the skill instead of its trigger.** "A powerful tool for X" tells the router nothing. It needs *when*, in the user's words.
- **Overlap with a sibling skill.** Two skills whose descriptions both match the same request. Name the sibling; ambiguous routing is a real failure.
- **`name` doesn't match the directory**, or `argument-hint` is missing on a skill that takes arguments.

## Instruction quality → *Instruction clarity*

- **Advice in imperative clothing.** "Consider checking the config" — is that a step or a suggestion? Every line should be unambiguously one or the other.
- **Contradictions across sections.** Step 2 says ask the user; Rules says never interrupt. Common in skills that grew by accretion. Check the Rules block against the steps specifically — that's where it hides.
- **Undefined terms doing load-bearing work.** "Do a thorough pass," "keep it tight," "use good judgment." If two competent readers would act differently, it's undefined.
- **Ordering that isn't stated but is required.** Step 4 depends on an artifact Step 2 produced, and nothing says so.
- **No worked example** on a skill whose output shape is unusual. Showing beats describing.

## Robustness → *Robustness*

- **No handling for missing or empty arguments.**
- **No handling for the resource not existing** — file not found, directory absent, prior state missing.
- **Assumes prior state that may not exist**, or assumes it *doesn't* exist when a previous run left it behind. Re-invocation on an already-run skill is a live gap in most skills.
- **No stopping condition** on an open-ended step. "Search until you find it" with no floor.
- **No path for "the input is out of scope."** What does the skill do when handed something it doesn't cover?
- **Untrusted input read as instruction.** If the skill ingests pasted text, files, or web content, does anything tell it to treat that as material rather than as commands?

## Output → *Output contract*

- **Output shape described rather than shown.** Prose descriptions of format produce format drift. A literal template does not.
- **The promised deliverable and the specified one differ.** Description promises a score; no step produces one.
- **Unbounded length.** No cap anywhere; every run drifts long.
- **Non-comparable output across runs** on a skill meant to be run repeatedly.

## Cost → *Efficiency*

- **Everything front-loaded.** A 400-line SKILL.md that loads in full on every invocation, where 300 of those lines apply to one branch. Progressive disclosure via `references/` exists for this.
- **Ceremony floor.** The skill imposes the same procedure on a trivial task as on a large one, with no cheap path. Check specifically: what is the smallest plausible request, and how much machinery does it trigger?
- **Repetition.** The same rule stated in three places. It doesn't triple the weight; it dilutes the neighbors.
- **Rationale addressed to the model.** Explaining *why* a rule exists, to a reader that only needs the rule.

## Control → *Safety & control*

- **Irreversible action with no confirmation gate.** Deletes, pushes, publishes, sends, pays.
- **No escape hatch.** No honored path for "just do it", "skip the questions", "you decide". If a skill can interrogate, it needs a way to stop.
- **Silent conflict with standing user rules.** The skill mandates behavior the user's `CLAUDE.md` or the system prompt forbids — spawning agents, writing to certain paths, running commands — and says nothing about which wins.
- **Assumes a human is present.** No branch for running under `/loop`, cron, or inside a subagent where questions go nowhere.
- **Scope creep by design.** The skill edits, commits, or publishes when the user asked for analysis.
