---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Surface-Subsurface Flux Evaluators

**Source tree:** `src/constitutive_relations/surface_subsurface_fluxes/`

## Overview

ATS uses separate surface and subsurface meshes.  The surface mesh is derived from the top
faces of the subsurface mesh (each surface cell corresponds to one subsurface top face).  The
evaluators in this directory transfer scalar and flux fields between those two mesh domains,
enabling the integrated hydrology approach where exchange between overland flow and Richards
flow is computed through the shared boundary.

All three evaluators in this directory are `EvaluatorSecondaryMonotypeCV` subclasses.

---

## 1. `OverlandSourceFromSubsurfaceFluxEvaluator`

**File:** `surface_subsurface_fluxes/overland_source_from_subsurface_flux_evaluator.hh:25`
**File:** `surface_subsurface_fluxes/overland_source_from_subsurface_flux_evaluator.cc`
**Factory key:** `"overland source from subsurface via flux"`

**Purpose:** Extracts the Darcy flux at the subsurface top boundary and places it as a source
term on the surface (overland flow) mesh.

**Mesh topology coupling:** For each surface cell c, the evaluator precomputes the corresponding
subsurface top face and its outward normal direction via `IdentifyFaceAndDirection_()`, which
uses `surface->getEntityParent(CELL, c)` to find the parent subsurface face
(`overland_source_from_subsurface_flux_evaluator.cc:87`).

**Evaluate:** (`cc:105-138`)
```
source[c] = flux[face] * dir          (molar basis, mol/m^2/s)
source[c] = flux[face] * dir / rho    (volume basis, m/s)
```

The `"volume basis"` flag (default false) switches between molar-conserving and volume-
conserving representations.  When `volume_basis_=true`, the molar flux from the subsurface is
divided by the liquid molar density to convert units.

**Dependencies:**
- `flux_key_` (subsurface face field, default `"mass_flux"`)
- `dens_key_` (subsurface cell field `"molar_density_liquid"`, only if `volume_basis_=true`)

**Key detail:** `EvaluatePartialDerivative_` is not implemented (asserts 0, `cc:141-149`).
This means the evaluator provides no Jacobian contribution; it is treated as frozen in the
Newton solve.  The actual flux-pressure coupling is handled inside the Richards PK's residual
evaluation directly.

---

## 2. `SurfaceTopCellsEvaluator`

**File:** `surface_subsurface_fluxes/surface_top_cells_evaluator.hh:26`
**File:** `surface_subsurface_fluxes/surface_top_cells_evaluator.cc`
**Factory key:** `"surface from top cell evaluator"`

**Purpose:** Copies a subsurface cell-valued field, evaluated at the topmost cell in each
column, to a surface-domain field.  The inverse direction to `TopCellsSurfaceEvaluator`.

**Use case:** Exposing the subsurface temperature or pressure at the surface-subsurface
interface to the surface energy balance, without needing to maintain a separate PK that knows
about both meshes.  For example, pulling the uppermost-cell soil temperature to drive surface
energy exchange.

**Dependency:** One subsurface field; key defaults to same variable name as the output.
Derivatives are not implemented (asserts 0).

---

## 3. `TopCellsSurfaceEvaluator`

**File:** `surface_subsurface_fluxes/top_cells_surface_evaluator.hh:26`
**File:** `surface_subsurface_fluxes/top_cells_surface_evaluator.cc`
**Factory key:** `"top cell from surface evaluator"`

**Purpose:** Maps a surface-domain field down into the top subsurface cells.  The inverse
direction to `SurfaceTopCellsEvaluator`.

**Negate flag:** The boolean `negate_` member allows the result to be sign-flipped, enabling
e.g. the overland water head to be applied as a pressure boundary condition on the top face of
the subsurface domain with the correct sign convention.

**Dependencies:** One surface-domain field.  `domain_surf_` is read from plist to locate
the surface mesh.

---

## 4. `Volumetric_FluxEvaluator`

**File:** `surface_subsurface_fluxes/volumetric_darcy_flux_evaluator.hh:23`
**File:** `surface_subsurface_fluxes/volumetric_darcy_flux_evaluator.cc`
**Factory key:** `"volumetric darcy flux"`

**Purpose:** Converts a molar Darcy flux (mol/s across a face, as produced by the Richards PK)
to a volumetric flux (m^3/s) by dividing by molar density:

```
q_vol[face] = q_mol[face] / n_liq[cell]
```

This conversion is needed by diagnostics and the Manning overland flow PK, which operates in
a volumetric (m^3/s) basis.

Author: Daniil Svyatsky.

---

## Design Note: No Derivatives

All four evaluators disable `EvaluatePartialDerivative_` (either via `AMANZI_ASSERT(0)` or
returning zeros).  This reflects the fact that cross-mesh flux coupling in ATS is handled
through the MPC (multi-process coupler) via operator splitting or sequential coupling, not
through a monolithic Jacobian.  The Newton solver within each PK sees each other's contributions
as frozen.  For tightly coupled surface-subsurface flow, the pressure continuity condition is
enforced via an MPC that assembles contributions from both PKs (see `src/pks/mpc/`).
