**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** Tecplot snapshot output (`*.tec`), output filename construction, `VELOCITY_AT_CENTER`
**Last verified:** 2026-07-31

# Tecplot Snapshot Formats

HDF5 and XDMF are covered in `hdf5_and_xdmf_formats.md`. Output cadence is in
`output_timing.md`. Variable-name resolution is in `observation_and_snapshot.md`
§3.

---

## 1. Output file naming — one shared builder

All snapshot-family files (`.tec`, `.vtk`, `.xmf`) get their names from
`OutputFilename` (`src/pflotran/output_common.F90:110`):

```fortran
  if (len_trim(optional_string) > 0) then
    final_optional_string = '-' // optional_string
  else
    final_optional_string = ''
  endif
  final_suffix = '.' // suffix

  ! open file
  if (len_trim(output_option%plot_name) > 2) then
    OutputFilename = trim(output_option%plot_name) // &
            trim(final_optional_string) // &
            final_suffix
  else
    OutputFilename = trim(option%global_prefix) // &
            trim(option%group_prefix) // &
            trim(final_optional_string) // &
            '-' // &
            trim(OutputFilenameID(output_option,option)) // &
            final_suffix
  endif
```
(`src/pflotran/output_common.F90:133-152`)

The numeric ID is the plot number, zero-padded to at least three digits by
`OutputFilenameID` (`src/pflotran/output_common.F90:72`):

```fortran
  if (output_option%plot_number < 10) then
    write(OutputFilenameID,'("00",i1)') output_option%plot_number
  else if (output_option%plot_number < 100) then
    write(OutputFilenameID,'("0",i2)') output_option%plot_number
  else if (output_option%plot_number < 1000) then
    write(OutputFilenameID,'(i3)') output_option%plot_number
```
(`src/pflotran/output_common.F90:89-94`; `i4` at `:96`, `i5` at `:98`, fatal
error above `10^5` at `:100-101`)

Concrete names produced with `global_prefix = 'pflotran'`:

| File | Built by | Writer |
|---|---|---|
| `pflotran-000.tec` | `OutputFilename(...,'tec','')` (`src/pflotran/output_tecplot.F90:262`) | `OutputTecplotBlock` (`:217`) |
| `pflotran-000.tec` | `OutputFilename(...,'tec','')` (`src/pflotran/output_tecplot.F90:974`) | `OutputTecplotPoint` (`:931`) |
| **`pflotran-vel-000.tec`** | `OutputFilename(...,'tec','vel')` (`src/pflotran/output_tecplot.F90:465`) | `OutputVelocitiesTecplotBlock` (`:422`) |
| **`pflotran-vel-000.tec`** | `OutputFilename(...,'tec','vel')` (`src/pflotran/output_tecplot.F90:1088`) | `OutputVelocitiesTecplotPoint` (`:1036`) |
| `pflotran-000.vtk` / `pflotran-vel-000.vtk` | `src/pflotran/output_vtk.F90:65` / `:196` | `OutputVTK` / `OutputVelocitiesVTK` |

If the deck (or the `plot` touch-file mechanism,
`src/pflotran/output.F90:1051-1057`) sets `plot_name`, the numeric ID is dropped
entirely and the file is simply `<plot_name>-vel.tec`
(`src/pflotran/output_common.F90:141-144`). Plot number 0 is always the initial
condition and nothing else (`src/pflotran/simulation_subsurface.F90:489-491`),
which is incremented only for snapshots (`src/pflotran/output.F90:1166-1169`).

The literal `'-000.tec'` does **not** exist in source; the suffix is synthesized
at runtime by `OutputFilename` + `OutputFilenameID`.

### Face-flux files

`OutputFluxVelocitiesTecplotBlk` (`src/pflotran/output_tecplot.F90:590`) bypasses
`OutputFilename` and assembles its name inline: prefix (`:657-661`), a two-letter
quantity token — `qw`/`qa`/`qh` for flux dofs 1/2/3 (`:672`, `:674`, `:676`,
with `flux_unit='MJ/'` for `qh` at `:677`) or `ql`/`qg` for liquid/gas (`:682`,
`:684`) — a direction letter `x`/`y`/`z` (`:688-695`), then
`'-' // <id> // '.tec'` (`:697-699`). Result: `pflotran-qlx-000.tec`,
`pflotran-qhz-012.tec`.

### Other `.tec` names

| Pattern | Routine | Line |
|---|---|---|
| `<prefix>-sec-rank<N>-obs<M>-<id>.tec` | `OutputSecondaryContinuumTecplot` (`:2300`) | `:2379-2381` |
| `region_<name>.tec` | `OutputTecplotPrintRegions` (`:2793`) | `:2828` |
| `<prefix>-darcyvel-<id>-rank<N>.dat` | `OutputPrintExplicitFlowrates` (`:2175`) | `:2221`, `:2250` |
| `<prefix>-cellinfo-<id>-rank<N>.dat` | same | `:2226`, `:2277` |

(all in `src/pflotran/output_tecplot.F90`; the last two are `.dat`, not `.tec`)

---

## 2. BLOCK versus POINT

### 2.1 Selection

Parsed in the `*_FILE` reader (`src/pflotran/output.F90:474-483`) and in the
legacy top-level `OUTPUT / FORMAT`
(`src/pflotran/factory_subsurface_read.F90:2115-2122`):

```fortran
            select case(trim(word))
              case('POINT')
                output_option%tecplot_format = TECPLOT_POINT_FORMAT
              case('BLOCK')
                output_option%tecplot_format = TECPLOT_BLOCK_FORMAT
              case('FEBRICK')
                output_option%tecplot_format = TECPLOT_FEBRICK_FORMAT
```

Two **silent** overrides follow immediately:

- POINT in parallel is downgraded — `'TECPLOT POINT format not supported in
  parallel. Switching to TECPLOT BLOCK.'`
  (`src/pflotran/output.F90:484-490`)
- implicit unstructured grids are forced to FEBRICK
  (`src/pflotran/output.F90:491-497`)

So a deck saying `FORMAT TECPLOT POINT` will produce BLOCK-packed files on any
multi-rank run. An extractor must sniff the `DATAPACKING=` field, not trust the
deck.

Dispatch (`src/pflotran/output.F90:1092-1097`):

```fortran
      select case(realization_base%output_option%tecplot_format)
        case (TECPLOT_POINT_FORMAT)
          call OutputTecplotPoint(realization_base)
        case (TECPLOT_BLOCK_FORMAT,TECPLOT_FEBRICK_FORMAT)
          call OutputTecplotBlock(realization_base)
      end select
```

### 2.2 BLOCK layout

`OutputTecplotBlock` (`src/pflotran/output_tecplot.F90:217`) writes, in order:

1. TITLE + VARIABLES + ZONE, via `OutputTecplotHeader`
   (`src/pflotran/output_tecplot.F90:268`)
2. **coordinates as three contiguous blocks** — all X nodal coordinates, then all
   Y, then all Z, over `(nx+1)(ny+1)(nz+1)` nodes
   (`WriteTecplotStructuredGrid`, `src/pflotran/output_tecplot.F90:1322`, loops
   marked `! x-dir` at `:1361`, `! y-dir` at `:1384`, `! z-dir` at `:1409`,
   10 values per line, format `1000 format(es13.6,1x)` at `:1347`); or
   `WriteTecplotUGridVertices` for unstructured
   (`src/pflotran/output_tecplot.F90:282`)
3. **each output variable as one contiguous block**, in
   `output_snap_variable_list` order:

```fortran
  ! loop over snapshot variables and write to file
  cur_variable => output_option%output_snap_variable_list%first
  do
    if (.not.associated(cur_variable)) exit
    call OutputGetVariableArray(realization_base,global_vec,cur_variable)
    call DiscretizationGlobalToNatural(discretization,global_vec, &
                                        natural_vec,ONEDOF)
    if (cur_variable%iformat == 0) then
      call WriteTecplotDataSetFromVec(OUTPUT_UNIT,realization_base, &
                                      natural_vec,TECPLOT_REAL)
    else
      call WriteTecplotDataSetFromVec(OUTPUT_UNIT,realization_base, &
                                      natural_vec,TECPLOT_INTEGER)
    endif
    cur_variable => cur_variable%next
  enddo
```
(`src/pflotran/output_tecplot.F90:285-300`)

4. connectivity last, for unstructured grids
   (`src/pflotran/output_tecplot.F90:308`, `:315`, `:320`)

Values are written 10 per line (`PetscInt, parameter :: num_per_line = 10`,
`src/pflotran/output_tecplot.F90:1889`, forwarded to
`WriteTecplotDataSetNumPerLine` at `:1898`) with format
`1010 format(100(es13.6,1x))` for reals and integer variants `1000-1004`
(`:1937-1942`).

**Consequence for extraction:** in BLOCK mode the k-th variable's values for the
whole domain are contiguous, in **natural (global) cell ordering**
(`DiscretizationGlobalToNatural`, `src/pflotran/output_tecplot.F90:290-291`),
after the 3×(node count) coordinate values. Values are cell-centered, so each
variable block has `nx·ny·nz` entries while the coordinate blocks have
`(nx+1)(ny+1)(nz+1)`.

### 2.3 POINT layout

`OutputTecplotPoint` (`src/pflotran/output_tecplot.F90:931`) writes **one row per
local cell**, coordinates first then all variables on the same line:

```fortran
  do local_id = 1, grid%nlmax
    ghosted_id = grid%nL2G(local_id)
    write(OUTPUT_UNIT,1000,advance='no') grid%x(ghosted_id)
    write(OUTPUT_UNIT,1000,advance='no') grid%y(ghosted_id)
    write(OUTPUT_UNIT,1000,advance='no') grid%z(ghosted_id)

    ! loop over snapshot variables and write to file
    cur_variable => output_option%output_snap_variable_list%first
    do
      if (.not.associated(cur_variable)) exit
      value = RealizGetVariableValueAtCell(realization_base,ghosted_id, &
                                           cur_variable%ivar, &
                                           cur_variable%isubvar, &
                                           cur_variable%isubsubvar)
      if (cur_variable%iformat == 0) then
        write(OUTPUT_UNIT,1000,advance='no') value
      else
        write(OUTPUT_UNIT,1001,advance='no') int(value)
      endif
      cur_variable => cur_variable%next
    enddo

    write(OUTPUT_UNIT,1009)

  enddo
```
(`src/pflotran/output_tecplot.F90:994-1018`)

Formats: `1000 format(es13.6,1x)`, `1001 format(i4,1x)`, `1009 format('')`
(`src/pflotran/output_tecplot.F90:990-992`). Here coordinates are **cell
centers**, not nodes, and the ordering is **local** (`local_id = 1, grid%nlmax`),
not natural. `VELOCITY_AT_FACE` is rejected in POINT mode
(`src/pflotran/output_tecplot.F90:1026-1030`).

Integer-format variables are written `i4` here, which will overflow (`****`) for
a material id or natural id above 9999.

### 2.4 The ZONE line

Built by `OutputWriteTecplotZoneHeader`
(`src/pflotran/output_tecplot.F90:98`), emitted as a single line at
`src/pflotran/output_tecplot.F90:211`. Common prefix:

```fortran
  string = 'ZONE T="' // &
           trim(StringFormatDouble(option%time/output_option%tconv)) // &
           '"' // &
           ', STRANDID=1, SOLUTIONTIME=' // &
           trim(StringFormatDouble(option%time/output_option%tconv))
```
(`src/pflotran/output_tecplot.F90:129-133`)

`StringFormatDouble` uses `'(1es13.5)'` (`src/pflotran/string.F90:774`);
`StringFormatInt` uses `'(1i12)'` (`src/pflotran/string.F90:750`).

Then, by format and grid type:

| Format / grid | Fields appended | Line |
|---|---|---|
| POINT, structured | `, I=nx, J=ny, K=nz` then `, DATAPACKING=POINT` | `:138-143`, `:149-150` |
| POINT, unstructured | fatal: `'POINT format currently not supported for unstructured'` | `:145-147` |
| BLOCK, structured | `, I=nx+1, J=ny+1, K=nz+1` | `:154-159` |
| BLOCK, implicit unstructured | `, N=<num_vertices_global>, E=<nmax>, ZONETYPE=FEBRICK` | `:161-166` |
| BLOCK, explicit/eclipse | `, N=<nmax>, E=<num_elems>, ZONETYPE=FEBRICK` | `:167-173` |
| BLOCK, polyhedra | `, NODES=`, `, FACES=`, `, E=`, `, TotalNumFaceNodes=`, `, NumConnectedBoundaryFaces=0`, `, TotalNumBoundaryConnections=0`, `, ZONETYPE=FEPOLYHEDRON` | `:175-188` |

VARLOCATION and packing:

```fortran
        string3 = ', VARLOCATION=(NODAL)'
      else
        if (variable_count > 4) then
          string3 = ', VARLOCATION=([4-' // &
                    trim(StringFormatInt(variable_count)) // &
                    ']=CELLCENTERED)'
        else
          string3 = ', VARLOCATION=([4]=CELLCENTERED)'
        endif
      endif
      string2 = trim(string2) // trim(string3) // ', DATAPACKING=BLOCK'
```
(`src/pflotran/output_tecplot.F90:197-207`) — the NODAL branch applies only to
explicit and eclipse unstructured grids (`:195-197`).

So in BLOCK mode the file explicitly declares columns 4..N as cell-centered and
columns 1-3 (X,Y,Z) as nodal — the structural reason the coordinate blocks are
longer than the variable blocks.

The TITLE line (`src/pflotran/output_tecplot.F90:71-72`):

```fortran
  write(fid,'(''TITLE = "'',1es13.5," [",a1,'']"'')') &
                option%time/output_option%tconv,output_option%tunit
```

Note `a1` — **only the first character of `tunit` is written into the title**, so
`TIME_UNITS h` gives `[h]` but a hypothetical `TIME_UNITS yr` would give `[y]`.

### 2.5 Writers that hand-roll their own ZONE line

`OutputFluxVelocitiesTecplotBlk` (`src/pflotran/output_tecplot.F90:757-772`),
which decrements the staggered dimension (`nx-1` at `:759-760`, `ny-1` at
`:762-765`, `nz-1` at `:767-770`) and omits STRANDID / SOLUTIONTIME /
VARLOCATION entirely; and `OutputVelocitiesTecplotPoint` (`:1119-1124`).

---

## 3. How variables become columns

`OutputTecplotHeader` (`src/pflotran/output_tecplot.F90:38`) seeds the line with
the three coordinate columns and does **not** advance:

```fortran
  string = 'VARIABLES=' // &
           '"X [m]",' // &
           '"Y [m]",' // &
           '"Z [m]"'
  write(fid,'(a)',advance="no") trim(string)

  call OutputWriteVariableListToHeader(fid, &
                                      output_option%output_snap_variable_list, &
                                       '',icolumn,PETSC_TRUE,variable_count)
  ! need to terminate line
  write(fid,'(a)') ''
  ! add x, y, z variables to count
  variable_count = variable_count + 3
```
(`src/pflotran/output_tecplot.F90:75-87`)

`OutputWriteVariableListToHeader` (`src/pflotran/output_aux.F90:1315`) walks the
list in order, skipping `plot_only` entries when `plot_file` is false, and counts:

```fortran
  variable_count = 0
  cur_variable => variable_list%first
  do
    if (.not.associated(cur_variable)) exit
    if (.not. plot_file .and. cur_variable%plot_only) then
    ...
    variable_name = OutputVariableGetName(cur_variable)
    units = cur_variable%units
    call OutputWriteToHeader(fid,variable_name,units,cell_string,icolumn)
    variable_count = variable_count + 1
    cur_variable => cur_variable%next
  enddo
```
(`src/pflotran/output_aux.F90:1339-1352`)

`OutputVariableGetName` is `name // ' ' // subname`
(`src/pflotran/output_aux.F90:1570-1571`), where `name` and `units` came from the
`OutputVariableToID` table (`src/pflotran/output_aux.F90:753-1311`; see
`observation_and_snapshot.md` §3.1). `OutputWriteToHeader`
(`src/pflotran/output_aux.F90:1358`) appends each as `,"<name> [<units>]"`.

**Column mapping:** columns 1,2,3 = X,Y,Z; column 3+k = the k-th surviving entry
of `output_snap_variable_list`. The BLOCK data loop
(`src/pflotran/output_tecplot.F90:286-300`) and the POINT row loop
(`src/pflotran/output_tecplot.F90:1001-1014`) walk the *same* list in the *same*
order, which is what keeps header and data aligned. `variable_count` (list length
+ 3) is what feeds `VARLOCATION=([4-N]=CELLCENTERED)`
(`src/pflotran/output_tecplot.F90:87` → `:199-202`).

Column-number prefixes: `OutputTecplotBlock` hardwires
`PetscInt, parameter :: icolumn = -1`
(`src/pflotran/output_tecplot.F90:241`) — BLOCK files never get numbered
headers, even with `PRINT_COLUMN_IDS` — while `OutputTecplotPoint` sets
`icolumn = 3` when `PRINT_COLUMN_IDS` is on
(`src/pflotran/output_tecplot.F90:982-986`).

---

## 4. `VELOCITY_AT_CENTER` and the `pflotran-vel-*.tec` files

### 4.1 Keyword

`case('VELOCITY_AT_CENTER')` sets a local buffer
(`src/pflotran/output.F90:553-554`) applied after the block closes:

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
(`src/pflotran/output.F90:585-592`; legacy top-level duplicate at
`src/pflotran/factory_subsurface_read.F90:2195-2202`)

All three flags default to `PETSC_FALSE`
(`src/pflotran/output_aux.F90:212`, `:224`, `:229`). Because the flag is only
propagated when a format was already requested, **`VELOCITY_AT_CENTER` with no
`FORMAT` in the same block is a silent no-op.**

The Tecplot velocity writer is invoked when `print_tecplot_vel_cent` is set
(`src/pflotran/output_tecplot.F90:325-327` from BLOCK, `:1022-1024` from POINT).

### 4.2 File contents

`OutputVelocitiesTecplotBlock` (`src/pflotran/output_tecplot.F90:422`) writes to
`pflotran-vel-<NNN>.tec` (`:465`) with this exact header:

```fortran
    write(OUTPUT_UNIT,'(''TITLE = "'',1es13.5," [",a1,'']"'')') &
                 option%time/output_option%tconv,output_option%tunit
    ! write variables
    variable_count = SEVEN_INTEGER
    string = 'VARIABLES=' // &
             '"X [m]",' // &
             '"Y [m]",' // &
             '"Z [m]",' // &
             '"qlx [m/' // trim(output_option%tunit) // ']",' // &
             '"qly [m/' // trim(output_option%tunit) // ']",' // &
             '"qlz [m/' // trim(output_option%tunit) // ']"'
    if (option%nphase > 1 .or. option%transport%nphase > 1) then
      variable_count = TEN_INTEGER
      string = trim(string) // &
               ',"qgx [m/' // trim(output_option%tunit) // ']",' // &
               '"qgy [m/' // trim(output_option%tunit) // ']",' // &
               '"qgz [m/' // trim(output_option%tunit) // ']"'
    endif

    string = trim(string) // ',"Material_ID"'
    write(OUTPUT_UNIT,'(a)') trim(string)

    call OutputWriteTecplotZoneHeader(OUTPUT_UNIT,realization_base, &
                                      variable_count,TECPLOT_BLOCK_FORMAT)
```
(`src/pflotran/output_tecplot.F90:475-498`)

So the columns are **fixed and not driven by `VARIABLES`**:
`X [m], Y [m], Z [m], qlx [m/<tunit>], qly, qlz` — plus `qgx, qgy, qgz` when
`nphase > 1` or `transport%nphase > 1` — plus `Material_ID`. Seven columns
single-phase, ten multiphase (`variable_count` at `:478` / `:487`).

Note the zone header is forced to `TECPLOT_BLOCK_FORMAT` regardless of the user's
`tecplot_format` (`src/pflotran/output_tecplot.F90:498`). A POINT run instead
reaches `OutputVelocitiesTecplotPoint` (`src/pflotran/output_tecplot.F90:1036`),
which builds the same VARIABLES line (`:1101-1116`) but writes
`, DATAPACKING=POINT` (`:1124`) and errors on non-structured grids (`:1082-1086`).
The POINT variant's TITLE uses `1es13.4` (`:1098`) where the BLOCK variant uses
`1es13.5` (`:475`) — an inconsistency present in the source.

Data block order in the BLOCK version
(`src/pflotran/output_tecplot.F90:511-563`): grid coordinates (`:512-516`), then
liquid vx/vy/vz (`:518-535`), then gas vx/vy/vz when multiphase (`:537-555`),
then `MATERIAL_ID` as an integer dataset (`:558-563`).

### 4.3 Units

Velocities are converted from internal (per-second) to per-`TIME_UNITS` inside
`OutputGetCellCenteredVelocities` (`src/pflotran/output_common.F90:340`) —
`vec_x_ptr(:) = velocities(X_DIRECTION,:)*realization_base%output_option%tconv`
(`:376`, Y at `:377`, Z at `:378`) — which is why the header says `m/<tunit>`.
The face-to-center averaging is done by `PatchGetCellCenteredVelocities` (called
at `:370`); I did not read that routine, so the averaging scheme is not
documented here.

---

## 5. Shared variable-resolution helpers (`output_common.F90`)

| Routine | Line | Role |
|---|---|---|
| `OutputFilenameID` / `OutputFilename` | `:72` / `:110` | zero-padded plot-number string; full output filename |
| **`OutputGetVariableArray`** | **`:158`** | variable → PETSc `Vec`; body is a single `RealizationGetVariable(realization_base,vec,variable%ivar,variable%isubvar,variable%isubsubvar)` (`:181-182`). Used by Tecplot BLOCK (`src/pflotran/output_tecplot.F90:289`) and both HDF5 paths (`src/pflotran/output_hdf5.F90:171`, `:591`) |
| `OutputConvertArrayToNatural` | `:191` | local → natural ordering for raw arrays |
| `OutputGetVariableAtCell` / `...AtCoord` | `:241` / `:269` | scalar at one ghosted cell (`:260-263`) / at an (x,y,z) |
| **`OutputGetCellCenteredVelocities`** | **`:340`** | wraps `PatchGetCellCenteredVelocities` (`:370`), applies `× tconv` (`:376-378`) |
| `OutputGetCellCoordinates` / `OutputGetVertexCoordinates` | `:392` / `:437` | coordinate Vecs |
| `OutputGetCellVertices` / `...Explicit` | `:513` / `:605` | connectivity |
| `OutputXMFHeader` / `Attribute` / `Footer` | `:701` / `:840` / `:813` | XDMF emission |
| `OutputGetFaceVelUGrid` / `OutputGetFaceFlowrateUGrid` | `:883` / `:1184` | face quantities |
| `OutputCollectVelocityOrFlux` | `:1812` | face gather for the flux writer |

Note the asymmetry: BLOCK and HDF5 go through `OutputGetVariableArray`, while
`OutputTecplotPoint` calls `RealizGetVariableValueAtCell` **directly**
(`src/pflotran/output_tecplot.F90:1004-1007`) rather than through the
`OutputGetVariableAtCell` wrapper. Same underlying accessor, different call path.

---

## 6. VTK, briefly

`FORMAT VTK` sets `print_vtk` (`src/pflotran/output.F90:510`) and is rejected
inside `OBSERVATION_FILE` (`src/pflotran/output.F90:502-508`). A separate
acknowledgment keyword `ACKNOWLEDGE_VTK_FLAW` exists
(`src/pflotran/output.F90:516-517`). Files are `<prefix>-<NNN>.vtk`
(`src/pflotran/output_vtk.F90:65`) and `<prefix>-vel-<NNN>.vtk`
(`:196`), the latter using dataset names `Vlx`, `Vly` (`:226`, `:237`).

## 7. Not found in this tree

- No `-surf` or surface-flow output file: grep for `surf` in `output_tecplot.F90`,
  `output_hdf5.F90`, `output_common.F90`, `output_vtk.F90` returns nothing, and
  no `output_surface.F90` exists. The comment fragment
  `! in Output_Surface_module` at `src/pflotran/output_common.F90:20` refers to a
  module absent from this flat tree.
- `'-domain'` appears only as `'-domain.h5'`
  (`src/pflotran/output_hdf5.F90:911`); there is no `-domain.tec`.
