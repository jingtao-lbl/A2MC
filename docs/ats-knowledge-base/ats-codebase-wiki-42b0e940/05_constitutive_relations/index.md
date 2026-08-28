---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Constitutive Relations -- Topic Index

## Role in ATS

Process Kernels (PKs) solve conservation equations (Richards, energy, transport) that require
closure relations to map primary variables (pressure, temperature, saturation) to secondary
quantities (density, viscosity, relative permeability, phase saturations, etc.).  These closure
relations are **not** housed inside PKs; instead they are registered as **secondary evaluators**
in the Amanzi State/Evaluator DAG and consumed by PKs through that dependency graph.

The `src/constitutive_relations/` tree holds the evaluators that apply broadly across PKs.
Flow-specific closures (WRMs, capillary-pressure models) live under
`src/pks/flow/constitutive_relations/` and are documented in `water_retention.md`.

```
src/constitutive_relations/
  eos/                         -- Equations of state (density, viscosity, vapor pressure)
  generic_evaluators/          -- Arithmetic combiners: add, multiply, reciprocal, subgrid
  surface_subsurface_fluxes/   -- Evaluators that couple surface/subsurface meshes
  column_integrators/          -- Vertical column scans: thaw depth, water table, ALT temp

src/pks/flow/constitutive_relations/
  wrm/                         -- Water retention models + permafrost saturation models
  elevation/                   -- Depth, effective height, fractional conductance
  overland_conductance/        -- Manning conductance
  water_content/               -- Soil/surface water content evaluators
```

## Evaluator Pattern

Every closure is an `EvaluatorSecondaryMonotypeCV` (or its column-integrator variant).  PKs
request the field by name; the evaluator graph resolves all transitive dependencies
(temperature, pressure, saturation...) and calls each evaluator's `Evaluate_()` and
`EvaluatePartialDerivative_()` when values are needed.  No PK directly calls an EOS or WRM
object -- it reads the evaluated field from State.

Concrete EOS or WRM model objects are created by factories
(`EOSFactory`, `WRMFactory`, `WRMPermafrostFactory`) and stored inside their wrapping evaluators.
The factory key (e.g. `"EOS type" = "liquid water"`) selects the registered concrete class.

## File Map

| File | Content |
|---|---|
| `eos.md` | Equations of state: water, ice, ideal gas, vapor, salt water, linear |
| `water_retention.md` | WRM base interface, van Genuchten, Brooks-Corey, permafrost models |
| `surface_subsurface_fluxes.md` | Cross-domain flux/value evaluators |
| `generic_evaluators.md` | Additive, multiplicative, reciprocal, subgrid aggregate/disaggregate |
| `column_integrators.md` | Thaw depth, water table, active-layer temperature, column sum |

## Key Interdependencies (critical for ECRP)

For permafrost simulations the closure chain is:

```
temperature, pressure
  --> PCIceWater (ice-liquid capillary pressure)    [wrm/pc_ice_water.cc]
  --> WRMPermafrostEvaluator
        uses WRM (van Genuchten or Brooks-Corey) + WRMPermafrostModel
        outputs: saturation_liquid, saturation_ice, saturation_gas
  --> EOSEvaluator (ice density, water density)     [eos/eos_evaluator.cc]
  --> Darcy flux / energy equations in PKs
```

The permafrost saturation models are the most numerically sensitive component -- five
implementations exist with different accuracy/stability tradeoffs.  See `water_retention.md`.
