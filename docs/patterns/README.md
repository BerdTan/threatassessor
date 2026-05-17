# Threat Pattern Documentation

This folder contains documentation for threat patterns used by the system.

## What Are Threat Patterns?

Threat patterns extend the base RAPIDS framework to handle specialized architecture types:

- **RAPIDS** (base): Ransomware, Application Vulns, Phishing, Insider, DDoS, Supply chain
- **AI/ML Pattern**: AI-specific threats using ARC Framework + MITRE ATLAS
- **Cloud Pattern**: Cloud-specific threats (future)
- **ICS Pattern**: Industrial control systems (future)
- **Mobile Pattern**: Mobile application threats (future)

## Current Patterns

### AI/ML Pattern (ARC Framework + MITRE ATLAS)

**Status:** ✅ Complete (v1.1)

**Documentation:**
- [AI_PATTERN_STATUS.md](AI_PATTERN_STATUS.md) - Implementation status and features
- [AI_PATTERN_VERIFICATION.md](AI_PATTERN_VERIFICATION.md) - Integration verification

**Frameworks:**
- **ARC Framework**: 88 controls across 9 categories (Integrity, Safety, Security, Privacy, Transparency, Accountability, Fairness, Resilience, Societal Impact)
- **MITRE ATLAS**: 170 techniques, 35 mitigations for adversarial ML

**Features:**
- Component detection (LLM API, Vector DB, Agent Orchestrator, etc.)
- Risk scoring (0-100 per ARC category)
- Control recommendations (20 AI-specific controls)
- Control gap benchmarking (coverage %)
- ATLAS technique mapping (real attack techniques)
- Full integration with RAPIDS controls

**Example Output:**
```
Architecture: 21_agentic_ai_system.mmd
- RAPIDS controls: 17
- AI/ML controls: 20
- Total controls: 37
- ARC benchmark: 1.1% coverage (1/91 controls)
- Critical gaps: Safety (85/100), Security (85/100), Privacy (80/100)
```

## Future Patterns

### Cloud Pattern (Planned)

**Frameworks:**
- Cloud Security Alliance (CSA) Cloud Controls Matrix
- NIST Cloud Computing Security Reference Architecture
- CIS Cloud Benchmarks

**Target Controls:**
- Identity & Access Management
- Data encryption (at-rest, in-transit)
- Network security (VPC, Security Groups)
- Logging & monitoring
- Container security
- Serverless security

### ICS Pattern (Planned)

**Frameworks:**
- IEC 62443 (Industrial Automation Security)
- NIST Cybersecurity Framework for ICS
- Purdue Model for ICS architecture

**Target Controls:**
- Zone/conduit segmentation
- Safety Instrumented Systems (SIS) protection
- OT network isolation
- Industrial protocol security
- Physical access controls

### Mobile Pattern (Planned)

**Frameworks:**
- OWASP Mobile Security Testing Guide
- NIST Mobile Security Guidelines
- Android/iOS security best practices

**Target Controls:**
- App sandboxing
- Secure storage
- Certificate pinning
- Biometric authentication
- Runtime application self-protection (RASP)

## Pattern Development Guidelines

When creating a new pattern:

1. **Select Framework**: Choose industry-standard framework(s)
   - Example: ARC Framework for AI, CSA CCM for Cloud

2. **Map Controls**: Create comprehensive control list
   - Example: 88 ARC controls for AI pattern

3. **Component Detection**: Define rules to detect architecture type
   - Keywords, node types, connection patterns

4. **Risk Scoring**: Define risk calculation per threat category
   - Control-aware: risk adjusts based on controls present

5. **Technique Mapping**: Map to MITRE ATT&CK or domain-specific frameworks
   - Enterprise ATT&CK for traditional
   - ATLAS for AI/ML
   - ICS-specific for industrial

6. **Enrichment**: Add RAPIDS-style structure
   - attack_paths
   - dir_category (prevention/detect/isolate/respond)
   - layer (application/network/data/identity)
   - placement (node-specific)
   - confidence scoring

7. **Benchmarking**: Provide gap analysis
   - Total controls available
   - Coverage percentage
   - Critical gaps (high risk + low coverage)

8. **Documentation**: Create status and verification docs
   - Status: features, examples, usage
   - Verification: test results, integration checks

## Pattern Integration Architecture

```
ThreatAnalyst
├── PatternRegistry
│   ├── AIPattern (ARC + ATLAS)
│   ├── CloudPattern (future)
│   ├── ICSPattern (future)
│   └── MobilePattern (future)
└── RAPIDS (base framework)
```

**Flow:**
1. ThreatAnalyst detects architecture type
2. Loads matching patterns from registry
3. Runs RAPIDS (base) + Pattern-specific assessment
4. Merges controls with full enrichment
5. Generates reports with pattern-specific sections

## Files

**Implementation:**
- `chatbot/modules/patterns/ai_pattern.py` - AI/ML pattern
- `chatbot/modules/pattern_registry.py` - Pattern registration system
- `chatbot/modules/atlas_helper.py` - MITRE ATLAS data loader

**Data:**
- `chatbot/data/atlas/*.yaml` - MITRE ATLAS techniques/mitigations
- `chatbot/data/enterprise-attack.json` - MITRE ATT&CK (base)

**Documentation:**
- `docs/patterns/` - This folder (pattern-specific docs)
- `docs/development/ARCHITECTURE.md` - System architecture

## Contributing

When adding a new pattern:

1. Create `chatbot/modules/patterns/<name>_pattern.py`
2. Implement ThreatPattern interface
3. Add data files to `chatbot/data/<name>/`
4. Create docs in `docs/patterns/<NAME>_PATTERN_STATUS.md`
5. Add verification doc `docs/patterns/<NAME>_PATTERN_VERIFICATION.md`
6. Update this README with pattern details

---

**Last Updated:** 2026-05-17
