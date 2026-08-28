---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Deformation Operator (`deformation/`)

The `deformation/` subdirectory contains two classes that implement a specialized linear operator for the ground-deformation problem: `MatrixVolumetricDeformation` and `Matrix_PreconditionerDelegate`.

## Build status (critical note)

**Both files are commented out of the `CMakeLists.txt` build at this commit** (`src/operators/CMakeLists.txt:24`):

```cmake
#  deformation/MatrixVolumetricDeformation.cc
#  deformation/Matrix_PreconditionerDelegate.cc
```

The source files are present but not compiled into `ats_operators`. The deformation PK (`src/pks/deform/`) either links these from Amanzi directly, uses a different implementation, or the feature is partially disabled at this commit. This should be verified before relying on this operator in a build.

## Source files

| File | Lines | Role |
|---|---|---|
| `deformation/MatrixVolumetricDeformation.hh` | 95 | Class declaration |
| `deformation/MatrixVolumetricDeformation.cc` | 404 | Full implementation |
| `deformation/Matrix_PreconditionerDelegate.hh` | 83 | Preconditioner wrapper declaration |
| `deformation/Matrix_PreconditionerDelegate.cc` | 219 | Trilinos/HYPRE preconditioner dispatch |

## Problem formulation

The volumetric deformation problem asks: given a required change in cell volume `dV` (driven by subsidence, frost heave, thermokarst, or consolidation), what change in vertical node position `dz_node` produces that volume change?

The relationship between vertical node displacement and cell volume change is encoded in the Jacobian matrix `dVdz`, a sparse rectangular matrix mapping node displacements to cell volume changes:

```
dVdz * dz_node = dV_cell
```

Because this system is generally overdetermined or underdetermined (nodes are shared among multiple cells), it is solved in the least-squares sense via the normal equations:

```
(dVdz^T * dVdz) * dz_node = dVdz^T * dV_cell
```

`MatrixVolumetricDeformation` assembles and applies this normal-equation operator, with additional regularization terms.

## MatrixVolumetricDeformation

### Vector spaces

The operator maps between (`src/operators/deformation/MatrixVolumetricDeformation.cc:131`):
- **Domain:** `"node"` component on `AmanziMesh::Entity_kind::NODE` (the vertical node displacements)
- **Range:** `"cell"` component on `AmanziMesh::Entity_kind::CELL` (the cell volume changes)

### Assembly: dVdz matrix

`PreAssemble_()` (`src/operators/deformation/MatrixVolumetricDeformation.cc:107`) builds `dVdz_` as a sparse `Epetra_CrsMatrix`. The assembly is hard-coded for triangular prisms (`MESH_TYPE 1`, i.e., 6 nodes per cell, as used in ATS's extruded 2D meshes) or hexahedra (`MESH_TYPE 0`, 8 nodes per cell). For each cell, the method:

1. Identifies the upward-facing and downward-facing horizontal faces by checking the sign of `getFaceNormal()[2]` (`src/operators/deformation/MatrixVolumetricDeformation.cc:159`).
2. Computes the perpendicular (horizontal) face area from the magnitude of the z-component of the face normal.
3. Assigns `+perp_area/n_top_nodes` to the top face nodes and `-perp_area/n_top_nodes` to the bottom face nodes in the Jacobian row for cell `c`. This gives `dV/dz_node = area / n_nodes` per node: lifting a top node by 1 m increases volume by `area/n_nodes`; lowering a bottom node by 1 m decreases it by the same amount.

### Normal equations and regularization

After building `dVdz_`, the code forms `dVdz^T * dVdz` using `EpetraExt::MatrixMatrix::Multiply` (`src/operators/deformation/MatrixVolumetricDeformation.cc:231`) and stores it as `operatorPre_`.

Two regularization terms are then added:

1. **Diagonal shift:** `diagonal_shift_` (default `1e-6`) is added to every diagonal entry to ensure the system is positive definite (`src/operators/deformation/MatrixVolumetricDeformation.cc:238`).
2. **Diffusive smoothing:** A graph Laplacian term is added with coefficient `smoothing_` / distance. For each node, all face-neighbors are found and a weighted Laplacian stencil (`+smoothing/dist` on diagonal, `-smoothing/dist` off-diagonal) is summed in (`src/operators/deformation/MatrixVolumetricDeformation.cc:249`). This penalizes large gradients in the node displacement field, producing smoother deformation patterns.

The resulting `operatorPre_` (indexed over nodes) is the system matrix that is solved at each step.

### Boundary conditions (fixed nodes)

`Assemble(fixed_nodes)` (`src/operators/deformation/MatrixVolumetricDeformation.cc:301`) copies `operatorPre_` to `operator_` and then, for each fixed node (e.g., the base of the column), replaces its row with the identity: zeros off-diagonal, 1 on diagonal. This enforces `dz_node = 0` at those nodes. `Assemble` must be called before `Apply` or `ApplyInverse`.

`ApplyRHS(x_cell, x_node, fixed_nodes)` (`src/operators/deformation/MatrixVolumetricDeformation.cc:82`) forms the right-hand side of the normal equations by applying `dVdz^T` (transpose) to the cell-volume RHS `x_cell`, then zeroing out fixed-node entries.

### Apply and ApplyInverse

`Apply(x, b)` calls `operator_->Apply()` on the node vector: `b_node = operator_ * x_node` (`src/operators/deformation/MatrixVolumetricDeformation.cc:52`).

`ApplyInverse(b, x)` calls the preconditioner `prec_->ApplyInverse()` on node vectors (`src/operators/deformation/MatrixVolumetricDeformation.cc:59`).

## Matrix_PreconditionerDelegate

A lightweight wrapper that owns the preconditioner for the deformation operator. Supports six preconditioner types (`src/operators/deformation/Matrix_PreconditionerDelegate.hh:52`):

| Enum | Trilinos implementation |
|---|---|
| `TRILINOS_ML` | `ML_Epetra::MultiLevelPreconditioner` (algebraic multigrid) |
| `TRILINOS_ILU` | `Ifpack_ILU` (incomplete LU) |
| `TRILINOS_BLOCK_ILU` | `Ifpack_AdditiveSchwarz` with ILU |
| `HYPRE_AMG` | `Ifpack_Hypre` with BoomerAMG (requires HYPRE build) |
| `HYPRE_EUCLID` | `Ifpack_Hypre` with Euclid |
| `HYPRE_PARASAILS` | `Ifpack_Hypre` with ParaSails |

The delegate is not the same as the standard `AmanziPreconditioners::PreconditionerFactory`; it is a simpler, ATS-side class that predates the current Amanzi preconditioner abstraction. This is another indication that `deformation/` is legacy code partially superseded by Amanzi infrastructure.

## Relationship to the deformation PK

The deformation PK (`src/pks/deform/`) calls this operator to compute vertical node displacements that match prescribed volume changes (from subsidence, ice loss, or sediment compaction). The result is used to update node coordinates in the mesh, which then propagates to all other PKs through the mesh coordinate change. This is the "moving mesh" capability of ATS for permafrost subsidence and thermokarst modeling.
