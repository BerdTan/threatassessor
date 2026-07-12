# Part 10: When the Benchmark Finds Its Own Blind Spots

*Part 9 ended with a promise: the next post would cover what happens when a benchmark starts catching its own measurement errors. This is that post, updated to include what we found when we pointed the same machine at an AI system diagram.*

---

## The flywheel: three gears, one loop

Last time we built a quality flywheel. Here is what it looks like when all three gears are turning:

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║                    THE QUALITY FLYWHEEL                       ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║    ┌─────────────┐   produces    ┌─────────────┐             ║
  ║    │  ⚙ GEAR 1   │──────────────►│  ⚙ GEAR 2   │             ║
  ║    │             │               │             │             ║
  ║    │    BUILD    │               │    LABEL    │             ║
  ║    │             │               │             │             ║
  ║    │  Engine     │               │ Independent │             ║
  ║    │  produces   │               │ model marks │             ║
  ║    │  threat     │               │ what SHOULD │             ║
  ║    │  model      │               │ be found    │             ║
  ║    └─────────────┘               └──────┬──────┘             ║
  ║           ▲                             │                     ║
  ║           │                             ▼                     ║
  ║    fixes  │                      ┌─────────────┐             ║
  ║    applied│◄─────────────────────│  ⚙ GEAR 3   │             ║
  ║           │      repair list     │             │             ║
  ║           │                      │    SCORE    │             ║
  ║           │                      │             │             ║
  ║           │                      │  Compares   │             ║
  ║           │                      │  the two.   │             ║
  ║           │                      │  Gaps =     │             ║
  ║           └──────────────────────│  repair list│             ║
  ║                                  └─────────────┘             ║
  ║                                                               ║
  ║  Rule: each gear must stay blind to the others.               ║
  ║  Gear 2 never sees Gear 1's output.                           ║
  ║  Gear 3 is never tuned to flatter Gear 1.                     ║
  ╚═══════════════════════════════════════════════════════════════╝
```

The loop works because each gear is genuinely independent. The moment any gear starts referencing another (the labeller trained on engine outputs, the scorer calibrated against historical engine performance), the wheel starts measuring its own confidence instead of its correctness. The score keeps rising. The system appears to improve. But it is only getting better at passing its own test.

We ran it on 26 architectures instead of 15. Then, later, we pointed it at something it had never seen before: a pure AI/agentic system diagram. What the loop found, in order, was six ways a gear can slip.

---

## Aha 1: The ruler was wrong

**Which gear:** Gear 3 (Score)

The labeller had marked T1021.001 (Remote Desktop Protocol) as expected for several architectures. The engine was detecting T1021 (Remote Services). The scorer counted this as a miss because the IDs did not match exactly.

But T1021.001 *is* T1021. The parent covers the child. The engine was correct. The ruler was wrong.

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║  AHA 1 — GEAR 3 SLIPPING: measurement error                  ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║  Labeller expected:   T1021.001 ─┐                           ║
  ║                       T1021.002 ─┼──► Gear 3 scored: MISS ✗  ║
  ║                       T1021.007 ─┘         ↑                 ║
  ║                                       wrong — these are       ║
  ║  Engine detected:     T1021 ────────► subtechniques of T1021  ║
  ║                                                               ║
  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║
  ║  Fix: parent ID covers all children                           ║
  ║                                                               ║
  ║  T1021 detected → T1021.001 ✓  T1021.002 ✓  T1021.007 ✓     ║
  ║                                                               ║
  ║  Recall: 63% ──────────────────────────────────────► 69%     ║
  ║  (engine unchanged — only the ruler improved)                 ║
  ╚═══════════════════════════════════════════════════════════════╝
```

Before fixing the engine, check whether the measuring is fair.

---

## Aha 2: The gate was backwards

**Which gear:** Gear 1 (Build)

T1567 is exfiltration over web service, using Dropbox, GitHub, S3 as staging for stolen data. The engine had a rule: only flag this technique if the architecture uses cloud infrastructure.

The labeller flagged it on six architectures with no cloud at all: a flat network, an internet-facing web server, a database.

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║  AHA 2 — GEAR 1 WRONG RULE: perspective error                 ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║  Rule (as written):                                           ║
  ║  ┌─────────────────────────────────────────────────────┐     ║
  ║  │  IF architecture uses cloud → flag T1567             │     ║
  ║  │  (thinking about YOUR cloud)                         │     ║
  ║  └─────────────────────────────────────────────────────┘     ║
  ║                       ↓                                       ║
  ║           6 archs: no cloud keywords                          ║
  ║           engine: skip T1567  ✗                               ║
  ║           labeller: T1567 expected  ✓                         ║
  ║                                                               ║
  ║  Why the labeller was right:                                   ║
  ║  T1567 = attacker uses THEIR cloud (Dropbox, GitHub, S3)      ║
  ║  Applies whenever there is internet connectivity              ║
  ║                                                               ║
  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║
  ║  Fix: has_cloud  →  has_cloud OR has_internet                  ║
  ║                                                               ║
  ║  ┌─────────────────────────────────────────────────────┐     ║
  ║  │  IF internet-facing → flag T1567                     │     ║
  ║  │  (thinking about ATTACKER'S capability)              │     ║
  ║  └─────────────────────────────────────────────────────┘     ║
  ║  6 misses ─────────────────────────────────────► 6 correct   ║
  ╚═══════════════════════════════════════════════════════════════╝
```

Rules written from the builder's perspective encode the builder's blind spots. When the labeller disagrees consistently across multiple architectures, it is usually right.

---

## Aha 3: The domain vocabulary gap

**Which gear:** Gear 1 (Build)

The corpus included a pure data pipeline: Data Sources → Kafka Cluster → Spark Cluster → Data Lake → BI Dashboard. The engine had no keywords for any of these nodes.

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║  AHA 3 — GEAR 1 NO VOCABULARY: domain blind spot              ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║  Node: "Kafka Cluster"                                        ║
  ║         ↓                                                     ║
  ║  [no keyword match]                                           ║
  ║         ↓                                                     ║
  ║  generic fallback fires                                       ║
  ║         ↓                                                     ║
  ║  T1059, T1083  ←  same as any web server                      ║
  ║                                                               ║
  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║
  ║  What Kafka actually is:                                      ║
  ║                                                               ║
  ║  Kafka Cluster ──► T1040  stream interception                 ║
  ║                    T1565  message injection (poison data)     ║
  ║                    T1213  data harvesting from stream         ║
  ║                    T1552  credentials in job config           ║
  ║                                                               ║
  ║  Spark Cluster ──► T1059  code execution in jobs              ║
  ║                    T1552  credentials in Spark config         ║
  ║                    T1565  transform-stage data manipulation   ║
  ║                                                               ║
  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║
  ║  Result after adding domain keywords:                         ║
  ║                                                               ║
  ║  data_pipeline overall:  67 ──────────────────────────► 83   ║
  ║  Threat-Relevant:        76 (Solid) ──────────► 96 (Excellent)║
  ╚═══════════════════════════════════════════════════════════════╝
```

Every time a node falls to the generic fallback, the domain is not covered. The flywheel surfaces this because the labeller knows the domain even when the engine does not.

---

## Aha 4: The invisible tradeoff

**Which gear:** Gear 3 (Score), which only measured half the picture

The previous tuning session removed Lateral Tool Transfer from all traversal nodes to fix a precision problem. It worked. Precision improved. It looked like a clean win.

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║  AHA 4 — GEAR 3 INCOMPLETE: only measured one dimension       ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║  Session 11 — tested on 15 architectures:                     ║
  ║                                                               ║
  ║  Remove T1570 (Lateral Tool Transfer)                         ║
  ║  Precision:  ▲  false positives eliminated  ← visible         ║
  ║  Recall:     ?  (not checked at full scale) ← invisible       ║
  ║                                                               ║
  ║  Looked like: a clean win ✓                                   ║
  ║                                                               ║
  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║
  ║  Session 12 — corpus regression on all 26 architectures:      ║
  ║                                                               ║
  ║  T1570 missing in:  ████████████████████████████  14 / 26    ║
  ║                                                               ║
  ║  Recall hole 3× larger than the precision gain                ║
  ║                                                               ║
  ║  Actual result: a hidden regression ✗                         ║
  ║                                                               ║
  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║
  ║  Rule: always check F1 at corpus scale                        ║
  ║  A change that improves one and breaks the other is not a win ║
  ╚═══════════════════════════════════════════════════════════════╝
```

The tradeoff is invisible if you test one architecture at a time. It only appears at scale.

---

## Aha 5: The signal that was missing

**Which gear:** Gear 3 (Score), measuring arch-wide rather than per-path

The existing signal checked whether a mitigation control existed somewhere for each technique on any attack path. But "somewhere in the architecture" is not the same as "covering that specific attack path."

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║  AHA 5 — GEAR 3 COARSE SIGNAL: arch-wide ≠ per-path           ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║  Old signal (tech_cov):                                       ║
  ║                                                               ║
  ║  AP-1  WebServer → T1557 fires here                           ║
  ║  AP-2  Database  → T1557 fires here                           ║
  ║  Control: WAF at entry, assigned to AP-1 only, maps T1557     ║
  ║                                          ↓                    ║
  ║  tech_cov asks: "is T1557 in any control?" → YES             ║
  ║  tech_cov score: 100% ← misleading                           ║
  ║  AP-2 T1557: no control ← invisible gap                      ║
  ║                                                               ║
  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║
  ║  New signal (ap_cov):                                         ║
  ║                                                               ║
  ║  For each (AP, technique) pair:                               ║
  ║    Does any control cover BOTH this AP AND this technique?    ║
  ║                                                               ║
  ║  AP-1 + T1557: WAF covers AP-1, maps T1557  →  ✓ covered     ║
  ║  AP-2 + T1557: no control covers AP-2        →  ✗ gap surfaced║
  ║                                                               ║
  ║  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ║
  ║  Corpus result: 96% of (AP, technique) pairs already aligned  ║
  ║  The pipeline was doing this well. Now it is measured.        ║
  ╚═══════════════════════════════════════════════════════════════╝
```

A 96% result on a new signal establishes the baseline you need to catch future regressions. Not wasted. Necessary.

---

## Aha 6: The engine didn't speak AI

**Which gear:** Gear 1 (Build) and Gear 3 (Score), simultaneously

Then we pointed the loop at something it had never seen: an agentic AI architecture.

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║  THE ARCHITECTURE THE ENGINE COULDN'T READ                    ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║  Users                                                        ║
  ║    │                                                          ║
  ║    ▼                                                          ║
  ║  Web UI / Chat Interface                                      ║
  ║    │                                                          ║
  ║    ▼                                                          ║
  ║  Agent Orchestrator  ◄─── 15 attack paths converge here      ║
  ║    │         │                                                ║
  ║    ▼         ▼                                                ║
  ║  Tool      Prompt Manager                                     ║
  ║  Registry    │                                                ║
  ║    │         ▼                                                ║
  ║    │      LLM API Gateway                                     ║
  ║    │         │                                                ║
  ║    ▼         ▼                                                ║
  ║  Database  Embedding  SessionStore  AuditLog                  ║
  ║  Tool      Service                                            ║
  ║                                                               ║
  ╚═══════════════════════════════════════════════════════════════╝
```

First run. The numbers were not encouraging.

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║  AHA 6 — GEAR 1 + GEAR 3: entire domain invisible             ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║  Node coverage:    47%  ← half the nodes untouched            ║
  ║  Validation FAIL:  89 techniques failed validation            ║
  ║  Hop coverage:     31%  ← 47 of 68 hops missing layers        ║
  ║  TATB overall:     79   Solid                                 ║
  ║                                                               ║
  ║  What was happening:                                          ║
  ║                                                               ║
  ║  Validator checks "server", "database", "network"             ║
  ║  AI nodes say "Agent Orchestrator", "Tool Registry",          ║
  ║               "Prompt Manager", "LLM API Gateway"             ║
  ║                                                               ║
  ║  Keyword match:  ZERO                                         ║
  ║  Technique T1021 on path "→ Agent Orchestrator → Tool         ║
  ║  Registry → Database Tool":   FAILED ✗                        ║
  ║                                                               ║
  ║  The engine knew about T1021 (lateral movement).              ║
  ║  It just could not confirm it on AI node labels.              ║
  ║                                                               ║
  ╚═══════════════════════════════════════════════════════════════╝
```

There was a second problem underneath the first. When we fixed the node coverage (adding 15 AI-system node types, ATLAS techniques, better path targets), the hop coverage score *got worse*:

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║  FIXING COVERAGE REVEALED A MEASUREMENT GAP                   ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║  Before AI node fix:                                          ║
  ║    Paths found:     5 (shallow, missed most nodes)            ║
  ║    Hops:           23                                         ║
  ║    Hop coverage:   52%                                        ║
  ║                                                               ║
  ║  After AI node fix:                                           ║
  ║    Paths found:    15 (reaching deep AI nodes)                ║
  ║    Hops:           68                                         ║
  ║    Hop coverage:   31%  ← went DOWN ✗                         ║
  ║                                                               ║
  ║  Why? The coverage checker infers zero-trust layers           ║
  ║  from control names. It knew "EDR" = detect + respond.        ║
  ║  It did not know:                                             ║
  ║                                                               ║
  ║  "human_oversight"   = detect + respond                       ║
  ║  "content_moderation"= prevention + detect + respond          ║
  ║  "api access control" = prevention + isolate + respond        ║
  ║  "rate limiting"     → was missing "respond" layer            ║
  ║                                                               ║
  ║  More coverage = more exposed gaps in the measurement layer   ║
  ║                                                               ║
  ╚═══════════════════════════════════════════════════════════════╝
```

There was a third layer. The critics (Architect, Red Team, Blackhat) had been referencing ATLAS techniques in their reasoning for months:

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║  CRITICS KNEW ATLAS. ENGINE DID NOT EMIT IT.                  ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║  Blackhat critique (before fix):                              ║
  ║  "ToolRegistry pivot: AML.T0044 (full model access)           ║
  ║   enables model theft followed by CodeExecution"              ║
  ║                                                               ║
  ║  Ground truth ATLAS techniques:    0                          ║
  ║                                                               ║
  ║  The critics were reasoning about a threat layer              ║
  ║  that did not exist in the data they were reviewing.          ║
  ║                                                               ║
  ║  Cross-critic signal for ATLAS:   0%                          ║
  ║  (no technique to corroborate)                                ║
  ║                                                               ║
  ║  Fix: inject AML.T* techniques into per_node_techniques       ║
  ║       for AI-system node types, route AML.* through           ║
  ║       AtlasHelper (not MitreHelper) to avoid false penalties  ║
  ║                                                               ║
  ╚═══════════════════════════════════════════════════════════════╝
```

Three separate gears, three simultaneous failures, one architecture. After fixing all three:

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║  21_agentic_ai_system — before and after                      ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║  Signal               Before        After                     ║
  ║  ─────────────────────────────────────────                    ║
  ║  Node coverage         47%           89%                      ║
  ║  Recall                49%           72%                      ║
  ║  Techniques found      23            45   (+ ATLAS live)      ║
  ║  Validation FAILED     89            18   (legitimately fail) ║
  ║  Hop layer coverage    31%           91%                       ║
  ║  Risk-Defensible       70 Solid      88 Excellent             ║
  ║  TATB overall          79 Solid      86 Excellent             ║
  ║                                                               ║
  ║  Remaining 18 validation failures: correct rejections         ║
  ║  (T1530 cloud-storage on paths with no cloud target)          ║
  ║                                                               ║
  ╚═══════════════════════════════════════════════════════════════╝
```

The engine had learned to read one language: traditional infrastructure. `server`, `database`, `network`, `firewall`. When the diagram said `Agent Orchestrator` and `Tool Registry`, it was like handing it a document in a different alphabet.

The flywheel did not ask us to fix this. It showed us the score and let us figure out why it was low. That is its job.

---

## What the wheel looks like when all gears turn

After all six corrections applied:

```
  ╔═══════════════════════════════════════════════════════════════╗
  ║  CORPUS RESULTS — before and after                            ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║                                                               ║
  ║  Metric                      Before      After               ║
  ║  ─────────────────────────────────────────────               ║
  ║  All architectures ≥ Solid     No         Yes (min = 70)     ║
  ║  Corpus average score          76          80                 ║
  ║  TTP accuracy avg              50%         59%                ║
  ║  Recall (with rollup fix)      62%         69%                ║
  ║  Worst architecture            67          70                 ║
  ║  data_pipeline overall         67          83  (+16)          ║
  ║  dmz_architecture overall      81          86  (Excellent)    ║
  ║  21_agentic_ai_system overall  79          86  (Excellent)    ║
  ║                                                               ║
  ║  Each improvement came from a different gear:                 ║
  ║                                                               ║
  ║  Gear 1 (Build):    wrong gate, domain gap, AI vocabulary     ║
  ║  Gear 2 (Label):    stayed honest throughout                  ║
  ║  Gear 3 (Score):    measurement error, coarse signal,         ║
  ║                     layer inference gap (AI controls)         ║
  ╚═══════════════════════════════════════════════════════════════╝
```

More important than the numbers: after several rounds of the loop, the critics in the Expert Review step are spending less time on basic structural omissions. They are finding subtler mismatches instead: cross-path dependencies, detection blind spots, control placement. The interesting work is moving up the stack.

The loop is not finished. 69% recall means roughly one in three expected techniques is still missing. The remaining gaps are architecture-conditional. The next round will surface them.

That is what the flywheel is for. Not a destination. A practice.

If you want to see exactly how TATB scores a threat model, the rubric definitions are open: [docs/TATB_RUBRIC.md](https://github.com/BerdTan/threatassessor/blob/master/docs/TATB_RUBRIC.md). The weights, the signals, the synonym tables used for MITRE alignment, and the design principles are all there. If you use threat modelling in your work and the rubric misses something important, I'd be curious to hear what.

---

*The next post covers the critic panel: how five expert critics are structured, where sequential anchoring limits diversity, and what changes when you let them run independently.*
