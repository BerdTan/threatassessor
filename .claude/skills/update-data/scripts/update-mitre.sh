#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
DATA_DIR="$REPO_ROOT/chatbot/data"
BACKUP_DIR="$DATA_DIR/backups"
URL="https://raw.githubusercontent.com/mitre/cti/refs/heads/master/enterprise-attack/enterprise-attack.json"
TARGET="$DATA_DIR/enterprise-attack.json"

mkdir -p "$BACKUP_DIR"

echo "Downloading enterprise-attack.json..."
wget -q --show-progress -O "$TARGET.tmp" "$URL"

echo "Validating JSON..."
python3 -c "import json,sys; d=json.load(open('$TARGET.tmp')); t=len([o for o in d.get('objects',[]) if o.get('type')=='attack-pattern']); print(f'  {t} techniques found'); sys.exit(0 if t > 800 else 1)"

STAMP=$(date +%Y%m%d_%H%M%S)
[ -f "$TARGET" ] && cp "$TARGET" "$BACKUP_DIR/enterprise-attack_$STAMP.json"
mv "$TARGET.tmp" "$TARGET"

# Delete stale pickle — will regenerate on next startup
rm -f "$DATA_DIR/enterprise-attack.json.pkl"

echo "Done. Run /build-embeddings-cache to regenerate technique_embeddings.json."
