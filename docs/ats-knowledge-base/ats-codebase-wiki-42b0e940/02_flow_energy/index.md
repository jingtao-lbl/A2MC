---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Topic 02: Flow and Energy PKs

## Scope

This topic covers all process-kernel (PK) source files in:

- `src/pks/flow/` — subsurface Richards flow, overland flow, snow distribution, and freeze-aware variants
- `src/pks/energy/` — subsurface and surface energy (thermal) PKs, including the three-phase permafrost energy equation

Cross-references are made to `src/pks/mpc/` (topic 04) for the coupled solvers that glue flow and energy together, `src/pks/surface_balance/` (topic 03) for surface energy balance and snow SWE, `src/constitutive_relations/` (topic 05) for equation-of-state and water-retention models, and `src/operators/` (topic 06) for the MFD diffusion operators.

## Physics Modules Covered

### Flow PKs (`src/pks/flow/`)

| Class | PK type string | File | Description |
|---|---|---|---|
| `Richards` | `"richards flow"` | `richards.hh`, `richards_pk.cc`, `richards_physics.cc`, `richards_ti.cc` | Two-phase variable-density Richards equation (subsurface) |
| `Permafrost` | `"permafrost flow"` | `permafrost.hh`, `permafrost_pk.cc` | Three-phase Richards with ice; swaps in permafrost WRM evaluators |
| `Preferential` | (inherits Richards) | `preferential.hh`, `preferential_pk.cc` | Gravity-driven preferential flow extension to Richards |
| `Interfrost` | (inherits Permafrost) | `interfrost.hh`, `interfrost.cc` | Special accumulation term for INTERFROST benchmark comparison |
| `OverlandPressureFlow` | `"overland flow, pressure basis"` | `overland_pressure.hh`, `overland_pressure_pk.cc`, `overland_pressure_physics.cc`, `overland_pressure_ti.cc` | Diffusion-wave overland flow, pressure primary variable |
| `IcyOverlandFlow` | `"overland flow with ice"` | `icy_overland.hh`, `icy_overland.cc` | Overland flow with freeze-thaw evaluators for icy surfaces |
| `SnowDistribution` | `"snow distribution"` | `snow_distribution.hh`, `snow_distribution_pk.cc`, `snow_distribution_physics.cc`, `snow_distribution_ti.cc` | Heuristic diffusion-wave redistribution of incoming snowfall |

### Energy PKs (`src/pks/energy/`)

| Class | PK type string | File | Description |
|---|---|---|---|
| `EnergyBase` | (abstract, not directly used) | `energy_base.hh`, `energy_base_pk.cc`, `energy_base_physics.cc`, `energy_base_ti.cc` | Base class: advection-diffusion energy equation |
| `TwoPhase` | `"two-phase energy"` | `energy_two_phase.hh`, `energy_two_phase.cc` | Two-phase (liquid + gas/air) subsurface energy |
| `ThreePhase` | `"three-phase energy"` | `energy_three_phase.hh`, `energy_three_phase.cc` | Three-phase (liquid + ice + gas) subsurface energy for permafrost |
| `EnergySurfaceIce` | `"surface energy"` | `energy_surface_ice.hh`, `energy_surface_ice.cc` | Surface energy transport, couples to subsurface via flux or temperature |
| `InterfrostEnergy` | (inherits ThreePhase) | `energy_interfrost.hh`, `energy_interfrost.cc` | INTERFROST benchmark variant |

## Science Overview

### Subsurface coupled flow-energy

The standard permafrost configuration couples two PKs via an MPC:

1. **Permafrost flow PK** solves the three-phase Richards equation with primary variable `domain-pressure`. Water content includes liquid and ice fractions; freeze-thaw partitioning is provided by a `WRMPermafrostEvaluator` that maps capillary pressures to three saturations (liquid, ice, gas).

2. **ThreePhase energy PK** solves the advection-diffusion energy equation with primary variable `domain-temperature`. Thermal conductivity depends on all three phase saturations; the conserved quantity includes latent heat implicitly through the saturation-dependent internal energies.

The MPC (see topic 04, `MPCCoupledFlowEnergy`) couples them globally-implicit at every Newton iteration.

### Surface flow

`OverlandPressureFlow` solves the diffusion-wave approximation for overland routing on the extracted surface mesh. Its source term receives infiltration/exfiltration from the subsurface Richards solver, mediated by the surface-subsurface MPC.

### Snow distribution

`SnowDistribution` is a standalone heuristic PK that downslope-redistributes incoming snowfall using a diffusion-wave analogy. It writes a redistributed `surface-precipitation_rain` / `surface-precipitation_snow` field consumed by the surface energy balance. It is documented here because it lives in `src/pks/flow/`, but snow mass balance (SWE, melt) lives in `src/pks/surface_balance/` (topic 03).

## File Map

| File | Topic |
|---|---|
| `flow_overview.md` | Full inventory of `src/pks/flow/`, PK hierarchy |
| `richards_pk.md` | `Richards` class in depth |
| `surface_flow.md` | `OverlandPressureFlow` and `IcyOverlandFlow` |
| `energy_overview.md` | Full inventory of `src/pks/energy/`, class hierarchy |
| `thermal_richards.md` | `Permafrost` + `ThreePhase` coupled permafrost system (ECRP-critical) |
| `snow_and_freezing.md` | `SnowDistribution`, freeze-aware flow/energy extensions |
