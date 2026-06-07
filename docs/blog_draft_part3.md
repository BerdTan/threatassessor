# When "Good Enough" Is Not Enough: Teaching a Threat Assessor to See What It Couldn't

*Part 3 of the ThreatAssessor series. [Part 1](blog_draft.md) covered the RAPIDS deterministic engine and the original three-critic MoE pipeline. [Part 2](blog_draft_part2.md) covered CloudPattern — CSP-aware threat intelligence via CAVEAT, CCM, and Singapore SSP. This article covers how we challenged our own assumptions about assessment quality, found two structural blind spots in a five-critic system, and built a flywheel that keeps finding them.*

---

**TL;DR:** After building a threat assessor with three independent AI critics, a confidence waterfall, and MITRE-grounded synthesis, we asked the uncomfortable question: *what can't any of them see?* The answer was two entire dimensions of threat — the defender's visibility into an attack, and chains that only become possible when multiple paths share infrastructure. We built two new critics to address them, then built a mechanism to keep asking the same question.

What you'll learn:
- Why three independent critics can all agree and still miss the same things.
- How "assume breach" thinking changes what controls you recommend, not just whether you flag a gap.
- What pivot-diverge chains are, why per-path analysis is structurally blind to them, and why that matters in production architectures.
- How a reflection flywheel keeps challenging "good enough."

Who should read this: security architects who want more than a checklist, engineers building AI assessment pipelines, and anyone who has wondered whether their threat model covers what a real attacker would actually do.

---

## The Problem with Agreement

By the end of Part 2, ThreatAssessor had a working five-tab dashboard, a deterministic RAPIDS engine, and three LLM critics running in sequence:

1. **Architect** — is the design structurally sound? Are there unmodelled threats? Are the ADR decisions complete?
2. **Coverage Auditor** — are the MITRE technique mappings accurate? Do the recommended controls actually address the mapped techniques?
3. **Exploit Analyst** — is this architecture actually hard to attack? Score the exploit difficulty across every path.

Three critics, three lenses, cross-referenced in sequential mode so each sees the prior's output. Confidence waterfall from 99.5% base. MITRE-grounded synthesis to prevent hallucination. By any reasonable measure, this was a well-engineered assessment pipeline.

Then we ran it on a production-class architecture — a 20-node system with six attack paths, an API Gateway, SIEM integration, and a mix of cloud and on-premises components — and looked at the output not as a report but as a question:

*If a real attacker executed AP-3 successfully, would anyone know?*

The three critics had no answer. Not because the answer was contested or uncertain. Because not one of them was asking the question.

---

## Blind Spot One: The Defender's View

Every finding from the original three critics was written from the attacker's perspective. Can this path be traversed? How hard is it? What controls reduce the probability? These are correct and important questions. They're also only half the conversation.

The other half is: *when the attack succeeds, what does the defender see?*

A path can be perfectly modelled, have every hop mapped to a MITRE technique, have controls in place, and still be silently exploitable if none of those controls produce an observable signal. Prevention and detection are not the same thing. An organisation with strong prevention but no detection is operating on the assumption that controls never fail — which is the assumption that attacker dwell time of 200 days (the real-world median) disproves every year.

We called the new critic **Purple Team** — the name borrowed from the practice of red and blue teams working together to improve detection, not just find and fix vulnerabilities.

Purple Team evaluates the same architecture through three lenses that the first three critics structurally cannot apply:

**Lens A — Coverage:** Does every MITRE technique across all attack paths have at least one control in `control_recommendations`? Not a prevent control. Any control. This catches techniques that are mapped correctly (so the Coverage Auditor is satisfied) but entirely undefended — no mitigation, no detection, no response.

**Lens B — Assume Breach:** For each node in each attack path, assume the attacker is already there. Does the onward path have at least one detection control — SIEM, EDR, IDS, logging, anything that would make the breach observable? Prevention-only downstream means the attacker dwell time on that node is theoretically unlimited. This is the most common gap we found in test architectures: paths where every hop had a prevent control but not a single node produced a log that a SOC analyst could act on.

**Lens C — SOC Operability:** For every CRITICAL or HIGH path, can a SOC analyst actually trace an indicator of attack or indicator of compromise through the path hop by hop? And are the ADR decisions internally consistent — does an ADR that recommends a control for a node actually cover the techniques at that node in `control_recommendations`? A hollow ADR is worse than no ADR: it creates the impression of coverage where none exists.

The scoring is forward (higher = better), which makes it consistent with how a defender would read the results — the Coverage Auditor and Exploit Analyst use forward and inverted scales respectively; Purple Team joins the Coverage Auditor on the defender-forward side.

What changed in reports after adding Purple Team was not the list of techniques or the list of controls. It was the *framing* of what "covered" means. An architecture that scored 96% confidence from the original three critics sometimes came back from Purple Team with a coverage score of 61% — not because the controls were wrong, but because most of them were prevention-only, and the detection layer was nearly invisible.

---

## Blind Spot Two: The Cross-Path Problem

The second blind spot is structural. It cannot be fixed by changing what any individual critic asks — it requires a new unit of analysis entirely.

Every critic in the pipeline evaluates one attack path at a time. AP-1 gets assessed. AP-2 gets assessed. AP-3 gets assessed. Each assessment is independent: the controls in AP-2 don't affect the score for AP-3, and vice versa. This is correct when paths are truly independent. It becomes incorrect the moment paths share infrastructure.

Consider a production architecture where AP-1 runs `External User → API Gateway → AuthService → UserDB` and AP-3 runs `External User → API Gateway → AccessControlAPI → DoorController`. The API Gateway appears in both. From a per-path perspective, it's hardened on AP-1 (has rate limiting and WAF) and hardened on AP-3 (has input validation). From a per-path perspective, the architecture is well-controlled.

From a cross-path perspective: an attacker who compromises the API Gateway in AP-1 is already positioned to pivot into AP-3 — not by traversing the AP-3 path from the start, but by jumping from the shared node directly to the AP-3 downstream targets. The WAF and rate limiting on AP-1 won't stop this pivot. The input validation on AP-3 won't see it coming. Both controls were placed to address per-path traversal. Neither was placed to address what happens when the shared node is already owned.

We called this a **pivot-diverge chain**: a shared node (the pivot) that fans out to multiple distinct downstream targets (the diverge). The chain is the composite attack that becomes possible when the pivot is compromised, regardless of which path brought the attacker there.

The **Blackhat critic** was built specifically to find these. It runs last — after all four prior critics have written their findings — because it needs two things that only exist after the full pipeline has run: the complete set of findings from every prior critic, and Purple Team's detection blindspot data. That second dependency is what makes the ordering non-negotiable: Blackhat uses Purple Team's detection blindspots not as something to re-report, but as a map of which pivot nodes are also invisible to defenders. A pivot node that has a chaining risk *and* no detection coverage is not just a structural gap — it's an attacker's ideal entry point into an extended dwell scenario.

Blackhat scores on an inverted scale (higher = easier to chain-exploit = weaker cross-path defence), with four dimensions:

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| Cross-path chain feasibility | 30% | Is a pivot-diverge chain technically executable from the shared node? |
| Least-resistance path | 25% | Which chain requires the fewest privilege escalations or control bypasses? |
| Stealth potential | 25% | Does Purple Team's detection data show this pivot is also invisible to defenders? |
| Mitigation chain coverage | 20% | Does any existing control close the *chain* — not just one leg of it? |

The stealth dimension is the one that produces the most actionable findings in practice. A chain that is technically feasible but highly visible is a different risk profile than a chain that is technically feasible and completely silent. Blackhat surfaces both, but the silent chains are the ones that end up in the "act immediately" tier.

Blackhat's pivot chains are not just scored and filed in the expert critique JSON. They are surfaced as **BH-N synthetic attack paths** in the ThreatModel — first-class entries in the same AP list as the deterministically discovered paths, with their own inline diagram, the feeding paths that contributed the pivot, and a "No ADR" notice that flags them for the architectural decision record process. An attacker chain that has no ADR is an undocumented risk acceptance, whether intentional or not.

---

## The Harmonisation Contract

Five critics on the same architecture create an obvious risk: they find the same things and argue about the wording. We saw this in the original three-critic pipeline — the Exploit Analyst would sometimes flag a technique the Coverage Auditor had already addressed, producing a disagreement that was really just a duplicate finding with a different label.

With five critics, the duplication surface is larger. The solution is not post-hoc deduplication (which hides the problem) but a **harmonisation contract** — a set of explicit, enforced scope rules that make each critic's domain non-overlapping:

- The Coverage Auditor does not re-assess structural design gaps (that's 2A's domain).
- The Exploit Analyst does not re-map MITRE techniques (that's 2B's domain — 2C receives 2B's output and adjusts scores for mapping errors, but doesn't re-map).
- Purple Team does not re-raise exploit paths or structural gaps — it is scoped to detection depth and ADR operability only.
- Blackhat does not repeat any finding from any prior critic. Its system prompt says this explicitly: "Do NOT repeat findings already covered by Architect, Tester, Red Team, or Purple Team critics." What Blackhat does with Purple Team's findings is *use* them — as input to stealth scoring — not reproduce them.

The contract is enforced in two ways: in the system prompts (what the LLM is told it is and isn't responsible for) and in the sequential mode dependency chain (each critic receives the prior's structured output and can see what has already been said). Parallel mode exists and runs faster, but the dashboard shows a warning when it's used: critics ran blind, cross-referencing was not possible, re-run with sequential mode for full cross-referencing. The tradeoff is visible, not hidden.

What the contract produces is a synthesis where findings have a known provenance — this finding came from the Exploit Analyst, this one was corroborated by both the Coverage Auditor and Purple Team, this one was raised only by the Architect and has no second opinion. The KNOWN/UNSURE classification in the Expert Consensus panel is derived from that provenance: KNOWN means ≥2 critics independently raised it; UNSURE means it came from a single critic. PT and BH findings about detection gaps and pivot chains are escalated to KNOWN deterministically — their evidence doesn't require a second critic to confirm because it's structurally provable from the architecture graph.

---

## The Flywheel

Adding Purple Team and Blackhat answered the two blind spots we found. It also raised a new version of the same question: *what can't these five critics see?*

The answer is built into the synthesis prompt as a permanent fixture — not as an afterthought but as a required output field. The synthesis must always produce a `blindspots` section: things the entire critic panel was structurally unable to assess, regardless of how well each critic did its job.

The three structural blindspots that appear in every assessment are:

**Supply chain** — every critic in the pipeline evaluates the architecture as drawn. None of them evaluates the third-party components that the architecture depends on but doesn't model. A `CloudApp` node has a vendor, a release pipeline, and a dependency tree. The critics cannot see any of that. The blindspot card surfaces this with a direct action: conduct a separate vendor risk assessment.

**BCP/DR** — security critics assess confidentiality and integrity risks. Availability is a different threat model, and none of the five critics asks what happens to the business if AP-3 succeeds and takes down the API Gateway for 48 hours. The blindspot card surfaces this with a direct action: map RTO/RPO targets and add BCP/DR controls to the relevant ADRs.

**API Gateway placement** — this one is the most architectural. Every critic assesses the attack paths that exist in the diagram. None of them can assess the attack paths that *should* exist in the diagram but don't. An architecture that has an `External User → CloudApp → Database` path with no API Gateway in the diagram will get thoroughly assessed — but no critic will tell you that the API Gateway is missing from the diagram entirely. The blindspot card surfaces this with a direct action: review whether the diagram accurately reflects the deployed architecture before treating the assessment as complete.

These are not failures of the critics. They are boundaries of the method. Making them explicit — tagging each as `⚠ Act` (there is something you can do now) or `📋 Note` (awareness, revisit when scope changes) — is more useful than pretending the assessment is complete.

The flywheel runs as follows: build critics, run them, find what they agree on (KNOWN), find what only one raises (UNSURE), find what none of them can see (blindspots), use those three outputs to ask what the next critic should do. Purple Team emerged from the blindspot observation that all three original critics were red-team-perspective only. Blackhat emerged from the structural observation that no per-path critic can reason about shared infrastructure. The synthesis blindspot section is the mechanism that keeps generating the next iteration.

---

## What This Looks Like in Practice

Here is what the five-critic sequential run produces on the SafeEntry architecture from Part 1 (15 nodes, 5 attack paths, SIEM integration):

**From the Architect:** Two structural gaps — the SIEM node is connected to `AccessLogDB` but not to `AuthService`, creating a partial logging architecture; the `NotificationService` has no data classification annotation in the diagram, leaving its sensitivity unmodelled.

**From the Coverage Auditor:** T1190 (Exploit Public-Facing Application) is mapped to the API Gateway but has no corresponding detection control — WAF is present but produces no observable alert path into the SIEM. T1078 (Valid Accounts) is mapped to AuthService but the MFA control in the ADR covers login only, leaving session token theft unaddressed.

**From the Exploit Analyst:** The IoT path (`Users → MobileApp → API Gateway → DoorController → CardReader`) scores 68/100 on exploit difficulty — the Door Controller to Card Reader hop has no authentication control, making physical access trivially escalatable from a compromised mobile session.

**From Purple Team:** The `DoorController → Biometric` hop has no detection coverage of any kind — no SIEM integration, no EDR, no local logging. An attacker who compromises the Biometric node operates with unlimited dwell time. The `NotificationService` has no detection control either; its outbound connections are untelegraphed.

**From Blackhat:** The API Gateway appears in both the AuthService path and the AccessControlAPI path. A compromised API Gateway becomes a pivot to the Door Controller chain without traversing the authentication step — the WAF on the gateway closes the external traversal but not the internal pivot. This chain scores 74/100 on chain feasibility and 81/100 on stealth (Purple Team confirmed zero detection coverage on the pivot node).

Five critics, five distinct findings, no duplicates. The Architect found a logging architecture gap. The Coverage Auditor found an undetected technique. The Exploit Analyst found a weak link in the IoT path. Purple Team found the IoT layer's detection blind spot. Blackhat found that the API Gateway's position in the graph makes it a stealth pivot between two paths that look independent from the outside.

None of these findings required the same information. None of them could have been found by any other critic in the chain.

---

## What Still Challenges the Assessor

Honest accounting: the five-critic pipeline is better than the three-critic pipeline, and there are things it still cannot do.

**Temporal reasoning.** All five critics assess a static diagram. They cannot reason about what the architecture looked like last quarter, what changed in the last deployment, or whether a control that appears in the diagram has been misconfigured in production. The diagram is an assertion; the critics treat it as ground truth.

**Absence detection.** Critics evaluate what is in the diagram. They cannot reliably tell you what should be in the diagram but isn't — the API Gateway placement blindspot described above is the clearest example. The synthesis prompt forces the blindspot section, but it can only surface the structural absences we know to look for. Novel absence patterns require human review.

**Attacker intent and skill.** Blackhat scores chains on feasibility, stealth, and least resistance. It does not model attacker motivation, operational security maturity, or resource level. A chain that scores 80/100 on feasibility and is attributed to a nation-state actor is a different risk profile than the same chain attributed to an opportunistic threat actor. ThreatAssessor scores the architecture, not the adversary.

**Control implementation quality.** The pipeline knows that MFA is recommended for the AuthService. It does not know whether the deployed MFA uses push notifications (phishable) or hardware tokens (not phishable). A control in the diagram is treated as implemented correctly. Assessing implementation quality requires access to the actual system, not the architecture model.

These are not reasons not to use the tool. They are reasons to use the tool with accurate expectations — as a fast, thorough first pass that surfaces most of what a human architect would find in a day's threat modelling session, not as a substitute for the deeper review that critical systems require.

---

## The Reflection Habit

The most durable output from building Purple Team and Blackhat was not the critics themselves. It was the habit of asking the question systematically: *what can't our current critics see?*

It's easy to look at a well-engineered assessment pipeline and assume coverage. Three independent critics. Sequential cross-referencing. MITRE grounding. Confidence waterfall. These are genuine quality mechanisms. They are also not the same as completeness. The pipeline can be internally consistent and externally incomplete at the same time.

The DECISIONS.md log in the repository captures this explicitly for every architectural choice — not just what was decided but what was assumed, what was rejected, and what the current version cannot do. The blindspot section in every assessment output is the operational version of the same habit: here is what we looked at, here is what we could not look at, here is what you need to do separately.

Part 4 of this series will cover AgentTools — giving the critics the ability to query the MITRE ATT&CK database, architecture context, and control effectiveness data *inside the LLM call*, rather than relying on the model's training knowledge for technique-level decisions. The hypothesis is the same as the one that produced Purple Team and Blackhat: the critics are bounded by what information they have access to at inference time. Expanding that access should expand what they can find. Whether it does — and at what cost — is the next experiment.

---

*ThreatAssessor uses MITRE ATT&CK® (MITRE Corporation), MITRE ATLAS™ (MITRE Corporation), the ARC Framework (GovTech Singapore), CSA CAVEAT (Cloud Security Alliance, CC0-1.0), CSA CCM v4.1 → ATT&CK mapping (Center for Threat-Informed Defense, Apache 2.0), and Singapore Government SSP data from the published ICT&SS Security Standards for Providers catalog.*
