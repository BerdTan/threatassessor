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

echo "Slimming — stripping unused object types..."
export TARGET
python3 - <<'PYEOF'
import json, os, sys

src  = os.environ["TARGET"] + ".tmp"
out  = os.environ["TARGET"] + ".slim"

KEEP_TYPES = {"attack-pattern","course-of-action","intrusion-set",
              "x-mitre-tactic","x-mitre-matrix","identity","marking-definition",
              "tool","campaign"}
KEEP_RELS  = {"mitigates","uses"}

with open(src) as f:
    data = json.load(f)

before = len(data["objects"])
data["objects"] = [
    o for o in data["objects"]
    if o.get("type") in KEEP_TYPES
    or (o.get("type") == "relationship"
        and o.get("relationship_type") in KEEP_RELS
        and not o.get("revoked", False))
]
after = len(data["objects"])

with open(out, "w") as f:
    json.dump(data, f, separators=(",",":"))

before_mb = os.path.getsize(src) / 1024 / 1024
after_mb  = os.path.getsize(out) / 1024 / 1024
print(f"  {before:,} → {after:,} objects  |  {before_mb:.1f} MB → {after_mb:.1f} MB")
PYEOF

STAMP=$(date +%Y%m%d_%H%M%S)
[ -f "$TARGET" ] && cp "$TARGET" "$BACKUP_DIR/enterprise-attack_$STAMP.json"
mv "$TARGET.slim" "$TARGET"
rm -f "$TARGET.tmp"

# Delete stale pickle — will regenerate on next startup
rm -f "$DATA_DIR/enterprise-attack.json.pkl"

echo "Done. Run /build-embeddings-cache to regenerate technique_embeddings.npz."
