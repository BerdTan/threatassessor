---
name: aivss-score
description: Run AIVSS v4 scorer on a governance_signals.json + ground_truth.json and print the full breakdown
---

Find the governance_signals.json and ground_truth.json for the most recent report (or the architecture named in args, if provided).

1. Load governance_signals.json from `report/<arch_name>/governance_signals.json`
2. Load ground_truth.json from `report/<arch_name>/ground_truth.json`
3. Instantiate `AIVSSFlowScorer` from `chatbot.modules.harness_aivss` and call `compute()`
4. Print a formatted breakdown:
   - AIVSS summary row: `[ Inbound X.X SEV ] [ Internal X.X SEV ] [ Outbound X.X SEV ] [ Overall X.X SEV ]`
   - Industry profile and coverage %
   - Per-flow metric table (metric, sub-scores, composite)
   - Per-threat table (technique_id, name, composite, severity, top_metric, mitigation_multiplier)
   - Per-agent scores if present
   - Flag any metrics below 50% coverage

If governance_signals.json already has an `aivss` block (from a previous run), show that cached result alongside a fresh computation and highlight any differences.
