---
name: check-skills
description: Supply-chain and phishing audit of the .claude/skills/ corpus. Checks git integrity, external URLs, allowed-tools gaps, script supply-chain patterns, and social engineering phrases. Read-only — outputs a findings table and waits for user approval before any action. Run after adding or modifying skills, or as part of /session-cleanup.
allowed-tools: Bash(git:*) Bash(grep:*) Bash(find:*) Bash(ls:*) Bash(python3:*) Read
---

# check-skills — Skill Supply-Chain & Phishing Audit

Read-only corpus-wide sweep of `.claude/skills/`. No writes until user approves. Surfaces supply-chain and phishing risks that DETECT-028 (runtime skill tamper) cannot catch alone — including committed-but-malicious content, embedded phishing URLs, and unconstrained tool scope.

---

## Phase 1 — Git Integrity

```bash
ROOT=$(git rev-parse --show-toplevel)

# Files in .claude/skills/ that differ from HEAD (uncommitted changes)
git diff --name-only HEAD "$ROOT/.claude/skills/"

# Most recent commit touching the skill directory
git log --oneline -3 -- "$ROOT/.claude/skills/"
```

Core skills (flag as **Critical** if modified):
`check-detect`, `run-er`, `detect-loop`, `check-governance`, `aivss-gate`, `check-mcp`, `check-eventbroker`, `tatb-loop`

Other skills: flag as **High** if diff is present.

Clean = ✅. Any diff = report the file, whether it is a core skill or not.

---

## Phase 2 — URL Audit (phishing / supply-chain link detection)

```bash
ROOT=$(git rev-parse --show-toplevel)
grep -rEn "https?://[^ )>\"',\`]+" "$ROOT/.claude/skills/" \
  --include="*.md" --include="*.py" --include="*.sh" \
  | grep -v "localhost\|127\.0\.0\.1\|0\.0\.0\.0\|host:8000\|host:3000"
```

Classify every URL found:

| Class | Criteria | Severity |
|---|---|---|
| `TRUSTED` | `github.com/mitre`, `github.com/govtech-responsibleai`, `medium.com/@breadtan`, project localhost refs | ✅ Pass |
| `REVIEW` | Any other `github.com/*`, `docs.*`, `pypi.org`, `anthropic.com` | ⚠ Medium — confirm intent |
| `PLACEHOLDER` | Contains `OWNER`, `REPO`, `example.com`, `YOUR_`, `<host>` | ⚠ High if in `curl`/`wget`/`fetch` context (pipe-to-execute without integrity check) |
| `SUSPICIOUS` | URL-shorteners (bit.ly, t.co, tinyurl.com, ow.ly), uncommon TLDs (.xyz, .tk, .ru, .cn unless explicitly expected), raw IPv4/IPv6, non-standard ports on external hosts | ❌ High |

Known pre-existing finding to confirm:
- `trim-data/SKILL.md`: `GH_RELEASE_URL="https://github.com/OWNER/REPO/..."` piped into `curl -L ... | tar -xz` — **High** (PLACEHOLDER in pipe-to-extract; no checksum verification)

---

## Phase 3 — `allowed-tools` Completeness

```bash
ROOT=$(git rev-parse --show-toplevel)
for f in "$ROOT"/.claude/skills/*/SKILL.md "$ROOT"/.claude/skills/*/skill.md; do
  [ -f "$f" ] || continue
  skill=$(basename $(dirname "$f"))
  grep -q "allowed-tools" "$f" && echo "✅ $skill" || echo "⚠  MISSING: $skill"
done
```

**Medium** — skills without `allowed-tools` have implicit wildcard tool scope (any tool Claude Code has). This is appropriate for some skills by design (e.g. `harden-audit`, `rerun-moe`, `skill-stress-test` intentionally need broad access). Mark confirmed intentional exemptions; flag the rest.

Known exemptions to confirm with user (intentionally broad):
`harden-audit`, `rerun-moe`, `skill-stress-test`, `critic-improve-loop`, `taco-run`, `taco-infer`, `taco-check`, `bughunt`

---

## Phase 4 — Script Supply-Chain Patterns

```bash
ROOT=$(git rev-parse --show-toplevel)

# curl|bash or wget|sh — arbitrary code exec without integrity check
grep -rEn "curl[^|]+\|[[:space:]]*(bash|sh)|wget[^|]+\|[[:space:]]*(bash|sh)" \
  "$ROOT/.claude/skills/" --include="*.sh" --include="*.py" --include="*.md"

# pip install without pinned version (no == or >=)
grep -rEn "pip install [^=<>'\"]" \
  "$ROOT/.claude/skills/" --include="*.sh" --include="*.py" --include="*.md"

# Mutable branch refs in download scripts (should be pinned to commit SHA)
grep -rEn "raw\.githubusercontent\.com/[^/]+/[^/]+/(main|master)/" \
  "$ROOT/.claude/skills/" --include="*.sh"

# pipe-to-extract without hash check
grep -rEn "curl[^|]+\|[[:space:]]*tar|wget[^|]+\|[[:space:]]*tar" \
  "$ROOT/.claude/skills/" --include="*.sh" --include="*.md"
```

Severity:
- `curl | bash` / `wget | sh` — **Critical** (RCE vector)
- `pip install` unversioned — **Medium**
- Mutable branch refs (`main`/`master`) in download scripts — **Medium** (three known instances: `update-data/` scripts for MITRE, ATLAS, ARC data)
- `curl | tar` without hash — **Medium** (no artifact integrity check)

---

## Phase 5 — Social Engineering / Phishing Phrase Detection

```bash
ROOT=$(git rev-parse --show-toplevel)
grep -rEin \
  "(click here|urgent.?action.?required|verify your identity|enter your (password|api.?key|token|secret)|you have been selected|congratulations.*access|free.?access|login to claim|account.*suspended|your session.*expired|security alert.*click)" \
  "$ROOT/.claude/skills/" --include="*.md"
```

Any match: **High**. These phrases have no legitimate place in developer skill instructions; their presence in a skill file is a strong indicator of social-engineering injection or supply-chain compromise.

Also check for hidden instruction payloads — zero-width chars, Cyrillic homoglyphs, or HTML comments in skill .md files:

```bash
ROOT=$(git rev-parse --show-toplevel)
# HTML comments (<!--...-->) — injection vector (DETECT-027 class)
grep -rEn "<!--.*-->" "$ROOT/.claude/skills/" --include="*.md"

# Zero-width / control chars
grep -rPn "[\x00-\x08\x0b-\x1f\x7f\xc2\xad]" "$ROOT/.claude/skills/" --include="*.md" 2>/dev/null || true
```

---

## Output Format

Present all findings in a single table, most severe first:

```
| # | Sev | Phase | Skill | File | Line | Finding |
|---|-----|-------|-------|------|------|---------|
| 1 | High | URL | trim-data | SKILL.md | 134 | PLACEHOLDER URL in curl pipe — GH_RELEASE_URL not set, no hash |
| 2 | Med | allowed-tools | factcheck | SKILL.md | — | No allowed-tools declared |
...
```

Then: **"Apply any remediation? (list #s or skip)"**

Remediation options per finding type:
- **Git diff**: `git diff .claude/skills/<skill>/` then propose discard or commit
- **Suspicious URL**: propose removal or replacement with trusted equivalent
- **Missing allowed-tools**: propose minimal set based on commands the skill actually uses
- **Mutable branch ref**: propose pinning to a specific commit SHA
- **Phishing phrase / HTML comment**: propose removal

After applying: run Phase 1 again to confirm git is clean.

---

## Integration

Run standalone or as part of `/session-cleanup` (Phase 2b — between memory check and docs staleness).

```bash
# Standalone
/check-skills

# After any skill modification before committing
/check-skills
```
