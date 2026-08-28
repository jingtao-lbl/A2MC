**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** timestep control, timestep cuts, and the end-of-run iteration summary (`timestepper_base.F90`, `timestepper_SNES.F90`, `timestepper_KSP.F90`, the `UpdateTimestep` methods on the process models)
**Last verified:** 2026-07-31

---

# Timestep Control and Timestep Cuts

## 0. What this document is

This describes **how PFLOTRAN chooses the next `dt`, when it throws a step away, and what it prints about that afterwards**. The audience is an agent that must look at a finished (or hung) run and answer two questions:

1. Did this ensemble member **fail**, or did it merely **struggle**?
2. If it struggled, **what** was throttling it?

Companion files in this directory:

- `newton_and_linear_solvers.md` — what "converged" means, PFLOTRAN's own tolerances vs PETSc's, and the `NUMERICAL_METHODS` block layout.
- `process_model_coupling.md` — how FLOW and TRAN are sequenced, and where the wall-clock summary comes from.

**Citation convention.** Every substantive claim carries a `(src/pflotran/<file>.F90:NNN)` citation read from the source at commit `157a26f7`. This tree is **not** current master; line numbers are valid only here. `SNESSolve`, `KSPSolve`, `SNESGetIterationNumber`, `SNESGetLinearSolveIterations`, `SNESGetConvergedReason` are **external PETSc** symbols and are labelled as such.

**These are run-control knobs, not calibration knobs.** Nothing in this document changes the physics being solved. Changing `MAX_TS_CUTS` or `TIMESTEP_MAXIMUM_GROWTH_FACTOR` changes cost and robustness, and can change the *discretization* error of the answer, but it does not change a model parameter. Treat every card in §7 as a numerical setting to be held fixed across an ensemble unless you are deliberately studying solver behaviour.

---

## 1. Executive summary

1. There are **four timestepper classes**, all extending `timestepper_base_type`: `timestepper_SNES` (implicit nonlinear, the normal case), `timestepper_KSP` (linear-only, used for operator-split transport and for the PNF flow mode), `timestepper_TS` (PETSc `TS` integrator), and `timestepper_steady`. Files: `timestepper_base.F90`, `timestepper_SNES.F90`, `timestepper_KSP.F90`, `timestepper_TS.F90`, `timestepper_steady.F90`.
2. **The next `dt` is proposed by the process model, not by the timestepper.** `TimestepperSNESUpdateDT` delegates to `process_model%UpdateTimestep(...)` (`timestepper_SNES.F90:281-288`). Each flow/transport mode implements its own growth rule.
3. **A cut happens when the solver attempt is rejected**, i.e. `snes_reason <= 0` or the process model's `AcceptSolution()` returns false (`timestepper_SNES.F90:402`). The step is retried at `time_step_reduction_factor * dt`.
4. **Exceeding `MAX_TS_CUTS` terminates the whole simulation.** It does **not** skip the step and continue. See §3.3 — this is the single most important fact for classifying an ensemble member.
5. **"Wasted" iterations are the iterations spent inside `SNESSolve` calls that were subsequently thrown away by a cut.** They are a *subset* of the reported `newton` / `linear` totals, not an addition to them (§4).
6. `MAX_TS_CUTS` counts **consecutive cuts within one timestep**, and resets to zero at the top of every step (`timestepper_SNES.F90:371`). The run-summary `cuts` figure is the lifetime total, a different quantity.

---

## 2. Choosing the next `dt`

### 2.1 The two-stage pipeline

Per timestep, `PMCBaseRunToTime` calls, in order:

1. `this%timestepper%SetTargetTime(...)` (`pmc_base.F90:607`) — clips the *already-chosen* `dt` so the step lands exactly on waypoints, sync times, and `dt_max` boundaries.
2. `this%StepDT(local_stop_flag)` (`pmc_base.F90:614`) — actually solves, cutting internally if needed.
3. `this%timestepper%UpdateDT(cur_pm)` (`pmc_base.F90:635`) — proposes the `dt` for the *next* step.

So `dt` for step *n+1* is set at the end of step *n* by `UpdateDT`, then trimmed at the start of step *n+1* by `SetTargetTime`.

### 2.2 `UpdateDT`: the growth rule

`TimestepperBaseUpdateDT` is a stub that errors out (`timestepper_base.F90:462-463`); the SNES stepper overrides it.

`TimestepperSNESUpdateDT` (`timestepper_SNES.F90:238-310`) does three things:

- **Post-cut freeze.** If the last step was cut, `num_constant_time_steps` is set to 1 (`timestepper_SNES.F90:261-262`) and thereafter incremented. While `0 < num_constant_time_steps <= constant_time_step_threshold`, `update_time_step` is forced false (`timestepper_SNES.F90:273-279`), meaning **`dt` is held constant and is not allowed to grow for `NUM_STEPS_AFTER_TS_CUT` steps after a cut** (default 5, `timestepper_base.F90:161`).
- **Delegation.** It calls `process_model%UpdateTimestep(update_time_step, dt, dt_min, dt_max, iaccel, num_newton_iterations, tfac, time_step_max_growth_factor)` (`timestepper_SNES.F90:281-288`). Note `num_newton_iterations` here is the count from the **last successful** `SNESSolve` only (assigned at `timestepper_SNES.F90:449` after the cut loop exits), not the sum over retries.
- **Rescue mode**, if enabled (§2.5).

### 2.3 What a process model does with it — Richards (single-governor form)

`PMRichardsUpdateTimestep` (`pm_richards.F90:329-390`):

```
if (num_newton_iterations >= iacceleration) then
  fac = 0.33 ; ut = 0
else
  up = pressure_change_governor / (max_pressure_change + 0.1)
  ut = up
endif
dtt = fac * dt * (1 + ut)                     ! pm_richards.F90:359-368
dtt = min(time_step_max_growth_factor*dt,dtt) ! pm_richards.F90:381
if (dtt > dt_max) dtt = dt_max                ! pm_richards.F90:382
dtt = max(dtt,dt_min)                         ! pm_richards.F90:386
```

with `fac = 0.5` in the easy branch (`pm_richards.F90:360`). Read this carefully:

- If the last solve needed **`iaccel` or more Newton iterations**, the proposal is `0.33 * dt` — an **unconditional shrink**, even though the solve converged. `iaccel` defaults to 5 (`timestepper_SNES.F90:129`) and is set by `TS_ACCELERATION` (`timestepper_SNES.F90:184-186`).
- Otherwise the proposal is `0.5 * dt * (1 + governor/actual_change)`. Growth requires `governor > actual_change`; the break-even point is `up = 1`, i.e. the actual pressure change equalling the governor.
- The result is then hard-capped by `TIMESTEP_MAXIMUM_GROWTH_FACTOR * dt` and by `dt_max`.

**Consequence for a deck that sets `PRESSURE_CHANGE_GOVERNOR 1.d8`**: `up` becomes enormous, so the governor term never binds and `dt` grows at exactly `TIMESTEP_MAXIMUM_GROWTH_FACTOR` per step — *unless* the Newton count reaches `iaccel`, in which case the `0.33 *` branch fires and the step shrinks regardless of the governor. A deck that disables the pressure governor is therefore still throttled, just by Newton count instead of by physics.

Finally, `RealizationLimitDTByCFL(this%realization, this%cfl_governor, dt, dt_max)` is called unconditionally (`pm_richards.F90:389`) but is a no-op unless `CFL_GOVERNOR` was set, since the body is wrapped in `if (Initialized(cfl_governor))` (`realization_subsurface.F90:2722`).

### 2.4 The multi-governor form — GENERAL

`PMGeneralUpdateTimestep` (`pm_general.F90:851-969`) takes the **minimum** over four governor ratios:

```
up   = pressure_change_governor    / (max_pressure_change    + 0.1)
ut   = temperature_change_governor / (max_temperature_change + 1.d-5)
ux   = xmol_change_governor        / (max_xmol_change        + 1.d-5)
us   = saturation_change_governor  / (max_saturation_change  + 1.d-5)
umin = min(up,ut,ux,us)                       ! pm_general.F90:901-905
dt   = min(growth_factor*dt, fac*(1+umin)*dt, tfac(ifac)*dt, dt_max)
                                              ! pm_general.F90:908-910
```

Crucially, GENERAL mode **prints which variable limited the step** when the governed branch wins (`pm_general.F90:913-947`), emitting a line of the form

```
 Dt limited by <Pressure|Temperature|Mole Fraction|Saturation>: Val=..., Gov=..., Scale=...
```

(format assembled at `pm_general.F90:936-939`). **This is the highest-value diagnostic string in the whole timestepping subsystem** — if a GENERAL-mode run is slow, grep the output for `Dt limited by` and the answer is there. Richards mode does **not** emit an equivalent line.

### 2.5 Rescue mode (SNES stepper only)

`RESCUE_MODE` (`timestepper_SNES.F90:194`) opens a sub-block accepting `RESCUE_FACTOR`/`FACTOR`/`RFAC`, `RESCUE_FREQUENCY`/`FREQUENCY`/`RFREQ`, and `RESCUE_STEP_THRESHOLD`/`THRESHOLD`/`STEP_THRESHOLD`/`RTHRESH` (`timestepper_SNES.F90:207-221`). Defaults: off; factor `1.0d3`, frequency `100`, threshold `1.0d-5` (`timestepper_SNES.F90:141-145`).

Mechanism: each step where `target_time * rescue_step_threshold > dt` increments a counter; each step where it is not, decrements it (`timestepper_SNES.F90:292-299`). When the counter exceeds `rescue_frequency`, `dt` is multiplied by `rescue_factor` outright (`timestepper_SNES.F90:300-307`) and the message `rescue mode activated. jumping time step size.` is printed. This is a deliberate escape hatch from a stalled, ever-shrinking step; it is **off by default** and, if enabled, produces a step size that the governors did not sanction.

### 2.6 `SetTargetTime`: waypoint and sync clipping

`TimestepperBaseSetTargetTime` (`timestepper_base.F90:469-674`) walks the waypoint list and shortens `dt` so the step lands on the next waypoint or the parent coupler's `sync_time`. Points that matter for diagnosis:

- Each waypoint carries its own `dt_max`; `dt = min(dt, cur_waypoint%dt_max)` (`timestepper_base.F90:554-555`). This is how `MAXIMUM_TIMESTEP_SIZE ... AT <time>` becomes piecewise in time.
- A step that was shortened to hit a waypoint or a sync time sets `revert_dt`, so the *following* step restores `min(prev_dt, dt_max)` rather than continuing from the artificially small value (`timestepper_base.F90:532-536`, flags set at `:646-651`). To stop this from deadlocking a nested coupler, the revert is abandoned after `MAX_NUM_CONTIGUOUS_REVERTS` consecutive sync-driven reverts (default 2, `timestepper_base.F90:188`).
- The overshoot test is `target_time + tolerance*dt >= cur_waypoint%time` where `tolerance` is `time_step_tolerance` (`timestepper_base.F90:581-583`), settable with `TIMESTEP_OVERSTEP_REL_TOLERANCE`, default `0.1` (`timestepper_base.F90:168`).
- If `steps >= max_time_step - 1`, `stop_flag` is set to `TS_STOP_MAX_TIME_STEP` (`timestepper_base.F90:657-660`). This is a **clean** stop, not a failure — see §5.

---

## 3. Timestep cuts

### 3.1 What triggers a cut

Inside the SNES stepper's retry loop (`timestepper_SNES.F90:378-435`):

```fortran
call SNESSolve(solver%snes,PETSC_NULL_VEC,process_model%solution_vec,ierr)   ! :384  (PETSc)
...
if (snes_reason <= 0 .or. .not. process_model%AcceptSolution()) then         ! :402
   ... call this%CutDT(process_model,icut,stop_flag,'snes',snes_reason,option)  ! :408
```

Two independent triggers:

- **`snes_reason <= 0`** — `snes_reason` comes from PETSc's `SNESGetConvergedReason` (`timestepper_SNES.F90:397`), but its value has usually been *overwritten* by PFLOTRAN's own convergence test (see `newton_and_linear_solvers.md` §3). Note `<= 0` catches `SNES_CONVERGED_ITERATING` (0) as well as every negative PETSc reason and PFLOTRAN's private codes `-88` (`CONVERGENCE_CUT_TIMESTEP`, `convergence.F90:216-217`), `-19` (out of EOS table, `convergence.F90:204-206`) and `-20` (residual exceeded `MAX_NORM`, `convergence.F90:259-261`).
- **`AcceptSolution()` false** — a process-model veto applied *after* a nominally converged solve. For subsurface flow and reactive transport this is a stub returning true (`pm_subsurface_flow.F90:886`, `pm_rt.F90:831`), so in practice it is other modes that use it.

For the linear (`timestepper_KSP`) stepper the analogous test is `ksp_reason <= 0 .or. .not. process_model%AcceptSolution()` (`timestepper_KSP.F90:279`), with `ksp_reason` from PETSc's `KSPGetConvergedReason` (`timestepper_KSP.F90:276`).

### 3.2 What a cut does

`TimestepperBaseCutDT` (`timestepper_base.F90:707-792`):

```fortran
icut = icut + 1                                          ! :733
this%time_step_cut_flag = PETSC_TRUE                     ! :734
...
this%target_time = this%target_time - this%dt            ! :774
this%dt = this%time_step_reduction_factor * this%dt      ! :776
```

and prints a line beginning ` -> Cut time step: ` followed by the reason tag (`'snes'` or `'ksp'`), the raw reason integer, `icut=`, the bracketed lifetime cut count, and the current `t=` and `dt=` (`timestepper_base.F90:778-790`). The caller then restores `target_time`, resets `option%dt`, and calls `process_model%TimeCut()` to roll the state back (`timestepper_SNES.F90:427-429`).

Side effect on output: `PMCBaseRunToTime` turns off **all four** I/O flags for that iteration when `time_step_cut_flag` is set (`pmc_base.F90:616-624`), because those flags were computed from the pre-cut target time. So **a cut suppresses the snapshot / observation / mass-balance / checkpoint output that the pre-cut step would have triggered**; the output is emitted on a later attempt that actually reaches the waypoint. A cut therefore never silently drops an output *time*, but it does mean the observed output cadence is not a reliable proxy for step count.

Note also `time_step_cut_flag` causes the next `SetTargetTime` to rewind the waypoint pointer to `prev_waypoint` (`timestepper_base.F90:518-526`).

### 3.3 Exceeding `MAX_TS_CUTS` — abort, not continue

This is the classification question. The code (`timestepper_base.F90:740-772`):

```fortran
if (icut > this%max_time_step_cuts .or. this%dt < this%dt_min) then
   ...print ' Stopping: Time step cut criteria exceeded.'                 ! :743
   ...print '    icut = <n>, max_time_step_cuts= <m>'                     ! :745-746
   ...or ' Stopping: Time step size is less than the minimum allowable'   ! :750-751
   process_model%output_option%plot_name = <pm name> // '_cut_to_failure' ! :762-764
   call Output(...)                                                       ! :768
   stop_flag = TS_STOP_FAILURE                                            ! :770
   return
endif
```

**The simulation terminates.** It does not abandon the step and move on. Propagation:

- `TimestepperSNESStepDT` returns immediately on `TS_STOP_FAILURE` (`timestepper_SNES.F90:425`); same in the KSP stepper (`timestepper_KSP.F90:290`).
- `PMCBaseRunToTime` exits its loop (`pmc_base.F90:625`) and every enclosing recursive `RunToTime` returns straight away (`pmc_base.F90:580`).
- `SimSubsurfExecuteRun` exits its waypoint loop and, because `stop_flag == TS_STOP_FAILURE`, **skips the final restart checkpoint** (`simulation_subsurface.F90:722-742` and the guard at `:737`).
- `SimSubsurfFinalizeRun` prints `Simulation failed.  Exiting!` and sets `this%driver%exit_code = EXIT_FAILURE` (`simulation_subsurface.F90:876-877`), where `EXIT_FAILURE = 88` (`pflotran_constants.F90:63`).
- `pflotran.F90` returns that through `call exit(iflag)` (`pflotran.F90:28-30`).

**So a member that blew through `MAX_TS_CUTS` exits with status 88, prints `Simulation failed.  Exiting!`, leaves a `<pmname>_cut_to_failure` snapshot file, and has no `-restart` checkpoint.** That is the unambiguous "failed" signature.

Two important details:

- The test is `icut > max_time_step_cuts`, and `icut` is incremented *before* the test (`timestepper_base.F90:733`). So `MAX_TS_CUTS 20` permits 20 cuts and fails on the 21st.
- `icut` is a local variable initialised to `0` at the top of every `StepDT` (`timestepper_SNES.F90:371`). **`MAX_TS_CUTS` is a per-timestep consecutive-cut budget**, consistent with its alias `MAXIMUM_CONSECUTIVE_TS_CUTS` (`timestepper_base.F90:279`). It is unrelated to the lifetime `cumulative_time_step_cuts` reported at the end of the run.
- The same block also fires on `dt < dt_min`, with a distinct message naming both `dt` and `dtmin`. If you see the `dt` / `dtmin` wording rather than the `icut` wording, the run collapsed to the floor rather than exhausting the cut budget.

### 3.4 Failed vs struggled: the decision rule

| Signal | Interpretation |
|---|---|
| Exit code 88 **and** `Simulation failed.  Exiting!` **and** a `*_cut_to_failure` file | **Failed.** Discard or re-run; the state is not physical at the reported end time. |
| ` Stopping: Time step cut criteria exceeded.` in the log | **Failed**, and specifically by cut budget. |
| ` Stopping: Time step size is less than the minimum allowable` | **Failed**, by `dt` collapse to `MINIMUM_TIMESTEP_SIZE`. |
| `Maximum timestep exceeded.  Exiting!` (`simulation_subsurface.F90:874`) | **Not a failure.** `MAX_STEPS` was hit; exit code stays 0 and a `-restart-max-ts` checkpoint is written (`simulation_subsurface.F90:729`). The run is *incomplete*, which is a different problem. |
| `Wallclock stop time exceeded.  Exiting!` (`simulation_subsurface.F90:872`) | **Not a failure.** Ran out of wall time; `-restart-max-wc` checkpoint written (`simulation_subsurface.F90:731`). |
| Nonzero `cuts` in the run summary, no stopping message, normal end | **Struggled but succeeded.** The answer is usable. |
| `Potential oscillatory convergence` warning (`pm_subsurface_flow.F90:868`) | Struggling: the flow PM detected the residual/solution norm triple repeating over its 7-deep history. Advisory only, does not stop anything. |

---

## 4. "Wasted Linear Iterations" and "Wasted Newton Iterations"

### 4.1 Where they are counted

Inside the SNES retry loop (`timestepper_SNES.F90:393-406`):

```fortran
call SNESGetIterationNumber(solver%snes,num_newton_iterations,ierr)      ! :393  (PETSc)
call SNESGetLinearSolveIterations(solver%snes,num_linear_iterations,ierr)! :395  (PETSc)
call SNESGetConvergedReason(solver%snes,snes_reason,ierr)                ! :397  (PETSc)

sum_newton_iterations = sum_newton_iterations + num_newton_iterations    ! :399
sum_linear_iterations = sum_linear_iterations + num_linear_iterations    ! :400

if (snes_reason <= 0 .or. .not. process_model%AcceptSolution()) then     ! :402
  sum_wasted_linear_iterations = sum_wasted_linear_iterations + num_linear_iterations  ! :403-404
  sum_wasted_newton_iterations = sum_wasted_newton_iterations + num_newton_iterations  ! :405-406
```

then accumulated into the lifetime counters at `timestepper_SNES.F90:438-447`.

### 4.2 Exact definition

> **A wasted Newton iteration is a Newton iteration that was executed inside a `SNESSolve` call whose result was then discarded and the timestep cut. A wasted linear iteration is a Krylov iteration executed inside such a call.**

Three consequences that are easy to get wrong:

1. **Wasted is a subset, not an addition.** Lines `:399-400` add to the totals *unconditionally*, before the rejection branch. So in a summary reading `newton 15404 ... Wasted Newton 1294`, the 1294 are 1294 *of the* 15404, not extra. The productive Newton count is `15404 - 1294 = 14110`.
2. **The granularity is a whole `SNESSolve`, not an individual iteration.** PETSc's `SNESGetLinearSolveIterations` returns the linear iterations for the entire nonlinear solve; PFLOTRAN charges all of them to "wasted" if that solve was rejected. It cannot attribute waste to a partial solve.
3. **It is not checkpointed.** `TimestepperSNESRegisterHeader` registers `cumulative_newton_iterations` and `cumulative_linear_iterations` but carries an explicit `! need to add cumulative wasted linear iterations` TODO and registers neither wasted counter (`timestepper_SNES.F90:563-571`). **A restarted run reports wasted counts only for the segment since restart.** The same applies to the HDF5 checkpoint path (`timestepper_SNES.F90:698-714`).

The KSP stepper tracks `cumulative_wasted_linear_iterations` in the same way (`timestepper_KSP.F90:280-282`) but has no Newton concept.

### 4.3 Where they are printed

`TimestepperSNESFinalizeRun` (`timestepper_SNES.F90:1039-1081`) emits exactly four lines per timestepper, each prefixed with the timestepper's `name`:

```
 <NAME> TS SNES steps = <n>  newton = <n>  linear = <n>  cuts = <n>     ! :1062-1066
 <NAME> TS SNES Wasted Linear Iterations = <n>                          ! :1068-1070
 <NAME> TS SNES Wasted Newton Iterations = <n>                          ! :1072-1074
 <NAME> TS SNES time = <f12.1> seconds                                  ! :1076-1078
```

`name` is `'FLOW'` or `'TRAN'`, assigned when the couplers are built (`factory_subsurface_linkage.F90:408` and `:499`). The KSP stepper prints the analogous `TS KSP steps / linear / cuts`, `TS KSP Wasted Linear Iterations`, `TS KSP time` (`timestepper_KSP.F90:834-848`); note it has **no** wasted-Newton line.

The `TS SNES time` figure is `cumulative_solver_time`, accumulated only around the `SNESSolve` call itself (`timestepper_SNES.F90:382-391`). It excludes residual/Jacobian setup outside `SNESSolve`, output, and everything the coupler does — so it will be noticeably smaller than the PMC "Total Time" (see `process_model_coupling.md` §4).

### 4.4 Reading a real summary

For the reference run:

```
FLOW TS SNES steps 5132, newton 15404, linear 537044, cuts 168,
     Wasted Linear Iterations 29057, Wasted Newton 1294
TRAN TS SNES steps 7139, newton 22432, linear 54684, cuts 0
```

Derived facts, all from the definitions above:

- **The run did not fail.** `cuts` alone never implies failure; only the `Stopping:` messages plus exit code 88 do.
- **FLOW waste is 5.4% of linear work and 8.4% of Newton work.** That is real but not pathological. 168 cuts over 5132 steps is roughly one cut per 30 steps.
- **The expensive part is the linear solve inside FLOW, not the cuts.** 537044 linear iterations over 15404 Newton iterations is ~35 Krylov iterations per Newton step. That is a preconditioner-quality problem, not a timestepping problem — see `newton_and_linear_solvers.md` §5.
- **TRAN has zero cuts but 79% of the wall clock.** With 7139 steps against FLOW's 5132, TRAN is taking *more* steps than FLOW despite being the child coupler (`process_model_coupling.md` §2), and only ~2.4 Krylov iterations per Newton step. Its cost is therefore in the sheer number of `SNESSolve` calls and in the per-step residual/Jacobian assembly, not in the linear algebra and not in retries. Tuning `MAX_TS_CUTS 50` on TRAN was inert — TRAN never cut once.
- The deck's `MINIMUM_NEWTON_ITERATIONS 1` guarantees at least one Newton iteration per solve (`newton_and_linear_solvers.md` §3.4); with 22432 Newton over 7139 TRAN steps (~3.1 each), that floor is not what is driving cost.

---

## 5. Stop flags

Defined in `timestepper_base.F90:16-20`:

| Constant | Value | Meaning | Failure? |
|---|---|---|---|
| `TS_CONTINUE` | 0 | keep stepping | no |
| `TS_STOP_END_SIMULATION` | 1 | reached final waypoint | no |
| `TS_STOP_MAX_TIME_STEP` | 2 | `MAX_STEPS` reached (`timestepper_base.F90:659`) | no |
| `TS_STOP_WALLCLOCK_EXCEEDED` | 3 | projected next step would exceed the wallclock budget (`pmc_base.F90:732-734`) | no |
| `TS_STOP_FAILURE` | 4 | cut budget or `dt_min` breached (`timestepper_base.F90:770`) | **yes** |

The wallclock projection is deliberately conservative: `TimestepperBaseWallClockStop` doubles the running average step time before comparing against `option%wallclock_stop_time` (`timestepper_base.F90:1110-1113`).

---

## 6. Where the ELM/CLM-style intuitions break

- **There is no fixed model timestep.** Every step size is adaptive. Comparing two ensemble members by step index is meaningless; compare by simulated time.
- **`dt` shrinks on *success* too.** The `num_newton_iterations >= iacceleration` branch shrinks the step even though the solve converged (`pm_richards.F90:361-363`). A run can be slow with zero cuts.
- **Governor units are physical and mode-specific.** `PRESSURE_CHANGE_GOVERNOR` is read by a bare `InputReadDouble` with no unit conversion (`pm_subsurface_flow.F90:226`), so it is in Pa. `TIMESTEP_*` sizes, by contrast, *do* go through `InputReadAndConvertUnits` with internal units `'sec'` (`timestepper_base.F90:268`, `:288-289`).
- **Some modes reject the governors outright.** `WIPP_FLOW` errors on `PRESSURE_CHANGE_GOVERNOR`, `TEMPERATURE_CHANGE_GOVERNOR`, and `CONCENTRATION_CHANGE_GOVERNOR` (`pm_wipp_flow.F90:1039-1040`); `ZFLOW` errors on `TEMPERATURE_CHANGE_GOVERNOR` (`pm_zflow.F90:440`). A card being spelled correctly does not mean it is legal in the active mode.
- **`INITIALIZE_TO_STEADY_STATE` and `RUN_AS_STEADY_STATE` are disabled** at this commit — both print an error and stop (`timestepper_base.F90:304-311`). Do not put them in a deck.

---

## 7. Card table — timestepper

All cards below live inside `NUMERICAL_METHODS <FLOW|TRANSPORT>` → `TIMESTEPPER` (see `newton_and_linear_solvers.md` §1). **These are run-control settings, not calibration parameters.**

### 7.1 Read by the timestepper base class (`timestepper_base.F90`, all modes)

| Keyword | Source line | Default (line) | Effect |
|---|---|---|---|
| `MAX_STEPS` / `MAXIMUM_NUMBER_OF_TIMESTEPS` | `:276` | `999999` (`:157`) | Stop cleanly with `TS_STOP_MAX_TIME_STEP` once `steps >= MAX_STEPS-1`. |
| `MAX_TS_CUTS` / `MAXIMUM_CONSECUTIVE_TS_CUTS` | `:279` | `16` (`:158`) | Consecutive cuts allowed **within one step**. Exceeding it aborts the run (§3.3). |
| `TIMESTEP_REDUCTION_FACTOR` | `:295` | `0.5` (`:159`) | Multiplier applied to `dt` on each cut. |
| `TIMESTEP_MAXIMUM_GROWTH_FACTOR` | `:298` | `2.0` (`:160`) | Hard ceiling on step-to-step growth, applied inside each PM's `UpdateTimestep`. |
| `NUM_STEPS_AFTER_TS_CUT` | `:272` | `5` (`:161`) | Steps after a cut during which `dt` is frozen (no growth). |
| `INITIAL_TIMESTEP_SIZE` | `:285` | `1.0 s` (`:22`, applied `:427`) | First `dt`. Unit token accepted, internal unit `sec`. |
| `MINIMUM_TIMESTEP_SIZE` | `:290` | `1.d-20 s` (`:23`, applied `:426`) | Floor. Dropping below it aborts the run (§3.3). |
| `MAXIMUM_TIMESTEP_SIZE [<dt>] [AT <time>]` | `:315` | none (waypoint `dt_max` init `0`, `waypoint.F90:88`) | Sets `dt_max`. With `AT`, creates a waypoint so `dt_max` is piecewise in time; the literal `AT` is required and anything else errors (`:330-334`). Values are filled forward through the waypoint list (`waypoint.F90:382-402`). |
| `MAX_NUM_CONTIGUOUS_REVERTS` | `:282` | `2` (`:188`) | Consecutive sync-driven `dt` reverts before the saved `prev_dt` is abandoned. |
| `TIMESTEP_OVERSTEP_REL_TOLERANCE` | `:301` | `0.1` (`:168`) | Relative slack when deciding a step "reaches" a waypoint. |
| `PRINT_EKG` | `:312` | off (`:189`) | Emit a machine-readable `TIMESTEP` record per step to the EKG unit (`timestepper_SNES.F90:488-497`). |
| `INITIALIZE_TO_STEADY_STATE` | `:304` | — | **Disabled**; errors out. |
| `RUN_AS_STEADY_STATE` | `:308` | — | **Disabled**; errors out. |

### 7.2 Read by the SNES timestepper (`timestepper_SNES.F90`)

| Keyword | Source line | Default (line) | Effect |
|---|---|---|---|
| `TS_ACCELERATION` | `:184` | `5` (`:129`) | `iaccel`. Newton counts `>= iaccel` force the shrink branch; `iaccel == 0` disables adaptive sizing entirely (guard `iacceleration /= 0`, e.g. `pm_richards.F90:357`); negative selects the `tfac`-ramp branch. |
| `DT_FACTOR` | `:188` | 13-entry ramp `2,2,2,2,2,1.8,1.6,1.4,1.2,1,1,1,1` (`:130-138`) | Per-Newton-count growth multipliers `tfac(ifac)`, `ifac = clamp(newton_count,1,size(tfac))`. |
| `RESCUE_MODE` (block) | `:194` | off (`:141`) | See §2.5. Sub-cards `RESCUE_FACTOR` (`1.0d3`), `RESCUE_FREQUENCY` (`100`), `RESCUE_STEP_THRESHOLD` (`1.0d-5`). |

### 7.3 Governor cards — read by the process model, inside the same `TIMESTEPPER` block

The coupler offers each `TIMESTEPPER` keyword to the process model **first**, and only falls through to the timestepper if the PM does not claim it (`pmc_base.F90:227-235`, with the comment `leave in this order as PM overrides TS`). The complete governor set at this commit:

| Keyword | Source line | Default (line) | Units | Applies to |
|---|---|---|---|---|
| `PRESSURE_CHANGE_GOVERNOR` | `pm_subsurface_flow.F90:225` | `5.d5` (`:126`) | Pa | all subsurface flow modes except WIPP_FLOW |
| `TEMPERATURE_CHANGE_GOVERNOR` | `pm_subsurface_flow.F90:229` | `5.d0` (`:127`) | °C | thermal flow modes; rejected by ZFLOW and WIPP_FLOW |
| `SATURATION_CHANGE_GOVERNOR` | `pm_subsurface_flow.F90:237` | `0.5d0` (`:128`) | — | multiphase modes |
| `CONCENTRATION_CHANGE_GOVERNOR` | `pm_subsurface_flow.F90:233` | `1.d0` (`:129`, field `xmol_change_governor`) | mole fraction | multiphase modes |
| `SALT_MASS_CHANGE_GOVERNOR` | `pm_subsurface_flow.F90:241` | `1.d1` (`:130`) | — | brine-capable modes |
| `CFL_GOVERNOR` (flow) | `pm_subsurface_flow.F90:245` | uninitialised → inactive (`:131`) | Courant number | caps `dt` at `CFL * dt_CFL=1` (`realization_subsurface.F90:2734-2739`) |
| `CFL_GOVERNOR` (transport) | `pm_rt.F90:318` | uninitialised → inactive | Courant number | same limiter, transport PM |
| `VOLUME_FRACTION_CHANGE_GOVERNOR` | `pm_rt.F90:321` | `1.d0` (`pm_rt.F90:154`) | volume fraction | reactive transport; **values `>= 1.d0` select the legacy non-governed branch** (`pm_rt.F90:861`) |

**That is the full list of `*_CHANGE_GOVERNOR` cards at commit `157a26f7`** (verified by `grep -rn "CHANGE_GOVERNOR" src/pflotran/*.F90`). Setting any of them to a very large number does not disable adaptive stepping; it only removes that one term from the `min`, leaving Newton count, `tfac`, `dt_max`, and `TIMESTEP_MAXIMUM_GROWTH_FACTOR` in control.

---

## 8. Uncertainty and limits of this document

- **`timestepper_TS.F90` (PETSc `TS`) is not analysed here.** It is selected only for `pm_richards_ts_type` / `pm_th_ts_type` (`factory_subsurface_linkage.F90:397-401`); its adaptivity is PETSc's, not PFLOTRAN's, and its `FinalizeRun` (`timestepper_TS.F90:605-637`) prints a different summary. Nothing above about cuts applies to it.
- **`timestepper_steady.F90` is likewise out of scope**; it does set `TS_STOP_FAILURE` at `timestepper_steady.F90:288`, so a steady solve can also fail the run, but the cut machinery does not apply.
- **Whether a given governor is honoured depends on the mode's `UpdateTimestep`.** I verified Richards (`pm_richards.F90`), GENERAL (`pm_general.F90`), and RT (`pm_rt.F90`). The other modes listed at `grep -rln "subroutine PM.*UpdateTimestep"` — `pm_th`, `pm_mphase`, `pm_hydrate`, `pm_sco2`, `pm_zflow`, `pm_pnf`, `pm_osrt`, `pm_nwt`, `pm_wipp_flow` — each have their own and were not read line by line for this document. Do not assume the Richards formula applies to them.
- **The step-limiting reason is not printed by most modes.** Only GENERAL emits `Dt limited by ...`. For Richards, the only way to attribute a small `dt` statically is to reason from the governor values and `TS_ACCELERATION`; there is no log line to read.
- **Wasted-iteration counts are not restart-safe** (§4.2, item 3). Any cross-member comparison must confirm the members were single-shot runs.
