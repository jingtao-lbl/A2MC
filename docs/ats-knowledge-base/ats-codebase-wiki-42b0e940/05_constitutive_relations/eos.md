---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Equations of State (EOS)

**Source tree:** `src/constitutive_relations/eos/`

## 1. Architecture

### Abstract base class

`EOS` (`eos/eos.hh:24`) declares the pure-virtual interface:

```cpp
virtual double MassDensity(std::vector<double>& params) = 0;
virtual double MolarDensity(std::vector<double>& params) = 0;
virtual bool IsTemperature() = 0;
virtual bool IsPressure() = 0;
virtual bool IsMoleFraction() = 0;
```

The `params` vector is ordered by the flags: `[mole_fraction?, temperature?, pressure?]`.
Derivatives (`DMassDensityDT`, `DMassDensityDp`, etc.) default to 0 and are overridden by
derived classes that have non-trivial dependence.

`EOSConstantMolarMass` (`eos/eos_constant_molar_mass.hh`) provides a mixin that implements
`MolarDensity = MassDensity / M` for phases with fixed molar mass.

### Evaluator wrapper

`EOSEvaluator` (`eos/eos_evaluator.hh:45`, `eos/eos_evaluator.cc`) wraps any `EOS` object as an
Amanzi secondary evaluator.  It queries `IsTemperature()`, `IsPressure()`, `IsMoleFraction()` to
build its dependency set, then calls the model pointwise on each mesh entity
(`eos_evaluator.cc:188-193`).

The evaluator can produce molar density, mass density, or both, controlled by
`"EOS basis"` = `"molar"` | `"mass"` | `"both"` (`eos_evaluator.cc:26-34`).

Factory key: `"EOS type"` selects the registered subclass.

---

## 2. Liquid Water -- `EOSWater`

**File:** `eos/eos_water.hh`, `eos/eos_water.cc`
**Factory key:** `"liquid water"`

Empirical cubic polynomial in temperature plus linear pressure correction:

```
dT = T - T0       (T0 = 273.15 K)
rho_1bar = ka + (kb + (kc + kd*dT)*dT)*dT
rho(T,p) = rho_1bar * (1 + alpha*(p - p0))
```

Hard-coded constants (`eos_water.cc:18-24`):

| Symbol | Value | Units |
|---|---|---|
| `ka` | 999.915 | kg m^-3 |
| `kb` | 0.0416516 | kg m^-3 K^-1 |
| `kc` | -0.0100836 | kg m^-3 K^-2 |
| `kd` | 0.000206355 | kg m^-3 K^-3 |
| `T0` | 273.15 | K |
| `alpha` | 5.0e-10 | Pa^-1 |
| `p0` | 1.0e5 | Pa |

Minimum pressure clamp: `p_eff = max(p, 101325)` (`eos_water.cc:38, 48`), so density is never
evaluated below atmospheric for numerical stability.

**Parameters (input deck):**
- `"molar mass [kg mol^-1]"` default 0.0180153, or equivalently `"molar mass [g mol^-1]"` = 18.0153

---

## 3. Ice -- `EOSIce`

**File:** `eos/eos_ice.hh`, `eos/eos_ice.cc`
**Factory key:** `"ice"`

Same quadratic-in-temperature form as water but with ice constants (`eos_ice.cc:22-31`):

```
rho_1bar = ka + (kb + kc*dT)*dT
rho(T,p) = rho_1bar * (1 + alpha*(p - p0))
```

| Symbol | Value | Units |
|---|---|---|
| `ka` | 916.724 | kg m^-3 |
| `kb` | -0.147143 | kg m^-3 K^-1 |
| `kc` | -0.000238095 | kg m^-3 K^-2 |
| `alpha` | 1.0e-10 | Pa^-1 (10x less compressible than water) |

Note the negative `kb` and `kc`: ice density decreases with temperature, consistent with
anomalous expansion on heating toward 0 degC.

**Permafrost relevance:** `EOSIce` is the phase density for ice saturation.  It is evaluated
alongside `EOSWater` whenever the energy PK is active and ice is present.

---

## 4. Ideal Gas (Air / Gas Phase) -- `EOSIdealGas`

**File:** `eos/eos_ideal_gas.hh`, `eos/eos_ideal_gas.cc`
**Factory key:** `"ideal gas"`

Implements ideal gas law for molar density only (mass density via molar mass):

```
n(T,p) = p / (R * T)
```

Parameters (`eos_ideal_gas.cc:57-63`):
- `"ideal gas constant [J mol^-1 K^-1]"` default 8.3144621
- `"molar mass of gas [g mol^-1]"` default 28.956 (dry air)

Like all EOS classes, minimum pressure clamp `p_eff = max(p, 101325)` is applied.

---

## 5. Vapor-in-Gas -- `EOSVaporInGas`

**File:** `eos/eos_vapor_in_gas.hh`, `eos/eos_vapor_in_gas.cc`
**Factory key:** `"vapor in gas"`

A thin wrapper around another EOS (typically `EOSIdealGas`) that disables mass density
functions (they are undefined for a mixture with variable mole fraction).  Provides only molar
density and its derivatives (`eos_vapor_in_gas.cc:23-34`).  Used when the gas phase includes
water vapor.

Configured via `"gas EOS parameters"` sublist which specifies the wrapped EOS type.

---

## 6. Salt Water -- `EOS_SW`

**File:** `eos/eos_sw.hh`, `eos/eos_sw.cc`
**Factory key:** `"salt water"`

Linear model in mole fraction C (salinity concentration, dimensionless) only (no T, no p
dependence, `IsTemperature()` and `IsPressure()` both return false):

```
rho(C) = rho_f + E * C
```

where `rho_f` = fresh water mass density (default 1000 kg/m^3) and `E` = 750 kg/m^3
(default, `eos_sw.cc:64`).  Molar density also accounts for variable molar mass of the
mixture.  Author: Daniil Svyatsky.

---

## 7. Linear (Pressure) -- `EOSLinear`

**File:** `eos/eos_linear.hh`
**Factory key:** `"linear"`

Density linear in pressure only (no temperature dependence):

```
rho(p) = rho0 * (1 + beta * max(p - p_atm, 0))
n(p)   = rho(p) / M
```

Parameters: `"density [kg m^-3]"`, `"compressibility [Pa^-1]"`.  Useful as a simple
compressibility model for deep subsurface or benchmark tests where the full empirical form is
not needed.

---

## 8. Constant Density -- `EOSConstant`

**File:** `eos/eos_constant.hh`, `eos/eos_constant.cc`
**Factory key:** `"constant"`

Returns user-specified fixed density; all derivatives are zero.  Used in isothermal benchmarks
or when density variation is deliberately suppressed.

---

## 9. Viscosity

Viscosity is factored out of the EOS hierarchy into a separate `ViscosityRelation` interface
(`eos/viscosity_relation.hh`) with analogous factory (`ViscosityRelationFactory`).

### `ViscosityWater`

**File:** `eos/viscosity_water.hh`, `eos/viscosity_water.cc`
**Factory key:** `"liquid water"`

Two-branch empirical formula (Poiseuille/Bingham form) (`viscosity_water.cc:27-44`):

- For `T < T1 = 293.15 K`:  `log10(mu/0.001) = 1301 * (1/A - 1/kav1)` where
  `A = kav1 + (kbv1 + kcv1*dT)*dT`, `dT = T1 - T`
- For `T >= T1`:  `log10(mu/0.001) = (kbv2 + kcv2*dT)*dT / (T - 168.15)`

Constants: `kav1=998.333, kbv1=-8.1855, kcv1=0.00585, kbv2=1.3272, kcv2=-0.001053`.
Output in Pa·s.

`ViscosityConstant` (`eos/viscosity_constant.hh`) returns a fixed value for benchmarks.

The `ViscosityEvaluator` (`eos/viscosity_evaluator.hh`) wraps a `ViscosityRelation` as a
secondary evaluator, keyed to `"temperature"` dependency.

---

## 10. Vapor Pressure -- `VaporPressureWater`

**File:** `eos/vapor_pressure_water.hh`, `eos/vapor_pressure_water.cc`
**Factory key:** `"water vapor over water/ice"`

Sonntag (1990) formula for saturation vapor pressure (`vapor_pressure_water.cc:34-40`):

```
p_sat(T) = 100 * exp(ka0 + ka/T + (kb + kc*T)*T + kd*ln(T))
```

Constants: `ka0=16.635764, ka=-6096.9385, kb=-2.7111933e-2, kc=1.673952e-5, kd=2.433502`.

Valid range 100 K < T < 373 K; throws `CutTimestep` outside this range.

The `MolarFractionGasEvaluator` (`eos/molar_fraction_gas_evaluator.hh`) uses this to compute
mole fraction of water vapor in the gas phase from temperature and total pressure.

---

## 11. Carbon Decomposition Rate -- `CarbonDecomposeRateEvaluator`

**File:** `eos/carbon_decomposition_rate_evaluator.hh`, `carbon_decomposition_rate_evaluator.cc`

An evaluator in the `eos/` directory that computes column-integrated soil respiration rate as a
function of temperature, pressure, saturation, and porosity.  Uses Q10-style temperature
sensitivity (`q10_` parameter).  Depends on subsurface temperature, pressure, saturation,
porosity, and depth.  Not a classical EOS but placed here for historical reasons.

---

## Summary Table

| Class | Factory Key | Deps | Notes |
|---|---|---|---|
| `EOSWater` | `"liquid water"` | T, p | cubic polynomial |
| `EOSIce` | `"ice"` | T, p | quadratic; permafrost |
| `EOSIdealGas` | `"ideal gas"` | T, p | n = p/(RT) |
| `EOSVaporInGas` | `"vapor in gas"` | via sub-EOS | molar only |
| `EOS_SW` | `"salt water"` | C (mole frac) | linear in salinity |
| `EOSLinear` | `"linear"` | p | compressibility |
| `EOSConstant` | `"constant"` | none | fixed value |
| `ViscosityWater` | `"liquid water"` | T | Poiseuille/Bingham |
| `VaporPressureWater` | `"water vapor over water/ice"` | T | Sonntag 1990 |
