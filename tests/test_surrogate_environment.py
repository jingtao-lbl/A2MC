"""Library-version stamps on a saved surrogate, and the loader that reads them back.

The gap this closes: a saved artifact recorded WHAT it was valid against (`Provenance`) and never
WHAT BUILT IT. A joblib pickle of a scikit-learn estimator is not guaranteed across a major version
bump, and a torch `state_dict` is not either, so an artifact could load after an upgrade and quietly
predict something else.

Every test asserts a way the check must FAIL or a way it must NOT, because a stamp that cannot
refuse is decoration ([[feedback_a_check_that_cannot_fail]]).
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from models.surrogate.environment import (ENVIRONMENT_FILE, capture_environment,   # noqa: E402
                                          check_environment, enforce_environment,
                                          read_environment, write_environment)
from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec            # noqa: E402
from models.surrogate.tiers import S0Surrogate, load                               # noqa: E402


def _spec(name="env_fixture"):
    return SurrogateSpec(
        name=name, tier="S0", use_mode="offline_search",
        input_names=("a", "b"), input_lower=(0.0, 0.0), input_upper=(1.0, 1.0),
        targets=[TargetSpec("y", observed=1.0)],
        provenance=Provenance(model="test", model_commit="abc123", param_list_hash="p",
                              base_param_file_hash="b", scoring_convention="sc",
                              training_ensemble_id="e", a2mc_version="v", created="2026-09-13"))


def _fitted(tmp_path):
    rng = np.random.default_rng(0)
    X = rng.uniform(0, 1, size=(40, 2))
    Y = (X[:, :1] * 2.0 + 0.1)
    m = S0Surrogate(_spec(), learner="ridge")
    m.fit(X, Y)
    d = tmp_path / "art"
    m.save(d)
    return d


# --------------------------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------------------------

def test_save_writes_the_stamp_and_it_names_the_libraries_actually_imported(tmp_path):
    d = _fitted(tmp_path)
    env = read_environment(d)
    assert env is not None, f"save() wrote no {ENVIRONMENT_FILE}"
    assert env["python"] == sys.version.split()[0]
    # sklearn and numpy fitted this artifact, so both must be recorded
    assert "numpy" in env["libraries"]
    assert "sklearn" in env["libraries"]


def test_it_records_what_was_IMPORTED_not_what_is_INSTALLED(monkeypatch):
    """The distinction that keeps an sklearn artifact from demanding torch.

    A pip-freeze-style stamp would record every installed package, so an S1 artifact fitted on a
    machine that happens to have torch would refuse to load on a machine that does not, for a
    library it never used.
    """
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    env = capture_environment()
    assert "torch" not in env["libraries"], (
        "torch was recorded although it was not imported; the stamp is reading the installed set")


# --------------------------------------------------------------------------------------------
# compare
# --------------------------------------------------------------------------------------------

def test_an_identical_environment_reports_nothing():
    assert check_environment(capture_environment()) == []


def test_a_MAJOR_library_bump_is_major():
    env = capture_environment()
    env["libraries"]["numpy"] = "1.26.4"          # current tree is numpy 2.x
    bad = check_environment(env)
    assert [m.library for m in bad] == ["numpy"]
    assert bad[0].severity == "major"


def test_a_MINOR_library_bump_is_minor_not_major():
    """Refusing on every difference would be refused-by-default after one `pip install -U`."""
    env = capture_environment()
    cur = env["libraries"]["numpy"]
    env["libraries"]["numpy"] = cur.split(".")[0] + ".0.0"
    bad = check_environment(env)
    assert bad and bad[0].severity == "minor", f"expected minor drift, got {bad}"


def test_a_library_that_has_GONE_MISSING_is_major():
    env = capture_environment()
    env["libraries"]["a_library_that_does_not_exist"] = "1.0"
    bad = check_environment(env)
    m = [x for x in bad if "does_not_exist" in x.library][0]
    assert m.severity == "major" and m.current is None


def test_a_python_MAJOR_change_is_major_and_a_patch_change_is_minor():
    env = capture_environment()
    env["python"] = "2.7.18"
    assert [m for m in check_environment(env) if m.library == "python"][0].severity == "major"
    env["python"] = sys.version.split()[0] + "9"
    assert [m for m in check_environment(env) if m.library == "python"][0].severity == "minor"


def test_no_recorded_environment_is_not_a_mismatch():
    """An unstamped artifact is UNPROTECTED, not wrong. Inventing a mismatch would be a lie."""
    assert check_environment(None) == []


# --------------------------------------------------------------------------------------------
# enforce, and the loader
# --------------------------------------------------------------------------------------------

def test_enforce_REFUSES_a_major_mismatch_under_strict(tmp_path):
    d = _fitted(tmp_path)
    env = read_environment(d)
    env["libraries"]["numpy"] = "1.26.4"
    (d / ENVIRONMENT_FILE).write_text(json.dumps(env))
    with pytest.raises(ValueError, match="environment mismatch"):
        enforce_environment(d, strict=True)


def test_enforce_only_WARNS_when_not_strict(tmp_path):
    d = _fitted(tmp_path)
    env = read_environment(d)
    env["libraries"]["numpy"] = "1.26.4"
    (d / ENVIRONMENT_FILE).write_text(json.dumps(env))
    with pytest.warns(RuntimeWarning, match="environment mismatch"):
        bad = enforce_environment(d, strict=False)
    assert any(m.severity == "major" for m in bad)


def test_a_MISSING_stamp_warns_rather_than_refusing(tmp_path):
    """Every artifact built before this existed has no stamp; hard-failing them makes the feature
    unadoptable on exactly the artifacts that most need auditing."""
    d = _fitted(tmp_path)
    (d / ENVIRONMENT_FILE).unlink()
    with pytest.warns(RuntimeWarning, match="carries no environment.json"):
        assert enforce_environment(d, strict=True) == []


def test_load_REFUSES_an_artifact_built_under_a_different_major(tmp_path):
    """The end-to-end contract: the gate is on the path a caller actually uses."""
    d = _fitted(tmp_path)
    env = read_environment(d)
    env["libraries"]["numpy"] = "1.26.4"
    (d / ENVIRONMENT_FILE).write_text(json.dumps(env))
    with pytest.raises(ValueError, match="environment mismatch"):
        load(d)


def test_load_still_works_on_a_matching_environment(tmp_path):
    d = _fitted(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("error")            # no warning at all on a clean artifact
        m = load(d)
    assert m.fitted
    assert m.predict_batch(np.array([[0.5, 0.5]])).values.shape == (1, 1)
