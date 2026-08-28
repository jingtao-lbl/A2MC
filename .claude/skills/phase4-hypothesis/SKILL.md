---
name: phase4-hypothesis
visibility: public
category: phase
description: Run Phase 4 (HYPOTHESIS) of the A2MC calibration workflow as the offline agent — the human-in-the-loop analog of the orchestrator's `_run_hypothesis()` / `reasoning.generate_hypothesis()`. Turn a Phase 3 diagnosis into specific, testable hypotheses with parameter changes + expected outcomes, and FIRST try to test them against the existing Morris ensemble (skip-testing — reads existing data, no new simulations) before committing to a Phase 5 experiment. Use when the user says "generate a hypothesis", "what should we test next", "design the experiment", "can we test this with existing data", "run Phase 4", after Phase 3 diagnosis.
modes:
  requires_fates: false      # calibration-workflow phase skill; mode resolved at runtime via describe_mode
  nutrient_pathway: any
  scope: [calibration]
  summary: "Offline analog of Phase 4 (hypotheses + skip-test on existing data). Applies in every calibration mode."
---

# Phase 4: Hypothesis (offline agent)

> **Driven by `calibration-goal`** — the run-to-convergence driver dispatches here when `WorkflowStateOffline.current_phase` routes to this phase; do the phase, then update + `save()` the state so the driver advances. Also runnable standalone (one phase).

The offline analog of `_run_hypothesis()`. Online, `reasoning.generate_hypothesis()` proposes the
hypothesis and decides `test_with_existing`; **offline, YOU do both** — frame a mechanistic,
falsifiable hypothesis with concrete parameter moves and expected target directions, then decide
whether the existing ensemble can already answer it.

> **Floor, not ceiling.** The online agent proposes one hypothesis per diagnosis, bounded by its
> prompt. As the offline agent you can generate + weigh several, bring in literature or satellite
> evidence (`offline-testing-workflow` Steps 1–4), design a sharper falsification test, or invent a
> skip-test the fixed loop has no method for. Match the discipline (diversity vs prior experiments,
> honor failed approaches, quantified success criteria), then reason more widely.

**Inputs (from Phase 3):** ranked root causes, implicated parameters, selected base cases.
**Deliverable:** a `Hypothesis` (name, mechanism, parameter moves with bounds, expected outcomes,
success criteria, confidence) + a routing decision: skip-test now, or queue a Phase 5 experiment.

## Step 1 — generate the hypothesis (you are the reasoning)

Mirror the `Hypothesis` schema (`reasoning/schemas.py`): **name**, **mechanism** (verify against RAG,
never from a param name), **parameters** (list of `{name, current, proposed, rationale}`, plus
`pft` / `organ` / `bounds` when relevant — FATES names; 2-organ params need dual leaf+fineroot
entries), **design_type** (`cumulative` or `factorial`), **expected_outcomes** + **success_criteria**
(quantified, e.g. "leaf_pft9 within 20%"), **confidence**. Must target a *different* mechanism
from previous experiments. **Check this mechanically, against the SITE store** — the per-case
`use_cases/{Model}_{Case}/memory/gained_knowledge/`, not the generic repo-root one:

```python
from memory import MemoryManager
m = MemoryManager("use_cases/{Model}_{Case}/memory/gained_knowledge")
m.check_do_not_repeat([{"parameter": "CNRT", "old_value": 0.016, "new_value": 0.020}])
```

`check_do_not_repeat()` already exists and returns the matching failed approaches — the obligation
has been prose for months while the callable sat unused. A refutation is a property of a
`(parameter, direction, base)` triple, so a hit is a prompt to check the DIRECTION and the BASE,
not an automatic veto.

## Step 2 — can existing data test it? (skip-testing inner loop, Phase 3↔4)

If the hypothesis is answerable from the **existing** Morris ensemble — a correlation, a high-vs-low
group contrast, a threshold, or a custom test — set `test_with_existing=true` and run it via
`phases/phase4_hypothesis/test_with_existing_data.py` (methods: comparison / correlation / threshold
/ diagnostic / custom_script). **Visualize the skip-test result** — the high-vs-low group contrast, the
scatter + fit, or the threshold split — as a figure (via the `plotting` skill); a skip-test verdict rides
on a distribution/relationship that a table of numbers flattens ([[feedback_figures_over_tables_over_words]]).
This is the 3↔4 inner loop: accumulate the evidence, and either

- **confidence ≥ `--confidence-threshold` (**`$A2MC_CONFIDENCE_THRESHOLD`**, from the machine config;
  0.95 if unset)** (or the pattern is clear) → conclude without
  new simulations; or
- **feed the insight back to `phase3-diagnosis`** and refine the next hypothesis (loop).

**Inner-loop counter (enforce it — the online agent does so in code).** This is the `skip_testing_count`
loop, capped at `--max-skip-testing` (**`$A2MC_MAX_SKIP_TESTING`**, from the machine config (`a2mc_noncime_config.sh` / `a2mc_config.sh`); 10 if unset). On each
skip-test, **increment `skip_testing_count`** in
`workflow_state_offline_r{RR}.json`. Exit the inner loop when **confidence ≥ `$A2MC_CONFIDENCE_THRESHOLD`**, OR `skip_testing_count`
= `--max-skip-testing`, OR **no further question about this cycle's mechanism is answerable from
existing data**. A hypothesis needing values outside the Morris range (`test_with_existing=false`)
retires **that hypothesis** to Phase 5 — it is not by itself the loop's exit, and reading it as one is
how this loop stopped entering at all (see "THE EXIT IS PER-HYPOTHESIS" below). `skip_testing_count` **counts within the current experiment cycle only — it resets to 0 when
Phase 5 begins.**

> **Footgun — untestable in range.** If the hypothesis needs parameter values *outside* the Morris
> sampled range, existing data can't test it — that hypothesis is Phase 5 work. Don't force a
> skip-test the ensemble can't actually answer. **But that retires the hypothesis, not the
> iteration:** before routing, check whether a *different* question about the same mechanism is
> answerable in range (below).

### THE EXIT IS PER-HYPOTHESIS, NOT PER-CYCLE — and that is how this loop dies

`test_with_existing=false` is a property of **one hypothesis**, not a verdict on the cycle. Taking it
as the cycle's exit means: frame one hypothesis, skip-test it, discover its *experiment* needs new
simulations, and leave — spending the **expensive** loop while the **free** one still had questions.

**Measured across one campaign's three rounds: 46 phase-3/4 logs at `iter01`, 4 at `iter02`, none
higher, against the configured cap (`$A2MC_MAX_SKIP_TESTING`, 10 at the time of measurement).**
Every one of one round's ten cycles sits at `iter01`. The loop was not
converging early; it was never entering.

**So before routing to Phase 5, ask explicitly and answer in the log:**

> *Is there another question about this cycle's mechanism that the EXISTING ensemble can answer?*

If yes, that is the next iteration — increment `skip_testing_count` and run it. Only when the honest
answer is no does the cycle route to Phase 5. Costed: a skip-test is minutes of arithmetic over data
already on disk; a Phase-5 cycle is hours of compute plus a scoring and analysis pass.

**And keep asking while Phase 5 RUNS.** Working discipline item 3 below already says not to idle
during an in-flight experiment, and this is the work it means. A worked sequence, all three at zero
compute during one cycle's simulations: iteration 1 established that a round's three targets form a
three-way constraint rather than a two-way trade; iteration 2 found the one parameter that moved the
binding target without harming the other, giving the next cycle a design; **iteration 3 then refuted
that design** by showing the same parameter drives a third target out of its band, which the next
cycle would otherwise have discovered by spending itself.

### A conditioned claim must be checked for the cost it conditions AWAY

The specific trap iteration 3 caught, because it will recur. Iteration 2 computed its correlations
over cases where one target was *already* in band and concluded a parameter moved a second target
without touching a third. True **within that population** — and silent about the fact that moving the
parameter **takes cases out of it**.

**Conditioning on a variable the intervention itself moves hides exactly the cost that matters.** So
whenever a screen is conditioned, pair it with the membership check:

> *Does this lever preserve membership in the set I conditioned on, over the range I intend to move it?*

Same error class as reading a group contrast on a downstream variable as a mechanism, which this
workflow has already produced once and retracted.

`phases/phase4_hypothesis/synthesis.py` consolidates multi-cycle skip-testing insights into
experiment designs when you exit the loop toward Phase 5.

## Step 2b — EVERY hypothesis carries its own test plan and falsification bar

Online, `design_experiments(hypothesis, base_case)` returns a `List[Experiment]` — so each
hypothesis mechanically gets concrete experiments, each with `modifications`,
`expected_results` and a **`success_threshold`**. Offline nothing forced that, and the gap is
**worse here**, because this skill invites you to weigh *several* hypotheses where the online
agent proposes one.

For **each** hypothesis you carry forward, state:

| | |
|---|---|
| **How it is examined** | skip-test on existing data (which cases, which reduction) **or** the Phase-5 variants that test it |
| **Expected outcome** | the direction and magnitude per target |
| **Success criteria** | the **quantified bar** that would confirm it |
| **What would refute it** | the observation that kills it — if nothing could, it is not a hypothesis |

Log the bar via `success_criteria=` on `log_hypothesis` (it emits `## Success Criteria`).
`expected_outcomes` says what you think will happen; `success_criteria` says what settles it.
Phase 6 rules CONFIRMED/REFUTED against this bar, so a hypothesis logged without one leaves
that verdict unanchored.

If you carry N hypotheses, log N of them (`log_hypothesis` is per-hypothesis) rather than one
merged entry — Phase 6 evaluates them individually and the reasoning chain tracks each.

## Step 3 — needs new simulations? design the experiment → Phase 5

If it can't be answered with existing data, the hypothesis becomes a parameter-sweep experiment.
**Hand off to the model's Phase-5 procedure** — `offline-testing-workflow` for ELM/ELM-FATES,
**`ecosim-run-workflow`** for EcoSIM, **`pflotran-run-workflow`** for PFLOTRAN, **`ats-run-workflow`** for ATS (all non-CIME; none of them transfer to each other, let alone to FATES) — it owns variant design, param-file
generation + verification, the V0 reproducibility gate, submission, and analysis. Invoke
`phase5-testing` for the phase-level routing.

## Step 4 — log and hand off

> **The log is a LIVING record — start it now, enrich as the phase runs.** Not an end-of-phase
> write-up. Full contract in `calibration-log`.
>
> **This phase's expected sections** — `PhaseLogger` names any you leave empty:
> Mechanism · Parameters to Modify · AI Reasoning and Analysis · Expected Outcomes · Success Criteria · Experiments Planned.
>
> **`Success Criteria` is the one that decides Phase 6.** Pass it explicitly — `log_hypothesis`
> now takes `success_criteria=` — or Phase 6 rules CONFIRMED/REFUTED against a bar no log holds.
>
> **Set the handshake before the `log_*` call**, so the chain is traceable:
> ```python
> logger.set_phase_handshake(
>     inherited_from="<phase3 log STEM> — root causes, implicated params, base cases",
>     handed_to="the hypothesis + its success_criteria bar + the planned experiments",
>     next_action="<skip-test to run, or the Phase 5 experiment to launch>")
> ```
> The log also carries `## Reasoning chain`, rebuilt from `workflow_state_offline` — so keep that
> state updated with the FINDING, not a label; the chain is only as good as what each phase wrote.


Log via `calibration-log` (phase log → `PhaseLogger.log_hypothesis`): the hypothesis, parameter
moves, skip-test evidence + verdict, and the routing decision. **Hand off** to `phase5-testing` (new simulations)
or back to `phase3-diagnosis` (another skip-test cycle). **Advance the driver state:** on route to Phase 5
`st.set_position(current_phase="testing")`; on a skip-test loop-back
`st.set_position(current_phase="diagnosis", skip_testing_count=<n+1>)`; `st.save()` either way
(`tools/workflow_state_offline.py`).

**Evidence gate (docs/33).** A skip-test log must cite the skip-test **script + output + figure** produced this session
(`test_with_existing_data.py` result + the Step-2 visualization in `phase_results/{stem}/`), not just an assertion. Run
`python tools/check_offline_log_evidence.py <log.md>` (exit 0). Note: a hypothesis is a hypothesis until a
Phase-5 test confirms it — do not promote it to the curated KB from here (that's the `docs/33` §3b KB gate).

## Working discipline (offline agent — applies across Phase 3↔4)

1. **Log the integrated story, not a snapshot.** A diagnosis/hypothesis log must carry the *whole
   reasoning chain*: what has already been tested and learned, the logic that led here, why each
   candidate was kept or ruled out, and **why the next step is the correct direction**. Credit the
   canonical prior log instead of re-deriving it; when a new finding overturns an earlier one, supersede
   it. A well-formed log lets a cold reader reconstruct the *argument*, not just the conclusion.

2. **Read your checked-out model source FIRST, then upstream git.** To verify how a parameter / line /
   mechanism behaves, read the **actual checked-out source** (`$A2MC_E3SM_ROOT/...`) and the **param file
   in use** BEFORE querying the upstream model repo. Your local tree may be a custom branch that diverges
   from upstream; ask upstream "has this been fixed since" *after* you know the local truth.

3. **Keep the inner loop turning while sims run.** Phase-5 simulations take hours — do NOT idle waiting.
   Continue diagnosis / hypothesis / skip-test work (the 3↔4 inner loop) in parallel with the in-flight
   experiment. Idle waiting is an online-agent limitation you don't share
   ([[feedback_offline_agent_drives_the_workflow]]).

4. **Stem invariant: the log stem is canonical.** Every `phase_results/{stem}/` folder MUST have a
   matching `logs/{stem}.md`. Decide the stem when you write the log and reuse that exact stem for
   `phase_results/` — never mint a separate letter for the artifacts (`docs/31`; via `PhaseLogger`
   offline mode). (Mirrored in `phase3-diagnosis`.)

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
- **Experiment execution (the new-simulation path)** → `phase5-testing`, which routes by model:
  `offline-testing-workflow` (FATES), `ecosim-run-workflow` (EcoSIM), `pflotran-run-workflow` (PFLOTRAN) or `ats-run-workflow` (ATS).
- **Literature / satellite grounding for a hypothesis** → `offline-testing-workflow` (Steps 1–4),
  `scientific-analysis`.
- **Next:** `phase5-testing` (new simulations) or `phase3-diagnosis` (skip-test loop).

## Changelog

- 2026-08-27: **Names every adapter model's run skill at the Phase-5 handoff, not EcoSIM alone**
  (PI-directed, first PFLOTRAN campaign), and states that the adapter models do not transfer to each
  other. A handoff that names one of three sends the other two to the wrong procedure or to none.

- 2026-08-22 (later): **Adds the three-tier script rule**: look in `use_cases/{Model}_{Case}/scripts/` for a canonical script TEMPLATE first, copy it into this phase's `phase_results/{stem}/` and ADAPT it there; write one from scratch when no template exists; a script's SECOND use is the trigger to promote it into `scripts/`. PI-directed, extended to every phase skill after the rule initially landed in only two. Does not conflict with "one canonical script per figure, never two copies" -- the canonical script stays with its figures, the canonical script TEMPLATE stays in `scripts/`. Evidence: 7 byte-identical duplicate script pairs measured across one site's phase_results folders. Checker `tools/check_case_script_tier.py`.

- 2026-08-22 (later): **Loop limits and the confidence threshold now quote their config variables instead of literals.** PI-caught in `calibration-discipline` and swept across every skill stating one. `A2MC_MAX_SKIP_TESTING`, `A2MC_MAX_EXPERIMENTS` and `A2MC_CONFIDENCE_THRESHOLD` live in `a2mc_noncime_config.sh` / `a2mc_config.sh` and **nowhere else** — a site or round config does not set them — and `orchestrator.py:3567-3571` reads all three, so a skill quoting `10` or `0.95` contradicted the running agent the moment a value changed. Measurement narratives keep their number but now say it was the value at measurement time. Companion to v2.282, which fixed the same hardcoded copies in `tools/check_workflow_state_offline.py`. [[feedback_bind_derived_facts_to_their_source]].

- 2026-08-22: **The inner loop was never entering, and Step 2 now says why and what to ask.** `test_with_existing=false` is a property of ONE hypothesis and was being read as the cycle's exit, so every cycle framed one hypothesis, skip-tested it, found its experiment needed simulation, and left — spending the expensive loop while the free one still had questions. Measured across one campaign's three rounds: **46** phase-3/4 logs at `iter01`, **4** at `iter02`, none higher, against a cap of 10, with all ten of one round's cycles at `iter01`. Adds the explicit pre-routing question (is there another question the EXISTING ensemble can answer?), its cost argument, the instruction to keep asking while Phase 5 runs, and a worked three-iteration sequence in which iteration 3 refuted the design iteration 2 proposed — before a cycle was spent on it. Also adds the trap that sequence exposed: **a conditioned screen must be paired with a check that the lever preserves membership in the conditioning set**, since conditioning on a variable the intervention moves hides the cost that matters. PI-directed. Details: `memory/dev_logs_adapterkit/20260822q_*`.

- 2026-08-18: Hand-off to Phase 5 now names the model's own procedure -- `offline-testing-workflow` (ELM/ELM-FATES) or `ecosim-run-workflow` (EcoSIM, non-CIME) -- rather than assuming the FATES one. Signal: PI, on adding the EcoSIM skill.
- 2026-08-16: **Names the `plotting` skill for any figure this phase produces.** The link was
  one-directional — `plotting`'s own cross-references claimed the phase skills apply its
  conventions, while most phase skills never mentioned it, so a session could produce figures
  for a whole case without the conventions or the view-the-PNG check ever being loaded. That
  happened: three sets of Lusignan figures were made before it was invoked, and the first
  invocation immediately caught a stats box drawn over the data. PI-directed ("every phase
  needs the plotting skill").
- 2026-08-02: Log step gained the block the other six phase skills received — living-record rule, this
  phase's expected sections, and `set_phase_handshake()`. It was the ONE phase skill missing it, found by
  the new PHASE-SECTIONS drift check on its first run rather than by re-reading.
- 2026-08-02: Added **Step 2b — every hypothesis carries its own test plan and falsification bar** (PI).
  Online, `design_experiments()` returns a `List[Experiment]` per hypothesis, each with a `success_threshold`;
  offline nothing required it, and the gap was worse here because this skill invites weighing SEVERAL
  hypotheses. Also fixed the underlying defect: `Hypothesis.success_criteria` existed in the schema but
  `log_hypothesis()` neither accepted nor emitted it in EITHER mode, so Phase 6 ruled CONFIRMED/REFUTED
  against a bar no log recorded. It now takes `success_criteria=` and emits `## Success Criteria`.
- 2026-07-15: Wired the conditional `set_position` state-advance in the handoff step (route to `testing` vs the 3↔4 skip-test loop-back to `diagnosis` with `skip_testing_count++`). Ported from demo `d3cbbf5` (offline-workflow enforcement sweep).
- 2026-07-15: **Skip-test result must be visualized** — Step 2 requires a figure of the contrast / scatter+fit / threshold split, and the evidence gate now cites script + output **+ figure**. Ported from demo `cd14d24`.
- 2026-07-06: Made the **inner-loop counter explicit** in Step 2 — named `skip_testing_count`,
  `--max-skip-testing` (`$A2MC_MAX_SKIP_TESTING`), `--confidence-threshold`
  (`$A2MC_CONFIDENCE_THRESHOLD`), the increment-per-skip-test, and the
  reset-to-0-on-Phase-5. Pairs with the Phase-6 middle-loop gate. Ported from demo `2d3f4b0`.
- 2026-07-06: Added the mirrored "Working discipline (Phase 3↔4)" block (integrated-story logs, source-before-upstream-git, keep the inner loop turning, log-stem-is-canonical). Kept in sync with `phase3-diagnosis`. Ported from demo, scrubbed of Kougarok specifics.
- 2026-07-02: Created — offline Phase 4 routine mirroring `reasoning.generate_hypothesis()` + skip-testing (`test_with_existing_data.py`); hands the new-simulation path to `offline-testing-workflow` / `phase5-testing`.

## Before you finish

**Discipline self-review (automatic).** Before advancing the state, re-check the [`calibration-discipline`](../calibration-discipline/SKILL.md) items that apply to this phase. This is unprompted and per-phase — the user does not have to ask (memory `feedback_schedule_periodic_reviews_with_a_real_mechanism`).