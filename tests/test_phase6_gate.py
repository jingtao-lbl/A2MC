"""Tests for the Phase-6 objective gate (docs/34) — WorkflowStateOffline.validate_phase6_decision.

The gate makes the offline agent restate the objective before it can escalate, so "stop → improve
the model" cannot be the path of least resistance (failure mode FM-2). tmp_path stays under the repo
tmp/ via pytest.ini --basetemp.
"""
from tools.workflow_state_offline import WorkflowStateOffline


def _state(ec, tmp_path):
    st = WorkflowStateOffline(site_dir=str(tmp_path), calibration_round=5)
    st.data["experiment_count"] = ec
    return st


def test_stop_at_experiment_count_zero_with_named_experiment_is_blocked(tmp_path):
    """The exact FM-2 lapse: stop→model-dev at experiment_count=0 with a lever untested."""
    st = _state(0, tmp_path)
    st.set_phase6_decision("stop_model_dev", binding_target="biomass_pft10",
                           next_targeted_experiment="storage_cushion sweep", max_experiments=10)
    errs = st.validate_phase6_decision()
    assert errs, "stop at ec=0 with a named experiment must be blocked"
    assert any("rethink_6to3" in e for e in errs)


def test_stop_requires_binding_target(tmp_path):
    st = _state(10, tmp_path)
    st.set_phase6_decision("stop_model_dev", binding_target="",
                           next_targeted_experiment="NONE",
                           exhaustion_justification="all levers tried", max_experiments=10)
    assert any("binding_target" in e for e in st.validate_phase6_decision())


def test_stop_at_cap_with_none_and_justification_is_valid(tmp_path):
    st = _state(10, tmp_path)
    st.set_phase6_decision("stop_model_dev", binding_target="biomass_pft10",
                           next_targeted_experiment="NONE",
                           exhaustion_justification="all in-range levers exhausted",
                           max_experiments=10)
    assert st.validate_phase6_decision() == []


def test_stop_without_justification_is_blocked(tmp_path):
    st = _state(10, tmp_path)
    st.set_phase6_decision("stop_model_dev", binding_target="biomass_pft10",
                           next_targeted_experiment="NONE", exhaustion_justification="",
                           max_experiments=10)
    assert any("exhaustion_justification" in e for e in st.validate_phase6_decision())


def test_rethink_with_target_is_valid(tmp_path):
    st = _state(2, tmp_path)
    st.set_phase6_decision("rethink_6to3", binding_target="biomass_pft10",
                           next_targeted_experiment="storage_cushion sweep")
    assert st.validate_phase6_decision() == []


def test_converge_needs_no_target(tmp_path):
    st = _state(3, tmp_path)
    st.set_phase6_decision("converge")
    assert st.validate_phase6_decision() == []


def test_unset_decision_reports_violation(tmp_path):
    st = _state(0, tmp_path)
    assert st.validate_phase6_decision()  # not set -> a violation


def test_phase6_decision_round_trips(tmp_path):
    st = _state(4, tmp_path)
    st.set_phase6_decision("rethink_6to3", binding_target="t",
                           next_targeted_experiment="exp")
    st.save()
    reloaded = WorkflowStateOffline.load(calibration_round=5, site_dir=str(tmp_path))
    assert reloaded.data["phase6_decision"]["decision"] == "rethink_6to3"
    assert reloaded.validate_phase6_decision() == []


# ---------------------------------------------------------------- rethink at the loop limit

def test_rethink_below_the_limit_is_allowed(tmp_path):
    """The route is auto-taken while the budget holds -- the guard must not block the normal case."""
    st = _state(3, tmp_path)
    st.set_phase6_decision("rethink_6to3", binding_target="NPP",
                           next_targeted_experiment="RMOM ladder", max_experiments=10)
    assert st.validate_phase6_decision() == []


def test_rethink_at_the_last_cycle_is_allowed(tmp_path):
    """ec = mx - 1: the increment lands exactly ON the limit, which spends the last legal cycle."""
    st = _state(9, tmp_path)
    st.set_phase6_decision("rethink_6to3", binding_target="NPP",
                           next_targeted_experiment="RMOM ladder", max_experiments=10)
    assert st.validate_phase6_decision() == []


def test_rethink_at_the_limit_is_blocked(tmp_path):
    """MEASURED: at 21 of 21 the gate returned no errors and would have licensed a 22nd cycle.
    A rethink INCREMENTS the counter, so the guard has to test the post-increment value."""
    st = _state(10, tmp_path)
    st.set_phase6_decision("rethink_6to3", binding_target="NPP",
                           next_targeted_experiment="RMOM ladder", max_experiments=10)
    errs = st.validate_phase6_decision()
    assert errs, "a rethink at the loop limit must be blocked -- it would spend cycle 11 of 10"
    assert any("rethink_6to3" in e and "exhausted" in e for e in errs)


def test_rethink_past_the_limit_is_blocked(tmp_path):
    """A round already over budget (the PI granted an extra cycle and it was spent) blocks too."""
    st = _state(21, tmp_path)
    st.set_phase6_decision("rethink_6to3", binding_target="NPP",
                           next_targeted_experiment="RMOM ladder", max_experiments=21)
    assert any("rethink_6to3" in e for e in st.validate_phase6_decision())


def test_the_other_three_decisions_are_unaffected_at_the_limit(tmp_path):
    """MUTATION GUARD: a too-broad guard keyed on ec >= mx alone would also block the round CLOSE,
    which is the decision the limit is supposed to produce. Only rethink spends a cycle."""
    st = _state(10, tmp_path)
    st.set_phase6_decision("redesign_6to0", binding_target="NPP",
                           next_targeted_experiment="NONE", max_experiments=10)
    assert st.validate_phase6_decision() == []
    st.set_phase6_decision("converge", binding_target="", next_targeted_experiment="NONE",
                           max_experiments=10)
    assert st.validate_phase6_decision() == []
