**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** process-model couplers — the FLOW/TRAN hierarchy, per-timestep sequencing, and the end-of-run summary (`pmc_base.F90`, `pmc_subsurface.F90`, `pm_base.F90`, `factory_subsurface_linkage.F90`, `simulation_subsurface.F90`)
**Last verified:** 2026-07-31

---

# Process-Model Coupling

## 0. What this document is

This describes **how PFLOTRAN sequences flow and transport inside a timestep**, and **where every line of the end-of-run summary comes from**. The audience is an agent that must attribute cost — "transport is 79% of my wall clock, why?" — or reason about whether a flow failure could have been caused by transport, or vice versa.

Companions: `timestepping_and_cuts.md` (adaptive `dt`, cuts, wasted iterations) and `newton_and_linear_solvers.md` (convergence and the `NUMERICAL_METHODS` block).

**PETSc symbols** (`PetscTime`, `PetscLogStagePush/Pop`, `SNESSolve`) are external framework and labelled as such.

**Out of scope by instruction:** the application-specific process models `pm_well.F90`, `pm_waste_form.F90`, `pm_wipp_srcsink.F90` and their couplers. Geomechanics and geophysics couplers are named for completeness only.

---

## 1. The two abstractions

PFLOTRAN separates **what is solved** from **when it is solved**:

- **`pm_base_type`** (`pm_base.F90:17-71`) — a *process model*. Owns a `solver`, a `solution_vec`, a `residual_vec`, a `realization_base`, and a `next` pointer forming a linked list. It supplies the physics hooks the timestepper calls: `InitializeTimestep`, `PreSolve`, `Residual`, `Jacobian`, `PostSolve`, `AcceptSolution`, `CheckConvergence`, `CheckUpdatePre`, `CheckUpdatePost`, `TimeCut`, `UpdateSolution`, `FinalizeTimestep`, `UpdateTimestep` (`pm_base.F90:32-70`).
- **`pmc_base_type`** (`pmc_base.F90:27-71`) — a *process-model coupler*. Owns exactly one `timestepper`, one `pm_list` (the head of a PM linked list), a `waypoint_list`, a `cumulative_time` accumulator, and — critically — a **`child`** and a **`peer`** pointer (`pmc_base.F90:37-38`).

`child` and `peer` are what encode the coupling topology. There is no "coupling scheme" enum; the topology *is* the scheme.

---

## 2. The subsurface topology: transport is a child of flow

### 2.1 Construction

`FactSubLinkAddPMCSubsurfFlow` creates the flow coupler, names its timestepper `'FLOW'` (`factory_subsurface_linkage.F90:408`), stamps its solver `FLOW_CLASS` (`:414`), and makes it the head of the coupler list:

```fortran
simulation%flow_process_model_coupler => pmc_subsurface          ! :418
simulation%process_model_coupler_list => &
  simulation%flow_process_model_coupler                          ! :419-420
```

`FactSubLinkAddPMCSubsurfTran` then creates the transport coupler, names its timestepper `'TRAN'` (`factory_subsurface_linkage.F90:499`), stamps its solver `TRANSPORT_CLASS` (`:501`), and attaches it:

```fortran
if (.not.associated(simulation%process_model_coupler_list)) then
  simulation%process_model_coupler_list => pmc_subsurface         ! :510
else
  call PMCBaseSetChildPeerPtr(pmc_subsurface%CastToBase(),PM_CHILD, &
                    simulation%flow_process_model_coupler%CastToBase(), &
                    pmc_dummy,PM_INSERT)                          ! :512-514
endif
```

**So in a coupled flow+transport run, the transport coupler is the *child* of the flow coupler.** Transport-only runs put transport at the head instead.

The head coupler is marked master: `simulation%process_model_coupler_list%is_master = PETSC_TRUE` (`factory_subsurface.F90:141`). Only the master handles checkpointing and the wall-clock stop test (`pmc_base.F90:669-740`). Only the head coupler gets the output callback: `simulation%process_model_coupler_list%Output => Output` (`factory_subsurface.F90:401`); every other coupler leaves it null (`pmc_base.F90:165`), which is what the comment `! only print output for process models of depth 0` refers to (`pmc_base.F90:707`).

### 2.2 Timestepper selection per coupler

Flow (`factory_subsurface_linkage.F90:393-407`):

| Process model | Timestepper |
|---|---|
| `steady_state` | `TimestepperSteadyCreate()` (`:395`) |
| `pm_richards_ts_type`, `pm_th_ts_type` | `TimestepperTSCreate()` (`:398`, `:400`) |
| `pm_pnf_type` | `TimestepperKSPCreate()` (`:402`) |
| everything else | `TimestepperSNESCreate()` (`:404`) |

Transport (`factory_subsurface_linkage.F90:479-495`):

| Process model | Timestepper |
|---|---|
| `steady_state` | `TimestepperSteadyCreate()` (`:483`) |
| `pm_rt_type` with `operator_split` | `TimestepperKSPCreate()` (`:489`) |
| `pm_rt_type` otherwise | `TimestepperSNESCreate()` (`:491`) |
| `pm_nwt_type` | `TimestepperSNESCreate()` (`:493`) |

The coupler class likewise switches: operator-split RT gets `PMCSubsurfaceOSRTCreate()` rather than `PMCSubsurfaceCreate()` (`factory_subsurface_linkage.F90:466-470`), which replaces `StepDT` entirely (`pmc_subsurface_osrt.F90:20`).

**Diagnostic use:** the `TS SNES` vs `TS KSP` tag in the end-of-run summary tells you which branch of these tables the run took, without reading the deck.

---

## 3. Sequencing within a timestep

### 3.1 The coupler loop

`PMCBaseRunToTime(this, sync_time, stop_flag)` (`pmc_base.F90:549-758`) is recursive. Structure, with line numbers:

```
if (stop_flag == TS_STOP_FAILURE) return                              :580
PetscLogStagePush(this%stage)                                         :583   (PETSc)
call this%GetAuxData()                                                :589
loop:
  exit if local_stop_flag /= TS_CONTINUE                              :593
  exit if this%timestepper%target_time >= sync_time                   :594
  SetOutputFlags(this)                                                :596
  this%timestepper%SetTargetTime(sync_time, ...)                      :607
  this%StepDT(local_stop_flag)                     <-- SOLVE          :614
  if (time_step_cut_flag) clear all four I/O flags                    :616-624
  exit if local_stop_flag == TS_STOP_FAILURE                          :625
  for each pm in pm_list:
      option%time = timestepper%target_time                           :633
      cur_pm%UpdateSolution()                                         :634
      this%timestepper%UpdateDT(cur_pm)                               :635
  call this%AccumulateAuxData()                                       :640
  if (associated(this%child)):
      call this%SetAuxData()                                          :645
      call this%child%RunToTime(this%timestepper%target_time, ...)     :646  <-- CHILD
      call this%GetAuxData()                                          :648
  ...timestep-modulus output/checkpoint flags                         :651-676
  if (associated(this%peer) .and. <sync or output or checkpoint>):
      call this%peer%RunToTime(this%timestepper%target_time, ...)      :700  <-- PEER
  if (associated(this%Output)) call this%Output(...)                   :708-716
  if (this%is_master): checkpoints, wallclock stop, steady-state stop  :718-740
end loop
call this%SetAuxData()                                                :745
if (peer .and. .not.peer_already_run_to_time) peer%RunToTime(sync_time):748-750
stop_flag = max(stop_flag,local_stop_flag)                            :752
PetscLogStagePop()                                                    :755   (PETSc)
```

### 3.2 What this means for flow and transport

The essential fact is line `:646`: **the child's `RunToTime` is called with the parent's just-completed `target_time` as its own sync time.**

Concretely, per outer iteration:

1. FLOW takes **one** timestep (`:614`).
2. FLOW updates its solution and proposes its next `dt` (`:629-637`).
3. FLOW hands its state to TRAN via `SetAuxData` (`:645`).
4. **TRAN then runs its own inner loop until it catches up** to FLOW's new time (`:646`, and TRAN's own `exit if target_time >= sync_time` at `:594`). That inner loop can take **any number of transport steps**, each with its own `SetTargetTime` / `StepDT` / `UpdateDT`.
5. FLOW reads back whatever TRAN produced (`:648`).

**This is sequential (loosely coupled) operator splitting at the coupler level, one-way per outer step: flow → transport.** There is no outer iteration to convergence between the two. The source acknowledges the limitation directly: `! Still need code to force all process models to use the same time step size if tightly or iteratively coupled.` (`pmc_base.F90:627-628`).

Consequences an agent must internalise:

- **The FLOW and TRAN step counts are independent and need not match.** TRAN having *more* steps than FLOW (7139 vs 5132 in the reference run) is normal and simply means transport's own governors and CFL limit chose smaller steps than flow's.
- **A transport failure aborts the whole simulation.** `local_stop_flag` from the child is propagated up by `stop_flag = max(stop_flag, local_stop_flag)` (`:752`), and `TS_STOP_FAILURE = 4` dominates every other flag. There is no "continue flow without transport" path.
- **A flow failure never gets to transport for that step**, because `:625` exits before `:646`.
- **Transport cannot influence the flow timestep.** `UpdateDT` for FLOW happens at `:635`, before the child runs. Flow's `dt` is chosen with no knowledge of how hard transport found the interval.
- **Data crosses only through `GetAuxData`/`SetAuxData`/`AccumulateAuxData`** (`pmc_base.F90:1653-1699`, overridden in `pmc_subsurface.F90:632-667`). These are the only coupling channel; the two couplers otherwise share nothing but the `option` object.

### 3.3 Peers

A `peer` is a sibling run at the same level (`pmc_base.F90:397-412`). Unlike a child, a peer is **not** run every step: it is invoked mid-loop only if `force_synchronized_output` is set *and* this step is a sync/output/checkpoint step (`pmc_base.F90:679-705`); otherwise it is run once at the end for the whole `sync_time` interval (`:748-750`). The subsurface flow/transport pair does not use this path.

### 3.4 The inner solve

`PMCBaseStepDT` (`pmc_base.F90:777-797`) is thin:

```fortran
call PetscTime(log_start_time,ierr)                                   ! :791  (PETSc)
call this%PrintHeader()                                               ! :792
call this%timestepper%StepDT(this%pm_list,stop_flag)                  ! :793
call PetscTime(log_end_time,ierr)                                     ! :794  (PETSc)
this%cumulative_time = this%cumulative_time + log_end_time - log_start_time  ! :795
```

**Note carefully what `cumulative_time` measures.** It brackets only `timestepper%StepDT`. The child's `RunToTime` is called at `:646`, *outside* this bracket. Therefore:

> **A coupler's `Total Time` is that coupler's own work only. It does not include its child's.**

So FLOW's `Total Time` and TRAN's `Total Time` are disjoint and can be compared directly, and their sum plus setup/output/IO should approximate the wall clock. This is exactly how one derives "transport is 79% of the run".

Inside `StepDT`, the per-timestep sequence for the SNES stepper is (`timestepper_SNES.F90:376-435`): `InitializeTimestep()` once, then a retry loop of `PreSolve()` → PETSc `SNESSolve` → accept-or-cut, then after the loop `PostSolve` is *not* called by the SNES stepper (the KSP stepper does call it, `timestepper_KSP.F90:312`), and finally `FinalizeTimestep()` (`timestepper_SNES.F90:486`).

---

## 4. The end-of-run summary

### 4.1 Where it is printed

`SimSubsurfFinalizeRun` (`simulation_subsurface.F90:840-939`) drives the whole thing:

1. If `stop_flag /= TS_STOP_END_SIMULATION`, print the reason (`:870-884`) — see `timestepping_and_cuts.md` §3.4.
2. `PetscLogStagePop` then push `FINAL_STAGE` (`:886-889`) — PETSc logging.
3. `this%process_model_coupler_list%FinalizeRun()` (`:892`) — the recursive per-coupler report.
4. Regression output, if the stop flag was clean (`:911-921`).
5. `SimulationBaseFinalizeRun(this)` → stops the timer (`:925`, `simulation_base.F90:207`).
6. `SimulationBaseWriteTimes(this, fid_out)` (`:927`) — the `Wall Clock Time` line.

### 4.2 The per-coupler block

`PMCBaseFinalizeRun` (`pmc_base.F90:830-871`) recurses **timestepper → PM list → child → peer** (`:855-869`), printing for each coupler:

```
<coupler name>                                          ! pmc_base.F90:849-850
 Total Time: <es12.4> seconds                           ! pmc_base.F90:851-853
```

then delegating to `this%timestepper%FinalizeRun(this%option)` (`:856`), which for the SNES stepper emits (`timestepper_SNES.F90:1061-1079`):

```
 <NAME> TS SNES steps = <n>  newton = <n>  linear = <n>  cuts = <n>
 <NAME> TS SNES Wasted Linear Iterations = <n>
 <NAME> TS SNES Wasted Newton Iterations = <n>
 <NAME> TS SNES time = <f12.1> seconds
```

where `<NAME>` is `'FLOW'` or `'TRAN'` from §2.1. The KSP stepper emits the analogous `TS KSP` block without the Newton lines (`timestepper_KSP.F90:834-848`); the base class (`timestepper_base.F90:1196-1214`) emits a `TS Base steps / cuts` and `TS Base time` pair and additionally writes directly to `stdout` when `OptionPrintToScreen` is true (`:1196-1204`).

**Because the recursion is parent-then-child, the FLOW block always precedes the TRAN block in the output.** Ordering alone identifies the hierarchy.

### 4.3 The wall clock

`SimulationBaseWriteTimes` (`simulation_base.F90:213-243`):

```fortran
total_time = this%timer%GetCumulativeTime()                      ! :227
write(*,'(/," Wall Clock Time:", 1pe12.4, " [sec] ", &
  & 1pe12.4, " [min] ", 1pe12.4, " [hr]")') &
  total_time, total_time/60.d0, total_time/3600.d0               ! :230-234
```

printed to screen and, separately, to `fid_out` (`:236-240`). It is a simulation-object timer, so it covers setup, run, and finalisation — everything except process start-up before the timer began.

### 4.4 Worked attribution

For the reference run (64.5 min wall clock, transport 79%):

| Quantity | Source | Reading |
|---|---|---|
| `Wall Clock Time` 64.5 min | `simulation_base.F90:230` | whole process |
| TRAN coupler `Total Time` ≈ 51 min | `pmc_base.F90:851`, accumulated at `:795` | transport's own `StepDT` calls only |
| FLOW coupler `Total Time` | same, on the parent | flow's own `StepDT` calls only, **excludes transport** |
| `FLOW TS SNES time` | `timestepper_SNES.F90:1076-1078`, accumulated at `:389-391` | time inside PETSc `SNESSolve` only |
| `TRAN TS SNES time` | same | ditto |

The gap between a coupler's `Total Time` and its `TS SNES time` is everything `StepDT` does outside `SNESSolve`: `InitializeTimestep`, `PreSolve`, `FinalizeTimestep`, the residual/Jacobian assembly triggered *by* `SNESSolve` is inside, but the auxvar updates around it are not. **A large `Total Time` − `TS SNES time` gap points at per-step setup cost (typically geochemistry auxvar updates for RT), not at the linear algebra.** Combined with TRAN's low linear-per-Newton ratio (~2.4, see `newton_and_linear_solvers.md` §5.3), that is where a transport-dominated run of this shape should be investigated first.

---

## 5. Screen/file print throttling

`SetOutputFlags` (`pmc_base.F90:875-913`) is called at the top of every coupler iteration (`:596`) and gates *all* `PrintMsg` output for that step:

- to screen, only if `mod(timestepper%steps, output_option%screen_imod) == 0` (`:897`);
- to file, only if `mod(timestepper%steps, output_option%output_file_imod) == 0` (`:907`).

**This is a per-coupler, per-step gate keyed on that coupler's own step counter.** Two implications for log forensics:

1. With `screen_imod > 1`, the convergence lines and `-> Cut time step:` messages of skipped steps are **silently absent**. A log with no cut messages is not proof of no cuts — check the `cuts` figure in the summary instead.
2. FLOW and TRAN have independent step counters, so their messages are throttled independently and can interleave unevenly.

---

## 6. Coupler classes present at this commit

Verified from `ls src/pflotran/pmc_*.F90`:

| File | Class | Role |
|---|---|---|
| `pmc_base.F90` | `pmc_base_type` | the recursive machinery described above |
| `pmc_subsurface.F90` | `pmc_subsurface_type` | subsurface flow and transport; owns solver setup incl. `SNESSetConvergenceTest` (`:303`, `:476`, `:619`) |
| `pmc_subsurface_osrt.F90` | `pmc_subsurface_osrt_type` | operator-split reactive transport; replaces `StepDT` entirely (`:20`, body at `:144-438`) |
| `pmc_linear.F90` | `pmc_linear_type` | extends `pmc_subsurface_type` with a linear-only solver setup (`:16-22`) |
| `pmc_general.F90` | `pmc_general_type` | wraps a single PM with its own `RunToTime`; has an `evaluate_at_end_of_simulation` flag (`:15-19`) |
| `pmc_third_party.F90` | `pmc_third_party_type` | external-driver coupling (`:16-24`) |
| `pmc_geomechanics.F90` | — | geomechanics; **not analysed here** |
| `pmc_geophysics.F90` | — | geophysics; **not analysed here** |

---

## 7. Uncertainty and limits

- **`PMCSubsurfaceOSRTStepDT` (`pmc_subsurface_osrt.F90:144-438`) was not read line by line.** It maintains its own `sum_newton_iterations`, `sum_linear_iterations`, `sum_wasted_linear_iterations`, `num_kinetic_state_updates` and `icut` locals (`:198-206`), so operator-split runs report through a different code path than the one documented in `timestepping_and_cuts.md` §4. Do not assume the wasted-iteration semantics carry over unchanged.
- **The aux-data contract is not documented here.** `GetAuxData`/`SetAuxData`/`AccumulateAuxData` are the whole flow↔transport interface, but their contents are physics (`pmc_subsurface.F90:632-667`) and belong in the flow/transport topics.
- **Whether transport actually sub-cycles depends on the deck.** The mechanism at `pmc_base.F90:646` permits any number of child steps per parent step; whether it does so is decided by transport's own governors, `CFL_GOVERNOR`, and `MAXIMUM_TIMESTEP_SIZE`. Compare the two `steps` figures in the summary to find out for a given run.
- **`Total Time` is measured with PETSc's `PetscTime` on the calling rank**; it is a wall-clock reading, not an MPI-reduced maximum. On a badly load-balanced run the reported number reflects the I/O rank only.
- **The recursion order in `PMCBaseFinalizeRun` is parent → own PM list → child → peer.** With deeper hierarchies (well models, waste forms — out of scope here) the summary ordering becomes harder to map back to the topology than the simple two-level FLOW/TRAN case described in §4.2.
