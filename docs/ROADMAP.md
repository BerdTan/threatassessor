# ThreatAssessor — Roadmap (open items only)

The single source for "what is next". `/recall` reads this file. Finished items are deleted, not ticked; git and DECISIONS.md hold the history.

**Line format:** `- [ID] status | label | file hint | needs: ID,ID | adr: N,N`
Status: `todo`, `doing`. Order within a section is build order. Rules: audit against `docs/PRINCIPLES.md` before any item; prepend a DECISIONS entry for real choices; delete the line when done.

## Now: publish P44
- [P44] doing | Publish P44: read draft end to end (check #7 diagram renders monospace), add LinkedIn first-comment link, add BLOG_INDEX row, delete Langfuse sessions sess-gate-check / sess-route-check / sess-after-fix | docs/blog/drafts/draft_2026-11-21.md | needs: — | adr: 264

## Next build: ManagedAgentHarness (gates AgentBench and flywheel)
First check whether managed-agent model-calling paths are spend-gated; apply Entry 226 constraints (bounded context, knowledge at rest) before the interface is set.
- [H9] todo | AgentPrepStage: policy load + credential provisioning (confirm_isolation wired) | chatbot/agents/managed/harness.py | needs: P44 | adr: 221,226
- [H10] todo | AgentExecuteStage: extract tool loop from ManagedAgent.run(); supervisor relay reused | chatbot/agents/managed/harness.py | needs: H9 | adr: 221
- [H11] todo | AgentAuditStage: output scan + token budget + credential expiry | chatbot/agents/managed/harness.py | needs: H10 | adr: 221
- [H12] todo | AgentSynthStage: write report + signal EventBroker | chatbot/agents/managed/harness.py | needs: H11 | adr: 221
- [H13] todo | ManagedAgentHarness stage pipeline + BlockedAgentError | chatbot/agents/managed/harness.py | needs: H12 | adr: 221

## After the harness
- [AB-A] todo | AgentBench A: 4-primitive corpus (P39 seed + 4 other frameworks) | docs/agentbench/corpus/ | needs: H13 | adr: 233
- [AB-B] todo | AgentBench B: primitive scorer (binary coverage + gap classification) | .claude/skills/agentbench/scripts/agentbench-run.py | needs: AB-A | adr: 233
- [AB-C] todo | AgentBench C: run 5 frameworks; leaderboard entry for TA fleet | docs/agentbench/results/ | needs: AB-B | adr: 233
- [AB-D] todo | AgentBench D: publish leaderboard + TA entry; blog draft | docs/blog/drafts/ | needs: AB-C | adr: 233
- [FW-A] todo | Flywheel A: BouncerStage context-hash parity check | chatbot/harness/stages.py | needs: H13 | adr: 227
- [FW-B] todo | Flywheel B: SUCCEEDED auto-staging to synthetic MMD queue | chatbot/modules/perspective_runner.py | needs: FW-A | adr: 227
- [FW-C] todo | Flywheel C: continuous red-team harness | .claude/skills/check-detect/scripts/check-detect.py | needs: FW-A | adr: 227
- [FW-D] todo | Flywheel D: GymProposer, Brier-triggered harness edit candidates | chatbot/api/routes/gym.py | needs: FW-C | adr: 227
- [CB-1] todo | CoreBouncer: extract hardening layers from ManagedAgent base | chatbot/agents/managed/bouncer.py | needs: H13 | adr: 222
- [CB-2] todo | Cross-fleet gating rule: report-layer-only signal between fleets | chatbot/agents/managed/bouncer.py | needs: CB-1 | adr: 222
- [CB-3] todo | Human-in-the-loop threshold (confidence < 0.7 queues for approval) | chatbot/agents/managed/bouncer.py | needs: CB-2 | adr: 222
- [FL-1] todo | Second fleet agent (scope TBD) | chatbot/agents/managed/ | needs: CB-3
- [FL-2] todo | Fleet manifest report/fleet/<fleet_id>/manifest.json | chatbot/agents/managed/reporter.py | needs: FL-1
- [FL-3] todo | EventBroker events fleet_started / agent_triggered / fleet_blocked | chatbot/harness/event_broker.py | needs: FL-2
- [FL-4] todo | Fleet-level token budget across agent runs | chatbot/agents/managed/reporter.py | needs: FL-3
- [FL-5] todo | FleetCoordinator: trigger type to fleet | chatbot/agents/managed/coordinator.py | needs: FL-4

## TA-firewall and verifier hardening
- [FW-H] todo | TA-firewall hardening: steer-vs-block experiment, per-caller keys, run events for boxing/taco/perspective, verify_api_key on /analyze/artifact, MCP/CLI entry points, full_moe weight decision, new DETECT rules, TMeval Phase 3 throttle/replay cases | chatbot/harness/spend_gate.py + policies/soc_detection_rules.yaml | needs: H13 | adr: 264
- [TP-1] todo | TAprover remaining: cvss_validity, control_existence, exporter M-IDs | .claude/skills/taprover/ | needs: — | adr: 249,262,263

## Backlog (not priority)
- [V-1] todo | Verifier source-existence check: a claim's cited Entry / commit / test / file must exist (enforcement side of PRINCIPLES #10) | scripts/validation/ + taprover | needs: TP-1
- [V-2] todo | More --prove-docs claim types: route counts (18 spend routes), rule counts (70 DETECT) against code | taprover | needs: V-1
- [V-3] todo | Bring .claude/graphs/skills.mmd fully current | .claude/graphs/skills.mmd | needs: —
- [LS-1] todo | LangSmith spike (user rotates key into .env as LANGSMITH_API_KEY; check variable names only) | — | needs: P44
- [EW-1] todo | EvalWatch: ingest AI Risk Explorer evals catalogue to DETECT coverage view; gated on FW-D | chatbot/modules/evalwatch.py | needs: FW-D | adr: 253
- [SQ-1] todo | Sequence Entries 243/244 (TMbench-gap pipeline roadmap, tiered arch weighting) into items | docs/DECISIONS.md | needs: — | adr: 243,244
- [EX-1] todo | ta-export version-stamp {model_id, routing_mode, skills_context} | chatbot/modules/ta_exporter.py | needs: — | adr: 225
- [EX-2] todo | skill-master: multi-location inventory + override detection + change-triggered re-scan | .claude/skills/skill-master/ | needs: EX-1 | adr: 225
- [EX-3] todo | Open Factory: ta-export reproducibility gap + interoperability steps | docs/DECISIONS.md | needs: EX-1 | adr: 224
- [MX-1] todo | ATT&CK v20.1 migration (needs approval); ATLAS upstream check | chatbot/data/ | needs: —
- [MX-2] todo | Fix 3 pre-existing unit test failures | tests/unit/ | needs: —
- [MX-3] todo | omnigent scratch experiment (check telemetry opt-out first) | — | needs: —
- [FV-1] todo | TAfutureview ("see far, fight far, defend smart"): forward view per architecture from data TA holds (ATT&CK catalog drift, brain gap patterns, ingested eval catalogue). Every forward claim carries confidence + basis (observed trend / upstream forecast / TA model); predictions scored later against outcomes via Brier. Audit vs PRINCIPLES 3,4 first. Inspired by gods-eye-view (fused live layers, shows others' forecasts) | chatbot/modules/ (TBD) | needs: FW-D,EW-1
- [BL-1] todo | Blog candidate: "one home per kind of information" (roadmap hygiene). Before snapshot saved in memory (project_roadmap_hygiene.md); write after a few weeks of use | docs/blog/drafts/ | needs: —
