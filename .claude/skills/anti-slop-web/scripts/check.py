#!/usr/bin/env python3
import sys, os, re, json, colorsys

EXTS = {".html", ".htm", ".css", ".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte", ".astro"}

BANNED_FONTS = ["inter", "roboto", "open sans", "lato", "montserrat", "poppins",
                "nunito", "raleway", "source sans pro", "ui-sans-serif"]

BANNED_HEX = {"#3b82f6", "#2563eb", "#1d4ed8", "#6366f1", "#4f46e5", "#8b5cf6",
              "#7c3aed", "#d97757", "#f4f1ea", "#888888", "#666666", "#333333"}

BANNED_TW = ["blue-500", "blue-600", "blue-700", "indigo-500", "indigo-600",
             "violet-500", "purple-600", "shadow-sm", "shadow-md",
             "from-blue-", "to-purple-", "from-purple-", "to-blue-"]

BANNED_COPY = ["empower your", "seamlessly", "next level", "supercharge",
               "built for the modern", "the future of", "effortlessly",
               "unlock the power", "take your", "game-changing"]

EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2728\u26A1\u2705\u2b50\u2699]")

TW_TEXT = {"text-xs": 12, "text-sm": 14, "text-base": 16, "text-lg": 18,
           "text-xl": 20, "text-2xl": 24, "text-3xl": 30, "text-4xl": 36,
           "text-5xl": 48, "text-6xl": 60, "text-7xl": 72, "text-8xl": 96,
           "text-9xl": 128}

TW_ROUND = {"rounded-none": 0, "rounded-sm": 2, "rounded": 4, "rounded-md": 6,
            "rounded-lg": 8, "rounded-xl": 12, "rounded-2xl": 16,
            "rounded-3xl": 24, "rounded-full": 999}


def gather(target):
    out = []
    if os.path.isfile(target):
        return [target]
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in
                   ("node_modules", ".git", "dist", "build", ".next", "__pycache__")]
        for f in files:
            if os.path.splitext(f)[1].lower() in EXTS:
                out.append(os.path.join(root, f))
    return out


def to_px(val, unit):
    v = float(val)
    return v * 16 if unit == "rem" or unit == "em" else v


def font_sizes(text):
    sizes = []
    for m in re.finditer(r"font-size\s*:\s*([\d.]+)(px|rem|em)", text, re.I):
        sizes.append(to_px(m.group(1), m.group(2).lower()))
    for cls, px in TW_TEXT.items():
        if re.search(r"(?<![\w-])" + cls + r"(?![\w-])", text):
            sizes.append(px)
    for m in re.finditer(r"text-\[([\d.]+)(px|rem)\]", text):
        sizes.append(to_px(m.group(1), m.group(2)))
    return sizes


def paddings(text):
    vals = []
    for m in re.finditer(r"padding(?:-block|-top|-bottom)?\s*:\s*([\d.]+)(px|rem)", text, re.I):
        vals.append(round(to_px(m.group(1), m.group(2).lower())))
    for m in re.finditer(r"(?<![\w-])py-(\d+)(?![\w-])", text):
        vals.append(int(m.group(1)) * 4)
    for m in re.finditer(r"(?<![\w-])py-\[([\d.]+)(px|rem)\]", text):
        vals.append(round(to_px(m.group(1), m.group(2))))
    return [v for v in vals if v >= 32]


def radii(text):
    vals = []
    for m in re.finditer(r"border-radius\s*:\s*([\d.]+)(px|rem)", text, re.I):
        vals.append(round(to_px(m.group(1), m.group(2).lower()), 1))
    for cls, px in TW_ROUND.items():
        if re.search(r"(?<![\w-])" + cls + r"(?![\w-])", text):
            vals.append(px)
    return vals


def hues(text):
    found = {}
    for m in re.finditer(r"#([0-9a-fA-F]{6})(?![0-9a-fA-F])", text):
        h = m.group(1).lower()
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
        if ss > 0.28 and 0.12 < ll < 0.88:
            found.setdefault(int(hh * 360) // 30, set()).add("#" + h)
    return found


def scan(paths):
    issues = []
    notes = []
    blob = ""
    for p in paths:
        try:
            blob += open(p, encoding="utf-8", errors="ignore").read() + "\n"
        except OSError:
            continue
    low = blob.lower()

    for f in BANNED_FONTS:
        if re.search(r"['\"\s:,]" + re.escape(f) + r"['\"\s,;)]", low):
            issues.append("banned typeface: %s" % f)

    for hx in BANNED_HEX:
        if hx in low:
            issues.append("banned color: %s" % hx)

    for c in BANNED_TW:
        if re.search(r"(?<![\w-])" + re.escape(c), low):
            issues.append("banned utility: %s" % c)

    if re.search(r"background-clip\s*:\s*text", low) and "linear-gradient" in low:
        issues.append("gradient text on headline")
    if "text-transparent" in low and "bg-gradient" in low:
        issues.append("gradient text on headline")
    if re.search(r"backdrop-(filter|blur)", low):
        issues.append("glassmorphism (backdrop blur)")
    if re.search(r"box-shadow\s*:\s*[^;]*rgba?\([^)]*\)\s*(?:,|;)", low) and low.count("box-shadow") > 4:
        notes.append("box-shadow used %d times - consider whether cards are earning their keep" % low.count("box-shadow"))

    emo = EMOJI.findall(blob)
    if len(emo) >= 3:
        issues.append("emoji used as icons (%d found)" % len(emo))

    for phrase in BANNED_COPY:
        if phrase in low:
            issues.append("template copy: '%s'" % phrase)

    sizes = sorted(set(font_sizes(blob)))
    if len(sizes) >= 2:
        rng = sizes[-1] / sizes[0]
        if rng < 5:
            issues.append("type dynamic range %.1fx (need >= 5x): %gpx -> %gpx"
                          % (rng, sizes[0], sizes[-1]))
        else:
            notes.append("type range %.1fx (%gpx -> %gpx) OK" % (rng, sizes[0], sizes[-1]))
    else:
        notes.append("could not read a type scale - check manually")

    pads = sorted(set(paddings(blob)))
    if pads and len(pads) < 3:
        issues.append("only %d distinct section padding value(s) %s (need >= 3)"
                      % (len(pads), pads))
    elif pads:
        notes.append("%d distinct section paddings %s OK" % (len(pads), pads))

    rad = sorted(set(radii(blob)))
    nonzero = [r for r in rad if r > 0]
    if len(nonzero) == 1 and blob.lower().count("rounded") + low.count("border-radius") > 5:
        issues.append("single radius %gpx applied uniformly - derive by role or use 0" % nonzero[0])

    hb = hues(blob)
    if len(hb) > 3:
        sample = {k: sorted(v)[:3] for k, v in list(hb.items())[:6]}
        issues.append("%d distinct saturated hue families - expect 1 accent. %s"
                      % (len(hb), json.dumps(sample)))

    if len(re.findall(r"grid-cols-3(?![\w-])", low)) >= 1 and re.search(r"(feature|benefit)", low):
        notes.append("3-column feature grid present - confirm there are genuinely 3 items")

    return issues, notes


def main():
    if len(sys.argv) < 2:
        print("usage: check.py <file-or-dir>")
        return 2
    paths = gather(sys.argv[1])
    if not paths:
        print("no source files found under %s" % sys.argv[1])
        return 2
    issues, notes = scan(paths)
    print("scanned %d file(s)\n" % len(paths))
    for n in notes:
        print("  note  %s" % n)
    if notes:
        print("")
    if not issues:
        print("PASS - no banned defaults or range violations found")
        print("static checks are a floor, not a target: now screenshot and look at it")
        return 0
    for i in sorted(set(issues)):
        print("  FAIL  %s" % i)
    print("\n%d issue(s). Fix, then re-run, then screenshot and look at it." % len(set(issues)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
