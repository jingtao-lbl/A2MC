---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Chemistry PK Helpers

## Purpose

`chem_pk_helpers` provides two utility functions that convert the primary variable of the transport PK (mole fraction) to/from the primary variable of the chemistry PK (molar concentration). These conversions are necessary at every operator-split step in reactive transport simulations.

**File:** `src/pks/chem_pk_helpers.hh` and `src/pks/chem_pk_helpers.cc`

---

## The unit mismatch problem

The ATS transport PK (`Transport_ATS`) tracks solute concentration as **mole fraction** (mol-C mol-H₂O⁻¹, dimensionless), stored in the field `molar_fraction`. Amanzi's chemistry PK (via the Alquimia interface to PFLOTRAN, CrunchFlow, etc.) expects **total component concentration** (mol-C L⁻¹ = mol-C dm⁻³), stored in the field `total_component_concentration`.

These two units differ by a factor of the molar density of liquid water [mol-H₂O m⁻³ = mol-H₂O L⁻¹ × 10³]. The conversion is:

```
concentration [mol-C L⁻¹] = mole_fraction [mol-C mol-H₂O⁻¹]
                             × molar_density [mol-H₂O m⁻³] × 10⁻³
```

The 10⁻³ factor converts from mol m⁻³ to mol L⁻¹.

---

## Functions

### `convertConcentrationToMolFrac`

(src/pks/chem_pk_helpers.cc:22-42)

```cpp
void convertConcentrationToMolFrac(State& S,
                                   const KeyTag& tcc,
                                   const KeyTag& mol_frac,
                                   const KeyTag& mol_dens,
                                   const std::string& passwd);
```

Converts `total_component_concentration` (TCC, [mol-C L⁻¹]) → `molar_fraction` ([mol-C mol-H₂O⁻¹]).

Implementation (src/pks/chem_pk_helpers.cc:38-41):
```cpp
// mol_frac [mol-C mol-H2O^-1] = tcc [mol-C L^-1] / (mol_dens [mol-H2O m^-3] × 10^-3)
// Note: ReciprocalMultiply(alpha, A, B, beta) computes alpha * A^{-1} * B + beta
mol_frac_c.ReciprocalMultiply(1.e3, mol_dens_c, tcc_c, 0.);
```

The molar density evaluator is updated from the DAG before the conversion. After conversion, `changedEvaluatorPrimary` marks the mole-fraction field as changed in the DAG.

**Called by:** `MPCReactiveTransport::AdvanceStep` (after the chemistry step, before transport), and `MPCCoupledReactiveTransport::AdvanceStep` for the integrated case.

### `convertMolFracToConcentration`

(src/pks/chem_pk_helpers.cc:45-63)

```cpp
void convertMolFracToConcentration(State& S,
                                   const KeyTag& mol_frac,
                                   const KeyTag& tcc,
                                   const KeyTag& mol_dens,
                                   const std::string& passwd);
```

Converts `molar_fraction` ([mol-C mol-H₂O⁻¹]) → `total_component_concentration` ([mol-C L⁻¹]).

Implementation (src/pks/chem_pk_helpers.cc:59-61):
```cpp
// tcc [mol-C L^-1] = mol_frac [mol-C mol-H2O^-1] × mol_dens [mol-H2O m^-3] × 10^-3
tcc_c.Multiply(1.e-3, mol_dens_c, mol_frac_c, 0.);
```

**Called by:** `MPCReactiveTransport::AdvanceStep` (after the transport step, before chemistry).

---

## Operator-split sequence in `MPCReactiveTransport`

Within a single `AdvanceStep(t_old, t_new)` of `MPCReactiveTransport`:

```
1. transport_pk_->AdvanceStep(t_old, t_new)
   → advances molar_fraction field

2. convertMolFracToConcentration(...)
   → molar_fraction → total_component_concentration

3. chemistry_pk_->AdvanceStep(t_old, t_new)
   → advances total_component_concentration via Alquimia

4. convertConcentrationToMolFrac(...)
   → total_component_concentration → molar_fraction
   (ready for next transport step)
```

For the integrated surface-subsurface case (`MPCCoupledReactiveTransport`), the same sequence applies but with separate fields for surface and subsurface domains: `tcc_key_`, `tcc_surf_key_`, `mol_frac_key_`, `mol_frac_surf_key_` (src/pks/mpc/mpc_coupled_reactivetransport.hh:76-80).

---

## Alquimia integration

`MPCReactiveTransport` uses an `#ifdef ALQUIMIA_ENABLED` guard (src/pks/mpc/mpc_reactivetransport.hh:73-78) to select between:
- `AmanziChemistry::Alquimia_PK` (PFLOTRAN or CrunchFlow via the Alquimia interface) when Alquimia is compiled in
- `AmanziChemistry::Chemistry_PK` (Amanzi's native simplified chemistry) otherwise

The helper functions in `chem_pk_helpers.cc` are used in both cases, since the unit mismatch is inherent to the transport-chemistry operator split regardless of which chemistry engine is used.

---

## Scope note

These two functions are the complete contents of `chem_pk_helpers.{hh,cc}`. There is no deeper chemistry integration in ATS beyond this unit-conversion bridge; the chemistry physics itself lives entirely in Amanzi's chemistry PKs (accessed through the Alquimia interface). ATS contributes the MPC layer that orchestrates the operator split and the field management.
