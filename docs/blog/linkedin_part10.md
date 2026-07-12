# LinkedIn Post — Part 10

---

I've been building a side project: an AI-assisted threat modelling tool I work on in my own time.

A few months back I added a quality flywheel: three gears that keep each other honest. Build produces a threat model. Label is an independent model that reads only the diagram and marks what should have been found. Score compares the two. Gaps become the next repair list.

I ran it across 26 architecture diagrams. Then pointed it at something new: an agentic AI system.

**Score: 79/100 Solid.**

Not bad. But the interesting part was *why* it wasn't higher. Three gears were failing at once, in three different ways.

**Gear 1:** The engine had no vocabulary for AI nodes. It knew `server`, `database`, `network`. It didn't know `Agent Orchestrator`, `Tool Registry`, `Prompt Manager`. 47% of nodes untouched by any attack path.

**Gear 3:** After I fixed node coverage, hop coverage went *down*. From 52% to 31%. More paths found, more hops exposed, and the coverage checker didn't know that `human_oversight` spans detect + respond, or that `content_moderation` covers three zero-trust layers, not one.

**The critics:** The Blackhat critic had been referencing ATLAS techniques in its reasoning for months. The ground truth contained zero ATLAS entries. It was reasoning about a threat layer that didn't exist in the data it was reviewing.

Three fixes later: node coverage 47% → 89%, validation failures 89 → 18, hop coverage 31% → 91%, overall score 79 → **85 Excellent**.

The flywheel didn't tell me what to fix. It showed me the score. I had to figure out why it was low.

That's the part I didn't expect when I started: the benchmark teaches you what it doesn't know. Every time you fix something, the next gap surfaces.

The flywheel still needs to turn. A benchmark without a feedback loop is just a score. But the speed and smoothness of the turning depend on something I can't build alone: real-world feedback from people who've tried to apply this, disagreed with a finding, or spotted something the engine missed entirely.

If you work in threat modelling or architecture review, I'd genuinely appreciate your take. What would make a tool like this actually useful to you?

---

Full write-up in Part 10. Link in comments.

---

*#ThreatModelling #CyberSecurity #MITRE #BuildInPublic #SideProject*
