---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Surface Flow PKs

## OverlandPressureFlow

### Class and registration

```
namespace Amanzi::Flow
class OverlandPressureFlow : public PK_PhysicalBDF_Default
PK type string: "overland flow, pressure basis"
```

Source: `src/pks/flow/overland_pressure.hh`, `src/pks/flow/overland_pressure_pk.cc`, `src/pks/flow/overland_pressure_physics.cc`, `src/pks/flow/overland_pressure_ti.cc`

### Governing equation

The diffusion-wave (kinematic-wave with diffusion) approximation to the shallow-water equations:

```
d(Theta)/dt  -  div [ n_l * k * grad h(p) ]  =  Q_w
```

where:
- `Theta` = surface water content `[mol]` (related to ponded depth)
- `p` = surface pressure `[Pa]` (primary variable, `surface-pressure`)
- `h(p)` = ponded depth derived from pressure relative to atmospheric: `h = max(0, (p - p_atm) / (rho * g))`
- `n_l * k` = overland conductivity `[mol m^-1 s^-1]`, based on Manning's equation
- `Q_w` = source from precipitation, ET, and subsurface exchange `[mol s^-1]`

The potential used by the diffusion operator is `pres_elev = p + rho * g * elev` (pressure-plus-elevation), accessed via field key `surface-pres_elev`.

(Source: `src/pks/flow/overland_pressure.hh:14-15`)

### Key fields

| Field key (default) | Description | Units |
|---|---|---|
| `surface-pressure` | Primary variable, liquid pressure | Pa |
| `surface-water_content` | Conserved quantity | mol |
| `surface-ponded_depth` | Ponded depth above land surface | m |
| `surface-pres_elev` | Diffusion potential (pressure + elevation) | Pa (or m head) |
| `surface-elevation` | Surface DEM elevation | m |
| `surface-slope_magnitude` | Slope magnitude for Manning | -- |
| `surface-water_flux` | Overland flux on surface mesh faces | mol s^-1 |
| `surface-overland_conductivity` | Manning-derived conductivity | mol m^-1 s^-1 |

### Source files

| File | Key methods |
|---|---|
| `overland_pressure_pk.cc` | Constructor, `parseParameterList()`, `Setup()`, `SetupOverlandFlow_()`, `SetupPhysicalEvaluators_()`, `Initialize()`, `CommitStep()`, `UpdatePermeabilityData_()` |
| `overland_pressure_physics.cc` | `ApplyDiffusion_()`, `AddAccumulation_()`, `AddSourceTerms_()`, `AddSourcesToPrecon_()` |
| `overland_pressure_ti.cc` | `FunctionalResidual()`, `ApplyPreconditioner()`, `UpdatePreconditioner()`, `ModifyPredictor()`, `ModifyCorrection()` |

### Overland conductivity and Manning's equation

The Manning-based conductivity evaluator lives in `src/pks/flow/constitutive_relations/overland_conductivity/`. It computes:

```
k = (1/n) * h^(5/3) / slope^(1/2)
```

where `n` is Manning's roughness coefficient, `h` is ponded depth, and `slope` is the local slope magnitude. The result is the scalar coefficient in the diffusion operator (the analog of relative permeability in Richards). The conductivity is cell-defined and upwinded to faces using the same upwinding machinery as Richards.

### Diffusion term (`ApplyDiffusion_`)

`src/pks/flow/overland_pressure_physics.cc:20-48`

1. Calls `UpdatePermeabilityData_()` to upwind the Manning conductivity to faces
2. Assembles the diffusion operator using `pres_elev` as the potential (not raw pressure)
3. Derives face fluxes from the potential gradient
4. Writes `surface-water_flux` field

### Accumulation term (`AddAccumulation_`)

`src/pks/flow/overland_pressure_physics.cc:54-83`

Standard backward-Euler: `(WC_new - WC_old) / dt`, cell-component only.

### Source terms (`AddSourceTerms_`)

`src/pks/flow/overland_pressure_physics.cc:90-119`

Three additive sources:

1. External source (precipitation, ET): from `source_key_`, scaled by cell volume
2. Subsurface exchange flux (when `coupled_to_subsurface_via_head_`): adds the field `surface_subsurface_flux` directly (units already `[mol s^-1]`)

The subsurface-exchange contribution is sign-consistent with the Richards top-face Neumann BC.

### Coupling to subsurface

Two flags set by the MPC:

- `coupled_to_subsurface_via_head_` — overland flow drives subsurface top BC as Dirichlet (continuity of head)
- `coupled_to_subsurface_via_flux_` — exchange flux from subsurface is applied as Neumann to overland accumulation

(Source: `src/pks/flow/overland_pressure.hh:272-274`)

In most production permafrost runs, the full coupled MPC (`MPCCoupledWater` or similar, topic 04) uses the flux exchange mode, where the subsurface Richards top-face flux and the overland source are determined simultaneously within the MPC Newton iteration.

### Boundary conditions

`FlowBCFactory` creates BC objects from the `"boundary conditions"` sublist:

- Zero-gradient (default outflow) — `bc_zero_gradient_`
- Head Dirichlet — `bc_head_`
- Pressure Dirichlet — `bc_pressure_`
- Mass flux Neumann — `bc_flux_`
- Seepage head — `bc_seepage_head_`
- Seepage pressure — `bc_seepage_pressure_`
- Critical depth — `bc_critical_depth_`
- Level — `bc_level_`
- Tidal — `bc_tidal_` (for coastal scenarios)
- Dynamic — `bc_dynamic_` (time-varying)

(Source: `src/pks/flow/overland_pressure.hh:297-308`)

### Globalization

- `"allow no negative ponded depths"` — modifies correction to prevent negative ponded depths during Newton iteration
- `"min ponded depth for velocity calculation"` (default 1 cm) — below this depth, declares velocity zero
- `"limit correction to pressure change [Pa]"` — clips Newton pressure updates
- `"min ponded depth for tidal bc"` (default 2 cm) — tidal BC control

(Source: `src/pks/flow/overland_pressure.hh:64-80`)

## IcyOverlandFlow

### Class and registration

```
namespace Amanzi::Flow
class IcyOverlandFlow : public OverlandPressureFlow
PK type string: "overland flow with ice"
```

Source: `src/pks/flow/icy_overland.hh`, `src/pks/flow/icy_overland.cc`

`IcyOverlandFlow` is a minimal extension of `OverlandPressureFlow`. The only override is `SetupPhysicalEvaluators_()`, which registers the surface ice-aware conductivity evaluators instead of the standard Manning ones.

(Source: `src/pks/flow/icy_overland.hh:56`)

This PK is used when the surface can freeze. The ice-aware conductivity computes an effective Manning coefficient that decreases as the fraction of frozen surface water increases. The unfrozen fraction field (`surface-unfrozen_fraction`) is provided by an evaluator from `src/constitutive_relations/`.

## SnowDistribution

Snow redistribution by `SnowDistribution` is documented in `snow_and_freezing.md`.

## Relation to Subsurface PKs

The surface flow PK operates on the extracted surface mesh (a 2-D manifold). Faces shared between surface and subsurface mesh form the coupling interface. The exchange flux (`surface-surface_subsurface_flux`) flows across this interface and is mediated by the MPC.

At the surface-subsurface interface:
- Subsurface top-face Darcy flux = overland bottom-face normal flux (by mass conservation)
- In head-coupling mode: surface pressure = subsurface top-face pressure (Dirichlet)

See topic 04 (MPC) for details on how the coupled Newton system is assembled across this interface.
