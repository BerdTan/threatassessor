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

## After Full Refresh

```
MITRE updated  → run /build-embeddings-cache (regenerates 45 MB embeddings, ~3 min)
ATLAS updated  → atlas_cache.pkl deleted; cache auto-rebuilds on next API start
SSP updated    → no further action needed
ARC updated    → review new RISK-* entries for relevance to ai_pattern.py
```
