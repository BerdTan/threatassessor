#!/usr/bin/env python3
"""Validate TAwatch's ai_role keyword heuristic against human labels.

  make   write a BLIND label sheet (no heuristic output, no taxonomy tags) + a private key
  score  join the filled sheet with the key and report agreement

Sampling is stratified so rare-class errors are visible:
  target (all 11), guardrail_bypass (10 of 32), near-miss weapon (15: AI-system words but no
  target hit, the likely false negatives), random weapon (24). Stratum sizes are kept in the key
  so the population miss rate can be estimated. Output stays under report/ (gitignored).
"""
import argparse, csv, json, random, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from chatbot.modules.tawatch import IncidentAdapter  # noqa: E402
from chatbot.modules.eval_agreement import agreement_report, per_class  # noqa: E402

DATA = ROOT / "report/brain/tawatch_incidents.jsonl"
OUT = ROOT / "report/brain/ailabel"
LABELS = ["weapon", "guardrail_bypass", "target"]
NEAR = re.compile(r"\b(agent\w*|mcp|plugin|skill|extension|copilot|assistant|prompt\w*|"
                  r"repositor\w+|package|npm|pypi|supply.chain|workflow|pipeline|llm)\b", re.I)
PLAN = {"target": 11, "guardrail_bypass": 10, "weapon_near": 15, "weapon_rand": 24}

GUIDE = """LABELLING GUIDE (first-read judgement, do not look anything up, do not guess what a program would say)

For each incident choose ONE label in the human_label column:

  weapon            the attacker used an AI tool to do the harm (scam text, malware, influence ops,
                    recon, fraud). The AI is a tool; no AI system was itself attacked.
  guardrail_bypass  the attacker had to jailbreak or evade a model's safety controls to get that
                    AI tool to do it. (Still AI-as-tool, but the safety bypass is the notable part.)
  target            an AI system, agent, model, MCP server, skill, rules file or AI-assisted
                    pipeline was itself attacked, hijacked, poisoned, lured or manipulated, or was
                    the entry point (prompt injection, tool poisoning, malicious skill, model theft).
  unsure            genuinely cannot tell from the text. Use sparingly; unsure cases are excluded.

If both weapon and target seem true, ask: did someone subvert an AI system's behaviour to cause
the harm? If yes, target. Use the notes column for anything you want to flag.
"""


def load():
    rows = [json.loads(l) for l in DATA.read_text().splitlines() if l.strip()]
    ad = IncidentAdapter()
    for r in rows:
        r["_role"] = ad.ai_role(r)
        r["_text"] = f"{r.get('headline','')} {r.get('description','')}"
    return rows


def make(seed):
    rows = load()
    rng = random.Random(seed)
    tgt = [r for r in rows if r["_role"] == "target"]
    byp = [r for r in rows if r["_role"] == "guardrail_bypass"]
    wk = [r for r in rows if r["_role"] == "weapon"]
    near = [r for r in wk if NEAR.search(r["_text"])]
    near_ids = {r["id"] for r in near}
    rand = [r for r in wk if r["id"] not in near_ids]
    strata = {"target": tgt, "guardrail_bypass": byp, "weapon_near": near, "weapon_rand": rand}
    pick = []
    for name, pop in strata.items():
        k = min(PLAN[name], len(pop))
        pick += [(name, r) for r in rng.sample(pop, k)]
    rng.shuffle(pick)
    OUT.mkdir(parents=True, exist_ok=True)
    key = {"seed": seed, "strata_population": {k: len(v) for k, v in strata.items()},
           "strata_sampled": {k: min(PLAN[k], len(v)) for k, v in strata.items()}, "rows": {}}
    with open(OUT / "sheet.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "headline", "description", "impact", "human_label", "notes"])
        for i, (name, r) in enumerate(pick, 1):
            cid = f"S{i:03d}"
            key["rows"][cid] = {"id": r["id"], "stratum": name, "heuristic": r["_role"]}
            w.writerow([cid, r.get("headline", ""), r.get("description", ""), r.get("impact", ""), "", ""])
    (OUT / "key.json").write_text(json.dumps(key, indent=1))
    (OUT / "GUIDE.txt").write_text(GUIDE)
    print(f"wrote {len(pick)} cases to {OUT}/sheet.csv (blind). Key kept in key.json: do not open it before labelling.")
    print("population:", key["strata_population"], "sampled:", key["strata_sampled"])


def score(args):
    key = json.loads((OUT / "key.json").read_text())
    got = {}
    with open(args.sheet or OUT / "sheet.csv") as f:
        for r in csv.DictReader(f):
            got[r["case"]] = (r["human_label"] or "").strip().lower()
    bad = {c: v for c, v in got.items() if v and v not in LABELS + ["unsure"]}
    if bad:
        sys.exit(f"invalid labels: {bad}")
    blank = [c for c, v in got.items() if not v]
    if blank:
        sys.exit(f"{len(blank)} cases unlabelled (e.g. {blank[:5]})")
    unsure = [c for c, v in got.items() if v == "unsure"]
    cases = [(c, got[c], key["rows"][c]) for c in got if got[c] != "unsure"]
    human = [h for _, h, _ in cases]
    pred = [m["heuristic"] for _, _, m in cases]
    rep = agreement_report(human, pred, LABELS, n_boot=2000, seed=0)
    print(f"cases scored: {len(cases)}  unsure excluded: {len(unsure)}")
    print("NOTE: sample is stratified, so raw kappa below is NOT a population estimate.\n")
    print(f"raw agreement {rep['observed_agreement']:.2f}  kappa {rep['kappa']:.2f} "
          f"(95% CI {rep['kappa_ci95'][0]:.2f} to {rep['kappa_ci95'][1]:.2f})  AC1 {rep['gwet_ac1']:.2f}")
    for l, m in rep["per_class"].items():
        print(f"  {l:17} precision {m['precision']:.2f}  recall {m['recall']:.2f}  support {m['support']}  predicted {m['predicted']}")
    print("confusion (human->heuristic):", rep["confusion"])
    # population estimate for the rare class
    N, n = key["strata_population"], key["strata_sampled"]
    by = {s: [h for _, h, m in cases if m["stratum"] == s] for s in N}
    tp = sum(h == "target" for h in by["target"])
    prec = tp / len(by["target"]) if by["target"] else float("nan")

    def est_fn(samples):
        fn = 0.0
        for s in ("guardrail_bypass", "weapon_near", "weapon_rand"):
            xs = samples[s]
            if xs:
                fn += sum(h == "target" for h in xs) / len(xs) * N[s]
        return fn

    def recall_from(samples):
        t = sum(h == "target" for h in samples["target"])
        fn = est_fn(samples)
        return t / (t + fn) if (t + fn) else float("nan")

    rng = random.Random(1)
    boots = []
    for _ in range(2000):
        s = {k: [rng.choice(v) for _ in v] if v else [] for k, v in by.items()}
        r = recall_from(s)
        if r == r:
            boots.append(r)
    boots.sort()
    lo, hi = (boots[int(.025 * len(boots))], boots[int(.975 * len(boots))]) if boots else (float("nan"),) * 2
    print(f"\nPOPULATION ESTIMATE for class 'target' (stratum-weighted):")
    print(f"  heuristic precision on its 11 target calls: {prec:.2f}")
    print(f"  estimated true targets the heuristic labels non-target: {est_fn(by):.1f} of {sum(N.values()) - N['target']}")
    print(f"  estimated recall: {recall_from(by):.2f} (95% CI {lo:.2f} to {hi:.2f})")
    print("\nRead disagreements case by case before changing the heuristic; change one thing, re-test on a FRESH sample.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make"); m.add_argument("--seed", type=int, default=42)
    s = sub.add_parser("score"); s.add_argument("--sheet")
    a = ap.parse_args()
    make(a.seed) if a.cmd == "make" else score(a)
