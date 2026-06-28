Critics Family SVG and Mascots

- Banner: `docs/assets/critics_family.svg`
- Mascot SVGs (individual files):
  - `docs/assets/mascots/architect_mascot.svg`
  - `docs/assets/mascots/tester_mascot.svg`
  - `docs/assets/mascots/redteam_mascot.svg`
  - `docs/assets/mascots/purpleteam_mascot.svg`
  - `docs/assets/mascots/blackhat_mascot.svg`
  - `docs/assets/mascots/orchestrator_mascot.svg`
  - `docs/assets/mascots/scrummaster_mascot.svg`
  - `docs/assets/mascots/trustedanalyst_mascot.svg`

Usage

- Embed a mascot directly in a blog post as an inline SVG or image.

Export to PNG (ImageMagick):

```bash
magick convert docs/assets/mascots/architect_mascot.svg docs/assets/mascots/architect_mascot.png
magick convert docs/assets/mascots/tester_mascot.svg docs/assets/mascots/tester_mascot.png
# ...repeat for each mascot
```

Export to PNG (Inkscape):

```bash
inkscape docs/assets/mascots/architect_mascot.svg --export-type=png --export-filename=docs/assets/mascots/architect_mascot.png
```

Next steps

- Export high-res PNGs (I can do this locally if you want PNGs committed here).
- Create a combined banner using the mascot artwork instead of emoji icons.

If you'd like color or style adjustments, tell me which personas to tweak and what palette or tone you prefer.