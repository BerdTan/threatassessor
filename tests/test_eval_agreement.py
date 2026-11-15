import math
from chatbot.modules.eval_agreement import (
    cohen_kappa, gwet_ac1, per_class, bootstrap_ci, agreement_report, observed_agreement)


def test_high_agreement_can_hide_missed_failure():
    # Course example: reviewer 9 SAFE + 1 UNSAFE, judge says SAFE for all ten.
    t = ["SAFE"] * 9 + ["UNSAFE"]
    p = ["SAFE"] * 10
    assert observed_agreement(t, p) == 0.9
    assert cohen_kappa(t, p, ["SAFE", "UNSAFE"]) == 0.0
    assert per_class(t, p, ["SAFE", "UNSAFE"])["UNSAFE"]["recall"] == 0.0


def test_perfect_and_worse_than_chance():
    a = ["x", "y", "x", "y"]
    assert cohen_kappa(a, a) == 1.0
    assert cohen_kappa(a, ["y", "x", "y", "x"]) < 0


def test_known_kappa_value():
    # 2x2: 20 yy, 5 yn, 10 ny, 15 nn  -> po=.7, pe=.5 -> kappa=.4
    t = ["y"] * 25 + ["n"] * 25
    p = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert math.isclose(cohen_kappa(t, p, ["y", "n"]), 0.4)


def test_single_label_is_nan_not_crash():
    assert math.isnan(cohen_kappa(["a"] * 5, ["a"] * 5))


def test_weighted_kappa_penalises_far_misses_more():
    labels = ["0", "1", "2", "3"]
    t = ["0", "1", "2", "3"] * 5
    near = ["1", "2", "3", "3"] * 5
    far = ["3", "3", "0", "0"] * 5
    assert cohen_kappa(t, near, labels, "quadratic") > cohen_kappa(t, far, labels, "quadratic")


def test_ac1_more_stable_than_kappa_under_skew():
    t = ["w"] * 95 + ["t"] * 5
    p = ["w"] * 95 + ["w"] * 3 + ["t"] * 2
    assert gwet_ac1(t, p) > cohen_kappa(t, p)


def test_precision_recall_and_support():
    t = ["t", "t", "w", "w", "w"]
    p = ["t", "w", "t", "w", "w"]
    r = per_class(t, p, ["t", "w"])
    assert r["t"]["recall"] == 0.5 and r["t"]["precision"] == 0.5 and r["t"]["support"] == 2


def test_bootstrap_interval_wide_on_small_n_and_deterministic():
    t = ["a", "b"] * 6
    p = ["a", "b", "a", "a", "b", "b"] * 2
    lo, hi = bootstrap_ci(lambda x, y: cohen_kappa(x, y), t, p, n_boot=500, seed=1)
    assert (lo, hi) == bootstrap_ci(lambda x, y: cohen_kappa(x, y), t, p, n_boot=500, seed=1)
    assert hi - lo > 0.3


def test_report_shape_and_length_mismatch():
    r = agreement_report(["a", "b", "a"], ["a", "b", "b"], n_boot=100)
    assert {"kappa", "gwet_ac1", "per_class", "kappa_ci95", "n"} <= set(r)
    import pytest
    with pytest.raises(ValueError):
        agreement_report(["a"], ["a", "b"])
