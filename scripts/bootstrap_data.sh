#!/usr/bin/env bash
# Bootstrap ThreatAssessor data files on a fresh clone.
# Downloads the trimmed MITRE + embeddings bundle (~14 MB) from GitHub Releases.
# Run once after cloning: bash scripts/bootstrap_data.sh
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
URL="https://github.com/BerdTan/threatassessor/releases/download/data-v1.0/data_bundle.tar.gz"
BUNDLE="$ROOT/data_bundle.tar.gz"

echo "Downloading data bundle from GitHub Releases …"
curl -fL "$URL" -o "$BUNDLE"
echo "Extracting …"
tar -xzf "$BUNDLE" -C "$ROOT"
rm "$BUNDLE"
echo "Done. Data files installed in chatbot/data/."
