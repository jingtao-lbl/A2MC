---
name: phase3-diagnosis
visibility: public
category: phase
description: Run Phase 3 (DIAGNOSIS) of the A2MC calibration workflow as the offline agent — the human-in-the-loop analog of the autonomous orchestrator's `_run_diagnosis()` / `reasoning.diagnose()`. Systematically root-cause WHY the screening round is missing its validation targets — gather diagnostic data with the phase3 tools, pull RAG + Adaptive Memory context, then reason to a structured diagnosis (failing targets, likely causes, ranked root causes, parameter recommendations, base cases, hypotheses) and hand off to Phase 4. Use when the user says "diagnose the failing targets", "run Phase 3", "why aren't the targets calibrating", "root-cause this round", "what's driving the PFTx miss", after screening (Phase 2) hands off a ranked ensemble.
modes:
  requires_fates: false      # calibration-workflow phase skill; mode resolved at runtime via describe_mode
  nutrient_pathway: any
  scope: [calibration]
  summary: "Offline analog of Phase 3 (root-cause the failing targets). Applies in every calibration mode."
---

# Phase 3: Diagnosis (offline agent)

> **Driven by `calibration-goal`** — the run-to-convergence driver dispatches here when `WorkflowStateOffline.current_phase` routes to this phase; do the phase, then update + `save()` the state so the driver advances. Also runnable standalone (one phase).

The offline analog of the orchestrator's `_run_diagnosis()`. Online, `reasoning.diagnose()`
makes this call automatically; **offline, YOU are the reasoning** — the `phases/phase3_diagnosis/`
tools are your instruments, RAG + Adaptive Memory are your evidence, and you produce the same
structured `Diagnosis` the online agent would. This is the **systematic** phase routine (diagnose
every failing target from the screening round), distinct from `diagnose-forensics` (reactive:
"is this one anomaly real?"). If you're chasing a single suspicious case, use `diagnose-forensics`
first; come here to diagnose the round.

> **Floor, not ceiling.** This skill captures what the online agent does in Phase 3 so you never
> do *less* — but the online loop is fenced into a fixed phase scope and you are not. Your value as
> the offline agent is doing *more*: pull extra data, run analyses no phase3 tool exists for, probe
> a mechanism deeper than the schema asks, cross into an adjacent phase when the evidence leads
> there, or question the round's framing outright. Match the discipline below (verify mechanisms,
> honor failed approaches, log it), then go past it — follow the surprising thread with
> `scientific-analysis` rather than forcing the finding back into the phase box.

## What this phase INHERITS, and what it must do with it

Up to three upstream sources hand Phase 3 its raw material, and a diagnosis that uses only part of it is re-deriving what the round already knows.

| from | what arrives | what it lets you ask |
|---|---|---|
| **Phase 1** (exploration) | the **top parameters** by whichever sensitivity index the round computed (Morris μ\*, Sobol delta or S1/ST — read the artifact, do not assume the metric) | which knobs actually move each target, so a proposed cause is checked against the sensitivity rather than against intuition |
| **Phase 2** (screening) | the **top-N CASES under both rankings**, per-target errors, which targets each case meets and misses, the whole-ensemble figure | what the leaders have in COMMON, how they DIFFER from each other, and where they differ from the rest |
| **Phase 6** (only on a 6→3 rethink) | the **NEW PATHWAYS** the rethink protocol emitted, each with its lever CLASS and its falsifier, plus that cycle's synthesis and the base / binding-target re-examination behind them | which pathway to test FIRST, and which lever class the round has already exhausted — so the cycle does not re-derive the diagnosis that produced the pathway, nor re-enter a class three cycles have refuted |

**On a rethink, the third row is where you start.** Cycles 1 and 2 of a round have no third row; every later cycle does, and ignoring it is how a round runs several cycles on one base attacking one target. See `phase6-refinement` Step 4's rethink protocol for what the pathways must carry.

### DIAGNOSE THE LEADER SET, NOT THE BEST CASE

**The single best case is the least informative member of the set, and it cannot be the diagnosis.**
It is best by a composite that averages the targets, so by construction it is the case whose failure
is most evenly spread. The signal is in how the leaders fail *differently* from one another: one holds
production and misses standing carbon, another holds standing carbon and misses flux. That contrast is
what identifies the constraint, and it is invisible in any single case.

**MEASURED, which is why this is stated rather than assumed.** Across one round's five diagnoses,
every log named the round's best case (7329) and **not one named any of the other eight Phase-2
leaders** (9505, 305, 4857, 9831, 2847, 9805, 9828, 9803). Only `best_case` crossed the handoff, so
"what do the leaders have in common" was never askable. The round spent five cycles moving levers on
one case while the ensemble held 104 cases meeting two targets whose shared property was the actual
finding.

**So, concretely:**

- **Pull the top-N as a SET** (`--top-n 100`, per `phase2-screening` Step 1), not `best_case` alone.
- **Tabulate which targets each leader meets and misses.** Group the leaders by their MISS PATTERN;
  each distinct pattern is a different failure mode and deserves its own line of the diagnosis.
- **Name at least one case per miss pattern in the log**, with its values. A diagnosis quoting one
  case cannot support a claim about the round.
- **Take the best case as the BASE for Phase 4, not as the subject of Phase 3.** Those are different
  jobs: the base is where an experiment starts; the subject is what the diagnosis explains.

### The four questions, answered explicitly in the log

1. **Do the top cases share characteristics?** Compare the leaders' parameter vectors against the rest of the alive set, ranked by **SEPARATION** (a rank-biserial or equivalent), never by correlation with a single target — a single-target ranking marks a budget-inflating runaway as a strong lever.
2. **Does a case predict one target well and another badly, and why?** The highest-value question in the phase, invisible in a composite score, and answerable only across the set. A case matching production while missing standing carbon says something structural that no aggregate error can express.
3. **Do the sensitivity rankings agree with what separates the leaders?** Disagreement is a finding: a highly sensitive parameter that does NOT distinguish the leaders is being cancelled by something, and a parameter that separates them without ranking as sensitive means the index was computed for a different target than the one now binding.
4. **Where does the current best case sit relative to the leaders?** Inside their range on the separating parameters means the gap is not a parameter-value problem, and no lever inside that range will close it.

**Deliverable:** a diagnosis (logged as a phase log) naming the ranked root causes and
the parameters/base-cases Phase 4 should act on.

## Step 1 — gather diagnostic data (reads existing outputs — no new simulations)

Drive the phase3 tools on the best / lowest-cost / most-targets cases. Run several at once via
`run_diagnostics_scripts.py`; dispatch AI-requested follow-ups via `dispatch.py`.

| Question | Tool |
|---|---|
| What params does this case have / how do top cases differ? | `read_case_parameters.py`, `compare_case_parameters.py` |
| Any parameter pinned at a Morris bound (redesign candidate)? | `check_edge_parameters.py` |
| Which targets, how far off, what direction? | `compare_targets.py` |
| Did a PFT collapse / crash? | `detect_collapse.py` |
| Why is a PFT not establishing / growing? | `diagnose_pft_limitations.py` |
| Carbon / mortality / nutrient mechanism | `analyze_carbon_balance.py`, `analyze_mortality.py`, `analyze_nutrient_balance.py`, `analyze_nutrient_pools.py` |
| Best vs lowest-cost case comparison | `comparative.py` |
| Structured hypothesis test with quantified metrics | `test_hypothesis_framework.py` |
| Diagnostic figures (6-panel PFT composite) | `plot_diagnostics.py` |

> **THE TABLE ABOVE IS FATES-SHAPED, AND FOR A NON-VEGETATION MODEL ALMOST NONE OF IT APPLIES.**
> Measured 2026-08-27: of ~19 scripts in `phases/phase3_diagnosis/`, **2** dispatch through the model
> backend (`compare_targets.py`, `run_diagnosis.py`); the rest read SZPF arrays, PFT establishment,
> mortality and nutrient pools. For PFLOTRAN's miniLEO there are no PFTs, nothing establishes, nothing
> dies, and there is no nutrient-uptake pathway — so "did a PFT collapse", "why is a PFT not
> establishing" and the mortality/nutrient tools have **no analog**, not a harder version.
>
> **This is the phase where that costs the most**, because Phase 3 is where the reasoning happens and
> a tool table is the most inviting thing in it. Build the diagnosis from the model's own outputs
> instead, and keep the three rules that ARE model-neutral:
> - **`compare_targets.py` still applies** — which targets, how far off, in which direction — and it
>   dispatches through the backend, so it works as written.
> - **The sim-vs-obs TIME-SERIES rule below is model-neutral and is the load-bearing one here.** For
>   miniLEO that means each scored species' outflow concentration and the hydrograph across the scored
>   window, against the measurements as measured (the hydrograph has a real 194-hour gap from a
>   tipping-bucket failure — leave it as a gap).
> - **Every mechanism claim is verified at `file:line` in the checked-out model source**, not from a
>   card name or a RAG summary. That rule cost a session on 2026-08-27: a source reading predicted four
>   PFLOTRAN parameters were inert under the deck's restart, and a four-case probe refuted half of it.
>   Reading source produces a HYPOTHESIS; the run decides.
>
> A reusable diagnostic you write for a non-FATES model is promoted the same way (`calibration-discipline`
> item 12) — copy-then-generalize, and it must dispatch through the backend to earn a place in the table.

Any `test_*.py` in the folder exposing `test_hypothesis()` is **auto-discovered** (see root
`CLAUDE.md` §"Diagnostic tools") — you can run one to probe an ensemble-wide pattern without new simulations.

> **Writing a custom diagnostic script? Use `tools/fates_utils`** for any per-PFT / SZPF extraction
> (`get_szpf_range()`, `extract_pft_data()`, `aggregate_szpf_by_pft()`, `get_pft_index()`) — do NOT hand-roll
> the SZPF (`levscpf`) index: it is **PFT-major** `(pft-1)×nlevsclass` with `nlevsclass` **file-derived**
> (13 in the common default but *configurable*, not a fixed 13), plus the 0-based/1-based offset (a classic
> silent bug; the FATES wiki's size-major formula is wrong). It is the canonical helper the existing phase3
> tools already import.

> **Trajectory view for collapse/exclusion.** The per-case `plot_diagnostics.py` (6-panel PFT composite)
> shows *one* case; to see *where in the spin-up→transient a target diverges from the ensemble/observations*,
> also read the whole-ensemble time-series comparison from Phase 2 Step 1b
> (`tools/plot_ensemble_cases.py --combined`, [[reference_ensemble_combined_plot_pipeline]]). Late collapse,
> overshoot-then-crash, and competitive-exclusion frontiers show up there before the per-case mechanism tools
> name them.
>
> **Make a SIM-vs-OBS TIME-SERIES comparison DURING diagnosis — do not wait for the report (PI, 2026-07-19).**
> For the diagnosed / best / candidate cases, plot each scored target's simulated trajectory over the run
> years against the observation (band + marker), in the R1 `fig4_sim_vs_obs_timeseries.png` style (its
> canonical script is `reports/20260717i_R1_ROUND_SUMMARY/make_comparison_figures.py`; the FATES analog is
> `tools/extract_and_plot_selected_cases.py plot`). The **shape of the trajectory IS often the diagnosis**:
> equilibrated / still-climbing / collapsed-late / overshoot-then-crash / oscillating tells you more than the
> single windowed number. Save it self-documenting in `phase_results/{stem}/` (figure + caption + canonical
> script + data). [[feedback_timeseries_plots_during_diagnosis]]

## Step 2 — pull evidence (RAG + Memory), verify before asserting

- **RAG/GraphRAG + `docs/fates-knowledge-base/`:** confirm the mechanism behind any parameter
  BEFORE naming it. Never infer a FATES mechanism from a parameter name (root `CLAUDE.md` rule).
- **Adaptive Memory — THE SITE STORE, and it has an API.** Open
  `use_cases/{Model}_{Case}/memory/gained_knowledge/`, **not** the generic repo-root store. This
  matters: `memory/manager.py` is the shared MODULE, and an agent told only to "load site
  discoveries" reads the generic store and considers the obligation discharged. The store that was
  empty after thirty experiment cycles is the per-case one.

  ```python
  from memory import MemoryManager
  m = MemoryManager("use_cases/{Model}_{Case}/memory/gained_knowledge")
  m.stats()                                   # is there anything here at all?
  m.get_failed_experiments(parameters=[...])  # what has already been tried on these levers
  m.get_parameter_cautions(parameters=[...])  # per-parameter warnings
  m.get_all_discoveries()                     # site mechanisms already established
  ```

  **Do NOT propose a direction Memory already records as failed**; if you must, say why this time
  differs. A refutation is a property of a `(parameter, direction, base)` **triple**, so check the
  direction and the base, not just the name: a dose that moved monotonically the wrong way is
  positive evidence for the opposite direction, not a closed door.

  **If `stats()` comes back all zeros, say so in the diagnosis.** An empty store is a finding about
  the campaign, not a reason to skip the step — and it means the previous round's
  `round-housekeeping` did not run.

## Step 3 — reason to a structured diagnosis

Produce the same shape the online `Diagnosis` schema carries (don't skip the discipline the
prompt enforces online):

1. **Mechanism inventory** — enumerate every plausible mechanism (nutrient limitation, carbon
   balance, allocation/PID, competition/ECA, mortality, phenology, sim protocol); rate each and
   name the confirming/refuting evidence from Step 1–2.
2. **Severity** — classify each failing target CRITICAL (>50% error) / HIGH (30–50) / MEDIUM
   (20–30) / LOW (<20).
3. **Ranked root causes** — `{cause, mechanism, affected_targets, confidence}`, most-confident
   first, each tied to evidence (not a statistical hunch).
4. **Parameter recommendations** — `{parameter, current_issue, suggested_direction, priority,
   caution}` (FATES names). Flag any that would need values outside Morris bounds as a Phase 0
   redesign candidate, not a Phase 4 knob.
5. **Comparative analysis** — recommend 1–2 `selected_base_cases` (`{case_id, rationale,
   targets_satisfied, targets_to_fix}`) for Phase 4 to build on.
6. **Hypotheses** — 1–N testable statements for Phase 4, each with an expected direction.

Structure follows `templates/reasoning/phase3_diagnosis_template.md`. **Verify every mechanism claim in
the checked-out model SOURCE (`file:line`), not just RAG or the parameter's long_name/units (PI, 2026-07-19).**
RAG + `long_name` are the starting hypothesis; the Fortran is the ground truth, and it has repeatedly
contradicted the description — R1 traced `CNLF` to a *ceiling* (realized = `CNLF*(0.33+0.67*CNPG)`, not the
operative N:C), `SLA1` to a power-law *coefficient* (not bulk SLA), `NPP_pft` to a *cumulative* field
(despite a per-hour unit attr), and `fCHLMESO`/`GRDM` to under-set graft placeholders. So before writing a
root cause that rests on "parameter X does Y", grep the source for X, read the equation it enters, and cite
the `file:line`. [[feedback_param_description_can_lie_verify_in_source]] [[feedback_verify_before_acting_triangulate_sources]]

## Step 4 — cheap test first? (skip-testing inner loop, Phase 3↔4)

If a hypothesis can be tested against the **existing** Morris ensemble (a correlation, a
high-vs-low group contrast, a threshold) — do that instead of queuing a new simulation. That is the Phase 3↔4
skip-testing inner loop: hand the hypothesis to `phase4-hypothesis`, which decides
`test_with_existing` vs a new simulation. Only real parameter values outside the ensemble range need Phase 5.

## Step 5 — log it and hand off

> **The log is a LIVING record — start it now, enrich as the phase runs.** Not an end-of-phase
> write-up: the operational detail (job/array IDs, which cases failed, what was restarted) is
> unrecoverable a week later. Full contract in `calibration-log`.
>
> **This phase's expected sections** — `PhaseLogger` names any you leave empty:
> Failing Targets · Likely Causes · Root Causes (Ranked) · Key Insights · AI Reasoning and Deep Analysis · Parameter Recommendations · Cross-PFT Conflicts · Hypotheses Tested · Conceptual Model.
>
> **Set the handshake before the `log_*` call**, so the chain is traceable:
> ```python
> logger.set_phase_handshake(
>     inherited_from="<predecessor log STEM> — what it concluded / asked of this phase",
>     handed_to="<what Phase 4 receives; mirror the reasoning/schemas.py field names>",
>     next_action="<the one concrete thing Phase 4 should do>")
> ```
> The log also carries `## Reasoning chain`, rebuilt from `workflow_state_offline` — so keep that
> state updated with the FINDING, not a label; the chain is only as good as what each phase wrote.


- **Log** via `calibration-log` (phase log → `PhaseLogger.log_diagnosis`, byte-identical to the
  autonomous agent so both modes' logs synthesize). Capture failing targets, ranked root causes,
  parameter recommendations, selected base cases, hypotheses, and the RAG/Memory evidence.
- **Evidence gate (docs/33).** The log must cite a first-hand artifact produced **this session** — the
  diagnostic script + its output/figure in `phase_results/{stem}/` or `phases/phase3_diagnosis/generated/`
  (a "Scripts Created" / "Output Figures" / "Evidence" section) — not just restate a prior log. Run
  `python tools/check_offline_log_evidence.py <log.md>`; it must exit 0 (ERROR = no resolvable first-hand
  artifact). See `feedback_offline_logs_need_first_hand_analysis`.
  **Make `phase_results/{stem}/` SELF-DOCUMENTING** (`calibration-log` "different jobs" note): the
  `log/{stem}.md` carries the analysis/findings/discussion/conclusion/next-action; the folder ships, per
  figure, the **figure + a caption/NOTES `.md` (what it shows + how-to-read + provenance) + the generating
  `.py` script (saved, not an inline heredoc) + the data**. The gate now WARNs on a figure missing its
  caption/script/data — clear those warnings, don't stop at exit 0 (mirrors `write-report`). Phase 4/6 identical.
- **Hand off** to `phase4-hypothesis` with the base cases + hypotheses. (If you came here from Phase 6 on a rethink, you are NOT starting fresh and you are NOT repeating the last cycle. The **rethink protocol** in `phase6-refinement` Step 4 hands you NEW PATHWAYS, each naming its lever class and what would falsify it; start from those, because your first job is to test the pathway rather than re-derive the diagnosis that produced it. `experiment_count` was incremented on the 6→3 route and this cycle's `skip_testing_count` starts fresh — confirm both in `workflow_state_offline_r{RR}.json`.)

## Footguns

- **The `generated/` dir is staging, not truth.** AI-written custom tests land in
  `phases/phase3_diagnosis/generated/` (see its README). Review + V0-validate a generated
  script's first run before trusting it. If it's vetted and reusable, **promote** it into the
  permanent tool library with `tools/promote_diagnostic_script.py --script <name>` (`--list` →
  `--dry-run` → promote) — this copies it to `phases/phase3_diagnosis/` and registers it in
  `DIAGNOSTIC_TOOLS_INVENTORY` so future runs auto-discover it. Human-gated; review before committing.
- **Verified-only Memory gate.** Baseline auto-discovered entries are `verified=false`; know
  whether your Memory context is filtered before leaning on it.
- **Don't touch the extractor.** Phase 3 reads existing outputs; it never modifies the Phase 5
  extraction path.
- **Artifact before signal.** A too-good "best" case or a tidy failure cluster is often
  contamination / infra-timing, not science — if a result looks surprising, run
  `diagnose-forensics` triage before diagnosing it as mechanism.

## Working discipline (offline agent — applies across Phase 3↔4)

1. **Log the integrated story, not a snapshot.** A diagnosis/hypothesis log must carry the *whole
   reasoning chain*: what has already been tested and learned (across prior iterations/cycles), the
   logic that led here, why each candidate was kept or ruled out, and **why the next step is the correct
   direction**. Credit the canonical prior log instead of re-deriving it; when a new finding overturns an
   earlier one, supersede it (don't silently restate). A well-formed log lets a cold reader reconstruct
   the *argument*, not just the conclusion.

2. **Read your checked-out model source FIRST, then upstream git.** To verify how a specific parameter /
   line / mechanism behaves, read the **actual checked-out source** (`$A2MC_E3SM_ROOT/...`) and the
   **param file in use** BEFORE querying the upstream model repo or its commit history. Your local tree
   may be a custom branch that already carries fixes or diverges from upstream — an upstream read can
   mislead if you haven't pinned what YOUR code actually does. Upstream git answers "has this been fixed
   since / is there a known issue", asked *after* you know the local truth.

3. **Keep the inner loop turning while sims run.** Phase-5 simulations (the middle experiment loop) take
   hours — do NOT idle waiting. Continue diagnosis / hypothesis / skip-test work (the 3↔4 inner loop):
   analyze existing data, refute or refine other levers, read source, check upstream — in parallel with
   the in-flight experiment. Idle waiting is an online-agent limitation you don't share
   ([[feedback_offline_agent_drives_the_workflow]]).

4. **Stem invariant: the log stem is canonical.** Every `phase_results/{stem}/` folder MUST have a
   matching `logs/{stem}.md`; a log with no results folder is fine (analysis-only), a results folder with
   no log is not. So **decide the stem when you write the log, and reuse that exact stem for
   `phase_results/`** — never mint a separate letter for the artifacts (`docs/31`; via `PhaseLogger`
   offline mode `topic_stem`/`topic_artifact_dir`).

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

- **ANY figure this phase produces** → **`plotting`**. Load it BEFORE the first `savefig`,
  not after: its load-bearing rule is to **open the rendered PNG and look at it**, and an
  overlapping legend, a stats box on the data or an unreadable font are invisible in the code
  and obvious in the picture. Also fixes fonts/units/semantic colours, and the A2MC ensemble
  figure template for biomass-vs-target time series.
- **Reactive anomaly** (one outlier, not the whole round) → `diagnose-forensics`.
- **Manuscript-grade investigation of a finding** → `scientific-analysis`.
- **Next:** `phase4-hypothesis` (turn the diagnosis into testable experiments).

## Changelog

- 2026-08-27: **States that the Step-1 tool table is FATES-shaped and what survives for a
  non-vegetation model** (PI-directed, first PFLOTRAN campaign). This skill named NEITHER EcoSIM nor
  PFLOTRAN anywhere — the only one of the seven phase skills mentioning no adapter model at all —
  while presenting a twelve-row tool table as the way to diagnose. Measured: 2 of ~19 scripts
  dispatch through the backend. For an abiotic reactive-transport case the collapse, establishment,
  mortality and nutrient tools have no analog, and saying so is more useful than leaving a reader to
  run them and get nothing. Keeps the three model-neutral rules explicit, including that a source
  reading is a hypothesis rather than a result.
- 2026-08-23: **The 6→3 re-entry consumes the rethink's PATHWAYS instead of being "same routine".** PI-directed, paired with `phase6-refinement`'s new rethink protocol. The hand-off bullet said a cycle arriving from Phase 6 followed the same routine with only the counters differing, which made a rethink a counter increment; measured on one round, three consecutive rethinks then carried one base and one target framing forward unexamined. The INHERITS table gains a third row for the Phase-6 rethink (the pathways, each with its lever CLASS and falsifier, plus the cycle synthesis and base re-examination behind them) and states that on a rethink that row is where the cycle STARTS. The hand-off bullet now says a rethink cycle is neither a fresh start nor a repeat, and that the first job is to test the pathway rather than re-derive the diagnosis that produced it.


- 2026-08-23 (later): **Diagnose the LEADER SET, not the best case.** PI-directed after the correction below. The single best case is the least informative member of the set: it is best by a composite that averages the targets, so by construction its failure is the most evenly spread, and the diagnostic signal is in how the leaders fail DIFFERENTLY from one another. Measured: across one round's five diagnoses every log named the best case (7329) and **not one named any of the other eight Phase-2 leaders**, so "what do the leaders have in common" was never askable — only `best_case` crossed the handoff. Now requires pulling the top-N as a set, grouping leaders by MISS PATTERN, naming at least one case per pattern with its values, and treating the best case as Phase 4's BASE rather than Phase 3's SUBJECT. Also makes the sensitivity-metric reference index-agnostic (Morris μ*, Sobol delta, S1/ST — read the artifact rather than assuming), which is what made the previous measurement wrong.

- 2026-08-23: **States what the phase INHERITS from Phases 1 and 2, and the four questions that inheritance makes askable.** PI-directed. The inputs were already named — including the Phase-1 μ* rankings — but in a trailing clause of a run-on sentence with nothing said about what to DO with them, and naming an input is not the same as stating the question it answers. **CORRECTED same day:** an earlier version of this entry claimed the Phase-1 rankings were referenced zero times. That measurement used Morris μ* vocabulary against a round that computed Sobol delta, so it matched nothing; the logs in fact cite the Phase-1 artifact 14-15 times each and name 3-8 of its 14 top parameters. The real gap is that Phase 3 inherited `best_case` and never the leader SET: all five logs name case 7329 and none names any of the other eight leaders. The four questions now stated: do the top cases share characteristics (ranked by separation, not single-target correlation); does a case predict one target well and another badly, and why (invisible in a composite score, and the highest-value question in the phase); do the μ* rankings agree with what separates the leaders (disagreement is itself a finding); and where does the current best case sit relative to the leaders (inside their range means no lever in that range closes the gap). Worked instance the same day: the R3 c05 diagnosis found the top separator reached only 0.361 rank-biserial while the best case sat inside the leaders' p10-p90 on all ten, which is question 4 answering itself.

- 2026-08-22 (later): **Adds the three-tier script rule**: look in `use_cases/{Model}_{Case}/scripts/` for a canonical script TEMPLATE first, copy it into this phase's `phase_results/{stem}/` and ADAPT it there; write one from scratch when no template exists; a script's SECOND use is the trigger to promote it into `scripts/`. PI-directed, extended to every phase skill after the rule initially landed in only two. Does not conflict with "one canonical script per figure, never two copies" -- the canonical script stays with its figures, the canonical script TEMPLATE stays in `scripts/`. Evidence: 7 byte-identical duplicate script pairs measured across one site's phase_results folders. Checker `tools/check_case_script_tier.py`.

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
- 2026-07-19: Two PI Phase-3 habits (`feedback_timeseries_plots_during_diagnosis`): (1) make sim-vs-obs
  TIME-SERIES comparison plots DURING diagnosis (Step 1 trajectory callout), not at the reporting stage — the
  trajectory shape is often the diagnosis; (2) sharpened Step 3 to VERIFY every mechanism claim in the
  checked-out model SOURCE (`file:line`), not just RAG/long_name (which have repeatedly been wrong).
- 2026-07-17: Evidence-gate bullet now requires a SELF-DOCUMENTING `phase_results/{stem}/` (figure + caption + saved generating .py + data), not just one artifact; the gate WARNs on a lone under-documented figure. Phase 4/6 mirror it. See `calibration-log` "different jobs" note.
- 2026-07-15: Named `tools/fates_utils` as the canonical per-PFT/SZPF helper for a custom diagnostic script (don't hand-roll `(pft-1)×13`), and added a trajectory-view cross-ref to the whole-ensemble time-series comparison (`plot_ensemble_cases.py --combined`, Phase 2 Step 1b) as a complement to the per-case `plot_diagnostics.py`. Ported from demo `ac4c125`+`b11162a`.
- 2026-07-06: Noted the middle-loop counter at the 6→3 re-entry (`experiment_count` incremented on the route;
  fresh `skip_testing_count`). Pairs with the Phase-6 middle-loop gate. Ported from demo `2d3f4b0`.
- 2026-07-06: Added "Working discipline (Phase 3↔4)" — integrated-story logs, read-your-source-before-upstream-git (generalized off demo's FATES-branch phrasing), keep the inner loop turning while sims run, and the log-stem-is-canonical invariant (now backed by `PhaseLogger` offline mode, v2.115). Ported from demo, scrubbed of Kougarok worked examples. Mirrored in `phase4-hypothesis`.
- 2026-07-02: Created — offline Phase 3 routine mirroring `reasoning.diagnose()`; composes `diagnose-forensics` (triage), `calibration-log` (phase log), hands off to `phase4-hypothesis`.

## Before you finish

**Discipline self-review (automatic).** Before advancing the state, re-check the [`calibration-discipline`](../calibration-discipline/SKILL.md) items that apply to this phase. This is unprompted and per-phase — the user does not have to ask (memory `feedback_schedule_periodic_reviews_with_a_real_mechanism`).
