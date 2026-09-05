# ta-boxing — Brain vs Bot Evaluation

Three contenders, one deterministic referee, four quality dimensions + efficiency metrics.

## Usage

```bash
# Full boxing match
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/ta-boxing/scripts/ta-boxing.py \
       --arch 22_generic_ai_nodes \
       --mmd tests/data/architectures/22_generic_ai_nodes.mmd

# With CI gate (exits 1 if bot actionability < 0.6)
python3 .claude/skills/ta-boxing/scripts/ta-boxing.py \
  --arch 22_generic_ai_nodes --mmd ... --gate bot:actionability:0.6

# Show last stored result for an arch
python3 .claude/skills/ta-boxing/scripts/ta-boxing.py --arch 22_generic_ai_nodes --show-last

# List all past results
python3 .claude/skills/ta-boxing/scripts/ta-boxing.py --list
```

## Contenders

| Contender | Method | Cost |
|---|---|---|
| bot | Full LLM pipeline (ThreatAssessorHarness, LANGFUSE_SKIP=1) | ~30s, ~8k tokens |
| brain | TA Brain pattern inference; D2 corpus-derived from evidence arch history | <1s, 0 tokens |
| brain_mini | TA Brain pattern inference; D2 arch-specific via synthetic path validation | <1s, 0 tokens |

## Referee dimensions (all deterministic, no LLM)

| # | Dimension | Measurement |
|---|---|---|
| D1 | Threat Completeness | ATT&CK technique recall vs union reference set |
| D2 | Threat Accuracy | Topology applicability (method per contender — see above) |
| D3 | Mitigation Relevance | % techniques with ≥1 ATT&CK M-mitigation |
| D4 | Actionability | Remediation quality: severity + named control + rationale |

## Output

Result written to `report/<arch_name>/boxing_results.json`.

Also accessible via:
- `GET /api/v1/boxing/results` — list all
- Dashboard → Reporting → Boxing tab
- `POST /api/v1/boxing/run` + `GET /api/v1/boxing/jobs/{id}` — async API

## Gate spec

```
--gate contender:dimension:threshold
```
Examples: `bot:actionability:0.7`, `brain:composite:0.5`, `brain_mini:threat_accuracy:0.6`

Exits 0 on pass, 1 on fail.

## LANGFUSE

`LANGFUSE_SKIP=1` is baked into the bot contender runner. Tracing is never enabled by default.
