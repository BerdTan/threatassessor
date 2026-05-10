
================================================================================
TECHNICAL THREAT ASSESSMENT REPORT
================================================================================

Architecture: 01_minimal_vulnerable.mmd
Type: Web App
Components: 3 nodes, 2 connections
Generated: parser
Assessment Date: 2026-05-10 08:26 UTC

═══════════════════════════════════════════════════════════════════════════════
SUMMARY METRICS
═══════════════════════════════════════════════════════════════════════════════

Overall Risk Score:      91/100 (higher = worse)
Defensibility Score:     16/100 (higher = better)
Control Coverage:        0%
Attack Paths Identified: 2

Controls Detected:       0
  None

Critical Gaps:           17
  least privilege, rate limiting, logging, patching, user training

═══════════════════════════════════════════════════════════════════════════════
ATTACK PATH ANALYSIS
═══════════════════════════════════════════════════════════════════════════════


[1] CRITICAL PRIORITY (Criticality: 0.96)
────────────────────────────────────────────────────────────────────────────────
Entry Point:  Internet
Target:       Database
Path:         Internet → WebServer → Database
Hop Count:    2
MITRE ATT&CK:
  • T1190: Exploit Public-Facing Application
    Adversaries may attempt to exploit a weakness in an Internet-facing host or system to initially access a network.
  • T1133: External Remote Services
    Adversaries may leverage external-facing remote services to initially access and/or persist within a network.
  • T1059: Command and Scripting Interpreter
    Adversaries may abuse command and script interpreters to execute commands, scripts, or binaries.
  • T1203: Exploitation for Client Execution
    Adversaries may exploit software vulnerabilities in client applications to execute code.
  • T1213: Data from Information Repositories
    Adversaries may leverage information repositories to mine valuable information.
  • T1005: Data from Local System
    Adversaries may search local system sources, such as file systems, configuration files, local databases, virtual machine files, or process memory, ...
  • T1567: Exfiltration Over Web Service
    Adversaries may use an existing, legitimate external Web service to exfiltrate data rather than their primary command and control channel.
  • T1486: Data Encrypted for Impact
    Adversaries may encrypt data on target systems or on large numbers of systems in a network to interrupt availability to system and network resources.
  • T1490: Inhibit System Recovery
    Adversaries may delete or remove built-in data and turn off services designed to aid in the recovery of a corrupted system to prevent recovery.
  • T1485: Data Destruction
    Adversaries may destroy data and files on specific systems or in large numbers on a network to interrupt availability to systems, services, and net...
Rationale:    [CRITICAL] Internet → Web Server → Database: 2 hops, criticality score 0.96

[2] CRITICAL PRIORITY (Criticality: 0.93)
────────────────────────────────────────────────────────────────────────────────
Entry Point:  WebServer
Target:       Database
Path:         WebServer → Database
Hop Count:    1
MITRE ATT&CK:
  • T1213: Data from Information Repositories
    Adversaries may leverage information repositories to mine valuable information.
  • T1005: Data from Local System
    Adversaries may search local system sources, such as file systems, configuration files, local databases, virtual machine files, or process memory, ...
  • T1567: Exfiltration Over Web Service
    Adversaries may use an existing, legitimate external Web service to exfiltrate data rather than their primary command and control channel.
  • T1486: Data Encrypted for Impact
    Adversaries may encrypt data on target systems or on large numbers of systems in a network to interrupt availability to system and network resources.
  • T1490: Inhibit System Recovery
    Adversaries may delete or remove built-in data and turn off services designed to aid in the recovery of a corrupted system to prevent recovery.
  • T1485: Data Destruction
    Adversaries may destroy data and files on specific systems or in large numbers on a network to interrupt availability to systems, services, and net...
Rationale:    [CRITICAL] Web Server → Database: 1 hop, criticality score 0.93


═══════════════════════════════════════════════════════════════════════════════
RAPIDS THREAT ASSESSMENT
═══════════════════════════════════════════════════════════════════════════════


APPLICATION VULNS: 🔴 CRITICAL
  Risk:          80/100
  Defensibility: 10/100
  Assessment:    WAF: ✗, Input validation: ✗, Rate limiting: ✗

RANSOMWARE: 🔴 CRITICAL
  Risk:          70/100
  Defensibility: 20/100
  Assessment:    Backup: ✗, EDR: ✗, Segmentation: ✗

DOS: 🔴 CRITICAL
  Risk:          70/100
  Defensibility: 10/100
  Assessment:    Load balancer: ✗, DDoS protection: ✗

PHISHING: 🟠 HIGH
  Risk:          60/100
  Defensibility: 10/100
  Assessment:    MFA: ✗, Email gateway: ✗

SUPPLY CHAIN: 🟠 HIGH
  Risk:          60/100
  Defensibility: 30/100
  Assessment:    Requires manual assessment of dependencies and third-party integrations

INSIDER THREAT: 🟠 HIGH
  Risk:          50/100
  Defensibility: 20/100
  Assessment:    Audit logging: ✗, Least privilege: ✗


═══════════════════════════════════════════════════════════════════════════════
CONTROL GAP ANALYSIS (RAPIDS-Driven, MITRE-Validated)
═══════════════════════════════════════════════════════════════════════════════

PRIMARY: RAPIDS threat assessment identifies what threats exist
VALIDATION: Attack paths + MITRE techniques confirm exploitability

Recommended Controls (with threat context and confidence):

1. LEAST PRIVILEGE (CRITICAL)
   Confidence: 🟡 MEDIUM (79%)
   Addresses: Mitigates T1059 in path(s) #1, T1133 in path(s) #1
   MITRE Mitigations: M1016, M1018, M1026
   MITRE Techniques: T1059, T1133, T1190

2. RATE LIMITING (CRITICAL)
   Confidence: 🟢 HIGH (87%)
   Addresses: Mitigates T1059 in path(s) #1, T1133 in path(s) #1
   MITRE Mitigations: M1033, M1035, M1037
   MITRE Techniques: T1059, T1133, T1190

3. LOGGING (CRITICAL)
   Confidence: 🟢 HIGH (84%)
   Addresses: Mitigates T1059 in path(s) #1, T1213 in path(s) #1, #2
   MITRE Mitigations: M1047
   MITRE Techniques: T1059, T1213

4. PATCHING (HIGH)
   Confidence: 🟢 HIGH (81%)
   Addresses: Mitigates T1190 in path(s) #1, T1203 in path(s) #1
   MITRE Mitigations: M1017, M1051, M1054
   MITRE Techniques: T1190, T1203, T1213

5. USER TRAINING (HIGH)
   Confidence: 🟠 LOW (46%)
   Addresses: Mitigates 
   MITRE Mitigations: 
   MITRE Techniques: 

6. BACKUP (HIGH)
   Confidence: 🟢 HIGH (100%)
   Addresses: Mitigates T1485 in path(s) #1, #2, T1486 in path(s) #1, #2
   MITRE Mitigations: M1053
   MITRE Techniques: T1485, T1486, T1490

7. EDR (HIGH)
   Confidence: 🟢 HIGH (93%)
   Addresses: Mitigates T1059 in path(s) #1, T1486 in path(s) #1, #2
   MITRE Mitigations: M1040, M1049
   MITRE Techniques: T1059, T1486

8. WAF (HIGH)
   Confidence: 🟢 HIGH (100%)
   Addresses: Mitigates T1190 in path(s) #1, T1203 in path(s) #1
   MITRE Mitigations: M1037, M1050
   MITRE Techniques: T1190, T1203

9. INPUT VALIDATION (HIGH)
   Confidence: 🟢 HIGH (98%)
   Addresses: Mitigates T1190 in path(s) #1, T1203 in path(s) #1
   MITRE Mitigations: M1050
   MITRE Techniques: T1190, T1203

10. MFA (HIGH)
   Confidence: 🟢 HIGH (96%)
   Addresses: Mitigates T1133 in path(s) #1, T1213 in path(s) #1, #2
   MITRE Mitigations: M1032
   MITRE Techniques: T1133, T1213, T1485

11. CODE SIGNING (HIGH)
   Confidence: 🟡 MEDIUM (78%)
   Addresses: Mitigates T1059 in path(s) #1, T1490 in path(s) #1, #2
   MITRE Mitigations: M1038, M1045
   MITRE Techniques: T1059, T1490

12. VULNERABILITY SCANNING (HIGH)
   Confidence: 🟡 MEDIUM (72%)
   Addresses: Mitigates T1213 in path(s) #1, #2
   MITRE Mitigations: M1017
   MITRE Techniques: T1213

13. NETWORK SEGMENTATION (HIGH)
   Confidence: 🟢 HIGH (96%)
   Addresses: Mitigates T1133 in path(s) #1, T1190 in path(s) #1
   MITRE Mitigations: M1030
   MITRE Techniques: T1133, T1190

14. AUDIT LOG (HIGH)
   Confidence: 🟢 HIGH (84%)
   Addresses: Mitigates T1059 in path(s) #1, T1213 in path(s) #1, #2
   MITRE Mitigations: M1047
   MITRE Techniques: T1059, T1213

15. BEHAVIORAL ANALYSIS (HIGH)
   Confidence: 🟢 HIGH (81%)
   Addresses: Mitigates T1059 in path(s) #1, T1486 in path(s) #1, #2
   MITRE Mitigations: M1040
   MITRE Techniques: T1059, T1486

16. DLP (MEDIUM)
   Confidence: 🟢 HIGH (90%)
   Addresses: Addresses 2 technique(s): T1005, T1567
   MITRE Mitigations: M1057
   MITRE Techniques: T1005, T1567

17. WEB CONTENT FILTERING (MEDIUM)
   Confidence: 🟢 HIGH (90%)
   Addresses: Addresses 1 technique(s): T1567
   MITRE Mitigations: M1021
   MITRE Techniques: T1567


Recommended Implementation Order:
  1. Perimeter defenses (WAF, Firewall, DDoS protection)
  2. Authentication (MFA, SSO, least privilege)
  3. Detection & Response (EDR, SIEM, logging)
  4. Data protection (Encryption, backup, DLP)

═══════════════════════════════════════════════════════════════════════════════
RESIDUAL RISK ASSESSMENT
═══════════════════════════════════════════════════════════════════════════════

Even with ALL recommended controls implemented, residual risk remains.
No control is 100% effective - this is a realistic assessment for risk acceptance.

| Threat Category      | Initial | Control Effectiveness | Residual | Status   |
|---------------------|---------|----------------------|----------|----------|
| Ransomware           | 70/100  | 100%                 | 0/100    | ✅ ACCEPT |
|   Controls: least privilege, backup +2 more
| Application Vulns    | 80/100  | 100%                 | 0/100    | ✅ ACCEPT |
|   Controls: rate limiting, patching +2 more
| Phishing             | 60/100  | 100%                 | 0/100    | ✅ ACCEPT |
|   Controls: least privilege, logging +2 more
| Insider Threat       | 50/100  | 100%                 | 0/100    | ✅ ACCEPT |
|   Controls: least privilege, logging +3 more
| Dos                  | 70/100  | 80%                  | 13/100   | ⚠️ MONITOR |
|   Controls: rate limiting
| Supply Chain         | 60/100  | 91%                  | 5/100    | ✅ ACCEPT |
|   Controls: code signing, vulnerability scanning

✅ OVERALL RESIDUAL RISK: 3.0/100 (ACCEPT)

Risk Acceptance Thresholds:
  • < 10:  ✅ ACCEPT (low risk, quarterly monitoring)
  • 10-20: ⚠️ MONITOR (medium risk, active monitoring required)
  • > 20:  ❌ MITIGATE (high risk, additional controls needed)

Why Residual Risk Exists (No Silver Bullet):
  • Zero-day exploits (no patch available yet)
  • Advanced Persistent Threats (sophisticated techniques)
  • Insider threats with privileged access
  • Social engineering and human error
  • Configuration drift and operational mistakes

Continuous Improvement Recommendations:
  • Quarterly threat landscape review
  • Annual penetration testing
  • Bi-annual incident response drills
  • Control effectiveness validation
  • Security awareness training (quarterly)


═══════════════════════════════════════════════════════════════════════════════
ARCHITECTURE-SPECIFIC RECOMMENDATIONS
═══════════════════════════════════════════════════════════════════════════════


Web Application Security:
  • Deploy Web Application Firewall (WAF)
  • Implement input validation/sanitization
  • Add rate limiting to prevent abuse
  • Enable HTTPS/TLS encryption
  • Implement security headers (CSP, HSTS)
  • Add API authentication/authorization

================================================================================
