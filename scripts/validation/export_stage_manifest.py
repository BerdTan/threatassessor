"""Export the pipeline's real stage order as JSON for TAprover's doc-claim check.

This is the only pipeline-side piece: it imports the harness and writes plain data.
TAprover reads the JSON and never imports the pipeline (independence invariant).

    PYTHONPATH=. .venv/bin/python scripts/validation/export_stage_manifest.py [out.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build() -> dict:
    sys.path.insert(0, str(ROOT))
    from chatbot.harness import controller as c
    return {"schema": "stage-manifest/0.1",
            "scenarios": {n: [s.name for s in f()] for n, f in c._SCENARIO_REGISTRY.items()}}


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "report" / "stage_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(), indent=2))
    print(f"wrote {out}")
