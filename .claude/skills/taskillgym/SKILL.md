---
name: taskillgym
description: Deterministic checker for our own skills and headline docs (CLAUDE.md, README files, MEMORY.md system state). Scores correct, complete, coherent, clear, conclusive; catches stale rule and tool counts that no longer match the repo. No LLM, read-only.
allowed-tools: Bash(python3:*)
---

# taskillgym

Run: `python3 .claude/skills/taskillgym/scripts/taskillgym.py [--json]`

## Checks

Mechanical facts only; it cannot judge whether instructions are good):
- **correct:** rule count and MCP tool count stated in CLAUDE.md, the README files (root, docs, mcp_server, taclaw), skill docs and memory system state match the repo; referenced paths exist.
- **complete:** every skill dir has SKILL.md with frontmatter; referenced scripts exist.
- **coherent:** frontmatter name matches directory; one quantity is not stated two ways across docs.
- **clear:** description of at least 40 chars; section headings present.
- **conclusive:** the skill states an output or exit contract.

## Output

Findings per item, severity `error` or `warn`, then a summary. Exit 1 if any `error`. Never edits files; fixing drift is a human decision (Entry 256).

**Known limit:** the MCP tool count is read only when "MCP" sits in the same clause as the number, so a line like "[mcp_server/README.md] — all 18 tools" is not checked. This avoids counting benchmark tools as MCP tools.
