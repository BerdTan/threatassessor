#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
ATLAS_DIR="$REPO_ROOT/chatbot/data/atlas"
BASE_URL="https://raw.githubusercontent.com/mitre-atlas/atlas-data/main/data"
FILES=(AML.T0000.yaml tactics.yaml techniques.yaml mitigations.yaml matrix.yaml)

mkdir -p "$ATLAS_DIR"

echo "Downloading ATLAS YAML files..."
for f in "${FILES[@]}"; do
    echo -n "  $f ... "
    curl -fsSL "$BASE_URL/$f" -o "$ATLAS_DIR/$f.tmp"
    python3 -c "import yaml; yaml.safe_load(open('$ATLAS_DIR/$f.tmp'))" && echo "OK" || { echo "INVALID YAML — aborting"; rm -f "$ATLAS_DIR/$f.tmp"; exit 1; }
    mv "$ATLAS_DIR/$f.tmp" "$ATLAS_DIR/$f"
done

# Force cache rebuild on next startup
rm -f "$ATLAS_DIR/atlas_cache.pkl"
echo "Done. atlas_cache.pkl deleted — will rebuild on next API start."
