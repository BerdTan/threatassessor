---
name: update-data
description: Refreshes threat intelligence data in chatbot/data/. Updates MITRE ATT&CK (enterprise-attack.json), ATLAS YAML files, SSP catalog (via scrape script), and ARC risk register YAML from GovTech GitHub. Use quarterly or when a new MITRE/ATLAS release is published. Always backs up before replacing. After MITRE update, prompts to run build-embeddings-cache.
allowed-tools: Bash(wget:*) Bash(curl:*) Bash(python3:*) Bash(mv:*) Bash(cp:*) Bash(mkdir:*)
compatibility: Requires internet access and python3 with pyyaml installed.
---

# Update Data

Run each section independently as needed, or all four in sequence for a full quarterly refresh.

## 1 — MITRE ATT&CK

```bash
bash .claude/skills/update-data/scripts/update-mitre.sh
```

Downloads `enterprise-attack.json` from mitre/cti GitHub, validates JSON, timestamps a backup, replaces in `chatbot/data/`. After completion, run `/build-embeddings-cache` to regenerate `technique_embeddings.json`.

## 2 — ATLAS

```bash
bash .claude/skills/update-data/scripts/update-atlas.sh
```

Fetches the 5 ATLAS YAML files from `mitre-atlas/atlas-data` into `chatbot/data/atlas/`. Deletes `atlas_cache.pkl` so the pickle regenerates on next startup. Validates YAML parse before replacing.

## 3 — SSP Catalog

```bash
cd /mnt/c/BACKUP/DEV-TEST
python3 scripts/ingest/scrape_ssp_catalog.py
```

Runs the existing scraper. Verify output:
```bash
ls -lh chatbot/data/ssp/
python3 -c "import json; d=json.load(open('chatbot/data/ssp/cybersecurity_catalog.json')); print(f'{len(d)} entries')"
```

## 4 — ARC Risk Register

```bash
bash .claude/skills/update-data/scripts/update-arc.sh
```

Fetches 5 YAML files (capabilities, components, controls, design, risks) from `govtech-responsibleai/agentic-risk-capability-framework/arc-risk-register` into `chatbot/data/arc/`. Validates YAML parse. Note: ARC is a living standard — review release notes before replacing `controls.yaml` as local customisations may exist.

## 5 — CAVEAT (Cloud Adversarial, Vulnerability, Exploitation, and Threat)

```bash
cd /mnt/c/BACKUP/DEV-TEST
python3 scripts/data/fetch_caveat.py
```

Fetches `CAVEaT-all-entries.md` from `CloudSecurityAlliance-WG/CAVEaT` GitHub (CC0-1.0),
parses 60+ cloud attack techniques with CSP-specific mitigations/detection (AWS/Azure/GCP),
and writes `chatbot/data/caveat/caveat_techniques.yaml` (git-ignored, backed up before replace).

Verify output:
```bash
python3 -c "
import yaml
d = yaml.safe_load(open('chatbot/data/caveat/caveat_techniques.yaml'))
print(f\"{d['count']} CAVEAT techniques loaded\")
print('First:', d['techniques'][0]['title'])
"
```

Note: `chatbot/data/caveat/caveat_mitre_mapping.yaml` is hand-authored and committed to git.
Do NOT overwrite it with the fetch script.

## 6 — CCM (CSA Cloud Controls Matrix → ATT&CK Mapping)

```bash
cd /mnt/c/BACKUP/DEV-TEST
python3 scripts/data/fetch_ccm.py
```

Fetches the CTID Mappings Explorer CSA CCM v4.1 → ATT&CK Enterprise YAML (Apache 2.0),
indexes 792 `mitigates` entries into two output files in `chatbot/data/ccm/` (git-ignored):
- `ccm_by_technique.yaml` — T#### → [{ccm_id, description, group, comments}]
- `ccm_by_control.yaml`   — ccm_id → {description, group, techniques}

Verify output:
```bash
python3 -c "
import yaml
d = yaml.safe_load(open('chatbot/data/ccm/ccm_by_technique.yaml'))
print(f\"{d['technique_count']} techniques mapped\")
import yaml
d2 = yaml.safe_load(open('chatbot/data/ccm/ccm_by_control.yaml'))
print(f\"{d2['control_count']} CCM controls indexed\")
"
```

## After Full Refresh

```
MITRE updated  → run /build-embeddings-cache (regenerates 45 MB embeddings, ~3 min)
ATLAS updated  → atlas_cache.pkl deleted; cache auto-rebuilds on next API start
SSP updated    → no further action needed
ARC updated    → review new RISK-* entries for relevance to ai_pattern.py
CAVEAT updated → no further action; CloudPattern loads from YAML at startup
CCM updated    → no further action; CcmHelper loads from YAML at startup
```
