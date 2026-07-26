#!/usr/bin/env python3
import sys, re, os

# Source pages routinely contain em-dashes and curly quotes; a Windows console
# defaults to cp1252 and dies printing them mid-inventory.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STOP = set("""a an the and or but if then than that this these those of in on at to for with from by as is
are was were be been being it its it's you your we our they their he she his her not no do does did so
such can could will would should may might must have has had here there what which who whom when where why
how all any both each few more most other some only own same too very just also into over under about
after before between during without within across per up down out off again further once""".split())

REQ_BLOCKS = ("li", "blockquote", "td", "dd", "figcaption")


def text_of(html):
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&mdash;", "-")
          .replace("&middot;", "-").replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"\s+", " ", t).strip()


def blocks(html):
    out = []
    for tag in REQ_BLOCKS:
        for m in re.finditer(r"<%s\b[^>]*>(.*?)</%s>" % (tag, tag), html, re.S | re.I):
            s = text_of(m.group(1))
            if len(s.split()) >= 2:
                out.append((tag, s))
    return out


def norm(s):
    s = re.sub(r"[^\w%$+./-]", "", s.lower())
    return s.strip(".-/")


def tokens(s):
    return [w for w in re.split(r"\s+", s) if w]


UNITS = ("gb|tb|mb|kb|day|days|week|weeks|month|months|year|years|hour|hours|min|mins|"
         "minute|minutes|second|seconds|project|projects|user|users|seat|seats|tool|tools|"
         "member|members|x|bit")


def required_atoms(txt):
    atoms = set()
    for w in tokens(txt):
        c = w.strip(".,;:!?()[]\"'")
        if not c or c.isdigit():
            continue
        if re.search(r"\d", c):
            atoms.add(norm(c))
        elif len(c) >= 3 and c.isupper() and c.isalpha():
            atoms.add(norm(c))
    for m in re.finditer(r"[$£€]\s?[\d,]+(?:\.\d+)?\s?[kmb]?\+?", txt, re.I):
        atoms.add(norm(m.group(0)))
    for m in re.finditer(r"\d[\d,.]*\s?[-]?\s?(?:%s)\b" % UNITS, txt, re.I):
        atoms.add(norm(m.group(0)))
    return {a for a in atoms if a}


def advisory_atoms(txt):
    lower_used = {w.strip(".,;:!?()[]\"'").lower() for w in tokens(txt)
                  if w[:1].islower()}
    out = set()
    for w in tokens(txt):
        c = w.strip(".,;:!?()[]\"'")
        if len(c) < 3 or not c[0].isupper() or c.isupper() or re.search(r"\d", c):
            continue
        if c.lower() in STOP:
            continue
        inner_caps = any(ch.isupper() for ch in c[1:])
        if inner_caps or c.lower() not in lower_used:
            out.add(c)
    return out


_HEAD = re.compile(r"<(h[1-6])\b[^>]*>(.*?)</\1>", re.S | re.I)

# Qualifiers that scope a claim. Losing one turns "report on request" into
# "we are certified" - the fact survives the atom check and the page now says
# something the original did not.
HEDGE = re.compile(
    r"\b(on request|by request|on demand|available|optional|add-?ons?|up to|"
    r"as low as|starting at|coming soon|in beta|planned|where applicable|"
    r"additional cost|extra cost|billed separately|subject to|estimated|"
    r"typically|average|coming|coming to)\b", re.I)


def sections(html):
    """(label, body_html) per heading, deepest-first, so a fact is attributed to
    the most specific heading that contains it."""
    marks = [(m.end(), int(m.group(1)[1]), text_of(m.group(2)))
             for m in _HEAD.finditer(html)]
    starts = [m.start() for m in _HEAD.finditer(html)]
    out = []
    for i, (end_of_head, lvl, label) in enumerate(marks):
        stop = len(html)
        for j in range(i + 1, len(marks)):
            if marks[j][1] <= lvl:
                stop = starts[j]
                break
        out.append((lvl, label, html[end_of_head:stop]))
    out.sort(key=lambda s: -s[0])          # deepest heading wins
    return out


def _sections_raw(html):
    return sections(html)


def owner_map(html):
    """atom -> the single heading it lives under, or None if ambiguous.

    A fact nested under h1 > h2 belongs to the h2, so ownership is taken at the
    deepest level that contains it. A fact repeated across sibling sections (a
    trial term restated under every tier) has no single owner and is skipped -
    otherwise an arbitrary pick would read as a move on the next rebuild."""
    seen = {}
    for lvl, label, body in _sections_raw(html):
        for a in required_atoms(text_of(body)):
            seen.setdefault(a, []).append((lvl, label))
    owners = {}
    for a, hits in seen.items():
        deepest = max(h[0] for h in hits)
        labels = {h[1] for h in hits if h[0] == deepest}
        if len(labels) == 1:
            owners[a] = labels.pop()
    return owners


def moved_facts(o_html, n_html, shared):
    """Facts that survived but changed owner - the failure the atom check is
    blind to. Only flagged when the NEW owner is also a heading that existed in
    the original: rewording a heading is allowed, re-parenting a fact is not."""
    o_own, n_own = owner_map(o_html), owner_map(n_html)
    o_labels = {norm(l.lower()) for _, l, _ in sections(o_html) if l}
    out = []
    for a in sorted(shared):
        o, n = o_own.get(a), n_own.get(a)
        if not o or not n:
            continue
        if norm(o.lower()) != norm(n.lower()) and norm(n.lower()) in o_labels:
            out.append((a, o, n))
    return out


def _keys(text):
    return [w for w in (t.lower().strip(".,;:!?()[]\"'") for t in tokens(text))
            if w and w not in STOP]


def dropped_hedges(o_blocks, n_txt):
    """Blocks that carried a qualifier in the original and don't in the rebuild.
    Matched by best token window rather than exact text, so rewording is fine and
    only the disappearance of the qualifier is reported."""
    n_tok = tokens(n_txt)
    n_low = [w.lower().strip(".,;:!?()[]\"'") for w in n_tok]
    # word -> positions, so each block only tests windows anchored on its rarest
    # word instead of sliding across the whole document (43 KB went 2.8s -> 0.2s)
    index = {}
    for i, w in enumerate(n_low):
        if w:
            index.setdefault(w, []).append(i)

    out = []
    for tag, b in o_blocks:
        if not HEDGE.search(b):
            continue
        keys = [k for k in _keys(b) if not HEDGE.match(k)]
        if len(keys) < 2:
            continue
        width = len(keys) + 12
        anchor = min(keys, key=lambda k: len(index.get(k, ())))
        if anchor not in index:
            continue                        # block is largely gone; already reported
        best, at = 0, 0
        for p in index[anchor]:
            start = max(0, p - width // 2)
            win = set(n_low[start:start + width])
            hit = sum(1 for k in keys if k in win)
            if hit > best:
                best, at = hit, start
        if best < max(2, len(keys) * 0.6):
            continue
        if not HEDGE.search(" ".join(n_tok[at:at + width])):
            out.append((tag, b))
    return out


def covered(block, hay_words):
    ws = [norm(w) for w in tokens(block) if norm(w) and norm(w) not in STOP]
    if not ws:
        return True
    hit = sum(1 for w in ws if w in hay_words)
    return hit / len(ws) >= 0.7


def main():
    if len(sys.argv) < 2:
        print("usage: content.py <original.html> [rebuilt.html]")
        print("  one arg : print the content inventory that must survive")
        print("  two args: diff the rebuild against it, exit 1 if anything was lost")
        return 2

    src = open(sys.argv[1], encoding="utf-8", errors="ignore").read()
    o_txt = text_of(src)
    o_req = required_atoms(o_txt)
    o_adv = advisory_atoms(o_txt)
    o_blk = blocks(src)

    if len(sys.argv) == 2:
        print("REQUIRED atoms (%d) - facts, prices, quantities, standards:" % len(o_req))
        print("  " + "  ".join(sorted(o_req)))
        print("\nREQUIRED blocks (%d) - list items, quotes, table cells:" % len(o_blk))
        for t, b in o_blk:
            print("  <%s> %s" % (t, b[:90]))
        print("\nADVISORY names (%d) - brands, people, products:" % len(o_adv))
        print("  " + "  ".join(sorted(o_adv)))
        print("\nAll REQUIRED items must appear in the rebuild. Presentation may change; facts may not.")
        return 0

    new = open(sys.argv[2], encoding="utf-8", errors="ignore").read()
    n_txt = text_of(new)
    n_req = required_atoms(n_txt)
    n_words = {norm(w) for w in tokens(n_txt)}
    n_lower = {norm(w) for w in tokens(n_txt.lower())}

    lost_atoms = sorted(o_req - n_req)
    lost_blocks = [(t, b) for t, b in o_blk if not covered(b, n_words)]
    lost_names = sorted(n for n in o_adv if norm(n.lower()) not in n_lower)
    moved = moved_facts(src, new, o_req & n_req)
    hedges = dropped_hedges([(t, b) for t, b in o_blk
                             if covered(b, n_words)], n_txt)

    tot_r = len(o_req) + len(o_blk)
    kept_r = tot_r - len(lost_atoms) - len(lost_blocks)
    print("content inventory: %d required items, %d kept, %d lost"
          % (tot_r, kept_r, len(lost_atoms) + len(lost_blocks)))

    if lost_atoms:
        print("\n  LOST facts/quantities (%d):" % len(lost_atoms))
        for a in lost_atoms:
            print("    - %s" % a)
    if lost_blocks:
        print("\n  LOST blocks (%d):" % len(lost_blocks))
        for t, b in lost_blocks:
            print("    - <%s> %s" % (t, b[:100]))
    if moved:
        print("\n  MOVED facts - present, but attached to a different thing (%d):" % len(moved))
        for a, o, n in moved:
            print("    - '%s' was under \"%s\", is now under \"%s\"" % (a, o, n))
    if hedges:
        print("\n  DROPPED qualifiers - the claim got stronger (%d):" % len(hedges))
        for t, b in hedges:
            print("    - <%s> %s" % (t, b[:100]))
            print("      the qualifier is gone in the rebuild; the page now claims more")
    if lost_names:
        print("\n  advisory - names absent (%d), check each is deliberate:" % len(lost_names))
        print("    " + "  ".join(lost_names))

    if lost_atoms or lost_blocks or moved or hedges:
        print("\nFAIL - a rebuild redesigns the page, it does not replace the product.")
        if lost_atoms or lost_blocks:
            print("Restore every missing item. Rewording is allowed; dropping a fact is not.")
        if moved:
            print("Put moved facts back under the thing they belong to. A price or")
            print("inclusion under the wrong tier misstates what the customer buys.")
        if hedges:
            print("Restore the qualifiers. 'Report on request' is not 'we are certified'.")
        return 1

    print("\nPASS - facts survived, stayed attached to the right thing, and kept their qualifiers")
    print("The script cannot read meaning: skim the tier-by-tier mapping yourself before shipping.")
    if lost_names:
        print("Advisory names above are not auto-failed, but confirm each removal was intended")
    return 0


if __name__ == "__main__":
    sys.exit(main())
