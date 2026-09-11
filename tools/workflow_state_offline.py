"""Offline-agent resume state (docs/31).

The autonomous agent resumes from a per-run `workflow_state_{sTAG}.json` (the WorkflowState
dataclass in orchestrator.py). The interactive (offline) agent has no run and no session_id —
it works continuously across days, keyed by calibration ROUND — so its resume brain is a
per-round singleton `use_cases/{site}/memory/workflow_state_offline_r{RR}.json`.

This is a SUBSET of WorkflowState (position/coordinate fields) + offline-only planning fields:
evidence is stored as POINTERS to topic-stems (the calibration logs hold the detail), plus
explicit open_threads / next_actions / decisions — the human-planning layer the online loop
has no place for (offline is a superset of online: it tracks everything online does, plus more).

Usage:
    from tools.workflow_state_offline import WorkflowStateOffline
    st = WorkflowStateOffline.load(calibration_round=5)      # or find_latest(site_dir)
    st.set_position(current_phase="diagnosis", experiment_count=0)
    st.add_diagnosis(stem, log_path, artifact_dir, one_line)
    st.add_thread("thread_id", summary="...", next_action="...", priority=1)
    st.save()
"""
import os
import re
import json
import glob
from collections import namedtuple
from pathlib import Path
from datetime import datetime

SCHEMA = "a2mc.offline_workflow_state.v1"

#: The machine configs that EXPORT the loop limits. Both are read; a disagreement between them is
#: reported rather than silently resolved, because "keep in sync" is a comment and not a mechanism.
CONFIG_FILES = ("a2mc_noncime_config.sh", "a2mc_config.sh")

#: The directory those configs live in. A module attribute so a test can point it at a fixture.
CONFIG_ROOT = Path(__file__).resolve().parents[1]


def limit_from_config(var, files=None, root=None):
    """-> (int_or_None, note). Read `export <var>=<int>` from the shipped machine configs.

    THE SINGLE DERIVATION OF THE LOOP LIMITS, and it lives here rather than in the checker
    because BOTH need it and a second copy is how the first drift happened.
    `A2MC_MAX_EXPERIMENTS` and `A2MC_MAX_SKIP_TESTING` are exported by `a2mc_config.sh` and
    `a2mc_noncime_config.sh` and by nothing else; `orchestrator.py` reads them as its argparse
    defaults, so the ONLINE agent obeys whatever the PI sets. Anything offline that hardcodes a
    number instead disagrees with the online agent the moment the PI changes one.

    Measured 2026-09-07: `set_phase6_decision` defaulted `max_experiments=10` while
    `a2mc_noncime_config.sh` exports 20, so an adapter case's Phase-6 decision recorded
    `experiment_count 12 of 10` -- a routing gate reading as exhausted eight cycles early.

    Returns None when no config states the value, leaving the caller's own fallback as the last
    resort it was written to be. Stdlib regex only, so a pre-commit interpreter needs nothing
    from the A2MC package.
    """
    files = CONFIG_FILES if files is None else files
    root = CONFIG_ROOT if root is None else Path(root)
    found = {}
    for name in files:
        f = root / name
        if not f.is_file():
            continue
        mm = re.findall(rf"^\s*export\s+{re.escape(var)}=([0-9]+)\s*$", f.read_text(), re.M)
        if mm:
            found[name] = int(mm[-1])
    if not found:
        return None, None
    vals = set(found.values())
    if len(vals) > 1:
        # THE TWO CONFIGS DISAGREE, and a bare state file cannot say which model family it belongs
        # to. Take the LARGER, deliberately and never silently: this value gates ROUTING, so a
        # too-small guess declares a round exhausted while cycles remain, which is the worse error.
        pairs = ", ".join(f"{k}={v}" for k, v in sorted(found.items()))
        return max(vals), (f"{var} DISAGREES between the machine configs ({pairs}) -- using the "
                           f"LARGER, because this limit gates routing and a too-small guess "
                           f"declares a round exhausted while cycles remain")
    v = next(iter(vals))
    return v, f"{var}={v} read from {'/'.join(sorted(found))}"

# The next workflow action a driver (the `calibration-goal` skill, docs/38 §4.3) should take,
# resolved PURELY from state. kind ∈ {"run_phase", "gate", "done"}:
#   run_phase  -> phase is the phase to run next (the driver ensures current_phase==phase, runs it)
#   close      -> a ROUND-CLOSE step the driver EXECUTES (never surfaces as a gate). phase is
#                 "round_close" (the three report steps) or "housekeeping" (the post-round
#                 curation). Two positions, not one, because the housekeeping is a Tier-3
#                 curated-KB write and therefore belongs AT/AFTER the human gate, never before
#                 it (`calibration-discipline` items 9/10/11).
#   gate       -> pause for a human decision (detail names the gate kind)
#   done       -> converged (Phase 7); clear the /goal
NextAction = namedtuple("NextAction", ["kind", "phase", "detail"])


class WorkflowStateOffline:
    """Per-round offline resume state (load / mutate / save)."""

    def __init__(self, site_dir=None, calibration_round=None, data=None, _from_load=False):
        """Build a state object. NOTE: this does NOT read disk -- `load()` is the reader.

        Two guards, both from live data loss:

        T9.2 -- NO SILENT `use_cases/TEMPLATE` FALLBACK. `site_dir` used to fall back to the
        template directory when `A2MC_USE_CASE_DIR` was unset, and `save()` does
        `mkdir(parents=True)`, so a mis-scoped call CREATED a spurious state tree inside the
        template instead of failing. Hit live 2026-08-22: a cycle-3 opening landed in
        `use_cases/TEMPLATE/memory/workflow_state_offline_r03.json` with `experiment_count: 0`,
        and the validator then declared that file clean. Env vars are intent; the case dir is
        truth (`feedback_env_vars_are_intent_case_dir_is_truth`), so an unresolvable site dir
        raises here rather than inventing one.

        T9.1 -- REFUSE TO BLANK AN EXISTING ROUND. The constructor populates `_blank()` when
        given no `data`, and `save()` writes unconditionally, so `WorkflowStateOffline(
        calibration_round=N)` followed by `.save()` silently REPLACED the round's history:
        on 2026-08-23 that turned r03's 303 decisions into 8 and reset `experiment_count`, and
        `check_workflow_state_offline.py` reported every invariant clean, because a state
        holding 8 decisions is structurally valid. Recoverable only because the file is tracked.
        Constructing over an existing round file now raises and names `load()`.
        """
        resolved = site_dir or os.environ.get("A2MC_USE_CASE_DIR")
        if not resolved and data is None:
            # Only a state that could be SAVED needs a real directory. `WorkflowStateOffline(
            # data=d)` is the sanctioned in-memory wrapper -- `check_workflow_state_offline.py`
            # uses it to call validate_phase6_decision() on an already-loaded dict and never
            # touches `.path`. Raising there would make the validator unusable without a sourced
            # config, which is the shape of failure T9.2 exists to prevent, not to cause.
            raise ValueError(
                "cannot resolve the use-case directory: pass site_dir=... or set "
                "A2MC_USE_CASE_DIR (source a2mc_config.sh then the case config). Refusing to "
                "fall back to use_cases/TEMPLATE -- save() would CREATE a state file there, and "
                "a spurious template state validates clean "
                "(feedback_env_vars_are_intent_case_dir_is_truth).")
        self.site_dir = Path(resolved) if resolved else None
        self.calibration_round = int(calibration_round
                                     or os.environ.get("A2MC_CALIBRATION_ROUND", "1"))
        self.site_name = os.environ.get(
            "A2MC_SITE_NAME", self.site_dir.name if self.site_dir else "unknown")
        if data is None and not _from_load and self.path.exists():
            raise FileExistsError(
                f"{self.path} already exists. The constructor does NOT read disk -- it would "
                f"hand you a BLANK state, and the next save() would destroy the round's history "
                f"(measured: 303 decisions -> 8). Use WorkflowStateOffline.load("
                f"calibration_round={self.calibration_round}) to read it, or pass data=... "
                f"explicitly if you really mean to replace it.")
        self.data = data if data is not None else self._blank()

    # ---- paths ----
    @property
    def path(self) -> Path:
        """The round's state file. RAISES on a data-only instance, which has no directory.

        The raise is the T9.2 guard at the point it actually matters: an in-memory wrapper
        built from `data=` can be validated freely, but the moment anything tries to READ or
        WRITE a file it must say which case it belongs to rather than inventing one.
        """
        if self.site_dir is None:
            raise ValueError(
                "this state was built from data= with no site_dir, so it has no path. Pass "
                "site_dir=... (or set A2MC_USE_CASE_DIR) if you mean to read or write a file; "
                "a data-only instance is for validation.")
        return (self.site_dir / "memory"
                / f"workflow_state_offline_r{self.calibration_round:02d}.json")

    def _blank(self) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "schema": SCHEMA,
            "note": ("Offline (interactive) agent resume brain — subset of WorkflowState + "
                     "offline planning fields; evidence is pointers to topic-stems, not blobs. "
                     "Per-round singleton (docs/31)."),
            "site": self.site_name,
            "calibration_round": self.calibration_round,
            "current_phase": "design",
            "experiment_count": 0,
            "skip_testing_count": 0,
            "converged": False,
            "started_at": today,
            "updated_at": today,
            "round_summary": "",
            "evidence": {"diagnoses": [], "hypotheses": [], "experiments": []},
            "open_threads": [],
            "next_actions": [],
            "decisions": [],
            # Phase-6 objective gate (docs/34). Filled before a converge/redesign/stop decision;
            # validate_phase6_decision() blocks a premature escalation. None until Phase 6.
            "phase6_decision": None,
            # ---- ROUND-CLOSE completion records (docs/38; the two positions the resolver reads).
            # Both None until the step completes. ADDITIVE: every pre-existing state file stays
            # valid and the schema string is unchanged -- a missing key reads as "not done yet",
            # which is exactly right for a round that closed before these existed.
            #
            # They are NOT `current_phase` values. Adding them to RUNNABLE_PHASES would make the
            # existing `phase in RUNNABLE_PHASES` branch fire on them and would force entries in
            # VALID_PHASES / PHASE_SKILL / _PHASE_NUM, at which point `_check_phase_logged` starts
            # demanding a log stem for a phase that has no number.
            "round_close": None,      # {report_path, closed_at, steps:{summarize,compare,report}}
            # The Phase-7 CONVERGED deliverable (T10.1). None until the campaign converges; a
            # converged state without it is an ERROR, because nothing downstream will produce it.
            "final_configuration": None,   # {path, reproduce_command, archived_binary, recorded_at}
            "housekeeping": None,     # {done_at, kb_curated, scripts_reviewed, ...}
            # T9.3 destruction guard: monotonic high-water marks. A state holding 8 decisions is
            # STRUCTURALLY VALID, which is why every invariant passed on a blanked r03 file that
            # had held 303. Validity cannot detect destruction; only history can.
            "_high_water": {"decisions": 0},
            "provenance": {"authored_by": "offline (interactive) agent",
                           "spec": "docs/31_Offline_Agent_Logging_And_Artifact_Layout_Plan.md"},
        }

    # ---- load / save ----
    @classmethod
    def load(cls, calibration_round=None, site_dir=None):
        """Load the round's state file, or return a blank one if it doesn't exist yet."""
        inst = cls(site_dir=site_dir, calibration_round=calibration_round, _from_load=True)
        if inst.path.exists():
            inst.data = json.loads(inst.path.read_text())
            inst.calibration_round = inst.data.get("calibration_round", inst.calibration_round)
        return inst

    @classmethod
    def find_latest(cls, site_dir=None):
        """Return the highest-round state instance on disk, or None if none exist."""
        resolved = site_dir or os.environ.get("A2MC_USE_CASE_DIR")
        if not resolved:
            raise ValueError(
                "find_latest: cannot resolve the use-case directory: pass site_dir=... or set "
                "A2MC_USE_CASE_DIR. Refusing to fall back to use_cases/TEMPLATE (T9.2).")
        base = Path(resolved)
        best = None
        for p in glob.glob(str(base / "memory" / "workflow_state_offline_r*.json")):
            m = re.search(r"workflow_state_offline_r(\d+)\.json$", p)
            if m and (best is None or int(m.group(1)) > best):
                best = int(m.group(1))
        if best is None:
            return None
        return cls.load(calibration_round=best, site_dir=site_dir)

    def save(self, allow_shrink=False) -> Path:
        """Write the state. REFUSES a write that would destroy recorded history (T9.3).

        WHAT WOULD MAKE THIS RAISE (named first, per `feedback_a_check_that_cannot_fail`):
          * fewer `decisions` than the high-water mark this round has already reached
          * a `round_close` or `housekeeping` record that was SET on disk and is now None

        Why a high-water mark and not a validator rule: `check_workflow_state_offline.py` asks
        whether a state is well-FORMED, and a blanked state is perfectly well-formed. On
        2026-08-23 a constructor-then-save replaced r03's 303 decisions with 8 and every
        invariant reported clean. Destruction is only visible against what came before, so the
        state has to carry its own watermark.

        `allow_shrink=True` is the deliberate escape hatch for a genuine correction (pruning a
        decision recorded in error). It is a keyword, so it can never be passed by accident.
        """
        hw = self.data.setdefault("_high_water", {"decisions": 0})
        n_dec = len(self.data.get("decisions", []))
        if not allow_shrink:
            prior = int(hw.get("decisions", 0))
            if n_dec < prior:
                raise ValueError(
                    f"refusing to save {self.path.name}: decisions would drop {prior} -> {n_dec}. "
                    f"This is the signature of a blank state overwriting a real one (measured "
                    f"2026-08-23: 303 -> 8, and the validator called it clean). If you truly mean "
                    f"to prune, pass save(allow_shrink=True).")
            if self.path.exists():
                try:
                    on_disk = json.loads(self.path.read_text())
                except Exception:
                    on_disk = {}
                for key in ("round_close", "housekeeping"):
                    if on_disk.get(key) and not self.data.get(key):
                        raise ValueError(
                            f"refusing to save {self.path.name}: '{key}' is recorded on disk and "
                            f"would be cleared. That erases the record that the round's "
                            f"deliverables were produced. Pass save(allow_shrink=True) if "
                            f"intentional.")
        hw["decisions"] = max(int(hw.get("decisions", 0)), n_dec)
        self.data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
        self.data["calibration_round"] = self.calibration_round
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2) + "\n")
        return self.path

    # ---- mutators ----
    def set_position(self, current_phase=None, experiment_count=None,
                     skip_testing_count=None, converged=None):
        prev_ec = self.data.get("experiment_count")
        for k, v in (("current_phase", current_phase),
                     ("experiment_count", experiment_count),
                     ("skip_testing_count", skip_testing_count),
                     ("converged", converged)):
            if v is not None:
                self.data[k] = v

        # A PHASE-6 DECISION EXPIRES WHEN THE CYCLE IT WAS MADE FOR ENDS. It records the routing
        # call for ONE cycle; `resolve_next_action()` routes on it and `validate_phase6_decision()`
        # checks the next gate against its premises, so a block left standing into the following
        # cycle misdrives both. Twice on 2026-08-22 a stale one survived a cycle advance and was
        # caught by a review rather than by anything mechanical: a c00 block found during c01, then
        # a c01 block found during c02. Clearing it here makes the expiry structural, not a habit.
        # Only on an ACTUAL advance -- moving phase within a cycle must leave the decision alone.
        if experiment_count is not None and experiment_count != prev_ec:
            self.data["phase6_decision"] = None
        return self


    def add_evidence(self, kind, stem, log_path, artifact_dir="", one_line=""):
        """kind in {'diagnoses','hypotheses','experiments'}. Idempotent on stem."""
        bucket = self.data["evidence"].setdefault(kind, [])
        entry = {"stem": stem, "log_path": str(log_path),
                 "artifact_dir": str(artifact_dir), "one_line": one_line}
        bucket[:] = [e for e in bucket if e.get("stem") != stem] + [entry]
        return self

    def add_diagnosis(self, stem, log_path, artifact_dir="", one_line=""):
        return self.add_evidence("diagnoses", stem, log_path, artifact_dir, one_line)

    def add_thread(self, thread_id, summary, next_action="", priority=None, refs=None):
        """Add or replace an open thread (idempotent on thread_id)."""
        t = {"id": thread_id, "summary": summary, "next_action": next_action}
        if priority is not None:
            t["priority"] = priority
        if refs:
            t["refs"] = list(refs)
        threads = self.data["open_threads"]
        threads[:] = [x for x in threads if x.get("id") != thread_id] + [t]
        threads.sort(key=lambda x: x.get("priority", 99))
        return self

    def close_thread(self, thread_id):
        self.data["open_threads"] = [x for x in self.data["open_threads"]
                                     if x.get("id") != thread_id]
        return self

    def add_decision(self, decision, rationale="", date=None):
        self.data["decisions"].append({
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "decision": decision, "rationale": rationale})
        return self

    def set_round_close(self, report_path, summarize=True, compare=True, report=True, date=None):
        """Record that the round's three-step CLOSE produced its deliverables (T1.2).

        `report_path` points at the ROUND report. `check_workflow_state_offline.py` asserts the
        pointer RESOLVES -- a pointer to nothing is worse than no pointer, because it reads as
        evidence. The three step flags say which of `summarize-calibration-round` ->
        `compare-calibration-rounds` -> `write-report` actually ran.
        """
        self.data["round_close"] = {
            "report_path": str(report_path),
            "closed_at": date or datetime.now().strftime("%Y-%m-%d"),
            "steps": {"summarize": bool(summarize), "compare": bool(compare),
                      "report": bool(report)},
        }
        return self

    def set_final_configuration(self, path, reproduce_command="", archived_binary="", date=None):
        """Record the Phase-7 CONVERGED deliverable (T10.1/T10.2).

        The campaign's actual product. `path` points at
        `use_cases/{Model}_{Case}/reports/{stem}_FINAL_CONFIGURATION/final_configuration.md`;
        `check_workflow_state_offline.py` asserts a converged state carries this AND that the
        pointer resolves. `archived_binary` is the ARCHIVED executable, never the live build
        path -- the build tree is shared and a queued job resolves its exe at run time
        (`feedback_bind_runs_to_archived_binaries`).
        """
        self.data["final_configuration"] = {
            "path": str(path),
            "reproduce_command": str(reproduce_command),
            "archived_binary": str(archived_binary),
            "recorded_at": date or datetime.now().strftime("%Y-%m-%d"),
        }
        return self

    def set_housekeeping(self, kb_curated=False, scripts_reviewed=False,
                         open_questions_path="", bound_debt_recorded=False, date=None):
        """Record that the POST-ROUND housekeeping ran (T1.2).

        Runs AT or AFTER the human gate, never before: curating knowledge is a Tier-3 write and
        one of the four gates (`calibration-discipline` items 9/10/11). A converged round runs
        this too, with a FULLER checklist rather than a skipped one -- convergence is the
        CAMPAIGN boundary and hands work to nobody, so every omission there is permanent
        (PI, 2026-08-25; see the round-close decision log).
        """
        self.data["housekeeping"] = {
            "done_at": date or datetime.now().strftime("%Y-%m-%d"),
            "kb_curated": bool(kb_curated),
            "scripts_reviewed": bool(scripts_reviewed),
            "open_questions_path": str(open_questions_path),
            "bound_debt_recorded": bool(bound_debt_recorded),
        }
        return self

    def set_next_actions(self, actions):
        self.data["next_actions"] = list(actions)
        return self

    # ---- Phase-6 objective gate (docs/34) ----

    #: allowed Phase-6 routing decisions (mirror the orchestrator state machine)
    PHASE6_DECISIONS = ("converge", "rethink_6to3", "redesign_6to0", "stop_model_dev")

    def set_phase6_decision(self, decision, binding_target="", next_targeted_experiment="NONE",
                            exhaustion_justification="", objective="", best_so_far="",
                            max_experiments=None):
        """Record a Phase-6 routing decision + the objective restatement it requires (docs/34).

        `next_targeted_experiment`: a named, in-range, target-aimed experiment aimed at
        `binding_target`, or the literal "NONE" if genuinely none remains.
        Call validate_phase6_decision() before acting on the result.

        `max_experiments` defaults to the MACHINE CONFIG rather than to a literal. It used to
        default to 10 while `a2mc_noncime_config.sh` exports 20, so an adapter case at cycle 12
        recorded `experiment_count 12 of 10` and the routing gate read as exhausted eight cycles
        early. The environment wins when it is set, then the config, then 10.
        """
        if max_experiments is None:
            env = os.environ.get("A2MC_MAX_EXPERIMENTS")
            mx = None
            if env is not None:
                try:
                    mx = int(env)
                except ValueError:
                    mx = None
            if mx is None:
                mx, _ = limit_from_config("A2MC_MAX_EXPERIMENTS")
            if not isinstance(mx, int) or mx < 1:
                mx = 10
        else:
            mx = max_experiments
        self.data["phase6_decision"] = {
            "objective": objective,
            "best_so_far": best_so_far,
            "binding_target": binding_target,
            "next_targeted_experiment": next_targeted_experiment,
            "exhaustion_justification": exhaustion_justification,
            "decision": decision,
            "experiment_count": self.data.get("experiment_count", 0),
            "max_experiments": mx,
        }
        return self

    def validate_phase6_decision(self):
        """Return a list of gate violations for the current phase6_decision ([] = valid).

        The gate (docs/34) makes the offline agent restate the objective before it can escalate,
        so "stop → improve the model" cannot be the path of least resistance:
          - decision must be one of PHASE6_DECISIONS;
          - any non-converge decision needs a non-empty binding_target;
          - stop_model_dev / redesign_6to0 are INVALID while experiment_count < max_experiments
            AND a named next_targeted_experiment remains (that is a rethink_6to3);
          - stop_model_dev additionally REQUIRES next_targeted_experiment == "NONE" AND a non-empty
            exhaustion_justification (you may not stop with a lever on the table);
          - rethink_6to3 is INVALID once experiment_count + 1 would exceed max_experiments, because a
            rethink SPENDS a cycle -- the guard must test the POST-increment value.
        """
        d = self.data.get("phase6_decision")
        errs = []
        if not d:
            return ["phase6_decision not set — fill it before a Phase-6 routing decision (docs/34)"]
        dec = d.get("decision")
        if dec not in self.PHASE6_DECISIONS:
            return [f"decision '{dec}' not in {self.PHASE6_DECISIONS}"]
        ec = d.get("experiment_count", 0)
        # A key PRESENT with value None returns None from .get(k, 10), not the default -- so a
        # state carrying `max_experiments: None` made this raise TypeError on `ec < mx` instead of
        # rejecting a premature stop. Coerce to the documented default and say so, rather than
        # letting the guard become unavailable at the moment it matters (2026-08-22 self-review).
        mx = d.get("max_experiments", 10)
        if not isinstance(mx, int) or isinstance(mx, bool) or mx < 1:
            errs.append(f"max_experiments is {mx!r} — not an int >= 1; treating it as 10 for this "
                        f"gate. Fix the state: the loop limit must be a number.")
            mx = 10
        nxt = (d.get("next_targeted_experiment") or "").strip()
        has_named = bool(nxt) and nxt.upper() != "NONE"
        if dec != "converge" and not (d.get("binding_target") or "").strip():
            errs.append("binding_target is required for a non-converge decision — name the "
                        "specific failing target (feedback_performance_experiment_is_the_objective)")
        if dec in ("stop_model_dev", "redesign_6to0") and ec < mx and has_named:
            errs.append(
                f"decision '{dec}' is invalid while experiment_count ({ec}) < max_experiments "
                f"({mx}) and a named in-range experiment remains ('{nxt}') — that is a rethink_6to3; "
                f"run it first (feedback_performance_experiment_is_the_objective).")
        # A rethink SPENDS a cycle, so it is only legal if the round has one left. The guard has to
        # test the POST-increment value: at ec = mx - 1 a rethink looks legal, and it is the increment
        # to mx that crosses the limit. MEASURED TWICE on one round -- at 19 of 20 the validator
        # returned no errors and the cycle's log went on to describe a "cycle 20" the budget did not
        # contain; at 21 of 21, after the PI granted one cycle over, it STILL returned no errors and
        # would have licensed a 22nd. Nothing else in the gate mentions rethink_6to3 at all, which is
        # why the round's only auto-taken route was also its only unguarded one.
        if dec == "rethink_6to3" and ec + 1 > mx:
            errs.append(
                f"decision 'rethink_6to3' is invalid at experiment_count ({ec}) of max_experiments "
                f"({mx}): a rethink INCREMENTS the counter, so it would spend cycle {ec + 1} of {mx}. "
                f"The middle loop is exhausted -- this is a round CLOSE followed by the human "
                f"converge/redesign/stop gate, not another cycle. Raise max_experiments explicitly if "
                f"the PI has granted more budget (calibration-discipline, the per-round banner).")
        if dec == "stop_model_dev":
            if has_named:
                errs.append("stop_model_dev requires next_targeted_experiment == NONE — you may not "
                            "stop with a named parameter experiment still on the table.")
            if not (d.get("exhaustion_justification") or "").strip():
                errs.append("stop_model_dev requires a non-empty exhaustion_justification "
                            "(why no in-range target-aimed experiment remains).")
            # A self-authored exhaustion_justification is NOT sufficient BELOW the loop limit: declaring
            # "next_targeted_experiment == NONE" at a low experiment_count is exactly the documented
            # premature-stop failure (2026-07-21: stop_model_dev asserted at experiment_count 0/10 while
            # XRLA-down remained an untested, source-verified residence lever — found in the very next
            # cycle). The middle loop exists to TEST the "it's futile" conviction, not trust it. So an
            # early stop needs an explicit HUMAN sign-off, not the agent's own say-so.
            if ec < mx and not bool(d.get("human_confirmed_exhaustion")):
                errs.append(
                    f"stop_model_dev at experiment_count ({ec}) < max_experiments ({mx}) requires "
                    f"human_confirmed_exhaustion=true. A self-declared next_targeted_experiment==NONE is "
                    f"not sufficient below the loop limit (feedback_never_self_declare_exhaustion): either "
                    f"drive the remaining cycles (rethink_6to3) or get explicit human sign-off.")
        return errs

    # Phases 0-5 are executed directly; phase 6 (refinement) is the convergence fork.
    RUNNABLE_PHASES = ("design", "exploration", "screening", "diagnosis", "hypothesis", "testing")

    def _round_is_closing(self, d, dec):
        """Is this refinement the ROUND's close, or just one cycle's Phase 6?

        Load-bearing distinction, and the one the first draft of this routing got wrong. Phase 6
        runs at the end of EVERY experiment cycle, so requiring the round report whenever
        `current_phase == "refinement"` would demand a round close ten times per round. A round
        closes only on `converged`, on reaching the middle-loop limit, or on a recorded routing
        decision that ends it -- `rethink_6to3` is explicitly NOT one, being mid-round by
        definition.
        """
        if d.get("converged"):
            return True
        if dec in ("converge", "redesign_6to0", "stop_model_dev"):
            return True
        mx = d.get("max_experiments")
        if not isinstance(mx, int) or isinstance(mx, bool) or mx < 1:
            mx = (d.get("phase6_decision") or {}).get("max_experiments")
        if not isinstance(mx, int) or isinstance(mx, bool) or mx < 1:
            # FALL BACK TO THE MACHINE CONFIG, exactly as `check_workflow_state_offline.py`'s
            # `resolve_max_experiments` does. This used to `return False` on the reasoning that an
            # unknown limit should not invent a close -- but the limit is never unknown: it lives in
            # `A2MC_MAX_EXPERIMENTS` in the machine config and NOWHERE ELSE, and a state that
            # carries no copy of it is the normal case, not a corrupt one, because the field is
            # written only when a Phase-6 decision is recorded.
            #
            # Measured 2026-09-08. A case sat at `experiment_count == 20` with twenty completed
            # cycles on disk and `max_experiments: null` in its state. The validator fell back to
            # the config, read 20 >= 20 and called the round closed; this method found no int,
            # returned False, and the resolver drove toward a twenty-first cycle. Two tools reading
            # one state disagreed about whether the round was over, and the one the DRIVER consults
            # was the one ignoring the budget.
            #
            # Refusing to guess is right when a value has no source of truth. This one has exactly
            # one ([[feedback_bind_derived_facts_to_their_source]]), so reading it is not a guess.
            env = os.environ.get("A2MC_MAX_EXPERIMENTS")
            mx = None
            if env is not None:
                try:
                    mx = int(env)
                except ValueError:
                    mx = None
            if not isinstance(mx, int) or mx < 1:
                mx, _ = limit_from_config("A2MC_MAX_EXPERIMENTS")
            if not isinstance(mx, int) or isinstance(mx, bool) or mx < 1:
                return False                  # genuinely no limit anywhere: do not invent a close
        return int(d.get("experiment_count", 0) or 0) >= mx

    def resolve_next_action(self) -> "NextAction":
        """Deterministic, PURE-state resolver for the offline convergence driver (docs/38 §4.3).

        Maps this state -> the next workflow action, encoding the phase graph, the Phase-6 fork,
        and the TWO round-close positions:
          - converged                       -> close(round_close) -> close(housekeeping) -> done
          - current_phase in 0..5           -> run_phase(current_phase)
          - current_phase == refinement:
              no decision, round CLOSING    -> close(round_close), THEN gate
              no decision, mid-round        -> gate (the per-cycle converge/rethink/redesign call)
              converge                      -> close(housekeeping) -> done
              rethink_6to3                  -> run_phase(diagnosis)   (UNCHANGED: mid-round)
              redesign_6to0                 -> close(housekeeping) -> run_phase(design)
              stop_model_dev                -> close(housekeeping) -> gate (human)

        THE ORDER IS THE POINT. The round report is produced BEFORE the gate is surfaced, so the
        human routes the round with its summary in hand rather than being asked to decide first;
        the housekeeping runs AFTER the gate clears, because curating knowledge is a Tier-3 write
        and one of the four human gates. A single close position cannot hold both, and putting
        them together would run a human-gated write ahead of the human gate.

        A CONVERGED round runs the housekeeping too -- with a FULLER checklist, not a skipped one
        (PI, 2026-08-25). Convergence is the CAMPAIGN boundary: it hands work to nobody, so every
        omission there is permanent, and it is the moment the site-to-generic knowledge promotion
        first becomes answerable.

        NOTE: WAIT_HPC (an ensemble in flight) and the expensive-action gates are RUNTIME concerns
        the driver overlays (they depend on squeue/monitors, not on state), so they are
        deliberately NOT resolved here -- this keeps the resolver pure + unit-testable.
        """
        d = self.data
        dec = (d.get("phase6_decision") or {}).get("decision")
        rc_done = bool(d.get("round_close"))
        hk_done = bool(d.get("housekeeping"))

        if d.get("converged"):
            if not rc_done:
                return NextAction("close", "round_close",
                                  "converged — write the round close (summarize-calibration-round "
                                  "-> compare-calibration-rounds -> write-report) before Phase 7")
            if not hk_done:
                return NextAction("close", "housekeeping",
                                  "converged — run the post-round housekeeping with its FULLER "
                                  "campaign-close checklist; nothing is skipped on convergence")
            return NextAction("done", "converged", "all targets met — Phase 7 CONVERGED")

        phase = d.get("current_phase", "design")

        # THE MIDDLE-LOOP LIMIT IS CHECKED BEFORE ANY run_phase, NOT ONLY IN THE REFINEMENT BRANCH.
        #
        # Measured 2026-09-08 on a case at `experiment_count == max_experiments == 20`, with twenty
        # completed cycles on disk: the resolver returned `run_phase(diagnosis)` and would have
        # driven a twenty-first, while `check_workflow_state_offline.py` called the same state
        # closed. The two disagreed because the limit test lived only in the `refinement` branch,
        # and a `rethink_6to3` sets `current_phase = "diagnosis"` -- which is runnable, so the
        # branch above returned before `_round_is_closing` was ever consulted. The budget was
        # therefore unenforced along the ONE path every cycle takes.
        #
        # `not rc_done` is what keeps this from firing after a redesign: the post-redesign
        # `run_phase("design")` is reached only once the close AND the housekeeping are recorded.
        if not rc_done and self._round_is_closing(d, dec):
            return NextAction("close", "round_close",
                              "the middle loop is at its limit (experiment_count == "
                              "max_experiments) — write the round close before anything else, so "
                              "the Phase-6 gate is decided with the report in hand")

        if phase in self.RUNNABLE_PHASES:
            return NextAction("run_phase", phase, f"execute the {phase} phase skill")

        if phase == "refinement":
            closing = self._round_is_closing(d, dec)
            if not dec:
                if closing and not rc_done:
                    return NextAction("close", "round_close",
                                      "the round is closing — write the round close BEFORE the "
                                      "gate, so the decision is made with the report in hand")
                return NextAction("gate", "refinement",
                                  "Phase-6 converge/rethink/redesign/stop decision needed "
                                  "(fill phase6_decision, then validate_phase6_decision)")
            if dec == "rethink_6to3":
                return NextAction("run_phase", "diagnosis",
                                  "Phase-6 rethink — next experiment cycle, back to diagnosis")
            # every remaining decision ENDS the round: close it, then do the housekeeping the
            # cleared gate authorises, then route.
            if not rc_done:
                return NextAction("close", "round_close",
                                  f"Phase-6 '{dec}' ends the round — write the round close first")
            if not hk_done:
                return NextAction("close", "housekeeping",
                                  f"gate cleared ('{dec}') — run the post-round housekeeping "
                                  f"before the next round opens")
            if dec == "converge":
                return NextAction("done", "converged", "Phase-6 decided converge — Phase 7 CONVERGED")
            if dec == "redesign_6to0":
                return NextAction("run_phase", "design",
                                  "Phase-6 redesign — widen the space, next calibration round")
            if dec == "stop_model_dev":
                return NextAction("gate", "refinement",
                                  "Phase-6 stop -> model-dev — HUMAN gate (must pass validate_phase6_decision)")
            return NextAction("gate", "refinement", f"unknown phase6 decision '{dec}'")
        return NextAction("gate", phase, f"unknown current_phase '{phase}' — resolve manually")

    # ---- read helpers (for the SessionStart hook) ----
    def summary_line(self) -> str:
        """One-line snapshot for cold start, e.g. the SessionStart hook."""
        d = self.data
        nt = len(d.get("open_threads", []))
        nxt = ""
        if d.get("open_threads"):
            nxt = " (→ next: %s)" % (d["open_threads"][0].get("next_action", "")[:80])
        return "R%s · %s · cycle %s · %d open thread%s%s" % (
            d.get("calibration_round"), d.get("current_phase"),
            d.get("experiment_count"), nt, "" if nt == 1 else "s", nxt)


if __name__ == "__main__":
    # tiny self-check (no file writes): build a blank, mutate, print
    st = WorkflowStateOffline(site_dir="use_cases/TEMPLATE", calibration_round=5)
    st.set_position(current_phase="diagnosis", experiment_count=0)
    st.add_diagnosis("20260704a_phase3_diagnosis_r05_c00_iter01_demo",
                     "logs/demo.md", "phase_results/demo/", "demo one-liner")
    st.add_thread("demo_thread", summary="do the thing", next_action="cap the bound", priority=1)
    print("path:", st.path)
    print("summary:", st.summary_line())
    print("evidence diagnoses:", len(st.data["evidence"]["diagnoses"]))
