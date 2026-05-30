#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
ARC_DIR="$REPO_ROOT/chatbot/data/arc"
BASE_URL="https://raw.githubusercontent.com/govtech-responsibleai/agentic-risk-capability-framework/main/arc-risk-register"
FILES=(capabilities.yaml components.yaml controls.yaml design.yaml risks.yaml)

mkdir -p "$ARC_DIR"

echo "Downloading ARC risk register YAML files..."
for f in "${FILES[@]}"; do
    echo -n "  $f ... "
    curl -fsSL "$BASE_URL/$f" -o "$ARC_DIR/$f.tmp"
    python3 -c "import yaml; yaml.safe_load(open('$ARC_DIR/$f.tmp'))" && echo "OK" || { echo "INVALID YAML — aborting"; rm -f "$ARC_DIR/$f.tmp"; exit 1; }
    mv "$ARC_DIR/$f.tmp" "$ARC_DIR/$f"
done

echo "Done. Review new RISK-* entries in risks.yaml for relevance to chatbot/modules/patterns/ai_pattern.py."
