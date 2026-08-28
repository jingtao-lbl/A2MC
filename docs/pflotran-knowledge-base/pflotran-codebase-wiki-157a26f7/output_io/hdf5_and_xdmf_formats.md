**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** HDF5 snapshot output (`*.h5`) and its XDMF sidecar (`*.xmf`)
**Last verified:** 2026-07-31

# HDF5 and XDMF Snapshot Output

Tecplot output and the shared filename builder are in `tecplot_formats.md`.
Output cadence is in `output_timing.md`.

PFLOTRAN calls the **HDF5 Fortran API directly** (`h5fcreate_f`, `h5fopen_f`,
`h5dwrite_f`, ...) and also uses PETSc viewers elsewhere. Both are **external
framework**, not PFLOTRAN code. Example direct HDF5 calls:
`src/pflotran/output_obs_h5.F90:176`, `:426`, `:639`.

---

## 1. Enabling it, and which routine runs

`FORMAT HDF5 [SINGLE_FILE | MULTIPLE_FILES [TIMES_PER_FILE n]]` inside
`SNAPSHOT_FILE` (`src/pflotran/output.F90:408-452`) or at the legacy top level
(`src/pflotran/factory_subsurface_read.F90:2077-2109`) sets
`output_option%print_hdf5` (`src/pflotran/output.F90:417`).

Inside `OBSERVATION_FILE`, `FORMAT HDF5` instead sets `print_obs_hdf5`
(`src/pflotran/output.F90:411-413`), which routes to `OutputObsH5`
(`src/pflotran/output_observation.F90:95-97`) writing
`<prefix>-obs-region.h5` (`src/pflotran/output_obs_h5.F90:168`). That is a
different file from the snapshot `.h5` discussed here.

Snapshot dispatch (`src/pflotran/output.F90:1067-1080`):

```fortran
      if (realization_base%discretization%itype == UNSTRUCTURED_GRID) then
        select case (realization_base%discretization%grid%itype)
          case (EXPLICIT_UNSTRUCTURED_GRID,ECLIPSE_UNSTRUCTURED_GRID)
            call OutputHDF5UGridXDMFExplicit(realization_base, &
                                             INSTANTANEOUS_VARS)
          case (IMPLICIT_UNSTRUCTURED_GRID)
            call OutputHDF5UGridXDMF(realization_base,INSTANTANEOUS_VARS)
          case (POLYHEDRA_UNSTRUCTURED_GRID)
            call PrintErrMsg(option,'Add code for HDF5 output for &
                                    &Polyhedra mesh')
        end select
      else
        call OutputHDF5(realization_base,INSTANTANEOUS_VARS)
      endif
```

Three code paths — **structured**, **implicit-unstructured XDMF**, and
**explicit/eclipse-unstructured XDMF** — and they differ in group naming, dataset
naming, and filename component order. An extractor must handle all three, or
detect which one produced a given file.

Averaged-variable calls go to the same routines with `AVERAGED_VARS`
(`src/pflotran/output.F90:2235`, `:2280`, `:2282`).

---

## 2. Time-group naming — three different literals

### 2.1 Structured (`OutputHDF5`, `src/pflotran/output_hdf5.F90:71`)

The classic `Time:  X.XXXXXE+XX h` form, **with a colon**:

```fortran
  ! create a group for the data set
  write(string,'(''Time:'',es13.5,x,a1)') &
        option%time/output_option%tconv,output_option%tunit
  if (len_trim(output_option%plot_name) > 2) then
    string = trim(string) // ' ' // output_option%plot_name
  endif
  !string = trim(string3) // ' ' // trim(string)
  call HDF5GroupOpenOrCreate(file_id,string,grp_id,option)
```
(`src/pflotran/output_hdf5.F90:144-151`)

### 2.2 Implicit-unstructured XDMF (`OutputHDF5UGridXDMF`, `:405`)

**No colon**, and prefixed by the plot number:

```fortran
  write(string,'(''Time'',es13.5,x,a1)') &
        option%time/output_option%tconv,output_option%tunit
  if (len_trim(output_option%plot_name) > 2) then
    string = trim(string) // ' ' // output_option%plot_name
  endif
  string = trim(string3) // ' ' // trim(string)
  call HDF5GroupOpenOrCreate(file_id,string,grp_id,option)
  group_name=string
```
(`src/pflotran/output_hdf5.F90:562-570`)

`string3` is `write(string3,'(i4)') output_option%plot_number`
(`src/pflotran/output_hdf5.F90:476`) — or, for averaged variables,
`int(option%time/periodic_snap_output_time_incr)` (`:480-481`). Fortran `trim`
strips only *trailing* blanks, so the `'(i4)'` **leading** blanks survive into
the group name.

### 2.3 Explicit-unstructured (`OutputHDF5UGridXDMFExplicit`, `:767`)

Adds an extended-precision variant:

```fortran
  if (output_option%extend_hdf5_time_format) then
    write(string,'(''Time'',es20.12,x,a1)') &
          option%time/output_option%tconv,output_option%tunit
  else
    write(string,'(''Time'',es13.5,x,a1)') &
          option%time/output_option%tconv,output_option%tunit
  endif
  ...
  string = trim(string3) // ' ' // trim(string)
  call HDF5GroupOpenOrCreate(file_id,string,grp_id,option)
  group_name=string
```
(`src/pflotran/output_hdf5.F90:1007-1020`)

`extend_hdf5_time_format` is parsed at
`src/pflotran/factory_subsurface_read.F90:2164` and defaults to `PETSC_FALSE`
(`src/pflotran/output_aux.F90:211`).

### 2.4 Consequences for a group-name matcher

- must accept both `Time:` and `Time`
- must accept an optional leading plot-number field with leading spaces
- must accept both `es13.5` and `es20.12` precision
- **`a1` means only the first character of `tunit` reaches the group name**, so
  `TIME_UNITS h` gives `h` but `TIME_UNITS yr` would give `y`
- an optional trailing ` <plot_name>` is appended when `PLOT_NAME` is set

Fixed group names elsewhere: `"Domain"`
(`src/pflotran/output_hdf5.F90:543`, `:985`, `:3574`) and `"Coordinates"`
(`src/pflotran/output_hdf5.F90:1424`, written by
`OutputHDF5WriteStructCoordGroup` at `:1397`).

The robust route is to read the `.xmf` sidecar (§5), which spells out the exact
group and dataset paths.

---

## 3. Dataset naming inside a time group

Unstructured/XDMF path (`src/pflotran/output_hdf5.F90:594-599`):

```fortran
        string = OutputVariableGetName(cur_variable)
        if (len_trim(cur_variable%units) > 0) then
          word = cur_variable%units
          call HDF5MakeStringCompatible(word)
          string = trim(string) // ' [' // trim(word) // ']'
        endif
```

Structured path is the same except it swaps spaces for underscores in the name:

```fortran
    string = StringSwapChar(OutputVariableGetName(cur_variable)," ","_")
```
(`src/pflotran/output_hdf5.F90:172`)

**So structured HDF5 dataset names are underscore-joined
(`Liquid_Pressure [Pa]`) while unstructured ones keep spaces
(`Liquid Pressure [Pa]`).** Units are passed through
`HDF5MakeStringCompatible`, which is why `m/s`-style units appear as
`m_per_s`-style in dataset names.

Averaged variables are prefixed `'Aveg. '`
(`src/pflotran/output_hdf5.F90:193`, `:620`).

`OutputVariableGetName` is `name // ' ' // subname`
(`src/pflotran/output_aux.F90:1570-1571`); `name` and `units` come from the
`OutputVariableToID` table (`src/pflotran/output_aux.F90:753-1311`, see
`observation_and_snapshot.md` §3.1). Data is fetched by `OutputGetVariableArray`
(`src/pflotran/output_hdf5.F90:171`, `:591` → `src/pflotran/output_common.F90:158`).

### Coordinates

Structured runs write `"X [m]"`, `"Y [m]"`, `"Z [m]"` into group `"Coordinates"`
with `nx+1`/`ny+1`/`nz+1` **node** values
(`src/pflotran/output_hdf5.F90:1428`, `:1438`, `:1448`, via
`WriteHDF5Coordinates` at `:1466`). Unstructured runs write `/Domain/Vertices`
and `/Domain/Cells` referenced from the `.xmf`
(`src/pflotran/output_common.F90:746-750`, `:767`).

### Cell-centered velocities

Structured path (`src/pflotran/output_hdf5.F90:221-247`):

```fortran
    string = "Liquid X-Velocity [m_per_" // trim(output_option%tunit) // "]"
```
(`:221`, Y at `:225`, Z at `:229`), while the gas ones are bare
`"Gas X-Velocity"`, `"Gas Y-Velocity"`, `"Gas Z-Velocity"` with **no unit
suffix** (`:237`, `:242`, `:247`).

XDMF path builds all six consistently, with units
(`src/pflotran/output_hdf5.F90:686-687` liquid, `:716-717` gas), looping over
`word ∈ {'X','Y','Z'}` (`:674-685`). The gas branch there is guarded by
`option%nphase > 1` alone (`:700`), whereas the structured path also considers
`option%transport%nphase` (`:210-212`).

Both inconsistencies (missing gas units on the structured path, differing
multiphase guards) are present in the source. Match dataset names by prefix, not
by exact string.

---

## 4. Single-file versus multiple-file

Keywords `SINGLE_FILE` / `MULTIPLE_FILES [TIMES_PER_FILE n]`
(`src/pflotran/output.F90:426-442`; legacy duplicate at
`src/pflotran/factory_subsurface_read.F90:2085-2095`). Defaults:
`print_single_h5_file = PETSC_TRUE`, `times_per_h5_file = 0`
(`src/pflotran/output_aux.F90:214-215`). Selecting `MULTIPLE_FILES` without
`TIMES_PER_FILE` sets `times_per_h5_file = 1`
(`src/pflotran/output.F90:432`), i.e. one file per output time.

`OutputHDF5OpenFile` (`src/pflotran/output_hdf5.F90:308`):

```fortran
  if (output_option%print_single_h5_file) then
    first = hdf5_first
    filename = trim(option%global_prefix) // trim(option%group_prefix) // &
               trim(string2) // '.h5'
  else
    string = OutputHDF5FilenameID(output_option,option,var_list_type)
    ...
    filename = trim(option%global_prefix) // trim(option%group_prefix) // &
                '-' // trim(string) // trim(string2) // '.h5'
  endif
```
(`src/pflotran/output_hdf5.F90:342-368`)

`string2` is `''` for instantaneous variables or `'-aveg'` for averaged
(`src/pflotran/output_hdf5.F90:334`, `:337`).

The file index is **not** the plot number:

```fortran
      file_number = floor(real(output_option%plot_number)/ &
                               output_option%times_per_h5_file)
```
(`OutputHDF5FilenameID`, `src/pflotran/output_hdf5.F90:1230-1231`), zero-padded
the same way as `OutputFilenameID` (`:1239-1248`). A new file is started when
`mod(plot_number, times_per_h5_file) == 0`
(`src/pflotran/output_hdf5.F90:350-355`, and `:497-502` in the XDMF path).

Append versus create: `HDF5FileTryOpen` when not `first`, `HDF5FileOpen` when
`first` (`src/pflotran/output_hdf5.F90:370-375`), with the messages
`" --> creating hdf5 output file: "` (`:378`) and
`" --> appending to hdf5 output file: "` (`:380`).

**Component-order divergence.** The XDMF path builds the single-file name as
`global_prefix // string2 // group_prefix // '.h5'`
(`src/pflotran/output_hdf5.F90:489-490`) whereas `OutputHDF5OpenFile` builds
`global_prefix // group_prefix // string2 // '.h5'` (`:344-345`). With an empty
`group_prefix` — the common case — the two agree. The multi-file XDMF variant is
at `:515-520`, and the same pair is repeated for the explicit-grid path at
`:861-863` and `:888-891`.

The XDMF path also keeps a second, basename-only form for embedding inside the
`.xmf`:

```fortran
    filename_header = trim(StringGetFilename(option%global_prefix)) // &
                      trim(string2) // trim(option%group_prefix) // '.h5'
```
(`src/pflotran/output_hdf5.F90:491-492`)

so the `.xmf` references the `.h5` by basename, making the pair relocatable.

---

## 5. The `.xmf` sidecar

One `.xmf` per snapshot, named by `OutputFilename(output_option,option,'xmf','')`
(`src/pflotran/output_hdf5.F90:477`; the averaged variant `'aveg'` at `:482`;
explicit-grid equivalents at `:848`, `:853`), opened as a plain text file:

```fortran
  open(unit=OUTPUT_UNIT,file=xmf_filename,action="write")
```
(`src/pflotran/output_hdf5.F90:552`, `:997`)

`OutputXMFHeader` (`src/pflotran/output_common.F90:701`) emits, in order:

| Element | Line |
|---|---|
| `<?xml version="1.0" ?>` | `:721` |
| `<!DOCTYPE Xdmf SYSTEM "Xdmf.dtd" []>` | `:724` |
| `<Xdmf>` | `:727` |
| `  <Domain>` | `:730` |
| `    <Grid Name="Mesh">` | `:733` |
| `      <Time Value = "..." />` (via `write(string2,'(es13.5)') time`) | `:736-737` |
| `<Topology Type="Mixed" NumberOfElements="...">` | `:741-742` |
| `<DataItem Format="HDF" DataType="Int" Dimensions="...">` → `<file>:/Domain/Cells` | `:746-750` |
| `<Geometry GeometryType="XYZ">` → `<file>:/Domain/Vertices` | `:759-767` |
| optional `XC`/`YC`/`ZC` cell-center attributes → `<file>:/Domain/XC` etc. | `:778-805` |

Per-variable attributes come from `OutputXMFAttribute`
(`src/pflotran/output_common.F90:840`), emitting
`<Attribute Name="..." AttributeType="Scalar"  Center="Cell|Node">`
(`:855-862`) and a `<DataItem Dimensions="N 1" Format="HDF">` naming the dataset
(`:865-871`). The reference string is built in the HDF5 module:

```fortran
        att_datasetname = trim(filename_header) // ":/" // trim(group_name) // &
                          "/" // trim(string)
```
(`src/pflotran/output_hdf5.F90:607-608`; identical constructions at `:632-633`,
`:692-693`, `:722-723`, `:1055`, `:1082`, `:1114`, `:1126`, `:1139`, `:1156`,
`:1168`, `:1180`)

Footer `OutputXMFFooter` (`src/pflotran/output_common.F90:813-836`: `</Grid>`,
`</Domain>`, `</Xdmf>`) is called at `src/pflotran/output_hdf5.F90:757`, `:1198`,
`:3633`.

**Recommended extraction route for HDF5 output:** parse the `.xmf` for each
snapshot to recover `(h5 filename, group name, dataset name)` triples rather than
reconstructing group names from the format strings in §2. The `.xmf` is plain
XML, is written per snapshot, and is generated by the same code that wrote the
datasets.

Note the `.xmf` is produced only on the **unstructured** paths
(`OutputHDF5UGridXDMF` and `...Explicit`). The structured path
(`OutputHDF5`, `src/pflotran/output_hdf5.F90:71`) has no `OutputFilename(...,'xmf',...)`
call, so a structured run yields `.h5` with no XDMF sidecar and the §2.1 group
naming must be used directly.

---

## 6. Other HDF5 files

| Pattern | Source | Contents |
|---|---|---|
| `<prefix>-domain.h5` | `src/pflotran/output_hdf5.F90:911` (path) / `:913` (basename via `StringGetFilename`) | domain/mesh dump |
| `<prefix>-regions.h5` | `src/pflotran/output_hdf5.F90:3445-3446` | structured region dump, group `'Time: 0. y'` (`:3456`) |
| `<prefix>_regions.h5` / `.xmf` | `src/pflotran/output_hdf5.F90:3550-3551` | unstructured region dump, group `'0 Time 0.'` (`:3579`) |
| `<prefix>-obs-region.h5` | `src/pflotran/output_obs_h5.F90:168` | `OBSERVATION_FILE` with `FORMAT HDF5` |

---

## 7. Related keywords

`HDF5_WRITE_GROUP_SIZE <n>` sets `option%hdf5_write_group_size`
(`src/pflotran/output.F90:520-523`) — a parallel-I/O tuning knob, not a format
change.

`AVERAGE_VARIABLES` (`src/pflotran/factory_subsurface_read.F90:1822-1824`)
requires both `PERIODIC TIME` and `FORMAT HDF5`; both are enforced with fatal
errors (`src/pflotran/output.F90:605-616`,
`src/pflotran/factory_subsurface_read.F90:2212-2219`). Its datasets are prefixed
`'Aveg. '` and, in multi-file mode, land in a separate `-aveg` file (§4).
