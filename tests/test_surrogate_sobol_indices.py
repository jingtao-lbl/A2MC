"""Tests for ``scripts/surrogate_sobol_indices.py`` — Sobol' indices via a surrogate.

The script's whole claim is that indices computed from a Saltelli design pushed through a
FITTED SURROGATE are usable when the ensemble itself was space-filling. That claim is checkable
rather than plausible: the Ishigami function has analytic first-order and total indices, so a
test can assert recovery against a known answer instead of against a previous run's output.

Two things are tested separately, because they fail for different reasons and conflating them
is how a broken surrogate gets read as a broken analyzer:

1. the ESTIMATOR path (design + analyze) on the true function -- must be near-exact;
2. the SURROGATE path on the same design -- must recover the RANKING, which is what a screen
   uses, at an accuracy the tests pin down rather than assume.

Every test also asserts a way the script must REFUSE, since the accuracy gate is the part that
protects a downstream reader ([[feedback_a_check_that_cannot_fail]]).
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec  # noqa: E402
from models.surrogate.tiers import S1Surrogate                           # noqa: E402

SALib = pytest.importorskip("SALib")

A, B = 7.0, 0.1


def ishigami(X):
    return np.sin(X[:, 0]) + A * np.sin(X[:, 1]) ** 2 + B * (X[:, 2] ** 4) * np.sin(X[:, 0])


def ishigami_analytic():
    """Closed-form S1 and ST for a=7, b=0.1 on U(-pi, pi)^3 (Sobol' & Levitan)."""
    V1 = 0.5 * (1 + B * np.pi ** 4 / 5) ** 2
    V2 = A ** 2 / 8
    VT = A ** 2 / 8 + B * np.pi ** 4 / 5 + B ** 2 * np.pi ** 8 / 18 + 0.5
    tail = 8 * B ** 2 * np.pi ** 8 / 225
    S1 = np.array([V1 / VT, V2 / VT, 0.0])
    ST = np.array([(V1 + tail) / VT, V2 / VT, tail / VT])
    return S1, ST


def _problem():
    return {"num_vars": 3, "names": ["x1", "x2", "x3"],
            "bounds": [[-np.pi, np.pi]] * 3}


def _spec():
    return SurrogateSpec(name="ishigami", use_mode="offline_search", tier="S1",
                         input_names=("x1", "x2", "x3"),
                         input_lower=(-np.pi,) * 3, input_upper=(np.pi,) * 3,
                         targets=(TargetSpec(name="y"),),
                         provenance=Provenance(model="synthetic"))


def test_analytic_reference_matches_published_values():
    """Guard the REFERENCE itself.

    Every other assertion here is measured against these numbers, so a typo in the closed form
    would make the whole file agree with the wrong answer. The published Ishigami values are
    S1 = (0.3139, 0.4424, 0) and ST = (0.5576, 0.4424, 0.2437).
    """
    S1, ST = ishigami_analytic()
    assert S1 == pytest.approx([0.3139, 0.4424, 0.0], abs=1e-3)
    assert ST == pytest.approx([0.5576, 0.4424, 0.2437], abs=1e-3)


def test_estimator_path_is_near_exact_on_the_true_function():
    """The design + analyze machinery, with the surrogate taken out of the picture.

    If this drifts, the fault is in the sampling or the analyzer call, NOT in any surrogate --
    which is exactly the distinction the two-test split exists to preserve.
    """
    from SALib.analyze import sobol as sobol_analyze
    from SALib.sample import sobol as sobol_sample

    problem = _problem()
    X = sobol_sample.sample(problem, 4096, calc_second_order=False, scramble=True, seed=1)
    res = sobol_analyze.analyze(problem, ishigami(X), calc_second_order=False,
                                print_to_console=False, seed=1)
    S1_true, ST_true = ishigami_analytic()
    assert np.max(np.abs(np.array(res["S1"]) - S1_true)) < 0.01
    assert np.max(np.abs(np.array(res["ST"]) - ST_true)) < 0.01


def test_surrogate_path_recovers_the_ranking_and_the_inert_input():
    """The architecture's real claim: a surrogate trained on a SPACE-FILLING sample supports a
    screen.

    Asserted at screen strength, not at estimator strength. x3 has zero FIRST-order effect but a
    substantial TOTAL effect (0.244) purely through its interaction with x1 -- recovering that
    is the property that distinguishes a genuine Sobol' screen from a feature-importance
    ranking, and it is the reason this path exists rather than calling ``model.sensitivity()``.
    """
    from SALib.analyze import sobol as sobol_analyze
    from SALib.sample import sobol as sobol_sample
    from scipy.stats import qmc

    problem, spec = _problem(), _spec()
    Xtr = qmc.scale(qmc.Sobol(d=3, scramble=True, seed=7).random(2048),
                    [-np.pi] * 3, [np.pi] * 3)
    model = S1Surrogate(spec, learner="rf").fit(Xtr, ishigami(Xtr).reshape(-1, 1))

    X = sobol_sample.sample(problem, 2048, calc_second_order=False, scramble=True, seed=1)
    y = model.predict_batch(X).values[:, 0]
    res = sobol_analyze.analyze(problem, y, calc_second_order=False,
                                print_to_console=False, seed=1)
    S1_true, ST_true = ishigami_analytic()
    S1, ST = np.array(res["S1"]), np.array(res["ST"])

    # x2 dominates S1, x1 dominates ST -- the ordering a screen acts on.
    assert np.argmax(S1) == 1
    assert np.argmax(ST) == 0
    # x3 is inert at first order but NOT in total: the interaction must survive.
    assert S1[2] < 0.10
    assert ST[2] > 0.10
    # Quantitative accuracy is real but loose; pinned so a regression is visible.
    assert np.max(np.abs(ST - ST_true)) < 0.15


def test_refuses_without_an_accuracy_report(tmp_path):
    """The gate must FAIL, not warn.

    Indices from an unvalidated surrogate are indistinguishable downstream from good ones, so
    the script exits non-zero rather than printing a caveat above its own output.
    """
    from scripts.surrogate_sobol_indices import load_accuracy_gate

    with pytest.raises(SystemExit) as e:
        load_accuracy_gate(None, allow_missing=False)
    assert "REFUSING" in str(e.value)


def test_refuses_a_failed_accuracy_report(tmp_path):
    """A report that exists but records passed=False must not be read as evidence."""
    from scripts.surrogate_sobol_indices import load_accuracy_gate

    p = tmp_path / "acc.json"
    p.write_text(json.dumps({"passed": False, "summary": "coverage 0.41 below 0.90"}))
    with pytest.raises(SystemExit) as e:
        load_accuracy_gate(str(p), allow_missing=False)
    assert "passed=False" in str(e.value)


def test_explicit_override_is_recorded_as_unsupported(tmp_path):
    """--no-accuracy-gate is allowed, but the output must carry the stamp.

    An ungated run that looked identical to a gated one in its provenance would defeat the gate
    by the back door.
    """
    from scripts.surrogate_sobol_indices import load_accuracy_gate

    g = load_accuracy_gate(None, allow_missing=True)
    assert g["gated"] is False
    assert "NOT supported" in g["note"]


def test_a_passing_report_alone_is_NOT_sufficient(tmp_path):
    """Contract changed 2026-08-27: metrics are necessary, promotion is what authorises.

    This test previously asserted that a passing report was accepted, and it correctly went red
    when the human gate landed. Passing metrics measure SKILL; they cannot see whether the training
    region contains the answer, whether the response is physically plausible, or whether the split
    was optimistic. Those decide whether a surrogate may steer a search, and they are judgements.
    """
    from scripts.surrogate_sobol_indices import load_accuracy_gate

    p = tmp_path / "acceptance.json"
    p.write_text(json.dumps({"passed": True, "summary": "all criteria met"}))
    with pytest.raises(SystemExit) as e:
        load_accuracy_gate(str(p), allow_missing=False)
    assert "not PROMOTED" in str(e.value)


def test_a_promoted_surrogate_is_accepted(tmp_path):
    """The complement: with a human promotion bound to this report, it proceeds.

    A gate that only ever refuses would be as useless as one that only ever passes.
    """
    from scripts.surrogate_sobol_indices import load_accuracy_gate
    from tools.promote_surrogate import PROMOTION_FILE, _acceptance

    p = tmp_path / "acceptance.json"
    p.write_text(json.dumps({"passed": True, "summary": "all criteria met"}))
    _, digest = _acceptance(tmp_path)
    (tmp_path / PROMOTION_FILE).write_text(json.dumps(
        {"promoted": True, "promoted_at": "2026-08-27T00:00:00", "reviewed_by": "tester",
         "basis": "checked the response is monotonic in the rate constants",
         "acceptance_sha": digest}))
    g = load_accuracy_gate(str(p), allow_missing=False)
    assert g["gated"] is True and g["passed"] is True and g["promoted"] is True


def test_a_promotion_does_not_survive_a_refit(tmp_path):
    """An approval is bound to the report it was granted against, by content hash.

    Without this, re-fitting a surrogate would silently inherit the previous approval -- the
    approval would describe a model that no longer exists.
    """
    from scripts.surrogate_sobol_indices import load_accuracy_gate
    from tools.promote_surrogate import PROMOTION_FILE

    p = tmp_path / "acceptance.json"
    p.write_text(json.dumps({"passed": True, "summary": "v1"}))
    (tmp_path / PROMOTION_FILE).write_text(json.dumps(
        {"promoted": True, "acceptance_sha": "0000000000000000", "basis": "stale"}))
    with pytest.raises(SystemExit) as e:
        load_accuracy_gate(str(p), allow_missing=False)
    assert "STALE" in str(e.value)
