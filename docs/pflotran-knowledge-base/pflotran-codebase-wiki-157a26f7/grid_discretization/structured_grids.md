**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** Structured grids — `grid_structured.F90`, the `NXYZ`/`DXYZ`/`BOUNDS` cards, DMDA decomposition, cell geometry, connections
**Last verified:** 2026-07-31

---

## 1. Scope and relationship to the unstructured path

`TYPE STRUCTURED [CARTESIAN|CYLINDRICAL|SPHERICAL]` selects `discretization%itype = STRUCTURED_GRID` and allocates a `grid_structured_type` (`src/pflotran/discretization.F90:176-191`, `:300-315`). Everything else in this document lives in `src/pflotran/grid_structured.F90` (2,128 lines). The `GRID` card mechanics, the full `TYPE` list and the shared keyword table are in `unstructured_grids.md` §1; this file covers only what is structured-specific.

Sub-types (`src/pflotran/grid_structured.F90:21-23`): `CARTESIAN_GRID = 3`, `CYLINDRICAL_GRID = 4`, `SPHERICAL_GRID = 5`. If the second token on the `TYPE` line is absent or unrecognized, it **silently defaults to `CARTESIAN`** rather than erroring (`src/pflotran/discretization.F90:188-190`).

Face constants, used by `REGION / FACE` and by boundary connections (`src/pflotran/grid_structured.F90:12-19`):

```
NULL_FACE=0  WEST_FACE=1  EAST_FACE=2  SOUTH_FACE=3  NORTH_FACE=4  BOTTOM_FACE=5  TOP_FACE=6
```

---

## 2. Defining the mesh

### 2.1 `NXYZ`

`NXYZ nx ny nz`, three integers (`src/pflotran/discretization.F90:217-223`). Dimension collapsing is automatic and silent for the curvilinear types (`src/pflotran/discretization.F90:224-227`):

- `CYLINDRICAL` forces `ny = 1`.
- `SPHERICAL` forces `ny = 1` and `nz = 1`.

`nx*ny*nz <= 0` is fatal: `'NXYZ not set correctly for structured grid.'` (`src/pflotran/discretization.F90:302-303`). Derived counts are set at `src/pflotran/discretization.F90:305-311` (`nxy = nx*ny`, `nmax = nxy*nz`).

**Ordering convention:** the global cell index runs x fastest, then y, then z. This is visible in the ghosted-id arithmetic `id = i + j*ngx + k*ngxy` (`src/pflotran/grid_structured.F90:966-967`) and in the coordinate fill loop, which nests k outermost and i innermost (`src/pflotran/grid_structured.F90:601-624`).

### 2.2 `DXYZ` — explicit per-cell spacing

Read by `StructGridReadDXYZ()` (`src/pflotran/grid_structured.F90:337-379`) as three arrays via `UtilityReadArray`: `nx` values for dx, `ny` for dy, `nz` for dz (`src/pflotran/grid_structured.F90:359-367`). The block is terminated by a line that fails `InputCheckExit`, which produces the message `'Card DXYZ should include either 3 entires (one for each grid direction or NX+NY+NZ entries)'` (`src/pflotran/discretization.F90:384-388`).

`UtilityReadArray` (real version, `src/pflotran/utility.F90:1412-1500`) supports:

- **Repeat counts** with either `*` or `@`: `10@5.d1` means ten values of 50.0 (`src/pflotran/utility.F90:1423-1441`). `10*5.d1` is identical.
- **Line continuation** with a trailing backslash (`src/pflotran/utility.F90:1416-1417`, `:1455-1457`).
- **Broadcast of a single value:** if exactly one value is supplied for a direction, it fills the whole array (`if (icount == 1) temp_array = temp_array(icount)`, `src/pflotran/utility.F90:1460-1461`). This is why the common 1-D deck form works:

```
GRID
  TYPE STRUCTURED CARTESIAN
  NXYZ 1 1 10
  DXYZ
    25.d0
    1.d0
    10@5.d1
  /
END
```
(`regression_tests/hydrate/hydrate-co2-well.in:79-87`.)

Any other count mismatch is fatal: `'Incorrect number of values read in UtilityReadRealArray() for <comment>. Expected <n> but read <m>.'` (`src/pflotran/utility.F90:1462-1475`).

`DXYZ` is rejected on unstructured grids: `'Keyword "DXYZ" not supported for unstructured grid'` (`src/pflotran/discretization.F90:378-381`).

### 2.3 `BOUNDS` — corner coordinates, uniform spacing

Read inline in `DiscretizationRead` (`src/pflotran/discretization.F90:389-471`). Exactly two data lines (min then max) between `BOUNDS` and `END`, with the number of values per line set by the sub-type (`src/pflotran/discretization.F90:399-406`):

| Sub-type | Values per line | Meaning |
|---|---|---|
| `CARTESIAN` | 3 | `x y z` |
| `CYLINDRICAL` | 2 | `r z` |
| `SPHERICAL` | 1 | `r` |

For `CYLINDRICAL` the second value is moved from the y slot to the z slot and y bounds are set to `[0,1]` (`src/pflotran/discretization.F90:418-428`). For `SPHERICAL` both y and z bounds become `[0,1]` (`:429-434`). A malformed block prints a worked example of the expected 4-line layout for the active sub-type and then `stop`s (`src/pflotran/discretization.F90:438-464`).

`BOUNDS` also **overwrites `ORIGIN`** with the lower corner (`src/pflotran/discretization.F90:465-470`).

### 2.4 `BOUNDS` and `DXYZ` are mutually exclusive

Checked at the end of pass 2: `'Only BOUNDS or DXYZ may be set in the GRID block, not both.'` (`src/pflotran/discretization.F90:609-613`).

### 2.5 Spacing resolution

`StructGridComputeSpacing()` (`src/pflotran/grid_structured.F90:383-516`) fills `dx_global/dy_global/dz_global`:

- If `DXYZ` was **not** given, spacing is derived from `BOUNDS` as `(upper-lower)/n` per direction (`src/pflotran/grid_structured.F90:420-433`). If bounds were never set either (`bounds(1,1) < -1.d19`), it is fatal: `'Bounds have not been set for grid and DXYZ does not exist'` (`:410-414`).
  - `CYLINDRICAL`: `dy_global = 1.d0` (`:438`); `SPHERICAL`: `dy_global = dz_global = 1.d0` (`:448-449`).
- If `DXYZ` **was** given, `bounds` are instead accumulated from `origin_global` plus the sum of the spacings (`src/pflotran/grid_structured.F90:452-470`, continuing for y and z).

---

## 3. Cell coordinates and geometry

### 3.1 Cell centres

`StructGridComputeCoord()` (`src/pflotran/grid_structured.F90:520-636`) writes `grid%x/y/z` for every **ghosted** cell.

- The local origin is `origin_global` plus the cumulative spacing up to the rank's starting index (`src/pflotran/grid_structured.F90:544-559`).
- Cell centres start half a spacing inside the local origin, or half a spacing outside it when the rank owns a ghost layer on that side (`istart/jstart/kstart > 0`, `src/pflotran/grid_structured.F90:594-618`), then advance by the average of adjacent spacings (`:625-634`).
- Upper local extents are taken from `bounds(...,UPPER)` rather than from the summation when the rank touches the global upper boundary. The in-source comment explains why: cumulative round-off would otherwise leave a region point on the global bound outside the domain (`src/pflotran/grid_structured.F90:568-591`).

### 3.2 Volumes

`StructGridComputeVolumes()` (`src/pflotran/grid_structured.F90:1303-1383`), where `radius => x` is the x-coordinate array:

| Sub-type | Volume | Source |
|---|---|---|
| `CARTESIAN` | `dx*dy*dz` | `grid_structured.F90:1334-1340` |
| `CYLINDRICAL` | `2*pi*r*dx*dz` | `:1341-1350` |
| `SPHERICAL` | `(4/3)*pi*dx*(r2^2 + r2*r1 + r1^2)` with `r1,2 = r -/+ dx/2` | `:1351-1359` |

On 2 to 16 ranks the routine also prints a per-rank decomposition summary (`nlmax`, `nlxyz`, `xs/e`, `ys/e`, `zs/e`) — useful for confirming how PETSc split the domain (`src/pflotran/grid_structured.F90:1364-1381`).

`GridComputeAreas()` is **not** available for structured grids: `'ERROR: GridComputeAreas only implemented for Unstructured grid'` (`src/pflotran/grid.F90:598-605`).

---

## 4. Parallel decomposition and index spaces

Unlike unstructured grids, structured grids are **not** partitioned by PFLOTRAN. `DiscretizationDecomposeDomain()` has an empty `STRUCTURED_GRID` case (`src/pflotran/discretization.F90:633-634`); PETSc's `DMDA` owns the decomposition.

`StructGridCreateDM()` (`src/pflotran/grid_structured.F90:201-244`) calls **PETSc's** `DMDACreate3D` with `DM_BOUNDARY_NONE` in all three directions, the deck's `stencil_type` and `stencil_width`, and `PETSC_DECIDE` for the process counts (`npx` initialized to `PETSC_DECIDE` at `src/pflotran/grid_structured.F90:121`; the call at `:227-233`). `DMSetFromOptions` follows, so the decomposition can be steered with PETSc command-line options (`-da_processors_x` etc.). The actual counts are read back into `npx_final/npy_final/npz_final` via `DMDAGetInfo` (`:234-241`).

There is **no `PROCESSORS` deck keyword** at this commit; `grep -rn "'PROCESSORS'" src/pflotran/*.F90` returns nothing, and `npx/npy/npz` are assigned only the `PETSC_DECIDE` initialization.

Local/ghosted extents come from `StructGridComputeLocalBounds()` (`src/pflotran/grid_structured.F90:248-302`), and the local<->ghosted<->natural mappings from `StructGridMapIndices()` (`:1387-1501`). The index-space vocabulary (`nL2G`, `nG2L`, `nG2A`, local vs ghosted local vs natural) is documented on `grid_type` at `src/pflotran/grid.F90:32-61` and is shared with the unstructured path.

**Output ordering** for structured grids uses `DMDAGlobalToNaturalBegin/End` (`src/pflotran/discretization.F90:1230-1234`), so, as with unstructured grids, cell-indexed output is in natural (i fastest, then j, then k) order regardless of rank count.

`STENCIL_TYPE STAR` (the default) versus `BOX` controls whether corner neighbours are in the ghost layer (`src/pflotran/discretization.F90:496-508`). `GridGetGhostedNeighbors()` / `GridGetGhostedNeighborsWithCorners()` (`src/pflotran/grid.F90:1332`, `:1379`) dispatch to the structured versions at `src/pflotran/grid_structured.F90:1505` and `:1581`.

---

## 5. Connections

### 5.1 Internal connections

`StructGridComputeInternConnect()` (`src/pflotran/grid_structured.F90:827-1116`). Connection count is the sum over the three directions (`src/pflotran/grid_structured.F90:861-863`):

```
nconn = (ngx-1)*nly*nlz + nlx*(ngy-1)*nlz + nlx*nly*(ngz-1)
```

For every connection, in each direction (Cartesian x-connections shown, `src/pflotran/grid_structured.F90:963-971` is the analogous spherical block; the y-direction Cartesian block is at `:1013-1023`):

```
dist(-1) = dist_up/(dist_up+dist_dn)     ! dist_up = 0.5*d(id_up), dist_dn = 0.5*d(id_dn)
dist(0)  = dist_up + dist_dn
dist(k)  = 1.d0                          ! k = 1 (x), 2 (y), 3 (z); other components 0
area     = product of the two transverse spacings
```

So for a Cartesian grid the connection unit vector is exactly an axis direction, and the upwind fraction is the half-spacing ratio. y-connections use `area = dx*dz` (`src/pflotran/grid_structured.F90:1022-1023`).

Curvilinear areas:

- `CYLINDRICAL`: x (radial) connection area is a cylinder wall; z-connections use `2*pi*r*dr` (see the boundary equivalents in §5.2, which use the same expressions). `NY /= 1` is fatal: `'For cylindrical coordinates, NY must be equal to 1.'` (`src/pflotran/grid_structured.F90:1027-1029`).
- `SPHERICAL`: radial connection area `4*pi*(r + dx/2)^2` (`src/pflotran/grid_structured.F90:970-971`); `'For spherical coordinates, NY must be equal to 1.'` for y-connections (`:1030-1032`).

Second-order TVD neighbours (`id_up2`, `id_dn2`) are allocated only when `option%itranmode == EXPLICIT_ADVECTION` and the flux limiter is not plain upwind (`src/pflotran/grid_structured.F90:876-883`); at domain edges they index a separate TVD ghost vector via negative ids (`:1000-1011`, and `StructGridCreateTVDGhosts` at `:1765`).

### 5.2 Boundary connections

`StructGridPopulateConnection()` (`src/pflotran/grid_structured.F90:1117-1299`), reached through `GridPopulateConnection()` (`src/pflotran/grid.F90:351-394`).

- `dist(0)` is `dist_scale` times the cell spacing in the face-normal direction, where `dist_scale = 0.5` normally and `1.0` when `2ND_ORDER_BOUNDARY_CONDITION` is set (`src/pflotran/grid_structured.F90:1142-1146`).
- The unit vector points **from the face toward the cell centre**: `+1` on `WEST`/`SOUTH`/`BOTTOM`, `-1` on `EAST`/`NORTH`/`TOP` (`src/pflotran/grid_structured.F90:1164-1168`, `:1214-1218`, `:1251-1256`). This matches the unstructured convention (see `unstructured_grids.md` §5.5).
- `dist(-1)` is set to 0 along with the rest of the array (`connection%dist(:,iconn) = 0.d0` at `src/pflotran/grid_structured.F90:1157` and equivalents), so boundary connections have `upwind_weight = 1` after `ConnectionCalculateDistances` (`src/pflotran/connection.F90:262-272`).

Boundary areas:

| Face | `CARTESIAN` | `CYLINDRICAL` | `SPHERICAL` |
|---|---|---|---|
| `WEST`/`EAST` | `dy*dz` (`:1160-1161`) | `2*pi*(r -/+ dx/2)*dz` (`:1181-1188`) | `4*pi*(r -/+ dx/2)^2` (`:1196-1202`) |
| `SOUTH`/`NORTH` | `dx*dz` (`:1212-1213`) | not applicable, `stop` (`:1225-1227`) | not applicable, `stop` (`:1228-1230`) |
| `BOTTOM`/`TOP` | `dx*dy` (`:1240-1241`) | `2*pi*r*dx` (`:1268-1269`) | fatal: `'Areas for spherical coordinates for z-axis not applicable.'` (`:1283-1286`) |

A degenerate boundary face is caught: `'Zero area in boundary connection at grid cell <n>.'` when `area < 1.d-20` (`src/pflotran/grid_structured.F90:1289-1295`).

Note the two `stop` statements for cylindrical/spherical `SOUTH`/`NORTH` faces (`src/pflotran/grid_structured.F90:1225-1230`) are bare Fortran `stop` after a `print *`, not the usual `PrintErrMsg` path.

---

## 6. Regions on structured grids

`GridLocalizeRegions()` (`src/pflotran/grid.F90:611-799`) supports these `def_type`s on `STRUCTURED_GRID`:

| `def_type` | Deck form | Handler |
|---|---|---|
| `DEFINED_BY_BLOCK` | `BLOCK i1 i2 j1 j2 k1 k2` | `GridLocalizeRegionFromBlock` (`grid.F90:643-644`, `:1626`) |
| `DEFINED_BY_CARTESIAN_BOUNDARY` | `CARTESIAN_BOUNDARY WEST\|EAST\|...` | `GridLocalizeRegionFromCartBound` (`grid.F90:645-646`, `:1704`) |
| `DEFINED_BY_COORD` | `COORDINATE` / `COORDINATES` / `INFINITE` | `GridLocalizeRegionFromCoordinates` (`grid.F90:647-648`, `:1756`) |
| `DEFINED_BY_CELL_IDS` | `LIST` (1 int/line) or a plain file | `GridLocalizeRegionsFromCellIDs` (`grid.F90:649-657`) |
| `DEFINED_BY_CELL_AND_FACE_IDS` | `LIST` (2 ints/line) | `GridLocalizeRegionsFromCellIDs` — **structured only**; other grid types abort (`grid.F90:658-666`) |
| `DEFINED_BY_POLY_BOUNDARY_FACE` | `POLYGON` + `TYPE BOUNDARY_FACES_IN_VOLUME` | `GridMapCellsInPolVol`; **requires a `FACE`** or aborts with `'REGIONs defined with POLYGON and BOUNDARY_FACES_IN_VOLUME on STRUCTURED grids must define a FACE.'` (`grid.F90:713-725`) |
| `DEFINED_BY_POLY_CELL_CENTER` | `POLYGON` + `TYPE CELL_CENTERS_IN_VOLUME` | `GridMapCellsInPolVol` (`grid.F90:739-746`) |

`DEFINED_BY_SIDESET_UGRID` (`.ss` files) is **rejected** on structured grids (`src/pflotran/grid.F90:671-676`); the structured analogue is `FACE` plus a coordinate or block region. Region keyword parsing is in `RegionRead()` (`src/pflotran/region.F90:400-599`).

Every region must end up with at least one cell globally, otherwise `'No cells assigned to REGION "<name>".'` (`src/pflotran/grid.F90:764-770`).

---

## 7. Traps

- **Silent Cartesian fallback.** A typo in the sub-type (`TYPE STRUCTURED CARTESION`) is not an error; it becomes `CARTESIAN` (`src/pflotran/discretization.F90:188-190`).
- **Silent dimension collapse.** `NXYZ 10 10 10` under `CYLINDRICAL` becomes `10 1 10`, and under `SPHERICAL` becomes `10 1 1`, with no message (`src/pflotran/discretization.F90:224-227`).
- **`INVERT_Z` is inert** at this commit. The keyword is accepted (`src/pflotran/discretization.F90:491`) but `invert_z_axis` is initialized `PETSC_FALSE` (`src/pflotran/grid_structured.F90:192`) and never set anywhere in the tree, so the gravity flip at `src/pflotran/discretization.F90:604-606` and the face-direction branches at `src/pflotran/grid_structured.F90:1242-1257` and `:1270-1282` are dead code. One of those branches would in fact abort if reached (`'Need to ensure that direction of inverted z is correct in StructGridPopulateConnection()'`, `src/pflotran/grid_structured.F90:1244-1246`).
- **`2ND_ORDER_BOUNDARY_CONDITION` is structured-only** and doubles the boundary connection distance (`src/pflotran/discretization.F90:569-575`; `src/pflotran/grid_structured.F90:1142-1146`).
- **Permeability tensor model differs by grid family.** Structured defaults to `TENSOR_TO_SCALAR_LINEAR`, unstructured to `TENSOR_TO_SCALAR_POTENTIAL` (`src/pflotran/discretization.F90:301` vs `:263`). Comparing a structured and an unstructured version of the same problem without setting `PERM_TENSOR_TO_SCALAR_MODEL` explicitly is comparing two different upscalings.
