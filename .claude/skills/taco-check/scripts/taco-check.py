#!/usr/bin/env python3
"""TACO Agent regression gate (Phase 3 + Phase 4 critic)."""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def run_phase(label: str, cmd: list) -> tuple[bool, float, str]:
    t0 = time.monotonic()
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    ok = result.returncode == 0
    out = result.stdout + result.stderr
    return ok, elapsed, out


def phase_benchmark_sanity() -> tuple[bool, float, str]:
    t0 = time.monotonic()
    sanity_script = ROOT / ".claude" / "skills" / "taco-check" / "scripts" / "_sanity.py"
    # Write a helper script so we avoid f-string nesting issues
    sanity_script.write_text(f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from chatbot.modules.taco_benchmark import TACOBenchmark
from chatbot.modules.ta_brain_builder import HOLD_OUT_ARCHS
from pathlib import Path

report_dir = Path({str(ROOT / 'report')!r})
arch = next(
    (a for a in sorted(HOLD_OUT_ARCHS) if (report_dir / a / 'ground_truth.json').exists()),
    None
)
if arch is None:
    print('SKIP: no hold-out arch with ground_truth.json found')
    sys.exit(0)

bm = TACOBenchmark(report_dir=report_dir)
result = bm.score_arch(arch)

for mode_name, score in [('workspace', result.workspace), ('taco_brain', result.taco_brain), ('taco_rag', result.taco_rag)]:
    for dim in ('threat_relevant','ttp_accurate','risk_defensible','groundedness','confidence_calibration','ciso_utility','overall'):
        v = getattr(score, dim)
        assert v is None or isinstance(v, (int, float)), f'{{mode_name}}.{{dim}} = {{v!r}} is not float or None'
        if v is not None:
            assert 0.0 <= float(v) <= 100.0, f'{{mode_name}}.{{dim}} = {{v}} out of [0,100]'
print(f'OK: sanity passed for {{arch}}')
""")
    proc = subprocess.run([sys.executable, str(sanity_script)], capture_output=True, text=True)
    sanity_script.unlink(missing_ok=True)
    elapsed = time.monotonic() - t0
    ok = proc.returncode == 0
    return ok, elapsed, proc.stdout + proc.stderr


_CRITIC_SIM = """
┌─────────────────────────────────────────────────────────────────┐
│  TACOminiCritic — manual activation walkthrough                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  STEP 1 — Enable in settings.yaml (Gate 1)                      │
│    Edit chatbot/config/settings.yaml:                           │
│      taco:                                                       │
│        critic_enabled: true   # was: false                      │
│    Then restart the API:  ./scripts/api/api_restart.sh          │
│                                                                  │
│  STEP 2 — Trigger from the dashboard (Gate 2)                   │
│    Open: http://localhost:8000/dashboard                         │
│    → Brain tab → TACO Agent sub-tab                             │
│    → Select an architecture with existing Expert Review data    │
│    → Check the "critic" checkbox (purple label)                 │
│    → Enter a query and click Run TACO                           │
│    → Expect a purple TACritic hop in the trace                  │
│                                                                  │
│  STEP 3 — Trigger via API (Gate 2)                              │
│    POST /api/v1/taco/run-sync                                    │
│    {                                                             │
│      "query": "what are the top risks?",                        │
│      "arch_name": "<arch_with_moe_data>",                       │
│      "force_critic": true                                        │
│    }                                                             │
│    → HopChain.routed_to_critics == true                         │
│    → Last hop: hop_type="critic", had_moe=true                  │
│                                                                  │
│  Without critic_enabled: true, the critic hop is never run       │
│  even if force_critic=true is sent in the request.              │
│                                                                  │
│  Architectures with MoE data (07_moe_orchestrator.json):        │
│    ls report/*/07_moe_orchestrator.json                         │
└─────────────────────────────────────────────────────────────────┘
"""


def main():
    phases = []

    ok1, t1, out1 = run_phase("unit tests", [
        sys.executable, "-m", "pytest",
        "tests/unit/test_taco_agent.py",
        "tests/unit/test_taco_rag.py",
        "tests/unit/test_taco_benchmark.py",
        "-v", "--tb=short",
    ])
    phases.append(("Unit tests", ok1, t1, out1))

    ok2, t2, out2 = phase_benchmark_sanity()
    phases.append(("Benchmark sanity", ok2, t2, out2))

    print("\n┌─────────────────────────────────────────┐")
    print("│ taco-check regression gate (Ph3 + Ph4)  │")
    print("├─────────────────────────────────────────┤")
    for name, ok, elapsed, _ in phases:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"│ {status}  {name:<28} {elapsed:5.1f}s │")
    print("└─────────────────────────────────────────┘")

    failed = [p for p in phases if not p[1]]
    if failed:
        print("\nFailed output:")
        for name, ok, _, out in failed:
            print(f"\n--- {name} ---")
            print(out[-3000:] if len(out) > 3000 else out)
        sys.exit(1)

    print("\nAll checks passed.")
    print(_CRITIC_SIM)


if __name__ == "__main__":
    main()
