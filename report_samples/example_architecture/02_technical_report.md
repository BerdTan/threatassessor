# 🔬 Technical Threat Assessment Report

**Architecture:** 01_minimal_vulnerable.mmd  
**Type:** Web App | **Components:** 3 nodes, 2 connections  
**Generated:** parser | **Date:** May 10, 2026

## 📊 Summary Metrics

**Overall Risk Score:** 91/100 (higher = worse)  
**Defensibility Score:** 16/100 (higher = better)  
**Control Coverage:** 0%  
**Attack Paths Identified:** 2  

**Controls Detected:** 0  
  None  

**Critical Gaps:** 17  
  least privilege, rate limiting, logging, patching, user training  

## 🛣️ Attack Path Analysis

### Path #1: CRITICAL Priority

| Attribute | Value |
|-----------|-------|
| **Entry Point** | Internet |
| **Target** | Database |
| **Attack Path** | Internet → WebServer → Database |
| **Hop Count** | 2 |
| **Criticality** | 0.96 |

**MITRE ATT&CK Techniques:**

- **T1190: Exploit Public-Facing Application**  
  Adversaries may attempt to exploit a weakness in an Internet-facing host or system to initially access a network.

- **T1133: External Remote Services**  
  Adversaries may leverage external-facing remote services to initially access and/or persist within a network.

- **T1059: Command and Scripting Interpreter**  
  Adversaries may abuse command and script interpreters to execute commands, scripts, or binaries.

- **T1203: Exploitation for Client Execution**  
  Adversaries may exploit software vulnerabilities in client applications to execute code.

- **T1213: Data from Information Repositories**  
  Adversaries may leverage information repositories to mine valuable information.

- **T1005: Data from Local System**  
  Adversaries may search local system sources, such as file systems, configuration files, local databases, virtual mach...

- **T1567: Exfiltration Over Web Service**  
  Adversaries may use an existing, legitimate external Web service to exfiltrate data rather than their primary command...

- **T1486: Data Encrypted for Impact**  
  Adversaries may encrypt data on target systems or on large numbers of systems in a network to interrupt availability ...

- **T1490: Inhibit System Recovery**  
  Adversaries may delete or remove built-in data and turn off services designed to aid in the recovery of a corrupted s...

- **T1485: Data Destruction**  
  Adversaries may destroy data and files on specific systems or in large numbers on a network to interrupt availability...

**Analysis:** [CRITICAL] Internet → Web Server → Database: 2 hops, criticality score 0.96

### Path #2: CRITICAL Priority

| Attribute | Value |
|-----------|-------|
| **Entry Point** | WebServer |
| **Target** | Database |
| **Attack Path** | WebServer → Database |
| **Hop Count** | 1 |
| **Criticality** | 0.93 |

**MITRE ATT&CK Techniques:**

- **T1213: Data from Information Repositories**  
  Adversaries may leverage information repositories to mine valuable information.

- **T1005: Data from Local System**  
  Adversaries may search local system sources, such as file systems, configuration files, local databases, virtual mach...

- **T1567: Exfiltration Over Web Service**  
  Adversaries may use an existing, legitimate external Web service to exfiltrate data rather than their primary command...

- **T1486: Data Encrypted for Impact**  
  Adversaries may encrypt data on target systems or on large numbers of systems in a network to interrupt availability ...

- **T1490: Inhibit System Recovery**  
  Adversaries may delete or remove built-in data and turn off services designed to aid in the recovery of a corrupted s...

- **T1485: Data Destruction**  
  Adversaries may destroy data and files on specific systems or in large numbers on a network to interrupt availability...

**Analysis:** [CRITICAL] Web Server → Database: 1 hop, criticality score 0.93
## 🎯 RAPIDS Threat Assessment

| Threat Category | Level | Risk Score | Defensibility | Assessment |
|----------------|-------|------------|---------------|------------|
| Application Vulns | 🔴 CRITICAL    | 80/100 | 10/100 | WAF: ✗, Input validation: ✗, Rate limiting: ✗ |
| Ransomware     | 🔴 CRITICAL    | 70/100 | 20/100 | Backup: ✗, EDR: ✗, Segmentation: ✗ |
| Denial of Service | 🔴 CRITICAL    | 70/100 | 10/100 | Load balancer: ✗, DDoS protection: ✗ |
| Phishing       | 🟠 HIGH        | 60/100 | 10/100 | MFA: ✗, Email gateway: ✗ |
| Supply Chain   | 🟠 HIGH        | 60/100 | 30/100 | Requires manual assessment of dependencies and third-part... |
| Insider Threat | 🟠 HIGH        | 50/100 | 20/100 | Audit logging: ✗, Least privilege: ✗ |

## 🔍 Control Gap Analysis

**Methodology:** RAPIDS-Driven, MITRE-Validated

- **PRIMARY:** RAPIDS threat assessment identifies what threats exist
- **VALIDATION:** Attack paths + MITRE techniques confirm exploitability

**Recommended Controls:**

| # | Control | Priority | Confidence | MITRE Mitigations | MITRE Techniques | Threat Context |
|---|---------|----------|------------|-------------------|------------------|----------------|
| 1 | **LEAST PRIVILEGE** | CRITICAL | 🟡 MEDIUM (79%) | M1016, M1018, M1026 +1 | T1059, T1133, T1190 +3 | Mitigates T1059 in path(s) #1, T1133 in path(s)... |
| 2 | **RATE LIMITING** | CRITICAL | 🟢 HIGH (87%) | M1033, M1035, M1037 | T1059, T1133, T1190 | Mitigates T1059 in path(s) #1, T1133 in path(s)... |
| 3 | **LOGGING** | CRITICAL | 🟢 HIGH (84%) | M1047 | T1059, T1213 | Mitigates T1059 in path(s) #1, T1213 in path(s)... |
| 4 | **PATCHING** | HIGH | 🟢 HIGH (81%) | M1017, M1051, M1054 | T1190, T1203, T1213 | Mitigates T1190 in path(s) #1, T1203 in path(s)... |
| 5 | **USER TRAINING** | HIGH | 🟠 LOW (46%) |  |  | Mitigates  |
| 6 | **BACKUP** | HIGH | 🟢 HIGH (100%) | M1053 | T1485, T1486, T1490 | Mitigates T1485 in path(s) #1, #2, T1486 in pat... |
| 7 | **EDR** | HIGH | 🟢 HIGH (93%) | M1040, M1049 | T1059, T1486 | Mitigates T1059 in path(s) #1, T1486 in path(s)... |
| 8 | **WAF** | HIGH | 🟢 HIGH (100%) | M1037, M1050 | T1190, T1203 | Mitigates T1190 in path(s) #1, T1203 in path(s)... |
| 9 | **INPUT VALIDATION** | HIGH | 🟢 HIGH (98%) | M1050 | T1190, T1203 | Mitigates T1190 in path(s) #1, T1203 in path(s)... |
| 10 | **MFA** | HIGH | 🟢 HIGH (96%) | M1032 | T1133, T1213, T1485 | Mitigates T1133 in path(s) #1, T1213 in path(s)... |
| 11 | **CODE SIGNING** | HIGH | 🟡 MEDIUM (78%) | M1038, M1045 | T1059, T1490 | Mitigates T1059 in path(s) #1, T1490 in path(s)... |
| 12 | **VULNERABILITY SCANNING** | HIGH | 🟡 MEDIUM (72%) | M1017 | T1213 | Mitigates T1213 in path(s) #1, #2 |
| 13 | **NETWORK SEGMENTATION** | HIGH | 🟢 HIGH (96%) | M1030 | T1133, T1190 | Mitigates T1133 in path(s) #1, T1190 in path(s)... |
| 14 | **AUDIT LOG** | HIGH | 🟢 HIGH (84%) | M1047 | T1059, T1213 | Mitigates T1059 in path(s) #1, T1213 in path(s)... |
| 15 | **BEHAVIORAL ANALYSIS** | HIGH | 🟢 HIGH (81%) | M1040 | T1059, T1486 | Mitigates T1059 in path(s) #1, T1486 in path(s)... |
| 16 | **DLP** | MEDIUM | 🟢 HIGH (90%) | M1057 | T1567, T1005 | Addresses 2 technique(s): T1567, T1005 |
| 17 | **WEB CONTENT FILTERING** | MEDIUM | 🟢 HIGH (90%) | M1021 | T1567 | Addresses 1 technique(s): T1567 |

**Recommended Implementation Order:**

1. Perimeter defenses (WAF, Firewall, DDoS protection)
2. Authentication (MFA, SSO, least privilege)
3. Detection & Response (EDR, SIEM, logging)
4. Data protection (Encryption, backup, DLP)

## ⚖️ Residual Risk Assessment

**Key Principle:** Even with ALL recommended controls implemented, residual risk remains.
No control is 100% effective - this is a realistic assessment for risk acceptance.

| Threat Category      | Initial | Control Effectiveness | Residual | Status   |
|---------------------|---------|----------------------|----------|----------|
| **Ransomware** | 70/100  | 100%                 | 0/100    | ✅ ACCEPT |
| ↳ *Controls:* least privilege, backup, edr, +1 more | | | | |
| **Application Vulns** | 80/100  | 100%                 | 0/100    | ✅ ACCEPT |
| ↳ *Controls:* rate limiting, patching, waf, +1 more | | | | |
| **Phishing** | 60/100  | 100%                 | 0/100    | ✅ ACCEPT |
| ↳ *Controls:* least privilege, logging, user training, +1 more | | | | |
| **Insider Threat** | 50/100  | 100%                 | 0/100    | ✅ ACCEPT |
| ↳ *Controls:* least privilege, logging, user training, +2 more | | | | |
| **Denial of Service** | 70/100  | 80%                  | 13/100   | ⚠️ MONITOR |
| ↳ *Controls:* rate limiting | | | | |
| **Supply Chain** | 60/100  | 91%                  | 5/100    | ✅ ACCEPT |
| ↳ *Controls:* code signing, vulnerability scanning | | | | |

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

## 🏗️ Architecture-Specific Recommendations

Web Application Security:
  • Deploy Web Application Firewall (WAF)
  • Implement input validation/sanitization
  • Add rate limiting to prevent abuse
  • Enable HTTPS/TLS encryption
  • Implement security headers (CSP, HSTS)
  • Add API authentication/authorization
