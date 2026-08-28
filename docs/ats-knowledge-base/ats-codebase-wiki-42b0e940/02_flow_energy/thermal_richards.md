---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Coupled Flow-Energy Permafrost System

**This is the highest-priority file for the ECRP narrative.** It documents the Permafrost flow PK and ThreePhase energy PK — the two components that, together with the MPC coupler (topic 04), form ATS's coupled freeze-thaw thermal-hydrology solver for permafrost applications.

## Overview

Permafrost simulation in ATS requires two simultaneously solved PKs:

1. **`Permafrost` flow PK** (`"permafrost flow"`) — three-phase Richards equation; primary variable is liquid pressure
2. **`ThreePhase` energy PK** (`"three-phase energy"`) — three-phase advection-diffusion energy equation; primary variable is temperature

These two PKs share state variables through the evaluator DAG: the flow PK computes the Darcy flux that drives enthalpy advection in the energy PK; the energy PK computes temperature that drives the phase-fraction split (liquid vs. ice) consumed by the flow PK's water retention model.

The coupling is made globally-implicit by `MPCCoupledFlowEnergy` (topic 04), which assembles a block-coupled Newton system at every iteration.

## Permafrost Flow PK

### Class

```
namespace Amanzi::Flow
class Permafrost : public Richards
PK type string: "permafrost flow"
```

Source: `src/pks/flow/permafrost.hh`, `src/pks/flow/permafrost_pk.cc`

`Permafrost` inherits all of Richards' physics methods unchanged. The only difference is `SetupPhysicalEvaluators_()`, which registers three-phase evaluators instead of two-phase ones.

(Source: `src/pks/flow/permafrost.hh:10-29`, confirming the comment: "Note that the only difference between permafrost and richards is in constitutive relations.")

### What changes relative to Richards

| Item | Richards (two-phase) | Permafrost (three-phase) |
|---|---|---|
| Water content evaluator | `WaterContentEvaluator` (liquid only) | Permafrost variant (liquid + ice + latent heat) |
| Saturation evaluator | `WRMEvaluator` (liquid + gas) | `WRMPermafrostEvaluator` (liquid + ice + gas) |
| Ice saturation field | Not registered | `domain-saturation_ice` registered at next and current tags |
| Relative permeability | `RelPermEvaluator` | `RelPermSutraIceEvaluator` or `RelPermFrzBCEvaluator` (ice-clogging options) |
| Capillary pressures | `pc_liq` only | Both `pc_liq` and `pc_ice` passed to WRM |

(Source: `src/pks/flow/permafrost_pk.cc:36-95`)

### Three-phase saturations from WRMPermafrostEvaluator

The evaluator `WRMPermafrostEvaluator` (src/pks/flow/constitutive_relations/wrm/wrm_permafrost_evaluator.hh) takes two capillary pressures as input:

- `domain-capillary_pressure_gas_liq` (`pc_liq`): liquid-gas capillary pressure, function of liquid saturation
- `domain-capillary_pressure_liq_ice` (`pc_ice`): liquid-ice capillary pressure, related to temperature via the Clausius-Clapeyron equation

It outputs three saturations: `s_liq`, `s_ice`, `s_gas`.

The mapping from `(pc_liq, pc_ice)` to saturations is provided by a `WRMPermafrostModel`, with multiple implementations:

| Class | Key | Description |
|---|---|---|
| `WRMFPDPermafrostModel` | `"fpd permafrost model"` | Painter's freezing-point-depression model (default) |
| `WRMImplicitPermafrostModel` | `"implicit permafrost model"` | Implicit formulation of Painter-Karra 2014 |
| `WRMMCKPermafrostModel` | `"mck permafrost model"` | McKenzie et al. model |
| `WRMSutraPermafrostModel` | `"sutra permafrost model"` | SUTRA-ICE model |
| `WRMInterfrostPermafrostModel` | `"interfrost permafrost model"` | For INTERFROST benchmark |
| `WRMOldPermafrostModel` | `"old permafrost model"` | Legacy formulation |

(Source: `src/pks/flow/constitutive_relations/wrm/`)

### FPD permafrost model (default): saturation logic

`WRMFPDPermafrostModel::saturations()` (src/pks/flow/constitutive_relations/wrm/wrm_fpd_permafrost_model.cc:27-46) implements the following logic:

```
sats[0] = s_gas, sats[1] = s_liq, sats[2] = s_ice

if (pc_liq <= 0):  # saturated (p >= p_atm)
    s_liq = WRM.saturation(pc_ice)
    s_ice = 1.0 - s_liq
    s_gas = 0

elif (pc_ice <= pc_liq):  # unfrozen unsaturated
    s_ice = 0
    s_liq = WRM.saturation(pc_liq)
    s_gas = 1.0 - s_liq

else:  # frozen, two capillary pressures active
    s_liq = WRM.saturation(pc_ice)
    s_ice = 1.0 - s_liq / WRM.saturation(pc_liq)
    s_gas = 1.0 - s_liq - s_ice
```

The ice-liquid capillary pressure `pc_ice` acts as a modified liquid capillary pressure during freezing, implementing the Clausius-Clapeyron constraint. As temperature drops below 273.15 K, `pc_ice` increases, pulling liquid out of the pore space into the ice phase.

(Source: `src/pks/flow/constitutive_relations/wrm/wrm_fpd_permafrost_model.cc:27-46`)

### Relative permeability with ice

Standard Richards uses `RelPermEvaluator` based only on liquid saturation. Permafrost uses one of two specialized evaluators:

- `RelPermSutraIceEvaluator`: includes an ice-clogging term that reduces relative permeability as ice fraction increases (SUTRA-ICE parameterization)
- `RelPermFrzBCEvaluator`: freeze-curve-based relative permeability

(Source: `src/pks/flow/permafrost_pk.cc:21-26`, imports of `rel_perm_sutraice_evaluator.hh` and `rel_perm_frzBC_evaluator.hh`)

The choice of evaluator is controlled by the `"type"` entry in the `"conductivity"` evaluator list in the input XML.

## ThreePhase Energy PK

### Class

```
namespace Amanzi::Energy
class ThreePhase : public TwoPhase
PK type string: "three-phase energy"
```

Source: `src/pks/energy/energy_three_phase.hh`, `src/pks/energy/energy_three_phase.cc`

`ThreePhase` inherits from `TwoPhase` (which inherits from `EnergyBase`). Like `Permafrost` in the flow hierarchy, `ThreePhase` only overrides `SetupPhysicalEvaluators_()` to swap in the three-phase thermal conductivity evaluator.

```cpp
// energy_three_phase.cc:36-42
void ThreePhase::SetupPhysicalEvaluators_() {
  if (plist_->isSublist("thermal conductivity evaluator")) {
    auto& tcm_plist = S_->GetEvaluatorList(conductivity_key_);
    tcm_plist.setParameters(plist_->sublist("thermal conductivity evaluator"));
    tcm_plist.set("evaluator type", "three-phase thermal conductivity");
  }
  EnergyBase::SetupPhysicalEvaluators_();
}
```

(Source: `src/pks/energy/energy_three_phase.cc:32-42`)

### Conserved quantity: total energy

The three-phase energy density is computed by `ThreePhaseEnergyEvaluator`, which calls `ThreePhaseEnergyModel::Energy()`:

```cpp
// three_phase_energy_model.cc:41-57
E = cv * ( phi * (n_g * s_g * u_g + n_i * s_i * u_i + n_l * s_l * u_l)
         + rho_r * u_r * (1 - phi0) )
```

where:
- `cv` = cell volume `[m^3]`
- `phi` = porosity `[-]`, `phi0` = base porosity (before deformation) `[-]`
- `s_l, s_i, s_g` = liquid, ice, gas saturations `[-]`
- `n_l, n_i, n_g` = molar densities of each phase `[mol m^-3]`
- `u_l, u_i, u_g` = internal energies of each phase `[MJ mol^-1]`
- `rho_r` = rock grain density `[mol m^-3]`
- `u_r` = internal energy of rock `[MJ mol^-1]`

(Source: `src/pks/energy/constitutive_relations/energy/three_phase_energy_model.cc:41-57`)

The rock term `rho_r * u_r * (1 - phi0)` represents heat stored in the mineral matrix. The liquid-ice-gas pore-space terms carry the latent heat implicitly through the temperature-dependent internal energies `u_l(T)` and `u_i(T)`. The latent heat of fusion appears as the discontinuity in `u(T)` across the phase boundary.

### Three-phase thermal conductivity (Peters-Lidard)

The default thermal conductivity model for permafrost is `ThermalConductivityThreePhasePetersLidard`:

```cpp
// thermal_conductivity_threephase_peterslidard.cc:29-41
double k_dry = (d * (1-phi) * k_soil + k_gas * phi) / (d * (1-phi) + phi);
double k_sat_u = k_soil^(1-phi) * k_liquid^phi;   // saturated unfrozen
double k_sat_f = k_soil^(1-phi) * k_ice^phi;       // saturated frozen
double kersten_u = (s_liq + eps)^alpha_u;
double kersten_f = (s_ice + eps)^alpha_f;
return kersten_f * k_sat_f + kersten_u * k_sat_u + (1 - kersten_f - kersten_u) * k_dry;
```

Parameters (all user-specified in input XML):
- `k_soil`, `k_liquid`, `k_ice`, `k_gas`: phase thermal conductivities `[W m^-1 K^-1]`
- `alpha_u`, `alpha_f`: Kersten number exponents for unfrozen and frozen conditions
- `d = 0.053`: empirical constant (hardcoded)
- `eps = 1e-10`: regularization

(Source: `src/pks/energy/constitutive_relations/thermal_conductivity/thermal_conductivity_threephase_peterslidard.cc:29-41`)

The Peters-Lidard model is based on `Atchley et al. GMD 2015` supplementary material. It smoothly interpolates between dry, saturated-frozen, and saturated-unfrozen end-member conductivities using Kersten numbers as mixing weights. At high ice saturation, it approaches the frozen-saturated value (higher conductivity), which is the dominant cold-season state in permafrost.

### Alternative three-phase TC models

| Class | Key | Notes |
|---|---|---|
| `ThermalConductivityThreePhaseVolumeAveraged` | `"three-phase volume averaged"` | Arithmetic volume average across phases |
| `ThermalConductivityThreePhaseWetDry` | `"three-phase wet/dry"` | Interpolation between wet and dry conductivities |
| `ThermalConductivityThreePhaseSutraHacked` | `"three-phase SUTRA hacked"` | SUTRA-ICE TC with modifications |

### Latent heat (implicit treatment)

ATS does **not** add an explicit latent heat source term to the energy equation. Instead, the latent heat is captured implicitly through the temperature-dependent energy density: the `u_l(T)` and `u_i(T)` evaluators (via `IEMLinear`) have different slopes and reference values, so the `d(E)/dT` derivative is large near 273.15 K (the large effective heat capacity in the mushy zone). This appears naturally in the accumulation Jacobian:

```
dE/dT = dE/ds_l * ds_l/dT + dE/ds_i * ds_i/dT + phi * (n_l s_l * du_l/dT + n_i s_i * du_i/dT + n_g s_g * du_g/dT) + rho_r * du_r/dT
```

The large `ds_l/dT` and `ds_i/dT` near the phase boundary (coming through the Clausius-Clapeyron relation embedded in the WRM) creates the apparent latent heat effect in the Newton Jacobian.

### INTERFROST variant

`InterfrostEnergy` (`src/pks/energy/energy_interfrost.hh`) inherits `ThreePhase` and overrides:

- `AddAccumulation_()` — uses a specialized accumulation term matching the INTERFROST benchmark specification
- `UpdatePreconditioner()` — corresponding preconditioner modification
- `SetupPhysicalEvaluators_()` — uses a distinct `"interfrost"` energy evaluator

This class exists only for reproducibility of the INTERFROST code-comparison benchmark and should not be used in production permafrost runs.

(Source: `src/pks/energy/energy_interfrost.hh:27-50`)

## Coupled System: Permafrost + ThreePhase

### Information flow between PKs

```
Temperature (ThreePhase PK)
   |
   v
Clausius-Clapeyron  -->  pc_ice = f(T)
   |
   v
WRMPermafrostEvaluator  -->  s_liq(pc_liq, pc_ice), s_ice(...), s_gas(...)
   |
   v
Permafrost flow PK:
  - water_content = phi * (n_l * s_l + n_i * s_i) * cv   [conserved quantity]
  - relative_permeability = f(s_liq, s_ice)
  - Darcy flux q = K_eff grad(p + rho g z)
       |
       v
ThreePhase energy PK:
  - advection: div(q * enthalpy)
  - thermal_conductivity = f(phi, s_liq, s_ice, T)   [Peters-Lidard]
  - energy E = cv * [phi(...) + rho_r u_r (1-phi0)]
```

The coupling is bidirectional: temperature controls ice content (affecting water content and permeability), and the Darcy flux controls enthalpy advection. Both PKs must converge simultaneously.

### MPC coupling (reference to topic 04)

The coupled system is assembled by `MPCCoupledFlowEnergy` using one of two strategies:

1. **Globally-implicit block Newton**: Both pressure and temperature are updated simultaneously. The block preconditioner uses flow and energy sub-preconditioners with optional off-diagonal terms.

2. **Operator-splitting (diagonal MPC)**: Flow and energy PKs are advanced sequentially within each timestep. Less accurate but sometimes more robust for strong nonlinearities.

The `friend class MPCCoupledFlowEnergy` declaration in `TwoPhase` (src/pks/energy/energy_two_phase.hh:58) and `friend class MPCCoupledFlowEnergy` in `Permafrost` (src/pks/flow/permafrost.hh:53) give the MPC direct access to operators for building the block system.

### Key numerical parameters for permafrost runs

| Parameter | PK | Default | Guidance |
|---|---|---|---|
| `"absolute error tolerance"` | Permafrost (flow) | 2750.0 mol | ~0.5 * phi * s * n_l per cell |
| `"absolute error tolerance"` | ThreePhase (energy) | 76e-6 MJ | ~1 degree C of water per molar tolerance |
| `"max valid change in ice saturation in a timestep"` | Permafrost | -1 (off) | Set to 0.1 for temporally resolved freeze fronts |
| `"modify predictor for freezing"` | ThreePhase | false | Enable when phase front advances rapidly |
| `"limit correction to temperature change [K]"` | ThreePhase | -1 (off) | Set to ~1-5 K for difficult phase-change problems |
| `"permeability rescaling"` | Permafrost | 1e7 | Standard; adjust for very low/high permeability |

(Sources: `src/pks/flow/richards.hh:44-130`, `src/pks/energy/energy_base.hh:35-103`)

### Admissibility and timestep control

The BDF time-stepper interacts with both PKs through:

- `IsAdmissible()` — ThreePhase rejects iterates with T outside [200 K, 330 K]
- `IsValid()` — Permafrost rejects timesteps with saturation change > threshold
- `ModifyPredictor()` — ThreePhase clips BDF extrapolations that jump across 273.15 K
- `ModifyCorrection()` — both PKs can clip Newton updates

These safeguards are especially important near the active layer base in Arctic applications, where freeze-thaw transitions occur over thin soil layers in short time periods.

## Practical notes for ECRP (ELM-ATS coupling)

1. The permafrost system is the subset of ATS most directly relevant to the proposed ELM-ATS hierarchical coupling (topic 07). ELM provides boundary conditions (air temperature, precipitation, radiation) that drive the ATS surface energy balance; ATS resolves the fine-scale permafrost thermal-hydrology that ELM cannot.

2. The evaluator DAG architecture means that AI/ML emulators can be inserted as drop-in replacements for expensive evaluators (e.g., replacing the WRM permafrost model with a neural network, or emulating the full Permafrost PK's flux output from ELM state). This is a key enabler for the AI-enhanced coupling described in the ECRP.

3. The three-phase energy conserved quantity (`E`) is the correct quantity to match across the ELM-ATS interface boundary for energy conservation. The advective enthalpy term (`div q e`) represents the dominant energy transport mechanism in unfrozen soil but becomes negligible when soil is frozen (ice blocks Darcy flow). This phase-dependent behavior is captured automatically by the coupled system.

4. Ground stability metrics for ECRP infrastructure risk assessment can be derived directly from ATS output fields: `domain-saturation_ice` (ice content), `domain-saturation_liquid` (liquid content), and the active layer thickness (depth at which `domain-temperature` crosses 273.15 K). These are standard ATS output fields.
