#!/usr/bin/env python3
"""Screenshot a page at three viewports and measure what actually rendered.

  shoot.py <url-or-file> --out .shots

Writes mobile/tablet/desktop folds, a desktop full-page shot, and measured.json
- the rendered facts (type sizes actually used, section heights, the visually
heaviest block, overflow at 390px, contrast, focus styles, motion queries).

The measurements exist so the visual pass is checkable. "The hero is the
strongest thing on the page" is an assertion; section heights are evidence. If a
claim in your audit contradicts measured.json, the claim is wrong.

Screenshots still have to be opened and looked at - measurement covers the
things a number can settle, not composition, awkwardness or fit.
"""
import sys, os, json, argparse

VIEWPORTS = [("mobile", 390, 844), ("tablet", 768, 1024), ("desktop", 1440, 900)]

MEASURE_JS = r"""
() => {
  const vis = el => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const txt = el => (el.textContent || '').trim().replace(/\s+/g, ' ');

  // type sizes actually rendered on visible text, not sizes declared in CSS
  const sizes = new Map();
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const px = Math.round(parseFloat(getComputedStyle(el).fontSize));
    const e = sizes.get(px) || { px, count: 0, sample: '' };
    e.count++;
    if (!e.sample) e.sample = txt(el).slice(0, 48);
    sizes.set(px, e);
  }
  const typeSizes = [...sizes.values()].sort((a, b) => b.px - a.px);

  // top-level blocks: height is the honest proxy for visual weight/rhythm
  const root = document.querySelector('main') || document.body;
  const blocks = [...root.children].filter(vis).map((el, i) => ({
    i, tag: el.tagName.toLowerCase(),
    cls: (el.className || '').toString().slice(0, 40),
    height: Math.round(el.getBoundingClientRect().height),
    maxFont: Math.max(0, ...[...el.querySelectorAll('*')].filter(vis)
      .map(e => parseFloat(getComputedStyle(e).fontSize) || 0)),
    text: txt(el).slice(0, 60),
  }));

  // grid break, measured rather than pattern-matched: the text column's width
  // versus anything substantially wider than it. A structural escape (an
  // element placed outside the max-width wrapper) uses no special idiom and is
  // invisible to source analysis.
  // The container is the width that RECURS - the max-width wrapper - not the
  // width of a paragraph, which in a two-column layout is far narrower and
  // makes every piece of page furniture look like an escape.
  const tally = new Map();
  const vw = window.innerWidth;
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el) || !el.children.length) continue;
    const w = Math.round(el.getBoundingClientRect().width);
    if (w > vw * 0.4 && w < vw * 0.95) tally.set(w, (tally.get(w) || 0) + 1);
  }
  // the wrapper is the LARGEST width that recurs, not the most frequent one -
  // a two-column layout repeats its half-width more often than the container
  let contentColumn = null;
  for (const [w, n] of tally) if (n >= 2 && w > (contentColumn || 0)) contentColumn = w;
  if (!contentColumn) for (const [w] of tally) if (w > (contentColumn || 0)) contentColumn = w;

  const widerThanColumn = [], kept = [];
  if (contentColumn) {
    for (const el of document.querySelectorAll('body *')) {
      if (!vis(el)) continue;
      const w = Math.round(el.getBoundingClientRect().width);
      if (w <= contentColumn * 1.05) continue;
      if (kept.some(k => k.contains(el))) continue;   // report the outermost only
      kept.push(el);
      widerThanColumn.push({ tag: el.tagName.toLowerCase(),
                             cls: (el.className || '').toString().slice(0, 30), width: w });
      if (widerThanColumn.length > 8) break;
    }
  }

  // horizontal overflow: the single most common mobile defect
  const de = document.documentElement;
  const overflow = [];
  if (de.scrollWidth > de.clientWidth + 1) {
    for (const el of document.querySelectorAll('body *')) {
      if (!vis(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.right > de.clientWidth + 1 || r.left < -1)
        overflow.push({ tag: el.tagName.toLowerCase(),
                        cls: (el.className || '').toString().slice(0, 30),
                        right: Math.round(r.right) });
      if (overflow.length > 6) break;
    }
  }

  // accessibility floor
  const lum = c => {
    const a = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
  };
  const parse = s => (s.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
  // the longest paragraph is body copy; the first one is usually a hero subhead
  const paras = [...document.querySelectorAll('p')].filter(vis)
    .sort((a, b) => txt(b).length - txt(a).length);
  const bodyEl = paras[0] || document.body;
  let bg = bodyEl, bgc = 'rgba(0, 0, 0, 0)', painted = false;
  while (bg) {
    const s = getComputedStyle(bg);
    if (s.backgroundImage && s.backgroundImage !== 'none') { painted = true; break; }
    if ((bgc = s.backgroundColor) !== 'rgba(0, 0, 0, 0)') break;
    bg = bg.parentElement;
  }
  // a gradient or photo behind the text has no single value to measure against
  const contrast = painted ? null : (() => {
    const l1 = lum(parse(getComputedStyle(bodyEl).color));
    const l2 = lum(parse(bgc === 'rgba(0, 0, 0, 0)' ? 'rgb(255,255,255)' : bgc));
    return +(((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)).toFixed(2));
  })();

  let killsFocus = 0;
  for (const el of document.querySelectorAll('a,button,input,select,textarea')) {
    const s = getComputedStyle(el, ':focus-visible');
    if (s.outlineStyle === 'none' && s.boxShadow === 'none') killsFocus++;
  }

  return {
    viewport: { w: window.innerWidth, h: window.innerHeight },
    pageHeight: Math.round(de.scrollHeight),
    typeSizes,
    typeRange: typeSizes.length > 1
      ? +(typeSizes[0].px / typeSizes[typeSizes.length - 1].px).toFixed(2) : null,
    blocks,
    tallestBlock: blocks.length ? blocks.reduce((a, b) => (b.height > a.height ? b : a)) : null,
    biggestTypeBlock: blocks.length ? blocks.reduce((a, b) => (b.maxFont > a.maxFont ? b : a)) : null,
    contentColumn,
    widerThanColumn,
    horizontalOverflow: overflow,
    bodyContrast: contrast,
    bodyContrastSample: txt(bodyEl).slice(0, 48),
    contrastUnmeasurable: painted,
    focusRemovedOn: killsFocus,
    interactive: document.querySelectorAll('a,button,input,select,textarea').length,
  };
}
"""


def summarise(m):
    """The four claims a model is most likely to get wrong by not looking."""
    out = []
    d = m.get("desktop", {})
    mob = m.get("mobile", {})
    blocks = d.get("blocks") or []
    if blocks:
        big = d.get("biggestTypeBlock")
        # type size, not height: an essay's body is legitimately taller than its
        # title block, so height says nothing about which block is strongest
        if big and big.get("i") != 0:
            out.append("HERO WEAK: block %d ('%s') renders larger type (%gpx) than the first block"
                       % (big["i"], big["text"][:30], big["maxFont"]))
        hs = sorted(b["height"] for b in blocks if b["height"] > 40)
        if len(hs) >= 3 and hs[-1] and (hs[-1] - hs[0]) / hs[-1] < 0.25:
            out.append("RHYTHM: every block is within 25%% of the same height %s - uniform density is the loudest generic tell" % hs)
    if d.get("contentColumn"):
        w = d.get("widerThanColumn") or []
        vw = (d.get("viewport") or {}).get("w", 0)
        bleed = [x for x in w if x["width"] >= vw - 2]
        mid = [x for x in w if x["width"] < vw - 2]
        parts = ["container %dpx" % d["contentColumn"]]
        if bleed:
            parts.append("%d element(s) at full viewport width%s"
                         % (len(bleed), " (a full-bleed structure, not necessarily the grid break)"
                            if len(bleed) > 2 else ""))
        if mid:
            parts.append("escaping the container: "
                         + ", ".join("%s.%s @%dpx" % (x["tag"], x["cls"], x["width"]) for x in mid[:3]))
        if not w:
            parts.append("nothing exceeds it - rule 3 wants exactly one thing to")
        out.append("; ".join(parts))
    if d.get("typeRange") is not None:
        out.append("measured type range %.2fx across %d rendered sizes"
                   % (d["typeRange"], len(d.get("typeSizes") or [])))
    if mob.get("horizontalOverflow"):
        out.append("MOBILE OVERFLOW at 390px: %s"
                   % ", ".join("%s.%s" % (o["tag"], o["cls"]) for o in mob["horizontalOverflow"][:3]))
    if d.get("contrastUnmeasurable"):
        out.append("CONTRAST: body text sits on a gradient or image - no single value to measure, check it by eye")
    elif d.get("bodyContrast") and d["bodyContrast"] < 4.5:
        out.append("CONTRAST: body text %.2f:1 on '%s', below the 4.5:1 floor"
                   % (d["bodyContrast"], (d.get("bodyContrastSample") or "")[:32]))
    if d.get("focusRemovedOn"):
        out.append("FOCUS: %d of %d interactive elements have no visible focus style"
                   % (d["focusRemovedOn"], d.get("interactive", 0)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--out", default=".shots")
    ap.add_argument("--wait", type=int, default=1200)
    ap.add_argument("--only", default="")
    ap.add_argument("--no-measure", action="store_true")
    ap.add_argument("--reveal", action="store_true",
                    help="print the machine findings; use only after writing your own")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed. run:")
        print("  pip install playwright && playwright install chromium")
        return 2

    url = args.target
    if not url.startswith("http"):
        url = "file://" + os.path.abspath(url)

    os.makedirs(args.out, exist_ok=True)
    picked = [v for v in VIEWPORTS if not args.only or v[0] in args.only.split(",")]
    written, measured = [], {}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, w, h in picked:
            page = browser.new_page(viewport={"width": w, "height": h},
                                    device_scale_factor=2)
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(args.wait)
            fold = os.path.join(args.out, "%s-fold.png" % name)
            page.screenshot(path=fold)
            written.append(fold)
            if not args.no_measure:
                try:
                    measured[name] = page.evaluate(MEASURE_JS)
                except Exception as e:
                    measured[name] = {"error": str(e)}
            if name == "desktop":
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(600)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(400)
                full = os.path.join(args.out, "desktop-full.png")
                page.screenshot(path=full, full_page=True)
                written.append(full)
            page.close()
        browser.close()

    for f in written:
        print(f)

    if measured:
        mpath = os.path.join(args.out, "measured.json")
        with open(mpath, "w", encoding="utf-8") as fh:
            json.dump(measured, fh, indent=1)
        print(mpath)

    # Deliberately does NOT print the findings by default. Printing them let a
    # summary be quoted back as if it were an observation - it made fabricating
    # the visual pass easier, not harder. Answer from the images first, then
    # open measured.json and check yourself against it.
    if args.reveal:
        flags = summarise(measured)
        if flags:
            print("\nmeasured:")
            for f in flags:
                print("  %s" % f)
        return 0

    print("""
NOW OPEN THE PNGs AND LOOK AT THEM. Reading the source is not seeing the page.

Answer these from the images, in writing, BEFORE opening measured.json:

  1. What do you see first, second, third on desktop-full.png?
  2. Which block is visually strongest - and is it the hero?
  3. Scrolling the full-page shot, do the blocks look interchangeable in
     height and density, or does the rhythm actually vary?
  4. At 390px: anything colliding, touching an edge, or running off-screen?
  5. Is 390px a designed layout, or the desktop one stacked at the same sizes?
  6. Does the accent read as a decision or as leftover default styling?
  7. Could someone infer your ATTITUDE line from the screenshot alone?

THEN open measured.json and check your answers against it. It records what
actually rendered: type sizes, block heights and largest type per block,
horizontal overflow at 390px, contrast, focus styles. Where your answer and
the measurement disagree, the measurement is right and your answer was a
guess. Say so and re-look.

Questions 1, 5, 6 and 7 are not in the JSON. Nothing can check those but you.
(`--reveal` prints the machine findings - only after you've written yours.)""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
