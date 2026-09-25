#!/usr/bin/env python3
"""Invariant checker for the offline resume state (`workflow_state_offline_r{RR}.json`).

The state analog of `tools/check_skill_registry.py`. The offline convergence loop is *state on
disk + resolve_next_action() + the phase skills* (see `calibration-goal`), so a corrupt or stale
state file silently misdrives the whole workflow. This validates the file the driver trusts:

  ERRORS (exit 1 — the state would misdrive the loop):
    - wrong `schema`; `current_phase` not a real phase; counters out of range / wrong type;
      `converged` not a bool; an `open_thread` with no `id`; a `phase6_decision` that fails
      `validate_phase6_decision()` (e.g. a premature stop_model_dev/redesign while cycles remain).
  WARNINGS (exit 0 — worth a look, not a corruption):
    - an evidence pointer whose `log_path` no longer resolves on disk (logs get relocated/gitignored);
      an `open_thread` with no `next_action`; `current_phase == refinement` with no decision yet
      (a valid *pending-gate* state); `skip_testing_count` over the usual cap.

Stdlib-only (runs under system python3 + the SessionStart hook). Run from the repo root:
    python3 tools/check_workflow_state_offline.py            # all use_cases/*/…_r*.json
    python3 tools/check_workflow_state_offline.py --file <path>
    python3 tools/check_workflow_state_offline.py --quiet    # one line per file (for the hook)

Author: Jing Tao with Claude
"""
import argparse
import glob
import re
import json
import pathlib
import subprocess
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Load workflow_state_offline DIRECTLY by file (not `from tools.…`) so we bypass tools/__init__.py,
# which pulls in 3.7+ deps (dataclasses) — this keeps the checker runnable under system python 3.6
# (the SessionStart hook + the Tier-1 smoke context, same as check_skill_registry).
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "_wso_direct", str(Path(__file__).resolve().parent / "workflow_state_offline.py"))
_wso = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_wso)
WorkflowStateOffline, SCHEMA = _wso.WorkflowStateOffline, _wso.SCHEMA

VALID_PHASES = set(WorkflowStateOffline.RUNNABLE_PHASES) | {"refinement"}

#: The machine configs that EXPORT the loop limits. Both are read; a disagreement between them is
#: reported rather than silently resolved, because "keep in sync" is a comment and not a mechanism.
_CONFIG_FILES = ("a2mc_noncime_config.sh", "a2mc_config.sh")

#: The directory those configs live in. A module attribute rather than an inline expression so a
#: test can point it at a fixture: a disagreement between the two configs is the branch most likely
#: to be wrong and the one hardest to reproduce against the real repo.
_CONFIG_ROOT = Path(__file__).resolve().parents[1]


def _limit_from_config(var):
    """-> (int_or_None, note). Thin wrapper over the ONE derivation, in workflow_state_offline.

    The implementation moved there on 2026-09-07 because `set_phase6_decision` needed the same
    lookup and was hardcoding 10, which is the drift a second copy always produces
    ([[feedback_bind_derived_facts_to_their_source]]). The module-level `_CONFIG_FILES` and
    `_CONFIG_ROOT` above are kept and PASSED IN, so a test can still point either at a fixture --
    that disagreement branch is the one hardest to reproduce against the real repo.
    """
    return _wso.limit_from_config(var, files=_CONFIG_FILES, root=_CONFIG_ROOT)


def _limit_from_env(var, fallback):
    """-> (int, note). The loop limits live in the MACHINE CONFIG, so read them from there.

    THE DRIFT THIS FIXES. `a2mc_config.sh` and `a2mc_noncime_config.sh` both export
    `A2MC_MAX_SKIP_TESTING` and `A2MC_MAX_EXPERIMENTS`, and `orchestrator.py:3567-3571` reads both as
    its argparse defaults -- so the ONLINE agent obeys whatever the PI sets. The offline runtime read
    neither: this module carried its own hardcoded 10s. They agree at 10 today, which is exactly why
    nobody noticed; set `A2MC_MAX_SKIP_TESTING=6` and the online agent obeys it while this checker
    goes on warning at 10, silently, in both directions.

    Two copies of a value with one source of truth is [[feedback_bind_derived_facts_to_their_source]].
    Found 2026-08-22 by the PI, after I read the state file and this module's own comment and
    concluded the offline inner loop had no limit at all -- without sourcing the config where it
    lives.

    Stdlib `os.environ` rather than `tools/config.py` on purpose: this module is imported by the
    pre-commit hook, whose interpreter must not depend on the A2MC package being importable. Same
    reason `workflow_state_offline` is loaded here by importlib rather than by `from tools import`.

    Falls back when the config was NOT sourced -- a pre-commit run typically has a bare environment.
    The note says which source was used, so a surprising limit is traceable rather than mysterious.
    """
    raw = os.environ.get(var)
    if raw is None or str(raw).strip() == "":
        # NOT SOURCED. Before falling back to a copy of the value, READ THE CONFIG THAT DEFINES IT.
        # The built-in constants below are a second copy of a number the shipped configs export, and
        # this docstring's own complaint applies to them: they agree by coincidence until someone
        # changes the config, at which point a bare-environment run (a pre-commit hook) resolves a
        # DIFFERENT limit from the agent that wrote the state. Measured 2026-09-06: a round raised
        # the cap to 20, two live cases passed the limit, and the same state files validated in a
        # sourced shell and failed in the hook. Stdlib regex only, so the no-A2MC-import rule holds.
        v, note = _limit_from_config(var)
        if v is not None:
            return v, note
        return fallback, f"{var} unset (config not sourced) — using the built-in default {fallback}"
    try:
        v = int(str(raw).strip())
    except (TypeError, ValueError):
        return _config_or(fallback, var, f"{var}={raw!r} is not an integer")
    if v < 1:
        return _config_or(fallback, var, f"{var}={v} must be >= 1")
    return v, None


def _config_or(fallback, var, why):
    """A malformed environment value falls back the SAME way an unset one does: config, then copy.

    Splitting these two paths is how an inconsistency creeps in -- unset reading the source of truth
    while junk reads a copy of it -- so both go through the config first and only then to the
    built-in constant, with `why` preserved in the note either way.
    """
    v, note = _limit_from_config(var)
    if v is not None:
        return v, f"{why} — {note}"
    return fallback, f"{why} — using the built-in default {fallback}"


#: The built-in fallbacks, used ONLY when the machine config was not sourced. They must match the
#: values the shipped configs export, or a bare-environment run disagrees with a sourced one.
FALLBACK_SKIP_TESTING_CAP = 10
FALLBACK_MAX_EXPERIMENTS = 10
#: commits touching a case since its newest recorded decision before we warn. 12 is 
#: deliberately loose -- this is a nudge about a habit, not a gate, and a chatty warning 
#: gets tuned out, which would make it worse than none.
DECISION_STALE_COMMITS = 12
REPO = Path(__file__).resolve().parent.parent



#: THE LOOP LIMIT MUST BE A NUMBER, or the whole middle loop becomes undecidable.
#:
#: `calibration-discipline` item 6 says: below `max_experiments` and not converged, the only valid
#: states are running-a-cycle or launching-the-next. That test needs a number. Found 2026-08-22 in a
#: self-review: R3's state carried `max_experiments: None`, so `experiment_count == max_experiments`
#: could never be true (the round could never legitimately reach the per-round checklist) and
#: `experiment_count < max_experiments` raised `TypeError: '<' not supported between 'int' and
#: 'NoneType'`.
#:
#: `.get(k, 10)` does NOT protect against this: a key PRESENT with value None returns None, not the
#: default. That is why both call sites looked safe and neither was. A raise is better than a
#: fail-open, but it makes the premature-stop guard unavailable at exactly the moment it is needed,
#: and any caller wrapping it in try/except turns it back into a fail-open.


def resolve_max_experiments(d):
    """-> (int, error_or_None). Prefers the top-level value, falls back to phase6_decision's."""
    for where in ("top-level", "phase6_decision"):
        src = d if where == "top-level" else (d.get("phase6_decision") or {})
        if "max_experiments" not in src:
            continue
        v = src["max_experiments"]
        if isinstance(v, int) and not isinstance(v, bool) and v >= 1:
            return v, None
        return _limit_from_env("A2MC_MAX_EXPERIMENTS", FALLBACK_MAX_EXPERIMENTS)[0], (
            f"max_experiments ({where}) is {v!r} — must be an int >= 1. The middle-loop limit is "
            f"undecidable while it is not a number: `experiment_count == max_experiments` can never "
            f"be true, so the round can never legitimately reach the per-round checklist, and the "
            f"premature-stop guard raises instead of rejecting.")
    return _limit_from_env("A2MC_MAX_EXPERIMENTS", FALLBACK_MAX_EXPERIMENTS)[0], None


def check_one(path):
    """Return (errors, warnings) for one state file."""
    errors, warnings = [], []
    try:
        d = json.loads(Path(path).read_text())
    except Exception as e:
        return [f"unreadable / invalid JSON: {e}"], []

    if d.get("schema") != SCHEMA:
        errors.append(f"schema '{d.get('schema')}' != expected '{SCHEMA}'")

    cp = d.get("current_phase")
    if cp not in VALID_PHASES:
        errors.append(f"current_phase '{cp}' not in {sorted(VALID_PHASES)}")

    cr = d.get("calibration_round")
    if not isinstance(cr, int) or cr < 1:
        errors.append(f"calibration_round '{cr}' must be an int >= 1")

    mx, mx_err = resolve_max_experiments(d)
    if mx_err:
        errors.append(mx_err)
    ec = d.get("experiment_count", 0)
    if not isinstance(ec, int) or ec < 0:
        errors.append(f"experiment_count '{ec}' must be an int >= 0")
    elif ec > mx:
        errors.append(f"experiment_count ({ec}) exceeds max_experiments ({mx}) — middle loop overran")

    stc = d.get("skip_testing_count", 0)
    if not isinstance(stc, int) or stc < 0:
        errors.append(f"skip_testing_count '{stc}' must be an int >= 0")
    else:
        cap, cap_note = _limit_from_env("A2MC_MAX_SKIP_TESTING", FALLBACK_SKIP_TESTING_CAP)
        if stc > cap:
            warnings.append(f"skip_testing_count ({stc}) over the inner-loop limit ({cap})"
                            + (f" [{cap_note}]" if cap_note else " [A2MC_MAX_SKIP_TESTING]"))

    if not isinstance(d.get("converged"), bool):
        errors.append(f"converged '{d.get('converged')}' must be a bool")

    for i, t in enumerate(d.get("open_threads", [])):
        if not (t.get("id") or "").strip():
            errors.append(f"open_threads[{i}] has no 'id'")
        if not (t.get("next_action") or "").strip():
            warnings.append(f"open_thread '{t.get('id', i)}' has no next_action")

    ev = d.get("evidence", {})
    for cat in ("diagnoses", "hypotheses", "experiments"):
        for e in ev.get(cat, []):
            lp = e.get("log_path")
            if lp and not (ROOT / lp).exists() and not Path(lp).exists():
                warnings.append(f"evidence {cat} '{e.get('stem', '?')}': log_path not on disk ({lp})")

    dec = d.get("phase6_decision")
    if dec:
        viol = WorkflowStateOffline(data=d).validate_phase6_decision()
        for v in viol:
            errors.append(f"phase6_decision: {v}")
        if cp != "refinement":
            warnings.append(f"phase6_decision set but current_phase is '{cp}', not 'refinement'")
    elif cp == "refinement":
        warnings.append("current_phase=refinement with no phase6_decision — pending the convergence gate")

    warnings.extend(_check_decisions_current(path, d))
    rc_errors, rc_warnings = _check_round_close(path, d)
    errors.extend(rc_errors)
    warnings.extend(rc_warnings)
    warnings.extend(_check_site_kb_populated(path, d))
    errors_, warnings_ = _check_phase_logged(path, d)
    warnings += _check_phase_skill_invoked(path, d)
    errors.extend(errors_)
    warnings.extend(warnings_)

    return errors, warnings


# Phase name -> the phase NUMBER that appears in an offline log stem
# (stem = YYYYMMDDx_phase{N}_{name}_r{RR}[_c{EE}[_iter{II}]]_{descriptor}).
_PHASE_NUM = {"design": 0, "exploration": 1, "screening": 2, "diagnosis": 3,
              "hypothesis": 4, "testing": 5, "refinement": 6, "converged": 7}


def _check_decisions_current(path, d):
    """WARN when the case has moved but the state has recorded no findings.

    The state is not only a program counter. `PhaseLogger` rebuilds its "Reasoning chain" block
    from `decisions` on every log write, so a finding that never reaches the state is invisible to
    the next phase -- which is the re-derivation the loop exists to prevent
    (`calibration-discipline`: "Your job is to keep it true").

    Measured 2026-08-21: a full day of R3 work established eight substantive findings (a definitive
    failure census, a misdiagnosis and its real cause, six passed gates, a model defect, three
    reasons a round was not comparable to its predecessor) and the state recorded TWO decisions,
    both from that morning. Everything else lived as prose in `next_action` -- which is the program
    counter, not the record -- and in commit messages. Nothing flagged it; the gap surfaced only
    because the PI asked.

    The signal used here is ACTIVITY vs RECORD: commits touching this case since the newest
    decision's date. It cannot judge whether a finding was worth recording, and deliberately does
    not try -- it asks the much weaker question "has this case moved a lot with nothing written
    down", which is the shape the failure actually took.

    WHAT WOULD MAKE THIS FAIL (named first, per `feedback_a_check_that_cannot_fail`):
      1. many commits touching the case, newest decision older than all of them  -> WARN
      2. no decisions at all on an active round                                  -> WARN
      3. git unavailable, or the case path unknown                               -> SILENT, never a
         false alarm; an unreadable history is not evidence of a missing finding.
    """
    warnings = []
    decs = d.get("decisions") or []
    if not isinstance(decs, list):
        return warnings
    if d.get("converged"):
        return warnings                      # a closed round is not expected to keep recording
    # Only the ACTIVE (highest-numbered) round. A superseded round's decisions are finished by
    # definition, and warning about them forever is how a nudge becomes noise and gets tuned out --
    # which would leave the real case unwatched. Measured: without this, r02 warned permanently
    # about 130 commits since 2026-07-21 while r03, the round actually being worked, was clean.
    here = Path(path).resolve()
    siblings = sorted(here.parent.glob("workflow_state_offline_r*.json"))
    if siblings and here != siblings[-1]:
        return warnings

    newest = max((x.get("date", "") for x in decs), default="")
    case_dir = Path(path).resolve().parent.parent          # <case>/memory/<state>.json -> <case>
    try:
        out = subprocess.run(
            ["git", "log", "--since", newest or "30 days ago", "--format=%h", "--", str(case_dir)],
            capture_output=True, text=True, timeout=30, cwd=str(REPO))
        if out.returncode != 0:
            return warnings
        n = len([x for x in out.stdout.split() if x])
    except Exception:
        return warnings                      # (3) silent

    if not decs:
        warnings.append(
            f"no decisions recorded on an active round ({n} commit(s) touching this case) — "
            f"findings belong in the state as they are established, not only at Phase 6")
    elif n >= DECISION_STALE_COMMITS:
        warnings.append(
            f"{n} commit(s) touching this case since the newest decision ({newest}) — "
            f"record findings with add_decision(finding, rationale) as they are established; "
            f"next_action is the program counter, not the record")
    return warnings


#: current_phase -> the skill that governs it. The mapping is the whole point: the skill carries
#: requirements the phase cannot be done correctly without.
PHASE_SKILL = {
    "design": "phase0-design", "exploration": "phase1-exploration",
    "screening": "phase2-screening", "diagnosis": "phase3-diagnosis",
    "hypothesis": "phase4-hypothesis", "testing": "phase5-testing",
    "refinement": "phase6-refinement",
}


def _case_of(path):
    """`EcoSIM_TeRaCON` from a state path, for warnings that must NAME THEIR CASE.

    This checker is REPO-WIDE. Its per-round messages said only "round 1", and the case name
    appeared once, on the group header above them. A warning read out of that context -- pasted
    into a review, quoted in a summary -- is attributed to whatever case the reader had in mind.
    Measured 2026-09-05: a clean TeRaCON state was reported as carrying a housekeeping debt and an
    empty knowledge base, both of which belong to other cases.
    """
    try:
        parts = pathlib.Path(path).parts
        return parts[parts.index("use_cases") + 1]
    except (ValueError, IndexError):
        return "?"


def _check_round_close(path, d):
    """Return (errors, warnings): did a CLOSED round actually produce its deliverables?

    WHAT WOULD MAKE THIS FAIL (named first, per `feedback_a_check_that_cannot_fail`):
      1. `round_close.report_path` empty, or recorded but not on disk        -> ERROR (any round)
      2. ACTIVE round: `housekeeping` recorded while `round_close` is not    -> ERROR
         (provably out of order -- the later step ran and the earlier did not)
      3. ACTIVE round: `converged` with no `round_close`                     -> ERROR
         (Phase 7 reached with no round report at all)
      4. any other closing round with no `round_close` / no `housekeeping`   -> WARN
      5. a round close recorded with a step not run                          -> WARN

    THE SEVERITY SPLIT, AND A TRAP I WALKED INTO BUILDING IT. The first draft errored when "a
    later round's state file exists", and exempted SUPERSEDED rounds from erroring -- but those
    are the SAME CONDITION, so the error branch was unreachable and the check could not fail on
    the case it was written for. Rules 2 and 3 replace it with conditions that are observable
    from the round's own state and reachable on the ACTIVE round.

    Why the historical debt only WARNS: rounds that closed before this contract existed carry a
    real debt -- the site KB is empty after thirty experiment cycles -- but blocking every future
    commit on a round finished in July is the retro-fail trap, and it teaches people to reach for
    --no-verify, which is how a gate stops being a gate. The debt stays VISIBLE on every run and
    is scheduled work, not a blocker.

    It asserts the POINTER, never the report's contents: `tools/check_report_conformance.py` R8
    owns those rules, and re-implementing them here would be a second opinion that drifts
    (`feedback_bind_derived_facts_to_their_source`).
    """
    errors, warnings = [], []
    rc = d.get("round_close")
    hk = d.get("housekeeping")
    dec = (d.get("phase6_decision") or {}).get("decision")
    rnd = d.get("calibration_round")
    here = Path(path).resolve()

    siblings = sorted(here.parent.glob("workflow_state_offline_r*.json"))
    is_active = not siblings or here == siblings[-1]

    mx, _ = resolve_max_experiments(d)
    ec = d.get("experiment_count", 0)
    ENDING = ("converge", "redesign_6to0", "stop_model_dev")
    closing = (bool(d.get("converged")) or dec in ENDING
               or (isinstance(ec, int) and isinstance(mx, int) and ec >= mx))

    # ---- rule 0: threads that outlived the round's close without being re-affirmed ----
    #
    # `close_thread()` exists and nothing ever required calling it, so a closed round keeps every
    # thread it ever opened and a cold session reads them as live. Measured 2026-09-22:
    # PFLOTRAN_miniLEO R1, closed 2026-09-02, still carried 16 -- among them a wait on a
    # filesystem drain and a queue gate, both resolved weeks earlier, and a "NOT YET DONE" item
    # that had in fact been done.
    #
    # A thread may legitimately outlive its round (an open question for the next one, a standing
    # instruction), so this WARNS and asks for one of two things: close it, or re-affirm it. A
    # re-affirm is visible, because `add_thread` stamps `updated` on every write. Threads written
    # before that stamp existed have no date and are reported as unreviewed, which is what they
    # are.
    if rc:
        closed_at = (rc.get("closed_at") or "").strip()
        threads = d.get("open_threads") or []
        if closed_at and threads:
            stale = [t.get("id", "<unnamed>") for t in threads
                     if (t.get("updated") or "") <= closed_at]
            if stale:
                warnings.append(
                    "%s round %s: %d of %d open thread(s) have not been touched since the round "
                    "closed on %s: %s. Close each with `close_thread(id)`, or re-affirm it with "
                    "`add_thread(...)` so its `updated` stamp moves -- a cold session reads an "
                    "open thread as live work."
                    % (_case_of(path), rnd, len(stale), len(threads), closed_at,
                       ", ".join(sorted(stale)[:8]) + (" ..." if len(stale) > 8 else "")))

    # ---- rule 1: the pointer. Wrong at ANY age -- it asserts evidence that is not there.
    if rc:
        rp = (rc.get("report_path") or "").strip()
        if not rp:
            errors.append(f"{_case_of(path)} round {rnd}: `round_close` recorded with an empty report_path -- "
                          f"that asserts a deliverable exists while naming nothing")
        elif not (ROOT / rp).exists() and not Path(rp).exists():
            errors.append(f"{_case_of(path)} round {rnd}: `round_close.report_path` does not resolve ({rp}). A "
                          f"pointer to nothing is worse than no pointer: it READS as evidence.")
        steps = rc.get("steps") or {}
        missing = [k for k in ("summarize", "compare", "report") if not steps.get(k)]
        if missing:
            warnings.append(
                f"{_case_of(path)} round {rnd}: round close recorded with step(s) not run: {', '.join(missing)}. "
                f"The three are ordered and `compare-calibration-rounds` is the one that gets "
                f"skipped -- which is how a round summary re-proposed two already-refuted "
                f"parameters.")

    # ---- rules 2 and 3: reachable ERRORs, on the ACTIVE round only.
    if not rc:
        if is_active and hk:
            errors.append(
                f"{_case_of(path)} round {rnd}: `housekeeping` is recorded but `round_close` is NOT. The steps ran "
                f"out of order: the round report is `calibration-discipline` item 9 and is what "
                f"the PI routes the round WITH, so it precedes the gate the housekeeping follows.")
        elif is_active and d.get("converged"):
            errors.append(
                f"{_case_of(path)} round {rnd}: `converged` with no `round_close`. Phase 7 was reached without a "
                f"round summary, cross-round ledger or ROUND report -- and a converged round is "
                f"the CAMPAIGN's terminal, so nothing downstream will produce them.")
        elif closing:
            warnings.append(
                f"{_case_of(path)} round {rnd}: closed (converged / at the cycle limit / gate decided '{dec}') but "
                f"no `round_close` is recorded. Record it via "
                f"`st.set_round_close(report_path=...)` once the three steps have run.")

    # ---- T10.2: the Phase-7 CONVERGED deliverable. Only meaningful once converged, and an
    # ERROR there rather than a warning: a converged round is the CAMPAIGN's terminal, so there is
    # no later step that will produce the artifact if this moment does not.
    if d.get("converged"):
        fc = d.get("final_configuration")
        if not fc:
            errors.append(
                f"{_case_of(path)} round {rnd}: `converged` with no `final_configuration`. The campaign's actual "
                f"product -- parameter values, the base they modify, the case, the ARCHIVED binary, "
                f"the reproduce command, and the residual -- has no record. Contract: "
                f"`phase6-refinement`, 'The Phase-7 CONVERGED deliverable'. Record it via "
                f"`st.set_final_configuration(path=...)`.")
        else:
            fp = (fc.get("path") or "").strip()
            if not fp:
                errors.append(f"{_case_of(path)} round {rnd}: `final_configuration` recorded with an empty path")
            elif not (ROOT / fp).exists() and not Path(fp).exists():
                errors.append(f"{_case_of(path)} round {rnd}: `final_configuration.path` does not resolve ({fp}). A "
                              f"pointer to nothing READS as evidence that the artifact exists.")
            if not (fc.get("reproduce_command") or "").strip():
                warnings.append(f"{_case_of(path)} round {rnd}: `final_configuration` carries no reproduce_command. "
                                f"A description of how to reproduce is not a reproduction.")
            ab = (fc.get("archived_binary") or "").strip()
            if not ab:
                warnings.append(f"{_case_of(path)} round {rnd}: `final_configuration` names no archived_binary -- "
                                f"the result cannot be tied to the executable that produced it")
            elif "/bld/" in ab or ab.endswith("/e3sm.exe") and "archive" not in ab.lower():
                warnings.append(f"{_case_of(path)} round {rnd}: `final_configuration.archived_binary` looks like a "
                                f"LIVE BUILD path ({ab}). The build tree is shared and every build "
                                f"overwrites it in place -- record the ARCHIVED copy "
                                f"(feedback_bind_runs_to_archived_binaries).")

    # ---- rule 4: the housekeeping debt. WARN everywhere -- see the docstring.
    if closing and not hk:
        warnings.append(
            f"{_case_of(path)} round {rnd}: closed but no `housekeeping` recorded. It runs AT or AFTER the gate, "
            f"including on convergence with a FULLER checklist (PI 2026-08-25), because a "
            f"converged round hands work to nobody. Measured cost of skipping it: thirty "
            f"experiment cycles and an empty site knowledge base.")
    return errors, warnings


def _check_site_kb_populated(path, d):
    """WARN when a case that has CLOSED a round has an empty site knowledge base.

    WHAT WOULD MAKE THIS FAIL (named first, per `feedback_a_check_that_cannot_fail`):
      * the case has closed at least one round (this state is closing, or a later round exists)
        AND `gained_knowledge/` is absent, or every store in it is empty

    WHY THIS SHAPE, AND WHAT WAS REJECTED. The obligation being enforced is "the diagnosis and
    hypothesis phases must READ the site knowledge base". The obvious check is to grep the phase
    log for a mention of it -- and that was rejected: a rule satisfied by typing a word is
    satisfied without doing the work, which is the failure mode
    `feedback_exact_strings_are_contracts` describes. It would be a check that cannot really fail.

    So this checks the CONSEQUENCE instead, which is not gameable and is the thing that actually
    went wrong: a store nobody writes is a store nobody can read. One case reached THIRTY
    experiment cycles across three closed rounds with `experiments: []`, `failed_approaches: []`
    and `parameters: {}` -- so every "check Memory before proposing" instruction in every phase
    skill was satisfiable by opening an empty file. The read obligation is delivered by the phase
    skills themselves (now naming the site path and the callable) plus the existing
    `_check_phase_skill_invoked`; this check covers the half those cannot see.

    WARNING, never ERROR: an empty KB is a real finding but blocks nothing mechanically, and a
    young case legitimately has one before its first round closes.
    """
    site_dir = Path(path).resolve().parent.parent          # …/<case>/memory/x.json -> <case>
    gk = site_dir / "memory" / "gained_knowledge"
    rnd = d.get("calibration_round")

    here = Path(path).resolve()
    later = any(re.search(r"_r(\d+)\.json$", s.name)
                and int(re.search(r"_r(\d+)\.json$", s.name).group(1)) > (rnd or 0)
                for s in here.parent.glob("workflow_state_offline_r*.json"))
    mx, _ = resolve_max_experiments(d)
    ec = d.get("experiment_count", 0)
    dec = (d.get("phase6_decision") or {}).get("decision")
    closed = (later or bool(d.get("converged")) or dec in ("converge", "redesign_6to0", "stop_model_dev")
              or (isinstance(ec, int) and isinstance(mx, int) and ec >= mx))
    if not closed:
        return []

    if not gk.is_dir():
        return [f"{_case_of(path)} round {rnd} has closed but {gk.relative_to(ROOT) if str(gk).startswith(str(ROOT)) else gk}"
                f" does not exist. Every 'check Memory before proposing' instruction in the phase "
                f"skills reads a store that is not there. `round-housekeeping` step 1 creates it."]

    counts, empty = {}, True
    for name in ("discoveries", "experiments", "parameters", "failed_approaches"):
        f = gk / f"{name}.json"
        n = 0
        if f.is_file():
            try:
                payload = json.loads(f.read_text())
                n = _count_kb_entries(payload, name)
            except Exception:
                n = -1
        counts[name] = n
        if n > 0:
            empty = False
    if empty:
        return [f"{_case_of(path)} round {rnd} has closed and the SITE knowledge base is EMPTY "
                f"({', '.join(f'{k}={v}' for k, v in counts.items())}). A store nobody writes is a "
                f"store nobody can read: the read obligation in `phase3-diagnosis` and "
                f"`phase4-hypothesis` is satisfiable by opening an empty file. Run "
                f"`round-housekeeping` (step 1 curates, step 6 asserts this)."]
    thin = [k for k, v in counts.items() if v == 0]
    if thin:
        return [f"{_case_of(path)} round {rnd} closed with empty site-KB store(s): {', '.join(thin)}. A round that "
                f"refuted levers and recorded zero `failed_approaches` did not curate them."]
    return []



def _count_kb_entries(payload, name):
    """Count entries in a gained_knowledge store, supporting BOTH storage formats.

    `MemoryManager._discovery_entries` documents that these files carry two formats and that
    both may coexist in one file: an ARRAY under the store's own key (used by the model-level
    store) and a FLAT map of top-level `name -> entry` dicts (used by the SITE stores, and what
    `MemoryManager.add_discovery` writes). A seeded site file typically has both -- an empty
    array left by its template, plus the real entries as top-level keys.

    THE BUG THIS FIXES. The previous form was `inner = payload.get(name, payload)`, which takes
    the array whenever the key EXISTS. For a seeded site store that array is `[]`, so the count
    came back 0 and the checker reported an empty store while `MemoryManager.stats()` on the same
    file reported seven. Measured 2026-09-09 on EcoSIM_Lusignan at its round close, immediately
    after seven discoveries had been curated into it. A checker and the library it is checking
    disagreeing about the same file is a bug in one of them, and it was here.
    """
    if not isinstance(payload, dict):
        return len(payload) if isinstance(payload, list) else 0
    seen = set()
    arr = payload.get(name)
    if isinstance(arr, list):
        for item in arr:
            if isinstance(item, dict):
                seen.add(item.get("id") or item.get("name") or id(item))
            else:
                seen.add(id(item))
    elif isinstance(arr, dict):
        seen.update(k for k in arr if not str(k).startswith("_"))
    for k, v in payload.items():
        if str(k).startswith("_") or k == name:
            continue
        if isinstance(v, dict):
            seen.add(k)
    return len(seen)


def _check_any_round_close_exists(paths):
    """Anti-silent-pass guard (rule 5). If `round_close` were renamed, every branch of
    `_check_round_close` would stop matching and this checker would report clean forever --
    the exact failure mode of a check keyed on a label another tool writes
    (`feedback_exact_strings_are_contracts`). At least one state is expected to carry one.
    """
    for p in paths:
        try:
            if json.loads(Path(p).read_text()).get("round_close"):
                return []
        except Exception:
            continue
    return ["no state file anywhere records a `round_close`. Either no round has closed yet "
            "(fine on a young case) or the key was renamed and every round-close check above is "
            "now matching nothing. Verify before ignoring."]


def _check_phase_skill_invoked(path, d):
    """WARN when the CURRENT phase's governing skill has not been invoked this session.

    THE GAP THIS CLOSES. `check_skill_claims.py` (v2.275) verifies that a skill a log CLAIMS was
    really invoked. It cannot notice a skill that was simply never invoked and never claimed --
    skip the skill, write "Skills: none", and the record is honest while the work is still wrong.

    So this fires at a different moment and asks a different question. It runs while the phase is
    CURRENT, not after the log is written, and it asks "have you read the thing that governs what
    you are doing right now". Sited here because the hourly `calibration-discipline` review and
    pre-commit check (9) both already run this checker -- no new command to remember, which is the
    property that made the other hooks stick.

    Measured cost of not having it, 2026-08-22: R3 Phases 1-4 were all worked without their skills.
    Invoking `phase3-diagnosis` afterwards surfaced a requirement it would have enforced -- a
    sim-vs-obs time series per scored target -- absent from two phases, and supplying it changed
    what the round knows.

    WARN, never ERROR: a phase is legitimately current for the first minutes before anything is
    read, and erroring would gate the loop on a bookkeeping artifact -- which is how gates get
    bypassed wholesale.
    """
    if d.get("converged"):
        return []
    # ACTIVE round only, for _check_decisions_current's reason: a superseded round warning forever
    # is how a nudge becomes noise and gets tuned out, leaving the real case unwatched.
    here = Path(path).resolve()
    siblings = sorted(here.parent.glob("workflow_state_offline_r*.json"))
    if siblings and here != siblings[-1]:
        return []
    cp = d.get("current_phase")
    skill = PHASE_SKILL.get(cp)
    if not skill:
        return []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from check_skill_claims import invoked_skills          # bind to the source, do not re-read
        invoked, ntr = invoked_skills()
    except Exception:
        return []                                              # no transcript access: stay silent
    if ntr == 0:
        return []
    if skill in invoked:
        return []
    return [f"current phase is '{cp}' but `{skill}` has NOT been invoked this session. "
            f"That skill carries requirements the phase cannot be done correctly without "
            f"(measured: skipping phase3-diagnosis cost a required sim-vs-obs time series). "
            f"Invoke it before finishing the phase, not after writing the log."]


def _check_phase_logged(path, d):
    """WARN when the state says a phase is current but no offline log exists for it.

    `calibration-discipline` already requires 'each phase logged with its phaseN skill +
    calibration-log'. That was a checklist item — a habit — and habits decay silently across
    a multi-week round. This makes it observable, and it belongs HERE because the same
    checklist already says the state is validated after EVERY phase, so the existing habit
    gains the check without a new command to remember.

    It is a filesystem question, not a judgement about prose: a log stem encodes its phase
    and round, so 'was this phase logged?' is decidable — the same category as the evidence
    gate (an artifact exists) rather than 'is the section any good'.

    WARNING, never ERROR: an error would block the state write a phase transition depends on,
    i.e. gate the loop on a bookkeeping artifact, and that is how gates get bypassed.

    But the window in which it fires innocently is SHORT, and the message says so. A phase log
    is a LIVING record, not an end-of-phase write-up (PI, 2026-08-02): a phase-0 log should
    exist from the moment cases are submitted, and then accumulate the job/array IDs, the
    monitoring armed, the cases that failed when the scheduler hiccupped, what was restarted,
    and the early plots that checked the run looks right — each paired with an artifact in
    `phase_results/{stem}/`. Create it early and enrich it; do not defer it to the end, or the
    operational detail that makes it useful is gone by the time you write it.
    """
    cp, rnd = d.get("current_phase"), d.get("calibration_round")
    n = _PHASE_NUM.get(cp)
    if n is None or rnd is None:
        return [], []                       # already reported by the checks above
    logs_dir = Path(path).parent / "logs"
    if not logs_dir.is_dir():
        return [], [f"no {logs_dir} — phase '{cp}' cannot have been logged"]

    want = f"_phase{n}_{cp}_r{int(rnd):02d}"
    if not any(want in p.name for p in logs_dir.glob("*.md")):
        return [], [f"no offline log found for phase {n} ({cp}) of round {int(rnd):02d} "
                    f"— expected a stem containing '{want}' in {logs_dir.name}/. "
                    f"START it now and enrich as you go (`calibration-log`): a phase log is a "
                    f"LIVING record — submission, job IDs, monitoring, failures/restarts, early "
                    f"verification plots — not an end-of-phase write-up. Only expected to be "
                    f"absent in the first moments of a phase."]
    return [], []


def main():
    ap = argparse.ArgumentParser(description="Validate offline workflow_state_offline_r*.json invariants")
    ap.add_argument("--file", help="check one state file (default: all use_cases/*/memory/…_r*.json)")
    ap.add_argument("--quiet", action="store_true", help="one line per file (for the SessionStart hook)")
    args = ap.parse_args()

    if args.file:
        paths = [args.file]
    else:
        # canonical per-round singletons only (…_r{RR}.json) — NOT archived/superseded copies
        # with extra suffixes, matching WorkflowStateOffline.find_latest()'s r(\d+)\.json regex.
        import re as _re
        paths = sorted(p for p in glob.glob(
            str(ROOT / "use_cases" / "*" / "memory" / "workflow_state_offline_r*.json"))
            if _re.search(r"workflow_state_offline_r\d+\.json$", p))

    if not paths:
        print("· no workflow_state_offline_r*.json found (no active offline round)")
        return 0

    # Anti-silent-pass guard (rule 5): surfaced ONCE for the whole run, not per file, since it
    # is a statement about the KEY's existence across the tree rather than about any one round.
    # If `round_close` were renamed, every branch of _check_round_close would quietly stop
    # matching and this checker would report clean forever.
    for g in _check_any_round_close_exists(paths):
        print(f"  NOTE    {g}")
    total_err = 0
    for p in paths:
        errs, warns = check_one(p)
        total_err += len(errs)
        rel = os.path.relpath(p, ROOT)
        if args.quiet:
            mark = "✘" if errs else ("·" if warns else "✔")
            print(f"  {mark} {rel}: {len(errs)} error(s), {len(warns)} warning(s)")
            continue
        mark = "✘" if errs else "✔"
        print(f"{mark} {rel}")
        for e in errs:
            print(f"    ERROR   {e}")
        for w in warns:
            print(f"    warn    {w}")

    if total_err:
        print(f"\n✘ {total_err} invariant error(s) — the offline state would misdrive the loop; fix before driving.")
        return 1
    print("\n✔ offline state invariants clean — schema, phase, counters, threads, phase6 gate all valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
