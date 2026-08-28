---
name: phase6-refinement
visibility: public
category: phase
description: Run Phase 6 (REFINEMENT) of the A2MC calibration workflow as the offline agent — the human-in-the-loop analog of the orchestrator's `_run_refinement()` / `reasoning.interpret_results()` + `extract_lesson()`. Evaluate the experiment results vs baseline + expected outcomes, extract lessons (discoveries / failed approaches), update Adaptive Memory, and decide convergence — converged, rethink (6→3), or redesign (6→0). Use when the user says "evaluate the results", "did the experiment work", "extract the lessons", "run Phase 6", "should we converge or iterate", "what did we learn", after Phase 5 testing.
modes:
  requires_fates: false      # calibration-workflow phase skill; mode resolved at runtime via describe_mode
  nutrient_pathway: any
  scope: [calibration]
  summary: "Offline analog of Phase 6 (evaluate, learn, converge/iterate). Applies in every calibration mode."
---

# Phase 6: Refinement (offline agent)

> **Driven by `calibration-goal`** — the run-to-convergence driver dispatches here for the **convergence fork**: this phase's converge/redesign/stop decision (`validate_phase6_decision`) is the driver's branch point AND a human gate (the driver auto-takes a `rethink_6to3`, pauses for converge/redesign/stop). Also runnable standalone.

The offline analog of `_run_refinement()`. Online, `reasoning.interpret_results()` +
`extract_lesson()` evaluate and learn automatically; **offline, YOU do both** — judge the experiment
honestly against expectation, name the mechanism you learned, and decide where the loop goes next.

> **Floor, not ceiling.** The online agent classifies confirmed/partial/rejected and picks the next
> phase. As the offline agent you can do the deeper work the loop can't: a full equifinality /
> cross-regime analysis (`scientific-analysis`), a manuscript figure, reconciling this result with
> prior rounds (`compare-calibration-rounds`), or deciding a finding is worth curating into the KB.
> Evaluate at least as rigorously as the online agent, then reason past it.

**Critical mode difference — the memory write gate.** The online agent runs Memory in **propose**
mode (stages to `auto_discovered_pending.json`, cannot write curated knowledge). **You, the offline
agent, are the disposer** — you write curated knowledge directly (interactive mode) and you promote
the online agent's staged proposals. "Online proposes, offline disposes." This is *the* thing Phase 6
does differently offline.

**Inputs (from Phase 5):** experiment results (per-target metrics, extraction status) + the Phase 4
expected outcomes. **Deliverable:** honest per-hypothesis verdict, lessons written to Memory, a
convergence decision.

## Step 1 — evaluate the results (reads existing experiment results — no new simulations)

`phases/phase6_refinement/evaluate_results.py` compares each experiment to expected outcomes and to
the Phase 2 baseline → outcome class (SUCCESS / PARTIAL / MARGINAL / FAILED), best experiment,
targets met.

> **Footgun — data-reliability gate.** A *silent* extraction failure (no error, empty metrics) reads
> as 0/6 targets and looks like a real FAILED result. Confirm `extraction_status == "extracted"` AND
> non-empty metrics AND no `error` before trusting any outcome — otherwise you contaminate the KB
> with a phantom failure.

## Step 1b — extract the FULL results + comparison plots (experiment Phase 6; esp. TIME SERIES)

For an **experiment** (N variants on a base case), Step 1's `evaluate_results.py` gives the per-target
*numbers at the observation month*, but Phase 6 also needs the **full extracted series and the visual
comparison vs observations** to judge honestly and to report.

### The requirement (model-NEUTRAL — this half applies to every model)

**Produce a sim-vs-obs TIME-SERIES overlay covering EVERY SCORED TARGET, before writing the verdict,
and include it in the cycle report.** Concretely:

- **one panel per scored target**, not one panel for the target the experiment aimed at. An
  intervention that moves its own target while pushing two others out of band has *failed*, and a
  single-target figure cannot show that. Measured: one cycle's report shipped a one-target figure
  while two of its variants had taken both other targets out of band — half the verdict, invisible.
- **the observation drawn as it was measured.** If the record is a series, plot the series: per-year
  points with their spread, and **gaps left as gaps**. A flat line at the multi-year mean is a
  *summary* of the observation, not the observation, and it hides both the spread and the years
  nobody measured.
- **the control on top**, so V0-tracks-its-base is visually confirmed rather than asserted.
- **the trajectory, not just the endpoint** — did the variant equilibrate, collapse late,
  overshoot-then-crash, or oscillate? That is what a single endpoint metric hides, and it is usually
  where the mechanism is.

### The implementation (model-SPECIFIC — do NOT inherit the wrong one)

**The requirement above is not carried by any one tool, and binding it to one is how it got lost.**
Until 2026-08-22 this step named only the FATES driver, so on a model where that driver does not run
the requirement silently left with it — measured on an adapter model whose Phase-6 cycles produced no
such figure at all, because nothing in its own run procedure asked for one.

| model family | the driver for this step |
|---|---|
| **ELM / ELM-FATES** (CIME) | `tools/extract_and_plot_selected_cases.py`, below |
| **a non-CIME adapter model** | that model's own run skill — `ecosim-run-workflow`, `pflotran-run-workflow`, `ats-run-workflow` — each owning its tape layout, its reducers and its calendar. For PFLOTRAN the panels are the ten outflow concentrations plus the hydrograph, scored through each target's own `reduce` via `tools/pflotran_evaluate_case.py`, on the target's OWN window (the chemistry ends at model hour 1574, the hydrograph at 1612 — they are different datasets and must not share one) |

If your model has no driver yet, **write the figure script into `phase_results/{stem}/` as canonical**
and satisfy the requirement there; do not skip it because no tool exists. Score every series through
the **target's own `reduce` and `tape`**, never a reimplementation, or the figure disagrees with the
scores for a reason no reader can see.

**For ELM / ELM-FATES**, use **`tools/extract_and_plot_selected_cases.py`** — the promoted successor
to the retired `use_cases/{Model}_{Case}/analysis/` one-off overlay scripts; **do NOT resurrect those**, and do
not edit the `_exp`-gated production extractor ([[feedback_do_not_change_extractor_case_naming]]).
**It is FATES-only**: it imports `extract_monthly_variables_FATES`, sums over SZPF size classes, and
is `_exp`-gated, so it cannot run on an adapter model:

- **`extract`** — pull the full monthly target variables (e.g. `FATES_LEAFC_SZPF` / `FATES_FROOTC_SZPF`)
  for every variant into the extract dir. It reuses the production `process_case()` and handles the
  **non-`_exp`** experiment suffixes this driver is for.
- **`v0check`** — confirm each V0 control reproduces its base within tolerance BEFORE interpreting any
  variant (the Step-10 gate).
- **`plot`** — the **time-series overlay**: one colored line per variant over the transient years, in a
  PFT × (target) panel grid, with the observation tolerance band (`axhspan`) + obs marker. This follows the
  **A2MC ensemble figure template** (`plotting` skill) — same obs-diamond / ±20%-band / units convention as
  the whole-ensemble plot, but with **solid opaque colored variant lines** (few lines, not a cloud) and the
  control **black-dashed on top**. Pass **`--baseline <ctrl case id or suffix>`** to dash-highlight the
  control so `split − ctrl`-style comparisons read at a glance — the others stay colored solid.

**The time series is REQUIRED, not optional** — see the model-neutral statement above for what it
must cover ([[feedback_figures_over_tables_over_words]]). Every figure gets a caption + a
plain-finding explanation in the log, and its script is canonical in `phase_results/{stem}/` (copied from the case template in `use_cases/{Model}_{Case}/scripts/` and adapted there): a figure
needing a change is edited and regenerated **there**, never patched beside the report.

## Step 2 — interpret + extract lessons (you are the reasoning)

Mirror `interpret_results` (targets improved/degraded, hypothesis_status **honestly** — partial is
PARTIAL, not SUCCESS; cross-PFT impact) and `extract_lesson` (is it a **discovery**? a **failed
approach**? a named pattern — Allocation Paradox, Perfect Storm, Mortality Trap?). Verify any
mechanism against RAG before asserting it.

## Step 3 — update Adaptive Memory (offline = curated, direct)

- **Vetted new discovery / failed approach you originated** → write it via `inject-knowledge`
  (interactive mode writes the curated JSON directly through `memory/manager.py`).
- **The online agent's staged proposals** (`auto_discovered_pending.json`) → review + promote/discard
  via `curate-knowledge` (`tools/review_pending_knowledge.py`). This is the Tier-3 write gate.

## Step 3b — promote reusable scripts into the shared library (round close)

Knowledge is not the only reusable output — a **diagnostic/analysis script** that proved reusable this
round should graduate out of its scratch home so future rounds/sites auto-discover it (the tooling analog
of "online proposes, offline disposes"). Human-gated; promote only genuinely reusable scripts, not one-offs.

- **Online agent's generated scripts** — `phases/phase3_diagnosis/generated/*.py` →
  `phases/phase3_diagnosis/` via `tools/promote_diagnostic_script.py` (`--list` → `--script <n> --dry-run`
  → promote; it copies the file and registers the tool in `DIAGNOSTIC_TOOLS_INVENTORY` so future runs
  auto-discover it). Full contract: `phases/phase3_diagnosis/generated/README.md`.
- **Your (offline) scripts** — the reusable ones you wrote into `use_cases/{Model}_{Case}/memory/phase_results/{stem}/`
  → `tools/` (a generic analysis utility) or `phases/phase3_diagnosis/` (a reusable `test_hypothesis`), via
  `tools/promote_diagnostic_script.py --source <path> --dest tools|phase3_diagnosis` (`--dry-run` first;
  `--dest tools` just copies, `--dest phase3_diagnosis` also registers it in `DIAGNOSTIC_TOOLS_INVENTORY`).
  Leave one-off figure scripts in `phase_results/{stem}/` — they are the log's evidence, not library code.
- **Generalize the promoted copy before committing** — promotion is copy-**then-generalize**. A
  `phase_results/{stem}/` script hardcodes its output path, stem, and case IDs; the library copy must be
  site/run-agnostic, so edit it to strip hardcoded paths/stems/case/site names and parameterize inputs
  (argparse or `tools/config.py`) — CLAUDE.md rules 5 + 8. The tool prints this reminder after copying.

## Step 4 — decide where the loop goes (GATE on the middle-loop counter)

The online orchestrator enforces this fork in **code** (`orchestrator.py` state machine: `experiment_count`
vs `max_experiments`), so it physically cannot skip a cycle. **Offline you must enforce the SAME gate by
hand** — the offline agent matches or exceeds the online loop discipline, it never rushes past it. **Read
`experiment_count` / `skip_testing_count` from `workflow_state_offline_r{RR}.json` before deciding.**

### The RETHINK PROTOCOL — what a 6→3 actually requires

`rethink_6to3` is the default route and, until now, only a counter increment. A cycle that re-enters Phase 3 carrying the previous cycle's base, binding target and lever class forward unexamined is not a new cycle, it is the same cycle with one parameter changed. Measured on one round: three consecutive rethinks ran on one base and attacked one target, and the cycle that finally re-examined both found the base was structurally wrong for the question being asked and that the binding target had moved.

A rethink is therefore a synthesis, not a routing decision. It has two halves — what THIS cycle did and learned, and what the WHOLE round already knew — and the pathways come from reading the second against the first. Answer all six in the log before recording the decision. Every one is settled by existing data at zero compute.

1. **Synthesize THIS cycle, phases 3 through 6.** What was hypothesized and on what mechanism; what each inner-loop iteration asked and returned, including the ones that refuted the cycle's own earlier iterations; what was actually run and what it scored per target; and what the verdict was against the pre-registered bar. State what the cycle ESTABLISHED separately from what it merely tried — a refuted hypothesis that localized a cost is a finding, and carrying only "it failed" forward loses it.
   **Write this once.** It is the same synthesis the CYCLE report needs (`write-report`), so produce it here and let the report draw on it rather than deriving it twice from the raw logs.
2. **Re-read Phase 1 and Phase 2 AGAINST that synthesis, not for citation.** The sensitivity ranking and the screening leaders were computed before the round learned what it now knows, so the question is what they say that this cycle's result makes newly relevant. Check the artifact's OWN caveats too: a ranking computed over a population that includes runaway cases ranks levers by their behaviour in a regime the calibration never occupies, and a leader list may include the unperturbed baseline as though it were an ensemble member.
3. **Is the BASE still right for the question now being asked?** A base is chosen to fix one target; the binding target moves. Check explicitly whether the base still has headroom on the targets it already holds. A base sitting at a band edge on the target the next experiment would move is the wrong base, however good its overall score.
4. **Has the BINDING TARGET moved?** Re-derive it from the current best configuration rather than inheriting the previous cycle's framing.
5. **What CLASS of lever has the round now exhausted, and what class is untried?** Group the refuted cycles by mechanism class, not by parameter. Three cycles refuting three parameters in one class is one refutation, and the next cycle should leave the class.

6. **For each refuted lever: which DIRECTION was moved, from a base with which SIGN of miss, and does that still apply?** A refutation is a property of a **(parameter, direction, base)** triple, not of a parameter, and question 5 does not catch this because it groups by mechanism rather than by direction. A lever refuted for failing to *lower* a target at a base where that target was too *high* has never been tested for *raising* it at a base where it is too *low* — and a dose response that moved monotonically the wrong way is **positive evidence for the opposite direction**, not a closed door. So tabulate it: parameter, direction moved, the base's own miss sign at the time, and whether the opposite direction has ever been run. Then check the two ways the answer can be "no, and it still cannot be": the opposite direction may be **out of bounds or past a physical ceiling** (extrapolate the dose and compare against both the calibrated bound and any structural limit, e.g. a fraction that cannot exceed 1), or the base may have **no headroom left** in that parameter. Where neither holds, the opposite direction is an untested experiment the round has been treating as refuted.

   **Measured, and it is why this question exists.** In one round three consecutive cycles refuted levers at a base whose flux target sat *in band near its ceiling*, so their job was to protect or lower it. The next cycle moved to a base missing that same target *from below*, inverting the job, and nothing re-read the inventory when the sign flipped. One of those "refuted" cycles had lowered a rate constant and watched the target fall 48 percent, which **confirms** its screened sign from the opposite side; the parameter sat at the 4th percentile of its range at the new base with nearly ten times its value available upward, and it took a question from the PI to surface it. The rethink that ran an hour earlier produced three pathways and none was this one.

**Deliverable: NEW PATHWAYS, plural, handed to Phase 3.** A rethink emits candidate pathways, each naming **what kind of move it is** and what would falsify it, rather than a single continuation of the refuted hypothesis. The kind is usually a lever class (question 5), but question 6 makes two others first-class: a **DIRECTION** on a lever the round already believes it refuted, and a **BASE CHANGE**, which is not a lever at all. A pathway that only says "change the base" is weak — say what to rank by, since a criterion is actionable and an instruction to look again is not. And a diagnostic pathway that costs no compute outranks an experiment when its outcome would decide which experiment to run. Record them with `st.add_decision(...)` and name them in `set_phase_handshake(handed_to=...)` so Phase 3 receives them instead of re-deriving them.

**Structural objective gate (docs/34) — fill it, don't skip it.** Before recording a decision, populate the
`phase6_decision` block and run the validator; a failing check **blocks** the escalation (it cannot be the
path of least resistance):

```python
from tools.workflow_state_offline import WorkflowStateOffline
st = WorkflowStateOffline.load(calibration_round=RR)
st.set_phase6_decision(decision="rethink_6to3",           # converge | rethink_6to3 | redesign_6to0 | stop_model_dev
    objective="6 targets", best_so_far="3/6", binding_target="<the specific failing target>",
    next_targeted_experiment="<named, in-range, target-aimed experiment aimed at binding_target> | NONE",
    exhaustion_justification="<why no in-range experiment remains> | ''", max_experiments=10)
violations = st.validate_phase6_decision()   # MUST be [] before you act
```
`stop_model_dev` / `redesign_6to0` are rejected while `experiment_count < max_experiments` and a named
`next_targeted_experiment` remains (that is a `rethink_6to3`); `stop_model_dev` also requires
`next_targeted_experiment == NONE` + a non-empty `exhaustion_justification`. On `rethink_6to3`, advance the
counter via `st.set_position(experiment_count=experiment_count+1)` and `st.save()`.

- **All targets met** → converged (Phase 7). The resolver routes through BOTH close positions before `done`: the round close (three report steps) and then the housekeeping with its **fuller** campaign-close checklist. The terminal deliverable is the **final configuration** — see the contract below; it is six required elements, not a phrase.
- **NOT met, `experiment_count` < `--max-experiments` (**`$A2MC_MAX_EXPERIMENTS`**, from the machine config (`a2mc_noncime_config.sh` / `a2mc_config.sh`); 10 if unset)** →
  **6→3 rethink is the DEFAULT.** Do NOT
  escalate while the cycle budget remains. Before choosing anything other than rethink, confirm there is **no
  named, in-range, target-aimed parameter experiment left to run** ([[feedback_performance_experiment_is_the_objective]]);
  if one remains — including a lead flagged in a prior log — that **is** the next rethink cycle, run it.
  **On routing 6→3: increment `experiment_count` in the state file.**
- **NOT met, `experiment_count` = `--max-experiments`** (middle loop exhausted) → **6→0 redesign**: back to
  `phase0-design` with widened bounds; increment `calibration_round`. Redesign earlier is justified ONLY if
  every remaining candidate is a Morris-bound **edge** parameter (a redesign signal, not a Phase-4 knob) AND
  no in-range experiment remains — the exception, not the default.

> **"Stop → improve the model" is NOT a loop branch.** Modifying model source is *outside* the A2MC
> calibration loop; it is justified only after the loop is **provably exhausted** (rethink cycles to the cap,
> then redesign) OR a structural impossibility is **proven by exhausting the targeted experiments**, not
> asserted from one result. Jumping there with `experiment_count` cycles still on the clock is the rush this
> gate prevents.

## Step 5 — log, report, hand off

> **The log is a LIVING record — start it now, enrich as the phase runs.** Not an end-of-phase
> write-up: the operational detail (job/array IDs, which cases failed, what was restarted) is
> unrecoverable a week later. Full contract in `calibration-log`.
>
> **This phase's expected sections** — `PhaseLogger` names any you leave empty:
> Target Changes · AI Reasoning and Deep Analysis · Lessons Learned · Discoveries (for gained_knowledge) · Failed Approaches (DO NOT REPEAT) · Experiment Results Summary.
>
> **Set the handshake before the `log_*` call**, so the chain is traceable:
> ```python
> logger.set_phase_handshake(
>     inherited_from="<predecessor log STEM> — what it concluded / asked of this phase",
>     handed_to="<what Phase 3 / 0 / 7 receives; mirror the reasoning/schemas.py field names>",
>     next_action="<the one concrete thing Phase 3 / 0 / 7 should do>")
> ```
> The log also carries `## Reasoning chain`, rebuilt from `workflow_state_offline` — so keep that
> state updated with the FINDING, not a label; the chain is only as good as what each phase wrote.


Log via `calibration-log` (phase log → `PhaseLogger.log_refinement`). Standardized reporting:
`summarize-calibration-round` (this round) / `compare-calibration-rounds` (vs prior). Then route per
Step 4. **Evidence gate (docs/33):** the refinement log must cite the evaluation artifact produced this
session (the biomass/target extraction + figure in `phase_results/{stem}/`); run
`python tools/check_offline_log_evidence.py <log.md>` (exit 0) before curating any lesson.

## Scripts: start from the case TEMPLATE, adapt it HERE

**Every script this phase writes follows the three-tier rule** (`calibration-discipline` item 2b):

```
use_cases/{Model}_{Case}/scripts/     the canonical script TEMPLATE   (seeded at onboarding)
        │  copy into this phase's folder, then ADAPT for this phase's purpose
        ▼
memory/phase_results/{stem}/          the canonical SCRIPT for this figure, beside its
                                      caption, data and notes -- this is the log's evidence
```

1. **Look in `use_cases/{Model}_{Case}/scripts/` first.** If a template covers what this phase needs, copy it into this phase's `phase_results/{stem}/` and adapt it there. Do not run it from `scripts/` and do not edit the template to suit one phase: the template is the shared shape, the copy is this phase's instrument.
2. **If there is NO template, write one from scratch** in `phase_results/{stem}/`. That is the correct first-use state and nothing is wrong with it.
3. **On a script's SECOND use, promote it to `scripts/` as the template**, then copy it back into the new phase's folder and adapt. Second use is the trigger, not third.

**This does not conflict with "one canonical script per figure, never two copies."** The canonical *script* always stays with its figures; the canonical script *TEMPLATE* stays in `scripts/`. Different artifacts, different jobs.

**Why it is a rule and not a preference:** measured on one site, `phase_results/` held **7 script names duplicated across stem folders, all 7 byte-identical** -- each a Phase-5 script copied verbatim into its Phase-6 folder, because there was nowhere for a reusable script to live. `tools/check_case_script_tier.py` (pre-commit 15, WARN) flags the next one.

## Related skills / next phase

- **`round-housekeeping`** — the POST-ROUND curation step, run AFTER the Phase-6 human gate and before the next Phase 0. It SEQUENCES the procedures rather than restating them, so this skill remains their single definition; it also asserts the outcome, which nothing did before.

- **ANY figure this phase produces** → **`plotting`**. Load it BEFORE the first `savefig`,
  not after: its load-bearing rule is to **open the rendered PNG and look at it**, and an
  overlapping legend, a stats box on the data or an unreadable font are invisible in the code
  and obvious in the picture. Also fixes fonts/units/semantic colours, and the A2MC ensemble
  figure template for biomass-vs-target time series.
- **Curate staged proposals** → `curate-knowledge`. **Inject a vetted finding** → `inject-knowledge`.
- **Deeper investigation / figure** → `scientific-analysis`. **Round reports** →
  `summarize-calibration-round`, `compare-calibration-rounds`; an **integrated, cross-cutting write-up**
  for a human reader (an investigation synthesis beyond the standardized round summary) → `write-report`.
- **Next:** converged (Phase 7), or loop to `phase3-diagnosis` (rethink) / `phase0-design` (redesign).


## The Phase-7 CONVERGED deliverable — the final configuration

**Contract added 2026-08-25 (T10.1).** Until then, three skills stated this deliverable in the same seven words — *"write the final config + round summary"* — and **nothing anywhere said what the artifact is**. A campaign's actual product had no specification, which is the same class of gap the per-round provenance ledger closed one level down.

Write it to **`use_cases/{Model}_{Case}/reports/{stem}_FINAL_CONFIGURATION/final_configuration.md`**, beside the round reports, and record its path in the state via `set_round_close(...)`'s companion field. It must carry all six:

| # | Element | Why it is not optional |
|---|---|---|
| 1 | **The parameter values**, every calibrated parameter with its final value and units | the result itself |
| 2 | **The base file they modify**, by path and content hash | a value is meaningless without the base it perturbs |
| 3 | **The case** that achieved them — case name, run root, and the scored result per target against the observations | someone must be able to point at the run |
| 4 | **The model binary, ARCHIVED** — commit, branch, and the archived executable path, **never the live build path** | the build tree is shared and every build overwrites it in place; a queued job resolves its exe at run time (`feedback_bind_runs_to_archived_binaries`) |
| 5 | **The command that reproduces it**, verbatim and runnable | a description of how to reproduce is not a reproduction |
| 6 | **What was NOT achieved** — the residual, routed to model development or to data | a converged campaign still has one, and the next person will otherwise rediscover it as a surprise |

**Why here and not in the round report.** The round report is a narrative for a reader; this is a machine-checkable record for a reproducer. `check_workflow_state_offline.py` asserts a converged state carries a resolvable pointer to it, which a narrative section cannot satisfy.
## Changelog

- 2026-08-27: **The Step-1b model table names each adapter's run skill and gives PFLOTRAN's panel
  set** (PI-directed, first PFLOTRAN campaign). The row listed three models and one example skill.
  Adds the two facts a PFLOTRAN Phase-6 figure gets wrong by default: which series are the panels,
  and that the chemistry and hydrograph targets have DIFFERENT windows — they shared one until
  2026-08-27 and it silently dropped 76 of 950 hydrograph observations.
- 2026-08-23 (later): **Question 6 added to the rethink protocol — for each refuted lever, which DIRECTION was moved, from a base with which SIGN of miss, and does that still apply?** PI-directed, and the signal is that the protocol had just run for the first time and missed this. A refutation is a property of a **(parameter, direction, base)** triple, and question 5 cannot catch it because it groups by mechanism class rather than by direction. Measured on the round that produced the protocol: three consecutive cycles refuted levers at a base whose flux target sat IN BAND near its ceiling, so their job was to protect or lower it; the next cycle moved to a base missing the same target FROM BELOW, inverting the job, and nothing re-read the inventory when the sign flipped. One of those "refuted" cycles had lowered a rate constant and watched the target fall 48 percent, which CONFIRMS its screened sign from the opposite side, and the parameter sat at the 4th percentile of its range at the new base with nearly ten times its value available upward. The rethink that had run an hour earlier produced three pathways and none was this one; it took a question from the PI. The question also carries the two ways the answer can legitimately be "no": the opposite direction may be past the calibrated bound or a structural ceiling (extrapolate the dose and check both), or the base may have no headroom left. Propagated to `calibration-discipline` item 6b and its At-a-glance line, to `calibration-log`'s Enrichment contract, and to the C9 guidance string in `check_calibration_log_conformance.py`.
- 2026-08-23: **New RETHINK PROTOCOL for the 6→3 route (Step 4).** PI-directed. `rethink_6to3` was the default route and only a counter increment: the skill named it as an enum value, as "the DEFAULT while cycles remain", and as `set_position(experiment_count=+1)`, with no method attached, while `phase3-diagnosis` called arrival from Phase 6 "same routine". Measured on one round: three consecutive rethinks ran on ONE base and attacked ONE target, and the cycle that finally re-examined both found the base was structurally wrong for the question then being asked (its own Fs already in band with 0.51 of headroom, so the next experiment would have broken the target it held) and that the binding target had moved. The protocol makes a rethink a SYNTHESIS with two halves — this cycle (phases 3-6) read against the whole picture (phases 1-2) — and five questions answered in the log, all settled by existing data at zero compute: synthesize this cycle separating what it ESTABLISHED from what it tried; re-read Phase 1/2 against that synthesis rather than citing them; is the BASE still right for the question now asked; has the BINDING TARGET moved; what lever CLASS is exhausted versus untried. Deliverable is NEW PATHWAYS, plural, each with its class and falsifier. Item 1 carries a write-once clause so the synthesis is not derived twice for the cycle report. Note the measured non-finding that sharpened this: every diagnosis in that round DID cite the Phase-1 and Phase-2 artifacts (14-15 and 6 times), so the gap was never citation — it was that citing an artifact and re-examining the strategy against it are different acts and only the first was required. Paired: `phase3-diagnosis` gains a Phase-6 row in its INHERITS table and consumes the pathways on re-entry.


- 2026-08-22 (later): **Adds the three-tier script rule**: look in `use_cases/{Model}_{Case}/scripts/` for a canonical script TEMPLATE first, copy it into this phase's `phase_results/{stem}/` and ADAPT it there; write one from scratch when no template exists; a script's SECOND use is the trigger to promote it into `scripts/`. PI-directed, extended to every phase skill after the rule initially landed in only two. Does not conflict with "one canonical script per figure, never two copies" -- the canonical script stays with its figures, the canonical script TEMPLATE stays in `scripts/`. Evidence: 7 byte-identical duplicate script pairs measured across one site's phase_results folders. Checker `tools/check_case_script_tier.py`.

- 2026-08-22 (later): **The Step-1b figure script is copied from the case template and adapted.** PI-directed; the canonical script still lives in `phase_results/{stem}/`, and the canonical script TEMPLATE now lives in `use_cases/{Model}_{Case}/scripts/`. Part of the three-tier script rule (see `calibration-discipline` item 2b).

- 2026-08-22 (later): **Loop limits and the confidence threshold now quote their config variables instead of literals.** PI-caught in `calibration-discipline` and swept across every skill stating one. `A2MC_MAX_SKIP_TESTING`, `A2MC_MAX_EXPERIMENTS` and `A2MC_CONFIDENCE_THRESHOLD` live in `a2mc_noncime_config.sh` / `a2mc_config.sh` and **nowhere else** — a site or round config does not set them — and `orchestrator.py:3567-3571` reads all three, so a skill quoting `10` or `0.95` contradicted the running agent the moment a value changed. Measurement narratives keep their number but now say it was the value at measurement time. Companion to v2.282, which fixed the same hardcoded copies in `tools/check_workflow_state_offline.py`. [[feedback_bind_derived_facts_to_their_source]].

- 2026-08-22: **Step 1b's requirement is separated from the FATES tool that implements it.** The step stated the time series as REQUIRED and then described it entirely through `tools/extract_and_plot_selected_cases.py`, which imports `extract_monthly_variables_FATES`, sums over SZPF size classes and is `_exp`-gated. **A requirement carried by a tool inherits the tool's applicability**, so on a non-CIME adapter model the requirement left with the driver, and that model's own run skill carried no figure requirement to catch it. The skill was not stale, it was model-bound. The requirement is now stated model-neutrally (one panel per SCORED target; the observation drawn as measured, with gaps left as gaps; the control on top; the trajectory not the endpoint) with a routing table to each family's driver, and an instruction to write a canonical script into `phase_results/{stem}/` where no driver exists rather than skip the figure. Signal: PI, on finding a cycle report whose only figure showed one of three scored targets and drew a flat line at the multi-year observed mean in place of the measured per-year series. Paired: `ecosim-run-workflow` gains the counterpart step; `write-report` gains the cycle/round report scope (`20260822p`).

- 2026-08-16: **Names the `plotting` skill for any figure this phase produces.** The link was
  one-directional — `plotting`'s own cross-references claimed the phase skills apply its
  conventions, while most phase skills never mentioned it, so a session could produce figures
  for a whole case without the conventions or the view-the-PNG check ever being loaded. That
  happened: three sets of Lusignan figures were made before it was invoked, and the first
  invocation immediately caught a stats box drawn over the data. PI-directed ("every phase
  needs the plotting skill").
- 2026-08-02: Log step now states the **living-record** contract (start at phase start, enrich as it runs —
  the operational detail is unrecoverable later), names **this phase's expected sections** so an omission is
  visible, and shows `set_phase_handshake()` so the chain is traceable. Full contract: `calibration-log`.
- 2026-07-18: Step 3b: added the generalize-the-copy step (promotion is copy-then-generalize — strip
  hardcoded paths/stems/case IDs, parameterize; the promote tool prints this reminder).
- 2026-07-18: Step 3b's offline path is now first-class — `promote_diagnostic_script.py --source <path> --dest
  tools|phase3_diagnosis` (was noted as a future improvement); no longer manual.
- 2026-07-18: Added **Step 3b — promote reusable scripts into the shared library** at round close (the
  tooling analog of the knowledge write-gate): online `phases/phase3_diagnosis/generated/` →
  `phases/phase3_diagnosis/` via `tools/promote_diagnostic_script.py`; offline `phase_results/{stem}/`
  scripts → `tools/` or `phases/phase3_diagnosis/` (manual — the promote tool reads only `generated/`).
  Mirrored in the `calibration-discipline` per-round checklist (item 12).
- 2026-07-15: Step 1b notes the new `extract_and_plot_selected_cases.py --baseline` flag (dash-highlight the control for split−ctrl reads). Ported from demo `db488cd`.
- 2026-07-09: **Added Step 1b — extract full results + time-series comparison plots** for an experiment's
  Phase 6, via the generic `tools/extract_and_plot_selected_cases.py` (`extract`/`v0check`/`plot`). Makes
  the **time-series overlay vs observations** a required Phase-6 figure — a single endpoint metric hides the
  trajectory (equilibrate / late-collapse / overshoot-crash / oscillate). Ported from demo `a2147ff`, scrubbed
  of Kougarok example filenames.
- 2026-07-06: **Wired the middle-loop gate into Step 4.** The decision fork now gates on `experiment_count`
  vs `--max-experiments` (rethink 6→3 is the DEFAULT while cycles remain; redesign 6→0 only at the cap), adds
  the "no in-range target-aimed experiment left" precondition before any escalation, the counter-increment
  step, and an explicit "'stop → improve the model' is NOT a loop branch" guard. Mirrors the online
  orchestrator's coded state machine so the offline agent can't rush past the loop. Ported from demo `2d3f4b0`
  (v3.12), scrubbed of the Kougarok worked example. See `feedback_performance_experiment_is_the_objective`.
- 2026-07-02: Created — offline Phase 6 routine mirroring `interpret_results()` + `extract_lesson()`; encodes the offline "disposer" write gate (direct curated writes + promote staged proposals), delegates memory to curate-/inject-knowledge, reporting to summarize-/compare-calibration-round.

## Before you finish

**Discipline self-review (automatic).** Before advancing the state, re-check the [`calibration-discipline`](../calibration-discipline/SKILL.md) items that apply to this phase. This is unprompted and per-phase — the user does not have to ask (memory `feedback_schedule_periodic_reviews_with_a_real_mechanism`).