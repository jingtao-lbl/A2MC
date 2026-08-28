---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Richards Flow PK

## Class and registration

```
namespace Amanzi::Flow
class Richards : public PK_PhysicalBDF_Default
PK type string: "richards flow"
```

Source: `src/pks/flow/richards.hh`, `src/pks/flow/richards_pk.cc`, `src/pks/flow/richards_physics.cc`, `src/pks/flow/richards_ti.cc`

Factory registration: `static RegisteredPKFactory<Richards> reg_` (src/pks/flow/richards_pk_reg.hh)

## Governing Equation

Richards solves the two-phase, variable-density flow equation in the subsurface:

```
d(Theta)/dt  -  div [ (k_r * n_l / mu) * K * (grad p + rho * g * z_hat) ]  =  Q_w
```

where:
- `Theta` = total water content `[mol]` (conserved quantity, evaluated by `WaterContentEvaluator`)
- `p` = liquid pressure `[Pa]` (primary variable, `domain-pressure`)
- `k_r` = relative permeability `[-]` (field `domain-relative_permeability`)
- `n_l` = molar density of liquid `[mol m^-3]` (field `domain-molar_density_liquid`)
- `mu` = dynamic viscosity `[Pa s]` (from EOS)
- `K` = intrinsic permeability tensor `[m^2]` (field `domain-permeability`)
- `rho` = mass density of liquid `[kg m^-3]` (field `domain-mass_density_liquid`)
- `Q_w` = source term `[mol s^-1]`

The PDE uses the head-based potential `p + rho * g * z` for the diffusion operator.

(Source: equation in `src/pks/flow/richards.hh:15-16`)

## Source files and method split

| File | Methods implemented |
|---|---|
| `richards_pk.cc` | Constructor, `parseParameterList()`, `Setup()`, `SetupRichardsFlow_()`, `SetupPhysicalEvaluators_()`, `Initialize()`, `CommitStep()`, `CalculateDiagnostics()`, `UpdatePermeabilityData_()`, `UpdatePermeabilityDerivativeData_()`, `UpdateVelocity_()`, `InitializeHydrostatic_()` |
| `richards_physics.cc` | `ApplyDiffusion_()`, `AddAccumulation_()`, `AddSources_()`, `AddSourcesToPrecon_()`, `UpdateVelocity_()` |
| `richards_ti.cc` | `FunctionalResidual()`, `ApplyPreconditioner()`, `UpdatePreconditioner()`, `ModifyPredictor*()`, `IsAdmissible()`, `IsValid()`, `ModifyCorrection()` |

## Setup and operator construction

`Setup()` calls `SetupRichardsFlow_()` then `SetupPhysicalEvaluators_()`.

`SetupRichardsFlow_()` (src/pks/flow/richards_pk.cc:164-) constructs:

1. **Boundary condition objects** via `FlowBCFactory` from the `"boundary conditions"` sublist: pressure, head, level, mass flux, seepage face, and seepage-with-infiltration conditions.

2. **Diffusion operator** (`PDE_DiffusionWithGravity`) for the primary forward problem. Both the forward matrix (`matrix_diff_`) and preconditioner matrix (`preconditioner_diff_`) are constructed from `"diffusion"` and `"diffusion preconditioner"` sublists.

3. **Accumulation operator** (`PDE_Accumulation`) added to the preconditioner for the `d(Theta)/dt` Jacobian contribution.

4. **Upwinding objects** (`Upwinding`) for face-based relative permeability. The method is controlled by `"relative permeability method"` (default: `"upwind with Darcy flux"`).

5. **Permeability rescaling**: the factor `perm_scale_` (default 1e7) is written into State and applied to both relative and absolute permeability evaluators (src/pks/flow/richards_pk.cc:112-115).

`SetupPhysicalEvaluators_()` (src/pks/flow/richards_pk.cc, inside the two-phase branch) registers requirements:
- `conserved_key_` (water_content) at next and current tags, with derivative w.r.t. `key_` (pressure)
- `sat_key_` and `sat_gas_key_` at next and current
- `coef_key_` (relative_permeability) at next
- `molar_dens_key_`, `mass_dens_key_` at next
- WRM partition extracted from the evaluator for `sat_key_`

## Residual assembly: `FunctionalResidual()`

Called once per nonlinear iteration by the BDF time-stepper (src/pks/flow/richards_ti.cc:22-111):

```
g = 0
BCs updated
g += ApplyDiffusion_(tag_next)        // div K_uw grad p  operator, also writes flux
g += AddAccumulation_()               // (Theta_new - Theta_old) / dt
g += AddSources_(tag) if source term
```

### Diffusion term (`ApplyDiffusion_`)

`src/pks/flow/richards_physics.cc:27-57`

1. Calls `UpdatePermeabilityData_()` to upwind `k_r` onto faces → `domain-upwind_relative_permeability`
2. Triggers `mass_dens_key_` evaluator update (for gravity term)
3. Calls `matrix_diff_->SetDensity()`, `SetScalarCoefficient()`, `UpdateMatrices()`, `ApplyBCs()`
4. Calls `matrix_diff_->UpdateFlux()` to write the Darcy flux `domain-water_flux` [mol s^-1]
5. Calls `matrix_->ComputeNegativeResidual()` to add the diffusion contribution to `g`

### Accumulation term (`AddAccumulation_`)

`src/pks/flow/richards_physics.cc:63-84`

```
g_cell += (WC_new - WC_old) / dt
```

Both `WC_new` (at `tag_next_`) and `WC_old` (at `tag_current_`) are `CompositeVector`s with only cell components; the contribution is added only to the cell block of `g`.

### Source term (`AddSources_`)

`src/pks/flow/richards_physics.cc:91-117`

Evaluated at `tag_next_` (implicit) or `tag_current_` (explicit, controlled by `"explicit source term"` parameter). Units are `[mol s^-1]`; the source is volume-integrated by multiplying by cell volume.

## Preconditioner assembly: `UpdatePreconditioner()`

`src/pks/flow/richards_ti.cc:135-219`

1. Updates permeability tensor (if mesh deforms) and upwinded `k_r` (including derivatives if `jacobian_` flag is set)
2. Calls `preconditioner_diff_->SetScalarCoefficient(rel_perm, dkrdp)` where `dkrdp` is non-null only when the Jacobian correction is active
3. Assembles the diffusion block: `preconditioner_->Init()`, `UpdateMatrices()`, `ApplyBCs()`
4. If Jacobian: computes the Newton correction with `UpdateMatricesNewtonCorrection(flux, pressure)`
5. Adds accumulation block: `preconditioner_acc_->AddAccumulationTerm(*dwc_dp, h, "cell", false)` where `dwc_dp = dWC/dp`
6. Optionally adds source derivative via `AddSourcesToPrecon_(h)`

The Jacobian correction is delayed by `jacobian_lag_` iterations (default 0) to improve robustness in the first few Newton steps.

## Globalization heuristics

Richards has several optional Newton globalization steps (all default to false):

| Parameter | Method | Effect |
|---|---|---|
| `"modify predictor with consistent faces"` | `ModifyPredictorConsistentFaces_()` | Makes face pressures consistent with predicted cell pressures before the Newton solve begins |
| `"modify predictor via water content"` | `ModifyPredictorWC_()` | Extrapolates in water content space (Krabbenhoft method), clips to smaller of pressure/WC extrapolant |
| `"modify predictor for flux BCs"` | `ModifyPredictorFluxBCs_()` | Solves local nonlinear problem on boundary faces for infiltration into dry soil |
| `"limit correction to pressure change [Pa]"` | `ModifyCorrection()` | Clips Newton updates exceeding a pressure threshold |
| `"max valid change in saturation in a timestep"` | `IsValid()` | Rejects timesteps with saturation change > threshold |
| `"max valid change in ice saturation in a timestep"` | `IsValid()` | Same for ice saturation |

(Source: `src/pks/flow/richards.hh:120-130`, `src/pks/flow/richards_ti.cc`)

## Primary variables and outputs

| Field key (default) | Description | Units | Where written |
|---|---|---|---|
| `domain-pressure` | Primary variable | Pa | Updated by Newton solver |
| `domain-water_flux` | Darcy flux on faces | mol s^-1 | `ApplyDiffusion_()` |
| `domain-darcy_velocity` | Cell-centered Darcy velocity | m s^-1 | `UpdateVelocity_()` via `CalculateDiagnostics()` |
| `domain-saturation_liquid` | Liquid saturation | -- | WRM evaluator |
| `domain-saturation_gas` | Gas saturation | -- | WRM evaluator |
| `domain-water_content` | Conserved quantity | mol | Water content evaluator |

## Coupling to surface

Two coupling modes are supported (set by MPC, not by user directly):

**Neumann (flux) coupling** (`coupled_to_surface_via_flux_ = true`): the top-face boundary condition is overridden with the exchange flux from field `domain-surface_subsurface_flux`. This is the standard mode for coupled surface-subsurface simulations.

**Dirichlet (head) coupling** (`coupled_to_surface_via_head_ = true`): the top-face BC is set to the surface pressure (Dirichlet). Used in simpler formulations.

(Source: `src/pks/flow/richards.hh:334-336`, `src/pks/flow/richards_pk.cc:127-138`)

## Steady-state variant

`RichardsSteadyState` (`src/pks/flow/richards_steadystate.hh/.cc`) inherits from `Richards` and overrides `FunctionalResidual()` to drop the accumulation term, solving only the steady-state diffusion equation. Used for initial condition generation.

## Friend class

`Richards` declares `class Amanzi::MPCSubsurface` as a friend, giving the coupled MPC direct access to protected members (particularly operator data and coupling flags). See topic 04.

(Source: `src/pks/flow/richards.hh:436`)
