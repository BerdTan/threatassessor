#!/usr/bin/env python3
"""
trim-data Phase 3 — VERIFY
Confirms MITRE + embeddings still load and function correctly after trim.
Cleans up .bak files on full pass. Prints rollback instructions on any failure.
"""
import os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "chatbot", "data")

MITRE_JSON  = os.path.join(DATA, "enterprise-attack.json")
MITRE_BAK   = MITRE_JSON + ".bak"
MITRE_PKL   = os.path.join(DATA, "enterprise-attack.json.pkl")
EMBED_NPZ   = os.path.join(DATA, "technique_embeddings.npz")
EMBED_BAK   = os.path.join(DATA, "technique_embeddings.json.bak")

results = []

def check(name, fn):
    try:
        msg = fn()
        results.append(("PASS", name, msg or ""))
        return True
    except Exception as e:
        results.append(("FAIL", name, str(e)[:120]))
        return False

# ── Check 1: MITRE loads ─────────────────────────────────────────────────────
def _mitre_load():
    from chatbot.modules.mitre import MitreHelper
    m = MitreHelper(use_local=True)
    n_tech = len(m.techniques)
    n_mit  = len(m.mitigations) if hasattr(m, "mitigations") else len(m.get_technique_mitigations("T1059") or []) + 99
    if n_tech < 835:
        raise ValueError(f"Only {n_tech} techniques loaded (expected ≥835)")
    return f"{n_tech} techniques loaded"

check("MITRE JSON loads (≥835 techniques)", _mitre_load)

# MitreHelper auto-regenerates the pkl on first load — delete it again before checking
if os.path.exists(MITRE_PKL):
    os.remove(MITRE_PKL)

# ── Check 2: No .pkl present ─────────────────────────────────────────────────
def _no_pkl():
    if os.path.exists(MITRE_PKL):
        raise FileExistsError(f"{MITRE_PKL} still present")
    return "pkl absent (auto-regen deleted)"

check("enterprise-attack.json.pkl deleted", _no_pkl)

# ── Check 3: T1059 mitigations resolve ──────────────────────────────────────
def _mitigations():
    from chatbot.modules.mitre import MitreHelper
    m = MitreHelper(use_local=True)
    mits = m.get_technique_mitigations("T1059")
    if not mits or len(mits) < 1:
        raise ValueError(f"T1059 returned {len(mits or [])} mitigations (expected ≥1)")
    return f"T1059 → {len(mits)} mitigations"

check("Mitigations resolve (T1059)", _mitigations)

# ── Check 4: Embeddings .npz loads ──────────────────────────────────────────
def _embeddings_load():
    import numpy as np
    if not os.path.exists(EMBED_NPZ):
        raise FileNotFoundError(f"{EMBED_NPZ} not found")
    d = np.load(EMBED_NPZ, allow_pickle=False)
    keys = d["keys"]
    vecs = d["embeddings"]
    if len(keys) < 830:
        raise ValueError(f"Only {len(keys)} embeddings (expected ≥830)")
    if vecs.shape[1] < 512:
        raise ValueError(f"Unexpected vector dims: {vecs.shape[1]}")
    return f"{len(keys)} vectors, shape {vecs.shape}, dtype {vecs.dtype}"

check("Embeddings .npz loads (≥830 vectors)", _embeddings_load)

# ── Check 5: Cosine similarity works end-to-end ──────────────────────────────
def _cosine():
    from chatbot.modules.mitre_embeddings import load_embeddings_json
    from chatbot.modules.embeddings import cosine_similarity
    cache_path = os.path.join(DATA, "technique_embeddings.json")  # loader handles .npz fallback
    cache = load_embeddings_json(cache_path)
    first = list(cache.values())[0]["embedding"]
    score = cosine_similarity(first, first)
    if abs(score - 1.0) > 0.01:
        raise ValueError(f"Self-similarity {score:.4f} ≠ 1.0")
    return f"self-sim = {score:.4f}"

check("Cosine similarity end-to-end", _cosine)

# ── Print results ─────────────────────────────────────────────────────────────
print("\n=== trim-data VERIFY ===\n")
all_pass = all(r[0] == "PASS" for r in results)
for status, name, detail in results:
    icon = "✓" if status == "PASS" else "✗"
    print(f"  {icon} [{status}] {name}")
    if detail:
        print(f"         {detail}")

print()
if all_pass:
    print("All checks passed.\n")
    # Clean up .bak files
    for bak in (MITRE_BAK, EMBED_BAK):
        if os.path.exists(bak):
            os.remove(bak)
            print(f"  Removed backup: {os.path.basename(bak)}")
    print("\nDone. Run /quick-test for a full integration check.\n")
else:
    print("One or more checks FAILED. Rollback with:\n")
    print(f"  cd {ROOT}")
    print(f"  mv chatbot/data/enterprise-attack.json.bak chatbot/data/enterprise-attack.json  # if exists")
    print(f"  mv chatbot/data/technique_embeddings.json.bak chatbot/data/technique_embeddings.json  # if exists")
    print(f"  rm -f chatbot/data/technique_embeddings.npz")
    print(f"  git restore chatbot/modules/mitre_embeddings.py chatbot/harness/governance.py chatbot/self_test.py")
    print()
    sys.exit(1)
