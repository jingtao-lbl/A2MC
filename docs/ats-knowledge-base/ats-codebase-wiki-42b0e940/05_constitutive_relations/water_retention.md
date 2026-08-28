---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Water Retention Models (WRM)

**Source tree:** `src/pks/flow/constitutive_relations/wrm/`

> **ECRP critical:** These closures control how liquid, ice, and gas saturations partition in
> partially frozen soil.  The permafrost WRM models are the central closure that couples the
> thermal and hydrologic state, and their numerical behavior determines convergence of the
> fully coupled flow-energy solve.

---

## 1. Base Interface

### `WRM`

**File:** `wrm/wrm.hh:44`

Pure-virtual interface for two-phase (water-gas) retention:

```cpp
virtual double k_relative(double saturation) = 0;
virtual double d_k_relative(double saturation) = 0;
virtual double saturation(double pc) = 0;       // S = S(pc)
virtual double d_saturation(double pc) = 0;     // dS/dpc
virtual double capillaryPressure(double saturation) = 0;  // pc(S)
virtual double d_capillaryPressure(double saturation) = 0;
virtual double residualSaturation() = 0;
virtual double suction_head(double saturation) { return 0.; }  // optional
```

Two relative-permeability functions are available: Mualem (`FLOW_WRM_MUALEM = 1`) and Burdine
(`FLOW_WRM_BURDINE = 2`) (`wrm.hh:38-39`).

### `WRMPermafrostModel`

**File:** `wrm/wrm_permafrost_model.hh:24`

Pure-virtual interface for three-phase (gas, liquid, ice) partitioning.  Each concrete model
receives capillary pressures and outputs phase saturations and their derivatives:

```cpp
// sats[0]=s_gas, sats[1]=s_liq, sats[2]=s_ice
virtual void saturations(double pc_liq, double pc_ice, double (&sats)[3]) = 0;
virtual void dsaturations_dpc_liq(double pc_liq, double pc_ice, double (&dsats)[3]) = 0;
virtual void dsaturations_dpc_ice(double pc_liq, double pc_ice, double (&dsats)[3]) = 0;
```

Each model holds a pointer to a `WRM` object (`wrm_permafrost_model.hh:42`) that provides the
unfrozen saturation curve.

### Capillary Pressure Helpers

Two helper structs convert between model-space and raw fields:

- **`PCLiqAtm`** (`wrm/pc_liq_atm.hh:24`) -- gas-liquid capillary pressure:
  `pc_gl = p_atm - p_liquid`

- **`PCIceWater`** (`wrm/pc_ice_water.hh:47`) -- liquid-ice capillary pressure from the
  Clausius-Clapeyron equation:
  `pc_il(T) = gamma * rho * (T0 - T) / T0`  for T < T0, else 0
  where `gamma = (sigma_gl / sigma_il) * L_f`
  (`pc_ice_water.cc:28-49`).

  Key parameters:
  - `"reference temperature [K]"` T0, default 273.15
  - `"interfacial tension ice-water [mN m^-1]"` sigma_il, default 33.1
  - `"interfacial tension air-water [mN m^-1]"` sigma_gl, default 72.7
  - `"latent heat [J kg^-1]"` L_f, default 3.34e5
  - `"smoothing width [K]"` -- replaces the sharp step with a piecewise-quadratic
    (`pc_ice_water.cc:31-48`); optional but helps convergence.

---

## 2. Two-Phase WRM Implementations

### 2a. van Genuchten -- `WRMVanGenuchten`

**File:** `wrm/wrm_van_genuchten.hh:65`, `wrm_van_genuchten.cc`
**Factory key:** `"van Genuchten"`

The standard van Genuchten (1980) / Mualem model:

**Saturation curve** (`wrm_van_genuchten.cc:89-98`):
```
S(pc) = (1 + (alpha*pc)^n)^{-m} * (1 - sr) + sr      for pc > pc0
S(pc) = 1.0                                            for pc <= 0
```
(cubic spline smoothing near pc=0 if `"saturation smoothing interval [Pa]"` > 0)

**Mualem relative permeability** (`wrm_van_genuchten.cc:39-53`):
```
Se = (S - sr) / (1 - sr)
kr_Mualem(S) = Se^l * (1 - (1 - Se^{1/m})^m)^2
kr_Burdine(S) = Se^2 * (1 - (1 - Se^{1/m})^m)
```

**Capillary pressure inverse** (`wrm_van_genuchten.cc:121-131`):
```
pc(S) = (Se^{-1/m} - 1)^{1/n} / alpha
```

**Parameters:**
| Name | Description |
|---|---|
| `"van Genuchten alpha [Pa^-1]"` | inverse entry pressure |
| `"van Genuchten n [-]"` or `"van Genuchten m [-]"` | shape (m = 1-1/n for Mualem) |
| `"residual saturation [-]"` | sr, default 0.0 |
| `"Mualem exponent l [-]"` | l, default 0.5 |
| `"smoothing interval width [saturation]"` | cubic spline near S=1; default 0 |
| `"Krel function name"` | `"Mualem"` (default) or `"Burdine"` |

The Hermite cubic spline regularization near full saturation (`s0 < s <= 1.0`) is critical for
convergence when cells transition between unsaturated and saturated states (`wrm_van_genuchten.cc:40-52`).

**Note on m/n:** the code accepts either m or n and converts internally.  For Mualem: m=1-1/n;
for Burdine: m=1-2/n (`wrm_van_genuchten.cc:206-220`).

### 2b. Brooks-Corey -- `WRMBrooksCorey`

**File:** `wrm/wrm_brooks_corey.hh:57`, `wrm_brooks_corey.cc`
**Factory key:** `"Brooks-Corey"`

Brooks-Corey power-law form, often used under freezing conditions (converts from vG parameters):

**Saturation** (`wrm_brooks_corey.cc:87-93`):
```
S(pc) = 1.0                              for pc <= p_sat
S(pc) = (p_sat/pc)^lambda * (1-sr) + sr for pc > p_sat
```

**Relative permeability** (`wrm_brooks_corey.cc:51-62`):
```
kr(S) = Se^{2b+3}    where b = 1/lambda (Clapp-Hornberger b)
```

**Parameters:**
- `"Brooks-Corey lambda [-]"` -- pore-size distribution index
- `"Brooks-Corey saturated matric suction [Pa]"` -- p_sat, the air-entry pressure
- `"residual saturation [-]"` -- default 0.0

**Freezing context:** Brooks-Corey is particularly appropriate for the ice relative permeability
modifier in freezing soils.  See `rel_perm_brooks_corey_freezing_coeff.hh` and
`rel_perm_frzBC_evaluator.hh` for the specialized freezing Brooks-Corey relative permeability
evaluators.

### 2c. Linear System -- `WRMLinearSystem`

**File:** `wrm/wrm_linear_system.hh`, `wrm_linear_system.cc`
**Factory key:** `"linear system"`

Saturation linear in capillary pressure.  Combined with constant relative permeability, makes the
flow equation linear.  Used for testing and simple benchmark problems where one-step Newton
convergence is desired.

### 2d. Constant -- `WRMConstant`

**File:** `wrm/wrm_constant.hh`
**Factory key:** `"constant"`

Fixed saturation (= 1) and relative permeability (= user-specified).  Used to pin cells to
full saturation or to suppress unsaturated flow entirely.

### 2e. Linear Relative Permeability -- `WRMLinearRelperm`

**File:** `wrm/wrm_linear_relperm.hh`, `wrm_linear_relperm.cc`

kr linear in saturation.  A simplification for sensitivity studies.

### 2f. Macropore -- `WRMMacropore`

**File:** `wrm/wrm_macropore.hh`, `wrm_macropore.cc`

Dual-domain capillary pressure model for macropore flow.  Less common but available for
structured soils with preferential flow paths.

### 2g. Plant Hydraulics -- `WRMPlantsChristoffersen`

**File:** `wrm/wrm_plants_christoffersen.hh`, `wrm_plants_christoffersen.cc`

Christoffersen et al. plant hydraulic water retention curve.  Used by the vegetation /
transpiration PKs when plant stem hydraulics is modeled.

### 2h. Interfrost Benchmark -- `WRMInterfrost`

**File:** `wrm/wrm_interfrost.hh:27`

Specialized WRM for the INTERFROST code comparison exercise (Grenier et al. 2018 AWR).  Only
implements relative permeability as `k_r = 10^(-50 * 0.37 * (1-S))`; saturation and capillary
pressure functions assert 0 (not valid for normal use).

---

## 3. Permafrost Saturation Models

When `temperature < T0 = 273.15 K`, ice can occupy pore space.  The permafrost models partition
total pore space among gas, liquid, and ice, driven by `pc_liq` (gas-liquid) and `pc_ice`
(liquid-ice) capillary pressures.  Five implementations exist.

### 3a. Implicit Permafrost Model (Painter) -- `WRMImplicitPermafrostModel`

**File:** `wrm/wrm_implicit_permafrost_model.hh:39`, `wrm_implicit_permafrost_model.cc`
**Factory key:** `"permafrost model"`

This is the default high-accuracy model, corresponding to Painter & Karra (2014) VZJ.  It
defines ice saturation implicitly by requiring thermodynamic consistency between gas-liquid and
liquid-ice capillary pressures (`wrm_implicit_permafrost_model.cc:93`):

```
tmp   = (1 - si) * S*(pc_liq)
F(si) = tmp - S*( pc_ice + pc_inv(tmp + si) ) = 0
```

where `S*` is the WRM saturation function and `pc_inv` its inverse (capillary pressure from
saturation).  The root is found with a Brent algorithm
(`wrm_implicit_permafrost_model.cc:354-376`; `eps_` default 1e-12, `max_it_` default 100).

A cubic spline bridges the solution from the unsaturated-frozen regime to the saturated regime,
preventing discontinuities in derivatives (`wrm_implicit_permafrost_model.cc:185-204`).

Three cases handled:
1. **Unfrozen** (`pc_ice <= 0`): `si=0`, standard WRM applies (`cc:40-51`)
2. **Saturated** (`pc_liq <= 0`): `sg=0`, WRM applied to pc_ice (`cc:88-99`)
3. **Frozen + unsaturated**: Brent solve for `si` (`cc:347-390`)

**Parameters:**
- `"converged tolerance"` default 1e-12
- `"max iterations"` default 100
- `"solver algorithm"` currently only `"brent"` is supported

### 3b. Freezing Point Depression (FPD) -- `WRMFPDPermafrostModel`

**File:** `wrm/wrm_fpd_permafrost_model.hh:33`, `wrm_fpd_permafrost_model.cc`
**Factory key:** `"fpd permafrost model"`

Painter's explicit (algebraic) approximation; no root-finding required.  Three cases
(`wrm_fpd_permafrost_model.cc:27-46`):

1. `pc_liq <= 0` (saturated): `sg=0, sl=S*(pc_ice), si=1-sl`
2. `pc_ice <= pc_liq` (unfrozen/above freezing): `si=0, sl=S*(pc_liq), sg=1-sl`
3. Partially frozen: `sl=S*(pc_ice), si=1 - sl/S*(pc_liq), sg=1-sl-si`

Faster than the implicit model but less accurate for complex frozen-unsaturated conditions.

### 3c. Smoothed FPD -- `WRMFPDSmoothedPermafrostModel`

**File:** `wrm/wrm_fpd_smoothed_permafrost_model.hh`, `wrm_fpd_smoothed_permafrost_model.cc`
**Factory key:** `"fpd smoothed permafrost model"`

The FPD model with additional Hermite spline smoothing near the phase boundary to improve
Newton convergence for coupled flow-energy systems.

### 3d. McKenzie et al. -- `WRMMCKPermafrostModel`

**File:** `wrm/wrm_mck_permafrost_model.hh:27`, `wrm_mck_permafrost_model.cc`
**Factory key:** `"mck permafrost model"`

Empirical temperature-based freezing curve after McKenzie et al. (2007), using a Gaussian form
(`wrm_mck_permafrost_model.cc:38`):

```
sl = sr + (S*(pc_liq) - sr) * exp(-((T - T0)/w)^2)    for T < T0
sl = S*(pc_liq)                                         for T >= T0
si = S*(pc_liq) - sl
```

Parameters: `"freezing point [K]"` (T0, default 273.15), `"sfc fitting coefficient"` (w, default 3.0).

This model takes temperature directly (pc_ice argument is treated as temperature), bypassing
the Clausius-Clapeyron relation.  Simpler but loses thermodynamic consistency with the
pressure field.

### 3e. SUTRA-Ice -- `WRMSutraPermafrostModel`

**File:** `wrm/wrm_sutra_permafrost_model.hh:36`, `wrm_sutra_permafrost_model.cc`
**Factory key:** `"sutra permafrost model"`

Linear interpolation over a temperature transition interval [T0-dT, T0] (Voss & Walvoord).
Takes temperature as pc_ice argument.  Parameters: `"temperature transition [K]"` (dT),
`"residual saturation [-]"`, `"freezing point [K]"` T0 default 273.15.

### 3f. Old Permafrost Model -- `WRMOldPermafrostModel`

**File:** `wrm/wrm_old_permafrost_model.hh`, `wrm_old_permafrost_model.cc`

Legacy implementation retained for backward compatibility; not recommended for new simulations.

---

## 4. Evaluator Layer

### `WRMEvaluator`

**File:** `wrm/wrm_evaluator.hh`
**Factory key:** `"water retention model"`

Wraps a partition of WRM objects (region-to-WRM pairs) and computes `saturation_liquid`,
`saturation_gas`, and optionally `relative_permeability` from `capillary_pressure_gas_liq`.

### `WRMPermafrostEvaluator`

**File:** `wrm/wrm_permafrost_evaluator.hh:80`
**Factory key:** `"water retention model with ice"`

Wraps both a `WRMPartition` and a `WRMPermafrostModelPartition`.  Outputs:
- `saturation_liquid`
- `saturation_gas`
- `saturation_ice`

Dependencies: `capillary_pressure_gas_liq`, `capillary_pressure_liq_ice`.

### Relative Permeability Evaluators

| Class | File | Description |
|---|---|---|
| `RelPermEvaluator` | `rel_perm_evaluator.hh` | Standard unfrozen relative permeability |
| `RelPermFrzBCEvaluator` | `rel_perm_frzBC_evaluator.hh` | Freezing-modified Brooks-Corey kr |
| `RelPermSutraIceEvaluator` | `rel_perm_sutraice_evaluator.hh` | SUTRA-Ice kr modifier |

### Capillary Pressure Evaluators

| Class | File | Description |
|---|---|---|
| `PCLiquidEvaluator` | `pc_liquid_evaluator.hh` | pc_gl = p_atm - p_liq |
| `PCIceEvaluator` | `pc_ice_evaluator.hh` | pc_il from PCIceWater model |
| `SuctionHeadEvaluator` | `suction_head_evaluator.hh` | Suction head from WRM |

---

## 5. Model Selection Guide (Permafrost)

| Model | Cost | Accuracy | When to use |
|---|---|---|---|
| `implicit` | High (Brent per cell) | Highest | Default for production permafrost runs |
| `fpd smoothed` | Medium | High | Faster alternative; good convergence |
| `fpd` | Low | Moderate | Fast benchmarks; explicit, no solve |
| `mck` | Low | Moderate | Empirical studies; T-only dependence |
| `sutra` | Low | Low-Moderate | Simple linear transition; legacy code |

The `implicit` model is the most thermodynamically consistent because it simultaneously satisfies
both the liquid-gas and liquid-ice equilibrium constraints.  The FPD models are algebraic
approximations that are computationally cheaper but may require finer time stepping.
