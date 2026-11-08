# tmleaderboard — TMbench Leaderboard + Open Submission

Maintain and display the TMbench leaderboard. Any tool that produces `threatmodel/0.1`
compliant JSON can be ingested, scored, and ranked alongside existing entries. No pipeline
access required — the scorer reads the spec and your JSON files.

This skill is designed to become the open standard entry point: external teams submit their
tool's outputs, the skill validates and scores them, and they appear on the leaderboard.

## Run

```bash
# Show current leaderboard (ranked by weighted mean)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmleaderboard/scripts/tmleaderboard.py

# Ingest a new tool — score all JSONs in <dir> and add to leaderboard
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmleaderboard/scripts/tmleaderboard.py --ingest <tool_name> <dir>

# Re-score an existing tool against the current spec version
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmleaderboard/scripts/tmleaderboard.py --rescore <tool_name>

# Re-score all tools (after a spec update)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmleaderboard/scripts/tmleaderboard.py --rescore-all

# Per-arch dimension diff between two tools
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmleaderboard/scripts/tmleaderboard.py --diff <tool_a> <tool_b>

# Show full per-arch breakdown for one tool
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmleaderboard/scripts/tmleaderboard.py --breakdown <tool_name>

# Export leaderboard as markdown table (for README / blog)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmleaderboard/scripts/tmleaderboard.py --export md

# List all registered tools
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tmleaderboard/scripts/tmleaderboard.py --list
```

## Output — default leaderboard view

```
TMbench Leaderboard  spec v0.1  |  10 reference architectures  |  2026-11-08
Weighted mean: T1×1.0  T2×1.5  T3×2.0  T4×2.5  |  Pass threshold: 8/13 (no zeros)

 Rank  Tool            Arches  Mean   W.Mean  Pass    T1    T2    T3    T4
   1   deepseek_flash  10/10  13.00  13.000  10/10  13.0  13.0  13.0  13.0
   2   ta_v3_1         10/10  12.90  12.886  10/10  12.3  13.0  13.0  13.0
   3   hetzner_27b     10/10  12.80  12.771  10/10  ...
   ...
```

Columns:
- **Mean** — simple arithmetic mean across all scored architectures
- **W.Mean** — weighted mean (T1×1.0, T2×1.5, T3×2.0, T4×2.5); primary ranking key
- **Pass** — architectures that meet PASS threshold (≥8, no TATB dimension at 0)
- **T1–T4** — mean score per tier

## Submitting an external tool

Any tool that produces `threatmodel/0.1` JSON output can be submitted.

### Step 1 — Produce outputs for the 10 reference architectures

The corpus is at `docs/tmbench/corpus/`. Each `.mmd` file is one architecture.
Run your tool against all 10 and produce one JSON file per architecture.

Each JSON must conform to the `threatmodel/0.1` schema:
- `spec_version: "threatmodel/0.1"` (required)
- `architecture_id` matching the corpus arch ID (e.g. `t1_rest_api`)
- `produced_by` — your tool name + version string
- Full sections: `architecture_summary`, `threat_actors`, `attack_paths`,
  `mitigations`, `findings`, `governance`

Full schema: `docs/tmbench/threatmodel.md §4`. Spec version: `threatmodel/0.1` (see `docs/tmbench/CHANGELOG.md` for patch history).

### Step 2 — Ingest

```bash
python3 .claude/skills/tmleaderboard/scripts/tmleaderboard.py \
  --ingest my_tool_v1 /path/to/my/outputs/
```

The script:
1. Validates each JSON has `spec_version: "threatmodel/0.1"`
2. Resolves `architecture_id` from the JSON field (or filename as fallback)
3. Scores each file with the TATB rubric
4. Writes scored results to `docs/tmbench/results/my_tool_v1/`
5. Prints the tool's per-arch breakdown
6. Shows the updated leaderboard

### Step 3 — Review and PR

Review the scores, fix any gaps in your output format, re-ingest. When happy, open a PR
adding your `docs/tmbench/results/<tool_name>/` directory. The leaderboard is updated
automatically on merge.

## Scoring rubric (TATB)

| Dimension | What it measures | Max |
|---|---|---|
| Threat Relevant (TR) | Threat actors grounded to architecture components | 3 |
| TTP Accurate (TA) | MITRE ATT&CK technique IDs correct + ATLAS for agentic arches | 3 |
| Risk Defensible (RD) | Severity ratings differentiated + rationale present | 3 |
| Plan Actionable (PA) | Mitigations specific, complete, with implementation status | 3 |
| Bonus | ATLAS coverage on agentic architectures OR completeness across all checks | 1 |
| **Total** | | **13** |

Pass threshold: ≥8 with no TATB dimension at zero.
Automatic Reject: any TATB dimension at 0, regardless of total.

## Tier weights

| Tier | Complexity | Architectures | Weight |
|---|---|---|---|
| T1 | Simple REST APIs, web apps | t1_rest_api, t1_web_app | 1.0× |
| T2 | Microservices, CI/CD, SaaS | t2_microservices, t2_cicd_pipeline, t2_saas_integration | 1.5× |
| T3 | Hybrid identity, container orchestration | t3_* | 2.0× |
| T4 | RAG pipelines, agent fleets | t4_* | 2.5× |

Weights compensate for rubric flatness: a T4 arch with 15 components is not intrinsically
harder to score 13/13 than a T1 arch with 5 components under the current spec. The weights
are a temporary scaffold — as the rubric matures, harder architectures should become
intrinsically harder to score perfectly, and weights converge toward 1.0.

## Corpus

10 reference architectures in `docs/tmbench/corpus/`:

| ID | Tier | Description |
|---|---|---|
| t1_rest_api | T1 | Simple REST API with auth service |
| t1_web_app | T1 | Web app + CDN + database |
| t2_microservices | T2 | 8-service microservices mesh |
| t2_cicd_pipeline | T2 | CI/CD pipeline with artifact store |
| t2_saas_integration | T2 | SaaS platform with third-party integrations |
| t3_hybrid_identity | T3 | Hybrid AD + cloud IAM + SSO |
| t3_container_orchestration | T3 | Kubernetes cluster + service mesh |
| t4_rag_pipeline | T4 | RAG pipeline with vector store + LLM API |
| t4_agent_fleet | T4 | Autonomous agent fleet with tool registry |
| t4_multi_region | T4 | Multi-region active-active with data sovereignty |

## Results storage

```
docs/tmbench/results/
  <tool_name>/
    t1_rest_api.json          # scored TM output for this arch
    t1_web_app.json
    ...
  README.md                   # submission instructions
```

Each stored JSON is the original tool output (not modified). Scores are recomputed on
demand by `--rescore` and displayed live by the leaderboard view.

## Related

- `docs/tmbench/threatmodel.md` — full spec + schema (§4)
- `docs/tmbench/corpus/` — 10 reference architecture `.mmd` files
- `docs/tmbench/results/` — all tool submissions
- `docs/tmbench/leaderboard.html` — rendered HTML leaderboard
- `/tmbench-check` — score a single TM JSON in detail
- `/tmeval` — adversarial red-team probe (outside-in + inside-out)
