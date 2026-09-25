"""The S3 dry loop, `tools/bayesian_optimization/bo_loop.py` (docs/42 stage S3, docs/45 test 15).

What matters here is not that the command runs. It is that every row of an ensemble is labelled
from its STATUS, so a run that never started is never taught to the classifier as a failure; that
the viability rules are all applied, in any order; that the matrix it writes is the one
`scripts/materialize_adapter_ensemble.py` reads, in the parameter list's box; that the same seed
reproduces the same proposal; that it refuses rather than guesses; and that each outcome has its
own exit code.

The synthetic ensemble below carries one row of every kind that matters: rows that pass both
rules, fail NPP only, fail Fs only, a FAILED row with NaN outputs, a FAILED row whose outputs are
finite (so only the status can label it), a COMPLETED row with a non-finite target, a RUNNING row
listed in the failed-cases file, a COMPLETED row that file also lists, PENDING, UNKNOWN and
SCORE_ERROR rows, and the baseline case 0.

Every test is written so that it fails if the behaviour it names is removed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.bayesian_optimization import bo_loop  # noqa: E402
from tools.bayesian_optimization.acquisition import propose_batch  # noqa: E402
from tools.bayesian_optimization.objective import Target  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore::sklearn.exceptions.ConvergenceWarning")

LOWER = np.array([10.0, 0.1, 100.0])
UPPER = np.array([20.0, 0.5, 300.0])
N_CASES = 48
Q = 4
N_CAND = 64

VIABLE = list(range(1, 31)) + list(range(43, 49))
NONVIABLE = [31, 32, 33, 34, 35]            # 31-32 fail NPP>1 only, 33-35 fail Fs<50 only
FAILED = [36, 38, 42]                       # FAILED (NaN), RUNNING listed, FAILED (finite)
COMPLETED_NONFINITE = [37]
EXCLUDED = [39, 40, 41]                     # SCORE_ERROR, PENDING, UNKNOWN
BASELINE = [0]
KNOWN = N_CASES                             # every case but the baseline has a design row
LABELLED = len(VIABLE) + len(NONVIABLE) + len(FAILED)
CASES = {"viable": VIABLE, "nonviable": NONVIABLE, "failed": FAILED,
         "completed_nonfinite": COMPLETED_NONFINITE, "excluded": EXCLUDED, "baseline": BASELINE}
TARGETS = [Target("NPP", 389.0, 0.36), Target("plant_C", 651.7, 0.35), Target("Fs", 6.2, 0.28)]
ALL_TRUE = {"NPP": True, "plant_C": True, "Fs": True}


def _write_y(path, rows, header=("case", "status", "NPP", "plant_C", "Fs")):
    with Path(path).open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def _y_rows(U):
    def model(u):
        return [389.0 * (0.4 + 1.2 * u[0]), 651.7 * (0.5 + 0.9 * u[1] * (0.5 + u[0])),
                6.2 * (0.5 + 1.0 * u[2])]

    rows = [[0, "COMPLETED", 400.0, 600.0, 6.0]]
    nan3 = [np.nan] * 3
    for c in range(1, N_CASES + 1):
        y, st = model(U[c - 1]), "COMPLETED"
        if c in (31, 32):
            y[0] = 0.5
        if c in (33, 34, 35):
            y[2] = 60.0
        if c == 36:
            st, y = "FAILED", nan3
        if c == 37:
            y[2] = np.nan
        if c == 38:
            st, y = "RUNNING", nan3
        if c == 39:
            st, y = "SCORE_ERROR:TypeError", nan3
        if c == 40:
            st, y = "PENDING", nan3
        if c == 41:
            st, y = "UNKNOWN", nan3
        if c == 42:
            st = "FAILED"
        rows.append([c, st] + list(y))
    return rows


def _true_V(case):
    """V of a synthetic case, computed from its Y row here rather than by objective.py."""
    U = np.random.default_rng(3).uniform(size=(N_CASES, 3))
    row = {r[0]: r for r in _y_rows(U)}[case]
    return max(abs(row[2 + j] - t.observed) / (t.uncertainty * t.observed)
               for j, t in enumerate(TARGETS))


@pytest.fixture(scope="module")
def ens(tmp_path_factory):
    d = tmp_path_factory.mktemp("ensemble")
    (d / "params.csv").write_text("name,pft,lower_bound,upper_bound\n"
                                  "A,1,10,20\nB,1,0.1,0.5\nC,0,100,300\n")
    (d / "targets.yaml").write_text(
        "model: synthmodel\ntargets:\n"
        "  NPP: {observed: 389.0, uncertainty: 0.36}\n"
        "  plant_C: {observed: 651.7, uncertainty: 0.35}\n"
        "  Fs: {observed: 6.2, uncertainty: 0.28}\n")
    U = np.random.default_rng(3).uniform(size=(N_CASES, 3))
    np.savetxt(d / "X.txt", LOWER + U * (UPPER - LOWER))
    _write_y(d / "Y.csv", _y_rows(U))
    # 38 is RUNNING and listed, so it becomes failed; 5 is listed but COMPLETED, so it stays.
    (d / "failed.csv").write_text("case,arm\n38,a\n5,a\n")
    return d


def _argv(ens, out, *extra, rules=("NPP>1", "Fs<50"), failed=True, dry_run=True):
    argv = ["--x-matrix", str(ens / "X.txt"), "--y-matrix", str(ens / "Y.csv"),
            "--param-list", str(ens / "params.csv"), "--targets", str(ens / "targets.yaml"),
            "--only", "NPP,plant_C,Fs", "--q", str(Q), "--n-cand", str(N_CAND),
            "--out", str(out)]
    for r in rules:
        argv += ["--viable-if", r]
    if failed:
        argv += ["--failed-cases", str(ens / "failed.csv")]
    if dry_run:
        argv.append("--dry-run")
    return argv + list(extra)


def _read(out):
    out = Path(out)
    matrix = out / bo_loop.MATRIX_FILE
    return {"matrix": matrix.read_bytes() if matrix.exists() else None,
            "table": (out / bo_loop.TABLE_FILE).read_bytes(),
            "meta": json.loads((out / bo_loop.META_FILE).read_text()),
            "notes": (out / bo_loop.NOTES_FILE).read_text()}


@pytest.fixture(scope="module")
def runs(ens, tmp_path_factory):
    """Run A (rules NPP then Fs), A again with --force into the same folder, B (rules in the
    other order) and C (seed 1)."""
    root = tmp_path_factory.mktemp("runs")
    got = {}
    got["A_code"] = bo_loop.main(_argv(ens, root / "A"))
    got["A"] = _read(root / "A")
    got["A2_code"] = bo_loop.main(_argv(ens, root / "A", "--force"))
    got["A2"] = _read(root / "A")
    got["B_code"] = bo_loop.main(_argv(ens, root / "B", rules=("Fs<50", "NPP>1")))
    got["B"] = _read(root / "B")
    got["C_code"] = bo_loop.main(_argv(ens, root / "C", "--seed", "1"))
    got["C"] = _read(root / "C")
    return got


# =============================================================================
# Labels
# =============================================================================

def test_labels_follow_the_status_table_whatever_order_the_rules_are_given_in(runs):
    """Catches: the rules parsed with a plain `store` so only the LAST --viable-if applies
    (rule order then changes the labels), the status column ignored (a FAILED row with finite
    outputs becomes viable, RUNNING/PENDING/SCORE_ERROR rows become crashed completions), and
    the failed-cases file overriding a COMPLETED row (case 5 would become failed)."""
    for key in ("A", "B"):
        lab = runs[key]["meta"]["labels"]
        assert lab["cases"] == CASES, key
        assert lab["failed_from_status"] == {"FAILED": 2, "RUNNING": 1}
        assert lab["running_corroboration"] == "failed_cases"
    assert runs["A"]["meta"]["labels"] == runs["B"]["meta"]["labels"]
    assert runs["A"]["meta"]["n_viable"] == len(VIABLE)
    assert runs["A"]["meta"]["status_counts"] == {
        "COMPLETED": 43, "FAILED": 2, "PENDING": 1, "RUNNING": 1,
        "SCORE_ERROR:TypeError": 1, "UNKNOWN": 1}
    # the same labels and seed give the same proposal
    assert runs["A"]["matrix"] == runs["B"]["matrix"]


def test_ensemble_drained_relabels_the_running_row_without_a_failed_cases_file(ens, tmp_path):
    """The second corroboration the status table allows for a RUNNING row. Catches:
    --ensemble-drained parsed but never reaching the labelling (the RUNNING row is then refused
    as uncorroborated), and a drained ensemble relabelling anything but RUNNING rows (a COMPLETED
    or excluded row would move to failed)."""
    out = tmp_path / "out"
    code = bo_loop.main(_argv(ens, out, "--ensemble-drained", failed=False))
    assert code == 8
    meta = _read(out)["meta"]
    assert meta["inputs"]["failed_cases"] is None
    lab = meta["labels"]
    assert lab["cases"] == CASES
    assert lab["failed_from_status"] == {"FAILED": 2, "RUNNING": 1}
    assert lab["running_corroboration"] == "ensemble_drained"


def test_finite_only_makes_every_completed_finite_row_viable_and_still_labels_by_status(ens,
                                                                                    tmp_path):
    """--viable-if-finite-only, the explicit alternative to rules, on its own. Catches: the option
    refused unless a rule is also given, and a FAILED row labelled by its outputs once no rule
    filters the rows (case 42, FAILED with finite outputs, would become viable)."""
    out = tmp_path / "out"
    code = bo_loop.main(_argv(ens, out, "--viable-if-finite-only", rules=()))
    assert code == 8
    meta = _read(out)["meta"]
    assert meta["viability"] == {"rules": [], "parsed": [], "finite_only": True,
                                 "combined": "AND"}
    assert meta["labels"]["cases"] == dict(CASES, viable=sorted(VIABLE + NONVIABLE), nonviable=[])
    assert meta["n_viable"] == len(VIABLE) + len(NONVIABLE)
    assert meta["surrogate"]["n_used"] == {t.name: len(VIABLE) + len(NONVIABLE) for t in TARGETS}


def test_the_baseline_case_number_comes_from_the_flag(ens, runs, tmp_path):
    """The baseline renumbered from 0 to 49. Catches: --baseline-case parsed but ignored (case 0
    hard-coded, so case 49 is refused as outside the 48-row matrix), and a baseline that joins a
    design row or changes the observed positions (the proposal would then differ from run A's,
    which has the same rows with the baseline numbered 0)."""
    d = _copy_ens(ens, tmp_path)
    _mutate_y(d, lambda rows, h: ([["49"] + r[1:] if r[0] == "0" else r for r in rows], h))
    out = tmp_path / "out"
    assert bo_loop.main(_argv(d, out, "--baseline-case", "49")) == 8
    got = _read(out)
    assert got["meta"]["labels"]["cases"] == dict(CASES, baseline=[49])
    assert got["meta"]["diagnostics"]["n_observed"] == KNOWN
    assert got["matrix"] is not None and got["matrix"] == runs["A"]["matrix"]


def test_every_case_with_a_design_row_is_an_observed_position_but_only_labelled_rows_train(runs):
    """Catches: passing only the labelled rows to propose_batch, which would let a PENDING or
    SCORE_ERROR case be proposed again; and the GPs training on anything but the viable rows or
    dropping the incumbent."""
    meta = runs["A"]["meta"]
    assert meta["diagnostics"]["n_observed"] == KNOWN
    sur = meta["surrogate"]
    assert sur["n_fit_rows"] == LABELLED
    assert sur["n_used"] == {"NPP": len(VIABLE), "plant_C": len(VIABLE), "Fs": len(VIABLE)}
    assert sur["incumbent_in_training"] == ALL_TRUE
    assert sur["classifier"]["fitted"] is True
    assert "uncalibrated" in sur["classifier"]["p_viable_is"]

    V = {c: _true_V(c) for c in VIABLE}
    best = min(V, key=V.get)
    assert meta["V_star"]["case"] == best
    assert meta["V_star"]["value"] == pytest.approx(V[best], rel=1e-12)


def test_a_capped_gp_keeps_the_best_rows_and_the_subsample_seed_reaches_the_draw(ens, tmp_path):
    """With --max-points below the viable count every GP subsamples. Catches: the fit called
    without priority=V, or with keep_best forced to 0 (a random draw drops the incumbent and
    propose_batch refuses the batch); and --subsample-seed not reaching the learner (both seeds
    would then train on the same rows and write the same table)."""
    got = {}
    for s in (0, 1):
        out = tmp_path / f"subsample{s}"
        with pytest.warns(RuntimeWarning, match=r"subsampled 36 -> 10 points, keeping the 5 "
                                                r"lowest-priority rows"):
            code = bo_loop.main(_argv(ens, out, "--max-points", "10", "--keep-best", "5",
                                      "--subsample-seed", str(s)))
        assert code == 8, s
        got[s] = _read(out)
    for s, g in got.items():
        meta = g["meta"]
        sur = meta["surrogate"]
        assert sur["n_used"] == {"NPP": 10, "plant_C": 10, "Fs": 10}, s
        assert sur["incumbent_in_training"] == ALL_TRUE, s
        lrn = sur["learner"]
        assert (lrn["max_points_requested"], lrn["max_points"], lrn["keep_best"],
                lrn["subsample_seed"], lrn["priority"]) == (10, 10, 5, s, "V"), s
        assert meta["seeds"]["subsample_seed"] == s
        best = min(VIABLE, key=_true_V)
        assert meta["V_star"]["case"] == best, s
    assert got[0]["table"] != got[1]["table"]


# =============================================================================
# The matrix, the table and determinism
# =============================================================================

def test_the_matrix_loads_at_q_by_p_inside_the_bounds_and_matches_the_table(runs):
    """Catches: unit-cube coordinates written instead of native values, a column order that is
    not the parameter list's, a table that disagrees with the matrix, and per-pick columns
    written under the wrong header (the predicted values then fall outside the synthetic
    outputs' range and no longer reproduce V_mean and the binding target; alpha no longer equals
    p_viable times ei)."""
    assert runs["A"]["matrix"] is not None
    path = Path(runs["A"]["meta"]["materialisation_recipe"]["matrix"])
    M = np.loadtxt(path, ndmin=2)
    assert M.shape == (Q, 3)
    assert np.all((M >= LOWER) & (M <= UPPER))
    assert not np.all((M >= 0) & (M <= 1)), "these are unit-cube values, not native ones"

    table = list(csv.DictReader(runs["A"]["table"].decode().splitlines()))
    assert len(table) == Q
    T = np.array([[float(r[c]) for c in ("A_1", "B_1", "C")] for r in table])
    assert np.array_equal(T, M)
    obs = np.array([t.observed for t in TARGETS])
    unc = np.array([t.uncertainty for t in TARGETS])
    # the ranges the synthetic viable rows span, with room for the GP mean between them
    ranges = {"NPP": (150.0, 700.0), "plant_C": (300.0, 1300.0), "Fs": (2.0, 12.0)}
    for r in table:
        assert r["pick_source"] in ("argmax", "maximin", "local_penalisation")
        assert float(r["V_star_used"]) == runs["A"]["meta"]["V_star"]["value"]
        pred = np.array([float(r[f"predicted_{t.name}"]) for t in TARGETS])
        for t, v in zip(TARGETS, pred):
            assert ranges[t.name][0] < v < ranges[t.name][1], (t.name, v)
        v = np.abs(pred - obs) / (unc * obs)
        assert float(r["V_mean"]) == pytest.approx(v.max(), rel=1e-9)
        assert r["binding"] == TARGETS[int(np.argmax(v))].name
        assert 0.0 <= float(r["p_viable"]) <= 1.0
        assert float(r["alpha"]) == pytest.approx(float(r["p_viable"]) * float(r["ei"]),
                                                  rel=1e-9)
        assert all(0.0 < float(r[f"sd_ratio_{t.name}"]) < 5.0 for t in TARGETS)
        assert r["in_hull"] == "True"
    assert runs["A"]["meta"]["n_proposed"] == Q


def test_the_plausibility_figures_sit_beside_a_chance_baseline_drawn_from_the_scan(ens, runs):
    """Each printed figure must be set beside the same figure for random q-point draws from the
    Sobol' scan the proposals were chosen from. Catches: a chance baseline drawn from the
    proposals themselves (the chance value then equals the proposals' own), a draw size other
    than q, a figure missing, a V_mean range that is not the table's, a minimum pairwise
    distance that is not the minimum, and a near-bound fraction measured at a margin other than 1%
    of the range. Every scan-based figure, for the proposals and for chance, is recomputed here
    from scipy's Sobol' generator and brute-force distances."""
    from scipy.stats import qmc

    meta = runs["A"]["meta"]
    pl = meta["plausibility"]
    for key in ("fraction_inside_bounds", "min_pairwise_linf", "nearest_observed_linf_min",
                "nearest_observed_linf_median", "fraction_coords_within_1pct_of_bound",
                "V_mean_min", "V_mean_max"):
        assert set(pl[key]) == {"proposals", "chance_median", "chance_p05", "chance_p95"}, key
    assert (pl["n_proposals"], pl["chance_draws"], pl["chance_draw_size"]) == (Q, 200, Q)
    assert pl["chance_source"] == "sobol_scan"
    assert pl["V_star"] == meta["V_star"]["value"]

    M = np.loadtxt(Path(meta["materialisation_recipe"]["matrix"]), ndmin=2)
    U_prop = (M - LOWER) / (UPPER - LOWER)
    U_obs = (np.loadtxt(ens / "X.txt") - LOWER) / (UPPER - LOWER)

    def nearest(A):
        return np.abs(A[:, None, :] - U_obs[None, :, :]).max(axis=2).min(axis=1)

    def min_pairwise(A):
        return min(float(np.max(np.abs(A[i] - A[j])))
                   for i in range(len(A)) for j in range(i + 1, len(A)))

    def near_bound(A):
        return float(np.mean((A < 0.01) | (A > 0.99)))

    brute = {"nearest_observed_linf_median": lambda A: float(np.median(nearest(A))),
             "nearest_observed_linf_min": lambda A: float(nearest(A).min()),
             "min_pairwise_linf": min_pairwise,
             "fraction_coords_within_1pct_of_bound": near_bound}
    scan = qmc.Sobol(d=3, scramble=True, seed=0).random(N_CAND)
    rng = np.random.default_rng(0)
    draws = [scan[rng.choice(N_CAND, Q, replace=False)] for _ in range(200)]
    assert pl["fraction_inside_bounds"]["proposals"] == 1.0
    for key, fn in brute.items():
        chance = [fn(D) for D in draws]
        want = {"proposals": fn(U_prop), "chance_median": float(np.median(chance)),
                "chance_p05": float(np.quantile(chance, 0.05)),
                "chance_p95": float(np.quantile(chance, 0.95))}
        for k, v in want.items():
            assert pl[key][k] == pytest.approx(v, rel=1e-12, abs=1e-15), (key, k)
    assert pl["nearest_observed_linf_median"]["chance_median"] != pytest.approx(
        pl["nearest_observed_linf_median"]["proposals"], rel=1e-6)
    # the near-bound figure is not zero at every chance quantile, so its margin is exercised
    assert pl["fraction_coords_within_1pct_of_bound"]["chance_p95"] > 0

    Vm = [float(r["V_mean"]) for r in csv.DictReader(runs["A"]["table"].decode().splitlines())]
    assert (pl["V_mean_min"]["proposals"], pl["V_mean_max"]["proposals"]) == (min(Vm), max(Vm))


def test_sd_ratio_and_the_hull_record_match_an_independent_refit(ens, runs):
    """The surrogate is refitted here from the ensemble files and run A's labels, without
    bo_loop. Catches: sd_ratio columns that do not carry posterior sd / target sd (a constant
    written in every cell passes a range check), and a hull record whose scan-distance quantiles
    or threshold are not the fitted gate's (every quantile set to the median, say)."""
    from scipy.stats import qmc

    from models.surrogate.learners import GPLearner
    from models.surrogate.spec import SurrogateSpec, TargetSpec
    from models.surrogate.tiers import S1Surrogate

    meta = runs["A"]["meta"]
    cases = meta["labels"]["cases"]
    fit_cases = sorted(cases["viable"] + cases["nonviable"] + cases["failed"])
    X = np.loadtxt(ens / "X.txt")[np.array(fit_cases) - 1]
    rows = {int(r[0]): r for r in csv.reader((ens / "Y.csv").read_text().splitlines()[1:])}
    Y = np.array([[float(v) for v in rows[c][2:5]] if c not in cases["failed"]
                  else [np.nan] * 3 for c in fit_cases])
    viable = np.isin(fit_cases, cases["viable"])
    spec = SurrogateSpec(name="refit", use_mode="offline_search", tier="S1",
                         input_names=("A_1", "B_1", "C"), input_lower=tuple(LOWER),
                         input_upper=tuple(UPPER),
                         targets=tuple(TargetSpec(t.name, lower=t.lo, upper=t.hi)
                                       for t in TARGETS))
    model = S1Surrogate(spec, learner=GPLearner(n_restarts=0, max_points=len(fit_cases),
                                                random_state=0),
                        classifier="rf", calibration_fraction=0, random_state=0)
    model.fit(X, Y, viable)

    table = list(csv.DictReader(runs["A"]["table"].decode().splitlines()))
    assert table[0]["pick_source"] == "argmax"     # scored by the fitted posterior, not a believer
    x1 = np.array([[float(table[0][c]) for c in ("A_1", "B_1", "C")]])
    _, sd = model.posterior(x1)
    want = sd[0] / model.target_sd_
    got = np.array([float(table[0][f"sd_ratio_{t.name}"]) for t in TARGETS])
    # A posterior sd this far below the target sd carries cancellation from the GP variance, and
    # the batch it is computed in differs; a wrong column is off by orders of magnitude.
    np.testing.assert_allclose(got, want, rtol=1e-3)
    cells = {table[i][f"sd_ratio_{t.name}"] for i in range(Q) for t in TARGETS}
    assert len(cells) == Q * len(TARGETS)

    hull = meta["hull"]
    scan = qmc.Sobol(d=3, scramble=True, seed=0).random(N_CAND)
    dist, inside = model.hull(LOWER + scan * (UPPER - LOWER))
    quant = hull["sobol_scan_distance_quantiles"]
    assert list(quant) == ["q00", "q05", "q25", "q50", "q75", "q95", "q100"]
    for key, q in zip(quant, (0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0)):
        assert quant[key] == pytest.approx(float(np.quantile(dist, q)), rel=1e-9), key
    assert list(quant.values()) == sorted(quant.values()) and quant["q00"] < quant["q100"]
    assert hull["threshold"] == pytest.approx(model._gate.threshold, rel=1e-12)
    assert hull["sobol_scan_fraction_inside"] == pytest.approx(float(np.mean(inside)), rel=1e-12)


def test_the_seed_reaches_the_classifier_and_n_restarts_reaches_the_gps(ens, runs, tmp_path):
    """Catches: --seed not passed to the surrogate (its RF keeps random_state 0; the different-
    seed test cannot see it, since the Sobol' seed alone changes the matrix), and --n-restarts
    not reaching the GP learners. Both are read from the fitted estimators, not from argv."""
    for key, seed in (("A", 0), ("C", 1)):
        settings = runs[key]["meta"]["surrogate"]["classifier"]["settings"]
        assert settings["random_state"] == seed, key
    zero = {t.name: 0 for t in TARGETS}
    assert runs["A"]["meta"]["surrogate"]["learner"]["n_restarts"] == zero
    out = tmp_path / "out"
    assert bo_loop.main(_argv(ens, out, "--n-restarts", "1")) == 8
    assert _read(out)["meta"]["surrogate"]["learner"]["n_restarts"] == {t.name: 1
                                                                        for t in TARGETS}


def test_the_same_seed_reproduces_matrix_table_and_meta_and_another_seed_does_not(runs):
    """Catches: anything run-dependent (a clock, a path that changes) recorded outside "run",
    and a seed that does not reach the candidate scan and the classifier."""
    a, a2, c = runs["A"], runs["A2"], runs["C"]
    assert a["matrix"] == a2["matrix"]
    assert a["table"] == a2["table"]
    strip = lambda m: {k: v for k, v in m.items() if k != "run"}  # noqa: E731
    assert strip(a["meta"]) == strip(a2["meta"])
    assert a2["meta"]["run"]["argv"][-1] == "--force"
    assert c["matrix"] is not None and c["matrix"] != a["matrix"]
    assert c["meta"]["seeds"]["seed"] == 1


# =============================================================================
# Outcomes and exit codes
# =============================================================================

def test_a_full_batch_without_provenance_exits_8_and_says_so(runs):
    """Catches: an exit code that ignores missing provenance, the most likely way a proposal
    gets detached from the binary that produced its training data."""
    assert runs["A_code"] == 8
    meta = runs["A"]["meta"]
    assert meta["outcome"] == "provenance_incomplete" and meta["exit_code"] == 8
    assert meta["provenance"]["status"] == "provenance_incomplete"
    assert meta["provenance"]["missing"] == ["round_config", "training_binary"]
    assert meta["shortfall"] == 0
    assert meta["hull"]["applied"] is True
    # Without the round config the run root has no prefix, so no command is offered.
    recipe = meta["materialisation_recipe"]
    assert recipe["matrix"] is not None and recipe["command"] is None
    assert "--round-config" in recipe["command_note"]


@pytest.mark.parametrize("given", ["round_config", "training_binary"])
def test_one_provenance_record_without_the_other_is_still_incomplete_exit_8(ens, tmp_path, given):
    """Catches: provenance counted complete when only one of --round-config and
    --training-binary is given."""
    extra = []
    if given == "round_config":
        cfg = tmp_path / "round.sh"
        cfg.write_text('export A2MC_CASE_NAME_PATTERN="Synth_case{N}"\n')
        extra = ["--round-config", str(cfg)]
    else:
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"archives": [
            {"label": "synth_bin", "sha256": "ab" * 32, "binary": "model.x"}]}))
        extra = ["--training-binary", "synth_bin", "--binary-manifest", str(manifest)]
    out = tmp_path / "out"
    code = bo_loop.main(_argv(ens, out, *extra))
    assert code == 8
    prov = _read(out)["meta"]["provenance"]
    assert prov["status"] == "provenance_incomplete"
    assert prov["missing"] == [k for k in ("round_config", "training_binary") if k != given]
    assert prov[given] is not None


def test_a_full_batch_with_provenance_exits_0_and_records_a_safe_recipe(ens, tmp_path, capsys):
    """Catches: provenance never counted complete, the round config's values kept with their
    quotes and comments (the recipe would carry a broken case pattern), the round config being
    EXECUTED rather than read (its last line would create a file), a recipe that does not stop
    on an unset or existing run root, and a printed plausibility summary without its chance
    baselines."""
    marker = tmp_path / "SHOULD_NOT_EXIST"
    cfg = tmp_path / "round.sh"
    cfg.write_text(
        "#!/bin/bash\n"
        'export A2MC_ENSEMBLE_NAME="Synth_R1"\n'
        'export A2MC_CASE_NAME_PATTERN="Synth_case{N}"   # one directory per case\n'
        'export A2MC_OUTPUT_DIR="${A2MC_OUTPUT_ROOT}/${A2MC_ENSEMBLE_NAME}"\n'
        f"touch {marker}\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"_archive_root": "/archive", "archives": [
        {"label": "other_bin", "sha256": "cd" * 32, "binary": "model.x", "source": ""},
        {"label": "synth_bin_abc1234", "model": "synthmodel", "binary": "model.x",
         "sha256": "ab" * 32, "source": "branch exp/x @ abc1234"}]}))
    from phases.phase0_design.create_parameter_sample import write_problem_text
    salib = tmp_path / "salib.txt"
    write_problem_text(salib, "sobol", {"seed": 1}, ["A_1", "B_1", "C"], LOWER, UPPER)

    out = tmp_path / "out"
    code = bo_loop.main(_argv(ens, out, "--round-config", str(cfg),
                              "--training-binary", "synth_bin_abc1234",
                              "--binary-manifest", str(manifest), "--salib-problem", str(salib)))
    assert code == 0
    printed = capsys.readouterr().out
    assert not marker.exists(), "the round config was executed"
    got = _read(out)
    meta = got["meta"]
    assert meta["outcome"] == "full_batch" and meta["provenance"]["status"] == "complete"
    rc = meta["provenance"]["round_config"]
    assert rc["sha256"] == hashlib.sha256(cfg.read_bytes()).hexdigest()
    assert rc["exports"]["A2MC_CASE_NAME_PATTERN"] == "Synth_case{N}"
    assert len(rc["export_lines"]) == 3
    tb = meta["provenance"]["training_binary"]
    assert (tb["sha256"], tb["commit"], tb["binary"]) == ("ab" * 32, "abc1234", "model.x")
    assert meta["surrogate"]["spec_provenance"]["model_commit"] == "abc1234"
    assert meta["surrogate"]["spec_provenance"]["training_ensemble_id"] == "Synth_R1"

    recipe = meta["materialisation_recipe"]
    assert recipe["case_name_pattern"] == "Synth_case{N}"
    assert recipe["run_root_must_not_exist"] is True
    assert recipe["run_root"] != "${A2MC_OUTPUT_ROOT}/${A2MC_ENSEMBLE_NAME}"
    assert recipe["binary"]["path"] == "/archive/synth_bin_abc1234/model.x"
    cmd = recipe["command"]
    assert "Synth_case{N}" in cmd and recipe["command_note"] is None
    guards = ("source ", 'test -n "${A2MC_OUTPUT_DIR}" && ',
              f'test ! -e "{recipe["run_root"]}" && ', "scripts/materialize_adapter_ensemble.py")
    assert all(g in cmd for g in guards), cmd
    assert [cmd.index(g) for g in guards] == sorted(cmd.index(g) for g in guards), cmd
    assert "overwrites" in recipe["warning"]
    assert "--dry-run" in got["notes"] and "bo_loop.py" in got["notes"]

    assert "chance median [5%, 95%] over 200 draws of 4 Sobol' scan points" in printed
    num = r"-?(?:\d[\d.e+-]*|nan|inf)"
    for key in ("fraction_inside_bounds", "min_pairwise_linf", "nearest_observed_linf_min",
                "nearest_observed_linf_median", "fraction_coords_within_1pct_of_bound",
                "V_mean_min", "V_mean_max"):
        assert re.search(rf"^\s+{key}\s+{num} \| {num} \[{num}, {num}\]$", printed, re.M), key
    assert "(V* = " in printed


@pytest.mark.parametrize("pattern", ["${A2MC_ENSEMBLE_PREFIX}_case{N}", "Synth_TR{N}MG{M}"])
def test_a_case_pattern_the_materializer_cannot_take_verbatim_is_not_passed_to_it(ens, tmp_path,
                                                                                 pattern):
    """The materializer replaces only {N} in a case pattern, and a single-quoted argument never
    expands a shell variable. Catches: a pattern with a shell variable passed as a quoted
    --case-pattern (every case directory would be named with the literal `${...}`), and a
    command offered for a pattern with another placeholder (every name would keep `{M}`)."""
    cfg = tmp_path / "round.sh"
    cfg.write_text('export A2MC_OUTPUT_DIR="/runs/Synth_R1"\n'
                   f'export A2MC_CASE_NAME_PATTERN="{pattern}"\n')
    out = tmp_path / "out"
    assert bo_loop.main(_argv(ens, out, "--round-config", str(cfg))) == 8
    recipe = _read(out)["meta"]["materialisation_recipe"]
    assert recipe["case_name_pattern"] == pattern
    if "$" in pattern:
        assert recipe["command"] is not None
        assert "scripts/materialize_adapter_ensemble.py" in recipe["command"]
        assert "--case-pattern" not in recipe["command"]
        assert "A2MC_CASE_NAME_PATTERN" in recipe["command_note"]
    else:
        assert recipe["command"] is None
        assert "['{M}']" in recipe["command_note"]


def test_too_few_viable_rows_is_a_cold_start_exit_3_with_no_surrogate_fitted(ens, tmp_path):
    """Catches: a cold start reported as a normal batch, and a surrogate fitted on no viable
    row."""
    out = tmp_path / "out"
    code = bo_loop.main(_argv(ens, out, rules=("NPP>100000",)))
    assert code == 3
    meta = _read(out)["meta"]
    assert meta["outcome"] == "cold_start" and meta["proposal_status"] == "cold_start"
    assert meta["surrogate"] is None and meta["n_viable"] == 0
    assert meta["n_proposed"] == Q


def test_a_cold_start_classifier_never_sees_an_unlabelled_row(ens, tmp_path):
    """With one viable row, labelled failures and no surrogate, propose_batch fits its own
    classifier on the rows it is given. Catches: the excluded and non-finite rows passed to it as
    well, which would teach that classifier a PENDING run as a failure; V* mapped to its case
    through all the rows rather than the rows propose_batch was given (the one viable case, 47,
    lies after the withheld cases 37 and 39-41, so that misalignment names case 43); the
    withholding left out of the record and the notes; and the classifier recorded without the
    label that says its P(viable) is an uncalibrated vote fraction."""
    out = tmp_path / "out"
    code = bo_loop.main(_argv(ens, out, rules=("NPP>234", "NPP<235")))
    assert code == 3
    meta = _read(out)["meta"]
    assert meta["n_viable"] == 1 and meta["surrogate"] is None
    assert meta["labels"]["cases"]["viable"] == [47]
    clf = meta["cold_start_classifier"]
    assert clf["registry_name"] == "rf" and "uncalibrated" in clf["p_viable_is"]
    assert meta["batching"] == "cold_start:feasibility_maximin(acquisition_classifier)"
    assert meta["diagnostics"]["n_observed"] == LABELLED
    unlabelled = len(COMPLETED_NONFINITE) + len(EXCLUDED)
    assert meta["unlabelled_rows"] == {"n": unlabelled, "handling": "withheld"}
    assert any(n.startswith(f"{unlabelled} case(s) with a design row but no label were withheld")
               for n in meta["notes"])
    assert meta["V_star"]["case"] == 47
    assert meta["V_star"]["value"] == pytest.approx(_true_V(47), rel=1e-12)
    assert meta["hull"] is None


def test_a_cold_start_whose_labelled_rows_are_all_viable_anchors_on_every_known_row(ens, tmp_path):
    """One COMPLETED viable case, 47; every other case is PENDING. No labelled failure exists, so
    no classifier can be fitted from labels, and the queued PENDING positions must still repel
    the maximin picks. Catches: the unlabelled rows withheld here too (picks then spread away
    from case 47 alone and can sit beside queued runs), and the unlabelled rows passed as
    non-viable labels (propose_batch would then fit a classifier that learns PENDING runs as
    failures). The picks must equal a greedy Euclidean maximin over the Sobol' scan against all
    48 known rows, computed here by brute force."""
    from scipy.stats import qmc

    d = _copy_ens(ens, tmp_path)

    def pend(rows, header):
        for r in rows:
            if r[0] not in ("0", "47"):
                r[1:] = ["PENDING", "nan", "nan", "nan"]
        return rows, header
    _mutate_y(d, pend)
    out = tmp_path / "out"
    code = bo_loop.main(_argv(d, out, rules=("NPP>1",), failed=False))
    assert code == 3
    meta = _read(out)["meta"]
    assert meta["labels"]["cases"]["viable"] == [47] and meta["surrogate"] is None
    assert meta["labels"]["counts"]["excluded"] == N_CASES - 1
    assert meta["unlabelled_rows"] == {"n": N_CASES - 1,
                                       "handling": "given_the_labelled_class:viable"}
    assert meta["batching"] == "cold_start:maximin"
    assert meta["cold_start_classifier"] is None
    assert meta["diagnostics"]["n_observed"] == KNOWN
    assert meta["n_dropped_near_unlabelled"] == 0
    assert meta["V_star"]["case"] == 47
    assert meta["V_star"]["value"] == pytest.approx(_true_V(47), rel=1e-12)

    scan = qmc.Sobol(d=3, scramble=True, seed=0).random(N_CAND)
    anchors = list((np.loadtxt(d / "X.txt") - LOWER) / (UPPER - LOWER))
    picks = []
    for _ in range(Q):
        dist = [min(float(np.sqrt(np.sum((c - a) ** 2))) for a in anchors) for c in scan]
        j = int(np.argmax(dist))
        picks.append(j)
        anchors.append(scan[j])
    M = np.loadtxt(out / bo_loop.MATRIX_FILE, ndmin=2)
    np.testing.assert_allclose(M, LOWER + scan[picks] * (UPPER - LOWER), rtol=1e-12, atol=0)


def test_a_cold_start_with_a_surrogate_says_its_hull_gate_was_not_applied(ens, tmp_path, capsys):
    """With 2-3 viable rows the surrogate is fitted, but its picks are maximin weighted by its
    P(viable), with no hull gate and no posterior scoring. Catches: the record presenting the hull
    threshold as if it had gated the batch, and a V-of-mean range of nan for the proposals set
    beside finite chance values."""
    out = tmp_path / "out"
    code = bo_loop.main(_argv(ens, out, rules=("NPP>600",)))
    assert code == 3
    printed = capsys.readouterr().out
    meta = _read(out)["meta"]
    assert meta["labels"]["cases"]["viable"] == [6, 8, 29] and meta["surrogate"] is not None
    assert meta["batching"].startswith("cold_start:feasibility_maximin(surrogate_viability)")
    assert meta["hull"]["applied"] is False and "NOT APPLIED" in meta["hull"]["note"]
    pl = meta["plausibility"]
    assert pl["n_proposals"] == Q
    assert "V_mean_min" not in pl and "V_mean_max" not in pl and "V_star" not in pl
    assert "not computed" in pl["V_mean_note"]
    assert "V_mean_min" not in printed and "recorded but not applied (cold start)" in printed


def test_more_picks_than_candidates_is_a_shortfall_exit_7(ens, tmp_path):
    """Catches: a short batch reported as complete."""
    out = tmp_path / "out"
    code = bo_loop.main(_argv(ens, out, "--q", "256"))
    assert code == 7
    meta = _read(out)["meta"]
    assert meta["outcome"] == "shortfall"
    assert 0 < meta["n_proposed"] < 256 and meta["shortfall"] == 256 - meta["n_proposed"]
    assert np.loadtxt(out / bo_loop.MATRIX_FILE, ndmin=2).shape == (meta["n_proposed"], 3)


def test_no_matrix_is_written_when_nothing_is_proposed_even_over_an_old_one(tmp_path):
    """Every viable row sits at one point, so the hull gate admits no candidate. Catches: an
    empty matrix written anyway (np.loadtxt reads it as shape (0,) and the materializer reports
    a column mismatch), and a matrix left by an earlier run surviving --force beside a record
    that says nothing was proposed."""
    d = tmp_path
    (d / "params.csv").write_text("name,pft,lower_bound,upper_bound\n"
                                  "A,1,10,20\nB,1,0.1,0.5\nC,0,100,300\n")
    (d / "targets.yaml").write_text(
        "targets:\n  NPP: {observed: 389.0, uncertainty: 0.36}\n"
        "  plant_C: {observed: 651.7, uncertainty: 0.35}\n"
        "  Fs: {observed: 6.2, uncertainty: 0.28}\n")
    U = np.random.default_rng(5).uniform(size=(12, 3))
    U[:6] = 0.5
    np.savetxt(d / "X.txt", LOWER + U * (UPPER - LOWER))
    _write_y(d / "Y.csv", [[c, "COMPLETED", 389 * (1 + 0.01 * c), 651.7, 6.2 * (1 + 0.02 * c)]
                           if c <= 6 else [c, "COMPLETED", 0.2, 1.0, 1.0]
                           for c in range(1, 13)])
    out = d / "out"
    out.mkdir()
    (out / bo_loop.MATRIX_FILE).write_text("1 2 3\n")
    code = bo_loop.main(["--x-matrix", str(d / "X.txt"), "--y-matrix", str(d / "Y.csv"),
                         "--param-list", str(d / "params.csv"),
                         "--targets", str(d / "targets.yaml"), "--only", "NPP,plant_C,Fs",
                         "--viable-if", "NPP>1", "--q", str(Q), "--n-cand", str(N_CAND),
                         "--out", str(out), "--dry-run", "--force"])
    assert code == 6
    assert not (out / bo_loop.MATRIX_FILE).exists()
    meta = _read(out)["meta"]
    assert meta["outcome"] == "all_out_of_hull" and meta["n_proposed"] == 0
    assert meta["outputs"]["proposal_matrix"] is None
    assert meta["materialisation_recipe"]["matrix"] is None
    assert len(list(csv.reader(_read(out)["table"].decode().splitlines()))) == 1


def test_a_refusal_exits_1_and_a_usage_error_exits_2(ens, tmp_path):
    """At the process level, since that is what a caller sees. Catches: a refusal that exits 0
    or loses its message, and an argument that is not type-checked by argparse."""
    proc = subprocess.run([sys.executable, str(REPO / "tools/bayesian_optimization/bo_loop.py"),
                           *_argv(ens, tmp_path / "o1", dry_run=False)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 1
    assert "REFUSING: --dry-run is required" in proc.stderr
    assert not (tmp_path / "o1").exists()

    with pytest.raises(SystemExit) as exc:
        bo_loop.main(_argv(ens, tmp_path / "o2", "--q", "eight"))
    assert exc.value.code == 2


def test_drop_picks_near_removes_only_the_pick_on_an_anchor_and_counts_it():
    """Catches: a pick that lands on an unlabelled case kept in the arrays, or removed from some
    per-pick arrays and not others."""
    ts = [Target("NPP", 389.0, 0.36)]
    X_obs = LOWER + np.array([[0.2, 0.2, 0.2], [0.8, 0.8, 0.8]]) * (UPPER - LOWER)
    prop = propose_batch(None, ts, LOWER, UPPER, X_obs, [np.nan, np.nan], [False, False], q=3,
                         n_cand=16, seed=0)
    assert len(prop.unit) == 3
    kept, n = bo_loop.drop_picks_near(prop, prop.unit[1:2], bo_loop.MIN_SEPARATION)
    assert n == 1 and kept.shortfall == prop.shortfall + 1
    assert np.array_equal(kept.unit, prop.unit[[0, 2]])
    assert np.array_equal(kept.native, prop.native[[0, 2]])
    for f in bo_loop._PER_PICK:
        assert len(getattr(kept, f)) == 2, f
    same, n0 = bo_loop.drop_picks_near(prop, np.array([[0.123, 0.456, 0.789]]),
                                       bo_loop.MIN_SEPARATION)
    assert n0 == 0 and same is prop


# =============================================================================
# Refusals
# =============================================================================

def _copy_ens(ens, tmp_path):
    d = tmp_path / "ens"
    shutil.copytree(ens, d)
    return d


def _mutate_x(d, fn):
    X = np.loadtxt(d / "X.txt")
    np.savetxt(d / "X.txt", fn(X))


def _mutate_y(d, fn, header=("case", "status", "NPP", "plant_C", "Fs")):
    rows = list(csv.reader((d / "Y.csv").read_text().splitlines()))[1:]
    rows, header = fn(rows, list(header))
    _write_y(d / "Y.csv", rows, header=header)


def _set_status(rows, header, case, status):
    for r in rows:
        if int(r[0]) == case:
            r[1] = status
    return rows, header


def _setup_no_dry_run(d, out):
    return _argv(d, out, dry_run=False)


def _setup_column_mismatch(d, out):
    _mutate_x(d, lambda X: np.hstack([X, np.full((len(X), 1), 0.5)]))
    return _argv(d, out)


def _setup_nonempty_out(d, out):
    out.mkdir()
    (out / "keep.txt").write_text("an earlier result\n")
    return _argv(d, out)


def _setup_unknown_rule_name(d, out):
    return _argv(d, out, rules=("NPP>1", "npp>1"))


def _setup_no_viability_rule(d, out):
    return _argv(d, out, rules=())


def _setup_finite_only_and_rules(d, out):
    return _argv(d, out, "--viable-if-finite-only")


def _setup_non_numeric_threshold(d, out):
    return _argv(d, out, rules=("NPP>1", "Fs<abc"))


def _setup_nonfinite_threshold(d, out):
    return _argv(d, out, rules=("NPP>nan",))


def _setup_baseline_case_not_in_the_y_matrix(d, out):
    return _argv(d, out, "--baseline-case", "5")


def _setup_running_uncorroborated(d, out):
    return _argv(d, out, failed=False)


def _setup_missing_status_column(d, out):
    _mutate_y(d, lambda rows, h: ([[r[0]] + r[2:] for r in rows], [h[0]] + h[2:]))
    return _argv(d, out)


def _setup_unknown_status(d, out):
    _mutate_y(d, lambda rows, h: _set_status(rows, h, 10, "DONE"))
    return _argv(d, out)


def _setup_case_out_of_range(d, out):
    _mutate_y(d, lambda rows, h: (rows + [["99", "COMPLETED", "389", "651.7", "6.2"]], h))
    return _argv(d, out)


def _setup_x_outside_bounds(d, out):
    def fn(X):
        X[4, 0] = 25.0
        return X
    _mutate_x(d, fn)
    return _argv(d, out)


def _setup_unknown_binary_label(d, out):
    (d / "manifest.json").write_text(json.dumps({"archives": [
        {"label": "real_bin", "sha256": "ab" * 32, "binary": "model.x"}]}))
    return _argv(d, out, "--training-binary", "no_such_bin",
                 "--binary-manifest", str(d / "manifest.json"))


def _setup_salib_bounds_mismatch(d, out):
    from phases.phase0_design.create_parameter_sample import write_problem_text
    upper = UPPER.copy()
    upper[1] = 0.6
    write_problem_text(d / "salib.txt", "sobol", {"seed": 1}, ["A_1", "B_1", "C"], LOWER, upper)
    return _argv(d, out, "--salib-problem", str(d / "salib.txt"))


def _setup_salib_names_mismatch(d, out):
    from phases.phase0_design.create_parameter_sample import write_problem_text
    write_problem_text(d / "salib.txt", "sobol", {"seed": 1}, ["A_1", "C", "B_1"], LOWER, UPPER)
    return _argv(d, out, "--salib-problem", str(d / "salib.txt"))


REFUSALS = {
    # name: (setup, message the refusal must carry)
    "no_dry_run": (_setup_no_dry_run, r"--dry-run is required"),
    "column_mismatch": (_setup_column_mismatch, r"has 4 columns but the parameter list has 3"),
    "nonempty_out": (_setup_nonempty_out, r"is not empty"),
    "unknown_rule_name": (_setup_unknown_rule_name, r"\['npp'\], which are not among the --only"),
    "no_viability_rule": (_setup_no_viability_rule, r"no viability rule"),
    "finite_only_and_rules": (_setup_finite_only_and_rules,
                              r"--viable-if rules or --viable-if-finite-only, not both"),
    "non_numeric_threshold": (_setup_non_numeric_threshold,
                              r"--viable-if 'Fs<abc': the threshold is not a number"),
    "nonfinite_threshold": (_setup_nonfinite_threshold,
                            r"--viable-if 'NPP>nan': the threshold is not a finite number"),
    "baseline_case_not_in_the_y_matrix": (
        _setup_baseline_case_not_in_the_y_matrix,
        r"outside the 48-row design matrix under the 1-based convention \(first few: \[0\]\)\. "
        r".*the baseline case is not 5\."),
    "running_uncorroborated": (_setup_running_uncorroborated, r"1 RUNNING row\(s\) \(first cases "
                                                              r"\[38\]\)"),
    "missing_status_column": (_setup_missing_status_column, r"has no `status` column"),
    "unknown_status": (_setup_unknown_status, r"\(10, 'DONE'\)"),
    "case_out_of_range": (_setup_case_out_of_range, r"outside the 48-row design matrix"),
    "x_outside_bounds": (_setup_x_outside_bounds, r"lie outside the parameter-list bounds \(first "
                                                  r"design rows \[5\]"),
    "unknown_binary_label": (_setup_unknown_binary_label, r"'no_such_bin' is not in"),
    "salib_bounds_mismatch": (_setup_salib_bounds_mismatch, r"B_1 upper bound 0\.6 differs"),
    "salib_names_mismatch": (_setup_salib_names_mismatch,
                             r"declares parameters \['A_1', 'C', 'B_1'\]"),
}


@pytest.mark.parametrize("name", sorted(REFUSALS))
def test_refusals_carry_their_reason_and_write_nothing(ens, tmp_path, name):
    """One refusal per check, each with the message that names it. Catches the removal of any
    one check: the run then either proceeds or fails somewhere else, with another message.
    Nothing may be written into --out by a refused run."""
    setup, message = REFUSALS[name]
    d = _copy_ens(ens, tmp_path)
    out = tmp_path / "out"
    argv = setup(d, out)
    with pytest.raises(SystemExit) as exc:
        bo_loop.main(argv)
    assert isinstance(exc.value.code, str) and exc.value.code.startswith("REFUSING: ")
    assert re.search(message, exc.value.code), exc.value.code
    assert not (out / bo_loop.META_FILE).exists()
    assert not (out / bo_loop.MATRIX_FILE).exists()
