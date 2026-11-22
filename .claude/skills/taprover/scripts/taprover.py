#!/usr/bin/env python3
"""TAprover — independent threat-model claim verifier (Entry 249, P50).

Slice 1+: technique_grounding + tactic_correctness across the three spec domains:
Enterprise (STIX), ICS (STIX), ATLAS (YAML). Domain is chosen from the ID shape.
Slice 2 (logic checks): agentic_trigger_parity, coverage, mitigation_validity, and --aggregate
(pass@k / pass^k over repeated runs of the same architecture). All deterministic.

Independence invariant: this file imports NOTHING from chatbot/ or agentic/. It sees only
the TM JSON and the STIX bundle. Deterministic: no LLM, no network.
Verdicts: VERIFIED / UNVERIFIABLE / REFUTED per claim. Exit 1 if any REFUTED.
"""
import argparse, hashlib, json, re, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "taprover/0.1"
DEFAULT_STIX = "chatbot/data/enterprise-attack.json"
DEFAULT_ICS = "chatbot/data/ics-attack.json"
DEFAULT_ATLAS = "chatbot/data/atlas"
TECH_ID = re.compile(r"^T\d{4}(\.\d{3})?$")
ATLAS_ID = re.compile(r"^AML\.T\d{4}(\.\d{3})?$")
MIT_ID = re.compile(r"^M\d{4}(\.\d{3})?$")
AGENTIC_TYPES = {"ai_system", "agentic", "agentic_system", "ai_agent"}  # ta-export architecture.type values meaning AI/agentic
# ATLAS v5.6 renamed "ML ..." tactics to "AI ..."; accept the old names as the same tactic.
ATLAS_TACTIC_ALIASES = {"ml-attack-staging": "ai-attack-staging", "ml-model-access": "ai-model-access"}
TACTICS = {
    "reconnaissance", "resource-development", "initial-access", "execution", "persistence",
    "privilege-escalation", "defense-evasion", "credential-access", "discovery",
    "lateral-movement", "collection", "command-and-control", "exfiltration", "impact",
}


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_stix(stix_path, domain="enterprise", kill_chain="mitre-attack"):
    """external_id -> {name, tactics, deprecated, revoked, domain}"""
    d = json.load(open(stix_path))
    objs = d["objects"] if isinstance(d, dict) else d
    by_id = {o["id"]: o for o in objs if o.get("type") == "attack-pattern"}
    ext_of = lambda o: next((r["external_id"] for r in o.get("external_references", [])
                             if TECH_ID.match(r.get("external_id", ""))), None)
    replaced_by = {}
    for o in objs:  # ATT&CK renumbers/merges techniques (e.g. ICS T0855 -> T1692.001); keep the pointer for evidence
        if o.get("type") == "relationship" and o.get("relationship_type") == "revoked-by":
            src, dst = by_id.get(o["source_ref"]), by_id.get(o["target_ref"])
            if src and dst and ext_of(src) and ext_of(dst):
                replaced_by[ext_of(src)] = ext_of(dst)
    cat = {}
    for o in objs:
        if o.get("type") != "attack-pattern":
            continue
        # source_name is inconsistent across MITRE bundles (ICS mixes 'mitre-attack' and 'mitre-ics-attack'): match by ID shape
        ext = next((r["external_id"] for r in o.get("external_references", [])
                    if TECH_ID.match(r.get("external_id", ""))), None)
        if not ext:
            continue
        cat[ext] = {
            "name": o.get("name", ""),
            "tactics": {p["phase_name"] for p in o.get("kill_chain_phases", [])
                        if p.get("kill_chain_name") == kill_chain},
            "deprecated": bool(o.get("x_mitre_deprecated")),
            "revoked": bool(o.get("revoked")),
            "domain": domain,
            "replaced_by": replaced_by.get(ext),
        }
    return cat


def load_catalog(stix_path):  # Enterprise; kept for callers/tests
    return load_stix(stix_path, "enterprise", "mitre-attack")


def load_mitigations(*paths):
    """MITRE mitigation ID (M1xxx / M08xx) -> {name, deprecated, revoked} from course-of-action objects."""
    out = {}
    for path in paths:
        if not path or not Path(path).exists():
            continue
        d = json.load(open(path))
        for o in (d["objects"] if isinstance(d, dict) else d):
            if o.get("type") != "course-of-action":
                continue
            ext = next((r["external_id"] for r in o.get("external_references", []) if MIT_ID.match(r.get("external_id", ""))), None)
            if ext:
                out[ext] = {"name": o.get("name", ""), "deprecated": bool(o.get("x_mitre_deprecated")), "revoked": bool(o.get("revoked"))}
    return out


def load_ics(path):
    return load_stix(path, "ics", "mitre-ics-attack")


def load_atlas(atlas_dir):
    """ATLAS YAML. Tactics/parents are '{{anchor.id}}' templates; resolve anchors from the raw text."""
    import yaml  # local import: only needed when ATLAS is loaded
    d = Path(atlas_dir)
    raw_t, raw_q = (d / "tactics.yaml").read_text(), (d / "techniques.yaml").read_text()
    tac_anchor = dict(re.findall(r"^- &(\w+)\s*\n\s*id:\s*(AML\.TA\d+)", raw_t, re.M))
    tech_anchor = dict(re.findall(r"^- &(\w+)\s*\n\s*id:\s*(AML\.T[\d.]+)", raw_q, re.M))
    tac_name = {t["id"]: t["name"] for t in yaml.safe_load(raw_t)}
    techs = yaml.safe_load(raw_q)
    ref = lambda v, amap: amap.get((re.fullmatch(r"\{\{(\w+)\.id\}\}", str(v)) or [None, None])[1])
    own = {}
    for t in techs:
        own[t["id"]] = {_norm_tactic(tac_name[i]) for i in (ref(x, tac_anchor) for x in t.get("tactics", [])) if i in tac_name}
    cat = {}
    for t in techs:
        tactics = own[t["id"]]
        if not tactics and "subtechnique-of" in t:
            tactics = own.get(ref(t["subtechnique-of"], tech_anchor), set())
        cat[t["id"]] = {"name": t["name"], "tactics": set(tactics), "deprecated": bool(t.get("deprecated")),
                        "revoked": bool(t.get("revoked")), "domain": "atlas"}
    return cat


def valid_tactics(cat):
    """domain -> set of tactic names that appear in that domain's catalog (Enterprise also has the fixed 14)."""
    out = {"enterprise": set(TACTICS)}
    for e in cat.values():
        out.setdefault(e.get("domain", "enterprise"), set()).update(e["tactics"])
    return out


def _norm_name(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _norm_tactic(s):
    t = re.sub(r"[\s_]+", "-", (s or "").strip().lower())
    return ATLAS_TACTIC_ALIASES.get(t, t)


def extract_claims(tm):
    """Return (meta, [claim dicts]) from threatmodel/0.1 or ta-export/1.0. Only stated facts are claims.
    meta also carries what the logic checks need: agentic flag, per-path technique lists, summary list, mitigations."""
    claims, meta = [], {}
    if isinstance(tm.get("assessment"), dict):  # ta-export/1.0
        a = tm["assessment"]
        ab = tm.get("architecture") if isinstance(tm.get("architecture"), dict) else {}
        meta = {"format": tm.get("schema", "ta-export"), "arch": ab.get("name") or a.get("architecture") or tm.get("architecture"),
                "routing_mode": (tm.get("routing") or {}).get("mode"),
                "agentic": ab.get("is_agentic") is True or ab.get("type") in AGENTIC_TYPES, "paths": {}, "mitigations": None}
        for ap in a.get("attack_paths", []):
            pid = ap.get("id", "?")
            names = ap.get("technique_names") or []
            meta["paths"][pid] = [t for t in ap.get("techniques", []) if isinstance(t, str)]
            for i, t in enumerate(ap.get("techniques", [])):
                claims.append({"path": pid, "technique_id": t,
                               "technique_name": names[i] if i < len(names) else None, "tactic": None})
        summary = [t for t in (a.get("mitre_techniques") or []) if isinstance(t, str)]
        meta["summary"] = summary
        seen = {c["technique_id"] for c in claims}
        for t in summary:  # architecture-level list: includes ATLAS, which per-path lists may omit; it is a claim too
            if t not in seen:
                claims.append({"path": "ARCH", "technique_id": t, "technique_name": None, "tactic": None})
                seen.add(t)
        mm = [{"control_id": m, "addresses": []} for x in (tm.get("otm") or {}).get("mitigations", []) for m in x.get("mitre_mitigations", [])]
        meta["mitigations"] = mm or None
    else:  # threatmodel/0.1
        summ = tm.get("architecture_summary") if isinstance(tm.get("architecture_summary"), dict) else {}
        gov = tm.get("governance") if isinstance(tm.get("governance"), dict) else {}
        meta = {"format": "threatmodel/" + str(tm.get("spec_version", "?")), "arch": tm.get("architecture_id"),
                "model_id": tm.get("produced_by"), "summary": None, "paths": {},
                "agentic": summ.get("is_agentic") is True or isinstance(gov.get("agentic"), dict)}
        for ap in tm.get("attack_paths", []):
            pid = ap.get("path_id", "?")
            if isinstance(ap.get("technique_id"), str) and ap["technique_id"].strip():
                meta["paths"].setdefault(pid, []).append(ap["technique_id"])
            else:
                meta["paths"].setdefault(pid, [])
            claims.append({"path": pid, "technique_id": ap.get("technique_id"),
                           "technique_name": ap.get("technique_name"), "tactic": ap.get("tactic")})
        ms = tm.get("mitigations")
        meta["mitigations"] = [{"control_id": m.get("control_id"), "addresses": [x for x in ([m["addresses_technique"]] if isinstance(m.get("addresses_technique"), str) else (m.get("addresses_technique") or [])) if isinstance(x, str)]}
                               for m in ms if isinstance(m, dict)] if isinstance(ms, list) and ms else None
    return meta, claims


def _v(category, claim, verdict, evidence, reason):
    return {"category": category, "path": claim["path"], "technique_id": claim["technique_id"],
            "verdict": verdict, "reason": reason, "evidence": evidence}


def _domain(tid):
    if ATLAS_ID.match(tid):
        return "atlas"
    return "enterprise" if TECH_ID.match(tid) else None


def check_technique_grounding(c, cat, lenient=False, loaded=None):
    tid, cg = c["technique_id"], "technique_grounding"
    if not isinstance(tid, str) or not tid.strip():
        # No claim was made. An unmade claim cannot be false; tmbench-check scores the absence.
        return _v(cg, c, "UNVERIFIABLE", "no technique_id stated; nothing to prove", "no_claim")
    dom = _domain(tid)  # ID-shape hint only: ATT&CK is merging ICS into T1xxx, so shape cannot pick the catalog
    if dom is None:
        return _v(cg, c, "REFUTED", f"'{tid}' is not a well-formed Enterprise/ICS/ATLAS technique ID", "malformed_id")
    if loaded is None:
        loaded = {e.get("domain", "enterprise") for e in cat.values()}
    e = cat.get(tid)
    if e is None:
        need = {"atlas"} if dom == "atlas" else {"enterprise", "ics"}  # a bare T-ID may live in either STIX catalog
        if need - loaded:
            return _v(cg, c, "UNVERIFIABLE", f"{', '.join(sorted(need - loaded))} catalog not loaded; cannot check {tid}", "catalog_not_loaded")
        where = "ATLAS" if dom == "atlas" else "Enterprise or ICS"
        if lenient:
            return _v(cg, c, "UNVERIFIABLE", f"{tid} not in the {where} catalog (--lenient)", "not_in_catalog")
        return _v(cg, c, "REFUTED", f"{tid} does not exist in the {where} catalog", "not_in_catalog")
    if e["revoked"] or e["deprecated"]:
        rb = f"; replaced by {e['replaced_by']}" if e.get("replaced_by") else ""
        return _v(cg, c, "REFUTED", f"{tid} is {'revoked' if e['revoked'] else 'deprecated'} in {e.get('domain', 'enterprise')}{rb}", "deprecated")
    if c.get("technique_name") and _norm_name(c["technique_name"]) != _norm_name(e["name"]):
        return _v(cg, c, "REFUTED", f"{tid} is '{e['name']}', claim says '{c['technique_name']}'", "name_mismatch")
    return _v(cg, c, "VERIFIED", f"{tid} = '{e['name']}' ({dom})", "ok")


def check_tactic_correctness(c, cat, vt=None):
    if not c.get("tactic"):
        return None  # no stated tactic -> no claim
    tid, tac, tc = c["technique_id"], _norm_tactic(c["tactic"]), "tactic_correctness"
    e = cat.get(tid) if isinstance(tid, str) else None
    if e is None:
        if not tid:
            return _v(tc, c, "UNVERIFIABLE", "no technique_id stated; cannot check tactic", "no_claim")
        return _v(tc, c, "UNVERIFIABLE", f"{tid} not in catalog; cannot check tactic", "not_in_catalog")
    dom = e.get("domain", "enterprise")
    vt = vt or valid_tactics(cat)
    if tac not in vt.get(dom, set()):
        return _v(tc, c, "REFUTED", f"'{c['tactic']}' is not a {dom} tactic", "not_a_tactic")
    if tac in e["tactics"]:
        return _v(tc, c, "VERIFIED", f"{tid} lists tactic {tac}", "ok")
    return _v(tc, c, "REFUTED", f"{tid} tactics are {sorted(e['tactics'])}, claim says {tac}", "wrong_tactic")


def _arch(category, verdict, evidence, reason):
    return {"category": category, "path": "ARCH", "technique_id": None, "verdict": verdict, "reason": reason, "evidence": evidence}


def check_agentic_parity(meta, results):
    """An architecture that declares itself agentic/AI must cite at least one verifiable ATLAS technique (spec 1.3)."""
    if not meta.get("agentic"):
        return None
    atlas = [r for r in results if r["category"] == "technique_grounding" and r["technique_id"] and ATLAS_ID.match(str(r["technique_id"]))]
    if any(r["verdict"] == "VERIFIED" for r in atlas):
        return _arch("agentic_trigger_parity", "VERIFIED", f"{sum(r['verdict'] == 'VERIFIED' for r in atlas)} ATLAS technique(s) verified for an agentic architecture", "ok")
    if atlas and all(r["verdict"] == "UNVERIFIABLE" for r in atlas):
        return _arch("agentic_trigger_parity", "UNVERIFIABLE", "ATLAS techniques are cited but could not be checked", "atlas_unverifiable")
    return _arch("agentic_trigger_parity", "REFUTED", "architecture is declared agentic/AI but no verified ATLAS technique is cited", "agentic_no_atlas")


def check_coverage(meta):
    """Every attack path cites a technique, and every path technique appears in the architecture-level list."""
    paths = meta.get("paths") or {}
    if not paths:
        return None
    empty = sorted(p for p, t in paths.items() if not t)
    summ = meta.get("summary")
    stray = sorted({t for ts in paths.values() for t in ts} - set(summ)) if summ else []
    if stray:
        return _arch("coverage", "REFUTED", f"path technique(s) missing from the architecture-level list: {stray[:5]}", "not_in_summary")
    if empty:
        return _arch("coverage", "UNVERIFIABLE", f"{len(empty)} path(s) cite no technique: {empty[:5]}", "empty_path")
    return _arch("coverage", "VERIFIED", f"{len(paths)} path(s) each cite a technique", "ok")


def check_mitigations(meta, model_ids, mit):
    """Cited MITRE mitigation IDs exist and are current; addressed techniques are in the model; paths are covered."""
    ms = meta.get("mitigations")
    if not ms:
        return []
    out, addressed = [], set()
    for m in ms:
        cid, addr = m.get("control_id"), m.get("addresses") or []
        addressed.update(addr)
        claim = {"path": "ARCH", "technique_id": cid}
        stray = sorted(set(addr) - model_ids)
        if stray:
            out.append(_v("mitigation_validity", claim, "REFUTED", f"mitigation {cid} addresses technique(s) not in the model: {stray[:5]}", "addresses_unknown_technique"))
        elif not isinstance(cid, str) or not MIT_ID.match(cid):
            out.append(_v("mitigation_validity", claim, "UNVERIFIABLE", f"control '{cid}' is not a MITRE mitigation ID; framework not checked here", "external_framework"))
        elif mit is None:
            out.append(_v("mitigation_validity", claim, "UNVERIFIABLE", "mitigation catalog not loaded", "catalog_not_loaded"))
        elif cid not in mit:
            out.append(_v("mitigation_validity", claim, "REFUTED", f"{cid} is not a MITRE mitigation", "unknown_mitigation"))
        elif mit[cid]["deprecated"] or mit[cid]["revoked"]:
            out.append(_v("mitigation_validity", claim, "REFUTED", f"{cid} is revoked or deprecated", "deprecated"))
        else:
            out.append(_v("mitigation_validity", claim, "VERIFIED", f"{cid} = '{mit[cid]['name']}'", "ok"))
    if addressed:  # only meaningful when mitigations say what they address
        gap = sorted({t for ts in (meta.get("paths") or {}).values() for t in ts} - addressed)
        out.append(_arch("mitigation_coverage", "UNVERIFIABLE" if gap else "VERIFIED",
                         f"{len(gap)} path technique(s) have no mitigation addressing them: {gap[:5]}" if gap else "every path technique is addressed by a mitigation",
                         "path_unmitigated" if gap else "ok"))
    return out


def prove(tm, cat, stix_sha=None, src_sha=None, lenient=False, run_id=None, loaded=None, mitigations=None):
    meta, claims = extract_claims(tm)
    loaded = loaded if loaded is not None else {e.get("domain", "enterprise") for e in cat.values()}
    vt = valid_tactics(cat)
    results = []
    for c in claims:
        results.append(check_technique_grounding(c, cat, lenient, loaded))
        t = check_tactic_correctness(c, cat, vt)
        if t:
            results.append(t)
    for extra in (check_agentic_parity(meta, results), check_coverage(meta)):
        if extra:
            results.append(extra)
    results += check_mitigations(meta, {c["technique_id"] for c in claims if c["technique_id"]}, mitigations)
    counts = {k: sum(r["verdict"] == k for r in results) for k in ("VERIFIED", "UNVERIFIABLE", "REFUTED")}
    if not results:  # nothing proven is not the same as proven
        overall = "UNVERIFIABLE"
    else:
        overall = "REFUTED" if counts["REFUTED"] else ("UNVERIFIABLE" if counts["UNVERIFIABLE"] else "VERIFIED")
    return {"schema": SCHEMA, "run_id": run_id or str(uuid.uuid4()),
            "proved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "arch": meta.get("arch"), "model_id": meta.get("model_id"), "routing_mode": meta.get("routing_mode"),
            "input_format": meta.get("format"), "input_sha256": src_sha, "evidence_sha256": stix_sha, "domains_loaded": sorted(loaded),
            "lenient": lenient, "overall": overall, "counts": counts, "claims": results}


def mark_drift(att, base_att):
    """Label REFUTED claims that the pinned (baseline) catalog accepts as catalog drift, not model error.
    Overall becomes DRIFT when every refutation is drift; real refutations keep it REFUTED."""
    key = lambda r: (r["path"], r["category"])
    base = {key(r): r for r in base_att["claims"]}
    for r in att["claims"]:
        b = base.get(key(r))
        r["drift"] = bool(r["verdict"] == "REFUTED" and b and b["verdict"] != "REFUTED")
    d = sum(r["drift"] for r in att["claims"])
    att["counts"]["DRIFT"] = d
    att["counts"]["REFUTED"] -= d
    att["baseline"] = base_att["evidence_sha256"]
    if att["overall"] == "REFUTED" and att["counts"]["REFUTED"] == 0:
        att["overall"] = "DRIFT"
    return att


def aggregate(atts):
    """pass@k / pass^k per architecture over repeated runs. A run passes when it has no REFUTED claim (DRIFT is not a failure).
    pass@k: at least one of k runs passes. pass^k: all k runs pass. Use pass^k for CI gates and public claims."""
    by = {}
    for a in atts:
        by.setdefault(a.get("arch") or "?", []).append(a["overall"] != "REFUTED")
    rows = {k: {"k": len(v), "passes": sum(v), "pass_at_k": any(v), "pass_pow_k": all(v)} for k, v in by.items()}
    n = len(rows) or 1
    return {"archs": rows, "pass_at_k_rate": round(sum(r["pass_at_k"] for r in rows.values()) / n, 3),
            "pass_pow_k_rate": round(sum(r["pass_pow_k"] for r in rows.values()) / n, 3)}


def _load_inputs(args):
    paths = []
    if args.prove:
        paths.append(Path(args.prove))
    if args.prove_dir:
        paths += sorted(Path(args.prove_dir).glob("*.json"))
    return paths


# --- Doc claims (Blog P44 principle 9): a document's claim about pipeline stage order ---
DOC_CLAIM = re.compile(r"before any LLM", re.I)
DOC_SUBJECT = re.compile(r"bouncer|governance gate", re.I)


def extract_doc_claims(text):
    """Lines that say the Bouncer/governance gate acts 'before any LLM ...' (subject within 2 lines above)."""
    lines, out = text.splitlines(), []
    for i, line in enumerate(lines):
        if DOC_CLAIM.search(line) and DOC_SUBJECT.search(" ".join(lines[max(0, i - 2): i + 1])):
            out.append({"line": i + 1, "text": line.strip()[:120]})
    return out


def prove_docs(manifest, docs, manifest_sha=""):
    """Check stage-order claims in docs {path: text} against a stage-manifest/0.1 dict.

    'Before any LLM' holds only if no stage runs ahead of the Bouncer. Limit: every stage
    before the Bouncer is treated as able to spend (AnalysisStage can call a model).
    """
    scen = (manifest or {}).get("scenarios") or {}
    late = {}
    for name, stages in scen.items():
        if "bouncer" in stages and stages.index("bouncer") > 0:
            late[name] = "after " + ", ".join(stages[: stages.index("bouncer")])
    has_bouncer = any("bouncer" in v for v in scen.values())
    claims = []
    for path, text in sorted(docs.items()):
        for c in extract_doc_claims(text):
            if not has_bouncer:
                verdict, reason, ev = "UNVERIFIABLE", "no_bouncer_in_manifest", "manifest lists no scenario with a bouncer"
            elif late:
                verdict, reason, ev = "REFUTED", "stage_runs_before_bouncer", "; ".join(f"{k}: bouncer {v}" for k, v in late.items())
            else:
                verdict, reason, ev = "VERIFIED", "bouncer_first", "bouncer is the first stage in every scenario that has one"
            claims.append({"category": "doc_stage_order", "source": path, "line": c["line"], "claim": c["text"],
                           "verdict": verdict, "reason": reason, "evidence": ev})
    counts = {v: sum(c["verdict"] == v for c in claims) for v in ("VERIFIED", "UNVERIFIABLE", "REFUTED")}
    overall = "REFUTED" if counts["REFUTED"] else ("UNVERIFIABLE" if counts["UNVERIFIABLE"] else "VERIFIED")
    return {"schema": SCHEMA, "kind": "doc_claims", "manifest_sha256": manifest_sha, "overall": overall,
            "checked": len(claims), "counts": counts, "claims": claims}



def main(argv=None):
    ap = argparse.ArgumentParser(description="TAprover — independent TM claim verifier")
    ap.add_argument("--prove", help="TM JSON (threatmodel/0.1 or ta-export/1.0)")
    ap.add_argument("--prove-dir", help="directory of TM JSON files")
    ap.add_argument("--stix", default=DEFAULT_STIX, help="Enterprise STIX bundle")
    ap.add_argument("--ics", default=DEFAULT_ICS, help="ICS STIX bundle (optional; ICS IDs UNVERIFIABLE if absent)")
    ap.add_argument("--atlas", default=DEFAULT_ATLAS, help="ATLAS YAML dir (optional; ATLAS IDs UNVERIFIABLE if absent)")
    ap.add_argument("--baseline-stix", help="pinned Enterprise bundle; REFUTED claims it accepts are labelled DRIFT, not REFUTED")
    ap.add_argument("--baseline-ics", default=DEFAULT_ICS, help="pinned ICS bundle for --baseline-stix")
    ap.add_argument("--lenient", action="store_true", help="treat IDs absent from the Enterprise catalog as UNVERIFIABLE instead of REFUTED")
    ap.add_argument("--summary", action="store_true", help="one line per input")
    ap.add_argument("--refuted-only", action="store_true", help="show only REFUTED claims")
    ap.add_argument("--aggregate", action="store_true", help="group attestations by architecture and report pass@k / pass^k over the runs")
    ap.add_argument("--out", help="write attestation(s) JSON here")
    ap.add_argument("--prove-docs", metavar="MANIFEST", help="stage-manifest JSON; check stage-order claims in --docs files against it")
    ap.add_argument("--docs", nargs="+", help="documents or code files to scan for stage-order claims (with --prove-docs)")
    args = ap.parse_args(argv)
    if args.prove_docs:
        if not args.docs:
            ap.error("--prove-docs needs --docs")
        att = prove_docs(json.load(open(args.prove_docs)), {d: Path(d).read_text() for d in args.docs if Path(d).is_file()}, _sha(args.prove_docs))
        for c in att["claims"]:
            print(f"[{c['verdict']:<12}] {c['source']}:{c['line']} ({c['reason']}): {c['evidence']}\n               {c['claim']}")
        print(f"docs: {att['overall']}  checked={att['checked']} {att['counts']}")
        if args.out:
            Path(args.out).write_text(json.dumps(att, indent=2))
        return 1 if att["overall"] == "REFUTED" else 0
    paths = _load_inputs(args)
    if not paths:
        ap.error("give --prove or --prove-dir")
    cat = load_catalog(args.stix)
    shas = {"enterprise": _sha(args.stix)}
    if Path(args.ics).exists():
        cat.update(load_ics(args.ics)); shas["ics"] = _sha(args.ics)
    else:
        print(f"warning: ICS catalog not found at {args.ics}; ICS IDs will be UNVERIFIABLE", file=sys.stderr)
    if (Path(args.atlas) / "techniques.yaml").exists():
        try:
            cat.update(load_atlas(args.atlas)); shas["atlas"] = _sha(Path(args.atlas) / "techniques.yaml")
        except Exception as e:
            print(f"warning: ATLAS load failed ({e}); ATLAS IDs will be UNVERIFIABLE", file=sys.stderr)
    else:
        print(f"warning: ATLAS catalog not found at {args.atlas}; ATLAS IDs will be UNVERIFIABLE", file=sys.stderr)
    stix_sha = shas
    mit = load_mitigations(args.stix, args.ics)
    bcat = bshas = None
    if args.baseline_stix:
        bcat = load_catalog(args.baseline_stix); bshas = {"enterprise": _sha(args.baseline_stix)}
        if Path(args.baseline_ics).exists():
            bcat.update(load_ics(args.baseline_ics)); bshas["ics"] = _sha(args.baseline_ics)
        bcat.update({k: v for k, v in cat.items() if v.get("domain") == "atlas"})  # ATLAS is not versioned here
    atts, any_refuted = [], False
    for p in paths:
        try:
            tm = json.load(open(p))
            att = prove(tm, cat, stix_sha, _sha(p), args.lenient, mitigations=mit or None)
        except Exception as e:  # unreadable input is a failure, not a pass
            print(f"{p.name}: ERROR {e}", file=sys.stderr)
            any_refuted = True
            continue
        if bcat is not None:
            att = mark_drift(att, prove(tm, bcat, bshas, _sha(p), args.lenient, mitigations=load_mitigations(args.baseline_stix, args.baseline_ics) or None))
        att["source"] = str(p)
        atts.append(att)
        any_refuted |= att["overall"] == "REFUTED"
        c = att["counts"]
        print(f"{p.name}: {att['overall']}  verified={c['VERIFIED']} unverifiable={c['UNVERIFIABLE']} refuted={c['REFUTED']}" + (f" drift={c['DRIFT']}" if "DRIFT" in c else ""))
        if not args.summary:
            for r in att["claims"]:
                if args.refuted_only and r["verdict"] != "REFUTED":
                    continue
                print(f"  [{'DRIFT' if r.get('drift') else r['verdict']:<12}] {r['path']} {r['technique_id']} {r['category']} ({r['reason']}): {r['evidence']}")
    agg = aggregate(atts) if args.aggregate else None
    if agg:
        for k, r in sorted(agg["archs"].items()):
            print(f"aggregate {k}: k={r['k']} passes={r['passes']} pass@k={r['pass_at_k']} pass^k={r['pass_pow_k']}")
        print(f"aggregate: pass@k={agg['pass_at_k_rate']} pass^k={agg['pass_pow_k_rate']} over {len(agg['archs'])} architecture(s)")
    if args.out:
        body = {"attestations": atts, "aggregate": agg} if agg else (atts[0] if len(atts) == 1 else atts)
        Path(args.out).write_text(json.dumps(body, indent=2))
    return 1 if any_refuted else 0


if __name__ == "__main__":
    sys.exit(main())
