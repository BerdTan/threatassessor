name: trim-data
description: Reduce chatbot/data/ from ~116 MB to ~42 MB for portability — strip unused MITRE object types, convert embeddings to numpy float16, delete the pkl cache, and optionally package data files as a GitHub Release asset with a bootstrap download script. Run before exporting or cloning to a new machine.
allowed-tools: Bash(python3:*) Bash(ls:*) Bash(du:*) Bash(rm:*) Bash(gzip:*) Bash(gunzip:*) Read Write Edit

# Trim Data

Four phases: **AUDIT → TRIM → VERIFY → PACKAGE**.

Audit is always read-only. Trim and Package require explicit user confirmation between phases.

---

## Phase 1 — AUDIT (always run first, no side effects)

```bash
ROOT=$(git rev-parse --show-toplevel)
python3 "$ROOT/.claude/skills/trim-data/scripts/audit.py"
```

Prints a table:

| File | Current size | Trimmed estimate | Method |
|------|-------------|-----------------|--------|
| enterprise-attack.json | 44 MB | ~35 MB | Strip 4,606 unused object types |
| enterprise-attack.json.pkl | 27 MB | 0 MB | Delete (auto-regenerates) |
| technique_embeddings.json | 45 MB | ~3.3 MB | Convert to float16 .npz |
| Total | ~116 MB | ~42 MB | |

Then ask: "Proceed with TRIM phase? (y/n)"

---

## Phase 2 — TRIM

Run only after user confirms.

```bash
ROOT=$(git rev-parse --show-toplevel)
python3 "$ROOT/.claude/skills/trim-data/scripts/trim.py"
```

### What trim.py does

**Step 1 — Delete .pkl:**
```
rm chatbot/data/enterprise-attack.json.pkl
```
Regenerates automatically on next load (3× slower first load, then cached again).

**Step 2 — Slim enterprise-attack.json:**

Keep only these object types (everything the app uses):
- `attack-pattern` (835 techniques)
- `course-of-action` (268 mitigations)
- `relationship` — **only** where `relationship_type` is `mitigates` or `uses` (not all 20k)
- `intrusion-set` (187 groups)
- `x-mitre-tactic` (14 tactics)
- `x-mitre-matrix` (1)
- `identity` (1)
- `marking-definition` (1)
- `tool` (91)
- `campaign` (52)

Drop entirely:
- `x-mitre-analytic` (1,739 — 3 MB, never read)
- `x-mitre-detection-strategy` (691 — 0.6 MB, never read)
- `malware` (696 — 1.2 MB, never directly used)
- `x-mitre-data-component` (109)
- `x-mitre-data-source` (38)
- Relationships where type is NOT `mitigates` or `uses` (drops ~18k of 20k relationships)

Writes to `chatbot/data/enterprise-attack.slim.json`, then renames over original after verification.

Always backs up original first: `enterprise-attack.json.bak` (deleted after verification passes).

**Step 3 — Convert technique_embeddings.json → .npz:**

Converts the 834 × 2048 float64 JSON array to a numpy float16 compressed archive:
- Saves `chatbot/data/technique_embeddings.npz` (~3.3 MB)
- Patches `chatbot/modules/mitre_embeddings.py`: adds npz loader that falls back to json if npz absent
- Patches `chatbot/harness/governance.py`: update path reference
- Patches `chatbot/self_test.py`: update embeddings path check

JSON file kept until verify passes, then deleted (or kept as `.json.bak`).

---

## Phase 3 — VERIFY

Runs automatically after TRIM, non-interactive.

```bash
ROOT=$(git rev-parse --show-toplevel)
python3 "$ROOT/.claude/skills/trim-data/scripts/verify.py"
```

Checks:
1. MITRE loads cleanly: `MitreHelper(use_local=True)` — ≥835 techniques, ≥268 mitigations
2. Embeddings load: npz loads, shape is (834, 2048), cosine similarity on one query returns a float
3. Relationships intact: T1059 → at least 3 mitigations resolved
4. No pkl file present

Prints pass/fail per check. On any failure: prints rollback instructions (rename `.bak` files back).

---

## Phase 4 — PACKAGE (optional, for portability)

Run only if user wants to export for a new machine without an API key.

```bash
ROOT=$(git rev-parse --show-toplevel)
python3 "$ROOT/.claude/skills/trim-data/scripts/package.py" [--gh-release]
```

**Without `--gh-release`:** Creates `data_bundle.tar.gz` in repo root:
```
chatbot/data/enterprise-attack.json   (~9 MB)
chatbot/data/technique_embeddings.npz  (~3.3 MB)
chatbot/data/atlas/                    (230 KB)
chatbot/data/kev/                      (1.3 MB)
chatbot/data/arc/                      (4 KB)
chatbot/data/ssp/                      (small, tracked)
chatbot/data/engine_hints.json
```
Total bundle: ~14 MB. Can be `scp`'d or attached to a GitHub Release manually.

**With `--gh-release`:** Uses `gh release create` to upload the bundle as an asset to a new GitHub Release tag (e.g. `data-v1.0`). Also writes `scripts/bootstrap_data.sh` which downloads + extracts the bundle on a fresh clone:
```bash
# scripts/bootstrap_data.sh
#!/bin/bash
set -e
ROOT=$(git rev-parse --show-toplevel)
GH_RELEASE_URL="https://github.com/OWNER/REPO/releases/download/data-v1.0/data_bundle.tar.gz"
curl -L "$GH_RELEASE_URL" | tar -xz -C "$ROOT"
echo "Data files installed."
```

`scripts/bootstrap_data.sh` IS committed to git. The bundle is not.

---

## Rollback

If anything breaks after TRIM:

```bash
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"
# Restore MITRE JSON
mv chatbot/data/enterprise-attack.json.bak chatbot/data/enterprise-attack.json
# Restore embeddings JSON
mv chatbot/data/technique_embeddings.json.bak chatbot/data/technique_embeddings.json
# Remove npz
rm -f chatbot/data/technique_embeddings.npz
# Revert code patches (git restore covers the 3 patched files)
git restore chatbot/modules/mitre_embeddings.py chatbot/harness/governance.py chatbot/self_test.py
```

---

## Related skills
- `/build-embeddings-cache` — regenerate embeddings from scratch (needs API key, ~3 min)
- `/quick-test` — sanity check after trim that MITRE + embeddings still load
- `/update-data` — refresh MITRE/ATLAS/SSP/ARC data from upstream sources
- `/repo-organise` — audit and prune stale report/ directories
