# taclaw-swarm — TAclaw Swarm Runner

Fan out TAclaw jobs across multiple artifact targets in parallel, aggregate findings cross-swarm, and spotlight the champion claw by composite risk score.

## Run

```bash
# Auto-discover subdirectories under a base path
python3 .claude/skills/taclaw-swarm/scripts/taclaw-swarm.py --dir ./services

# Explicit targets
python3 .claude/skills/taclaw-swarm/scripts/taclaw-swarm.py \
  --targets ./auth/ ./payments/ ./catalog/

# Targets from file (one path per line)
python3 .claude/skills/taclaw-swarm/scripts/taclaw-swarm.py --targets-file targets.txt

# Wave 2: re-submit BLOCK targets for deeper analysis
python3 .claude/skills/taclaw-swarm/scripts/taclaw-swarm.py --dir ./services --wave2-on-block

# Save JSON report for downstream consumption
python3 .claude/skills/taclaw-swarm/scripts/taclaw-swarm.py \
  --dir ./services --output swarm_report.json
```

## Arguments

| Arg | Default | Notes |
|---|---|---|
| `--targets` | — | One or more target directories |
| `--dir` | — | Base directory; auto-discovers immediate subdirectories |
| `--depth` | 1 | Discovery depth (with `--dir`) |
| `--targets-file` | — | File with one target path per line |
| `--max-concurrent` | 6 | Max parallel TAclaw jobs |
| `--wave2-on-block` | off | Re-submit BLOCK targets after Wave 1 completes |
| `--output` | — | Write JSON report to file |
| `--api-url` | $TA_API_URL | API base URL |
| `--api-key` | $API_KEY | API key (TM-API-KEY header) |
| `--timeout` | 300 | Per-job poll timeout in seconds |

## Champion score

`champion_score = AIVSS × avg_fidelity × log(1 + technique_count)`

Higher AIVSS and broader technique surface with good fidelity wins. Ties broken by DETECT hit count.

## Output

```
Swarm Summary
══════════════════════════════════════════════════════════════════
Target          Gate    AIVSS   Techniques   Fidelity   Routing        Time
──────────────────────────────────────────────────────────────────
auth/           BLOCK   8.4     12           0.91       full_moe       47s ★
payments/       BLOCK   7.9     9            0.87       full_moe       39s
catalog/        PASS    4.2     6            0.95       brain_fast     12s
notify/         PASS    2.1     3            0.82       api_only        8s
══════════════════════════════════════════════════════════════════

Targets: 4 total  4 completed  0 failed
BLOCK gates: 2/4   Max AIVSS: 8.4   DETECT hits: 7

Top techniques across swarm:
  T1190        ████ (4/4 targets)
  T1552        ███  (3/4 targets)
  T1059        ██   (2/4 targets)

★ Champion: auth/
   AIVSS 8.4 · 12 techniques · fidelity 0.91 · 3 DETECT hits
   Passport: PP-a3f2e1d40b91
```

## Wave 2

When `--wave2-on-block` is set, BLOCK targets from Wave 1 are resubmitted after Wave 1 completes. Wave 2 results replace Wave 1 in the final report. Useful for monorepo scans where you want additional depth on hot targets only, keeping total token spend proportional to actual risk.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | All jobs completed (gates may be PASS or BLOCK — not a failure) |
| 1 | One or more jobs failed (API error or timeout) |
| 2 | Config error (missing API key, no targets discovered) |

## Outside-in use

```bash
# CI: exit non-zero if any target gates BLOCK
python3 .claude/skills/taclaw-swarm/scripts/taclaw-swarm.py \
  --dir ./services --output /tmp/swarm.json
python3 -c "
import json, sys
r = json.load(open('/tmp/swarm.json'))
sys.exit(1 if r['aggregate']['block_count'] > 0 else 0)
"

# Agent / MCP handoff: run swarm, feed JSON summary to next agent
python3 .claude/skills/taclaw-swarm/scripts/taclaw-swarm.py \
  --targets ./new_feature --output /tmp/swarm.json
```

## Relationship to other entry points

| Entry point | When to use |
|---|---|
| `ta` / `taclaw` CLI | Single target, interactive or CI gate |
| Dashboard (Platform tab) | Visual inspection of a single job |
| `run_taclaw` MCP tool | Single target from an agent |
| `taclaw-swarm` skill | Multi-target batch scan; aggregate + rank |
