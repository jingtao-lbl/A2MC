---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Surface Balance

Source directory: `src/pks/surface_balance/`

The surface balance module computes surface energy balance (SEB), snowpack evolution,
evapotranspiration (ET), precipitation partitioning, and atmospheric forcing.  Its outputs
are water and energy source/sink terms fed into the surface overland flow and energy PKs.
The module has three layers: PKs (the time-stepping drivers), constitutive evaluators in
`constitutive_relations/land_cover/` and `constitutive_relations/litter/`, and a CLM-based
alternative.

---

## 1. `SurfaceBalanceBase` — generic conserved-quantity ODE

**PK type string:** `"general surface balance"`

**Files:** `src/pks/surface_balance/surface_balance_base.{hh,cc}`

### Physics

A general balance equation:

```
∂Φ/∂t = Σᵢ Qᵢ
```

where `Φ` is a conserved quantity and `Qᵢ` are source/sink terms.  Solved with BDF
(backward differentiation formula) via `pk_physical_bdf_default`.  The time integration
theta parameter allows Crank-Nicholson weighting between explicit (θ=0) and implicit (θ=1).
Default θ=1 (fully implicit) (src/pks/surface_balance/surface_balance_base.hh:83).

This is the base class used for water balance of snow, canopy water, and other reservoir
types.  Key parameters (src/pks/surface_balance/surface_balance_base.hh:117-124):
- `is_source_term_` — whether a source key is used
- `is_source_term_differentiable_` — for Jacobian
- `theta_` — Crank-Nicholson weight
- `modify_predictor_positivity_preserving_` — prevent negative conserved quantities

Registration: `src/pks/surface_balance/surface_balance_base_reg.hh`.

---

## 2. `ImplicitSubgrid` — snow water equivalent balance

**PK type string:** `"surface balance implicit subgrid"`

**Files:** `src/pks/surface_balance/surface_balance_implicit_subgrid.{hh,cc}`

### Physics

Solves for conservation of **snow water equivalent (SWE)** on the snow domain.  The
conserved quantity is `snow_water_equivalent` [m SWE].  Source terms include snowfall
(as new snow) and snowmelt (from energy balance).

This PK adds snow-specific state variables (src/pks/surface_balance/surface_balance_implicit_subgrid.hh:97-104):
- `snow_dens_key_` — snow density [kg m⁻³]
- `snow_age_key_` — snow age [d]
- `new_snow_key_` — new snow source [m SWE s⁻¹]
- `snow_source_key_` — total snow source/sink
- `snow_death_rate_key_` — rate at which the last thin layer of snow must be removed
- `area_frac_key_` — subgrid fractional areas (snow-covered vs. bare fraction)

**Subgrid area fractions** are a key feature.  Rather than assuming a cell is uniformly
snow-covered or bare, a snow fractional area model captures the subgrid heterogeneity of
shallow snowpacks, important for tundra and patchy snow conditions
(src/pks/surface_balance/surface_balance_implicit_subgrid.hh:13-15, noting "ATS Issue #8").

The maximum snow density is set by `density_snow_max_`.

`ModifyPredictor` and `ModifyCorrection` apply positivity-preserving bounds on SWE to
prevent numerical oscillations near zero.

Registration: `src/pks/surface_balance/surface_balance_implicit_subgrid_reg.hh`.

---

## 3. `SurfaceBalanceCLM` — CLM-based surface process model

**PK type string:** (registered via `surface_balance_CLM_reg.hh`)

**Files:** `src/pks/surface_balance/CLM/`

### Overview

This PK wraps an **old variant of CLM (Community Land Model)** maintained by the ParFlow
group (src/pks/surface_balance/CLM/surface_balance_CLM.cc:18-26).  It provides:
- Snowpack evolution
- Surface and subsurface water sources
- Latent/sensible heat flux diagnostics
- Soil moisture feedback on evapotranspiration

The CLM Fortran layer is called through `ats_clm_interface.{cc,hh}` and the Fortran
module `ats_clm.F90`.

**Important notes about CLM integration:**
1. This is **water-only** at this commit.  CLM internally solves its own energy balance
   but does not export energy fluxes back into ATS's energy equation — the comment states
   "One could refactor CLM to split out this energy balance as well"
   (src/pks/surface_balance/CLM/surface_balance_CLM.cc:23-25).
2. The primary variable is snow depth.

The PK manages two output water source keys:
- `surf_water_src_key_` — surface water source [m s⁻¹]
- `ss_water_src_key_` — subsurface water source [m s⁻¹]

And several diagnostic energy flux keys:
- `qE_lh_key_` (latent heat), `qE_sh_key_` (sensible heat),
  `qE_lw_out_key_` (outgoing longwave), `qE_cond_key_` (conducted energy)
  (src/pks/surface_balance/CLM/surface_balance_CLM.cc:55-59).

Meteorological inputs follow the same pattern as the SEB evaluators (SW, LW, air temp,
vapor pressure, wind speed, rain, snow).

### ELM-style vs CLM

This CLM integration is NOT the ELM/E3SM land model — it is an older CLM variant.  For
ELM-ATS coupling, see `src/executables/elm_ats_api/` (topic 07).  The surface balance CLM
PK is intended for standalone ATS runs requiring a more complete land surface model than
the ATS-native SEB evaluators, without the full ELM coupling overhead.

---

## 4. SEB evaluators (`constitutive_relations/land_cover/`)

These are the building blocks for the ATS-native surface energy balance.  They are used
by `ImplicitSubgrid` and by the standalone SEB evaluators that produce source terms for
the surface flow and energy PKs.

### SEB physics definitions

`src/pks/surface_balance/constitutive_relations/land_cover/seb_physics_defs.hh`

Defines the core data structures used throughout the SEB:
- `ModelParams` — physical constants (Stefan-Boltzmann, von Karman, snow density, latent
  heats, etc.) plus user-overridable parameters (src/pks/surface_balance/constitutive_relations/land_cover/seb_physics_defs.hh:46-108).
- `GroundProperties` — surface skin state (temp, pressure, ponded depth, albedo, emissivity,
  rsoil, roughness length) (seb_physics_defs.hh:112-140).
- `SnowProperties` — snow state (depth, density, temp, albedo, emissivity, roughness).
- `MetData` — meteorological forcing (wind speed at reference height, shortwave, longwave,
  snow/rain precipitation, air temperature, vapor pressure) (seb_physics_defs.hh:159-173).
- `EnergyBalance` — energy flux components (SW in, LW in/out, sensible, latent, conducted,
  melt, error) (seb_physics_defs.hh:177-191).
- `MassBalance` — condensation/sublimation rate and melt rate.
- `FluxBalance` — final partitioned fluxes to surface, subsurface, and snow domains.
- `Partition` / `Partitioner` — area-weighted mixing for snow + water + ice + tundra
  sub-surface types (seb_physics_defs.hh:239-266).

### SEB evaluators

| Evaluator file | Type string | Description |
|---|---|---|
| `seb_twocomponent_evaluator.{hh,cc}` | `"surface energy balance, two components"` | SEB for a surface with two components: snow-covered and bare/water ground.  Computes water and energy source terms for both surface and subsurface. |
| `seb_threecomponent_evaluator.{hh,cc}` | `"surface energy balance, three components"` | Three-component SEB: snow, ponded water/ice, and vegetated/bare tundra.  Area-weighted fluxes.  Depends on `area_fractions`, subgrid albedos and emissivities. Derivatives disabled (`IsDifferentiableWRT` returns false); numerical finite differencing used instead (src/pks/surface_balance/constitutive_relations/land_cover/seb_threecomponent_evaluator.hh:117-121). |

The three-component evaluator outputs (src/pks/surface_balance/constitutive_relations/land_cover/seb_threecomponent_evaluator.hh:146-162):
- `water_source_key_` — surface water source [m s⁻¹]
- `energy_source_key_` — surface energy source [W m⁻²]
- `ss_water_source_key_` — subsurface water source [mol s⁻¹]
- `ss_energy_source_key_` — subsurface energy source [W m⁻³]
- `snow_source_key_` — snow mass source/sink [m SWE s⁻¹]
- `new_snow_key_` — new snowfall [m SWE s⁻¹]
Plus diagnostic keys: melt, evaporation, snow temperature, heat fluxes, albedo.

### Area fraction evaluators

These compute the subgrid fractional areas used by the SEB evaluators:

| Evaluator | Description |
|---|---|
| `area_fractions_twocomponent_evaluator.{hh,cc}` | Two fractions: snow-covered and bare. |
| `area_fractions_threecomponent_evaluator.{hh,cc}` | Three fractions: snow, water/ice, tundra. |
| `area_fractions_threecomponent_microtopography_evaluator.{hh,cc}` | Three fractions with microtopography-based water fraction (accounts for depression storage). |

### Albedo and radiation evaluators

| Evaluator | Description |
|---|---|
| `albedo_twocomponent_evaluator.{hh,cc}` | Albedo for two-component surface. |
| `albedo_threecomponent_evaluator.{hh,cc}` | Albedo for three-component surface. |
| `radiation_balance_evaluator.{hh,cc}` | Net radiation from shortwave and longwave. |
| `canopy_radiation_evaluator.{hh,cc}` | Radiation transmitted through and intercepted by canopy. |
| `incident_shortwave_radiation_evaluator.{hh,cc}` + `_model.{hh,cc}` | Downwelling shortwave with slope/aspect correction. |
| `longwave_evaluator.{hh,cc}` | Downwelling longwave from air temperature and humidity. |

### Snow evaluators

| Evaluator | Description |
|---|---|
| `snow_meltrate_evaluator.{hh,cc}` | Snow melt rate from energy available for melt. |

### ET evaluators

| Evaluator | Description |
|---|---|
| `pet_priestley_taylor_evaluator.{hh,cc}` | Potential ET using **Priestley-Taylor** formulation, based on PRMS-IV (Equations 1-57 to 1-60).  Computes ground heat flux, slope of saturation vapor pressure, psychrometric constant, and latent heat of vaporization as intermediate steps. Optional limiter multiplication (src/pks/surface_balance/constitutive_relations/land_cover/pet_priestley_taylor_evaluator.hh:63-95). |
| `evaporation_downregulation_evaluator.{hh,cc}` | Downregulates potential evaporation when soil is dry. |
| `transpiration_distribution_evaluator.{hh,cc}` | Distributes potential transpiration vertically along roots using root fraction and plant wilting factor.  Based on CLM 4.5 and PRMS.  Integrates `(rooting_fraction * wilting_factor)` per column to compute normalized weights, then multiplies by potential ET.  Seasonal phenology controlled by `"leaf on doy"` / `"leaf off doy"` LandCover parameters (src/pks/surface_balance/constitutive_relations/land_cover/transpiration_distribution_evaluator.hh:19-51). Requires columnar mesh. |
| `transpiration_distribution_relperm_evaluator.{hh,cc}` | Alternative transpiration distribution based on relative permeability rather than wilting factor. |
| `plant_wilting_factor_evaluator.{hh,cc}` + `_model.{hh,cc}` | Plant wilting factor as a function of soil matric potential; drops to zero at the permanent wilting point. |
| `rooting_depth_fraction_evaluator.{hh,cc}` | Root distribution profile as a function of depth (exponential or other parameterization). |

### Land cover and interception evaluators

| Evaluator | Description |
|---|---|
| `LandCover.{cc,hh}` + `land_cover_evaluator_reg.hh` | `LandCover` struct holding PFT-like parameters (roughness lengths, leaf-on/off DOY, rooting parameters, etc.) per land cover region.  Used as a parameter map (`LandCoverMap`) throughout SEB and ET evaluators. |
| `interception_fraction_evaluator.{hh,cc}` + `_model.{hh,cc}` | Canopy interception fraction as a function of LAI. |
| `drainage_evaluator.{hh,cc}` | Drainage of intercepted water from canopy. |

### Litter evaluators (`constitutive_relations/litter/`)

| Evaluator | Description |
|---|---|
| `evaporative_flux_relaxation_evaluator.{hh,cc}` + `_model.{hh,cc}` | Evaporation from litter layer using a relaxation timescale. |
| `micropore_macropore_flux_evaluator.{hh,cc}` + `_model.{hh,cc}` | Water flux exchange between litter micropores and macropores. |

---

## 5. Comparison with ELM surface energy balance

The ATS-native SEB evaluators share architectural intent with ELM's surface energy balance
but are implemented independently.  Key comparisons:

| Feature | ATS SEB | ELM |
|---|---|---|
| Snow physics | Single-layer implicit subgrid SWE balance | Multi-layer snowpack |
| ET | Priestley-Taylor PET + rooting distribution | Ball-Berry stomatal conductance |
| Albedo | Empirical per-surface-type constants in `SurfaceParams` | MEGAN/MOSSES parameterizations |
| Area fractions | Subgrid snow/water/tundra fractions | Tile-based fractional land cover |
| Canopy | Empirical interception + BGCSimple transpiration | Full CLM multi-layer canopy |

When ATS is coupled to ELM (via `src/executables/elm_ats_api/`), ELM provides the
surface energy balance and the ATS SEB PKs are typically not active.  The ATS SEB is
used for standalone ATS runs.

---

## Python analysis scripts

Several Python files exist in `constitutive_relations/land_cover/` as offline analysis
tools (not compiled):
- `area_fractions_subgrid_evaluator.py` — analysis script
- `evaporation.py` — evaporation model exploration
- `incident_shortwave_radiation.py` — radiation geometry analysis
- `plant_wilting_factor.py` — wilting factor curve exploration
- `rooting_depth_fraction.py` — root distribution visualization
- `transpiration_distribution.py` — transpiration distribution analysis

These are documentation/analysis aids, not part of the compiled ATS library.
