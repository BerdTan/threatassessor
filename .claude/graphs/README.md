# Codebase Context Graphs

Five MMD files covering the six architectural domains. Use these before opening files — each answers a specific navigation question.

| Graph | When to read | Key question answered |
|---|---|---|
| [master.mmd](master.mmd) | Unfamiliar with the codebase / orienting a new session | "How do the six domains connect? Where does X fit?" |
| [pipeline.mmd](pipeline.mmd) | Changing analysis output, adding a report file, tracing a score | "Which module produces this output file? What calls what?" |
| [harness.mmd](harness.mmd) | Changing stage order, adding a sink, debugging governance blocks | "What runs when, what fires side-effects, what's tested?" |
| [dashboard-tabs.mmd](dashboard-tabs.mmd) | Fixing a UI bug, adding a tab, tracing a fetch | "Which JS function, which API route, which Python module?" |
| [skills.mmd](skills.mmd) | Deciding which skill to run, adding a new skill | "Which skill for this task? What's the recommended sequence?" |

## Validate before committing

After any edit to a `.mmd` file, run:

```bash
python3 .claude/skills/codemap/scripts/validate_graphs.py
```

Catches: YAML multi-line values, `graph` mode with inter-subgraph edges (needs `flowchart`), `<br/>` inside edge labels, literal `\n` in node labels, duplicate node IDs, reserved keyword node IDs.

All five checks correspond to real rendering failures that have occurred. Exit 0 = clean.

## Update policy

Update the relevant graph **when you change**:
- A module's primary inputs/outputs → `pipeline.mmd`
- Stage order, a new stage, a new sink → `harness.mmd`
- A tab's data sources or a new API route → `dashboard-tabs.mmd`
- A new skill or a workflow sequence change → `skills.mmd`
- Any of the above + the master picture → `master.mmd`

These are **curated relationship maps**, not auto-generated call graphs. The value is in the semantic groupings and workflow edges — keep them accurate but don't add every function call.

## Last updated: 2026-07-18
