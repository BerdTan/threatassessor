# TMbench Results

Tool submissions are stored under `results/<tool_name>/<arch_id>.json`.

Each JSON must conform to `threatmodel/0.1` schema (see `../threatmodel.md §4`).

## Adding a result

```bash
python3 scripts/tmbench/tmbench_runner.py --ingest <tool_name> <path/to/output.json>
```

This copies the JSON, scores it against the spec, and diffs dimensions vs the corpus ground truth.

## Leaderboard

```bash
python3 scripts/tmbench/tmbench_runner.py --leaderboard
```

## Coverage grid

```bash
python3 scripts/tmbench/tmbench_runner.py --status
```

## Re-score a tool's existing results

```bash
python3 scripts/tmbench/tmbench_runner.py --score-all <tool_name>
```

## Tool naming convention

| Type | Example name |
|---|---|
| TA pipeline | `ta_v3` |
| OpenAI GPT-4o | `gpt4o` |
| Claude Sonnet | `claude_sonnet` |
| TMagent (hetzner) | `tmagent_hetzner` |
| Manual submission | `manual_<date>` |
