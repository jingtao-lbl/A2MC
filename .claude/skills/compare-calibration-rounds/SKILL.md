---
name: compare-calibration-rounds
visibility: public
category: calibration
description: Compare A2MC calibration rounds (R1, R2, …) for ANY onboarded model — the CROSS-ROUND PARAMETER LEDGER, i.e. what every round did with each parameter (calibrated, refuted with mechanism, baked into base, never present, bounds still provisional), the CROSS-ROUND MECHANISM LEDGER, i.e. what the CAMPAIGN now knows about the SYSTEM with one row per established mechanism, its evidence and the round that established it, plus best-achievable performance per round against the targets and per-round sensitivity. A REQUIRED step before EVERY round report INCLUDING THE FIRST, where only the cross-round figures are not applicable and the one-column ledger is the baseline later rounds are checked against. Use when the user asks to "compare rounds", "what did earlier rounds do with parameter X", "what have we learned about the system across rounds", "what mechanisms has this campaign established", "why was parameter X refuted", "update the multi-round figure", "refresh the R1-RN comparison", "which round is best", "top sensitive parameters per round", or to regenerate any `multiround_*` / cross-round figure after new cases complete. Codifies the multiround bundle pipeline + the footguns (screening contamination, case-name patterns, μ* ranking, param-set mismatch, partial-ensemble caveats).
modes:
  requires_fates: false      # generic since 2026-08-24; the PARAMETER LEDGER is model-agnostic, the FIGURE backend is per model
  nutrient_pathway: any
  scope: [analysis]
  summary: "Cross-round comparison for any model: the per-parameter per-round ledger (the part every model needs), plus performance and sensitivity overlays whose producing tools are per model. Required before the ROUND report."
---

# Compare Calibration Rounds

Cross-round comparison of A2MC calibration rounds: best-achievable biomass per round vs the
validation targets, and Morris μ* sensitivity per round. The canonical bundle lives under a
site's analysis dir, `use_cases/{Model}_{Case}/analysis/multiround_*/` (self-locating scripts; figures
versioned beside them; the Kougarok reference instance is `multiround_top50_sensitivity_20260606/`).
Read `README.md` there + the originating dev/ana log (findings) and
the originating dev/ana log (procedure) first.

## DELIVERABLE 1 — the CROSS-ROUND PARAMETER LEDGER, and it is the reason this skill is required

**This was missing until 2026-08-24 and its absence is measured.** Until then this skill produced
cross-round *performance figures* only. A round summary was then written that proposed adding two
parameters earlier rounds had already tested and refuted with named mechanisms, and both errors
survived every checker, because **nothing in the round-close path opened a prior round**
(`memory/dev_logs_adapterkit/reflection/20260824a_*`, `20260824b_*`). Figures cannot carry that: an
investigation verdict is not a plot, and a parameter varied on a secondary surface by crossing
appears in no parameter list and no sensitivity bar.

**Build one row per parameter that has EVER been in play, one column per round.** This table is what
the ROUND report's parameter reference table (`write-report`) fills its status column from, and
what the next round's add/remove decision is made against.

```markdown
| Parameter | R1 | R2 | R3 | current status and the evidence |
|---|---|---|---|---|
| GRDM  | corrected, dominant establishment lever | calibrated | DROPPED in prune (norm mu* 0.016) | restore: low mu* was measured against an ALREADY-CORRECTED base |
| PPI   | recommended as a knob | calibrated by CROSSING on the secondary surface, swept 280-400 | frozen at 280 | REFUTED with mechanism (non-monotonic, residence not conserved) — do not re-propose |
| SPOSC | not present | promoted to an input; 6 probes, bit-identical output | absent from the round's tertiary file | EXCLUDED, runtime-verified; adding it is a data change that buys nothing |
```

**Per-cell vocabulary** (use these words; they are what makes the table greppable and the status
column checkable): `calibrated` · `refuted with mechanism` · `confirmed` · `baked into base` ·
`dropped in prune` · `frozen constant` · `never present` · `bounds provisional`.

**Four sources, and you must read all four — a parameter can be in play through any of them:**

1. each round's **parameter list** (`use_cases/{Model}_{Case}/parameters/*_r{NN}.csv`) — the obvious one;
2. each round's **design and config** — a parameter varied by **crossing** or held as a staged
   constant lives on a secondary/tertiary surface and appears in **no** parameter list. **This is the
   source that was missed.** Read the round config wrapper and the crossed/ensemble design spec;
3. each round's **state file** `memory/workflow_state_offline_r{NN}.json` — its `decisions`,
   `round_summary` and `evidence` carry refutations with their mechanisms;
4. the case's **investigation reports** under `reports/` — a parameter can be settled by a dedicated
   investigation that never appears in any round's list at all.

**The `bound_source` column of each round's parameter list is part of this ledger, not a footnote.**
A bound still carrying a `provisional:` seed (or free-text equivalent such as a naive plus-or-minus
50 percent with a deferral note) is a **debt** that must be reported here, because deferring it again
is how a placeholder range survives into an ensemble. One measured case: 15 of 28 rows carried a
deferred plus-or-minus 50 percent envelope, nothing read the field, and four of the six parameters
whose lethal ranges killed 81 percent of that ensemble were among them.

## DELIVERABLE 1b — the MODEL EVOLUTION across the rounds, and the comparability verdict

**Two rounds run on different model commits are not automatically comparable, and until 2026-08-24 nothing said so.** The parameter ledger answers what each round did with each *parameter*; this answers what each round ran as a *model*. Both are required before the round report, for the same reason: a cross-round claim that ignores either one is a claim about two different things.

**Read the case's `config/calibration_rounds.yaml` `model_change_ledger` block** (schema and a worked instance in the EcoSIM BioCON case). It carries one entry per source change with its commit, branch, `kind`, whether it is default-off, what it changes, its V0-at-equality result, whether it is on `fork/main`, and the load-bearing pair **`rounds_before` / `rounds_after`**.

**Where it goes** (PI, 2026-08-24): the **detail** in the case's `memory/model_evolution/{stem}.md` record, and only a **compact table in the round report's appendix**. Engineering provenance does not belong in a science narrative. `summarize-calibration-round` guarantee 6 owns the split; this skill supplies the cross-round content for it.

**Report:**

1. **what each round's binary actually contained** — from `round_binaries`, not from the `ecosim_source` block, which records what a round was *configured* against. Those differ: in the worked case R3's `ecosim_source` names one branch and its binary is three commits further on;
2. **which changes fall between the rounds being compared**, with each one's `kind`;
3. **the comparability verdict, split by what is being compared.** A change can leave VALUES identical and still make COUNTS incomparable. The worked case: dropping underflow from the FP trap list does not alter what a completing case computes, and it does let the later round complete cases the earlier binary would have aborted, so death rates and completion counts across that change are **not** like-for-like while per-case values are;
4. **what no change addresses**, which is as much a finding as what they fix.

**Verify ancestry, never assume it.** A change is in a round's binary when it is an ancestor of the commit that round actually ran:

```bash
git -C $A2MC_MODEL_PATH log --oneline <anchor-tag>..<binary-commit>
git -C $A2MC_MODEL_PATH merge-base --is-ancestor <change-commit> <binary-commit>
```

**If the ledger block does not exist for this case, say so in the report rather than omitting the section**, and note that the comparison is therefore unverified on the model axis. An absent ledger is a finding about the case's provenance, not a licence to skip the question.

**Not the same axis as the RAG milestone.** `rag/milestones.json` registers a model commit for **knowledge-base and RAG selection** (the EcoSIM entry is `ecosim-2dea74d9`). That is a different question from which binary produced an ensemble, and the two commits are routinely different. Do not read one for the other.

## DELIVERABLE 1c — the CROSS-ROUND MECHANISM LEDGER: what the CAMPAIGN now knows about the system

**Deliverable 1 answers what each round did with each PARAMETER. This answers what the campaign has learned about the SYSTEM, and until 2026-09-05 nothing carried it across rounds at all.** The parameter ledger compresses a mechanism to a status token in one cell, `refuted with mechanism` — the word without the mechanism. A reader of the ledger can see that a lever was refuted and cannot see why, which is precisely the knowledge a next round needs in order not to re-derive it.

**One row per established mechanism, not per parameter.** That is the point of a separate ledger: the three shapes below have no row in Deliverable 1 by construction, and they are exactly the findings a campaign most wants to keep.

| Mechanism | What it says, in one sentence | Evidence (`file:line`, artifact, or log) | Established in | Status now |
|---|---|---|---|---|
| Two solutes, one fixed-ratio source, opposite sinks | one mineral releases both at a fixed ratio; the saturated sink tracks the source while the unsaturated one strengthens with it, so the two move in opposite directions | `savannah_river.dat:2649`; the round's first Phase-3 diagnosis | R1 c00 | CONFIRMED, R1 c01 experiment |

Vocabulary for the status column, kept small so it stays checkable: `established` · `confirmed by experiment` · `refuted` · `superseded in round N` · `carried, untested`.

**The three shapes that live only here:**

- **A relation between two parameters.** Deliverable 1 gives each one its own row and one cell for its own behaviour, so the interaction disappears in the split.
- **A variable that is neither sampled nor scored.** It has no row anywhere, so its absence leaves no hole a reader can see. In the measured case it was the master variable of the whole round.
- **The finding that a parameter list was WRONG.** A ledger built from the parameter lists cannot naturally represent what every list omitted.

**Sources, in order.** Each round's `memory/workflow_state_offline_r{NN}.json` — its `evidence.diagnoses[].one_line` and `decisions[]`, which hold findings as they were established rather than after several layers of synthesis — then each round's Phase-3 diagnoses and Phase-6 refinements, then the round reports. **Read the state files first**: they are machine-readable and, being written at the moment of the finding, are the only source that has not been thinned by a summary.

**Carry a superseded mechanism rather than deleting it**, with the round that superseded it. A campaign that silently drops a refuted explanation invites its own re-derivation two rounds later, which is the same failure mode Deliverable 1 exists to prevent for parameters.

## The FIRST round runs this skill too, and the objection that there is nothing to compare is half right

**It is true of Deliverable 2 and false of every other one** (PI, 2026-09-05). A first round has no prior round, so the cross-round figures have nothing to plot and the round report records them as **not applicable rather than omitted** — the distinction matters, because an omitted section reads as an oversight and a not-applicable one reads as a checked box.

**Deliverables 1, 1b and 1c all have content at R1**, and this is the reason the skill is required from the first round rather than from the second:

| deliverable | at a FIRST round |
|---|---|
| 1, parameter ledger | one round column. Every parameter's baseline, range tested, and role, plus any parameter that decided the round while being in no parameter list, plus the `bound_source` debt still outstanding |
| 1b, model evolution | which binary the round ran, with its checksum, and a one-line statement if no source change occurred. The anchor every later comparability verdict is measured from |
| 1c, mechanism ledger | every mechanism the round established, with its evidence and the cycle that established it |
| 2, cross-round figures | **not applicable**, stated as such |

**The one-column ledger is not a degenerate case of the table, it is the baseline the table is built on.** Round 2's comparison reads Round 1's ledger; if Round 1 never wrote one, Round 2 must reconstruct Round 1's parameter history from its logs, which is exactly the reconstruction this skill exists to make unnecessary and exactly where a round summary was measured re-proposing two already-refuted parameters. A first round that skips this step does not save work, it moves the work to the round that can least afford to redo it.

**Write it with a `**Status:** Baseline` header** saying plainly that this round is the first, so a reader does not mistake a one-column table for a broken one.

## DELIVERABLE 2 — performance and sensitivity across rounds (the figures)

The original content of this skill, and the part whose tooling is per model. Resolve the backend
before running anything: `python tools/describe_mode.py`, or read `$A2MC_MODEL`.

| | FATES / ELM (CIME) | EcoSIM, PFLOTRAN, ATS (adapter) |
|---|---|---|
| per-round best-achievable | `phases/phase2_screening/screen_ensemble.py` + `plot_multiround_top50_overlay.py` | the case's own screen (e.g. `screen_params_vs_targets.py`) over each round's scored-target matrix |
| per-round sensitivity | `morris_sensitivity_analysis.py` + `plot_multiround_sensitivity_overlay.py` | whatever each round produced; **say which**, and say so explicitly where a round's estimator was unusable |
| extraction | `tools/extract_monthly_variables_FATES.py` | `scripts/extract_flat_ensemble_targets.py` / `extract_crossed_ensemble_targets.py` |

**Deliverables 1, 1b and 1c are required in every round close. Deliverable 2 is required where the backend
exists**, and where a round produced no usable sensitivity the report says so rather than omitting
the section. A round whose estimator failed is a finding, not a blank.

## When to use

- "Compare the rounds", "which round is best", "update/refresh the multi-round figure".
- "Top sensitive parameters per round" / cross-round sensitivity.
- Regenerating a `multiround_*` figure after new cases complete (e.g. a round's relaunched/added cases).
- P-pool or cross-regime cross-round overlays (same bundle conventions).

## The bundle

```
multiround_top50_sensitivity_20260606/
├── scripts/
│   ├── plot_multiround_top50_overlay.py        # biomass top-50 vs 6 targets (6 panels)
│   ├── plot_multiround_sensitivity_overlay.py  # Morris μ* top params per round (grouped bars)
│   ├── build_Y_from_monthly.py                 # R2..R5 Morris Y matrices from monthly NCs
│   └── build_Y_R1.py                           # R1 (138-param)
├── screening_top50/{R1..RN}/                   # screen_ensemble.py outputs per round
├── sensitivity/{R1..RN}_{leaf,fineroot}/       # morris μ* CSVs + per-round png
├── Y_matrices/                                 # Morris inputs (for sensitivity only)
└── multiround_*.png                            # the comparison figures
```
Also: `tools/compare_rounds.py` for quantitative round-vs-round deltas.

## Pipeline (to refresh a figure after new cases)

1. **Extract** the new cases (all 3 phases if the combined/sensitivity figures are needed):
   production `tools/extract_monthly_variables_FATES.py` (TRANS) or `tools/extract_and_plot_selected_cases.py`
   (`extract`, any phase via `--phase/--year-start/--year-end`, reuses `process_case`).
2. **Re-screen** the round: `phases/phase2_screening/screen_ensemble.py --data-dir <round extract dir>
   --top-n 100 --output-dir screening_top50/<RN>` (source that round's config so
   `A2MC_CASE_NAME_PATTERN` is right). **⚠️ see footgun #1 — filter out-of-range cases first.**
3. **Biomass figure:** `python scripts/plot_multiround_top50_overlay.py` (reads `screening_top50/*/`).
4. **Sensitivity** (only if refreshing μ*): rebuild Y (`build_Y_from_monthly.py`) → Morris
   (`phases/phase1_exploration/morris_sensitivity_analysis.py`) → `plot_multiround_sensitivity_overlay.py`.

## Footguns (the load-bearing part)

| # | Footgun | Guard |
|---|---|---|
| 1 | **CROSS-round screening must cap the case number.** `screen_ensemble.py` matches `PtCNPEn(\d+)<suffix>_TRANS` for any digits, so out-of-Morris-range experiment cases (e.g. H1 clumping #5001/5005/5006) sitting in a shared extract dir get swept in and can rank as "best". (This made the R5 biomass figure briefly show best **#5001** instead of **#1304**, 2026-06-10.) | Pass **`screen_ensemble.py --max-case-num <ensemble max>`** (e.g. `4890`) for cross-round comparison — it drops out-of-range cases and prints how many. Verify `# Sets:` in `_results.txt` = expected. **NOTE:** leave `--max-case-num` UNSET for a single round's own whole-ensemble summary graph — those legitimately exceed the Morris size (e.g. R3 + reruns = 4941). |
| 2 | **Read `_results.txt` Sim_ columns + `screening_result.json` `best_case_num`, NOT `screening_top50_indices.txt`.** The indices file mislabels case numbers on partial ensembles and isn't always rewritten (can be stale). | The overlay scripts already do this; don't "trust" the indices file. |
| 3 | **Morris CSV `rank` column is by `mu`, not `mu_star`.** | Re-sort by `mu_star` (Morris importance) for selecting/ranking top params. |
| 4 | **Sensitivity file prefix is unreliable.** Older runs (R1–R4, 6/6) named *both* organs `morris_leafbiomass_*` (the `--output-var` quirk); newer runs (R5, 6/10) correctly use `morris_finerootbiomass_*` for fineroot. So a dir can hold either prefix. The **directory** `{Rn}_{organ}` is the source of truth for the organ; content is correct per dir. | Map organ by directory, never by filename prefix. Glob `morris_*PFT{X}_2*.csv` (matches both); ensure one file per PFT so `sorted()[-1]` is unambiguous. |
| 5 | **Param-set mismatch across rounds.** R1 used 138 params; R2+ used 162. | Align on shared names; show "no bar"/blank for params absent in a round; note it in the caption. |
| 6 | **Partial-ensemble rounds.** Screening/ranking is valid on a partial ensemble (dead cases get finite high cost), but **Morris μ* is NOT reliable** until the ensemble is reasonably complete. | Include a partial round in the biomass top-N figure (label it), but **exclude it from the sensitivity overlay** until a full Y-rebuild + Morris re-run. |

## Conventions

- **Filenames** embed round + axis-mode + case count: `R{N}_{TRANS,combined}_{count}cases_ensemble.png`,
  `multiround_top50_biomass_vs_6targets_R1-RN.png`, `multiround_top_sensitive_params_bars_R1-RN.png`
  (per `feedback_plot_filename_convention`).
- **Biomass overlay bands:** grey ±20% acceptance band + light-blue ±1 SD observation band (SD often
  exceeds the mean → floor the lower SD edge at 0). SD values from `validation_targets_leafroot.txt`.
- **Whole-ensemble** (not top-N) cross-round plots use `tools/plot_ensemble_cases.py` +
  `regen_ensemble_milestone_plot.sh` (different from this bundle's top-50 overlay).
- NERSC: scratch (symlink dirs, filtered sets) under `$HOME`/repo `tmp/` only — never `/tmp`,`/scratch`.

## Cross-references

- **`calibration-goal`** — the run-to-convergence DRIVER dispatches this skill as part of the round CLOSE. `resolve_next_action()` returns `close("round_close")` when a round ends, and the driver runs the three steps in order: `summarize-calibration-round` -> `compare-calibration-rounds` -> `write-report`. The close happens BEFORE the Phase-6 human gate, so the PI routes the round with these deliverables in hand.

- **`plotting`** — every figure this skill produces goes through it: fonts, units, semantic
  colours, the A2MC ensemble template, and the load-bearing check (open the rendered PNG and
  look at it). Load it before the first `savefig`.
- Worked examples: the originating dev/ana log (procedure), `20260610b` (refresh + H1 catch),
  the originating dev/ana log (findings).
- Tools: `phases/phase2_screening/screen_ensemble.py`, `phases/phase1_exploration/morris_sensitivity_analysis.py`,
  `tools/{compare_rounds,extract_and_plot_selected_cases,plot_ensemble_cases}.py`.

## Changelog

- 2026-09-05 (later, 2): **TRIGGER CHANGE — `description` rewritten.** It advertised the parameter ledger and the performance figures only, so Deliverable 1c existed in the file and nothing routed to it: *"what have we learned about the system across rounds"*, *"what mechanisms has this campaign established"* and *"why was parameter X refuted"* fired no skill. The description now names the CROSS-ROUND MECHANISM LEDGER, states that the skill is required before EVERY round report including the first with only the figures not applicable there, and adds those three phrasings as triggers. **When this skill fires has therefore changed deliberately.** Same pass corrected the same 12-day four-surface drift: every registry still marked this skill **FATES** although it went `requires_fates: false` on 2026-08-24.

- 2026-09-05 (later): **Required from the FIRST round, and a section saying what a first round produces.** PI question: "for the 1st round report there is nothing to compare, right?" Half right, and the half that is wrong is the load-bearing one. Only Deliverable 2, the cross-round figures, is not applicable at R1; Deliverables 1, 1b and 1c all have content, and the one-column ledger a first round writes is the baseline every later round is checked against. Skip it and Round 2 must reconstruct Round 1's parameter history from logs, which is the reconstruction this skill exists to make unnecessary and where a round summary was measured re-proposing two already-refuted parameters. This skill is now the fifth name in `write-report`'s enforced required-skills list, checked as an ERROR for every round report including the first. `description` untouched; no trigger change, and it still does not advertise the mechanism ledger.

- 2026-09-05: **DELIVERABLE 1c, the CROSS-ROUND MECHANISM LEDGER.** PI-directed, from the same audit that added guarantee 8 to `summarize-calibration-round`. Deliverable 1 answers what each round did with each PARAMETER and compresses a mechanism to a status token in one cell, `refuted with mechanism` — the word without the mechanism — so a reader can see that a lever was refuted and not why, which is exactly the knowledge that stops a later round re-deriving it. Nothing carried system knowledge across rounds at all. 1c is one row per established MECHANISM, not per parameter, with its evidence, the round that established it, and a small status vocabulary; it names the three shapes that have no row in Deliverable 1 by construction (a relation between two parameters, a variable neither sampled nor scored, and the finding that a parameter list was wrong), and it orders its sources with the machine-readable one first, each round's `workflow_state_offline_r{NN}.json`. A superseded mechanism is carried with the round that superseded it rather than deleted, for the same reason Deliverable 1 carries refuted parameters. **Reconciled in the same pass:** the required-deliverables sentence named only 1 and 2. `description` deliberately untouched, so no trigger change; it still does not mention the mechanism ledger, which is a known gap left for a PI call.

- 2026-08-24: **Made GENERIC (`requires_fates: true` -> `false`) and given the deliverable it was missing.** PI-directed, from an audit that asked whether invoking this skill at a round close would have surfaced the parameter history a round summary got wrong. It would not have: the skill produced cross-round *performance figures* and nothing else, and it was FATES-only, so for an adapter model it was not runnable at all. Two changes. **(1) DELIVERABLE 1, the cross-round parameter ledger** — one row per parameter ever in play, one column per round, a fixed per-cell vocabulary, and four required sources including the one that was missed: a parameter varied by **crossing** on a secondary surface appears in no parameter list. It also carries `bound_source` debt, because a deferred provisional bound surviving into the next ensemble is the same class of loss. **(2) DELIVERABLE 2** is the original figure pipeline, with its backend split per model and the rule that a round whose sensitivity estimator failed reports that rather than omitting the section. Measured signal: a round summary proposed re-adding two parameters already refuted with named mechanisms, and 15 of 28 bounds carried an unread deferral whose ranges then killed 81 percent of that ensemble. This skill is now a **required step before the ROUND report** (`write-report`). **`description` and `modes` both touched** — it now fires for any model, and on "what did earlier rounds do with parameter X".



- 2026-08-16: **Names the `plotting` skill.** `plotting` listed this skill as one that applies its
  conventions while this one never mentioned it — a one-directional link. The reciprocal pointer
  is now required in both directions. PI-directed.
- 2026-06-17: `## Changelog` convention adopted (see .claude/skills/README.md). Earlier history: git log + memory/dev_logs/.
