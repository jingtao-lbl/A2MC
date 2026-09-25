# `models/surrogate/` — learned emulators

**This is not a model adapter.** It lives under `models/` because it is a model *of* a model, but it does **not** implement `ModelBackend`, and it must **not** be registered in `models/registry.py`. Registering it would let the calibration loop mistake an emulator for a simulator, which is the one confusion this whole design exists to prevent.

Design and rationale: `docs/41_Surrogate_Module_Design_And_Implementation_Plan.md`.

## The one rule

> **The surrogate makes the SEARCH global. The physics model keeps the VERDICT.**

Every configuration a surrogate proposes is confirmed on the physics model before it enters a round record, a report, or curated knowledge. A surrogate result is unverified by construction, so it is not eligible for curated knowledge, which admits a finding only after a verified test on the physics model.

## Why it is not a `ModelBackend`

The backend interface's narrowest waist is a **time series per history variable**:

```
case_path --extract_history_variables--> {var: (time, group) array}
          --reduce_target--> simulated{target: scalar}
          --compute_snapshot_cost--> (total_cost, per_target_errors)
```

An S0/S1 surrogate predicts the **reduced scalar**. To impersonate a backend it would have to fabricate a trajectory that reduces to that scalar, and for a `max` or `peak` reduction infinitely many trajectories qualify, so the fabricated one is invented data entering a real evaluator. It would also force trajectory emulation (S2) to serve a job S1 already does.

**Adopted instead:** a surrogate predicts the same `simulated: Dict[str, float]` that `tools/model_evaluate_case.py::evaluate_model_case` returns, and that mapping is fed to the **existing, unmodified** `tools/cost_functions.py::compute_snapshot_cost`. Physics and surrogate are therefore scored by literally the same function.

The physics backend is still needed, but only at training time to assemble `Y` from completed cases. It is not in the prediction path.

## Tier, learner, and architecture

Three choices, made separately:

- **Tier** = *what* is emulated, and how much knowledge it carries. Scalar (S0/S1) vs trajectory (S2) vs knowledge-guided (S3).
- **Learner** = *with what model family* a tier class regresses. `S0Surrogate`, `S1Surrogate`, `S2Surrogate` and `S3Surrogate` each accept any registry family, and tier and learner are independent.
- **Architecture** = the network a structured output needs, chosen by the SHAPE of the output: a jointly fitted vector, a driver-conditioned series, a gridded field, values on a network of nodes, an output field driven by an input function. Those classes fix their network with `arch=` or `cell=` rather than taking `learner=`; see [Architectures by output type](#architectures-by-output-type).

### S1 makes two picks, not one

S1 asks two questions of every parameter set, and **both** are the caller's choice:

```
   parameter set θ
        ├──► "will it survive?"        → classifier= → alive / dead
        └──► "if so, what comes out?"  → learner=    → target values
                                         (trained on the survivors only)
```

Same algorithm families appear in both lists because most families have a regressor *and* a classifier form — `RandomForestRegressor` and `RandomForestClassifier` are one algorithm pointed at two kinds of question.

| Family | Regressor (`learner=`) | Classifier (`classifier=`) | Inductive bias | Native σ |
|---|---|---|---|---|
| Linear model | `ridge` | `logistic` | linear — **the complexity baseline** | yes (leverage) |
| Random Forest | `rf` | `rf` | axis-aligned splits — **represents a cliff** | yes (inter-tree spread) |
| Gradient Boosting Machine | `gbm` | `gbm` | axis-aligned, boosted | no |
| XGBoost | `xgb` | — | axis-aligned, boosted; optional `xgboost` package | no |
| Gaussian Process | `gp` | `gp` | ARD Matérn-5/2 + white noise | yes (analytic) |
| Multi-Layer Perceptron | `mlp` | `mlp` | smooth, torch deep ensemble | yes (ensemble disagreement) |

Notes on the entries:

- **`ridge`/`logistic` are one family in its two forms.** Logistic regression is a *classifier* despite the name — it predicts class probability, not a continuous value — so the regression counterpart is ridge, not a "logistic regressor".
- **Ridge rather than OLS or Lasso.** `RidgeCV` contains OLS as its α→0 limit, so it costs nothing when OLS would have sufficed and stays stable when it wouldn't; a baseline that fails for a boring reason (blown-up coefficients under correlated inputs) is worse than no baseline, because a strawman makes the flexible families look good for the wrong reason. Lasso is a different tool: it does variable *selection*, and under correlation it arbitrarily keeps one of a correlated group, producing a false sensitivity story.
- **Always put `ridge` in the bake-off.** It is the only thing that answers *"are the flexible families earning their complexity?"* If it matches them on ranking, they aren't.
- **Matérn-5/2 rather than RBF** is deliberate — RBF's smoothness prior is exactly wrong for knife-edge structure. The GP is `O(n³)`, so it subsamples above `max_points` and says so.
- **`logistic` earns its place on calibration.** When failures are the minority, tree classifiers are over-confident and step-like, and here the *probability itself* is used (it gates NROY and the search), not just the yes/no.
- **`mlp` is the only family that accepts a custom loss**, in either role. That makes it the PGNN entry point (`KnowledgeGuidedLoss`, below).
- **`xgb` is optional.** `gbm` is the same algorithmic family and needs nothing beyond scikit-learn, so it stays the default boosted learner; `xgb` is for a caller who wants XGBoost specifically (its regularisation terms, GPU training, or parity with a published XGBoost surrogate). `xgboost` is imported at `fit`, so a missing package fails there with the install instruction.

Any object with `fit`/`predict_proba`/`classes_` works as a classifier, so neither list is a limit. To fit several targets with ONE joint learner rather than one learner per target, use `VectorSurrogate` with `mlp_multi` or `gp_multi` ([Architectures by output type](#architectures-by-output-type)).

**Pick on evidence, not taste.** `validate.compare_learners()` fits every combination on the same split, scores them through the identical acceptance battery, and ranks them for the use named by `rank_for` (`screen`, `search`, `sensitivity`, `rule_out`, `balanced`), because which family wins depends on the use. The default `learners` are `rf`, `gbm`, `gp` and `mlp`, so `ridge` and `xgb` enter only when named. `bakeoff_summary()` prints the table with a `cliff` column (classifier accuracy *near* the boundary, not overall). Pass `classifiers=(...)` to cross both axes; failures are recorded with their error rather than silently dropped.

**Don't want to choose?** `recommend(goal, n_train=, structure=)` returns ranked options *with reasons* for five goals — `screen`, `sensitivity`, `rule_out`, `search`, `physics_constrained` — adjusting for dataset size and known response structure, and ending by saying the priors are not the last word. Two hard constraints are enforced: `rule_out` bars `gbm` (no native σ means one constant interval width), and `physics_constrained` admits only `mlp`. `xgb` has no native σ either and is not suggested for any goal.

### Knowledge-guided loss (the PGNN hook)

`KnowledgeGuidedLoss` adds soft penalties to the MLP's data loss — the "physics-guided loss" family of Willard et al. (2022), and the mechanism Liu et al. (2024) used for KGML-ag-Carbon:

- `monotone={input_index: ±1}` — required sign of ∂output/∂input, enforced on the autograd gradient
- `bounds=(lo, hi)` — admissible output range
- `weight` — the `α_phys` multiplier

Two caveats carried straight from the literature: **soft physics is not guaranteed physics** (prefer a structural `TargetSpec.transform` where one exists, since it holds under *any* weights), and a penalty regularises toward whatever you impose, so an incorrect monotonicity produces a confidently wrong model. Every entry should trace to a verified source-level mechanism.

This is **not** a PINN, and deliberately so: a classical PINN is not the right tool for emulating an existing model from a large library of paired simulations. `docs/41` §4.2 records a PINN's scope and entry condition.

## Tiers

Ascent is **gated**: a tier may not be built until the tier below has *failed a written acceptance test*.
**The gate is enforced, not only stated**: `spec.py` keeps two tuples — `VALID_TIERS` is the roadmap, `IMPLEMENTED_TIERS` is the registry — and a spec declaring an unimplemented tier is refused at construction with an error naming what would unblock it. All four tiers are implemented.

**These S-labels are TIERS, and are unrelated to the S0-S6 STAGE labels in `docs/42`** (the Bayesian-optimization plan). They share the letters and nothing else. Acquisition, deciding where to spend the next run, is search rather than emulation, so it belongs to `tools/bayesian_optimization/` and not to this package. Inside `models/surrogate/`, `S2` always means the trajectory tier.

| Tier | What it emulates | Produces | Use for |
|---|---|---|---|
| **S0** | `θ → scalar` per target | point estimate | ranking, screening, sensitivity structure |
| **S1** | viability, then `θ → scalar` | point + conformal interval + viability + hull gate | everything S0 does, plus anything requiring honest uncertainty |
| **S2** | `θ → y(t)` per target, reduced to the S1 scalar | trajectory + point + conformal interval + viability + hull gate | seasonal shape, phase diagnosis, anything a scalar cannot express |
| **S3** | S2 + process structure | trajectory with composed targets and enforced admissibility | structural admissibility, a derived target that cannot contradict its own components |


### S2 — the trajectory tier

`S2Surrogate` emulates `θ → y(t)`, one series per target, and **reduces the predicted series to the
scalar S1 predicts**. `predict_batch` therefore returns the same `BatchPrediction` every existing
consumer expects, and the series is available separately:

```python
m = S2Surrogate(spec, learner="gbm", n_components=24,
                reduce="annual_mean_sum", time_index=years)   # years: the year label per timestep
m.fit(X, Y, viable=viable, trajectories=T)                    # T is (N, n_targets, n_steps)

m.predict_batch(X).values     # (N, T) scalars — drop-in for S0/S1
m.predict_trajectories(X)     # (N, T, D) series — the tier's reason for existing
```

**Architecture: latent ROM.** Per target, the centred training trajectories are decomposed by SVD, the leading `n_components` singular vectors are kept as a basis, and `θ → coefficient` is regressed with one learner per component drawn from the same registry S0 and S1 use. The learner axis stays orthogonal to the tier axis, so every registry family works here. A trajectory conditioned on per-step drivers needs a sequence network instead: `KGMLEmulator`, an S3 architecture described below.

**`trajectories` is required.** A trajectory tier fitted on scalars alone is an S1 with extra steps,
and `fit` refuses it.

**`Y` is a CHECK, not a second training signal.** `fit` asserts that reducing the supplied
trajectories reproduces the Y matrix to 1e-4 relative and refuses otherwise. **Relative to the column's own magnitude** (v2.436): the denominator used to be `max(1, |ref|)`, which makes the check relative only for quantities of order 1 or larger and an ABSOLUTE 1e-4 for everything smaller -- so on concentrations around 4.7e-4 mol/L a reducer could disagree by 20 percent and pass. A reducer that does not
match the one the Y matrix was built with yields a surrogate that is internally consistent and
answers a different question than the calibration is scored on, which nothing downstream can detect.

**Reducers** live in `tiers.REDUCERS`: `mean`, `sum`, `final`, `max`, `annual_mean_sum`. The last
needs `time_index` (the year label of every timestep) and is the per-step form of a year-end value:
a within-year cumulative series, differenced into per-step values, sums within each year to that
year's end-of-year value. A reducer is **not** on `TargetSpec`, which carries only the reduced value's
identity; the module's contract is that reduction happens upstream, and S2 is the one tier that must
undo and redo it.

**Intervals are on the reduced scalar**, because that is the quantity a caller acts on. A band over
a multi-thousand-step series is a different object and is not claimed.


### S3 — the knowledge-guided tier

`S3Surrogate` subclasses S2 and adds process structure. It uses KGML's **wiring** channel rather
than its loss channel, and that choice follows this package's own doctrine: `KnowledgeGuidedLoss`
says *"where a constraint can instead be made STRUCTURAL, prefer [it] ... which holds under any
weights."* A penalty makes a relation likely; composition makes it true at every point, for every
learner, including the tree families that have no gradient for a penalty to use.

```python
m = S3Surrogate(spec, learner="gbm", n_components=24,
                reduce="annual_mean_sum", time_index=years,
                compose={"total": ["part_a", "part_b"]},  # derived, never fitted
                nonneg=["part_a", "part_b", "total"])
m.fit(X, Y, viable=viable, trajectories=T)
```

**`compose`** — the derived target is not regressed. Its trajectory is the sum of its components'
trajectories at every timestep, so the identity survives reduction. Components must themselves be
targets (so they are fitted and scored), and chained composition is refused because the fit order
would be ambiguous. **A wrong rule is refused at fit**: the training trajectories are checked
against the stated identity before anything is learned.

**`nonneg`** — declared targets are clamped at zero, components before the sum so a negative
component cannot hide inside a positive total. **Violations are counted**, not silently repaired,
and kept on the model as `nonneg_violation_rate`: a constraint that quietly fixes predictions hides
how often the unconstrained model was inadmissible.

**What S3 does not claim.** It is not a PINN and adds no PDE residual, which needs a governing
equation that many process models do not have. It does not pretrain-then-finetune: the training set is already
process-model output, so KGML's "physics as data" arm is satisfied by construction. The soft-penalty
arm remains available on the `mlp` learner through `KnowledgeGuidedLoss` and is orthogonal to this
tier.

**What to expect from it.** Composition makes the declared identity hold exactly, and clamping removes inadmissible values: both act on **admissibility**, by construction. Neither is a mechanism for better ranking or pointwise accuracy, so before crediting either with an accuracy change, compare against an S2 that differs only in the structure.


### The two S3 architectures, and which to reach for

S3 has two implementations. They emulate the same thing and are conditioned on different inputs,
which is what decides when each is usable.

| | `tiers.S3Surrogate` | `sequence.KGMLEmulator` |
|---|---|---|
| conditioned on | theta | theta **and the per-step drivers** |
| trajectory from | latent ROM (SVD basis + per-component regression) | sequence encoder (`cell=`) with per-target branches |
| model family | any registry family (`learner=`) | a torch network; `cell=` is `gru`, `lstm`, `tcn` or `transformer` |
| knowledge channel | structural composition + admissibility | branch wiring + mass-balance hinge |
| can be asked about drivers it never saw | **no** | **yes** |
| state across time | none needed: the basis spans the whole record | reset every `chunk_days` steps: each window starts from a zero state, in training and in prediction |
| viability and intervals | classifier + split-conformal interval on the reduced scalar | neither; the extrapolation gate only |
| needs torch / a GPU | no | yes / strongly preferred |

**The conditioning is the whole difference.** A ROM's basis is tied to the window it was fitted on, so it learns one driver history and cannot answer a counterfactual. Feeding the drivers at every timestep makes the network an emulator of the MODEL rather than of the RUN, so its response to driver series outside the training record can be queried; check that response against the process model before relying on it.

**Use the ROM for calibration and the sequence model for emulation.** That is also the `use_mode`
split: `offline_search` gates on ranking, `online_inference` on pointwise accuracy.

```python
m = KGMLEmulator(spec, driver_names=driver_names, time_index=years,
                 branch_of={"net": ["gross", "loss_a", "loss_b"]},  # net computed FROM the others
                 mass_balance={"gross": 1.0, "loss_a": -1.0, "loss_b": -1.0, "net": -1.0},
                 mass_balance_scale=["loss_a", "loss_b"],           # the hinge's denominator
                 mass_balance_tol=measured_from_the_data,           # NO default, deliberately
                 nonneg=["gross", "loss_a", "loss_b"])
m.fit(X, None, viable=viable, trajectories=T, drivers=D)
m.predict_trajectories(X_new, D_counterfactual)
```

**`mass_balance_tol` has no default and `mass_balance_scale` is required**, both for the same reason: a relative hinge is a claim about how tightly a particular process model closes its own budget, and about which term is safe to divide by. A published tolerance (KGML's `tol_MB = 0.01`) belongs to the model it was measured on; a tolerance tighter than the emulated model's own closure penalises that model for its own behaviour, so measure the closure on the training trajectories. The denominator must stay bounded away from zero over the whole record: where a scale term reaches zero, the relative residual is unbounded there, and the hinge becomes explosive or inert depending on the tolerance.

**What to expect from the physics term.** It acts directly on the predicted budget violation. Its effect on pointwise accuracy is not implied by that, and has to be measured against an otherwise identical fit with the term inert.

**For calibration, where the scored quantity is a scalar, S1 is usually sufficient.** S2, S3 and the architectures below exist for emulating the structure of an output: its trajectory, field or network.

**S0 may not be used to rule anything out.** Ruling out requires honest intervals, which S0 does not produce; `run_acceptance` records that refusal as an explicit note rather than silently passing.

## Architectures by output type

The tiers say WHAT is emulated; the architecture follows from the SHAPE of the process model's output. Every class below takes the same `SurrogateSpec`, saves with `save(directory)` (which writes `spec.json`, `tier.json` and `environment.json` beside its weights), and returns one scalar per target from `predict_batch`, reducing a structured prediction to get it, so the scalar consumers accept every one of them.

| process-model output | shape | class (module) | options | tier |
|---|---|---|---|---|
| scalar metric | `(N, T)` | per-target learners in `S0Surrogate` / `S1Surrogate` (`tiers.py`) | `gp`, `rf`, `gbm` (histogram gradient boosting), `xgb` (optional `xgboost`), `mlp`, `ridge` | S0, S1 |
| short output vector | `(N, T)`, fitted jointly | `VectorSurrogate` (`multioutput.py`) | `mlp_multi` (shared-trunk deep ensemble), `gp_multi` (intrinsic coregionalisation GP) | S1 |
| time series, from theta alone | `(N, T, D)` | `S2Surrogate` / `S3Surrogate` (`tiers.py`) | latent ROM over any registry learner; S3 adds `compose` and `nonneg` | S2, S3 |
| time series under per-step drivers | `(N, T, D)` | `KGMLEmulator` (`sequence.py`) | `cell="gru"`, `"lstm"`, `"tcn"` (causal dilated convolutions), `"transformer"` (causally masked); **`spatial_graph=[(i, j), ...]`** adds masked attention ACROSS the target axis on a declared edge list, so a target is informed only by its named neighbours | S3 |
| gridded spatial field | `(N, C, *S)`, S one or two axes | `FieldEmulator` (`fields.py`) | `arch="cnn"` (decoder), `"unet"`, `"fno"` | S2, or S3 with `nonneg` |
| spatiotemporal field | `(N, C, D, *S)` | `SpatioTemporalEmulator` (`spatiotemporal.py`) | `arch="convlstm"`, `"fno"` (a Fourier recurrent cell) | S2, or S3 with `nonneg` |
| irregular network | `(N, C, n_nodes)`, or `(N, C, D, n_nodes)` with drivers | `GraphEmulator` (`graphs.py`) | `arch="gcn"` (edge weights honoured), `"gat"`; `driver_names=` makes it graph-temporal | S2, or S3 with `nonneg` |
| input function to output field | `a(x)` to `u(x)` | `FieldEmulator(arch="fno", input_field_names=...)` on a shared grid; `DeepONetEmulator` (`operators.py`) at any query coordinates | DeepONet takes the input function at fixed sensors and answers at arbitrary points | S2, or S3 with `nonneg` |

**Loading.** `tiers.load(directory)` rebuilds every class in the table: the four tier classes by `spec.tier`, the others by the class name `save` wrote into `tier.json`. It reads the artifact's own `spec.json` and runs the provenance and environment checks first. The dispatch has to be by class, because `KGMLEmulator` declares tier S3 and saves different files from `S3Surrogate`. Each architecture's own loader (`sequence.load_kgml`, `fields.load_field`, and so on) can still be called directly with a spec, but it skips the provenance check. The `load_surrogate.py` that `tools/package_surrogate.py` writes into a bundle calls `tiers.load`.

**What each class returns.** `S1Surrogate`, `S2Surrogate`, `S3Surrogate` and `VectorSurrogate` return a split-conformal interval, a viability probability and the extrapolation gate's verdict with each point prediction. **That interval is INFINITE when the calibration set is too small to support the level** -- below 19 rows at alpha 0.05 the rank the finite-sample guarantee needs does not exist, so the radius is `inf` and a warning says so (v2.436; it used to clamp the level to 1.0 and return the widest observed residual, which under-covers while reading as a 95 percent bound). `S0Surrogate` returns the point prediction alone. `KGMLEmulator` and the field, spatiotemporal, graph and operator classes return the point prediction and the extrapolation gate only, so interval coverage is not scored for them, and they cannot support ruling a region out.

**Structural properties the tests assert**, because each is invisible to a whole-record accuracy score:

- **Causal in time.** Two driver records identical up to step k give identical predictions up to k. Asserted for the `transformer` and `tcn` cells, both `SpatioTemporalEmulator` architectures and the graph-temporal network; `gru` and `lstm` are causal by construction. A Fourier operator over the space-time block is NOT causal, and a negative-control test shows it failing, which is why the spatiotemporal FNO is recurrent in time rather than an FNO over `(t, x)`.
- **State carried across chunks.** `SpatioTemporalEmulator` trains on windows of `chunk_steps` but carries the recurrent state from one window into the next, and predicts the whole record in one pass from its first step; a test asserts the carry for both architectures. The graph-temporal network uses the same scheme. A state reset at window edges, or a prediction that starts from a zero state part-way through a record, loses what the record had built up. `KGMLEmulator` resets: each `chunk_days` window starts from a zero state, in training and in prediction, so no step is informed by anything before the start of its own window.
- **Bounded reach.** A graph emulator with L layers lets a node be informed by nodes at most L hops away, asserted for `gcn` and `gat` at L = 1 and 2, with a fully connected network as the negative control. A `tcn` cell's memory ends at its receptive field.
- **Resolution transfer.** The FNO's spectral layer gives the same answer at the shared points of a grid twice as fine, and a test holds a `FieldEmulator(arch="fno")` trained on one grid to a within-case R² above 0.9 on grids two and four times finer. Every grid architecture will run on another grid, but only the FNO is designed to transfer; `DeepONetEmulator` answers at arbitrary coordinates by construction.

**Score a structured output WITHIN each case.** `per_case_channel_r2` flattens space, time and nodes per case and scores each case against its own mean, stamping `r2_normalisation: within_case`. `predict_batch` still reduces every channel to a scalar so these classes plug into the scalar battery, but `run_acceptance` scores only that reduction, not the field or the series.

**Training defaults.** `mlp_multi`, `FieldEmulator`, `SpatioTemporalEmulator`, `GraphEmulator` and `DeepONetEmulator` share one training loop, `_nn.fit_torch`: Adam in minibatches, a validation split by case, the best-validation checkpoint, and early stopping on `patience`. When the epoch budget, not the validation loss, ends a fit, a `RuntimeWarning` says so, and a NaN validation loss is refused. The field, spatiotemporal, graph and operator classes also refuse a NaN inside a row declared viable before training, and a reload defaults to the device the network was fitted on. `VectorSurrogate` leaves a viable row that misses any target out of the joint fit, with a warning. `gp_multi` trains full-batch with Adam on the negative log marginal likelihood, and subsamples above `max_points` as `gp` does. `KGMLEmulator` runs its own windowed loop rather than `_nn.fit_torch`, and since v2.439 it mirrors that loop's stopping contract instead of inheriting none of it: it takes `patience`, keeps the best-validation weights, records how the fit ENDED in `fit_info_` (`epochs_run`, `best_epoch`, `best_val`, `stopped_by_patience`), warns when the budget rather than the data ended it, refuses a non-finite validation loss, and reloads on the device it was fitted on. `patience` rides in the saved config because it decides which weights the artifact holds.

**THE BEST-VALIDATION CHECKPOINT IS NOT THE BEST MODEL WHEN THE USE IS EXTRAPOLATION.** Every class here selects
the checkpoint on a validation split taken over CASES, scored on the steps it trained on, so it measures
interpolation under conditions already seen. When the artifact's job is to answer about conditions it has NOT seen --
a new forcing record, a withheld year, a driver regime outside the training envelope -- that criterion can be
anti-correlated with the capability, and nothing in the artifact, the report or the history shows it. Measured on
`PFLOTRAN_miniLEO` with `KGMLEmulator(cell="tcn", layers=9)`, varying only the epoch budget: at 200 epochs the
validation loss is **3.4x better** than at 30 (0.00829 to 0.00244) while the withheld-forcing score is **2.9x worse**
(-0.3818 to -1.0941), and the fit selects epoch 196. Neither fit diverged. So for an extrapolation use, select the
checkpoint on a hold-out of the CONDITIONS, not of the cases, and treat a case-split validation curve as a training
diagnostic rather than as model selection. Details: `memory/dev_logs_adapterkit/20260923j_*`.

**What the tests do and do not establish.** They fit each family to synthetic data with a known answer, which shows that it can learn and that its structural properties hold. Whether a family suits a given process model is a separate measurement, on that model's own ensemble and scored within each case.

## Acceptance is a MEASUREMENT; promotion is a HUMAN GATE

`run_acceptance` measures. `AcceptanceReport.passed` means the automated thresholds **for this
surrogate's `use_mode`** were met, which is **necessary and not sufficient** for using the surrogate.

A surrogate becomes usable only when a human records approval with `tools/promote_surrogate.py`,
because three things that decide it are not thresholds: whether the training region contains the
answer (that is the standing gate, `scripts/check_surrogate_gate.py`), whether the predicted response
is physically plausible, and whether the hold-out split was optimistic. The approval is bound by
content hash to the acceptance report it was granted against, so **re-fitting invalidates it** rather
than silently inheriting it. Same shape as A2MC's other Tier-3 write gate, `review_pending_knowledge`.

`tools/promote_surrogate.py` has four subcommands: `review` prints the acceptance report with what it cannot tell you, `promote --basis "<what was checked beyond the metrics>"` records the approval in `promotion.json` beside the artifact, `revoke --reason` withdraws it, and `status` answers whether the artifact may be used. `tools/package_surrogate.py <artifact> --out <dir>` bundles an artifact with a copy of this module and a generated `load_surrogate.py`, so a recipient without A2MC can load it; it refuses an unpromoted artifact unless given `--allow-unpromoted`.

## Was the verdict ROBUST, or LUCKY?

`passed` is a hard threshold on ONE number from ONE split, so a surrogate at rho 0.71 against a
0.70 bar is indistinguishable from a comfortable one. Two diagnostics answer that, computed at fit
time and stored in `acceptance.json` so the promotion reviewer sees them without refitting:

- **`bootstrap_acceptance`** — resamples the TEST set (no refit) and reports how often each verdict holds. A `pass_rate` well below 1.0 under a headline PASS is the signal. Exact and cheap: the model is row-independent, so `predict(X[idx]) == predict(X)[idx]`, and the bootstrap predicts once and slices rather than predicting once per replicate.
- **`perturbation_stability`** — does the top-K SHORTLIST survive a relative input jitter? The loop
  consumes an ordering, so shortlist stability is the operationally meaningful form of robustness.
  **Read it with care:** LOW overlap alongside a HIGH rho means the top candidates are effectively
  TIED, which is a property of the problem rather than a defect in the surrogate — and is itself
  worth knowing, because it says the ordering is not meaningful.

Neither measures whether the TRAINING ensemble was representative. That is the standing gate
(`scripts/check_surrogate_gate.py`), and it is a different question.

## `use_mode` selects the battery

| | `offline_search` (calibration) | `online_inference` (runtime emulator) |
|---|---|---|
| accuracy | R² measured, **not gated** — ranking is the requirement | **R² >= 0.9 gates** |
| coverage | **gates** (the higher honesty bar) | measured, not gated |
| ranking | rho >= 0.7, top-K >= 0.5 | rho >= 0.5, top-K >= 0.3 |
| manifold respect | on-manifold fraction >= 0.9, when `Y_train` is supplied | the same |

Encoded in `MODE_CRITERIA`; an unknown mode is refused rather than defaulted, because falling back to another mode's bar would judge a runtime emulator by the calibration bar without saying so.

**Which R².** For a scalar target the battery pools one value per case, and the across-case variance is the signal. For a TRAJECTORY target the R² must be normalised within each case (`validate.summarise_per_case_r2`): a pooled R² divides by the between-case spread, which a parameter sweep makes large, and rates a model that only places each case's level as nearly perfect. `validate.require_r2_normalisation` refuses a trajectory report whose per-target blocks do not say `within_case`.

## The five acceptance tests

`R²` alone is not the gate: it does not say whether a surrogate orders candidates correctly, or whether its uncertainty is honest.

1. **Ranking fidelity** — Spearman ρ and top-K recall. A target that declares an `observed` value is ranked on each candidate's distance to it, the quantity a calibration orders candidates by; one without is ranked on the predicted level itself. The screening requirement, much weaker than accuracy.
2. **Interval coverage** — empirical vs nominal, reported *with mean width* so that an honest-but-useless wide interval is visible as such. A class that produces no intervals is not scored on it, and the report notes that.
3. **Boundary behaviour** — error binned by distance to training data. A rising profile is fine *provided the gate refuses out there*.
4. **Manifold respect** — are predicted target *combinations* producible at all? Independent per-target regressors will emit target pairs the model cannot produce.
5. **Confirmation rate** — measured in use via `record_confirmation`, never offline. The only number that decides whether the loop is better off.

Classifier accuracy is additionally reported **near the viability boundary**, because a global figure is dominated by easy interior points while the boundary is what decides anything.

## Two-stage, and why failures are training data

S1 fits a viability classifier on **all** rows including failed, dead, and crashed runs, then regresses **only on the viable subset**. Fitting one regressor across a regime boundary degrades it everywhere: a failed or collapsed run and a viable one are not two ends of a continuum.

This inverts normal ensemble hygiene. Failed runs must be **retained with their labels** (docs/41 §7 constraint 3); parameter bounds centred on a non-viable region show up only in those labels.

## Provenance

A surrogate is bound to a `(model commit, parameter list + bounds, base parameter file, scoring convention, training ensemble)` tuple. Change any element and the artifact is invalid, exactly as a RAG profile is invalid against the wrong source commit.

The scoring convention is the easiest element to overlook: a change in how targets are reduced (a calendar convention, an aggregation window) makes an artifact trained before it score against a different objective, while it still loads and predicts plausible numbers.

**It is checked on load when the caller states what it expects.** `load(dir, expect=<Provenance>)` raises on any field populated on both sides and differing; `strict=False` downgrades it to a warning. Unstamped fields always warn, because an empty field is treated as *unknown* rather than as a match — so an unstamped artifact is **unprotected**, not verified. `expect=None` skips the comparison, which is right for inspection and wrong before acting on the artifact.

**The library environment is checked on every load.** `save` records in `environment.json` the versions of the libraries that were imported when the artifact was built. `tiers.load` refuses under `strict` when one of them has changed major version or is missing, and warns on a smaller difference; an architecture's own loader, called directly, runs the same check.

## Interval calibration

Split conformal wraps **any** learner, so honest intervals never depend on the model family.

When the learner exposes a native σ (`ridge`, `rf`, `gp`, `mlp`), the nonconformity score is $|y-\hat y|/\sigma(x)$ and the interval is $\hat y \pm q\,\sigma(x)$ — **normalised conformal**, so the band widens where the model is unsure instead of being one constant width everywhere. That matters because calibration drives to box edges. Families without a σ (`gbm`, `xgb`) fall back to a constant half-width; `S1Surrogate.normalized` records which happened. `VectorSurrogate` applies the same rule per target with its joint learner's σ, which both `mlp_multi` and `gp_multi` provide.

The finite-sample level is $\lceil (n+1)(1-\alpha)\rceil / n$, not the plain $(1-\alpha)$ quantile, which under-covers on small calibration sets.

Coverage remains **marginal, not conditional** — which is precisely the limitation `docs/41` §2.1 turns on, and why the hull gate is a separate, non-optional check.

## Dependencies

`scikit-learn`, `numpy`, `scipy`, `joblib` for `ridge`/`rf`/`gbm`/`gp`; `torch` (in `a2mc_env`) for `mlp`, `mlp_multi`, `gp_multi` and every architecture in the section above. `SALib` for Sobol' indices through a surrogate (`scripts/surrogate_sobol_indices.py`). `xarray` is not required. `xgboost` is OPTIONAL and needed only for the `xgb` learner; on macOS its wheel also needs the OpenMP runtime (`brew install libomp`).

## Before fitting, and scope

**Two preconditions for a useful surrogate, both checked before fitting** (`docs/41` §8):

1. the round is sampled space-filling (Sobol' sequence or LHS), **and**
2. **the completed ensemble contains configurations inside the observational bands.**

**A space-filling design that still misses the targets does not satisfy them.** A surrogate is an interpolant of its training ensemble, so an ensemble that never reaches the target region carries no information about the only region worth searching.

**Condition 2 is executable, not a judgement:** run `scripts/check_surrogate_gate.py --y-matrix <Y csv>`. Exit 0 means the condition holds and exit 10 means it does not (a result, not an error); exit 1 or 2 means the check itself could not run. The condition is a property of the ensemble, not of the code, so no amount of fitting machinery satisfies it.

**Choose the hold-out for the question being asked.** Each splitter in `splits.SPLITTERS` returns a description of what it tests and what it is optimistic about, which is what belongs in `acceptance.json["split_kind"]`:

| splitter | what the held-out set tests |
|---|---|
| `random` | interpolation within the ensemble's own point set; always optimistic |
| `block` | a contiguous run of the sampling sequence. A tail block of a Sobol' sequence is surrounded by the points before it, so it is EASIER than a random hold-out and is not a neutral control; it does show whether anything depends on sequence position |
| `axis` | extrapolation along one named parameter: train on the rest of its range, predict its top (or bottom) tail |
| `shell` | extrapolation away from the centre of the cube, by mean absolute deviation; weak in many dimensions, where `axis` is the honest test |
| `levels` | whole values of a label withheld (driver years, sites, treatments); the test for a driver-conditioned emulator, because only it asks about conditions never seen |

Every splitter divides the training ensemble; an independent validation ensemble is drawn apart from it, which is the stronger test where one exists.

**Scope: this is an OFFLINE-AGENT capability.** It is deliberately **not** wired into `orchestrator.py`, and wiring is revisited only after the module has been exercised offline.

**Assembly and downstream tools.** `scripts/fit_ensemble_surrogate.py` builds `(X, Y, viable)` from a completed A2MC ensemble (the Y CSV from `scripts/extract_flat_ensemble_targets.py` joined to the round's X matrix on the case number), fits an `S1Surrogate` for `offline_search`, runs acceptance with the bootstrap and perturbation diagnostics, and saves; `--split` picks the hold-out (`random`, `block`, `axis`, `shell`), and `--test-matrix` with `--test-y` scores on an independent ensemble instead. `scripts/surrogate_sobol_indices.py` turns a fitted surrogate into Sobol' indices by pushing a large Saltelli design through it, gated on the acceptance report. Together these are the Phase-1 chain for a **space-filling** round, where neither `morris.analyze` nor `sobol.analyze` applies to the ensemble directly.
