**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** SIMULATION / CHECKPOINT and SIMULATION / RESTART
**Last verified:** 2026-07-31

# Checkpoint and Restart

Checkpoint files are **not** analysis output — they are opaque solver state used
to resume a run. They do not carry the mass-balance or observation time series.
An extraction layer should read `-mas.dat` / `.pft` / `.tec` / `.h5` snapshots,
not checkpoints. This page exists so that a calibration agent can (a) drive
restarts correctly and (b) recognize the failure modes.

---

## 1. The `CHECKPOINT` block

`CHECKPOINT` is a sub-block of `SIMULATION`, dispatched at exactly one place:

```fortran
      case('CHECKPOINT')
        option%checkpoint => OptionCheckpointCreate()
        ...
        call CheckpointRead(input,option,waypoint_list)
```
(`src/pflotran/factory_forward.F90:161-164`)

A grep for the literal `'CHECKPOINT'` across all `*.F90` finds no other dispatch
site — no `simulation_*.F90` handles it.

Parser: `CheckpointRead` (`src/pflotran/checkpoint.F90:1312-1469`). The complete
keyword set (all line refs into `src/pflotran/checkpoint.F90`):

| Keyword | Line | Effect |
|---|---|---|
| `PERIODIC TIME <v> <unit>` | `:1362`, `:1367-1380` | sets `tconv`, `tunit`, `periodic_time_incr` |
| `PERIODIC TIMESTEP <n>` | `:1381-1384` | sets `periodic_ts_incr` |
| `TIMES <unit> <list>` | `:1389-1425` | one waypoint per value with `print_checkpoint = PETSC_TRUE` (`:1420`) |
| `FORMAT BINARY` | `:1433-1434` | `format_binary = PETSC_TRUE` |
| `FORMAT HDF5` | `:1435-1436` | `format_hdf5 = PETSC_TRUE` |
| `TIME_UNITS <unit>` | `:1441-1443` | sets the default unit used in file names |

Anything else is a fatal error with the message
`'Must specify PERIODIC TIME, PERIODIC TIMESTEP, TIMES, or FORMAT'`
(`src/pflotran/checkpoint.F90:1446-1447`).

Format resolution at block close (`src/pflotran/checkpoint.F90:1459-1465`):

```fortran
  if (format_binary .and. format_hdf5) then
    checkpoint_option%format = CHECKPOINT_BOTH
  else if (format_hdf5) then
    checkpoint_option%format = CHECKPOINT_HDF5
  else ! default
    checkpoint_option%format = CHECKPOINT_BINARY
  endif
```

Constants `CHECKPOINT_BINARY = 1`, `CHECKPOINT_HDF5 = 2`, `CHECKPOINT_BOTH = 3`
(`src/pflotran/option_checkpoint.F90:11-13`). Defaults from
`OptionCheckpointInit` (`src/pflotran/option_checkpoint.F90:66-70`):
`tunit = ''`, `tconv = 0.d0`, `periodic_time_incr = UNINITIALIZED_DOUBLE`,
`periodic_ts_incr = 0`, `format = CHECKPOINT_BINARY`.

**`tconv` here is the reciprocal of the output-option `tconv`.** Checkpoint uses

```fortran
            checkpoint_option%tconv = 1.d0/units_conversion
```
(`src/pflotran/checkpoint.F90:1378`, and identically at `:1397`, `:1458`)

so it is *output units per second*, and file names multiply
(`temp_time = time * option%checkpoint%tconv`,
`src/pflotran/checkpoint.F90:117`). The `OUTPUT` block's `tconv` is *seconds per
output unit* and divides (`src/pflotran/factory_subsurface_read.F90:1816-1818`,
used as `option%time/output_option%tconv`). Do not assume they are the same
quantity.

### Triggering

- `PERIODIC TIME` → `CheckpointPeriodicTimeWaypoints`
  (`src/pflotran/checkpoint.F90:1473`) walks the increment up to the final time,
  inserting waypoints with `print_checkpoint = PETSC_TRUE` (`:1524-1527`);
  called once from `src/pflotran/factory_subsurface.F90:641`. Warns above 15000
  waypoints (`src/pflotran/checkpoint.F90:1499`, `:1510-1516`).
- `PERIODIC TIMESTEP` → modulus test after every step:
  ```fortran
      if (this%option%checkpoint%periodic_ts_incr > 0) then
        if (mod(this%timestepper%steps, &
                this%option%checkpoint%periodic_ts_incr) == 0) then
          checkpoint_at_this_timestep_flag = PETSC_TRUE
  ```
  (`src/pflotran/pmc_base.F90:670-673`)
- waypoint-driven checkpoints set `checkpoint_at_this_time_flag` in
  `SetTargetTime` (`src/pflotran/timestepper_base.F90:615`), and — like the
  output flags — that flag is **cleared if the timestep was cut**
  (`src/pflotran/pmc_base.F90:623`).

---

## 2. File names

Base name, no suffix (`src/pflotran/checkpoint.F90:85-87`):

```fortran
  CheckpointFilename = trim(option%global_prefix) // &
                       trim(option%group_prefix) // &
                       trim(adjustl(append_name))
```

Suffix added by the writer:

```fortran
  filename = CheckpointFilename(append_name,option)
  filename = trim(filename) // '.chk'
```
(`src/pflotran/checkpoint.F90:172-173`, `CheckpointOpenFileForWriteBinary`) and

```fortran
  filename = CheckpointFilename(append_name, option)
  filename = trim(filename) // '.h5'
```
(`src/pflotran/checkpoint.F90:548-549`, `CheckpointOpenFileForWriteHDF5`).

Append-name forms:

```fortran
  temp_time = time * option%checkpoint%tconv
  write(word,'(f15.4)') temp_time
  CheckpointAppendNameAtTime = '-' // trim(adjustl(word)) // &
                               trim(adjustl(option%checkpoint%tunit))
```
(`src/pflotran/checkpoint.F90:117-121`) → e.g. `pflotran-10.0000y.chk`

```fortran
  write(word,'(i9)') timestep
  CheckpointAppendNameAtTimestep = '-' // 'ts' // trim(adjustl(word))
```
(`src/pflotran/checkpoint.F90:147-148`) → e.g. `pflotran-ts100.h5`

Call sites: `src/pflotran/pmc_base.F90:723` (time) and `:728` (timestep).

End-of-run checkpoints use fixed literals
(`src/pflotran/simulation_subsurface.F90:730-738`):

```fortran
    select case(this%stop_flag)
      case(TS_STOP_MAX_TIME_STEP)
        append_name = '-restart-max-ts'
      case(TS_STOP_WALLCLOCK_EXCEEDED)
        append_name = '-restart-max-wc'
      case default ! TS_STOP_END_SIMULATION
        append_name = '-restart'
    end select
```

and are written **only if the run did not fail**
(`src/pflotran/simulation_subsurface.F90:729-730`). So a normally-completed run
leaves `pflotran-restart.chk` or `pflotran-restart.h5`; a run killed by the
wallclock limit leaves `pflotran-restart-max-wc.*`; a diverged run leaves
neither. That last case is the reliable signal that a calibration ensemble member
failed.

HDF5 checkpoints carry a top-level group literally named `"Checkpoint"`
(`src/pflotran/checkpoint.F90:554` on write, `:587` on read).

---

## 3. `CHECKPOINT_REVISION_NUMBER` and compatibility checking

Single definition, value **1**:

```fortran
  PetscInt, parameter, public :: CHECKPOINT_REVISION_NUMBER = 1
```
(`src/pflotran/pflotran_constants.F90:31`)

Written into binary checkpoints as a PetscBag field
`"checkpoint_version"` alongside `"test_header_size"`
(`src/pflotran/checkpoint.F90:235-243`, value assigned at `:240`), and into HDF5
checkpoints as an integer dataset `"Revision Number"`
(`src/pflotran/checkpoint.F90:933`, `:947`, `:949`).

**Binary check** — `CheckPointReadCompatibilityBinary`
(`src/pflotran/checkpoint.F90:249`):

```fortran
  ! check compatibility
  if (header%version /= CHECKPOINT_REVISION_NUMBER) then
    write(word,*) header%version
    write(word2,*) CHECKPOINT_REVISION_NUMBER
    option%io_buffer = 'Incorrect checkpoint file format (' // &
      trim(adjustl(word)) // ' vs ' // &
      trim(adjustl(word2)) // ').'
    call PrintErrMsg(option)
  endif
```
(`src/pflotran/checkpoint.F90:297-305`)

Binary additionally validates the PetscBag byte size of a dummy header type,
erroring with `'Inconsistent PetscBagSize (<a> vs <b>).'`
(`src/pflotran/checkpoint.F90:307-317`). This catches a compiler/PETSc-version
mismatch that the revision number cannot.

**HDF5 check** — `CheckPointReadCompatibilityHDF5`
(`src/pflotran/checkpoint.F90:962`), reading dataset `"Revision Number"`
(`:989`) and comparing at `:1006-1013` with the identical message text. There is
no bag-size analogue on the HDF5 path.

Both are `PrintErrMsg` (fatal), not warnings. The comparison is **strict
inequality** — there is no minimum-compatible-version, no forward compatibility,
and no per-process-model revision. A checkpoint written by any build whose
`CHECKPOINT_REVISION_NUMBER` differs is simply rejected.

---

## 4. `RESTART`, `RESET_TO_TIME_ZERO`, `SKIP_RESTART`

### 4.1 `RESTART`

Dispatched at `src/pflotran/factory_forward.F90:165` into
`FactoryForwardReadRestart` (`:368`), which sets
`option%restart_flag = PETSC_TRUE` (`:389`). Two syntaxes:

- **Legacy inline**: a filename directly on the `RESTART` line (`:391-399`). If a
  *second* word follows, it sets `option%restart_time = 0.d0` (`:396`) — the
  legacy shorthand for reset-to-zero — and returns.
- **Block form** (`:408-419`):

```fortran
    select case(word)
      case('FILENAME')
        call InputReadFilename(input,option,option%restart_filename)
        call InputErrorMsg(input,option,'RESTART','filename')
      case('RESET_TO_TIME_ZERO')
        ! any value but UNINITIALIZED_DOUBLE will set back to zero.
        option%restart_time = 0.d0
      case('REALIZATION_DEPENDENT')
        realization_dependent_restart = PETSC_TRUE
```

`REALIZATION_DEPENDENT` inserts the realization id before the literal
`'-restart'` in the filename (`src/pflotran/factory_forward.F90:423-437`),
erroring if `-restart` is absent (`:431-434`, whose message gives the example
`pflotran-restart.h5 -> pflotranR1-restart.h5`). A command-line override also
exists: `PetscOptionsGetString(... '-restart', option%restart_filename,
option%restart_flag, ...)` (`src/pflotran/option.F90:612-614`).

Defaults: `restart_flag = PETSC_FALSE`, `restart_filename = ""`,
`restart_time = UNINITIALIZED_DOUBLE`
(`src/pflotran/option.F90:546-548`; declarations at `:132-134`).

### 4.2 `RESET_TO_TIME_ZERO`

The parse site (above) only writes `restart_time = 0.d0`. The `UNINITIALIZED_DOUBLE`
default is what makes `Initialized(option%restart_time)` mean "reset was
requested". Use site, binary path:

```fortran
  if (associated(this%timestepper)) then
    call this%timestepper%RestartBinary(viewer,this%option)
    if (Initialized(this%option%restart_time)) then
      ! simply a flag to set time back to zero, no matter what the restart
      ! time is set to.
      call this%timestepper%Reset()
      ! note that this sets the target time back to zero.
    endif
```
(`src/pflotran/pmc_base.F90:1175-1182`)

HDF5 path is identical logic at `src/pflotran/pmc_base.F90:1452-1456`, with
`output_option%plot_number = 0` zeroed at `:1437-1439` (binary equivalent at
`:1169-1171`). Geophysics repeats it at
`src/pflotran/pmc_geophysics.F90:372` and `:522-526`.

What `Reset()` actually does (`TimestepperBaseReset`,
`src/pflotran/timestepper_base.F90:1060`):

```fortran
  this%target_time = 0.d0
  this%dt = this%dt_init
  this%prev_dt = 0.d0
  this%steps = 0
  this%cumulative_time_step_cuts = 0
  this%num_constant_time_steps = 0
  this%num_contig_revert_due_to_sync = 0
  this%revert_dt = PETSC_FALSE
```
(`src/pflotran/timestepper_base.F90:1073-1080`)

Note the ordering: `Reset()` runs **after** the checkpoint's header was loaded
into the stepper (`src/pflotran/pmc_base.F90:1176`), so it overrides the
checkpointed time, `dt`, and step count. `option%time` then picks up the zeroed
value at `src/pflotran/pmc_base.F90:1201` (binary) / `:1284` (HDF5).

**Practical meaning:** `RESET_TO_TIME_ZERO` restarts with the checkpointed
*state* (pressures, saturations, concentrations, porosity, permeability) but a
*clock at zero* and a fresh `dt_init`. Output files therefore restart their time
axis at 0. Plot numbering also resets, so `pflotran-000.tec` will be overwritten.
`-mas.dat`, by contrast, is **appended** (see `mass_balance_file.md` §1), so a
reset-to-zero restart produces a non-monotonic `Time` column in that file.

The inversion/prerequisite path forces the same thing programmatically
(`src/pflotran/factory_forward.F90:651`, `:674`).

### 4.3 `SKIP_RESTART`

A per-process-model flag: `PetscBool :: skip_restart` on the PM base type
(`src/pflotran/pm_base.F90:24`), default `PETSC_FALSE`
(`src/pflotran/pm_base.F90:107`). It means "do not load this process model's
state from the checkpoint; initialize it fresh instead."

Four parse sites: the generic PM options block
(`PMBaseReadSimOptionsSelectCase`, `src/pflotran/pm_base.F90:205-206`), the
`WASTE_FORM` block (`src/pflotran/factory_subsurface_read.F90:295-301`, which
requires `TYPE` first, `:296-300`), the WIPP source/sink
(`src/pflotran/pm_wipp_srcsink.F90:1345-1346`), and `WELLBORE_MODEL`
(`src/pflotran/wipp_well.F90:312-313`). A retired alias
`OVERWRITE_RESTART_TRANSPORT` now errors and points at `SKIP_RESTART`
(`src/pflotran/factory_subsurface_read.F90:1723-1727`).

**Binary restart forbids it outright:**

```fortran
    if (cur_pm%skip_restart) then
      this%option%io_buffer = 'Due to sequential nature of binary files, &
        &skipping restart for binary formatted files is not allowed.'
      call PrintErrMsg(this%option)
    endif
```
(`src/pflotran/pmc_base.F90:1210-1214`; duplicated at
`src/pflotran/pmc_geophysics.F90:387-391`)

**HDF5 restart honors it.** `PMCBaseRestartHDF5` first scans the PM list and
hoists a single PMC-wide flag — note the semantics: *any* PM with `skip_restart`
sets it for the whole PMC, since the loop `exit`s on the first hit
(`src/pflotran/pmc_base.F90:1401-1411`). What is then skipped: opening the PMC
group and reading the PMC header (`src/pflotran/pmc_base.F90:1427-1435` master
branch, `:1441-1444` otherwise); the timestepper restart read
(`if (.not.skip_restart) call this%timestepper%RestartHDF5(...)`, `:1448-1450`);
and the entire per-PM `RestartHDF5` loop (`:1488-1499`).

And it is legal only at time zero:

```fortran
    else if (skip_restart) then
        this%option%io_buffer = 'Restarted simulations that SKIP_RESTART on &
          &checkpointed process models must restart at time 0.'
        call PrintErrMsg(this%option)
```
(`src/pflotran/pmc_base.F90:1457-1460`; also
`src/pflotran/pmc_geophysics.F90:527-530`)

So in practice `SKIP_RESTART` must be paired with `RESET_TO_TIME_ZERO` and
`FORMAT HDF5`. Geophysics additionally uses it to suppress waypoint skip-ahead
(`src/pflotran/pmc_geophysics.F90:108-113`).

`src/pflotran/pm_rt.F90:583` contains a commented-out use
(`!  if (this%option%restart_flag .and. this%skip_restart) then`) — dead code,
noted only for completeness.

---

## 5. What is inside a checkpoint

Dispatcher `PMCBaseCheckpoint` (`src/pflotran/pmc_base.F90:948`) writes binary
when the format is `CHECKPOINT_BINARY` or `CHECKPOINT_BOTH`
(`:966-970`) and HDF5 when `CHECKPOINT_HDF5` or `CHECKPOINT_BOTH` (`:971-974`) —
both formats can be written from one run.

### 5.1 Binary write order

`PMCBaseCheckpointBinary` (`src/pflotran/pmc_base.F90:980`), header portion on
the master rank only (`:1006`): open `.chk` (`:1010`); compatibility bag with
version + test-header size (`:1011`, into `src/pflotran/checkpoint.F90:194-245`);
PMC header bag with fields `plot_number` and `times_per_h5_file`
(`PMCBaseRegisterHeader`, `src/pflotran/pmc_base.F90:1060-1084`; values at
`:1104-1108`, viewed at `:1021`); the timestepper (`:1026`), whose bag fields in
order (`src/pflotran/timestepper_base.F90:954-968`) are `time`, `dt`, `prev_dt`,
`num_steps`, `cumulative_time_step_cuts`, `num_constant_time_steps`,
`num_contig_revert_due_to_sync`, `revert_dt`, with
`header%time = this%target_time` (`:991`); each process model in the list
(`:1032`); then recursion into `child` (`:1037`) and `peer` (`:1041`).

Flow process-model payload, `CheckpointFlowProcessModelBinary`
(`src/pflotran/checkpoint.F90:323`), guarded by `option%nflowdof > 0` (`:359`).
Sequential `VecView` order: `field%flow_xx` packed primary variables (`:365`);
`STATE` from global aux (`:380`) — skipped for `RICHARDS_MODE,
RICHARDS_TS_MODE, ZFLOW_MODE` (`:372`) and **fatal for `PNF_MODE`**
(`'Checkpointing must be implemented for PNF mode'`, `:374`); `Sl_min`
hysteresis, `SCO2_MODE` only (`:385-390`); `POROSITY` (`:400`); and
`PERMEABILITY_X`, `_Y`, `_Z` (`:405`, `:410`, `:415`) — **diagonal only**, per
the comment at `:394-396`.

Transport payload is `PMRTCheckpointBinary`
(`src/pflotran/pm_rt.F90:1672-1851`), covering activity coefficients, mineral
volume fractions, reaction auxiliary data, secondary-continuum concentrations,
and kinetic sorption. I did not enumerate its individual writes.

### 5.2 HDF5 write order

`PMCBaseCheckpointHDF5` (`src/pflotran/pmc_base.F90:1282`): open `.h5` and create
group `"Checkpoint"` (`:1316-1318`), write `"Revision Number"` (`:1319-1320`),
create a group named after the PMC and write `"Output_plot_number"` (`:1564`) and
`"Output_times_per_h5_file"` (`:1571`), then the timestepper (`:1333`), one
subgroup per process model (`:1339-1341`), then child (`:1350`) and peer (`:1354`).

Flow payload, `CheckpointFlowProcessModelHDF5`
(`src/pflotran/checkpoint.F90:1025`), with vectors mapped to **natural** ordering
first (`DiscretizationGlobalToNatural`, e.g. `:1070-1071`). Dataset names in
order: `"Primary_Variables"` (`:1074`), `"State"` (`:1095`), `"Sl_min"` (`:1109`),
`"Porosity"` (`:1123`), `"Permeability_X"` (`:1133`), `"Permeability_Y"` (`:1143`),
`"Permeability_Z"` (`:1153`). **Divergence between the two formats:** the HDF5
`"State"` skip-list includes `WF_MODE` (`:1088`) while the binary one does not
(`:372`) — a real asymmetry in this tree, not a documentation error.

---

## 6. Restart read path and validation

Format is inferred from the **filename**, not from the `CHECKPOINT` block:

```fortran
    if (index(this%option%restart_filename,'.chk') > 0) then
      call this%process_model_coupler_list%RestartBinary(viewer)
    elseif (index(this%option%restart_filename,'.h5') > 0) then
      call this%process_model_coupler_list%RestartHDF5(h5_chk_grp_id)
    else
      this%option%io_buffer = 'Unknown restart filename format (' // &
```
(`src/pflotran/simulation_subsurface.F90:240-245`)

Readers: `PMCBaseRestartBinary` (`src/pflotran/pmc_base.F90:1114`) and
`PMCBaseRestartHDF5` (`src/pflotran/pmc_base.F90:1373`).

Validations beyond the revision number:

1. **File existence** — binary: `PetscTestFile` → `'Restart file "..." not
   found.'` (`src/pflotran/pmc_base.F90:1144-1150`); HDF5:
   `'HDF5 restart file "..." not found.'` (`src/pflotran/checkpoint.F90:585-586`)
2. **PetscBag size**, binary only (`src/pflotran/checkpoint.F90:307-317`)
3. **Grid-type compatibility**, checked before the read: binary format or a
   `.chk` filename combined with a non-`STRUCTURED_GRID` is fatal —
   `'Binary Checkpoint/Restart (.chk format) is not supported for unstructured
   grids.  Please use HDF5 (.h5 format).'`
   (`src/pflotran/simulation_subsurface.F90:203-231`, message at `:227-229`)
4. **Restart time past the end of the simulation** — after `WaypointSkipToTime`,
   if no waypoint remains it **prints** (does not error)
   `'Simulation is being restarted at a time that is at or beyond the end of
   checkpointed simulation (...)'`, binary at
   `src/pflotran/pmc_base.F90:1193-1199`, HDF5 at `:1276-1282`. The two differ:
   binary **multiplies** by `tconv` (`:1193-1194`) while HDF5 **divides**
   (`:1276-1277`) — affects the printed number only.
5. **`SKIP_RESTART` legality** — §4.3

Data read-back is `RestartFlowProcessModelBinary`
(`src/pflotran/checkpoint.F90:427`, `VecLoad` at `:468`, `:477`, `:487`, `:495`,
`:499`, `:503`, `:507`) and `RestartFlowProcessModelHDF5` (`:1165`, dataset reads
at `:1210`, `:1230`, `:1247`, `:1261`, `:1271`, `:1281`, `:1291`) — in exactly
the write order, with no per-vector size or geometry validation beyond what
PETSc/HDF5 enforce. `PMSubsurfaceFlowRestartUpdate` runs afterward
(`src/pflotran/pm_subsurface_flow.F90:1099` binary, `:1142` HDF5).

### One source oddity worth knowing

In the SCO2 branch of the **binary restart** routine, after the `VecLoad` /
`SCO2SetSlminVecLoc` sequence there is a stray *write* call inside the read path:

```fortran
    call VecView(global_vec,viewer,ierr)
```
(`src/pflotran/checkpoint.F90:492`)

This would desynchronize the sequential binary stream for `SCO2_MODE` restarts.
The line text is verified; the runtime consequence is inferred, not tested.

---

## 7. Side effects of `restart_flag` on output

`option%restart_flag` changes more than the state load:

- `mass_balance_first` / `observation_first` are set from `num_steps == 0`
  (`src/pflotran/output_observation.F90:53-65`), so a restart with a nonzero step
  count **appends** to `-mas.dat` and `.pft` without re-emitting a header
- initial porosity and property recomputation is suppressed
  (`src/pflotran/pm_subsurface_flow.F90:478`, `:484`, `:504`)
- `JUMPSTART_KINETIC_SORPTION` is gated
  (`src/pflotran/factory_subsurface.F90:689-694`)
- several process models short-circuit their output-file setup with
  `if (this%option%restart_flag .and. exist) return`
  (`src/pflotran/pm_waste_form.F90:5459`,
  `src/pflotran/pm_ufd_biosphere.F90:1731`,
  `src/pflotran/pm_wipp_srcsink.F90:4211`, `src/pflotran/pm_well.F90:8593`,
  `:8835`, `src/pflotran/pm_ufd_decay.F90:2346`)

For an extraction layer: **a restarted run's `-mas.dat` is a concatenation, not a
clean table.** Check for a monotonic `Time` column before treating it as one time
series.
