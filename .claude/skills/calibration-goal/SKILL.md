---
name: calibration-goal
visibility: public
category: calibration
description: The offline agent's run-to-convergence DRIVER — the conductor above the phase skills. Use when the user says "run the calibration", "drive it to convergence", "keep calibrating until the targets are met", "continue the calibration loop / to the goal", or sets a standing goal to reach the validation targets. Each invocation loads WorkflowStateOffline, resolves the next action, dispatches to the matching phaseN skill, advances + saves state, and repeats across turns + HPC waits until Phase-7 CONVERGED or a loop limit — pausing ONLY at the four human gates. Harness-neutral (no dependency on any coding-agent's features). DISTINCT from onboard-session (cold-start orient) and a single phaseN skill (one phase).
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [calibration]
  summary: "Run-to-convergence driver: advances the offline 7-phase loop to CONVERGED, pausing only at the human gates. Model-agnostic."
---

<!-- ─────────────────────────── At a glance ─────────────────────────── -->
```text
each invocation (or re-invocation):
  st = WorkflowStateOffline.find_latest()
  na = st.resolve_next_action()          # done | run_phase(N) | gate
  classify at runtime:
     converged / limit  → DONE   (Phase 7; summarize the round)
     HPC in flight       → WAIT   (arm monitors; stop — a trigger resumes you)
     a human fork        → GATE   (pause; surface the decision)
     mechanical step     → RUN the phaseN skill → advance st → save → loop
  drive until DONE; pause only at the 4 gates; never silently halt with work outstanding
```

# calibration-goal — the offline run-to-convergence driver

**The conductor.** The online agent stays on-task because `orchestrator.py --run` is a blocking `while`
loop (`:1031`). The offline (interactive) agent is turn-based and cannot block for the days an HPC
ensemble takes — so its loop is **not a process**: it is *state on disk + this per-invocation driver +
re-invocation triggers + the same convergence/limit exit*. This skill is that driver. Full design +
rationale: **`docs/43`**.

**Harness-neutral (load-bearing).** This skill runs on any coding agent (Claude Code, Cursor, Aider,
…) using only: `WorkflowStateOffline` + this skill + `AGENTS.md` rule 10 + whatever re-invocation the
harness provides. It takes **no** dependency on any platform feature. A harness stop-guard (e.g. Claude
Code's `/goal` — "check a goal before stopping") can *optionally harden* the "don't stop early" habit,
but is never required; where absent, you apply the stop-classification below yourself.

## When to use (vs. onboard-session vs. a single phase skill)

```
Cold start / "where are we?"           → onboard-session (orient, resume, then hand to this)
Run/continue the WHOLE calibration
  to the goal (converge on targets)    → calibration-goal (this skill — the driver loop)
Do exactly ONE phase                   → phase{0..6}-* directly
```

`calibration-goal` **delegates** "what's next" to `WorkflowStateOffline` (+ `onboard-session`'s resume
brain) and **dispatches** the work to the `phase{0..6}` skills — it does not re-implement them.

## The driver loop (run this every invocation)

Mirrors `orchestrator.py` `run()`; the loop lives on disk, so each invocation is one iteration.

**0. Entering calibration mode — arm the discipline self-review (first invocation of a drive, and
after any session boundary).** Arm the time-based backstop with a real timer (`CronCreate`,
off-minute, e.g. `17 */3 * * *`) and hold the per-phase review in force for every step below: after
each phase skill completes, re-check the [`calibration-discipline`](../calibration-discipline/SKILL.md)
items for that phase BEFORE advancing the state. This is automatic — it does not wait to be
requested. Timers are session-only, so re-arm at session start
(memory `feedback_schedule_periodic_reviews_with_a_real_mechanism`).

1. **Load state.** `st = WorkflowStateOffline.find_latest(site_dir)` (highest-round singleton at
   `use_cases/{Model}_{Case}/memory/workflow_state_offline_r{RR}.json`). If none, this is a fresh run — route
   to `phase0-design` and initialize the state. **Validate it first:**
   `python3 tools/check_workflow_state_offline.py` (must exit 0 — the state analog of
   `check_skill_registry`; a corrupt/overrun state misdrives the whole loop, so fix it before driving).
2. **Resolve the next action (pure state).**
   ```python
   from tools.workflow_state_offline import WorkflowStateOffline
   st = WorkflowStateOffline.find_latest()
   na = st.resolve_next_action()   # NextAction(kind, phase, detail); kind ∈ {done, run_phase, gate}
   ```
3. **Classify + act** (the runtime overlay on top of the pure resolver — WAIT and the KB/irreversible
   gates depend on `squeue`/monitors, not on state):
   - **`na.kind == "done"`** → the calibration is CONVERGED (or a terminal limit). By this point the
     resolver has already routed you through BOTH close positions, so the round summary, the
     cross-round ledger, the ROUND report and the housekeeping all exist. Write the **final
     configuration** — seven required elements, specified in
     [`phase6-refinement`](../phase6-refinement/SKILL.md) under "The Phase-7 CONVERGED deliverable",
     and **not** a free-form paragraph: `check_workflow_state_offline.py` asserts a converged state
     carries a resolvable pointer to it. Then stop. **DONE.**
   - **`na.kind == "close"`** → a ROUND-CLOSE step. **EXECUTE it; never surface it as a gate.** Then
     re-resolve — the resolver decides what follows, not you.
     - **`na.phase == "round_close"`** → the **three steps, IN ORDER, and the middle one is the one
       that gets skipped**: [`summarize-calibration-round`](../summarize-calibration-round/SKILL.md)
       → [`compare-calibration-rounds`](../compare-calibration-rounds/SKILL.md) →
       [`write-report`](../write-report/SKILL.md) (the ROUND report). Then
       `st.set_round_close(report_path=…, summarize=…, compare=…, report=…)` and `st.save()`.
       `compare-calibration-rounds` is a **step, not an option**: skipping it is how one round
       summary re-proposed two parameters earlier rounds had already refuted with named mechanisms.
     - **`na.phase == "housekeeping"`** → the post-round curation, **after** the gate has cleared:
       `round-housekeeping` (curate the round's verified findings, promote or discard the staged
       proposals, record the case's script templates, emit the open-questions list, record the
       bound debt, assert the KB is non-empty where the round produced findings). Then
       `st.set_housekeeping(…)` and `st.save()`.
       **A converged round runs this too, with a FULLER checklist** — convergence is the CAMPAIGN
       boundary and hands work to nobody, so every omission there is permanent (PI, 2026-08-25).

     **Why two positions and not one.** The report is written BEFORE the gate so the human routes
     the round with its summary in hand; the housekeeping runs AFTER, because curating knowledge is
     a Tier-3 write and one of the four gates below. A single position would run a human-gated write
     ahead of the human gate.
   - **an HPC ensemble for the current phase is in flight** (a submitter/ensemble is running, not yet
     complete) → this is a **WAIT**: (re-)arm monitors (`arm-hpc-monitoring`) and stop cleanly — a
     re-invocation trigger (a Monitor/log event, a human continue, or a scheduler) will resume the loop
     when the ensemble finishes. *Waiting is a correct stop, not abandonment — do not poll in a turn.*
   - **`na.kind == "gate"`, or the step is a curated-KB write / an expensive-irreversible action** →
     **GATE**: pause and surface the decision to the human. Do NOT drive past it. (See gates below.)
   - **`na.kind == "run_phase"`** and the step is mechanical → **EXECUTE**: invoke the matching phase
     skill (`na.phase` → `phase{N}-*`), or the concrete next action (extract completed data, regen a
     plot, skip-test on existing data). Then **advance the state** (`st.set_position(...)`, add the
     evidence pointer, apply the counter changes for a fork) and **`st.save()`**.
4. **Loop.** Return to step 1. Within a session, rule 10 (and a harness stop-guard where present) keeps
   you advancing; across an HPC wait, the re-invocation trigger restarts the loop.

## The stop-classification (the 3 VALID stops — before ending a turn)

Never end a turn with a mechanical step outstanding. A stop is valid ONLY when one holds:

- **(done)** `st.converged`, or a loop limit reached (`experiment_count == max_experiments` at a round
  that cannot widen further) → report Phase 7 / the terminal state.
- **(wait)** an HPC ensemble for the current phase is in flight with monitors armed → let a trigger
  resume you.
- **(gate)** a human decision is required (the four forks below).

Respect the three loop limits (`max_skip_testing` / `max_experiments` / max rounds). "wait" and "gate"
are correct stops; a silent halt with an actionable next step is the failure mode this driver removes
(FM-3, docs/35).

## The gates — pause, hand back to the human (never drive past)

1. **Phase-6 converge / redesign / stop-model-dev** — the hard fork. **The round report is already
   written when this gate is surfaced** (the resolver routes `close(round_close)` first), so the human
   decides with the summary, the cross-round ledger and the next-round plan in front of them rather
   than being asked to route a round whose summary does not exist yet. At Phase 6, fill `phase6_decision`
   and call **`st.validate_phase6_decision()`**; it structurally blocks a premature `stop_model_dev` /
   `redesign_6to0` while a named in-range experiment + budget remain (that is a `rethink_6to3`, which the
   driver auto-takes — 6→3, `experiment_count++`). Surface only the genuinely human forks
   (converge, redesign, or an earned stop-model-dev). This is FM-2 (docs/34) — it keeps "drive to the
   goal" from becoming "bail out early."
2. **A curated-KB write** (`inject-knowledge` / `curate-knowledge`) — the Tier-3 write gate; human-vetted.
3. **An expensive / irreversible action** — a full-ensemble redesign, a large HPC spend.
4. **A standing hard stop** — destructive/outside-repo action, a claim about the user, an ambiguous
   instruction (AGENTS.md rule 9 + the offline-agent operating discipline).

## The exit (identical predicate to `--run`)

Terminate exactly when `orchestrator.py:1031` would: **`st.converged == True`** **OR** the middle loop is
exhausted at a round that cannot widen further (→ a human stop/redesign fork). The three loop limits
bound it.

**Neither exit is reachable without the round close.** `resolve_next_action()` routes a converged state
through `close(round_close)` and then `close(housekeeping)` before it will return `done`, so Phase 7
cannot be declared with an unwritten report or uncurated knowledge. Clear any harness driving-goal only
after `done`.

## Guardrails

- **Do not re-implement the phases** — dispatch to `phase{0..6}` skills; they carry the per-phase
  discipline (incl. the FM-1 evidence gate, `check_offline_log_evidence.py`).
- **Do not embed a harness feature** — no `/goal`/`Monitor`/`/loop` as a *requirement*; they are
  optional hardenings. The skill must run on a bare harness (this skill + rule 10 + human/scheduled
  resume).
- **Do not spin on an HPC wait** — arm monitors and stop; let the event resume you. Polling in a turn
  wastes it.
- **Do not drive past a gate** — the four forks are the reason the interactive runtime exists (judgment
  + curated-knowledge authority). Surface, don't decide.
- **Always `st.save()` after a state change** — the loop is on disk; an unsaved advance is lost at the
  turn boundary.

## Cross-references


- **Reciprocal skills** — `summarize-calibration-round`, `compare-calibration-rounds`, `write-report`: the three ordered steps this driver dispatches at `close("round_close")`. Each names this skill back, so the relationship is visible from the side that matters — the skill that has to be loaded. Enforced by `tools/check_skill_registry.py::reciprocity_check`, which validates only DECLARED links, so an undeclared edge stays invisible by construction.
- `docs/43_Offline_Agent_Goal_Driven_Convergence_Loop.md` — the full design (this skill is §4.3).
  (Renumbered from `docs/38` on 2026-08-26; two documents shared that number.)
- `tools/workflow_state_offline.py` — `WorkflowStateOffline` (the program counter) + `resolve_next_action()`
  + `validate_phase6_decision()`.
- `onboard-session` (cold-start orient/resume — hands off to this), `phase0-design` … `phase6-refinement`
  (the dispatched executors), `arm-hpc-monitoring` (the WAIT bridge), `summarize-calibration-round`
  (round exit), `a2mc-init` (setup can hand off directly into a driven run).
- `plotting` — any figure a dispatched phase produces goes through it; load before the first
  `savefig`, since its view-the-rendered-PNG rule is what catches a broken figure.
- `AGENTS.md` rule 10 (drive-don't-wait) + §"Offline-Agent Operating Discipline" (the FM-1..4 gates).

## Changelog

- 2026-08-16: **Names the `plotting` skill.** The link was one-directional — `plotting` claimed
  these skills apply its conventions while they never mentioned it, so a whole case's figures
  could be produced without the conventions or the view-the-PNG check being loaded. PI-directed.
- 2026-07-15: Driver loop Step 1 now validates the state via `tools/check_workflow_state_offline.py` (exit 0 before driving — the state analog of `check_skill_registry`). Ported from demo `d3cbbf5` (offline-workflow enforcement sweep).
- 2026-07-11: Initial version — the offline run-to-convergence driver (docs/43, numbered docs/38 at the time). Harness-neutral: the
  conductor above the phase skills, mirroring `orchestrator.py:1031` via `WorkflowStateOffline` +
  `resolve_next_action()`, pausing only at the four human gates. Distilled from `docs/43` + the
  implementation tracker `memory/dev_logs/20260711h_*`.
