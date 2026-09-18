#!/usr/bin/env python3
"""
Skills SHA256 manifest drift detector — Engine Item 6.3.

Compares the committed .claude/skills/skills.sha256 baseline against the
current state of .claude/skills/. Reports added, removed, and modified files.
Exits 0 if clean, 1 if drift detected.
"""

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                    text=True).strip())
SKILLS_DIR = ROOT / ".claude" / "skills"
MANIFEST_PATH = SKILLS_DIR / "skills.sha256"

_EXTENSIONS = {".md", ".py", ".sh", ".yaml", ".json"}


def _compute_current() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(SKILLS_DIR.rglob("*")):
        if path.is_file() and path.suffix in _EXTENSIONS and path != MANIFEST_PATH:
            rel = str(path.relative_to(ROOT))
            result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _load_manifest() -> dict[str, str]:
    if not MANIFEST_PATH.exists():
        print("WARN  skills.sha256 not found — run with --regen to create baseline")
        return {}
    manifest: dict[str, str] = {}
    for line in MANIFEST_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) == 2:
            digest, path = parts
            manifest[path] = digest
    return manifest


def _regen(current: dict[str, str]) -> None:
    lines = [f"{digest}  {path}" for path, digest in sorted(current.items())]
    MANIFEST_PATH.write_text("\n".join(lines) + "\n")
    print(f"OK    Manifest regenerated: {len(lines)} entries → {MANIFEST_PATH}")


def main() -> int:
    regen = "--regen" in sys.argv

    current = _compute_current()

    if regen:
        _regen(current)
        return 0

    baseline = _load_manifest()
    if not baseline:
        return 1

    baseline_paths = set(baseline)
    current_paths = set(current)

    added   = current_paths - baseline_paths
    removed = baseline_paths - current_paths
    modified = {p for p in baseline_paths & current_paths if baseline[p] != current[p]}

    drift = added | removed | modified

    if not drift:
        print(f"OK    Skills manifest clean — {len(current)} files match baseline")
        return 0

    print(f"DRIFT Skills manifest mismatch — {len(drift)} file(s) changed:\n")
    for p in sorted(added):
        print(f"  ADD      {p}")
    for p in sorted(removed):
        print(f"  REMOVE   {p}")
    for p in sorted(modified):
        print(f"  MODIFIED {p}")

    print(f"\nRun with --regen to update baseline after intentional changes.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
