"""Replay validation for the BO loop (docs/42 stage S1).

The thing worth testing here is not that the loop runs. It is that **the gate can return NO-GO**,
that the join between the design matrix and the scored outputs cannot silently attach the wrong
parameters to a real result, and that the acquisition actually behaves like a
feasibility-weighted expected improvement rather than merely producing numbers.

A gate whose only tested path is the passing one is not a gate
([[feedback_a_check_that_cannot_fail]]), so both verdicts are asserted below.
"""
import csv
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.bayesian_optimization.bo_replay import (  # noqa: E402
    Pool,
    _greedy_batch,
    acquisition,
    build_pool,
    gate,
    hit_iteration,
    parse_viable_if,
    run_bo,
    run_random,
)
from tools.bayesian_optimization.objective import Target  # noqa: E402


# =============================================================================
# The join -- the place a silent error would be worst
# =============================================================================

def _write_case_files(tmp_path, n_rows, cases, values):
    x = tmp_path / "X.txt"
    np.savetxt(x, np.arange(n_rows * 2, dtype=float).reshape(n_rows, 2))
    y = tmp_path / "Y.csv"
    with y.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case", "status", "a", "b"])
        for c, (va, vb) in zip(cases, values):
            w.writerow([c, "COMPLETED", va, vb])
    t = tmp_path / "t.yaml"
    t.write_text("targets:\n  a: {observed: 10.0, uncertainty: 0.2}\n"
                 "  b: {observed: 20.0, uncertainty: 0.2}\n")
    return x, y, t


def test_case_i_joins_to_matrix_row_i_minus_1(tmp_path):
    """A2MC's convention (`materialize_adapter_ensemble.py:216`). Getting it off by one attaches
    the wrong parameters to a real result and every downstream number stays plausible."""
    x, y, t = _write_case_files(tmp_path, 4, [1, 2, 3, 4],
                               [(10, 20)] * 4)
    pool = build_pool(x, y, t, ["a", "b"])
    assert np.array_equal(pool.cases, [1, 2, 3, 4])
    assert np.array_equal(pool.X[0], [0.0, 1.0])      # case 1 -> row 0
    assert np.array_equal(pool.X[3], [6.0, 7.0])      # case 4 -> row 3


def test_the_BASELINE_case_has_no_matrix_row_and_is_dropped(tmp_path):
    """Case 0 is the unperturbed V0. Under `i - 1` it indexes -1, which in numpy is the LAST row
    of the design -- so keeping it would pair the baseline's result with the final design row."""
    x, y, t = _write_case_files(tmp_path, 3, [0, 1, 2], [(10, 20)] * 3)
    pool = build_pool(x, y, t, ["a", "b"])
    assert 0 not in pool.cases.tolist()
    assert len(pool) == 2
    assert np.array_equal(pool.X[0], [0.0, 1.0])


def test_a_case_number_beyond_the_design_is_REFUSED(tmp_path):
    """The wrong round's matrix is the realistic way this happens, and it would otherwise index
    happily until it ran off the end."""
    x, y, t = _write_case_files(tmp_path, 2, [1, 2, 9], [(10, 20)] * 3)
    with pytest.raises(SystemExit, match="outside the 2-row design"):
        build_pool(x, y, t, ["a", "b"])


def test_an_unscorable_row_never_enters_the_pool(tmp_path):
    x, y, t = _write_case_files(tmp_path, 3, [1, 2, 3],
                               [(10, 20), (float("nan"), 20), (12, 22)])
    pool = build_pool(x, y, t, ["a", "b"])
    assert pool.cases.tolist() == [1, 3]
    assert np.isfinite(pool.V).all()


# =============================================================================
# Viability
# =============================================================================

def test_parse_viable_if_reads_each_operator_and_refuses_a_bare_string():
    assert parse_viable_if("NPP>1.0") == ("NPP", ">", 1.0)
    assert parse_viable_if("NPP>=1.0") == ("NPP", ">=", 1.0)
    assert parse_viable_if("x<2") == ("x", "<", 2.0)
    assert parse_viable_if(None) is None
    with pytest.raises(SystemExit, match="no comparison operator"):
        parse_viable_if("NPP alive")


def test_viable_if_naming_an_unscored_target_is_refused(tmp_path):
    x, y, t = _write_case_files(tmp_path, 2, [1, 2], [(10, 20)] * 2)
    with pytest.raises(SystemExit, match="not a scored target"):
        build_pool(x, y, t, ["a", "b"], viable_if="zzz>1")


def test_viable_if_splits_the_pool_on_the_named_target(tmp_path):
    x, y, t = _write_case_files(tmp_path, 3, [1, 2, 3], [(0.0, 20), (10, 20), (0.5, 20)])
    pool = build_pool(x, y, t, ["a", "b"], viable_if="a>1.0")
    assert pool.viable.tolist() == [False, True, False]


# =============================================================================
# The acquisition
# =============================================================================

class _FlatGP:
    def __init__(self, mu, sd):
        self.mu, self.sd = mu, sd

    def predict(self, X):
        return np.full(len(X), self.mu)

    def predict_std(self, X):
        return np.full(len(X), self.sd)


def _pool(n=6):
    ts = [Target("a", 10.0, 0.2), Target("b", 20.0, 0.2)]
    return Pool(cases=np.arange(1, n + 1), X=np.linspace(0, 1, n).reshape(n, 1),
                Yt=np.zeros((n, 2)), V=np.ones(n), viable=np.ones(n, bool), targets=ts)


def test_expected_improvement_is_non_negative_and_grows_with_the_incumbent():
    """EI is `E[max(0, V* - V)]`: a worse incumbent leaves more room to improve. If this were
    inverted the loop would walk away from the optimum and still produce a tidy curve."""
    p = _pool()
    rng = np.random.default_rng(0)
    gps = [_FlatGP(10.0, 1.0), _FlatGP(20.0, 1.0)]
    cand = np.arange(len(p))
    lo = acquisition(p, gps, None, cand, V_star=0.5, n_mc=4000, rng=np.random.default_rng(1))
    hi = acquisition(p, gps, None, cand, V_star=3.0, n_mc=4000, rng=np.random.default_rng(1))
    assert (lo >= 0).all() and (hi >= 0).all()
    assert hi.mean() > lo.mean()
    del rng


def test_P_viable_MULTIPLIES_the_acquisition_and_zero_kills_it():
    """docs/42 section 4.2: steer away from regions that return nothing, without teaching the GP
    that they are merely poor."""
    class _Clf:
        classes_ = np.array([False, True])

        def predict_proba(self, X):
            p = np.linspace(0.0, 1.0, len(X))
            return np.stack([1 - p, p], axis=1)

    p = _pool()
    gps = [_FlatGP(10.0, 1.0), _FlatGP(20.0, 1.0)]
    cand = np.arange(len(p))
    plain = acquisition(p, gps, None, cand, 3.0, 4000, np.random.default_rng(2))
    weighted = acquisition(p, gps, _Clf(), cand, 3.0, 4000, np.random.default_rng(2))
    assert weighted[0] == pytest.approx(0.0)          # P(viable) = 0
    assert weighted[-1] == pytest.approx(plain[-1], rel=1e-9)   # P(viable) = 1
    assert np.all(np.diff(weighted) >= -1e-12)        # monotone in P(viable)


def test_the_max_is_taken_INSIDE_the_monte_carlo_sample():
    """docs/42 section 3: fit the targets, never fit the max. Taking the max of the MEANS instead
    of the mean of the MAXES understates `V` whenever the targets are uncertain -- Jensen, and it
    is invisible in any single number the loop prints.

    Two targets, both centred exactly on their observations, so max-of-means gives V = 0 and EI
    = V*. Sampling first cannot: |draw - obs| is positive almost surely.
    """
    p = _pool()
    gps = [_FlatGP(10.0, 2.0), _FlatGP(20.0, 4.0)]
    ei = acquisition(p, gps, None, np.arange(len(p)), V_star=1.0, n_mc=20000,
                     rng=np.random.default_rng(3))
    assert ei.mean() < 0.999, "EI equals V* exactly, which means V was evaluated at the means"
    assert ei.mean() > 0.0


def test_a_batch_returns_q_DISTINCT_candidates():
    p = _pool(30)
    a = np.linspace(0, 1, 30)
    pick = _greedy_batch(p, np.arange(30), a, q=5)
    assert len(pick) == 5 and len(set(pick.tolist())) == 5


def test_the_batch_is_not_five_copies_of_one_peak():
    """Local penalisation exists so a batch spends its q evaluations on more than one region;
    without it every pick clusters at the acquisition maximum and the batch buys one point's
    worth of information."""
    ts = [Target("a", 10.0, 0.2)]
    x = np.linspace(0, 1, 200).reshape(-1, 1)
    p = Pool(cases=np.arange(1, 201), X=x, Yt=np.zeros((200, 1)), V=np.ones(200),
             viable=np.ones(200, bool), targets=ts)
    a = np.exp(-0.5 * ((x[:, 0] - 0.5) / 0.02) ** 2)      # one sharp peak
    pick = _greedy_batch(p, np.arange(200), a, q=5)
    assert x[pick, 0].std() > 0.02, "every pick landed inside one peak width"


# =============================================================================
# The gate -- both verdicts
# =============================================================================

def test_hit_iteration_is_one_based_and_None_when_never_reached():
    assert hit_iteration(np.array([3.0, 2.0, 1.0]), bar=2.0) == 2
    assert hit_iteration(np.array([3.0, 2.0]), bar=0.5) is None


def test_the_gate_returns_NO_GO_when_bo_does_not_beat_random():
    """The path that makes this a gate rather than a formality."""
    bad = [np.array([2.0, 2.0, 2.0])] * 3
    good = [np.array([2.0, 1.0, 0.1])] * 3
    v = gate(bo_curves=bad, rnd_curves=good, exp_curves=bad, bar=0.5, budget=3)
    assert v["verdict"] == "NO-GO" and v["beats_random"] is False


def test_the_gate_returns_NO_GO_when_bo_only_matches_pure_EXPLOITATION():
    """Second condition. Random is a weak bar on a large pool, so a PASS that came entirely from
    having a surrogate -- with the acquisition contributing nothing -- must not read as GO."""
    bo = [np.array([2.0, 1.0, 0.4])] * 3
    exploit = [np.array([2.0, 0.9, 0.2])] * 3          # strictly better than bo
    rnd = [np.array([2.0, 2.0, 2.0])] * 3
    v = gate(bo, rnd, exploit, bar=0.5, budget=3)
    assert v["beats_random"] is True
    assert v["at_least_matches_pure_exploitation"] is False
    assert v["verdict"] == "NO-GO"


def test_the_gate_returns_GO_only_when_BOTH_conditions_hold():
    bo = [np.array([2.0, 1.0, 0.1])] * 3
    exploit = [np.array([2.0, 1.5, 0.9])] * 3
    rnd = [np.array([2.0, 2.0, 2.0])] * 3
    v = gate(bo, rnd, exploit, bar=0.5, budget=3)
    assert v["verdict"] == "GO"
    assert v["bo"]["n_reached"] == 3 and v["random"]["n_reached"] == 0


# =============================================================================
# End to end, on a synthetic problem with a known answer
# =============================================================================

def test_bo_finds_a_planted_optimum_that_random_search_misses():
    """A functional check with an answer known by construction, so it is independent of whether
    the real EcoSIM gate happens to pass.

    2000 candidates in 4-D; `V` is a smooth bowl centred at 0.5 with a single sharp minimum. BO
    gets 20 seed + 4x8 = 52 evaluations, 2.6% of the pool, and must reach the true top-10 that
    52 random draws almost never find.
    """
    rng = np.random.default_rng(7)
    n, d = 2000, 4
    X = rng.random((n, d))
    dist = np.linalg.norm(X - 0.5, axis=1)
    ts = [Target("a", 10.0, 0.2)]
    # a value whose violation is monotone in `dist`: |y-10|/(0.2*10) = dist  ->  y = 10 + 2*dist
    Yt = (10.0 + 2.0 * dist).reshape(-1, 1)
    V = dist.copy()
    pool = Pool(cases=np.arange(1, n + 1), X=X, Yt=Yt, V=V,
                viable=np.ones(n, bool), targets=ts)
    bar = float(np.sort(V)[9])

    hits_bo = sum(hit_iteration(run_bo(pool, 20, 4, 8, seed=s, n_mc=128, n_cand=800),
                                bar) is not None for s in range(3))
    hits_rn = sum(hit_iteration(run_random(pool, 52, seed=s), bar) is not None
                  for s in range(3))
    assert hits_bo >= 2, f"BO reached the planted optimum in only {hits_bo}/3 replicates"
    assert hits_bo > hits_rn
