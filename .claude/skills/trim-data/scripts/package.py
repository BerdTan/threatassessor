#!/usr/bin/env python3
"""
trim-data Phase 4 — PACKAGE
Creates data_bundle.tar.gz for portability.
With --gh-release: uploads to a GitHub Release and writes scripts/bootstrap_data.sh.
"""
import os, sys, tarfile, subprocess, textwrap

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DATA = os.path.join(ROOT, "chatbot", "data")

GH_RELEASE = "--gh-release" in sys.argv
BUNDLE     = os.path.join(ROOT, "data_bundle.tar.gz")

INCLUDE_PATHS = [
    "chatbot/data/enterprise-attack.json",
    "chatbot/data/technique_embeddings.npz",
    "chatbot/data/technique_embeddings_meta.json",
    "chatbot/data/engine_hints.json",
    "chatbot/data/atlas",
    "chatbot/data/kev",
    "chatbot/data/arc",
    "chatbot/data/ssp",
    "chatbot/data/ccm",
    "chatbot/data/caveat",
]

print("\n=== trim-data PACKAGE ===\n")

print("Building data_bundle.tar.gz …")
total_size = 0
with tarfile.open(BUNDLE, "w:gz") as tar:
    for rel in INCLUDE_PATHS:
        full = os.path.join(ROOT, rel)
        if not os.path.exists(full):
            print(f"  skip (absent): {rel}")
            continue
        tar.add(full, arcname=rel)
        if os.path.isdir(full):
            for r, _, files in os.walk(full):
                for fn in files:
                    total_size += os.path.getsize(os.path.join(r, fn))
        else:
            total_size += os.path.getsize(full)
        print(f"  + {rel}")

bundle_mb = os.path.getsize(BUNDLE) / 1024 / 1024
print(f"\n  Bundle: {BUNDLE}")
print(f"  Size:   {bundle_mb:.1f} MB (compressed from ~{total_size/1024/1024:.1f} MB)\n")

if not GH_RELEASE:
    print("Bundle created. To install on another machine:")
    print(f"  tar -xzf data_bundle.tar.gz -C /path/to/repo/")
    print()
    print("For GitHub Release upload, re-run with --gh-release")
    sys.exit(0)

# ── GitHub Release ────────────────────────────────────────────────────────────
TAG = "data-v1.0"
print(f"Creating GitHub Release tag: {TAG} …")

# Get remote URL to determine owner/repo
try:
    remote = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], cwd=ROOT, text=True
    ).strip()
    # parse github.com/OWNER/REPO from https or ssh url
    if "github.com" in remote:
        parts = remote.split("github.com")[-1].strip(":/").replace(".git", "").split("/")
        owner, repo = parts[0], parts[1]
    else:
        print("  ERROR: origin remote does not look like a GitHub URL.")
        print(f"  remote = {remote}")
        sys.exit(1)
except subprocess.CalledProcessError:
    print("  ERROR: could not read git remote origin.")
    sys.exit(1)

ASSET_URL = f"https://github.com/{owner}/{repo}/releases/download/{TAG}/data_bundle.tar.gz"

# Create release + upload asset via gh CLI
try:
    subprocess.run(
        ["gh", "release", "create", TAG,
         BUNDLE,
         "--title", "Data bundle (MITRE + embeddings)",
         "--notes", "Portable data files for ThreatAssessor. Install with scripts/bootstrap_data.sh."],
        cwd=ROOT, check=True
    )
    print(f"  Release created: {ASSET_URL}")
except FileNotFoundError:
    print("  ERROR: 'gh' CLI not found. Install from https://cli.github.com/")
    sys.exit(1)
except subprocess.CalledProcessError as e:
    print(f"  ERROR: gh release create failed: {e}")
    sys.exit(1)

# ── Write bootstrap script ────────────────────────────────────────────────────
BOOTSTRAP = os.path.join(ROOT, "scripts", "bootstrap_data.sh")
script = textwrap.dedent(f"""\
    #!/usr/bin/env bash
    # Bootstrap ThreatAssessor data files on a fresh clone.
    # Downloads the trimmed MITRE + embeddings bundle (~14 MB) from GitHub Releases.
    # Run once after cloning: bash scripts/bootstrap_data.sh
    set -euo pipefail

    ROOT=$(git rev-parse --show-toplevel)
    URL="{ASSET_URL}"
    BUNDLE="$ROOT/data_bundle.tar.gz"

    echo "Downloading data bundle from GitHub Releases …"
    curl -fL "$URL" -o "$BUNDLE"
    echo "Extracting …"
    tar -xzf "$BUNDLE" -C "$ROOT"
    rm "$BUNDLE"
    echo "Done. Data files installed in chatbot/data/."
""")

os.makedirs(os.path.dirname(BOOTSTRAP), exist_ok=True)
with open(BOOTSTRAP, "w") as f:
    f.write(script)
os.chmod(BOOTSTRAP, 0o755)
print(f"\n  Bootstrap script written: scripts/bootstrap_data.sh")
print(f"  Commit this file — the bundle itself stays out of git.\n")
print("On a fresh clone, run:  bash scripts/bootstrap_data.sh\n")
