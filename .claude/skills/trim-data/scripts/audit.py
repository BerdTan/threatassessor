#!/usr/bin/env python3
"""
trim-data Phase 1 — AUDIT
Read-only size survey of chatbot/data/ with trim estimates.
"""
import os, json, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DATA = os.path.join(ROOT, "chatbot", "data")

def mb(path):
    try:
        return os.path.getsize(path) / 1024 / 1024
    except FileNotFoundError:
        return 0.0

def fmt(n):
    return f"{n:.1f} MB" if n > 0 else "absent"

MITRE_JSON   = os.path.join(DATA, "enterprise-attack.json")
MITRE_PKL    = os.path.join(DATA, "enterprise-attack.json.pkl")
EMBED_JSON   = os.path.join(DATA, "technique_embeddings.json")
EMBED_NPZ    = os.path.join(DATA, "technique_embeddings.npz")

print("\n=== trim-data AUDIT ===\n")

rows = []
total_now = 0.0
total_after = 0.0

# --- enterprise-attack.json ---
now = mb(MITRE_JSON)
if now > 0:
    with open(MITRE_JSON) as f:
        data = json.load(f)
    objs = data.get("objects", [])
    keep_types = {"attack-pattern","course-of-action","intrusion-set",
                  "x-mitre-tactic","x-mitre-matrix","identity","marking-definition",
                  "tool","campaign"}
    keep_rels  = {"mitigates","uses"}
    kept = [o for o in objs if o.get("type") in keep_types or
            (o.get("type") == "relationship" and o.get("relationship_type") in keep_rels)]
    dropped = len(objs) - len(kept)
    slim_est = now * len(kept) / len(objs)
    rows.append(("enterprise-attack.json", fmt(now), f"~{slim_est:.1f} MB",
                 f"Strip {dropped:,} unused objects ({len(objs)-len(kept)} dropped of {len(objs)})"))
    total_now   += now
    total_after += slim_est
else:
    rows.append(("enterprise-attack.json", "absent", "—", "Not found — skip"))

# --- .pkl ---
pkl = mb(MITRE_PKL)
rows.append(("enterprise-attack.json.pkl", fmt(pkl), "0 MB",
             "Delete — auto-regenerates on next load"))
total_now   += pkl
# total_after += 0

# --- technique_embeddings ---
if mb(EMBED_NPZ) > 0:
    rows.append(("technique_embeddings.npz", fmt(mb(EMBED_NPZ)), fmt(mb(EMBED_NPZ)),
                 "Already converted — nothing to do"))
    total_now   += mb(EMBED_NPZ)
    total_after += mb(EMBED_NPZ)
elif mb(EMBED_JSON) > 0:
    # float64 JSON → float16 npz
    with open(EMBED_JSON) as f:
        emb = json.load(f)
    n = len(emb)
    sample = list(emb.values())[0]
    d = len(sample.get("embedding", sample) if isinstance(sample, dict) else sample)
    npz_est = n * d * 2 / 1024 / 1024  # float16 = 2 bytes
    rows.append(("technique_embeddings.json", fmt(mb(EMBED_JSON)), f"~{npz_est:.1f} MB",
                 f"Convert {n} × {d}-dim vectors → float16 .npz"))
    total_now   += mb(EMBED_JSON)
    total_after += npz_est
else:
    rows.append(("technique_embeddings.json", "absent", "—", "Not found — skip"))

# --- other data (small, kept as-is) ---
other = 0.0
for name in os.listdir(DATA):
    p = os.path.join(DATA, name)
    if os.path.isdir(p):
        for root, _, files in os.walk(p):
            for fn in files:
                other += os.path.getsize(os.path.join(root, fn))
    elif name not in ("enterprise-attack.json","enterprise-attack.json.pkl",
                      "technique_embeddings.json","technique_embeddings.npz",
                      "enterprise-attack.json.bak","technique_embeddings.json.bak"):
        other += os.path.getsize(p)
other /= 1024 * 1024
rows.append(("Other (atlas, kev, arc, ssp…)", fmt(other), fmt(other), "Kept as-is"))
total_now   += other
total_after += other

# --- print table ---
col = [38, 14, 16, 52]
header = ("File", "Current", "After trim", "Method")
sep = "  ".join("-" * c for c in col)
fmt_row = lambda r: "  ".join(str(v).ljust(c) for v, c in zip(r, col))
print(fmt_row(header))
print(sep)
for r in rows:
    print(fmt_row(r))
print(sep)
print(fmt_row(("TOTAL", fmt(total_now), f"~{total_after:.1f} MB",
               f"{100*(1-total_after/total_now):.0f}% reduction" if total_now else "")))

print()
saving = total_now - total_after
print(f"  Estimated saving:  {saving:.1f} MB  ({100*saving/total_now:.0f}%)" if total_now else "")
print()
