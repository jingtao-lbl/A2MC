---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Energy PKs Overview

## Directory contents

`src/pks/energy/` contains approximately 20 source files implementing one abstract base class and four concrete PK families, plus a `constitutive_relations/` subtree for energy-specific evaluators.

```
src/pks/energy/
├── energy_base.hh / energy_base_pk.cc / energy_base_physics.cc / energy_base_ti.cc
├── energy_two_phase.hh / energy_two_phase.cc
├── energy_three_phase.hh / energy_three_phase.cc
├── energy_surface_ice.hh / energy_surface_ice.cc
├── energy_interfrost.hh / energy_interfrost.cc
├── energy_bc_factory.hh
├── advection_diffusion/
└── constitutive_relations/
    ├── energy/       (ThreePhaseEnergyModel, LiquidGas, LiquidIce, RichardsEnergy, SurfaceIce)
    ├── enthalpy/     (EnthalpyEvaluator)
    ├── internal_energy/  (IEM: linear, quadratic, water vapor)
    ├── source_terms/ (energy source evaluators)
    └── thermal_conductivity/  (two-phase and three-phase TC models + evaluators)
```

## PK Inheritance Hierarchy

```
PK
└── PK_PhysicalBDF_Default              (Amanzi)
    └── EnergyBase                       (src/pks/energy/energy_base.hh)
        ├── TwoPhase                     (src/pks/energy/energy_two_phase.hh)
        │   └── ThreePhase               (src/pks/energy/energy_three_phase.hh)
        │       └── InterfrostEnergy     (src/pks/energy/energy_interfrost.hh)
        └── EnergySurfaceIce             (src/pks/energy/energy_surface_ice.hh)
```

`EnergyBase` is abstract and cannot be instantiated directly; it implements all physics methods. Concrete subclasses override only `SetupPhysicalEvaluators_()` to register the correct energy, enthalpy, and thermal conductivity evaluators for their phase configuration.

## EnergyBase: the common equation

All energy PKs solve the following advection-diffusion equation for temperature:

```
d(E)/dt  +  div [ q * e(T) ]  -  div [ kappa * grad T ]  =  Q_w * e(T) + Q_e
```

where:
- `E` = total energy stored in cell (conserved quantity) `[MJ]`
- `q` = Darcy water flux vector `[mol s^-1]` (provided by the flow PK)
- `e(T)` = specific enthalpy of water `[MJ mol^-1]`
- `kappa` = thermal conductivity `[W m^-1 K^-1]`
- `T` = temperature `[K]` (primary variable, `domain-temperature`)
- `Q_w e(T)` = enthalpy carried by mass sources
- `Q_e` = additional energy source `[MJ s^-1]`

(Source: `src/pks/energy/energy_base.hh:13-14`)

The equation is implemented via three additive contributions in `FunctionalResidual()`:

1. `AddAccumulation_()` — `(E_new - E_old) / dt`
2. `AddAdvection_()` — `div(q * e)` (treated implicitly by default)
3. `ApplyDiffusion_()` — `div(kappa * grad T)`

## Source files and method split

`EnergyBase` follows the same three-file `.cc` split as Richards:

| File | Key methods |
|---|---|
| `energy_base_pk.cc` | `parseParameterList()`, `Setup()`, `SetupEnergy_()`, `SetupPhysicalEvaluators_()`, `Initialize()`, `CommitStep()`, `UpdateConductivityData_()`, boundary condition methods |
| `energy_base_physics.cc` | `AddAccumulation_()`, `AddAdvection_()`, `ApplyDiffusion_()`, `AddSources_()`, `ApplyDirichletBCsToEnthalpy_()` |
| `energy_base_ti.cc` | `FunctionalResidual()`, `ApplyPreconditioner()`, `UpdatePreconditioner()`, `ErrorNorm()`, `IsAdmissible()`, `ModifyPredictor()`, `ModifyCorrection()` |

## PK module comparison

| Class | PK type string | Domain | Phase config | Thermal conductivity |
|---|---|---|---|---|
| `TwoPhase` | `"two-phase energy"` | subsurface | liquid + gas | Two-phase TC evaluator |
| `ThreePhase` | `"three-phase energy"` | subsurface | liquid + ice + gas | Three-phase TC evaluator (Peters-Lidard or volume-averaged) |
| `EnergySurfaceIce` | `"surface energy"` | surface | liquid + ice (surface) | Surface TC evaluator |
| `InterfrostEnergy` | (inherits ThreePhase) | subsurface | three-phase (benchmark) | Three-phase TC, specialized accumulation |

## Key evaluators consumed by energy PKs

| Field key (default) | Purpose | Units | Provided by |
|---|---|---|---|
| `domain-energy` | Conserved quantity | MJ | `ThreePhaseEnergyEvaluator` (or two-phase variant) |
| `domain-enthalpy` | Advective transport coefficient | MJ mol^-1 | `EnthalpyEvaluator` |
| `domain-thermal_conductivity` | Cell-based conductivity | W m^-1 K^-1 | TC evaluator (two- or three-phase) |
| `domain-upwind_thermal_conductivity` | Face-based conductivity | W m^-1 K^-1 | Upwinding of cell-based TC |
| `domain-water_flux` | Advecting flux from flow PK | mol s^-1 | Richards / Permafrost PK |
| `domain-water_content` | Used in error norm | mol | Water content evaluator |
| `domain-diffusive_energy_flux` | Diffusive energy flux on faces | MJ s^-1 | Written by this PK |
| `domain-advected_energy_flux` | Advected energy flux on faces | MJ s^-1 | Written by this PK |

## Thermal conductivity upwinding

Unlike Richards (which uses Darcy-flux upwinding for `k_r`), energy PKs default to arithmetic mean upwinding for thermal conductivity:

```cpp
// energy_base_pk.cc:197-206
std::string method_name = plist_->get<std::string>("upwind conductivity method", "arithmetic mean");
if (method_name == "cell centered") {
  upwinding_ = Teuchos::rcp(new Operators::UpwindCellCentered(...));
} else if (method_name == "arithmetic mean") {
  upwinding_ = Teuchos::rcp(new Operators::UpwindArithmeticMean(...));
}
```

Arithmetic mean is appropriate for thermal conductivity because temperature gradients are smooth (unlike saturation jumps in Richards). The harmonic mean option (`"cell centered"`) is also available.

(Source: `src/pks/energy/energy_base_pk.cc:197-206`)

## Advection treatment

The advection operator (`PDE_AdvectionUpwind`) carries enthalpy at the Darcy flux velocity. It is:

- **Included by default** (`"include thermal advection"` = true)
- **Implicit by default** (`"explicit advection"` = false)
- **Optionally suppressed from preconditioner** (`"supress advective terms in preconditioner"` = false)

Suppressing advection from the preconditioner (while keeping it in the residual) is a common performance optimization for strongly diffusion-dominated regimes. It makes the linear solve easier without changing the converged answer.

(Source: `src/pks/energy/energy_base_pk.cc:308-357`)

## Admissibility check

`EnergyBase::IsAdmissible()` rejects any iterate with temperature outside [200 K, 330 K]:

```cpp
// energy_base_pk.cc:688
if (minT < 200.0 || maxT > 330.0) { return false; }
```

This is a hard constraint that triggers a BDF timestep restart when temperature wanders outside physically meaningful bounds.

(Source: `src/pks/energy/energy_base_pk.cc:663-701`)

## Predictor modification for freezing

When `"modify predictor for freezing"` = true, `ModifyPredictor()` prevents extrapolations that jump across the phase-change temperature (273.15 K):

```cpp
// energy_base_pk.cc:725-748
if (u0_c[0][c] > 273.15 && u_c[0][c] < 273.15) {
  u_c[0][c] = 273.15 - 0.00001;  // clip to just below freezing
}
```

This globalization heuristic reduces BDF timestep rejections near the freeze-thaw front.

(Source: `src/pks/energy/energy_base_pk.cc:721-748`)

## Coupling to surface / subsurface

`EnergyBase` supports four coupling modes (typically set by MPC):

- `coupled_to_surface_via_temp_` — subsurface top BC set to surface temperature (Dirichlet)
- `coupled_to_surface_via_flux_` — subsurface top BC set to surface energy flux (Neumann)
- `coupled_to_subsurface_via_temp_` — surface bottom BC set to subsurface temperature (Dirichlet)
- `coupled_to_subsurface_via_flux_` — surface receives subsurface energy flux (Neumann)

(Source: `src/pks/energy/energy_base.hh:319-324`)

## Energy constitutive relations subtree

The `src/pks/energy/constitutive_relations/` subtree (documented in topic 05) provides:

- **Energy density evaluators** (`energy/`): `ThreePhaseEnergyEvaluator`, `LiquidIceEnergyEvaluator`, `RichardsEnergyEvaluator`, `SurfaceIceEnergyEvaluator`. These evaluate `E = cv * [phi * (n_l s_l u_l + n_i s_i u_i + n_g s_g u_g) + rho_r u_r (1 - phi0)]`.

- **Internal energy models** (`internal_energy/`): `IEMLinear` (linear in T), `IEMQuadratic`, `IEMWaterVapor`

- **Enthalpy** (`enthalpy/`): `EnthalpyEvaluator` — `h = u + p / n_l`

- **Thermal conductivity** (`thermal_conductivity/`):
  - Two-phase: `ThermalConductivityTwoPhasePetersLidard`, `ThermalConductivityTwoPhaseWetDry`
  - Three-phase: `ThermalConductivityThreePhasePetersLidard` (default for permafrost), `ThermalConductivityThreePhaseSutraHacked`, `ThermalConductivityThreePhaseVolumeAveraged`, `ThermalConductivityThreePhaseWetDry`
  - Surface: `ThermalConductivitySurfaceEvaluator`
