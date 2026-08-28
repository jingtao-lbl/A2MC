---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Surface-Subsurface Coupling: MPCCoupledWater and MPCPermafrost

## Why this matters for ECRP

The coupled surface-subsurface solver is ATS's signature capability and the primary reason it is scientifically superior to single-domain codes for permafrost hydrology. `MPCCoupledWater` (isothermal) and `MPCPermafrost` (thermal) enforce continuity of pressure and flux across the surface-subsurface interface **discretely and implicitly**, within a single Newton solve. This eliminates the operator-split errors that plague sequential approaches when strong exchange fluxes occur (e.g., during rapid snowmelt or active layer thaw). The ELM-ATS coupling described in topic 07 feeds boundary conditions into this solver from ELM's land-surface model.

---

## MPCCoupledWater — integrated hydrology (isothermal)

**File:** `src/pks/mpc/mpc_coupled_water.hh` and `src/pks/mpc/mpc_coupled_water.cc`

**PK type string:** `"coupled water"`

**Reference:** Coon et al., Adv. Water Resour., 2020 (https://doi.org/10.1016/j.advwatres.2020.103701)

```cpp
class MPCCoupledWater : public StrongMPC<PK_PhysicalBDF_Default> { ... };
```
(src/pks/mpc/mpc_coupled_water.hh:75)

### Coupled equations

The system (from the header doc, src/pks/mpc/mpc_coupled_water.hh:20-38):

```
∂Θ_s(p_s*)/∂t = ∇·k_s ∇(z + h(p_s*)) + Q_ext + q_ss    [overland flow / surface]
∂Θ(p)/∂t = ∇·kK(∇p + ρgẑ)                               [Richards / subsurface]
−kK(∇p + ρgẑ)·n̂ |_Γ = q_ss                              [flux continuity at Γ]
p|_Γ = p_s                                                 [pressure continuity at Γ]
```

The exchange flux `q_ss` and the pressure equality at the surface-subsurface interface Γ are enforced **discretely** rather than iteratively.

### Discrete coupling mechanism

The key insight (from Coon et al. 2020) is that the mimetic finite difference discretization of the subsurface uses face-based unknowns. The faces that lie on the top surface of the subsurface mesh are co-located with the overland flow cells. Therefore, the surface cell pressure and the subsurface top-face pressure are the same unknown. By assembling the overland flow operator directly into the subsurface discrete operator (at the surface rows/columns), the pressure continuity condition is satisfied exactly at every Newton iteration — no separate enforcement loop is needed.

This means `MPCCoupledWater` can only be used with MFD (mimetic finite difference) subsurface discretizations, not FV.

### Sub-PK order

Input parameter `"PKs order"` must list `{subsurface_flow_pk, surface_flow_pk}` in this exact order (src/pks/mpc/mpc_coupled_water.hh:48).

### Preconditioner

`MPCCoupledWater` holds a single monolithic `Operators::Operator` preconditioner (`precon_`) that combines both the subsurface and surface operators into one system (src/pks/mpc/mpc_coupled_water.hh:135-136). The surface operator is embedded in the subsurface operator rows/columns corresponding to the surface cells, following the discrete coupling approach.

`ApplyPreconditioner` (overridden) applies this monolithic preconditioner rather than the block-diagonal default from `StrongMPC` (src/pks/mpc/mpc_coupled_water.hh:98-100).

### Globalization delegate

`MPCDelegateWater` (src/pks/mpc/mpc_coupled_water.hh:139) handles numerical difficulties at the wetting front:
- **Pressure coupling**: use the star-system pressure as the initial value for the primary solve
- **Flux coupling**: convert the lateral surface fluxes from the star system to a source term for the primary solve — more stable when cells are wetting up
- **Hybrid coupling**: use pressure-based where flow is divergent (run-off) and flux-based where flow is convergent (run-on)

The `consistent_cells_` option (src/pks/mpc/mpc_coupled_water.hh:140) enables a correction step to ensure cell-centered pressures are consistent with the face-based unknowns after applying the preconditioner.

---

## MPCPermafrost — integrated thermal hydrology (the full permafrost solver)

**File:** `src/pks/mpc/mpc_permafrost.hh` and `src/pks/mpc/mpc_permafrost.cc`

**PK type string:** `"permafrost model"`

**Reference:** Painter et al., WRR, 2016 (https://doi.org/10.1002/2015WR018427)

```cpp
class MPCPermafrost : public MPCSubsurface { ... };
```
(src/pks/mpc/mpc_permafrost.hh:67)

### Inheritance chain

```
PK
└── MPC<PK_PhysicalBDF_Default>
    └── StrongMPC<PK_PhysicalBDF_Default>
        └── MPCSubsurface          (2-PK: subsurface flow + energy)
            └── MPCPermafrost      (4-PK: subsurface flow + energy + surface flow + energy)
```

`MPCPermafrost` inherits all the subsurface Jacobian machinery from `MPCSubsurface` and extends it to the 4-PK surface+subsurface system.

### Sub-PK order

Must be exactly (src/pks/mpc/mpc_permafrost.hh:35-36):

```
"PKs order" = [subsurface_flow_pk, subsurface_energy_pk, surface_flow_pk, surface_energy_pk]
```

Sub-PK indices: 0 = subsurface Richards, 1 = subsurface energy, 2 = surface overland flow (icy), 3 = surface energy (icy).

### Coupling architecture

`MPCPermafrost` enforces:
1. **Mass continuity** at Γ: same mechanism as `MPCCoupledWater` — surface pressure equated to subsurface top-face pressure
2. **Energy continuity** at Γ: surface temperature equated to subsurface top-face temperature (similar discrete approach)
3. **Mass exchange flux** `q_ss` (src/pks/mpc/mpc_permafrost.hh:125): the exfiltration/infiltration flux passing mass (and its associated enthalpy) between surface and subsurface
4. **Energy exchange flux** (src/pks/mpc/mpc_permafrost.hh:126): the advected energy associated with the mass exchange

Both exchange flux keys are registered as primary variables that are computed and passed between the sub-PKs within the Newton solve.

### 4×4 Jacobian structure

`MPCPermafrost::UpdatePreconditioner` (overrides `MPCSubsurface`) assembles the extended 4×4 block system. The subsurface 2×2 block from `MPCSubsurface` is retained; additional terms are added for:
- Surface accumulation derivatives: `dE_dp_surf_` (src/pks/mpc/mpc_permafrost.hh:131)
- Surface flow coupling to surface temperature: `ddivq_dT_` for overland conductivity (src/pks/mpc/mpc_permafrost.hh:133)
- Cross-domain coupling: the exchange flux terms couple surface and subsurface rows in the off-diagonal blocks

The surface blocks are assembled by `MPCSurface`-like logic embedded in `MPCPermafrost`.

### EWC delegates (two of them)

`MPCPermafrost` holds **two** EWC delegates (src/pks/mpc/mpc_permafrost.hh:148-151):
1. `ewc_` (inherited from `MPCSubsurface`): subsurface EWC using `PermafrostModel`
2. `surf_ewc_` (`MPCDelegateEWCSurface`): surface EWC using `SurfaceIceModel`

Both are active in `ModifyPredictor`. This double EWC is critical for problems with simultaneous freeze-thaw at both the surface (ponded water freezing) and the near-surface subsurface (active layer).

### Water delegate

`MPCPermafrost` also holds an `MPCDelegateWater` (src/pks/mpc/mpc_permafrost.hh:151) for the surface-subsurface flux globalization, same as `MPCCoupledWater`.

### Coupling flags propagated to sub-PKs

`parseParameterList` sets (src/pks/mpc/mpc_permafrost.cc:52-56):
```cpp
pks_list_->sublist(names[0]).set("coupled to surface via flux", true);
pks_list_->sublist(names[1]).set("coupled to surface via flux", true);
pks_list_->sublist(names[2]).set("coupled to subsurface via flux", true);
pks_list_->sublist(names[3]).set("coupled to subsurface via flux", true);
```
These flags tell each sub-PK to expect an incoming exchange flux source term rather than using a Neumann BC at the domain boundary.

---

## Surface-subsurface helper utilities

**File:** `src/pks/mpc/mpc_surface_subsurface_helpers.hh` and `.cc`

(src/pks/mpc/mpc_surface_subsurface_helpers.hh:17-105)

Three utility functions for copying data between the surface and subsurface meshes at the interface:

| Function | Purpose |
|---|---|
| `CopySurfaceToSubsurface(surf, sub)` | Copy surface cell values → subsurface top-face values |
| `CopySubsurfaceToSurface(sub, surf)` | Copy subsurface top-face values → surface cell values |
| `MergeSubsurfaceAndSurfacePressure(kr_surf, sub_p, surf_p)` | Merge pressures at interface using the surface relative permeability as a weighting |

These helpers also define template structs `DomainFaceGetter` and `DomainFaceSetter` (src/pks/mpc/mpc_surface_subsurface_helpers.hh:37-99) that provide efficient, type-safe access to either `FACE` or `BOUNDARY_FACE` components of a vector, selected at compile time to avoid per-cell runtime dispatch.

---

## Operator-split variants

Two additional MPCs provide the same coupled physics but with an operator-splitting approach (rather than fully implicit):

### MPCCoupledWaterSplitFlux

(documented in [mpc.md](mpc.md))

Splits lateral overland flow from vertical exchange. More scalable for large 3D problems; supports columnar decomposition of the subsurface.

### MPCPermafrostSplitFlux

(documented in [mpc.md](mpc.md))

Thermal analog of `MPCCoupledWaterSplitFlux`. The "star" system advances surface flow AND energy transport laterally; the primary system handles the vertical coupled thermal hydrology.

---

## Choosing between implicit and split-flux

| Criterion | `MPCCoupledWater` / `MPCPermafrost` | Split-flux variants |
|---|---|---|
| Accuracy near wetting fronts | Higher (single Newton solve) | Lower (operator split error) |
| Robustness for very wet/ponded cases | Similar (with hybrid delegate) | Similar |
| Computational cost (3D subsurface) | High (full 3D implicit solve each outer step) | Lower (1D columns possible) |
| Lateral subsurface flow | Included | Excluded (columns) or included (3D) |
| Temporal accuracy | First-order tight coupling | First-order operator split |
| Recommended for | Small to medium domains, steep gradients | Large domains, intermediate-scale |
