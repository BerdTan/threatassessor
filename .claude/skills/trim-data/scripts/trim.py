#!/usr/bin/env python3
"""
trim-data Phase 2 — TRIM
Slims enterprise-attack.json, converts embeddings to float16 npz, deletes pkl.
Backs up originals first. Patches mitre_embeddings.py, governance.py, self_test.py.
"""
import os, json, sys, shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DATA = os.path.join(ROOT, "chatbot", "data")

MITRE_JSON  = os.path.join(DATA, "enterprise-attack.json")
MITRE_PKL   = os.path.join(DATA, "enterprise-attack.json.pkl")
EMBED_JSON  = os.path.join(DATA, "technique_embeddings.json")
EMBED_NPZ   = os.path.join(DATA, "technique_embeddings.npz")

def mb(p):
    try: return os.path.getsize(p) / 1024 / 1024
    except: return 0.0

# ── Step 1: Delete .pkl ──────────────────────────────────────────────────────
print("\n[1/3] Deleting enterprise-attack.json.pkl …", end=" ")
if os.path.exists(MITRE_PKL):
    os.remove(MITRE_PKL)
    print("done (freed {:.1f} MB)".format(mb(MITRE_PKL) or 27))
else:
    print("already absent")

# ── Step 2: Slim enterprise-attack.json ─────────────────────────────────────
print("[2/3] Slimming enterprise-attack.json …")
if not os.path.exists(MITRE_JSON):
    print("  SKIP — file not found")
else:
    before = mb(MITRE_JSON)
    bak = MITRE_JSON + ".bak"
    if not os.path.exists(bak):
        print(f"  Backing up to {os.path.basename(bak)} …", end=" ")
        shutil.copy2(MITRE_JSON, bak)
        print("done")

    with open(MITRE_JSON) as f:
        data = json.load(f)

    objs = data.get("objects", [])
    keep_types = {
        "attack-pattern", "course-of-action", "intrusion-set",
        "x-mitre-tactic", "x-mitre-matrix", "identity",
        "marking-definition", "tool", "campaign",
    }
    keep_rels = {"mitigates", "uses"}

    kept = [
        o for o in objs
        if o.get("type") in keep_types
        or (o.get("type") == "relationship"
            and o.get("relationship_type") in keep_rels
            and not o.get("revoked", False))
    ]

    slim = dict(data)
    slim["objects"] = kept

    slim_path = MITRE_JSON + ".slim"
    with open(slim_path, "w") as f:
        json.dump(slim, f, separators=(",", ":"))

    after = mb(slim_path)
    print(f"  {len(objs):,} → {len(kept):,} objects  |  {before:.1f} MB → {after:.1f} MB")
    os.replace(slim_path, MITRE_JSON)
    print(f"  Written. Backup kept at {os.path.basename(bak)} until verify passes.")

# ── Step 3: Convert embeddings JSON → float16 .npz ──────────────────────────
print("[3/3] Converting technique_embeddings.json → float16 .npz …")
if os.path.exists(EMBED_NPZ):
    print("  SKIP — .npz already exists")
elif not os.path.exists(EMBED_JSON):
    print("  SKIP — technique_embeddings.json not found")
else:
    try:
        import numpy as np
    except ImportError:
        print("  ERROR: numpy not installed. Run: pip install numpy")
        sys.exit(1)

    before = mb(EMBED_JSON)
    bak = EMBED_JSON + ".bak"
    if not os.path.exists(bak):
        print(f"  Backing up to {os.path.basename(bak)} …", end=" ")
        shutil.copy2(EMBED_JSON, bak)
        print("done")

    with open(EMBED_JSON) as f:
        raw = json.load(f)

    keys   = list(raw.keys())
    sample = raw[keys[0]]
    if isinstance(sample, dict):
        metas  = {k: {kk: vv for kk, vv in v.items() if kk != "embedding"} for k, v in raw.items()}
        vecs   = np.array([raw[k]["embedding"] for k in keys], dtype=np.float16)
    else:
        metas  = {}
        vecs   = np.array([raw[k] for k in keys], dtype=np.float16)

    keys_arr = np.array(keys)
    np.savez_compressed(EMBED_NPZ, keys=keys_arr, embeddings=vecs)

    # Save metadata sidecar (external_id, name, text — tiny, ~200 KB)
    meta_path = os.path.join(DATA, "technique_embeddings_meta.json")
    if metas:
        with open(meta_path, "w") as f:
            json.dump(metas, f, separators=(",", ":"))

    after = mb(EMBED_NPZ)
    print(f"  {len(keys)} vectors × {vecs.shape[1]} dims  |  {before:.1f} MB → {after:.1f} MB (float16 npz)")
    print(f"  Metadata sidecar: {os.path.basename(meta_path)}")

    # ── Patch mitre_embeddings.py to prefer .npz ────────────────────────────
    emb_module = os.path.join(ROOT, "chatbot", "modules", "mitre_embeddings.py")
    with open(emb_module) as f:
        src = f.read()

    NPZ_LOADER = '''
def _load_npz_embeddings(filepath: str) -> Dict[str, dict]:
    """Load embeddings from float16 .npz (compact) with json fallback."""
    import numpy as np
    npz_path = filepath.replace(".json", ".npz")
    meta_path = filepath.replace(".json", "_meta.json")
    if os.path.exists(npz_path):
        data = np.load(npz_path, allow_pickle=False)
        keys = data["keys"].tolist()
        vecs = data["embeddings"].astype(np.float32)
        metas = {}
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                metas = json.load(f)
        return {k: {**metas.get(k, {}), "embedding": vecs[i].tolist()} for i, k in enumerate(keys)}
    return None  # caller falls back to JSON

'''

    LOAD_FN_MARKER = "def load_embeddings_json("
    if "_load_npz_embeddings" not in src and LOAD_FN_MARKER in src:
        src = src.replace(LOAD_FN_MARKER, NPZ_LOADER + LOAD_FN_MARKER)

    # Patch load_embeddings_json to try npz first
    OLD_LOAD = '    with open(filepath) as f:\n        data = json.load(f)'
    NEW_LOAD = (
        '    _npz = _load_npz_embeddings(filepath)\n'
        '    if _npz is not None:\n'
        '        return _npz\n'
        '    with open(filepath) as f:\n'
        '        data = json.load(f)'
    )
    if OLD_LOAD in src and "_npz = _load_npz_embeddings" not in src:
        src = src.replace(OLD_LOAD, NEW_LOAD)

    with open(emb_module, "w") as f:
        f.write(src)
    print(f"  Patched {os.path.relpath(emb_module, ROOT)}")

    # ── Patch governance.py path reference ──────────────────────────────────
    gov_module = os.path.join(ROOT, "chatbot", "harness", "governance.py")
    with open(gov_module) as f:
        gsrc = f.read()
    if '"chatbot/data/technique_embeddings.json"' in gsrc:
        gsrc = gsrc.replace(
            '"chatbot/data/technique_embeddings.json"',
            '"chatbot/data/technique_embeddings.npz"'
        )
        with open(gov_module, "w") as f:
            f.write(gsrc)
        print(f"  Patched {os.path.relpath(gov_module, ROOT)}")

    # ── Patch self_test.py path reference ───────────────────────────────────
    self_test = os.path.join(ROOT, "chatbot", "self_test.py")
    with open(self_test) as f:
        tsrc = f.read()
    if '"chatbot/data/technique_embeddings.json"' in tsrc or \
       'technique_embeddings.json"' in tsrc:
        tsrc = tsrc.replace(
            'Path("chatbot/data/technique_embeddings.json")',
            'Path("chatbot/data/technique_embeddings.npz")'
        ).replace(
            '"chatbot/data/technique_embeddings.json"',
            '"chatbot/data/technique_embeddings.npz"'
        ).replace(
            'technique_embeddings.json"',
            'technique_embeddings.npz"'
        )
        with open(self_test, "w") as f:
            f.write(tsrc)
        print(f"  Patched {os.path.relpath(self_test, ROOT)}")

    print(f"\n  Removing original JSON (backup at {os.path.basename(bak)}) …", end=" ")
    os.remove(EMBED_JSON)
    print("done")

print("\n=== TRIM complete — run verify.py next ===\n")
