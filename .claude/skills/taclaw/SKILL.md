---
name: taclaw
description: Autonomous security assessment — crawls a target repo or directory, discovers architecture artifacts (Terraform, CloudFormation, OpenAPI, prose), merges them into a composite threat model, and runs the full TA pipeline. Accepts a local path or git URL. Reports gate (PASS/BLOCK), top attack paths, and offers export.
allowed-tools: Bash(python3:*) Bash(curl:*) Bash(git:*) Bash(source:*)
---

# taclaw — Autonomous Security Assessment Agent

TAclaw crawls any target (local directory or git URL), auto-discovers architecture
artifacts, runs them through TA's adapters and pipeline, and surfaces a unified
threat assessment — no manual `.mmd` authoring required.

## Usage

```
/taclaw <target>              # local directory or git URL
/taclaw <target> --name <n>  # override architecture name
/taclaw <target> --git        # force git_url mode
```

## Execution steps

1. **Submit job**
```bash
TA_BASE="${TA_API_BASE_URL:-http://localhost:8000}"
TA_KEY="${TA_API_KEY:-}"

curl -s -X POST "$TA_BASE/api/v1/taclaw/run" \
  -H "TM-API-KEY: $TA_KEY" -H "Content-Type: application/json" \
  -d "{\"target\": \"<TARGET>\", \"target_type\": \"<directory|git_url>\", \"arch_name\": \"<ARCH>\"}"
```
Capture `job_id` from response.

2. **Poll until done** (status: queued → running → completed | failed)
```bash
curl -s "$TA_BASE/api/v1/taclaw/jobs/<JOB_ID>" -H "TM-API-KEY: $TA_KEY"
```
Poll every 5s until `status == "completed"` or `"failed"`.

3. **Report results** — extract from completed job:
   - `gate`: PASS or BLOCK
   - `artifacts_found`: number of files processed
   - `graphs_merged`: number of architecture graphs merged
   - `composite_nodes` / `composite_edges`: size of the combined graph
   - `source_formats`: list of detected formats (e.g. ["terraform", "openapi"])
   - `export.gate.blocking_signals`: if BLOCK, explain what triggered it
   - Top 5 attack paths from `export.assessment.attack_paths`

4. **Present to user**:
   ```
   TAclaw Assessment: <ARCH_NAME>
   ─────────────────────────────────────────────────────
   Gate:             PASS / BLOCK
   Artifacts found:  12 (terraform: 3, cloudformation: 2, openapi: 7)
   Composite graph:  18 nodes, 24 edges
   
   Top attack paths:
     [CRITICAL] Internet → Payments DB (T1190, T1078)
     [HIGH]     API Gateway → Internal Admin (T1098)
     ...
   
   Blocking signals:  exploitation.severity=CRITICAL
   ```

5. **Offer next steps**:
   - "Export full report?" → `GET /api/v1/reports/<ARCH>/export`
   - "Run expert review?" → `POST /api/v1/jobs/expert-review` (FULL_MOE)
   - "Generate CISO brief?" → `POST /api/v1/reports/<ARCH>/generate-ciso-brief`
   - "Open issues for blocking signals?" → guide user to GitHub / issue tracker

## Notes

- If the API is not running: `./scripts/api/api_start.sh`
- Git cloning requires `git` on PATH and network access
- ProseAdapter uses an LLM call — slow for large `.md` files; prose extraction is best-effort
- If `artifacts_found == 0`, suggest: "Does the target have .tf, .yaml, .mmd, or .md files?"
- TAclaw defaults to `ssp_profile=low_risk_cloud`; pass a different profile if the user mentions a specific security posture
- Timeout: large repos (~200 files) take 30–90s for the pipeline; poll accordingly
