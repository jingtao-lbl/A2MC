---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Biogeochemistry

Source directory: `src/pks/biogeochemistry/`

Three BGC implementations exist: `bgc_simple/` (the primary production-grade PK),
`carbon/simple/` (a leaner ODE solver for multi-pool carbon), and `fates/` (an
experimental FATES-Fortran interface).

---

## 1. `BGCSimple` — Century-style soil carbon + multi-PFT canopy

**PK type string:** `"BGC simple"`

**Files:** `src/pks/biogeochemistry/bgc_simple/bgc_simple.{hh,cc}`

### What it does

`BGCSimple` is an **explicit (forward Euler) PK** that advances one time step per call
to `AdvanceStep`.  It operates simultaneously on the subsurface mesh (soil carbon) and
the surface mesh (vegetation), requiring that the subsurface mesh has `build_columns`
activated.

**Above-ground model (vegetation).**  A multi-leaf-layer, big-leaf model with multiple
**Plant Functional Types (PFTs)** sorted by height so that shorter PFTs receive only the
radiation not captured by taller ones.  Each column can host several PFTs.  PFT state
(leaf, root, stem, and storage biomass, LAI, GPP, NPP, transpiration, etc.) is held in
`std::vector<std::vector<Teuchos::RCP<PFT>>> pfts_` and `pfts_old_`, outside of Amanzi's
`State` object.  On each failed step these are reset from `pfts_old_` before reattempting
(src/pks/biogeochemistry/bgc_simple/bgc_simple.cc:358-369).  The code comment notes this
as "hackery" that should eventually be refactored into State.

**Below-ground model (soil carbon).**  A Century-style 7-pool decomposition scheme
(default: `"number of carbon pools" = 7`).  The number of pools can be read from the
input list but the comment notes it is unclear whether changing it actually works
(src/pks/biogeochemistry/bgc_simple/bgc_simple.hh:38).  Soil carbon pool state lives in
`std::vector<std::vector<Teuchos::RCP<SoilCarbon>>> soil_carbon_pools_` and IS also stored
in the ATS primary variable field `key_` on the subsurface mesh (component `"cell"`,
`num_pools_` DOFs per cell).

**Cryoturbation.**  Carbon is diffused down the soil column via a cryoturbation
coefficient (`"cryoturbation mixing coefficient [cm^2/yr]"`, default 5.0 cm²/yr).  The
`Cryoturbate()` free function in `bgc_simple_funcs.cc` performs this vertical diffusion
(src/pks/biogeochemistry/bgc_simple/bgc_simple_funcs.hh:47-59).

### Key inputs consumed

| Key | Unit | Source |
|---|---|---|
| `temperature` | K | subsurface energy PK |
| `pressure` | Pa | flow PK (mafic potential) |
| `surface-cell_volume` | m² | mesh |
| `surface-incoming_shortwave_radiation` | W m⁻² | meteorological forcing |
| `surface-air_temperature` | K | meteorological forcing |
| `surface-vapor_pressure_air` | Pa | meteorological forcing |
| `surface-wind_speed` | m s⁻¹ | meteorological forcing |
| `surface-co2_concentration` | ppm | meteorological forcing |

### Key outputs produced

| Key | Unit | Use |
|---|---|---|
| `DOMAIN-transpiration` | mol s⁻¹ | consumed by flow PK as subsurface water sink |
| `SURFACE_DOMAIN-shaded_shortwave_radiation` | W m⁻² | soil evaporation driver in SEB |
| `SURFACE_DOMAIN-total_leaf_area_index` | — | surface energy balance |
| `co2_decomposition` | (diagnostic) | carbon diagnostic |
| `surface-total_biomass`, `surface-leaf_biomass` | kg C m⁻² | diagnostics |

### Core free function: `BGCAdvance`

`BGCAdvance()` in `bgc_simple_funcs.cc` is the single entry point called per column in
`AdvanceStep` (src/pks/biogeochemistry/bgc_simple/bgc_simple.cc:478-491).  It calls
vegetation photosynthesis/respiration, updates soil carbon pools via Century decomposition,
and applies cryoturbation.

### Parameter structures

- **`PFT`** (`src/pks/biogeochemistry/bgc_simple/PFT.hh`): Holds all per-PFT state (leaf,
  root, stem, storage biomass; LAI; GPP; NPP; ET; etc.).  Parameters set from input via
  `Init(plist, col_area)`.  Key photosynthetic parameters include `Vcmax25` (maximum
  carboxylation rate), `Emax25`, `Jmax25`, stomatal conductance slope `mp`, and water
  potential thresholds `swpo`, `swpc`.

- **`SoilCarbon`** (`src/pks/biogeochemistry/bgc_simple/SoilCarbon.hh`): A thin wrapper
  around an `Epetra_SerialDenseVector SOM` of pool concentrations, linked to a
  `SoilCarbonParameters` object that stores pool turnover rates and transfer coefficients.

- **`SoilCarbonParameters`** (`bgc_simple/SoilCarbonParameters.hh`): Per-region parameters
  for the Century soil carbon model, read from `"soil carbon parameters"` sublists keyed
  by mesh partition region name.

### Class hierarchy

```
PK_Physical_Default
  └── BGCSimple   (explicit, not BDF)
```

`BGCSimple` is also a `friend class` of `FATES_PK`, sharing column-access helpers
(src/pks/biogeochemistry/bgc_simple/bgc_simple.hh:131).

### Registration

`src/pks/biogeochemistry/bgc_simple/bgc_simple_reg.hh` — registers `"BGC simple"`.

---

## 2. `CarbonSimple` — explicit multi-pool ODE solver

**PK type string:** `"simple Carbon"`

**Files:** `src/pks/biogeochemistry/carbon/simple/CarbonSimple.{hh,cc}`

### What it does

`CarbonSimple` is an **explicit-time-stepping PK** (`PK_Physical_Default_Explicit_Default`)
that solves

```
d(carbon) / dt = source  -  decomposition  +  div(bioturbation_flux)
```

for a multi-pool carbon field on the subsurface mesh.  Unlike `BGCSimple`, it does not
carry its own vegetation model; it expects external `source_key_` and `decomp_key_`
evaluators.  Bioturbation diffusion is also optional, controlled by `"is cryoturbation"`.

Key optional evaluator dependencies (src/pks/biogeochemistry/carbon/simple/CarbonSimple.cc:26-38):
- `div_diff_flux_key_` — divergence of bioturbation fluxes
- `source_key_` — carbon source (e.g. litterfall)
- `decomp_key_` — decomposition rate

`CarbonSimple` is likely intended for use in the `bgc/carbon/` evaluation pipeline but
does not appear to be heavily exercised in current regression tests.

### Registration

`src/pks/biogeochemistry/carbon/simple/CarbonSimple_reg.hh` — registers `"simple Carbon"`.

---

## 3. BGC evaluators (`constitutive_models/carbon/`)

These secondary evaluators compute rates used by `CarbonSimple` (and potentially other
BGC PKs).

| Evaluator file | What it computes |
|---|---|
| `pool_decomposition_evaluator.{cc,hh}` | Carbon pool turnover: first-order decay applied to each pool, product of pool C and a decay rate key (`decay_key_`). Depends on `carbon_key_` and `decay_key_`. |
| `pool_transfer_evaluator.{cc,hh}` | Inter-pool transfer fluxes. |
| `bioturbation_evaluator.{cc,hh}` | Bioturbation (cryoturbation) diffusion coefficient field for use in a div-grad operator. |

`PoolDecompositionEvaluator` is a `EvaluatorSecondaryMonotypeCV` subclass
(src/pks/biogeochemistry/constitutive_models/carbon/pool_decomposition_evaluator.hh:25).

---

## 4. `FATES_PK` — experimental FATES interface

**PK type string:** `"FATES"` (registered via `fates_reg.hh`)

**Files:** `src/pks/biogeochemistry/fates/fates_pk.{hh,cc}`

### Status: experimental / partially functional

The FATES PK wraps the **FATES (Functionally Assembled Terrestrial Ecosystem Simulator)**
Fortran library via ISO C Fortran binding (`ISO_Fortran_binding.h`).

The C interface is declared as `extern "C"` in `fates_pk.hh:54-87`:
- `init_ats_fates`, `init_soil_depths`, `init_coldstart` — initialization
- `fatessetmasterproc`, `fatessetinputfiles`, `fatesreadparameters`, `fatesreadpfts` — parameter loading
- `set_fates_global_elements`, `get_nlevsclass` — dimensioning
- `dynamics_driv_per_site` — vegetation dynamics per column per day
- `wrap_btran`, `wrap_photosynthesis`, `wrap_sunfrac`, `wrap_canopy_radiation` — photosynthesis wrappers
- `calculate_biomass` — biomass output

**Two time scales are maintained** (src/pks/biogeochemistry/fates/fates_pk.hh:131-132):
- `dt_photosynthesis_` (default 1800 s = 30 min)
- `dt_site_dym_` (default 86400 s = 1 day)

`AdvanceStep` only runs photosynthesis when `t_new == t_photosynthesis_ + dt_photosynthesis_`
and vegetation dynamics when `t_new == t_site_dym_ + dt_site_dym_`
(src/pks/biogeochemistry/fates/fates_pk.cc:404-406).

**Known issues visible in source:**
- Debug `std::cout` statements left in `AdvanceStep` (fates_pk.cc:462-477), indicating this
  code is still in development.
- Decomposition pool output fields (`met_decomp_key_`, `cel_decomp_key_`, `lig_decomp_key_`)
  are entirely commented out in both `Setup` and `Initialize` (fates_pk.cc:133-147).
- The old-style `S->HasField` / `S->RequireField` API is mixed with the newer
  `S->Require<CompositeVector,...>` API (fates_pk.cc:151-238), suggesting incomplete porting.

**Conclusion:** FATES integration exists structurally but is not production-ready at this
commit.  It requires the FATES Fortran library to be compiled in and linked, controlled by
a CMake flag.  The CMakeLists for `fates/` (`src/pks/biogeochemistry/fates/CMakeLists.txt`)
gates the build.

---

## Note: Alquimia (reactive geochemistry)

**Alquimia is NOT implemented in the BGC PKs.**  Reactive transport in ATS uses the
`Transport_ATS` PK with an `#ifdef ALQUIMIA_ENABLED` code path (see `transport.md`).
The BGC PKs (`bgc_simple`, `CarbonSimple`) implement their own internal biogeochemical
cycle and do not call Alquimia.
