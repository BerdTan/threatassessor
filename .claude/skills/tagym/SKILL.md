---
name: tagym
description: TAgym autonomous assessment flywheel — start a gym run against a target queue, follow iteration-by-iteration progress with per-arch gate/mitigations/Brier output, inspect results, and optionally trigger brain ingest on PASS iterations. Instrument gym for the TA assessment engine.
allowed-tools: Bash(python3:*) Bash(curl:*) Bash(source:*)
---

# tagym — Instrument Gym for ThreatAssessor

TAgym runs the full TAclaw assessment pipeline continuously against a target queue,
harvesting a Brier calibration snapshot after each iteration. It trains the assessment
instrument itself — not analysts, not techniques.

## Usage

```
/tagym                              # check current session status
/tagym <target-dir>                 # start a run against a directory
/tagym <target-dir> -n <N>          # N iterations (default 10)
/tagym stop                         # stop running session
/tagym ingest                       # trigger brain ingest on PASS iterations
```

## Execution steps

### Status check (default — no args)

```bash
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate
python3 -m taclaw.cli gym status
```

Parse the output and report:
- Session ID and running/stopped state
- Iteration table: arch / gate / mitigations / Brier snapshot / delta annotation
- Summary line: Pass count, Block count, avg mitigations, total Brier Δ

If no active session: tell the user and offer `/tagym <target>` to start one.

---

### Start a run

```bash
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate
python3 -m taclaw.cli gym start \
  --target <TARGET_DIR> \
  --max-iterations <N>
```

For multiple targets, repeat `--target`:
```bash
python3 -m taclaw.cli gym start \
  --target tests/data/architectures \
  --target /path/to/other/archs \
  --max-iterations 20
```

After start, immediately run `gym status` once to confirm the first iteration is queued,
then tell the user to run `/tagym` again to follow progress.

**Sensible defaults:**
- `--type directory` unless user passes a `https://` URL (then `--type git_url`)
- `--ssp low_risk_cloud` unless user specifies a profile
- `-n 10` unless user specifies

---

### Follow progress

Poll with `gym status` and render the iteration table. Highlight:
- BLOCK iterations where Brier held flat (`← no change` annotation)
- Brier delta trend: is calibration improving (▼), drifting (▲), or flat?
- Iterations where mitigations drop sharply — may indicate a sparse or noisy arch

Stop polling when `status == "stopped"`.

---

### Stop a run

```bash
python3 -m taclaw.cli gym stop
```

---

### Ingest PASS iterations into Brain

After a completed session, identify PASS iterations and offer brain ingest:

```bash
# Check which archs produced PASS results
python3 -m taclaw.cli gym status
```

For each PASS arch where a new pattern was found, trigger ingest:
```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from chatbot.modules.ta_brain_builder import build_brain
build_brain(incremental=True)
print('Brain updated.')
"
```

Then run Brier recalibration to confirm improvement:
```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from chatbot.modules.ta_brain_benchmarks import run_benchmarks
run_benchmarks()
"
```

Report the new avg Brier vs the session's starting snapshot.

---

## Reading the output

| Column | Meaning |
|---|---|
| # | Iteration index (1-based) |
| Arch | Architecture name derived from target path |
| Gate | PASS = new pattern ingestible; BLOCK = pipeline halted, no ingest |
| Mitigations | Controls found by the harness for this arch |
| Brier | Avg precision-weighted calibration score after this iteration |
| Delta | ▼ = improved, ▲ = degraded, `← no change` = BLOCK held Brier flat |

**Key invariant:** Brier only changes on PASS iterations where brain ingest runs.
A BLOCK iteration always holds Brier flat — this is expected behaviour, not a failure.

---

## Interpreting results

- **Brier Δ negative overall** — calibration improved; the gym is working
- **Multiple consecutive BLOCKs** — target queue may lack novel patterns; add new arch targets
- **High mitigations + BLOCK** — the harness found issues but the quality gate rejected ingest; check `ta gate --arch <name>` for blocking signals
- **Brier not moving after 5+ PASSes** — knowledge base may have saturated this arch type; try different topology targets

---

## Notes

- API must be running: `./scripts/api/api_start.sh`
- Single session at a time — `/tagym start` replaces any running session
- `tests/data/architectures/` (33 sample archs) is a good default target queue for calibration runs
- Brier snapshots read passively from `report/brain/ta_brain_benchmarks.json` — no forced recalibration during the run
- Brain ingest (`incremental=True`) is safe to run after the gym session; it deduplicates automatically

## Related skills

- `/taclaw` — single-target autonomous assessment
- `/check-brain` — Brier calibration health check
- `/brain-ingest` — rebuild `ta_brain.json` from instances
- `/bench-loop` — full model evaluation loop (corpus → benchmark → promote)
