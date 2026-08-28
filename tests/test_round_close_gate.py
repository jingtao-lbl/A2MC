"""Every rule of `_check_round_close` fires, and a complete round is clean.

Written failure-first (`feedback_a_check_that_cannot_fail`). The gap this closes, from audit
`20260824c` G4: `check_workflow_state_offline.py` reported ALL-CLEAN on a round that closed with
no deliverables, because nothing recorded whether they existed. A validator that cannot fail on
the thing it was built for is not a validator.

The severity split is the subtle part and has its own tests. Two sibling checks in the same file
are WARN-only on purpose -- erroring would block the state write a phase transition depends on.
That argument covers a round IN PROGRESS but not a state that is provably inconsistent, so the
ERRORs key on conditions visible in the round's OWN state: `housekeeping` recorded without a
`round_close` (the steps ran out of order), `converged` with no round close at all, and a report
pointer that does not resolve. Everything historical WARNS, because retro-failing two rounds
closed in July would block unrelated commits and teach people to reach for --no-verify.

A branch was removed while writing these: the first draft errored when "a later round exists"
and exempted SUPERSEDED rounds, which are the same condition -- so the ERROR was unreachable and
the check could not fail on the case it was built for.
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "_csw", ROOT / "tools" / "check_workflow_state_offline.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CSW = _mod()

REPORT = "use_cases/EcoSIM_BioCON/reports/20260823f_R3_ROUND_SUMMARY/R3_round_summary.md"


def base_state(rnd=1, **over):
    d = {
        "schema": "a2mc.offline_workflow_state.v1",
        "site": "T", "calibration_round": rnd, "current_phase": "refinement",
        "experiment_count": 10, "skip_testing_count": 0, "converged": False,
        "max_experiments": 10, "decisions": [], "open_threads": [],
        "evidence": {"diagnoses": [], "hypotheses": [], "experiments": []},
        "round_close": None, "housekeeping": None, "phase6_decision": None,
    }
    d.update(over)
    return d


def write(tmp_path, d, rnd=None):
    rnd = rnd if rnd is not None else d["calibration_round"]
    p = tmp_path / f"workflow_state_offline_r{rnd:02d}.json"
    p.write_text(json.dumps(d))
    return p


def check(tmp_path, d, rnd=None):
    return CSW._check_round_close(str(write(tmp_path, d, rnd)), d)


# --------------------------------------------------------------- the round close itself

def test_a_closed_round_with_no_deliverables_is_reported(tmp_path):
    """THE gap from 20260824c G4: this used to report clean."""
    errs, warns = check(tmp_path, base_state())
    assert any("no `round_close` is recorded" in m for m in errs + warns)


def test_a_complete_round_is_clean(tmp_path):
    d = base_state(
        round_close={"report_path": REPORT, "closed_at": "2026-08-23",
                     "steps": {"summarize": True, "compare": True, "report": True}},
        housekeeping={"done_at": "2026-08-23", "kb_curated": True})
    errs, warns = check(tmp_path, d)
    assert errs == [], errs
    assert warns == [], warns


def test_an_unresolvable_report_pointer_is_an_ERROR(tmp_path):
    """A pointer to nothing is worse than no pointer: it READS as evidence."""
    d = base_state(round_close={"report_path": "reports/nope/does_not_exist.md",
                                "closed_at": "2026-08-23",
                                "steps": {"summarize": True, "compare": True, "report": True}},
                   housekeeping={"done_at": "x"})
    errs, _ = check(tmp_path, d)
    assert any("does not resolve" in e for e in errs), errs


def test_an_empty_report_pointer_is_an_ERROR(tmp_path):
    d = base_state(round_close={"report_path": "", "closed_at": "x",
                                "steps": {"summarize": True, "compare": True, "report": True}},
                   housekeeping={"done_at": "x"})
    errs, _ = check(tmp_path, d)
    assert any("empty report_path" in e for e in errs), errs


def test_a_skipped_middle_step_is_named(tmp_path):
    """`compare-calibration-rounds` is the step that gets skipped, and skipping it is how a
    round summary re-proposed two parameters earlier rounds had already refuted."""
    d = base_state(round_close={"report_path": REPORT, "closed_at": "x",
                                "steps": {"summarize": True, "compare": False, "report": True}},
                   housekeeping={"done_at": "x"})
    _, warns = check(tmp_path, d)
    assert any("compare" in w for w in warns), warns


# --------------------------------------------------------------- severity: WARN vs ERROR

def test_it_only_WARNS_while_the_close_is_still_current(tmp_path):
    """A round in progress must not be blocked on a bookkeeping artifact -- that is how gates
    get bypassed wholesale."""
    errs, warns = check(tmp_path, base_state())
    assert errs == [], errs
    assert warns, "a closing round with no round_close should at least warn"


def test_housekeeping_without_a_round_close_is_an_ERROR(tmp_path):
    """Rule 2, and the replacement for a branch that COULD NOT FIRE.

    The first draft errored when "a later round's state file exists" and exempted SUPERSEDED
    rounds -- the same condition, so the error was unreachable and the check could not fail on
    the case it was written for. This condition is observable from the round's own state: the
    later step ran and the earlier one did not, which is provably out of order.
    """
    d = base_state(housekeeping={"done_at": "x", "kb_curated": True})
    errs, _ = check(tmp_path, d)
    assert any("out of order" in e for e in errs), errs


def test_converged_with_no_round_close_is_an_ERROR(tmp_path):
    """Rule 3. A converged round is the CAMPAIGN's terminal -- nothing downstream will produce
    the report if this moment does not."""
    d = base_state(converged=True, current_phase="testing")
    errs, _ = check(tmp_path, d)
    assert any("converged" in e.lower() for e in errs), errs


def test_a_SUPERSEDED_round_never_errors(tmp_path):
    """The retro-fail trap. Rounds closed before this contract existed carry a real debt, but
    blocking every commit on a round finished in July teaches people to use --no-verify.

    Note this state would ERROR under rule 2 if it were ACTIVE (housekeeping without a round
    close), which is what makes the exemption meaningful rather than vacuous.
    """
    d1 = base_state(rnd=1, phase6_decision={"decision": "redesign_6to0"},
                    housekeeping={"done_at": "x"})
    write(tmp_path, base_state(rnd=2), rnd=2)
    write(tmp_path, base_state(rnd=3), rnd=3)          # r1 is now superseded twice over
    errs, warns = CSW._check_round_close(str(write(tmp_path, d1, rnd=1)), d1)
    assert errs == [], errs
    assert warns, "the debt must stay VISIBLE even when it does not block"


# --------------------------------------------------------------- housekeeping

def test_redesign_without_housekeeping_stays_VISIBLE(tmp_path):
    """The measured failure: three rounds opened a new Phase 0 with the previous round's
    knowledge uncurated -- thirty experiment cycles, and an empty site KB.

    It WARNS rather than errors, deliberately. Erroring would retro-fail two rounds closed in
    July and block every unrelated commit, and the fix for that debt is scheduled work (the
    post-round housekeeping skill), not a gate. What matters is that it cannot go quiet.
    """
    d = base_state(rnd=1, phase6_decision={"decision": "redesign_6to0"},
                   round_close={"report_path": REPORT, "closed_at": "x",
                                "steps": {"summarize": True, "compare": True, "report": True}})
    write(tmp_path, base_state(rnd=2), rnd=2)
    errs, warns = CSW._check_round_close(str(write(tmp_path, d, rnd=1)), d)
    assert errs == [], errs
    assert any("housekeeping" in w for w in warns), warns


def test_a_converged_round_is_still_asked_for_housekeeping(tmp_path):
    """PI 2026-08-25: convergence is the CAMPAIGN boundary and skips nothing."""
    d = base_state(converged=True, current_phase="testing",
                   round_close={"report_path": REPORT, "closed_at": "x",
                                "steps": {"summarize": True, "compare": True, "report": True}})
    _, warns = check(tmp_path, d)
    assert any("housekeeping" in w for w in warns), warns


# --------------------------------------------------------------- mid-round, and the guard

def test_a_MID_ROUND_refinement_is_not_treated_as_a_close(tmp_path):
    """Phase 6 runs every cycle. Demanding a round report ten times per round would make the
    check noise, and noise gets tuned out."""
    errs, warns = check(tmp_path, base_state(experiment_count=3))
    assert errs == [] and warns == [], (errs, warns)


def test_a_rethink_is_not_a_close(tmp_path):
    d = base_state(experiment_count=3, phase6_decision={"decision": "rethink_6to3"})
    errs, warns = check(tmp_path, d)
    assert errs == [] and warns == [], (errs, warns)


def test_the_anti_silent_pass_guard_fires_when_the_key_vanishes(tmp_path):
    """If `round_close` were renamed, every rule above would stop matching and this checker
    would report clean forever (`feedback_exact_strings_are_contracts`)."""
    p_with = write(tmp_path, base_state(
        round_close={"report_path": REPORT, "closed_at": "x", "steps": {}}), rnd=1)
    assert CSW._check_any_round_close_exists([str(p_with)]) == []
    p_without = write(tmp_path, base_state(rnd=2), rnd=2)
    assert CSW._check_any_round_close_exists([str(p_without)]), \
        "with no round_close anywhere the guard must speak up"


def test_the_live_tree_still_validates():
    """The real states must not be broken by this check -- exit 0, warnings allowed."""
    import subprocess, sys
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_workflow_state_offline.py")],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr


# --------------------------------------------------------------- T6.3: the site KB

def _case(tmp_path, stores=None, **over):
    """A case tree: <case>/memory/workflow_state_offline_rNN.json and gained_knowledge/."""
    mem = tmp_path / "C" / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    if stores is not None:
        gk = mem / "gained_knowledge"
        gk.mkdir(exist_ok=True)
        for name, n in stores.items():
            payload = {name: ([{"id": i} for i in range(n)] if name != "parameters"
                              else {f"p{i}": {} for i in range(n)}), "_comment": "x"}
            (gk / f"{name}.json").write_text(json.dumps(payload))
    d = base_state(**over)
    p = mem / f"workflow_state_offline_r{d['calibration_round']:02d}.json"
    p.write_text(json.dumps(d))
    return str(p), d


def test_an_empty_site_kb_after_a_closed_round_is_reported(tmp_path):
    """THE measured failure: thirty experiment cycles, three closed rounds, an empty store.

    Checked as a CONSEQUENCE rather than as a mention in a log. A rule satisfied by typing a word
    is satisfied without doing the work; a store with nothing in it cannot be faked.
    """
    path, d = _case(tmp_path, stores={"discoveries": 0, "experiments": 0,
                                      "parameters": 0, "failed_approaches": 0})
    out = CSW._check_site_kb_populated(path, d)
    assert out and "EMPTY" in out[0], out


def test_a_populated_site_kb_is_quiet(tmp_path):
    path, d = _case(tmp_path, stores={"discoveries": 3, "experiments": 2,
                                      "parameters": 5, "failed_approaches": 4})
    assert CSW._check_site_kb_populated(path, d) == []


def test_a_partially_curated_kb_names_the_empty_stores(tmp_path):
    """A round that refuted levers and recorded zero failed_approaches did not curate them."""
    path, d = _case(tmp_path, stores={"discoveries": 5, "experiments": 0,
                                      "parameters": 0, "failed_approaches": 0})
    out = CSW._check_site_kb_populated(path, d)
    assert out and "failed_approaches" in out[0], out


def test_a_missing_gained_knowledge_dir_is_reported(tmp_path):
    path, d = _case(tmp_path, stores=None)
    out = CSW._check_site_kb_populated(path, d)
    assert out and "does not exist" in out[0], out


def test_a_young_case_that_has_closed_NOTHING_is_not_nagged(tmp_path):
    """A round in progress legitimately has an empty store; nagging it is how a check becomes
    noise and gets tuned out."""
    path, d = _case(tmp_path, stores={"discoveries": 0, "experiments": 0,
                                      "parameters": 0, "failed_approaches": 0},
                    experiment_count=2)          # mid-round, limit is 10
    assert CSW._check_site_kb_populated(path, d) == []


# --------------------------------------------------------------- T10.2: the Phase-7 deliverable

def _converged(**over):
    d = base_state(converged=True, current_phase="testing",
                   round_close={"report_path": REPORT, "closed_at": "x",
                                "steps": {"summarize": True, "compare": True, "report": True}},
                   housekeeping={"done_at": "x", "kb_curated": True})
    d.update(over)
    return d


def test_converged_with_no_final_configuration_is_an_ERROR(tmp_path):
    """A converged round is the CAMPAIGN's terminal: no later step will produce the artifact.

    Until 2026-08-25 three skills stated this deliverable in the same seven words and NOTHING
    specified what it was, so a campaign could converge with its actual product unrecorded.
    """
    errs, _ = check(tmp_path, _converged())
    assert any("no `final_configuration`" in e for e in errs), errs


def test_an_unresolvable_final_configuration_pointer_is_an_ERROR(tmp_path):
    d = _converged(final_configuration={"path": "reports/nope/final_configuration.md",
                                        "reproduce_command": "x", "archived_binary": "/archive/e"})
    errs, _ = check(tmp_path, d)
    assert any("does not resolve" in e for e in errs), errs


def test_a_complete_final_configuration_is_clean(tmp_path):
    d = _converged(final_configuration={
        "path": REPORT,                       # any resolvable file, for the pointer test
        "reproduce_command": "source a2mc_config.sh && ./run.sh case_1174",
        "archived_binary": "/archive/binaries/ecosim_2aa31c6d"})
    errs, warns = check(tmp_path, d)
    assert errs == [], errs
    assert warns == [], warns


def test_a_LIVE_BUILD_binary_path_is_flagged(tmp_path):
    """The build tree is shared and every build overwrites it in place; a queued job resolves its
    exe at RUN time. Recording the live path ties the result to whatever is there later."""
    d = _converged(final_configuration={
        "path": REPORT, "reproduce_command": "x",
        "archived_binary": "/global/cfs/.../E3SM_FATES_api43/bld/e3sm.exe"})
    _, warns = check(tmp_path, d)
    assert any("LIVE BUILD" in w for w in warns), warns


def test_a_missing_reproduce_command_is_flagged(tmp_path):
    d = _converged(final_configuration={"path": REPORT, "reproduce_command": "",
                                        "archived_binary": "/archive/e"})
    _, warns = check(tmp_path, d)
    assert any("reproduce_command" in w for w in warns), warns


def test_an_UNCONVERGED_round_is_not_asked_for_one(tmp_path):
    """The deliverable is terminal. Demanding it from every closing round would make it noise."""
    d = base_state(round_close={"report_path": REPORT, "closed_at": "x",
                                "steps": {"summarize": True, "compare": True, "report": True}},
                   housekeeping={"done_at": "x"})
    errs, warns = check(tmp_path, d)
    assert not any("final_configuration" in m for m in errs + warns), (errs, warns)
