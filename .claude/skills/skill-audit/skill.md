# skill-audit — Skill Corpus Execution Surface Audit

Engine Item 15. Audit the `.claude/skills/` corpus as an adversarial execution surface.
Six dimensions; no API required. Distinct from `check-skills` (tamper detection vs execution risk).

## Run

```bash
python3 .claude/skills/skill-audit/scripts/skill-audit.py
```

## What it checks

| Dim | Name | What |
|---|---|---|
| AUD-1 | Parameter injection | shell=True / eval() / os.system() with unsanitised user args |
| AUD-2 | Privilege path audit | Writes to report/, chatbot/data/, .env, policies/, DECISIONS.md |
| AUD-3 | Skill chaining map | Skills invoking other skills; transitive blast radius if downstream compromised |
| AUD-4 | Output injection | Skills writing to shared docs (DECISIONS.md, docs/blog/) consumed by other skills |
| AUD-5 | Manifest coverage gap | .py/.sh scripts not covered by skills.sha256 |
| AUD-6 | Execution scope drift | Network/write ops vs declared allowed-tools |

## Relationship to check-skills

| Tool | Question |
|---|---|
| check-skills | Did someone modify this file (tamper detection)? |
| skill-audit | If a skill is modified or receives adversarial input, what is the blast radius? |

Both are needed; neither is redundant.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No CRITICAL or HIGH findings |
| 1 | One or more CRITICAL/HIGH findings |
| 2 | Cannot parse input files |

## Attack vectors covered

| Vector | Dim |
|---|---|
| Unsanitised user arg → shell injection via skill script | AUD-1 |
| Compromised skill writes to .env / policies (credential clobber) | AUD-2 |
| Tampered downstream skill whose output controls upstream execution | AUD-3 |
| Adversarial output injected into DECISIONS.md feeds recall/gen-blog | AUD-4 |
| New skill added without manifest entry — tamper detection blind spot | AUD-5 |
| Skill performs network calls outside its declared allowed-tools scope | AUD-6 |

## Notes on AUD-5

AUD-5 cross-references `.py`/`.sh` scripts only (not `.md` files). After adding a new skill, regenerate
the manifest before re-running:

```bash
python3 .claude/skills/check-skills/scripts/check-skills.py --regen
```

## Findings — Engine Item 15 first run (2026-09-20)

Result: 0 critical, 0 high, 14 medium, 35 low, 4 info. Exit 0.
(After regenerating skills.sha256 manifest to include skill-audit.py.)

| Dim | Finding | Severity | Notes |
|---|---|---|---|
| AUD-1 | No parameter injection patterns detected | INFO | 72 skill scripts scanned; no shell=True/eval()/os.system() with argv paths |
| AUD-2 | Expected writes to report/chatbot/data/policies | LOW | By design; no .env writes found |
| AUD-3 | audit-to-detect → check-detect, detect-loop | MEDIUM | Multi-hop chain; both are in manifest — low operational risk |
| AUD-3 | detect-loop → check-detect | MEDIUM | Multi-hop; check-detect is manifest-covered |
| AUD-3 | incident-simulator → check-detect | MEDIUM | Multi-hop; same as above |
| AUD-3 | Transitive nodes: aisurface-audit, check-detect, critic-gym, detect-loop, model-audit | MEDIUM | Appear as both invoker and invoked; all manifest-covered |
| AUD-4 | detect-loop: writes DECISIONS.md | MEDIUM | Intended; output feeds recall/gen-blog/session-cleanup next session |
| AUD-4 | gen-blog: writes DECISIONS.md | MEDIUM | Intended; same consumers |
| AUD-4 | tatb-loop: writes DECISIONS.md | MEDIUM | Intended; same consumers |
| AUD-5 | All 72 corpus scripts in SHA256 manifest | INFO | 173 manifest entries clean after regen |
| AUD-6 | 7 skills: network calls but allowed-tools lacks WebFetch | MEDIUM | brain-grow, check-mcp, incident-simulator, quick-test, run-er, tatb-corpus, tatb-score |
| AUD-6 | 8 skills: no allowed-tools declaration | LOW | anti-slop-web, audit-to-detect, check-sip, codemap, critic-gym, rerun-moe, taci, taclaw-swarm, taco-check, taco-run |
