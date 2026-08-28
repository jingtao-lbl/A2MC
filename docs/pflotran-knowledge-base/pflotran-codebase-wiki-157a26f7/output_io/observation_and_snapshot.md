**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** OUTPUT / OBSERVATION_FILE, the OBSERVATION card, SNAPSHOT_FILE, VARIABLES resolution
**Last verified:** 2026-07-31

# Observation Files, Snapshot Files, and Variable Resolution

Output cadence keywords are in `output_timing.md`. Snapshot file layouts are in
`tecplot_formats.md` and `hdf5_and_xdmf_formats.md`.

---

## 1. `OBSERVATION_FILE` versus the `OBSERVATION` card

These are **two unrelated deck constructs at two different levels**, and both are
required to get an observation file. This is the answer to "the deck declared
`OBSERVATION_FILE` but no observation file was written."

### 1.1 `OBSERVATION_FILE` — a sub-block of `OUTPUT`

Dispatched at `src/pflotran/factory_subsurface_read.F90:1802-1804` into the
shared `OutputFileRead` (`src/pflotran/output.F90:68`). Its entire effect on
entry is one flag:

```fortran
    case('OBSERVATION_FILE')
      output_option%print_observation = PETSC_TRUE
```
(`src/pflotran/output.F90:134-135`)

The block then accepts timing keywords, a `VARIABLES` list
(`src/pflotran/output.F90:531-533`), `FORMAT HDF5`
(`src/pflotran/output.F90:411-413`), and `PRINT_COLUMN_IDS`. It explicitly
rejects `FORMAT TECPLOT` and `FORMAT VTK`
(`src/pflotran/output.F90:460-467`, `:502-508`), `NO_PRINT_SOURCE_SINK`
(`:188-191`), and `TOTAL_MASS_REGIONS` (`:202-205`).

`print_observation` gates exactly one call site:

```fortran
  if (realization_base%output_option%print_observation) then
    call OutputObservationTecplotColumnTXT(realization_base)
    call OutputAggregateToFile(realization_base)
    call OutputIntegralFlux(realization_base)
```
(`src/pflotran/output_observation.F90:90-93`)

Note the flag is *only* a permission bit. It creates nothing by itself.

### 1.2 `OBSERVATION` — a top-level card that creates an observation point

Dispatched at `src/pflotran/factory_subsurface_read.F90:1746-1751`:

```fortran
      case ('OBSERVATION')
        observation => ObservationCreate()
        call ObservationRead(observation,input,option)
        call ObservationAddToList(observation, &
                                  realization%patch%observation_list)
```

`ObservationRead` (`src/pflotran/observation.F90:174`) requires the block to name
**what** is being observed. The keywords that set an observation's type:

| Keyword | Line | `observation%itype` set to |
|---|---|---|
| `REGION <name>` | `src/pflotran/observation.F90:212-222` | `OBSERVATION_SCALAR` (`:221`), unless an aggregate was already declared |
| `BOUNDARY_CONDITION <name>` | `src/pflotran/observation.F90:206-211` | `OBSERVATION_FLUX` (`:211`) |
| `AGGREGATE_METRIC` / `AGGREGATE_METRICS` | `src/pflotran/observation.F90:269-271` | `OBSERVATION_AGGREGATE` (`:271`) |

The type constants are `OBSERVATION_SCALAR = 1`, `OBSERVATION_FLUX = 2`,
`OBSERVATION_AGGREGATE = 3`
(`src/pflotran/observation.F90:15-17`); the default assigned at creation is
`OBSERVATION_SCALAR` (`src/pflotran/observation.F90:90`).

Other accepted keywords: `VELOCITY` (`:223-224`), `AT_CELL_CENTER` (`:265-266`),
`AT_COORDINATE` (`:267-268`), and five `SECONDARY_*` keywords requiring
`MULTIPLE_CONTINUUM` (`:225-264`). An observation may be linked to only one
region — a second `REGION` after a `BOUNDARY_CONDITION` is fatal
(`src/pflotran/observation.F90:213-217`). Of the aggregate metrics only `MAX` is
functional (`:300-327`); `AVERAGE`, `MIN`, `MIN_ABOVE`, and `MAX_BELOW` are
parsed and then immediately error out as "still in development"
(`:297-299`, `:331-343`).

`BOUNDARY_CONDITION` additionally forces flux storage:
`option%flow%store_fluxes = PETSC_TRUE` and
`option%transport%store_fluxes = PETSC_TRUE`
(`src/pflotran/observation.F90:209-210`).

### 1.3 The gate that produces silence

`OutputObservationTecplotColumnTXT`
(`src/pflotran/output_observation.F90:108`) decides **once per run** whether to
open a file at all:

```fortran
  if (check_for_obs_points) then
    open_file = PETSC_FALSE
    observation => patch%observation_list%first
    do
      if (.not.associated(observation)) exit
      if (observation%print_velocities) calculate_velocities = PETSC_TRUE
      if (observation%itype == OBSERVATION_SCALAR .or. &
          (observation%itype == OBSERVATION_FLUX .and. &
           OptionIsIORank(option))) then
        open_file = PETSC_TRUE
        exit
      endif
      observation => observation%next
    enddo
    check_for_obs_points = PETSC_FALSE
  endif
```
(`src/pflotran/output_observation.F90:155-170`)

Everything that follows — filename construction, header, and data — sits inside
`if (open_file) then` (`src/pflotran/output_observation.F90:183`, closing at
`:277`).

**Therefore:** with an `OBSERVATION_FILE` block but no `OBSERVATION` card,
`patch%observation_list%first` is unassociated, the loop exits on its first
iteration, `open_file` stays `PETSC_FALSE`, and the routine returns having done
nothing. No file is created and **no warning is issued** — there is no check
anywhere in this tree that pairs `print_observation` against a non-empty
`observation_list`. The run is otherwise completely normal.

The two sibling calls behave the same way:

- `OutputAggregateToFile` (`src/pflotran/output_observation.F90:288`) iterates
  `patch%observation_list%first` (`:329-330`) — empty list, nothing written
- `OutputIntegralFlux` (`src/pflotran/output_observation.F90:2020`) returns
  immediately on `if (.not.associated(patch%integral_flux_list%first)) return`
  (`:2069`)

Note also that an `OBSERVATION` block declaring **only** `AGGREGATE_METRIC`
yields `itype == OBSERVATION_AGGREGATE`, which does *not* satisfy the test at
`:161-163` — so it produces `-obs-<i>-agg-<j>.pft` files but still no
`-obs-<rank>.pft`.

### 1.4 Minimum deck to actually get an observation file

```
OBSERVATION
  REGION <an existing REGION name>
/
```

placed at the **top level** (a sibling of `OUTPUT`, `REGION`, `TIME`, ...), plus
the `OBSERVATION_FILE` block inside `OUTPUT` to set `print_observation` and the
output cadence. Both are necessary; neither is sufficient.

The legacy keywords `OBSERVATION_TIMES` and `PERIODIC_OBSERVATION` also set
`print_observation` (`src/pflotran/factory_subsurface_read.F90:2024`, `:2049`),
so those routes hit exactly the same gate.

---

## 2. Observation file naming and format

One file **per MPI rank** (`src/pflotran/output_observation.F90:184-186`):

```fortran
    write(string,'(i6)') option%myrank
    filename = trim(option%global_prefix) // trim(option%group_prefix) // &
               '-obs-' // trim(adjustl(string)) // '.pft'
```

i.e. `pflotran-obs-0.pft`, `pflotran-obs-1.pft`, ... An extraction layer running
on a parallel job must expect several files, each holding only the observation
points owned by that rank. `OBSERVATION_FLUX` points are written only on the I/O
rank (`src/pflotran/output_observation.F90:162-163`, `:230`).

Related file names from the same module:

| Pattern | Source |
|---|---|
| `<prefix>-obs-<rank>.pft` | `src/pflotran/output_observation.F90:185-186` |
| `<prefix>-obs-<obs_id>-agg-<agg_id>.pft` | `src/pflotran/output_observation.F90:352-354` |
| `<prefix>-obs-sec-<rank>.pft` (secondary continuum) | `src/pflotran/output_observation.F90:675-676` |
| `<prefix>-obs-region.h5` (`FORMAT HDF5`) | `src/pflotran/output_obs_h5.F90:168` |
| `<prefix>-int.dat` (`INTEGRAL_FLUX`) | `src/pflotran/output_observation.F90:2094-2097` |

Open/append logic mirrors the mass balance file — replace on the first write of a
fresh run, append otherwise
(`src/pflotran/output_observation.F90:190-241`, using `observation_first` from
`:53-54`, cleared at `:279`).

### 2.1 Header

Same comma-separated quoted form as `-mas.dat`, starting with
`' "Time [<tunit>]"'` (`src/pflotran/output_observation.F90:194-195`) and
terminated at `:237`. Column names combine a variable name with a *cell string*
identifying the observation location. `WriteObservationHeaderForCell`
(`src/pflotran/output_observation.F90:465`) builds:

```fortran
  local_id = region%cell_ids(icell)
  write(cell_string,*) grid%nG2A(grid%nL2G(region%cell_ids(icell)))
  cell_string = trim(region%name) // ' (' // trim(adjustl(cell_string)) // ')'

  ! add coordinate of cell center
  x_string = BestFloat(grid%x(grid%nL2G(local_id)),1.d4,1.d-2)
  y_string = BestFloat(grid%y(grid%nL2G(local_id)),1.d4,1.d-2)
  z_string = BestFloat(grid%z(grid%nL2G(local_id)),1.d4,1.d-2)
  cell_string = trim(cell_string) // ' (' // trim(adjustl(x_string)) // &
                ' ' // trim(adjustl(y_string)) // &
                ' ' // trim(adjustl(z_string)) // ')'
```
(`src/pflotran/output_observation.F90:499-509`)

so a column reads
`"<Variable> [<units>] <region> (<natural_id>) (<x> <y> <z>)"`. This is the
three-argument branch of `OutputWriteToHeader`
(`src/pflotran/output_aux.F90:1399-1401`) — the one the mass-balance writer never
uses, since it always passes an empty cell string.

`WriteObservationHeaderForCoord` (`src/pflotran/output_observation.F90:518`)
omits the cell id and uses the requested coordinate instead (`:545-552`).
`WriteObservationHeaderForBC` (`:1000`) is used for `OBSERVATION_FLUX` points.

An `OBSERVATION_SCALAR` point over a multi-cell region emits **one column group
per cell** unless `AT_COORDINATE` was requested
(`src/pflotran/output_observation.F90:211-228`), so an observation on a large
region can produce a very wide file.

### 2.2 Data rows

`es14.6` for reals, `i2` for integer-format variables:

```fortran
110 format(es14.6)
111 format(i2)
```
(`src/pflotran/output_observation.F90:1165-1166`, written at `:1188` and `:1190`)

The leading time value uses `1es14.6`
(`src/pflotran/output_observation.F90:244`).

**Same parsing rule as `-mas.dat`: comma-separated quoted header,
whitespace/fixed-width data rows.** But note the width differs — `es14.6` here
versus `es16.8` in `-mas.dat` — so a shared column slicer must be parameterized.
The `i2` integer format will overflow to `**` for any value outside `-9..99`.

---

## 3. The `VARIABLES` block: name → field resolution

`VARIABLES` may appear at three levels, each populating a different list:

| Location | List populated | Line |
|---|---|---|
| `OUTPUT / VARIABLES` (master) | `output_variable_list` | `src/pflotran/factory_subsurface_read.F90:1819-1821` |
| `OUTPUT / SNAPSHOT_FILE / VARIABLES` | `output_snap_variable_list` | `src/pflotran/output.F90:528-530` |
| `OUTPUT / OBSERVATION_FILE / VARIABLES` | `output_obs_variable_list` | `src/pflotran/output.F90:531-533` |
| `OUTPUT / AVERAGE_VARIABLES` | `aveg_output_variable_list` | `src/pflotran/factory_subsurface_read.F90:1822-1824` |

A per-file list left empty is discarded and repointed at the master list after
the `OUTPUT` block closes:

```fortran
  ! If VARIABLES were not specified within the *_FILE blocks, point their
  ! variable lists to the master variable list, which can be specified within
  ! the OUTPUT block. If no VARIABLES are specified for the master list, the
  ! defaults will be populated.
          if (.not.associated(output_option%output_snap_variable_list%first) &
              .and.(output_option%output_snap_variable_list%flow_vars .and. &
                    output_option%output_snap_variable_list%energy_vars)) then
            call OutputVariableListDestroy( &
                 output_option%output_snap_variable_list)
            output_option%output_snap_variable_list => &
                 output_option%output_variable_list
          endif
```
(`src/pflotran/factory_subsurface_read.F90:2174-2193`; the observation
equivalent at `:2186-2193`)

Each entry is parsed by `OutputVariableRead` (`src/pflotran/output.F90:648`),
which uppercases the keyword (`:681`) and delegates to `OutputVariableToID`.

### 3.1 Where the list of valid output-variable names lives

**`OutputVariableToID`, `src/pflotran/output_aux.F90:753-1311`.** This single
`select case(word)` is the authoritative registry. Each arm maps the deck keyword
to four things — a display `name`, a `units` string, an output `category`, and an
integer `id` from `Variables_module`:

```fortran
    case ('LIQUID_PRESSURE')
      name = 'Liquid Pressure'
      units = 'Pa'
      category = OUTPUT_PRESSURE
      id = LIQUID_PRESSURE
    case ('LIQUID_SATURATION')
      name = 'Liquid Saturation'
      units = ''
      category = OUTPUT_SATURATION
      id = LIQUID_SATURATION
```
(`src/pflotran/output_aux.F90:815-824`)

To enumerate every legal `VARIABLES` keyword for this pin, read the `case` labels
between `src/pflotran/output_aux.F90:809` and `:1311`. The `name`/`units` pair
from this table is exactly what appears in every file header, since
`OutputVariableGetName` returns `name // ' ' // subname`
(`src/pflotran/output_aux.F90:1570-1571`) and `units` is passed straight to
`OutputWriteToHeader`.

The integer `id` becomes `output_variable%ivar`, which is what retrieves data:
`OutputGetVariableArray` (`src/pflotran/output_common.F90:158`) forwards it to
`RealizationGetVariable(...,variable%ivar,variable%isubvar,
variable%isubsubvar)` (`src/pflotran/output_common.F90:181-182`) for whole-field
output, while the per-cell path uses `RealizGetVariableValueAtCell`
(`src/pflotran/output_common.F90:260-263`, wrapped by `OutputGetVariableAtCell`
at `:241`).

The output `category` constants are declared at
`src/pflotran/output_aux.F90:146-155` (`OUTPUT_GENERIC`, `OUTPUT_PRESSURE`,
`OUTPUT_SATURATION`, `OUTPUT_CONCENTRATION`, `OUTPUT_RATE`,
`OUTPUT_VOLUME_FRACTION`, `OUTPUT_DISCRETE`, `OUTPUT_DISPLACEMENT`,
`OUTPUT_STRESS`, `OUTPUT_STRAIN`).

Two mode guards run **before** the main table:

- with `option%iflowmode == NULL_MODE` only a whitelist of transport-safe names
  is allowed (`src/pflotran/output_aux.F90:778-796`), anything else erroring with
  `'Output variable "..." not supported when not running a flow mode.'` (`:793-794`)
- with `option%igeopmode == NULL_MODE` the electrical/Archie variables error with
  `'... not supported when not running a geophysics mode.'`
  (`src/pflotran/output_aux.F90:797-807`)

A few keywords take a modifier read as a second word before the lookup, e.g.
`LIQUID_DENSITY MOLAR` becomes the synthetic key `LIQUID_DENSITY_MOLAR`
(`src/pflotran/output.F90:684-697`, table arm at
`src/pflotran/output_aux.F90:840-844`).

### 3.2 Automatic defaults

Exactly one variable is auto-appended, to the **snapshot** list only:

```fortran
  ! Material IDs
  units = ''
  name = 'Material ID'
  output_variable => OutputVariableCreate(name,OUTPUT_DISCRETE, &
                                          units,MATERIAL_ID)
  output_variable%plot_only = PETSC_TRUE ! toggle output off for observation
  output_variable%iformat = 1 ! integer
  call OutputVariableAddToList(output_variable_list,output_variable)
```
(`OutputVariableAppendDefaults`, `src/pflotran/output_aux.F90:1487-1494`, called
from `src/pflotran/factory_subsurface.F90:394-395`)

`plot_only = PETSC_TRUE` means it is skipped when writing observation data
(`src/pflotran/output_observation.F90:1174-1177`) and when a header is written
with `plot_file = .false.` (`src/pflotran/output_aux.F90:1343`). So
`Material ID` appears in snapshot files but not in `.pft` files even when both
share the master list.

Lists are finalized per realization by `RealizationProcessOutputVarList`, applied
to all four (`src/pflotran/init_subsurface.F90:1365-1372`).

---

## 4. `SNAPSHOT_FILE` in brief

`SNAPSHOT_FILE` uses the same reader (`src/pflotran/output.F90:133`) and the same
timing keywords, but takes `FORMAT` — `TECPLOT POINT|BLOCK|FEBRICK`,
`HDF5 [SINGLE_FILE|MULTIPLE_FILES [TIMES_PER_FILE n]]`, or `VTK`
(`src/pflotran/output.F90:406-514`) — plus the field-selection keywords
`VELOCITY_AT_CENTER`, `VELOCITY_AT_FACE`, `FLUXES`, `FLOWRATES`/`FLOWRATE`,
`MASS_FLOWRATE`, `ENERGY_FLOWRATE`, `AVERAGE_FLOWRATES`/`AVERAGE_FLOWRATE`,
`AVERAGE_MASS_FLOWRATE`, `AVERAGE_ENERGY_FLOWRATE`
(`src/pflotran/output.F90:553-574`).

Those field keywords are **buffered and applied only after the block closes**,
each gated on the format flags that were set:

```fortran
  if (vel_cent) then
    if (output_option%print_tecplot) &
         output_option%print_tecplot_vel_cent = PETSC_TRUE
    if (output_option%print_hdf5) &
         output_option%print_hdf5_vel_cent = PETSC_TRUE
    if (output_option%print_vtk) &
         output_option%print_vtk_vel_cent = PETSC_TRUE
  endif
```
(`src/pflotran/output.F90:585-592`)

**Ordering within the block does not matter**, since the buffered locals are
consumed after the block is fully read. But they *are* reset per `OutputFileRead`
call (`src/pflotran/output.F90:122-129`), so `VELOCITY_AT_CENTER` must be in the
same block as its `FORMAT`. A `VELOCITY_AT_CENTER` with no `FORMAT` at all sets
nothing and is a silent no-op.

`FLUXES` / `FLOWRATES` additionally force
`option%flow%store_fluxes = PETSC_TRUE` (`src/pflotran/output.F90:634`) and, on
explicit/eclipse unstructured grids, set `print_explicit_flowrate`
(`src/pflotran/output.F90:635-641`).

`AVERAGE_VARIABLES` requires both `PERIODIC TIME` and `FORMAT HDF5`; both are
enforced with fatal errors (`src/pflotran/output.F90:605-616`).
