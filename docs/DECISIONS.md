# ThreatAssessor — Architectural Decision Log

Read this file at the start of every session. After any significant decision about architecture, logic, or format, add an entry: date, what was decided, reasoning, alternatives rejected.

---

## 2026-05-26 — Strategic Roadmap Priority: AIPattern YAML extraction first

**What was decided:**
Extract the hardcoded threat risk and control data from `chatbot/modules/patterns/ai_pattern.py` into YAML files (`chatbot/data/arc/risks.yaml`, `chatbot/data/arc/controls.yaml`) as the top roadmap priority.

**Reasoning:**
AIPattern embeds ~1,100 lines of Python dicts for ARC Framework risks (46 risks, 9 categories) and controls (88 controls). Updating a threat description, adding a new risk, or adjusting a control currently requires a Python edit and server restart. YAML extraction makes maintenance low-friction and sets the data-driven pattern that CloudPattern and ICSPattern should follow.

**Alternatives rejected:**
- *Implement CloudPattern first:* More user-visible but AIPattern is already in production and accumulating staleness debt.
- *MCP server first:* Higher external value but depends on a stable internal architecture; better to solidify the pattern layer first.
- *No change:* Acceptable short-term, but every new threat domain adds 1,000+ lines of hardcoded Python.

---

## 2026-05-26 — Roadmap: full priority order agreed

**What was decided:**
1. AIPattern → YAML data extraction
2. `scripts/backtest_all_architectures.py` — create missing script
3. CloudPattern implementation (ThreatPattern ABC already exists)
4. Enable AgentTool stubs in Architect + Tester critics (currently MVP1-disabled)
5. MCP server (5 tools wrapping REST API)
6. Parallel critic execution (optional — cuts ~40s from Expert Review)

**Reasoning:**
Items 1–2 are maintenance/correctness fixes. Items 3–4 deepen coverage and accuracy. Item 5 opens agent-to-agent integration. Item 6 is a performance optimisation with architectural trade-offs (loses fail-fast semantics).

**Alternatives rejected:**
- Parallel critics before agent tools: Performance gain is secondary to accuracy improvement.
- MCP before CloudPattern: MCP makes more sense once the pattern layer is richer.

---

## 2026-05-25 — Expert Review: Synthesis sub-step progress callbacks

**What was decided:**
Added 5 `progress_callback` signals inside Layer 3 of `MoEOrchestrator.run_pipeline()` using a `"synthesis:*"` stage prefix: `synthesis:confidence`, `synthesis:llm`, `synthesis:build`, `synthesis:save`, `synthesis:artifacts`.

**Reasoning:**
Layer 3 was a ~20s silent block. The SSE loop only had a generic ticker. Users saw "Running…" with no indication of which sub-step was executing. The `progress_callback` pattern was already established for critics (stages: `architect`, `tester`, `red_team`); extending it to synthesis sub-steps required only 5 `put_nowait()` calls and a branch in the SSE drain loop.

**Alternatives rejected:**
- Polling a status file: More complex, requires disk writes per sub-step.
- Single "synthesis started" callback: Doesn't convey the LLM wait (~20s) vs. fast steps.

---

## 2026-05-25 — Reports tab: JSON removed, moved to Raw Data tab

**What was decided:**
Reports tab shows only `.md` and `.mmd` files. All JSON (including Expert Review critique files) moved to Raw Data tab, which fetches the report directory async and organises JSON into Foundation / Expert Review / Live Session sections.

**Reasoning:**
Reports tab was mixing narrative documents (executive summary, action plan) with raw JSON data (critique files, ground truth). Analysts reading reports don't need raw JSON; developers debugging need JSON separately. The split makes each tab's purpose clear.

**Alternatives rejected:**
- Keep JSON in Reports under a collapsible section: Still mixes audiences.
- Remove JSON from UI entirely: Useful for debugging and download; should be accessible.

---

## 2026-05-24 — Tester false-positive detection: MITRE ground truth first

**What was decided:**
Rewrote `_check_if_false_positive()` in `tester_critic.py` to query `mitre.get_technique_mitigations(technique_id)` first. If the M-code is in the official MITRE list → definitively not a false positive, regardless of LLM phrasing.

**Reasoning:**
The Tester LLM was claiming M1032 is not a valid mitigation for T1485, which is factually wrong (MITRE lists M1032, M1053, M1018 for T1485). The previous heuristic relied on regex extraction from the LLM's own description, making it vulnerable to phrasing variations. Authoritative data should always override LLM output for factual assertions.

**Alternatives rejected:**
- Add explicit ground-truth assertions to the Tester system prompt: Prompt engineering is brittle; the LLM can still contradict it.
- Accept as known LLM limitation: Produces false findings in every Expert Review run — not acceptable.

---

## 2026-05-23 — Expert Review: Pause/Resume via SSE abort + checkpoint loading

**What was decided:**
Pause aborts the client-side `AbortController` (stops SSE). Resume creates a new `AbortController` and reconnects. The orchestrator skips already-completed critics by calling `_load_saved_critique(path)` — each critic saves its JSON immediately on completion, which serves as a natural checkpoint.

**Reasoning:**
Re-running completed critics on resume would waste ~60s of LLM calls and API quota. The orchestrator already saves critic JSON files immediately (`04_architect_critique.json` etc.), making checkpoint-based resume trivial — load the file, fire the `progress_callback` with the loaded result so the SSE frontend replays the live card.

**Alternatives rejected:**
- Server-side pause (pause the asyncio task): Complex and fragile across SSE reconnects.
- Re-run entire pipeline on resume: Wastes LLM API calls, adds ~90s latency.

---

## 2026-05-22 — MoE architecture: sequential fail-fast, not parallel

**What was decided:**
Critics run sequentially: Architect → Tester → Red Team. Each receives the previous critic's output. Pipeline aborts if a prerequisite is missing.

**Reasoning:**
Tester receives `architect_critique` to validate roadmap alignment. Red Team receives `tester_critique` to adjust exploit difficulty for known mapping errors. This chain enables cross-critic reasoning. Parallelism would break this dependency and reduce synthesis quality.

**Alternatives rejected:**
- Parallel execution: Faster (~40s saved) but critics would lose cross-referencing ability.
- Single monolithic LLM prompt: No independent validation; single point of hallucination.
