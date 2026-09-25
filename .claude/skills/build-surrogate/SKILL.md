---
name: build-surrogate
visibility: public
category: calibration
description: Build, score and hand over a learned surrogate of a process model from a finished calibration ensemble — the S0/S1/S2/S3 tier ladder in `models/surrogate/`, its gated ascent, the hold-out design that decides what the numbers MEAN, and the acceptance and promotion gates. Use when the user says "build a surrogate", "train an emulator", "can we emulate EcoSIM/PFLOTRAN", "fit a surrogate on the ensemble", "speed up the search with a surrogate", "build a KGML emulator", or asks whether a finished ensemble can support one. Covers both use modes — calibration accelerator (`offline_search`) and emulator (`online_inference`) — which gate on different criteria and are not interchangeable.
allowed-tools: [Read, Glob, Grep, Write, Edit, Bash]
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [calibration]
  summary: "Build a learned surrogate from a finished ensemble: tier ladder, split design, acceptance, packaging. Model-agnostic."
---

# build-surrogate — a learned surrogate, from a finished ensemble to a handed-over artifact

A surrogate is a statistical model of **a process model**, fitted to an ensemble that model already produced. It is not an adapter and not a model: it is bound to one `(model version, parameter list, bounds, base parameter file, scoring convention)` tuple, exactly as a RAG profile is bound to a source commit, and it is invalid the moment any of those changes.

**Two things decide whether this work is worth doing, and both are answered before any fitting.** What the surrogate is FOR, and what the ensemble can PROVE about it.

---

## Step 0 — resolve the USE MODE, because the two gate on different things

`use_mode` is a declared field on `SurrogateSpec` and it selects the acceptance battery (`MODE_CRITERIA` in `validate.py`). Choosing wrong does not produce an error; it produces a verdict about the wrong question.

| | `offline_search` — a calibration accelerator | `online_inference` — an emulator |
|---|---|---|
| what it does | ranks candidate parameter sets between rounds so the expensive model runs on fewer of them | replaces the process model in a runtime, consumed step by step rather than reviewed |
| the bar | **ranking**: Spearman rho and top-k recall against distance to the observation. Pointwise $R^2$ is measured and NOT gated | **pointwise accuracy**: daily $R^2 \ge 0.9$, normalised WITHIN each case (step 5). Interval coverage is not gated |
| why that bar | a good $R^2$ with a bad ranking is useless to a search, which only ever asks "which of these is closest" | a prediction nobody reviews must be right, not merely correctly ordered |
| fine-tuning on observations | **forbidden**: ranking candidates against observations with a surrogate trained toward them is circular | legitimate, and it is how KGML converts a model surrogate into a predictive instrument |

**Ranking is on distance to the observation, `|y - observed|`, whenever the target declares one.** A surrogate that predicts high values well and low values badly can have an excellent $R^2$ and rank the candidates a calibration cares about in the wrong order. **A target with no `observed` is ranked on the predicted level**, because there is nothing else to rank it by: that is what `run_acceptance` does and, since 2026-09-22, what `perturbation_stability` does too. The two used to disagree -- stability measured the shortlist by level while acceptance measured it by error -- so the number a human read at review time described a shortlist nothing else used. `acceptance.json` now records `ranked_on` per target, so which rule applied is in the file rather than in this sentence.

---

## Step 1 — THE HOLD-OUT DESIGN IS A PHASE 0 DECISION, AND THIS IS THE STEP THAT GETS SKIPPED

**An independent validation lattice cannot be recovered later by re-splitting.** Every split of one scrambled Sobol' sequence draws train and test from the same point set, so it measures interpolation inside that set however cleverly the split is chosen. The only independent test is one **drawn with a different scramble seed and RUN**, and both are design-time acts.

So when a round is being designed and a surrogate is even possible later, set in the site config:

```bash
export A2MC_SOBOL_SEQ_VALID_SAMPLES=1024        # a power of two
export A2MC_SOBOL_SEQ_VALID_SEED=<NOT the training seed>
export A2MC_VALID_MATRIX_FILE="${A2MC_USE_CASE_DIR}/parameters/<case>_valid_sobolseq1024.txt"
```

`scripts/create_adapter_parameter_sample.py` then draws it, refuses a seed equal to the training seed, asserts no validation point coincides with a training point, and prints plainly when a round is being designed WITHOUT one. Run those cases like any other, then **hold them** until a surrogate exists: holding removes the temptation to look. `scripts/fit_ensemble_surrogate.py --test-matrix` defaults to `A2MC_VALID_MATRIX_FILE`, **and it is used only when `--test-y` is given as well** (`scripts/fit_ensemble_surrogate.py:265`, `if a.test_matrix and a.test_y`). With the X and no Y the run falls back to the weaker random split and says so in `split_kind`, which is the one place to check: a case that designed and RAN a validation lattice can still be scored on a random split if nobody passed its Y.

**When the round was already designed without one**, say so in the acceptance report and quantify the optimism instead of ignoring it. `models/surrogate/splits.py` provides named strategies, each carrying its own `description` and `optimistic_about` into `acceptance.json`:

| split | what it tests | measured on EcoSIM_Lusignan R1b |
|---|---|---|
| `random` | interpolation inside the lattice. The historical default and the weakest | rho 0.582 / 0.584 / 0.491 |
| `block` | sequence position. **Written as a neutral control and measured to be the EASIEST** | rho 0.655 / 0.634 / 0.518 |
| `shell` | distance from the cube centre. Weak in high dimensions, see below | rho 0.582 / 0.597 / 0.436 |
| `axis` | **extrapolation along one named parameter. The honest test in high dimensions** | rho 0.551 / 0.561 / 0.444 |
| `levels` | whole values of a label withheld: years, sites, treatments | see step 5 |

**Two findings that reverse an intuition, both measured rather than argued.** A tail block of a Sobol' sequence is the easiest hold-out available, not a neutral control, because each new point of the sequence fills a gap between earlier ones, so the last 20% is the subset most thoroughly surrounded by the first 80%. And an "outer shell" defined by the Chebyshev radius is meaningless past a few dimensions: in 54 dimensions essentially every point has a coordinate near an edge, so that radius is ~0.5 for the entire ensemble (measured: min 0.44, sd < 0.02) and the split silently degenerates to random while READING as an extrapolation test. `shell_split` uses the mean absolute deviation for that reason; prefer `axis` when the question is extrapolation.

```bash
python scripts/fit_ensemble_surrogate.py --y-matrix <Y.csv> --learner rf --seed <seed> \
    --split axis --split-axis <PARAM> --split-side upper --out <dir>
```

> **It exits NON-ZERO when acceptance fails**, which is the normal outcome early on. Chain follow-up commands with `;`, not `&&`, or the copy you wanted is skipped for exactly the runs worth recording.

---

## Step 2 — check the ensemble can support a surrogate at all

```bash
python scripts/check_surrogate_gate.py --y-matrix <Y.csv>
```

This is about the ENSEMBLE, not the fit: a surrogate that ranks beautifully inside a region that does not contain the answer is useless. The gate asks whether enough cases sit inside the observational bands to be worth ranking.

**A closed gate bounds what a fit may be QUOTED AS; it does not forbid the fit.** A learner-family comparison, a sensitivity model or a constraint model is still legitimate and still informative on an ensemble whose gate is shut. What is not licensed is calling the result a calibration accelerator. Say which of the two a fit is, in the artifact and in the report, because the numbers look identical either way.

**Then check the ranking is stable in ensemble SIZE before believing it.** A comparison run on a subset ranks families at that subset and the order need not survive: measured across five training-set sizes on one ensemble, three distinct orderings appeared and the leader at a third of the data lost at full data (`20260923d_*`). Sweep the size before concluding from a ranking.

**A learning curve whose fits are stopped by their BUDGET confounds the two things it appears to separate**, because more data at a fixed budget of passes is also more parameter updates. Converge the fits, or state the confound and stop there: the stronger reading of such a curve, that the ensemble rather than the construction is the binding constraint, was withdrawn on one case for exactly this reason once converging a fit at FIXED data was measured to buy the same order of gain as the final increment of data (`20260924zc_*`).

---

## Step 3 — climb the tier ladder, and DO NOT SKIP A RUNG

`VALID_TIERS` is the roadmap; `IMPLEMENTED_TIERS` is the registry. **A tier may not be built until the tier below has a WRITTEN acceptance failure on this ensemble.** The tuple grows by recording a failure, never by wanting a feature.

**The two tuples are identical today (`S0, S1, S2, S3`), so the construction-time refusal is DORMANT** -- there is no tier to ask for that is not built, and the branch cannot fire in normal use. The rung rule is therefore carried by this convention and by review, not by the code, which is worth knowing before leaning on it. `tests/test_surrogate_low_severity_fixes.py` patches the registry to prove the branch still fires when a roadmap tier outruns the implementation, so the mechanism is alive even while the condition is empty.

**And the rung has been skipped in practice, which is what a dormant refusal costs.** One case reached the sequence tier with no S0 or S1 fit and no acceptance battery ever run on its ensemble, across six protocols and four logs, and neither the code nor review caught it (`20260923j_*`). It was run afterwards and returned the tier-level failure the ladder asks for, so the ascent was justified in the end and had simply never been demonstrated (`20260925j_*`). If you find yourself above S0 with no written failure beneath, run the missing rung rather than justify the tier you are on: it is also the tier that serves `offline_search`, so the gap usually hides an unevaluated USE MODE as well. **Budget it properly rather than assuming it is quick** -- a scalar tier is cheap in every family except the Gaussian process, whose cost is cubic in the training points, and one S0 comparison across six families took about a hundred minutes with the GP dominating.

| tier | what it emulates | build it when |
|---|---|---|
| **S0** | `theta -> scalar`, viable cases only | always the first fit |
| **S1** | S0 plus a viability classifier and split-conformal intervals | S0 cannot say which cases die, or gives no uncertainty |
| **S2** | `theta -> y(t)`, a latent ROM, reduced to the scalar S1 predicts | the scalar tier fails and the failure looks like a missing time dimension |
| **S3** | S2 plus knowledge: structural composition, admissibility clamps, or a physics loss | S2 fails, or the predictions are inadmissible |

**Two architectures live at S3 and they are not a fourth tier.** `S3Surrogate` is a latent ROM with composed targets. `KGMLEmulator` (`sequence.py`) is the sequence, driver-conditioned form: a trunk with per-flux branches, after Liu et al. (2024). **Its encoder is a choice, not a GRU:** `cell="gru" | "lstm" | "transformer" | "tcn"`, the last two causal by construction (a triangular attention mask, left-only padding) and tested as such; an optional `spatial_graph=[...]` adds masked attention across the target axis. **The conditioning is the difference that matters.** A ROM's basis is tied to the window it was fitted on, so it learns one run; feeding the daily drivers at every timestep lets the network answer about weather it never saw, at least in principle (step 5 is how you find out whether it actually does).

**Keep the learner axis orthogonal to the tier axis.** `ridge`, `rf`, `gbm`, `xgb`, `gp` and `mlp` all work at every ROM tier because the tier decides WHAT is emulated and the learner decides HOW. A failure that reproduces across every AVAILABLE learner family is a **tier-level** failure and is the written failure that unlocks the next rung; a failure on one family is a bad default. First recorded instance: on one ensemble all six families failed ranking fidelity while interval coverage and manifold respect passed, at a bootstrap pass rate of 0.0 over 200 resamples (`20260925j_*`).

**Read the roster a comparison actually fitted from the RUN, never from the registry.** Availability is one way the set shrinks -- `xgb` needs the optional `xgboost` package and raises only when `fit` is called -- and the quieter way is the CALL: a comparison routine carries its own default, so a driver that passes no roster quantifies the rule over fewer families than are registered, with nothing raised and a complete-looking table produced. Declare it with `--bakeoff-learners` (default `all`, or an explicit comma-separated list; it refuses an unknown family by name), and read what a verdict covers from the run's own `bakeoff.json` (`requested_learners` / `fitted_learners` / `failed_learners`) (`20260925b_*`).

**The tier says WHAT is emulated; the ARCHITECTURE says in what SHAPE the answer comes out.** Six families landed in v2.433 and this skill did not name any of them, which is how a build ends up re-deriving a scalar tier for an output that is a field. Pick by the OUTPUT, not by novelty:

| the output is | family | class |
|---|---|---|
| a scalar per target | the ROM tiers above | `S0Surrogate` … `S3Surrogate` |
| several correlated scalars at once | multi-output | `MultiOutputGPLearner`, `MultiOutputMLPLearner`, `VectorSurrogate` |
| a trajectory in time | sequence | `KGMLEmulator` (`cell=` gru / lstm / transformer / tcn) |
| a field over a fixed grid | field | `FieldEmulator` (cnn / unet / fno) |
| a field that also evolves | space-time | `SpatioTemporalEmulator` (convlstm / fno) |
| values on an irregular network | graph | `GraphEmulator` (gcn / gat, static or temporal) |
| a solution operator, resolution-free | operator | `DeepONetEmulator` |

**Most of this table will not apply to a given case, and the reason is the SHAPE OF THE SCORED OUTPUT rather than any property of the methods.** Scored concentrations at a single outflow point offer no grid for a field emulator and no node network for a graph one. Record the position of every family for the case -- applies, measured, result -- because a family ruled out by data shape is an answer, and an unrecorded one reads as untried work that somebody will later propose.

**The SEQUENCE family has now been fitted to a real ensemble** -- all four cells and the `spatial_graph` variant, beside the S2 ROM, on one ~4,000-case ensemble across six protocols (`memory/dev_logs_adapterkit/20260923a_*`, `20260923d_*`). **The other five have not**, and only the scalar reduction of any family goes through the acceptance battery, so treat those five as capability rather than result: the first real fit of one is a Step 5 question, not a Step 3 one. The GP learner is worth one warning of its own — its ARD length scales start at $\sqrt{d}$ since 2026-09-22 because a unit start does not fit above about 44 inputs at all, and it now warns when the optimiser fails to move them.

---

## Step 4 — the traps that cost a wrong answer, in the order they bite

**Reduce-and-check, never reduce-and-trust.** An S2/S3 fit must assert that reducing its training trajectories reproduces the independently-produced Y matrix (`models/surrogate/tiers.py` does this to 1e-4 RELATIVE, per target, against a floor taken from that target's own magnitude). Until 2026-09-22 the denominator was `max(1, |ref|)`, which made the check absolute for anything below unit magnitude: at miniLEO's ~4.7e-4 mol/L a reducer could disagree by 20 percent and pass. A mismatched reducer yields a surrogate that is internally consistent, plausible, and answering a different question than the calibration is scored on. Nothing downstream can see it.

**Verify a conservation law in the model's OUTPUT before building a loss on it.** EcoSIM's `GPP - RA - RH - NEE` closes only to 0.0384 relative, not to machine precision. KGML's published `tol_MB = 0.01` belongs to ecosys, and importing it would have penalised the model for its own behaviour from the first epoch. `mass_balance_tol` therefore has **no default**: measure the closure on the training data and pass it.

**A relative hinge's DENOMINATOR matters more than its tolerance.** Measured: `|GPP|` gives a p99 relative residual of 74,748 against 0.91 for `|RA + RH|`, because GPP reaches exactly zero in winter while respiration floors at 0.0015. That is why KGML divides by the respiration terms, and the reason is stated nowhere in the paper or the library. `mass_balance_scale` is a required argument so the denominator is a declared choice.

**Know which tape variables are cumulative.** EcoSIM's tape mixes within-year cumulatives that reset on 1 January with instantaneous fluxes (`ECO_NEE_CO2_col`, in umol C m-2 s-1). De-cumulating a flux differences noise; failing to de-cumulate a cumulative gives a monotone ramp. And EcoSIM uses a **real Gregorian calendar**, so a fixed 365-day stride drifts one day per leap year.

**A parameter held numerically fixed is not held CONSTANT if the swept axis changes its meaning.** Before a sweep, check every fixed parameter for dependence on the axis being varied. Three instances in one session, each producing a wrong verdict first: layer count across cell types (stacked state for a recurrent cell, receptive field for a convolutional one), patience-in-epochs across training-set sizes (an epoch is more gradient steps when there are more cases), and epoch budget across window lengths (fewer windows per epoch). The first wrote off an architecture for a parameter that was never its own (`20260923a_*`, `20260923j_*`).

**A comparison may only rank fits that CONVERGED.** A fit whose best epoch is at or one before its last was ended by its BUDGET rather than by its data, and a budget does not penalise constructions equally: measured, converging a six-construction comparison reversed its ordering, the arm that gained most rising from two species over the bar to eight while the previous leader gained least. The stopping record is written into every saved fit, so read it before ranking rather than after publishing. A construction with no epochs at all, a ROM, is the control that isolates the budget, since it scores identically under both (`20260924zc_*`).

**Drop constant driver columns.** A column that is identically zero is silent dead weight in a network's input. `scripts/extract_ecosim_forcing.py` detects and drops them, which is how `LWRAD` was caught.

**A reloaded artifact must predict identically.** cuDNN's GRU and the CPU kernel do not agree bit for bit (measured 3.8e-4, far above float32 noise), so a loader that rebuilds on CPU what `fit` trained on CUDA silently returns different numbers. Round-trip through `save`/`load` and assert equality.

**Knowledge guidance buys ADMISSIBILITY, not accuracy.** Measured three times across two channels and two architectures: structural composition made an identity exact and moved ranking by nothing; an admissibility clamp removed 10.3% negative ET and moved ranking by nothing; a mass-balance hinge cut the budget violation eightfold and moved daily $R^2$ by at most 0.012. Expect this, state it, and do not sell it as an accuracy result.

---

## Step 5 — score it, and score the RIGHT THING

```bash
python scripts/fit_ensemble_surrogate.py --y-matrix <Y.csv> --learner <fam> --out <dir>   # writes acceptance.json
```

**NORMALISE WITHIN THE CASE, not across the ensemble.** An $R^2$ pooled over every case and timestep divides by the BETWEEN-CASE variance, which a parameter sweep makes large; predicting each case's level captures nearly all of it while the trajectory stays free. Score within each case against its own mean, and report the median and the share of cases clearing the bar. Measured: a pooled 10-of-10 pass became 7 of 10 within cases, 53% of trajectories, and 0 of 10 once a forcing replay was withheld, every median negative (`use_cases/PFLOTRAN_miniLEO/reports/20260915a_LSTM_Emulator_Methodology/`).

**For an `online_inference` artifact the case hold-out is not sufficient and can be badly misleading.** With every forcing year present in training, the network sees each day of the record once per training case and can approach a lookup keyed on position in the record, modulated by theta. A hold-out over CASES cannot penalise that, because the held-out cases are scored on exactly the days it memorised.

**So withhold whole years and predict them** (`levels_split`), keeping the case split byte-identical so the only variable is the years:

```python
from models.surrogate.splits import levels_split
ysplit = levels_split(years, [2015, 2016])          # terminal: training day axis stays contiguous
```

Measured on EcoSIM_Lusignan R1b, this reversed the headline: **three of five fluxes met the 0.9 bar on held-out cases and ZERO of five met it on withheld years** (GPP 0.889 to 0.494, NEE 0.851 to 0.232). Two details worth copying. Withholding **terminal** years keeps the training day axis contiguous so no training sequence straddles a gap; withholding **interior** years asks the easier between-year question but leaves seams, which makes that set slightly harder and its numbers a floor. And a **hierarchically wired** target degrades furthest off-distribution, because it consumes its parents' predictions and their errors compound rather than average.

**SELECTING the checkpoint is a separate act from SCORING it, and the default selects on the wrong question.** The torch-backed classes keep the weights at the best VALIDATION epoch, where validation is a split over CASES scored on the TRAINING steps -- interpolation under conditions already seen. For an extrapolation use that criterion can be ANTI-CORRELATED with the capability, and nothing in the artifact, the report or the history shows it: varying only the epoch budget on one sequence emulator, validation improved 3.4x while the withheld-forcing score degraded 2.9x, and the fit returned its best-validation epoch, 196 of 200 (`20260923j_*`). So select on a hold-out of the CONDITIONS, and treat a case-split validation curve as a training diagnostic rather than as model selection.

**Assert the baseline rather than trusting it.** When comparing against an earlier fit, re-derive the shared split and assert it against the earlier run's saved case list, and assert the baseline's actuals match on the compared days. Either mismatch must abort: a silently incomparable baseline is the failure mode of any before-and-after measurement.

---

## Step 6 — promote, then package. In that order

**Before either: is the acceptance report still the BINDING verdict?** A promotion is bound to its report by content hash, so a RE-FIT invalidates an approval. Nothing models the opposite and more common case: the artifact and its report are unchanged and still accurate about what they measured, while a **later, harder test** has moved what the artifact should be believed to do. There is no `superseded_by` field and no checker, so this check is manual, and it gates promotion as much as packaging. A bundle shipping a superseded verdict is the failure, and the caption travelling with the figure is where a reviewer will actually see it (`20260913e_The_Surrogate_Gap_Register.md`, G7).

**`AcceptanceReport.passed` is necessary and not sufficient**, for three reasons no threshold can see: the metrics test skill and not relevance; physical plausibility is a judgement; and the split may be optimistic and still pass.

```bash
python tools/promote_surrogate.py review  <dir>
python tools/promote_surrogate.py promote <dir> --basis "<what you checked BEYOND the metrics>" --reviewed-by NAME
```

`--basis` is required and a promotion with no stated basis is a rubber stamp. The approval is bound to the acceptance report by content hash, so re-fitting invalidates it rather than silently inheriting it.

```bash
python tools/package_surrogate.py <dir> --out <bundle> --tar \
    --report <use_cases/<Case>/reports/<stem>/> \
    --figure <the phase_results figure a reviewer needs>.png
cd <bundle> && python load_surrogate.py            # verify it loads
```

The bundle carries the artifact, a copy of `models/surrogate/*.py`, a loader and a manifest, and loads with A2MC absent. It refuses an unpromoted artifact unless `--allow-unpromoted`, which stamps the README so a recipient cannot mistake a review copy for an approved one.

**Ship the REPORT, not just the figures.** A bundle whose purpose is review that shows the reviewer nothing is asking them to audit a number they cannot see, and a figure without the document is the number without the argument. `--report` takes the report directory, copies its `.md`/`.pdf`/`.docx` and figures into `report/`, skips the build machinery and names what it skipped, and leads the generated README with it. `--figure` is for loose review figures into `figures/`; it is repeatable, resolves against the CWD (a figure's canonical home is its phase stem, not the artifact directory), and copies the caption beside it when there is an unambiguous one. The two overlap deliberately.

**Anything added to a bundle AFTER packaging is not in the manifest**, which is built from what the packager wrote — so `sha256sum -c` reports success without checking it, and the gap is invisible from inside the bundle. Measured on a shipped bundle whose report was copied in by hand: 19 entries verifying clean while 6 of its 25 files went unchecked. Use `--report` / `--figure` / `--include` at package time, or regenerate the manifest over the whole bundle afterwards.

---

## Guardrails

- **Never skip a rung of the ladder.** A tier without a written failure beneath it is a feature request wearing a tier number.
- **Convergent evidence is not confirmation.** Two derivations that agree may be two readings of one observation. Agreement raises the PRIORITY of the direct test, never the confidence that the test is unnecessary: a hypothesis promoted on convergence from two directions was refuted by the first experiment that tested it (`20260923h_*`).
- **Never re-split your way to an independent test.** If the round was designed without a validation lattice, say so; do not imply otherwise by choosing a fancier split.
- **Never hand-type `split_kind`.** Use a splitter and let it describe itself, or the string drifts from what the code did.
- **Never quote a case hold-out, or a pooled $R^2$, as evidence for an emulator.** The first measures the parameter response: withhold the conditions. The second measures the population of trajectories: normalise within the case. The two are independent, and the pooled score survives a correct hold-out.
- **Never promote and package in one motion without checking the acceptance report is still BINDING.** Reading it is not enough: a report can be entirely accurate about what it measured and still overtaken by a later, harder test. The gate is the human, not the tool.
- **An artifact bound to a superseded scoring convention is invalid**, even though it loads, has the right shape and predicts plausible numbers. `Provenance` exists for this; fill it in.
- **Check the bundle survives its DESTINATION, not just its own manifest.** A bundle's checkpoint is a binary and destination repos routinely ignore `*.pt`. After copying one in, run `git check-ignore -v <bundle>/artifact/*.pt` **there**: if it is ignored the bundle commits incomplete, the loader fails from a fresh clone, and the manifest keeps verifying for whoever did the copy, so nothing local shows it. An exception keyed on a path is also revoked by renaming the bundle — rename it and fix that line in the same commit.
- **Run the packager on a REAL artifact early, not at hand-over time.** A fixture has no history, no caption conventions and no superseded verdict, so a green fixture suite has tested the tool for correctness and not for fitness. Measured: the first real run produced two bugs and exposed three gaps that twelve passing tests could not see (`20260913f_The_Packager_Meets_A_Real_Artifact.md`).

## Cross-references

- **Reciprocal skills** — `plotting` (every figure here follows it), `phase0-design` (where step 1's validation design is decided), `phase1-exploration` (produces the Y matrix a surrogate trains on).
- `models/surrogate/README.md` — the module's own tier and architecture reference.
- `tools/promote_surrogate.py`, `tools/package_surrogate.py`, `scripts/fit_ensemble_surrogate.py`, `scripts/check_surrogate_gate.py` — the backing commands.
- Worked example, four tiers and their failures: `use_cases/EcoSIM_Lusignan/memory/logs/20260912{a,b,c,d}_*.md`, and the withheld-year test in `20260913b_*`.
- The procedure this was distilled from: `memory/dev_logs_adapterkit/20260913a_The_Surrogate_Building_Procedure.md`, with the gap closures in `20260913c_*`.
- **The open gaps this workflow still has**, with evidence and what would close each: `memory/dev_logs_adapterkit/20260913e_The_Surrogate_Gap_Register.md`. Read it before trusting a verdict or handing a bundle over.

## Notes

- **Branch fit:** `models/surrogate/` exists only on `adapter-kit`; this skill has no meaning on `main` until that module is adopted there.

