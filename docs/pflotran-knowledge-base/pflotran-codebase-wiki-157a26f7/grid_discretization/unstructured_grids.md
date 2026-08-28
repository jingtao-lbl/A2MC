**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** Unstructured grids — the `GRID` card, `.ugi` / HDF5 mesh formats, side sets, parallel decomposition, connectivity geometry
**Last verified:** 2026-07-31

---

## 1. The `GRID` card

`GRID` is a required block in the `SUBSURFACE` section. It is read **twice**:

| Pass | Entry point | Caller |
|---|---|---|
| 1 (required cards) | `DiscretizationReadRequiredCards()` (`src/pflotran/discretization.F90:121`) | `src/pflotran/factory_subsurface_read.F90:744` |
| 2 (everything else) | `DiscretizationRead()` (`src/pflotran/discretization.F90:324`) | `src/pflotran/factory_subsurface_read.F90:1081` |

Pass 1 needs only `TYPE`, `NXYZ` and `ORIGIN`; it skips `DXYZ`/`BOUNDS` bodies (`src/pflotran/discretization.F90:243-244`) and silently accepts (as no-ops) a list of keywords it defers to pass 2 (`src/pflotran/discretization.F90:238-242`). At the end of pass 1 the grid object is allocated and the mesh file is read (`src/pflotran/discretization.F90:257-317`). The `patch_type` is created immediately afterward (`src/pflotran/factory_subsurface_read.F90:746-751`).

### 1.1 `TYPE` — the complete valid list at this commit

Parsed in `src/pflotran/discretization.F90:175-216`:

| `TYPE` keyword | `discretization%itype` | `grid%itype` | `grid%ctype` |
|---|---|---|---|
| `STRUCTURED` [`CARTESIAN`\|`CYLINDRICAL`\|`SPHERICAL`] | `STRUCTURED_GRID` | `STRUCTURED_GRID` | `STRUCTURED` |
| `UNSTRUCTURED <file>` | `UNSTRUCTURED_GRID` | `IMPLICIT_UNSTRUCTURED_GRID` | `IMPLICIT UNSTRUCTURED` |
| `UNSTRUCTURED_EXPLICIT <file>` | `UNSTRUCTURED_GRID` | `EXPLICIT_UNSTRUCTURED_GRID` | `EXPLICIT UNSTRUCTURED` |
| `UNSTRUCTURED_POLYHEDRA <file>` | `UNSTRUCTURED_GRID` | `POLYHEDRA_UNSTRUCTURED_GRID` | `POLYHEDRA UNSTRUCTURED` |
| `ECLIPSE <file>` | `UNSTRUCTURED_GRID` | `ECLIPSE_UNSTRUCTURED_GRID` | `ECLIPSE UNSTRUCTURED` |

Anything else triggers `InputKeywordUnrecognized(...,'discretization type',...)` (`src/pflotran/discretization.F90:213-215`). The integer constants are defined in `src/pflotran/pflotran_constants.F90:259-265` (`NULL_GRID=0`, `STRUCTURED_GRID=1`, `UNSTRUCTURED_GRID=2`, `IMPLICIT_UNSTRUCTURED_GRID=3`, `EXPLICIT_UNSTRUCTURED_GRID=4`, `POLYHEDRA_UNSTRUCTURED_GRID=5`, `ECLIPSE_UNSTRUCTURED_GRID=6`).

Note the two-level typing: `discretization%itype` is only ever `STRUCTURED_GRID` or `UNSTRUCTURED_GRID`; the implicit/explicit/polyhedra/Eclipse distinction lives in `grid%itype` (comment at `src/pflotran/discretization.F90:22-23`).

Choosing an unstructured type also changes a **material default**: the permeability-tensor-to-scalar model is forced to `TENSOR_TO_SCALAR_POTENTIAL` for unstructured grids (`src/pflotran/discretization.F90:263`) versus `TENSOR_TO_SCALAR_LINEAR` for structured (`src/pflotran/discretization.F90:301`). It can be overridden in pass 2 with `PERM_TENSOR_TO_SCALAR_MODEL` (`src/pflotran/discretization.F90:546-567`).

### 1.2 How the mesh filename argument is consumed

The filename is the **second token on the `TYPE` line**, read with `InputReadFilename` into `discretization%filename` (`src/pflotran/discretization.F90:211-212`). Dispatch to a reader is by **substring test on the filename**, not by a separate keyword:

```
IMPLICIT_UNSTRUCTURED_GRID   index(filename,'.h5') > 0  ->  UGridReadHDF5()   else  UGridRead()
EXPLICIT_UNSTRUCTURED_GRID   index(filename,'.h5') > 0  ->  UGridExplicitReadHDF5()  else  UGridExplicitRead()
POLYHEDRA_UNSTRUCTURED_GRID  index(filename,'.h5') > 0  ->  hard error 'Add UGridPolyhedraReadHDF5'  else  UGridPolyhedraRead()
ECLIPSE_UNSTRUCTURED_GRID    always GridEclipseRead()
```
(`src/pflotran/discretization.F90:266-297`.)

Consequences worth knowing:

- The test is `index(...) > 0`, i.e. `.h5` **anywhere** in the path. A directory named `foo.h5/` would misroute.
- There is **no other filename-based dispatch**. Suffixes such as `_ugi`, `_ref_`, `.ugi` carry **no meaning to PFLOTRAN**. In the motivating case, `mesh_rotated10_0.025_ugi.h5` is read by `UGridReadHDF5` purely because it contains `.h5`; `mesh.ugi` would be read by `UGridRead`; and `mesh_ref_ugi.h5` is just another HDF5 implicit mesh under a different user-chosen name. A grep of `src/pflotran/*.F90` for `_ref_` returns only unrelated hits (`eos_gas.F90`, `eos_water.F90`, `material.F90`) — nothing in the grid path. Treat `_ref_` as a **user naming convention** (conventionally "refined"), unverifiable from source.
- HDF5 support for `UNSTRUCTURED_POLYHEDRA` is **not implemented** at this commit — passing a `.h5` file aborts with `'Add UGridPolyhedraReadHDF5'` (`src/pflotran/discretization.F90:287`).

### 1.3 Grid-related deck keywords and their defaults

Read in pass 2, `src/pflotran/discretization.F90:371-598`. Defaults come from `DiscretizationCreate()` (`src/pflotran/discretization.F90:72-117`) and `UGridCreate()` (`src/pflotran/grid_unstructured_aux.F90:255-283`).

| Keyword | Applies to | Argument | Default | Source |
|---|---|---|---|---|
| `TYPE` | all | see §1.1 | none (fatal if `GRID` block leaves `itype == NULL_GRID`) | `discretization.F90:171-216`, `:251-255` |
| `NXYZ nx ny nz` | structured | 3 ints | none; fatal if `nx*ny*nz <= 0` | `discretization.F90:217-227`, `:302-303` |
| `ORIGIN x y z` | all | 3 reals | `0,0,0` | `discretization.F90:228-237`, `:89` |
| `DXYZ` / `BOUNDS` | structured only | block | — (`DXYZ` on an unstructured grid is a hard error) | `discretization.F90:373-381` |
| `GRAVITY gx gy gz` | all | 3 reals | set elsewhere in `option%gravity`; this card overwrites it | `discretization.F90:472-483` |
| `MAX_CELLS_SHARING_A_VERTEX n` | unstructured | int | `24` | `discretization.F90:484-490`; default `grid_unstructured_aux.F90:263` |
| `STENCIL_WIDTH n` | structured DM | int | `1` | `discretization.F90:492-495`; default `:110` |
| `STENCIL_TYPE BOX\|STAR` | structured DM | word | `DMDA_STENCIL_STAR` | `discretization.F90:496-508`; default `:111` |
| `DOMAIN_FILENAME <file>` | explicit / Eclipse only | filename | `''` | `discretization.F90:509-520` |
| `UPWIND_FRACTION_METHOD FACE_CENTER_PROJECTION\|CELL_VOLUME\|ABSOLUTE_DISTANCE` | unstructured only (fatal on structured) | word | `UGRID_UPWIND_FRACTION_PT_PROJ` (= `FACE_CENTER_PROJECTION`) | `discretization.F90:521-544`; default `grid_unstructured_aux.F90:277` |
| `PERM_TENSOR_TO_SCALAR_MODEL LINEAR\|FLOW\|POTENTIAL\|FLOW_FULL_TENSOR\|POTENTIAL_FULL_TENSOR` | all | word | `POTENTIAL` for unstructured, `LINEAR` for structured | `discretization.F90:546-567`, `:263`, `:301` |
| `2ND_ORDER_BOUNDARY_CONDITION` | structured only (fatal otherwise) | flag | `PETSC_FALSE` | `discretization.F90:569-575` |
| `IMPLICIT_GRID_AREA_CALCULATION TRUE_AREA\|PROJECTED_AREA` | unstructured | word | `PROJECTED_AREA` (`project_face_area_along_normal = PETSC_TRUE`) | `discretization.F90:576-592`; default `grid_unstructured_aux.F90:278` |
| `RIGHT_HAND_RULE_CHECK_ALL` | unstructured | flag | `PETSC_FALSE` | `discretization.F90:593-595`; default `grid_unstructured_aux.F90:279` |
| `FILE` | — | — | **parsed and discarded in both passes** | `discretization.F90:238`, `:372` |
| `INVERT_Z` | structured | flag | **parsed and discarded** | see below |

Two keywords are inert at this commit, and this is worth flagging because both look load-bearing:

- **`FILE`** appears only in the no-op case lists of both read passes (`src/pflotran/discretization.F90:238` and `:372`). It never sets anything. A mesh filename must go on the `TYPE` line.
- **`INVERT_Z`** is accepted (`src/pflotran/discretization.F90:491`) with an empty body. `grep -rn "INVERT_Z" src/pflotran/*.F90` returns exactly those two lines. `structured_grid%invert_z_axis` is initialized `PETSC_FALSE` (`src/pflotran/grid_structured.F90:192`) and never assigned anywhere in the tree, so the `invert_z_axis` branches at `src/pflotran/discretization.F90:604` and `src/pflotran/grid_structured.F90:1242,1270` are dead at this commit.

---

## 2. Unstructured mesh formats

### 2.1 The `.ugi` ASCII implicit mesh — exact layout

Read by `UGridRead()` (`src/pflotran/grid_unstructured.F90:44-276`). The layout is documented in-source at `src/pflotran/grid_unstructured.F90:86-103` and in `src/pflotran/README_unstructured.txt`, and is confirmed by the parser:

```
<num_cells> <num_vertices>                 ! line 1, two integers
<type> <v1> <v2> ... <vn>                  ! one line per cell, cell 1 .. num_cells
...
<x> <y> <z>                                ! one line per vertex, vertex 1 .. num_vertices
...
```

- Line 1: `num_cells` -> `unstructured_grid%nmax`, `num_vertices` -> `num_vertices_global` (`src/pflotran/grid_unstructured.F90:112-116`).
- Element type code is a **word**, upper-cased before matching (`src/pflotran/grid_unstructured.F90:146-148`). Accepted codes and their vertex counts (`src/pflotran/grid_unstructured.F90:149-164`):

| Code | Element | Vertices read |
|---|---|---|
| `H` | hexahedron | 8 |
| `W` | wedge / prism | 6 |
| `P` | pyramid | 5 |
| `T` | tetrahedron | 4 |
| `Q` | quadrilateral (2-D cell) | 4 |

  Anything else is fatal: `'Unrecognized element type "<x>" in <file>.'` (`src/pflotran/grid_unstructured.F90:160-163`). Note that `src/pflotran/README_unstructured.txt` says pyramids are "not yet supported" — the reader at this commit **does** accept `P` and `PYR_TYPE` exists (`src/pflotran/grid_unstructured_cell.F90:15`), so the README text is stale for the read path. `Q` is not listed in the README at all.
- Vertex ids are **1-based** as written in the file (the reader subtracts 1 only later, for PETSc: `src/pflotran/grid_unstructured.F90:698-700`).
- Only `num_vertices` integers are consumed per cell line; a hexahedron line has 8, a tet line has 4. Trailing text on the line is ignored, which is why comments work.
- Vertex block: exactly 3 doubles per line, x y z (`src/pflotran/grid_unstructured.F90:236-239`).

Worked example from this tree, `regression_tests/hydrate/mesh.ugi` (50 hexes, 132 vertices, 183 lines = 1 header + 50 cells + 132 vertices):

```
50 132
H 1 2 8 7 13 14 20 19
H 2 3 9 8 14 15 21 20
...
5.000000e+01 1.000000e+01 5.000000e+02
```

Mixed-element example with trailing comments, `shortcourse/exercises/implicit_grid/mixed.ugi`:

```
15 24
P 4 5 6 2 1 #Top
T 4 3 5 1
W 2 7 6 4 9 5 #Top
```

**Reading is serial-then-scatter.** The I/O rank opens the file and reads every cell, MPI_Send-ing each rank's slice (`src/pflotran/grid_unstructured.F90:134-208`); vertices likewise (`:227-257`). Cells are split as evenly as possible with the remainder spread over the first `remainder` ranks (`src/pflotran/grid_unstructured.F90:119-124`). `max_nvert_per_cell` is hard-set to 8 before reading (`src/pflotran/grid_unstructured.F90:84`), so an 8-vertex hexahedron is the largest cell the ASCII reader can hold.

### 2.2 The HDF5 implicit mesh — exact layout

Read by `UGridReadHDF5()` (`src/pflotran/grid_unstructured.F90:280-552`). Two datasets are required, both rank-2:

| Dataset | Shape (HDF5 `dims_h5`) | Type | Meaning |
|---|---|---|---|
| `Domain/Cells` | `(1+max_nvert, num_cells)` | native integer | column *i* = `[nvert, v1, v2, ..., vnvert, ...]` |
| `Domain/Vertices` | `(3, num_vertices)` | native double | column *i* = `[x, y, z]` |

- Both are opened by literal path: `h5dopen_f(file_id, "Domain/Cells", ...)` (`src/pflotran/grid_unstructured.F90:345`) and `"Domain/Vertices"` (`:459`). A group named `Domain` is expected (`:340`).
- Each is checked to be exactly 2-dimensional, otherwise fatal (`src/pflotran/grid_unstructured.F90:352-356`, `:466-470`).
- `nmax` = `dims_h5(2)` of `Domain/Cells` (`src/pflotran/grid_unstructured.F90:367`); `num_vertices_global` = `dims_h5(2)` of `Domain/Vertices` (`:481`).
- **The first entry of each cell column is the vertex count, not a type code.** Only `4, 5, 6, 8` are legal; anything else is reported per-rank (first 10 offenders) and then fatal `'Unknown cell types in <file>.'` (`src/pflotran/grid_unstructured.F90:420-439`). The remaining entries `2 .. nvert+1` are the vertex ids (`:441-445`).
- `max_nvert_per_cell` is fixed at 8 here too (`src/pflotran/grid_unstructured.F90:319`, `:548`).
- Reads are **collective hyperslab** reads — each rank reads its own contiguous column range computed from `MPI_Exscan`/`MPI_Scan` (`src/pflotran/grid_unstructured.F90:378-399`), with `H5FD_MPIO_COLLECTIVE_F` unless built `SERIAL_HDF5` (`:406-409`). HDF5 (`h5dopen_f`, `h5sselect_hyperslab_f`, `h5dread_f`) is an **external library**, not PFLOTRAN code.

So the HDF5 form is the same information as `.ugi` with the letter type code replaced by an integer vertex count, and with parallel-direct reads instead of read-on-rank-0-and-send. For a large mesh (the 0.025 m rotated mesh in the motivating case), the HDF5 form is the one that scales.

### 2.3 Other unstructured formats (for orientation)

- **`UNSTRUCTURED_EXPLICIT`** (`.uge`-style ASCII), `UGridExplicitRead()` (`src/pflotran/grid_unstructured_explicit.F90:30`), format documented at `src/pflotran/grid_unstructured_explicit.F90:67-91`:
  ```
  CELLS <N>
  id x y z volume        (x N)
  CONNECTIONS <M>
  id_up id_dn x y z area (x M)
  ```
  No vertices at all — geometry is supplied directly, so no connectivity is derived.
- **`ECLIPSE`** reads a GRDECL deck via `GridEclipseRead()` (`src/pflotran/grid_eclipse.F90:336`), which parses on the I/O rank only (`src/pflotran/grid_eclipse.F90:378-380`) and then populates the same `explicit_grid` structure.
- **`UNSTRUCTURED_POLYHEDRA`** is handled in `src/pflotran/grid_unstructured_polyhedra.F90` (ASCII only, see §1.2).

---

## 3. Side sets: `.ss` files and `REGION ... FILE`

This is how the motivating case defines `top`, `east`, `west`, `north`, `south`, `bottom`.

### 3.1 Binding a region to a file

`REGION <name>` is parsed by `RegionRead()` (`src/pflotran/region.F90:400-599`). The `FILE` keyword only stores the filename — it does not read or classify it (`src/pflotran/region.F90:550-552`).

Classification happens later, in `InitCommonReadRegionFiles()` (`src/pflotran/init_common.F90:233-273`), again by **filename substring**:

| Filename contains | `region%def_type` | Reader |
|---|---|---|
| `.h5` | from HDF5 contents (`Cell Ids` / `Face Ids` / `Vertex Ids`) | `HDF5ReadRegionFromFile` / `HDF5ReadRegionDefinedByVertex` (`init_common.F90:237-254`) |
| `.ss` | `DEFINED_BY_SIDESET_UGRID` | `RegionReadSideSet` via the `RegionReadFromFile` interface (`init_common.F90:255-259`) |
| `.ex` | `DEFINED_BY_FACE_UGRID_EXP` | `RegionReadExplicitFaceSet` (`init_common.F90:260-266`) |
| anything else | cell-id list or cell-id+face-id list | `RegionReadFromFileId` (`init_common.F90:267-269`) |

So **the `.ss` extension is load-bearing**: rename `mesh_ugi_top.ss` to `mesh_ugi_top.txt` and PFLOTRAN will try to parse it as a cell-id list and fail. The `def_type` constants are at `src/pflotran/region.F90:14-23`.

Deck form, from `regression_tests/hydrate/hydrate-co2-multi-well-np2.in:209-217`:

```
REGION top
  FACE TOP
  FILE mesh_ugi_top.ss
END
```

`FACE TOP` sets `region%iface = TOP_FACE` (`src/pflotran/region.F90:586-587`). For a side-set region the face id actually used comes from the side-set mapping, not from `FACE`; `FACE` is required for polygon-defined boundary regions on structured grids (`src/pflotran/grid.F90:718-725`) and is otherwise metadata.

### 3.2 The `.ss` file format — exact layout

Read by `RegionReadSideSet()` (`src/pflotran/region.F90:833-990`); layout documented in-source at `src/pflotran/region.F90:870-881`:

```
<num_faces>                    ! line 1, one integer
<type> <v1> <v2> ... <vn>      ! one line per face, face 1 .. num_faces
```

- `num_faces` -> `sideset%nfaces` (`src/pflotran/region.F90:890`).
- Face type code, upper-cased (`src/pflotran/region.F90:921-923`), with vertex counts (`src/pflotran/region.F90:924-936`):

| Code | Face | Vertices read |
|---|---|---|
| `Q` | quadrilateral | 4 |
| `T` | triangle | 3 |
| `L` | line (2-D meshes) | 2 |

  Any other code is fatal: `'Unknown face type "<x>" in sideset file "<file>". Please use "Q" (quadrilateral) or "T" (triangle).'` (`src/pflotran/region.F90:931-935`). Note `L` is accepted by the parser but omitted from that message.
- Vertex ids are **global/natural, 1-based**, referring to the mesh file's vertex numbering.
- Storage is `face_vertices(4, nfaces_local)`; `max_nvert_per_face` is a hard-coded parameter `4` (`src/pflotran/region.F90:857`, `:901-903`). Unused slots stay `UNINITIALIZED_INTEGER`.
- Same read-on-io_rank-and-MPI_Send distribution as `.ugi` (`src/pflotran/region.F90:907-983`); each rank's local `sideset%nfaces` is overwritten with its own slice count (`:949`, `:976`).

Worked example, `regression_tests/hydrate/mesh_ugi_top.ss` (6 lines):

```
5
Q 121 122 128 127
Q 122 123 129 128
Q 123 124 130 129
...
```

and `shortcourse/exercises/implicit_grid/west.ss`:

```
4
Q 24 20 19 23
Q 19 17 16 12
Q 20 18 17 19
```

### 3.3 How a side set becomes boundary faces

`GridLocalizeRegions()` dispatches `DEFINED_BY_SIDESET_UGRID` to `UGridMapSideSet2()` (`src/pflotran/grid.F90:671-683`). Two hard constraints:

1. **Implicit unstructured only.** `'Regions defined through sidesets are only supported for IMPLICIT_UNSTRUCTURED_GRIDS.'` (`src/pflotran/grid.F90:672-676`).
2. **Faces must be boundary faces**, i.e. attached to exactly one cell.

The mapping algorithm (`src/pflotran/grid_unstructured.F90:2870-3175`) is a sparse-matrix match, not a search:

1. Count local boundary faces — those whose `face_to_cell_ghosted(2, face_id) < 1` (`src/pflotran/grid_unstructured.F90:2935-2945`).
2. Build `Mat_vert_to_face` (local boundary faces x global vertices), one 1.0 per incident vertex (`:2947-2951`).
3. Build the region's face-to-vertex matrix from the `.ss` contents and multiply: `MatMatMult(Mat_vert_to_face, Mat_region_face_to_vert, ...)` (`:3070-3071`).
4. A local boundary face matches a side-set face when the product entry reaches `min_nverts` — 3 for a 3-D grid, 2 for a 2-D grid (`:3105-3107`). Matched faces populate `region%cell_ids` and `region%faces` (`:3125-3144`).
5. A global check requires **every** side-set face to have been matched exactly once, otherwise:
   `'The number of faces mapped in UGridMapSideSet2 (<n>) does not match the number of faces in REGION "<name>" (<m>). Perhaps there are non-boundary faces included in the region. A boundary face must be connected to a single grid cell.'` (`src/pflotran/grid_unstructured.F90:3162-3172`).

Note the threshold in step 4 is `>= 3` shared vertices even for quadrilateral faces, so a quad face matches on 3 of 4 vertices. `region%num_cells` is then `size(region%cell_ids)` (`src/pflotran/grid.F90:681-683`), and an empty region anywhere in the communicator is fatal: `'No cells assigned to REGION "<name>".'` (`src/pflotran/grid.F90:764-770`).

The older `UGridMapSideSet()` (`src/pflotran/grid_unstructured.F90:2558`) is still exported but is not the routine `GridLocalizeRegions` calls.

### 3.4 The `.ex` explicit face-set format (for contrast)

`RegionReadExplicitFaceSet()` (`src/pflotran/region.F90:994`), layout at `src/pflotran/region.F90:1024-1040`:

```
CONNECTIONS <M>
id x y z area     (x M)
```

i.e. cell id plus face centroid and area, no vertices. Only valid for `EXPLICIT_UNSTRUCTURED_GRID` / `ECLIPSE_UNSTRUCTURED_GRID` (`src/pflotran/grid.F90:684-691`).

---

## 4. Parallel decomposition, ordering and ghosting

### 4.1 Decomposition

`DiscretizationDecomposeDomain()` (`src/pflotran/discretization.F90:619-678`) routes by `grid%itype`:

| `grid%itype` | routine | build requirement |
|---|---|---|
| `IMPLICIT_UNSTRUCTURED_GRID` | `UGridDecompose` | ParMETIS required (`discretization.F90:640-644`) |
| `EXPLICIT_UNSTRUCTURED_GRID` | `UGridExplicitDecompose` | ParMETIS **or** PTScotch (`:648-652`) |
| `POLYHEDRA_UNSTRUCTURED_GRID` | `UGridPolyhedraDecompose` | ParMETIS (`:655-659`) |
| `ECLIPSE_UNSTRUCTURED_GRID` | `UGridExplicitDecompose` | ParMETIS or PTScotch (`:662-666`) |
| `STRUCTURED_GRID` | nothing (PETSc `DMDA` owns it) | — |

`UGridDecompose()` (`src/pflotran/grid_unstructured.F90:556-1199`):

1. Flatten local cell->vertex lists to 0-based CSR (`:694-703`).
2. Two cells are adjacent if they share `num_common_vertices` = 3 in 3-D, 2 in 2-D (`:705-713`).
3. `MatCreateMPIAdj` builds the adjacency matrix (`:725-728`) — **PETSc**.
4. `MatMeshToCellGraph` forms the dual graph, guarded by `PETSC_HAVE_PARMETIS` (`:749-752`) — **PETSc/ParMETIS**.
5. `UGridPartition()` (`src/pflotran/grid_unstructured_aux.F90:1031-1106`) runs `MatPartitioningCreate` / `SetAdjacency` / `SetFromOptions` / `Apply` (`:1068-1076`) — so the partitioner is selectable at runtime via PETSc options. `ISPartitioningCount` gives the new per-rank cell count (`:1096-1097`), and a rank receiving zero cells is fatal: `'A processor core has been assigned zero cells.'` (`:1102`).
6. Cells/vertices/duals are scattered to their new owners packed in a strided PETSc `Vec` with `-777` / `-888` / `-999` separators; the packing and the full 28-step sequence are described in `src/pflotran/README_unstructured.txt`.
7. Cell type is finally inferred from the stored vertex count, **not** from the file's letter code (`src/pflotran/grid_unstructured.F90:1162-1197`): 8->`HEX_TYPE`, 6->`WEDGE_TYPE`, 5->`PYR_TYPE`, 4->`TET_TYPE` in 3-D; 4->`QUAD_TYPE`, 3->`TRI_TYPE` in 2-D.

`MAX_CELLS_SHARING_A_VERTEX` sizes the `vertex_to_cell` table (`src/pflotran/grid_unstructured.F90:1276`); exceeding it is fatal with `'Vertex can be shared by at most by <n> cells. Rank = ... vertex_id = ... exceeds it.'` (`:1522-1528`). Raise the card if a fine tetrahedral mesh trips it.

### 4.2 The three index spaces

Defined and documented on `grid_type` (`src/pflotran/grid.F90:32-61`):

- **local** — non-ghosted cells owned by this rank, `1 .. nlmax`; matches a `DMCreateGlobalVector` array.
- **ghosted local** — owned plus ghost copies, `1 .. ngmax`; matches a `DMCreateLocalVector` array.
- **natural** — the global cell numbering as it appears in the mesh file, `1 .. nmax`.

Mapping arrays: `nL2G` (local->ghosted), `nG2L` (ghosted->local), `nG2A` (ghosted->natural) (`src/pflotran/grid.F90:60-61`). For unstructured grids the natural<->PETSc permutation is carried by the PETSc `AO` object `ao_natural_to_petsc` and by `cell_ids_natural` / `cell_ids_petsc` (`src/pflotran/grid_unstructured_aux.F90:31-34`). Region cell ids given in a deck are natural and are converted through the `AO` (see `UGridAddWellCells` for the pattern, `src/pflotran/grid_unstructured_aux.F90:2383-2389`).

### 4.3 Output ordering (relevant to reading Tecplot cell fields)

Output is written from a **natural-ordered** vector, not a PETSc-ordered one. `output_tecplot.F90` creates `natural_vec` with `DiscretizationCreateVector(..., NATURAL, ...)` (`src/pflotran/output_tecplot.F90:275`), fills it via `DiscretizationGlobalToNatural(...)` (`:290-291`) and only then writes (`:294-297`); the same pattern is used for velocities (`:505-543`).

`DiscretizationGlobalToNatural()` (`src/pflotran/discretization.F90:1210-1242`) uses `DMDAGlobalToNatural{Begin,End}` for structured grids and the unstructured DM's `scatter_gton` `VecScatter` otherwise — both **PETSc**.

**Practical consequence:** cell-indexed output values come out in natural order, i.e. in the same order the cells appear in the mesh file (line 2 of a `.ugi` = cell 1 = first output value; column 1 of `Domain/Cells` = cell 1). Output ordering is therefore independent of the number of MPI ranks and of the ParMETIS partition. This is what makes extraction from Tecplot cell fields reproducible across rank counts.

---

## 5. Connectivity and geometry for the flux terms

### 5.1 The `connection_set_type` contract

`src/pflotran/connection.F90:16-36`. Per connection:

| Field | Meaning |
|---|---|
| `id_up(:)`, `id_dn(:)` | ghosted ids of upwind / downwind cell |
| `id_up2(:)`, `id_dn2(:)` | second-order (TVD) neighbours, allocated only for higher-order advection |
| `dist(-1:3,:)` | `-1` = fraction upwind, `0` = distance magnitude, `1:3` = unit vector |
| `area(:)` | face area normal to the distance vector |
| `intercp(1:3,:)` | intersection of the up->dn line with the shared face |
| `cntr(1:3,:)` | face mass-centre coordinates |
| `face_id(:)` | local face id |

`intercp` and `face_id` are allocated **only** for `IMPLICIT_UNSTRUCTURED_GRID` and `POLYHEDRA_UNSTRUCTURED_GRID` (`src/pflotran/connection.F90:106-112` internal, `:120-126` boundary). Connection types are `INTERNAL_FACE_CONNECTION_TYPE=1`, `BOUNDARY_FACE_CONNECTION_TYPE=2`, `GENERIC_CONNECTION_TYPE=3` (`src/pflotran/connection.F90:12-14`).

### 5.2 What the flux kernels consume

`ConnectionCalculateDistances()` (`src/pflotran/connection.F90:241-274`) is the single place the `dist` array is unpacked:

```
distance_gravity  = dist(0) * dot_product(gravity, dist(1:3))
distance_upwind   = dist(0) * dist(-1)
distance_downwind = dist(0) - distance_upwind
upwind_weight     = distance_downwind / (distance_upwind + distance_downwind)
```

So the **gravity projection is the connection length times the component of the gravity vector along the connection unit vector** (`src/pflotran/connection.F90:265-266`). The gravity vector itself is `option%gravity`, settable by `GRID / GRAVITY` (`src/pflotran/discretization.F90:472-478`).

### 5.3 Internal connections on an implicit unstructured grid

`UGridComputeInternConnect()` (`src/pflotran/grid_unstructured.F90:1203-1847`), per shared face:

- **Face area.** The face is split into triangles; each contributes `0.5*|v1 x v2|` (`src/pflotran/grid_unstructured.F90:1671-1677`, and `:1686-1697` for the second triangle of a quad). If `project_face_area_along_normal` is true (the default, `PROJECTED_AREA`), each triangle area is multiplied by `|n_i . n_up_dn|`, the cosine between the face normal and the unit vector between cell centres (`:1678-1681`, `:1698-1699`). Under `IMPLICIT_GRID_AREA_CALCULATION TRUE_AREA` the projection is skipped. `connection%area = area1 + area2` (`:1730`).
- **Distances.** The up->dn segment is intersected with the face plane (`GeometryGetPlaneIntercept`, `src/pflotran/grid_unstructured.F90:1663`; for quads the two triangle-plane intercepts are averaged, `:1704-1712`). Then
  `dist(-1) = dist_up/(dist_up+dist_dn)`, `dist(0) = dist_up+dist_dn`, `dist(1:3) = normalize(v1+v2)` (`:1716-1729`), where `v1` runs cell-centre-up -> intercept and `v2` intercept -> cell-centre-dn. The in-source comment calls this "very crude" (`:1715`).
- **Line faces** (2-D meshes) use a line intercept and `area = |point1 - point2|` (`src/pflotran/grid_unstructured.F90:1615-1640`).
- **Stored per-face geometry.** `face_area(face_id)` is filled separately as the **unprojected true area** — `0.5*|n1|` plus `0.5*|n2|`, with no dot-product factor (`src/pflotran/grid_unstructured.F90:1790-1805`). `face_centroid` is the arithmetic mean of the face's vertices (`:1807-1828`). This asymmetry matters: **internal connections may use a projected area while boundary connections use the true area** (§5.5).

### 5.4 Upwind fraction alternatives

`UGridCalculateDist()` (`src/pflotran/grid_unstructured_aux.F90:2290-2353`) implements the three `UPWIND_FRACTION_METHOD` options for the explicit/Eclipse path:

| Method | `upwind_fraction` | Source |
|---|---|---|
| `FACE_CENTER_PROJECTION` (default) | `|proj(v_up onto up->dn)| / |up->dn|` | `grid_unstructured_aux.F90:2310-2340` |
| `CELL_VOLUME` | `vol_up / (vol_up + vol_dn)` | `:2341-2342` |
| `ABSOLUTE_DISTANCE` | `|v_up| / (|v_up| + |v_dn|)` | `:2343-2347` |

The default method also validates the geometry, warning per-rank if the face centre cannot be projected onto the inter-centre vector (`upwind_fraction > 1` or a negative component), with the message ending `'Please check the location of the cell centers and face center.'` (`:2315-2339`). Coincident cell centres (`distance < 1.d-40`) produce `'Coincident cell centers at (...)'` (`:2294-2306`).

### 5.5 Boundary connections

`GridPopulateConnection()` (`src/pflotran/grid.F90:351-394`) dispatches to `UGridPopulateConnection()` for implicit unstructured grids. There (`src/pflotran/grid_unstructured.F90:1850-1950`):

- The cell centroid is recomputed from the cell's vertices via `UCellComputeCentroid` (`:1893-1902`).
- The centroid is **projected perpendicularly onto the boundary face's plane** (`GeometryProjectPointOntoPlane`, `:1927-1928`) — i.e. the shortest distance to the face, not the distance to the face centroid. The in-source comment at `:1903-1904` says this deliberately.
- `dist(0) = |cell_centre - intercept|`, `dist(1:3)` = that vector normalized, so the **boundary unit vector points from the face toward the cell centre** (`:1931-1941`).
- `connection%area = unstructured_grid%face_area(face_id)` — the **true, unprojected** face area (`:1942`).
- `dist(-1)` is never assigned for boundary connections, so it keeps the `ConnectionCreate` initialization of `0` (`src/pflotran/connection.F90:118`). Through `ConnectionCalculateDistances` that gives `distance_upwind = 0` and `upwind_weight = 1`.
- A missing face id is fatal: `'Face id undefined for cell <n> in boundary condition. Should this be a source/sink?'` (`:1886-1891`).

### 5.6 Volumes, areas, quality, and the right-hand-rule check

- `GridComputeVolumes()` -> `UGridComputeVolumes()` + `UGridComputeQuality()` for implicit unstructured (`src/pflotran/grid.F90:568-570`). Volumes come from `UCellComputeVolume` per cell type (`src/pflotran/grid_unstructured.F90:2057`).
- `GridComputeAreas()` is **implemented only for implicit unstructured 2-D meshes**; anything else is a hard error `'ERROR: GridComputeAreas only implemented for Unstructured grid'` (`src/pflotran/grid.F90:598-605`).
- `UGridEnsureRightHandRule()` (`src/pflotran/grid_unstructured.F90:2197-2376`, called from `src/pflotran/realization_subsurface.F90:418`) verifies that for every face the right-hand rule points away from the cell centroid. On failure it prints the offending cell's natural id, type, vertex list, offending face, and computed volume (or area, for 2-D cells), then aborts. If quad faces are involved the message suggests the remedy: `'Cells founds that violate right hand rule. Keyword: "RIGHT_HAND_RULE_CHECK_ALL" can be used under GRID to check all combinatons of points on face'` (`:2364-2367`). `RIGHT_HAND_RULE_CHECK_ALL` makes the test try all four vertex triples of a quad before declaring a violation (`:2271-2281`).

This check is the one most likely to bite a rotated or machine-generated mesh: vertex ordering within each `H`/`T`/`W` line must be consistent, and a mesh generator that emits a mirrored ordering will abort here rather than run with negative volumes.

---

## 6. Quick reference for the motivating case

Deck fragment implied by the case files:

```
GRID
  TYPE UNSTRUCTURED mesh_rotated10_0.025_ugi.h5
END

REGION top
  FACE TOP
  FILE mesh_ugi_top.ss
END
... (east, west, north, south, bottom likewise)
```

What PFLOTRAN actually does with it:

1. `TYPE UNSTRUCTURED` -> `IMPLICIT_UNSTRUCTURED_GRID`; filename contains `.h5` -> `UGridReadHDF5` reads `Domain/Cells` and `Domain/Vertices` (`src/pflotran/discretization.F90:266-272`). The `_ugi` and `_rotated10_0.025` parts of the name mean nothing to the code.
2. Permeability tensor->scalar model silently defaults to `POTENTIAL`, not `LINEAR` (`src/pflotran/discretization.F90:263`).
3. ParMETIS is **mandatory** for this grid type (`src/pflotran/discretization.F90:640-644`).
4. Each `.ss` gives `DEFINED_BY_SIDESET_UGRID` (`src/pflotran/init_common.F90:255-259`) and is matched to local boundary faces by `UGridMapSideSet2` (`src/pflotran/grid.F90:677-680`); every listed face must map or the run aborts (`src/pflotran/grid_unstructured.F90:3162-3172`).
5. Internal connection areas are **projected onto the inter-cell direction by default**; boundary connection areas are true areas. For a mesh rotated 10 degrees this projection is the difference between the two, so if a mass-balance comparison against an axis-aligned mesh is being made, `IMPLICIT_GRID_AREA_CALCULATION TRUE_AREA` is the switch that changes it (`src/pflotran/discretization.F90:576-592`).
6. Output cell ordering is natural = mesh-file column order, independent of rank count (`src/pflotran/output_tecplot.F90:275-297`).

---

## 7. Known uncertainties

- `_ref_` in `mesh_ref_ugi.h5` has **no meaning in source**; only `.h5` is inspected (`src/pflotran/discretization.F90:267`). Its intent (refined mesh?) cannot be determined statically.
- `src/pflotran/README_unstructured.txt` states pyramids are "not yet supported", which contradicts the `P` branch in `UGridRead` (`src/pflotran/grid_unstructured.F90:154-155`) and `PYR_TYPE` (`src/pflotran/grid_unstructured_cell.F90:15`). Whether pyramids work end-to-end (volume, faces, connectivity) was not verified here.
- The `L` (line, 2 vertices) face code in `.ss` files is accepted by the parser (`src/pflotran/region.F90:929-930`) but is absent from the error message listing valid codes and from the in-source format block (`:870-881`).
- `GRID / FILE` and `GRID / INVERT_Z` are accepted and inert at this commit (§1.3). Decks carrying them will not error, and will not get the behaviour the keyword names suggest.
- Whether a given build has ParMETIS/PTScotch/parallel HDF5 is a compile-time property (`PETSC_HAVE_PARMETIS`, `PETSC_HAVE_PTSCOTCH`, `SERIAL_HDF5`) and cannot be read from the source tree.
