# Pentest report structure

Follow this skeleton for `security-assessment/REPORT.md`. It mirrors how a professional pentester writes: an executive summary a manager reads, a risk table anyone can scan, then evidenced findings, then the defensive and detection work. Fill every bracket; delete sections that genuinely don't apply and say why.

---

```markdown
# Security Assessment — <Project Name>

**Assessor:** Claude (ethical-hacking skill)  ·  **Date:** <YYYY-MM-DD>
**Target:** <path / repo>  ·  **Commit:** <git sha if available>
**Authorization:** Confirmed by user on <date>. Owner/authorized-tester: yes.
**Depth:** <A static | B static+safe probes | C +scanners | D +exploitation>
**Scope:** <app code, deps, secrets/git-history, infra/CI, business logic>
**Out of scope:** <what the user excluded>

## 1. Executive summary
2–4 sentences, non-technical. What the system is, the overall risk posture, and
the single most important thing to fix. No jargon.

## 2. Risk summary
| ID | Finding | Severity | Confirmed? | Fix effort |
|----|---------|----------|-----------|-----------|
| RT-01 | <short title> | Critical | Executed / Static | Low |
| RT-02 | … | High | … | Medium |

Severity counts: **Critical N · High N · Medium N · Low N**

## 3. Methodology & rules of engagement
How the assessment was run, what depth meant in practice, what was and wasn't
executed, and the limits of coverage (be explicit — static review ≠ proof of safety).

## 4. Red team — findings
For EACH finding:

### RT-0X — <title>  ·  Severity: <level>
- **Component:** `path/to/file.ext:LINE`
- **Confidence:** Confirmed by execution | UNCONFIRMED (static)
- **Description:** what the flaw is and why it exists.
- **Attack path:** how an attacker reaches and abuses it. Include a Mermaid
  diagram for non-trivial paths:
  ```mermaid
  flowchart LR
    A[Untrusted input] --> B[handler] --> C[(sink)]
  ```
- **Evidence — what I did and the result:**
  - Command / probe:
    ```
    <exact command>
    <raw output>
    ```
    (full transcript: `evidence/RT-0X-cmd.txt`)
  - Screenshot: `![RT-0X](evidence/RT-0X.png)` — or "no browser available; transcript only."
- **Impact:** what an attacker gains — data, control, downtime.
- **Remediation pointer:** → see BT-0X.

## 5. Blue team — remediation plan
Prioritized. Quick wins first, then structural fixes.

### Do today (quick wins)
1. <fix> — closes RT-0X. <one-line how>.

### Structural / class-closing fixes
- **BT-0X →** fixes RT-0X (and RT-0Y): <specific change, code/config-level,
  matched to the stack>. Effort: <L/M/H>. Risk reduced: <high/…>.

## 6. Purple team — detection & incident response
Per significant finding:

### PT-0X — detecting/responding to RT-0X
- **Indicators of compromise:** <log patterns / request signatures / anomalies
  specific to THIS system>.
- **Check now:** `<command or log query>` — result: <ran it: clean / signs found / not run because…>.
- **If active:** Contain → <step>. Eradicate → <step>. Recover → <step>.
  Preserve evidence: <how>.

## 7. Appendix
- Tool versions, scan outputs, evidence file index (`evidence/`), and any
  scope items skipped with the reason.
```

---

## Rules
- **Every finding must carry evidence** of what was done and the result. No evidence → label **UNCONFIRMED** and say why.
- **Never fabricate** a transcript, a screenshot, or a CVE number. A missing screenshot is stated as missing. Before writing any CVE ID or affected-version range, run it through `factcheck` or mark it **UNVERIFIED** (SKILL.md rule 7).
- **Severity is impact × exploitability**, with a one-line rationale — not a category default.
- Cross-reference IDs (RT ↔ BT ↔ PT) so red, blue, and purple stay linked.
