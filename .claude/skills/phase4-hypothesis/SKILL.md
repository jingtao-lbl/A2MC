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
success criteria, confidence), **the chosen base and the reason it was chosen** (Step 2a), and a
routing decision: skip-test now, or queue a Phase 5 experiment. Phase 5 follows this and may adjust
it for practical reasons; a change that would move the bar comes back here.

## Step 0 — BUILD THE CASE'S MECHANISM GRAPH, then design from it

**This phase owns the SCIENCE. Phase 5 owns executing what you decide here correctly.** The
division is worth stating plainly because it was ambiguous until 2026-09-07 and the ambiguity cost
a round: **what varies, from which base, to what values, against what bar is settled HERE and is
fixed before the handoff**; staging, verification, the gate and submission are Phase 5's.

So before framing a hypothesis, **construct the mechanism network for THIS CASE'S PROBLEM** — not a
general reading of the model, but the sub-network that produces the specific miss the round is
failing on. State the problem as a direction first ("the model underestimates standing biomass while
maintaining production"), then assemble, from the five KB surfaces below:

- every **mechanism** that feeds the scored variables in that statement, traced
  `parameter -> controls -> mechanism -> affects -> output`;
- the **`depends_on` couplings** among anything you intend to move together;
- and **which of those mechanisms this round's parameter list can actually reach.**

**That last one is the step that gets skipped, and it is the one that pays.** A sensitivity screen
cannot rank a mechanism the design has no parameter on, so "we tested it and nothing worked" is only
ever a statement about the reachable part. Measured on one site: the round's parameters sat almost
entirely on the production INPUT side of a carbon balance, **six whole categories and seven of
twenty-one plant-side mechanisms had no sampled parameter at all**, and sixteen experiment cycles
refuted lever after lever without any of them being able to move the part of the network that
mattered. The graph traversal that found it took minutes and existed on disk the whole time.

Two consequences for the design that follows:

- **A parameter outside the round's sampled list is testable.** Phase 5 stages values directly and
  is not confined to the Phase-0 design matrix, so an unreachable mechanism is a candidate now
  rather than a reason to open a new round.
- **Check the candidate is not INERT at this case before spending a cycle on it.** A parameter whose
  name matches the deficit is the most seductive and the most likely to be gated off. Trace the
  guard, not just the name: on one case the single parameter in the `turnover` category was an
  integer selecting a pattern rather than a rate, and every read of it was behind a
  woody-vascular test that is false for all three of that site's PFTs, so changing it would have
  done nothing. One command against five cases and a cycle.

## Step 1 — generate the hypothesis (you are the reasoning)

Mirror the `Hypothesis` schema (`reasoning/schemas.py`): **name**, **mechanism** (verify against the
model's KNOWLEDGE BASE first and the model SOURCE to confirm, never from a param name — see the
KB-first note below), **parameters** (list of `{name, current, proposed, rationale}`, plus
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

> **KB FIRST, SOURCE TO CONFIRM (PI, 2026-09-05).** Before reading model source to establish what a
> parameter, dimension or mechanism IS, query that model's knowledge base —
> `docs/<model>-knowledge-base/`, greppable with `git grep -i <term> -- docs/<model>-knowledge-base/`
> even with no RAG profile active. It usually carries the `file:line` you were about to go find, and
> it carries context the source does not: which axis a dimension belongs to, which of two
> similarly-named axes applies, what a prior round already measured. Then read the source to CONFIRM
> and cite it; source remains ground truth on what the model DOES. Measured 2026-09-05: a session reconstructed the EcoSIM `micresb` slot semantics from Fortran over several turns, while `docs/ecosim-knowledge-base/ecosim-codebase-wiki-2dea74d9/microbial_bgc/index.md:133` stated it in one line WITH the same `MicBGCPars.F90:178-179` citation -- and additionally recorded that the 2-slot necromass axis is NOT the 3-slot living-biomass axis, a distinction the source read missed and which turned out to matter. The cost of skipping it: a wrong root-cause diagnosis and two fixes that treated symptoms.
> **STAGE MATTERS, AND THIS IS THE CALIBRATION-STAGE RULE (PI, 2026-09-06).** While ONBOARDING a model the KB does not exist yet, source is the only recourse, and [[feedback_param_description_can_lie_verify_in_source]] governs: trace the read, then the internal variable, then its usage, especially before setting a bound. **At CALIBRATION stage the case is set up and the KB is assumed well-built, so the KB is where you START and it usually hands you the citation. It does NOT replace verifying in source: a KB page tells you what a thing IS, and only the code settles what it DOES -- or, just as often, what is ABSENT from it, which no page can state.** Query all five surfaces FIRST, then confirm in source. If you are in the source to LEARN what a parameter does rather than to CONFIRM what the KB told you, stop and name which it is: either you skipped the KB, or the KB has a gap. **A gap is a BUILD TASK** (rebuild the wiki, extend the curated seed, curate the round's findings at round close) and not something to route around every cycle. Full rule: [[feedback_full_mechanism_picture_before_designing_an_experiment]].
>
> **THE KB IS FIVE SURFACES, NOT ONE, AND THEY ARE NOT INTERCHANGEABLE. QUERY ALL FIVE, not the first one or two that answer.** They are: the **codebase wiki** `docs/<model>-knowledge-base/<model>-codebase-wiki-<commit>/` (`git grep -i <term> -- docs/<model>-knowledge-base/`, which works with no RAG profile active), the **RAG vector index** `rag/chroma_db/<profile>/` and the **knowledge graph** `rag/graphs/<profile>.json` (both via `HybridRetriever`), the **MODEL-level adaptive memory** `memory/<model>/gained_knowledge/`, and the **SITE-level adaptive memory** `use_cases/{Model}_{Case}/memory/gained_knowledge/`. The last two are the ones that get forgotten and they are populated: 21 entries for EcoSIM at model level, 28 for one case at site level, on 2026-09-05. Measured the same day on ONE parameter, `SPORC`: the knowledge-graph node carried a one-line description and units but no bounds, no code location and no mention of the two-slot axis, while the codebase wiki carried the slot semantics, the defaults AND the `MicBGCPars.F90` citation. Concluding "the KB does not have it" from the thin surface would have been wrong, so check the surfaces that hold that KIND of knowledge rather than the first one you open.
>
> **The curated overlay lives in DIFFERENT PLACES by model family, and looking in the wrong one reads as "it does not exist".** An adapter model keeps it at `models/<model>/curated_seed.yaml`; only the FATES profiles use `rag/data/curated_relationships_<profile>.yaml`. The active profile's `rag/metadata/<profile>.json` names the file its graph was built from, so read that rather than guessing the path. Measured 2026-09-06: `models/ecosim/curated_seed.yaml` was declared missing on the strength of an `ls rag/data/`, and it is human-authored and is what built the EcoSIM graph.
>
> **MEASURED COST OF QUERYING ONE SURFACE INSTEAD OF FIVE (EcoSIM_TeRaCON R1, seven cycles, 2026-09-06).** The graph stated `parameter:RMOM --controls--> mechanism:Microbial_Maintenance_Respiration --affects--> output:CO2_SEMIS_FLX_col`, the exact variable that case scores as `Fs`, and named 12 parameters for that output where a rank-correlation screen surfaced 4. The curated seed's `RMOM` entry carried the mechanism, the `NitroPars.F90:209` citation, the positive sign, the Morris rank and the `VMXO` coupling. The SITE store listed `RMOM` as an untested rank-1 alternative and recorded `CNRT` as a confirmed lever at +41% `plant_C`. All of it was re-derived from correlations across two cycles. The graph also declares three `depends_on` pairs among nine levers composed in one experiment, which is the documented explanation for a non-additivity that got written up as a discovery.
>
> **THEN GO TO THE SOURCE AND CONFIRM IT. This step is not optional and is not reserved for claims you have already decided are load-bearing.** Confirming is not the same as learning: at calibration stage you arrive at the source already knowing what the KB says, in order to check it, so the read is short and targeted. A long exploratory source read at this stage is the signal described above. The KB tells you what a thing IS; the source tells you what it DOES. Open the `file:line` the KB handed you in the checkout at `$A2MC_MODEL_PATH` and read **the code that USES the value**, not only its declaration or its description string: a `description`, a `long_name` or a `units` field in any of these surfaces can be wrong, which is a standing rule here ([[feedback_param_description_can_lie_verify_in_source]]) and is exactly why the KB read is a starting point rather than an answer. Confirming costs one command -- `git -C "$A2MC_MODEL_PATH" show HEAD:<path> | sed -n '<lo>,<hi>p'` -- against the hours a wrong mechanism costs downstream.
>
> **AND AN OUTPUT VARIABLE IS VERIFIED LIKE A PARAMETER.** The rule above is written about parameters and mechanisms; a tape field is a third category and the same failure arrives one category over. Before reducing one, establish that it is ACTIVE (a field registered `default='inactive'` is not written unless a run names it, and the model's `docs/<model>-knowledge-base/<model>_output_info_<commit>.cdl` carries a source-derived `:status`) and what its TEMPORAL SEMANTICS are -- rate, per-record increment, within-year cumulative that RESETS, run-cumulative, or stock. One reduction does not fit all five and the units do not separate them. Full rule and the measured cost: `calibration-discipline` item 3c.
>
> **A hypothesis is where this bites hardest**, because a mechanism asserted from a half-understood
> parameter propagates into the experiment design, the bar, and the compute spent on it.

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

## Step 2a — CHOOSE THE BASE, and choose it for the mechanism under test

Phase 3 hands up `selected_base_cases` with rationale; **which one this experiment runs on is a
scientific decision and it is made here.** Phase 5 restates the same rule from the execution side
(`phase5-testing` step 0b) and instantiates whatever you choose; the two must agree, so if you
change one, change both.

- **Rank by in-band count first, composite as tie-break, and EXCLUDE anything below the model's
  viability floor.** A collapsed stand posts a flattering composite for the wrong reason, since
  every relative error approaches -1.
- **Then choose from among the top cases by what THIS experiment needs. The current best is not
  automatically the right base.** The base must have HEADROOM on the targets the hypothesis will
  move, and a configuration with a better composite that sits on a band edge in the direction the
  experiment pushes is the wrong base for that experiment.
- **Say which one you chose and why, in the log.** The rationale is part of the design, because
  Phase 6 reads a refutation as a property of a `(parameter, direction, base)` triple and cannot do
  that if the base was implicit.

Worked example: one round deliberately based several cycles on a configuration that was NOT its
composite-best, because that one needed the smallest correction and therefore had the largest
allowance on the target each experiment had to spend. A rule that said "use the best case" would
have picked the wrong base every time.

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
**`ecosim-run-workflow`** for EcoSIM, **`pflotran-run-workflow`** for PFLOTRAN, **`ats-run-workflow`** for ATS (all non-CIME; none of them transfer to each other, let alone to FATES) — it owns variant **EXECUTION**: param-file
generation and verification, the V0 reproducibility gate, submission, and analysis. **The DESIGN —
which parameters move, from which base, in which direction, against what bar — is yours** (Steps 0,
2a and 2b). Phase 5 follows it and may adjust it for PRACTICAL reasons during execution, recording
what it changed; anything that would change what the experiment CONFIRMS or REFUTES comes back here
to be redesigned and re-logged. Invoke `phase5-testing` for the phase-level routing; its step 0b is
the execution-side statement of both that boundary and the base rule in Step 2a.

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

- 2026-09-08: **An OUTPUT VARIABLE is verified like a parameter** (one line appended to the KB-first block; PI-directed). The rule that block states is written about parameters and mechanisms, and a tape field is a third category no rule named -- so in one session the identical failure arrived one category over: a single `nanmean` applied to six variables with five different temporal semantics, and an `inactive` field read as gross production while the model's own output-info CDL carried `status = "inactive"`. Canonical rule and the measured cost: `calibration-discipline` item 3c. No `description` change.

- 2026-09-07 (later still): **Reworded to match `phase5-testing`'s loosened boundary (PI).** Saying the design is "fixed before the handoff" was too strong: Phase 5 legitimately adjusts for PRACTICAL reasons during execution — a value not representable at the file's dtype, a dose respaced to avoid two rungs staging the same stored value, a resubmission after an infrastructure failure — and must record what it changed. What comes BACK here is anything that would change what the experiment confirms or refutes: which parameter, which direction, which base, what range, what counts as a pass. Step 3 and the Deliverable line both say so, in the same words `phase5-testing` step 0b uses, so the two cannot drift. **No `description` change.**

- 2026-09-07: **New Step 0 (build the case's mechanism graph, then design from it) and Step 2a (choose the base, for the mechanism under test).** **PI-directed division of labour: Phase 4 owns the SCIENCE, Phase 5 owns EXECUTING it correctly.** The two skills contradicted each other and one of them contradicted itself: `phase4-hypothesis` Step 3's HEADING read "design the experiment -> Phase 5" while its BODY four lines later said the model's run skill "owns variant design", and `phase5-testing` invited the agent to add variants and a second base of its own. Nothing said who decided what, and the ambiguity is not academic: on one round the design was done in Phase 4 (correctly) and the staging machinery then had to be invented in Phase 5 with no rule saying which phase owned which. The base rule is now stated in BOTH skills rather than moved -- Phase 4 as a scientific choice, Phase 5 as a check the executor performs -- with each naming the other and an instruction to change both together. **Step 0** requires the mechanism network to be built for the case's SPECIFIC miss, stated as a direction, and -- the part that gets skipped -- for the design to record WHICH of those mechanisms this round's parameter list can actually reach, because a sensitivity screen cannot rank a mechanism the design has no parameter on. Measured on one site: the round's parameters sat almost entirely on the production input side of a carbon balance, six categories and seven of twenty-one plant-side mechanisms had no sampled parameter at all, and sixteen cycles refuted lever after lever without being able to move the part of the network that mattered; the graph traversal that found it took minutes. Step 0 also records that an unsampled parameter is testable NOW (Phase 5 stages directly, outside the Phase-0 matrix) and that a candidate must be checked for INERTNESS before it is spent on -- on one case the single parameter whose name matched the deficit was an integer selecting a pattern rather than a rate, gated behind a test false for all three of that site's PFTs. **Step 2a** carries the base rule: rank by in-band count with the composite as tie-break, exclude anything below the viability floor, then choose by headroom on the targets THIS hypothesis moves, and say which and why in the log, because Phase 6 reads a refutation as a property of a (parameter, direction, base) triple. **Reconciled in the same pass:** Step 3's body now says the run skill owns variant EXECUTION, and the Deliverable line names the chosen base and its reason. **No `description` change, so when this skill fires is unaffected.**

- 2026-09-06: **"the KB is meant to be sufficient" removed -- it invited exactly the misreading it warns against.** PI-directed, and the signal is a measured misreading in the session that first followed this rule: the agent paraphrased the sentence as "the KB is assumed sufficient", which reads as permission to stop at the KB, and the PI corrected it -- *"KB is not sufficient, they just let you have a quick understanding, you still need to verify in the source code if needed"*. The sentence already said *and only then confirm in source*, so the instruction was right and one clause of it was pulling the other way. **Evidence that both halves are load-bearing, from the same session:** the wiki DID carry the model's respiration temperature functions with their constants and `file:line`, so one grep would have replaced six source reads of LEARNING -- and the finding that mattered was that NO calibratable array appears in either function body, a claim about ABSENCE that no wiki page can settle. The KB would have oriented in seconds and still not answered it. Replaced with "the KB is where you START and it usually hands you the citation; it does NOT replace verifying in source". Applied identically across nine skills. The five-surface requirement, the query order and every `description` are UNCHANGED, so when each skill fires is unaffected.


- 2026-09-05: **KB FIRST, SOURCE TO CONFIRM.** PI-directed, after a session reconstructed the EcoSIM `micresb` slot semantics from Fortran over several turns while `docs/ecosim-knowledge-base/ecosim-codebase-wiki-2dea74d9/microbial_bgc/index.md:133` stated it in one line with the same `MicBGCPars.F90:178-179` citation -- and additionally recorded that the 2-slot NECROMASS axis is not the 3-slot LIVING-biomass axis, a distinction the source read missed and which mattered. Cost: a wrong root-cause diagnosis and two fixes that treated symptoms. The knowledge was in the repo THREE times (the KB, a sibling case's hand-authored parameter list, and the Fortran) and the lowest-level one was reached for. **This is a SEARCH ORDER, not a demotion of source:** source stays ground truth on what the model DOES, and a load-bearing claim still gets a `file:line`; the KB is where you START, because it usually carries that citation already plus context the source does not. `git grep -i <term> -- docs/<model>-knowledge-base/` works with no RAG profile active. Placed at the hypothesis step because a mechanism asserted from a half-understood parameter propagates into the experiment design, its bar, and the compute spent on it. `description` untouched; no trigger change.
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