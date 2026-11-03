# threat-model — Spec-Driven Threat Model Generator

Generate a complete, verifiable threat model for any architecture input,
conforming to the **threatmodel/0.1** open spec. Output is valid JSON
scoreable by the bundled `tmbench-check` scorer.

**No vendor lock-in.** Works with any LLM via Claude Code, no external dependencies.  
**Self-contained.** Spec and scorer are bundled — the full ThreatAssessor repo is not required.  
**TA-enhanced.** When the TA repo is present, uses the full harness for richer output.  
Spec license: CC BY 4.0 (see `spec/threatmodel.md`).

---

## Usage

```
/threat-model path/to/arch.mmd
/threat-model path/to/main.tf
/threat-model path/to/architecture.md
```

Outputs `threatmodel.json` in the same directory as the input file.

---

## Bundled files

| File | Purpose |
|------|---------|
| `spec/threatmodel.md` | threatmodel/0.1 spec (CC BY 4.0) — the generation contract |
| `scripts/tmbench-check.py` | Scorer — validates and scores the output JSON |

Both files work standalone. The TA repo is not required.

---

## Instructions for Claude

### Step 0 — Detect mode

Check whether the ThreatAssessor repo is available:

```bash
# TA repo present if any of these exist:
test -f chatbot/harness/controller.py && echo "ta_mode" || echo "standalone"
command -v ta && echo "ta_mode" || echo "standalone"
```

- **standalone** (default): generate using this skill's spec + prompt; score with bundled `scripts/tmbench-check.py`
- **ta_enhanced**: TA repo or `ta` CLI found → use `ta tm run <path>` for generation; score with `ta tm run --score` or tmbench-check

---

### Step 1 — Read the spec

Read `spec/threatmodel.md` from this skill's directory.  
Focus on: §1 (Required Sections), §3 (Verification Checklist), §4 (Output Schema).

Locate this skill's directory:
```bash
# The skill lives next to this SKILL.md file
SKILL_DIR="$(dirname "$(realpath "$0")")"
# or find it:
find .claude/skills/threat-model -name SKILL.md -maxdepth 1 | head -1 | xargs dirname
```

---

### Step 2 — Read the architecture input

Read the file at the path given as argument. Auto-detect format from content:
- **Mermaid**: starts with `graph`, `flowchart`, or `sequenceDiagram`; or `.mmd` extension
- **Terraform**: contains `resource "…"` blocks; or `.tf` extension
- **Prose**: anything else — treat as a natural-language architecture description

---

### Step 3 — Determine coverage requirements

Count the components in the architecture before writing attack paths:
- ≤ 5 components → at least 3 attack paths
- 6–15 components → at least 5 attack paths
- > 15 components → at least 8 attack paths

Detect if the architecture is **agentic** (contains an LLM, autonomous agent, tool-calling component,
or RAG pipeline). If so: include at least one MITRE ATLAS technique and populate the `agentic`
governance block.

---

### Step 4 — Generate the threat model (standalone mode)

Produce a JSON object conforming to the §4 Output Schema from `spec/threatmodel.md`.

Rules:
- Output ONLY valid JSON — no markdown fences, no commentary, no preamble
- Every MITRE ATT&CK technique ID must be real, correctly named, and tactic-matched
- Every threat actor must have a `non_capabilities` list with at least 2 entries
- Every attack path must have at least one mitigation and one finding
- High and Critical findings require a CVSS 3.1 vector string
- Set `spec_version` to `"threatmodel/0.1"`
- Set `produced_by` to `"threat-model-skill/0.1"`
- Set `produced_at` to the current ISO 8601 datetime

**TA-enhanced mode**: instead of generating directly, run:
```bash
ta tm run <path> --out threatmodel.json
```
This uses the full TA harness (AIVSS scoring, brain patterns, MoE routing).

---

### Step 5 — Self-verify

Before writing, check every item in the §3 Verification Checklist from `spec/threatmodel.md`.
Fix any failing item. A TM that fails self-verification must not be written as-is.

---

### Step 6 — Write and score

Write the TM JSON:
```bash
# standalone: write to file next to architecture input
```

Then score it with the bundled scorer:
```bash
python3 <skill_dir>/scripts/tmbench-check.py --score threatmodel.json
```

If `tmbench-check` is not importable (missing `jsonschema` or similar), fall back to
Claude's own checklist-based verification and report it as "self-scored".

---

### Step 7 — Report to the user

```
threatmodel.json written  [standalone | ta_enhanced]
Architecture: <arch_id>
Components: N  |  Attack paths: N  |  Findings: N
Agentic: yes/no

Score: N/13  [PASS | FAIL]
  TR=N  TA=N  RD=N  PA=N

Gaps (if any):
  [severity] description
```

If scoring failed: report "self-scored (no scorer available)" and list the checklist result instead.

---

## Installing this skill

**Standalone install** (no TA repo needed):

```bash
mkdir -p ~/.claude/skills/threat-model
cp -r .claude/skills/threat-model/* ~/.claude/skills/threat-model/
```

Or clone just the skill:
```bash
# From the ThreatAssessor repo, export the two bundled files:
# spec/threatmodel.md   — the spec
# scripts/tmbench-check.py — the scorer
```

The skill is self-contained once those three items are in place:
`SKILL.md`, `spec/threatmodel.md`, `scripts/tmbench-check.py`.

---

## TA-enhanced features (when TA repo is present)

| Feature | Standalone | TA-enhanced |
|---------|-----------|-------------|
| TM generation | Claude prompt | `ta tm run` → harness pipeline |
| Scoring | Bundled `scripts/tmbench-check.py` | Same + AIVSS + brain patterns |
| MITRE validation | Best-effort (model knowledge) | Validated against technique DB |
| DETECT rules | None | 65 SOC detection rules evaluated |
| Export | `threatmodel.json` | `ta-export/1.0` bundle + `threatmodel.json` |

---

## Spec and scorer version

The `spec/threatmodel.md` and `scripts/tmbench-check.py` bundled here are copies of:
- `docs/tmbench/threatmodel.md` — spec source
- `.claude/skills/tmbench-check/scripts/tmbench-check.py` — scorer source

When the TA repo is updated, re-export to keep the bundle in sync:
```bash
cp docs/tmbench/threatmodel.md .claude/skills/threat-model/spec/threatmodel.md
cp .claude/skills/tmbench-check/scripts/tmbench-check.py .claude/skills/threat-model/scripts/tmbench-check.py
```
