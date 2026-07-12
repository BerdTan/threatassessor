# LinkedIn Post — Part 10

---

We built a quality flywheel for AI-assisted threat modelling.

Three gears: **Build** (engine produces a threat model), **Label** (independent model marks what should have been found), **Score** (compare the two, gaps become the repair list).

We ran it on 26 architecture diagrams. Then we pointed it at something it had never seen: an agentic AI system.

**The score came back: 79/100 Solid.**

Respectable. But when we looked at why it wasn't higher, we found three simultaneous failures — in three different gears.

**Gear 1 (Build):** The engine had no vocabulary for AI nodes. `server`, `database`, `network` — it knew those. `Agent Orchestrator`, `Tool Registry`, `Prompt Manager` — zero keyword matches. 47% of nodes untouched by any attack path.

**Gear 3 (Score):** After fixing node coverage, hop coverage went *down*. From 52% to 31%. Because the coverage checker inferred zero-trust layers from control names — and it didn't know that `human_oversight` means detect + respond, or that `content_moderation` covers three layers, not one.

**The critics vs. the ground truth:** Our Blackhat critic had been reasoning about ATLAS techniques (AML.T0044, AML.T0051) for months. The ground truth contained zero ATLAS entries. The critics were reasoning about a threat layer that didn't exist in the data they were reviewing.

Three gears. Three fixes. One architecture.

After: node coverage 47% → 89%, validation failures 89 → 18, hop coverage 31% → 91%, overall 79 → **85 Excellent**.

The flywheel didn't ask us to fix any of this. It showed us the score. We figured out why it was low. That's its job.

---

The full write-up is in Part 10 of the series — link in comments.

What I keep finding: the most useful thing a benchmark can do is *not* confirm what's working. It's surface what you forgot to look for.

---

*#ThreatModelling #AISecurityEngineering #MITRE #ATLASFramework #BuildInPublic*
