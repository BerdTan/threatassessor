#!/usr/bin/env python3
"""TAskillgym: deterministic checker for our own skills and headline docs.
Dimensions: correct, complete, coherent, clear, conclusive. No LLM, no network.
Exit 1 if any finding has severity 'error'. Never edits files."""
import re, sys, json, glob, os, collections
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[4]
SK = ROOT / ".claude/skills"
MEM = Path.home() / ".claude/projects/-mnt-c-BACKUP-DEV-TEST/memory/MEMORY.md"
F = []  # (severity, dimension, where, message)

def add(sev, dim, where, msg):
    item = (sev, dim, str(where), msg)
    if item not in F:
        F.append(item)

def truth():
    rules = yaml.safe_load((ROOT / "policies/soc_detection_rules.yaml").read_text())
    rules = rules.get("rules", rules) if isinstance(rules, dict) else rules
    tools = len(re.findall(r"@mcp\.tool", (ROOT / "mcp_server/server.py").read_text()))
    return {"rules": len(rules), "mcp_tools": tools}

def rd(p):
    try:
        return Path(p).read_text(errors="ignore")
    except OSError:
        return ""

CLAIMS = [
    ("rules", re.compile(r"\b(\d+)\s+(?:SOC\s+)?(?:DETECT\s+)?(?:SOC\s+DETECT\s+)?rules\b", re.I)),
    ("mcp_tools", re.compile(r"\b(\d+)\s+(?:MCP\s+)?tools\b", re.I)),
]

def check_counts(T):
    seen = collections.defaultdict(set)
    docs = [(ROOT / "CLAUDE.md", "error", None)]
    docs += [(p, "error", None) for p in SK.glob("*/SKILL.md")]
    if MEM.exists():
        m = rd(MEM)
        sec = m.split("## System state", 1)[-1].split("\n## ", 1)[0] if "## System state" in m else ""
        docs.append((MEM, "warn", sec))
    for p, sev, sect in docs:
        text = sect if sect is not None and sect != "" else rd(p)
        for line in text.splitlines():
            if re.search(r"\b(was|were|before|previously|→|->|from \d+ to|\d+→\d+)\b", line, re.I):
                continue  # historical or transition wording
            for key, rx in CLAIMS:
                if key == "mcp_tools" and "mcp" not in line.lower():
                    continue
                if key == "rules" and not re.search(r"detect|soc", line, re.I):
                    continue
                for m_ in rx.finditer(line):
                    if key == "rules" and re.search(r"DETECT-[A-Z]{2,4}\s*$", line[:m_.start()]):
                        continue  # domain-scoped count, not the total
                    n = int(m_.group(1))
                    seen[(key, n)].add(p.name if p.name != "SKILL.md" else p.parent.name)
                    if n != T[key]:
                        add(sev, "correct", p.relative_to(ROOT) if str(p).startswith(str(ROOT)) else p,
                            f"states {n} {key.replace('_',' ')}; repo has {T[key]}")
    # coherent: more than one distinct value for the same quantity across docs
    for key in T:
        vals = {n for (k, n) in seen if k == key}
        if len(vals) > 1:
            add("warn", "coherent", "docs", f"{key} stated as {sorted(vals)} across docs (repo: {T[key]})")

def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}

def check_skills():
    for d in sorted(p for p in SK.iterdir() if p.is_dir()):
        sm = d / "SKILL.md"
        names = os.listdir(d)
        if "SKILL.md" not in names and any(n.lower() == "skill.md" for n in names):
            add("error", "complete", d.relative_to(ROOT), "file is not named exactly SKILL.md (breaks on case-sensitive systems)")
            continue
        if not sm.exists():
            add("error", "complete", d.relative_to(ROOT), "skill directory has no SKILL.md")
            continue
        t = rd(sm)
        fm = frontmatter(t)
        if fm is None:
            add("error", "complete", sm.relative_to(ROOT), "no YAML frontmatter")
            continue
        if fm.get("name") not in (d.name,):
            add("warn", "coherent", sm.relative_to(ROOT), f"frontmatter name {fm.get('name')!r} != directory {d.name!r}")
        desc = str(fm.get("description") or "")
        if len(desc) < 40:
            add("warn", "clear", sm.relative_to(ROOT), f"description is {len(desc)} chars (<40); recall cannot route on it")
        if "## " not in t:
            add("warn", "clear", sm.relative_to(ROOT), "no section headings (no usage structure)")
        if not re.search(r"\bexit\b|\boutput\b|\breturns?\b|\bwrites?\b|\bverdict\b|\breports?\b|\bprints?\b", t, re.I):
            add("warn", "conclusive", sm.relative_to(ROOT), "states no output or exit contract")
        for ref in set(re.findall(r"(?<![\w/.-])((?:scripts/|\.claude/skills/)[\w./-]+\.(?:py|sh)(?![\w]))", t)):
            cand = [d / ref, ROOT / ref]
            if not any(c.exists() for c in cand):
                add("error", "complete", sm.relative_to(ROOT), f"references missing script {ref}")
        for ref in set(re.findall(r"`((?:chatbot|mcp_server|policies|scripts|tests)/[\w./-]+\.(?:py|yaml|sh))`", t)):
            if re.search(r"/[A-Z]\.py$", ref) or ref.startswith("scripts/") and (d / ref).exists():
                continue  # placeholder or skill-relative path
            if not (ROOT / ref).exists():
                add("warn", "correct", sm.relative_to(ROOT), f"references missing path {ref}")

def main():
    as_json = "--json" in sys.argv
    T = truth()
    check_counts(T)
    check_skills()
    n_skills = len([p for p in SK.iterdir() if p.is_dir()])
    by = collections.Counter((s, d) for s, d, *_ in F)
    if as_json:
        print(json.dumps({"truth": T, "skills": n_skills, "findings": F}, indent=1))
    else:
        print(f"TAskillgym  skills={n_skills}  repo: {T['rules']} rules, {T['mcp_tools']} MCP tools")
        for sev in ("error", "warn"):
            for s, d, w, m in F:
                if s == sev:
                    print(f"  {s:5} {d:10} {w}: {m}")
        print("summary:", dict(by) or "clean")
    sys.exit(1 if any(s == "error" for s, *_ in F) else 0)

if __name__ == "__main__":
    main()
