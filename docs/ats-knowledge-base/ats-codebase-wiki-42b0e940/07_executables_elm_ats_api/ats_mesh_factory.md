---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# ATS Mesh Factory

Sources: `src/executables/ats_mesh_factory.{cc,hh}`

## Purpose

`ats_mesh_factory` is the single point of entry for all mesh creation in ATS.
It reads mesh specifications from the `"mesh"` sublist of the input deck and
produces registered `Amanzi::AmanziMesh::Mesh` objects in `State`. The factory
supports a rich vocabulary of mesh types, including structured generation,
Exodus file reading, surface extraction, domain decomposition sets, and
columnar structures used by the ELM coupling.

## Entry points

### `createMeshes` `(ats_mesh_factory.cc:826)`

The top-level function called by `Coordinator`'s constructor
`(coordinator.cc:115)`. Iterates over the `"mesh"` sublist, always
processing `"domain"` first, then `"surface"`, then the remainder in
declaration order. Each entry dispatches to `createMesh`.

### `createMesh` `(ats_mesh_factory.cc:731)`

Reads the `"mesh type"` string and calls the appropriate type-specific
creator. Supported types and their creators:

| `"mesh type"` string | Creator function |
|---|---|
| `"read mesh file"` | `createMeshFromFile` |
| `"generate mesh"` | `createMeshGenerated` |
| `"logical mesh"` | `createMeshLogical` |
| `"aliased"` | `createMeshAliased` |
| `"surface"` | `createMeshSurface` |
| `"extracted"` | `createMeshExtracted` |
| `"column"` | `createMeshColumn` |
| `"column surface"` | `createMeshColumnSurface` |
| `"domain set indexed"` | `createDomainSetIndexed` |
| `"domain set regions"` | `createDomainSetRegions` |

## Mesh types

### Read mesh file `(ats_mesh_factory.cc:37)`

Reads an Exodus II file via `Amanzi::AmanziMesh::MeshFactory`. Parallel
meshes have the `.par` suffix; serial meshes use `.exo`. The factory
auto-partitions serial meshes when running in parallel.

Optional column building: if `"build columns from set"` is present, calls
`mesh->buildColumns(regionname)`; if `"build columns"` is true, builds all
columns. Column structures are required for the ELM coupling (each column
maps to one land surface cell).

### Generate mesh `(ats_mesh_factory.cc:87)`

Creates a structured hex mesh from `"domain low coordinate"`,
`"domain high coordinate"`, and `"number of cells"` parameters in the
`"generate mesh parameters"` sublist.

### Logical mesh `(ats_mesh_factory.cc:129)`

Creates a topologically-specified mesh without explicit node coordinates, used
for river networks and root networks. Can read from an external XML file via
`"read from file"`.

### Aliased mesh `(ats_mesh_factory.cc:171)`

Registers a second domain name pointing to an existing mesh. Used when two
domains (e.g., `"surface"` and `"snow"`) share the same mesh object. Domain
sets use the wildcard alias pattern to propagate indexed target names.

### Surface mesh `(ats_mesh_factory.cc:219)`

Extracts the top surface of a 3D parent mesh by lifting the faces in a named
region. Produces a flattened 2D mesh. Also registers a companion `"<name>_3d"`
mesh (the unflattened 3D submanifold). Used in every coupled
surface-subsurface simulation.

### Extracted mesh `(ats_mesh_factory.cc:310)`

Extracts a subset of cells from a parent mesh by region name. Locality is
preserved: local cells in the extracted mesh have parents that are local in
the parent mesh, avoiding cross-rank communication when mapping data between
the two meshes.

### Column mesh `(ats_mesh_factory.cc:374)`

Creates a `ColumnMesh` for a single vertical column, identified by a surface
cell local ID (`"entity LID"`). Always serial (uses `getCommSelf()`). Used
within domain sets to give each surface cell its own 1D column mesh.

### Column surface mesh `(ats_mesh_factory.cc:419)`

Creates a single-cell surface mesh above a column. Used for per-column surface
energy balance models.

### Domain set indexed `(ats_mesh_factory.cc:491)`

Creates a collection of sub-meshes, one per entity (typically surface cell)
in a region. Each sub-mesh is built by calling `createMesh` recursively with
the `"entity LID"` filled in. Optionally builds a reference map from each
subdomain back to a global reference mesh for visualization. This is the
mechanism by which column-based models are realized in ELM coupling.

### Domain set regions `(ats_mesh_factory.cc:633)`

Similar to indexed domain sets but indexed by region name rather than entity
ID. Each region becomes one sub-mesh.

## Column structure and ELM coupling

When the ELM API is active, the subsurface mesh must have been built with
columns (via `"build columns from set"` or `"build columns": true`). The
`ELM_ATSDriver` constructor verifies this at line
`(src/executables/elm_ats_api/elm_ats_driver.cc:150)`:

```cpp
ncolumns_ = mesh_surf_->getNumEntities(AmanziMesh::CELL, AmanziMesh::Parallel_kind::OWNED);
AMANZI_ASSERT(ncolumns_ == mesh_subsurf_->columns.num_columns_owned);
```

The column accessor `mesh_subsurf_->columns.getCells(col)` and
`mesh_subsurf_->columns.getFaces(col)` are used throughout `ELM_ATSDriver`
to map between the per-column ELM array layout (Fortran column-major) and the
ATS unstructured cell ordering.

## Mesh verification

Any mesh type can enable a geometric and topological audit by setting
`"verify mesh": true` in its parameter list. The audit (`MeshAudit`) runs on
each rank, writing per-rank text files in parallel mode. An audit failure
throws an `Amanzi_exception`. `(ats_mesh_factory.cc:777)`

## Registration with State

All creator functions call `State::RegisterMesh(name, mesh, deformable)` to
make the mesh available globally via `S_->GetMesh(name)`. Domain sets are
registered via `State::RegisterDomainSet(name, ds)`.

## Helper: `setDefaultParameters` `(ats_mesh_factory.cc:858)`

Sets the default partitioner to `"zoltan_rcb"` (which keeps cell columns
together — important for ELM-style coupling) and propagates the verbosity
level to the mesh parameter list if not already set.
