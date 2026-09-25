# `tools/bayesian_optimization/` — the search layer

**What this answers.** A2MC already answers *what should we run next?* by reasoning: Phase 3 diagnosis returns parameter recommendations, Phase 4 designs targeted experiments, and every round report ends with a next-round plan (which parameters to test, add or drop, their bounds, the base and the design) that Phase 0 takes as its input. What it has not had is a **model-based search** that fits the completed runs and proposes specific parameter vectors by optimizing an acquisition on the joint objective. This package is that. It proposes the parameter sets most likely to put **every** validation target inside its observational band at the same time, confirms them on the physics model, and repeats.

**Full design:** [`docs/42_Multi_Objective_Bayesian_Optimization_Plan.md`](../../docs/42_Multi_Objective_Bayesian_Optimization_Plan.md). This README is the map; that document is the reasoning.

---

## What it is not

| | answers | lives in |
|---|---|---|
| **this package** | *where should the next run go?* | `tools/bayesian_optimization/` |
| the surrogate | *what would the model say at θ, without running it?* | `models/surrogate/` |
| the composite ranking | *which completed case scored best?* | `tools/optimize_function.py` |

Emulation and search are different jobs, which is why they are different directories — the acquisition function is a **consumer** of the surrogate, not part of it. This package reuses `models/surrogate`'s per-target GPs and viability classifier rather than building a second modelling layer (`docs/42` §3).

The composite is not being retired. It is the right **reporting** metric and the wrong **joint-feasibility** objective; §"The objective" below is the difference.

---

## The objective, and why it is not a mean

Per target $i$, the **normalized violation**

$$v_i(\theta) = \frac{|\mathrm{sim}_i(\theta) - \mathrm{obs}_i|}{u_i \cdot \mathrm{obs}_i}, \qquad V(\theta) = \max_i v_i(\theta)$$

$u_i$ is the fractional `uncertainty` already carried per target in `targets.yaml`, so the band is $\mathrm{obs} \times (1 \pm u)$ and **no new threshold is invented anywhere**. Then $v_i \le 1$ means target $i$ is in band, and $V \le 1$ means all of them are, simultaneously. That is the success criterion, not a proxy for it.

**A mean compensates; a max cannot.** A target deep inside its band can offset one far outside, so a good composite score can hide a failing target. Measured on EcoSIM BioCON R3: the round's best case by the composite (7329) misses `plant_C` by **74% of a band-width**, paid for by `NPP` and `Fs` sitting comfortably inside theirs. Case 2847 is worse on the composite and best under $V$, with all three targets within 16%.

$\arg\max_i v_i$ also **names the binding target**, which is a mechanistic statement the reasoning loop can use rather than a number.

---

## Modules, in build order

`docs/42` §6 builds in stages. **S0–S3 require zero simulations.**

| stage | module | what it does | status |
|---|---|---|---|
| **S0** | `objective.py` | the objective above, plus the free disagreement check against the composite | **built** — v2.334, 16 tests |
| **S1** | `bo_replay.py` | the **GO/NO-GO gate**: replay the propose loop against an already-completed ensemble and measure whether it rediscovers a known optimum faster than random | **built** — 17 tests; **GO** on EcoSIM_BioCON R3 (4/10 replicates reach the top-10 bar vs 1/10 random) |
| **S2** | `acquisition.py` | feasibility-weighted expected improvement, batched; maximized by a random-candidate scan with a local refinement step, not the L-BFGS-B this row once promised | **built** — v2.435, 60 tests |
| **S3** | `bo_loop.py` | propose → run → refit, with the three stopping rules | **built** — v2.435, 24 tests; DRY only: it refuses to run without `--dry-run` and has never touched a real ensemble (build step 9) |
| S4+ | — | closed loop on the physics model; Phase-6 integration | needs an active round |

> **Status corrected 2026-09-22.** The two rows above read "not built" until this date while both modules had been committed in `ef534b36` on 2026-09-17 -- 2,306 lines with 3,808 lines of tests. A status table that contradicts the tree is worse than none, because a reader trusts it instead of looking. The S2 row also described an L-BFGS-B optimizer that was never written; what landed is a scan plus local refinement.

**S1 is a real kill-switch, not a formality.** `docs/42`: *"If BO cannot rediscover a known optimum from data we already own, it will not find an unknown one."* Nothing after it is built until it returns GO.

---

## Running them

Source the round's site config first, so `$A2MC_VALIDATION_TARGETS` resolves.

```bash
source use_cases/EcoSIM_BioCON/config/ecosim_biocon_config_r3.sh

# S0 -- the objective, and where it disagrees with the composite
python tools/bayesian_optimization/objective.py \
    --y-matrix <round>/R3_Y_matrix_full.csv --only NPP,plant_C,Fs \
    --out per_case_V.csv --json s0_summary.json

# S1 -- the gate. Exit code 0 = GO, 10 = NO-GO.
python -u tools/bayesian_optimization/bo_replay.py \
    --x-matrix use_cases/EcoSIM_BioCON/parameters/ecosim_biocon_sobol_matrix_r03.txt \
    --y-matrix <round>/R3_Y_matrix_full.csv --only NPP,plant_C,Fs \
    --viable-if "NPP>1.0" \
    --n-seed 50 --q 5 --n-iter 30 --replicates 10 --top-k 10 \
    --json s1_gate.json --curves s1_curves.csv
```

**Use `python -u` for `bo_replay.py`.** It runs for minutes and buffers otherwise, and a zero-byte log is indistinguishable from a hang.

---

## Three things that will bite

**The join is 1-based, and case 0 has no row.** `scripts/materialize_adapter_ensemble.py:216` builds case `i` from `X[i-1]`, and the V0 baseline case has no design row at all. Under `i-1` it indexes `-1`, which in numpy is the **last** row of the design — a silent join that attaches the wrong parameters to a real result. `build_pool` refuses out-of-range case numbers and drops the baseline explicitly.

**A failed run returns no cost, not a bad one** (`docs/42` §4.2). Rows with a missing or non-finite value get `V = nan`, all their $v_i$ `nan`, and a binding index of `-1`; they are excluded from rankings, never sorted last. Imputing a penalty would teach anything fitted on this that the region is merely poor.

**No viability threshold is needed for `V` to work**, which looks wrong until the arithmetic. A dead EcoSIM case has $\mathrm{NPP} \approx 0$, so $v_{\mathrm{NPP}} = 1/0.36 = 2.78$ and it sinks on its own. The `--viable-if` split in `bo_replay.py` is a *separate* thing: it is what makes the acquisition's $P(\text{viable})$ term real, matching `S1Surrogate`'s two-stage shape, because fitting one regressor across a live/dead regime boundary is what produced the R² = 0.48 that motivated that tier.

---

## Gradient search: where it applies, and where it does not

**On the physics: not available.** ELM-FATES, EcoSIM and PFLOTRAN carry no adjoint and no automatic differentiation, so a gradient of the model would have to come from finite differences — `P + 1` simulations per step (29 here), across a surface where 81% of `EcoSIM_BioCON R3` returns NPP ≈ 0 and $V$ therefore jumps by ~1.6 across a boundary of zero width. A difference quotient straddling that cliff reports an arbitrarily large slope belonging to viability, not to the objective.

**On the surrogate: available, cheap, and planned.** The emulator is an ordinary differentiable function fitted in memory. S2 maximizes the acquisition by **multi-start L-BFGS-B**, with gradients analytic through a Matérn-5/2 GP posterior or via autograd through the torch MLP ensemble (`models/surrogate/learners.py` already calls `torch.autograd.grad` in its physics-guided loss). Multi-start matters: expected improvement is multimodal by construction, and a single descent collapses the batch onto one peak.

**The fallback is the right starting point.** A dense random-candidate scan needs no gradients and is dimension-robust; the surrogate evaluation is milliseconds against an hour-long simulation, so the inner optimizer is not on the critical path until it is shown to be. S1's replay uses the scan, because there the only observable candidates are the ensemble's own completed cases.

Full reasoning, including why a local method is still the right endgame tool once a basin is found: `docs/42` §6 S2 and §"Why not finite differences on the model itself".

---

## Related

- `docs/42_Multi_Objective_Bayesian_Optimization_Plan.md` — the plan, the formulation, the rejected alternatives, the open PI decisions
- `models/surrogate/README.md` — the emulator this reuses; *"the surrogate makes the SEARCH global, the physics model keeps the VERDICT"*
- `tools/cost_functions.py` — the composite this is compared against, and which `objective.py` imports rather than re-deriving
- `use_cases/EcoSIM_BioCON/memory/logs/20260822u_phase2_screening_r03_*` — the round's own hand-rolled convergence distance, which $V$ independently reproduces
