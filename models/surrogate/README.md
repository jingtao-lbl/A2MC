# `models/surrogate/` — learned emulators

**This is not a model adapter.** It lives under `models/` because it is a model *of* a model, but it does **not** implement `ModelBackend`, and it must **not** be registered in `models/registry.py`. Registering it would let the calibration loop mistake an emulator for a simulator, which is the one confusion this whole design exists to prevent.

Design and rationale: `docs/41_Surrogate_Module_Design_And_Implementation_Plan.md`.

## The one rule

> **The surrogate makes the SEARCH global. The physics model keeps the VERDICT.**

Every configuration a surrogate proposes is confirmed on the physics model before it enters a round record, a report, or curated knowledge. A surrogate result is unverified by construction, so injecting one into the knowledge base is already forbidden by `feedback_no_kb_injection_before_verified_test`.

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

## Two axes: tier and learner

These are independent, and conflating them was a real defect in the first cut (one hard-coded RandomForest shipped as if it were a ladder).

- **Tier** = *what* is emulated. Scalar (S0/S1) vs trajectory (S2) vs knowledge-guided sequence model (S3).
- **Learner** = *with what model family*. Any tier accepts any family.

### S1 makes two picks, not one

S1 asks two questions of every parameter set, and **both** are the caller's choice:

```
   parameter set θ
        ├──► "will it survive?"        → classifier= → alive / dead
        └──► "if so, what comes out?"  → learner=    → plant_C, NPP, ...
                                         (trained on the survivors only)
```

Same algorithm families appear in both lists because most families have a regressor *and* a classifier form — `RandomForestRegressor` and `RandomForestClassifier` are one algorithm pointed at two kinds of question.

| Family | Regressor (`learner=`) | Classifier (`classifier=`) | Inductive bias | Native σ |
|---|---|---|---|---|
| Linear model | `ridge` | `logistic` | linear — **the complexity baseline** | yes (leverage) |
| Random Forest | `rf` | `rf` | axis-aligned splits — **represents a cliff** | yes (inter-tree spread) |
| Gradient Boosting Machine | `gbm` | `gbm` | axis-aligned, boosted | no |
| Gaussian Process | `gp` | `gp` | ARD Matérn-5/2 + white noise | yes (analytic) |
| Multi-Layer Perceptron | `mlp` | `mlp` | smooth, torch deep ensemble | yes (ensemble disagreement) |

Notes on the entries:

- **`ridge`/`logistic` are one family in its two forms.** Logistic regression is a *classifier* despite the name — it predicts class probability, not a continuous value — so the regression counterpart is ridge, not a "logistic regressor".
- **Ridge rather than OLS or Lasso.** `RidgeCV` contains OLS as its α→0 limit, so it costs nothing when OLS would have sufficed and stays stable when it wouldn't; a baseline that fails for a boring reason (blown-up coefficients under correlated inputs) is worse than no baseline, because a strawman makes the flexible families look good for the wrong reason. Lasso is a different tool: it does variable *selection*, and under correlation it arbitrarily keeps one of a correlated group, producing a false sensitivity story.
- **Always put `ridge` in the bake-off.** It is the only thing that answers *"are the flexible families earning their complexity?"* If it matches them on ranking, they aren't.
- **Matérn-5/2 rather than RBF** is deliberate — RBF's smoothness prior is exactly wrong for knife-edge structure. The GP is `O(n³)`, so it subsamples above `max_points` and says so.
- **`logistic` earns its place on calibration.** When failures are the minority, tree classifiers are over-confident and step-like, and here the *probability itself* is used (it gates NROY and the search), not just the yes/no.
- **`mlp` is the only family that accepts a custom loss**, in either role. That makes it the PGNN entry point and the architecture S2/S3 grows from.

Any object with `fit`/`predict_proba`/`classes_` works as a classifier, so neither list is a limit.

**Pick on evidence, not taste.** `validate.compare_learners()` fits every combination on the same split, scores them through the identical acceptance battery, and ranks them; `bakeoff_summary()` prints the table with a `cliff` column (classifier accuracy *near* the boundary, not overall). Pass `classifiers=(...)` to cross both axes; failures are recorded with their error rather than silently dropped.

**Don't want to choose?** `recommend(goal, n_train=, structure=)` returns ranked options *with reasons* for five goals — `screen`, `sensitivity`, `rule_out`, `search`, `physics_constrained` — adjusting for dataset size and known response structure, and ending by saying the priors are not the last word. Two hard constraints are enforced: `rule_out` bars `gbm` (no native σ means one constant interval width), and `physics_constrained` admits only `mlp`.

### Knowledge-guided loss (the PGNN hook)

`KnowledgeGuidedLoss` adds soft penalties to the MLP's data loss — the "physics-guided loss" family of Willard et al. (2022), and the mechanism Liu et al. (2024) used for KGML-ag-Carbon:

- `monotone={input_index: ±1}` — required sign of ∂output/∂input, enforced on the autograd gradient
- `bounds=(lo, hi)` — admissible output range
- `weight` — the `α_phys` multiplier

Two caveats carried straight from the literature: **soft physics is not guaranteed physics** (prefer a structural `TargetSpec.transform` where one exists, since it holds under *any* weights), and a penalty regularises toward whatever you impose, so an incorrect monotonicity produces a confidently wrong model. Every entry should trace to a verified source-level mechanism.

This is **not** a PINN, and deliberately so — the supplied review is explicit that a classical PINN is not the right tool for emulating an existing model with a large library of paired simulations.

## Tiers

Ascent is **gated**: a tier may not be built until the tier below has *failed a written acceptance test*.
**The gate is enforced, not only stated** (v2.332): `spec.py` keeps two tuples — `VALID_TIERS` is the
roadmap, `IMPLEMENTED_TIERS` is the registry — and a spec declaring an unimplemented tier is refused at
construction with an error naming what would unblock it. Before that, `tier="S3"` constructed cleanly
and failed much later at `load()`.

**These S-labels are TIERS, and are unrelated to the S0-S6 STAGE labels in `docs/42`** (the
Bayesian-optimization plan). They share the letters and nothing else: stage S2's deliverable was moved out
of this package to `tools/bayesian_optimization/acquisition.py` on 2026-08-27, because acquisition is search rather than
emulation. Inside `models/surrogate/`, `S2` always means the trajectory tier.

| Tier | What it emulates | Produces | Use for |
|---|---|---|---|
| **S0** | `θ → scalar` per target | point estimate | ranking, screening, sensitivity structure |
| **S1** | viability, then `θ → scalar` | point + conformal interval + viability + hull gate | everything S0 does, plus anything requiring honest uncertainty |
| S2 | `θ → y(t)` | trajectory | not built — needs a written S1 failure first |
| S3 | knowledge-guided | trajectory + physics structure | not built — planned for a downstream runtime-emulator use case, not the calibration loop |

**S1 is very probably the ceiling for calibration.** S2/S3 are in the plan because a downstream runtime-emulator use case needs S3, not because this loop does.

**S0 may not be used to rule anything out.** Ruling out requires honest intervals, which S0 does not produce; `run_acceptance` records that refusal as an explicit note rather than silently passing.

## Acceptance is a MEASUREMENT; promotion is a HUMAN GATE

`run_acceptance` measures. `AcceptanceReport.passed` means the automated thresholds **for this
surrogate's `use_mode`** were met, which is **necessary and not sufficient** for using the surrogate.

A surrogate becomes usable only when a human records approval with `tools/promote_surrogate.py`,
because three things that decide it are not thresholds: whether the training region contains the
answer (that is the standing gate, `scripts/check_surrogate_gate.py`), whether the predicted response
is physically plausible, and whether the hold-out split was optimistic. The approval is bound by
content hash to the acceptance report it was granted against, so **re-fitting invalidates it** rather
than silently inheriting it. Same shape as A2MC's other Tier-3 write gate, `review_pending_knowledge`.

## Was the verdict ROBUST, or LUCKY?

`passed` is a hard threshold on ONE number from ONE split, so a surrogate at rho 0.71 against a
0.70 bar is indistinguishable from a comfortable one. Two diagnostics answer that, computed at fit
time and stored in `acceptance.json` so the promotion reviewer sees them without refitting:

- **`bootstrap_acceptance`** — resamples the TEST set (no refit) and reports how often each verdict
  holds. A `pass_rate` well below 1.0 under a headline PASS is the signal. Exact and cheap: the
  model is row-independent, so `predict(X[idx]) == predict(X)[idx]`, and the bootstrap predicts
  once and slices — 200 replicates in ~6 s rather than ~275 s.
- **`perturbation_stability`** — does the top-K SHORTLIST survive a relative input jitter? The loop
  consumes an ordering, so shortlist stability is the operationally meaningful form of robustness.
  **Read it with care:** LOW overlap alongside a HIGH rho means the top candidates are effectively
  TIED, which is a property of the problem rather than a defect in the surrogate — and is itself
  worth knowing, because it says the ordering is not meaningful.

Neither measures whether the TRAINING ensemble was representative. That is the standing gate
(`scripts/check_surrogate_gate.py`), and it is a different question.

## `use_mode` selects the battery, and now actually does

| | `offline_search` (calibration) | `online_inference` (runtime emulator) |
|---|---|---|
| accuracy | R² measured, **not gated** — ranking is the requirement | **R² >= 0.9 gates** |
| coverage | **gates** (the higher honesty bar) | measured, not gated |
| ranking | rho >= 0.7, top-K >= 0.5 | rho >= 0.5, top-K >= 0.3 |

Encoded in `MODE_CRITERIA`; an unknown mode is refused rather than defaulted. Until 2026-08-27 the
field was declared, validated and documented as selecting the battery while being read by nothing, so
an `online_inference` surrogate would have been judged by the calibration bar in silence.

## The five acceptance tests

`R²` is not the gate. It was what the 2025 Kougarok attempt reported, and it told nobody what to do.

1. **Ranking fidelity** — Spearman ρ and top-K recall. The screening requirement, much weaker than accuracy.
2. **Interval coverage** — empirical vs nominal, reported *with mean width* so that an honest-but-useless wide interval is visible as such.
3. **Boundary behaviour** — error binned by distance to training data. A rising profile is fine *provided the gate refuses out there*.
4. **Manifold respect** — are predicted target *combinations* producible at all? Independent per-target regressors will emit `(plant_C, NPP)` pairs the model cannot produce.
5. **Confirmation rate** — measured in use via `record_confirmation`, never offline. The only number that decides whether the loop is better off.

Classifier accuracy is additionally reported **near the viability boundary**, because a global figure is dominated by easy interior points while the boundary is what decides anything.

## Two-stage, and why failures are training data

S1 fits a viability classifier on **all** rows including failed, dead, and crashed runs, then regresses **only on the viable subset**. Fitting one regressor across a regime boundary is what produced the 2025 `Fineroot_PFT7` R² = 0.48: a dead stand and a living one are not two ends of a continuum.

This inverts normal ensemble hygiene. Failed runs must be **retained with their labels** (docs/41 §7 constraint 3); R1's bounds were void precisely because they were centred on a dead graft.

## Provenance

A surrogate is bound to a `(model commit, parameter list + bounds, base parameter file, scoring convention, training ensemble)` tuple. Change any element and the artifact is invalid, exactly as a RAG profile is invalid against the wrong source commit.

The scoring convention is the one learned the hard way: the EcoSIM leap-calendar fix (v2.213) changed target reduction on 2026-07-30, so anything trained before it scores against a different objective.

**This is enforced on load, not merely available.** `load(dir, expect=<Provenance>)` raises on any field populated on both sides and differing; `strict=False` downgrades it to a warning. Unstamped fields always warn, because an empty field is treated as *unknown* rather than as a match — so an unstamped artifact is **unprotected**, not verified. `expect=None` skips the comparison, which is right for inspection and wrong before acting on the artifact.

## Interval calibration

Split conformal wraps **any** learner, so honest intervals never depend on the model family.

When the learner exposes a native σ (`rf`, `gp`, `mlp`), the nonconformity score is $|y-\hat y|/\sigma(x)$ and the interval is $\hat y \pm q\,\sigma(x)$ — **normalised conformal**, so the band widens where the model is unsure instead of being one constant width everywhere. That matters because calibration drives to box edges. Families without a σ (`gbm`) fall back to a constant half-width; `S1Surrogate.normalized` records which happened.

The finite-sample level is $\lceil (n+1)(1-\alpha)\rceil / n$, not the plain $(1-\alpha)$ quantile, which under-covers on the small calibration sets we actually have.

Coverage remains **marginal, not conditional** — which is precisely the limitation `docs/41` §2.1 turns on, and why the hull gate is a separate, non-optional check.

## Dependencies

`scikit-learn`, `numpy`, `scipy`, `joblib` for `rf`/`gbm`/`gp`; `torch` (already in `a2mc_env`) for `mlp`. `SALib` 1.5.2 was added 2026-07-31 for Sobol/Morris. `xarray` and `xgboost` remain absent and are not required.

## Status

> ## ⛔ THE BUILD IS PAUSED AT A HARD PI GATE (2026-07-31) — read this before fitting anything
>
> **Two conditions, BOTH required**, recorded in `docs/41` §8 and the handoff `memory/dev_logs_adapterkitsurrogate/20260731d_*`:
>
> 1. the round is sampled space-filling (Sobol' sequence / LHS), **and**
> 2. **the completed ensemble contains configurations inside the observational bands.**
>
> **A space-filling design that still MISSES the targets does not open the build.** A surrogate is an interpolant of its training ensemble, so an ensemble that never reaches the target region carries no information about the only region worth searching.
>
> **Condition 2 is executable, not a judgement:** run `scripts/check_surrogate_gate.py --y-matrix <Y csv>`. Exit 0 opens the gate, exit 10 keeps it closed (a result, not an error).
>
> **Step A4 was EXECUTED AND WITHDRAWN on 2026-07-31**, not merely left unwritten — its results carry "forward into nothing", because it assessed a region that does not contain the answer. This banner exists because an earlier version of this Status section said only that A4 was "not yet written", and a session read that, did not open the handoff, and built toward the gated capability without seeing the gate (`memory/dev_logs_adapterkit/20260827e_*`). A README fronting a paused build must front the pause.

**Scope (PI, 2026-08-27): this is an OFFLINE-AGENT capability.** It is deliberately **not** wired into `orchestrator.py`, and that is a decision rather than a gap to close. Wiring is revisited only after the module has been exercised well offline.

Foundation built and unit-tested (A0–A3).

**A4 is CLOSED, and it is not a coding task that was left undone.** It was the *question* "do the existing R1/R2 ensembles suffice, or is a purpose-built ensemble a precondition?" — and it **answered: precondition**, so it was withdrawn rather than finished. `docs/41` is explicit that the correct response is to stop, not to mine the result.

What now exists is the **assembly machinery A4 would have used**, written 2026-08-27 for Phase C: `scripts/fit_ensemble_surrogate.py` builds `(X, Y, viable)` from a completed A2MC ensemble, fits, runs acceptance and saves. The layout it was waiting on is no longer guessed — it is `scripts/extract_flat_ensemble_targets.py`'s Y CSV joined to the round's X matrix on the case number, exercised against a real ensemble. **Having this machinery does not reopen A4 and does not open the gate**; the gate is a property of the ensemble, not of the code.

Downstream, `scripts/surrogate_sobol_indices.py` turns a fitted surrogate into Sobol' indices by pushing a large Saltelli design through it, gated on the acceptance report. Together these are the Phase-1 chain for a **space-filling** round, where neither `morris.analyze` nor `sobol.analyze` applies to the ensemble directly.

**Still not fitted to a real completed ensemble.** The first is PFLOTRAN miniLEO R1, in flight. The chain is verified end to end on the real design matrix with a synthetic response, and smoke-tested on that round's first completed cases; what is untested is the fit quality on real physics, which only the round can supply.
