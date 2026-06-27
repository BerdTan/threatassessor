---
name: aivss-gate
description: Show current per-critic AIVSS gate config and last-run inbound score
---

1. Read `settings.critics` block from `chatbot/config/settings.py` (or the loaded settings singleton).
2. Read the most recent `logs/siem.jsonl` entry (last line). If absent, note that no SIEM events have been emitted yet.
3. Show a formatted per-critic gate table:

```
Critic        Allowed Models   Allowed Tools   Gate Threshold   Last Internal Score
architect     [any]            [any]           10.0 (off)       1.8 LOW
red_team      [any]            [any]           10.0 (off)       2.4 LOW
tester        [any]            [any]           10.0 (off)       1.5 LOW
purple_team   [any]            [any]           10.0 (off)       —
```

4. Show the last SIEM event summary:
   - Architecture, timestamp, run_id
   - Inbound / Internal / Outbound AIVSS scores + overall severity
   - Top threat (technique_id, score, severity)
   - Governance dim severities (D1-D5)

5. Note: if inbound score was HIGH (≥7.0) or CRITICAL (≥9.0), call out which tightening action was triggered.
