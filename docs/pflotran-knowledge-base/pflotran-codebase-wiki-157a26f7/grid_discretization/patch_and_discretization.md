**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** `discretization.F90`, `patch.F90`, `grid.F90`, `connection.F90` — the object graph, DM/vector machinery, and what a "patch" is
**Last verified:** 2026-07-31

---

## 1. The object graph

```
realization_subsurface
 |- discretization  (discretization_type,  src/pflotran/discretization.F90:20-42)
 |    |- grid       (grid_type,            src/pflotran/grid.F90:18-88)
 |    |    |- structured_grid    (grid_structured_type,    grid_structured.F90:25-72)
 |    |    |- unstructured_grid  (grid_unstructured_type,  grid_unstructured_aux.F90:24-71)
 |    |    |     |- explicit_grid   (unstructured_explicit_type,  grid_unstructured_aux.F90:73-89)
 |    |    |     |- polyhedra_grid  (unstructured_polyhedra_type, grid_unstructured_aux.F90:91-126)
 |    |    |- internal_connection_set_list / boundary_connection_set_list
 |    |    |- reg_internal_connection_set_list / reg_boundary_connection_set_list
 |    |- dm_1dof / dm_nflowdof / dm_ntrandof / dm_n_stress_strain_dof  (dm_ptr_type)
 |    |- dmc_nflowdof(:) / dmc_ntrandof(:)   ! coarsened DM hierarchy for Galerkin multigrid
 |- patch           (patch_type,            src/pflotran/patch.F90:35-101)
      |- grid  ->  the SAME grid_type object as discretization%grid
```

The `patch%grid => discretization%grid` aliasing is set in `src/pflotran/factory_subsurface_read.F90:746-751`, immediately after `DiscretizationReadRequiredCards` returns. So the grid is owned by the discretization; the patch borrows it.

Only `STRUCTURED_GRID` and `UNSTRUCTURED_GRID` cause a patch to be created (`src/pflotran/factory_subsurface_read.F90:745-751`).

---

## 2. `discretization_type` — the PETSc DM layer

`src/pflotran/discretization.F90:20-42`. Beyond the grid pointer and the `TYPE` metadata it holds:

| Field | Purpose | Source |
|---|---|---|
| `itype` / `ctype` | `STRUCTURED_GRID` or `UNSTRUCTURED_GRID` only | `discretization.F90:21-24` |
| `origin_global(3)` | domain origin from `ORIGIN`/`BOUNDS` | `:25` |
| `filename` | mesh filename from the `TYPE` line | `:27` |
| `dm_1dof`, `dm_nflowdof`, `dm_ntrandof`, `dm_n_stress_strain_dof` | one DM per degree-of-freedom count | `:33-36` |
| `dmc_nflowdof(:)`, `dmc_ntrandof(:)` | coarsened DM hierarchies for Galerkin multigrid; element *i* is **finer** than *i-1* | `:29-31` |
| `dm_index_to_ndof(5)` | maps a DM index to its dof count | `:32` |
| `tvd_ghost_scatter` | `VecScatter` for TVD ghost values | `:37` |
| `stencil_width`, `stencil_type` | DMDA ghost-layer controls, default `1` / `DMDA_STENCIL_STAR` | `:39-40`, `:110-111` |

### 2.1 DM creation

`DiscretizationCreateDMs()` (`src/pflotran/discretization.F90:682-...`) populates `dm_index_to_ndof` for structured grids (`:713-716`) and then creates one DM per non-zero dof count: always `dm_1dof` with `ndof = 1` (`:726-729`), plus `dm_nflowdof` if `o_nflowdof > 0` (`:733-738`), `dm_ntrandof` if `o_ntrandof > 0` (`:740-745`), and the geomechanics DM if requested (`:747-752`). For structured grids it then calls `StructGridComputeLocalBounds` on `dm_1dof` to fill `lxs/lys/lzs` etc. (`:755-759`).

`DiscretizationCreateDM()` routes to `StructGridCreateDM` (PETSc `DMDACreate3D`, `src/pflotran/grid_structured.F90:227-233`) or to the unstructured `ugdm` machinery. The `dm_ptr_type` carries both a PETSc `DM` and a `ugdm` pointer (`src/pflotran/discretization.F90:99-106`), so the same call site works for both families.

### 2.2 Vectors and the three orderings

`DiscretizationCreateVector(discretization, dm_index, vector, vector_type, option)` (`src/pflotran/discretization.F90:804-845`):

| `vector_type` | Structured | Unstructured | Index space |
|---|---|---|---|
| `GLOBAL` | `DMCreateGlobalVector` | `DMCreateGlobalVector` | local (owned cells only) |
| `LOCAL` | `DMCreateLocalVector` | `DMCreateLocalVector` | ghosted local |
| `NATURAL` | `DMDACreateNaturalVector` | `UGridDMCreateVector(...)` | natural (mesh-file order) |

(`src/pflotran/discretization.F90:827-841`.) `DMCreateGlobalVector` / `DMCreateLocalVector` / `DMDACreateNaturalVector` are **PETSc**. Every newly created vector is zeroed (`:843`).

The communication wrappers, all thin dispatchers over PETSc:

| Routine | Structured | Unstructured | Source |
|---|---|---|---|
| `DiscretizationGlobalToLocal` | `DMGlobalToLocal*` | `VecScatter` on `ugdm` | `discretization.F90:53` |
| `DiscretizationLocalToGlobal` / `...Add` | `DMLocalToGlobal*` | `VecScatter` | `:54-55` |
| `DiscretizationLocalToLocal` | `DMLocalToLocal*` | `VecScatter` | `:56` |
| `DiscretizationGlobalToNatural` | `DMDAGlobalToNatural{Begin,End}` | `VecScatterBegin/End(ugdm%scatter_gton, ...)` | `:1210-1242` |
| `DiscretizationNaturalToGlobal` | — | — | `:1246` |

**`DiscretizationGlobalToNatural` is the routine that fixes output ordering.** Tecplot output creates a `NATURAL` vector, scatters into it, then writes (`src/pflotran/output_tecplot.F90:275`, `:290-291`, `:294-297`). Consequence: cell-indexed output values appear in mesh-file order, independent of rank count and of the ParMETIS partition.

### 2.3 Domain decomposition entry point

`DiscretizationDecomposeDomain()` (`src/pflotran/discretization.F90:619-678`) is a no-op for structured grids (PETSc's DMDA does it) and dispatches to `UGridDecompose` / `UGridExplicitDecompose` / `UGridPolyhedraDecompose` for the unstructured families, with `#if !defined(PETSC_HAVE_PARMETIS)` guards that abort at run time if the build lacks the partitioner (`:640-667`). Afterwards the unstructured `nmax/nlmax/ngmax/global_offset` are copied up into `grid_type` (`:670-675`).

---

## 3. `grid_type` — the family-neutral facade

`src/pflotran/grid.F90:18-88`. It holds only what is common to every grid family and delegates the rest:

- Sizes: `nmax` (global cells), `nlmax` (local, non-ghosted), `ngmax` (local + ghost), `global_offset`, and face equivalents `nlmax_faces`/`ngmax_faces`/`nmax_faces` (`grid.F90:23-30`).
- Index maps `nL2G`, `nG2L`, `nG2A` with the definitive comment block on the three index spaces (`grid.F90:32-61`).
- Ghosted cell-centre coordinates `x(:), y(:), z(:)` (`grid.F90:63`) and local/global bounding boxes (`:65-68`).
- A natural-id hash `hash(:,:,:)` with `num_hash_bins = 1000` (`grid.F90:70-71`, default at `:177`), used by `GridGetLocalGhostedIdFromHash` (`:1253`).
- `cell_neighbors_local_ghosted(:,:)` where slot 0 is the neighbour count and negative ids mark ghosts (`grid.F90:73-76`).
- Four connection-set lists: internal, boundary, and region-restricted variants (`grid.F90:81-86`).

Every geometric operation on `grid_type` is a `select case (grid%itype)` dispatcher:

| Operation | Source |
|---|---|
| `GridComputeInternalConnect` | `grid.F90:185-243` |
| `GridComputeCoordinates` | `grid.F90:464-542` |
| `GridComputeVolumes` | `grid.F90:546-578` |
| `GridComputeAreas` (implicit unstructured only) | `grid.F90:582-607` |
| `GridLocalizeRegions` | `grid.F90:611-799` |
| `GridPopulateConnection` (boundary connections) | `grid.F90:351-394` |
| `GridMapIndices` | `grid.F90:398-435` |

`GridComputeCoordinates` also performs the six `MPI_Allreduce` calls that turn per-rank bounding boxes into the global domain extent (`grid.F90:522-540`).

`ConnectionSetIntersectRegion()` (`grid.F90:247-308`) builds a region-restricted connection set by an O(nconn x ncells) double loop; the resulting ids are **local to the region**, not to the grid (comment at `grid.F90:250-252`). This is what backs `INTEGRAL_FLUX` over a region.

---

## 4. `connection_set_type` — the flux-term interface

`src/pflotran/connection.F90:16-36`. Full field list and the `dist(-1:3)` convention are in `unstructured_grids.md` §5.1-5.2; the essentials:

- Types: `INTERNAL_FACE_CONNECTION_TYPE = 1`, `BOUNDARY_FACE_CONNECTION_TYPE = 2`, `GENERIC_CONNECTION_TYPE = 3` (`connection.F90:12-14`).
- Allocation is type-dependent: internal connections get `id_up` + `id_dn`; boundary connections get only `id_dn`; generic (source/sink) connections get only `id_dn` and **no `dist` or `area` at all** (`connection.F90:96-130`).
- `intercp` and `face_id` exist only for `IMPLICIT_UNSTRUCTURED_GRID` and `POLYHEDRA_UNSTRUCTURED_GRID` (`connection.F90:106-112`, `:120-126`). Code that reads `connection%face_id` must therefore guard on grid type — `ConnectionSetIntersectRegion` does exactly that (`grid.F90:298-301`).
- `ConnectionCalculateDistances()` (`connection.F90:241-274`) is the single unpacking point used by the flux kernels; it derives `distance_gravity`, `distance_upwind`, `distance_downwind` and `upwind_weight` from `dist` and `option%gravity`.

Connection sets are stored in singly-linked lists (`connection_set_list_type`, `connection.F90:44-49`) with `ConnectionAddToList` (`:188`) and an optional pointer-array view built by `ConnectionConvertListToArray` (`:212`).

---

## 5. `patch.F90` — role and entry points

`patch.F90` is 12,115 lines, the largest file in `src/pflotran/`. This section covers its **role** and its **entry points**; it deliberately does not attempt line-by-line coverage.

### 5.1 What a patch is

A patch is the container that binds **one grid** to **everything defined on that grid**: material assignment, regions, boundary/initial/source-sink couplers, characteristic curves, observation points, integral-flux planes, and all mode-specific auxiliary variable arrays. The `patch_type` also has a `next` pointer (`patch.F90:99`), i.e. it is designed as a list, but the subsurface factory creates exactly one (`factory_subsurface_read.F90:746-750`).

Practically: **grid = geometry and topology; patch = state and properties on that geometry.**

### 5.2 The arrays a patch owns

`src/pflotran/patch.F90:35-101`. Cell-indexed integer maps (all sized `grid%ngmax`, allocated at `src/pflotran/init_subsurface.F90:83`):

| Array | Meaning |
|---|---|
| `imat(:)` | material id per ghosted cell. **`imat <= 0` marks an inactive cell** — the universal skip test throughout the code base (e.g. `patch.F90:10541`, `condition_control.F90:174`). `STRATA / INACTIVE` sets it to 0 (`strata.F90:235-236`; `init_subsurface.F90:240-245`) |
| `imat_internal_to_external(:)` | internal id -> deck-facing material id |
| `cc_id(:)` | characteristic-curves id |
| `cct_id(:)` | thermal characteristic-curves id |
| `mtf_id(:)` | material-transform id |

Connection-indexed real arrays (`patch.F90:47-59`), the results the flux kernels write and output/mass-balance read:

`internal_velocities`, `boundary_velocities`, `internal_tran_coefs`, `boundary_tran_coefs`, `internal_flow_fluxes`, `boundary_flow_fluxes`, `ss_flow_fluxes` (moles/s), `ss_flow_vol_fluxes` (m^3/s, liquid phase, needed by transport), `internal_tran_fluxes`, `boundary_tran_fluxes`, `ss_tran_fluxes`, plus `flow_upwind_direction` / `flow_upwind_direction_bc` for multiphase upwinding (`patch.F90:61-63`).

**The auxvar arrays are not fields of `patch_type` directly** — they live one level down in `patch%aux`, of type `auxiliary_type` (`patch.F90:97`; type at `src/pflotran/auxiliary.F90:30-49`). That type is a bag of nullable pointers, one per physics mode:

```
Global, RT, NWT, TH, Richards, ZFlow, PNF, Mphase, General, Hydrate, WIPPFlo,
SCO2, Material, MTransform, ERT, SC_heat, SC_RT, InlineSurface, inversion_aux
```

Only the modes actually enabled are allocated; `AuxInit` nullifies all of them (`src/pflotran/auxiliary.F90:57-...`). So "which auxvars does the patch own" is answered by which flow/transport mode is active — `patch%aux%Richards`, `patch%aux%General`, `patch%aux%RT`, and always `patch%aux%Material` for material properties.

The patch also holds owned lists (`region_list`, five coupler lists, `strata_list`, `observation_list`, `integral_flux_list`) and **borrowed pointers** back to the realization (`field`, `datasets`, `reaction`, `reaction_nw`, `reaction_base`) — the distinction is marked in-source at `patch.F90:89`. `PatchCreate()` allocates and initializes each owned list and nullifies each borrowed pointer (`patch.F90:133-215`).

### 5.3 Main entry points

Public interface at `src/pflotran/patch.F90:114-125`. Grouped by what they do:

**Setup / binding**

| Routine | Line | Role |
|---|---|---|
| `PatchCreate` | `133` | allocate + init; called right after the grid is read |
| `PatchLocalizeRegions` | `220` | deep-copies each global region into the patch's own list, then calls `GridLocalizeRegions` — the single funnel through which **all** grid families localize regions (see the in-source note at `patch.F90:250-251`) |
| `PatchProcessCouplers` | `257` | resolves each coupler's `region_name` to a region pointer, its condition name to a condition, and builds the connection sets; errors if a named region does not exist (`patch.F90:278-281`) |
| `PatchInitAllCouplerAuxVars` / `PatchInitCouplerAuxVars` | `851`, `892` | allocate per-coupler auxvars |
| `PatchInitConstraints` / `PatchInitCouplerConstraints` | `6057`, `6091` | geochemical constraints on couplers |
| `PatchCreateZeroArray` | `11896` | builds the matrix-zeroing structure for inactive cells / inactive dofs |
| `PatchSetupUpwindDirection` | `11713` | initializes `flow_upwind_direction` |

**Per-timestep update**

| Routine | Line | Role |
|---|---|---|
| `PatchUpdateAllCouplerAuxVars` | `1220` | top-level driver over all coupler lists |
| `PatchUpdateCouplerAuxVars` | `1252` | per-list driver; dispatches to the mode-specific routine |
| `PatchUpdateCouplerAuxVars{WF,G,H,MPH,TH,Rich,ZFlow,PNF,SCO2}` | `1324`, `1550`, `2650`, `3939`, `4028`, `4292`, `4388`, `4505`, `4582` | **the bulk of the file** — one large routine per flow mode translating a boundary condition into that mode's auxvars |
| `PatchUpdateCouplerSaturation` | `5574` | saturation on a coupler |
| `PatchUpdateHetroCouplerAuxVars` | `5814` | heterogeneous (dataset-driven) couplers |
| `PatchUpdateUniformVelocity` | `6265` | prescribed uniform velocity field |
| `PatchScaleSourceSink` | `5632` | applies source/sink scaling (by volume, etc.) |

The mode-specific `PatchUpdateCouplerAuxVars*` family accounts for roughly 4,000 of the file's 12,000 lines. It is the reason `patch.F90` is so large, and it is the part that grows with every new flow mode.

**Query / output / diagnostics**

| Routine | Line | Role |
|---|---|---|
| `PatchGetVariable1` / `PatchGetVariable2` | `6335`, `10682` | **the variable dispatcher.** Maps an `ivar`/`isubvar` pair to a value for every cell and fills a vector. This is what output and observation code calls to obtain "liquid pressure", "saturation", a species concentration, etc. |
| `PatchGetVariableValueAtCell` | `8327` | the same dispatch for a single cell (observation points) |
| `PatchSetVariable` | `9608` | the inverse — writes a vector into the auxvars (restart, initial conditions) |
| `PatchCountCells` | `10516` | returns `total_count = grid%nlmax` and the count of cells with `imat > 0` (`patch.F90:10535-10543`) |
| `PatchCalculateCFL1Timestep` | `10549` | max timestep for CFL = 1 |
| `PatchGetCellCenteredVelocities` | `10755` | reconstructs cell-centred velocity from connection velocities |
| `PatchGetKOrthogonalityError` | `10855` | **mesh-quality diagnostic** — measures how far the grid deviates from K-orthogonality, the assumption underlying the two-point flux approximation |
| `PatchGetIntegralFluxConnections` | `10984` | resolves an `INTEGRAL_FLUX` definition to a list of connections |
| `PatchGetWaterMassInRegion` / `PatchGetCompMassInRegionAssign` | `11558`, `11605` | regional mass balance |
| `PatchUnsupportedVariable1..4` | `11798`-`11880` | uniform "this mode does not support this variable" error paths |
| `PatchCouplerInputRecord` | `11454` | writes the coupler section of the input record file |

`PatchGetKOrthogonalityError` is worth knowing about for unstructured work: PFLOTRAN's two-point flux approximation assumes the line between adjacent cell centres is parallel to the shared face normal, and this routine quantifies the violation. A mesh that is rotated or non-orthogonal will show a non-zero error here even though the run completes.

### 5.4 What `patch.F90` does *not* do

It does not read the deck (that is `factory_subsurface_read.F90`), does not compute grid geometry (that is `grid*.F90`), and does not assemble the residual or Jacobian (that is each mode's own module — `richards.F90`, `general.F90`, etc.). Its job is to be the place where "the grid" and "the physics state" meet.

---

## 6. Startup sequence (grid-relevant subset)

Reconstructed from the call sites cited above:

1. `InputFindStringInFile(input, option, "GRID")` locates the block (`factory_subsurface_read.F90:738-740`).
2. `DiscretizationReadRequiredCards` reads `TYPE`/`NXYZ`/`ORIGIN`, allocates the grid, and **reads the mesh file** (`discretization.F90:121-320`).
3. `PatchCreate` + `patch%grid => discretization%grid` (`factory_subsurface_read.F90:745-751`).
4. Pass 2: `DiscretizationRead` handles `DXYZ`/`BOUNDS`/`GRAVITY`/`STENCIL_*`/`UPWIND_FRACTION_METHOD`/`IMPLICIT_GRID_AREA_CALCULATION`/... (`factory_subsurface_read.F90:1080-1081`).
5. `DiscretizationDecomposeDomain` partitions unstructured grids (`discretization.F90:619`).
6. `DiscretizationCreateDMs` builds the DMs and, for structured grids, the local bounds (`discretization.F90:682`).
7. `GridComputeCoordinates`, `GridComputeInternalConnect`, `GridComputeVolumes` (`grid.F90:464`, `:185`, `:546`).
8. `UGridEnsureRightHandRule` for implicit unstructured grids (`realization_subsurface.F90:418`).
9. `InitCommonReadRegionFiles` reads `.h5` / `.ss` / `.ex` / plain region files (`init_common.F90:233-273`).
10. `PatchLocalizeRegions` -> `GridLocalizeRegions` maps every region onto local cells and faces (`patch.F90:220-253`).
11. `PatchProcessCouplers` binds conditions to regions and creates boundary connection sets (`patch.F90:257`).
12. `patch%imat` is filled from `STRATA` (`init_subsurface.F90:83`, `:239-245`).

Steps 2 and 4 being separate passes over the same block is the reason a keyword can appear valid in one pass and be a no-op in the other (see `unstructured_grids.md` §1.3 on `FILE` and `INVERT_Z`).

---

## 7. Uncertainties

- The Galerkin-multigrid DM hierarchies `dmc_nflowdof` / `dmc_ntrandof` are declared (`discretization.F90:29-31`) and `DiscretizationCreateInterpolation` is exported (`:51`), but how far the multigrid path is exercised was not traced here.
- `patch_type%next` implies multi-patch support (`patch.F90:99`); only the single-patch subsurface path was verified (`factory_subsurface_read.F90:745-751`). Whether any driver builds a patch list at this commit was not established.
- The `UNSTRUCTURED_GRID` branch of `DiscretizationCreateDMs`'s `dm_index_to_ndof` block is empty at `discretization.F90:717-723` — all four cases fall through without assignment. Whether `dm_index_to_ndof` is consulted on the unstructured path was not traced; treat any dependence on it for unstructured grids as unverified.
