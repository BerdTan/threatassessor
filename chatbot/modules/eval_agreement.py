"""Agreement metrics for validating a labeller (heuristic, judge or table) against reviewed labels.

Pure functions, no I/O, no LLM. Follows the practice of reporting several measures together:
per-class recall and precision first (they carry the cost of a missed rare class), then Cohen's
kappa (chance-corrected agreement), Gwet's AC1 (less sensitive to skewed prevalence), and a
bootstrap interval so small samples show how little they prove. Kappa is a signal, not proof:
both raters can be wrong, and with a dominant class a high raw agreement can hide a miss.
"""
from __future__ import annotations

import random
from collections import Counter
from typing import Callable, Dict, List, Optional, Sequence, Tuple


def confusion(y_true: Sequence[str], y_pred: Sequence[str], labels: Sequence[str]) -> Dict[Tuple[str, str], int]:
    if len(y_true) != len(y_pred):
        raise ValueError("label sequences differ in length")
    c = Counter(zip(y_true, y_pred))
    return {(a, b): c.get((a, b), 0) for a in labels for b in labels}


def observed_agreement(y_true: Sequence[str], y_pred: Sequence[str]) -> float:
    n = len(y_true)
    return sum(a == b for a, b in zip(y_true, y_pred)) / n if n else float("nan")


def cohen_kappa(y_true: Sequence[str], y_pred: Sequence[str], labels: Optional[Sequence[str]] = None,
                weights: Optional[str] = None) -> float:
    """Cohen's kappa. weights=None (nominal), 'linear' or 'quadratic' (ordinal; labels must be ordered).

    Returns nan when chance agreement is total (e.g. both raters use one single label)."""
    n = len(y_true)
    if n == 0:
        return float("nan")
    labels = list(labels or sorted(set(y_true) | set(y_pred)))
    k = len(labels)
    idx = {l: i for i, l in enumerate(labels)}
    if weights not in (None, "linear", "quadratic"):
        raise ValueError("weights must be None, 'linear' or 'quadratic'")

    def w(i: int, j: int) -> float:  # disagreement weight
        if weights is None:
            return 0.0 if i == j else 1.0
        d = abs(i - j) / (k - 1) if k > 1 else 0.0
        return d if weights == "linear" else d * d

    obs = [[0.0] * k for _ in range(k)]
    for a, b in zip(y_true, y_pred):
        obs[idx[a]][idx[b]] += 1
    row = [sum(r) for r in obs]
    col = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    do = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k)) / n
    de = sum(w(i, j) * row[i] * col[j] for i in range(k) for j in range(k)) / (n * n)
    if de == 0:
        return float("nan")
    return 1.0 - do / de


def gwet_ac1(y_true: Sequence[str], y_pred: Sequence[str], labels: Optional[Sequence[str]] = None) -> float:
    """Gwet's AC1 for two raters. More stable than kappa when one class dominates."""
    n = len(y_true)
    if n == 0:
        return float("nan")
    labels = list(labels or sorted(set(y_true) | set(y_pred)))
    k = len(labels)
    if k < 2:
        return float("nan")
    pa = observed_agreement(y_true, y_pred)
    ct, cp = Counter(y_true), Counter(y_pred)
    pi = [((ct[l] + cp[l]) / (2 * n)) for l in labels]
    pe = sum(p * (1 - p) for p in pi) / (k - 1)
    return (pa - pe) / (1 - pe) if pe != 1 else float("nan")


def per_class(y_true: Sequence[str], y_pred: Sequence[str], labels: Optional[Sequence[str]] = None) -> Dict[str, Dict[str, float]]:
    """Precision, recall, F1 and support per class. 'true' = reviewed label, 'pred' = labeller."""
    labels = list(labels or sorted(set(y_true) | set(y_pred)))
    out = {}
    for l in labels:
        tp = sum(a == l and b == l for a, b in zip(y_true, y_pred))
        fp = sum(a != l and b == l for a, b in zip(y_true, y_pred))
        fn = sum(a == l and b != l for a, b in zip(y_true, y_pred))
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / (tp + fn) if tp + fn else float("nan")
        f1 = 2 * prec * rec / (prec + rec) if prec == prec and rec == rec and (prec + rec) else float("nan")
        out[l] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn, "predicted": tp + fp}
    return out


def bootstrap_ci(metric: Callable[[Sequence[str], Sequence[str]], float], y_true: Sequence[str],
                 y_pred: Sequence[str], n_boot: int = 2000, alpha: float = 0.05,
                 seed: int = 0) -> Tuple[float, float]:
    """Percentile bootstrap interval, resampling cases. NaN resamples are dropped."""
    rng = random.Random(seed)
    n = len(y_true)
    vals: List[float] = []
    for _ in range(n_boot):
        ix = [rng.randrange(n) for _ in range(n)]
        v = metric([y_true[i] for i in ix], [y_pred[i] for i in ix])
        if v == v:
            vals.append(v)
    if len(vals) < max(20, n_boot // 10):
        return (float("nan"), float("nan"))
    vals.sort()
    lo = vals[int((alpha / 2) * len(vals))]
    hi = vals[min(len(vals) - 1, int((1 - alpha / 2) * len(vals)))]
    return (lo, hi)


def agreement_report(y_true: Sequence[str], y_pred: Sequence[str], labels: Optional[Sequence[str]] = None,
                     n_boot: int = 2000, seed: int = 0) -> Dict:
    labels = list(labels or sorted(set(y_true) | set(y_pred)))
    return {
        "n": len(y_true),
        "observed_agreement": observed_agreement(y_true, y_pred),
        "kappa": cohen_kappa(y_true, y_pred, labels),
        "kappa_ci95": bootstrap_ci(lambda a, b: cohen_kappa(a, b, labels), y_true, y_pred, n_boot, seed=seed),
        "gwet_ac1": gwet_ac1(y_true, y_pred, labels),
        "per_class": per_class(y_true, y_pred, labels),
        "confusion": {f"{a}->{b}": v for (a, b), v in confusion(y_true, y_pred, labels).items() if v},
        "note": "kappa is a signal, not proof; read recall on the rare class first",
    }
