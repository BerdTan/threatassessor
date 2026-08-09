---
name: taci
description: Validate and debug the ThreatAssessor GitHub Actions CI workflow. Runs a local dry-run of the PR reviewer against changed .mmd files, checks workflow config, validates secrets wiring, and prints the formatted PR comment to stdout. Use after any change to .github/workflows/ta-review.yml or scripts/ci/ta_pr_review.py, or when the CI workflow fails on GitHub Actions.
argument-hint: "[--dry-run] [--arch <file.mmd>] [--check-workflow] [--fix-perms]"
---

# taci — ThreatAssessor CI Workflow Validator

Validates the TA GitHub Actions PR reviewer locally without needing a real PR.
Runs `scripts/ci/ta_pr_review.py` against a changed or specified `.mmd` file,
prints the formatted PR comment to stdout, and checks workflow configuration.

## When to use

- After editing `.github/workflows/ta-review.yml`
- After editing `scripts/ci/ta_pr_review.py`
- When a CI run fails on GitHub Actions — diagnose locally first
- To verify a new `.mmd` file produces a sensible review comment before pushing
- To confirm secrets are wired and the API health check passes

## Do NOT use for

- Running the full analysis pipeline — use `/rerun-moe` or `/rerun-corpus`
- Editing detection rules — use `/detect-loop`
- Checking critic quality — use `/critic-gym`

## Run

```bash
# Dry-run against currently changed .mmd files (vs master)
python3 .claude/skills/taci/scripts/taci.py --dry-run

# Dry-run against a specific .mmd file
python3 .claude/skills/taci/scripts/taci.py --arch tests/data/architectures/01_minimal_vulnerable.mmd

# Check workflow file + script for common issues (no API needed)
python3 .claude/skills/taci/scripts/taci.py --check-workflow

# Fix script permissions for GitHub Actions (marks api scripts executable)
python3 .claude/skills/taci/scripts/taci.py --fix-perms

# Full check: workflow validation + dry-run analysis
python3 .claude/skills/taci/scripts/taci.py --check-workflow --arch tests/data/architectures/21_agentic_ai_system.mmd
```

## Output

- Workflow config checks (secrets referenced, script permissions, venv step present)
- governance_check result (50ms, no LLM)
- analyze-stream result (gate=PASS/BLOCK)
- Formatted PR comment as it would appear on GitHub
- Exit 0 = PASS, exit 1 = BLOCK or config error

## Prerequisites

- API running: `./scripts/api/api_start.sh`
- `.env` present with `API_KEY` set
- For `--dry-run`: must be on a branch with at least one changed `.mmd` vs master
