---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Advection Operator (`advection/`)

The advection operator computes the discrete advective flux divergence for a scalar field transported by a pre-computed velocity field. It is used by transport PKs (passive scalar, energy advection) and is deliberately separated from the div-grad operator.

## Source files

| File | Lines | Role |
|---|---|---|
| `advection/advection.hh` | 58 | Abstract base class interface |
| `advection/advection.cc` | 52 | Base class implementations for `set_flux` and `set_num_dofs` |
| `advection/advection_donor_upwind.hh` | 50 | Donor-upwind concrete class |
| `advection/advection_donor_upwind.cc` | 121 | Donor-upwind implementation |
| `advection/advection_factory.hh` | 38 | Factory class |
| `advection/advection_factory.cc` | 42 | Factory: currently creates only `AdvectionDonorUpwind` |

## Class hierarchy

```
Advection   (abstract base)
    |
    +-- AdvectionDonorUpwind
```

`AdvectionFactory` reads `"Advection method"` from a parameter list and constructs the concrete class. Only `"donor upwind"` is currently registered (`src/operators/advection/advection_factory.cc:29`). No higher-order (e.g., Lax-Wendroff, MUSCL) schemes exist in ATS at this commit.

## The Advection base class

Declared in `src/operators/advection/advection.hh`. Key state held by the base:

- `flux_` — a `CompositeVector` with a `"face"` component holding the Darcy velocity or total flux (one DOF per face, scalar).
- `field_` — a `CompositeVector` holding both `"cell"` and `"face"` components for the transported quantity; allocated lazily in `set_num_dofs()` with `num_dofs_` degrees of freedom per entity (`src/operators/advection/advection.cc:33`).
- `num_dofs_` — number of scalar components being transported simultaneously (e.g., number of solute species).

The pure virtual method `Apply(bc_flux, include_bc_fluxes)` is the only required interface. After `Apply`, the `"cell"` component of `field_` holds the advective flux divergence accumulation and the `"face"` component holds the face-upwinded fluxes.

## AdvectionDonorUpwind

### Upwind cell identification

When `set_flux()` is called (`src/operators/advection/advection_donor_upwind.cc:35`), it immediately calls `IdentifyUpwindCells_()`. This private method (`src/operators/advection/advection_donor_upwind.cc:96`) iterates over all used cells (owned + ghost) and for each face determines the upwind and downwind cell IDs based on the sign of `flux[0][f] * fdirs[n]`. Positive product means the cell is the upwind side. Both `upwind_cell_` and `downwind_cell_` are `Epetra_IntVector` indexed over all faces (including ghosted), initialized to `-1` (meaning boundary or unset).

### Apply

`AdvectionDonorUpwind::Apply()` proceeds in two phases (`src/operators/advection/advection_donor_upwind.cc:42`):

**Part 1 — Face accumulation:** For each face, if `upwind_cell_[f] >= 0`, the face-component of `field_` is set to `|flux[0][f]| * field_c[upwind_cell_[f]]` for each DOF. This assigns the upwinded scalar value, scaled by the absolute flux magnitude.

**Part 2 — Cell accumulation:** For each face, subtract the face flux from the upwind cell and add it to the downwind cell. After the loop, `field_->ViewComponent("cell")` holds the net advective flux divergence (positive = source to cell from advective transport).

The boundary condition parameter `bc_flux` is accepted but not used in Part 1 or Part 2 in the current implementation. The parameter `include_bc_fluxes` modulates whether boundary conditions are included, but the actual BC injection code is not present at this commit (the `Apply` body ends after Part 2 without any BC-specific code block for `include_bc_fluxes`).

### Parallelism

The implementation uses `ScatterMasterToGhosted("cell")` before Part 1 and relies on the fact that `upwind_cell_` is populated for all (owned and ghost) faces. The face loop in Part 1 covers all ghosted faces. The cell loop in Part 2 only credits/debits owned cells via the `c1 < ncells_owned` / `c2 < ncells_owned` guards (`src/operators/advection/advection_donor_upwind.cc:79`).

## Factory

`AdvectionFactory::create()` (`src/operators/advection/advection_factory.cc:24`) reads `"Advection method"` and throws if the string is not `"donor upwind"`. Only one scheme is currently supported; the factory architecture is extensible for future higher-order additions.

## Relationship to the div-grad operator

The advection operator is completely independent of `MatrixMFD`. The div-grad operator handles the diffusive/dispersive part (Richards, overland flow), while this operator handles advective transport. PKs that couple both (e.g., coupled flow-energy or reactive transport) instantiate both independently and add their contributions to the residual.

## Limitations (at this commit)

- Only first-order donor-upwind scheme is available; no limiter, no higher-order reconstruction.
- Boundary condition injection (`include_bc_fluxes`) appears to be partially stubbed.
- The factory will throw on any string other than `"donor upwind"`.
