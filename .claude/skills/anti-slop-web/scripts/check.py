#!/usr/bin/env python3
"""Static token/range/shape audit for anti-slop-web. Python stdlib, no install.

  check.py <file-or-dir>            full audit (tokens + structure)
  check.py <path> --build           token checks only, faster, use mid-build
  check.py <path> --app             dense app/dashboard profile (see PROFILES)

The checks are a floor, not a target. Passing here means nothing has been
verified visually - run shoot.py and look at the page.
"""
import sys, os, re, json, math, colorsys
from html.parser import HTMLParser

EXTS = {".html", ".htm", ".css", ".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte", ".astro"}

# Framework scaffolding and generated output are not design decisions. Judging
# them concatenated with the page produced 11 failures for a clean page.
SKIP_FILE = re.compile(
    r"(^|[.\-])(config|conf)\.(js|ts|mjs|cjs)$|\.(test|spec|stories)\.[jt]sx?$"
    r"|\.min\.(js|css)$|\.d\.ts$|^tailwind\.|^postcss\.|^vite\.|^next\.|^rollup\.",
    re.I)
SKIP_DIR = ("node_modules", ".git", "dist", "build", ".next", "__pycache__",
            "coverage", ".svelte-kit", "out", "vendor")

BANNED_FONTS = ["inter", "roboto", "open sans", "lato", "montserrat", "poppins",
                "nunito", "raleway", "source sans pro", "ui-sans-serif"]

# Named so failures can say which one, and normalised to RGB at import so that
# oklch()/hsl()/rgb() spellings of the same colour are caught too.
#
# Only ACCENTS get a near-neighbour radius. Applying one to neutrals was wrong
# twice over: every warm off-white sits within any sane radius of every other,
# and banned-defaults.md bans neutrals for being *pure grey*, not for being near
# one specific grey. A tinted neutral like #6b6055 is the thing it asks for.
BANNED_ACCENTS = {
    "#3b82f6": "tailwind blue-500", "#2563eb": "tailwind blue-600",
    "#1d4ed8": "tailwind blue-700", "#6366f1": "tailwind indigo-500",
    "#4f46e5": "tailwind indigo-600", "#8b5cf6": "tailwind violet-500",
    "#7c3aed": "tailwind violet-600", "#d97757": "the default terracotta",
}
BANNED_EXACT = {
    "#f4f1ea": "the default cream", "#888888": "pure grey",
    "#666666": "pure grey", "#333333": "pure grey",
}

BANNED_TW = ["blue-500", "blue-600", "blue-700", "indigo-500", "indigo-600",
             "violet-500", "purple-600", "shadow-sm", "shadow-md",
             "from-blue-", "to-purple-", "from-purple-", "to-blue-"]

# Specific enough not to fire on ordinary English. "take your" alone matched
# "Take your machine off the bench"; the banned thing is the full construction.
BANNED_COPY = [
    (r"\bempower(s|ing)? your\b", "empower your"),
    (r"\bseamlessly\b", "seamlessly"),
    (r"\btake[s]? your\b[^.!?]{0,40}\bto the next level\b", "take your X to the next level"),
    (r"\bsupercharge\b", "supercharge"),
    (r"\bbuilt for the modern\b", "built for the modern"),
    (r"\bthe future of\b[^.!?]{0,40}\b(is here|today|has arrived)\b", "the future of X, today"),
    (r"\beffortlessly\b", "effortlessly"),
    (r"\bunlock the (power|potential)\b", "unlock the power"),
    (r"\bgame[- ]changing\b", "game-changing"),
]

EMOJI = re.compile("[\U0001F300-\U0001FAFF✨⚡✅⭐⚙]")

TW_TEXT = {"text-xs": 12, "text-sm": 14, "text-base": 16, "text-lg": 18,
           "text-xl": 20, "text-2xl": 24, "text-3xl": 30, "text-4xl": 36,
           "text-5xl": 48, "text-6xl": 60, "text-7xl": 72, "text-8xl": 96,
           "text-9xl": 128}

TW_ROUND = {"rounded-none": 0, "rounded-sm": 2, "rounded": 4, "rounded-md": 6,
            "rounded-lg": 8, "rounded-xl": 12, "rounded-2xl": 16,
            "rounded-3xl": 24}
TW_ROUND_PILL = {"rounded-full": 999}

PROFILES = {
    # (min type range, check section rhythm)
    "page": (5.0, True),
    "app": (2.5, False),
}


# ---------------------------------------------------------------- input

def gather(target):
    out = []
    if os.path.isfile(target):
        return [target]
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR]
        for f in files:
            if os.path.splitext(f)[1].lower() in EXTS and not SKIP_FILE.search(f):
                out.append(os.path.join(root, f))
    return out


# A comment is not a design decision. Scanning raw text meant prose in comments
# manufactured failures ("...avoid blue-600...") and a stray <section> inside a
# comment moved the first-section window off the real hero.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
# (?<![*\w:]) keeps "./src/**/*.js" and "https://" from opening a comment that
# never closes and swallows the rest of the file.
_BLOCK_COMMENT = re.compile(r"(?<![*\w:])/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"^[ \t]*//[^\n]*", re.M)


def strip_comments(text):
    text = _HTML_COMMENT.sub(" ", text)
    text = _BLOCK_COMMENT.sub(" ", text)
    return _LINE_COMMENT.sub(" ", text)


# Highlighting themes, chart series and inline SVG are data or third-party
# palettes, not the page's colour decisions.
_FONT_DECL = re.compile(
    r"font-family\s*:[^;}\n]*"                  # CSS
    r"|--[\w-]*font[\w-]*\s*:[^;}\n]*"          # tailwind v4 --font-sans token
    r"|font(?:-?family)?\s*:\s*\[[^\]]*\]"      # tailwind config array
    r"|fontFamily\s*:\s*[\"'][^\"']*[\"']"      # JSX style object
    r"|family=[^&\"'>\s]+"                      # google fonts url
    r"|@font-face[^}]*}", re.I)

_CODE_BLOCK = re.compile(r"<(pre|code|svg)\b.*?</\1>", re.S | re.I)
_HL_RULE = re.compile(
    r"[^{}]*\.(tok(en)?|hljs|prism|shiki|cm|highlight|chart|series|sparkline)[\w-]*"
    r"[^{}]*\{[^}]*\}", re.I)


def design_surface(text):
    """The subset of the source that expresses this page's own palette."""
    text = _CODE_BLOCK.sub(" ", text)
    return _HL_RULE.sub(" ", text)


# ---------------------------------------------------------------- colour

def _srgb(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def oklch_to_rgb(L, C, H):
    a, b = C * math.cos(math.radians(H)), C * math.sin(math.radians(H))
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bl = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return tuple(min(255, max(0, round(_srgb(v) * 255))) for v in (r, g, bl))


def rgb_to_oklab(rgb):
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


_HEX = re.compile(r"#([0-9a-fA-F]{3,8})\b")
# the component class must admit unit suffixes (243.4deg, 0.25turn) or the
# whole colour fails to match and is silently skipped
_FUNC = re.compile(
    r"\b(oklch|hsla?|rgba?)\(\s*([0-9.%a-z\-]+)[\s,]+([0-9.%a-z\-]+)[\s,]+([0-9.%a-z\-]+)", re.I)


_ANGLE_UNIT = re.compile(r"(deg|rad|turn|grad)$", re.I)


def _num(tok, scale=1.0):
    # hsl(243.4deg 75.4% 58.6%) is valid CSS; letting the unit reach float()
    # threw ValueError and silently dropped the whole colour.
    tok = _ANGLE_UNIT.sub("", tok.strip())
    if tok.endswith("%"):
        return float(tok[:-1]) / 100.0 * scale
    return float(tok)


def colors_in(text):
    """Every colour the text declares, as RGB tuples, whatever the syntax."""
    out = []
    for m in _HEX.finditer(text):
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h[:3])
        elif len(h) in (6, 8):
            h = h[:6]
        else:
            continue
        out.append(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))
    for m in _FUNC.finditer(text):
        fn, a, b, c = m.group(1).lower(), m.group(2), m.group(3), m.group(4)
        try:
            if fn == "oklch":
                out.append(oklch_to_rgb(_num(a), _num(b, 0.4), _num(c)))
            elif fn.startswith("hsl"):
                r, g, bl = colorsys.hls_to_rgb(
                    (_num(a) % 360) / 360.0, _num(c, 1.0), _num(b, 1.0))
                out.append((round(r * 255), round(g * 255), round(bl * 255)))
            else:
                out.append(tuple(min(255, max(0, round(_num(v, 255.0))))
                                 for v in (a, b, c)))
        except (ValueError, ZeroDivisionError):
            continue
    return out


def _hex_to_rgb(hx):
    return tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5))


_ACCENT_LAB = [(hx, name, rgb_to_oklab(_hex_to_rgb(hx)))
               for hx, name in BANNED_ACCENTS.items()]
_EXACT_RGB = {_hex_to_rgb(hx): (hx, name) for hx, name in BANNED_EXACT.items()}
NEAR = 0.035  # OKLab distance. banned-defaults.md bans "near-neighbours" too.


def banned_color_hits(text):
    hits = {}
    for rgb in colors_in(text):
        if rgb in _EXACT_RGB:
            hx, name = _EXACT_RGB[rgb]
            hits[hx] = (name, "#%02x%02x%02x" % rgb, True)
        lab = rgb_to_oklab(rgb)
        for hx, name, blab in _ACCENT_LAB:
            d = math.dist(lab, blab)
            if d < NEAR:
                got = "#%02x%02x%02x" % rgb
                if d == 0 or hx not in hits:
                    hits[hx] = (name, got, d == 0)
    return hits


def flat_neutrals(text):
    """banned-defaults.md: tint neutrals toward the accent hue. Any perfectly
    achromatic mid-tone is the tell, not just the three greys on the list."""
    out = set()
    for rgb in colors_in(text):
        r, g, b = rgb
        if r == g == b and 24 < r < 232:
            out.add("#%02x%02x%02x" % rgb)
    return out


def hue_families(text):
    """Cluster saturated hues so an accent plus its tints counts once, instead of
    splitting across fixed 30-degree buckets."""
    pts = []
    for rgb in colors_in(text):
        r, g, b = (v / 255.0 for v in rgb)
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        if s > 0.28 and 0.12 < l < 0.88:
            pts.append((h * 360, "#%02x%02x%02x" % rgb))
    fams = []
    for hdeg, hx in sorted(pts):
        for f in fams:
            if min(abs(hdeg - f[0]), 360 - abs(hdeg - f[0])) <= 25:
                f[1].add(hx)
                break
        else:
            fams.append((hdeg, {hx}))
    return fams


# ---------------------------------------------------------------- tokens

def to_px(val, unit):
    v = float(val)
    return v * 16 if unit in ("rem", "em") else v


def resolve_vars(text):
    m = {}
    for mm in re.finditer(r"(--[\w-]+)\s*:\s*([\d.]+)(px|rem|em)\s*[;}]", text):
        m.setdefault(mm.group(1), set()).add(to_px(mm.group(2), mm.group(3).lower()))
    return m


_LEN = re.compile(r"([\d.]+)(px|rem|em)\b")


def font_sizes(text):
    """Includes the endpoints of clamp()/min()/max(). Fluid type is the modern
    default; not parsing it silently switched the dynamic-range rule off."""
    sizes = []
    cv = resolve_vars(text)
    for m in re.finditer(r"font-size\s*:\s*([^;}\n]+)", text, re.I):
        decl = m.group(1)
        # every var() in the declaration, including inside clamp()/min()/max().
        # `clamp(var(--step-4), 8vw, var(--step-6))` previously resolved to
        # nothing, so the display size vanished and the range read as ~1.5x -
        # a false failure that pushes you to rip out fluid type to satisfy it.
        for vm in re.finditer(r"var\(\s*(--[\w-]+)", decl):
            sizes.extend(cv.get(vm.group(1), []))
        for lm in _LEN.finditer(decl):
            sizes.append(to_px(lm.group(1), lm.group(2).lower()))
    for cls, px in TW_TEXT.items():
        if re.search(r"(?<![\w-])" + cls + r"(?![\w-])", text):
            sizes.append(px)
    for m in re.finditer(r"text-\[([\d.]+)(px|rem)\]", text):
        sizes.append(to_px(m.group(1), m.group(2)))
    # JSX / styled-object syntax: style={{ fontSize: "89px" }}
    for m in re.finditer(r"fontSize\s*:\s*[\"']?([\d.]+)(px|rem|em)", text):
        sizes.append(to_px(m.group(1), m.group(2).lower()))
    return sizes


# A hard floor alone can't separate section rhythm from card padding: 32 threw
# away a real tight rhythm, 24 let `.card { padding: 24px }` count as a third
# section value and mask uniform rhythm. Shorthand arity is the honest signal -
# `padding: 96px 0` states its vertical value, `padding: 24px` is ambiguous.
PAD_FLOOR = 24        # explicitly vertical (padding-block / py- / 2-value shorthand)
PAD_FLOOR_AMBIG = 48  # single-value shorthand, probably a card


def paddings(text):
    vals = []
    cv = resolve_vars(text)
    # weight each CSS rule by how many elements it actually styles, so one
    # `header, section { padding-block: 5rem }` reads as the page-wide flatness
    # it is rather than as a single data point
    for rule in _CSS_RULE.finditer(text):
        sel, body = rule.group(1), rule.group(2)
        for m in re.finditer(r"padding(-block|-top|-bottom)?\s*:\s*([^;}\n\"']+)", body, re.I):
            raw = m.group(2)
            vv = None
            var = re.match(r"\s*var\(\s*(--[\w-]+)", raw)
            if var:
                got = sorted(cv.get(var.group(1), []))
                vv, vertical = (round(got[0]) if got else None), True
            else:
                parts = [p for p in re.findall(r"([\d.]+)(px|rem|em)?", raw) if p[0]]
                if parts:
                    vv = round(to_px(parts[0][0], (parts[0][1] or "px").lower()))
                    vertical = bool(m.group(1)) or len(parts) >= 2
            if vv is None:
                continue
            if vv >= (PAD_FLOOR if vertical else PAD_FLOOR_AMBIG):
                vals.extend([vv] * _selector_usage(sel, text))
    for m in re.finditer(r"(?<![\w-])py-(\d+)(?![\w-])", text):
        vals.append(int(m.group(1)) * 4)
    for m in re.finditer(r"(?<![\w-])py-\[([\d.]+)(px|rem)\]", text):
        vals.append(round(to_px(m.group(1), m.group(2))))
    for m in re.finditer(r"padding(?:Block|Top|Bottom)\s*:\s*[\"']?([\d.]+)(px|rem)", text):
        vals.append(round(to_px(m.group(1), m.group(2).lower())))
    return [v for v in vals if v >= PAD_FLOOR]


_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
_RADIUS_DECL = re.compile(r"border-radius\s*:\s*([\d.]+)(px|rem|em)", re.I)
PILL_PX = 100  # a pill is a role, not a surface radius - never counts as variety


_CLASS_ATTR = re.compile(r'class(?:Name)?\s*=\s*["\']([^"\']+)["\']')
_cache = {}


def _memo(kind, text, build):
    key = (kind, len(text), hash(text))
    if key not in _cache:
        _cache[key] = build()
    return _cache[key]


def class_counts(text):
    """Precomputed once. Scanning the whole blob per CSS rule made the radius
    check quadratic: 566 KB took 7s before this."""
    def build():
        c = {}
        for m in _CLASS_ATTR.finditer(text):
            for tok in m.group(1).split():
                c[tok] = c.get(tok, 0) + 1
        return c
    return _memo("classes", text, build)


_BLOCK_TAGS = ("section", "article", "header", "footer", "main", "aside",
               "figure", "div", "nav", "li")


def _selector_usage(selector, text):
    """How many elements actually wear this rule. A CSS rule is written once but
    may style forty cards; counting declarations instead of usages let uniform
    radius hide in a stylesheet, and let `header, section { padding-block: X }`
    count as a single padded block when it rhythm-flattens the whole page."""
    total = 0
    cc = class_counts(text)
    for n in re.findall(r"\.([\w-]+)", selector):
        total += cc.get(n, 0)
    for t in re.findall(r"(?<![\w.\-#])([a-z]+)(?![\w\-(])", selector):
        if t in _BLOCK_TAGS:
            total += len(re.findall(r"<%s\b" % t, text, re.I))
    return max(1, total)


def radii(text):
    """Weighted by how many elements each radius reaches. Counting distinct
    class names meant one rounded-full pill disabled the rule permanently."""
    return _memo("radii", text, lambda: _radii(text))


def _radii(text):
    vals = []
    for m in _CSS_RULE.finditer(text):
        d = _RADIUS_DECL.search(m.group(2))
        if not d:
            continue
        px = round(to_px(d.group(1), d.group(2).lower()), 1)
        if px < PILL_PX:
            vals.extend([px] * _selector_usage(m.group(1), text))
    for m in re.finditer(r'style="[^"]*border-radius\s*:\s*([\d.]+)(px|rem|em)', text, re.I):
        px = round(to_px(m.group(1), m.group(2).lower()), 1)
        if px < PILL_PX:
            vals.append(px)
    for cls, px in TW_ROUND.items():
        vals.extend([px] * len(re.findall(r"(?<![\w-])" + cls + r"(?![\w-])", text)))
    return vals


def pill_count(text):
    return sum(len(re.findall(r"(?<![\w-])" + c + r"(?![\w-])", text))
               for c in TW_ROUND_PILL)


# ---------------------------------------------------------------- shapes

SHAPE_CTA = ["ready to get started", "ready to start", "ready to dive",
             "get started today", "start your free", "join thousands",
             "join 1", "start building today", "ready to transform"]

SHAPE_CLOUD = ["trusted by", "used by teams", "backed by", "loved by",
               "powering teams", "as seen in"]

BREAKOUT = ["100vw", "-mx-", "margin-inline:-", "margin-left:-", "margin-left: -",
            "full-bleed", "fullbleed", "col-span-full", "w-screen"]

# Section-shape phrases only count as a section label - in a heading, or as a
# short standalone line. "Ray was trusted by every landlord" is not a logo cloud.
_LABELISH = re.compile(
    r"<(h[1-6]|p|span|div|strong)\b[^>]*>\s*([^<]{0,70})\s*</\1>", re.I)


def label_texts(html):
    return [m.group(2).lower() for m in _LABELISH.finditer(html)]


def dominance(vals):
    if not vals:
        return None
    counts = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    top = max(counts, key=counts.get)
    return top, counts[top], len(vals)


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}
TEMPLATE_COUNTS = (3, 4)  # the counts a grid imposes; 12 photos chose themselves


class _Dom(HTMLParser):
    """Just enough tree to count a container's element children."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "#root", "cls": "", "style": "", "kids": []}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        node = {"tag": tag, "cls": (a.get("class") or a.get("classname") or ""),
                "style": a.get("style") or "", "kids": []}
        self.stack[-1]["kids"].append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                return


def _grid_classes(text):
    """Class names whose CSS rule makes them a grid container."""
    out = set()
    for m in _CSS_RULE.finditer(text):
        if re.search(r"display\s*:\s*grid|grid-template-columns", m.group(2), re.I):
            out.update(re.findall(r"\.([\w-]+)", m.group(1)))
    return out


def _is_grid(node, gclasses):
    cls = node["cls"].split()
    return (bool(gclasses.intersection(cls))
            or any(c.startswith("grid-cols-") for c in cls)
            or "grid-template-columns" in node["style"])


def template_grids(text):
    """Grid containers whose children are all identical and number 3 or 4.

    A regex could only count how often a class appeared in the file, which
    cannot tell a 3-up feature template from a 12-print photo grid or a
    13-speaker schedule - both of which the count-based check flagged."""
    def build():
        try:
            p = _Dom()
            p.feed(text)
        except Exception:
            return []
        gclasses = _grid_classes(text)
        found = []

        def walk(node):
            kids = node["kids"]
            if _is_grid(node, gclasses) and len(kids) in TEMPLATE_COUNTS:
                sigs = {(k["tag"], k["cls"].split()[0] if k["cls"].split() else "")
                        for k in kids}
                if len(sigs) == 1:
                    tag, cls = sigs.pop()
                    found.append((tag, cls, len(kids)))
            for k in kids:
                walk(k)

        walk(p.root)
        return found
    return _memo("grids", text, build)


def first_class_tokens(blob):
    out = []
    for m in re.finditer(r'class(?:Name)?\s*=\s*["\']([^"\']+)["\']', blob):
        toks = m.group(1).split()
        if toks:
            out.append(toks[0])
    return out


def hero_region(blob):
    """The neighbourhood of the first <h1>. Anchoring on <section> missed every
    hero built in <header>, <div class="hero"> or a React component."""
    m = re.search(r"<h1\b", blob, re.I)
    if not m:
        return None
    return blob[max(0, m.start() - 900):m.start() + 1400]


def structural(blob, low, profile):
    issues, notes = [], []
    min_range, check_rhythm = PROFILES[profile]

    if check_rhythm:
        d = dominance(paddings(blob))
        if d and d[2] >= 4 and d[1] / d[2] >= 0.55:
            issues.append("uniform section rhythm: %gpx used %d of %d times - vary the vertical scale"
                          % (d[0], d[1], d[2]))

    rad = [r for r in radii(blob) if r > 0]
    d = dominance(rad)
    if d and d[2] >= 4 and d[1] / d[2] >= 0.7:
        issues.append("uniform radius: %gpx used %d of %d times - derive by role or use 0"
                      % (d[0], d[1], d[2]))

    centered = len(re.findall(r"text-align\s*:\s*center", low)) + \
        len(re.findall(r"(?<![\w-])text-center(?![\w-])", low))
    if re.search(r"(body|main|\.container)\s*\{[^}]*text-align\s*:\s*center", low):
        issues.append("centered-everything: centering set at body/container level, everything inherits it - asymmetry reads as designed")
    elif centered >= 4:
        issues.append("centered-everything layout (%d centering rules) - asymmetry reads as designed"
                      % centered)

    for tag, cls, n in template_grids(blob):
        issues.append("n-up card grid: %d identical <%s%s> in a grid - the item count matches the grid, so the grid chose the content"
                      % (n, tag, (" class=%s" % cls) if cls else ""))

    h = hero_region(blob)
    if h:
        has_label = bool(re.search(r'class(?:Name)?="[^"]*(eyebrow|badge|pill|kicker|tag)', h, re.I))
        btns = len(re.findall(r"<(a|button)\b[^>]*>", h, re.I))
        if has_label and btns >= 2:
            issues.append("template hero: eyebrow/badge + h1 + paragraph + two buttons")

    labels = label_texts(blob)
    for s in SHAPE_CTA:
        if any(s in t for t in labels):
            issues.append("template closing CTA section: '%s'" % s)
            break
    for s in SHAPE_CLOUD:
        if any(t.startswith(s) or t == s for t in labels):
            issues.append("logo-cloud / social-proof strip: '%s'" % s)
            break

    trophies = re.findall(r">\s*[\d.,]+\s*(?:[km]\+?|\+|%|★)\s*<", low)
    if len(trophies) >= 3 and re.search(r'class(?:name)?="[^"]*stat', low):
        issues.append("three-big-numbers stat strip")

    if not any(b in low for b in BREAKOUT):
        # Deliberately does not claim there ISN'T one. A structural escape -
        # placing an element outside the max-width wrapper - uses no idiom to
        # match, so asserting absence here rewarded adding a decorative 100vw
        # div to turn the note green. shoot.py measures it properly.
        notes.append("no full-bleed idiom (100vw / -mx- / w-screen) in the source - "
                     "if your grid break is structural that's fine, confirm it in "
                     "measured.json widerThanColumn rather than adding one to satisfy this")

    sizes = sorted(set(font_sizes(blob)))
    if len(sizes) >= 3:
        gaps = [sizes[i + 1] / sizes[i] for i in range(len(sizes) - 1)]
        if max(gaps) > 2.4:
            notes.append("gap of %.1fx in the type scale - confirm the display size comes from the scale, not bolted on"
                         % max(gaps))
    if len(sizes) <= 3:
        notes.append("only %d type sizes in use - a derived scale usually shows 4-6" % len(sizes))

    notes.append("negative space and hierarchy cannot be checked statically - use shoot.py and look")
    return issues, notes


def looks_like_app(blob, low):
    controls = (low.count("<input") + low.count("<select") + low.count("<textarea")
                + low.count('role="switch"') + low.count("aria-current"))
    # A page carrying real prose is a document, whatever furniture it contains.
    # One spec table on a marketing page used to trip this on every run, and a
    # suggestion that fires every time is a suggestion nobody reads.
    prose_words = len(re.sub(r"<[^>]+>", " ", blob).split())
    if prose_words > 400 and controls < 3:
        return False
    dense = low.count("<table") >= 2 or len(re.findall(r"<t[hd]\b", low)) >= 20
    return (dense
            or controls >= 3
            or (low.count("<section") == 0 and low.count("panel") >= 3)
            or bool(re.search(r"<(aside|nav)\b", low) and re.search(r"<main\b", low)))


# ---------------------------------------------------------------- scan

def scan(paths, build_only=False, profile="page"):
    issues, notes = [], []
    blob = ""
    for p in paths:
        try:
            blob += strip_comments(open(p, encoding="utf-8", errors="ignore").read()) + "\n"
        except OSError:
            continue
    low = blob.lower()
    surface = design_surface(blob)
    prose = re.sub(r"<blockquote.*?</blockquote>", " ", low, flags=re.S)
    min_range, _ = PROFILES[profile]

    # Only where a font is *declared*. Matching the bare name anywhere in the
    # source flagged an article that discussed Poppins in a sentence, and the
    # old boundary set was position-lucky: ">Inter and" escaped, " Poppins "
    # did not. Neither outcome had anything to do with the page's type.
    decls = " || ".join(m.group(0) for m in _FONT_DECL.finditer(low))
    for f in BANNED_FONTS:
        if re.search(r"(?<![\w-])" + re.escape(f).replace(r"\ ", r"[+\s-]") + r"(?![\w-])", decls):
            issues.append("banned typeface: %s" % f)
    if re.search(r"(?<![\w-])font-sans(?![\w-])", low) and "fontfamily" not in low:
        notes.append("font-sans with no fontFamily override - that is the Tailwind default stack, name a face")

    for hx, (name, got, exact) in sorted(banned_color_hits(surface).items()):
        if exact:
            issues.append("banned color: %s (%s)" % (hx, name))
        else:
            issues.append("banned color: %s is a near-neighbour of %s (%s)"
                          % (got, hx, name))

    for c in BANNED_TW:
        # Prefix-tolerant: in real Tailwind these are always prefixed
        # (bg-blue-600, hover:text-indigo-500), so the old left-anchored
        # lookbehind could never match. Entries that already end in "-" are
        # gradient stubs (from-blue-500), so they take no trailing boundary.
        tail = "" if c.endswith("-") else r"(?![\w-])"
        for m in re.finditer(r"(?<![\w])[\w-]*?" + re.escape(c) + tail, low):
            # `--shadow-sm: 0 12px 40px ...` declares a custom shadow that
            # happens to be named after the utility; it is not the utility.
            if m.group(0).startswith("--"):
                continue
            issues.append("banned utility: %s" % c)
            break

    flat = flat_neutrals(surface)
    if flat:
        issues.append("pure grey neutral(s) %s - tint neutrals toward the accent hue"
                      % " ".join(sorted(flat)[:4]))

    if re.search(r"background-clip\s*:\s*text", low) and "linear-gradient" in low:
        issues.append("gradient text on headline")
    if "text-transparent" in low and "bg-gradient" in low:
        issues.append("gradient text on headline")
    if re.search(r"backdrop-(filter|blur)", low):
        issues.append("glassmorphism (backdrop blur)")
    if re.search(r"box-shadow\s*:\s*[^;]*rgba?\([^)]*\)\s*(?:,|;)", low) and low.count("box-shadow") > 4:
        notes.append("box-shadow used %d times - consider whether cards are earning their keep" % low.count("box-shadow"))

    # emoji only counts as an icon when it IS the element - emoji inside a
    # sentence is the page's subject matter, not decoration
    icons = re.findall(r">\s*(" + EMOJI.pattern + r"[\s️]*){1,3}\s*<", blob)
    # data-driven icon lists: { icon: "🚀", title: ... } is the same tell in JSX
    icons += re.findall(r"(?:icon|emoji|glyph)\s*:\s*[\"']" + EMOJI.pattern, blob, re.I)
    if len(icons) >= 3:
        issues.append("emoji used as icons (%d found)" % len(icons))

    for pat, label in BANNED_COPY:
        if re.search(pat, prose, re.I):
            issues.append("template copy: '%s'" % label)

    sizes = sorted(set(font_sizes(blob)))
    if len(sizes) >= 2:
        rng = sizes[-1] / sizes[0]
        # banned-defaults.md's own claim is that slop sits around 2.5x, so that
        # is where the hard failure belongs. Between there and the target the
        # honest report is "verify it's felt" - a product page at 3.7x and a
        # docs page at 2.9x are utilitarian, not generic, and failing them
        # taught the reader to skim past every other line.
        if rng < min_range * 0.6:
            issues.append("type dynamic range %.1fx (need >= %gx): %gpx -> %gpx"
                          % (rng, min_range, sizes[0], sizes[-1]))
        elif rng < min_range:
            notes.append("type range %.1fx is just under the %gx target (%gpx -> %gpx) - confirm the display size is doing real work"
                         % (rng, min_range, sizes[0], sizes[-1]))
        else:
            notes.append("type range %.1fx (%gpx -> %gpx) OK" % (rng, sizes[0], sizes[-1]))
    elif re.search(r"<h[1-6]\b", low) or len(blob) > 1500:
        # A real page whose scale can't be parsed has silently skipped the
        # flagship rule - that is a failure to verify, not a clean bill.
        issues.append("could not read a type scale - the >= %gx dynamic range rule did NOT run, verify it by hand"
                      % min_range)
    else:
        notes.append("no type scale found (file is near-empty) - nothing to range-check")

    if PROFILES[profile][1]:
        allpads = paddings(blob)
        pads = sorted(set(allpads))
        # one or two padded blocks is not a rhythm to have opinions about; a
        # single-column docs page was failing for having one <main>
        if len(allpads) >= 3 and len(pads) < 3:
            issues.append("only %d distinct section padding value(s) %s (need >= 3)"
                          % (len(pads), pads))
        elif pads:
            notes.append("%d distinct section paddings %s OK" % (len(pads), pads))

    # Skipped under --app: one deliberate surface radius across every panel is a
    # committed shape language in dense UI, not a default.
    if profile != "app":
        nonzero = [r for r in radii(blob) if r > 0]
        rad = sorted(set(nonzero))
        if len(rad) == 1 and len(nonzero) >= 4:
            issues.append("single radius %gpx on %d elements (%d pills exempt) - derive by role or use 0"
                          % (rad[0], len(nonzero), pill_count(blob)))

    fams = hue_families(surface)
    if len(fams) > 3:
        sample = {int(h): sorted(v)[:3] for h, v in fams[:6]}
        issues.append("%d distinct saturated hue families - expect 1 accent. %s"
                      % (len(fams), json.dumps(sample)))

    if not build_only:
        si, sn = structural(blob, low, profile)
        issues += si
        notes += sn

    if profile == "page" and looks_like_app(blob, low):
        notes.append("this looks like dense app UI - if so re-run with --app, which relaxes the type-range and section-rhythm rules")

    return issues, notes


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    build_only = "--build" in sys.argv
    profile = "app" if "--app" in sys.argv else "page"
    if not args:
        print(__doc__.strip())
        return 2
    paths = gather(args[0])
    if not paths:
        print("no source files found under %s" % args[0])
        return 2
    issues, notes = scan(paths, build_only, profile)
    print("scanned %d file(s), profile=%s\n" % (len(paths), profile))
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
