**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** OUTPUT timing controls — TIME_UNITS, TIMES, PERIODIC TIME, PERIODIC TIMESTEP, initial/final
**Last verified:** 2026-07-31

# Output Timing

There are three parallel, independent output streams — **snapshot**,
**observation**, **mass balance** — each with its own timestep modulus, its own
time increment, and its own waypoint flag. The naming is consistent throughout:
`*_snap_*`, `*_obs_*`, `*_msbl_*`
(`src/pflotran/output_aux.F90:65-71`).

Checkpoint timing is separate again and is covered in `checkpoint_restart.md` §1.

---

## 1. `TIME_UNITS`

A **top-level `OUTPUT` keyword**, not a `*_FILE` sub-block keyword
(`src/pflotran/factory_subsurface_read.F90:1811-1818`):

```fortran
            case('TIME_UNITS')
              call InputReadWord(input,option,word,PETSC_TRUE)
              call InputErrorMsg(input,option,'Output Time Units','OUTPUT')
              output_option%tunit = trim(word)
              internal_units = 'sec'
              output_option%tconv = &
                UnitsConvertToInternal(word,internal_units, &
                                       'OUTPUT,TIME_UNITS',option)
```

Two derived quantities:

- **`tunit`** — the literal string embedded in every `[...]` units bracket, in
  Tecplot titles, and in HDF5 group names. Note that Tecplot titles and HDF5
  group names use an `a1` edit descriptor and therefore keep **only its first
  character** (`src/pflotran/output_tecplot.F90:71-72`,
  `src/pflotran/output_hdf5.F90:145-146`).
- **`tconv`** — *seconds per output time unit*. 3600 for `TIME_UNITS h`.
  Times are **divided** by it on output (`option%time/output_option%tconv`, e.g.
  `src/pflotran/output_observation.F90:2979`,
  `src/pflotran/output_tecplot.F90:130`) and rates are **multiplied** by it
  (`src/pflotran/output_observation.F90:3314`,
  `src/pflotran/output_common.F90:376`).

Defaults: `tunit = ''`, `tconv = 1.d0`
(`src/pflotran/output_aux.F90:197-198`) — i.e. seconds, with an empty unit
label, if `TIME_UNITS` is omitted.

`TIME_UNITS` is not accepted inside `SNAPSHOT_FILE` / `OBSERVATION_FILE` /
`MASS_BALANCE_FILE`; the shared reader's `case default` rejects it
(`src/pflotran/output.F90:577-579`). It applies globally to all three streams.

**Warning:** `CHECKPOINT` has its own `tconv` with the *reciprocal* meaning —
`checkpoint_option%tconv = 1.d0/units_conversion`
(`src/pflotran/checkpoint.F90:1378`), used by multiplication
(`src/pflotran/checkpoint.F90:117`). The two are not interchangeable.

**Effect on stored numbers:** changing `TIME_UNITS h` to `TIME_UNITS d` changes
the `Time` column's scale *and* the numeric value of every rate column in
`-mas.dat` and every velocity value in `*-vel-*.tec`. It does not change
cumulative or inventory columns.

---

## 2. `TIMES <unit> <list>`

Inside a `*_FILE` block (`src/pflotran/output.F90:245-267`): read a units word,
convert to seconds, read an arbitrary-length list via `UtilityReadArray`, and
create one waypoint per value carrying the stream's own flag:

```fortran
        do k = 1, size(temp_real_array)
          waypoint => WaypointCreate()
          waypoint%time = temp_real_array(k)*units_conversion
          select case(trim(block_name))
            case('SNAPSHOT_FILE')
              waypoint%print_snap_output = PETSC_TRUE
            case('OBSERVATION_FILE')
              waypoint%print_obs_output = PETSC_TRUE
            case('MASS_BALANCE_FILE')
              waypoint%print_msbl_output = PETSC_TRUE
          end select
          call WaypointInsertInList(waypoint,waypoint_list)
        enddo
```
(`src/pflotran/output.F90:254-266`)

The unit here is **independent of `TIME_UNITS`**. `TIMES h 24 48` means 24 and 48
hours regardless of the output time unit; only the *reported* `Time` column is in
`TIME_UNITS`.

Two legacy top-level forms exist:

- `OUTPUT / TIMES <unit> <list>` drives the **snapshot** stream only
  (`src/pflotran/factory_subsurface_read.F90:1912-1928`, flag at `:1925`)
- `OUTPUT / OBSERVATION_TIMES <unit> <list>` drives observation **and** mass
  balance together, creating two waypoints per listed time
  (`src/pflotran/factory_subsurface_read.F90:2037-2046`), and additionally sets
  `print_observation = PETSC_TRUE` (`:2024`)

---

## 3. `PERIODIC TIME <v> <unit>`

Two behaviors, depending on whether `between <a> and <b>` follows.

### 3.1 Without `between`

Sets the stream's increment (`src/pflotran/output.F90:279-291`):

```fortran
            select case(trim(block_name))
              case('SNAPSHOT_FILE')
                output_option%periodic_snap_output_time_incr = temp_real
              case('OBSERVATION_FILE')
                output_option%periodic_obs_output_time_incr = temp_real
              case('MASS_BALANCE_FILE')
                output_option%periodic_msbl_output_time_incr = temp_real
            end select
```

Waypoints are then materialized once, at setup, by
`InitCommonAddOutputWaypoints`:

```fortran
  ! Add waypoints for periodic mass balance output
  if (output_option%periodic_msbl_output_time_incr > 0.d0) then
    temp_real = 0.d0
    num_waypoints = final_time / output_option%periodic_msbl_output_time_incr
    ...
    do
      k = k + 1
      temp_real = temp_real + output_option%periodic_msbl_output_time_incr
      if (temp_real > final_time) exit
      waypoint => WaypointCreate()
      waypoint%time = temp_real
      waypoint%print_msbl_output = PETSC_TRUE
      call WaypointInsertInList(waypoint,waypoint_list)
```
(`src/pflotran/init_common.F90:622-648`; the observation equivalent at
`:594-620`, snapshot immediately above)

Note the loop starts at `temp_real = 0` and **increments before creating**, so
the first periodic waypoint is at `t = incr`, not at `t = 0`. A t=0 row comes
only from `print_initial_*` (§6).

Both loops emit a screen warning above `warning_num_waypoints` requested outputs
(`src/pflotran/init_common.F90:598-605`).

### 3.2 With `between <a> and <b>`

The waypoints for `[a,b]` are created inline and the increment is then **zeroed**
(`src/pflotran/output.F90:294-352`):

```fortran
                  case('MASS_BALANCE_FILE')
                    do
                      waypoint => WaypointCreate()
                      waypoint%time = temp_real
                      waypoint%print_msbl_output = PETSC_TRUE
                      call WaypointInsertInList(waypoint,waypoint_list)
                      temp_real = temp_real + &
                           output_option%periodic_msbl_output_time_incr
                      if (temp_real > temp_real2) exit
                    enddo
                    output_option%periodic_msbl_output_time_incr = 0.d0
```
(`src/pflotran/output.F90:336-346`)

Zeroing the increment is what stops `InitCommonAddOutputWaypoints` from
generating further periodic waypoints (its guard is `> 0.d0`,
`src/pflotran/init_common.F90:623`). This is how a restricted output window is
expressed. Here the loop **creates before incrementing**, so `t = a` *is*
included.

The parser requires the literal words `between` and `and` — a missing `and`
raises `INPUT_ERROR_DEFAULT` (`src/pflotran/output.F90:303-306`), a missing
`between` likewise (`:348-351`). Both are compared case-insensitively
(`StringCompareIgnoreCase`, `src/pflotran/output.F90:294`, `:303`).

---

## 4. `PERIODIC TIMESTEP <n>`

Sets the stream's modulus (`src/pflotran/output.F90:354-367`), evaluated after
every step:

```fortran
      snapshot_plot_at_this_timestep_flag = &
        (mod(this%timestepper%steps,this%pm_list% &
              output_option%periodic_snap_output_ts_imod) == 0)
      observation_plot_at_this_timestep_flag = &
        (mod(this%timestepper%steps,this%pm_list% &
              output_option%periodic_obs_output_ts_imod) == 0)
      massbal_plot_at_this_timestep_flag = &
        (mod(this%timestepper%steps,this%pm_list% &
              output_option%periodic_msbl_output_ts_imod) == 0)
      if (this%pm_list%steady_state) &
        snapshot_plot_at_this_timestep_flag = PETSC_TRUE
```
(`src/pflotran/pmc_base.F90:655-665`)

Defaults are `100000000` for all three
(`src/pflotran/output_aux.F90:241-243`) — how "never, unless asked" is encoded.
`PERIODIC TIMESTEP 1` means every step.

A steady-state process model forces a snapshot every step
(`src/pflotran/pmc_base.F90:664-665`).

A legacy top-level `OUTPUT / PERIODIC TIMESTEP` drives snapshots only
(`src/pflotran/factory_subsurface_read.F90:2014-2018`);
`OUTPUT / PERIODIC_OBSERVATION TIMESTEP` drives observation
(`src/pflotran/factory_subsurface_read.F90:2063-2067`); the legacy
`OUTPUT / MASS_BALANCE` sets the mass-balance modulus to 1
(`src/pflotran/factory_subsurface_read.F90:1848`).

---

## 5. How the mechanisms interact

They are **ORed**, not exclusive. A stream is written on a given step if *any* of
these holds:

1. a waypoint at that time carries the stream's flag —
   ```fortran
          if (cur_waypoint%print_snap_output) snapshot_plot_flag = PETSC_TRUE
          if (cur_waypoint%print_obs_output) observation_plot_flag = PETSC_TRUE
          if (cur_waypoint%print_msbl_output) massbal_plot_flag = PETSC_TRUE
   ```
   (`src/pflotran/timestepper_base.F90:612-614`, inside the
   `equal_to_or_exceeds_waypoint` branch of `SetTargetTime`)
2. the timestep modulus test passes (`src/pflotran/pmc_base.F90:655-663`)
3. it is the initial output (`src/pflotran/simulation_subsurface.F90:467-474`)

Duplicate waypoints at the same time are merged by ORing their flags
(`src/pflotran/waypoint.F90:518-527`), so `TIMES` and `PERIODIC TIME` landing on
the same instant produce one row, not two.

### 5.1 Cut timesteps silently drop scheduled output

```fortran
    if (this%timestepper%time_step_cut_flag) then
      ! if we are using the modulus of the output_option%imod, we may
      ! still print
      ! if timestep has been cut, all the I/O flags set above in
      ! %SetTargetTime, which are based on waypoints times, not time step,
      ! should be turned off
      snapshot_plot_at_this_time_flag = PETSC_FALSE
      observation_plot_at_this_time_flag = PETSC_FALSE
      massbal_plot_at_this_time_flag = PETSC_FALSE
      checkpoint_at_this_time_flag = PETSC_FALSE
    endif
```
(`src/pflotran/pmc_base.F90:616-624`)

A run with heavy timestep cutting can therefore miss scheduled rows entirely.
**An extraction layer must treat the output time series as irregular and read the
`Time` column rather than assuming a fixed cadence.** This is the most common
cause of a calibration ensemble member having fewer rows than expected without
any error message.

Note the modulus-based flags are *not* cleared, only the waypoint-derived ones.

### 5.2 The dispatcher

`Output` (`src/pflotran/output.F90:1020-1178`) runs snapshot writers first
(`:1061-1151`), then `OutputObservation` if `observation_plot_flag`
(`:1154-1156`), then `OutputMassBalance` if `massbal_plot_flag` (`:1159-1161`),
then `OutputAvegVars` (`:1164`). All three flags are cleared at the end
(`:1171-1173`), and `plot_number` is incremented only for snapshots
(`:1166-1169`) — which is why `-mas.dat` and `.pft` have no plot-number suffix
while `.tec`/`.h5`/`.xmf` do.

A `plot` touch-file can force a snapshot out of band
(`src/pflotran/output.F90:1050-1058`), setting `plot_name = 'plot'` and thereby
also changing that snapshot's filename
(`src/pflotran/output_common.F90:141-144`).

### 5.3 Synchronization across process-model couplers

`force_synchronized_output` (default `PETSC_TRUE`,
`src/pflotran/output_aux.F90:250`; cleared by `NO_SYNCHRONIZED_OUTPUT`,
`src/pflotran/factory_subsurface_read.F90:1827-1828`) forces peer process-model
couplers to run to the same time when any output flag is set
(`src/pflotran/pmc_base.F90:680-689`).

---

## 6. Initial and final outputs

### Initial

```fortran
  ! print initial condition output if not a restarted sim
  call OutputInit(option,master_timestepper%steps)
  if (output_option%plot_number == 0 .and. &
      master_timestepper%max_time_step >= 0) then
    snapshot_plot_flag = output_option%print_initial_snap
    observation_plot_flag = output_option%print_initial_obs
    massbal_plot_flag = output_option%print_initial_massbal
    call Output(this%realization,snapshot_plot_flag,observation_plot_flag, &
                massbal_plot_flag)
  endif
```
(`src/pflotran/simulation_subsurface.F90:465-474`)

Defaults (`src/pflotran/output_aux.F90:201-205`):

| Flag | Default |
|---|---|
| `print_initial_snap` | `PETSC_TRUE` |
| `print_initial_obs` | `PETSC_TRUE` |
| `print_initial_massbal` | **`PETSC_FALSE`** |

So a `-mas.dat` normally has no t=0 row unless `PRINT_INITIAL` is given, while
`.tec`/`.pft` normally do.

Plot number 0 is reserved for the initial condition and nothing else
(`src/pflotran/simulation_subsurface.F90:489-491`). Keywords:
`PRINT_INITIAL` (`src/pflotran/output.F90:175-183`) and
`NO_INITIAL`/`NO_PRINT_INITIAL` (`:164-172`), per stream; legacy whole-block
forms at `src/pflotran/factory_subsurface_read.F90:1838-1845`.

Note a latent bug in the legacy top-level form: `case('PRINT_INITIAL')` sets the
three `print_final_*` flags, not the `print_initial_*` ones
(`src/pflotran/factory_subsurface_read.F90:1842-1845`). The `*_FILE` sub-block
form (`src/pflotran/output.F90:175-183`) sets the correct flags.

### Final

Only `print_final_snap` reaches a waypoint:

```fortran
    if (cur_waypoint%final) then
      cur_waypoint%print_snap_output = &
        realization%output_option%print_final_snap
      exit
    endif
```
(`src/pflotran/realization_subsurface.F90:1773-1778`)

`print_final_obs` and `print_final_massbal` are set
(`src/pflotran/output.F90:156`, `:160`;
`src/pflotran/factory_subsurface_read.F90:1835-1845`) and echoed to the input
record (`src/pflotran/output.F90:1430`, `:1476`) but a grep of all `*.F90` finds
no site that reads them to gate an output call. So `NO_FINAL` inside
`OBSERVATION_FILE` or `MASS_BALANCE_FILE` appears inert in this tree. Stated as a
negative finding from an exhaustive grep; not confirmed by execution.

Default for all three is `PETSC_TRUE`
(`src/pflotran/output_aux.F90:202`, `:204`, `:206`).

---

## 7. Other cadence knobs in the `OUTPUT` block

| Keyword | Line | Effect |
|---|---|---|
| `SCREEN OFF` | `src/pflotran/output.F90:380-382` | disables screen printing |
| `SCREEN PERIODIC <n>` | `src/pflotran/output.F90:383-386` | sets `screen_imod` (default 1, `src/pflotran/output_aux.F90:238`) |
| `OUTPUT_FILE OFF` | `src/pflotran/factory_subsurface_read.F90:1935-1937` | disables the `.out` file |
| `OUTPUT_FILE PERIODIC <n>` | `src/pflotran/factory_subsurface_read.F90:1938-1941` | sets `output_file_imod` (default 1, `src/pflotran/output_aux.F90:239`) |
| `NO_SYNCHRONIZED_OUTPUT` | `src/pflotran/factory_subsurface_read.F90:1827-1828` | see §5.3 |

Only one `OUTPUT` block is permitted per deck:

```fortran
        if (output_option%output_read) then
          option%io_buffer = 'Only one OUTPUT block may be included in a &
            &PFLOTRAN input deck.'
          call PrintErrMsg(option)
        endif
```
(`src/pflotran/factory_subsurface_read.F90:1777-1781`)
