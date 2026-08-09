# Rendering the report as a webpage

Turn `security-assessment/REPORT.md` into a self-contained, good-looking `security-assessment/report.html`. The point is comprehension: a stakeholder who won't read Markdown should understand the risk in thirty seconds and drill into any finding.

## Before you build it
**Invoke the `anti-slop-web` skill first.** A security report page rendered with default Bootstrap-ish styling reads as generic AI output and undercuts the work. Commit to one visual direction; derive tokens from a few decisions; screenshot the result and look at it before delivering.

## Hard requirements
- **Self-contained.** Inline all CSS and JS. Embed screenshots as relative paths (`evidence/RT-0X.png`) or data URIs so the file opens standalone. No external CDNs.
- **Render evidence, don't describe it.** Screenshots show as images. Transcripts show in monospace `<pre>` blocks that scroll horizontally, never break the page. Mermaid diagrams render (inline the mermaid runtime, or pre-render to SVG — do not rely on a CDN).
- **Top of page = the summary.** Project name, assessment date, and a severity-count row (Critical / High / Medium / Low as colored tiles) visible without scrolling. Then the risk-summary table.
- **Findings below, scannable.** Each finding is a card or an expandable row, color-keyed by severity, showing ID · title · component · confirmed-vs-static badge. Expanding reveals description, attack path + diagram, evidence, impact, and the linked fix.
- **Three sections, clearly separated:** Red (findings), Blue (remediation plan), Purple (detection & response), with the RT↔BT↔PT cross-links clickable.
- **Confidence is visible.** A badge on every finding: "Confirmed by execution" vs "Static — unconfirmed". Never let the page imply more certainty than the report states.
- **Theme-aware and responsive.** Readable in light and dark; no horizontal page scroll on a phone (wide tables/transcripts scroll inside their own container).

## Verify before claiming done
- Open or parse the HTML; confirm it renders and image paths resolve.
- Confirm the severity counts on the page match the report's risk table.
- Report the path. If any screenshot is missing, the page shows a labelled placeholder ("no capture — see transcript"), not a broken image and not a fabricated one.

## Publishing (optional)
If the user wants a shareable link, the `Artifact` tool can host the HTML. A security report names real weaknesses in the user's system — treat it as sensitive: publish only if the user asks, and confirm first. Default is the local file.
