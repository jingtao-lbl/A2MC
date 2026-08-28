---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Flow PKs Overview

## Directory contents

`src/pks/flow/` contains 34 source files implementing five distinct PK families plus a local `constitutive_relations/` subtree for flow-specific evaluators (WRMs, relative permeability, overland conductivity, water-content models, source terms, elevation models, porosity).

```
src/pks/flow/
├── richards.hh / richards_pk.cc / richards_physics.cc / richards_ti.cc
├── permafrost.hh / permafrost_pk.cc
├── preferential.hh / preferential_pk.cc
├── interfrost.hh / interfrost.cc
├── overland_pressure.hh / overland_pressure_pk.cc / overland_pressure_physics.cc / overland_pressure_ti.cc
├── icy_overland.hh / icy_overland.cc
├── snow_distribution.hh / snow_distribution_pk.cc / snow_distribution_physics.cc / snow_distribution_ti.cc
├── flow_bc_factory.hh
├── predictor_delegate_bc_flux.hh / .cc
├── richards_steadystate.hh / .cc
└── constitutive_relations/
    ├── wrm/               (WRM models + evaluators + permafrost-WRM models)
    ├── overland_conductivity/
    ├── water_content/
    ├── sources/
    ├── elevation/
    └── porosity/
```

## PK Inheritance Hierarchy

```
PK
└── PK_PhysicalBDF_Default              (pk_physical_bdf_default.hh, Amanzi)
    ├── Richards                         (src/pks/flow/richards.hh)
    │   ├── Permafrost                   (src/pks/flow/permafrost.hh)
    │   │   └── Interfrost               (src/pks/flow/interfrost.hh)
    │   └── Preferential                 (src/pks/flow/preferential.hh)
    ├── OverlandPressureFlow             (src/pks/flow/overland_pressure.hh)
    │   └── IcyOverlandFlow              (src/pks/flow/icy_overland.hh)
    └── SnowDistribution                 (src/pks/flow/snow_distribution.hh)
```

All flow PKs inherit from `PK_PhysicalBDF_Default`, which provides BDF (Backward Differentiation Formula) time-stepping via Amanzi's `BDFFnBase` interface. This means each PK implements:

- `FunctionalResidual()` — the nonlinear residual `g(t, u, u_dot)`
- `ApplyPreconditioner()` — applies P^{-1} u
- `UpdatePreconditioner()` — assembles and factors P
- `ModifyPredictor()` — optional globalization hooks
- `ModifyCorrection()` — optional Newton-update limiters

The method files are split across three `.cc` files per PK following a naming convention:

- `_pk.cc` — `Setup()`, `Initialize()`, `CommitStep()`, operator construction
- `_physics.cc` — `ApplyDiffusion_()`, `AddAccumulation_()`, `AddSources_()`
- `_ti.cc` — `FunctionalResidual()`, `ApplyPreconditioner()`, `UpdatePreconditioner()`

## Key Design Patterns

### Evaluator graph

Flow PKs do not compute constitutive relations directly. Instead, they declare dependencies (via `requireEvaluatorAtNext()` / `S_->RequireEvaluator()`) on named `CompositeVector` fields whose values are provided by `EvaluatorSecondaryMonotype` objects registered in the `State`. This lazy evaluation DAG is triggered automatically when the PK calls `S_->GetEvaluator(key, tag).Update(*S_, name_)`.

The critical evaluators consumed by Richards-family PKs are:

| Field key | Evaluator family | Units |
|---|---|---|
| `DOMAIN-water_content` | `WaterContentEvaluator` (or permafrost variant) | mol |
| `DOMAIN-saturation_liquid` | `WRMEvaluator` / `WRMPermafrostEvaluator` | -- |
| `DOMAIN-saturation_ice` | `WRMPermafrostEvaluator` (permafrost only) | -- |
| `DOMAIN-relative_permeability` | `RelPermEvaluator` (or sutraice / frzBC variants) | -- |
| `DOMAIN-permeability` | field from input (TensorVector) | m^2 |
| `DOMAIN-molar_density_liquid` | EOS evaluator | mol m^-3 |
| `DOMAIN-mass_density_liquid` | EOS evaluator | kg m^-3 |

### Upwinding of relative permeability

Richards needs relative permeability on faces for the flux computation. The method is controlled by the `"relative permeability method"` input parameter:

- `"upwind with Darcy flux"` (default) — first-order upwind using the Darcy flux direction stored in `DOMAIN-water_flux_direction`
- `"upwind with gravity"` — upwind direction set by gravitational flux
- `"cell centered"` — harmonic mean (accurate for fully saturated, poor for dry conditions)
- `"arithmetic mean"` — simple average; not recommended

The upwinder objects are in `src/operators/upwinding/`.

(Source: `src/pks/flow/richards.hh:86-100`)

### Surface-subsurface coupling flags

Each Richards (and OverlandPressureFlow) PK has two optional coupling flags set by the MPC:

- `coupled_to_surface_via_flux_` — Neumann BC at the top face set from the exchange flux field
- `coupled_to_surface_via_head_` — Dirichlet BC at the top face set from surface pressure

These flags are set via XML parameters `"coupled to surface via flux"` and `"coupled to surface via head"` (defaults both false); in practice the MPC sets them programmatically.

(Source: `src/pks/flow/richards.hh:333-336`, `src/pks/flow/richards_pk.cc:127-138`)

### Boundary condition types (flow)

Created by `FlowBCFactory` from the `"boundary conditions"` sublist:

- Pressure Dirichlet (`bc_pressure_`)
- Head Dirichlet (`bc_head_`)
- Mass flux Neumann (`bc_flux_`)
- Fixed level (`bc_level_`)
- Seepage face (pressure-based; `bc_seepage_`, `bc_seepage_infilt_`)
- Infiltration override (`bc_infiltration_`)

(Source: `src/pks/flow/richards_pk.cc:175-198`)

### Permeability rescaling

To avoid numerical ill-conditioning from multiplying small absolute permeability values (m^2) by large molar density / viscosity ratios, Richards applies a user-specified rescaling factor (default 1e7) to both absolute and relative permeabilities. The value is stored as `permeability_rescaling` in `State` and applied globally.

(Source: `src/pks/flow/richards_pk.cc:112-115`, `src/pks/flow/richards.hh:44-47`)

## Module Summary Table

| Module | Primary variable | Domain mesh | Equation type |
|---|---|---|---|
| `Richards` | `domain-pressure` | subsurface 3-D | Richards (two-phase) |
| `Permafrost` | `domain-pressure` | subsurface 3-D | Richards (three-phase, freeze-thaw) |
| `Preferential` | `domain-pressure` | subsurface 3-D | Richards + gravity-driven preferential term |
| `Interfrost` | `domain-pressure` | subsurface 3-D | Richards (three-phase, INTERFROST benchmark) |
| `OverlandPressureFlow` | `surface-pressure` | surface 2-D | Diffusion wave (Manning) |
| `IcyOverlandFlow` | `surface-pressure` | surface 2-D | Diffusion wave with ice evaluators |
| `SnowDistribution` | `surface-precipitation_snow` | surface 2-D | Diffusion-wave redistribution (heuristic) |

## Local Constitutive Relations (flow-specific)

The `src/pks/flow/constitutive_relations/` subtree is documented as part of topic 05, but its most important components for permafrost are:

- `wrm/wrm_permafrost_evaluator.{hh,cc}` — evaluator that maps (pc_liq, pc_ice) to (s_liq, s_ice, s_gas) via a `WRMPermafrostModel`
- `wrm/wrm_fpd_permafrost_model.{hh,cc}` — Painter's freezing-point-depression (FPD) model; default for permafrost
- `wrm/wrm_implicit_permafrost_model.{hh,cc}`, `wrm_sutra_permafrost_model.{hh,cc}`, `wrm_mck_permafrost_model.{hh,cc}` — alternative three-phase saturation models
- `wrm/rel_perm_sutraice_evaluator.{hh,cc}`, `rel_perm_frzBC_evaluator.{hh,cc}` — relative permeability evaluators that account for ice clogging of pore space
