# threatmodel.md — Open Threat Model Specification v0.1

**Status:** Draft  
**Version:** 0.1.0  
**Date:** 2026-11-01  
**Maintainer:** ThreatAssessor project  
**License:** CC BY 4.0 — use, adapt, benchmark freely; attribution required

---

## Purpose

This document defines what a **complete, verifiable threat model** must contain. It is a machine-readable contract intended for:

- AI agents conducting threat models (to self-verify output completeness)
- Benchmark runners scoring TM tool output against ground truth
- Human reviewers auditing TM quality against a shared standard
- Tool builders who want their output to be externally comparable

This spec is **not tied to any specific tool or vendor**. Any agent or tool that produces a threat model can be scored against it using the same runner and the same corpus.

---

## Scope

A threat model in scope for this spec covers one **architecture** — a defined system with components, data flows, trust boundaries, and an operational context. The spec does not prescribe how the architecture is described (Mermaid, Terraform, prose, diagram) but requires that the TM output addresses all sections below.

---

## 1. Required Sections

A compliant threat model MUST contain all six sections. A section is present if it has at least one substantive entry (not a placeholder, not "N/A" without justification).

### 1.1 Architecture Summary

**Required fields:**
- Component inventory: list of components with roles (data store, compute, ingress, egress, agent)
- Trust boundary map: which components cross trust boundaries and how
- Data classification: sensitivity tier of data at rest and in transit (at minimum: public / internal / confidential / restricted)
- Operational context: deployment model (cloud, on-prem, hybrid, agentic pipeline, SaaS)

**Minimum coverage:** All components identified in the source architecture must appear. Unlabelled components are a gap.

### 1.2 Threat Actor Profile

**Required fields:**
- At least one threat actor with: motivation, capability tier (opportunistic / targeted / nation-state), likely initial access vector
- For agentic architectures: at least one adversarial agent scenario (prompt injection, goal hijacking, tool misuse)

**Minimum coverage:** At least one external and one insider threat actor for non-trivial architectures (> 3 components).

### 1.3 Attack Paths

**Required fields per path:**
- `technique_id`: MITRE ATT&CK technique ID (e.g. T1190, T1078) — enterprise, ICS, or ATLAS as appropriate
- `technique_name`: human-readable name
- `tactic`: the ATT&CK tactic phase (Initial Access, Execution, Persistence, …)
- `target_component`: the architecture component this path targets
- `entry_point`: where the attack enters the system
- `impact`: what the attacker achieves if the path succeeds (data exfil, lateral movement, denial of service, etc.)
- `likelihood`: Low / Medium / High — with a one-line rationale

**Minimum coverage:**
- At least 3 attack paths for architectures with ≤ 5 components
- At least 5 attack paths for architectures with 6–15 components
- At least 8 attack paths for architectures with > 15 components
- At least one path per trust boundary crossing
- At least one path targeting data at rest and one targeting data in transit

**ATLAS requirement:** Architectures containing an AI/ML component MUST include at least one MITRE ATLAS technique (e.g. AML.T0043 Craft Adversarial Data, AML.T0048 Model Backdoor).

### 1.4 Mitigations

**Required fields per mitigation:**
- `control_id`: reference to a control framework (e.g. NIST CSF PR.AC-1, CIS Control 5.1, CSA ART 4.2)
- `control_name`: human-readable label
- `addresses_technique`: one or more `technique_id` values this control mitigates
- `implementation_status`: Implemented / Partial / Planned / Not applicable
- `residual_risk`: Low / Medium / High after this control is applied

**Minimum coverage:** Every attack path MUST have at least one mitigation. A path with no mitigation is a gap — it must be explicitly noted as an open finding, not silently omitted.

### 1.5 Risk Assessment

**Required fields per finding:**
- `finding_id`: unique identifier (e.g. F-001)
- `severity`: Critical / High / Medium / Low / Informational
- `severity_rationale`: one sentence explaining the rating
- `cvss_vector` OR `aivss_vector`: at least one structured severity vector
  - CVSS 3.1 for traditional systems
  - AIVSS for AI/ML components (adds AI-specific metrics: autonomy level, training data integrity, inference integrity)
- `affected_components`: list of components
- `linked_techniques`: list of `technique_id` values
- `remediation_priority`: Immediate / Short-term (< 90 days) / Long-term (> 90 days)

**Minimum coverage:** Every attack path must produce at least one finding. Duplicate findings for the same technique on different components are valid and expected.

### 1.6 Governance Signals

**Required for all architectures:**
- `data_sovereignty`: jurisdictions where data is processed and stored
- `compliance_scope`: applicable frameworks (SOC 2, ISO 27001, GDPR, HIPAA, PCI-DSS, etc.) — "none identified" is acceptable if justified
- `third_party_dependencies`: external services, APIs, or models the architecture depends on, with trust tier (trusted / conditional / untrusted)

**Required for agentic architectures** (architectures with autonomous agents, LLM-driven components, or tool-calling pipelines):
- `agent_autonomy_level`: supervised / semi-autonomous / autonomous
- `tool_call_scope`: list of tools or APIs the agent can invoke
- `blast_radius`: what an uncontrolled agent run could affect (data, external systems, other agents)
- `human_oversight_points`: where a human is in the loop, or explicit statement that no oversight exists
- `model_provenance`: model provider, model ID, and whether the model is fine-tuned or prompted-only

---

## 2. TATB Rubric

The TATB rubric scores TM quality across four dimensions. Each dimension is scored 0–3; total is 0–12. A passing TM scores ≥ 8 with no dimension at 0.

### 2.1 Threat-Relevant (TR)

Does the TM identify threats that are genuinely applicable to this architecture, or does it list generic threats that apply to any system?

| Score | Meaning |
|---|---|
| 3 | All threats are specific to the architecture's components, data flows, and deployment context. No generic filler. |
| 2 | Most threats are specific; a few are generic but not misleading. |
| 1 | Mix of specific and generic. A reader could not distinguish this TM from one written for a different architecture. |
| 0 | Threats are entirely generic (e.g. "SQL injection", "phishing" with no architecture grounding). |

### 2.2 TTP-Accurate (TA)

Are the MITRE ATT&CK technique IDs correct and appropriate for the attack paths described?

| Score | Meaning |
|---|---|
| 3 | All technique IDs are valid, correctly named, and the tactic phase is accurate. Sub-techniques used where they add precision. |
| 2 | Minor errors (one wrong tactic phase, one deprecated technique ID) but overall mapping is accurate. |
| 1 | Several technique IDs are wrong, missing, or mismatched to their described attack path. |
| 0 | No MITRE ATT&CK grounding, or technique IDs are fabricated/nonsensical. |

### 2.3 Risk-Defensible (RD)

Are the severity ratings defensible against the architecture's actual exposure and control posture?

| Score | Meaning |
|---|---|
| 3 | Severity ratings reflect the architecture's real exposure. Controls reduce ratings where applied. Open findings are rated higher than mitigated ones. |
| 2 | Most ratings are defensible; one or two are inflated or deflated without clear rationale. |
| 1 | Ratings are inconsistent — identical exposures rated differently, or all findings rated the same severity. |
| 0 | All findings are the same severity, or severity is not present. |

### 2.4 Plan-Actionable (PA)

Does the TM produce a remediation plan a practitioner can act on?

| Score | Meaning |
|---|---|
| 3 | Every finding has a mitigation with a control reference, implementation status, and remediation priority. A practitioner knows what to do next. |
| 2 | Most findings are actionable; a few have vague mitigations ("implement security controls"). |
| 1 | Mitigations are present but generic or redundant. Control references are absent or wrong. |
| 0 | No actionable mitigations. Findings listed with no remediation guidance. |

---

## 3. Verification Checklist

An AI agent completing a TM can self-verify by checking each item. A TMbench runner uses the same checklist to score output.

**Section completeness:**
- [ ] Architecture summary present with all required fields
- [ ] At least one threat actor with motivation, capability tier, and initial access vector
- [ ] Attack path count meets minimum coverage threshold for architecture size
- [ ] Every trust boundary crossing has at least one attack path
- [ ] Every attack path has at least one mitigation
- [ ] Every attack path has at least one risk finding with severity
- [ ] Governance signals section present

**ATT&CK grounding:**
- [ ] All technique IDs match the ATT&CK Enterprise, ICS, or ATLAS taxonomy
- [ ] All technique names match their IDs
- [ ] All tactic phase assignments are correct

**Agentic architecture (if applicable):**
- [ ] At least one ATLAS technique present
- [ ] Agent autonomy level declared
- [ ] Blast radius assessed
- [ ] Human oversight points identified or explicitly noted as absent
- [ ] Model provenance recorded

**Risk quality:**
- [ ] No two findings for materially different exposures share the same severity without rationale
- [ ] Severity vectors (CVSS or AIVSS) present for all High and Critical findings
- [ ] Residual risk assessed after mitigations applied

---

## 4. Output Schema

A TM produced for TMbench scoring MUST be serialisable to the following JSON structure. Fields marked `required` must be present for a submission to be scored; fields marked `recommended` are scored under Plan-Actionable.

```json
{
  "spec_version": "threatmodel/0.1",
  "architecture_id": "<string — identifier for the input architecture>",
  "produced_by": "<string — tool name and version>",
  "produced_at": "<ISO 8601 datetime>",
  "architecture_summary": {
    "components": [
      { "id": "<string>", "role": "<string>", "trust_zone": "<string>" }
    ],
    "trust_boundaries": ["<string>"],
    "data_classification": "<public|internal|confidential|restricted>",
    "operational_context": "<string>"
  },
  "threat_actors": [
    {
      "name": "<string>",
      "motivation": "<string>",
      "capability_tier": "<opportunistic|targeted|nation-state>",
      "initial_access_vector": "<string>"
    }
  ],
  "attack_paths": [
    {
      "path_id": "<string>",
      "technique_id": "<string>",
      "technique_name": "<string>",
      "tactic": "<string>",
      "target_component": "<string>",
      "entry_point": "<string>",
      "impact": "<string>",
      "likelihood": "<Low|Medium|High>",
      "likelihood_rationale": "<string>"
    }
  ],
  "mitigations": [
    {
      "mitigation_id": "<string>",
      "control_id": "<string>",
      "control_name": "<string>",
      "addresses_technique": ["<technique_id>"],
      "implementation_status": "<Implemented|Partial|Planned|Not applicable>",
      "residual_risk": "<Low|Medium|High>"
    }
  ],
  "findings": [
    {
      "finding_id": "<string>",
      "severity": "<Critical|High|Medium|Low|Informational>",
      "severity_rationale": "<string>",
      "severity_vector": "<CVSS 3.1 or AIVSS vector string>",
      "affected_components": ["<component_id>"],
      "linked_techniques": ["<technique_id>"],
      "linked_mitigations": ["<mitigation_id>"],
      "remediation_priority": "<Immediate|Short-term|Long-term>"
    }
  ],
  "governance": {
    "data_sovereignty": ["<jurisdiction>"],
    "compliance_scope": ["<framework>"],
    "third_party_dependencies": [
      { "name": "<string>", "trust_tier": "<trusted|conditional|untrusted>" }
    ],
    "agentic": {
      "agent_autonomy_level": "<supervised|semi-autonomous|autonomous>",
      "tool_call_scope": ["<string>"],
      "blast_radius": "<string>",
      "human_oversight_points": ["<string>"],
      "model_provenance": {
        "provider": "<string>",
        "model_id": "<string>",
        "fine_tuned": "<boolean>"
      }
    }
  }
}
```

The `agentic` block is required only when the architecture contains an autonomous agent component.

---

## 5. Scoring Summary

A TMbench runner scores a submission as follows:

| Dimension | Max points | Source |
|---|---|---|
| Threat-Relevant | 3 | TATB rubric §2.1 |
| TTP-Accurate | 3 | TATB rubric §2.2 |
| Risk-Defensible | 3 | TATB rubric §2.3 |
| Plan-Actionable | 3 | TATB rubric §2.4 |
| Completeness bonus | +1 | All checklist items pass |
| Agentic coverage bonus | +1 | ATLAS technique + agentic block present (if applicable) |
| **Total** | **13** | |

**Pass threshold:** ≥ 8 with no TATB dimension at 0.  
**Leaderboard metric:** mean score across all corpus architectures.

---

## 6. Corpus

The TMbench corpus contains reference architectures with ground truth threat models scored and reviewed against this spec. Corpus entries are in `docs/tmbench/corpus/`. Each entry contains:

- `<arch_id>.mmd` — architecture diagram (Mermaid)
- `<arch_id>_ground_truth.json` — reference TM in the output schema above
- `<arch_id>_scores.json` — TATB scores for the ground truth TM

See `docs/tmbench/corpus/README.md` for the corpus inventory and complexity tier classification.

---

## 7. Versioning

This spec is versioned with semver. A breaking change (removing a required field, changing a scoring rule) increments the major version. A scoring run MUST record the spec version it was scored against. Leaderboard entries from different spec versions are not directly comparable.

---

## 8. Relationship to Other Standards

| Standard | Relationship |
|---|---|
| MITRE ATT&CK Enterprise | Required for technique grounding in §1.3 |
| MITRE ATLAS | Required for AI/ML components in §1.3 |
| CVSS 3.1 | One accepted severity vector in §1.5 |
| AIVSS | Preferred severity vector for AI/ML findings in §1.5 |
| NIST CSF | One accepted control framework in §1.4 |
| CSA ART | One accepted control framework in §1.4; preferred for agentic architectures |
| STRIDE | Compatible methodology for generating attack paths; not required |
| PASTA | Compatible methodology; not required |

This spec does not prescribe a threat modeling *methodology* — it defines the required *output*. Any methodology that produces output meeting §1–4 is compliant.
