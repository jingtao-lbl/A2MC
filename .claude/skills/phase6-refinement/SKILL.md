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
agent, are the disposer** — you are the only writer of curated knowledge, and you promote the online
agent's staged proposals. "Online proposes, offline disposes." This is *the* thing Phase 6 does
differently offline.

**That is a statement about AUTHORITY, not about TIMING, and the two were being read as one.** Being
the only permitted writer does not mean writing during this phase: the write happens **at or after
the Step-4 human gate**, and `round-housekeeping` is where it happens. Step 3 below stages the
candidates and defers the write; `calibration-discipline` item 8 is the governing rule.

**Inputs — TWO LOGS, READ FROM DISK, not values handed forward:** this cycle's **Phase-4 log** (the
pre-registered bar, the hypothesis, the mechanism, why that base) and its **Phase-5 log** (what was
actually executed, including any adjustment Phase 5 made), plus the experiment results themselves
(per-target metrics, extraction status). See Step 0. **Deliverable:** honest per-hypothesis verdict,
lessons written to Memory, a convergence decision.

> **Before designing or interpreting anything here, hold the MECHANISM NETWORK, not one or two parameters.** At calibration stage the model KB is assumed well-built, so it is where you START and it usually hands you the citation -- it does NOT replace verifying in source: query ALL FIVE surfaces (codebase wiki, RAG index, **knowledge graph**, MODEL-level and SITE-level `gained_knowledge/`) plus the case's own parameter list, pull `parameter -> controls -> mechanism -> affects -> output` for the **scored** variables and the `depends_on` couplings among anything you intend to move together, and only then confirm in source. Needing source to LEARN rather than to CONFIRM means a KB gap, which is a build task. [[feedback_full_mechanism_picture_before_designing_an_experiment]]

> **AND AN OUTPUT VARIABLE IS VERIFIED LIKE A PARAMETER.** The rule above is written about parameters and mechanisms; a tape field is a third category and the same failure arrives one category over. Before reducing one, establish that it is ACTIVE (a field registered `default='inactive'` is not written unless a run names it, and the model's `docs/<model>-knowledge-base/<model>_output_info_<commit>.cdl` carries a source-derived `:status`) and what its TEMPORAL SEMANTICS are -- rate, per-record increment, within-year cumulative that RESETS, run-cumulative, or stock. One reduction does not fit all five and the units do not separate them. Full rule and the measured cost: `calibration-discipline` item 3c.

## Step 0 — OPEN THIS CYCLE'S PHASE-4 AND PHASE-5 LOGS. BOTH. BEFORE EVALUATING ANYTHING

Phase 6 rules on a bar it did not set, over an experiment it did not run. Both of those facts live in
logs on disk under `use_cases/{Model}_{Case}/memory/logs/`, and **neither arrives here as a value**:

| open | to get |
|---|---|
| the cycle's **Phase-4** log | the **pre-registered bar in its own words**, the hypothesis and the mechanism it rests on, the expected outcome per target, and **why that base was chosen** |
| the cycle's **Phase-5** log | what was **actually executed** — which arms ran, which died, what the V0 gate returned, and **any practical adjustment Phase 5 made to the design** |

**Read the Phase-5 log for DIVERGENCE specifically.** `phase5-testing` step 0b permits an adjustment
during execution for practical reasons and requires it to be recorded there. A Phase 6 that scores the
**designed** values rather than the **executed** ones delivers a verdict on an experiment nobody ran,
and nothing downstream catches it: the numbers are real, the arms completed, and the log reads clean.
Where the two logs disagree, the Phase-5 log is what happened and the Phase-4 log is what it was
supposed to test — say so explicitly, and judge whether the adjustment moved what the experiment could
confirm or refute.

**Quote the bar into this phase's log verbatim with the Phase-4 stem beside it**, rather than restating
it from memory. A bar carried in the head drifts across a long round.

**And VERIFY the numbers you act on against the STEM FOLDER the log points at.** The general rule is
`calibration-log`'s and is stated there: a phase log is a SYNTHESIS of its `phase_results/{stem}/`, the
folder is upstream, and where the two disagree the folder wins. **Its Phase-6 application is the sharp
one**, because this phase is where a number stops being descriptive and starts deciding a verdict: the
bar, the base's own scores and what each arm returned all get re-read from the script that computed them
and the data file that holds them, before anything is ruled CONFIRMED or REFUTED. Prefer the mechanical
form wherever a tool offers one, reading a gate FROM the prior cycle's data file at full precision rather
than passing values by hand.

**MEASURED, in one site's calibration round, and each piece failed differently.**

- **A bar that lived only in prose was wrong.** One cycle's three gate values had been hand-entered
  into the Phase-4 design script and appear in no artifact anywhere in the round; one was wrong by
  1e-4 relative. Because a copied base makes the V0 gate EXACT, quoting the log faithfully and
  gating at rtol 0 would have FAILED and reported non-determinism in the model -- a false and
  serious finding, produced by following the quote-the-bar rule correctly. The gate passed only
  because it was run against the prior cycle's data file instead.
- **A bar read off a scoring script was a different base's.** An earlier cycle had three numbers in
  play for one verdict: the Phase-4 log's pre-registered 0.97 and 1.1, a hardcoded 0.664 in the
  shared scoring template that belonged to another base, and the base's own allowance of 1.2425
  derived only afterwards by hand. The measured rate of 1.139 is REFUTED against the literal and
  affordable against the correct bar, so the refutation the scorer reported was an artifact.
- **And the read was not happening at all.** Across that round, **10 of 17 refinement logs cite the
  Phase-4 log stem zero times, the last eight cycles consecutively**, while all 17 cite Phase 5 --
  which is diagnostic rather than careless: Phase 5 occupies the single `inherited_from` slot and
  Phase 4 has none, so the design half of each cycle simply fell out.

Reading the log is where you FIND the bar; the stem folder is where you GET it.

**AND CHECK THE METRIC, not only the number.** Two quantities can carry one name across two
artifacts and not be the same quantity. Before comparing anything to a bar, read the metric's
DEFINITION out of the script that computed the bar, not out of the word used for it. Measured
2026-09-08: a cycle's bar was *"mean nRMSE below 0.538"*, which is a per-YEAR series RMSE
normalised by the observation mean; the same cycle's own Phase-4 analysis computed a scalar
relative miss of the window-reduced value under the same name, where the identical reference case
scores 0.307. The projection was compared against a number from the other definition and reported
as halving an error it did not halve. The rule that catches it is one line long: **the metric comes
from the script, never from the name.**

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

**The same rule governs an UNSCORED objective metric, and it is easier to break because the metric
lives in a script rather than in `targets.yaml`.** Import the round's own function; never rewrite it.

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

## Step 1c — the CUMULATIVE figure, and the question it exists to answer

**Every cycle's Phase 6 produces a second, cumulative figure in its `phase_results/{stem}/` folder** (PI, 2026-09-06), alongside the per-experiment one Step 1b requires. Step 1b's figure shows what THIS cycle's variants did. This one shows **where the round as a whole now stands**: the ensemble background, every simulation any cycle has tested so far, the two best of each cycle, and the current best drawn on top, all against the measurements over the observation window.

### The question it must answer, in words, in the log

> **Has any experiment in previous cycles actually improved on what the initial ensemble already contained?**

**Ask it every cycle and write the answer down.** It is the only check that distinguishes a round making progress from a round rediscovering its own starting sample, and nothing else in the loop asks it: Phase 2 ranks the ensemble, Phase 6 judges one experiment against one bar, and neither compares the round's accumulated output against the design it started from.

**Answer it TWO ways, because they disagree and the disagreement is the finding.**

1. **On the round's declared cost.** Is any tested case better than the best ensemble case? Often no, and a "no" here is worth stating plainly rather than hiding behind the cycle's own verdict.
2. **On DOMINATION over the per-target relative errors.** Is any tested case not dominated by ANY case in the ensemble, i.e. does it occupy ground the sample never reached? This is the question a composite cannot answer.

**Measured on one round's eighth cycle:** zero of 24 living tested simulations beat the ensemble's best on the composite, and the round's own best tested case turned out to BE an ensemble case re-run as a control rung. On domination the same data said the opposite: six tested configurations were not dominated by any of 1,245 alive ensemble cases, four of them from the most recent cycle, one reaching a standing-carbon error of 17.6% that the sample never achieves. Reporting only the composite would have said eight cycles produced nothing; reporting only in-band counts would have missed it too. The round's obstacle was a RELATION between two targets, and an aggregate is the wrong instrument for a relation.

### Four traps, each of which produced a wrong answer before it was fixed

- **A composite alone REWARDS COLLAPSE, so it cannot rank "best".** A dead stand has every target near zero, so every relative error is -1 and the composite approaches 1.0, which beats any case overshooting by more than a factor of two. Measured: a case whose standing carbon was 0.187 g C m-2 outranked live cases holding two of three targets. **Rank by in-band count first, composite as tie-break, and exclude cases below the model's viability floor from ranking entirely** — draw them, since they are simulations the round ran, but never let one be "best".
- **Domination needs a TOLERANCE, because a V0 rung REPRODUCES its base.** Tested against the ensemble with exact comparison, a control rung reports itself as un-dominated "new ground", which is a floating-point artifact and a false claim on the figure. Equality must count as domination.
- **Filter the comparison population to LIVING cases, and label it with the number you actually compared against.** Using the completed count where the alive count was meant put a false number in one figure's legend and title; the verdict was unaffected, since a dead case dominates nothing, but the label was untrue.
- **Mark which tested cases are CONTROLS, and derive it rather than assume it.** A V0 rung reproduces an ensemble case exactly, so it is identifiable by matching the scored values — not by a naming convention, which mislabels a V0 that failed its own gate. If the round's best-scoring simulation is a control, the round has not beaten its starting point, and that belongs in the log rather than buried in a table.

### Building it — INCREMENTALLY. Do not re-extract the ensemble.

**The ensemble is already extracted and must not be pulled again** (PI, 2026-09-06). Phase 1 produced the ensemble time series and the scored scalars for every completed case. A cycle adds only the handful of simulations it ran, cached in that cycle's own stem folder so the stem invariant holds and a re-run costs nothing. Re-extracting a full ensemble to redraw this figure costs roughly forty-five minutes of shared-filesystem I/O and buys nothing; one session started such a pass and it was stopped for exactly that reason.

Where the full ensemble's TIME SERIES was only sampled, say so on the figure and let the full ensemble contribute its scored RANGE from the Phase-1 matrix instead — two different populations, both honest, neither mislabelled as the other.

**Verify before plotting.** Each cached series, reduced over its target's own window, must reproduce that cycle's Phase-5 scorer for the same case. If it does not, the figure and the scores disagree for a reason no reader can see, so the script should refuse rather than plot.

A case that has adopted this carries the two pieces as templates in `use_cases/{Model}_{Case}/scripts/` — one incremental extractor, one plotting script — copied into the cycle's `phase_results/{stem}/` and adapted there, per the three-tier rule below.

## Step 2 — interpret + extract lessons (you are the reasoning)

Mirror `interpret_results` (targets improved/degraded, hypothesis_status **honestly** — partial is
PARTIAL, not SUCCESS; cross-PFT impact) and `extract_lesson` (is it a **discovery**? a **failed
approach**? a named pattern — Allocation Paradox, Perfect Storm, Mortality Trap?). Verify any
mechanism against the KB's five surfaces and then **in source** before asserting it — RAG alone is
one surface of five, and this skill's KB-first block above is the full rule. **If the hypothesis was
REJECTED, Step 2b applies and is stricter:** finding the mechanism behind the rejection is required,
not optional, and a claim about ABSENCE has to be traced rather than grepped.

## Step 2b — a REJECTED hypothesis needs its MECHANISM, traced in source

**A verdict of REFUTED with only the SHAPE of the failure recorded teaches the next cycle almost nothing** (PI, 2026-09-06). "The lever is a cliff", "it died", "the dose response turned over" are phenomenology. The cycle's real output is **why**, and a rejection is often more informative than a confirmation because it usually means the hypothesis had the mechanism wrong — which is usually a fact about how the MODEL works rather than about one dose at one base, and is therefore reusable by later cycles. **That does not make it a model-LAYER knowledge entry.** Where it goes is Step 3's question, and the answer there is the case's own store until a second case reproduces it; what makes the mechanism reusable is that it is traced in source and cited, not that it is filed high.

**Ask three questions and answer them in the log.**

1. **What did the hypothesis assume the parameter DOES, and is that what the code does?** A rejection very often turns out to be a sign error or a misread role. Check the direction the parameter enters its equation: a term in a **denominator** relaxes what a reader expects it to tighten.
2. **Which quantity actually changed, and which one did not?** Trace from the parameter to the scored variable, naming every intermediate. Where the chain passes through a `min`, a `max`, or a saturating term, that is usually the whole result: a `min()` that switches branches produces a lever that is inert on one side and near-linear on the other, which presents as a threshold and is not one.
3. **Does the mechanism explain the SMALL moves as well as the big one?** A story that explains the collapse but not the near-zero rung is half a story. The sign and size of the smallest response is the sharpest test available, and it is free.

### Confirm by TRACING, and be most suspicious of a claim about ABSENCE

**A statement that something is "never read", "not used", or "has no effect" is the highest-risk claim in this step, and one grep does not establish it** ([[feedback_dont_assert_absence_from_one_grep]]). Before writing one:

- **Check that your search covered the tree.** Enumerate with `git ls-files '*.F90' | wc -l` and compare against what your pattern actually matched. Index-based, so it satisfies the bounded-search rule and is not a filesystem walk.
- **Follow the variable through its aliases** — a module array, its pointer in an API type, and the local name in an `associate` block are three names for one thing, and a consumer may use any of them.
- **Distinguish the AGGREGATE from the DRIVER.** A per-PFT or per-column summary of a quantity is frequently diagnostic while the per-branch or per-node version drives the model. They differ by a suffix.
- **Classify each hit as a read or a write** rather than counting occurrences. A variable with twenty appearances and two right-hand-side uses, both in the output path, is genuinely inert; the same count with one use inside a rate equation is not.

**MEASURED, and it is why this step exists.** One cycle's refutation was first written up as "the parameter is a cliff, not a lever", then re-analysed and written up a second time with two confident negatives: that the photosynthesis routine reads no leaf nutrient state, and that the direct pathway therefore could not produce the observed collapse, which was offered as a possible model defect. **Both were false.** The searches had covered **186 of the repository's 214** source files, missing 38 deeper and 28 outside the searched directory. A complete trace found the mechanism fully determined in one line: leaf protein accumulates as `AMIN1(nitrogen route, phosphorus route)`, and leaf protein sets Rubisco surface density, which sets `Vmax`. While nitrogen is the minimum the parameter is inert, which is why the small rung moved +0.4%; once phosphorus becomes the minimum, photosynthetic capacity falls in proportion to it, which is the collapse. The trap that made the wrong story plausible was that the **aggregated** ratio really is read only by the history output, while the **per-branch** ratio one line away is the driver — near-identical names, opposite roles.

**Record the chain, not the conclusion.** A mechanism is checkable only if each link carries its `file:line`, so write it as a chain a reader can walk. And name what the mechanism does NOT explain: an honest residual is a pathway for the next cycle, while a mechanism stretched to cover everything is how a wrong story survives.

**THE SAME RULE APPLIES TO AN ABSENCE CLAIM ABOUT THE ROUND, and this phase is where those get written** (PI, 2026-09-08). A synthesis sentence — *"no lever does X"*, *"every lever we measured behaves like Y"*, *"the round has never tried Z"* — is exactly as risky as *"this variable is never read"*, and it is verified the same way: **trace it to the artifact.** The `decisions[]` list and the auto-generated `## Reasoning chain` tell you WHICH cycle and WHICH log; the log names the stem; **`phase_results/{stem}/` and the data file the script wrote are what settle it.** Do not stop at the index. Full rule and the measured episode: `calibration-discipline` §"A CLAIM ABOUT WHAT THE ROUND HAS ESTABLISHED IS VERIFIED AT THE ARTIFACT". The short version of that episode is that one refinement log declared the round had never found a certain kind of lever while its own reasoning chain named the refuting parameter 35 times.

## Step 3 — stage the knowledge candidates. DO NOT WRITE THEM YET

**A curated write happens AT OR AFTER the Phase-4 human gate in Step 4, never here.** This step
identifies the candidates and records them in the log; the write itself is `round-housekeeping`'s,
after the gate clears. `calibration-discipline` item 8 is the rule — *no curated-KB injection until
a Phase-5 test verifies the hypothesis AND the human gate clears* — and this skill's own
Related-skills entry already says `round-housekeeping` is the post-gate curation step. This step
used to sit before Step 4 with no qualifier, which put it in contradiction with both.

So in this phase: **name each candidate in the log's `## Discoveries (for gained_knowledge)` and
`## Failed Approaches (DO NOT REPEAT)` sections, and write `Memory written: none` unless the gate
has already cleared.**

**And when the write does happen, the DESTINATION is the CASE's own store.**

- **A finding you originated** → `use_cases/{Model}_{Case}/memory/gained_knowledge/`, via
  `inject-knowledge`. That is the default and usually the only correct destination: a rate, a
  refutation or an elasticity measured at one base at one site is a statement about that case.
- **The online agent's staged proposals** (`auto_discovered_pending.json`) → review +
  promote/discard via `curate-knowledge` (`tools/review_pending_knowledge.py`). This is the Tier-3
  write gate.
- **Promotion onward to `memory/<model>/gained_knowledge/` is a SEPARATE, later, evidence-gated
  decision**, not something this phase does. One case showing a relation is one observation (root
  `CLAUDE.md`, §Adaptive Memory: *a curated discovery lands in its own case's store; it is not
  promoted anywhere by default*).
- **Neither store is the knowledge GRAPH.** The model knowledge graph represents model SOURCE CODE
  relationships — parameter, mechanism, model variable — and is independent of any case and any
  target. A measured response is an emergent property of a model RUN, dependent on forcing, base
  and position on the response surface, so it never becomes an edge. A measurement may PROMPT a
  source read that adds an edge; it never justifies one (PI, 2026-09-08).

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
   **Re-read the Phase-3, Phase-4 and Phase-5 logs to write it — do not compose it from recall.** Step 0 already put the Phase-4 and Phase-5 logs in front of you for the VERDICT; the synthesis needs them again for a different reason, because it must separate what the cycle established from what it merely tried, and that distinction is in the inner-loop iterations and the execution record rather than in the final numbers. **Cite all three stems in this section**, so a reader can walk the cycle without reconstructing it.
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
    exhaustion_justification="<why no in-range experiment remains> | ''")
#   NOTE: do NOT pass max_experiments. It DEFAULTS to the machine config, and the default is the
#   fix for a measured bug: it used to default to 10 while a2mc_noncime_config.sh exports 20, so a
#   case at cycle 12 recorded "12 of 10" and the routing gate read as exhausted eight cycles early
#   (tools/workflow_state_offline.py:409-412). Passing the literal reinstates exactly that bug.
violations = st.validate_phase6_decision()   # MUST be [] before you act
```
`stop_model_dev` / `redesign_6to0` are rejected while `experiment_count < max_experiments` and a named
`next_targeted_experiment` remains (that is a `rethink_6to3`); `stop_model_dev` also requires
`next_targeted_experiment == NONE` + a non-empty `exhaustion_justification`. On `rethink_6to3`, advance the
counter via `st.set_position(experiment_count=experiment_count+1)` and `st.save()`.

- **All targets met** → converged (Phase 7). The resolver routes through BOTH close positions before `done`: the round close (three report steps) and then the housekeeping with its **fuller** campaign-close checklist. The terminal deliverable is the **final configuration** — see the contract below; it is seven required elements, not a phrase.
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
> `inherited_from` names ONE predecessor stem — for this phase that is Phase 5. **Phase 6 has two
> parents**, so name the Phase-4 stem in the body as well (Step 0); a handshake field with one slot is
> not a reason to leave the design half of the cycle uncited.
>
> The log also carries `## Reasoning chain`, rebuilt from `workflow_state_offline` — so keep that
> state updated with the FINDING, not a label; the chain is only as good as what each phase wrote.


Log via `calibration-log` (phase log → `PhaseLogger.log_refinement`). Standardized reporting:
`summarize-calibration-round` (this round) / `compare-calibration-rounds` (vs prior). Then route per
Step 4. **Evidence gate (docs/33):** the refinement log must cite the evaluation artifacts produced this
session in `phase_results/{stem}/` — the extraction of this cycle's **scored targets**, whatever
they are for this case, plus **BOTH required figures**: the per-experiment overlay of Step 1b and
the cumulative figure of Step 1c. Run `python tools/check_offline_log_evidence.py <log.md>`
(exit 0) before recording any candidate. The scored targets are the case's own; a case with no
vegetation scores none of the plant variables an earlier wording assumed.

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
  figure template for a scored-target-versus-observation time series — that template is
  named for the vegetation case it was written from, so read it as the shape to match rather
  than as a claim that every case scores biomass.
- **Curate staged proposals** → `curate-knowledge`. **Inject a vetted finding** →
  `inject-knowledge`. **Both run at or after the Step-4 gate, not during this phase** (Step 3), and
  both write to `use_cases/{Model}_{Case}/memory/gained_knowledge/` unless a separate,
  evidence-gated decision promotes onward.
- **Deeper investigation / figure** → `scientific-analysis`. **Round reports** →
  `summarize-calibration-round`, `compare-calibration-rounds`; an **integrated, cross-cutting write-up**
  for a human reader (an investigation synthesis beyond the standardized round summary) → `write-report`.
- **Next:** converged (Phase 7), or loop to `phase3-diagnosis` (rethink) / `phase0-design` (redesign).


## The Phase-7 CONVERGED deliverable — the final configuration

**Contract added 2026-08-25 (T10.1).** Until then, three skills stated this deliverable in the same seven words — *"write the final config + round summary"* — and **nothing anywhere said what the artifact is**. A campaign's actual product had no specification, which is the same class of gap the per-round provenance ledger closed one level down.

**The deliverable is the DIRECTORY `use_cases/{Model}_{Case}/reports/{stem}_FINAL_CONFIGURATION/`**, beside the round reports: `final_configuration.md` carrying elements 1 to 6, `inputs/` carrying element 7, and a `MANIFEST.md5` over both. Record the markdown file's path in the state with **`st.set_final_configuration(path=..., reproduce_command=..., archived_binary=...)`** — NOT via `set_round_close`, which records the ROUND report and has no companion field for this. It must carry all seven:

| # | Element | Why it is not optional |
|---|---|---|
| 1 | **The parameter values** — the RANKED SET, not one configuration: the top N on the criterion `targets.yaml` scores, each with every calibrated parameter, its value and units, and a provenance row saying where it came from and where it is discussed | the result itself, and a calibration's result is a set. "Best" depends on what the parameterization is for, and a single pick cannot express that. **Measured 2026-09-09:** this row read "its final value", singular, and a round shipped one configuration that ten sampled ones beat on the scored criterion |
| 2 | **The base file they modify**, by path and content hash | a value is meaningless without the base it perturbs |
| 3 | **The case** that achieved them — case name, run root, and the scored result per target against the observations | someone must be able to point at the run |
| 4 | **The model binary, ARCHIVED** — commit, branch, and the archived executable path, **never the live build path** | the build tree is shared and every build overwrites it in place; a queued job resolves its exe at run time (`feedback_bind_runs_to_archived_binaries`) |
| 5 | **The command that reproduces it**, verbatim and runnable | a description of how to reproduce is not a reproduction |
| 6 | **What was NOT achieved** — the residual, routed to model development or to data | a converged campaign still has one, and the next person will otherwise rediscover it as a surprise |
| 7 | **The INPUT BUNDLE, copied in — not referenced** — every file the run reads: the namelist or deck, the submit script, each parameter surface, and the forcing/driver data, under `inputs/`, with a `MANIFEST.md5` | elements 2 to 5 identify inputs by PATH, which is a record and not a reproduction path. A path resolves on one machine; a campaign whose drivers sit in a gitignored directory is unreproducible while every path in it is correct |

**Three rules carry element 7.** **Copy what the run READS, not what it WROTE** — a case directory is mostly output. **Reference the executable** by commit, branch, archived path and checksum rather than bundling a machine-specific binary the other elements already pin. **Ship the repointing recipe WITH the loop that asserts every repointed path exists**, because the failure is asymmetric: a missing driver aborts loudly, a stale parameter-file pointer silently reproduces the wrong configuration. Run the recipe before writing that it works.

**The bundle is also the handoff artifact** — the tar returned to the contributor who supplied the measurements. Check the case is off every public sync leg's INCLUDE list before copying their data into the repository.

**Why here and not in the round report.** The round report is a narrative for a reader; this is a machine-checkable record for a reproducer. `check_workflow_state_offline.py` asserts a converged state carries a resolvable pointer to it, which a narrative section cannot satisfy.
## Before you finish

**Discipline self-review (automatic).** Before advancing the state, re-check the [`calibration-discipline`](../calibration-discipline/SKILL.md) items that apply to this phase. This is unprompted and per-phase — the user does not have to ask (memory `feedback_schedule_periodic_reviews_with_a_real_mechanism`).

