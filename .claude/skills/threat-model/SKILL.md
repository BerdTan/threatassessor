# threat-model — Spec-Driven Threat Model Generator

Generate a complete, verifiable threat model for any architecture input,
conforming to the **threatmodel/0.1** open spec. Output is valid JSON
that any `tmbench-check`-compatible scorer can evaluate.

**No vendor lock-in.** Works with any LLM via Claude Code.
Spec license: CC BY 4.0 (see `spec/threatmodel.md`).

---

## Usage

```
/threat-model <path-to-architecture>
/threat-model path/to/arch.mmd
/threat-model path/to/main.tf
/threat-model path/to/architecture.md
```

Outputs `threatmodel.json` in the same directory as the input file,
or prints to stdout with `--stdout`.

To score the output:
```bash
python3 .claude/skills/tmbench-check/scripts/tmbench-check.py --score threatmodel.json
```

---

## What it produces

A `threatmodel/0.1` JSON with six required sections:

1. **Architecture Summary** — component inventory, trust boundaries, data classification
2. **Threat Actor Profile** — at least one actor with motivation, capability tier, non_capabilities
3. **Attack Paths** — MITRE ATT&CK technique IDs, target component, impact, likelihood
4. **Mitigations** — control framework references (NIST CSF / CIS / CSA ART), residual risk
5. **Risk Assessment** — CVSS or AIVSS severity vectors, remediation priority
6. **Governance Signals** — data sovereignty, compliance scope, third-party dependencies

For agentic architectures (LLM components, autonomous agents, tool-calling pipelines),
the output also includes MITRE ATLAS techniques and an agentic governance block.

Pass threshold: **≥ 8/13** on the TATB rubric with no dimension at 0.

---

## Run

```bash
SKILL_DIR="$(git rev-parse --show-toplevel)/.claude/skills/threat-model"
```

Claude Code reads the architecture file and the spec, then generates the TM JSON.

---

## Instructions for Claude

When this skill is invoked:

1. **Read the spec** from `spec/threatmodel.md` in this skill's directory.
   Focus on §1 (Required Sections), §3 (Verification Checklist), and §4 (Output Schema).

2. **Read the architecture input** from the path provided as argument.
   Auto-detect format:
   - Mermaid (`.mmd`, starts with `graph`/`flowchart`/`sequenceDiagram`)
   - Terraform (`.tf`, contains `resource "..."`)
   - Prose (`.md`, `.txt`, or any other — treat as architecture description)

3. **Determine architecture size** for minimum attack path coverage:
   - ≤ 5 components → at least 3 attack paths
   - 6–15 components → at least 5 attack paths
   - > 15 components → at least 8 attack paths
   Count components in the architecture before writing attack paths.

4. **Detect if the architecture is agentic** (contains an LLM, autonomous agent,
   or tool-calling component). If so:
   - Include at least one MITRE ATLAS technique (AML.T0043, AML.T0048, etc.)
   - Populate the `agentic` block in governance

5. **Generate the threat model** as a JSON object conforming to the §4 Output Schema.
   Rules:
   - Output ONLY valid JSON — no markdown fences, no commentary
   - Every MITRE ATT&CK technique ID must be real and match its technique name and tactic
   - Every threat actor must have a non-empty `non_capabilities` list (at least 2 entries)
   - Every attack path must have at least one mitigation and one finding
   - High and Critical findings require a CVSS 3.1 vector string
   - Set `spec_version` to `"threatmodel/0.1"`
   - Set `produced_by` to `"threat-model-skill/0.1"`
   - Set `produced_at` to the current ISO 8601 datetime

6. **Self-verify** using the §3 Verification Checklist before writing output.
   For each checklist item, confirm it passes. If any item fails, fix the TM before outputting.

7. **Write the output**:
   - Default: write to `threatmodel.json` in the same directory as the input file
   - With `--stdout`: print to stdout

8. **Report** to the user:
   ```
   threatmodel.json written
   Architecture: <arch_id>
   Components: N  |  Attack paths: N  |  Findings: N
   Agentic: yes/no
   
   To score: python3 .claude/skills/tmbench-check/scripts/tmbench-check.py --score threatmodel.json
   ```

---

## Spec bundled here

`spec/threatmodel.md` is included in this skill directory so it works without
the full ThreatAssessor repository. It is identical to `docs/tmbench/threatmodel.md`
in the TA repo and versioned together with it.

If you want to validate the skill's output as part of a CI pipeline, the scorer
(`tmbench-check`) is also in the TA repository under `.claude/skills/tmbench-check/`.

---

## Relationship to TMAgent

`TMAgent` (`chatbot/agents/tmagent.py`) is the full TA implementation of this skill:
same spec, same prompt contract, but wired into the TA harness (AIVSS scoring,
DETECT rules, MoE routing, brain pattern matching). If you have the TA API running,
use `ta tm run <path>` for the enriched output. This skill is the standalone version.
