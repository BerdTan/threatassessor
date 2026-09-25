# prompt-audit — Prompt Template Security Audit

Engine Item 16. Audit prompt templates as an adversarial security surface.
Six dimensions; no API required. Distinct from `promptsmith` (quality lens vs security lens).

## Run

```bash
python3 .claude/skills/prompt-audit/scripts/prompt-audit.py
```

## What it checks

| Dim | Name | What |
|---|---|---|
| PAU-1 | Template enumeration | Locate all prompt templates: critic constants, builders, f-string constructions |
| PAU-2 | Injection path audit | External content (arch text, TAclaw, enrichment, MCP params) interpolated without sanitisation |
| PAU-3 | Leakage check | System prompts exposing internal paths, key names, module names, error text |
| PAU-4 | Over-permission audit | Critic system prompts with generic helpfulness / role-widening phrases |
| PAU-5 | Instruction-override surface | User input escaping user-role into system-role context (prompt injection escalation) |
| PAU-6 | Critic scope tightness | Five critic prompts susceptible to role-redirect via poisoned architecture input |

## Relationship to other skills

| Tool | Question |
|---|---|
| promptsmith | Is this prompt high quality? |
| prompt-audit | Can this prompt be weaponised or bypassed? |
| aisurface-audit | Where does external data enter the system? (data-path level) |
| prompt-audit | How does ingested data become LLM input and where is construction vulnerable? (prompt layer) |

Run `aisurface-audit` first for the ingest surface map; `prompt-audit` for depth on the prompt construction slice.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No CRITICAL or HIGH findings |
| 1 | One or more CRITICAL/HIGH findings |
| 2 | Cannot parse input files |

## Attack vectors covered

| Vector | Dim |
|---|---|
| Arch diagram text containing "Ignore previous instructions" injected into critic prompt | PAU-2 |
| TAclaw-crawled file content embedding role-override directives | PAU-2 |
| System prompt reveals internal module path aiding targeted injection crafting | PAU-3 |
| Blackhat critic prompted to "be helpful" — exploitable to elicit attacker assistance | PAU-4 |
| User content prepended before system role (role boundary escape) | PAU-5 |
| Poisoned arch input redirects critic role — DETECT-QC-009 endogenous constraint evasion | PAU-6 |

## Findings — Engine Item 16 first run (2026-09-25)

Result: 0 critical, 1 high, 12 medium, 3 low, 6 info. Exit 1.

| Dim | Finding | Severity | Notes |
|---|---|---|---|
| PAU-1 | 21 template sites across 10 files | INFO | Critics: 13, Orchestrators: 2, Other: 6 |
| PAU-2 | `moe_orchestrator.py:1662` — raw `architecture`/`arch_name` in orchestrator prompt | HIGH | No sanitisation detected; attacker-controlled arch diagram can embed directives |
| PAU-2 | `agent_framework.py:334` + `ground_truth_generator.py:1572` — same pattern | MEDIUM | Core analysis pipeline; arch content flows directly into f-string prompts |
| PAU-3 | No internal-detail leakage | INFO | `/var/www` in scrum_master_critic.py is a threat example, not internal config |
| PAU-4 | No over-permissioned critics | INFO | blackhat/architect have tightest narrowing; purple/scrum/tester have 1 constraint each (LOW) |
| PAU-5 | 5 files with single-block prompts + external var interpolation | MEDIUM | No explicit system/user role separation — instruction-override possible |
| PAU-6 | 4 of 5 critics have anchor score 1/10 | MEDIUM | Prompts describe role but lack explicit constraint directives; scrum_master tightest (score 2) |

## Notes on PAU-4 and PAU-6

PAU-4 (over-permission) and PAU-6 (scope tightness) both assess critic system prompts but from different angles:
- PAU-4: does the prompt *grant* excess permission (helpfulness, role-widening)?
- PAU-6: is the prompt *anchored* tightly enough to resist *input-driven* role redirect?

A critic can pass PAU-4 (no helpfulness phrases) yet fail PAU-6 (low anchor count, no output-format constraint).
Both dimensions are needed.
