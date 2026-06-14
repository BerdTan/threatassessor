# When the Critics Disagree: ScrumMaster and the Art of Security Harmony

*Part 5 of the ThreatAssessor series. [Part 1](blog_draft.md) introduced the RAPIDS engine and three-critic MoE pipeline. [Part 2](blog_draft_part2.md) covered CloudPattern and SSP compliance. [Part 3](blog_draft_part3.md) exposed two structural blind spots and the feedback flywheel. [Part 4](blog_draft_part4.md) showed how StoryCaster reads the human journeys hidden in your diagram.*

Estimated reading time: ~7–9 minutes

**Hook:** Five security experts walk into your architecture review. They find nineteen problems — and none of them agree on what to fix first. Who breaks the deadlock? That is what ScrumMaster was built for.

---

**TL;DR (in one screen):**
- Running five security critics on the same architecture surfaces real friction — critics disagree, gaps compound, and confidence stalls at 68%.
- ScrumMaster reads all five critics at once, identifies structural impediments versus addressable gaps, and proposes a tiered action plan: apply controls now, then tackle the architecture changes.
- Harmony is not always reachable. When it is not, ScrumMaster signals a redesign and tells you what to add to the diagram — not just what to review.
- The result is a living ADR that closes the loop between finding and decision.

What you'll learn:
- Why critics naturally produce friction and why that friction is valuable, not broken.
- How ScrumMaster arbitrates between nineteen impediments to produce five actionable items.
- What "redesign signal" means in practice — and what to actually do next.
- How the ThreatModel/ADR is enhanced by SM findings without a full re-run.

Who should read this: security architects and risk owners who need a clear path from expert disagreement to executive decision.

---

## Five Experts, One Architecture, Nineteen Problems

The ServiceEntry architecture has been through a lot. In Part 4 it received user journey intelligence from StoryCaster — every attack path now carries a human story. In this part, we turn up the pressure: instead of one critic pass, we run all five in sequence and watch what happens.

The ServiceEntry v2 analysis starts from a clean position:

| Metric | Value |
|--------|-------|
| Overall risk score | 50/100 |
| Defensibility | 73/100 |
| Attack paths | 5 |
| Controls present | 7 |
| Controls missing | 17 |
| Base confidence (deterministic) | 77.1% |

Decent defensibility, mediocre risk, too many missing controls. The deterministic engine has done its job. Now five critics review the same findings independently — then as a group.

In plain language: the numbers show the system is OK but not safe. There are several ways an attacker could reach important data, and we lack enough controls to stop or detect those routes. The confidence score (77.1%) means the automated checks are reasonably consistent, but not definitive — human review may change that.

### What Each Critic Found

Running in Sequential mode (Architect → Tester → Red Team → Purple Team → Blackhat), each critic builds on the previous one's output:

| Critic | Score | Status | Confidence impact |
|--------|-------|--------|-------------------|
| 🏛️ Architect | 87/100 | MINOR_GAPS | −2% |
| 🔬 Tester | 94/100 | PASS | 0% |
| 🎯 Red Team | 45/100 | MINOR_GAPS | −3% |
| 🟣 Purple Team | 72/100 | NEEDS_REVIEW | −2% |
| ⚔️ Blackhat | 85/100 | MAJOR_GAPS | −5% |

**Final validated confidence: 68.2%** — down from 77.1%. A 9-point drop driven by three critics who independently reached the same conclusion from different angles: the architecture has structural exposure at its pivot nodes.

Layman's takeaway from the critic table: different reviewers look for different problems. A high Tester score means the mechanics (controls vs techniques) are correctly configured on paper, but the Red Team and Blackhat results show practical attack paths that still let an attacker move freely. The net effect: the system looks correct but can still be exploited in ways automated checks didn't flag.

The Tester scores near-perfect because the MITRE mappings and control placements are technically correct. The Red Team scores 45 because *correct mappings do not equal hard-to-exploit*. The Blackhat scores 85 — which sounds good — but signals MAJOR_GAPS because it found that every single one of the five attack paths shares three pivot nodes. One compromise fans out to all five.

This is the value of running multiple critics. The Tester passing does not mean you are safe. The Blackhat's major gaps are invisible to the Tester and only partially visible to the Red Team.

---

## The Friction Is Not a Bug

Nineteen impediments surface across five critics. Two are structural blindspots — the critics collectively cannot see them because they are outside every critic's rubric scope. The remaining seventeen are coverage gaps, unresolved recommendations, and contradictions.

Here is a sample of what the impediment analysis finds:

**Critical/high severity:**
- *Supply chain and third-party vendor risk assessment — all attack paths assume internal architecture.* No critic can assess what is not in the diagram.
- *Business continuity impact of security controls — implementing network segmentation would alter user-facing latency and session handling.* A security improvement that breaks user journeys is not an improvement.

**Coverage gaps (medium severity, recurring across critics):**
- No micro-segmentation between MobileApp, API Gateway, and backend services
- T1078 (Valid Accounts) attack surface is unmitigated across all five corroborated user journeys
- Detection baselines undefined — Purple Team cannot assess anomaly detection without user behaviour data

Nineteen impediments. Most unresolvable by adding controls alone. **This is when a human team would enter a long meeting and leave with a list of things to "review."**

ScrumMaster is built for exactly this moment.

---

## ScrumMaster: Negotiator, Not Just Summariser

The metaphor is deliberate. In software delivery, a Scrum Master does not write the code or define the product. They remove the impediments that block the team from moving forward — clarifying ambiguity, resolving conflicts, and sequencing work so the highest-value items get attention first.

In ThreatAssessor, ScrumMaster reads all five `ValidationResult` objects simultaneously — something no individual critic does — and runs a deterministic impediment analysis before calling a single LLM.

The harmony check asks: *can the majority of high-severity gaps be addressed with incremental controls, or do they require architectural changes?* For ServiceEntry v2:

> *"ScrumMaster found 19 impediments — all 19 are structurally unresolvable (2 critical/high severity). No impediments can be addressed with incremental controls alone. The action plan is tiered: immediate control additions first, then architectural decisions with concrete first steps."*

All nineteen unresolvable. This triggers the **redesign signal** — not a failure, but a deliberate output. It means running more critic rounds would not improve confidence. The architecture needs a structural change before re-evaluation will help.

Zero iterations. Zero re-triggering. ScrumMaster stops immediately and delivers a tiered plan instead.

---

## The Action Plan: Two Tiers, Five Items

Where a traditional report would produce a long list sorted by CVSS-equivalent severity — all labelled "high" — ScrumMaster produces five items in two explicit tiers.

### ⚡ Immediate: Apply Now, No Diagram Changes

Three items you can start today:

**1. Network segmentation at the MobileApp pivot node**
The MobileApp is the entry point for all five attack paths. A single mobile compromise fans out to User Database, Access Log Database, and Redis Cache simultaneously. Blackhat found this; Red Team confirmed it. Adding microsegmentation between MobileApp and the API Gateway layer — a firewall rule, a service mesh policy, a network zone boundary — closes the fan-out without touching the architecture diagram.
*Effort: days. Risk reduction: medium.*

**2. Micro-segmentation at the API Gateway**
T1059 command injection can spread laterally across all downstream services through the API Gateway pivot node. Purple Team flagged the detection gap; Blackhat confirmed the spread pattern. East-west traffic inspection here stops lateral movement before it reaches the database layer.
*Effort: days. Risk reduction: medium.*

**3. Multi-factor authentication across all API endpoints**
T1078 (Valid Accounts) is active on all five corroborated user journeys — MFA is missing and three critics raised it independently (Red Team, Purple Team, Blackhat). Every user story in the architecture involves an authentication hop. This is the single highest-coverage control available.
*Effort: days. Risk reduction: medium.*

Three controls. Days of effort each. No architectural redesign required. These can be tracked directly in the ADR using the `📋 Add to ADR` button — each item appends an `SM-ADR-XX` entry to `10_adr_report.md` with OPEN status, the rationale, and the first concrete step.

### 🏗️ Structural: Diagram Changes Required

Two items that require adding components to the architecture diagram and re-running analysis:

**4. Vendor Risk Assessment node**
Supply chain risk is invisible to all five critics because no vendor or external dependency appears in the diagram. The solution is not a policy document — it is a diagram node. Add `VendorRiskAssessment[Vendor Risk Assessment]` connected to the relevant service boundaries, then re-run. RAPIDS will generate attack paths through the vendor surface, and the critics will assess it.
*First step: Add `vendor_risk_assessment` node to the `.mmd` source file.*

**5. RTO/RPO targets per attack path criticality tier**
Implementing network segmentation and EDR creates latency and operational constraints that affect the availability model. Before committing to the Maximum Security tier, model the availability impact. Add BCP/DR controls to ADRs for HIGH/CRITICAL paths.
*First step: Map current attack paths to availability impact; add `recovery_time_objective` field to the top three ADRs.*

---

## The Confidence Picture

Starting at 77.1%, dropping to 68.2% after five critics, holding at 68.2% after ScrumMaster (no re-triggering attempted):

```
Foundation → 68.2%    (redesign signal — iteration would not help)
```

This is honest reporting. The architecture has real structural gaps that controls alone cannot close. The confidence will not improve to 90% until the diagram is updated and the critics re-run on the new architecture.

The RAPIDS engine also surfaced an engine improvement hint: the `insider_threat` category may be under-weighted (+20% suggested) based on the volume of lateral movement gaps the critics found. Applying this weight adjustment before the next analysis run will surface the pivot-node risk more prominently in the base score.

---

## What Makes This Different from a Pentest Report

A penetration test produces findings. ScrumMaster produces a **decision log**.

The difference is sequencing and ownership. A pentest finding says "API Gateway lacks authentication." The ScrumMaster action plan says "Implement OAuth2/JWT at API Gateway — this blocks T1078 across all five corroborated user journeys. First step: add the control to ADR-AP2 and assign an owner. Verify in the next Expert Review run."

The `10_adr_report.md` now contains:

```
## SM-ADR-01 [HIGH] — Mobile App network segmentation
Status: OPEN — added via ScrumMaster action plan
Added: 2026-06-14
First step: Deploy microsegmentation at MobileApp→APIGateway boundary

## SM-ADR-02 [HIGH] — API Gateway micro-segmentation
...
```

These entries persist across sessions. When the architecture is updated and the analysis re-runs, the ADR entries are already in place. The Tester critic will validate whether the control was actually implemented. Confidence moves or it does not — and you know why.

---

## The Improvement Tiers, Updated

After ScrumMaster runs, the Improvement Tiers in Expert Review are enhanced with SM items:

| Tier | Result |
|------|--------|
| ⚡ Quick Wins | 3 items, 4–6 weeks — **Practical: YES** |
| ⭐ Recommended | 5 items, 4–6 weeks — **Practical: YES** |
| 🔒 Maximum | 5 items, 3–6 months — **Practical: MAYBE** |

The Quick Wins tier closes the gap from risk 50 → 18. The Maximum tier reaches risk 8 — near the theoretical floor — but carries high operational complexity and significant changes to user workflows. The ScrumMaster action plan sits above this: it tells you what to do *before* entering the tier decision. Apply the immediate controls regardless of which tier you select.

Caveat: Timelines are indicative and will vary by organisation size, scope, and resource availability. Treat them as planning guidance, not a fixed deliverable schedule.

---

## What the Performance Numbers Say

For readers interested in the engineering:

The ServiceEntry v2 Expert Review ran against **Claude Sonnet 4 via AWS Bedrock** (`us.anthropic.claude-sonnet-4-20250514-v1:0`) in Sequential mode. Here are the actual numbers from a full fresh run:

| Component | Tokens | Cost | LLM latency | t/s |
|-----------|-------:|-----:|------------:|----:|
| 🏛️ Architect | 5,839 | $0.0175 | 20.4s | 286 |
| 🔬 Tester | 8,867 | $0.0266 | 16.0s | 553 |
| 🎯 Red Team | 3,886 | $0.0117 | 19.6s | 198 |
| 🟣 Purple Team | 2,194 | $0.0066 | 11.6s | 189 |
| ⚔️ Blackhat | 2,782 | $0.0083 | 11.3s | 246 |
| 🎼 Orchestrator synthesis | 7,775 | $0.0233 | 33.6s | 231 |
| 🧩 ScrumMaster | 1,427 | $0.0043 | 10.7s | 133 |
| **Total** | **32,770** | **$0.098** | **124s** | |

The Orchestrator is the most expensive single component — not because it runs the most complex analysis, but because its prompt is the largest: it receives the full output of all five critics simultaneously to synthesise consensus. At 33.6 seconds it is also the slowest single call.

**ScrumMaster: one LLM call, the cheapest row in the table.** At 1,427 tokens and $0.004, it is an order of magnitude cheaper than any critic. It runs a single call to translate the 19 impediments into a concrete, first-step-ready action plan. The token count is low because it works from a compact structured summary of the impediment list — not the full critic outputs.

A note on when ScrumMaster does and does not call the LLM: on ServiceEntry v2 all 19 impediments were structurally unresolvable, which triggers an early *redesign signal* path that skips the LLM and produces the tiered plan deterministically. The numbers above were captured by running ScrumMaster on the completed assessment with the harmony gate bypassed — a controlled measurement run to get representative numbers. In production use on this architecture, ScrumMaster correctly returns the redesign signal with zero LLM spend. For architectures where fewer than half the critical/high impediments are unresolvable, the harmony check passes and ScrumMaster uses its full LLM path: two calls (proposal formulation + action plan), typically 2,000–4,000 tokens each.

**$0.098 for the complete seven-component pipeline.** Wall-clock time was 124 seconds in Sequential mode, dominated by waiting for each LLM call in turn. Switching to Parallel mode cuts wall-clock to roughly 40–50 seconds with no change in token spend, since all five critics run concurrently instead of sequentially.

The Harness tab in the dashboard shows this breakdown live after every Expert Review run — per-row tokens, cost, LLM latency, wall-clock time, and tokens/second efficiency — with automatic hints if the slowest critic is pulling the pipeline disproportionately or if token usage is high enough to warrant prompt trimming.

---

## What Comes Next

The ServiceEntry architecture has a clear path:

1. Apply the three immediate controls (microsegmentation, east-west inspection, MFA) — days of effort, no diagram change
2. Add `vendor_risk_assessment` and RTO/RPO nodes to the `.mmd` source file
3. Re-run analysis — RAPIDS will find new attack paths through the updated diagram
4. Re-run Expert Review — critics will assess the new coverage
5. ScrumMaster will re-harmonise — if the structural gaps are addressed, confidence will improve toward the 90% target

This is the loop. Architecture → Analysis → Critics → ScrumMaster → ADR → Architecture. Each cycle tightens the diagram and narrows the gap.

Harmony is not a one-time achievement. It is a rhythm.

---

*Coming in Part 6: QualityChecker — before the MoE critics run, we score the deterministic foundation itself. How coherent are the attack paths? Do the controls map to actual techniques? Are the RAPIDS scores calibrated? A silent pass through a broken baseline produces confident-looking results on a shaky foundation.*

---

**About this series:**
Each part is grounded in real analysis output from the chosen architecture - a system modelled as a Mermaid diagram. No synthetic examples. The numbers, the impediments, and the arbitration shown here are from an actual run.

ThreatAssessor is an exploration attempt into AI-assisted security architecture analysis. All analysis is advisory - it augments, not replaces, human security judgment.


*ThreatAssessor uses MITRE ATT&CK® (MITRE Corporation), MITRE ATLAS™ (MITRE Corporation), the ARC Framework (GovTech Singapore), CSA CAVEAT (Cloud Security Alliance, CC0-1.0), CSA CCM v4.1 → ATT&CK mapping (Center for Threat-Informed Defense, Apache 2.0), CTID KEV→ATT&CK mapping (Center for Threat-Informed Defense, Apache 2.0), CISA Known Exploited Vulnerabilities catalog (CISA, public domain), and Singapore Government SSP data from the published ICT&SS Security Standards for Providers catalog.*
