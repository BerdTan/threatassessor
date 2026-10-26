#!/usr/bin/env python3
"""
recall.py — Synthesise outstanding priorities from MEMORY.md + DECISIONS.md.

Outputs a sequence-ordered gist:
  - Done count (collapsed)
  - Open priorities expanded into their build steps with file hints
  - NEXT SESSION pointer
  - New items from recent DECISIONS.md entries not yet in memory
  - Concrete first step (first incomplete step in sequence)

Update PRIORITY_STEPS after any dependency analysis session.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MEMORY_DIR = Path.home() / ".claude/projects/-mnt-c-BACKUP-DEV-TEST/memory"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
DECISIONS_FILE = ROOT / "docs/DECISIONS.md"

# ── Sequence config ───────────────────────────────────────────────────────────
# Each entry: (step, priority_num, label, file_hint, depends_on_step)
# Update this after a dependency analysis session.
# Mark a step done by prepending ✅ to its label.
#
# Dependency chain (2026-10-26, reordered 2026-10-26):
#   P37 (TA Perspective) — DONE (6f1f39b); blog P37 published
#   P38 (Managed agent fleet) — DONE (87e8a1e); blog P38 published
#   OpenShell supervisor + fleet tool registry (Entries 228–230) — DONE (1a8cfd9, 48c083f, 083fb38)
#     supervisor relay / circuit breaker / RunCredentials / confirm_isolation now in base.py
#     fleet tool registry + CISO posture endpoint live; check-managed-agents skill 29/29 PASS
#   Fleet Foundation (Entry 221) — ManagedAgentHarness harness.py steps 9–13 still needed
#     (circuit breaker + confirm_isolation already landed in base; harness.py wraps them as stages)
#   Recursive flywheel (Entry 227) — Steps A–D; starts after step 13 (harness exists)
#     Step A (BouncerStage context-hash) only needs existing BouncerStage — no fleet layer required
#     Runs in parallel with CoreBouncer track (14–16) and fleet build (17–21)
#   Fleet Security (Entry 222) — CoreBouncer; after Foundation (step 13)
#   Fleet Service — second agent; lands clean into harness
#   Fleet Report — fleet manifest + EventBroker fleet events; after Service
#   FleetCoordinator — only when third agent is scoped
PRIORITY_STEPS = [
    # ── Priority 33/34/35 — DONE ─────────────────────────────────────────────
    (1,  33, "✅ DETECT-ABU 6 rules + MCPAccessLogger",  "policies/soc_detection_rules.yaml",         None),
    (2,  34, "✅ Jev Phase 2: GT noul ❻ + CISO posture ❽", "ground_truth_generator.py + ta_exporter.py", 1),
    (3,  35, "✅ Per-action MCP Jev noul gate ❾",        "mcp_server/server.py",                      None),
    # ── Priority 37 — TA Perspective — DONE (6f1f39b) ────────────────────────
    (4,  37, "✅ GroupCampaignMatcher + STIX cache",              "chatbot/modules/group_campaign_matcher.py",  None),
    (5,  37, "✅ Hook into ground_truth Phase 3B",                "chatbot/modules/ground_truth_generator.py",  4),
    (6,  37, "✅ PerspectiveRunner + vocabulary gap fix",         "chatbot/modules/perspective_runner.py",      5),
    (7,  37, "✅ SSE route + GET /perspective/scenarios/{arch}",  "chatbot/api/routes/perspective.py",          6),
    (8,  37, "✅ Kill chain canvas + pause/resume toolbar",       "chatbot/api/static/js/dashboard.js",         7),
    # ── Priority 40 — OpenShell supervisor model (Entries 228–230) — DONE ────
    (29, 40, "✅ OpenShell supervisor: allowed_tools/allowed_endpoints/supervisor relay/circuit breaker/RunCredentials/confirm_isolation (Entry 228)", "chatbot/agents/managed/base.py + registry.py", None),
    (30, 40, "✅ Fleet tool registry + CISO posture endpoint + check-managed-agents skill 29/29 (Entries 229–230)", "chatbot/agents/managed/tool_registry.py + platform.py", 29),
    # Blog P39 is now unblocked — step 30 is done
    (31, 40, "📝 Draft P39 blog — 'The Four Primitives: What OpenShell Teaches TA About Rogue Agents'", "docs/blog/drafts/", 30),
    # ── Priority 40 — ManagedAgentHarness harness.py (Entry 221) ─────────────
    # circuit breaker + RunCredentials + confirm_isolation are already in base.py (step 29);
    # harness.py wraps them into formal stage objects for the fleet pipeline.
    (9,  40, "AgentPrepStage — policy load + credential provisioning (confirm_isolation wired)", "chatbot/agents/managed/harness.py",  31),
    (10, 40, "AgentExecuteStage — extract tool loop from ManagedAgent.run(); supervisor relay reused", "chatbot/agents/managed/harness.py", 9),
    (11, 40, "AgentAuditStage — output scan + token budget + credential expiry", "chatbot/agents/managed/harness.py", 10),
    (12, 40, "AgentSynthStage — write report + signal EventBroker", "chatbot/agents/managed/harness.py", 11),
    (13, 40, "ManagedAgentHarness stage pipeline + BlockedAgentError (circuit breaker already in base)", "chatbot/agents/managed/harness.py", 12),
    # ── Priority 41 — Recursive improvement flywheel (Entry 227) ─────────────
    # Starts after step 13 (harness exists); runs in parallel with CoreBouncer + fleet build.
    # Step A only needs existing BouncerStage — no fleet layer required.
    (23, 41, "Step A — BouncerStage context-hash parity check",  "chatbot/harness/stages.py",             13),
    (24, 41, "Step B — SUCCEEDED auto-staging → synthetic MMD queue", "chatbot/modules/perspective_runner.py", 23),
    (25, 41, "Step C — Continuous red-team harness (known-evasion scenarios, live pipeline)", ".claude/skills/check-detect/scripts/check-detect.py", 23),
    (26, 41, "Step D — GymProposer: Brier-triggered harness edit candidates", "chatbot/api/routes/gym.py", 25),
    # ── Fleet Security — CoreBouncer (Entry 222) ──────────────────────────────
    (14, 40, "CoreBouncer: extract hardening layers from ManagedAgent base", "chatbot/agents/managed/bouncer.py", 13),
    (15, 40, "Cross-fleet gating rule: report-layer-only signal between fleets", "chatbot/agents/managed/bouncer.py", 14),
    (16, 40, "Human-in-the-loop threshold (confidence < 0.7 → queue for approval)", "chatbot/agents/managed/bouncer.py", 15),
    # ── Fleet Service + Report + Coordinator ─────────────────────────────────
    (17, 40, "Second fleet agent (scope TBD)",                    "chatbot/agents/managed/",               16),
    (18, 40, "Fleet manifest: report/fleet/<fleet_id>/manifest.json", "chatbot/agents/managed/reporter.py", 17),
    (19, 40, "EventBroker: fleet_started/agent_triggered/fleet_blocked", "chatbot/harness/event_broker.py", 18),
    (20, 40, "Fleet-level token budget across agent runs",         "chatbot/agents/managed/reporter.py",    19),
    (21, 40, "FleetCoordinator: routes trigger type → correct fleet", "chatbot/agents/managed/coordinator.py", 20),
    # ── Freestanding: ta-export + skill-master (Entry 224/225) ───────────────
    (27, 0,  "ta-export version-stamp: {model_id, routing_mode, skills_context} into bundle", "chatbot/modules/ta_exporter.py", None),
    (28, 0,  "skill-master: multi-location inventory + override detection + change-triggered re-scan (Entry 225)", ".claude/skills/skill-master/", 27),
    # Blog P40 unblocked after flywheel D + skill-master
    (32, 0,  "📝 Draft P40 blog — recursive flywheel + skill-master + CISO-as-partner story", "docs/blog/drafts/", 28),
    # ── Freestanding: Open Factory (Entry 224) — needs sequencing ────────────
    (33, 0,  "Open Factory (Entry 224): define ta-export reproducibility gap + interoperability steps", "docs/DECISIONS.md", 27),
    # ── Freestanding: recall ADR auto-sequencing (Step 22) ───────────────────
    (22, 0,  "✅ recall skill: ADR auto-scan now live — open design-intent entries surface automatically", ".claude/skills/recall/scripts/recall.py", None),
]

# Maps DECISIONS entry number → list of step numbers that implement it.
# Used to cross-reference the ADR panel with the build sequence.
ADR_TO_STEPS: dict[int, list[int]] = {
    221: [9, 10, 11, 12, 13],   # ManagedAgentHarness stages
    222: [14, 15, 16],           # CoreBouncer
    224: [33],                   # Open Factory (step = define implementation)
    225: [27, 28],               # ta-export version-stamp + skill-master
    226: [9],                    # shared knowledge constraints → harness step
    227: [23, 24, 25, 26],       # recursive flywheel Steps A–D
    228: [29],                   # OpenShell supervisor (done)
    229: [30],                   # fleet tool registry (done)
    230: [30],                   # check-managed-agents (done)
}

# ── helpers ───────────────────────────────────────────────────────────────────

def read_file(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def extract_priorities(memory: str) -> list[tuple[int, str, bool]]:
    """Return list of (num, text, done) from the '## Current priorities' section."""
    section = re.search(r"## Current priorities.*?(?=\n##|\Z)", memory, re.S)
    if not section:
        return []
    items = re.findall(r"(\d+)\.\s+(.*)", section.group())
    result = []
    for num, text in items:
        stripped = text.strip()
        done = (
            (stripped.startswith("~~") and stripped.endswith("~~"))
            or stripped.startswith("✅")
            or re.match(r"^1[–-]\d+\.", stripped) is not None
        )
        clean = re.sub(r"~~(.+?)~~", r"\1", stripped).strip()
        result.append((int(num), clean, done))
    return result


def extract_recent_decisions(decisions: str, max_sessions: int = 2) -> list[str]:
    """Pull open/pending items from the last N session blocks in DECISIONS.md."""
    sessions = re.split(r"(?=^## Session)", decisions, flags=re.M)
    open_items = []
    seen = set()
    target_kws = ["blog candidate", "planned", "next steps", "todo", "pending"]
    skip_kws = ["why now", "depends on", "prerequisite", "recursive", "answer arc", "alternatives rejected"]
    for session in sessions[1 : max_sessions + 1]:
        for line in session.splitlines():
            stripped = line.strip()
            if not stripped or len(stripped) < 10:
                continue
            low = stripped.lower()
            if any(kw in low for kw in skip_kws):
                continue
            if any(kw in low for kw in target_kws):
                if not re.match(r"^[-*#]|^\*\*|^Entry", stripped):
                    continue
                clean = re.sub(r"^[-*#]+\s*|\*\*", "", stripped).strip()
                if len(clean) > 100:
                    clean = clean[:97] + "..."
                key = clean.lower()[:40]
                if clean and key not in seen:
                    seen.add(key)
                    open_items.append(clean)
    return open_items


def extract_open_adrs(decisions: str) -> list[tuple[int, str, str]]:
    """
    Return (entry_num, title, status) for every entry whose Status line
    contains 'design intent', 'pending', or 'design constraint'.
    """
    open_adrs = []
    entries = re.split(r"(?=^### Entry \d+)", decisions, flags=re.M)
    for block in entries:
        m = re.match(r"^### Entry (\d+) — (.+)", block)
        if not m:
            continue
        num = int(m.group(1))
        title = m.group(2).strip()
        status_m = re.search(r"^\*\*Status:\*\*\s*(.+)", block, re.M)
        if not status_m:
            continue
        status = status_m.group(1).strip()
        low = status.lower()
        if any(kw in low for kw in ("design intent", "pending", "design constraint")):
            open_adrs.append((num, title, status))
    return open_adrs


def adr_step_ref(entry_num: int) -> tuple[bool, str]:
    """
    Return (in_sequence, display_ref) for an ADR.
    display_ref is a short string like "steps 9–13" or "step 33 (needs sequencing)".
    """
    steps = ADR_TO_STEPS.get(entry_num)
    if steps is None:
        # Fall back to label scan
        entry_str = str(entry_num)
        for _, _, label, _, _ in PRIORITY_STEPS:
            if f"Entry {entry_str}" in label or f"({entry_str})" in label:
                return True, "in sequence (label ref)"
        return False, "no steps defined yet"

    if len(steps) == 1:
        ref = f"step {steps[0]}"
    elif steps[-1] == steps[0] + len(steps) - 1:
        ref = f"steps {steps[0]}–{steps[-1]}"
    else:
        ref = "steps " + ", ".join(str(s) for s in steps)

    # Check whether all mapped steps are done (have ✅ prefix)
    done_set = {s for s, _, lbl, _, _ in PRIORITY_STEPS if lbl.startswith("✅")}
    all_done = all(s in done_set for s in steps)
    marker = "✅ done" if all_done else "⬜ open"
    return True, f"{ref} [{marker}]"


def in_priorities(text: str, priorities: list[tuple[int, str, bool]]) -> bool:
    low = text.lower()
    for _, p_text, _ in priorities:
        if low[:30] in p_text.lower() or p_text.lower()[:30] in low:
            return True
    return False


def priority_is_done(pnum: int, priorities: list[tuple[int, str, bool]]) -> bool:
    for n, _, done in priorities:
        if n == pnum:
            return done
    return False


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    memory = read_file(MEMORY_FILE)
    decisions = read_file(DECISIONS_FILE)

    priorities = extract_priorities(memory)
    decision_items = extract_recent_decisions(decisions, max_sessions=2)
    open_adrs = extract_open_adrs(decisions)

    done = [(n, t) for n, t, d in priorities if d]
    open_pnums = {n for n, _, d in priorities if not d}

    # New items from DECISIONS not yet reflected in memory priorities
    new_items = [item for item in decision_items if not in_priorities(item, priorities)]

    lines = ["## Recall\n"]

    # Done (collapsed)
    if done:
        lines.append(f"**Done ({len(done)}):** " + ", ".join(str(n) for n, _ in done))

    # Open priorities — expanded into build steps, in sequence order.
    # Include a step when: its priority is open OR it is not yet done (no ✅ prefix),
    # so that undone sub-steps under a "done" parent priority still surface.
    open_steps = [
        (step, pnum, label, hint, dep)
        for step, pnum, label, hint, dep in PRIORITY_STEPS
        if pnum in open_pnums or pnum == 0 or not label.startswith("✅")
    ]
    # Drop steps that are individually marked done (✅) AND whose priority is closed,
    # to avoid re-listing already-finished work.
    open_steps = [
        (step, pnum, label, hint, dep)
        for step, pnum, label, hint, dep in open_steps
        if not (label.startswith("✅") and pnum not in open_pnums and pnum != 0)
    ]

    if open_steps:
        lines.append("\n**Build sequence (open):**")
        current_pnum = None
        for step, pnum, label, hint, dep in open_steps:
            done_marker = "✅" if label.startswith("✅") else "⬜"
            label = label.lstrip("✅").strip()
            # Group header when priority changes
            if pnum != current_pnum:
                p_label = f"Priority {pnum}" if pnum else "Freestanding"
                lines.append(f"\n  [{p_label}]")
                current_pnum = pnum
                pass  # blog steps are now explicit ⬜ steps in PRIORITY_STEPS
            dep_note = f"  ← needs step {dep}" if dep else ""
            lines.append(f"  Step {step:2d} {done_marker} {label}{dep_note}")
            lines.append(f"           → {hint}")

    # Open ADRs from DECISIONS.md — compact reference panel with step cross-refs
    if open_adrs:
        lines.append("\n**Open ADRs:**")
        for num, title, status in open_adrs:
            in_seq, step_ref = adr_step_ref(num)
            tag = f"→ {step_ref}" if in_seq else "⚠ no steps yet — needs sequencing"
            short_title = title if len(title) <= 65 else title[:62] + "…"
            lines.append(f"  Entry {num}  {short_title}")
            lines.append(f"           {tag}")

    # New from DECISIONS not yet in memory
    if new_items:
        lines.append("\n**From recent DECISIONS (not yet in memory):**")
        for item in new_items[:4]:
            lines.append(f"  • {item}")

    # Concrete next step: first ⬜ step in sequence
    first_open = next(
        ((step, label, hint) for step, pnum, label, hint, dep in open_steps
         if not label.startswith("✅")),
        None
    )
    if first_open:
        s, lbl, hint = first_open
        lines.append(f"\n**Next up:** Step {s} — {lbl}")
        lines.append(f"  → {hint}")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
