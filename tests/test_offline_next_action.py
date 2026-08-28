"""Unit tests for WorkflowStateOffline.resolve_next_action (docs/38 §4.3, T1).

Pure-state resolver: given a state, what is the next workflow action? Covers each runnable
phase, the converged short-circuit, the four Phase-6 fork branches, and the TWO round-close
positions added 2026-08-25.

`site_dir` is now explicit everywhere: the constructor no longer falls back to
`use_cases/TEMPLATE`, because `save()` would CREATE a state file there and a spurious template
state validates clean (T9.2).
"""
import pytest

from tools.workflow_state_offline import WorkflowStateOffline

SITE = "tmp/_resolver_tests"          # never written; the resolver is pure


def _st(round_closed=True, housekeeping_done=True, **position):
    """A blank in-memory state (no save).

    `round_closed` / `housekeeping_done` default TRUE so the pre-existing tests below keep
    asserting the branch they were written for rather than the new close positions. The
    close-position tests set them False explicitly.
    """
    st = WorkflowStateOffline(site_dir=SITE, calibration_round=1)
    if round_closed:
        st.set_round_close(report_path="reports/x/R1_round_summary.md")
    if housekeeping_done:
        st.set_housekeeping(kb_curated=True)
    if position:
        st.set_position(**position)
    return st


def test_runnable_phases_return_run_phase():
    for ph in ("design", "exploration", "screening", "diagnosis", "hypothesis", "testing"):
        na = _st(current_phase=ph).resolve_next_action()
        assert na.kind == "run_phase" and na.phase == ph, (ph, na)


def test_converged_short_circuits_to_done():
    na = _st(current_phase="testing", converged=True).resolve_next_action()
    assert na.kind == "done" and na.phase == "converged", na


def test_phase6_without_decision_is_a_gate():
    na = _st(current_phase="refinement").resolve_next_action()
    assert na.kind == "gate" and na.phase == "refinement", na


def test_phase6_converge_is_done():
    st = _st(current_phase="refinement")
    st.set_phase6_decision("converge")
    na = st.resolve_next_action()
    assert na.kind == "done", na


def test_phase6_rethink_routes_to_diagnosis():
    st = _st(current_phase="refinement")
    st.set_phase6_decision("rethink_6to3", binding_target="PFT10_leaf",
                           next_targeted_experiment="vmax_p sweep")
    na = st.resolve_next_action()
    assert na.kind == "run_phase" and na.phase == "diagnosis", na


def test_phase6_redesign_routes_to_design():
    """CONTRACT CHANGED 2026-08-25: only AFTER the round close and the housekeeping.

    This test previously asserted `redesign_6to0 -> run_phase(design)` directly. That route is
    what let three rounds open a new Phase 0 with the previous round's knowledge uncurated and
    its open questions unwritten. The direct edge is gone deliberately; the close-position tests
    below pin the two steps that now precede it.
    """
    st = _st(current_phase="refinement")
    st.set_phase6_decision(decision="redesign_6to0", binding_target="plant_C")
    na = st.resolve_next_action()
    assert na.kind == "run_phase" and na.phase == "design", na


def test_phase6_stop_model_dev_is_a_human_gate():
    st = _st(current_phase="refinement")
    st.set_phase6_decision("stop_model_dev", binding_target="PFT10_leaf",
                           next_targeted_experiment="NONE",
                           exhaustion_justification="all in-range experiments tried")
    na = st.resolve_next_action()
    assert na.kind == "gate" and na.phase == "refinement", na


def test_converged_beats_a_pending_phase6_gate():
    st = _st(current_phase="refinement", converged=True)
    na = st.resolve_next_action()
    assert na.kind == "done", na


def test_driver_walkthrough_phase0_to_converged():
    """Simulate the calibration-goal driver stepping resolve_next_action through a full loop:
    design→…→refinement (gate) → a rethink cycle back to diagnosis → converge (done)."""
    st = WorkflowStateOffline(site_dir=SITE, calibration_round=1)
    # phases 0-5 each resolve to run themselves
    for ph in ("design", "exploration", "screening", "diagnosis", "hypothesis", "testing"):
        st.set_position(current_phase=ph)
        assert st.resolve_next_action() == ("run_phase", ph, st.resolve_next_action().detail)
    # phase 6 with no decision → gate (the driver pauses for the human)
    st.set_position(current_phase="refinement")
    assert st.resolve_next_action().kind == "gate"
    # decision = rethink → route back to diagnosis; the driver then advances + clears the decision
    st.set_phase6_decision("rethink_6to3", binding_target="PFT10_leaf",
                           next_targeted_experiment="vmax_p sweep")
    assert st.resolve_next_action().phase == "diagnosis"
    st.set_position(current_phase="diagnosis", experiment_count=1)
    st.data["phase6_decision"] = None
    assert st.resolve_next_action() == ("run_phase", "diagnosis", st.resolve_next_action().detail)
    # second refinement → converge. The route to done now passes through BOTH close positions:
    # the round report first, then the housekeeping the cleared gate authorises. Nothing is
    # skipped on convergence (PI, 2026-08-25).
    st.set_position(current_phase="refinement")
    st.set_phase6_decision("converge")
    na = st.resolve_next_action()
    assert na.kind == "close" and na.phase == "round_close", na
    st.set_round_close(report_path="reports/20260717i_R1_ROUND_SUMMARY/R1_round_summary.md")
    na = st.resolve_next_action()
    assert na.kind == "close" and na.phase == "housekeeping", na
    st.set_housekeeping(kb_curated=True, scripts_reviewed=True)
    assert st.resolve_next_action().kind == "done"


# --------------------------------------------------------------------- round-close positions

def test_a_closing_round_writes_its_report_BEFORE_the_gate():
    """The whole point of two positions: the PI routes the round with its summary in hand."""
    st = _st(round_closed=False, current_phase="refinement")
    st.data["max_experiments"] = 10
    st.set_position(experiment_count=10)
    na = st.resolve_next_action()
    assert na.kind == "close" and na.phase == "round_close", na


def test_the_gate_follows_once_the_report_exists():
    st = _st(round_closed=True, current_phase="refinement")
    st.data["max_experiments"] = 10
    st.set_position(experiment_count=10)
    na = st.resolve_next_action()
    assert na.kind == "gate" and na.phase == "refinement", na


def test_mid_round_phase6_does_NOT_demand_a_round_close():
    """REGRESSION, and the bug the first draft of this routing had.

    Phase 6 runs at the end of EVERY experiment cycle. Keying the round close on
    `current_phase == 'refinement'` would demand a round report ten times per round.
    """
    st = _st(round_closed=False, current_phase="refinement")
    st.data["max_experiments"] = 10
    st.set_position(experiment_count=3)          # mid-round
    na = st.resolve_next_action()
    assert na.kind == "gate", na


def test_rethink_is_untouched_by_the_close_positions():
    """`rethink_6to3` is mid-round BY DEFINITION and must never route through a close."""
    st = _st(round_closed=False, housekeeping_done=False, current_phase="refinement")
    st.set_phase6_decision(decision="rethink_6to3", binding_target="plant_C")
    na = st.resolve_next_action()
    assert na.kind == "run_phase" and na.phase == "diagnosis", na


def test_housekeeping_runs_AFTER_the_gate_clears_never_before():
    """Curating knowledge is a Tier-3 write and one of the four human gates, so it cannot
    precede the gate. A single close position would have done exactly that."""
    st = _st(round_closed=True, housekeeping_done=False, current_phase="refinement")
    st.set_phase6_decision(decision="redesign_6to0", binding_target="plant_C")
    na = st.resolve_next_action()
    assert na.kind == "close" and na.phase == "housekeeping", na


def test_a_CONVERGED_round_still_runs_the_housekeeping():
    """PI, 2026-08-25, answering against the recommendation: convergence is the CAMPAIGN
    boundary. It hands work to nobody, so nothing is skipped -- the checklist gets FULLER."""
    st = _st(round_closed=True, housekeeping_done=False, current_phase="testing", converged=True)
    na = st.resolve_next_action()
    assert na.kind == "close" and na.phase == "housekeeping", na


def test_converged_reaches_done_only_after_both_positions():
    st = _st(round_closed=True, housekeeping_done=True, current_phase="testing", converged=True)
    na = st.resolve_next_action()
    assert na.kind == "done" and na.phase == "converged", na


def test_a_state_missing_both_records_does_not_crash():
    """Every state file written before 2026-08-25 lacks both keys; absent must read as
    'not done yet', never as an exception."""
    st = _st(round_closed=False, housekeeping_done=False, current_phase="refinement")
    st.data.pop("round_close", None)
    st.data.pop("housekeeping", None)
    st.data["max_experiments"] = 10
    st.set_position(experiment_count=10)
    na = st.resolve_next_action()
    assert na.kind == "close" and na.phase == "round_close", na


def test_an_unknown_experiment_limit_does_not_invent_a_close():
    """With no resolvable max_experiments, 'is the round closing?' is unanswerable -- and an
    unanswerable question must not be answered YES."""
    st = _st(round_closed=False, current_phase="refinement")
    st.data.pop("max_experiments", None)
    st.set_position(experiment_count=99)
    na = st.resolve_next_action()
    assert na.kind == "gate", na


# --------------------------------------------------------------------- T9: state safety

def test_constructor_refuses_to_blank_an_existing_round(tmp_path):
    """T9.1. Measured 2026-08-23: constructor-then-save turned 303 decisions into 8, and every
    invariant reported clean, because a state holding 8 decisions is structurally valid."""
    st = WorkflowStateOffline(site_dir=str(tmp_path), calibration_round=7)
    st.add_decision("a real finding")
    st.save()
    with pytest.raises(FileExistsError):
        WorkflowStateOffline(site_dir=str(tmp_path), calibration_round=7)
    assert len(WorkflowStateOffline.load(site_dir=str(tmp_path),
                                         calibration_round=7).data["decisions"]) == 1


def test_no_silent_template_fallback(monkeypatch):
    """T9.2. The fallback CREATED `use_cases/TEMPLATE/memory/...` on a mis-scoped call."""
    monkeypatch.delenv("A2MC_USE_CASE_DIR", raising=False)
    with pytest.raises(ValueError, match="TEMPLATE"):
        WorkflowStateOffline(calibration_round=1)
    with pytest.raises(ValueError, match="TEMPLATE"):
        WorkflowStateOffline.find_latest()


def test_save_refuses_to_shrink_the_decision_record(tmp_path):
    """T9.3. Validity cannot detect destruction; only history can."""
    st = WorkflowStateOffline(site_dir=str(tmp_path), calibration_round=2)
    st.add_decision("one"); st.add_decision("two"); st.save()
    st2 = WorkflowStateOffline.load(site_dir=str(tmp_path), calibration_round=2)
    st2.data["decisions"] = []
    with pytest.raises(ValueError, match="decisions would drop"):
        st2.save()
    st2.save(allow_shrink=True)          # the deliberate escape hatch still works


def test_save_refuses_to_clear_a_recorded_round_close(tmp_path):
    st = WorkflowStateOffline(site_dir=str(tmp_path), calibration_round=2)
    st.set_round_close(report_path="reports/x/R2_round_summary.md")
    st.save()
    st2 = WorkflowStateOffline.load(site_dir=str(tmp_path), calibration_round=2)
    st2.data["round_close"] = None
    with pytest.raises(ValueError, match="would be cleared"):
        st2.save()


def test_the_whole_close_sequence_holds_for_a_NON_ECOSIM_case(tmp_path):
    """END-TO-END, and model-agnostic on purpose.

    Every other test here drives the resolver one transition at a time, and the live states this
    was developed against are all EcoSIM's. The round close is this branch's main deliverable and
    the branch exists to generalize past one model, so the SEQUENCE -- not just each edge -- is
    walked here on a PFLOTRAN-shaped case: phases 0-5, the cycle limit, the report BEFORE the
    gate, the gate, the housekeeping AFTER it, and the next round opening.

    The order is the assertion. A refactor that kept every individual route correct but let the
    housekeeping precede the gate would pass every other test in this file and fail this one --
    and that inversion was the audit's own proposed design.
    """
    reports = tmp_path / "reports" / "20260825a_R1_ROUND_SUMMARY"
    reports.mkdir(parents=True)
    (reports / "R1_round_summary.md").write_text("# R1\n")

    st = WorkflowStateOffline(site_dir=str(tmp_path), calibration_round=1)
    st.data["max_experiments"] = 10

    for ph in ("design", "exploration", "screening", "diagnosis", "hypothesis", "testing"):
        st.set_position(current_phase=ph)
        assert st.resolve_next_action().kind == "run_phase"

    st.set_position(current_phase="refinement", experiment_count=10)
    na = st.resolve_next_action()
    assert (na.kind, na.phase) == ("close", "round_close"), na       # report first

    st.set_round_close(report_path=str(reports / "R1_round_summary.md"))
    assert st.resolve_next_action().kind == "gate"                    # THEN the human gate

    st.set_phase6_decision("redesign_6to0", binding_target="Mn", objective="o",
                           best_so_far="b", next_targeted_experiment="NONE", max_experiments=10)
    na = st.resolve_next_action()
    assert (na.kind, na.phase) == ("close", "housekeeping"), na       # housekeeping AFTER it

    st.set_housekeeping(kb_curated=True, scripts_reviewed=True)
    na = st.resolve_next_action()
    assert (na.kind, na.phase) == ("run_phase", "design"), na         # next round opens
