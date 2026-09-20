# health-audit — ThreatAssessor Structural Health

Catches orphaned code, broken seams, and coverage gaps that accumulate silently as TA grows.
No API required. Read-only. Produces a findings table; never auto-modifies.

## Run

```bash
# Full audit — all 7 checks
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/health-audit/scripts/health-audit.py

# Single check
python3 .claude/skills/health-audit/scripts/health-audit.py --check detect
python3 .claude/skills/health-audit/scripts/health-audit.py --check routes
python3 .claude/skills/health-audit/scripts/health-audit.py --check fixtures
python3 .claude/skills/health-audit/scripts/health-audit.py --check env
python3 .claude/skills/health-audit/scripts/health-audit.py --check skills
python3 .claude/skills/health-audit/scripts/health-audit.py --check adapters
python3 .claude/skills/health-audit/scripts/health-audit.py --check schemas
```

## The 7 checks

| Check | What it catches |
|---|---|
| `detect` | DETECT rules in `soc_detection_rules.yaml` with no test scenario in `test_incident_simulator.py` |
| `routes` | FastAPI endpoints in `routes/*.py` not in `openapi.yaml`, and vice versa |
| `fixtures` | `.mmd` files in `tests/data/architectures/` not referenced in any test or CLAUDE.md |
| `env` | `.env.example` keys never read in Python; `os.getenv()` calls with no `.env.example` entry |
| `skills` | `.claude/skills/<name>/` dirs not mentioned in CLAUDE.md check commands |
| `adapters` | Adapter classes in `chatbot/adapters/` never imported outside that package |
| `schemas` | JSON schemas in `chatbot/schemas/` not referenced in code or `openapi.yaml` |

## When to run

- After any session that adds a new DETECT rule, API route, adapter, skill, or env var
- Before a P-blog that claims TA is self-auditing (confirm the claim is true)
- As part of a periodic hygiene pass (complement to `/session-cleanup`)

## What it does NOT do

- Full Python dead-code analysis (too noisy from dynamic imports) — use `/check-deprecation` after heavy refactoring
- Test execution — it checks *coverage* (which rules have scenarios) not *correctness* (whether scenarios pass)
- Auto-fix — findings are proposed actions only; human approves and applies

## Findings table

Output matches the session-cleanup format: `Area | Item | Status | Proposed Action`.

Status codes:
- `✅` — clean
- `⚠` — drift / gap (worth fixing before next blog or release)
- `❌` — missing file / broken reference (fix immediately)

Exit code 0 = all clean. Exit code 1 = one or more issues.

## Relationship to other skills

| Skill | Focus |
|---|---|
| `/health-audit` | Structural seams — orphans, drift, coverage gaps |
| `/session-cleanup` | Docs health — CLAUDE.md counts, DECISIONS.md freshness, bench debris |
| `/check-deprecation` | Import hygiene — broken imports, anti-patterns |
| `/check-skills` | Supply-chain integrity — SHA256 manifest, phishing patterns |
| `/check-detect` | Detection correctness — rule regression + live corpus |
