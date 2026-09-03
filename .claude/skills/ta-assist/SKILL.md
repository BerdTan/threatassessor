---
name: ta-assist
description: Interactive secure-by-design architecture review. Accepts any input (paste .mmd, describe in prose, upload a file path), runs TA threat analysis, and guides the user through findings, attack paths, mitigations, and architecture improvements. Orchestrates TA's MCP tools — the LLM handles conversation; TA's deterministic engine does all threat reasoning.
allowed-tools: Bash(python3:*) Bash(source:*) Bash(curl:*)
---

# ta-assist — Interactive Secure Architecture Review

Guides a user through a threat-model-driven secure design review in a conversation.
TA's deterministic engine does all security reasoning; this skill orchestrates the
MCP tool calls and presents results in plain language.

## Flow

1. **Collect input** — ask the user for their architecture:
   - Paste raw Mermaid (`.mmd` text)  
   - Describe in prose ("it's a 3-tier web app with PostgreSQL and Redis cache")  
   - Provide a file path (`.tf`, `.yaml`, `.mmd`, `.md`)

2. **Screen + analyze**
   - Paste / prose / file path → call `POST /api/v1/governance/check` first (~50ms, no LLM)
   - If not blocked → call `POST /api/v1/analyze/artifact` (file/prose) or `POST /api/v1/analyze-stream` (MMD)
   - Present: gate result (PASS/BLOCK), top 3 attack paths, overall risk level

3. **Drill into a component**
   - Ask: "Which component or service concerns you most?"
   - Call `POST /api/v1/enrich` with the named component
   - Present: `ComponentContext.as_markdown()` — matched nodes, attack paths, techniques, controls

4. **Offer next steps** (user picks one or more):
   - **Mitigations** — call `GET /api/v1/technique-mitigations?technique_ids=<ids>` for top techniques
   - **Improved architecture** — call `POST /api/v1/reports/{arch}/rerun-with-sm` to run Scrum Master
   - **Full export** — call `GET /api/v1/reports/{arch}/export`
   - **CISO brief** — call `POST /api/v1/reports/{arch}/generate-ciso-brief`

5. **Repeat** — loop back to step 3 for another component, or wrap up

## API base (read from env)

```bash
TA_BASE="${TA_API_BASE_URL:-http://localhost:8000}"
TA_KEY="${TA_API_KEY:-}"
```

## Quick curl helpers

```bash
# Governance screen (paste MMD text as JSON)
curl -s -X POST "$TA_BASE/api/v1/governance/check" \
  -H "TM-API-KEY: $TA_KEY" -H "Content-Type: application/json" \
  -d "{\"mmd_content\": \"$MMD_TEXT\", \"arch_name\": \"$ARCH_NAME\"}"

# Enrich a finding
curl -s -X POST "$TA_BASE/api/v1/enrich" \
  -H "TM-API-KEY: $TA_KEY" -H "Content-Type: application/json" \
  -d "{\"arch_name\": \"$ARCH_NAME\", \"component\": \"$COMPONENT\", \"finding\": {\"type\": \"technique\", \"id\": \"$TID\"}}"

# Export bundle
curl -s "$TA_BASE/api/v1/reports/$ARCH_NAME/export" \
  -H "TM-API-KEY: $TA_KEY"
```

## Conversation style

- Present findings in bullet points, not raw JSON
- For attack paths: `[CRITICALITY] Entry → Target (techniques: T1234, T5678)`
- For controls: numbered list, most-impactful first
- After each step ask "Want to explore another component, or move to the next step?"
- If gate is BLOCK: surface the blocking signals first and explain what they mean before continuing

## Notes

- If the API is not running, tell the user to run: `./scripts/api/api_start.sh`
- If `TA_API_KEY` is not set, check `.env` for `API_KEY`
- Prose input uses the ProseAdapter (LLM-assisted). If the LLM can't extract nodes, fall back to asking the user for a `.mmd` description
- Architecture name defaults to the filename stem or "ta_assist_session"
