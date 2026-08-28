---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Snow and Freezing Extensions

## Scope

This file covers three things:

1. `SnowDistribution` PK — heuristic redistribution of incoming snowfall (lives in `src/pks/flow/`)
2. `IcyOverlandFlow` — freeze-aware surface flow (extends `OverlandPressureFlow`)
3. `EnergySurfaceIce` — surface energy PK that couples to the subsurface energy equation

**Important:** Snow water equivalent (SWE) evolution, snowmelt, and the full surface energy balance (radiation, turbulent fluxes, sublimation) are **not** implemented in `src/pks/flow/` or `src/pks/energy/`. Those processes are owned by `src/pks/surface_balance/` (topic 03). The PKs documented here handle only the spatial distribution of snowfall and the freeze-state of surface water; the full snow mass balance lives elsewhere.

## SnowDistribution

### Class and registration

```
namespace Amanzi::Flow
class SnowDistribution : public PK_PhysicalBDF_Default
PK type string: "snow distribution"
```

Source: `src/pks/flow/snow_distribution.hh`, `src/pks/flow/snow_distribution_pk.cc`, `src/pks/flow/snow_distribution_physics.cc`, `src/pks/flow/snow_distribution_ti.cc`

### Purpose

`SnowDistribution` redistributes incoming snow precipitation spatially across the surface mesh. It treats fresh snowfall as a source, then allows it to "flow" downhill using a diffusion-wave equation analogous to overland flow. The result is that new snow accumulates preferentially in topographic depressions, mimicking wind redistribution and gravitational settling.

From the header:

> "Think of it as an analogue to overland flow — it effectively ensures that new snow 'flows downhill,' due to a uniformly distributed random direction wind, and lands on the lowest lying areas."

(Source: `src/pks/flow/snow_distribution.hh:15-17`)

### Governing heuristic

The snow distribution equation is:

```
d(SWE)/dt  -  div [ k(SWE) * grad (SWE + elevation) ]  =  P_snow
```

where:
- `SWE` is snow water equivalent depth `[m]`
- `k(SWE)` is an effective snow conductivity controlled by Manning's coefficient (smoother = more uniform distribution)
- `P_snow` is the incoming precipitation rate `[m s^-1]`
- `elevation` is the surface DEM

The equation is solved over a single `"distribution time"` interval (default 86400 s = 1 day), then the result is committed as the new snow precipitation field. This is a sub-cycled problem: the PK advances over the precipitation interval, then commits once.

(Source: `src/pks/flow/snow_distribution.hh:27-43`)

### Key PK design notes

The comments in `snow_distribution.hh` include explicit warnings about fragility:

```
//  ALL SORTS OF FRAGILITY and UGLINESS HERE!
//  DO NOT USE THIS OUT IN THE WILD!
//
//  1. this MUST go first
//  2. it must be PERFECT NON_OVERLAPPING with everything else.
//  3. Extrapolating in the timestepper should break things, so don't.
//  4. set: pk's distribution time, potential's dt factor
```

(Source: `src/pks/flow/snow_distribution.hh:107-115`)

This PK is a specialized tool for realistic snowpack initialization in complex terrain. It is not a general-purpose solver and should be positioned first in the PK list if used.

### Key fields

| Field | Description | Units |
|---|---|---|
| `surface-precipitation_snow` | Output: redistributed snow | m SWE s^-1 |
| `surface-elevation` | Input: DEM | m |
| `surface-snow_conductivity` | Effective diffusivity for redistribution | m^2 s^-1 or similar |

### `CommitStep()` override

Unlike other PKs, `SnowDistribution::CommitStep()` is empty (no-op). The actual commit is done inside `AdvanceStep()`. This prevents the coordinator from re-committing the solution after the PKs own `AdvanceStep()` has already handled it.

(Source: `src/pks/flow/snow_distribution.hh:120-124`)

## IcyOverlandFlow

### Class and registration

```
namespace Amanzi::Flow
class IcyOverlandFlow : public OverlandPressureFlow
PK type string: "overland flow with ice"
```

Source: `src/pks/flow/icy_overland.hh`, `src/pks/flow/icy_overland.cc`

### Purpose

`IcyOverlandFlow` extends `OverlandPressureFlow` to handle surface water that can freeze. It is a thin wrapper: the only override is `SetupPhysicalEvaluators_()`, which registers ice-aware conductivity evaluators that reduce the effective Manning coefficient when the surface is (partially) frozen.

(Source: `src/pks/flow/icy_overland.hh:56`)

### Ice-aware conductivity

The ice-aware overland conductivity evaluator (in `src/pks/flow/constitutive_relations/overland_conductivity/`) computes:

```
k_eff = k_Manning * f_unfrozen
```

where `f_unfrozen` is the unfrozen fraction of surface water. As temperature drops toward or below 0°C, `f_unfrozen` decreases and overland flow effectively shuts off — ice blocks overland transport.

The unfrozen fraction field `surface-unfrozen_fraction` is evaluated from surface temperature by an evaluator in `src/constitutive_relations/`.

### When to use

`IcyOverlandFlow` should be used whenever surface freezing is expected (Arctic, subarctic, or seasonal freeze-thaw regimes). In temperate applications without surface ice, `OverlandPressureFlow` is sufficient.

## EnergySurfaceIce

### Class and registration

```
namespace Amanzi::Energy
class EnergySurfaceIce : public EnergyBase
PK type string: "surface energy"
```

Source: `src/pks/energy/energy_surface_ice.hh`, `src/pks/energy/energy_surface_ice.cc`

Note: despite the PK type string `"surface energy"`, this PK is **not** a full surface energy balance. It solves the thermal energy advection-diffusion equation on the surface mesh, representing heat transport in surface water (ponded water or flowing stream). The full surface energy balance (radiation, turbulent fluxes, latent heat of evaporation, snowmelt) is in `src/pks/surface_balance/` (topic 03), which provides the energy source term to this PK.

(Source: `src/pks/energy/energy_surface_ice.hh:15-22`)

### Physics

`EnergySurfaceIce` inherits all of `EnergyBase`'s physics. The primary variable is `surface-temperature`. The conserved quantity is the surface energy density, evaluated by `SurfaceIceEnergyEvaluator`.

The equation is:

```
d(E_surface)/dt  +  div(q_surf * h_surf)  -  div(kappa_surf * grad T)  =  Q_skin + Q_subsurface_exchange
```

where:
- `E_surface` = surface energy per unit area (ponded water + possible ice)
- `q_surf` = overland water flux (from `IcyOverlandFlow` or `OverlandPressureFlow`)
- `h_surf` = surface water enthalpy
- `kappa_surf` = surface thermal conductivity
- `Q_skin` = energy source from surface energy balance (skin temperature solver in topic 03)
- `Q_subsurface_exchange` = energy flux across surface-subsurface interface

### Coupling to subsurface energy

`EnergySurfaceIce` inherits `EnergyBase`'s coupling flags:

- `coupled_to_subsurface_via_flux_` — receives energy flux from subsurface energy PK as a Neumann source
- `coupled_to_subsurface_via_temp_` — temperature Dirichlet BC from subsurface

In fully coupled runs, the subsurface-to-surface energy exchange flux is set by the MPC.

(Source: `src/pks/energy/energy_surface_ice.hh:28-38`)

### Additional source terms

`EnergySurfaceIce::AddSources_()` and `AddSourcesToPrecon_()` extend `EnergyBase` to handle:

- `is_energy_source_term_` — general energy source (e.g., from skin energy balance)
- `is_water_source_term_` — source carries enthalpy of incoming water (precipitation)
- `is_air_conductivity_` — simple parameterization `q = K_s2a * (T_air - T_surf)` for sensible heat exchange with the atmosphere without running a full surface energy balance

The air conductivity term (flag `is_air_conductivity_`, coefficient `K_surface_to_air_`) is a simple fallback for cases where the full surface energy balance is not needed.

(Source: `src/pks/energy/energy_surface_ice.hh:79-91`)

## Summary: Snow and Freezing Architecture

The following diagram shows how snow and surface-freeze processes are distributed across ATS modules:

```
Atmospheric forcing (air T, precipitation, radiation)
           |
           v
src/pks/surface_balance/ (topic 03)
  - Full surface energy balance (SEB)
  - Snow SWE: accumulation, melt, sublimation
  - Provides: Q_skin (energy flux to surface), P_rain, P_snow (redistributed)
           |         |
           |         v
           |    src/pks/flow/SnowDistribution
           |       - Redistributes P_snow spatially
           |       - Output: surface-precipitation_snow
           |
           v
src/pks/energy/EnergySurfaceIce
  - Temperature of surface water
  - Receives Q_skin from surface_balance
  - Advects heat with overland flux
           |
           v
src/pks/flow/IcyOverlandFlow
  - Surface water routing
  - Freezing reduces effective Manning conductivity
           |
           v
Surface-subsurface interface (MPC, topic 04)
           |
           v
src/pks/flow/Permafrost + src/pks/energy/ThreePhase
  - Subsurface coupled freeze-thaw thermal-hydrology
  - See thermal_richards.md
```

The key architectural point is that **snow mass balance belongs to `surface_balance/`** and **snow redistribution belongs to `flow/SnowDistribution`** as a preprocessing step. The two are logically separate: redistribution shapes where snow goes; surface_balance determines how much SWE evolves over time.
