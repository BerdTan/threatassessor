#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

echo "Fetching CISA KEV + CTID KEV→ATT&CK mappings..."
python3 "$REPO_ROOT/scripts/data/fetch_kev.py"

echo ""
python3 -c "
import json
from pathlib import Path
meta = json.loads((Path('$REPO_ROOT') / 'chatbot/data/kev/kev_meta.json').read_text())
print(f\"  CTID: {meta['ctid_technique_count']} techniques, {meta['ctid_total_mappings']} CVE-technique links ({meta['ctid_kev_date']})\")
print(f\"  CISA: {meta['cisa_cve_count']} CVEs, {meta['cisa_ransomware_count']} ransomware-linked\")
print(f\"  Fetched: {meta['fetched_at']}\")
"
echo "Done. No further action needed — KevHelper loads from JSON at startup."
