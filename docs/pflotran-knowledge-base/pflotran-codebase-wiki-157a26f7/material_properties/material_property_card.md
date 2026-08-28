**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** MATERIAL_PROPERTY input card — porosity, permeability, thermal, dispersivity, electrical
**Last verified:** 2026-07-31

# The `MATERIAL_PROPERTY` card

## Structure

```
MATERIAL_PROPERTY <name>
  ID 1
  POROSITY 0.39
  CHARACTERISTIC_CURVES sf1
  PERMEABILITY
    PERM_ISO 1.188d-11
  /
  ...
END
```

Reader: `MaterialPropertyRead` (`src/pflotran/material.F90:294`). One `select case(trim(keyword))` over the whole card body (`src/pflotran/material.F90:348`); an unrecognized keyword is fatal via `InputKeywordUnrecognized` (`src/pflotran/material.F90:1019-1020`). The object is allocated and defaulted by `MaterialPropertyCreate` (`src/pflotran/material.F90:164`) — **that function is the authoritative default list** for everything below.

Post-read validations happen at the bottom of the same routine (`src/pflotran/material.F90:1024-1162`), including the requirement that `ID > 0` (`:1153-1162`).

---

## 1. Identity and linkage

| Card | Effect | Source | Default |
|---|---|---|---|
| `NAME <word>` | material name | `material.F90:350-352` | `''` (`:186`) |
| `ID <int>` | external material id, matched against `STRATA` | `material.F90:353-361` | `0`; must be `> 0` (`:1153-1162`) |
| `ACTIVE` / `INACTIVE` | include/exclude the material | `material.F90:362-365` | `ACTIVE` (`:185`) |
| `CHARACTERISTIC_CURVES <name>` **or** `SATURATION_FUNCTION <name>` | binds the named `CHARACTERISTIC_CURVES` block | `material.F90:366-369` | `''` (`:216`) |
| `THERMAL_CHARACTERISTIC_CURVES <name>` | binds a `THERMAL_CHARACTERISTIC_CURVES` block | `material.F90:370-372` | `''` (`:218`) |
| `MATERIAL_TRANSFORM <name>` | binds a `MATERIAL_TRANSFORM` block (illitization / buffer erosion, `src/pflotran/material_transform.F90`) | `material.F90:373-375` | `''` (`:217`) |

`SATURATION_FUNCTION` here is a plain alias for `CHARACTERISTIC_CURVES` — the same `case` label handles both (`material.F90:366`). Name resolution to an integer id happens later; a missing name is fatal ("Characteristic curve … not found", `src/pflotran/realization_subsurface.F90:845-851`).

Duplicate `ID`s and duplicate `NAME`s are both fatal, checked in `MaterialPropConvertListToArray` (`src/pflotran/material.F90:1298-1341`).

---

## 2. Porosity

| Card | Source | Default |
|---|---|---|
| `POROSITY <value \| DATASET name>` | `material.F90:469-472` | `UNINITIALIZED_DOUBLE` (`:204`) |

Read through `DatasetReadDoubleOrDataset`, so it accepts either a literal or a gridded dataset reference. Dimensionless volume fraction; the input record prints it with no unit suffix (`material.F90:2574-2582`).

There is **no range check on porosity in `material.F90`** — no `0 < φ < 1` assertion is present in the reader or in `MaterialPropertyCreate`. A calibration layer must bound it itself.

Porosity has three runtime flavors stored per cell (`src/pflotran/material_aux.F90:20-22`, `:58-63`):
- `POROSITY_INITIAL` / `porosity_0` — as given in the deck or initial condition,
- `POROSITY_BASE` / `porosity_base` — prescribed from outside the flow solve (geomechanics, mineral precipitation/dissolution),
- `POROSITY_CURRENT` / `porosity` — what the flow solve actually uses, after soil compressibility etc.

---

## 3. Permeability

`PERMEABILITY` opens a sub-block (`src/pflotran/material.F90:536-658`). Storage is the 3×3 array `material_property%permeability`, default `UNINITIALIZED_DOUBLE` (`:188`). Units are **m²**, per the input record (`material.F90:2529-2546`).

### 3.1 Isotropic

| Card | Effect | Source |
|---|---|---|
| `PERM_ISO <k>` | sets `(1,1)=(2,2)=(3,3)=k` and flags `perm_iso_read` | `material.F90:624-632` |
| `PERM_ISO_LOG10 <x>` | same, with `k = 10**x` | `material.F90:617-623` |
| `ISOTROPIC` | forces `isotropic_permeability = TRUE` | `material.F90:563-564` |

`PERM_ISO` combined with any anisotropic option is fatal: "PERM_ISO cannot be used in conjunction with anisotropic permeability options" (`material.F90:659-665`).

### 3.2 Diagonal anisotropy

| Card | Target | Source |
|---|---|---|
| `PERM_X` / `PERM_Y` / `PERM_Z` | `(1,1)` / `(2,2)` / `(3,3)` | `material.F90:569-580` |
| `PERM_X_LOG10` / `PERM_Y_LOG10` / `PERM_Z_LOG10` | same, `10**x` | `material.F90:581-592` |
| `ANISOTROPIC` | `isotropic_permeability = FALSE` | `material.F90:553-554` |
| `PERM_HORIZONTAL <k>` | sets `(1,1)=(2,2)=k`, leaves `(3,3)` uninitialized | `material.F90:646-653` |
| `VERTICAL_ANISOTROPY_RATIO <r>` | sets `isotropic = FALSE`, stores `r` | `material.F90:558-562` |

`PERM_HORIZONTAL` **requires** `VERTICAL_ANISOTROPY_RATIO` or it is fatal; when both are present, `(3,3) = (1,1) * r` (`material.F90:666-677`).

Regardless of the flags given, the reader auto-detects anisotropy: if `(1,1)`, `(2,2)`, `(3,3)` differ by more than `1.d-40` it forces `isotropic_permeability = FALSE` (`material.F90:678-683`).

### 3.3 Full tensor

`PERM_XY`, `PERM_XZ`, `PERM_YZ` (and `_LOG10` variants) fill the off-diagonals (`material.F90:593-616`). Rules enforced at `material.F90:685-715`:
- if any off-diagonal is set, **all three** must be, else fatal (`:689-695`);
- full-tensor permeability is fatal outside `RICHARDS_MODE` — an explicit "only tested in RICHARDS_MODE" guard (`:696-703`);
- setting them auto-enables `full_permeability_tensor` and `option%flow%full_perm_tensor` (`:704-709`);
- otherwise the off-diagonals are zeroed (`:710-715`).

`FULL_TENSOR` is also available as an explicit flag (`material.F90:555-557`).

The tensor is reduced to a face-normal scalar at flux time by `PermeabilityTensorToScalar` (`src/pflotran/material_aux.F90:421`); which reduction model is used (linear / flow / potential, `material_aux.F90:30-34`) is set by the grid type in `discretization.F90`, per the comment at `material_aux.F90:25-29`.

### 3.4 Dataset-driven permeability

| Card | Effect | Source |
|---|---|---|
| `DATASET <name>` | read `k` from a gridded dataset | `material.F90:639-645` |
| `PERMEABILITY_SCALING_FACTOR <s>` | multiply dataset values by `s` | `material.F90:565-568`, default `0.d0` (`:192`) |
| `RANDOM_DATASET` | **removed** — fatal error telling you to use `DATASET` | `material.F90:633-638` |

`PERMEABILITY_SCALING_FACTOR` and `VERTICAL_ANISOTROPY_RATIO` are applied **only** on the dataset path, in `SubsurfReadPermsFromFile` (`src/pflotran/init_subsurface.F90:947`, applied at `:1030-1039`). The scaling factor is ignored when permeability comes from a literal `PERM_ISO`/`PERM_X`. Its default of `0.d0` is a sentinel — the code only applies it `if (… > 0.d0)` (`init_subsurface.F90:1030-1032`).

Per-material `DATASET name` is internally split into `nameX`, `nameY`, `nameZ` (plus `nameXY/XZ/YZ` for full tensor) at `material.F90:1037-1058`.

### 3.5 `PERM_FACTOR` — pressure-driven permeability multiplier

Sub-block (`material.F90:748-780`) implementing a ramp from 1 to `MAX_PERMFACTOR` between `MIN_PRESSURE` and `MAX_PRESSURE` (comment at `:764-766`).

| Card | Source | Default |
|---|---|---|
| `MIN_PRESSURE` | `material.F90:767-769` | `0.d0` (`:256`) |
| `MAX_PRESSURE` | `material.F90:770-772` | `1.d6` (`:257`) |
| `MAX_PERMFACTOR` | `material.F90:773-775` | `1.d0` (`:258`) |

### 3.6 Porosity-driven permeability evolution

`PERMEABILITY_POWER`, `PERMEABILITY_CRITICAL_POROSITY`, `PERMEABILITY_MIN_SCALE_FACTOR` are read at `material.F90:781-792`. Because they are the highest-leverage and most misread knobs in this card, they have their own topic: **`porosity_permeability_evolution.md`**.

---

## 4. Thermal properties

| Card | Target | Internal units | Default | Source |
|---|---|---|---|---|
| `ROCK_DENSITY <v> [unit]` | `rock_density` | kg/m³ | `UNINITIALIZED_DOUBLE` (`:219`) | `material.F90:376-380` |
| `SPECIFIC_HEAT` / `HEAT_CAPACITY <v> [unit]` | `specific_heat` | J/kg-C | `UNINITIALIZED_DOUBLE` (`:220`) | `material.F90:381-385` |
| `THERMAL_CONDUCTIVITY_DRY <v> [unit]` | `thermal_conductivity_dry` | W/m-C | `UNINITIALIZED_DOUBLE` (`:221`) | `material.F90:395-404` |
| `THERMAL_CONDUCTIVITY_WET <v> [unit]` | `thermal_conductivity_wet` | W/m-C | `UNINITIALIZED_DOUBLE` (`:222`) | `material.F90:405-414` |
| `THERMAL_CONDUCTIVITY_FROZEN <v> [unit]` | `thermal_conductivity_frozen` | W/m-C | `UNINITIALIZED_DOUBLE` (`:252`) | `material.F90:419-425` |
| `THERMAL_COND_EXPONENT <v>` | `alpha` | – | `0.45d0` (`:223`) | `material.F90:415-418` |
| `THERMAL_COND_EXPONENT_FROZEN <v>` | `alpha_fr` | – | `0.95d0` (`:253`) | `material.F90:426-429` |

`ROCK_DENSITY`, both heat-capacity spellings, and all three thermal conductivities call `InputReadAndConvertUnits`, so an optional unit token may follow the value (`material.F90:379-380, 384-385, 399-401, 409-411, 423-425`). The two exponents do not — they are read raw (`:415-418`, `:426-429`).

### 4.1 The implicit thermal characteristic curve

Specifying `THERMAL_CONDUCTIVITY_DRY` or `_WET` **silently overwrites** `thermal_conductivity_func_name` with the synthetic name `"_TCC_<external_id>"` (`material.F90:402-404`, `:412-414`). PFLOTRAN then auto-builds a matching curve object in `realization_subsurface.F90` (`:760-762`), so you get a thermal characteristic curve without writing one.

Fallbacks when neither is given and the mode is not `G_MODE`/`SCO2_MODE`: `thermal_conductivity_wet = 2.d0` and `thermal_conductivity_dry = 5.d-1` W/m-C (`src/pflotran/realization_subsurface.F90:745-758`).

Which conductivity model is attached depends on the flow mode (`realization_subsurface.F90:763-780`): `TH_MODE`/`TH_TS_MODE` get `TCFFrozenCreate` (uses `alpha` and `alpha_fr`), everything else gets `TCFDefaultCreate`.

**Gotcha — `THERMAL_COND_EXPONENT` has no effect in the default model.** `TCFAssignDefault` does store `alpha` on the object (`src/pflotran/characteristic_curves_thermal.F90:1938-1957`), but `TCFDefaultConductivity` never reads it:

```
! based on Somerton et al., 1974:
! k_eff = k_dry + sqrt(s_l)*(k_wet-k_dry)
```
(`src/pflotran/characteristic_curves_thermal.F90:534-564`, formula at `:555-557`, comment citing Somerton et al. 1974 at `:549-550`). The exponent is honored only in the frozen/TH path, `Ke = (Sl + eps)**alpha` (`characteristic_curves_thermal.F90:1639`, `:1670-1671`). So calibrating `THERMAL_COND_EXPONENT` in a non-freezing run is a no-op.

`HEAT_CAPACITY` is converted J → MJ via `option%scale` when packed into the material parameter arrays (`src/pflotran/material.F90:1493-1494`). `MaterialSetupThermal` is a hard error in `RICHARDS_MODE`, `RICHARDS_TS_MODE`, `ZFLOW_MODE`, `WF_MODE`, `PNF_MODE` (`material.F90:1480-1484`) — i.e. thermal properties are meaningless in isothermal modes.

`ROCK_DENSITY` reaches the per-cell aux var as `soil_particle_density`, and only if initialized (`material.F90:1922-1925`).

---

## 5. Transport-side properties

### 5.1 Dispersivity

| Card | Target | Units | Default | Source |
|---|---|---|---|---|
| `LONGITUDINAL_DISPERSIVITY` | `dispersivity(1)` | m | `0.d0` (`:255`) | `material.F90:386-388` |
| `TRANSVERSE_DISPERSIVITY_H` | `dispersivity(2)` | m | `0.d0` | `material.F90:389-391` |
| `TRANSVERSE_DISPERSIVITY_V` | `dispersivity(3)` | m | `0.d0` | `material.F90:392-394` |

Units confirmed by the input record, which appends `' m'` (`material.F90:2635-2647`). All three are read raw — **no unit conversion**. Note a cosmetic bug in the record: the "transverse v" line prints `dispersivity(2)`, not `(3)` (`material.F90:2645`).

### 5.2 Tortuosity

| Card | Target | Default | Source |
|---|---|---|---|
| `TORTUOSITY <v \| DATASET>` | `tortuosity` | `1.d0` (`:209`) | `material.F90:473-478` |
| `ANISOTROPIC_TORTUOSITY` block with `TORTUOSITY_X/Y/Z` | `tortuosity_anisotropic(1:3)` | `UNINITIALIZED_DOUBLE` (`:210`) | `material.F90:479-509` |
| `TORTUOSITY_FUNCTION_OF_POROSITY <pwr>` | sets `tortuosity = UNINITIALIZED`, stores `tortuosity_func_porosity_pwr` | `UNINITIALIZED_DOUBLE` (`:212`) | `material.F90:518-523` |
| `TORTUOSITY_POWER <pwr>` | `tortuosity_pwr` | `0.d0` (`:211`) | `material.F90:793-796` |

`TORTUOSITY` and `ANISOTROPIC_TORTUOSITY` are mutually exclusive — specifying both is fatal (`material.F90:1132-1140`); and once `ANISOTROPIC_TORTUOSITY` is active globally, all three of X/Y/Z must be given (`:1141-1151`).

`TORTUOSITY_POWER` drives the same style of evolution as `PERMEABILITY_POWER`: `tortuosity = tortuosity0 * (porosity_base/porosity0)**tortuosity_pwr`, gated on `reaction%update_tortuosity` (`src/pflotran/realization_subsurface.F90:2021-2032`). The default `0.d0` makes the scale factor identically 1, i.e. no evolution.

### 5.3 Electrical / geophysics

All of these are gated by `InputCheckSupported` against `GEOPHYSICS_CLASS` (and mostly `FLOW_CLASS`), so they are rejected outside those process models.

| Card | Target | Default | Source |
|---|---|---|---|
| `ELECTRICAL_CONDUCTIVITY` | `material_electrical_conductivity` | `UNINITIALIZED_DOUBLE` (`:225`) | `material.F90:977-983` |
| `ARCHIE_CEMENTATION_EXPONENT` | `archie_cementation_exponent` | `UNINITIALIZED_DOUBLE` (`:227`) | `material.F90:984-990` |
| `ARCHIE_SATURATION_EXPONENT` | `archie_saturation_exponent` | `UNINITIALIZED_DOUBLE` (`:228`) | `material.F90:991-997` |
| `ARCHIE_TORTUOSITY_CONSTANT` | `archie_tortuosity_constant` | `UNINITIALIZED_DOUBLE` (`:229`) | `material.F90:998-1004` |
| `SURFACE_ELECTRICAL_CONDUCTIVITY` | `surface_electrical_conductivity` | `UNINITIALIZED_DOUBLE` (`:230`) | `material.F90:1005-1011` |
| `WAXMAN_SMITS_CLAY_CONDUCTIVITY` | `waxman_smits_clay_conductivity` | `UNINITIALIZED_DOUBLE` (`:236`) | `material.F90:1012-1018` |

No unit strings appear for these in the reader or the input record — units are unverifiable from `material.F90` alone.

---

## 6. Compressibility and geomechanics

| Card | Target | Default | Source |
|---|---|---|---|
| `SOIL_COMPRESSIBILITY_FUNCTION <name>` | selects the model | `''` (`:244`) | `material.F90:430-434` |
| `SOIL_COMPRESSIBILITY` / `BULK_COMPRESSIBILITY` / `POROSITY_COMPRESSIBILITY` | `soil_compressibility` | `UNINITIALIZED_DOUBLE` (`:245`) | `material.F90:435-449` |
| `SOIL_REFERENCE_PRESSURE <v \| INITIAL_PRESSURE>` | `soil_reference_pressure` (Pa) | `UNINITIALIZED_DOUBLE` (`:246`) | `material.F90:450-468` |
| `GEOMECHANICS_SUBSURFACE_PROPS` block | geomechanics coupling; sets `transient_porosity` | – | `material.F90:510-517` |
| `WIPP-FRACTURE` block | pressure-induced fracture perm/porosity (BRAGFLO 6.02 UM Eq. 136) | – | `material.F90:524-531` |
| `CREEP_CLOSURE_TABLE <name>` | `creep_closure_name` | `1` / `''` (`:241-242`) | `material.F90:532-535` |

The compressibility keyword you use **must match** the function you selected, and mismatches are fatal: `BRAGFLO`/`BULK_EXPONENTIAL` demand `BULK_COMPRESSIBILITY`; `POROSITY_EXPONENTIAL` demands `POROSITY_COMPRESSIBILITY`; `LEIJNSE`/`DEFAULT` demand `SOIL_COMPRESSIBILITY` (`material.F90:1061-1092`). Selecting a function without any compressibility value, or without a `SOIL_REFERENCE_PRESSURE`, is also fatal (`:1094-1111`). Setting `SOIL_REFERENCE_PRESSURE` both explicitly and as `INITIAL_PRESSURE` is fatal (`:1112-1119`).

Available function names (from the model-mapping switch, `material.F90:1691-1699`): `BRAGFLO`, `BULK_EXPONENTIAL`, `POROSITY_EXPONENTIAL`, `QUADRATIC`, `LEIJNSE`, `DEFAULT`, `LINEAR`.

Selecting any compressibility function sets `option%flow%transient_porosity = PETSC_TRUE` (`material.F90:1093`).

---

## 7. Other

| Card | Notes | Source |
|---|---|---|
| `TENSORIAL_REL_PERM_EXPONENT <e1 e2 e3>` | three doubles; fatal outside `ZFLOW_MODE` | `material.F90:803-807`, guard `:1122-1130` |
| `SECONDARY_CONTINUUM` block | dual-continuum geometry (`NESTED_CUBES` / `SLAB` / `NESTED_SPHERES`) and its own porosity/tortuosity/diffusion | `material.F90:808-976` |
| `MINERAL_SURFACE_AREA_POWER` | **removed** — fatal, redirects to `MINERAL_KINETICS` | `material.F90:797-802` |
| `PERM_PRINCIPAL_DIRECTION` | present but inside `#if 0`, i.e. **not compiled** | `material.F90:716-746` |

---

## 8. Calibration-knobs summary (motivating-deck cards)

Defaults cited from `MaterialPropertyCreate` (`src/pflotran/material.F90:164-290`).

| Keyword | Source line | Units | Default | Valid range | Controls |
|---|---|---|---|---|---|
| `POROSITY` | `material.F90:469-472` | – | uninitialized (`:204`) | `(0,1)`, **not code-checked** | pore volume; storage, transport velocity, and the base of the perm-evolution ratio |
| `PERMEABILITY / PERM_ISO` | `material.F90:624-632` | m² | uninitialized (`:188`) | `> 0` | intrinsic permeability, all three diagonal terms |
| `PERMEABILITY / PERM_X,_Y,_Z` | `material.F90:569-580` | m² | uninitialized | `> 0` | per-axis permeability; triggers anisotropy detection (`:678-683`) |
| `PERMEABILITY / PERM_*_LOG10` | `material.F90:581-592`, `:617-623` | log10(m²) | – | – | same values, log-space input (natural for a log-uniform sampler) |
| `PERMEABILITY / VERTICAL_ANISOTROPY_RATIO` | `material.F90:558-562` | – | uninitialized (`:191`) | `> 0` | `k_zz/k_xx`; required with `PERM_HORIZONTAL` |
| `PERMEABILITY / PERMEABILITY_SCALING_FACTOR` | `material.F90:565-568` | – | `0.d0` sentinel (`:192`) | `> 0` to take effect | multiplies dataset perms only (`init_subsurface.F90:1030-1039`) |
| `PERMEABILITY_POWER` | `material.F90:781-784` | – | `1.d0` (`:193`) | any | exponent of the porosity-ratio perm scale — see `porosity_permeability_evolution.md` |
| `PERMEABILITY_CRITICAL_POROSITY` | `material.F90:785-788` | – | `0.d0` (`:194`) | `[0, φ)` | percolation-threshold porosity subtracted in the ratio |
| `PERMEABILITY_MIN_SCALE_FACTOR` | `material.F90:789-792` | – | `1.d0` (`:195`) | `> 0` | **lower** clamp on the perm scale factor |
| `LONGITUDINAL_DISPERSIVITY` | `material.F90:386-388` | m | `0.d0` (`:255`) | `>= 0` | longitudinal mechanical dispersion |
| `TRANSVERSE_DISPERSIVITY_H` / `_V` | `material.F90:389-394` | m | `0.d0` | `>= 0` | transverse dispersion |
| `TORTUOSITY` | `material.F90:473-478` | – | `1.d0` (`:209`) | `(0,1]` | diffusive path scaling |
| `TORTUOSITY_POWER` | `material.F90:793-796` | – | `0.d0` (`:211`) | any | exponent of porosity-ratio tortuosity evolution (`realization_subsurface.F90:2027-2029`) |
| `ROCK_DENSITY` | `material.F90:376-380` | kg/m³ (convertible) | uninitialized (`:219`) | `> 0` | grain density → bulk heat capacity, sorption |
| `HEAT_CAPACITY` / `SPECIFIC_HEAT` | `material.F90:381-385` | J/kg-C (convertible) | uninitialized (`:220`) | `> 0` | soil heat capacity (scaled to MJ, `:1493-1494`) |
| `THERMAL_CONDUCTIVITY_DRY` | `material.F90:395-404` | W/m-C (convertible) | `0.5` fallback (`realization_subsurface.F90:755-757`) | `> 0` | `k_dry` in `k = k_dry + sqrt(Sl)(k_wet-k_dry)` |
| `THERMAL_CONDUCTIVITY_WET` | `material.F90:405-414` | W/m-C (convertible) | `2.0` fallback (`realization_subsurface.F90:751-753`) | `> k_dry` | `k_wet` in the same expression |
| `THERMAL_CONDUCTIVITY_FROZEN` | `material.F90:419-425` | W/m-C (convertible) | uninitialized (`:252`) | `> 0` | frozen-soil conductivity (TH mode only) |
| `THERMAL_COND_EXPONENT` | `material.F90:415-418` | – | `0.45d0` (`:223`) | `> 0` | Kersten exponent — **no effect unless TH/frozen** (`characteristic_curves_thermal.F90:534-564`) |
| `THERMAL_COND_EXPONENT_FROZEN` | `material.F90:426-429` | – | `0.95d0` (`:253`) | `> 0` | frozen Kersten exponent (`characteristic_curves_thermal.F90:1671`) |
| `SOIL_COMPRESSIBILITY` (etc.) | `material.F90:435-449` | model-dependent | uninitialized (`:245`) | `>= 0` | pore compressibility; requires a matching `SOIL_COMPRESSIBILITY_FUNCTION` |
| `SOIL_REFERENCE_PRESSURE` | `material.F90:450-468` | Pa | uninitialized (`:246`) | – | reference `P` for the compressibility law |

### Sampling guidance

- Prefer `PERM_ISO_LOG10` / `PERM_X_LOG10` when sampling permeability; permeability spans orders of magnitude and the log10 cards let a uniform sampler act in log space without a wrapper (`material.F90:581-592`, `:617-623`).
- `THERMAL_COND_EXPONENT` is a dead knob outside TH/freezing — do not spend samples on it in an isothermal or general-mode run (§4.1).
- `PERMEABILITY_SCALING_FACTOR` is a dead knob when permeability is given literally (§3.4).
- Nothing in this card range-checks porosity or permeability. All physical bounds must be imposed by the calibration layer.

---

## Related

- `characteristic_curves.md` — the `CHARACTERISTIC_CURVES` block this card binds to.
- `porosity_permeability_evolution.md` — `PERMEABILITY_POWER`, `PERMEABILITY_CRITICAL_POROSITY`, `PERMEABILITY_MIN_SCALE_FACTOR`.
