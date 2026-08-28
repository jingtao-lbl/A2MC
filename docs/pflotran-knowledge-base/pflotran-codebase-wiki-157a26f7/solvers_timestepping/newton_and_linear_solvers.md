**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** the `NUMERICAL_METHODS` block, Newton convergence criteria, and the linear solver (`solver.F90`, `convergence.F90`, the `ReadNewtonBlock` methods on the process models)
**Last verified:** 2026-07-31

---

# Newton and Linear Solvers

## 0. What this document is

This describes **what "converged" means to PFLOTRAN**, how the deck's `NUMERICAL_METHODS` block is parsed, and which tolerance wins when PFLOTRAN's own criteria and PETSc's disagree. The audience is an agent diagnosing a run that is slow, that cuts too much, or that converged suspiciously fast.

Companions: `timestepping_and_cuts.md` (what happens once a solve is rejected) and `process_model_coupling.md` (which solver belongs to which process model).

**PFLOTRAN is built on PETSc.** `SNESSolve`, `SNESSetTolerances`, `SNESConvergedDefault`, `SNESGetConvergedReason`, `KSPSolve`, `KSPSetTolerances`, `PCSetType` and every `SNES*`/`KSP*`/`PC*`/`Mat*`/`Vec*` symbol below are **external PETSc**, not PFLOTRAN code. Where the distinction matters for diagnosis, it is called out explicitly.

**Run-control, not calibration.** Every card in §6 is a numerical setting. Loosening a tolerance changes how accurately the discrete equations are satisfied, which perturbs the answer, but it is not a model parameter. Hold these fixed across an ensemble.

---

## 1. The `NUMERICAL_METHODS` block

### 1.1 Top-level syntax

Read inside `SUBSURFACE` by `FactorySubsurfReadInput` (`factory_subsurface_read.F90:1547-1582`):

```
NUMERICAL_METHODS <qualifier>
  TIMESTEPPER
    ...
  /
  NEWTON_SOLVER
    ...
  /
  LINEAR_SOLVER
    ...
  /
END
```

The **qualifier is mandatory** and is read as the very next card on the same line (`factory_subsurface_read.F90:1548`). Accepted values (`:1551`, `:1560`, `:1569`):

| Qualifier | Routed to |
|---|---|
| `FLOW` | `simulation%flow_process_model_coupler%ReadNumericalMethods` |
| `TRANSPORT` or `TRAN` | `simulation%tran_process_model_coupler%ReadNumericalMethods` |
| `GEOPHYSICS` or `GEOP` | `simulation%geop_process_model_coupler%ReadNumericalMethods` |

Anything else errors with `NUMERICAL_METHODS must specify FLOW or TRANSPORT.` (`:1579-1580`). Naming a qualifier whose process model was never declared is also a hard error, e.g. `A SUBSURFACE_FLOW process model must be defined to read NUMERICAL_METHODS for FLOW.` (`:1556-1557`).

**Consequence: `FLOW` and `TRANSPORT` have completely independent timesteppers, Newton solvers and linear solvers.** Nothing is shared. A `NUMERICAL_METHODS TRANSPORT` block with `MAX_TS_CUTS 50` has no effect whatsoever on the flow solve.

### 1.2 The three sub-blocks

`PMCBaseReadNumericalMethods` (`pmc_base.F90:174-273`) dispatches on exactly three keywords (`:216-269`):

| Sub-block | Handler | Line |
|---|---|---|
| `TIMESTEPPER` | PM's `ReadTSBlock`, falling back to `timestepper%ReadSelectCase` | `:217-240` |
| `NEWTON_SOLVER` | PM's `ReadNewtonBlock`, falling back to `SolverReadNewtonSelectCase` | `:241-264` |
| `LINEAR_SOLVER` | `SolverReadLinear` (no PM hook) | `:265-266` |

Anything else is an unrecognised-keyword error (`:267-268`).

**The process model gets first refusal on `TIMESTEPPER` and `NEWTON_SOLVER` cards.** The source says so directly: `! leave in this order as PM overrides TS` (`pmc_base.F90:227`, repeated `:251`). Only if the PM leaves `found` false does the generic handler see the keyword. This is why the same spelling can mean different things in FLOW vs TRANSPORT, and why a card legal in GENERAL mode may be rejected in RICHARDS.

Guard: if the process model has no timestepper at all, the whole block errors with `No time integrator is used with process model "<name>". Therefore, a NUMERICAL_METHODS card may not be used.` (`pmc_base.F90:196-200`).

### 1.3 The pre-refactor spelling is a hard error

Bare top-level `TIMESTEPPER`, `NEWTON_SOLVER` or `LINEAR_SOLVER` cards (the pre-2020 syntax) now abort with an explanatory message pointing at "Numerical Methods Refactor" (`factory_subsurface_read.F90:1522-1527`). An old deck will not silently do the wrong thing; it will refuse to run.

---

## 2. The solver object

`solver_type` (`solver.F90:15-86`) holds one PETSc `SNES`, one `KSP`, one `PC`, one `TS`, the system matrix `M` and preconditioner matrix `Mpre`, and both PFLOTRAN's and PETSc's tolerances side by side.

Creation and ownership: each process model creates its own solver via `PMBaseInitializeSolver` → `SolverCreate()` (`pm_base.F90:397-410`), and the coupler then points its timestepper at it and stamps the class (`factory_subsurface_linkage.F90:411-414` for FLOW, `:497-500` for TRAN). The `itype` field (`FLOW_CLASS` / `TRANSPORT_CLASS` / `GEOPHYSICS_CLASS`) is what selects the PETSc options prefix `-flow_` / `-tran_` / `-geop_` (`solver.F90:579-586`, `:1063-1070`).

**Some modes override the solver defaults before the deck is read.** GENERAL sets `newton_dtol = 1.d9` and `newton_max_iterations = 8` (`pm_general.F90:748-750`, with the comment `helps accommodate rise in residual due to change in state`). RICHARDS does not override, so it inherits `SolverCreate`'s values. Do not assume "the default" is mode-independent.

### 2.1 SNES type

`solver%snes_type` defaults to `SNESNEWTONLS` (`solver.F90:177`). `SolverCreateSNES` accepts only `SNESNEWTONLS`, `SNESNEWTONTR`, `SNESNEWTONTRDC` and errors on anything else (`solver.F90:445-453`).

**Line search is then switched off again.** `PMCSubsurfaceSetupSolvers_TimestepperSNES` sets `SNESLINESEARCHBASIC` with the comment `! by default turn off line search` (`pmc_subsurface.F90:274-279`). So the default subsurface configuration is a plain undamped Newton method, not a globalised one, unless the deck asks for a trust-region type via `SNES_TYPE`.

---

## 3. Newton convergence: who wins

This is the part most likely to be misread. The convergence decision is made in **three layers**, evaluated in order, each able to overwrite the previous one.

### 3.1 The call chain

PETSc's `SNESSetConvergenceTest` is pointed at PFLOTRAN's own callback (`pmc_subsurface.F90:303-305`), which dispatches to the process model's `CheckConvergence`. For Richards that is `PMRichardsCheckConvergence` (`pm_richards.F90:713-834`), which ends by calling `PMSubsurfaceFlowCheckConvergence` (`pm_richards.F90:832-833`), which calls the shared `ConvergenceTest` (`pm_subsurface_flow.F90:845-847`). Reactive transport routes through `pm_rt.F90:1476`.

So the ordering per Newton iteration is: **PM-specific test → generic `ConvergenceTest` → PETSc's `SNESConvergedDefault` (called from inside `ConvergenceTest`) → PFLOTRAN overrides.**

### 3.2 Layer 1 — the PM's own infinity-norm test (sets a flag)

`PMRichardsCheckConvergence` loops over local cells and tests four quantities against four tolerances (`pm_richards.F90:748-762` for the residuals, `pm_richards.F90:636-645` in `PMRichardsCheckUpdatePost` for the updates):

| Quantity | Tested against | Field |
|---|---|---|
| $\lvert R_i\rvert$ | `residual_abs_inf_tol` | absolute residual |
| $\lvert R_i\rvert / \lvert A_i\rvert$ | `residual_scaled_inf_tol` | residual scaled by the accumulation term |
| $\lvert \Delta X_i\rvert$ | `abs_update_inf_tol` | absolute update |
| $\lvert \Delta X_i\rvert / \lvert X^0_i\rvert$ | `rel_update_inf_tol` | relative update |

The four per-cell flags are `MPI_Allreduce`d with `MPI_LAND` (`pm_richards.F90:791-793`), then:

```fortran
option%convergence = CONVERGENCE_CONVERGED               ! pm_richards.F90:798
do itol = 1, MAX_INDEX
  if (.not.this%converged_flag(itol)) then
    option%convergence = CONVERGENCE_KEEP_ITERATING      ! pm_richards.F90:802
```

**This entire block is guarded by `if (this%check_post_convergence)`** (`pm_richards.F90:732`, `:958`). And for subsurface flow that flag **defaults to false** (`pm_subsurface_flow.F90:116`). It is turned on by `USE_INFINITY_NORM_CONVERGENCE` and off again by `USE_EUCLIDEAN_NORM_CONVERGENCE` (`pm_subsurface_flow.F90:312-316`).

**Per-mode default for `check_post_convergence`, verified:**

| Mode | Default | Source |
|---|---|---|
| all `pm_subsurface_flow` descendants (incl. RICHARDS, TH) | **false** | `pm_subsurface_flow.F90:116` |
| GENERAL | **true** | `pm_general.F90:102` |
| ZFLOW | **true** | `pm_zflow.F90:117` |
| WIPP_FLOW | **true** | `pm_wipp_flow.F90:176` |
| reactive transport (`pm_rt`) | **false** | `pm_rt.F90:151` |
| NWT | **false** | `pm_nwt.F90:156` |

For reactive transport it is switched on implicitly by supplying `ITOL_ABSOLUTE_UPDATE` or `ITOL_RELATIVE_UPDATE` (`pm_rt.F90:363-370`) or by `REFACTORED_CONVERGENCE` (`pm_rt.F90:253-254`).

**Diagnostic implication:** in a plain Richards run with no `USE_INFINITY_NORM_CONVERGENCE`, the `ITOL_*` tolerances are read and stored but **never consulted**. Setting them will not change anything. Confirm the flag before blaming a tolerance.

### 3.3 Layer 2 — `ConvergenceTest`

`ConvergenceTest` (`convergence.F90:58-668`) is where the layers combine. The order is exactly:

1. **PETSc runs first.** `call SNESConvergedDefault(snes_,i_iteration,xnorm,unorm,fnorm,reason,0,ierr)` (`convergence.F90:174-175`), with the comment `We must check the convergence here as i_iteration initializes snes->ttol for subsequent iterations`. This applies PETSc's `atol` / `rtol` / `stol` / `divtol` and fills `reason`.
2. Early exit on PETSc divergence-tolerance (`reason == -9`) when the PM did not claim convergence (`convergence.F90:177-182`).
3. `option%force_newton_iteration` forces `reason = 0` and returns (`convergence.F90:193-197`).
4. `option%out_of_table` forces `reason = -19` (`convergence.F90:204-206`).
5. **`option%convergence` overwrites `reason` outright** (`convergence.F90:214-227`):

   | `option%convergence` | value | `reason` becomes |
   |---|---|---|
   | `CONVERGENCE_CUT_TIMESTEP` | -1 | `-88` |
   | `CONVERGENCE_KEEP_ITERATING` | 0 | `0` |
   | `CONVERGENCE_FORCE_ITERATION` | 1 | `0` |
   | `CONVERGENCE_CONVERGED` | 2 | `999` |
   | `CONVERGENCE_BREAKOUT_INNER_ITER` | 3 | `6` |

   (constants at `pflotran_constants.F90:306-311`). It is then reset to `CONVERGENCE_OFF` (`convergence.F90:230`) so a sibling process model does not inherit it.

**So the answer to "which wins" is: PFLOTRAN's PM-level criterion wins, because it is applied after PETSc's and simply overwrites the reason code.** PETSc's `atol`/`rtol`/`stol` only decide the outcome when the PM leaves `option%convergence` at `CONVERGENCE_OFF` — i.e. when `check_post_convergence` is false, which for Richards is the default.

6. If `solver%check_infinity_norm` is true (default true, `solver.F90:186`), a further block computes the infinity norms of the residual and the update directly from the PETSc vectors and can overwrite `reason` again (`convergence.F90:233-261`):
   - `inorm_residual < newton_inf_res_tol` → `reason = 10` (`itol_res`)
   - `inorm_update < newton_inf_upd_tol` and `i_iteration > 0` → `reason = 11` (`itol_upd`)
   - `inorm_residual > solver%max_norm` → `reason = -20`

   **Both `newton_inf_res_tol` and `newton_inf_upd_tol` default to `UNINITIALIZED_DOUBLE = -999.d0`** (`solver.F90:142-143`, `pflotran_constants.F90:300`). Since norms are non-negative, `norm < -999` is never true, so these two paths are **inert unless `ITOL`/`ITOL_UPDATE` is supplied in the deck**. That is deliberate but easy to misread as "PFLOTRAN has a default infinity-norm tolerance". It does not.

   `max_norm` defaults to `MAX_DOUBLE = 1.d20` (`solver.F90:141`, `pflotran_constants.F90:303`), so `reason = -20` fires only on a genuinely exploding residual.

7. **`MINIMUM_NEWTON_ITERATIONS` is applied last and overrides everything except `-88`** (`convergence.F90:276-278` in the infinity-norm branch, `:379-381` in the other):
   ```fortran
   if (i_iteration < solver%newton_min_iterations .and. reason /= -88) reason = 0
   ```
   Default `newton_min_iterations = 1` (`solver.F90:148`). So the iteration-0 "already converged" outcome is suppressed and **at least one Newton iteration is always taken** unless the deck sets it to 0.

### 3.4 The per-iteration convergence line

Unless `NO_PRINT_CONVERGENCE` was given, each Newton iteration prints one line (`convergence.F90:280-364`) of the shape

```
  2 2r: 3.14e-04 2x: 1.00e+07 2u: 2.71e-02 ir: 5.55e-06 iu: 1.11e-03 rsn: itol_res
```

where `2r`/`2x`/`2u` are the 2-norms of residual, solution and update (PETSc's `fnorm`/`xnorm`/`unorm`), `ir`/`iu` are the infinity norms, and `rsn` is the decoded reason: `atol` (2), `rtol` (3), `stol` (4), `itol_res` (10), `itol_upd` (11), `itol_post_check` (12), `itol_res_sec` (13), `max_norm` (-20), `out_of_EOS_table` (-19), else the raw integer (`convergence.F90:282-301`). Which columns appear is controlled by the `CONVERGENCE_INFO` sub-block (§6.2).

**`NO_PRINT_CONVERGENCE` suppresses this entire line** (`solver.F90:1226-1227`). A deck carrying it has thrown away the primary per-iteration diagnostic; if a member is behaving strangely, re-run one case without it.

The private reason `999` (`CONVERGENCE_CONVERGED`) has **no** decoded string and falls through to `case default`, printing as the bare integer `999`. Likewise `-88` prints as `-88`. Seeing `rsn: -88` in a log means the process model explicitly demanded a timestep cut.

### 3.5 Oscillation detection

`PMSubsurfaceFlowCheckConvergence` keeps a 7-deep rolling history of the `(fnorm, xnorm, unorm)` triple and warns `Potential oscillatory convergence` when the current triple and its two successors repeat an earlier triple to within 1% (`pm_subsurface_flow.F90:850-869`, tolerance `tol = 1.d-2` at `:842`). Advisory only — it does not change `reason`.

---

## 4. What happens to a diverged solve

`snes_reason <= 0` sends the step to `CutDT` (`timestepper_SNES.F90:402-409`; see `timestepping_and_cuts.md` §3). Additionally, if `snes_reason < SNES_CONVERGED_ITERATING`, `SolverNewtonPrintFailedReason` decodes it (`timestepper_SNES.F90:411`).

That routine (`solver.F90:1595-1706`) prints `Newton solver reason: <text>`. Without `VERBOSE_LOGGING` the text is the bare PETSc enum name; **with** `VERBOSE_LOGGING` it is a sentence, and for several reasons it interpolates the actual tolerance in force:

| PETSc reason | Terse | Verbose adds |
|---|---|---|
| `SNES_DIVERGED_FUNCTION_DOMAIN` | name only (`:1625`) | "The new solution location passed to the function is not in the domain of F." |
| `SNES_DIVERGED_FUNCTION_COUNT` | name only | the `maxf` value (`:1629-1632`) |
| `SNES_DIVERGED_LINEAR_SOLVE` | name only | "The linear solver failed." **and** calls `SolverLinearPrintFailedReason` regardless of verbosity (`:1702-1703`) |
| `SNES_DIVERGED_FNORM_NAN` | name only | points at boundary conditions / out-of-range constitutive relations (`:1644-1648`) |
| `SNES_DIVERGED_MAX_IT` | name only | the `maxit` value (`:1654-1656`) |
| `SNES_DIVERGED_LINE_SEARCH` | name only | "The line search failed." |
| `SNES_DIVERGED_DTOL` | name only | the `divtol` value (`:1683-1686`) |

**`VERBOSE_LOGGING` is the single highest-yield diagnostic switch for a failing member.** It is accepted in both `NEWTON_SOLVER` (`solver.F90:1343`) and `LINEAR_SOLVER` (`solver.F90:952`), aliased `VERBOSE_ERROR_MESSAGING`.

It also enables NaN localisation: on `SNES_DIVERGED_FNORM_NAN` with `verbose_logging`, `OutputFindNaNOrInfInVec` is called on the residual vector to identify the offending cells (`timestepper_SNES.F90:413-422`).

---

## 5. The linear solver

### 5.1 Defaults

`SolverCreate` leaves `linear_atol`, `linear_rtol`, `linear_dtol` and `linear_max_iterations` at `PETSC_DEFAULT_REAL` / `PETSC_DEFAULT_INTEGER` (`solver.F90:129-132`). **PFLOTRAN supplies no linear-solver tolerances of its own; PETSc's own defaults apply** until the deck overrides them. The KSP type defaults to `KSPBCGS` (`solver.F90:178`) and `pc_type` to the empty string (`solver.F90:179`), meaning PETSc's default preconditioner is used unless the deck names one.

After setup, PFLOTRAN reads the effective values back out of PETSc with `KSPGetTolerances` (`solver.F90:527-529`, `:243-245`) so that whatever it later prints reflects command-line overrides too.

### 5.2 Precedence

The comment at `solver.F90:239-240` states the rule: `KSPSetFromOptions must come after custom setup in order to override from command line`. And `solver.F90:499-504` notes `SNESSetFromOptions()` calls `KSPSetFromOptions()`, which calls `PCSetFromOptions()`, so they must not be called separately. Order of precedence, weakest to strongest:

1. PETSc built-in defaults
2. PFLOTRAN's `SolverCreate` values and any per-PM override (§2)
3. Deck cards in `LINEAR_SOLVER` / `NEWTON_SOLVER`
4. **PETSc command-line options** (`-flow_*`, `-tran_*`, `-geop_*`), applied last

Several deck cards are themselves nothing but wrappers that call `PetscOptionsSetValue` with the class prefix — the whole `HYPRE_OPTIONS` sub-block (`solver.F90:664-908`), `GMRES_RESTART` (`solver.F90:962`), `MUMPS` (`solver.F90:944-946`), and every `NTRDC_OPTIONS` card (`solver.F90:1104-1214`). Those are indistinguishable from command-line settings once set.

### 5.3 Reading the linear-work ratio

The most useful derived statistic from the end-of-run summary is **linear iterations per Newton iteration**. It comes straight from PETSc's `SNESGetLinearSolveIterations` divided by `SNESGetIterationNumber` accumulated over the run. Interpretation:

- A ratio in the low single digits means the preconditioner is doing its job and the cost is in the number of nonlinear solves, i.e. in timestepping.
- A ratio in the tens means the Krylov solve is the bottleneck; the lever is `PRECONDITIONER` / `HYPRE_OPTIONS` / `CPR`, not `MAX_TS_CUTS` or the governors.

For the reference run, FLOW is 537044/15404 ≈ 35 and TRAN is 54684/22432 ≈ 2.4. FLOW is preconditioner-limited; TRAN is not.

---

## 6. Card tables

**All run-control, none calibration.**

### 6.1 `NEWTON_SOLVER` — generic (`SolverReadNewtonSelectCase`, `solver.F90:1036-1385`)

| Keyword | Line | Default (line) | Effect |
|---|---|---|---|
| `ATOL` | `:1250` | `PETSC_DEFAULT_REAL` (`:137`) | PETSc SNES absolute residual tolerance, via `SNESSetTolerances` (`:487`). |
| `RTOL` | `:1254` | `PETSC_DEFAULT_REAL` (`:138`) | PETSc SNES relative residual tolerance. |
| `STOL` | `:1258` | `PETSC_DEFAULT_REAL` (`:139`) | PETSc step-size tolerance; also fed to `SNESLineSearchSetTolerances` for `SNESNEWTONLS` (`:515`). |
| `DTOL` | `:1262` | `PETSC_DEFAULT_REAL` (`:140`); GENERAL overrides to `1.d9` (`pm_general.F90:749`) | PETSc divergence tolerance, via `SNESSetDivergenceTolerance` (`:490`). |
| `MAXIMUM_NUMBER_OF_ITERATIONS` | `:1236` | `PETSC_DEFAULT_INTEGER` (`:147`); GENERAL overrides to `8` (`pm_general.F90:750`) | Max Newton iterations. Exceeding it gives `SNES_DIVERGED_MAX_IT` → timestep cut. |
| `MINIMUM_NEWTON_ITERATION(S)` | `:1240` | `1` (`:148`) | Floor; forces `reason = 0` below this count (`convergence.F90:276`, `:379`). |
| `MAXF` | `:1294` | `PETSC_DEFAULT_INTEGER` (`:149`) | Max residual evaluations. |
| `MAX_NORM` | `:1266` | `MAX_DOUBLE = 1.d20` (`:141`) | Residual infinity norm above which `reason = -20` (`convergence.F90:259`). |
| `ITOL` / `INF_TOL` / `ITOL_RES` / `INF_TOL_RES` | `:1270` | uninitialised → **inert** (`:142`) | Infinity-norm residual tolerance → `reason = 10`. |
| `ITOL_UPDATE` / `INF_TOL_UPDATE` | `:1274` | uninitialised → **inert** (`:143`) | Infinity-norm update tolerance → `reason = 11`. |
| `ITOL_SEC` / `ITOL_RES_SEC` / `INF_TOL_SEC` | `:1278` | `1.d-10` (`:146`) | Secondary-continuum residual tolerance. **Requires `MULTIPLE_CONTINUUM` and TRANSPORT**, else hard error (`:1280-1289`). |
| `SNES_TYPE` | `:1074` | `SNESNEWTONLS` (`:177`) | `LINE_SEARCH`, `TRUST_REGION`, `NTRDC`/`NEWTONTRDC`, `NTR`/`NEWTONTR`. The last two also set `option%flow%using_newtontrdc`. |
| `NTRDC_OPTIONS` / `NEWTONTRDC_OPTIONS` / `NTR_OPTIONS` / `NEWTONTR_OPTIONS` | `:1104` | — | Sub-block forwarding `TR_TOL`, `ETA1..3`, `T1`, `T2`, `DELTA_M`, `DELTA_0`, `USE_CAUCHY`, `AUTO_SCALE_UNKNOWNS`, `AUTO_SCALE_MAX` to PETSc options. |
| `INEXACT_NEWTON` | `:1223` | off (`:181`) | Enables PETSc Eisenstat–Walker via `SNESKSPSetUseEW` (`:495`). |
| `NO_PRINT_CONVERGENCE` | `:1226` | printing **on** (`:183`) | Suppresses the per-iteration convergence line. |
| `PRINT_DETAILED_CONVERGENCE` | `:1244` | off (`:184`) | Per-dof norms, max/min values and their cell IDs (`convergence.F90:418-640`). Expensive. |
| `PRINT_LINEAR_ITERATIONS` | `:1247` | off (`:185`) | Adds `   Linear Solver Iterations: <n>` per Newton iteration (`convergence.F90:410-414`). Only in the non-infinity-norm branch. |
| `NO_INF_NORM` / `NO_INFINITY_NORM` | `:1229` | check **on** (`:186`) | Disables the whole infinity-norm block in `ConvergenceTest`. |
| `MATRIX_TYPE` | `:1298` | PETSc default (`:166`) | `BAIJ`, `AIJ`, `MFFD`/`MATRIX_FREE`, `HYPRESTRUCT`, `SELL`. |
| `PRECONDITIONER_MATRIX_TYPE` | `:1319` | PETSc default (`:167`) | Same set plus `SHELL`. Note: the `SELL` case here assigns `M_mat_type`, not `Mpre_mat_type` (`:1333-1334`) — apparent bug, reported as observed. |
| `VERBOSE_LOGGING` / `VERBOSE_ERROR_MESSAGING` | `:1343` | off (`:157`) | Verbose failure text + `SNESView` (`:1507-1509`). |
| `CONVERGENCE_INFO` | `:1346` | all on (`:158-162`) | Sub-block of `YES`/`NO` toggles: `2R`/`FNORM`/`2NORMR`, `2X`/`XNORM`/`2NORMX`, `2U`/`UNORM`/`2NORMU`, `IR`/`INORMR`, `IU`/`INORMU` — selects which columns the convergence line shows. |

### 6.2 `NEWTON_SOLVER` — subsurface-flow cards (claimed by the PM first)

`PMSubsurfaceFlowReadNewtonSelectCase` (`pm_subsurface_flow.F90:256-322`):

| Keyword | Line | Effect |
|---|---|---|
| `PRESSURE_DAMPENING_FACTOR` | `:284` | Damps the pressure update in a pre-check. |
| `PRESSURE_CHANGE_LIMIT` | `:292` | Caps the per-iteration pressure change. |
| `SATURATION_CHANGE_LIMIT` | `:288` | Caps the per-iteration saturation change. |
| `TEMPERATURE_CHANGE_LIMIT` | `:296` | Caps the per-iteration temperature change. |
| `NUMERICAL_JACOBIAN` | `:302` | Finite-difference Jacobian. |
| `ANALYTICAL_JACOBIAN` | `:305` | Analytic Jacobian (`ANALYTICAL_DERIVATIVES` is deprecated, `:308`). |
| `USE_INFINITY_NORM_CONVERGENCE` | `:312` | **Enables the PM's `ITOL_*` machinery** (§3.2). |
| `USE_EUCLIDEAN_NORM_CONVERGENCE` | `:315` | Disables it. |

`PMRichardsReadNewtonSelectCase` (`pm_richards.F90:210-247`) adds the tolerances themselves:

| Keyword | Line | Default (line) |
|---|---|---|
| `RESIDUAL_INF_TOL` | `:213` | sets both residual tolerances at once |
| `RESIDUAL_ABS_INF_TOL` | `:219` | `1.d-5` (`:80`) |
| `RESIDUAL_SCALED_INF_TOL` / `ITOL_SCALED_RESIDUAL` | `:224` | `1.d-5` (`:81`) |
| `UPDATE_INF_TOL` | `:228` | sets both update tolerances at once |
| `ABS_UPDATE_INF_TOL` | `:234` | `1.d0` (`:82`) |
| `REL_UPDATE_INF_TOL` / `ITOL_RELATIVE_UPDATE` | `:240` | `1.d-5` (`:83`) |

`pm_th.F90:259`/`:292` uses the same two aliases. **In GENERAL and SCO2 the bare `ITOL_SCALED_RESIDUAL` / `ITOL_RELATIVE_UPDATE` spellings are deprecated** and route through `InputKeywordDeprecated` (`pm_general.F90:571-572`, `:631-632`; `pm_sco2.F90:466-467`, `:530-531`). In NWT the analogous cards are block-structured and *mandatory*, named `NWT_ITOL_ABSOLUTE_RESIDUAL`, `NWT_ITOL_SCALED_RESIDUAL`, `NWT_ITOL_RELATIVE_UPDATE`, `NWT_ITOL_ABSOLUTE_UPDATE` (`pm_nwt.F90:345`, `:370`, `:395`, `:420`; required-block checks at `:532-551`).

For reactive transport, `PMRTReadNewtonSelectCase` (`pm_rt.F90:332-376`) accepts only `NUMERICAL_JACOBIAN`, `ITOL_ABSOLUTE_UPDATE` and `ITOL_RELATIVE_UPDATE`, the latter two writing module-level variables `rt_itol_abs_update` / `rt_itol_rel_update` and switching `check_post_convergence` on.

### 6.3 `LINEAR_SOLVER` (`SolverReadLinear`, `solver.F90:557-982`)

| Keyword | Line | Default (line) | Effect |
|---|---|---|---|
| `SOLVER` / `KSP_TYPE` | `:602` | `KSPBCGS` (`:178`) | `NONE`/`PREONLY`, `GMRES`, `FGMRES`, `BCGS`/`BICGSTAB`/`BI-CGSTAB`, `IBCGS`/`IBICGSTAB`/`IBI-CGSTAB`, `RICHARDSON`, `CG`, `DIRECT` (= PREONLY+LU), `ITERATIVE`/`KRYLOV` (= BCGS+BJACOBI). |
| `PRECONDITIONER` / `PC_TYPE` | `:633` | PETSc default (`:179`) | `NONE`, `ILU`, `LU`, `BJACOBI`/`BLOCK_JACOBI`, `JACOBI`, `ASM`/`ADDITIVE_SCHWARZ`, `HYPRE`, `SHELL`, `CPR` (allocates the CPR stash, `:656-657`). |
| `ATOL` | `:912` | PETSc default (`:129`) | KSP absolute tolerance. |
| `RTOL` | `:916` | PETSc default (`:130`) | KSP relative tolerance. |
| `DTOL` | `:920` | PETSc default (`:131`) | KSP divergence tolerance. |
| `MAXIMUM_NUMBER_OF_ITERATIONS` | `:928` | PETSc default (`:132`) | KSP iteration cap. (`MAXIT` is deprecated, `:924-926`.) |
| `LU_ZERO_PIVOT_TOL` | `:932` | uninitialised (`:133`) | Zero-pivot tolerance for LU. |
| `DISABLE_SHIFT` | `:937` | shift **on** (`:135`) | Turns off the diagonal shift that guards near-zero pivots. |
| `STOP_ON_FAILURE` | `:940` | off (`:134`) | `KSPSetErrorIfNotConverged(PETSC_TRUE)` (`:286`) — the run **dies** on a linear failure instead of cutting the timestep. |
| `MUMPS` | `:943` | — | Sets `-<prefix>pc_factor_mat_solver_type mumps`. |
| `CPR_OPTIONS` | `:949` | — | Sub-block, handled in `solver_cpr.F90`. |
| `HYPRE_OPTIONS` | `:664` | — | Large sub-block of BoomerAMG/PILUT/ParaSails/Euclid pass-throughs (`:673-908`). |
| `GMRES_RESTART` | `:955` | PETSc default | `-<prefix>ksp_gmres_restart`. |
| `GMRES_MODIFIED_GS` | `:966` | off | `-<prefix>ksp_gmres_modifiedgramschmidt`. |
| `VERBOSE_LOGGING` / `VERBOSE_ERROR_MESSAGING` | `:952` | off (`:157`) | Verbose failure text + `KSPView`/`PCView` (`:1441-1442`). |

Guard worth knowing: with a PETSc lacking MUMPS, `KSPPREONLY + PCLU` on more than one rank is a hard error advising `SOLVER ITERATIVE` (`solver.F90:1410-1418`).

---

## 7. The echo of the solver settings

At the start of a run, `TimestepperSNESPrintInfo` (`timestepper_SNES.F90:957-1006`) prints the timestepper block and then calls `SolverPrintNewtonInfo` and `SolverPrintLinearInfo` (`:1003-1004`).

`SolverPrintNewtonInfo` (`solver.F90:1450-1511`) emits a `<NAME> Newton Solver` header followed by `atol`, `rtol`, `stol`, `dtol`, `maxnorm`, `inftolres`, `inftolupd`, `inftolrelupd`, `inftolsclres`, `max iter`, `min iter`, `maxf`, `matrix type`, `precond. matrix type`, `inexact newton`, `print convergence`, `print detailed convergence`, `check infinity norm`. `SolverPrintLinearInfo` (`solver.F90:1389-1446`) emits `<NAME> Linear Solver` with `solver`, `preconditioner`, `atol`, `rtol`, `dtol`, `maximum iteration` and, if set, `zero pivot tolerance`.

**These echoes are the ground truth for what a member actually ran with**, because they are printed after `SNESGetTolerances`/`KSPGetTolerances` have read the effective values back from PETSc (`solver.F90:522-529`) and therefore include command-line overrides. Prefer them over re-parsing the deck.

Caution: `inftolres` and `inftolupd` will print as `-999` when never set — that is the uninitialised sentinel, meaning "inactive", not a real tolerance.

---

## 8. Uncertainty and limits

- **The layering in §3 was traced for RICHARDS and, at the read-side, for GENERAL, TH, SCO2, HYDRATE, RT and NWT.** The overwrite order inside `ConvergenceTest` is common to all of them, but each PM's own `CheckConvergence` differs and only Richards' was read line by line.
- **`newton_inf_rel_update_tol` and `newton_inf_scaled_res_tol` exist as `solver_type` fields** (`solver.F90:34-35`) and are printed (`solver.F90:1481-1484`), but I found **no card in `SolverReadNewtonSelectCase` that writes them** — the deck-level `ITOL_RELATIVE_UPDATE` / `ITOL_SCALED_RESIDUAL` cards write the *process model's* fields instead. Treat these two solver fields as vestigial at this commit.
- **`INITIALIZE_TO_STEADY_STATE` / `RUN_AS_STEADY_STATE` are disabled** (`timestepper_base.F90:304-311`).
- **PETSc version behaviour is not statically knowable from this tree.** `PETSC_DEFAULT_REAL` / `PETSC_DEFAULT_INTEGER` resolve to whatever the linked PETSc uses, so the numeric defaults for `ATOL`/`RTOL`/`DTOL`/`MAXIMUM_NUMBER_OF_ITERATIONS` cannot be stated here. Read them from the run's own `Newton Solver` / `Linear Solver` echo (§7).
- **Command-line PETSc options cannot be recovered from the deck.** If ensemble members were launched with differing `-flow_*` flags, only the §7 echo will show it.
- `solver_cpr.F90` (the CPR two-stage preconditioner) and `solver.F90:1515-1594` (`SolverCheckCommandLine`) were not analysed in depth.
